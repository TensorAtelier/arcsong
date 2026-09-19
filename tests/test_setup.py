"""The Setup API through fake weights: checks, the licence, the download and the jobs gate."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arcsong.app import create_app
from arcsong.engine import EngineSpec
from arcsong.models import (
    CONVERTED_FILES,
    VAE_FILES,
    FakeModels,
    MlxYueModels,
    check,
    models_dir,
    weights_state,
)

FAKE = EngineSpec("arcsong.fake_engine:FakeEngine", {"stage_seconds": 0.01})


def fake_models(tmp_path, **options):
    return FakeModels(tmp_path / "models", preinstalled=False, **options)


def serve(tmp_path, models):
    return TestClient(create_app(FAKE, tmp_path, models=models))


def fake_setup(tmp_path, store):
    """A Setup with only the part a unit test needs."""
    from arcsong.setup import ENGINE, Part, Setup

    parts = [Part(ENGINE, "Song model", FakeModels(tmp_path / "models"))]
    return Setup(parts, store, lambda message: None, iter(range(9**9)).__next__)


def wait_setup(client, done, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        setup = client.get("/api/setup").json()
        if done(setup):
            return setup
        time.sleep(0.02)
    raise AssertionError(f"setup never got there: {setup}")


def checks_by_id(setup, part="engine"):
    """Every check the page shows for a part: its own, plus the machine-wide ones."""
    found = next(p for p in setup["parts"] if p["id"] == part)
    return {c["id"]: c for c in [*setup["checks"], *found["checks"]]}


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
        refused = client.post("/api/setup/download/engine")
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
        started = client.post("/api/setup/download/engine")
        assert started.status_code == 200
        assert started.json()["download"]["state"] == "running"
        assert client.post("/api/setup/download/engine").status_code == 409  # one at a time
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
        client.post("/api/setup/download/engine")
        wait_setup(client, lambda s: s["download"].get("bytes", 0) > 0)

        cancelled = client.post("/api/setup/download/engine/cancel").json()
        partial = (tmp_path / "models" / "weights.bin").stat().st_size
        assert client.post("/api/setup/download/engine/cancel").status_code == 409

        client.post("/api/setup/download/engine")
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
        client.post("/api/setup/download/engine")
        setup = wait_setup(client, lambda s: s["download"]["state"] != "running")
        retried = client.post("/api/setup/download/engine")

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
    monkeypatch.delenv("ARCSONG_MLX_MODELS", raising=False)
    assert models_dir(tmp_path) == tmp_path / "models"
    assert models_dir(tmp_path, "~/weights") == (tmp_path.home() / "weights").resolve()
    monkeypatch.setenv("ARCSONG_MLX_MODELS", str(tmp_path / "env"))
    assert models_dir(tmp_path) == tmp_path / "env"


def test_the_mlx_download_removes_every_stray_file_before_verifying(tmp_path, monkeypatch):
    import huggingface_hub
    import lyra.conversion
    import yue2.storage

    write_mlx_weights(tmp_path)
    converted = tmp_path / "converted"
    (converted / ".DS_Store").write_text("finder")
    (converted / ".cache" / "huggingface").mkdir(parents=True)
    (converted / ".cache" / "huggingface" / ".gitignore").write_text("*")
    (converted / ".gitattributes").write_text("*.safetensors filter=lfs")
    (tmp_path / "vae" / ".cache").mkdir()
    seen = {}
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: None)
    monkeypatch.setattr(
        lyra.conversion,
        "verify_conversion",
        lambda path: seen.update(
            stray=sorted(p.name for p in path.iterdir() if p.name.startswith("."))
        ),
    )
    monkeypatch.setattr(yue2.storage, "model_identity", lambda path: None)
    models = MlxYueModels(tmp_path)

    models.download(lambda phase: None)

    assert seen["stray"] == []
    assert not (tmp_path / "vae" / ".cache").exists()
    assert weights_state(models)["installed"] is True


class LateQueue:
    """A queue whose message arrives just after the first poll gave up."""

    def __init__(self, message):
        self.message, self.polls = message, 0

    def get(self, timeout=None):
        self.polls += 1
        if self.polls == 1 or self.message is None:
            raise __import__("queue").Empty
        message, self.message = self.message, None
        return message


class DeadProcess:
    exitcode = 0

    def is_alive(self):
        return False

    def join(self, timeout=None):
        pass


def test_a_download_that_exits_right_after_saying_done_counts_as_done(tmp_path):
    from arcsong.db import Store

    store = Store(tmp_path / "arcsong.db")
    setup = fake_setup(tmp_path, store)
    process = DeadProcess()
    setup._process, setup._downloads["engine"] = process, {"state": "running"}

    setup._follow(process, LateQueue({"type": "done"}), "engine")

    assert setup._downloads["engine"]["state"] == "done"
    store.close()


def test_a_cancel_that_lands_while_the_download_finishes_is_kept(tmp_path):
    from arcsong.db import Store

    store = Store(tmp_path / "arcsong.db")
    setup = fake_setup(tmp_path, store)

    class CancelledWhileJoining(DeadProcess):
        def join(self, timeout=None):
            setup._downloads["engine"] = {"state": "cancelled"}

    process = CancelledWhileJoining()
    setup._process, setup._downloads["engine"] = process, {"state": "running"}
    queue_ = LateQueue({"type": "done"})
    queue_.polls = 1  # the message is there on the first poll

    setup._follow(process, queue_, "engine")

    assert setup._downloads["engine"]["state"] == "cancelled"
    store.close()


# --- parts ------------------------------------------------------------------------------------


def serve_parts(tmp_path, **kwargs):
    return TestClient(create_app(FAKE, tmp_path, **kwargs))


def part(setup, part_id):
    return next(p for p in setup["parts"] if p["id"] == part_id)


def test_the_covers_part_downloads_on_its_own_and_never_gates_songs(tmp_path):
    covers = FakeModels(tmp_path / "covers", preinstalled=False, download_seconds=0.5)
    with serve_parts(tmp_path, covers=covers) as client:
        setup = client.get("/api/setup").json()
        assert [p["id"] for p in setup["parts"]] == ["engine", "covers"]
        assert part(setup, "covers")["weights"]["installed"] is False
        # The engine part is installed, so songs run even though covers are missing.
        assert setup["can_render"] is True
        assert client.post("/api/jobs", json={"style": "pop"}).status_code == 201

        client.post("/api/setup/licence")
        assert client.post("/api/setup/download/covers").status_code == 200
        done = wait_setup(client, lambda s: part(s, "covers")["download"]["state"] != "running")

    assert part(done, "covers")["download"]["state"] == "done"
    assert part(done, "covers")["weights"]["installed"] is True
    assert part(done, "engine")["download"]["state"] == "idle"


def test_only_one_part_downloads_at_a_time(tmp_path):
    slow = FakeModels(tmp_path / "models", preinstalled=False, download_seconds=3.0)
    covers = FakeModels(tmp_path / "covers", preinstalled=False)
    with serve_parts(tmp_path, models=slow, covers=covers) as client:
        client.post("/api/setup/licence")
        assert client.post("/api/setup/download/engine").status_code == 200
        refused = client.post("/api/setup/download/covers")
        client.post("/api/setup/download/engine/cancel")

    assert refused.status_code == 409 and "Song model" in refused.json()["detail"]


def test_an_unknown_part_is_a_404(tmp_path):
    with serve_parts(tmp_path) as client:
        client.post("/api/setup/licence")
        assert client.post("/api/setup/download/nope").status_code == 404


def test_a_part_whose_own_check_fails_is_not_usable(tmp_path):
    broken = FakeModels(
        tmp_path / "covers", checks=[check("ffmpeg", "ffmpeg", "fail", "not found")]
    )
    with serve_parts(tmp_path, covers=broken) as client:
        setup = wait_setup(client, lambda s: not s["checking"])
        usable = client.app.state.setup.usable("covers")

    assert part(setup, "covers")["weights"]["installed"] is True
    assert usable is False  # installed, but ffmpeg is missing
    assert client_app_can_render(setup) is True


def client_app_can_render(setup):
    return setup["can_render"]


def test_the_real_transcription_weights_are_described(tmp_path):
    from arcsong.models import TranscriptionModels

    models = TranscriptionModels(tmp_path)
    state = weights_state(models)

    assert state["installed"] is False
    assert 2.5 * 2**30 < state["bytes_total"] < 2.8 * 2**30
    assert set(models.files()) == {
        "sheetsage2/config.json",
        "sheetsage2/model.safetensors",
        "mert2/config.json",
        "mert2/model.safetensors",
    }
    [ffmpeg] = models.engine_checks()
    assert ffmpeg["id"] == "ffmpeg" and ffmpeg["status"] in ("ok", "fail")


def test_a_parts_progress_counts_only_its_own_files(tmp_path):
    """The covers weights sit beside the song weights, so a part must not count the other's
    files as its own download progress."""
    from arcsong.models import TranscriptionModels, bytes_on_disk

    shared = tmp_path / "models"
    (shared / "converted").mkdir(parents=True)
    (shared / "converted" / "ar-8bit.safetensors").write_bytes(b"x" * 4096)  # a song weight
    covers = TranscriptionModels(shared)

    assert bytes_on_disk(covers) == 0

    sheet = shared / "sheetsage2"
    sheet.mkdir()
    (sheet / "config.json").write_bytes(b"y" * 2060)
    # The hub names a file it is still fetching by hash, so ask it where that file goes.
    from huggingface_hub._local_folder import get_local_download_paths

    in_flight = get_local_download_paths(sheet, "model.safetensors").incomplete_path("etag123")
    in_flight.parent.mkdir(parents=True, exist_ok=True)
    in_flight.write_bytes(b"z" * 1000)

    assert bytes_on_disk(covers) == 2060 + 1000
    assert bytes_on_disk(covers) < weights_state(covers)["bytes_total"]

    # Half-written files never push a part past its own total.
    in_flight.write_bytes(b"z" * (weights_state(covers)["bytes_total"] * 2))
    assert bytes_on_disk(covers) == weights_state(covers)["bytes_total"]


def test_the_licence_names_every_set_of_weights_arcsong_downloads(tmp_path):
    with serve_parts(tmp_path) as client:
        licence = client.get("/api/setup").json()["licence"]

    assert licence["id"] == "CC-BY-NC-4.0"
    assert any("SheetSage2" in url for url in licence["models"])
    assert any("MERT-v2-FullSong" in url for url in licence["models"])


def test_progress_survives_a_file_the_hub_renames_underneath_it(tmp_path, monkeypatch):
    """The hub renames each file as it completes; a snapshot taken mid-rename must not raise,
    or the thread following the download dies with the part stuck on "running"."""
    from arcsong.models import TranscriptionModels, bytes_on_disk

    models = TranscriptionModels(tmp_path)
    cache = tmp_path / "mert2" / ".cache" / "huggingface" / "download"
    cache.mkdir(parents=True)
    vanishing = cache / "abc.etag.incomplete"
    vanishing.write_bytes(b"x" * 10)
    real_stat = Path.stat

    def stat_but_gone(self, *args, **kwargs):
        if self == vanishing:
            raise FileNotFoundError(self)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_but_gone)

    assert bytes_on_disk(models) == 0
