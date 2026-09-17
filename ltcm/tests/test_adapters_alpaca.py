"""The Alpaca adapter: request shapes, string-typed money, status mapping, UnknownOutcome."""

import unittest
from decimal import Decimal

from ltcm.broker import Instrument, OrderIntent, RejectedOrder, UnknownOutcome, VenueUnavailable
from ltcm.data import TransportError
from ltcm.adapters import AlpacaCredentials
from ltcm.adapters.alpaca import (
    DATA_BASE,
    LIVE_BASE,
    PAPER_BASE,
    STATUS_MAP,
    AlpacaBroker,
    alpaca_symbol,
    instrument_for,
)
from ltcm.tests.fakes import FakeTransport

AAPL = Instrument("equity", "AAPL", "alpaca")
BTC = Instrument("crypto", "BTC-USD", "alpaca", market_id="BTC-USD")
CALL = Instrument(
    "option", "AAPL", "alpaca", multiplier="100", expiry="2026-10-16", strike="200", right="call"
)

ACCOUNT = {
    "id": "904837e3-3b76-47ec-b432-046db621571b",
    "account_number": "PA3ABCDEFG",
    "status": "ACTIVE",
    "currency": "USD",
    "cash": "103544.02",
    "equity": "155444.89",
    "buying_power": "207088.04",
    "portfolio_value": "155444.89",
    "balance_asof": "2026-09-15",
    "created_at": "2026-01-02T12:00:00Z",
}

POSITIONS = [
    {
        "asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
        "symbol": "AAPL",
        "asset_class": "us_equity",
        "qty": "50",
        "avg_entry_price": "198.22",
        "side": "long",
        "market_value": "11700.00",
        "current_price": "234.00",
        "qty_available": "50",
    },
    {
        "symbol": "TSLA",
        "asset_class": "us_equity",
        "qty": "10",
        "avg_entry_price": "300.00",
        "side": "short",
        "current_price": "280.00",
    },
    {"symbol": "ZERO", "asset_class": "us_equity", "qty": "0", "avg_entry_price": "1"},
]

ORDER = {
    "id": "61e69015-8549-4bfd-b9c3-01e75843f47d",
    "client_order_id": "oi-" + "a" * 32,
    "created_at": "2026-09-15T14:00:00Z",
    "submitted_at": "2026-09-15T14:00:00Z",
    "updated_at": "2026-09-15T14:00:01Z",
    "symbol": "AAPL",
    "asset_class": "us_equity",
    "qty": "10",
    "filled_qty": "0",
    "filled_avg_price": None,
    "order_class": "simple",
    "type": "limit",
    "side": "buy",
    "time_in_force": "day",
    "limit_price": "230.50",
    "status": "new",
}

FILLS = [
    {
        "id": "20260915140001000::c2b1e9a0-0000-0000-0000-000000000001",
        "activity_type": "FILL",
        "transaction_time": "2026-09-15T14:00:01Z",
        "type": "fill",
        "price": "234.07",
        "qty": "10",
        "side": "buy",
        "symbol": "AAPL",
        "leaves_qty": "0",
        "order_id": "61e69015-8549-4bfd-b9c3-01e75843f47d",
        "cum_qty": "10",
        "order_status": "filled",
    }
]


def broker(routes=None, *, paper=True):
    transport = FakeTransport(routes or {})
    credentials = AlpacaCredentials("PKTESTKEYID", "supersecretvalue", paper=paper)
    return AlpacaBroker(credentials, transport=transport), transport


def intent(instrument=AAPL, **kwargs):
    kwargs.setdefault("rationale", "test")
    kwargs.setdefault("created_at", "2026-09-15T14:00:00Z")
    kwargs.setdefault("quantity", "10")
    kwargs.setdefault("side", "buy")
    return OrderIntent.new(desk_id="desk-1", instrument=instrument, **kwargs)


