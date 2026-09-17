"""The Setup API through fake weights: checks, the licence, the download and the jobs gate."""

import time

import pytest
from fastapi.testclient import TestClient

from songloom.app import create_app
from songloom.engine import EngineSpec
from songloom.models import (
    CONVERTED_FILES,
    VAE_FILES,
    FakeModels,
    MlxYueModels,
    check,
    models_dir,
    weights_state,
)

FAKE = EngineSpec("songloom.fake_engine:FakeEngine", {"stage_seconds": 0.01})


def fake_models(tmp_path, **options):
    return FakeModels(tmp_path / "models", preinstalled=False, **options)


def serve(tmp_path, models):
    return TestClient(create_app(FAKE, tmp_path, models=models))


def wait_setup(client, done, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        setup = client.get("/api/setup").json()
        if done(setup):
            return setup
        time.sleep(0.02)
    raise AssertionError(f"setup never got there: {setup}")


def checks_by_id(setup):
    return {c["id"]: c for c in setup["checks"]}


def test_a_fresh_data_dir_is_not_ready_and_lists_the_checks(tmp_path):
    with serve(tmp_path, fake_models(tmp_path)) as client:
        setup = wait_setup(client, lambda s: not s["checking"])

    assert setup["ready"] is False
    assert setup["weights"]["installed"] is False
    assert setup["weights"]["bytes_total"] == 64_000
    assert setup["licence"]["id"] == "CC-BY-NC-4.0"
    assert setup["licence"]["acknowledged_at"] is None
    assert setup["download"]["state"] == "idle"
    checks = checks_by_id(setup)
    assert {"runtime", "ram", "power", "disk", "weights"} <= set(checks)
    assert checks["weights"]["status"] == "fail"
    assert checks["ram"]["status"] in ("ok", "warn")


def test_jobs_are_refused_until_the_weights_are_installed(tmp_path):
    with serve(tmp_path, fake_models(tmp_path)) as client:
        refused = client.post("/api/jobs", json={"style": "pop"})

    assert refused.status_code == 409
    assert "Setup" in refused.json()["detail"]


def test_the_download_needs_the_licence_acknowledged_first(tmp_path):
    with serve(tmp_path, fake_models(tmp_path)) as client:
        refused = client.post("/api/setup/download")
        acknowledged = client.post("/api/setup/licence").json()

    assert refused.status_code == 409
    assert "licence" in refused.json()["detail"]
    assert acknowledged["licence"]["acknowledged_at"] is not None


def test_the_acknowledgement_survives_a_restart(tmp_path):
    with serve(tmp_path, fake_models(tmp_path)) as client:
        at = client.post("/api/setup/licence").json()["licence"]["acknowledged_at"]
    with serve(tmp_path, fake_models(tmp_path)) as client:
        again = client.post("/api/setup/licence").json()["licence"]["acknowledged_at"]
        assert client.get("/api/setup").json()["licence"]["acknowledged_at"] == at
    assert again == at


def test_a_download_reports_progress_verifies_and_makes_setup_ready(tmp_path):
    models = fake_models(tmp_path, download_seconds=1.0)
    with serve(tmp_path, models) as client:
        subscription = client.app.state.runner.broadcaster.subscribe()
        client.post("/api/setup/licence")
        started = client.post("/api/setup/download")
        assert started.status_code == 200
        assert started.json()["download"]["state"] == "running"
        assert client.post("/api/setup/download").status_code == 409  # one at a time
        assert client.post("/api/jobs", json={"style": "pop"}).status_code == 409

        setup = wait_setup(client, lambda s: s["download"]["state"] != "running")
        job = client.post("/api/jobs", json={"style": "pop"})

    assert setup["download"]["state"] == "done", setup["download"]
    assert setup["weights"]["installed"] is True
    assert setup["ready"] is True
    assert job.status_code == 201
    messages = []
    while not subscription.empty():
        message = subscription.get()
        if message["type"] == "setup":
            messages.append(message["setup"]["download"])
    progress = [m["bytes"] for m in messages if m["state"] == "running" and "bytes" in m]
    assert len(progress) >= 2 and progress == sorted(progress)
    assert all(0 <= b <= 64_000 for b in progress)
    assert {m.get("phase") for m in messages} >= {"downloading", "verifying"}
    assert messages[-1]["state"] == "done"


def test_a_cancelled_download_resumes_where_it_stopped(tmp_path):
    models = fake_models(tmp_path, download_seconds=4.0)
    with serve(tmp_path, models) as client:
        client.post("/api/setup/licence")
        client.post("/api/setup/download")
        wait_setup(client, lambda s: s["download"].get("bytes", 0) > 0)

        cancelled = client.post("/api/setup/download/cancel").json()
        partial = (tmp_path / "models" / "weights.bin").stat().st_size
        assert client.post("/api/setup/download/cancel").status_code == 409

        client.post("/api/setup/download")
        # The first poll after a restart already counts what the cancelled run left.
        resumed = client.get("/api/setup").json()["download"]["bytes"]
        setup = wait_setup(client, lambda s: s["download"]["state"] != "running")

    assert cancelled["download"]["state"] == "cancelled"
    assert cancelled["weights"]["bytes_on_disk"] == partial
    assert "incomplete" in checks_by_id(cancelled)["weights"]["detail"]
    assert 0 < partial < 64_000
    assert resumed >= partial
    assert setup["download"]["state"] == "done"
    assert (tmp_path / "models" / "weights.bin").stat().st_size == 64_000


@pytest.mark.parametrize(
    "option, reason",
    [("fail_download", "RuntimeError: network went away"), ("fail_verify", "ValueError: bad hash")],
)
def test_a_failed_download_says_why_and_can_be_retried(tmp_path, option, reason):
    message = reason.split(": ", 1)[1]
    with serve(tmp_path, fake_models(tmp_path, **{option: message})) as client:
        client.post("/api/setup/licence")
        client.post("/api/setup/download")
        setup = wait_setup(client, lambda s: s["download"]["state"] != "running")
        retried = client.post("/api/setup/download")

    assert setup["download"]["state"] == "failed"
    assert setup["download"]["reason"] == reason
    assert "Traceback" in setup["download"]["error"]
    assert setup["ready"] is False
    assert retried.status_code == 200


def test_checks_run_again_on_request(tmp_path):
    calls = []

    class Counting(FakeModels):
        def engine_checks(self):
            calls.append(1)
            return [check("runtime", "Fake runtime", "ok", f"run {len(calls)}")]

    with serve(tmp_path, Counting(tmp_path / "models")) as client:
        wait_setup(client, lambda s: not s["checking"])
        client.post("/api/setup/checks")
        setup = wait_setup(client, lambda s: checks_by_id(s)["runtime"]["detail"] == "run 2")

    assert setup["ready"] is False  # installed, but the licence is not acknowledged
    assert len(calls) == 2


def test_the_default_models_come_preinstalled_so_other_tests_never_meet_the_gate(tmp_path):
    with TestClient(create_app(FAKE, tmp_path)) as client:
        assert client.post("/api/jobs", json={"style": "pop"}).status_code == 201


# --- mlx-Yue weights on disk, without the Engine ----------------------------------------------


def write_mlx_weights(root, skip=()):
    for sub, files in (("converted", CONVERTED_FILES), ("vae", VAE_FILES)):
        for name, size in files.items():
            if f"{sub}/{name}" in skip:
                continue
            path = root / sub / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as out:
                out.truncate(size)  # sparse: pinned sizes without the bytes


def test_mlx_weights_are_installed_when_every_file_has_its_pinned_size(tmp_path):
    write_mlx_weights(tmp_path)
    (tmp_path / "vae" / ".gitattributes").write_text("vae metadata is harmless")

    state = weights_state(MlxYueModels(tmp_path))

    assert state["installed"] is True
    assert state["bytes_present"] == state["bytes_total"] > 9 * 2**30


def test_mlx_weights_with_a_missing_file_or_hub_metadata_are_not_installed(tmp_path):
    write_mlx_weights(tmp_path, skip={"converted/ar-bf16.safetensors"})
    (tmp_path / "converted" / ".cache" / "huggingface").mkdir(parents=True)
    (tmp_path / "converted" / ".cache" / "huggingface" / ".gitignore").write_text("*")
    (tmp_path / "converted" / ".gitattributes").write_text("*.safetensors filter=lfs")

    state = weights_state(MlxYueModels(tmp_path))

    assert state["installed"] is False
    assert state["missing"] == ["converted/ar-bf16.safetensors"]
    assert state["stray"] == ["converted/.cache", "converted/.gitattributes"]


def test_the_models_dir_defaults_into_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("SONGLOOM_MLX_MODELS", raising=False)
    assert models_dir(tmp_path) == tmp_path / "models"
    assert models_dir(tmp_path, "~/weights") == (tmp_path.home() / "weights").resolve()
    monkeypatch.setenv("SONGLOOM_MLX_MODELS", str(tmp_path / "env"))
    assert models_dir(tmp_path) == tmp_path / "env"
