"""The `draft-final` measurement driven through the SpikeEngine seam with a FakeEngine."""

import json
from functools import partial
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from spike import cli
from spike.fake import FakeEngine

STEM = "draft-final-fake-song-8bit-8-32"


def run_draft_final(tmp_path, *extra):
    return cli.main(
        ["draft-final", "--engine", "fake", "--results-dir", str(tmp_path / "results"),
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


def test_renders_a_draft_and_its_final_in_one_process_and_direct_32_in_another(
    tmp_path, monkeypatch
):
    use_fake(monkeypatch)

    assert run_draft_final(tmp_path) == 0

    data = ok_result(tmp_path)
    assert data["measurement"] == "draft-final"
    assert data["case"] == "song"
    assert data["params"] == {"precision": "8bit", "draft_steps": 8, "final_steps": 32}
    draft_process, direct_process = data["runs"]
    assert draft_process["process"] == "draft"
    assert direct_process["process"] == "direct"
    assert draft_process["pid"] != direct_process["pid"]
    assert draft_process["draft"]["steps"] == 8
    assert draft_process["final"]["steps"] == 32
    assert direct_process["direct"]["steps"] == 32
    for take in (draft_process["draft"], draft_process["final"], direct_process["direct"]):
        assert Path(take["audio_path"]).is_file()
        assert take["seconds"] > 0


def test_the_final_re_synthesizes_the_drafts_semantic_tokens_and_noise(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_draft_final(tmp_path)

    data = ok_result(tmp_path)
    assert data["draft_to_final"]["outcome"] == "ok"
    assert data["draft_to_final"]["final_method"] == "re-synthesis"
    draft, final = data["runs"][0]["draft"], data["runs"][0]["final"]
    assert final["method"] == "re-synthesis"
    assert Path(final["take_dir"]) != Path(draft["take_dir"])
    reused = data["draft_to_final"]["reused"]
    assert reused["Semantic tokens"]["equal"] is True
    assert reused["synthesis noise"]["equal"] is True


def test_records_the_final_re_render_time_against_the_direct_32_step_total(
    tmp_path, monkeypatch
):
    use_fake(
        monkeypatch,
        stage_seconds={"planning": 0.3, "semantic generation": 0.3, "synthesis": 0.05},
        load_seconds=0.1,
        lazy_load_seconds={"nar_load_seconds": 0.25},
    )

    run_draft_final(tmp_path)

    data = ok_result(tmp_path)
    timing = data["timing"]
    draft_process, direct_process = data["runs"]
    assert timing["draft_seconds"] == draft_process["draft"]["seconds"]
    assert timing["final_seconds"] == draft_process["final"]["seconds"]
    assert timing["direct_seconds"] == direct_process["direct"]["seconds"]
    # Re-synthesis skips planning and semantic generation.
    assert timing["final_seconds"] < 0.3 < timing["direct_seconds"]
    assert timing["final_saving_seconds"] == pytest.approx(
        timing["direct_seconds"] - timing["final_seconds"]
    )
    assert timing["final_to_direct_ratio"] == pytest.approx(
        timing["final_seconds"] / timing["direct_seconds"]
    )
    assert timing["final_lazy_load_seconds"] == pytest.approx(0.25)
    assert timing["direct_model_load_seconds"] == pytest.approx(
        direct_process["load_seconds"] + 0.25
    )


def test_a_final_identical_to_direct_32_is_recorded_as_bit_identical(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_draft_final(tmp_path)

    comparison = ok_result(tmp_path)["final_vs_direct"]
    assert comparison["first_diverging_stage"] == "none"
    assert comparison["stages"]["synthesis"]["equal"] is True
    assert comparison["stages"]["synthesis"]["max_abs_difference"] == 0.0
    assert comparison["stages"]["decoding"]["bit_identical"] is True


def test_a_final_differing_from_direct_32_records_max_abs_diff_and_correlation(
    tmp_path, monkeypatch
):
    # The Final is its process's second Take, so its Latents vary; direct-32's do not.
    use_fake(monkeypatch, diverge_in="synthesis", diverge_between="takes")

    run_draft_final(tmp_path)

    comparison = ok_result(tmp_path)["final_vs_direct"]
    assert comparison["first_diverging_stage"] == "synthesis"
    assert comparison["stages"]["synthesis"]["max_abs_difference"] == pytest.approx(0.5)
    audio = comparison["stages"]["decoding"]
    assert audio["bit_identical"] is False
    assert audio["max_abs_difference"] > 0
    assert audio["correlation"] < 1.0


def test_an_engine_that_cannot_take_semantic_tokens_back_records_unsupported_and_the_fallback(
    tmp_path, monkeypatch
):
    # Like audio.cpp: its own noise from the seed is hidden, so keeping a Draft's noise means
    # probing for the Semantic token count and supplying noise the harness wrote.
    use_fake(
        monkeypatch,
        fail_in="render_final",
        failure="unsupported",
        own_noise_hidden=True,
        noise_probe_seconds=0.2,
    )

    run_draft_final(tmp_path)

    data = result(tmp_path)
    assert data["outcome"] == "unsupported"
    assert "Unsupported" in data["error"]
    draft_to_final = data["draft_to_final"]
    assert draft_to_final["outcome"] == "unsupported"
    assert "FakeEngine cannot run render_final" in draft_to_final["reason"]
    assert draft_to_final["final_method"] == "full re-run"
    draft, final = data["runs"][0]["draft"], data["runs"][0]["final"]
    direct = data["runs"][1]["direct"]
    assert final["method"] == "full re-run"
    # The fallback re-runs the whole Take with the Draft's seed and saved noise file: the
    # noise is handed over, not compared with itself.
    assert final["noise_source"] == draft["noise_path"]
    assert draft_to_final["reused"] == {
        "synthesis noise": {"supplied_from_draft": True, "file": draft["noise_path"]}
    }
    timing = data["timing"]
    assert timing["fallback_seconds"] == final["seconds"]
    assert timing["final_seconds"] == final["seconds"]
    assert timing["direct_seconds"] == direct["seconds"]

    # The Final used the supplied noise and direct-32 the Engine's own, so they differ from
    # synthesis on; the results say so, and name direct-32 as the same-seed workaround.
    comparison = data["final_vs_direct"]
    assert comparison["first_diverging_stage"] == "synthesis"
    assert comparison["stages"]["decoding"]["bit_identical"] is False
    assert "noise" in comparison["note"]
    fallback = draft_to_final["fallback"]
    assert fallback["noise"] == "supplied from the Draft's saved noise file"
    assert fallback["seconds"] == final["seconds"]
    same_seed = fallback["same_seed_rerun"]
    assert same_seed["take"] == "direct"
    assert same_seed["seconds"] == direct["seconds"]
    assert "same-seed" in same_seed["note"]


def test_the_draft_time_excludes_the_noise_probe(tmp_path, monkeypatch):
    use_fake(
        monkeypatch,
        own_noise_hidden=True,
        noise_probe_seconds=0.4,
        stage_seconds={"synthesis": 0.05},
    )

    run_draft_final(tmp_path)

    data = ok_result(tmp_path)
    draft = data["runs"][0]["draft"]
    probe = draft["details"]["noise_probe_seconds"]
    assert probe >= 0.4
    timing = data["timing"]
    assert timing["noise_probe_seconds"] == probe
    assert timing["draft_seconds"] == pytest.approx(draft["seconds"] - probe)
    assert timing["draft_seconds"] < 0.4
    assert "noise_probe_seconds" in timing["notes"]


def test_an_engine_that_exports_its_noise_needs_no_probe(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_draft_final(tmp_path)

    timing = ok_result(tmp_path)["timing"]
    assert "noise_probe_seconds" not in timing
    assert "notes" not in timing


def test_resummarize_recomputes_the_summary_from_recorded_runs_without_running(
    tmp_path, monkeypatch
):
    use_fake(monkeypatch)
    run_draft_final(tmp_path)
    path = tmp_path / "results" / f"{STEM}.json"
    data = json.loads(path.read_text())
    data["runs"][0]["draft"]["seconds"] = 123.0
    del data["timing"]
    path.write_text(json.dumps(data))
    use_fake(monkeypatch, fail_in="load")  # any Engine run would now fail

    assert run_draft_final(tmp_path, "--resummarize") == 0

    redone = ok_result(tmp_path)
    assert redone["timing"]["draft_seconds"] == 123.0
    assert redone["runs"] == data["runs"]
    assert redone["started_at"] == data["started_at"]
    assert redone["env"] == data["env"]
    assert "resummarized_at" in redone


def test_resummarize_without_results_is_an_error(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    assert run_draft_final(tmp_path, "--resummarize") == 1


def test_the_draft_and_final_are_copied_as_a_listening_pair(tmp_path, monkeypatch):
    use_fake(monkeypatch)

    run_draft_final(tmp_path)

    data = ok_result(tmp_path)
    pair = data["listening_pair"]
    draft, final = Path(pair["draft"]), Path(pair["final"])
    assert draft.parent == final.parent == tmp_path / "listen" / STEM
    assert (draft.name, final.name) == ("draft-8.flac", "final-32.flac")
    source = sf.read(data["runs"][0]["final"]["audio_path"], dtype="int16")[0]
    assert np.array_equal(sf.read(final, dtype="int16")[0], source)
