# Songloom

Local web UI for the YuE2 music model. Plan: `PLAN.md`. Prior art: `docs/prior-art.md`.

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
