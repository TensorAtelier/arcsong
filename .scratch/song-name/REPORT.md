# song-name — report

Owner requests (cycle 2): songs have a song name (makes the UI easier); backfill existing songs;
then mid-cycle: the name is required.

## Tickets

- 01 — server: `title` on requests (optional at the API), names stored when indexed, Finals inherit, schema v6 backfill, blank rename stores the default: `5efdb9c`
- 02 — a required Song name in Create (Write, Plan) and Cover; Edit in Create, Render it again, Retry and render-from-Score keep the name: `a3a2176` (docs `2c5e256`)
- QA fix — a queued Final shows its Draft's current name (runner.finalize copies it).

## Backfill on the owner's library

Backed up `arcsong.db` (`arcsong.db.before-v6-20261017-135349` beside it), restarted: v5 → v6; all
six songs now store the names they showed (four first lines, "Rain against the window of the corner
room" ×2 for the sketch, "The kettle's got a dent in it").

## QA verdict (goal mode)

GOAL VERDICT: MET — names stored and backfilled in one transaction (v1–v5 chains reach 6), required
in every form that makes a song, optional and trimmed at the API, Finals keep the Draft's current
name, rename/blank-reset work, every re-send keeps the name; an extra `title` key cannot reach an
Engine call. Defects: a queued Final showed the Draft's old name until indexed (fixed, tested); the
cycle-2 decision entry was uncommitted (committed with this report). Verification: pytest 276
passed, ruff clean, tsc clean, bundle hash matches.

## Parked

None.

## Decisions made for you

- Required in the forms, optional at the API — scripts, old jobs' Retry and the suite keep working.
- Every song stores its name (no NULL = "default"), so names can't shift under a song later.
- Name field after the Sketch/Single choice, before Style.
