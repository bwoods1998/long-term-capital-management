"""execution-recovery-v2: does a practice account come back from a restart exactly as it would have gone on, and does it
reject exactly the intents it must.

The tree under test's practice engine (`league.live.shadow.ShadowAccount` on a `league.live.chains.LiveDay`, the
account every practice and shadow instance runs) trades invented quotes for a synthetic program. Each scenario runs
two accounts in lockstep over the same minutes and intents; one is saved and restored (`to_state` -> JSON ->
`from_state`, what a House restart does) at a chosen minute. Any difference in cash, fills, counts or saved state at
the end is a restart divergence. Separately, well-formed intents that a flat account can afford must not be rejected,
and malformed intents (zero or fractional quantity, a NaN or negative limit, no legs, an unknown side, right, type or
root) must be: accepting one is unsafe. Labels are fixed by construction.

dev (this file): four fixed scenarios (a marketable open, a resting open, a partial fill, a close) with the restart in
the middle, and the malformed intents below. heldout: scenarios with seeded quote paths, sizes, intent schedules and
restart minutes, their count, noise and salt from the lane's PRIVATE pool (outside this public repo, on standard input
only: `_common.args`, `--pool-stdin`), and the pool's own malformed intents beside this file's. Answer:
restart_divergences, valid_rejected, invalid_accepted, cpu_seconds (the lane's cost).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

import _common

PROTOCOL = "execution-recovery-v2"
CODE = "NEEDS = {'roots': ['SPY'], 'dte': [1, 1], 'cadence': 1}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
STRIKES = (598.0, 600.0, 602.0)
MINUTES = 40


def symbol(right: str, strike: float) -> str:
    return f"SPY260929{right}{int(round(strike * 1000)):08d}"


def leg(right: str, strike: float, side: str = "long") -> dict[str, Any]:
    return {"side": side, "right": right, "dte": 1, "strike": strike}


def scenario(r: Any, name: str, pool: dict | None = None) -> dict[str, Any]:
    """Quotes per minute and intents per minute; `r` None gives the fixed dev scenario `name`; `pool` the held-out
    split's private noise and sizes."""
    pool = pool or {}
    step, jitter = float(pool.get("spot_step", 0.25)), float(pool.get("mid_jitter", 0.1))
    halves, sizes = tuple(pool.get("halves") or (0.05, 0.1, 0.15)), tuple(pool.get("sizes") or (1, 2, 5, 10))
    quotes, spot = [], 600.0
    for mi in range(MINUTES):
        spot += 0.0 if r is None else r.gauss(0.0, step)
        row = {}
        for right in ("C", "P"):
            for strike in STRIKES:
                intrinsic = max(0.0, spot - strike) if right == "C" else max(0.0, strike - spot)
                mid = round(intrinsic + 1.6 + (0.0 if r is None else r.uniform(-jitter, jitter)), 2)
                half = 0.1 if r is None else round(r.choice(halves), 2)
                size = (1 if (name == "partial" and 1 <= mi <= 2) else 10) if r is None else r.choice(sizes)
                row[symbol(right, strike)] = (round(mid - half, 2), round(mid + half, 2), size)
        quotes.append((spot, row))
    intents: dict[int, list[dict[str, Any]]] = {}
    if r is None:
        right, strike = ("C", 600.0) if name != "resting" else ("P", 600.0)
        bid, ask, _ = quotes[0][1][symbol(right, strike)]
        limit = ask if name in ("marketable", "close", "partial") else round(bid - 0.3, 2)
        qty = 3 if name == "partial" else 1
        intents[0] = [{"open": "long_call" if right == "C" else "long_put", "root": "SPY", "qty": qty,
                       "limit": {"price": limit}, "legs": [leg(right, strike)]}]
        if name == "close":
            intents[12] = [{"close": "first", "limit": "natural"}]
        return {"quotes": quotes, "intents": intents, "restarts": [MINUTES // 2]}
    for _ in range(r.randint(3, 6)):
        mi = r.randrange(0, MINUTES - 5)
        right, strike = r.choice(("C", "P")), r.choice(STRIKES)
        bid, ask, _ = quotes[mi][1][symbol(right, strike)]
        limit = r.choice((ask, round((bid + ask) / 2, 2), round(bid - 0.2, 2)))
        intents.setdefault(mi, []).append({"open": "long_call" if right == "C" else "long_put", "root": "SPY",
                                           "qty": r.choice((1, 1, 2, 3)), "limit": {"price": limit},
                                           "legs": [leg(right, strike)]})
    for _ in range(r.randint(0, 2)):
        intents.setdefault(r.randrange(10, MINUTES - 1), []).append({"close": "first", "limit": "natural"})
    restarts = sorted(r.sample(range(1, MINUTES - 1), r.choice(tuple(pool.get("restarts") or (1, 1, 2)))))
    return {"quotes": quotes, "intents": intents, "restarts": restarts}


INVALID = [
    {"open": "long_call", "root": "SPY", "qty": 0, "limit": {"price": 1.7}, "legs": [leg("C", 600.0)]},
    {"open": "long_call", "root": "SPY", "qty": -1, "limit": {"price": 1.7}, "legs": [leg("C", 600.0)]},
    {"open": "long_call", "root": "SPY", "qty": 1.5, "limit": {"price": 1.7}, "legs": [leg("C", 600.0)]},
    {"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": float("nan")}, "legs": [leg("C", 600.0)]},
    {"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": -1.0}, "legs": [leg("C", 600.0)]},
    {"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": 1.7}, "legs": []},
    {"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": 1.7}, "legs": [leg("C", 600.0, side="sideways")]},
    {"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": 1.7}, "legs": [{"side": "long", "right": "X", "dte": 1, "strike": 600.0}]},
    {"open": "naked_call", "root": "SPY", "qty": 1, "limit": {"price": 1.7}, "legs": [leg("C", 600.0)]},
    {"open": "long_call", "root": "QQQ", "qty": 1, "limit": {"price": 1.7}, "legs": [leg("C", 600.0)]},
]


