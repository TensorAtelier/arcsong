# Announcement draft — v0.2.0 (for the owner to post)

Where: r/LocalLLaMA first (one place, so the star baseline means something). Flair: "Resources"
or "Other". Post after the v0.2.0 release page is live.

---

**Title:** Arcsong — a local, private web app for YuE2 on Apple Silicon (sketch takes, compare, finalize, edit the score)

I've been using YuE2 (the open full-song model: style + lyrics in, vocals and accompaniment out)
on a MacBook through the mlx-Yue port, and built a small app around it so I'd stop living in the CLI.

What it does:

- **Sketch, then pick.** Write a style and lyrics, render 4 quick drafts (8 steps) with different
  seeds, compare them on one shared playhead (keys 1–4 switch takes at the same moment), star one,
  and Finalize it at 32 steps — same music, full quality.
- **Read and edit the Score.** YuE2 plans an ABC melody before it sings. Arcsong shows it as
  notation, plays it on a piano, lets you edit it with live validation, and renders from your edit.
- **Covers** (optional): upload a recording, it's transcribed into a Score you can re-sing.
- **Everything stays on your machine** — no account, no telemetry. Setup downloads the weights
  (~11 GB, CC BY-NC 4.0) with a resumable progress bar.

Install: `uv tool install git+https://github.com/TensorAtelier/arcsong`, then `arcsong serve`.
Needs an Apple Silicon Mac; a song peaks around 11 GiB, so 24 GB+ is comfortable. A 3-minute
song takes a few minutes on an M5 Pro.

Repo, screenshots and three unedited sample songs: https://github.com/TensorAtelier/arcsong

Next I'm looking at rendering on your own cloud GPU (Modal / RunPod) for Windows, Linux and
smaller Macs — a test run did a 3-minute song for about $0.05 on an L4. Feedback welcome,
especially from 16 GB Macs: I don't know yet whether they cope.
