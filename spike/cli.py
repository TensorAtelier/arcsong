"""`spike` command line: one subcommand per measurement."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from spike import audiocpp_setup
from spike.audiocpp_engine import AudioCppEngine
from spike.cases import load_case
from spike.fake import FakeEngine
from spike.measurements import cancel, doctor, timing
from spike.mlx_engine import DEFAULT_MODELS_DIR, MlxYueEngine
from spike.runner import DEFAULT_TIMEOUT_SECONDS, EngineFactory, run_case

SPIKE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = SPIKE_DIR / "results"
DEFAULT_RUNS_DIR = SPIKE_DIR / "runs"

ENGINES: dict[str, Callable[[argparse.Namespace], EngineFactory]] = {
    "mlx": lambda args: partial(MlxYueEngine, models_dir=args.mlx_models),
    "audiocpp": lambda args: partial(AudioCppEngine, models_dir=args.audiocpp_models),
    "fake": lambda args: partial(FakeEngine),
}


def _audiocpp_models_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--audiocpp-models",
        type=Path,
        default=Path(
            os.environ.get("SPIKE_AUDIOCPP_MODELS", audiocpp_setup.DEFAULT_MODELS_DIR)
        ).expanduser(),
        help="directory holding the audio.cpp GGUF model directory "
        "(env SPIKE_AUDIOCPP_MODELS; default %(default)s)",
    )


def _common_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--engine", choices=sorted(ENGINES), required=True)
    command.add_argument("--force", action="store_true", help="rerun even if results exist")
    command.add_argument(
        "--mlx-models",
        type=Path,
        default=Path(os.environ.get("SPIKE_MLX_MODELS", DEFAULT_MODELS_DIR)).expanduser(),
        help="mlx-Yue weights directory holding converted/ and vae/ "
        "(env SPIKE_MLX_MODELS; default %(default)s)",
    )
    _audiocpp_models_argument(command)
    command.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    command.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spike", description="M0 engine spike harness")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "setup",
        help="Download the pinned audio.cpp release and YuE2 GGUF weights, verifying sha256 "
        "(mlx-Yue is installed by uv sync and reuses existing weights)",
    )
    run.add_argument("--pins", type=Path, default=audiocpp_setup.PINS_PATH)
    run.add_argument("--vendor-dir", type=Path, default=audiocpp_setup.DEFAULT_VENDOR_DIR)
    _audiocpp_models_argument(run)

    run = commands.add_parser("doctor", help="Load an Engine and render the clip case")
    _common_arguments(run)
    run.add_argument("--precision", default="bf16")
    run.add_argument("--steps", type=int, default=32, help="Synthesis steps")

    run = commands.add_parser(
        "timing",
        help="Per-Stage time, load time, peak memory and artifact sizes for the song case",
    )
    _common_arguments(run)
    run.add_argument(
        "--precisions", nargs="+", help="default: every precision the Engine offers"
    )
    run.add_argument(
        "--steps", type=int, nargs="+", default=list(timing.STEPS), help="Synthesis steps"
    )
    run.add_argument("--runs", type=int, default=timing.RUNS, help="runs per case")
    run.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="seconds before a run is killed and recorded as failed (default %(default)g)",
    )

    run = commands.add_parser(
        "cancel",
        help="Per-Stage cancel latency, reuse after cancel and leftover files",
    )
    _common_arguments(run)
    run.add_argument("--precision", help="default: 8bit for mlx, q8_0 for audio.cpp")
    run.add_argument("--steps", type=int, default=cancel.STEPS, help="Synthesis steps")
    run.add_argument(
        "--stages",
        nargs="+",
        choices=list(cancel.STAGE_CASES),
        default=list(cancel.STAGE_CASES),
        metavar="STAGE",
        help="Stages to cancel in (default: all four)",
    )
    run.add_argument(
        "--cancel-after",
        type=float,
        default=cancel.CANCEL_AFTER_SECONDS,
        help="seconds a Stage runs before cancel is requested (default %(default)g)",
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="seconds before a run is killed and recorded as failed (default %(default)g)",
    )
    return parser


def _exit_on_termination() -> None:
    """Turn SIGTERM/SIGHUP into SystemExit so a running measurement child is cleaned up."""

    def handler(signum, frame):
        sys.exit(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGHUP):
        if signal.getsignal(signum) is not signal.SIG_IGN:  # e.g. keep nohup's ignored SIGHUP
            signal.signal(signum, handler)


def _setup(args: argparse.Namespace) -> int:
    try:
        done = audiocpp_setup.setup(
            audiocpp_setup.load_pins(args.pins),
            args.vendor_dir,
            args.audiocpp_models,
            fetch=audiocpp_setup.fetch_url,
        )
    except audiocpp_setup.ChecksumMismatch as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    fetched = ", ".join(done.downloaded) if done.downloaded else "nothing (all files in place)"
    print(f"audio.cpp CLI: {done.cli}\nYuE2 weights: {done.model_dir}\ndownloaded: {fetched}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "setup":
        return _setup(args)
    common = dict(
        engine_name=args.engine,
        engine_factory=ENGINES[args.engine](args),
        results_dir=args.results_dir,
        runs_dir=args.runs_dir,
        force=args.force,
    )
    if argv is None:
        _exit_on_termination()
    if args.command == "doctor":
        run_case(
            measurement=doctor.MEASUREMENT,
            measure=doctor.measure,
            case=doctor.CASE,
            request=load_case(doctor.CASE),
            params={"precision": args.precision, "steps": args.steps},
            **common,
        )
    elif args.command == "timing":
        request = load_case(timing.CASE)
        for precision in args.precisions or timing.PRECISIONS[args.engine]:
            for steps in args.steps:
                run_case(
                    measurement=timing.MEASUREMENT,
                    measure=timing.measure,
                    case=timing.CASE,
                    request=request,
                    params={"precision": precision, "steps": steps},
                    repeats=args.runs,
                    timeout=args.timeout,
                    **common,
                )
    elif args.command == "cancel":
        for stage in args.stages:
            case = cancel.STAGE_CASES[stage]
            run_case(
                measurement=cancel.MEASUREMENT,
                measure=cancel.measure,
                case=case,
                request=load_case(case),
                params=cancel.params(
                    args.precision or cancel.PRECISIONS[args.engine],
                    args.steps,
                    stage,
                    args.cancel_after,
                ),
                timeout=args.timeout,
                **common,
            )
    return 0

