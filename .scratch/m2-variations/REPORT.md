# m2-variations — report

**Goal:** Build M2 from PLAN.md: "Generate ×N" Drafts with distinct seeds, a compare view with synced players and waveforms, star/pick, and "Finalize" a Draft by re-synthesizing its saved Semantic tokens and noise at 32 steps.
**Result:** QA goal verdict **MET**. Its 3 defects and 2 of its 5 risks were fixed with tests (the fix commit after `13b06a9`).

## Tickets

| # | Ticket | Commit |
|---|---|---|
| 01 | Variations and stars API, schema v2 with migration | `63b32ba` |
| 02 | Finalize: API, runner, worker, Engine `finalize` (mlx-Yue + fake) | `80d40db` |
| 03 | Waveform peaks endpoint, seed-dependent fake tone | `80d40db` |
| 04 | Takes count in Create, queue labels, Library star/filter/labels/Finalize | `9b843f6` |
| 05 | Compare view with waveforms and a shared playhead | `9b843f6` |
| — | Review fixes | see `git log` |

Parked: none.

## Evidence

- `uv run pytest -q`: 204 passed, 3 skipped (opt-in real tests); `ruff check` and `npm run typecheck` are clean.
- Real engine, on AC, after the review fixes (`SONGLOOM_REAL_ENGINE=1 caffeinate -ims uv run pytest -q tests/test_real_engine.py`): 2 passed in 62 s. That covers a full render, plus a Draft finalized from its saved Take. The Final's `semantic.npy`, `noise.npy` and `score.abc` are byte-identical to the Draft's, and its latents differ.
- Browser, fake engine (automation tab):
  - Create ×4 at 8 steps queued four seeds, labelled "Take n of 4 · Compare".
  - Compare drew four different waveforms.
  - Star and Finalize on Take 2 led to Library entries "Final of #2" and "Finalized as #5", with Finalize hidden. Starred only listed #2.
- Playback, in the user's debug Chrome over the DevTools protocol (Chrome won't load media in the hidden automation tab):
  - Take 1 played to 3.9 s. Switching to Take 2 continued from there.
  - A click at 75% of Take 3 moved every Take to 14.98 s while Take 2 kept playing.
  - After the fix, clicking the same waveform spot again moved the playing Take from 13.4 s back to 10.4 s.
- Two bugs were found and fixed during the build: switching Takes stopped both (AbortError treated as failure), and a test read the API after its server closed.

## QA verdict (summary)

GOAL VERDICT: MET. All five stories delivered (04 and 05 judged from the code plus the recorded browser checks).
- **Checked live with curl:** the Setup gate on groups and finalize, a group of 4 with distinct seeds, group lookup and 404, star round trip, both Finalize refusals, and a Draft deleted while its Final was queued (the Final fails with "its Draft was deleted") or running (it completes).
- **Checked against the source and the build:** the migration on a fresh DB, a v1 test DB and a copy of the real v1 `songloom.db`; the mlx `finalize` against lyra's `load_artifacts`/`save_artifacts` contract; wavesurfer never decoding the full file; stable effect dependencies; and a static build matching `web/src`.

Defects and what happened to them:

1. Clicking a waveform at the same second as the previous click didn't move the playing Take. **Fixed:** every click is a new seek object; checked in the debug Chrome.
2. Starring a song deleted mid-request returned 500. **Fixed:** 404, with a test.
3. With mlx, a Draft deleted during the Final's model load failed with a raw traceback. **Fixed:** the Draft is read before the model loads, and a missing one fails as "its Draft was deleted"; a test shows no model load is attempted.

Risks:

- Generation config carried over from a finalized Draft into later renders. **Fixed:** renders start from the weights' own config. No unit test; covered by the real render rerun.
- Migration not atomic. **Fixed:** one transaction, with a test that forces the last ALTER to fail and finds the v1 schema intact.
- Star flicker when a song list reload crosses a star change. **Accepted:** songs have no `seq`; the window is milliseconds on localhost and the next reload corrects it.
- Dispatch recursion for runs of orphaned Finals. **Accepted:** bounded and on an RLock.

Drift: none. CLAUDE.md's API list is updated by `/doc-commit`.

## Decisions made for you

Ranked costly-and-surprising first.

- **Schema v2 migrates your library in place:** additive columns, one transaction. Your current library is empty.
- **One Final per Draft:** refused while one is queued, running or done; retry after a failure or cancel. A Final is its own complete Take, so it survives deleting its Draft.
- **"Synced players" means one shared playhead**, not simultaneous playback: switching Takes continues from the same moment, and a waveform click moves every Take.
- **Seeds:** a given seed counts up (s, s+1, …); none gives distinct random seeds.
- **The Takes count doesn't force 8-step drafts;** a hint recommends Quick draft.
- **A group is not a table:** `group_id` is the first job's id, and a Final sits outside its Draft's group.
- **Waveforms come from server-computed peaks**, cached in memory, never stored in the Take directory (mlx-Yue verifies its contents).
- **A star is a single on/off pick,** not a rating.
- **wavesurfer.js 7 is the new web dependency** (named in PLAN.md).
- **`serve --engine fake` writes 20 s tones,** and the fake tone varies with the seed; tests keep 1 s.
- **CONTEXT.md gains three terms:** Finalize, Variations, Star.
