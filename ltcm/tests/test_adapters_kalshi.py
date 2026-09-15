"""The Kalshi adapter: the signed call shape, cents on the wire, dollars everywhere else."""

import base64
import unittest
from decimal import Decimal

from ltcm.broker import Instrument, OrderIntent, RejectedOrder, UnknownOutcome, VenueUnavailable
from ltcm.data import TransportError
from ltcm.data.kalshi import BASE
from ltcm.adapters import KalshiCredentials
from ltcm.adapters.kalshi import (
    CAPABILITIES,
    ORDERS_PATH,
    ORDERS_PATH_V2,
    PREFIX,
    KalshiBroker,
    contract_side,
    whole_contracts,
)
from ltcm.tests.fakes import Clock, FakeSigner, FakeTransport

TICKER = "KXCPI-26SEP-T3.0"
YES = Instrument("event", "CPI", "kalshi", market_id=TICKER)
NO = Instrument("event", "CPI", "kalshi", market_id=TICKER, right="no")

NOW = "2026-09-15T14:00:00Z"
MILLIS = "1789480800000"  # 2026-09-15T14:00:00Z in milliseconds

BALANCE = {"balance": 250000, "portfolio_value": 312500, "updated_ts": 1789480800}

POSITIONS = {
    "market_positions": [
        {
            "ticker": TICKER,
            "position": 25,
            "market_exposure": 1000,
            "realized_pnl": 0,
            "total_traded": 1000,
            "fees_paid": 17,
        },
        {"ticker": "KXOTHER", "position": 0, "market_exposure": 0},
    ],
    "event_positions": [],
}

ORDER = {
    "order": {
        "order_id": "8ac1b2cd-0000-4000-8000-000000000001",
        "client_order_id": "oi-" + "b" * 32,
        "ticker": TICKER,
        "status": "resting",
        "action": "buy",
        "side": "yes",
        "type": "limit",
        "yes_price": 40,
        "no_price": 60,
        "initial_count": 10,
        "fill_count": 0,
        "remaining_count": 10,
        "taker_fees": 0,
        "created_time": NOW,
    }
}

ORDERS_PAGE = {"orders": [ORDER["order"]], "cursor": ""}

FILLS = {
    "fills": [
        {
            "trade_id": "t-1",
            "order_id": "8ac1b2cd-0000-4000-8000-000000000001",
            "ticker": TICKER,
            "side": "yes",
            "action": "buy",
            "count": 10,
            "yes_price": 40,
            "no_price": 60,
            "is_taker": True,
            "fee_cost": "0.17",
            "created_time": "2026-09-15T14:00:01Z",
        }
    ],
    "cursor": "",
}


def make(routes=None, **kwargs):
    kwargs.setdefault("order_api", "legacy")  # most fixtures below describe the legacy shape
    transport = FakeTransport(routes or {})
    signer = FakeSigner()
    credentials = KalshiCredentials("2c3d4e5f-0000-4000-8000-000000000009", signer)
    client = KalshiBroker(credentials, transport=transport, clock=Clock(NOW), **kwargs)
    return client, transport, signer


def intent(instrument=YES, **kwargs):
    kwargs.setdefault("rationale", "test")
    kwargs.setdefault("created_at", NOW)
    kwargs.setdefault("quantity", "10")
    kwargs.setdefault("side", "buy")
    return OrderIntent.new(desk_id="desk-1", instrument=instrument, **kwargs)


class SigningTests(unittest.TestCase):
    def test_the_signature_covers_timestamp_method_and_the_prefixed_path(self):
        client, transport, signer = make({BASE + "/portfolio/balance": BALANCE})
        client.balance()
        self.assertEqual(signer.last_message, MILLIS + "GET" + "/trade-api/v2/portfolio/balance")
        headers = transport.last["headers"]
        self.assertEqual(headers["KALSHI-ACCESS-KEY"], "2c3d4e5f-0000-4000-8000-000000000009")
        self.assertEqual(headers["KALSHI-ACCESS-TIMESTAMP"], MILLIS)
        self.assertEqual(
            headers["KALSHI-ACCESS-SIGNATURE"], base64.b64encode(b"woods-signature").decode()
        )

    def test_the_timestamp_is_milliseconds(self):
        client, _, _ = make({BASE + "/portfolio/balance": BALANCE})
        self.assertEqual(client.timestamp_ms(), MILLIS)
        self.assertEqual(len(client.timestamp_ms()), 13)

    def test_the_query_string_is_never_signed(self):
        client, transport, signer = make({BASE + "/portfolio/positions*": POSITIONS})
        client.positions()
        self.assertEqual(signer.last_message, MILLIS + "GET" + PREFIX + "/portfolio/positions")
        self.assertIn("limit=1000", transport.last["url"], "the query is sent but not signed")

    def test_the_path_carries_the_trade_api_prefix(self):
        client, transport, _ = make({BASE + "/portfolio/balance": BALANCE})
        client.balance()
        self.assertTrue(transport.last["path"].startswith("/trade-api/v2/"))
        self.assertTrue(transport.last["url"].startswith("https://api.elections.kalshi.com/"))

    def test_credentials_require_a_signer_and_never_print_one(self):
        with self.assertRaises(ValueError):
            KalshiCredentials("id", object())
        credentials = KalshiCredentials("2c3d-secret-looking-id", FakeSigner())
        self.assertNotIn("secret-looking", repr(credentials))


