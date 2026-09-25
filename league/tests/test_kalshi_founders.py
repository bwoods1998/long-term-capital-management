"""K1 (the Kalshi-scale run, Sept 25, 2026): founder rows flagged `seat_full_league` are seated into a full league.

`House.found` seats founders only below `min_population`, and the league sits at its 128-seat ceiling; the weekend's
model-versus-market sports founders read the live `odds` feed and cannot be replayed for 20 days, so neither `found`
nor `enroll` would seat them. `league/kalshi_founders.py` `seat` births one a births pass, making room through the
House's own displacement rules: on its own desk when that desk is full, else on the desk whose pooled forward record
over the last 7 days is the most negative, never on a desk whose record is not negative."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from league import kalshi_founders
from league.ledger import now_iso
from league.tests.test_house import BUYER, HouseCase

ALTS = BUYER.replace('"BTC/USD"', '"SOL/USD"')  # the alts desk; BUYER sits on the crypto majors desk


def row(key, series, *, flag=True):
    """A founder row of the sports desk, as the Kalshi-scale run writes them (a seed's program pointed at a league)."""
    out = {"seed": "favorites-daily", "key": key, "params": {"min_volume_24h": 2000, "max_hours": 30.0, "min_hours": 5.0},
           "needs": {"series": list(series), "wake_minutes": 30}}
    if flag:
        out["seat_full_league"] = True
    return out


def alerts(house, level, *words):
    return [e.payload["text"] for e in house.ledger.iter(kinds="ops.alert")
            if e.payload.get("level") == level and all(w in e.payload.get("text", "") for w in words)]


class FounderSeats(HouseCase):
    def setUp(self):
        super().setUp()
        self.flag_rows(self.house)
        self.rules = self.house.game["economy"]

    def flag_rows(self, house):
        sports = house.niches["kalshi-sports"]
        sports.founders = tuple(sports.founders) + (row("k1-mlb-model", ["KXMLBGAME", "KXMLBTOTAL"]),
                                                    row("k1-nfl-model", ["KXNFLGAME", "KXNFLSPREAD"]),
                                                    row("k1-unflagged", ["KXNCAAFGAME"], flag=False))

    def blocks(self, agent, growth, n, *, at=None):
        for i in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": "alpaca-paper", "block": f"b{i}"}, agent=agent.id, at=at)

    def full(self):
        """The league at its ceiling, as it is on the floor."""
        self.rules["max_population"] = len(self.house.registry.living())

    def founders_born(self):
        return sorted(a.founder for a in self.house.registry.agents.values() if a.founder)

    def postmortem(self, agent):
        return self.house.ledger.last("agent.postmortem", agent=agent.id).payload


class Room(FounderSeats):
    def test_an_unborn_flagged_founder_is_born_when_there_is_room(self):
        born = kalshi_founders.seat(self.house)
        self.assertEqual((born.founder, born.specialty), ("k1-mlb-model", "kalshi-sports"))
        self.assertEqual(self.house.evaluator.rung(born.id), 1, "the owner's prior: forward-tested from the first day")
        route = self.house.ledger.get(f"birth-route:{born.id}").payload
        self.assertEqual(route["route"], "founder")
        self.assertEqual({k: route["evidence"][k] for k in ("seat_full_league", "founder", "rule", "displaced")},
                         {"seat_full_league": True, "founder": "k1-mlb-model", "rule": "free seat", "displaced": None})
        self.assertEqual(len(alerts(self.house, "info", "flagged founder k1-mlb-model", "free seat")), 1)
        self.assertEqual(self.house._state["kalshi_founders"]["seated"]["k1-mlb-model"]["agent"], born.id)

    def test_one_birth_a_call_and_unflagged_founders_are_untouched(self):
        first = kalshi_founders.seat(self.house)
        self.assertEqual(len(self.house.registry.agents), 1)
        second = kalshi_founders.seat(self.house)
        self.assertEqual(len(self.house.registry.agents), 2)
        self.assertEqual((first.founder, second.founder), ("k1-mlb-model", "k1-nfl-model"))
        self.assertIsNone(kalshi_founders.seat(self.house))
        # Neither the new unflagged row nor the desk's own founders: those are `found`'s, below the floor.
        self.assertEqual(self.founders_born(), ["k1-mlb-model", "k1-nfl-model"])

    def test_a_dead_founder_is_not_reborn_even_after_a_restart(self):
        mlb = kalshi_founders.seat(self.house)
        self.house.kill(mlb, "evidence", "test: its forward record")
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-nfl-model")
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.house.close(wait=None)
        self.house = self.new_house()  # the same root: the registry and house.json are read back
        self.flag_rows(self.house)
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(self.founders_born(), ["k1-mlb-model", "k1-nfl-model"])

    def test_the_births_pass_seats_a_flagged_founder_after_enroll(self):
        self.house._births(self.rules)
        self.assertEqual(self.founders_born(), ["k1-mlb-model"])

    def test_an_exception_inside_does_not_break_the_births_pass(self):
        with patch.object(self.house, "found", side_effect=RuntimeError("boom")), \
                patch.object(self.house, "_refill", return_value=None) as refill:
            self.house._births(self.rules)
            self.house._births(self.rules)
        self.assertEqual(refill.call_count, 2, "the refill still runs after it")
        self.assertEqual(len(alerts(self.house, "warning", "flagged founders could not be seated", "RuntimeError: boom")), 1,
                         "told once an hour, never escalated by a births pass every five minutes")
        self.assertEqual(self.founders_born(), [])

    def test_a_program_that_cannot_be_born_is_told_once_and_asked_again_when_it_changes(self):
        with patch.object(self.house, "found", side_effect=ValueError("its NEEDS sit in no open specialty")) as found:
            self.assertIsNone(kalshi_founders.seat(self.house))  # mlb refused
            self.assertIsNone(kalshi_founders.seat(self.house))  # nfl refused
            self.assertIsNone(kalshi_founders.seat(self.house))  # nobody asked again
        self.assertEqual(found.call_count, 2)
        self.assertEqual(len(alerts(self.house, "warning", "flagged founder k1-mlb-model could not be born")), 1)
        sports = self.house.niches["kalshi-sports"]
        sports.founders = tuple({**f, "params": {**f["params"], "min_hours": 6.0}} if f["key"] == "k1-mlb-model" else f
                                for f in sports.founders)
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")


class FullLeague(FounderSeats):
    def test_a_full_league_displaces_the_weakest_eligible_resident_of_the_most_negative_desk(self):
        alts, alts_2, majors = self.seated("alts", ALTS), self.seated("alts", ALTS), self.seated("majors")
        self.assertEqual({a.specialty for a in (alts, alts_2, majors)}, {"alpaca-crypto-alts", "alpaca-crypto-majors"})
        self.blocks(alts, -0.01, 6)     # the alts desk: -0.06 over 6 blocks
        self.blocks(majors, -0.002, 6)  # the majors desk: -0.012 over 6 blocks
        self.full()
        self.clock.advance(3601)  # past a never-traded seat's fair chance
        # The House's own order: a resident that has never traded first (alts_2 has no block of its own).
        self.assertEqual(self.house._weakest(self.rules, evidenced=True).id, alts_2.id)
        born = kalshi_founders.seat(self.house)
        self.assertEqual((born.founder, born.specialty), ("k1-mlb-model", "kalshi-sports"))
        dead = [a for a in (alts, alts_2) if not self.house.registry.get(a.id).alive]
        self.assertEqual(dead, [alts_2])
        self.assertTrue(self.house.registry.get(majors.id).alive)
        self.assertEqual(len(self.house.registry.living()), self.rules["max_population"], "one for one")
        text = self.postmortem(dead[0])
        self.assertEqual(text["cause"], "displaced")
        self.assertIn("the founder k1-mlb-model", text["text"])
        self.assertIn("alpaca-crypto-alts, whose pooled forward record over the last 7 days is -0.0600 over 6 active blocks", text["text"])
        evidence = self.house.ledger.get(f"birth-route:{born.id}").payload["evidence"]
        self.assertEqual((evidence["rule"], evidence["displaced"], evidence["record"]["desk"]), ("league full", dead[0].id, "alpaca-crypto-alts"))
        self.assertEqual(len(alerts(self.house, "info", "k1-mlb-model", f"displacing {dead[0].id} of alpaca-crypto-alts")), 1)
        # One displacement a desk a tick (the House's rule): in the same tick the next founder's seat comes from the
        # next negative desk, and the alts desk's other resident stays.
        nfl = kalshi_founders.seat(self.house)
        self.assertEqual(nfl.founder, "k1-nfl-model")
        self.assertFalse(self.house.registry.get(majors.id).alive)
        self.assertEqual(sum(self.house.registry.get(a.id).alive for a in (alts, alts_2)), 1)

    def test_a_desk_whose_record_is_not_negative_is_never_taken_from(self):
        gone = self.seated("gone", ALTS)
        self.blocks(gone, +0.01, 6)
        self.house.kill(gone, "evidence", "test")  # the alts desk's record is positive through a member that died
        idle = self.seated("idle", ALTS)  # never traded: the House's own rules would let an evidenced newcomer take it
        stale = self.seated("stale", ALTS)
        self.blocks(stale, -0.02, 6, at=now_iso(lambda: self.clock() - 8 * 86400))  # negative all told, outside the 7 days
        self.full()
        self.clock.advance(3601)
        self.assertIsNotNone(self.house._weakest(self.rules, evidenced=True))
        records = kalshi_founders.desk_records(self.house)
        self.assertEqual((list(records), records["alpaca-crypto-alts"][0]), (["alpaca-crypto-alts"], 6))
        self.assertAlmostEqual(records["alpaca-crypto-alts"][1], 0.06)
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(idle.id).alive and self.house.registry.get(stale.id).alive)
        refusal = self.house._state["seat_refusals"]["founders"]
        self.assertEqual(refusal["count"], 2)
        self.assertIn("no desk's pooled forward record over the last 7 days is negative", refusal["why"])

    def test_no_eligible_resident_births_nothing_and_warns_once_an_hour(self):
        real, winner = self.seated("real"), self.seated("winner", ALTS)
        self.house.evaluator.promote(real.id, 2, "test: real money")
        self.blocks(real, -0.01, 6)
        self.blocks(winner, -0.01, 6)
        self.house.ledger.append("eval.block", {"agent": winner.id, "log_growth": 0.2, "active": True, "book": "alpaca-paper",
                                                "block": "b9"}, agent=winner.id)  # a winner, on a desk negative overall
        self.full()
        self.clock.advance(3601)
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(self.founders_born(), [])
        self.assertTrue(self.house.registry.get(real.id).alive and self.house.registry.get(winner.id).alive)
        told = alerts(self.house, "warning", "2 flagged founders wait for a seat")
        self.assertEqual(len(told), 1)
        self.assertIn("may be displaced", told[0])
        self.clock.advance(3601)
        kalshi_founders.seat(self.house)
        self.assertEqual(len(alerts(self.house, "warning", "2 flagged founders wait for a seat")), 2)

    def test_a_proven_familys_member_is_never_taken_even_when_the_founder_is_proven_too(self):
        resident = self.seated("resident", ALTS)
        self.blocks(resident, -0.01, 6)
        self.full()
        self.clock.advance(3601)
        with patch.object(self.house, "_family_proven", return_value=True):
            self.assertIsNotNone(self.house._weakest(self.rules, evidenced=True, newcomer=kalshi_founders_newcomer()),
                                 "the House's rule lets a proven newcomer take a proven family's member")
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(resident.id).alive)

    def test_a_desk_held_for_its_waiters_is_passed_over(self):
        alts, majors = self.seated("alts", ALTS), self.seated("majors")
        self.blocks(alts, -0.01, 6)
        self.blocks(majors, -0.002, 6)
        self.full()
        self.clock.advance(3601)
        waiting = {"proven": [], "graduates": [{"niche": "alpaca-crypto-alts", "candidate": "c1"}], "retained": [], "cards": [],
                   "strategies": []}
        with patch.object(self.house, "seat_waiters", return_value=waiting):
            self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertTrue(self.house.registry.get(alts.id).alive, "the alts desk's next seat is its waiting graduate's")
        self.assertFalse(self.house.registry.get(majors.id).alive)


