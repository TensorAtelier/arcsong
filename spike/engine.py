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
    """A Stage's `start`/`end` at time `t`. An Engine that learns a Stage's exact start only
    after the fact also sends `enter` the moment it sees the Stage has begun."""

    stage: str
    kind: Literal["start", "end", "enter"]
    t: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressEvent:
    """A progress signal that fired at time `t`, e.g. a token callback or a log line.

    `stage` is the Stage the Engine believes it is in (None if it cannot tell); `completed`
    and `total` are the counts the signal itself carries, None when it carries none.
    Consumers that only want Stage transitions skip it by its `kind`.
    """

    stage: str | None
    signal: str
    completed: int | None = None
    total: int | None = None
    t: float = field(default_factory=time.monotonic)
    kind: Literal["progress"] = "progress"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EventSink = Callable[[StageEvent | ProgressEvent], None]


@dataclass(frozen=True)
class EngineInfo:
    name: str
    version: str | None
    commit: str | None
    # Whether Takes run after `load` reuse the model it loaded (a warm process); False when
    # every Take starts a new Engine process that loads the model again.
    takes_reuse_loaded_model: bool = True


@dataclass
class RunOutput:
    """What a whole-Take run left behind."""

    audio_path: Path
    audio_seconds: float
    files: list[Path] = field(default_factory=list)
    # Weights an Engine loads lazily inside a Stage, e.g. {"nar_load_seconds": 4.2}.
    lazy_load_seconds: dict[str, float] = field(default_factory=dict)
    # The Engine's own peak-memory figure (MLX: mx.get_peak_memory()), if it has one.
    engine_peak_memory_bytes: int | None = None
    # The file holding each Stage's output, for the Stages whose output the Engine exports:
    # planning -> Score, semantic generation -> Semantic tokens, synthesis -> Latents.
    stage_outputs: dict[str, Path] = field(default_factory=dict)
    # The synthesis noise the Take used, saved so a Final can reuse it; None if not kept.
    noise_path: Path | None = None
    # Engine-specific facts about how the Take was made, e.g. extra work to keep its noise.
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CliTake:
    """A whole Take started through an Engine's own command line (optional capability
    `take_command`). `stage_markers` maps a Stage to text its output prints as it begins."""

    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    stage_markers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WeightsDownload:
    """What an Engine's weight download put in a directory (optional capability
    `download_weights`). Paths are relative to that directory."""

    # The directories the Engine loads weights from, e.g. {"converted": ..., "vae": ...}.
    weight_dirs: dict[str, str]
    # Files fetched from the model hub, as the hub names them (joined to their directory).
    downloaded: list[str]
    # Files placed without downloading them (e.g. local copies of large weights).
    supplied_locally: list[dict[str, Any]] = field(default_factory=list)
    # How each directory was fetched: repository, revision, patterns.
    sources: list[dict[str, Any]] = field(default_factory=list)


def never_cancelled() -> bool:
    return False


def ignore_event(event: StageEvent | ProgressEvent) -> None:
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
        noise: Path | None = None,
        keep_noise: bool = False,
        cancelled: CancelCheck = ...,
        on_event: EventSink = ...,
    ) -> RunOutput:
        """A whole Take. `noise` is a noise file an earlier run of this Engine saved
        (`RunOutput.noise_path`) to synthesize with; `keep_noise` asks the Engine to save
        the noise it uses even if that takes extra work."""
        ...

    def render_final(
        self,
        draft_dir: Path,
        steps: int,
        output_dir: Path,
        *,
        cancelled: CancelCheck = ...,
        on_event: EventSink = ...,
    ) -> RunOutput:
        """Re-synthesizes and decodes the Semantic tokens and noise of the Draft saved in
        `draft_dir` at `steps` Synthesis steps; `Unsupported` if they can't be taken back."""
        ...
