"""The `download` measurement driven through the SpikeEngine seam with a FakeEngine.

The FakeEngine's download mimics a Hugging Face `local_dir` snapshot: its repository
files (including `.gitattributes`) plus `.cache/huggingface/...` metadata, with a large
weight supplied locally. Its verification, like mlx-Yue's `verify_conversion`, rejects
any file in the converted directory it does not expect.
"""

import json
from functools import partial
from pathlib import Path

from spike import cli
from spike.fake import FakeEngine


def run_download(tmp_path, monkeypatch, **options):
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))
    code = cli.main(
        ["download", "--engine", "fake",
         "--results-dir", str(tmp_path / "results"), "--runs-dir", str(tmp_path / "runs")]
    )  # fmt: skip
    assert code == 0
    return json.loads((tmp_path / "results" / "download-fake-weights.json").read_text())


def test_records_the_files_downloaded_and_the_metadata_the_hub_adds(tmp_path, monkeypatch):
    result = run_download(tmp_path, monkeypatch)

    assert result["outcome"] == "ok", result.get("error")
    assert result["measurement"] == "download"
    [run] = result["runs"]
    assert run["downloaded"] == [
        "converted/.gitattributes",
        "converted/config.json",
        "vae/model.bin",
    ]
    assert [f["path"] for f in run["supplied_locally"]] == ["converted/weights.bin"]
    assert run["metadata_files"] == [
        "converted/.cache/huggingface/.gitignore",
        "converted/.cache/huggingface/download/.gitattributes.metadata",
        "converted/.cache/huggingface/download/config.json.metadata",
        "vae/.cache/huggingface/.gitignore",
        "vae/.cache/huggingface/download/model.bin.metadata",
    ]


def test_verification_fails_on_the_metadata_and_the_fix_is_shown_working(tmp_path, monkeypatch):
    result = run_download(tmp_path, monkeypatch)

    [run] = result["runs"]
    assert run["verification"]["outcome"] == "failed"
    assert ".cache" in run["verification"]["error"]
    first, second = run["fixes"]
    assert first["removed"] == ["converted/.cache", "vae/.cache"]
    assert first["verification"]["outcome"] == "failed"
    assert ".gitattributes" in first["verification"]["error"]
    assert second["removed"] == ["converted/.gitattributes"]
    assert second["verification"]["outcome"] == "ok"
    assert result["fix"] == {
        "works": True,
        "removed": ["converted/.cache", "vae/.cache", "converted/.gitattributes"],
        "steps": [first["fix"], second["fix"]],
    }


def test_downloading_again_after_the_fix_brings_the_metadata_back(tmp_path, monkeypatch):
    result = run_download(tmp_path, monkeypatch)

    [run] = result["runs"]
    again = run["after_redownload"]
    assert "converted/.cache/huggingface/download/config.json.metadata" in again["metadata_files"]
    assert again["verification"]["outcome"] == "failed"
    assert again["fixes"][-1]["verification"]["outcome"] == "ok"


def test_the_temporary_download_directory_is_deleted(tmp_path, monkeypatch):
    result = run_download(tmp_path, monkeypatch)

    [run] = result["runs"]
    assert run["temp_dir_deleted"] is True
    assert not Path(run["temp_dir"]).exists()


def test_without_metadata_verification_passes_and_no_fix_is_needed(tmp_path, monkeypatch):
    result = run_download(tmp_path, monkeypatch, download_metadata=False)

    [run] = result["runs"]
    # The fake's `.gitattributes` still fails verification without any metadata.
    assert run["metadata_files"] == []
    assert [step["removed"] for step in run["fixes"]] == [["converted/.gitattributes"]]
    assert result["fix"]["works"] is True
