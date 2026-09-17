"""The worker process: owns the Engine (and the model) and renders one job at a time."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from songloom.engine import Cancelled, EngineSpec


def worker_main(spec: EngineSpec, jobs, events, cancel) -> None:
    """Run in a spawned process. `jobs` carries (job_id, request, out_dir) or None to stop;
    `events` carries dicts back to the server; `cancel` is set to stop the running job."""
    engine = spec.build()
    engine.load()
    events.put({"type": "ready"})
    while (job := jobs.get()) is not None:
        job_id, request, out_dir = job
        cancel.clear()

        def emit(event: dict[str, Any], job_id=job_id) -> None:
            events.put({**event, "job_id": job_id})

        emit({"type": "started"})
        try:
            take = engine.render(request, Path(out_dir), cancel.is_set, emit)
        except Cancelled:
            emit({"type": "cancelled"})
        except Exception:
            emit({"type": "failed", "error": traceback.format_exc()})
        else:
            emit(
                {
                    "type": "done",
                    "audio_path": str(take.audio_path),
                    "audio_seconds": take.audio_seconds,
                }
            )
