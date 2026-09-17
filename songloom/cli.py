"""`songloom serve`."""

from __future__ import annotations

import argparse

import uvicorn

from songloom.engine import EngineSpec

ENGINES = {
    "mlx": "songloom.mlx_engine:MlxYueEngine",
    "fake": "songloom.fake_engine:FakeEngine",
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="songloom")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the songloom web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8840)
    serve.add_argument("--data", help="Data directory (default: $SONGLOOM_DATA or user data dir)")
    serve.add_argument("--engine", choices=sorted(ENGINES), default="mlx")
    serve.add_argument(
        "--mlx-models",
        help="mlx-Yue weights (default: $SONGLOOM_MLX_MODELS or <data>/models)",
    )
    args = parser.parse_args(argv)

    from songloom.app import create_app
    from songloom.config import data_dir
    from songloom.models import FakeModels, MlxYueModels, models_dir

    data = data_dir(args.data)
    if args.engine == "mlx":
        directory = models_dir(data, args.mlx_models)
        models = MlxYueModels(directory)
        kwargs = {"models": str(directory)}
    else:
        # Fake weights to download, so the Setup page can be tried without a GPU or network.
        models = FakeModels(
            data / "models", preinstalled=False, size=64 * 2**20, download_seconds=6
        )
        kwargs = {"stage_seconds": 1.0}
    app = create_app(EngineSpec(ENGINES[args.engine], kwargs), data, models=models)
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
