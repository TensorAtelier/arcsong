"""The `cancel` measurement driven through the SpikeEngine seam with a FakeEngine."""

import json
from functools import partial
from pathlib import Path

import pytest

from spike import cli
from spike.engine import STAGES
from spike.fake import FakeEngine

SLACK = 0.15


def run_cancel(tmp_path, *extra):
    return cli.main(
        ["cancel", "--engine", "fake", "--results-dir", str(tmp_path / "results"),
         "--runs-dir", str(tmp_path / "runs"), "--cancel-after", "0.1", *extra]
    )  # fmt: skip


def use_fake(monkeypatch, **options):
    options.setdefault("stage_seconds", 0.4)
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))


def result_for(tmp_path, stage: str, case: str) -> dict:
    path = tmp_path / "results" / f"cancel-fake-{case}-8bit-8-{stage.replace(' ', '_')}-0.1.json"
    return json.loads(path.read_text())


def only_run(tmp_path, stage: str, case: str) -> dict:
    result = result_for(tmp_path, stage, case)
    assert result["outcome"] == "ok", result.get("error")
    [run] = result["runs"]
    return run


def test_writes_one_result_per_stage_using_song_where_clip_is_too_fast(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.4)

    assert run_cancel(tmp_path) == 0

    names = sorted(p.name for p in (tmp_path / "results").glob("*.json"))
    assert names == [
        "cancel-fake-clip-8bit-8-semantic_generation-0.1.json",
        "cancel-fake-clip-8bit-8-synthesis-0.1.json",
        "cancel-fake-song-8bit-8-decoding-0.1.json",
        "cancel-fake-song-8bit-8-planning-0.1.json",
    ]
    for stage, case in [("planning", "song"), ("semantic generation", "clip"),
                        ("synthesis", "clip"), ("decoding", "song")]:  # fmt: skip
        result = result_for(tmp_path, stage, case)
        assert result["measurement"] == "cancel"
        assert result["case"] == case
        assert result["params"] == {
            "precision": "8bit",
            "steps": 8,
            "stage": stage,
            "cancel_after_seconds": 0.1,
        }
        [run] = result["runs"]
        assert run["stage"] == stage
        assert run["stage_at_request"] == stage


def test_latency_runs_from_the_cancel_request_until_control_returns(tmp_path, monkeypatch):
    # Synthesis only looks at the cancel flag every 0.4 s; other Stages every 10 ms.
    use_fake(monkeypatch, stage_seconds=1.0, cancel_check_seconds={"synthesis": 0.4})

    run_cancel(tmp_path, "--stages", "synthesis", "decoding")

    slow = only_run(tmp_path, "synthesis", "clip")
    # Checks at 0, 0.4 s into synthesis; the request at 0.1 s waits for the second one.
    assert slow["cancel_latency_seconds"] == pytest.approx(0.3, abs=SLACK)
    assert slow["cancel_requested_seconds"] - slow["stage_entered_seconds"] == pytest.approx(
        0.1, abs=SLACK / 2
    )
    assert slow["cancelled_by"] == "InterruptedError"
    fast = only_run(tmp_path, "decoding", "song")
    assert 0 <= fast["cancel_latency_seconds"] < 0.05 + SLACK / 2
    assert fast["stage_at_request"] == "decoding"


def test_reuse_after_cancel_runs_a_full_clip_in_the_same_process(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_cancel(tmp_path, "--stages", "planning")

    reuse = only_run(tmp_path, "planning", "song")["reuse"]
    assert reuse["case"] == "clip"
    assert reuse["outcome"] == "ok"
    assert reuse["reloaded"] is False
    assert reuse["attempts"] == [{"reloaded": False, "outcome": "ok"}]
    assert reuse["audio_seconds"] == pytest.approx(0.5)
    assert reuse["run_seconds"] >= 4 * 0.4
    assert "audio.wav" in {f["path"] for f in reuse["files"]}


def test_reuse_reloads_when_the_cancel_left_the_engine_unusable(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.3, load_seconds=0.2, unusable_after_cancel=True)

    run_cancel(tmp_path, "--stages", "synthesis")

    reuse = only_run(tmp_path, "synthesis", "clip")["reuse"]
    assert reuse["outcome"] == "ok"
    assert reuse["reloaded"] is True
    assert reuse["reload_seconds"] == pytest.approx(0.2, abs=SLACK / 2)
    [first, second] = reuse["attempts"]
    assert first["reloaded"] is False
    assert first["outcome"] == "failed"
    assert "unusable" in first["error"]
    assert second == {"reloaded": True, "outcome": "ok"}


def test_reuse_that_fails_even_after_reload_is_recorded(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.3, fail_in="run_after_cancel")

    run_cancel(tmp_path, "--stages", "synthesis")

    reuse = only_run(tmp_path, "synthesis", "clip")["reuse"]
    assert reuse["outcome"] == "failed"
    assert reuse["reloaded"] is True
    assert [a["outcome"] for a in reuse["attempts"]] == ["failed", "failed"]


def test_leftover_files_of_the_cancelled_take_are_recorded(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.3)

    run_cancel(tmp_path, "--stages", "synthesis")

    run = only_run(tmp_path, "synthesis", "clip")
    take = Path(run["take_dir"])
    on_disk = {str(p.relative_to(take)): p.stat().st_size for p in take.rglob("*") if p.is_file()}
    assert {f["path"]: f["bytes"] for f in run["leftover_files"]} == on_disk
    assert set(on_disk) == {"score.abc", "semantic.bin"}
    assert run["leftover_looks_complete"] is False


def test_a_partial_audio_file_left_behind_looks_like_a_complete_take(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.3, audio_written_at_decoding_start=True)

    run_cancel(tmp_path, "--stages", "decoding")

    run = only_run(tmp_path, "decoding", "song")
    assert "audio.wav" in {f["path"] for f in run["leftover_files"]}
    assert run["leftover_looks_complete"] is True


def test_a_take_that_finishes_before_the_cancel_request_is_a_failed_measurement(
    tmp_path, monkeypatch
):
    use_fake(monkeypatch, stage_seconds={s: 0.05 for s in STAGES})

    assert run_cancel(tmp_path, "--stages", "decoding") == 0

    result = result_for(tmp_path, "decoding", "song")
    assert result["outcome"] == "failed"
    assert "finished before cancel was requested" in result["error"]


def test_rerun_skips_stages_whose_results_exist(tmp_path, monkeypatch, capsys):
    use_fake(monkeypatch, stage_seconds=0.3)
    run_cancel(tmp_path, "--stages", "synthesis")
    capsys.readouterr()

    run_cancel(tmp_path, "--stages", "synthesis")

    assert "skip cancel-fake-clip-8bit-8-synthesis-0.1" in capsys.readouterr().out


def test_a_non_default_cancel_delay_is_part_of_the_case(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.3)

    run_cancel(tmp_path, "--stages", "synthesis")  # --cancel-after 0.1

    [path] = (tmp_path / "results").glob("*.json")
    assert path.name == "cancel-fake-clip-8bit-8-synthesis-0.1.json"
    result = json.loads(path.read_text())
    assert result["params"] == {
        "precision": "8bit",
        "steps": 8,
        "stage": "synthesis",
        "cancel_after_seconds": 0.1,
    }
    assert result["runs"][0]["cancel_after_seconds"] == 0.1
