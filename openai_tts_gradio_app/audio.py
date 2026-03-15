from __future__ import annotations

import io
import re
import struct
import tempfile
import wave

import httpx

from .config import CONTENT_TYPE_SUFFIXES


def audio_suffix_from_response(response: httpx.Response) -> str:
    content_disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename="[^"]+(\.[A-Za-z0-9]+)"', content_disposition)
    if match:
        return match.group(1)

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type in CONTENT_TYPE_SUFFIXES:
        return CONTENT_TYPE_SUFFIXES[content_type]
    return ".wav"


def write_audio_tempfile(response: httpx.Response) -> str:
    suffix = audio_suffix_from_response(response)
    return write_audio_bytes_tempfile(response.content, suffix=suffix)


def write_audio_bytes_tempfile(audio_bytes: bytes, *, suffix: str = ".wav") -> str:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        handle.write(audio_bytes)
        return handle.name
    finally:
        handle.close()


def wav_bytes_from_pcm_frames(
    frames: bytes,
    *,
    sample_rate: int,
    sample_width: int,
    num_channels: int,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return buffer.getvalue()


def write_pcm_audio_tempfile(
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    sample_width: int,
    num_channels: int,
) -> str:
    audio_bytes = wav_bytes_from_pcm_frames(
        pcm_bytes,
        sample_rate=sample_rate,
        sample_width=sample_width,
        num_channels=num_channels,
    )
    return write_audio_bytes_tempfile(audio_bytes, suffix=".wav")


def parse_wav_stream_header(
    wav_prefix: bytes,
) -> tuple[int, int, int, int, int] | None:
    if len(wav_prefix) < 12:
        return None
    if wav_prefix[:4] not in {b"RIFF", b"RF64"} or wav_prefix[8:12] != b"WAVE":
        raise RuntimeError("Streaming audio body is not a WAV file")

    pos = 12
    fmt_chunk: tuple[int, int, int, int] | None = None
    while pos + 8 <= len(wav_prefix):
        chunk_id = wav_prefix[pos : pos + 4]
        chunk_size = struct.unpack("<I", wav_prefix[pos + 4 : pos + 8])[0]
        chunk_start = pos + 8

        if chunk_id == b"fmt ":
            if len(wav_prefix) < chunk_start + 16:
                return None
            (
                audio_format,
                num_channels,
                sample_rate,
                _byte_rate,
                block_align,
                bits_per_sample,
            ) = struct.unpack("<HHIIHH", wav_prefix[chunk_start : chunk_start + 16])
            if audio_format != 1:
                raise RuntimeError("Only PCM WAV streaming is supported")
            sample_width = bits_per_sample // 8
            fmt_chunk = (
                sample_rate,
                sample_width,
                num_channels,
                block_align,
            )
        elif chunk_id == b"data":
            if fmt_chunk is None:
                raise RuntimeError("Invalid WAV stream: missing fmt chunk before data")
            sample_rate, sample_width, num_channels, block_align = fmt_chunk
            return (
                sample_rate,
                sample_width,
                num_channels,
                block_align,
                chunk_start,
            )

        padded_chunk_size = chunk_size + (chunk_size % 2)
        next_pos = chunk_start + padded_chunk_size
        if len(wav_prefix) < next_pos:
            return None
        pos = next_pos

    return None


def read_wav_chunk(audio_bytes: bytes) -> tuple[int, int, int, bytes]:
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        num_channels = wav_file.getnchannels()
        raw_frames = wav_file.readframes(wav_file.getnframes())
    return sample_rate, sample_width, num_channels, raw_frames


def concat_wav_chunks_to_file(audio_chunks: list[bytes]) -> str | None:
    if not audio_chunks:
        return None

    sample_rate: int | None = None
    sample_width: int | None = None
    num_channels: int | None = None
    pcm_frames = bytearray()

    for audio_bytes in audio_chunks:
        chunk_sample_rate, chunk_sample_width, chunk_num_channels, chunk_frames = read_wav_chunk(
            audio_bytes
        )
        if sample_rate is None:
            sample_rate = chunk_sample_rate
            sample_width = chunk_sample_width
            num_channels = chunk_num_channels
        elif (
            sample_rate != chunk_sample_rate
            or sample_width != chunk_sample_width
            or num_channels != chunk_num_channels
        ):
            raise RuntimeError("Streaming chunk audio format mismatch")
        pcm_frames.extend(chunk_frames)

    if sample_rate is None or sample_width is None or num_channels is None:
        return None

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    try:
        with wave.open(handle, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(pcm_frames))
        return handle.name
    finally:
        handle.close()
