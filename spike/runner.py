"""Runs one measurement case in a fresh child process (D-008, D-015).

A case whose results file exists is skipped unless forced. Whatever happens in the
child (success, Unsupported, an exception, a crash or an out-of-memory kill) ends up
as the `outcome` of that case's results file; the harness itself keeps going.
"""

from __future__ import annotations

import multiprocessing
import re
import shutil
import signal
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spike import env as environment
from spike.engine import SpikeEngine, Unsupported
from spike.results import build_result, case_stem, write_result

Measure = Callable[[SpikeEngine, dict, dict, Path], list[dict]]
EngineFactory = Callable[[], SpikeEngine]

_OOM_MESSAGE = re.compile(r"out of memory|insufficient memory|MemoryError", re.IGNORECASE)


def _child(conn, measure: Measure, factory: EngineFactory, request, params, run_dir) -> None:
    try:
        runs = measure(factory(), request, params, run_dir)
        message = ("ok", runs, None)
    except Unsupported as error:
        message = ("unsupported", [], f"Unsupported: {error}")
    except MemoryError:
        message = ("oom", [], traceback.format_exc())
    except BaseException as error:  # noqa: BLE001 - every failure becomes an outcome
        text = traceback.format_exc()
        message = ("oom" if _OOM_MESSAGE.search(str(error)) else "failed", [], text)
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
        print(f"warning: other model servers are running ({names}); memory numbers may be skewed",
              file=sys.stderr)

    run_dir = runs_dir / stem
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    log(f"run {stem}")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(
        target=_child, args=(sender, measure, engine_factory, request, params, run_dir)
    )
    started_at = datetime.now(UTC).isoformat()
    start = time.perf_counter()
    child.start()
    sender.close()
    try:
        outcome, runs, error = receiver.recv()
    except EOFError:
        child.join()
        outcome, error = _outcome_from_exit(child.exitcode)
        runs = []
    child.join()
    total_seconds = time.perf_counter() - start

    result = build_result(
        measurement=measurement,
        engine=engine_name,
        engine_version=info.version,
        case=case,
        params=params,
        env=env,
        outcome=outcome,
        started_at=started_at,
        total_seconds=total_seconds,
        runs=runs,
        error=error,
    )
    write_result(results_path, result)
    log(f"{outcome} {stem} in {total_seconds:.1f}s -> {results_path}")
    return results_path
