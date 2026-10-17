"""`arcsong serve`."""

from __future__ import annotations

import argparse
import os

import uvicorn

from arcsong.engine import EngineSpec

ENGINES = {
    "mlx": "arcsong.mlx_engine:MlxYueEngine",
    "fake": "arcsong.fake_engine:FakeEngine",
}

REQUIRE_AC_ENV = "ARCSONG_REQUIRE_AC"
TRUTHY = {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="arcsong")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the arcsong web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8840)
    serve.add_argument("--data", help="Data directory (default: $ARCSONG_DATA or user data dir)")
    serve.add_argument("--engine", choices=sorted(ENGINES), default="mlx")
    serve.add_argument(
        "--mlx-models",
        help="mlx-Yue weights (default: $ARCSONG_MLX_MODELS or <data>/models)",
    )
    serve.add_argument(
        "--require-ac",
        action="store_true",
        default=None,
        help=(
            "Refuse to render on battery, as mlx-Yue's guard does (default: "
            "$ARCSONG_REQUIRE_AC, else off: songs render on battery, more slowly)."
        ),
    )
    # Rendering on battery was opt-in until it became the default; old scripts still pass it.
    serve.add_argument("--allow-battery", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    require_ac = (
        args.require_ac
        if args.require_ac is not None
        else os.environ.get(REQUIRE_AC_ENV, "").strip().lower() in TRUTHY
    )
    allow_battery = not require_ac or args.allow_battery

    from arcsong.app import create_app
    from arcsong.config import data_dir
    from arcsong.models import FakeModels, MlxYueModels, TranscriptionModels, models_dir

    data = data_dir(args.data)
    if args.engine == "mlx":
        directory = models_dir(data, args.mlx_models)
        models = MlxYueModels(directory)
        covers = TranscriptionModels(directory)
        # Songs render on battery unless the user asks for mlx-Yue's AC guard.
        kwargs = {"models": str(directory), "require_ac": not allow_battery}
    else:
        # Fake weights to download, so the Setup page can be tried without a GPU or network.
        models = FakeModels(
            data / "models", preinstalled=False, size=64 * 2**20, download_seconds=6
        )
        covers = FakeModels(
            data / "covers-models", preinstalled=False, size=16 * 2**20, download_seconds=3
        )
        # Long enough to hear and compare Variations in the page.
        kwargs = {"stage_seconds": 1.0, "audio_seconds": 20.0}
    app = create_app(
        EngineSpec(ENGINES[args.engine], kwargs),
        data,
        models=models,
        covers=covers,
        allow_battery=allow_battery,
    )
    config = uvicorn.Config(app, host=args.host, port=args.port, timeout_graceful_shutdown=5)
    Server(config, app.state.shutting_down).run()


class Server(uvicorn.Server):
    """Tells the app it is shutting down the moment a stop signal arrives, so open event
    streams close and the server can exit (and stop its worker) even with a page open."""

    def __init__(self, config: uvicorn.Config, shutting_down):
        super().__init__(config)
        self.shutting_down = shutting_down

    def handle_exit(self, sig, frame) -> None:
        self.shutting_down.set()
        super().handle_exit(sig, frame)


if __name__ == "__main__":
    main()
