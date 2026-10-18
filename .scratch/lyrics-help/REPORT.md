# lyrics-help — report

Owner question (2026-10-17): what does "strictly formatted lyrics" mean for YuE2 — answered in
chat, then built as advice under Create's Lyrics box (also on Plan, which shares the field).

## Tickets

- 01 — `web/src/lyrics.ts` (notes, sung lines, length estimate) and the UI under Lyrics: `ab3b1b8`
- QA fixes — the commit after.

## QA verdict (goal mode)

GOAL VERDICT: MET — all eight proof-of-done items delivered; 21 edge cases (CRLF, "[Verse 2]",
"[Pre-Chorus]", lowercase, trailing spaces, consecutive labels, inline parentheses) give no false
positives; estimate never "0–…" and monotonic over 1–80 lines; nothing blocks submit. Defects
(minor): the "before the first label" note always said Line 1; seconds bounds rounded inward;
a comment named the wrong brackets; labels-only lyrics called "Empty". Risks: whole-line ad-libs
like "(ooh ooh)" got instrumental advice; real-world labels like "[Final Chorus]" read as unknown;
a changelog bullet for CI rides along.

Fixed: all four defects and the ad-lib wording ("If it means an instrumental part…"). Kept: the
label list (YuE2's example plus Hook/Post-Chorus/Break); unknown labels are only advised about.

## Parked

None.

## Decisions made for you

- Advice only, never a blocker: the model renders whatever is in the box.
- Estimate shown as a range (±25%), fitted on eight real renders; the vocal-less take is the
  known outlier no lyric-based estimate can predict.
