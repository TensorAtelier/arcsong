# Third-party notices

## FluidR3 GM acoustic grand piano soundfont

`songloom/soundfont/acoustic_grand_piano-mp3/` (88 note samples, 6.7 MB, served at
`/soundfont/` by the app, so one copy ships in the package rather than two in the build)
comes from the abcjs layout of
[midi-js-soundfonts](https://github.com/gleitz/midi-js-soundfonts) by Benjamin Gleitzman
(MIT licence), which packages samples from the FluidR3 GM soundfont by Frank Wen (MIT
licence). abcjs fetches one file per note, so the whole 88-key range is vendored and no
Score can fail to play. It is vendored so the Score view's melody preview works without
reaching the network; songloom does not load anything from a CDN at runtime.

## Bundled JavaScript

The built page in `songloom/static/` bundles [React](https://react.dev) (MIT),
[abcjs](https://www.abcjs.net) (MIT) and [wavesurfer.js](https://wavesurfer.xyz) (BSD-3-Clause).
Their licence texts ship inside their npm packages, listed in `web/package.json`.

## Model weights

The YuE2 weights songloom downloads are **not** covered by this repository's licence: they are
CC BY-NC 4.0 (non-commercial), and the Setup page shows and records that acknowledgement.
