"""The FastAPI app: REST API for jobs and songs."""

from __future__ import annotations

import asyncio
import functools
import io
import json
import queue
import random
import re
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import soundfile
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from songloom.config import data_dir
from songloom.db import Store
from songloom.engine import EngineSpec
from songloom.models import FakeModels, Models
from songloom.runner import JobRunner
from songloom.setup import Setup

STATIC_DIR = Path(__file__).parent / "static"
# The vendored piano the Score view plays, inside the package so a clone or a wheel has it
# and nothing is fetched from a CDN (THIRD_PARTY_NOTICES.md).
SOUNDFONT_DIR = Path(__file__).parent / "soundfont"
# Browsers reject the `audio/x-flac` that mimetypes guesses for .flac (Chrome plays audio/flac).
AUDIO_TYPES = {".flac": "audio/flac", ".wav": "audio/wav"}


SEED_LIMIT = 2**31
MAX_VARIATIONS = 8


class SongRequest(BaseModel):
    style: str = Field(min_length=1)
    lyrics: str = ""
    mode: Literal["full", "melody", "off"] = "full"
    seed: int | None = Field(default=None, ge=0, lt=SEED_LIMIT)
    precision: Literal["8bit", "bf16"] = "8bit"
    steps: Literal[8, 32] = 32
    # An edited Score to render instead of writing one; upstream needs a planning mode for it.
    abc: str | None = None

    @model_validator(mode="after")
    def _score_needs_a_planning_mode(self):
        if self.abc is not None and self.mode == "off":
            raise ValueError("a Score needs planning mode full or melody, not off")
        if self.abc is not None and not self.abc.strip():
            raise ValueError("the Score is empty")
        return self


class ScoreRequest(BaseModel):
    """A Score-only run: the same Song request, but only the planning Stage runs."""

    style: str = Field(min_length=1)
    lyrics: str = ""
    mode: Literal["full", "melody"] = "full"  # "off" writes no Score
    seed: int | None = Field(default=None, ge=0, lt=SEED_LIMIT)
    precision: Literal["8bit", "bf16"] = "8bit"
    # Planning ignores this; it is kept so rendering from the Score uses the chosen quality.
    steps: Literal[8, 32] = 32


class CheckScore(BaseModel):
    abc: str
    # The Score this one was edited from, for the difference report.
    original: str | None = None


class StripChords(BaseModel):
    abc: str


class GroupRequest(SongRequest):
    count: int = Field(ge=2, le=MAX_VARIATIONS)
    # Variations differ only in seed, and a supplied Score would make them identical.
    abc: None = None


class Star(BaseModel):
    starred: bool


def variation_seeds(seed: int | None, count: int) -> list[int]:
    """A given seed s gives s, s+1, …; no seed gives distinct random seeds."""
    if seed is None:
        return random.sample(range(SEED_LIMIT), count)
    return [(seed + i) % SEED_LIMIT for i in range(count)]


