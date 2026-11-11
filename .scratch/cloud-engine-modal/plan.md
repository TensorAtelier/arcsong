# cloud-engine-modal — plan

**Goal:** render songs on the user's own Modal account: `arcsong serve --engine modal`, set up from the Setup page.
**Not yet:** covers on Modal (SheetSage2 stays Mac-only); RunPod; choosing precision on Modal (yue2 on CUDA is bf16); keeping a warm GPU between sessions.
**Stack / interfaces:** `arcsong/modal_app.py` (the Modal app the user deploys: image with the official yue2 0.1.5 wheel, the X-001 weights Volume, an L4 `Renderer`); `arcsong/modal_engine.py` (the Engine the worker drives, over `modal.Cls.from_name`); `ModalModels` for Setup; optional extra `arcsong[modal]`.
**Proof of done:** on a fresh data dir, `arcsong serve --engine modal` → Setup → Download deploys the app → Create renders a sketch of 2 takes on Modal → Finalize one → both play in the Library; Plan a melody works; the fake-engine suite and release journeys stay green.

## Tickets

- [x] 01 — remote app: `arcsong/modal_app.py` deploys with `modal deploy`; `download` fills the Volume; `Renderer.run(job, queue)` does plan / render / finalize and streams stage events. Check: `modal run` one plan and one 8-step render.
- [x] 02 — engine: `ModalEngine` (render, plan_only, finalize; transcribe refuses) writes the Take directory from the returned files, forwards events, cancels the remote call. Check: unit tests with a fake remote.
- [x] 03 — wiring: `--engine modal`, `ModalModels` (checks: client installed, logged in; Download = deploy + weights), covers part says "Mac engine only", optional extra. Check: Setup page on `--engine modal` in the browser.
- [x] 04 — real run: sketch of 2, Finalize, Plan a melody through the app on Modal; record time and cost. Docs: README section, CHANGELOG, CLAUDE.md.

## Notes

- Auth: Modal's own login (`modal setup`, `~/.modal.toml`); Arcsong stores no token (cycle-4 decision).
- Events go through an ephemeral `modal.Queue`; the result comes back from `FunctionCall.get()`; cancel = `FunctionCall.cancel()`.
- A Take from Modal keeps yue2's own artifacts (plan files, semantic.npy, audio.flac…); Finalize sends the plan files and semantic.npy back. Finalizing a Mac Draft on Modal (or the reverse) is not supported: different precision and noise.
- One GPU container (`max_containers=1`), kept 5 minutes after the last job so a sketch's takes share one model load.
- Real run, 2026-11-11 (owner's Modal account): Setup's deploy + Volume in under a minute (weights already there from X-001); sketch of 2 at 8 steps → 56.5 s and 57.6 s of audio, take 2 in 54 s warm; Plan a melody 13 s; Finalize at 32 steps 16 s (same length as its Draft); live token progress every second; Cancel mid-semantic → cancelled, Modal backlog 0. Take 1 waited ~14 min: no L4 was free, fixed with a GPU fallback list. Spend $0.15.
