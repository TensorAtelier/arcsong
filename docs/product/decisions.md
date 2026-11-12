# Decisions

## 2026-11-11 — cycle 5

- North star: 0 stars (same day as cycle 4's snapshot; no new row). Nothing announced yet.
- Owner, this session: set up RunPod (Claude Code plugin signed in; `runpodctl` 3.1.0 with `RUNPOD_API_KEY` in `~/.zshrc`; $15 balance) and ran `/pm` — the key cycle 4 named as runpod-serverless's blocker.
- Owner call (in chat, asked by the PM): RunPod test spend **up to $3** of their balance; anything left deployed may stay. By: owner.
- Picked:
  - X-002 (experiment, not a build): runpod-serverless stays at 0.30 — confidence 0.4 because two unknowns surfaced in orient: yue2 0.1.5 pins torch 2.10.0 while Flash GPU workers run torch 2.9.1 and drop torch pins, and RunPod caps a job's result at 10 MB while a Take is ~50 MB. Low confidence on a real ask → the smallest test first (rubric).
  - announcement-v0.5.0 draft (`docs/product/announcement-v0.5.0.md`) — cycle 4's "next": the post is the only lever on the north star; the owner posts it.
- Design found on the way: `runpod.Model` stages the 7.3 GB 3B weights on the host before a worker starts, so a RunPod engine needs no network volume (the 0.53 GB VAE downloads on the worker) — no monthly storage bill.
- X-002: **kept** — yue2 renders on Flash's torch 2.9.1 (70 s song, 38 s on a 4090, 167 s from cold), files return complete in 1 MB stream chunks, $0.18 for six runs. runpod-serverless rescored 0.30 → 0.60 (C 0.4 → 0.8) and picked as the cycle's build (chain 1). Above song-metadata (0.50) on score and on the owner's evident ask.
- Shipped: **v0.6.0** (https://github.com/TensorAtelier/arcsong/releases/tag/v0.6.0) — `--engine runpod`, plus the fix for v0.5.0's Modal install line (`uv tool install` left `modal` off PATH; both cloud installs now use `--with-executables-from`). The tag installs in isolation with `arcsong`, `rp` and `runpod` on PATH and serves Setup on `--engine runpod`.
- QA: FAIL first, four defects, all fixed before merge — Setup missed the key `rp login` saves; failures showed whole tracebacks; a lost stream left the job billing; Cancel only cancelled the job record while the GPU kept working.
- Incident: the first two cancel fixes broke the real worker — a job queued after a cancel failed with "CUDA error … previous error during capture". The worker logs showed RunPod loads a fresh copy of the app module per job in the same process, so a module-level lock didn't hold and the next job's generation overlapped the cancelled one. Fixed with the lock and pipeline on `sys`, and stops only at stage boundaries (a cancelled song can hold the GPU ~90 s). Re-verified on RunPod: cancel mid-semantic, then a plan (22 s) and a song (24 s) both succeed.
- Release QA: verify green (305 passed, ruff, tsc); `scripts/release-qa` J1–J5 pass. J7 on RunPod: pass — Set up on RunPod (deploy 65–100 s), sketch of two 2.6-min takes (196 s cold, ~60 s warm), Finalize, Plan a melody, live progress, Cancel, Library playback. J6 real weights: **pass** after the release, at the owner's ask — 6/6 real-engine tests (render, Finalize, Score-only, render from an edited Score, covers download, full cover) in 152 s on battery with v0.6.0's code; first J6 since cycle 1.
- Spend: ~$0.55 of the owner's $3 RunPod budget (X-002 $0.18). Left on the account: the `arcsong` endpoint (`render`, scales to zero, nothing billed while idle).
- Metrics: same day as cycle 4's snapshot; no new row.
- Shortcuts: a cancel waits for the current stage to end — repay if users cancel often on RunPod (needs a CUDA-safe stop inside generation). J6 repaid (run on battery: it no longer needs AC).
- Owner question this cycle: better audio quality. Already in the app: 32 synthesis steps (Make the song / Finalize) and bf16 on the Mac; output is yue2's own 48 kHz FLAC. Candidate added for next cycle: a local mastering pass on download (loudness + limiter), unscored.
- Next: the announcement (now `announcement-v0.6.0.md`: Mac, Modal and RunPod) is still the only lever on the north star — the owner posts it. Build candidates: mastering pass, song-metadata (0.50), covers on the cloud engines.

## 2026-11-11 — cycle 4

- North star: 0 stars (Δ 0 since 2026-10-17; 22 unique cloners, mostly CI; nothing announced, so the kill clock hasn't started).
- Since cycle 3, outside `/pm`: nine owner-requested UI changes on `main` (section buttons and hints, Library lyrics toggle, lyrics tidying, Make the song / Sketch buttons, Seed in Advanced, the style dictionary, Make instrumental). Unreleased; they ship with this cycle's release.
- Picked (chain 1, one release, v0.5.0):
  - cloud-engine-modal (rescored 0.73: I4 C0.8 core2 / E5 Cx3 R0 U1 — risk 0: a new `--engine modal`, the Mac engine untouched; upkeep 1: the remote image pins its own yue2 wheel and weights revision). The owner asked about it three times since cycle 3; it is the roadmap's next entry and what lets Windows, Linux and small Macs make songs at all.
- Owner call from cycle 3 (how a user connects Modal) — decided by the PM, not escalated: it creates no account or key and stores nothing, so it is cheap to undo. The user installs `arcsong[modal]`, runs `modal setup` once (Modal's own login, kept in `~/.modal.toml`), and Setup's Download deploys a Modal app named `arcsong` into their workspace and fills its weights Volume. Arcsong never sees or stores a token. By: PM (the cycle-3 default; the owner's three asks raised no objection).
- Spend: testing on the owner's Modal account inside the approved $30 monthly credit, capped at $5 for this cycle.
- Scope cut (Not yet): covers on Modal (SheetSage2 stays on the Mac engine), RunPod (next on the roadmap, same remote shape), a precision choice on Modal (yue2 on CUDA renders bf16).
- J6 real weights: the Mac is on battery again (60%); fourth release without it.
- Shipped: **v0.5.0** (https://github.com/TensorAtelier/arcsong/releases/tag/v0.5.0) — cloud-engine-modal plus the nine owner-requested UI changes. CI green on b3ca4ee (seven jobs, the journeys included); the tag installs with `uvx --from 'arcsong[modal] @ git+…@v0.5.0'` and serves Setup on `--engine modal`.
- Build: lite pipeline, four tickets (`.scratch/cloud-engine-modal/REPORT.md`). Goal-mode QA: PASS WITH NOTES; seven of eight findings fixed before merge (app-versioned deploy marker, call-loop tests, one-line deploy errors, last-event drain, Modal-side cancels no longer kill the worker, README figures, a docstring); one left (wording when finalizing a Modal Draft on the Mac — unsupported and documented).
- Release QA: verify green (289 passed, ruff, tsc); `scripts/release-qa` J1–J5 pass locally and on CI. J7 Modal (new journey): pass — Set up on Modal, sketch of 2, Finalize (16 s), Plan a melody (13 s), live progress, Cancel mid-render, Library playback; $0.15 of the owner's Modal credit. J6 real weights: **not run** (battery).
- Incidents: no L4 was free on Modal, so the first take waited ~14 min with no runner — `Renderer` now falls back to A10G and L40S. `FunctionCall.get(timeout=…)` blocks while a call is pending — the engine waits on a side thread.
- Left running on the owner's account: the deployed `arcsong` app (scales to zero, nothing billed while idle) and the weights Volume `arcsong-yue2-weights` (from X-001).
- Metrics: 0 stars, 22 unique cloners (mostly CI), 8 unique views, 1 download (Δ +13 cloners, +5 views since 2026-10-17; nothing announced).
- Shortcuts: J6 not run — repay on AC power before the announcement (fourth release); the README's Modal cost figure is X-001's L4 number, not a fresh one — repay when a full-quality song is next rendered on Modal.
- Next: the announcement is now the only real lever — v0.5.0 is the first release that reaches people without an Apple Silicon Mac, which widens who can star it; the PM drafts a new post (the v0.2.0 draft is stale) and the owner posts it. Build candidates: runpod-serverless (0.30, needs a RunPod API key → NEEDS-YOU when picked), covers on Modal, song-metadata (0.50). If nothing is announced by next run, the cycle is maintenance-sized.

## 2026-10-18 — cycle 3

- North star: 0 stars (no new snapshot: the machine clock is still on 2026-10-17; v0.3.0 has 0 downloads; nothing announced)
- Picked (chain 2 features, one release, v0.4.0):
  - e2e-in-ci (0.84: I3 C0.7 core2 / E3 Cx1 R0 U1) — run `scripts/release-qa` on CI so a broken core journey can't reach a release unnoticed.
  - lyrics-help = lyrics-check (0.67: I2 C0.5 core2 / E2 Cx0 R0 U1) + length-estimate (rescored 0.80: I1 C0.8 core2 / E1 Cx0 R0 U1 — X-001 measured 71 s for a verse + chorus, ~165 s for a full song) — one feature: both live under the Lyrics box. Flags what YuE2 reads badly (no section labels, no blank line between sections, stage directions in brackets/parentheses, very long lines) and estimates the length.
- Passed over: song-metadata (rescored 0.50: needs `mutagen`, upkeep 1); cloud-engine-modal (0.58) — a week's build, next cycle with nothing else beside it.
- Repay from cycle 2: J6 real weights — still on battery this morning; stays open.
- CI: the last run's Windows job was lost by the runner (no log, step never concluded); rerun.
- Shipped: **v0.4.0** (https://github.com/TensorAtelier/arcsong/releases/tag/v0.4.0) — e2e-in-ci, lyrics-help. CI green on 658aeae (seven jobs, the journeys included); the tag installs with `uvx --from git+…@v0.4.0` and serves the committed bundle.
- Release QA: verify green (277 passed, ruff, tsc); `scripts/release-qa` J1–J5 pass locally and on CI. J6 real weights: **not run** — still on battery (64%, discharging); third release without it.
- Incidents:
  - Windows runners died mid-suite twice (no log): the covers-progress test still reserved ~5 GB on NTFS after the truncate fix; it now declares small files.
  - The release commit's journeys failed once with "Chrome did not start" (a 10 s window on a cold runner): now 30 s, and Chrome's own output is printed on failure.
- Metrics: no new row (machine clock still 2026-10-17 at the start of the run); v0.3.0 and v0.4.0 have 0 downloads; nothing announced.
- Shortcuts: J6 — repay on AC power before the announcement; it has now been skipped for v0.3.0 and v0.4.0, so it moves to NEEDS-YOU-level visibility in the next run's opening if still open.
- Next: cloud-engine-modal (0.58) as the cycle's only build — a week's work; it needs one owner call on how a user connects their Modal account (the PM's default: the user runs `modal setup` themselves and Arcsong uses that login; no keys stored by Arcsong). The announcement is still the lever on the north star; until it goes out, stars stay at 0 and the kill clock hasn't started.

## 2026-10-17 — cycle 2

- North star: 0 stars (Δ 0; same day as v0.2.0; announcement not posted yet)
- Owner requests (in the `/pm` call): a song name, with existing songs backfilled; a random-style button next to Style; remove the style suggestion chips (too much space).
- Picked (chain 3, one release, v0.3.0):
  - style-dice (1.40: I2 C0.7 core2 / E1 Cx0 R0 U1) — owner request; chips removed, a dice button fills a random tag-form style (genre, mood, instruments, voice) in the shape YuE2 was trained on.
  - release-qa-script (0.93: I2 C0.7 core2 / E2 Cx0 R0 U1) — cycle 1's scratch journeys as one repo command; this release's QA runs through it.
  - song-name (0.84: I3 C0.7 core2 / E3 Cx1 R1 U0) — owner request; outranks e2e-in-ci (0.84) on the tie because the owner asked.
- Interpretation (taste anchored in the charter, cheap to undo — decided, not escalated): "song name" = (1) an optional **Song name** field in Create, shared by every take of a sketch, and (2) every song **stores** its name: existing songs are backfilled with the name they show today (their first sung line), so names never shift if the default rule changes. Rename and "blank resets to the default" keep working.
- Owner, mid-cycle: "i want song name to be required." → the Song name field is required in Create's Write and Plan tabs and in Cover (submit disabled until named). The API keeps `title` optional (falls back to the first sung line), so scripts, old jobs' Retry/Render-again and the test suite keep working. By: owner (requirement), PM (where it is enforced).
- Passed over: e2e-in-ci (0.84) — next cycle, on top of release-qa-script; lyrics-check (0.67, new: warn on lyrics YuE2 reads badly) — candidate; cloud-engine-modal (0.58).
- Shipped: **v0.3.0** (https://github.com/TensorAtelier/arcsong/releases/tag/v0.3.0) — style-dice, song-name (with the owner's mid-cycle "required"), release-qa-script. CI green on 0a06fe8; the tag installs with `uvx --from git+…@v0.3.0` and serves the committed bundle.
- Backfill on the owner's library: backed up `arcsong.db` (`arcsong.db.before-v6-20261017-135349`), restarted → schema 6; all six songs store the names they showed.
- Release QA: verify green (277 passed, ruff, tsc). `scripts/release-qa` (now a repo command): J1–J5 pass — unnamed song refused, "First Light" kept after restart, sketch "Neon Run" with its Final, rename/download/delete, Score, cover. Manual steps listed in product.md (piano preview, play across views, cover render, keys 3–4, Setup progress) not re-walked: no code they use changed this cycle. J6 real weights: **not run** — the Mac was on battery (release.md asks for AC); risk judged low (the only engine-facing change is an extra `title` key the engine never reads, checked by QA).
- Incidents:
  - A merge (feat/song-name) landed a failing test: the gate was `pytest | tail`, which hides pytest's exit code. Fixed in the next commit (1b6bc23); lesson saved to the PM's memory (gate on pytest's own exit code).
  - Windows CI ran out of disk twice in `test_a_parts_progress_counts_only_its_own_files` (it wrote ~5 GB); now sized with truncate.
- Metrics: same day as the last snapshot (0 stars, 9 cloners, 3 views, 1 download); no new row.
- Shortcuts: J6 not run — repay before the announcement, on AC power (`dev stop arcsong` first). Manual release steps not re-walked — repay next cycle that touches Score, playback or covers.
- Next: e2e-in-ci (0.84) — `scripts/release-qa` on CI (macOS runner has Chrome); lyrics-check (0.67, warn on lyrics YuE2 reads badly); cloud-engine-modal (0.58). The owner's announcement post is still the biggest lever on the north star; nothing measures until it goes out.

## 2026-10-17 — cycle 1

- North star: 0 stars (Δ 0 since the 2026-10-17 baseline, same day)
- Picked (chain 3, one release, v0.2.0):
  - metrics-script (1.50: I3 C1 core1 / E1 Cx0 R0 U1) — GitHub keeps traffic 14 days; every run without it loses data.
  - score-zero-notes (1.00: I2 C0.5 core1 / E1 Cx0 R0 U0) — a visible defect on a page a new user opens; one hour.
  - readme-v0-2 (0.83: I5 C0.5 core1 / E2 Cx0 R1 U0, part of v0.2.0-and-announce, approved N-003) — the README shows the old UI; v0.2.0 and the announcement need it.
- Alongside, not a build: X-001 Modal spike (1.33), approved N-002, running in the background.
- Passed over: release-qa-script (0.93) — next cycle; this cycle's release QA is run by hand with the CDP driver. song-metadata, length-estimate (1.00 each, impact 1) — tie on score with score-zero-notes but move nothing a new user sees first.
- Pipeline size: lite for all three (`--lite`) — each is about an hour; the full spec/ticket/agent pipeline would cost more than the work.
- Landing: merge — solo repo, no PR workflow, CI on main.
- Shipped: **v0.2.0** (https://github.com/TensorAtelier/arcsong/releases/tag/v0.2.0) — metrics-script, score-zero-notes, readme-v0-2, and sketch-ready-link (a release-QA fix); plus the work since v0.1.0 (redesign, titles, player, battery default, CI on three OSes, swap-stop fix). CI green on de80f52; wheel checked (no `spike`, fonts and soundfont inside); the tag installs with `uvx --from git+…@v0.2.0` and serves the same bundle.
- Release QA: verify green (271 passed, ruff, tsc). Journeys on a fresh fake-Engine server in a headless browser, no console errors:
  - J1 first song [core]: pass — Create gated before Setup; licence → download → Single song → bar plays (0:02/0:20) → still in the Library after a server restart.
  - J2 sketch and pick [core]: **failed, then pass** — the Compare link vanished when the sketch finished (fixed: sketch-ready-link); keys 1/2 switch at the shared time (1.91 → 2.27 s), Space pauses, S stars, Finalize lands in the sketch card; no overflow at 390 px.
  - J3 library [core]: pass — empty search message, Starred filter, rename via ⋯, download named `arcsong-1-kettle-song-take-one.flac`, delete with confirm; no overflow at 390 px.
  - J4 score: pass — plan → notation + valid check → edit (badge) → render queued.
  - J5 cover: pass — covers download → upload a WAV → transcribed Score.
  - J6 real weights: pass — 6/6 in 164 s (first attempt failed: the owner's running Arcsong held the GPU lock; stopped it, reran, restarted it; `docs/release.md` now says to stop it).
- X-001: **kept** — 3-minute song at 32 steps ≈ $0.045 and ≈ 200 s from a cold Modal L4 (success line: ≤ $0.10, ≤ 12 min). cloud-engine-modal rescored 0.36 → 0.58.
- Metrics: 0 stars, 9 unique cloners, 3 unique views, 1 download (Δ 0, same day as the baseline).
- Shortcuts: release QA ran from scratch scripts, saved as `.scratch/release-qa-script/seed/` — repay when release-qa-script lands (next cycle). Real-weights tests need the owner's Mac — repay never (by design), documented in `docs/release.md`.
- Next: release-qa-script (0.93) then e2e-in-ci (0.84) — make journeys 1–5 one command and run them on CI; then cloud-engine-modal (0.58), which will need a decision on how users authenticate Modal from inside Arcsong. The owner's announcement post (`docs/product/announcement-v0.2.0.md`) starts the clock on the kill criteria: if it goes out, next run's snapshot is the first real data point. A RunPod API key will be asked for when runpod-serverless is picked.

## 2026-10-17 — N-003: v0.2.0 and announcement

- Context: charter-mode escalation (public).
- Decision: tag v0.2.0 once the README is redone, then announce in one place first. The PM writes the post; the owner publishes it (it posts as them).
- Why: a star baseline only means something after a single, known announcement.
- Reversibility: costly (public)
- By: owner ("ok")

## 2026-10-17 — N-002: Modal spend for X-001

- Context: charter-mode escalation (money).
- Decision: run X-001 on the owner's existing Modal account, inside its $30 monthly credit; the experiment is capped at $10 of usage. RunPod account registered with the owner's SSH key; creating RunPod machines from scripts will need an API key — asked for when RunPod work is picked.
- Why: owner answer.
- Reversibility: cheap
- By: owner

## 2026-10-17 — N-001: charter confirmed

- Context: charter-mode escalation (charter).
- Decision: `product.md` accepted as drafted, except `ship: auto` (the draft said ask).
- Why: owner answer.
- Reversibility: cheap
- By: owner

## 2026-10-17 — charter drafted

- Context: first `/pm` run (`--plan`, with the owner asking about features, testing, QA, Modal
  and RunPod). No `docs/product/` existed, so this was charter mode.
- Decision: drafted `product.md` from `PLAN.md`, the README, `TARGET.md`, `HANDOFF.md` and the
  public repo numbers; seeded `backlog.md` with 14 scored candidates and experiment X-001;
  `metrics.md` with three `gh api` sources and a baseline snapshot.
- Why: a charter is the only thing the PM can score against; the owner's asks became backlog
  rows rather than a separate plan.
- Reversibility: cheap — every `(inferred)` field waits in `NEEDS-YOU.md`.
- By: PM

Proposed first cycle once the charter is confirmed (not started — `--plan`):

- Pick: metrics-script (1.50), score-zero-notes (1.00), release-qa-script (0.93).
- Then, on approval: X-001 cloud spike (1.33, money), v0.2.0-and-announce (0.83, public).
- Passed over: cloud-engine-modal (0.36) and runpod-serverless (0.30) until X-001 says the cost
  and speed are worth it; ai-lyric-writer (0.17) — no anchor in the charter and heavy upkeep.
