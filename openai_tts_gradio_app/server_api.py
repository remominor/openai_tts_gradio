from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

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


def fetch_voices(endpoints: APIEndpoints) -> tuple[list[dict[str, Any]], str]:
    response = httpx.get(endpoints.voices_url, timeout=DEFAULT_REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    raw_voices: Any = []
    if isinstance(payload, dict):
        if isinstance(payload.get("voices"), list):
            raw_voices = payload["voices"]
        elif payload.get("object") == "list" and isinstance(payload.get("data"), list):
            raw_voices = payload["data"]

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
        "voice_name": voice_name.strip(),
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
    valid_voice_values = {value for _label, value in voice_choices}
    voice_value = voice_id if voice_id in valid_voice_values else "default"

    voice_label = result.get("voice", {}).get("label", voice_value)
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
