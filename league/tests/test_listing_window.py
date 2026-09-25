"""The Kalshi listing window a strategy may opt into (Sept 25, 2026, the Kalshi-scale run's K1):
`min_hours_to_close` and `max_markets` in NEEDS.

A Kalshi wake is shown the soonest markets to close, 200 at most, and a game market's
`hours_to_close` runs to the game's expected END (three hours after the start on nearly every game of
the weekend of Sept 26-27, 2026). Measured on that slate: from the noon kickoffs on Saturday the 200
markets a college-football strategy was shown were all games in progress -- none it could still enter
-- and during the Sunday 1 PM games the same held for the NFL. These tests hold the two keys to what
they say, live and in replay alike, to the House's cache, to the birth that refuses them out of bounds,
and to the rule that a strategy declaring neither is shown exactly what it was.
"""

from __future__ import annotations

import json
import unittest

from league import niches
from league.replay import run_replay
from league.tapes import KalshiData, iso, listing_window, parse_time
from league.tests.test_house import HouseCase
from league.tests.test_tapes import FakeMarketData, live

NOW = parse_time("2026-09-26T16:00:00Z")
# Four games, two markets each, expected to end this many hours after NOW (a game in progress ends
# within three hours; one about to start, three hours after its kickoff).
ENDS = {"26SEP26AAABBB": 1.5, "26SEP26CCCDDD": 2.99, "26SEP26EEEFFF": 3.2, "26SEP26GGGHHH": 5.0}


def rows() -> list:
    return [live(f"KXNCAAFSPREAD-{code}-{code[7:10]}{n}", "0.40", "0.44", "2026-09-28T17:00:00Z", can_close_early=True,
                 expected_expiration_time=iso(NOW + hours * 3600)) for code, hours in ENDS.items() for n in (3, 7)]


def program(window: str = "") -> str:
    """A strategy that remembers the markets its first wake was shown, in order."""
    return ('NEEDS = {"venue": "kalshi", "horizon": "day", "style": "window-test", "series": ["KXNCAAFSPREAD"], '
            f'"max_hours_to_close": 30, "wake_minutes": 10{window}}}\nPARAMS = {{}}\n\n'
            'def decide(ctx):\n'
            '    memory = ctx.get("memory") or {}\n'
            '    seen = memory.get("seen") or [row["market"] for row in ctx.get("markets") or []]\n'
            '    return {"intents": [], "thought": "watching", "memory": {"seen": seen}}\n')


WINDOW = ', "min_hours_to_close": 3.0, "max_markets": 3'


class LiveAndReplayAgree(unittest.TestCase):
    def tape(self) -> dict:
        step = [{"market": row["ticker"], "series": "KXNCAAFSPREAD", "title": row["title"], "yes_bid": 0.40, "yes_ask": 0.44,
                 "yes_ask_low": 0.40, "yes_bid_high": 0.44, "close_time": row["expected_expiration_time"], "volume_24h": 1000.0,
                 "open_interest": 10.0, "strike": 2.5} for row in reversed(rows())]  # not in close order on the tape
        return {"venue": "kalshi", "horizon": "day", "step_seconds": 300,
                "steps": [{"t": iso(NOW + 300 * i), "markets": [dict(m) for m in step]} for i in range(3)],
                "results": {m["market"]: "no" for m in step}}

    def replayed(self, code: str) -> list:
        result = run_replay(code, {}, self.tape(), stake=200.0, audit=True)
        self.assertTrue(result["ok"], result.get("error"))
        return result["final_memory"]["seen"]

    def test_a_replay_step_shows_what_a_live_wake_is_shown(self):
        listing = KalshiData(FakeMarketData({"KXNCAAFSPREAD": [rows()]}), clock=lambda: NOW)
        shown = [row["market"] for row in listing.markets(["KXNCAAFSPREAD"], max_hours_to_close=30, min_hours_to_close=3.0, limit=3)]
        self.assertEqual(shown, ["KXNCAAFSPREAD-26SEP26EEEFFF-EEE3", "KXNCAAFSPREAD-26SEP26EEEFFF-EEE7",
                                 "KXNCAAFSPREAD-26SEP26GGGHHH-GGG3"])
        self.assertEqual(self.replayed(program(WINDOW)), shown)

    def test_a_floor_the_live_wake_reads_as_absent_is_absent_in_replay(self):
        # A floor at or over max_hours_to_close is refused at birth; NEEDS that reach a replay anyway (a direct
        # run, an old record) are shown what a live wake shows them: every market, as if the floor were absent.
        self.assertEqual(listing_window({"max_hours_to_close": 30, "min_hours_to_close": 30}), (0.0, 200))
        self.assertEqual(self.replayed(program(', "min_hours_to_close": 30')), self.replayed(program()))
        self.assertEqual(self.replayed(program(', "min_hours_to_close": True')), self.replayed(program()))  # a bool is no number

    def test_a_replay_without_the_keys_is_unchanged(self):
        # The tape's own order, every market inside max_hours_to_close, uncapped: what it always showed.
        self.assertEqual(self.replayed(program()), [m["market"] for m in self.tape()["steps"][0]["markets"]])


