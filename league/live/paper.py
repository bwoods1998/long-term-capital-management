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

An open not filled in `WAIT_MINUTES` is cancelled and sent again at a fresh natural, `TRIES` times in all; after that the
proof has failed for the day, the owner is told, and real opens stay shut until the next session (or until the owner
sets `live.require_paper_proof` false).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping

import numpy as np

from .real import RLeg, limit_price, structure_fill, ROrder
from .state import LiveState
from .venue import TERMINAL, Account, occ_parts

WAIT_MINUTES = 8
HOLD_MINUTES = 2
TRIES = 3
ROOT = "SPY"


class PaperProof:
    def __init__(self, state: LiveState, account: Account, *, record: Callable[..., Any] | None = None,
                 clock: Callable[[], float] | None = None):
        self.state, self.account = state, account
        self.record = record or (lambda *a, **k: None)
        self.clock = clock or (lambda: 0.0)

    def status(self) -> dict:
        return dict(self.state.get("paper_proof", {}) or {})

    def passed(self) -> bool:
        return self.status().get("status") == "passed"

    def _put(self, row: Mapping[str, Any]) -> None:
        self.state.put("paper_proof", dict(row))

    def step(self, *, day: str, mi: int, snap: Any, chain: Any, start_minute: int = 5) -> dict:
        """One minute of the proof (`snap`, `chain`: SPY's snapshot and chain now)."""
        row = self.status()
        if row.get("status") == "passed":
            return row
        if row.get("day") != day:
            row = {"day": day, "status": "waiting", "tries": 0}
        if row.get("status") == "failed" or mi < start_minute:
            self._put(row)
            return row
        if row["status"] == "waiting":
            if snap is None:
                return row
            legs = self._legs(snap, chain)
            if legs is None:
                row["why"] = "no SPY vertical one strike wide is quoted a day or more out"
                self._put(row)
                return row
            natural = legs[0][1] - legs[1][2]  # long leg's ask less the short leg's bid
            if not (math.isfinite(natural) and natural > 0):
                return row
            row["tries"] = int(row.get("tries") or 0) + 1
            cid = f"lv-paper-proof-{day.replace('-', '')}-{row['tries']}"
            body = {"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": limit_price(round(natural, 2), "open"),
                    "time_in_force": "day", "client_order_id": cid,
                    "legs": [{"symbol": legs[0][0], "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
                             {"symbol": legs[1][0], "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"}]}
            answer = self.account.submit(body, exit=False)
            self._event("open_sent", {"body": body, "ok": answer.ok, "error": answer.error, "answer": answer.order})
            if not answer.ok:
                row.update(status="failed" if row["tries"] >= TRIES else "waiting", why=f"the open was refused: {answer.error}")
            else:
                row.update(status="open_sent", open_id=answer.order.get("id"), open_cid=cid, sent_minute=mi,
                           legs=[legs[0][0], legs[1][0]], limit=body["limit_price"])
            self._put(row)
            return row
        if row["status"] in ("open_sent", "close_sent"):
            closing = row["status"] == "close_sent"
            venue_id = row.get("close_id" if closing else "open_id")
            try:
                order = self.account.order_by_client_id(row.get("close_cid" if closing else "open_cid"))
            except Exception as exc:  # noqa: BLE001 - asked again next minute
                row["why"] = f"could not read the order: {str(exc)[:160]}"
                self._put(row)
                return row
            status = str((order or {}).get("status") or "")
            filled = self._filled(order, row, closing)
            if filled:
                self._event("close_filled" if closing else "open_filled", {"order": order})
                if closing:
                    row.update(status="passed", passed_minute=mi, why="the multi-leg route opened and closed a structure")
                    self.record("live.paper_proof", {"status": "passed", "day": day})
                else:
                    row.update(status="open_filled", filled_minute=mi)
            elif status in TERMINAL or mi - int(row.get("sent_minute") or mi) >= WAIT_MINUTES:
                if status not in TERMINAL and venue_id:
                    self.account.cancel(venue_id)
                self._event("unfilled", {"order": order, "closing": closing})
                if closing:
                    row.update(status="open_filled", why="the close did not fill; sent again")
                else:
                    row.update(status="failed" if int(row.get("tries") or 0) >= TRIES else "waiting",
                               why=f"the open did not fill ({status or 'working'})")
            self._put(row)
            if row["status"] == "failed":
                self.record("live.paper_proof", {"status": "failed", "day": day, "why": row.get("why")})
            return row
        if row["status"] == "open_filled" and mi - int(row.get("filled_minute") or mi) >= HOLD_MINUTES:
            if snap is None:
                return row
            symbols = row.get("legs") or []
            idx = [chain.column(s) for s in symbols]
            if len(idx) != 2 or min(idx) < 0:
                return row
            natural = float(snap.bid[idx[0]]) - float(snap.ask[idx[1]])  # sell the long at its bid, buy the short at its ask
            if not math.isfinite(natural):
                return row
            natural = max(0.0, round(natural, 2))
            cid = f"lv-paper-proof-{day.replace('-', '')}-close-{int(row.get('close_tries') or 0) + 1}"
            body = {"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": limit_price(natural, "close"),
                    "time_in_force": "day", "client_order_id": cid,
                    "legs": [{"symbol": symbols[0], "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_close"},
                             {"symbol": symbols[1], "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_close"}]}
            answer = self.account.submit(body, exit=True)
            self._event("close_sent", {"body": body, "ok": answer.ok, "error": answer.error, "answer": answer.order})
            row["close_tries"] = int(row.get("close_tries") or 0) + 1
            if answer.ok:
                row.update(status="close_sent", close_id=answer.order.get("id"), close_cid=cid, sent_minute=mi)
            elif row["close_tries"] >= TRIES:
                row.update(status="failed", why=f"the close was refused: {answer.error}")
            self._put(row)
        return row

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
