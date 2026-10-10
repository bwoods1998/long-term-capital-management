"""The equity Gym engine (DESIGN 11's engine list): golden P&L, no look-ahead, as-of identity, cash >= 0, the holds,
determinism, open AND close fills, and the result's views.

`league.equity.sizing.size_entry` is money's; these tests mock it at the interface with `fake_size_entry`, the rule its
docstring fixes, for the Gym's case (no loss budget). `RealSizing` runs the same programs through money's function once
it lands (skipped while it is a stub).
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import random
import tempfile
import unittest
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import config, engine, results, sizing, synth
from league.equity.ctx import ctx_bytes
from league.equity.engine import EngineConfig, fill_price, official, run, run_isolated, split_factor
from league.equity.program import load_program
from league.equity.store import EquityStore, nyse_sessions, write_store

D = dt.date
CENT = Decimal("0.01")
SIX = Decimal("0.000001")


def fake_size_entry(x: sizing.SizingInputs) -> sizing.Sized:
    """`size_entry`'s rule (league/equity/sizing.py's docstring) for the tests: refusals, the intent, the caps in order,
    the budget when there is one, the minimum order; qty floored to 6 places, usd = qty x limit."""
    if x.cash < 0:
        return sizing.Sized(Decimal(0), Decimal(0), "cash_negative", "the account owes cash")
    if x.any_short:
        return sizing.Sized(Decimal(0), Decimal(0), "short_held", "a short is held")
    target, binding = (x.sleeve_equity * x.share if x.share is not None else x.usd), "intent"
    caps = [("instrument", x.position_share * x.E - x.account_symbol_value),
            ("sleeve_cap", x.position_share * x.sleeve_equity - x.sleeve_symbol_value),
            ("sleeve_cash", x.sleeve_free_cash), ("invested", x.invested_share * x.E - x.invested_now),
            ("cash", x.available_cash)]
    if x.budget_room is not None:
        caps.append(("budget", x.budget_room / x.weight))
    for name, cap in caps:
        if cap < target:
            target, binding = max(cap, Decimal(0)), name
    if target < x.min_order_usd:
        return sizing.Sized(Decimal(0), Decimal(0), "min_order", f"${target:.2f} is under the minimum order")
    qty = (target / x.limit_price).quantize(SIX, rounding=ROUND_DOWN)
    return sizing.Sized(qty * x.limit_price, qty, binding, f"{binding} binds")


def gym_sizing():
    return mock.patch.object(sizing, "size_entry", fake_size_entry)


@contextlib.contextmanager
def recorded():
    """Every ctx the engine builds, in order (the engine's `build` wrapped)."""
    seen: list = []
    real = engine.build

    def wrapper(inputs):
        ctx = real(inputs)
        seen.append(ctx)
        return ctx

    with mock.patch.object(engine, "build", wrapper):
        yield seen


def program(body: str, *, symbols=("SPY",), history=2, max_hold=20, params="{}"):
    code = (f"NEEDS = {{'symbols': {list(symbols)!r}, 'history': {history}, 'max_hold_sessions': {max_hold}}}\n"
            f"PARAMS = {params}\nSTATE = {{'n': 0}}\n\ndef decide(ctx):\n    STATE['n'] += 1\n" +
            "".join(f"    {line}\n" for line in body.strip("\n").splitlines()))
    return load_program(code, name="test")


def hand_store(root, rows: dict[str, list[tuple[float, float, float, float]]], *, start=D(2025, 1, 2), gate=False):
    """A store from hand rows per symbol: (raw open, raw close, all open, all close) a session from `start`."""
    n = max(len(r) for r in rows.values())
    cal = nyse_sessions(start, start + dt.timedelta(days=n * 2 + 14))[:n]
    days = [d for d, _ in cal]
    series = {}
    for sym, sym_rows in rows.items():
        ro, rc, ao, ac = (list(col) for col in zip(*sym_rows))
        series[sym] = {"days": days[:len(sym_rows)], "raw_o": ro, "raw_h": [max(a, b) for a, b in zip(ro, rc)],
                       "raw_l": [min(a, b) for a, b in zip(ro, rc)], "raw_c": rc, "raw_v": [1e6] * len(ro),
                       "all_o": ao, "all_h": [max(a, b) for a, b in zip(ao, ac)],
                       "all_l": [min(a, b) for a, b in zip(ao, ac)], "all_c": ac}
    write_store(root, calendar=cal, series=series, classes={s: config.class_of(s) for s in rows},
                fetched_through=days[-1], source="synthetic", gate=gate)
    return EquityStore(root).bars(list(rows), "validation", history=0), days


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tmp = Path(self.dir.name)
        patcher = gym_sizing()
        patcher.start()
        self.addCleanup(patcher.stop)

    def synthetic(self, name="s", **kw):
        kw.setdefault("start", D(2024, 10, 1))
        kw.setdefault("end", D(2025, 12, 31))
        return synth.synthetic_store(self.tmp / name, **kw)


class Pieces(unittest.TestCase):
    def test_fill_price(self):
        self.assertAlmostEqual(fill_price(100.0, "buy", 0.0001, 1.0), 100.01)
        self.assertAlmostEqual(fill_price(100.0, "sell", 0.0003, 1.5), 99.955)
        for args in ((0.0, "buy", 0.0001, 1.0), (float("nan"), "buy", 0.0001, 1.0), (100.0, "short", 0.0001, 1.0),
                     (100.0, "buy", -0.1, 1.0), (100.0, "sell", 0.5, 2.0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                fill_price(*args)

    def test_split_factors(self):
        self.assertEqual(split_factor(0.5), 2)
        self.assertEqual(split_factor(0.05), 20)
        self.assertEqual(split_factor(10.0), Fraction(1, 10), "a 1-for-10 reverse split")
        self.assertEqual(split_factor(2 / 3), Fraction(3, 2))
        self.assertEqual(split_factor(0.5 * 0.99), 2, "a split and a dividend on one day")
        self.assertIsNone(split_factor(0.98), "a dividend is not a split")
        self.assertIsNone(split_factor(1.0))

    def test_fees_are_each_rounded_up_and_taf_capped(self):
        self.assertEqual(config.sell_fees(Decimal("504.84951"), Decimal("4.95")), Decimal("0.03"))
        self.assertEqual(config.sell_fees(Decimal("1000000"), Decimal("100000")), Decimal("27.80") + Decimal("8.30"))
        self.assertEqual(config.sell_fees(Decimal(0), Decimal(0)), Decimal(0))
        with self.assertRaises(ValueError):
            config.sell_fees(Decimal(-1), Decimal(1))

    def test_config_helpers(self):
        self.assertEqual((config.class_of("spy"), config.class_of("AAPL"), config.class_of("TSLA")),
                         ("etf", "stock", None))
        self.assertEqual((config.half_spread("SPY"), config.half_spread("XLK"), config.half_spread("GLD")),
                         (0.0001, 0.0003, 0.0005))
        with self.assertRaises(KeyError):
            config.half_spread("TSLA")
        self.assertEqual(set(config.HALF_SPREAD_BP), set(config.UNIVERSE))
        self.assertTrue(config.may_sell(3, 4))
        self.assertFalse(config.may_sell(4, 4))
        self.assertTrue(config.max_hold_due(19, 20), "held 20 by the next open: out at it")
        self.assertFalse(config.max_hold_due(18, 20))
        self.assertTrue(config.max_hold_due(0, 1), "a maximum of 1: sold at the open after its entry session")


class Golden(Case):
    def test_open_buy_close_sell_with_half_spreads_and_fees(self):
        root = synth.constant_store(self.tmp / "c", sessions=6, price=100.0, step=1.0)
        bars = EquityStore(root).bars(["SPY"], "validation", history=0)
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'share': 0.5, 'at': 'open'}]
return [{'sell': p['id'], 'at': 'close'} for p in ctx.positions]
""")
        result = run(prog, bars)
        [trade] = result["trades"][:1]
        # Bought at session 1's open 101 x (1 + 1 bp); sold at session 2's close 102 x (1 - 1 bp).
        buy, sell = Decimal("101.0101"), Decimal("101.9898")
        qty = (Decimal(500) / buy).quantize(SIX, rounding=ROUND_DOWN)
        self.assertEqual(qty, Decimal("4.950000"))
        proceeds = qty * sell
        sec = (proceeds * Decimal("27.80") / Decimal(10 ** 6)).quantize(CENT, rounding=ROUND_CEILING)
        taf = (qty * Decimal("0.000166")).quantize(CENT, rounding=ROUND_CEILING)
        self.assertEqual((sec, taf), (Decimal("0.02"), Decimal("0.01")))
        net = proceeds - qty * buy - sec - taf
        days = [d.isoformat() for d, _ in nyse_sessions(D(2025, 1, 2), D(2025, 1, 31))]
        self.assertEqual((trade["entry_day"], trade["entry_at"], trade["exit_day"], trade["exit_at"]),
                         (days[1], "open", days[2], "close"))
        self.assertEqual((trade["entry_px"], trade["exit_px"], trade["qty"]), (101.0101, 101.9898, 4.95))
        self.assertEqual((trade["notional"], trade["fees"], trade["div"]), (500.0, 0.03, 0.0))
        self.assertEqual(trade["net"], float(net.quantize(CENT)))
        self.assertEqual(trade["net"], 4.82)
        self.assertEqual((trade["held_sessions"], trade["reason"]), (1, "program"))
        self.assertAlmostEqual(trade["return"], float(net / (qty * buy)), places=8)
        cash = Decimal(1000) - qty * buy + proceeds - sec - taf
        self.assertEqual(result["daily"][2][2], float(cash.quantize(CENT)))
        self.assertEqual(result["daily"][1], [days[1], -0.05, 999.95, 0.5])
        self.assertEqual(result["summary"]["fees"], 0.03)
        lot = result["lots"][0]
        self.assertEqual((lot["weight"], lot["hs"], lot["reason"]),
                         (round(float(qty * buy / 1000), 8), 0.0001, "program"))

    def test_a_dividend_through_the_ratio_is_cash_on_lots_held_at_the_previous_close(self):
        # Raw closes 100, 100, 98 (ex $2), 98, 98; adjustment=all is raw x 0.98 before the ex-day.
        bars, days = hand_store(self.tmp / "d", {"SPY": [(100, 100, 98, 98), (100, 100, 98, 98), (98, 98, 98, 98),
                                                         (98, 98, 98, 98), (98, 98, 98, 98)]})
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'usd': 200, 'at': 'close'}, {'buy': 'SPY', 'usd': 100, 'at': 'open'}]
if STATE['n'] == 2:
    return [{'buy': 'SPY', 'usd': 100, 'at': 'open'}]
return [{'sell': p['id'], 'at': 'open'} for p in ctx.positions]
""")
        result = run(prog, bars)
        by_id = {t["id"]: t for t in result["trades"]}
        # Lots 1 (open of session 1) and 2 (close of session 1) were held at session 1's close: $2 a share each.
        lot1_qty = (Decimal(100) / Decimal("100.01")).quantize(SIX, rounding=ROUND_DOWN)
        lot2_qty = (Decimal(200) / Decimal("100.01")).quantize(SIX, rounding=ROUND_DOWN)
        self.assertEqual((lot1_qty, lot2_qty), (Decimal("0.999900"), Decimal("1.999800")))
        self.assertEqual((by_id[1]["div"], by_id[2]["div"]), (2.0, 4.0))
        self.assertEqual(by_id[3]["div"], 0.0, "a lot bought at the ex-day's open earns nothing")
        self.assertEqual(result["actions"], [{"symbol": "SPY", "day": days[2].isoformat(), "kind": "dividend",
                                              "per_share": 2.0}])
        proceeds = lot2_qty * Decimal("97.9902")
        fees = config.sell_fees(proceeds, lot2_qty)
        self.assertEqual(by_id[2]["net"], float((proceeds - lot2_qty * Decimal("100.01") - fees +
                                                 (lot2_qty * 2).quantize(CENT)).quantize(CENT)))
        self.assertEqual(result["summary"]["dividends"], round(by_id[1]["div"] + by_id[2]["div"], 2))

    def test_a_split_through_the_ratio_scales_shares_and_entry(self):
        bars, days = hand_store(self.tmp / "s", {"SPY": [(200, 200, 100, 100), (200, 200, 100, 100),
                                                         (100, 100, 100, 100), (100, 100, 100, 100),
                                                         (100, 100, 100, 100)]})
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'share': 0.4, 'at': 'close'}]
return [{'sell': p['id'], 'at': 'close'} for p in ctx.positions if p['held_sessions'] >= 2]
""")
        with recorded() as seen:
            result = run(prog, bars)
        qty = (Decimal(400) / Decimal("200.02")).quantize(SIX, rounding=ROUND_DOWN)
        [trade] = result["trades"]
        self.assertEqual(trade["qty"], float((qty * 2).quantize(SIX)))
        self.assertEqual(trade["entry_px"], 100.01)
        self.assertEqual(trade["div"], 0.0)
        self.assertEqual(result["actions"], [{"symbol": "SPY", "day": days[2].isoformat(), "kind": "split",
                                              "factor": "2:1"}])
        position = seen[2].positions[0]
        self.assertEqual((position["qty"], position["entry"], position["mark"]), (float(qty * 2), 100.01, 100.0))
        self.assertEqual(seen[2].bars["SPY"].close.tolist(), [100.0, 100.0, 100.0], "history as of t")

    def test_open_and_close_fills_in_one_session_in_order(self):
        root = self.synthetic(symbols=("SPY", "QQQ", "IWM"))
        bars = EquityStore(root).bars(["SPY", "QQQ", "IWM"], "validation", history=2)
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'share': 0.5, 'at': 'open'}, {'buy': 'QQQ', 'share': 0.5, 'at': 'open'}]
if STATE['n'] == 2:
    out = [{'buy': 'IWM', 'share': 0.5, 'at': 'open'}]
    out += [{'sell': p['id'], 'at': 'open'} for p in ctx.positions if p['symbol'] == 'SPY']
    out += [{'sell': p['id'], 'at': 'close'} for p in ctx.positions if p['symbol'] == 'QQQ']
    out += [{'buy': 'SPY', 'share': 0.5, 'at': 'close'}]
    return out
return []
""", symbols=("SPY", "QQQ", "IWM"))
        with recorded() as seen:
            result = run(prog, bars)
        self.assertEqual(seen[2].rejects, [], "exits fund entries in each phase: nothing was refused")
        lots = {t["lid"]: t for t in result["lots"]}
        f = bars.first
        self.assertEqual(lots[3]["symbol"], "IWM")
        self.assertEqual((lots[3]["entry_at"], lots[4]["entry_at"]), ("open", "close"))
        self.assertAlmostEqual(lots[3]["entry_px"], fill_price(official(bars, "IWM", f + 1, "open"), "buy", 1e-4, 1),
                               places=6)
        self.assertAlmostEqual(lots[4]["entry_px"], fill_price(official(bars, "SPY", f + 1, "close"), "buy", 1e-4, 1),
                               places=6)
        self.assertAlmostEqual(lots[2]["exit_px"], fill_price(official(bars, "QQQ", f + 1, "close"), "sell", 1e-4, 1),
                               places=6)
        self.assertEqual(lots[1]["exit_day"], lots[3]["entry_day"])
        self.assertEqual(result["status"], "ok")


