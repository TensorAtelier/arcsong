# Songloom

Write a style and some lyrics, get a whole song — vocals and accompaniment — generated on your
own Mac. Songloom is a local web app around the [YuE2](https://huggingface.co/m-a-p/YuE2-3B)
music model, running through the [mlx-Yue](https://github.com/vanch007/mlx-Yue) port on Apple
Silicon. Nothing is sent anywhere: the model, the weights and your songs stay on the machine.

> **Status: v0.1.0, early.** Apple Silicon only. NVIDIA support is planned but not started.

## What it does

- **Write a song** from a style description and lyrics, with section tags (`[Verse]`, `[Chorus]`),
  a seed, precision and quality settings, and live per-stage progress you can cancel.
- **Variations**: queue 2–8 takes of the same request with different seeds, compare them side by
  side with waveforms and one shared playhead, and star the one you want.
- **Finalize** a quick 8-step draft into a full 32-step render that keeps the same music, by
  re-synthesizing what the draft already generated.
- **Library**: everything you have made, with playback, FLAC/WAV download, disk usage, re-run,
  and permanent delete.
- **Score**: read the melody the model planned as notation, play it, edit the ABC with live
  validation, and render a song from your edit. Export ABC or MIDI.
- **Covers** (optional): upload a recording, have it transcribed into a Score, and re-sing that
  melody with your own style and lyrics. The recording is deleted as soon as the job ends.

## Requirements

- macOS on Apple Silicon (M-series). The model peaks at about 11 GiB of unified memory, so
  24 GB or more is comfortable; below that, close other apps and local model servers.
- About 11 GB of disk for the song weights, downloaded from the Setup page on first run.
- For covers: [ffmpeg](https://ffmpeg.org) (`brew install ffmpeg`) and a further ~2.6 GiB of
  transcription weights.
- Songs must be rendered on AC power — mlx-Yue refuses to run on battery.

## Install

```sh
uv tool install git+https://github.com/TensorAtelier/songloom
songloom serve
```

Then open <http://127.0.0.1:8840>. The first run opens the Setup page, which checks the machine,
shows the model licence, and downloads the weights with progress. Songs, the library and settings
live in `~/Library/Application Support/songloom` (override with `--data` or `$SONGLOOM_DATA`).

No Node is needed to run it: the web app ships prebuilt.

## Licences

The code is Apache-2.0 (see [`LICENSE`](LICENSE)).

**The model weights are not.** YuE2 and the transcription models are
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — non-commercial use only — and
Songloom asks you to acknowledge that before it downloads anything. Check the model licence
before any commercial use of what you make, and if you upload a recording to cover, you are
responsible for having the rights to it. Third-party components are listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Development

```sh
uv sync                     # Python side
cd web && npm install       # only if you are changing the page
uv run songloom serve --engine fake   # no GPU, no weights: scripted stages and a test tone

uv run pytest -q            # 240 tests, all on the fake engine
uv run ruff check .
cd web && npm run typecheck && npm run build   # the build is committed
```

Slow tests that need real weights and the GPU are opt-in:
`SONGLOOM_REAL_ENGINE=1 caffeinate -ims uv run pytest -q tests/test_real_engine.py`.

Architecture, conventions and the hard-won gotchas are in [`CLAUDE.md`](CLAUDE.md); the roadmap
and the reasoning behind the design are in [`PLAN.md`](PLAN.md).

## Credits

[YuE2](https://huggingface.co/m-a-p/YuE2-3B) and
[SheetSage2](https://huggingface.co/m-a-p/SheetSage2) by M-A-P; the Apple Silicon port
[mlx-Yue](https://github.com/vanch007/mlx-Yue) by vanch007. Songloom is an independent front end
and is not affiliated with either.
