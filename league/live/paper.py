"""The practice account proves the multi-leg route before real money uses it.

The options-swarm run, Wave 5 (Sept 26, 2026; the plan: "a 1-lot paper structure early in Monday's session before the
first real one", the one order no agent's intent produced that the owner authorized). Each session day, until it has
passed once, the House sends ONE structure to the practice account (`alpaca-paper`): a 1-lot SPY debit call vertical
one strike wide, at the money, on the nearest expiry at least a day out (never an expiring contract), at the natural
price; once it has filled it closes it with one multi-leg order at the natural. The round trip passing (open filled,
positions showing both legs, close filled) is what `passed` means, and real opens wait for it
(`config.json` `live.require_paper_proof`). Paper fills prove the ROUTE (the order's shape, the venue's answers, the
legs' fills as the House reads them), never the calibration: paper fills are synthetic. Every answer is kept in the
live state's events for the owner's record.

THE SINGLE-LEG PROOF (the sprint's review of #390, Sept 26, 2026): `PaperProof(..., kind="single")`, once the vertical has
passed, proves the long call's route the same way: a 1-lot SPY call about 1-2% out of the money on the nearest expiry at
least a day out, bought to open at the natural (the ask) with a single-leg `buy_to_open`, held two minutes, sold to close
at the natural (the bid) with a single-leg `sell_to_close`. Real long calls and puts open only once it has passed.

The session loop runs this proof with real money off and no real-account client. Passing the paper route never
changes real-money configuration, enables a grant, promotes a family, or sends an order to the real venue.

A timed-out or uneven order is cancelled, then read until the venue confirms it is terminal. Each owned leg is
reconciled and closed before another attempt, at most `TRIES` opens per session. Client ids, order bodies and the
initial inventory are committed before dispatch; ambiguous answers and session changes never discard ownership.
An unreadable order or position snapshot cannot pass the proof. Unrelated paper positions are left alone.

THE STOCK PROOF (release E1, A8.7 as staged by A10.1; `StockPaperProof`): the equity book's route on the practice
account before its first real order, in two stages, each in the equity book's OPEN window (the book passes its
`league.equity.schedule.Moments`; league/live never imports league.equity here). Stage BUY (kv `paper_proof_stock_buy`):
a FRACTIONAL share of SPY (about `STOCK_USD`) bought with a marketable limit (the ask plus `STOCK_COLLAR_BP`) from the
open window's first send (09:30:30 ET) to the book's entry cut-off (09:45; cancelled if it has not filled by then); it
passes on the buy's fill (a fractional quantity at a price), the attempt's own lot row and the position reconciled to it
(the paper account's SPY up by exactly that), and gates every REAL equity BUY. Stage SELL (kv `paper_proof_stock_sell`):
the practice lot sold in the next session's open window (the min hold kept: never in the session it was bought; a
marketable limit at the bid less the collar; an unfilled sale is cancelled after `STOCK_REPRICE_S` and, once the venue
says it is terminal, sent again for what is left with a wider collar, never past `STOCK_MAX_COLLAR_BP`, until the
window ends at 15:55); it passes once the sale's fills (the whole lot), the account's FILL activities naming both orders
for the same quantities and reconciliation (the account's SPY back at its baseline) witness the round trip, and gates
every REAL equity SALE (in that window the practice sale goes first: the book steps the proof before its own windows,
and real exits wait for the pass). A SELL stage that ends its window without passing is FAILED (kv status "failed",
an alarm with the owner's step): real lots stay held and new real buys stop until it passes; the next open window buys
again (stage BUY stays passed) and the one after sells. The durable attempt row is kv `paper_proof_stock`. Client ids
`lq-pp-...` (the equity book's prefix: never `lv-`). Only the equity book waits on it; options entries never do.
"""

from __future__ import annotations

import datetime as dt
import math
import time
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import numpy as np

from .real import RLeg, limit_price, single_body, structure_fill, ROrder
from .state import LiveState
from .venue import TERMINAL, Account, dec

WAIT_MINUTES = 8
HOLD_MINUTES = 2
TRIES = 3
ROOT = "SPY"


#: The single-leg proof's call: out of the money by about this share of the spot (1-2%).
SINGLE_OTM = (0.01, 0.02)


