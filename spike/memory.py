"""Peak physical footprint of another process, sampled from outside it (D-008).

Physical footprint (`ri_phys_footprint` from `proc_pid_rusage`) counts Metal unified
memory that RSS misses, and is what macOS memory pressure acts on. Sampling from a
watcher works the same for an in-process Engine child and a subprocess binary.
"""

from __future__ import annotations

import ctypes
import platform
import threading

RUSAGE_INFO_V4 = 4
DEFAULT_INTERVAL = 0.25


class _RUsageInfoV4(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64)
        for name in (
            "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins",
            "wired_size", "resident_size", "phys_footprint", "proc_start_abstime",
            "proc_exit_abstime", "child_user_time", "child_system_time",
            "child_pkg_idle_wkups", "child_interrupt_wkups", "child_pageins",
            "child_elapsed_abstime", "diskio_bytesread", "diskio_byteswritten",
            "cpu_time_qos_default", "cpu_time_qos_maintenance", "cpu_time_qos_background",
            "cpu_time_qos_utility", "cpu_time_qos_legacy", "cpu_time_qos_user_initiated",
            "cpu_time_qos_user_interactive", "billed_system_time", "serviced_system_time",
            "logical_writes", "lifetime_max_phys_footprint", "instructions", "cycles",
            "billed_energy", "serviced_energy", "interval_max_phys_footprint", "runnable_time",
        )
    ]  # fmt: skip


_libproc = None
if platform.system() == "Darwin":
    _libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    _libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    _libproc.proc_pid_rusage.restype = ctypes.c_int


def _rusage(pid: int) -> _RUsageInfoV4 | None:
    if _libproc is None:
        return None
    usage = _RUsageInfoV4()
    if _libproc.proc_pid_rusage(pid, RUSAGE_INFO_V4, ctypes.byref(usage)) != 0:
        return None
    return usage


def phys_footprint(pid: int) -> int | None:
    """Current physical footprint of `pid` in bytes, or None if it can't be read."""
    usage = _rusage(pid)
    return None if usage is None else int(usage.phys_footprint)


class MemorySampler:
    """Samples a pid's physical footprint on a background thread until stopped."""

    def __init__(self, pid: int, interval: float = DEFAULT_INTERVAL):
        self.pid = pid
        self.interval = interval
        self.peak_bytes: int | None = None
        self.lifetime_peak_bytes: int | None = None
        self.sample_count = 0
        self._stop = threading.Event()
        self._sampled = threading.Condition()
        self._thread = threading.Thread(target=self._loop, name="memory-sampler", daemon=True)

    def _sample(self) -> None:
        usage = _rusage(self.pid)
        if usage is None:
            return
        footprint, lifetime = int(usage.phys_footprint), int(usage.lifetime_max_phys_footprint)
        with self._sampled:
            self.peak_bytes = max(self.peak_bytes or 0, footprint)
            if lifetime:
                self.lifetime_peak_bytes = max(self.lifetime_peak_bytes or 0, lifetime)
            self.sample_count += 1
            self._sampled.notify_all()

    def _loop(self) -> None:
        while True:
            self._sample()
            if self._stop.wait(self.interval):
                return

    def wait_for_samples(self, count: int, timeout: float = 10.0) -> bool:
        with self._sampled:
            return self._sampled.wait_for(lambda: self.sample_count >= count, timeout)

    def start(self) -> MemorySampler:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def to_dict(self) -> dict:
        return {
            "peak_footprint_bytes": self.peak_bytes,
            "lifetime_peak_footprint_bytes": self.lifetime_peak_bytes,
            "footprint_samples": self.sample_count,
            "footprint_interval_seconds": self.interval,
        }

    def __enter__(self) -> MemorySampler:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
