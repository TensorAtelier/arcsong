# M0 engine spike — run status

- Spec: .scratch/m0-engine-spike/spec.md
- Branch: feat/m0-engine-spike (base ded28b4)
- Verification: 
  uv run pytest -q
  uv run ruff check .
- Started: 2026-09-16
- Baseline: empty — no project code exists before ticket 01

## 01 — Harness skeleton and mlx-Yue doctor

- Result: done
- Commit: b48a947
- QA rounds: 1
- Verification:
  ```
  $ uv run pytest -q
  ..........                                                               [100%]
  10 passed in 1.32s
  $ uv run ruff check .
  All checks passed!
  $ uv run spike doctor --engine mlx --force
  ok doctor-mlx-clip-bf16-32 in 29.7s -> /Users/julian/projects/songloom/spike/results/doctor-mlx-clip-bf16-32.json
  ```
- QA verdict: PASS — a real `--force` render produced a readable 16.0 s 48 kHz stereo FLAC and `outcome: ok`; a plain rerun skipped; a missing weights path was recorded as `failed` with exit 0; the FakeEngine tests use a real SIGKILL and abort.

## 02 — mlx-Yue Stage timing, peak memory and artifact sizes

- Result: done
- Commit: 4c27e25
- QA rounds: 1
- Verification:
  ```
  $ uv run pytest -q
  ...................                                                      [100%]
  19 passed in 9.65s
  $ uv run ruff check .
  All checks passed!
  ```
- QA verdict: PASS — all four real results files checked field by field against the run folders on disk (Stage sums, serial start times, footprint vs MLX peak, file lists); the fake-engine matrix plus resume was exercised; the timeout and orphan-child tests were run 3×.

## 03 — audio.cpp setup and doctor

- Result: done
- Commit: 61b4337
- QA rounds: 1
- Verification:
  ```
  $ uv run pytest -q
  38 passed in 15.65s
  $ uv run ruff check .
  All checks passed!
  $ uv run spike setup
  downloaded: nothing (all files in place)
  $ uv run spike doctor --engine audiocpp --force
  ok doctor-audiocpp-clip-bf16-32 in 29.9s -> /Users/julian/projects/songloom/spike/results/doctor-audiocpp-clip-bf16-32.json
  ```
- QA verdict: PASS — setup reran with nothing to fetch; a real sha256 mismatch through the CLI exited 1 with nothing left behind; the real GPU doctor made a non-silent 16 s WAV with `outcome: ok`, version 0.8.0; all pins cross-checked against the GitHub digest and the HF LFS hashes.

## 04 — audio.cpp Stage timing, peak memory and artifact sizes

- Result: done
- Commit: d1cf6c8
- QA rounds: 1
- Verification:
  ```
  $ uv run pytest -q
  ..........................................                               [100%]
  42 passed in 21.18s
  $ uv run ruff check .
  All checks passed!
  ```
- QA verdict: PASS — the 4 audio.cpp results files were checked field by field against the mlx results, the files on disk, the raw log durations and `pmset -g log`. All 8 runs are ok, no kept run overlaps the 17:38–17:44 sleep, and footprints include the CLI (6.26 / 8.84 GiB).

## 05 — Cancellation per Stage, both Engines

- Result: done
- Commit: baaf447
- QA rounds: 2
- Verification:
  ```
  $ uv run pytest -q
  58 passed in 59.88s
  $ uv run ruff check .
  All checks passed!
  $ caffeinate -ims uv run spike cancel --engine mlx --stages synthesis --results-dir …/qa05r2/results --runs-dir …/qa05r2/runs --timeout 600
  ok cancel-mlx-clip-8bit-8-synthesis in 24.9s
  ```
- QA verdict: PASS — all 8 results use a 1.0 s delay (measured request gap 1.002–1.006 s). A real mlx synthesis cancel reproduced the committed result: 0.112 s latency, nothing left on disk, reuse in the same process without a reload. Reuse and reload are measured through lyra's load events.
  (Round 1: FAIL — planning cancelled at 5 s with no recorded reason; fixed by rerunning at 1 s and putting the delay into params.)

## 06 — Seed reproducibility, both Engines

- Result: done
- Commit: 503771e
- QA rounds: 2
- Verification:
  ```
  $ uv run pytest -q
  77 passed in 65.68s (0:01:05)
  $ uv run ruff check .
  All checks passed!
  $ caffeinate -ims uv run spike repro --engine mlx --results-dir qa06r2/results --runs-dir qa06r2/runs --listen-dir qa06r2/listen
  ok repro-mlx-clip-8bit-32-planned in 102.0s -> .../scratchpad/qa06r2/results/repro-mlx-clip-8bit-32-planned.json
  ```
- QA verdict: PASS — hashes of real Take files match the JSON; the warm pair shares a pid and the fresh Take has another; the comparators catch a 1-token / 1e-6 / 1-LSB change on real mlx and audio.cpp outputs; audio.cpp's uncompared Stages and its cold-per-Take nature are recorded; the listening pairs match their sources.
  (Round 1: FAIL — audio.cpp cold runs were labelled a warm process; fixed with `takes_reuse_loaded_model` / `warm_process` plus a note.)

