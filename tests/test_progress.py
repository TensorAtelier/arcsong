"""The `progress` measurement: which signals fire inside each Stage, how often, and whether
they can drive a % bar. Driven through the SpikeEngine seam with a FakeEngine whose Stages
fire scripted progress signals."""

import json
from functools import partial
from pathlib import Path

import pytest

from spike import cli
from spike.engine import STAGES, ProgressEvent, StageEvent
from spike.fake import FakeEngine
from spike.measurements import progress

PLANNING, SEMANTIC, SYNTHESIS, DECODING = STAGES
SLACK = 0.04


def run_progress(tmp_path, monkeypatch, **options) -> dict:
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))
    results_dir, runs_dir = tmp_path / "results", tmp_path / "runs"
    code = cli.main(
        ["progress", "--engine", "fake", "--results-dir", str(results_dir),
         "--runs-dir", str(runs_dir)]
    )  # fmt: skip
    assert code == 0
    [path] = results_dir.glob("*.json")
    return json.loads(path.read_text())


def evenly(count: int) -> list[float]:
    """`count` signals spread evenly through a Stage, none at its very start or end."""
    return [(i + 0.5) / count for i in range(count)]


SCRIPT = {
    PLANNING: [{"signal": "on_token", "at": evenly(10)}],
    SEMANTIC: [{"signal": "on_token", "at": evenly(20)}],
    SYNTHESIS: [{"signal": "step", "at": evenly(5), "total": True}],
}
SECONDS = {PLANNING: 0.2, SEMANTIC: 0.4, SYNTHESIS: 0.5, DECODING: 0.1}
MIN_UPDATES = progress.MIN_BAR_UPDATES
# mlx-Yue decoding in spike/runs/progress-mlx-song-8bit-8/run-1/progress-events.jsonl.
DECODING_START, DECODING_END = 200.29461470805109, 210.43428287515417
DECODING_UPDATES = (200.424190166872, 205.43453254224733, 210.4218798330985)


def test_a_song_case_records_every_signal_fired_inside_each_stage(tmp_path, monkeypatch):
    result = run_progress(tmp_path, monkeypatch, stage_seconds=SECONDS, progress_signals=SCRIPT)

    assert result["measurement"] == "progress"
    assert result["case"] == "song"
    assert result["params"] == {"precision": "8bit", "steps": 8}
    [run] = result["runs"]
    assert run["outcome"] == "ok"
    stages = run["stages"]
    assert list(stages) == list(STAGES)
    assert stages[PLANNING]["signals"]["on_token"]["count"] == 10
    assert stages[SEMANTIC]["signals"]["on_token"]["count"] == 20
    assert stages[SYNTHESIS]["signals"]["step"]["count"] == 5
    assert stages[DECODING]["signals"] == {}
    for stage, seconds in SECONDS.items():
        assert seconds <= stages[stage]["seconds"] < seconds + SLACK


def test_inter_arrival_times_and_event_rate_come_from_signal_timestamps(tmp_path, monkeypatch):
    result = run_progress(tmp_path, monkeypatch, stage_seconds=SECONDS, progress_signals=SCRIPT)

    step = result["runs"][0]["stages"][SYNTHESIS]["signals"]["step"]
    # Five steps 0.1 s apart in a 0.5 s Stage.
    gaps = step["inter_arrival_seconds"]
    for key in ("min", "median", "max"):
        assert gaps[key] == pytest.approx(0.1, abs=SLACK), key
    assert step["per_second"]["mean"] == pytest.approx(10, rel=0.15)
    assert step["per_second"]["max_in_one_second"] == 5


def test_known_total_is_told_apart_from_a_running_count(tmp_path, monkeypatch):
    result = run_progress(tmp_path, monkeypatch, stage_seconds=SECONDS, progress_signals=SCRIPT)

    stages = result["runs"][0]["stages"]
    step = stages[SYNTHESIS]["signals"]["step"]
    assert step["total_known_up_front"] is True
    assert step["running_count_only"] is False
    token = stages[SEMANTIC]["signals"]["on_token"]
    assert token["total_known_up_front"] is False
    assert token["running_count_only"] is True
    assert stages[SYNTHESIS]["percent_bar"]["verdict"] == "percent"
    assert stages[SEMANTIC]["percent_bar"]["verdict"] == "count_only"
    assert stages[DECODING]["percent_bar"]["verdict"] == "none"


