"""Variations, stars and the schema v2 migration, through the fake Engine."""

import json
import os
import sqlite3

import numpy as np
import pytest
import soundfile
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.db import Store
from songloom.engine import EngineSpec
from tests.test_app import FAKE, wait_for

REQUEST = {"style": "indie pop", "lyrics": "[Verse]\nhello", "steps": 8}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as c:
        yield c


def test_a_group_queues_count_jobs_that_differ_only_in_seed(client):
    created = client.post("/api/groups", json={**REQUEST, "count": 4})

    assert created.status_code == 201
    jobs = created.json()
    assert len(jobs) == 4
    ids = [j["id"] for j in jobs]
    assert ids == sorted(ids)
    assert {j["group_id"] for j in jobs} == {ids[0]}
    assert len({j["request"]["seed"] for j in jobs}) == 4
    for job in jobs:
        request = {k: v for k, v in job["request"].items() if k != "seed"}
        assert request == {**REQUEST, "mode": "full", "precision": "8bit"}

    done = [wait_for(client, i) for i in ids]
    assert [j["status"] for j in done] == ["done"] * 4
    songs = client.get("/api/songs").json()
    assert {s["group_id"] for s in songs} == {ids[0]}


def test_a_given_seed_counts_up_across_the_group(client):
    jobs = client.post("/api/groups", json={**REQUEST, "count": 3, "seed": 2**31 - 2}).json()

    assert [j["request"]["seed"] for j in jobs] == [2**31 - 2, 2**31 - 1, 0]


@pytest.mark.parametrize("count", [0, 1, 9])
def test_a_group_needs_two_to_eight_takes(client, count):
    assert client.post("/api/groups", json={**REQUEST, "count": count}).status_code == 422


def test_a_group_is_listed_by_its_id_and_single_jobs_have_no_group(client):
    single = client.post("/api/jobs", json=REQUEST).json()
    jobs = client.post("/api/groups", json={**REQUEST, "count": 2}).json()

    group = client.get(f"/api/groups/{jobs[0]['group_id']}")

    assert single["group_id"] is None
    assert [j["id"] for j in group.json()] == [j["id"] for j in jobs]
    assert all("live" in j and "seq" in j for j in group.json())
    assert client.get(f"/api/groups/{single['id']}").status_code == 404


def test_starring_a_song_round_trips_and_is_broadcast(client):
    job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])
    song_id = job["song_id"]
    subscription = client.app.state.runner.broadcaster.subscribe()

    starred = client.put(f"/api/songs/{song_id}/star", json={"starred": True})

    assert starred.status_code == 200
    assert starred.json()["starred"] is True and starred.json()["bytes"] > 0
    assert client.get("/api/songs").json()[0]["starred"] is True
    assert client.get(f"/api/jobs/{job['id']}").json()["starred"] is True
    messages = []
    while not subscription.empty():
        messages.append(subscription.get())
    song_messages = [m for m in messages if m["type"] == "song"]
    assert song_messages and song_messages[0]["song"]["starred"] is True
    assert any(m["type"] == "job" and m["job"]["starred"] for m in messages)

    client.put(f"/api/songs/{song_id}/star", json={"starred": False})
    assert client.get("/api/songs").json()[0]["starred"] is False
    assert client.put("/api/songs/999/star", json={"starred": True}).status_code == 404


def test_a_star_survives_a_restart(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as client:
        job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])
        client.put(f"/api/songs/{job['song_id']}/star", json={"starred": True})
    with TestClient(create_app(FAKE, tmp_path)) as client:
        assert client.get("/api/songs").json()[0]["starred"] is True


