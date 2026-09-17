# 07 — Draft→Final, both Engines

**What to build:** The `draft-final` measurement. mlx-Yue: render the `song` case as a Draft (8 Synthesis steps), keeping its Semantic tokens and synthesis noise; re-synthesize and decode those at 32 steps to make the Final; separately render the same Song request and seed directly at 32 steps. Record the Final re-render time against the direct 32-step total, and Final vs direct-32 Latents/audio comparison (bit-identical, else max-abs diff and correlation). audio.cpp: try the closest equivalent (same seed with a saved `nar_noise_file` at 8 then 32 steps). If Semantic tokens can't be supplied back, record re-using them as `unsupported` and record the cost of the fallback (a full 32-step re-run). Copy the Draft and Final audio of each Engine to the listening directory. Run on this Mac.

Read first: spec, ledger D-012; `CONTEXT.md`.

**Blocked by:** 01, 03

**Status:** done

- [x] Tests through `FakeEngine` cover the timing comparison and the unsupported-fallback recording
- [x] Results JSON exists for both Engines, with Draft time, Final re-render time, direct-32 time and the Final vs direct-32 comparison (or `unsupported` + fallback cost)
- [x] Draft/Final listening pairs exist, with paths recorded in the results
- [x] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, after ticket 06:** (1) Both Engines reproduce bit-identically for the same seed at one precision: mlx-Yue warm/warm and warm/fresh (Score, Semantic tokens, Latents, audio); audio.cpp audio. So "same seed at 32 steps" is an exact fallback for Draft→Final, costing a full re-run. (2) audio.cpp v0.8.0's CLI does **not** export a generated Score: `--out-dir` writes nothing more for YuE2, and `--text-out` errors. (Correction after QA: v0.8.0's docs never promised it. Score export was added on `main` by PR #561, merged 2026-09-15 23:09 UTC, after the v0.8.0 tag, so the next release should have it.) It also exposes no Semantic tokens. (3) `RunOutput.stage_outputs` and the runner's `measures=`/`summarize=` hooks (added in 06) are the natural building blocks here.

**QA round 1 (FAIL):** four problems in audio.cpp's result. (1) The Draft time included a 165 s noise probe. (2) Final ≠ direct-32 was unexplained (the noise source differs) and direct-32 was not named as the same-seed workaround. (3) The Fake hid the noise mismatch. (4) The noise was compared with itself. Fixed by a summary-only change (`--resummarize` from recorded runs) and Fake/test changes; no GPU rerun.
