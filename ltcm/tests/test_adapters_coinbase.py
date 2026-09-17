"""The Coinbase adapter: JWT shape, order configuration mapping, UnknownOutcome, fills."""

import base64
import json
import unittest
from decimal import Decimal

from ltcm.broker import Instrument, OrderIntent, RejectedOrder, UnknownOutcome
from ltcm.data import TransportError
from ltcm.data.coinbase import HOST, MARKET, PREFIX
from ltcm.adapters import CoinbaseCredentials, b64url, jws
from ltcm.adapters.coinbase import (
    CAPABILITIES,
    JWT_LIFETIME,
    STATUS_MAP,
    CoinbaseBroker,
    order_configuration,
)
from ltcm.tests.fakes import Clock, FakeSigner, FakeTransport

BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")
NOW = "2026-09-15T14:00:00Z"
EPOCH = 1789480800
KEY_ID = "organizations/abc/apiKeys/def"

ACCOUNTS = {
    "accounts": [
        {
            "uuid": "8bfc20d7-0000-0000-0000-000000000001",
            "name": "USD Wallet",
            "currency": "USD",
            "available_balance": {"value": "5000.25", "currency": "USD"},
            "hold": {"value": "0", "currency": "USD"},
            "type": "ACCOUNT_TYPE_FIAT",
            "active": True,
            "ready": True,
        },
        {
            "uuid": "8bfc20d7-0000-0000-0000-000000000002",
            "name": "BTC Wallet",
            "currency": "BTC",
            "available_balance": {"value": "0.25", "currency": "BTC"},
            "hold": {"value": "0.05", "currency": "BTC"},
            "type": "ACCOUNT_TYPE_CRYPTO",
        },
        {
            "uuid": "8bfc20d7-0000-0000-0000-000000000003",
            "currency": "ETH",
            "available_balance": {"value": "0", "currency": "ETH"},
            "hold": {"value": "0", "currency": "ETH"},
        },
    ],
    "has_next": False,
    "cursor": "",
    "size": 3,
}

BOOK = {
    "pricebook": {
        "product_id": "BTC-USD",
        "bids": [{"price": "64000", "size": "1"}],
        "asks": [{"price": "64100", "size": "1"}],
        "time": NOW,
    },
    "last": "64050",
}

CREATED = {
    "success": True,
    "success_response": {
        "order_id": "0000-11111-22222",
        "product_id": "BTC-USD",
        "side": "BUY",
        "client_order_id": "oi-" + "c" * 32,
    },
    "order_configuration": {"market_market_ioc": {"base_size": "0.01"}},
}

REFUSED = {
    "success": False,
    "error_response": {
        "error": "INSUFFICIENT_FUND",
        "message": "Insufficient balance in source account",
        "error_details": "",
    },
}

ORDER_ROW = {
    "order_id": "0000-11111-22222",
    "client_order_id": "oi-" + "c" * 32,
    "product_id": "BTC-USD",
    "side": "BUY",
    "status": "OPEN",
    "time_in_force": "GOOD_UNTIL_CANCELLED",
    "created_time": NOW,
    "completion_percentage": "0",
    "filled_size": "0",
    "average_filled_price": "0",
    "total_fees": "0",
    "order_type": "LIMIT",
    "order_configuration": {"limit_limit_gtc": {"base_size": "0.02", "limit_price": "60000"}},
}

FILLS = {
    "fills": [
        {
            "entry_id": "e-1",
            "trade_id": "tr-1",
            "order_id": "0000-11111-22222",
            "trade_time": "2026-09-15T14:00:03Z",
            "trade_type": "FILL",
            "price": "64100.00",
            "size": "0.01",
            "commission": "1.6025",
            "product_id": "BTC-USD",
            "sequence_timestamp": "2026-09-15T14:00:03Z",
            "liquidity_indicator": "TAKER",
            "side": "BUY",
        }
    ],
    "cursor": "",
}


