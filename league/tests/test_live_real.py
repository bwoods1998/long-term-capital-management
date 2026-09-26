"""The real book and its order path (`league/live/real.py`): client order ids written before sending, lost answers,
restarts mid-order, partial and uneven multi-leg fills, the contract rules, the order count and reconciliation. The
venue is `live_fakes.Venue`: Alpaca's documented multi-leg shapes with invented prices."""

import datetime as dt
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.live import money as M
    from league.live.real import RealBook, RLeg, ROrder, client_id, limit_price, mleg_body, structure_fill
    from league.live.state import LiveState
    from league.live.venue import occ_symbol
    from league.tests.live_fakes import MONDAY, Clock, Market, Venue, at


def legs(strike=600.0, width=1.0, expiry="2026-09-29", right=True):
    return [RLeg(occ_symbol("SPY", expiry, right, strike), 1, 1, right, strike, expiry, 1),
            RLeg(occ_symbol("SPY", expiry, right, strike + width), -1, 1, right, strike + width, expiry, 2)]


@unittest.skipUnless(HAVE, "numpy not installed")
class Prices(unittest.TestCase):
    def test_the_signed_limit(self):
        self.assertEqual(limit_price(0.55, "open"), "0.55")        # a debit opened: paid, positive
        self.assertEqual(limit_price(-0.38, "open"), "-0.38")      # a credit opened: received, negative
        self.assertEqual(limit_price(0.47, "close"), "-0.47")      # a debit closed: received, negative
        self.assertEqual(limit_price(-0.12, "close"), "0.12")      # a credit bought back: paid, positive
        self.assertEqual(limit_price(0.0, "close"), "0.00")
        self.assertEqual(limit_price(-0.0, "close"), "0.00")

    def test_the_multi_leg_body_is_the_gateways(self):
        order = ROrder(7, client_id(7, "Condor VRP!", nonce="a1b2c3"), "i", "condor-vrp", "open", "debit_vertical", "SPY", legs(), 3,
                       0.55, "0.55", None, 0.0, "2026-09-28", 10)
        body = mleg_body(order)
        self.assertEqual(body["client_order_id"], "lv-a1b2c3-0000007-condor-vrp")
        self.assertEqual({k: body[k] for k in ("order_class", "qty", "type", "limit_price", "time_in_force")},
                         {"order_class": "mleg", "qty": "3", "type": "limit", "limit_price": "0.55", "time_in_force": "day"})
        self.assertEqual([(l["side"], l["position_intent"], l["ratio_qty"]) for l in body["legs"]],
                         [("buy", "buy_to_open", "1"), ("sell", "sell_to_open", "1")])
        order.action = "close"
        self.assertEqual([(l["side"], l["position_intent"]) for l in mleg_body(order)["legs"]],
                         [("sell", "sell_to_close"), ("buy", "buy_to_close")])