class NoLookAhead(Case):
    def test_fuzzing_every_row_after_t_changes_no_decision_at_or_before_t(self):
        root = self.synthetic(symbols=("SPY", "QQQ"))
        bars = EquityStore(root).bars(["SPY", "QQQ"], "validation", history=20)
        prog = program("""
out = [{'sell': p['id'], 'at': 'open'} for p in ctx.positions if p['held_sessions'] >= 2]
for s in ctx.symbols:
    c = ctx.bars[s].close
    if c[-1] < c[-2] and ctx.cash > 100:
        out.append({'buy': s, 'share': 0.3, 'at': 'close' if ctx.weekday % 2 else 'open'})
return out
""", symbols=("SPY", "QQQ"), history=20)
        with recorded() as seen:
            run(prog, bars)
        base = [ctx_bytes(c) for c in seen]
        rng = np.random.default_rng(5)
        for t0 in sorted(random.Random(9).sample(range(bars.first, bars.n - 2), 6)):
            raw, adj = {}, {}
            for sym in bars.symbols:
                r, a = bars.raw[sym].copy(), bars.adj[sym].copy()
                r[t0 + 1:] = rng.uniform(1, 500, r[t0 + 1:].shape)
                a[t0 + 1:] = rng.uniform(1, 500, a[t0 + 1:].shape)
                r[t0 + 1 + rng.integers(0, bars.n - t0 - 1)] = np.nan
                raw[sym], adj[sym] = r, a
            fuzzed = dataclasses.replace(bars, raw=raw, adj=adj)
            with recorded() as again:
                run(prog, fuzzed)
            decisions = t0 - (bars.first - 1) + 1     # the decisions at the closes first - 1 .. t0
            self.assertEqual([ctx_bytes(c) for c in again[:decisions]], base[:decisions], t0)


