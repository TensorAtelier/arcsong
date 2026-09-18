# Changelog

All notable changes to songloom. Versions follow [semantic versioning](https://semver.org);
while the project is at 0.x, minor versions may change behaviour.

## 0.1.0 — 2026-09-18

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
