"""Cover jobs: uploading a recording, transcribing it into a Score, and losing the upload."""

import io
import time

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


# --- Review fixes -----------------------------------------------------------------------------


def test_a_refused_upload_leaves_no_job_behind(client, tmp_path):
    from songloom.app import MAX_UPLOAD_BYTES

    too_big = upload(client, audio=b"\0" * (MAX_UPLOAD_BYTES + 1024))
    empty = upload(client, audio=b"")
    no_rights = upload(client, rights_confirmed="false")

    assert (too_big.status_code, empty.status_code, no_rights.status_code) == (413, 422, 422)
    assert client.get("/api/jobs").json() == []
    assert list((tmp_path / "uploads").glob("*")) == []
    # A later job still runs: no phantom cover is waiting in front of it.
    job = wait_for(client, client.post("/api/jobs", json={"style": "pop", "steps": 8}).json()["id"])
    assert job["status"] == "done", job["error"]


def test_the_uploads_name_never_reaches_the_filesystem(client, tmp_path):
    job = upload(client, name="../../evil name.WAV").json()

    assert job["request"]["source_name"] == "evil name.WAV"
    [stored] = list((tmp_path / "uploads").glob("*"))
    assert stored.name == f"{job['id']}.WAV"
    wait_for(client, job["id"])


def test_a_cover_is_refused_while_the_covers_checks_are_still_running(tmp_path):
    class SlowChecks(FakeModels):
        def engine_checks(self):
            time.sleep(1.0)  # the real ffmpeg and Metal checks are subprocesses
            return super().engine_checks()

    with serve(tmp_path, covers=SlowChecks(tmp_path / "covers-models")) as client:
        early = upload(client)
        setup = client.get("/api/setup").json()
        covers = next(p for p in setup["parts"] if p["id"] == "covers")
        # Songs don't wait for checks; only the optional part does.
        assert setup["can_render"] is True
        while not client.get("/api/setup").json()["parts"][1]["checked"]:
            time.sleep(0.05)
        later = upload(client)
        wait_for(client, later.json()["id"])

    assert early.status_code == 409
    assert covers["usable"] is False and covers["checked"] is False
    assert later.status_code == 201


def test_cancelling_a_real_transcription_reads_as_cancelled_not_failed(tmp_path, monkeypatch):
    """mlx-Yue raises its own InterruptedError; the worker must see songloom's Cancelled, or the
    queue shows a red failure with a traceback for something the user asked for."""
    import lyra.transcription.pipeline as pipeline

    from songloom.engine import Cancelled
    from songloom.mlx_engine import MlxYueEngine

    def interrupted(*args, **kwargs):
        raise InterruptedError("Cancelled during transcription")

    monkeypatch.setattr(pipeline, "transcribe", interrupted)
    engine = MlxYueEngine(models=tmp_path)
    engine._sheetsage = object()  # the model is not what this test is about
    audio = tmp_path / "recording.wav"
    audio.write_bytes(RECORDING)

    with pytest.raises(Cancelled):
        engine.transcribe(audio, {}, tmp_path / "out", lambda: True, lambda event: None)

    # Without a cancel asked for, the same error is a real failure.
    with pytest.raises(InterruptedError):
        engine.transcribe(audio, {}, tmp_path / "out", lambda: False, lambda event: None)
