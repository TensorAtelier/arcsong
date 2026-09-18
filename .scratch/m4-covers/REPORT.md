# m4-covers — report

**Goal:** Build M4 from PLAN.md: an optional extra install (ffmpeg + the transcription weights, detected on the Setup page), then upload audio → transcribe it into a Score → edit that Score with the M3 view → render a cover, with ABC and MIDI export.
**Result:** QA verdict **PARTIAL** twice, then **MET** on the third pass. Six defects, two partly-fixed ones, three nits and all drift are closed, each with a test.

## Tickets

| # | Ticket | Commit |
|---|---|---|
| 01 | Setup parts: engine + covers, ffmpeg check, per-part download | `51ba6a5` |
| 02 | Cover jobs: upload, `transcribe()`, upload deleted on every finish | `5e8dc68` |
| 03 | Cover panel, queue labels, ABC/MIDI export | `af06f17` |
| — | Review fixes | `d630073` |
| — | Re-review fixes | `1dab6b7`, `52745e6` |

Parked: none.

## Evidence

- `uv run pytest -q`: 240 passed, 7 skipped (opt-in real tests); `ruff check` and `npm run typecheck` clean; the reviewer rebuilt the committed bundle and compared hashes.
- Real, on the user's machine and weights (`SONGLOOM_REAL_ENGINE=1`, on AC):
  - the covers weights downloaded and verified in 42 s (218 MB SheetSage2 + 2.4 GB MERT2, now in `~/projects/mlx-Yue/models`);
  - a rendered Take was transcribed and re-sung in a new style in 47 s, with the upload gone from disk afterwards. Re-run after the review fixes: 2 passed in 47 s.
- Real download progress: a covers download into a temp directory, polled every 2 s, reported 0 → 8 → 18 → 39 → 55 → 62 → 100%, which is what proved the second progress fix (the first one never matched the hub's hashed names).
- Browser, fake engine: the Cover panel takes a file, style and the rights box; the job shows "Cover · … from my-song.wav" with its transcription Stage; the Score view opens with notation, exports ABC and MIDI, and renders the cover.
- Live checks by the reviewer: refusals leave no job and no file; a `kill -9` mid-transcription discards the running job's recording and keeps the queued ones; a planted `incoming-*` file is swept on restart.

## QA verdict (summary)

Three passes: **PARTIAL**, **PARTIAL**, **MET**.

Defects, all fixed:

1. An oversized upload created its job row before validating, leaving a phantom cover queued that killed the next job with a raw error.
2. A part counted every file in its directory, so with the covers weights beside the song weights the covers progress read 100% from the start and its disk check could never warn. Fixed twice: first to count only the part's own files, then — after the reviewer showed the hub names in-flight files by hash — to count whatever part-downloaded files exist rather than guessing their names.
3. Cancelling a real transcription reported a failure with a traceback. Fixed, then fixed again to cover a cancel during the 2.4 GB model load.
4. The two transcription models were downloaded under the existing acknowledgement but named nowhere. Now in the licence list, the Covers summary and `THIRD_PARTY_NOTICES.md`, with ffmpeg noted as detected, never shipped.
5. A cover could start before the ffmpeg check had run, failing later in the worker. Optional parts now wait for their own checks; the Song model does not.
6. The page recomputed readiness and could disagree with the server; it now uses the server's verdict.

Nits fixed: a staged upload could survive an error or a crash (try/finally plus a startup sweep); the Cover panel said "finish Setup" during the brief checking window; a file the hub renames mid-listing could wedge a download's progress thread.

Drift fixed: the transcription model was reloading on every cover (now loaded once); `CONTEXT.md` gained **Cover** and a **Stage** that admits a fifth; a dead `uploads_dir` removed.

Risks accepted, recorded in CLAUDE.md: stale `.incomplete` files can inflate a progress bar after a revision-pin change (display only); the resident transcription model adds about 3 GiB on top of the song model.

## Decisions made for you

Ranked costly-and-surprising first.

- **The uploaded recording is deleted as soon as the job ends,** however it ends, and a server sweeps anything a crash left behind. songloom never keeps someone's recording.
- **Covers are an optional Setup part** (~2.6 GiB): Setup now manages named parts, and only the Song model gates making songs.
- **ffmpeg is detected, never shipped:** it is a separate program under its own licence, so Setup says `brew install ffmpeg`.
- **The transcription models are CC BY-NC 4.0, like the song weights,** so the existing acknowledgement covers them — but they are now named wherever the licence is shown.
- **A rights confirmation is required per upload,** and the panel says you are responsible for what you upload and for what you do with the result.
- **mlx-Yue's `transcription` extra is part of songloom's dependency,** so a cover needs no second install.
- **Uploads are capped at 200 MB** and transcription shares the serial queue with rendering.
- **Task `melody-full`:** both voices, no chords, which is what a cover re-sings.
- **The transcribed Score is the same native ABC a planned Score uses,** so it edits, renders and exports through the M3 view unchanged.
- **MIDI export comes from abcjs in the page,** so every Score exports one, not only transcribed ones.
