"""Durable REST Voyage outbox; observability never owns/repeats inference.

Provision a Voyage once outside the guest and freeze its ID in run config. Each
producer needs a disjoint sequence range (one million events reserved here).
REST event fields/attribution mirror Sail's installed SDK and public Voyages API.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from .provider import ClosingConnection, Transport, canonical


class Voyage:
    def __init__(
        self,
        path,
        config,
        *,
        transport=None,
        agent_id="coordinator",
        sequence_start=1_000_000,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.id = config["voyage_id"]
        self.agent_id = agent_id
        self.sequence_start = sequence_start
        if not isinstance(self.id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{8,100}", self.id
        ):
            raise ValueError("Invalid Voyage identity")
        if not isinstance(agent_id, str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]{0,50}", agent_id
        ):
            raise ValueError("Invalid agent identity")
        if (
            type(sequence_start) is not int
            or not 1 <= sequence_start <= 2**53 - 1_000_000
        ):
            raise ValueError("Invalid sequence allocation")
        self.transport = transport or Transport(
            injected=config.get("injected_auth", False),
            key_fingerprint=config["key_fingerprint"],
            voyage_id=self.id,
        )
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS voyage_contract (id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS voyage_events (key TEXT PRIMARY KEY,sequence INTEGER UNIQUE NOT NULL,body TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0);
CREATE TRIGGER IF NOT EXISTS voyage_contract_immutable BEFORE UPDATE ON voyage_contract BEGIN SELECT RAISE(ABORT,'immutable trace identity'); END;
CREATE TRIGGER IF NOT EXISTS voyage_event_immutable BEFORE UPDATE OF key,sequence,body ON voyage_events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER IF NOT EXISTS voyage_no_delete BEFORE DELETE ON voyage_events BEGIN SELECT RAISE(ABORT,'immutable event history'); END;""")
            db.execute("BEGIN IMMEDIATE")
            frozen = canonical(
                {
                    "voyage_id": self.id,
                    "agent_id": agent_id,
                    "sequence_start": sequence_start,
                }
            )
            old = db.execute("SELECT body FROM voyage_contract WHERE id=1").fetchone()
            if old and old[0] != frozen:
                raise ValueError("Voyage producer identity changed")
            db.execute("INSERT OR IGNORE INTO voyage_contract VALUES(1,?)", (frozen,))
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def headers(self, span_id=None):
        result = {"X-Sail-Voyage-Id": self.id, "X-Sail-Voyage-Agent-Id": self.agent_id}
        if span_id:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", span_id):
                raise ValueError("Invalid span identity")
            result["X-Sail-Voyage-Span-Id"] = span_id
        return result

    def event(self, key, kind, payload=None, *, span_id=None):
        if (
            not isinstance(key, str)
            or not 1 <= len(key) <= 200
            or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,100}", kind)
        ):
            raise ValueError("Invalid event identity")
        payload = payload or {}
        if not isinstance(payload, dict) or len(canonical(payload).encode()) > 16000:
            raise ValueError("Bounded event payload required")
        if span_id:
            self.headers(span_id)
        base = {
            "source": "sdk",
            "kind": kind,
            "level": "error" if kind == "voyage.failed" else "info",
            "payload": payload,
            "agent_id": self.agent_id,
            "agent_name": self.agent_id,
            "agent_role": "research",
        }
        if span_id:
            base["span_id"] = span_id
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT body FROM voyage_events WHERE key=?", (key,)
            ).fetchone()
            if old:
                import json

                previous = json.loads(old[0])
                previous.pop("occurred_at")
                previous.pop("sequence_id")
                if previous != base:
                    raise ValueError("Event identity reused with different content")
                return
            if db.execute(
                "SELECT 1 FROM voyage_events WHERE json_extract(body,'$.kind') IN ('voyage.completed','voyage.failed')"
            ).fetchone():
                raise ValueError("Trace already locally terminal")
            last = db.execute("SELECT MAX(sequence) FROM voyage_events").fetchone()[0]
            seq = self.sequence_start if last is None else last + 1
            if seq >= self.sequence_start + 1_000_000:
                raise ValueError("Trace sequence allocation exhausted")
            body = {
                **base,
                "sequence_id": seq,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
            db.execute(
                "INSERT INTO voyage_events(key,sequence,body) VALUES(?,?,?)",
                (key, seq, canonical(body)),
            )

    def flush(self):
        """At most 64 retained events. Ambiguous delivery retries identical sequences."""
        import fcntl
        import json

        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.connect() as db:
                rows = db.execute(
                    "SELECT key,body FROM voyage_events WHERE delivered=0 ORDER BY sequence LIMIT 64"
                ).fetchall()
            if not rows:
                return True
            try:
                self.transport(
                    "POST",
                    "/v1/voyages/" + self.id + "/events",
                    {"events": [json.loads(r["body"]) for r in rows]},
                )
            except Exception:
                return False
            with self.connect() as db:
                db.executemany(
                    "UPDATE voyage_events SET delivered=1 WHERE key=?",
                    [(r["key"],) for r in rows],
                )
            return True
