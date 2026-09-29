"""The practice league's record: `<state>/observe.sqlite` (mode 0600), the House's private file.

The sprint (B4, Sept 26, 2026) made the observe band: an observe instance (`<family>@<version>:o`, `league/live/step.py`)
trades the shadow book on live quotes under the Gym's own fill rules, and its trades are never a forward row (no
evidence, no band). The practice league (Sept 29, 2026) keeps a record of it here:

- `trades`: one row a closed practice trade (the engine's own row in `body`; `exit_day` the session it closed, whose
  P&L is realized then; `reason` its exit reason; `forced` 1 when the House closed it winding the instance down);
- `practice`: one row per (family, version) from its first live minute, kept after the family retires (families live
  hours; the record outlives them): its tier, lineage, structure and roots at its first pin, the session days and
  minutes it was live, its decision coverage (due, made, missed for want of quotes, missed for want of the minute's
  budget), its marked P&L path (per minute, across a remade account) and its open positions at the engine's mark.

WHO READS IT. Nothing that feeds evidence or money: not the gate, the verifier, the bands, the money table, tuition or
Profit. The swarm reads `practice_summary` (read-only) as a RESEARCH signal (`league/swarm/practice.py`: the strategist's
table, the architect's lines, the bandit's capped bonus), and the publisher shows its aggregates (the site's practice
block: never a price, strike, leg, expiry, minute, trade date, version or code).

HONEST ACCOUNTING. The fills are the engine's (`ShadowAccount`, the House's shadow fill model, the Candidates' own); a
trade's P&L is the engine's after fees. The headline is REALIZED P&L; open positions are reported apart, at the engine's
mark (a mid inside the package's bounds), and never added to it. Forced (wind-down) closes stay in the headline, because
they happened, and are counted apart; the feedback's statistics use program-closed trades only.

Bounded: at most `MAX_ROWS` trades (the oldest go first); practice rows unseen for `KEEP_DAYS` days are pruned. Each write
is one transaction; a failure is caught, alerted once, and never stops the minute (trades stay in the shadow account and
are offered again; a practice row is repaired by the next minute's upsert).
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

FILE = "observe.sqlite"
MAX_ROWS = 50_000
KEEP_DAYS = 120
PRUNE_EVERY = 3600.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, family TEXT NOT NULL,
    version INTEGER, trade_id TEXT NOT NULL, day TEXT, pnl REAL, max_loss REAL, recorded_at REAL NOT NULL,
    body TEXT NOT NULL, UNIQUE(instance, account, trade_id));
CREATE INDEX IF NOT EXISTS trades_family ON trades(family, day);
CREATE TABLE IF NOT EXISTS practice (
    family TEXT NOT NULL, version INTEGER NOT NULL,
    tier TEXT NOT NULL, lineage TEXT, structure TEXT, roots TEXT,
    capital REAL NOT NULL,
    first_at REAL NOT NULL, first_day TEXT NOT NULL,
    last_at REAL NOT NULL, last_day TEXT NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    minutes INTEGER NOT NULL DEFAULT 0,
    decisions_due INTEGER NOT NULL DEFAULT 0, decisions_made INTEGER NOT NULL DEFAULT 0,
    missed_quotes INTEGER NOT NULL DEFAULT 0, missed_budget INTEGER NOT NULL DEFAULT 0,
    account TEXT, base_pnl REAL NOT NULL DEFAULT 0,
    pnl_marked REAL NOT NULL DEFAULT 0, peak_marked REAL NOT NULL DEFAULT 0, drawdown_marked REAL NOT NULL DEFAULT 0,
    open_positions INTEGER NOT NULL DEFAULT 0, open_mark_pnl REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'live',
    PRIMARY KEY (family, version));
"""
#: Columns the practice league added to `trades` (Sept 29, 2026), backfilled from `body` on first open.
TRADE_COLUMNS = (("exit_day", "TEXT"), ("reason", "TEXT"), ("forced", "INTEGER"))


