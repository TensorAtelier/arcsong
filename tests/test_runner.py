"""Runner guards a multi-hour matrix needs: per-run timeout and no orphaned GPU child."""

import json
import os
import signal
import subprocess
import sys
import time
from functools import partial
from pathlib import Path

from spike import cli
from spike.fake import FakeEngine

PARENT_SCRIPT = """
import sys
from functools import partial
from spike import cli
from spike.fake import FakeEngine
cli.ENGINES["fake"] = lambda args: partial(FakeEngine, stage_seconds=60)
cli.main(["timing", "--engine", "fake", "--precisions", "bf16", "--steps", "8", "--runs", "1",
          "--results-dir", sys.argv[1], "--runs-dir", sys.argv[2]])
"""


def test_a_run_exceeding_the_timeout_is_killed_and_recorded_as_failed(tmp_path, monkeypatch):
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, stage_seconds=30))
    start = time.monotonic()

    code = cli.main(
        ["timing", "--engine", "fake", "--precisions", "bf16", "--steps", "8", "--runs", "1",
         "--timeout", "2", "--results-dir", str(tmp_path / "results"),
         "--runs-dir", str(tmp_path / "runs")]
    )  # fmt: skip

    assert code == 0
    assert time.monotonic() - start < 20
    result = json.loads((tmp_path / "results" / "timing-fake-song-bf16-8.json").read_text())
    assert result["outcome"] == "failed"
    assert "timed out after 2" in result["error"]
    [run] = result["runs"]
    assert run["outcome"] == "failed"


def _children(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
    return [int(line) for line in out.split()]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def test_killing_the_harness_also_stops_the_measurement_child(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    parent = subprocess.Popen(
        [sys.executable, "-c", PARENT_SCRIPT, str(tmp_path / "results"), str(tmp_path / "runs")],
        cwd=repo,
        stdout=subprocess.DEVNULL,
    )
    try:
        assert _wait(lambda: _children(parent.pid), 20), "measurement child never started"
        children = _children(parent.pid)

        parent.send_signal(signal.SIGKILL)
        parent.wait()

        assert _wait(lambda: not any(_alive(pid) for pid in children), 10), children
    finally:
        parent.kill()
        for pid in _children(parent.pid):
            os.kill(pid, signal.SIGKILL)
