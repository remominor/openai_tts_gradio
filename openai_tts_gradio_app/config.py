from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import gradio as gr

DEFAULT_SERVER_BASE_URL = os.environ.get(
    "OPENAI_TTS_SERVER_BASE_URL",
    "http://localhost:8000/v1",
)
DEFAULT_REQUEST_TIMEOUT = 15.0
REQUEST_MODE_AUTO = "auto"
REQUEST_MODE_STREAMING = "streaming"
REQUEST_MODE_NON_STREAMING = "non-streaming"
STREAM_FORMAT_DEFAULT = "default"
STREAM_FORMAT_SSE = "sse"
STREAM_FORMAT_AUDIO = "audio"
STREAM_AUDIO_BODY_CHUNK_BYTES = 4096
PCM_STREAM_SAMPLE_RATE = 24000
PCM_STREAM_SAMPLE_WIDTH = 2
PCM_STREAM_CHANNELS = 1
LOG_LEVEL_ENV_VAR = "OPENAI_TTS_GRADIO_LOG_LEVEL"
BROWSER_DEBUG_STORAGE_KEY = "openai-tts-debug"

CONTENT_TYPE_SUFFIXES = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/opus": ".opus",
    "audio/pcm": ".pcm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}

CUSTOM_CSS = """
:root {
  --panel-bg: linear-gradient(180deg, #f7f1e7 0%, #efe7d8 100%);
  --card-bg: rgba(255, 252, 246, 0.9);
  --surface-bg: rgba(255, 255, 255, 0.78);
  --ink: #1d2730;
  --muted: #5f6c72;
  --accent: #c35f2d;
  --accent-2: #254c63;
  --line: rgba(37, 76, 99, 0.14);
  --shadow: 0 18px 60px rgba(29, 39, 48, 0.08);
}

body.dark,
.dark,
.gradio-container.dark {
  --panel-bg:
    radial-gradient(circle at top left, rgba(195, 95, 45, 0.16), transparent 28%),
    radial-gradient(circle at top right, rgba(114, 170, 204, 0.14), transparent 24%),
    linear-gradient(180deg, #11161c 0%, #171f27 100%);
  --card-bg: rgba(25, 32, 41, 0.92);
  --surface-bg: rgba(20, 27, 35, 0.88);
  --ink: #edf2f7;
  --muted: #b8c2cc;
  --accent: #ef8b49;
  --accent-2: #7bb5d9;
  --line: rgba(123, 181, 217, 0.18);
  --shadow: 0 24px 70px rgba(0, 0, 0, 0.32);
}

.gradio-container {
  background: var(--panel-bg);
  color: var(--ink);
  font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
}

.app-shell {
  max-width: 980px;
  margin: 0 auto;
}

.app-hero {
  border: 1px solid var(--line);
  background: var(--card-bg);
  border-radius: 24px;
  padding: 22px 24px 18px 24px;
  box-shadow: var(--shadow);
  color: var(--ink);
}

.app-hero h1,
.app-hero h2,
.app-hero h3,
.app-hero p,
.status-box p,
.upload-box p {
  margin: 0;
}

.app-hero h1 {
  letter-spacing: -0.03em;
  font-size: 2.2rem;
  margin-bottom: 8px;
}

.app-hero p {
  color: var(--muted);
  line-height: 1.45;
}

.status-box,
.upload-box {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--surface-bg);
  padding: 12px 14px;
  color: var(--ink);
}

.status-ok {
  color: #215840;
}

.status-warn {
  color: #8f3d1d;
}

.primary-action button {
  background: linear-gradient(135deg, var(--accent), #de7b3d) !important;
  border: none !important;
}

body.dark .status-ok,
.dark .status-ok,
.gradio-container.dark .status-ok {
  color: #7fe0a4;
}

body.dark .status-warn,
.dark .status-warn,
.gradio-container.dark .status-warn {
  color: #ffb48d;
}

.gradio-container code {
  background: rgba(0, 0, 0, 0.08);
  color: var(--ink);
  padding: 0.12rem 0.32rem;
  border-radius: 0.35rem;
}

.dom-hidden-control {
  display: none !important;
}

body.dark .gradio-container code,
.dark .gradio-container code,
.gradio-container.dark code {
  background: rgba(255, 255, 255, 0.08);
}
"""

APP_THEME = gr.themes.Soft(
    primary_hue="amber",
    secondary_hue="slate",
    neutral_hue="stone",
)

LOGGER = logging.getLogger("openai_tts_gradio")


@dataclass(frozen=True)
class APIEndpoints:
    root_base: str
    v1_base: str
    models_url: str
    models_fallback_url: str
    speech_url: str
    voices_url: str
    upload_url: str


def configure_logging() -> None:
    level_name = os.environ.get(LOG_LEVEL_ENV_VAR, "WARNING").strip().upper() or "WARNING"
    level = getattr(logging, level_name, logging.WARNING)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    logging.getLogger().setLevel(level)
    LOGGER.setLevel(level)
