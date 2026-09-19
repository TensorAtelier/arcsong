"""One real render through mlx-Yue. Slow and needs weights, AC power and the GPU, so it only
runs with ARCSONG_REAL_ENGINE=1."""

import os
import time
from pathlib import Path

import pytest
import soundfile
from fastapi.testclient import TestClient

from arcsong.app import create_app
from arcsong.engine import EngineSpec
from arcsong.models import MlxYueModels

pytestmark = pytest.mark.skipif(
    os.environ.get("ARCSONG_REAL_ENGINE") != "1", reason="set ARCSONG_REAL_ENGINE=1"
)

MODELS = Path(os.environ.get("ARCSONG_MLX_MODELS", "~/projects/mlx-Yue/models")).expanduser()
MLX = EngineSpec("arcsong.mlx_engine:MlxYueEngine", {"models": str(MODELS)})
SHORT = {
    "style": "English, warm piano pop, expressive female voice",
    "lyrics": "[Verse]\nNeon fades along the lane\nFootsteps keep the time",
    "mode": "full",
    "seed": 831001,
    "precision": "8bit",
    "steps": 8,
}


def test_a_real_take_is_rendered_saved_and_indexed(tmp_path):
    with TestClient(create_app(MLX, tmp_path, models=MlxYueModels(MODELS))) as client:
        job = client.post("/api/jobs", json=SHORT).json()
        deadline = time.monotonic() + 900
        while (job := client.get(f"/api/jobs/{job['id']}").json())["status"] in (
            "queued",
            "running",
        ):
            assert time.monotonic() < deadline, "render took over 15 minutes"
            time.sleep(1)

        assert job["status"] == "done", job["error"]
        take = tmp_path / "songs" / str(job["id"])
        assert {"audio.flac", "score.abc", "semantic.npy", "noise.npy"} <= {
            p.name for p in take.iterdir()
        }
        audio = client.get(f"/api/songs/{job['song_id']}/audio")
        assert audio.status_code == 200
        info = soundfile.info(take / "audio.flac")
        assert info.samplerate == 48_000 and info.duration == pytest.approx(job["audio_seconds"])


def wait_done(client, job_id, limit=900):
    deadline = time.monotonic() + limit
    while (job := client.get(f"/api/jobs/{job_id}").json())["status"] in ("queued", "running"):
        assert time.monotonic() < deadline, f"job {job_id} took over {limit} s"
        time.sleep(1)
    return job


def test_a_real_draft_is_finalized_from_its_saved_take(tmp_path):
    with TestClient(create_app(MLX, tmp_path, models=MlxYueModels(MODELS))) as client:
        draft = wait_done(client, client.post("/api/jobs", json=SHORT).json()["id"])
        assert draft["status"] == "done", draft["error"]
        created = client.post(f"/api/songs/{draft['song_id']}/finalize")
        assert created.status_code == 201, created.text
        final = wait_done(client, created.json()["id"])

        assert final["status"] == "done", final["error"]
        assert final["request"]["steps"] == 32 and final["source_song_id"] == draft["song_id"]
        draft_dir, final_dir = (tmp_path / "songs" / str(j["id"]) for j in (draft, final))
        # Same Semantic tokens and noise; only synthesis differs.
        for name in ("semantic.npy", "noise.npy", "score.abc"):
            assert (final_dir / name).read_bytes() == (draft_dir / name).read_bytes(), name
        assert (final_dir / "latent.npy").read_bytes() != (draft_dir / "latent.npy").read_bytes()
        assert final["audio_seconds"] == pytest.approx(draft["audio_seconds"])


