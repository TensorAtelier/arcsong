"""The `doctor` measurement driven through the SpikeEngine seam with a FakeEngine."""

import json
import wave
from functools import partial
from pathlib import Path

import pytest

from spike import cli
from spike.fake import FakeEngine


def run_doctor(tmp_path, *extra):
    results_dir, runs_dir = tmp_path / "results", tmp_path / "runs"
    code = cli.main(
        [
            "doctor",
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


def only_result(results_dir: Path) -> dict:
    files = sorted(results_dir.glob("*.json"))
    assert len(files) == 1, files
    return json.loads(files[0].read_text())


def use_fake(monkeypatch, **options):
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))


def test_doctor_writes_a_results_file_matching_the_schema(tmp_path):
    code, results_dir, runs_dir = run_doctor(tmp_path)

    assert code == 0
    result = only_result(results_dir)
    assert result["measurement"] == "doctor"
    assert result["engine"] == "fake"
    assert result["engine_version"] == FakeEngine.VERSION
    assert result["case"] == "clip"
    assert result["params"] == {"precision": "bf16", "steps": 32}
    assert result["outcome"] == "ok"
    assert "error" not in result
    assert result["total_seconds"] > 0

    env = result["env"]
    assert env["machine"]["arch"]
    assert env["machine"]["memory_bytes"] > 0
    assert env["os"]["system"]
    assert env["engine"] == {"name": "fake", "version": FakeEngine.VERSION, "commit": None}
    assert isinstance(env["model_servers"], list)

    [run] = result["runs"]
    assert run["load_seconds"] >= 0
    assert run["run_seconds"] >= 0
    assert run["audio_seconds"] > 0
    audio = Path(run["audio_path"])
    assert audio.is_relative_to(runs_dir)
    with wave.open(str(audio)) as clip:
        assert clip.getnframes() > 0
    assert [e["stage"] for e in run["stage_events"] if e["kind"] == "start"] == [
        "planning",
        "semantic generation",
        "synthesis",
        "decoding",
    ]


def test_rerun_skips_a_case_whose_results_exist(tmp_path, capsys):
    run_doctor(tmp_path)
    [path] = (tmp_path / "results").glob("*.json")
    first = path.read_text()
    capsys.readouterr()

    code, _, _ = run_doctor(tmp_path)

    assert code == 0
    assert path.read_text() == first
    assert "skip" in capsys.readouterr().out.lower()


def test_force_reruns_a_case_whose_results_exist(tmp_path):
    run_doctor(tmp_path)
    [path] = (tmp_path / "results").glob("*.json")
    first = json.loads(path.read_text())

    code, results_dir, _ = run_doctor(tmp_path, "--force")

    assert code == 0
    second = only_result(results_dir)
    assert second["outcome"] == "ok"
    assert second["started_at"] != first["started_at"]


@pytest.mark.parametrize(
    ("failure", "outcome", "message"),
    [
        ("error", "failed", "FakeEngine failure"),
        ("unsupported", "unsupported", "FakeEngine cannot run"),
        ("memory", "oom", "FakeEngine out of memory"),
        ("killed", "oom", "SIGKILL"),
        ("abort", "failed", "SIGABRT"),
    ],
)
def test_engine_failure_is_recorded_as_the_outcome(
    tmp_path, monkeypatch, failure, outcome, message
):
    use_fake(monkeypatch, fail_in="run", failure=failure)

    code, results_dir, _ = run_doctor(tmp_path)

    assert code == 0
    result = only_result(results_dir)
    assert result["outcome"] == outcome
    assert message in result["error"]
    assert result["runs"] == []
    assert result["env"]["engine"]["name"] == "fake"


def test_failure_during_load_is_recorded(tmp_path, monkeypatch):
    use_fake(monkeypatch, fail_in="load", failure="error")

    code, results_dir, _ = run_doctor(tmp_path)

    assert code == 0
    assert only_result(results_dir)["outcome"] == "failed"
