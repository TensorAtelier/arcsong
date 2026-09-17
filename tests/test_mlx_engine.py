"""mlx-Yue load bookkeeping, without weights: only the pipeline's `load_timing` dict."""

import re

import pytest

from spike.mlx_engine import StderrProgress, loads_since, progress_line


def test_a_run_reports_only_the_weights_it_loaded_itself():
    before = {
        "ar_load_events_seconds": (0.5,),
        "ar_load_seconds": 0.5,
        "resolve_conversion_integrity_seconds": 6.0,
    }
    after = {
        **before,
        "ar_load_events_seconds": (0.5, 0.25),
        "ar_load_seconds": 0.75,
        "nar_load_events_seconds": (0.125,),
        "nar_load_seconds": 0.125,
    }

    assert loads_since(before, after) == pytest.approx(
        {"ar_load_seconds": 0.25, "nar_load_seconds": 0.125}
    )


def test_a_run_that_loaded_nothing_reports_no_loads():
    timing = {"vae_load_events_seconds": (0.1,), "vae_load_seconds": 0.1}

    assert loads_since(timing, dict(timing)) == {}


# ---------------------------------------------------------------- progress inside a Stage


def progress_lines(tty: bool) -> list[str]:
    """What yue2's own `Progress` writes for a synthesis Stage, through a pipe or a TTY."""
    import io

    from yue2 import progress as yue2_progress

    class Stream(io.StringIO):
        def isatty(self):
            return tty

    stream = Stream()
    reporter = yue2_progress.Progress(stream=stream, refresh_interval=0.25)
    reporter._interval = 0.0  # render every update, so each state shows up once
    with reporter.stage("Synthesizing audio", unit="steps") as stage:
        stage.update(3, total=8)
        stage.update(8, total=8)
    reporter.close()
    return [line for line in re.split(r"[\r\n]", stream.getvalue()) if line.strip()]


@pytest.mark.parametrize("tty", [False, True])
def test_yue2_progress_lines_give_label_count_and_total(tty):
    parsed = [progress_line(line) for line in progress_lines(tty)]

    assert ("Synthesizing audio", 0, None) in parsed
    assert ("Synthesizing audio", 3, 8) in parsed
    assert parsed[-1] == ("Synthesizing audio", 8, 8)


def test_other_stderr_text_is_not_a_progress_line():
    assert progress_line("warning: something else") is None
    assert progress_line("[YuE2] Completed: 184.7s audio in 240.5s") is None
    assert progress_line("[YuE2] Running Loading acoustic model: elapsed 5.0s") == (
        "Loading acoustic model", None, None
    )


def test_stderr_progress_lines_become_progress_events_while_a_stage_runs(monkeypatch):
    import io
    import sys

    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    events = []

    with StderrProgress("synthesis", events.append):
        print("[YuE2] Starting Synthesizing audio: 0 steps | elapsed 0.0s", file=sys.stderr)
        sys.stderr.write("[YuE2] Running Synthesizing audio: 3/8 steps (38%) | elap")
        sys.stderr.write("sed 5.0s\nunrelated text\n")
    print("after the Stage", file=sys.stderr)

    assert sys.stderr is stream
    assert "unrelated text\nafter the Stage\n" in stream.getvalue()
    assert [(e.stage, e.signal, e.completed, e.total, e.kind) for e in events] == [
        ("synthesis", "stderr: Synthesizing audio", 0, None, "progress"),
        ("synthesis", "stderr: Synthesizing audio", 3, 8, "progress"),
    ]
