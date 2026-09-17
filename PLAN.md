# Songloom — local UI for YuE2 music generation

> Working name; rename freely. Plan drafted 2026-09-16.

## Goal

A local web app that lets AI hobbyists generate full songs (vocals + accompaniment) with
YuE2-3B on their own machine: write style + lyrics, get a song, iterate, keep a library.
Apple Silicon first via the `mlx-Yue` port (`vanch007/mlx-Yue`, which runs YuE2; engine confirmed
2026-09-17 after the M0 spike); NVIDIA later.

**Audience:** tinkerers comfortable cloning a repo and running one command. So: expose seeds,
precision, steps, ABC scores and sampling knobs — but with good defaults so the first song
needs only style + lyrics.

**Non-goals** (the model can't do these — don't promise them): stem separation / locked
accompaniment, voice cloning, audio inpainting, exact duration control, real-time streaming,
training/LoRA, direct MIDI input (must convert to ABC first).

## Feature stack rank

Ranked by *how often a user needs it* × *how much it makes the app worth opening instead of the CLI*.

| # | Feature | Why this rank | Milestone |
|---|---|---|---|
| 1 | **Song generation** — style + lyrics → song; mode (full / melody / off), seed, precision | The core loop. Nothing else matters without it. | v1 |
| 2 | **Job queue with live progress + cancel** | A full song takes minutes; a UI that freezes or can't be cancelled is unusable. | v1 |
| 3 | **Library** — list past songs, play, download FLAC/WAV, view settings, "re-run with these settings" | Generative output is disposable only if you can find the good ones again. | v1 |
| 4 | **Model setup screen** — detect/download weights with progress, run `doctor`, show licence | Without it, first run fails for anyone who didn't follow the README exactly. | v1 |
| 5 | **Draft → final** — quick 8-step render, then re-synthesize the same take at 32 steps | M0: feasible on mlx-Yue and bit-identical to a direct 32-step render. Synthesis dominates a 32-step Take, but the saving only appears with 2+ Drafts per Final (one Draft + Final = 584 s vs 486 s direct), so it pairs with variations. v1 still gets the fast first listen by exposing Synthesis steps (8 = draft, 32 = final). | Steps selector v1; "Finalize" shipped in M2 (with #6) |
| 6 | **Variations / compare** — N seeds of one request, side-by-side players, star/pick | Output is stochastic; upstream's best benchmark result is *best-of-8*. Picking is how people get good songs. | v1.1 |
| 7 | **Score view & edit** — render the generated ABC plan as notation, preview melody via MIDI synth, edit, re-render song from edited score | YuE2's unique feature vs Suno-likes. Plan-first flow also lets users approve a melody *before* the expensive render. | v1.2 |
| 8 | **Prompt helpers** — style preset library, lyric section tags (`[Verse]`/`[Chorus]`) template, length estimate | Cheap, raises hit rate for new users. Can trickle in alongside anything. | ongoing |
| 9 | **Covers & transcription** — upload audio → transcribe (ABC/MIDI) → re-sing in new style | Impressive but niche, heaviest deps (ffmpeg, SheetSage2 + MERT2 weights), slowest jobs, copyright questions on inputs. | v1.3 |
| 10 | **NVIDIA backend** | Doubles the audience, but needs a CUDA box to test and a second install path. | v2 |
| 11 | **Packaging / release** — one-command install, versioned releases | Needed before announcing publicly, not before it's good. | v2 |

**v1 = #1–#4, plus the Synthesis-steps selector from #5.** Definition of usable: a fresh clone → one install command →
setup screen downloads models → user writes lyrics → gets a song with progress → finds it in
the library tomorrow.

## Architecture

```
Browser (Vite + React + TS)
   │  REST + SSE (progress events)
FastAPI server  ── SQLite (jobs, songs, tags, ratings)
   │  job queue (serial: one GPU job at a time)
Engine worker process  (long-lived, model kept loaded)
   │  Engine interface
   ├─ MlxEngine   → lyra.YuE2Pipeline   (Apple Silicon)   v1
   └─ CudaEngine  → yue2.YuE2Pipeline   (NVIDIA)          v2
Filesystem library: data/songs/<id>/  (SongResult.save_artifacts output, as-is)
```

Key decisions:

- **Separate worker process for the model.** Peak ~10–11 GB unified memory; an OOM or a
  Metal crash must not take the web server (and queue state) down. Server restarts the worker
  and marks the job failed. Keep the model warm between jobs — load takes seconds, integrity
  check ~7 s — but unload after an idle timeout (default ~15 min) so 10–11 GB isn't held
  while the user runs other local models.
- **Server ↔ worker IPC:** `multiprocessing` queues for jobs and events, plus a shared
  `Event` that the pipeline's `cancelled()` checks. If a stage ignores cancel within a grace
  period, kill the worker and restart it (accept the reload cost). M0: cooperative cancel
  returned within 0.13 s in every Stage with no reload, and the staged API leaves no stale
  resource files. Still unmeasured: a kill while a Take is being saved, so the worker must
  not index a Take until saving has finished.
- **Progress throttling:** `on_token` fires per token (up to 71/s measured in M0); the worker
  coalesces events to a few per second before they reach SSE. What a bar can show per Stage
  (M0): planning and semantic generation give a running token count with no total; synthesis
  gives a stepped `N/steps` only from yue2's stderr progress lines (one per 5 s through a pipe,
  first step ~15 s in); decoding gives nothing usable. So v1 shows the Stage segment plus a
  token counter and a stepped synthesis %. Ask upstream for `on_progress` on
  `synthesize()`/`decode()`.