def test_progress_bunched_at_a_stage_start_does_not_track_wall_time(tmp_path, monkeypatch):
    bunched = [0.02 + 0.02 * i for i in range(8)]
    script = {**SCRIPT, DECODING: [{"signal": "chunk", "at": bunched, "total": True}]}
    seconds = {**SECONDS, DECODING: 0.5}

    result = run_progress(tmp_path, monkeypatch, stage_seconds=seconds, progress_signals=script)

    stages = result["runs"][0]["stages"]
    even = stages[SYNTHESIS]["signals"]["step"]["tracks_wall_time"]
    assert even["linear"] is True
    assert even["max_deviation"] < 0.15
    chunk = stages[DECODING]["signals"]["chunk"]["tracks_wall_time"]
    assert chunk["linear"] is False
    # All 8 of 8 done 0.16 of the way in: the bar runs 0.84 ahead of wall time.
    assert chunk["max_deviation"] == pytest.approx(0.84, abs=0.1)
    assert stages[DECODING]["percent_bar"]["verdict"] == "uneven_percent"


def test_the_raw_signal_timeline_is_kept_in_the_run_directory(tmp_path, monkeypatch):
    run_progress(tmp_path, monkeypatch, stage_seconds=SECONDS, progress_signals=SCRIPT)

    [events_file] = (tmp_path / "runs").rglob(progress.EVENTS_NAME)
    lines = [json.loads(line) for line in events_file.read_text().splitlines()]
    assert sum(e["kind"] == "progress" for e in lines) == 35
    assert {e["kind"] for e in lines} == {"start", "end", "progress"}


# ---------------------------------------------------------------- exact statistics


def spans(**stages: tuple[float, float]) -> list:
    return [
        StageEvent(stage.replace("_", " "), kind, t)
        for stage, (start, end) in stages.items()
        for kind, t in (("start", start), ("end", end))
    ]


def test_signals_are_attributed_to_the_stage_whose_span_holds_them():
    events = [
        *spans(planning=(0.0, 10.0), synthesis=(10.0, 20.0)),
        ProgressEvent(None, "line", t=10.0),  # the line ending planning: in neither Stage
        ProgressEvent(None, "line", t=12.0),
        ProgressEvent(None, "line", t=13.0),
        ProgressEvent(None, "line", t=17.0),
        ProgressEvent(None, "line", t=25.0),  # after every Stage
    ]

    stages = progress.analyse(events)

    line = stages[SYNTHESIS]["signals"]["line"]
    assert line["count"] == 3
    assert line["inter_arrival_seconds"] == {"min": 1.0, "median": 2.5, "max": 4.0}
    assert line["first_after_start_seconds"] == 2.0
    assert line["last_before_end_seconds"] == 3.0
    assert stages[PLANNING]["signals"] == {}
    assert stages[SEMANTIC] == {
        "seconds": None,
        "signals": {},
        "percent_bar": {"verdict": "not_run", "signal": None},
    }


