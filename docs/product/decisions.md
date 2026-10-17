# Decisions

## 2026-10-17 — cycle 1

- North star: 0 stars (Δ 0 since the 2026-10-17 baseline, same day)
- Picked (chain 3, one release, v0.2.0):
  - metrics-script (1.50: I3 C1 core1 / E1 Cx0 R0 U1) — GitHub keeps traffic 14 days; every run without it loses data.
  - score-zero-notes (1.00: I2 C0.5 core1 / E1 Cx0 R0 U0) — a visible defect on a page a new user opens; one hour.
  - readme-v0-2 (0.83: I5 C0.5 core1 / E2 Cx0 R1 U0, part of v0.2.0-and-announce, approved N-003) — the README shows the old UI; v0.2.0 and the announcement need it.
- Alongside, not a build: X-001 Modal spike (1.33), approved N-002, running in the background.
- Passed over: release-qa-script (0.93) — next cycle; this cycle's release QA is run by hand with the CDP driver. song-metadata, length-estimate (1.00 each, impact 1) — tie on score with score-zero-notes but move nothing a new user sees first.
- Pipeline size: lite for all three (`--lite`) — each is about an hour; the full spec/ticket/agent pipeline would cost more than the work.
- Landing: merge — solo repo, no PR workflow, CI on main.
- Shipped: (pending)
- Release QA: (pending)
- Next: (pending)

## 2026-10-17 — N-003: v0.2.0 and announcement

- Context: charter-mode escalation (public).
- Decision: tag v0.2.0 once the README is redone, then announce in one place first. The PM writes the post; the owner publishes it (it posts as them).
- Why: a star baseline only means something after a single, known announcement.
- Reversibility: costly (public)
- By: owner ("ok")

## 2026-10-17 — N-002: Modal spend for X-001

- Context: charter-mode escalation (money).
- Decision: run X-001 on the owner's existing Modal account, inside its $30 monthly credit; the experiment is capped at $10 of usage. RunPod account registered with the owner's SSH key; creating RunPod machines from scripts will need an API key — asked for when RunPod work is picked.
- Why: owner answer.
- Reversibility: cheap
- By: owner

## 2026-10-17 — N-001: charter confirmed

- Context: charter-mode escalation (charter).
- Decision: `product.md` accepted as drafted, except `ship: auto` (the draft said ask).
- Why: owner answer.
- Reversibility: cheap
- By: owner

## 2026-10-17 — charter drafted

- Context: first `/pm` run (`--plan`, with the owner asking about features, testing, QA, Modal
  and RunPod). No `docs/product/` existed, so this was charter mode.
- Decision: drafted `product.md` from `PLAN.md`, the README, `TARGET.md`, `HANDOFF.md` and the
  public repo numbers; seeded `backlog.md` with 14 scored candidates and experiment X-001;
  `metrics.md` with three `gh api` sources and a baseline snapshot.
- Why: a charter is the only thing the PM can score against; the owner's asks became backlog
  rows rather than a separate plan.
- Reversibility: cheap — every `(inferred)` field waits in `NEEDS-YOU.md`.
- By: PM

Proposed first cycle once the charter is confirmed (not started — `--plan`):

- Pick: metrics-script (1.50), score-zero-notes (1.00), release-qa-script (0.93).
- Then, on approval: X-001 cloud spike (1.33, money), v0.2.0-and-announce (0.83, public).
- Passed over: cloud-engine-modal (0.36) and runpod-serverless (0.30) until X-001 says the cost
  and speed are worth it; ai-lyric-writer (0.17) — no anchor in the charter and heavy upkeep.
