# 04 — audio.cpp Stage timing, peak memory and artifact sizes

**What to build:** The `timing` measurement for the audio.cpp Engine. It runs the same `song` case at bf16 and q8_0 × 8 and 32 Synthesis steps, 2 runs each, with the same measurements as the mlx-Yue matrix: load time, per-Stage times from `--log` (Stages the log doesn't separate are recorded as combined, stating which), total time, peak physical footprint of the subprocess, audio duration, and the size of every output file. Then run the full matrix on this Mac.

Read first: spec, ledger D-008, D-009, D-014; `CONTEXT.md`. Tickets 02 and 03 exist; reuse the sampler and results schema so both Engines' results compare field for field.

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] `uv run spike timing --engine audiocpp` has run the full 8-run matrix on this Mac; one results JSON per (precision, steps) case, with fields matching the mlx-Yue timing results
- [ ] The engineer's report quotes total and per-Stage times for q8_0/32 steps and bf16/32 steps next to the mlx-Yue numbers from ticket 02
- [ ] `uv run pytest -q` and `uv run ruff check .` pass
