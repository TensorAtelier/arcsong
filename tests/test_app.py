"""The arcsong app end to end through a fake Engine in a real worker process."""

import time
import wave
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from arcsong.app import create_app
from arcsong.engine import EngineSpec

FAKE = EngineSpec("arcsong.fake_engine:FakeEngine", {"stage_seconds": 0.01})


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as c:
        yield c


def wait_for(client, job_id, statuses=("done", "failed", "cancelled"), timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} still {job['status']}")


def test_a_job_runs_to_a_playable_song(client):
    created = client.post("/api/jobs", json={"style": "indie pop", "lyrics": "[Verse]\nhello"})
    assert created.status_code == 201
    job = created.json()
    assert job["status"] in ("queued", "running")
    assert isinstance(job["request"]["seed"], int)

    done = wait_for(client, job["id"])

    assert done["status"] == "done", done["error"]
    audio = client.get(f"/api/songs/{done['song_id']}/audio")
    assert audio.status_code == 200
    with wave.open(BytesIO(audio.content)) as wav:
        assert wav.getnframes() == 48_000


def test_jobs_run_one_at_a_time_in_order(client):
    ids = [client.post("/api/jobs", json={"style": f"style {i}"}).json()["id"] for i in range(3)]

    jobs = [wait_for(client, i) for i in ids]

    assert [j["status"] for j in jobs] == ["done"] * 3
    for earlier, later in zip(jobs, jobs[1:], strict=False):
        assert earlier["finished_at"] <= later["started_at"]
    assert [j["id"] for j in client.get("/api/jobs").json()] == list(reversed(ids))


def test_an_engine_failure_marks_the_job_failed_and_the_queue_moves_on(tmp_path):
    failing = EngineSpec(
        "arcsong.fake_engine:FakeEngine", {"stage_seconds": 0.01, "fail_in": "synthesis"}
    )
    with TestClient(create_app(failing, tmp_path)) as client:
        first = client.post("/api/jobs", json={"style": "a"}).json()
        second = client.post("/api/jobs", json={"style": "b"}).json()

        assert wait_for(client, first["id"])["status"] == "failed"
        failed = wait_for(client, second["id"])
        assert failed["status"] == "failed"
        assert "fake failure in synthesis" in failed["error"]


def test_a_request_is_validated(client):
    assert client.post("/api/jobs", json={"style": ""}).status_code == 422
    assert client.post("/api/jobs", json={"style": "x", "steps": 16}).status_code == 422
    assert client.get("/api/jobs/999").status_code == 404
    assert client.get("/api/songs/999/audio").status_code == 404


def test_finished_songs_survive_a_restart(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as client:
        job = wait_for(client, client.post("/api/jobs", json={"style": "a"}).json()["id"])
    with TestClient(create_app(FAKE, tmp_path)) as client:
        again = client.get(f"/api/jobs/{job['id']}").json()
        assert again["status"] == "done"
        assert client.get(f"/api/songs/{again['song_id']}/audio").status_code == 200


def test_the_web_app_is_served_beside_the_api(client):
    page = client.get("/")
    assert page.status_code == 200
    assert '<div id="root"></div>' in page.text
    assert client.get("/api/jobs").status_code == 200


def test_finished_audio_is_served_with_a_browser_playable_type(client):
    done = wait_for(client, client.post("/api/jobs", json={"style": "a"}).json()["id"])
    audio = client.get(f"/api/songs/{done['song_id']}/audio")
    assert audio.headers["content-type"] == "audio/wav"


def test_every_job_snapshot_is_newer_than_the_last(client):
    job = client.post("/api/jobs", json={"style": "a"}).json()
    later = client.get(f"/api/jobs/{job['id']}").json()
    listed = client.get("/api/jobs").json()[0]
    assert job["seq"] < later["seq"] < listed["seq"]


MESSY = "\n  \n  [Verse]  \n\thello there \r\n\n [Chorus]\n  sing it  \n\n\n"
TIDY = "[Verse]\nhello there\n\n[Chorus]\nsing it"


def test_lyrics_are_trimmed_line_by_line_keeping_blank_lines(client):
    song = client.post("/api/jobs", json={"style": "pop", "lyrics": MESSY}).json()
    score = client.post("/api/scores", json={"style": "pop", "lyrics": MESSY}).json()
    group = client.post("/api/groups", json={"style": "pop", "lyrics": MESSY, "count": 2}).json()

    assert song["request"]["lyrics"] == TIDY
    assert score["request"]["lyrics"] == TIDY
    assert all(job["request"]["lyrics"] == TIDY for job in group)
