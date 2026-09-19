"""One real weights download from Hugging Face (~10 GB) into a temporary directory, through the
Setup API. Slow and uses the network, so it only runs with ARCSONG_REAL_DOWNLOAD=1."""

import os
import time

import pytest
from fastapi.testclient import TestClient

from arcsong.app import create_app
from arcsong.engine import EngineSpec
from arcsong.models import MlxYueModels

pytestmark = pytest.mark.skipif(
    os.environ.get("ARCSONG_REAL_DOWNLOAD") != "1", reason="set ARCSONG_REAL_DOWNLOAD=1"
)


def test_the_real_weights_download_cleans_up_verifies_and_is_ready(tmp_path):
    models = MlxYueModels(tmp_path / "models")
    spec = EngineSpec("arcsong.fake_engine:FakeEngine")  # no GPU: only the weights matter here
    with TestClient(create_app(spec, tmp_path, models=models)) as client:
        client.post("/api/setup/licence")
        assert client.post("/api/setup/download").status_code == 200
        seen, deadline = [], time.monotonic() + 3600
        while (setup := client.get("/api/setup").json())["download"]["state"] == "running":
            assert time.monotonic() < deadline, "download took over an hour"
            seen.append((setup["download"].get("phase"), setup["download"].get("bytes", 0)))
            time.sleep(5)

    assert setup["download"]["state"] == "done", setup["download"]
    assert setup["weights"]["installed"] is True
    assert setup["ready"] is True
    assert not (tmp_path / "models" / "converted" / ".cache").exists()
    assert not (tmp_path / "models" / "converted" / ".gitattributes").exists()
    downloading = [b for phase, b in seen if phase == "downloading"]
    assert len(set(downloading)) >= 2, seen
    assert "verifying" in {phase for phase, _ in seen}
