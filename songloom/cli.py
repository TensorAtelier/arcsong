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
        help="mlx-Yue weights (default: $SONGLOOM_MLX_MODELS or ~/projects/mlx-Yue/models)",
    )
    args = parser.parse_args(argv)

    from songloom.app import create_app

    kwargs = {"models": args.mlx_models} if args.engine == "mlx" else {"stage_seconds": 1.0}
    app = create_app(EngineSpec(ENGINES[args.engine], kwargs), args.data)
    uvicorn.run(app, host=args.host, port=args.port)
