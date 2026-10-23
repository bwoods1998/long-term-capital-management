"""THE OWNER'S GOAL V3's money rows (release 1019l, the captain's A138), on the table in force.

"I accept losing my entire Alpaca balance. Use it. ... every seatable program trades real money from its first event at
up to 5% of equity a position ... a bug stop that pauses new entries after a 25% loss in one session". Release 1019l
moved five rows and three bounds and the Done reader's total, nothing else: a learning position 0.02 -> 0.05 of E and
a Probe one 0.035 -> 0.05 (a learning position is never larger than a Probe one), the shared loss budget $400 a window
and $800 in total -> $1,900 each, the daily stop 0.35 -> 0.25. The name's wall stays 0.10 here and at the gateway.
The earlier releases' tests of the same mechanisms run on release 1019i's table (league/tests/v2_walls.py)."""
from __future__ import annotations

import datetime as dt
import json
import unittest
from decimal import Decimal as D

from league import constitution as K
from league.events import book as EB
from league.events import done as DN
from league.live import money as M
from league.swarm.evaluator import equity_fingerprint, execution_fingerprint
from league.tests import equity_design as X
from league.tests import test_events_book as TB
from league.tests.evl6_fakes import on_1019h

NOW = dt.datetime(2026, 10, 23, 12, 0, tzinfo=dt.timezone.utc)


class TheRows(unittest.TestCase):
    def test_the_five_rows_and_three_bounds_in_force(self):
        ev = K.CONSTITUTION["equity_money"]["event"]
        self.assertEqual(ev["position_share"], {"learning": "0.05", "probe": "0.05", "sized": "0.10"})
        self.assertEqual((ev["one_share_max"]["learning"], ev["per_name_share"]), ("0.05", "0.10"))
        om = K.CONSTITUTION["options_money"]
        self.assertEqual((om["probe"]["loss_budget_usd"], om["probe"]["loss_total_usd"], om["daily_stop_share"],
                          om["drawdown_stop_share"]), ("1900", "1900", "0.25", "0.60"))
        self.assertEqual(K.EQUITY_MONEY_BOUNDS["event.position_share.learning"], ("0", "0.05"))
        self.assertEqual(K.EQUITY_MONEY_BOUNDS["event.per_name_share"], ("0", "0.10"), "the name's wall is unchanged")
        self.assertEqual((K.OPTIONS_MONEY_BOUNDS["probe.loss_budget_usd"], K.OPTIONS_MONEY_BOUNDS["probe.loss_total_usd"]),
                         (("0", "1900"), ("0", "1900")))
        self.assertEqual((K.equity_money_problems(), K.options_money_problems()), ([], []))
        self.assertEqual(DN.LOSS_TOTAL_USD, 1900.0)

    def test_the_digests_moved_once_with_the_rows_and_nothing_else(self):
        self.assertEqual((K.money_digest()[:8], K.digest()[:8]), ("1687e4e3", "3feab26d"))
        self.assertEqual(K.digest(), K.PINNED_DIGEST)
        self.assertEqual((K.money_digest(), K.digest()), X.DIGESTS[X.in_force()])
        before = X.before_1019l()
        self.assertEqual((K.money_digest(before)[:8], K.digest(before)[:8]), ("d52a5af5", "9c8b2221"), "release 1019i's")
        self.assertEqual((execution_fingerprint()[:8], equity_fingerprint()[:8]), ("b60410ad", "78022ca6"),
                         "the options execution fingerprint and the equity identity do not move")

        def flat(c, prefix=""):
            out = {}
            for k, v in c.items():
                out.update(flat(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}": v})
            return out
        moved = {k for k, v in flat(K.CONSTITUTION).items() if flat(before).get(k, "absent") != v}
        self.assertEqual(moved, {"equity_money.event.position_share.learning", "equity_money.event.position_share.probe",
                                 "options_money.probe.loss_budget_usd", "options_money.probe.loss_total_usd",
                                 "options_money.daily_stop_share"})
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((K.money_digest(at), K.digest(at)), X.DIGESTS[candidate])
            self.assertEqual((K.money_digest(X.before_1019l(at)), K.digest(X.before_1019l(at))), X.DIGESTS_1019I[candidate])

    def test_the_book_and_the_options_table_read_them(self):
        s = EB.settings()
        self.assertEqual((s.share("learning"), s.share("probe"), s.share("sized")), (D("0.05"), D("0.05"), D("0.10")))
        t = M.Table.from_constitution()
        self.assertEqual((t.probe_loss_budget, t.probe_loss_total, t.daily_stop_share), (D("1900"), D("1900"), D("0.25")))


class TheDoneStop(unittest.TestCase):
    def test_the_stop_is_the_balance_not_800(self):
        self.assertFalse(DN._stop({"realized_total_usd": "800", "at_risk_usd": "0", "total_budget_usd": "1900"}, NOW)["spent"])
        spent = DN._stop({"realized_total_usd": "1800", "at_risk_usd": "100", "total_budget_usd": "1900"}, NOW)
        self.assertTrue(spent["spent"])
        self.assertIn("the $1900 loss budget is spent", spent["why"])
        self.assertTrue(DN._stop({"realized_total_usd": "1900", "at_risk_usd": "0", "total_budget_usd": "5000"}, NOW)["spent"],
                        "never above V3's total, whatever the table says")


@on_1019h
class TheLearningBuy(TB.EventTest):
    def test_a_learning_buy_takes_five_percent_of_e_in_whole_shares(self):
        """The same day as league/tests/test_events_book.py `TheDay` (E $2,000, limit $20.00), at V3's 5%: 5 shares
        ($100.00), where V2's 2% took 2."""
        h = self.harness()
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME")
        h.lane.intent(TB.V2("EVL-ERN-READ-O1"), "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        self.ready(h)
        h.symbol("ACME", last=17.0, sd=0.02)
        h.tick(9, 15)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["status"], buy["band"]), ("planned", "learning"))
        h.tick(9, 16)
        [body] = h.bodies()
        self.assertEqual((body["symbol"], body["qty"], body["limit_price"]), ("ACME", "5", "20.00"), "5% of $2,000 at $20")


from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
