# score-zero-notes — plan

**Goal:** the Score page no longer shows a bare "0 vocal notes" that reads like a bug.
**Finding:** not a counting bug. Song 5 (seed 4243, lyrics given, mode full) has a Score whose
`V: Vocal` voice is rests in all 57 bars — `z16` with chord symbols — while `V: Ins` carries 268
notes. The model planned no vocal melody for that take; the summary counts it correctly.
**Not yet:** flagging such takes in Compare or the Library (needs the Score per take, an extra
request each); re-planning automatically.
**Stack / interfaces:** `web/src/ScoreView.tsx` only; the report already carries the counts.
**Proof of done:** song 5's Score page says the take has no planned vocal melody although it has
lyrics, and what to do; songs with vocal notes look as before; an instrumental with no lyrics
says nothing.

## Tickets

- [x] 01 — Notice on the Score page when the request has sung lyrics and the Vocal voice has no sounding notes: what it means, and "render another seed" as the remedy; the facts chip reads "no vocal melody" instead of "0 vocal notes". Check on song 5 and song 3 in the debug Chrome.

## Notes

- Sung lyrics = any non-empty line that isn't a `[Section]` tag, the same rule `db.default_title` uses.
