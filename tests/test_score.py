"""Score-only runs, Score checking and rendering from an edited Score, through the fake Engine."""

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.db import Store
from songloom.engine import EngineSpec
from songloom.fake_engine import fake_score
from tests.test_app import FAKE, wait_for
from tests.test_variations import V1_SCHEMA

REQUEST = {"style": "indie pop", "lyrics": "[Verse]\nhello", "steps": 8}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as c:
        yield c


def test_a_score_job_writes_abc_and_makes_no_song(client):
    created = client.post("/api/scores", json={"style": "indie pop", "lyrics": "[Verse]\nhi"})

    assert created.status_code == 201
    job = created.json()
    assert job["kind"] == "score"
    done = wait_for(client, job["id"])
    assert done["status"] == "done" and done["song_id"] is None
    assert client.get("/api/songs").json() == []

    score = client.get(f"/api/scores/{job['id']}").json()
    assert score["abc"] == fake_score(done["request"])
    assert score["report"]["bpm"] > 0
    assert score["report"]["voices"]["Vocal"]["sounding_notes"] == 16
    assert score["report"]["voices"]["Vocal"]["chords"] == 4
    assert score["job"]["id"] == job["id"]


def test_a_score_job_reports_planning_and_the_queue_moves_on(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.3})
    with TestClient(create_app(slow, tmp_path)) as client:
        subscription = client.app.state.runner.broadcaster.subscribe()
        score_job = client.post("/api/scores", json={"style": "pop"}).json()
        take = client.post("/api/jobs", json=REQUEST).json()

        assert wait_for(client, score_job["id"])["status"] == "done"
        assert wait_for(client, take["id"])["status"] == "done"

    stages = []
    while not subscription.empty():
        message = subscription.get()
        if message["type"] == "job" and message["job"]["id"] == score_job["id"]:
            stage = (message["job"]["live"] or {}).get("stage")
            if stage and stage not in stages:
                stages.append(stage)
    assert stages == ["planning"]


def test_a_queued_score_job_can_be_cancelled(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.5})
    with TestClient(create_app(slow, tmp_path)) as client:
        client.post("/api/jobs", json=REQUEST)  # keeps the Score job queued
        score_job = client.post("/api/scores", json={"style": "pop"}).json()

        assert client.post(f"/api/jobs/{score_job['id']}/cancel").status_code == 200
        cancelled = wait_for(client, score_job["id"])

    assert cancelled["status"] == "cancelled"
    assert cancelled["score"] is None


def test_a_score_run_refuses_the_mode_that_writes_none(client):
    assert client.post("/api/scores", json={"style": "pop", "mode": "off"}).status_code == 422
    assert client.get("/api/scores/999").status_code == 404
    take = client.post("/api/jobs", json=REQUEST).json()
    assert client.get(f"/api/scores/{take['id']}").status_code == 404  # not a Score job


# --- checking ---------------------------------------------------------------------------------


def edit_first_vocal_note(abc: str, note: str) -> str:
    """Change the Score's first sounding note; line 9 is the Vocal music line."""
    lines = abc.splitlines(keepends=True)
    music = lines[9]
    start = music.index("8") - 1  # the note letter before its first duration
    lines[9] = music[:start] + note + music[start + 1 :]
    return "".join(lines)


def test_checking_reports_a_valid_score_and_what_an_edit_changed(client):
    original = fake_score({"seed": 7})
    first = original.splitlines()[9][original.splitlines()[9].index("8") - 1]
    edited = edit_first_vocal_note(original, "G" if first != "G" else "A")

    checked = client.post("/api/score/check", json={"abc": edited, "original": original}).json()

    assert checked["ok"] is True and checked["error"] is None
    assert checked["report"]["voices"]["Vocal"]["sounding_notes"] == 16
    assert checked["diff"]["match"] is False
    assert any("Vocal" in d for d in checked["diff"]["differences"])


def test_checking_an_unchanged_score_matches_and_an_invalid_one_says_why(client):
    original = fake_score({"seed": 3})

    same = client.post("/api/score/check", json={"abc": original, "original": original}).json()
    broken = client.post("/api/score/check", json={"abc": "X:1\nT:\nnot a score"}).json()

    assert same["diff"]["match"] is True
    assert broken["ok"] is False and broken["report"] is None
    assert "Incomplete native two-voice ABC" in broken["error"]


