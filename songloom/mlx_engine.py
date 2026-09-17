"""The mlx-Yue Engine: `lyra.YuE2Pipeline` driven through its staged API in the worker process.

`lyra` (and MLX) are imported lazily, so only the worker process ever touches the GPU.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path
from typing import Any

from songloom.engine import (
    STAGES,
    TRANSCRIBING,
    CancelCheck,
    Cancelled,
    Emit,
    ScoreOutput,
    TakeOutput,
)
from songloom.progress import StderrCounts

SAMPLE_RATE = 48_000
# Both melody voices, no chords: what a cover re-sings (mlx-Yue's other tasks add chord symbols
# the render ignores).
TRANSCRIPTION_TASK = "melody-full"


class MlxYueEngine:
    """Keeps one pipeline loaded and reuses it across Takes; a Take asking for the other
    precision reloads it."""

    def __init__(
        self,
        models: str | Path,
        require_ac: bool = True,
        transcription_models: str | Path | None = None,
    ):
        self.models = Path(models).expanduser()
        # The covers weights sit beside the song weights unless told otherwise.
        self.transcription_models = Path(transcription_models or models).expanduser()
        self.require_ac = require_ac
        self._pipe: Any = None
        self._sheetsage: Any = None
        self._generation_config: Any = None
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
        # The weights' own settings; a Final swaps in its Draft's, so renders start from these.
        self._generation_config = self._pipe.generation_config
        self._precision = precision

    def transcribe(
        self,
        audio: Path,
        request: dict[str, Any],
        out_dir: Path,
        cancelled: CancelCheck,
        emit: Emit,
    ) -> ScoreOutput:
        """SheetSage2 over the upload: the Score comes back as the same native two-voice ABC a
        planned Score uses, so it renders and edits like any other."""
        from lyra.transcription.pipeline import transcribe

        emit({"type": "stage", "stage": TRANSCRIBING})
        if out_dir.exists():
            shutil.rmtree(out_dir)  # transcription insists on a fresh directory

        def run():
            # Loading the model is inside the guard: the first cover spends minutes here, and
            # mlx-Yue's own InterruptedError has to read as a cancel, not a failure.
            model = self._transcriber(cancelled)
            return transcribe(
                audio,
                out_dir,
                model=model,
                offline=True,
                task=TRANSCRIPTION_TASK,
                cancelled=cancelled,
                progress=_window_reporter(emit),
            )

        result = _cancel_guard(cancelled)(run)
        abc = result.get("abc")
        if result.get("status") != "complete" or not abc:
            raise ValueError(result.get("abc_error") or "the recording produced no Score")
        return ScoreOutput(abc)

    def _transcriber(self, cancelled: CancelCheck):
        """SheetSage2 and its 2.4 GB MERT2 parent, loaded once and kept for later covers."""
        if self._sheetsage is None:
            from lyra.transcription.model import SheetSage2

            self._sheetsage = SheetSage2.from_pretrained(
                str(self.transcription_models / "sheetsage2"),
                str(self.transcription_models / "mert2"),
                offline=True,
                cancelled=cancelled,
            )
        return self._sheetsage

    def plan_only(self, request: dict[str, Any], cancelled: CancelCheck, emit: Emit) -> ScoreOutput:
        """The planning Stage alone: seconds, and nothing is written to disk."""
        self.load(request["precision"])
        # Like render(): start from the weights' settings, not a previous Final's.
        self._pipe.generation_config = self._generation_config
        emit({"type": "stage", "stage": STAGES[0]})
        plan = self._plan(self._pipe, request, cancelled, emit)
        if cancelled():
            raise Cancelled(STAGES[0])
        if plan.abc is None:
            raise ValueError("this planning mode writes no Score")
        return ScoreOutput(plan.abc)

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        from lyra.pipeline import initial_noise

        self.load(request["precision"])
        pipe = self._pipe
        pipe.generation_config = dataclasses.replace(
            self._generation_config, ode_steps=request["steps"]
        )
        guard = _cancel_guard(cancelled)

        emit({"type": "stage", "stage": STAGES[0]})
        plan = self._plan(pipe, request, cancelled, emit)
        emit({"type": "stage", "stage": STAGES[1]})
        semantic = guard(
            pipe.generate_semantic,
            plan,
            cancelled=cancelled,
            on_token=_token_counter(STAGES[1], emit),
        )
        emit({"type": "stage", "stage": STAGES[2]})
        noise = initial_noise(len(semantic.tokens), plan.request.seed)
        # Synthesis exposes no progress callback; yue2's N/total lines on stderr are the only
        # signal (M0: one line per 5 s through a pipe).
        with StderrCounts(_step_reporter(STAGES[2], emit)):
            latents = guard(pipe.synthesize, semantic, cancelled=cancelled, noise=noise)
        return self._decode_and_save(semantic, noise, latents, out_dir, cancelled, emit)

    def finalize(
        self,
        source_dir: Path,
        request: dict[str, Any],
        out_dir: Path,
        cancelled: CancelCheck,
        emit: Emit,
    ) -> TakeOutput:
        """The Draft's saved Semantic tokens and noise, re-synthesized at the request's steps with
        the Draft's own generation settings (M0: the result is bit-identical to a direct render).
        mlx-Yue's `load_artifacts` verifies the saved Take before it is used."""
        from lyra.artifacts import load_artifacts
        from yue2.protocol import GenerationConfig

        # Read the Draft before a possibly slow model load, and say plainly if it is gone.
        if not source_dir.is_dir():
            raise FileNotFoundError("its Draft was deleted")
        try:
            saved = load_artifacts(source_dir)
        except FileNotFoundError:
            if not source_dir.is_dir():
                raise FileNotFoundError("its Draft was deleted") from None
            raise
        self.load(request["precision"])
        pipe = self._pipe
        if saved.noise is None:
            raise ValueError(f"the Draft in {source_dir} kept no synthesis noise")
        pipe.generation_config = dataclasses.replace(
            GenerationConfig.from_dict(saved.config["generation"]), ode_steps=request["steps"]
        )
        guard = _cancel_guard(cancelled)
        emit({"type": "stage", "stage": STAGES[2]})
        with StderrCounts(_step_reporter(STAGES[2], emit)):
            latents = guard(pipe.synthesize, saved.semantic, cancelled=cancelled, noise=saved.noise)
        return self._decode_and_save(saved.semantic, saved.noise, latents, out_dir, cancelled, emit)

    def _plan(self, pipe, request: dict[str, Any], cancelled: CancelCheck, emit: Emit):
        """Write the Score, or take the one the request carries (upstream turns a request's
        `abc` into the plan without generating, so this Stage is instant)."""
        return _cancel_guard(cancelled)(
            pipe.plan,
            request["style"],
            request["lyrics"],
            cot=request["mode"],
            seed=request["seed"],
            abc=request.get("abc"),
            cancelled=cancelled,
            on_token=_token_counter(STAGES[0], emit),
        )

    def _decode_and_save(self, semantic, noise, latents, out_dir, cancelled, emit) -> TakeOutput:
        from lyra.pipeline import SongResult
        from yue2.storage import identity

        pipe = self._pipe
        emit({"type": "stage", "stage": STAGES[3]})
        audio = _cancel_guard(cancelled)(pipe.decode, latents, cancelled=cancelled)
        if cancelled():
            raise Cancelled("decoding")

        plan = semantic.plan
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


def _window_reporter(emit: Emit):
    """Transcription works window by window; report them as the Stage's progress."""

    def on_progress(event: dict[str, Any]) -> None:
        if "windows" in event:
            emit(
                {
                    "type": "progress",
                    "stage": TRANSCRIBING,
                    "completed": event["window"],
                    "total": event["windows"],
                }
            )

    return on_progress


def _token_counter(stage: str, emit: Emit):
    count = 0

    def on_token(phase, token) -> None:
        nonlocal count
        count += 1
        emit({"type": "progress", "stage": stage, "tokens": count})

    return on_token


def _step_reporter(stage: str, emit: Emit):
    def on_count(completed: int, total: int) -> None:
        emit({"type": "progress", "stage": stage, "completed": completed, "total": total})

    return on_count


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
