"""Progress plumbing: coalescing Engine events, and reading yue2's progress lines on stderr."""

from __future__ import annotations

import re
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from arcsong.engine import Emit

# Send at most this many progress updates per second per job (M0: on_token peaks ~71/s).
PROGRESS_PER_SECOND = 4


class Coalescer:
    """Passes Stage and outcome events straight through, but holds `progress` events and
    forwards only the latest one at most PROGRESS_PER_SECOND times a second. A held update is
    flushed before any other event, so nothing a bar needs arrives out of order."""

    def __init__(self, emit: Emit, clock: Callable[[], float] = time.monotonic):
        self._emit, self._clock = emit, clock
        self._pending: dict[str, Any] | None = None
        self._last_sent = float("-inf")
        self._lock = threading.Lock()

    def __call__(self, event: dict[str, Any]) -> None:
        with self._lock:
            if event["type"] == "progress":
                now = self._clock()
                if now - self._last_sent >= 1 / PROGRESS_PER_SECOND:
                    self._pending, self._last_sent = None, now
                    self._emit(event)
                else:
                    self._pending = event
                return
            self.flush_locked()
            self._emit(event)

    def flush_locked(self) -> None:
        if self._pending is not None:
            self._emit(self._pending)
            self._pending, self._last_sent = None, self._clock()


# yue2.progress.Progress output, e.g. "[YuE2] Running Synthesizing audio: 3/8 steps (38%) |
# elapsed 12.3s" through a pipe, or "[YuE2] | Synthesizing audio: [###-----] 3/8 steps ..."
# on a terminal. (Same parser the M0 spike validated against real yue2 output.)
_LINE = re.compile(
    r"^\[YuE2\] (?:Starting|Running|Completed|Failed|Cancelled|Limit reached|"
    r"Finished \(generation limit reached\)|[|/\\-]) (?P<label>[^:]+): (?P<rest>.*)$"
)
_AMOUNT = re.compile(r"^(?:\[[#-]*\] )?(?P<completed>\d+)/(?P<total>\d+) [A-Za-z]")


def progress_line(line: str) -> tuple[str, int, int] | None:
    """(label, completed, total) from a yue2 progress line that carries a count and a total."""
    match = _LINE.match(line.strip())
    amount = match and _AMOUNT.match(match.group("rest"))
    if not amount:
        return None
    return match.group("label"), int(amount.group("completed")), int(amount.group("total"))


class StderrCounts:
    """While active, passes every stderr write through and reports yue2 `N/total` lines."""

    def __init__(self, on_count: Callable[[int, int], None]):
        self._on_count = on_count
        self._pending = ""

    def write(self, text: str) -> int:
        written = self._stream.write(text)
        *lines, self._pending = re.split(r"[\r\n]", self._pending + text)
        for line in lines:
            if (parsed := progress_line(line)) is not None:
                self._on_count(parsed[1], parsed[2])
        return written

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def __enter__(self):
        self._stream = sys.stderr
        sys.stderr = self
        return self

    def __exit__(self, *exc):
        sys.stderr = self._stream
        return False
