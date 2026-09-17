"""Stopping, killing and restarting the server; model load failures; Takes saved at shutdown."""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.engine import EngineSpec
from tests.test_app import FAKE, wait_for


def fake(**kwargs):
    return EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.05, **kwargs})


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def children(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
    return [int(p) for p in out.split()]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True,
                          text=True).stdout.strip() not in ("", "Z")  # fmt: skip


@pytest.fixture
def server(tmp_path):
    """A real `songloom serve --engine fake` process; yields (process, port)."""
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "songloom.cli", "serve", "--engine", "fake",
         "--port", str(port), "--data", str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    deadline = time.monotonic() + 30
    while True:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs", timeout=1)
            break
        except OSError:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.2)
    while not children(process.pid):  # the worker process
        time.sleep(0.1)
    yield process, port
    if process.poll() is None:
        process.kill()
        process.wait()


def test_the_server_stops_promptly_with_an_event_stream_open(server):
    process, port = server
    worker = children(process.pid)[0]
    stream = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=30)
    assert stream.readline().startswith(b": connected")

    process.send_signal(signal.SIGTERM)

    process.wait(timeout=8)
    deadline = time.monotonic() + 5
    while alive(worker):
        assert time.monotonic() < deadline, "worker outlived the server"
        time.sleep(0.1)
    stream.close()


def test_a_killed_servers_worker_exits_on_its_own(server):
    process, _ = server
    worker = children(process.pid)[0]

    process.kill()
    process.wait()

    deadline = time.monotonic() + 5
    while alive(worker):
        assert time.monotonic() < deadline, "orphaned worker kept running"
        time.sleep(0.1)


def test_a_model_that_cannot_load_fails_jobs_with_the_reason_and_does_not_spin(tmp_path):
    spec = fake(fail_load="weights not found at /nowhere")
    with TestClient(create_app(spec, tmp_path, load_retry=0.5)) as client:
        runner = client.app.state.runner
        jobs = [client.post("/api/jobs", json={"style": s}).json() for s in "ab"]

        failed = [wait_for(client, j["id"]) for j in jobs]
        time.sleep(1.5)  # nothing queued: no further attempts to load

        assert [j["status"] for j in failed] == ["failed", "failed"]
        assert all("The model could not load: RuntimeError: weights not found" in j["error"]
                   for j in failed)  # fmt: skip
        assert runner.worker_starts <= 3


def test_job_snapshots_after_a_restart_outrank_those_from_before(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as client:
        job = wait_for(client, client.post("/api/jobs", json={"style": "a"}).json()["id"])
        before = client.get(f"/api/jobs/{job['id']}").json()["seq"]
    with TestClient(create_app(FAKE, tmp_path)) as client:
        after = client.get(f"/api/jobs/{job['id']}").json()["seq"]
    assert after > before


def test_a_take_that_finishes_while_the_server_stops_is_kept(tmp_path):
    # The Engine ignores the stop request (like a Take already saving) and finishes in ~0.8 s.
    spec = fake(stage_seconds=0.2, ignore_cancel=True)
    with TestClient(create_app(spec, tmp_path)) as client:
        job = client.post("/api/jobs", json={"style": "a"}).json()
        wait_for(client, job["id"], statuses=("running",))
    with TestClient(create_app(FAKE, tmp_path)) as client:
        kept = client.get(f"/api/jobs/{job['id']}").json()
        assert kept["status"] == "done", kept["error"]
        assert client.get(f"/api/songs/{kept['song_id']}/audio").status_code == 200
