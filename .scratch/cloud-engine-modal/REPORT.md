# cloud-engine-modal — report

`arcsong serve --engine modal` renders on the user's own Modal account, set up from the Setup page.

## Tickets

- 01 — the Modal app (`arcsong/modal_app.py`): 03c9f33
- 02 — `ModalEngine` (`arcsong/modal_engine.py`): f9718dd
- 03 — `--engine modal`, `ModalModels`, Setup wording, the `modal` extra: 2f8364a
- 04 — real end-to-end run, README / CHANGELOG / CLAUDE.md: 60d2052
- QA fixes (below): this report's commit

## Real run (owner's Modal account, 2026-11-11)

Fresh data dir → Set up on Modal (deploy + Volume) → sketch of 2 at 8 steps (56.5 s and 57.6 s of
audio; take 2 in 54 s warm) → Plan a melody (13 s) → Finalize take 1 at 32 steps (16 s, same
length as its Draft) → both takes and the Final play in the Library. Live token progress every
second; Cancel mid-semantic → cancelled, Modal backlog 0. Spend: $0.15.

Found on the way: Modal had no free L4, so take 1 waited ~14 minutes with no runner (fixed with a
GPU fallback list), and `FunctionCall.get(timeout=…)` blocks while a call is pending (fixed: the
result is awaited on a side thread).

## QA verdict (goal mode)

PASS WITH NOTES. No blocking finding; the code backs every ticket. Defects and what was done:

1. Stale deploy marker: Setup stayed Ready after `modal app stop` or an upgrade that changed the
   app. **Fixed**: the marker is named after a hash of `modal_app.py`, so a changed app asks to be
   set up again; the README's removal step says to delete the `modal` folder.
2. No test reached the call loop. **Fixed**: three tests drive `_call` through a stand-in `modal`
   module (event relay including the last one, cancel, remote errors).
3. A failed deploy's reason was a wrapped fragment. **Fixed**: the message is one line.
4. Events put just before the call ended could be dropped. **Fixed**: the loop drains after it
   sees the call end.
5. A cancel made on Modal's side (`InputCancellation`, a BaseException) would kill the worker.
   **Fixed**: it becomes a plain job failure.
6. README cost and speed lines went beyond the notes and named only the L4. **Fixed**: X-001's
   measured figures, the fallback GPUs, and that a stopped server leaves its song running.
7. `load()` docstring claimed an early failure. **Fixed.**
8. Finalizing a Modal Draft on the Mac says "kept no synthesis noise" rather than plain advice.
   **Left**: documented as unsupported; low.

## Decisions made for you

- Modal login is Modal's own (`modal setup`); Arcsong stores no token. (cycle 4, decisions.md)
- Reuse X-001's Volume `arcsong-yue2-weights`; weights and wheel pinned by revision.
- One container, kept 5 minutes; GPU fallbacks L4 → A10G → L40S (L40S costs more).
- Covers stay Mac-only; Mac and Modal Drafts can't finalize across engines.
- Journey 7 (Modal) added to the release journeys, run when Modal code changes.