class CredentialTests(unittest.TestCase):
    def test_the_secret_never_appears_in_a_repr(self):
        credentials = AlpacaCredentials("PKTESTKEYID", "supersecretvalue")
        for rendered in (repr(credentials), str(credentials), f"{credentials}"):
            self.assertNotIn("supersecretvalue", rendered)
            self.assertNotIn("PKTESTKEYID", rendered)
            self.assertIn("redacted", rendered)

    def test_headers_carry_both_keys(self):
        headers = AlpacaCredentials("id", "secret").headers()
        self.assertEqual(headers["APCA-API-KEY-ID"], "id")
        self.assertEqual(headers["APCA-API-SECRET-KEY"], "secret")

    def test_empty_credentials_are_refused(self):
        with self.assertRaises(ValueError):
            AlpacaCredentials("", "secret")
        with self.assertRaises(ValueError):
            AlpacaCredentials("id", "")

    def test_paper_and_live_base_urls(self):
        paper, _ = broker(paper=True)
        live, _ = broker(paper=False)
        self.assertEqual(paper.base, PAPER_BASE)
        self.assertEqual(live.base, LIVE_BASE)
        self.assertIn("paper", paper.capabilities())
        self.assertNotIn("paper", live.capabilities())


class SymbolTests(unittest.TestCase):
    def test_equity_crypto_and_occ_option_symbols(self):
        self.assertEqual(alpaca_symbol(AAPL), "AAPL")
        self.assertEqual(alpaca_symbol(BTC), "BTC/USD")
        self.assertEqual(alpaca_symbol(Instrument("crypto", "ETH", "alpaca")), "ETH/USD")
        self.assertEqual(alpaca_symbol(CALL), "AAPL261016C00200000")

    def test_option_symbols_round_trip(self):
        rebuilt = instrument_for({"symbol": "AAPL261016C00200000", "asset_class": "us_option"})
        self.assertEqual(rebuilt.expiry, "2026-10-16")
        self.assertEqual(rebuilt.strike, Decimal("200"))
        self.assertEqual(rebuilt.right, "call")
        self.assertEqual(rebuilt.multiplier, Decimal("100"))

    def test_a_malformed_option_expiry_is_refused(self):
        bad = Instrument("option", "AAPL", "alpaca", expiry="2026-10-1", strike="200", right="put")
        with self.assertRaises(RejectedOrder):
            alpaca_symbol(bad)


class AccountTests(unittest.TestCase):
    def test_balance_parses_string_money(self):
        client, transport = broker({PAPER_BASE + "/v2/account": ACCOUNT})
        balance = client.balance()
        self.assertEqual(balance.cash, Decimal("103544.02"))
        self.assertEqual(balance.equity, Decimal("155444.89"))
        self.assertEqual(balance.buying_power, Decimal("207088.04"))
        self.assertEqual(balance.venue, "alpaca")
        self.assertEqual(balance.as_of, "2026-09-15T00:00:00Z")
        self.assertEqual(transport.last["headers"]["APCA-API-KEY-ID"], "PKTESTKEYID")

    def test_positions_sign_shorts_and_skip_flat_rows(self):
        client, _ = broker({PAPER_BASE + "/v2/positions": POSITIONS})
        positions = client.positions()
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0].quantity, Decimal("50"))
        self.assertEqual(positions[0].mark, Decimal("234.00"))
        self.assertEqual(positions[0].average_cost, Decimal("198.22"))
        self.assertEqual(positions[1].quantity, Decimal("-10"), "a short qty is negative")
        self.assertEqual(positions[1].unrealized_pnl, Decimal("200.00"))

    def test_an_auth_failure_is_venue_unavailable_not_a_rejection(self):
        client, _ = broker({PAPER_BASE + "/v2/account": (403, {}, b'{"message": "forbidden"}')})
        with self.assertRaises(VenueUnavailable):
            client.balance()

    def test_a_server_error_is_venue_unavailable(self):
        client, _ = broker({PAPER_BASE + "/v2/account": (503, {}, b"busy")})
        with self.assertRaises(VenueUnavailable):
            client.balance()


