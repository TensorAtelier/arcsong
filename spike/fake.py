"""A scripted Engine for exercising the harness without weights (D-016)."""

from __future__ import annotations

import os
import signal
import time
import wave
from pathlib import Path
from typing import Any

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


class FakeEngine:
    VERSION = "fake-1"

    def __init__(
        self,
        *,
        stage_seconds: float = 0.0,
        audio_seconds: float = 0.5,
        fail_in: str | None = None,
        failure: str = "error",
    ):
        self.stage_seconds = stage_seconds
        self.audio_seconds = audio_seconds
        self.fail_in = fail_in
        self.failure = failure
        self.precision: str | None = None

    def info(self) -> EngineInfo:
        return EngineInfo(name="fake", version=self.VERSION, commit=None)

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

    def _stage(self, stage: str, on_event: EventSink, value: Any) -> Any:
        on_event(StageEvent(stage, "start"))
        time.sleep(self.stage_seconds)
        on_event(StageEvent(stage, "end"))
        return value

    def load(self, precision: str) -> None:
        self._maybe_fail("load")
        self.precision = precision

    def plan(self, request, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event):
        self._maybe_fail("plan")
        return self._stage(STAGES[0], on_event, {"score": "X:1", "request": request})

    def generate_semantic(
        self, score_or_request, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event
    ):
        self._maybe_fail("generate_semantic")
        return self._stage(STAGES[1], on_event, [1, 2, 3])

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
        return self._stage(STAGES[2], on_event, [0.0] * len(semantic))

    def decode(self, latents, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event):
        self._maybe_fail("decode")
        frames = int(self.audio_seconds * SAMPLE_RATE)
        return self._stage(STAGES[3], on_event, bytes(frames * 2))

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
        score = self.plan(request, cancelled=cancelled, on_event=on_event)
        semantic = self.generate_semantic(score, cancelled=cancelled, on_event=on_event)
        latents = self.synthesize(semantic, steps, cancelled=cancelled, on_event=on_event)
        pcm = self.decode(latents, cancelled=cancelled, on_event=on_event)
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / "audio.wav"
        with wave.open(str(audio_path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            out.writeframes(pcm)
        return RunOutput(audio_path, len(pcm) / 2 / SAMPLE_RATE, [audio_path])
