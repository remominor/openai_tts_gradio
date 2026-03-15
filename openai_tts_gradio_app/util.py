from __future__ import annotations

import inspect
from typing import Any

import gradio as gr
import httpx

from .config import (
    LOGGER,
    REQUEST_MODE_AUTO,
    REQUEST_MODE_NON_STREAMING,
    REQUEST_MODE_STREAMING,
    STREAM_FORMAT_AUDIO,
    STREAM_FORMAT_DEFAULT,
    STREAM_FORMAT_SSE,
)
from .events import reset_live_audio_event


def supports_kwarg(callable_obj: Any, name: str) -> bool:
    try:
        return name in inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False


def format_error(prefix: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text.strip() or str(exc)
        return f"{prefix}: HTTP {exc.response.status_code} - {detail}"
    return f"{prefix}: {exc}"


def status_markup(message: str, *, ok: bool) -> str:
    css_class = "status-ok" if ok else "status-warn"
    return f"<div class='status-box'><p class='{css_class}'>{message}</p></div>"


def store_model_selection(value: str | None) -> str | None:
    return value or None


def store_voice_selection(value: str | None) -> str:
    return value or "default"


def normalize_request_mode(value: str | None) -> str:
    if value in {
        REQUEST_MODE_AUTO,
        REQUEST_MODE_STREAMING,
        REQUEST_MODE_NON_STREAMING,
    }:
        return value
    return REQUEST_MODE_AUTO


def normalize_stream_format(value: str | None) -> str:
    if value in {
        STREAM_FORMAT_DEFAULT,
        STREAM_FORMAT_SSE,
        STREAM_FORMAT_AUDIO,
    }:
        return value
    return STREAM_FORMAT_DEFAULT


def browser_audio_enabled(request_mode: str | None, stream_format: str | None) -> bool:
    mode = normalize_request_mode(request_mode)
    requested_stream_format = normalize_stream_format(stream_format)
    enabled = (
        mode != REQUEST_MODE_NON_STREAMING
        and requested_stream_format == STREAM_FORMAT_AUDIO
    )
    LOGGER.debug(
        "browser_audio_enabled mode=%s stream_format=%s enabled=%s",
        mode,
        requested_stream_format,
        enabled,
    )
    return enabled


def reset_audio_outputs(request_mode: str) -> tuple[str, dict[str, Any], str]:
    mode = normalize_request_mode(request_mode)
    if mode == REQUEST_MODE_NON_STREAMING:
        message = "Non-streaming request started."
    elif mode == REQUEST_MODE_STREAMING:
        message = "Streaming request started."
    else:
        message = "Auto request started."
    return (
        reset_live_audio_event(),
        gr.update(value=None),
        status_markup(message, ok=True),
    )


def generation_control_updates(
    request_mode: str | None,
    stream_format: str | None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    mode = normalize_request_mode(request_mode)
    requested_stream_format = normalize_stream_format(stream_format)
    use_browser_audio = browser_audio_enabled(mode, requested_stream_format)

    if use_browser_audio:
        route_message = (
            "Active path: browser audio-body streaming. This bypasses the server-side "
            "trigger bridge and runs the request directly in the browser."
        )
    elif mode == REQUEST_MODE_NON_STREAMING:
        route_message = "Active path: completed server response through Gradio."
    elif requested_stream_format == STREAM_FORMAT_SSE:
        route_message = "Active path: SSE live streaming through Gradio."
    else:
        route_message = "Active path: server request through Gradio with automatic stream detection."

    return (
        gr.update(visible=not use_browser_audio),
        gr.update(visible=use_browser_audio),
        status_markup(route_message, ok=True),
    )
