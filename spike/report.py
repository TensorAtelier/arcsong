"""`report`: the M0 report's tables, regenerated from the results files (D-019).

The report mixes generated tables with hand-written interpretation. Each table lives
in a block between `<!-- generated:<key> ... -->` and `<!-- /generated:<key> -->`
markers; regenerating replaces only those blocks, so the interpretation around them is
kept and running the command twice gives the same file. A report that does not exist
yet (or lacks a block) gets a skeleton section per M0 question.

Every table cell comes from a results file, and every row or cell names that file. A
question or case without results reads "not measured".
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from spike.engine import STAGES
from spike.measurements import cancel, draft_final, progress, repro, timing

NOT_MEASURED = "not measured"
MISSING = "—"
ENGINES = {"mlx": "mlx-Yue", "audiocpp": "audio.cpp"}
GIB = 2**30
MIB = 2**20
KIB = 2**10

Result = tuple[str, dict[str, Any]]  # (results file name, contents)


class Results:
    """Every results file in a directory, looked up by measurement, engine and params."""

    def __init__(self, results_dir: Path):
        self.items: list[Result] = []
        if results_dir.is_dir():
            for path in sorted(results_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text())
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and "measurement" in data:
                    self.items.append((path.name, data))

    def of(self, measurement: str, engine: str | None = None, **params: Any) -> list[Result]:
        return [
            (name, data)
            for name, data in self.items
            if data.get("measurement") == measurement
            and (engine is None or data.get("engine") == engine)
            and all((data.get("params") or {}).get(k) == v for k, v in params.items())
        ]

    def first(self, measurement: str, engine: str | None = None, **params: Any) -> Result | None:
        found = self.of(measurement, engine, **params)
        return found[0] if found else None

    def engines(self, measurement: str | None = None) -> list[str]:
        found = {d.get("engine") for _, d in self.items if measurement in (None, d["measurement"])}
        return [*ENGINES, *sorted(e for e in found if e not in ENGINES and e)]


# ---------------------------------------------------------------- formatting helpers


def cite(name: str) -> str:
    return f"`{name}`"


def seconds(value: float | None, digits: int = 1) -> str:
    return MISSING if value is None else f"{value:.{digits}f}"


def gib(value: int | None) -> str:
    return MISSING if value is None else f"{value / GIB:.2f}"


def mib(value: int | None) -> str:
    return MISSING if value is None else f"{value / MIB:.1f}"


def label(engine: str) -> str:
    return ENGINES.get(engine, engine)


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def ok_runs(data: dict) -> list[dict]:
    """Runs that succeeded; ticket 01's older doctor shape has no per-run outcome."""
    runs = data.get("runs") or []
    return [run for run in runs if run.get("outcome", data.get("outcome")) == "ok"]


def short_error(data: dict | None) -> str:
    text = ((data or {}).get("error") or "").strip()
    if not text:
        return ""
    last = text.splitlines()[-1]
    return re.sub(r"(?:/[^/\s:'\"]+)+/", "…/", last).replace("|", "\\|")


def outcome_cell(data: dict) -> str:
    error = short_error(data)
    return f"{data.get('outcome')}: {error}" if error else str(data.get("outcome"))


def not_measured_row(prefix: list[str], width: int) -> list[str]:
    return [*prefix, NOT_MEASURED, *[MISSING] * (width - len(prefix) - 1)]


def per_audio_second(run: dict) -> float | None:
    total, audio = run.get("total_seconds"), run.get("audio_seconds")
    return total / audio if total and audio else None


# ---------------------------------------------------------------- M0 questions


