"""Which tests run where. The app's own tests run everywhere CI does; two groups don't.

- The M0 harness (`spike/`) measured mlx-Yue and audio.cpp on this Mac: it drives a macOS
  audio.cpp build through shell scripts and reads macOS memory counters, so its tests run on
  macOS only.
- A few harness tests assert wall-clock timings to within tens of milliseconds. Shared CI
  runners are too slow and noisy for that, so they are skipped where `CI` is set (GitHub sets
  it) and keep running locally.
"""

import os
import sys
from functools import cache

import pytest

SPIKE_MODULES = {
    "test_audiocpp_engine",
    "test_audiocpp_log",
    "test_audiocpp_setup",
    "test_cancel",
    "test_doctor",
    "test_download",
    "test_draft_final",
    "test_env",
    "test_hygiene",
    "test_m0_report_numbers",
    "test_memory",
    "test_progress",
    "test_repro",
    "test_report",
    "test_runner",
    "test_timing",
}
WALLCLOCK_MODULES = {"test_cancel", "test_progress", "test_timing"}


@cache
def mlx_usable() -> bool:
    """Linux's mlx wheel needs its CPU or CUDA extra, and Windows has no build of it."""
    try:
        import mlx.core  # noqa: F401
    except ImportError:
        return False
    return True


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_mlx: imports MLX itself (skipped where it can't)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        module = item.module.__name__.rsplit(".", 1)[-1]
        if module in SPIKE_MODULES and sys.platform != "darwin":
            item.add_marker(pytest.mark.skip(reason="the M0 harness measured macOS only"))
        elif module in WALLCLOCK_MODULES and os.environ.get("CI"):
            item.add_marker(pytest.mark.skip(reason="wall-clock assertions; CI is too noisy"))
        if item.get_closest_marker("needs_mlx") and not mlx_usable():
            item.add_marker(pytest.mark.skip(reason="MLX can't load on this machine"))
