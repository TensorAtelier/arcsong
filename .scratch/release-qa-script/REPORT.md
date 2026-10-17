# release-qa-script — report

## Tickets

- 01 + 02 — `scripts/release-qa` (private headless Chrome + its own fake-Engine server) and the docs pointing at it: `e8e9fa5`
- QA fixes — the commit after this report's predecessor.

## QA verdict (goal mode, summary)

GOAL VERDICT: PARTIAL — happy path delivered (all five pass, exit 0, 1m13s, nothing left behind);
names covered; docs point at it. Defects: (1) server exiting early hung the cleanup (exit 13, no
SUMMARY, temp dirs leaked); (2) Chrome failing to start leaked its profile (trap under `set -e`);
(3) screenshots written into the current directory (a stray PNG in the repo root); (4) a busy port
8851 counted as "our server"; (5) product.md overstated what the script walks; (6) a CLAUDE.md line
outside the tickets; (7) `cdp.mjs` defaulted to the owner's debug Chrome on 9222.

Fixed 1–5 and 7: stopServer skips an exited child; `up()` fails as soon as the server exits; a busy
8851 or DevTools port stops the run with a message; the trap can't stop early; screenshots go to a
temp dir (printed, removed when empty); product.md says which steps stay by hand; `CDP` is required.
Checked: server exits → exit 1 with a "setup" line; Chrome fails → exit 2; port busy → message,
exit 1; no temp dirs left; full run exit 0. Kept 6 (the metrics pointer belongs in CLAUDE.md).

## Parked

None.

## Decisions made for you

- The upload tone is generated at run time rather than committed (`.gitignore` excludes `*.wav`).
- Scripted subset of journeys 1–5; the rest stay a manual per-release check, listed in product.md.
