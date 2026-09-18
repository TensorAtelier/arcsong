# m3-score — report

**Goal:** Build M3 from PLAN.md: a "Score only" run, a notation view with MIDI melody preview, an ABC editor with live re-render and validation, rendering a song from an edited Score, and a diff against the original.
**Result:** QA verdict **PARTIAL** on the first pass (the flow worked; the Score view's lifecycle and error handling did not), then **MET** on re-review after the fixes. One regression the first fix introduced was caught by the re-review and fixed too.

## Tickets

| # | Ticket | Commit |
|---|---|---|
| 01 | Score jobs: schema v3, `POST /api/scores`, Engine `plan_only`, dispatch by kind | `b47f5ce` |
| 02 | Score checking: `/api/score/check`, `/strip-chords`, a Take's Score | `b47f5ce` |
| 03 | Rendering from an edited Score (planning skipped) | `b47f5ce` |
| 04 | Score view: notation, melody preview, editor, diff, entry points | `4ca7778` |
| — | Review fixes | `9d33371` |
| — | Re-review fix | `7d0f35a` |

Parked: none.

## Evidence

- `uv run pytest -q`: 219 passed, 5 skipped (opt-in real tests); `ruff check` and `npm run typecheck` clean; the committed build matches `web/src` (the reviewer rebuilt it and compared asset names).
- Real engine, on AC (`SONGLOOM_REAL_ENGINE=1`, 38 s for both): a Score-only run finished with ABC that mlx-Yue's own parser accepts and wrote nothing to disk; a Take rendered from a chord-stripped Score came back carrying that Score.
- Browser, fake engine: notation with both voices and chord symbols; an edit re-renders and the diff names the changed voice and note; an invalid edit shows mlx-Yue's own message; "Remove chords" took 4 chords to 0 with the melody unchanged; "Render song from this Score" queued a Take labelled "From an edited Score"; the Library's Score link opens a Take's Score; the view fills in when planning finishes.
- Playback, in the user's debug Chrome over the DevTools protocol: the melody plays from the vendored samples; leaving the view stops it (live audio sources 1 → 0); an edit resets the button, one click restarts it, and it falls back to Play when the melody ends.

## QA verdict (summary)

First pass **PARTIAL**, re-review **MET**. The reviewer drove the whole flow with curl, migrated a hand-built v2 database, cancelled a running Score job, fuzzed the check endpoints (5 MB of junk, lone surrogates, a 2000-group Score) with no 500s, and confirmed the `/soundfont` mount serves samples while `/api` and the SPA still win their routes.

Defects, all fixed:

1. The melody kept playing after leaving the Score view.
2. A Score URL that 404s polled the API once a second forever.
3. Opening another Score kept the first Score's text against the second's Song request.
4. A failed or cancelled Score run read "Writing the Score (failed)…" and never showed its error.
5. The notices claimed no Score could fail to play; notes outside the piano range can.
6. "Score only" hardcoded 8 steps, so rendering from it silently ignored the chosen quality.
7. A slow validation response could overwrite a newer one.
8. `plan_only` inherited a previous Final's generation config.
9. A Score job's progress showed all four Stages though it runs one.

Drift, both fixed: Variations accepted a supplied Score (now 422), and the `Song` type declared fields the API never returns.

Re-review regression, fixed in `7d0f35a`: after fix 1 the Play button stayed on "Stop" once the Score was edited, so restarting took two clicks.

Residual nits accepted: the 422 for a group carrying a Score is pydantic's wording (no UI path sends it), and the sample-loading error can't tell a missing soundfont from an out-of-range note, so it names both possibilities.

## Decisions made for you

Ranked costly-and-surprising first.

- **The vendored soundfont is 6.7 MB, not the 2.6 MB in the question you answered:** abcjs fetches one MP3 per note, so the whole 88-key range ships. It lives in `songloom/soundfont/` and FastAPI serves it at `/soundfont`, so one copy is in the package instead of two in the build, and `.gitignore`'s `*.mp3` has an exception for it. Trimming the range or dropping the preview is still open.
- **Schema v3** adds `jobs.kind` and `jobs.score`; a Score job's ABC lives in the database, since planning writes nothing to disk.
- **A Score job shares the serial queue and the worker** (planning needs the model), reports the planning Stage and can be cancelled, but makes no song.
- **Editing never writes back:** rendering queues a new job, so the original Score and its Take are untouched.
- **Validation is mlx-Yue's own parser,** so the page rejects exactly what the Engine would and shows its message verbatim.
- **`/api/score/check` returns a compact summary,** not mlx-Yue's full report, which carries every note as a `Fraction` (not JSON, and more than a keystroke needs).
- **An invalid edit keeps the last valid notation on screen, dimmed.**
- **The Score view reloads itself while its job is planning,** and never overwrites edits.
- **A Score-only run stores the quality chosen in Create,** so rendering from the Score uses it.
- **Variations can't carry a Score** (they would be identical).
- **The fake Engine writes a real native two-voice ABC** that varies with the seed, so the page and the parser can be tested without a GPU.
