# Songloom

Local web UI for the YuE2 music model. Plan: `PLAN.md`. Prior art: `docs/prior-art.md`.

## App (`songloom/`, `web/`)

- Run: `uv run songloom serve` (127.0.0.1:8840, `--engine mlx|fake`, `--data DIR`), or `dev start songloom`. Data (SQLite `songloom.db` + `songs/<job id>/`) lives in `$SONGLOOM_DATA`, else `~/Library/Application Support/songloom`. mlx-Yue weights come from `$SONGLOOM_MLX_MODELS`, else `~/projects/mlx-Yue/models`.
- Shape: FastAPI (`app.py`) → `JobRunner` (`runner.py`, owns the queue, live progress, SSE broadcast, worker restarts) → one spawned worker process (`worker.py`) that owns the Engine (`mlx_engine.py`, or `fake_engine.py` for tests). Only the server writes the database. A song is indexed only after mlx-Yue's `save_artifacts` returns.
- Web: Vite + React + TS in `web/`, built into `songloom/static/` (committed, so running needs no Node). After editing `web/src`, run `cd web && npm run build` and commit the build.
- Verify: `uv run pytest -q`, `uv run ruff check .`, `cd web && npm run typecheck`. Real render test: `SONGLOOM_REAL_ENGINE=1 caffeinate -ims uv run pytest -q tests/test_real_engine.py`.

Gotchas:
- Only one process can own the Lyra GPU lock. A second worker (another server, or an orphan) fails with "Another Lyra process owns the GPU", and today the runner restarts it in a loop (M1a review defect 2).
- A server with an open page (SSE) doesn't exit on SIGTERM, and a SIGKILLed server orphans its worker (defects 1, 3). Close the page before restarting, and check no `spawn_main` process is left.
- `seq` on job snapshots resets on server restart, so reload the page after restarting (defect 4).
- Serve FLAC as `audio/flac`; Chrome won't play the `audio/x-flac` that mimetypes guesses.
- Static files are mounted last in `create_app`; a mount registered before a route swallows it.

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
