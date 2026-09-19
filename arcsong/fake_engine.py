"""A stand-in Engine for tests and UI work: scripted Stages, progress and a short tone."""

from __future__ import annotations

import math
import os
import struct
import time
import wave
from pathlib import Path
from typing import Any

from arcsong.engine import (
    STAGES,
    TRANSCRIBING,
    CancelCheck,
    Cancelled,
    Emit,
    ScoreOutput,
    TakeOutput,
)

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
        crash_in: str | None = None,
        ignore_cancel: bool = False,
        fail_load: str | None = None,
        fail_transcribe: str | None = None,
    ):
        self.stage_seconds = stage_seconds
        self.audio_seconds = audio_seconds
        self.tokens_per_stage = tokens_per_stage
        self.fail_in = fail_in
        self.crash_in = crash_in  # the worker process dies abruptly, like an OOM kill
        self.ignore_cancel = ignore_cancel
        self.fail_load = fail_load  # load() raises this, like missing weights or a held GPU
        self.fail_transcribe = fail_transcribe

    def load(self) -> None:
        if self.fail_load:
            raise RuntimeError(self.fail_load)

    def transcribe(
        self,
        audio: Path,
        request: dict[str, Any],
        out_dir: Path,
        cancelled: CancelCheck,
        emit: Emit,
    ) -> ScoreOutput:
        """Reads the upload (so a missing file fails like the real one), reports windows, and
        writes a Score whose seed comes from the recording's size."""
        if not audio.is_file():
            raise FileNotFoundError(f"no recording at {audio}")
        if self.fail_transcribe:
            raise ValueError(self.fail_transcribe)
        emit({"type": "stage", "stage": TRANSCRIBING})
        windows = 3
        deadline = time.monotonic() + self.stage_seconds
        for window in range(1, windows + 1):
            if cancelled():
                raise Cancelled(TRANSCRIBING)
            emit({"type": "progress", "stage": TRANSCRIBING, "completed": window, "total": windows})
            while time.monotonic() < deadline * window / windows:
                if cancelled():
                    raise Cancelled(TRANSCRIBING)
                time.sleep(TICK)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "melody.mid").write_bytes(b"MThd fake")
        abc = fake_score({"seed": audio.stat().st_size})
        (out_dir / "score.abc").write_text(abc)
        return ScoreOutput(abc)

    def plan_only(self, request: dict[str, Any], cancelled: CancelCheck, emit: Emit) -> ScoreOutput:
        if cancelled():
            raise Cancelled(STAGES[0])
        emit({"type": "stage", "stage": STAGES[0]})
        self._run_stage(STAGES[0], self.tokens_per_stage, 0, cancelled, emit)
        return ScoreOutput(fake_score(request))

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        # A supplied Score makes planning instant, as it does in mlx-Yue.
        stages = STAGES[1:] if request.get("abc") else STAGES
        return self._run(stages, request, out_dir, cancelled, emit)

    def finalize(
        self,
        source_dir: Path,
        request: dict[str, Any],
        out_dir: Path,
        cancelled: CancelCheck,
        emit: Emit,
    ) -> TakeOutput:
        """Like mlx-Yue, needs the Draft's saved Take and runs only synthesis and decoding."""
        if not (source_dir / "audio.wav").is_file():
            raise FileNotFoundError(f"no saved Take in {source_dir}")
        return self._run(STAGES[2:], request, out_dir, cancelled, emit)

    def _run(self, stages, request, out_dir, cancelled, emit) -> TakeOutput:
        steps = request.get("steps", 8)
        for stage in stages:
            if cancelled() and not self.ignore_cancel:
                raise Cancelled(stage)
            emit({"type": "stage", "stage": stage})
            if self.fail_in == stage:
                raise RuntimeError(f"fake failure in {stage}")
            if self.crash_in == stage:
                os._exit(137)
            updates = {STAGES[0]: self.tokens_per_stage, STAGES[1]: self.tokens_per_stage}
            count = updates.get(stage, steps if stage == STAGES[2] else 0)
            self._run_stage(stage, count, steps, cancelled, emit)
        out_dir.mkdir(parents=True, exist_ok=True)
        if request.get("mode", "full") != "off":  # mlx-Yue saves the Score beside the audio
            (out_dir / "score.abc").write_text(request.get("abc") or fake_score(request))
        audio = out_dir / "audio.wav"
        _write_tone(audio, self.audio_seconds, request.get("seed", 0))
        return TakeOutput(audio_path=audio, audio_seconds=self.audio_seconds)

    def _run_stage(self, stage, count, steps, cancelled, emit) -> None:
        deadline = time.monotonic() + self.stage_seconds
        done = 0
        while (now := time.monotonic()) < deadline:
            if cancelled() and not self.ignore_cancel:
                raise Cancelled(stage)
            elapsed = 1 - (deadline - now) / self.stage_seconds
            while count and done < int(elapsed * count):
                done += 1
                if stage == STAGES[2]:
                    emit({"type": "progress", "stage": stage, "completed": done, "total": steps})
                else:
                    emit({"type": "progress", "stage": stage, "tokens": done})
            time.sleep(min(TICK, max(0.0, deadline - now)))


# The native two-voice ABC dialect mlx-Yue writes and accepts: 4/4 in 32nd-note units, a
# Vocal and an Ins voice, four measures each (see `lyra.music_tools.abc_tools.parse`).
SCALE = ["C", "D", "E", "F", "G", "A", "B", "c"]
SCORE_TEMPLATE = """X:1
T:
M:4/4
L:1/32
Q:1/4={bpm}
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
V: Vocal
{vocal}|
V: Ins
{ins}|
"""


def fake_score(request: dict[str, Any]) -> str:
    """A Score the real parser accepts, whose notes follow the seed so Variations differ."""
    seed = int(request.get("seed") or 0)  # a job made straight in the store may carry no seed
    bars = []
    for bar in range(4):
        notes = [SCALE[(seed // (bar + 1) + i * 2) % len(SCALE)] for i in range(4)]
        bars.append("".join(f"{note}8" for note in notes))
    vocal = "|".join(f'"{SCALE[(seed + i) % 7]}"{bar}' for i, bar in enumerate(bars))
    ins = "|".join(bars[::-1])
    return SCORE_TEMPLATE.format(bpm=90 + seed % 60, vocal=vocal, ins=ins)


def _write_tone(path: Path, seconds: float, seed: int) -> None:
    """A tone whose pitch and swell depend on the seed, so Variations look and sound different
    (and a Final matches its Draft, which has the same seed)."""
    frames = int(SAMPLE_RATE * seconds)
    pitch = 220 + seed % 440
    swells = 1 + seed % 5

    def sample(i: int) -> int:
        t = i / SAMPLE_RATE
        envelope = 0.2 + 0.8 * abs(math.sin(math.pi * swells * t / max(seconds, 1e-9)))
        return int(12000 * envelope * math.sin(2 * math.pi * pitch * t))

    samples = (sample(i) for i in range(frames))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"".join(struct.pack("<h", s) for s in samples))