class QuoteTests(unittest.TestCase):
    def test_equity_quote_reads_the_singular_wrapper_from_the_iex_feed(self):
        payload = {
            "symbol": "AAPL",
            "quote": {"t": "2026-09-15T14:00:00.055031265Z", "bp": 233.98, "bs": 2, "ap": 234.02, "as": 1},
            "currency": "USD",
        }
        client, transport = broker({DATA_BASE + "/v2/stocks/AAPL/quotes/latest*": payload})
        quote = client.quote(AAPL)
        self.assertEqual(quote.bid, Decimal("233.98"))
        self.assertEqual(quote.ask, Decimal("234.02"))
        self.assertEqual(quote.source, "alpaca:iex")
        self.assertFalse(quote.delayed)
        self.assertEqual(transport.last["query"]["feed"], "iex")
        self.assertEqual(quote.as_of, "2026-09-15T14:00:00Z")

    def test_crypto_quote_reads_the_symbol_keyed_map(self):
        payload = {"quotes": {"BTC/USD": {"ap": 64130.1, "as": 3.25, "bp": 64123.45, "bs": 0.35, "t": "2026-09-15T14:00:00Z"}}}
        client, transport = broker({DATA_BASE + "/v1beta3/crypto/us/latest/quotes*": payload})
        quote = client.quote(BTC)
        self.assertEqual(quote.bid, Decimal("64123.45"))
        self.assertEqual(quote.ask, Decimal("64130.1"))
        self.assertEqual(quote.source, "alpaca:crypto")
        self.assertEqual(transport.last["query"]["symbols"], "BTC/USD")

    def test_a_missing_quote_is_venue_unavailable(self):
        client, _ = broker({DATA_BASE + "/v2/stocks/AAPL/quotes/latest*": {"symbol": "AAPL"}})
        with self.assertRaises(VenueUnavailable):
            client.quote(AAPL)


class SubmitTests(unittest.TestCase):
    def test_the_request_body_is_exactly_what_alpaca_expects(self):
        client, transport = broker({("POST", PAPER_BASE + "/v2/orders"): ORDER})
        proposal = intent(order_type="limit", limit_price="230.50", time_in_force="day")
        order = client.submit(proposal)
        sent = transport.last
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["path"], "/v2/orders")
        self.assertEqual(
            sent["body"],
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": "230.50",
                "client_order_id": proposal.id,
            },
        )
        self.assertNotIn("notional", sent["body"])
        self.assertEqual(sent["headers"]["Content-Type"], "application/json")
        self.assertEqual(order.broker_order_id, ORDER["id"])
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order.intent_id, ORDER["client_order_id"])
        self.assertEqual(order.desk_id, "desk-1")

    def test_a_market_order_carries_no_limit_price(self):
        client, transport = broker({("POST", PAPER_BASE + "/v2/orders"): ORDER})
        client.submit(intent())
        self.assertNotIn("limit_price", transport.last["body"])
        self.assertEqual(transport.last["body"]["type"], "market")

    def test_the_client_order_id_is_the_intent_id_and_fits_the_limit(self):
        proposal = intent()
        self.assertTrue(proposal.id.startswith("oi-"))
        self.assertLessEqual(len(proposal.id), 128)

    def test_an_expiring_entry_is_refused_before_anything_is_sent(self):
        # Alpaca has no good-till-date order; sent as plain gtc it would outlive its expiry.
        client, transport = broker({("POST", PAPER_BASE + "/v2/orders"): ORDER})
        with self.assertRaises(RejectedOrder):
            client.submit(intent(order_type="limit", limit_price="230.50", time_in_force="gtc", expires_at="2026-09-15T15:00:00Z"))
        self.assertEqual(transport.calls, [])

    def test_a_venue_rejection_raises_rejected_order(self):
        client, _ = broker(
            {("POST", PAPER_BASE + "/v2/orders"): (422, {}, b'{"message": "insufficient buying power"}')}
        )
        with self.assertRaises(RejectedOrder) as caught:
            client.submit(intent())
        self.assertIn("insufficient buying power", str(caught.exception))