class InTheHouse(HouseCase):
    class Listing:
        """A Kalshi listing that says what it was asked. `strict` answers only the arguments every
        listing was asked before the window existed."""

        def __init__(self, strict: bool = False):
            self.asked, self.strict = [], strict

        def markets(self, series, *, max_hours_to_close, max_age=None, **window):
            if self.strict and window:
                raise TypeError(f"unexpected {sorted(window)}")
            self.asked.append((list(series), max_hours_to_close, window))
            return [{"market": f"{series[0]}-26SEP26AAABBB-AAA3", "series": series[0]}]

    def spawn(self, window: str):
        return self.house.spawn("", "window-family", program(window), reason="test")

    def test_the_wake_asks_for_the_declared_window_and_caches_it_apart(self):
        self.house.kalshi_data = listing = self.Listing()
        agent = self.spawn(', "min_hours_to_close": 3.0, "max_markets": 500')
        self.assertEqual((agent.specialty, agent.needs["min_hours_to_close"], agent.needs["max_markets"]), ("kalshi-sports", 3.0, 500))
        self.house.snapshot(agent, self.house.books["alpaca-paper"])
        self.assertEqual(listing.asked, [(["KXNCAAFSPREAD"], 30.0, {"min_hours_to_close": 3.0, "limit": 500})])
        self.assertIn("markets:KXNCAAFSPREAD:30.0:3.0:500", self.house._data_cache)
        self.assertNotIn("markets:KXNCAAFSPREAD:30.0", self.house._data_cache)

    def test_a_strategy_without_the_keys_is_asked_and_cached_as_before(self):
        self.house.kalshi_data = listing = self.Listing(strict=True)
        agent = self.spawn("")
        ctx = self.house.snapshot(agent, self.house.books["alpaca-paper"])
        self.assertEqual(ctx["markets"], [{"market": "KXNCAAFSPREAD-26SEP26AAABBB-AAA3", "series": "KXNCAAFSPREAD"}])
        self.assertEqual(listing.asked, [(["KXNCAAFSPREAD"], 30.0, {})])
        self.assertEqual([key for key in self.house._data_cache if key.startswith("markets:")], ["markets:KXNCAAFSPREAD:30.0"])

    def test_a_birth_is_refused_a_window_out_of_bounds(self):
        for window, why in ((', "min_hours_to_close": 30', "under max_hours_to_close (30)"),
                            (', "min_hours_to_close": -1', "at least 0"),
                            (', "max_markets": 501', "from 1 to 500"),
                            (', "max_markets": 2.5', "from 1 to 500")):
            with self.subTest(window=window), self.assertRaisesRegex(ValueError, "cannot show this listing: .*" + why.replace("(", r"\(").replace(")", r"\)")):
                self.spawn(window)


class TheFounders(unittest.TestCase):
    def test_each_consensus_founder_declares_a_window_inside_its_bounds(self):
        desk = niches.load()["kalshi-sports"]
        window = {f["key"]: (f["needs"]["min_hours_to_close"], f["needs"]["max_markets"]) for f in desk.founders if f["key"].startswith("consensus-")}
        # Measured: 306 of 346 NCAAF events, all 15 MLS, 65 of 67 MLB and 30 of 45 NFL events expire 3.00 hours after the
        # start; Liga MX has one at 0.83, and the soccer slates fit in 200 markets either way.
        self.assertEqual(window, {"consensus-nfl": (3.0, 500), "consensus-ncaaf": (3.0, 500), "consensus-mlb": (3.0, 300),
                                  "consensus-mls": (0.5, 200), "consensus-ligamx": (0.5, 200)})
        for founder in desk.founders:
            self.assertEqual(niches.constrain({**json.loads(json.dumps(founder.get("needs") or {})), "venue": "kalshi", "horizon": "day"},
                                              desk).get("max_markets"), (founder.get("needs") or {}).get("max_markets"))


if __name__ == "__main__":
    unittest.main()
