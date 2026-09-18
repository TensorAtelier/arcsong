# M0 engine spike — run report

- Spec: `.scratch/m0-engine-spike/spec.md` · Ledger: `DECISIONS.md` · Per-ticket evidence: `STATUS.md`
- Branch: `feat/m0-engine-spike` (base `ea4cfbc`) · Mode: auto · Run: 2026-09-16 → 2026-09-17

## Run summary

| Ticket | Result | Commit / wip branch | QA rounds |
|---|---|---|---|
| 01 Harness skeleton and mlx-Yue doctor | done | `294d9f6` | 1 |
| 02 mlx-Yue Stage timing, peak memory, artifact sizes | done | `6038085` | 1 |
| 03 audio.cpp setup and doctor | done | `94affee` | 1 |
| 04 audio.cpp Stage timing, peak memory, artifact sizes | done | `2a1a631` | 1 |
| 05 Cancellation per Stage, both Engines | done | `1742689` | 2 |
| 06 Seed reproducibility, both Engines | done | `2b6c657` | 2 |
| 07 Draft→Final, both Engines | done | `bc85cff` | 2 |
| 08 Stale resource files and download checks (mlx-Yue) | done | `46a41ca` | 1 |
| 09 M0 report and Engine recommendation | done (unparked 2026-09-17) | `c2a1fb8`, merged `5b6e5f0` | 2 + fixes |
| 10 Progress within a Stage, both Engines | done (unparked 2026-09-17) | `8d21b5f`, merged `6cceba4` | 2 + fixes |

## Goal review (verbatim)

