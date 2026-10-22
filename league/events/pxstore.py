"""THE PRICE LANE'S STORE (release 1019i; PREREG-EVL-8's harness plan H2, goal-2026-10-19/evl8/GUSHER-RESULT.json):
`px.sqlite` beside the lane's `events.sqlite`, under the same state root (`<state>/events/px.sqlite`), written only by
the price lane's recorders (league/events/pxdata.py) and read by nothing that decides real money until PREREG-EVL-8's
programs ship (H3): with league/config.json `events.px_data` on, the recorders only WARM it.

ITS OWN STORE, NEVER THE LANE'S TABLES: the PX universe keeps its own results (`px_eligibility`, `px_universe`) and its
own operating-company cache (`cik_info`, the lane's schema, so league/events/universe.py `operating` reads and fills it
here); nothing here writes the lane's `eligibility`, `universe`, `bars`, `marks` or `cik_info`. A rollback drops nothing:
an older release never opens this file.

THE TABLES (every one `px_*` but the cache, each refused to the births' facts: league/events/births.py `FACTS_DENY` takes
`TABLES`):
- `px_meta` (key, value): the schema version and the recorders' progress (the backfill's chunks, the nights done).
- `px_runs`: ONE ROW A RECORDER RUN (`start_run`, `finish_run`): its id (`run`: `<job>:<UTC time>:<n>`), job, start and
  end, status, requests and rows, and a summary of counts. Every row any run writes carries its run id.
- `px_bars`: SIP daily bars (`adj` raw or all) as last read, with the bar's own time (`t`) and when it was fetched; an
  upsert like the lane's `bars`, except that a stored close the vendor later changed is first kept in `px_bar_moves`
  (symbol, day, adj, the close before and after, both reading times, the run): an adjustment published after a read
  is on record, never lost.
- `px_minutes` (WRITE-ONCE): one value a (symbol, session, label) from SIP 1Min bars, once the span is whole on the
  Basic plan's tape: `px1530` (THE PX1530 MARK x_D: the close of the last raw regular-session minute bar starting in
  [15:00, 15:29] ET, ending by 15:30; on an early close [close - 60 min, close - 31 min]), `v1530` (the session's raw
  regular-session minute volumes through the bar ending at 15:30), `pm` (THE PREMARKET INDICATION pm_D: the close of
  the last minute bar starting in [08:00, 08:58] ET when at least 3 bars of that span have volume, else none); with
  the number of bars, the first and last bar times read and when.
- `px_flags` (WRITE-ONCE): FLAGGED(D) of entry session D (PREREG-EVL-8 draft section 1): P's adjusted close read AT OR
  AFTER 09:00 ET of D (c*_P) against P's raw close; flagged when |c*_P / c_P(raw) - 1| > 0.001 (a split, a dividend or
  a correction effective D) or when either close was not read.
- `px_eligibility` (WRITE-ONCE, one row a (day, cik, rule)): every result of the PX universe's test for entry session
  D, eligible or not, with the first reason it failed (`why`, a short token), the rule (live | backfill) and the run.
- `px_universe` (WRITE-ONCE, one row a (day, cik, rule)): PXU(D)'s eligible issuers: the symbol, exchange, P's raw close,
  ADV20 (dollars) and ADV20sh (shares), the benchmark, the adjusted bars on record of the 61 sessions before D, when
  it was decided and the latest fetch time of its inputs (`inputs_at`).
- `px_features` (WRITE-ONCE, `put_features`): a decided value set (JSON) of an issuer on a session, by kind, with
  `decided_at`, `inputs_at` (the latest `fetched_at` of its inputs), the bar times it read (`bars_from`, `bars_to`),
  its `source` (live | backfill) and its run. INSERT OR IGNORE: a value is written once at its decision and never
  recomputed; the bars' upsert can never move it.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from . import store as S

DB_NAME = "px.sqlite"
SCHEMA_VERSION = 1
#: FLAGGED(D)'s tolerance on |c*_P / c_P(raw) - 1| (PREREG-EVL-8 draft section 1).
FLAG_TOLERANCE = 0.001
SOURCES = ("live", "backfill")
RULES = (S.LIVE_RULE, S.BACKFILL_RULE)
LABELS = ("px1530", "v1530", "pm")

SCHEMA = """
CREATE TABLE IF NOT EXISTS px_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS px_runs(run TEXT PRIMARY KEY, job TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
  status TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0, rows INTEGER NOT NULL DEFAULT 0, summary TEXT);
