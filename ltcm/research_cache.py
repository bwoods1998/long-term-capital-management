"""Restart-safe reuse of exact, successful historical experiments; never new evidence.

Keys include the engine, runner, complete experiment specification and split policy. A short
TTL lets late venue corrections reach repeated historical windows. Failed runs are not saved.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping


class ResearchCache:
    def __init__(self, path: Path, *, engine: str, ttl_seconds: float = 3600, clock=time.time):
        self.path, self.engine, self.ttl, self.clock = path, engine, ttl_seconds, clock

    def key(self, spec: Mapping[str, Any], fraction: float) -> str:
        body = json.dumps({"engine": self.engine, "spec": spec, "fraction": fraction}, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(body.encode()).hexdigest()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, at REAL NOT NULL, report TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, subject TEXT NOT NULL, at REAL NOT NULL, body TEXT NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS experiments_subject_at ON experiments(subject,at)")
        return db

    def remember(self, candidate: Mapping[str, Any], window: Mapping[str, Any]) -> None:
        """Save successes AND failures with source, including work interrupted mid-cycle."""
        body = json.dumps({**candidate, "window": dict(window)}, allow_nan=False, default=str)
        db = self._connect()
        try:
            with db:
                db.execute("INSERT OR REPLACE INTO experiments VALUES (?,?,?,?)", (candidate["id"], candidate["subject"], self.clock(), body))
                db.execute("DELETE FROM experiments WHERE id IN (SELECT id FROM experiments ORDER BY at DESC LIMIT -1 OFFSET 5000)")
        finally:
            db.close()

    def lessons(self, subject: str, limit: int = 8) -> list[dict[str, Any]]:
        db = self._connect()
        try:
            rows = db.execute("SELECT body FROM experiments WHERE subject=? ORDER BY at DESC LIMIT 80", (subject,)).fetchall()
        finally:
            db.close()
        out, seen = [], set()
        for (body,) in rows:
            candidate = json.loads(body)
            if candidate.get("kind") == "baseline" or not (candidate.get("report") or candidate.get("error")):
                continue
            signature = hashlib.sha256(json.dumps({"code": candidate.get("code"), "params": candidate.get("params")}, sort_keys=True).encode()).hexdigest()
            if signature in seen:
                continue
            seen.add(signature)
            out.append({"hypothesis": candidate.get("hypothesis") or candidate.get("label"), "params": candidate.get("params"),
                        "error": candidate.get("error"), "evidence": candidate.get("evidence"), "window": candidate.get("window"),
                        "profile": candidate.get("profile"), "cached": bool(candidate.get("cache_hit"))})
            if len(out) >= limit:
                break
        return out

    def get(self, key: str) -> dict[str, Any] | None:
        db = self._connect()
        try:
            row = db.execute("SELECT at,report FROM results WHERE key=?", (key,)).fetchone()
            if row is None or not 0 <= self.clock() - row[0] < self.ttl:
                return None
            value = json.loads(row[1])
            return value if isinstance(value, dict) and value.get("errors") == 0 and not value.get("unsupported") else None
        finally:
            db.close()

    def put(self, key: str, report: Mapping[str, Any]) -> None:
        if report.get("errors") != 0 or report.get("unsupported"):
            return
        body = json.dumps(dict(report), allow_nan=False)
        db = self._connect()
        try:
            with db:
                db.execute("INSERT OR REPLACE INTO results VALUES (?,?,?)", (key, self.clock(), body))
                db.execute("DELETE FROM results WHERE at < ?", (self.clock() - self.ttl,))
        finally:
            db.close()
