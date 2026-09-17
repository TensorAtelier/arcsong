"""The Library API: listing songs, disk usage, deleting and downloading Takes."""


import pytest
from fastapi.testclient import TestClient

from songloom.app import create_app
from tests.test_app import FAKE, wait_for


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as c:
        yield c


def make_song(client, **request) -> dict:
    body = {"style": "indie pop", "lyrics": "[Verse]\nhello", **request}
    return wait_for(client, client.post("/api/jobs", json=body).json()["id"])


def test_songs_are_listed_newest_first_with_their_request_and_size(client, tmp_path):
    first = make_song(client, style="first", seed=7)
    second = make_song(client, style="second")

    songs = client.get("/api/songs").json()

    assert [s["id"] for s in songs] == [second["song_id"], first["song_id"]]
    oldest = songs[1]
    assert oldest["job_id"] == first["id"]
    assert oldest["request"]["style"] == "first" and oldest["request"]["seed"] == 7
    assert oldest["audio_seconds"] == 1.0
    take = tmp_path / "songs" / str(first["id"])
    assert oldest["bytes"] == sum(f.stat().st_size for f in take.rglob("*") if f.is_file()) > 0


def test_library_reports_song_count_and_disk_use(client):
    empty = client.get("/api/library").json()
    assert empty["songs"] == 0 and empty["bytes_used"] == 0 and empty["bytes_free"] > 0

    make_song(client)
    make_song(client)
    library = client.get("/api/library").json()

    assert library["songs"] == 2
    assert library["bytes_used"] == sum(s["bytes"] for s in client.get("/api/songs").json())


def test_deleting_a_song_removes_its_files_song_and_job(client, tmp_path):
    kept = make_song(client, style="kept")
    gone = make_song(client, style="gone")
    subscription = client.app.state.runner.broadcaster.subscribe()

    response = client.delete(f"/api/songs/{gone['song_id']}")

    assert response.status_code == 200
    assert not (tmp_path / "songs" / str(gone["id"])).exists()
    assert (tmp_path / "songs" / str(kept["id"])).exists()
    assert [s["id"] for s in client.get("/api/songs").json()] == [kept["song_id"]]
    assert client.get(f"/api/jobs/{gone['id']}").status_code == 404
    assert client.get(f"/api/songs/{gone['song_id']}/audio").status_code == 404
    message = subscription.get(timeout=5)
    assert message["type"] == "deleted"
    assert (message["job_id"], message["song_id"]) == (gone["id"], gone["song_id"])
    assert client.delete(f"/api/songs/{gone['song_id']}").status_code == 404


def test_a_job_that_is_still_running_has_no_song_to_delete(tmp_path):
    from songloom.engine import EngineSpec

    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 5})
    with TestClient(create_app(slow, tmp_path)) as client:
        job = client.post("/api/jobs", json={"style": "a"}).json()
        wait_for(client, job["id"], statuses=("running",))
        assert client.get("/api/songs").json() == []
        assert client.delete("/api/songs/1").status_code == 404
        client.post(f"/api/jobs/{job['id']}/cancel")
