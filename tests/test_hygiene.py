"""The `hygiene` measurement driven through the SpikeEngine seam with a FakeEngine.

The FakeEngine's command line mimics mlx-Yue's: it refuses a non-empty output directory
and writes `<output>.resources.jsonl` / `.resources.json` next to it, refusing to start
if either exists. Its staged in-process path writes each Stage's output as it goes.
"""

import json
from functools import partial

from spike import cli
from spike.fake import FakeEngine

STAGE_SECONDS = {"planning": 0.05, "semantic generation": 0.05, "synthesis": 1.5, "decoding": 0.05}


def use_fake(monkeypatch, **options):
    options.setdefault("stage_seconds", STAGE_SECONDS)
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))


def run_hygiene(tmp_path):
    code = cli.main(
        ["hygiene", "--engine", "fake", "--kill-after", "0.3",
         "--results-dir", str(tmp_path / "results"), "--runs-dir", str(tmp_path / "runs")]
    )  # fmt: skip
    assert code == 0
    return json.loads((tmp_path / "results" / "hygiene-fake-clip-8bit-8-0.3.json").read_text())


def paths(files: list[dict]) -> list[str]:
    return [f["path"] for f in files]


def test_a_killed_command_line_take_leaves_resource_files_that_block_a_rerun_until_removed(
    tmp_path, monkeypatch
):
    use_fake(monkeypatch)

    result = run_hygiene(tmp_path)

    assert result["outcome"] == "ok", result.get("error")
    assert result["measurement"] == "hygiene"
    assert result["params"] == {"precision": "8bit", "steps": 8, "kill_after_seconds": 0.3}
    [run] = result["runs"]
    take = run["cli"]
    assert take["outcome"] == "ok"
    assert take["killed_in"] == "synthesis"
    assert "take.resources.jsonl" in paths(take["leftover_files"])
    assert take["resource_files_left"] == ["take.resources.jsonl"]

    blocked = take["rerun_without_cleanup"]
    assert blocked["outcome"] == "failed"
    assert "take.resources.jsonl" in blocked["error"]

    [cleaned] = take["reruns_after_cleanup"]
    assert cleaned["removed"] == ["take.resources.jsonl"]
    assert cleaned["outcome"] == "ok"
    assert cleaned["looks_complete"] is True
    assert cleaned["stale_files_kept"] == []
    assert take["cleanup_rule"] == "remove take.resources.jsonl"
    assert result["cleanup_rules"]["cli"] == "remove take.resources.jsonl"
    assert result["resource_files"]["cli"] == {
        "left_after_kill": ["take.resources.jsonl"],
        "written_by_completed_rerun": ["take.resources.json", "take.resources.jsonl"],
    }


def test_the_staged_api_path_leaves_no_resource_files_and_reruns_without_cleanup(
    tmp_path, monkeypatch
):
    use_fake(monkeypatch)

    result = run_hygiene(tmp_path)

    [run] = result["runs"]
    take = run["api"]
    assert take["outcome"] == "ok"
    assert take["killed_in"] == "synthesis"
    # The fake's staged path has written the Score and Semantic tokens by synthesis.
    assert paths(take["leftover_files"]) == ["take/score.abc", "take/semantic.npy"]
    assert take["resource_files_left"] == []
    assert take["rerun_without_cleanup"]["outcome"] == "ok"
    assert take["rerun_without_cleanup"]["looks_complete"] is True
    assert take["reruns_after_cleanup"] == []
    assert take["cleanup_rule"] == "none needed"
    assert result["cleanup_rules"]["api"] == "none needed"
    assert result["resource_files"]["api"] == {
        "left_after_kill": [],
        "written_by_completed_rerun": [],
    }


def test_an_engine_without_a_command_line_records_that_path_as_unsupported(tmp_path, monkeypatch):
    use_fake(monkeypatch, take_cli=False)

    result = run_hygiene(tmp_path)

    assert result["outcome"] == "ok", result.get("error")
    [run] = result["runs"]
    assert run["cli"]["outcome"] == "unsupported"
    assert run["api"]["outcome"] == "ok"
    assert result["cleanup_rules"] == {"api": "none needed", "cli": None}


def test_a_take_that_finishes_before_it_is_killed_fails_the_case(tmp_path, monkeypatch):
    use_fake(monkeypatch, stage_seconds=0.01)

    result = run_hygiene(tmp_path)

    assert result["outcome"] == "failed"
    [run] = result["runs"]
    assert run["api"]["outcome"] == "failed"
    assert "finished before it was killed" in run["api"]["error"]
    assert "finished before it was killed" in result["error"]
