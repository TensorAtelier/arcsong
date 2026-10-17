"""Record today's public numbers in docs/product/metrics.md.

Arcsong has no telemetry, so the PM reads GitHub: stars, unique cloners and views (GitHub keeps
only 14 days of traffic, so a day without a snapshot is lost) and release downloads.

    uv run python scripts/metrics.py [--note TEXT] [--dry-run]

Needs the `gh` CLI logged in with push access (traffic is visible to maintainers only). A rerun
on the same day replaces that day's row.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = "TensorAtelier/arcsong"
METRICS = Path(__file__).resolve().parent.parent / "docs" / "product" / "metrics.md"
HEADER = "| Date | Stars |"


def gh(path: str):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def snapshot() -> dict:
    repo = gh(f"repos/{REPO}")
    clones = gh(f"repos/{REPO}/traffic/clones")
    views = gh(f"repos/{REPO}/traffic/views")
    releases = gh(f"repos/{REPO}/releases")
    downloads = sum(asset["download_count"] for r in releases for asset in r["assets"])
    return {
        "stars": repo["stargazers_count"],
        "cloners": clones["uniques"],
        "views": views["uniques"],
        "downloads": downloads,
    }


def row(day: str, numbers: dict, note: str) -> str:
    return (
        f"| {day} | {numbers['stars']} | {numbers['cloners']} | {numbers['views']} "
        f"| {numbers['downloads']} | {note} |"
    )


def write_row(text: str, day: str, line: str) -> str:
    """The metrics file with `line` as `day`'s snapshot: replacing a row for that day, else
    appended after the table's last row."""
    lines = text.splitlines()
    start = next(i for i, current in enumerate(lines) if current.startswith(HEADER))
    end = start + 2  # header and separator
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    for i in range(start + 2, end):
        if lines[i].startswith(f"| {day} |"):
            lines[i] = line
            break
    else:
        lines.insert(end, line)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--note", default="", help="text for the Notes column")
    parser.add_argument("--dry-run", action="store_true", help="print the row, write nothing")
    args = parser.parse_args(argv)
    day = datetime.date.today().isoformat()
    line = row(day, snapshot(), args.note)
    print(line)
    if not args.dry_run:
        METRICS.write_text(write_row(METRICS.read_text(), day, line))
        print(f"written to {METRICS}", file=sys.stderr)


if __name__ == "__main__":
    main()
