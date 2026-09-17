"""mlx-Yue Engine: in-process `lyra.YuE2Pipeline` driven through its public Stage methods.

`lyra` (and MLX) are imported lazily so the harness process never touches the GPU;
only the fresh child process that runs a measurement loads them.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import subprocess
import sys
import time
from importlib import metadata
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
    WeightsDownload,
    ignore_event,
    never_cancelled,
)

DEFAULT_MODELS_DIR = Path("~/projects/mlx-Yue/models").expanduser()
DISTRIBUTION = "mlx-yue"
SAMPLE_RATE = 48000
# Pre-converted weights (mlx-Yue README) and the VAE; downloads use their current revision
# except the VAE, which mlx-Yue pins.
CONVERTED_REPO = "vanch007/mlx-Yue2-3B"
# The converted repository's large weights: taken from the local models directory as APFS
# clones rather than downloaded again (D-013); verification hashes them all the same.
CONVERTED_LOCAL_PATTERNS = ("*.safetensors",)
VAE_PATTERNS = ("config.json", "weights_manifest.json", "model.safetensors")
# Text the mlx-Yue command line prints to stderr as a Stage begins.
CLI_STAGE_MARKERS = {
    STAGES[0]: "Planning score",
    STAGES[1]: "Generating song",
    STAGES[2]: "Synthesizing audio",
    STAGES[3]: "Decoding audio",
}
_SAMPLING_KEYS = ("abc_sampling", "semantic_sampling")


def _installed_commit() -> str | None:
    try:
        direct_url = metadata.distribution(DISTRIBUTION).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not direct_url:
        return None
    return json.loads(direct_url).get("vcs_info", {}).get("commit_id")


def _mlx_peak_memory_bytes() -> int | None:
    import mlx.core as mx

    get_peak = getattr(mx, "get_peak_memory", None) or getattr(mx.metal, "get_peak_memory", None)
    return None if get_peak is None else int(get_peak())


def loads_since(before: dict, after: dict) -> dict[str, float]:
    """Weights loaded between two snapshots of `YuE2Pipeline.load_timing`, per model.

    The pipeline appends each lazy load to `<model>_load_events_seconds`.
    """
    loads = {}
    suffix = "_load_events_seconds"
    for key, events in after.items():
        if not key.endswith(suffix):
            continue
        new = tuple(events)[len(tuple(before.get(key, ()))) :]
        if new:
            loads[f"{key.removesuffix(suffix)}_load_seconds"] = float(sum(new))
    return loads


class _Stage:
    def __init__(self, stage: str, on_event: EventSink):
        self.stage, self.on_event = stage, on_event

    def __enter__(self):
        self.on_event(StageEvent(self.stage, "start"))

    def __exit__(self, *exc):
        self.on_event(StageEvent(self.stage, "end"))
        return False


class MlxYueEngine:
    def __init__(
        self,
        models_dir: Path = DEFAULT_MODELS_DIR,
        *,
        require_ac: bool = True,
        progress: bool = True,
    ):
        self.models_dir = Path(models_dir).expanduser()
        self.require_ac = require_ac
        self.progress = progress
        self.pipe: Any = None

    def info(self) -> EngineInfo:
        try:
            version = metadata.version(DISTRIBUTION)
        except metadata.PackageNotFoundError:
            version = None
        return EngineInfo(name="mlx-Yue", version=version, commit=_installed_commit())

    def load(self, precision: str) -> None:
        from lyra import YuE2Pipeline

        self.pipe = YuE2Pipeline.from_pretrained(
            str(self.models_dir / "converted"),
            vae=str(self.models_dir / "vae"),
            precision=precision,
            local_files_only=True,
            require_ac=self.require_ac,
            progress=self.progress,
        )

    def _loaded(self):
        if self.pipe is None:
            raise RuntimeError("call load(precision) before running a Stage")
        return self.pipe

    @staticmethod
    def _split(request: dict) -> tuple[dict, dict]:
        fields = {k: v for k, v in request.items() if k not in _SAMPLING_KEYS}
        sampling = {k: request.get(k) for k in _SAMPLING_KEYS}
        return fields, sampling

    def plan(
        self,
        request: dict,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ):
        fields, sampling = self._split(request)
        with _Stage(STAGES[0], on_event):
            return self._loaded().plan(
                **fields, abc_sampling=sampling["abc_sampling"], cancelled=cancelled
            )

    def generate_semantic(
        self,
        score_or_request: Any,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
        sampling: dict | None = None,
    ):
        score = score_or_request
        if isinstance(score_or_request, dict):
            sampling = score_or_request.get("semantic_sampling", sampling)
            score = self.plan(score_or_request, cancelled=cancelled, on_event=on_event)
        with _Stage(STAGES[1], on_event):
            return self._loaded().generate_semantic(score, sampling=sampling, cancelled=cancelled)

    def synthesize(
        self,
        semantic: Any,
        steps: int,
        noise: Any = None,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ):
        from lyra.pipeline import initial_noise

        pipe = self._loaded()
        pipe.generation_config = dataclasses.replace(pipe.generation_config, ode_steps=steps)
        if noise is None:
            noise = initial_noise(len(semantic.tokens), semantic.plan.request.seed)
        with _Stage(STAGES[2], on_event):
            return pipe.synthesize(semantic, cancelled=cancelled, noise=noise)

    def decode(
        self,
        latents: Any,
        *,
        cancelled: CancelCheck = never_cancelled,
        on_event: EventSink = ignore_event,
    ):
        with _Stage(STAGES[3], on_event):
            return self._loaded().decode(latents, cancelled=cancelled)

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
        """A whole Take through the Stage methods, saved with mlx-Yue's own artifacts
        (which always include the synthesis noise, so `keep_noise` needs no extra work)."""
        from lyra.pipeline import initial_noise

        pipe = self._loaded()
        _, sampling = self._split(request)
        load_timing_before = dict(pipe.load_timing)
        start = time.perf_counter()
        plan = self.plan(request, cancelled=cancelled, on_event=on_event)
        semantic = self.generate_semantic(
            plan, sampling=sampling["semantic_sampling"], cancelled=cancelled, on_event=on_event
        )
        if noise is None:
            noise_array = initial_noise(len(semantic.tokens), plan.request.seed)
        else:
            noise_array = np.load(noise, allow_pickle=False)
        synthesis_start = time.perf_counter()
        latents = self.synthesize(
            semantic, steps, noise_array, cancelled=cancelled, on_event=on_event
        )
        synthesis_seconds = time.perf_counter() - synthesis_start
        decode_start = time.perf_counter()
        audio = self.decode(latents, cancelled=cancelled, on_event=on_event)

        config = pipe.effective_config(
            plan.request, sampling["abc_sampling"], sampling["semantic_sampling"]
        )
        timing = {
            "abc": plan.timing,
            "semantic": semantic.timing,
            "nar_seconds": synthesis_seconds,
            "vae_seconds": time.perf_counter() - decode_start,
            "load": dict(pipe.load_timing),
            "e2e_seconds": time.perf_counter() - start,
        }
        return self._save(
            output_dir, semantic, latents, audio, noise_array, config, timing, load_timing_before
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
        """Loads the Draft's saved Take (integrity-checked by mlx-Yue), then re-synthesizes
        its Semantic tokens with its noise at `steps` and decodes: planning and semantic
        generation are not run again."""
        from lyra.artifacts import load_artifacts
        from yue2.protocol import GenerationConfig

        pipe = self._loaded()
        load_timing_before = dict(pipe.load_timing)
        start = time.perf_counter()
        saved = load_artifacts(Path(draft_dir))
        if saved.noise is None:
            raise ValueError(f"the Draft in {draft_dir} kept no synthesis noise")
        # The Draft's generation settings (sampling included), with the Final's steps.
        pipe.generation_config = dataclasses.replace(
            GenerationConfig.from_dict(saved.config["generation"]), ode_steps=steps
        )
        synthesis_start = time.perf_counter()
        latents = self.synthesize(
            saved.semantic, steps, saved.noise, cancelled=cancelled, on_event=on_event
        )
        synthesis_seconds = time.perf_counter() - synthesis_start
        decode_start = time.perf_counter()
        audio = self.decode(latents, cancelled=cancelled, on_event=on_event)

        request = saved.semantic.plan.request
        config = pipe.effective_config(request)
        timing = {
            "abc": saved.semantic.plan.timing,
            "semantic": saved.semantic.timing,
            "draft_load_seconds": synthesis_start - start,
            "nar_seconds": synthesis_seconds,
            "vae_seconds": time.perf_counter() - decode_start,
            "load": dict(pipe.load_timing),
            "e2e_seconds": time.perf_counter() - start,
        }
        return self._save(
            output_dir,
            saved.semantic,
            latents,
            audio,
            saved.noise,
            config,
            timing,
            load_timing_before,
        )

    def _save(
        self, output_dir, semantic, latents, audio, noise, config, timing, load_timing_before
    ) -> RunOutput:
        from lyra.pipeline import SongResult
        from yue2.storage import identity

        pipe = self._loaded()
        request_id = identity(
            {"request": semantic.plan.request.to_dict(), "config": config, "weights": pipe.weights}
        )
        result = SongResult(
            audio, SAMPLE_RATE, semantic, latents, config, pipe.weights, timing, request_id, noise
        )
        result.save_artifacts(output_dir)
        files = sorted(p for p in output_dir.rglob("*") if p.is_file())
        exported = zip(STAGES[:3], ("score.abc", "semantic.npy", "latent.npy"), strict=True)
        return RunOutput(
            output_dir / "audio.flac",
            len(audio) / SAMPLE_RATE,
            files,
            lazy_load_seconds=loads_since(load_timing_before, pipe.load_timing),
            engine_peak_memory_bytes=_mlx_peak_memory_bytes(),
            stage_outputs={
                stage: output_dir / name
                for stage, name in exported
                if (output_dir / name).is_file()
            },
            noise_path=output_dir / "noise.npy" if (output_dir / "noise.npy").is_file() else None,
        )

    def take_command(
        self, request: dict, output_dir: Path, precision: str, steps: int, workdir: Path
    ) -> CliTake:
        """`mlx-yue generate <request> --output <output_dir>` with this Engine's weights."""
        from yue2.protocol import GenerationConfig

        workdir.mkdir(parents=True, exist_ok=True)
        request_path = workdir / "request.json"
        generation = GenerationConfig(ode_steps=steps).to_dict()
        request_path.write_text(json.dumps({**request, "generation_config": generation}))
        argv = [
            str(Path(sys.executable).with_name("mlx-yue")), "generate", str(request_path),
            "--output", str(output_dir),
            "--model", str(self.models_dir / "converted"), "--vae", str(self.models_dir / "vae"),
            "--precision", precision, "--offline",
        ]  # fmt: skip
        if self.require_ac:
            argv.append("--require-ac")
        return CliTake(argv, stage_markers=dict(CLI_STAGE_MARKERS))

    def download_weights(self, target_dir: Path) -> WeightsDownload:
        """The README's `snapshot_download(..., local_dir=...)` for the converted weights
        and the VAE, into `target_dir/converted` and `target_dir/vae`. Only the converted
        repository's small files and the VAE (config, manifest, weights) are downloaded;
        its large weights are cloned from `models_dir/converted`. Running it again over
        the same directory downloads again, as a setup screen's retry would."""
        from huggingface_hub import HfApi, snapshot_download
        from lyra.conversion import VAE_REPO, VAE_REVISION

        api = HfApi()
        converted_revision = api.model_info(CONVERTED_REPO).sha
        plans = [
            {
                "repository": CONVERTED_REPO,
                "revision": converted_revision,
                "local_dir": "converted",
                "ignore_patterns": list(CONVERTED_LOCAL_PATTERNS),
            },
            {
                "repository": VAE_REPO,
                "revision": VAE_REVISION,
                "local_dir": "vae",
                "allow_patterns": list(VAE_PATTERNS),
            },
        ]
        downloaded: list[str] = []
        for plan in plans:
            repo_files = api.list_repo_files(plan["repository"], revision=plan["revision"])
            snapshot_download(
                plan["repository"],
                revision=plan["revision"],
                local_dir=target_dir / plan["local_dir"],
                allow_patterns=plan.get("allow_patterns"),
                ignore_patterns=plan.get("ignore_patterns"),
            )
            downloaded += [
                f"{plan['local_dir']}/{name}"
                for name in repo_files
                if _selected(name, plan.get("allow_patterns"), plan.get("ignore_patterns"))
            ]

        supplied = []
        source_dir = self.models_dir / "converted"
        for source in sorted(source_dir.iterdir()):
            if not any(fnmatch.fnmatch(source.name, p) for p in CONVERTED_LOCAL_PATTERNS):
                continue
            target = target_dir / "converted" / source.name
            if not (target.is_file() and target.stat().st_size == source.stat().st_size):
                target.unlink(missing_ok=True)
                # APFS clone: no extra disk space, and the source is never written.
                subprocess.run(["cp", "-c", str(source), str(target)], check=True)
            supplied.append(
                {"path": f"converted/{source.name}", "source": str(source), "method": "cp -c"}
            )
        return WeightsDownload(
            weight_dirs={"converted": "converted", "vae": "vae"},
            downloaded=sorted(downloaded),
            supplied_locally=supplied,
            sources=plans,
        )

    @staticmethod
    def unexpected_weight_files(weight_dirs: dict[str, Path]) -> list[Path]:
        """Files in the converted directory `verify_conversion` rejects: anything but the
        files its `conversion.json` lists, `conversion.json` itself and `README.md`."""
        converted = Path(weight_dirs["converted"])
        manifest_path = converted / "conversion.json"
        if not manifest_path.is_file():
            return []
        allowed = set(json.loads(manifest_path.read_text())["files"]) | {
            "conversion.json",
            "README.md",
        }
        return sorted(
            path
            for path in converted.rglob("*")
            if path.is_file() and path.relative_to(converted).as_posix() not in allowed
        )

    @staticmethod
    def verify_weights(weight_dirs: dict[str, Path]) -> dict:
        """What `YuE2Pipeline` checks before loading: `verify_conversion` on the converted
        directory (every file hashed) and the VAE's weight identity."""
        from lyra.conversion import verify_conversion
        from yue2.storage import model_identity

        manifest = verify_conversion(Path(weight_dirs["converted"]))
        vae = model_identity(Path(weight_dirs["vae"]))
        return {"converted_files": sorted(manifest["files"]), "vae_files": sorted(vae["files"])}


def _selected(name: str, allow: list[str] | None, ignore: list[str] | None) -> bool:
    if allow is not None and not any(fnmatch.fnmatch(name, p) for p in allow):
        return False
    return not (ignore is not None and any(fnmatch.fnmatch(name, p) for p in ignore))