def make(routes=None, *, algorithm="ES256"):
    transport = FakeTransport(routes or {})
    signer = FakeSigner(algorithm=algorithm, signature=b"cdp-signature")
    credentials = CoinbaseCredentials(KEY_ID, signer)
    client = CoinbaseBroker(
        credentials, transport=transport, clock=Clock(NOW), nonce=lambda: "0123456789abcdef"
    )
    return client, transport, signer


def intent(instrument=BTC, **kwargs):
    kwargs.setdefault("rationale", "test")
    kwargs.setdefault("created_at", NOW)
    kwargs.setdefault("quantity", "0.01")
    kwargs.setdefault("side", "buy")
    return OrderIntent.new(desk_id="desk-1", instrument=instrument, **kwargs)


def decode_jwt(token):
    header, payload, signature = token.split(".")

    def part(value):
        return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))

    return part(header), part(payload), signature


class JwtTests(unittest.TestCase):
    def test_header_and_payload_match_the_cdp_contract(self):
        client, transport, signer = make({HOST + PREFIX + "/accounts*": ACCOUNTS})
        client.accounts()
        token = transport.last["headers"]["Authorization"]
        self.assertTrue(token.startswith("Bearer "))
        header, payload, signature = decode_jwt(token[len("Bearer "):])
        self.assertEqual(header["alg"], "ES256")
        self.assertEqual(header["typ"], "JWT")
        self.assertEqual(header["kid"], KEY_ID)
        self.assertEqual(header["nonce"], "0123456789abcdef")
        self.assertEqual(payload["sub"], KEY_ID)
        self.assertEqual(payload["iss"], "cdp")
        self.assertEqual(payload["nbf"], EPOCH)
        self.assertEqual(payload["exp"], EPOCH + JWT_LIFETIME)
        self.assertEqual(payload["uri"], "GET api.coinbase.com/api/v3/brokerage/accounts")
        self.assertEqual(signature, b64url(b"cdp-signature"))

    def test_the_uri_claim_excludes_the_query_string(self):
        client, transport, _ = make({HOST + PREFIX + "/accounts*": ACCOUNTS})
        client.accounts()
        _, payload, _ = decode_jwt(transport.last["headers"]["Authorization"][7:])
        self.assertNotIn("?", payload["uri"])
        self.assertIn("limit=250", transport.last["url"])

    def test_the_uri_claim_names_the_method_and_path_of_that_request(self):
        client, transport, _ = make({("POST", HOST + PREFIX + "/orders"): CREATED})
        client.submit(intent())
        _, payload, _ = decode_jwt(transport.last["headers"]["Authorization"][7:])
        self.assertEqual(payload["uri"], "POST api.coinbase.com/api/v3/brokerage/orders")

    def test_an_ed25519_key_signs_with_eddsa(self):
        client, transport, _ = make({HOST + PREFIX + "/accounts*": ACCOUNTS}, algorithm="EdDSA")
        client.accounts()
        header, _, _ = decode_jwt(transport.last["headers"]["Authorization"][7:])
        self.assertEqual(header["alg"], "EdDSA")

    def test_the_signed_input_is_the_two_encoded_segments(self):
        signer = FakeSigner(algorithm="ES256", signature=b"sig")
        token = jws({"alg": "ES256"}, {"sub": "x"}, signer)
        self.assertEqual(signer.messages[0].decode("ascii"), token.rsplit(".", 1)[0])

    def test_a_fresh_token_is_minted_per_request(self):
        client, transport, signer = make({HOST + PREFIX + "/accounts*": ACCOUNTS})
        client.accounts()
        client.accounts()
        self.assertEqual(len(signer.messages), 2)

    def test_credentials_require_a_signer_and_never_print_one(self):
        with self.assertRaises(ValueError):
            CoinbaseCredentials(KEY_ID, object())
        self.assertNotIn("apiKeys", repr(CoinbaseCredentials(KEY_ID, FakeSigner())))


