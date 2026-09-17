# 05 — Cancellation per Stage, both Engines

**What to build:** The `cancel` measurement. For mlx-Yue, and for each Stage (planning, semantic generation, synthesis, decoding): start a Take (`clip`, or `song` when `clip` gets through a Stage in under ~2 s), request cancel once that Stage has run for ~1 s, and record the latency from the request until control returns. Then, in the same process, run a full `clip` Take and record whether it succeeds and whether a reload was needed. Record what the cancelled Take left on disk and whether anything looks like a complete Take. For audio.cpp: record kill-to-exit latency during each Stage it logs, the leftover files, and the load cost of the next run. Run it on this Mac for both Engines.

Read first: spec, ledger D-010, D-015; `CONTEXT.md`.

**Blocked by:** 01, 03

**Status:** done

- [x] Tests through `FakeEngine` (with scripted cancel responsiveness per Stage) cover latency calculation, the reuse check and the leftover-file check
- [x] Results JSON exists for both Engines, with per-Stage cancel latency, a reuse-after-cancel outcome and leftover files
- [x] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, after ticket 01:** the `clip` case (upstream quickstart request) already supplies a Score (`abc`) and caps semantic tokens at 400, so running it never exercises planning: no Score gets written. The `song` case has no `abc`, so planning runs. For any check that needs the planning Stage or compares a generated Score, use a variant of `clip` without `abc` (a short-lyrics request with planning mode `full`), or `song`. Keep `clip` itself unchanged: its doctor results already exist.

**QA round 1 (FAIL):** the planning cases were cancelled at 5 s instead of ~1 s, with no reason recorded; the stated reason did not reproduce. Fixed: both reran at 1 s, and a non-default delay is now part of the case params and file name.
