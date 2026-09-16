# 07 — Draft→Final, both Engines

**What to build:** The `draft-final` measurement. mlx-Yue: render the `song` case as a Draft (8 Synthesis steps), keeping its Semantic tokens and synthesis noise; re-synthesize and decode those at 32 steps to make the Final; separately render the same Song request and seed directly at 32 steps. Record the Final re-render time against the direct 32-step total, and Final vs direct-32 Latents/audio comparison (bit-identical, else max-abs diff and correlation). audio.cpp: try the closest equivalent (same seed with a saved `nar_noise_file` at 8 then 32 steps). If Semantic tokens can't be supplied back, record re-using them as `unsupported` and record the cost of the fallback (a full 32-step re-run). Copy the Draft and Final audio of each Engine to the listening directory. Run on this Mac.

Read first: spec, ledger D-012; `CONTEXT.md`.

**Blocked by:** 01, 03

**Status:** ready-for-agent

- [ ] Tests through `FakeEngine` cover the timing comparison and the unsupported-fallback recording
- [ ] Results JSON exists for both Engines, with Draft time, Final re-render time, direct-32 time and the Final vs direct-32 comparison (or `unsupported` + fallback cost)
- [ ] Draft/Final listening pairs exist, with paths recorded in the results
- [ ] `uv run pytest -q` and `uv run ruff check .` pass
