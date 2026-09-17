"""The `repro` measurement driven through the SpikeEngine seam with a FakeEngine."""

import json
from functools import partial
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from spike import cli
from spike.engine import STAGES
from spike.fake import DIVERGE_INDEX, FakeEngine
from spike.measurements import repro

STEM = "repro-fake-clip-8bit-32-planned"


def run_repro(tmp_path, *extra):
    return cli.main(
        ["repro", "--engine", "fake", "--results-dir", str(tmp_path / "results"),
         "--runs-dir", str(tmp_path / "runs"), "--listen-dir", str(tmp_path / "listen"), *extra]
    )  # fmt: skip


def use_fake(monkeypatch, **options):
    monkeypatch.setitem(cli.ENGINES, "fake", lambda args: partial(FakeEngine, **options))


def result(tmp_path) -> dict:
    return json.loads((tmp_path / "results" / f"{STEM}.json").read_text())


def ok_result(tmp_path) -> dict:
    data = result(tmp_path)
    assert data["outcome"] == "ok", data.get("error")
    return data


def test_runs_clip_without_its_score_twice_warm_and_once_fresh(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    assert run_repro(tmp_path) == 0

    data = ok_result(tmp_path)
    assert data["measurement"] == "repro"
    assert data["case"] == "clip"
    assert data["params"] == {"precision": "8bit", "steps": 32, "score": "planned"}
    warm, fresh = data["runs"]
    assert warm["process"] == "warm"
    assert fresh["process"] == "fresh"
    assert [take["take"] for take in warm["takes"]] == [1, 2]
    assert [take["take"] for take in fresh["takes"]] == [1]
    assert warm["pid"] != fresh["pid"]
    for take in [*warm["takes"], *fresh["takes"]]:
        assert take["seed"] == 831001
        assert Path(take["audio_path"]).is_file()
        # The Score was planned, not supplied: it differs from clip's own.
        score = Path(take["stage_outputs"]["planning"]).read_text()
        assert score != json.loads((cli.SPIKE_DIR / "cases" / "clip.json").read_text())["abc"]


def test_identical_outputs_report_no_diverging_stage(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_repro(tmp_path)

    comparisons = ok_result(tmp_path)["comparisons"]
    assert set(comparisons) == {"warm_vs_warm", "warm_vs_fresh"}
    for comparison in comparisons.values():
        assert comparison["first_diverging_stage"] == "none"
        stages = comparison["stages"]
        assert list(stages) == list(STAGES)
        assert stages["planning"] == {"output": "Score", "compared": True, "equal": True}
        assert stages["semantic generation"]["equal"] is True
        assert stages["semantic generation"]["first_differing_index"] is None
        assert stages["synthesis"]["equal"] is True
        assert stages["synthesis"]["max_abs_difference"] == 0.0
        assert stages["decoding"]["bit_identical"] is True
        assert stages["decoding"]["equal"] is True
        assert "max_abs_difference" not in stages["decoding"]


def test_a_divergence_in_the_second_warm_take_shows_only_in_warm_vs_warm(tmp_path, monkeypatch):
    use_fake(monkeypatch, diverge_in="synthesis", diverge_between="takes")

    run_repro(tmp_path)

    comparisons = ok_result(tmp_path)["comparisons"]
    warm = comparisons["warm_vs_warm"]
    assert warm["first_diverging_stage"] == "synthesis"
    assert warm["stages"]["planning"]["equal"] is True
    assert warm["stages"]["semantic generation"]["equal"] is True
    assert warm["stages"]["synthesis"]["equal"] is False
    assert warm["stages"]["synthesis"]["max_abs_difference"] == pytest.approx(0.5)
    audio = warm["stages"]["decoding"]
    assert audio["bit_identical"] is False
    assert audio["max_abs_difference"] > 0
    assert audio["correlation"] < 1.0
    assert comparisons["warm_vs_fresh"]["first_diverging_stage"] == "none"


@pytest.mark.parametrize("stage", STAGES)
def test_a_divergence_between_processes_names_its_stage_in_warm_vs_fresh(
    tmp_path, monkeypatch, stage
):
    use_fake(monkeypatch, diverge_in=stage, diverge_between="processes")

    run_repro(tmp_path)

    comparisons = ok_result(tmp_path)["comparisons"]
    assert comparisons["warm_vs_warm"]["first_diverging_stage"] == "none"
    fresh = comparisons["warm_vs_fresh"]
    assert fresh["first_diverging_stage"] == stage
    assert fresh["uncompared_stages_before"] == []
    stages = fresh["stages"]
    index = STAGES.index(stage)
    assert all(stages[s]["equal"] for s in STAGES[:index])
    assert not any(stages[s]["equal"] for s in STAGES[index:])
    if stage == "semantic generation":
        assert stages[stage]["first_differing_index"] == DIVERGE_INDEX


def test_one_same_seed_listening_pair_is_copied_and_recorded(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_repro(tmp_path)

    data = ok_result(tmp_path)
    pair = data["listening_pair"]
    assert pair["comparison"] == "warm_vs_fresh"
    warm, fresh = Path(pair["first"]), Path(pair["second"])
    assert warm.parent == fresh.parent == tmp_path / "listen" / STEM
    assert (warm.name, fresh.name) == ("warm-take-1.flac", "fresh-take-1.flac")
    source = sf.read(data["runs"][0]["takes"][0]["audio_path"], dtype="int16")[0]
    assert np.array_equal(sf.read(warm, dtype="int16")[0], source)
    assert sf.info(fresh).samplerate == sf.info(warm).samplerate


def test_the_listening_pair_is_the_one_that_differs(tmp_path, monkeypatch):
    use_fake(monkeypatch, diverge_in="decoding", diverge_between="takes")

    run_repro(tmp_path)

    pair = ok_result(tmp_path)["listening_pair"]
    assert pair["comparison"] == "warm_vs_warm"
    assert Path(pair["first"]).name == "warm-take-1.flac"
    assert Path(pair["second"]).name == "warm-take-2.flac"


def test_a_failed_take_is_the_outcome_and_nothing_is_compared(tmp_path, monkeypatch):
    use_fake(monkeypatch, fail_in="synthesize")

    assert run_repro(tmp_path) == 0

    data = result(tmp_path)
    assert data["outcome"] == "failed"
    assert "comparisons" not in data
    assert [run["outcome"] for run in data["runs"]] == ["failed", "failed"]


def test_existing_results_are_skipped_unless_forced(tmp_path, monkeypatch):
    use_fake(monkeypatch)
    run_repro(tmp_path)
    path = tmp_path / "results" / f"{STEM}.json"
    first = path.read_text()

    run_repro(tmp_path)
    assert path.read_text() == first

    run_repro(tmp_path, "--force")
    assert json.loads(path.read_text())["started_at"] != json.loads(first)["started_at"]


def test_a_warm_process_is_recorded_as_one_that_reuses_its_loaded_model(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_repro(tmp_path)

    data = ok_result(tmp_path)
    assert [run["takes_reuse_loaded_model"] for run in data["runs"]] == [True, True]
    warm = data["comparisons"]["warm_vs_warm"]
    assert warm["warm_process"] is True
    assert "note" not in warm


def test_takes_that_each_reload_the_model_are_not_called_a_warm_process(tmp_path, monkeypatch):
    # Like audio.cpp's CLI: every Take is a new process that loads the model again.
    use_fake(monkeypatch, takes_reuse_loaded_model=False)

    run_repro(tmp_path)

    data = ok_result(tmp_path)
    assert [run["takes_reuse_loaded_model"] for run in data["runs"]] == [False, False]
    for name in ("warm_vs_warm", "warm_vs_fresh"):
        comparison = data["comparisons"][name]
        assert comparison["warm_process"] is False
        assert "loads the model again" in comparison["note"]
    assert data["comparisons"]["warm_vs_warm"]["first_diverging_stage"] == "none"


# Numeric comparisons, on the files a Take leaves behind.


def write_npy(path: Path, array) -> Path:
    np.save(path, np.asarray(array))
    return path


def test_semantic_tokens_report_the_first_differing_index(tmp_path):
    a = write_npy(tmp_path / "a.npy", np.array([1, 2, 3, 4], dtype=np.int32))
    b = write_npy(tmp_path / "b.npy", np.array([1, 2, 9, 4], dtype=np.int32))
    short = write_npy(tmp_path / "c.npy", np.array([1, 2], dtype=np.int32))

    assert repro.compare_semantic(a, a) == {
        "equal": True, "first_differing_index": None, "lengths": [4, 4]
    }  # fmt: skip
    assert repro.compare_semantic(a, b)["first_differing_index"] == 2
    assert repro.compare_semantic(a, short) == {
        "equal": False, "first_differing_index": 2, "lengths": [4, 2]
    }  # fmt: skip


def test_latents_report_the_max_abs_difference(tmp_path):
    a = write_npy(tmp_path / "a.npy", np.zeros((3, 2), dtype=np.float32))
    b = write_npy(tmp_path / "b.npy", np.array([[0, 0], [0.25, -0.75], [0, 0]], np.float32))
    other_shape = write_npy(tmp_path / "c.npy", np.zeros((4, 2), dtype=np.float32))

    assert repro.compare_latents(a, a)["max_abs_difference"] == 0.0
    assert repro.compare_latents(a, a)["equal"] is True
    assert repro.compare_latents(a, b) == {
        "equal": False, "max_abs_difference": 0.75, "shapes": [[3, 2], [3, 2]]
    }  # fmt: skip
    assert repro.compare_latents(a, other_shape) == {
        "equal": False, "max_abs_difference": None, "shapes": [[3, 2], [4, 2]]
    }  # fmt: skip


def write_audio(path: Path, samples) -> Path:
    sf.write(path, np.asarray(samples, dtype=np.int16), 8000, subtype="PCM_16")
    return path


def test_audio_is_bit_identical_or_reports_max_abs_difference_and_correlation(tmp_path):
    wave = (np.sin(np.arange(800) / 5) * 16384).astype(np.int16)
    a = write_audio(tmp_path / "a.wav", wave)
    copy = write_audio(tmp_path / "copy.wav", wave)
    inverted = write_audio(tmp_path / "inverted.wav", -wave)
    shifted = write_audio(tmp_path / "shifted.flac", wave + 3276)

    assert repro.compare_audio(a, copy) == {
        "equal": True, "bit_identical": True, "sample_counts": [800, 800]
    }  # fmt: skip
    opposite = repro.compare_audio(a, inverted)
    assert opposite["bit_identical"] is False
    assert opposite["correlation"] == pytest.approx(-1.0)
    assert opposite["max_abs_difference"] == pytest.approx(2 * np.abs(wave).max() / 32768)
    offset = repro.compare_audio(a, shifted)
    assert offset["correlation"] == pytest.approx(1.0)
    assert offset["max_abs_difference"] == pytest.approx(3276 / 32768)


def test_audio_of_different_lengths_is_compared_over_the_shared_samples(tmp_path):
    wave = (np.sin(np.arange(800) / 5) * 16384).astype(np.int16)
    a = write_audio(tmp_path / "a.wav", wave)
    longer = write_audio(tmp_path / "b.wav", np.concatenate([wave, wave[:100]]))

    compared = repro.compare_audio(a, longer)
    assert compared["bit_identical"] is False
    assert compared["sample_counts"] == [800, 900]
    assert compared["max_abs_difference"] == 0.0
    assert compared["correlation"] == pytest.approx(1.0)


def test_only_exported_stage_outputs_are_compared(tmp_path):
    wave = (np.sin(np.arange(800) / 5) * 16384).astype(np.int16)
    take = {"audio_path": str(write_audio(tmp_path / "a.wav", wave)), "stage_outputs": {}}
    other = {"audio_path": str(write_audio(tmp_path / "b.wav", -wave)), "stage_outputs": {}}

    comparison = repro.compare_takes(take, other)

    assert comparison["stages"]["planning"] == {
        "output": "Score", "compared": False, "reason": "not exported by the Engine"
    }  # fmt: skip
    assert comparison["stages"]["synthesis"]["compared"] is False
    assert comparison["first_diverging_stage"] == "decoding"
    assert comparison["uncompared_stages_before"] == [
        "planning", "semantic generation", "synthesis"
    ]  # fmt: skip
    assert repro.compare_takes(take, take)["first_diverging_stage"] == "none"
