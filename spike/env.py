"""Environment snapshot recorded with every results file (D-008, D-015)."""

from __future__ import annotations

import platform
import re
import subprocess
import sys

from spike.engine import EngineInfo

MODEL_SERVERS = (
    ("Ollama", re.compile(r"(^|/)ollama(\s|$)|Ollama\.app", re.IGNORECASE)),
    ("LM Studio", re.compile(r"LM Studio|(^|/)lms(\s|$)")),
    ("ComfyUI", re.compile(r"ComfyUI/", re.IGNORECASE)),
)


def model_servers_from_ps(ps_output: str) -> list[dict]:
    """Parse `ps -axo pid=,rss=,command=` output into model-server processes."""
    servers = []
    for line in ps_output.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        pid, rss_kib, command = int(parts[0]), int(parts[1]), parts[2]
        for server, pattern in MODEL_SERVERS:
            if pattern.search(command):
                servers.append(
                    {"server": server, "pid": pid, "rss_bytes": rss_kib * 1024, "command": command}
                )
                break
    return servers


def running_model_servers() -> list[dict]:
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,rss=,command="], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return model_servers_from_ps(out)


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _memory_bytes() -> int:
    value = _sysctl("hw.memsize")
    if value and value.isdigit():
        return int(value)
    try:
        import os

        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return 0


def snapshot(engine: EngineInfo) -> dict:
    return {
        "machine": {
            "arch": platform.machine(),
            "model": _sysctl("hw.model"),
            "cpu": _sysctl("machdep.cpu.brand_string"),
            "memory_bytes": _memory_bytes(),
        },
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "macos": platform.mac_ver()[0] or None,
        },
        "python": sys.version.split()[0],
        "engine": {"name": engine.name, "version": engine.version, "commit": engine.commit},
        "model_servers": running_model_servers(),
    }
