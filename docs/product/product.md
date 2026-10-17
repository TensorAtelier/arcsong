# Arcsong — product charter

> Draft 2026-10-17 by `/pm` (charter mode). Fields marked `(inferred)` wait for the owner;
> see `NEEDS-YOU.md`.

## Goal

Arcsong lets AI-music tinkerers make full songs with YuE2 privately, on their own hardware: write
a style and lyrics, sketch a few takes, pick one, finalize it, keep a library. It wins on
reliability, install experience and a calm, music-first interface, not on features — every
feature it has also ships in some other YuE2 front end (`docs/prior-art.md`). (inferred)

Business model: none-yet — attention for Tensor Atelier (GitHub org, Patreon, tensoratelier.com).
The weights are CC BY-NC 4.0, so Arcsong never sells generation or hosts it for others. (inferred)

## North star

Metric: GitHub stars on `TensorAtelier/arcsong` (inferred)
Source: `github-repo` in `metrics.md`
Current: 0 (2026-10-17, never announced)   Target: 100 by 2027-01-31 (inferred)

Supporting: unique cloners (14-day window), release asset downloads, open issues from people
other than the owner.

Arcsong collects no telemetry — "songs made" is not measurable, by design. Stars and clones are
the honest proxy.

## Core use cases

Must be excellent. Release QA tests these hardest; their fixes score core = 2.

1. A new user installs Arcsong and makes a first song — quality bar: from `uv tool install` to a
   playing song with no step outside the app except the install command; Setup says plainly what
   is missing and why. (inferred)
2. A songwriter sketches takes, compares them and finalizes the best — quality bar: sketching 4
   takes is one click, Compare switches takes at the same moment, Finalize keeps the music.
   (inferred)
3. A user finds, plays, renames and downloads past songs — quality bar: the Library opens on the
   newest work, playback continues across views, downloads are named after the song. (inferred)

## Good enough

Must work; stop there.

- Score view and editing — renders, plays, validates, renders a song from an edit.
- Covers — transcribe, edit, re-sing; optional part of Setup.
- Setup page internals — checks and resumable download; no polish beyond clarity.
- Phone layouts — a bonus; desktop first, tablet (768 px) is the smallest target.
- Light theme — matches dark; no separate design work.

## Non-goals

- Hosting generation for other people, or any paid tier — the weights are CC BY-NC 4.0.
- Telemetry or accounts — the app's promise is "made privately on this Mac".
- What the model can't do (from `PLAN.md`): stem separation, voice cloning, inpainting, exact
  duration, real-time streaming, training/LoRA, direct MIDI input.
- PyPI publishing — a name there can be yanked but never reclaimed (`PLAN.md` M6); revisit with
  users.

## Taste anchor

The warm analog redesign the owner chose on 2026-10-17 (Claude Design canvas, row 1: dark warm
greys, one amber accent, Bricolage Grotesque / Instrument Sans / JetBrains Mono, paper-white
light theme). Quiet chrome, the music and words in front. The rejected "Vivid" row is the
counter-example: energy in the interface competes with the user's songs.

## Kill criteria

Fewer than 25 stars 8 weeks after the first public announcement → maintenance mode (fixes and
dependency bumps only) and an options memo. (inferred)
maintenance_below: 0.3

## Autonomy

ship: ask        # a release is public (inferred)
chain: 3
spend: never     # money is always the owner's — including cloud GPU time for Modal/RunPod work

## Release

verify: `uv run pytest -q && uv run ruff check . && (cd web && npm run typecheck)`
ship: `docs/release.md` — bump version, CHANGELOG, tag, `gh release create` with the wheel and sdist
preview: `uv run arcsong serve --engine fake --data <tmp>` at http://127.0.0.1:8840 (fake Engine,
fake weights download); real-weights journeys on the owner's Mac (`dev start arcsong`)
production: https://github.com/TensorAtelier/arcsong/releases (install: `uv tool install git+https://github.com/TensorAtelier/arcsong`)
health: CI on `main` (`gh run list --limit 1`) — macOS, Linux, Windows on the fake Engine

Journeys (end-to-end, in priority order):

1. [core] First song — fresh data dir → Setup checks → licence → download (fake) → Create, Single
   song → progress → plays in the bar → in the Library tomorrow (after a restart).
2. [core] Sketch and pick — Sketch 4 takes → Compare: 1–4 switch at the same moment, Space,
   S stars → Finalize → the Final appears in the sketch's Library card.
3. [core] Library — search, filter Starred, rename from ⋯, play across views, download FLAC named
   after the title, delete with confirm.
4. Score — Plan a melody → notation and piano preview → edit ABC (valid, diff) → render.
5. Cover — upload → transcribed Score → render (covers part installed).
6. Real weights (pre-release only, owner's Mac on AC): `ARCSONG_REAL_ENGINE=1 caffeinate -ims uv
   run pytest -q tests/test_real_engine.py`.
