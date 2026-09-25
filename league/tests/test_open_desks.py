"""Open desks (Workstream F, Sept 23, 2026): one desk a venue whose universe is the whole venue.

The owner: "I don't want to force the agents into any predefined strategies that would be too
rigid ... design the most aggressive incentivized and resource rich environment for them to find
that alpha." `kalshi-open` and `alpaca-open` hold every tradable market of their venue, take eight
seats each, and are where a program that spans desks (or names markets no desk lists) is born. An
open-desk agent is still shown only what it names, and is staked exactly like any other.
"""

import json
import unittest
from decimal import Decimal

from league import feeds, history, niches
from league.ledger import now_iso
from league.tests.test_allocator import IDLE, HouseCaseReal
from league.tests.test_house import HouseCase
from league.tests.test_hypotheses import PASSER, FoundryCase, candidate
from league.venues import instrument_for

D = Decimal


def code_for(symbols, *, venue="alpaca", horizon="hour", style="open-test", key=None, extra=""):
    key = key or ("series" if venue == "kalshi" else "symbols")
    return (f'NEEDS = {{"venue": "{venue}", "horizon": "{horizon}", "style": "{style}", "{key}": {json.dumps(list(symbols))}, '
            f'"wake_minutes": 5{extra}}}\nPARAMS = {{}}\n\ndef decide(ctx):\n    return {{"intents": [], "thought": "waiting"}}\n')


