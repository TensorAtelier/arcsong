"""A scripted Engine for exercising the harness without weights (D-016)."""

from __future__ import annotations

import os
import signal
import time
import wave
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from spike.engine import (
    STAGES,
    CancelCheck,
    EngineInfo,
    EventSink,
    RunOutput,
    StageEvent,
    Unsupported,
    ignore_event,
    never_cancelled,
)

SAMPLE_RATE = 8000
SEMANTIC_TOKENS = 50
LATENT_CHANNELS = 8
# Where scripted divergent Semantic tokens start to differ.
DIVERGE_INDEX = 10
LATENT_DIVERGENCE = 0.5


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)


class FakeEngine:
    VERSION = "fake-1"

    def __init__(
        self,
        *,
        stage_seconds: float | dict[str, float] = 0.0,
        audio_seconds: float = 0.5,
        fail_in: str | None = None,
        failure: str = "error",
        load_seconds: float = 0.0,
        lazy_load_seconds: dict[str, float] | None = None,
        peak_memory_bytes: int | None = None,
        cancel_check_seconds: dict[str, float] | None = None,
        unusable_after_cancel: bool = False,
        audio_written_at_decoding_start: bool = False,
        diverge_in: str | None = None,
        diverge_between: str = "takes",
        takes_reuse_loaded_model: bool = True,
    ):
        self.stage_seconds = stage_seconds
        self.load_seconds = load_seconds
        self.lazy_load_seconds = dict(lazy_load_seconds or {})
        self.peak_memory_bytes = peak_memory_bytes
        self.audio_seconds = audio_seconds
        self.fail_in = fail_in
        self.failure = failure
        # How often each Stage looks at its cancel check (scripted cancel responsiveness).
        self.cancel_check_seconds = dict(cancel_check_seconds or {})
        # A cancel breaks the Engine until `load` runs again.
        self.unusable_after_cancel = unusable_after_cancel
        # Decoding creates the audio file before it has written any audio.
        self.audio_written_at_decoding_start = audio_written_at_decoding_start
        # Scripted non-reproducibility: the output of Stage `diverge_in` (and so every later
        # Stage) varies with the Take's index in its process ("takes": a warm process's second
        # Take differs from its first) or with the process ("processes").
        if diverge_between not in ("takes", "processes"):
            raise ValueError(f"diverge_between must be takes or processes, not {diverge_between}")
        self.diverge_in = diverge_in
        self.diverge_between = diverge_between
        self.takes = 0
        self.takes_reuse_loaded_model = takes_reuse_loaded_model
        self.precision: str | None = None
        self.cancelled_before = False
        self.usable = True

    def info(self) -> EngineInfo:
        return EngineInfo(
            name="fake",
            version=self.VERSION,
            commit=None,
            takes_reuse_loaded_model=self.takes_reuse_loaded_model,
        )

    def _maybe_fail(self, operation: str) -> None:
        if operation != self.fail_in:
            return
        match self.failure:
            case "error":
                raise RuntimeError(f"FakeEngine failure in {operation}")
            case "unsupported":
                raise Unsupported(f"FakeEngine cannot run {operation}")
            case "memory":
                raise MemoryError(f"FakeEngine out of memory in {operation}")
            case "killed":
                os.kill(os.getpid(), signal.SIGKILL)
            case "abort":
                os.abort()
            case _:
                raise ValueError(f"unknown failure {self.failure!r}")

    def _stage(
        self, stage: str, on_event: EventSink, value: Any, cancelled: CancelCheck = never_cancelled
    ) -> Any:
        on_event(StageEvent(stage, "start"))
        seconds = self.stage_seconds
        duration = seconds.get(stage, 0.0) if isinstance(seconds, dict) else seconds
        check_every = self.cancel_check_seconds.get(stage, 0.01)
        deadline = time.monotonic() + duration
        while (remaining := deadline - time.monotonic()) > 0:
            if cancelled():
                self.cancelled_before = True
                if self.unusable_after_cancel:
                    self.usable = False
                raise InterruptedError(f"FakeEngine cancelled during {stage}")
            time.sleep(min(check_every, remaining))
        on_event(StageEvent(stage, "end"))
        return value

    def load(self, precision: str) -> None:
        self._maybe_fail("load")
        time.sleep(self.load_seconds)
        self.precision = precision
        self.usable = True

    def _variation(self, stage: str) -> int:
        """0 unless `stage` is scripted to diverge; then differs per Take or per process."""
        if stage != self.diverge_in:
            return 0
        if self.diverge_between == "processes":
            return os.getpid()
        return max(self.takes - 1, 0)

    def plan(self, request, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event):
        self._maybe_fail("plan")
        score = request.get("abc") or f"X:1\nT:fake\n% seed {request.get('seed')}\n"
        if variation := self._variation(STAGES[0]):
            score += f"% variation {variation}\n"
        return self._stage(STAGES[0], on_event, {"score": score, "request": request}, cancelled)

    def generate_semantic(
        self, score_or_request, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event
    ):
        self._maybe_fail("generate_semantic")
        rng = np.random.default_rng(zlib.crc32(score_or_request["score"].encode()))
        tokens = rng.integers(0, 1000, SEMANTIC_TOKENS, dtype=np.int32)
        tokens[DIVERGE_INDEX:] += self._variation(STAGES[1])
        return self._stage(STAGES[1], on_event, tokens, cancelled)

    def synthesize(
        self,
        semantic,
        steps,
        noise=None,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event=ignore_event,
    ):
        self._maybe_fail("synthesize")
        rng = np.random.default_rng(zlib.crc32(np.asarray(semantic).tobytes()))
        latents = rng.uniform(-1, 1, (len(semantic), LATENT_CHANNELS)).astype(np.float32)
        latents[0, 0] += LATENT_DIVERGENCE * self._variation(STAGES[2])
        return self._stage(STAGES[2], on_event, latents, cancelled)

    def decode(self, latents, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event):
        self._maybe_fail("decode")
        frames = int(self.audio_seconds * SAMPLE_RATE)
        t = np.arange(frames)
        wave = 8000 * np.sin(2 * np.pi * 440 * t / SAMPLE_RATE)
        # Bounded however large a scripted Latent variation is, so it always reaches the audio.
        wave += 1000 * np.sin(np.resize(np.asarray(latents, dtype=np.float64).ravel(), frames))
        if variation := self._variation(STAGES[3]):
            wave[::2] += np.random.default_rng(variation).integers(1, 1000, len(wave[::2]))
        pcm = np.clip(np.round(wave), -32768, 32767).astype("<i2").tobytes()
        return self._stage(STAGES[3], on_event, pcm, cancelled)

    def run(
        self,
        request: dict,
        steps: int,
        output_dir: Path,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ) -> RunOutput:
        self._maybe_fail("run")
        if self.cancelled_before:
            self._maybe_fail("run_after_cancel")
        if not self.usable:
            raise RuntimeError("FakeEngine is unusable after a cancel; load it again")
        self.takes += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        score = self.plan(request, cancelled=cancelled, on_event=on_event)
        score_path = output_dir / "score.abc"
        score_path.write_text(score["score"])
        semantic = self.generate_semantic(score, cancelled=cancelled, on_event=on_event)
        semantic_path = output_dir / "semantic.npy"
        np.save(semantic_path, semantic)
        latents = self.synthesize(semantic, steps, cancelled=cancelled, on_event=on_event)
        audio_path = output_dir / "audio.wav"
        if self.audio_written_at_decoding_start:
            _write_wav(audio_path, b"")
        pcm = self.decode(latents, cancelled=cancelled, on_event=on_event)
        _write_wav(audio_path, pcm)
        latents_path = output_dir / "extra" / "latent.npy"
        latents_path.parent.mkdir(exist_ok=True)
        np.save(latents_path, latents)
        return RunOutput(
            audio_path,
            len(pcm) / 2 / SAMPLE_RATE,
            [audio_path, score_path, semantic_path, latents_path],
            lazy_load_seconds=dict(self.lazy_load_seconds),
            engine_peak_memory_bytes=self.peak_memory_bytes,
            stage_outputs={
                STAGES[0]: score_path,
                STAGES[1]: semantic_path,
                STAGES[2]: latents_path,
            },
        )
