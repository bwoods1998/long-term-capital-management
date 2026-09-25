"""The Alpaca adapter's level-3 structures (Sept 25, 2026, the options-desk run, Track P).

A book holds a structure as ONE instrument priced at S = net value + collateral K (`league/structures.py`);
the venue holds its legs. These tests pin the translation at the adapter: the multi-leg order sent for
every admitted type, the parent order's legs read back as ONE fill of the held instrument, the FILL
activities of the legs grouped the same way, the structure's touch, and the single-leg exit that buys a
short leg back. Venue answers are in the shapes Alpaca documents: the `POST /v2/orders` 200 response's
multi-leg example (https://docs.alpaca.markets/reference/postorder: parent `order_class: "mleg"`, `qty`
the structures, `legs` each with `ratio_qty`, `qty` = ratio x the parent's qty, `filled_qty`,
`filled_avg_price`, `side`, `symbol`, `status`, `position_intent`; legs carry their own `id`,
https://docs.alpaca.markets/reference/getorderbyorderid-1) and the FILL activity rows the adapter
already reads. What the practice account really answers is recorded at its first order
(`drain_structure_answers`).
"""

import unittest
from decimal import Decimal

from league import structures
from ltcm.adapters import AlpacaCredentials, PURPOSE_HEADER
from ltcm.adapters.alpaca import DATA_BASE, MLEG_TYPES, PAPER_BASE, AlpacaBroker, is_structure, mleg_body, mleg_limit
from ltcm.broker import Instrument, OrderIntent, RejectedOrder, UnknownOutcome
from ltcm.data import TransportError
from ltcm.tests.fakes import FakeTransport

D = Decimal
VENUE = "alpaca-paper"


def occ(strike, right="C", expiry="260928", root="SPY"):
    return f"{root}{expiry}{right}{int(D(str(strike)) * 1000):08d}"


def leg(strike, role, right="C", expiry="260928", ratio=None):
    row = {"occ": occ(strike, right, expiry), "role": role}
    if ratio is not None:
        row["ratio"] = ratio
    return row


#: One of every admitted type, as a strategy writes it.
TYPES = {
    "debit_vertical": [leg(580, "long"), leg(581, "short")],
    "credit_vertical": [leg(581, "long", "P"), leg(582, "short", "P")],
    "iron_condor": [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "long", "C")],
    "iron_butterfly": [leg(584, "long", "P"), leg(585, "short", "P"), leg(585, "short", "C"), leg(586, "long", "C")],
    "long_butterfly": [leg(580, "long"), leg(581, "short", ratio=2), leg(582, "long")],
    "calendar": [leg(585, "short", expiry="260928"), leg(585, "long", expiry="261002")],
    "diagonal": [leg(586, "short", expiry="260928"), leg(585, "long", expiry="261002")],
    "long_straddle": [leg(585, "long", "C"), leg(585, "long", "P")],
    "long_strangle": [leg(587, "long", "C"), leg(583, "long", "P")],
}


def spec(kind):
    return structures.classify(kind, [structures._leg_from(VENUE, row) for row in TYPES[kind]])


def held(kind):
    return structures.instrument(spec(kind), VENUE)


def order_intent(kind="iron_condor", *, side="buy", limit="0.62", quantity="1", **kwargs):
    kwargs.setdefault("purpose", "exit" if side == "sell" else "entry")
    if kwargs["purpose"] == "exit":
        kwargs.setdefault("exit_reason", "desk")
        kwargs.setdefault("exit_of", "in-" + "e" * 32)
    return OrderIntent.new(desk_id="book-alpaca-paper", instrument=held(kind), side=side, quantity=quantity, order_type="limit",
                           limit_price=limit, time_in_force="day", rationale="test", created_at="2026-09-25T14:00:00Z", **kwargs)


def broker(routes=None):
    transport = FakeTransport(routes or {})
    return AlpacaBroker(AlpacaCredentials("PKTESTKEYID", "supersecretvalue", paper=True), transport=transport, venue=VENUE), transport


PARENT = "7a1f0c2e-0000-4000-8000-000000000001"