@unittest.skipUnless(HAVE, "numpy not installed")
class Fills(unittest.TestCase):
    def order(self, qty=3):
        return ROrder(1, "lv-0000001-f", "i", "f", "open", "debit_vertical", "SPY", legs(), qty, 0.60, "0.60", None, 0.0,
                      "2026-09-28", 10)

    def row(self, parent, first, second, p1="1.50", p2="0.95"):
        a, b = legs()
        return {"id": "x", "status": "partially_filled", "filled_qty": str(parent),
                "legs": [{"symbol": a.symbol, "filled_qty": str(first), "filled_avg_price": p1 if first else None},
                         {"symbol": b.symbol, "filled_qty": str(second), "filled_avg_price": p2 if second else None}]}

    def test_whole_structures_only(self):
        self.assertEqual(structure_fill(self.order(), self.row(1, 1, 1))[:2], (1, 0.55))
        units, value, _, uneven = structure_fill(self.order(), self.row(2, 2, 1))
        self.assertEqual((units, uneven), (1, True))     # a leg ahead of the other waits
        self.assertIsNone(structure_fill(self.order(), {"id": "x", "status": "filled", "filled_qty": "3"}))  # no legs yet

    def test_partial_fills_across_readings_book_their_increments(self):
        with tempfile.TemporaryDirectory() as d:
            clock = Clock(at(MONDAY, 10, 0))
            market = Market(clock)
            book = RealBook(LiveState(Path(d) / "live.sqlite", clock=clock), Venue(market), M.Table.from_constitution(), clock=clock)
            order = book.new_order(instance="i", family="f", action="open", type_="debit_vertical", root="SPY", legs=legs(),
                                   qty=3, limit_value=0.60, tif=None, day="2026-09-28", minute=30, max_loss=180.0)
            order.status, order.venue_id, order.dispatched = "working", "x", True
            book._absorb(order, dict(self.row(1, 1, 1), client_order_id=order.client_id))
            pos = book.positions[order.pid]
            self.assertEqual((pos.qty, round(pos.entry, 4)), (1, 0.55))
            book._absorb(order, dict(self.row(3, 3, 3, p1="1.60", p2="1.00"), client_order_id=order.client_id, status="filled"))
            # Cumulative averages 1.60 / 1.00: 0.60 over three; the first was 0.55, so the next two were 0.625 each.
            self.assertEqual(pos.qty, 3)
            self.assertAlmostEqual(pos.entry, 0.60, places=9)
            self.assertEqual(order.status, "filled")
            fills = book.state.rows("SELECT qty, value FROM fills ORDER BY id")
            self.assertEqual([(f["qty"], round(f["value"], 4)) for f in fills], [(1, 0.55), (2, 0.625)])


