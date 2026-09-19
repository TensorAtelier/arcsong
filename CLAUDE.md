# Arcsong

Local web UI for the YuE2 music model. Plan: `PLAN.md`. Prior art: `docs/prior-art.md`.

## App (`arcsong/`, `web/`)

- Run: `uv run arcsong serve` (127.0.0.1:8840, `--engine mlx|fake`, `--data DIR`), or `dev start arcsong`. Data (SQLite `arcsong.db` + `songs/<job id>/`) lives in `$ARCSONG_DATA`, else `~/Library/Application Support/arcsong`. mlx-Yue weights come from `--mlx-models`, `$ARCSONG_MLX_MODELS`, else `<data>/models` (the `dev` registration passes `--mlx-models ~/projects/mlx-Yue/models`).
- Shape: FastAPI (`app.py`) → `JobRunner` (`runner.py`, owns the queue, live progress, SSE broadcast, worker restarts) → one spawned worker process (`worker.py`) that owns the Engine (`mlx_engine.py`, or `fake_engine.py` for tests). Only the server writes the database. A song is indexed only after mlx-Yue's `save_artifacts` returns.
- Library: `GET /api/songs`, `GET /api/library` (usage), `GET /api/songs/{id}/download?format=flac|wav` (converted in memory, keeping bit depth), `DELETE /api/songs/{id}` (permanent: Take directory, song row and job row; broadcasts an SSE `deleted` message).
- Variations and Finals: `POST /api/groups` (a Song request + `count` 2–8, seeds count up from the given one or are random), `GET /api/groups/{id}`, `PUT /api/songs/{id}/star` (SSE `song` message), `POST /api/songs/{id}/finalize` (the Draft's request at 32 steps; one Final per Draft), `GET /api/songs/{id}/peaks?buckets=N` (waveform min/max, cached in memory). Schema v2: `jobs.group_id` (the group's first job id), `jobs.source_song_id` (a Final's Draft), `songs.starred`; migrations run in one transaction. The Engine's `finalize()` re-synthesizes a saved Take (mlx-Yue via `load_artifacts`); the worker job tuple carries the Draft's directory.
- Scores: `POST /api/scores` (planning alone, through the Engine's `plan_only()`; the request's `steps` is kept for rendering from the Score later), `GET /api/scores/{job_id}`, `GET /api/songs/{id}/score`, `POST /api/score/check` and `/api/score/strip-chords` (mlx-Yue's own `lyra.music_tools.abc_tools`, in the server process — pure text, no MLX). A Song request may carry an `abc`, which upstream turns into the plan, so planning is skipped. Schema v3: `jobs.kind` (`take` | `score`) and `jobs.score`.
- Covers: `POST /api/covers` (multipart: the recording plus style, lyrics and a rights confirmation) queues a `cover` job; the Engine's `transcribe()` runs mlx-Yue's SheetSage2 over it and stores the Score, whose ABC is the same native dialect a planned Score uses, so the Score view edits and renders it unchanged. Transcription exports (MIDI, LAB, `result.json`) go to `<data>/covers/<job id>/`; the upload lives in `<data>/uploads/` only while the job runs. Schema v4: `jobs.source_audio`.
- Setup (`setup.py` + `models.py`): `GET /api/setup` returns machine checks plus a `parts` list — `engine` (the song weights) and the optional `covers` (ffmpeg + SheetSage2 and MERT2, ~2.6 GiB) — each with its own weights state (from pinned file sizes), download, checks, `checked` and `usable`. `POST /api/setup/checks|licence`, `POST /api/setup/download/{part}` and `.../cancel`, SSE `setup` messages with a `seq`. One part downloads at a time; only `engine` gates rendering, and an optional part is not usable until its own checks have run. The weights download runs in its own spawned process at pinned revisions; the server polls bytes on disk. `POST /api/jobs` answers 409 until the weights are installed. `--engine fake` downloads 64 MB of fake weights so Setup can be tried without a GPU; `create_app` without `models=` uses preinstalled fake weights, so tests skip the gate.
- Create holds the song form and the Cover panel; the page has Create / Library / Setup views on `#/`, `#/library`, `#/setup`, Compare on `#/compare/<group id>` and the Score on `#/score/job/<id>` or `#/score/song/<id>` (abcjs notation, melody preview, ABC editor with live validation and a diff); it opens on Setup while not ready. `--engine fake` writes 20 s tones whose pitch depends on the seed.
- Web: Vite + React + TS in `web/`, built into `arcsong/static/` (committed, so running needs no Node). After editing `web/src`, run `cd web && npm run build` and commit the build.
- Released: [v0.1.0](https://github.com/TensorAtelier/arcsong/releases/tag/v0.1.0), installed with `uv tool install git+https://github.com/TensorAtelier/arcsong`. Cutting a release: `docs/release.md`. The wheel ships `arcsong` only (never `spike`, which stays in the repository); supported Pythons are 3.12–3.14; the README's samples and screenshots live in `docs/media/` with `.gitignore` exceptions.
- Verify: `uv run pytest -q`, `uv run ruff check .`, `cd web && npm run typecheck`. The real-engine tests cover a render, a Finalize, a Score-only run, a render from an edited Score, the covers weights download and a full cover. Real render test: `ARCSONG_REAL_ENGINE=1 caffeinate -ims uv run pytest -q tests/test_real_engine.py`. Real weights download (~10 GB, ~2.5 min, into a temp dir): `ARCSONG_REAL_DOWNLOAD=1 uv run pytest -q tests/test_real_download.py`.

Gotchas:
- Only one process can own the Lyra GPU lock; a second worker fails to load with "Another Lyra process owns the GPU". That now fails the waiting job with the reason and retries only when a job needs a worker (5 s apart).
- The worker exits when its server dies (parent check every 1 s), and SIGTERM ends open SSE streams so the server can stop with a page open. If a server was killed with an older build, check no `spawn_main` process is left.
- Job snapshots carry a `seq` seeded from the clock, so it keeps increasing across restarts; the page reloads the job list whenever its event stream reconnects.
- Serve FLAC as `audio/flac`; Chrome won't play the `audio/x-flac` that mimetypes guesses.
- Static files are mounted last in `create_app`; a mount registered before a route swallows it.
- mlx-Yue's `verify_conversion` rejects any extra file in `converted/` (the hub's `.cache`, `.gitattributes`, even a `.DS_Store`); the download deletes whatever `MlxYueModels.stray_files()` reports before verifying. Stray files in `vae/` are harmless.
- The Metal check imports MLX, so it runs in a short subprocess; the server process never imports MLX.
- The melody preview's piano lives in `arcsong/soundfont/` (88 MP3s, vendored, see `THIRD_PARTY_NOTICES.md`) and FastAPI mounts it at `/soundfont`: abcjs fetches one file per note, and nothing may come from a CDN at runtime. `.gitignore` excludes `*.mp3` with an exception for it.
- `POST /api/score/check` returns a compact summary, not mlx-Yue's `report()`: that carries every note as a `Fraction`, which FastAPI cannot encode.
- Covers need the ffmpeg binary (detected, never shipped: `brew install ffmpeg`) and mlx-Yue's `transcription` extra, which is part of arcsong's own dependency. The transcription model is loaded once per worker and stays resident: about 3 GiB on top of the song model, which the RAM check's "about 11 GiB" does not include.
- Download progress counts each part's own declared files plus whatever `*.incomplete` files sit under its `.cache/huggingface/download/` trees: the hub names those by hash, so their names can't be rebuilt, and two parts sharing a directory must not count each other's bytes. Stale `.incomplete` files (after a revision-pin change) can make a bar read 100% while nothing is installed; `installed` and `usable` come from real files, so nothing is wrongly enabled.
- A cover's upload is staged as `uploads/incoming-<uuid>` before any job row exists, so a refused upload leaves nothing behind, and `JobRunner.start()` sweeps stragglers. Every finish path deletes the recording.
- mlx-Yue refuses to render when macOS reports memory pressure (`kern.memorystatus_vm_pressure_level` ≥ 2), which loading the 11 GiB model can trigger on its own if other model servers are resident — ComfyUI at 4 GB was enough. `_cancel_guard` turns that refusal into advice rather than a traceback. Quit other model servers before real renders, as the M0 notes already say for timing.
- Never add files to a Take directory: mlx-Yue's `load_artifacts` verifies its contents, and Finalize depends on it (peaks stay in memory for that reason).
- Chrome doesn't load media in a hidden tab, so the Claude-in-Chrome automation tab can't test playback. Use the debug Chrome on port 9222 over the DevTools protocol (bring the target to front, click with `Input.dispatchMouseEvent`).
- Compare playback: pausing a Take whose `play()` hasn't settled raises AbortError; ignore it, or switching Takes stops both.
- The page remembers deleted song and job ids, so a list response already in flight can't resurrect a deleted song. Keep that filter when adding new list reloads.

## M0 engine spike (`spike/`)

Measurement harness comparing the mlx-Yue and audio.cpp Engines; not product code.
Findings and Engine recommendation: `docs/m0-report.md` (regenerate its tables with `uv run spike report`). Run log: `.scratch/m0-engine-spike/REPORT.md`.

- `uv run spike <setup|doctor|timing|cancel|repro|draft-final|hygiene|download|report> --engine mlx|audiocpp|fake`
- Verify: `uv run pytest -q` and `uv run ruff check .` (tests use `FakeEngine`; no real weights).
- Each measurement writes one JSON per case to `spike/results/` (committed) and skips existing results unless `--force`. Audio and tensors go to the gitignored `spike/runs/` and `spike/listen/`.
- mlx-Yue weights come from `~/projects/mlx-Yue/models` (`SPIKE_MLX_MODELS`). audio.cpp v0.8.0 and its GGUF weights come from `uv run spike setup` (pins in `spike/audiocpp_pins.json`).

Gotchas learned running it:
- Wrap real GPU runs in `caffeinate -ims`. A lid-close sleep corrupted a timing run, because audio.cpp's own timers count through sleep.
- mlx-Yue refuses to run on battery (`require_ac=True`); audio.cpp doesn't, so check `pmset -g batt` first.
- Run one GPU job at a time, and quit LM Studio/ComfyUI for timing numbers; they skew results (recorded in `env.model_servers`).
- 8bit and bf16 make different songs from the same seed; compare only within one precision.
- audio.cpp v0.8.0's CLI exports neither the generated Score nor Semantic tokens, and it reloads the model on every run.

## Agent skills

### Issue tracker

Local markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
