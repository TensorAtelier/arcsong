# M0 engine spike

**Status:** ready-for-agent
**Ledger:** `.scratch/m0-engine-spike/DECISIONS.md` (D-001…D-019). Glossary: `CONTEXT.md`.

## Problem Statement

Before building songloom's UI, the developer doesn't know which Engine to build on (mlx-Yue or audio.cpp), or whether the features PLAN.md depends on work on this Mac at all: cancelling a running Take, seeing progress per Stage, reproducing a Take from its seed, turning a Draft into a Final, fitting in memory, and keeping library size manageable. Guessing wrong means redesigning the M1 worker, queue and library after they're built.

## Solution

A measurement harness (`spike/`) that runs the same fixed Song requests through both Engines behind one interface. It records every M0 answer as committed JSON results, and produces an M0 report with an Engine recommendation plus audio pairs the developer can listen to. No product code is built.

## User Stories

1. As the developer, I want one command that sets up both Engines (pinned mlx-Yue dependency, pinned audio.cpp binary, audio.cpp weights), so that the spike is reproducible.
2. As the developer, I want existing mlx-Yue weights reused instead of re-downloaded, so that setup doesn't cost 10 GB of bandwidth.
3. As the developer, I want a `doctor`-style check that both Engines load and produce a short `clip` Take, so that I know the harness works before multi-hour runs.
4. As the developer, I want both Engines driven through the same interface, so that their numbers are comparable.
5. As the developer, I want operations an Engine can't perform recorded as "Unsupported", so that missing capabilities show up as findings rather than crashes.
6. As the developer, I want wall time per Stage (planning, semantic generation, synthesis, decoding) and model load time for the `song` case, so that I know which Stage dominates.
7. As the developer, I want those timings at each precision (bf16 and 8-bit) and at 8 and 32 Synthesis steps, so that I can pick defaults.
8. As the developer, I want each timing case run twice, so that I can see variance.
9. As the developer, I want peak physical memory per run, measured the same way for both Engines, so that I can set memory-aware defaults and a minimum RAM.
10. As the developer, I want each measurement's results to record the machine, OS, Engine version and whether other model servers held memory, so that the numbers can be interpreted later.
11. As the developer, I want to know, for each Stage, how long a cancel request takes to return control, so that I can design the worker's cancel path.
12. As the developer, I want to know whether the Engine can run another Take in the same process after a cancel, so that I know whether a cancel costs a model reload.
13. As the developer, I want to know what a cancelled Take leaves on disk, so that the library never shows a partial Take as complete.
14. As the developer, I want to know whether the same Song request and seed give identical Score, Semantic tokens, Latents and audio in a warm process and in a fresh process, so that I know what "re-run with these settings" can promise.
15. As the developer, I want one same-seed audio pair saved for listening, so that I can judge any differences by ear.
16. As the developer, I want to know whether a Draft's Semantic tokens and noise can be re-synthesized at 32 steps into a Final, and how that Final compares to a direct 32-step render, so that I can place feature #5.
17. As the developer, I want the Final re-render time compared with a full 32-step run, so that I know the real saving.
18. As the developer, I want a Draft/Final audio pair saved for listening, so that I can judge the quality gain.
19. As the developer, I want to know whether stale resource files from a killed run block a rerun to the same output directory, and what cleanup fixes it, so that the worker can clean up.
20. As the developer, I want to know whether a Hugging Face download into a local directory leaves metadata files that break mlx-Yue's weight verification, and the fix, so that the setup screen's download works.
21. As the developer, I want the size of every file a `song` Take writes, so that I can size library cleanup.
22. As the developer, I want a failed or out-of-memory measurement recorded as that measurement's outcome while the run continues, so that one failure doesn't waste a multi-hour matrix.
23. As the developer, I want the matrix to resume and skip cases whose results already exist, so that an interruption doesn't mean starting over.
24. As the developer, I want an M0 report that answers every M0 checkbox with numbers traceable to the results files, so that I can trust and audit it.
25. As the developer, I want an Engine recommendation that applies the decision rule in D-017 and mentions hybrid options, so that I can confirm or override the choice quickly.
26. As the developer, I want PLAN.md's M0 checkboxes ticked with a pointer to the report, and plan items the findings change flagged rather than rewritten, so that the plan stays mine.
27. As the future Engine-adapter author, I want the spike's Engine interface to mirror PLAN.md's Engine seam, so that M1 can start from it.

