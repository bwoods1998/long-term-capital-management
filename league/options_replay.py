"""Rung 0 for the options desk: walk an options tape (`league/options_history.py`) with a
long-calls-and-puts strategy, under the House's own option rules.

Self-contained beside `replay.py` in the agent's box (standard library plus `replay.py`'s helpers).
`replay.run_replay` hands a tape with `"asset_class": "option"` here, and the result has the same
shape as every other replay, so the evaluator's gates judge it unchanged.

EXECUTION IS ESTIMATED, AND CONSERVATIVE, BECAUSE NO HISTORICAL OPTION QUOTES EXIST.

- A contract is tradable at a step only if it has printed at or before it (point-in-time
  listing), expires AFTER today (New York), and its last qualifying print is at most
  `quote_age_seconds` old (the book's own option quote-age rule). Otherwise: refused.
- Its bid and ask are ESTIMATED around the last print, twice. What the strategy is SHOWN and
  marked at (`display_quote`) is a central estimate fitted to the median live OPRA spread; what
  a fill at the touch PAYS (`estimate_quote`) is wider: at least a tick, 4% of the premium or
  half the median recent bar range either side. The tape's `spread_model.stress` widens only
  what fills pay, so a stressed run changes costs, not decisions.
- Limit orders only (the House refuses option market orders). Nothing fills in the bar the
  decision saw: an order is worked against LATER bars of its contract that printed at least
  `min_volume` contracts in `min_trades` trades, and at most `max_participation` of the bar's
  volume (all or nothing). A buy at or over the SHOWN ask at the bar's open is marketable and
  fills at the worse of the shown and the conservative ask, never above its limit; any other buy
  fills at its own limit only when the bar traded at least one tick THROUGH it (`low <= limit -
  tick`): a touched limit is not a fill. Sells mirror this.
- Orders are day orders: an unfilled one expires at 16:00 New York.
- One contract is 100 shares: every premium is paid and received times 100. Fees are
  `fee_per_contract_usd` a contract a fill (an assumed regulatory pass-through; Alpaca charges no
  commission, `league/fees.py`).
- The expiry rule: from 14:30 New York on its last day the House cancels the agent's orders in a
  held contract and offers it at the estimated bid, re-priced each step. Whatever is still held
  when that session ends is written off at ZERO (the book's `expire_options`), never exercised.
- Holdings are marked at the estimated bid of their last print.

STRUCTURES (Sept 25, 2026, the options-desk run: `league/structures.py`, the rules in
`league/structure_core.py`, uploaded beside this file). A strategy whose NEEDS carry
`"structures": true` trades level-3 structures with defined risk under the live options book's
rules (`league/options_shadow.py`), each HELD AS ONE POSITION at S = net value + collateral:

- It is shown what the House shows it live (`House._structure_context`): the chain NOT filtered by
  a single contract's affordability, expiries from today (until 14:30 New York) to
  `max_days_to_expiry` (7 when unstated), within 20% of spot, at most 80 an underlying nearest the
  money; `ctx["structures"]` (`structure_core.candidates` at the smaller of its order and position
  caps); and each held structure's type, legs, held prices, natural open and P&L at the mark.
- An open fills only on a LATER bar than the decision's, when EVERY leg printed in that bar (or has
  a recorded OPRA quote after the decision: then its quote is used) and the structure's CONSERVATIVE
  ask -- long legs at the wider estimated ask, short legs at the wider estimated bid
  (`estimate_quote`, times the stress) -- is within the limit, at that ask; a close mirrors it at the
  conservative bid. At most `max_participation` of each leg's bar volume for the leg's contracts
  (quantity x ratio), one contract on a quote alone (its size was not recorded); all or nothing;
  `fee_per_contract_usd` a contract a leg a fill; day orders. Marks at the structure's SHOWN bid.
- Opens are refused from 14:30 New York on the earliest expiry day, and a RESTING open of a structure
  expiring today is cancelled at that cut (after the bar closing at it is worked), as the House cancels
  it live; closes stay. From 15:30 the House offers the
  structure at its conservative bid (at least a cent), re-priced each step; what is still held at that
  session's end is SETTLED -- at `intrinsic` on the underlying's close (one expiry), or at the far
  legs' bid less the near legs' intrinsic (a calendar or diagonal) -- never written off at zero. A
  structure whose far leg the history never priced is "not evaluated": refunded at its cost (fees
  stay paid) and not counted as a trade.
- An open is refused unless EVERY leg is among the `chain_rules.reach` (160) contracts of its
  underlying nearest the money that the chain could show at that step (the House's rule live,
  `House._structure_reach_refusal`; G-LOOP's review, Sept 25, 2026). On a tape that keeps only what
  the chain could reach (`OptionsHistory._structure_reach`), a contract is listed and may be a leg
  only from the step it was first among them (`contracts[occ]["reached"]`): its earlier bars are
  kept for its spread estimate alone. So what a strategy is shown, and may open, at a step never
  depends on where the underlying went after it.
- A structure is ONE trade when it is flat (`trade_log` has one row a structure), so the replay's
  trade count is a count of structures.
"""

from __future__ import annotations

import bisect
import copy
import math
import random
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

try:
    from league.replay import (MAX_BARS, MAX_CANCELS, MAX_ERRORS, MAX_INTENTS, RUIN_EQUITY, RUIN_LOG_GROWTH, _block_key,
                               _clean_memory, _feed_index, _feeds_until, _mean, _num, _parse_ts, digest)
    from league.options_history import display_quote, estimate_quote, parse_occ, structure_days, tick, implied_vol, bs_delta, years_to
    from league import structure_core as core
except ImportError:  # in the agent's box the files sit side by side
    from replay import (MAX_BARS, MAX_CANCELS, MAX_ERRORS, MAX_INTENTS, RUIN_EQUITY, RUIN_LOG_GROWTH, _block_key,  # type: ignore
                        _clean_memory, _feed_index, _feeds_until, _mean, _num, _parse_ts, digest)
    from options_history import display_quote, estimate_quote, parse_occ, structure_days, tick, implied_vol, bs_delta, years_to  # type: ignore
    import structure_core as core  # type: ignore

NY = ZoneInfo("America/New_York")
EPS = 1e-9
#: The House's structure clock (`league/house.py` STRUCTURE_ENTRY_CUT_HOUR / STRUCTURE_CLOSE_HOUR,
#: Sept 25, 2026), in New York minutes: no structure is opened on its earliest expiry day from 14:30,
#: and the House sells what is still held from 15:30.
STRUCTURE_ENTRY_CUT = 14 * 60 + 30
STRUCTURE_CLOSE = 15 * 60 + 30
#: A structure agent is shown at most this many contracts an underlying (`STRUCTURE_CHAIN_PER_UNDERLYING`).
STRUCTURE_CHAIN_PER_UNDERLYING = 80
#: ...and may open a structure only on legs among this many nearest the money at that step (`options_history.STRUCTURE_REACH`,
#: the House's rule live): a tape says which under `chain_rules.reach`; this is the number when it does not.
STRUCTURE_REACH = 160


