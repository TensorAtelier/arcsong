"""`scripts/metrics.py`: one snapshot row per day in docs/product/metrics.md."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "metrics_script", Path(__file__).resolve().parent.parent / "scripts" / "metrics.py"
)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)

TABLE = """# Metrics

## Snapshots

| Date | Stars | Unique cloners (14 d) | Views (14 d, unique) | Release downloads | Notes |
|---|---|---|---|---|---|
| 2026-10-17 | 0 | 9 | 3 | 1 | Baseline. |

Trailing prose stays put.
"""
NUMBERS = {"stars": 4, "cloners": 12, "views": 30, "downloads": 2}


def test_a_new_day_is_appended_after_the_last_row():
    line = metrics.row("2026-10-24", NUMBERS, "after the announcement")
    out = metrics.write_row(TABLE, "2026-10-24", line)

    lines = out.splitlines()
    assert lines[lines.index("| 2026-10-17 | 0 | 9 | 3 | 1 | Baseline. |") + 1] == (
        "| 2026-10-24 | 4 | 12 | 30 | 2 | after the announcement |"
    )
    assert out.endswith("Trailing prose stays put.\n")


def test_a_rerun_on_the_same_day_replaces_that_row():
    out = metrics.write_row(TABLE, "2026-10-17", metrics.row("2026-10-17", NUMBERS, "rerun"))

    assert "| 2026-10-17 | 4 | 12 | 30 | 2 | rerun |" in out
    assert "Baseline." not in out
    assert out.count("| 2026-10-17 |") == 1
