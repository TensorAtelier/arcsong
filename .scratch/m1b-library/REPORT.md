# m1b-library — report

- Plan: `.scratch/m1b-library/plan.md` · Size: lite · Mode: auto
- Branch: `feat/m1b-library` (base `a7d0591`) · Built 2026-09-17

## Tickets

| # | Ticket | Commit | Check |
|---|---|---|---|
| 01 | Library API: list, usage, delete | `48515bf` | 4 API tests (order and fields, sizes against disk, delete removes files, song and job rows plus SSE message, double delete → 404, running job has no song) |
| 02 | Download as FLAC or WAV | `212ebae` | 4 tests (both formats and filenames, FLAC source served unchanged, unknown song or format refused) |
| 03 + 04 | Library view and actions (one commit, as noted in the plan) | `13d2b83` | browser against a fake-engine server: filter, settings, both delete confirm paths (files and job gone on disk), downloads, re-run with the same seed, Edit in Create prefilling every field |
| — | Review fixes | `8f5c82c` | lossless WAV test (sample for sample); browser: delete, then server restart with the page open → reload keeps the song deleted, no error |

Parked: none.

## Review (verbatim)

```
GOAL VERDICT: MET

What I checked: I read the full branch diff (`git diff 11b168a...HEAD`) and every changed file in full. All three verification commands are green:
- `uv run pytest -q`: 170 passed, 1 skipped
- `uv run ruff check .`: All checks passed!
- `npm run typecheck` (`tsc --noEmit`): exit 0, no errors

A fresh `npx vite build --outDir <scratch>/static` is identical to the committed `songloom/static/` (`diff -r` found no differences).

I also ran the app with the fake engine on port 8844 and tried everything below with curl:
- listing songs and the library figures
- re-running a stored request
- deleting while another job is running, deleting twice, 4 deletes at once, and a non-integer id
- the SSE `deleted` message reaching two open event streams
- both download formats, their headers, a bad format, and a missing audio file
- how much memory the WAV conversion of a 3-minute, 48 kHz, 24-bit stereo FLAC (~40 MiB) uses

I did not re-check the page in a browser. Afterwards I stopped the server and deleted the scratch data. The only `spawn_main` process still running belongs to practice-dojo, not songloom.

STORIES:
- 01 (Library API). Delivered.
  - `/api/songs` lists newest first with the request and the byte total of the Take directory; this matched the files on disk in my run and in `test_songs_are_listed_newest_first_with_their_request_and_size`.
  - `/api/library`'s free space comes from `shutil.disk_usage(root)` and matched `df`.
  - DELETE removes the directory, the song row and the job row.
    - A second delete gets 404. Of 4 deletes at once, exactly one got 200.
    - Deleting song 1 while job 3 (a re-run of song 1) was running left job 3 untouched, and it finished normally.
    - An id that isn't a number gets 422.
    - Both open event streams received `{"type":"deleted","job_id":3,"song_id":3,"seq":…}`.
  - Race and path safety:
    - Only finished Takes have a song row (`add_song` sets the job to done in the same transaction), so a running job can't be deleted (tested).
    - Job ids are AUTOINCREMENT, so the deleted `songs/<id>` directory name is never reused.
    - The path given to `rmtree` always comes from the DB (`audio_path.parent` as the worker reported it), never from the request.
- 02 (Download). Delivered, with a fidelity defect (1).
  - Both formats return the right content type.
  - Filenames are ASCII only: `"a"; filename=x.exe` becomes `songloom-5-a-filename-x-exe.wav`, `日本語` becomes `songloom-6.flac`, and at most 6 words are kept. The header can't be injected into.
  - A format other than flac or wav gets 422; an unknown song or missing file gets 404.
  - Memory: converting the 3-minute FLAC took 0.3 s, but the process peaked about 177 MiB higher, because `soundfile.read` decodes to float64 and then the buffer is copied. That is acceptable on this machine.
- 03 (Library view). Delivered as far as I can tell from reading the code.
  - Hash nav, newest-first list, a filter on style and lyrics that ignores case, player, settings drawer, date, length, size, and the usage line.
  - The usage line sits in the Library panel's heading, not the page header. That's a minor wording gap with the Proof of done.
- 04 (Actions). Delivered.
  - Re-run posts `song.request` unchanged; the server echoed the same seed 42, bf16, 8 steps and melody mode.
  - Edit in Create fills in all six fields (the form is re-keyed by a draft version).
  - Delete has an in-page confirm and Keep step, with no `window.confirm`.
  - `removeDeleted` drops the job from the queue and the song from the list, both for the page that deleted it and, through SSE, for other open pages.

DRIFT:
- No plan Note is contradicted. The 03+04 shared commit is stated in the Notes.
- One Note is met in letter only: "WAV/FLAC conversion uses soundfile". Real Takes are PCM_24 FLAC (the vendored mlx-Yue `pipeline.py:98` writes them that way), but the WAV download is written as PCM_16, which silently loses bit depth. The FLAC-to-WAV test only checks shape and sample rate, so it doesn't catch this.
- None of the Not-yet items crept in: no stars, tags, playlists, bulk delete, trash or setup page.

RISKS (ranked):
1. People download WAVs expecting a lossless master and get 16-bit audio, truncated with no dither.
2. A ghost card can come back after a delete.
   - The server sends `seq` on `deleted`, but the page ignores it.
   - Only a `/api/songs` or `/api/jobs` REST request already in flight when the `deleted` message arrives can do this: from `reloadSongs` after a job finishes, or from the reload on reconnect.
   - The deleted song then reappears in the Library, or its job in the queue, until the next reload. Rare, since it needs a delete within that short window.
3. View switching and drafts:
   - Anything typed in Create is lost when you switch to Library, because the form unmounts.
   - After Edit in Create, the draft and the "Loaded from the Library" hint come back every time you return to Create.
4. A download that races a delete may send a truncated file or a 500 instead of a clean 404. Local and rare.
5. `/api/songs` exposes absolute `dir`/`audio_path` paths. Harmless on localhost-only v1.
6. Delete trusts that the audio file sits directly inside the Take directory. That holds for both engines today, but nothing enforces that the directory is under `songs_dir`, so a future engine that saves audio in a subfolder would leave files behind on delete.
7. If the song list fails to load but the job list then loads, `setLoadError(null)` clears the error, and the Library shows "Loading…" forever.

DEFECTS:
1. songloom/app.py:157 — Converting FLAC to WAV writes subtype="PCM_16", so 24-bit Takes lose bit depth. Reproduce: write a PCM_24 FLAC Take, download with ?format=wav, and soundfile.info(...).subtype is PCM_16. Fix: keep the source subtype, and add an assertion on subtype to the test. Story 02.
2. web/src/App.tsx:31-59 and :63-81, web/src/api.ts (Deleted) — Deletions aren't remembered against later REST responses, and the seq on deleted is unused. A /api/songs or /api/jobs response fetched before a delete but arriving after the deleted message puts the song and job back in the page. Fix: keep a set of deleted song and job ids (or the delete seq) and filter reload results with it. Stories 03/04.
3. web/src/App.tsx:33-37,68 — songs and jobs share one loadError, so a successful jobs load clears a songs failure and the Library stays on "Loading…". Story 03 (minor).
```

