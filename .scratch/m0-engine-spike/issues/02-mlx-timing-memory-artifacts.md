# 02 — mlx-Yue Stage timing, peak memory and artifact sizes

**What to build:** The `timing` measurement for the mlx-Yue Engine. It runs the `song` case at bf16 and 8bit × 8 and 32 Synthesis steps, 2 runs each, one GPU job at a time. For every run it records: model load time; wall time for each Stage (planning, semantic generation, synthesis, decoding) and in total; peak physical footprint (`ri_phys_footprint`, sampled every 250 ms from outside the child process) alongside MLX's own peak-memory figure; audio duration; and the size of every file the Take writes. Then run the full matrix on this Mac and leave the results JSON files in the results directory.

Read first: spec, ledger D-008, D-009, D-014, D-015; `CONTEXT.md`. The harness from ticket 01 exists.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] A memory sampler test shows the sampler reports a peak within 10% of a known allocation made by a child process
- [ ] Tests through `FakeEngine` cover per-Stage timing aggregation and artifact size capture
- [ ] `uv run spike timing --engine mlx` has run the full 8-run matrix on this Mac; one results JSON per (precision, steps) case exists with per-Stage times, load time, peak footprint and file sizes for both runs (failed or OOM runs recorded as outcomes)
- [ ] The engineer's report quotes the per-Stage times for 8bit/32 steps and bf16/32 steps
- [ ] `uv run pytest -q` and `uv run ruff check .` pass
