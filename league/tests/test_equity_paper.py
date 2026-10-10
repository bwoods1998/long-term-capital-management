"""The stock paper proof (league/live/paper.py `StockPaperProof`, release E1, A8.7): a fractional SPY bought with a
marketable limit in the 15:55 close window on the practice account, held overnight, sold at the next open, and passed
only once its fills, the position, the account's FILL activities and the reconciliation all witness the round trip.
The practice account is `live_fakes.Venue` taught to fill stock limit orders (invented prices, the venue's shapes)."""

import datetime as dt
import tempfile
import unittest
import uuid
from decimal import Decimal as D
from pathlib import Path

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.live.paper import STOCK_KEY, StockPaperProof
    from league.live.state import LiveState
    from league.tests.live_fakes import MONDAY, Clock, Market, Venue, at, iso

TUESDAY = MONDAY + dt.timedelta(days=1)
WEDNESDAY = MONDAY + dt.timedelta(days=2)


if HAVE:
    class PaperStocks(Venue):
        """The practice account with stock limit orders: a buy fills at the ask when its limit reaches it, a sale at
        the bid; `stock_fill` "natural", "none" (it rests) or "half" (half of what is left, once a reading). Each fill
        is a FILL activity naming its order, unless `activity_lag`."""

        def __init__(self, market, **kw):
            super().__init__(market, venue="alpaca-paper", equity="100000", **kw)
            self.extra_positions = []
            self.stock_fill = "natural"
            self.activity_lag = False

        def _try_fill(self, order):
            if order["legs"] or order["type"] != "limit" or len(order["symbol"]) > 6:
                return super()._try_fill(order)
            if self.stock_fill == "none":
                return
            quote = self.market.stocks([order["symbol"]])[order["symbol"]]["latestQuote"]
            limit, buying = D(order["limit_price"]), order["side"] == "buy"
            price = D(str(quote["ap"] if buying else quote["bp"]))
            if (buying and price > limit) or (not buying and price < limit):
                return
            left = D(order["qty"]) - D(order["filled_qty"])
            add = left if self.stock_fill == "natural" else (left / 2).quantize(D("0.000001"))
            if add <= 0:
                return
            done = D(order["filled_qty"]) + add
            order["filled_qty"], order["filled_avg_price"] = str(done), str(price)
            order["status"] = "filled" if done >= D(order["qty"]) else "partially_filled"
            if order["status"] == "filled":
                order["filled_at"] = iso(self.clock())
            sign = D(1) if buying else D(-1)
            self.held[order["symbol"]] = self.held.get(order["symbol"], D(0)) + sign * add
            if not self.activity_lag:
                self.activity_rows.append({"id": str(uuid.uuid4()), "activity_type": "FILL", "order_id": order["id"],
                                           "symbol": order["symbol"], "side": order["side"], "qty": str(add),
                                           "price": str(price), "transaction_time": iso(self.clock())})


