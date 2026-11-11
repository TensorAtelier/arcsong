"""The RunPod Engine's local half and Setup, over stand-ins (no RunPod account)."""

import base64
import time

import pytest

from arcsong.engine import Cancelled
from arcsong.modal_engine import PLAN_FILES
from arcsong.models import RunPodModels
from arcsong.runpod_engine import RunPodEngine

REQUEST = {"style": "pop", "lyrics": "", "mode": "full", "seed": 1, "steps": 8, "abc": None}
TAKE = {"audio.flac": b"f" * 2500, "score.abc": b"X:1", "semantic.npy": b"tokens"}


def stream_of(result, files, events=({"type": "stage", "stage": "synthesis"},), size=1000):
    """What `runpod_app.render` yields: events, a result header, then the files in chunks."""
    chunks = list(events)
    chunks.append({"type": "result", **result, "sizes": {n: len(d) for n, d in files.items()}})
    for name, data in files.items():
        for start in range(0, len(data), size):
            piece = base64.b64encode(data[start : start + size]).decode()
            chunks.append({"type": "file", "name": name, "data": piece})
    return chunks


class FakeJob:
    def __init__(self, chunks, status="COMPLETED", error=None, delay=0.0):
        self.chunks, self._status, self.error, self.delay = chunks, status, error, delay
        self.cancelled = False

    def stream(self, timeout):
        for chunk in self.chunks:
            time.sleep(self.delay)
            yield chunk

    def status(self):
        return self._status

    def result(self, timeout):
        if self.error:
            raise self.error
        return self.chunks

    def cancel(self):
        self.cancelled = True


def engine_with(job):
    jobs = []

    class Queue:
        def spawn(self, **kwargs):
            jobs.append(kwargs["job"])
            return job

    engine = RunPodEngine(remote=None)
    engine._queue = Queue()
    engine._remote = engine._call
    return engine, jobs


def test_a_render_reassembles_the_chunked_take_and_relays_events(tmp_path):
    engine, jobs = engine_with(FakeJob(stream_of({"audio_seconds": 4.5}, TAKE)))
    events = []

    take = engine.render(REQUEST, tmp_path / "take", lambda: False, events.append)

    assert take.audio_seconds == 4.5
    assert {p.name: p.read_bytes() for p in (tmp_path / "take").iterdir()} == TAKE
    assert [e["stage"] for e in events] == ["planning", "synthesis"]
    assert jobs == [{"kind": "render", "request": REQUEST}]


def test_a_plan_returns_its_score(tmp_path):
    engine, _ = engine_with(FakeJob(stream_of({"abc": "X:1"}, {})))
    assert engine.plan_only(REQUEST, lambda: False, print).abc == "X:1"


def test_a_final_sends_the_drafts_files_as_base64(tmp_path):
    draft = tmp_path / "draft"
    draft.mkdir()
    for name in (*PLAN_FILES, "score.abc"):
        (draft / name).write_bytes(name.encode())
    engine, jobs = engine_with(FakeJob(stream_of({"audio_seconds": 4.5}, TAKE)))

    engine.finalize(draft, REQUEST, tmp_path / "final", lambda: False, print)

    sent = jobs[0]["files"]
    assert sorted(sent) == sorted([*PLAN_FILES, "score.abc"])
    assert base64.b64decode(sent["plan.json"]) == b"plan.json"


def test_a_cancel_cancels_the_runpod_job(tmp_path):
    job = FakeJob(stream_of({"audio_seconds": 4.5}, TAKE), delay=5)
    engine, _ = engine_with(job)
    with pytest.raises(Cancelled):
        engine.render(REQUEST, tmp_path / "take", lambda: True, print)
    assert job.cancelled


def test_a_failed_job_says_why_in_one_line(tmp_path):
    error = RuntimeError("Traceback (most recent call last):\n  ...\nValueError: bad score\n")
    engine, _ = engine_with(FakeJob([], status="FAILED", error=error))
    with pytest.raises(RuntimeError, match=r"^RunPod: ValueError: bad score$"):
        engine.plan_only(REQUEST, lambda: False, print)


def test_a_job_cancelled_on_runpod_or_cut_short_is_a_plain_failure(tmp_path):
    engine, _ = engine_with(FakeJob([], status="CANCELLED"))
    with pytest.raises(RuntimeError, match="stopped on RunPod"):
        engine.render(REQUEST, tmp_path / "take", lambda: False, print)

    short = stream_of({"audio_seconds": 4.5}, TAKE)[:-1]  # the last chunk never arrived
    engine, _ = engine_with(FakeJob(short))
    with pytest.raises(RuntimeError, match="incomplete"):
        engine.render(REQUEST, tmp_path / "take", lambda: False, print)


def test_a_mac_draft_is_refused_naming_runpod(tmp_path):
    (tmp_path / "mac").mkdir()
    (tmp_path / "mac" / "noise.npy").write_bytes(b"")
    engine, _ = engine_with(FakeJob([]))
    with pytest.raises(ValueError, match="RunPod can't continue"):
        engine.finalize(tmp_path / "mac", REQUEST, tmp_path / "final", lambda: False, print)


def test_setup_finds_runpods_own_key(tmp_path, monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "runpod", types.ModuleType("runpod"))  # CI has no extras
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    config = tmp_path / "config.toml"
    models = RunPodModels(tmp_path / "runpod", config=config)
    assert models.engine_checks()[0]["status"] == "fail"  # no file

    config.write_text('apikey = ""\napiurl = "https://api.runpod.io/graphql"\n')
    assert models.engine_checks()[0]["status"] == "fail"  # `runpodctl doctor` left it empty

    config.write_text('apikey = "rpa_x"\n')
    assert models.engine_checks()[0]["status"] == "ok"

    config.unlink()
    monkeypatch.setenv("RUNPOD_API_KEY", "rpa_y")
    assert models.engine_checks()[0]["status"] == "ok"
    assert models.remote == "RunPod"


def test_setup_deploys_from_a_folder_holding_only_the_app(tmp_path, monkeypatch):
    import subprocess

    seen = {}

    def run(args, cwd, **kwargs):
        from pathlib import Path

        seen["files"] = sorted(p.name for p in Path(cwd).iterdir())
        seen["args"] = args[3:]
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    models = RunPodModels(tmp_path / "runpod")
    phases = []
    models.download(phases.append)

    assert seen["files"] == ["runpod_app.py"]
    assert seen["args"] == ["flash", "deploy", "--python-version", "3.12"]
    assert phases == ["deploying"]
    assert sorted(p.name for p in (tmp_path / "runpod").iterdir()) == sorted(models.files())


def test_setup_asks_for_the_client_when_it_is_missing(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "runpod", None)  # import fails
    [missing] = RunPodModels(tmp_path / "runpod").engine_checks()
    assert missing["status"] == "fail" and "arcsong[runpod]" in missing["detail"]


def test_a_failed_deploy_is_one_line(tmp_path, monkeypatch):
    import subprocess

    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Error:\n  unauthorized\n")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match=r"^Error: unauthorized$"):
        RunPodModels(tmp_path / "runpod").download(print)
