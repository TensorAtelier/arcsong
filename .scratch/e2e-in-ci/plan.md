# e2e-in-ci — plan

**Goal:** the five release journeys run on every push, so a broken core journey shows up red on
CI rather than at release time.
**Not yet:** a phone-width pass beyond what the journeys already check; Windows/macOS browser runs.
**Stack / interfaces:** `.github/workflows/ci.yml` — a "Release journeys" job on ubuntu-24.04
(Chrome and Node are on the image), `uv sync --frozen`, `CHROME=$(command -v google-chrome)
scripts/release-qa`; failure screenshots uploaded as an artifact.
**Proof of done:** the job is green on CI with all five journeys passing; it fails the run when a
journey fails (`scripts/release-qa` exits non-zero).

## Tickets

- [x] 01 — The CI job; green on GitHub.

## Notes

- Journey 5 needs the covers part usable, which needs ffmpeg on PATH: install it in the job if the image lacks it.
- `scripts/release-qa` prints the screenshot directory; the job reads it from the log line.
