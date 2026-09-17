# Songloom

A local app for generating full songs with the YuE2 music model on the user's own machine.

## Language

### Making a song

**Song request**:
What the user asks for: style, lyrics, planning mode, seed and render settings.
_Avoid_: prompt, job spec

**Planning mode**:
Whether the model first writes a Score, and how much of it: `full` (melody + chords), `melody`, or `off` (no Score).
_Avoid_: CoT, cot mode

**Score**:
The ABC-notation melody (and optionally chords) the model writes before making audio. Users can read and edit it.
_Avoid_: plan, sheet, ABC plan

**Take**:
One generated song produced from a Song request and a seed.
_Avoid_: result, output, generation

**Draft**:
A Take rendered with few synthesis steps (8) to judge it quickly.
_Avoid_: preview, fast mode

**Final**:
A Draft's Take re-rendered with full synthesis steps (32), keeping the same music.
_Avoid_: HQ render, full quality

**Finalize**:
Make a Draft's Final by re-synthesizing its saved Semantic tokens and noise; planning and semantic generation don't run again.
_Avoid_: upscale, enhance, re-render

**Cover**:
A song made from a recording the user uploads: it is transcribed into a Score, which is then re-sung with a new style and lyrics.
_Avoid_: remix, remake, version

**Variations**:
Several Takes of one Song request that differ only in seed, queued together and compared side by side.
_Avoid_: batch, candidates, alternatives

**Star**:
The user's pick among Takes; a single on/off mark on a song.
_Avoid_: favourite, like, rating

### Inside generation

**Stage**:
One step of a job's work. A Take passes through four: planning (writes the Score), semantic generation (writes Semantic tokens), synthesis (turns them into Latents), decoding (turns Latents into audio). A Cover has one of its own, transcribing, which comes before any of those.
_Avoid_: phase, step

**Semantic tokens**:
The model's intermediate musical content for a Take, produced token by token; the slow, sequential part.
_Avoid_: codes, AR output

**Latents**:
The compressed audio representation produced by synthesis and decoded into sound.
_Avoid_: NAR output, embeddings

**Synthesis steps**:
How many solver steps synthesis uses; trades time for audio quality.
_Avoid_: ODE steps, NAR steps, inference steps

**Engine**:
A runtime that executes the YuE2 model on some hardware (e.g. mlx-Yue, audio.cpp).
_Avoid_: backend, runtime, pipeline
