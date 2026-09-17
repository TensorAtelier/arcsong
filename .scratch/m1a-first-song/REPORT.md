# m1a-first-song — report

- Plan: `.scratch/m1a-first-song/plan.md` · Size: lite · Mode: auto
- Branch: `feat/m1a-first-song` (base `61d6908`) · Built 2026-09-17

## Tickets

| # | Ticket | Commit | Check |
|---|---|---|---|
| 01 | Server, database and queue with a fake engine | `4f49cb0` | 5 API tests; curl against a running fake server |
| 02 | Real mlx-Yue worker | `a09d498` | opt-in real render test (25 s); two curl renders, the second faster on the warm model |
| 03 | Live progress and cancel | `daeff99` | 9 tests; real server: SSE Stages, ~4 token updates/s, synthesis `N/32`, cancel mid-synthesis in 0.19 s with no Take left |
| 04 | Worker crash and restart recovery | `a159631` | 3 tests (crash, grace kill, restart recovery), stable over 5 repeated runs |
| 05 | Bare Create page | `bf9062d` | browser end to end on the real engine: generate, progress, song playable (decoded 23.2 s stereo), cancel; found and fixed two bugs |

Parked: none.

## Review (verbatim)

```
GOAL VERDICT: PARTIAL

Checks: `uv run pytest -q` passed (157 passed, 1 skipped, which is the opt-in real-engine test). `uv run ruff check .` reported "All checks passed!". `cd web && npm run typecheck` (tsc --noEmit) exited clean. I also rebuilt `web/` into scratch and it is byte-identical to the committed `songloom/static/`.

What I ran:
- Fake-engine server on 8842: create job → SSE stream → done → GET audio.
- CLI restart: 3 jobs, SIGINT mid-job, restart.
- Shutdown and crash cases: SIGTERM and SIGINT with an SSE client open, SIGKILL of the server, and `--engine mlx` with missing weights.
- Uvicorn in-process: counted SSE subscribers after clients disconnected.
- TestClient script: FLAC content type, and `seq` across a restart.

Real-engine run blocked: I could not do a real render. The user's `songloom serve --port 8840` (pid 87885, started via `dev` at 03:30 during my session) holds the Lyra GPU lock. My 8842 worker died with `RuntimeError: Another Lyra process owns the GPU` and restarted 16 times. I left 8840 alone. Scratch data is deleted and no process of mine is left.

STORIES:
- 01. delivered. `test_a_job_runs_to_a_playable_song` and `test_jobs_run_one_at_a_time_in_order`. By curl on 8842: job went queued → running → done, GET `/api/songs/1/audio` returned 200 `audio/wav`, and `/` served the page.
- 02. delivered, not re-verified by QA. `mlx_engine.py` loads once and reuses the pipeline, uses the staged API, and saves into `out_dir`. The song row is written only when the server handles `done`, which the worker sends after `save_artifacts` returns (`runner._handle` → `Store.add_song`). The opt-in `tests/test_real_engine.py` exists; I could not run it because of the GPU lock above.
- 03. delivered on the fake engine; the real-engine progress path is unverified.
  - SSE: carried queued → running → stage and progress snapshots → done.
  - Tests: throttling, flush-before-stage order, queued/running/finished cancel and cancel latency under 1 s are covered by `tests/test_progress_live.py`.
  - Cancel by job id holds: the worker stops only when `cancel_job.value == job_id`, `_handle` resets it to `NO_JOB` under the lock, and a late cancel sees the DB status is final and returns 409.
  - Real synthesis `N/steps`: `lyra` builds `Progress()` per stage, which reads `sys.stderr` when called, so `StderrCounts` should catch the lines. That is code reading only; I did not see it run.
- 04. partial.
  - Delivered: a crash mid-job fails the job and the next job runs on a new worker, and a job that ignores cancel is killed after the grace period (both tests pass). On restart through the CLI, job 1 (running) became `failed "the server stopped while this job was running"`, and jobs 2 and 3 ran in order to done.
  - Gaps: a worker that fails while loading the model restarts endlessly with an unhelpful error; a SIGKILLed server leaves its worker orphaned; SIGTERM hangs while a page is open (defects 1–3).
- 05. partial.
  - Delivered: the form, queue panel, Stage and progress display, cancel button, audio player and served build all exist. The FLAC fix works: a `.flac` song is served as `audio/flac`. Within one server run, the `seq` ordering is correct, because `job()` reads the DB and takes `seq` under the same runner lock.
  - Gap: `seq` restarts at 1 when the server restarts, so an open page silently drops every later update for jobs it already knows (defect 4). I did not drive a browser.

DRIFT:
- Notes bullet 2 and PLAN.md "shared cancel `Event`": the code uses `mp.Value("q")` holding the id of the job to cancel. This is a deliberate improvement, but it contradicts the ledger wording.
- Stack "`./data` in dev": there is no `./data` default. The dev registration runs against `~/Library/Application Support/songloom` unless `--data` or `SONGLOOM_DATA` is set.
- Proof of done "Stopping and restarting the server…": in practice the user has the page open (the proof starts by opening it). In that state the server does not stop on SIGTERM, and the page does not show what happened after the restart.
- Not-yet items: none crept in. There is no library, setup, doctor, finalize or styling work.

RISKS (ranked):
1. `dev restart songloom` with a browser tab open.
   - The old process frees the port but never exits, and its worker keeps the Lyra GPU lock.
   - `dev` then starts a new server, whose worker hits "Another Lyra process owns the GPU" and restarts endlessly (confirmed on 8842).
   - Every job fails with "the worker process exited unexpectedly (code 1)", and a second ~10 GB model may sit in memory.
2. Stale page after a restart. An open page keeps showing old status for existing jobs (the `seq` reset), for example a resumed queued job stays "queued" forever until reload.
3. Any persistent load failure (missing weights, the `require_ac` check on battery, GPU lock) becomes a CPU-burning restart loop, and the job shows no useful reason.
4. A SIGKILLed or crashed server orphans the worker. It keeps the model and GPU lock and may finish writing into `songs/<id>` after recovery has deleted that directory. The result is a stray, never-indexed directory; it is never served.
5. Minor: a finished Take can be lost at shutdown. If the worker sends `done` during `stop()`, the pump thread has already exited. The job stays `running`, and on the next start `recover()` marks it failed and deletes the completed Take.
6. Minor: cancel on a busy job can be delayed. `_watch` only runs when `events.get(timeout=0.2)` times out, so a stuck job that ignores cancel and still sends events more often than every 0.2 s never gets its grace-period kill. Throttling (at most 4 progress events a second) makes this unlikely.
7. Minor: HEAD on `/api/songs/{id}/audio` returns 404. The request falls through to the static mount; browsers use GET, so playback still works.

What holds up:
- Races: dispatch, cancel and worker events are serialized well. Every job-state change is either under `JobRunner._lock` or on the single pump thread, and worker restarts happen only on the pump thread.
- Partial Takes: I found no path that indexes or serves one.
- SSE cleanup: subscribers went from 5 to 0 within 0.5 s of the clients being killed, and from 3 to 0 for idle clients.

DEFECTS:
1. songloom/app.py:95-106 (the /api/events stream loop): an open SSE client blocks shutdown indefinitely. Uvicorn waits for open connections and the loop sends a keep-alive every second, so it never ends; lifespan runner.stop() only runs after all SSE clients leave. Reproduce: `songloom serve --engine fake --port 8842`, `curl -N localhost:8842/api/events &`, `kill -TERM <server pid>`: "Waiting for connections to close", still alive after 8 s with the port released, exits only when curl is killed. Needed: end SSE streams on shutdown (a stopping flag checked in the loop plus uvicorn timeout_graceful_shutdown). Affects: Proof of done restart, story 04.
2. songloom/runner.py:187-198 (_watch) with songloom/worker.py:24-26: a worker that dies before taking a job is restarted in a tight endless loop, with no backoff or limit; the job error is only "the worker process exited unexpectedly (code 1)" while the real reason (FileNotFoundError, GPU lock, AC requirement) appears only in the server log. Reproduce: `songloom serve --engine mlx --mlx-models /nonexistent/models --port 8842` gave 99 tracebacks in ~25 s; with another Lyra process holding the GPU, 16 restarts in seconds. Needed: the worker catches load errors and sends them as an event; the runner fails the running and queued jobs with that message and backs off or stops restarting. Affects: story 04 (and 02).
3. songloom/runner.py:98-103 (_start_worker, daemon=True): if the server is SIGKILLed, the worker outlives it; it blocks in jobs.get() with no parent-death check. Reproduce: start the fake server, kill -9 the server pid; the spawn_main child is still running 3 s later with PPID 1. With mlx this orphan keeps ~10 GB and the Lyra GPU lock, so a restarted server cannot render (see defect 2). Needed: the worker watches its parent (os.getppid() or a pipe checked alongside jobs.get with a timeout) and exits. Affects: story 04, Proof of done restart.
4. songloom/runner.py:67 (self._seq = itertools.count(1)) with web/src/App.tsx:11-16: seq restarts at 1 on every server start, so the page's keep-the-highest-seq rule discards every new snapshot for jobs it already knows. Reproduce: a TestClient script on one data dir got seq 68 for job 1 on the first app and seq 1 for the same job after restart; in a browser, EventSource reconnects and a job that resumed after the restart never updates. Related: the page does not re-fetch /api/jobs when EventSource reconnects, and Store.recover() changes are never published. Needed: make seq increase across restarts (seed it from time or store it), and reload the list on reconnect. Affects: story 05, Proof of done restart.
5. songloom/runner.py:80-91 (stop): a Take that finishes while the server is stopping is thrown away. The pump thread exits as soon as _stopping is set, so a done event sent after the cancel check (while save_artifacts runs) is never handled; the job stays running, and on the next start recover() fails it and _discard_partial_take deletes the complete Take. Found by code reading, not run. Needed: drain the events queue after the worker exits in stop(). Affects: story 04 (edge).
```

