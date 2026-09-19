"""The Setup page's server side: checks, the licence acknowledgement, and the weights
download, which runs in its own spawned process while the server polls its bytes on disk."""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import shutil
import subprocess
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from arcsong.db import Store
from arcsong.models import LICENCE, Check, Models, bytes_on_disk, check, weights_state
from arcsong.worker import exit_with_parent

GIB = 2**30
# M0: a song peaks at ~10.5–11 GiB of unified memory. The real floor is unmeasured (PLAN open
# question 2), so below this the page warns instead of blocking.
RAM_WARN_GIB = 24
# Room left over after the download, for Takes (~40 MiB each) and the rest of the system.
DISK_SPARE_BYTES = 1 * GIB
POLL_SECONDS = 0.5
LICENCE_KEY = "licence_acknowledged"


def download_main(models: Models, events, parent_pid: int) -> None:
    """Run in a spawned process: download, clean up and verify, reporting phases and the end."""
    threading.Thread(target=exit_with_parent, args=(parent_pid,), daemon=True).start()
    try:
        models.download(lambda phase: events.put({"type": "phase", "phase": phase}))
    except BaseException as error:
        events.put({"type": "failed", "reason": _reason(error), "error": traceback.format_exc()})
    else:
        events.put({"type": "done"})


def _final_event(events, wait: float = 1.0) -> dict[str, Any] | None:
    """The outcome a finished download process left in `events`, if any."""
    while True:
        try:
            event = events.get(timeout=wait)
        except queue.Empty:
            return None
        if event["type"] != "phase":
            return event


def _reason(error: BaseException) -> str:
    text = str(error).strip().splitlines()
    return f"{type(error).__name__}: {text[-1]}" if text else type(error).__name__


ENGINE = "engine"
COVERS = "covers"


@dataclass
class Part:
    """One set of weights the Setup page manages. `engine` is needed to make songs; the rest
    are optional extras (`covers`)."""

    id: str
    label: str
    models: Models
    summary: str = ""
    # The Engine part: songs need it, and it never waits for its checks to finish.
    required: bool = False


