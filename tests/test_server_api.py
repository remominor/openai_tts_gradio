from __future__ import annotations

import unittest
from unittest.mock import patch

from openai_tts_gradio_app.server_api import fetch_voices, normalize_server_base_url


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class ServerApiTest(unittest.TestCase):
    def test_normalize_server_base_url_accepts_root_url(self) -> None:
        endpoints = normalize_server_base_url("http://localhost:8000")

        self.assertEqual(endpoints.root_base, "http://localhost:8000")
        self.assertEqual(endpoints.v1_base, "http://localhost:8000/v1")
        self.assertEqual(endpoints.speech_url, "http://localhost:8000/v1/audio/speech")

    def test_normalize_server_base_url_accepts_v1_url(self) -> None:
        endpoints = normalize_server_base_url("http://localhost:8000/v1/")

        self.assertEqual(endpoints.root_base, "http://localhost:8000")
        self.assertEqual(endpoints.v1_base, "http://localhost:8000/v1")
        self.assertEqual(endpoints.upload_url, "http://localhost:8000/upload_voice")

    def test_normalize_server_base_url_requires_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "required"):
            normalize_server_base_url("   ")

    @patch("openai_tts_gradio_app.server_api.httpx.get")
    def test_fetch_voices_prefers_data_objects_over_voice_id_strings(self, mock_get) -> None:
        mock_get.return_value = _FakeResponse(
            {
                "object": "list",
                "data": [
                    {
                        "id": "voice-a",
                        "name": "voice-a",
                        "voice_id": "voice-a",
                    },
                    {
                        "id": "voice-b",
                        "name": "voice-b",
                        "voice_id": "voice-b",
                    },
                ],
                "voices": ["voice-a", "voice-b"],
            }
        )

        voices, voice_dir = fetch_voices(normalize_server_base_url("http://localhost:10087/v1"))

        self.assertEqual([voice["id"] for voice in voices], ["voice-a", "voice-b"])
        self.assertEqual([voice["label"] for voice in voices], ["voice-a", "voice-b"])
        self.assertEqual(voice_dir, "")

    @patch("openai_tts_gradio_app.server_api.httpx.get")
    def test_fetch_voices_falls_back_to_voice_id_strings(self, mock_get) -> None:
        mock_get.return_value = _FakeResponse(
            {
                "voices": ["voice-a", "voice-b"],
            }
        )

        voices, voice_dir = fetch_voices(normalize_server_base_url("http://localhost:10087/v1"))

        self.assertEqual([voice["id"] for voice in voices], ["voice-a", "voice-b"])
        self.assertEqual([voice["label"] for voice in voices], ["voice-a", "voice-b"])
        self.assertEqual(voice_dir, "")
