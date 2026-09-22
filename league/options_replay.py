"""Rung 0 for the options desk: walk an options tape (`league/options_history.py`) with a
long-calls-and-puts strategy, under the House's own option rules.

Self-contained beside `replay.py` in the agent's box (standard library plus `replay.py`'s helpers).
`replay.run_replay` hands a tape with `"asset_class": "option"` here, and the result has the same
shape as every other replay, so the evaluator's gates judge it unchanged.

EXECUTION IS ESTIMATED, AND CONSERVATIVE, BECAUSE NO HISTORICAL OPTION QUOTES EXIST.

- A contract is tradable at a step only if it has printed at or before it (point-in-time
  listing), expires AFTER today (New York), and its last qualifying print is at most
  `quote_age_seconds` old (the book's own option quote-age rule). Otherwise: refused.
- Its bid and ask are ESTIMATED around the last print (`estimate_quote`): at least a tick, 4% of
  the premium or half the median recent bar range either side, times `spread_stress`.
- Limit orders only (the House refuses option market orders). Nothing fills in the bar the
  decision saw: an order is worked against LATER bars of its contract that printed at least
  `min_volume` contracts in `min_trades` trades, and at most `max_participation` of the bar's
  volume (all or nothing). A buy fills at the estimated ask at the bar's open if its limit is
  at least that, else at its own limit only when the bar traded at least one tick THROUGH it
  (`low <= limit - tick`): a touched limit is not a fill. Sells mirror this.
- Orders are day orders: an unfilled one expires at 16:00 New York.
- One contract is 100 shares: every premium is paid and received times 100. Fees are
  `fee_per_contract_usd` a contract a fill (an assumed regulatory pass-through; Alpaca charges no
  commission, `league/fees.py`).
- The expiry rule: from 14:30 New York on its last day the House cancels the agent's orders in a
  held contract and offers it at the estimated bid, re-priced each step. Whatever is still held
  when that session ends is written off at ZERO (the book's `expire_options`), never exercised.
- Holdings are marked at the estimated bid of their last print.
"""

from __future__ import annotations

import copy
import math
import random
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

try:
    from league.replay import (MAX_BARS, MAX_CANCELS, MAX_ERRORS, MAX_INTENTS, RUIN_EQUITY, RUIN_LOG_GROWTH, _block_key,
                               _clean_memory, _mean, _num, _parse_ts, digest)
    from league.options_history import estimate_quote, parse_occ, tick, implied_vol, bs_delta, years_to
except ImportError:  # in the agent's box the files sit side by side
    from replay import (MAX_BARS, MAX_CANCELS, MAX_ERRORS, MAX_INTENTS, RUIN_EQUITY, RUIN_LOG_GROWTH, _block_key,  # type: ignore
                        _clean_memory, _mean, _num, _parse_ts, digest)
    from options_history import estimate_quote, parse_occ, tick, implied_vol, bs_delta, years_to  # type: ignore

