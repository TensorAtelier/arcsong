# sketch-ready-link — report

Found by release QA (cycle 1, journey 2): once a sketch's last take finished, Create offered no way
to compare it.

## Tickets

- 01 — the latest sketch keeps its Compare link when nothing is rendering: `7d937f1`
- QA fix — the idle fallback is the newest sketch with a finished take (all-cancelled sketches skipped).

## QA verdict (goal mode)

GOAL VERDICT: MET — all six cases traced (render unchanged; idle link for the newest sketch; singles,
Finals, Scores and covers ignored; no link at 0 done; cancelled/failed not counted; deletes handled).
Defect 1 (cosmetic): an all-cancelled newest sketch showed "0 of M done" and no link — fixed.
Risks: the idle link stays until a newer sketch; no automated QueuePanel test (release-qa-script,
next cycle, covers journey 2). Release QA journey 2 passed with the link in place.

## Parked

None.

## Decisions made for you

- Fixed in this cycle rather than shipped around: a core journey (sketch → compare) dead-ended.
