"""The FastAPI app: REST API for jobs and songs."""

from __future__ import annotations

import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from songloom.config import data_dir
from songloom.db import Store
from songloom.engine import EngineSpec
from songloom.runner import JobRunner


class SongRequest(BaseModel):
    style: str = Field(min_length=1)
    lyrics: str = ""
    mode: Literal["full", "melody", "off"] = "full"
    seed: int | None = Field(default=None, ge=0, lt=2**31)
    precision: Literal["8bit", "bf16"] = "8bit"
    steps: Literal[8, 32] = 32


def create_app(spec: EngineSpec, data: str | Path | None = None) -> FastAPI:
    root = data_dir(data)
    songs_dir = root / "songs"
    songs_dir.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(root / "songloom.db")
        runner = JobRunner(store, songs_dir, spec)
        app.state.store, app.state.runner = store, runner
        runner.start()
        try:
            yield
        finally:
            runner.stop()
            store.close()

    app = FastAPI(title="songloom", lifespan=lifespan)

    @app.post("/api/jobs", status_code=201)
    def create_job(body: SongRequest):
        request = body.model_dump()
        if request["seed"] is None:
            request["seed"] = random.randrange(2**31)
        job = app.state.store.create_job(request)
        app.state.runner.dispatch()
        return job

    @app.get("/api/jobs")
    def list_jobs():
        return app.state.store.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int):
        job = app.state.store.get_job(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job

    @app.get("/api/songs/{song_id}/audio")
    def song_audio(song_id: int):
        song = app.state.store.get_song(song_id)
        if song is None or not Path(song["audio_path"]).exists():
            raise HTTPException(404, "no such song")
        return FileResponse(song["audio_path"])

    return app
