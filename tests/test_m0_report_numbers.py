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


def assert_occurs(text: str, number: str, times: int) -> None:
    """Every prose occurrence must carry the recomputed value: editing any one of them to a
    different number lowers the count and fails."""
    assert text.count(number) == times, (number, text.count(number), times)


def interpretation() -> str:
    """The report with generated blocks removed, so matches come from hand-written text."""
    text = REPORT.read_text()
    return re.sub(r"<!-- generated:([\w-]+).*?<!-- /generated:\1 -->", "", text, flags=re.S)


def test_draft_final_arithmetic_matches_results():
    t = load("draft-final-mlx-song-8bit-8-32.json")["timing"]
    draft, final, direct = t["draft_seconds"], t["final_seconds"], t["direct_seconds"]
    text = interpretation()
    for number, times in (
        (f"{draft:.1f}", 4), (f"{final:.1f}", 4), (f"{direct:.1f}", 4),
        (f"{t['final_to_direct_ratio']:.3f}", 1), (f"{draft + final:.1f}", 1),
        (f"{draft + final - direct:.1f}", 2), (f"{2 * draft + final:.1f}", 1),
        (f"{2 * direct:.1f}", 1),
    ):  # fmt: skip
        assert_occurs(text, number, times)
    fallback = load("draft-final-audiocpp-song-q8_0-8-32.json")["draft_to_final"]["fallback"]
    assert_occurs(text, f"{fallback['same_seed_rerun']['seconds']:.1f}", 2)


def test_cancel_ranges_match_results():
    text = interpretation()
    for engine in ("mlx", "audiocpp"):
        latencies = [
            run["cancel_latency_seconds"]
            for path in sorted(RESULTS.glob(f"cancel-{engine}-*.json"))
            for run in json.loads(path.read_text())["runs"]
        ]
        assert_occurs(text, span(latencies, "{:.3f}"), 2)


def test_memory_and_planning_ranges_match_results():
    text = interpretation()
    peaks = {}
    for precision in ("bf16", "8bit"):
        for steps in (8, 32):
            runs = load(f"timing-mlx-song-{precision}-{steps}.json")["runs"]
            peaks[precision, steps] = [r["lifetime_peak_footprint_bytes"] for r in runs]
    every = [b / GIB for runs in peaks.values() for b in runs]
    assert_occurs(text, span(every, "{:.2f}"), 1)
    savings = [
        (bf16 - q) / GIB
        for steps in (8, 32)
        for bf16, q in zip(peaks["bf16", steps], peaks["8bit", steps], strict=True)
    ]
    assert_occurs(text, span(savings, "{:.2f}"), 2)
    q8 = [
        r["lifetime_peak_footprint_bytes"] / GIB
        for s in (8, 32)
        for r in load(f"timing-audiocpp-song-q8_0-{s}.json")["runs"]
    ]
    assert_occurs(text, span(q8, "{:.2f}"), 4)
    planning = [
        r["stage_seconds"]["planning"]
        for p in ("bf16", "8bit")
        for s in (8, 32)
        for r in load(f"timing-mlx-song-{p}-{s}.json")["runs"]
    ]
    assert_occurs(text, span(planning), 2)


def test_progress_within_a_stage_numbers_match_results():
    text = " ".join(interpretation().split())  # prose wraps lines anywhere
    mlx = load("progress-mlx-song-8bit-8.json")["runs"][0]
    audiocpp = load("progress-audiocpp-song-q8_0-8.json")["runs"][0]
    tokens = {
        stage: mlx["stages"][stage]["signals"]["on_token"]
        for stage in ("planning", "semantic generation")
    }
    assert_occurs(text, f"fired {tokens['planning']['count']} times", 1)
    assert_occurs(text, f"{tokens['semantic generation']['count']} times for Semantic tokens", 1)
    peak = max(t["per_second"]["max_in_one_second"] for t in tokens.values())
    assert_occurs(text, f"peaked at {peak} callbacks in one second", 1)
    assert_occurs(text, f"up to {peak} token", 1)
    assert_occurs(text, f"({mlx['progress_events']} progress events", 1)
    assert_occurs(text, f"{mlx['total_seconds']:.1f} s (mlx-Yue 8bit)", 1)
    assert_occurs(text, f"{audiocpp['total_seconds']:.1f} s (audio.cpp q8_0)", 1)
    assert mlx["stderr_is_tty"] is False and audiocpp["stderr_is_tty"] is False
    assert_occurs(text, "with stderr not a terminal", 1)
    fits = {
        stage: mlx["stages"][stage]["signals"][f"stderr: {label}"]
        for stage, label in (("synthesis", "Synthesizing audio"), ("decoding", "Decoding audio"))
    }
    deviation = {s: f["tracks_wall_time"]["max_deviation"] for s, f in fits.items()}
    assert_occurs(text, f"max deviation {deviation['synthesis']:.2f}", 1)
    assert_occurs(text, f"lags wall time by up to {deviation['decoding']:.2f}", 1)
    assert_occurs(text, f"Decoding logged {fits['decoding']['count']} lines", 1)
    assert_occurs(text, f"Synthesis logged {fits['synthesis']['count']} such lines", 1)
    log = {s: e["signals"]["--log line"] for s, e in audiocpp["stages"].items()}
    assert_occurs(text, f"{log['synthesis']['inter_arrival_seconds']['max']:.3f} s", 1)
    assert_occurs(text, f"{log['planning']['inter_arrival_seconds']['max']:.3f} s", 1)
    assert_occurs(text, f"peaked at {log['planning']['per_second']['max_in_one_second']} lines", 1)
    [chunk] = [v for k, v in audiocpp["stages"]["decoding"]["signals"].items() if "VAE" in k]
    assert_occurs(text, f"logged {chunk['count']} `framework.oobleck_audio_vae", 1)
    assert_occurs(text, f"{chunk['inter_arrival_seconds']['median']:.3f} s apart", 1)