## Implementation Decisions

- **Repository:** git repo on `main`; `.gitignore` excludes venv, runs, vendor binaries, models, listening audio, and any audio/tensor/weight file types (D-018).
- **Project:** `uv` project, Python 3.12; pytest + ruff. mlx-Yue is a git dependency pinned to commit `9253ed1`; its weights are read from a configurable path defaulting to `~/projects/mlx-Yue/models` (D-006).
- **audio.cpp:** pinned release `v0.8.0` macOS arm64 Metal tarball, sha256 recorded, unpacked into a gitignored vendor directory; GGUF weights (main q8_0, main bf16, VAE f16 plus sidecars) from HF `audio-cpp/Yue2-3B-GGUF` (the repo audio.cpp v0.8.0's own model spec names; corrected after ticket 03) into a gitignored models directory (D-006).
- **Engine interface (`SpikeEngine`):** `load(precision)`, `plan(request)`, `generate_semantic(score_or_request)`, `synthesize(semantic, steps, noise)`, `decode(latents)`, `run(request, steps)`. Every call takes a cancel check and emits timestamped Stage events; unavailable operations raise `Unsupported` (D-005).
  - `MlxYueEngine`: in-process `lyra.YuE2Pipeline`, using its public Stage methods, `cancelled=` and `on_token`.
  - `AudioCppEngine`: subprocess of the prebuilt CLI; whole-run only; Stage times parsed from `--log`; cancel = process kill; supports seed, Synthesis steps, planning mode, ABC input and noise file.
- **Harness modules:** memory sampler (peak `ri_phys_footprint` of a target pid every 250 ms, D-008); a runner that executes a measurement in a fresh child process, writes one JSON results file per case, skips existing results unless forced, and records crashes/OOM/Unsupported as outcomes (D-015); an environment snapshot (machine, OS, Engine versions/commits, other model-server processes).
- **Measurements** (each a CLI subcommand): `doctor`, `timing` (D-009 matrix), `cancel` (D-010), `repro` (D-011), `draft-final` (D-012), `hygiene` and `download` (D-013), with artifact sizes captured in `timing` (D-014).
- **Cases:** `clip` (upstream quickstart request) and `song` (~3-min full-song example), identical inputs for both Engines, Planning mode `full`, fixed seed (D-007).
- **Results schema:** one JSON per case: `{measurement, engine, engine_version, case, params, env, outcome: ok|unsupported|failed|oom, error?, runs: [...measurement-specific numbers...]}`. The report generator reads only these files.
- **Report:** generated skeleton with the numbers filled in from results (tables per question); the recommendation and interpretation are written against D-017. Written to `docs/m0-report.md`.
- **Listening pairs:** copied to a gitignored listening directory; paths listed in the report (D-004).

## Testing Decisions

- A good test drives the harness through the `SpikeEngine` seam with a `FakeEngine` (scripted Stage durations, cancel responsiveness, deterministic or perturbed outputs, injectable crash/Unsupported) and asserts on the results JSON and the report output: external behaviour, not internals.
- Tested: Stage timing aggregation, cancel orchestration and latency calculation, reproducibility comparisons (equality, max-abs diff), resume/skip logic, failure-as-outcome recording, results schema, report generation, `--log` parsing for audio.cpp (against captured sample log text), memory sampler against a child process that allocates a known amount.
- Not tested with real weights inside pytest (D-016). Real measurements are commands whose committed results files are the evidence.
- Verification commands: `uv run pytest -q`, `uv run ruff check .`.
- Prior art: none in this repo (new project).

## Out of Scope

- FastAPI server, SQLite, job queue, worker supervisor, frontend (M1).
- Covers, transcription, ffmpeg (M4).
- NVIDIA/CUDA measurement (M5); a C-ABI or HTTP-server adapter for audio.cpp.
- Optimising either Engine; patching Engine source.
- A final product name.

## Further Notes

- Real-weight runs are long: the timing matrix is roughly 1.5–3 h of GPU time. Run them in the background, one GPU job at a time, and avoid running other model servers alongside.
- The spike runs a third-party prebuilt binary (audio.cpp release asset). Verify its sha256 against the release before running it.
- Published reference for sanity checks: mlx-Yue on an M5 Pro with 24 GB, 3:20 song at 32 steps = 337 s, 10.4 GiB peak.