def _ny(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, NY)


def _session_end(ts: float) -> float:
    return _ny(ts).replace(hour=16, minute=0, second=0, microsecond=0).timestamp()


class _Book:
    """The simulated options account: cash, contracts held, working orders, and the tally."""

    def __init__(self, stake: float, limits: dict[str, float], fee: float, multiplier: int, liquidity: dict[str, Any], record: bool):
        self.stake, self.cash, self.limits, self.fee_rate, self.mult, self.liq = stake, stake, limits, fee, multiplier, liquidity
        self.positions: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.held: dict[str, dict[str, Any]] = {}     # structures held, by code (the held instrument's market_id)
        self.sorders: dict[str, dict[str, Any]] = {}  # structure orders, by order id
        self.seq = self.fills = self.refused = self.expired_orders = self.written_off = self.forced = 0
        self.settled = self.not_evaluated = self.structures_opened = self.structures_closed = self.unseen = self.cut_opens = 0
        self.unreached = 0  # structure opens refused for a leg outside the chain's reach (G-LOOP's review, Sept 25, 2026)
        self.fees_usd = 0.0
        self.reasons: dict[str, int] = {}
        self.trade_returns: list[float] = []
        self.trade_log: list[dict[str, Any]] = []
        self.fill_log: list[dict[str, Any]] | None = [] if record else None

    def refuse(self, why: str) -> None:
        self.refused += 1
        self.reasons[why] = self.reasons.get(why, 0) + 1

    def equity(self) -> float:
        return (self.cash + sum(p["quantity"] * p["mark"] * self.mult for p in self.positions.values())
                + sum(p["quantity"] * p["mark"] * self.mult for p in self.held.values()))

    def reserved(self) -> float:
        return (sum(o["quantity"] * (o["limit_price"] * self.mult + self.fee_rate) for o in self.orders.values() if o["side"] == "buy")
                + sum(o["quantity"] * (o["limit_price"] * self.mult + self.fee_rate * o["contracts"]) for o in self.sorders.values() if o["side"] == "buy"))

    # -- structures: one held position each, at the held price S a share ----------------------
    def _sclose(self, position: dict[str, Any], how: str, now: str) -> None:
        """A structure gone flat: ONE closed trade, whatever its legs."""
        self.trade_returns.append(position["pnl"] / self.stake)
        self.structures_closed += 1
        if len(self.trade_log) < 2000:
            self.trade_log.append({"name": position["code"], "group": position["symbol"], "leg": position["structure"], "pnl": position["pnl"],
                                   "entry": position["entry"], "opened_at": position["opened_at"], "closed_at": now,
                                   "close_time": position["expiry"] + "T20:00:00Z", "how": how})
        del self.held[position["code"]]

    def sfill(self, order: dict[str, Any], price: float, now: str, how: str) -> None:
        """A structure order filled whole at the held price `price` a share (an open buys it, a close sells it)."""
        qty, code = order["quantity"], order["code"]
        fee = qty * self.fee_rate * order["contracts"]
        gross = qty * price * self.mult
        self.fills += 1
        self.fees_usd += fee
        if order["side"] == "buy":
            self.cash -= gross + fee
            spec = order["spec"]
            p = self.held.get(code)
            if p is None:
                self.structures_opened += 1
                p = self.held[code] = {"code": code, "spec": spec, "structure": spec.type, "symbol": spec.underlying, "expiry": spec.expiry,
                                       "quantity": 0.0, "cost": 0.0, "pnl": 0.0, "mark": price, "opened_at": now, "reason": order["reason"],
                                       "entry": price, "fees": 0.0, "contracts": order["contracts"]}
            p["quantity"] += qty
            p["cost"] += gross
            p["fees"] += fee
            p["pnl"] -= fee
        else:
            p = self.held[code]
            average = p["cost"] / p["quantity"]
            self.cash += gross - fee
            p["pnl"] += gross - average * qty - fee
            p["fees"] *= max(0.0, p["quantity"] - qty) / p["quantity"]
            p["quantity"] -= qty
            p["cost"] = average * p["quantity"]
            if p["quantity"] <= EPS:
                self._sclose(p, how, now)
        if self.fill_log is not None:
            self.fill_log.append({"t": now, "code": code, "side": order["side"], "quantity": qty, "price": price, "fee": fee, "how": how})

    def settle(self, position: dict[str, Any], price: float | None, now: str, how: str) -> None:
        """What is still held at its expiry's close: paid out at `price` a share (no fee: nothing
        traded), or, when the history cannot value it (`price` None), refunded at cost and not
        counted as a trade -- not evaluated, never a loss made up."""
        qty = position["quantity"]
        if price is None:
            self.cash += position["cost"]
            self.not_evaluated += 1
            del self.held[position["code"]]
            if self.fill_log is not None:
                self.fill_log.append({"t": now, "code": position["code"], "side": "settle", "quantity": qty, "price": None, "fee": 0.0, "how": how})
            return
        proceeds = qty * price * self.mult
        self.cash += proceeds
        position["pnl"] += proceeds - position["cost"]
        position["quantity"] = 0.0
        position["cost"] = 0.0
        self.settled += 1
        if self.fill_log is not None:
            self.fill_log.append({"t": now, "code": position["code"], "side": "settle", "quantity": qty, "price": price, "fee": 0.0, "how": how})
        self._sclose(position, how, now)

    def _close(self, position: dict[str, Any], how: str, now: str) -> None:
        self.trade_returns.append(position["pnl"] / self.stake)
        if len(self.trade_log) < 2000:
            self.trade_log.append({"name": position["occ"], "group": position["symbol"], "leg": position["right"], "pnl": position["pnl"],
                                   "entry": position["entry"], "opened_at": position["opened_at"], "closed_at": now,
                                   "close_time": position["expiry"] + "T20:00:00Z", "how": how})
        del self.positions[position["occ"]]

    def fill(self, order: dict[str, Any], price: float, now: str, how: str) -> None:
        qty, occ = order["quantity"], order["occ"]
        fee = qty * self.fee_rate
        gross = qty * price * self.mult
        self.fills += 1
        self.fees_usd += fee
        if order["side"] == "buy":
            self.cash -= gross + fee
            p = self.positions.setdefault(occ, {**order["ident"], "occ": occ, "quantity": 0.0, "cost": 0.0, "pnl": 0.0, "mark": price,
                                                "opened_at": now, "reason": order["reason"], "entry": price, "fees": 0.0})
            p["quantity"] += qty
            p["cost"] += gross
            p["fees"] += fee
            p["pnl"] -= fee
        else:
            p = self.positions[occ]
            average = p["cost"] / p["quantity"]
            self.cash += gross - fee
            p["pnl"] += gross - average * qty - fee
            p["fees"] *= max(0.0, p["quantity"] - qty) / p["quantity"]
            p["quantity"] -= qty
            p["cost"] = average * p["quantity"]
            if p["quantity"] <= EPS:
                self._close(p, how, now)
        if self.fill_log is not None:
            self.fill_log.append({"t": now, "occ": occ, "side": order["side"], "quantity": qty, "price": price, "fee": fee, "how": how})