def leg_row(symbol, *, side, intent, ratio="1", qty="1", filled="0", price=None, status="new", leg_id=None):
    return {"id": leg_id or f"leg-{symbol}", "asset_class": "us_option", "symbol": symbol, "side": side, "position_intent": intent,
            "ratio_qty": ratio, "qty": qty, "filled_qty": filled, "filled_avg_price": price, "status": status, "order_class": "mleg"}


def condor_order(*, status="new", filled=("0", "0", "0", "0"), prices=(None, None, None, None), qty="1", client_order_id=None,
                 opening=True, legs=True, limit="-0.38"):
    """The documented multi-leg answer for a $1-wide SPY iron condor (580/581 puts, 590/591 calls)."""
    symbols = [occ(580, "P"), occ(581, "P"), occ(590, "C"), occ(591, "C")]
    signs = [1, -1, -1, 1]
    rows = []
    for symbol, sign, done, price in zip(symbols, signs, filled, prices):
        if opening:
            side, intent = ("buy", "buy_to_open") if sign > 0 else ("sell", "sell_to_open")
        else:
            side, intent = ("sell", "sell_to_close") if sign > 0 else ("buy", "buy_to_close")
        rows.append(leg_row(symbol, side=side, intent=intent, qty=qty, filled=done, price=price,
                            status="filled" if done == qty else ("partially_filled" if done != "0" else "new")))
    row = {"id": PARENT, "client_order_id": client_order_id or order_intent().id, "asset_class": "", "order_class": "mleg",
           "order_type": "limit", "type": "limit", "qty": qty, "filled_qty": min(filled), "filled_avg_price": None,
           "limit_price": limit, "time_in_force": "day", "status": status, "submitted_at": "2026-09-25T14:00:00Z",
           "updated_at": "2026-09-25T14:00:01Z"}
    if legs:
        row["legs"] = rows
    return row