def engine_choice(results: Results) -> str:
    engines = [e for e in results.engines() if e in ENGINES or results.of("doctor", e)]

    def doctor(engine):
        found = results.first("doctor", engine)
        if not found:
            return None
        name, data = found
        info = (data.get("env") or {}).get("engine") or {}
        commit = (info.get("commit") or "")[:7]
        return f"{outcome_cell(data)}, {info.get('name')} {info.get('version')} @ {commit}", name

    def slowest_cancel(engine):
        runs = [(name, run) for name, data in results.of("cancel", engine) for run in ok_runs(data)]
        runs = [(n, r) for n, r in runs if r.get("cancel_latency_seconds") is not None]
        if not runs:
            return None
        name, run = max(runs, key=lambda item: item[1]["cancel_latency_seconds"])
        how = "process kill" if "kill_to_exit_seconds" in run else "in-process"
        text = (
            f"{run['cancel_latency_seconds']:.3f} s, slowest of {len(runs)} Stages "
            f"({run.get('stage')}; {how})"
        )
        return text, name

    def reuse_after_cancel(engine):
        found = results.of("cancel", engine)
        runs = [run for _, data in found for run in ok_runs(data)]
        if not runs:
            return None
        ok = sum((run.get("reuse") or {}).get("outcome") == "ok" for run in runs)
        reloaded = sum(bool((run.get("reuse") or {}).get("reloaded")) for run in runs)
        return (
            f"next Take ok after {ok} of {len(runs)} cancels; harness reloads: {reloaded}",
            f"cancel-{engine}-*.json",
        )

    def warm_process(engine):
        found = results.first("repro", engine)
        if not found:
            return None
        name, data = found
        warm = [run for run in data.get("runs") or [] if run.get("process") == "warm"]
        if not warm or "takes_reuse_loaded_model" not in warm[0]:
            return None
        reuses = warm[0]["takes_reuse_loaded_model"]
        text = "yes" if reuses else "no: every Take is a new process that loads the model"
        return text, name

    def stages_seen(engine):
        runs = [run for _, data in results.of("cancel", engine) for run in ok_runs(data)]
        if not runs:
            return None
        seen = sum(run.get("stage_at_request") == run.get("stage") for run in runs)
        return f"{seen} of {len(runs)} Stages", f"cancel-{engine}-*.json"

    def score_exported(engine):
        found = results.first("repro", engine)
        if not found:
            return None
        name, data = found
        stage = (((data.get("comparisons") or {}).get("warm_vs_fresh") or {}).get("stages") or {})
        planning = stage.get(STAGES[0])
        if planning is None:
            return None
        text = "yes" if planning.get("compared") else f"no ({planning.get('reason')})"
        return text, name

    def resynthesis(engine):
        found = results.first("draft-final", engine)
        if not found:
            return None
        name, data = found
        summary = data.get("draft_to_final") or {}
        if not summary:
            return outcome_cell(data), name
        return f"{summary.get('outcome')} (Final by {summary.get('final_method')})", name

    def same_seed(engine):
        found = results.first("repro", engine)
        if not found:
            return None
        name, data = found
        comparison = (data.get("comparisons") or {}).get("warm_vs_fresh") or {}
        audio = (comparison.get("stages") or {}).get(STAGES[3])
        if audio is None:
            return outcome_cell(data), name
        return ("yes" if audio.get("bit_identical") else "no"), name

    def fastest(steps):
        def cell(engine):
            candidates = [
                (per_audio_second(run), data["params"].get("precision"), run.get("run"), name)
                for name, data in results.of("timing", engine, steps=steps)
                for run in ok_runs(data)
                if per_audio_second(run)
            ]
            if not candidates:
                return None
            value, precision, run, name = min(candidates)
            return f"{value:.2f} ({precision}, run {run})", name

        return cell

    def lowest_peak(engine):
        candidates = [
            (run["lifetime_peak_footprint_bytes"], data["params"].get("precision"), name)
            for name, data in results.of("timing", engine)
            for run in ok_runs(data)
            if run.get("lifetime_peak_footprint_bytes")
        ]
        if not candidates:
            return None
        value, precision, name = min(candidates)
        return f"{gib(value)} ({precision})", name

    rows_spec: list[tuple[str, Callable[[str], tuple[str, str] | None]]] = [
        ("Doctor: `clip` Take renders", doctor),
        ("Cancel returns control (s)", slowest_cancel),
        ("After a cancel", reuse_after_cancel),
        ("Takes reuse the loaded model", warm_process),
        ("Stage start seen live when cancel was requested", stages_seen),
        ("Score exported (planning usable alone)", score_exported),
        ("Draft→Final from saved Semantic tokens", resynthesis),
        ("Same seed, fresh process → bit-identical audio", same_seed),
        ("Fastest `song` Take at 8 steps (s per audio second)", fastest(8)),
        ("Fastest `song` Take at 32 steps (s per audio second)", fastest(32)),
        ("Lowest `song` peak footprint, lifetime (GiB)", lowest_peak),
    ]
    rows = []
    for title, cell in rows_spec:
        row = [title]
        for engine in engines:
            found = cell(engine)
            row.append(NOT_MEASURED if found is None else f"{found[0]} — {cite(found[1])}")
        rows.append(row)
    return table(["Criterion", *(label(e) for e in engines)], rows)