class MoneyTests(unittest.TestCase):
    def test_balance_cents_become_dollars(self):
        client, _, _ = make({BASE + "/portfolio/balance": BALANCE})
        balance = client.balance()
        self.assertEqual(balance.cash, Decimal("2500"))
        self.assertEqual(balance.equity, Decimal("3125"))
        self.assertEqual(balance.buying_power, Decimal("2500"))
        self.assertEqual(balance.as_of, NOW)

    def test_the_fixed_point_dollar_fields_win_when_present(self):
        client, _, _ = make(
            {BASE + "/portfolio/balance": {"balance": 250000, "balance_dollars": "2500.2500"}}
        )
        self.assertEqual(client.balance().cash, Decimal("2500.2500"))

    def test_positions_average_cost_is_exposure_over_contracts(self):
        client, _, _ = make({BASE + "/portfolio/positions*": POSITIONS})
        positions = client.positions()
        self.assertEqual(len(positions), 1, "a flat market is not a position")
        self.assertEqual(positions[0].quantity, Decimal("25"))
        self.assertEqual(positions[0].instrument.market_id, TICKER)
        self.assertEqual(positions[0].average_cost, Decimal("10") / Decimal("25"))

    def test_a_missing_balance_field_is_venue_unavailable(self):
        client, _, _ = make({BASE + "/portfolio/balance": {"updated_ts": 1}})
        with self.assertRaises(VenueUnavailable):
            client.balance()


class ContractTests(unittest.TestCase):
    def test_the_contract_side_defaults_to_yes(self):
        self.assertEqual(contract_side(YES), "yes")
        self.assertEqual(contract_side(NO), "no")
        with self.assertRaises(RejectedOrder):
            contract_side(Instrument("event", "X", "kalshi", market_id="T", right="maybe"))

    def test_contracts_are_whole(self):
        self.assertEqual(whole_contracts(Decimal("10")), 10)
        with self.assertRaises(RejectedOrder):
            whole_contracts(Decimal("1.5"))
        with self.assertRaises(RejectedOrder):
            whole_contracts(Decimal("0"))

    def test_capabilities(self):
        client, _, _ = make()
        self.assertEqual(client.capabilities(), CAPABILITIES)
        self.assertIn("event", client.capabilities())


