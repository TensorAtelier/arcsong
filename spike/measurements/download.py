"""`download`: does a hub download into a local directory pass the Engine's weight checks?

Decisions: D-013 (method), D-015 (failures as outcomes).

The Engine's optional `download_weights` capability fetches its smallest weight set that
still lets its verification run into a temporary directory (large weights it can take
from an existing local copy are supplied without downloading). Every file that is
neither downloaded nor supplied is metadata the hub wrote. The Engine's
`verify_weights` then runs on the result. While it fails, fixes are applied one at a
time, cumulatively: first deleting the metadata directories (e.g. `.cache`), then the
files the Engine's verification does not accept (`unexpected_weight_files`). The same
download is then run again over the fixed directory, to see whether the metadata comes
back and the fix is still needed. The temporary directory is always deleted.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from spike.engine import SpikeEngine, Unsupported

MEASUREMENT = "download"
CASE = "weights"
DELETE_METADATA = "delete the hub's metadata directories"
DELETE_UNEXPECTED = "delete files the Engine's verification does not accept"


def _files(root: Path) -> dict[str, int]:
    return {
        path.relative_to(root).as_posix(): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _verify(engine, weight_dirs: dict[str, Path]) -> dict:
    start = time.monotonic()
    try:
        engine.verify_weights(weight_dirs)
    except Exception as error:  # noqa: BLE001 - a failed verification is the finding
        return {
            "outcome": "failed",
            "error": f"{type(error).__name__}: {error}",
            "seconds": time.monotonic() - start,
        }
    return {"outcome": "ok", "seconds": time.monotonic() - start}


def _metadata_dirs(root: Path, weight_dirs: dict[str, Path], metadata: list[str]) -> list[Path]:
    """The top-level entries of each weight directory that hold nothing but metadata."""
    known = set(_files(root)) - set(metadata)
    found: set[Path] = set()
    for name in metadata:
        path = root / name
        for weight_dir in weight_dirs.values():
            if path.is_relative_to(weight_dir):
                top = weight_dir / path.relative_to(weight_dir).parts[0]
                prefix = top.relative_to(root).as_posix()
                holds_known = any(PurePosixPath(k).is_relative_to(prefix) for k in known)
                if not holds_known:
                    found.add(top)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def _remove(paths: list[Path], root: Path) -> list[str]:
    removed = []
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
            # A directory the removed file leaves empty would be rejected just the same.
            parent = path.parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        else:
            continue
        removed.append(path.relative_to(root).as_posix())
    return removed


def _fix(engine, root: Path, weight_dirs: dict[str, Path], metadata: list[str], verification):
    steps: list[dict] = []
    if verification["outcome"] == "ok":
        return steps
    candidates: list[tuple[str, Callable[[], list[Path]]]] = [
        (DELETE_METADATA, lambda: _metadata_dirs(root, weight_dirs, metadata)),
        (DELETE_UNEXPECTED, lambda: list(engine.unexpected_weight_files(weight_dirs))),
    ]
    for name, targets in candidates:
        removed = _remove(targets(), root)
        if not removed:
            continue
        verification = _verify(engine, weight_dirs)
        steps.append({"fix": name, "removed": removed, "verification": verification})
        if verification["outcome"] == "ok":
            break
    return steps


def _download_and_verify(engine, root: Path) -> dict:
    start = time.monotonic()
    fetched = engine.download_weights(root)
    seconds = time.monotonic() - start
    files = _files(root)
    known = set(fetched.downloaded) | {item["path"] for item in fetched.supplied_locally}
    metadata = sorted(path for path in files if path not in known)
    weight_dirs = {key: root / value for key, value in fetched.weight_dirs.items()}
    verification = _verify(engine, weight_dirs)
    return {
        "sources": fetched.sources,
        "download_seconds": seconds,
        "files": [{"path": path, "bytes": size} for path, size in files.items()],
        "downloaded": sorted(fetched.downloaded),
        "supplied_locally": fetched.supplied_locally,
        "metadata_files": metadata,
        "verification": verification,
        "fixes": _fix(engine, root, weight_dirs, metadata, verification),
    }


def measure(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    if not hasattr(engine, "download_weights"):
        raise Unsupported("the Engine has no weight download")
    temp_dir = Path(tempfile.mkdtemp(prefix="download-", dir=run_dir))
    record: dict = {"temp_dir": str(temp_dir)}
    try:
        record.update(_download_and_verify(engine, temp_dir))
        again = _download_and_verify(engine, temp_dir)
        record["after_redownload"] = {
            key: again[key]
            for key in ("download_seconds", "metadata_files", "verification", "fixes")
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        record["temp_dir_deleted"] = not temp_dir.exists()
    return record


def summarize(runs: list[dict], stem: str) -> dict:
    [run] = runs
    fixes = run["fixes"]
    works = run["verification"]["outcome"] == "ok" or (
        bool(fixes) and fixes[-1]["verification"]["outcome"] == "ok"
    )
    return {
        "fix": {
            "works": works,
            "removed": [path for step in fixes for path in step["removed"]],
            "steps": [step["fix"] for step in fixes],
        }
    }
