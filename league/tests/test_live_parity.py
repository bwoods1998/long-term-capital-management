"""The Gym and the live path can never disagree: on the same live arrays, a program run through the live path's split
(`ShadowAccount.job` -> the decider -> `ShadowAccount.apply`) sees the same ctx, sends the same intents and fills the
same trades as the Gym's own `engine.Account.step`. And the live chain's contract identities are the store's."""

import datetime as dt
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import runtime as R
    from league.live.chains import LiveDay, contract_key, trading_days_around
    from league.live.decider import InlineDecider
    from league.live.shadow import ShadowAccount, needs_of
    from league.tests.live_fakes import MONDAY, Clock, Market, at
    from league.gym import legs as L
    from league.gym import venue as V
    from league.gym.ctx import Snapshot
    from league.live.real import RLeg, RPosition
    from league.live.step import OptionsLive

PROGRAM = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.02, "cadence": 2, "history": 3, "start": 571, "end": 958}
PARAMS = {"hold": 4}
STATE = {"n": 0}

def decide(ctx):
    c = ctx.chain
    STATE["n"] += 1
    seen = [ctx.minute, c.n, round(float(c.strike[0]), 2), round(float(ctx.under.price), 4), round(ctx.cash, 4),
            len(ctx.positions), len(ctx.orders), round(float(c.delta[min(3, c.n - 1)]), 9), len(ctx.under.closes),
            round(float(np.nansum(c.iv)), 6), ctx.weekday, ctx.events["fomc"], STATE["n"]]
    out = []
    for p in ctx.positions:
        if p["held_minutes"] >= ctx.params["hold"]:
            out.append({"close": p["id"], "limit": "natural", "note": str(seen)})
    if not ctx.positions and not ctx.orders:
        out.append({"open": "debit_vertical", "root": "SPY", "qty": 3, "limit": "natural", "note": str(seen),
                    "legs": [{"side": "long", "right": "C", "dte": 1, "delta": 0.4},
                             {"side": "short", "right": "C", "rel": 0, "offset": 2.0}]})
    return out
