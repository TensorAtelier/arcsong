"""The audio.cpp Engine driven through the harness, with a stand-in `audiocpp_cli`.

The stand-in replays a real captured `--log` and writes a short WAV, so these tests
exercise the subprocess, log streaming, results and kill paths without weights or GPU.
"""

import json
import os
import signal
import sys
import time
import wave
from functools import partial
from pathlib import Path

import pytest

from spike import cli
from spike.audiocpp_engine import AudioCppEngine, Cancelled
from spike.engine import STAGES
from spike.runner import run_case

FIXTURE_LOG = Path(__file__).parent / "fixtures" / "audiocpp_clip_given_score.log"

FAKE_CLI = """#!{python}
import json, os, sys, time, wave
argv = sys.argv[1:]
if argv == ["--version"]:
    print("audio.cpp 0.8.0\\ngit: 4af1432 2026-09-15\\nbackends: cpu,metal")
    sys.exit(0)
out = argv[argv.index("--out") + 1]
with open(os.environ["FAKE_CLI_RECORD"], "w") as record:
    json.dump({{"argv": argv, "pid": os.getpid()}}, record)
hang_once = os.environ.get("FAKE_CLI_HANG_ONCE")
if hang_once and not os.path.exists(hang_once):
    open(hang_once, "w").close()
if os.environ.get("FAKE_CLI_HANG") or (hang_once and os.path.getsize(hang_once) == 0):
    if hang_once:
        open(hang_once, "w").write("hung")
    print("[TIMING ts=0] yue2.plan_ms 1.0", flush=True)
    time.sleep(120)
block = bytearray(b"\\x01") * (int(os.environ.get("FAKE_CLI_ALLOCATE_MIB", "0")) * 2**20)
for entry in open({log!r}).read().splitlines():
    print(entry.split(" ", 1)[1], flush=True)
time.sleep(float(os.environ.get("FAKE_CLI_HOLD_SECONDS", "0")))
if os.environ.get("FAKE_CLI_FAIL"):
    print("ggml_metal: out of memory", flush=True)
    sys.exit(3)
with wave.open(out, "wb") as audio:
    audio.setnchannels(2); audio.setsampwidth(2); audio.setframerate(48000)
    audio.writeframes(bytes(48000 * 4))
print("audio_out=" + out)
"""


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    path = tmp_path / "bin" / "audiocpp_cli"
    path.parent.mkdir()
    path.write_text(FAKE_CLI.format(python=sys.executable, log=str(FIXTURE_LOG)))
    path.chmod(0o755)
    models = tmp_path / "models"
    for name in ("yue2-3b-q8_0.gguf", "yue2-3b-bf16.gguf", "yue2-vae-f16.gguf"):
        (models / "Yue2-3B-GGUF" / name).parent.mkdir(parents=True, exist_ok=True)
        (models / "Yue2-3B-GGUF" / name).write_bytes(b"GGUF")
    record = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_CLI_RECORD", str(record))
    factory = partial(AudioCppEngine, cli=path, models_dir=models)
    monkeypatch.setitem(cli.ENGINES, "audiocpp", lambda args: factory)
    return factory, record


def run_doctor(tmp_path, *extra):
    return cli.main(
        ["doctor", "--engine", "audiocpp", "--results-dir", str(tmp_path / "results"),
         "--runs-dir", str(tmp_path / "runs"), *extra]
    )  # fmt: skip


def only_result(tmp_path) -> dict:
    [path] = (tmp_path / "results").glob("*.json")
    return json.loads(path.read_text())


def option(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, value in enumerate(argv) if value == flag]


def test_doctor_drives_the_cli_with_the_clip_case_and_records_stages(tmp_path, fake_cli):
    _, record = fake_cli

    assert run_doctor(tmp_path, "--precision", "q8_0", "--steps", "8") == 0

    result = only_result(tmp_path)
    assert result["engine"] == "audiocpp"
    assert result["engine_version"] == "0.8.0"
    assert result["env"]["engine"] == {"name": "audio.cpp", "version": "0.8.0", "commit": "4af1432"}
    assert result["outcome"] == "ok", result.get("error")
    [run] = result["runs"]
    with wave.open(run["audio_path"]) as audio:
        assert audio.getnframes() == 48000
    assert run["audio_seconds"] == pytest.approx(1.0)
    assert [(e["stage"], e["kind"]) for e in run["stage_events"]] == [
        (stage, kind) for stage in STAGES for kind in ("start", "end")
    ]
    names = {Path(f["path"]).name for f in run["files"]}
    assert {"audio.wav", "score.abc", "audiocpp.log"} <= names

    clip = json.loads((Path(cli.__file__).parent / "cases" / "clip.json").read_text())
    argv = json.loads(record.read_text())["argv"]
    assert option(argv, "--lyrics") == [clip["lyrics"]]
    assert option(argv, "--seed") == [str(clip["seed"])]
    requested = option(argv, "--request-option")
    assert f"style={clip['style']}" in requested
    assert "cot=full" in requested
    assert "num_inference_steps=8" in requested
    assert "semantic_max_tokens=400" in requested
    [abc_file] = [r.split("=", 1)[1] for r in requested if r.startswith("abc_file=")]
    assert Path(abc_file).read_text() == clip["abc"]
    assert "yue2.model_gguf=yue2-3b-q8_0.gguf" in option(argv, "--session-option")
    assert "--log" in argv


