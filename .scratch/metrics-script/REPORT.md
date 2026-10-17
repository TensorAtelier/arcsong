# metrics-script — report

## Tickets

- 01 — snapshot row from `gh api`: `1332b82`
- 02 — write the row into `metrics.md`, replacing a same-day row: `8131522`
- QA fixes: a note-less rerun keeps the day's note; UTF-8 and `\n` on write (Windows); `|` escaped in notes — see the commit after this report's.

## QA verdict (goal mode, verbatim summary)

GOAL VERDICT: PARTIAL — "The command works and the proof of done holds." Stories: 01 delivered
(numbers checked against `gh api`; dry run writes nothing); 02 partial — a same-day rerun
without `--note` erased the note already in today's row. Risks: `|` in a note breaks the table;
no `encoding=` on Windows. Drift: the baseline cell `1 (v0.1.0 wheel)` normalised to `1`.
Verification: dry run, `tests/test_metrics_script.py` 2 passed, ruff clean, full suite 268 passed.

All three defects are fixed with tests (4 passed). The drift is accepted: the column is numeric.

## Parked

None.

## Decisions made for you

- Same-day reruns replace the row (one snapshot per day); a rerun with no note keeps the old note.
- stdlib + `gh` only, outside the wheel (`scripts/`), run by the owner — not scheduled yet ("Not yet").
