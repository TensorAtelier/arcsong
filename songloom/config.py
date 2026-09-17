"""Where songloom keeps its data."""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs

DATA_ENV = "SONGLOOM_DATA"


def data_dir(override: str | Path | None = None) -> Path:
    """The data directory: an explicit override, else `$SONGLOOM_DATA`, else the user data dir."""
    chosen = override or os.environ.get(DATA_ENV) or platformdirs.user_data_dir("songloom")
    path = Path(chosen).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