class TheOrderSent(unittest.TestCase):
    def test_every_type_the_venue_can_close_as_one_order_opens_as_one_at_the_signed_net(self):
        # K and the natural price per type: S = K + net value, and Alpaca's limit is S - K on an open
        # (a debit positive, a credit negative).
        natural = {"debit_vertical": "0.40", "credit_vertical": "0.35", "iron_condor": "0.38", "iron_butterfly": "0.60",
                   "long_butterfly": "0.20"}
        self.assertEqual(sorted(MLEG_TYPES), sorted(natural))
        for kind in natural:
            with self.subTest(kind):
                sp = spec(kind)
                limit = structures.held_limit(sp, "open", natural[kind])
                client, transport = broker({("POST", PAPER_BASE + "/v2/orders"): {**condor_order(), "id": "x"}})
                body = mleg_body(order_intent(kind, limit=str(limit)))
                self.assertEqual(body["order_class"], "mleg")
                self.assertNotIn("symbol", body)
                self.assertNotIn("side", body)
                self.assertEqual((body["type"], body["time_in_force"], body["qty"]), ("limit", "day", "1"))
                expected = D(natural[kind]) if not sp.credit else -D(natural[kind])
                self.assertEqual(D(body["limit_price"]), expected, kind)
                self.assertEqual(len(body["legs"]), len(sp.legs))
                for row, part in zip(body["legs"], sp.legs):
                    self.assertEqual(row["symbol"], part.occ)
                    self.assertEqual(row["ratio_qty"], str(part.ratio))
                    self.assertEqual((row["side"], row["position_intent"]),
                                     ("buy", "buy_to_open") if part.sign > 0 else ("sell", "sell_to_open"))

    def test_a_type_whose_one_order_close_is_uncovered_is_never_opened_here(self):
        """Alpaca refused a calendar's close as one multi-leg order ("mleg uncovered short contracts not
        allowed", https://forum.alpaca.markets/t/16802): its covered check reads sides, and the close of a
        calendar, a diagonal, a straddle or a strangle sells a leg no buy in the order covers. Legging out
        is not allowed, so they are not opened here at all (they trade on the options shadow book)."""
        client, transport = broker({})
        for kind in ("calendar", "diagonal", "long_straddle", "long_strangle"):
            with self.subTest(kind):
                limit = structures.held_limit(spec(kind), "open", "0.90")
                with self.assertRaises(RejectedOrder) as refused:
                    client.submit(order_intent(kind, limit=str(limit)))
                self.assertIn("legging out is not allowed", str(refused.exception))
                closing = mleg_body(order_intent(kind, side="sell", limit=str(limit)))  # a close is sent as it is
                self.assertEqual({r["position_intent"] for r in closing["legs"]} <= {"sell_to_close", "buy_to_close"}, True)
        self.assertEqual(transport.calls, [])
        self.assertEqual(AlpacaBroker.structure_types, MLEG_TYPES)

    def test_the_close_sign_is_the_gateways_a_credit_buy_back_positive_a_debit_sale_negative(self):
        # The House floors its expiry-day close at S = 0.01 (the integrator, Sept 25): a credit structure
        # sold at 0.01 pays at most K - 0.01 to buy it back (positive); a debit one receives at least 0.01.
        self.assertEqual(mleg_body(order_intent("iron_condor", side="sell", limit="0.01"))["limit_price"], "0.99")
        self.assertEqual(mleg_body(order_intent("debit_vertical", side="sell", limit="0.01"))["limit_price"], "-0.01")
        self.assertEqual(mleg_body(order_intent("credit_vertical", side="sell", limit="1.00"))["limit_price"], "0.00")

    def test_a_close_reverses_every_leg_and_the_sign(self):
        body = mleg_body(order_intent("iron_condor", side="sell", limit="0.80"))
        # A credit structure held at 0.80 of its $1 collateral is bought back for at most 0.20: a debit.
        self.assertEqual(body["limit_price"], "0.20")
        self.assertEqual([(r["side"], r["position_intent"]) for r in body["legs"]],
                         # canonical order: 590C (short), 591C (long), 580P (long), 581P (short)
                         [("buy", "buy_to_close"), ("sell", "sell_to_close"), ("sell", "sell_to_close"), ("buy", "buy_to_close")])
        body = mleg_body(order_intent("debit_vertical", side="sell", limit="0.55"))
        self.assertEqual(body["limit_price"], "-0.55")  # a debit structure's close receives: a credit
        self.assertEqual([(r["side"], r["position_intent"]) for r in body["legs"]], [("sell", "sell_to_close"), ("buy", "buy_to_close")])

    def test_the_butterfly_body_keeps_its_ratio_and_the_order_is_whole_structures(self):
        body = mleg_body(order_intent("long_butterfly", limit="0.20", quantity="3"))
        self.assertEqual(body["qty"], "3")
        self.assertEqual([r["ratio_qty"] for r in body["legs"]], ["1", "2", "1"])

    def test_submit_posts_the_body_with_the_purpose_and_reads_the_answer_as_the_held_structure(self):
        intent = order_intent()
        client, transport = broker({("POST", PAPER_BASE + "/v2/orders"): condor_order(client_order_id=intent.id)})
        order = client.submit(intent)
        sent = transport.last
        self.assertEqual(sent["body"], mleg_body(intent))
        self.assertEqual(sent["body"]["client_order_id"], intent.id)
        self.assertEqual(sent["headers"][PURPOSE_HEADER], "entry")
        self.assertEqual(order.instrument, intent.instrument)
        self.assertEqual((order.side, order.status, order.filled_quantity, order.limit_price), ("buy", "accepted", D(0), D("0.62")))
        self.assertEqual(order.broker_order_id, PARENT)

    def test_refused_before_anything_is_sent(self):
        client, transport = broker({})
        with self.assertRaises(RejectedOrder):
            client.submit(OrderIntent.new(desk_id="d", instrument=held("iron_condor"), side="buy", quantity="1", order_type="market",
                                          rationale="t", created_at="2026-09-25T14:00:00Z"))
        with self.assertRaises(RejectedOrder):
            client.submit(order_intent(quantity="1.5"))
        with self.assertRaises(RejectedOrder):
            client.submit(order_intent(limit="0.625"))  # a limit is never moved to the cent
        # A code whose legs were reversed (a debit vertical named as the credit one) is never traded.
        good = held("debit_vertical")
        tampered = Instrument("option", "SPY", VENUE, multiplier="100", expiry=good.expiry, strike=good.strike, right=good.right,
                              market_id=good.market_id.replace("+1", "#").replace("-1", "+1").replace("#", "-1"))
        with self.assertRaises(RejectedOrder):
            client.submit(OrderIntent.new(desk_id="d", instrument=tampered, side="buy", quantity="1", order_type="limit",
                                          limit_price="0.40", rationale="t", created_at="2026-09-25T14:00:00Z"))
        self.assertEqual(transport.calls, [])

    def test_a_venue_refusal_is_a_rejection_and_is_kept_for_the_owner(self):
        client, _ = broker({("POST", PAPER_BASE + "/v2/orders"): (403, {}, b'{"message": "options market orders are only allowed"}')})
        with self.assertRaises(RejectedOrder):
            client.submit(order_intent())
        answers = client.drain_structure_answers()
        self.assertEqual([(a["stage"], a["structure"]) for a in answers], [("refused", "iron_condor")])
        self.assertEqual(answers[0]["detail"]["sent"]["order_class"], "mleg")

    def test_a_lost_write_is_confirmed_by_client_id_and_its_legs_read_nested(self):
        intent = order_intent()
        bare = condor_order(client_order_id=intent.id, legs=False, status="filled")
        nested = condor_order(client_order_id=intent.id, status="filled", filled=("1", "1", "1", "1"),
                              prices=("0.10", "0.30", "0.35", "0.12"))
        client, transport = broker({
            ("POST", PAPER_BASE + "/v2/orders"): TransportError("timed out"),
            PAPER_BASE + "/v2/orders:by_client_order_id*": bare,
            PAPER_BASE + f"/v2/orders/{PARENT}*": nested,
        })
        order = client.submit(intent)
        self.assertEqual([c["query"] for c in transport.calls if c["path"] == f"/v2/orders/{PARENT}"], [{"nested": "true"}])
        self.assertEqual((order.status, order.filled_quantity), ("filled", D(1)))
        self.assertEqual(order.average_price, D(1) + D("0.10") - D("0.30") - D("0.35") + D("0.12"))

    def test_a_lost_write_the_venue_never_saw_is_unknown(self):
        client, _ = broker({("POST", PAPER_BASE + "/v2/orders"): TransportError("timed out"),
                            PAPER_BASE + "/v2/orders:by_client_order_id*": (404, {}, b'{"message": "not found"}')})
        with self.assertRaises(UnknownOutcome):
            client.submit(order_intent())

    def test_the_first_answer_of_each_type_is_kept_once(self):
        intent = order_intent()
        client, _ = broker({("POST", PAPER_BASE + "/v2/orders"): condor_order(client_order_id=intent.id)})
        client.submit(intent)
        client.submit(intent)
        answers = client.drain_structure_answers()
        self.assertEqual([(a["stage"], a["structure"]) for a in answers], [("submit", "iron_condor")])
        self.assertEqual(answers[0]["detail"]["answer"]["legs"][1]["position_intent"], "sell_to_open")
        self.assertNotIn("account_number", str(answers))
        self.assertEqual(client.drain_structure_answers(), [])


