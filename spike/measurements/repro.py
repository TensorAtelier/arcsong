"""`repro`: does the same Song request and seed give the same Take again?

Decisions: D-011 (method), D-004 (listening directory), D-015 (failures as outcomes).

The `clip` case runs with its supplied Score removed, so planning writes a Score that
can be compared (`params.score = "planned"`). Two children, one after the other: a warm
process loads the Engine once and renders two Takes; a fresh process loads it again and
renders one. The harness then compares warm Take 1 with warm Take 2 (warm vs warm) and
with the fresh Take (warm vs fresh), Stage by Stage, on the files each Take left:
Score text, Semantic tokens, Latents and audio. Only the Stage outputs an Engine exports
are compared; audio.cpp's CLI exports audio only. An Engine whose Takes each start a new
process that reloads the model (audio.cpp) has no warm process: every run and comparison
records `takes_reuse_loaded_model` / `warm_process`, with a note when it is false. The
first compared Stage whose output differs is the first diverging Stage; any uncompared
Stage before it is listed too, since the divergence may have begun there. One same-seed
audio pair is copied, as FLAC, to the listening directory: warm vs fresh, unless only the
warm pair differs.
"""

from __future__ import annotations

import os
import shutil
import time
from functools import partial
from pathlib import Path

import numpy as np

from spike.engine import STAGES, SpikeEngine

MEASUREMENT = "repro"
CASE = "clip"
STEPS = 32
PRECISIONS = {"mlx": "8bit", "audiocpp": "q8_0", "fake": "8bit"}
SCORE = "planned"
WARM_TAKES = 2
FRESH_TAKES = 1
STAGE_OUTPUTS = dict(zip(STAGES, ("Score", "Semantic tokens", "Latents", "audio"), strict=True))
NOT_EXPORTED = "not exported by the Engine"
COLD_TAKES_NOTE = (
    "the Engine starts a new process for every Take, which loads the model again: "
    "the warm Takes are cold runs from one harness process, so a warm process "
    "(reused model, caches, kernel selection) was not tested"
)


def request_without_score(request: dict) -> dict:
    """The case's Song request with planning left to write the Score."""
    return {key: value for key, value in request.items() if key != "abc"}


def params(precision: str, steps: int) -> dict:
    return {"precision": precision, "steps": steps, "score": SCORE}


def _measure(
    engine: SpikeEngine, request: dict, params: dict, run_dir: Path, *, process: str, takes: int
) -> dict:
    load_start = time.monotonic()
    engine.load(params["precision"])
    load_seconds = time.monotonic() - load_start
    records = []
    for take in range(1, takes + 1):
        take_dir = run_dir / f"take-{take}"
        start = time.monotonic()
        output = engine.run(request, params["steps"], take_dir)
        records.append(
            {
                "take": take,
                "seed": request["seed"],
                "run_seconds": time.monotonic() - start,
                "take_dir": str(take_dir),
                "audio_path": str(output.audio_path),
                "audio_seconds": output.audio_seconds,
                "stage_outputs": {stage: str(path) for stage, path in output.stage_outputs.items()},
            }
        )
    return {
        "process": process,
        "pid": os.getpid(),
        "takes_reuse_loaded_model": engine.info().takes_reuse_loaded_model,
        "load_seconds": load_seconds,
        "takes": records,
    }


warm = partial(_measure, process="warm", takes=WARM_TAKES)
fresh = partial(_measure, process="fresh", takes=FRESH_TAKES)
MEASURES = (warm, fresh)


def compare_score(a: Path, b: Path) -> dict:
    return {"equal": Path(a).read_text() == Path(b).read_text()}


def compare_semantic(a: Path, b: Path) -> dict:
    left, right = np.load(a).ravel(), np.load(b).ravel()
    shared = min(len(left), len(right))
    differing = np.flatnonzero(left[:shared] != right[:shared])
    if len(differing):
        first = int(differing[0])
    elif len(left) != len(right):
        first = shared
    else:
        first = None
    lengths = [len(left), len(right)]
    return {"equal": first is None, "first_differing_index": first, "lengths": lengths}


def compare_latents(a: Path, b: Path) -> dict:
    left, right = np.load(a), np.load(b)
    shapes = [list(left.shape), list(right.shape)]
    if left.shape != right.shape:
        return {"equal": False, "max_abs_difference": None, "shapes": shapes}
    delta = left.astype(np.float64) - right.astype(np.float64)
    difference = float(np.max(np.abs(delta), initial=0))
    return {"equal": difference == 0.0, "max_abs_difference": difference, "shapes": shapes}


