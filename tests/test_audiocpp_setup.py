"""audio.cpp setup: pinned release + YuE2 GGUF weights, verified by sha256, idempotent."""

import hashlib
import io
import json
import os
import tarfile

import pytest

from spike import audiocpp_setup, cli
from spike.audiocpp_setup import ChecksumMismatch, setup


def tarball_bytes() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in [("./audiocpp_cli", b"#!/bin/sh\necho cli\n"), ("./LICENSE", b"MIT")]:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644  # the real release ships 0644 binaries
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def pinned(url: str, data: bytes, **extra) -> dict:
    return {"url": url, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), **extra}


class Server:
    """Serves bytes by URL and counts what was fetched."""

    def __init__(self, blobs: dict[str, bytes]):
        self.blobs, self.fetched = dict(blobs), []

    def fetch(self, url, destination, log=None):
        self.fetched.append(url)
        destination.write_bytes(self.blobs[url])


@pytest.fixture
def release():
    tarball = tarball_bytes()
    sidecar, gguf = b'{"a": 1}', b"GGUF" + bytes(1000)
    server = Server(
        {
            "https://gh/audio.tar.gz": tarball,
            "https://hf/rev/sidecars/cfg.json": sidecar,
            "https://hf/rev/main.gguf": gguf,
        }
    )
    pins = {
        "release": pinned("https://gh/audio.tar.gz", tarball, tag="v9.9.9", asset="audio.tar.gz"),
        "weights": {
            "repo": "org/Model-GGUF",
            "revision": "rev",
            "directory": "Model-GGUF",
            "files": [
                {"path": "sidecars/cfg.json", **pinned("", sidecar)},
                {"path": "main.gguf", **pinned("", gguf)},
            ],
        },
    }
    return pins, server


@pytest.fixture(autouse=True)
def hf_urls(monkeypatch):
    monkeypatch.setattr(
        audiocpp_setup,
        "weight_url",
        lambda weights, path: f"https://hf/{weights['revision']}/{path}",
    )


def test_setup_downloads_verifies_and_unpacks_everything(tmp_path, release):
    pins, server = release

    done = setup(pins, tmp_path / "vendor", tmp_path / "models", fetch=server.fetch, log=print)

    assert len(server.fetched) == 3
    assert done.downloaded == ["audio.tar.gz", "sidecars/cfg.json", "main.gguf"]
    cli_path = done.cli
    assert cli_path == tmp_path / "vendor" / "audio.cpp-v9.9.9" / "audiocpp_cli"
    assert os.access(cli_path, os.X_OK)
    model_dir = tmp_path / "models" / "Model-GGUF"
    assert done.model_dir == model_dir
    assert (model_dir / "sidecars" / "cfg.json").read_bytes() == b'{"a": 1}'
    assert (model_dir / "main.gguf").stat().st_size == 1004
    assert not list(tmp_path.rglob("*.part"))


def test_a_second_run_downloads_nothing(tmp_path, release):
    pins, server = release
    setup(pins, tmp_path / "vendor", tmp_path / "models", fetch=server.fetch, log=print)
    server.fetched.clear()

    done = setup(pins, tmp_path / "vendor", tmp_path / "models", fetch=server.fetch, log=print)

    assert server.fetched == []
    assert done.downloaded == []
    assert os.access(done.cli, os.X_OK)


def test_a_sha256_mismatch_fails_loudly_and_keeps_nothing(tmp_path, release):
    pins, server = release
    server.blobs["https://hf/rev/main.gguf"] = b"GGUF" + b"\x01" * 1000

    with pytest.raises(ChecksumMismatch, match="main.gguf") as error:
        setup(pins, tmp_path / "vendor", tmp_path / "models", fetch=server.fetch, log=print)

    assert pins["weights"]["files"][1]["sha256"] in str(error.value)
    model_dir = tmp_path / "models" / "Model-GGUF"
    assert not (model_dir / "main.gguf").exists()
    assert not list(tmp_path.rglob("*.part"))


def test_a_tarball_mismatch_is_not_unpacked(tmp_path, release):
    pins, server = release
    server.blobs["https://gh/audio.tar.gz"] = tarball_bytes() + b"tampered"

    with pytest.raises(ChecksumMismatch, match="audio.tar.gz"):
        setup(pins, tmp_path / "vendor", tmp_path / "models", fetch=server.fetch, log=print)

    assert not (tmp_path / "vendor" / "audio.cpp-v9.9.9").exists()


def test_setup_command_exits_nonzero_on_mismatch(tmp_path, release, monkeypatch, capsys):
    pins, server = release
    server.blobs["https://gh/audio.tar.gz"] = b"not the release"
    pins_path = tmp_path / "pins.json"
    pins_path.write_text(json.dumps(pins))
    monkeypatch.setattr(audiocpp_setup, "fetch_url", server.fetch)

    code = cli.main(
        ["setup", "--pins", str(pins_path), "--vendor-dir", str(tmp_path / "vendor"),
         "--audiocpp-models", str(tmp_path / "models")]
    )  # fmt: skip

    assert code != 0
    assert "sha256 mismatch" in capsys.readouterr().err


def test_committed_pins_cover_the_release_and_the_yue2_files():
    pins = audiocpp_setup.load_pins()
    assert pins["release"]["tag"] == "v0.8.0"
    assert pins["release"]["asset"] == "audio-v0.8.0-bin-macos-arm64-metal.tar.gz"
    assert len(pins["release"]["sha256"]) == 64
    paths = {f["path"] for f in pins["weights"]["files"]}
    assert paths == {
        "yue2-3b-q8_0.gguf",
        "yue2-3b-bf16.gguf",
        "yue2-vae-f16.gguf",
        "sidecars/yue2-model-config.json",
        "sidecars/yue2-generation-config.json",
        "sidecars/yue2-qwen.tiktoken",
        "sidecars/yue2-vae-config.json",
    }