class ObserveStore:
    """`<state>/observe.sqlite` (the module docstring)."""

    def __init__(self, root: str | Path, *, alert: Callable[[str, str], Any] | None = None,
                 clock: Callable[[], float] = time.time, max_rows: int = MAX_ROWS):
        self.path = Path(root) / FILE
        self.alert, self.clock, self.max_rows = alert, clock, int(max_rows)
        self.db: sqlite3.Connection | None = None
        self.told = False
        self.practice_told = False
        self._pruned_at = float("-inf")

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
            _migrate(db)
            self.db = db
        return self.db

    def add(self, instance: str, family: str, version: int | None, trades: Iterable[Mapping[str, Any]], *,
            account: str = "") -> bool:
        """The trades of one observe instance's shadow account (`account`: its nonce, as trade ids restart when an account
        is made again under the same key), each once by (instance, account, trade id), in one transaction. False when not
        written."""
        rows = [(str(instance), str(account), str(family), version, str(t.get("id")), str(t.get("day") or ""),
                 _num(t.get("pnl")), _num(t.get("max_loss")), self.clock(), json.dumps(dict(t), sort_keys=True, default=str),
                 _day_of(t.get("exit_day")), str(t.get("exit_reason") or "") or None, 1 if t.get("forced") is True else 0)
                for t in trades]
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.executemany("INSERT OR IGNORE INTO trades(instance, account, family, version, trade_id, day, pnl, "
                               "max_loss, recorded_at, body, exit_day, reason, forced) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                over = int(db.execute("SELECT count(*) FROM trades").fetchone()[0]) - self.max_rows
                if over > 0:
                    db.execute("DELETE FROM trades WHERE seq IN (SELECT seq FROM trades ORDER BY seq LIMIT ?)", (over,))
            return True
        except Exception as exc:  # noqa: BLE001 - the practice record never stops the minute
            if not self.told and self.alert is not None:
                self.told = True
                try:
                    self.alert("warning", f"live: the observe band's trades could not be recorded ({type(exc).__name__}); "
                                          "they are offered again next minute")
                except Exception:  # noqa: BLE001
                    pass
            return False

    def practice(self, rows: Iterable[Mapping[str, Any]]) -> bool:
        """One minute of the practice league: an upsert per practice account, all in one transaction. Each row:
        {family, version, tier, lineage, structure, roots, capital, account (the account's nonce), at, day (the session),
        equity (the account's, at the engine's mark), open_positions, open_mark_pnl, due, made, missed_quotes,
        missed_budget (0 or 1 each), status ("live" | "wound_down")}. A (family, version) seen for the first time starts
        its record (`first_at`: this minute). A remade account (a new nonce) continues it: its marked P&L restarts from the
        realized P&L of the earlier accounts. False when not written (alerted once; the next minute repairs it)."""
        rows = [dict(r) for r in rows]
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                for r in rows:
                    self._upsert(db, r)
                now = self.clock()
                if now - self._pruned_at >= PRUNE_EVERY:
                    self._pruned_at = now
                    db.execute("DELETE FROM practice WHERE last_at < ?", (now - KEEP_DAYS * 86400.0,))
            return True
        except Exception as exc:  # noqa: BLE001 - the practice record never stops the minute
            if not self.practice_told and self.alert is not None:
                self.practice_told = True
                try:
                    self.alert("warning", f"live: the practice league's record could not be written ({type(exc).__name__}); "
                                          "the next minute writes it again")
                except Exception:  # noqa: BLE001
                    pass
            return False

    @staticmethod
    def _upsert(db: sqlite3.Connection, r: Mapping[str, Any]) -> None:
        family, version = str(r["family"]), int(r["version"])
        at, day = float(r["at"]), str(r["day"])
        capital = float(r.get("capital") or 0.0)
        account = str(r.get("account") or "")
        counts = [int(bool(r.get(k))) for k in ("due", "made", "missed_quotes", "missed_budget")]
        old = db.execute("SELECT sessions, minutes, last_day, account, base_pnl, peak_marked, drawdown_marked, tier "
                         "FROM practice WHERE family=? AND version=?", (family, version)).fetchone()
        if old is None or old[3] != account:
            # A new record, or a remade account: its equity starts at `capital` again, so the marked path carries on from
            # the realized P&L of the (family, version)'s other accounts.
            base = db.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE family=? AND version=? AND account != ?",
                              (family, version, account)).fetchone()[0]
        else:
            base = old[4]
        equity = _num(r.get("equity"))
        marked = float(base or 0.0) + ((equity - capital) if equity is not None else 0.0)
        tier = "validated" if r.get("tier") == "validated" else "train"
        if old is None:
            db.execute("INSERT INTO practice(family, version, tier, lineage, structure, roots, capital, first_at, first_day, "
                       "last_at, last_day, sessions, minutes, decisions_due, decisions_made, missed_quotes, missed_budget, "
                       "account, base_pnl, pnl_marked, peak_marked, drawdown_marked, open_positions, open_mark_pnl, status) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,1,1,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (family, version, tier, r.get("lineage"), r.get("structure"),
                        json.dumps([str(x) for x in r.get("roots") or []]), capital, at, day, at, day, *counts, account,
                        float(base or 0.0), marked, max(0.0, marked), max(0.0, -marked),
                        int(r.get("open_positions") or 0), float(_num(r.get("open_mark_pnl")) or 0.0),
                        str(r.get("status") or "live")))
            return
        peak = max(float(old[5]), marked)
        drawdown = max(float(old[6]), peak - marked)
        db.execute("UPDATE practice SET last_at=?, last_day=?, sessions=sessions+?, minutes=minutes+1, "
                   "decisions_due=decisions_due+?, decisions_made=decisions_made+?, missed_quotes=missed_quotes+?, "
                   "missed_budget=missed_budget+?, account=?, base_pnl=?, pnl_marked=?, peak_marked=?, drawdown_marked=?, "
                   "open_positions=?, open_mark_pnl=?, status=?, tier=? WHERE family=? AND version=?",
                   (at, day, int(day != old[2]), *counts, account, float(base or 0.0), marked, peak, drawdown,
                    int(r.get("open_positions") or 0), float(_num(r.get("open_mark_pnl")) or 0.0),
                    str(r.get("status") or "live"), "validated" if "validated" in (tier, old[7]) else "train",
                    family, version))

    def close(self) -> None:
        try:
            if self.db is not None:
                self.db.close()
        except Exception:  # noqa: BLE001
            pass
        self.db = None


