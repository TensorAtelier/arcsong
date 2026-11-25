"""Choosing where each song renders: several Engines in one app, each a lane with its own worker."""

import time

import pytest
from fastapi.testclient import TestClient

from arcsong.app import Engine, create_app
from arcsong.engine import EngineSpec
from arcsong.models import FakeModels

SLOW = EngineSpec("arcsong.fake_engine:FakeEngine", {"stage_seconds": 0.3})
FAST = EngineSpec("arcsong.fake_engine:FakeEngine", {"stage_seconds": 0.01})
SONG = {"style": "pop", "lyrics": "[Verse]\nhello"}


def wait_for(client, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} still {job['status']}")


def two_engines(tmp_path, spec=FAST, cloud_installed=True):
    return [
        Engine("mac", "This Mac", spec, FakeModels(tmp_path / "mac")),
        Engine("cloud", "Cloud", spec, FakeModels(tmp_path / "c", preinstalled=cloud_installed)),
    ]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(two_engines(tmp_path), tmp_path)) as c:
        yield c


def test_setup_lists_each_engine_and_a_job_runs_where_it_asks(client):
    setup = client.get("/api/setup").json()
    assert [(e["id"], e["usable"]) for e in setup["engines"]] == [("mac", True), ("cloud", True)]
    assert setup["default_engine"] == "mac" and setup["can_render"]

    cloud = client.post("/api/jobs", json={**SONG, "engine": "cloud"}).json()
    default = client.post("/api/jobs", json=SONG).json()

    assert wait_for(client, cloud["id"])["engine"] == "cloud"
    assert wait_for(client, default["id"])["engine"] == "mac"
    assert "engine" not in cloud["request"]  # where it ran isn't part of the song's recipe


def test_an_engine_not_set_up_or_unknown_is_refused(tmp_path):
    with TestClient(create_app(two_engines(tmp_path, cloud_installed=False), tmp_path)) as c:
        refused = c.post("/api/jobs", json={**SONG, "engine": "cloud"})
        assert refused.status_code == 409 and "Cloud isn't set up" in refused.json()["detail"]
        assert c.post("/api/jobs", json={**SONG, "engine": "moon"}).status_code == 422
        assert c.post("/api/scores", json={"style": "pop", "engine": "cloud"}).status_code == 409
        setup = c.get("/api/setup").json()
        assert setup["can_render"] and setup["default_engine"] == "mac"


def test_engines_render_at_the_same_time(tmp_path):
    with TestClient(create_app(two_engines(tmp_path, SLOW), tmp_path)) as c:
        mac = c.post("/api/jobs", json={**SONG, "engine": "mac"}).json()
        cloud = c.post("/api/jobs", json={**SONG, "engine": "cloud"}).json()
        mac, cloud = wait_for(c, mac["id"]), wait_for(c, cloud["id"])

    assert mac["status"] == cloud["status"] == "done"
    assert cloud["started_at"] < mac["finished_at"]  # the cloud song didn't wait for the Mac


def test_a_final_runs_on_its_drafts_engine(client):
    draft = client.post("/api/jobs", json={**SONG, "steps": 8, "engine": "cloud"}).json()
    draft = wait_for(client, draft["id"])

    final = client.post(f"/api/songs/{draft['song_id']}/finalize")

    assert final.status_code == 201
    assert wait_for(client, final.json()["id"])["engine"] == "cloud"


def test_variations_and_scores_carry_their_engine(client):
    group = client.post("/api/groups", json={**SONG, "count": 2, "engine": "cloud"}).json()
    score = client.post("/api/scores", json={"style": "pop", "engine": "cloud"}).json()

    assert [wait_for(client, j["id"])["engine"] for j in group] == ["cloud", "cloud"]
    assert wait_for(client, score["id"])["engine"] == "cloud"


def test_serve_offers_the_mac_first_only_on_apple_silicon(tmp_path, monkeypatch):
    from arcsong import cli

    monkeypatch.setattr(cli, "apple_silicon", lambda: True)
    engines, covers = cli._all_engines(tmp_path, None, True)
    assert [e.id for e in engines] == ["mlx", "modal", "runpod"]

    monkeypatch.setattr(cli, "apple_silicon", lambda: False)
    engines, covers = cli._all_engines(tmp_path, None, True)
    assert [e.id for e in engines] == ["modal", "runpod"]
    assert covers.engine_checks()[0]["status"] == "fail"
