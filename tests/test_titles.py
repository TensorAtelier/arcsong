"""Song titles: a default from the lyrics, renaming, Finals inheriting it, and schema v5."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from arcsong.app import create_app
from arcsong.db import SCHEMA_VERSION, Store, default_title
from tests.test_app import FAKE, wait_for

REQUEST = {
    "style": "English, indie pop, warm vocal",
    "lyrics": "[Verse]\nSoft morning light\n",
    "steps": 8,
}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as c:
        yield c


@pytest.mark.parametrize(
    ("style", "lyrics", "title"),
    [
        ("English, indie pop", "[Verse]\n\n  Soft morning light  \nmore", "Soft morning light"),
        ("English, indie pop", "[verse]\n[chorus]\n", "Indie pop (instrumental)"),
        ("lo-fi soul, warm Rhodes", "", "Lo-fi soul (instrumental)"),
        ("English", "", "English (instrumental)"),
        ("", "", "Untitled"),
        ("pop", "x" * 80, "x" * 59 + "…"),
    ],
)
def test_the_default_title_is_the_first_sung_line_else_the_style(style, lyrics, title):
    assert default_title({"style": style, "lyrics": lyrics}) == title


def test_songs_and_jobs_carry_the_default_title(client):
    job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])

    assert job["title"] == "Soft morning light"
    [song] = client.get("/api/songs").json()
    assert song["title"] == "Soft morning light" and song["title_set"] is False
    queued = client.post("/api/jobs", json={**REQUEST, "lyrics": ""}).json()
    assert queued["title"] == "Indie pop (instrumental)"


def test_renaming_round_trips_is_broadcast_and_resets_on_empty(client):
    job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])
    song_id = job["song_id"]
    subscription = client.app.state.runner.broadcaster.subscribe()

    renamed = client.put(f"/api/songs/{song_id}/title", json={"title": "  Morning Song "})

    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Morning Song" and renamed.json()["title_set"] is True
    assert renamed.json()["bytes"] > 0
    assert client.get(f"/api/jobs/{job['id']}").json()["title"] == "Morning Song"
    messages = []
    while not subscription.empty():
        messages.append(subscription.get())
    assert any(m["type"] == "song" and m["song"]["title"] == "Morning Song" for m in messages)
    assert any(m["type"] == "job" and m["job"]["title"] == "Morning Song" for m in messages)

    reset = client.put(f"/api/songs/{song_id}/title", json={"title": "   "})
    assert reset.json()["title"] == "Soft morning light" and reset.json()["title_set"] is False
    assert client.put("/api/songs/999/title", json={"title": "x"}).status_code == 404
    too_long = client.put(f"/api/songs/{song_id}/title", json={"title": "x" * 121})
    assert too_long.status_code == 422


def test_a_final_inherits_its_drafts_title(client):
    draft = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])
    client.put(f"/api/songs/{draft['song_id']}/title", json={"title": "Keeper"})

    final = wait_for(client, client.post(f"/api/songs/{draft['song_id']}/finalize").json()["id"])

    assert final["status"] == "done"
    songs = {s["id"]: s for s in client.get("/api/songs").json()}
    assert songs[final["song_id"]]["title"] == "Keeper"
    assert songs[final["song_id"]]["title_set"] is True


def test_a_title_survives_a_restart(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as client:
        job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])
        client.put(f"/api/songs/{job['song_id']}/title", json={"title": "Kept"})
    with TestClient(create_app(FAKE, tmp_path)) as client:
        assert client.get("/api/songs").json()[0]["title"] == "Kept"


def test_the_download_is_named_after_the_title(client):
    job = wait_for(client, client.post("/api/jobs", json=REQUEST).json()["id"])

    response = client.get(f"/api/songs/{job['song_id']}/download?format=wav")

    name = f"arcsong-{job['song_id']}-soft-morning-light.wav"
    assert name in response.headers["content-disposition"]


def test_a_v4_database_gains_titles_with_its_rows_intact(tmp_path):
    path = tmp_path / "arcsong.db"
    Store(path).close()
    conn = sqlite3.connect(path)
    # Rebuild songs as v4 had it: no title column.
    conn.executescript(
        """
        DROP TABLE songs;
        CREATE TABLE songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id),
            dir TEXT NOT NULL, audio_path TEXT NOT NULL, audio_seconds REAL,
            created_at REAL NOT NULL, starred INTEGER NOT NULL DEFAULT 0
        );
        PRAGMA user_version = 4;
        """
    )
    conn.execute(
        "INSERT INTO jobs (status, request_json, created_at, song_id) VALUES ('done', ?, 1, 1)",
        (json.dumps({**REQUEST, "seed": 5}),),
    )
    conn.execute(
        "INSERT INTO songs (job_id, dir, audio_path, audio_seconds, created_at, starred) "
        "VALUES (1, '/d', '/d/audio.flac', 2.5, 2, 1)"
    )
    conn.commit()
    conn.close()

    store = Store(path)
    [song] = store.list_songs()
    version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    store.close()

    assert version == SCHEMA_VERSION == 5
    assert song["starred"] is True and song["title"] == "Soft morning light"
    assert song["title_set"] is False