class Cash(Case):
    def test_random_programs_never_take_the_sleeve_below_zero(self):
        root = self.synthetic(symbols=("SPY", "QQQ", "IWM", "DIA"), start=D(2022, 1, 3))
        bars = EquityStore(root).bars(["SPY", "QQQ", "IWM", "DIA"], "train", history=5)
        prog = program("""
k = STATE['n']
out = []
for i, p in enumerate(ctx.positions):
    if (k + i) % 3 == 0:
        out.append({'sell': p['id'], 'at': 'open' if (k + i) % 2 else 'close'})
for j, s in enumerate(ctx.symbols):
    if (k * 7 + j * 3) % 5 < 3:
        out.append({'buy': s, 'share': ((k + j) % 10 + 1) / 10.0, 'at': 'close' if (k + j) % 2 else 'open'})
if k % 11 == 0:
    out.append({'buy': 'SPY', 'usd': 5000.0})
return out
""", symbols=("SPY", "QQQ", "IWM", "DIA"))
        with recorded() as seen:
            result = run(prog, bars)
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["summary"]["trades"], 200)
        self.assertTrue(all(c.cash >= 0 for c in seen))
        self.assertTrue(all(row[2] > 0 for row in result["daily"]))
        self.assertTrue(any("instrument" in r or "sleeve" in r or "min_order" in r for c in seen for r in c.rejects))

    def test_an_oversized_entry_is_an_engine_failure_never_a_negative_sleeve(self):
        root = synth.constant_store(self.tmp / "c", sessions=5)
        bars = EquityStore(root).bars(["SPY"], "validation", history=0)
        prog = program("return [{'buy': 'SPY', 'share': 1.0}]")

        def greedy(x):
            qty = Decimal(20)
            return sizing.Sized(qty * x.limit_price, qty, "intent", "too much")

        with mock.patch.object(sizing, "size_entry", greedy):
            with self.assertRaises(AssertionError):
                run(prog, bars)
            failed = run_isolated(prog, bars)
        self.assertEqual((failed["status"], failed["trials"]), ("error", 0))
        self.assertIn("below zero", failed["reason"])