## 07 — Draft→Final, both Engines

- Result: done
- Commit: 0079aed
- QA rounds: 2
- Verification:
  ```
  $ uv run pytest -q
  91 passed in 72.43s (0:01:12)
  $ uv run ruff check .
  All checks passed!
  $ uv run spike draft-final --engine {audiocpp,mlx} --results-dir <scratch copy> --runs-dir <scratch>/runs --listen-dir <scratch>/listen --resummarize
  unsupported draft-final-audiocpp-song-q8_0-8-32 re-summarized from recorded runs -> …
  ok draft-final-mlx-song-8bit-8-32 re-summarized from recorded runs -> …
  ```
- QA verdict: PASS — every number checked against the run dirs (numpy/soundfile, sha1, mtimes, CLI logs). mlx Final == direct-32 bit for bit and is a real re-synthesis (360 s, no planning or semantic generation); audio.cpp's Draft time excludes the probe, and the noise mismatch and same-seed workaround are explained; `--resummarize` reproduces the committed files exactly and runs nothing.
  (Round 1: FAIL — 4 defects in how audio.cpp's result was recorded; fixed without a GPU rerun.)

## 08 — Stale resource files and model download checks (mlx-Yue)

- Result: done
- Commit: 1b5dfbd
- QA rounds: 1
- Verification:
  ```
  $ uv run pytest -q
  100 passed in 85.99s (0:01:25)
  $ uv run ruff check .
  All checks passed!
  $ caffeinate -ims uv run spike hygiene --engine mlx --results-dir qa08/results --runs-dir qa08/runs
  ok hygiene-mlx-clip-8bit-8 in 63.2s
  $ caffeinate -ims uv run spike download --engine mlx --results-dir qa08/results --runs-dir qa08/runs
  ok download-mlx-weights in 22.8s
  ```
- QA verdict: PASS — both measurements re-run independently with matching results. Claims checked against the mlx-Yue 9253ed1 source and huggingface_hub 1.31.0; the VAE really came over the network; the temp dir was deleted; ~/projects/mlx-Yue/models was unchanged (path/size/mtime diff).

## 09 — M0 report and Engine recommendation

- Result: blocked
- Wip branch: wip/m0-engine-spike/09-m0-report (f9e22e3)
- QA rounds: 2
- Verification:
  ```
  $ uv run pytest -q
  110 passed in 86.29s (0:01:26)
  $ uv run ruff check .
  All checks passed!
  $ uv run spike report --out <scratch>/qa09r2/m0-report.md ; cmp with docs/m0-report.md
  IDENTICAL
  ```
- QA verdict: FAIL — 
  1. docs/m0-report.md:59, :285 — claims audio.cpp semantic generation logs nothing until it ends; the cited q8_0 log shows a KV-cache refill line mid-Stage.
  2. docs/m0-report.md:429–447 — missing caveat: the log parser clamps Stage starts after a sleep without flagging it (no kept result clamped).
  3. docs/m0-report.md:535 — Findings 1 says mlx-Yue is "confirmed"; D-017 makes it a proposal the user confirms.
  4. tests/test_m0_report_numbers.py — substring checks miss drift for 11 of 15 numbers that repeat in the prose.

## 09 — M0 report and Engine recommendation (unparked)

- Result: done
- Commit: 0ec12eb (fixes), merged in 96b4882
- QA rounds: 2 + fixed after the user's approval, without a third QA round
- Verification:
  ```
  $ uv run pytest -q
  110 passed in 85.37s (0:01:25)
  $ uv run ruff check .
  All checks passed!
  $ uv run spike report (twice) ; cmp with the prior copy
  IDENTICAL
  ```
- Note: the fixes were applied by the driver directly, with no fresh QA pass. Mutation check: editing one prose occurrence of 223.2 fails `test_draft_final_arithmetic_matches_results`.

## 10 — Progress within a Stage, both Engines

- Result: blocked
- Wip branch: wip/m0-engine-spike/10-within-stage-progress (d191ac6)
- QA rounds: 2
- Verification:
  ```
  $ uv run pytest -q
  135 passed in 95.37s (0:01:35)
  $ uv run ruff check .
  All checks passed!
  $ uv run spike report --out <scratch copy of docs/m0-report.md>   (twice) ; cmp
  BYTE-STABLE
  ```
- QA verdict: FAIL —
  1. PLAN.md:120 and docs/m0-report.md (must-have row, mlx synthesis/decoding prose, "What M1 can use", finding 9) — mlx-Yue decoding's results verdict `uneven_percent` renders as "stepped %", contradicting the note/prose that call it unusable; the PLAN.md note's token-count claim doesn't name mlx-Yue.
  2. tests/test_progress.py:194–195 — the docstring cites numbers from a superseded run as coming from the committed results file.
