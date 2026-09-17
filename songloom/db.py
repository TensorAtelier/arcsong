"""The SQLite index of jobs and songs. Only the server process writes it."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,            -- queued | running | done | failed | cancelled
    request_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    error TEXT,
    song_id INTEGER
);
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    dir TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    audio_seconds REAL,
    created_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(SCHEMA)
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._conn.close()

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO jobs (status, request_json, created_at) VALUES ('queued', ?, ?)",
                (json.dumps(request), time.time()),
            )
            job_id = cur.lastrowid
        return self.get_job(job_id)

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT j.*, s.audio_seconds FROM jobs j LEFT JOIN songs s ON s.id = j.song_id "
                "WHERE j.id = ?",
                (job_id,),
            ).fetchone()
        return _job(row) if row else None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT j.*, s.audio_seconds FROM jobs j LEFT JOIN songs s ON s.id = j.song_id "
                "ORDER BY j.id DESC"
            ).fetchall()
        return [_job(r) for r in rows]

    def next_queued(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
        return self.get_job(row["id"]) if row else None

    def mark_running(self, job_id: int) -> None:
        self._update(job_id, "status = 'running', started_at = ?", time.time())

    def mark_finished(self, job_id: int, status: str, error: str | None = None) -> None:
        self._update(job_id, "status = ?, finished_at = ?, error = ?", status, time.time(), error)

    def add_song(self, job_id: int, directory: Path, audio: Path, seconds: float) -> int:
        """Index a finished Take and mark its job done, in one transaction."""
        now = time.time()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO songs (job_id, dir, audio_path, audio_seconds, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (job_id, str(directory), str(audio), seconds, now),
            )
            self._conn.execute(
                "UPDATE jobs SET status = 'done', finished_at = ?, song_id = ? WHERE id = ?",
                (now, cur.lastrowid, job_id),
            )
            return cur.lastrowid

    def recover(self) -> list[int]:
        """On server start: jobs left `running` by a previous server can never finish."""
        with self._lock, self._conn:
            rows = self._conn.execute("SELECT id FROM jobs WHERE status = 'running'").fetchall()
            ids = [r["id"] for r in rows]
            self._conn.execute(
                "UPDATE jobs SET status = 'failed', finished_at = ?, "
                "error = 'the server stopped while this job was running' WHERE status = 'running'",
                (time.time(),),
            )
        return ids

    def list_songs(self) -> list[dict[str, Any]]:
        """Finished Takes with their Song request, newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT s.*, j.request_json FROM songs s JOIN jobs j ON j.id = s.job_id "
                "ORDER BY s.id DESC"
            ).fetchall()
        return [_song(r) for r in rows]

    def delete_song(self, song_id: int) -> dict[str, Any] | None:
        """Remove a song and the job that made it; returns the deleted song, or None."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT s.*, j.request_json FROM songs s JOIN jobs j ON j.id = s.job_id "
                "WHERE s.id = ?",
                (song_id,),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (row["job_id"],))
        return _song(row)

    def get_song(self, song_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
        return dict(row) if row else None

    def _update(self, job_id: int, assignments: str, *values: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values, job_id))


def _job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["request"] = json.loads(job.pop("request_json"))
    return job


def _song(row: sqlite3.Row) -> dict[str, Any]:
    song = dict(row)
    song["request"] = json.loads(song.pop("request_json"))
    return song