def stage_timing(results: Results) -> str:
    headers = ["Engine", "Precision", "Steps", "Run", *(f"{s} s (%)" for s in STAGES), "Source"]
    rows = []
    for engine, precision, steps, found in timing_cases(results):
        prefix = [label(engine), precision, str(steps)]
        if found is None:
            rows.append(not_measured_row([*prefix, MISSING], len(headers)))
            continue
        name, data = found
        runs = ok_runs(data)
        if not runs:
            rows.append([*prefix, MISSING, outcome_cell(data), *[MISSING] * 3, cite(name)])
        for run in runs:
            split = run.get("stage_seconds") or {}
            total = sum(split.get(stage) or 0 for stage in STAGES)
            cells = [
                f"{split[s]:.1f} ({100 * split[s] / total:.0f}%)" if split.get(s) is not None
                and total else MISSING
                for s in STAGES
            ]
            rows.append([*prefix, str(run.get("run", 1)), *cells, cite(name)])
    return table(headers, rows)


def timing_cases(results: Results):
    for engine in ENGINES:
        for precision in timing.PRECISIONS[engine]:
            for steps in timing.STEPS:
                yield engine, precision, steps, results.first(
                    timing.MEASUREMENT, engine, precision=precision, steps=steps
                )


def reproducibility(results: Results) -> str:
    headers = [
        "Engine", "Precision", "Steps", "Pair", "Warm Takes shared a loaded model",
        "Score", "Semantic tokens", "Latents", "Audio", "Source",
    ]  # fmt: skip
    rows = []
    for engine in ENGINES:
        found = results.first(repro.MEASUREMENT, engine)
        if found is None:
            rows.append(not_measured_row([label(engine), MISSING, MISSING], len(headers)))
            continue
        name, data = found
        params = data.get("params") or {}
        prefix = [label(engine), str(params.get("precision")), str(params.get("steps"))]
        comparisons = data.get("comparisons") or {}
        if not comparisons:
            rows.append([*prefix, MISSING, outcome_cell(data), *[MISSING] * 4, cite(name)])
        for pair, comparison in comparisons.items():
            stages = comparison.get("stages") or {}
            rows.append(
                [
                    *prefix,
                    pair.replace("_", " "),
                    "yes" if comparison.get("warm_process") else "no",
                    *(stage_comparison(stages.get(stage)) for stage in STAGES),
                    cite(name),
                ]
            )
    return table(headers, rows)


def stage_comparison(stage: dict | None) -> str:
    if not stage:
        return MISSING
    if not stage.get("compared"):
        return str(stage.get("reason", "not compared"))
    if "bit_identical" in stage:
        if stage["bit_identical"]:
            return "bit-identical"
        return (
            f"differs (max abs {stage.get('max_abs_difference'):.3f}, "
            f"correlation {stage.get('correlation'):.3f})"
        )
    if stage.get("equal"):
        if "max_abs_difference" in stage:
            return f"identical (max abs {stage['max_abs_difference']})"
        return "identical"
    if "max_abs_difference" in stage:
        return f"differs (max abs {stage['max_abs_difference']:.3f})"
    if stage.get("first_differing_index") is not None:
        return f"differs from index {stage['first_differing_index']}"
    return "differs"


def artifact_sizes(results: Results) -> str:
    headers = [
        "Engine", "Precision", "Steps", "Audio (s)", "Audio file (MiB)",
        "`.npy` intermediates (MiB)", "Other files (KiB)", "All files (MiB)", "Source",
    ]  # fmt: skip
    rows = []
    per_file: dict[str, list[tuple[str, dict[str, int]]]] = {}
    for engine, precision, steps, found in timing_cases(results):
        prefix = [label(engine), precision, str(steps)]
        runs = ok_runs(found[1]) if found else []
        if not runs:
            row = not_measured_row(prefix, len(headers))
            if found:
                row[3], row[-1] = outcome_cell(found[1]), cite(found[0])
            rows.append(row)
            continue
        name, run = found[0], runs[0]
        files = {f["path"]: f["bytes"] for f in run.get("files") or []}
        audio = Path(run.get("audio_path") or "").name
        npy = sum(b for p, b in files.items() if p.endswith(".npy"))
        other = sum(b for p, b in files.items() if p != audio and not p.endswith(".npy"))
        rows.append(
            [
                *prefix,
                seconds(run.get("audio_seconds")),
                f"{mib(files.get(audio))} ({audio})",
                mib(npy) if npy else "none",
                f"{other / KIB:.1f}",
                mib(sum(files.values())),
                f"{cite(name)} run {run.get('run', 1)}",
            ]
        )
        per_file.setdefault(engine, []).append((f"{precision}/{steps} ({cite(name)})", files))

    parts = [table(headers, rows)]
    for engine, cases in per_file.items():
        names = sorted({path for _, files in cases for path in files})
        parts.append(f"Every file a `song` Take wrote, {label(engine)}, run 1 (bytes):")
        parts.append(
            table(
                ["File", *(case for case, _ in cases)],
                ([path, *(str(files.get(path, MISSING)) for _, files in cases)] for path in names),
            )
        )
    return "\n\n".join(parts)


