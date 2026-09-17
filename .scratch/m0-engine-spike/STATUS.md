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
- Commit: COMMIT04
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
