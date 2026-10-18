# e2e-in-ci — report

## Tickets

- 01 — "Release journeys" CI job (ubuntu, headless Chrome, fake Engine, ffmpeg installed): `scripts/release-qa` on every push; screenshots + log uploaded.
- CI health: `test_a_parts_progress_counts_only_its_own_files` declares small covers files instead of a ~5 GB file (two Windows runners died mid-suite).
- QA hardening: the screenshot step no longer errors when an earlier step failed.

## QA verdict (goal mode)

GOAL VERDICT: MET — run 39106399743 green on all six jobs; J1–J5 pass on CI; `shell: bash` gives
pipefail (confirmed from the log's shell line), so a failing journey turns the job red; Chrome path
fallback fails loudly; ffmpeg installed; artifacts uploaded. The test change still proves "own files
only" and "capped at the total". Defects: none. Risks: screenshot step noise after an earlier
failure (fixed); a red run may carry no screenshots (the SUMMARY line names the journey); Node 20
deprecation warnings on two actions.

## Parked

None.

## Decisions made for you

- Ubuntu only for the browser journeys (Chrome and Node are on the image; macOS minutes cost 10×).
