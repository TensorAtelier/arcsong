# 04 — audio.cpp Stage timing, peak memory and artifact sizes

**What to build:** The `timing` measurement for the audio.cpp Engine. It runs the same `song` case at bf16 and q8_0 × 8 and 32 Synthesis steps, 2 runs each, with the same measurements as the mlx-Yue matrix: load time, per-Stage times from `--log` (Stages the log doesn't separate are recorded as combined, stating which), total time, peak physical footprint of the subprocess, audio duration, and the size of every output file. Then run the full matrix on this Mac.

Read first: spec, ledger D-008, D-009, D-014; `CONTEXT.md`. Tickets 02 and 03 exist; reuse the sampler and results schema so both Engines' results compare field for field.

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] `uv run spike timing --engine audiocpp` has run the full 8-run matrix on this Mac; one results JSON per (precision, steps) case, with fields matching the mlx-Yue timing results
- [ ] The engineer's report quotes total and per-Stage times for q8_0/32 steps and bf16/32 steps next to the mlx-Yue numbers from ticket 02
- [ ] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, after ticket 03:** (1) Memory is not yet measured for audio.cpp: the runner samples the Python child's footprint, not the `audiocpp_cli` subprocess it launches. Ticket 03's doctor results show a ~16 MB peak, which is only the wrapper. Sample the CLI's pid (or the whole process tree) with the same `ri_phys_footprint` method. (2) `timing`'s precision table has no `audiocpp` entry yet (should be `bf16`, `q8_0`). (3) Model load time for audio.cpp comes from the log (session/AR/NAR/VAE load) via `lazy_load_seconds`/`session_load_seconds`; keep field names comparable with the mlx results. (4) The YuE2 GGUF weights come from HF `audio-cpp/Yue2-3B-GGUF` (pinned in `spike/audiocpp_pins.json`), not `audio.cpp-gguf`.