- **Restart semantics:** on server start, jobs left `running` become `failed`; `queued` jobs
  resume in order.
- **Memory-aware defaults:** detect total RAM and warn below a floor instead of crashing.
  M0: mlx-Yue peaks at ~10.5–11 GiB footprint, and 8-bit lowers that only 0.08–0.25 GiB
  (synthesis has no 8-bit model), so precision is not a memory lever. Default to 8-bit for
  speed (faster planning and semantic generation). The RAM floor is unmeasured: test on a
  16 GB and a 24 GB Mac before documenting a minimum.
- **Serial queue, concurrency 1.** One model instance can't run jobs in parallel on one GPU;
  queue everything else (variations = N queued jobs sharing a group id).
- **Use the staged API, not the CLI.** `lyra.YuE2Pipeline` exposes
  `plan → generate_semantic → synthesize → decode`, each with `cancelled=`; `on_token` on
  the two token Stages. That gives Stage-level progress, real cancellation, re-synthesis for
  #5, and the "edit plan then render" flow (#7). (M0: synthesis and decoding expose no
  progress callback; see Progress throttling.)
- **Engine interface is the seam for NVIDIA.** Methods: `doctor()`, `ensure_models(progress)`,
  `plan(request)`, `render(plan, steps, seed)`, `resynthesize(song, steps)`,
  `transcribe(audio)`. The mlx port mirrors upstream's API and artifact layout, so the CUDA
  adapter should be thin. Keep request/artifact formats engine-neutral.
- **Library = artifact dirs on disk + SQLite index.** Don't invent a format: store whatever
  `save_artifacts` writes (audio.flac, request.json, score.abc, semantic/latent/noise .npy,
  result.json). The `.npy` files are what make replay / draft→final possible. M0: a ~3-min
  Take is 37–40 MiB, almost all FLAC; the `.npy` files are only ~2 MiB, so keep them for every
  Take. The library shows disk usage, and deleting unwanted Takes and Drafts is what frees
  space. "Re-run with these settings" reproduces the same Take (bit-identical in M0) as long
  as precision and Synthesis steps are part of the settings.
- **Library location:** configurable; defaults to the user data dir via `platformdirs`
  (`~/Library/Application Support/songloom` on macOS), with a `./data` override for
  development. The install dir gets replaced on upgrade under `uv tool install`.
- **Localhost only in v1:** bind `127.0.0.1`. LAN/multi-user needs auth and is out of scope
  until v2.
- **Engine as a pinned dependency**, not a copy: depend on `mlx-yue` by git commit
  (currently audited `9253ed1`). Re-audit before bumping — it's a days-old single-maintainer port.
  audio.cpp stays the candidate for M5 (healthier project, Metal + CUDA) once it can take
  Semantic tokens back; see `docs/m0-report.md`, Hybrid options.
