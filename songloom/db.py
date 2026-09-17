"""The SQLite index of jobs and songs. Only the server process writes it."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,            -- queued | running | done | failed | cancelled
    request_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    error TEXT,
    song_id INTEGER,
    group_id INTEGER,                -- Variations: the id of the group's first job
    source_song_id INTEGER           -- a Final: the Draft it was made from
);
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    dir TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    audio_seconds REAL,
    created_at REAL NOT NULL,
    starred INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
"""

# A v1 database's tables need the v2 columns (CREATE TABLE IF NOT EXISTS won't add them).
MIGRATE_1_TO_2 = [
    "ALTER TABLE jobs ADD COLUMN group_id INTEGER",
    "ALTER TABLE jobs ADD COLUMN source_song_id INTEGER",
    "ALTER TABLE songs ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
]


class Store:
    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if 0 < version < 2:
                self._migrate(MIGRATE_1_TO_2, 2)
            with self._conn:
                self._conn.executescript(SCHEMA)
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate(self, statements: list[str], version: int) -> None:
        """Run a migration and set the schema version in one transaction: SQLite rolls back DDL
        too, so an interrupted migration leaves the old schema, never half of the new one."""
        self._conn.execute("BEGIN")
        try:
            for statement in statements:
                self._conn.execute(statement)
            self._conn.execute(f"PRAGMA user_version = {version}")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def close(self) -> None:
        self._conn.close()

    def create_job(
        self, request: dict[str, Any], source_song_id: int | None = None
    ) -> dict[str, Any]:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO jobs (status, request_json, created_at, source_song_id) "
                "VALUES ('queued', ?, ?, ?)",
                (json.dumps(request), time.time(), source_song_id),
            )
            job_id = cur.lastrowid
        return self.get_job(job_id)

    def create_group(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Queue Variations in one transaction; every member's `group_id` is the first job's id."""
        now = time.time()
        with self._lock, self._conn:
            ids = [
                self._conn.execute(
                    "INSERT INTO jobs (status, request_json, created_at) VALUES ('queued', ?, ?)",
                    (json.dumps(request), now),
                ).lastrowid
                for request in requests
            ]
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE jobs SET group_id = ? WHERE id IN ({placeholders})", (ids[0], *ids)
            )
        return [self.get_job(job_id) for job_id in ids]

    def list_group(self, group_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                f"{JOB_SELECT} WHERE j.group_id = ? ORDER BY j.id", (group_id,)
            ).fetchall()
        return [_job(r) for r in rows]

    def finals_of(self, song_id: int) -> list[dict[str, Any]]:
        """Jobs making a Final of this song, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                f"{JOB_SELECT} WHERE j.source_song_id = ? ORDER BY j.id", (song_id,)
            ).fetchall()
        return [_job(r) for r in rows]

    def set_starred(self, song_id: int, starred: bool) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE songs SET starred = ? WHERE id = ?", (int(starred), song_id)
            )
        return cur.rowcount > 0

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(f"{JOB_SELECT} WHERE j.id = ?", (job_id,)).fetchone()
        return _job(row) if row else None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(f"{JOB_SELECT} ORDER BY j.id DESC").fetchall()
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
            rows = self._conn.execute(f"{SONG_SELECT} ORDER BY s.id DESC").fetchall()
        return [_song(r) for r in rows]

    def delete_song(self, song_id: int) -> dict[str, Any] | None:
        """Remove a song and the job that made it; returns the deleted song, or None."""
        with self._lock, self._conn:
            row = self._conn.execute(f"{SONG_SELECT} WHERE s.id = ?", (song_id,)).fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (row["job_id"],))
        return _song(row)

    def get_song(self, song_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(f"{SONG_SELECT} WHERE s.id = ?", (song_id,)).fetchone()
        return _song(row) if row else None

    def get_setting(self, key: str) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value_json"]) if row else None

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (key, json.dumps(value)),
            )

    def _update(self, job_id: int, assignments: str, *values: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values, job_id))


JOB_SELECT = (
    "SELECT j.*, s.audio_seconds, s.starred FROM jobs j LEFT JOIN songs s ON s.id = j.song_id"
)
SONG_SELECT = (
    "SELECT s.*, j.request_json, j.group_id, j.source_song_id "
    "FROM songs s JOIN jobs j ON j.id = s.job_id"
)


def _job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["request"] = json.loads(job.pop("request_json"))
    job["starred"] = bool(job["starred"])
    return job


def _song(row: sqlite3.Row) -> dict[str, Any]:
    song = dict(row)
    song["request"] = json.loads(song.pop("request_json"))
    song["starred"] = bool(song["starred"])
    return song
