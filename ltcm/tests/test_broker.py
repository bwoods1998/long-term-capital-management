import unittest
from decimal import Decimal

from ltcm.broker import (
    Balance,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    money,
)


def equity(symbol="AAPL", venue="alpaca"):
    return Instrument("equity", symbol, venue)


class MoneyTests(unittest.TestCase):
    def test_money_rejects_floats_and_nan(self):
        self.assertEqual(money("1.50"), Decimal("1.50"))
        self.assertEqual(money(3), Decimal(3))
        with self.assertRaises(ValueError):
            money(1.5)
        with self.assertRaises(ValueError):
            money("nan")
        with self.assertRaises(ValueError):
            money(True)
        with self.assertRaises(ValueError):
            money("abc")


class InstrumentTests(unittest.TestCase):
    def test_keys_and_roundtrip(self):
        inst = equity()
        self.assertEqual(inst.key, "equity:AAPL:alpaca")
        self.assertEqual(Instrument.from_dict(inst.to_dict()), inst)
        option = Instrument("option", "AAPL", "schwab", multiplier="100", expiry="2026-10-16", strike="200", right="call")
        self.assertEqual(option.key, "option:AAPL:schwab:2026-10-16:200:call")
        self.assertEqual(Instrument.from_dict(option.to_dict()), option)
        event = Instrument("event", "CPI", "kalshi", market_id="KXCPI-26SEP-T3.0")
        self.assertIn("KXCPI-26SEP-T3.0", event.key)

    def test_validation(self):
        with self.assertRaises(ValueError):
            Instrument("bond", "X", "alpaca")
        with self.assertRaises(ValueError):
            Instrument("option", "AAPL", "alpaca")
        with self.assertRaises(ValueError):
            Instrument("event", "X", "kalshi")
        with self.assertRaises(ValueError):
            Instrument("equity", "AAPL", "alpaca", multiplier="0")


class QuoteTests(unittest.TestCase):
    def test_reference_and_mid(self):
        q = Quote(equity(), Decimal("99"), Decimal("101"), Decimal("100.5"), "t", "sim", delayed=False)
        self.assertEqual(q.mid, Decimal("100"))
        self.assertEqual(q.reference("buy"), Decimal("101"))
        self.assertEqual(q.reference("sell"), Decimal("99"))
        last_only = Quote(equity(), None, None, Decimal("50"), "t", "yahoo:delayed")
        self.assertEqual(last_only.reference("buy"), Decimal("50"))
        self.assertEqual(last_only.mid, Decimal("50"))
        self.assertTrue(last_only.delayed)


class OrderIntentTests(unittest.TestCase):
    def test_derived_identity_is_stable(self):
        a = OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="3", rationale="r", created_at="t", session_id="s")
        b = OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="3", rationale="different words", created_at="t2", session_id="s")
        c = OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="3", rationale="r", created_at="t", session_id="s", nonce="2")
        self.assertEqual(a.id, b.id)
        self.assertNotEqual(a.id, c.id)
        self.assertTrue(a.id.startswith("oi-"))
        self.assertEqual(OrderIntent.from_dict(a.to_dict()), a)

    def test_validation(self):
        with self.assertRaises(ValueError):
            OrderIntent.new(desk_id="d", instrument=equity(), side="hold", quantity="1", rationale="r", created_at="t")
        with self.assertRaises(ValueError):
            OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="0", rationale="r", created_at="t")
        with self.assertRaises(ValueError):
            OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="1", order_type="limit", rationale="r", created_at="t")
        with self.assertRaises(ValueError):
            OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="1", limit_price="10", rationale="r", created_at="t")
        with self.assertRaises(ValueError):
            OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="1", rationale="", created_at="t")
        limit = OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="2", order_type="limit", limit_price="10.5", rationale="r", created_at="t")
        self.assertEqual(limit.notional_hint, Decimal("21.0"))


