"""X-001: render one YuE2 song on a Modal L4 with the official `yue2` PyTorch package.

Standalone measurement, not product code (see docs/product/backlog.md § X-001).

    modal run spike/modal_yue2.py::download   # once: original weights -> Volume (CPU only)
    modal run spike/modal_yue2.py             # one cold L4 container: plan, semantic,
                                              # then 8- and 32-step synthesis + decode

The two step counts share one plan and one set of semantic tokens (same request and seed,
so they would be identical anyway): exactly Arcsong's Draft -> Final shape. The FLACs, the
Score and a JSON of timings land in --out.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import modal

WHEEL = "yue2_infer-0.1.5-py3-none-any.whl"  # the official package, shipped in the model repo
REPOS = {"YuE2-3B": "m-a-p/YuE2-3B", "YuE2-Vae": "m-a-p/YuE2-Vae"}
WEIGHTS = Path("/weights")
GPU = "L4"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("huggingface-hub==0.36.2", "nvidia-ml-py==13.610.43")
    .run_commands(f"hf download m-a-p/YuE2-3B {WHEEL} --local-dir /tmp/wheel",
                  f"pip install /tmp/wheel/{WHEEL}")
)
volume = modal.Volume.from_name("arcsong-yue2-weights", create_if_missing=True)
app = modal.App("arcsong-x001", image=image)

LYRICS = """[Verse]
Rain against the window of the corner room
Coffee going cold beside the afternoon

[Chorus]
Stay a little longer, let the record play
Nothing out there needs us till the break of day"""
REQUEST = dict(style="English, late-night lo-fi soul, warm Rhodes, brushed drums, soft male vocal",
               lyrics=LYRICS, cot="full", seed=4242, id="x001")


@app.function(volumes={WEIGHTS: volume}, timeout=30 * 60, max_containers=1)
def download():
    """Fetch the original weights into the Volume (yue2.storage.resolve_model's file set)."""
    from huggingface_hub import snapshot_download
    from yue2.storage import MODEL_FILES, MODEL_LICENSES
    patterns = sorted(MODEL_FILES) + ["model-?????-of-?????.safetensors"]
    patterns += [f"licenses/{name}" for name in MODEL_LICENSES]
    start = time.perf_counter()
    for name, repo in REPOS.items():
        snapshot_download(repo, local_dir=WEIGHTS / name, allow_patterns=patterns)
    volume.commit()
    sizes = {str(p.relative_to(WEIGHTS)): p.stat().st_size for p in WEIGHTS.rglob("*.safetensors")}
    return {"seconds": round(time.perf_counter() - start, 1), "files": sizes}


class VramPeak:
    """Sample whole-GPU memory in use (NVML) every 50 ms."""

    def __init__(self):
        import threading

        import pynvml
        pynvml.nvmlInit()
        self._nvml, self._handle = pynvml, pynvml.nvmlDeviceGetHandleByIndex(0)
        self.peak, self._stop = 0, threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop.wait(0.05):
            self.peak = max(self.peak, self._nvml.nvmlDeviceGetMemoryInfo(self._handle).used)

    def take(self):
        """Peak since the last take, in GiB."""
        peak, self.peak = self.peak, 0
        return round(peak / 2**30, 2)


@app.function(gpu=GPU, volumes={WEIGHTS: volume}, timeout=30 * 60, max_containers=1)
def render(steps_list: list[int], request: dict):
    t0 = time.time()
    import dataclasses
    import io

    import soundfile as sf
    import torch
    import yue2
    from yue2 import YuE2Pipeline
    vram = VramPeak()
    out = {"gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
           "yue2": yue2.__version__, "import_s": round(time.time() - t0, 2), "stages": {}}

    def stage(name, fn):
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        result = fn()
        torch.cuda.synchronize()
        out["stages"][name] = {
            "seconds": round(time.perf_counter() - start, 2),
            "torch_peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
            "nvml_peak_used_gib": vram.take()}
        return result

    pipe = stage("load_verify", lambda: YuE2Pipeline(WEIGHTS / "YuE2-3B", WEIGHTS / "YuE2-Vae",
                                                     device="cuda"))
    stage("load_model", pipe._load_model)
    plan = stage("planning", lambda: pipe.plan(**request))
    semantic = stage("semantic", lambda: pipe.generate_semantic(plan))
    out["token_timing"] = {"plan": plan.timing, "semantic": semantic.timing}
    audio_files, base = {}, pipe.generation_config
    for steps in steps_list:
        pipe.generation_config = dataclasses.replace(base, ode_steps=steps)
        latents = stage(f"synthesis_{steps}", lambda: pipe.synthesize(semantic))
        audio = stage(f"decoding_{steps}", lambda latents=latents: pipe.decode(latents))
        buffer = io.BytesIO()
        sf.write(buffer, audio, 48000, format="FLAC", subtype="PCM_24")
        audio_files[steps] = buffer.getvalue()
        out[f"audio_seconds_{steps}"] = round(len(audio) / 48000, 1)
    pipe.close()
    out["in_function_s"] = round(time.time() - t0, 2)
    # JSON round trip: torch types (TorchVersion, enums) would not unpickle on a Mac without torch.
    return json.loads(json.dumps(out, default=str)), audio_files, plan.abc, t0


@app.local_entrypoint()
def main(steps: str = "8,32", out: str = "spike/runs/x001", request: str = ""):
    """--request: a JSON file with style/lyrics/seed (e.g. YuE2's examples/tonight-awake.json)."""
    chosen = dict(REQUEST)
    if request:
        data = json.loads(Path(request).read_text())
        chosen.update({k: data[k] for k in ("style", "lyrics", "seed") if k in data})
    called = time.time()
    result, audio_files, abc, entered = render.remote([int(s) for s in steps.split(",")], chosen)
    result["client_wall_s"] = round(time.time() - called, 2)
    # Call -> function entry: container boot + image. Mac and container clocks differ by ~1 s.
    result["cold_start_s"] = round(entered - called, 2)
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    for steps_count, data in audio_files.items():
        (directory / f"x001-l4-{steps_count}step.flac").write_bytes(data)
    (directory / "x001.abc").write_text(abc or "")
    (directory / "x001-l4.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
