"""The FastAPI app: REST API for jobs and songs."""

from __future__ import annotations

import asyncio
import json
import queue
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
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


def create_app(
    spec: EngineSpec, data: str | Path | None = None, cancel_grace: float | None = None
) -> FastAPI:
    root = data_dir(data)
    songs_dir = root / "songs"
    songs_dir.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(root / "songloom.db")
        kwargs = {} if cancel_grace is None else {"cancel_grace": cancel_grace}
        runner = JobRunner(store, songs_dir, spec, **kwargs)
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
        app.state.runner.publish(job["id"])
        app.state.runner.dispatch()
        return app.state.runner.job(job["id"])

    @app.get("/api/jobs")
    def list_jobs():
        return app.state.runner.jobs()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int):
        job = app.state.runner.job(job_id)
        if job is None:
            raise HTTPException(404, "no such job")
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: int):
        if app.state.runner.job(job_id) is None:
            raise HTTPException(404, "no such job")
        if not app.state.runner.cancel(job_id):
            raise HTTPException(409, "job already finished")
        return app.state.runner.job(job_id)

    @app.get("/api/events")
    async def events(request: Request):
        """Server-sent events: a `job` message with the job's snapshot whenever a job changes
        (created, started, Stage change, progress at most a few times a second, finished)."""
        broadcaster = app.state.runner.broadcaster
        subscription = broadcaster.subscribe()

        async def stream():
            try:
                yield ": connected\n\n"
                while not await request.is_disconnected():
                    try:
                        message = await asyncio.to_thread(subscription.get, True, 1.0)
                    except queue.Empty:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(message)}\n\n"
            finally:
                broadcaster.unsubscribe(subscription)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/songs/{song_id}/audio")
    def song_audio(song_id: int):
        song = app.state.store.get_song(song_id)
        if song is None or not Path(song["audio_path"]).exists():
            raise HTTPException(404, "no such song")
        return FileResponse(song["audio_path"])

    return app
