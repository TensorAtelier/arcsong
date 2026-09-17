"""The Library API: listing songs, disk usage, deleting and downloading Takes."""

import io

import numpy as np
import pytest
import soundfile
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


@pytest.mark.parametrize("fmt", ["flac", "wav"])
def test_a_song_downloads_as_flac_or_wav_named_after_its_style(client, fmt):
    song = make_song(client, style="English, City Pop, groovy bass!")

    response = client.get(f"/api/songs/{song['song_id']}/download", params={"format": fmt})

    assert response.status_code == 200
    assert response.headers["content-type"] == f"audio/{fmt}"
    disposition = response.headers["content-disposition"]
    name = f"songloom-{song['song_id']}-english-city-pop-groovy-bass.{fmt}"
    assert f'filename="{name}"' in disposition
    audio, rate = soundfile.read(io.BytesIO(response.content))
    assert rate == 48_000 and len(audio) == 48_000


def test_a_flac_take_downloads_as_flac_unchanged_and_as_wav_converted(client):
    song = make_song(client)
    stored = client.app.state.store.get_song(song["song_id"])
    # Make the Take a stereo FLAC, as mlx-Yue saves it.
    flac = stored["audio_path"].replace(".wav", ".flac")
    tone, rate = soundfile.read(stored["audio_path"], always_2d=True)
    soundfile.write(flac, np.hstack([tone, tone]), rate, subtype="PCM_24")
    with client.app.state.store._lock, client.app.state.store._conn as conn:
        conn.execute("UPDATE songs SET audio_path = ? WHERE id = ?", (flac, song["song_id"]))

    as_flac = client.get(f"/api/songs/{song['song_id']}/download?format=flac")
    as_wav = client.get(f"/api/songs/{song['song_id']}/download?format=wav")

    assert as_flac.content == open(flac, "rb").read()
    wav, wav_rate = soundfile.read(io.BytesIO(as_wav.content), always_2d=True)
    assert wav_rate == rate and wav.shape == (48_000, 2)


def test_an_unknown_song_or_format_is_refused(client):
    song = make_song(client)
    assert client.get("/api/songs/999/download").status_code == 404
    assert client.get(f"/api/songs/{song['song_id']}/download?format=mp3").status_code == 422
