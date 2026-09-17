import unittest
from decimal import Decimal

from ltcm.broker import Instrument, OrderIntent, Position, Quote
from ltcm.manifest import DeskManifest
from ltcm.risk import Breaker, RiskContext, RiskEngine, circuit_breakers
from ltcm.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "alpaca")


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
        venue_capabilities={"equity", "option", "limit", "shadow"},
        market_open=True,
    )
    base.update(overrides)
    return RiskContext(**base)


class RiskEngineTests(unittest.TestCase):
    def test_zero_equity_does_not_trap_existing_inventory(self):
        from dataclasses import replace
        order = replace(intent(side="sell", quantity="2"), purpose="exit", exit_of="desk:position", exit_reason="desk")
        ctx = context(desk_equity=Decimal("-10"), positions={AAPL.key: Position(AAPL, Decimal("3"), Decimal("100"), Decimal("100"))})
        self.assertTrue(RiskEngine().check(order, ctx).approved)
        self.assertFalse(RiskEngine().check(intent(quantity="1"), ctx).approved)
        ctx.kill_switch = True
        self.assertFalse(RiskEngine().check(order, ctx).approved)

    def test_exit_label_cannot_open_or_reverse_a_position(self):
        from dataclasses import replace
        order = replace(intent(side="sell", quantity="3"), purpose="exit", exit_of="desk:position", exit_reason="desk")
        for held in [None, Position(AAPL, Decimal("2"), Decimal("100"), Decimal("100"))]:
            ctx = context(positions={} if held is None else {AAPL.key: held})
            self.assertTrue(any("exit must reduce" in r for r in RiskEngine().check(order, ctx).reasons))

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

    def test_a_refused_sell_says_what_the_desk_holds_on_that_market(self):
        ticker = "KXHIGHNY-26SEP16-B81.5"
        yes = Instrument("event", ticker, "kalshi", market_id=ticker, right="yes")
        no = Instrument("event", ticker, "kalshi", market_id=ticker, right="no")
        held = {yes.key: Position(yes, Decimal("54"), Decimal("0.1"), Decimal("0.2"))}
        events = manifest(instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []}, venues=["kalshi"])
        sell_no = OrderIntent.new(desk_id="earnings-01", instrument=no, side="sell", quantity="54", order_type="limit", limit_price="0.8",
                                  rationale="close", created_at="2026-09-14T14:30:00.000Z", session_id="s")
        reasons = self.engine.check(sell_no, context(manifest=events, positions=held)).reasons
        self.assertTrue(any("you hold 54 YES on this market" in r for r in reasons), reasons)

    def test_an_exit_is_never_refused_for_the_days_order_count(self):
        held = {AAPL.key: type("P", (), {"quantity": Decimal("5"), "instrument": AAPL, "average_cost": Decimal("100"), "mark": Decimal("100")})()}
        stop = OrderIntent.new(
            desk_id="earnings-01", instrument=AAPL, side="sell", quantity="5", order_type="market", rationale="stop",
            created_at="2026-09-14T14:30:00.000Z", session_id=None, purpose="exit", exit_reason="stop", exit_of="oi-x",
        )
        decision = self.engine.check(stop, context(desk_orders_today=500, positions=held))
        self.assertFalse(any("orders today" in r for r in decision.reasons), decision.reasons)
        entry = self.engine.check(intent(quantity="1"), context(desk_orders_today=500))
        self.assertTrue(any("orders today" in r for r in entry.reasons), "the desk's own orders still count")

    def test_mandate_rules(self):
        crypto = Instrument("crypto", "BTC-USD", "alpaca")
        decision = self.engine.check(intent(instrument=crypto, quantity="0.001"), context())
        self.assertTrue(any("asset class" in r for r in decision.reasons))
        gme = Instrument("equity", "GME", "alpaca")
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

    def test_event_contracts_are_judged_in_cents_not_percent(self):
        # On Sept 16, 2026 a seven-cent bid against a four-cent ask read as "75% away" and was
        # refused; on a contract that pays a dollar, the sanity line is cents through the touch.
        market = Instrument(
            "event", "KXBTCD-26SEP1521", "kalshi", market_id="KXBTCD-26SEP1521-T75799.99", right="yes"
        )
        events = manifest(
            venues=["kalshi"],
            instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
        )
        book = Quote(market, Decimal("0.01"), Decimal("0.04"), Decimal("0.04"), "2026-09-14T14:30:00.000Z", "kalshi", False)
        ctx = context(manifest=events, quote=book, venue_capabilities={"event", "limit", "shadow"}, market_open=None)

        def check(price):
            return self.engine.check(intent(instrument=market, quantity="10", order_type="limit", limit_price=price), ctx)

        self.assertFalse([r for r in check("0.07").reasons if "deviates" in r or "through" in r])
        self.assertFalse([r for r in check("0.01").reasons if "through" in r])  # a resting bid
        self.assertIn("limit price is 0.08 through the ask of 0.04", check("0.12").reasons)
        # A resting bid commits its limit, not the ask it does not cross: 90 x 0.11 is $9.90 of
        # cash, whatever the ask says.
        wide = Quote(market, Decimal("0.10"), Decimal("0.20"), Decimal("0.20"), "2026-09-14T14:30:00.000Z", "kalshi", False)
        ctx = context(manifest=manifest(venues=["kalshi"], instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []}),
                      quote=wide, venue_capabilities={"event", "limit", "shadow"}, market_open=None, desk_equity=Decimal("87"), desk_cash=Decimal("87"))
        bid = self.engine.check(intent(instrument=market, quantity="90", order_type="limit", limit_price="0.11"), ctx)
        self.assertFalse([r for r in bid.reasons if "notional" in r], bid.reasons)
        self.assertEqual(bid.notional, Decimal("9.90"))

    def test_the_floor_loss_breaker_spares_exits_and_shadow_desks(self):
        # On Sept 16, 2026 a 2.5% live loss refused three time-stop exits and froze the shadows.
        live = manifest(venues=["alpaca"], capital={"mode": "live", "usd": "500"})
        bleeding = dict(manifest=live, floor_equity=Decimal("975"), floor_daily_pnl=Decimal("-25"), floor_max_daily_loss_pct=Decimal("0.02"))
        held = {AAPL.key: Position(AAPL, "2", "100", mark="100")}
        entry = self.engine.check(intent(quantity="1"), context(**bleeding))
        self.assertTrue(any("floor daily loss" in r for r in entry.reasons))
        exit_ = self.engine.check(intent(side="sell", quantity="2"), context(positions=held, **bleeding))
        self.assertFalse([r for r in exit_.reasons if "floor daily loss" in r], exit_.reasons)
        shadow = self.engine.check(intent(quantity="1"), context(**{**bleeding, "manifest": manifest()}))
        self.assertFalse([r for r in shadow.reasons if "floor daily loss" in r], shadow.reasons)

    def test_exposure_rules(self):
        decision = self.engine.check(intent(quantity="3"), context(desk_cash=Decimal("100")))
        self.assertTrue(any("insufficient desk cash" in r for r in decision.reasons))
        held = {AAPL.key: Position(AAPL, "2", "100", mark="100")}
        decision = self.engine.check(intent(quantity="1"), context(positions=held, desk_cash=Decimal("800")))
        self.assertTrue(any("position would be" in r for r in decision.reasons))  # 300 > 25% of 1000
        msft = Instrument("equity", "MSFT", "alpaca")
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
        live = manifest(venues=["alpaca"], capital={"mode": "live", "usd": "500"})
        ctx = context(manifest=live, floor_equity=Decimal("4500"), floor_daily_pnl=Decimal("-500"))
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