def _read_audio(path: Path) -> np.ndarray:
    import soundfile

    samples, _ = soundfile.read(str(path), dtype="float64", always_2d=True)
    return samples


def compare_audio(a: Path, b: Path) -> dict:
    """Bit-identical decoded samples, or else the max-abs difference (full scale = 1.0) and
    the Pearson correlation over the samples both files share."""
    left, right = _read_audio(a), _read_audio(b)
    counts = [len(left), len(right)]
    if left.shape == right.shape and np.array_equal(left, right):
        return {"equal": True, "bit_identical": True, "sample_counts": counts}
    shared = min(len(left), len(right))
    channels = min(left.shape[1], right.shape[1])
    x, y = left[:shared, :channels].ravel(), right[:shared, :channels].ravel()
    difference = float(np.max(np.abs(x - y), initial=0))
    correlation = None
    if x.size and x.std() > 0 and y.std() > 0:
        correlation = float(np.corrcoef(x, y)[0, 1])
    return {
        "equal": False,
        "bit_identical": False,
        "sample_counts": counts,
        "max_abs_difference": difference,
        "correlation": correlation,
    }


_COMPARE = dict(zip(STAGES[:3], (compare_score, compare_semantic, compare_latents), strict=True))


def compare_takes(take: dict, other: dict) -> dict:
    """Stage-by-Stage comparison of two Take records (as `_measure` writes them)."""
    stages: dict[str, dict] = {}
    for stage in STAGES:
        entry: dict = {"output": STAGE_OUTPUTS[stage]}
        if stage == STAGES[3]:
            paths = (take.get("audio_path"), other.get("audio_path"))
            compare = compare_audio
        else:
            paths = (take["stage_outputs"].get(stage), other["stage_outputs"].get(stage))
            compare = _COMPARE[stage]
        if None in paths:
            entry.update(compared=False, reason=NOT_EXPORTED)
        else:
            entry.update(compared=True, **compare(Path(paths[0]), Path(paths[1])))
        stages[stage] = entry

    first, uncompared = "none", []
    for stage, entry in stages.items():
        if not entry["compared"]:
            uncompared.append(stage)
        elif not entry["equal"]:
            first = stage
            break
    return {
        "first_diverging_stage": first,
        "uncompared_stages_before": uncompared if first != "none" else [],
        "stages": stages,
    }


def copy_as_flac(source: Path, target: Path) -> None:
    import soundfile

    info = soundfile.info(str(source))
    subtype = info.subtype if info.subtype in ("PCM_16", "PCM_24") else "PCM_24"
    samples, rate = soundfile.read(str(source), dtype="int32", always_2d=True)
    soundfile.write(str(target), samples, rate, format="FLAC", subtype=subtype)


def summarizer(listen_dir: Path):
    """Compares the Takes of a finished case and copies its listening pair."""

    def summarize(runs: list[dict], stem: str) -> dict:
        by_process = {run["process"]: run["takes"] for run in runs}
        warm_takes, fresh_takes = by_process["warm"], by_process["fresh"]
        pairs = {
            "warm_vs_warm": ((warm_takes[0], "warm-take-1"), (warm_takes[1], "warm-take-2")),
            "warm_vs_fresh": ((warm_takes[0], "warm-take-1"), (fresh_takes[0], "fresh-take-1")),
        }
        warm_process = all(run["takes_reuse_loaded_model"] for run in runs)
        comparisons = {}
        for name, (a, b) in pairs.items():
            comparisons[name] = {"warm_process": warm_process, **compare_takes(a[0], b[0])}
            if not warm_process:
                comparisons[name]["note"] = COLD_TAKES_NOTE

        chosen = "warm_vs_fresh"
        if (
            comparisons[chosen]["stages"][STAGES[3]]["equal"]
            and not comparisons["warm_vs_warm"]["stages"][STAGES[3]]["equal"]
        ):
            chosen = "warm_vs_warm"
        target_dir = listen_dir / stem
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True)
        pair: dict = {"comparison": chosen}
        for key, (take, name) in zip(("first", "second"), pairs[chosen], strict=True):
            target = target_dir / f"{name}.flac"
            copy_as_flac(Path(take["audio_path"]), target)
            pair[key] = str(target)
        return {"comparisons": comparisons, "listening_pair": pair}

    return summarize
