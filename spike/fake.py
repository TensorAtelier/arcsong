"""A scripted Engine for exercising the harness without weights (D-016)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sys
import tempfile
import time
import wave
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from spike.engine import (
    STAGES,
    CancelCheck,
    CliTake,
    EngineInfo,
    EventSink,
    RunOutput,
    StageEvent,
    Unsupported,
    WeightsDownload,
    ignore_event,
    never_cancelled,
)

SAMPLE_RATE = 8000
SEMANTIC_TOKENS = 50
LATENT_CHANNELS = 8
# Where scripted divergent Semantic tokens start to differ.
DIVERGE_INDEX = 10
LATENT_DIVERGENCE = 0.5
NOISE_WEIGHT = 0.1


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
        own_noise_hidden: bool = False,
        noise_probe_seconds: float = 0.0,
        take_cli: bool = True,
        download_metadata: bool = True,
    ):
        # The options this Engine was made with, so its command line can make the same one.
        self.options = {k: v for k, v in locals().items() if k != "self"}
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
        # Like audio.cpp: the Engine's own noise from the seed is neither exported nor the
        # noise the harness writes, so keeping noise means probing for the Semantic token
        # count (`noise_probe_seconds`) and supplying harness-written noise.
        self.own_noise_hidden = own_noise_hidden
        self.noise_probe_seconds = noise_probe_seconds
        # Like mlx-Yue: a command line (`python -m spike.fake take ...`) that refuses a
        # non-empty output directory and a stale `<output>.resources.json[l]` next to it.
        self.take_cli = take_cli
        # Like a Hugging Face `local_dir` download: `.cache/huggingface/...` metadata.
        self.download_metadata = download_metadata
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
        if noise is not None:
            latents += NOISE_WEIGHT * np.asarray(noise, dtype=np.float32)
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

    def _noise(self, request: dict, frames: int, *, own: bool = False) -> np.ndarray:
        seed = request.get("seed", 0)
        if own and self.own_noise_hidden:
            seed += 1  # a generator the harness can't reproduce
        rng = np.random.default_rng(seed)
        return rng.standard_normal((frames, LATENT_CHANNELS), dtype=np.float32)

    def _save(
        self,
        output_dir: Path,
        score: str,
        semantic: np.ndarray,
        noise: np.ndarray,
        latents: np.ndarray,
        pcm: bytes,
        *,
        noise_path: Path | None = None,
        export_noise: bool = True,
        details: dict | None = None,
    ) -> RunOutput:
        output_dir.mkdir(parents=True, exist_ok=True)
        score_path = output_dir / "score.abc"
        score_path.write_text(score)
        semantic_path = output_dir / "semantic.npy"
        np.save(semantic_path, semantic)
        if export_noise and noise_path is None:
            noise_path = output_dir / "noise.npy"
            np.save(noise_path, noise)
        audio_path = output_dir / "audio.wav"
        _write_wav(audio_path, pcm)
        latents_path = output_dir / "extra" / "latent.npy"
        latents_path.parent.mkdir(exist_ok=True)
        np.save(latents_path, latents)
        return RunOutput(
            audio_path,
            len(pcm) / 2 / SAMPLE_RATE,
            sorted(p for p in output_dir.rglob("*") if p.is_file()),
            lazy_load_seconds=dict(self.lazy_load_seconds),
            engine_peak_memory_bytes=self.peak_memory_bytes,
            stage_outputs={
                STAGES[0]: score_path,
                STAGES[1]: semantic_path,
                STAGES[2]: latents_path,
            },
            noise_path=noise_path,
            details=dict(details or {}),
        )

    def run(
        self,
        request: dict,
        steps: int,
        output_dir: Path,
        *,
        noise: Path | None = None,
        keep_noise: bool = False,
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
        # Each Stage's output is on disk as soon as the Stage ends, as a cancel would find it.
        score = self.plan(request, cancelled=cancelled, on_event=on_event)
        (output_dir / "score.abc").write_text(score["score"])
        semantic = self.generate_semantic(score, cancelled=cancelled, on_event=on_event)
        np.save(output_dir / "semantic.npy", semantic)
        details: dict = {}
        supplied = noise
        if noise is None and keep_noise and self.own_noise_hidden:
            start = time.monotonic()
            time.sleep(self.noise_probe_seconds)
            details["noise_probe_seconds"] = time.monotonic() - start
            supplied = output_dir / "noise.npy"
            np.save(supplied, self._noise(request, len(semantic)))
        if supplied is not None:
            noise_array = np.load(supplied)
        else:
            noise_array = self._noise(request, len(semantic), own=True)
        latents = self.synthesize(
            semantic, steps, noise_array, cancelled=cancelled, on_event=on_event
        )
        if self.audio_written_at_decoding_start:
            _write_wav(output_dir / "audio.wav", b"")
        pcm = self.decode(latents, cancelled=cancelled, on_event=on_event)
        return self._save(
            output_dir,
            score["score"],
            semantic,
            noise_array,
            latents,
            pcm,
            noise_path=supplied,
            export_noise=not self.own_noise_hidden,
            details=details,
        )

    def render_final(
        self,
        draft_dir: Path,
        steps: int,
        output_dir: Path,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ) -> RunOutput:
        self._maybe_fail("render_final")
        self.takes += 1
        draft_dir = Path(draft_dir)
        semantic = np.load(draft_dir / "semantic.npy")
        noise = np.load(draft_dir / "noise.npy")
        latents = self.synthesize(semantic, steps, noise, cancelled=cancelled, on_event=on_event)
        pcm = self.decode(latents, cancelled=cancelled, on_event=on_event)
        score = (draft_dir / "score.abc").read_text()
        return self._save(Path(output_dir), score, semantic, noise, latents, pcm)

    def take_command(
        self, request: dict, output_dir: Path, precision: str, steps: int, workdir: Path
    ) -> CliTake:
        """A whole Take through this Engine's command line (see `take_cli`)."""
        if not self.take_cli:
            raise Unsupported("FakeEngine has no command line")
        workdir.mkdir(parents=True, exist_ok=True)
        request_path = workdir / "request.json"
        request_path.write_text(json.dumps(request))
        argv = [sys.executable, "-m", "spike.fake", "take", "--options", json.dumps(self.options),
                "--request", str(request_path), "--output", str(output_dir),
                "--precision", precision, "--steps", str(steps)]  # fmt: skip
        return CliTake(argv, stage_markers={stage: _marker(stage) for stage in STAGES})

    # Like mlx-Yue's converted directory: exactly these files, plus an optional README.
    CONVERTED_FILES = frozenset({"config.json", "weights.bin"})
    CONVERTED_OPTIONAL = frozenset({"README.md"})

    def download_weights(self, target_dir: Path) -> WeightsDownload:
        """Mimics a hub `local_dir` snapshot of each weight directory (with `.gitattributes`
        and, if `download_metadata`, `.cache/huggingface/...`), with the large converted
        weight supplied locally instead of downloaded."""
        repos = {"converted": [".gitattributes", "config.json"], "vae": ["model.bin"]}
        downloaded = []
        for directory, names in repos.items():
            for name in names:
                path = target_dir / directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"fake {name}\n")
                downloaded.append(f"{directory}/{name}")
                if self.download_metadata:
                    meta = target_dir / directory / ".cache" / "huggingface"
                    (meta / "download").mkdir(parents=True, exist_ok=True)
                    (meta / ".gitignore").write_text("*\n")
                    (meta / "download" / f"{name}.metadata").write_text("etag\n")
        (target_dir / "converted" / "weights.bin").write_bytes(b"weights")
        return WeightsDownload(
            weight_dirs={"converted": "converted", "vae": "vae"},
            downloaded=downloaded,
            supplied_locally=[
                {"path": "converted/weights.bin", "source": "fake", "method": "copy"}
            ],
            sources=[{"repository": f"fake/{name}", "local_dir": name} for name in repos],
        )

    def unexpected_weight_files(self, weight_dirs: dict[str, Path]) -> list[Path]:
        converted = Path(weight_dirs["converted"])
        allowed = self.CONVERTED_FILES | self.CONVERTED_OPTIONAL
        return sorted(
            path
            for path in converted.rglob("*")
            if path.is_file() and path.relative_to(converted).as_posix() not in allowed
        )

    def verify_weights(self, weight_dirs: dict[str, Path]) -> dict:
        converted = Path(weight_dirs["converted"])
        present = {p.relative_to(converted).as_posix() for p in converted.rglob("*") if p.is_file()}
        unexpected = [
            p.relative_to(converted).as_posix() for p in self.unexpected_weight_files(weight_dirs)
        ]
        missing = sorted(self.CONVERTED_FILES - present)
        if missing or unexpected:
            raise ValueError(
                f"Converted directory has missing or unexpected files: "
                f"missing={missing}, unexpected={unexpected}"
            )
        if not (Path(weight_dirs["vae"]) / "model.bin").is_file():
            raise FileNotFoundError("No VAE weights")
        return {"files": sorted(present)}


