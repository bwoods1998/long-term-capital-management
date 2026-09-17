"""Append-only, hash-chained event log shared by every Long Term Capital Management component.

One SQLite file holds every stream. Each stream is its own hash chain: an event's digest covers
its identity, content and the previous digest in the same stream, so any edit or deletion is
detectable by `EventLog.verify()`. Rows can never be updated or deleted (triggers enforce it).

Identity is idempotent: appending an event whose `id` already exists returns the stored event when
the content matches and raises `EventConflict` when it does not. Callers derive ids from their own
durable identities (an intent id, a request id, a session id plus a counter) so a crash and retry
never produces a duplicate.

Payload keys beginning with an underscore are private. `public_view()` strips them, and the
`public` flag on the row says whether the event may leave the box at all.
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
from typing import Any, Iterator

GENESIS = "genesis"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    stream TEXT NOT NULL,
    kind TEXT NOT NULL,
    at TEXT NOT NULL,
    public INTEGER NOT NULL,
    payload TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    digest TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS events_stream ON events(stream, seq);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, seq);
CREATE INDEX IF NOT EXISTS events_fill_desk ON events(json_extract(payload, '$.desk_id'), seq)
    WHERE kind = 'broker.fill';
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;
"""

# kind -> default publicity. "deferred" events are stored private and released by the publisher
# once the related order is terminal.
KINDS: dict[str, str] = {
    "desk.session_started": "public",
    "desk.thought": "public",
    "desk.tool_call": "public",
    "desk.tool_result": "public",
    "desk.memo": "public",
    "desk.intent": "deferred",
    "desk.playbook_updated": "public",
    "desk.postmortem": "public",
    "desk.outcome": "public",
    "desk.session_ended": "public",
    "desk.watch": "public",  # leap: watch
    "desk.exit_plan": "public",  # leap: exits
    "desk.code_run": "public",  # leap: sandbox
    "risk.decision": "public",
    "risk.review": "public",
    "risk.breaker": "public",
    "broker.order": "deferred",
    "broker.fill": "public",
    "broker.reconciled": "public",
    "ledger.mark": "public",
    # The floor's own balance: the venue accounts added up, marked on the `ops` stream because
    # it belongs to the whole floor rather than to any one desk's ledger.
    "floor.mark": "public",
    "committee.allocation": "public",
    "committee.memo": "public",
    "committee.gate": "public",
    "evolution.spawned": "public",
    "evolution.retired": "public",
    "evolution.promoted": "public",
    # leap: founding -- the floor opened a new family (`ltcm/founding.py`).
    "evolution.founded": "public",
    "lab.hypothesis": "public",
    "lab.result": "public",
    "lab.progress": "public",
    # leap: lab -- forecasts and their scoring, and the lab's directed experiments.
    "desk.forecast": "public",
    "lab.calibration": "public",
    "lab.experiment": "public",
    "lab.verdict": "public",
    # The fact that a market resolved, recorded once so a venue is asked once. Never published:
    # the public record of a resolution is the desk.outcome or the lab.calibration it feeds.
    "lab.resolution": "private",
    "ops.alert": "public",
    "ops.budget": "public",
    "provider.request": "private",
}

STREAM_PREFIXES = ("desk:", "ledger:", "broker:")
FIXED_STREAMS = ("risk", "committee", "evolution", "lab", "ops")


class EventError(ValueError):
    """Invalid event content or stream."""


class EventConflict(EventError):
    """An id was reused with different content."""


class ChainBroken(EventError):
    """Verification found an edited, missing or reordered event."""