class FirmEventRuleTests(unittest.TestCase):
    """Sept 17, 2026: the floor's real losses were cheap longshots and single outsized markets."""

    TICKER = "KXHIGHAUS-26SEP17-T102"

    def setUp(self):
        self.engine = RiskEngine()
        self.yes = Instrument("event", self.TICKER, "kalshi", market_id=self.TICKER, right="yes")
        self.no = Instrument("event", self.TICKER, "kalshi", market_id=self.TICKER, right="no")
        self.events = manifest(venues=["kalshi"], instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
                               limits={**SAMPLE["limits"], "max_order_notional_pct": "1", "max_position_pct": "1", "max_gross_pct": "4"})

    def ctx(self, instrument, bid, ask, **overrides):
        book = Quote(instrument, Decimal(bid), Decimal(ask), Decimal(ask), "2026-09-14T14:30:00.000Z", "kalshi", False)
        base = dict(manifest=self.events, quote=book, venue_capabilities={"event", "limit", "shadow"}, market_open=None,
                    desk_equity=Decimal("200"), desk_cash=Decimal("200"), min_event_price="0.15",
                    max_event_market_pct="0.15", max_event_market_floor_pct="0.035", floor_equity=Decimal("750"))
        base.update(overrides)
        return context(**base)

    def buy(self, instrument, quantity, price, **extra):
        return OrderIntent.new(desk_id="earnings-01", instrument=instrument, side="buy", quantity=quantity, order_type="limit",
                               limit_price=price, rationale="t", created_at="2026-09-14T14:30:00.000Z", session_id="s", **extra)

    def reasons(self, intent_, ctx):
        return self.engine.check(intent_, ctx).reasons

    def test_a_longshot_buy_is_refused_and_the_favorite_is_not(self):
        longshot = self.reasons(self.buy(self.yes, "100", "0.02"), self.ctx(self.yes, "0.01", "0.02"))
        self.assertTrue(any("longshot" in r for r in longshot), longshot)
        favorite = self.reasons(self.buy(self.no, "10", "0.97"), self.ctx(self.no, "0.97", "0.98"))
        self.assertFalse(any("longshot" in r for r in favorite), favorite)

    def test_a_resting_bid_is_judged_at_its_limit_not_the_ask(self):
        reasons = self.reasons(self.buy(self.yes, "10", "0.12"), self.ctx(self.yes, "0.10", "0.16"))
        self.assertTrue(any("longshot" in r for r in reasons), reasons)

    def test_an_exit_buy_is_never_a_longshot(self):
        exit_buy = self.buy(self.yes, "10", "0.05", purpose="exit", exit_reason="stop", exit_of="oi-x")
        self.assertFalse(any("longshot" in r for r in self.reasons(exit_buy, self.ctx(self.yes, "0.04", "0.05"))))

    def test_one_market_is_capped_at_its_share_of_desk_equity_across_both_legs(self):
        held = {self.yes.key: Position(self.yes, Decimal("20"), Decimal("0.60"), Decimal("0.6"))}  # $12 at cost
        # $12 held + $18.50 more = $30.50 > 15% of $200
        reasons = self.reasons(self.buy(self.no, "50", "0.37"), self.ctx(self.no, "0.36", "0.37", positions=held))
        self.assertTrue(any("at risk on one market" in r for r in reasons), reasons)
        ok = self.reasons(self.buy(self.no, "40", "0.37"), self.ctx(self.no, "0.36", "0.37", positions=held))  # $26.80
        self.assertFalse(any("at risk on one market" in r for r in ok), ok)

    def test_working_buys_on_the_market_count(self):
        reasons = self.reasons(self.buy(self.no, "10", "0.95"),
                               self.ctx(self.no, "0.94", "0.95", working_event_buys={self.TICKER: Decimal("25")}))
        self.assertTrue(any("at risk on one market" in r for r in reasons), reasons)

    def test_a_live_desk_is_also_capped_by_the_live_floor(self):
        live = manifest(venues=["kalshi"], capital={"mode": "live", "usd": "400"}, instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
                        limits={**SAMPLE["limits"], "max_order_notional_pct": "1", "max_position_pct": "1", "max_gross_pct": "4"})
        # $28.50 is under 15% of a $400 desk ($60) but over 3.5% of a $750 floor ($26.25)
        reasons = self.reasons(self.buy(self.no, "30", "0.95"),
                               self.ctx(self.no, "0.94", "0.95", manifest=live, desk_equity=Decimal("400"), desk_cash=Decimal("400")))
        self.assertTrue(any("of the live floor" in r for r in reasons), reasons)

    def test_rules_are_off_when_unset(self):
        reasons = self.reasons(self.buy(self.yes, "100", "0.02"),
                               self.ctx(self.yes, "0.01", "0.02", min_event_price=0, max_event_market_pct=0, max_event_market_floor_pct=0))
        self.assertFalse(any("longshot" in r or "one market" in r for r in reasons), reasons)


