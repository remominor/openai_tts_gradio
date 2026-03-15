from __future__ import annotations

import argparse

from .config import DEFAULT_SERVER_BASE_URL, configure_logging
from .ui import create_demo, launch_kwargs


def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Portable Gradio UI for OpenAI-compatible TTS servers",
        epilog="Dependencies: pip install gradio httpx",
    )
    parser.add_argument(
        "--server-base-url",
        type=str,
        default=DEFAULT_SERVER_BASE_URL,
        help="Server root or /v1 base URL, for example http://10.50.0.51:8000/v1",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    demo = create_demo(args.server_base_url)
    demo.queue()
    demo.launch(**launch_kwargs(demo, host=args.host, port=args.port, share=args.share))
