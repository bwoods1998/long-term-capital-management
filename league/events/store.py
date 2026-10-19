"""The event lane's store: `events.sqlite` and the document files under one state root.

Records are appended and never rewritten; a row's `status` only moves forward. Times are ISO 8601 UTC strings ending in
`Z`; days are New York session dates (`YYYY-MM-DD`). Event ids: `8k:<accession>`, `f4:<accession>`, `news:<id>`.
Documents (the raw bytes a recorder fetched) live gzip-compressed at `<root>/docs/<sha[:2]>/<sha>.gz`, keyed by the
SHA-256 of the uncompressed bytes, so a verdict can cite exactly what it read.

The schema is pinned in goal-2026-10-19/EVL-DESIGN.md ("The store"); `SCHEMA_VERSION` moves with any change to it.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA_VERSION = 1
DB_NAME = "events.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS filings(accession TEXT PRIMARY KEY, form TEXT NOT NULL, cik TEXT NOT NULL, company TEXT,
  items TEXT, accepted_at TEXT NOT NULL, knowable_at TEXT NOT NULL, received_at TEXT NOT NULL, source TEXT NOT NULL,
  index_url TEXT, doc_url TEXT, doc_kind TEXT, text_sha TEXT, text_len INTEGER, raw_sha TEXT, status TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS filings_knowable ON filings(form, knowable_at);
CREATE INDEX IF NOT EXISTS filings_cik ON filings(cik, accepted_at);
CREATE TABLE IF NOT EXISTS documents(sha TEXT PRIMARY KEY, kind TEXT NOT NULL, bytes INTEGER NOT NULL,
  path TEXT NOT NULL, stored_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS form4_owners(accession TEXT NOT NULL, owner_cik TEXT NOT NULL, owner_name TEXT,
  is_director INTEGER, is_officer INTEGER, officer_title TEXT, is_ten_pct INTEGER, PRIMARY KEY(accession, owner_cik));
CREATE TABLE IF NOT EXISTS form4_tx(accession TEXT NOT NULL, seq INTEGER NOT NULL, security TEXT, tx_date TEXT,
  code TEXT, shares REAL, price REAL, acquired TEXT, owned_after REAL, PRIMARY KEY(accession, seq));
CREATE TABLE IF NOT EXISTS news(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT, received_at TEXT NOT NULL,
  knowable_at TEXT NOT NULL, source TEXT, headline TEXT, summary TEXT, symbols TEXT, live INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS news_knowable ON news(knowable_at);
CREATE TABLE IF NOT EXISTS sessions(day TEXT PRIMARY KEY, open_at TEXT NOT NULL, close_at TEXT NOT NULL,
  early INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS universe(day TEXT NOT NULL, symbol TEXT NOT NULL, cik TEXT NOT NULL, name TEXT, exchange TEXT,
  prev_close REAL, adv20 REAL, bench TEXT, sigma60 REAL, PRIMARY KEY(day, symbol));
CREATE INDEX IF NOT EXISTS universe_cik ON universe(day, cik);
CREATE TABLE IF NOT EXISTS cik_info(cik TEXT PRIMARY KEY, sic TEXT, periodic_form TEXT, periodic_at TEXT,
  operating INTEGER, checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS verdicts(event TEXT NOT NULL, prompt_sha TEXT NOT NULL, model TEXT NOT NULL, request_id TEXT,
  asked_at TEXT, answered_at TEXT, status TEXT NOT NULL, score INTEGER, guidance TEXT, answer TEXT, usd REAL,
  PRIMARY KEY(event, prompt_sha, model));
CREATE TABLE IF NOT EXISTS intents(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
  symbol TEXT NOT NULL, cik TEXT, decided_at TEXT NOT NULL, entry_day TEXT NOT NULL, entry_at TEXT NOT NULL,
  exit_day TEXT NOT NULL, exit_at TEXT NOT NULL, rank_key REAL, mode TEXT NOT NULL, status TEXT NOT NULL, why TEXT,
  PRIMARY KEY(program, version, event));
CREATE INDEX IF NOT EXISTS intents_entry ON intents(program, version, entry_day);
CREATE TABLE IF NOT EXISTS outcomes(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL, entry_px REAL,
  exit_px REAL, bench TEXT, bench_entry REAL, bench_exit REAL, cost_entry_bp REAL, cost_exit_bp REAL, r REAL, b REAL,
  a REAL, spread_entry_bp REAL, spread_exit_bp REAL, stress_r REAL, tradable INTEGER, settled_at TEXT NOT NULL,
  status TEXT NOT NULL, PRIMARY KEY(program, version, event));
CREATE TABLE IF NOT EXISTS looks(program TEXT NOT NULL, version INTEGER NOT NULL, k INTEGER NOT NULL, at TEXT NOT NULL,
  sessions INTEGER, n INTEGER, issuers INTEGER, blocks INTEGER, mean_a REAL, mean_r REAL, mean_a_tradable REAL,
  p REAL, alpha REAL, fp_check REAL, held INTEGER NOT NULL, passed INTEGER NOT NULL, why TEXT,
  PRIMARY KEY(program, version, k));
CREATE TABLE IF NOT EXISTS bars(symbol TEXT NOT NULL, day TEXT NOT NULL, adj TEXT NOT NULL, o REAL, h REAL, l REAL,
  c REAL, v REAL, fetched_at TEXT NOT NULL, PRIMARY KEY(symbol, day, adj));
CREATE TABLE IF NOT EXISTS marks(symbol TEXT NOT NULL, day TEXT NOT NULL, label TEXT NOT NULL, px REAL, t TEXT,
  source TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(symbol, day, label));
CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT, summary TEXT);
"""

