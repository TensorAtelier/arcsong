# m6-release — plan

**Goal:** Build M6 from PLAN.md: one-command install, versioned releases, a README with screenshots and audio samples, and licence notices — so someone who has never seen songloom can install it, understand what it does, and hear it before committing 11 GB of download.
**Already done** (2026-09-17, before this feature): the repo moved to `TensorAtelier/songloom`, history rewritten to the brand identity, `LICENSE` (Apache-2.0), `THIRD_PARTY_NOTICES.md`, a first README, and package metadata at v0.1.0 that builds a correct wheel.
**Not yet:** PyPI (claiming a name there is permanent and the git URL install works today). A Homebrew tap. Auto-update. Signed or notarised anything. A project website on tensoratelier.com. Windows/NVIDIA install docs (M5). CI.
**Stack / interfaces:**
- Packaging: ship `songloom` only — the `spike` measurement harness leaves both the wheel and the console scripts. Settle `requires-python` against what actually runs.
- Media: `docs/media/` holds screenshots (PNG) and short audio samples (MP3, transcoded from real FLAC renders with ffmpeg), with `.gitignore` exceptions so they survive the blanket audio/image rules.
- Release: `CHANGELOG.md`, a `docs/release.md` runbook, an annotated `v0.1.0` tag and a GitHub Release carrying the built wheel and sdist.
**Proof of done:** On a machine that has never run songloom, `uv tool install git+https://github.com/TensorAtelier/songloom` puts exactly one command on PATH, `songloom serve` opens a page whose Setup panel explains what it needs, and the README shows what the app looks like and lets you hear what it makes before you download anything. `gh release view v0.1.0` shows the release with its notes and artifacts.

## Tickets

- [x] 01 — Package hygiene: ship `songloom` only (drop `spike` from `[project.scripts]` and the wheel's packages), settle `requires-python` against the Pythons it actually runs on, and confirm the wheel carries the built page, the soundfont and the licence; check: build, install into a throwaway `uv tool` environment, confirm one entry point, run `songloom serve` against the real weights and stop it.
- [x] 02 — Real samples and screenshots: render 2–3 short songs on the real engine, transcode ~45 s excerpts to MP3 for the repo, and capture page screenshots (Create, Compare, Score, Library, Setup) from a server holding those songs; check: files exist under `docs/media/`, each MP3 plays and is under 1.5 MB, each PNG is legible at README width.
- [x] 03 — README for a stranger: rewrite around the media — what it makes (samples), what it looks like (screenshots), what it needs, how to install, upgrade and remove it (including what `uv tool install` actually creates), where data lives, and what the CC BY-NC weights mean; check: every relative link and image path resolves, and the install commands are the ones ticket 01 verified.
- [ ] 04 — Release mechanics: `CHANGELOG.md` for 0.1.0, a `docs/release.md` runbook, then an annotated `v0.1.0` tag and a GitHub Release with the wheel and sdist attached and notes pointing at the README; check: `gh release view v0.1.0` and a download of the attached wheel installs.

## Notes

- **No PyPI in this release.** Publishing a name there can be yanked but never reclaimed or replaced, and the git URL install already works; the README says how to install without it. Revisit when the app has users.
- **Cutting the tag and the GitHub Release is public and is the last thing done**, after everything else is verified — and it waits for an explicit go-ahead, since a release under the org is outward-facing in a way a commit is not.
- `spike` stays in the repository (it is the M0 evidence and its tests run in CI-less verification), it just stops being part of the distributed package: `[tool.hatch.build.targets.wheel] packages = ["songloom"]`.
- Samples are MP3 rather than the FLAC songloom produces: GitHub serves them inline, they are a tenth of the size, and nobody needs lossless to decide whether to install something. The FLACs stay out of the repo.
- Screenshots come from a server with the real rendered songs in its library, not the fake engine, so what the README shows is what a user gets. Dark theme, since that is what the page defaults to on this Mac.
- Samples and screenshots are made in the same session on real weights (about 20 minutes of GPU on AC power), so the Library shot has real durations and sizes in it.
- The Python version question from the install dry run is ticket 01's: the wheel says `>=3.12,<3.13`, yet `uv tool install` put it on 3.14.4 where it ran fine. Find out which Pythons genuinely work before widening or narrowing the pin — mlx-Yue pins exact versions of mlx, mlx-lm and transformers, so the constraint may belong to them rather than to songloom.
- `requires-python` was `>=3.12,<3.13` and the pin was stale: the full suite passes on 3.12, **3.13.13 and 3.14.4** (240 passed each, in throwaway venvs), and mlx imports with Metal available on 3.14. Widened to `>=3.12`. Real rendering is still only exercised on 3.12, which is what the project venv uses.
- The sdist carried the M0 harness, the agent notes and the web sources (8.9 MB). It now holds the app, its tests and the licence files only; the wheel ships `songloom` and one console script.
- Verified by installing the built wheel itself, not the git URL: one executable on PATH, no `spike`, page serves on a fresh data dir.
- Renders refused three times with mlx-Yue's `MemoryError: System memory pressure is not normal (level=2)` while ComfyUI held 4 GB and a VM 1.5 GB. The machine read pressure level 1 when idle; loading the 11 GiB model spiked it. Fixed the message (a release shouldn't show a port's traceback) and re-ran once ComfyUI was closed: three songs in about four minutes.
- The licence acknowledgement is the user's to give, so the samples session stopped and asked rather than clicking it through the API. That exposed the button's weight: the *disabled* download button was the loud one and the required step was a quiet outline. The licence section now carries an accent rule, a "needs you" chip and the only primary button on the page until it is done.
- Screenshots come from the real app with the real songs in it (five songs, real durations and sizes), cropped to content and downsampled to 1600px; samples are 45 s MP3 excerpts at 160 kbps, 880 KB each, checked for level (mean ≈ −17.7 dB, peaks just under 0, no clipping).
