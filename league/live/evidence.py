"""Private execution observations; never an authority for orders, bands or model fitting.

Only selected/working contracts are recorded. All entry points swallow observation failures. A durable pending
marker precedes each observation, so a failed write followed by a restart remains visible to the read-only report.
Session-minute coverage supplies the second witness when even that marker cannot be written. No existing records
are deleted: the 256 MiB combined database/WAL/SHM / 224 MiB payload / 100,000 events per session bounds stop collection.
An operator can archive a closed database; filling the recorder must never prevent an owned exit.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
import weakref
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

FILE = "live-execution.sqlite"
HEALTH = "live-execution-health.json"
MAX_BYTES = 224 * 1024 * 1024
MAX_DISK_BYTES = 256 * 1024 * 1024
DISK_HEADROOM = 4 * 1024 * 1024  # one maximal model + event, indexes, pending/failure markers, WAL/SHM overhead
MAX_EVENTS_DAY = 100_000
MAX_EVENT_BYTES = 64 * 1024
MAX_MODEL_BYTES = 1024 * 1024
QUOTE_STALE_SECONDS = 60.0  # diagnostic only; does not change quote admission or fills
NY = ZoneInfo("America/New_York")
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models(hash TEXT PRIMARY KEY, version TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, day TEXT NOT NULL, at REAL NOT NULL,
 source TEXT NOT NULL, kind TEXT NOT NULL, ident TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_day ON events(day,seq);
CREATE INDEX IF NOT EXISTS events_ident ON events(source,ident,seq);
CREATE TABLE IF NOT EXISTS coverage(day TEXT NOT NULL, minute INTEGER NOT NULL, complete INTEGER NOT NULL,
 PRIMARY KEY(day,minute));
CREATE TABLE IF NOT EXISTS gaps(day TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(day,reason));
"""


