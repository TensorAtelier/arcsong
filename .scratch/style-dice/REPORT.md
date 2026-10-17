# style-dice — report

Owner request (cycle 2): remove the style suggestion chips (too much space); a random button
beside Style.

## Tickets

- 01 — chips removed; a dice beside Style rolls a curated tag-form style: `28c120a`

## QA verdict (goal mode)

GOAL VERDICT: MET — chips, `addToStyle` and their CSS gone; the dice is `type=button`, labelled,
replaces the field, on Write and Plan; Cover untouched. 200,000 rolls: 0 malformed, all 3,456
combinations reached, never the same instrument twice. Defects: none. Risks: a roll replaces what
was typed (by design); every roll starts with "English"; a redundant `.seed-row button.dice` rule
(removed).

## Parked

None.

## Decisions made for you

- Replace, not append: a roll is a suggestion; the field stays editable.
- Curated genre → mood/instrument pools, not independent picks, so a roll reads like a song.
