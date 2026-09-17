# 08 — Stale resource files and model download checks (mlx-Yue)

**What to build:** Two measurements for mlx-Yue. `hygiene`: start a Take writing to an output directory, kill the process mid-synthesis, rerun to the same output directory, and record whether stale `<output>.resources.json` / `.resources.jsonl` (or any other leftover file) block or corrupt the rerun, whether the staged Python API path creates those files at all, and the minimal cleanup that makes a rerun work. `download`: use `huggingface_hub` `snapshot_download` with `local_dir` into a temporary directory, for the smallest file set that still lets mlx-Yue's conversion/weight verification run (e.g. configs + tokenizer + VAE, or the 8bit AR only). Record which extra files Hugging Face writes (such as `.cache/huggingface/…`), whether verification fails because of them, and a fix that works (e.g. ignore patterns, deleting the metadata directory, or a verify flag). No full 10 GB re-download. Run both on this Mac.

Read first: spec, ledger D-013; `CONTEXT.md`. mlx-Yue source is installed as a dependency (pinned `9253ed1`); the reference clone is `~/projects/mlx-Yue`.

**Blocked by:** 01

**Status:** done

- [x] Results JSON for `hygiene`, with the leftover files after a kill, the rerun outcome with and without cleanup, and the cleanup rule
- [x] Results JSON for `download`, with the file set downloaded, extra metadata files, the verification outcome, and a fix shown working
- [x] The temporary download directory is deleted afterwards
- [x] `uv run pytest -q` and `uv run ruff check .` pass