```
GOAL VERDICT: PARTIAL

Verification on `feat/m0-engine-spike` at 6a583e3 (working tree clean):
$ uv run pytest -q
100 passed in 86.40s (0:01:26)
$ uv run ruff check .
All checks passed!

The measurement side is done and the evidence holds up. The branch can't deliver the goal's proof of done: there's no `docs/m0-report.md`, no recommendation and no PLAN.md ticks. On top of that, one M0 question named in the Problem Statement was never measured: progress within a Stage.

STORIES:
- 1. delivered — `uv run spike setup` syncs the pinned mlx-yue git dependency (9253ed1 in `pyproject.toml`) and downloads audio.cpp v0.8.0 with sha256 checks (`spike/audiocpp_pins.json`, `tests/test_audiocpp_setup.py`, including the mismatch path).
- 2. delivered — `DEFAULT_MODELS_DIR=~/projects/mlx-Yue/models` with `--mlx-models` / `SPIKE_MLX_MODELS` (`spike/mlx_engine.py`, `spike/cli.py`). The results record commit 9253ed13….
- 3. delivered — `doctor-mlx-clip-bf16-32.json` and `doctor-audiocpp-clip-bf16-32.json` are both ok. The mlx file uses the older per-run shape (its run has no `outcome` or memory fields).
- 4. delivered — `SpikeEngine` protocol in `spike/engine.py`. Both adapters write identical timing fields (`test_timing_results_match_the_other_engines_field_for_field`).
- 5. delivered — audio.cpp's Stage methods raise `Unsupported` (`test_stage_operations_are_recorded_as_unsupported`). `draft-final-audiocpp-…json` has outcome `unsupported`, with the fallback cost.
- 6. delivered — every `timing-*.json` run has `stage_seconds` for the 4 Stages plus `model_load_seconds`.
- 7. delivered — 8 timing files: mlx bf16/8bit and audio.cpp bf16/q8_0, each at 8 and 32 steps.
- 8. delivered — every timing file has 2 ok runs.
- 9. delivered — `peak_footprint_bytes` and `lifetime_peak_footprint_bytes` from the same sampler for both Engines. It includes child processes (`test_sampler_counts_the_footprint_of_processes_the_watched_process_launches`), and MLX's own peak is recorded alongside.
- 10. delivered — `env` holds the machine (Mac17,9, M5 Pro, 64 GiB), OS 26.4.1, Engine name/version/commit and `model_servers`. The baseline memory snapshot D-008 asks for is missing (see DRIFT).
- 11. delivered — 8 `cancel-*.json` files, one per Stage per Engine. mlx latency is 0.002–0.129 s. audio.cpp adds `kill_to_exit_seconds`.
- 12. delivered — `reuse` shows a full clip run in the same process with `reloaded: false` (mlx). For audio.cpp it shows the next run's reload cost.
- 13. delivered — `leftover_files` / `leftover_looks_complete`: mlx leaves nothing; audio.cpp leaves `audiocpp.log` and `score.abc`, and neither looks complete.
- 14. delivered — mlx: Score, Semantic tokens, Latents and audio are identical warm-vs-warm and warm-vs-fresh. audio.cpp: audio is bit-identical, but the other outputs weren't compared because v0.8.0 doesn't export them, and it has no warm process. Both limits are recorded as findings, not hidden.
- 15. delivered — `spike/listen/repro-{mlx,audiocpp}-…/{warm,fresh}-take-1.flac` exist on disk.
- 16. delivered — mlx: the Final is a real re-synthesis and bit-identical to the direct 32-step render. audio.cpp: `unsupported`, with a same-seed re-run as the workaround.
- 17. delivered — mlx `timing`: Draft 223.2 s, Final 360.8 s, direct 485.5 s. audio.cpp's `final_saving_seconds` of 4.1 s is run-to-run jitter, not a saving (flagged for the report).
- 18. delivered — `spike/listen/draft-final-{mlx,audiocpp}-…/draft-8.flac` and `final-32.flac` exist.
- 19. delivered — `hygiene-mlx-clip-8bit-8.json`: the staged API needs no cleanup; the CLI path needs `take.resources.jsonl` removed. Not covered: a kill while the Take is being saved.
- 20. delivered — `download-mlx-weights.json` lists the metadata files, the verification failure and a fix that works. Only the small files plus the VAE were really downloaded; the large weights were cloned locally.
- 21. delivered — each timing run lists every file with its size, plus `audio_bytes` and `files_total_bytes`. mlx: FLAC 40 MB against about 2.4 MB of `.npy` files.
- 22. delivered — `test_a_failing_run_is_recorded_and_the_matrix_continues`, `test_a_run_exceeding_the_timeout_is_killed_and_recorded_as_failed`, plus the SIGKILL→`oom` mapping in `spike/runner.py`.
- 23. delivered — `test_rerunning_the_matrix_skips_cases_whose_results_exist` and skip tests for doctor, cancel and repro.
- 24. missing — no `docs/m0-report.md` and no `report` command on the branch.
- 25. missing — no Engine recommendation on the branch.
- 26. missing — PLAN.md is unchanged on the branch; every M0 box is still `[ ]`.
- 27. partial — `SpikeEngine` covers PLAN.md's plan/render/resynthesize at Stage level (`run`, `render_final`). It doesn't mirror `doctor()` or `ensure_models(progress)`. It also has no progress hook within a Stage: only start/end/enter events. That hook is exactly what M1's SSE progress needs to build on.

How close the parked work (f9e22e3) is to stories 24–26: close. The report is generated byte-identically, the D-017 steps and hybrid options are there, the listening paths are listed, and PLAN.md changes only inside M0. The 4 open defects are three one-line text fixes and one test tightening. One more thing I'd add as a fifth: PLAN.md ticks the "Per-stage progress" checkbox with a note that the callback rate "was not measured". Ticking an unanswered question overstates it.

The branch is based on 1b5dfbd. The only later branch commit (6a583e3) touches just `.scratch/`, so merging would be trivial.

Does the branch solve the Problem Statement? Not yet. The raw evidence answers most questions:
- Cancel: yes on both Engines, well under 1 s.
- Seed reproducibility: yes, bit-identical on mlx.
- Draft→Final: works on mlx; Unsupported on audio.cpp v0.8.0.
- Memory: about 10.5 GiB mlx, about 6.3 GiB audio.cpp q8_0.
- Library size: FLAC dominates.

But the developer can't decide on the M1 Engine from the branch: there's no report or recommendation, and they'd have to read 26 JSON files. Progress within a Stage is unanswered on either Engine, although the Problem Statement ("seeing progress per Stage") and PLAN.md's M0 checkbox ("what callbacks fire, how often, map to a % bar") both ask for it. The spec's user stories dropped that question, so no ticket covered it.

DRIFT:
- Spec vs PLAN.md: no user story covers PLAN.md's "Per-stage progress" checkbox. The spec says `MlxYueEngine` uses `on_token`, but nothing under `spike/` calls it (grep for `on_token` finds nothing). Callback rate within a Stage was never recorded.
- D-008: "The results file records machine, OS, engine version and a baseline memory snapshot." `spike/env.py` `snapshot()` records model-server RSS but no baseline system memory, so readers can't tell how much memory was taken before a run.
- D-019 / goal proof of done: not met on this branch (stories 24–26).
- D-017: on the parked branch only, `docs/m0-report.md:535` calls mlx-Yue "confirmed" instead of proposed. The feature branch doesn't contradict D-017.
- Spec "Further Notes" says avoid running other model servers alongside. Every results file has LM Studio and ComfyUI in `env.model_servers`. That is recorded and allowed by D-015, but mlx bf16/32 varies from 649.8 s to 497.9 s between runs.
- Out of Scope: nothing crept in. No server, database, queue or frontend code; no Engine source patched (no monkeypatching); the audio.cpp noise probe is harness work, not tuning.

RISKS (ranked):
1. M1 builds its progress throttle and % bar without data. mlx `on_token` and synthesis-step callback rates are unknown. From its logs, audio.cpp prints nothing useful for progress during synthesis, its longest Stage.
2. Timing comparisons are skewed by other model servers, sleep and battery (audio.cpp bf16/8 ran on battery per the ticket comments). Songs also differ in length (mlx 172–185 s, audio.cpp 204–216 s), so raw totals mislead. None of this is written down on the branch, only in the ticket comments.
3. Worker cleanup is unmeasured for a kill while the Take is being saved, so the library could show a partial Take as complete.
4. `spike/runner.py` `_outcome_from_exit` labels any SIGKILL of a child `oom`, so a manual or external kill would be recorded as out-of-memory.
5. audio.cpp repro only proves identical audio across cold processes. Latents and Semantic tokens can't be checked with v0.8.0.

DEFECTS:
1. docs/m0-report.md (missing on branch) — no M0 report, recommendation or `spike report` command — `git show HEAD:docs/m0-report.md` fails; ticket 09 is parked on `wip/m0-engine-spike/09-m0-report` (f9e22e3) with 4 open QA defects — stories 24, 25; D-019
2. PLAN.md:109–127 — M0 checkboxes unticked, no pointer to a report — `git diff ded28b4...HEAD -- PLAN.md` is empty — story 26; D-019
3. spike/mlx_engine.py (whole adapter), spike/engine.py:20–33 — progress within a Stage is never measured: `on_token` is unused despite the spec's adapter description, and `StageEvent` carries only start/end/enter, so no results file records callback counts or rates — `grep -rn on_token spike/` finds nothing; PLAN.md M0 "Per-stage progress" checkbox — Problem Statement ("seeing progress per Stage"), story 27
4. spike/env.py:97–113 — no baseline memory snapshot in `env`, which D-008 requires — `snapshot()` returns only machine/os/python/engine/model_servers; check any `spike/results/*.json` `env` — D-008, story 10
5. f9e22e3:PLAN.md (parked) — the "Per-stage progress" checkbox is ticked `[x]` while its own note says callback rate within a Stage was not measured — `git show f9e22e3 -- PLAN.md` — story 26 (fix before merging the parked work)
```

## Parked tickets

*Update 2026-09-17: ticket 09 was unparked with the user's approval. All five defects below were fixed in `c2a1fb8` and merged (`5b6e5f0`). Stories 24–26 are now on the branch. Within-Stage progress (goal review defect 3) continues as ticket 10.*

- **09 — M0 report and Engine recommendation.** Branch `wip/m0-engine-spike/09-m0-report` (`5d11e34`). It failed QA round 2 on four small defects: (1) the report says audio.cpp semantic generation logs nothing until it ends, but q8_0 logs show one mid-Stage KV-cache refill line; (2) the "parser clamps Stage starts after sleep" caveat is missing; (3) Findings 1 says mlx-Yue is "confirmed", which should say recommended (D-017); (4) the prose-number test misses drift for 11 of 15 repeated numbers. The goal review adds (5): PLAN.md ticks "Per-stage progress" although within-Stage rate wasn't measured. Everything else in the report passed a line-by-line QA recheck against the results.

## Ticket 10 (added 2026-09-17)

Unparked with the user's approval: both defects below were fixed without GPU runs (`8d21b5f`) and merged (`6cceba4`). mlx-Yue decoding is now verdict `coarse_percent` (too few updates for a bar). All M0 checkboxes in PLAN.md are ticked.

It was parked after two QA rounds. The measurement holds up: QA rebuilt the analysis from the raw timelines and matched both results files. What M1 can use for a progress bar:
- **mlx-Yue:** `on_token` in planning and semantic generation gives a steady running count with no total, up to 71 events/s, which the SSE throttle must absorb. Synthesis and decoding have no public callback; yue2's `N/total` lines on stderr give a stepped % (at most one line per 5 s through a pipe; synthesis starts 15.3 s in, and decoding has only 3 updates).
- **audio.cpp:** nothing usable inside any Stage. Synthesis is silent for ~131 s, and the decoding chunk total only appears at the end.

Open defects: mlx-Yue decoding's verdict ('stepped %') contradicts the PLAN.md note and prose ('too coarse'); a test docstring cites numbers from a superseded run. Both can be fixed without GPU runs.

## Look here first

1. **The Engine decision and the report are parked, and the decision is yours.** The parked report recommends **mlx-Yue**. audio.cpp v0.8.0 fails D-017's must-haves: it can't run planning alone, re-synthesize saved Semantic tokens, or export a Score. Its upstream PR #561 adds Score export after a full run only. Fix the 5 defects on the wip branch and merge it, then confirm or override the recommendation.
2. **Progress within a Stage was never measured.** This was a spec gap: PLAN.md asked, but no user story or ticket covered it. mlx-Yue's `on_token` rate and synthesis-step progress are unknown, and audio.cpp logs nothing during synthesis, its longest Stage (~600 s at 32 steps). M1's progress bar and throttle design depend on this. It's a short follow-up ticket (clip-sized runs).
3. **The timing comparison has soft spots.** LM Studio/ComfyUI ran throughout, one audio.cpp case ran on battery, and the songs differ in length. `env` also lacks the baseline memory snapshot D-008 asked for, and the runner labels any SIGKILL as `oom`. The mlx-Yue memory (~10.5 GiB) and the cancel/repro/Draft→Final findings don't depend on these conditions; the cross-Engine speed ratio does.

## Decisions made for you

Ranked costly-and-surprising first. One line each; full entries in `DECISIONS.md`.

- **D-017** — Engine decision rule: UI must-haves (cancel, per-Stage progress, planning alone + re-synthesis) outrank speed and memory; the recommendation is a proposal for you to confirm.
- **D-005** — audio.cpp driven through its prebuilt CLI (whole runs, log-parsed Stages, cancel = kill), not the C ABI or server; its "unsupported" findings are about that surface at v0.8.0.
- **D-006** — mlx-Yue pinned as a git dependency at `9253ed1` reusing existing weights; audio.cpp as the pinned v0.8.0 release binary with sha256 plus GGUF weights from `audio-cpp/Yue2-3B-GGUF`.
- **D-018** — `git init` of songloom on `main`, work on `feat/m0-engine-spike`; weights, audio and tensors gitignored.
- **D-009** — Timing matrix: `song` × 2 precisions × 8/32 steps × 2 runs per Engine (~3 h GPU total).
- **D-012** — Draft→Final method: mlx re-synthesizes saved Semantic tokens + noise; audio.cpp tried a saved noise file, recorded as unsupported with a same-seed re-run as the workaround.
- **D-013** — Download check limited to small files + VAE (~530 MB); no full 10 GB re-download. Hygiene tested with kills mid-synthesis.
- **D-008** — Memory = external `ri_phys_footprint` sampling (process tree), each run in a fresh process; 2 runs per case.
- **D-007** — Two fixed cases: `clip` (upstream quickstart) and `song` (~3 min), identical inputs for both Engines. During the run, `clip` without its supplied Score was used where planning mattered.
- **D-010** — Cancel ~1 s into each Stage, then reuse in the same process; audio.cpp measured as kill-to-exit plus reload.
- **D-011** — Repro: 2 warm Takes + 1 fresh, compared Stage by Stage.
- **D-015** — Failures, OOM and Unsupported recorded as outcomes; resume skips existing results; other model servers warned about, not blocked.
- **D-016** — One test seam (`SpikeEngine` + `FakeEngine`); real-weight runs are commands whose committed JSON is the evidence.
- **D-020** — Seam check: `SpikeEngine`/`FakeEngine` plus leaf tests for log parsing and the memory sampler.
- **D-004** — Code in `spike/`, results JSON committed in `spike/results/`, audio in gitignored `spike/runs/` and `spike/listen/`, report at `docs/m0-report.md`.
- **D-014** — Record every file size per `song` Take.
- **D-019** — Proof of done: committed report answering every M0 box with cited numbers, recommendation, listening pairs, PLAN.md ticks.
- **D-001** — Scope = the M0 checklist only (no server/UI/queue). *Missed: the within-Stage progress rate from the M0 checklist was dropped when writing user stories.*
- **D-003** — Glossary terms added to `CONTEXT.md` (Take, Draft, Final, Stage, Score, …).
- **D-002** — Actors: you (decide the Engine, listen) and the future M1 adapter author.
