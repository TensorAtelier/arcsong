"""Live progress and cancel: the coalescer, yue2 stderr lines, broadcasts and cancelling jobs."""

import io
import re
import sys
import time

import pytest
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.engine import STAGES, EngineSpec
from songloom.progress import PROGRESS_PER_SECOND, Coalescer, StderrCounts, progress_line
from tests.test_app import wait_for


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_progress_is_coalesced_to_a_few_updates_per_second():
    sent, clock = [], Clock()
    emit = Coalescer(sent.append, clock)
    for token in range(1, 72):  # 71 tokens in one second, the M0 peak
        clock.now = token / 71
        emit({"type": "progress", "stage": "planning", "tokens": token})

    assert 1 <= len(sent) <= PROGRESS_PER_SECOND + 1
    assert [e["tokens"] for e in sent] == sorted(e["tokens"] for e in sent)


def test_a_held_progress_update_is_flushed_before_the_next_stage_or_outcome():
    sent, clock = [], Clock()
    emit = Coalescer(sent.append, clock)
    emit({"type": "progress", "stage": "planning", "tokens": 1})
    emit({"type": "progress", "stage": "planning", "tokens": 2})  # held: same instant
    emit({"type": "stage", "stage": "semantic generation"})
    emit({"type": "progress", "stage": "semantic generation", "tokens": 5})  # held
    emit({"type": "done"})

    assert sent == [
        {"type": "progress", "stage": "planning", "tokens": 1},
        {"type": "progress", "stage": "planning", "tokens": 2},
        {"type": "stage", "stage": "semantic generation"},
        {"type": "progress", "stage": "semantic generation", "tokens": 5},
        {"type": "done"},
    ]


@pytest.mark.parametrize("tty", [False, True])
def test_yue2_progress_lines_give_count_and_total(tty):
    from yue2 import progress as yue2_progress

    class Stream(io.StringIO):
        def isatty(self):
            return tty

    stream = Stream()
    reporter = yue2_progress.Progress(stream=stream, refresh_interval=0.25)
    reporter._interval = 0.0
    with reporter.stage("Synthesizing audio", unit="steps") as stage:
        stage.update(3, total=8)
        stage.update(8, total=8)
    reporter.close()
    parsed = {progress_line(line) for line in re.split(r"[\r\n]", stream.getvalue())}

    assert ("Synthesizing audio", 3, 8) in parsed
    assert ("Synthesizing audio", 8, 8) in parsed
    assert progress_line("[YuE2] Running Loading acoustic model: elapsed 5.0s") is None


def test_stderr_counts_pass_every_write_through_and_restore_stderr(monkeypatch):
    real = io.StringIO()
    monkeypatch.setattr(sys, "stderr", real)
    counts = []
    with StderrCounts(lambda done, total: counts.append((done, total))):
        sys.stderr.write("[YuE2] Running Synthesizing audio: 3/8 st")
        sys.stderr.write("eps (38%) | elapsed 12.3s\nother text\n")
    assert sys.stderr is real
    assert counts == [(3, 8)]
    assert real.getvalue().endswith("other text\n")


def collect_until_finished(subscription, job_id, timeout=30):
    messages, deadline = [], time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = subscription.get(timeout=timeout)["job"]
        if job["id"] != job_id:
            continue
        messages.append(job)
        if job["status"] in ("done", "failed", "cancelled"):
            return messages
    raise AssertionError("job never finished")


def test_job_changes_are_broadcast_with_stages_and_progress(tmp_path):
    spec = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.5})
    with TestClient(create_app(spec, tmp_path)) as client:
        subscription = client.app.state.runner.broadcaster.subscribe()
        job = client.post("/api/jobs", json={"style": "x", "steps": 8}).json()

        messages = collect_until_finished(subscription, job["id"])

    assert messages[-1]["status"] == "done"
    live = [m["live"] for m in messages if m["live"]]
    stages = [s for s in dict.fromkeys(entry["stage"] for entry in live) if s]
    assert stages == list(STAGES)
    tokens = [e["tokens"] for e in live if e["stage"] == "planning" and "tokens" in e]
    assert tokens and tokens == sorted(tokens)
    steps = [(e["completed"], e["total"]) for e in live if "total" in e]
    assert steps and all(total == 8 for _, total in steps)
    # 4 half-second Stages at a few updates a second: well under the fake's 40+ raw signals.
    assert len(live) <= 4 * (PROGRESS_PER_SECOND + 3)


def test_a_running_job_is_cancelled_promptly_and_the_next_job_runs(tmp_path):
    spec = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 5.0})
    with TestClient(create_app(spec, tmp_path)) as client:
        first = client.post("/api/jobs", json={"style": "a"}).json()
        second = client.post("/api/jobs", json={"style": "b"}).json()
        wait_for(client, first["id"], statuses=("running",))
        while not (client.get(f"/api/jobs/{first['id']}").json()["live"] or {}).get("stage"):
            time.sleep(0.02)

        asked = time.monotonic()
        assert client.post(f"/api/jobs/{first['id']}/cancel").status_code == 200
        cancelled = wait_for(client, first["id"])
        latency = time.monotonic() - asked

        assert cancelled["status"] == "cancelled" and cancelled["song_id"] is None
        assert latency < 1.0
        assert wait_for(client, second["id"], statuses=("running",))["status"] == "running"
        client.post(f"/api/jobs/{second['id']}/cancel")
        assert wait_for(client, second["id"])["status"] == "cancelled"


def test_a_queued_job_is_cancelled_without_running(tmp_path):
    spec = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.2})
    with TestClient(create_app(spec, tmp_path)) as client:
        first = client.post("/api/jobs", json={"style": "a"}).json()
        second = client.post("/api/jobs", json={"style": "b"}).json()

        assert client.post(f"/api/jobs/{second['id']}/cancel").json()["status"] == "cancelled"

        assert wait_for(client, first["id"])["status"] == "done"
        second = client.get(f"/api/jobs/{second['id']}").json()
        assert second["status"] == "cancelled" and second["started_at"] is None


def test_cancelling_a_finished_or_unknown_job_is_refused(tmp_path):
    spec = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.01})
    with TestClient(create_app(spec, tmp_path)) as client:
        job = wait_for(client, client.post("/api/jobs", json={"style": "a"}).json()["id"])
        assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409
        assert client.post("/api/jobs/999/cancel").status_code == 404
