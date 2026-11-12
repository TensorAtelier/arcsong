"""The RunPod worker's generator (`arcsong.runpod_app.render`), with a stand-in SDK and GPU."""

import base64
import importlib
import sys
import threading
import time
import types

import pytest


@pytest.fixture
def app(monkeypatch):
    sdk = types.ModuleType("runpod")
    sdk.Model = lambda name: types.SimpleNamespace(path="/models/yue2")
    sdk.GpuGroup = types.SimpleNamespace(ADA_24="ADA_24", AMPERE_24="AMPERE_24")

    class App:
        def __init__(self, name):
            pass

        def queue(self, **options):
            return lambda fn: fn

    sdk.App = App
    monkeypatch.setitem(sys.modules, "runpod", sdk)
    monkeypatch.delitem(sys.modules, "arcsong.runpod_app", raising=False)
    return importlib.import_module("arcsong.runpod_app")


def test_events_then_a_header_then_the_files_in_1_mb_chunks(app, monkeypatch):
    audio = bytes(range(256)) * (5 * 2**12)  # 5 MiB

    def run(job, emit, stop):
        emit({"type": "stage", "stage": "synthesis"})
        return {"files": {"audio.flac": audio, "score.abc": b"X:1"}, "audio_seconds": 9.0}

    monkeypatch.setattr(app, "_run", run)
    chunks = list(app.render({"kind": "render", "request": {}}))

    assert chunks[0] == {"type": "stage", "stage": "synthesis"}
    assert chunks[1] == {
        "type": "result",
        "audio_seconds": 9.0,
        "sizes": {"audio.flac": len(audio), "score.abc": 3},
    }
    files = [c for c in chunks if c["type"] == "file"]
    assert all(len(base64.b64decode(c["data"])) <= app.CHUNK for c in files)
    joined = b"".join(base64.b64decode(c["data"]) for c in files if c["name"] == "audio.flac")
    assert joined == audio


def test_a_cancel_stops_the_gpu_work_before_the_next_job_runs(app, monkeypatch):
    log = []
    second_started = threading.Event()

    def run(job, emit, stop):
        log.append(f"start {job['kind']}")
        if job["kind"] == "plan":
            second_started.set()
            return {"abc": "X:1"}
        emit({"type": "stage", "stage": "planning"})
        while not stop.is_set():  # tokens, until the cancel arrives
            time.sleep(0.01)
        log.append("stopped")
        time.sleep(0.2)  # unwinding still holds the GPU
        log.append("released")
        raise app.Stopped()

    monkeypatch.setattr(app, "_run", run)
    first = app.render({"kind": "render", "request": {}})
    assert next(first)["stage"] == "planning"
    first.close()  # what RunPod's cancel does to the generator

    # RunPod's runtime gave the next job its own copy of the module; the lock must still hold.
    del sys.modules["arcsong.runpod_app"]
    copy = importlib.import_module("arcsong.runpod_app")
    assert copy is not app
    monkeypatch.setattr(copy, "_run", run)
    assert list(copy.render({"kind": "plan", "request": {}}))[0]["abc"] == "X:1"
    assert second_started.is_set()
    assert log == ["start render", "stopped", "released", "start plan"]


def test_a_worker_error_reaches_the_job(app, monkeypatch):
    def run(job, emit, stop):
        raise ValueError("bad score")

    monkeypatch.setattr(app, "_run", run)
    with pytest.raises(ValueError, match="bad score"):
        list(app.render({"kind": "plan", "request": {}}))
