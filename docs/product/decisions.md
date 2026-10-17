# Decisions

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
