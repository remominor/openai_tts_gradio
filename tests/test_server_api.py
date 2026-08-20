from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openai_tts_gradio_app.server_api import (
    delete_voice,
    fetch_voices,
    load_server_history,
    normalize_server_base_url,
    remember_server_url,
    update_voice,
)


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

    def test_server_history_persists_recent_urls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "servers.json"
            with patch("openai_tts_gradio_app.server_api.SERVER_HISTORY_PATH", history_path):
                remember_server_url("http://tts-two:8000/v1/")
                remember_server_url("http://tts-one:8000/v1")

                self.assertEqual(
                    load_server_history("http://tts-one:8000/v1"),
                    [
                        "http://tts-one:8000/v1",
                        "http://tts-two:8000/v1",
                    ],
                )

    @patch("openai_tts_gradio_app.server_api.httpx.get")
    @patch("openai_tts_gradio_app.server_api.httpx.patch")
    def test_update_voice_sends_metadata_and_refreshes_choices(self, mock_patch, mock_get) -> None:
        mock_patch.return_value = _FakeResponse(
            {"id": "renamed", "voice_id": "voice-a", "name": "renamed", "ref_text": "updated"}
        )
        mock_get.return_value = _FakeResponse(
            {"data": [{"id": "renamed", "name": "renamed", "voice_id": "voice-a"}]}
        )

        dropdown, name, ref_text, _status, selected = update_voice(
            "http://localhost:8000/v1", "voice-a", "renamed", "updated"
        )

        mock_patch.assert_called_once_with(
            "http://localhost:8000/v1/audio/voices/voice-a",
            json={"name": "renamed", "ref_text": "updated"},
            timeout=15.0,
        )
        self.assertEqual(dropdown["value"], "renamed")
        self.assertEqual(name, "renamed")
        self.assertEqual(ref_text, "updated")
        self.assertEqual(selected, "renamed")

    @patch("openai_tts_gradio_app.server_api.httpx.get")
    @patch("openai_tts_gradio_app.server_api.httpx.delete")
    def test_delete_voice_refreshes_choices_and_selects_default(self, mock_delete, mock_get) -> None:
        mock_delete.return_value = _FakeResponse({"deleted": True})
        mock_get.return_value = _FakeResponse({"data": []})

        dropdown, name, ref_text, _status, selected = delete_voice(
            "http://localhost:8000/v1", "voice-a"
        )

        mock_delete.assert_called_once_with(
            "http://localhost:8000/v1/audio/voices/voice-a", timeout=15.0
        )
        self.assertEqual(dropdown["value"], "default")
        self.assertEqual(name, "")
        self.assertEqual(ref_text, "")
        self.assertEqual(selected, "default")

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
