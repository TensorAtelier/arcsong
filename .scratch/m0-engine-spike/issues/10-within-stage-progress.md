# 10 — Progress within a Stage, both Engines

**What to build:** A `progress` measurement that answers the part of PLAN.md's M0 "Per-stage progress" question that is still open: which progress signals fire *inside* each Stage, how often, and whether they can drive a % bar. For mlx-Yue, record every `on_token` callback during planning (Score writing) and semantic generation, plus any per-step signal during synthesis and decoding (find what `lyra.YuE2Pipeline` exposes, e.g. `on_progress`/report hooks used by `synthesize` and `decode`). For each Stage record: signal name, count, timestamps (inter-arrival min / median / max), whether the total is known up front (so a % can be computed) or only a running count, and how closely progress-over-time tracks wall time (linear or not). For audio.cpp, record the same from `--log` line arrivals per Stage. The known facts are that synthesis logs nothing and decoding logs one line per VAE chunk; confirm them on the `song` case. Run on this Mac, and add a "Progress within a Stage" section to `docs/m0-report.md` via `uv run spike report`, then tick PLAN.md's "Per-stage progress" checkbox.

Read first: `docs/m0-report.md` ("Per-Stage progress" and "Progress within a Stage was not measured"), spec, ledger D-005, D-008, D-015; `CONTEXT.md`. mlx-Yue source: `~/projects/mlx-Yue/src/lyra/pipeline.py` (same commit as the installed dependency).

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Tests through `FakeEngine` (with scripted per-Stage progress signals) cover counting, inter-arrival statistics, known-total vs running-count detection, and linearity against wall time
- [x] Results JSON exists for both Engines on the `song` case (8bit/q8_0, 8 steps is enough), with per-Stage signal counts, inter-arrival stats and a % bar verdict per Stage
- [x] The report gains a generated "Progress within a Stage" table plus a short interpretation stating, per Engine and Stage, what M1's progress bar can use and what event rate the SSE throttle must handle
- [x] PLAN.md's "Per-stage progress" checkbox is ticked with its note updated; no other PLAN.md change
- [x] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, when writing this ticket (2026-09-17):** it comes from goal review defect 3. The M0 checklist asked for it, but the spec's user stories dropped it. Real GPU runs: check `pmset -g batt` for AC, wrap in `caffeinate -ims`, one job at a time, and quit LM Studio/ComfyUI if possible (the env snapshot records them). Keep instrumentation passive: counting callbacks must not change what a Take does or noticeably slow it; compare total time against the committed 8-step timing results as a sanity check. Out of scope: the other goal-review risks (baseline memory snapshot in `env`, SIGKILL recorded as `oom`, kill while a Take is being saved). File them separately if wanted.

**QA round 1 (FAIL):** (1) `cancel` `stage_events` absorbed progress events; (2) `stderr_is_tty` wasn't recorded in results; (3) linearity deviation was sampled only at arrivals. All fixed in round 2 (both Engines re-run under `caffeinate` on AC, 2026-09-17 ~09:14 UTC).

**QA round 2 (FAIL) — parked on `wip/m0-engine-spike/10-within-stage-progress` (d191ac6). Open defects:**
1. PLAN.md:120, docs/m0-report.md:59, :337–345, :358–362, :637–642 — mlx-Yue decoding's results verdict is `uneven_percent` (rendered "stepped: % from a known total"), the same as synthesis. But the PLAN.md note says a stepped % exists "only in mlx-Yue synthesis", and the prose calls decoding too coarse for a bar. The verdict can't tell deviation 0.18 over 18 updates (synthesis) from 0.53 over 3 updates (decoding). Fix: add a documented "too coarse" verdict (deviation or update-count threshold) and regenerate from the committed jsonl (no GPU needed), or make the note and prose match the table. Also qualify the PLAN.md note's "token counts, up to 71/s" as mlx-Yue only.
2. tests/test_progress.py:194–195 — the docstring cites `progress-mlx-song-8bit-8.json` for numbers (208.180–218.958, 8/19, 17/19) from the superseded run. The committed timeline has decoding 200.295–210.434 with updates 0, 9/19, 19/19. Fix the numbers or drop the citation.
Non-blocking (QA): several prose numbers aren't guarded by the numbers test; "slowest signals change every 3–5 s" understates mlx synthesis (~10 s between value changes).
QA round 2 otherwise confirmed: the analysis rebuilt from the jsonl matches both results files; round-1 fixes are real (the cancel filter test fails without the filter); the stderr tee is passive and patches no Engine source; no earlier results changed; report regeneration is byte-stable.

**Resolved 2026-09-17 (user approved, no GPU):** fixed in `3fcfe84`, merged into `feat/m0-engine-spike` (`67fe51b`). A new `coarse_percent` verdict (a % signal with fewer than 5 updates) is documented next to the 0.15 cut-off. Committed verdicts were re-derived from the saved `progress-events.jsonl` timelines; only mlx-Yue decoding changed, and a script asserted all other stage data was identical. The PLAN.md note names each Engine; the test docstring was corrected, with a new test pinned to the committed decoding timeline; the "3–5 s" claim was corrected. Verified: 137 tests pass, ruff clean, report regeneration byte-stable.
