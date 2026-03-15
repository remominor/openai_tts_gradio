from __future__ import annotations

import pathlib
import unittest
import wave

from openai_tts_gradio_app.audio import (
    concat_wav_chunks_to_file,
    parse_wav_stream_header,
    read_wav_chunk,
    wav_bytes_from_pcm_frames,
)


class AudioHelpersTest(unittest.TestCase):
    def test_parse_wav_stream_header_detects_data_offset(self) -> None:
        wav_bytes = wav_bytes_from_pcm_frames(
            b"\x00\x01\x02\x03",
            sample_rate=24000,
            sample_width=2,
            num_channels=1,
        )

        parsed = parse_wav_stream_header(wav_bytes)

        self.assertEqual(parsed, (24000, 2, 1, 2, 44))

    def test_parse_wav_stream_header_returns_none_for_partial_prefix(self) -> None:
        wav_bytes = wav_bytes_from_pcm_frames(
            b"\x00\x01\x02\x03",
            sample_rate=24000,
            sample_width=2,
            num_channels=1,
        )

        self.assertIsNone(parse_wav_stream_header(wav_bytes[:20]))

    def test_concat_wav_chunks_to_file_combines_frames(self) -> None:
        chunk_a = wav_bytes_from_pcm_frames(
            b"\x00\x01\x02\x03",
            sample_rate=24000,
            sample_width=2,
            num_channels=1,
        )
        chunk_b = wav_bytes_from_pcm_frames(
            b"\x04\x05\x06\x07",
            sample_rate=24000,
            sample_width=2,
            num_channels=1,
        )

        output_path = concat_wav_chunks_to_file([chunk_a, chunk_b])
        self.assertIsNotNone(output_path)
        assert output_path is not None

        try:
            path = pathlib.Path(output_path)
            self.assertTrue(path.exists())
            with wave.open(str(path), "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 24000)
                self.assertEqual(wav_file.getsampwidth(), 2)
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertEqual(wav_file.readframes(wav_file.getnframes()), b"\x00\x01\x02\x03\x04\x05\x06\x07")
        finally:
            pathlib.Path(output_path).unlink(missing_ok=True)

    def test_concat_wav_chunks_to_file_rejects_mismatched_format(self) -> None:
        chunk_a = wav_bytes_from_pcm_frames(
            b"\x00\x01",
            sample_rate=24000,
            sample_width=2,
            num_channels=1,
        )
        chunk_b = wav_bytes_from_pcm_frames(
            b"\x00\x01",
            sample_rate=16000,
            sample_width=2,
            num_channels=1,
        )

        with self.assertRaisesRegex(RuntimeError, "format mismatch"):
            concat_wav_chunks_to_file([chunk_a, chunk_b])

    def test_read_wav_chunk_returns_pcm_frames(self) -> None:
        wav_bytes = wav_bytes_from_pcm_frames(
            b"\x01\x02\x03\x04",
            sample_rate=22050,
            sample_width=2,
            num_channels=1,
        )

        self.assertEqual(read_wav_chunk(wav_bytes), (22050, 2, 1, b"\x01\x02\x03\x04"))
