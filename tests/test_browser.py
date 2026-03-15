from __future__ import annotations

import unittest

from openai_tts_gradio_app.browser import live_player_head


class BrowserBridgeTest(unittest.TestCase):
    def test_live_player_head_keeps_browser_audio_separate_from_native_audio(self) -> None:
        script = live_player_head()

        self.assertIn('const browserAudio = root.querySelector("[data-openai-tts-browser-player=\'1\']");', script)
        self.assertIn('const nativeAudio = root.querySelector("audio:not([data-openai-tts-browser-player=\'1\'])");', script)
        self.assertNotIn('root.querySelector("[data-openai-tts-browser-player=\'1\']") || root.querySelector("audio")', script)

