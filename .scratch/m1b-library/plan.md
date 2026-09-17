# m1b-library — plan

**Goal:** Build the M1b Library from PLAN.md: list and filter past songs, play and download (FLAC/WAV), view settings, re-run with the same settings, show disk usage, and delete Takes.
**Not yet:** Setup page (weights download, doctor, licence, RAM check) — its own feature, `m1b-setup`. Stars/ratings, tags, playlists, bulk delete, trash/undo. Score view (M3). Finalize/re-synthesis (M2). Clearing failed/cancelled jobs from the queue.
**Stack / interfaces:**
- API additions: `GET /api/songs` (Takes with their Song request and size on disk), `GET /api/library` (song count, bytes used, free disk space), `GET /api/songs/{id}/download?format=flac|wav`, `DELETE /api/songs/{id}`; an SSE `deleted` message.
- Page: a two-view page, Create and Library, switched by a nav (`#/` and `#/library`; no router dependency).
**Proof of done:** Open the Library view: every finished song is listed newest first with its style, length, date, size and settings. Typing in the filter narrows it by style or lyrics. A song plays in place, downloads as FLAC or WAV, re-runs with the same settings (and the same seed, so the same song), or loads into Create to tweak. The header shows how much disk the library uses and how much is free. Deleting a song asks for confirmation in the page, then removes its files and its entry in both views.

## Tickets

- [x] 01 — Library API: `GET /api/songs`, `GET /api/library` and `DELETE /api/songs/{id}` (removes the Take directory and its song and job rows, and broadcasts a `deleted` SSE message); check: API tests through the fake engine (listing order and fields, sizes, delete removes files and rows, deleting twice → 404, a running job has no song to delete).
- [x] 02 — Download as FLAC or WAV: `GET /api/songs/{id}/download?format=flac|wav` returns the audio as an attachment named after the song; the missing format is converted on the fly; check: tests decode both formats with soundfile and compare length.
- [ ] 03 — Library view: nav between Create and Library; newest-first list with filter, player, settings drawer, size and date, and disk usage in the header; check: in the browser against a fake-engine server with a few songs.
- [ ] 04 — Library actions: Download FLAC/WAV, Re-run (queues the identical request, then switches to Create so the job is visible), Edit in Create (prefills the form), and Delete with an in-page confirm step that removes the song from both views live; check: in the browser (re-run appears in the queue with the same seed; delete confirm, cancel and confirm paths; the file is gone on disk).

## Notes

- Delete is permanent (no trash) and needs an in-page confirmation; no `window.confirm`. It removes the Take directory, the song row and its job row, so the queue loses the entry too.
- The library lists songs (finished Takes), newest first; the filter matches style and lyrics case-insensitively in the page; the server returns all songs (fine at this scale).
- Size on disk = the Take directory's total bytes (M0: ~37–40 MiB per 3-min song, nearly all FLAC); free space from `shutil.disk_usage` on the data dir.
- WAV/FLAC conversion uses `soundfile` (already installed with mlx-Yue) into memory; no temporary files; the download filename is `songloom-<id>-<style slug>.<ext>`.
- Re-run sends the stored Song request unchanged (seed included), which M0 showed reproduces the same Take at the same precision and steps.
- Browser checks use the fake engine (no GPU needed); the real engine's saved Takes are FLAC, so ticket 02 also tests FLAC input with a FLAC written by the test.