@unittest.skipUnless(HAVE, "numpy not installed")
class TheStockProof(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(at(MONDAY, 15, 50))
        self.market = Market(self.clock)
        self.paper = PaperStocks(self.market)
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=self.clock)
        self.records = []
        self.proof = StockPaperProof(self.state, self.paper, record=lambda kind, payload, agent=None:
                                     self.records.append((kind, payload)), clock=self.clock)

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def step(self, day, hh, mm, ss=3):
        self.clock.set(at(day, hh, mm, ss))
        return self.proof.step(self.clock(), market=self.market)

    def bodies(self, side=None):
        return [b for b in self.paper.sent if side is None or b["side"] == side]

    def test_a_close_buy_held_overnight_and_sold_at_the_open_passes(self):
        self.assertEqual(self.step(MONDAY, 15, 54)["status"], "waiting")
        self.assertEqual(self.paper.sent, [], "not before 15:55")
        row = self.step(MONDAY, 15, 55)
        [buy] = self.bodies()
        self.assertTrue(buy["client_order_id"].startswith("lq-pp-20260928-") and buy["client_order_id"].endswith("-b"))
        self.assertEqual((buy["symbol"], buy["side"], buy["type"], buy["time_in_force"]), ("SPY", "buy", "limit", "day"))
        self.assertEqual(buy["limit_price"], "600.62", "the ask 600.01 plus 10 bp, up to the cent")
        self.assertEqual(buy["qty"], "0.041623", "about $25: a fractional share, six places")
        self.assertEqual(row["status"], "buy_sent")
        row = self.step(MONDAY, 15, 56)
        self.assertEqual(row["status"], "held")
        self.assertTrue(row["buy_witness"] and row["hold_witness"])
        for hh, mm in ((15, 58), (16, 0), (20, 0)):
            self.step(MONDAY, hh, mm)
        self.assertEqual(self.step(TUESDAY, 9, 30)["status"], "held", "never before 09:30:30")
        self.assertEqual(self.bodies("sell"), [])
        row = self.step(TUESDAY, 9, 31)
        [sale] = self.bodies("sell")
        self.assertEqual((sale["qty"], sale["type"], sale["limit_price"]), ("0.041623", "limit", "599.39"))
        self.assertTrue(sale["client_order_id"].endswith("-s1"))
        row = self.step(TUESDAY, 9, 32)
        self.assertEqual(row["status"], "passed", row.get("why"))
        self.assertTrue(self.proof.passed())
        self.assertEqual(self.paper.held.get("SPY"), D(0))
        self.assertEqual([p for k, p in self.records if k == "live.paper_proof"],
                         [{"status": "passed", "day": "2026-09-29", "kind": "stock"}])
        self.step(TUESDAY, 9, 40)
        self.assertEqual(len(self.paper.sent), 2, "a passed proof sends nothing more")

    def test_never_lv_and_never_the_options_key(self):
        self.step(MONDAY, 15, 55)
        self.assertTrue(all(b["client_order_id"].startswith("lq-pp-") for b in self.paper.sent))
        self.assertIsNone(self.state.get("paper_proof"))
        self.assertIsNotNone(self.state.get(STOCK_KEY))

    def test_an_unfilled_buy_is_cancelled_at_15_59_30_and_tried_again_at_the_next_close(self):
        self.paper.stock_fill = "none"
        self.step(MONDAY, 15, 55)
        self.step(MONDAY, 15, 59, 0)
        self.assertEqual(self.paper.cancels, [], "still inside the window")
        self.step(MONDAY, 15, 59, 31)
        self.assertEqual(len(self.paper.cancels), 1)
        row = self.step(MONDAY, 15, 59, 45)
        self.assertEqual(row["status"], "waiting")
        self.step(MONDAY, 15, 59, 50)
        self.assertEqual(len(self.bodies("buy")), 1, "one attempt a session")
        self.paper.stock_fill = "natural"
        self.step(TUESDAY, 9, 31)
        self.assertEqual(len(self.bodies()), 1, "a buy goes only in the close window")
        self.step(TUESDAY, 15, 55)
        self.assertEqual(len(self.bodies("buy")), 2)
        self.assertEqual(self.proof.status()["attempts"], 2)

    def test_a_partial_sale_is_cancelled_then_sent_again_for_what_is_left_wider(self):
        self.step(MONDAY, 15, 55)
        self.step(MONDAY, 15, 56)
        self.paper.stock_fill = "half"
        self.step(TUESDAY, 9, 31)                                   # half of the lot sold on its way in
        self.paper.stock_fill = "none"                              # then it rests
        self.step(TUESDAY, 9, 31, 30)
        self.assertEqual(self.paper.cancels, [], "a sale gets a minute")
        self.step(TUESDAY, 9, 32, 10)
        self.assertEqual(len(self.paper.cancels), 1)
        self.paper.stock_fill = "natural"
        self.step(TUESDAY, 9, 33)                                   # terminal: what is left is sent again at once
        sales = self.bodies("sell")
        self.assertEqual(len(sales), 2)
        self.assertEqual(D(sales[0]["qty"]) - D(sales[1]["qty"]), D("0.020812"), "what the first one sold")
        self.assertEqual(sales[1]["limit_price"], "598.79", "the bid less 20 bp: one step wider")
        self.assertTrue(sales[1]["client_order_id"].endswith("-s2"))
        row = self.step(TUESDAY, 9, 34)
        self.assertEqual(row["status"], "passed", row.get("why"))

    def test_missing_activities_hold_the_pass_and_end_the_attempt_after_the_session(self):
        self.paper.activity_lag = True
        self.step(MONDAY, 15, 55)
        self.step(MONDAY, 15, 56)
        self.step(TUESDAY, 9, 31)
        row = self.step(TUESDAY, 9, 32)
        self.assertEqual(row["status"], "sold")
        self.assertFalse(row["activity_witness"])
        self.assertIn("activity_witness", row["why"])
        self.assertFalse(self.proof.passed())
        row = self.step(WEDNESDAY, 9, 0)
        self.assertEqual(row["status"], "waiting", "the attempt ended flat")
        self.assertFalse(self.proof.passed())

    def test_a_position_that_disagrees_with_the_fills_never_passes(self):
        self.step(MONDAY, 15, 55)
        self.paper.held["SPY"] = self.paper.held.get("SPY", D(0)) + D("0.5")   # not this attempt's: a stray half share
        row = self.step(MONDAY, 15, 56)
        self.assertEqual(row["status"], "held")
        self.assertFalse(row["hold_witness"])
        self.step(TUESDAY, 9, 31)
        row = self.step(TUESDAY, 9, 32)
        self.assertFalse(self.proof.passed())
        self.assertFalse(row["hold_witness"])
        self.assertEqual(self.paper.held["SPY"], D("0.5"), "the stray half share is left alone")

    def test_an_unreadable_account_sends_nothing(self):
        self.paper.positions = lambda: (_ for _ in ()).throw(RuntimeError("HTTP 500"))
        row = self.step(MONDAY, 15, 55)
        self.assertIn("unreadable", row["why"])
        self.assertEqual(self.paper.sent, [])

    def test_a_restart_mid_attempt_resumes_by_client_id_and_sends_nothing_twice(self):
        self.step(MONDAY, 15, 55)
        again = StockPaperProof(self.state, self.paper, clock=self.clock)
        self.clock.set(at(MONDAY, 15, 56))
        self.assertEqual(again.step(self.clock(), market=self.market)["status"], "held")
        self.clock.set(at(TUESDAY, 9, 31))
        again.step(self.clock(), market=self.market)
        self.clock.set(at(TUESDAY, 9, 32))
        self.assertEqual(again.step(self.clock(), market=self.market)["status"], "passed")
        self.assertEqual([b["side"] for b in self.paper.sent], ["buy", "sell"])

    def test_a_lost_answer_is_looked_up_never_sent_again(self):
        self.paper.submit_mode = "lost"
        row = self.step(MONDAY, 15, 55)
        self.assertEqual(row["status"], "buy_sent")
        self.paper.submit_mode = "ok"
        self.step(MONDAY, 15, 56)                                   # found by its client id, resting
        row = self.step(MONDAY, 15, 57)
        self.assertEqual(row["status"], "held", "its fill read by its client id")
        self.assertEqual(len(self.paper.sent), 1)


if __name__ == "__main__":
    unittest.main()
