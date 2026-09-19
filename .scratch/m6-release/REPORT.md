# m6-release — report

**Goal:** One-command install, a versioned release, a README with screenshots and audio samples, and licence notices — so someone who has never seen this can install it, understand it, and hear it before committing 11 GB of download.
**Result:** Released as **[Arcsong v0.1.0](https://github.com/TensorAtelier/arcsong/releases/tag/v0.1.0)**. QA verdict **PARTIAL**; its 5 defects and both machine-level risks are fixed, and the release was re-cut from the corrected commit.

## Tickets

| # | Ticket | Commit |
|---|---|---|
| 01 | Package hygiene: app-only wheel, trimmed sdist, `requires-python` | `800f7f0` |
| 02 | Real samples and screenshots | `e5bb0e2` |
| 03 | README built around them | `e5bb0e2`, `f98bb9f` |
| 04 | Tag, release, changelog, runbook | `4ce7b71` + the release |
| — | Rename to Arcsong | `5e8bf69` |
| — | Review fixes | `d112209` |

Parked: none.

## Evidence

- `uv run pytest -q`: 241 passed, 7 skipped (opt-in real tests); `ruff` and `npm run typecheck` clean. The reviewer independently rebuilt the web bundle and confirmed the committed build is identical.
- **Published artifacts verified:** the wheel downloaded from the release URL matches a fresh local build by SHA-256, carries `LICENSE` and `THIRD_PARTY_NOTICES.md`, contains no `spike`, installs one `arcsong` command and runs.
- **A stranger's first run, exercised on an empty data directory:** jobs refused with 409 before weights, Setup showed its checks and both parts, licence → download → installed, then a song rendered, was indexed, and downloaded as FLAC.
- Samples: three 45 s MP3 excerpts at 160 kbps, mean level ≈ −17.7 dB, peaks under 0, no clipping. Screenshots: six PNGs from the real app with five real songs in it.
- Real engine: not re-run at release time — the Mac was on battery, and mlx-Yue refuses to render on battery. The last real runs (renders, Finalize, Score, covers) all passed earlier in the day.

## QA verdict (summary)

**PARTIAL.** Stories 02 and 04 delivered; 01 and 03 partial. All findings fixed in `d112209`:

1. The wheel shipped 88 vendored MIT soundfont files and MIT/BSD bundles with **no attribution file** — `THIRD_PARTY_NOTICES.md` now installs beside `LICENSE`. The one genuine compliance gap.
2. The sdist carried tests that **could never run**, since ten import the `spike` harness the package excludes. It now ships the app alone.
3. The README claimed the samples **play in the page**; GitHub serves them with `content-disposition: attachment`. Reworded.
4. "240 tests" went stale when a test was added; the number is gone rather than corrected.
5. Classifiers named only 3.12 while the docs claimed 3.12–3.14; they now match, and CLAUDE.md says the pin is unbounded.

Machine-level risks, both fixed: a **worker process from before the rename** was still running (the kind that holds the Lyra GPU lock), along with the whole `dev` server on port 8840; and the venv's dev scripts still pointed at the deleted path, so `uv run pytest` failed until `uv sync --reinstall`.

The release was then **re-cut** — the first artifacts predated the fixes and had no downloads.

## Decisions made for you

Ranked costly-and-surprising first.

- **Renamed to Arcsong.** songloom was too common to release under, and `songwright` was taken by an iOS app. Arcsong was free on PyPI, GitHub and the App Store. The rename moved the package, command, environment variables, data directory (rewriting absolute paths inside SQLite), repository, docs and screenshots.
- **No PyPI.** A name there can be yanked but never reclaimed; the git URL install works today.
- **The release is a tag plus artifacts, nothing more** — and `docs/release.md` records how to delete one, which is what made re-cutting safe.
- **`spike` stays in the repository but out of the package**, so installing never puts the M0 harness on a user's PATH.
- **`requires-python = ">=3.12"`**: the old `<3.13` pin had nothing behind it; the suite passes on 3.12, 3.13 and 3.14.
- **Samples are MP3, not the FLAC the app makes** — a tenth of the size, and nobody needs lossless to decide whether to install something.
- **Screenshots come from the real app with real songs**, and the Setup shot shows the first-run state rather than a finished one.
- **The licence acknowledgement was left to the user to click** rather than pushed through the API — which is how the Setup page's weak call to action was found and fixed.
