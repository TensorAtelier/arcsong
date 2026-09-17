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
- Commit: COMMIT07
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
