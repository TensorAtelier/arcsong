"""Variations, stars and the schema v2 migration, through the fake Engine."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.db import Store
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