class FullDesk(FounderSeats):
    def test_a_full_founder_desk_displaces_on_its_own_desk(self):
        resident = self.house.found(["football-favorites"])[0]  # an unflagged founder of the sports desk
        elsewhere = self.seated("elsewhere", ALTS)
        self.blocks(elsewhere, -0.01, 6)  # a negative desk elsewhere is not asked: the desk is what is full
        self.house.niches["kalshi-sports"].max_members = 1
        self.clock.advance(3601)
        born = kalshi_founders.seat(self.house)
        self.assertEqual(born.founder, "k1-mlb-model")
        self.assertFalse(self.house.registry.get(resident.id).alive)
        self.assertTrue(self.house.registry.get(elsewhere.id).alive)
        text = self.postmortem(resident)
        self.assertEqual(text["cause"], "displaced")
        self.assertIn(f"Its desk kalshi-sports was full and the founder k1-mlb-model ({born.id}) takes its seat", text["text"])
        self.assertEqual(self.house.ledger.get(f"birth-route:{born.id}").payload["evidence"]["rule"], "desk full")

    def test_a_full_desk_with_nobody_to_displace_births_nothing(self):
        resident = self.house.found(["football-favorites"])[0]
        self.house.niches["kalshi-sports"].max_members = 1
        self.clock.advance(600)  # inside its fair chance
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(resident.id).alive)
        self.assertIn("its desk is full (1 of 1) and no resident may be displaced",
                      self.house._state["seat_refusals"]["founders"]["why"])
        self.assertEqual(len(alerts(self.house, "warning", "flagged founders wait for a seat")), 1)


def kalshi_founders_newcomer():
    from league.house import Newcomer

    return Newcomer(family="sports-favorites", venue="kalshi", what="the founder k1-mlb-model")


if __name__ == "__main__":
    unittest.main()
