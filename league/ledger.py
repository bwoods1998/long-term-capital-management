"""The House ledger: one append-only, hash-chained record of everything that decides an agent's fate.

Every intent, order, fill, mark, credit move, trial and verdict is one row. Rows are chained: a
row's digest covers its identity, its content and the digest of the row before it, so an edit, a
deletion or a reordering anywhere is found by `Ledger.verify()`. SQLite triggers refuse UPDATE
and DELETE outright. Only the House process opens this file for writing; agents run in other
boxes, hold no path to it, and are given `agent_view()` rows, never a handle.

Identity is idempotent: appending an id that already exists returns the stored row when the
content matches and raises `LedgerConflict` when it does not, so a crash and a retry never
record a fill or a charge twice. Callers derive ids from their own durable identities.

Payload keys beginning with an underscore are private and are stripped by `public_view()`; the
`public` flag on a row says whether it may leave the box at all.

The mechanics (canonical JSON, digest, immutability triggers, single shared connection under
one lock) are the ones `ltcm/events.py` ran in production for the first run.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

GENESIS = "genesis"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    agent TEXT NOT NULL,
    at TEXT NOT NULL,
    public INTEGER NOT NULL,
    payload TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    digest TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS ledger_kind ON ledger(kind, seq);
CREATE INDEX IF NOT EXISTS ledger_agent ON ledger(agent, seq);
CREATE INDEX IF NOT EXISTS ledger_agent_kind ON ledger(agent, kind, seq);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
    BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
    BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
"""

#: The agent column of a row that belongs to the House rather than to one agent.
HOUSE = "house"

#: kind -> whether the row is public by default. A kind not listed here cannot be written.
KINDS: dict[str, bool] = {
    # An agent's life.
    "agent.born": True,
    "agent.strategy": True,  # a strategy version adopted: code hash, params, generation
    "agent.woke": True,
    "agent.thought": True,
    "agent.research": True,
    "agent.intent": True,
    "agent.forked": True,
    "agent.died": True,
    "agent.postmortem": True,
    # The netting book.
    "book.baseline": True,  # what the venue account held that is not the book's
    "book.stake": True,  # capital the House lends an agent on a book
    "book.refused": True,  # an intent the risk rules turned away
    "book.order": True,
    "book.cancel": True,
    "book.fill": True,  # a venue fill attributed to one agent
    "book.cross": True,  # two agents' opposite intents netted inside the House
    "book.settle": True,  # a Kalshi market resolved
    "book.mark": True,  # one agent's equity on one book
    "book.reconciled": True,
    "floor.mark": True,  # the real venue accounts added up
    # The evaluator.
    "eval.trial": True,  # one replay: every one is counted
    "eval.block": True,  # one forward observation of after-cost log growth
    "eval.verdict": True,  # promotion, demotion or death, with the statistics that decided it
    "eval.drift": True,
    # The economy.
    "credit.grant": True,
    "credit.charge": True,
    "credit.transfer": True,
    # The frontier model's jobs.
    "audit.verdict": True,
    "audit.counterfactual": True,
    "astra.pass": True,  # one architect, toolsmith, operator, designer or teacher pass
    "astra.change": True,  # a pull request it opened and what CI said
    # The commons.
    "library.note": True,
    "tool.request": True,
    "tool.fulfilled": True,
    "playbook.entry": True,
    # Operations.
    "ops.started": True,
    "ops.alert": True,
    "ops.budget": True,
    "ops.deploy": True,
    "ops.recommendation": True,
    "ops.constitution": True,  # the digest of the constitution the House started under
    "provider.request": False,  # a metered model call: private, the cost is what is public
}


class LedgerError(ValueError):
    """Invalid content."""


class LedgerConflict(LedgerError):
    """An id was reused with different content."""


class ChainBroken(LedgerError):
    """Verification found an edited, missing or reordered row."""


