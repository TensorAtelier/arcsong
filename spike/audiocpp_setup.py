"""audio.cpp setup (D-006): the pinned release binary and the YuE2 GGUF weights.

Every file is pinned by URL/revision, size and sha256 in `audiocpp_pins.json`. A file is
downloaded to `<name>.part`, hashed while streaming and only moved into place when its
sha256 matches, so any file at its final path has been verified. A second run finds
every file in place and downloads nothing. A mismatch raises `ChecksumMismatch`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
PINS_PATH = SPIKE_DIR / "audiocpp_pins.json"
DEFAULT_VENDOR_DIR = SPIKE_DIR / "vendor"
DEFAULT_MODELS_DIR = SPIKE_DIR / "models"
CLI_NAME = "audiocpp_cli"
EXECUTABLES = ("audiocpp_cli", "audiocpp_gguf", "audiocpp_server")
CHUNK_BYTES = 1 << 20

Log = Callable[[str], None]
Fetch = Callable[..., None]


class ChecksumMismatch(Exception):  # noqa: N818 - reads better at the call site
    """A downloaded file's sha256 differs from its pin."""


@dataclass
class SetupResult:
    cli: Path
    model_dir: Path
    downloaded: list[str] = field(default_factory=list)


def load_pins(path: Path = PINS_PATH) -> dict:
    return json.loads(Path(path).read_text())


def release_dir(vendor_dir: Path, pins: dict) -> Path:
    return Path(vendor_dir) / f"audio.cpp-{pins['release']['tag']}"


def cli_path(vendor_dir: Path = DEFAULT_VENDOR_DIR, pins: dict | None = None) -> Path:
    return release_dir(vendor_dir, pins or load_pins()) / CLI_NAME


def model_dir(models_dir: Path = DEFAULT_MODELS_DIR, pins: dict | None = None) -> Path:
    return Path(models_dir) / (pins or load_pins())["weights"]["directory"]


def weight_url(weights: dict, path: str) -> str:
    return f"https://huggingface.co/{weights['repo']}/resolve/{weights['revision']}/{path}"


def fetch_url(url: str, destination: Path, log: Log = print) -> None:
    """Stream a public URL to a file, reporting progress about every 10 s."""
    request = urllib.request.Request(url, headers={"User-Agent": "songloom-spike"})
    with urllib.request.urlopen(request) as response, open(destination, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done, last = 0, time.monotonic()
        while chunk := response.read(CHUNK_BYTES):
            out.write(chunk)
            done += len(chunk)
            if time.monotonic() - last > 10:
                last = time.monotonic()
                share = f" ({done / total:.0%})" if total else ""
                log(f"  {destination.name}: {done / 2**30:.2f} GiB{share}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_file(
    name: str, url: str, size: int, sha256: str, destination: Path, fetch: Fetch, log: Log
) -> bool:
    """Download and verify one pinned file unless it is already in place. True if fetched."""
    if destination.is_file() and destination.stat().st_size == size:
        log(f"have {name}")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    log(f"download {name} ({size / 2**20:.1f} MiB) from {url}")
    try:
        fetch(url, part, log=log)
        actual = sha256_of(part)
        if actual != sha256:
            raise ChecksumMismatch(
                f"sha256 mismatch for {name}: expected {sha256}, got {actual} (from {url})"
            )
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    os.replace(part, destination)
    log(f"verified {name} sha256 {sha256}")
    return True


def _unpack(tarball: Path, destination: Path, log: Log) -> None:
    if (destination / CLI_NAME).is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".unpack-", dir=destination.parent))
    try:
        with tarfile.open(tarball) as tar:
            tar.extractall(staging, filter="data")
        for name in EXECUTABLES:
            binary = staging / name
            if binary.is_file():
                binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if not (staging / CLI_NAME).is_file():
            raise RuntimeError(f"{tarball.name} contains no {CLI_NAME}")
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    log(f"unpacked {tarball.name} into {destination}")


def setup(
    pins: dict,
    vendor_dir: Path = DEFAULT_VENDOR_DIR,
    models_dir: Path = DEFAULT_MODELS_DIR,
    *,
    fetch: Fetch | None = None,
    log: Log = print,
) -> SetupResult:
    fetch = fetch or fetch_url
    vendor_dir, models_dir = Path(vendor_dir), Path(models_dir)
    downloaded: list[str] = []

    release = pins["release"]
    tarball = vendor_dir / "downloads" / release["asset"]
    if ensure_file(
        release["asset"], release["url"], release["size"], release["sha256"], tarball, fetch, log
    ):
        downloaded.append(release["asset"])
    _unpack(tarball, release_dir(vendor_dir, pins), log)

    weights = pins["weights"]
    target = model_dir(models_dir, pins)
    for pin in weights["files"]:
        url = weight_url(weights, pin["path"])
        if ensure_file(
            pin["path"], url, pin["size"], pin["sha256"], target / pin["path"], fetch, log
        ):
            downloaded.append(pin["path"])

    return SetupResult(cli=cli_path(vendor_dir, pins), model_dir=target, downloaded=downloaded)
