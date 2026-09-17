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
        self.precision: str | None = None
        self.cancelled_before = False
        self.usable = True

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

    def plan(self, request, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event):
        self._maybe_fail("plan")
        return self._stage(STAGES[0], on_event, {"score": "X:1", "request": request}, cancelled)

    def generate_semantic(
        self, score_or_request, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event
    ):
        self._maybe_fail("generate_semantic")
        return self._stage(STAGES[1], on_event, [1, 2, 3], cancelled)

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
        return self._stage(STAGES[2], on_event, [0.0] * len(semantic), cancelled)

    def decode(self, latents, *, cancelled: CancelCheck = never_cancelled, on_event=ignore_event):
        self._maybe_fail("decode")
        frames = int(self.audio_seconds * SAMPLE_RATE)
        return self._stage(STAGES[3], on_event, bytes(frames * 2), cancelled)

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
        output_dir.mkdir(parents=True, exist_ok=True)
        score = self.plan(request, cancelled=cancelled, on_event=on_event)
        score_path = output_dir / "score.abc"
        score_path.write_text(score["score"])
        semantic = self.generate_semantic(score, cancelled=cancelled, on_event=on_event)
        semantic_path = output_dir / "semantic.bin"
        semantic_path.write_bytes(bytes(semantic))
        latents = self.synthesize(semantic, steps, cancelled=cancelled, on_event=on_event)
        audio_path = output_dir / "audio.wav"
        if self.audio_written_at_decoding_start:
            _write_wav(audio_path, b"")
        pcm = self.decode(latents, cancelled=cancelled, on_event=on_event)
        _write_wav(audio_path, pcm)
        latents_path = output_dir / "extra" / "latents.bin"
        latents_path.parent.mkdir(exist_ok=True)
        latents_path.write_bytes(bytes(64 * len(latents)))
        return RunOutput(
            audio_path,
            len(pcm) / 2 / SAMPLE_RATE,
            [audio_path, score_path, semantic_path, latents_path],
            lazy_load_seconds=dict(self.lazy_load_seconds),
            engine_peak_memory_bytes=self.peak_memory_bytes,
        )
