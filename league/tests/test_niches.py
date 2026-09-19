"""Specialties: one niche for life, a universe that follows the season, research that compounds.

The owner's design of Sept 19, 2026: a swarm of specialists, each spending its whole research
budget on one corner of one venue, kept broad enough (one niche for all sports results) that the
calendar cannot leave a specialist with nothing to trade.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from league import niches, seeds
from league.agents import NAME
from league.commons import Commons
from league.ledger import Ledger
from league.runner import needs_of
from league.safety import check_code
from league.tests.test_house import BUYER, HouseCase
from league.venues import instrument_for


class TheFile(unittest.TestCase):
    def setUp(self):
        self.niches = niches.load()

    def test_every_founder_builds_is_safe_and_declares_needs_inside_its_specialty(self):
        names = []
        for niche in self.niches.values():
            for founder in niche.founders:
                code = niches.founder_code(seeds.load(founder["seed"]), niche, founder)
                check_code(code)
                info = needs_of(code)
                self.assertTrue(info["ok"], (founder["key"], info))
                needs = info["needs"]
                self.assertEqual(needs["venue"], niche.venue)
                self.assertIn(needs["horizon"], niche.horizons, founder["key"])
                self.assertTrue(needs[niche.key] and set(needs[niche.key]) <= set(niche.universe), founder["key"])
                self.assertLessEqual(len(needs[niche.key]), niches.MAX_UNIVERSE)
                self.assertEqual(niches.constrain(needs, niche)[niche.key], needs[niche.key])  # already inside: unchanged
                self.assertTrue(NAME.match(niche.desk), niche.desk)
                names.append(founder["key"])
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 20)

    def test_a_founders_program_is_its_seeds_below_the_literals(self):
        niche = self.niches["kalshi-sports"]
        founder = next(f for f in niche.founders if f["key"] == "football-favorites")
        seed = seeds.load(founder["seed"])
        code = niches.founder_code(seed, niche, founder)
        self.assertEqual(code.split("def decide(ctx):", 1)[1], seed.split("def decide(ctx):", 1)[1] + ("" if seed.endswith("\n") else "\n"))
        self.assertTrue(code.startswith("# SPECIALTY: kalshi-sports"))
        self.assertIn("# Founder football-favorites of the Meriwether desk", code)
        self.assertEqual(needs_of(code)["needs"]["series"][:2], ["KXNCAAFGAME", "KXNFLGAME"])
        self.assertEqual(needs_of(code)["params"]["min_volume_24h"], 5000)

    def test_no_series_or_symbol_is_in_two_specialties(self):
        seen = {}
        for niche in self.niches.values():
            for item in niche.listed:
                self.assertNotIn((niche.venue, niche.asset_class, item), seen, f"{item} is in {niche.id} and {seen.get((niche.venue, niche.asset_class, item))}")
                seen[(niche.venue, niche.asset_class, item)] = niche.id

    def test_every_pattern_compiles_and_claims_its_own_listed_series_only(self):
        kalshi = [n for n in self.niches.values() if n.venue == "kalshi"]
        for niche in kalshi:
            for pattern in niche.patterns:
                re.compile(pattern)
            for other in kalshi:
                if other is not niche:
                    strays = [s for s in other.listed if niche.fits(s)]
                    self.assertEqual(strays, [], f"{niche.id}'s patterns would claim {other.id}'s {strays[:3]}")

    def test_sports_is_one_broad_niche_that_a_new_season_joins_by_pattern(self):
        sports = self.niches["kalshi-sports"]
        for series in ("KXNBAGAME", "KXNHLTOTAL", "KXNCAAMBGAME", "KXUCLGAME", "KXVALORANTMAP"):
            self.assertTrue(sports.fits(series), series)
        for series in ("KXBTCD", "KXHIGHNY", "KXNFLTD", "KXAAAGASD"):
            self.assertFalse(sports.fits(series), series)
        self.assertGreaterEqual(sports.max_members, 8)

    def test_options_are_open_long_premium_only_and_paper_is_their_replay(self):
        options = self.niches["alpaca-options"]
        self.assertFalse(options.dormant)
        self.assertFalse(options.replay)
        self.assertEqual([f["key"] for f in options.founders], ["options-breakout", "options-pullback"])
        self.assertEqual(options.desk, "krasker")
        self.assertIn("LONG PREMIUM ONLY", options.brief)
        call = instrument_for("alpaca", {"occ": "F260925C00013000"})
        self.assertTrue(options.holds(call))
        self.assertFalse(options.holds(instrument_for("alpaca", {"symbol": "F"})))  # the stock itself is not the specialty
        self.assertFalse(options.holds(instrument_for("alpaca", {"occ": "NVDA260925C00200000"})))
        self.assertFalse(self.niches["alpaca-megacaps"].holds(instrument_for("alpaca", {"occ": "NVDA260925C00200000"})))

    def test_the_brief_tells_a_member_which_series_charge_makers(self):
        text = self.niches["kalshi-sports"].text()
        self.assertIn("KXNFLGAME", text.split("MAKER fee")[1].split(".")[0])
        self.assertIn("No series of this specialty charges a maker fee", self.niches["kalshi-weather"].text())
        self.assertNotIn("maker fee", self.niches["alpaca-megacaps"].text().split("YOUR SPECIALTY")[1].split("Your universe")[0].lower().replace("maker round trip", ""))


class Constrain(unittest.TestCase):
    def setUp(self):
        self.niches = niches.load()
        self.weather = self.niches["kalshi-weather"]

    def needs(self, **kw):
        return {"venue": "kalshi", "horizon": "day", "style": "x", "series": ["KXHIGHNY"], **kw}

    def test_a_strategy_cannot_leave_its_niche_by_declaring_another_venue_or_horizon(self):
        with self.assertRaisesRegex(ValueError, "trades kalshi"):
            niches.constrain(self.needs(venue="alpaca"), self.weather)
        with self.assertRaisesRegex(ValueError, "judged by the day"):
            niches.constrain(self.needs(horizon="hour"), self.weather)

    def test_what_it_asks_to_see_is_cut_to_the_universe(self):
        out = niches.constrain(self.needs(series=["KXNFLGAME", "kxhighny", "KXHIGHCHI", "KXHIGHNY"]), self.weather)
        self.assertEqual(out["series"], ["KXHIGHNY", "KXHIGHCHI"])

    def test_naming_nothing_inside_shows_the_head_of_the_universe_and_never_more_than_twelve(self):
        out = niches.constrain(self.needs(series=["KXNFLGAME"]), self.weather)
        self.assertEqual(out["series"], list(self.weather.universe[:12]))

    def test_match_places_a_strategy_by_what_it_asks_to_see_and_never_in_a_dormant_niche(self):
        self.assertEqual(niches.match({"venue": "alpaca", "horizon": "day", "symbols": ["SPY", "NVDA", "QQQ"]}, self.niches).id, "alpaca-index-etfs")
        self.assertEqual(niches.match({"venue": "kalshi", "horizon": "day", "series": ["KXEPLGAME"]}, self.niches).id, "kalshi-sports")
        self.assertIsNone(niches.match({"venue": "kalshi", "horizon": "day", "series": ["KXFEDDECISION"]}, self.niches))
        self.assertIsNone(niches.match({"venue": "kalshi", "horizon": "hour", "series": ["KXEPLGAME"]}, self.niches))  # sports is judged by the day
        self.assertIsNone(niches.match({"venue": "alpaca", "horizon": "day", "symbols": ["F", "SOFI"]}, self.niches))  # only options hold those, and it did not say options
        self.assertEqual(niches.match({"venue": "alpaca", "horizon": "day", "asset_class": "option", "symbols": ["SPY", "F"]}, self.niches).id, "alpaca-options")
        self.assertEqual(niches.match({"venue": "alpaca", "horizon": "day", "symbols": ["SPY"]}, self.niches).id, "alpaca-index-etfs")  # the same ticker, as shares

    def test_holds(self):
        sports, etfs, majors = self.niches["kalshi-sports"], self.niches["alpaca-index-etfs"], self.niches["alpaca-crypto-majors"]
        self.assertTrue(sports.holds(instrument_for("kalshi", {"market": "KXNFLGAME-26SEP20CLETB-TB"})))
        self.assertFalse(sports.holds(instrument_for("kalshi", {"market": "KXBTCD-26SEP1912-T87299.99"})))
        self.assertTrue(etfs.holds(instrument_for("alpaca", {"symbol": "SPY"})))
        self.assertFalse(etfs.holds(instrument_for("alpaca", {"symbol": "BTC/USD"})))
        self.assertFalse(etfs.holds(instrument_for("alpaca", {"symbol": "SPY", "expiry": "2026-10-16", "strike": "650", "right": "call"})))  # an option is not the ETF
        self.assertTrue(majors.holds(instrument_for("alpaca-paper", {"symbol": "BTC/USD"})))


class Seasons(unittest.TestCase):
    NOW = 1_789_000_000.0

    def iso(self, hours):
        from league.tapes import iso
        return iso(self.NOW + hours * 3600)

    def test_the_survey_counts_what_resolves_inside_the_window_by_series(self):
        class Listing:
            def __init__(self, pages):
                self.pages, self.calls = pages, []

            def markets(self, **kw):
                self.calls.append(kw)
                index = int(kw.get("cursor") or 0)
                return {"markets": self.pages[index], "cursor": str(index + 1) if index + 1 < len(self.pages) else ""}

        game = dict(can_close_early=True)
        listing = Listing([
            [{"ticker": "KXNBAGAME-A-X", "event_ticker": "KXNBAGAME-A", "close_time": self.iso(60), "expiration_time": self.iso(5), "volume_24h": 900, **game},
             {"ticker": "KXNBAGAME-A-Y", "event_ticker": "KXNBAGAME-A", "close_time": self.iso(60), "expiration_time": self.iso(5), "volume_24h": 100, **game}],
            [{"ticker": "KXNBAGAME-B-X", "event_ticker": "KXNBAGAME-B", "close_time": self.iso(110), "expiration_time": self.iso(70), "volume_24h": 5000, **game},  # next week's
             {"ticker": "KXHIGHNY-1", "event_ticker": "KXHIGHNY-26", "close_time": self.iso(20), "expiration_time": self.iso(34), "volume_24h": 50},
             {"ticker": "BAD", "event_ticker": "KXBAD-1", "close_time": "never", "volume_24h": 1}],
        ])
        self.assertEqual(niches.survey(listing, clock=lambda: self.NOW), {"KXNBAGAME": 1000.0, "KXHIGHNY": 50.0})
        self.assertEqual(listing.calls[0]["max_close_ts"], int(self.NOW + 48 * 3600) + 72 * 3600)

    def test_a_new_season_joins_by_pattern_and_category_and_the_universe_is_ranked_by_what_trades_now(self):
        ns = niches.load()
        asked = []

        def category_of(series):
            asked.append(series)
            return {"KXNBAGAME": "Sports", "KXFAKETOTAL": "Economics", "KXTINYGAME": "Sports"}.get(series)

        volumes = {"KXNBAGAME": 9e6, "KXEPLGAME": 5e6, "KXNFLGAME": 7e6, "KXFAKETOTAL": 8e6, "KXTINYGAME": 100.0, "KXHIGHNY": 4e4, "KXUNKNOWNGAME": 3e6}
        live = niches.apply_survey(ns, volumes, category_of)
        self.assertEqual(live["kalshi-sports"], ["KXNBAGAME", "KXNFLGAME", "KXEPLGAME"])  # the NBA joined, and leads
        self.assertEqual(ns["kalshi-sports"].universe[:3], ("KXNBAGAME", "KXNFLGAME", "KXEPLGAME"))
        self.assertIn("KXMLBGAME", ns["kalshi-sports"].universe)  # dark today, still inside
        self.assertEqual(live["kalshi-weather"], ["KXHIGHNY"])
        self.assertNotIn("KXTINYGAME", asked)  # too thin to be worth a question
        self.assertTrue(ns["kalshi-sports"].holds(instrument_for("kalshi", {"market": "KXNBAGAME-26OCT21BOSNYK-BOS"})))
        # A stranger with a sporting name and another category, or none Kalshi will vouch for, stays out.
        for stranger in ("KXFAKETOTAL", "KXUNKNOWNGAME"):
            self.assertNotIn(stranger, ns["kalshi-sports"].universe)


class Library(unittest.TestCase):
    def test_a_specialists_own_niche_comes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "l.sqlite")
            commons = Commons(ledger)
            body = "Heavy favourites above ninety cents were safe in this sample of settled markets."
            commons.library_write("weather-1", "Favourites above ninety cents in weather", body, niche="kalshi-weather")
            commons.library_write("sports-1", "Favourites above ninety cents in football", body, niche="kalshi-sports")
            first = lambda niche: commons.library_search("favourites ninety cents", niche=niche)["results"][0]
            self.assertEqual((first("kalshi-weather")["niche"], first("kalshi-sports")["niche"]), ("kalshi-weather", "kalshi-sports"))
            self.assertEqual(len(commons.library_search("favourites ninety cents", niche="kalshi-sports")["results"]), 2)  # the rest is still shared
            ledger.close()


OUTSIDER = BUYER.replace("test-buyer", "test-outsider").replace('"symbol": "BTC/USD", "side": "buy"', '"symbol": "SPY", "side": "buy"')


class InTheHouse(HouseCase):
    def test_the_founders_are_the_niches_founders_with_a_family_a_program_a_specialty(self):
        rows = self.house.founders()
        self.assertEqual(len(rows), sum(len(n.founders) for n in self.house.niches.values()))
        by_key = {r["key"]: r for r in rows}
        self.assertEqual((by_key["favorites-daily"]["family"], by_key["favorites-daily"]["niche"]), ("kalshi-favorites", "kalshi-weather"))
        self.assertEqual((by_key["football-favorites"]["family"], by_key["soccer-favorites"]["family"]), ("sports-favorites", "sports-favorites"))
        self.assertEqual(by_key["alts-trend"]["family"], "crypto-alts-trend")
        # Every agent of a desk is numbered from one partner's name.
        self.assertEqual({r["name"] for r in rows if r["niche"] == "kalshi-sports"}, {"meriwether"})
        self.assertEqual(by_key["options-breakout"]["name"], "krasker")

    def test_a_birth_is_placed_by_its_needs_and_a_child_inherits(self):
        parent = self.seated()
        self.assertEqual(parent.specialty, "alpaca-crypto-majors")
        child = self.house.spawn("child", "test-family", BUYER, parent=parent.id, reason="test")
        self.assertEqual(child.specialty, "alpaca-crypto-majors")

    def test_a_strategy_in_no_open_specialty_is_not_born(self):
        nowhere = BUYER.replace('"symbols": ["BTC/USD"]', '"symbols": ["ZZZZ"]')
        with self.assertRaisesRegex(ValueError, "no open specialty"):
            self.house.spawn("nowhere", "test-family", nowhere, reason="test")
        self.house.niches["alpaca-options"].dormant, self.house.niches["alpaca-options"].dormant_reason = True, "closed for the test"
        with self.assertRaisesRegex(ValueError, "not open yet: closed for the test"):
            self.house.spawn("optioneer", "test-family", BUYER, reason="test", specialty="alpaca-options")

    def test_an_entry_outside_the_specialty_is_dropped_and_said_so(self):
        agent = self.house.spawn("outsider", "test-family", OUTSIDER, reason="test")  # a crypto specialist that tries to buy SPY
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        summary = self.house.tick()
        self.assertEqual(summary["orders"], 0)
        woke = [e.payload for e in self.house.ledger.iter(kinds="agent.woke", agent=agent.id)]
        self.assertIn("outside the alpaca-crypto-majors specialty", json.dumps(woke))

    def test_a_desk_numbers_its_agents_and_a_child_takes_the_next_number(self):
        born = self.house.found(["meriwether"])
        self.assertEqual([a.id for a in born], ["meriwether", "meriwether-2", "meriwether-3", "meriwether-4", "meriwether-5", "meriwether-6"])
        self.assertEqual({a.line for a in born}, {"meriwether"})
        self.assertEqual([a.founder for a in born][:2], ["football-favorites", "football-longshot-no"])
        self.assertEqual(self.house.found(["meriwether"]), [])  # idempotent, though six share the name
        parent = born[2]
        self.house.economy.grant(parent.id, "10", "test")
        self.house.niches["kalshi-sports"].max_members = 20
        child = self.house.fork(parent)
        self.assertEqual((child.id, child.line, child.parent), ("meriwether-7", "meriwether", parent.id))

    def test_a_full_specialty_has_no_more_children(self):
        parent = self.seated()
        self.house.economy.grant(parent.id, "10", "test")
        self.house.niches["alpaca-crypto-majors"].max_members = 1
        self.assertIsNone(self.house.fork(parent))
        self.house.niches["alpaca-crypto-majors"].max_members = 2
        self.assertIsNotNone(self.house.fork(parent))

    def test_the_niche_floor_is_paid_by_specialty(self):
        agent = self.seated()
        self.assertEqual([s.niche for s in self.house.standings() if s.agent == agent.id], ["alpaca-crypto-majors"])

    def test_the_live_universe_outlives_a_restart(self):
        self.house._state["niche_live"] = {"kalshi-sports": ["KXNBAGAME", "KXNFLGAME"]}
        self.house._save_state()
        self.house.close(wait=None)
        self.house = self.new_house()
        self.assertEqual(self.house.niches["kalshi-sports"].universe[:2], ("KXNBAGAME", "KXNFLGAME"))

    def test_an_agent_whose_series_are_dark_is_shown_the_busiest_live_series_of_its_specialty(self):
        class Listing:
            def __init__(self):
                self.asked = []

            def markets(self, series, *, max_hours_to_close):
                self.asked.append(list(series))
                return [{"market": "KXNBAGAME-26OCT21BOSNYK-BOS"}] if "KXNBAGAME" in series else []

        base = self.seated()
        self.house.kalshi_data = listing = Listing()
        fan = type(base)(**{**base.__dict__, "venue": "kalshi", "horizon": "day", "specialty": "kalshi-sports",
                            "needs": {"venue": "kalshi", "horizon": "day", "series": ["KXMLBGAME"], "max_hours_to_close": 30}})
        book = self.house.books["alpaca-paper"]
        self.assertEqual(self.house.snapshot(fan, book)["markets"], [])  # no survey yet: nothing to fall back on
        self.house.niches["kalshi-sports"].live = ("KXNBAGAME", "KXNHLGAME")
        self.house._data_cache.clear()
        ctx = self.house.snapshot(fan, book)
        self.assertEqual(ctx["markets"], [{"market": "KXNBAGAME-26OCT21BOSNYK-BOS"}])
        self.assertIn("busiest live series of your specialty", ctx["note"])
        self.assertEqual(listing.asked[-1], ["KXNBAGAME", "KXNHLGAME"])

    def test_research_is_told_the_specialty(self):
        agent = self.seated()
        text = self.house.niche_of(agent).text()
        self.assertIn("YOUR SPECIALTY: Bitcoin and ether on Alpaca", text)
        self.assertIn("0.25%", text)


if __name__ == "__main__":
    unittest.main()