class SubmitTests(unittest.TestCase):
    def test_the_legacy_body_prices_in_integer_cents(self):
        client, transport, _ = make({("POST", BASE + ORDERS_PATH): ORDER})
        proposal = intent(order_type="limit", limit_price="0.40", time_in_force="gtc")
        order = client.submit(proposal)
        self.assertEqual(
            transport.last["body"],
            {
                "ticker": TICKER,
                "action": "buy",
                "side": "yes",
                "count": 10,
                "type": "limit",
                "yes_price": 40,
                "client_order_id": proposal.id,
            },
        )
        self.assertEqual(transport.last["path"], PREFIX + ORDERS_PATH)
        self.assertEqual(order.broker_order_id, "8ac1b2cd-0000-4000-8000-000000000001")
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order.limit_price, Decimal("0.40"))

    def test_a_no_side_order_prices_the_no_leg(self):
        client, transport, _ = make({("POST", BASE + ORDERS_PATH): ORDER})
        client.submit(intent(NO, order_type="limit", limit_price="0.60", time_in_force="gtc"))
        self.assertEqual(transport.last["body"]["side"], "no")
        self.assertEqual(transport.last["body"]["no_price"], 60)
        self.assertNotIn("yes_price", transport.last["body"])

    def test_a_market_buy_declares_its_worst_case_cost(self):
        client, transport, _ = make({("POST", BASE + ORDERS_PATH): ORDER})
        client.submit(intent())
        body = transport.last["body"]
        self.assertEqual(body["type"], "market")
        self.assertEqual(body["buy_max_cost"], 1000, "10 contracts can never cost more than $10")
        self.assertNotIn("yes_price", body)

    def test_a_sub_cent_limit_is_refused_before_any_request(self):
        client, transport, _ = make({("POST", BASE + ORDERS_PATH): ORDER})
        with self.assertRaises(Exception):
            client.submit(intent(order_type="limit", limit_price="0.4050", time_in_force="gtc"))
        self.assertEqual(transport.calls, [])

    def test_only_event_contracts_are_accepted(self):
        client, transport, _ = make()
        with self.assertRaises(RejectedOrder):
            client.submit(intent(Instrument("equity", "AAPL", "kalshi")))
        self.assertEqual(transport.calls, [])

    def test_the_v2_body_uses_book_sides_and_dollar_strings(self):
        client, transport, _ = make({("POST", BASE + ORDERS_PATH_V2): {"order_id": "x", "remaining_count": "10"}}, order_api="v2")
        client.submit(intent(order_type="limit", limit_price="0.40", time_in_force="gtc"))
        body = transport.last["body"]
        self.assertEqual(transport.last["path"], PREFIX + ORDERS_PATH_V2)
        self.assertEqual(body["side"], "bid")
        self.assertEqual(body["price"], "0.4000")
        self.assertEqual(body["count"], "10.00")
        self.assertEqual(body["time_in_force"], "good_till_canceled")
        self.assertEqual(body["self_trade_prevention_type"], "taker_at_cross")
        self.assertNotIn("action", body)

    def test_an_unknown_order_api_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            make(order_api="v3")


class UnknownOutcomeTests(unittest.TestCase):
    def test_a_lost_post_that_cannot_be_confirmed_is_unknown(self):
        client, transport, _ = make(
            {
                ("POST", BASE + ORDERS_PATH): TransportError("timed out"),
                BASE + ORDERS_PATH + "*": {"orders": []},
            }
        )
        with self.assertRaises(UnknownOutcome):
            client.submit(intent(order_type="limit", limit_price="0.40", time_in_force="gtc"))
        posts = [call for call in transport.calls if call["method"] == "POST"]
        self.assertEqual(len(posts), 1, "a lost write is never retried")

    def test_a_lost_post_the_venue_did_receive_is_found_by_client_order_id(self):
        proposal = intent(order_type="limit", limit_price="0.40", time_in_force="gtc")
        resting = dict(ORDER["order"], client_order_id=proposal.id)
        client, _, _ = make(
            {
                ("POST", BASE + ORDERS_PATH): TransportError("timed out"),
                BASE + ORDERS_PATH + "*": {"orders": [resting]},
            }
        )
        order = client.submit(proposal)
        self.assertEqual(order.intent_id, proposal.id)
        self.assertEqual(order.status, "accepted")


