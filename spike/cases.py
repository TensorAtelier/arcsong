"""Fixed test cases (D-007): identical Song requests for every Engine."""

from __future__ import annotations

import json
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent / "cases"
CASE_NAMES = ("clip", "song")


def load_case(name: str) -> dict:
    if name not in CASE_NAMES:
        raise ValueError(f"unknown case {name!r}; expected one of {CASE_NAMES}")
    return json.loads((CASES_DIR / f"{name}.json").read_text())
