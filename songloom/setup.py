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
from pathlib import Path
from typing import Any

import psutil

from songloom.db import Store
from songloom.models import LICENCE, Check, Models, bytes_on_disk, check, weights_state
from songloom.worker import exit_with_parent

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


class Setup:
    def __init__(
        self,
        models: Models,
        store: Store,
        publish: Callable[[dict[str, Any]], None],
        seq: Callable[[], int],
    ):
        """`publish` broadcasts a message to the page; `seq` numbers snapshots (see
        `JobRunner.next_seq`) so the page keeps the newest one."""
        self.models = models
        self.store = store
        self._publish = publish
        self._seq = seq
        self._ctx = mp.get_context("spawn")
        self._lock = threading.RLock()
        self._engine_checks: list[Check] | None = None
        self._checking = False
        self._process = None
        self._download: dict[str, Any] = {"state": "idle"}
        self._stopping = threading.Event()

    # --- snapshot --------------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        seq = self._seq()
        weights = weights_state(self.models)
        acknowledged = self.store.get_setting(LICENCE_KEY)
        with self._lock:
            download = dict(self._download)
            engine_checks = self._engine_checks
            checking = self._checking
        if download["state"] == "running":
            download["bytes"] = bytes_on_disk(self.models)
            download["bytes_total"] = weights["bytes_total"]
        checks = [
            *(engine_checks or []),
            _ram_check(),
            _power_check(),
            _disk_check(self.models.directory, weights),
            _weights_check(weights, download["state"]),
        ]
        can_render = self.can_render(weights, download)
        return {
            "seq": seq,
            "checks": checks,
            "checking": checking or engine_checks is None,
            "weights": weights,
            "licence": {**LICENCE, "acknowledged_at": (acknowledged or {}).get("at")},
            "download": download,
            "can_render": can_render,
            "ready": can_render and acknowledged is not None,
        }

    def can_render(self, weights=None, download=None) -> bool:
        """Jobs need the weights on disk, no download rewriting them, and no failed verification
        since the server started (sizes alone can't catch a corrupt file)."""
        weights = weights or weights_state(self.models)
        with self._lock:
            download = download or self._download
        return weights["installed"] and download["state"] not in ("running", "failed")

    def publish(self) -> None:
        self._publish({"type": "setup", "setup": self.snapshot()})

    # --- checks ----------------------------------------------------------------------------

    def run_checks(self) -> None:
        """Re-run the Engine's own checks in the background; the rest are live."""
        with self._lock:
            if self._checking:
                return
            self._checking = True
        threading.Thread(target=self._check, name="songloom-checks", daemon=True).start()

    def _check(self) -> None:
        try:
            results = self.models.engine_checks()
        except Exception as error:
            results = [check("runtime", "Engine checks", "fail", _reason(error))]
        with self._lock:
            self._engine_checks, self._checking = results, False
        if not self._stopping.is_set():
            self.publish()

    # --- licence ---------------------------------------------------------------------------

    def acknowledge(self) -> None:
        if self.store.get_setting(LICENCE_KEY) is None:
            self.store.set_setting(LICENCE_KEY, {"licence": LICENCE["id"], "at": time.time()})
        self.publish()

    # --- download --------------------------------------------------------------------------

    def start_download(self) -> str | None:
        """Start the download; returns why it can't start, or None."""
        if self.store.get_setting(LICENCE_KEY) is None:
            return "acknowledge the model licence first"
        with self._lock:
            if self._download["state"] == "running":
                return "a download is already running"
            events = self._ctx.Queue()
            self._process = self._ctx.Process(
                target=download_main, args=(self.models, events, os.getpid()), daemon=True
            )
            self._download = {"state": "running", "phase": "starting", "started_at": time.time()}
            self._process.start()
            process = self._process
        threading.Thread(
            target=self._follow, args=(process, events), name="songloom-download", daemon=True
        ).start()
        self.publish()
        return None

    def cancel_download(self) -> bool:
        with self._lock:
            process = self._process
            if process is None or self._download["state"] != "running":
                return False
            self._download = {"state": "cancelled"}
        process.kill()
        process.join()
        self.publish()
        return True

    def _follow(self, process, events) -> None:
        """Relay the download's phases and bytes until its process ends."""
        outcome = None
        while outcome is None:
            try:
                event = events.get(timeout=POLL_SECONDS)
            except queue.Empty:
                event = None
            with self._lock:
                if self._process is not process or self._download["state"] != "running":
                    return  # cancelled or stopped
                if event and event["type"] == "phase":
                    self._download["phase"] = event["phase"]
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
            if self._process is not process or self._download["state"] != "running":
                return  # cancelled while it was finishing: keep what cancel reported
            if outcome["type"] == "done":
                self._download = {"state": "done", "finished_at": time.time()}
            else:
                self._download = {
                    "state": "failed",
                    "reason": outcome["reason"],
                    "error": outcome["error"],
                }
        self.publish()

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            process, self._process = self._process, None
        if process is not None and process.is_alive():
            process.kill()
            process.join()


# --- checks that need no Engine ---------------------------------------------------------------


def _ram_check() -> Check:
    total = psutil.virtual_memory().total / GIB
    label = "Memory"
    if total < RAM_WARN_GIB:
        detail = (
            f"{total:.0f} GiB. A song peaks at about 11 GiB and songloom is untested below "
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


def _weights_check(weights: dict[str, Any], download_state: str) -> Check:
    label = "Model weights"
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