class TheOrderRead(unittest.TestCase):
    """The book polls an order through `get_order`: the parent's legs become ONE held fill."""

    PRICES = ("0.10", "0.30", "0.35", "0.12")  # long 580P, short 581P, short 590C, long 591C

    def read(self, row, *, intent=None, client=None):
        client = client or broker({})[0]
        return client.parse_order(row, intent=intent), client

    def test_a_filled_condor_is_one_fill_of_the_held_instrument_at_its_held_price(self):
        intent = order_intent()
        client, _ = broker({PAPER_BASE + "/v2/account/activities/FILL*": []})
        order, client = self.read(condor_order(status="filled", filled=("1",) * 4, prices=self.PRICES), intent=intent, client=client)
        self.assertEqual((order.status, order.filled_quantity, order.side), ("filled", D(1), "buy"))
        # K 1.00 + 0.10 - 0.30 - 0.35 + 0.12 = 0.57: a credit of 0.43 received, $57 at risk.
        self.assertEqual(order.average_price, D("0.57"))
        self.assertEqual(order.instrument, intent.instrument)
        self.assertEqual(order.limit_price, D("0.62"))  # the venue's -0.38 net read back as S
        answers = client.drain_structure_answers()
        self.assertEqual([a["stage"] for a in answers], ["fill"])

    def test_the_first_fill_of_a_type_records_how_the_venue_lists_its_legs_fills(self):
        rows = [activity(occ(580, "P"), "buy", "1", "0.10", "2026-09-25T14:00:01Z", order_id=f"leg-{occ(580, 'P')}"),
                activity(occ(581, "P"), "sell", "1", "0.30", "2026-09-25T14:00:01Z", order_id=f"leg-{occ(581, 'P')}"),
                activity("AAPL", "buy", "1", "234", "2026-09-25T14:00:02Z", order_id="other")]
        client, transport = broker({PAPER_BASE + "/v2/account/activities/FILL*": rows})
        client.parse_order(condor_order(status="filled", filled=("1",) * 4, prices=self.PRICES), intent=order_intent())
        record = [a for a in client.drain_structure_answers() if a["stage"] == "activity"]
        self.assertEqual(len(record), 1)
        self.assertEqual(record[0]["detail"]["order_id_is"], ["leg"])
        self.assertEqual([r["symbol"] for r in record[0]["detail"]["rows"]], [occ(580, "P"), occ(581, "P")])
        self.assertEqual(transport.last["query"]["after"], "2026-09-25T14:00:00Z")
        client.parse_order(condor_order(status="filled", filled=("1",) * 4, prices=self.PRICES), intent=order_intent())
        self.assertEqual(len([c for c in transport.calls if "activities" in c["path"]]), 1)  # once a type

    def test_a_failed_activity_read_never_stops_the_order_being_read(self):
        client, _ = broker({PAPER_BASE + "/v2/account/activities/FILL*": (500, {}, b"down")})
        order = client.parse_order(condor_order(status="filled", filled=("1",) * 4, prices=self.PRICES), intent=order_intent())
        self.assertEqual(order.filled_quantity, D(1))

    def test_a_leg_ahead_of_the_others_is_pending(self):
        order, _ = self.read(condor_order(status="partially_filled", qty="2", filled=("2", "1", "1", "1"),
                                          prices=("0.10", "0.30", "0.35", "0.12")), intent=order_intent(quantity="2"))
        self.assertEqual(order.filled_quantity, D(1))
        self.assertEqual(order.status, "partially_filled")
        self.assertEqual(order._raw["uneven_legs"], {occ(580, "P"): "2"})

    def test_legs_across_two_polls_complete_the_structure(self):
        intent = order_intent(quantity="2")
        first, client = self.read(condor_order(status="partially_filled", qty="2", filled=("1", "1", "1", "0"),
                                               prices=("0.10", "0.30", "0.35", None)), intent=intent)
        self.assertEqual((first.filled_quantity, first.average_price), (D(0), None))
        second, _ = self.read(condor_order(status="filled", qty="2", filled=("2",) * 4, prices=self.PRICES), intent=intent, client=client)
        self.assertEqual((second.status, second.filled_quantity, second.average_price), ("filled", D(2), D("0.57")))

    def test_a_parent_filled_before_its_legs_say_so_is_still_open(self):
        order, _ = self.read(condor_order(status="filled", filled=("1", "1", "1", "0"), prices=("0.10", "0.30", "0.35", None)),
                             intent=order_intent())
        self.assertEqual((order.status, order.filled_quantity), ("accepted", D(0)))

    def test_an_answer_without_legs_books_nothing_yet(self):
        row = condor_order(status="filled", filled=("1",) * 4, legs=False)
        order, _ = self.read(row, intent=order_intent())
        self.assertEqual(order.filled_quantity, D(1))
        self.assertIsNone(order.average_price)  # a book reads "not yet" and asks again

    def test_a_close_read_without_its_legs_is_still_a_sale(self):
        intent = order_intent(side="sell", limit="0.80")
        client = broker({})[0]
        client.parse_order(condor_order(opening=False, limit="0.20"), intent=intent)  # sent: the adapter knows it
        order, _ = self.read(condor_order(opening=False, limit="0.20", legs=False, status="accepted"), client=client)
        self.assertEqual((order.side, order.instrument, order.limit_price), ("sell", intent.instrument, D("0.80")))

    def test_an_order_that_ended_with_uneven_legs_is_an_error(self):
        order, client = self.read(condor_order(status="canceled", qty="2", filled=("2", "2", "1", "1"),
                                               prices=self.PRICES), intent=order_intent(quantity="2"))
        self.assertEqual((order.status, order.filled_quantity), ("cancelled", D(1)))
        self.assertIn("ERROR", order.reason)
        self.assertIn("unevenly", order.reason)
        self.assertIn("uneven", [a["stage"] for a in client.drain_structure_answers()])

    def test_after_a_restart_the_structure_is_read_back_from_its_legs(self):
        for kind in TYPES:
            with self.subTest(kind):
                sp = spec(kind)
                legs = [leg_row(row["symbol"], side=row["side"], intent=row["position_intent"], ratio=row["ratio_qty"],
                                qty=str(int(row["ratio_qty"])), filled=str(int(row["ratio_qty"])), price="1.00", status="filled")
                        for row in structures.mleg_legs(sp, "open")]
                row = {"id": PARENT, "client_order_id": "oi-" + "b" * 32, "order_class": "mleg", "qty": "1", "filled_qty": "1",
                       "status": "filled", "type": "limit", "limit_price": "0.40", "time_in_force": "day", "legs": legs}
                order, _ = self.read(row)
                self.assertEqual(order.instrument, held(kind))
                self.assertEqual(order.side, "buy")
                self.assertEqual(order.filled_quantity, D(1))
                expected = sp.collateral + sum((part.sign * part.ratio * D("1.00") for part in sp.legs), D(0))
                self.assertEqual(order.average_price, expected)

    def test_a_close_read_back_is_a_sale_at_the_held_price(self):
        intent = order_intent(side="sell", limit="0.80")
        prices = ("0.02", "0.05", "0.06", "0.01")  # sold 580P, bought back 581P and 590C, sold 591C
        order, _ = self.read(condor_order(status="filled", filled=("1",) * 4, prices=prices, opening=False, limit="0.20"), intent=intent)
        self.assertEqual((order.side, order.filled_quantity), ("sell", D(1)))
        self.assertEqual(order.average_price, D(1) + D("0.02") - D("0.05") - D("0.06") + D("0.01"))
        self.assertEqual(order.limit_price, D("0.80"))
        # Read after a restart, without the intent, the legs' `*_to_close` say it is a sale.
        again, _ = self.read(condor_order(status="filled", filled=("1",) * 4, prices=prices, opening=False, limit="0.20"))
        self.assertEqual((again.side, again.instrument, again.average_price), ("sell", intent.instrument, order.average_price))

    def test_a_multi_leg_order_that_is_no_admitted_structure_is_never_booked(self):
        legs = [leg_row(occ(580, "P"), side="sell", intent="sell_to_open", filled="1", price="0.30", status="filled")]
        order, _ = self.read({"id": PARENT, "client_order_id": "oi-" + "c" * 32, "order_class": "mleg", "qty": "1", "filled_qty": "1",
                              "status": "filled", "legs": legs})
        self.assertIsNone(order.average_price)
        self.assertIn("cannot name", order.reason)

    def test_get_and_open_orders_ask_for_the_legs_nested(self):
        client, transport = broker({PAPER_BASE + f"/v2/orders/{PARENT}*": condor_order(),
                                    PAPER_BASE + "/v2/orders?*": [condor_order()]})
        client.get_order(PARENT)
        self.assertEqual(transport.last["query"], {"nested": "true"})
        orders = client.open_orders()
        self.assertEqual(transport.last["query"]["nested"], "true")
        self.assertEqual(len(orders), 1)
        self.assertTrue(is_structure(orders[0].instrument))


