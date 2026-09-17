# m1a-first-song — plan

**Goal:** Build M1a from PLAN.md: FastAPI server, SQLite jobs/songs, mlx-Yue worker process with queue, cancel and SSE progress, and a bare Create page, so a user can write lyrics and get a song end to end.
**Not yet:** Library page (list/filter, delete, disk usage, re-run) and Setup page (download, doctor, licence, RAM check) — M1b. Finalize/re-synthesis and variations — M2. Score view/edit — M3. Idle model unload. Packaging/`uv tool install`. Any styling beyond plain, readable defaults.
**Stack / interfaces:**
- Backend: `songloom` Python package (FastAPI + uvicorn, stdlib `sqlite3`, `multiprocessing` spawn), `songloom serve` on 127.0.0.1:8840.
- Engine: mlx-Yue staged API (`lyra.YuE2Pipeline`) in one long-lived worker process; a fake engine for tests.
- API: REST under `/api` (create/list/get/cancel jobs, song audio) plus one SSE stream `/api/events`.
- Frontend: Vite + React + TS in `web/`, built into the package's static dir and served by FastAPI.
- Data: `SONGLOOM_DATA` dir (default `platformdirs` user data dir; `./data` in dev), holding `songloom.db` and `songs/<id>/` (mlx-Yue `save_artifacts` output as-is).
**Proof of done:** Run `songloom serve`, open http://127.0.0.1:8840, write style + lyrics, press Generate. The job shows up in the queue with its current Stage and live progress (token count, then the stepped synthesis %), can be cancelled, and when it finishes plays the song in the page. Stopping and restarting the server keeps finished songs and marks an interrupted job failed.

## Tickets

- [x] 01 — Server, database and queue with a fake engine: `songloom serve` accepts `POST /api/jobs`, a worker process runs jobs one at a time and the job reaches `done` with a playable WAV at `GET /api/songs/{id}/audio`; check: pytest API test through the fake engine, plus curl against a running server.
- [ ] 02 — Real mlx-Yue worker: the worker loads mlx-Yue once, keeps it warm, renders a request through the staged API and saves the Take; a song row is written only after saving completes; check: slow test behind `SONGLOOM_REAL_ENGINE=1` rendering a short request, plus a manual curl render.
- [ ] 03 — Live progress and cancel: `GET /api/events` (SSE) streams job state, Stage changes, a throttled token count and synthesis `N/steps`; `POST /api/jobs/{id}/cancel` stops a queued or running job via a shared cancel flag; check: fake-engine tests for event order, throttling and cancel, plus one real cancel.
- [ ] 04 — Worker crash and restart recovery: if the worker process dies the running job is marked failed and the next job runs on a new worker; on server start, `running` jobs become `failed` and `queued` jobs run in order; check: fake-engine tests that kill the worker and restart the app.
- [ ] 05 — Bare Create page: form (style, lyrics with a section-tag template, planning mode, seed, precision, Synthesis steps, advanced drawer), a queue panel with Stage + progress + cancel, and an audio player for finished jobs; built assets are served by `songloom serve`; check: drive the real page in the browser end to end (generate, watch progress, play; cancel one).

## Notes

- Engine confirmed as mlx-Yue (user, 2026-09-17); the adapter follows the spike's `MlxYueEngine` but lives in `songloom`, not `spike`.
- Worker = one `multiprocessing` spawn process owning the model; server ↔ worker via two queues (jobs in, events out) and a shared cancel `Event`, as PLAN.md's architecture says.
- Progress comes from `on_token` (running count) and yue2's stderr `N/total` lines for synthesis (M0 findings); events are coalesced to at most ~4 per second per job before SSE.
- A song row is inserted only after `save_artifacts` returns, so a kill while saving never shows a partial Take (M0 open risk).
- Defaults: precision 8bit (speed; M0 showed no memory benefit), Synthesis steps 32 with 8 offered as the quick draft, planning mode `full`, random seed shown and editable.
- Schema v1: `jobs(id, status, request_json, created_at, started_at, finished_at, error, song_id)` and `songs(id, job_id, dir, audio_path, audio_seconds, created_at)`; a `schema_version` pragma allows cheap migration later. No real user data exists yet, so this is not escalated.
- The SQLite database lives only in the data dir; the worker never touches the database, only the server writes it.
- Real-weight tests are opt-in (`SONGLOOM_REAL_ENGINE=1`); the default `uv run pytest -q` stays fast.
- Register with `dev` at the end: `dev register songloom 8840 --cmd "uv run songloom serve --port 8840" --cwd ~/projects/songloom`.
