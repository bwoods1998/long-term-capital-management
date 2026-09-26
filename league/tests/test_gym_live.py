"""The live path's use of the Gym's core, with no store: a chain read as plain arrays becomes a
Snapshot and a ctx, the program decides, and the intent resolves into legs, a limit and a maximum
loss exactly as the replay resolves it (numpy only; the House imports no pyarrow)."""

import math
import unittest
from pathlib import Path

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import ctx as C
    from league.gym import events as EV
    from league.gym import greeks as G
    from league.gym import legs as L
    from league.gym import runtime as R
    from league.gym import venue

EXAMPLES = Path(__file__).resolve().parents[1] / "gym" / "examples"


@unittest.skipUnless(HAVE, "numpy not installed (requirements-gym.txt)")
class LivePath(unittest.TestCase):
    def chain(self, minute=700):
        spot = 450.0
        strikes = np.arange(440.0, 461.0)
        dte = np.zeros(strikes.size * 2, dtype=int)
        k = np.repeat(strikes, 2)
        call = np.tile([True, False], strikes.size)
        years = G.years_to_expiry(dte, minute)
        mid = G.bs_price(spot, k, years, 0.04, 0.25, call)
        bid = np.maximum(np.round(mid - 0.02, 2), 0.0)
        ask = np.round(mid + 0.02, 2) + 0.01
        return C.Snapshot("SPY", minute, spot, dte, k, call, bid, ask, np.full(k.size, 50), np.full(k.size, 50), rate=0.04)

    def ctx_for(self, snap, program):
        needs = program.needs
        chain = snap.view(snap.slice_index(needs.dte_min, needs.dte_max, needs.band))
        closes = [440.0, 442.0, 441.0, 444.0, 445.0, 443.0]
        under = C.underlying_view("SPY", np.full(snap.minute - 570 + 1, 450.0), closes=closes, opens=closes, highs=closes, lows=closes)
        today, tomorrow = EV.flags_for(__import__("datetime").date(2026, 9, 28), [__import__("datetime").date(2026, 9, 28)])
        return C.build_ctx(minute=snap.minute, open_minute=570, close_minute=960, weekday=0, chains={"SPY": chain},
                           underlyings={"SPY": under}, positions=[], orders=[], cash=5000.0, equity=5000.0, budget=5000.0,
                           buying_power=5000.0, params=program.params, rules={"SPY": venue.rules_for("SPY").as_dict()},
                           events=today, events_next=tomorrow)

    def test_a_program_decides_on_a_live_chain_and_the_intent_resolves(self):
        program = R.load_program((EXAMPLES / "condor_vrp.py").read_text(), name="condor", params={"vrp_min": 0.1, "dte_min": 0})
        snap = self.chain()
        runner = program.start()
        intents = runner.decide(self.ctx_for(snap, program))
        self.assertEqual(runner.errors, 0, runner.messages)
        [intent] = [i for i in intents if "open" in i]
        order = L.resolve_open(intent, snap, venue.rules_for("SPY"), buying_power=5000.0)
        self.assertEqual(order.type, "iron_condor")
        self.assertEqual([leg.side for leg in order.legs], [1, -1, -1, 1])
        strikes = [leg.strike for leg in order.legs]
        self.assertEqual(strikes[0], strikes[1] - 1.0)
        self.assertEqual(strikes[3], strikes[2] + 1.0)
        self.assertLess(order.limit, 0)                                  # a credit
        self.assertAlmostEqual(order.max_loss_share, 1.0 + order.limit)  # the wing less the credit
        self.assertLessEqual(order.max_loss + 2 * order.fees, 150.0)     # max_loss 150 sized it
        # The natural value is the four touches, as the House would price the multi-leg order.
        by_idx = {leg.idx: leg for leg in order.legs}
        natural = sum(leg.side * (snap.ask[i] if leg.side > 0 else snap.bid[i]) for i, leg in by_idx.items())
        self.assertAlmostEqual(order.natural, natural, places=9)
        self.assertEqual(order.limit, order.natural)
        close = L.resolve_close({"close": 1, "limit": {"mid": 1}}, order.type, order.legs, order.qty, snap,
                                venue.rules_for("SPY"), position=1)
        self.assertGreaterEqual(close.limit, close.natural)
        self.assertLessEqual(close.limit, close.mid)

    def test_refusals_speak_a_programs_language(self):
        snap = self.chain()
        rules = venue.rules_for("SPY")
        cases = [
            ({"open": "naked_call", "legs": [], "qty": 1}, "'open' is one of"),
            ({"open": "credit_vertical", "legs": [{"side": "short", "right": "C", "dte": 0, "strike": 450},
                                                  {"side": "long", "right": "C", "dte": 0, "strike": 449}], "qty": 1}, "credit_vertical"),
            ({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 450}], "qty": 1000}, "'qty'"),
            ({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 450}], "max_loss": 1}, "buys none"),
            ({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 9, "strike": 450}], "qty": 1}, "no quoted expiry"),
            ({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 450}], "qty": 400}, "buying power"),
        ]
        for intent, fragment in cases:
            with self.assertRaises(L.Refused) as caught:
                L.resolve_open(intent, snap, rules, buying_power=5000.0)
            self.assertIn(fragment, str(caught.exception))
        with self.assertRaises(L.Refused):
            L.resolve_open({"open": "calendar", "legs": [], "qty": 1}, snap, venue.rules_for("XSP"), buying_power=1e6)

    def test_limit_rules_and_ticks(self):
        self.assertEqual(L.limit_value("natural", "open", 0.73, 0.60, 0.01), 0.73)
        self.assertEqual(L.limit_value("mid", "open", 0.73, 0.605, 0.01), 0.60)      # passive: down on an open
        self.assertEqual(L.limit_value("mid", "close", 0.47, 0.605, 0.01), 0.61)     # passive: up on a close
        self.assertEqual(L.limit_value({"mid": 2}, "open", 0.73, 0.60, 0.01), 0.62)
        self.assertEqual(L.limit_value({"mid": 50}, "open", 0.73, 0.60, 0.01), 0.73)  # never past the natural
        self.assertEqual(L.limit_value({"price": -0.40}, "open", -0.35, -0.45, 0.01), -0.40)
        self.assertEqual(venue.leg_tick("SPY", 5.0), 0.01)
        self.assertEqual(venue.leg_tick("SPXW", 2.0), 0.05)
        self.assertEqual(venue.leg_tick("SPXW", 3.5), 0.10)
        self.assertEqual(venue.leg_tick("AAPL", 3.5), 0.05)
        self.assertTrue(math.isnan(C.parity_spot([0], [450.0], [True], [1.0], float("nan"))))


if __name__ == "__main__":
    unittest.main()
