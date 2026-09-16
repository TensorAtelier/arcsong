"""The memory sampler watches another process's physical footprint from outside (D-008)."""

import subprocess
import sys

import pytest

from spike.memory import MemorySampler, phys_footprint

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="ri_phys_footprint is macOS-only")

MIB = 2**20
ALLOCATION = 512 * MIB

# Waits for a byte on stdin, then fills (touches) a known allocation and holds it.
ALLOCATING_CHILD = f"""
import sys, time
sys.stdin.read(1)
block = bytearray(b"\\x01") * {ALLOCATION}
print("allocated", flush=True)
time.sleep(1.5)
"""


def test_sampler_reports_a_peak_within_10_percent_of_a_known_child_allocation():
    child = subprocess.Popen(
        [sys.executable, "-c", ALLOCATING_CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        with MemorySampler(child.pid, interval=0.25) as sampler:
            sampler.wait_for_samples(2)
            baseline = phys_footprint(child.pid)
            child.stdin.write("go")
            child.stdin.close()
            assert child.stdout.readline().strip() == "allocated"
            child.wait(timeout=30)
    finally:
        child.kill()

    assert baseline is not None
    growth = sampler.peak_bytes - baseline
    assert abs(growth - ALLOCATION) <= 0.10 * ALLOCATION, (sampler.peak_bytes, baseline)
    assert sampler.sample_count >= 4


def test_sampler_of_a_missing_process_reports_no_peak():
    with MemorySampler(2**22 + 12345, interval=0.01) as sampler:
        pass
    assert sampler.peak_bytes is None