class Holds(Case):
    def setUp(self):
        super().setUp()
        root = synth.constant_store(self.tmp / "c", sessions=12, price=50.0, step=0.5)
        self.bars = EquityStore(root).bars(["SPY"], "validation", history=0)
        self.days = [d.isoformat() for d, _ in nyse_sessions(D(2025, 1, 2), D(2025, 2, 28))]

    def test_a_lot_never_sells_in_the_session_it_was_bought(self):
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'share': 0.5, 'at': 'open'}, {'sell': 1, 'at': 'close'}]
if STATE['n'] == 2:
    return [{'sell': 1, 'at': 'open'}]
return []
""")
        with recorded() as seen:
            result = run(prog, self.bars)
        self.assertTrue(any("bought this session" in r for r in seen[1].rejects))
        [trade] = result["trades"]
        self.assertEqual((trade["entry_day"], trade["exit_day"]), (self.days[1], self.days[2]))

    def test_a_close_bought_lot_may_sell_at_the_next_open(self):
        prog = program("""
out = [{'sell': p['id'], 'at': 'open'} for p in ctx.positions]
return out + [{'buy': 'SPY', 'share': 0.5, 'at': 'close'}]
""")
        result = run(prog, self.bars)
        self.assertTrue(result["trades"])
        for trade in result["trades"]:
            self.assertEqual((trade["entry_at"], trade["exit_at"], trade["held_sessions"]), ("close", "open", 1))

    def test_max_hold_exits_at_the_open_that_completes_it(self):
        """A lot is held at most `max_hold_sessions` (the book's rule too: league/equity/live.py `_house_exits`)."""
        prog = program("return [{'buy': 'SPY', 'share': 0.5, 'at': 'open'}] if STATE['n'] == 1 else []", max_hold=3)
        with recorded() as seen:
            result = run(prog, self.bars)
        [trade] = result["trades"]
        self.assertEqual((trade["entry_day"], trade["exit_day"], trade["exit_at"]),
                         (self.days[1], self.days[4], "open"))
        self.assertEqual((trade["reason"], trade["held_sessions"]), ("max_hold", 3))
        self.assertEqual(seen[3].positions[0]["held_sessions"], 2, "held 2 at the close before its exit")
        self.assertEqual(seen[4].closed[0]["reason"], "max_hold")

    def test_two_failed_decides_in_a_row_exit_every_lot(self):
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'share': 0.5, 'at': 'open'}]
if STATE['n'] in (2, 3):
    return 1 / 0
