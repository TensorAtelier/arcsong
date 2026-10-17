# readme-v0-2 — report

## Tickets

- 01 — screenshots of the redesign from real songs (headless Chrome, 1440 px at 1.5×, dark): `42a1432`
- 02 — README for v0.2.0: status, feature tour, "Your first song", swap-stop troubleshooting: `b870141`
- 03 — failure cards stay dismissed (localStorage) and age out after a day — found while taking the Create shot: `1c16a68`
- QA fixes: AC refusal mapped to advice and quoted; keys 1–8; "artwork"; changelog line — the commit after `b870141`'s successors.

## QA verdict (goal mode, summary)

GOAL VERDICT: PARTIAL — 01 delivered (all six PNGs current, tracked, referenced); 03 delivered
(try/catch storage, 200-id cap, seconds vs seconds); 02 partial: a troubleshooting entry quoted a
message the app never shows, `1`–`9` unreachable (max 8 takes), "cover" used for the seed artwork
against the glossary. Drift: README says v0.2.0 ahead of pyproject (bumped at tag time); changelog
lacked ticket 03. Risks: setup.png shows a local path with the username; the 24 h cutoff only
recomputes on re-render. Verification: tsc clean, ruff clean, pytest 270 passed, bundle current.

All three defects and the changelog drift are fixed. Accepted: the version bump happens at tag
time (docs/release.md); setup.png's path shows the owner's username, already public as the author.

## Parked

None.

## Decisions made for you

- Dark theme for every shot (the default look; reads on GitHub's light and dark pages).
- Ticket 03 added mid-feature: shipping a README whose first screenshot shows stale error cards
  would have advertised a defect.
- The AC refusal mapped in the engine rather than reworded in the README: the user sees it in the app.
