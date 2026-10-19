"""THE AUCTION PAPER PROOF (release R2): the practice account proves the event kind's auction orders before real money.

The equity book's route on the practice account (`alpaca-paper`) before its first real `opg` or `cls` order, in two
stages, each sent in the event lane's own send windows (league/equity/schedule.py `event_moments`), the book stepping it
every minute from its event step (league/equity/live.py `_auction_step`):

- STAGE BUY (kv `paper_proof_auction_buy`): ONE WHOLE SHARE of a liquid stock (`SYMBOL`, a NYSE common stock: no ETF,
  its opening and closing crosses on the listing exchange's tape) bought with a LIMIT-ON-OPEN order at 1.25 x its
  previous SIP close (the real entries' own shape and limit) in the `opg` window (09:16-09:27 ET). It passes when the
  order filled at the open (one share at a price, `buy_witness`) and the practice position is up by exactly that share
  (`hold_witness`). It gates every REAL event buy (`buy_passed`).
- STAGE SELL (kv `paper_proof_auction_sell`): that share sold with a MARKET-ON-CLOSE order in the same session's `cls`
  window (close - 13 to close - 11 minutes), the real exits' own shape (a real event exit is a market sale in its
  auction: a limit could only leave a lot held through the auction the shadow sells at). It passes when the sale filled
  (`sell_witness`) and the practice position is back at its baseline (`recon_witness`). A sale that ends its session
  unfilled FAILS the stage (an error alert with the owner's step): new real event buys stop until it passes; real event
  sales never wait on it (an exit is never blocked); the next `cls` window sells again.
- THE GAP (a report, never a gate): once the tape is 16 minutes old, each fill is set beside the listing exchange's
  auction print on the SIP tape (the `O` print at the open, the `6` print at the close; PREREG-EVL-1 section 5) as
  `gap_bp`, signed, positive when the practice fill was worse. Paper fills are the venue's simulation: they prove the
  ROUTE (the order shapes, the venue's answers, the fills as the House reads them), never the calibration.

The durable attempt row is kv `paper_proof_auction` ({schema, status, day, baseline, orders: [{action, body, cid,
status, filled, avg, terminal}], witnesses, gaps}). Every order is written before its POST and looked up by its client
id (`lq-ap-<day>-<nonce>-<n>-b|s`, the equity book's prefix), never sent again blind. One attempt a session. Nothing
here sends an order to the real account. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import math
import time
import urllib.parse
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
KEY = "paper_proof_auction"
BUY_KEY = "paper_proof_auction_buy"
SELL_KEY = "paper_proof_auction_sell"
#: The practice share: a liquid NYSE-listed common stock (its crosses print `O` and `6` on the NYSE tape, code "N").
SYMBOL = "KO"
LISTING_CODE = "N"
LIMIT_RATIO = Decimal("1.25")
CENT = Decimal("0.01")
#: The SIP tape is readable this long after (the Basic plan: 15 minutes and one).
TAPE_DELAY_S = 16 * 60
#: How long after the auction an order still working is waited for (the venue ends an auction order at its auction).
SETTLE_S = 300
BUY_WITNESSES = ("buy_witness", "hold_witness")
#: The gaps beside the tape's prints are read at most this many minutes after both stages passed (a report).
GAP_TRIES = 240
SELL_WITNESSES = ("sell_witness", "recon_witness")


def _dec(value: Any) -> Decimal | None:
    try:
        out = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None
    return out if out.is_finite() else None


class AuctionProof:
    """THE AUCTION PAPER PROOF (the module docstring). `state`: the House's LiveState (kv and events). `account`: the
    practice Account (`alpaca-paper`, league/live/venue.py). `market`: the House's market data (the previous SIP close,
    the tape's prints). `step(now, moments)` once a minute; `buy_passed()` gates every real event buy, `sell_failed()`
    names a failed SELL stage (new real event buys stop), `passed()` both, `status()` for the health page."""

    def __init__(self, state: Any, account: Any, market: Any, *, clock: Callable[[], float] | None = None,
                 record: Callable[..., Any] | None = None, alert: Callable[[str, str], Any] | None = None):
        self.state, self.account, self.market = state, account, market
        self.clock = clock or time.time
        self.record = record or (lambda *a, **k: None)
        self.alert = alert or (lambda *a, **k: None)

    # ------------------------------------------------------------------ the stages
    def _stage(self, key: str) -> dict:
        return dict(self.state.get(key, {}) or {})

    def _row(self) -> dict:
        return dict(self.state.get(KEY, {}) or {})

    def status(self) -> dict:
        return {**self._row(), "stages": {"buy": self._stage(BUY_KEY) or None, "sell": self._stage(SELL_KEY) or None}}

    def buy_passed(self) -> bool:
        row = self._stage(BUY_KEY)
        return row.get("schema") == 1 and row.get("status") == "passed" and all(row.get(k) is True for k in BUY_WITNESSES)

    def sell_passed(self) -> bool:
        row = self._stage(SELL_KEY)
        return row.get("schema") == 1 and row.get("status") == "passed" and all(row.get(k) is True for k in SELL_WITNESSES)

    def sell_failed(self) -> str:
        row = self._stage(SELL_KEY)
        return str(row.get("why") or "the auction paper proof's SELL stage failed") if row.get("status") == "failed" else ""

    def passed(self) -> bool:
        return self.buy_passed() and self.sell_passed()

    def _put(self, row: Mapping[str, Any]) -> None:
        self.state.put(KEY, dict(row))

    def _event(self, what: str, detail: Mapping[str, Any]) -> None:
        try:
            self.state.event(f"{KEY}.{what}", dict(detail))
        except Exception:  # noqa: BLE001 - a record, never the proof's end
            pass

    # ------------------------------------------------------------------ readings
    def _held(self) -> Decimal:
        """The practice account's signed `SYMBOL` shares (0 when none); raises when the positions cannot be read."""
        rows = self.account.positions()
        if not isinstance(rows, list):
            raise ValueError("positions are not a list")
        found = [r for r in rows if isinstance(r, Mapping) and str(r.get("symbol") or "").upper() == SYMBOL]
        if len(found) > 1:
            raise ValueError(f"{SYMBOL} is listed twice")
        if not found:
            return Decimal(0)
        qty = _dec(found[0].get("qty"))
        if qty is None:
            raise ValueError(f"{SYMBOL}'s quantity is unreadable")
        return -abs(qty) if str(found[0].get("side") or "") == "short" else qty

    def _prev_close(self, day: dt.date) -> Decimal:
        """`SYMBOL`'s raw SIP close of the last session before `day` (the real entries' limit is read off the same)."""
        start = (day - dt.timedelta(days=10)).isoformat()
        rows = (self.market.bars([SYMBOL], timeframe="1Day", start=start, adjustment="raw") or {}).get(SYMBOL) or []
        best = None
        for bar in rows:
            t = str(bar.get("t") or "")
            try:
                when = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(NEW_YORK).date()
            except ValueError:
                continue
            close = _dec(bar.get("c"))
            if when < day and close is not None and close > 0 and (best is None or when > best[0]):
                best = (when, close)
        if best is None:
            raise ValueError(f"no SIP daily close of {SYMBOL} before {day}")
        return best[1]

    def _print(self, day: dt.date, at: float, kind: str) -> Decimal | None:
        """The listing exchange's auction print of `SYMBOL` (`O` at the open, `6` at the close) on the SIP tape, or None
        when the tape is not readable yet or holds none. A report only."""
        code = "O" if kind == "open" else "6"
        start = at if kind == "open" else at - 5
        end = at + (300 if kind == "open" else 300)
        if self.clock() < end + TAPE_DELAY_S:
            return None
        path = f"/v2/stocks/{urllib.parse.quote(SYMBOL, safe='.')}/trades"
        params = {"start": _iso(start), "end": _iso(end), "feed": "sip", "limit": 10000}
        try:
            page = self.market._get(path, params, f"trades {SYMBOL}")
        except Exception:  # noqa: BLE001 - the gap is a report: asked again later
            return None
        for trade in (page or {}).get("trades") or []:
            if trade.get("x") == LISTING_CODE and code in (trade.get("c") or []):
                return _dec(trade.get("p"))
        return None

    # ------------------------------------------------------------------ orders
    def _dispatch(self, row: dict, body: dict, *, action: str) -> None:
        work = {"action": action, "body": body, "cid": body["client_order_id"], "at": self.clock(), "status": "unknown",
                "filled": "0", "avg": None, "terminal": False}
        row["orders"].append(work)
        row.update(status=f"{action}_sent", why="awaiting the dispatched order")
        self._put(row)  # committed before the POST: a crash at any later point looks up this same id
        answer = self.account.submit(body, exit=action == "sell")
        self._event(action + "_sent", {"body": body, "ok": answer.ok, "error": answer.error})
        if answer.ok and answer.order:
            work["id"] = answer.order.get("id")
        elif not answer.unknown:
            work.update(status="rejected", terminal=True, rejected=True, error=str(answer.error)[:200])
        row["why"] = answer.error or "the order was accepted; awaiting its auction"
        self._put(row)

    def _refresh(self, row: dict) -> None:
        """The last order brought up to the venue's answer by its client id."""
        work = row["orders"][-1]
        if work.get("terminal"):
            return
        answer = self.account.order_by_client_id(work["cid"])
        if answer is None:
            work["lookups"] = int(work.get("lookups") or 0) + 1
            if work["lookups"] >= 6:
                work.update(status="lost", terminal=True, lost=True)
                self.alert("warning", f"equity: the auction paper proof's practice order {work['cid']} is not at the "
                                      "venue by its client id: given up as lost")
            return
        if str(answer.get("client_order_id") or "") != work["cid"]:
            raise ValueError("the lookup returned another client order id")
        filled = _dec(answer.get("filled_qty")) or Decimal(0)
        work.update(id=answer.get("id"), status=str(answer.get("status") or ""), filled=str(filled),
                    avg=answer.get("filled_avg_price"))
        work["terminal"] = work["status"] in ("filled", "canceled", "expired", "rejected", "done_for_day", "replaced",
                                              "stopped", "suspended")

    def _filled(self, row: Mapping[str, Any], action: str) -> Decimal:
        return sum((Decimal(w.get("filled") or "0") for w in row.get("orders") or [] if w["action"] == action), Decimal(0))

    # ------------------------------------------------------------------ the minute
    def step(self, now: float, moments: Any) -> dict:
        """Advance the one attempt (the module docstring) in the event lane's windows of the day (`moments`:
        league/equity/schedule.py `EventMoments`, None on a day without a session). Never raises for the venue's
        trouble: an unreadable reading is the row's `why`, and nothing new is sent without readable evidence."""
        row = self._row()
        if self.passed():
            if row.get("gaps_open", True) and int(row.get("gap_tries") or 0) < GAP_TRIES:
                row["gap_tries"] = int(row.get("gap_tries") or 0) + 1
                self._gaps(row)
            return row
        if row.get("schema") != 1:
            row = {"schema": 1, "status": "waiting", "attempts": 0, "orders": [], "why": "waiting for an opg window"}
            self._put(row)
        today = dt.datetime.fromtimestamp(float(now), NEW_YORK).date()
        try:
            row = self._advance(row, float(now), today, moments)
        except Exception as exc:  # noqa: BLE001 - never the book's minute's end
            row["why"] = f"auction paper proof: {type(exc).__name__}: {str(exc)[:160]}"
        self._put(row)
        return row

    def _advance(self, row: dict, now: float, today: dt.date, m: Any) -> dict:
        status = row["status"]
        if row.get("orders") and not row["orders"][-1].get("terminal"):
            self._refresh(row)
        if status == "waiting":
            if m is None or not (m.open_send <= now < m.open_until) or row.get("tried_day") == today.isoformat():
                return row
            held = self._held()
            limit = (self._prev_close(today) * LIMIT_RATIO).quantize(CENT, rounding=ROUND_FLOOR)
            row["attempts"] = int(row.get("attempts") or 0) + 1
            attempt = f"lq-ap-{today:%Y%m%d}-{getattr(self.state, 'nonce', '')}-{row['attempts']}"
            row.update(attempt=attempt, day=today.isoformat(), tried_day=today.isoformat(), baseline=str(held),
                       orders=[], buy_witness=False, hold_witness=False, sell_witness=False, recon_witness=False,
                       gaps={})
            body = {"symbol": SYMBOL, "qty": "1", "side": "buy", "type": "limit", "time_in_force": "opg",
                    "limit_price": format(limit, "f"), "client_order_id": attempt + "-b"}
            self._dispatch(row, body, action="buy")
            return row
        work = row["orders"][-1] if row.get("orders") else None
        if status == "buy_sent":
            if work is None or not work.get("terminal"):
                late = row.get("day") != today.isoformat() or (m is not None and now >= m.open_at + SETTLE_S)
                if late and work is not None and work.get("id") and not work.get("cancel_at"):
                    work["cancel_at"] = now   # an opg order still working after its open: cancelled, never left to rest
                    self.account.cancel(work["id"])
                return row
            bought = self._filled(row, "buy")
            if bought != 1 or work.get("avg") in (None, ""):
                row.update(status="waiting", why=f"the limit-on-open practice buy ended {work.get('status')} with "
                                                 f"{bought} filled: the next session's opg window tries again")
                return row
            row["buy_witness"] = True
            held = self._held()
            row["hold_witness"] = held - Decimal(row["baseline"]) == 1
            if not row["hold_witness"]:
                row["why"] = f"the practice account's {SYMBOL} is not its baseline plus the one share bought"
                row["status"] = "held_unreconciled"
                return row
            self._pass_buy(row, today)
            row.update(status="held", why="held: sold at this session's close (market-on-close)")
            return row
        if status in ("held", "held_unreconciled"):
            if status == "held_unreconciled":
                if self._held() - Decimal(row["baseline"]) == 1:
                    row["hold_witness"] = True
                    self._pass_buy(row, today)
                    row["status"] = "held"
                return row
            if m is None or not (m.close_send <= now < m.close_until) or row.get("sell_day") == today.isoformat():
                return row      # (one practice sale a session: a sale that failed tries again at the next cls window)
            body = {"symbol": SYMBOL, "qty": "1", "side": "sell", "type": "market", "time_in_force": "cls",
                    "client_order_id": f"{row['attempt']}-s{sum(1 for w in row['orders'] if w['action'] == 'sell') + 1}"}
            row["sell_day"] = today.isoformat()
            self._dispatch(row, body, action="sell")
            return row
        if status == "sell_sent":
            if work is None or not work.get("terminal"):
                if m is not None and row.get("sell_day") == today.isoformat() and now >= m.close_at + SETTLE_S \
                        and work is not None and work.get("id") and not work.get("cancel_at"):
                    work["cancel_at"] = now
                    self.account.cancel(work["id"])
                return row
            sold = self._filled(row, "sell")
            if sold != 1:
                self._fail_sell(row, today, f"the market-on-close practice sale ended {work.get('status')} with {sold} "
                                            "filled")
                row["status"] = "held"
                return row
            row["sell_witness"] = work.get("avg") not in (None, "")
            row["recon_witness"] = self._held() == Decimal(row["baseline"])
            if row["sell_witness"] and row["recon_witness"]:
                self._pass_sell(row, today)
                row.update(status="passed", why=f"a limit-on-open buy and a market-on-close sale of one {SYMBOL} share, "
                                                "filled at their auctions; positions reconciled")
                return row
            self._fail_sell(row, today, "the sale filled but the practice position is not back at its baseline")
            row["status"] = "sold_unreconciled"
            return row
        if status == "sold_unreconciled":
            if self._held() == Decimal(row["baseline"]):
                row["recon_witness"] = True
                self._pass_sell(row, today)
                row["status"] = "passed"
            return row
        return row

    def _pass_buy(self, row: dict, today: dt.date) -> None:
        if self.buy_passed():
            return
        work = next(w for w in row["orders"] if w["action"] == "buy")
        self.state.put(BUY_KEY, {"schema": 1, "status": "passed", "passed_at": self.clock(), "day": today.isoformat(),
                                 "attempt": row.get("attempt"), "fill": work.get("avg"),
                                 **{k: row.get(k) is True for k in BUY_WITNESSES}})
        self._event("buy_passed", {"day": today.isoformat(), "attempt": row.get("attempt")})
        self.record("live.paper_proof", {"status": "passed", "stage": "buy", "day": today.isoformat(), "kind": "auction"})

    def _pass_sell(self, row: dict, today: dt.date) -> None:
        work = [w for w in row["orders"] if w["action"] == "sell"][-1]
        self.state.put(SELL_KEY, {"schema": 1, "status": "passed", "passed_at": self.clock(), "day": today.isoformat(),
                                  "attempt": row.get("attempt"), "fill": work.get("avg"),
                                  "failures": int(self._stage(SELL_KEY).get("failures") or 0),
                                  **{k: row.get(k) is True for k in SELL_WITNESSES}})
        self._event("sell_passed", {"day": today.isoformat(), "attempt": row.get("attempt")})
        self.record("live.paper_proof", {"status": "passed", "stage": "sell", "day": today.isoformat(), "kind": "auction"})

    def _fail_sell(self, row: dict, today: dt.date, why: str) -> None:
        before = self._stage(SELL_KEY)
        failures = int(before.get("failures") or 0) + 1
        self.state.put(SELL_KEY, {"schema": 1, "status": "failed", "failed_at": self.clock(), "day": today.isoformat(),
                                  "attempt": row.get("attempt"), "failures": failures,
                                  "why": f"the auction paper proof's SELL stage failed on {today.isoformat()}: {why}"})
        self._event("sell_failed", {"why": why, "failures": failures})
        self.record("live.paper_proof", {"status": "failed", "stage": "sell", "day": today.isoformat(), "kind": "auction"})
        self.alert("error", f"equity: the auction paper proof's SELL stage failed ({why}). New real event buys stop until "
                            "it passes; real event sales go on. Owner step: look at the practice account (alpaca-paper) "
                            f"and its {SYMBOL} position and orders; the proof sells again at the next cls window.")

    def _gaps(self, row: dict) -> None:
        """THE GAP of each practice fill beside the listing exchange's auction print (a report; read once the tape is
        16 minutes old)."""
        gaps = dict(row.get("gaps") or {})
        try:
            day = dt.date.fromisoformat(str(row.get("day")))
        except ValueError:
            return
        from ..equity import schedule as ES

        m = ES.event_moments(day)
        if m is None:
            return
        for action, kind, at in (("buy", "open", m.open_at), ("sell", "close", m.close_at)):
            if action in gaps:
                continue
            work = next((w for w in row.get("orders") or [] if w["action"] == action and _dec(w.get("avg"))), None)
            if work is None:
                continue
            px = self._print(day, at, kind)
            if px is None or px <= 0:
                continue
            fill = _dec(work["avg"])
            gap = (fill / px - 1) * 10000 if action == "buy" else (1 - fill / px) * 10000
            gaps[action] = {"fill": str(fill), "print": str(px), "gap_bp": round(float(gap), 2)}
        row["gaps"] = gaps
        row["gaps_open"] = len(gaps) < 2
        self._put(row)


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["AuctionProof", "KEY", "BUY_KEY", "SELL_KEY", "SYMBOL", "BUY_WITNESSES", "SELL_WITNESSES"]
