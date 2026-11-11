"""The Modal Engine: each job runs on the user's own Modal account (`arcsong.modal_app`).

The worker process stays light: it sends the request, forwards the remote stage events, and
writes the returned files as the Take. A Take keeps yue2's own artifacts, so a Final sends the
Draft's plan and Semantic tokens back to be re-synthesized at more steps.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arcsong.engine import STAGES, CancelCheck, Cancelled, Emit, ScoreOutput, TakeOutput

APP_NAME = "arcsong"
# What yue2's SymbolicPlan.load and a Final need from a Draft made on Modal.
PLAN_FILES = ("plan.json", "abc_tokens.npy", "prefix.npy", "plan_manifest.json", "semantic.npy")
POLL_SECONDS = 0.5
CANCELLED_ELSEWHERE = "The job was stopped on Modal (from its dashboard or `modal app stop`)."
COVERS_ADVICE = "Covers run on the Mac engine only: start Arcsong with --engine mlx to make one."
MAC_DRAFT_ADVICE = (
    "This Draft was made by the Mac engine, which Modal can't continue. Finalize it with "
    "--engine mlx, or render the song again on Modal."
)

# (job, cancelled, emit) -> the remote result; tests pass their own.
Remote = Callable[[dict[str, Any], CancelCheck, Emit], dict[str, Any]]


class ModalEngine:
    mac_draft_advice = MAC_DRAFT_ADVICE
    cancelled_elsewhere = CANCELLED_ELSEWHERE

    def __init__(self, app_name: str = APP_NAME, remote: Remote | None = None):
        self.app_name = app_name
        self._remote = remote

    def load(self) -> None:
        """Nothing to load here: the model lives in the remote container. The lookup is lazy, so
        a missing app or login only shows at the first job, in Modal's own words."""
        if self._remote is None:
            import modal

            self._renderer = modal.Cls.from_name(self.app_name, "Renderer")
            self._remote = self._call

    def _call(self, job: dict[str, Any], cancelled: CancelCheck, emit: Emit) -> dict[str, Any]:
        import modal

        with modal.Queue.ephemeral() as events:
            call = self._renderer().run.spawn(job, events)
            # `FunctionCall.get(timeout=…)` doesn't return early while the call is pending, so it
            # waits on a side thread and this loop stays free to relay events and cancel.
            outcome: dict[str, Any] = {}
            waiter = threading.Thread(target=_wait, args=(call, outcome), daemon=True)
            waiter.start()
            while True:
                if cancelled():
                    call.cancel()
                    raise Cancelled(job["kind"])
                waiter.join(POLL_SECONDS)
                finished = not waiter.is_alive()  # read before draining, so no event is left over
                for event in events.get_many(1000, block=False):
                    emit(event)
                if finished:
                    error = outcome.get("error")
                    if error is None:
                        return outcome["result"]
                    if isinstance(error, Exception):
                        raise error
                    # Modal's InputCancellation is a BaseException: the worker would die on it.
                    raise RuntimeError(self.cancelled_elsewhere) from error

    def plan_only(self, request: dict[str, Any], cancelled: CancelCheck, emit: Emit) -> ScoreOutput:
        emit({"type": "stage", "stage": STAGES[0]})  # the container may take a minute to start
        abc = self._remote({"kind": "plan", "request": request}, cancelled, emit)["abc"]
        if abc is None:
            raise ValueError("this planning mode writes no Score")
        return ScoreOutput(abc)

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        emit({"type": "stage", "stage": STAGES[0]})
        result = self._remote({"kind": "render", "request": request}, cancelled, emit)
        return _save(result, out_dir)

    def finalize(
        self,
        source_dir: Path,
        request: dict[str, Any],
        out_dir: Path,
        cancelled: CancelCheck,
        emit: Emit,
    ) -> TakeOutput:
        if not source_dir.is_dir():
            raise FileNotFoundError("its Draft was deleted")
        # mlx-Yue keeps its own synthesis noise; yue2 on CUDA would make different music from it.
        if (source_dir / "noise.npy").exists():
            raise ValueError(self.mac_draft_advice)
        names = [*PLAN_FILES, *(["score.abc"] if (source_dir / "score.abc").exists() else [])]
        files = {name: (source_dir / name).read_bytes() for name in names}
        emit({"type": "stage", "stage": STAGES[2]})
        job = {"kind": "finalize", "request": request, "files": files}
        return _save(self._remote(job, cancelled, emit), out_dir)

    def transcribe(self, audio, request, out_dir, cancelled, emit) -> ScoreOutput:
        raise RuntimeError(COVERS_ADVICE)


def _wait(call, outcome: dict[str, Any]) -> None:
    try:
        outcome["result"] = call.get()
    except BaseException as error:  # the remote's own error, re-raised in the worker
        outcome["error"] = error


def _save(result: dict[str, Any], out_dir: Path) -> TakeOutput:
    if out_dir.exists():
        shutil.rmtree(out_dir)  # leftovers of an interrupted Take; never a finished one
    out_dir.mkdir(parents=True)
    for name, data in result["files"].items():
        (out_dir / Path(name).name).write_bytes(data)
    return TakeOutput(out_dir / "audio.flac", result["audio_seconds"])
