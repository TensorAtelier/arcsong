"""audio.cpp Engine: the prebuilt `audiocpp_cli` driven as a subprocess (D-005).

The CLI only runs a whole Take, so `run` is the one supported operation; the Stage
operations raise `Unsupported`. Stage events come from the CLI's `--log` output: YuE2
logs each Stage's duration (`yue2.plan_ms`, `yue2.semantic_ms`, ...) the moment the
Stage ends, and log lines are flushed one by one, so a line's arrival time is the
Stage's end and its logged duration gives the start. Because those `start` events come
late, each Stage is also announced by an `enter` event as soon as the log shows it has
begun. Cancel kills the process.
"""

from __future__ import annotations

import os
import re
import signal
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spike import audiocpp_setup
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

NAME = "audio.cpp"
MODEL_GGUF = {"q8_0": "yue2-3b-q8_0.gguf", "bf16": "yue2-3b-bf16.gguf"}
PRECISIONS = tuple(MODEL_GGUF)
VAE_GGUF = "yue2-vae-f16.gguf"
POLL_SECONDS = 0.05
# Overlap with the previous Stage beyond line-arrival jitter means the clocks diverged.
CLOCK_SLACK_SECONDS = 1.0
LOG_NAME = "audiocpp.log"
AUDIO_NAME = "audio.wav"
SCORE_NAME = "score.abc"

PLANNING, SEMANTIC, SYNTHESIS, DECODING = STAGES

# e.g. "[TIMING ts=20260916-170051] yue2.semantic_ms 8084.98975"
_SCALAR = re.compile(r"^\[(?:TIMING|TRACE)[^\]]*\]\s+(yue2\.[\w.]+)\s+(-?\d[\d.eE+-]*)\s*$")
_LOAD_KEYS = {
    "yue2.ar.init_ms": "ar_load_seconds",
    "yue2.nar.init_ms": "nar_load_seconds",
    "yue2.vae.init_ms": "vae_load_seconds",
}


class Cancelled(Exception):  # noqa: N818 - names what happened to the Take
    """The run was cancelled and its process killed."""

    def __init__(self, message: str, *, kill_to_exit_seconds: float | None = None):
        super().__init__(message)
        self.kill_to_exit_seconds = kill_to_exit_seconds


# The log line that shows a Stage has just begun (the one ending the Stage before it).
_ENTERED_BY = {
    "yue2.plan_ms": (PLANNING,),
    "yue2.semantic.abc_generate_ms": (SEMANTIC,),
    "yue2.semantic_ms": (SYNTHESIS,),
    "yue2.nar_ms": (DECODING,),
}


def entered_stages(line: str, score_given: bool) -> tuple[str, ...]:
    """Stages a `--log` line shows have just begun, for live `enter` events.

    With a Score supplied nothing is logged between planning and semantic generation,
    so both are announced by `yue2.plan_ms`.
    """
    match = _SCALAR.match(line.strip())
    if not match:
        return ()
    key = match.group(1)
    if score_given and key == "yue2.plan_ms":
        return (PLANNING, SEMANTIC)
    return _ENTERED_BY.get(key, ())


