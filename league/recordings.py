"""Bounded, shared, timestamped recordings of newly fetched strategy market snapshots.

These are sampled REST views, not tick data or historical queue positions. Recording uses no
additional market requests. Content is compressed; retention evictions remain visible in stats.
The immutable experiment archive separately preserves any data used in an evaluated trial.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from .ledger import canonical


class Recorder:
    def __init__(self, path: str | Path, *, clock=time.time, max_bytes: int = 256 * 1024 * 1024,
                 retention_seconds: float = 7 * 86400):
        self.clock, self.max_bytes, self.retention = clock, max_bytes, retention_seconds
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots(
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, started REAL NOT NULL,
                received REAL NOT NULL, digest TEXT NOT NULL, payload BLOB NOT NULL);
            CREATE INDEX IF NOT EXISTS snapshots_time ON snapshots(received);
            CREATE TABLE IF NOT EXISTS recorder_meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            INSERT OR IGNORE INTO recorder_meta VALUES('evicted',0);
        """)

    def record(self, source: str, value: Any, *, started: float) -> int:
        raw = canonical(value).encode("utf-8")
        payload = gzip.compress(raw, mtime=0)
        if len(payload) > self.max_bytes:
            raise ValueError("snapshot exceeds recorder capacity")
        now = self.clock()
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                removed = self.db.execute("DELETE FROM snapshots WHERE received<?", (now - self.retention,)).rowcount
                used = self.db.execute("SELECT COALESCE(SUM(length(payload)),0) FROM snapshots").fetchone()[0]
                while used + len(payload) > self.max_bytes:
                    old = self.db.execute("SELECT id,length(payload) FROM snapshots ORDER BY id LIMIT 1").fetchone()
                    self.db.execute("DELETE FROM snapshots WHERE id=?", (old[0],))
                    used -= old[1]
                    removed += 1
                self.db.execute("UPDATE recorder_meta SET value=value+? WHERE key='evicted'", (removed,))
                ident = self.db.execute("INSERT INTO snapshots(source,started,received,digest,payload) VALUES(?,?,?,?,?)",
                    (source, started, now, hashlib.sha256(raw).hexdigest(), payload)).lastrowid
                self.db.execute("COMMIT")
                return ident
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def stats(self) -> dict[str, Any]:
        with self.lock:
            count, size, first, last = self.db.execute(
                "SELECT COUNT(*),COALESCE(SUM(length(payload)),0),MIN(received),MAX(received) FROM snapshots").fetchone()
            evicted = self.db.execute("SELECT value FROM recorder_meta WHERE key='evicted'").fetchone()[0]
        return {"kind": "sampled_rest_snapshots", "snapshots": count, "compressed_bytes": size,
                "first_received": first, "last_received": last, "evicted": evicted,
                "retention_seconds": self.retention, "max_payload_bytes": self.max_bytes}

    def close(self) -> None:
        with self.lock:
            self.db.close()