class OrderConfigurationTests(unittest.TestCase):
    def test_a_market_order_becomes_market_market_ioc_with_a_base_size(self):
        configuration = order_configuration(intent(quantity="0.015"))
        self.assertEqual(configuration, {"market_market_ioc": {"base_size": "0.015"}})
        self.assertNotIn("quote_size", configuration["market_market_ioc"])

    def test_a_gtc_limit_becomes_limit_limit_gtc(self):
        configuration = order_configuration(
            intent(order_type="limit", limit_price="60000.50", time_in_force="gtc")
        )
        self.assertEqual(
            configuration,
            {"limit_limit_gtc": {"base_size": "0.01", "limit_price": "60000.50", "post_only": False}},
        )

    def test_a_day_or_ioc_limit_is_refused_rather_than_silently_resting_forever(self):
        for tif in ("day", "ioc"):
            with self.assertRaises(RejectedOrder):
                order_configuration(
                    intent(order_type="limit", limit_price="60000", time_in_force=tif)
                )

    def test_a_limit_with_an_expiry_becomes_limit_limit_gtd_with_an_rfc3339_end_time(self):
        # Sept 17, 2026: the venue cancels a resting entry at its end time even if the floor stalls.
        configuration = order_configuration(
            intent(order_type="limit", limit_price="60000.50", time_in_force="gtc", post_only=True,
                   expires_at="2026-09-15T14:20:00.000Z")
        )
        self.assertEqual(
            configuration,
            {"limit_limit_gtd": {"base_size": "0.01", "limit_price": "60000.50", "end_time": "2026-09-15T14:20:00Z", "post_only": True}},
        )

    def test_an_expiring_entry_carries_no_attached_bracket(self):
        client, transport, _ = make({("POST", HOST + PREFIX + "/orders"): CREATED})
        proposal = intent(order_type="limit", limit_price="60000", time_in_force="gtc", target_price="66000",
                          stop_price="57000", expires_at="2026-09-15T16:00:00.000Z")
        order = client.submit(proposal)
        body = transport.last["body"]
        self.assertIn("limit_limit_gtd", body["order_configuration"])
        self.assertNotIn("attached_order_configuration", body, "only a GTC order can carry an attached order")
        self.assertNotIn("bracket", order._raw, "the floor keeps this entry's stop itself")

    def test_a_market_order_with_an_expiry_is_refused(self):
        market = intent()
        object.__setattr__(market, "expires_at", "2026-09-15T14:20:00.000Z")
        with self.assertRaises(RejectedOrder):
            order_configuration(market)

    def test_an_expired_order_is_terminal(self):
        client, _, _ = make()
        order = client.parse_order(dict(ORDER_ROW, status="EXPIRED"))
        self.assertEqual(order.status, "expired")
        self.assertTrue(order.terminal)

    def test_capabilities_do_not_claim_day_or_ioc(self):
        client, _, _ = make()
        self.assertEqual(client.capabilities(), CAPABILITIES)
        self.assertIn("gtc", client.capabilities())
        self.assertNotIn("ioc", client.capabilities())
        self.assertNotIn("equity", client.capabilities())


class SubmitTests(unittest.TestCase):
    def test_the_request_body_is_exactly_what_coinbase_expects(self):
        client, transport, _ = make({("POST", HOST + PREFIX + "/orders"): CREATED})
        proposal = intent()
        order = client.submit(proposal)
        self.assertEqual(
            transport.last["body"],
            {
                "client_order_id": proposal.id,
                "product_id": "BTC-USD",
                "side": "BUY",
                "order_configuration": {"market_market_ioc": {"base_size": "0.01"}},
            },
        )
        self.assertEqual(transport.last["path"], "/api/v3/brokerage/orders")
        self.assertEqual(order.broker_order_id, "0000-11111-22222")
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order.intent_id, proposal.id)
        self.assertEqual(order.id, "ord-" + proposal.id[3:])

    def test_a_refusal_arrives_as_success_false_not_a_4xx(self):
        client, _, _ = make({("POST", HOST + PREFIX + "/orders"): REFUSED})
        with self.assertRaises(RejectedOrder) as caught:
            client.submit(intent())
        self.assertIn("Insufficient balance", str(caught.exception))

    def test_a_success_with_no_order_id_is_unknown(self):
        client, _, _ = make({("POST", HOST + PREFIX + "/orders"): {"success": True, "success_response": {}}})
        with self.assertRaises(UnknownOutcome):
            client.submit(intent())

    def test_only_crypto_is_accepted(self):
        client, transport, _ = make()
        with self.assertRaises(RejectedOrder):
            client.submit(intent(Instrument("equity", "AAPL", "coinbase")))
        self.assertEqual(transport.calls, [])