def activity(symbol, side, qty, price, at, *, order_id=PARENT, n=1):
    return {"id": f"2026092514000{n}000::{symbol}-{n}", "activity_type": "FILL", "transaction_time": at, "type": "fill",
            "price": price, "qty": qty, "side": side, "symbol": symbol, "order_id": order_id, "order_status": "filled",
            "cum_qty": qty, "leaves_qty": "0"}


class TheFillActivities(unittest.TestCase):
    """`fills` reports ONE fill of the held instrument per tranche of whole structures."""

    def known(self, routes=None):
        client, transport = broker(routes or {})
        client.parse_order(condor_order(qty="2"), intent=order_intent(quantity="2"))  # the adapter sent it
        return client, transport

    def batch(self, rows):
        return {PAPER_BASE + "/v2/account/activities/FILL*": rows}

    def legs(self, n, at, *, qty="1", order_ids=None):
        rows = [
            activity(occ(580, "P"), "buy", qty, "0.10", at, n=n),
            activity(occ(581, "P"), "sell", qty, "0.30", at, n=n),
            activity(occ(590, "C"), "sell", qty, "0.35", at, n=n),
            activity(occ(591, "C"), "buy", qty, "0.12", at, n=n),
        ]
        for row, order_id in zip(rows, order_ids or [PARENT] * 4):
            row["order_id"] = order_id
        return rows

    def test_legs_in_one_batch_are_one_fill(self):
        client, transport = self.known()
        transport.route(PAPER_BASE + "/v2/account/activities/FILL*", self.legs(1, "2026-09-25T14:00:01Z", qty="2"))
        fills = client.fills(since="2026-09-25T00:00:00Z")
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual((fill.instrument, fill.side, fill.quantity, fill.price), (held("iron_condor"), "buy", D(2), D("0.57")))
        self.assertEqual((fill.order_id, fill.id), (PARENT, f"{PARENT}:2"))
        # Asked again over the same rows, the same fill under the same id: a reader dedupes by id.
        self.assertEqual([f.id for f in client.fills(since="2026-09-25T00:00:00Z")], [fill.id])

    def test_legs_across_two_polls_and_one_leg_late(self):
        client, transport = self.known()
        rows = self.legs(1, "2026-09-25T14:00:01Z")
        transport.route(PAPER_BASE + "/v2/account/activities/FILL*", rows[:3])
        self.assertEqual(client.fills(), [])  # three legs of four: pending
        transport.route(PAPER_BASE + "/v2/account/activities/FILL*", rows[3:])
        fills = client.fills(since="2026-09-25T14:00:01Z")
        self.assertEqual([(f.quantity, f.price) for f in fills], [(D(1), D("0.57"))])

    def test_two_tranches_price_each_leg_first_in_first_out(self):
        client, transport = self.known()
        first = self.legs(1, "2026-09-25T14:00:01Z")
        second = self.legs(2, "2026-09-25T14:05:00Z")
        second[1]["price"] = "0.40"  # the second short put sold dearer: a larger credit on the second condor
        transport.route(PAPER_BASE + "/v2/account/activities/FILL*", first + second)
        fills = client.fills()
        self.assertEqual([(f.id, f.quantity, f.price) for f in fills],
                         [(f"{PARENT}:1", D(1), D("0.57")), (f"{PARENT}:2", D(1), D("0.47"))])

    def test_a_leg_fill_under_the_legs_own_order_id_is_grouped_too(self):
        client, transport = self.known()
        rows = self.legs(1, "2026-09-25T14:00:01Z", order_ids=[f"leg-{occ(580, 'P')}", f"leg-{occ(581, 'P')}",
                                                                f"leg-{occ(590, 'C')}", f"leg-{occ(591, 'C')}"])
        transport.route(PAPER_BASE + "/v2/account/activities/FILL*", rows)
        fills = client.fills()
        self.assertEqual([(f.instrument, f.quantity) for f in fills], [(held("iron_condor"), D(1))])

    def test_an_order_the_adapter_never_saw_is_asked_about_once(self):
        client, transport = broker({PAPER_BASE + "/v2/account/activities/FILL*": self.legs(1, "2026-09-25T14:00:01Z"),
                                    PAPER_BASE + f"/v2/orders/{PARENT}*": condor_order(status="filled", filled=("1",) * 4,
                                                                                         prices=TheOrderRead.PRICES)})
        fills = client.fills()
        self.assertEqual([(f.instrument, f.quantity, f.price) for f in fills], [(held("iron_condor"), D(1), D("0.57"))])
        lookups = [c for c in transport.calls if c["path"] == f"/v2/orders/{PARENT}"]
        self.assertEqual(len(lookups), 1)
        self.assertEqual(lookups[0]["query"], {"nested": "true"})

    def test_a_single_contract_and_a_stock_are_fills_as_before(self):
        simple = activity(occ(600, "C"), "buy", "1", "1.25", "2026-09-25T14:00:01Z", order_id="simple-1")
        stock = {**activity("AAPL", "buy", "10", "234.07", "2026-09-25T14:00:02Z", order_id="simple-2"), "symbol": "AAPL"}
        client, transport = broker({PAPER_BASE + "/v2/account/activities/FILL*": [simple, stock],
                                    PAPER_BASE + "/v2/orders/simple-1*": {"id": "simple-1", "order_class": "simple", "symbol": simple["symbol"],
                                                                          "qty": "1", "status": "filled"}})
        fills = client.fills()
        self.assertEqual([(f.instrument.symbol, f.instrument.market_id, f.quantity) for f in fills],
                         [("SPY", None, D(1)), ("AAPL", None, D(10))])
        client.fills()
        self.assertEqual(len([c for c in transport.calls if c["path"] == "/v2/orders/simple-1"]), 1)  # remembered as simple


