# 06 — Seed reproducibility, both Engines

**What to build:** The `repro` measurement. Run the `clip` case with one fixed seed three times per Engine: twice in one warm process and once in a fresh process. Compare the Score text (equal or not); Semantic tokens (equal or not; first differing index); Latents (max-abs difference); and audio (bit-identical, else max-abs difference and correlation). Report warm-vs-warm and warm-vs-fresh separately, and name the first Stage that diverges. For audio.cpp, compare only what the CLI outputs (Score if exported, audio). Copy one same-seed audio pair per Engine to the gitignored listening directory. Run on this Mac.

Read first: spec, ledger D-011; `CONTEXT.md`.

**Blocked by:** 01, 03

**Status:** ready-for-agent

- [ ] Tests through `FakeEngine` cover identical outputs, outputs perturbed in one Stage (the first diverging Stage is reported correctly), and the numeric comparisons
- [ ] Results JSON exists for both Engines with warm/warm and warm/fresh comparisons and the first diverging Stage (or "none")
- [ ] One same-seed listening pair per Engine exists, with paths recorded in the results
- [ ] `uv run pytest -q` and `uv run ruff check .` pass
