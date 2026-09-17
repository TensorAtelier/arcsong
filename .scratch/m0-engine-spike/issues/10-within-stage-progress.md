# 10 — Progress within a Stage, both Engines

**What to build:** A `progress` measurement that answers the part of PLAN.md's M0 "Per-stage progress" question that is still open: which progress signals fire *inside* each Stage, how often, and whether they can drive a % bar. For mlx-Yue, record every `on_token` callback during planning (Score writing) and semantic generation, plus any per-step signal during synthesis and decoding (find what `lyra.YuE2Pipeline` exposes, e.g. `on_progress`/report hooks used by `synthesize` and `decode`). For each Stage record: signal name, count, timestamps (inter-arrival min / median / max), whether the total is known up front (so a % can be computed) or only a running count, and how closely progress-over-time tracks wall time (linear or not). For audio.cpp, record the same from `--log` line arrivals per Stage. The known facts are that synthesis logs nothing and decoding logs one line per VAE chunk; confirm them on the `song` case. Run on this Mac, and add a "Progress within a Stage" section to `docs/m0-report.md` via `uv run spike report`, then tick PLAN.md's "Per-stage progress" checkbox.

Read first: `docs/m0-report.md` ("Per-Stage progress" and "Progress within a Stage was not measured"), spec, ledger D-005, D-008, D-015; `CONTEXT.md`. mlx-Yue source: `~/projects/mlx-Yue/src/lyra/pipeline.py` (same commit as the installed dependency).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Tests through `FakeEngine` (with scripted per-Stage progress signals) cover counting, inter-arrival statistics, known-total vs running-count detection, and linearity against wall time
- [ ] Results JSON exists for both Engines on the `song` case (8bit/q8_0, 8 steps is enough), with per-Stage signal counts, inter-arrival stats and a % bar verdict per Stage
- [ ] The report gains a generated "Progress within a Stage" table plus a short interpretation stating, per Engine and Stage, what M1's progress bar can use and what event rate the SSE throttle must handle
- [ ] PLAN.md's "Per-stage progress" checkbox is ticked with its note updated; no other PLAN.md change
- [ ] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, when writing this ticket (2026-09-17):** it comes from goal review defect 3. The M0 checklist asked for it, but the spec's user stories dropped it. Real GPU runs: check `pmset -g batt` for AC, wrap in `caffeinate -ims`, one job at a time, and quit LM Studio/ComfyUI if possible (the env snapshot records them). Keep instrumentation passive: counting callbacks must not change what a Take does or noticeably slow it; compare total time against the committed 8-step timing results as a sanity check. Out of scope: the other goal-review risks (baseline memory snapshot in `env`, SIGKILL recorded as `oom`, kill while a Take is being saved). File them separately if wanted.