class EventClusterTests(unittest.TestCase):
    """Sept 17, 2026: markets that settle on the same move in the same hour are one bet."""

    def test_crypto_series_closing_in_the_same_hour_share_a_cluster(self):
        from ltcm.risk import event_cluster

        btc = event_cluster("KXBTCD-26SEP1717-T117999.99")
        self.assertEqual(btc, "crypto:2026-09-17T21", "17:00 in New York is 21:00 UTC in September")
        self.assertEqual(event_cluster("KXETHD-26SEP1717-T4199.99"), btc)
        self.assertEqual(event_cluster("KXSOL-26SEP1717-B240"), btc)
        self.assertEqual(event_cluster("KXBTCD-26SEP1717-T1", close_time="2026-09-17T21:00:00Z"), btc, "the close time and the ticker agree")
        self.assertEqual(event_cluster("KXBTCD-26SEP1717-T1", close_time="2026-09-17T21:59:59.000Z"), btc, "truncated to the hour")
        self.assertNotEqual(event_cluster("KXETHD-26SEP1718-T4199.99"), btc, "the next hour is another bet")
        self.assertEqual(event_cluster("KXBTC-26DEC0100-B90000"), "crypto:2026-12-01T05", "standard time in December")
        self.assertEqual(event_cluster("KXBTC-26SEP171715-15"), btc, "a quarter-hour market truncates to its hour")

    def test_other_groups_series_and_the_fallbacks(self):
        from ltcm.risk import event_cluster

        self.assertEqual(event_cluster("KXHIGHNY-26SEP17-B75.5"), "weather:2026-09-17", "a date with no hour: the day")
        self.assertEqual(event_cluster("KXHIGHCHI-26SEP17-B70.5"), "weather:2026-09-17")
        self.assertEqual(event_cluster("KXGOLDD-26SEP1717-T2650"), "commod:2026-09-17T21")
        self.assertEqual(event_cluster("KXWTI-26SEP1717-T70"), "commod:2026-09-17T21")
        self.assertEqual(event_cluster("KXINXU-26SEP17H1600-T6500"), "KXINXU:2026-09-17T20", "anything else is its series")
        self.assertEqual(event_cluster("KXMLBGAME-26SEP161910NYYBOS-NYY"), "KXMLBGAME:2026-09-16T23")
        self.assertEqual(event_cluster("KXNFLGAME-26SEP20KCBUF-KC"), "KXNFLGAME:2026-09-20")
        self.assertEqual(event_cluster("KXFED-26OCT-T4.25"), "KXFED", "no day in the code: the series alone, the conservative key")
        self.assertEqual(event_cluster("KXODD"), "KXODD")
        self.assertEqual(event_cluster("KXFED-26XYZ01-T4"), "KXFED")
        self.assertEqual(event_cluster("KXBTCD-26SEP1717-T1", close_time="not a time"), "crypto:2026-09-17T21", "an unreadable close time falls back to the ticker")
        self.assertEqual(event_cluster("kxbtcd-26sep1717-t1"), "crypto:2026-09-17T21")

    def test_without_a_tz_database_new_york_time_still_converts(self):
        import sys
        from unittest import mock

        from ltcm.risk import event_cluster

        with mock.patch.dict(sys.modules, {"zoneinfo": None}):
            self.assertEqual(event_cluster("KXBTCD-26SEP1717-T1"), "crypto:2026-09-17T21")
            self.assertEqual(event_cluster("KXBTC-26DEC0100-B90000"), "crypto:2026-12-01T05")

    def test_exposure_counts_the_market_and_its_cluster(self):
        from ltcm.risk import add_event_exposure

        book = {}
        add_event_exposure(book, "KXBTCD-26SEP1717-T1", Decimal("30"))
        add_event_exposure(book, "KXETHD-26SEP1717-T2", Decimal("25"))
        add_event_exposure(book, "KXETHD-26SEP1717-T2", Decimal("0"))
        self.assertEqual(book, {"KXBTCD-26SEP1717-T1": Decimal("30"), "KXETHD-26SEP1717-T2": Decimal("25"),
                                "cluster:crypto:2026-09-17T21": Decimal("55")})


