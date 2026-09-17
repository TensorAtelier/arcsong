"""The worker process: owns the Engine (and the model) and renders one job at a time."""

from __future__ import annotations

import os
import threading
import time
import traceback
from functools import partial
from pathlib import Path
from typing import Any

from songloom.engine import Cancelled, EngineSpec
from songloom.progress import Coalescer

NO_JOB = -1
PARENT_CHECK_SECONDS = 1.0


def _is_cancelled(cancel_job, job_id: int) -> bool:
    return cancel_job.value == job_id


def exit_with_parent(parent_pid: int) -> None:
    """If the server dies without stopping us (e.g. SIGKILL), exit rather than keep the model
    and the GPU lock. Runs in a daemon thread, so it also works mid-render."""
    while True:
        time.sleep(PARENT_CHECK_SECONDS)
        if os.getppid() != parent_pid:
            os._exit(0)


def worker_main(spec: EngineSpec, jobs, events, cancel_job, parent_pid: int | None = None) -> None:
    """Run in a spawned process. `jobs` carries a dict per job — `job_id`, `request`, `kind`
    ("take" or "score"), `out_dir` for a Take and `source_dir` for a Final — or None to stop.
    `events` carries dicts back to the server; `cancel_job.value` holds the id of the job to
    stop, so a late cancel for a finished job can never stop the next one."""
    if parent_pid is not None:
        threading.Thread(target=exit_with_parent, args=(parent_pid,), daemon=True).start()
    try:
        engine = spec.build()
        engine.load()
    except BaseException:
        events.put({"type": "load_failed", "error": traceback.format_exc()})
        return
    events.put({"type": "ready"})
    while (job := jobs.get()) is not None:
        job_id, request = job["job_id"], job["request"]

        def raw(event: dict[str, Any], job_id=job_id) -> None:
            events.put({**event, "job_id": job_id})

        emit = Coalescer(raw)
        emit({"type": "started"})
        try:
            cancelled = partial(_is_cancelled, cancel_job, job_id)
            if job["kind"] == "cover":
                score = engine.transcribe(
                    Path(job["source_audio"]), request, Path(job["out_dir"]), cancelled, emit
                )
                done = {"type": "done", "score": score.abc}
            elif job["kind"] == "score":
                done = {"type": "done", "score": engine.plan_only(request, cancelled, emit).abc}
            else:
                out_dir, source = Path(job["out_dir"]), job.get("source_dir")
                take = (
                    engine.finalize(Path(source), request, out_dir, cancelled, emit)
                    if source is not None
                    else engine.render(request, out_dir, cancelled, emit)
                )
                done = {
                    "type": "done",
                    "audio_path": str(take.audio_path),
                    "audio_seconds": take.audio_seconds,
                }
        except Cancelled:
            emit({"type": "cancelled"})
        except Exception:
            emit({"type": "failed", "error": traceback.format_exc()})
        else:
            emit(done)