(The three DEFECTS entries are condensed from the reviewer's multi-line bullets without changing their content.)

## Fixes after review (`8f5c82c`)

| Defect | Fix | Checked |
|---|---|---|
| 1. WAV downloads lose bit depth | keep the source subtype (PCM_16/PCM_24, else PCM_24) and read as int32 | test asserts PCM_24 and that the WAV equals the FLAC sample for sample |
| 2. A deleted song can come back | the page remembers deleted song and job ids and filters them from later list responses and job updates | browser: delete, then server restart with the page open → reconnect reload keeps it deleted |
| 3. Shared load error | separate songs and jobs errors | browser: reload after restart shows no stale error or "Loading…" (a forced songs failure wasn't reproduced) |

Not fixed (review risks, all minor): the Create draft is lost when switching views and the Edit-in-Create draft returns each visit (3); download racing a delete can 500 (4); absolute paths in `/api/songs` (5); delete assumes audio sits directly in the Take directory (6).

## Parked tickets

None.

## Look here first

1. **Delete is permanent.** It asks for confirmation in the page but has no trash or undo.
2. **Unsaved Create text is lost when you switch to Library** (review risk 3). A small follow-up if it bothers you.
3. **The review fixes weren't re-reviewed** by a fresh QA agent; each is covered by a test or a browser check above.

## Decisions made for you

From the plan's Notes, ranked costly-and-surprising first:

- **Delete is permanent (no trash)**, confirmed in the page; it removes the Take directory, the song row and its job row, so the queue loses the entry too.
- **Tickets 03 and 04 share one commit** (one component, checked together).
- **WAV/FLAC conversion** happens in memory with `soundfile` (about 177 MiB peak for a 3-minute song), keeping the source bit depth; the download name is `songloom-<id>-<style words>.<ext>`.
- **The filter runs in the page**; the server returns all songs (fine at this scale).
- **Size on disk** is each Take directory's total; free space is `shutil.disk_usage` of the data dir.
- **Re-run sends the stored request unchanged** (seed included), which reproduces the same Take at the same precision and steps (M0).
- **Browser checks used the fake engine**; FLAC handling is covered by a test that writes a real 24-bit FLAC.
