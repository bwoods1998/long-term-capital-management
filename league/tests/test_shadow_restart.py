"""Restart equivalence for working shadow orders, using invented quotes and the real fill engine."""

import copy
import datetime as dt
import json
import unittest

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym.runtime import load_program
    from league.live.chains import LiveDay
    from league.live.shadow import ShadowAccount
    from league.tests.live_fakes import MONDAY, at, iso


@unittest.skipUnless(HAVE, "numpy not installed")
class WorkingRestart(unittest.TestCase):
    SYMBOL = "SPY260929C00600000"
    CODE = "NEEDS = {'roots': ['SPY'], 'dte': [1, 1], 'cadence': 1}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"

    def setUp(self):
        self.day = LiveDay(MONDAY, 570, 960, trading_days=[MONDAY, MONDAY + dt.timedelta(days=1)])
        self.account = ShadowAccount(instance="synthetic", family="synthetic", needs=load_program(self.CODE).needs,
                                     params={}, capital=10000)
        self.quote(0, 1.8, 2.0)

    def quote(self, mi, bid, ask, size=10):
        stamp = iso(at(MONDAY, 9, 30, 0) + mi * 60)
        row = {"latestQuote": {"bp": bid, "ap": ask, "bs": size, "as": size, "t": stamp}}
        self.day.chain("SPY").record(mi, {self.SYMBOL: row}, open_epoch=at(MONDAY, 9, 30, 0))
        self.day.chain("SPY").set_price(mi, 600)
        self.day.advance(mi)

    def open(self, *, limit=1.9, qty=1):
        self.account.apply(self.day, 0, [{"open": "long_call", "root": "SPY", "qty": qty, "limit": {"price": limit},
                                         "legs": [{"side": "long", "right": "C", "dte": 1, "strike": 600.0}]}])
        self.assertEqual(len(self.account.orders), 1, self.account.rejects_since)

    def restart(self, account=None):
        state = json.loads(json.dumps((account or self.account).to_state()))
        return ShadowAccount.from_state(state)

    def assert_equal_execution(self, restored):
        self.assertEqual(restored.cash, self.account.cash)
        self.assertEqual(restored.counts, self.account.counts)
        self.assertEqual(restored.fill_rows, self.account.fill_rows)
        self.assertEqual(restored.to_state(), self.account.to_state())

    def test_seen_resting_order_keeps_its_limit_when_the_market_later_crosses(self):
        self.open()
        self.quote(1, 1.8, 2.0)
        self.account.pre(self.day, 1)
        original = next(iter(self.account.orders.values()))
        self.assertEqual((original.seen, original.aggressive), (True, False))
        restored = self.restart()
        self.assertTrue(next(iter(restored.orders.values())).fill_flags_known)
        self.quote(2, 1.6, 1.8)
        self.account.pre(self.day, 2)
        restored.pre(self.day, 2)
        self.assertEqual(next(iter(restored.positions.values())).entry, 1.9)
        self.assert_equal_execution(restored)

    def test_taking_partial_remainder_still_takes_after_an_unmarketable_minute_and_restart(self):
        self.open(limit=2.0, qty=3)
        self.quote(1, 1.8, 2.0, size=1)
        self.account.pre(self.day, 1)
        work = next(iter(self.account.orders.values()))
        self.assertEqual((work.seen, work.aggressive, work.filled, work.remaining), (True, True, 1, 2))
        restored = self.restart()
        self.quote(2, 2.1, 2.3)
        self.account.pre(self.day, 2)
        restored.pre(self.day, 2)
        self.assertEqual(next(iter(restored.orders.values())).remaining, 2)
        self.quote(3, 1.6, 1.8)
        self.account.pre(self.day, 3)
        restored.pre(self.day, 3)
        self.assertAlmostEqual(next(iter(restored.positions.values())).entry, (2.0 + 2 * 1.8) / 3)
        self.assert_equal_execution(restored)

    def test_resting_partial_remainder_keeps_its_limit_after_restart(self):
        self.open(qty=3)
        self.quote(1, 1.8, 2.0)
        self.account.pre(self.day, 1)
        self.quote(2, 1.6, 1.8, size=1)
        self.account.pre(self.day, 2)
        work = next(iter(self.account.orders.values()))
        self.assertEqual((work.seen, work.aggressive, work.filled, work.remaining), (True, False, 1, 2))
        restored = self.restart()
        self.quote(3, 1.5, 1.7)
        self.account.pre(self.day, 3)
        restored.pre(self.day, 3)
        self.assertAlmostEqual(next(iter(restored.positions.values())).entry, 1.9)
        self.assert_equal_execution(restored)

    def test_new_unseen_order_is_known_and_takes_its_first_marketable_quote(self):
        self.open(limit=2.0)
        restored = self.restart()
        work = next(iter(restored.orders.values()))
        self.assertEqual((work.seen, work.aggressive, work.fill_flags_known), (False, False, True))
        self.quote(1, 1.6, 1.8)
        self.account.pre(self.day, 1)
        restored.pre(self.day, 1)
        self.assertEqual(next(iter(restored.positions.values())).entry, 1.8)
        self.assert_equal_execution(restored)

    def test_legacy_or_malformed_pairs_keep_the_old_fallback_and_persist_unknown_history(self):
        self.open(qty=3)
        self.quote(1, 1.8, 2.0)
        self.account.pre(self.day, 1)
        self.quote(2, 1.6, 1.8, size=1)
        self.account.pre(self.day, 2)
        original = self.account.to_state()
        for fields in ({}, {"seen": True}, {"aggressive": True}, {"seen": True, "aggressive": "false"},
                       {"seen": 1, "aggressive": False}, {"seen": False, "aggressive": True},
                       {"seen": None, "aggressive": False}):
            with self.subTest(fields=fields):
                state = copy.deepcopy(original)
                row = state["orders"][0]
                for key in ("seen", "aggressive", "fill_flags_known"):
                    row.pop(key)
                row.update(fields)
                restored = ShadowAccount.from_state(state)
                work = next(iter(restored.orders.values()))
                self.assertEqual((work.seen, work.aggressive, work.filled, work.fill_flags_known), (False, False, 1, False))
                again = self.restart(restored)
                repeated = next(iter(again.orders.values()))
                self.assertEqual((repeated.seen, repeated.aggressive, repeated.fill_flags_known), (False, False, False))
        self.quote(3, 1.5, 1.7)
        again.pre(self.day, 3)
        self.assertAlmostEqual(next(iter(again.positions.values())).entry, (1.9 + 2 * 1.7) / 3,
                               msg="legacy fallback behavior stays unchanged; lost history is not inferred")

    def test_unknown_marker_never_coerces_truthy_strings_or_changes_valid_flags(self):
        self.open()
        self.quote(1, 1.8, 2.0)
        self.account.pre(self.day, 1)
        for marker in (False, "false", 1, None):
            with self.subTest(marker=marker):
                state = self.account.to_state()
                state["orders"][0]["fill_flags_known"] = marker
                restored = self.restart(ShadowAccount.from_state(state))
                work = next(iter(restored.orders.values()))
                self.assertEqual((work.seen, work.aggressive, work.fill_flags_known), (True, False, False))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