class TheTouch(unittest.TestCase):
    def test_a_structure_is_quoted_from_every_leg_in_one_request(self):
        quotes = {"quotes": {
            occ(580, "P"): {"bp": 0.09, "ap": 0.11, "t": "2026-09-25T14:00:03Z"},
            occ(581, "P"): {"bp": 0.29, "ap": 0.31, "t": "2026-09-25T14:00:01Z"},
            occ(590, "C"): {"bp": 0.34, "ap": 0.36, "t": "2026-09-25T14:00:02Z"},
            occ(591, "C"): {"bp": 0.11, "ap": 0.13, "t": "2026-09-25T14:00:04Z"},
        }}
        client, transport = broker({DATA_BASE + "/v1beta1/options/quotes/latest*": quotes})
        quote = client.quote(held("iron_condor"))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.last["query"]["symbols"].split(","), [occ(590, "C"), occ(591, "C"), occ(580, "P"), occ(581, "P")])
        # bid = 1 + 0.09 - 0.31 - 0.36 + 0.11 = 0.53; ask = 1 + 0.11 - 0.29 - 0.34 + 0.13 = 0.61
        self.assertEqual((quote.bid, quote.ask), (D("0.53"), D("0.61")))
        self.assertEqual(quote.as_of, "2026-09-25T14:00:01Z")  # the oldest leg's
        self.assertEqual(quote.instrument, held("iron_condor"))

    def test_a_leg_without_a_quote_leaves_that_side_empty(self):
        client, _ = broker({DATA_BASE + "/v1beta1/options/quotes/latest*": {"quotes": {
            occ(580, "C"): {"bp": 1.0, "ap": 1.1, "t": "2026-09-25T14:00:03Z"}}}})
        quote = client.quote(held("debit_vertical"))
        self.assertEqual((quote.bid, quote.ask), (None, None))