@unittest.skipUnless(HAVE, "numpy not installed")
class OrderPath(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(at(MONDAY, 10, 0))
        self.market = Market(self.clock)
        self.venue = Venue(self.market)
        self.path = Path(self.dir.name) / "live.sqlite"
        self.book = RealBook(LiveState(self.path, clock=self.clock), self.venue, M.Table.from_constitution(), clock=self.clock)

    def tearDown(self):
        self.dir.cleanup()

    def open(self, qty=2, strike=600.0, family="f", limit=None):
        a, b = legs(strike)
        bid_a, ask_a = self.market.quote(a.symbol)
        bid_b, ask_b = self.market.quote(b.symbol)
        natural = round(ask_a - bid_b, 2) if limit is None else limit
        order = self.book.new_order(instance=f"{family}@1:r", family=family, action="open", type_="debit_vertical", root="SPY",
                                    legs=[a, b], qty=qty, limit_value=natural, tif=None, day="2026-09-28", minute=30,
                                    max_loss=natural * 100 * qty, reserve=natural * 110 * qty)
        return self.book.send(order)

    def test_the_row_is_written_before_the_order_is_sent(self):
        seen = []
        self.venue.on_submit = lambda body: seen.extend(LiveState(self.path).rows("SELECT client_id, status FROM orders"))
        order = self.open()
        self.assertEqual(seen, [{"client_id": order.client_id, "status": "pending"}])
        self.assertEqual(self.venue.sent[0]["client_order_id"], order.client_id)
        self.assertEqual(order.status, "filled")
        self.assertEqual(self.book.positions[order.pid].qty, 2)

    def test_a_lost_answer_is_looked_up_never_sent_again(self):
        self.venue.submit_mode = "lost"
        order = self.open()
        self.assertEqual(order.status, "unknown")
        self.assertEqual(len(self.venue.sent), 1)
        self.clock.set(self.clock() + 60)
        self.book.look_up(today="2026-09-28")
        self.assertEqual(len(self.venue.sent), 1)
        self.assertEqual(self.book.orders[order.oid].status, "working")   # found at the venue by its client id
        self.book.ingest(self.venue.orders())                            # and it fills there
        self.assertIsNone(self.book.orders.get(order.oid))
        self.assertEqual(sum(p.qty for p in self.book.positions.values()), 2)

    def test_a_lost_answer_the_venue_never_saw_is_lost_and_found_again_if_it_turns_up(self):
        self.venue.submit_mode = "lost_absent"
        order = self.open()
        for i in range(4):
            self.clock.set(self.clock() + 60)
            self.book.look_up(today="2026-09-28")
        self.assertEqual(self.book.state.rows("SELECT status FROM orders")[0]["status"], "lost")
        self.assertEqual(len(self.venue.sent), 1)
        # It turns up after all (it had reached the venue): the next reading of the orders books its fill.
        self.venue.submit_mode = "ok"
        created = self.venue._create(self.venue.sent[0])
        self.venue._try_fill(created)
        foreign = self.book.ingest(self.venue.orders_rows())
        self.assertEqual(foreign, [])
        self.assertEqual(sum(p.qty for p in self.book.positions.values()), 2)

    def test_a_restart_mid_order_finds_it_by_its_client_id(self):
        self.venue.fill = "none"
        order = self.open()
        self.assertEqual(order.status, "working")
        # A crash between the row and the POST's answer: the row says pending, the venue has the order.
        LiveState(self.path).execute("UPDATE orders SET status='pending', venue_id=NULL WHERE oid=?", (order.oid,))
        again = RealBook(LiveState(self.path, clock=self.clock), self.venue, M.Table.from_constitution(), clock=self.clock)
        self.assertEqual(again.orders[order.oid].status, "pending")
        self.clock.set(self.clock() + 60)
        again.look_up(today="2026-09-28")
        self.assertEqual(again.orders[order.oid].status, "working")
        self.assertEqual(len(self.venue.sent), 1)
        self.venue.fill = "natural"
        again.ingest(self.venue.orders())
        self.assertEqual(sum(p.qty for p in again.positions.values()), 2)

    def test_a_new_live_state_never_reuses_a_client_id(self):
        order = self.open()
        other = RealBook(LiveState(Path(self.dir.name) / "fresh.sqlite", clock=self.clock), self.venue, M.Table.from_constitution(),
                         clock=self.clock)
        again = other.new_order(instance="f@1:r", family="f", action="open", type_="debit_vertical", root="SPY", legs=legs(605.0),
                                qty=1, limit_value=0.5, tif=None, day="2026-09-28", minute=30)
        self.assertEqual(again.oid, order.oid)                      # the same row id in a new state ...
        self.assertNotEqual(again.client_id, order.client_id)       # ... never the same client order id
        other.state.close()

    def test_a_fill_and_the_orders_progress_are_one_commit(self):
        self.venue.fill = "none"
        order = self.open()
        self.venue.fill = "natural"
        real_upsert = self.book.state.upsert

        def crash_on_order(table, row, key):
            if table == "orders":
                raise RuntimeError("the House died here")
            return real_upsert(table, row, key)

        self.book.state.upsert = crash_on_order
        with self.assertRaises(RuntimeError):
            self.book.ingest(self.venue.orders())
        self.book.state.upsert = real_upsert
        again = RealBook(LiveState(self.path, clock=self.clock), self.venue, M.Table.from_constitution(), clock=self.clock)
        again.ingest(self.venue.orders())
        self.assertEqual(sum(p.qty for p in again.positions.values()), 2, "booked once, not twice")
        self.assertEqual(len(again.state.rows("SELECT * FROM fills")), 1)

    def test_a_partial_fill_then_a_cancel_leaves_what_filled(self):
        self.venue.fill = "partial"
        order = self.open(qty=3)
        self.assertEqual(self.book.positions[order.pid].qty, 1)
        self.book.ingest(self.venue.orders())
        self.assertEqual(self.book.positions[order.pid].qty, 2)
        self.venue.fill = "none"
        self.book.cancel(self.book.orders[order.oid], "test")
        self.book.ingest(self.venue.orders())
        self.assertNotIn(order.oid, self.book.orders)
        self.assertEqual(self.book.positions[order.pid].qty, 2)
        self.assertEqual(self.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False), [])

    def test_an_uneven_fill_freezes_new_entries(self):
        self.venue.fill = "uneven"
        self.open(qty=1)
        for _ in range(2):
            self.book.ingest(self.venue.orders())
            problems = self.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False)
        self.assertTrue(any("unevenly" in p for p in problems))
        self.assertIn("unevenly", self.book.frozen)

    def test_venue_and_gateway_refusals(self):
        self.venue.submit_mode = "reject"
        order = self.open()
        self.assertEqual((order.status, order.dispatched), ("rejected", True))
        self.assertIn("wash trade", self.book.rejects_since["f@1:r"][0])
        self.venue.submit_mode = "gateway"
        order = self.open(strike=605.0)
        self.assertEqual((order.status, order.dispatched), ("refused", False))
        self.venue.submit_mode = "ok"
        from league.live.venue import Submitted

        original = self.venue.submit
        self.venue.submit = lambda body, exit: Submitted(False, {"error": "equity unread", "cap": "equity"}, "HTTP 503", status=503)
        order = self.open(strike=610.0)
        self.venue.submit = original
        self.assertEqual((order.status, order.dispatched), ("refused", False))    # never dispatched, never counted
        # The gateway's day cap counts what reached the venue, not what the gateway refused.
        exposure = self.book.exposure("f", day="2026-09-28", week_start="2026-09-28")
        rejected = self.book.state.rows("SELECT max_loss FROM orders WHERE status='rejected'")[0]["max_loss"]
        self.assertEqual(exposure.day_opened, M.D(rejected))

    def test_one_order_stream_a_contract_and_no_opposite_side(self):
        self.venue.fill = "none"
        order = self.open()
        self.assertIn("one order stream per contract", self.book.path_refusal(order.legs, opening=True, day="2026-09-28"))
        self.venue.fill = "natural"
        self.book.ingest(self.venue.orders())
        a, b = order.legs
        # Another family selling the contract this book holds long: refused (positions net across the account).
        other = [RLeg(a.symbol, -1, 1, True, a.strike, a.expiry, a.key), RLeg(occ_symbol("SPY", a.expiry, True, a.strike - 1), 1, 1, True, a.strike - 1, a.expiry, 3)]
        self.assertIn("takes the other side", self.book.path_refusal(other, opening=True, day="2026-09-28"))
        same_side = [RLeg(a.symbol, 1, 1, True, a.strike, a.expiry, a.key), RLeg(occ_symbol("SPY", a.expiry, True, a.strike + 2), -1, 1, True, a.strike + 2, a.expiry, 4)]
        self.assertIsNone(self.book.path_refusal(same_side, opening=True, day="2026-09-28"))

    def test_the_days_order_count_counts_legs_and_cancels_and_keeps_room_to_close(self):
        self.book._count("2026-09-28", 240)
        # One open structure of two legs keeps four for its close and a cancel: 250 - 240 - 0 leaves ten for a new open.
        self.assertIsNone(self.book.path_refusal(legs(610.0), opening=True, day="2026-09-28"))
        order = self.open()
        self.assertEqual(self.book.count_today("2026-09-28"), 242)
        self.assertEqual(self.book.exit_reserve(), 4)
        self.book._count("2026-09-28", 3)             # 245 + 4 kept = 249: a two-leg open does not fit
        self.assertIn("the day's order count", self.book.path_refusal(legs(620.0), opening=True, day="2026-09-28"))
        # A program's close keeps the room the House's own exits need (4 at least); the House's exit meets only the gateway.
        self.assertIn("kept for the House's own exits", self.book.path_refusal(legs(630.0), opening=False, day="2026-09-28"))
        self.assertIsNone(self.book.path_refusal(legs(630.0), opening=False, day="2026-09-28", house=True))
        self.assertIn("kept for the House's own exits", self.book.count_refusal(2, day="2026-09-28"))


