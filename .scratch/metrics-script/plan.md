# metrics-script — plan

**Goal:** one command records today's public numbers in `docs/product/metrics.md`, so the PM's measure step is mechanical and GitHub's 14-day traffic window is never lost.
**Not yet:** scheduling it (a cron or `project-pulse` hook); referrer history.
**Stack / interfaces:** `scripts/metrics.py`, stdlib only, reading through the `gh` CLI; run as `uv run python scripts/metrics.py [--note TEXT] [--dry-run]`.
**Proof of done:** running it prints the row and writes it into the Snapshots table, replacing today's row if one exists; a test covers the table edit without `gh`.

## Tickets

- [x] 01 — Snapshot row from `gh api`: stars, unique cloners, unique views, release downloads; `--dry-run` prints it; check by running it.
- [x] 02 — Write the row into `metrics.md`: append, or replace today's row; keeps the note column; unit test on a sample table.

## Notes

- stdlib + `gh` only, so it runs anywhere the owner's `gh` login does; not part of the wheel (not under `arcsong/`).
- Same-day reruns replace the row rather than add one: one snapshot per day.
