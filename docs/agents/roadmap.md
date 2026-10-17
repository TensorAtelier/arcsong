# Roadmap

goal: Private, local YuE2 songwriting for tinkerers that is easy to install and calm to use — and, through the user's own cloud GPU, reachable from machines that can't run the model (charter: docs/product/product.md).
landing: merge

## Features

- [x] metrics-script      — `scripts/metrics.py` writes a snapshot row to docs/product/metrics.md from `gh api` → .scratch/metrics-script/REPORT.md
- [x] score-zero-notes    — the Score page explains a take the model planned with no vocal melody → .scratch/score-zero-notes/REPORT.md
- [x] readme-v0-2         — README for the redesign: new screenshots and a "Your first song" walkthrough (v0.2.0) → .scratch/readme-v0-2/REPORT.md
- [ ] release-qa-script   — release journeys 1–5 on the fake Engine as one command over the DevTools protocol
- [ ] e2e-in-ci           — the same journeys headless on CI                                    (needs: release-qa-script)
- [ ] cloud-engine-modal  — render on the user's own Modal account: a CUDA Engine over `yue2` behind a remote worker (needs: X-001 result)
- [ ] runpod-serverless   — the same remote protocol on RunPod serverless                       (needs: cloud-engine-modal)

## Later

- song-metadata: title, artist and cover art written into downloaded files.
- length-estimate: expected song length from the lyrics.
- vocal-less takes flagged in Compare and the Library (from score-zero-notes: needs the Score per take).
- swap-limit: an option to raise mlx-Yue's 64 MiB swap-out stop, if the stop keeps tripping.
- Homebrew tap; a project page on tensoratelier.com.

## Out of scope

- A hosted service or paid tier — the weights are CC BY-NC 4.0.
- Telemetry and accounts — the app is private by design.
- PyPI — a name can be yanked but never reclaimed.
