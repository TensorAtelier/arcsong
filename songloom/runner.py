"""The job runner inside the server: feeds queued jobs to the worker one at a time and turns
the worker's events into database updates."""

from __future__ import annotations

import multiprocessing as mp
import queue
import threading
from pathlib import Path
from typing import Any

from songloom.db import Store
from songloom.engine import EngineSpec
from songloom.worker import worker_main


class JobRunner:
    def __init__(self, store: Store, songs_dir: Path, spec: EngineSpec):
        self.store = store
        self.songs_dir = songs_dir
        self.spec = spec
        self._ctx = mp.get_context("spawn")
        self._lock = threading.Lock()
        self._running: int | None = None
        self._stopping = threading.Event()

    def start(self) -> None:
        self._jobs = self._ctx.Queue()
        self._events = self._ctx.Queue()
        self._cancel = self._ctx.Event()
        self._process = self._ctx.Process(
            target=worker_main,
            args=(self.spec, self._jobs, self._events, self._cancel),
            daemon=True,
        )
        self._process.start()
        self._thread = threading.Thread(target=self._pump, name="songloom-events", daemon=True)
        self._thread.start()
        self.dispatch()

    def stop(self) -> None:
        self._stopping.set()
        self._cancel.set()
        self._jobs.put(None)
        self._process.join(timeout=5)
        if self._process.is_alive():
            self._process.kill()
            self._process.join()
        self._thread.join(timeout=2)

    def dispatch(self) -> None:
        """Send the oldest queued job to the worker if it is idle."""
        with self._lock:
            if self._running is not None or self._stopping.is_set():
                return
            job = self.store.next_queued()
            if job is None:
                return
            self._running = job["id"]
            self.store.mark_running(job["id"])
            out_dir = self.songs_dir / str(job["id"])
            self._jobs.put((job["id"], job["request"], str(out_dir)))

    def _pump(self) -> None:
        while not self._stopping.is_set():
            try:
                event = self._events.get(timeout=0.2)
            except queue.Empty:
                continue
            self._handle(event)

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event["type"]
        job_id = event.get("job_id")
        if kind == "done":
            audio = Path(event["audio_path"])
            self.store.add_song(job_id, audio.parent, audio, event["audio_seconds"])
        elif kind == "failed":
            self.store.mark_finished(job_id, "failed", event["error"])
        elif kind == "cancelled":
            self.store.mark_finished(job_id, "cancelled")
        else:
            return
        with self._lock:
            if self._running == job_id:
                self._running = None
        self.dispatch()