(The five DEFECTS entries are condensed from the reviewer's multi-line bullets without changing their content.)

## Fixes after review (2026-09-17)

The user asked to continue after the review, so all five defects were fixed on this branch. `tests/test_shutdown.py` has one test per defect; all five fail on the pre-fix code (checked in a temporary worktree) and pass after.

| Defect | Fix | Checked |
|---|---|---|
| 1. An open SSE page blocks shutdown | `songloom serve` runs a uvicorn `Server` subclass whose `handle_exit` sets `app.state.shutting_down`; event streams end on it; `timeout_graceful_shutdown=5` as a backstop | real subprocess test; real mlx-Yue server with a stream open exits 2 s after SIGTERM, worker gone. It had also happened for real: the `dev`-stopped server (pid 87885) and its worker were still alive, holding the GPU, and had to be killed. |
| 2. Load failure → endless restart loop, no reason shown | worker catches load errors and sends `load_failed`; the runner fails the waiting job with "The model could not load: <reason>" and starts another worker only when a job needs it, at least 5 s later; a worker that dies before `ready` is treated as a load failure | fake-engine test (2 jobs fail with the reason, ≤3 worker starts, none while idle); real server with missing weights: job fails with `FileNotFoundError: /nonexistent/models/converted`, no restart loop |
| 3. A SIGKILLed server orphans its worker | the worker gets the server pid and a daemon thread exits when its parent changes (checked every 1 s, also mid-render) | real subprocess test: worker exits within 5 s of `kill -9` on the server |
| 4. `seq` resets on restart; the page doesn't reload on reconnect | `seq` starts from microseconds since the epoch; the page reloads `/api/jobs` on every EventSource (re)connect | restart test: `seq` after restart > before |
| 5. A Take finishing during shutdown is discarded | `stop()` joins the pump thread first, waits up to 5 s for the worker, then drains remaining worker events | test: a job still running at shutdown is `done` with playable audio after restart |

Also: `_watch` now runs on every pump pass (review risk 6: a busy job that ignores cancel still gets its grace-period kill).
Not fixed: review risk 7 (HEAD on the audio endpoint returns 404; browsers use GET).

## Parked tickets

None.

## Look here first

1. **All five review defects are fixed** (see "Fixes after review"). The fixes weren't re-reviewed by a fresh QA agent; each has a test that fails on the old code, and the two that hit the user were rechecked on the real engine.
2. **Precision and data-dir defaults:** 8-bit, 32 steps, data in `~/Library/Application Support/songloom` (see Decisions).
3. **Review risk 7 is still open:** HEAD on `/api/songs/{id}/audio` returns 404 (harmless for browsers).

## Decisions made for you

From the plan's Notes, ranked costly-and-surprising first:

- **Schema v1** (`jobs`, `songs`, `user_version` pragma), not escalated because no real user data existed. It will hold your songs from now on.
- **Data dir** defaults to `~/Library/Application Support/songloom` (not `./data` as the plan's stack line said, per review DRIFT).
- **Built web assets are committed** in `songloom/static/`, so the app runs without Node; rebuild with `cd web && npm run build`.
- **Registered with `dev`** on port 8840 (`uv run songloom serve --port 8840`).
- **Defaults:** 8-bit precision (speed only, per M0), 32 steps with 8 as "Quick draft", planning mode `full`, random seed shown on each job.
- **Worker design:** one spawned worker owns the model; server ↔ worker via queues; cancel targets a job id through a shared value (a deviation from PLAN.md's shared `Event`, so a late cancel can't stop the next job).
- **A song is indexed only after `save_artifacts` returns**, and unfinished jobs' song directories are deleted (M0 open risk).
- **Progress:** `on_token` running count plus yue2 stderr `N/total` for synthesis, coalesced to at most 4 updates/s; job snapshots carry a `seq` so the page keeps the newest.
- **Cancel grace:** a running job that ignores cancel is killed after 10 s and its worker replaced.
- **Real-weight tests are opt-in** (`SONGLOOM_REAL_ENGINE=1`); the default suite stays fast.
- **The engine adapter lives in `songloom/`**, modelled on the spike's `MlxYueEngine` rather than importing `spike`.
