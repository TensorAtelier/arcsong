"""The Runpod app Arcsong deploys into the user's own RunPod account (`--engine runpod`).

It runs the official `yue2` package on a 24 GB GPU as a Serverless queue endpoint, through the
Runpod SDK ("Flash"). Setup deploys it with `rp flash deploy`; `arcsong.runpod_engine` spawns
one `render` job per song and reads its stream. The 3B weights are staged on the worker's host
by `runpod.Model` (no volume, no storage bill); the 0.5 GB VAE downloads on the worker.

A job's stream carries stage and progress events, then a `result` header, then the Take's files
in 1 MB chunks: a queue job's output is capped at 10 MB and a Take is about 50 MB (X-002).
Only `runpod` is imported at module level: the worker has no Arcsong, the Mac has no torch.
"""

from __future__ import annotations

import base64
import sys
import threading
import time

import runpod

APP_NAME = "arcsong"
MODEL_REV = "8f24312f187763b9854adeec87e437e2b03bbff1"  # pinned like the Mac engine's weights
VAE = ("m-a-p/YuE2-Vae", "152733a19ad43aa67e367f9b5503ef8075bb5126")
WHEEL = (
    f"https://huggingface.co/m-a-p/YuE2-3B/resolve/{MODEL_REV}/yue2_infer-0.1.5-py3-none-any.whl"
)
# yue2's own pins minus torch: its torch==2.10.0 pin upgrades torch on the worker and breaks the
# image's torchvision (X-002); it renders on the image's 2.9.1. The wheel goes in with --no-deps.
DEPENDENCIES = [
    "transformers==4.57.6",
    "huggingface-hub==0.36.2",
    "safetensors==0.7.0",
    "tiktoken==0.12.0",
    "numpy==2.2.6",
    "soundfile==0.13.1",
    "accelerate==1.13.0",
]
SAMPLE_RATE = 48_000
CHUNK = 2**20  # the stream dropped 6 MB chunks in X-002; 1 MB ones arrived whole
PROGRESS_SECONDS = 0.5  # token counts go back at most this often

model = runpod.Model(f"m-a-p/YuE2-3B:{MODEL_REV}")
app = runpod.App(APP_NAME)
# Kept on `sys`, not in this module: RunPod's runtime gave each job its own copy of the module,
# so a module-level lock let a job start planning while a cancelled one still held the GPU, and
# CUDA graph capture failed in both (2026-11-11). One process, one lock, one loaded pipeline.
_process = sys.__dict__.setdefault("_arcsong_runpod", {"lock": threading.Lock(), "state": {}})
_lock = _process["lock"]
_state: dict = _process["state"]  # the loaded pipeline, kept while the worker stays warm


class Stopped(Exception):
    """The job was cancelled (its stream closed). The GPU work stops at the next stage boundary:
    raising from inside a generation left CUDA with a device-side assert that failed the next
    job on the same worker (2026-11-11)."""


@app.queue(
    name="render",
    # A song peaks at 9.6 GiB; either 24 GB pool will do, whichever has stock.
    gpu=[runpod.GpuGroup.ADA_24, runpod.GpuGroup.AMPERE_24],
    workers=(0, 1),  # one song at a time, like the Mac; it also caps the bill
    idle_timeout=120,  # a sketch's takes share one model load
    model=model,
    dependencies=DEPENDENCIES,
    min_cuda_version="12.8",
    execution_timeout_ms=30 * 60 * 1000,
)
def render(job: dict):
    """One job: `plan` returns the Score; `render` and `finalize` return the Take's files."""
    import queue

    events: queue.Queue = queue.Queue()
    outcome: dict = {}
    stop = threading.Event()

    def work() -> None:
        try:
            # One song on the GPU at a time: a cancelled job's thread unwinds before the next runs.
            with _lock:
                outcome["result"] = _run(job, events.put, stop)
        except BaseException as error:  # noqa: BLE001 — re-raised below, in the generator
            outcome["error"] = error
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()
    try:
        while (event := events.get()) is not None:
            yield event
    finally:
        stop.set()  # a cancel closes this generator; the GPU work stops at the next stage
    if "error" in outcome:
        raise outcome["error"]
    result = outcome["result"]
    files = result.pop("files", {})
    yield {"type": "result", **result, "sizes": {name: len(data) for name, data in files.items()}}
    for name, data in files.items():
        for start in range(0, len(data), CHUNK):
            chunk = base64.b64encode(data[start : start + CHUNK]).decode()
            yield {"type": "file", "name": name, "data": chunk}