def test_linearity_uses_the_counts_a_signal_carries_or_else_its_share_of_arrivals():
    events = [
        *spans(synthesis=(0.0, 10.0)),
        # A total discovered with the first update, as yue2's stderr progress lines do.
        ProgressEvent(SYNTHESIS, "stderr", completed=0, t=1.0),
        ProgressEvent(SYNTHESIS, "stderr", completed=1, total=4, t=2.5),
        ProgressEvent(SYNTHESIS, "stderr", completed=2, total=4, t=5.0),
        ProgressEvent(SYNTHESIS, "stderr", completed=4, total=4, t=9.0),
        ProgressEvent(SYNTHESIS, "line", t=9.5),
        ProgressEvent(SYNTHESIS, "line", t=9.9),
    ]

    signals = progress.analyse(events)[SYNTHESIS]["signals"]

    stderr = signals["stderr"]
    assert stderr["total_known_up_front"] is False
    assert stderr["total_known_from_signal"] == 2
    assert stderr["running_count_only"] is False
    assert stderr["total"] == 4
    # Progress 0, .25, .5, 1 at wall-time fractions .1, .25, .5, .9: just before the last
    # update the bar still holds .5 while .9 of the Stage has passed.
    assert stderr["tracks_wall_time"]["max_deviation"] == pytest.approx(0.4)
    assert stderr["tracks_wall_time"]["linear"] is False
    line = signals["line"]
    # Arrival shares .5 and 1 at .95 and .99: the bar holds 0 until .95 of the Stage.
    assert line["tracks_wall_time"]["max_deviation"] == pytest.approx(0.95)
    assert line["running_count_only"] is True
    assert line["inter_arrival_seconds"]["max"] == pytest.approx(0.4)
    assert line["per_second"]["max_in_one_second"] == 2


def test_a_sparse_bar_is_judged_by_the_value_it_holds_between_updates():
    # A sparse % signal like yue2's stderr progress lines (one per 5 s through a pipe).
    start, end = 208.180, 218.958
    events = [
        *spans(decoding=(start, end)),
        ProgressEvent(DECODING, "stderr", completed=0, t=208.310),
        ProgressEvent(DECODING, "stderr", completed=8, total=19, t=213.316),
        ProgressEvent(DECODING, "stderr", completed=17, total=19, t=218.325),
        ProgressEvent(DECODING, "stderr", completed=19, total=19, t=218.938),
    ]

    stage = progress.analyse(events)[DECODING]

    fit = stage["signals"]["stderr"]["tracks_wall_time"]
    # Just before 218.325 the bar holds 8/19 while 0.941 of the Stage has passed.
    held = 8 / 19
    assert fit["max_deviation"] == pytest.approx((218.325 - start) / (end - start) - held)
    assert fit["linear"] is False
    # Four updates are too few to animate a bar, whatever their deviation.
    assert stage["percent_bar"] == {"verdict": "coarse_percent", "signal": "stderr"}


def test_a_percent_signal_with_too_few_updates_is_too_coarse_for_a_bar():
    # mlx-Yue decoding in the committed progress-mlx-song-8bit-8 timeline
    # (spike/runs/progress-mlx-song-8bit-8/run-1/progress-events.jsonl).
    start, end = DECODING_START, DECODING_END
    events = [
        *spans(decoding=(start, end)),
        ProgressEvent(DECODING, "stderr: Decoding audio", completed=0, t=DECODING_UPDATES[0]),
        ProgressEvent(DECODING, "stderr: Decoding audio", 9, 19, DECODING_UPDATES[1]),
        ProgressEvent(DECODING, "stderr: Decoding audio", 19, 19, DECODING_UPDATES[2]),
    ]

    stage = progress.analyse(events)[DECODING]

    fit = stage["signals"]["stderr: Decoding audio"]["tracks_wall_time"]
    # Just before 19/19 arrives the bar still holds 9/19, with nearly all the Stage gone.
    elapsed = (DECODING_UPDATES[2] - start) / (end - start)
    assert fit["max_deviation"] == pytest.approx(elapsed - 9 / 19)
    assert stage["percent_bar"] == {
        "verdict": "coarse_percent",
        "signal": "stderr: Decoding audio",
    }


def test_a_percent_signal_with_enough_updates_is_a_stepped_bar_even_off_wall_time():
    start, end = 0.0, 10.0
    steps = [(2.0 + i, i + 1) for i in range(MIN_UPDATES)]
    events = [
        *spans(decoding=(start, end)),
        *(ProgressEvent(DECODING, "step", done, MIN_UPDATES, t) for t, done in steps),
    ]

    stage = progress.analyse(events)[DECODING]

    assert stage["signals"]["step"]["tracks_wall_time"]["linear"] is False
    assert stage["percent_bar"] == {"verdict": "uneven_percent", "signal": "step"}


