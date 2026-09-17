"""The mlx-Yue Engine: `lyra.YuE2Pipeline` driven through its staged API in the worker process.

`lyra` (and MLX) are imported lazily, so only the worker process ever touches the GPU.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from pathlib import Path
from typing import Any

from songloom.engine import STAGES, CancelCheck, Cancelled, Emit, TakeOutput

MODELS_ENV = "SONGLOOM_MLX_MODELS"
DEFAULT_MODELS_DIR = "~/projects/mlx-Yue/models"
SAMPLE_RATE = 48_000


def models_dir(override: str | Path | None = None) -> Path:
    chosen = override or os.environ.get(MODELS_ENV) or DEFAULT_MODELS_DIR
    return Path(chosen).expanduser()


class MlxYueEngine:
    """Keeps one pipeline loaded and reuses it across Takes; a Take asking for the other
    precision reloads it."""

    def __init__(self, models: str | Path | None = None, require_ac: bool = True):
        self.models = models_dir(models)
        self.require_ac = require_ac
        self._pipe: Any = None
        self._precision: str | None = None

    def load(self, precision: str = "8bit") -> None:
        if self._pipe is not None and self._precision == precision:
            return
        from lyra import YuE2Pipeline

        self._pipe = None  # release the old weights before loading new ones
        self._pipe = YuE2Pipeline.from_pretrained(
            str(self.models / "converted"),
            vae=str(self.models / "vae"),
            precision=precision,
            local_files_only=True,
            require_ac=self.require_ac,
        )
        self._precision = precision

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        from lyra.pipeline import SongResult, initial_noise
        from yue2.storage import identity

        self.load(request["precision"])
        pipe = self._pipe
        pipe.generation_config = dataclasses.replace(
            pipe.generation_config, ode_steps=request["steps"]
        )
        guard = _cancel_guard(cancelled)

        emit({"type": "stage", "stage": STAGES[0]})
        plan = guard(
            pipe.plan,
            request["style"],
            request["lyrics"],
            cot=request["mode"],
            seed=request["seed"],
            cancelled=cancelled,
        )
        emit({"type": "stage", "stage": STAGES[1]})
        semantic = guard(pipe.generate_semantic, plan, cancelled=cancelled)
        emit({"type": "stage", "stage": STAGES[2]})
        noise = initial_noise(len(semantic.tokens), plan.request.seed)
        latents = guard(pipe.synthesize, semantic, cancelled=cancelled, noise=noise)
        emit({"type": "stage", "stage": STAGES[3]})
        audio = guard(pipe.decode, latents, cancelled=cancelled)
        if cancelled():
            raise Cancelled("decoding")

        config = pipe.effective_config(plan.request, None, None)
        request_id = identity(
            {"request": plan.request.to_dict(), "config": config, "weights": pipe.weights}
        )
        result = SongResult(
            audio, SAMPLE_RATE, semantic, latents, config, pipe.weights,
            {"abc": plan.timing, "semantic": semantic.timing}, request_id, noise,
        )  # fmt: skip
        if out_dir.exists():
            shutil.rmtree(out_dir)  # leftovers of an interrupted Take; never a finished one
        result.save_artifacts(out_dir)
        return TakeOutput(out_dir / "audio.flac", len(audio) / SAMPLE_RATE)


def _cancel_guard(cancelled: CancelCheck):
    """Call a Stage method, turning mlx-Yue's own cancellation error into `Cancelled`."""

    def call(method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:
            if cancelled():
                raise Cancelled(method.__name__) from None
            raise

    return call
