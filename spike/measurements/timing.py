"""`timing`: per-Stage time, load time, memory and artifact sizes for `song`.

Decisions: D-008 (method), D-009 (matrix), D-014 (artifact sizes).

The runner executes each run in a fresh child and adds the peak physical footprint it
sampled from outside; this module measures everything seen from inside the child.
"""

from __future__ import annotations

import time
from pathlib import Path

from spike.engine import STAGES, SpikeEngine, StageEvent

MEASUREMENT = "timing"
CASE = "song"
STEPS = (8, 32)
RUNS = 2
PRECISIONS = {"mlx": ("bf16", "8bit"), "fake": ("bf16", "8bit")}


def stage_seconds(events: list[StageEvent]) -> dict[str, float]:
    """Wall time per Stage: the sum of every start→end span of that Stage."""
    totals = {stage: 0.0 for stage in STAGES}
    open_since: dict[str, float] = {}
    for event in events:
        if event.kind == "start":
            open_since[event.stage] = event.t
        elif event.stage in open_since:
            span = event.t - open_since.pop(event.stage)
            totals[event.stage] = totals.get(event.stage, 0.0) + span
    return totals


def artifact_sizes(take_dir: Path) -> list[dict]:
    """Every file the Take wrote, relative to its directory, with its size."""
    return [
        {"path": str(path.relative_to(take_dir)), "bytes": path.stat().st_size}
        for path in sorted(take_dir.rglob("*"))
        if path.is_file()
    ]


def measure(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    events: list[StageEvent] = []
    take_dir = run_dir / "take"

    load_start = time.monotonic()
    engine.load(params["precision"])
    run_start = time.monotonic()
    output = engine.run(request, params["steps"], take_dir, on_event=events.append)
    run_end = time.monotonic()

    load_seconds = run_start - load_start
    run_seconds = run_end - run_start
    files = artifact_sizes(take_dir)
    return {
        "load_seconds": load_seconds,
        "lazy_load_seconds": output.lazy_load_seconds,
        "model_load_seconds": load_seconds + sum(output.lazy_load_seconds.values()),
        "stage_seconds": stage_seconds(events),
        "run_seconds": run_seconds,
        "total_seconds": run_end - load_start,
        "engine_peak_memory_bytes": output.engine_peak_memory_bytes,
        "audio_seconds": output.audio_seconds,
        "audio_path": str(output.audio_path),
        "audio_bytes": output.audio_path.stat().st_size,
        "take_dir": str(take_dir),
        "files": files,
        "files_total_bytes": sum(f["bytes"] for f in files),
        "stage_events": [
            {"stage": e.stage, "kind": e.kind, "seconds": e.t - run_start} for e in events
        ],
    }
