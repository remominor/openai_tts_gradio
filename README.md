# OpenAI TTS Gradio

Portable Gradio client for OpenAI-compatible text-to-speech servers.

This mini-project is self-contained. It does not import anything from the
parent repository and can be copied to another machine as-is.

## Features

- Accepts a server base URL like `http://10.50.0.51:8000/v1`
- Loads models from `/v1/audio/models` with fallback to `/v1/models`
- Loads stored voices from `/v1/audio/voices`
- Uploads new voices through `/upload_voice`
- Lets you preview a local voice file before upload
- Supports `Auto`, `Streaming`, and `Non-streaming` request modes
- Supports `Default`, `SSE`, and `Audio` stream format requests for `/v1/audio/speech`
- Streams playback from `/v1/audio/speech` over SSE or streaming WAV/PCM audio bodies when the server supports it
- Keeps the completed result in a Gradio `Audio` block for replay or download
- Uses readable light and dark mode styling

## Requirements

- Python 3.10+
- `gradio` 5.50+
- `httpx`

## Quick Start

From this directory:

```bash
pip install .
openai-tts-gradio --server-base-url http://10.50.0.51:8000/v1
```

Or run it without installing:

```bash
pip install gradio httpx
python openai_tts_gradio.py --server-base-url http://10.50.0.51:8000/v1
```

## CLI

```bash
python openai_tts_gradio.py \
  --server-base-url http://10.50.0.51:8000/v1 \
  --host 0.0.0.0 \
  --port 7860
```

Options:

- `--server-base-url`: server root or `/v1` base URL
- `--host`: Gradio bind host, default `0.0.0.0`
- `--port`: Gradio bind port, default `7860`
- `--share`: enable Gradio sharing

You can also set the default server URL with:

```bash
export OPENAI_TTS_SERVER_BASE_URL=http://10.50.0.51:8000/v1
```

## Supported Server Endpoints

- `GET /v1/audio/models`
- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /upload_voice`
- `POST /v1/audio/speech`

## Portability

To move this client elsewhere, copy the entire `openai_tts_gradio/` directory.
That directory contains:

- the application code
- install metadata
- usage documentation
