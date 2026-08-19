from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

import gradio as gr
import httpx

from .config import APIEndpoints, DEFAULT_REQUEST_TIMEOUT, LOGGER
from .util import format_error, status_markup, store_voice_selection


def normalize_server_base_url(server_base_url: str) -> APIEndpoints:
    normalized = server_base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("Server base URL is required.")

    if normalized.endswith("/v1"):
        root_base = normalized[:-3]
        v1_base = normalized
    else:
        root_base = normalized
        v1_base = f"{normalized}/v1"

    return APIEndpoints(
        root_base=root_base,
        v1_base=v1_base,
        models_url=f"{v1_base}/audio/models",
        models_fallback_url=f"{v1_base}/models",
        speech_url=f"{v1_base}/audio/speech",
        voices_url=f"{v1_base}/audio/voices",
        upload_url=f"{root_base}/upload_voice",
    )


def fetch_models(endpoints: APIEndpoints) -> list[str]:
    last_error: Exception | None = None
    for url in (endpoints.models_url, endpoints.models_fallback_url):
        try:
            response = httpx.get(url, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            models = [
                str(item["id"])
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
            LOGGER.debug("loaded %s models from %s", len(models), url)
            return models
        except Exception as exc:
            last_error = exc
            LOGGER.debug("model fetch failed url=%s error=%s", url, exc)
    if last_error is not None:
        raise last_error
    return []


def normalize_voice_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    voice_id = str(item.get("id") or item.get("voice_id") or "").strip()
    if not voice_id:
        return None

    label = str(
        item.get("label")
        or item.get("name")
        or item.get("filename")
        or voice_id
    ).strip() or voice_id

    normalized = dict(item)
    normalized["id"] = voice_id
    normalized["label"] = label
    return normalized


def extract_raw_voice_entries(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    data_entries = payload.get("data")
    if isinstance(data_entries, list):
        structured_entries = [item for item in data_entries if isinstance(item, dict)]
        if structured_entries:
            return structured_entries

    voice_entries = payload.get("voices")
    if not isinstance(voice_entries, list):
        return []

    structured_entries = [item for item in voice_entries if isinstance(item, dict)]
    if structured_entries:
        return structured_entries

    fallback_entries: list[dict[str, Any]] = []
    for item in voice_entries:
        voice_id = str(item).strip()
        if voice_id:
            fallback_entries.append({"id": voice_id, "name": voice_id})
    return fallback_entries


def fetch_voices(endpoints: APIEndpoints) -> tuple[list[dict[str, Any]], str]:
    response = httpx.get(endpoints.voices_url, timeout=DEFAULT_REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    raw_voices = extract_raw_voice_entries(payload)
    voices: list[dict[str, Any]] = []
    for item in raw_voices:
        if not isinstance(item, dict):
            continue
        normalized = normalize_voice_entry(item)
        if normalized is not None:
            voices.append(normalized)

    LOGGER.debug("loaded %s voices from %s", len(voices), endpoints.voices_url)
    return voices, str(payload.get("voice_dir", "")) if isinstance(payload, dict) else ""


def voice_dropdown_choices(voices: list[dict[str, Any]]) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = [("default", "default")]
    for voice in voices:
        voice_id = str(voice.get("id", "")).strip()
        label = str(voice.get("label", voice_id)).strip() or voice_id
        if voice_id:
            choices.append((label, voice_id))
    return choices


def _voice_url(endpoints: APIEndpoints, voice_id: str) -> str:
    return f"{endpoints.voices_url}/{quote(voice_id, safe='')}"


def load_voice_details(
    server_base_url: str,
    voice_id: str | None,
) -> tuple[str, str, str]:
    """Load editable metadata for the selected voice."""
    if not voice_id or voice_id == "default":
        return "", "", "Select an uploaded voice to edit."
    try:
        endpoints = normalize_server_base_url(server_base_url)
        voices, _voice_dir = fetch_voices(endpoints)
        selected = next((item for item in voices if item.get("id") == voice_id), None)
        if selected is None:
            return "", "", status_markup("Selected voice was not found on the server.", ok=False)
        return (
            str(selected.get("name") or selected.get("id") or ""),
            str(selected.get("ref_text") or ""),
            status_markup(f"Editing <code>{selected.get('name') or selected.get('id')}</code>.", ok=True),
        )
    except Exception as exc:
        return "", "", status_markup(format_error("Voice details failed", exc), ok=False)


def update_voice(
    server_base_url: str,
    voice_id: str | None,
    voice_name: str,
    ref_text: str,
) -> tuple[dict[str, Any], str, str, str, str]:
    if not voice_id or voice_id == "default":
        return gr.update(), "", "", status_markup("Select an uploaded voice to update.", ok=False), store_voice_selection(voice_id)
    try:
        endpoints = normalize_server_base_url(server_base_url)
        response = httpx.patch(
            _voice_url(endpoints, voice_id),
            json={"name": voice_name.strip(), "ref_text": ref_text.strip()},
            timeout=DEFAULT_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        updated = response.json()
        voices, _voice_dir = fetch_voices(endpoints)
        choices = voice_dropdown_choices(voices)
        new_voice_id = str(updated.get("id") or updated.get("voice_id") or voice_id)
        status = status_markup(f"Updated voice <code>{new_voice_id}</code>.", ok=True)
        return (
            gr.update(choices=choices, value=new_voice_id),
            str(updated.get("name") or new_voice_id),
            str(updated.get("ref_text") or ""),
            status,
            new_voice_id,
        )
    except Exception as exc:
        return gr.update(), voice_name, ref_text, status_markup(format_error("Voice update failed", exc), ok=False), store_voice_selection(voice_id)


def delete_voice(
    server_base_url: str,
    voice_id: str | None,
) -> tuple[dict[str, Any], str, str, str, str]:
    if voice_id == "__cancelled__":
        return gr.update(), gr.skip(), gr.skip(), gr.skip(), gr.skip()
    if not voice_id or voice_id == "default":
        return gr.update(), "", "", status_markup("Select an uploaded voice to delete.", ok=False), store_voice_selection(voice_id)
    try:
        endpoints = normalize_server_base_url(server_base_url)
        response = httpx.delete(_voice_url(endpoints, voice_id), timeout=DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()
        voices, _voice_dir = fetch_voices(endpoints)
        status = status_markup(f"Deleted voice <code>{voice_id}</code>.", ok=True)
        return (
            gr.update(choices=voice_dropdown_choices(voices), value="default"),
            "",
            "",
            status,
            "default",
        )
    except Exception as exc:
        return gr.update(), "", "", status_markup(format_error("Voice deletion failed", exc), ok=False), store_voice_selection(voice_id)


def upload_voice(
    server_base_url: str,
    voice_file: str | None,
    voice_url: str,
    voice_name: str,
    ref_text: str,
    preload: bool,
    current_voice: str | None,
) -> tuple[dict[str, Any], str, str, str]:
    file_path = voice_file or None
    voice_url = voice_url.strip()
    if bool(file_path) == bool(voice_url):
        return (
            gr.update(),
            status_markup(
                "Provide exactly one of Voice File or Voice URL for upload.",
                ok=False,
            ),
            gr.skip(),
            store_voice_selection(current_voice),
        )

    try:
        endpoints = normalize_server_base_url(server_base_url)
    except Exception as exc:
        return (
            gr.update(),
            status_markup(str(exc), ok=False),
            gr.skip(),
            store_voice_selection(current_voice),
        )

    data = {
        # The server's upload API calls this form field "name". Keep the
        # client-side variable named voice_name because it describes the UI
        # value, but submit the API's field name so it is persisted.
        "name": voice_name.strip(),
        "ref_text": ref_text.strip(),
        "preload": "true" if preload else "false",
    }
    files = None
    handle = None
    if file_path:
        path = Path(file_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        handle = path.open("rb")
        files = {"voice_file": (path.name, handle, mime_type)}
    else:
        data["voice_url"] = voice_url

    try:
        response = httpx.post(
            endpoints.upload_url,
            data=data,
            files=files,
            timeout=None,
        )
        response.raise_for_status()
        result = response.json()
        voices, voice_dir = fetch_voices(endpoints)
    except Exception as exc:
        return (
            gr.update(),
            status_markup(format_error("Voice upload failed", exc), ok=False),
            gr.skip(),
            store_voice_selection(current_voice),
        )
    finally:
        if handle is not None:
            handle.close()

    voice_id = str(result.get("voice_id") or current_voice or "default")
    voice_choices = voice_dropdown_choices(voices)
    uploaded_voice = next(
        (
            voice
            for voice in voices
            if str(voice.get("voice_id") or "") == voice_id
            or str(voice.get("id") or "") == voice_id
        ),
        None,
    )
    voice_value = str(uploaded_voice.get("id")) if uploaded_voice else "default"

    voice_label = (uploaded_voice or {}).get("label", voice_value)
    status = f"Uploaded voice <code>{voice_label}</code>"
    if voice_dir:
        status += f" to <code>{voice_dir}</code>"
    num_steps = result.get("num_steps")
    if num_steps is not None:
        status += f" with {num_steps} cached code steps"
    status += "."

    refresh_status = (
        f"Server refreshed after upload. {max(len(voice_choices) - 1, 0)} stored voice(s) available."
    )
    return (
        gr.update(choices=voice_choices, value=voice_value),
        status_markup(status, ok=True),
        status_markup(refresh_status, ok=True),
        voice_value,
    )
