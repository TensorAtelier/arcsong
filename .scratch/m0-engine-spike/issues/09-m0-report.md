# 09 — M0 report and Engine recommendation

**What to build:** `docs/m0-report.md`, generated from the results directory by a `report` command (tables filled from the JSON), with the interpretation written in. It must answer every M0 checkbox in PLAN.md with numbers traceable to named results files: Engine choice, per-Stage timing split, cancellation, Draft→Final, timing + peak memory (bf16 vs 8-bit, 8 vs 32 steps), stale resource-file hygiene, model download, artifact sizes, seed reproducibility. It gives an Engine recommendation by applying the ledger's decision rule (D-017) step by step, and mentions hybrid options. It lists the local paths of the listening pairs, with what to listen for. Then tick PLAN.md's M0 checkboxes with a pointer to the report. Add a short "Findings that affect the plan" section to the report that flags which PLAN.md items should change (e.g. #5 placement, memory-aware defaults, minimum RAM, Engine choice, library cleanup) without rewriting those PLAN.md sections.

Read first: spec, ledger D-017 and D-019; `CONTEXT.md`; every file in the results directory; PLAN.md.

**Blocked by:** 02, 04, 05, 06, 07, 08

**Status:** ready-for-agent

- [ ] `uv run spike report` regenerates the report's tables from the results files; a test with fixture results checks every M0 question gets a section and missing results are shown as "not measured"
- [ ] Every number in the report appears in, and cites, a results file
- [ ] The recommendation walks D-017's criteria in order and states the Engine
- [ ] PLAN.md's M0 checkboxes are ticked with a link to the report; no other PLAN.md section is rewritten
- [ ] `uv run pytest -q` and `uv run ruff check .` pass

## Comments

**Driver, after ticket 02 (from QA):** (1) The 250 ms sampled `peak_footprint_bytes` reads 0.02–0.66 GiB below macOS's `lifetime_peak_footprint_bytes`; quote the lifetime figure, or both. (2) `spike/results/doctor-mlx-clip-bf16-32.json` (ticket 01) uses the older per-run shape (no `run`/`outcome`/memory fields) and `SCHEMA_VERSION` was not bumped; the report generator must tolerate both shapes, or doctor results can be regenerated. (3) LM Studio and ComfyUI were running throughout the mlx timing matrix (`env.model_servers`); run-to-run synthesis time varied up to ~25%. Say so next to the timing numbers.
