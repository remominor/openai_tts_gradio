from __future__ import annotations

import json
import time
from typing import Any


def build_live_audio_event(
    event_type: str,
    *,
    stream_id: str | None = None,
    seq: int | None = None,
    **payload: Any,
) -> dict[str, Any]:
    event: dict[str, Any] = {"type": event_type}
    if stream_id is not None:
        event["stream_id"] = stream_id
    if seq is not None:
        event["seq"] = seq
    event.update(payload)
    return event


def make_live_audio_event(
    event_type: str,
    *,
    stream_id: str | None = None,
    seq: int | None = None,
    **payload: Any,
) -> str:
    return json.dumps(
        build_live_audio_event(
            event_type,
            stream_id=stream_id,
            seq=seq,
            **payload,
        )
    )


def make_live_audio_batch(events: list[dict[str, Any]]) -> str:
    return json.dumps({"type": "batch", "events": events})


def reset_live_audio_event() -> str:
    return make_live_audio_event("reset", ts=time.time())
