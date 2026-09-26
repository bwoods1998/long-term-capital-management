"""The D3 real-fill calibration round trips: the House's own 1-lot SPY and QQQ debit verticals, only to measure fills.

The owner's decision D3 (the sprint, Sept 26, 2026, `docs/goals/LTCM_SWARM_SPRINT.md`): without real fills the Gym's
execution cost is a guess, and it is the biggest single term in every family's result. So the House -- not an agent --
sends 1-lot SPY and QQQ debit verticals, opens and closes them, every session until `live.calibration_samples` samples
per cell, within a strict bound on the day's possible loss: a new open goes only while today's realized calibration loss
(net, floored at zero), plus the maximum loss of any calibration position still held or open still working, plus its own
maximum loss (fees included) stays within the constitution's `options_money.calibration.day_usd` ($50). The day can
never lose more than that, and a closed round trip frees its maximum loss. These are the only orders no agent's intent produced besides the paper route proof. They are never
evidence for any family.

WHAT IT SENDS (`Calibration.step`, once a session minute, from `OptionsLive._session_minute` after the families' real
orders of the minute, so it takes only what they left):

- At each slot (10:00, 12:30 and 14:30 ET: 14:00Z, 16:30Z and 18:30Z in daylight time), at most one round trip, never
  two at once: the symbol with the fewest open-at-mid samples still under the target whose vertical fits every cap. The
  vertical: calls one strike ($1) wide, nearest the money (its centre nearest the underlying, the cheaper at a tie; the
  next nearest of `CANDIDATES` pairs when those contracts are held or worked or it does not fit a cap), on the nearest
  expiry at least a day out, on contracts no book position or working order holds and no waiting exit needs; those
  whose mid debit keeps one lot within the day's bound first. One round trip at a time: a slot waits while a
  calibration position is held or a calibration order works.
- The open: a limit at the mid (the Gym's `limit_value("mid")`: the $0.01 net tick, rounded passively). It works
  `WAIT_MINUTES` (its time in force, cancelled by the order path), then goes ONCE more at the mid plus one tick, then
  nothing.
- The close, once filled: at the mid, then at the mid less one tick, then at the natural, each for `WAIT_MINUTES`; at
  the natural at once from `LAST_RESORT_MINUTES` before the session's close. Charged to the day's order budget like a
  program's close (only that last resort may use the room kept for the House's own exits); at most `CLOSE_ATTEMPTS_DAY`
  attempts a position a day, backing off `REJECT_BACKOFF_MINUTES` (doubling) after a refused one; a natural of a tick
  or less (nothing bids for it) is never sent. The House's own expiry-day rules apply to these positions as to any,
  and from `CALIBRATION_BACKSTOP` minutes before the close the House itself closes one still open.
- It yields: a root on which any family works a real order is left to the families that minute.
- Every order goes through the real book (`league/live/real.py` `RealBook`): written before it is sent, one order stream
  per contract, never the opposite side of a contract the account holds (the wash-trade guard), the day's order count
  (250, every leg counted), buying power reserved, and the gateway's own caps and kill switch behind them.
- New round trips only while: `config.json` real_money, the grant active and every real-entry rule open
  (`OptionsLive.real_block`: the kill switch, the stops, reconciliation, the House), the paper proof PASSED,
  `live.calibration` true in `<state>/swarm.json` (off by default), the day's loss bound with room, the book's, the
  gateway's order and day caps and buying power with room, and the recorder readable. Closes need only the kill switch off.

NEVER EVIDENCE, NEVER PROFIT: the orders and positions belong to `FAMILY` ("house:calibration", never a swarm family's
slug), whose closed trades never reach a forward record (`OptionsLive._export_real`), whose structures the site never
shows, which Profit leaves out (`league/trading_profit.py`; their realized net is published as a cost,
`compute.other_usd`), and whose positions the House takes for an orphan's only in the session's last minutes.

RECORDS (`Recorder`, `<state>/calibration.sqlite`, mode 0600): one row per attempt (per order), written in one transaction
when it is sent and completed in one when it ends: the order and client order ids; the symbol, legs, cell (symbol x
offset x open/close), limit price and tick offset; each leg's NBBO and the structure's mid and natural at submit; the
submit, fill and cancel times; the fill price and filled quantity; the fees (the book's venue-table estimate: the
venue's own are not read here); and the outcome (filled, partial, cancelled or rejected). A failure to record never
blocks or delays an order: it is caught, logged and alerted once. Never published (the repository is public; these are
quotes). `python -m league.live --root <state> --calibration` reads it: counts per cell, fill rate, mean fill against
the mid in ticks.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..gym import legs as L
from ..gym import venue as V
from . import money as M
from .real import ROrder, RLeg, RPosition
from .venue import occ_parts

#: The calibration's orders and positions: never a swarm family (their ids are slugs, `[a-z0-9-]`).
FAMILY = "house:calibration"
INSTANCE = "house:calibration@0:c"
SYMBOLS = ("SPY", "QQQ")
#: New York minutes a round trip may start (10:00, 12:30, 14:30 ET), each within `SLOT_WINDOW` minutes of its time.
SLOTS = (600, 750, 870)
SLOT_WINDOW = 45
#: Minutes each attempt works before the next: its time in force is one less (the order path, as the Gym, gives an order
#: of time in force k the market's minutes m + 1 through m + 1 + k; `OptionsLive._venue_rules`).
WAIT_MINUTES = 5
TIF = WAIT_MINUTES - 1
#: Minutes before the session's close from which an open position closes at the natural at once.
LAST_RESORT_MINUTES = 15
#: No new round trip starts within this many minutes of the close.
NO_NEW_MINUTES = 60
#: The nearest pairs tried, in order, when the nearest one's contracts are held or worked or it does not fit a cap.
CANDIDATES = 4
#: A position's close attempts a day (the mid, a tick under, then the natural), and the back-off after a refused one.
CLOSE_ATTEMPTS_DAY = 6
REJECT_BACKOFF_MINUTES = 5.0
WIDTH = 1.0
TICK = V.NET_TICK
FILE = "calibration.sqlite"
#: One row per attempt; the recorder stops writing (and the program starts no round trip) past this many.
MAX_ROWS = 20000
#: The cells' offsets: open at the mid and one tick over; close at the mid, one tick under, and the natural.
OPEN_OFFSETS = {"mid": ("mid", 0), "mid+1": ({"mid": 1}, 1)}
CLOSE_OFFSETS = {"mid": ("mid", 0), "mid-1": ({"mid": 1}, 1), "natural": ("natural", None)}
COUNTED = ("filled", "partial", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    oid INTEGER PRIMARY KEY, client_id TEXT NOT NULL, trip TEXT NOT NULL, day TEXT NOT NULL, symbol TEXT NOT NULL,
    legs TEXT NOT NULL, action TEXT NOT NULL, offset TEXT NOT NULL, ticks INTEGER, cell TEXT NOT NULL,
    limit_price TEXT NOT NULL, limit_value REAL NOT NULL, qty INTEGER NOT NULL, quote TEXT NOT NULL, mid REAL, natural REAL,
    submitted_at REAL NOT NULL, venue_submitted_at TEXT, filled_at TEXT, canceled_at TEXT, cancel_sent REAL,
    done_at REAL, status TEXT, outcome TEXT, filled_qty INTEGER, fill_value REAL, fees REAL,
    fees_source TEXT);
CREATE INDEX IF NOT EXISTS samples_cell ON samples(symbol, cell, outcome);
CREATE INDEX IF NOT EXISTS samples_open ON samples(outcome);
"""


