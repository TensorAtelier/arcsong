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
- Commit: (this commit — see git log for `feat(01)`)
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
