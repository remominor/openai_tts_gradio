from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import gradio as gr
import httpx

from .audio import (
    audio_suffix_from_response,
    concat_wav_chunks_to_file,
    parse_wav_stream_header,
    wav_bytes_from_pcm_frames,
    write_audio_bytes_tempfile,
    write_audio_tempfile,
    write_pcm_audio_tempfile,
)
from .config import (
    LOGGER,
    PCM_STREAM_CHANNELS,
    PCM_STREAM_SAMPLE_RATE,
    PCM_STREAM_SAMPLE_WIDTH,
    REQUEST_MODE_NON_STREAMING,
    REQUEST_MODE_STREAMING,
    STREAM_AUDIO_BODY_CHUNK_BYTES,
    STREAM_FORMAT_AUDIO,
    STREAM_FORMAT_DEFAULT,
    STREAM_FORMAT_SSE,
)
from .events import build_live_audio_event, make_live_audio_batch, make_live_audio_event
from .server_api import normalize_server_base_url
from .util import (
    format_error,
    normalize_request_mode,
    normalize_stream_format,
    reset_audio_outputs,
    status_markup,
)


def dispatch_server_generate_request(
    server_base_url: str,
    model_id: str | None,
    voice_id: str | None,
    text: str,
    request_mode: str,
    stream_format: str,
    instructions: str = "",
    guidance_scale: float | str | None = None,
) -> Any:
    live_events, output_audio, generation_status = reset_audio_outputs(request_mode)
    yield live_events, output_audio, generation_status

    for live_audio_events, output_audio, generation_status in generate_speech(
        server_base_url,
        model_id,
        voice_id,
        text,
        request_mode,
        stream_format,
        instructions,
        guidance_scale,
    ):
        yield live_audio_events, output_audio, generation_status


