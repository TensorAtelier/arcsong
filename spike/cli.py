"""`spike` command line: one subcommand per measurement."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from functools import partial
from pathlib import Path

from spike.cases import load_case
from spike.fake import FakeEngine
from spike.measurements import doctor
from spike.mlx_engine import DEFAULT_MODELS_DIR, MlxYueEngine
from spike.runner import EngineFactory, run_case

SPIKE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = SPIKE_DIR / "results"
DEFAULT_RUNS_DIR = SPIKE_DIR / "runs"

ENGINES: dict[str, Callable[[argparse.Namespace], EngineFactory]] = {
    "mlx": lambda args: partial(MlxYueEngine, models_dir=args.mlx_models),
    "fake": lambda args: partial(FakeEngine),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spike", description="M0 engine spike harness")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("doctor", help="Load an Engine and render the clip case")
    run.add_argument("--engine", choices=sorted(ENGINES), required=True)
    run.add_argument("--force", action="store_true", help="rerun even if results exist")
    run.add_argument("--precision", default="bf16")
    run.add_argument("--steps", type=int, default=32, help="Synthesis steps")
    run.add_argument(
        "--mlx-models",
        type=Path,
        default=Path(os.environ.get("SPIKE_MLX_MODELS", DEFAULT_MODELS_DIR)).expanduser(),
        help="mlx-Yue weights directory holding converted/ and vae/ "
        "(env SPIKE_MLX_MODELS; default %(default)s)",
    )
    run.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        run_case(
            measurement=doctor.MEASUREMENT,
            measure=doctor.measure,
            engine_name=args.engine,
            engine_factory=ENGINES[args.engine](args),
            case=doctor.CASE,
            request=load_case(doctor.CASE),
            params={"precision": args.precision, "steps": args.steps},
            results_dir=args.results_dir,
            runs_dir=args.runs_dir,
            force=args.force,
        )
    return 0