class UnknownOutcomeTests(unittest.TestCase):
    def test_a_lost_post_that_cannot_be_confirmed_is_unknown(self):
        client, transport, _ = make(
            {
                ("POST", HOST + PREFIX + "/orders"): TransportError("timed out"),
                HOST + PREFIX + "/orders/historical/batch*": {"orders": []},
            }
        )
        with self.assertRaises(UnknownOutcome):
            client.submit(intent())
        posts = [call for call in transport.calls if call["method"] == "POST"]
        self.assertEqual(len(posts), 1, "a lost write is never retried")

    def test_a_lost_post_the_venue_did_receive_is_found_by_client_order_id(self):
        proposal = intent()
        row = dict(ORDER_ROW, client_order_id=proposal.id)
        client, _, _ = make(
            {
                ("POST", HOST + PREFIX + "/orders"): TransportError("timed out"),
                HOST + PREFIX + "/orders/historical/batch*": {"orders": [row]},
            }
        )
        order = client.submit(proposal)
        self.assertEqual(order.intent_id, proposal.id)
        self.assertEqual(order.status, "accepted")
        self.assertEqual(order.limit_price, Decimal("60000"))


class AccountTests(unittest.TestCase):
    def test_fee_tier_is_read_only_and_never_defaults_missing_rates_to_zero(self):
        broker = CoinbaseBroker.__new__(CoinbaseBroker)
        calls = []
        def answer(*args, **kwargs):
            calls.append(args)
            return {"fee_tier": {"maker_fee_rate": "0.005", "taker_fee_rate": "0.009"}}
        broker._call = answer
        self.assertEqual(broker.fee_rates(), {"maker": "0.005", "taker": "0.009", "future_contract": "0.20"})
        self.assertEqual(calls[0], ("GET", PREFIX + "/transaction_summary"))
        broker._call = lambda *args, **kwargs: {"fee_tier": {}}
        with self.assertRaises((ValueError, TypeError)):
            broker.fee_rates()

    def test_balance_is_usd_cash_plus_marked_crypto(self):
        client, _, _ = make(
            {HOST + PREFIX + "/accounts*": ACCOUNTS, HOST + MARKET + "/product_book*": BOOK}
        )
        balance = client.balance()
        self.assertEqual(balance.cash, Decimal("5000.25"))
        # 0.25 available + 0.05 held, marked at the 64050 mid
        self.assertEqual(balance.equity, Decimal("5000.25") + Decimal("0.30") * Decimal("64050"))
        self.assertEqual(balance.venue, "coinbase")

    def test_positions_skip_usd_and_empty_wallets(self):
        client, _, _ = make(
            {HOST + PREFIX + "/accounts*": ACCOUNTS, HOST + MARKET + "/product_book*": BOOK}
        )
        positions = client.positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].instrument.symbol, "BTC-USD")
        self.assertEqual(positions[0].quantity, Decimal("0.30"))
        self.assertEqual(positions[0].mark, Decimal("64050"))
        self.assertEqual(
            positions[0].unrealized_pnl,
            Decimal("0"),
            "Coinbase reports no cost basis, so this adapter reports no profit",
        )

    def test_quotes_come_from_the_public_book_without_a_jwt(self):
        client, transport, signer = make({HOST + MARKET + "/product_book*": BOOK})
        quote = client.quote(BTC)
        self.assertEqual(quote.bid, Decimal("64000"))
        self.assertEqual(quote.ask, Decimal("64100"))
        self.assertEqual(signer.messages, [], "public market data is never signed")
        self.assertNotIn("Authorization", transport.last["headers"])