def stage_progress(results: Results) -> str:
    headers = ["Engine", "Stage", "Stage start seen (s into the Take)", "Cancel landed in it",
               "Source"]  # fmt: skip
    rows = []
    for engine in ENGINES:
        for stage in cancel.STAGE_CASES:
            found = results.first(cancel.MEASUREMENT, engine, stage=stage)
            runs = ok_runs(found[1]) if found else []
            if not runs:
                row = not_measured_row([label(engine), stage], len(headers))
                if found:
                    row[2], row[-1] = outcome_cell(found[1]), cite(found[0])
                rows.append(row)
                continue
            run = runs[0]
            rows.append(
                [
                    label(engine),
                    stage,
                    seconds(run.get("stage_entered_seconds"), 3),
                    "yes" if run.get("stage_at_request") == stage else "no",
                    cite(found[0]),
                ]
            )
    return table(headers, rows)


PERCENT_BAR = {
    "percent": "yes: % from a known total",
    "uneven_percent": "stepped: % from a known total, not tracking wall time",
    "count_only": "running count only (tracks wall time)",
    "uneven_count": "no: running count, not tracking wall time",
    "none": "none: fewer than 2 signals",
    "not_run": "Stage not run",
}


def gaps(stats: dict) -> str:
    found = stats.get("inter_arrival_seconds")
    if not found:
        return MISSING
    return " / ".join(f"{found[key]:.3f}" for key in ("min", "median", "max"))


def total_cell(stats: dict) -> str:
    if stats.get("running_count_only"):
        return "running count"
    if stats.get("total_known_up_front"):
        return f"up front ({stats.get('total')})"
    return f"from signal {stats.get('total_known_from_signal')} ({stats.get('total')})"


def tracking(stats: dict) -> str:
    fit = stats.get("tracks_wall_time") or {}
    if fit.get("max_deviation") is None:
        return MISSING
    return f"{fit['max_deviation']:.2f} ({'linear' if fit.get('linear') else 'not linear'})"


def progress_within_stage(results: Results) -> str:
    headers = [
        "Engine", "Stage", "Stage (s)", "Signal", "Count", "Gap min / median / max (s)",
        "First / last gap to Stage edge (s)", "Mean per s", "Most in 1 s", "Total",
        "Max deviation from wall time", "% bar (Stage verdict)", "Source",
    ]  # fmt: skip
    rows = []
    rates = []
    for engine in ENGINES:
        found = results.first(progress.MEASUREMENT, engine, precision=progress.PRECISIONS[engine])
        runs = ok_runs(found[1]) if found else []
        if not runs:
            row = not_measured_row([label(engine), MISSING], len(headers))
            if found:
                row[2], row[-1] = outcome_cell(found[1]), cite(found[0])
            rows.append(row)
            continue
        name, data = found
        run = runs[0]
        params = data.get("params") or {}
        source = f"{cite(name)} ({params.get('precision')}, {params.get('steps')} steps)"
        busiest = None
        for stage, entry in (run.get("stages") or {}).items():
            bar = entry.get("percent_bar") or {}
            signals = entry.get("signals") or {}
            prefix = [label(engine), stage, seconds(entry.get("seconds"))]
            if not signals:
                verdict = PERCENT_BAR.get(bar.get("verdict"), str(bar.get("verdict")))
                rows.append([*prefix, "nothing fired", "0", *[MISSING] * 6, verdict, source])
            for signal, stats in signals.items():
                rate = stats.get("per_second") or {}
                chosen = bar.get("signal") == signal
                verdict = PERCENT_BAR.get(bar.get("verdict"), MISSING) if chosen else MISSING
                edges = (
                    f"{seconds(stats.get('first_after_start_seconds'))} / "
                    f"{seconds(stats.get('last_before_end_seconds'))}"
                )
                rows.append(
                    [
                        *prefix,
                        f"`{signal}`",
                        str(stats.get("count")),
                        gaps(stats),
                        edges,
                        seconds(rate.get("mean"), 2),
                        str(rate.get("max_in_one_second")),
                        total_cell(stats),
                        tracking(stats),
                        verdict,
                        source,
                    ]
                )
                most = rate.get("max_in_one_second") or 0
                if busiest is None or most > busiest[0]:
                    busiest = (most, signal, stage)
        if busiest:
            events, run_seconds = run.get("progress_events"), run.get("run_seconds")
            mean = events / run_seconds if events is not None and run_seconds else None
            tty = run.get("stderr_is_tty")
            rates.append(
                [
                    label(engine),
                    f"{busiest[0]} (`{busiest[1]}`, {busiest[2]})",
                    str(events) if events is not None else MISSING,
                    seconds(mean, 2),
                    MISSING if tty is None else ("yes" if tty else "no"),
                    cite(name),
                ]
            )
    parts = [table(headers, rows)]
    if rates:
        parts.append("Event rate a progress stream must handle, whole Take:")
        parts.append(
            table(
                [
                    "Engine", "Most signals in 1 s", "Progress events", "Mean per s",
                    "stderr a terminal", "Source",
                ],  # fmt: skip
                rates,
            )
        )
    return "\n\n".join(parts)


