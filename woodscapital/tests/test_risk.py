import unittest
from decimal import Decimal

from woodscapital.broker import Instrument, OrderIntent, Position, Quote
from woodscapital.manifest import DeskManifest
from woodscapital.risk import Breaker, RiskContext, RiskEngine, circuit_breakers
from woodscapital.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "paper")


def manifest(**overrides):
    data = {**SAMPLE}
    data.update(overrides)
    return DeskManifest.from_dict(data)


def quote(price="100", delayed=False):
    p = Decimal(price)
    return Quote(AAPL, p - Decimal("0.05"), p + Decimal("0.05"), p, "2026-09-14T14:30:00.000Z", "sim", delayed)


def intent(side="buy", quantity="5", order_type="market", limit_price=None, instrument=AAPL, desk_id="earnings-01"):
    return OrderIntent.new(
        desk_id=desk_id, instrument=instrument, side=side, quantity=quantity, order_type=order_type,
        limit_price=limit_price, rationale="test", created_at="2026-09-14T14:30:00.000Z", session_id="s",
    )


def context(**overrides):
    base = dict(
        manifest=manifest(),
        desk_equity=Decimal("1000"),
        desk_cash=Decimal("1000"),
        positions={},
        quote=quote(),
        now="2026-09-14T14:30:00.000Z",
        venue_capabilities={"equity", "option", "limit", "paper"},
        market_open=True,
    )
    base.update(overrides)
    return RiskContext(**base)


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RiskEngine()

    def test_clean_order_is_approved(self):
        decision = self.engine.check(intent(quantity="2"), context())
        self.assertTrue(decision.approved, decision.reasons)
        self.assertEqual(decision.reference_price, Decimal("100.05"))
        self.assertEqual(decision.notional, Decimal("200.10"))
        self.assertEqual(decision.to_dict()["reasons"], [])

    def test_all_violations_are_listed(self):
        ctx = context(kill_switch=True, desk_orders_today=20)
        decision = self.engine.check(intent(quantity="5"), ctx)
        self.assertFalse(decision.approved)
        self.assertIn("kill switch engaged", decision.reasons)
        self.assertTrue(any("orders today" in r for r in decision.reasons))
        self.assertTrue(any("order notional" in r for r in decision.reasons))  # 500 > 25% of 1000

    def test_mandate_rules(self):
        crypto = Instrument("crypto", "BTC-USD", "paper")
        decision = self.engine.check(intent(instrument=crypto, quantity="0.001"), context())
        self.assertTrue(any("asset class" in r for r in decision.reasons))
        gme = Instrument("equity", "GME", "paper")
        decision = self.engine.check(intent(instrument=gme, quantity="1"), context(quote=Quote(gme, None, None, Decimal("20"), "t", "sim")))
        self.assertTrue(any("not permitted by mandate" in r for r in decision.reasons))
        other_venue = Instrument("equity", "AAPL", "kalshi")
        decision = self.engine.check(intent(instrument=other_venue, quantity="1"), context())
        self.assertTrue(any("venue" in r for r in decision.reasons))

    def test_short_and_fractional(self):
        decision = self.engine.check(intent(side="sell", quantity="1"), context())
        self.assertTrue(any("shorting is not permitted" in r for r in decision.reasons))
        held = {AAPL.key: Position(AAPL, "3", "90", mark="100")}
        decision = self.engine.check(intent(side="sell", quantity="3"), context(positions=held, desk_cash=Decimal("700")))
        self.assertTrue(decision.approved, decision.reasons)
        decision = self.engine.check(intent(quantity="0.5"), context())
        self.assertTrue(any("fractional" in r for r in decision.reasons))
        decision = self.engine.check(intent(quantity="0.5"), context(venue_capabilities={"equity", "fractional"}))
        self.assertTrue(decision.approved, decision.reasons)

    def test_price_rules(self):
        decision = self.engine.check(intent(quantity="1"), context(quote=None))
        self.assertTrue(any("no reference price" in r for r in decision.reasons))
        live = manifest(venues=["alpaca"], capital={"mode": "live", "usd": "500"})
        alpaca = Instrument("equity", "AAPL", "alpaca")
        decision = self.engine.check(intent(instrument=alpaca, quantity="1"), context(manifest=live, quote=None))
        self.assertTrue(any("no quote available for a live order" in r for r in decision.reasons))
        decision = self.engine.check(intent(quantity="1"), context(quote=quote("3")))
        self.assertTrue(any("below mandate minimum" in r for r in decision.reasons))
        decision = self.engine.check(intent(quantity="1", order_type="limit", limit_price="130"), context())
        self.assertTrue(any("limit price deviates" in r for r in decision.reasons))
        decision = self.engine.check(intent(quantity="1", order_type="limit", limit_price="101"), context())
        self.assertTrue(decision.approved, decision.reasons)

    def test_exposure_rules(self):
        decision = self.engine.check(intent(quantity="3"), context(desk_cash=Decimal("100")))
        self.assertTrue(any("insufficient desk cash" in r for r in decision.reasons))
        held = {AAPL.key: Position(AAPL, "2", "100", mark="100")}
        decision = self.engine.check(intent(quantity="1"), context(positions=held, desk_cash=Decimal("800")))
        self.assertTrue(any("position would be" in r for r in decision.reasons))  # 300 > 25% of 1000
        msft = Instrument("equity", "MSFT", "paper")
        held = {msft.key: Position(msft, "2", "400", mark="400")}
        wide = manifest(limits={**SAMPLE["limits"], "max_position_pct": "1", "max_order_notional_pct": "1"})
        decision = self.engine.check(intent(quantity="2"), context(manifest=wide, positions=held, desk_cash=Decimal("200")))
        self.assertTrue(any("gross exposure" in r for r in decision.reasons))  # 800 + 200 > 100% of 1000
        # reducing exposure is always allowed under the gross cap
        decision = self.engine.check(intent(side="sell", quantity="1", instrument=msft), context(
            manifest=wide, positions=held, desk_cash=Decimal("200"),
            quote=Quote(msft, Decimal("399"), Decimal("401"), Decimal("400"), "t", "sim")))
        self.assertTrue(decision.approved, decision.reasons)

    def test_daily_loss_rules(self):
        ctx = context(desk_equity=Decimal("880"), desk_daily_pnl=Decimal("-120"))
        decision = self.engine.check(intent(quantity="1"), ctx)
        self.assertTrue(any("daily loss" in r for r in decision.reasons))
        held = {AAPL.key: Position(AAPL, "2", "100", mark="90")}
        ctx = context(desk_equity=Decimal("880"), desk_daily_pnl=Decimal("-120"), positions=held)
        decision = self.engine.check(intent(side="sell", quantity="1"), ctx)
        self.assertTrue(decision.approved, decision.reasons)
        ctx = context(floor_equity=Decimal("4500"), floor_daily_pnl=Decimal("-500"))
        decision = self.engine.check(intent(quantity="1"), ctx)
        self.assertTrue(any("floor daily loss" in r for r in decision.reasons))

    def test_market_hours_and_liquidity(self):
        decision = self.engine.check(intent(quantity="1"), context(market_open=False))
        self.assertTrue(any("outside regular hours" in r for r in decision.reasons))
        decision = self.engine.check(intent(quantity="1", order_type="limit", limit_price="100"), context(market_open=False))
        self.assertTrue(decision.approved, decision.reasons)
        decision = self.engine.check(intent(quantity="1"), context(adv_usd=Decimal("1000000")))
        self.assertTrue(any("average daily volume" in r for r in decision.reasons))
        decision = self.engine.check(intent(quantity="2"), context(adv_usd=Decimal("10000")))
        self.assertTrue(any("1% of average daily" in r for r in decision.reasons) or any("average daily volume" in r for r in decision.reasons))


