"""The Modal app Arcsong deploys into the user's own Modal workspace (`--engine modal`).

It runs the official `yue2` PyTorch package (the wheel shipped in the model repo) on an L4, with
the weights in a Modal Volume, so a song needs no Mac GPU. Setup deploys it with
`modal deploy <this file>` and fills the Volume through `download`; `arcsong.modal_engine`
calls `Renderer.run` for each job. Only `modal` is imported at module level: the container has
no Arcsong, and the user's Mac has no torch.
"""

from __future__ import annotations

import time
from pathlib import Path

import modal

APP_NAME = "arcsong"
VOLUME_NAME = "arcsong-yue2-weights"  # the same Volume X-001 filled, so its weights are reused
WEIGHTS = Path("/weights")
WHEEL = "yue2_infer-0.1.5-py3-none-any.whl"  # the official package, shipped in the model repo
# Pinned like the Mac engine's weights, so a deploy today and one next month run the same model.
REPOS = {
    "YuE2-3B": ("m-a-p/YuE2-3B", "8f24312f187763b9854adeec87e437e2b03bbff1"),
    "YuE2-Vae": ("m-a-p/YuE2-Vae", "152733a19ad43aa67e367f9b5503ef8075bb5126"),
}
SAMPLE_RATE = 48_000
# Token counts go back at most this often; one queue write per token would flood it.
PROGRESS_SECONDS = 0.5

model_repo, model_revision = REPOS["YuE2-3B"]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("huggingface-hub==0.36.2")
    .run_commands(
        f"hf download {model_repo} {WHEEL} --revision {model_revision} --local-dir /tmp/wheel",
        f"pip install /tmp/wheel/{WHEEL}",
    )
)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME, image=image)


@app.function(volumes={WEIGHTS: volume}, timeout=30 * 60)
def download() -> dict:
    """Fetch the weights yue2 needs into the Volume; files already there are skipped."""
    from huggingface_hub import snapshot_download
    from yue2.storage import MODEL_FILES, MODEL_LICENSES

    patterns = sorted(MODEL_FILES) + ["model-?????-of-?????.safetensors"]
    patterns += [f"licenses/{name}" for name in MODEL_LICENSES]
    start = time.perf_counter()
    for name, (repo, revision) in REPOS.items():
        snapshot_download(
            repo, revision=revision, local_dir=WEIGHTS / name, allow_patterns=patterns
        )
    volume.commit()
    total = sum(p.stat().st_size for p in WEIGHTS.rglob("*.safetensors"))
    return {"seconds": round(time.perf_counter() - start, 1), "bytes": total}


@app.cls(
    # Cheapest first; Modal takes the next when none is free (a song peaks at 9.6 GiB).
    gpu=["L4", "A10G", "L40S"],
    volumes={WEIGHTS: volume},
    timeout=30 * 60,
    max_containers=1,  # one song at a time, like the Mac; it also caps the bill
    scaledown_window=5 * 60,  # a sketch's takes share one model load
)
class Renderer:
    @modal.enter()
    def load(self) -> None:
        import dataclasses

        from yue2 import YuE2Pipeline

        self.pipe = YuE2Pipeline(WEIGHTS / "YuE2-3B", WEIGHTS / "YuE2-Vae", device="cuda")
        self.base = self.pipe.generation_config
        self.replace = dataclasses.replace

    @modal.method()
    def run(self, job: dict, events: modal.Queue) -> dict:
        """One job: `plan` returns the Score; `render` and `finalize` return the Take's files.
        Stage and progress events go to `events` while it runs."""
        import tempfile

        from yue2.pipeline import SemanticResult, SymbolicPlan

        def emit(event: dict) -> None:
            events.put(event)

        request = job["request"]
        pipe = self.pipe
        pipe.generation_config = self.replace(self.base, ode_steps=request["steps"])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            if job["kind"] == "finalize":
                source = out / "source"
                source.mkdir()
                for name, data in job["files"].items():
                    (source / name).write_bytes(data)
                import numpy as np

                plan = SymbolicPlan.load(source)
                tokens = np.load(source / "semantic.npy", allow_pickle=False).tolist()
                semantic = SemanticResult(plan, tokens, {}, False)
            else:
                emit({"type": "stage", "stage": "planning"})
                plan = pipe.plan(
                    request["style"],
                    request["lyrics"],
                    cot=request["mode"],
                    seed=request["seed"],
                    abc=request.get("abc"),
                    on_token=_counter("planning", emit),
                )
                if job["kind"] == "plan":
                    return {"abc": plan.abc}
                emit({"type": "stage", "stage": "semantic generation"})
                semantic = pipe.generate_semantic(
                    plan, on_token=_counter("semantic generation", emit)
                )
            emit({"type": "stage", "stage": "synthesis"})
            latents = pipe.synthesize(semantic)
            emit({"type": "stage", "stage": "decoding"})
            audio = pipe.decode(latents)
            song = _song_result(pipe, semantic, latents, audio)
            take = out / "take"
            song.save_artifacts(take)
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
