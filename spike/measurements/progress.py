"""`progress`: which progress signals fire inside each Stage of a `song` Take, how often,
and whether they can drive a % bar.

Decisions: D-005 (Engines report through the seam), D-008 (monotonic timestamps).

The Engine sends a `ProgressEvent` for every signal it sees (mlx-Yue: `on_token` callbacks
and yue2's progress lines on stderr; audio.cpp: `--log` line arrivals). Each signal is
attributed to the Stage whose recorded start→end span holds it strictly, so the log line
that ends a Stage counts in neither Stage. Counting is passive: an event is a timestamp and
a list append, and the Take runs exactly as it would without it.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from spike.engine import STAGES, ProgressEvent, SpikeEngine, StageEvent
from spike.measurements.timing import stage_seconds

MEASUREMENT = "progress"
CASE = "song"
STEPS = 8
RUNS = 1
PRECISIONS = {"mlx": "8bit", "audiocpp": "q8_0", "fake": "8bit"}
EVENTS_NAME = "progress-events.jsonl"
# A bar whose shown fraction never strays further than this from the elapsed fraction of
# the Stage's wall time counts as tracking wall time (linear). The shown fraction is checked
# as each signal arrives, just before it (the value the bar has held since the previous
# signal, 0 before the first) and at the Stage's end, so a bar with fewer steps than
# 1 / LINEAR_MAX_DEVIATION can only pass if its steps are offset to straddle wall time.
LINEAR_MAX_DEVIATION = 0.15
# A % signal with fewer updates than this inside its Stage is too coarse to animate a bar,
# however its few steps happen to line up with wall time.
MIN_BAR_UPDATES = 5
CURVE_POINTS = 10
# Verdicts, best first.
VERDICTS = ("percent", "uneven_percent", "count_only", "coarse_percent", "uneven_count")

Event = StageEvent | ProgressEvent


def stage_spans(events: Iterable[Event]) -> dict[str, tuple[float, float]]:
    """Each Stage's first start and last end, for the Stages that have both."""
    starts: dict[str, float] = {}
    ends: dict[str, float] = {}
    for event in events:
        if event.kind == "start":
            starts.setdefault(event.stage, event.t)
        elif event.kind == "end":
            ends[event.stage] = event.t
    return {s: (starts[s], ends[s]) for s in STAGES if s in starts and s in ends}


def _max_in_window(times: list[float], window: float = 1.0) -> int:
    best, first = 0, 0
    for last, t in enumerate(times):
        while t - times[first] >= window:
            first += 1
        best = max(best, last - first + 1)
    return best


def signal_stats(signals: list[ProgressEvent], start: float, end: float) -> dict[str, Any]:
    """Count, inter-arrival times, event rate, total detection and linearity of one signal
    (`signals` in arrival order) inside a Stage spanning `start`→`end`."""
    times = [s.t for s in signals]
    count = len(times)
    duration = end - start
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    totals = [s.total for s in signals]
    total_from = next((i for i, total in enumerate(totals, start=1) if total is not None), None)
    final_total = next((t for t in reversed(totals) if t is not None), None)
    completed = [s.completed for s in signals if s.completed is not None]
    top = max(completed, default=0)

    shown = []
    for index, signal in enumerate(signals, start=1):
        denominator = signal.total or final_total or top
        if signal.completed is not None and denominator:
            shown.append(signal.completed / denominator)
        else:
            shown.append(index / count)
    elapsed = [(t - start) / duration if duration > 0 else 1.0 for t in times]
    deviation = None
    if times:
        held = [0.0, *shown[:-1]]
        deviation = max(
            abs(shown[-1] - 1.0),
            *(max(abs(p - x), abs(h - x)) for p, h, x in zip(shown, held, elapsed, strict=True)),
        )

    curve = []
    for point in range(CURVE_POINTS + 1):
        at = start + duration * point / CURVE_POINTS
        latest = [p for p, t in zip(shown, times, strict=True) if t <= at]
        curve.append(round(latest[-1] if latest else 0.0, 3))

    return {
        "count": count,
        "inter_arrival_seconds": None
        if not gaps
        else {"min": min(gaps), "median": statistics.median(gaps), "max": max(gaps)},
        "first_after_start_seconds": times[0] - start if times else None,
        "last_before_end_seconds": end - times[-1] if times else None,
        "per_second": {
            "mean": count / duration if duration > 0 else None,
            "max_in_one_second": _max_in_window(times),
        },
        "total_known_up_front": total_from == 1,
        "total_known_from_signal": total_from,
        "running_count_only": total_from is None,
        "total": final_total,
        "tracks_wall_time": {
            "max_deviation": deviation,
            "linear": deviation is not None and deviation <= LINEAR_MAX_DEVIATION,
            "curve": curve,
        },
    }


