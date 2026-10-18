# lyrics-help — plan

**Goal:** under Create's Lyrics box, say what YuE2 is likely to misread and roughly how long the
song will be (owner's question about "strictly formatted lyrics"; PLAN #8 length estimate).
**Not yet:** the same notes in Cover (a cover's length follows the recording); fixing lyrics
automatically; a server-side check.
**Stack / interfaces:** `web/src/lyrics.ts` (pure: notes + estimate), `CreateForm.tsx`, `style.css`.
**Proof of done:** good lyrics → no notes and an estimate; missing labels, a missing blank line, a
"(guitar solo)" line, an unknown label, a very long line → one note each with its line; empty
lyrics → "Instrumental: the model picks the length"; nothing blocks submitting.

## Tickets

- [x] 01 — `lyrics.ts` (notes, sung lines, estimate fitted on real renders) and the UI under Lyrics; checked in the browser.

## Notes

- Advice, never a blocker: YuE2 will render whatever is there.
- Estimate: 40 s + 3.8 s per sung line, ±25% (fitted 2026-10-17 on 6 library songs + X-001's two renders; the vocal-less take is the outlier no lyric-based estimate can predict).