class LifecycleTests(unittest.TestCase):
    def test_status_map_covers_the_documented_states(self):
        for state in (
            "PENDING", "OPEN", "FILLED", "CANCELLED", "EXPIRED", "FAILED",
            "UNKNOWN_ORDER_STATUS", "QUEUED", "CANCEL_QUEUED", "EDIT_QUEUED",
        ):
            self.assertIn(state, STATUS_MAP, state)

    def test_open_orders_filters_on_order_status(self):
        client, transport, _ = make({HOST + PREFIX + "/orders/historical/batch*": {"orders": [ORDER_ROW]}})
        orders = client.open_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(transport.last["query"]["order_status"], "OPEN")
        self.assertEqual(orders[0].quantity, Decimal("0.02"))
        self.assertEqual(orders[0].order_type, "limit")
        self.assertEqual(orders[0].status, "accepted")

    def test_get_order_reads_the_order_wrapper(self):
        client, transport, _ = make(
            {HOST + PREFIX + "/orders/historical/0000-11111-22222": {"order": ORDER_ROW}}
        )
        order = client.get_order("0000-11111-22222")
        self.assertEqual(order.broker_order_id, "0000-11111-22222")
        self.assertEqual(order.limit_price, Decimal("60000"))

    def test_cancel_posts_a_single_id_to_batch_cancel(self):
        client, transport, _ = make(
            {
                HOST + PREFIX + "/orders/historical/batch*": {"orders": [ORDER_ROW]},
                ("POST", HOST + PREFIX + "/orders/batch_cancel"): {
                    "results": [{"success": True, "order_id": "0000-11111-22222"}]
                },
            }
        )
        order = client.cancel("ord-" + "c" * 32)
        self.assertEqual(order.status, "cancelled")
        posts = [call for call in transport.calls if call["method"] == "POST"]
        self.assertEqual(posts[-1]["body"], {"order_ids": ["0000-11111-22222"]})

    def test_a_cancel_refused_for_a_real_reason_raises(self):
        client, _, _ = make(
            {
                HOST + PREFIX + "/orders/historical/batch*": {"orders": [ORDER_ROW]},
                ("POST", HOST + PREFIX + "/orders/batch_cancel"): {
                    "results": [{"success": False, "failure_reason": "NOT_ALLOWED_TO_CANCEL"}]
                },
            }
        )
        with self.assertRaises(RejectedOrder):
            client.cancel("ord-" + "c" * 32)

    def test_a_cancel_of_an_already_filled_order_is_not_an_error(self):
        client, _, _ = make(
            {
                HOST + PREFIX + "/orders/historical/batch*": {"orders": [ORDER_ROW]},
                ("POST", HOST + PREFIX + "/orders/batch_cancel"): {
                    "results": [{"success": False, "failure_reason": "ORDER_IS_FULLY_FILLED"}]
                },
            }
        )
        self.assertEqual(client.cancel("ord-" + "c" * 32).status, "cancelled")

    def test_fills_carry_the_commission_as_the_fee(self):
        client, transport, _ = make({HOST + PREFIX + "/orders/historical/fills*": FILLS})
        fills = client.fills(since="2026-09-15T00:00:00Z")
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.price, Decimal("64100.00"))
        self.assertEqual(fill.quantity, Decimal("0.01"))
        self.assertEqual(fill.fee, Decimal("1.6025"))
        self.assertEqual(fill.side, "buy")
        self.assertEqual(fill.instrument.symbol, "BTC-USD")
        self.assertEqual(
            transport.last["query"]["start_sequence_timestamp"], "2026-09-15T00:00:00Z"
        )


if __name__ == "__main__":
    unittest.main()