def test_bf16_selects_the_bf16_main_model(tmp_path, fake_cli):
    factory, record = fake_cli
    engine = factory()
    engine.load("bf16")

    engine.run({"style": "s", "lyrics": "l", "cot": "full", "seed": 1}, 32, tmp_path / "take")

    argv = json.loads(record.read_text())["argv"]
    assert "yue2.model_gguf=yue2-3b-bf16.gguf" in option(argv, "--session-option")


def measure_operation(operation, engine, request, params, run_dir):
    engine.load(params["precision"])
    calls = {
        "plan": lambda: engine.plan(request),
        "generate_semantic": lambda: engine.generate_semantic(request),
        "synthesize": lambda: engine.synthesize([1, 2, 3], params["steps"]),
        "decode": lambda: engine.decode([0.0]),
    }
    calls[operation]()
    return {}


@pytest.mark.parametrize("operation", ["plan", "generate_semantic", "synthesize", "decode"])
def test_stage_operations_are_recorded_as_unsupported(tmp_path, fake_cli, operation):
    factory, _ = fake_cli

    path = run_case(
        measurement="stage-op",
        measure=partial(measure_operation, operation),
        engine_name="audiocpp",
        engine_factory=factory,
        case="clip",
        request={"style": "s", "lyrics": "l", "cot": "full", "seed": 1},
        params={"precision": "q8_0", "steps": 8},
        results_dir=tmp_path / "results",
        runs_dir=tmp_path / "runs",
        log=lambda message: None,
    )

    result = json.loads(path.read_text())
    assert result["outcome"] == "unsupported"
    assert "Unsupported" in result["error"]
    assert "audio.cpp" in result["error"]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_for_record(record: Path) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if record.exists() and record.read_text():
            return json.loads(record.read_text())
        time.sleep(0.05)
    raise AssertionError("fake CLI never started")


def test_cancel_kills_the_cli_process(tmp_path, fake_cli, monkeypatch):
    factory, record = fake_cli
    monkeypatch.setenv("FAKE_CLI_HANG", "1")
    engine = factory()
    engine.load("q8_0")
    requested = []

    def cancelled() -> bool:
        if record.exists() and record.read_text():
            requested.append(time.monotonic())
            return True
        return False

    with pytest.raises(Cancelled):
        engine.run(
            {"style": "s", "lyrics": "l", "seed": 1}, 8, tmp_path / "take", cancelled=cancelled
        )

    assert time.monotonic() - requested[0] < 2
    assert not alive(json.loads(record.read_text())["pid"])


def test_cancel_records_kill_to_exit_latency_and_announces_the_stage(
    tmp_path, fake_cli, monkeypatch
):
    factory, record = fake_cli
    monkeypatch.setenv("FAKE_CLI_HANG", "1")
    engine = factory()
    engine.load("q8_0")
    events = []

    with pytest.raises(Cancelled) as raised:
        engine.run(
            {"style": "s", "lyrics": "l", "seed": 1},
            8,
            tmp_path / "take",
            cancelled=lambda: bool(events),
            on_event=events.append,
        )

    assert 0 < raised.value.kill_to_exit_seconds < 2
    assert [(e.stage, e.kind) for e in events] == [("planning", "enter")]


