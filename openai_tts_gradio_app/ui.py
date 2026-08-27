from __future__ import annotations

from typing import Any

import gradio as gr

from .browser import browser_generate_click_js, live_player_head
from .config import (
    APP_THEME,
    CUSTOM_CSS,
    LOGGER,
    REQUEST_MODE_AUTO,
    REQUEST_MODE_NON_STREAMING,
    REQUEST_MODE_STREAMING,
    STREAM_FORMAT_AUDIO,
    STREAM_FORMAT_DEFAULT,
    STREAM_FORMAT_SSE,
)
from .server_api import (
    delete_voice,
    fetch_models,
    fetch_voices,
    load_voice_details,
    load_server_history,
    normalize_server_base_url,
    remember_server_url,
    update_voice,
    upload_voice,
    voice_dropdown_choices,
)
from .streaming import dispatch_server_generate_request
from .util import (
    format_error,
    generation_control_updates,
    status_markup,
    store_model_selection,
    store_voice_selection,
    supports_kwarg,
)


def blocks_constructor_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"title": "Remote OpenAI TTS"}
    if not supports_kwarg(gr.Blocks.launch, "theme"):
        kwargs["theme"] = APP_THEME
    if not supports_kwarg(gr.Blocks.launch, "css"):
        kwargs["css"] = CUSTOM_CSS
    if not supports_kwarg(gr.Blocks.launch, "head"):
        kwargs["head"] = live_player_head()
    return kwargs


def launch_kwargs(
    demo: gr.Blocks,
    *,
    host: str,
    port: int,
    share: bool,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "server_name": host,
        "server_port": port,
        "share": share,
    }
    if supports_kwarg(demo.launch, "theme"):
        kwargs["theme"] = APP_THEME
    if supports_kwarg(demo.launch, "css"):
        kwargs["css"] = CUSTOM_CSS
    if supports_kwarg(demo.launch, "head"):
        kwargs["head"] = live_player_head()
    return kwargs


def refresh_server_data(
    server_base_url: str,
    current_model: str | None,
    current_voice: str | None,
) -> tuple[dict[str, Any], dict[str, Any], str, str | None, str]:
    try:
        endpoints = normalize_server_base_url(server_base_url)
    except Exception as exc:
        return (
            gr.update(choices=[], value=None),
            gr.update(choices=[("default", "default")], value="default"),
            status_markup(str(exc), ok=False),
            None,
            "default",
        )

    models: list[str] = []
    voices: list[dict[str, Any]] = []
    voice_dir = ""
    model_error: Exception | None = None
    voice_error: Exception | None = None

    try:
        models = fetch_models(endpoints)
    except Exception as exc:
        model_error = exc
    try:
        voices, voice_dir = fetch_voices(endpoints)
    except Exception as exc:
        voice_error = exc

    current_model_value = (current_model or "").strip() or None
    model_value = current_model_value or (models[0] if models else None)
    model_choices = list(models)
    if model_value and model_value not in model_choices:
        model_choices.append(model_value)
    voice_choices = voice_dropdown_choices(voices)
    valid_voice_values = {value for _label, value in voice_choices}
    current_voice_value = (current_voice or "").strip() or "default"
    if current_voice_value not in valid_voice_values:
        voice_choices.append((current_voice_value, current_voice_value))
        valid_voice_values.add(current_voice_value)
    voice_value = current_voice_value

    ok = bool(models)
    if model_error is not None and not models:
        status = format_error("Model refresh failed", model_error)
        if voice_error is None:
            status += (
                f". Voice listing still loaded {max(len(voice_choices) - 1, 0)} stored voice(s)"
            )
        return (
            gr.update(choices=model_choices, value=model_value),
            gr.update(choices=voice_choices, value=voice_value),
            status_markup(status, ok=False),
            model_value,
            voice_value,
        )

    status = (
        f"Connected to <code>{endpoints.v1_base}</code>. "
        f"Loaded {len(models)} model(s) and {max(len(voice_choices) - 1, 0)} stored voice(s)"
    )
    if voice_dir:
        status += f" from <code>{voice_dir}</code>."
    else:
        status += "."
    if voice_error is not None:
        ok = bool(models)
        status += " " + format_error("Voice list unavailable", voice_error)

    LOGGER.debug(
        "server refresh models=%s voices=%s voice_dir=%s",
        len(models),
        max(len(voice_choices) - 1, 0),
        voice_dir,
    )
    return (
        gr.update(choices=model_choices, value=model_value),
        gr.update(choices=voice_choices, value=voice_value),
        status_markup(status, ok=ok),
        model_value,
        voice_value,
    )