- **Frontend libs:** `abcjs` (notation render + MIDI playback preview, #7),
  `wavesurfer.js` (waveforms, #6). Both on npm; no CDN at runtime (local-first). Built
  frontend assets ship inside the Python package, so end users never need Node; lay out the
  repo so the build output lands in the package from the start.
- **Runs under `dev`:** `dev register songloom 8840 --cmd "uv run songloom serve --port 8840" --cwd ~/projects/songloom`.

## Milestones

### Pre-M0 — Prior-art check — done 2026-09-16, see `docs/prior-art.md`
**Decision: build standalone.** The field is days old with no clear leader (top standalone UI
has 31★). Every planned feature already ships somewhere, so songloom competes on
reliability, install experience and sustained maintenance, not on features.

### M0 — Engine spike (1–2 days) — de-risk before any UI
Script that drives the staged `lyra` API in a subprocess and answers:
Answered 2026-09-16 — see [`docs/m0-report.md`](docs/m0-report.md) (recommendation, numbers, flagged plan changes).
- [x] Engine choice: `mlx-Yue` vs `audio.cpp` (2.8k★, Metal + CUDA, used by riff). Compare
      install friction, speed, memory, staged API / cancel / progress hooks. `audio.cpp` could
      also cover the NVIDIA path (M5) with one engine.
- [x] Per-stage timing split (plan / generate_semantic / synthesize / decode) — decides
      whether draft→final (#5) or plan-first is the real iteration lever. (Planning reportedly
      takes seconds, per yue2gen.)
- [x] Seed reproducibility: same seed + inputs → same audio on MLX/Metal? "Re-run with these
      settings" and draft→final both depend on it; if not, the UI says "similar", not "same".
- [x] Artifact sizes per song (`.npy` intermediates vs FLAC) — sizes the library cleanup feature.
- [x] Per-stage progress: what callbacks fire, how often, and can they map to a % bar?
      (Answered — see report, "Progress within a Stage": mlx-Yue gives token counts, up to 71/s, in planning and semantic generation and a stepped % in synthesis via stderr; its decoding % is too coarse for a bar; audio.cpp gives nothing usable inside a Stage.)
- [x] Cancellation: does `cancelled()` stop each stage promptly and leave the pipeline reusable?
- [x] Draft→final: render at 8 steps, then re-`synthesize` the saved semantic tokens + noise at
      32 steps — same song, better quality? (Decides #5.) Already shown feasible by YuE-Studio
      and riff; confirm on our engine.
- [x] Timing + peak memory on this M5 Pro for a ~3-min song, bf16 vs 8bit, 8 vs 32 steps.
- [x] Failure hygiene: stale `<output>.resources.json[l]` blocks re-runs — confirm the API
      path avoids it or the worker cleans it up.
- [x] Model download without the HF cache-metadata files that fail `verify_conversion`.

### M1a — First song end to end (features #1–#2)
Done 2026-09-17 (`.scratch/m1a-first-song/REPORT.md`). The review's 5 defects (shutdown with an open page, orphaned workers, load-failure restart loops, `seq` reset on restart, a Take finishing during shutdown) are fixed with tests.
Backend: FastAPI, SQLite schema (jobs, songs), worker + queue + IPC, SSE progress, engine
adapter. Frontend: bare Create page (style, lyrics with section-tag template, mode, seed,
precision, advanced drawer) and Queue panel. Tests: engine adapter against a fake engine;
worker crash mid-job → job marked failed, next job runs; restart recovery; one slow smoke
test with real weights behind a flag.

### M1b — v1 usable (features #3–#4)
Library done 2026-09-17 (`.scratch/m1b-library/REPORT.md`): list, filter, play, settings, FLAC/WAV download, re-run, edit in Create, disk usage and permanent delete.
Setup done 2026-09-17 (`.scratch/m1b-setup/REPORT.md`): checks (Metal, RAM warning below 24 GiB, AC power, disk, weights), CC BY-NC 4.0 acknowledgement gating the download, a ~10.45 GB download of all precisions with progress, cancel/resume, metadata cleanup and verification. Weights now default to `<data>/models`. v1 (#1–#4) is feature-complete.
Library (list/filter, player, download, re-run, disk usage + Take/Draft deletion), Setup page
(model download with progress, `doctor`, licence acknowledgement, RAM check). Download fix
from M0: after `snapshot_download`, delete `converted/.cache` and `converted/.gitattributes`
(or ignore `.gitattributes`), or mlx-Yue's `verify_conversion` rejects the directory.

### M2 — Variations + Finalize (#6, #5)
Done 2026-09-17 (`.scratch/m2-variations/REPORT.md`): Create queues 2/4/8 Takes with distinct seeds; a Compare view shows a waveform per Take with one shared playhead; star a pick (Starred filter in the Library); Finalize re-synthesizes a Draft's saved Semantic tokens and noise at 32 steps, verified on real weights.
"Generate ×N" Drafts (8 steps) with distinct seeds, compare view with synced players +
waveforms, star/pick, then "Finalize" the pick: re-synthesize its saved Semantic tokens and
noise at 32 steps (~361 s for a 3-min song instead of a full 486 s re-render).

### M3 — Score workflow (#7)
Done 2026-09-17 (`.scratch/m3-score/REPORT.md`): "Score only" runs the planning Stage alone in seconds; the Score view renders notation (abcjs) with a melody preview from a vendored local piano, an ABC editor with live re-render, mlx-Yue's own validation message and a diff against the original, "Remove chords", and "Render song from this Score" (planning skipped), verified on real weights. Schema v3 stores a Score job's ABC.
"Plan only" button → notation view (abcjs) + MIDI melody preview → ABC text editor with
live re-render and validation (the port has ABC preflight + `strip-chords`) → render song
from edited score. Show plan diff vs original.

### M4 — Covers & transcription (#9)
Optional extra install (ffmpeg + transcription models, with setup-screen detection). Upload
audio → transcribe → edit score (reuses M3) → cover render. Export ABC/MIDI. Check the
SheetSage2 and MERT2 weight licences before shipping.

### M5 — NVIDIA backend (#10)
`CudaEngine` over official `yue2-infer`, or audio.cpp if it has gained Semantic-token input
and Score export by then (re-evaluate with the spike harness); engine auto-detect; test on a
CUDA machine; document Linux/Windows install.

### M6 — Release (#11)
One-command install (`uv tool install` or bootstrap script), versioned releases, README
with screenshots/audio samples, licence notices.

## Licensing & distribution

- **Model weights are CC BY-NC 4.0** — non-commercial. The app must download weights at
  setup time (never bundle them), show the licence, and require acknowledgement.
- App code can be MIT/Apache-2.0; `mlx-Yue` is Apache-2.0, upstream code Apache-2.0.
- Generated audio: don't make claims about output rights. Show a neutral "check the model
  licence before commercial use of outputs" note on the setup and export screens.
- Covers: warn that users are responsible for rights to uploaded source audio.
- Transcription models (SheetSage2, MERT2) have their own licences — check them in M4.

## Prior art to look at before M0

- `stavitian/yue2-studio` — macOS app + installer for YuE2 on Apple Silicon (created 2026-09-15).
- `rdx-ai-art/yue2-mlx-pinokio` — Pinokio one-click launcher.
- ComfyUI integration (per ComfyUI wiki).
Surveyed 2026-09-16 — see `docs/prior-art.md`. None of the originally planned differentiators
(score edit, draft→final, variations compare, NVIDIA path) is unique any more.

## Open questions

1. Final name.
2. Minimum RAM for mlx-Yue (does 16 GB work? 24 GB?) — needs a run on a smaller Mac.

### Resolved (2026-09-17)
- **Engine:** mlx-Yue (`vanch007/mlx-Yue`, YuE2) for v1, confirmed after the M0 spike
  (`docs/m0-report.md`).
- **#5 placement:** Synthesis-steps selector in v1; "Finalize" re-synthesis in M2 with variations.

### Resolved (2026-09-16)
- **Standalone vs contribute:** build standalone (see Pre-M0).
- **Frontend:** React + Vite — `abcjs` and `wavesurfer.js` justify it; built assets ship in
  the Python package.
- **Multi-user:** single-user localhost (`127.0.0.1`) for v1; LAN + auth revisited in v2.
- **Library location:** user data dir via `platformdirs` by default, configurable, `./data`
  override for development.
