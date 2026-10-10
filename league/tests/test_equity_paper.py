"""The stock paper proof (league/live/paper.py `StockPaperProof`, release E1, A8.7 as staged by A10.1), in the equity
book's OPEN window (the book's `league.equity.schedule.Moments`): stage BUY, a fractional SPY bought with a marketable
limit from 09:30:30 ET to the entry cut-off, passed on its fill, its lot row and the reconciled position (it gates
every real equity buy); stage SELL, that lot sold in the next session's open window, passed only once its fills, the
position, the account's FILL activities and the reconciliation all witness the round trip (it gates every real equity
sale); a SELL stage that ends its window unpassed fails, with an alarm, and the proof tries again. The practice account
is `live_fakes.Venue` taught to fill stock limit orders (invented prices, the venue's shapes)."""

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
    from league.equity import schedule as S
    from league.live.paper import STOCK_BUY_KEY, STOCK_KEY, STOCK_SELL_KEY, StockPaperProof
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
        self.clock = Clock(at(MONDAY, 9, 0))
        self.market = Market(self.clock)
        self.paper = PaperStocks(self.market)
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=self.clock)
        self.records = []
        self.alerts = []
        self.proof = self.new_proof()

    def new_proof(self):
        return StockPaperProof(self.state, self.paper, clock=self.clock,
                               record=lambda kind, payload, agent=None: self.records.append((kind, payload)),
                               alert=lambda level, text: self.alerts.append((level, text)))

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def step(self, day, hh, mm, ss=3, *, proof=None):
        """One minute of the book's tick: the proof stepped with the book's own moments of the day."""
        self.clock.set(at(day, hh, mm, ss))
        return (proof or self.proof).step(self.clock(), market=self.market, window=S.moments(day))

    def bodies(self, side=None):
        return [b for b in self.paper.sent if side is None or b["side"] == side]

    def bought_monday(self):
        self.step(MONDAY, 9, 31)
        row = self.step(MONDAY, 9, 32)
        self.assertEqual(row["status"], "held")
        self.assertTrue(self.proof.buy_passed())

    def test_stage_buy_in_the_open_window_then_stage_sell_at_the_next_open(self):
        self.assertEqual(self.step(MONDAY, 9, 30)["status"], "waiting")
        self.assertEqual(self.paper.sent, [], "not before 09:30:30")
        row = self.step(MONDAY, 9, 31)
        [buy] = self.bodies()
        self.assertTrue(buy["client_order_id"].startswith("lq-pp-20260928-") and buy["client_order_id"].endswith("-b"))
        self.assertEqual((buy["symbol"], buy["side"], buy["type"], buy["time_in_force"]), ("SPY", "buy", "limit", "day"))
        self.assertEqual(buy["limit_price"], "600.62", "the ask 600.01 plus 10 bp, up to the cent")
        self.assertEqual(buy["qty"], "0.041623", "about $25: a fractional share, six places")
        self.assertEqual(row["status"], "buy_sent")
        self.assertFalse(self.proof.buy_passed())
        row = self.step(MONDAY, 9, 32)
        self.assertEqual(row["status"], "held")
        self.assertTrue(row["buy_witness"] and row["hold_witness"])
        self.assertTrue(self.proof.buy_passed(), "stage BUY: its fill, its lot row and the reconciled position")
        self.assertEqual(self.state.get(STOCK_BUY_KEY)["lot"]["qty"], "0.041623")
        self.assertFalse(self.proof.sell_passed() or self.proof.passed())
        self.assertEqual(self.proof.sell_failed(), "", "the SELL stage is to come, not failed: real buys may go")
        for hh, mm in ((12, 0), (15, 56), (16, 0), (20, 0)):
            self.step(MONDAY, hh, mm)
        self.assertEqual(self.bodies("sell"), [], "never sold in the session it was bought")
        self.assertEqual(self.step(TUESDAY, 9, 30)["status"], "held", "never before 09:30:30")
        self.assertEqual(self.bodies("sell"), [])
        self.step(TUESDAY, 9, 31)
        [sale] = self.bodies("sell")
        self.assertEqual((sale["qty"], sale["type"], sale["limit_price"]), ("0.041623", "limit", "599.39"))
        self.assertTrue(sale["client_order_id"].endswith("-s1"))
        row = self.step(TUESDAY, 9, 32)
        self.assertEqual(row["status"], "passed", row.get("why"))
        self.assertTrue(self.proof.sell_passed() and self.proof.passed())
        self.assertEqual(self.paper.held.get("SPY"), D(0))
        self.assertEqual([p for k, p in self.records if k == "live.paper_proof"],
                         [{"status": "passed", "stage": "buy", "day": "2026-09-28", "kind": "stock"},
                          {"status": "passed", "stage": "sell", "day": "2026-09-29", "kind": "stock"}])
        self.step(TUESDAY, 9, 40)
        self.assertEqual(len(self.paper.sent), 2, "a passed proof sends nothing more")
        self.assertEqual(self.alerts, [])

    def test_never_lv_and_never_the_options_key(self):
        self.step(MONDAY, 9, 31)
        self.assertTrue(all(b["client_order_id"].startswith("lq-pp-") for b in self.paper.sent))
        self.assertIsNone(self.state.get("paper_proof"))
        self.assertIsNotNone(self.state.get(STOCK_KEY))

    def test_a_buy_goes_only_in_the_open_window(self):
        self.step(MONDAY, 15, 55)
        self.step(MONDAY, 9, 46)
        self.assertEqual(self.paper.sent, [], "after the entry cut-off and in the close window: nothing")
        self.clock.set(at(MONDAY, 9, 31))
        self.proof.step(self.clock(), market=self.market, window=None)
        self.assertEqual(self.paper.sent, [], "a day the book has no window for: nothing")
        self.step(TUESDAY, 9, 31)
        self.assertEqual(len(self.bodies("buy")), 1)

    def test_an_unfilled_buy_is_cancelled_at_the_entry_cut_off_and_tried_again_at_the_next_open(self):
        self.paper.stock_fill = "none"
        self.step(MONDAY, 9, 31)
        self.step(MONDAY, 9, 44, 50)
        self.assertEqual(self.paper.cancels, [], "still inside the window")
        self.step(MONDAY, 9, 45, 3)
        self.assertEqual(len(self.paper.cancels), 1)
        row = self.step(MONDAY, 9, 46)
        self.assertEqual(row["status"], "waiting")
        self.step(MONDAY, 9, 47)
        self.assertEqual(len(self.bodies("buy")), 1, "one attempt a session")
        self.paper.stock_fill = "natural"
        self.step(TUESDAY, 9, 31)
        self.assertEqual(len(self.bodies("buy")), 2)
        self.assertEqual(self.proof.status()["attempts"], 2)
        self.assertFalse(self.proof.buy_passed())
        self.step(TUESDAY, 9, 32)
        self.assertTrue(self.proof.buy_passed())

    def test_a_partial_sale_is_cancelled_then_sent_again_for_what_is_left_wider(self):
        self.bought_monday()
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

    def test_missing_activities_fail_the_sell_stage_when_its_window_ends(self):
        self.paper.activity_lag = True
        self.bought_monday()
        self.step(TUESDAY, 9, 31)
        row = self.step(TUESDAY, 9, 32)
        self.assertEqual(row["status"], "sold")
        self.assertFalse(row["activity_witness"])
        self.assertIn("activity_witness", row["why"])
        self.assertFalse(self.proof.sell_passed())
        self.assertEqual(self.proof.sell_failed(), "", "not failed while its window is open")
        row = self.step(TUESDAY, 15, 55)
        self.assertEqual(row["status"], "waiting", "the attempt ended flat")
        self.assertIn("SELL stage failed", self.proof.sell_failed())
        self.assertIn("activity_witness", self.proof.sell_failed())
        [(level, text)] = self.alerts
        self.assertEqual(level, "error")
        self.assertIn("new real equity buys stop", text)
        self.assertIn("Owner step", text)
        self.assertTrue(self.proof.buy_passed(), "stage BUY stays passed")
        self.paper.activity_lag = False
        self.step(WEDNESDAY, 9, 31)
        self.assertEqual(len(self.bodies("buy")), 2, "the next open window buys again")
        self.assertEqual(self.state.get(STOCK_SELL_KEY)["failures"], 1)

    def test_a_sale_unfilled_by_the_windows_end_fails_holds_the_lot_and_sells_next_session(self):
        self.bought_monday()
        self.paper.stock_fill = "none"
        self.step(TUESDAY, 9, 31)
        self.step(TUESDAY, 15, 55, 3)                               # the window ended: the working sale cancelled
        self.assertEqual(self.proof.sell_failed(), "")
        row = self.step(TUESDAY, 15, 56)
        self.assertEqual(row["status"], "held", "the practice lot stays held")
        self.assertIn("not sold by the open window's end", self.proof.sell_failed())
        self.assertEqual(len(self.alerts), 1)
        self.step(TUESDAY, 15, 58)
        self.assertEqual(len(self.alerts), 1, "told once a failure")
        self.paper.stock_fill = "natural"
        self.step(WEDNESDAY, 9, 31)
        self.assertEqual(len(self.bodies("sell")), 2)
        row = self.step(WEDNESDAY, 9, 32)
        self.assertEqual(row["status"], "passed", row.get("why"))
        self.assertTrue(self.proof.sell_passed())
        self.assertEqual(self.proof.sell_failed(), "", "a pass ends the failure")

    def test_a_position_that_disagrees_with_the_fills_never_passes(self):
        self.step(MONDAY, 9, 31)
        self.paper.held["SPY"] = self.paper.held.get("SPY", D(0)) + D("0.5")   # not this attempt's: a stray half share
        row = self.step(MONDAY, 9, 32)
        self.assertEqual(row["status"], "held")
        self.assertFalse(row["hold_witness"])
        self.assertFalse(self.proof.buy_passed(), "stage BUY needs the position reconciled")
        self.step(TUESDAY, 9, 31)
        row = self.step(TUESDAY, 9, 32)
        self.assertFalse(self.proof.passed())
        self.assertFalse(row["hold_witness"])
        self.assertEqual(self.paper.held["SPY"], D("0.5"), "the stray half share is left alone")

    def test_an_unreadable_account_sends_nothing(self):
        self.paper.positions = lambda: (_ for _ in ()).throw(RuntimeError("HTTP 500"))
        row = self.step(MONDAY, 9, 31)
        self.assertIn("unreadable", row["why"])
        self.assertEqual(self.paper.sent, [])

    def test_a_restart_mid_attempt_resumes_by_client_id_and_sends_nothing_twice(self):
        self.step(MONDAY, 9, 31)
        again = self.new_proof()
        self.assertEqual(self.step(MONDAY, 9, 32, proof=again)["status"], "held")
        self.step(TUESDAY, 9, 31, proof=again)
        self.assertEqual(self.step(TUESDAY, 9, 32, proof=again)["status"], "passed")
        self.assertEqual([b["side"] for b in self.paper.sent], ["buy", "sell"])

    def test_a_lost_answer_is_looked_up_never_sent_again(self):
        self.paper.submit_mode = "lost"
        row = self.step(MONDAY, 9, 31)
        self.assertEqual(row["status"], "buy_sent")
        self.paper.submit_mode = "ok"
        self.step(MONDAY, 9, 32)                                    # found by its client id, resting
        row = self.step(MONDAY, 9, 33)
        self.assertEqual(row["status"], "held", "its fill read by its client id")
        self.assertEqual(len(self.paper.sent), 1)


if __name__ == "__main__":
    unittest.main()
