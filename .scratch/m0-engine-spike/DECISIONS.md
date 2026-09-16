# m0-engine-spike — decisions

Coverage: [x] scope [x] actors [x] terms [x] data [x] interfaces [x] stack [x] edges [x] seams [x] proof

Facts gathered 2026-09-16 before deciding:
- `~/projects/mlx-Yue` is cloned at `9253ed1` with a working `.venv` and weights (`models/converted` 9.2 GB: AR bf16 + 8bit, NAR bf16; `models/vae` 0.5 GB).
- mlx-Yue exposes `lyra.YuE2Pipeline` with public `plan`, `generate_semantic`, `synthesize(noise=)`, `decode`, each taking `cancelled=`; `on_token` on the token stages; `save_artifacts`.
- audio.cpp v0.8.0 (2026-09-15, Apache-2.0) ships `audio-v0.8.0-bin-macos-arm64-metal.tar.gz` with YuE2. Its C++ runtime has the same four stages internally, but the CLI, server and C ABI expose only a whole run. No cancel or progress callback for YuE2 was found; the CLI has `--log` progress output and `nar_noise_file`, `num_inference_steps`, `abc`/`abc_file` options. GGUF weights: HF `audio-cpp/audio.cpp-gguf` (default `yue2-3b-q8_0.gguf` + `yue2-vae-f16.gguf`).
- Machine: M5 Pro, 64 GiB, macOS 26.4.1, 227 GiB free disk. `uv`, `cmake`, Xcode present; `ffmpeg` absent (only needed for transcription, out of scope).
- Published reference (stavitian, mlx-Yue, M5 Pro 24 GB): 3:20 song at 32 steps = 337 s, 10.4 GiB peak.

## D-001 — Scope is the M0 checklist, nothing more

- Decision: Answer every M0 item in PLAN.md: engine choice, per-Stage timing split, cancellation, Draft→Final, seed reproducibility, timing + peak memory (bf16 vs 8bit, 8 vs 32 Synthesis steps), stale resource-file hygiene, model download without HF cache metadata, artifact sizes per Take.
- Why: M0 exists to de-risk M1; anything beyond the checklist is M1 work done without a spec.
- Rejected: building the M1 worker process now (premature; its design depends on these answers); benchmarking NVIDIA (no CUDA machine).
- Reversibility: cheap
- To change: add an item to the spec and a ticket.
- Decided by: AI

## D-002 — Actors

- Decision: Two readers. The developer (the user) decides the M1 Engine from the report and listens to audio pairs. The future Engine-adapter author (an agent in M1) reuses the adapter shape and measured constraints.
- Why: No end user touches a spike.
- Rejected: none.
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-003 — Glossary

- Decision: Terms resolved into `CONTEXT.md`: Song request, Planning mode, Score, Take, Draft, Final, Stage, Semantic tokens, Latents, Synthesis steps, Engine.
- Why: Both engines and upstream use different words (plan/cot/ABC, NAR/ODE/inference steps); the spike's report compares them, so it needs one vocabulary.
- Rejected: using upstream's names (they differ per engine).
- Reversibility: cheap
- To change: edit `CONTEXT.md`.
- Decided by: AI

## D-004 — Where spike code and data live

- Decision: Spike code in a `spike/` Python package in the songloom repo, run via `uv run`. Heavy outputs (audio, `.npy`, logs) go to `spike/runs/` (gitignored). Each measurement's numbers are written as JSON to `spike/results/` (committed). The report is `docs/m0-report.md`. Listening pairs are copied as small FLAC/MP3 files to `spike/listen/` (gitignored, paths listed in the report).
- Why: Results must be reproducible and reviewable in git; audio and tensors are large and derived from CC BY-NC weights, so they stay out of git.
- Rejected: a separate scratch repo (loses history next to the plan); committing audio (licence + size).
- Reversibility: cheap
- To change: move directories.
- Decided by: AI

## D-005 — One adapter per Engine behind a shared spike interface

- Decision: Define a small `SpikeEngine` protocol: `load(precision)`, `plan`, `generate_semantic`, `synthesize(steps, noise)`, `decode`, `run(request)` (whole Take), each accepting a cancel check and emitting timestamped Stage events. `MlxYueEngine` calls `lyra` in-process. `AudioCppEngine` drives the prebuilt CLI as a subprocess: whole runs only, Stage timing parsed from `--log` output, cancel = kill the process. Operations an Engine cannot do raise `Unsupported`, recorded as a finding rather than a failure.
- Why: The same measurements must run against both Engines. The shape mirrors PLAN.md's Engine interface, so M1 inherits it. "Unsupported" is itself a key finding for the engine choice.
- Rejected: audio.cpp via the C ABI + ctypes (more work, and the ABI still exposes no YuE2 stage/cancel hooks); the audio.cpp HTTP server (same limits, plus a process to manage).
- Reversibility: cheap
- To change: add a C-ABI adapter in a ticket if the CLI path hides something.
- Decided by: AI