def verdict(signals: dict[str, dict]) -> dict[str, Any]:
    """Whether a Stage's best signal can drive a % bar: `percent` (a total and progress that
    tracks wall time), `uneven_percent` (a total, but progress runs ahead of or behind wall
    time), `count_only` (a running count with no total that tracks wall time),
    `coarse_percent` (a total, but fewer than MIN_BAR_UPDATES updates), `uneven_count` (a
    running count that does not track wall time, e.g. bursts of setup lines) or `none` (fewer
    than two signals). Among signals with the same verdict, the one closest to wall time wins, then
    the busiest."""
    ranked = []
    for name, stats in signals.items():
        if stats["count"] < 2:
            continue
        linear = stats["tracks_wall_time"]["linear"]
        if stats["running_count_only"]:
            kind = "count_only" if linear else "uneven_count"
        elif stats["count"] < MIN_BAR_UPDATES:
            kind = "coarse_percent"
        else:
            kind = "percent" if linear else "uneven_percent"
        deviation = stats["tracks_wall_time"]["max_deviation"]
        rank = (VERDICTS.index(kind), deviation, -stats["count"])
        ranked.append((*rank, name, kind))
    if not ranked:
        return {"verdict": "none", "signal": None}
    *_, name, kind = min(ranked)
    return {"verdict": kind, "signal": name}


def analyse(events: Iterable[Event]) -> dict[str, dict[str, Any]]:
    """Per Stage: its wall time, every progress signal that fired inside it, and a verdict."""
    events = list(events)
    spans = stage_spans(events)
    progress = sorted((e for e in events if e.kind == "progress"), key=lambda e: e.t)
    stages: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        if stage not in spans:
            stages[stage] = {
                "seconds": None,
                "signals": {},
                "percent_bar": {"verdict": "not_run", "signal": None},
            }
            continue
        start, end = spans[stage]
        by_signal: dict[str, list[ProgressEvent]] = {}
        for event in progress:
            if start < event.t < end:
                by_signal.setdefault(event.signal, []).append(event)
        signals = {name: signal_stats(found, start, end) for name, found in by_signal.items()}
        stages[stage] = {
            "seconds": end - start,
            "signals": signals,
            "percent_bar": verdict(signals),
        }
    return stages


def write_events(events: Iterable[Event], directory: Path, since: float) -> Path:
    """Every Stage and progress event, one JSON line each, timed from `since`."""
    path = directory / EVENTS_NAME
    with path.open("w") as out:
        for event in sorted(events, key=lambda e: e.t):
            record = event.to_dict()
            record["seconds"] = record.pop("t") - since
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def measure(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    events: list[Event] = []
    take_dir = run_dir / "take"
    # yue2 refreshes its stderr progress every 0.25 s on a terminal but at most every 5 s
    # through a pipe, so its line counts depend on this.
    stderr_is_tty = bool(getattr(sys.stderr, "isatty", lambda: False)())

    load_start = time.monotonic()
    engine.load(params["precision"])
    run_start = time.monotonic()
    output = engine.run(request, params["steps"], take_dir, on_event=events.append)
    run_end = time.monotonic()

    recorded = list(events)
    events_path = write_events(recorded, run_dir, run_start)
    return {
        "load_seconds": run_start - load_start,
        "run_seconds": run_end - run_start,
        "total_seconds": run_end - load_start,
        "audio_seconds": output.audio_seconds,
        "stage_seconds": stage_seconds(recorded),
        "stages": analyse(recorded),
        "progress_hooks": output.details.get("progress_hooks"),
        "stderr_is_tty": stderr_is_tty,
        "progress_events": sum(e.kind == "progress" for e in recorded),
        "events_path": str(events_path),
    }
