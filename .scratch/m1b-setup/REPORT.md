# m1b-setup — report

**Goal:** Build the M1b Setup page from PLAN.md: model download with progress, `doctor`, licence acknowledgement, RAM check.
**Result:** QA goal verdict **MET**; its 3 code defects are fixed with tests (`5a8a625`), and the stale docs go through `/doc-commit`.

## Tickets

| # | Ticket | Commit |
|---|---|---|
| 01 | Setup checks API, weights state, `<data>/models` default, jobs 409 gate | `8a3d83a` |
| 02 | Licence acknowledgement in SQLite, download gated on it | `8a3d83a` |
| 03 | Weights download in a spawned process: pinned revisions, cleanup, verify, cancel/resume, SSE | `8a3d83a` |
| 04 | Setup page, nav mark, first-load redirect, Create notice | `3f093b6` |
| — | Review fixes | `5a8a625` |

Parked: none.

## Evidence

- `uv run pytest -q`: 186 passed, 2 skipped (opt-in real tests); `ruff check`, `npm run typecheck` clean.
- Real download (`SONGLOOM_REAL_DOWNLOAD=1 uv run pytest tests/test_real_download.py`): 10.45 GB in 151 s, metadata removed, verified, Setup ready (2026-09-17; copy deleted afterwards).
- Browser, fake engine, empty data dir: page opens on Setup → acknowledge → download with live bar → cancel → "Download again" resumes → ready → Create queues and runs a song. Fresh server: Create shows "Finish Setup" and disables Generate.
- `weights_state` on `~/projects/mlx-Yue/models`: installed, 10,450,706,602 bytes, nothing missing or stray.

## QA verdict (verbatim summary)

GOAL VERDICT: MET. All four stories delivered (04 judged from code plus API behaviour; the QA agent had no browser). Checked by hand: fresh-dir snapshot, both 409 gates, cancel then resume from 23,488,101 bytes, acknowledgement and readiness across a restart, SIGTERM and SIGKILL mid-download leave no process behind, SSE `setup` messages with `seq`, the file lists match mlx-Yue's `verify_conversion` exactly, and the runtime check doesn't take the GPU lock.

Defects and what happened to them:

1. Stray files such as `.DS_Store` in `converted/` made "download again" fail verification every time. **Fixed:** the download removes every file `stray_files()` reports.
2. A download whose `done` message arrived just after a poll timed out was marked "exited unexpectedly". **Fixed:** a dead process's queue is read one last time before calling it a failure.
3. A cancel landing while the download finished could be overwritten by `done`/`failed`. **Fixed:** the outcome is only recorded if the state is still `running`.
4. CLAUDE.md and PLAN.md are stale. **Handled by `/doc-commit`.**

Drift noted: the plan said progress came from `tqdm_class`; the code polls bytes on disk. The plan's Note is corrected.

Risks accepted: jobs already queued aren't stopped by a download started through the API (the page never offers a download while weights are installed); on a fresh clone the worker's first load fails harmlessly and is retried when a job needs it.

## Decisions made for you

Ranked costly-and-surprising first.

- **Weights default to `<data>/models`** (was `~/projects/mlx-Yue/models`). Your `dev` registration now passes `--mlx-models /Users/julian/projects/mlx-Yue/models`, so nothing downloads again.
- **All three weight files download (~10.45 GB):** `verify_conversion` requires every precision the manifest lists.
- **The licence gates the download, not song creation:** hand-installed weights still render; the page shows the licence until acknowledged.
- **RAM below 24 GiB warns, never blocks:** the floor is unmeasured (PLAN open question 2).
- **Battery warns:** mlx-Yue refuses to render off AC.
- **Weights state from pinned sizes, not hashes:** hashing runs after a download and on every model load.
- **A failed verification blocks songs** until a successful retry or a restart.
- **Progress by polling bytes on disk** every 0.5 s, not hub internals.
- **The download runs in its own spawned process:** cancel is a kill, and hub `.incomplete` files make the retry resume.
- **Metal check in a short subprocess:** the server never imports MLX.
- **The acknowledgement lives in a new `settings` key/value table:** additive, no migration.
- **`--engine fake` now downloads 64 MB of fake weights** in 6 s, so the Setup page can be tried without a GPU.
