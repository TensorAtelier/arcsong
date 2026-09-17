"""`cancel`: how fast a cancel returns control in each Stage, and what it costs after.

Decisions: D-010 (method), D-015 (failures as outcomes).

One case per Stage, each in a fresh child: load the Engine, start a Take, request
cancel once the Stage has run `cancel_after_seconds`, and time the request until
`run` returns control. Then, in the same process, render a full `clip` Take; if that
fails, load the Engine again and retry, recording whether the reload was needed.
What the cancelled Take left on disk is listed, with whether it looks like a Take.

A Stage counts as begun at its first `enter` or `start` event: mlx-Yue reports a
Stage's start as it happens, audio.cpp announces it with `enter` from its log (its
`start` events arrive only once the Stage has ended).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from spike.cases import load_case
from spike.engine import STAGES, SpikeEngine, StageEvent
from spike.measurements.timing import artifact_sizes

MEASUREMENT = "cancel"
CANCEL_AFTER_SECONDS = 1.0
STEPS = 8
PRECISIONS = {"mlx": "8bit", "audiocpp": "q8_0", "fake": "8bit"}
# `clip` gets through planning (its Score is supplied) and decoding in under ~2 s.
STAGE_CASES = {
    "planning": "song",
    "semantic generation": "clip",
    "synthesis": "clip",
    "decoding": "song",
}
REUSE_CASE = "clip"
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg"}


def params(precision: str, steps: int, stage: str, cancel_after: float) -> dict:
    """A case's params. A cancel delay other than the default is part of the case (and
    its results file name), so a run at another delay never passes for the default."""
    case_params: dict = {"precision": precision, "steps": steps, "stage": stage}
    if cancel_after != CANCEL_AFTER_SECONDS:
        case_params["cancel_after_seconds"] = cancel_after
    return case_params


def stage_at(events: list[StageEvent], t: float) -> str | None:
    """The Stage running at time `t`: the latest one begun by then and not yet ended."""
    begun: dict[str, float] = {}
    ended: set[str] = set()
    for event in events:
        if event.t > t:
            continue
        if event.kind in ("enter", "start"):
            begun.setdefault(event.stage, event.t)
        elif event.kind == "end":
            ended.add(event.stage)
    running = [stage for stage in STAGES if stage in begun and stage not in ended]
    return running[-1] if running else None


def looks_complete(files: list[dict]) -> bool:
    """Whether a Take directory holds what a library would take for a finished Take."""
    return any(Path(f["path"]).suffix in AUDIO_SUFFIXES and f["bytes"] > 0 for f in files)


class CancelTrigger:
    """Requests cancel once `stage` has run `after` seconds, on a timer thread."""

    def __init__(self, stage: str, after: float):
        self.stage, self.after = stage, after
        self.events: list[StageEvent] = []
        self.entered_at: float | None = None
        self.requested_at: float | None = None
        self._requested = threading.Event()
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_event(self, event: StageEvent) -> None:
        with self._lock:
            self.events.append(event)
            if event.stage != self.stage or event.kind not in ("enter", "start"):
                return
            if self.entered_at is not None:
                return
            self.entered_at = event.t
            delay = max(0.0, event.t + self.after - time.monotonic())
            self._timer = threading.Timer(delay, self._request)
            self._timer.daemon = True
            self._timer.start()

    def _request(self) -> None:
        self.requested_at = time.monotonic()
        self._requested.set()

    def cancelled(self) -> bool:
        return self._requested.is_set()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()


def _reuse(engine: SpikeEngine, precision: str, steps: int, take_dir: Path) -> dict:
    request = load_case(REUSE_CASE)
    attempts: list[dict] = []
    reuse: dict = {"case": REUSE_CASE, "reloaded": False, "attempts": attempts}
    for reload in (False, True):
        if reload:
            reload_start = time.monotonic()
            engine.load(precision)
            reuse["reloaded"] = True
            reuse["reload_seconds"] = time.monotonic() - reload_start
        attempt_dir = take_dir.with_name(f"{take_dir.name}{'-reloaded' if reload else ''}")
        start = time.monotonic()
        try:
            output = engine.run(request, steps, attempt_dir)
        except Exception as error:  # noqa: BLE001 - a failed reuse is the finding
            attempts.append(
                {
                    "reloaded": reload,
                    "outcome": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        attempts.append({"reloaded": reload, "outcome": "ok"})
        files = artifact_sizes(attempt_dir)
        reuse.update(
            outcome="ok",
            run_seconds=time.monotonic() - start,
            lazy_load_seconds=output.lazy_load_seconds,
            audio_seconds=output.audio_seconds,
            take_dir=str(attempt_dir),
            files=files,
        )
        return reuse
    reuse["outcome"] = "failed"
    return reuse


def measure(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    stage = params["stage"]
    after = params.get("cancel_after_seconds", CANCEL_AFTER_SECONDS)
    take_dir = run_dir / "take"

    load_start = time.monotonic()
    engine.load(params["precision"])
    run_start = time.monotonic()
    load_seconds = run_start - load_start

    trigger = CancelTrigger(stage, after)
    cancelled_by = error_text = None
    kill_to_exit = None
    try:
        engine.run(
            request,
            params["steps"],
            take_dir,
            cancelled=trigger.cancelled,
            on_event=trigger.on_event,
        )
    except Exception as error:  # noqa: BLE001 - whatever the Engine raises on cancel
        returned_at = time.monotonic()
        if trigger.requested_at is None:
            raise
        cancelled_by, error_text = type(error).__name__, str(error)
        kill_to_exit = getattr(error, "kill_to_exit_seconds", None)
    else:
        trigger.stop()
        raise RuntimeError(
            f"the Take finished before cancel was requested in {stage} "
            f"(entered: {trigger.entered_at is not None})"
        )

    requested_at = trigger.requested_at
    leftover = artifact_sizes(take_dir) if take_dir.exists() else []
    record = {
        "stage": stage,
        "cancel_after_seconds": after,
        "load_seconds": load_seconds,
        "stage_entered_seconds": trigger.entered_at - run_start,
        "cancel_requested_seconds": requested_at - run_start,
        "stage_at_request": stage_at(trigger.events, requested_at),
        "cancel_latency_seconds": returned_at - requested_at,
        "cancelled_by": cancelled_by,
        "cancel_message": error_text,
        "take_dir": str(take_dir),
        "leftover_files": leftover,
        "leftover_looks_complete": looks_complete(leftover),
        "stage_events": [
            {"stage": e.stage, "kind": e.kind, "seconds": e.t - run_start}
            for e in sorted(trigger.events, key=lambda e: e.t)
        ],
    }
    if kill_to_exit is not None:
        record["kill_to_exit_seconds"] = kill_to_exit
    record["reuse"] = _reuse(engine, params["precision"], params["steps"], run_dir / "reuse")
    return record
