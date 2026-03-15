#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compatibility entry point for the OpenAI TTS Gradio app."""

from openai_tts_gradio_app import create_demo, main

__all__ = ["create_demo", "main"]


if __name__ == "__main__":
    main()
