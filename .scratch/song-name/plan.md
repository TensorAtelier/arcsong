# song-name — plan

**Goal (owner):** songs have a name, which makes the UI easier; existing songs are backfilled; the
name is **required** when making a song.
**Not yet:** renaming a whole sketch at once (each take renames on its own, as today).
**Stack / interfaces:** `arcsong/db.py` (schema v6, backfill, stored names), `arcsong/app.py`
(`title` on Song/Score/Group requests and the cover form), `web/src` (Song name field in Create and
Cover, required; Edit in Create carries the current name).
**Proof of done:** Create can't submit without a name; a named sketch's takes all carry it into the
queue, Compare and the Library; a Final keeps its Draft's name; every existing song has a stored
name equal to what it showed before; rename and "blank resets" still work; tests cover the API,
the migration and the inheritance.

## Tickets

- [x] 01 — Server: `title` on requests (optional at the API, blank → none), job/song name = given name else first sung line, stored when the song is indexed; Final inherits; schema v6 backfills stored names; rename blank stores the default; tests.
- [x] 02 — Create and Cover: a required Song name field (Write, Plan, Cover); Edit in Create pre-fills the song's current name; Retry/Render again keep names; check in the browser.

## Notes

- Required in the forms, optional at the API (owner asked for required; the API stays lenient for scripts and old requests — logged in decisions.md).
- `title_set` stays in the API, now meaning "differs from the default", so the rename box's
  "blank resets" logic is unchanged.
