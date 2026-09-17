"""The Engine seam: what the worker process drives to turn a Song request into a Take."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

STAGES = ("planning", "semantic generation", "synthesis", "decoding")

CancelCheck = Callable[[], bool]
# An Engine reports what it is doing as plain dicts, e.g. {"type": "stage", "stage": "planning"}.
Emit = Callable[[dict[str, Any]], None]


class Cancelled(Exception):  # noqa: N818 - a normal outcome, not an error
    """Raised by an Engine when its cancel check turned true mid-Take."""


@dataclass
class TakeOutput:
    """What a finished Take left on disk."""

    audio_path: Path
    audio_seconds: float


class Engine(Protocol):
    def load(self) -> None:
        """Load the model once; later Takes reuse it."""

    def render(
        self, request: dict[str, Any], out_dir: Path, cancelled: CancelCheck, emit: Emit
    ) -> TakeOutput:
        """Render one Take into `out_dir`, which must be complete when this returns."""

    def finalize(
        self,
        source_dir: Path,
        request: dict[str, Any],
        out_dir: Path,
        cancelled: CancelCheck,
        emit: Emit,
    ) -> TakeOutput:
        """Make a Draft's Final: re-synthesize the Take saved in `source_dir` (its Semantic
        tokens and noise) at `request["steps"]` and decode it into `out_dir`. Only the synthesis
        and decoding Stages run."""


@dataclass(frozen=True)
class EngineSpec:
    """A picklable recipe for building an Engine inside the worker process."""

    factory: str  # "package.module:callable"
    kwargs: dict[str, Any] = field(default_factory=dict)

    def build(self) -> Engine:
        module, _, name = self.factory.partition(":")
        return getattr(importlib.import_module(module), name)(**self.kwargs)