def create_demo(default_server_base_url: str) -> gr.Blocks:
    initial_route = generation_control_updates(REQUEST_MODE_AUTO, STREAM_FORMAT_DEFAULT)[2]

    with gr.Blocks(**blocks_constructor_kwargs()) as demo:
        with gr.Column(elem_classes=["app-shell"]):
            gr.Markdown(
                """
                <div class="app-hero">
                  <h1>Remote OpenAI TTS</h1>
                  <p>
                    A small Gradio client for OpenAI-compatible text-to-speech servers.
                    Point it at a server base URL, refresh models and stored voices,
                    upload new voices, live-stream playback, and keep the completed
                    waveform for replay or download.
                  </p>
                </div>
                """
            )

            with gr.Row():
                server_base_url = gr.Dropdown(
                    label="Server Base URL",
                    choices=load_server_history(default_server_base_url),
                    value=default_server_base_url,
                    allow_custom_value=True,
                    filterable=True,
                    info="Select a recent server or enter a root URL / URL ending in /v1.",
                    scale=5,
                )
                refresh_button = gr.Button("Refresh Models & Voices", variant="secondary", scale=1)

            server_status = gr.HTML(
                value=status_markup("Enter a server URL, then refresh.", ok=True)
            )
            selected_model = gr.State(value=None)
            selected_voice = gr.State(value="default")

            with gr.Row():
                model_dropdown = gr.Dropdown(
                    label="Model",
                    choices=[],
                    value=None,
                    interactive=True,
                    allow_custom_value=True,
                    info="Select a listed model or type one directly.",
                )
                voice_dropdown = gr.Dropdown(
                    label="Voice",
                    choices=[("default", "default")],
                    value="default",
                    interactive=True,
                    allow_custom_value=True,
                    info="Select a listed voice or type one directly.",
                )

            with gr.Accordion("Upload Voice", open=False):
                with gr.Column(elem_classes=["upload-box"]):
                    gr.Markdown(
                        "Upload an audio file from this machine or register one by URL. "
                        "Exactly one of the two inputs below must be set."
                    )
                    with gr.Row():
                        voice_file = gr.Audio(
                            label="Voice File",
                            type="filepath",
                            sources=["upload"],
                        )
                        voice_url = gr.Textbox(
                            label="Voice URL",
                            placeholder="https://example.com/reference.wav",
                        )
                    with gr.Row():
                        voice_name = gr.Textbox(
                            label="Voice Name",
                            placeholder="optional name",
                        )
                        preload_checkbox = gr.Checkbox(
                            label="Preload Voice Cache",
                            value=True,
                        )
                    voice_ref_text = gr.Textbox(
                        label="Reference Transcript",
                        lines=3,
                        placeholder="Optional transcript for the reference audio",
                    )
                    upload_button = gr.Button("Upload Voice", variant="secondary")
                    upload_status = gr.HTML(
                        value=status_markup("No voice upload attempted yet.", ok=True)
                    )

            with gr.Accordion("Manage Selected Voice", open=False):
                gr.Markdown(
                    "Select an uploaded voice above to edit its name or transcript, "
                    "or permanently delete it. Configured voices are read-only."
                )
                manage_voice_name = gr.Textbox(label="Voice Name")
                manage_voice_ref_text = gr.Textbox(label="Reference Transcript", lines=3)
                with gr.Row():
                    update_voice_button = gr.Button("Save Voice Changes", variant="secondary")
                    delete_voice_button = gr.Button("Delete Voice", variant="stop")
                manage_voice_status = gr.HTML(
                    value=status_markup("Select an uploaded voice to manage it.", ok=True)
                )

            text_input = gr.Textbox(
                label="Text to Synthesize",
                placeholder="Enter English text here...",
                lines=7,
                max_lines=14,
            )
            instructions_input = gr.Textbox(
                label="Instructions (optional)",
                placeholder="Voice design or direction, e.g. speak warmly and slowly…",
                lines=2,
            )
            guidance_scale = gr.Textbox(
                label="CFG Scale (blank = server default)",
                value="",
                placeholder="Auto",
            )
            request_mode = gr.Radio(
                label="Request Mode",
                choices=[
                    ("Auto", REQUEST_MODE_AUTO),
                    ("Streaming", REQUEST_MODE_STREAMING),
                    ("Non-streaming", REQUEST_MODE_NON_STREAMING),
                ],
                value=REQUEST_MODE_AUTO,
                info="Auto uses SSE when available and falls back to a completed audio response.",
            )
            stream_format = gr.Radio(
                label="Stream Format",
                choices=[
                    ("Default", STREAM_FORMAT_DEFAULT),
                    ("SSE", STREAM_FORMAT_SSE),
                    ("Audio", STREAM_FORMAT_AUDIO),
                ],
                value=STREAM_FORMAT_DEFAULT,
                info="Audio uses the Gradio/server request path by default for compatibility with servers that do not allow browser-direct fetches.",
            )
            generation_route = gr.HTML(value=initial_route)

            server_generate_button = gr.Button(
                "Generate Speech",
                variant="primary",
                elem_classes=["primary-action"],
                elem_id="openai-tts-generate-server",
                visible=True,
            )
            browser_generate_button = gr.Button(
                "Generate Speech in Browser",
                variant="primary",
                elem_classes=["primary-action"],
                elem_id="openai-tts-generate-browser",
                visible=False,
            )

            gr.HTML(
                value="""
                <div id="openai-tts-live-player" class="status-box">
                  <p style="font-weight:600; margin-bottom:4px;">Live Playback</p>
                  <p id="openai-tts-live-player-status" class="status-ok">Idle</p>
                </div>
                """,
            )
            live_audio_events = gr.Textbox(
                label="Live Audio Events",
                visible="hidden",
                elem_id="openai-tts-live-events",
                elem_classes=["dom-hidden-control"],
            )
            output_audio = gr.Audio(
                label="Generated Speech",
                type="filepath",
                autoplay=False,
                waveform_options=gr.WaveformOptions(show_recording_waveform=False),
                elem_id="openai-tts-output-audio",
            )
            generation_status = gr.HTML(
                value=status_markup("No synthesis request submitted yet.", ok=True),
                elem_id="openai-tts-generation-status",
            )

            refresh_button.click(
                fn=refresh_server_data,
                inputs=[server_base_url, selected_model, selected_voice],
                outputs=[
                    model_dropdown,
                    voice_dropdown,
                    server_status,
                    selected_model,
                    selected_voice,
                ],
                queue=False,
            )

            model_dropdown.change(
                fn=store_model_selection,
                inputs=[model_dropdown],
                outputs=[selected_model],
                queue=False,
            )
            voice_dropdown.change(
                fn=store_voice_selection,
                inputs=[voice_dropdown],
                outputs=[selected_voice],
                queue=False,
            )

            server_base_url.change(
                fn=remember_server_url,
                inputs=[server_base_url],
                outputs=[server_base_url],
                queue=False,
            )
            voice_dropdown.change(
                fn=load_voice_details,
                inputs=[server_base_url, voice_dropdown],
                outputs=[manage_voice_name, manage_voice_ref_text, manage_voice_status],
                queue=False,
            )

            upload_button.click(
                fn=upload_voice,
                inputs=[
                    server_base_url,
                    voice_file,
                    voice_url,
                    voice_name,
                    voice_ref_text,
                    preload_checkbox,
                    selected_voice,
                ],
                outputs=[voice_dropdown, upload_status, server_status, selected_voice],
            )

            update_voice_button.click(
                fn=update_voice,
                inputs=[server_base_url, selected_voice, manage_voice_name, manage_voice_ref_text],
                outputs=[
                    voice_dropdown,
                    manage_voice_name,
                    manage_voice_ref_text,
                    manage_voice_status,
                    selected_voice,
                ],
            )

            delete_voice_button.click(
                fn=delete_voice,
                inputs=[server_base_url, selected_voice],
                outputs=[
                    voice_dropdown,
                    manage_voice_name,
                    manage_voice_ref_text,
                    manage_voice_status,
                    selected_voice,
                ],
                js="""(server_url, voice_id) => {
                    if (!window.confirm('Delete this uploaded voice permanently?')) {
                        return [server_url, '__cancelled__'];
                    }
                    return [server_url, voice_id];
                }""",
            )

            request_mode.change(
                fn=generation_control_updates,
                inputs=[request_mode, stream_format],
                outputs=[server_generate_button, browser_generate_button, generation_route],
                queue=False,
            )
            stream_format.change(
                fn=generation_control_updates,
                inputs=[request_mode, stream_format],
                outputs=[server_generate_button, browser_generate_button, generation_route],
                queue=False,
            )

            server_generate_button.click(
                fn=dispatch_server_generate_request,
                inputs=[
                    server_base_url,
                    model_dropdown,
                    voice_dropdown,
                    text_input,
                    request_mode,
                    stream_format,
                    instructions_input,
                    guidance_scale,
                ],
                outputs=[live_audio_events, output_audio, generation_status],
                concurrency_limit=None,
            )

            browser_generate_button.click(
                fn=None,
                inputs=[
                    server_base_url,
                    model_dropdown,
                    voice_dropdown,
                    text_input,
                    request_mode,
                    instructions_input,
                    guidance_scale,
                ],
                outputs=[generation_status],
                js=browser_generate_click_js(),
                queue=False,
                show_progress="hidden",
            )

            demo.load(
                fn=refresh_server_data,
                inputs=[server_base_url, selected_model, selected_voice],
                outputs=[
                    model_dropdown,
                    voice_dropdown,
                    server_status,
                    selected_model,
                    selected_voice,
                ],
            )
            demo.load(
                fn=generation_control_updates,
                inputs=[request_mode, stream_format],
                outputs=[server_generate_button, browser_generate_button, generation_route],
                queue=False,
            )

    return demo
