"""The job runner inside the server: feeds queued jobs to the worker one at a time, turns the
worker's events into database updates and live progress, broadcasts job changes, and replaces
the worker process when it dies."""

from __future__ import annotations

import itertools
import multiprocessing as mp
import os
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
# After the model fails to load, wait this long before trying a new worker for the next job,
# so a persistent failure (missing weights, battery, GPU held elsewhere) can't spin.
LOAD_RETRY_SECONDS = 5.0
# How long stop() waits for the worker to finish a Take it is already saving.
STOP_WAIT_SECONDS = 5.0


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
        load_retry: float = LOAD_RETRY_SECONDS,
    ):
        self.store = store
        self.songs_dir = songs_dir
        self.spec = spec
        self.cancel_grace = cancel_grace
        self.load_retry = load_retry
        self.broadcaster = Broadcaster()
        self._ctx = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._running: int | None = None
        self._live: dict[str, Any] = {}
        self._cancel_asked_at: float | None = None
        self._stopping = threading.Event()
        # Microseconds since the epoch, so snapshots from a restarted server still outrank
        # snapshots a page kept from the previous one.
        self._seq = itertools.count(time.time_ns() // 1000)
        self._process = None
        self._worker_ready = False
        self._load_failed_at: float | None = None
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
        self._thread.join(timeout=2)
        with self._lock:
            process = self._process
            if process is not None:
                if self._running is not None:
                    self._cancel.value = self._running
                self._jobs.put(None)
        if process is None:
            return
        process.join(timeout=STOP_WAIT_SECONDS)
        if process.is_alive():
            process.kill()
            process.join()
        # A Take that was already saving when we asked it to stop still counts.
        while True:
            try:
                self._handle(self._events.get(timeout=0.2))
            except queue.Empty:
                break

    def _start_worker(self) -> None:
        with self._lock:
            self._jobs = self._ctx.Queue()
            self._events = self._ctx.Queue()
            self._cancel = self._ctx.Value("q", NO_JOB)
            self._process = self._ctx.Process(
                target=worker_main,
                args=(self.spec, self._jobs, self._events, self._cancel, os.getpid()),
                daemon=True,
            )
            self._worker_ready = False
            self._process.start()
            self.worker_starts += 1

    def _replace_worker(self, outcome: str, error: str | None, restart: bool = True) -> None:
        """The worker died or had to be killed: close out its job, and start a fresh worker
        now (`restart`) or leave it to the next dispatch (after a failed model load)."""
        with self._lock:
            process, job_id = self._process, self._running
            if process is not None:
                if process.is_alive():
                    process.kill()
                process.join()
            if job_id is not None:
                self.store.mark_finished(job_id, outcome, error)
                self._discard_partial_take(job_id)
                self._running, self._live, self._cancel_asked_at = None, {}, None
            if restart:
                self._start_worker()
            else:
                self._process = None
        if job_id is not None:
            self.publish(job_id)
        self.dispatch()

    def _load_failed(self, error: str) -> None:
        """The model could not load: fail the job waiting for it with the real reason, and
        don't start another worker until a job needs one and the retry delay has passed."""
        reason = error.strip().splitlines()[-1] if error.strip() else "unknown error"
        with self._lock:
            self._load_failed_at = time.monotonic()
        self._replace_worker("failed", f"The model could not load: {reason}\n\n{error}", False)

    # --- jobs ------------------------------------------------------------------------------

    def job(self, job_id: int) -> dict[str, Any] | None:
        """A job from the database, with live progress while it runs. `seq` grows with every
        snapshot taken, so a client receiving snapshots by different routes (REST, SSE) can
        keep the newest."""
        with self._lock:
            job = self.store.get_job(job_id)
            if job is not None:
                job["live"] = dict(self._live) if job_id == self._running else None
                job["seq"] = next(self._seq)
        return job

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            running, live = self._running, dict(self._live)
            seq = next(self._seq)
            listed = self.store.list_jobs()
        return [{**j, "live": live if j["id"] == running else None, "seq": seq} for j in listed]

    def dispatch(self) -> None:
        """Send the oldest queued job to the worker if it is idle, starting a worker if there is
        none (unless the last model load failed too recently)."""
        with self._lock:
            if self._running is not None or self._stopping.is_set():
                return
            job = self.store.next_queued()
            if job is None:
                return
            if self._process is None:
                failed_at = self._load_failed_at
                if failed_at is not None and time.monotonic() - failed_at < self.load_retry:
                    return  # the pump retries dispatch once the delay has passed
                self._start_worker()
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

    def delete_song(self, song_id: int) -> dict[str, Any] | None:
        """Permanently delete a finished Take: its files, its song row and its job row."""
        song = self.store.delete_song(song_id)
        if song is None:
            return None
        shutil.rmtree(song["dir"], ignore_errors=True)
        message = {"type": "deleted", "job_id": song["job_id"], "song_id": song_id}
        self.publish_message({**message, "seq": self.next_seq()})
        return song

    def next_seq(self) -> int:
        return next(self._seq)

    def publish_message(self, message: dict[str, Any]) -> None:
        """Broadcast a message that is not a job snapshot (`deleted`, `setup`)."""
        self.broadcaster.publish(message)

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
                event = None
            if event is not None:
                self._handle(event)
            # Checked on every pass, not only when idle, so a job that ignores cancel but keeps
            # sending progress still gets killed after the grace period.
            self._watch(process)

    def _watch(self, process) -> None:
        if self._stopping.is_set():
            return
        if process is None:
            self.dispatch()  # a load failure is waiting out its retry delay
            return
        with self._lock:
            if process is not self._process:
                return
            asked, ready = self._cancel_asked_at, self._worker_ready
        if not process.is_alive():
            code = process.exitcode
            if not ready:
                self._load_failed(f"the worker process exited with code {code} while loading")
            else:
                message = f"the worker process exited unexpectedly (code {code})"
                self._replace_worker("failed", message)
        elif asked is not None and time.monotonic() - asked > self.cancel_grace:
            self._replace_worker("cancelled", None)

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event["type"]
        job_id = event.get("job_id")
        if kind == "ready":
            with self._lock:
                self._worker_ready, self._load_failed_at = True, None
            return
        if kind == "load_failed":
            if not self._stopping.is_set():
                self._load_failed(event["error"])
            return
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
