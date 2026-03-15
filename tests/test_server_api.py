from __future__ import annotations

import unittest

from openai_tts_gradio_app.server_api import normalize_server_base_url


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