V1_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL, request_json TEXT NOT NULL,
    created_at REAL NOT NULL, started_at REAL, finished_at REAL, error TEXT, song_id INTEGER
);
CREATE TABLE songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id),
    dir TEXT NOT NULL, audio_path TEXT NOT NULL, audio_seconds REAL, created_at REAL NOT NULL
);
PRAGMA user_version = 1;
"""


def test_a_v1_database_migrates_with_its_rows_intact(tmp_path):
    path = tmp_path / "songloom.db"
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    conn.execute(
        "INSERT INTO jobs (status, request_json, created_at, song_id) VALUES ('done', ?, 1, 1)",
        (json.dumps({**REQUEST, "seed": 5}),),
    )
    conn.execute(
        "INSERT INTO songs (job_id, dir, audio_path, audio_seconds, created_at) "
        "VALUES (1, '/d', '/d/audio.flac', 2.5, 2)"
    )
    conn.commit()
    conn.close()

    store = Store(path)
    [song] = store.list_songs()
    job = store.get_job(1)
    version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    store.close()
    Store(path).close()  # opening a v2 database again is a no-op

    assert version == 2
    assert song["request"]["seed"] == 5 and song["audio_seconds"] == 2.5
    assert song["starred"] is False and song["group_id"] is None
    assert job["status"] == "done" and job["source_song_id"] is None


# --- Finalize ---------------------------------------------------------------------------------


def make_draft(client, **request):
    body = {**REQUEST, **request}
    return wait_for(client, client.post("/api/jobs", json=body).json()["id"])


def test_finalize_queues_a_32_step_final_that_runs_only_synthesis_and_decoding(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.3})
    with TestClient(create_app(slow, tmp_path)) as client:
        draft = make_draft(client, seed=41)
        subscription = client.app.state.runner.broadcaster.subscribe()

        created = client.post(f"/api/songs/{draft['song_id']}/finalize")
        assert created.status_code == 201
        final = created.json()
        done = wait_for(client, final["id"])
        songs = client.get("/api/songs").json()

    assert final["source_song_id"] == draft["song_id"]
    assert final["request"] == {**draft["request"], "steps": 32}
    assert done["status"] == "done", done["error"]
    stages = []
    while not subscription.empty():
        message = subscription.get()
        if message["type"] == "job" and message["job"]["id"] == final["id"]:
            stage = (message["job"]["live"] or {}).get("stage")
            if stage and stage not in stages:
                stages.append(stage)
    assert stages == ["synthesis", "decoding"]
    song = next(s for s in songs if s["id"] == done["song_id"])
    assert song["source_song_id"] == draft["song_id"]
    # The fake's tone depends on the seed, so the Final sounds like its Draft.
    draft_audio = (tmp_path / "songs" / str(draft["id"]) / "audio.wav").read_bytes()
    final_audio = (tmp_path / "songs" / str(final["id"]) / "audio.wav").read_bytes()
    assert final_audio == draft_audio


def test_finalize_is_refused_for_a_full_quality_take_and_a_second_final(client):
    full = make_draft(client, steps=32)
    draft = make_draft(client)

    assert client.post(f"/api/songs/{full['song_id']}/finalize").status_code == 409
    assert client.post("/api/songs/999/finalize").status_code == 404
    first = client.post(f"/api/songs/{draft['song_id']}/finalize").json()
    again = client.post(f"/api/songs/{draft['song_id']}/finalize")
    assert again.status_code == 409 and f"#{first['id']}" in again.json()["detail"]
    wait_for(client, first["id"])
    assert client.post(f"/api/songs/{draft['song_id']}/finalize").status_code == 409


def test_a_cancelled_final_can_be_retried(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.5})
    with TestClient(create_app(slow, tmp_path)) as client:
        draft = make_draft(client)
        blocker = client.post("/api/jobs", json=REQUEST).json()  # keeps the Final queued
        final = client.post(f"/api/songs/{draft['song_id']}/finalize").json()
        client.post(f"/api/jobs/{final['id']}/cancel")
        retried = client.post(f"/api/songs/{draft['song_id']}/finalize")
        client.post(f"/api/jobs/{blocker['id']}/cancel")

    assert retried.status_code == 201


def test_a_final_whose_draft_was_deleted_before_it_ran_fails_and_the_queue_moves_on(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.3})
    with TestClient(create_app(slow, tmp_path)) as client:
        draft = make_draft(client)
        blocker = client.post("/api/jobs", json=REQUEST).json()
        final = client.post(f"/api/songs/{draft['song_id']}/finalize").json()
        after = client.post("/api/jobs", json=REQUEST).json()
        client.delete(f"/api/songs/{draft['song_id']}")

        failed = wait_for(client, final["id"])
        wait_for(client, blocker["id"])
        next_job = wait_for(client, after["id"])

    assert failed["status"] == "failed" and "Draft was deleted" in failed["error"]
    assert next_job["status"] == "done"


# --- Waveform peaks ---------------------------------------------------------------------------


def test_peaks_have_the_requested_buckets_within_range_and_the_duration(client):
    job = make_draft(client, seed=3)

    peaks = client.get(f"/api/songs/{job['song_id']}/peaks?buckets=100").json()

    assert peaks["duration"] == 1.0
    assert len(peaks["min"]) == len(peaks["max"]) == 100
    assert all(-1 <= lo <= hi <= 1 for lo, hi in zip(peaks["min"], peaks["max"], strict=True))
    assert max(peaks["max"]) > 0.2
    assert client.get("/api/songs/999/peaks").status_code == 404
    assert client.get(f"/api/songs/{job['song_id']}/peaks?buckets=4").status_code == 422


def test_peaks_follow_the_audio_and_variations_differ(client, tmp_path):
    jobs = client.post("/api/groups", json={**REQUEST, "count": 2, "seed": 10}).json()
    songs = [wait_for(client, j["id"])["song_id"] for j in jobs]
    first, second = (client.get(f"/api/songs/{s}/peaks?buckets=50").json() for s in songs)
    assert first["max"] != second["max"]

    # A quiet file after a loud one at the same path: the cache notices the rewrite.
    path = tmp_path / "songs" / str(jobs[0]["id"]) / "audio.wav"
    soundfile.write(path, np.full((48_000, 2), 0.01, dtype="float32"), 48_000, subtype="PCM_16")
    os.utime(path, ns=(1, 1))
    quiet = client.get(f"/api/songs/{songs[0]}/peaks?buckets=50").json()
    assert max(quiet["max"]) == pytest.approx(0.01, abs=1e-3)


# --- Review fixes -----------------------------------------------------------------------------


def test_an_interrupted_migration_leaves_the_v1_schema_untouched(tmp_path):
    path = tmp_path / "songloom.db"
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    # The last ALTER will fail on this column, after the first two have run.
    conn.execute("ALTER TABLE songs ADD COLUMN starred INTEGER")
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.OperationalError, match="duplicate column"):
        Store(path)

    conn = sqlite3.connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert "group_id" not in columns and "source_song_id" not in columns
    assert version == 1


def test_starring_a_song_deleted_mid_request_is_a_404(client, monkeypatch):
    job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])
    store = client.app.state.store
    monkeypatch.setattr(store, "get_song", lambda song_id: None)  # deleted after the UPDATE

    assert (
        client.put(f"/api/songs/{job['song_id']}/star", json={"starred": True}).status_code == 404
    )


def test_the_mlx_final_of_a_deleted_draft_says_so_before_loading_the_model(tmp_path):
    from songloom.mlx_engine import MlxYueEngine

    engine = MlxYueEngine(models=tmp_path / "models")
    request = {**REQUEST, "seed": 1, "mode": "full", "precision": "8bit", "steps": 32}

    with pytest.raises(FileNotFoundError, match="its Draft was deleted"):
        engine.finalize(tmp_path / "gone", request, tmp_path / "out", lambda: False, lambda e: None)
    assert engine._pipe is None  # no model load was attempted