@dataclass
class StageLogParser:
    """Turns `--log` lines into Stage events, given the time each line arrived.

    YuE2 logs a Stage's duration in ms as the Stage ends: `yue2.plan_ms`,
    `yue2.semantic_ms`, `yue2.nar_ms` (synthesis), `yue2.vae_decode_ms` (decoding).
    `yue2.semantic_ms` covers both writing the Score (when none is given, logged inside
    it as `yue2.semantic.abc_generate_ms`) and writing Semantic tokens, so planning runs
    from the start of `yue2.plan_ms` until the Score is written, and semantic generation
    from there to the end of `yue2.semantic_ms`. Model initialisation happens inside the
    Stage that first needs it (as for mlx-Yue) and is also reported by `load_seconds`,
    together with the session load from process launch (`started`) to planning.
    """

    started: float | None = None
    scalars: dict[str, float] = field(default_factory=dict)
    _planning_start: float | None = None
    _planning_end: float | None = None
    _last_end: float | None = None

    def feed(self, line: str, t: float) -> list[StageEvent]:
        match = _SCALAR.match(line.strip())
        if not match:
            return []
        key, value = match.group(1), float(match.group(2))
        self.scalars[key] = value
        return self._events(key, value / 1000.0, t)

    def _events(self, key: str, seconds: float, t: float) -> list[StageEvent]:
        if key == "yue2.plan_ms":
            self._planning_start, self._planning_end = t - seconds, t
        elif key == "yue2.semantic.abc_generate_ms":
            self._planning_end = t
        elif key == "yue2.semantic_ms":
            planning_start = self._planning_start
            if planning_start is None:
                planning_start = t - seconds
            planning_end = self._planning_end if self._planning_end is not None else planning_start
            self._last_end = t
            return [
                StageEvent(PLANNING, "start", planning_start),
                StageEvent(PLANNING, "end", planning_end),
                StageEvent(SEMANTIC, "start", max(planning_end, t - seconds)),
                StageEvent(SEMANTIC, "end", t),
            ]
        elif key == "yue2.nar_ms":
            return self._span(SYNTHESIS, seconds, t)
        elif key == "yue2.vae_decode_ms":
            return self._span(DECODING, seconds, t)
        return []

    def _span(self, stage: str, seconds: float, t: float) -> list[StageEvent]:
        """A Stage ending at `t`, starting no earlier than the previous Stage ended.

        The CLI's timer keeps counting while the Mac sleeps and ours does not, so a
        logged duration can reach back past the previous Stage.
        """
        start = t - seconds
        if self._last_end is not None and start < self._last_end - CLOCK_SLACK_SECONDS:
            start = self._last_end
        self._last_end = t
        return [StageEvent(stage, "start", start), StageEvent(stage, "end", t)]

    def load_seconds(self) -> dict[str, float]:
        load = {
            name: self.scalars[key] / 1000.0
            for key, name in _LOAD_KEYS.items()
            if key in self.scalars
        }
        if self.started is not None and self._planning_start is not None:
            load["session_load_seconds"] = self._planning_start - self.started
        return load


def wav_seconds(path: Path) -> float:
    """Duration of a RIFF/WAVE file of any sample format (PCM or float)."""
    with open(path, "rb") as source:
        riff, _, wave = struct.unpack("<4sI4s", source.read(12))
        if riff != b"RIFF" or wave != b"WAVE":
            raise ValueError(f"{path} is not a WAV file")
        byte_rate = None
        while header := source.read(8):
            chunk, size = struct.unpack("<4sI", header)
            if chunk == b"fmt ":
                fmt = source.read(size)
                byte_rate = struct.unpack("<I", fmt[8:12])[0]
                if size % 2:
                    source.seek(1, os.SEEK_CUR)
            elif chunk == b"data":
                if byte_rate is None:
                    raise ValueError(f"{path} has data before its fmt chunk")
                return size / byte_rate
            else:
                source.seek(size + size % 2, os.SEEK_CUR)
    raise ValueError(f"{path} has no data chunk")


