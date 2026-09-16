"""The spike's Engine seam (D-005): one interface both Engines are driven through."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

STAGES = ("planning", "semantic generation", "synthesis", "decoding")

CancelCheck = Callable[[], bool]


class Unsupported(Exception):  # noqa: N818 - glossary term, recorded as an outcome
    """Raised when an Engine cannot perform an operation; a finding, not a failure."""


@dataclass(frozen=True)
class StageEvent:
    stage: str
    kind: Literal["start", "end"]
    t: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EventSink = Callable[[StageEvent], None]


@dataclass(frozen=True)
class EngineInfo:
    name: str
    version: str | None
    commit: str | None


@dataclass
class RunOutput:
    """What a whole-Take run left behind."""

    audio_path: Path
    audio_seconds: float
    files: list[Path] = field(default_factory=list)


def never_cancelled() -> bool:
    return False


def ignore_event(event: StageEvent) -> None:
    return None


@runtime_checkable
class SpikeEngine(Protocol):
    """Mirrors PLAN.md's Engine seam. Operations an Engine lacks raise `Unsupported`."""

    def info(self) -> EngineInfo:
        """Name, version and commit, available without loading weights."""
        ...

    def load(self, precision: str) -> None: ...

    def plan(
        self, request: dict, *, cancelled: CancelCheck = ..., on_event: EventSink = ...
    ) -> Any: ...

    def generate_semantic(
        self, score_or_request: Any, *, cancelled: CancelCheck = ..., on_event: EventSink = ...
    ) -> Any: ...

    def synthesize(
        self,
        semantic: Any,
        steps: int,
        noise: Any = None,
        *,
        cancelled: CancelCheck = ...,
        on_event: EventSink = ...,
    ) -> Any: ...

    def decode(
        self, latents: Any, *, cancelled: CancelCheck = ..., on_event: EventSink = ...
    ) -> Any: ...

    def run(
        self,
        request: dict,
        steps: int,
        output_dir: Path,
        *,
        cancelled: CancelCheck = ...,
        on_event: EventSink = ...,
    ) -> RunOutput: ...