CFM_SUMMARY = {"balance_summary": {"cfm_usd_balance": {"value": "120.00"}, "unrealized_pnl": {"value": "-3.50"}, "futures_buying_power": {"value": "480.00"}}}
CFM_POSITIONS = {"positions": [
    {"product_id": "ETP-20DEC30-CDE", "side": "SHORT", "number_of_contracts": "2", "avg_entry_price": "2450", "current_price": "2440", "unrealized_pnl": "2.00"},
    {"product_id": "BIP-20DEC30-CDE", "side": "LONG", "number_of_contracts": "0"},
]}
ETP_PRODUCT = {"product_id": "ETP-20DEC30-CDE", "price": "2440", "product_type": "FUTURE", "quote_increment": "0.5",
               "future_product_details": {"contract_size": "0.1", "contract_root_unit": "ETH", "contract_expiry": "2089-12-30T16:00:00Z", "perpetual_details": {}}}


class FuturesTests(unittest.TestCase):
    """leap: futures -- CDE contracts as positions with the venue's contract size (Sept 17, 2026)."""

    def routes(self):
        return {
            HOST + PREFIX + "/accounts*": ACCOUNTS, HOST + MARKET + "/product_book*": BOOK,
            HOST + PREFIX + "/cfm/balance_summary": CFM_SUMMARY, HOST + PREFIX + "/cfm/positions": CFM_POSITIONS,
            HOST + MARKET + "/products/ETP-20DEC30-CDE": ETP_PRODUCT,
        }

    def test_futures_positions_carry_the_contract_size_and_the_short_sign(self):
        client, _, _ = make(self.routes())
        positions = {p.instrument.symbol: p for p in client.positions()}
        self.assertEqual(set(positions), {"BTC-USD", "ETP-20DEC30-CDE"}, "a zero-contract row is not a position")
        short = positions["ETP-20DEC30-CDE"]
        self.assertEqual((short.instrument.asset_class, short.quantity, short.average_cost, short.mark), ("future", Decimal("-2"), Decimal("2450"), Decimal("2440")))
        self.assertEqual(short.instrument.multiplier, Decimal("0.1"), "the venue's contract size is the multiplier")
        self.assertEqual(short.instrument.expiry, "2030-12-20")
        self.assertEqual(short.market_value, Decimal("-2") * Decimal("2440") * Decimal("0.1"))

    def test_balance_adds_the_futures_wallet_and_its_pnl_but_never_a_contracts_notional(self):
        client, _, _ = make(self.routes())
        balance = client.balance()
        spot = Decimal("5000.25") + Decimal("0.30") * Decimal("64050")
        self.assertEqual(balance.equity, spot + Decimal("120.00") + Decimal("-3.50"))
        self.assertEqual(balance.cash, Decimal("5000.25") + Decimal("120.00"))

    def test_without_derivatives_access_the_spot_book_stands(self):
        routes = self.routes()
        routes[HOST + PREFIX + "/cfm/balance_summary"] = (403, {}, b'{"error":"no access"}')
        routes[HOST + PREFIX + "/cfm/positions"] = (403, {}, b'{"error":"no access"}')
        client, _, _ = make(routes)
        self.assertEqual([p.instrument.symbol for p in client.positions()], ["BTC-USD"])
        self.assertEqual(client.balance().equity, Decimal("5000.25") + Decimal("0.30") * Decimal("64050"))

    def test_a_futures_order_must_be_a_cde_product_in_whole_contracts(self):
        client, _, _ = make(self.routes())
        bad = Instrument("future", "BTC-USD", "coinbase", market_id="BTC-USD")
        with self.assertRaises(RejectedOrder):
            client.submit(intent(bad, side="sell", quantity="1", order_type="limit", limit_price="76000", time_in_force="gtc"))
        etp = Instrument("future", "ETP-20DEC30-CDE", "coinbase", multiplier=Decimal("0.1"), market_id="ETP-20DEC30-CDE")
        with self.assertRaises(RejectedOrder):
            client.submit(intent(etp, side="sell", quantity="1.5", order_type="limit", limit_price="2440", time_in_force="gtc"))
        self.assertIn("short", client.capabilities())
        self.assertEqual(client.fee_rates.__doc__ is not None, True)
