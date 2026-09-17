# M0 report — Engine spike

Answers every M0 checkbox in `PLAN.md` from the committed results in `spike/results/`.
The tables inside `<!-- generated:… -->` blocks are rewritten by `uv run spike report`
from those files; everything else is interpretation, and every number in it comes from a
table below or names the results file it comes from. Figures that are not measurements
(star counts, release dates, file sizes of pinned downloads) name their source and are
marked as such. Times in results files are UTC; local time on the test Mac is UTC−7.
The interpretation reflects the results files as of this report's commit; regenerating
rewrites only the tables, and `tests/test_m0_report_numbers.py` cross-checks key
interpretation numbers against the committed results.

## Results files

<!-- generated:sources (tables from the results files; `uv run spike report` rewrites this block) -->
Machine: Apple M5 Pro (Mac17,9), 64 GiB, macOS 26.4.1

| Results file | Measurement | Engine | Case | Params | Outcome | Started (UTC) |
|---|---|---|---|---|---|---|
| `cancel-audiocpp-clip-q8_0-8-semantic_generation.json` | cancel | audio.cpp | clip | precision=q8_0, steps=8, stage=semantic generation | ok | 2026-09-17 02:22:22 |
| `cancel-audiocpp-clip-q8_0-8-synthesis.json` | cancel | audio.cpp | clip | precision=q8_0, steps=8, stage=synthesis | ok | 2026-09-17 02:22:35 |
| `cancel-audiocpp-song-q8_0-8-decoding.json` | cancel | audio.cpp | song | precision=q8_0, steps=8, stage=decoding | ok | 2026-09-17 02:22:54 |
| `cancel-audiocpp-song-q8_0-8-planning.json` | cancel | audio.cpp | song | precision=q8_0, steps=8, stage=planning | ok | 2026-09-17 02:35:54 |
| `cancel-mlx-clip-8bit-8-semantic_generation.json` | cancel | mlx-Yue | clip | precision=8bit, steps=8, stage=semantic generation | ok | 2026-09-17 02:16:30 |
| `cancel-mlx-clip-8bit-8-synthesis.json` | cancel | mlx-Yue | clip | precision=8bit, steps=8, stage=synthesis | ok | 2026-09-17 02:16:48 |
| `cancel-mlx-song-8bit-8-decoding.json` | cancel | mlx-Yue | song | precision=8bit, steps=8, stage=decoding | ok | 2026-09-17 02:17:13 |
| `cancel-mlx-song-8bit-8-planning.json` | cancel | mlx-Yue | song | precision=8bit, steps=8, stage=planning | ok | 2026-09-17 02:35:36 |
| `doctor-audiocpp-clip-bf16-32.json` | doctor | audio.cpp | clip | precision=bf16, steps=32 | ok | 2026-09-17 00:07:25 |
| `doctor-mlx-clip-bf16-32.json` | doctor | mlx-Yue | clip | precision=bf16, steps=32 | ok | 2026-09-16 22:41:03 |
| `download-mlx-weights.json` | download | mlx-Yue | weights | — | ok | 2026-09-17 04:46:03 |
| `draft-final-audiocpp-song-q8_0-8-32.json` | draft-final | audio.cpp | song | precision=q8_0, draft_steps=8, final_steps=32 | unsupported | 2026-09-17 03:43:41 |
| `draft-final-mlx-song-8bit-8-32.json` | draft-final | mlx-Yue | song | precision=8bit, draft_steps=8, final_steps=32 | ok | 2026-09-17 03:25:23 |
| `hygiene-mlx-clip-8bit-8.json` | hygiene | mlx-Yue | clip | precision=8bit, steps=8 | ok | 2026-09-17 04:49:14 |
| `repro-audiocpp-clip-q8_0-32-planned.json` | repro | audio.cpp | clip | precision=q8_0, steps=32, score=planned | ok | 2026-09-17 03:01:47 |
| `repro-mlx-clip-8bit-32-planned.json` | repro | mlx-Yue | clip | precision=8bit, steps=32, score=planned | ok | 2026-09-17 03:03:24 |
| `timing-audiocpp-song-bf16-32.json` | timing | audio.cpp | song | precision=bf16, steps=32 | ok | 2026-09-17 01:38:04 |
| `timing-audiocpp-song-bf16-8.json` | timing | audio.cpp | song | precision=bf16, steps=8 | ok | 2026-09-17 00:10:59 |
| `timing-audiocpp-song-q8_0-32.json` | timing | audio.cpp | song | precision=q8_0, steps=32 | ok | 2026-09-17 01:09:16 |
| `timing-audiocpp-song-q8_0-8.json` | timing | audio.cpp | song | precision=q8_0, steps=8 | ok | 2026-09-17 00:57:45 |
| `timing-mlx-song-8bit-32.json` | timing | mlx-Yue | song | precision=8bit, steps=32 | ok | 2026-09-16 23:25:17 |
| `timing-mlx-song-8bit-8.json` | timing | mlx-Yue | song | precision=8bit, steps=8 | ok | 2026-09-16 23:16:48 |
| `timing-mlx-song-bf16-32.json` | timing | mlx-Yue | song | precision=bf16, steps=32 | ok | 2026-09-16 22:57:28 |
| `timing-mlx-song-bf16-8.json` | timing | mlx-Yue | song | precision=bf16, steps=8 | ok | 2026-09-16 22:47:39 |
<!-- /generated:sources -->

## Engine recommendation

**Recommendation: build M1 on mlx-Yue.** D-017's first criterion decides it: with the
pinned audio.cpp release, planning cannot run alone and a Draft's Semantic tokens cannot
be re-synthesized, and both are M1 must-haves (no merged upstream change adds either). The later criteria are recorded below
for completeness; they do not overturn step 1. This is a proposal; confirm or override
it before M1.

### Step 1 — M1 must-haves (see [Engine choice](#engine-choice))