class SingleContractsUnchanged(unittest.TestCase):
    CALL = Instrument("option", "SPY", VENUE, multiplier="100", expiry="2026-09-28", strike="600", right="call")

    def sent(self, **kwargs):
        client, transport = broker({("POST", PAPER_BASE + "/v2/orders"): {"id": "s", "symbol": occ(600), "asset_class": "us_option",
                                                                           "qty": "1", "status": "new", "order_class": "simple"}})
        kwargs.setdefault("side", "buy")
        client.submit(OrderIntent.new(desk_id="d", instrument=self.CALL, quantity="1", order_type="limit", limit_price="1.00",
                                      rationale="t", created_at="2026-09-25T14:00:00Z", **kwargs))
        return transport.last["body"]

    def test_a_single_contract_opens_by_buying_and_closes_by_selling(self):
        body = self.sent()
        self.assertEqual((body["symbol"], body["position_intent"]), (occ(600), "buy_to_open"))
        self.assertNotIn("order_class", body)
        self.assertEqual(self.sent(side="sell", purpose="exit", exit_reason="desk", exit_of="in-x")["position_intent"], "sell_to_close")

    def test_a_buy_that_is_an_exit_buys_a_short_leg_back(self):
        body = self.sent(purpose="exit", exit_reason="desk", exit_of="in-x")
        self.assertEqual(body["position_intent"], "buy_to_close")

    def test_mleg_limit_is_whole_cents_or_refused(self):
        self.assertEqual(mleg_limit(spec("iron_condor"), D("0.62"), True), D("-0.38"))
        self.assertEqual(mleg_limit(spec("debit_vertical"), D("0.40"), True), D("0.40"))
        with self.assertRaises(RejectedOrder):
            mleg_limit(spec("debit_vertical"), D("0.405"), True)


if __name__ == "__main__":
    unittest.main()
