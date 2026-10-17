# style-dice — plan

**Goal (owner):** remove the "Add + lo-fi soul …" chips under Style (too much space); a random
button next to the Style input that fills in a random style.
**Not yet:** random lyrics; a style library or recent styles.
**Stack / interfaces:** `web/src/CreateForm.tsx` (+ a small `styles.ts` vocabulary), `style.css`.
**Proof of done:** no chip row under Style; a dice button inside the Style row replaces the
field with a fresh tag-form style each click; the field stays editable; Plan a melody gets it too.

## Tickets

- [x] 01 — Remove the chips; dice button beside Style generating "<language>, <genre>, <mood>, <2 instruments>, <voice>" from curated pools; check in the browser.

## Notes

- Tag form, comma-separated, as YuE2's own example (`City Pop, upbeat, danceable, groovy bass, …`).
- Starts with "English" — Arcsong's existing examples do; the dice keeps English so the lyrics box
  (in English) and the voice match. Pools are curated pairs that make sense together (a genre
  carries instruments that fit it), not independent picks, so a roll doesn't read like noise.
- Replaces the field rather than appending: a roll is a suggestion, editable afterwards.