def test_cancel_measurement_runs_against_the_cli(tmp_path, fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_HANG_ONCE", str(tmp_path / "hung-once"))

    code = cli.main(
        ["cancel", "--engine", "audiocpp", "--stages", "planning", "--cancel-after", "0.2",
         "--results-dir", str(tmp_path / "results"), "--runs-dir", str(tmp_path / "runs")]
    )  # fmt: skip

    assert code == 0
    [path] = (tmp_path / "results").glob("*.json")
    assert path.name == "cancel-audiocpp-song-q8_0-8-planning-0.2.json"
    [run] = json.loads(path.read_text())["runs"]
    assert run["stage_at_request"] == "planning"
    assert run["cancelled_by"] == "Cancelled"
    assert 0 < run["kill_to_exit_seconds"] <= run["cancel_latency_seconds"] < 2
    assert "audiocpp.log" in {f["path"] for f in run["leftover_files"]}
    assert run["leftover_looks_complete"] is False
    reuse = run["reuse"]
    assert (reuse["outcome"], reuse["reloaded"]) == ("ok", False)
    assert {"session_load_seconds", "ar_load_seconds"} <= set(reuse["lazy_load_seconds"])


def test_a_failing_cli_is_recorded_with_its_log_tail(tmp_path, fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_FAIL", "1")

    assert run_doctor(tmp_path, "--precision", "q8_0") == 0

    result = only_result(tmp_path)
    assert result["outcome"] == "oom"
    assert "exited with code 3" in result["error"]
    assert "out of memory" in result["error"]


def test_the_cli_dies_with_a_timed_out_run(tmp_path, fake_cli, monkeypatch):
    factory, record = fake_cli
    monkeypatch.setenv("FAKE_CLI_HANG", "1")

    run_case(
        measurement="doctor",
        measure=cli.doctor.measure,
        engine_name="audiocpp",
        engine_factory=factory,
        case="clip",
        request={"style": "s", "lyrics": "l", "seed": 1},
        params={"precision": "q8_0", "steps": 8},
        results_dir=tmp_path / "results",
        runs_dir=tmp_path / "runs",
        timeout=3,
        log=lambda message: None,
    )

    assert only_result(tmp_path)["outcome"] == "failed"
    pid = wait_for_record(record)["pid"]
    deadline = time.monotonic() + 5
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if alive(pid):
        os.kill(pid, signal.SIGKILL)
        pytest.fail("audiocpp_cli outlived its killed run")


def run_timing(tmp_path, engine, *extra):
    return cli.main(
        ["timing", "--engine", engine, "--results-dir", str(tmp_path / "results"),
         "--runs-dir", str(tmp_path / "runs"), *extra]
    )  # fmt: skip


def test_timing_runs_the_song_case_at_bf16_and_q8_0_by_default(tmp_path, fake_cli):
    assert run_timing(tmp_path, "audiocpp", "--runs", "1") == 0

    names = sorted(p.name for p in (tmp_path / "results").glob("*.json"))
    assert names == [
        "timing-audiocpp-song-bf16-32.json",
        "timing-audiocpp-song-bf16-8.json",
        "timing-audiocpp-song-q8_0-32.json",
        "timing-audiocpp-song-q8_0-8.json",
    ]
    for name in names:
        assert json.loads((tmp_path / "results" / name).read_text())["outcome"] == "ok"


def test_timing_results_match_the_other_engines_field_for_field(tmp_path, fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLI_ALLOCATE_MIB", "256")
    monkeypatch.setenv("FAKE_CLI_HOLD_SECONDS", "1")
    run_timing(tmp_path / "audiocpp", "audiocpp", "--precisions", "q8_0", "--steps", "32")
    run_timing(tmp_path / "fake", "fake", "--precisions", "8bit", "--steps", "32")

    [path] = (tmp_path / "audiocpp" / "results").glob("*.json")
    result = json.loads(path.read_text())
    [other] = (tmp_path / "fake" / "results").glob("*.json")
    reference = json.loads(other.read_text())
    assert result.keys() == reference.keys()
    assert [run["outcome"] for run in result["runs"]] == ["ok", "ok"], result.get("error")
    for run in result["runs"]:
        assert run.keys() == reference["runs"][0].keys()
        assert list(run["stage_seconds"]) == list(STAGES)
        assert {"session_load_seconds", "ar_load_seconds", "nar_load_seconds",
                "vae_load_seconds"} <= set(run["lazy_load_seconds"])  # fmt: skip
        assert run["model_load_seconds"] == pytest.approx(
            run["load_seconds"] + sum(run["lazy_load_seconds"].values())
        )
        files = {f["path"] for f in run["files"]}
        assert {"audio.wav", "audiocpp.log"} <= files
        # The CLI subprocess's footprint is measured, not only the Python wrapper's.
        assert run["peak_footprint_bytes"] > 256 * 2**20