def cancellation(results: Results) -> str:
    headers = [
        "Engine", "Stage", "Case", "Cancel after (s)", "Latency (s)", "How", "Kill→exit (s)",
        "Left on disk", "Looks like a Take", "Next Take", "Next Take (s)", "Source",
    ]  # fmt: skip
    rows = []
    for engine in ENGINES:
        for stage in cancel.STAGE_CASES:
            found = results.first(cancel.MEASUREMENT, engine, stage=stage)
            runs = ok_runs(found[1]) if found else []
            if not runs:
                row = not_measured_row([label(engine), stage], len(headers))
                if found:
                    row[2], row[-1] = outcome_cell(found[1]), cite(found[0])
                rows.append(row)
                continue
            name, data = found
            run = runs[0]
            killed = "kill_to_exit_seconds" in run
            left = [f"{f['path']} ({f['bytes']} B)" for f in run.get("leftover_files") or []]
            reuse = run.get("reuse") or {}
            rows.append(
                [
                    label(engine),
                    stage,
                    data.get("case"),
                    seconds(run.get("cancel_after_seconds")),
                    seconds(run.get("cancel_latency_seconds"), 3),
                    "process kill" if killed else f"in-process ({run.get('cancelled_by')})",
                    seconds(run.get("kill_to_exit_seconds"), 3) if killed else MISSING,
                    ", ".join(left) or "nothing",
                    "yes" if run.get("leftover_looks_complete") else "no",
                    f"{reuse.get('outcome')}, harness reload: "
                    f"{'yes' if reuse.get('reloaded') else 'no'}",
                    seconds(reuse.get("run_seconds")),
                    cite(name),
                ]
            )
    return table(headers, rows)


def draft_to_final(results: Results) -> str:
    found = {engine: results.first(draft_final.MEASUREMENT, engine) for engine in ENGINES}

    def row(title: str, cell: Callable[[dict], str]) -> list[str]:
        cells = []
        for engine in ENGINES:
            if found[engine] is None:
                cells.append(NOT_MEASURED)
                continue
            try:
                cells.append(cell(found[engine][1]))
            except (KeyError, TypeError, AttributeError):
                cells.append(MISSING)
        return [title, *cells]

    def timing_of(key: str, digits: int = 1) -> Callable[[dict], str]:
        return lambda data: seconds((data.get("timing") or {}).get(key), digits)

    def reused(data: dict) -> str:
        tokens = (data["draft_to_final"].get("reused") or {}).get("Semantic tokens")
        if tokens is None:
            return f"no — {data['draft_to_final'].get('reason')}"
        count = (tokens.get("lengths") or [MISSING])[0]
        return f"{'identical' if tokens.get('equal') else 'differ'} ({count} tokens)"

    def noise(data: dict) -> str:
        entry = (data["draft_to_final"].get("reused") or {}).get("synthesis noise") or {}
        if "equal" in entry:
            return "identical" if entry["equal"] else "differs"
        return "supplied from the Draft's noise file" if entry.get("supplied_from_draft") else "no"

    def compared(key: str) -> Callable[[dict], str]:
        def cell(data: dict) -> str:
            comparison = data[key]
            audio = (comparison.get("stages") or {}).get(STAGES[3])
            return (
                f"first differs at: {comparison.get('first_diverging_stage')}; audio "
                f"{stage_comparison(audio)}"
            )

        return cell

    def draft_plus_final(data: dict) -> str:
        t = data["timing"]
        return seconds(t["draft_seconds"] + t["final_seconds"])

    def peaks(data: dict) -> str:
        return ", ".join(
            f"{run.get('process')} {gib(run.get('lifetime_peak_footprint_bytes'))}"
            for run in data.get("runs") or []
        )

    def same_seed(data: dict) -> str:
        fallback = (data["draft_to_final"].get("fallback") or {}).get("same_seed_rerun")
        return seconds(fallback["seconds"]) if fallback else MISSING

    rows = [
        row("Outcome", lambda d: f"{d.get('outcome')} (Final by "
            f"{(d.get('draft_to_final') or {}).get('final_method', MISSING)})"),
        row("Precision, steps", lambda d: f"{d['params']['precision']}, "
            f"{d['params']['draft_steps']}→{d['params']['final_steps']}"),
        row("Draft render (s)", timing_of("draft_seconds")),
        row("Harness noise probe, not in the Draft (s)", timing_of("noise_probe_seconds")),
        row("Final render (s)", timing_of("final_seconds")),
        row("Direct 32-step render (s)", timing_of("direct_seconds")),
        row("Final ÷ direct", timing_of("final_to_direct_ratio", 3)),
        row("Draft + Final (s)", draft_plus_final),
        row("Same-seed full re-run (s)", same_seed),
        row("Semantic tokens reused", reused),
        row("Synthesis noise reused", noise),
        row("Final vs direct 32-step", compared("final_vs_direct")),
        row("Draft vs Final", compared("draft_vs_final")),
        row("Peak footprint, lifetime (GiB), per process", peaks),
        row("Source", lambda d: MISSING),
    ]
    rows[-1] = ["Source", *(cite(f[0]) if f else NOT_MEASURED for f in found.values())]
    return table(["", *(label(e) for e in ENGINES)], rows)


