"""The Gym and the live path can never disagree: on the same live arrays, a program run through the live path's split
(`ShadowAccount.job` -> the decider -> `ShadowAccount.apply`) sees the same ctx, sends the same intents and fills the
same trades as the Gym's own `engine.Account.step`. And the live chain's contract identities are the store's."""

import datetime as dt
import unittest
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


if __name__ == "__main__":
    unittest.main()
