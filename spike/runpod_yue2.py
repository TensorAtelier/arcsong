"""X-002: render one YuE2 song on RunPod Serverless through the Runpod SDK (Flash).

Standalone measurement, not product code (see docs/product/backlog.md § X-002). It answers the
two unknowns a RunPod engine has that Modal didn't:

- yue2 0.1.5 pins torch 2.10.0, but Flash GPU workers run the image's torch (2.9.1) and drop
  any torch pin. Does yue2 render on it?
- A queue job's result is capped at 10 MB and a finished Take is ~50 MB. Does a generator that
  yields the files in chunks bring them all back?

    uv run --no-project --python 3.12 --with 'runpod>=2.0' rp flash dev spike/runpod_yue2.py --once

The 3B model is staged on the host by `runpod.Model` (no volume); the 0.5 GB VAE downloads on
the worker. Output (Take files, timings JSON) lands in spike/runs/x002/.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import runpod

MODEL_REV = "8f24312f187763b9854adeec87e437e2b03bbff1"
VAE = ("m-a-p/YuE2-Vae", "152733a19ad43aa67e367f9b5503ef8075bb5126")
WHEEL = f"https://huggingface.co/m-a-p/YuE2-3B/resolve/{MODEL_REV}/yue2_infer-0.1.5-py3-none-any.whl"
# yue2's own pins minus torch: its torch==2.10.0 pin would upgrade torch on the worker and leave
# the image's torchvision broken. The wheel itself goes in with --no-deps inside the function.
DEPENDENCIES = [
    "transformers==4.57.6", "huggingface-hub==0.36.2", "safetensors==0.7.0", "tiktoken==0.12.0",
    "numpy==2.2.6", "soundfile==0.13.1", "accelerate==1.13.0",
]
CHUNK = 2**20  # raw bytes per yielded chunk; the stream dropped 6 MB chunks (X-002 run 5)

model = runpod.Model(f"m-a-p/YuE2-3B:{MODEL_REV}")
app = runpod.App("arcsong-x002f")  # dev templates linger ~90 min after a session

LYRICS = """[Verse]
Rain against the window of the corner room
Coffee going cold beside the afternoon

[Chorus]
Stay a little longer, let the record play
Nothing out there needs us till the break of day"""
REQUEST = dict(
    style="English, late-night lo-fi soul, warm Rhodes, brushed drums, soft male vocal",
    lyrics=LYRICS,
    seed=4242,
    steps=32,
)


@app.queue(
    name="render",
    gpu=[runpod.GpuGroup.ADA_24, runpod.GpuGroup.AMPERE_24],
    workers=(0, 1),
    idle_timeout=30,
    model=model,
    dependencies=DEPENDENCIES,
    min_cuda_version="12.8",
    execution_timeout_ms=20 * 60 * 1000,
)
def render(style: str, lyrics: str, seed: int, steps: int):
    t0 = time.time()
    import dataclasses
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", WHEEL], check=True)
    import tempfile

    import torch
    from huggingface_hub import snapshot_download
    from yue2 import YuE2Pipeline
    from yue2.storage import MODEL_FILES, MODEL_LICENSES

    info = {"gpu": torch.cuda.get_device_name(0), "torch": torch.__version__, "stages": {}}
    print("worker:", info, flush=True)

    def stage(name, fn):
        start = time.perf_counter()
        result = fn()
        info["stages"][name] = round(time.perf_counter() - start, 2)
        return result

    vae = stage(
        "vae_download",
        lambda: snapshot_download(
            VAE[0], revision=VAE[1], local_dir="/tmp/YuE2-Vae",
            allow_patterns=sorted(MODEL_FILES) + [f"licenses/{n}" for n in MODEL_LICENSES],
        ),
    )
    info["model_path"] = str(model.path)
    pipe = stage("load", lambda: YuE2Pipeline(str(model.path), vae, device="cuda"))
    pipe.generation_config = dataclasses.replace(pipe.generation_config, ode_steps=int(steps))
    plan = stage("planning", lambda: pipe.plan(style, lyrics, cot="full", seed=int(seed)))
    semantic = stage("semantic", lambda: pipe.generate_semantic(plan))
    latents = stage("synthesis", lambda: pipe.synthesize(semantic))
    audio = stage("decoding", lambda: pipe.decode(latents))
    info["audio_seconds"] = round(len(audio) / 48000, 1)
    with tempfile.TemporaryDirectory() as tmp:
        import soundfile as sf

        out = Path(tmp)
        sf.write(out / "audio.flac", audio, 48000, format="FLAC", subtype="PCM_24")
        (out / "score.abc").write_text(plan.abc or "")
        files = {p.name: p.read_bytes() for p in out.iterdir()}
    info["in_function_s"] = round(time.time() - t0, 2)
    yield {"info": info, "sizes": {k: len(v) for k, v in files.items()}}
    for name, data in files.items():
        for start in range(0, len(data), CHUNK):
            yield {"file": name, "data": base64.b64encode(data[start : start + CHUNK]).decode()}


@runpod.local_entrypoint
def main():
    called = time.time()
    out = Path("spike/runs/x002")
    out.mkdir(parents=True, exist_ok=True)
    parts: dict[str, list[bytes]] = {}
    header = {}
    # `render.stream()` gives up after 300 s; a cold worker spends ~4 min unpacking the image alone.
    job = render.spawn(**REQUEST)
    print("job:", job.id, flush=True)
    for chunk in job.stream(timeout=25 * 60):
        if "info" in chunk:
            header = chunk
            print("worker:", json.dumps(chunk), flush=True)
        else:
            parts.setdefault(chunk["file"], []).append(base64.b64decode(chunk["data"]))
    got = {name: b"".join(chunks) for name, chunks in parts.items()}
    for name, data in got.items():
        (out / name).write_bytes(data)
    header["client_wall_s"] = round(time.time() - called, 2)
    header["received"] = {k: len(v) for k, v in got.items()}
    header["complete"] = header["received"] == header.get("sizes")
    header["job_status"] = job.status()
    try:  # what the stored result holds, apart from the stream
        stored = job.result(timeout=60)
        header["stored_chunks"] = len(stored)
        header["stored_bytes"] = sum(len(c.get("data", "")) for c in stored)
    except Exception as error:
        header["stored_error"] = f"{type(error).__name__}: {error}"[-500:]
    if not header["complete"]:
        try:  # a failed generator job ends its stream quietly; its error is in the result
            header["job_result"] = str(job.result(timeout=30))[:300]
        except Exception as error:
            header["job_error"] = f"{type(error).__name__}: {error}"[-2500:]
    (out / "x002.json").write_text(json.dumps(header, indent=2))
    print(json.dumps(header, indent=2))
    if not header["complete"]:
        raise SystemExit("chunks missing")
