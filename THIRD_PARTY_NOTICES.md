# Third-party notices

## FluidR3 GM acoustic grand piano soundfont

`arcsong/soundfont/acoustic_grand_piano-mp3/` (88 note samples, 6.7 MB, served at
`/soundfont/` by the app, so one copy ships in the package rather than two in the build)
comes from the abcjs layout of
[midi-js-soundfonts](https://github.com/gleitz/midi-js-soundfonts) by Benjamin Gleitzman
(MIT licence), which packages samples from the FluidR3 GM soundfont by Frank Wen (MIT
licence). abcjs fetches one file per note, so the whole 88-key piano range (A0–C8) is
vendored. A hand-edited note above that range makes the preview say it could not load a
sample; one below it is simply silent. It is vendored so the Score view's melody preview
works without reaching the network; arcsong does not load anything from a CDN at runtime.

## Bundled JavaScript

The built page in `arcsong/static/` bundles [React](https://react.dev) (MIT),
[abcjs](https://www.abcjs.net) (MIT) and [wavesurfer.js](https://wavesurfer.xyz) (BSD-3-Clause).
Their licence texts ship inside their npm packages, listed in `web/package.json`.

## Model weights

The weights arcsong downloads are **not** covered by this repository's licence. All of them are
CC BY-NC 4.0 (non-commercial), and the Setup page shows and records that acknowledgement:

- Song model: [m-a-p/YuE2-3B](https://huggingface.co/m-a-p/YuE2-3B),
  [m-a-p/YuE2-Vae](https://huggingface.co/m-a-p/YuE2-Vae), converted for MLX as
  [vanch007/mlx-Yue2-3B](https://huggingface.co/vanch007/mlx-Yue2-3B).
- Covers (optional): [m-a-p/SheetSage2](https://huggingface.co/m-a-p/SheetSage2) and its parent
  [m-a-p/MERT-v2-FullSong](https://huggingface.co/m-a-p/MERT-v2-FullSong).

Covers also need [ffmpeg](https://ffmpeg.org), which arcsong detects but never ships: it is a
separate program under its own licence, installed by you.
