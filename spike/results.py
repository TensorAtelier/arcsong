"""Results schema (spec): one JSON file per case, read by the report generator."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
OUTCOMES = ("ok", "unsupported", "failed", "oom")


def case_stem(measurement: str, engine: str, case: str, params: dict[str, Any]) -> str:
    parts = [measurement, engine, case, *(str(v) for v in params.values())]
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", "-".join(parts))


def build_result(
    *,
    measurement: str,
    engine: str,
    engine_version: str | None,
    case: str,
    params: dict[str, Any],
    env: dict[str, Any],
    outcome: str,
    started_at: str,
    total_seconds: float,
    runs: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "measurement": measurement,
        "engine": engine,
        "engine_version": engine_version,
        "case": case,
        "params": params,
        "env": env,
        "outcome": outcome,
        "started_at": started_at,
        "total_seconds": total_seconds,
        "runs": runs,
    }
    if error is not None:
        result["error"] = error
    return result


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