return []
""")
        result = run(prog, self.bars)
        [trade] = result["trades"]
        self.assertEqual((trade["exit_day"], trade["exit_at"], trade["reason"]), (self.days[3], "open", "house"))
        once = program("""
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'share': 0.5, 'at': 'open'}]
if STATE['n'] in (2, 4):
    return 1 / 0
return []
""", max_hold=60)
        self.assertEqual(run(once, self.bars)["trades"], [], "failures not in a row exit nothing")

    def test_refusals_reach_the_next_ctx(self):
        prog = program("""
if STATE['n'] == 1:
    return [{'buy': 'QQQ', 'share': 0.5}, {'cancel': 4}, {'sell': 99}, {'buy': 'SPY', 'share': 0.001},
            {'buy': 'SPY', 'share': 0.7}]
return []
""")
        with recorded() as seen:
            result = run(prog, self.bars)
        rejects = seen[1].rejects
        self.assertEqual(len(rejects), 4, rejects)
        self.assertTrue(any("NEEDS" in r for r in rejects))
        self.assertTrue(any("cancel 4" in r for r in rejects))
        self.assertTrue(any("no open lot 99" in r for r in rejects))
        self.assertTrue(any("min_order" in r for r in rejects))
        self.assertEqual(seen[2].rejects, [])
        lot = result["lots"][0]
        self.assertEqual((lot["reason"], lot["exit_day"], round(lot["weight"], 4)), ("open", None, 0.5),
                         "an ETF holds at most half of E0")
        self.assertLess(seen[1].caps["SPY"], 1.0, "half of E0 is held: cents of room are left")


class Determinism(Case):
    def test_the_same_inputs_give_the_same_result_and_the_settings_name_the_run(self):
        root = self.synthetic(symbols=("SPY", "QQQ"))
        bars = EquityStore(root).bars(["SPY", "QQQ"], "validation", history=5)
        prog = program("""