class PaperProof:
    def __init__(self, state: LiveState, account: Account, *, record: Callable[..., Any] | None = None,
                 clock: Callable[[], float] | None = None, kind: str = "vertical"):
        if kind not in ("vertical", "single"):
            raise ValueError(kind)
        self.state, self.account = state, account
        self.record = record or (lambda *a, **k: None)
        self.clock = clock or time.time
        self.kind = kind
        self.key = "paper_proof" if kind == "vertical" else "paper_proof_single"

    def status(self) -> dict:
        return dict(self.state.get(self.key, {}) or {})

    def passed(self) -> bool:
        row = self.status()
        return (row.get("schema") == 2 and row.get("status") == "passed"
                and row.get("open_witness") is True and row.get("close_witness") is True)

    def held_symbols(self) -> list[str]:
        """Keep an unfinished attempt's contracts in the read window across session changes."""
        row = self.status()
        return list(row.get("legs") or []) if not self.passed() else []

    def _put(self, row: Mapping[str, Any]) -> None:
        self.state.put(self.key, dict(row))

    @staticmethod
    def _new(day: str, tries: int = 0) -> dict:
        return {"schema": 2, "day": day, "status": "waiting", "tries": tries, "orders": []}

    def _positions(self) -> dict[str, Decimal]:
        rows = self.account.positions()
        if not isinstance(rows, list):
            raise ValueError("positions are not a list")
        out = {}
        for item in rows:
            symbol, qty = str(item["symbol"]), Decimal(str(item["qty"]))
            if not symbol or not qty.is_finite() or symbol in out:
                raise ValueError("invalid or duplicate position")
            out[symbol] = qty
        return out

    @staticmethod
    def _owned(row: Mapping[str, Any]) -> dict[str, Decimal]:
        out = {symbol: Decimal(0) for symbol in row.get("legs") or []}
        for order in row.get("orders") or []:
            for symbol, qty in (order.get("fills") or {}).items():
                out[symbol] += Decimal(str(qty))
        return out

    @staticmethod
    def _fills(work: Mapping[str, Any], answer: Mapping[str, Any]) -> dict[str, str]:
        """Cumulative signed contracts on this order only; never infer fills from account inventory."""
        body = work["body"]
        requested = body.get("legs") or [body]
        actual = answer.get("legs") or [answer]
        by_symbol = {str(leg.get("symbol")): leg for leg in actual}
        if (len(by_symbol) != len(actual) or set(by_symbol) != {leg["symbol"] for leg in requested}
                or Decimal(str(answer.get("qty"))) != Decimal(str(body["qty"]))):
            raise ValueError("the order's contracts or quantity differ from the dispatched request")
        out = {}
        for leg in requested:
            symbol = leg["symbol"]
            value = by_symbol.get(symbol)
            if value is None or value.get("side") != leg["side"]:
                raise ValueError("order does not identify every requested leg and side")
            qty = Decimal(str(value.get("filled_qty") or "0"))
            target = Decimal(str(body["qty"])) * Decimal(str(leg.get("ratio_qty") or "1"))
            previous = abs(Decimal(str((work.get("fills") or {}).get(symbol) or "0")))
            if not qty.is_finite() or qty < previous or qty < 0 or qty > target or qty != qty.to_integral_value():
                raise ValueError("invalid or regressed cumulative leg fill")
            out[symbol] = str(qty if leg["side"] == "buy" else -qty)
        return out

    def _dispatch(self, row: dict, body: dict, *, action: str, mi: int) -> dict:
        work = {"action": action, "body": body, "cid": body["client_order_id"], "at": self.clock(),
                "minute": mi, "status": "unknown", "fills": {}, "terminal": False}
        row["orders"].append(work)
        row.update(status="open_sent" if action == "open" else "close_sent", why="awaiting the dispatched order")
        # FULL synchronous SQLite commit before POST. A crash at any later instruction looks up this same id.
        self._put(row)
        answer = self.account.submit(body, exit=action != "open")
        self._event(action + "_sent", {"body": body, "ok": answer.ok, "error": answer.error, "answer": answer.order})
        if answer.ok and answer.order:
            work["id"] = answer.order.get("id")
        elif not answer.unknown:
            # An explicit rejection/unsent request owns nothing. A timeout, missing answer or process death does not.
            work.update(status="rejected", terminal=True, rejected=True)
        row["why"] = answer.error or "the order was accepted; awaiting fill and inventory witnesses"
        self._put(row)
        return row

    def _refresh(self, row: dict) -> None:
        work = row["orders"][-1]
        if work.get("rejected"):
            return
        answer = self.account.order_by_client_id(work["cid"])
        if answer is None:
            row["why"] = "the dispatched order is not yet found; its outcome remains unresolved"
            self._put(row)
            return
        if str(answer.get("client_order_id") or "") != work["cid"]:
            raise ValueError("the lookup returned another client order id")
        work["fills"] = self._fills(work, answer)
        work.update(id=answer.get("id"), status=str(answer.get("status") or ""))
        work["terminal"] = work["status"] in TERMINAL
        work["route_full"] = (work["action"] in ("open", "close") and
                              self._filled(answer, row, work["action"] == "close"))
        changed = work.get("answer") != answer
        work["answer"] = dict(answer)
        with self.state.transaction():
            self._put(row)
            if changed:
                self._event("order_observed", {"cid": work["cid"], "action": work["action"], "answer": answer})
        if work["terminal"]:
            return
        values = [abs(Decimal(qty)) for qty in work["fills"].values()]
        uneven = len(values) > 1 and max(values) != min(values)
        aged = self.clock() - float(work["at"]) >= WAIT_MINUTES * 60
        if (uneven or aged) and work.get("id"):
            if self.clock() - float(work.get("cancel_at") or 0) >= 60:
                work["cancel_at"] = self.clock()
                self._put(row)  # a lost cancel answer is also recovered by this order's id
                ok, why = self.account.cancel(work["id"])
                self._event("cancel", {"cid": work["cid"], "ok": ok, "why": why})
            row["why"] = "waiting for the venue to confirm the order is terminal after cancellation"
            self._put(row)

    def _inventory(self, row: dict, positions: Mapping[str, Decimal]) -> bool:
        owned = self._owned(row)
        for symbol, qty in owned.items():
            actual = positions.get(symbol, Decimal(0)) - Decimal(row["baseline"][symbol])
            if actual != qty:
                row["why"] = f"paper inventory disagrees with this attempt's recorded fills for {symbol}"
                self._put(row)
                return False
        return True

    def _finish_failed_attempt(self, row: dict, day: str) -> dict:
        self._event("attempt_flat", {"attempt": row, "day": day})
        tries = int(row.get("tries") or 0) if row.get("day") == day else 0
        fresh = self._new(day, tries)
        if tries >= TRIES:
            fresh.update(status="failed", why="paper attempts ended flat without a witnessed multi-leg round trip")
            self.record("live.paper_proof", {"status": "failed", "day": day, "why": fresh["why"], "kind": self.kind})
        self._put(fresh)
        return fresh

    def _close(self, row: dict, *, snap: Any, chain: Any, mi: int, cleanup: bool) -> dict:
        owned = self._owned(row)
        if snap is None:
            return row
        # Buy back an owned short before selling an owned long. Unrelated account holdings are never touched.
        remaining = sorted(((s, q) for s, q in owned.items() if q), key=lambda item: item[1])
        symbols = [remaining[0][0]] if cleanup else list(row["legs"])
        idx = [chain.column(s) for s in symbols]
        if not idx or min(idx) < 0 or not all(bool(snap.valid[i]) for i in idx):
            row["why"] = "an owned contract has no current quote for its close"
            self._put(row)
            return row
        cid = f"{row['attempt']}-c{sum(w['action'] != 'open' for w in row['orders']) + 1}"
        body = {"type": "limit", "time_in_force": "day", "client_order_id": cid}
        if self.kind == "single" and not cleanup:
            bid = float(snap.bid[idx[0]])
            if not (math.isfinite(bid) and bid > 0):
                row["why"] = "the proof's call has no bid to sell it at"
                self._put(row)
                return row
            body = _single(symbols[0], "close", bid, cid)
        elif cleanup:
            symbol, qty = remaining[0]
            price = float(snap.ask[idx[0]] if qty < 0 else snap.bid[idx[0]])
            if not math.isfinite(price) or price < 0:
                return row
            body.update(symbol=symbol, qty=str(abs(qty)), side="buy" if qty < 0 else "sell",
                        position_intent="buy_to_close" if qty < 0 else "sell_to_close", limit_price=f"{max(0.01, price):.2f}")
        else:
            natural = float(snap.bid[idx[0]]) - float(snap.ask[idx[1]])
            if not math.isfinite(natural):
                return row
            body.update(order_class="mleg", qty="1", limit_price=limit_price(max(0.0, round(natural, 2)), "close"),
                        legs=[{"symbol": symbols[0], "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_close"},
                              {"symbol": symbols[1], "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_close"}])
        return self._dispatch(row, body, action="cleanup" if cleanup else "close", mi=mi)

    def step(self, *, day: str, mi: int, snap: Any, chain: Any, start_minute: int = 5) -> dict:
        """Advance one durable attempt. A new session never discards unresolved orders or owned contracts."""
        row = self.status()
        if self.passed():
            return row
        if row.get("schema") != 2:
            if row and (row.get("tries") or row.get("legs") or row.get("status") not in (None, "waiting")):
                row.update(status="blocked", why="legacy paper proof has no inventory/dispatch witnesses; owner reconciliation required")
                self._put(row)
                return row
            row = self._new(day)
        if row["status"] == "blocked":
            return row
        # Reset only a clean idle attempt. Active work remains owned even if it is from another session.
        if row["status"] in ("waiting", "failed") and not row.get("orders") and row.get("day") != day:
            row = self._new(day)
        if row["status"] == "failed":
            return row
        try:
            if row.get("orders"):
                self._refresh(row)
            positions = self._positions()
        except Exception as exc:  # noqa: BLE001 - no new dispatch or pass without readable evidence
            row["why"] = f"paper proof evidence unreadable: {str(exc)[:160]}"
            self._put(row)
            return row
        if row["status"] == "waiting":
            if mi < start_minute or snap is None:
                self._put(row)
                return row
            legs = self._single(snap, chain) if self.kind == "single" else self._legs(snap, chain)
            if legs is None:
                row["why"] = ("no SPY call 1-2% out of the money is quoted a day or more out" if self.kind == "single"
                              else "no SPY vertical one strike wide is quoted a day or more out")
                self._put(row)
                return row
            symbols = [leg[0] for leg in legs]
            if any(positions.get(symbol, Decimal(0)) for symbol in symbols):
                row["why"] = "the selected proof contracts already belong to another paper position"
                self._put(row)
                return row
            natural = legs[0][1] - (legs[1][2] if len(legs) > 1 else 0.0)
            if not (math.isfinite(natural) and natural > 0):
                return row
            row["tries"] = int(row.get("tries") or 0) + 1
            prefix = "lv-ps" if self.kind == "single" else "lv-pp"
            row.update(legs=symbols, baseline={s: str(positions.get(s, Decimal(0))) for s in symbols},
                       attempt=f"{prefix}-{day.replace('-', '')}-{self.state.nonce}-{row['tries']}",
                       open_witness=False, close_witness=False)
            if self.kind == "single":
                body = _single(symbols[0], "open", natural, row["attempt"] + "-o")
            else:
                body = {"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": limit_price(round(natural, 2), "open"),
                        "time_in_force": "day", "client_order_id": row["attempt"] + "-o",
                        "legs": [{"symbol": symbols[0], "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
                                 {"symbol": symbols[1], "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"}]}
            return self._dispatch(row, body, action="open", mi=mi)
        if not row.get("orders") or not self._inventory(row, positions):
            return row
        work = row["orders"][-1]
        if not work.get("terminal"):
            return row
        owned = self._owned(row)
        held = [Decimal(1)] if self.kind == "single" else [Decimal(1), Decimal(-1)]
        if work["action"] == "open" and work.get("route_full") and list(owned.values()) == held:
            if not row.get("open_witness"):
                row.update(status="open_filled", open_witness=True, filled_at=self.clock())
                self._event("open_witness", {"cid": work["cid"], "owned": owned})
                self._put(row)
            if self.clock() - float(row["filled_at"]) >= HOLD_MINUTES * 60:
                return self._close(row, snap=snap, chain=chain, mi=mi, cleanup=False)
            return row
        flat = not any(owned.values())
        if work["action"] == "close" and work.get("route_full") and row.get("open_witness") and flat:
            row.update(status="passed", close_witness=True, passed_at=self.clock(),
                       why=(f"a witnessed {'single-leg' if self.kind == 'single' else 'multi-leg'} open and close returned "
                            "the owned contracts to their baseline"))
            self._put(row)
            self._event("close_witness", {"cid": work["cid"], "owned": owned})
            self.record("live.paper_proof", {"status": "passed", "day": day, "kind": self.kind})
            return row
        if flat:
            return self._finish_failed_attempt(row, day)
        row["status"] = "recovering"
        self._put(row)
        return self._close(row, snap=snap, chain=chain, mi=mi, cleanup=True)

    def _filled(self, order: Any, row: Mapping[str, Any], closing: bool) -> bool:
        if not isinstance(order, Mapping):
            return False
        if self.kind == "single":
            # A single-leg order's own fields (its `legs` is null): the whole contract filled, at a price.
            filled = order.get("filled_qty")
            try:
                return Decimal(str(filled)) >= 1 and order.get("filled_avg_price") not in (None, "")
            except (ArithmeticError, ValueError):
                return False
        legs = [RLeg(s, 1 if i == 0 else -1, 1, True, 0.0, "", 0) for i, s in enumerate(row.get("legs") or [])]
        fake = ROrder(0, "", "", "", "close" if closing else "open", "debit_vertical", ROOT, legs, 1, 0.0, "0", None, 0.0, "", 0)
        fill = structure_fill(fake, order)
        return fill is not None and fill[0] >= 1 and not fill[3]

    @staticmethod
    def _single(snap: Any, chain: Any) -> tuple[tuple[str, float, float]] | None:
        """The nearest expiry a day or more out: the call whose strike is nearest 1.5% over the spot, within 1-2% out of
        the money, with a two-sided quote (ask, bid)."""
        spot = float(snap.spot)
        if not math.isfinite(spot):
            return None
        ok = snap.valid & snap.is_call & (snap.dte >= 1)
        if not ok.any():
            return None
        first = int(snap.dte[ok].min())
        low, high = spot * (1 + SINGLE_OTM[0]), spot * (1 + SINGLE_OTM[1])
        pool = np.flatnonzero(ok & (snap.dte == first) & (snap.strike >= low) & (snap.strike <= high) & (snap.bid > 0))
        if pool.size == 0:
            return None
        i = int(pool[np.argmin(np.abs(snap.strike[pool] - spot * (1 + sum(SINGLE_OTM) / 2)))])
        return ((chain.symbol[i], float(snap.ask[i]), float(snap.bid[i])),)

    @staticmethod
    def _legs(snap: Any, chain: Any) -> tuple[tuple[str, float, float], tuple[str, float, float]] | None:
        """The nearest expiry a day or more out: (long call at the money, short call one strike above), each (symbol,
        ask, bid)."""
        spot = float(snap.spot)
        if not math.isfinite(spot):
            return None
        ok = snap.valid & snap.is_call & (snap.dte >= 1)
        if not ok.any():
            return None
        first = int(snap.dte[ok].min())
        pool = np.flatnonzero(ok & (snap.dte == first))
        strikes = snap.strike[pool]
        order = np.argsort(strikes)
        pool, strikes = pool[order], strikes[order]
        above = np.flatnonzero(strikes >= spot)
        if above.size == 0 or above[0] + 1 >= pool.size:
            return None
        i, j = int(pool[above[0]]), int(pool[above[0] + 1])
        if abs(float(snap.strike[j]) - float(snap.strike[i]) - 1.0) > 1e-9:
            return None
        return ((chain.symbol[i], float(snap.ask[i]), float(snap.bid[i])), (chain.symbol[j], float(snap.ask[j]), float(snap.bid[j])))

    def _event(self, what: str, detail: Mapping[str, Any]) -> None:
        self.state.event(f"{self.key}.{what}", dict(detail))


def _single(symbol: str, action: str, price: float, cid: str) -> dict:
    """The single-leg proof's order body, built by the real route's own `single_body` so the two cannot drift."""
    order = ROrder(0, cid, "paper-proof", "paper-proof", action, "long_call", ROOT, [RLeg(symbol, 1, 1, True, 0.0, "", 0)],
                   1, float(price), f"{float(price):.2f}", None, 0.0, "", 0)
    return single_body(order)


# ------------------------------------------------------------------------------------- the stock proof (E1, A8.7, A10)
#: The durable attempt row (the round trip under way), and the two stages' records (A10.1): BUY gates every real equity
#: buy, SELL every real equity sale.
STOCK_KEY = "paper_proof_stock"
STOCK_BUY_KEY = "paper_proof_stock_buy"
STOCK_SELL_KEY = "paper_proof_stock_sell"
STOCK_SYMBOL = "SPY"
#: The proof buys about this many dollars of SPY: a fractional share.
STOCK_USD = Decimal("25")
#: Shares are sent to six places (league/equity/config.py `QTY_PLACES`); prices on the cent.
STOCK_PLACES, CENT = Decimal("0.000001"), Decimal("0.01")
#: The marketable limit's collar in basis points (the equity book's ETF entry collar), widened by a step for each sale
#: re-sent, never past the maximum (the book's ETF maximum).
STOCK_COLLAR_BP, STOCK_COLLAR_STEP_BP, STOCK_MAX_COLLAR_BP = 10, 10, 50
#: An unfilled sale is cancelled after this long (then sent again for what is left once it is terminal).
STOCK_REPRICE_S = 60
STOCK_TOLERANCE = Decimal("1e-9")
#: What each stage's pass needs (A10.1): BUY its fill, the attempt's own lot row and the position reconciled to it;
#: SELL the whole lot sold, the account's FILL activities naming both orders, and the position back at its baseline.
STOCK_BUY_WITNESSES = ("buy_witness", "hold_witness")
STOCK_WITNESSES = ("buy_witness", "hold_witness", "sell_witness", "activity_witness", "recon_witness")
NEW_YORK = ZoneInfo("America/New_York")


class StockPaperProof:
    """THE STOCK PROOF, staged (A10.1; the module docstring): `step(now, market=..., window=...)` once a minute from the
    equity book's tick, BEFORE the book's own windows (so in the SELL stage's window the practice sale goes first);
    `window` is the book's `league.equity.schedule.Moments` of the day (`open_send`, `entry_until`, `exit_until`; None
    on a day without a session), so the proof trades in exactly the book's OPEN window. `buy_passed()` gates every real
    equity BUY, `sell_passed()` every real equity SALE, `sell_failed()` names a SELL stage that failed (new real buys
    stop until it passes); `passed()` is both; `status()` for the health page."""

    def __init__(self, state: LiveState, account: Account, *, record: Callable[..., Any] | None = None,
                 clock: Callable[[], float] | None = None, alert: Callable[[str, str], Any] | None = None,
                 after: Callable[[], bool] | None = None):
        self.state, self.account = state, account
        self.record = record or (lambda *a, **k: None)
        self.alert = alert or (lambda *a, **k: None)
        self.clock = clock or time.time
        #: Whether the practice account's earlier proofs (the options route's `PaperProof`s) have passed: ONE PROOF AT A
        #: TIME on the practice account, the options route's first; a new attempt starts only then (None: no wait).
        self.after = after
        self.key = STOCK_KEY

    def _row(self) -> dict:
        return dict(self.state.get(self.key, {}) or {})

    def _stage(self, key: str) -> dict:
        return dict(self.state.get(key, {}) or {})

    def status(self) -> dict:
        return {**self._row(), "stages": {"buy": self._stage(STOCK_BUY_KEY) or None,
                                          "sell": self._stage(STOCK_SELL_KEY) or None}}

    def buy_passed(self) -> bool:
        """Stage BUY (A10.1): a witnessed fractional SPY buy in an open window, its position reconciled."""
        row = self._stage(STOCK_BUY_KEY)
        return row.get("schema") == 1 and row.get("status") == "passed" and all(row.get(k) is True
                                                                                 for k in STOCK_BUY_WITNESSES)

    def sell_passed(self) -> bool:
        """Stage SELL (A10.1): the practice lot sold in a later session's open window, every witness agreeing."""
        row = self._stage(STOCK_SELL_KEY)
        return row.get("schema") == 1 and row.get("status") == "passed" and all(row.get(k) is True for k in STOCK_WITNESSES)

    def sell_failed(self) -> str:
        """Why the SELL stage failed and has not passed since ("" when it has not failed): new real buys stop."""
        row = self._stage(STOCK_SELL_KEY)
        return str(row.get("why") or "the stock paper proof's SELL stage failed") if row.get("status") == "failed" else ""

    def passed(self) -> bool:
        return self.buy_passed() and self.sell_passed()

    @staticmethod
    def _new() -> dict:
        return {"schema": 1, "status": "waiting", "attempts": 0, "orders": [], "why": "waiting for an open window"}

    def _put(self, row: Mapping[str, Any]) -> None:
        self.state.put(self.key, dict(row))

    def _event(self, what: str, detail: Mapping[str, Any]) -> None:
        self.state.event(f"{self.key}.{what}", dict(detail))

    # ------------------------------------------------------------------ evidence
    def _held(self) -> Decimal:
        """The paper account's signed SPY shares (0 when it holds none); raises when the positions cannot be read."""
        rows = self.account.positions()
        if not isinstance(rows, list):
            raise ValueError("positions are not a list")
        found = [r for r in rows if isinstance(r, Mapping) and str(r.get("symbol") or "").upper() == STOCK_SYMBOL]
        if len(found) > 1:
            raise ValueError(f"{STOCK_SYMBOL} is listed twice")
        if not found:
            return Decimal(0)
        qty = dec(found[0].get("qty"))
        if qty is None:
            raise ValueError(f"{STOCK_SYMBOL}'s quantity is unreadable")
        return -abs(qty) if str(found[0].get("side") or "") == "short" else qty

    @staticmethod
    def _filled(row: Mapping[str, Any], action: str) -> Decimal:
        return sum((Decimal(w.get("filled") or "0") for w in row.get("orders") or [] if w["action"] == action), Decimal(0))

    def _owned(self, row: Mapping[str, Any]) -> Decimal:
        """What this attempt holds by its own orders' fills (never inferred from the account)."""
        return self._filled(row, "buy") - self._filled(row, "sell")

    def _reconciled(self, row: Mapping[str, Any], held: Decimal) -> bool:
        return abs(held - Decimal(row.get("baseline") or "0") - self._owned(row)) <= STOCK_TOLERANCE

    @staticmethod
    def _quote(market: Any) -> tuple[Decimal, Decimal]:
        """SPY's (bid, ask) now; ValueError when either is not a positive price or they cross."""
        q = ((market.stocks([STOCK_SYMBOL]) or {}).get(STOCK_SYMBOL) or {}).get("latestQuote") or {}
        bid, ask = dec(q.get("bp")), dec(q.get("ap"))
        if bid is None or ask is None or bid <= 0 or ask < bid:
            raise ValueError(f"no two-sided {STOCK_SYMBOL} quote")
        return bid, ask

    # ------------------------------------------------------------------ the stages' records
    def _pass_buy(self, row: dict, today: dt.date) -> None:
        if self.buy_passed():
            return
        work = next(w for w in row["orders"] if w["action"] == "buy" and Decimal(w.get("filled") or "0") > 0)
        self.state.put(STOCK_BUY_KEY, {"schema": 1, "status": "passed", "passed_at": self.clock(), "day": today.isoformat(),
                                       "attempt": row.get("attempt"), "lot": {"qty": str(self._filled(row, "buy")),
                                                                              "avg": work.get("avg"), "cid": work["cid"]},
                                       **{k: row.get(k) is True for k in STOCK_BUY_WITNESSES}})
        self._event("buy_passed", {"attempt": row.get("attempt"), "day": today.isoformat()})
        self.record("live.paper_proof", {"status": "passed", "stage": "buy", "day": today.isoformat(), "kind": "stock"})

    def _pass_sell(self, row: dict, today: dt.date) -> None:
        self.state.put(STOCK_SELL_KEY, {"schema": 1, "status": "passed", "passed_at": self.clock(), "day": today.isoformat(),
                                        "attempt": row.get("attempt"),
                                        "failures": int(self._stage(STOCK_SELL_KEY).get("failures") or 0),
                                        **{k: row.get(k) is True for k in STOCK_WITNESSES}})
        self._event("passed", {k: row[k] for k in STOCK_WITNESSES})
        self.record("live.paper_proof", {"status": "passed", "stage": "sell", "day": today.isoformat(), "kind": "stock"})

    def _fail_sell(self, row: dict, today: dt.date, why: str) -> None:
        """The SELL stage failed this session (A10.1): real lots stay held, new real buys stop until it passes, and the
        owner is told once a failure with the step to take."""
        before = self._stage(STOCK_SELL_KEY)
        failures = int(before.get("failures") or 0) + 1
        self.state.put(STOCK_SELL_KEY, {"schema": 1, "status": "failed", "failed_at": self.clock(),
                                        "day": today.isoformat(), "attempt": row.get("attempt"), "failures": failures,
                                        "why": f"the stock paper proof's SELL stage failed on {today.isoformat()}: {why}"})
        self._event("sell_failed", {"attempt": row.get("attempt"), "why": why, "failures": failures})
        self.record("live.paper_proof", {"status": "failed", "stage": "sell", "day": today.isoformat(), "kind": "stock"})
        self.alert("error", f"equity: the stock paper proof's SELL stage failed ({why}). Real equity lots stay held and new "
                            "real equity buys stop until it passes. Owner step: look at the practice account "
                            f"(alpaca-paper) and its {STOCK_SYMBOL} position and orders; the proof tries again at the "
                            "next open window.")

    # ------------------------------------------------------------------ orders
    def _dispatch(self, row: dict, body: dict, *, action: str) -> dict:
        work = {"action": action, "body": body, "cid": body["client_order_id"], "at": self.clock(), "status": "unknown",
                "filled": "0", "avg": None, "terminal": False}
        row["orders"].append(work)
        row.update(status=f"{action}_sent", why="awaiting the dispatched order")
        self._put(row)  # committed before the POST: a crash at any later point looks up this same id
        answer = self.account.submit(body, exit=action == "sell")
        self._event(action + "_sent", {"body": body, "ok": answer.ok, "error": answer.error, "answer": answer.order})
        if answer.ok and answer.order:
            work["id"] = answer.order.get("id")
        elif not answer.unknown:
            work.update(status="rejected", terminal=True, rejected=True)
        row["why"] = answer.error or "the order was accepted; awaiting its fill"
        self._put(row)
        return row

    def _refresh(self, row: dict, *, late: bool) -> None:
        """The last order brought up to the venue's answer by its client id; one still working when `late` (its window
        ended) and a sale working past `STOCK_REPRICE_S` are cancelled (at most once a minute)."""
        work = row["orders"][-1]
        if work.get("terminal"):
            return
        answer = self.account.order_by_client_id(work["cid"])
        if answer is None:
            row["why"] = "the dispatched order is not yet found; its outcome remains unresolved"
            return
        if str(answer.get("client_order_id") or "") != work["cid"]:
            raise ValueError("the lookup returned another client order id")
        filled = dec(answer.get("filled_qty")) or Decimal(0)
        if filled < Decimal(work.get("filled") or "0") or filled > Decimal(work["body"]["qty"]):
            raise ValueError("an invalid or regressed cumulative fill")
        work.update(id=answer.get("id"), status=str(answer.get("status") or ""), filled=str(filled),
                    avg=answer.get("filled_avg_price"))
        work["terminal"] = work["status"] in TERMINAL
        if work["terminal"]:
            self._event("order_observed", {"cid": work["cid"], "answer": dict(answer)})
            return
        stale = late or (work["action"] == "sell" and self.clock() - float(work["at"]) >= STOCK_REPRICE_S)
        if stale and work.get("id") and self.clock() - float(work.get("cancel_at") or 0) >= 60:
            work["cancel_at"] = self.clock()
            self._put(row)  # a lost cancel answer is recovered by the order's id too
            ok, why = self.account.cancel(work["id"])
            self._event("cancel", {"cid": work["cid"], "ok": ok, "why": why})
            row["why"] = "waiting for the venue to confirm the order is terminal after its cancel"

    def _activities(self, row: Mapping[str, Any]) -> bool:
        """Whether the account's FILL activities name this attempt's buy and sale for exactly their filled quantities."""
        after = (dt.date.fromisoformat(row["buy_day"]) - dt.timedelta(days=1)).isoformat()
        rows = self.account.activities(["FILL"], after=after)
        by_order: dict[str, Decimal] = {}
        for r in rows:
            qty = dec(r.get("qty"))
            if r.get("order_id") and qty is not None:
                by_order[str(r["order_id"])] = by_order.get(str(r["order_id"]), Decimal(0)) + abs(qty)
        for work in row.get("orders") or []:
            want = Decimal(work.get("filled") or "0")
            if want > 0 and abs(by_order.get(str(work.get("id")), Decimal(0)) - want) > STOCK_TOLERANCE:
                return False
        return self._filled(row, "buy") > 0

    # ------------------------------------------------------------------ the minute
    def step(self, now: float, *, market: Any, window: Any = None) -> dict:
        """Advance the one durable attempt (the module docstring) inside the book's OPEN window of the day (`window`:
        the book's `schedule.Moments`, None on a day without a session). Never raises for the venue's trouble: an
        unreadable reading is the row's `why`, and nothing new is sent without readable evidence. A minute with nothing
        to do (`_idle`) reads nothing of the practice account."""
        row = self._row()
        if self.passed():
            return row
        if row.get("schema") != 1:
            row = self._new()
            self._put(row)
        today = dt.datetime.fromtimestamp(now, NEW_YORK).date()
        if self._idle(row, today, now, window):
            return row
        try:
            if row.get("orders"):
                work = row["orders"][-1]
                ends = getattr(window, "entry_until" if work["action"] == "buy" else "exit_until", None)
                late = window is None or str(row.get(f"{work['action']}_day")) != today.isoformat() or now >= float(ends)
                self._refresh(row, late=late)
            held = self._held()
        except Exception as exc:  # noqa: BLE001 - no new dispatch or pass without readable evidence
            row["why"] = f"stock paper proof evidence unreadable: {str(exc)[:160]}"
            self._put(row)
            return row
        try:
            row = self._advance(row, held, today, now, window, market)
        except Exception as exc:  # noqa: BLE001
            row["why"] = f"stock paper proof: {type(exc).__name__}: {str(exc)[:160]}"
        self._put(row)
        return row

    def _idle(self, row: Mapping[str, Any], today: dt.date, now: float, window: Any) -> bool:
        """Whether this minute has nothing for the proof to do, so the practice account is not read at all (the book
        steps the proof every minute, around the clock, until both stages pass): no order of it is still working, and
        it is waiting outside a BUY window it may still use, or holding its lot with stage BUY passed outside the SELL
        stage's window (the buy's own session, a day without a session, before the window's first send, or after its
        end once the day's failure is recorded). Exactly the minutes in which `_advance` would return the row as it
        is."""
        work = row["orders"][-1] if row.get("orders") else None
        if work is not None and not work.get("terminal"):
            return False
        opened = window is not None and float(window.open_send) <= now
        if row.get("status") == "waiting":
            return not opened or row.get("tried_day") == today.isoformat() or now >= float(window.entry_until)
        if row.get("status") == "held" and self.buy_passed():
            if not opened or today.isoformat() <= str(row.get("buy_day")):
                return True
            return now >= float(window.exit_until) and row.get("sell_day") != today.isoformat()
        return False

    def _advance(self, row: dict, held: Decimal, today: dt.date, now: float, window: Any, market: Any) -> dict:
        status = row["status"]
        opened = window is not None and float(window.open_send) <= now
        if status == "waiting":
            if not opened or row.get("tried_day") == today.isoformat() or now >= float(window.entry_until):
                return row
            if self.after is not None and not self.after():
                row["why"] = "waiting for the options route's paper proofs on the practice account (one proof at a time)"
                return row
            _, ask = self._quote(market)
            limit = (ask * (1 + Decimal(STOCK_COLLAR_BP) / 10000)).quantize(CENT, rounding=ROUND_UP)
            qty = (STOCK_USD / limit).quantize(STOCK_PLACES, rounding=ROUND_DOWN)
            row["attempts"] = int(row.get("attempts") or 0) + 1
            attempt = f"lq-pp-{today:%Y%m%d}-{self.state.nonce}-{row['attempts']}"
            row.update(attempt=attempt, buy_day=today.isoformat(), tried_day=today.isoformat(), baseline=str(held),
                       orders=[], sell_day=None, **{k: False for k in STOCK_WITNESSES})
            body = {"symbol": STOCK_SYMBOL, "qty": format(qty, "f"), "side": "buy", "type": "limit", "time_in_force": "day",
                    "limit_price": format(limit, "f"), "client_order_id": attempt + "-b"}
            return self._dispatch(row, body, action="buy")
        work = row["orders"][-1] if row.get("orders") else None
        if work is None or not work.get("terminal"):
            return row
        if status == "buy_sent":
            bought = self._filled(row, "buy")
            if bought <= 0:
                row.update(status="waiting", why="the buy ended unfilled: the next session's open window tries again")
                return row
            row["buy_witness"] = (bought != bought.to_integral_value() and work.get("avg") not in (None, "")
                                  and work["status"] in ("filled", "canceled", "expired", "done_for_day"))
            row.update(status="held", why="held: sold in the next session's open window")
            self._event("buy_witness", {"cid": work["cid"], "filled": str(bought), "avg": work.get("avg")})
            status = "held"
        if status == "sell_sent":
            # Terminal (cancel then resend): what is left goes again at once, a step wider; nothing left is sold.
            row["status"] = status = "held" if self._owned(row) > STOCK_TOLERANCE else "sold"
        if status == "held":
            if self._reconciled(row, held):
                row["hold_witness"] = True
            elif not row.get("hold_witness"):
                row["why"] = f"the paper account's {STOCK_SYMBOL} disagrees with this attempt's recorded fills"
            if row.get("buy_witness") and row.get("hold_witness"):
                self._pass_buy(row, today)                     # stage BUY: fill, lot row, position, reconciliation
            if window is None or today.isoformat() <= str(row["buy_day"]):
                return row                                   # never sold in the session it was bought
            sold_today = row.get("sell_day") == today.isoformat()
            if now >= float(window.exit_until):
                if sold_today:
                    self._fail_sell(row, today, f"the practice lot was not sold by the open window's end "
                                                f"({self._owned(row)} {STOCK_SYMBOL} left)")
                    row["sell_day"] = None
                return row
            if not opened:
                return row
            owned = self._owned(row)
            if owned <= STOCK_TOLERANCE:
                row["status"] = "sold"
                return row
            bid, _ = self._quote(market)
            sells = sum(1 for w in row["orders"] if w["action"] == "sell")
            collar = min(STOCK_MAX_COLLAR_BP, STOCK_COLLAR_BP + STOCK_COLLAR_STEP_BP * sells)
            limit = (bid * (1 - Decimal(collar) / 10000)).quantize(CENT, rounding=ROUND_DOWN)
            body = {"symbol": STOCK_SYMBOL, "qty": format(owned.normalize(), "f"), "side": "sell", "type": "limit",
                    "time_in_force": "day", "limit_price": format(limit, "f"),
                    "client_order_id": f"{row['attempt']}-s{sells + 1}"}
            row["sell_day"] = today.isoformat()
            return self._dispatch(row, body, action="sell")
        if status == "sold":
            bought, sold = self._filled(row, "buy"), self._filled(row, "sell")
            row["sell_witness"] = bought > 0 and abs(bought - sold) <= STOCK_TOLERANCE and all(
                w.get("avg") not in (None, "") for w in row["orders"] if w["action"] == "sell" and Decimal(w["filled"]) > 0)
            row["recon_witness"] = self._reconciled(row, held) and abs(held - Decimal(row["baseline"])) <= STOCK_TOLERANCE
            row["activity_witness"] = self._activities(row)
            if all(row.get(k) is True for k in STOCK_WITNESSES):
                row.update(status="passed", passed_at=self.clock(),
                           why=(f"a witnessed fractional {STOCK_SYMBOL} buy in an open window and sale in the next "
                                "session's: fills, position, activities and reconciliation agree"))
                self._pass_sell(row, today)
                return row
            missing = [k for k in STOCK_WITNESSES if row.get(k) is not True]
            ended = today.isoformat() > str(row.get("sell_day") or today.isoformat()) or (
                window is not None and now >= float(window.exit_until))
            if ended:
                # The sale's window has ended without every witness: the stage fails and this attempt ends flat; the
                # next session's open window buys again (stage BUY stays passed) and the next one sells.
                self._event("attempt_flat", {"attempt": row.get("attempt"), "missing": missing})
                self._fail_sell(row, today, f"the round trip ended without {', '.join(missing)}")
                row.update(status="waiting", why=f"the last attempt ended flat without {', '.join(missing)}")
            else:
                row["why"] = f"sold; waiting for {', '.join(missing)}"
        return row


__all__ = ["PaperProof", "StockPaperProof", "STOCK_KEY", "STOCK_BUY_KEY", "STOCK_SELL_KEY"]