def canonical(value: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, no NaN, unicode preserved."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def now_iso(clock=time.time) -> str:
    """UTC timestamp with millisecond precision, e.g. 2026-09-20T13:00:00.123Z."""
    t = clock()
    millis = min(int(round((t - int(t)) * 1000)), 999)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{millis:03d}Z"


def public_view(payload: Any) -> Any:
    """Drop private (underscore-prefixed) keys, recursively."""
    if isinstance(payload, list):
        return [public_view(v) for v in payload]
    if not isinstance(payload, dict):
        return payload
    return {
        key: public_view(value)
        for key, value in payload.items()
        if not (isinstance(key, str) and key.startswith("_"))
    }


def digest_for(entry_id: str, kind: str, agent: str, at: str, public: bool, payload: str, previous: str) -> str:
    material = canonical(
        {
            "id": entry_id,
            "kind": kind,
            "agent": agent,
            "at": at,
            "public": bool(public),
            "payload": payload,
            "previous_hash": previous,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Entry:
    seq: int
    id: str
    kind: str
    agent: str
    at: str
    public: bool
    payload: dict[str, Any]
    previous_hash: str
    digest: str

    def to_public(self) -> dict[str, Any]:
        """The shape that may leave the box. Never includes private keys."""
        return {
            "seq": self.seq,
            "id": self.id,
            "kind": self.kind,
            "agent": self.agent,
            "at": self.at,
            "payload": public_view(self.payload),
            "digest": self.digest,
        }


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        seq=row["seq"],
        id=row["id"],
        kind=row["kind"],
        agent=row["agent"],
        at=row["at"],
        public=bool(row["public"]),
        payload=json.loads(row["payload"]),
        previous_hash=row["previous_hash"],
        digest=row["digest"],
    )


class Ledger:
    """Thread-safe append-only ledger. One instance per process per file."""

    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(SCHEMA)

    # ------------------------------------------------------------------ writes
    def append(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        agent: str = HOUSE,
        id: str | None = None,
        public: bool | None = None,
        at: str | None = None,
    ) -> Entry:
        """Append one row. Idempotent on `id`. Returns the stored row."""
        if kind not in KINDS:
            raise LedgerError(f"unknown ledger kind {kind!r}")
        if not isinstance(payload, dict):
            raise LedgerError("payload must be a dict")
        if not isinstance(agent, str) or not 1 <= len(agent) <= 120:
            raise LedgerError("invalid agent")
        if public is None:
            public = KINDS[kind]
        try:
            text = canonical(payload)
        except (TypeError, ValueError) as exc:
            raise LedgerError(f"payload is not canonical JSON: {exc}") from exc
        if len(text) > 200_000:
            raise LedgerError("payload exceeds 200000 bytes")
        entry_id = id or f"le-{uuid.uuid4()}"
        if not isinstance(entry_id, str) or not 1 <= len(entry_id) <= 200:
            raise LedgerError("invalid entry id")
        stamp = at or now_iso(self.clock)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute("SELECT * FROM ledger WHERE id = ?", (entry_id,)).fetchone()
                if existing is not None:
                    same = (
                        existing["kind"] == kind
                        and existing["agent"] == agent
                        and existing["payload"] == text
                        and bool(existing["public"]) == bool(public)
                    )
                    self._db.execute("COMMIT")
                    if same:
                        return _entry(existing)
                    raise LedgerConflict(f"ledger entry {entry_id} exists with different content")
                previous = self._db.execute("SELECT digest FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
                previous_hash = previous["digest"] if previous else GENESIS
                digest = digest_for(entry_id, kind, agent, stamp, public, text, previous_hash)
                self._db.execute(
                    "INSERT INTO ledger (id, kind, agent, at, public, payload, previous_hash, digest)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (entry_id, kind, agent, stamp, int(bool(public)), text, previous_hash, digest),
                )
                row = self._db.execute("SELECT * FROM ledger WHERE id = ?", (entry_id,)).fetchone()
                self._db.execute("COMMIT")
            except Exception:
                try:
                    self._db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        return _entry(row)

    # ------------------------------------------------------------------- reads
    # Every read runs and fetches under the lock `append` holds from BEGIN to COMMIT: all threads
    # share one connection, and two readers on it at once got each other's rows in the first run.
    def _all(self, sql: str, params: Any = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def _one(self, sql: str, params: Any = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(sql, params).fetchone()

    def get(self, entry_id: str) -> Entry | None:
        row = self._one("SELECT * FROM ledger WHERE id = ?", (entry_id,))
        return _entry(row) if row else None

    def read(
        self,
        *,
        kinds: Iterable[str] | str | None = None,
        agent: str | None = None,
        after: int = 0,
        limit: int = 1000,
        public_only: bool = False,
        newest: bool = False,
    ) -> list[Entry]:
        """Rows in sequence order. `newest=True` returns the LAST `limit` rows, still oldest first."""
        clauses = ["seq > ?"]
        params: list[Any] = [int(after)]
        if kinds is not None:
            wanted = [kinds] if isinstance(kinds, str) else sorted({str(k) for k in kinds})
            if not wanted:
                return []
            clauses.append(f"kind IN ({','.join('?' for _ in wanted)})")
            params.extend(wanted)
        if agent is not None:
            clauses.append("agent = ?")
            params.append(agent)
        if public_only:
            clauses.append("public = 1")
        params.append(max(1, min(int(limit), 10_000)))
        order = "DESC" if newest else "ASC"
        rows = self._all(
            f"SELECT * FROM ledger WHERE {' AND '.join(clauses)} ORDER BY seq {order} LIMIT ?", params
        )
        entries = [_entry(r) for r in rows]
        return entries[::-1] if newest else entries

    def iter(self, *, kinds: Iterable[str] | str | None = None, agent: str | None = None) -> Iterator[Entry]:
        """Every matching row, oldest first, in pages."""
        after = 0
        while True:
            batch = self.read(kinds=kinds, agent=agent, after=after, limit=5000)
            if not batch:
                return
            yield from batch
            after = batch[-1].seq

    def last(self, kind: str, *, agent: str | None = None) -> Entry | None:
        rows = self.read(kinds=kind, agent=agent, limit=1, newest=True)
        return rows[-1] if rows else None

    def count(self, *, kinds: Iterable[str] | str | None = None, agent: str | None = None) -> int:
        clauses, params = ["1=1"], []
        if kinds is not None:
            wanted = [kinds] if isinstance(kinds, str) else sorted({str(k) for k in kinds})
            if not wanted:
                return 0
            clauses.append(f"kind IN ({','.join('?' for _ in wanted)})")
            params.extend(wanted)
        if agent is not None:
            clauses.append("agent = ?")
            params.append(agent)
        return int(self._one(f"SELECT COUNT(*) FROM ledger WHERE {' AND '.join(clauses)}", params)[0])

    def head(self) -> tuple[int, str]:
        """The last sequence number and digest: what a reconciliation or a publication pins."""
        row = self._one("SELECT seq, digest FROM ledger ORDER BY seq DESC LIMIT 1")
        return (int(row["seq"]), row["digest"]) if row else (0, GENESIS)

    def agent_view(self, agent: str, *, after: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        """What one agent may read of the ledger: its own public rows, as plain data."""
        return [e.to_public() for e in self.read(agent=agent, after=after, limit=limit, public_only=True)]

    # ------------------------------------------------------------- integrity
    def verify(self) -> int:
        """Recompute every digest and chain link. Returns the number of rows checked."""
        previous = GENESIS
        checked = 0
        expected_seq = None
        for entry in self.iter():
            if entry.previous_hash != previous:
                raise ChainBroken(f"seq {entry.seq}: previous hash mismatch")
            digest = digest_for(
                entry.id, entry.kind, entry.agent, entry.at, entry.public, canonical(entry.payload), entry.previous_hash
            )
            if digest != entry.digest:
                raise ChainBroken(f"seq {entry.seq}: digest mismatch")
            if expected_seq is not None and entry.seq != expected_seq:
                raise ChainBroken(f"seq {entry.seq}: a row is missing before it")
            expected_seq = entry.seq + 1
            previous = entry.digest
            checked += 1
        return checked

    def close(self) -> None:
        with self._lock:
            self._db.close()