## D-006 — Stack and dependency pinning

- Decision: songloom becomes a `uv` project (Python 3.12). mlx-Yue is a git dependency pinned to `9253ed1`, with weights reused from `~/projects/mlx-Yue/models` via a config path (no re-download). audio.cpp uses the pinned `v0.8.0` macOS arm64 Metal release tarball, sha256 recorded, unpacked into `spike/vendor/` (gitignored). Its GGUF weights (q8_0 main + f16 VAE, plus bf16 main to match the precision comparison) download into `spike/models/` (gitignored). Tests: pytest; lint: ruff.
- Why: A pinned git dependency is what PLAN.md intends for M1, so the spike also proves that install path works. The prebuilt binary is how end users would get audio.cpp. Reusing 9.7 GB of existing weights saves time.
- Rejected: building audio.cpp from source (users wouldn't); importing mlx-Yue from its local checkout by path (hides packaging problems).
- Reversibility: cheap
- To change: edit `pyproject.toml` / the vendor script.
- Decided by: AI

## D-007 — Two fixed test cases, same inputs for both Engines

- Decision: `clip` = a short Song request (~15–20 s, the upstream quickstart request) for cancel, reproducibility and hygiene checks. `song` = a ~3-minute Song request (mlx-Yue's `examples/full-song.json`) for timing, memory and artifact sizes. Both use Planning mode `full` and a fixed seed. Identical style, lyrics and seed on both Engines.
- Why: Short cases make the repeated checks cheap; one realistic song gives the numbers M1 needs. Identical inputs make Engine numbers comparable.
- Rejected: a matrix of song lengths (cost without changing any decision).
- Reversibility: cheap
- To change: edit the case files.
- Decided by: AI

## D-008 — Measurement method

- Decision: Stage timing from monotonic timestamps around each Stage (mlx-Yue) or from `--log` lines (audio.cpp), plus total wall time and load time reported separately. Peak memory = the process's peak physical footprint (`proc_pid_rusage` `ri_phys_footprint`), sampled every 250 ms from a watcher, with the same method for both Engines. Each engine runs in its own fresh process. MLX's own peak-memory figure is recorded alongside. Each timing case runs 2× and reports both runs. The results file records machine, OS, engine version and a baseline memory snapshot.
- Why: RSS under-counts Metal unified memory; physical footprint is what macOS pressure acts on. External sampling works for a subprocess binary too.
- Rejected: `/usr/bin/time -l` max RSS alone (misses GPU allocations); a single run (no sense of variance).
- Reversibility: cheap
- To change: swap the sampler.
- Decided by: AI

## D-009 — Timing matrix

- Decision: `song` case per Engine at the precisions it offers (mlx-Yue: bf16, 8bit; audio.cpp: bf16, q8_0) × Synthesis steps 8 and 32. 2 runs each → up to 16 full-song runs (roughly 1.5–3 h of GPU time total), run in the background, one at a time.
- Why: Covers PLAN.md's "bf16 vs 8bit, 8 vs 32 steps" question for both Engines, which is also the main input to the engine choice.
- Rejected: 3+ runs each (time cost; variance is visible with 2).
- Reversibility: cheap
- To change: edit the matrix config.
- Decided by: AI

## D-010 — Cancellation test

- Decision: For each Stage, start the `clip` case, request cancel once that Stage has been running ~1 s (the synthesis/decode checks may use `song` if `clip` finishes those Stages too fast), and measure latency from the request to control returning. Then run a full `clip` in the same process to confirm the pipeline is still usable, and check that no partial Take is left looking complete. audio.cpp: measure kill-to-exit latency and the reload cost of the next run.
- Why: M1's worker design (cooperative cancel vs kill + restart) hangs on this number.
- Rejected: testing only one Stage (cancel behaviour differs per Stage loop).
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-011 — Seed reproducibility test

- Decision: Run `clip` with the same seed 3×: twice in one warm process, once in a fresh process. Compare Score text equality, Semantic tokens equality, Latents max-abs difference, and audio bit-identity (else max-abs diff + a correlation figure). Both Engines. Save one pair for listening.
- Why: "Re-run with these settings" and Draft→Final depend on it; warm vs fresh can differ because of caches or kernel selection.
- Rejected: comparing audio only (a mismatch wouldn't show which Stage diverges).
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-012 — Draft→Final test

- Decision: mlx-Yue: render `song` at 8 steps, saving Semantic tokens and synthesis noise; re-synthesize and decode those at 32 steps; also render the same request + seed directly at 32 steps. Compare Final vs direct-32 numerically; time the Final re-render against the full 32-step run. Save the Draft/Final pair for listening. audio.cpp: attempt the same with a saved `nar_noise_file`. If the Semantic tokens cannot be supplied back, record Draft→Final as Unsupported, with the cost of the closest workaround (a full re-run with the same seed, if seed reproducibility holds).
- Why: Decides feature #5 and its real saving.
- Rejected: judging quality numerically alone (it's a listening judgement; the user does that).
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-013 — Hygiene and download checks

- Decision: (a) Kill a mlx-Yue run mid-Stage, then rerun to the same output directory; record whether stale `<output>.resources.json[l]` files block it and what cleanup the worker would need. (b) Model download: use `huggingface_hub` with `local_dir` into a temp directory for the smallest weight set that still exercises mlx-Yue's `verify_conversion` (config + tokenizer + the VAE or 8bit AR). Record which files HF adds (`.cache/huggingface/…`), whether verification fails on them, and the fix. No full 10 GB re-download.
- Why: Both are PLAN.md items that directly shape M1's setup screen and worker cleanup.
- Rejected: full re-download (time and bandwidth for no extra signal).
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-014 — Artifact sizes

- Decision: For each `song` run, record the size of every file the Engine writes (audio, Score, Semantic tokens, Latents, noise, JSON), plus the size of the listening-quality audio alone.
- Why: Sizes the library cleanup feature (PLAN.md).
- Rejected: none.
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-015 — Failure and edge behaviour

- Decision: A crash, out-of-memory kill or Unsupported operation during a measurement is written to the results file as the outcome of that measurement; the harness moves on. Before a GPU run, the harness records whether Ollama, LM Studio or ComfyUI processes hold memory, and warns without blocking. Real-weight runs are serial and can be resumed per case (a case whose results JSON exists is skipped unless forced).
- Why: A spike's job is to find failures; a multi-hour matrix must survive one and resume.
- Rejected: aborting on first failure.
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-016 — Testing seam

- Decision: One seam: the `SpikeEngine` protocol. The harness (timing, cancel orchestration, comparisons, resume, results/report writing) is unit-tested against a `FakeEngine`. Real-weight measurements are run as commands, not tests, and their evidence is the committed results JSON. Verification commands: `uv run pytest -q` and `uv run ruff check .`.
- Why: Real runs take minutes to hours and need GPU + weights; the logic that turns them into numbers still needs to be right.
- Rejected: pytest tests that load real weights (too slow for the ticket loop); no tests (report numbers would be untrusted).
- Reversibility: cheap
- To change: add a slow marker suite later.
- Decided by: AI

## D-017 — Engine decision rule

- Decision: The report recommends an Engine using, in order: (1) M1 must-haves: cancel that returns within ~5 s without a process kill (or a kill-and-reload cost the UI can live with), per-Stage progress, and the ability to run planning alone and re-synthesize saved Semantic tokens (needed for #5/#7). (2) Speed and peak memory on the `song` case. (3) Install friction for end users. (4) Project health (maintainers, release cadence). Also note hybrid options (e.g. mlx-Yue on Mac, audio.cpp for NVIDIA). The recommendation is a proposal; the user confirms it after reading the report, before M1.
- Why: Makes the pick traceable to measured facts, with UI-critical capabilities weighted above raw speed.
- Rejected: speed-first ranking (a fast engine that can't cancel or stop after planning blocks core features).
- Reversibility: cheap (no product code depends on it yet)
- To change: the user overrides in PLAN.md.
- Decided by: AI

## D-018 — Repository setup

- Decision: `git init` the songloom repo with a `main` branch and a `.gitignore` covering `.venv/`, `spike/runs/`, `spike/vendor/`, `spike/models/`, `spike/listen/`, `*.npy`, `*.flac`, `*.wav`, `*.gguf`, `*.safetensors`. Commit the existing planning files as the initial commit, then work on `feat/m0-engine-spike`.
- Why: `run-tickets` needs git for branches and per-ticket commits; weights and audio must never be committed.
- Rejected: none.
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-019 — Proof of done

- Decision: Done when `docs/m0-report.md` is committed and (1) answers every M0 checkbox in PLAN.md with numbers traceable to `spike/results/*.json`; (2) gives an Engine recommendation per D-017; (3) lists local paths to two listening pairs (same seed twice; Draft vs Final); (4) PLAN.md's M0 checkboxes are ticked with a pointer to the report, and any plan items the findings change (e.g. #5 placement, memory defaults, Engine) are flagged for the user rather than silently rewritten.
- Why: Restates goal.md's proof in checkable terms.
- Rejected: none.
- Reversibility: cheap
- To change: n/a
- Decided by: AI

## D-020 — Test seams confirmed for the spec (to-spec seam check)

- Decision: One seam, the `SpikeEngine` protocol with a `FakeEngine` (D-016). Plus two leaf checks against fixed inputs: audio.cpp `--log` parsing against captured log text, and the memory sampler against a child process with a known allocation.
- Why: Highest possible seam; the leaf checks cover the two pieces a fake engine can't exercise.
- Rejected: per-module unit tests for runner internals (couples tests to structure).
- Reversibility: cheap
- To change: add seams in a ticket.
- Decided by: AI
