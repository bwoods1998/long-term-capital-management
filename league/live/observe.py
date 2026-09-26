"""The observe band's trades, kept for the post-mortem: `<state>/observe.sqlite` (mode 0600).

The sprint (B4, Sept 26, 2026). An observe instance (`<family>@<version>:o`, `league/live/step.py`) trades the shadow book
on live quotes, and its trades are never a forward row (no evidence, no band, no site). They are kept HERE, one row a
trade, for Monday's post-mortem ("every real and shadow trade against the Gym's expectation"). Nothing public and nothing
that feeds evidence reads this file: not the swarm, the gate, the publisher or the money table.

Bounded: at most `MAX_ROWS` rows (the oldest go first). Each write is one transaction; a failure is caught, alerted once,
and never stops the minute (the trades stay in the shadow account and are offered again).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

FILE = "observe.sqlite"
MAX_ROWS = 50_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER,
    trade_id TEXT NOT NULL, day TEXT, pnl REAL, max_loss REAL, recorded_at REAL NOT NULL, body TEXT NOT NULL,
    UNIQUE(instance, trade_id));
CREATE INDEX IF NOT EXISTS trades_family ON trades(family, day);
"""


class ObserveStore:
    """`<state>/observe.sqlite` (the module docstring)."""

    def __init__(self, root: str | Path, *, alert: Callable[[str, str], Any] | None = None,
                 clock: Callable[[], float] = time.time, max_rows: int = MAX_ROWS):
        self.path = Path(root) / FILE
        self.alert, self.clock, self.max_rows = alert, clock, int(max_rows)
        self.db: sqlite3.Connection | None = None
        self.told = False

    def _connect(self) -> sqlite3.Connection:
        if self.db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            db = sqlite3.connect(str(self.path), timeout=0.05, isolation_level=None, check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(SCHEMA)
            self.db = db
        return self.db

    def add(self, instance: str, family: str, version: int | None, trades: Iterable[Mapping[str, Any]]) -> bool:
        """The trades of one observe instance, each once (by its id), in one transaction. False when not written."""
        rows = [(str(instance), str(family), version, str(t.get("id")), str(t.get("day") or ""), _num(t.get("pnl")),
                 _num(t.get("max_loss")), self.clock(), json.dumps(dict(t), sort_keys=True, default=str)) for t in trades]
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.executemany("INSERT OR IGNORE INTO trades(instance, family, version, trade_id, day, pnl, max_loss, "
                               "recorded_at, body) VALUES(?,?,?,?,?,?,?,?,?)", rows)
                over = int(db.execute("SELECT count(*) FROM trades").fetchone()[0]) - self.max_rows
                if over > 0:
                    db.execute("DELETE FROM trades WHERE seq IN (SELECT seq FROM trades ORDER BY seq LIMIT ?)", (over,))
            return True
        except Exception as exc:  # noqa: BLE001 - the post-mortem's record never stops the minute
            if not self.told and self.alert is not None:
                self.told = True
                try:
                    self.alert("warning", f"live: the observe band's trades could not be recorded ({type(exc).__name__}); "
                                          "they are offered again next minute")
                except Exception:  # noqa: BLE001
                    pass
            return False

    def close(self) -> None:
        try:
            if self.db is not None:
                self.db.close()
        except Exception:  # noqa: BLE001
            pass
        self.db = None


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["ObserveStore", "FILE", "MAX_ROWS"]
