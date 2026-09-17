"""The model weights an Engine needs: where they live, whether they are all there, and how to
download them. `download()` runs in its own spawned process (see `songloom.setup`), so a
cancel is a kill and the server never imports MLX."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol

MODELS_ENV = "SONGLOOM_MLX_MODELS"

# A check the Setup page lists: status is "ok", "warn" or "fail".
Check = dict[str, str]
# The download process reports its phase ("downloading", "verifying") through this.
Phase = Callable[[str], None]


def check(id: str, label: str, status: str, detail: str) -> Check:
    return {"id": id, "label": label, "status": status, "detail": detail}


def models_dir(data: Path, override: str | Path | None = None) -> Path:
    """The weights directory: an explicit override, else `$SONGLOOM_MLX_MODELS`, else
    `<data>/models`."""
    chosen = override or os.environ.get(MODELS_ENV)
    return Path(chosen).expanduser().resolve() if chosen else data / "models"


class Models(Protocol):
    directory: Path

    def files(self) -> dict[str, int]:
        """Every file the Engine needs, relative to `directory`, with its size in bytes."""

    def stray_files(self) -> list[str]:
        """Files that would make the Engine reject an otherwise complete directory."""

    def engine_checks(self) -> list[Check]:
        """Checks only this Engine knows how to run (platform, runtime). May be slow."""

    def download(self, phase: Phase) -> None:
        """Fetch whatever is missing, clean up, and verify; raises if the result is unusable."""


def weights_state(models: Models) -> dict[str, Any]:
    """How much of the weights is on disk, from file sizes alone (no hashing)."""
    wanted = models.files()
    present = 0
    missing = []
    for name, size in wanted.items():
        path = models.directory / name
        if path.is_file() and path.stat().st_size == size:
            present += size
        else:
            missing.append(name)
    stray = models.stray_files()
    return {
        "dir": str(models.directory),
        "installed": not missing and not stray,
        "bytes_total": sum(wanted.values()),
        "bytes_present": present,
        "bytes_on_disk": bytes_on_disk(models),
        "missing": missing,
        "stray": stray,
    }


def bytes_on_disk(models: Models) -> int:
    """What this part's download has written so far, the file it is still fetching included.
    Counts only the files the part declares, because two parts can share one directory (the
    covers weights sit beside the song weights)."""
    written = missing = 0
    for name, size in models.files().items():
        path = models.directory / name
        if path.is_file():
            written += min(path.stat().st_size, size)
        else:
            missing += size
    return written + min(_incomplete_bytes(models), missing)


def _incomplete_bytes(models: Models) -> int:
    """Bytes in the hub's part-downloaded files. It names them by hash
    (`<local dir>/.cache/huggingface/download/…/<hash>.<etag>.incomplete`), so the only honest
    way to count them is to look, not to rebuild the name."""
    roots = {
        models.directory / Path(name).parts[0]
        for name in models.files()
        if len(Path(name).parts) > 1
    }
    total = 0
    for root in roots:
        cache = root / ".cache" / "huggingface" / "download"
        if cache.is_dir():
            total += sum(f.stat().st_size for f in cache.rglob("*.incomplete") if f.is_file())
    return total


# --- mlx-Yue --------------------------------------------------------------------------------

# Pre-converted weights (mlx-Yue README) at the revision M0 downloaded and verified, and the
# VAE at the revision mlx-Yue pins (`lyra.conversion.VAE_REVISION`).
CONVERTED_REPO = "vanch007/mlx-Yue2-3B"
CONVERTED_REVISION = "fa66d203dd56d7e033e05ee8b32269768984c4cc"
VAE_REPO = "m-a-p/YuE2-Vae"
VAE_REVISION = "95535e72a97bc0f09b8ada125d26b4009428c0e8"

# Sizes at those revisions (Hugging Face file metadata, 2026-09-17).
CONVERTED_FILES = {
    "LICENSE": 20309,
    "README.md": 3262,
    "THIRD_PARTY_NOTICES.md": 793,
    "ar-8bit.safetensors": 2656158264,
    "ar-bf16.safetensors": 4331951136,
    "config.json": 959,
    "conversion.json": 3784,
    "licenses/SnakeBeta-NVIDIA-MIT.txt": 1076,
    "licenses/stable-audio-tools-MIT.txt": 1069,
    "nar-bf16.safetensors": 2929490456,
    "qwen.tiktoken": 2561218,
}
VAE_FILES = {
    "LICENSE": 20309,
    "README.md": 8975,
    "THIRD_PARTY_NOTICES.md": 793,
    "config.json": 1378,
    "licenses/SnakeBeta-NVIDIA-MIT.txt": 1076,
    "licenses/stable-audio-tools-MIT.txt": 1069,
    "model.safetensors": 530512720,
    "weights_manifest.json": 178,
}
# Only these VAE files are required to load; the rest are its licence and notices.
VAE_REQUIRED = ("config.json", "model.safetensors", "weights_manifest.json")
# `verify_conversion` rejects any other file in the converted directory (M0: the hub's
# `.cache` metadata and the repository's `.gitattributes`).
CONVERTED_ALLOWED_EXTRA = {"README.md"}
LICENCE = {
    "id": "CC-BY-NC-4.0",
    "name": "Creative Commons Attribution-NonCommercial 4.0",
    "url": "https://creativecommons.org/licenses/by-nc/4.0/legalcode",
    # Every set of weights songloom downloads, song and covers alike, under this one licence.
    "models": [
        "https://huggingface.co/m-a-p/YuE2-3B",
        "https://huggingface.co/m-a-p/YuE2-Vae",
        f"https://huggingface.co/{CONVERTED_REPO}",
        "https://huggingface.co/m-a-p/SheetSage2",
        "https://huggingface.co/m-a-p/MERT-v2-FullSong",
    ],
}
RUNTIME_CHECK_SECONDS = 60


@dataclass
class MlxYueModels:
    directory: Path

    def files(self) -> dict[str, int]:
        converted = {f"converted/{name}": size for name, size in CONVERTED_FILES.items()}
        vae = {f"vae/{name}": VAE_FILES[name] for name in VAE_REQUIRED}
        return {**converted, **vae}

    def stray_files(self) -> list[str]:
        converted = self.directory / "converted"
        if not converted.is_dir():
            return []
        allowed = set(CONVERTED_FILES) | CONVERTED_ALLOWED_EXTRA
        stray = {
            path.relative_to(converted).parts[0]
            for path in converted.rglob("*")
            if path.is_file() and path.relative_to(converted).as_posix() not in allowed
        }
        return sorted(f"converted/{name}" for name in stray)

    def engine_checks(self) -> list[Check]:
        return [_runtime_check(), _engine_version_check()]

    def download(self, phase: Phase) -> None:
        from huggingface_hub import snapshot_download

        phase("downloading")
        snapshot_download(
            CONVERTED_REPO,
            revision=CONVERTED_REVISION,
            local_dir=self.directory / "converted",
            ignore_patterns=[".gitattributes"],
        )
        snapshot_download(
            VAE_REPO,
            revision=VAE_REVISION,
            local_dir=self.directory / "vae",
            allow_patterns=sorted(VAE_FILES),
        )
        shutil.rmtree(self.directory / "vae" / ".cache", ignore_errors=True)
        # Everything `verify_conversion` would reject: the hub's `.cache`, `.gitattributes`, and
        # anything else that landed there (e.g. a Finder `.DS_Store`).
        for name in self.stray_files():
            path = self.directory / name
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)

        phase("verifying")
        from lyra.conversion import verify_conversion
        from yue2.storage import model_identity

        verify_conversion(self.directory / "converted")
        model_identity(self.directory / "vae")


def _runtime_check() -> Check:
    """mlx-Yue's own platform check (Apple Silicon, macOS, Metal), in a short subprocess so
    the server never imports MLX."""
    label = "Apple Silicon and Metal"
    code = (
        "import json; from lyra.runtime import runtime_status; "
        "print(json.dumps(runtime_status()))"
    )
    try:
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=RUNTIME_CHECK_SECONDS,
            check=True,
        ).stdout
        status = json.loads(out.strip().splitlines()[-1])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        return check("runtime", label, "fail", f"mlx-Yue could not check the runtime: {detail}")
    if not status["supported"]:
        return check("runtime", label, "fail", status["error"])
    device = status.get("device", {}).get("device_name") or status["machine"]
    return check("runtime", label, "ok", f"{device}, macOS {status['macos']}, Metal available")


def _engine_version_check() -> Check:
    label = "mlx-Yue"
    try:
        dist = metadata.distribution("mlx-yue")
    except metadata.PackageNotFoundError:
        return check("engine", label, "fail", "mlx-yue is not installed; run `uv sync`")
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    commit = direct.get("vcs_info", {}).get("commit_id")
    return check("engine", label, "ok", f"{dist.version}" + (f" @ {commit[:7]}" if commit else ""))


# --- transcription (covers) -------------------------------------------------------------------

# The SheetSage2 adapter and its MERT-v2 parent, at the revisions mlx-Yue pins
# (`lyra.transcription.model`). Both are CC BY-NC 4.0, like the song weights.
SHEETSAGE_REPO = "m-a-p/SheetSage2"
SHEETSAGE_REVISION = "eab522a8168e8b8b8c4856bf8609cd86198f01fe"
MERT_REPO = "m-a-p/MERT-v2-FullSong"
MERT_REVISION = "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42"
# Sizes at those revisions (Hugging Face file metadata, 2026-09-17). Only these two files are
# fetched, which is what mlx-Yue's `resolve_models` asks the hub for.
TRANSCRIPTION_FILES = {
    "sheetsage2/config.json": 2060,
    "sheetsage2/model.safetensors": 228738564,
    "mert2/config.json": 882,
    "mert2/model.safetensors": 2529812848,
}
FFMPEG_HINT = "install it with `brew install ffmpeg`"


@dataclass
class TranscriptionModels:
    """The weights a cover needs: SheetSage2 and the MERT2 it adapts."""

    directory: Path

    def files(self) -> dict[str, int]:
        return dict(TRANSCRIPTION_FILES)

    def stray_files(self) -> list[str]:
        return []  # nothing here rejects extra files, unlike the converted song weights

    def engine_checks(self) -> list[Check]:
        return [_ffmpeg_check()]

    def download(self, phase: Phase) -> None:
        from huggingface_hub import snapshot_download

        phase("downloading")
        for repo, revision, local in (
            (SHEETSAGE_REPO, SHEETSAGE_REVISION, "sheetsage2"),
            (MERT_REPO, MERT_REVISION, "mert2"),
        ):
            snapshot_download(
                repo,
                revision=revision,
                local_dir=self.directory / local,
                allow_patterns=["config.json", "model.safetensors"],
            )
            shutil.rmtree(self.directory / local / ".cache", ignore_errors=True)

        phase("verifying")
        self.verify()

    def verify(self) -> None:
        """What `SheetSage2.from_pretrained` checks before it loads: that the MERT2 file is the
        parent SheetSage2 was trained against. Hashing only, so no MLX import."""
        from yue2.storage import sha256_file

        config = json.loads((self.directory / "sheetsage2" / "config.json").read_text())
        expected = config["base_model_sha256"]
        digest = sha256_file(self.directory / "mert2" / "model.safetensors")
        if digest != expected:
            raise ValueError("the MERT2 weights do not match the SheetSage2 checkpoint")


def _ffmpeg_check() -> Check:
    """ffmpeg decodes the upload. It is a separate program with its own licence, so songloom
    looks for it rather than shipping it."""
    label = "ffmpeg"
    try:
        out = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=20, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return check("ffmpeg", label, "fail", f"not found; covers need it — {FFMPEG_HINT}")
    version = out.splitlines()[0] if out.strip() else "installed"
    return check("ffmpeg", label, "ok", version)


# --- fake -----------------------------------------------------------------------------------


@dataclass
class FakeModels:
    """Weights for the fake Engine: one small file, downloaded in slices. `preinstalled` needs
    no files at all, which is what tests of other features want."""

    directory: Path
    preinstalled: bool = True
    size: int = 64_000
    download_seconds: float = 0.2
    fail_download: str | None = None
    fail_verify: str | None = None
    checks: list[Check] = field(default_factory=list)

    def files(self) -> dict[str, int]:
        return {} if self.preinstalled else {"weights.bin": self.size}

    def stray_files(self) -> list[str]:
        return []

    def engine_checks(self) -> list[Check]:
        return list(self.checks) or [check("runtime", "Fake runtime", "ok", "no GPU needed")]

    def download(self, phase: Phase) -> None:
        phase("downloading")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "weights.bin"
        slices = 20
        with path.open("ab") as out:
            while (written := out.tell()) < self.size:
                if self.fail_download and written >= self.size // 2:
                    raise RuntimeError(self.fail_download)
                out.write(b"\0" * min(self.size // slices, self.size - written))
                out.flush()
                time.sleep(self.download_seconds / slices)
        phase("verifying")
        if self.fail_verify:
            raise ValueError(self.fail_verify)

