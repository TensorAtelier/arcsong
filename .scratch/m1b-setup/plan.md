# m1b-setup — plan

**Goal:** Build the M1b Setup page from PLAN.md: model download with progress, `doctor`, licence acknowledgement, RAM check — so a fresh clone gets from one install command to a first song without following the README by hand.
**Not yet:** Choosing which precisions to download (all of them come down). Idle unload of the model. A measured RAM floor (needs a 16/24 GB Mac). Transcription weights (M4). NVIDIA (M5). Moving existing weights into the data dir. Deleting weights from the page.
**Stack / interfaces:**
- API: `GET /api/setup` (checks, weights state, licence, download state, `ready`), `POST /api/setup/checks` (run the checks again), `POST /api/setup/licence` (acknowledge), `POST /api/setup/download` and `POST /api/setup/download/cancel`; SSE `setup` messages while a download runs. `POST /api/jobs` answers 409 while the weights are not installed.
- Page: a third view, Setup (`#/setup`), in the nav with a warning mark when not ready; the page opens on Setup while it isn't; Create shows a one-line link to Setup instead of queueing into a failure.
**Proof of done:** Start `songloom serve --data <empty dir>`: the page opens on Setup, lists the checks (Apple Silicon + Metal, macOS, RAM, AC power, free disk, weights), shows the CC BY-NC 4.0 licence with links, and only after "I acknowledge" offers Download (~9.8 GB). The download shows a byte progress bar, can be cancelled and resumed, cleans the hub metadata, verifies the weights, and then Setup turns ready and Create can make a song. With the existing weights (`--mlx-models ~/projects/mlx-Yue/models`) Setup shows the weights as installed straight away.

## Tickets

- [x] 01 — Setup checks API: a `Models` seam (mlx + fake) reporting weights state from pinned file sizes, doctor checks (platform/Metal via a short subprocess, macOS, RAM, power, free disk, weights, mlx-yue commit), `GET /api/setup` and `POST /api/setup/checks`; the default weights dir moves to `<data>/models`; jobs refused with 409 while weights are missing; check: API tests with the fake, and `GET /api/setup` against the real weights dir.
- [x] 02 — Licence acknowledgement: `POST /api/setup/licence` stores the acknowledgement (licence id + time) in SQLite and it survives a restart; download refuses (409) without it; check: API tests.
- [x] 03 — Model download: runs in a spawned process at pinned revisions (`vanch007/mlx-Yue2-3B@fa66d20…`, `m-a-p/YuE2-Vae` at mlx-Yue's pin), reports bytes to the server, deletes `.cache` and `.gitattributes`, verifies with `verify_conversion` + `model_identity`, cancel kills the process and a retry resumes; SSE `setup` messages; check: API tests through a fake download (progress, cancel, failure, success → ready), and one real download into a temporary dir behind `SONGLOOM_REAL_DOWNLOAD=1`.
- [ ] 04 — Setup page: nav tab with not-ready mark, checks list with re-run, licence panel with acknowledge, download bar with cancel/retry and error text, open on Setup while not ready, Create's link to Setup; check: in the browser against a fake-engine server (not-ready → acknowledge → download → ready → Create works).

## Notes

- Weights default to `<data>/models` (was `~/projects/mlx-Yue/models`, a dev-machine path); `--mlx-models` / `$SONGLOOM_MLX_MODELS` still override. The local `dev` registration gets `--mlx-models ~/projects/mlx-Yue/models` so the existing 9.7 GB aren't downloaded again.
- Weights state comes from file presence and pinned byte sizes (instant); full hashing happens after a download (in the download process) and on every model load (mlx-Yue already verifies). No hash on page load.
- The server never imports MLX: the Metal check runs `lyra.runtime.runtime_status()` in a short subprocess, cached until "Run checks again".
- The download runs in its own spawned process (not the GPU worker, not a server thread), so cancel is a kill and the server stays responsive; hub `.incomplete` files make a retry resume.
- Progress comes from a `tqdm_class` passed to `snapshot_download`, whose aggregate byte bar covers every file; the total comes from the pinned sizes.
- All three weight files come down (8-bit AR, bf16 AR, bf16 NAR): `verify_conversion` checks every precision the manifest lists, and the page offers both precisions.
- RAM: warn (not block) below 24 GiB — songs peak at ~11 GiB and the floor is unmeasured (PLAN open question 2). Power: warn on battery, because mlx-Yue refuses to render off AC. Disk: fail when free space is below what is left to download plus 1 GiB.
- The licence acknowledgement gates the download, not song creation: weights that were already on disk (installed by hand) can make songs; the page still shows the licence until acknowledged. The acknowledgement lives in a new `settings` key/value table (additive, no migration).
- Tickets 01–03 share one commit: the checks, licence and download live in one `Setup` object behind the same snapshot, and were tested together.
- A download whose verification failed blocks song creation until the next server start or a successful retry, because sizes alone can't catch a corrupt file (mlx-Yue's load would reject it anyway).
- Setup snapshots carry a `seq` from the job runner's clock, so the page keeps the newest one whether it came over REST or SSE. Partly downloaded bytes (`bytes_on_disk`) show as "incomplete" rather than "not downloaded".
- Real download check (`SONGLOOM_REAL_DOWNLOAD=1`): 10.45 GB in 151 s on 2026-09-17, cleaned and verified, Setup ready.
- Licence copy: "YuE2 weights are CC BY-NC 4.0 — non-commercial use only", links to the CC legal code and the two model pages, and PLAN's neutral note "check the model licence before commercial use of outputs".