def replay_options(decide: Any, needs: dict, effective: dict, tape: dict, stake: float, limits: dict[str, float],
                   oos_fraction: float, deadline: Any, audit: bool, failed: Any, seed: int, sha: str, horizon: str) -> dict:
    contracts = {k: v for k, v in (tape.get("contracts") or {}).items() if isinstance(v, dict) and parse_occ(k)}
    rules = tape.get("chain_rules") or {}
    model = tape.get("spread_model") or {}
    stress = max(1.0, float(model.get("stress") or 1.0))  # the execution stress: what fills pay, not what is shown
    liq = {"min_volume": 5.0, "min_trades": 2, "max_participation": 0.10, "quote_age_seconds": 1500, **(tape.get("liquidity") or {})}
    mult = int(tape.get("multiplier") or 100)
    fee = float(tape.get("fee_per_contract_usd") if tape.get("fee_per_contract_usd") is not None else 0.05)
    symbols = [s for s in (needs.get("symbols") or tape.get("symbols") or []) if isinstance(s, str)]
    chain_symbols = symbols[:8]
    max_days = int(needs.get("max_days_to_expiry") or rules.get("max_days_to_expiry") or 21)
    max_days = max(2, min(max_days, 45))
    # A structure agent (NEEDS `"structures": true`, read as the House reads it: `True` alone): its structure context and
    # book rules.
    structural = needs.get("structures") is True
    if structural:
        # As `House._structure_context` (`structure_days`): 0 is 0-DTE; 10 at most for SPY, QQQ or IWM.
        max_days = structure_days(needs.get("max_days_to_expiry"), symbols)
    # The reach (G-LOOP's review, Sept 25, 2026): an open's legs must be among the `reach` nearest at its step; on a tape
    # that keeps only what the chain could reach, a contract is listed only from the step it first could.
    reach_rule = max(1, int(rules.get("reach") or STRUCTURE_REACH)) if structural else 0
    gated = structural and isinstance(tape.get("reached"), dict)
    reached_at = {occ: (_parse_ts(info.get("reached")) if info.get("reached") else None) for occ, info in contracts.items()} if gated else {}
    reachable: dict[str, Any] = {"ts": None, "occs": frozenset()}
    # The entry cut and the House's close by New York day (`House._structure_hours`): the regular
    # 14:30 and 15:30, earlier on an early close (the tape carries those days, from the House's calendar).
    early = {str(day): (int(pair[0]), int(pair[1])) for day, pair in (tape.get("structure_hours") or {}).items()
             if isinstance(pair, (list, tuple)) and len(pair) == 2}

    def structure_hours(day: str) -> tuple[int, int]:
        return early.get(day, (STRUCTURE_ENTRY_CUT, STRUCTURE_CLOSE))
    bar_limit = int(_num((needs.get("bars") or {}).get("limit")) or 120)
    bar_limit = max(1, min(MAX_BARS, bar_limit))
    half_bps = float(_num(tape.get("half_spread_bps")) or 1.0) / 10000.0
    step_seconds = float(_num(tape.get("step_seconds")) or 900.0)
    declared = (needs.get("bars") or {}).get("timeframe") if isinstance(needs.get("bars"), dict) else None
    if tape.get("timeframe") and declared and tape["timeframe"] != declared:
        return failed("unsupported input: tape timeframe does not match declared bars")
    book = _Book(stake, limits, fee, mult, liq, audit)
    history = {s: [dict(b) for b in rows[-MAX_BARS:]] for s, rows in (tape.get("warmup_bars") or {}).items()}
    last_print: dict[str, dict[str, Any]] = {}   # occ -> {"bar", "ts", "half", "bid", "ask"}
    ranges: dict[str, list[float]] = {}
    spot: dict[str, tuple[float, str]] = {}
    by_under: dict[str, set[str]] = {}  # underlying -> contracts that have printed
    recorded: dict[str, dict[str, Any]] = {}  # occ -> the last recorded OPRA quote {"bid", "ask", "ts", "source"}
    # Structures: each leg's CONSERVATIVE touch (what a fill pays) from this step's bar or recorded
    # quote, the latest one seen (the House's offer and a two-expiry settlement read it), and each
    # underlying's last close of each New York day (a single-expiry settlement reads it).
    exec_touch: dict[str, dict[str, Any]] = {}
    step_quotes: dict[str, dict[str, Any]] = {}
    last_exec: dict[str, dict[str, Any]] = {}
    day_close: dict[tuple[str, str], float] = {}
    house_offers = 0
    # A structure agent's wake also carries the options-derived features and the recorded feeds it
    # declares (`House.snapshot`): each row stamped with when it became available, the latest at or
    # before the step, as `replay.py` shows them to every other desk.
    features = feeds = None
    if structural and needs.get("options_features") and isinstance(tape.get("options_features"), dict):
        features = _feed_index({"options_features": tape["options_features"]}).get("options_features") or {}
    if structural and needs.get("feeds") and isinstance(tape.get("feeds"), dict):
        feeds = _feed_index(tape["feeds"])
    quote_fills = 0
    memory: dict[str, Any] = {}
    errors, last_error = 0, ""
    blocks: list[dict[str, Any]] = []
    block_key, block_active, block_equity, previous_equity = None, False, stake, stake
    peak, max_drawdown, equity, ruined, steps_walked, decisions = stake, 0.0, stake, False, 0, 0
    shown_rows = liquidity_misses = structures_shown = 0
    now_ts = 0.0

    def close_block(growth: float | None = None) -> None:
        nonlocal previous_equity
        if growth is None:
            growth = max(RUIN_LOG_GROWTH, math.log(max(block_equity, 1e-300) / previous_equity))
        blocks.append({"key": block_key, "log_growth": round(growth, 12), "active": block_active})
        previous_equity = block_equity

    def quote(occ: str, at: float) -> dict[str, Any] | None:
        """The freshest quote within the age limit: a recorded OPRA quote where one exists, else
        the estimate around the last qualifying print."""
        age = float(liq["quote_age_seconds"]) + EPS
        seen, real = last_print.get(occ), recorded.get(occ)
        if real is not None and at - real["ts"] <= age and (seen is None or real["ts"] >= seen["ts"]):
            return {**(seen or {}), **real}
        if seen is None or at - seen["ts"] > age:
            return None
        return seen

    def work(occ: str, bar: dict[str, Any], now: str) -> None:
        """Later bars meet working orders. An order at or through the quote a strategy is SHOWN
        (the bar's open +- the displayed half-spread) is marketable, as an order at the touch
        is live: it fills at the worse of the shown and the conservative touch, never past its
        limit. Any other order rests and fills at its limit only on a print a tick through it."""
        nonlocal liquidity_misses
        if not any(o["occ"] == occ for o in book.orders.values()):
            return  # nothing works against this bar (the estimates below are the replay's costliest arithmetic)
        volume, trades = float(bar.get("v") or 0), int(bar.get("n") or 0)
        stress = max(1.0, float(model.get("stress") or 1.0))  # the execution stress: costs, not the quote shown
        half = estimate_quote(bar, ranges.get(occ, []), model)[2] * stress
        shown = (display_quote(float(bar["o"]), model)[1] - float(bar["o"])) * stress  # the shown half-spread at the open
        bar_start = now_ts - step_seconds
        for order_id in [k for k, o in book.orders.items() if o["occ"] == occ]:
            order = book.orders[order_id]
            if order["placed_ts"] >= now_ts or bar_start >= order["expires_ts"]:
                continue  # placed at this step, or a day order that had expired before this bar began
            if volume < liq["min_volume"] or trades < liq["min_trades"] or order["quantity"] > liq["max_participation"] * volume + EPS:
                liquidity_misses += 1
                continue
            limit, step = order["limit_price"], tick(order["limit_price"])
            opening = float(bar["o"])
            if order["side"] == "buy":
                price = (min(limit, opening + max(shown, half)) if limit >= opening + shown - EPS
                         else (limit if float(bar["l"]) <= limit - step + EPS else None))
            else:
                worst = max(opening - max(shown, half), 0.0)
                price = (max(limit, worst) if opening - shown > 0 and limit <= opening - shown + EPS
                         else (limit if float(bar["h"]) >= limit + step - EPS else None))
            if price is None:
                continue
            if order["side"] == "sell" and occ not in book.positions:
                del book.orders[order_id]
                continue
            del book.orders[order_id]
            book.fill(order, round(price, 4), now, "expiry rule" if order.get("house") else "sold")

    def submit(intent: Any, now: str) -> None:
        if not isinstance(intent, dict):
            return book.refuse("malformed: an intent is a dict")
        side = intent.get("side")
        if side not in ("buy", "sell") or not isinstance(intent.get("reason"), str) or not intent["reason"].strip():
            return book.refuse("malformed: side is buy or sell, and every intent needs a reason")
        occ = str(intent.get("occ") or intent.get("symbol") or "").upper()
        parsed = parse_occ(occ)
        if parsed is None:
            return book.refuse("this specialty trades options only: name the contract's OCC code")
        if intent.get("type") != "limit":
            return book.refuse("an option order must be a limit order")
        if parsed["underlying"] not in symbols:
            return book.refuse("this contract's underlying is not one you trade")
        limit = _num(intent.get("limit_price"))
        if limit is None or limit <= 0:
            return book.refuse("malformed: a limit order needs a positive limit_price")
        info = contracts.get(occ)
        today = _ny(now_ts).strftime("%Y-%m-%d")
        if side == "buy":
            if info is None or (_parse_ts(info.get("first_print")) or 9e18) > now_ts:
                return book.refuse("not listed at this step: the contract had not printed yet (point-in-time)")
            if parsed["expiry"] <= today:
                return book.refuse("an option entry must expire after today")
        seen = quote(occ, now_ts)
        if seen is None and side == "buy":
            return book.refuse("no quote for this contract at this step: no qualifying print within the quote age")
        if intent.get("quantity") is not None:
            qty = _num(intent.get("quantity"))
        else:
            notional = _num(intent.get("notional_usd"))
            qty = None if notional is None else math.floor(notional / (limit * mult) + 1e-9)
        if qty is None or qty < 1 or abs(qty - round(qty)) > 1e-9:
            return book.refuse("the size is a whole number of contracts, at least one")
        qty = float(round(qty))
        if side == "sell":
            held = book.positions.get(occ, {}).get("quantity", 0.0)
            offered = sum(o["quantity"] for o in book.orders.values() if o["occ"] == occ and o["side"] == "sell")
            if qty > held - offered + EPS:
                return book.refuse("no shorts: a sell is limited to what is held and not already offered")
        else:
            notional = qty * limit * mult
            if notional > book.limits["max_order_usd"] + EPS:
                return book.refuse("over the order cap")
            held_value = book.positions.get(occ, {}).get("quantity", 0.0) * limit * mult
            working = sum(o["quantity"] * o["limit_price"] * mult for o in book.orders.values() if o["occ"] == occ and o["side"] == "buy")
            if held_value + working + notional > book.limits["max_position_usd"] + EPS:
                return book.refuse("over the position cap")
            if notional + qty * fee > book.cash - book.reserved() + EPS:
                return book.refuse("no leverage: not enough free cash for the order and its fee")
        if intent.get("post_only") and seen is not None and (limit >= seen["ask"] if side == "buy" else limit <= (seen["bid"] or 0)):
            return book.refuse("post_only order would cross the estimated touch")
        book.seq += 1
        order_id = f"ord-{book.seq:06d}"
        book.orders[order_id] = {"order_id": order_id, "occ": occ, "ident": {"symbol": parsed["underlying"], "expiry": parsed["expiry"],
                                 "strike": parsed["strike"], "right": parsed["right"]}, "side": side, "quantity": qty, "limit_price": round(limit, 4),
                                 "submitted_at": now, "placed_ts": now_ts, "expires_ts": _session_end(now_ts), "reason": intent["reason"].strip()[:500]}

    def iv_of(occ: str) -> float | None:
        """The contract's implied volatility at its last print, against the underlying then: solved
        the first time a chain shows it (most prints are never shown), the same number either way."""
        seen = last_print[occ]
        if "iv" not in seen:
            args = seen.get("iv_args")
            seen["iv"] = implied_vol(args[0], args[1], args[2], years_to(*args[3]), args[4]) if args else None
        return seen["iv"]

    def chain(now: str) -> list[dict[str, Any]]:
        today = _ny(now_ts).strftime("%Y-%m-%d")
        # A structure agent's chain (`House._chain(structures=True)`): no single-contract affordability
        # line, today's expiry until the entry cut, at most 80 an underlying.
        afford = None if structural else float(limits["max_order_usd"]) / mult
        moment = _ny(now_ts)
        first = today if structural and moment.hour * 60 + moment.minute < structure_hours(today)[0] else None
        per_underlying = STRUCTURE_CHAIN_PER_UNDERLYING if structural else int(rules.get("per_underlying", 40))
        rows_out = []
        near: set[str] = set()  # the reach: the `reach_rule` nearest an underlying, which an open's legs must be among
        for symbol in chain_symbols:
            s = spot.get(symbol)
            listed = by_under.get(symbol, set())
            expired = [occ for occ in listed if contracts[occ]["expiry"] < today]
            listed.difference_update(expired)  # never shown again: expired
            if s is None:
                continue
            price = s[0]
            rows = []
            for occ in listed:
                if gated and (reached_at.get(occ) is None or reached_at[occ] > now_ts + EPS):
                    continue  # kept on the tape for a later reach: not listed before it (`reached`)
                info, seen = contracts[occ], quote(occ, now_ts)
                if seen is None or "bar" not in seen:
                    continue  # a recorded quote alone, with no print yet: not listed by the replay's rule
                expiry = info["expiry"]
                days = (datetime.fromisoformat(expiry).date() - moment.date()).days
                if (expiry <= today and expiry != first) or days > max_days or seen["bid"] is None or (afford is not None and seen["ask"] > afford):
                    continue
                if abs(float(info["strike"]) / price - 1.0) > float(rules.get("moneyness", 0.2)):
                    continue
                rows.append((abs(float(info["strike"]) / price - 1), expiry, occ, info, seen))
            # Nearest the money first, then the nearer expiry; the contract's code breaks a tie (a call and
            # a put of one strike), so the cut and the order are the same in every process.
            rows.sort(key=lambda r: r[:3])
            if structural:
                near.update(r[2] for r in rows[:reach_rule])
            for _, expiry, occ, info, seen in rows[:per_underlying]:
                years = years_to(expiry, now_ts)
                vol = iv_of(occ)  # solved once, at the print, against the underlying then; only for rows shown
                rows_out.append({"symbol": occ, "occ": occ, "underlying": symbol, "expiry": expiry, "strike": float(info["strike"]), "right": info["right"],
                                 "bid": seen["bid"], "ask": seen["ask"], "as_of": seen["bar"]["t"], "last": float(seen["bar"]["c"]),
                                 "iv": None if vol is None else round(vol, 6),
                                 "delta": None if vol is None else round(bs_delta(price, float(info["strike"]), years, vol, info["right"]), 6),
                                 "volume": seen["day_volume"], "trades": seen["day_trades"], "underlying_price": price,
                                 "quote_source": seen.get("source") or "estimated from trade prints (no historical quotes)",
                                 "greeks_source": "computed (Black-Scholes)"})
        reachable.update(ts=now_ts, occs=frozenset(near))
        return rows_out

    def conservative(spec: Any, touches_by_leg: dict[str, dict[str, Any]]) -> tuple[float | None, float | None]:
        """The structure's (bid, ask) a share from each leg's conservative touch (`structure_core.quote`:
        long legs at the ask and short legs at the bid to open, the reverse to close); None where a leg
        has no touch."""
        touches = {}
        for leg in spec.legs:
            seen = touches_by_leg.get(leg.occ)
            if seen is None:
                return None, None
            touches[leg.occ] = (core.dec(float(seen["bid"] or 0.0)), core.dec(float(seen["ask"])))
        bid, ask = core.quote(spec, touches)
        return (None if bid is None else float(bid)), (None if ask is None else float(ask))

    def shown_bid(spec: Any) -> float | None:
        """The structure's SHOWN bid (what it is marked at): each leg's shown quote, as a single
        contract is marked, or its last one; None when a leg has never been priced."""
        shown = {}
        for leg in spec.legs:
            seen = quote(leg.occ, now_ts) or last_print.get(leg.occ)
            if seen is None:
                return None
            shown[leg.occ] = seen
        return conservative(spec, shown)[0]

    def settlement(spec: Any) -> tuple[float | None, str]:
        """What a structure still held at its earliest expiry's close is paid a share, and how: its
        `intrinsic` on the underlying's close that day (one expiry); for a calendar or a diagonal, K plus
        the far legs at their last conservative bid (ask, if short) less the near legs' intrinsic. None
        when the history cannot value it: not evaluated."""
        close = day_close.get((spec.underlying, spec.expiry))
        if close is None:
            return None, "not evaluated: the underlying has no close on the tape on its expiry day"
        spot_at = core.dec(close)
        if spec.type not in core.TWO_EXPIRIES:
            return float(core.intrinsic(spec, spot_at)), "settled at intrinsic on the underlying's close"
        value = float(spec.collateral)
        for leg in spec.legs:
            if leg.expiry == spec.expiry:
                value += leg.sign * leg.ratio * float(core.leg_intrinsic(leg, spot_at))
                continue
            seen = last_exec.get(leg.occ)
            if seen is None:
                return None, "not evaluated: the history never priced its far leg"
            value += leg.ratio * (float(seen["bid"] or 0.0) if leg.sign > 0 else -float(seen["ask"]))
        return max(0.0, value), "settled: the far leg's bid less the near leg's intrinsic"

    def structure_work(now: str) -> None:
        """This step's bars and recorded quotes meet the structure orders placed before it: every leg
        must have printed in this bar (or have a recorded quote after the decision, which is then used),
        each within `max_participation` of its bar's volume for quantity x ratio contracts (one contract
        on a quote alone); a buy fills at the structure's conservative ask when that is within its limit,
        a sell at its conservative bid when that is at or over its limit. All or nothing."""
        nonlocal liquidity_misses
        bar_start = now_ts - step_seconds
        for order_id in list(book.sorders):
            order = book.sorders[order_id]
            if order["placed_ts"] >= now_ts or bar_start >= order["expires_ts"]:
                continue  # placed at this step, or a day order that had expired before this bar began
            touches: dict[str, dict[str, Any]] = {}
            short = False
            for leg in order["spec"].legs:
                printed, real = exec_touch.get(leg.occ), step_quotes.get(leg.occ)
                if real is not None and real["ts"] > order["placed_ts"]:
                    seen, room = real, (liq["max_participation"] * printed["volume"] if printed is not None else 1.0)
                elif printed is not None:
                    seen, room = printed, liq["max_participation"] * printed["volume"]
                else:
                    break  # a leg that did not print: no fill this step
                if order["quantity"] * leg.ratio > room + EPS:
                    short = True
                    break
                touches[leg.occ] = seen
            if short:
                liquidity_misses += 1
                continue
            if len(touches) != len(order["spec"].legs):
                continue
            bid, ask = conservative(order["spec"], touches)
            if order["side"] == "buy" and ask is not None and ask <= order["limit_price"] + EPS:
                del book.sorders[order_id]
                book.sfill(order, round(ask, 4), now, "opened")
            elif order["side"] == "sell" and bid is not None and bid >= order["limit_price"] - EPS and order["code"] in book.held:
                del book.sorders[order_id]
                book.sfill(order, round(bid, 4), now, "expiry rule" if order.get("house") else "closed")

    def submit_structure(intent: dict[str, Any], now: str) -> None:
        """A structure intent (`structure_core.parse`, the House's own rules), refused as the House and
        its book refuse one, or resting as ONE order of the held instrument at its held limit S."""
        if not structural:
            return book.refuse("a structure intent is for a structure agent: its NEEDS carry \"structures\": true")
        try:
            order = core.parse(intent, venue="alpaca")
        except ValueError as exc:
            return book.refuse(f"not a structure order: {str(exc)[:160]}")
        spec = order.spec
        if spec.underlying not in symbols:
            return book.refuse("this structure's underlying is not one you trade")
        code, qty, limit, moment = spec.code, float(order.quantity), float(order.held_limit), _ny(now_ts)
        today = moment.strftime("%Y-%m-%d")
        if order.action == "open":
            if spec.expiry < today or (spec.expiry == today and moment.hour * 60 + moment.minute >= structure_hours(today)[0]):
                cut, close = structure_hours(today)
                return book.refuse(f"no structure is opened on its earliest expiry day from {cut // 60:02d}:{cut % 60:02d} New York: "
                                   f"the House closes what is still held from {close // 60:02d}:{close % 60:02d} and nothing is held into an expiry")
            if reachable["ts"] != now_ts:
                chain(now)  # the chain as it stands at this step, which sets the reach
            if any(leg.occ not in reachable["occs"] for leg in spec.legs):
                # The House's rule live (`House._structure_reach_refusal`), and what keeps a reach-filtered tape honest:
                # a leg's admission depends on the chain at this step alone, never on where the market went after it.
                book.unreached += 1
                return book.refuse(f"outside the chain's reach: every leg of an open must be among the {reach_rule} contracts of its "
                                   "underlying nearest the money that the chain holds at this step (the House's rule live)")
            for leg in spec.legs:
                info = contracts.get(leg.occ)
                if info is None:
                    # A leg the history never saw (a far leg past the tape's expiries, say): the structure
                    # cannot be valued here, so it is not evaluated -- refused, never a loss made up.
                    book.unseen += 1
                    return book.refuse("not evaluated: the history holds no prints of a leg of this structure")
                if (_parse_ts(info.get("first_print")) or 9e18) > now_ts:
                    return book.refuse("not listed at this step: a leg had not printed yet (point-in-time)")
                if quote(leg.occ, now_ts) is None:
                    return book.refuse("no quote for a leg at this step: no qualifying print or recorded quote within the quote age")
            notional = qty * limit * mult  # the structure's maximum loss
            if notional > book.limits["max_order_usd"] + EPS:
                return book.refuse("over the order cap: a structure's maximum loss is its held price x 100 x quantity")
            held_value = book.held.get(code, {}).get("quantity", 0.0) * limit * mult
            working = sum(o["quantity"] * o["limit_price"] * mult for o in book.sorders.values() if o["code"] == code and o["side"] == "buy")
            if held_value + working + notional > book.limits["max_position_usd"] + EPS:
                return book.refuse("over the position cap")
            if notional + qty * fee * spec.contracts > book.cash - book.reserved() + EPS:
                return book.refuse("no leverage: not enough free cash for the structure's maximum loss and its fee")
        else:
            held = book.held.get(code, {}).get("quantity", 0.0)
            offered = sum(o["quantity"] for o in book.sorders.values() if o["code"] == code and o["side"] == "sell")
            if qty > held - offered + EPS:
                return book.refuse("no shorts: a close is limited to the structures held and not already offered")
        book.seq += 1
        order_id = f"ord-{book.seq:06d}"
        book.sorders[order_id] = {"order_id": order_id, "code": code, "spec": spec, "side": order.side, "action": order.action,
                                  "quantity": qty, "limit_price": limit, "natural_limit": float(order.limit_price), "contracts": spec.contracts,
                                  "submitted_at": now, "placed_ts": now_ts, "expires_ts": _session_end(now_ts), "reason": order.reason[:500]}

    def structure_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """The held structures and working structure orders as the House shows them (`House._structure_row`)."""
        held, working = [], []
        for p in book.held.values():
            spec, q = p["spec"], p["quantity"]
            average = (p["cost"] + p["fees"]) / q / mult if q else 0.0  # per share, fees included, as the book reports it
            k = float(spec.collateral)
            natural = (lambda s: s) if not spec.credit else (lambda s: k - s)
            top = spec.max_value
            held.append({"quantity": q, "average_cost": average, "mark": p["mark"], "opened_at": p["opened_at"], "reason": p["reason"],
                         "structure": spec.type, "legs": spec.intent_legs(), "symbol": spec.underlying, "expiry": spec.expiry,
                         "kind": "credit" if spec.credit else "debit", "market_id": p["code"],
                         "natural_open": round(natural(average), 6), "natural_mark": round(natural(p["mark"]), 6),
                         "pnl_usd": round((p["mark"] - average) * mult * q, 2), "max_loss_usd": round(average * mult * q, 2),
                         "max_gain_usd": None if top is None else round(max(0.0, float(top) - average) * mult * q, 2)})
        for o in book.sorders.values():
            if o.get("house"):
                continue
            spec = o["spec"]
            working.append({"order_id": o["order_id"], "side": o["side"], "quantity": o["quantity"], "limit_price": o["limit_price"],
                            "filled": 0.0, "submitted_at": o["submitted_at"], "structure": spec.type, "legs": spec.intent_legs(),
                            "symbol": spec.underlying, "expiry": spec.expiry, "kind": "credit" if spec.credit else "debit",
                            "market_id": o["code"], "action": o["action"], "natural_limit": o["natural_limit"]})
        return held, working

    day_totals: dict[str, tuple[str, float, int]] = {}
    for step in tape["steps"]:
        now = step["t"]
        now_ts = float(_parse_ts(now))
        key = _block_key(now_ts, horizon)
        if key != block_key:
            if block_key is not None:
                close_block()
            block_key, block_active = key, False
        steps_walked += 1
        held_before, fills_before = bool(book.positions or book.held), book.fills
        today = _ny(now_ts).strftime("%Y-%m-%d")
        exec_touch.clear()
        step_quotes.clear()
        # The legs whose conservative touch can matter this step: those of held structures and working
        # structure orders (a fill, the House's offer, a two-expiry settlement read only these).
        watched = {leg.occ for p in book.held.values() for leg in p["spec"].legs} | {leg.occ for o in book.sorders.values() for leg in o["spec"].legs}
        for symbol, bar in (step.get("execution_bars") or {}).items():
            if _num(bar.get("c")):
                spot[symbol] = (float(bar["c"]), now)
                day_close[(symbol, today)] = float(bar["c"])  # the last close of the day so far (steps are in session)
        # (a) the option bars that closed now meet the orders placed before, then become the quote.
        for occ, bar in (step.get("options") or {}).items():
            if isinstance(bar, list) and len(bar) == 6:
                bar = dict(zip(("o", "h", "l", "c", "v", "n"), bar))  # the compact form tapes carry
            if occ not in contracts or not isinstance(bar, dict) or _num(bar.get("c")) is None:
                continue
            work(occ, bar, now)
            if occ in watched and float(bar.get("v") or 0) >= liq["min_volume"] and int(bar.get("n") or 0) >= liq["min_trades"]:
                # A structure leg's CONSERVATIVE touch at this bar: what a fill at the touch pays
                # (`estimate_quote` from the bars before it, as `work` reads it, times the stress).
                wide = estimate_quote(bar, ranges.get(occ, []), model)[2] * stress
                close = float(bar["c"])
                exec_touch[occ] = last_exec[occ] = {"bid": max(0.0, round(close - wide, 4)), "ask": round(close + wide, 4),
                                                    "volume": float(bar.get("v") or 0), "ts": now_ts, "source": "estimate"}
            ranges.setdefault(occ, []).append(max(0.0, float(bar["h"]) - float(bar["l"])))
            del ranges[occ][:-int(model.get("range_bars", 5))]
            day, volume, trades = day_totals.get(occ, ("", 0.0, 0))
            day_totals[occ] = (today, (volume if day == today else 0.0) + float(bar.get("v") or 0), (trades if day == today else 0) + int(bar.get("n") or 0))
            if float(bar.get("v") or 0) >= liq["min_volume"] and int(bar.get("n") or 0) >= liq["min_trades"]:
                _, _, half = estimate_quote(bar, ranges[occ], model)  # what a fill at the touch would pay
                bid, ask = display_quote(float(bar["c"]), model)  # what the strategy is shown and marked at
                info, under = contracts[occ], spot.get(contracts[occ].get("underlying"))
                args = None  # the implied volatility's inputs at this print (`iv_of` solves it when shown)
                if bid is not None and under is not None:
                    args = ((bid + ask) / 2.0, under[0], float(info["strike"]), (info["expiry"], now_ts), info["right"])
                last_print[occ] = {"bar": {"t": now, **bar}, "ts": now_ts, "bid": bid, "ask": ask, "half": half, "iv_args": args,
                                   "day_volume": day_totals[occ][1], "day_trades": day_totals[occ][2]}
                by_under.setdefault(info.get("underlying"), set()).add(occ)
        for occ, q in (step.get("quotes") or {}).items():
            bid, ask, stamp = _num(q.get("bid")), _num(q.get("ask")), _parse_ts(q.get("t"))
            if occ in contracts and bid and ask and 0 < bid < ask and stamp is not None and stamp <= now_ts:
                recorded[occ] = {"bid": bid, "ask": ask, "ts": stamp, "source": "recorded OPRA quote"}
                if structural:
                    step_quotes[occ] = {"bid": bid, "ask": ask, "volume": None, "ts": stamp, "source": "recorded OPRA quote"}
                    if occ in watched:
                        last_exec[occ] = step_quotes[occ]
                by_under.setdefault(contracts[occ].get("underlying"), set()).add(occ)
                # A quote recorded after the order was placed is executable for one contract (its
                # size was not recorded): a buy at or over the ask, a sell at or under the bid.
                for order_id in [k for k, o in book.orders.items() if o["occ"] == occ and o["placed_ts"] < stamp < o["expires_ts"]]:
                    order = book.orders[order_id]
                    if order["quantity"] > 1:
                        continue
                    if order["side"] == "buy" and order["limit_price"] >= ask - EPS:
                        del book.orders[order_id]
                        book.fill(order, ask, now, "recorded quote")
                        quote_fills += 1
                    elif order["side"] == "sell" and order["limit_price"] <= bid + EPS and occ in book.positions:
                        del book.orders[order_id]
                        book.fill(order, bid, now, "expiry rule" if order.get("house") else "sold at a recorded bid")
                        quote_fills += 1
        if book.sorders:
            structure_work(now)
            # The House's entry cut (`House._cancel_structure_opens_at_cut`, review of Sept 25, 2026): from the
            # cut (14:30 New York, 90 minutes before an early close) no OPEN of a structure expiring today
            # rests; the bar that closed at the cut was worked first (it traded before the cut). Closes stay.
            moment = _ny(now_ts)
            if moment.hour * 60 + moment.minute >= structure_hours(today)[0]:
                for order_id in [k for k, o in book.sorders.items() if o["side"] == "buy" and o["spec"].expiry <= today]:
                    del book.sorders[order_id]
                    book.expired_orders += 1
                    book.cut_opens += 1
        for order_id in [k for k, o in book.orders.items() if now_ts >= o["expires_ts"]]:
            del book.orders[order_id]
            book.expired_orders += 1
        for order_id in [k for k, o in book.sorders.items() if now_ts >= o["expires_ts"]]:
            del book.sorders[order_id]
            book.expired_orders += 1
        for symbol, rows in (step.get("history_bars") or {}).items():
            series = history.setdefault(symbol, [])
            series.extend(dict(b) for b in rows)
            del series[:-MAX_BARS]
        # (b) the expiry rule, then marks.
        ny = _ny(now_ts)
        for occ, p in list(book.positions.items()):
            if p["expiry"] < today or (p["expiry"] == today and ny.hour * 60 + ny.minute >= 960):
                p["pnl"] -= p["cost"]
                book.written_off += 1
                book.orders = {k: o for k, o in book.orders.items() if o["occ"] != occ}
                book._close(p, "expired: written off at zero", now)
            elif p["expiry"] == today and ny.hour * 60 + ny.minute >= 870:
                book.orders = {k: o for k, o in book.orders.items() if o["occ"] != occ}
                seen = quote(occ, now_ts) or last_print.get(occ)
                if seen and seen["bid"]:
                    book.seq += 1
                    book.orders[f"ord-{book.seq:06d}"] = {"order_id": f"ord-{book.seq:06d}", "occ": occ, "ident": {}, "side": "sell", "quantity": p["quantity"],
                                                          "limit_price": seen["bid"], "submitted_at": now, "placed_ts": now_ts, "expires_ts": _session_end(now_ts),
                                                          "reason": "The House's expiry rule", "house": True}
                    book.forced += 1
        minutes = ny.hour * 60 + ny.minute
        for code, p in list(book.held.items()):
            if p["expiry"] < today or (p["expiry"] == today and minutes >= 960):
                book.sorders = {k: o for k, o in book.sorders.items() if o["code"] != code}
                price, how = settlement(p["spec"])
                book.settle(p, price, now, how)
            elif p["expiry"] == today and minutes >= structure_hours(today)[1]:
                # The House's expiry-day close: the agent's orders in it cancelled, the whole structure
                # offered at its conservative bid (a cent when a leg has none), re-priced each step.
                book.sorders = {k: o for k, o in book.sorders.items() if o["code"] != code}
                bid = conservative(p["spec"], last_exec)[0]
                book.seq += 1
                order_id = f"ord-{book.seq:06d}"
                book.sorders[order_id] = {"order_id": order_id, "code": code, "spec": p["spec"], "side": "sell", "action": "close",
                                          "quantity": p["quantity"], "limit_price": max(0.01, bid) if bid is not None else 0.01,
                                          "natural_limit": None, "contracts": p["contracts"], "submitted_at": now, "placed_ts": now_ts,
                                          "expires_ts": _session_end(now_ts), "reason": "The House's expiry rule", "house": True}
                house_offers += 1
        for occ, p in book.positions.items():
            seen = quote(occ, now_ts) or last_print.get(occ)
            if seen is not None:
                p["mark"] = seen["bid"] or 0.0
        for p in book.held.values():
            bid = shown_bid(p["spec"])
            if bid is not None:
                p["mark"] = bid
        equity = book.equity()
        if equity > RUIN_EQUITY and (step.get("options") or step.get("execution_bars")):
            decisions += 1
            random.seed(seed + decisions)
            ctx: dict[str, Any] = {
                "now": now, "venue": "alpaca", "rung": 0, "params": copy.deepcopy(effective), "memory": copy.deepcopy(memory),
                "cash": book.cash, "equity": equity, "limits": dict(limits),
                "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07, "option_per_contract": fee},
                "positions": [{"occ": p["occ"], "symbol": p["symbol"], "expiry": p["expiry"], "strike": p["strike"], "right": p["right"],
                               # per share, fees included, as the House's book reports it
                               "quantity": p["quantity"], "average_cost": (p["cost"] + p["fees"]) / p["quantity"] / mult if p["quantity"] else 0.0,
                               "mark": p["mark"], "opened_at": p["opened_at"], "reason": p["reason"]} for p in book.positions.values()],
                "open_orders": [{"order_id": o["order_id"], "occ": o["occ"], "symbol": o["ident"].get("symbol"), "side": o["side"], "quantity": o["quantity"],
                                 "limit_price": o["limit_price"], "filled": 0.0, "submitted_at": o["submitted_at"]} for o in book.orders.values() if not o.get("house")],
                "bars": {s: [dict(b) for b in history.get(s, [])[-bar_limit:]] for s in symbols},
                "quotes": {s: {"bid": v[0] * (1 - half_bps), "ask": v[0] * (1 + half_bps), "t": v[1]} for s, v in spot.items() if s in symbols},
            }
            ctx["chain"] = chain(now)
            shown_rows += len(ctx["chain"])
            if structural:
                held_rows, working_rows = structure_rows()
                ctx["positions"] += held_rows
                ctx["open_orders"] += working_rows
                cap = min(float(limits["max_order_usd"]), float(limits["max_position_usd"]))
                try:
                    ctx["structures"] = core.candidates(ctx["chain"], max_loss_usd=core.dec(cap), today=today)
                except (ValueError, ArithmeticError):
                    ctx["structures"] = []
                if features is not None:
                    ctx["options_features"] = {s: dict(rows[found - 1]) for s, (stamps, rows) in features.items()
                                               for found in (bisect.bisect_right(stamps, now_ts),) if found and s in symbols}
                if feeds is not None:
                    ctx["feeds"] = _feeds_until(feeds, now_ts)
                ctx["structure_rules"] = {"entry_cut_new_york": "14:30 on the structure's earliest expiry day",
                                          "house_close_new_york": "15:30 on the structure's earliest expiry day, at its bid, re-priced each tick",
                                          "fee_per_contract_leg_usd": fee, "book": "replay"}
                structures_shown += len(ctx["structures"])
            answer, error = deadline.call(decide, ctx)
            if error is not None:
                errors += 1
                last_error = error
                if errors >= MAX_ERRORS:
                    return failed("too many errors", errors=errors, last_error=last_error, steps=steps_walked)
            else:
                memory = _clean_memory(answer.get("memory"))
                cancels, intents = answer.get("cancels") or [], answer.get("intents") or []
                for order_id in (cancels if isinstance(cancels, list) else [])[:MAX_CANCELS]:
                    if isinstance(order_id, str) and order_id in book.orders and not book.orders[order_id].get("house"):
                        del book.orders[order_id]
                    elif isinstance(order_id, str) and order_id in book.sorders and not book.sorders[order_id].get("house"):
                        del book.sorders[order_id]
                    else:
                        book.refuse("cancel: no such open order")
                for intent in (intents if isinstance(intents, list) else [])[:MAX_INTENTS]:
                    if isinstance(intent, dict) and (intent.get("structure") or intent.get("spread")):
                        submit_structure(intent, now)
                    elif structural:
                        book.refuse("a structure agent's book holds structures only: send a structure intent "
                                    "(`structure`, `action`, `legs`, `limit_price`: league/CONTRACT.md, Options structures)")
                    else:
                        submit(intent, now)
            equity = book.equity()
        if held_before or book.positions or book.held or book.fills > fills_before:
            block_active = True
        block_equity = equity
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak > 0 else 0.0)
        if equity <= RUIN_EQUITY:
            ruined = True
            close_block(RUIN_LOG_GROWTH)
            block_key = None
            break
    if block_key is not None:
        close_block()
    out_count = max(0, min(len(blocks), int(math.floor(len(blocks) * max(0.0, min(1.0, oos_fraction)) + 1e-9))))
    inside, outside = blocks[: len(blocks) - out_count], blocks[len(blocks) - out_count:]
    result = {
        "ok": True, "blocks": blocks, "trades": len(book.trade_returns), "trade_returns": [round(r, 12) for r in book.trade_returns],
        "fills": book.fills, "maker_fills": 0, "fees_usd": round(book.fees_usd, 10), "refused": book.refused,
        "refusal_reasons": dict(sorted(book.reasons.items())), "errors": errors, "last_error": last_error, "unresolved": 0,
        "expired_orders": book.expired_orders, "open_positions": len(book.positions) + len(book.held),
        "open_orders": len(book.orders) + len(book.sorders),
        "final_equity": round(equity, 10), "return_pct": round((equity / stake - 1.0) * 100.0, 10), "max_drawdown": round(max_drawdown, 12),
        "ruined": ruined, "steps": steps_walked, "horizon": horizon, "venue": "alpaca", "asset_class": "option", "stake": stake,
        "in_sample": {"blocks": len(inside), "mean_log_growth": round(_mean([b["log_growth"] for b in inside]), 12)},
        "out_of_sample": {"blocks": len(outside), "mean_log_growth": round(_mean([b["log_growth"] for b in outside]), 12),
                          "active_blocks": sum(1 for b in outside if b["active"])},
        "needs": needs, "params": effective, "code_sha256": sha,
        "options": {"execution_model": {"quotes": (model.get("kind") or "estimated from trade prints"), "spread_model": model, "liquidity": liq,
                                        "fee_per_contract_usd": fee, "multiplier": mult,
                                        "fills": "limit only; later bars only; at the estimated open touch or one tick through; all or nothing"},
                    "contracts_on_tape": len(contracts), "chain_rows_shown": shown_rows, "forced_expiry_offers": book.forced,
                    "written_off_at_expiry": book.written_off, "liquidity_misses": liquidity_misses,
                    "recorded_quote_fills": quote_fills, "recorded_quotes_seen": len(recorded)},
    }
    if structural:
        # A structure is one trade: `trades` above counts closed structures (settled ones included).
        result["options"]["structures"] = {
            "opened": book.structures_opened, "closed": book.structures_closed, "settled_at_expiry": book.settled,
            "not_evaluated": book.not_evaluated, "unseen_leg_refusals": book.unseen, "house_close_offers": house_offers,
            "outside_reach_refusals": book.unreached, "reach": reach_rule,
            "opens_cancelled_at_the_cut": book.cut_opens,
            "candidates_shown": structures_shown,
            "execution": ("structures: later bars only; every leg printed in the bar or quoted after the decision; long legs at "
                          "the conservative ask and short legs at the conservative bid to open, the reverse to close; "
                          "quantity x ratio within max_participation of each leg's bar volume; all or nothing; "
                          "settled at intrinsic (or the far leg's bid less the near leg's intrinsic) at the expiry's close")}
    result["digest"] = digest(book.trade_log)
    if audit:
        result["fill_log"] = book.fill_log
        result["final_memory"] = memory
    return result