class OrderTests(unittest.TestCase):
    def test_open_orders_asks_for_resting(self):
        client, transport, _ = make({BASE + ORDERS_PATH + "*": ORDERS_PAGE})
        orders = client.open_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(transport.last["query"]["status"], "resting")
        self.assertEqual(orders[0].quantity, Decimal("10"))
        self.assertEqual(orders[0].limit_price, Decimal("0.40"))
        self.assertEqual(orders[0].side, "buy")

    def test_cancel_deletes_by_the_venue_order_id(self):
        client, transport, _ = make(
            {
                BASE + ORDERS_PATH + "*": ORDERS_PAGE,
                ("DELETE", BASE + ORDERS_PATH + "/8ac1b2cd-0000-4000-8000-000000000001"): (200, {}, b"{}"),
            }
        )
        order = client.cancel("ord-" + "b" * 32)
        self.assertEqual(order.status, "cancelled")
        deletes = [call for call in transport.calls if call["method"] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertTrue(deletes[0]["path"].endswith("8ac1b2cd-0000-4000-8000-000000000001"))

    def test_fills_convert_cents_to_dollars_and_keep_the_fee(self):
        client, transport, _ = make({BASE + "/portfolio/fills*": FILLS})
        fills = client.fills(since="2026-09-15T00:00:00Z")
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.price, Decimal("0.40"))
        self.assertEqual(fill.quantity, Decimal("10"))
        self.assertEqual(fill.fee, Decimal("0.17"))
        self.assertEqual(fill.side, "buy")
        self.assertEqual(fill.instrument.market_id, TICKER)
        self.assertEqual(transport.last["query"]["min_ts"], "1789430400")

    def test_a_fixed_point_fill_row_parses_too(self):
        modern = {
            "fills": [
                {
                    "fill_id": "f-2",
                    "order_id": "o-2",
                    "ticker": TICKER,
                    "outcome_side": "yes",
                    "book_side": "ask",
                    "count_fp": "5.00",
                    "yes_price_dollars": "0.4250",
                    "fee_cost": "0.09",
                    "created_time": "2026-09-15T15:00:00Z",
                }
            ]
        }
        client, _, _ = make({BASE + "/portfolio/fills*": modern})
        fill = client.fills()[0]
        self.assertEqual(fill.price, Decimal("0.4250"))
        self.assertEqual(fill.quantity, Decimal("5.00"))
        self.assertEqual(fill.side, "sell", "an ask on the book is a sell")

    def test_quotes_come_from_the_public_market_data_with_no_signature(self):
        market = {"market": {"ticker": TICKER, "yes_bid": 38, "yes_ask": 41, "last_price": 40}}
        client, transport, signer = make({BASE + f"/markets/{TICKER}": market})
        quote = client.quote(YES)
        self.assertEqual(quote.bid, Decimal("0.38"))
        self.assertEqual(quote.ask, Decimal("0.41"))
        self.assertEqual(signer.messages, [], "public market data is never signed")
        self.assertNotIn("KALSHI-ACCESS-KEY", transport.last["headers"])


if __name__ == "__main__":
    unittest.main()


class V2DefaultTests(unittest.TestCase):
    """The v2 event-order surface is the default since the legacy mutations were retired."""

    def make_v2(self, routes=None, **kwargs):
        from decimal import Decimal as D
        from ltcm.broker import Quote

        class MarketData:
            def quote(self, instrument):
                return Quote(instrument, D("0.41"), D("0.44"), D("0.42"), NOW, "kalshi", delayed=False)

        kwargs.setdefault("order_api", "v2")
        kwargs.setdefault("market_data", MarketData())
        return make(routes, **kwargs)

    def test_default_order_api_is_v2(self):
        transport = FakeTransport({})
        client = KalshiBroker(KalshiCredentials("2c3d4e5f-0000-4000-8000-000000000009", FakeSigner()), transport=transport, clock=Clock(NOW))
        self.assertEqual(client.order_api, "v2")

    def test_a_market_buy_becomes_an_ioc_limit_at_the_ask(self):
        client, transport, _ = self.make_v2({("POST", BASE + ORDERS_PATH_V2): {"order_id": "k1", "client_order_id": "x", "fill_count": "10.00", "remaining_count": "0.00", "average_fill_price": "0.4400"}})
        order = client.submit(intent(order_type="market", quantity="10"))
        body = transport.last["body"]
        self.assertEqual(body["price"], "0.4400")
        self.assertEqual(body["time_in_force"], "immediate_or_cancel")
        self.assertEqual(body["count"], "10.00")
        self.assertEqual(order.status, "filled")
        self.assertEqual(str(order.filled_quantity), "10.00")
        self.assertEqual(order.broker_order_id, "k1")

    def test_a_market_sell_crosses_the_bid_and_reduces_only(self):
        client, transport, _ = self.make_v2({("POST", BASE + ORDERS_PATH_V2): {"order_id": "k2", "remaining_count": "10.00", "fill_count": "0.00"}})
        order = client.submit(intent(side="sell", order_type="market", quantity="10"))
        body = transport.last["body"]
        self.assertEqual(body["side"], "ask")
        self.assertEqual(body["price"], "0.4100")
        self.assertTrue(body["reduce_only"])
        self.assertEqual(order.status, "accepted")

    def test_the_no_leg_is_refused_on_v2(self):
        client, transport, _ = self.make_v2()
        no_leg = Instrument("event", YES.symbol, "kalshi", market_id=YES.market_id, right="no")
        with self.assertRaises(RejectedOrder):
            client.submit(intent(instrument=no_leg, order_type="limit", limit_price="0.40"))
        self.assertEqual(transport.calls, [])

    def test_prices_outside_the_book_are_refused(self):
        client, transport, _ = self.make_v2()
        with self.assertRaises(RejectedOrder):
            client.submit(intent(order_type="limit", limit_price="1.00"))
        self.assertEqual(transport.calls, [])