def cell_of(symbol: str, action: str, offset: str) -> str:
    return f"{symbol}:{action}:{offset}"


def outcome_of(status: str, filled_qty: int) -> str | None:
    """An ended order's outcome, or None while it has not ended (or is lost: it may still turn up)."""
    if status == "filled":
        return "filled"
    if status in ("cancelled", "expired"):
        return "partial" if filled_qty > 0 else "cancelled"
    if status in ("rejected", "refused"):
        return "rejected"
    return None


class Recorder:
    """`<state>/calibration.sqlite` (the module docstring). Every method catches its own failure: it is logged and alerted
    once, and the order path goes on. `counts()` is None when the file cannot be read."""

    def __init__(self, root: str | Path, *, alert: Any = None, log: Any = None, max_rows: int = MAX_ROWS):
        self.path = Path(root) / FILE
        self.alert, self.log = alert, log
        self.max_rows = int(max_rows)
        self.db: sqlite3.Connection | None = None
        self.told = False

    def _connect(self) -> sqlite3.Connection:
        if self.db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            # A short timeout: the minute thread never waits on this file (the report command only reads it).
            db = sqlite3.connect(str(self.path), timeout=0.05, isolation_level=None, check_same_thread=False)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(SCHEMA)
            self.db = db
        return self.db

    def _failed(self, what: str, exc: BaseException) -> None:
        if self.log is not None:
            try:
                self.log("live.calibration_record", {"what": what, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            except Exception:  # noqa: BLE001
                pass
        if not self.told and self.alert is not None:
            self.told = True
            try:
                self.alert("warning", f"live: the calibration's samples could not be recorded ({what}: {type(exc).__name__}); "
                                      "its orders go on, no new round trip starts until the recorder reads again")
            except Exception:  # noqa: BLE001
                pass

    def submitted(self, row: Mapping[str, Any]) -> bool:
        """One attempt's row, as it is sent (one transaction). False when it could not be written."""
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                if int(db.execute("SELECT count(*) FROM samples").fetchone()[0]) >= self.max_rows:
                    raise ValueError(f"the recorder holds {self.max_rows} rows")
                cols = list(row)
                db.execute(f"INSERT OR IGNORE INTO samples({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                           [row[c] for c in cols])
            return True
        except Exception as exc:  # noqa: BLE001 - never blocks the order
            self._failed("submit", exc)
            return False

    def open_rows(self) -> list[dict]:
        try:
            return [dict(r) for r in self._connect().execute(
                "SELECT oid FROM samples WHERE outcome IS NULL ORDER BY oid LIMIT 50")]
        except Exception as exc:  # noqa: BLE001
            self._failed("read", exc)
            return []

    def finished(self, oid: int, fields: Mapping[str, Any]) -> None:
        """An attempt's end (one transaction)."""
        try:
            db = self._connect()
            cols = list(fields)
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(f"UPDATE samples SET {','.join(f'{c}=?' for c in cols)} WHERE oid=?",
                           [fields[c] for c in cols] + [int(oid)])
        except Exception as exc:  # noqa: BLE001
            self._failed("finish", exc)

    def counts(self) -> dict[str, int] | None:
        """Ended attempts that reached the venue, per cell; None when the file cannot be read."""
        try:
            db = self._connect()
            if int(db.execute("SELECT count(*) FROM samples").fetchone()[0]) >= self.max_rows:
                return None
            marks = ",".join("?" * len(COUNTED))
            return {r["cell"]: int(r["n"]) for r in db.execute(
                f"SELECT cell, count(*) AS n FROM samples WHERE outcome IN ({marks}) GROUP BY cell", COUNTED)}
        except Exception as exc:  # noqa: BLE001
            self._failed("count", exc)
            return None

    def close(self) -> None:
        try:
            if self.db is not None:
                self.db.close()
        except Exception:  # noqa: BLE001
            pass
        self.db = None


class Calibration:
    """The D3 program (the module docstring), one per `OptionsLive` with a real account."""

    def __init__(self, live: Any):
        self.live = live
        self.recorder = Recorder(live.root, alert=live.alert, log=live.state.event)

    # ------------------------------------------------------------------ state
    def _st(self) -> dict:
        return dict(self.live.state.get("calibration", {}) or {})

    def _put(self, st: Mapping[str, Any]) -> None:
        self.live.state.put("calibration", dict(st))

    def status(self) -> dict:
        """For health.json, from the House's thread: the live state only (the samples' counts are the report's)."""
        st = self._st()
        trip = dict(st["trip"]) if st.get("trip") else None
        if trip:
            trip.pop("legs", None)                          # contracts are not a status line's
        return {"trip": trip, "slots": st.get("slots"), "why": st.get("why"),
                "day_possible_loss_usd": st.get("day_possible_loss_usd")}

    def positions(self) -> list[RPosition]:
        book = self.live.book
        return [p for p in book.positions.values() if p.family == FAMILY and p.qty > 0] if book is not None else []

    def active(self) -> bool:
        return bool(self._st().get("trip")) or bool(self.positions())

    # ------------------------------------------------------------------ what the minute reads
    def roots(self, now: float) -> dict[str, tuple[int, int, float]]:
        """The chains the program needs read now: while a round trip works, or around a slot it may still start."""
        from .step import ny

        if self._st().get("trip"):
            return {s: (1, 7, 0.01) for s in SYMBOLS}
        if not self.live.switches()["calibration"] or self.live.real_block(opening=True):
            return {}
        local = ny(now)
        minute = local.hour * 60 + local.minute
        fired = self._fired(local.date().isoformat())
        if any(slot - 2 <= minute < slot + SLOT_WINDOW and slot not in fired for slot in SLOTS):
            return {s: (1, 7, 0.01) for s in SYMBOLS}
        return {}

    def _fired(self, today: str) -> list[int]:
        slots = self._st().get("slots") or {}
        return [int(x) for x in slots.get("fired") or []] if slots.get("day") == today else []

    # ------------------------------------------------------------------ the minute
    def step(self, day: Any, mi: int, out: dict) -> None:
        """Records brought up to date, the round trip's open (its progress, or a new one at a slot), then every open
        calibration position's close."""
        if self.live.book is None:
            return
        self.live.book.closed_since.pop(INSTANCE, None)
        self.live.book.rejects_since.pop(INSTANCE, None)
        self._finish_rows()
        self.live._isolated(INSTANCE, lambda: self._open(day, mi, out))
        if not self.live._killed():
            for pos in self.positions():
                self.live._isolated(INSTANCE, lambda pos=pos: self._close(pos, day, mi, out))

    def _finish_rows(self) -> None:
        state = self.live.state
        for row in self.recorder.open_rows():
            found = state.rows("SELECT * FROM orders WHERE oid=?", (int(row["oid"]),))
            if not found:
                continue
            order = ROrder.of(found[0])
            outcome = outcome_of(order.status, order.filled_qty)
            if outcome is None:
                continue
            fees = state.rows("SELECT COALESCE(SUM(fees), 0) AS f FROM fills WHERE oid=?", (order.oid,))[0]["f"]
            self.recorder.finished(order.oid, {
                "status": order.status, "outcome": outcome, "filled_qty": int(order.filled_qty),
                "fill_value": float(order.fill_value) if order.filled_qty > 0 else None,
                "venue_submitted_at": order.answer.get("submitted_at"), "filled_at": order.answer.get("filled_at"),
                "canceled_at": order.answer.get("canceled_at") or order.answer.get("expired_at"),
                "cancel_sent": order.cancel_sent, "done_at": self.live.clock(),
                "fees": float(fees) if order.filled_qty > 0 else 0.0, "fees_source": "book_estimate"})

    # ------------------------------------------------------------------ opening
    def _open(self, day: Any, mi: int, out: dict) -> None:
        live, book = self.live, self.live.book
        st = self._st()
        today = day.day.isoformat()
        minute = day.open_min + mi
        trip = st.get("trip")
        if trip:
            found = live.state.rows("SELECT * FROM orders WHERE oid=?", (int(trip["oid"]),))
            order = ROrder.of(found[0]) if found else None
            if order is not None and order.working:
                return
            if (order is None or order.filled_qty >= 1 or trip.get("attempt") != "mid" or trip.get("day") != today
                    or order.status not in ("cancelled", "expired")):
                if order is not None and order.filled_qty >= 1 and order.pid in book.positions:
                    pos = book.positions[order.pid]         # filled: the close ladder takes it, under this trip's name
                    if pos.info.get("cal_trip") != trip["id"]:
                        pos.info["cal_trip"] = trip["id"]
                        book._save_position(pos)
                st["trip"] = None                           # filled, its attempts spent, or its session over
                self._put(st)
                return
            # The mid went unfilled: once more at the mid plus one tick, on the same contracts, if it still may.
            legs = [RLeg.of(x) for x in trip["legs"]]
            why = self._may_open(day, minute)
            sent = None if why else self._send_open(day, mi, trip["symbol"], legs, "mid+1", trip["id"], out)
            st = self._st()
            if isinstance(sent, ROrder):
                trip.update(attempt="mid+1", oid=sent.oid)
                st["trip"] = trip
            else:
                st["trip"] = None
                st["why"] = f"{today}: the re-price did not go: {why or sent}"
            self._put(st)
            return
        slot = next((s for s in SLOTS if s <= minute < s + SLOT_WINDOW and s not in self._fired(today)), None)
        if slot is None or minute >= day.close_min - NO_NEW_MINUTES:
            return
        why = self._may_open(day, minute)
        if why:
            return  # the slot stays open (inside its window) until real entries may go
        counts = self.recorder.counts()
        if counts is None:
            return  # an unreadable recorder starts nothing (its closes go on)
        target = int(live.switches()["calibration_samples"])
        due = sorted((s for s in SYMBOLS if counts.get(cell_of(s, "open", "mid"), 0) < target),
                     key=lambda s: (counts.get(cell_of(s, "open", "mid"), 0), SYMBOLS.index(s)))
        if not due:
            self._fire(st, today, slot, f"{today}: every symbol has {target} samples at the mid")
            return
        # One round trip at a time: a calibration position still held, or a calibration order still working, makes the
        # slot wait (inside its window).
        if self.positions() or any(o.working and o.family == FAMILY for o in book.orders.values()):
            return
        # It yields: a root on which any family works a real order now is left to the families this minute.
        worked = {o.root for o in book.orders.values() if o.working and o.family != FAMILY}
        due = [s for s in due if s not in worked]
        if not due:
            return  # the slot waits (inside its window) for the families' orders to finish
        reasons, unread = [], []
        for symbol in due:
            picks = self._verticals(day, mi, symbol)
            if picks is None:
                unread.append(symbol)                       # its chain is not read this minute
                continue
            if isinstance(picks, str):
                reasons.append(f"{symbol}: {picks}")
                continue
            trip_id = f"{today.replace('-', '')}-{slot}-{symbol}"
            for n, pick in enumerate(picks, 1):             # the nearest the money first; the first that fits every cap
                sent = self._send_open(day, mi, symbol, pick, "mid", trip_id, out)
                if isinstance(sent, ROrder):
                    st = self._st()
                    st["trip"] = {"id": trip_id, "day": today, "slot": slot, "symbol": symbol, "attempt": "mid",
                                  "oid": sent.oid, "legs": [leg.row() for leg in pick]}
                    self._fire(st, today, slot, None)
                    return
                reasons.append(f"{symbol} pair {n}: {sent}")  # never a strike or a price in a status line
                if sent.startswith(("rejected", "refused", "unknown")):
                    break                                   # it reached the order path: nothing more this slot
        if unread:
            return  # a symbol whose chain is unread this minute may still fit: the slot waits (inside its window)
        self._fire(self._st(), today, slot, f"{today} {slot // 60}:{slot % 60:02d}: " + "; ".join(reasons)[:400])

    def _fire(self, st: dict, today: str, slot: int, why: str | None) -> None:
        slots = st.get("slots") or {}
        fired = [int(x) for x in slots.get("fired") or []] if slots.get("day") == today else []
        st["slots"] = {"day": today, "fired": sorted(set(fired) | {slot})}
        if why:
            st["why"] = why
            self.live.record("live.calibration", {"slot": slot, "day": today, "held": why})
        self._put(st)

    def _may_open(self, day: Any, minute: int) -> str | None:
        live = self.live
        if not live.switches()["calibration"]:
            return "live.calibration is off"
        if live.table.calibration_day <= 0:
            return "the constitution's calibration day cap is zero"
        blocked = live.real_block(opening=True)
        if blocked:
            return blocked
        if live.proof is None or not live.proof.passed():
            return "the paper proof has not passed"
        if live.sizing_equity() is None:
            return "no sizing equity (the grant or the account)"
        if minute >= day.close_min - NO_NEW_MINUTES:
            return "too near the close"
        return None

    def _verticals(self, day: Any, mi: int, symbol: str) -> list[list[RLeg]] | str | None:
        """The call verticals that may be traded, nearest the money first (the module docstring: the vertical's centre
        nearest the underlying, the cheaper at a tie), a reason none may, or None while the chain is unread."""
        snap, chain = day.snapshot(symbol, mi), day.chains.get(symbol)
        if snap is None or chain is None:
            return None
        spot = float(snap.spot)
        if not math.isfinite(spot) or spot <= 0:
            return None
        import numpy as np

        ok = snap.valid & snap.is_call & (snap.dte >= 1)
        if not ok.any():
            return "no call a day or more out is quoted"
        first = int(snap.dte[ok].min())
        pool = np.flatnonzero(ok & (snap.dte == first))
        by_strike = {round(float(snap.strike[i]), 3): int(i) for i in pool}
        book = self.live.book
        held = {s for s, q in book.held_net().items() if q} | book.busy() | self.live._pending_symbols()
        why = "no strike one dollar above the nearest is quoted"
        out = []
        pairs = [k for k in by_strike if round(k + WIDTH, 3) in by_strike]
        near = sorted(pairs, key=lambda k: (abs(k + WIDTH / 2 - spot), -k))[:CANDIDATES]
        cap = float(self.live.table.calibration_day)

        def over(k: float) -> bool:
            debit = float(snap.mid[by_strike[k]]) - float(snap.mid[by_strike[round(k + WIDTH, 3)]])
            return not (math.isfinite(debit) and debit * V.MULTIPLIER <= cap)

        # Nearest the money, those whose mid debit keeps one lot's maximum loss within the day's bound first.
        for strike in sorted(near, key=lambda k: (over(k), near.index(k))):
            i, j = by_strike[strike], by_strike[round(strike + WIDTH, 3)]
            symbols = (str(chain.symbol[i]), str(chain.symbol[j]))
            if set(symbols) & held:
                why = "the nearest pairs' contracts are held or worked"
                continue
            legs = []
            for idx, side in ((i, 1), (j, -1)):
                parts = occ_parts(str(chain.symbol[idx]))
                legs.append(RLeg(str(chain.symbol[idx]), side, 1, True, float(snap.strike[idx]),
                                 parts[1] if parts else "", int(chain.key[idx])))
            out.append(legs)
        return out or why

    def _legfills(self, day: Any, mi: int, symbol: str, legs: Sequence[RLeg]) -> tuple[Any, list[L.LegFill]] | None:
        import numpy as np

        chain, snap = day.chains.get(symbol), day.snapshot(symbol, mi)
        if chain is None or snap is None:
            return None
        idx = chain.index_of(np.array([leg.key for leg in legs], dtype=np.int64))
        if (idx < 0).any():
            return None
        fills = [L.LegFill(int(k), leg.key, leg.side, leg.ratio, int(snap.dte[int(k)]), leg.strike, leg.is_call)
                 for leg, k in zip(legs, idx)]
        return snap, fills

    def _quote(self, snap: Any, fills: Sequence[L.LegFill], legs: Sequence[RLeg], action: str, minute: int) -> dict:
        natural, _ = L.natural_value(snap, fills, action)
        mid = L.mid_value(snap, fills)
        return {"legs": [{"symbol": leg.symbol, "side": leg.side, "bid": _num(snap.bid[f.idx]), "ask": _num(snap.ask[f.idx]),
                          "bid_size": _int(snap.bid_size[f.idx]), "ask_size": _int(snap.ask_size[f.idx])}
                         for leg, f in zip(legs, fills)],
                "mid": _num(mid), "natural": _num(natural), "spot": _num(snap.spot), "minute": int(minute)}

    def _send_open(self, day: Any, mi: int, symbol: str, legs: list[RLeg], offset: str, trip: str, out: dict) -> ROrder | str:
        live, book, table = self.live, self.live.book, self.live.table
        today = day.day.isoformat()
        got = self._legfills(day, mi, symbol, legs)
        if got is None:
            return "its contracts are not in this minute's chain"
        snap, fills = got
        quote = self._quote(snap, fills, legs, "open", day.open_min + mi)
        natural, mid = quote["natural"], quote["mid"]
        if natural is None or mid is None or not (natural > 0 and mid > 0):
            return "no two-sided quote on both legs"
        rule, _ = OPEN_OFFSETS[offset]
        limit = L.limit_value(rule, "open", natural, mid, TICK)
        if not 0 < limit < WIDTH - 1e-9:
            return f"a debit of {limit:.2f} on a vertical {WIDTH:.0f} wide can never pay"
        prices = [float(snap.ask[f.idx]) if f.side > 0 else float(snap.bid[f.idx]) for f in fills]
        fees = L.order_fees(symbol, fills, prices, 1, "open")
        max_loss = round(limit * V.MULTIPLIER, 2)
        unit = M.D(round(max_loss + 2 * fees, 2))
        equity = live.sizing_equity()
        if equity is None:
            return "no sizing equity"
        possible = self.day_possible_loss(today)
        if possible + unit > table.calibration_day:
            return (f"the day's calibration bound: ${M.cents(possible)} could already be lost today (realized, and what is "
                    f"open or working) and this round trip risks ${M.cents(unit)}, over ${table.calibration_day}")
        week_start = (day.day - dt.timedelta(days=day.day.weekday())).isoformat()
        exposure = book.exposure(FAMILY, day=today, week_start=week_start)
        loss = M.D(max_loss)
        if exposure.book_loss + loss > table.book_share * equity:
            return f"the book's cap: ${M.cents(exposure.book_loss)} open of ${M.cents(table.book_share * equity)}"
        if loss > min(table.gateway_order_max_loss, table.gateway_order_share * equity):
            return "the gateway's per-order cap"
        if exposure.day_opened + loss > table.gateway_day_share * equity:
            return "the gateway's day cap"
        reserve = (max_loss + 2 * fees) * (1 + float(table.bp_buffer))
        free = float(M.D(live.account_row.get("options_buying_power") or 0)) - book.reserved() if live.account_row else 0.0
        if reserve > free + 1e-9:
            return f"buying power: it reserves {reserve:.2f}; {max(0.0, free):.2f} is free"
        refusal = book.path_refusal(legs, opening=True, day=today)
        if refusal:
            return refusal
        sent = book.new_order(instance=INSTANCE, family=FAMILY, action="open", type_="debit_vertical", root=symbol,
                              legs=list(legs), qty=1, limit_value=limit, tif=TIF, day=today, minute=mi,
                              reserve=reserve, max_loss=max_loss, fees_est=fees, why=f"calibration: open at {offset}")
        self._record(sent, trip, symbol, legs, "open", offset, quote, mid)
        book.send(sent)
        if sent.pid is not None and sent.pid in book.positions:
            pos = book.positions[sent.pid]                  # filled on arrival: its close carries this round trip's name
            pos.info["cal_trip"] = trip
            book._save_position(pos)
        self._possible_note(today)
        out.setdefault("orders", []).append({"oid": sent.oid, "family": FAMILY, "action": "open", "status": sent.status,
                                             "calibration": offset})
        live.record("live.calibration", {"trip": trip, "symbol": symbol, "action": "open", "offset": offset,
                                         "status": sent.status, "oid": sent.oid, "_limit": sent.limit_price,
                                         "_mid": mid, "_natural": natural})
        return sent if sent.status in ("working", "filled", "unknown") else f"{sent.status}: {sent.answer.get('error')}"

    # ------------------------------------------------------------------ closing
    def _close(self, pos: RPosition, day: Any, mi: int, out: dict) -> None:
        live, book = self.live, self.live.book
        if pos.info.get("broken") or pos.status != "open" or book.closing_order(pos.pid) is not None:
            return                                          # the House's own leg closes, or a close already works
        today = day.day.isoformat()
        minute = day.open_min + mi
        now = live.clock()
        rules = day.rules.get(pos.root) or V.rules_for(pos.root, open_minute=day.open_min, close_minute=day.close_min)
        if pos.expiry == today and minute + 1 >= rules.close_cutoff:
            return                                          # past the expiring close cutoff: the House alerts
        # Attempts a day, and a back-off after the venue or the gateway refused one: an unfilled or refused close is
        # never re-sent without end (every one spends the day's order count). The House's own backstop closes a
        # position still open near the close (`OptionsLive._venue_rules`, `CALIBRATION_BACKSTOP`).
        tally = dict(pos.info.get("cal_attempts") or {})
        if tally.get("day") != today:
            tally = {"day": today, "n": 0, "next_at": 0.0, "backoff": REJECT_BACKOFF_MINUTES}
        last_sent = live.state.rows("SELECT status FROM orders WHERE pid=? AND family=? AND action='close' "
                                    "ORDER BY oid DESC LIMIT 1", (pos.pid, FAMILY))
        if last_sent and last_sent[0]["status"] in ("rejected", "refused") and not tally.get("backed_off_after") == tally["n"]:
            tally.update(next_at=now + 60.0 * float(tally["backoff"]), backoff=2 * float(tally["backoff"]),
                         backed_off_after=tally["n"])
            pos.info["cal_attempts"] = tally
            book._save_position(pos)
        if int(tally["n"]) >= CLOSE_ATTEMPTS_DAY or now < float(tally.get("next_at") or 0.0):
            return
        tried = list(pos.info.get("cal_close") or [])
        last = minute >= day.close_min - LAST_RESORT_MINUTES or bool(live._expiry_close(pos, day, mi, minute))
        offset = "natural" if last or tried[-1:] in (["mid-1"], ["natural"]) else ("mid-1" if tried[-1:] == ["mid"] else "mid")
        got = self._legfills(day, mi, pos.root, pos.legs)
        if got is None:
            return
        snap, fills = got
        quote = self._quote(snap, fills, pos.legs, "close", day.open_min + mi)
        if quote["natural"] is None or quote["mid"] is None:
            return
        if offset == "natural" and quote["natural"] <= TICK + 1e-9:
            return  # nothing bids for it: a natural of a tick or less cannot fill (it is left to expire, or the backstop)
        rule, _ = CLOSE_OFFSETS[offset]
        try:
            order = L.resolve_close({"close": pos.pid, "limit": rule}, pos.type, fills, pos.qty, snap, day.rules[pos.root],
                                    position=pos.pid)
        except L.Refused as exc:
            live.record("live.calibration", {"pid": pos.pid, "action": "close", "offset": offset, "held": str(exc)[:200]})
            return
        value = max(TICK, round(order.limit, 2))            # a debit structure is never given away for nothing
        # Charged to the day's order budget like a program's close; only the true last resort (the session's last
        # minutes, or the House's own expiry close) may use the room kept for the House's exits.
        refusal = book.path_refusal(pos.legs, opening=False, day=today, house=offset == "natural" and last)
        if refusal:
            live.record("live.calibration", {"pid": pos.pid, "action": "close", "offset": offset, "held": refusal[:200]})
            return
        sent = book.new_order(instance=INSTANCE, family=FAMILY, action="close", type_=pos.type, root=pos.root,
                              legs=list(pos.legs), qty=order.qty, limit_value=value,
                              tif=TIF if offset != "natural" else 0, day=today, minute=mi, pid=pos.pid,
                              fees_est=order.fees, why=f"calibration: close at {offset}")
        pos.info["cal_close"] = (tried + [offset])[-20:]
        tally["n"] = int(tally["n"]) + 1
        pos.info["cal_attempts"] = tally
        book._save_position(pos)
        self._record(sent, str(pos.info.get("cal_trip") or f"pid-{pos.pid}"), pos.root, pos.legs, "close", offset, quote,
                     quote["mid"])
        book.send(sent)
        out.setdefault("orders", []).append({"oid": sent.oid, "family": FAMILY, "action": "close", "status": sent.status,
                                             "calibration": offset})
        live.record("live.calibration", {"pid": pos.pid, "action": "close", "offset": offset, "status": sent.status,
                                         "oid": sent.oid, "_limit": sent.limit_price, "_mid": quote["mid"],
                                         "_natural": quote["natural"]})

    # ------------------------------------------------------------------ records and the day's cap
    def _record(self, order: ROrder, trip: str, symbol: str, legs: Sequence[RLeg], action: str, offset: str,
                quote: Mapping[str, Any], mid: float | None) -> None:
        # The rule's tick offset from the mid, worse for the order (None: the natural). The exact distance of the limit
        # from the mid, after the tick's passive rounding, is `limit_value` against `mid`.
        ticks = (OPEN_OFFSETS if action == "open" else CLOSE_OFFSETS)[offset][1]
        self.recorder.submitted({
            "oid": order.oid, "client_id": order.client_id, "trip": trip, "day": order.day, "symbol": symbol,
            "legs": json.dumps([leg.row() for leg in legs], sort_keys=True), "action": action, "offset": offset,
            "ticks": ticks, "cell": cell_of(symbol, action, offset), "limit_price": order.limit_price,
            "limit_value": float(order.limit_value), "qty": int(order.qty), "quote": json.dumps(quote, sort_keys=True),
            "mid": quote.get("mid"), "natural": quote.get("natural"), "submitted_at": float(order.placed_at)})

    def day_possible_loss(self, today: str) -> M.Decimal:
        """The most the calibration can lose on session day `today` as things stand, from the live state's own rows (never
        the recorder): today's REALIZED net loss (positions closed today, fees included; floored at zero), plus every
        calibration position still held (its maximum loss and its fees twice, open and close), plus every calibration open
        still working or unresolved (its remaining maximum loss and round-trip fees; a lost one of today's counts whole: it
        may yet turn up filled). A new open goes only while this plus its own maximum loss and fees stays within
        `options_money.calibration.day_usd`, so the day can never lose more; a closed round trip frees its maximum loss."""
        from .step import ny

        state = self.live.state
        realized = M.ZERO
        for r in state.rows("SELECT cash, closed_at FROM positions WHERE family=? AND status='closed' AND closed_at IS NOT NULL",
                            (FAMILY,)):
            if ny(float(r["closed_at"])).date().isoformat() == today:
                realized += M.D(r["cash"])
        possible = max(M.ZERO, -realized)
        for r in state.rows("SELECT qty, opened_qty, max_loss_share, fees, status FROM positions WHERE family=? AND "
                            "status IN ('open', 'awaiting_expiry', 'unpriced_close')", (FAMILY,)):
            units = int(r["opened_qty"]) if r["status"] == "unpriced_close" else max(0, int(r["qty"]))
            possible += M.D(r["max_loss_share"]) * V.MULTIPLIER * units + 2 * M.D(r["fees"])
        for r in state.rows("SELECT qty, filled_qty, status, max_loss, fees_est, day FROM orders WHERE family=? AND "
                            "action='open' AND status IN ('pending', 'working', 'unknown', 'lost')", (FAMILY,)):
            if r["status"] == "lost" and r["day"] != today:
                continue
            remaining = int(r["qty"]) if r["status"] == "lost" else max(0, int(r["qty"]) - int(r["filled_qty"]))
            share = M.D(remaining) / max(1, int(r["qty"]))
            possible += (M.D(r["max_loss"]) + 2 * M.D(r["fees_est"])) * share
        return possible

    def _possible_note(self, today: str) -> None:
        st = self._st()
        st["day_possible_loss_usd"] = {"day": today, "usd": str(M.cents(self.day_possible_loss(today)))}
        self._put(st)


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def report(root: str | Path) -> dict:
    """The read-only report (`python -m league.live --root <state> --calibration`): per cell the attempts, fills, fill
    rate and mean fill against the mid in ticks (positive: worse than the mid). Opens the file read-only."""
    path = Path(root) / FILE
    if not path.exists():
        return {"file": str(path), "cells": {}, "note": "no calibration samples yet"}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    db.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in db.execute("SELECT * FROM samples ORDER BY oid")]
    finally:
        db.close()
    cells: dict[str, dict] = {}
    for r in rows:
        c = cells.setdefault(r["cell"], {"attempts": 0, "ended": 0, "filled": 0, "partial": 0, "cancelled": 0, "rejected": 0,
                                         "open": 0, "_ticks": [], "_seconds": []})
        c["attempts"] += 1
        outcome = r["outcome"]
        if outcome is None:
            c["open"] += 1
            continue
        c[outcome] += 1
        if outcome in COUNTED:
            c["ended"] += 1
        if outcome in ("filled", "partial") and r["fill_value"] is not None and r["mid"] is not None:
            worse = (r["fill_value"] - r["mid"]) if r["action"] == "open" else (r["mid"] - r["fill_value"])
            c["_ticks"].append(worse / TICK)
            filled = _stamp(r["filled_at"])
            if filled is not None:
                c["_seconds"].append(filled - float(r["submitted_at"]))
    out = {}
    for cell, c in sorted(cells.items()):
        ticks, seconds = c.pop("_ticks"), c.pop("_seconds")
        c["fill_rate"] = round((c["filled"] + c["partial"]) / c["ended"], 4) if c["ended"] else None
        c["mean_fill_vs_mid_ticks"] = round(sum(ticks) / len(ticks), 3) if ticks else None
        c["median_seconds_to_fill"] = round(sorted(seconds)[len(seconds) // 2], 1) if seconds else None
        out[cell] = c
    return {"file": str(path), "rows": len(rows), "cells": out}


def _stamp(text: Any) -> float | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


__all__ = ["Calibration", "Recorder", "report", "FAMILY", "INSTANCE", "SYMBOLS", "SLOTS", "FILE", "cell_of", "outcome_of"]
