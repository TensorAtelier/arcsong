# m4-covers — plan

**Goal:** Build M4 from PLAN.md: an optional extra install (ffmpeg + the transcription weights, detected on the Setup page), then upload audio → transcribe it into a Score → edit that Score with the M3 view → render a cover, with ABC and MIDI export.
**Not yet:** Separating vocals from a mix (the model transcribes what it hears). Chord transcription beyond what `task="melody-full"` gives. Trimming or choosing a section of the upload. Keeping uploaded recordings (they are deleted after transcription). Cleaning up old transcription output directories. Batch transcription. NVIDIA (M5).
**Stack / interfaces:**
- Setup becomes multi-part: an `engine` part (today's weights) and an optional `covers` part (ffmpeg + SheetSage2 229 MB + MERT-v2-FullSong 2.53 GB at mlx-Yue's pinned revisions, both CC BY-NC 4.0 like the song weights, so the same acknowledgement covers them). `GET /api/setup` gains `parts`, and the download endpoints take which part to fetch.
- ffmpeg is a check, never a download: it is a separate binary with its own licence, so Setup detects it and says `brew install ffmpeg`.
- API: `POST /api/covers` (multipart: the recording, style, lyrics, mode, precision, steps, and a rights confirmation) queues a job of kind `cover`; the Engine's `transcribe()` turns the audio into a Score in `jobs.score`, with mlx-Yue's other exports (MIDI, LAB, result.json) kept under `<data>/covers/<job id>/`. Schema v4: `jobs.kind` gains `cover`.
- The uploaded recording lives in `<data>/uploads/` only while the job runs and is deleted as soon as it finishes, however it finishes.
- Page: a Cover panel in Create (file picker, style and lyrics for the re-sing, a rights confirmation, and what the upload is used for), a queue label with the transcription's own progress, and the existing Score view for the result. The Score view gains ABC and MIDI download (MIDI straight from abcjs, so any Score can export one).
**Proof of done:** With ffmpeg installed and the covers weights downloaded from Setup, pick an audio file in Create, confirm the rights line, and press "Transcribe": a cover job reports its windows as it goes and finishes in the Score view with the transcribed melody in notation, playable. Edit it, press "Render song from this Score", and a Take comes back singing that melody in the style you asked for. The Score exports as ABC or MIDI. The uploaded file is gone from disk once the job ends. Setup shows "Covers" as its own part, with ffmpeg and the extra weights checked separately.

## Tickets

- [x] 01 — Setup parts: `Setup` holds named parts (`engine`, `covers`), `GET /api/setup` returns them, `POST /api/setup/download/{part}` and its cancel, an ffmpeg check with an install hint, and `TranscriptionModels` (pinned SheetSage2 and MERT revisions, sizes, verification by the same file-size rule); check: API tests with fake parts (a part downloads independently, jobs still gate on the engine part only, ffmpeg missing shows as a warning not a failure).
- [x] 02 — Cover jobs: schema v4, `POST /api/covers` (multipart upload with size and rights checks), Engine `transcribe()` for mlx-Yue and the fake, worker dispatch by kind, window progress, cancel, and deleting the upload when the job ends; check: API tests through the fake (a cover job produces a Score, the upload is gone, cancel and failure also delete it, a refused upload never queues), and one real transcription of a songloom Take behind `SONGLOOM_REAL_ENGINE=1`.
- [ ] 03 — Cover page: the Create panel (file picker, style, lyrics, rights confirmation, copyright note), queue progress for transcription, the Score view's ABC and MIDI download, and rendering a cover from the transcribed Score; check: in the browser against a fake-engine server, and a real cover render if the real transcription ticket passed.

## Notes

- Both transcription repos are CC BY-NC 4.0, the same licence as the song weights, so Setup's existing acknowledgement covers them; the Covers section says so rather than asking twice.
- ffmpeg is detected, not installed: `ffmpeg -version` in a subprocess (like the Metal check), with `brew install ffmpeg` as the hint. Without it the Covers part is "not ready" and `POST /api/covers` answers 409.
- Transcription runs in the same worker and the same serial queue as rendering, because it needs the GPU; the model loads lazily on the first cover and stays loaded (about 3 GiB on top of the song model — noted for the RAM check).
- The transcribed Score is mlx-Yue's own native two-voice ABC (`upstream/notation_sheetsage2.py` writes the same `V: Vocal` / `V: Ins` dialect), so it parses with `parse_abc` and renders through the existing Score view and `request.abc` path without conversion.
- Task `melody-full` (both voices, no chords) is the default: it is what a cover needs, and chords would come back as symbols the render ignores.
- MIDI export comes from abcjs in the page (`synth.getMidiFile`), so every Score exports one, not only transcribed ones; ABC export is the text already on screen.
- Uploads are deleted when the job ends, so songloom never keeps someone's recording. The page says so next to the rights confirmation.
- Asked, 2026-09-17: the user installed ffmpeg themselves (`brew install ffmpeg`), and approved downloading the covers weights (~2.8 GB) into their data dir to test a real transcription and cover render end to end.
- Setup's snapshot now carries `parts` (each with its own weights, download and checks) plus machine-wide checks (RAM, power) at the top level; `weights` and `download` stay at the top level as the Engine part's, because most of the page only cares about those. A part is usable when its weights are installed, nothing is rewriting them, and its own checks pass — which is how a missing ffmpeg blocks covers without touching songs.
- One download runs at a time across parts, so they never compete for the network.
- The transcription weights live beside the song weights (`<models>/sheetsage2`, `<models>/mert2`), and mlx-Yue's `resolve_models` takes those directories straight.
- Verification for the covers part is mlx-Yue's own rule: the MERT2 file's sha256 must match the `base_model_sha256` SheetSage2 records. Hashing only, so the server never imports MLX.
- Covers need mlx-Yue's `transcription` extra (mido, mir-eval, pretty-midi, scipy). It is part of songloom's own dependency now, so a cover needs no second install — only ffmpeg and the weights.
- Form fields arrive as text, so `steps` is taken as an `int` and checked by hand; `Literal[8, 32]` refused `"8"` and would have broken the page too (caught by the real run, now covered by a test).
- `GET /api/scores/{job}` serves a cover's transcription as well as a planned Score, so the Score view needs no special case.
- Real cover check (`SONGLOOM_REAL_ENGINE=1`, 2026-09-17, on AC): the covers weights downloaded and verified in 42 s (218 MB + 2.4 GB), then a rendered Take was transcribed and re-sung in a new style in 47 s, with the upload gone from disk afterwards.