def _migrate(db: sqlite3.Connection) -> None:
    """The practice league's trade columns on a file written before them, filled from each trade's own row."""
    have = {row[1] for row in db.execute("PRAGMA table_info(trades)")}
    missing = [(name, kind) for name, kind in TRADE_COLUMNS if name not in have]
    if not missing:
        return
    with db:
        db.execute("BEGIN IMMEDIATE")
        for name, kind in missing:
            db.execute(f"ALTER TABLE trades ADD COLUMN {name} {kind}")
        for seq, body in db.execute("SELECT seq, body FROM trades").fetchall():
            try:
                t = json.loads(body)
            except (TypeError, ValueError):
                t = {}
            db.execute("UPDATE trades SET exit_day=?, reason=?, forced=? WHERE seq=?",
                       (_day_of(t.get("exit_day")), str(t.get("exit_reason") or "") or None,
                        1 if t.get("forced") is True else 0, seq))


# ------------------------------------------------------------------------------------------------ the summary
def practice_summary(root: str | Path, *, sessions: int | None = 10) -> dict[str, Any]:
    """The practice league as research and the site read it: read-only (`mode=ro`, a one-second timeout), standard library
    only, NEVER raising ({} on any error, a missing file or a file from before the practice table).

    The window is the last `sessions` session days on record (None: all of them). One row per (family, version) with a
    closed trade or a live minute in it:

        family, version, tier, lineage, structure, roots, status ("live" | "wound_down"), first_day, last_day
        sessions, minutes, coverage (decisions made / due; None before any was due)   its whole record
        trades, forced, pnl_usd, max_loss_usd, return_on_risk (P&L / maximum loss)      closed in the window, forced
                                                                                         (wind-down) closes included
        drawdown_realized_usd   the largest drop of cumulative realized P&L, in close order, in the window
        drawdown_marked_usd     the largest drop of its per-minute marked P&L from its peak, its whole record
        open_positions, open_mark_pnl_usd                                               now, at the engine's mark
        program {trades, wins, pnl_usd, days, t_trade, t_daily, returns, daily}         program-closed trades only
                                                                                         (the feedback's statistics)

    `t_trade` is the t of the per-trade return on maximum loss (None below 3 trades); `t_daily` the t of the daily return
    (the day's per-trade returns summed per exit day; None below 2 days). A trade recorded before the practice table
    (no practice row) is listed under its own family and version as tier "validated" (the only tier then)."""
    path = Path(root) / FILE
    if not path.exists():
        return {}
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            return _summary(db, sessions)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - research and the site go without it
        return {}


def _summary(db: sqlite3.Connection, sessions: int | None) -> dict[str, Any]:
    db.row_factory = sqlite3.Row
    live = [dict(r) for r in db.execute("SELECT * FROM practice")]
    trades = [dict(r) for r in db.execute("SELECT seq, family, version, pnl, max_loss, exit_day, day, reason, forced, body "
                                          "FROM trades ORDER BY seq")]
    for t in trades:
        t["close_day"] = t.get("exit_day") or _day_of(_body(t).get("exit_day")) or t.get("day") or ""
    days = sorted({str(r["last_day"]) for r in live} | {str(r["first_day"]) for r in live}
                  | {t["close_day"] for t in trades if t["close_day"]})
    if sessions is not None and int(sessions) > 0 and len(days) > int(sessions):
        since = days[-int(sessions)]
    else:
        since = days[0] if days else ""
    keyed: dict[tuple[str, int], dict[str, Any]] = {}
    for r in live:
        if str(r["last_day"]) < since:
            continue
        keyed[(str(r["family"]), int(r["version"]))] = {"live": r, "trades": []}
    for t in trades:
        if t["close_day"] < since:
            continue
        key = (str(t["family"]), int(t["version"] or 0))
        if key not in keyed:
            row = next((r for r in live if (str(r["family"]), int(r["version"])) == key), None)
            keyed[key] = {"live": row, "trades": []}
        keyed[key]["trades"].append(t)
    rows = [_row(key, part) for key, part in keyed.items()]
    rows.sort(key=lambda r: (-r["trades"], r["family"], r["version"]))
    return {"sessions": len([d for d in days if d >= since]), "since": since or None, "rows": rows}


