"""live.sqlite as the House's equity book writes it for the event kind (league/equity/live.py `SCHEMA` and
`ORDER_COLUMNS_DDL`, league/events/book.py `SCHEMA`), filled with INVENTED rows for release 1019f's alarms
(league/ops/evl_health.py `evl_entries`, `evl_handback`) and the daily report's real buys. Every symbol, quantity, limit
and price here is invented; no market price is read."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def ny(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).timestamp()


def stamp(epoch: float, ms: float = 0.0) -> str:
    """An RFC 3339 stamp as the venue writes one (nanoseconds), `ms` milliseconds after `epoch`."""
    at = dt.datetime.fromtimestamp(epoch, UTC) + dt.timedelta(milliseconds=ms)
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"


def entry_why(at: str, binding: str = "intent", qty: int = 3, band: str = "learning") -> str:
    """A sent event buy's `why` as league/equity/live.py `_event_work_entry` writes it (`_size_event`'s words)."""
    return f"event entry at the {at} ({qty} shares at {band} ({binding}): {qty} XYZ at 12.34: the intent's $37.02)"


class Book:
    """The book's tables in `<root>/live.sqlite` and helpers that write one event buy, its orders and its lot."""

    def __init__(self, root: Path):
        from league.equity import live as L
        from league.events import book as BK

        self.path = Path(root) / "live.sqlite"
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.executescript(L.SCHEMA)
        self.db.executescript(BK.SCHEMA)
        have = {row[1] for row in self.db.execute("PRAGMA table_info(eq_orders)")}
        for column, ddl in L.ORDER_COLUMNS_DDL.items():
            if column not in have:
                self.db.execute(ddl)
        self.iid, self.eid, self.lid = (int(self.db.execute(f"SELECT COALESCE(MAX({key}), 0) FROM {table}").fetchone()[0])
                                        for key, table in (("iid", "eq_intents"), ("eid", "eq_orders"), ("lid", "eq_lots")))

    def close(self) -> None:
        self.db.close()

    def buy(self, day: dt.date, at: str, *, status: str = "done", why: str = "", orders: tuple = (),
            program: str = "EVL-ERN-READ-O1", version: int = 2, band: str = "learning", event: str | None = None,
            ended: float | None = None) -> int:
        """One event BUY intent at the `at` ("open" | "close") auction of `day` with its orders (each a dict for
        `order`): returns its iid."""
        self.iid += 1
        iid = self.iid
        cross = ny(day, "09:30" if at == "open" else "16:00")
        self.db.execute("INSERT INTO eq_intents(iid, instance, family, version, decided_day, exec_day, at, kind, symbol, "
                        "share, tag, status, why, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, 'buy', 'XYZ', "
                        "'0.02', ?, ?, ?, ?, ?)",
                        (iid, f"{program}:{version}:r", program, version, day.isoformat(), day.isoformat(), at,
                         f"evl:{event or f'ev{iid}'}", status, why, cross - 900, ended if ended is not None else cross + 150))
        self.db.execute("INSERT INTO eq_event_intents(iid, program, version, event, side, band, tif, otype, symbol, cik, "
                        "day, at, weight, decided_at, created_at) VALUES(?, ?, ?, ?, 'buy', ?, ?, 'limit', 'XYZ', "
                        "'0000000009', ?, ?, '0.40', ?, ?)",
                        (iid, program, version, event or f"ev{iid}", band, "opg" if at == "open" else "cls",
                         day.isoformat(), at, "2026-10-20T13:15:00Z", cross - 900))
        for spec in orders:
            self.order(iid, day, at, **spec)
        return iid

    def order(self, iid: int, day: dt.date, at: str, *, status: str, filled: str = "0", answer: dict | None = None,
              why: str | None = None, side: str = "buy", lid: int | None = None, fill_at: float | None = None) -> int:
        self.eid += 1
        cross = ny(day, "09:30" if at == "open" else "16:00")
        self.db.execute("INSERT INTO eq_orders(eid, client_id, instance, family, lid, iid, side, symbol, class, at, qty, "
                        "limit_px, collar_bp, status, placed_at, day, filled_qty, why, answer, updated_at, tif, otype) "
                        "VALUES(?, ?, 'EVL-ERN-READ-O1:2:r', 'EVL-ERN-READ-O1', ?, ?, ?, 'XYZ', 'stock', ?, '3', '12.34', 0, "
                        "?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (self.eid, f"lq-test-{self.eid}", lid, iid, side, at, status, cross - 840, day.isoformat(), filled,
                         why if why is not None else entry_why(at), json.dumps(answer or {}), cross + 60,
                         "opg" if at == "open" else "cls", "limit" if side == "buy" else "market"))
        if fill_at is not None:
            self.db.execute("INSERT INTO eq_fills(eid, lid, qty, px, at) VALUES(?, ?, ?, '12.00', ?)",
                            (self.eid, lid, filled, fill_at))
        return self.eid

    def lot(self, iid: int, *, program: str = "EVL-ERN-READ-O1", version: int = 2, event: str = "ev1",
            status: str = "open", opened_at: float, closed_at: float | None = None, band: str = "learning") -> int:
        """A real event lot of buy `iid` (its `info.evl` as `_book_fill` writes it)."""
        self.lid += 1
        info = {"evl": {"program": program, "version": version, "event": event, "cik": "0000000009", "band": band}}
        self.db.execute("INSERT INTO eq_lots(lid, instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
                        "entry_notional, entry_at, opened_at, opened_day, status, exit_px, closed_at, iid, info) VALUES(?, ?, "
                        "?, ?, 'event', 'XYZ', 'stock', ?, '3', '12.00', '36.00', 'open', ?, '2026-10-20', ?, ?, ?, ?, ?)",
                        (self.lid, f"{program}:{version}:r", program, version, "0" if status == "closed" else "3",
                         opened_at, status, "12.50" if status == "closed" else None, closed_at, iid, json.dumps(info)))
        return self.lid

    def decision(self, day: dt.date, at: str, programs: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO eq_event_decisions(day, at, decided_at, status, summary, created_at) VALUES(?, ?, ?, "
                        "'done', ?, 0)", (day.isoformat(), at, "2026-10-20T13:15:00Z", json.dumps({"programs": programs})))


def cancel_at_once(day: dt.date, at: str, ms: float = 5.0) -> dict:
    """An order the venue accepted, then ended `canceled` `ms` milliseconds after its own submission, nothing filled
    (the captain's A80)."""
    sent = ny(day, "09:16" if at == "open" else "15:50")
    return {"status": "canceled", "answer": {"submitted_at": stamp(sent), "canceled_at": stamp(sent, ms),
                                             "final": "canceled"}}