#: The forward-only order of an intent's status (a `skipped:<why>` is terminal like `exited`).
INTENT_ORDER = {"planned": 0, "entered": 1, "exited": 2}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(moment: dt.datetime) -> str:
    """ISO 8601 UTC with a `Z`, to the second (the store's one time format)."""
    if moment.tzinfo is None:
        raise ValueError("a naive datetime has no place in the store")
    return moment.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(text: str) -> dt.datetime:
    """The inverse of `iso` (also accepts an explicit offset)."""
    value = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError(f"not an aware time: {text!r}")
    return value.astimezone(dt.timezone.utc)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Store:
    """One state root: `events.sqlite` plus `docs/`. Open it with `Store(root)`; close with `close()` or a `with`."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(exist_ok=True)
        self.db = sqlite3.connect(str(self.root / DB_NAME), timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        have = self.meta("schema_version")
        if have is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        elif int(have) != SCHEMA_VERSION:
            raise RuntimeError(f"events.sqlite schema {have} is not this code's {SCHEMA_VERSION}")

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """One transaction (BEGIN IMMEDIATE ... COMMIT, rolled back on any exception)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # -- meta -------------------------------------------------------------------------------------------------------
    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value))

    # -- documents --------------------------------------------------------------------------------------------------
    def put_document(self, data: bytes, kind: str, *, now: dt.datetime | None = None) -> str:
        """Store raw bytes once (idempotent); returns their SHA-256."""
        digest = sha256(data)
        rel = Path("docs") / digest[:2] / f"{digest}.gz"
        path = self.root / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wb") as out:
                out.write(data)
            os.replace(tmp, path)
        self.db.execute("INSERT OR IGNORE INTO documents(sha, kind, bytes, path, stored_at) VALUES(?, ?, ?, ?, ?)",
                        (digest, kind, len(data), str(rel), iso(now or utc_now())))
        return digest

    def get_document(self, digest: str) -> bytes:
        row = self.db.execute("SELECT path FROM documents WHERE sha=?", (digest,)).fetchone()
        if row is None:
            raise KeyError(digest)
        with gzip.open(self.root / row["path"], "rb") as src:
            data = src.read()
        if sha256(data) != digest:
            raise RuntimeError(f"document {digest} does not match its digest")
        return data

    # -- receipts ---------------------------------------------------------------------------------------------------
    def start_receipt(self, job: str, *, now: dt.datetime | None = None) -> int:
        cur = self.db.execute("INSERT INTO receipts(job, started_at, status) VALUES(?, ?, 'running')",
                              (job, iso(now or utc_now())))
        return int(cur.lastrowid)

    def finish_receipt(self, rid: int, status: str, summary: Mapping[str, Any] | None = None, *,
                       now: dt.datetime | None = None) -> None:
        self.db.execute("UPDATE receipts SET finished_at=?, status=?, summary=? WHERE id=?",
                        (iso(now or utc_now()), status, json.dumps(summary or {}, sort_keys=True, default=str), rid))

    # -- intents (forward-only status) ------------------------------------------------------------------------------
    def move_intent(self, program: str, version: int, event: str, status: str, why: str | None = None) -> bool:
        """Move an intent's status forward; a move backward or out of a terminal state is refused (False)."""
        row = self.db.execute("SELECT status FROM intents WHERE program=? AND version=? AND event=?",
                              (program, version, event)).fetchone()
        if row is None:
            raise KeyError((program, version, event))
        old = str(row["status"])
        if old.startswith("skipped") or old == "exited":
            return False
        if not status.startswith("skipped") and INTENT_ORDER.get(status, -1) <= INTENT_ORDER.get(old, -1):
            return False
        self.db.execute("UPDATE intents SET status=?, why=COALESCE(?, why) WHERE program=? AND version=? AND event=?",
                        (status, why, program, version, event))
        return True


__all__ = ["Store", "SCHEMA", "SCHEMA_VERSION", "iso", "parse_iso", "sha256", "utc_now", "INTENT_ORDER"]