class TheDesks(unittest.TestCase):
    def setUp(self):
        self.niches = niches.load()
        self.kalshi, self.alpaca = self.niches["kalshi-open"], self.niches["alpaca-open"]

    def test_one_open_desk_a_venue_with_its_seats_both_horizons_and_no_planted_strategy(self):
        opened = sorted(n.id for n in self.niches.values() if n.open)
        self.assertEqual(opened, ["alpaca-open", "kalshi-open"])
        # Twelve seats on the Alpaca desk since Sept 25, 2026 (S2 of the forward-first run); the Kalshi desk's row is the
        # Kalshi-scale run's (eight at the time).
        self.assertEqual((self.alpaca.max_members, self.kalshi.max_members >= 8), (12, True))
        for desk in (self.kalshi, self.alpaca):
            self.assertEqual((desk.horizons, desk.founders, desk.dormant, desk.replay), (("hour", "day"), (), False, True))
            self.assertEqual(desk.listed, ())  # not a hard-coded list: the whole venue
        self.assertEqual(self.alpaca.asset_classes, ("equity", "crypto"))  # never options: the options desk's rules
        self.assertNotIn("option", self.alpaca.asset_classes)
        self.assertEqual(len({n.desk for n in self.niches.values()}), len(self.niches))  # every desk numbers its own line

    def test_an_open_desk_row_that_claims_options_patterns_or_founders_is_refused(self):
        import tempfile
        from pathlib import Path

        doc = json.loads(niches.NICHES_PATH.read_text(encoding="utf-8"))
        for bad in ({"asset_classes": ["equity", "option"]}, {"patterns": ["^KX"]}, {"founders": [{"seed": "x", "key": "x"}]}, {"asset_class": "equity"}):
            rows = [dict(r) for r in doc["niches"]]
            row = next(r for r in rows if r["id"] == ("kalshi-open" if "patterns" in bad else "alpaca-open"))
            row.update(bad)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "niches.json"
                path.write_text(json.dumps({**doc, "niches": rows}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "open desk"):
                    niches.load(path)

    def test_the_kalshi_open_desk_holds_any_series_and_nothing_of_another_venue(self):
        desk = self.kalshi
        for ticker in ("KXFEDDECISION-26OCT-H0", "KXBTCD-26SEP1912-T87299.99", "KXNFLGAME-26SEP20CLETB-TB", "KXYTTOPVIDEO2D-26SEP24-A"):
            self.assertTrue(desk.holds(instrument_for("kalshi", {"market": ticker})), ticker)
            self.assertTrue(desk.holds(instrument_for("kalshi-shadow", {"market": ticker, "leg": "no"})), ticker)
        self.assertFalse(desk.holds(instrument_for("kalshi", {"market": "KXMVENFLMULTIGAMEEXTENDED-26SEP-X"})))  # combos
        self.assertFalse(desk.holds(instrument_for("kalshi", {"market": "BTC/USD"})))   # a coin pair is Alpaca's
        self.assertFalse(desk.holds(instrument_for("alpaca", {"symbol": "SPY"})))       # another venue's instrument
        self.assertFalse(desk.holds(instrument_for("alpaca-paper", {"symbol": "BTC/USD"})))

    def test_the_alpaca_open_desk_holds_any_stock_etf_or_dollar_coin_and_no_option(self):
        desk = self.alpaca
        for venue in ("alpaca", "alpaca-paper"):
            for symbol in ("SPY", "COIN", "BRK.B", "NVDA", "F", "BTC/USD", "PEPE/USD", "BTC-USD"):
                self.assertTrue(desk.holds(instrument_for(venue, {"symbol": symbol})), (venue, symbol))
        self.assertFalse(desk.holds(instrument_for("alpaca", {"occ": "F260925C00013000"})))       # the options desk's
        self.assertFalse(desk.holds(instrument_for("alpaca", {"symbol": "BTC/EUR"})))              # coins against the dollar only
        self.assertFalse(desk.holds(instrument_for("alpaca", {"symbol": "KXBTCD-26SEP1912-T87299.99"})))  # a Kalshi ticker
        self.assertFalse(desk.holds(instrument_for("kalshi", {"market": "KXBTCD-26SEP1912-T87299.99"})))
        # The fixed desks are unchanged: an open desk widens nothing but itself.
        self.assertFalse(self.niches["alpaca-crypto-majors"].holds(instrument_for("alpaca", {"symbol": "PEPE/USD"})))
        self.assertFalse(self.niches["alpaca-index-etfs"].holds(instrument_for("alpaca", {"symbol": "COIN"})))

    def test_constrain_keeps_what_it_names_twelve_at_most_and_drops_what_the_venue_cannot_list(self):
        named = [f"KXSERIES{i}" for i in range(15)]
        out = niches.constrain({"venue": "kalshi", "horizon": "hour", "series": ["kxfeddecision", "BTC/USD", "KXMVECOMBO"] + named}, self.kalshi)
        self.assertEqual(out["series"], ["KXFEDDECISION"] + named[:11])
        mixed = niches.constrain({"venue": "alpaca", "horizon": "day", "symbols": ["COIN", "btc/usd", "BTC/EUR", "SPY"]}, self.alpaca)
        self.assertEqual(mixed["symbols"], ["COIN", "BTC/USD", "SPY"])
        with self.assertRaisesRegex(ValueError, "trades alpaca"):
            niches.constrain({"venue": "kalshi", "horizon": "day", "series": ["KXFEDDECISION"]}, self.alpaca)

    def test_naming_nothing_it_may_trade_shows_the_head_of_a_capped_discovery_list(self):
        # Alpaca: derived from the other Alpaca desks (what the House records history for), coins first.
        found = niches.constrain({"venue": "alpaca", "horizon": "hour", "symbols": ["BTC/EUR"]}, self.alpaca)
        self.assertEqual(len(found["symbols"]), niches.MAX_UNIVERSE)
        self.assertEqual(found["symbols"][:2], ["BTC/USD", "ETH/USD"])
        self.assertLessEqual(len(self.alpaca.universe), niches.OPEN_DISCOVERY)
        options_only = set(self.niches["alpaca-options"].listed) - {s for n in self.niches.values() if not n.open and n.asset_class != "option" for s in n.listed}
        self.assertFalse(options_only & set(self.alpaca.universe))  # an options underlier is not offered as shares by default
        # Kalshi: nothing until the survey has run; never the whole venue.
        self.assertEqual(niches.constrain({"venue": "kalshi", "horizon": "day", "series": []}, self.kalshi)["series"], [])

    def test_match_prefers_a_specific_desk_when_one_holds_most_of_what_it_names(self):
        ns = self.niches
        home = lambda **needs: (niches.match(needs, ns).id if niches.match(needs, ns) else None)  # noqa: E731
        self.assertEqual(home(venue="alpaca", horizon="day", symbols=["SPY", "NVDA", "QQQ"]), "alpaca-index-etfs")  # 2 of 3
        self.assertEqual(home(venue="alpaca", horizon="hour", symbols=["BTC/USD", "ETH/USD", "SPY"]), "alpaca-crypto-majors")
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXHIGHNY", "KXHIGHCHI", "KXAAAGASD"]), "kalshi-weather")
        self.assertEqual(home(venue="kalshi", horizon="hour", series=["KXBTCD"]), "kalshi-crypto-strikes")
        # Spanning desks, or naming what no desk lists: the open desk of the venue.
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXHIGHNY", "KXAAAGASD"]), "kalshi-open")
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXBTCD", "KXBTC15M"]), "kalshi-open")
        self.assertEqual(home(venue="kalshi", horizon="hour", series=["KXFEDDECISION"]), "kalshi-open")
        self.assertEqual(home(venue="alpaca", horizon="hour", symbols=["BTC/USD", "SPY"]), "alpaca-open")
        self.assertEqual(home(venue="alpaca", horizon="hour", symbols=["BTC/USD", "PEPE/USD"]), "alpaca-open")
        self.assertEqual(home(venue="alpaca", horizon="day", symbols=["COIN"]), "alpaca-open")
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXHIGHNY", "BTC/USD"]), "kalshi-weather")  # a stray is no evidence
        # A new season's series the survey has not added yet is still its desk's by pattern (three
        # sports cards of the last 108 on the floor, Sept 23, 2026, named one beside a listed one).
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXMLBTOTAL", "KXARGPREMDIVTOTAL"]), "kalshi-sports")
        # ... but a desk that can show it none of it yet is no home: the open desk can.
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXUCLWGAME"]), "kalshi-open")
        # The open desk is not a way around a desk's clock, nor a home for options or for nothing.
        self.assertIsNone(home(venue="kalshi", horizon="hour", series=["KXEPLGAME"]))           # sports is judged by the day
        self.assertEqual(home(venue="kalshi", horizon="hour", series=["KXHIGHNY", "KXHIGHCHI", "KXBTCD"]), "kalshi-crypto-strikes")  # as before
        self.assertEqual(home(venue="alpaca", horizon="day", asset_class="option", symbols=["F", "SOFI"]), "alpaca-options")
        self.assertIsNone(home(venue="alpaca", horizon="day", asset_class="option", symbols=["COIN"]))
        self.assertIsNone(home(venue="alpaca", horizon="hour", symbols=["BTC/EUR"]))
        self.assertIsNone(home(venue="alpaca", horizon="hour", symbols=[]))
        # A dormant open desk seats nobody: the old rule answers.
        ns["kalshi-open"].dormant = True
        self.assertEqual(home(venue="kalshi", horizon="day", series=["KXHIGHNY", "KXAAAGASD"]), "kalshi-weather")
        self.assertIsNone(home(venue="kalshi", horizon="day", series=["KXFEDDECISION"]))

    def test_spanning_is_what_the_lab_asks(self):
        self.assertEqual(niches.spanning({"venue": "kalshi", "horizon": "day", "series": ["KXHIGHNY", "KXNFLGAME"]}, self.niches).id, "kalshi-open")
        self.assertEqual(niches.spanning({"venue": "alpaca", "horizon": "hour", "symbols": ["SOL/USD", "COIN"]}, self.niches).id, "alpaca-open")
        self.assertIsNone(niches.spanning({"venue": "kalshi", "horizon": "day", "series": ["KXHIGHNY"]}, self.niches))
        self.assertIsNone(niches.spanning({"venue": "alpaca", "horizon": "hour", "symbols": ["BTC/EUR"]}, self.niches))

    def test_the_survey_gives_the_kalshi_open_desk_a_capped_discovery_list_that_claims_nothing(self):
        volumes = {"KXNFLGAME": 9e6, "KXHIGHNY": 5e4, "KXFEDDECISION": 8e6, "KXYTTOPVIDEO2D": 12849.5, "KXTHIN": 100.0,
                   "KXMVESPORTS": 7e6, **{f"KXNEW{i}": 3e5 - i for i in range(40)}}
        category = {"KXNFLGAME": "Sports"}.get
        baseline = niches.load()
        without = niches.apply_survey({k: v for k, v in baseline.items() if not v.open}, volumes, category)
        live = niches.apply_survey(self.niches, volumes, category)
        self.assertEqual({k: v for k, v in live.items() if k != "kalshi-open"}, without)  # it takes nothing from any desk
        found = live["kalshi-open"]
        self.assertEqual(len(found), niches.OPEN_DISCOVERY)
        self.assertEqual(found[:2], ["KXFEDDECISION", "KXNEW0"])  # the busiest no desk covers, first
        self.assertNotIn("KXMVESPORTS", found)  # combos never
        self.assertNotIn("KXTHIN", found)       # nor what hardly trades
        self.assertEqual(self.kalshi.universe, tuple(found))
        small = {"KXNFLGAME": 9e6, "KXFEDDECISION": 8e6, "KXHIGHNY": 5e4}
        self.assertEqual(niches.apply_survey(niches.load(), small, category)["kalshi-open"], ["KXFEDDECISION", "KXNFLGAME", "KXHIGHNY"])
        # And it is what a strategy naming nothing it may trade is shown, twelve at most.
        self.assertEqual(niches.constrain({"venue": "kalshi", "horizon": "day", "series": ["BTC/USD"]}, self.kalshi)["series"], found[:12])

    def test_the_desks_that_follow_a_listed_universe_ignore_the_open_desks(self):
        before = {k: v for k, v in niches.load().items() if not v.open}
        self.assertEqual(feeds.perp_coins(self.niches), feeds.perp_coins(before))
        self.assertEqual(feeds.sports_plan(self.niches), feeds.sports_plan(before))
        self.assertNotIn("COIN", history.niche_symbols())  # the history store's universe is the listed desks'

    def test_research_is_told_what_an_open_desk_allows(self):
        text = self.kalshi.text()
        self.assertIn("YOUR SPECIALTY: The open Kalshi desk", text)
        self.assertIn("EVERY series Kalshi lists", text)
        self.assertNotIn("No series of this specialty charges a maker fee", text)  # some do: the schedule says which
        self.alpaca.live = self.alpaca.live[:3]
        text = self.alpaca.text()
        self.assertIn("never an option", text)
        self.assertIn("BTC/USD, ETH/USD, SOL/USD", text)
        from league.rules import rules_text
        from league.economy import load_game
        self.assertIn("OPEN desk (kalshi-open, alpaca-open", rules_text(load_game()))


OPEN_BUYER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "open-buyer", "symbols": ["BTC/USD", "COIN"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {"notional": 20.0}

def decide(ctx):
    return {"intents": [], "thought": "waiting"}
'''


class InTheHouse(HouseCase):
    def test_a_spanning_strategy_is_born_on_the_open_desk_and_keeps_what_it_names(self):
        agent = self.house.spawn("", "open-family", OPEN_BUYER, reason="test")
        self.assertEqual((agent.specialty, agent.id), ("alpaca-open", "london"))
        self.assertEqual(agent.needs["symbols"], ["BTC/USD", "COIN"])
        # Mostly one desk's: born there, the stray name cut, as always.
        mostly = OPEN_BUYER.replace('["BTC/USD", "COIN"]', '["BTC/USD", "ETH/USD", "COIN"]')
        other = self.house.spawn("", "open-family", mostly, reason="test")
        self.assertEqual((other.specialty, other.needs["symbols"]), ("alpaca-crypto-majors", ["BTC/USD", "ETH/USD"]))

    def test_an_architects_spanning_strategy_is_enrolled_on_the_open_desk(self):
        from league import strategies

        rows = [{"name": "coin-and-coinbase", "family": "cross-asset", "why": "a test strategy", "code": OPEN_BUYER}]
        real = strategies.all_strategies
        strategies.all_strategies = lambda: rows
        try:
            born = self.house.enroll()
        finally:
            strategies.all_strategies = real
        self.assertEqual([(a.id, a.specialty, a.founder) for a in born], [("london", "alpaca-open", "coin-and-coinbase")])

    def seat_open(self, code=OPEN_BUYER):
        agent = self.house.spawn("", "open-family", code, reason="test", specialty="alpaca-open")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.seat(agent)
        return agent

    def test_an_open_desk_entry_in_any_market_of_its_venue_is_accepted_and_another_venues_refused(self):
        # In the regular session: outside it no stock entry is sent (the wake skip, Sept 24, 2026).
        self.clock.now = 1789000000.0 + 13.6 * 3600  # 2026-09-10 14:02Z, 10:02 in New York
        self.broker.clock_iso = now_iso(self.clock)
        agent = self.seat_open()
        book = self.house.books["alpaca-paper"]
        for symbol, bid, ask in (("COIN", "250", "250.10"), ("PEPE/USD", "0.00001", "0.0000101"), ("XLE", "90", "90.02")):
            self.broker.set_quote(instrument_for("alpaca-paper", {"symbol": symbol}), bid, ask)
        rows = [{"symbol": s, "side": "buy", "notional_usd": 20.0, "type": "market", "reason": "test"} for s in ("COIN", "PEPE/USD", "XLE", "BTC/USD")]
        intents, dropped = self.house._intents(agent, book, rows)
        self.assertEqual(dropped, [])
        self.assertEqual(sorted(i.instrument.market_id or i.instrument.symbol for i in intents), ["BTC/USD", "COIN", "PEPE/USD", "XLE"])
        foreign = [{"symbol": "KXBTCD-26SEP1912-T87299.99", "side": "buy", "notional_usd": 20.0, "type": "market", "reason": "a Kalshi ticker"},
                   {"market": "KXBTCD-26SEP1912-T87299.99", "leg": "yes", "side": "buy", "quantity": 1, "type": "market", "reason": "as Kalshi says it"},
                   {"occ": "F260925C00013000", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.2, "reason": "an option"}]
        intents, dropped = self.house._intents(agent, book, foreign)
        self.assertEqual(intents, [])
        self.assertEqual(len(dropped), 3)
        self.assertIn("outside the alpaca-open specialty", " ".join(dropped))

    def test_a_fixed_desk_still_refuses_what_only_the_open_desk_may_trade(self):
        agent = self.seated()  # alpaca-crypto-majors
        self.broker.set_quote(instrument_for("alpaca-paper", {"symbol": "COIN"}), "250", "250.10")
        intents, dropped = self.house._intents(agent, self.house.books["alpaca-paper"],
                                               [{"symbol": "COIN", "side": "buy", "notional_usd": 20.0, "type": "market", "reason": "test"}])
        self.assertEqual(intents, [])
        self.assertIn("outside the alpaca-crypto-majors specialty", " ".join(dropped))

    def test_capacity_is_twelve(self):
        niche = self.house.niches["alpaca-open"]
        self.assertEqual(niche.max_members, 12)  # eight until Sept 25, 2026 (S2 of the forward-first run)
        agents = [self.seat_open(OPEN_BUYER.replace("open-buyer", f"open-buyer-{i}")) for i in range(11)]
        parent = agents[0]
        self.house.economy.grant(parent.id, "10", "test")
        child = self.house.fork(parent)
        self.assertIsNotNone(child)  # the twelfth seat
        self.assertEqual((child.specialty, self.house.members("alpaca-open")), ("alpaca-open", 12))
        self.house.economy.grant(parent.id, "10", "test")
        self.assertIsNone(self.house.fork(parent))  # full: no niche may crowd out the rest

    def test_an_open_desk_wake_asks_the_venue_only_for_what_it_names(self):
        asked = {"bars": [], "quotes": []}

        class Alpaca:
            def bars(self, symbols, timeframe, **kw):
                asked["bars"].append(list(symbols)); return {s: [] for s in symbols}

            def quotes(self, symbols):
                asked["quotes"].append(list(symbols)); return {s: {"bid": 1.0, "ask": 1.01} for s in symbols}

        self.house.alpaca_data = Alpaca()
        many = [f"S{chr(65 + i)}" for i in range(12)] + ["BTC/USD"]
        agent = self.seat_open(OPEN_BUYER.replace('["BTC/USD", "COIN"]', json.dumps(many)))
        self.assertEqual(len(agent.needs["symbols"]), niches.MAX_UNIVERSE)  # held to twelve at birth
        self.house.snapshot(agent, self.house.books["alpaca-paper"])
        self.assertEqual(asked["bars"], [many[:12]])
        self.assertEqual(asked["quotes"], [many[:12]])

    def test_a_kalshi_open_desk_wake_is_bounded_and_falls_back_to_the_discovery_list(self):
        class Listing:
            def __init__(self):
                self.asked = []

            def markets(self, series, *, max_hours_to_close, max_age=None):
                self.asked.append(list(series))
                return [{"market": "KXNEW0-26SEP24-A"}] if "KXNEW0" in series else []

        self.house.kalshi_data = listing = Listing()
        code = code_for(["KXFEDDECISION", "KXHIGHNY"], venue="kalshi", horizon="day", extra=', "max_hours_to_close": 30')
        agent = self.house.spawn("", "open-family", code, reason="test")
        self.assertEqual(agent.specialty, "kalshi-open")  # spans weather and a series no desk lists
        book = self.house.books["alpaca-paper"]
        self.assertEqual(self.house.snapshot(agent, book)["markets"], [])  # both dark, and no survey yet: nothing, never the venue
        self.assertEqual(listing.asked, [["KXFEDDECISION", "KXHIGHNY"]])
        volumes = {f"KXNEW{i}": 3e5 - i for i in range(30)}
        niches.apply_survey(self.house.niches, volumes, lambda s: None)
        self.house._data_cache.clear()
        ctx = self.house.snapshot(agent, book)
        self.assertEqual(ctx["markets"], [{"market": "KXNEW0-26SEP24-A"}])
        self.assertEqual(listing.asked[-1], [f"KXNEW{i}" for i in range(niches.MAX_UNIVERSE)])
        self.assertTrue(all(len(call) <= niches.MAX_UNIVERSE for call in listing.asked))

    def test_a_floor_surveyed_before_the_open_desk_existed_surveys_again_within_the_half_hour(self):
        """Deployed onto a floor whose last survey was hours ago, the open desk would otherwise have
        no discovery list until the next day's survey."""
        rows = [{"ticker": "KXFEDDECISION-26OCT-H0", "event_ticker": "KXFEDDECISION-26OCT", "close_time": None, "volume_24h": 9000}]

        class Market:
            def markets(self, **kw):
                return {"markets": [dict(r, close_time=now_iso(clock)) for r in rows], "cursor": ""}

        from league.ledger import now_iso
        clock = lambda: self.clock() + 3600  # noqa: E731 - closes an hour from now
        self.house.kalshi_data = type("K", (), {"market_data": Market()})()
        old = {n.id: [] for n in self.house.niches.values() if n.venue == "kalshi" and not n.open}
        self.house._state.update(niche_live=old, last_niche_survey=self.clock(), last_niche_try=self.clock())
        self.assertFalse(self.house.survey_due())  # tried just now
        self.clock.advance(1801)
        self.assertTrue(self.house.survey_due())   # not tomorrow: the open desk has never been surveyed
        live = self.house.survey_niches()
        self.assertEqual(live["kalshi-open"], ["KXFEDDECISION"])
        self.assertFalse(self.house.survey_due())
        self.clock.advance(23 * 3600)
        self.assertFalse(self.house.survey_due())  # and then once a day, as before

    def test_a_shut_session_offers_an_open_desk_its_coins_only(self):
        from unittest.mock import patch

        agent = self.seat_open()
        ctx = {"now": "2026-09-26T12:00:00Z", "quotes": {"BTC/USD": {"bid": 1, "ask": 2}, "COIN": {"bid": 1, "ask": 2}}}
        with patch("league.house.market_open_at", return_value=False):
            self.assertEqual(self.house._offered(agent, ctx), 1)
        with patch("league.house.market_open_at", return_value=True):
            self.assertEqual(self.house._offered(agent, ctx), 2)
        coins = self.seat_open(OPEN_BUYER.replace('"COIN"', '"SOL/USD"'))
        self.assertFalse(self.house.niche_of(coins).keeps_hours(coins.needs))
        self.assertTrue(self.house.niche_of(agent).keeps_hours(agent.needs))


class TheFoundry(FoundryCase):
    """The foundry may write for an open desk like any desk, and a card that belongs to one desk is
    refused there before a replay is bought."""

    DESK = "alpaca-open"

    def setUp(self):
        super().setUp()
        spanning = PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["BTC/USD", "COIN"]').replace("sawtooth", "spanning")
        self.frontier.candidates = [candidate("spanning", "the sawtooth on a coin, read against a stock no desk lists", spanning),
                                    candidate("sawtooth", "the sawtooth on the majors alone", PASSER)]

    def test_a_spanning_card_is_replayed_and_born_there_and_a_one_desk_card_is_refused(self):
        self.call()
        outcomes = {c["name"]: self.foundry.evaluations()[c["id"]] for c in self.foundry.cards().values()}
        self.assertEqual(outcomes["spanning"]["outcome"], "passed")
        self.assertEqual(outcomes["sawtooth"]["outcome"], "invalid")
        self.assertIn("alpaca-crypto-majors desk", outcomes["sawtooth"]["detail"])
        shown = self.frontier.asked[0]["user"]["desk"]
        self.assertEqual((shown["id"], shown["universe"][:2]), ("alpaca-open", ["BTC/USD", "ETH/USD"]))
        self.assertIn("no one desk can hold", shown["brief"])
        # The passer takes an open-desk seat by the ordinary refill, on paper, with all it names.
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.seated()  # the league is never empty in production
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        card = self.card_of("spanning")
        self.assertEqual((child.id, child.specialty, child.founder), (card["line_id"], "alpaca-open", f"card:{card['id']}"))
        self.assertEqual(child.needs["symbols"], ["BTC/USD", "COIN"])
        self.assertEqual(self.house.evaluator.rung(child.id), 1)

    def test_the_packet_for_an_unsurveyed_kalshi_open_desk_still_builds(self):
        packet = self.foundry.packet("kalshi-open")
        self.assertEqual((packet["desk"]["id"], packet["desk"]["universe"]), ("kalshi-open", []))


class TheAllocator(HouseCaseReal):
    """Crowding is the allocator's to price: an open-desk agent gets no way around the envelope."""

    def test_an_open_desk_agent_is_bunted_and_staked_exactly_like_any_other(self):
        house = self.house
        fixed = self.agent("fixed", code=IDLE)
        opened = house.spawn("", "alloc-test", IDLE.replace("idle-test", "idle-open"), reason="test", endowment="2.5", specialty="alpaca-open")
        house.evaluator.seat(opened.id, 1, "test: straight to paper")
        house._state["tried"][opened.id] = opened.code_sha256
        self.assertEqual((fixed.specialty, opened.specialty), ("alpaca-crypto-majors", "alpaca-open"))
        table = {a.id: dict(e=1.10, w_paper=1.21, paper_trades=6) for a in (fixed, opened)}
        with self.evidence_of(table):
            self.tick()
        real = house.books["alpaca"]
        for agent in (fixed, opened):
            self.assertEqual(house.evaluator.rung(agent.id), 2, agent.id)
            self.assertEqual(real.account(agent.id).staked, D("25"))
            self.assertEqual(real.limits[agent.id].max_position_usd, D("12.50"))
            self.assertEqual(real.limits[agent.id].asset_classes, real.limits[fixed.id].asset_classes)
            # An unproven family's agent is seated as a probe (Sept 24, 2026); on Alpaca a probe is $25 too.
            self.assertEqual(house.allocator.board()["agents"][agent.id]["band"], "probe")
        self.assertEqual(house.allocator.target_stake(opened, "swing", None), house.allocator.target_stake(fixed, "swing", None))
        self.assertLessEqual(house.allocator.committed("alpaca"), house.allocator.capital("alpaca"))
        # And it goes back to paper on the same evidence that sends any other bunt back (past the one-loss
        # trial: three real results in its stay, Sept 24, 2026).
        table = {a.id: dict(e=0.80, w_paper=1.21, w_real=0.73, paper_trades=6, real_trades=3, real_stay_closed=3) for a in (fixed, opened)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual([house.evaluator.rung(a.id) for a in (fixed, opened)], [1, 1])

    def test_the_envelope_binds_an_open_desk_agent_like_any_other(self):
        from unittest.mock import patch
        from league.constitution import CONSTITUTION

        tuition = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "25"})
        tuition.start()
        self.addCleanup(tuition.stop)
        fixed = self.agent("fixed", code=IDLE)
        opened = house_spawn = self.house.spawn("", "alloc-test", IDLE.replace("idle-test", "idle-open"), reason="test",
                                                 endowment="2.5", specialty="alpaca-open")
        self.house.evaluator.seat(house_spawn.id, 1, "test")
        self.house._state["tried"][house_spawn.id] = house_spawn.code_sha256
        table = {fixed.id: dict(e=1.20, w_paper=1.4, paper_trades=6), opened.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(fixed.id), self.house.evaluator.rung(opened.id)), (2, 1))  # one $25 bunt fits
        self.assertEqual(self.house._state["promotion_status"][opened.id]["stage"], "envelope")


if __name__ == "__main__":
    unittest.main()