def _marker(stage: str) -> str:
    return f"fake: {stage} begins"


def _take_cli(argv: list[str]) -> int:
    """Mimics mlx-Yue's `generate --output`: an empty output directory is required, and
    `<output>.resources.jsonl` (written from the start) and `<output>.resources.json`
    (written at the end) must not exist yet. The Take is saved when it is complete."""
    parser = argparse.ArgumentParser(prog="python -m spike.fake take")
    parser.add_argument("--options", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--precision", required=True)
    parser.add_argument("--steps", type=int, required=True)
    args = parser.parse_args(argv)
    output: Path = args.output
    if output.exists() and any(output.iterdir()):
        print("error: Output directory must be empty", file=sys.stderr)
        return 2
    log_path = output.with_name(output.name + ".resources.jsonl")
    report_path = output.with_name(output.name + ".resources.json")
    for path in (log_path, report_path):
        if path.exists():
            print(f"FileExistsError: Resource evidence already exists: {path}", file=sys.stderr)
            return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("x") as log:
        log.write(json.dumps({"sample": 1}) + "\n")
        log.flush()
        engine = FakeEngine(**json.loads(args.options))
        engine.load(args.precision)

        def on_event(event: StageEvent) -> None:
            if event.kind == "start":
                print(_marker(event.stage), file=sys.stderr, flush=True)

        request = json.loads(args.request.read_text())
        with tempfile.TemporaryDirectory() as staging:
            engine.run(request, args.steps, Path(staging) / "take", on_event=on_event)
            shutil.copytree(Path(staging) / "take", output, dirs_exist_ok=True)
    report_path.write_text(json.dumps({"samples": 1}))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] != ["take"]:
        print("usage: python -m spike.fake take ...", file=sys.stderr)
        return 2
    return _take_cli(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
