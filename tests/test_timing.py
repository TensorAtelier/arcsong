"""The `timing` measurement driven through the SpikeEngine seam with a FakeEngine."""

import json
from functools import partial
from pathlib import Path

import pytest

from spike import cli
from spike.engine import STAGES
from spike.fake import FakeEngine

SCRIPTED = {"planning": 0.05, "semantic generation": 0.3, "synthesis": 0.15, "decoding": 0.1}
SLACK = 0.1


def run_timing(tmp_path, *extra):
    results_dir, runs_dir = tmp_path / "results", tmp_path / "runs"
    code = cli.main(
        [
            "timing",
            "--engine",
            "fake",
            "--results-dir",
            str(results_dir),
            "--runs-dir",
            str(runs_dir),
            *extra,
        ]
    )
    return code, results_dir, runs_dir


def use_fake(monkeypatch, **options):
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_full_matrix_writes_one_results_file_per_precision_and_steps_with_two_runs(tmp_path):
    code, results_dir, _ = run_timing(tmp_path)

    assert code == 0
    names = sorted(p.name for p in results_dir.glob("*.json"))
    assert names == [
        "timing-fake-song-8bit-32.json",
        "timing-fake-song-8bit-8.json",
        "timing-fake-song-bf16-32.json",
        "timing-fake-song-bf16-8.json",
    ]
    for name in names:
        result = load(results_dir / name)
        assert result["measurement"] == "timing"
        assert result["case"] == "song"
        assert result["outcome"] == "ok"
        assert len(result["runs"]) == 2
        assert all(run["outcome"] == "ok" for run in result["runs"])
    assert load(results_dir / "timing-fake-song-8bit-32.json")["params"] == {
        "precision": "8bit",
        "steps": 32,
    }


def test_each_run_aggregates_wall_time_per_stage_load_time_and_memory(tmp_path, monkeypatch):
    use_fake(
        monkeypatch,
        stage_seconds=SCRIPTED,
        load_seconds=0.2,
        lazy_load_seconds={"ar_load_seconds": 0.05, "nar_load_seconds": 0.05},
        peak_memory_bytes=123_456,
    )

    run_timing(tmp_path, "--precisions", "bf16", "--steps", "8")

    result = load(tmp_path / "results" / "timing-fake-song-bf16-8.json")
    assert [run["run"] for run in result["runs"]] == [1, 2]
    for run in result["runs"]:
        assert list(run["stage_seconds"]) == list(STAGES)
        for stage, seconds in SCRIPTED.items():
            assert seconds <= run["stage_seconds"][stage] < seconds + SLACK, stage
        assert sum(run["stage_seconds"].values()) <= run["run_seconds"]
        assert run["run_seconds"] < sum(SCRIPTED.values()) + SLACK
        assert 0.2 <= run["load_seconds"] < 0.2 + SLACK
        assert run["lazy_load_seconds"] == {"ar_load_seconds": 0.05, "nar_load_seconds": 0.05}
        assert run["model_load_seconds"] == pytest.approx(run["load_seconds"] + 0.1)
        assert run["total_seconds"] == pytest.approx(run["load_seconds"] + run["run_seconds"])
        assert run["engine_peak_memory_bytes"] == 123_456
        assert run["audio_seconds"] == pytest.approx(0.5)
        assert run["peak_footprint_bytes"] > 0
        assert run["footprint_samples"] >= 1


def test_each_run_records_the_size_of_every_file_the_take_writes(tmp_path):
    run_timing(tmp_path, "--precisions", "8bit", "--steps", "32", "--runs", "1")

    [run] = load(tmp_path / "results" / "timing-fake-song-8bit-32.json")["runs"]
    take = Path(run["take_dir"])
    on_disk = {
        str(p.relative_to(take)): p.stat().st_size for p in take.rglob("*") if p.is_file()
    }
    assert {f["path"]: f["bytes"] for f in run["files"]} == on_disk
    assert {"audio.wav", "score.abc", "semantic.bin", "extra/latents.bin"} <= set(on_disk)
    assert run["files_total_bytes"] == sum(on_disk.values())
    assert run["audio_bytes"] == on_disk["audio.wav"]


def test_a_failing_run_is_recorded_and_the_matrix_continues(tmp_path, monkeypatch):
    use_fake(monkeypatch, fail_in="synthesize", failure="memory")

    code, results_dir, _ = run_timing(tmp_path, "--precisions", "bf16", "--steps", "8", "32")

    assert code == 0
    for steps in (8, 32):
        result = load(results_dir / f"timing-fake-song-bf16-{steps}.json")
        assert result["outcome"] == "oom"
        assert "FakeEngine out of memory" in result["error"]
        assert [run["outcome"] for run in result["runs"]] == ["oom", "oom"]
        assert all("peak_footprint_bytes" in run for run in result["runs"])


def test_rerunning_the_matrix_skips_cases_whose_results_exist(tmp_path, capsys):
    run_timing(tmp_path, "--precisions", "bf16", "--steps", "8", "--runs", "1")
    existing = tmp_path / "results" / "timing-fake-song-bf16-8.json"
    first = existing.read_text()
    capsys.readouterr()

    run_timing(tmp_path, "--precisions", "bf16", "--steps", "8", "32", "--runs", "1")

    assert existing.read_text() == first
    assert (tmp_path / "results" / "timing-fake-song-bf16-32.json").exists()
    assert "skip timing-fake-song-bf16-8" in capsys.readouterr().out