c = ctx.bars['QQQ'].close
out = [{'sell': p['id'], 'at': 'open'} for p in ctx.positions]
return out + ([{'buy': 'QQQ', 'share': 0.5, 'at': 'close'}] if c[-1] < c[-2] else [])
""", symbols=("SPY", "QQQ"), history=5)
        a, b = run(prog, bars), run(prog, bars)
        self.assertEqual(a["result_sha"], b["result_sha"])
        self.assertEqual(a["run_id"], b["run_id"])
        stressed = run(prog, bars, cfg=EngineConfig(k=config.K_STRESS))
        self.assertNotEqual(stressed["run_id"], a["run_id"])
        self.assertLess(stressed["summary"]["pnl"], a["summary"]["pnl"])
        self.assertEqual(results.sha(a), results.sha(dict(a)))
        for key in ("run_id", "program", "program_sha", "run_sha", "params", "window", "symbols", "engine",
                    "data_version", "capital", "k", "trials", "status", "needs", "summary", "by_year", "trades",
                    "entry_days", "exposure", "bh", "mte", "daily", "lots", "runtime", "result_sha", "start", "end"):
            self.assertIn(key, a)
        self.assertEqual((a["window"], a["capital"], a["trials"], a["start"]), ("validation", "1000", 1, "2025-01-02"))
        self.assertEqual(sorted(a["by_year"]), ["2025"])
        self.assertIn("bh_pnl", a["by_year"]["2025"])

    def test_status_no_data_and_disqualified(self):
        root = synth.constant_store(self.tmp / "c", sessions=4)
        empty = EquityStore(root).bars(["SPY"], "validation", history=0, start=D(2025, 6, 2))
        result = run(program("return []"), empty)
        self.assertEqual((result["status"], result["summary"]["trades"], result["daily"]), ("no_data", 0, []))
        bars = EquityStore(root).bars(["SPY"], "validation", history=0)
        broken = run(program("return 1 / 0"), bars, cfg=EngineConfig(max_errors=2))
        self.assertEqual(broken["status"], "disqualified")
        self.assertIn("errors", broken["reason"])


class Views(Case):
    def setUp(self):
        super().setUp()
        root = synth.constant_store(self.tmp / "c", sessions=8, price=100.0, step=0.5)
        bars = EquityStore(root).bars(["SPY"], "validation", history=0)
        self.result = run(program("""
