"""`hygiene`: what a Take killed mid-synthesis leaves behind, and what a rerun needs.

Decisions: D-013 (method), D-015 (failures as outcomes).

Two paths, each in its own directory under the run: the staged in-process path the
harness drives (`api`: `SpikeEngine.run` in a separate process) and the Engine's own
command line (`cli`: the optional `take_command` capability; `unsupported` without it).
For each, a `clip` Take is started writing to `<path>/take`, killed (SIGKILL, as a
crash or a force-quit would) once synthesis has run `kill_after_seconds`, and every
file left in `<path>` is listed, including files next to the output directory such as
`take.resources.jsonl`. The Take is then rerun to the same output directory with no
cleanup. While a rerun fails, cleanups are applied one at a time, cumulatively, from
the smallest: first the files named after the output directory next to it
(`take.*`), then the output directory itself. The first cleanup set that lets a rerun
succeed is the path's cleanup rule. A successful rerun also records any file from the
killed Take it left untouched (`stale_files_kept`), which would mix into the new Take.
"""

from __future__ import annotations

import glob
import multiprocessing
import os
import shutil
import subprocess
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable
from pathlib import Path

from spike.engine import STAGES, CliTake, SpikeEngine, StageEvent, Unsupported
from spike.measurements.cancel import looks_complete
from spike.runner import _exit_when_orphaned

MEASUREMENT = "hygiene"
CASE = "clip"
STEPS = 8
PRECISIONS = {"mlx": "8bit", "audiocpp": "q8_0", "fake": "8bit"}
KILL_STAGE = STAGES[2]
KILL_AFTER_SECONDS = 1.0
TAKE_TIMEOUT_SECONDS = 1200.0
OUTPUT_NAME = "take"
TAIL_LINES = 40
PATHS = ("api", "cli")


def params(precision: str, steps: int, kill_after: float) -> dict:
    case_params: dict = {"precision": precision, "steps": steps}
    if kill_after != KILL_AFTER_SECONDS:
        case_params["kill_after_seconds"] = kill_after
    return case_params


