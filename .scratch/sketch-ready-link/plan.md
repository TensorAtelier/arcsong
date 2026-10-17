# sketch-ready-link — plan

**Goal:** after a sketch finishes, Create still offers "Compare" for it (release QA, journey 2:
the link vanished with the last take, leaving the Library as the only way in).
**Not yet:** a toast or sound when a sketch completes.
**Stack / interfaces:** `web/src/QueuePanel.tsx`.
**Proof of done:** while a sketch renders the link reads as before; once every take is done the
Rendering card says nothing is rendering and links "Compare your last sketch (4 takes) →"; a
newer single song doesn't hide it; release-QA journey 2 passes.

## Tickets

- [x] 01 — Keep the latest sketch's Compare link after it finishes; check with release QA J2.

## Notes

- "Latest sketch" = the Variations group with the highest job id.
