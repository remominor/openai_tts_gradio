from __future__ import annotations

import unittest
from unittest.mock import patch

from openai_tts_gradio_app.config import (
    REQUEST_MODE_AUTO,
    REQUEST_MODE_NON_STREAMING,
    STREAM_FORMAT_AUDIO,
    STREAM_FORMAT_DEFAULT,
    STREAM_FORMAT_SSE,
)
from openai_tts_gradio_app.util import browser_audio_enabled, generation_control_updates


class ControlStateTest(unittest.TestCase):
    def test_browser_audio_disabled_by_default(self) -> None:
        self.assertFalse(browser_audio_enabled(REQUEST_MODE_AUTO, STREAM_FORMAT_AUDIO))
        self.assertFalse(browser_audio_enabled(REQUEST_MODE_NON_STREAMING, STREAM_FORMAT_AUDIO))
        self.assertFalse(browser_audio_enabled(REQUEST_MODE_AUTO, STREAM_FORMAT_DEFAULT))

    def test_generation_control_updates_describes_server_audio_body_path_by_default(self) -> None:
        server_button, browser_button, route = generation_control_updates(
            REQUEST_MODE_AUTO,
            STREAM_FORMAT_AUDIO,
        )

        self.assertTrue(server_button["visible"])
        self.assertFalse(browser_button["visible"])
        self.assertIn("audio-body streaming through Gradio", route)

    def test_generation_control_updates_describes_sse_path(self) -> None:
        _server_button, _browser_button, route = generation_control_updates(
            REQUEST_MODE_AUTO,
            STREAM_FORMAT_SSE,
        )

        self.assertIn("SSE live streaming", route)

    def test_generation_control_updates_switch_buttons_for_browser_audio_when_enabled(self) -> None:
        with patch("openai_tts_gradio_app.util.ENABLE_BROWSER_AUDIO", True):
            server_button, browser_button, route = generation_control_updates(
                REQUEST_MODE_AUTO,
                STREAM_FORMAT_AUDIO,
            )

        self.assertFalse(server_button["visible"])
        self.assertTrue(browser_button["visible"])
        self.assertIn("browser audio-body streaming", route)
