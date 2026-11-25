"""The job runner inside the server: feeds queued jobs to the workers, turns their events into
database updates and live progress, broadcasts job changes, and replaces a worker process when
it dies. Each Engine (the Mac, Modal, RunPod) is a lane with its own worker that runs one job at
a time, so a song on RunPod never waits behind one on the Mac."""

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

from arcsong.db import Store
from arcsong.engine import EngineSpec
from arcsong.worker import NO_JOB, worker_main

# A running job that has not stopped this long after a cancel request gets its worker killed.
# (M0: mlx-Yue honoured cancel within 0.13 s in every Stage.)
CANCEL_GRACE_SECONDS = 10.0
# After the model fails to load, wait this long before trying a new worker for the next job,
# so a persistent failure (missing weights, battery, GPU held elsewhere) can't spin.
LOAD_RETRY_SECONDS = 5.0
# How long stop() waits for the worker to finish a Take it is already saving.
STOP_WAIT_SECONDS = 5.0
# A Final re-synthesizes a Draft at full quality.
FINAL_STEPS = 32


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


class Lane:
    """One Engine: its worker process, and the job that worker is running."""

    def __init__(self, name: str, spec: EngineSpec, default: bool):
        self.name, self.spec = name, spec
        # The default lane also runs jobs that name no Engine, and starts its worker at once.
        self.default = default
        self.process = None
        self.jobs = self.events = self.cancel = None
        self.running: int | None = None
        self.live: dict[str, Any] = {}
        self.cancel_asked_at: float | None = None
        self.worker_ready = False
        self.load_failed_at: float | None = None
        self.thread: threading.Thread | None = None


DEFAULT_LANE = "engine"