def create_app(
    spec: EngineSpec,
    data: str | Path | None = None,
    cancel_grace: float | None = None,
    load_retry: float | None = None,
    models: Models | None = None,
) -> FastAPI:
    """`models` are the weights the Engine needs; by default, fake weights that are already
    installed, so tests of other features never meet the Setup gate."""
    root = data_dir(data)
    songs_dir = root / "songs"
    songs_dir.mkdir(exist_ok=True)
    models = models or FakeModels(root / "models")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(root / "songloom.db")
        options = {"cancel_grace": cancel_grace, "load_retry": load_retry}
        kwargs = {k: v for k, v in options.items() if v is not None}
        runner = JobRunner(store, songs_dir, spec, **kwargs)
        setup = Setup(models, store, runner.publish_message, runner.next_seq)
        app.state.store, app.state.runner, app.state.setup = store, runner, setup
        setup.run_checks()
        runner.start()
        try:
            yield
        finally:
            app.state.shutting_down.set()
            setup.stop()
            runner.stop()
            store.close()

    app = FastAPI(title="songloom", lifespan=lifespan)
    # Set when the server starts shutting down, so open event streams end instead of keeping
    # the server alive (uvicorn waits for open connections before running lifespan shutdown).
    app.state.shutting_down = threading.Event()

    @app.post("/api/jobs", status_code=201)
    def create_job(body: SongRequest):
        if not app.state.setup.can_render():
            raise HTTPException(409, "The model weights are not installed yet; finish Setup first.")
        request = body.model_dump()
        if request["seed"] is None:
            request["seed"] = random.randrange(SEED_LIMIT)
        job = app.state.store.create_job(request)
        app.state.runner.publish(job["id"])
        app.state.runner.dispatch()
        return app.state.runner.job(job["id"])

    @app.post("/api/scores", status_code=201)
    def create_score(body: ScoreRequest):
        """Queue a Score-only run: planning alone, no audio."""
        if not app.state.setup.can_render():
            raise HTTPException(409, "The model weights are not installed yet; finish Setup first.")
        request = {**body.model_dump(), "abc": None}
        if request["seed"] is None:
            request["seed"] = random.randrange(SEED_LIMIT)
        job = app.state.store.create_job(request, kind="score")
        app.state.runner.publish(job["id"])
        app.state.runner.dispatch()
        return app.state.runner.job(job["id"])

    @app.get("/api/scores/{job_id}")
    def get_score(job_id: int):
        """A Score job with its ABC and, once written, its report."""
        job = app.state.runner.job(job_id)
        if job is None or job["kind"] != "score":
            raise HTTPException(404, "no such Score")
        return {"job": job, "abc": job["score"], "report": score_report(job["score"])}

    @app.post("/api/score/check")
    def check_score(body: CheckScore):
        """Validate a Score exactly as the Engine would, and say what an edit changed."""
        return score_check(body.abc, body.original)

    @app.post("/api/score/strip-chords")
    def strip_score_chords(body: StripChords):
        from lyra.music_tools.abc_tools import AbcError, strip_chords

        try:
            return {"abc": strip_chords(body.abc)}
        except AbcError as error:
            raise HTTPException(422, str(error)) from None

    @app.get("/api/songs/{song_id}/score")
    def song_score(song_id: int):
        """The Score saved with a Take, if its planning mode wrote one."""
        song = app.state.store.get_song(song_id)
        path = Path(song["dir"]) / "score.abc" if song else None
        if path is None or not path.exists():
            raise HTTPException(404, "this song has no Score")
        abc = path.read_text()
        job = app.state.store.get_job(song["job_id"])
        request = job["request"] if job else song["request"]
        return {"song_id": song_id, "abc": abc, "report": score_report(abc), "request": request}

    @app.post("/api/groups", status_code=201)
    def create_group(body: GroupRequest):
        """Queue Variations: `count` jobs of one Song request that differ only in seed."""
        if not app.state.setup.can_render():
            raise HTTPException(409, "The model weights are not installed yet; finish Setup first.")
        base = body.model_dump(exclude={"count"})
        requests = [{**base, "seed": seed} for seed in variation_seeds(body.seed, body.count)]
        jobs = app.state.store.create_group(requests)
        for job in jobs:
            app.state.runner.publish(job["id"])
        app.state.runner.dispatch()
        return [app.state.runner.job(job["id"]) for job in jobs]

    @app.get("/api/groups/{group_id}")
    def get_group(group_id: int):
        jobs = app.state.runner.group(group_id)
        if not jobs:
            raise HTTPException(404, "no such group")
        return jobs

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
        (created, started, Stage change, progress at most a few times a second, finished); a
        `deleted` message when a song is deleted; a `song` message with the song when its star
        changes; a `setup` message with the Setup snapshot when
        checks finish, the licence is acknowledged, or a download starts, progresses or ends."""
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

    @app.get("/api/setup")
    def get_setup():
        return app.state.setup.snapshot()

    @app.post("/api/setup/checks")
    def run_checks():
        app.state.setup.run_checks()
        return app.state.setup.snapshot()

    @app.post("/api/setup/licence")
    def acknowledge_licence():
        app.state.setup.acknowledge()
        return app.state.setup.snapshot()

    @app.post("/api/setup/download")
    def start_download():
        refused = app.state.setup.start_download()
        if refused:
            raise HTTPException(409, refused)
        return app.state.setup.snapshot()

    @app.post("/api/setup/download/cancel")
    def cancel_download():
        if not app.state.setup.cancel_download():
            raise HTTPException(409, "no download is running")
        return app.state.setup.snapshot()

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

    @app.post("/api/songs/{song_id}/finalize", status_code=201)
    def finalize_song(song_id: int):
        """Queue this Draft's Final: its saved Semantic tokens and noise at 32 Synthesis steps."""
        if not app.state.setup.can_render():
            raise HTTPException(409, "The model weights are not installed yet; finish Setup first.")
        job, refused = app.state.runner.finalize(song_id)
        if job is None:
            raise HTTPException(404 if refused == "no such song" else 409, refused)
        return job

    @app.put("/api/songs/{song_id}/star")
    def star_song(song_id: int, body: Star):
        song = app.state.runner.star_song(song_id, body.starred)
        if song is None:
            raise HTTPException(404, "no such song")
        return _with_size(song)

    @app.get("/api/songs/{song_id}/download")
    def download_song(song_id: int, format: Literal["flac", "wav"] = "flac"):
        song = app.state.store.get_song(song_id)
        path = Path(song["audio_path"]) if song else None
        if path is None or not path.exists():
            raise HTTPException(404, "no such song")
        job = app.state.store.get_job(song["job_id"])
        name = download_name(song_id, job["request"]["style"] if job else "", format)
        disposition = {"Content-Disposition": f'attachment; filename="{name}"'}
        if path.suffix == f".{format}":
            return FileResponse(path, media_type=AUDIO_TYPES[path.suffix], headers=disposition)
        # Keep the source bit depth (mlx-Yue saves 24-bit FLAC); read as int32 so no float
        # round trip or silent truncation happens on the way.
        subtype = soundfile.info(path).subtype
        if subtype not in ("PCM_16", "PCM_24"):
            subtype = "PCM_24"
        audio, rate = soundfile.read(path, always_2d=True, dtype="int32")
        buffer = io.BytesIO()
        soundfile.write(buffer, audio, rate, format=format.upper(), subtype=subtype)
        media_type = AUDIO_TYPES[f".{format}"]
        return Response(buffer.getvalue(), media_type=media_type, headers=disposition)

    @app.get("/api/songs/{song_id}/peaks")
    def song_peaks(song_id: int, buckets: int = Query(800, ge=16, le=4000)):
        """The waveform of a Take for drawing: per-bucket min and max of the mixed-down audio
        (-1..1) and its duration, so the page never decodes the whole file."""
        song = app.state.store.get_song(song_id)
        path = Path(song["audio_path"]) if song else None
        if path is None or not path.exists():
            raise HTTPException(404, "no such song")
        return waveform_peaks(str(path), path.stat().st_mtime_ns, buckets)

    @app.get("/api/songs/{song_id}/audio")
    def song_audio(song_id: int):
        song = app.state.store.get_song(song_id)
        if song is None or not Path(song["audio_path"]).exists():
            raise HTTPException(404, "no such song")
        path = Path(song["audio_path"])
        media_type = AUDIO_TYPES.get(path.suffix, "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    if SOUNDFONT_DIR.is_dir():
        app.mount("/soundfont", StaticFiles(directory=SOUNDFONT_DIR), name="soundfont")

    # The built web app (web/ -> songloom/static); mounted last so /api routes win.
    if (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")

    return app


def score_report(abc: str | None) -> dict | None:
    """mlx-Yue's own reading of a Score: bpm, notes per voice and nominal length."""
    if abc is None:
        return None
    from lyra.music_tools.abc_tools import AbcError, parse_abc

    try:
        return _summary(parse_abc(abc))
    except (AbcError, ValueError):
        return None


def _summary(score) -> dict:
    """What the page shows about a Score. `report()` carries every note as Fractions, which
    is more than a keystroke needs and not JSON, so summarize it here."""
    from lyra.music_tools.abc_tools import report

    full = report(score)
    return {
        "bpm": full["bpm"],
        "duration_seconds": full["nominal_duration_seconds"],
        "voices": {
            name: {
                "sounding_notes": voice["sounding_notes"],
                "measures": voice["measures"],
                "chords": len(voice["chords"]),
            }
            for name, voice in full["voices"].items()
        },
    }


def score_check(abc: str, original: str | None) -> dict:
    """What the page needs after every keystroke: is it valid, what is in it, what changed."""
    from lyra.music_tools.abc_tools import AbcError, compare, parse_abc

    try:
        score = parse_abc(abc)
    except AbcError as error:
        return {"ok": False, "error": str(error), "report": None, "diff": None}
    except ValueError as error:  # the parser's own guards, e.g. an unsupported key
        return {"ok": False, "error": str(error), "report": None, "diff": None}

    diff = None
    if original is not None:
        try:
            diff = compare(parse_abc(original), score, allow_tempo_change=True)
        except (AbcError, ValueError):
            diff = None
    return {"ok": True, "error": None, "report": _summary(score), "diff": diff}


@functools.lru_cache(maxsize=64)
def waveform_peaks(path: str, mtime_ns: int, buckets: int) -> dict:
    """`mtime_ns` is only part of the cache key, so a rewritten file is read again."""
    info = soundfile.info(path)
    frames = info.frames
    size = max(1, -(-frames // buckets))  # ceil, so at most `buckets` blocks
    mins, maxs = [], []
    for block in soundfile.blocks(path, blocksize=size, always_2d=True, dtype="float32"):
        mono = block.mean(axis=1)
        mins.append(round(float(mono.min()), 4))
        maxs.append(round(float(mono.max()), 4))
    return {"duration": frames / info.samplerate, "min": mins, "max": maxs}


def _directory_bytes(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())


def _with_size(song: dict) -> dict:
    return {**song, "bytes": _directory_bytes(Path(song["dir"]))}


def download_name(song_id: int, style: str, extension: str) -> str:
    """e.g. songloom-12-english-city-pop-groovy-bass.flac (ASCII, at most 6 style words)."""
    words = re.findall(r"[a-z0-9]+", style.lower())[:6]
    slug = "-".join(words)
    return f"songloom-{song_id}{'-' + slug if slug else ''}.{extension}"