def _tree(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under `root`, relative to it, with (bytes, mtime_ns)."""
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            found[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return found


def _resource_files(paths) -> list[str]:
    """mlx-Yue's resource evidence files (`<output>.resources.json[l]`) among `paths`."""
    return sorted(path for path in paths if ".resources.json" in Path(path).name)


def _listing(tree: dict[str, tuple[int, int]]) -> list[dict]:
    return [{"path": path, "bytes": size} for path, (size, _) in tree.items()]


class _Take:
    """A running Take in another process: which Stages it has begun, kill, wait."""

    def __init__(self, stage_markers: dict[str, str] | None = None):
        self.begun: list[str] = []
        self._changed = threading.Condition()
        self.stage_markers = stage_markers or {}

    def _begin(self, stage: str) -> None:
        with self._changed:
            if stage not in self.begun:
                self.begun.append(stage)
                self._changed.notify_all()

    def wait_for_stage(self, stage: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._changed:
            while stage not in self.begun:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                if not self.alive():
                    break
                self._changed.wait(min(remaining, 0.1))
            else:
                return True
        self._drain()
        return stage in self.begun

    def _drain(self) -> None:
        """Wait for the output of a Take that has exited to be read."""
        self._reader.join(5)

    def alive(self) -> bool:
        raise NotImplementedError

    def kill(self) -> None:
        raise NotImplementedError

    def wait(self, timeout: float) -> tuple[bool, str | None]:
        """(finished ok, error text)."""
        raise NotImplementedError


def _api_take(engine: SpikeEngine, request, precision, steps, output_dir, parent_pid, conn):
    threading.Thread(target=_exit_when_orphaned, args=(parent_pid,), daemon=True).start()

    def on_event(event: StageEvent) -> None:
        if event.kind in ("start", "enter"):
            conn.send(("stage", event.stage))

    try:
        engine.load(precision)
        engine.run(request, steps, Path(output_dir), on_event=on_event)
        conn.send(("done", None))
    except BaseException:  # noqa: BLE001 - reported to the measuring process
        conn.send(("error", traceback.format_exc()))
    finally:
        conn.close()


class _ApiTake(_Take):
    def __init__(self, engine: SpikeEngine, request: dict, precision: str, steps: int, output):
        super().__init__()
        context = multiprocessing.get_context("spawn")
        self._receiver, sender = context.Pipe(duplex=False)
        self._process = context.Process(
            target=_api_take,
            args=(engine, request, precision, steps, str(output), os.getpid(), sender),
        )
        self._process.start()
        sender.close()
        self._final: tuple[str, str | None] | None = None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        try:
            while True:
                kind, value = self._receiver.recv()
                if kind == "stage":
                    self._begin(value)
                else:
                    self._final = (kind, value)
        except (EOFError, OSError):
            pass

    def alive(self) -> bool:
        return self._process.is_alive()

    def kill(self) -> None:
        if self._process.is_alive():
            self._process.kill()
        self._process.join()

    def wait(self, timeout: float) -> tuple[bool, str | None]:
        self._process.join(timeout)
        if self._process.is_alive():
            self.kill()
            return False, f"timed out after {timeout:g}s and was killed"
        self._reader.join(5)
        if self._final is None:
            return False, f"exited with code {self._process.exitcode} without reporting"
        kind, text = self._final
        return kind == "done", text


class _CliTake(_Take):
    def __init__(self, command: CliTake):
        super().__init__(command.stage_markers)
        self._tail: deque[str] = deque(maxlen=TAIL_LINES)
        self._process = subprocess.Popen(
            command.argv,
            env={**os.environ, "PYTHONUNBUFFERED": "1", **command.env},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self._process.stdout is not None
        for chunk in self._process.stdout:
            for line in chunk.replace("\r", "\n").splitlines():
                if not line.strip():
                    continue
                self._tail.append(line)
                for stage, marker in self.stage_markers.items():
                    if marker in line:
                        self._begin(stage)

    def alive(self) -> bool:
        return self._process.poll() is None

    def kill(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
        self._process.wait()

    def wait(self, timeout: float) -> tuple[bool, str | None]:
        try:
            code = self._process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            return False, f"timed out after {timeout:g}s and was killed"
        self._reader.join(5)
        if code == 0:
            return True, None
        return False, f"exit code {code}:\n" + "\n".join(self._tail)


Launch = Callable[[Path], _Take]


def _launchers(engine: SpikeEngine, request: dict, precision: str, steps: int, run_dir: Path):
    def api(output: Path) -> _Take:
        return _ApiTake(engine, request, precision, steps, output)

    def cli(output: Path) -> _Take:
        command = engine.take_command(request, output, precision, steps, run_dir / "cli-request")
        return _CliTake(command)

    return {"api": api, "cli": cli if hasattr(engine, "take_command") else None}


def _cleanups(output: Path) -> list[tuple[str, Callable[[], list[Path]]]]:
    """Cleanups to try, smallest first; each lists the paths it would remove."""
    return [
        (
            "files named after the output directory next to it",
            lambda: sorted(output.parent.glob(glob.escape(output.name) + ".*")),
        ),
        ("the output directory", lambda: [output] if output.exists() else []),
    ]


def _rerun(launch: Launch, output: Path, root: Path, killed: dict, removed: list[str]) -> dict:
    start = time.monotonic()
    take = launch(output)
    try:
        ok, error = take.wait(TAKE_TIMEOUT_SECONDS)
    finally:
        take.kill()
    after = _tree(root)
    files = _listing(after)
    attempt: dict = {
        "removed": removed,
        "outcome": "ok" if ok else "failed",
        "seconds": time.monotonic() - start,
        "files_after": files,
    }
    if error is not None:
        attempt["error"] = error
    if ok:
        take_files = [f for f in files if f["path"].startswith(f"{output.name}/")]
        attempt["looks_complete"] = looks_complete(take_files)
        attempt["stale_files_kept"] = sorted(
            path for path, stat in killed.items() if after.get(path) == stat
        )
    return attempt


def _remove(paths: list[Path], root: Path) -> list[str]:
    removed = []
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(str(path.relative_to(root)))
    return removed


def _kill_then_rerun(launch: Launch, root: Path, after: float) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    output = root / OUTPUT_NAME
    take = launch(output)
    try:
        if not take.wait_for_stage(KILL_STAGE, TAKE_TIMEOUT_SECONDS):
            ok, error = take.wait(0.1)
            if ok:
                raise RuntimeError(
                    f"the Take finished before it was killed; {KILL_STAGE} was never seen to begin"
                )
            raise RuntimeError(f"the Take never reached {KILL_STAGE}: {error}")
        entered = time.monotonic()
        while time.monotonic() - entered < after:
            if not take.alive():
                raise RuntimeError(f"the Take finished before it was killed in {KILL_STAGE}")
            time.sleep(0.02)
        if not take.alive():
            raise RuntimeError(f"the Take finished before it was killed in {KILL_STAGE}")
        killed_in = take.begun[-1]
        take.kill()
        killed_after = time.monotonic() - entered
    finally:
        take.kill()

    killed = _tree(root)
    record: dict = {
        "outcome": "ok",
        "killed_in": killed_in,
        "killed_after_stage_start_seconds": killed_after,
        "stages_begun": list(take.begun),
        "leftover_files": _listing(killed),
        "resource_files_left": _resource_files(killed),
    }
    attempt = _rerun(launch, output, root, killed, [])
    record["rerun_without_cleanup"] = attempt
    record["reruns_after_cleanup"] = []
    removed_total: list[str] = []
    for _, targets in _cleanups(output):
        if attempt["outcome"] == "ok":
            break
        found = targets()
        if not found:
            continue
        removed = _remove(found, root)
        removed_total += removed
        attempt = _rerun(launch, output, root, killed, removed)
        record["reruns_after_cleanup"].append(attempt)
    if record["rerun_without_cleanup"]["outcome"] == "ok":
        record["cleanup_rule"] = "none needed"
    elif attempt["outcome"] == "ok":
        record["cleanup_rule"] = "remove " + ", ".join(removed_total)
    else:
        record["cleanup_rule"] = "no cleanup tried made a rerun work"
    return record


def measure(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    after = params.get("kill_after_seconds", KILL_AFTER_SECONDS)
    launchers = _launchers(engine, request, params["precision"], params["steps"], run_dir)
    record: dict = {"kill_stage": KILL_STAGE, "kill_after_seconds": after}
    for name in PATHS:
        launch = launchers[name]
        if launch is None:
            record[name] = {"outcome": "unsupported", "error": "the Engine has no command line"}
            continue
        try:
            record[name] = _kill_then_rerun(launch, run_dir / name, after)
        except Unsupported as error:
            record[name] = {"outcome": "unsupported", "error": f"Unsupported: {error}"}
        except Exception:  # noqa: BLE001 - one path's failure is that path's outcome
            record[name] = {"outcome": "failed", "error": traceback.format_exc()}
    return record


def summarize(runs: list[dict], stem: str) -> dict:
    [run] = runs
    summary: dict = {
        "cleanup_rules": {name: run[name].get("cleanup_rule") for name in PATHS},
        "resource_files": {},
    }
    for name in PATHS:
        record = run[name]
        if record["outcome"] != "ok":
            summary["resource_files"][name] = None
            continue
        attempts = [record["rerun_without_cleanup"], *record["reruns_after_cleanup"]]
        completed = [a for a in attempts if a["outcome"] == "ok"]
        summary["resource_files"][name] = {
            "left_after_kill": record["resource_files_left"],
            "written_by_completed_rerun": _resource_files(
                f["path"] for f in completed[-1]["files_after"]
            )
            if completed
            else None,
        }
    failed = [name for name in PATHS if run[name]["outcome"] == "failed"]
    if failed:
        summary["outcome"] = "failed"
        summary["error"] = "\n".join(f"{name}: {run[name]['error']}" for name in failed)
    return summary