@unittest.skipUnless(HAVE, "numpy not installed")
class Reconciliation(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(at(MONDAY, 10, 0))
        self.market = Market(self.clock)
        self.venue = Venue(self.market)
        self.book = RealBook(LiveState(Path(self.dir.name) / "live.sqlite", clock=self.clock), self.venue,
                             M.Table.from_constitution(), clock=self.clock)
        a, b = legs()
        order = self.book.new_order(instance="f@1:r", family="f", action="open", type_="debit_vertical", root="SPY", legs=[a, b],
                                    qty=1, limit_value=5.0, tif=None, day="2026-09-28", minute=30)
        self.book.send(order)

    def tearDown(self):
        self.dir.cleanup()

    def recon(self, **kw):
        return self.book.reconcile(self.venue.positions(), kw.pop("foreign", []), day=MONDAY, after_close=kw.pop("after_close", False), **kw)

    def test_a_matching_account_with_the_known_dust(self):
        self.assertEqual(self.recon(), [])
        self.assertEqual(self.book.frozen, "")

    def test_a_mismatch_freezes_on_the_second_reading_and_clears_after_two_clean_ones(self):
        sym = next(iter(self.venue.held))
        self.venue.held[sym] += 1
        self.assertTrue(self.recon())
        self.assertEqual(self.book.frozen, "")          # one reading: a fill in flight, perhaps
        self.assertTrue(self.recon())
        self.assertIn("the account holds 2, the book 1", self.book.frozen)
        self.venue.held[sym] -= 1
        self.recon()
        self.assertNotEqual(self.book.frozen, "")
        self.recon()
        self.assertEqual(self.book.frozen, "")

    def test_what_is_a_mismatch(self):
        self.venue.extra_positions.append({"symbol": "BTCUSD", "asset_class": "crypto", "qty": "0.01", "side": "long"})
        self.assertIn("BTCUSD", " ".join(self.recon()))
        self.venue.extra_positions[-1] = {"symbol": "LTCUSD", "asset_class": "crypto", "qty": "0.5", "side": "long"}
        self.venue.extra_positions = self.venue.extra_positions[-1:]
        self.assertIn("LTCUSD", " ".join(self.recon()))          # more than the known dust
        self.venue.extra_positions = []
        self.venue.held["SPY"] = D(100)
        self.assertIn("100 shares held, 0 expected", " ".join(self.recon()))
        self.assertEqual(self.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False, shares={"SPY": 100}), [])
        del self.venue.held["SPY"]
        self.assertIn("not the live path's", " ".join(self.recon(foreign=[{"client_order_id": "manual-1", "status": "new"}])))

    def test_the_close_of_an_assignments_shares_is_the_houses_own_order(self):
        rows = self.venue.orders_rows() + [{"id": "s1", "client_order_id": "lv-shares-spy-1790000000", "status": "new",
                                            "symbol": "SPY", "side": "sell", "legs": None}]
        self.assertEqual(self.book.ingest(rows), [])
        self.assertEqual(self.book.ingest(rows + [{"id": "m1", "client_order_id": "manual", "status": "new"}])[0]["id"], "m1")

    def test_after_the_close_contracts_expiring_that_day_are_the_venues_to_settle(self):
        day_legs = legs(expiry="2026-09-28")
        order = self.book.new_order(instance="f@1:r", family="f", action="open", type_="debit_vertical", root="SPY", legs=day_legs,
                                    qty=1, limit_value=5.0, tif=None, day="2026-09-28", minute=30)
        self.book.send(order)
        for leg in day_legs:
            self.venue.held.pop(leg.symbol)
        self.assertTrue(self.recon())
        self.assertEqual(self.recon(after_close=True), [])


@unittest.skipUnless(HAVE, "numpy not installed")
class ClientIds(unittest.TestCase):
    def test_every_process_draws_its_own_nonce_even_on_a_rolled_back_state(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "live.sqlite"
            first = LiveState(path)
            nonce = first.nonce
            first.close()
            again = LiveState(path)                           # the same file: a restart, or a checkpoint restored
            self.assertNotEqual(again.nonce, nonce)
            self.assertIsNone(again.get("nonce"), "never stored with the rows it would repeat")
            again.close()


if __name__ == "__main__":
    unittest.main()