def test_a_bar_that_stops_short_is_judged_at_the_stage_end():
    events = [
        *spans(synthesis=(0.0, 10.0)),
        *(ProgressEvent(SYNTHESIS, "step", completed=i, total=10, t=float(i)) for i in (1, 2, 3)),
    ]

    fit = progress.analyse(events)[SYNTHESIS]["signals"]["step"]["tracks_wall_time"]

    assert fit["max_deviation"] == pytest.approx(0.7)


def test_a_single_signal_or_none_cannot_drive_a_bar():
    events = [*spans(decoding=(0.0, 4.0)), ProgressEvent(DECODING, "chunk", t=2.0, total=1)]

    stage = progress.analyse(events)[DECODING]

    assert stage["signals"]["chunk"]["inter_arrival_seconds"] is None
    assert stage["percent_bar"] == {"verdict": "none", "signal": None}


def test_the_best_signal_decides_a_stage_verdict():
    events = [
        *spans(synthesis=(0.0, 8.0)),
        *(ProgressEvent(SYNTHESIS, "line", t=0.5 + i) for i in range(8)),
        *(ProgressEvent(SYNTHESIS, "step", completed=i + 1, total=8, t=i + 1.0) for i in range(8)),
    ]

    bar = progress.analyse(events)[SYNTHESIS]["percent_bar"]

    assert bar == {"verdict": "percent", "signal": "step"}


def test_stage_events_are_kept_apart_from_progress_by_existing_consumers():
    from spike.measurements.timing import stage_seconds

    events = [*spans(planning=(0.0, 2.0)), ProgressEvent(PLANNING, "on_token", t=1.0)]

    assert stage_seconds(events)[PLANNING] == 2.0


def test_the_events_file_lists_events_in_time_order_timed_from_the_run_start(tmp_path: Path):
    events = [*spans(planning=(5.0, 7.0)), ProgressEvent(PLANNING, "on_token", 3, None, 6.0)]

    path = progress.write_events(events, tmp_path, since=5.0)

    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(e["kind"], e["seconds"]) for e in lines] == [
        ("start", 0.0),
        ("progress", 1.0),
        ("end", 2.0),
    ]
    assert lines[1]["signal"] == "on_token" and lines[1]["completed"] == 3


def test_a_running_count_that_tracks_wall_time_beats_a_busier_bunched_one():
    events = [
        *spans(decoding=(0.0, 20.0)),
        *(ProgressEvent(DECODING, "line", t=0.1 + i / 100) for i in range(50)),
        *(ProgressEvent(DECODING, "chunk", t=20 * (i + 0.5) / 6) for i in range(6)),
    ]

    bar = progress.analyse(events)[DECODING]["percent_bar"]

    assert bar == {"verdict": "count_only", "signal": "chunk"}


def test_signals_bunched_at_a_stage_edge_are_an_uneven_count_not_one_to_show():
    # Setup lines as synthesis begins, then silence until it ends (audio.cpp's `--log`).
    events = [
        *spans(synthesis=(0.0, 100.0)),
        *(ProgressEvent(SYNTHESIS, "line", t=0.5 + i / 100) for i in range(30)),
    ]

    bar = progress.analyse(events)[SYNTHESIS]["percent_bar"]

    assert bar == {"verdict": "uneven_count", "signal": "line"}


def test_among_uneven_counts_the_one_closest_to_wall_time_is_named():
    # audio.cpp decoding: many bunched log lines, and chunk lines that start late.
    events = [
        *spans(decoding=(0.0, 20.0)),
        *(ProgressEvent(DECODING, "line", t=0.1 + i / 100) for i in range(50)),
        *(ProgressEvent(DECODING, "chunk", t=3.8 + 3.2 * i) for i in range(6)),
    ]

    bar = progress.analyse(events)[DECODING]["percent_bar"]

    assert bar == {"verdict": "uneven_count", "signal": "chunk"}


def test_a_run_records_whether_stderr_was_a_terminal(tmp_path, monkeypatch):
    # Engines that print progress on stderr (yue2) write far more often to a terminal.
    result = run_progress(tmp_path, monkeypatch, stage_seconds=SECONDS, progress_signals=SCRIPT)

    assert result["runs"][0]["stderr_is_tty"] is False