def _row(key: tuple[str, int], part: Mapping[str, Any]) -> dict[str, Any]:
    fam, version = key
    live, trades = part["live"], part["trades"]
    body0 = _body(trades[0]) if trades else {}
    closes = sorted(trades, key=lambda t: (t["close_day"], t["seq"]))
    pnl = [float(t["pnl"] or 0.0) for t in closes]
    losses = [float(t["max_loss"] or 0.0) for t in closes]
    cum = peak = drawdown = 0.0
    for p in pnl:
        cum += p
        peak = max(peak, cum)
        drawdown = max(drawdown, peak - cum)
    program = [t for t in closes if not t.get("forced")]
    returns = [float(t["pnl"] or 0.0) / float(t["max_loss"]) for t in program if (t["max_loss"] or 0) > 0]
    daily: dict[str, list[float]] = {}
    for t in program:
        if (t["max_loss"] or 0) > 0:
            d = daily.setdefault(t["close_day"], [0.0, 0.0])
            d[0] += float(t["pnl"] or 0.0) / float(t["max_loss"])
            d[1] += float(t["pnl"] or 0.0)
    due = int(live["decisions_due"]) if live else 0
    return {
        "family": fam, "version": version,
        "tier": (live or {}).get("tier") or "validated", "lineage": (live or {}).get("lineage"),
        "structure": (live or {}).get("structure") or body0.get("type"),
        "roots": _roots(live) if live else sorted({str(_body(t).get("root") or "") for t in trades} - {""}),
        "status": (live or {}).get("status") or "wound_down",
        "first_day": (live or {}).get("first_day") or (closes[0]["close_day"] if closes else None),
        "last_day": max([str((live or {}).get("last_day") or "")] + [t["close_day"] for t in closes]) or None,
        "sessions": int(live["sessions"]) if live else len({t["close_day"] for t in closes}),
        "minutes": int(live["minutes"]) if live else 0,
        "coverage": round(int(live["decisions_made"]) / due, 4) if live and due else None,
        "decisions_due": due, "decisions_made": int(live["decisions_made"]) if live else 0,
        "missed_quotes": int(live["missed_quotes"]) if live else 0, "missed_budget": int(live["missed_budget"]) if live else 0,
        "trades": len(closes), "forced": sum(1 for t in closes if t.get("forced")),
        "pnl_usd": round(sum(pnl), 2), "max_loss_usd": round(sum(losses), 2),
        "return_on_risk": round(sum(pnl) / sum(losses), 4) if sum(losses) > 0 else None,
        "drawdown_realized_usd": round(drawdown, 2),
        "drawdown_marked_usd": round(float(live["drawdown_marked"]), 2) if live else round(drawdown, 2),
        "open_positions": int(live["open_positions"]) if live else 0,
        "open_mark_pnl_usd": round(float(live["open_mark_pnl"]), 2) if live else 0.0,
        "program": {
            "trades": len(program), "wins": sum(1 for t in program if float(t["pnl"] or 0.0) > 0),
            "pnl_usd": round(sum(float(t["pnl"] or 0.0) for t in program), 2), "days": len(daily),
            "t_trade": t_stat(returns, 3), "t_daily": t_stat([v[0] for _, v in sorted(daily.items())], 2),
            "returns": [round(x, 6) for x in returns],
            "daily": [[d, round(v[0], 6), round(v[1], 2)] for d, v in sorted(daily.items())],
        },
    }


def t_stat(values: list[float], minimum: int) -> float | None:
    """The t of the mean of `values` (None below `minimum` values or with no spread)."""
    n = len(values)
    if n < max(2, int(minimum)):
        return None
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    if not var > 0 or not math.isfinite(var):
        return None
    return round(mean / math.sqrt(var / n), 4)


def _roots(live: Mapping[str, Any]) -> list[str]:
    try:
        value = json.loads(live.get("roots") or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value] if isinstance(value, list) else []


def _body(t: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(t.get("body") or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _day_of(value: Any) -> str | None:
    text = str(value or "")
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


__all__ = ["ObserveStore", "practice_summary", "t_stat", "FILE", "MAX_ROWS", "KEEP_DAYS"]
