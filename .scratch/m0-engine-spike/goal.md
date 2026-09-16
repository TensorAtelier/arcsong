# m0-engine-spike — goal

**Goal:** Answer the M0 questions in PLAN.md: pick the engine (mlx-Yue vs audio.cpp) and measure stage timing, cancel, seed reproducibility, memory and artifact sizes on this Mac.
**Constraints:** Runs on this machine (MacBook Pro M5 Pro, 64 GB, macOS 26.4.1). Must happen before any UI work (PLAN.md M0). Model weights are CC BY-NC 4.0 — download, never commit.
**Non-goals:** Web server, database, frontend, job queue product code (M1). Covers / transcription (M4). Measuring on NVIDIA (M5) (inferred). Tuning either engine's performance (inferred). Picking a final product name (inferred).
**Taste anchor:** none — taste decisions escalate (none expected: the spike has no UI).
**Proof of done:** A committed M0 report where every M0 checkbox in PLAN.md is answered with numbers taken from committed result files, an engine recommendation with its reasons, and audio pairs the user can listen to (same seed twice; 8-step draft vs 32-step final of the same take).