'''.replace("import", "")
PROGRAM = "import numpy as np\n" + PROGRAM


@unittest.skipUnless(HAVE, "numpy not installed")
class GymAndLiveAgree(unittest.TestCase):
    def test_the_same_intents_and_the_same_trades(self):
        clock = Clock(at(MONDAY, 9, 30))
        market = Market(clock)
        day = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY))
        day.history["SPY"] = [(590.0, 595.0, 588.0, 592.0), (591.0, 596.0, 589.0, 593.0), (592.0, 597.0, 590.0, 594.0)]
        program = R.load_program(PROGRAM, name="probe")

        gym = E.Account(program, E.RunConfig(window="forward", roots=("SPY",), capital=10000.0), ("SPY",))
        seen_gym = []
        runner = gym.runner
        original = runner.decide
        runner.decide = lambda ctx: seen_gym.append(original(ctx)) or seen_gym[-1]
        decider = InlineDecider()
        info = decider.load("k", PROGRAM, {}, "probe")
        live = ShadowAccount(instance="k", family="probe", needs=needs_of(info["needs"]), params=program.params, capital=10000.0)
        seen_live = []
        began = False
        for mi in range(0, 60):
            clock.set(at(MONDAY, 9, 30) + 60 * mi)
            market.spot = 600.0 + 0.35 * np.sin(mi / 5.0) + 0.02 * mi
            chain = day.chain("SPY")
            day.advance(mi)
            changed = chain.record(mi, market.chain("SPY", expiry_from="2026-09-28", expiry_to="2026-10-02",
                                                    strike_from=market.spot * 0.97, strike_to=market.spot * 1.03),
                                   open_epoch=at(MONDAY, 9, 30, 0))
            chain.set_price(mi, market.spot)
            if changed:
                day.remap([gym, live])
            if not began:
                gym.begin_day(day)
                live.begin_day(day)
                began = True
            if mi == 0:
                continue
            wants = mi in gym.decision_minutes(day)
            gym.step(day, mi, wants)
            live.pre(day, mi)
            if wants:
                job = live.job(day, mi)
                job["key"], job["mi"] = "k", mi
                snaps = {("SPY", mi): day.snapshot("SPY", mi)}
                unders = {("SPY", 3, mi): day.under("SPY", mi, 3)}
                answer = decider.decide(snaps, unders, [job])["k"]
                seen_live.append(answer["intents"])
                live.apply(day, mi, answer["intents"])
        self.assertGreater(len(seen_gym), 20)
        self.assertEqual(seen_live, seen_gym)
        self.assertEqual(live.trades, gym.trades)
        self.assertGreaterEqual(len(gym.trades), 2)
        self.assertAlmostEqual(live.cash, gym.cash, places=9)
        self.assertEqual(live.counts, gym.counts)
        # The day's end on a live day, for both kinds of account (the review of #398: the Gym's Train-only drift record read
        # `day.history.arrays`, which a LiveDay's dict has not, and the shadow book raised at every close).
        gym.end_day(day, last=False)
        live.end_day(day, last=False)
        self.assertEqual(live.daily, gym.daily)
        self.assertEqual(len(live.daily), 1)
        self.assertEqual((gym.exposure, live.exposure), ({}, {}), "a forward (live) account records no drift hours")


@unittest.skipUnless(HAVE, "numpy not installed")
class ContractIdentity(unittest.TestCase):
    def test_the_live_key_is_the_stores(self):
        from league.gym.day import contract_key as store_key
        exp = np.array([20724, 20725, 20730])
        strike = np.array([600.0, 7650.0, 2.5])
        call = np.array([True, False, True])
        self.assertTrue((contract_key(exp, strike, call) == store_key(exp, strike, call)).all())

    def test_the_chain_is_the_stores_order_and_grows_without_losing_rows(self):
        clock = Clock(at(MONDAY, 10, 0))
        market = Market(clock, width=3)
        day = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY))
        chain = day.chain("SPY")
        rows = market.chain("SPY", expiry_from="2026-09-28", expiry_to="2026-09-29")
        chain.record(30, rows, open_epoch=at(MONDAY, 9, 30, 0))
        self.assertTrue((np.diff(chain.key) > 0).all())
        before = dict(zip(chain.symbol, chain.bid[30]))
        market.spot = market.center = 605.0                                   # new strikes listed around the new spot
        more = market.chain("SPY", expiry_from="2026-09-28", expiry_to="2026-09-29")
        self.assertTrue(chain.record(31, more, open_epoch=at(MONDAY, 9, 30, 0)))
        self.assertTrue((np.diff(chain.key) > 0).all())
        after = dict(zip(chain.symbol, chain.bid[30]))
        for sym, bid in before.items():
            self.assertTrue(bid == after[sym] or (np.isnan(bid) and np.isnan(after[sym])))

    def test_a_quote_from_before_the_open_is_not_in_force(self):
        clock = Clock(at(MONDAY, 9, 30, 1))
        market = Market(clock, width=1)
        day = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY))
        chain = day.chain("SPY")
        rows = market.chain("SPY", expiry_from="2026-09-28", expiry_to="2026-09-28")   # stamped a second before 09:30:01
        chain.record(0, rows, open_epoch=at(MONDAY, 9, 30, 1))
        self.assertTrue(np.isnan(chain.bid[0]).all())

    def test_the_index_level_is_put_call_parity(self):
        clock = Clock(at(MONDAY, 11, 0))
        market = Market(clock, width=10)
        day = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY))
        chain = day.chain("XSP")
        chain.record(90, market.chain("XSP", expiry_from="2026-09-28", expiry_to="2026-09-29"), open_epoch=at(MONDAY, 9, 30, 0))
        level = chain.parity(90, float("nan"))
        self.assertAlmostEqual(level, market.level("XSP"), delta=0.05)


@unittest.skipUnless(HAVE, "numpy not installed")
class QuoteRevision(unittest.TestCase):
    def test_normal_quote_writes_are_odd_even_when_geometry_does_not_change(self):
        clock = Clock(at(MONDAY, 10, 0))
        market = Market(clock, width=1)
        chain = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY)).chain("SPY")
        rows = market.chain("SPY", expiry_from="2026-09-28", expiry_to="2026-09-28")
        rows = {next(iter(rows)): next(iter(rows.values()))}
        self.assertEqual(chain.quote_revision, 0)
        self.assertTrue(chain.record(30, rows, open_epoch=at(MONDAY, 9, 30, 0)))
        self.assertEqual(chain.quote_revision, 2)
        generation = chain.generation
        seen = []

        class WatchedQuotes(np.ndarray):
            def __setitem__(self, key, value):
                seen.append(("quote_write", chain.quote_revision))
                super().__setitem__(key, value)

        chain.bid, chain.ask = chain.bid.view(WatchedQuotes), chain.ask.view(WatchedQuotes)
        admit = chain._admit
        def observe_admit(symbols):
            seen.append(("admit", chain.quote_revision))
            return admit(symbols)
        with patch.object(chain, "_admit", side_effect=observe_admit):
            self.assertFalse(chain.record(31, rows, open_epoch=at(MONDAY, 9, 30, 0)))
        self.assertEqual(seen, [("admit", 3), ("quote_write", 3), ("quote_write", 3)])
        self.assertEqual(chain.quote_revision, 4)
        self.assertEqual(chain.generation, generation)

    def test_invalid_minutes_and_admission_errors_always_finish_on_an_even_revision(self):
        chain = LiveDay(MONDAY, 570, 960, trading_days=trading_days_around(MONDAY)).chain("SPY")
        self.assertFalse(chain.record(-1, {}, open_epoch=0))
        self.assertEqual(chain.quote_revision, 2)
        def broken_admit(symbols):
            self.assertEqual(chain.quote_revision, 3)
            raise ValueError("unreadable contract admission")
        with patch.object(chain, "_admit", side_effect=broken_admit), self.assertRaisesRegex(ValueError, "admission"):
            chain.record(0, {}, open_epoch=0)
        self.assertEqual(chain.quote_revision, 4)
        self.assertFalse(chain.record(0, {}, open_epoch=0))
        self.assertEqual(chain.quote_revision, 6)


@unittest.skipUnless(HAVE, "numpy not installed")
class LiveCloseFloor(unittest.TestCase):
    """The Gym's close floor is the live path's. The engine fills a close whose natural is below the package's least at
    that least (`engine.Account._in_bounds`): honest only because a real close is never sent below it. The live close
    limit is floored in `league/live/step.py` `OptionsLive._send_close` ("A close's limit stays one the gateway takes":
    0 for a debit structure, -(collateral - 0.01) for a credit one, a tick for a long call or put). That file is a money
    file: this test runs its code, never edits it. For each structure type with a bounded range, a close is sent into a
    blown-out quote (every leg bid 0.00 and asked 99.00: a natural far below the least), as the House's forced close and
    as a program's close at the natural; the limit sent is at or above `legs.value_bounds`'s least."""

    DAY, EXPIRY = dt.date(2026, 9, 28), "2026-09-29"
    #: (type, [(side, ratio, is_call, strike)]): every bounded type the Gym admits (calendars and diagonals have no bound).
    STRUCTURES = [
        ("long_call", [(1, 1, True, 600.0)]),
        ("long_put", [(1, 1, False, 600.0)]),
        ("debit_vertical", [(1, 1, True, 600.0), (-1, 1, True, 605.0)]),
        ("debit_vertical", [(1, 1, False, 605.0), (-1, 1, False, 600.0)]),
        ("credit_vertical", [(-1, 1, False, 600.0), (1, 1, False, 595.0)]),
        ("credit_vertical", [(-1, 1, True, 600.0), (1, 1, True, 605.0)]),
        ("iron_condor", [(1, 1, False, 590.0), (-1, 1, False, 595.0), (-1, 1, True, 605.0), (1, 1, True, 612.0)]),
        ("iron_butterfly", [(1, 1, False, 595.0), (-1, 1, False, 600.0), (-1, 1, True, 600.0), (1, 1, True, 605.0)]),
        ("long_butterfly", [(1, 1, True, 595.0), (-1, 2, True, 600.0), (1, 1, True, 605.0)]),
        ("long_straddle", [(1, 1, True, 600.0), (1, 1, False, 600.0)]),
        ("long_strangle", [(1, 1, False, 595.0), (1, 1, True, 605.0)]),
    ]

    def send_close(self, type_, shape, *, forced):
        rules = V.rules_for("SPY", open_minute=570, close_minute=960)
        n = len(shape)
        snap = Snapshot("SPY", 600, 600.0, dte=[1] * n, strike=[k for _, _, _, k in shape], is_call=[c for _, _, c, _ in shape],
                        bid=[0.0] * n, ask=[99.0] * n, keys=list(range(n)))
        legs = [L.LegFill(i, i, side, ratio, 1, k, call) for i, (side, ratio, call, k) in enumerate(shape)]
        collateral, _ = L.classify(type_, "SPY", legs, rules)
        pos = RPosition(pid=1, instance="k", family="probe", type=type_, root="SPY",
                        legs=[RLeg(f"SPY-{i}", side, ratio, call, k, self.EXPIRY, i) for i, (side, ratio, call, k) in enumerate(shape)],
                        qty=1, opened_qty=1, entry=1.0, max_loss_share=1.0, collateral=collateral)
        sent = []

        class Book:
            def path_refusal(self, *args, **kwargs):
                return None

            def new_order(self, **kwargs):
                sent.append(kwargs)
                return SimpleNamespace(oid=1, dispatched=True, status="working", answer={})

            def send(self, order):
                pass

            def _save_position(self, pos):
                pass

        live = SimpleNamespace(book=Book(), pending_exits={}, clock=lambda: 0.0, _yield_contracts=lambda *a, **k: False,
                               _save_pending=lambda: None, _killed=lambda: False, _instance_spent=lambda *a, **k: None)
        day = SimpleNamespace(rules={"SPY": rules}, chains={"SPY": SimpleNamespace(index_of=lambda keys: keys)},
                              snapshot=lambda root, mi: snap, day=self.DAY, open_min=570)
        refused = OptionsLive._send_close(live, pos, day, 30, forced=forced, why="probe", out={})
        self.assertIsNone(refused, f"{type_}: {refused}")
        [order] = sent
        natural, _ = L.natural_value(snap, legs, "close")
        return order["limit_value"], natural, L.value_bounds(legs, [self.EXPIRY] * n)

    def test_the_live_close_floor_is_at_or_above_the_gyms_least(self):
        for type_, shape in self.STRUCTURES:
            for forced in (False, True):
                with self.subTest(type=type_, legs=shape, forced=forced):
                    limit, natural, (lo, hi) = self.send_close(type_, shape, forced=forced)
                    self.assertTrue(math.isfinite(lo), "a bounded type")
                    if any(side < 0 for side, _, _, _ in shape):
                        self.assertLess(natural, lo, "the quote is below the least: the floor is what is tested")
                    else:
                        # All long legs: bids are never negative, so the natural is never below the least (0); a forced
                        # close's concession (0.01 a try under the natural) is what the floor holds here.
                        self.assertEqual((natural, lo), (0.0, 0.0))
                    self.assertGreaterEqual(limit, lo - 1e-9)
                    self.assertLessEqual(limit, hi + 1e-9)

    def test_calendars_and_diagonals_have_no_bound(self):
        legs = [L.LegFill(0, 0, -1, 1, 0, 600.0, True), L.LegFill(1, 1, 1, 1, 0, 600.0, True)]
        self.assertEqual(L.value_bounds(legs, ["2026-09-29", "2026-10-02"]), (-math.inf, math.inf))


if __name__ == "__main__":
    unittest.main()
