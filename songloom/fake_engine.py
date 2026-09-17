"""A stand-in Engine for tests and UI work: scripted Stages, progress and a short tone."""

from __future__ import annotations

import math
import struct
import time
import wave
from pathlib import Path
from typing import Any

from songloom.engine import STAGES, CancelCheck, Cancelled, Emit, TakeOutput

SAMPLE_RATE = 48_000
TICK = 0.005


class FakeEngine:
    """Each Stage lasts `stage_seconds`. Planning and semantic generation report a growing
    token count; synthesis reports `steps` of the request's Synthesis steps, like mlx-Yue."""

    def __init__(
        self,
        stage_seconds: float = 0.02,
        audio_seconds: float = 1.0,
        tokens_per_stage: int = 20,
        fail_in: str | None = None,
    ):
        self.stage_seconds = stage_seconds
        self.audio_seconds = audio_seconds
        self.tokens_per_stage = tokens_per_stage
        self.fail_in = fail_in

    def load(self) -> None:
        pass

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        steps = request.get("steps", 8)
        for stage in STAGES:
            if cancelled():
                raise Cancelled(stage)
            emit({"type": "stage", "stage": stage})
            if self.fail_in == stage:
                raise RuntimeError(f"fake failure in {stage}")
            updates = {STAGES[0]: self.tokens_per_stage, STAGES[1]: self.tokens_per_stage}
            count = updates.get(stage, steps if stage == STAGES[2] else 0)
            self._run_stage(stage, count, steps, cancelled, emit)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio = out_dir / "audio.wav"
        _write_tone(audio, self.audio_seconds)
        return TakeOutput(audio_path=audio, audio_seconds=self.audio_seconds)

    def _run_stage(self, stage, count, steps, cancelled, emit) -> None:
        deadline = time.monotonic() + self.stage_seconds
        done = 0
        while (now := time.monotonic()) < deadline:
            if cancelled():
                raise Cancelled(stage)
            elapsed = 1 - (deadline - now) / self.stage_seconds
            while count and done < int(elapsed * count):
                done += 1
                if stage == STAGES[2]:
                    emit({"type": "progress", "stage": stage, "completed": done, "total": steps})
                else:
                    emit({"type": "progress", "stage": stage, "tokens": done})
            time.sleep(min(TICK, max(0.0, deadline - now)))


def _write_tone(path: Path, seconds: float) -> None:
    frames = int(SAMPLE_RATE * seconds)
    samples = (int(8000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)) for i in range(frames))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"".join(struct.pack("<h", s) for s in samples))