def canonical(value: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, no NaN, unicode preserved."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def now_iso(clock=time.time) -> str:
    """UTC timestamp with millisecond precision, e.g. 2026-09-14T22:00:00.123Z."""
    t = clock()
    whole = time.gmtime(t)
    millis = int(round((t - int(t)) * 1000))
    if millis == 1000:  # rounding at the edge of a second
        millis = 999
    return time.strftime("%Y-%m-%dT%H:%M:%S", whole) + f".{millis:03d}Z"


def valid_stream(stream: str) -> bool:
    if not isinstance(stream, str) or not 1 <= len(stream) <= 120:
        return False
    if stream in FIXED_STREAMS:
        return True
    return any(
        stream.startswith(prefix) and len(stream) > len(prefix) for prefix in STREAM_PREFIXES
    )


def public_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop private (underscore-prefixed) keys, recursively."""
    if not isinstance(payload, dict):
        return payload
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(key, str) and key.startswith("_"):
            continue
        if isinstance(value, dict):
            out[key] = public_view(value)
        elif isinstance(value, list):
            out[key] = [public_view(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


def digest_for(
    event_id: str, stream: str, kind: str, at: str, public: bool, payload: str, previous: str
) -> str:
    material = canonical(
        {
            "id": event_id,
            "stream": stream,
            "kind": kind,
            "at": at,
            "public": bool(public),
            "payload": payload,
            "previous_hash": previous,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    seq: int
    id: str
    stream: str
    kind: str
    at: str
    public: bool
    payload: dict[str, Any]
    previous_hash: str
    digest: str

    def public_payload(self) -> dict[str, Any]:
        return public_view(self.payload)

    def to_public(self) -> dict[str, Any]:
        """The shape the site receives. Never includes private keys."""
        return {
            "seq": self.seq,
            "id": self.id,
            "stream": self.stream,
            "kind": self.kind,
            "at": self.at,
            "payload": self.public_payload(),
            "digest": self.digest,
        }


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        seq=row["seq"],
        id=row["id"],
        stream=row["stream"],
        kind=row["kind"],
        at=row["at"],
        public=bool(row["public"]),
        payload=json.loads(row["payload"]),
        previous_hash=row["previous_hash"],
        digest=row["digest"],
    )


class EventLog:
    """Thread-safe append-only log. One instance per process per file."""

    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False, timeout=30
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    # ------------------------------------------------------------------ writes
    def append(
        self,
        stream: str,
        kind: str,
        payload: dict[str, Any],
        *,
        id: str | None = None,
        public: bool | None = None,
        at: str | None = None,
    ) -> Event:
        """Append one event. Idempotent on `id`. Returns the stored event."""
        if not valid_stream(stream):
            raise EventError(f"invalid stream {stream!r}")
        if kind not in KINDS:
            raise EventError(f"unknown event kind {kind!r}")
        if not isinstance(payload, dict):
            raise EventError("payload must be a dict")
        if public is None:
            public = KINDS[kind] == "public"
        try:
            text = canonical(payload)
        except (TypeError, ValueError) as exc:
            raise EventError(f"payload is not canonical JSON: {exc}") from exc
        if len(text) > 200_000:
            raise EventError("payload exceeds 200000 bytes")
        event_id = id or f"ev-{uuid.uuid4()}"
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 200:
            raise EventError("invalid event id")
        stamp = at or now_iso(self.clock)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                existing = self._db.execute(
                    "SELECT * FROM events WHERE id = ?", (event_id,)
                ).fetchone()
                if existing is not None:
                    same = (
                        existing["stream"] == stream
                        and existing["kind"] == kind
                        and existing["payload"] == text
                        and bool(existing["public"]) == bool(public)
                    )
                    self._db.execute("COMMIT")
                    if same:
                        return _row_to_event(existing)
                    raise EventConflict(f"event {event_id} exists with different content")
                previous = self._db.execute(
                    "SELECT digest FROM events WHERE stream = ? ORDER BY seq DESC LIMIT 1",
                    (stream,),
                ).fetchone()
                previous_hash = previous["digest"] if previous else GENESIS
                digest = digest_for(event_id, stream, kind, stamp, public, text, previous_hash)
                self._db.execute(
                    "INSERT INTO events (id, stream, kind, at, public, payload, previous_hash, digest)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_id, stream, kind, stamp, int(bool(public)), text, previous_hash, digest),
                )
                row = self._db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
                self._db.execute("COMMIT")
            except Exception:
                try:
                    self._db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        return _row_to_event(row)

    # ------------------------------------------------------------------- reads
    # Every read runs its statement and fetches its rows under `_lock`, the lock `append` holds
    # from BEGIN to COMMIT. All threads share one connection: on Sept 16, 2026 two readers on it
    # at once got each other's rows (a `read(after=100)` answered from seq 451), rows with a
    # `seq` of None that wedged a ledger's cursor, and rows an append had not committed yet (and
    # then rolled back, its seq reused by a different event the cursor had already passed).
    # Decoding happens after the lock is released. Nothing is acquired while `_lock` is held, so
    # the only lock order is a caller's own lock (a ledger's, the gateway's), then this one.
    def _fetchone(self, sql: str, params: Any = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: Any = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def get(self, event_id: str) -> Event | None:
        row = self._fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
        return _row_to_event(row) if row else None

    def read(
        self,
        *,
        stream: str | None = None,
        kind: str | None = None,
        after: int = 0,
        limit: int = 1000,
        public_only: bool = False,
        newest: bool = False,
    ) -> list[Event]:
        """Events in sequence order. `newest=True` returns the LAST `limit` events (still oldest
        first): a reader folding state from a kind that has outgrown the clamp wants the recent
        tape, not the first ten thousand rows written years ago."""
        clauses = ["seq > ?"]
        params: list[Any] = [int(after)]
        if stream is not None:
            clauses.append("stream = ?")
            params.append(stream)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if public_only:
            clauses.append("public = 1")
        params.append(max(1, min(int(limit), 10_000)))
        order = "DESC" if newest else "ASC"
        rows = self._fetchall(
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY seq {order} LIMIT ?",
            params,
        )
        events = [_row_to_event(r) for r in rows]
        return events[::-1] if newest else events

    def read_ledger(self, desk_id: str, *, after: int = 0, limit: int = 2000) -> list[Event]:
        """Indexed economic tape for one book. Do not deserialize every thought on the floor
        once per desk, once per mode, on every checkpoint and capital decision."""
        rows = self._fetchall(
            "SELECT * FROM ("
            "SELECT * FROM events WHERE kind='committee.allocation' AND seq>? "
            "UNION ALL SELECT * FROM events WHERE kind='broker.fill' AND json_extract(payload, '$.desk_id')=? AND seq>? "
            "UNION ALL SELECT * FROM events WHERE kind='ledger.mark' AND stream=? AND seq>?"
            ") ORDER BY seq LIMIT ?",
            (after, desk_id, after, f"ledger:{desk_id}", after, max(1, min(int(limit), 10000))),
        )
        return [_row_to_event(r) for r in rows]

    def read_fills(self, desk_id: str, *, limit: int = 10000) -> list[Event]:
        rows = self._fetchall("SELECT * FROM events WHERE kind='broker.fill' AND json_extract(payload, '$.desk_id')=? ORDER BY seq DESC LIMIT ?",
                              (desk_id, max(1, min(int(limit), 10000))))
        return [_row_to_event(r) for r in reversed(rows)]

    def iter_all(self) -> Iterator[Event]:
        after = 0
        while True:
            batch = self.read(after=after, limit=5000)
            if not batch:
                return
            yield from batch
            after = batch[-1].seq

    def last(self, stream: str, kind: str | None = None) -> Event | None:
        if kind is None:
            row = self._fetchone(
                "SELECT * FROM events WHERE stream = ? ORDER BY seq DESC LIMIT 1", (stream,)
            )
        else:
            row = self._fetchone(
                "SELECT * FROM events WHERE stream = ? AND kind = ? ORDER BY seq DESC LIMIT 1",
                (stream, kind),
            )
        return _row_to_event(row) if row else None

    def count(self, stream: str | None = None) -> int:
        if stream is None:
            return self._fetchone("SELECT COUNT(*) FROM events")[0]
        return self._fetchone("SELECT COUNT(*) FROM events WHERE stream = ?", (stream,))[0]

    def streams(self) -> list[str]:
        rows = self._fetchall("SELECT DISTINCT stream FROM events ORDER BY stream")
        return [r["stream"] for r in rows]

    def latest_seq(self) -> int:
        row = self._fetchone("SELECT MAX(seq) AS m FROM events")
        return int(row["m"] or 0)

    # ------------------------------------------------------------- integrity
    def verify(self) -> int:
        """Recompute every digest and chain link. Returns the number of events checked."""
        previous: dict[str, str] = {}
        checked = 0
        for event in self.iter_all():
            expected_previous = previous.get(event.stream, GENESIS)
            if event.previous_hash != expected_previous:
                raise ChainBroken(f"{event.stream} seq {event.seq}: previous hash mismatch")
            text = canonical(event.payload)
            digest = digest_for(
                event.id, event.stream, event.kind, event.at, event.public, text, event.previous_hash
            )
            if digest != event.digest:
                raise ChainBroken(f"{event.stream} seq {event.seq}: digest mismatch")
            previous[event.stream] = event.digest
            checked += 1
        return checked

    def close(self) -> None:
        with self._lock:
            self._db.close()
