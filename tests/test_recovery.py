"""Worker crashes, cancels the Engine ignores, and restarting the server mid-job."""

import json
import time

from fastapi.testclient import TestClient

from arcsong.app import create_app
from arcsong.db import Store
from arcsong.engine import EngineSpec
from tests.test_app import FAKE, wait_for


def fake(**kwargs):
    return EngineSpec("arcsong.fake_engine:FakeEngine", {"stage_seconds": 0.05, **kwargs})


def test_a_worker_crash_fails_the_job_and_the_next_job_runs_on_a_new_worker(tmp_path):
    # Every job crashes in synthesis, so both jobs exercise a fresh worker.
    with TestClient(create_app(fake(crash_in="synthesis"), tmp_path)) as client:
        first = client.post("/api/jobs", json={"style": "a"}).json()
        second = client.post("/api/jobs", json={"style": "b"}).json()

        crashed = wait_for(client, first["id"])
        after = wait_for(client, second["id"])

        assert crashed["status"] == "failed"
        assert "exited unexpectedly (code 137)" in crashed["error"]
        assert after["status"] == "failed" and after["started_at"] >= crashed["finished_at"]
        assert client.app.state.runner.worker_starts == 3
        assert not (tmp_path / "songs" / str(first["id"])).exists()


def test_a_job_that_ignores_cancel_is_killed_after_the_grace_period(tmp_path):
    spec = fake(stage_seconds=30, ignore_cancel=True)
    with TestClient(create_app(spec, tmp_path, cancel_grace=0.5)) as client:
        job = client.post("/api/jobs", json={"style": "a"}).json()
        wait_for(client, job["id"], statuses=("running",))
        asked = time.monotonic()
        client.post(f"/api/jobs/{job['id']}/cancel")

        cancelled = wait_for(client, job["id"])

        assert cancelled["status"] == "cancelled"
        assert 0.5 <= time.monotonic() - asked < 5
        assert client.app.state.runner.worker_starts == 2


def test_on_start_running_jobs_fail_and_queued_jobs_run_in_order(tmp_path):
    store = Store(tmp_path / "arcsong.db")
    interrupted = store.create_job({"style": "was running", "steps": 8})
    store.mark_running(interrupted["id"])
    waiting = [store.create_job({"style": f"queued {i}", "steps": 8}) for i in range(2)]
    store.close()
    leftover = tmp_path / "songs" / str(interrupted["id"])
    leftover.mkdir(parents=True)
    (leftover / "half-written.npy").write_bytes(b"x")

    with TestClient(create_app(FAKE, tmp_path)) as client:
        failed = client.get(f"/api/jobs/{interrupted['id']}").json()
        done = [wait_for(client, j["id"]) for j in waiting]

    assert failed["status"] == "failed"
    assert "server stopped" in failed["error"]
    assert not leftover.exists()
    assert [j["status"] for j in done] == ["done", "done"]
    assert done[0]["finished_at"] <= done[1]["started_at"]
    assert json.dumps(done[0]["request"])
