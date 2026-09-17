# 02 — mlx-Yue Stage timing, peak memory and artifact sizes

**What to build:** The `timing` measurement for the mlx-Yue Engine. It runs the `song` case at bf16 and 8bit × 8 and 32 Synthesis steps, 2 runs each, one GPU job at a time. For every run it records: model load time; wall time for each Stage (planning, semantic generation, synthesis, decoding) and in total; peak physical footprint (`ri_phys_footprint`, sampled every 250 ms from outside the child process) alongside MLX's own peak-memory figure; audio duration; and the size of every file the Take writes. Then run the full matrix on this Mac and leave the results JSON files in the results directory.

Read first: spec, ledger D-008, D-009, D-014, D-015; `CONTEXT.md`. The harness from ticket 01 exists.

**Blocked by:** 01

**Status:** done

- [x] A memory sampler test shows the sampler reports a peak within 10% of a known allocation made by a child process
- [x] Tests through `FakeEngine` cover per-Stage timing aggregation and artifact size capture
- [x] `uv run spike timing --engine mlx` has run the full 8-run matrix on this Mac; one results JSON per (precision, steps) case exists with per-Stage times, load time, peak footprint and file sizes for both runs (failed or OOM runs recorded as outcomes)
- [x] The engineer's report quotes the per-Stage times for 8bit/32 steps and bf16/32 steps
- [x] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, after ticket 01:** two runner gaps matter for this multi-hour matrix (D-015: a run must survive failures and resume). (1) `run_case` has no timeout, so a hung child blocks the whole matrix. (2) If the parent `spike` process is killed, the child keeps running on the GPU. Handling both is in scope here only as far as the matrix needs it (e.g. a generous per-run timeout recorded as `failed`, and killing the child when the parent exits). LM Studio and ComfyUI were running during ticket 01; the env snapshot records that, and timing numbers should be read with it in mind.
