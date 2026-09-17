"""audio.cpp `--log` parsing against real captured output (D-020).

Fixtures are real `audiocpp_cli --log` output from this Mac, one line each, prefixed by
the seconds since the process was launched at which the line arrived on the pipe.
"""

from pathlib import Path

import pytest

from spike.audiocpp_engine import StageLogParser, entered_stages
from spike.engine import STAGES
from spike.measurements.timing import stage_seconds

FIXTURES = Path(__file__).parent / "fixtures"


def feed(name: str) -> tuple[list, StageLogParser]:
    parser = StageLogParser(started=0.0)
    events = []
    for entry in (FIXTURES / name).read_text().splitlines():
        arrived, line = entry.split(" ", 1)
        events.extend(parser.feed(line, float(arrived)))
    return events, parser


def test_given_score_log_yields_the_four_stages_in_order_with_their_durations():
    events, parser = feed("audiocpp_clip_given_score.log")

    assert [(e.stage, e.kind) for e in events] == [
        (stage, kind) for stage in STAGES for kind in ("start", "end")
    ]
    assert all(a.t <= b.t for a, b in zip(events, events[1:], strict=False))
    seconds = stage_seconds(events)
    # Score supplied: planning only tokenises the prompt (yue2.plan_ms 1.076).
    assert seconds["planning"] == pytest.approx(0.001076, abs=1e-6)
    assert seconds["semantic generation"] == pytest.approx(8.08498975, abs=1e-3)
    assert seconds["synthesis"] == pytest.approx(14.098228667, abs=1e-6)
    assert seconds["decoding"] == pytest.approx(1.791829333, abs=1e-6)
    assert events[-1].t == pytest.approx(34.363)


def test_generated_score_log_splits_planning_from_semantic_generation():
    events, parser = feed("audiocpp_clip_generated_score.log")

    assert [(e.stage, e.kind) for e in events] == [
        (stage, kind) for stage in STAGES for kind in ("start", "end")
    ]
    seconds = stage_seconds(events)
    # Planning: prompt tokenising, AR init and writing the Score, ending when
    # yue2.semantic.abc_generate_ms arrives (10.102 s); starts at 0.450 - 0.00086825.
    assert seconds["planning"] == pytest.approx(10.102 - 0.450 + 0.00086825, abs=1e-6)
    assert seconds["semantic generation"] == pytest.approx(17.130 - 10.102, abs=1e-6)
    # Together they cover yue2.plan_ms + yue2.semantic_ms, up to line-arrival jitter.
    assert seconds["planning"] + seconds["semantic generation"] == pytest.approx(
        0.00086825 + 16.679696583, abs=5e-3
    )
    assert seconds["synthesis"] == pytest.approx(4.36839325)
    assert seconds["decoding"] == pytest.approx(1.731020834)
    assert parser.scalars["yue2.semantic.abc_generated_tokens"] == 579


def test_given_score_log_reports_model_load_times():
    _, parser = feed("audiocpp_clip_given_score.log")

    load = parser.load_seconds()
    assert load["session_load_seconds"] == pytest.approx(10.349, abs=2e-3)
    assert load["ar_load_seconds"] == pytest.approx(0.363672875)
    assert load["nar_load_seconds"] == pytest.approx(0.269658083)
    assert load["vae_load_seconds"] == pytest.approx(0.0000485)
    assert parser.scalars["yue2.semantic.tokens"] == 400


def test_lines_without_stage_timings_yield_no_events():
    parser = StageLogParser(started=0.0)

    assert parser.feed("ggml_metal_device_init: testing tensor API for f16 support", 1.0) == []
    assert parser.feed("[TIMING ts=20260916-170044] yue2.ar.init_ms 363.672875", 2.0) == []
    assert parser.feed("audio_out=/tmp/audio.wav", 3.0) == []


def test_a_stage_never_starts_before_the_previous_stage_ended():
    # The CLI's timer keeps counting while the Mac sleeps; the harness's monotonic clock
    # does not, so a logged duration can exceed the time since the previous Stage ended.
    parser = StageLogParser(started=0.0)
    events = []
    for line, t in [
        ("[TIMING ts=0] yue2.plan_ms 1.0", 1.0),
        ("[TIMING ts=0] yue2.semantic.abc_generate_ms 9000.0", 10.0),
        ("[TIMING ts=0] yue2.semantic_ms 19000.0", 20.0),
        ("[TIMING ts=0] yue2.nar_ms 500000.0", 100.0),
        ("[TIMING ts=0] yue2.vae_decode_ms 900000.0", 110.0),
    ]:
        events.extend(parser.feed(line, t))

    seconds = stage_seconds(events)
    assert seconds["synthesis"] == pytest.approx(80.0)
    assert seconds["decoding"] == pytest.approx(10.0)
    assert all(a.t <= b.t for a, b in zip(events, events[1:], strict=False))


def entered(name: str, score_given: bool) -> list[tuple[str, float]]:
    stages = []
    for entry in (FIXTURES / name).read_text().splitlines():
        arrived, line = entry.split(" ", 1)
        stages.extend((stage, float(arrived)) for stage in entered_stages(line, score_given))
    return stages


def test_generated_score_log_announces_each_stage_as_it_begins():
    assert entered("audiocpp_clip_generated_score.log", score_given=False) == [
        ("planning", 0.450),
        ("semantic generation", 10.102),
        ("synthesis", 17.130),
        ("decoding", 21.498),
    ]


def test_given_score_log_announces_semantic_generation_with_planning():
    assert entered("audiocpp_clip_given_score.log", score_given=True) == [
        ("planning", 10.350),
        ("semantic generation", 10.350),
        ("synthesis", 18.435),
        ("decoding", 32.536),
    ]
