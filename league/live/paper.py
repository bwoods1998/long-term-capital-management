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

A timed-out or uneven order is cancelled, then read until the venue confirms it is terminal. Each owned leg is
reconciled and closed before another attempt, at most `TRIES` opens per session. Client ids, order bodies and the
initial inventory are committed before dispatch; ambiguous answers and session changes never discard ownership.
An unreadable order or position snapshot cannot pass the proof. Unrelated paper positions are left alone.
"""

from __future__ import annotations

import math
import time
from decimal import Decimal
from typing import Any, Callable, Mapping

import numpy as np

from .real import RLeg, limit_price, structure_fill, ROrder
from .state import LiveState
from .venue import TERMINAL, Account

WAIT_MINUTES = 8
HOLD_MINUTES = 2
TRIES = 3
ROOT = "SPY"


class PaperProof:
    def __init__(self, state: LiveState, account: Account, *, record: Callable[..., Any] | None = None,
                 clock: Callable[[], float] | None = None):
        self.state, self.account = state, account
        self.record = record or (lambda *a, **k: None)
        self.clock = clock or time.time

    def status(self) -> dict:
        return dict(self.state.get("paper_proof", {}) or {})

    def passed(self) -> bool:
        row = self.status()
        return (row.get("schema") == 2 and row.get("status") == "passed"
                and row.get("open_witness") is True and row.get("close_witness") is True)

    def held_symbols(self) -> list[str]:
        """Keep an unfinished attempt's contracts in the read window across session changes."""
        row = self.status()
        return list(row.get("legs") or []) if not self.passed() else []

    def _put(self, row: Mapping[str, Any]) -> None:
        self.state.put("paper_proof", dict(row))

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
        self._put(row)
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
            self.record("live.paper_proof", {"status": "failed", "day": day, "why": fresh["why"]})
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
        if cleanup:
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
            legs = self._legs(snap, chain)
            if legs is None:
                row["why"] = "no SPY vertical one strike wide is quoted a day or more out"
                self._put(row)
                return row
            symbols = [leg[0] for leg in legs]
            if any(positions.get(symbol, Decimal(0)) for symbol in symbols):
                row["why"] = "the selected proof contracts already belong to another paper position"
                self._put(row)
                return row
            natural = legs[0][1] - legs[1][2]
            if not (math.isfinite(natural) and natural > 0):
                return row
            row["tries"] = int(row.get("tries") or 0) + 1
            row.update(legs=symbols, baseline={s: str(positions.get(s, Decimal(0))) for s in symbols},
                       attempt=f"lv-pp-{day.replace('-', '')}-{self.state.nonce}-{row['tries']}",
                       open_witness=False, close_witness=False)
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
        if work["action"] == "open" and work.get("route_full") and list(owned.values()) == [Decimal(1), Decimal(-1)]:
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
                       why="a witnessed multi-leg open and close returned the owned contracts to their baseline")
            self._put(row)
            self._event("close_witness", {"cid": work["cid"], "owned": owned})
            self.record("live.paper_proof", {"status": "passed", "day": day})
            return row
        if flat:
            return self._finish_failed_attempt(row, day)
        row["status"] = "recovering"
        self._put(row)
        return self._close(row, snap=snap, chain=chain, mi=mi, cleanup=True)

    @staticmethod
    def _filled(order: Any, row: Mapping[str, Any], closing: bool) -> bool:
        if not isinstance(order, Mapping):
            return False
        legs = [RLeg(s, 1 if i == 0 else -1, 1, True, 0.0, "", 0) for i, s in enumerate(row.get("legs") or [])]
        fake = ROrder(0, "", "", "", "close" if closing else "open", "debit_vertical", ROOT, legs, 1, 0.0, "0", None, 0.0, "", 0)
        fill = structure_fill(fake, order)
        return fill is not None and fill[0] >= 1 and not fill[3]

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
        self.state.event("paper_proof." + what, dict(detail))


__all__ = ["PaperProof"]
