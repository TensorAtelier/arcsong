# 01 — Harness skeleton and mlx-Yue doctor

**What to build:** A developer runs one command, the `doctor` measurement for the mlx-Yue Engine. It loads mlx-Yue (a git dependency pinned to `9253ed1`, weights read from a configurable path defaulting to `~/projects/mlx-Yue/models`), renders the `clip` case, and writes a results JSON with outcome, environment snapshot and total time, plus the audio under the gitignored runs directory. This ticket establishes the whole harness spine that later tickets extend: the `uv` project (Python 3.12, pytest, ruff), the `spike` package and CLI, the `SpikeEngine` protocol with `Unsupported`, a `FakeEngine`, the fresh-child-process runner (resume/skip existing results unless `--force`; crash/OOM/Unsupported recorded as the outcome), the results schema, the environment snapshot (machine, OS, Engine version/commit, running Ollama/LM Studio/ComfyUI processes), and the `clip` and `song` case definitions.

Read first: `.scratch/m0-engine-spike/spec.md`, and ledger entries D-004, D-005, D-006, D-007, D-015, D-016 and D-020 in `.scratch/m0-engine-spike/DECISIONS.md`; `CONTEXT.md` for vocabulary. Engine facts are at the top of DECISIONS.md.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `uv sync` then `uv run spike doctor --engine mlx` produces a playable `clip` audio file under the runs directory and a results JSON with `outcome: ok` in the results directory
- [ ] Rerunning the same command skips the case because results exist; `--force` reruns it
- [ ] Tests through `FakeEngine` cover: results schema, resume/skip, and a crashing / Unsupported engine recorded as that outcome while the command exits cleanly
- [ ] mlx-Yue is pinned by git commit in `pyproject.toml`; no weights, audio or tensors are tracked by git
- [ ] `uv run pytest -q` and `uv run ruff check .` pass
