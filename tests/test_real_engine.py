"""One real render through mlx-Yue. Slow and needs weights, AC power and the GPU, so it only
runs with SONGLOOM_REAL_ENGINE=1."""

import os
import time
from pathlib import Path

import pytest
import soundfile
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.engine import EngineSpec
from songloom.models import MlxYueModels

pytestmark = pytest.mark.skipif(
    os.environ.get("SONGLOOM_REAL_ENGINE") != "1", reason="set SONGLOOM_REAL_ENGINE=1"
)

MODELS = Path(os.environ.get("SONGLOOM_MLX_MODELS", "~/projects/mlx-Yue/models")).expanduser()
MLX = EngineSpec("songloom.mlx_engine:MlxYueEngine", {"models": str(MODELS)})
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