def timing_memory(results: Results) -> str:
    headers = [
        "Engine", "Precision", "Steps", "Run", "Model load (s)", "Total (s)", "Audio (s)",
        "s per audio s", "Peak footprint, lifetime (GiB)", "Peak footprint, 250 ms samples (GiB)",
        "MLX peak (GiB)", "Source",
    ]  # fmt: skip
    rows = []
    conditions = []
    for engine, precision, steps, found in timing_cases(results):
        prefix = [label(engine), precision, str(steps)]
        if found is None:
            rows.append(not_measured_row([*prefix, MISSING], len(headers)))
            continue
        name, data = found
        conditions.append(condition_row(name, data))
        runs = ok_runs(data)
        if not runs:
            rows.append([*prefix, MISSING, outcome_cell(data), *[MISSING] * 6, cite(name)])
        for run in runs:
            rows.append(
                [
                    *prefix,
                    str(run.get("run", 1)),
                    seconds(run.get("model_load_seconds")),
                    seconds(run.get("total_seconds")),
                    seconds(run.get("audio_seconds")),
                    seconds(per_audio_second(run), 2),
                    gib(run.get("lifetime_peak_footprint_bytes")),
                    gib(run.get("peak_footprint_bytes")),
                    gib(run.get("engine_peak_memory_bytes")),
                    cite(name),
                ]
            )
    parts = [table(headers, rows)]
    if conditions:
        parts.append("Conditions recorded with each timing case:")
        parts.append(
            table(
                ["Source", "Started (UTC)", "Ended (UTC)", "Other model servers",
                 "ComfyUI RSS (MiB)", "LM Studio RSS (MiB)"],  # fmt: skip
                conditions,
            )
        )
    return "\n\n".join(parts)


def condition_row(name: str, data: dict) -> list[str]:
    started = data.get("started_at")
    start = end = MISSING
    if started:
        moment = datetime.fromisoformat(started)
        start = moment.strftime("%Y-%m-%d %H:%M")
        end = (moment + timedelta(seconds=data.get("total_seconds") or 0)).strftime("%H:%M")
    servers = (data.get("env") or {}).get("model_servers") or []
    rss: dict[str, int] = {}
    for server in servers:
        rss[server["server"]] = rss.get(server["server"], 0) + (server.get("rss_bytes") or 0)
    return [
        cite(name),
        start,
        end,
        ", ".join(sorted(rss)) or "none",
        f"{rss['ComfyUI'] / MIB:.0f}" if "ComfyUI" in rss else MISSING,
        f"{rss['LM Studio'] / MIB:.0f}" if "LM Studio" in rss else MISSING,
    ]


HYGIENE_PATHS = {"api": "staged API", "cli": "Engine command line"}


