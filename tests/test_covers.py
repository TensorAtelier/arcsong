"""Cover jobs: uploading a recording, transcribing it into a Score, and losing the upload."""

import io

import pytest
from fastapi.testclient import TestClient

from songloom.app import MAX_UPLOAD_BYTES, create_app
from songloom.engine import EngineSpec
from songloom.models import FakeModels
from tests.test_app import FAKE, wait_for

RECORDING = b"RIFF" + b"\0" * 4096


def serve(tmp_path, spec=FAKE, **kwargs):
    return TestClient(create_app(spec, tmp_path, **kwargs))


@pytest.fixture
def client(tmp_path):
    with serve(tmp_path) as c:
        yield c


def upload(client, audio=RECORDING, name="take.wav", **fields):
    body = {"style": "warm soul, brass", "rights_confirmed": "true", **fields}
    files = {"audio": (name, io.BytesIO(audio), "audio/wav")}
    return client.post("/api/covers", files=files, data=body)


def test_a_cover_transcribes_the_upload_into_a_score(client, tmp_path):
    created = upload(client, lyrics="[Verse]\nnew words")

    assert created.status_code == 201
    job = created.json()
    assert job["kind"] == "cover" and job["request"]["source_name"] == "take.wav"
    assert job["request"]["style"] == "warm soul, brass"
    done = wait_for(client, job["id"])

    assert done["status"] == "done", done["error"]
    assert done["song_id"] is None
    score = client.get(f"/api/scores/{job['id']}").json()
    assert score["report"]["voices"]["Vocal"]["sounding_notes"] == 16
    # mlx-Yue's other exports stay on disk; the upload does not.
    assert (tmp_path / "covers" / str(job["id"]) / "melody.mid").is_file()
    assert list((tmp_path / "uploads").glob("*")) == []
    assert client.get(f"/api/jobs/{job['id']}").json()["source_audio"] is None


def test_the_upload_goes_when_the_cover_fails_or_is_cancelled(tmp_path):
    failing = EngineSpec("songloom.fake_engine:FakeEngine", {"fail_transcribe": "no music here"})
    with serve(tmp_path, failing) as client:
        job = upload(client).json()
        failed = wait_for(client, job["id"])

    assert failed["status"] == "failed" and "no music here" in failed["error"]
    assert list((tmp_path / "uploads").glob("*")) == []

    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 5.0})
    with serve(tmp_path, slow) as client:
        first = upload(client).json()
        queued = upload(client).json()
        assert len(list((tmp_path / "uploads").glob("*"))) == 2

        client.post(f"/api/jobs/{queued['id']}/cancel")
        assert wait_for(client, queued["id"])["status"] == "cancelled"
        assert len(list((tmp_path / "uploads").glob("*"))) == 1  # the running one is still there

        client.post(f"/api/jobs/{first['id']}/cancel")
        wait_for(client, first["id"])

    assert list((tmp_path / "uploads").glob("*")) == []


def test_a_cover_needs_the_covers_part_and_the_rights_confirmation(tmp_path):
    missing = FakeModels(tmp_path / "covers-models", preinstalled=False)
    with serve(tmp_path, covers=missing) as client:
        refused = upload(client)
    with serve(tmp_path) as client:
        no_rights = upload(client, rights_confirmed="false")
        empty = upload(client, audio=b"")
        no_style = upload(client, style="")

    assert refused.status_code == 409 and "Covers" in refused.json()["detail"]
    assert no_rights.status_code == 422 and "rights" in no_rights.json()["detail"]
    assert empty.status_code == 422
    assert no_style.status_code == 422


def test_form_fields_arrive_as_text_and_are_still_understood(client):
    created = upload(client, steps="8", precision="bf16", mode="melody", seed="4242")

    assert created.status_code == 201, created.text
    request = created.json()["request"]
    assert request["steps"] == 8 and request["precision"] == "bf16"
    assert request["mode"] == "melody" and request["seed"] == 4242
    assert upload(client, steps="16").status_code == 422


def test_an_oversized_recording_is_refused_and_leaves_nothing_behind(client, tmp_path):
    too_big = b"\0" * (MAX_UPLOAD_BYTES + 1024)

    refused = upload(client, audio=too_big)

    assert refused.status_code == 413
    assert list((tmp_path / "uploads").glob("*")) == []


def test_a_cover_reports_its_own_stage_and_the_queue_moves_on(tmp_path):
    slow = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.6})
    with serve(tmp_path, slow) as client:
        subscription = client.app.state.runner.broadcaster.subscribe()
        cover = upload(client).json()
        take = client.post("/api/jobs", json={"style": "pop", "steps": 8}).json()

        assert wait_for(client, cover["id"])["status"] == "done"
        assert wait_for(client, take["id"])["status"] == "done"

    live = []
    while not subscription.empty():
        message = subscription.get()
        if message["type"] != "job" or message["job"]["id"] != cover["id"]:
            continue
        if message["job"]["live"]:
            live.append(message["job"]["live"])
    assert {entry["stage"] for entry in live if entry.get("stage")} == {"transcribing"}
    windows = [(e["completed"], e["total"]) for e in live if "total" in e]
    assert windows and windows[-1] == (3, 3)


def test_a_transcribed_score_renders_a_cover(client):
    job = wait_for(client, upload(client).json()["id"])
    score = client.get(f"/api/scores/{job['id']}").json()

    rendered = client.post(
        "/api/jobs", json={**job["request"], "abc": score["abc"], "source_name": None}
    )

    assert rendered.status_code == 201
    done = wait_for(client, rendered.json()["id"])
    assert done["status"] == "done", done["error"]
    assert client.get(f"/api/songs/{done['song_id']}/score").json()["abc"] == score["abc"]
