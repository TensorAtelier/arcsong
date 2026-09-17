"""`draft-final`: can a Draft's Semantic tokens and noise become a Final, and what's saved?

Decisions: D-012 (method), D-004 (listening directory), D-015 (failures as outcomes).

Two children, one after the other. The draft process loads the Engine, renders `song` as
a Draft (8 Synthesis steps) keeping its synthesis noise, then renders the Final from the
Draft's saved Take: its Semantic tokens and noise re-synthesized and decoded at 32 steps
(`render_final`). An Engine that can't take the Semantic tokens back raises `Unsupported`;
that is recorded, and the Final is made by the closest workaround instead: a full re-run
of the Song request with the Draft's seed and saved noise, whose time is the fallback's
cost. The direct process loads the Engine again and renders the same Song request and
seed directly at 32 steps.

The harness then records the Draft, Final and direct-32 times, compares the Final with
direct-32 Stage by Stage (Score, Semantic tokens, Latents, audio: equal, else max-abs
difference and, for audio, correlation), checks what the Final really reused from the
Draft, and copies the Draft and Final audio, as FLAC, to the listening directory. A case
whose Final needed the workaround has the outcome `unsupported`, with every number kept.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from spike.engine import STAGES, RunOutput, SpikeEngine, Unsupported
from spike.measurements.repro import compare_semantic, compare_takes, copy_as_flac

MEASUREMENT = "draft-final"
CASE = "song"
DRAFT_STEPS = 8
FINAL_STEPS = 32
PRECISIONS = {"mlx": "8bit", "audiocpp": "q8_0", "fake": "8bit"}
RESYNTHESIS = "re-synthesis"
FULL_RERUN = "full re-run"


def params(precision: str, draft_steps: int, final_steps: int) -> dict:
    return {"precision": precision, "draft_steps": draft_steps, "final_steps": final_steps}


def _take(output: RunOutput, *, steps: int, seconds: float, take_dir: Path) -> dict:
    return {
        "steps": steps,
        "seconds": seconds,
        "take_dir": str(take_dir),
        "audio_path": str(output.audio_path),
        "audio_seconds": output.audio_seconds,
        "stage_outputs": {stage: str(path) for stage, path in output.stage_outputs.items()},
        "noise_path": str(output.noise_path) if output.noise_path else None,
        # Weights loaded inside this Take (included in `seconds`).
        "lazy_load_seconds": output.lazy_load_seconds,
        "details": output.details,
    }


def _loaded(engine: SpikeEngine, precision: str) -> float:
    start = time.monotonic()
    engine.load(precision)
    return time.monotonic() - start


def draft_then_final(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    load_seconds = _loaded(engine, params["precision"])

    draft_dir = run_dir / "draft"
    start = time.monotonic()
    draft = engine.run(request, params["draft_steps"], draft_dir, keep_noise=True)
    draft_take = _take(
        draft, steps=params["draft_steps"], seconds=time.monotonic() - start, take_dir=draft_dir
    )

    final_dir = run_dir / "final"
    steps = params["final_steps"]
    unsupported = None
    start = time.monotonic()
    try:
        final = engine.render_final(draft_dir, steps, final_dir)
        method, noise_source = RESYNTHESIS, None
    except Unsupported as error:
        unsupported = str(error)
        if final_dir.exists():
            shutil.rmtree(final_dir)
        start = time.monotonic()
        final = engine.run(request, steps, final_dir, noise=draft.noise_path)
        method, noise_source = FULL_RERUN, draft_take["noise_path"]
    final_take = _take(final, steps=steps, seconds=time.monotonic() - start, take_dir=final_dir)
    final_take.update(method=method, noise_source=noise_source)
    if unsupported is not None:
        final_take["render_final_unsupported"] = unsupported
    return {
        "process": "draft",
        "pid": os.getpid(),
        "load_seconds": load_seconds,
        "draft": draft_take,
        "final": final_take,
    }


def direct(engine: SpikeEngine, request: dict, params: dict, run_dir: Path) -> dict:
    load_seconds = _loaded(engine, params["precision"])
    take_dir = run_dir / "direct"
    steps = params["final_steps"]
    start = time.monotonic()
    output = engine.run(request, steps, take_dir)
    return {
        "process": "direct",
        "pid": os.getpid(),
        "load_seconds": load_seconds,
        "direct": _take(output, steps=steps, seconds=time.monotonic() - start, take_dir=take_dir),
    }


MEASURES = (draft_then_final, direct)


def _reused(draft: dict, final: dict) -> dict:
    """What the Final shares with the Draft. Outputs the Final wrote itself are compared
    with the Draft's; a file the Draft's run left and the Final was given is recorded as
    supplied, since comparing it with itself would show nothing."""
    reused: dict = {}
    semantic = STAGES[1]
    if final["method"] == RESYNTHESIS and semantic in draft["stage_outputs"]:
        paths = (draft["stage_outputs"][semantic], final["stage_outputs"].get(semantic))
        if paths[1] is not None:
            reused["Semantic tokens"] = compare_semantic(Path(paths[0]), Path(paths[1]))
    draft_noise, final_noise = draft["noise_path"], final["noise_path"]
    if draft_noise is None or final_noise is None:
        return reused
    if Path(draft_noise) == Path(final_noise):
        reused["synthesis noise"] = {"supplied_from_draft": True, "file": draft_noise}
    else:
        equal = Path(draft_noise).read_bytes() == Path(final_noise).read_bytes()
        reused["synthesis noise"] = {"equal": equal, "files": [draft_noise, final_noise]}
    return reused


NOISE_MISMATCH_NOTE = (
    "the Final was synthesized with the Draft's saved noise file, written by the harness; "
    "direct-32 used the Engine's own noise from the seed, which the Engine does not export "
    "and which differs from that file, so the two differ from synthesis on. This is not a "
    "reproducibility failure: see draft_to_final.fallback.same_seed_rerun"
)
SAME_SEED_NOTE = (
    "direct-32 is itself the same-seed full re-run without a noise file: the D-012 "
    "workaround when seed reproducibility holds. A plain same-seed Draft would share the "
    "Engine's own noise with it and needs no noise probe; its Final costs this run"
)
PROBE_NOTE = (
    "draft_seconds excludes noise_probe_seconds: the probe is harness work to learn the "
    "Semantic token count so the Draft's noise can be supplied as a file, not part of "
    "rendering a Draft; a plain same-seed Draft costs draft_seconds"
)


def summarizer(listen_dir: Path):
    """Compares the Final with direct-32 and copies the Draft/Final listening pair."""

    def summarize(runs: list[dict], stem: str) -> dict:
        by_process = {run["process"]: run for run in runs}
        draft = by_process["draft"]["draft"]
        final = by_process["draft"]["final"]
        direct_take = by_process["direct"]["direct"]

        draft_to_final: dict = {"outcome": "ok", "final_method": final["method"]}
        extra: dict = {}
        if final["method"] == FULL_RERUN:
            reason = final["render_final_unsupported"]
            draft_to_final.update(outcome="unsupported", reason=reason)
            extra = {"outcome": "unsupported", "error": f"Unsupported: {reason}"}
        draft_to_final["reused"] = _reused(draft, final)
        final_vs_direct = compare_takes(final, direct_take)
        if final["method"] == FULL_RERUN:
            draft_to_final["fallback"] = {
                "seconds": final["seconds"],
                "noise": "supplied from the Draft's saved noise file"
                if final.get("noise_source")
                else "the Engine's own noise from the seed",
            }
            if final.get("noise_source") and direct_take["noise_path"] is None:
                draft_to_final["fallback"]["same_seed_rerun"] = {
                    "take": "direct",
                    "seconds": direct_take["seconds"],
                    "note": SAME_SEED_NOTE,
                }
                final_vs_direct["note"] = NOISE_MISMATCH_NOTE

        probe_seconds = draft.get("details", {}).get("noise_probe_seconds")
        timing = {
            "draft_seconds": draft["seconds"] - (probe_seconds or 0.0),
            "final_seconds": final["seconds"],
            "direct_seconds": direct_take["seconds"],
            "final_saving_seconds": direct_take["seconds"] - final["seconds"],
            "final_to_direct_ratio": final["seconds"] / direct_take["seconds"],
        }
        if final["method"] == FULL_RERUN:
            timing["fallback_seconds"] = final["seconds"]
        if probe_seconds is not None:
            timing["noise_probe_seconds"] = probe_seconds
            timing["notes"] = PROBE_NOTE
        # The Final runs in the Draft's process; direct-32 loads the Engine from scratch.
        timing["final_lazy_load_seconds"] = sum(final["lazy_load_seconds"].values())
        timing["direct_model_load_seconds"] = by_process["direct"]["load_seconds"] + sum(
            direct_take["lazy_load_seconds"].values()
        )

        target_dir = listen_dir / stem
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True)
        pair = {}
        for key, take in (("draft", draft), ("final", final)):
            target = target_dir / f"{key}-{take['steps']}.flac"
            copy_as_flac(Path(take["audio_path"]), target)
            pair[key] = str(target)

        return {
            **extra,
            "draft_to_final": draft_to_final,
            "timing": timing,
            "final_vs_direct": final_vs_direct,
            "draft_vs_final": compare_takes(draft, final),
            "listening_pair": pair,
        }

    return summarize

