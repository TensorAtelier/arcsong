"""A stand-in Engine for tests and UI work: scripted Stages and a short tone as the Take."""

from __future__ import annotations

import math
import struct
import time
import wave
from pathlib import Path
from typing import Any

from songloom.engine import STAGES, CancelCheck, Cancelled, Emit, TakeOutput

SAMPLE_RATE = 48_000


class FakeEngine:
    def __init__(self, stage_seconds: float = 0.02, audio_seconds: float = 1.0, fail_in=None):
        self.stage_seconds = stage_seconds
        self.audio_seconds = audio_seconds
        self.fail_in = fail_in

    def load(self) -> None:
        pass

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        for stage in STAGES:
            if cancelled():
                raise Cancelled(stage)
            emit({"type": "stage", "stage": stage})
            if self.fail_in == stage:
                raise RuntimeError(f"fake failure in {stage}")
            time.sleep(self.stage_seconds)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio = out_dir / "audio.wav"
        _write_tone(audio, self.audio_seconds)
        return TakeOutput(audio_path=audio, audio_seconds=self.audio_seconds)


def _write_tone(path: Path, seconds: float) -> None:
    frames = int(SAMPLE_RATE * seconds)
    samples = (int(8000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)) for i in range(frames))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"".join(struct.pack("<h", s) for s in samples))
