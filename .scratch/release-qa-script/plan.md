# release-qa-script — plan

**Goal:** release QA's journeys 1–5 (`docs/product/product.md` → Release) are one command, so every
release is checked the same way, and e2e-in-ci can build on it.
**Not yet:** running it on CI (e2e-in-ci); journey 6 (real weights) stays `tests/test_real_engine.py`.
**Stack / interfaces:** `scripts/release-qa` (bash: a private headless Chrome on a temp profile,
then Node) + `scripts/release_qa/` (`cdp.mjs`, `release-qa.mjs`, `qa-tone.wav`). It starts its own
fake-Engine server on port 8851 with a temp data dir; nothing touches the owner's server or browser.
**Proof of done:** `scripts/release-qa` prints one JSON line per journey and a summary, exits 0 when
all five pass and non-zero otherwise; journeys cover the cycle-2 names (unnamed song refused; names
appear); `docs/release.md` and `product.md`'s Release section point at it.

## Tickets

- [x] 01 — Move the cycle-1 seed into `scripts/`, one command that starts and stops its own Chrome, exit code reflects the journeys; run it.
- [x] 02 — Point `docs/release.md` and CLAUDE.md at it.

## Notes

- Node (already needed for `web/`) and Google Chrome; `CHROME=` overrides the browser path.
