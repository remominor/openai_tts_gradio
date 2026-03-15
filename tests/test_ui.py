from __future__ import annotations

import unittest
from unittest.mock import patch

import gradio as gr

from openai_tts_gradio_app.ui import create_demo, refresh_server_data


class UiTest(unittest.TestCase):
    def test_create_demo_allows_custom_model_and_voice_values(self) -> None:
        demo = create_demo("http://localhost:10087/v1")

        dropdowns = {
            block.label: block
            for block in demo.blocks.values()
            if isinstance(block, gr.Dropdown)
        }

        self.assertTrue(dropdowns["Model"].allow_custom_value)
        self.assertTrue(dropdowns["Voice"].allow_custom_value)

    @patch("openai_tts_gradio_app.ui.fetch_voices")
    @patch("openai_tts_gradio_app.ui.fetch_models")
    def test_refresh_server_data_preserves_custom_model_and_voice_values(
        self,
        mock_fetch_models,
        mock_fetch_voices,
    ) -> None:
        mock_fetch_models.return_value = ["listed-model"]
        mock_fetch_voices.return_value = ([{"id": "listed-voice", "label": "listed-voice"}], "")

        model_update, voice_update, _status, model_value, voice_value = refresh_server_data(
            "http://localhost:10087/v1",
            "typed-model",
            "typed-voice",
        )

        self.assertEqual(model_update["choices"], ["listed-model", "typed-model"])
        self.assertEqual(model_update["value"], "typed-model")
        self.assertEqual(
            voice_update["choices"],
            [
                ("default", "default"),
                ("listed-voice", "listed-voice"),
                ("typed-voice", "typed-voice"),
            ],
        )
        self.assertEqual(voice_update["value"], "typed-voice")
        self.assertEqual(model_value, "typed-model")
        self.assertEqual(voice_value, "typed-voice")

