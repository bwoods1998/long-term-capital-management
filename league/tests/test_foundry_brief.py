"""E2 and E3 of the close-the-gaps run (Sept 24, 2026): the foundry brief `foundry-2026-09-24.1`.

The evidence (docs/goals/LTCM_CLOSE_THE_GAPS.md, gap 1): every kalshi-crypto-15m family was negative on its
pooled record at T0 (crypto-15m-favorites n 106, bound -0.0064) and kalshi-crypto-strikes ran -10.3% an
active block; the one family with real profit, resting bids on 0.90-0.97 weather favourites, earned about
$1.41 a day and had a measured capacity of about $7.81 a day; Deploy B recorded the data the desks had
asked for (weather ensembles, NWS forecasts, 8-K earnings times, SOFR and par yields, ESPN odds, DVOL and
funding). These tests hold: model-versus-market cards that name the recorded feeds and state their fee and
the edge that clears it; no card on the two crypto desks until a family there is positive forward over three
active blocks; the weather family scaled on the ensemble's fair value as the first transfer to try; and a
family at its measured capacity gets no House mutation and is marked in the packet.
"""

from __future__ import annotations

from unittest.mock import patch

from league.economy import load_game
from league.hypotheses import DESK_FEEDS, FOUNDRY_BRIEF, PROMPT_VERSION
from league.tests import test_hypotheses
from league.tests.test_hypotheses import PASSER, WEATHER, FoundryCase, candidate


class TransferCase(FoundryCase):
    """The transfer tests' House (a Kalshi practice book too) and helpers, without their tests."""

    new_house = test_hypotheses.Transfer.new_house
    settings = test_hypotheses.Transfer.settings
    member = test_hypotheses.Transfer.member
    earn_on = test_hypotheses.Transfer.earn_on

ENSEMBLE = ("Price every Kalshi weather series (daily highs, lows, rain) from the ensemble members' forecasts "
            "and bid, post-only, where the model's probability clears the ask and the fee.")


class Brief(FoundryCase):
    def test_cards_are_model_versus_market_and_state_their_fee_and_the_edge_that_clears_it(self):
        self.assertEqual(PROMPT_VERSION, "foundry-2026-09-24.1")
        for words in ("MODEL VERSUS MARKET", "recorded_feeds", "edge_needed", "at_capacity"):
            self.assertIn(words, FOUNDRY_BRIEF)
        silent = {k: v for k, v in candidate("silent", "a sawtooth that names no fee", PASSER).items() if k not in ("fee", "edge_needed")}
        self.frontier.candidates = [silent, candidate("sawtooth", "the recorded sawtooth, fee and edge stated", PASSER)]
        out = self.call()
        self.assertEqual(len(out["cards"]), 1)
        self.assertIn("the fee it pays and the edge it needs", out["refused"][0])
        card = self.card_of("sawtooth")
        self.assertTrue(card["fee"] and card["edge_needed"])

    def test_the_packet_names_the_recorded_feeds_of_its_desk(self):
        self.call()
        shown = self.frontier.asked[0]["user"]["data"]["recorded_feeds"]
        self.assertEqual([f["feed"] for f in shown], list(DESK_FEEDS[self.DESK]))
        vol = next(f for f in shown if f["feed"] == "vol")
        self.assertIn("NEEDS['feeds']", vol["declare"])
        self.assertIn("history", vol["replay"])  # DVOL is backfilled: a replay judges it now
        self.assertEqual(DESK_FEEDS["kalshi-weather"], ("weather", "nws", "forecast"))
        self.assertIn("earnings", DESK_FEEDS["alpaca-megacaps"])
        self.assertIn("rates", DESK_FEEDS["kalshi-open"])
        self.assertIn("odds", DESK_FEEDS["kalshi-sports"])

    def test_the_game_file_sends_calls_to_the_deep_markets_and_closes_the_two_crypto_desks(self):
        foundry = load_game()["hypotheses"]
        self.assertEqual(set(foundry["fast_desks"]),
                         {"alpaca-megacaps", "alpaca-index-etfs", "alpaca-crypto-majors", "alpaca-open", "kalshi-open"})
        self.assertEqual(set(foundry["closed_desks"]), {"kalshi-crypto-strikes", "kalshi-crypto-15m"})
        self.assertEqual(foundry["closed_reopen_blocks"], 3)
        self.assertEqual((foundry["first_transfer"]["family"], foundry["first_transfer"]["desk"]), ("weather-favorites", "kalshi-weather"))