class Setup:
    def __init__(
        self,
        parts: list[Part],
        store: Store,
        publish: Callable[[dict[str, Any]], None],
        seq: Callable[[], int],
    ):
        """`publish` broadcasts a message to the page; `seq` numbers snapshots (see
        `JobRunner.next_seq`) so the page keeps the newest one."""
        self.parts = {part.id: part for part in parts}
        self.store = store
        self._publish = publish
        self._seq = seq
        self._ctx = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._part_checks: dict[str, list[Check]] = {}
        self._checking = False
        self._process = None
        self._downloading: str | None = None
        self._downloads: dict[str, dict[str, Any]] = {p.id: {"state": "idle"} for p in parts}
        self._stopping = threading.Event()

    @property
    def models(self) -> Models:
        """The song weights; the Engine part is what rendering needs."""
        return self.parts[ENGINE].models

    # --- snapshot --------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        seq = self._seq()
        acknowledged = self.store.get_setting(LICENCE_KEY)
        with self._lock:
            checking = self._checking or not self._part_checks
        parts = [self._part_snapshot(part) for part in self.parts.values()]
        engine = next(p for p in parts if p["id"] == ENGINE)
        can_render = _part_usable(engine)
        return {
            "seq": seq,
            "checks": [_ram_check(), _power_check()],
            "checking": checking,
            "parts": parts,
            # The Engine part, also at the top level: most of the page only cares about it.
            "weights": engine["weights"],
            "download": engine["download"],
            "licence": {**LICENCE, "acknowledged_at": (acknowledged or {}).get("at")},
            "can_render": can_render,
            "ready": can_render and acknowledged is not None,
        }

    def _part_snapshot(self, part: Part) -> dict[str, Any]:
        weights = weights_state(part.models)
        with self._lock:
            download = dict(self._downloads[part.id])
            checks = list(self._part_checks.get(part.id, []))
            checked = part.id in self._part_checks
        if download["state"] == "running":
            download["bytes"] = bytes_on_disk(part.models)
            download["bytes_total"] = weights["bytes_total"]
        snapshot = {
            "id": part.id,
            "label": part.label,
            "summary": part.summary,
            "required": part.required,
            "weights": weights,
            "download": download,
            "checked": checked,
            "checks": [
                *checks,
                _disk_check(part.models.directory, weights),
                _weights_check(weights, download["state"], part.label),
            ],
        }
        snapshot["usable"] = _part_usable(snapshot)
        return snapshot

    def part(self, part_id: str) -> dict[str, Any] | None:
        part = self.parts.get(part_id)
        return self._part_snapshot(part) if part else None

    def usable(self, part_id: str) -> bool:
        """This part's weights are installed, nothing is rewriting them, and its own checks pass."""
        snapshot = self.part(part_id)
        return snapshot is not None and snapshot["usable"]

    def can_render(self, *_ignored) -> bool:
        return self.usable(ENGINE)

    def publish(self) -> None:
        self._publish({"type": "setup", "setup": self.snapshot()})

    # --- checks ----------------------------------------------------------------------------

    def run_checks(self) -> None:
        """Re-run the Engine's own checks in the background; the rest are live."""
        with self._lock:
            if self._checking:
                return
            self._checking = True
        threading.Thread(target=self._check, name="arcsong-checks", daemon=True).start()

    def _check(self) -> None:
        results = {}
        for part in self.parts.values():
            try:
                results[part.id] = part.models.engine_checks()
            except Exception as error:
                failed = check("runtime", f"{part.label} checks", "fail", _reason(error))
                results[part.id] = [failed]
        with self._lock:
            self._part_checks, self._checking = results, False
        if not self._stopping.is_set():
            self.publish()

    # --- licence ---------------------------------------------------------------------------

    def acknowledge(self) -> None:
        if self.store.get_setting(LICENCE_KEY) is None:
            self.store.set_setting(LICENCE_KEY, {"licence": LICENCE["id"], "at": time.time()})
        self.publish()

    # --- download --------------------------------------------------------------------------

    def start_download(self, part_id: str = ENGINE) -> str | None:
        """Start a part's download; returns why it can't start, or None. One at a time, so two
        parts never compete for the network or the disk."""
        part = self.parts.get(part_id)
        if part is None:
            return "no such part"
        if self.store.get_setting(LICENCE_KEY) is None:
            return "acknowledge the model licence first"
        with self._lock:
            if self._downloading is not None:
                running = self.parts[self._downloading].label
                return f"the {running} download is already running"
            events = self._ctx.Queue()
            self._process = self._ctx.Process(
                target=download_main, args=(part.models, events, os.getpid()), daemon=True
            )
            self._downloads[part_id] = {
                "state": "running",
                "phase": "starting",
                "started_at": time.time(),
            }
            self._downloading = part_id
            self._process.start()
            process = self._process
        threading.Thread(
            target=self._follow,
            args=(process, events, part_id),
            name="arcsong-download",
            daemon=True,
        ).start()
        self.publish()
        return None

    def cancel_download(self, part_id: str = ENGINE) -> bool:
        with self._lock:
            process = self._process
            if process is None or self._downloads.get(part_id, {}).get("state") != "running":
                return False
            self._downloads[part_id] = {"state": "cancelled"}
            self._downloading = None
        process.kill()
        process.join()
        self.publish()
        return True

    def _follow(self, process, events, part_id: str) -> None:
        """Relay the download's phases and bytes until its process ends."""
        outcome = None
        while outcome is None:
            try:
                event = events.get(timeout=POLL_SECONDS)
            except queue.Empty:
                event = None
            with self._lock:
                if self._process is not process or self._downloads[part_id]["state"] != "running":
                    return  # cancelled or stopped
                if event and event["type"] == "phase":
                    self._downloads[part_id]["phase"] = event["phase"]
                elif event:
                    outcome = event
                elif not process.is_alive():
                    # Its last message can still be in the queue's pipe; read what is left.
                    outcome = _final_event(events)
                    if outcome is None:
                        code = process.exitcode
                        reason = f"the download process exited unexpectedly (code {code})"
                        outcome = {"type": "failed", "reason": reason, "error": reason}
            if self._stopping.is_set():
                return
            if outcome is None:
                self.publish()
        process.join(timeout=5)
        with self._lock:
            if self._process is not process or self._downloads[part_id]["state"] != "running":
                return  # cancelled while it was finishing: keep what cancel reported
            self._downloading = None
            if outcome["type"] == "done":
                self._downloads[part_id] = {"state": "done", "finished_at": time.time()}
            else:
                self._downloads[part_id] = {
                    "state": "failed",
                    "reason": outcome["reason"],
                    "error": outcome["error"],
                }
        self.publish()

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            process, self._process, self._downloading = self._process, None, None
        if process is not None and process.is_alive():
            process.kill()
            process.join()


