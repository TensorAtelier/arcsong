# Roadmap

goal: Private, local YuE2 songwriting for tinkerers that is easy to install and calm to use — and, through the user's own cloud GPU, reachable from machines that can't run the model (charter: docs/product/product.md).
landing: merge

## Features

- [x] metrics-script      — `scripts/metrics.py` writes a snapshot row to docs/product/metrics.md from `gh api` → .scratch/metrics-script/REPORT.md
- [x] score-zero-notes    — the Score page explains a take the model planned with no vocal melody → .scratch/score-zero-notes/REPORT.md
- [x] readme-v0-2         — README for the redesign: new screenshots and a "Your first song" walkthrough (v0.2.0) → .scratch/readme-v0-2/REPORT.md
- [x] sketch-ready-link   — Create keeps the latest sketch's Compare link after it finishes (release QA fix) → .scratch/sketch-ready-link/REPORT.md
- [x] style-dice          — no style chips; a dice button next to Style fills a random tag-form style → .scratch/style-dice/REPORT.md
- [x] release-qa-script   — release journeys 1–5 on the fake Engine as one command over the DevTools protocol → .scratch/release-qa-script/REPORT.md
- [x] song-name           — a required Song name in Create and Cover, shared by a sketch's takes; every song stores its name (existing ones backfilled) → .scratch/song-name/REPORT.md
- [x] e2e-in-ci           — `scripts/release-qa` on CI → .scratch/e2e-in-ci/REPORT.md
- [x] lyrics-help         — under Lyrics: flag what YuE2 reads badly, and estimate the song's length → .scratch/lyrics-help/REPORT.md
- [x] owner-ui-requests   — section buttons and hints, Library lyrics toggle, lyrics tidying, Make the song / Sketch buttons, the style dictionary, Make instrumental (owner requests between cycles 3 and 4)
- [x] cloud-engine-modal  — `--engine modal`: render on the user's own Modal account, set up from Setup → .scratch/cloud-engine-modal/REPORT.md
- [x] runpod-serverless   — `--engine runpod`: render on the user's own RunPod account (Runpod SDK) → .scratch/runpod-serverless/REPORT.md

## Later

- song-metadata: title, artist and cover art written into downloaded files.
- vocal-less takes flagged in Compare and the Library (from score-zero-notes: needs the Score per take).
- swap-limit: an option to raise mlx-Yue's 64 MiB swap-out stop, if the stop keeps tripping.
- Homebrew tap; a project page on tensoratelier.com.
- covers on Modal / RunPod: SheetSage2 in the cloud apps (from cloud-engine-modal's Not yet).
- Modal precision choice (8-bit on CUDA) and finalizing across engines (from cloud-engine-modal).

## Out of scope

- A hosted service or paid tier — the weights are CC BY-NC 4.0.
- Telemetry and accounts — the app is private by design.
- PyPI — a name can be yanked but never reclaimed.
