# score-zero-notes — report

## Finding

Not a counting bug. Song 5 (seed 4243, lyrics given, mode full) has a Score whose Vocal voice is
rests in all 57 bars while the Ins voice carries 268 notes: the model planned no vocal melody for
that take. The summary was right; the page just gave no reading of it.

## Tickets

- 01 — notice on the Score page and a "no vocal melody" chip: `692205f`

## QA verdict (goal mode)

GOAL VERDICT: MET — story 01 delivered (song 5 notice + chip; song 3 unchanged; notice follows the
live check, so writing notes into the Vocal voice clears it; no notice for instrumentals or
tag-only lyrics; null report safe). Drift: none. Defects: none. Risks: the remedy is advice with no
button; chip and notice vanish while an edit is invalid (as before). QA could not see the page;
the PM checked it in the browser (song 5 shows both, song 3 shows "35 vocal notes").

## Parked

None.

## Decisions made for you

- Explain rather than "fix": the Score is what the model planned; hiding or re-planning it would
  misreport the take.
- Flagging vocal-less takes in Compare and the Library waits (needs a Score request per take).
