# m2-variations — plan

**Goal:** Build M2 from PLAN.md: "Generate ×N" Drafts (8 steps) with distinct seeds, a compare view with synced players and waveforms, star/pick, then "Finalize" the pick by re-synthesizing its saved Semantic tokens and noise at 32 steps.
**Not yet:** Score view/edit (M3). Batch actions (finalize several, delete a group). Ratings beyond one star. Per-variation sampling tweaks (only the seed varies). Loudness matching between takes. Re-grouping or renaming groups.
**Stack / interfaces:**
- DB schema v2 (migration from v1 with `ALTER TABLE ADD COLUMN`): `jobs.group_id` (id of the group's first job), `jobs.source_song_id` (the Draft a Final came from), `songs.starred`.
- API: `POST /api/groups` (a Song request + `count` 2–8 → the queued jobs), `GET /api/groups/{id}` (its jobs), `PUT /api/songs/{id}/star` (`{"starred": bool}`), `POST /api/songs/{id}/finalize` (queues a Final), `GET /api/songs/{id}/peaks` (waveform min/max buckets + duration). Jobs and songs gain `group_id`, `source_song_id`, `starred`. SSE: a `song` message when a star changes.
- Engine: `finalize(source_dir, request, out_dir, cancelled, emit)` beside `render`, in mlx-Yue (load the Draft's artifacts, synthesize with its noise, decode, save) and the fake. The worker job tuple gains the source directory.
- Page: Create gets a "Takes" count (1, 2, 4, 8); the queue marks group members and links "Compare"; a Compare view on `#/compare/<group id>` with one waveform per Take (wavesurfer.js, server peaks, streaming `<audio>`), a shared playhead (play one Take, switch to another at the same moment), star, and Finalize; the Library gets a star toggle, a Starred filter, Draft/Final labels, Finalize, and a Compare link.
**Proof of done:** In Create, pick 4 Takes at Quick draft and Generate: four jobs with four different seeds queue as one group. Open Compare: each finished Take shows its waveform; playing one then clicking another continues from the same moment. Star one and Finalize it: a 32-step Final queues, runs only synthesis and decoding, and lands in the Library marked as the Final of that Draft, starred Takes filterable. With real weights, a Finalize render succeeds end to end.

## Tickets

- [x] 01 — Variations and stars API: schema v2 with migration, `POST /api/groups`, `GET /api/groups/{id}`, `PUT /api/songs/{id}/star` with an SSE `song` message, new fields on jobs and songs; check: API tests (distinct seeds, order, group lookup, star round trip and survival across restart, a v1 database migrates with its rows intact).
- [x] 02 — Finalize: `POST /api/songs/{id}/finalize` queues a Final (same request, 32 steps, `source_song_id`); refused with 409 for a Take already at 32 steps or one with a queued/running/done Final; worker and Engine `finalize` for mlx-Yue and the fake; check: API tests through the fake (Final job runs synthesis and decoding only, song indexed with its source), and a real Draft → Final render behind `SONGLOOM_REAL_ENGINE=1`.
- [x] 03 — Waveform peaks: `GET /api/songs/{id}/peaks?buckets=N` returns per-bucket min/max of the mixed-down audio and the duration, cached in memory; the fake's tone varies with the seed so Takes look different; check: API tests (bucket count, range, a quiet vs loud file).
- [x] 04 — Create ×N, queue and Library: Takes count in Create, group label and Compare link in the queue, Library star toggle, Starred filter, Draft/Final labels, Finalize button; check: in the browser against a fake-engine server.
- [x] 05 — Compare view: `#/compare/<group>` with a card per Take (seed, status/progress, waveform, play, star, Finalize), shared playhead across Takes, waveform click seeks; check: in the browser against a fake-engine server (switching Takes keeps the position; star and Finalize update the Library).

## Notes

- A group is not a table: `group_id` is the id of the group's first job, set on every member (the first included). Single jobs keep `group_id` null. A Final is not in its Draft's group; it points at the Draft with `source_song_id`.
- Seeds: a given seed `s` gives `s, s+1, …`; no seed gives distinct random seeds. The request is otherwise identical across the group.
- The count selector doesn't force 8 steps; its hint recommends Quick draft for variations. Finalize is offered only for Takes below 32 steps.
- A Final's request is the Draft's request with `steps: 32`, so "Re-run" of a Final renders the same song directly (M0: Final is bit-identical to a direct 32-step render at the same precision).
- Finalize reuses the Draft's saved `semantic.npy` and `noise.npy` via mlx-Yue's `load_artifacts` (which verifies them), loads the pipeline at the Draft's precision, and saves a complete new Take directory, so deleting the Draft later doesn't affect the Final. A Final whose Draft was deleted shows "Final of a deleted Draft".
- Only one Final per Draft: a second Finalize is refused while one is queued, running or done; after a failure or cancel it can be retried.
- Peaks are computed from the audio file with soundfile (not stored in the Take directory, whose contents mlx-Yue's `load_artifacts` verifies), cached in memory per song. wavesurfer.js gets `peaks` + `duration` and a streaming media element, so the browser never decodes a whole 40 MB FLAC.
- Synced players = one shared playhead: only one Take plays at a time; starting another seeks it to the shared time. Clicking a waveform moves the shared time for every Take.
- The star is a boolean on the song (the "pick"); an SSE `song` message keeps other views in step.
- CONTEXT.md gains **Variations** (Takes of one Song request with different seeds, compared side by side) and **Finalize** (turning a Draft into its Final).
- Tickets 02 and 03 share one commit: both touch the song routes in `app.py`. The fake Engine's tone now varies with the seed (pitch and swell), which the peaks test relies on.
- Real Finalize check (`SONGLOOM_REAL_ENGINE=1 … -k finalized`, 2026-09-17, on AC): an 8-step Draft of the short clip was finalized in one server run (38 s total); the Final's `semantic.npy`, `noise.npy` and `score.abc` are byte-identical to the Draft's and its latents differ.
- Tickets 04 and 05 share one commit: the Compare view, queue labels and Library actions all hang off the same App state (song events, jobs, `updateSong`).
- `songloom serve --engine fake` now writes 20 s tones (was 1 s), long enough to compare Takes in the page. Tests keep the 1 s default.
- Browser check (fake engine): Create ×4 at 8 steps queued four seeds labelled "Take n of 4 · Compare"; Compare drew four different waveforms; star and Finalize on Take 2 gave "Final running…", then the Library showed #5 "Final of #2", #2 "Finalized as #5" without a Finalize button, and Starred only listed #2.
- Playback was checked in the user's debug Chrome (port 9222) over the DevTools protocol, because Chrome doesn't load media in the hidden automation tab: Take 1 played to 3.9 s; switching to Take 2 paused Take 1 and continued from there (5.3 s 1.5 s later); a real click at 75% of Take 3's waveform moved every Take to 14.98 s with Take 2 still playing. This found and fixed a bug: pausing a Take whose play() hadn't settled raised AbortError, and treating it as a failure stopped the Take just switched to.