out = [{'sell': p['id'], 'at': 'open'} for p in ctx.positions]
return out + [{'buy': 'SPY', 'share': 0.5, 'at': 'close'}]
"""), bars)

    def test_what_leaves_each_window(self):
        r = self.result
        self.assertEqual(results.view(r, "train"), results.view(dict(r), "train"))
        validation = results.view(r, "validation")
        for hidden in ("trades", "daily", "lots", "entry_days", "start", "end", "data_version", "actions", "exposure"):
            self.assertNotIn(hidden, validation)
        self.assertEqual(list(validation["by_year"]), ["y1"])
        self.assertEqual(set(validation["by_year"]["y1"]), {"trades", "days", "days_traded"})
        self.assertNotIn("by_year", validation["bh"])
        holdout = results.view(r, "holdout")
        self.assertEqual(holdout["daily"], r["daily"])
        self.assertNotIn("trades", holdout)
        self.assertNotIn("lots", holdout)
        self.assertEqual(results.view(r, "look"), holdout)
        forward = results.view(r, "forward")
        self.assertEqual(forward["trades"][0], {"day": r["trades"][0]["exit_day"], "net": r["trades"][0]["net"],
                                                "notional": r["trades"][0]["notional"]})
        self.assertEqual(results.view(r, "gate"), {"run_id": r["run_id"], "status": "ok", "trials": 1})
        with self.assertRaises(ValueError):
            results.view(r, "secret")
        failed = results.failed("p", "boom")
        self.assertEqual((failed["status"], failed["trials"], failed["trades"], failed["lots"]), ("error", 0, [], []))

    def test_buy_and_hold_and_mte_beside(self):
        daily = [["2025-01-02", 0.0, 1000.0, 0.5], ["2025-01-03", 0.0, 1000.0, 0.5]]
        bh = results.buy_and_hold(daily, {"SPY": [100.0, 110.0, 121.0]}, Decimal(1000))
        self.assertEqual(bh, {"pnl": 100.0, "by_year": {"2025": 100.0}, "exposure": 0.5, "basket_return": 0.21})
        trades = [{"entry_day": "2025-01-02", "entry_at": "open", "exit_day": "2025-01-03", "exit_at": "close",
                   "return": 0.15}]
        days = ["2024-12-31", "2025-01-02", "2025-01-03"]
        opens = {"SPY": [99.0, 105.0, 115.0]}
        [x] = results.excess_returns(trades, {"SPY": [100.0, 110.0, 121.0]}, days, opens)
        self.assertAlmostEqual(x, 0.15 - (121.0 / 105.0 - 1.0))
        [y] = results.excess_returns(trades, {"SPY": [100.0, 110.0, 121.0]}, days)
        self.assertAlmostEqual(y, 0.15 - 0.21, msg="without opens, from the close before the open entry")
        self.assertEqual(results.mte(trades * 2, {"SPY": [100.0, 110.0, 121.0]}, days=days, opens=opens)["n"], 2)
        r = self.result
        self.assertEqual(r["mte"]["n"], r["summary"]["trades"])
        self.assertLess(r["mte"]["mean"], 0, "an overnight round trip on a flat open-to-close path pays its costs")
        self.assertEqual(r["bh"]["by_year"]["2025"], r["by_year"]["2025"]["bh_pnl"])


class RealSizing(unittest.TestCase):
    """Cross-package: the engine through money's `size_entry` (skipped until money's package lands) agrees with the
    rule the fake above implements on an ordinary program."""

    def test_the_real_sizer_agrees_with_the_rule(self):
        probe = sizing.SizingInputs(symbol="SPY", klass="etf", share=Decimal("0.5"), usd=None,
                                    limit_price=Decimal("100"), E=Decimal(1000), sleeve_equity=Decimal(1000),
                                    sleeve_free_cash=Decimal(1000), sleeve_symbol_value=Decimal(0),
                                    position_share=Decimal("0.50"), account_symbol_value=Decimal(0),
                                    invested_now=Decimal(0), invested_share=Decimal("1.00"),
                                    available_cash=Decimal(1000), cash=Decimal(1000), any_short=False,
                                    budget_room=None, weight=Decimal("0.20"), min_order_usd=Decimal(10))
        try:
            sizing.size_entry(probe)
        except NotImplementedError:
            self.skipTest("money's size_entry is not implemented on this branch yet")
        with tempfile.TemporaryDirectory() as tmp:
            root = synth.synthetic_store(Path(tmp) / "s", symbols=("SPY", "QQQ"), start=D(2024, 10, 1),
                                         end=D(2025, 12, 31))
            bars = EquityStore(root).bars(["SPY", "QQQ"], "validation", history=2)
            prog = program("""
out = [{'sell': p['id'], 'at': 'open'} for p in ctx.positions if p['held_sessions'] >= 2]
return out + [{'buy': s, 'share': 0.3, 'at': 'close'} for s in ctx.symbols]
""", symbols=("SPY", "QQQ"))
            real = run(prog, bars)
            with gym_sizing():
                fake = run(prog, bars)
        self.assertEqual(real["trades"], fake["trades"])


if __name__ == "__main__":
    unittest.main()
