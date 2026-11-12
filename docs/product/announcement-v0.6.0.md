# Announcement draft — v0.6.0 (for the owner to post)

Replaces the v0.2.0 draft. Where: r/LocalLLaMA first (one place, so the star baseline means
something); flair "Resources" or "Other". Before posting: run J6 (real weights) on AC power, and
check the release page and README screenshots still match the app.

---

**Title:** Arcsong — a private web app for YuE2 full-song generation: sketch takes, compare, finalize, edit the score (runs on your Mac, or a GPU in your own Modal or RunPod account)

I've been making songs with YuE2 (the open full-song model: a style and lyrics in, vocals and
accompaniment out) and built a small app around it so I'd stop living in the CLI.

What it does:

- **Sketch, then pick.** Write a style and lyrics, render 4 quick drafts with different seeds,
  compare them on one shared playhead (keys 1–4 switch takes at the same moment), star one, and
  Finalize it at full quality: same music, more detail.
- **Read and edit the Score.** YuE2 plans an ABC melody before it sings. Arcsong shows it as
  notation, plays it on a piano, lets you edit it with live validation and renders from your edit.
  **Make instrumental** moves the vocal line to an instrument using YuE2's own recipe.
- **Help with the prompt.** A searchable dictionary of ~215 style phrases (genres, instruments,
  voices, moods), hints for section labels, and a check that flags lyrics YuE2 reads badly.
- **Covers** (Mac): upload a recording, it's transcribed into a Score you can re-sing.
- **Your songs stay yours.** No account, no telemetry, songs and library on your machine.

Two ways to render:

- **On an Apple Silicon Mac** (24 GB+ is comfortable): `uv tool install git+https://github.com/TensorAtelier/arcsong`,
  then `arcsong serve`. Setup downloads the weights (~11 GB, CC BY-NC 4.0) with a resumable bar.
- **On your own Modal account** (Windows, Linux, smaller Macs): install `arcsong[modal]` (with
  `--with-executables-from modal`, see the README), run `modal setup`, then `arcsong serve --engine modal`. Setup deploys a small app into *your*
  workspace; a 3-minute song took about 200 s and $0.05 on an L4 in my tests, and Modal's
  monthly free credit covers a lot of songs.
- **On your own RunPod account**: install `arcsong[runpod]` the same way (`--with-executables-from
  runpod`), `rp login`, then `arcsong serve --engine runpod`. Songs run as Serverless jobs on a
  24 GB GPU; nothing is stored there, and my whole test session (two full-length drafts, a
  Finalize, a melody plan) cost about five cents.

Repo, screenshots and unedited sample songs: https://github.com/TensorAtelier/arcsong

Feedback welcome, especially from 16 GB Macs and from anyone trying the cloud routes on Windows.

---

Notes for the owner:

- RunPod shipped in v0.6.0 (X-002, then a real end-to-end run on the owner's account).
- The $0.05 figure is X-001's (a cold L4, 32 steps); the v0.5.0 test run spent $0.15 across
  setup, two drafts, a Finalize and a cancelled render.
