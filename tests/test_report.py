"""`spike report`: the M0 report's tables regenerated from results files.

Fixture results are trimmed copies of real results files (including ticket 01's older
doctor shape) plus one failed case; the rest of the matrix is deliberately missing.
"""

import re
import shutil
from pathlib import Path

from spike import cli
from spike.report import QUESTIONS

FIXTURES = Path(__file__).parent / "fixtures" / "report"


def run_report(tmp_path, results_dir: Path) -> str:
    out = tmp_path / "docs" / "m0-report.md"
    code = cli.main(["report", "--results-dir", str(results_dir), "--out", str(out)])
    assert code == 0
    return out.read_text()


def fixture_results(tmp_path) -> Path:
    results_dir = tmp_path / "results"
    shutil.copytree(FIXTURES, results_dir)
    return results_dir


def section(report: str, title: str) -> str:
    """The text under a `## title` heading, up to the next `## ` heading."""
    match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", report, re.M | re.S)
    assert match, f"no section {title!r}"
    return match.group(1)


def test_every_m0_question_gets_a_section(tmp_path):
    report = run_report(tmp_path, fixture_results(tmp_path))

    titles = [title for _, title in QUESTIONS]
    assert titles == [
        "Engine choice",
        "Per-Stage timing split",
        "Seed reproducibility",
        "Artifact sizes",
        "Per-Stage progress",
        "Cancellation",
        "Draft→Final",
        "Timing and peak memory",
        "Stale resource files",
        "Model download",
    ]
    for title in titles:
        assert section(report, title).strip()


def test_without_results_every_question_is_not_measured(tmp_path):
    empty = tmp_path / "results"
    empty.mkdir()
    report = run_report(tmp_path, empty)

    for _, title in QUESTIONS:
        assert "not measured" in section(report, title), title


def test_tables_are_filled_from_results_and_cite_their_file(tmp_path):
    report = run_report(tmp_path, fixture_results(tmp_path))

    timing = section(report, "Per-Stage timing split")
    # timing-mlx-song-8bit-8.json run 1: synthesis 97.0877... s of 234.4 s of Stages.
    row = next(line for line in timing.splitlines() if "| 8bit | 8 | 1 |" in line)
    assert "97.1" in row and "timing-mlx-song-8bit-8.json" in row

    memory = section(report, "Timing and peak memory")
    # lifetime_peak_footprint_bytes 11517483056 = 10.73 GiB
    assert "10.73" in memory

    cancel = section(report, "Cancellation")
    audiocpp = next(line for line in cancel.splitlines() if "cancel-audiocpp-clip" in line)
    assert "0.065" in audiocpp and "kill" in audiocpp


def test_missing_and_failed_cases_are_shown(tmp_path):
    report = run_report(tmp_path, fixture_results(tmp_path))

    timing = section(report, "Timing and peak memory")
    bf16_32 = next(line for line in timing.splitlines() if "| mlx-Yue | bf16 | 32 |" in line)
    assert "not measured" in bf16_32
    failed = next(line for line in timing.splitlines() if "| audio.cpp | q8_0 | 8 |" in line)
    assert "failed" in failed and "timing-audiocpp-song-q8_0-8.json" in failed
    assert "not measured" in section(report, "Stale resource files")
    assert "not measured" in section(report, "Model download")


def test_the_older_doctor_shape_is_read(tmp_path):
    report = run_report(tmp_path, fixture_results(tmp_path))

    choice = section(report, "Engine choice")
    assert "doctor-mlx-clip-bf16-32.json" in choice


def test_regenerating_keeps_hand_written_text_and_is_stable(tmp_path):
    results_dir = fixture_results(tmp_path)
    first = run_report(tmp_path, results_dir)
    out = tmp_path / "docs" / "m0-report.md"
    edited = first.replace(
        "## Cancellation\n", "## Cancellation\n\nHand-written: cancel is fast.\n", 1
    )
    out.write_text(edited)

    second = run_report(tmp_path, results_dir)
    third = run_report(tmp_path, results_dir)

    assert "Hand-written: cancel is fast." in second
    assert second == third == edited


def test_regenerating_updates_tables_when_results_change(tmp_path):
    results_dir = fixture_results(tmp_path)
    first = run_report(tmp_path, results_dir)
    (results_dir / "timing-mlx-song-8bit-8.json").unlink()

    second = run_report(tmp_path, results_dir)

    assert second != first
    row = next(
        line
        for line in section(second, "Timing and peak memory").splitlines()
        if "| mlx-Yue | 8bit | 8 |" in line
    )
    assert "not measured" in row
