# Prior art — YuE2 UIs (Pre-M0)

Surveyed 2026-09-16 from GitHub READMEs only (nothing installed or run, so claimed features
are unverified). YuE2 was released ~2026-09-08; a GitHub search for "yue2" returned ~45
repos, ~30 of them updated within the last two days.

## Closest to arcsong (Apple Silicon, app/web UI)

| Project | Engine | Form | Notable | Stars |
|---|---|---|---|---|
| [Flip-Engineering/riff](https://github.com/Flip-Engineering/riff) | audio.cpp (Metal / CUDA / CPU) | Mac installer + web studio, MIT | Plan-first + score workspace (edit melody/harmony, transpose, ABC/MIDI import/export), A/B compare takes, "Finish audio" from saved synthesis, re-decode, AI writer, library with notes/search/archive | 2 |
| [deadjoe/yue2_groove](https://github.com/deadjoe/yue2_groove) | official `yue2` (MPS; CUDA validated) | Web UI + Pinokio, Apache-2.0 | Simple SONG view + 7-tab STUDIO view; score edit → compare; covers; batch; re-decode; single adapter file with upstream contract tests | 1 |
| [tonywestonuk/YuE-Studio](https://github.com/tonywestonuk/YuE-Studio) | fork of `yue2` + custom MLX / Neural Engine engines | Native Swift app, DMG, Apache-2.0 | **Draft (8 steps) → "Render full quality" (same tokens + seed, 32 steps) already works**; staged queue with per-stage throughput; 16 GB Macs supported; ~2× faster synthesis on the ANE | 4 |
| [stavitian/yue2-studio](https://github.com/stavitian/yue2-studio) | `mlx-Yue` CLI (vanch007) | Swift WKWebView + stdlib server, MIT | Installer, covers, library, score viewer; two patches that make `mlx-Yue` work on 24 GB Macs | 1 |
| [Rdx-ai-art/yue2-mlx.pinokio](https://github.com/Rdx-ai-art/yue2-mlx.pinokio) | own MLX port (`ahmadw/YuE2-3B-MLX`) | Gradio + Pinokio | BF16 / 8-bit / 4-bit, 16 GB min, LLM writing room | 1 |

## NVIDIA / Windows / ComfyUI (the plan's v2 audience)

- [dynamohum/yue2gen](https://github.com/dynamohum/yue2gen) — web app + ComfyUI engine in Docker. Plan-first,
  score editor with three views, covers, stems (CPU separation), starred library, waveform player.
- [Garionhk/GoKuk](https://github.com/Garionhk/GoKuk) — portable Windows app. Piano-roll score editor with synth
  preview, "edit score before singing", takes ×1–4, covers, OOM retry in low-memory mode.
- [vrgamegirl19/Yue2_Studio](https://github.com/vrgamegirl19/Yue2_Studio) (31★) — web studio with LoRA training, LLM
  writing room, batches.
- [filliptm/ComfyUI-FL-YuE2](https://github.com/filliptm/ComfyUI-FL-YuE2) (121★, the most-starred UI) — ComfyUI nodes
  with a piano-roll score editor and LoRA training.
- Also: CodeCat04/Whiskerwave-Studio, DocShotgun/ds-yue-webui, krakenunbound/yue2-studio,
  Ladypoly/YuE2_WebUI, ~10 more ComfyUI node packs.

## Engines

- `vanch007/mlx-Yue` (5★, 2026-09-13) — the port the plan pins. Needs patches on 24 GB Macs
  (resource guard aborts on transient memory-pressure warnings) per stavitian.
- `0xShug0/audio.cpp` (2.8k★) — ggml engine with YuE2 support on Metal/CUDA/Vulkan; used by
  riff and Whiskerwave. A larger, multi-model project, so less single-maintainer risk than
  `mlx-Yue`.
- `ServeurpersoCom/yue2.cpp`, `engival/yue2.cpp` — standalone C++ ports.

## Facts useful for M0

- M5 Pro / 24 GB with `mlx-Yue` (stavitian): 3:20 song at 32 steps = 337 s, 10.4 GiB peak;
  1:16 song at 8 steps = 47 s, ~9 GiB. No per-stage split published.
- Draft → final by reusing tokens + seed is shown to work (YuE-Studio, riff "Finish audio").
- Planning is cheap: "a new plan costs seconds" (yue2gen).

## What this means for the plan

Every arcsong differentiator (score edit, draft→final, variations/compare, a clean NVIDIA
path) already ships in at least one project, and riff covers nearly the whole roadmap on
Apple Silicon. No project has much traction yet (the top standalone UI has 31★). The
winner will likely come down to reliability, install experience and staying maintained,
not features.