def stale_resource_files(results: Results) -> str:
    headers = [
        "Engine", "Path", "Killed in", "After Stage start (s)", "Resource files left",
        "Rerun, no cleanup", "Cleanup rule", "Rerun after cleanup", "Source",
    ]  # fmt: skip
    rows = []
    for engine in ("mlx",):
        found = results.first("hygiene", engine)
        runs = ok_runs(found[1]) if found else []
        if not runs:
            row = not_measured_row([label(engine), MISSING], len(headers))
            if found:
                row[2], row[-1] = outcome_cell(found[1]), cite(found[0])
            rows.append(row)
            continue
        run = runs[0]
        for key, path in HYGIENE_PATHS.items():
            entry = run.get(key)
            if not entry:
                rows.append(not_measured_row([label(engine), path], len(headers)))
                continue
            again = entry.get("rerun_without_cleanup") or {}
            after = entry.get("reruns_after_cleanup") or []
            rows.append(
                [
                    label(engine),
                    path,
                    str(entry.get("killed_in")),
                    seconds(entry.get("killed_after_stage_start_seconds"), 2),
                    ", ".join(entry.get("resource_files_left") or []) or "none",
                    outcome_cell(again) if again else MISSING,
                    str(entry.get("cleanup_rule")),
                    ", ".join(str(r.get("outcome")) for r in after) or "not needed",
                    cite(found[0]),
                ]
            )
    return table(headers, rows)


def unexpected_count(verification: dict) -> str:
    outcome = str(verification.get("outcome"))
    match = re.search(r"unexpected=\[(.*?)\]", verification.get("error") or "")
    if not match:
        return outcome
    names = re.findall(r"'([^']*)'", match.group(1))
    shown = names[0] if len(names) == 1 else f"{len(names)} files"
    return f"{outcome} (unexpected in the converted directory: {shown})"


def model_download(results: Results) -> str:
    found = results.first("download", "mlx")
    runs = ok_runs(found[1]) if found else []
    if not runs:
        status = outcome_cell(found[1]) + " — " + cite(found[0]) if found else NOT_MEASURED
        return table(["", label("mlx")], [["Download check", status]])
    name, data = found
    run = runs[0]
    sizes = {f["path"]: f["bytes"] for f in run.get("files") or []}
    downloaded = run.get("downloaded") or []
    metadata = run.get("metadata_files") or []
    again = run.get("after_redownload") or {}

    def fixes(steps: list[dict]) -> str:
        return "; ".join(
            f"remove {', '.join(step.get('removed') or [])} → "
            f"{unexpected_count(step.get('verification') or {})}"
            for step in steps
        )

    def by_directory(paths: list[str]) -> str:
        counts: dict[str, int] = {}
        for path in paths:
            top = path.split("/", 1)[0]
            counts[top] = counts.get(top, 0) + 1
        return ", ".join(f"{top}/ {count}" for top, count in counts.items())

    sources = "; ".join(
        f"{s.get('repository')} @ {str(s.get('revision'))[:7]} → {s.get('local_dir')}/"
        for s in run.get("sources") or []
    )
    fix = data.get("fix") or {}
    rows = [
        ["Sources", sources],
        ["Download time (s)", seconds(run.get("download_seconds"))],
        [
            "Files fetched",
            f"{len(downloaded)} files, {mib(sum(sizes.get(p, 0) for p in downloaded))} MiB",
        ],
        ["Large weights cloned locally, not fetched", ", ".join(
            f"{s['path']} ({mib(sizes.get(s['path']))} MiB)"
            for s in run.get("supplied_locally") or []
        ) or "none"],  # fmt: skip
        ["Metadata files the hub added", f"{len(metadata)} ({by_directory(metadata)})"],
        ["Verification as downloaded", unexpected_count(run.get("verification") or {})],
        ["Fix steps", fixes(run.get("fixes") or [])],
        [
            "`snapshot_download` again over the same directory",
            f"{seconds(again.get('download_seconds'))} s; {len(again.get('metadata_files') or [])}"
            f" metadata files; {unexpected_count(again.get('verification') or {})}; "
            f"then {fixes(again.get('fixes') or [])}",
        ],
        ["Fix that works", f"{'yes' if fix.get('works') else 'no'}: remove "
         f"{', '.join(fix.get('removed') or [])}"],  # fmt: skip
        ["Temporary directory deleted", "yes" if run.get("temp_dir_deleted") else "no"],
        ["Source", cite(name)],
    ]
    return table(["", label("mlx")], rows)


