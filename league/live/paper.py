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

THE STRUCTURE PROOFS (money rules v3, release V3-A, the owner's D3): once the vertical and the single have passed, the
House proves each remaining real structure type the same way, one at a time and in `KINDS` order, on SPY's nearest
expiry at least a day out, 1 lot at the natural, held two minutes, closed with one multi-leg order at the natural:
`long_butterfly` (calls: short two at the first strike at or above the spot, long one $1 either side),
`credit_vertical` (calls: short the first strike at or above the spot, long $1 above), `iron_condor` (short the put at
or below the spot and the call above it, each with a long wing $1 further out) and `iron_butterfly` (short a call and a
put at the first strike at or above the spot, long wings $1 out). A credit structure opens at a negative limit (a credit,
Alpaca's convention) and closes at a positive one. Every proof's legs are checked to form its type
(`structure_core.classify`) before the open, and its bodies are the real route's own (`real.mleg_body`). A real open of a
type waits for that type's proof (`PROOF_FOR`; `OptionsLive._real_intent`), and `league.ci` refuses a constitution whose
`real_types` names a type with no proof here. Paper has no money behind it: its short legs may sit in the money for the
two minutes held (the iron butterfly's always does), which the real path, the Gym and the shadow book refuse for a
credit structure at entry on an American-style root (`league/gym/legs.py` `assignment_refusal`): the proof is of the
route (the order's shape and the venue's answers), not of an entry.

The session loop runs this proof with real money off and no real-account client. Passing the paper route never
changes real-money configuration, enables a grant, promotes a family, or sends an order to the real venue.

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

from .. import structure_core as core
from .real import RLeg, limit_price, mleg_body, single_body, structure_fill, ROrder
from .state import LiveState
from .venue import TERMINAL, Account

WAIT_MINUTES = 8
HOLD_MINUTES = 2
TRIES = 3
#: No proof opens before this many minutes into the session (`PaperProof.step`).
START_MINUTE = 5
ROOT = "SPY"


#: The single-leg proof's call: out of the money by about this share of the spot (1-2%).
SINGLE_OTM = (0.01, 0.02)
#: Every proof, in the order the House runs them (`OptionsLive._paper_proof`): the vertical first (every real open waits
#: for it), then the single, then the structures. Real types only: a kind runs only while the money table's `real_types`
#: names a type it proves.
KINDS = ("vertical", "single", "long_butterfly", "credit_vertical", "iron_condor", "iron_butterfly")
#: The proof a real open of each order type waits for. `league.ci` (`check_structures`) reads this literal from the tree
#: and refuses a constitution whose `options_money.real_types` names a type missing here.
PROOF_FOR = {"debit_vertical": "vertical", "long_call": "single", "long_put": "single", "long_butterfly": "long_butterfly",
             "credit_vertical": "credit_vertical", "iron_condor": "iron_condor", "iron_butterfly": "iron_butterfly"}
#: The structure type each multi-leg proof opens.
STRUCTURE = {"vertical": "debit_vertical", "long_butterfly": "long_butterfly", "credit_vertical": "credit_vertical",
             "iron_condor": "iron_condor", "iron_butterfly": "iron_butterfly"}
#: Each proof's SPY read window: (dte low, dte high, band as a share of the spot).
WINDOW = {"vertical": (1, 7, 0.01), "single": (1, 7, 0.025), "long_butterfly": (1, 7, 0.01),
          "credit_vertical": (1, 7, 0.01), "iron_condor": (1, 7, 0.01), "iron_butterfly": (1, 7, 0.01)}
#: Each proof's client order id prefix (an attempt's ids are `<prefix>-<day>-<nonce>-<try>-o`, `-c1`, ...).
PREFIX = {"vertical": "lv-pp", "single": "lv-ps", "long_butterfly": "lv-plb", "credit_vertical": "lv-pcv",
          "iron_condor": "lv-pic", "iron_butterfly": "lv-pib"}
#: What each proof looks for, when the chain does not have it.
WANTED = {"vertical": "no SPY vertical one strike wide is quoted a day or more out",
          "single": "no SPY call 1-2% out of the money is quoted a day or more out",
          "long_butterfly": "no SPY call butterfly $1 wide at the money is quoted a day or more out",
          "credit_vertical": "no SPY call credit vertical $1 wide at the money is quoted a day or more out",
          "iron_condor": "no SPY iron condor with $1 wings around the spot is quoted a day or more out",
          "iron_butterfly": "no SPY iron butterfly with $1 wings at the money is quoted a day or more out"}


class PaperProof:
    def __init__(self, state: LiveState, account: Account, *, record: Callable[..., Any] | None = None,
                 clock: Callable[[], float] | None = None, kind: str = "vertical"):
        if kind not in KINDS:
            raise ValueError(kind)
        self.state, self.account = state, account
        self.record = record or (lambda *a, **k: None)
        self.clock = clock or time.time
        self.kind = kind
        self.key = "paper_proof" if kind == "vertical" else f"paper_proof_{kind}"
        self.window = WINDOW[kind]

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
        # Even is the same number of STRUCTURES on every leg: a butterfly's body fills two contracts to a wing's one.
        ratio = {leg["symbol"]: Decimal(str(leg.get("ratio_qty") or "1")) for leg in work["body"].get("legs") or []}
        values = [abs(Decimal(qty)) / ratio.get(symbol, Decimal(1)) for symbol, qty in work["fills"].items()]
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
            sides, ratios = self._shape(row)
            # The close at the natural: each long leg sold at its bid, each short leg bought back at its ask.
            natural = sum(side * ratio * float(snap.bid[i] if side > 0 else snap.ask[i])
                          for side, ratio, i in zip(sides, ratios, idx))
            if not math.isfinite(natural):
                return row
            spec = self._spec(row["legs"], sides, ratios)
            if spec.credit:
                # A buy-back: never a credit, and never at or above the collateral (the gateway's defined-risk line).
                natural = max(min(0.0, round(natural, 2)), -(float(spec.collateral) - 0.01))
            else:
                natural = max(0.0, round(natural, 2))
            body = mleg_body(self._order(symbols, sides, ratios, "close", natural, cid))
        return self._dispatch(row, body, action="cleanup" if cleanup else "close", mi=mi)

    def step(self, *, day: str, mi: int, snap: Any, chain: Any, start_minute: int = START_MINUTE) -> dict:
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
            legs = self._select(snap, chain)
            if legs is None:
                row["why"] = WANTED[self.kind]
                self._put(row)
                return row
            symbols = [leg[0] for leg in legs]
            sides, ratios = [leg[3] for leg in legs], [leg[4] for leg in legs]
            if any(positions.get(symbol, Decimal(0)) for symbol in symbols):
                row["why"] = "the selected proof contracts already belong to another paper position"
                self._put(row)
                return row
            # The open at the natural: each long leg bought at its ask, each short leg sold at its bid (a credit structure's
            # value is negative: it takes in a credit).
            natural = sum(leg[3] * leg[4] * (leg[1] if leg[3] > 0 else leg[2]) for leg in legs)
            if not math.isfinite(natural):
                return row
            if self.kind != "single":
                natural = round(natural, 2)
                why = self._open_refusal(symbols, sides, ratios, natural)
                if why:
                    row["why"] = why
                    self._put(row)
                    return row
            elif not natural > 0:
                return row
            row["tries"] = int(row.get("tries") or 0) + 1
            prefix = PREFIX[self.kind]
            row.update(legs=symbols, sides=sides, ratios=ratios, baseline={s: str(positions.get(s, Decimal(0))) for s in symbols},
                       attempt=f"{prefix}-{day.replace('-', '')}-{self.state.nonce}-{row['tries']}",
                       open_witness=False, close_witness=False)
            if self.kind == "single":
                body = _single(symbols[0], "open", natural, row["attempt"] + "-o")
            else:
                body = mleg_body(self._order(symbols, sides, ratios, "open", natural, row["attempt"] + "-o"))
            return self._dispatch(row, body, action="open", mi=mi)
        if not row.get("orders") or not self._inventory(row, positions):
            return row
        work = row["orders"][-1]
        if not work.get("terminal"):
            return row
        owned = self._owned(row)
        sides, ratios = self._shape(row)
        held = [Decimal(side * ratio) for side, ratio in zip(sides, ratios)]
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
                       why=(f"a witnessed {'single-leg' if self.kind == 'single' else 'multi-leg'} open and close"
                            f"{'' if self.kind in ('vertical', 'single') else ' of a ' + STRUCTURE[self.kind]} returned "
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
        sides, ratios = self._shape(row)
        legs = [RLeg(s, side, ratio, True, 0.0, "", 0) for s, side, ratio in zip(row.get("legs") or [], sides, ratios)]
        fake = ROrder(0, "", "", "", "close" if closing else "open", STRUCTURE[self.kind], ROOT, legs, 1, 0.0, "0", None, 0.0,
                      "", 0)
        fill = structure_fill(fake, order)
        return fill is not None and fill[0] >= 1 and not fill[3]

    def _shape(self, row: Mapping[str, Any]) -> tuple[list[int], list[int]]:
        """The attempt's legs' sides (+1 long, -1 short) and ratios, in `legs` order. A vertical attempt recorded before
        the shapes were (Sept 28, 2026) is long then short, 1:1; any other attempt without them is unreadable."""
        legs = list(row.get("legs") or [])
        if self.kind == "single":
            return [1] * len(legs), [1] * len(legs)
        sides = row.get("sides") if row.get("sides") is not None else ([1, -1] if self.kind == "vertical" else None)
        ratios = row.get("ratios") if row.get("ratios") is not None else [1] * len(legs)
        if (sides is None or len(sides) != len(legs) or len(ratios) != len(legs)
                or any(int(x) not in (1, -1) for x in sides) or any(int(x) not in (1, 2) for x in ratios)):
            raise ValueError("the attempt's legs have no recorded shape")
        return [int(x) for x in sides], [int(x) for x in ratios]

    def _spec(self, symbols: list[str], sides: list[int], ratios: list[int]) -> Any:
        """The legs as this proof's structure type (`structure_core.classify`; ValueError when they are not one)."""
        return core.classify(STRUCTURE[self.kind], [core.leg(s, side, ratio) for s, side, ratio in zip(symbols, sides, ratios)])

    def _open_refusal(self, symbols: list[str], sides: list[int], ratios: list[int], natural: float) -> str | None:
        """Why a multi-leg proof may not open these legs at this natural value a share, or None: the legs must form the
        proof's type, and the price must be a defined-risk one (the gateway's own lines): a debit above zero and below the
        structure's most value, a credit above zero and below its collateral."""
        try:
            spec = self._spec(symbols, sides, ratios)
        except ValueError as exc:
            return f"the proof's legs are not a {STRUCTURE[self.kind]}: {exc}"
        if spec.credit:
            if not (natural < 0 and -natural < float(spec.collateral)):
                return f"the natural {natural:+.2f} is not a credit under the {spec.collateral} collateral"
        elif not (natural > 0 and (spec.max_value is None or natural < float(spec.max_value))):
            return f"the natural {natural:+.2f} is not a debit under the structure's most value"
        return None

    @staticmethod
    def _order(symbols: list[str], sides: list[int], ratios: list[int], action: str, value: float, cid: str) -> ROrder:
        """The proof's order as the real route's own `ROrder`, so `mleg_body` writes it exactly as a real one."""
        legs = [RLeg(s, side, ratio, s[-9] == "C", 0.0, "", 0) for s, side, ratio in zip(symbols, sides, ratios)]
        return ROrder(0, cid, "paper-proof", "paper-proof", action, "paper-proof", ROOT, legs, 1, float(value),
                      limit_price(value, action), None, 0.0, "", 0)

    def _select(self, snap: Any, chain: Any) -> list[tuple[str, float, float, int, int]] | None:
        """This proof's legs, each (symbol, ask, bid, side, ratio), or None when the chain has no such structure now."""
        if self.kind == "single":
            legs = self._single(snap, chain)
            return None if legs is None else [(*legs[0], 1, 1)]
        if self.kind == "vertical":
            legs = self._legs(snap, chain)
            return None if legs is None else [(*legs[0], 1, 1), (*legs[1], -1, 1)]
        return self._structure(self.kind, snap, chain)

    @staticmethod
    def _structure(kind: str, snap: Any, chain: Any) -> list[tuple[str, float, float, int, int]] | None:
        """A structure proof's legs on the nearest expiry a day or more out, around A, the first strike at or above the
        spot (the module docstring): every leg listed, a long leg with an ask and a short leg with a bid."""
        spot = float(snap.spot)
        if not math.isfinite(spot):
            return None
        ok = snap.valid & (snap.dte >= 1)
        if not ok.any():
            return None
        first = int(snap.dte[ok].min())
        at = {(bool(snap.is_call[i]), round(float(snap.strike[i]), 3)): int(i)
              for i in np.flatnonzero(ok & (snap.dte == first))}
        above = sorted(k for c, k in at if c and k >= spot)
        if not above:
            return None
        a = above[0]
        if kind == "long_butterfly":
            plan = [(True, a - 1, 1, 1), (True, a, -1, 2), (True, a + 1, 1, 1)]
        elif kind == "credit_vertical":
            plan = [(True, a, -1, 1), (True, a + 1, 1, 1)]
        elif kind == "iron_butterfly":
            plan = [(False, a - 1, 1, 1), (False, a, -1, 1), (True, a, -1, 1), (True, a + 1, 1, 1)]
        else:  # the iron condor: the short put at or below the spot, the short call the first strike above it
            below = sorted(k for c, k in at if not c and k <= spot)
            if not below:
                return None
            b = below[-1]
            c = a if a > b else a + 1
            plan = [(False, b - 1, 1, 1), (False, b, -1, 1), (True, c, -1, 1), (True, c + 1, 1, 1)]
        out = []
        for is_call, strike, side, ratio in plan:
            i = at.get((is_call, round(strike, 3)))
            if i is None:
                return None
            ask, bid = float(snap.ask[i]), float(snap.bid[i])
            price = ask if side > 0 else bid
            if not (math.isfinite(price) and price > 0):
                return None
            out.append((str(chain.symbol[i]), ask, bid, side, ratio))
        return out

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


__all__ = ["PaperProof", "KINDS", "PROOF_FOR", "STRUCTURE", "WINDOW"]