def test_chords_can_be_stripped_and_a_broken_score_is_refused(client):
    original = fake_score({"seed": 5})
    assert '"' in original  # the fake writes chord symbols on the Vocal voice

    stripped = client.post("/api/score/strip-chords", json={"abc": original}).json()["abc"]
    refused = client.post("/api/score/strip-chords", json={"abc": "nope"})

    assert (
        client.post("/api/score/check", json={"abc": stripped}).json()["report"]["voices"]["Vocal"][
            "chords"
        ]
        == 0
    )
    unchanged = client.post("/api/score/check", json={"abc": stripped, "original": original}).json()
    assert unchanged["ok"] is True and unchanged["diff"]["match"] is True
    assert refused.status_code == 422


def test_a_takes_score_is_served_from_its_directory(client):
    job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])

    score = client.get(f"/api/songs/{job['song_id']}/score").json()

    assert score["abc"] == fake_score(job["request"])
    assert score["report"]["voices"]["Ins"]["sounding_notes"] == 16
    assert client.get("/api/songs/999/score").status_code == 404


def test_a_take_without_planning_has_no_score(client):
    job = wait_for(client, client.post("/api/jobs", json={**REQUEST, "mode": "off"}).json()["id"])

    assert client.get(f"/api/songs/{job['song_id']}/score").status_code == 404


# --- rendering from a Score -------------------------------------------------------------------


def test_a_take_rendered_from_an_edited_score_skips_planning_and_keeps_it(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.3})
    edited = fake_score({"seed": 7}).replace("Q:1/4=97", "Q:1/4=120")
    with TestClient(create_app(slow, tmp_path)) as client:
        subscription = client.app.state.runner.broadcaster.subscribe()
        job = client.post("/api/jobs", json={**REQUEST, "abc": edited}).json()
        done = wait_for(client, job["id"])
        score = client.get(f"/api/songs/{done['song_id']}/score").json()

    assert done["status"] == "done", done["error"]
    assert done["request"]["abc"] == edited
    assert score["abc"] == edited and score["report"]["bpm"] == 120
    stages = []
    while not subscription.empty():
        message = subscription.get()
        if message["type"] == "job" and message["job"]["id"] == job["id"]:
            stage = (message["job"]["live"] or {}).get("stage")
            if stage and stage not in stages:
                stages.append(stage)
    assert stages == ["semantic generation", "synthesis", "decoding"]


def test_a_score_needs_a_planning_mode_and_some_text(client):
    abc = fake_score({"seed": 1})

    assert client.post("/api/jobs", json={**REQUEST, "abc": abc, "mode": "off"}).status_code == 422
    assert client.post("/api/jobs", json={**REQUEST, "abc": "  "}).status_code == 422
    assert client.post("/api/jobs", json={**REQUEST, "abc": abc}).status_code == 201


def test_a_v1_database_migrates_all_the_way_to_v3(tmp_path):
    path = tmp_path / "songloom.db"
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    conn.execute("INSERT INTO jobs (status, request_json, created_at) VALUES ('done', '{}', 1)")
    conn.commit()
    conn.close()

    store = Store(path)
    job = store.get_job(1)
    version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    store.close()

    assert version == 3
    assert job["kind"] == "take" and job["score"] is None


# --- Review fixes -----------------------------------------------------------------------------


def test_a_score_only_run_keeps_the_quality_for_rendering_from_it(client):
    job = client.post("/api/scores", json={"style": "pop", "steps": 32}).json()

    assert job["request"]["steps"] == 32
    draft = client.post("/api/scores", json={"style": "pop", "steps": 8}).json()
    assert draft["request"]["steps"] == 8
    assert client.post("/api/scores", json={"style": "pop"}).json()["request"]["steps"] == 32


def test_variations_never_carry_a_score(client):
    body = {**REQUEST, "count": 2, "abc": fake_score({"seed": 1})}

    assert client.post("/api/groups", json=body).status_code == 422


def test_a_running_score_job_can_be_cancelled(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 3.0})
    with TestClient(create_app(slow, tmp_path)) as client:
        job = client.post("/api/scores", json={"style": "pop"}).json()
        while not (client.get(f"/api/jobs/{job['id']}").json()["live"] or {}).get("stage"):
            time.sleep(0.02)

        assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
        cancelled = wait_for(client, job["id"])
        after = wait_for(client, client.post("/api/scores", json={"style": "pop"}).json()["id"])
        starts = client.app.state.runner.worker_starts

    assert cancelled["status"] == "cancelled" and cancelled["score"] is None
    assert after["status"] == "done" and after["score"]
    assert starts == 1  # cancelling a Score job doesn't cost a worker restart
