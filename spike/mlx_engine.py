"""mlx-Yue Engine: in-process `lyra.YuE2Pipeline` driven through its public Stage methods.

`lyra` (and MLX) are imported lazily so the harness process never touches the GPU;
only the fresh child process that runs a measurement loads them.
"""

from __future__ import annotations

import dataclasses
import json
import time
from importlib import metadata
from pathlib import Path
from typing import Any

from spike.engine import (
    STAGES,
    CancelCheck,
    EngineInfo,
    EventSink,
    RunOutput,
    StageEvent,
    ignore_event,
    never_cancelled,
)

DEFAULT_MODELS_DIR = Path("~/projects/mlx-Yue/models").expanduser()
DISTRIBUTION = "mlx-yue"
SAMPLE_RATE = 48000
_SAMPLING_KEYS = ("abc_sampling", "semantic_sampling")


def _installed_commit() -> str | None:
    try:
        direct_url = metadata.distribution(DISTRIBUTION).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not direct_url:
        return None
    return json.loads(direct_url).get("vcs_info", {}).get("commit_id")


def _mlx_peak_memory_bytes() -> int | None:
    import mlx.core as mx

    get_peak = getattr(mx, "get_peak_memory", None) or getattr(mx.metal, "get_peak_memory", None)
    return None if get_peak is None else int(get_peak())


def loads_since(before: dict, after: dict) -> dict[str, float]:
    """Weights loaded between two snapshots of `YuE2Pipeline.load_timing`, per model.

    The pipeline appends each lazy load to `<model>_load_events_seconds`.
    """
    loads = {}
    suffix = "_load_events_seconds"
    for key, events in after.items():
        if not key.endswith(suffix):
            continue
        new = tuple(events)[len(tuple(before.get(key, ()))) :]
        if new:
            loads[f"{key.removesuffix(suffix)}_load_seconds"] = float(sum(new))
    return loads


class _Stage:
    def __init__(self, stage: str, on_event: EventSink):
        self.stage, self.on_event = stage, on_event

    def __enter__(self):
        self.on_event(StageEvent(self.stage, "start"))

    def __exit__(self, *exc):
        self.on_event(StageEvent(self.stage, "end"))
        return False


class MlxYueEngine:
    def __init__(
        self,
        models_dir: Path = DEFAULT_MODELS_DIR,
        *,
        require_ac: bool = True,
        progress: bool = True,
    ):
        self.models_dir = Path(models_dir).expanduser()
        self.require_ac = require_ac
        self.progress = progress
        self.pipe: Any = None

    def info(self) -> EngineInfo:
        try:
            version = metadata.version(DISTRIBUTION)
        except metadata.PackageNotFoundError:
            version = None
        return EngineInfo(name="mlx-Yue", version=version, commit=_installed_commit())

    def load(self, precision: str) -> None:
        from lyra import YuE2Pipeline

        self.pipe = YuE2Pipeline.from_pretrained(
            str(self.models_dir / "converted"),
            vae=str(self.models_dir / "vae"),
            precision=precision,
            local_files_only=True,
            require_ac=self.require_ac,
            progress=self.progress,
        )

    def _loaded(self):
        if self.pipe is None:
            raise RuntimeError("call load(precision) before running a Stage")
        return self.pipe

    @staticmethod
    def _split(request: dict) -> tuple[dict, dict]:
        fields = {k: v for k, v in request.items() if k not in _SAMPLING_KEYS}
        sampling = {k: request.get(k) for k in _SAMPLING_KEYS}
        return fields, sampling

    def plan(
        self,
        request: dict,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ):
        fields, sampling = self._split(request)
        with _Stage(STAGES[0], on_event):
            return self._loaded().plan(
                **fields, abc_sampling=sampling["abc_sampling"], cancelled=cancelled
            )

    def generate_semantic(
        self,
        score_or_request: Any,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
        sampling: dict | None = None,
    ):
        score = score_or_request
        if isinstance(score_or_request, dict):
            sampling = score_or_request.get("semantic_sampling", sampling)
            score = self.plan(score_or_request, cancelled=cancelled, on_event=on_event)
        with _Stage(STAGES[1], on_event):
            return self._loaded().generate_semantic(score, sampling=sampling, cancelled=cancelled)

    def synthesize(
        self,
        semantic: Any,
        steps: int,
        noise: Any = None,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ):
        from lyra.pipeline import initial_noise

        pipe = self._loaded()
        pipe.generation_config = dataclasses.replace(pipe.generation_config, ode_steps=steps)
        if noise is None:
            noise = initial_noise(len(semantic.tokens), semantic.plan.request.seed)
        with _Stage(STAGES[2], on_event):
            return pipe.synthesize(semantic, cancelled=cancelled, noise=noise)

    def decode(
        self,
        latents: Any,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ):
        with _Stage(STAGES[3], on_event):
            return self._loaded().decode(latents, cancelled=cancelled)

    def run(
        self,
        request: dict,
        steps: int,
        output_dir: Path,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ) -> RunOutput:
        """A whole Take through the Stage methods, saved with mlx-Yue's own artifacts."""
        from lyra.pipeline import SongResult, initial_noise
        from yue2.storage import identity

        pipe = self._loaded()
        _, sampling = self._split(request)
        load_timing_before = dict(pipe.load_timing)
        start = time.perf_counter()
        plan = self.plan(request, cancelled=cancelled, on_event=on_event)
        semantic = self.generate_semantic(
            plan, sampling=sampling["semantic_sampling"], cancelled=cancelled, on_event=on_event
        )
        noise = initial_noise(len(semantic.tokens), plan.request.seed)
        synthesis_start = time.perf_counter()
        latents = self.synthesize(semantic, steps, noise, cancelled=cancelled, on_event=on_event)
        synthesis_seconds = time.perf_counter() - synthesis_start
        decode_start = time.perf_counter()
        audio = self.decode(latents, cancelled=cancelled, on_event=on_event)

        config = pipe.effective_config(
            plan.request, sampling["abc_sampling"], sampling["semantic_sampling"]
        )
        timing = {
            "abc": plan.timing,
            "semantic": semantic.timing,
            "nar_seconds": synthesis_seconds,
            "vae_seconds": time.perf_counter() - decode_start,
            "load": dict(pipe.load_timing),
            "e2e_seconds": time.perf_counter() - start,
        }
        request_id = identity(
            {"request": plan.request.to_dict(), "config": config, "weights": pipe.weights}
        )
        result = SongResult(
            audio, SAMPLE_RATE, semantic, latents, config, pipe.weights, timing, request_id, noise
        )
        result.save_artifacts(output_dir)
        files = sorted(p for p in output_dir.rglob("*") if p.is_file())
        return RunOutput(
            output_dir / "audio.flac",
            len(audio) / SAMPLE_RATE,
            files,
            lazy_load_seconds=loads_since(load_timing_before, pipe.load_timing),
            engine_peak_memory_bytes=_mlx_peak_memory_bytes(),
        )
