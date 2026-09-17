"""mlx-Yue load bookkeeping, without weights: only the pipeline's `load_timing` dict."""

import pytest

from spike.mlx_engine import loads_since


def test_a_run_reports_only_the_weights_it_loaded_itself():
    before = {
        "ar_load_events_seconds": (0.5,),
        "ar_load_seconds": 0.5,
        "resolve_conversion_integrity_seconds": 6.0,
    }
    after = {
        **before,
        "ar_load_events_seconds": (0.5, 0.25),
        "ar_load_seconds": 0.75,
        "nar_load_events_seconds": (0.125,),
        "nar_load_seconds": 0.125,
    }

    assert loads_since(before, after) == pytest.approx(
        {"ar_load_seconds": 0.25, "nar_load_seconds": 0.125}
    )


def test_a_run_that_loaded_nothing_reports_no_loads():
    timing = {"vae_load_events_seconds": (0.1,), "vae_load_seconds": 0.1}

    assert loads_since(timing, dict(timing)) == {}