| Must-have | mlx-Yue | audio.cpp v0.8.0 |
|---|---|---|
| Cancel returns within ~5 s without a process kill, or a kill-and-reload the UI can live with | **Pass, no kill.** In-process cancel returned in 0.002–0.129 s in all four Stages; the next Take ran in the same process with no reload (`cancel-mlx-*.json`). | **Pass, by kill.** Killing the CLI returned in 0.065–0.120 s; the next Take ran in 11.2–13.9 s for `clip` (`cancel-audiocpp-*.json`). There is nothing to reload because every Take is a new process that loads the model anyway (`repro-audiocpp-clip-q8_0-32-planned.json`). |
| Per-Stage progress | **Pass.** Stage start and end come live from the staged API (`cancel-mlx-*.json`: the Stage was seen before cancel in 4 of 4 Stages). Progress within a Stage: not measured. | **Pass, Stage level only.** Stage starts are inferred from the `--log` line that ends the Stage before (4 of 4 Stages seen, `cancel-audiocpp-*.json`). In the `song` run log (`spike/runs/timing-audiocpp-song-q8_0-32/run-1/take/audiocpp.log`, not a results file) synthesis logs nothing until it ends and semantic generation logs at most a KV-cache refill line mid-Stage (useless for progress), so no % bar inside the two longest Stages; decoding logs one line per VAE chunk (6 lines). |
| Run planning alone (Score for #7) | **Pass.** `plan()` is a public Stage method and its Score is exported and was compared (`repro-mlx-clip-8bit-32-planned.json`), so "plan only → approve → render" stops after planning. | **Fail.** The CLI only runs a whole Take, and the Score is "not exported by the Engine" (`repro-audiocpp-clip-q8_0-32-planned.json`). audio.cpp PR #561 "Export generated Yue2 ABC plan as a score artifact" (merged 2026-09-15 23:09 UTC, after the v0.8.0 tag; source: GitHub) attaches the generated Score as `score.abc` to the result of a *full run*. That lets a UI show and edit a Score after a render and re-import it through `abc`, but it adds no way to stop after planning: plan-first is still a whole render on audio.cpp. |
| Re-synthesize saved Semantic tokens (#5) | **Pass.** The Final re-synthesized the Draft's 4618 Semantic tokens and noise and matched a direct 32-step render bit for bit (`draft-final-mlx-song-8bit-8-32.json`). | **Fail.** `unsupported`: the CLI neither exports nor accepts Semantic tokens, so a Final is a full re-run (`draft-final-audiocpp-song-q8_0-8-32.json`). PR #561 does not change this. |

mlx-Yue meets every must-have. audio.cpp as pinned fails two. **Step 1 selects mlx-Yue.**

### Step 2 — Speed and peak memory on `song` (see [Timing and peak memory](#timing-and-peak-memory))

- **Speed: mlx-Yue is faster at 8 steps and similar at 32.** The Engines wrote songs of different length
  (mlx-Yue 172.3 s bf16 and 184.7 s 8bit; audio.cpp 204.1 s bf16 and 216.3 s q8_0), so
  compare seconds per audio second. At 8 steps: mlx-Yue 8bit 1.30/1.45 and bf16
  1.58/1.83; audio.cpp q8_0 1.60/1.59 and bf16 2.01/2.02. At 32 steps: mlx-Yue bf16
  3.81/2.93 and 8bit 3.16/2.95; audio.cpp bf16 3.70/3.74 and q8_0 3.67/3.67 (run 1/run 2).
- **Memory: audio.cpp is much lower.** Lifetime peak footprint was 6.27–6.28 GiB for
  audio.cpp q8_0 and 8.85–8.86 GiB for bf16, against 10.50–10.81 GiB for mlx-Yue at either
  precision.
- **Caveats on the comparison:** see the conditions under the timing table. Nothing
  here could reverse step 1, so no case was rerun for this report.

### Step 3 — Install friction for end users

- **mlx-Yue.** A pinned git dependency that `uv sync` installs (ticket 01). Weights come
  from Hugging Face: three large safetensors of 2533.1, 4131.3 and 2793.8 MiB, plus a
  VAE (`download-mlx-weights.json`). A plain `snapshot_download(local_dir=…)` fails
  mlx-Yue's verification until the metadata files are deleted. That fix is known and
  small ([Model download](#model-download)). Apple Silicon only.
- **audio.cpp.** A prebuilt 26268059-byte macOS Metal tarball with a pinned sha256, and
  GGUF weights of 4264186432 bytes (q8_0) or 7261475392 bytes (bf16), plus a
  265218656-byte VAE (source: `spike/audiocpp_pins.json`, not a results file). No Python
  stack. The same project ships Metal, CUDA and Vulkan builds.
- **Verdict: audio.cpp is lighter to install,** most of all off the Mac. It does not
  outweigh step 1.

### Step 4 — Project health (source: `gh repo view` / `gh release list`, looked up 2026-09-17 UTC; not measurements)

- **audio.cpp** (`0xShug0/audio.cpp`): 2,799 stars, last push 2026-09-17. Six tagged
  releases from v0.7.0 (2026-08-27) to v0.8.0 (2026-09-15). The contributors API's first
  page is full (30).
- **mlx-Yue** (`vanch007/mlx-Yue`): 6 stars, 1 contributor, no releases. Created
  2026-09-13, last push 2026-09-15.
- **Verdict: audio.cpp is much healthier.** mlx-Yue is the single-maintainer risk PLAN.md
  already notes: pin the commit and re-audit before bumping.

### Hybrid options

1. **mlx-Yue on Mac (v1), audio.cpp for NVIDIA (M5)** instead of the official `yue2`
   package. This works only once audio.cpp exposes the staged operations: planning alone
   and Semantic-token input. PR #561 adds neither; it exports the Score after a full run.
   Until then, NVIDIA users would get Draft→Final as a full re-run, plan-first as a full
   render, and Score editing as edit-after-render with the edited Score supplied as `abc`
   input (the export half needs a release that contains PR #561).
2. **audio.cpp as a low-memory Mac fallback.** q8_0 peaked at 6.27–6.28 GiB against
   mlx-Yue's 10.50 GiB or more, which may bring 16 GB Macs into reach. #5 would be
   disabled there, and #7's plan-first step would be a full render; with a release that
   contains PR #561, a Score could at least be shown and edited after a render. This costs
   a second adapter in M1.
3. **Re-evaluate audio.cpp at M3/M5** once a release offers a planning-only run and
   Semantic tokens in and out (PR #561's Score export after a full run is a step, not
   either of those). Its install and health advantages would then count for more.

## Engine choice

<!-- generated:engine-choice (tables from the results files; `uv run spike report` rewrites this block) -->
| Criterion | mlx-Yue | audio.cpp |
|---|---|---|
| Doctor: `clip` Take renders | ok, mlx-Yue 0.1.0 @ 9253ed1 — `doctor-mlx-clip-bf16-32.json` | ok, audio.cpp 0.8.0 @ 4af1432 — `doctor-audiocpp-clip-bf16-32.json` |
| Cancel returns control (s) | 0.129 s, slowest of 4 Stages (decoding; in-process) — `cancel-mlx-song-8bit-8-decoding.json` | 0.120 s, slowest of 4 Stages (planning; process kill) — `cancel-audiocpp-song-q8_0-8-planning.json` |
| After a cancel | next Take ok after 4 of 4 cancels; harness reloads: 0 — `cancel-mlx-*.json` | next Take ok after 4 of 4 cancels; harness reloads: 0 — `cancel-audiocpp-*.json` |
| Takes reuse the loaded model | yes — `repro-mlx-clip-8bit-32-planned.json` | no: every Take is a new process that loads the model — `repro-audiocpp-clip-q8_0-32-planned.json` |
| Stage start seen live when cancel was requested | 4 of 4 Stages — `cancel-mlx-*.json` | 4 of 4 Stages — `cancel-audiocpp-*.json` |
| Score exported (planning usable alone) | yes — `repro-mlx-clip-8bit-32-planned.json` | no (not exported by the Engine) — `repro-audiocpp-clip-q8_0-32-planned.json` |
| Draft→Final from saved Semantic tokens | ok (Final by re-synthesis) — `draft-final-mlx-song-8bit-8-32.json` | unsupported (Final by full re-run) — `draft-final-audiocpp-song-q8_0-8-32.json` |
| Same seed, fresh process → bit-identical audio | yes — `repro-mlx-clip-8bit-32-planned.json` | yes — `repro-audiocpp-clip-q8_0-32-planned.json` |
| Fastest `song` Take at 8 steps (s per audio second) | 1.30 (8bit, run 1) — `timing-mlx-song-8bit-8.json` | 1.59 (q8_0, run 2) — `timing-audiocpp-song-q8_0-8.json` |
| Fastest `song` Take at 32 steps (s per audio second) | 2.93 (bf16, run 2) — `timing-mlx-song-bf16-32.json` | 3.67 (q8_0, run 2) — `timing-audiocpp-song-q8_0-32.json` |
| Lowest `song` peak footprint, lifetime (GiB) | 10.50 (8bit) — `timing-mlx-song-8bit-32.json` | 6.27 (q8_0) — `timing-audiocpp-song-q8_0-8.json` |
<!-- /generated:engine-choice -->

The table collects the evidence for the D-017 walk above. Two notes:

- **audio.cpp's cancel rows are kill-based.** "Harness reloads: 0" only means the next
  CLI process started normally. That process loads the model again for every Take.
- **The doctor row reads ticket 01's older results shape** for mlx-Yue. Both Engines
  rendered the `clip` case.

## Per-Stage timing split

<!-- generated:stage-timing (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Precision | Steps | Run | planning s (%) | semantic generation s (%) | synthesis s (%) | decoding s (%) | Source |
|---|---|---|---|---|---|---|---|---|
| mlx-Yue | bf16 | 8 | 1 | 53.1 (20%) | 115.3 (43%) | 88.0 (33%) | 10.1 (4%) | `timing-mlx-song-bf16-8.json` |
| mlx-Yue | bf16 | 8 | 2 | 55.9 (18%) | 129.5 (42%) | 110.9 (36%) | 11.8 (4%) | `timing-mlx-song-bf16-8.json` |
| mlx-Yue | bf16 | 32 | 1 | 62.9 (10%) | 136.7 (21%) | 438.0 (67%) | 11.8 (2%) | `timing-mlx-song-bf16-32.json` |
| mlx-Yue | bf16 | 32 | 2 | 59.1 (12%) | 112.4 (23%) | 315.7 (63%) | 10.3 (2%) | `timing-mlx-song-bf16-32.json` |
| mlx-Yue | 8bit | 8 | 1 | 37.9 (16%) | 85.2 (36%) | 97.1 (41%) | 13.8 (6%) | `timing-mlx-song-8bit-8.json` |
| mlx-Yue | 8bit | 8 | 2 | 42.3 (16%) | 98.5 (38%) | 109.0 (42%) | 11.2 (4%) | `timing-mlx-song-8bit-8.json` |
| mlx-Yue | 8bit | 32 | 1 | 39.6 (7%) | 87.9 (15%) | 437.5 (76%) | 12.8 (2%) | `timing-mlx-song-8bit-32.json` |
| mlx-Yue | 8bit | 32 | 2 | 40.6 (8%) | 89.2 (17%) | 395.9 (74%) | 11.7 (2%) | `timing-mlx-song-8bit-32.json` |
| audio.cpp | bf16 | 8 | 1 | 61.9 (15%) | 152.4 (37%) | 175.2 (43%) | 20.7 (5%) | `timing-audiocpp-song-bf16-8.json` |
| audio.cpp | bf16 | 8 | 2 | 60.4 (15%) | 156.0 (38%) | 175.3 (43%) | 20.1 (5%) | `timing-audiocpp-song-bf16-8.json` |
| audio.cpp | bf16 | 32 | 1 | 57.0 (8%) | 142.1 (19%) | 535.6 (71%) | 19.0 (3%) | `timing-audiocpp-song-bf16-32.json` |
| audio.cpp | bf16 | 32 | 2 | 56.6 (7%) | 143.0 (19%) | 543.3 (71%) | 19.1 (3%) | `timing-audiocpp-song-bf16-32.json` |
| audio.cpp | q8_0 | 8 | 1 | 41.6 (12%) | 125.0 (36%) | 158.5 (46%) | 20.1 (6%) | `timing-audiocpp-song-q8_0-8.json` |
| audio.cpp | q8_0 | 8 | 2 | 40.4 (12%) | 125.2 (36%) | 157.9 (46%) | 20.1 (6%) | `timing-audiocpp-song-q8_0-8.json` |
| audio.cpp | q8_0 | 32 | 1 | 40.3 (5%) | 125.2 (16%) | 607.8 (77%) | 20.1 (3%) | `timing-audiocpp-song-q8_0-32.json` |
| audio.cpp | q8_0 | 32 | 2 | 40.3 (5%) | 125.2 (16%) | 607.2 (77%) | 20.2 (3%) | `timing-audiocpp-song-q8_0-32.json` |
<!-- /generated:stage-timing -->

**Synthesis dominates at 32 steps.** It took 63–77% of the Stage time on both Engines
(mlx-Yue 315.7–438.0 s, audio.cpp 535.6–607.8 s). At 8 steps it drops to 33–46%, and
semantic generation (36–43%) and planning (12–20%) together take more time than synthesis.

**Planning is not "seconds" for a ~3-minute song.** It took 37.9–62.9 s on mlx-Yue and
40.3–61.9 s on audio.cpp. That is still much cheaper than the rest of a Take, so plan-first
(#7) remains a real iteration lever: rejecting a Score saves its semantic generation and
synthesis.

**So both levers matter:**

- **Draft→Final (#5)** attacks the Stage that dominates a 32-step Take.
- **Plan-first (#7)** avoids spending anything past planning on a Score the user rejects.

The mlx-Yue timing matrix ran with LM Studio and ComfyUI running (see the conditions
under [Timing and peak memory](#timing-and-peak-memory)). Run-to-run synthesis varied
from 438.0 s to 315.7 s for bf16/32, so read single mlx-Yue runs with care. audio.cpp's
two runs agreed closely: q8_0/32 synthesis took 607.8 and 607.2 s.

## Seed reproducibility

<!-- generated:reproducibility (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Precision | Steps | Pair | Warm Takes shared a loaded model | Score | Semantic tokens | Latents | Audio | Source |
|---|---|---|---|---|---|---|---|---|---|
| mlx-Yue | 8bit | 32 | warm vs warm | yes | identical | identical | identical (max abs 0.0) | bit-identical | `repro-mlx-clip-8bit-32-planned.json` |
| mlx-Yue | 8bit | 32 | warm vs fresh | yes | identical | identical | identical (max abs 0.0) | bit-identical | `repro-mlx-clip-8bit-32-planned.json` |
| audio.cpp | q8_0 | 32 | warm vs warm | no | not exported by the Engine | not exported by the Engine | not exported by the Engine | bit-identical | `repro-audiocpp-clip-q8_0-32-planned.json` |
| audio.cpp | q8_0 | 32 | warm vs fresh | no | not exported by the Engine | not exported by the Engine | not exported by the Engine | bit-identical | `repro-audiocpp-clip-q8_0-32-planned.json` |
<!-- /generated:reproducibility -->

**mlx-Yue reproduces a Take exactly.** Same Song request and seed gave the same Score, the
same Semantic tokens, Latents with a max abs difference of 0.0, and bit-identical audio.
This held both in the warm process that reused the loaded model and in a fresh process.
"Re-run with these settings" can say "same", not "similar", for the same precision and
Synthesis steps on this Mac.

**Precision is part of the settings.** bf16 and 8bit wrote songs of different length from
the same seed (172.3 s vs 184.7 s, `timing-mlx-song-*.json`). Reproducing across precisions,
Engine versions or machines was not measured.

**audio.cpp's audio was also bit-identical,** but only audio could be compared: the CLI
exports no Score, Semantic tokens or Latents. Its "warm" pair is two cold CLI runs, because
the Engine starts a new process for every Take, so reproducibility inside one warm process
was not tested.

## Artifact sizes

<!-- generated:artifact-sizes (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Precision | Steps | Audio (s) | Audio file (MiB) | `.npy` intermediates (MiB) | Other files (KiB) | All files (MiB) | Source |
|---|---|---|---|---|---|---|---|---|
| mlx-Yue | bf16 | 8 | 172.3 | 35.1 (audio.flac) | 2.1 | 57.2 | 37.3 | `timing-mlx-song-bf16-8.json` run 1 |
| mlx-Yue | bf16 | 32 | 172.3 | 35.1 (audio.flac) | 2.1 | 57.2 | 37.3 | `timing-mlx-song-bf16-32.json` run 1 |
| mlx-Yue | 8bit | 8 | 184.7 | 38.1 (audio.flac) | 2.3 | 59.1 | 40.5 | `timing-mlx-song-8bit-8.json` run 1 |
| mlx-Yue | 8bit | 32 | 184.7 | 38.2 (audio.flac) | 2.3 | 59.1 | 40.5 | `timing-mlx-song-8bit-32.json` run 1 |
| audio.cpp | bf16 | 8 | 204.1 | 37.4 (audio.wav) | none | 24.5 | 37.4 | `timing-audiocpp-song-bf16-8.json` run 1 |
| audio.cpp | bf16 | 32 | 204.1 | 37.4 (audio.wav) | none | 24.5 | 37.4 | `timing-audiocpp-song-bf16-32.json` run 1 |
| audio.cpp | q8_0 | 8 | 216.3 | 39.6 (audio.wav) | none | 25.7 | 39.6 | `timing-audiocpp-song-q8_0-8.json` run 1 |
| audio.cpp | q8_0 | 32 | 216.3 | 39.6 (audio.wav) | none | 25.7 | 39.6 | `timing-audiocpp-song-q8_0-32.json` run 1 |

Every file a `song` Take wrote, mlx-Yue, run 1 (bytes):

| File | bf16/8 (`timing-mlx-song-bf16-8.json`) | bf16/32 (`timing-mlx-song-bf16-32.json`) | 8bit/8 (`timing-mlx-song-8bit-8.json`) | 8bit/32 (`timing-mlx-song-8bit-32.json`) |
|---|---|---|---|---|
| abc_tokens.npy | 7988 | 7988 | 8412 | 8412 |
| audio.flac | 36785787 | 36825623 | 39998986 | 40003786 |
| config.json | 1737 | 1716 | 1737 | 1716 |
| latent.npy | 1102976 | 1102976 | 1182336 | 1182336 |
| noise.npy | 1102976 | 1102976 | 1182336 | 1182336 |
| plan.json | 44309 | 44310 | 45966 | 45966 |
| plan_manifest.json | 341 | 341 | 341 | 341 |
| prefix.npy | 9896 | 9896 | 10320 | 10320 |
| request.json | 1665 | 1665 | 1665 | 1665 |
| result.json | 7810 | 7815 | 7951 | 7947 |
| score.abc | 2745 | 2745 | 2844 | 2844 |
| semantic.npy | 17360 | 17360 | 18600 | 18600 |

Every file a `song` Take wrote, audio.cpp, run 1 (bytes):

| File | bf16/8 (`timing-audiocpp-song-bf16-8.json`) | bf16/32 (`timing-audiocpp-song-bf16-32.json`) | q8_0/8 (`timing-audiocpp-song-q8_0-8.json`) | q8_0/32 (`timing-audiocpp-song-q8_0-32.json`) |
|---|---|---|---|---|
| audio.wav | 39190828 | 39190828 | 41533228 | 41533228 |
| audiocpp.log | 25117 | 25103 | 26341 | 26344 |
<!-- /generated:artifact-sizes -->

**The audio file is almost all of a Take.** An mlx-Yue `song` Take is 37.3–40.5 MiB, of
which the FLAC is 35.1–38.2 MiB. All `.npy` intermediates together are 2.1–2.3 MiB, and the
two that Draft→Final needs (`semantic.npy` 17360–18600 bytes, `noise.npy` 1102976–1182336
bytes) are small. audio.cpp writes only a WAV of 37.4–39.6 MiB and its log.

**Library cleanup should target whole Takes** (unwanted Drafts, losing variations), not
intermediates. Keeping the `.npy` files so any Take can get a Final costs about 2 MiB per
Take. Synthesis steps barely change the size: 8- and 32-step Takes of the same precision are within 0.1 MiB.

## Per-Stage progress

<!-- generated:progress (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Stage | Stage start seen (s into the Take) | Cancel landed in it | Source |
|---|---|---|---|---|
| mlx-Yue | planning | 0.000 | yes | `cancel-mlx-song-8bit-8-planning.json` |
| mlx-Yue | semantic generation | 0.001 | yes | `cancel-mlx-clip-8bit-8-semantic_generation.json` |
| mlx-Yue | synthesis | 6.722 | yes | `cancel-mlx-clip-8bit-8-synthesis.json` |
| mlx-Yue | decoding | 215.456 | yes | `cancel-mlx-song-8bit-8-decoding.json` |
| audio.cpp | planning | 0.395 | yes | `cancel-audiocpp-song-q8_0-8-planning.json` |
| audio.cpp | semantic generation | 0.393 | yes | `cancel-audiocpp-clip-q8_0-8-semantic_generation.json` |
| audio.cpp | synthesis | 6.210 | yes | `cancel-audiocpp-clip-q8_0-8-synthesis.json` |
| audio.cpp | decoding | 315.235 | yes | `cancel-audiocpp-song-q8_0-8-decoding.json` |

Progress within a Stage (how often callbacks fire, whether they map to a % bar): not measured — no results file records callback counts or rates.
<!-- /generated:progress -->

**Both Engines report Stage transitions live.** mlx-Yue's staged API emits a Stage's
start as it happens; its synthesis start at 6.722 s and decoding start at 215.456 s were
seen before cancel was requested. audio.cpp's Stage starts are inferred from the log line
that ends the previous Stage, for example decoding at 315.235 s. Its Stage *durations*
arrive only when a Stage ends.

**Progress within a Stage was not measured.** No results file records how often mlx-Yue's
`on_token` or step callbacks fire, so whether they map to a % bar is still open.
audio.cpp's `--log` gives no usable progress inside planning's Score writing, semantic generation or
synthesis. In the `song` run log `spike/runs/timing-audiocpp-song-q8_0-32/run-1/take/audiocpp.log`
(a run directory, not a results file), semantic generation logged only a KV-cache refill
(lines stamped 18:11:49, about 111 s into the Stage) and synthesis logged nothing between its setup lines and
its end, which the results file puts at 607.8 s. Decoding does log inside the Stage: that
log has 6 `framework.oobleck_audio_vae.decode.full_ms` lines, one per VAE chunk, about 4 s
apart, which could drive a coarse decoding bar.

**M1a should measure the callback rate** before designing the progress throttle. A
Stage-level bar (4 segments) is supported by the evidence today.

## Cancellation

<!-- generated:cancellation (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Stage | Case | Cancel after (s) | Latency (s) | How | Kill→exit (s) | Left on disk | Looks like a Take | Next Take | Next Take (s) | Source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mlx-Yue | planning | song | 1.0 | 0.010 | in-process (InterruptedError) | — | nothing | no | ok, harness reload: no | 10.2 | `cancel-mlx-song-8bit-8-planning.json` |
| mlx-Yue | semantic generation | clip | 1.0 | 0.002 | in-process (InterruptedError) | — | nothing | no | ok, harness reload: no | 10.5 | `cancel-mlx-clip-8bit-8-semantic_generation.json` |
| mlx-Yue | synthesis | clip | 1.0 | 0.122 | in-process (InterruptedError) | — | nothing | no | ok, harness reload: no | 10.4 | `cancel-mlx-clip-8bit-8-synthesis.json` |
| mlx-Yue | decoding | song | 1.0 | 0.129 | in-process (InterruptedError) | — | nothing | no | ok, harness reload: no | 10.6 | `cancel-mlx-song-8bit-8-decoding.json` |
| audio.cpp | planning | song | 1.0 | 0.120 | process kill | 0.076 | audiocpp.log (9781 B) | no | ok, harness reload: no | 11.3 | `cancel-audiocpp-song-q8_0-8-planning.json` |
| audio.cpp | semantic generation | clip | 1.0 | 0.080 | process kill | 0.056 | audiocpp.log (9629 B), score.abc (339 B) | no | ok, harness reload: no | 11.2 | `cancel-audiocpp-clip-q8_0-8-semantic_generation.json` |
| audio.cpp | synthesis | clip | 1.0 | 0.065 | process kill | 0.040 | audiocpp.log (13991 B), score.abc (339 B) | no | ok, harness reload: no | 11.8 | `cancel-audiocpp-clip-q8_0-8-synthesis.json` |
| audio.cpp | decoding | song | 1.0 | 0.065 | process kill | 0.043 | audiocpp.log (20849 B) | no | ok, harness reload: no | 13.9 | `cancel-audiocpp-song-q8_0-8-decoding.json` |
<!-- /generated:cancellation -->

**mlx-Yue cancels promptly and stays usable.** `cancelled()` stopped every Stage in
0.002–0.129 s. It left nothing on disk, and the same process then rendered a full `clip`
Take in 10.2–10.6 s with no reload. The worker can use cooperative cancel. The planned
"kill the worker after a grace period" path is still a sensible guard, but none of the
four Stages needed it.

**audio.cpp can only cancel by killing its process.** That took 0.065–0.120 s (kill to
exit 0.040–0.076 s). It left its log, plus the supplied `score.abc` for `clip`, and
nothing that looks like a Take. The next Take is a new process, as every audio.cpp Take is.

## Draft→Final

<!-- generated:draft-final (tables from the results files; `uv run spike report` rewrites this block) -->
|  | mlx-Yue | audio.cpp |
|---|---|---|
| Outcome | ok (Final by re-synthesis) | unsupported (Final by full re-run) |
| Precision, steps | 8bit, 8→32 | q8_0, 8→32 |
| Draft render (s) | 223.2 | 334.5 |
| Harness noise probe, not in the Draft (s) | — | 165.2 |
| Final render (s) | 360.8 | 772.8 |
| Direct 32-step render (s) | 485.5 | 776.9 |
| Final ÷ direct | 0.743 | 0.995 |
| Draft + Final (s) | 583.9 | 1107.3 |
| Same-seed full re-run (s) | — | 776.9 |
| Semantic tokens reused | identical (4618 tokens) | no — audio.cpp's CLI cannot take a Draft's Semantic tokens back: it neither exports them nor accepts them as input, so a Final means re-running the whole Take |
| Synthesis noise reused | identical | supplied from the Draft's noise file |
| Final vs direct 32-step | first differs at: none; audio bit-identical | first differs at: decoding; audio differs (max abs 1.334, correlation 0.035) |
| Draft vs Final | first differs at: synthesis; audio differs (max abs 0.673, correlation 0.984) | first differs at: decoding; audio differs (max abs 0.760, correlation 0.987) |
| Peak footprint, lifetime (GiB), per process | draft 10.92, direct 11.05 | draft 6.29, direct 6.28 |
| Source | `draft-final-mlx-song-8bit-8-32.json` | `draft-final-audiocpp-song-q8_0-8-32.json` |
<!-- /generated:draft-final -->

**mlx-Yue: feasible and exact.** The Final re-synthesized the Draft's Semantic tokens and
noise at 32 steps. It matched a direct 32-step render from a separate process bit for bit,
which proves the Final really was re-synthesized.

- **What a Final costs.** It took 360.8 s against 485.5 s for the direct 32-step render,
  or 0.743 of the time. Use the harness's Final time: the Final's own `result.json`
  repeats the Draft's planning and semantic timings.
- **When the saving applies.** Only for Drafts that go on to get a Final. A Draft plus its
  Final (223.2 + 360.8 = 583.9 s) takes 98.4 s longer than rendering 32 steps directly.
  With two Drafts judged per Final it pays (sums from the file's unrounded seconds): 2 × 223.2 + 360.8 = 807.1 s, against
  2 × 485.5 = 971.1 s for two direct renders. The Draft gets a first listen in 223.2 s
  instead of 485.5 s.

**audio.cpp: `unsupported`.** The CLI cannot take a Draft's Semantic tokens back, so a
Final is a full re-run.

- **Real Final cost.** The same-seed full re-run took 776.9 s.
- **Not a saving.** The 772.8 s "Final" (a full re-run with the Draft's noise file) against
  the 776.9 s direct render is run-to-run jitter between two full re-runs.
- **Noise probe.** The 165.2 s probe was harness work so the Draft's noise could be
  supplied as a file. It is not part of a Draft.
- **Plain same-seed Drafts (inferred, not measured).** Such a Draft needs no probe and
  shares the Engine's own noise with the direct render. This follows from ticket 06's
  bit-identical same-seed audio.

## Timing and peak memory

<!-- generated:timing-memory (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Precision | Steps | Run | Model load (s) | Total (s) | Audio (s) | s per audio s | Peak footprint, lifetime (GiB) | Peak footprint, 250 ms samples (GiB) | MLX peak (GiB) | Source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mlx-Yue | bf16 | 8 | 1 | 6.6 | 273.1 | 172.3 | 1.58 | 10.80 | 10.78 | 10.48 | `timing-mlx-song-bf16-8.json` |
| mlx-Yue | bf16 | 8 | 2 | 6.7 | 314.7 | 172.3 | 1.83 | 10.81 | 10.79 | 10.48 | `timing-mlx-song-bf16-8.json` |
| mlx-Yue | bf16 | 32 | 1 | 6.8 | 656.0 | 172.3 | 3.81 | 10.75 | 10.46 | 10.48 | `timing-mlx-song-bf16-32.json` |
| mlx-Yue | bf16 | 32 | 2 | 6.7 | 504.0 | 172.3 | 2.93 | 10.73 | 10.30 | 10.48 | `timing-mlx-song-bf16-32.json` |
| mlx-Yue | 8bit | 8 | 1 | 6.7 | 240.5 | 184.7 | 1.30 | 10.73 | 10.22 | 10.61 | `timing-mlx-song-8bit-8.json` |
| mlx-Yue | 8bit | 8 | 2 | 7.0 | 267.7 | 184.7 | 1.45 | 10.73 | 10.14 | 10.61 | `timing-mlx-song-8bit-8.json` |
| mlx-Yue | 8bit | 32 | 1 | 6.9 | 584.5 | 184.7 | 3.16 | 10.50 | 9.84 | 10.61 | `timing-mlx-song-8bit-32.json` |
| mlx-Yue | 8bit | 32 | 2 | 7.1 | 544.3 | 184.7 | 2.95 | 10.50 | 10.00 | 10.61 | `timing-mlx-song-8bit-32.json` |
| audio.cpp | bf16 | 8 | 1 | 7.0 | 411.3 | 204.1 | 2.01 | 8.86 | 8.85 | — | `timing-audiocpp-song-bf16-8.json` |
| audio.cpp | bf16 | 8 | 2 | 6.1 | 412.7 | 204.1 | 2.02 | 8.85 | 8.84 | — | `timing-audiocpp-song-bf16-8.json` |
| audio.cpp | bf16 | 32 | 1 | 5.3 | 754.4 | 204.1 | 3.70 | 8.85 | 8.84 | — | `timing-audiocpp-song-bf16-32.json` |
| audio.cpp | bf16 | 32 | 2 | 5.3 | 763.0 | 204.1 | 3.74 | 8.85 | 8.84 | — | `timing-audiocpp-song-bf16-32.json` |
| audio.cpp | q8_0 | 8 | 1 | 3.5 | 346.4 | 216.3 | 1.60 | 6.27 | 6.26 | — | `timing-audiocpp-song-q8_0-8.json` |
| audio.cpp | q8_0 | 8 | 2 | 1.0 | 344.7 | 216.3 | 1.59 | 6.27 | 6.26 | — | `timing-audiocpp-song-q8_0-8.json` |
| audio.cpp | q8_0 | 32 | 1 | 1.0 | 794.6 | 216.3 | 3.67 | 6.28 | 6.26 | — | `timing-audiocpp-song-q8_0-32.json` |
| audio.cpp | q8_0 | 32 | 2 | 1.0 | 794.1 | 216.3 | 3.67 | 6.27 | 6.26 | — | `timing-audiocpp-song-q8_0-32.json` |

Conditions recorded with each timing case:

| Source | Started (UTC) | Ended (UTC) | Other model servers | ComfyUI RSS (MiB) | LM Studio RSS (MiB) |
|---|---|---|---|---|---|
| `timing-mlx-song-bf16-8.json` | 2026-09-16 22:47 | 22:57 | ComfyUI, LM Studio | 55 | 361 |
| `timing-mlx-song-bf16-32.json` | 2026-09-16 22:57 | 23:16 | ComfyUI, LM Studio | 55 | 366 |
| `timing-mlx-song-8bit-8.json` | 2026-09-16 23:16 | 23:25 | ComfyUI, LM Studio | 55 | 370 |
| `timing-mlx-song-8bit-32.json` | 2026-09-16 23:25 | 23:44 | ComfyUI, LM Studio | 55 | 371 |
| `timing-audiocpp-song-bf16-8.json` | 2026-09-17 00:10 | 00:24 | ComfyUI, LM Studio | 56 | 401 |
| `timing-audiocpp-song-bf16-32.json` | 2026-09-17 01:38 | 02:03 | ComfyUI, LM Studio | 583 | 502 |
| `timing-audiocpp-song-q8_0-8.json` | 2026-09-17 00:57 | 01:09 | ComfyUI, LM Studio | 583 | 489 |
| `timing-audiocpp-song-q8_0-32.json` | 2026-09-17 01:09 | 01:35 | ComfyUI, LM Studio | 583 | 492 |
<!-- /generated:timing-memory -->

**How the columns compare:**

- **s per audio s** uses each run's `total_seconds` (model load plus Take), because audio.cpp
  loads the model inside its run.
- **Model load** is `model_load_seconds` for both Engines: mlx-Yue 6.6–7.1 s; audio.cpp
  bf16 5.3–7.0 s and q8_0 1.0–3.5 s.
- **Peak memory:** quote the lifetime figure. The 250 ms samples read up to 0.66 GiB lower
  (mlx-Yue 8bit/32 run 1: 10.50 against 9.84).

**Precision on mlx-Yue.**

- **Speed: 8bit is faster only at 8 steps.** 8bit ran 1.30/1.45 s per audio second at 8
  steps against bf16's 1.58/1.83. At 32 steps it is mixed: 8bit 3.16/2.95 against bf16
  3.81/2.93, and bf16 run 2 was the fastest 32-step run.
- **Memory: 8bit saves little.** Each 8bit run's lifetime peak is below the matching bf16
  run by only 0.08–0.25 GiB (8 steps: 10.73/10.73 against 10.80/10.81 GiB; 32 steps:
  10.50/10.50 against 10.75/10.73 GiB; differences from unrounded bytes). MLX's own peak is
  higher for 8bit (10.61 against 10.48 GiB).
- **A likely reason (inferred, not measured):** only the semantic-generation model has an
  8bit file. The converted weights hold `ar-8bit`, `ar-bf16` and `nar-bf16` and no 8bit
  synthesis model (`download-mlx-weights.json`), so synthesis, the dominant Stage at 32
  steps, runs bf16 at either precision.
- **Draft→Final peaked higher.** Those runs reached 10.92 GiB (draft process) and
  11.05 GiB (direct process) (`draft-final-mlx-song-8bit-8-32.json`).
- **On audio.cpp, q8_0 does save memory:** 6.27–6.28 GiB against 8.85–8.86 GiB.

**Conditions next to these numbers.** Only the model-server list and start times are in
the results files; the rest comes from ticket QA notes and `pmset` logs.

- **Other model servers.** LM Studio and ComfyUI were running for every timing case (table
  above). ComfyUI's RSS was 55–56 MiB up to the audio.cpp bf16/8 case and 583 MiB after.
  RSS does not show Metal memory: per the ticket 04 notes, the user freed ComfyUI's
  memory at about 17:50 local (00:50 UTC), between audio.cpp bf16/8 and q8_0/8.
- **Power.** Every mlx-Yue result ran on AC, because the harness passes mlx-Yue's
  `require_ac=True`. Per `pmset`, audio.cpp bf16/8 (00:10–00:24 UTC, 17:10–17:24 local) ran
  on **battery**, and the other audio.cpp cases ran on AC.
- **Sleep.** The Mac slept 17:38–17:44 local (00:38–00:44 UTC). No kept result overlaps it:
  the affected audio.cpp bf16/32 case was rerun under `caffeinate` and started at 01:38 UTC.
  The audio.cpp log parser clamps a Stage start that appears to begin before the previous
  Stage ended (a sign of sleep) without flagging it in the results; no kept result was clamped.
- **Possible battery effect.** audio.cpp bf16/8's synthesis took 175.2/175.3 s, slower than
  q8_0/8's 158.5/157.9 s, even though bf16 synthesized faster than q8_0 at 32 steps
  (535.6/543.3 s against 607.8/607.2 s). Battery power may explain it, so treat audio.cpp
  bf16/8 as a possibly slow reading. It was not rerun: even a much faster bf16/8 could
  not change step 1 of the recommendation.
- **Run-to-run variance on mlx-Yue** reached 656.0 against 504.0 s total for bf16/32; the
  cause (background servers or thermal state) is not recorded.

## Stale resource files

<!-- generated:stale-resource-files (tables from the results files; `uv run spike report` rewrites this block) -->
| Engine | Path | Killed in | After Stage start (s) | Resource files left | Rerun, no cleanup | Cleanup rule | Rerun after cleanup | Source |
|---|---|---|---|---|---|---|---|---|
| mlx-Yue | staged API | synthesis | 1.08 | none | ok | none needed | not needed | `hygiene-mlx-clip-8bit-8.json` |
| mlx-Yue | Engine command line | synthesis | 1.09 | take.resources.jsonl | failed: FileExistsError: Resource evidence already exists: …/take.resources.jsonl | remove take.resources.jsonl | ok | `hygiene-mlx-clip-8bit-8.json` |
<!-- /generated:stale-resource-files -->

**The staged API avoids the stale-resource-file problem.** Killed mid-synthesis, it left no
`<output>.resources.json[l]` and a rerun to the same output directory succeeded with no
cleanup. Only mlx-Yue's command line writes resource evidence: it left
`take.resources.jsonl`, the rerun failed with `FileExistsError`, and removing that file
fixed it. The M1 worker, which uses the staged API, needs no resource-file cleanup.

**Gap for M1's worker cleanup:** only kills during synthesis were measured. A kill while
a Take is being saved (a partly written output directory) was not.

## Model download

<!-- generated:model-download (tables from the results files; `uv run spike report` rewrites this block) -->
|  | mlx-Yue |
|---|---|
| Sources | vanch007/mlx-Yue2-3B @ fa66d20 → converted/; m-a-p/YuE2-Vae @ 95535e7 → vae/ |
| Download time (s) | 10.9 |
| Files fetched | 12 files, 508.4 MiB |
| Large weights cloned locally, not fetched | converted/ar-8bit.safetensors (2533.1 MiB), converted/ar-bf16.safetensors (4131.3 MiB), converted/nar-bf16.safetensors (2793.8 MiB) |
| Metadata files the hub added | 30 (converted/ 21, vae/ 9) |
| Verification as downloaded | failed (unexpected in the converted directory: 22 files) |
| Fix steps | remove converted/.cache, vae/.cache → failed (unexpected in the converted directory: .gitattributes); remove converted/.gitattributes → ok |
| `snapshot_download` again over the same directory | 1.3 s; 28 metadata files; failed (unexpected in the converted directory: 21 files); then remove converted/.cache, vae/.cache → failed (unexpected in the converted directory: .gitattributes); remove converted/.gitattributes → ok |
| Fix that works | yes: remove converted/.cache, vae/.cache, converted/.gitattributes |
| Temporary directory deleted | yes |
| Source | `download-mlx-weights.json` |
<!-- /generated:model-download -->

**A plain `snapshot_download(local_dir=…)` breaks mlx-Yue's verification.** The hub adds
`.cache/huggingface/…` metadata, and the converted repository brings a `.gitattributes`.
Both make mlx-Yue's verification reject the converted directory.

**The fix is to delete two things after download:** `converted/.cache` and
`converted/.gitattributes` (or pass `ignore_patterns` for `.gitattributes` when
downloading). The harness also deleted `vae/.cache`. Every verification error names only
the converted directory, so `vae/.cache` does not break VAE verification. That last point
is inferred from the error text and ticket 08's reading of the source; it was not removed
separately.

**Scope of the check:** the small files plus the VAE (12 files, 508.4 MiB fetched over the
network). The three large safetensors were cloned locally, not downloaded. A real full
download would add metadata and lock files for them too, which deleting `.cache` still
covers.

**The second pass was not a fresh download.** It is `snapshot_download` over the same
directory: huggingface_hub re-hashed the VAE and skipped it, and fetched only the small
files again (1.3 s).

## Listening pairs

<!-- generated:listening-pairs (tables from the results files; `uv run spike report` rewrites this block) -->
| Measurement | Engine | Pair | Files | Source |
|---|---|---|---|---|
| repro | audio.cpp | warm vs fresh | `/Users/julian/projects/songloom/spike/listen/repro-audiocpp-clip-q8_0-32-planned/warm-take-1.flac`<br>`/Users/julian/projects/songloom/spike/listen/repro-audiocpp-clip-q8_0-32-planned/fresh-take-1.flac` | `repro-audiocpp-clip-q8_0-32-planned.json` |
| repro | mlx-Yue | warm vs fresh | `/Users/julian/projects/songloom/spike/listen/repro-mlx-clip-8bit-32-planned/warm-take-1.flac`<br>`/Users/julian/projects/songloom/spike/listen/repro-mlx-clip-8bit-32-planned/fresh-take-1.flac` | `repro-mlx-clip-8bit-32-planned.json` |
| draft-final | audio.cpp | draft vs final | `/Users/julian/projects/songloom/spike/listen/draft-final-audiocpp-song-q8_0-8-32/draft-8.flac`<br>`/Users/julian/projects/songloom/spike/listen/draft-final-audiocpp-song-q8_0-8-32/final-32.flac` | `draft-final-audiocpp-song-q8_0-8-32.json` |
| draft-final | mlx-Yue | draft vs final | `/Users/julian/projects/songloom/spike/listen/draft-final-mlx-song-8bit-8-32/draft-8.flac`<br>`/Users/julian/projects/songloom/spike/listen/draft-final-mlx-song-8bit-8-32/final-32.flac` | `draft-final-mlx-song-8bit-8-32.json` |
<!-- /generated:listening-pairs -->

The files are in the gitignored `spike/listen/` directory on this Mac.

**Same seed (`clip`, 16 s, warm vs fresh Take).** Both Engines' pairs are bit-identical,
so they should sound identical. Listening only confirms that the copies play and nothing
was mixed up.

**Draft vs Final (`song`, 8 vs 32 Synthesis steps).** The music should be the same:
melody, lyrics, arrangement and timing (mlx-Yue audio correlation 0.984). Listen for:

- **Quality:** vocal clarity and diction; hiss, sibilance or a metallic or "watery" timbre
  in the Draft; smeared drums and transients; high-frequency detail and stereo width.
- **Decisions:** whether the Draft is good enough to judge the song, and whether the Final
  sounds better by enough to spend 360.8 s on it (mlx-Yue).
- **audio.cpp's pair** used the same noise file for both renders.

## Findings that affect the plan

Flags for the user. `PLAN.md` is changed only inside its M0 section: the checkboxes are ticked except per-stage progress, one pointer line to this report was added under the M0 heading, and the progress checkbox stays open with a one-line note that callback rate within a Stage was not measured.

1. **Engine choice (M0, Architecture, M5).** mlx-Yue is recommended for v1 by D-017 step 1 (a proposal: confirm or override it).
   M5's NVIDIA path is still open: audio.cpp is healthier and easier to install, but it
   needs Semantic-token input before it can back #5. Revisit at M5 (see Hybrid options).
2. **#5 placement ("v1 if M0 confirms").** Feasibility is confirmed on mlx-Yue, with
   bit-identical Finals, and synthesis dominates a 32-step Take. The saving appears only
   with two or more Drafts per Final. One Draft kept as a Final costs 98.4 s more than a
   direct render. #5 therefore fits naturally with M2 variations (N Drafts, then finalize
   the pick). For v1 alone, its value is the faster first listen (223.2 s vs 485.5 s).
   Decide whether that justifies v1.
3. **#5 row and the M0 note "Planning reportedly takes seconds".** For the ~3-minute
   song, planning took 37.9–62.9 s. The #5 row's premise "if semantic generation
   dominates" does not hold at 32 steps: synthesis does.
4. **Memory-aware defaults.** "Default to 8-bit on small machines" lowers mlx-Yue's peak
   only 0.08–0.25 GiB per matched run (8bit 10.50–10.73 GiB against bf16 10.73–10.81 GiB),
   likely because synthesis has only a bf16 model. 8-bit buys speed at 8 steps, little
   memory. A small-machine default needs another lever, or a RAM floor.
5. **Minimum RAM.** It was measured only on a 64 GiB Mac, where mlx-Yue peaked at up to
   11.05 GiB of footprint (Draft→Final). The RAM floor, and whether 16 GB works, need a
   run on a smaller Mac before documenting a minimum. The audio.cpp q8_0 fallback
   (6.27–6.28 GiB) is an option (Hybrid 2).
6. **Library cleanup (Architecture: "`.npy` … may be much larger than the FLAC").** It is
   the other way round: intermediates are 2.1–2.3 MiB of a 37.3–40.5 MiB Take. "Clear
   intermediates" saves little. Deleting Drafts and unwanted Takes is what frees space,
   and keeping the `.npy` files so any Take can get a Final is cheap.
7. **Worker cancel and cleanup (Architecture: IPC and kill-after-grace).** Cooperative
   cancel worked in every Stage within 0.129 s with no reload, and the staged API leaves
   no stale resource files. Still open for M1: a kill while a Take is being saved.
8. **Setup screen download (#4).** After `snapshot_download`, delete `converted/.cache`
   and `converted/.gitattributes`, or ignore `.gitattributes` at download.
9. **Progress (#2).** Stage-level progress is confirmed. Measure the per-token or per-step
   callback rate in M1a before building the progress throttle or a % bar within a Stage.
10. **"Re-run with these settings" (#3).** It can promise the same Take on mlx-Yue when
    precision and Synthesis steps are part of the settings. Reproducing across precisions,
    Engine versions or machines was not measured.
