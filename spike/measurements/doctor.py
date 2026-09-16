"""`doctor`: the Engine loads and renders the `clip` case into a playable Take."""

from __future__ import annotations

import time
from pathlib import Path

from spike.engine import SpikeEngine, StageEvent

MEASUREMENT = "doctor"
CASE = "clip"


def measure(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    events: list[StageEvent] = []

    load_start = time.monotonic()
    engine.load(params["precision"])
    run_start = time.monotonic()
    output = engine.run(request, params["steps"], run_dir / "take", on_event=events.append)
    run_end = time.monotonic()

    return {
        "load_seconds": run_start - load_start,
        "run_seconds": run_end - run_start,
        "audio_path": str(output.audio_path),
        "audio_seconds": output.audio_seconds,
        "files": [{"path": str(p), "bytes": p.stat().st_size} for p in output.files],
        "stage_events": [
            {"stage": e.stage, "kind": e.kind, "seconds": e.t - run_start} for e in events
        ],
    }