class UnknownOutcomeTests(unittest.TestCase):
    def test_a_lost_post_that_cannot_be_confirmed_is_unknown_not_a_retry(self):
        client, transport = broker(
            {
                ("POST", PAPER_BASE + "/v2/orders"): TransportError("timed out"),
                PAPER_BASE + "/v2/orders:by_client_order_id*": (404, {}, b'{"message": "order not found"}'),
            }
        )
        with self.assertRaises(UnknownOutcome) as caught:
            client.submit(intent())
        self.assertIn("reconcile", str(caught.exception))
        posts = [call for call in transport.calls if call["method"] == "POST"]
        self.assertEqual(len(posts), 1, "a lost write is never retried")

    def test_a_lost_post_the_venue_did_receive_returns_that_order(self):
        proposal = intent()
        accepted = dict(ORDER, client_order_id=proposal.id, status="accepted")
        client, transport = broker(
            {
                ("POST", PAPER_BASE + "/v2/orders"): TransportError("timed out"),
                PAPER_BASE + "/v2/orders:by_client_order_id*": accepted,
            }
        )
        order = client.submit(proposal)
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order.broker_order_id, ORDER["id"])
        self.assertEqual(transport.last["query"]["client_order_id"], proposal.id)
        self.assertIn("/v2/orders:by_client_order_id", transport.last["path"])

    def test_a_lookup_that_also_fails_is_still_unknown(self):
        client, _ = broker(
            {
                ("POST", PAPER_BASE + "/v2/orders"): TransportError("timed out"),
                PAPER_BASE + "/v2/orders:by_client_order_id*": TransportError("still down"),
            }
        )
        with self.assertRaises(UnknownOutcome):
            client.submit(intent())

    def test_an_unreadable_success_body_is_unknown(self):
        client, _ = broker({("POST", PAPER_BASE + "/v2/orders"): (200, {}, b"")})
        with self.assertRaises(UnknownOutcome):
            client.submit(intent())


class OrderLifecycleTests(unittest.TestCase):
    def test_status_map_covers_every_alpaca_state_the_docs_list(self):
        for state in (
            "new", "partially_filled", "filled", "done_for_day", "canceled", "expired",
            "replaced", "pending_cancel", "pending_replace", "accepted", "pending_new",
            "accepted_for_bidding", "stopped", "rejected", "suspended", "calculated", "held",
        ):
            self.assertIn(state, STATUS_MAP, state)
        self.assertEqual(STATUS_MAP["canceled"], "cancelled")
        self.assertEqual(STATUS_MAP["done_for_day"], "expired")

    def test_get_order_by_our_id_looks_up_the_client_order_id(self):
        client, transport = broker({PAPER_BASE + "/v2/orders:by_client_order_id*": ORDER})
        order = client.get_order("ord-" + "a" * 32)
        self.assertEqual(transport.last["query"]["client_order_id"], "oi-" + "a" * 32)
        self.assertEqual(order.limit_price, Decimal("230.50"))
        self.assertEqual(order.quantity, Decimal("10"))

    def test_open_orders_asks_for_the_open_status(self):
        client, transport = broker({PAPER_BASE + "/v2/orders*": [ORDER]})
        orders = client.open_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(transport.last["query"]["status"], "open")

    def test_cancel_sends_a_delete_and_rereads_the_order(self):
        cancelled = dict(ORDER, status="canceled")
        calls = {"n": 0}

        def lookup(method, url, body):
            calls["n"] += 1
            return ORDER if calls["n"] == 1 else cancelled

        client, transport = broker(
            {
                PAPER_BASE + "/v2/orders:by_client_order_id*": lookup,
                ("DELETE", PAPER_BASE + "/v2/orders/" + ORDER["id"]): (204, {}, b""),
            }
        )
        order = client.cancel("ord-" + "a" * 32)
        self.assertEqual(order.status, "cancelled")
        deletes = [call for call in transport.calls if call["method"] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        self.assertTrue(deletes[0]["path"].endswith(ORDER["id"]))

    def test_fills_map_the_activity_rows(self):
        client, transport = broker({PAPER_BASE + "/v2/account/activities/FILL*": FILLS})
        fills = client.fills(since="2026-09-15T00:00:00Z")
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.quantity, Decimal("10"))
        self.assertEqual(fill.price, Decimal("234.07"))
        self.assertEqual(fill.side, "buy")
        self.assertEqual(fill.instrument.symbol, "AAPL")
        self.assertEqual(fill.at, "2026-09-15T14:00:01Z")
        self.assertEqual(transport.last["query"]["after"], "2026-09-15T00:00:00Z")
        self.assertEqual(transport.last["query"]["direction"], "asc")


if __name__ == "__main__":
    unittest.main()
