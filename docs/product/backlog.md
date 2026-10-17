# Backlog

Rescored each cycle. Score = (impact × confidence × core) / (effort + complexity + risk + upkeep).
First scoring 2026-10-17, against the draft charter (north star: stars; nothing announced yet).

| Candidate | Source | I | C | Core | E | Cx | R | U | Score | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| metrics-script — `scripts/metrics` appends a `metrics.md` row from `gh api` (traffic is lost after 14 days) | metrics | 3 | 1 | 1 | 1 | 0 | 0 | 1 | 1.50 | shipped cycle 1 |
| cloud-spike — X-001: YuE2 (`yue2`, already inside mlx-Yue) on a Modal L4, one song: time, cost, cold start | research (owner ask) | 4 | 0.5 | 2 | 2 | 1 | 0 | 0 | 1.33 | done 2026-10-17: kept (see X-001) |
| score-zero-notes — Score of song 5 shows "0 vocal notes" (from the UI review) | defect | 2 | 0.5 | 1 | 1 | 0 | 0 | 0 | 1.00 | shipped cycle 1 |
| release-qa-script — scripted journeys 1–5 on the fake Engine over CDP (grown from the scratch driver) | testing (owner ask) | 2 | 0.7 | 2 | 2 | 0 | 0 | 1 | 0.93 | candidate |
| e2e-in-ci — the same journeys headless in CI (Playwright, fake Engine) | testing (owner ask) | 3 | 0.7 | 2 | 3 | 1 | 0 | 1 | 0.84 | after release-qa-script |
| v0.2.0-and-announce — README screenshots + "Your first song", tag v0.2.0, announce | roadmap (M6 leftovers) | 5 | 0.5 | 1 | 2 | 0 | 1 | 0 | 0.83 | README + tag in cycle 1; post is the owner's |
| song-metadata — FLAC/MP3 tags (title, artist "Arcsong", art from the seed gradient) on download | feature | 1 | 0.5 | 2 | 1 | 0 | 0 | 0 | 1.00 | candidate |
| length-estimate — expected song length from the lyrics, shown under Lyrics | PLAN #8 | 1 | 0.5 | 2 | 1 | 0 | 0 | 0 | 1.00 | candidate |
| swap-limit — let Arcsong raise mlx-Yue's 64 MiB swap-out stop (overrides upstream's guard) | defect (2026-10-17) | 2 | 0.5 | 2 | 1 | 1 | 2 | 1 | 0.40 | wait: needs a second real failure after today's fix |
| cloud-engine-modal — `RemoteEngine` + `CudaEngine` over `yue2`, run on the user's own Modal account | research (owner ask) | 4 | 0.8 | 2 | 5 | 3 | 1 | 2 | 0.58 | rescored after X-001 (confidence 0.5 → 0.8) |
| runpod-serverless — the same remote protocol on RunPod serverless (handler + image) | research (owner ask) | 3 | 0.4 | 2 | 3 | 2 | 1 | 2 | 0.30 | after cloud-engine-modal |
| ai-lyric-writer — draft lyrics with a local LLM (Ollama / LM Studio) | feature (riff has one) | 2 | 0.3 | 2 | 3 | 2 | 0 | 2 | 0.17 | parked |
| homebrew-tap | roadmap (M6 leftovers) | 2 | 0.5 | 1 | 2 | 1 | 0 | 1 | 0.25 | parked |
| runpod-pod-template — whole app in a Docker image as a RunPod template | research (owner ask) | 2 | 0.3 | 1 | 3 | 2 | 1 | 2 | 0.08 | parked: needs a CUDA engine and a non-local bind |

Notes on the owner's four asks:

- **Features.** The product is feature-complete for its core use cases; nothing new scores near
  the top because no one is using it yet. The cheapest real movers are distribution
  (v0.2.0 + announce) and reach (cloud rendering for people without a 24 GB+ Mac).
- **Testing.** Unit and API coverage is broad (≈270 tests, CI on three OSes since today). The gap
  is the browser: every UI check so far was manual or a scratch CDP script. Script the core
  journeys first (local, cheap), then put them in CI.
- **QA.** Release QA = journeys 1–5 on the fake Engine + journey 6 on real weights, run before
  each tag. `release-qa-script` makes 1–5 one command.
- **Modal / RunPod.** See X-001. Both are Linux + NVIDIA, so they need a CUDA engine — and the
  official `yue2` PyTorch package already ships inside mlx-Yue, so that engine may be thin.
  Modal first: a Python SDK fits a Python app, per-second billing, a volume for the ~10 GB of
  weights, and users bring their own account (the weights' NC licence rules out hosting).
  RunPod second, on the same remote protocol.

## Experiments

### X-001 — cloud rendering on Modal

- Hypothesis: a song rendered on a Modal L4 costs under $0.10 and arrives within 1.5× the M5 Pro's
  time including cold start, so "render in your own cloud" is a real path for Windows, Linux and
  small Macs.
- Smallest test: a standalone `modal run` script (no Arcsong integration) that loads `yue2` from
  a Modal Volume and renders one 8-step and one 32-step song; record load time, per-Stage time,
  peak VRAM and the bill.
- Success line: 32-step song ≤ $0.10 and ≤ 12 min end to end from a cold start.
- Review: one week after spend is approved.
- Result: **kept** (2026-10-17) — success line held with a wide margin. A 3-minute song (165 s, YuE2's
  own example) at 32 steps: ~200 s and ~$0.045 end to end from a cold L4 (cold start 9 s, weight
  hash check 8–26 s, planning 44 s, semantic 87 s at ~50 tok/s, synthesis 36 s, decoding 6 s) —
  about 2.4× faster than the M5 Pro's 486 s. Peak VRAM 9.6 GiB. Whole experiment ~$0.13 of
  credits. Runs official `yue2` 0.1.5 (wheel inside the `m-a-p/YuE2-3B` repo; torch 2.10 +
  transformers 4.57, which conflict with mlx-Yue's, so the remote side needs its own environment).
  Stages, `on_token`, `cancelled=` and seed-derived noise map onto Arcsong's Engine; synthesis and
  decode progress need a thin wrapper. Script: `spike/modal_yue2.py`; audio in the PM scratchpad.
