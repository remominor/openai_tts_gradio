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
- Supports optional voice-design/direction instructions and per-generation CFG scale overrides
- Streams playback from `/v1/audio/speech` over SSE or streaming WAV/PCM audio bodies when the server supports it
- Uses the Gradio/server audio-body path by default for `Audio` streaming so it works with servers that do not support SSE or browser cross-origin fetches
- Keeps browser-direct audio-body streaming available as an explicit opt-in for CORS-capable servers
- Keeps the completed result in a Gradio `Audio` block for replay or download
- Uses readable light and dark mode styling
- Keeps up to 20 recently used server URLs in persistent JSON storage

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

If you want to use the browser-direct audio-body path instead of the default
Gradio/server path:

```bash
OPENAI_TTS_GRADIO_ENABLE_BROWSER_AUDIO=1 \
python openai_tts_gradio.py --server-base-url http://10.50.0.51:8000/v1
```

The default server URL can be configured with either
`--server-base-url` or `OPENAI_TTS_SERVER_BASE_URL`. The UI presents recent
servers in a selectable dropdown while still allowing a new URL to be typed.

## Docker / Unraid

The container runs only this UI; your OpenAI-compatible TTS server remains a
separate service. Recent server URLs are stored in `/app/voices/servers.json`.
The included Compose configuration maps `./voices` to that path so the history
survives container recreation.

The published image is available at
`ghcr.io/remominor/openai_tts_gradio:latest`:

```bash
docker pull ghcr.io/remominor/openai_tts_gradio:latest
docker run --rm -p 7860:7860 \
  -e OPENAI_TTS_SERVER_BASE_URL=http://<tts-server-lan-ip>:8000/v1 \
  ghcr.io/remominor/openai_tts_gradio:latest
```

Every push to `main` refreshes the `latest` image. Version tags also publish
version and commit-SHA tags.

1. Copy this project to your Unraid server (for example,
   `/mnt/user/appdata/openai-tts-gradio`).
2. In `compose.yaml`, replace `192.168.1.50:8000` with the LAN IP and port of
   your TTS server. Do not use `localhost` unless that server runs inside this
   same container.
3. In Unraid's Compose Manager, add a stack using that directory and deploy it.
   Alternatively, from that directory run `docker compose up -d --build`.
4. Open `http://<unraid-host>:7860`.

To deploy from the Unraid Docker tab without Compose, first build the image
from the project directory:

```bash
docker build -t openai-tts-gradio:latest .
```

Then create a container with these settings:

- Repository: `openai-tts-gradio:latest`
- Network type: `bridge`
- Port mapping: host `7860` to container `7860` (TCP)
- Environment variable: `OPENAI_TTS_SERVER_BASE_URL` =
  `http://<tts-server-lan-ip>:8000/v1`
- Restart policy: `unless-stopped`

The image runs as an unprivileged user and exposes a Docker health check. For
an Unraid system with a reverse proxy, point the proxy at port `7860`; ensure
the proxy allows WebSocket upgrades for Gradio's queue.

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

Useful environment variables:

- `OPENAI_TTS_SERVER_BASE_URL`: default backend URL used at startup
- `OPENAI_TTS_GRADIO_ENABLE_BROWSER_AUDIO=1`: opt in to browser-direct audio-body streaming
- `OPENAI_TTS_GRADIO_LOG_LEVEL=DEBUG`: enable verbose client logging

## Streaming Paths

The UI exposes two separate controls:

- `Request Mode`: `Auto`, `Streaming`, or `Non-streaming`
- `Stream Format`: `Default`, `SSE`, or `Audio`

How they behave:

- `Non-streaming` waits for the completed response and then loads the final audio into the player.
- `Streaming` starts playback as soon as the backend begins returning stream data.
- `Auto` uses the streaming-capable server path and lets the app infer the response type from the returned headers.

Stream format details:

- `Default` is the safest first choice when you are not sure what the backend supports.
- `SSE` is only appropriate for servers that return `text/event-stream` from `/v1/audio/speech`.
- `Audio` requests streaming audio data such as WAV or PCM. This now uses the server-side Gradio path by default, which is the more compatible option for backends that do not support SSE or do not allow browser cross-origin requests.

Browser-direct audio mode:

- The browser-direct `Audio` path is disabled by default.
- Enable it with `OPENAI_TTS_GRADIO_ENABLE_BROWSER_AUDIO=1`.
- Use it only when the TTS server is reachable directly from the browser and its CORS policy allows that request.
- If explicit `Audio` works in `Default` mode but fails when browser-direct mode is enabled, the usual cause is CORS or another browser-side network restriction rather than TTS generation itself.

Recommended choices:

- If a server does not support SSE, use `Stream Format = Audio` or `Default`.
- If a server streams audio bodies correctly but browser fetches fail, keep browser-direct audio disabled and use the default Gradio/server path.
- If you need to validate SSE specifically, select `Stream Format = SSE`; failures there usually indicate the backend is returning audio bytes instead of SSE events.

## Supported Server Endpoints

- `GET /v1/audio/models`
- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /upload_voice`
- `POST /v1/audio/speech`

## Troubleshooting

- If the UI seems stuck on a streaming request, restart the TTS backend first. A hung backend queue can look like a client regression.
- If `SSE` fails but `Audio` works, the backend likely does not implement SSE for `/v1/audio/speech`.
- If `Audio` only fails when browser-direct mode is enabled, disable `OPENAI_TTS_GRADIO_ENABLE_BROWSER_AUDIO` and retry through the default Gradio/server path.
- For server-side debug logs, start the app with `OPENAI_TTS_GRADIO_LOG_LEVEL=DEBUG`.

## Portability

To move this client elsewhere, copy the entire `openai_tts_gradio/` directory.
That directory contains:

- the application code
- install metadata
- usage documentation
