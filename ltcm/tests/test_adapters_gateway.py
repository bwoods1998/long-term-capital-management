"""Gateway mode: the same adapters, with the venue keys somewhere this process cannot reach.

Every test here runs the *real* Kalshi and Coinbase adapters over a fake transport, once in
direct mode and once in gateway mode, and asserts the difference is exactly the one intended:
the request goes to the gateway, carries a bearer token and no venue signature, and is otherwise
byte-for-byte the request the venue would have received.
"""

import unittest
from decimal import Decimal

from ltcm.adapters import (
    COINBASE_ORDERS_PATH,
    REFERENCE_HEADER,
    CoinbaseCredentials,
    GatewaySigner,
    KalshiCredentials,
    VenueClient,
    gateway_path,
    gateway_url_for,
)
from ltcm.adapters.coinbase import CoinbaseBroker
from ltcm.adapters.kalshi import KalshiBroker
from ltcm.broker import Instrument, OrderIntent, Quote
from ltcm.tests.fakes import Clock, FakeSigner, FakeTransport

GATEWAY = "https://ltcm-gateway.workers.dev"
TOKEN = "gateway-token-that-is-long-enough-1234567890"
NOW = "2026-09-15T14:00:00Z"
EPOCH = 1789480800

TICKER = "KXTEST-26SEP15"
EVENT = Instrument("event", TICKER, "kalshi", market_id=TICKER)
BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")

BALANCE = {"balance": 50000, "portfolio_value": 50000}
ACCOUNTS = {"accounts": [], "has_next": False}
KALSHI_ORDER = {"order": {"order_id": "k-1", "client_order_id": "oi-" + "a" * 32, "ticker": TICKER,
                          "status": "resting", "remaining_count": 3, "fill_count": 0}}
COINBASE_ORDER = {"success": True, "success_response": {"order_id": "c-1"}}


def intent(instrument, **kwargs):
    kwargs.setdefault("rationale", "test")
    kwargs.setdefault("created_at", NOW)
    kwargs.setdefault("side", "buy")
    return OrderIntent.new(desk_id="desk-1", instrument=instrument, **kwargs)


class FakeMarketData:
    """Public market data, which needs no credential and so never goes through the gateway."""

    def __init__(self, bid="64000", ask="64100", last="64050"):
        self.quote_value = Quote(
            instrument=BTC, bid=Decimal(bid), ask=Decimal(ask), last=Decimal(last),
            as_of=NOW, source="fake", delayed=False,
        )
        self.asked: list[str] = []

    def quote(self, instrument):
        self.asked.append(instrument.market_id or instrument.symbol)
        return self.quote_value

    def price_ranges(self, ticker):
        return [{"start": Decimal("0.01"), "end": Decimal("0.99"), "step": Decimal("0.01")}]


def kalshi_broker(transport, *, gateway=False):
    if gateway:
        client = VenueClient(
            transport, gateway_url=GATEWAY, gateway=GatewaySigner(TOKEN), venue="kalshi"
        )
        credentials = KalshiCredentials("gateway", GatewaySigner(TOKEN))
    else:
        client = VenueClient(transport)
        credentials = KalshiCredentials("real-key-id", FakeSigner())
    return KalshiBroker(
        credentials, client=client, clock=Clock(NOW), market_data=FakeMarketData()
    )


def coinbase_broker(transport, *, gateway=False, market_data=None):
    data = market_data or FakeMarketData()
    if gateway:
        client = VenueClient(
            transport, gateway_url=GATEWAY, gateway=GatewaySigner(TOKEN), venue="coinbase"
        )
        credentials = CoinbaseCredentials("gateway", GatewaySigner(TOKEN))
    else:
        client = VenueClient(transport)
        credentials = CoinbaseCredentials("organizations/o/apiKeys/k", FakeSigner())
    broker = CoinbaseBroker(
        credentials, client=client, clock=Clock(NOW), market_data=data, nonce=lambda: "n" * 32
    )
    if gateway:
        client.reference_price = lambda product_id: data.quote(BTC).mid
    return broker


class GatewayUrlTest(unittest.TestCase):
    def test_kalshi_loses_its_prefix_and_keeps_its_query(self):
        self.assertEqual(
            gateway_url_for(
                GATEWAY + "/", "kalshi",
                "https://api.elections.kalshi.com/trade-api/v2/portfolio/orders?status=resting&limit=200",
            ),
            GATEWAY + "/v1/kalshi/portfolio/orders?status=resting&limit=200",
        )

    def test_coinbase_paths_are_already_absolute(self):
        self.assertEqual(
            gateway_url_for(GATEWAY, "coinbase", "https://api.coinbase.com/api/v3/brokerage/accounts"),
            GATEWAY + "/v1/coinbase/api/v3/brokerage/accounts",
        )
        self.assertEqual(gateway_path("coinbase", "https://api.coinbase.com/x?y=1"), ("x", "y=1"))

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