class ClosedDesks(TransferCase):
    def test_no_card_on_a_closed_desk_until_a_family_there_is_positive_over_three_blocks(self):
        self.settings(closed_desks=[self.DESK], exploration_share=0, fast_share=0, transfer_share=0)
        self.assertIn(self.DESK, self.foundry._closed_desks())
        picked = {self.foundry.allocate(fresh=True)[0].niche for _ in range(3)}
        self.assertNotIn(self.DESK, picked)
        member = self.member("reopener", "majors-maker", PASSER, specialty=self.DESK)
        self.earn_on(member, "alpaca-paper", growth=0.002, n=2)
        self.clock.advance(301)  # the House's pooled forward records are read every five minutes
        self.assertIn(self.DESK, self.foundry._closed_desks())  # two positive blocks are not three
        self.earn_on(member, "alpaca-paper", growth=0.002, n=1)
        self.clock.advance(301)
        self.assertEqual(self.foundry._closed_desks(), {})

    def test_a_family_reopens_a_closed_desk_only_on_its_record_there(self):
        """The review of #262: `House.family_forward` pools a family over every desk it lives on (kalshi-favorites lives
        on kalshi-crypto-strikes and kalshi-weather at T4): its blocks elsewhere are no forward record on the closed desk."""
        self.settings(closed_desks=[self.DESK], exploration_share=0, fast_share=0, transfer_share=0)
        self.member("stayer", "shared-family", PASSER, specialty=self.DESK)
        away = self.member("traveller", "shared-family", PASSER, specialty="alpaca-index-etfs")
        for hour in range(4):
            self.house.ledger.append("eval.block", {"log_growth": 0.01, "active": True, "book": "alpaca-paper",
                                                    "key": f"2026-09-10T0{hour}"}, agent=away.id)
        self.clock.advance(301)
        self.assertIn("active blocks there", self.foundry._closed_desks()[self.DESK])

    def test_members_active_in_one_hour_are_one_block_of_their_family(self):
        """The review of #262: three members of one family active in the same hour (T4: huang-hd8ff7c-3, -4 and -5 at
        2026-09-24T04) are one forward block of the family, not three; three hours are three."""
        self.settings(closed_desks=[self.DESK], exploration_share=0, fast_share=0, transfer_share=0)
        members = [self.member(name, "sibling-family", PASSER, specialty=self.DESK) for name in ("sib-one", "sib-two", "sib-three")]
        for member in members:
            self.house.ledger.append("eval.block", {"log_growth": 0.01, "active": True, "book": "alpaca-paper",
                                                    "key": "2026-09-10T04"}, agent=member.id)
        self.clock.advance(301)
        self.assertIn(self.DESK, self.foundry._closed_desks())
        for hour in ("05", "06"):
            self.house.ledger.append("eval.block", {"log_growth": 0.01, "active": True, "book": "alpaca-paper",
                                                    "key": f"2026-09-10T{hour}"}, agent=members[0].id)
        self.clock.advance(301)
        self.assertEqual(self.foundry._closed_desks(), {})

    def test_a_desk_whose_families_lose_stays_closed(self):
        self.settings(closed_desks=[self.DESK])
        member = self.member("loser", "majors-taker", PASSER, specialty=self.DESK)
        self.earn_on(member, "alpaca-paper", growth=-0.002, n=6)
        self.clock.advance(301)
        self.assertIn("positive forward record over 3", self.foundry._closed_desks()[self.DESK])


class FirstTransfer(TransferCase):
    def test_the_weather_family_is_scaled_on_the_ensemble_first_then_ports_go_on(self):
        self.settings(transfer_share=1.0, fast_share=0, exploration_share=0,
                      first_transfer={"family": "weather-favorites", "desk": "kalshi-weather", "mechanism": ENSEMBLE,
                                      "feeds": ["weather", "nws", "forecast"]})
        weather = self.member("mullins", "weather-favorites", WEATHER, specialty="kalshi-weather",
                              why="resting maker bids on daily weather favourites above 90 cents")
        self.earn_on(weather, "kalshi-shadow", growth=0.01)
        desk, route, reason = self.foundry.allocate(fresh=True)
        self.assertEqual((desk.niche, route), ("kalshi-weather", "transfer"))
        self.assertIn("first transfer", reason)
        self.foundry.run(desk.niche, route, reason)
        self.house.wait()
        shown = self.frontier.asked[-1]["user"]
        self.assertTrue(shown["transfer"]["scale"])
        self.assertEqual(shown["transfer"]["feeds"], ["weather", "nws", "forecast"])
        self.assertIn("ensemble", shown["transfer"]["ask"])
        self.assertNotIn("never_tried_here", shown["transfer"])
        self.assertEqual([f["feed"] for f in shown["data"]["recorded_feeds"]], ["weather", "nws", "forecast"])
        call = [e.payload for e in self.house.ledger.iter(kinds="merton.pass") if e.payload.get("role") == "foundry"][-1]
        self.assertEqual(call["allocation"]["transfer"], {"family": "weather-favorites", "desk": "kalshi-weather", "scale": True})
        # Tried once: the next transfer is the ordinary port, to a Kalshi desk where the family never lived.
        self.assertIsNone(self.foundry._first_transfer())
        desk, route, _ = self.foundry.allocate(fresh=True)
        self.assertEqual(route, "transfer")
        self.assertNotEqual(desk.niche, "kalshi-weather")


class Capacity(FoundryCase):
    def full(self, family, venue):
        return {"family": family, "venue": venue, "state": "swing", "swing": {"limit": "capacity"},
                "capacity": {"usd_per_day": 7.81, "markets_per_day": 26.5, "fill_rate_at_size": 0.6, "size_usd": 12.0}}

    def test_a_family_at_its_capacity_gets_no_house_mutation_and_is_marked_in_the_packet(self):
        self.rules.update(newcomer_seconds=600, max_population=10)
        earner = self.seated("earner")
        self.earn(earner)
        self.clock.advance(601)
        with patch.object(self.house.allocator, "family", side_effect=self.full):
            self.assertTrue(self.foundry._at_capacity(earner))
            self.assertIsNone(self.foundry._evidence_mutation(self.rules, living=self.house.registry.living(), loser=None))
            rows = self.foundry._forward_on_desk(earner.specialty)
        self.assertTrue(next(r for r in rows if r["family"] == earner.family)["capacity"]["at_capacity"])
        self.clock.advance(601)  # a refill that found nobody looks again after ten minutes
        child = self.foundry._evidence_mutation(self.rules, living=self.house.registry.living(), loser=None)
        self.assertEqual(child.parent, earner.id)  # below its capacity, an earning family is bred again


if __name__ == "__main__":
    import unittest

    unittest.main()