class FloorClusterRuleTests(unittest.TestCase):
    """Sept 17, 2026: `mullins` and `mullins-4` run nearly the same favorites settings, and the
    per-market cap read only the desk's own book."""

    BTC = "KXBTCD-26SEP1717-T117999.99"
    ETH = "KXETHD-26SEP1717-T4199.99"
    TICKER = FirmEventRuleTests.TICKER
    ctx = FirmEventRuleTests.ctx
    buy = FirmEventRuleTests.buy
    reasons = FirmEventRuleTests.reasons

    def setUp(self):
        FirmEventRuleTests.setUp(self)
        limits = {**SAMPLE["limits"], "max_order_notional_pct": "1", "max_position_pct": "1", "max_gross_pct": "4"}
        instruments = {**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []}
        self.live = manifest(venues=["kalshi"], capital={"mode": "live", "usd": "400"}, instruments=instruments, limits=limits)
        self.shadow = manifest(venues=["kalshi"], instruments=instruments, limits=limits)
        self.btc = Instrument("event", self.BTC, "kalshi", market_id=self.BTC, right="no")
        self.eth = Instrument("event", self.ETH, "kalshi", market_id=self.ETH, right="no")

    def floor_ctx(self, instrument, **overrides):
        base = dict(manifest=self.live, desk_equity=Decimal("400"), desk_cash=Decimal("400"), floor_equity=Decimal("979"),
                    max_event_cluster_floor_pct="0.08")
        base.update(overrides)
        return self.ctx(instrument, "0.89", "0.90", **base)

    def exposure(self, *holdings):
        from ltcm.risk import add_event_exposure

        book = {}
        for market, amount in holdings:
            add_event_exposure(book, market, Decimal(amount))
        return book

    def test_two_live_desks_holding_a_market_leave_no_room_for_a_third_order(self):
        floor = self.exposure((self.BTC, "20"), (self.BTC, "20"))  # $20 on each of two live desks
        order = self.buy(self.btc, "16", "0.9375")  # $15
        reasons = self.reasons(order, self.floor_ctx(self.btc, floor_event_exposure=floor))
        self.assertTrue(any("would put 55.00 at risk across the live desks, cap 34.26" in r for r in reasons), reasons)
        alone = self.reasons(order, self.floor_ctx(self.btc))
        self.assertFalse(any("at risk" in r for r in alone), "the desk's own book alone fits")

    def test_one_reason_when_the_desk_alone_is_over_the_floor_share(self):
        held = {self.btc.key: Position(self.btc, Decimal("30"), Decimal("0.90"), Decimal("0.9"))}  # $27 of its own
        floor = self.exposure((self.BTC, "27"), (self.BTC, "20"))
        reasons = self.reasons(self.buy(self.btc, "10", "0.90"), self.floor_ctx(self.btc, positions=held, floor_event_exposure=floor))
        self.assertEqual(len([r for r in reasons if "at risk" in r]), 1, reasons)
        self.assertTrue(any("of the live floor" in r and "across" not in r for r in reasons), reasons)

    def test_bitcoin_and_ether_closing_in_the_same_hour_are_summed(self):
        floor = self.exposure((self.BTC, "30"), (self.ETH, "30"), ("KXBTCD-26SEP1717-T118249.99", "15"))  # $75 in the 21:00 cluster
        eth_again = Instrument("event", "KXETHD-26SEP1717-T4249.99", "kalshi", market_id="KXETHD-26SEP1717-T4249.99", right="no")
        reasons = self.reasons(self.buy(eth_again, "5", "0.90"), self.floor_ctx(eth_again, floor_event_exposure=floor))  # $4.50 more
        self.assertTrue(any("crypto:2026-09-17T21 would put 79.50 at risk across the live desks, cap 78.32" in r for r in reasons), reasons)
        later = Instrument("event", "KXETHD-26SEP1718-T4249.99", "kalshi", market_id="KXETHD-26SEP1718-T4249.99", right="no")
        self.assertFalse(any("at risk" in r for r in self.reasons(self.buy(later, "5", "0.90"), self.floor_ctx(later, floor_event_exposure=floor))),
                         "the next hour's market is another cluster")

    def test_the_desks_own_book_counts_toward_its_cluster_without_the_floor_map(self):
        held = {self.btc.key: Position(self.btc, Decimal("40"), Decimal("0.90"), Decimal("0.9"))}  # $36 (a legacy position)
        reasons = self.reasons(self.buy(self.eth, "30", "0.90"),
                               self.floor_ctx(self.eth, positions=held, working_event_buys={"KXSOLD-26SEP1717-T240": Decimal("20")},
                                              max_event_market_floor_pct=0))
        self.assertTrue(any("crypto:2026-09-17T21 would put 83.00" in r for r in reasons), reasons)

    def test_a_shadow_desk_is_never_checked(self):
        floor = self.exposure((self.BTC, "200"))
        reasons = self.reasons(self.buy(self.btc, "16", "0.9375"), self.floor_ctx(self.btc, manifest=self.shadow, floor_event_exposure=floor))
        self.assertFalse(any("across the live desks" in r for r in reasons), reasons)

    def test_exits_are_never_refused(self):
        floor = self.exposure((self.BTC, "200"), (self.ETH, "200"))
        held = {self.btc.key: Position(self.btc, Decimal("40"), Decimal("0.90"), Decimal("0.9"))}
        sell = OrderIntent.new(desk_id="earnings-01", instrument=self.btc, side="sell", quantity="40", order_type="limit", limit_price="0.89",
                               rationale="t", created_at="2026-09-14T14:30:00.000Z", session_id="s")
        self.assertFalse(any("at risk" in r for r in self.reasons(sell, self.floor_ctx(self.btc, positions=held, floor_event_exposure=floor))))
        exit_buy = self.buy(self.eth, "10", "0.90", purpose="exit", exit_reason="stop", exit_of="oi-x")
        self.assertFalse(any("at risk" in r for r in self.reasons(exit_buy, self.floor_ctx(self.eth, floor_event_exposure=floor))))

    def test_a_held_leg_with_no_close_hour_counts_against_every_hour_it_could_close_in(self):
        """Sept 17, 2026 review: a ticker with no readable hour was keyed `crypto` or
        `crypto:2026-09-17`, and only a key spelled the same way was ever summed with it, so an
        hourly order's cluster cap never saw it."""
        order = self.buy(self.eth, "5", "0.90")  # $4.50 in crypto:2026-09-17T21
        for held, why in (("KXBTCMAXY-26SEP17-T120000", "a date and no hour"), ("KXDOGE-ODD", "no readable code at all")):
            floor = self.exposure((self.BTC, "40"), (held, "35"))
            reasons = self.reasons(order, self.floor_ctx(self.eth, floor_event_exposure=floor, max_event_market_floor_pct=0))
            self.assertTrue(any("crypto:2026-09-17T21 would put 79.50 at risk across the live desks" in r for r in reasons), (why, reasons))
        # The desk's own book is read the same way when the floor's map is missing.
        dated = Instrument("event", "KXBTCMAXY-26SEP17-T120000", "kalshi", market_id="KXBTCMAXY-26SEP17-T120000", right="no")
        held = {self.btc.key: Position(self.btc, Decimal("40"), Decimal("1"), Decimal("1")),
                dated.key: Position(dated, Decimal("35"), Decimal("1"), Decimal("1"))}
        reasons = self.reasons(order, self.floor_ctx(self.eth, positions=held, max_event_market_floor_pct=0))
        self.assertTrue(any("crypto:2026-09-17T21 would put 79.50" in r for r in reasons), reasons)
        # A date-only order sums every hour of its day and the next UTC day, and nothing further.
        weekly = Instrument("event", "KXETHMAXW-26SEP17-T5000", "kalshi", market_id="KXETHMAXW-26SEP17-T5000", right="no")
        floor = self.exposure((self.BTC, "40"), ("KXETHD-26SEP1801-T4199.99", "35"))  # 17:00 and 01:00 New York: 21:00 and 05:00 UTC
        reasons = self.reasons(self.buy(weekly, "5", "0.90"), self.floor_ctx(weekly, floor_event_exposure=floor, max_event_market_floor_pct=0))
        self.assertTrue(any("crypto:2026-09-17 would put 79.50" in r for r in reasons), reasons)
        far = self.exposure(("KXBTCD-26SEP2017-T1", "75"))
        self.assertFalse(any("at risk" in r for r in self.reasons(self.buy(weekly, "5", "0.90"), self.floor_ctx(weekly, floor_event_exposure=far, max_event_market_floor_pct=0))))

    def test_clusters_overlap_when_they_could_be_the_same_hour(self):
        from ltcm.risk import cluster_at_risk, clusters_overlap

        self.assertTrue(clusters_overlap("crypto:2026-09-17T21", "crypto:2026-09-17T21"))
        self.assertFalse(clusters_overlap("crypto:2026-09-17T21", "crypto:2026-09-17T22"))
        self.assertFalse(clusters_overlap("crypto:2026-09-17T21", "commod:2026-09-17T21"))
        self.assertTrue(clusters_overlap("crypto", "crypto:2026-09-17T21"), "no time: every hour of the group")
        self.assertTrue(clusters_overlap("crypto:2026-09-17T21", "crypto"))
        self.assertTrue(clusters_overlap("weather:2026-09-17", "weather:2026-09-17T02"))
        self.assertTrue(clusters_overlap("weather:2026-09-17", "weather:2026-09-18T10"), "a US day runs into the next UTC date")
        self.assertFalse(clusters_overlap("weather:2026-09-17", "weather:2026-09-19T01"))
        self.assertFalse(clusters_overlap("weather:2026-09-17", "weather:2026-09-16T23"))
        self.assertFalse(clusters_overlap("weather:2026-09-17", "weather:2026-09-18"))
        self.assertTrue(clusters_overlap("KXFED:26-XX", "KXFED:2026-09-17T21"), "a time it cannot read overlaps")
        book = {"KXA": Decimal("9"), "cluster:crypto:2026-09-17T21": Decimal("5"), "cluster:crypto": Decimal("2"),
                "cluster:crypto:2026-09-17": Decimal("3"), "cluster:crypto:2026-09-17T22": Decimal("7"), "floor:unreadable": Decimal("1")}
        self.assertEqual(cluster_at_risk(book, "crypto:2026-09-17T21"), Decimal("10"))

    def test_a_live_desks_unreadable_book_refuses_a_live_event_buy_and_never_an_exit(self):
        from ltcm.risk import FLOOR_BOOK_UNREADABLE

        floor = {FLOOR_BOOK_UNREADABLE: Decimal("1")}
        reasons = self.reasons(self.buy(self.eth, "1", "0.90"), self.floor_ctx(self.eth, floor_event_exposure=floor))
        self.assertTrue(any("could not be read" in r for r in reasons), reasons)
        exit_buy = self.buy(self.eth, "1", "0.90", purpose="exit", exit_reason="stop", exit_of="oi-x")
        self.assertFalse(any("could not be read" in r for r in self.reasons(exit_buy, self.floor_ctx(self.eth, floor_event_exposure=floor))))
        shadow = self.reasons(self.buy(self.eth, "1", "0.90"), self.floor_ctx(self.eth, manifest=self.shadow, floor_event_exposure=floor))
        self.assertFalse(any("could not be read" in r for r in shadow))

    def test_the_floor_rule_is_off_at_zero(self):
        floor = self.exposure((self.BTC, "200"))
        reasons = self.reasons(self.buy(self.btc, "16", "0.9375"),
                               self.floor_ctx(self.btc, floor_event_exposure=floor, max_event_market_floor_pct=0, max_event_cluster_floor_pct=0))
        self.assertFalse(any("at risk" in r for r in reasons), reasons)