# --- checks that need no Engine ---------------------------------------------------------------


def _ram_check() -> Check:
    total = psutil.virtual_memory().total / GIB
    label = "Memory"
    if total < RAM_WARN_GIB:
        detail = (
            f"{total:.0f} GiB. A song peaks at about 11 GiB and arcsong is untested below "
            f"{RAM_WARN_GIB} GiB; close other apps and model servers before rendering."
        )
        return check("ram", label, "warn", detail)
    return check("ram", label, "ok", f"{total:.0f} GiB (a song peaks at about 11 GiB)")


def _power_check() -> Check:
    label = "Power"
    try:
        out = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return check("power", label, "ok", "not a Mac battery; nothing to check")
    if "'AC Power'" in out:
        return check("power", label, "ok", "on AC power")
    return check("power", label, "warn", "on battery: mlx-Yue refuses to render until plugged in")


def _disk_check(directory: Path, weights: dict[str, Any]) -> Check:
    label = "Disk space"
    existing = directory
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    free = shutil.disk_usage(existing).free
    needed = weights["bytes_total"] - weights["bytes_on_disk"]
    free_text = f"{free / GIB:.1f} GiB free"
    if needed and free < needed + DISK_SPARE_BYTES:
        detail = f"{free_text}; the download needs {needed / GIB:.1f} GiB plus 1 GiB to spare"
        return check("disk", label, "fail", detail)
    if needed:
        return check("disk", label, "ok", f"{free_text}; the download needs {needed / GIB:.1f} GiB")
    return check("disk", label, "ok", f"{free_text}; a 3-minute song takes about 40 MiB")


def _part_usable(snapshot: dict[str, Any]) -> bool:
    """Installed, no download rewriting or failing on it, and its own checks (Metal, ffmpeg) all
    pass — sizes alone can't catch a corrupt file, so a failed verification blocks too. An
    optional part also waits for its checks: covers without ffmpeg would fail in the worker,
    while the Engine part doesn't wait, since a bad runtime fails the model load anyway."""
    if not snapshot["checked"] and not snapshot["required"]:
        return False
    return (
        snapshot["weights"]["installed"]
        and snapshot["download"]["state"] not in ("running", "failed")
        and all(c["status"] != "fail" for c in snapshot["checks"] if c["id"] != "weights")
    )


def _weights_check(weights: dict[str, Any], download_state: str, label: str = "Model") -> Check:
    label = f"{label} weights"
    where = weights["dir"]
    if weights["installed"]:
        return check("weights", label, "ok", f"installed in {where}")
    if download_state == "running":
        return check("weights", label, "warn", f"downloading into {where}")
    if weights["stray"]:
        stray = ", ".join(weights["stray"])
        detail = f"{where} has files mlx-Yue rejects ({stray}); download again to remove them"
        return check("weights", label, "fail", detail)
    if weights["bytes_on_disk"]:
        have, total = weights["bytes_on_disk"] / GIB, weights["bytes_total"] / GIB
        detail = f"incomplete in {where} ({have:.1f} of {total:.1f} GiB); download to finish"
        return check("weights", label, "fail", detail)
    total = weights["bytes_total"] / GIB
    return check("weights", label, "fail", f"not downloaded yet ({total:.1f} GiB into {where})")
