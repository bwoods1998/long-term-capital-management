"""The live path's own state on the House's disk: the real book (SQLite) and the shadow books (one JSON file).

The options-swarm run, Wave 5 (Sept 26, 2026). `<root>/live.sqlite` holds what real money depends on, written BEFORE
anything is sent: every real order (its client order id, from its row id and the process's nonce, kept in its row: a restart never sends one twice:
an order found in the row with status `pending` or `unknown` is looked up at the venue by that id, never re-sent), every
position each family instance holds, every fill, the program each real instance runs (so an instance a band move or a
retirement took off the swarm's list can still close what it holds), and the key-values of the stops, the counters and
the latches. WAL, `synchronous=FULL`, one connection under one lock.

`<root>/live-shadow.json` holds the shadow books (the Gym's `Account` state), rewritten atomically each minute.
Programs and their parameters live here, never in git (the repository is public; programs are fitted to licensed data).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

#: The live state's file in the House's state root.
STATE_FILE = "live.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY, family TEXT NOT NULL, version INTEGER, run_sha TEXT, code TEXT NOT NULL, params TEXT NOT NULL,
    band TEXT, tuition INTEGER NOT NULL DEFAULT 0, mode TEXT NOT NULL DEFAULT 'live', created_at REAL NOT NULL,
    retired_at REAL, why TEXT);
CREATE TABLE IF NOT EXISTS positions (
    pid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, type TEXT NOT NULL, root TEXT NOT NULL,
    legs TEXT NOT NULL, qty INTEGER NOT NULL, opened_qty INTEGER NOT NULL, entry REAL NOT NULL, max_loss_share REAL NOT NULL,
    collateral REAL NOT NULL, fees REAL NOT NULL DEFAULT 0, cash REAL NOT NULL DEFAULT 0, opened_at REAL NOT NULL,
    opened_day TEXT NOT NULL, opened_minute INTEGER NOT NULL, tag TEXT, note TEXT, status TEXT NOT NULL,
    closed_at REAL, exit_value_qty REAL NOT NULL DEFAULT 0, reason TEXT, tuition INTEGER NOT NULL DEFAULT 0,
    info TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS orders (
    oid INTEGER PRIMARY KEY, client_id TEXT UNIQUE NOT NULL, venue_id TEXT, instance TEXT NOT NULL, family TEXT NOT NULL,
    action TEXT NOT NULL, type TEXT NOT NULL, root TEXT NOT NULL, legs TEXT NOT NULL, qty INTEGER NOT NULL,
    limit_value REAL NOT NULL, limit_price TEXT NOT NULL, tif INTEGER, placed_at REAL NOT NULL, day TEXT NOT NULL,
    placed_minute INTEGER NOT NULL, status TEXT NOT NULL, filled_qty INTEGER NOT NULL DEFAULT 0,
    fill_value REAL NOT NULL DEFAULT 0, pid INTEGER, forced INTEGER NOT NULL DEFAULT 0, reserve REAL NOT NULL DEFAULT 0,
    max_loss REAL NOT NULL DEFAULT 0, fees_est REAL NOT NULL DEFAULT 0, tuition INTEGER NOT NULL DEFAULT 0, why TEXT,
    answer TEXT, updated_at REAL NOT NULL, cancel_sent REAL, attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS orders_status ON orders(status);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT, oid INTEGER NOT NULL, pid INTEGER, qty INTEGER NOT NULL, value REAL NOT NULL,
    fees REAL NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
    payload TEXT NOT NULL);
"""


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def loads(text: Any, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


class LiveState:
    """`<root>/live.sqlite` (the module docstring)."""

    def __init__(self, path: str | Path, *, clock: Any = time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        self._depth = 0
        #: Drawn at every process start and never stored: part of every client order id, so neither a new state nor one
        #: rolled back (a Sail checkpoint restored with its old row ids) sends an id the venue has seen (it refuses a
        #: duplicate, and a lookup by it would find the old order). Each order row keeps its own id for lookups.
        self.nonce = os.urandom(4).hex()

    def close(self) -> None:
        with self.lock:
            self.db.close()

    # ------------------------------------------------------------------ key-values
    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return loads(row["value"], default) if row else default

    def put(self, key: str, value: Any) -> None:
        with self.lock:
            self.db.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (key, dumps(value)))

    def event(self, kind: str, payload: Mapping[str, Any]) -> None:
        with self.lock:
            self.db.execute("INSERT INTO events(at, kind, payload) VALUES(?,?,?)", (self.clock(), kind, dumps(payload)))

    def events(self, *, kinds: Iterable[str] | None = None, limit: int = 200) -> list[dict]:
        with self.lock:
            if kinds:
                names = list(kinds)
                rows = self.db.execute(f"SELECT * FROM events WHERE kind IN ({','.join('?' * len(names))}) ORDER BY seq DESC LIMIT ?",
                                       (*names, limit)).fetchall()
            else:
                rows = self.db.execute("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "payload": loads(r["payload"], {})} for r in rows]

    # ------------------------------------------------------------------ rows
    def upsert(self, table: str, row: Mapping[str, Any], key: str) -> None:
        cols = list(row)
        with self.lock:
            self.db.execute(
                f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
                f"ON CONFLICT({key}) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols if c != key)}",
                [row[c] for c in cols])

    def rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, tuple(params)).fetchall()]

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.db.execute(sql, tuple(params))

    def transaction(self) -> "_Tx":
        return _Tx(self)


class _Tx:
    """One transaction; a transaction opened inside another joins it (only the outermost commits or rolls back)."""

    def __init__(self, state: LiveState):
        self.state = state

    def __enter__(self) -> LiveState:
        self.state.lock.acquire()
        depth = getattr(self.state, "_depth", 0)
        if depth == 0:
            self.state.db.execute("BEGIN IMMEDIATE")
        self.state._depth = depth + 1
        return self.state

    def __exit__(self, kind: Any, value: Any, tb: Any) -> None:
        try:
            self.state._depth -= 1
            if self.state._depth == 0:
                self.state.db.execute("COMMIT" if kind is None else "ROLLBACK")
        finally:
            self.state.lock.release()


def write_json_atomic(path: str | Path, value: Any) -> None:
    """Temp file in the same directory, fsync, `os.replace`, mode 0600."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


__all__ = ["STATE_FILE", "LiveState", "write_json_atomic", "read_json", "dumps", "loads"]