def generate_speech(
    server_base_url: str,
    model_id: str | None,
    voice_id: str | None,
    text: str,
    request_mode: str,
    stream_format: str,
    instructions: str = "",
    guidance_scale: float | str | None = None,
) -> Any:
    request_text = text.strip()
    if not request_text:
        yield (
            gr.skip(),
            gr.skip(),
            status_markup("Enter some text to synthesize.", ok=False),
        )
        return
    if not model_id:
        yield (
            gr.skip(),
            gr.skip(),
            status_markup("Select a model before generating speech.", ok=False),
        )
        return

    try:
        endpoints = normalize_server_base_url(server_base_url)
    except Exception as exc:
        yield gr.skip(), gr.skip(), status_markup(str(exc), ok=False)
        return

    mode = normalize_request_mode(request_mode)
    requested_stream_format = normalize_stream_format(stream_format)
    payload = {
        "model": model_id,
        "input": request_text,
        "voice": voice_id or "default",
        "response_format": "wav",
        "stream": mode != REQUEST_MODE_NON_STREAMING,
    }
    if instructions and instructions.strip():
        payload["instructions"] = instructions.strip()
    if guidance_scale is not None and str(guidance_scale).strip():
        payload["guidance_scale"] = guidance_scale
    if mode != REQUEST_MODE_NON_STREAMING and requested_stream_format != STREAM_FORMAT_DEFAULT:
        payload["stream_format"] = requested_stream_format

    LOGGER.debug(
        "generate_speech start mode=%s stream_format=%s model=%s voice=%s endpoint=%s",
        mode,
        requested_stream_format,
        model_id,
        voice_id or "default",
        endpoints.speech_url,
    )

    t0 = time.perf_counter()
    stream_id = uuid.uuid4().hex
    live_seq = 1
    start_event = build_live_audio_event("start", stream_id=stream_id, seq=live_seq)
    audio_chunk_payloads: list[str] = []
    pending_final_chunk_payload: str | None = None
    ttfa_s: float | None = None

    if mode == REQUEST_MODE_NON_STREAMING:
        try:
            response = httpx.post(
                endpoints.speech_url,
                json=payload,
                timeout=None,
            )
            response.raise_for_status()
            audio_path = write_audio_tempfile(response)
            elapsed = time.perf_counter() - t0
            LOGGER.debug("non-streaming response completed elapsed=%.3fs", elapsed)
            yield (
                gr.skip(),
                audio_path,
                status_markup(
                    f"Completed in {elapsed:.1f}s without live streaming.",
                    ok=True,
                ),
            )
        except Exception as exc:
            yield (
                gr.skip(),
                gr.skip(),
                status_markup(format_error("Speech generation failed", exc), ok=False),
            )
        return

    yield (
        json.dumps(start_event),
        gr.skip(),
        status_markup(
            "Connecting to streaming speech endpoint…"
            if mode == REQUEST_MODE_STREAMING
            else "Requesting speech with automatic streaming detection…",
            ok=True,
        ),
    )

    try:
        accept_header = "text/event-stream, application/octet-stream"
        if requested_stream_format == STREAM_FORMAT_SSE:
            accept_header = "text/event-stream"
        elif requested_stream_format == STREAM_FORMAT_AUDIO:
            accept_header = "application/octet-stream"

        with httpx.stream(
            "POST",
            endpoints.speech_url,
            json=payload,
            timeout=None,
            headers={"Accept": accept_header},
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            LOGGER.debug("streaming response content_type=%s", content_type or "<missing>")

            if content_type != "text/event-stream":
                if mode == REQUEST_MODE_STREAMING and requested_stream_format == STREAM_FORMAT_SSE:
                    raise RuntimeError(
                        "server returned raw audio instead of SSE live chunks; "
                        "use Auto or Non-streaming mode for this server"
                    )

                audio_bytes = bytearray()
                wav_header_buffer = bytearray()
                pcm_live_buffer = bytearray()
                live_chunk_count = 0
                live_chunk_status = "Streaming audio body…"
                live_event_history: list[dict[str, Any]] = [dict(start_event)]
                sample_rate = PCM_STREAM_SAMPLE_RATE
                sample_width = PCM_STREAM_SAMPLE_WIDTH
                num_channels = PCM_STREAM_CHANNELS
                block_align = max(sample_width * num_channels, 1)
                wav_header_parsed = content_type == "audio/pcm"
                supports_live_audio_body = content_type in {
                    "audio/wav",
                    "audio/x-wav",
                    "audio/pcm",
                }

                for body_chunk in response.iter_bytes(chunk_size=STREAM_AUDIO_BODY_CHUNK_BYTES):
                    if not body_chunk:
                        continue
                    audio_bytes.extend(body_chunk)

                    if not supports_live_audio_body:
                        continue

                    if content_type in {"audio/wav", "audio/x-wav"}:
                        if wav_header_parsed:
                            pcm_live_buffer.extend(body_chunk)
                        else:
                            wav_header_buffer.extend(body_chunk)
                            parsed_header = parse_wav_stream_header(bytes(wav_header_buffer))
                            if parsed_header is None:
                                continue
                            (
                                sample_rate,
                                sample_width,
                                num_channels,
                                block_align,
                                data_offset,
                            ) = parsed_header
                            LOGGER.debug(
                                "parsed wav stream header sample_rate=%s sample_width=%s channels=%s block_align=%s",
                                sample_rate,
                                sample_width,
                                num_channels,
                                block_align,
                            )
                            pcm_live_buffer.extend(wav_header_buffer[data_offset:])
                            wav_header_buffer.clear()
                            wav_header_parsed = True
                    else:
                        pcm_live_buffer.extend(body_chunk)

                    playable_chunk_size = max(
                        int(sample_rate * sample_width * num_channels * 0.20),
                        STREAM_AUDIO_BODY_CHUNK_BYTES,
                    )
                    playable_chunk_size -= playable_chunk_size % block_align
                    if playable_chunk_size <= 0:
                        playable_chunk_size = block_align

                    while len(pcm_live_buffer) >= playable_chunk_size:
                        emit_pcm = bytes(pcm_live_buffer[:playable_chunk_size])
                        del pcm_live_buffer[:playable_chunk_size]
                        wav_chunk = wav_bytes_from_pcm_frames(
                            emit_pcm,
                            sample_rate=sample_rate,
                            sample_width=sample_width,
                            num_channels=num_channels,
                        )
                        if ttfa_s is None:
                            ttfa_s = time.perf_counter() - t0
                        live_seq += 1
                        live_chunk_count += 1
                        live_event_history.append(
                            build_live_audio_event(
                                "audio.chunk",
                                stream_id=stream_id,
                                seq=live_seq,
                                data=base64.b64encode(wav_chunk).decode("ascii"),
                            )
                        )
                        yield (
                            make_live_audio_batch(live_event_history),
                            gr.skip(),
                            status_markup(live_chunk_status, ok=True),
                        )

                if not audio_bytes:
                    raise RuntimeError("server returned an empty audio response")

                elapsed = time.perf_counter() - t0
                suffix = audio_suffix_from_response(response)
                final_chunk_payload: str | None = None
                if supports_live_audio_body and len(pcm_live_buffer) >= block_align:
                    final_emit_len = len(pcm_live_buffer) - (len(pcm_live_buffer) % block_align)
                    if final_emit_len > 0:
                        final_wav_chunk = wav_bytes_from_pcm_frames(
                            bytes(pcm_live_buffer[:final_emit_len]),
                            sample_rate=sample_rate,
                            sample_width=sample_width,
                            num_channels=num_channels,
                        )
                        final_chunk_payload = base64.b64encode(final_wav_chunk).decode("ascii")

                if content_type == "audio/pcm":
                    final_pcm_len = len(audio_bytes) - (len(audio_bytes) % block_align)
                    audio_path = write_pcm_audio_tempfile(
                        bytes(audio_bytes[:final_pcm_len]),
                        sample_rate=sample_rate,
                        sample_width=sample_width,
                        num_channels=num_channels,
                    )
                else:
                    audio_path = write_audio_bytes_tempfile(bytes(audio_bytes), suffix=suffix)

                parts = [f"Completed in {elapsed:.1f}s"]
                if ttfa_s is not None:
                    parts.append(f"TTFA {ttfa_s:.2f}s")
                if live_chunk_count > 0:
                    parts.append("streaming audio body")
                else:
                    parts.append("audio body returned as a single chunk")
                live_seq += 1
                live_event_history.append(
                    build_live_audio_event(
                        "done",
                        stream_id=stream_id,
                        seq=live_seq,
                        final_chunk_data=final_chunk_payload,
                    )
                )
                LOGGER.debug(
                    "audio-body stream completed elapsed=%.3fs live_chunks=%s",
                    elapsed,
                    live_chunk_count,
                )
                yield (
                    make_live_audio_batch(live_event_history),
                    gr.skip(),
                    status_markup(" | ".join(parts), ok=True),
                )
                yield gr.skip(), audio_path, gr.skip()
                return

            if mode == REQUEST_MODE_STREAMING and requested_stream_format == STREAM_FORMAT_AUDIO:
                raise RuntimeError(
                    "server returned SSE events instead of a streaming audio body; "
                    "use Auto or select SSE for this server"
                )

            for raw_line in response.iter_lines():
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                data = raw_line[6:]
                if data == "[DONE]":
                    break
                event = json.loads(data)
                event_type = event.get("type")

                if event_type == "audio.chunk":
                    if ttfa_s is None:
                        ttfa_s = time.perf_counter() - t0
                    audio_chunk_payloads.append(event["data"])
                    segment_index = event.get("segment_index")
                    segment_count = event.get("segment_count")
                    if event.get("final"):
                        pending_final_chunk_payload = event["data"]
                        continue
                    live_seq += 1
                    status = "Streaming audio…"
                    if segment_index is not None and segment_count is not None:
                        status = f"Streaming audio… segment {segment_index + 1}/{segment_count}"
                    yield (
                        make_live_audio_event(
                            "audio.chunk",
                            stream_id=stream_id,
                            seq=live_seq,
                            data=event["data"],
                        ),
                        gr.skip(),
                        status_markup(status, ok=True),
                    )
                    continue

                if event_type == "done":
                    elapsed = time.perf_counter() - t0
                    audio_s = event.get("audio_s")
                    rtf = event.get("rtf")
                    parts = [f"Completed in {elapsed:.1f}s"]
                    if ttfa_s is not None:
                        parts.append(f"TTFA {ttfa_s:.2f}s")
                    if audio_s is not None:
                        parts.append(f"audio {audio_s:.1f}s")
                    if rtf is not None:
                        parts.append(f"rtf {rtf:.3f}")
                    live_seq += 1
                    LOGGER.debug(
                        "sse stream completed elapsed=%.3fs chunks=%s",
                        elapsed,
                        len(audio_chunk_payloads),
                    )
                    yield (
                        make_live_audio_event(
                            "done",
                            stream_id=stream_id,
                            seq=live_seq,
                            final_chunk_data=pending_final_chunk_payload,
                        ),
                        gr.skip(),
                        status_markup(" | ".join(parts), ok=True),
                    )
                    final_audio_path = concat_wav_chunks_to_file(
                        [base64.b64decode(chunk) for chunk in audio_chunk_payloads]
                    )
                    yield gr.skip(), final_audio_path, gr.skip()
                    return

                if event_type == "error":
                    raise RuntimeError(event.get("error", "unknown stream error"))
    except Exception as exc:
        live_seq += 1
        LOGGER.exception("speech generation failed")
        yield (
            make_live_audio_event(
                "error",
                stream_id=stream_id,
                seq=live_seq,
                error=str(exc),
            ),
            gr.skip(),
            status_markup(format_error("Speech generation failed", exc), ok=False),
        )
        return

    if audio_chunk_payloads:
        live_seq += 1
        yield (
            make_live_audio_event(
                "done",
                stream_id=stream_id,
                seq=live_seq,
                final_chunk_data=pending_final_chunk_payload,
            ),
            gr.skip(),
            status_markup("Streaming completed.", ok=True),
        )
        final_audio_path = concat_wav_chunks_to_file(
            [base64.b64decode(chunk) for chunk in audio_chunk_payloads]
        )
        yield gr.skip(), final_audio_path, gr.skip()
    else:
        yield (
            gr.skip(),
            gr.update(value=None),
            status_markup("No audio was returned by the server.", ok=False),
        )
