# Songloom

Local web UI for the YuE2 music model. Plan: `PLAN.md`. Prior art: `docs/prior-art.md`.

## App (`songloom/`, `web/`)

- Run: `uv run songloom serve` (127.0.0.1:8840, `--engine mlx|fake`, `--data DIR`), or `dev start songloom`. Data (SQLite `songloom.db` + `songs/<job id>/`) lives in `$SONGLOOM_DATA`, else `~/Library/Application Support/songloom`. mlx-Yue weights come from `--mlx-models`, `$SONGLOOM_MLX_MODELS`, else `<data>/models` (the `dev` registration passes `--mlx-models ~/projects/mlx-Yue/models`).
- Shape: FastAPI (`app.py`) → `JobRunner` (`runner.py`, owns the queue, live progress, SSE broadcast, worker restarts) → one spawned worker process (`worker.py`) that owns the Engine (`mlx_engine.py`, or `fake_engine.py` for tests). Only the server writes the database. A song is indexed only after mlx-Yue's `save_artifacts` returns.
- Library: `GET /api/songs`, `GET /api/library` (usage), `GET /api/songs/{id}/download?format=flac|wav` (converted in memory, keeping bit depth), `DELETE /api/songs/{id}` (permanent: Take directory, song row and job row; broadcasts an SSE `deleted` message). - Setup (`setup.py` + `models.py`): `GET /api/setup` (checks, weights state from pinned file sizes, licence, download, `can_render`, `ready`), `POST /api/setup/checks|licence|download|download/cancel`, SSE `setup` messages with a `seq`. The weights download runs in its own spawned process at pinned revisions; the server polls bytes on disk. `POST /api/jobs` answers 409 until the weights are installed. `--engine fake` downloads 64 MB of fake weights so Setup can be tried without a GPU; `create_app` without `models=` uses preinstalled fake weights, so tests skip the gate.
- The page has Create / Library / Setup views on `#/`, `#/library`, `#/setup`; it opens on Setup while not ready.
- Web: Vite + React + TS in `web/`, built into `songloom/static/` (committed, so running needs no Node). After editing `web/src`, run `cd web && npm run build` and commit the build.
- Verify: `uv run pytest -q`, `uv run ruff check .`, `cd web && npm run typecheck`. Real render test: `SONGLOOM_REAL_ENGINE=1 caffeinate -ims uv run pytest -q tests/test_real_engine.py`. Real weights download (~10 GB, ~2.5 min, into a temp dir): `SONGLOOM_REAL_DOWNLOAD=1 uv run pytest -q tests/test_real_download.py`.

Gotchas:
- Only one process can own the Lyra GPU lock; a second worker fails to load with "Another Lyra process owns the GPU". That now fails the waiting job with the reason and retries only when a job needs a worker (5 s apart).
- The worker exits when its server dies (parent check every 1 s), and SIGTERM ends open SSE streams so the server can stop with a page open. If a server was killed with an older build, check no `spawn_main` process is left.
- Job snapshots carry a `seq` seeded from the clock, so it keeps increasing across restarts; the page reloads the job list whenever its event stream reconnects.
- Serve FLAC as `audio/flac`; Chrome won't play the `audio/x-flac` that mimetypes guesses.
- Static files are mounted last in `create_app`; a mount registered before a route swallows it.
- mlx-Yue's `verify_conversion` rejects any extra file in `converted/` (the hub's `.cache`, `.gitattributes`, even a `.DS_Store`); the download deletes whatever `MlxYueModels.stray_files()` reports before verifying. Stray files in `vae/` are harmless.
- The Metal check imports MLX, so it runs in a short subprocess; the server process never imports MLX.
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
