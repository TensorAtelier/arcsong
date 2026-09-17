"""Key numbers in the M0 report's hand-written interpretation, recomputed from the committed
results files, so a changed results file cannot silently leave stale interpretation."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "spike" / "results"
REPORT = ROOT / "docs" / "m0-report.md"
GIB = 2**30


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def span(values, fmt="{:.1f}") -> str:
    return f"{fmt.format(min(values))}–{fmt.format(max(values))}"


def interpretation() -> str:
    """The report with generated blocks removed, so matches come from hand-written text."""
    text = REPORT.read_text()
    return re.sub(r"<!-- generated:([\w-]+).*?<!-- /generated:\1 -->", "", text, flags=re.S)


def test_draft_final_arithmetic_matches_results():
    t = load("draft-final-mlx-song-8bit-8-32.json")["timing"]
    draft, final, direct = t["draft_seconds"], t["final_seconds"], t["direct_seconds"]
    text = interpretation()
    for number in (
        f"{draft:.1f}", f"{final:.1f}", f"{direct:.1f}", f"{t['final_to_direct_ratio']:.3f}",
        f"{draft + final:.1f}", f"{draft + final - direct:.1f}",
        f"{2 * draft + final:.1f}", f"{2 * direct:.1f}",
    ):  # fmt: skip
        assert number in text, number
    fallback = load("draft-final-audiocpp-song-q8_0-8-32.json")["draft_to_final"]["fallback"]
    assert f"{fallback['same_seed_rerun']['seconds']:.1f}" in text


def test_cancel_ranges_match_results():
    text = interpretation()
    for engine in ("mlx", "audiocpp"):
        latencies = [
            run["cancel_latency_seconds"]
            for path in sorted(RESULTS.glob(f"cancel-{engine}-*.json"))
            for run in json.loads(path.read_text())["runs"]
        ]
        assert span(latencies, "{:.3f}") in text, engine


def test_memory_and_planning_ranges_match_results():
    text = interpretation()
    peaks = {}
    for precision in ("bf16", "8bit"):
        for steps in (8, 32):
            runs = load(f"timing-mlx-song-{precision}-{steps}.json")["runs"]
            peaks[precision, steps] = [r["lifetime_peak_footprint_bytes"] for r in runs]
    every = [b / GIB for runs in peaks.values() for b in runs]
    assert span(every, "{:.2f}") in text
    savings = [
        (bf16 - q) / GIB
        for steps in (8, 32)
        for bf16, q in zip(peaks["bf16", steps], peaks["8bit", steps], strict=True)
    ]
    assert span(savings, "{:.2f}") in text
    q8 = [
        r["lifetime_peak_footprint_bytes"] / GIB
        for s in (8, 32)
        for r in load(f"timing-audiocpp-song-q8_0-{s}.json")["runs"]
    ]
    assert span(q8, "{:.2f}") in text
    planning = [
        r["stage_seconds"]["planning"]
        for p in ("bf16", "8bit")
        for s in (8, 32)
        for r in load(f"timing-mlx-song-{p}-{s}.json")["runs"]
    ]
    assert span(planning) in text
