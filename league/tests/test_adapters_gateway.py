"""Alpaca gateway routing preserves order bodies while keeping venue credentials outside the House."""
import unittest
from decimal import Decimal
from league.adapters import AlpacaCredentials, GatewaySigner, VenueClient, gateway_path, gateway_url_for
from league.adapters.alpaca import AlpacaBroker
from league.broker import Instrument, OrderIntent
from league.tests.broker_fakes import FakeTransport
GATEWAY = "https://ltcm-gateway.workers.dev"
TOKEN = "gateway-token-that-is-long-enough-1234567890"
NOW = "2026-09-15T14:00:00Z"
AAPL = Instrument("equity", "AAPL", "alpaca")
ALPACA_ACCOUNT = {"id": "a-1", "status": "ACTIVE", "currency": "USD", "cash": "500.00",
                  "equity": "500.00", "buying_power": "500.00", "portfolio_value": "500.00"}
ALPACA_ORDER = {"id": "a-o-1", "client_order_id": "oi-" + "c" * 32, "symbol": "AAPL",
                "status": "new", "qty": "2", "filled_qty": "0", "side": "buy",
                "order_type": "limit", "limit_price": "10.00", "submitted_at": NOW}


def intent(instrument, **kwargs):
    kwargs.setdefault("rationale", "test")
    kwargs.setdefault("created_at", NOW)
    kwargs.setdefault("side", "buy")
    return OrderIntent.new(desk_id="desk-1", instrument=instrument, **kwargs)


def alpaca_broker(transport, *, gateway=False):
    if gateway:
        client = VenueClient(
            transport, gateway_url=GATEWAY, gateway=GatewaySigner(TOKEN), venue="alpaca"
        )
        credentials = AlpacaCredentials("gateway", "gateway", paper=False)
    else:
        client = VenueClient(transport)
        credentials = AlpacaCredentials("PKREALKEYID", "real-secret", paper=False)
    return AlpacaBroker(credentials, client=client)


class GatewayUrlTest(unittest.TestCase):
    def test_retired_venues_are_refused_before_any_request(self):
        for venue in ("kalshi", "coinbase", "unknown"):
            with self.assertRaises(ValueError):
                VenueClient(FakeTransport(), gateway_url=GATEWAY, gateway=GatewaySigner(TOKEN), venue=venue)
            with self.assertRaises(ValueError):
                gateway_path(venue, "https://example.com/orders")



    def test_alpacas_two_hosts_map_onto_one_venue_route(self):
        # Trading and market data are different hosts with the same credential; the gateway
        # picks the host from the path, so the floor needs one venue name, not two.
        self.assertEqual(
            gateway_url_for(GATEWAY, "alpaca", "https://api.alpaca.markets/v2/account"),
            GATEWAY + "/v1/alpaca/v2/account",
        )
        self.assertEqual(
            gateway_url_for(GATEWAY, "alpaca", "https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest?feed=iex"),
            GATEWAY + "/v1/alpaca/v2/stocks/AAPL/quotes/latest?feed=iex",
        )

    def test_gateway_mode_needs_a_token_and_a_venue(self):
        with self.assertRaises(ValueError):
            VenueClient(FakeTransport(), gateway_url=GATEWAY)
        with self.assertRaises(ValueError):
            VenueClient(FakeTransport(), gateway_url=GATEWAY, gateway=GatewaySigner(TOKEN))
        with self.assertRaises(ValueError):
            GatewaySigner("too short")

    def test_the_signer_holds_a_token_and_never_shows_it(self):
        signer = GatewaySigner(TOKEN)
        self.assertEqual(signer.headers(), {"Authorization": "Bearer " + TOKEN})
        self.assertEqual(signer.sign(b"anything"), b"")
        self.assertEqual(signer.algorithm, "none")
        self.assertNotIn(TOKEN, repr(signer))


class AlpacaGatewayTest(unittest.TestCase):
    def test_a_read_carries_the_bearer_token_and_neither_alpaca_header(self):
        transport = FakeTransport({GATEWAY + "/v1/alpaca/v2/account": ALPACA_ACCOUNT})
        balance = alpaca_broker(transport, gateway=True).balance()
        self.assertEqual(balance.cash, Decimal("500.00"))
        call = transport.calls[-1]
        self.assertEqual(call["url"], GATEWAY + "/v1/alpaca/v2/account")
        self.assertEqual(call["headers"]["Authorization"], "Bearer " + TOKEN)
        for name in ("APCA-API-KEY-ID", "APCA-API-SECRET-KEY"):
            self.assertNotIn(name, call["headers"])

    def test_direct_mode_still_sends_the_key_and_the_secret(self):
        transport = FakeTransport({"https://api.alpaca.markets/v2/account": ALPACA_ACCOUNT})
        alpaca_broker(transport).balance()
        call = transport.calls[-1]
        self.assertEqual(call["headers"]["APCA-API-KEY-ID"], "PKREALKEYID")
        self.assertEqual(call["headers"]["APCA-API-SECRET-KEY"], "real-secret")
        self.assertNotIn("Authorization", call["headers"])

    def test_an_order_body_is_unchanged_by_the_detour(self):
        order = intent(AAPL, quantity="2", order_type="limit", limit_price="10.00", time_in_force="day")
        direct = FakeTransport({("POST", "https://api.alpaca.markets/v2/orders"): ALPACA_ORDER})
        alpaca_broker(direct).submit(order)
        through = FakeTransport({("POST", GATEWAY + "/v1/alpaca/v2/orders"): ALPACA_ORDER})
        alpaca_broker(through, gateway=True).submit(order)
        self.assertEqual(direct.calls[-1]["body"], through.calls[-1]["body"])
        self.assertEqual(through.calls[-1]["body"]["symbol"], "AAPL")

    def test_market_data_goes_through_the_gateway_too(self):
        quote = {"symbol": "AAPL", "quote": {"ap": 12.5, "bp": 12.4, "t": NOW}}
        transport = FakeTransport({GATEWAY + "/v1/alpaca/v2/stocks/AAPL/quotes/latest*": quote})
        found = alpaca_broker(transport, gateway=True).quote(AAPL)
        self.assertEqual(found.ask, Decimal("12.5"))
        self.assertTrue(transport.calls[-1]["url"].startswith(GATEWAY + "/v1/alpaca/v2/stocks/AAPL/quotes/latest"))
        self.assertEqual(transport.calls[-1]["headers"]["Authorization"], "Bearer " + TOKEN)

