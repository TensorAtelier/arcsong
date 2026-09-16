"""Runs one measurement case, one fresh child process per run (D-008, D-015).

A case whose results file exists is skipped unless forced. Whatever happens in a
child (success, Unsupported, an exception, a crash, an out-of-memory kill or a
timeout) ends up as the `outcome` of that run and of the case; the harness keeps
going. While a child runs, its physical footprint is sampled from this process.
A child never outlives the harness: it is killed when the harness exits, and it
exits by itself if the harness is killed outright.
"""

from __future__ import annotations

import multiprocessing
import os
import re
import shutil
import signal
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spike import env as environment
from spike.engine import SpikeEngine, Unsupported
from spike.memory import MemorySampler
from spike.results import build_result, case_stem, write_result

Measure = Callable[[SpikeEngine, dict, dict, Path], dict]
EngineFactory = Callable[[], SpikeEngine]

DEFAULT_TIMEOUT_SECONDS = 3600.0
ORPHAN_CHECK_SECONDS = 0.5

_OOM_MESSAGE = re.compile(r"out of memory|insufficient memory|MemoryError", re.IGNORECASE)


def _exit_when_orphaned(parent_pid: int) -> None:
    """Stop this child once the harness that started it is gone (e.g. SIGKILLed)."""
    while True:
        if os.getppid() != parent_pid:
            os._exit(1)
        time.sleep(ORPHAN_CHECK_SECONDS)


def _child(
    conn, parent_pid: int, measure: Measure, factory: EngineFactory, request, params, run_dir
) -> None:
    threading.Thread(target=_exit_when_orphaned, args=(parent_pid,), daemon=True).start()
    try:
        run = measure(factory(), request, params, run_dir)
        message = ("ok", run, None)
    except Unsupported as error:
        message = ("unsupported", {}, f"Unsupported: {error}")
    except MemoryError:
        message = ("oom", {}, traceback.format_exc())
    except BaseException as error:  # noqa: BLE001 - every failure becomes an outcome
        text = traceback.format_exc()
        message = ("oom" if _OOM_MESSAGE.search(str(error)) else "failed", {}, text)
    try:
        conn.send(message)
    finally:
        conn.close()


def _outcome_from_exit(exitcode: int | None) -> tuple[str, str]:
    if exitcode is not None and exitcode < 0:
        name = signal.Signals(-exitcode).name
        if -exitcode == signal.SIGKILL:
            return "oom", f"child process terminated by {name} (treated as an out-of-memory kill)"
        return "failed", f"child process terminated by {name}"
    return "failed", f"child process exited with code {exitcode} without reporting a result"


def _run_child(
    measure: Measure,
    engine_factory: EngineFactory,
    request: dict,
    params: dict[str, Any],
    run_dir: Path,
    timeout: float | None,
) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(
        target=_child,
        args=(sender, os.getpid(), measure, engine_factory, request, params, run_dir),
    )
    start = time.perf_counter()
    child.start()
    sender.close()
    sampler = MemorySampler(child.pid).start()
    try:
        if receiver.poll(timeout):
            try:
                outcome, run, error = receiver.recv()
            except EOFError:
                child.join()
                outcome, error = _outcome_from_exit(child.exitcode)
                run = {}
        else:
            child.kill()
            outcome, run, error = "failed", {}, f"run timed out after {timeout:g}s and was killed"
        child.join()
    finally:
        sampler.stop()
        if child.is_alive():
            child.kill()
            child.join()
        receiver.close()

    record: dict[str, Any] = {"outcome": outcome}
    if error is not None:
        record["error"] = error
    record.update(run)
    record["child_wall_seconds"] = time.perf_counter() - start
    record.update(sampler.to_dict())
    return record


def run_case(
    *,
    measurement: str,
    measure: Measure,
    engine_name: str,
    engine_factory: EngineFactory,
    case: str,
    request: dict,
    params: dict[str, Any],
    results_dir: Path,
    runs_dir: Path,
    force: bool = False,
    repeats: int = 1,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    log: Callable[[str], None] = print,
) -> Path:
    stem = case_stem(measurement, engine_name, case, params)
    results_path = results_dir / f"{stem}.json"
    if results_path.exists() and not force:
        log(f"skip {stem}: results exist at {results_path} (use --force to rerun)")
        return results_path

    info = engine_factory().info()
    env = environment.snapshot(info)
    if env["model_servers"]:
        names = ", ".join(sorted({s["server"] for s in env["model_servers"]}))
        print(
            f"warning: other model servers are running ({names}); memory numbers may be skewed",
            file=sys.stderr,
        )

    case_dir = runs_dir / stem
    if case_dir.exists():
        shutil.rmtree(case_dir)

    started_at = datetime.now(UTC).isoformat()
    start = time.perf_counter()
    runs = []
    for index in range(1, repeats + 1):
        run_dir = case_dir / f"run-{index}"
        run_dir.mkdir(parents=True)
        log(f"run {stem} ({index}/{repeats})")
        record = _run_child(measure, engine_factory, request, params, run_dir, timeout)
        runs.append({"run": index, **record})
        log(f"{record['outcome']} {stem} run {index} in {record['child_wall_seconds']:.1f}s")
    total_seconds = time.perf_counter() - start

    failures = [run for run in runs if run["outcome"] != "ok"]
    result = build_result(
        measurement=measurement,
        engine=engine_name,
        engine_version=info.version,
        case=case,
        params=params,
        env=env,
        outcome=failures[0]["outcome"] if failures else "ok",
        started_at=started_at,
        total_seconds=total_seconds,
        runs=runs,
        error=failures[0].get("error") if failures else None,
    )
    write_result(results_path, result)
    log(f"{result['outcome']} {stem} in {total_seconds:.1f}s -> {results_path}")
    return results_path