CREATE TABLE IF NOT EXISTS px_bars(symbol TEXT NOT NULL, day TEXT NOT NULL, adj TEXT NOT NULL, o REAL, h REAL, l REAL,
  c REAL, v REAL, n INTEGER, vw REAL, t TEXT NOT NULL, fetched_at TEXT NOT NULL, run TEXT NOT NULL,
  PRIMARY KEY(symbol, day, adj));
CREATE INDEX IF NOT EXISTS px_bars_day ON px_bars(day, adj);
CREATE TABLE IF NOT EXISTS px_bar_moves(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, day TEXT NOT NULL,
  adj TEXT NOT NULL, c_was REAL, c_now REAL, was_at TEXT NOT NULL, now_at TEXT NOT NULL, run TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS px_minutes(symbol TEXT NOT NULL, day TEXT NOT NULL, label TEXT NOT NULL, value REAL,
  bars INTEGER NOT NULL, first_t TEXT, last_t TEXT, fetched_at TEXT NOT NULL, run TEXT NOT NULL,
  PRIMARY KEY(symbol, day, label));
CREATE TABLE IF NOT EXISTS px_flags(day TEXT NOT NULL, symbol TEXT NOT NULL, prev_day TEXT NOT NULL, c_raw REAL,
  c_adj REAL, ratio REAL, flagged INTEGER NOT NULL, read_at TEXT NOT NULL, run TEXT NOT NULL, PRIMARY KEY(day, symbol));
CREATE TABLE IF NOT EXISTS px_eligibility(day TEXT NOT NULL, cik TEXT NOT NULL, rule TEXT NOT NULL,
  eligible INTEGER NOT NULL, symbol TEXT, why TEXT, decided_at TEXT NOT NULL, run TEXT NOT NULL,
  PRIMARY KEY(day, cik, rule));
CREATE TABLE IF NOT EXISTS px_universe(day TEXT NOT NULL, cik TEXT NOT NULL, rule TEXT NOT NULL, symbol TEXT NOT NULL,
  name TEXT, exchange TEXT, prev_close REAL, adv20 REAL, adv20sh REAL, bench TEXT, adjusted61 INTEGER,
  decided_at TEXT NOT NULL, inputs_at TEXT, run TEXT NOT NULL, PRIMARY KEY(day, cik, rule));
CREATE TABLE IF NOT EXISTS px_features(day TEXT NOT NULL, cik TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT NOT NULL,
  value TEXT NOT NULL, decided_at TEXT NOT NULL, inputs_at TEXT NOT NULL, bars_from TEXT, bars_to TEXT,
  source TEXT NOT NULL, run TEXT NOT NULL, PRIMARY KEY(day, cik, kind));
CREATE TABLE IF NOT EXISTS cik_info(cik TEXT PRIMARY KEY, sic TEXT, periodic_form TEXT, periodic_at TEXT,
  operating INTEGER, checked_at TEXT NOT NULL);
"""
#: Every `px_*` table (league/events/births.py `FACTS_DENY` refuses each: SIP prices and what is made of them).
TABLES = frozenset({"px_meta", "px_runs", "px_bars", "px_bar_moves", "px_minutes", "px_flags", "px_eligibility",
                    "px_universe", "px_features"})
_RUNS = itertools.count(1)


def path_of(root: str | os.PathLike[str]) -> Path:
    """px.sqlite under the lane's state root (`<state>/events/`)."""
    return Path(root) / DB_NAME


class PxStore:
    """px.sqlite (the module docstring): `PxStore(root)` with `root` the lane's root; `close()` or a `with`. It has the
    `db` and `tx()` league/events/universe.py `operating` takes a store by (its `cik_info`)."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path_of(self.root)), timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        have = self.meta("schema_version")
        if have is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        elif int(have) != SCHEMA_VERSION:
            raise RuntimeError(f"px.sqlite schema {have} is not this code's {SCHEMA_VERSION}")

    def __enter__(self) -> "PxStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # -- meta and runs ----------------------------------------------------------------------------------------------
    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM px_meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO px_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value))

    def start_run(self, job: str, *, now: dt.datetime) -> str:
        """A new run of recorder `job`: its id, kept in `px_runs` as running."""
        run = f"{job}:{S.iso(now)}:{os.getpid()}-{next(_RUNS)}"
        self.db.execute("INSERT INTO px_runs(run, job, started_at, status) VALUES(?, ?, ?, 'running')",
                        (run, job, S.iso(now)))
        return run

    def finish_run(self, run: str, status: str, *, now: dt.datetime, requests: int = 0, rows: int = 0,
                   summary: Mapping[str, Any] | None = None) -> None:
        self.db.execute("UPDATE px_runs SET finished_at=?, status=?, requests=?, rows=?, summary=? WHERE run=?",
                        (S.iso(now), status, int(requests), int(rows), json.dumps(summary or {}, sort_keys=True,
                                                                                    default=str), run))

    def last_run(self, job: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM px_runs WHERE job=? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                              (job,)).fetchone()
        return None if row is None else dict(row)

    # -- daily bars -------------------------------------------------------------------------------------------------
    def put_bars(self, rows: Iterable[Mapping[str, Any]], *, adj: str, run: str, now: dt.datetime) -> tuple[int, int]:
        """Daily bars ({symbol, day, t, o, h, l, c, v, n, vw}) of adjustment `adj` into `px_bars`, one transaction: a
        new bar inserted; a stored one updated, its close kept in `px_bar_moves` first when the vendor changed it.
        Returns (rows stored, closes moved)."""
        if adj not in ("raw", "all"):
            raise ValueError(adj)
        stamp = S.iso(now)
        stored = moved = 0
        with self.tx() as db:
            for b in rows:
                key = (str(b["symbol"]).upper(), str(b["day"]), adj)
                have = db.execute("SELECT c, fetched_at FROM px_bars WHERE symbol=? AND day=? AND adj=?", key).fetchone()
                if have is not None and have["c"] != b.get("c"):
                    db.execute("INSERT INTO px_bar_moves(symbol, day, adj, c_was, c_now, was_at, now_at, run) VALUES(?, ?, "
                               "?, ?, ?, ?, ?, ?)", (*key, have["c"], b.get("c"), have["fetched_at"], stamp, run))
                    moved += 1
                db.execute("INSERT INTO px_bars(symbol, day, adj, o, h, l, c, v, n, vw, t, fetched_at, run) VALUES(?, ?, ?, ?, "
                           "?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, day, adj) DO UPDATE SET o=excluded.o, "
                           "h=excluded.h, l=excluded.l, c=excluded.c, v=excluded.v, n=excluded.n, vw=excluded.vw, "
                           "t=excluded.t, fetched_at=excluded.fetched_at, run=excluded.run",
                           (*key, b.get("o"), b.get("h"), b.get("l"), b.get("c"), b.get("v"), b.get("n"), b.get("vw"),
                            str(b["t"]), stamp, run))
                stored += 1
        return stored, moved

    def bars(self, symbol: str, days: Iterable[dt.date], adj: str = "raw") -> dict[str, dict[str, Any]]:
        """`symbol`'s stored bars of `days` ({day iso: row}), as league/events/universe.py `bars` reads the lane's."""
        want = [d.isoformat() for d in days]
        if not want:
            return {}
        marks = ",".join("?" * len(want))
        rows = self.db.execute(f"SELECT * FROM px_bars WHERE symbol=? AND adj=? AND day IN ({marks})",
                               (symbol.upper(), adj, *want))
        return {r["day"]: dict(r) for r in rows}

    # -- the write-once values --------------------------------------------------------------------------------------
    def put_minute(self, symbol: str, day: dt.date, label: str, value: float | None, *, bars: int, first_t: str | None,
                   last_t: str | None, run: str, now: dt.datetime) -> bool:
        """One minute-bar value (`LABELS`), WRITE-ONCE: True when this call wrote it, False when one stood already."""
        if label not in LABELS:
            raise ValueError(label)
        cur = self.db.execute("INSERT OR IGNORE INTO px_minutes(symbol, day, label, value, bars, first_t, last_t, "
                              "fetched_at, run) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (symbol.upper(), day.isoformat(), label, value, int(bars), first_t, last_t, S.iso(now), run))
        return cur.rowcount == 1

    def minute(self, symbol: str, day: dt.date, label: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM px_minutes WHERE symbol=? AND day=? AND label=?",
                              (symbol.upper(), day.isoformat(), label)).fetchone()
        return None if row is None else dict(row)

    def put_flag(self, day: dt.date, symbol: str, prev_day: dt.date, c_raw: float | None, c_adj: float | None, *,
                 run: str, now: dt.datetime) -> bool:
        """FLAGGED(day) of `symbol` (the module docstring), WRITE-ONCE: True when this call wrote it."""
        ratio = None if not c_raw or c_adj is None else c_adj / c_raw
        flagged = ratio is None or abs(ratio - 1.0) > FLAG_TOLERANCE
        cur = self.db.execute("INSERT OR IGNORE INTO px_flags(day, symbol, prev_day, c_raw, c_adj, ratio, flagged, read_at, "
                              "run) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (day.isoformat(), symbol.upper(), prev_day.isoformat(), c_raw, c_adj, ratio, int(flagged),
                               S.iso(now), run))
        return cur.rowcount == 1

    def flag(self, day: dt.date, symbol: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM px_flags WHERE day=? AND symbol=?", (day.isoformat(), symbol.upper())).fetchone()
        return None if row is None else dict(row)

    def put_result(self, day: dt.date, cik: str, rule: str, row: Mapping[str, Any] | None, *, why: str | None, run: str,
                   now: dt.datetime) -> bool:
        """One result of the PX universe's test, WRITE-ONCE per (day, cik, rule): `px_eligibility`, and the issuer's
        `px_universe` row when eligible (`row`: symbol, name, exchange, prev_close, adv20, adv20sh, bench, adjusted61,
        inputs_at). True when this call wrote it; the first result of a (day, cik, rule) stands."""
        if rule not in RULES:
            raise ValueError(rule)
        stamp = S.iso(now)
        with self.tx() as db:
            cur = db.execute("INSERT OR IGNORE INTO px_eligibility(day, cik, rule, eligible, symbol, why, decided_at, run) "
                             "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (day.isoformat(), str(cik), rule, 1 if row else 0,
                                                               str(row["symbol"]) if row else None, why, stamp, run))
            if cur.rowcount != 1:
                return False
            if row:
                db.execute("INSERT OR IGNORE INTO px_universe(day, cik, rule, symbol, name, exchange, prev_close, adv20, "
                           "adv20sh, bench, adjusted61, decided_at, inputs_at, run) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                           "?, ?)", (day.isoformat(), str(cik), rule, str(row["symbol"]), row.get("name"),
                                     row.get("exchange"), row.get("prev_close"), row.get("adv20"), row.get("adv20sh"),
                                     row.get("bench"), row.get("adjusted61"), stamp, row.get("inputs_at"), run))
        return True

    def universe(self, day: dt.date, rule: str = S.LIVE_RULE) -> dict[str, dict[str, Any]]:
        """PXU(day)'s eligible issuers under `rule`, by CIK."""
        return {str(r["cik"]): dict(r) for r in self.db.execute("SELECT * FROM px_universe WHERE day=? AND rule=?",
                                                                (day.isoformat(), rule))}

    def judged(self, day: dt.date, rule: str = S.LIVE_RULE) -> set[str]:
        """The CIKs the PX universe's test has a result for on `day` under `rule`."""
        return {str(r[0]) for r in self.db.execute("SELECT cik FROM px_eligibility WHERE day=? AND rule=?",
                                                   (day.isoformat(), rule))}

    def put_features(self, day: dt.date, cik: str, kind: str, symbol: str, value: Mapping[str, Any], *,
                     decided_at: dt.datetime, inputs_at: str, bars_from: str | None, bars_to: str | None, source: str,
                     run: str) -> bool:
        """THE WRITE-ONCE VALUES (PREREG-EVL-8 draft section 1): a decided value set of `cik` on `day` by `kind`, written
        ONCE (INSERT OR IGNORE) with its decision time, the latest fetch time of its inputs, the bar times it read, its
        source (`SOURCES`: live | backfill) and its run. True when this call wrote it, False when a value stood (it is
        never recomputed). Its inputs must all have been fetched before its decision (`inputs_at` <= `decided_at`)."""
        if source not in SOURCES:
            raise ValueError(source)
        decided = S.iso(decided_at)
        if not inputs_at or str(inputs_at) > decided:
            raise ValueError(f"inputs fetched at {inputs_at!r}, after the decision at {decided}")
        cur = self.db.execute("INSERT OR IGNORE INTO px_features(day, cik, kind, symbol, value, decided_at, inputs_at, "
                              "bars_from, bars_to, source, run) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (day.isoformat(), str(cik), kind, symbol.upper(), json.dumps(dict(value), sort_keys=True),
                               decided, str(inputs_at), bars_from, bars_to, source, run))
        return cur.rowcount == 1

    def features(self, day: dt.date, cik: str, kind: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM px_features WHERE day=? AND cik=? AND kind=?",
                              (day.isoformat(), str(cik), kind)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["value"] = json.loads(out["value"])
        return out

    # -- size -------------------------------------------------------------------------------------------------------
    def size_bytes(self) -> int:
        """px.sqlite's size on disk (its WAL included)."""
        total = 0
        for suffix in ("", "-wal"):
            try:
                total += os.path.getsize(str(path_of(self.root)) + suffix)
            except OSError:
                pass
        return total


__all__ = ["PxStore", "DB_NAME", "SCHEMA", "SCHEMA_VERSION", "TABLES", "FLAG_TOLERANCE", "SOURCES", "RULES", "LABELS",
           "path_of"]