class OrderExpiryTests(unittest.TestCase):
    """Sept 17, 2026: a resting entry may name when the venue itself cancels it."""

    NOW = "2026-09-17T01:00:00.000Z"
    BTC = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")

    def entry(self, **kwargs):
        options = dict(desk_id="d", instrument=self.BTC, side="buy", quantity="0.001", order_type="limit",
                       limit_price="60000", time_in_force="gtc", rationale="r", created_at=self.NOW, session_id="s")
        options.update(kwargs)
        return OrderIntent.new(**options)

    def test_an_expiry_round_trips_and_is_not_part_of_the_id(self):
        expiring = self.entry(expires_at="2026-09-17T01:20:00.000Z")
        self.assertEqual(expiring.expires_at, "2026-09-17T01:20:00.000Z")
        self.assertEqual(expiring.to_dict()["expires_at"], "2026-09-17T01:20:00.000Z")
        self.assertEqual(OrderIntent.from_dict(expiring.to_dict()), expiring)
        self.assertEqual(expiring.id, self.entry(expires_at="2026-09-17T02:00:00.000Z").id)
        self.assertEqual(expiring.id, self.entry().id)
        self.assertNotIn("expires_at", self.entry().to_dict())

    def test_the_window_is_two_minutes_to_two_days_from_created_at(self):
        self.assertIsNotNone(self.entry(expires_at="2026-09-17T01:02:00.000Z"))
        self.assertIsNotNone(self.entry(expires_at="2026-09-19T01:00:00Z"))
        for stamp in ("2026-09-17T01:01:59.999Z", "2026-09-19T01:00:01Z", "2026-09-17T00:59:00Z"):
            with self.assertRaises(ValueError, msg=stamp):
                self.entry(expires_at=stamp)

    def test_only_a_resting_gtc_limit_entry_can_expire(self):
        stamp = "2026-09-17T01:20:00Z"
        with self.assertRaises(ValueError):
            self.entry(order_type="market", limit_price=None, expires_at=stamp)
        for tif in ("day", "ioc"):
            with self.assertRaises(ValueError, msg=tif):
                self.entry(time_in_force=tif, expires_at=stamp)
        with self.assertRaises(ValueError):
            self.entry(side="sell", purpose="exit", exit_reason="stop", exit_of="oi-x", expires_at=stamp)
        for bad in ("soon", "2026-09-17", 1789606800):
            with self.assertRaises(ValueError, msg=bad):
                self.entry(expires_at=bad)
        with self.assertRaises(ValueError):
            self.entry(created_at="t", expires_at=stamp)


class OrderAndFillTests(unittest.TestCase):
    def test_order_from_intent(self):
        intent = OrderIntent.new(desk_id="d", instrument=equity(), side="buy", quantity="3", rationale="r", created_at="t")
        order = Order.from_intent(intent)
        self.assertEqual(order.id, "ord-" + intent.id[3:])
        self.assertEqual(order.status, "new")
        self.assertFalse(order.terminal)
        self.assertEqual(order.remaining, Decimal(3))
        order.status = "filled"
        self.assertTrue(order.terminal)
        self.assertNotIn("_raw", order.to_dict())
        self.assertIn("_raw", order.to_dict(private=True))
        with self.assertRaises(ValueError):
            Order.from_intent(intent).__class__(**{**order.__dict__, "status": "weird"})

    def test_fill_and_position(self):
        fill = Fill("f", "o", "d", equity(), "buy", "2", "10", "0.01", "t")
        self.assertEqual(fill.notional, Decimal("20"))
        with self.assertRaises(ValueError):
            Fill("f", "o", "d", equity(), "buy", "0", "10", "0", "t")
        pos = Position(equity(), "2", "10", mark="12")
        self.assertEqual(pos.market_value, Decimal("24"))
        self.assertEqual(pos.unrealized_pnl, Decimal("4"))
        short = Position(equity(), "-1", "10", mark="8")
        self.assertEqual(short.unrealized_pnl, Decimal("2"))
        self.assertIsNone(Position(equity(), "1", "10").market_value)

    def test_balance(self):
        bal = Balance("alpaca", "100", "120", "100", "t")
        self.assertEqual(bal.to_dict()["equity"], "120")


if __name__ == "__main__":
    unittest.main()


class CryptoKeyTests(unittest.TestCase):
    def test_a_crypto_product_keys_the_same_with_or_without_its_market_id(self):
        from ltcm.broker import Instrument

        self.assertEqual(Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD").key, Instrument("crypto", "BTC-USD", "coinbase").key)
        self.assertEqual(Instrument("crypto", "BTC-USD", "coinbase").key, "crypto:BTC-USD:coinbase")
        event = Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1", right="no")
        self.assertEqual(event.key, "event:KXBTC-1:kalshi:no:KXBTC-1", "event keys keep the market id: their positions were always keyed with it")


class EventLegKeyTests(unittest.TestCase):
    def test_an_event_contract_without_a_leg_keys_as_the_yes_leg(self):
        from ltcm.broker import Instrument

        bare = Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1")
        yes = Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1", right="yes")
        no = Instrument("event", "KXBTC-1", "kalshi", market_id="KXBTC-1", right="no")
        self.assertEqual(bare.key, yes.key, "a desk that omits the leg means YES, as the fill will say")
        self.assertNotEqual(yes.key, no.key)