class BreakerTests(unittest.TestCase):
    def test_breakers(self):
        desk = manifest()
        out = circuit_breakers(desk=desk, desk_equity=Decimal("850"), desk_daily_pnl=Decimal("-150"),
                               floor_equity=Decimal("4000"), floor_daily_pnl=Decimal("-400"),
                               data_stale_seconds=2000, reconciliation_mismatch=True)
        rules = {(b.scope, b.rule) for b in out}
        self.assertIn(("desk:earnings-01", "daily_loss"), rules)
        self.assertIn(("floor", "daily_loss"), rules)
        self.assertIn(("floor", "stale_data"), rules)
        self.assertIn(("floor", "reconciliation"), rules)
        self.assertTrue(all(isinstance(b, Breaker) for b in out))
        self.assertEqual(circuit_breakers(desk=desk, desk_equity=Decimal("1000"), desk_daily_pnl=Decimal("5"),
                                          floor_equity=Decimal("5000"), floor_daily_pnl=Decimal("10")), [])
        bankrupt = circuit_breakers(desk=desk, desk_equity=Decimal("0"), desk_daily_pnl=Decimal("-1000"),
                                    floor_equity=Decimal("4000"), floor_daily_pnl=Decimal("-1000"))
        self.assertIn("pause_desk", [b.action for b in bankrupt])


if __name__ == "__main__":
    unittest.main()
