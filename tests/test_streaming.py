from __future__ import annotations

import unittest
from unittest.mock import patch

import gradio as gr

from openai_tts_gradio_app.streaming import dispatch_server_generate_request


class StreamingDispatchTest(unittest.TestCase):
    def test_dispatch_server_generate_request_resets_outputs_before_streaming(self) -> None:
        with patch(
            "openai_tts_gradio_app.streaming.generate_speech",
            return_value=iter([("event-1", "audio-1", "status-1")]),
        ):
            outputs = list(
                dispatch_server_generate_request(
                    "http://localhost:8000/v1",
                    "gpt-4o-mini-tts",
                    "default",
                    "hello",
                    "streaming",
                    "sse",
                )
            )

        self.assertEqual(len(outputs), 2)
        self.assertIn('"type": "reset"', outputs[0][0])
        self.assertEqual(outputs[0][1], gr.update(value=None))
        self.assertIn("Streaming request started.", outputs[0][2])
        self.assertEqual(outputs[1], ("event-1", "audio-1", "status-1"))