def test_a_real_score_only_run_writes_abc_the_parser_accepts(tmp_path):
    from lyra.music_tools.abc_tools import parse_abc, report

    with TestClient(create_app(MLX, tmp_path, models=MlxYueModels(MODELS))) as client:
        job = client.post("/api/scores", json={**SHORT, "mode": "full"}).json()
        done = wait_done(client, job["id"], limit=300)
        score = client.get(f"/api/scores/{job['id']}").json()

    assert done["status"] == "done", done["error"]
    assert done["song_id"] is None
    assert not (tmp_path / "songs" / str(job["id"])).exists()  # planning writes nothing
    assert report(parse_abc(score["abc"]))["bpm"] > 0
    assert score["report"]["voices"]["Vocal"]["sounding_notes"] > 0


def test_a_real_take_renders_from_an_edited_score(tmp_path):
    with TestClient(create_app(MLX, tmp_path, models=MlxYueModels(MODELS))) as client:
        score_job = client.post("/api/scores", json={**SHORT, "mode": "full"}).json()
        wait_done(client, score_job["id"], 300)
        abc = client.get(f"/api/scores/{score_job['id']}").json()["abc"]
        edited = client.post("/api/score/strip-chords", json={"abc": abc}).json()["abc"]
        assert edited != abc

        job = client.post("/api/jobs", json={**SHORT, "abc": edited}).json()
        done = wait_done(client, job["id"])
        saved = client.get(f"/api/songs/{done['song_id']}/score").json()["abc"]

    assert done["status"] == "done", done["error"]
    # mlx-Yue uses the supplied Score as the plan, so the Take carries it back unchanged.
    assert saved == edited


def test_the_real_transcription_weights_download_and_verify(tmp_path):
    """Fetches SheetSage2 and MERT2 into the user's models directory (once; later runs are a
    no-op) and checks them the way mlx-Yue does."""
    from arcsong.models import TranscriptionModels, weights_state

    models = TranscriptionModels(MODELS)
    if not weights_state(models)["installed"]:
        models.download(lambda phase: None)

    state = weights_state(models)
    assert state["installed"] is True
    models.verify()


def test_a_real_cover_transcribes_a_take_and_re_sings_it(tmp_path):
    """Renders a short Take, transcribes it back into a Score, and renders a cover from that."""
    from arcsong.models import TranscriptionModels, weights_state

    if not weights_state(TranscriptionModels(MODELS))["installed"]:
        pytest.skip("the covers weights are not installed")
    engine = EngineSpec(
        "arcsong.mlx_engine:MlxYueEngine",
        {"models": str(MODELS), "transcription_models": str(MODELS)},
    )
    app = create_app(
        engine, tmp_path, models=MlxYueModels(MODELS), covers=TranscriptionModels(MODELS)
    )
    with TestClient(app) as client:
        take = wait_done(client, client.post("/api/jobs", json=SHORT).json()["id"])
        assert take["status"] == "done", take["error"]
        audio = Path(take_dir(tmp_path, take) / "audio.flac")

        with audio.open("rb") as recording:
            created = client.post(
                "/api/covers",
                files={"audio": ("take.flac", recording, "audio/flac")},
                data={"style": "slow jazz trio, brushed drums", "rights_confirmed": "true",
                      "steps": "8"},
            )
        assert created.status_code == 201, created.text
        cover = wait_done(client, created.json()["id"], limit=1800)
        assert cover["status"] == "done", cover["error"]
        score = client.get(f"/api/scores/{cover['id']}").json()

        assert score["report"]["voices"]["Vocal"]["sounding_notes"] > 0
        assert not list((tmp_path / "uploads").glob("*"))  # the recording is gone

        sung = client.post("/api/jobs", json={**cover["request"], "abc": score["abc"]})
        assert sung.status_code == 201, sung.text
        done = wait_done(client, sung.json()["id"])

    assert done["status"] == "done", done["error"]
    assert client_score_matches(tmp_path, done, score["abc"])


def take_dir(tmp_path, job):
    return tmp_path / "songs" / str(job["id"])


def client_score_matches(tmp_path, job, abc):
    return (take_dir(tmp_path, job) / "score.abc").read_text() == abc
