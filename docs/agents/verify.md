# Verification commands

Run from the repo root. All must exit 0 for a ticket to be done.

- test: `uv run pytest -q`
- lint: `uv run ruff check .`

Note: the `uv` project is created by ticket 01 of `m0-engine-spike`; before that there is no code to verify, so that run's baseline was empty.