class KalshiGatewayTest(unittest.TestCase):
    def test_a_read_goes_to_the_gateway_with_only_a_bearer_token(self):
        transport = FakeTransport({GATEWAY + "/v1/kalshi/portfolio/balance": BALANCE})
        balance = kalshi_broker(transport, gateway=True).balance()
        self.assertEqual(balance.cash, Decimal("500.00"))
        call = transport.calls[-1]
        self.assertEqual(call["url"], GATEWAY + "/v1/kalshi/portfolio/balance")
        self.assertEqual(call["headers"]["Authorization"], "Bearer " + TOKEN)
        for name in ("KALSHI-ACCESS-KEY", "KALSHI-ACCESS-TIMESTAMP", "KALSHI-ACCESS-SIGNATURE"):
            self.assertNotIn(name, call["headers"])

    def test_direct_mode_still_signs_and_still_reaches_the_venue(self):
        url = "https://api.elections.kalshi.com/trade-api/v2/portfolio/balance"
        transport = FakeTransport({url: BALANCE})
        kalshi_broker(transport).balance()
        call = transport.calls[-1]
        self.assertEqual(call["url"], url)
        self.assertEqual(call["headers"]["KALSHI-ACCESS-KEY"], "real-key-id")
        self.assertNotIn("Authorization", call["headers"])

    def test_an_order_body_is_unchanged_by_the_detour(self):
        direct_url = "https://api.elections.kalshi.com/trade-api/v2/portfolio/events/orders"
        order = intent(EVENT, quantity="3", order_type="limit", limit_price="0.65", time_in_force="gtc")
        direct = FakeTransport({("POST", direct_url): KALSHI_ORDER})
        kalshi_broker(direct).submit(order)
        through = FakeTransport({("POST", GATEWAY + "/v1/kalshi/portfolio/events/orders"): KALSHI_ORDER})
        kalshi_broker(through, gateway=True).submit(order)
        self.assertEqual(direct.calls[-1]["body"], through.calls[-1]["body"])
        self.assertEqual(through.calls[-1]["body"]["price"], "0.6500")

    def test_a_cancel_keeps_its_venue_order_id_in_the_path(self):
        orders = {"orders": [{"order_id": "k-9", "client_order_id": "oi-" + "b" * 32,
                              "ticker": TICKER, "status": "resting", "remaining_count": 1}]}
        transport = FakeTransport({GATEWAY + "/v1/kalshi/portfolio/orders*": orders})
        transport.route(("DELETE", GATEWAY + "/v1/kalshi/portfolio/events/orders/k-9"), {})
        order = kalshi_broker(transport, gateway=True).cancel("ord-" + "b" * 32)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(transport.calls[-1]["method"], "DELETE")


