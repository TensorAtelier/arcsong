"""The worker process: owns the Engine (and the model) and renders one job at a time."""

from __future__ import annotations

import traceback
from functools import partial
from pathlib import Path
from typing import Any

from songloom.engine import Cancelled, EngineSpec
from songloom.progress import Coalescer

NO_JOB = -1


def _is_cancelled(cancel_job, job_id: int) -> bool:
    return cancel_job.value == job_id


def worker_main(spec: EngineSpec, jobs, events, cancel_job) -> None:
    """Run in a spawned process. `jobs` carries (job_id, request, out_dir) or None to stop;
    `events` carries dicts back to the server; `cancel_job.value` holds the id of the job to
    stop, so a late cancel for a finished job can never stop the next one."""
    engine = spec.build()
    engine.load()
    events.put({"type": "ready"})
    while (job := jobs.get()) is not None:
        job_id, request, out_dir = job

        def raw(event: dict[str, Any], job_id=job_id) -> None:
            events.put({**event, "job_id": job_id})

        emit = Coalescer(raw)
        emit({"type": "started"})
        try:
            cancelled = partial(_is_cancelled, cancel_job, job_id)
            take = engine.render(request, Path(out_dir), cancelled, emit)
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