def _kill_when_parent_dies(parent_pid: int, pid: int) -> subprocess.Popen:
    """A watchdog that kills the CLI if the process driving it is killed outright."""
    script = f"while kill -0 {parent_pid} 2>/dev/null && kill -0 {pid} 2>/dev/null; do sleep 0.5; done; kill -9 {pid} 2>/dev/null"  # noqa: E501
    return subprocess.Popen(
        ["/bin/sh", "-c", script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class AudioCppEngine:
    def __init__(
        self,
        cli: Path | None = None,
        models_dir: Path = audiocpp_setup.DEFAULT_MODELS_DIR,
        *,
        backend: str = "metal",
        threads: int = 8,
    ):
        self.cli = Path(cli) if cli else audiocpp_setup.cli_path()
        self.model_dir = audiocpp_setup.model_dir(Path(models_dir).expanduser())
        self.backend = backend
        self.threads = threads
        self.precision: str | None = None

    def info(self) -> EngineInfo:
        try:
            out = subprocess.run(
                [str(self.cli), "--version"], capture_output=True, text=True, timeout=30
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return EngineInfo(
                name=NAME, version=None, commit=None, takes_reuse_loaded_model=False
            )
        version = re.search(r"audio\.cpp\s+(\S+)", out)
        commit = re.search(r"git:\s*([0-9a-f]+)", out)
        return EngineInfo(
            name=NAME,
            version=version.group(1) if version else None,
            commit=commit.group(1) if commit else None,
            # Each `run` launches `audiocpp_cli`, which loads the model again.
            takes_reuse_loaded_model=False,
        )

    def load(self, precision: str) -> None:
        """Checks the binary and weights; the CLI itself loads them inside each run."""
        if precision not in MODEL_GGUF:
            raise ValueError(f"audio.cpp precision must be one of {PRECISIONS}, got {precision!r}")
        if not os.access(self.cli, os.X_OK):
            raise FileNotFoundError(f"audio.cpp CLI not found at {self.cli}; run `spike setup`")
        for name in (MODEL_GGUF[precision], VAE_GGUF):
            if not (self.model_dir / name).is_file():
                raise FileNotFoundError(f"{self.model_dir / name} missing; run `spike setup`")
        self.precision = precision

    def _unsupported(self, operation: str) -> Unsupported:
        return Unsupported(
            f"audio.cpp's CLI runs only whole Takes; it cannot run {operation} on its own"
        )

    def plan(self, request, *, cancelled=never_cancelled, on_event=ignore_event) -> Any:
        raise self._unsupported("planning")

    def generate_semantic(
        self, score_or_request, *, cancelled=never_cancelled, on_event=ignore_event
    ) -> Any:
        raise self._unsupported("semantic generation")

    def synthesize(
        self, semantic, steps, noise=None, *, cancelled=never_cancelled, on_event=ignore_event
    ) -> Any:
        raise self._unsupported("synthesis from given Semantic tokens")

    def decode(self, latents, *, cancelled=never_cancelled, on_event=ignore_event) -> Any:
        raise self._unsupported("decoding of given Latents")

    def command(self, request: dict, steps: int, output_dir: Path) -> list[str]:
        if self.precision is None:
            raise RuntimeError("call load(precision) before run")
        argv = [
            str(self.cli),
            "--task", "gen",
            "--family", "yue2",
            "--model", str(self.model_dir),
            "--backend", self.backend,
            "--threads", str(self.threads),
            "--session-option", f"yue2.model_gguf={MODEL_GGUF[self.precision]}",
            "--session-option", f"yue2.vae_gguf={VAE_GGUF}",
            "--lyrics", request["lyrics"],
            "--request-option", f"style={request['style']}",
            "--request-option", f"cot={request.get('cot', 'full')}",
            "--request-option", f"num_inference_steps={steps}",
            "--seed", str(request["seed"]),
        ]  # fmt: skip
        if request.get("abc"):
            argv += ["--request-option", f"abc_file={output_dir / SCORE_NAME}"]
        for group, prefix in (("abc_sampling", "abc"), ("semantic_sampling", "semantic")):
            for key, value in (request.get(group) or {}).items():
                argv += ["--request-option", f"{prefix}_{key}={value}"]
        return argv + ["--out", str(output_dir / AUDIO_NAME), "--log"]

    def run(
        self,
        request: dict,
        steps: int,
        output_dir: Path,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ) -> RunOutput:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if request.get("abc"):
            (output_dir / SCORE_NAME).write_text(request["abc"])
        argv = self.command(request, steps, output_dir)
        parser = StageLogParser(started=time.monotonic())
        log_path = output_dir / LOG_NAME
        tail: list[str] = []
        score_given = bool(request.get("abc"))

        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        watchdog = _kill_when_parent_dies(os.getpid(), process.pid)

        def pump() -> None:
            with open(log_path, "w") as log:
                for line in process.stdout:
                    now = time.monotonic()
                    log.write(line)
                    log.flush()
                    tail[:] = [*tail[-39:], line.rstrip("\n")]
                    for stage in entered_stages(line, score_given):
                        on_event(StageEvent(stage, "enter", now))
                    for event in parser.feed(line, now):
                        on_event(event)

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            while process.poll() is None:
                if cancelled():
                    killed_at = time.monotonic()
                    process.kill()
                    process.wait()
                    raise Cancelled(
                        f"audio.cpp run killed (pid {process.pid})",
                        kill_to_exit_seconds=time.monotonic() - killed_at,
                    )
                time.sleep(POLL_SECONDS)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            reader.join(timeout=5)
            watchdog.kill()
            watchdog.wait()

        if process.returncode != 0:
            how = (
                f"killed by {signal.Signals(-process.returncode).name}"
                if process.returncode < 0
                else f"exited with code {process.returncode}"
            )
            raise RuntimeError(f"audiocpp_cli {how}; last log lines:\n" + "\n".join(tail))
        audio = output_dir / AUDIO_NAME
        return RunOutput(
            audio,
            wav_seconds(audio),
            sorted(p for p in output_dir.rglob("*") if p.is_file()),
            lazy_load_seconds=parser.load_seconds(),
        )