class CoinbaseGatewayTest(unittest.TestCase):
    def test_a_read_carries_the_bearer_token_and_no_jwt(self):
        transport = FakeTransport({GATEWAY + "/v1/coinbase/api/v3/brokerage/accounts*": ACCOUNTS})
        coinbase_broker(transport, gateway=True).accounts()
        call = transport.calls[-1]
        self.assertTrue(call["url"].startswith(GATEWAY + "/v1/coinbase/api/v3/brokerage/accounts?"))
        self.assertEqual(call["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn(REFERENCE_HEADER, call["headers"])

    def test_direct_mode_still_mints_a_jwt(self):
        transport = FakeTransport({"https://api.coinbase.com/api/v3/brokerage/accounts*": ACCOUNTS})
        coinbase_broker(transport).accounts()
        token = transport.calls[-1]["headers"]["Authorization"]
        self.assertTrue(token.startswith("Bearer ey"), token[:20])

    def test_an_order_post_carries_the_desks_own_reference_price(self):
        url = GATEWAY + "/v1/coinbase/" + COINBASE_ORDERS_PATH
        transport = FakeTransport({("POST", url): COINBASE_ORDER})
        coinbase_broker(transport, gateway=True).submit(
            intent(BTC, quantity="0.01", order_type="market", time_in_force="ioc")
        )
        call = transport.calls[-1]
        # mid of 64000/64100
        self.assertEqual(call["headers"][REFERENCE_HEADER], "64050")
        self.assertEqual(call["body"]["order_configuration"],
                         {"market_market_ioc": {"base_size": "0.01"}})

    def test_a_cancel_is_not_an_order_and_carries_no_price(self):
        base = GATEWAY + "/v1/coinbase/api/v3/brokerage/orders"
        transport = FakeTransport({
            base + "/historical/c-1": {"order": {"order_id": "c-1", "product_id": "BTC-USD",
                                                 "status": "OPEN", "client_order_id": "oi-x"}},
            ("POST", base + "/batch_cancel"): {"results": [{"success": True}]},
        })
        coinbase_broker(transport, gateway=True).cancel("c-1")
        self.assertEqual(transport.calls[-1]["url"], base + "/batch_cancel")
        self.assertNotIn(REFERENCE_HEADER, transport.calls[-1]["headers"])

    def test_an_unquotable_product_simply_sends_no_price(self):
        class Silent(FakeMarketData):
            def quote(self, instrument):
                raise RuntimeError("no market data")

        url = GATEWAY + "/v1/coinbase/" + COINBASE_ORDERS_PATH
        transport = FakeTransport({("POST", url): COINBASE_ORDER})
        client = VenueClient(
            transport, gateway_url=GATEWAY, gateway=GatewaySigner(TOKEN), venue="coinbase"
        )
        client.reference_price = lambda product_id: None
        broker = CoinbaseBroker(
            CoinbaseCredentials("gateway", GatewaySigner(TOKEN)), client=client,
            clock=Clock(NOW), market_data=Silent(),
        )
        broker.submit(intent(BTC, quantity="0.01", order_type="limit", limit_price="60000",
                             time_in_force="gtc"))
        self.assertNotIn(REFERENCE_HEADER, transport.calls[-1]["headers"])


class ServiceGatewayModeTest(unittest.TestCase):
    """`_make_live_broker` picks the mode, and gateway mode never touches a key file."""

    def _service(self, **config):
        from ltcm import service as service_module

        built = object.__new__(service_module.Service)
        built.config = {"venues": {"kalshi": {"key_id_env": "KALSHI_KEY_ID"},
                                   "coinbase": {"key_name_env": "COINBASE_KEY_NAME"}},
                        "gateway_token_env": "GATEWAY_TOKEN", **config}
        built.broker_factory = None
        built.transport = FakeTransport()
        built.clock = Clock(NOW)
        built.alerts: list[tuple[str, str]] = []
        built.alert = lambda level, message: built.alerts.append((level, message))
        built.secret = lambda name: {"GATEWAY_TOKEN": TOKEN}.get(name)
        built._private_key = lambda path: self.fail("gateway mode must not read a key file")
        return built

    def test_gateway_url_builds_gateway_mode_brokers_for_both_venues(self):
        service = self._service(gateway_url=GATEWAY)
        for venue, expected in (("kalshi", "portfolio/balance"), ("coinbase", "api/v3/brokerage/accounts")):
            broker = service._make_live_broker(venue)
            self.assertIsNotNone(broker, venue)
            self.assertEqual(broker.client.gateway_url, GATEWAY)
            self.assertEqual(broker.client.venue, venue)
            self.assertEqual(broker.credentials.key_id, "gateway")
            self.assertEqual(
                broker.client._to_gateway("GET", "https://x/" + expected, {}, None)[1]["Authorization"],
                "Bearer " + TOKEN,
            )
        self.assertEqual(service.alerts, [])

    def test_without_a_token_no_live_broker_is_built_and_nothing_is_logged(self):
        service = self._service(gateway_url=GATEWAY)
        service.secret = lambda name: None
        self.assertIsNone(service._make_live_broker("kalshi"))
        self.assertEqual(len(service.alerts), 1)
        self.assertNotIn(TOKEN, service.alerts[0][1])

    def test_no_gateway_url_leaves_the_direct_path_alone(self):
        service = self._service(gateway_url=None)
        service._private_key = lambda path: None
        self.assertIsNone(service._make_live_broker("kalshi"))

    def test_the_coinbase_reference_price_comes_from_the_desks_quote(self):
        service = self._service(gateway_url=GATEWAY)
        broker = service._make_live_broker("coinbase")
        broker.market_data = FakeMarketData()
        self.assertEqual(broker.client.reference_price("BTC-USD"), Decimal("64050"))
        self.assertIsNone(broker.client.reference_price(""))


if __name__ == "__main__":
    unittest.main()
