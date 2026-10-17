# Changelog

All notable changes to arcsong. Versions follow [semantic versioning](https://semver.org);
while the project is at 0.x, minor versions may change behaviour.

## 0.3.0 — 2026-10-17

Songs have names, and Style gets a dice.

- **Song names.** Create and Cover ask for a song name, and every take of a sketch shares it.
  Every song now stores its name; existing songs keep the name they showed (schema 6).
- A dice beside Style rolls a random style; the suggestion chips under it are gone.
- A queued Final shows its Draft's current name.
- `scripts/release-qa` runs the release journeys in a private headless Chrome (for contributors).

## 0.2.0 — 2026-10-17

A new look, song titles and one player for the whole app; renders on battery; tested on macOS,
Linux and Windows (fake Engine) in CI.

### Look and feel
- A redesign in a warm analog style: dark warm greys with one amber accent, a paper-white light
  version, and bundled fonts (Bricolage Grotesque, Instrument Sans, JetBrains Mono), so nothing
  loads from the network. A System / Light / Dark switch sits in the header.
- Create has three tabs: **Write a song** (Sketch, a few quick takes, or Single, one take at
  full quality), **Plan a melody** (Score only) and **Cover a recording** (now with drag and
  drop). Style suggestions and section tags insert with a click; a dice button picks a seed.
- Beside it, the queue shows what is rendering stage by stage, failed jobs with Retry, and what
  just finished. Dismissed failures stay dismissed, and a failure older than a day stops showing.
- The Library groups a sketch's takes and their Finals in one card, with filters for starred
  songs, drafts and Finals, and a ⋯ menu per song for rename, the Score, downloads and delete.
- Compare shows the shared playhead and takes keyboard shortcuts: 1–8 switch take, Space plays
  or pauses, S stars.
- The Score's notation sits on paper beside the ABC editor, and renders at a chosen quality.

### Fixes
- Create keeps a finished sketch's Compare link, instead of dropping it with the last take.
- The Score page explains a take the model planned with no vocal melody, instead of a bare
  "0 vocal notes".
- An orphaned worker exits on Windows too (it watched its parent with `os.getppid()`).
- After mlx-Yue stopped a render because macOS swapped memory to disk, every later song
  failed at once with the same error until the app restarted. The model is now reloaded for
  the next song, and the message says what happened and what to do.

### Power
- With `--require-ac`, a song refused on battery now says so and how to render anyway,
  instead of mlx-Yue's "AC power is required for an acceptance benchmark".
- Songs render on battery by default, more slowly. `--require-ac` (or `ARCSONG_REQUIRE_AC=1`)
  brings back the old behaviour of waiting for AC power; `--allow-battery` is no longer needed
  but still accepted.

### Titles and playback
- Every song has a title: its first sung line, or the style's genre for an instrumental.
  Rename it in place; a Final inherits its Draft's title, and downloads are named after it.
- One player for the whole page: a song keeps playing across views in a bar along the bottom,
  with waveforms you can click to seek, Space to play or pause, and the Mac's media keys.
  Compare and the Score preview pause it, and it pauses them.

## 0.1.0 — 2026-09-19

The first release: everything needed to write, compare, edit and cover songs on an Apple
Silicon Mac, with the model running locally.

### Making songs
- Style and lyrics in, a full song out, with section tags, seed, precision and quality
  settings, live per-Stage progress, and cancel.
- A serial job queue with one worker process holding the model, which survives a crashed
  render and recovers jobs left running by a stopped server.
- **Variations**: 2–8 takes of one request with distinct seeds, compared side by side with
  waveforms and a single shared playhead, with a star for the pick.
- **Finalize**: turn a quick 8-step draft into a 32-step render that keeps the same music, by
  re-synthesizing what the draft already produced.

### Library
- Every finished take with playback, filtering, settings, re-run, disk usage, FLAC and WAV
  download, and permanent delete.

### Score
- The melody the model plans, shown as notation with a melody preview, an ABC editor with live
  validation and a diff against the original, and a song rendered from your edit.
- Score-only runs that plan in seconds without rendering audio, and ABC or MIDI export.

### Covers
- Upload a recording, have it transcribed into a Score, and re-sing that melody with your own
  style and lyrics. The recording is deleted as soon as the job ends.

### Setup
- A first-run page that checks the machine, shows the CC BY-NC 4.0 model licence, and downloads
  the weights with progress, resumable and cancellable. Covers are an optional second part,
  with ffmpeg detected rather than bundled.

### Known limits
- Apple Silicon only; NVIDIA and Windows are not supported yet.
- Rendering needs AC power, and mlx-Yue refuses to start under memory pressure — close other
  local model servers first.
- Songs peak at about 11 GiB of memory; the RAM check warns below 24 GB.