def number(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    # numpy scalar and Decimal values, never arbitrary object's repr (which could contain credentials).
    return number(value)


def dumps(value: Any) -> str:
    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def sample(day: Any, mi: int, root: str, legs: list[dict]) -> dict:
    """Called on the live minute writer after set_price; never from the concurrent publisher.

    Copy only these legs. The revision guard additionally refuses a torn geometry/quote copy. It is not a claim
    that quote_revision brackets underlying set_price: all recorder calls share that method's writer thread.
    """
    result = {"day": day.day.isoformat() if day is not None else None,
              "minute": day.open_min + mi if day is not None else None, "root": root, "spot": None,
              "status": "missing", "legs": []}
    chain = day.chains.get(root) if day is not None else None
    if chain is None or not 0 <= mi < chain.minutes:
        return result
    revision = chain.quote_revision
    if revision % 2:
        result["status"] = "concurrent_update"
        return result
    result["spot"] = number(chain.underlying.price[mi])
    for leg in legs:
        row = dict(leg)
        i = chain.column(str(leg["symbol"]))
        row.update(bid=None, ask=None, bid_size=None, ask_size=None, quote_at=None, received_at=None,
                   quote_time_raw=None, quote_time_status="missing")
        if i >= 0:
            row.update(key=int(chain.key[i]), strike=number(chain.strike[i]), is_call=bool(chain.is_call[i]),
                       dte=int(chain.dte[i]), expiry=(dt.date(1970, 1, 1) + dt.timedelta(days=int(chain.expiration[i]))).isoformat(),
                       bid=number(chain.bid[mi, i]), ask=number(chain.ask[mi, i]),
                       bid_size=int(chain.bid_size[mi, i]), ask_size=int(chain.ask_size[mi, i]),
                       quote_at=number(chain.quote_at[mi, i]), received_at=number(chain.received_at[mi, i]))
            row["quote_time_raw"] = chain.quote_time_raw[mi, i]
            row["quote_time_status"] = ("parsed" if row["quote_at"] is not None else
                                        "missing" if row["quote_time_raw"] is None else "invalid")
            row["bid_size_status"] = ("missing", "quoted", "invalid")[int(chain.bid_size_status[mi, i])]
            row["ask_size_status"] = ("missing", "quoted", "invalid")[int(chain.ask_size_status[mi, i])]
            row["observation_status"] = ("not_observed", "accepted", "missing_quote", "invalid_NBBO",
                                          "before_session", "crossed")[int(chain.observation_status[mi, i])]
            row["last_read_at"] = number(chain.last_read_at[mi, i])
            age = row["received_at"] - row["quote_at"] if row["received_at"] is not None and row["quote_at"] is not None else None
            row["quote_age_seconds"] = age
            row["stale"] = None if age is None else age > QUOTE_STALE_SECONDS
            row["future_dated"] = None if age is None else age < 0
        result["legs"].append(row)
    if revision != chain.quote_revision:
        result.update(status="concurrent_update", legs=[])
    else:
        result["status"] = "sampled" if result["legs"] and all(
            r["bid"] is not None and r["ask"] is not None for r in result["legs"]) else "missing"
    return result


def body_legs(body: Mapping[str, Any]) -> list[dict]:
    return [{"symbol": r["symbol"], "direction": 1 if r["side"] == "buy" else -1,
             "ratio": int(r.get("ratio_qty") or 1)} for r in (body.get("legs") or [body])]


class Evidence:
    def __init__(self, root: Path, *, clock: Callable[[], float] = time.time, alert: Callable[..., Any] | None = None,
                 context: Callable[[], Any] | None = None, max_bytes: int = MAX_BYTES,
                 max_events_day: int = MAX_EVENTS_DAY, max_disk_bytes: int = MAX_DISK_BYTES):
        self.root, self.path, self.clock = Path(root), Path(root) / FILE, clock
        self.alert, self.context = alert, context or (lambda: None)
        self.max_bytes, self.max_events_day = max_bytes, max_events_day
        self.max_disk_bytes = max_disk_bytes
        self.db: sqlite3.Connection | None = None
        self._finalizer = None
        self.model: dict | None = None
        self.engine: str | None = None
        self.failed: set[str] = set()
        self._seen: dict[tuple, str] = {}
        self._coverage: tuple[str, int] | None = None
        self._used = 0
        self._counts: dict[str, int] = {}
        self.run_id = uuid.uuid4().hex

    def _day(self) -> str:
        return dt.datetime.fromtimestamp(self.clock(), NY).date().isoformat()

    def _connect(self) -> sqlite3.Connection:
        if self.db is None:
            if self._finalizer is not None:
                self._finalizer()
                self._finalizer = None
            self.root.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            db = sqlite3.connect(self.path, timeout=0.02, isolation_level=None, check_same_thread=False)
            # The finalizer owns the connection, not this recorder; it also closes disposable reference cycles.
            self._finalizer = weakref.finalize(self, db.close)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            # Reports hold a consistent read snapshot without delaying the minute writer. A pinned reader can
            # defer WAL checkpoints, so the combined-file guard below bounds that case as well as the main DB.
            db.execute("PRAGMA wal_autocheckpoint=64")
            db.execute("PRAGMA journal_size_limit=1048576")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={max(1, (self.max_disk_bytes - DISK_HEADROOM) // page_size)}")
            db.executescript(SCHEMA)
            pending = db.execute("SELECT value FROM meta WHERE key='pending'").fetchone()
            if pending:
                old = json.loads(pending[0])
                db.execute("INSERT OR IGNORE INTO gaps VALUES(?,?)", (old["day"], "interrupted_observation"))
            self._used = int(db.execute("SELECT coalesce(sum(length(body)),0) FROM events").fetchone()[0])
            self._used += int(db.execute("SELECT coalesce(sum(length(body)),0) FROM models").fetchone()[0])
            self._counts = dict(db.execute("SELECT day,count(*) FROM events GROUP BY day"))
            self.db = db
        return self.db

    def disk_bytes(self) -> int:
        return sum(path.stat().st_size for path in
                   (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")) if path.exists())

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """The only integration boundary. Construction, serialization, disk and alert failures stay observational."""
        day = "unknown"
        try:
            day = self._day()
            if day in self.failed:
                return None
            db = self._connect()
            if self.disk_bytes() >= self.max_disk_bytes - DISK_HEADROOM:
                raise ValueError("execution evidence disk bound")
            # Commit before constructing a payload or invoking the observation method.
            db.execute("INSERT OR REPLACE INTO meta VALUES('pending',?)", (dumps({"day": day, "method": method}),))
            result = getattr(self, "_" + method)(*args, **kwargs)
            db.execute("DELETE FROM meta WHERE key='pending'")
            return result
        except Exception as exc:  # noqa: BLE001 - never alter the order/exit/reconciliation outcome
            self.failed.add(day)
            try:
                if self.db is not None:
                    self.db.execute("INSERT OR IGNORE INTO gaps VALUES(?,?)", (day, "observation_write_failed"))
            except Exception:  # pending marker / missing coverage remains the durable witness
                pass
            try:
                from .state import write_json_atomic
                health = self.root / HEALTH
                old = json.loads(health.read_text()) if health.exists() else {}
                old[day] = {"incomplete": True, "error_type": type(exc).__name__}
                write_json_atomic(health, old)
            except Exception:
                pass
            try:
                if self.alert:
                    self.alert("warning", "private execution evidence is incomplete; order handling continues")
            except Exception:
                pass
            return None

    def _insert(self, source: str, kind: str, ident: str, data: Mapping[str, Any], *, day: str | None = None,
                dedupe: bool = False) -> None:
        day = day or self._day()
        body = dumps(dict(data, recorder_run=self.run_id))
        key = (day, source, kind, ident)
        digest = hashlib.sha256(body.encode()).hexdigest()
        if dedupe and self._seen.get(key) == digest:
            return
        size = len(body.encode())
        if (size > MAX_EVENT_BYTES or self._used + size > self.max_bytes
                or self._counts.get(day, 0) >= self.max_events_day):
            raise ValueError("execution evidence storage bound")
        self.db.execute("INSERT INTO events(day,at,source,kind,ident,body) VALUES(?,?,?,?,?,?)",
                        (day, self.clock(), source, kind, ident, body))
        self._used += size
        self._counts[day] = self._counts.get(day, 0) + 1
        if dedupe:
            # Bound this optimization as well; evicting only means a duplicate observation may be stored.
            if len(self._seen) >= 4096:
                self._seen.clear()
            self._seen[key] = digest

    def _model(self, model: Any) -> dict:
        self.model = self._capture_model(model)
        return self.model

    def _capture_model(self, model: Any) -> dict:
        from ..gym.driver import build_bundle
        artifact = {"hazard": dict(model.hazard), "meta": dict(model.meta), "source": str(model.source)}
        body = dumps(artifact)
        digest = hashlib.sha256(body.encode()).hexdigest()
        if len(body.encode()) > MAX_MODEL_BYTES or self._used + len(body.encode()) > self.max_bytes:
            raise ValueError("model artifact exceeds evidence bound")
        before = self.db.total_changes
        self.db.execute("INSERT OR IGNORE INTO models VALUES(?,?,?)", (digest, model.version, body))
        if self.db.total_changes > before:
            self._used += len(body.encode())
        if self.engine is None:
            self.engine = build_bundle()[1]
        return {"version": model.version, "sha256": digest, "engine_bundle": self.engine,
                "fee_provenance": "venue_table_estimate", "natural_only": not bool(model.hazard)}

    def _begin(self, now: float) -> tuple[str, int] | None:
        from .chains import session_minutes
        local = dt.datetime.fromtimestamp(now, NY)
        session = session_minutes(local.date())
        minute = local.hour * 60 + local.minute
        self._coverage = None
        if session is not None and session[0] <= minute <= session[1]:
            key = (local.date().isoformat(), minute)
            exists = self.db.execute("SELECT complete FROM coverage WHERE day=? AND minute=?", key).fetchone()
            if exists is None:
                self.db.execute("INSERT INTO coverage VALUES(?,?,0)", key)
                self._coverage = key
        return self._coverage

    def _end(self, token: tuple[str, int] | None, successful: bool) -> None:
        if token is not None and successful:
            self.db.execute("UPDATE coverage SET complete=1 WHERE day=? AND minute=?", token)
        self._coverage = None

    def _instance(self, inst: Any) -> None:
        self._insert(inst.kind, "instance", inst.key,
                     {"family": inst.family, "version": inst.version, "run_sha": inst.run_sha,
                      "tuition": inst.tuition, "band": inst.band}, dedupe=True)

    def _snapshot(self, root: str, legs: list[dict], *, mi: int | None = None) -> dict:
        day = self.context()
        return sample(day, getattr(day, "_minute", -1) if mi is None else mi, root, legs)

    def _paper(self, kind: str, row: Mapping[str, Any], *, work: Mapping[str, Any] | None = None,
               detail: Any = None, mi: int | None = None) -> None:
        work = work or (row.get("orders") or [{}])[-1]
        body = work.get("body") or {}
        data = {"attempt": row.get("attempt"), "action": work.get("action"), "model": self.model,
                "work": dict(work), "detail": detail, "synthetic": True, "fee_provenance": "unknown"}
        if kind in ("submit", "opportunity") and body:
            data["quote"] = self._snapshot("SPY", body_legs(body), mi=mi)
        self._insert("paper", kind, str(work.get("cid") or row.get("attempt") or "proof"), data,
                     dedupe=kind in ("lookup", "order_observed", "open_witness", "close_witness"))

    def _paper_event(self, kind: str, status: Callable[[], Mapping[str, Any]], detail: Any) -> None:
        self._paper(kind, status(), detail=detail)

    def _real(self, kind: str, order: Any, *, detail: Any = None, mi: int | None = None) -> None:
        from .real import mleg_body, single_leg_body
        body = single_leg_body(order) if order.action == "close_leg" else mleg_body(order)
        data = {"order": order.row(), "body": body, "detail": detail, "model": self.model,
                "synthetic": False, "fee_provenance": "venue_table_estimate"}
        if kind == "decision":
            current = self.context()
            data["decision_minute"] = current.open_min + order.placed_minute if current is not None else None
        if kind in ("submit", "opportunity", "decision"):
            data["quote"] = self._snapshot(order.root, body_legs(body), mi=mi)
        self._insert("real", kind, order.client_id, data, dedupe=kind == "reply")

    def _shadow(self, kind: str, account: Any, *, day: Any = None, mi: int | None = None, work: Any = None,
                detail: Any = None) -> None:
        from .shadow import _working_state
        from .venue import occ_symbol
        data = {"instance": account.instance, "family": account.family, "model": self._capture_model(account.cfg.fill_model),
                "synthetic": True, "fee_provenance": "venue_table_simulation", "detail": detail}
        ident = account.instance
        if kind == "trade":
            ident += ":trade:" + str(detail["id"])
        if work is not None:
            ident += ":" + str(work.oid)
            data["work"] = _working_state(work)
            data["work"].update(seen=work.seen, aggressive=work.aggressive,
                                fill_flags_known=getattr(work, "fill_flags_known", True))
            if day is not None and mi is not None:
                order = work.order
                legs = (account.positions[work.pid].legs_today() if order.action == "close"
                        and work.pid in account.positions else order.legs)
                chain = day.chains.get(order.root)
                contracts = [{"symbol": chain.symbol[leg.idx] if chain is not None and 0 <= leg.idx < chain.contracts else
                              occ_symbol(order.root, (day.day + dt.timedelta(days=int(leg.dte))).isoformat(), leg.is_call, leg.strike),
                              "direction": 1 if (leg.side > 0) == (order.action == "open") else -1,
                              "ratio": leg.ratio} for leg in legs]
                data["quote"] = sample(day, mi, order.root, contracts)
                if kind == "opportunity":
                    data["next_quote"] = sample(day, mi + 1, order.root, contracts)
        self._insert("shadow", kind, ident, data, dedupe=kind == "trade")

    def _refusal(self, source: str, instance: str, detail: Any) -> None:
        self._insert(source, "rejection", instance, {"detail": detail})

    def _checkpoint(self, payload: Mapping[str, Any]) -> None:
        self._insert("shadow", "checkpoint", self.run_id,
                     {"state_semantic_sha256": hashlib.sha256(dumps(payload).encode()).hexdigest(),
                      "accounts": [{"instance": a["instance"], "fills": a["counts"].get("fills", 0)}
                                   for a in payload["accounts"]]})

    def close(self) -> None:
        try:
            if self._finalizer is not None:
                self._finalizer()
                self._finalizer = None
            elif self.db is not None:
                self.db.close()
            self.db = None
        except Exception:
            pass

__all__ = ["Evidence", "FILE", "HEALTH", "sample", "number", "dumps"]