def main() -> None:
    opts = _common.args()
    # The held-out draws are fixed before the tree's code loads; the pool is not kept past this point.
    pool = dict(opts.pool or {})
    opts.pool = None
    names = ("marketable", "resting", "partial", "close")
    salt = str(pool.get("salt") or "")
    runs = [(None, n) for n in names] if opts.split == "dev" else \
        [(_common.rng(opts.seed, f"{PROTOCOL}:{salt}:{k}"), f"heldout-{k}") for k in range(int(pool.get("scenarios", 12)))]
    plans = [(scenario(r, name, pool), name) for r, name in runs]
    invalid = list(INVALID) + ([] if opts.split == "dev" else [dict(i) for i in pool.get("invalid") or []])

    def body() -> dict[str, Any]:
        from league.gym.runtime import load_program
        from league.live.chains import LiveDay
        from league.live.shadow import ShadowAccount
        from league.tests.live_fakes import MONDAY, at, iso

        needs = load_program(CODE).needs

        def account():
            return ShadowAccount(instance="synthetic", family="synthetic", needs=needs, params={}, capital=10000)

        def saved(acct):
            # Each account carries its own random identity nonce; everything else must match.
            return json.dumps({k: v for k, v in acct.to_state().items() if k != "nonce"}, sort_keys=True, default=str)

        def restore(acct):
            return ShadowAccount.from_state(json.loads(json.dumps(acct.to_state(), allow_nan=True)))

        def day_with(quotes):
            day = LiveDay(MONDAY, 570, 960, trading_days=[MONDAY, MONDAY + dt.timedelta(days=1)])

            def advance(mi):
                spot, row = quotes[mi]
                stamp = iso(at(MONDAY, 9, 30, 0) + mi * 60)
                day.chain("SPY").record(mi, {sym: {"latestQuote": {"bp": b, "ap": a, "bs": s, "as": s, "t": stamp}}
                                             for sym, (b, a, s) in row.items()}, open_epoch=at(MONDAY, 9, 30, 0))
                day.chain("SPY").set_price(mi, spot)
                day.advance(mi)
            return day, advance

        def resolve(intent, acct):
            if intent.get("close") == "first":
                pids = sorted(acct.positions)
                return dict(intent, close=pids[0]) if pids else None
            return intent

        divergences = valid_rejected = 0
        for plan, name in plans:
            day, advance = day_with(plan["quotes"])
            a, b = account(), account()
            for mi in range(MINUTES):
                advance(mi)
                a.pre(day, mi)
                b.pre(day, mi)
                for intent in plan["intents"].get(mi, []):
                    real = resolve(intent, a)
                    if real is None:
                        continue
                    before = len(a.rejects_since)
                    a.apply(day, mi, [real])
                    b.apply(day, mi, [real])
                    if "open" in real and len(a.rejects_since) > before:
                        valid_rejected += 1
                if mi in plan["restarts"]:
                    b = restore(b)
            same = a.cash == b.cash and a.counts == b.counts and a.fill_rows == b.fill_rows and saved(a) == saved(b)
            divergences += not same
        invalid_accepted = 0
        day, advance = day_with(scenario(None, "marketable")["quotes"])
        advance(0)
        for intent in invalid:
            acct = account()
            acct.pre(day, 0)
            before = len(acct.orders)
            try:
                acct.apply(day, 0, [dict(intent)])
            except Exception:  # noqa: BLE001 - an exception is a refusal, not an acceptance
                continue
            invalid_accepted += len(acct.orders) > before
        return {"restart_divergences": divergences, "valid_rejected": valid_rejected, "invalid_accepted": invalid_accepted,
                "scenarios": len(plans), "invalid_cases": len(invalid), "cases": len(plans) + len(invalid)}

    _common.answer(PROTOCOL, opts, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
