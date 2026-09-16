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