def sources(results: Results) -> str:
    if not results.items:
        return f"Results files: none ({NOT_MEASURED})."
    rows = []
    machines = set()
    for name, data in results.items:
        env = data.get("env") or {}
        machine = env.get("machine") or {}
        if machine:
            os_info = env.get("os") or {}
            machines.add(
                f"{machine.get('cpu')} ({machine.get('model')}), "
                f"{machine.get('memory_bytes', 0) / GIB:.0f} GiB, macOS {os_info.get('macos')}"
            )
        params = ", ".join(f"{k}={v}" for k, v in (data.get("params") or {}).items())
        rows.append(
            [
                cite(name),
                str(data.get("measurement")),
                label(str(data.get("engine"))),
                str(data.get("case")),
                params or MISSING,
                str(data.get("outcome")),
                str(data.get("started_at", MISSING))[:19].replace("T", " "),
            ]
        )
    header = "Machine: " + "; ".join(sorted(machines)) if machines else ""
    body = table(
        ["Results file", "Measurement", "Engine", "Case", "Params", "Outcome", "Started (UTC)"],
        rows,
    )
    return f"{header}\n\n{body}" if header else body


def listening_pairs(results: Results) -> str:
    rows = []
    for measurement in (repro.MEASUREMENT, draft_final.MEASUREMENT):
        for name, data in results.of(measurement):
            pair = data.get("listening_pair")
            if not pair:
                continue
            kinds = [k for k in pair if k != "comparison"]
            paths = [pair[k] for k in kinds]
            rows.append(
                [
                    measurement,
                    label(str(data.get("engine"))),
                    str(pair.get("comparison", " vs ".join(kinds))).replace("_", " "),
                    "<br>".join(f"`{p}`" for p in paths),
                    cite(name),
                ]
            )
    if not rows:
        return f"Listening pairs: {NOT_MEASURED}."
    return table(["Measurement", "Engine", "Pair", "Files", "Source"], rows)


QUESTIONS: list[tuple[str, str]] = [
    ("engine-choice", "Engine choice"),
    ("stage-timing", "Per-Stage timing split"),
    ("reproducibility", "Seed reproducibility"),
    ("artifact-sizes", "Artifact sizes"),
    ("progress", "Per-Stage progress"),
    ("progress-within-stage", "Progress within a Stage"),
    ("cancellation", "Cancellation"),
    ("draft-final", "Draft→Final"),
    ("timing-memory", "Timing and peak memory"),
    ("stale-resource-files", "Stale resource files"),
    ("model-download", "Model download"),
]

RENDERERS: dict[str, Callable[[Results], str]] = {
    "sources": sources,
    "engine-choice": engine_choice,
    "stage-timing": stage_timing,
    "reproducibility": reproducibility,
    "artifact-sizes": artifact_sizes,
    "progress": stage_progress,
    "progress-within-stage": progress_within_stage,
    "cancellation": cancellation,
    "draft-final": draft_to_final,
    "timing-memory": timing_memory,
    "stale-resource-files": stale_resource_files,
    "model-download": model_download,
    "listening-pairs": listening_pairs,
}

_BLOCK = re.compile(
    r"<!-- generated:(?P<key>[\w-]+)[^>]*-->\n.*?<!-- /generated:(?P=key) -->", re.S
)
PLACEHOLDER = "_Interpretation: not written yet._"


def block(key: str, body: str) -> str:
    return (
        f"<!-- generated:{key} (tables from the results files; `uv run spike report` "
        f"rewrites this block) -->\n{body.strip()}\n<!-- /generated:{key} -->"
    )


def skeleton() -> str:
    parts = [
        "# M0 report — Engine spike",
        "## Results files",
        "<!-- slot:sources -->",
        "## Engine recommendation",
        PLACEHOLDER,
    ]
    for key, title in QUESTIONS:
        parts += [f"## {title}", f"<!-- slot:{key} -->", PLACEHOLDER]
    parts += [
        "## Listening pairs",
        "<!-- slot:listening-pairs -->",
        PLACEHOLDER,
        "## Findings that affect the plan",
        PLACEHOLDER,
    ]
    text = "\n\n".join(parts) + "\n"
    return re.sub(r"<!-- slot:([\w-]+) -->", lambda m: block(m.group(1), ""), text)


def render(results_dir: Path, existing: str | None = None) -> str:
    """The report with every generated block rewritten from `results_dir`."""
    results = Results(results_dir)
    text = existing if existing is not None else skeleton()
    present = {m.group("key") for m in _BLOCK.finditer(text)}
    for key, title in QUESTIONS:
        if key not in present:
            text = text.rstrip("\n") + f"\n\n## {title}\n\n{block(key, '')}\n\n{PLACEHOLDER}\n"
    return _BLOCK.sub(
        lambda m: block(m.group("key"), RENDERERS[m.group("key")](results))
        if m.group("key") in RENDERERS
        else m.group(0),
        text,
    )


def write_report(results_dir: Path, out: Path) -> Path:
    existing = out.read_text() if out.exists() else None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(results_dir, existing))
    return out