def _pipeline():
    if "pipe" not in _state:
        import subprocess
        import sys

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--no-deps", WHEEL], check=True
        )
        import dataclasses

        from huggingface_hub import snapshot_download
        from yue2 import YuE2Pipeline
        from yue2.storage import MODEL_FILES, MODEL_LICENSES

        patterns = sorted(MODEL_FILES) + [f"licenses/{name}" for name in MODEL_LICENSES]
        vae = snapshot_download(
            VAE[0], revision=VAE[1], local_dir="/tmp/YuE2-Vae", allow_patterns=patterns
        )
        pipe = YuE2Pipeline(str(model.path), vae, device="cuda")
        _state.update(pipe=pipe, base=pipe.generation_config, replace=dataclasses.replace)
    return _state["pipe"]


def _run(job: dict, emit, stop) -> dict:
    import tempfile
    from pathlib import Path

    def check() -> None:
        if stop.is_set():
            raise Stopped()

    request = job["request"]
    check()
    pipe = _pipeline()
    from yue2.pipeline import SemanticResult, SymbolicPlan

    pipe.generation_config = _state["replace"](_state["base"], ode_steps=int(request["steps"]))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        if job["kind"] == "finalize":
            import numpy as np

            source = out / "source"
            source.mkdir()
            for name, data in job["files"].items():
                (source / Path(name).name).write_bytes(base64.b64decode(data))
            plan = SymbolicPlan.load(source)
            tokens = np.load(source / "semantic.npy", allow_pickle=False).tolist()
            semantic = SemanticResult(plan, tokens, {}, False)
        else:
            emit({"type": "stage", "stage": "planning"})
            plan = pipe.plan(
                request["style"],
                request["lyrics"],
                cot=request["mode"],
                seed=int(request["seed"]),
                abc=request.get("abc"),
                on_token=_counter("planning", emit),
            )
            if job["kind"] == "plan":
                return {"abc": plan.abc}
            check()
            emit({"type": "stage", "stage": "semantic generation"})
            tokens = _counter("semantic generation", emit)
            semantic = pipe.generate_semantic(plan, on_token=tokens)
        check()
        emit({"type": "stage", "stage": "synthesis"})
        latents = pipe.synthesize(semantic)
        check()
        emit({"type": "stage", "stage": "decoding"})
        audio = pipe.decode(latents)
        take = out / "take"
        _song_result(pipe, semantic, latents, audio).save_artifacts(take)
        return {
            "files": {p.name: p.read_bytes() for p in take.iterdir() if p.is_file()},
            "audio_seconds": len(audio) / SAMPLE_RATE,
        }


def _counter(stage: str, emit):
    count, sent = 0, 0.0

    def on_token(phase, token) -> None:
        nonlocal count, sent
        count += 1
        if time.monotonic() - sent >= PROGRESS_SECONDS:
            sent = time.monotonic()
            emit({"type": "progress", "stage": stage, "tokens": count})

    return on_token


def _song_result(pipe, semantic, latents, audio):
    """What `YuE2Pipeline.__call__` builds, from the staged calls (it has no public helper)."""
    from yue2.pipeline import SongResult
    from yue2.storage import identity

    request = semantic.plan.request
    config = pipe.effective_config(request, None, None)
    request_id = identity({"request": request.to_dict(), "config": config, "weights": pipe.weights})
    timing = {"abc": semantic.plan.timing, "semantic": semantic.timing}
    return SongResult(
        audio, SAMPLE_RATE, semantic, latents, config, pipe.weights, timing, request_id
    )
