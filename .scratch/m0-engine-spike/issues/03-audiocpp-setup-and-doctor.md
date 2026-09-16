# 03 — audio.cpp setup and doctor

**What to build:** A developer runs a setup command that downloads the pinned audio.cpp `v0.8.0` macOS arm64 Metal release tarball, verifies its sha256 against the GitHub release asset digest (recording it), and unpacks it into the gitignored vendor directory. The same command downloads the YuE2 GGUF files (main `q8_0`, main `bf16`, VAE `f16`, and the required sidecars) from HF `audio-cpp/audio.cpp-gguf` into the gitignored models directory. Then `doctor` works for the audio.cpp Engine: an `AudioCppEngine` implements `run` by driving the CLI as a subprocess with the `clip` case's style, lyrics, planning mode `full`, seed and Synthesis steps, and parses `--log` output into Stage events. Operations the CLI can't do alone (planning-only, semantic generation, synthesis from given Semantic tokens, decode) raise `Unsupported`. Cancel kills the process.

Read first: spec, ledger D-005, D-006, D-007 and the audio.cpp facts at the top of DECISIONS.md; `CONTEXT.md`. audio.cpp's YuE2 docs: `docs/models/yue2.md` in the `0xShug0/audio.cpp` repo at tag `v0.8.0`. Check the HF repo's file listing for the exact YuE2 paths.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The setup command is idempotent (a second run downloads nothing) and fails loudly on a sha256 mismatch
- [ ] `uv run spike doctor --engine audiocpp` produces a playable `clip` audio file and a results JSON with `outcome: ok` and the audio.cpp version
- [ ] A log-parsing test against captured real `--log` output (saved as a test fixture) yields the Stage events and their durations
- [ ] Unsupported operations are recorded as `outcome: unsupported` by the harness, not as crashes
- [ ] `uv run pytest -q` and `uv run ruff check .` pass