NY = ZoneInfo("America/New_York")
EPS = 1e-9


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
        self.seq = self.fills = self.refused = self.expired_orders = self.written_off = self.forced = 0
        self.fees_usd = 0.0
        self.reasons: dict[str, int] = {}
        self.trade_returns: list[float] = []
        self.trade_log: list[dict[str, Any]] = []
        self.fill_log: list[dict[str, Any]] | None = [] if record else None

    def refuse(self, why: str) -> None:
        self.refused += 1
        self.reasons[why] = self.reasons.get(why, 0) + 1

    def equity(self) -> float:
        return self.cash + sum(p["quantity"] * p["mark"] * self.mult for p in self.positions.values())

    def reserved(self) -> float:
        return sum(o["quantity"] * (o["limit_price"] * self.mult + self.fee_rate) for o in self.orders.values() if o["side"] == "buy")

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
    liq = {"min_volume": 5.0, "min_trades": 2, "max_participation": 0.10, "quote_age_seconds": 1500, **(tape.get("liquidity") or {})}
    mult = int(tape.get("multiplier") or 100)
    fee = float(tape.get("fee_per_contract_usd") if tape.get("fee_per_contract_usd") is not None else 0.05)
    symbols = [s for s in (needs.get("symbols") or tape.get("symbols") or []) if isinstance(s, str)]
    chain_symbols = symbols[:8]
    max_days = int(needs.get("max_days_to_expiry") or rules.get("max_days_to_expiry") or 21)
    max_days = max(2, min(max_days, 45))
    bar_limit = int(_num((needs.get("bars") or {}).get("limit")) or 120)
    bar_limit = max(1, min(MAX_BARS, bar_limit))
    half_bps = float(_num(tape.get("half_spread_bps")) or 1.0) / 10000.0
    book = _Book(stake, limits, fee, mult, liq, audit)
    history = {s: [dict(b) for b in rows[-MAX_BARS:]] for s, rows in (tape.get("warmup_bars") or {}).items()}
    last_print: dict[str, dict[str, Any]] = {}   # occ -> {"bar", "ts", "half", "bid", "ask"}
    ranges: dict[str, list[float]] = {}
    spot: dict[str, tuple[float, str]] = {}
    by_under: dict[str, set[str]] = {}  # underlying -> contracts that have printed
    recorded: dict[str, dict[str, Any]] = {}  # occ -> the last recorded OPRA quote {"bid", "ask", "ts", "source"}
    quote_fills = 0
    memory: dict[str, Any] = {}
    errors, last_error = 0, ""
    blocks: list[dict[str, Any]] = []
    block_key, block_active, block_equity, previous_equity = None, False, stake, stake
    peak, max_drawdown, equity, ruined, steps_walked, decisions = stake, 0.0, stake, False, 0, 0
    shown_rows = liquidity_misses = 0
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
        """Later bars meet working orders: at the estimated open touch, or one tick through."""
        nonlocal liquidity_misses
        volume, trades = float(bar.get("v") or 0), int(bar.get("n") or 0)
        _, _, half = estimate_quote(bar, ranges.get(occ, []), model)
        for order_id in [k for k, o in book.orders.items() if o["occ"] == occ]:
            order = book.orders[order_id]
            if order["placed_ts"] >= now_ts:
                continue
            if volume < liq["min_volume"] or trades < liq["min_trades"] or order["quantity"] > liq["max_participation"] * volume + EPS:
                liquidity_misses += 1
                continue
            limit, step = order["limit_price"], tick(order["limit_price"])
            if order["side"] == "buy":
                ask_open = float(bar["o"]) + half
                price = ask_open if limit >= ask_open - EPS else (limit if float(bar["l"]) <= limit - step + EPS else None)
            else:
                bid_open = float(bar["o"]) - half
                price = bid_open if bid_open > 0 and limit <= bid_open + EPS else (limit if float(bar["h"]) >= limit + step - EPS else None)
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

    def chain(now: str) -> list[dict[str, Any]]:
        today = _ny(now_ts).strftime("%Y-%m-%d")
        afford = float(limits["max_order_usd"]) / mult
        rows_out = []
        for symbol in chain_symbols:
            s = spot.get(symbol)
            if s is None:
                continue
            price = s[0]
            rows = []
            for occ in by_under.get(symbol, ()):
                info, seen = contracts[occ], quote(occ, now_ts)
                if seen is None or "bar" not in seen:
                    continue  # a recorded quote alone, with no print yet: not listed by the replay's rule
                expiry = info["expiry"]
                days = (datetime.fromisoformat(expiry).date() - _ny(now_ts).date()).days
                if expiry <= today or days > max_days or seen["bid"] is None or seen["ask"] > afford:
                    continue
                if abs(float(info["strike"]) / price - 1.0) > float(rules.get("moneyness", 0.2)):
                    continue
                years = years_to(expiry, now_ts)
                vol = seen.get("iv")  # solved once, at the print, against the underlying then
                rows.append({"symbol": occ, "occ": occ, "underlying": symbol, "expiry": expiry, "strike": float(info["strike"]), "right": info["right"],
                             "bid": seen["bid"], "ask": seen["ask"], "as_of": seen["bar"]["t"], "last": float(seen["bar"]["c"]),
                             "iv": None if vol is None else round(vol, 6),
                             "delta": None if vol is None else round(bs_delta(price, float(info["strike"]), years, vol, info["right"]), 6),
                             "volume": seen["day_volume"], "trades": seen["day_trades"], "underlying_price": price,
                             "quote_source": seen.get("source") or "estimated from trade prints (no historical quotes)",
                             "greeks_source": "computed (Black-Scholes)"})
            rows.sort(key=lambda r: (abs(r["strike"] / price - 1), r["expiry"]))
            rows_out += rows[:int(rules.get("per_underlying", 40))]
        return rows_out

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
        held_before, fills_before = bool(book.positions), book.fills
        today = _ny(now_ts).strftime("%Y-%m-%d")
        for symbol, bar in (step.get("execution_bars") or {}).items():
            if _num(bar.get("c")):
                spot[symbol] = (float(bar["c"]), now)
        # (a) the option bars that closed now meet the orders placed before, then become the quote.
        for occ, bar in (step.get("options") or {}).items():
            if isinstance(bar, list) and len(bar) == 6:
                bar = dict(zip(("o", "h", "l", "c", "v", "n"), bar))  # the compact form tapes carry
            if occ not in contracts or not isinstance(bar, dict) or _num(bar.get("c")) is None:
                continue
            work(occ, bar, now)
            ranges.setdefault(occ, []).append(max(0.0, float(bar["h"]) - float(bar["l"])))
            del ranges[occ][:-int(model.get("range_bars", 5))]
            day, volume, trades = day_totals.get(occ, ("", 0.0, 0))
            day_totals[occ] = (today, (volume if day == today else 0.0) + float(bar.get("v") or 0), (trades if day == today else 0) + int(bar.get("n") or 0))
            if float(bar.get("v") or 0) >= liq["min_volume"] and int(bar.get("n") or 0) >= liq["min_trades"]:
                bid, ask, half = estimate_quote(bar, ranges[occ], model)
                info, under = contracts[occ], spot.get(contracts[occ].get("underlying"))
                vol = None
                if bid is not None and under is not None:
                    vol = implied_vol((bid + ask) / 2.0, under[0], float(info["strike"]), years_to(info["expiry"], now_ts), info["right"])
                last_print[occ] = {"bar": {"t": now, **bar}, "ts": now_ts, "bid": bid, "ask": ask, "half": half, "iv": vol,
                                   "day_volume": day_totals[occ][1], "day_trades": day_totals[occ][2]}
                by_under.setdefault(info.get("underlying"), set()).add(occ)
        for occ, q in (step.get("quotes") or {}).items():
            bid, ask, stamp = _num(q.get("bid")), _num(q.get("ask")), _parse_ts(q.get("t"))
            if occ in contracts and bid and ask and 0 < bid < ask and stamp is not None and stamp <= now_ts:
                recorded[occ] = {"bid": bid, "ask": ask, "ts": stamp, "source": "recorded OPRA quote"}
                by_under.setdefault(contracts[occ].get("underlying"), set()).add(occ)
                # A quote recorded after the order was placed is executable for one contract (its
                # size was not recorded): a buy at or over the ask, a sell at or under the bid.
                for order_id in [k for k, o in book.orders.items() if o["occ"] == occ and o["placed_ts"] < stamp]:
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
        for order_id in [k for k, o in book.orders.items() if now_ts >= o["expires_ts"]]:
            del book.orders[order_id]
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
        for occ, p in book.positions.items():
            seen = quote(occ, now_ts) or last_print.get(occ)
            if seen is not None:
                p["mark"] = seen["bid"] or 0.0
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
                    else:
                        book.refuse("cancel: no such open order")
                for intent in (intents if isinstance(intents, list) else [])[:MAX_INTENTS]:
                    submit(intent, now)
            equity = book.equity()
        if held_before or book.positions or book.fills > fills_before:
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
        "expired_orders": book.expired_orders, "open_positions": len(book.positions), "open_orders": len(book.orders),
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
    result["digest"] = digest(book.trade_log)
    if audit:
        result["fill_log"] = book.fill_log
        result["final_memory"] = memory
    return result
