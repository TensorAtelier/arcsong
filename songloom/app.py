"""The FastAPI app: REST API for jobs and songs."""

from __future__ import annotations

import asyncio
import json
import queue
import random
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from songloom.config import data_dir
from songloom.db import Store
from songloom.engine import EngineSpec
from songloom.runner import JobRunner

STATIC_DIR = Path(__file__).parent / "static"
# Browsers reject the `audio/x-flac` that mimetypes guesses for .flac (Chrome plays audio/flac).
AUDIO_TYPES = {".flac": "audio/flac", ".wav": "audio/wav"}


class SongRequest(BaseModel):
    style: str = Field(min_length=1)
    lyrics: str = ""
    mode: Literal["full", "melody", "off"] = "full"
    seed: int | None = Field(default=None, ge=0, lt=2**31)
    precision: Literal["8bit", "bf16"] = "8bit"
    steps: Literal[8, 32] = 32


def create_app(
    spec: EngineSpec,
    data: str | Path | None = None,
    cancel_grace: float | None = None,
    load_retry: float | None = None,
) -> FastAPI:
    root = data_dir(data)
    songs_dir = root / "songs"
    songs_dir.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(root / "songloom.db")
        options = {"cancel_grace": cancel_grace, "load_retry": load_retry}
        kwargs = {k: v for k, v in options.items() if v is not None}
        runner = JobRunner(store, songs_dir, spec, **kwargs)
        app.state.store, app.state.runner = store, runner
        runner.start()
        try:
            yield
        finally:
            app.state.shutting_down.set()
            runner.stop()
            store.close()

    app = FastAPI(title="songloom", lifespan=lifespan)
    # Set when the server starts shutting down, so open event streams end instead of keeping
    # the server alive (uvicorn waits for open connections before running lifespan shutdown).
    app.state.shutting_down = threading.Event()

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
                while not (await request.is_disconnected() or app.state.shutting_down.is_set()):
                    try:
                        message = await asyncio.to_thread(subscription.get, True, 1.0)
                    except queue.Empty:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(message)}\n\n"
            finally:
                broadcaster.unsubscribe(subscription)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/songs")
    def list_songs():
        return [_with_size(song) for song in app.state.store.list_songs()]

    @app.get("/api/library")
    def library():
        songs = app.state.store.list_songs()
        disk = shutil.disk_usage(root)
        return {
            "songs": len(songs),
            "bytes_used": sum(_directory_bytes(Path(s["dir"])) for s in songs),
            "bytes_free": disk.free,
        }

    @app.delete("/api/songs/{song_id}")
    def delete_song(song_id: int):
        song = app.state.runner.delete_song(song_id)
        if song is None:
            raise HTTPException(404, "no such song")
        return {"deleted": song_id, "job_id": song["job_id"]}

    @app.get("/api/songs/{song_id}/audio")
    def song_audio(song_id: int):
        song = app.state.store.get_song(song_id)
        if song is None or not Path(song["audio_path"]).exists():
            raise HTTPException(404, "no such song")
        path = Path(song["audio_path"])
        media_type = AUDIO_TYPES.get(path.suffix, "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    # The built web app (web/ -> songloom/static); mounted last so /api routes win.
    if (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")

    return app


def _directory_bytes(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())


def _with_size(song: dict) -> dict:
    return {**song, "bytes": _directory_bytes(Path(song["dir"]))}
