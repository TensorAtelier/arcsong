"""The job runner inside the server: feeds queued jobs to the worker one at a time, turns the
worker's events into database updates and live progress, broadcasts job changes, and replaces
the worker process when it dies."""

from __future__ import annotations

import multiprocessing as mp
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from songloom.db import Store
from songloom.engine import EngineSpec
from songloom.worker import NO_JOB, worker_main

# A running job that has not stopped this long after a cancel request gets its worker killed.
# (M0: mlx-Yue honoured cancel within 0.13 s in every Stage.)
CANCEL_GRACE_SECONDS = 10.0


class Broadcaster:
    """Fans job snapshots out to any number of subscribers (one per SSE connection)."""

    def __init__(self):
        self._subscribers: set[queue.SimpleQueue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.SimpleQueue:
        q: queue.SimpleQueue = queue.SimpleQueue()
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.SimpleQueue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, message: dict[str, Any]) -> None:
        with self._lock:
            for q in self._subscribers:
                q.put(message)


class JobRunner:
    def __init__(
        self,
        store: Store,
        songs_dir: Path,
        spec: EngineSpec,
        cancel_grace: float = CANCEL_GRACE_SECONDS,
    ):
        self.store = store
        self.songs_dir = songs_dir
        self.spec = spec
        self.cancel_grace = cancel_grace
        self.broadcaster = Broadcaster()
        self._ctx = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._running: int | None = None
        self._live: dict[str, Any] = {}
        self._cancel_asked_at: float | None = None
        self._stopping = threading.Event()
        self.worker_starts = 0

    # --- lifecycle -------------------------------------------------------------------------

    def start(self) -> None:
        for job_id in self.store.recover():
            self._discard_partial_take(job_id)
        self._start_worker()
        self._thread = threading.Thread(target=self._pump, name="songloom-events", daemon=True)
        self._thread.start()
        self.dispatch()

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            if self._running is not None:
                self._cancel.value = self._running
            self._jobs.put(None)
            process = self._process
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
        self._thread.join(timeout=2)

    def _start_worker(self) -> None:
        with self._lock:
            self._jobs = self._ctx.Queue()
            self._events = self._ctx.Queue()
            self._cancel = self._ctx.Value("q", NO_JOB)
            self._process = self._ctx.Process(
                target=worker_main,
                args=(self.spec, self._jobs, self._events, self._cancel),
                daemon=True,
            )
            self._process.start()
            self.worker_starts += 1

    def _replace_worker(self, outcome: str, error: str | None) -> None:
        """The worker died or had to be killed: close out its job and start a fresh worker."""
        with self._lock:
            process, job_id = self._process, self._running
            if process.is_alive():
                process.kill()
            process.join()
            if job_id is not None:
                self.store.mark_finished(job_id, outcome, error)
                self._discard_partial_take(job_id)
                self._running, self._live, self._cancel_asked_at = None, {}, None
            self._start_worker()
        if job_id is not None:
            self.publish(job_id)
        self.dispatch()

    # --- jobs ------------------------------------------------------------------------------

    def job(self, job_id: int) -> dict[str, Any] | None:
        """A job from the database, with live progress while it runs."""
        job = self.store.get_job(job_id)
        if job is not None:
            with self._lock:
                job["live"] = dict(self._live) if job_id == self._running else None
        return job

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            running, live = self._running, dict(self._live)
        return [{**j, "live": live if j["id"] == running else None} for j in self.store.list_jobs()]

    def dispatch(self) -> None:
        """Send the oldest queued job to the worker if it is idle."""
        with self._lock:
            if self._running is not None or self._stopping.is_set():
                return
            job = self.store.next_queued()
            if job is None:
                return
            self._running, self._live = job["id"], {"stage": None}
            self.store.mark_running(job["id"])
            self._jobs.put((job["id"], job["request"], str(self.songs_dir / str(job["id"]))))
        self.publish(job["id"])

    def cancel(self, job_id: int) -> bool:
        """Cancel a queued or running job; False if it has already finished (or never existed)."""
        with self._lock:
            job = self.store.get_job(job_id)
            if job is None or job["status"] not in ("queued", "running"):
                return False
            if job["status"] == "queued":
                self.store.mark_finished(job_id, "cancelled")
            else:
                self._cancel.value = job_id
                self._cancel_asked_at = self._cancel_asked_at or time.monotonic()
        self.publish(job_id)
        return True

    def publish(self, job_id: int) -> None:
        job = self.job(job_id)
        if job is not None:
            self.broadcaster.publish({"type": "job", "job": job})

    # --- worker events ---------------------------------------------------------------------

    def _pump(self) -> None:
        while not self._stopping.is_set():
            with self._lock:
                events, process = self._events, self._process
            try:
                event = events.get(timeout=0.2)
            except queue.Empty:
                self._watch(process)
                continue
            self._handle(event)

    def _watch(self, process) -> None:
        if self._stopping.is_set():
            return
        with self._lock:
            if process is not self._process:
                return
            asked = self._cancel_asked_at
        if not process.is_alive():
            code = process.exitcode
            self._replace_worker("failed", f"the worker process exited unexpectedly (code {code})")
        elif asked is not None and time.monotonic() - asked > self.cancel_grace:
            self._replace_worker("cancelled", None)

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event["type"]
        job_id = event.get("job_id")
        with self._lock:
            current = job_id is not None and job_id == self._running
        if kind in ("stage", "progress"):
            if current:
                with self._lock:
                    if kind == "stage":
                        self._live = {"stage": event["stage"]}
                    else:
                        fields = {k: v for k, v in event.items() if k not in ("type", "job_id")}
                        self._live = {**self._live, **fields}
                self.publish(job_id)
            return
        if kind not in ("done", "failed", "cancelled") or not current:
            return
        if kind == "done":
            audio = Path(event["audio_path"])
            self.store.add_song(job_id, audio.parent, audio, event["audio_seconds"])
        else:
            self.store.mark_finished(job_id, kind, event.get("error"))
            self._discard_partial_take(job_id)
        with self._lock:
            if self._running == job_id:
                self._running, self._live, self._cancel_asked_at = None, {}, None
                self._cancel.value = NO_JOB
        self.publish(job_id)
        self.dispatch()

    def _discard_partial_take(self, job_id: int) -> None:
        """Remove whatever an unfinished job left in its song directory; it was never indexed."""
        shutil.rmtree(self.songs_dir / str(job_id), ignore_errors=True)