class JobRunner:
    def __init__(
        self,
        store: Store,
        songs_dir: Path,
        engines: EngineSpec | dict[str, EngineSpec],
        cancel_grace: float = CANCEL_GRACE_SECONDS,
        load_retry: float = LOAD_RETRY_SECONDS,
    ):
        """`engines`: one spec, or one per Engine id, the first being the default."""
        self.store = store
        self.songs_dir = songs_dir
        # A cover's transcription exports (MIDI, LAB, result.json) live beside the songs.
        self.covers_dir = songs_dir.parent / "covers"
        self.uploads_dir = songs_dir.parent / "uploads"
        if isinstance(engines, EngineSpec):
            engines = {DEFAULT_LANE: engines}
        self.lanes = {
            name: Lane(name, spec, i == 0) for i, (name, spec) in enumerate(engines.items())
        }
        self.default_engine = next(iter(self.lanes))
        self.cancel_grace = cancel_grace
        self.load_retry = load_retry
        self.broadcaster = Broadcaster()
        self._ctx = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        # Microseconds since the epoch, so snapshots from a restarted server still outrank
        # snapshots a page kept from the previous one.
        self._seq = itertools.count(time.time_ns() // 1000)
        self.worker_starts = 0

    # --- lifecycle -------------------------------------------------------------------------

    def start(self) -> None:
        self._discard_staged_uploads()
        for job_id in self.store.recover():
            self._discard_partial_take(job_id)
            self._discard_upload(job_id)
        for lane in self.lanes.values():
            if lane.default:
                self._start_worker(lane)
            lane.thread = threading.Thread(
                target=self._pump, args=(lane,), name=f"arcsong-events-{lane.name}", daemon=True
            )
            lane.thread.start()
        self.dispatch()

    def stop(self) -> None:
        self._stopping.set()
        for lane in self.lanes.values():
            if lane.thread is not None:
                lane.thread.join(timeout=2)
        with self._lock:
            stopping = [lane for lane in self.lanes.values() if lane.process is not None]
            for lane in stopping:
                if lane.running is not None:
                    lane.cancel.value = lane.running
                lane.jobs.put(None)
        for lane in stopping:
            lane.process.join(timeout=STOP_WAIT_SECONDS)
            if lane.process.is_alive():
                lane.process.kill()
                lane.process.join()
            # A Take that was already saving when we asked it to stop still counts.
            while True:
                try:
                    self._handle(lane, lane.events.get(timeout=0.2))
                except queue.Empty:
                    break

    def _start_worker(self, lane: Lane) -> None:
        with self._lock:
            lane.jobs = self._ctx.Queue()
            lane.events = self._ctx.Queue()
            lane.cancel = self._ctx.Value("q", NO_JOB)
            lane.process = self._ctx.Process(
                target=worker_main,
                args=(lane.spec, lane.jobs, lane.events, lane.cancel, os.getpid()),
                daemon=True,
            )
            lane.worker_ready = False
            lane.process.start()
            self.worker_starts += 1

    def _replace_worker(
        self, lane: Lane, outcome: str, error: str | None, restart: bool = True
    ) -> None:
        """The worker died or had to be killed: close out its job, and start a fresh worker
        now (`restart`) or leave it to the next dispatch (after a failed model load)."""
        with self._lock:
            process, job_id = lane.process, lane.running
            if process is not None:
                if process.is_alive():
                    process.kill()
                process.join()
            if job_id is not None:
                self.store.mark_finished(job_id, outcome, error)
                self._discard_partial_take(job_id)
                self._discard_upload(job_id)
                lane.running, lane.live, lane.cancel_asked_at = None, {}, None
            if restart:
                self._start_worker(lane)
            else:
                lane.process = None
        if job_id is not None:
            self.publish(job_id)
        self.dispatch()

    def _load_failed(self, lane: Lane, error: str) -> None:
        """The model could not load: fail the job waiting for it with the real reason, and
        don't start another worker until a job needs one and the retry delay has passed."""
        reason = error.strip().splitlines()[-1] if error.strip() else "unknown error"
        with self._lock:
            lane.load_failed_at = time.monotonic()
        message = f"The model could not load: {reason}\n\n{error}"
        self._replace_worker(lane, "failed", message, False)

    # --- jobs ------------------------------------------------------------------------------

    def job(self, job_id: int) -> dict[str, Any] | None:
        """A job from the database, with live progress while it runs. `seq` grows with every
        snapshot taken, so a client receiving snapshots by different routes (REST, SSE) can
        keep the newest."""
        with self._lock:
            job = self.store.get_job(job_id)
            if job is not None:
                job["live"] = self._live().get(job_id)
                job["seq"] = next(self._seq)
        return job

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            live, seq = self._live(), next(self._seq)
            listed = self.store.list_jobs()
        return [{**j, "live": live.get(j["id"]), "seq": seq} for j in listed]

    def group(self, group_id: int) -> list[dict[str, Any]]:
        """A group's jobs, oldest first, with live progress like `jobs()`."""
        with self._lock:
            live, seq = self._live(), next(self._seq)
            listed = self.store.list_group(group_id)
        return [{**j, "live": live.get(j["id"]), "seq": seq} for j in listed]

    def _live(self) -> dict[int, dict[str, Any]]:
        """Each running job's live progress, by job id."""
        return {
            lane.running: dict(lane.live)
            for lane in self.lanes.values()
            if lane.running is not None
        }

    def engine_of(self, job: dict[str, Any]) -> str:
        """The Engine a job or song runs on; one from before jobs had an Engine, the default."""
        return job.get("engine") or self.default_engine

    def dispatch(self) -> None:
        """Send each idle lane its oldest queued job."""
        for lane in self.lanes.values():
            self._dispatch(lane)

    def _dispatch(self, lane: Lane) -> None:
        """Send the lane's oldest queued job to its worker if it is idle, starting a worker if
        there is none (unless the last model load failed too recently)."""
        with self._lock:
            if lane.running is not None or self._stopping.is_set():
                return
            job = self.store.next_queued(lane.name, lane.default)
            if job is None:
                return
            source_dir = None
            if job["source_song_id"] is not None:
                source = self.store.get_song(job["source_song_id"])
                if source is None:
                    self.store.mark_finished(job["id"], "failed", "its Draft was deleted")
                    self.publish(job["id"])
                    self._dispatch(lane)  # the next queued job, if any
                    return
                source_dir = source["dir"]
            if lane.process is None:
                failed_at = lane.load_failed_at
                if failed_at is not None and time.monotonic() - failed_at < self.load_retry:
                    return  # the pump retries dispatch once the delay has passed
                self._start_worker(lane)
            lane.running, lane.live = job["id"], {"stage": None}
            self.store.mark_running(job["id"])
            out_dir = self.songs_dir / str(job["id"])
            if job["kind"] == "cover":
                out_dir = self.covers_dir / str(job["id"])
            lane.jobs.put(
                {
                    "job_id": job["id"],
                    "request": job["request"],
                    "kind": job["kind"],
                    "out_dir": str(out_dir),
                    "source_dir": source_dir,
                    "source_audio": job["source_audio"],
                }
            )
        self.publish(job["id"])

    def cancel(self, job_id: int) -> bool:
        """Cancel a queued or running job; False if it has already finished (or never existed)."""
        with self._lock:
            job = self.store.get_job(job_id)
            if job is None or job["status"] not in ("queued", "running"):
                return False
            if job["status"] == "queued":
                self.store.mark_finished(job_id, "cancelled")
                self._discard_upload(job_id)
            else:
                for lane in self.lanes.values():
                    if lane.running == job_id:
                        lane.cancel.value = job_id
                        lane.cancel_asked_at = lane.cancel_asked_at or time.monotonic()
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

    def finalize(self, song_id: int) -> tuple[dict[str, Any] | None, str | None]:
        """Queue a Final of a Draft: the same request at 32 Synthesis steps. Returns the job, or
        why it can't be queued ("no such song" means 404)."""
        with self._lock:
            song = self.store.get_song(song_id)
            if song is None:
                return None, "no such song"
            if song["request"]["steps"] >= FINAL_STEPS:
                return None, f"this Take already has {FINAL_STEPS} Synthesis steps"
            for final in self.store.finals_of(song_id):
                if final["status"] in ("queued", "running", "done"):
                    return None, f"this Draft already has a Final (job #{final['id']})"
            # The Draft's current name, so a queued Final already shows a rename.
            request = {**song["request"], "steps": FINAL_STEPS, "title": song["title"]}
            # A Final continues the Draft's own saved tokens, so it runs where the Draft did.
            engine = self.engine_of(song)
            job = self.store.create_job(request, source_song_id=song_id, engine=engine)
        self.publish(job["id"])
        self.dispatch()
        return self.job(job["id"]), None

    def star_song(self, song_id: int, starred: bool) -> dict[str, Any] | None:
        if not self.store.set_starred(song_id, starred):
            return None
        return self._song_changed(song_id)

    def title_song(self, song_id: int, title: str | None) -> dict[str, Any] | None:
        if not self.store.set_title(song_id, title):
            return None
        return self._song_changed(song_id)

    def _song_changed(self, song_id: int) -> dict[str, Any] | None:
        song = self.store.get_song(song_id)
        if song is None:
            return None  # deleted between the update and this read
        self.publish_message({"type": "song", "song": song, "seq": self.next_seq()})
        # The job snapshot carries the star and title too.
        self.publish(song["job_id"])
        return song

    def publish_message(self, message: dict[str, Any]) -> None:
        """Broadcast a message that is not a job snapshot (`deleted`, `setup`)."""
        self.broadcaster.publish(message)

    def publish(self, job_id: int) -> None:
        job = self.job(job_id)
        if job is not None:
            self.broadcaster.publish({"type": "job", "job": job})

    # --- worker events ---------------------------------------------------------------------

    def _pump(self, lane: Lane) -> None:
        while not self._stopping.is_set():
            with self._lock:
                events, process = lane.events, lane.process
            event = None
            if events is None:
                time.sleep(0.2)  # this lane's worker hasn't been needed yet
            else:
                try:
                    event = events.get(timeout=0.2)
                except queue.Empty:
                    pass
            if event is not None:
                self._handle(lane, event)
            # Checked on every pass, not only when idle, so a job that ignores cancel but keeps
            # sending progress still gets killed after the grace period.
            self._watch(lane, process)

    def _watch(self, lane: Lane, process) -> None:
        if self._stopping.is_set():
            return
        if process is None:
            self._dispatch(lane)  # a load failure is waiting out its retry delay
            return
        with self._lock:
            if process is not lane.process:
                return
            asked, ready = lane.cancel_asked_at, lane.worker_ready
        if not process.is_alive():
            code = process.exitcode
            if not ready:
                error = f"the worker process exited with code {code} while loading"
                self._load_failed(lane, error)
            else:
                message = f"the worker process exited unexpectedly (code {code})"
                self._replace_worker(lane, "failed", message)
        elif asked is not None and time.monotonic() - asked > self.cancel_grace:
            self._replace_worker(lane, "cancelled", None)

    def _handle(self, lane: Lane, event: dict[str, Any]) -> None:
        kind = event["type"]
        job_id = event.get("job_id")
        if kind == "ready":
            with self._lock:
                lane.worker_ready, lane.load_failed_at = True, None
            return
        if kind == "load_failed":
            if not self._stopping.is_set():
                self._load_failed(lane, event["error"])
            return
        with self._lock:
            current = job_id is not None and job_id == lane.running
        if kind in ("stage", "progress"):
            if current:
                with self._lock:
                    if kind == "stage":
                        lane.live = {"stage": event["stage"]}
                    else:
                        fields = {k: v for k, v in event.items() if k not in ("type", "job_id")}
                        lane.live = {**lane.live, **fields}
                self.publish(job_id)
            return
        if kind not in ("done", "failed", "cancelled") or not current:
            return
        if kind == "done" and "score" in event:
            self.store.finish_score(job_id, event["score"])
            self._discard_upload(job_id)
        elif kind == "done":
            audio = Path(event["audio_path"])
            self.store.add_song(job_id, audio.parent, audio, event["audio_seconds"])
        else:
            self.store.mark_finished(job_id, kind, event.get("error"))
            self._discard_partial_take(job_id)
            self._discard_upload(job_id)
        with self._lock:
            if lane.running == job_id:
                lane.running, lane.live, lane.cancel_asked_at = None, {}, None
                lane.cancel.value = NO_JOB
        self.publish(job_id)
        self._dispatch(lane)

    def _discard_staged_uploads(self) -> None:
        """Recordings a previous server was still receiving when it died belong to no job."""
        for path in self.uploads_dir.glob("incoming-*"):
            path.unlink(missing_ok=True)

    def _discard_upload(self, job_id: int) -> None:
        """A cover's recording is the user's own audio: delete it the moment the job ends,
        however it ends."""
        job = self.store.get_job(job_id)
        if job is None or job["kind"] != "cover" or not job["source_audio"]:
            return
        Path(job["source_audio"]).unlink(missing_ok=True)
        self.store.clear_source_audio(job_id)

    def _discard_partial_take(self, job_id: int) -> None:
        """Remove whatever an unfinished job left in its song directory; it was never indexed."""
        shutil.rmtree(self.songs_dir / str(job_id), ignore_errors=True)