class FuturesShortTests(unittest.TestCase):
    """leap: futures -- shorts are for futures; a spot coin is never sold short (Sept 17, 2026)."""

    def test_a_short_sale_of_spot_crypto_is_refused_even_when_the_venue_can_short(self):
        from ltcm.risk import RiskEngine
        engine = RiskEngine()
        shorting = manifest(instruments={**SAMPLE["instruments"], "allow_short": True, "asset_classes": ["crypto", "future"]}, venues=["coinbase"])
        coin = Instrument("crypto", "ETH-USD", "coinbase", market_id="ETH-USD")
        ctx = context(manifest=shorting, venue_capabilities={"crypto", "future", "limit", "short"}, market_open=None,
                      quote=Quote(instrument=coin, bid=Decimal("2440"), ask=Decimal("2441"), last=Decimal("2440"), as_of="2026-09-17T00:00:00Z", source="t"))
        decision = engine.check(intent(side="sell", quantity="1", order_type="limit", limit_price="2441", instrument=coin), ctx)
        self.assertFalse(decision.approved)
        self.assertTrue(any("cannot be sold short" in r for r in decision.reasons), decision.reasons)
        future = Instrument("future", "ETP-20DEC30-CDE", "coinbase", multiplier=Decimal("0.1"), market_id="ETP-20DEC30-CDE")
        ctx = context(manifest=shorting, venue_capabilities={"crypto", "future", "limit", "short"}, market_open=None,
                      quote=Quote(instrument=future, bid=Decimal("2440"), ask=Decimal("2441"), last=Decimal("2440"), as_of="2026-09-17T00:00:00Z", source="t"))
        decision = engine.check(intent(side="sell", quantity="1", order_type="limit", limit_price="2440", instrument=future), ctx)
        self.assertFalse(any("short" in r for r in decision.reasons), decision.reasons)
