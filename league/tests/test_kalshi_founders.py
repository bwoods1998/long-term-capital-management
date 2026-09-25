"""K1 (the Kalshi-scale run, Sept 25, 2026): founder rows flagged `seat_full_league` are seated into a full league.

`House.found` seats founders only below `min_population`, and the league sits at its 128-seat ceiling; the weekend's
model-versus-market sports founders read the live `odds` feed and cannot be replayed for 20 days, so neither `found`
nor `enroll` would seat them. `league/kalshi_founders.py` `seat` births one a births pass: through the House's own
seat market first (on its own desk when that desk is full, else on the desk whose pooled forward record over the last
7 days is the most negative, never on a desk whose record is not negative), then from a desk whose niches.json row
says it `yields_seats` (the fifteen-minute crypto desk), whose resident dies `desk_closed`, never `displaced`."""
from __future__ import annotations

import json
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from league import kalshi_founders, niches as niches_module
from league.book import Book, Intent, Limits
from league.fees import Fees
from league.ledger import now_iso
from league.tests.fakes import FakeBroker
from league.tests.test_house import BUYER, HouseCase
from league.venues import instrument_for

ALTS = BUYER.replace('"BTC/USD"', '"SOL/USD"')  # the alts desk; BUYER sits on the crypto majors desk
MARKET = {"market": "KXBTC15M-26SEP231145-45", "leg": "no"}
FLAGGED = ("k1-mlb-model", "k1-nfl-model", "k1-unflagged")


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

    def blocks(self, agent, growth, n, *, at=None, book="alpaca-paper"):
        for i in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": book, "block": f"b{i}"}, agent=agent.id, at=at)

    def full(self):
        """The league at its ceiling, as it is on the floor."""
        self.rules["max_population"] = len(self.house.registry.living())

    def founders_born(self):
        """The sports desk's founders ever born: the flagged rows and the desk's own."""
        return sorted(a.founder for a in self.house.registry.agents.values()
                      if a.founder and (a.founder in FLAGGED or a.specialty == "kalshi-sports"))

    def postmortem(self, agent):
        return self.house.ledger.last("agent.postmortem", agent=agent.id).payload

    def evidence(self, agent):
        return self.house.ledger.get(f"birth-route:{agent.id}").payload["evidence"]


class Room(FounderSeats):
    def test_an_unborn_flagged_founder_is_born_when_there_is_room(self):
        born = kalshi_founders.seat(self.house)
        self.assertEqual((born.founder, born.specialty), ("k1-mlb-model", "kalshi-sports"))
        self.assertEqual(self.house.evaluator.rung(born.id), 1, "the owner's prior: forward-tested from the first day")
        route = self.house.ledger.get(f"birth-route:{born.id}").payload
        self.assertEqual(route["route"], "founder")
        self.assertEqual({k: route["evidence"][k] for k in ("seat_full_league", "founder", "rule", "made_way", "cause")},
                         {"seat_full_league": True, "founder": "k1-mlb-model", "rule": "free seat", "made_way": None, "cause": None})
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

    def test_it_holds_the_lifecycle_lock_from_the_seat_question_to_the_birth(self):
        held = []
        real = self.house.found

        def found(names):
            held.append(self.house._lifecycle_lock._is_owned())
            return real(names)

        with patch.object(self.house, "found", side_effect=found):
            kalshi_founders.seat(self.house)
        self.assertEqual(held, [True])

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
        text = self.postmortem(alts_2)
        self.assertEqual(text["cause"], "displaced")
        self.assertIn("the founder k1-mlb-model", text["text"])
        self.assertIn("alpaca-crypto-alts, whose pooled forward record over the last 7 days is -0.0600 over 6 active blocks", text["text"])
        evidence = self.evidence(born)
        self.assertEqual((evidence["rule"], evidence["made_way"], evidence["cause"], evidence["record"]["desk"]),
                         ("league full", alts_2.id, "displaced", "alpaca-crypto-alts"))
        self.assertEqual(len(alerts(self.house, "info", "k1-mlb-model", f"displacing {alts_2.id} of alpaca-crypto-alts")), 1)
        # One displacement a desk a tick (the House's rule): in the same tick the next founder's seat comes from the
        # next negative desk, and the alts desk's other resident stays.
        nfl = kalshi_founders.seat(self.house)
        self.assertEqual(nfl.founder, "k1-nfl-model")
        self.assertFalse(self.house.registry.get(majors.id).alive)
        self.assertTrue(self.house.registry.get(alts.id).alive)

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
        self.assertIn("the seat market displaces no resident", told[0])
        self.assertIn("no desk yields a seat: kalshi-crypto-15m is at its floor (0 members, floor 4)", told[0])
        self.clock.advance(3601)
        kalshi_founders.seat(self.house)
        self.assertEqual(len(alerts(self.house, "warning", "2 flagged founders wait for a seat")), 2)

    def test_a_proven_familys_member_is_never_taken_even_when_the_founder_is_proven_too(self):
        resident = self.seated("resident", ALTS)
        self.blocks(resident, -0.01, 6)
        self.full()
        self.clock.advance(3601)
        with patch.object(self.house, "_family_proven", return_value=True), \
                patch.object(self.house.allocator, "family", return_value={"state": "swing"}):
            self.assertIsNotNone(self.house._weakest(self.rules, evidenced=True, newcomer=sports_newcomer()),
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
        self.assertEqual(self.evidence(born)["rule"], "desk full")

    def test_a_full_desk_with_nobody_to_displace_births_nothing(self):
        resident = self.house.found(["football-favorites"])[0]
        self.house.niches["kalshi-sports"].max_members = 1
        self.clock.advance(600)  # inside its fair chance
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(resident.id).alive)
        self.assertIn("its desk is full (1 of 1) and no resident may be displaced",
                      self.house._state["seat_refusals"]["founders"]["why"])
        self.assertEqual(len(alerts(self.house, "warning", "flagged founders wait for a seat")), 1)


class YieldingDesk(FounderSeats):
    """The seat market offers no one (at the Sept 25 T0, not even to an evidenced newcomer), and the fifteen-minute
    crypto desk, whose niches.json row says it `yields_seats` down to 4, gives up a practice resident instead."""

    DESK = "kalshi-crypto-15m"

    def setUp(self):
        super().setUp()
        self.kalshi = FakeBroker("kalshi-shadow", family="kalshi")
        self.house.books["kalshi-shadow"] = Book("kalshi-shadow", self.kalshi, self.house.ledger, fees=Fees("kalshi"),
                                                 real_money=False, clock=self.clock)
        self.code = next(r for r in self.house.founders() if r["key"] == "quarter-hour-favorites")["code"]
        self.family = next(r for r in self.house.founders() if r["key"] == "k1-mlb-model")["family"]

    def resident(self, *, family="crypto-15m-favorites", growth=-0.01, blocks=6):
        """A practice member of the fifteen-minute desk, seated a moment ago: inside every grace the seat market keeps."""
        agent = self.house.spawn("huang", family, self.code, specialty=self.DESK, reason="a test resident")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.seat(agent)
        self.blocks(agent, growth, blocks, book="kalshi-shadow")
        return agent

    def order(self, agent, price, *, post_only=False):
        contract = instrument_for("kalshi-shadow", MARKET)
        self.kalshi.set_quote(contract, "0.94", "0.96")
        book = self.house.books["kalshi-shadow"]
        book.limits[agent.id] = Limits(D("100"), D("75"))
        (outcome,) = book.submit([Intent.new(agent=agent.id, instrument=contract, side="buy", quantity=1, order_type="limit",
                                             limit_price=price, post_only=post_only, reason="test", created_at=now_iso(self.clock))])
        return outcome

    def alive(self, *agents):
        return [self.house.registry.get(a.id).alive for a in agents]

    def test_the_fifteen_minute_desk_yields_down_to_four_and_its_cap_is_four(self):
        flags = kalshi_founders.yielding(self.house)
        self.assertEqual(flags[self.DESK]["floor"], 4)
        self.assertIn("seat_full_league", flags[self.DESK]["reason"])
        self.assertEqual(self.house.niches[self.DESK].max_members, 4)

    def test_it_gives_its_weakest_practice_resident_to_the_founder_in_the_same_call(self):
        traders = [self.resident() for _ in range(4)]
        idle = self.resident(blocks=0)  # never traded: the House's ranking takes it first
        self.full()
        self.assertIsNone(self.house._weakest(self.rules, evidenced=True), "the seat market offers no one")
        born = kalshi_founders.seat(self.house)
        self.assertEqual((born.founder, born.specialty), ("k1-mlb-model", "kalshi-sports"))
        self.assertEqual(self.alive(idle, *traders), [False, True, True, True, True])
        self.assertEqual(self.house.registry.get(idle.id).cause, "desk_closed")
        self.assertEqual(len(self.house.registry.living()), self.rules["max_population"], "one out, one in")
        text = self.postmortem(idle)
        self.assertEqual(text["cause"], "desk_closed")
        self.assertIn("Its desk kalshi-crypto-15m yields seats while its pooled record is negative: K1 (the Kalshi-scale run", text["text"])
        self.assertIn("pooled forward record over the last 7 days is -0.2400 over 24 active blocks; 5 members, floor 4", text["text"])
        self.assertIn(f"the founder k1-mlb-model ({born.id}) takes the seat on kalshi-sports", text["text"])
        evidence = self.evidence(born)
        self.assertEqual((evidence["rule"], evidence["made_way"], evidence["cause"], evidence["record"]["desk"]),
                         ("desk yields seats", idle.id, "desk_closed", self.DESK))
        self.assertEqual(len(alerts(self.house, "info", "k1-mlb-model", f"({idle.id} retired, desk_closed")), 1)
        self.assertEqual([e.payload["cause"] for e in self.house.ledger.iter(kinds="agent.died")], ["desk_closed"],
                         "never counted as a displacement")

    def test_the_floor_is_respected(self):
        residents = [self.resident() for _ in range(5)]
        self.full()
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertEqual(self.house.members(self.DESK), 4)
        self.assertIsNone(kalshi_founders.seat(self.house), "at its floor: the next founder waits")
        self.assertEqual(self.house.members(self.DESK), 4)
        self.assertEqual(sum(self.alive(*residents)), 4)
        self.assertEqual(len(alerts(self.house, "warning", "1 flagged founder waits", "kalshi-crypto-15m is at its floor (4 members, floor 4)")), 1)

    def test_real_money_holding_working_drained_proven_own_family_and_researching_residents_are_never_taken(self):
        real = self.resident()
        self.house.evaluator.promote(real.id, 2, "test: real money")
        holder, bidder, drained = self.resident(), self.resident(), self.resident()
        self.assertEqual(self.order(holder, "0.96").status, "filled")
        self.assertEqual(self.order(bidder, "0.90", post_only=True).status, "resting")
        self.house._house_control(drained, "pause_entries", "test: the House drains it")
        proven, own, busy = self.resident(family="crypto-15m-proven"), self.resident(family=self.family), self.resident()
        self.full()

        def record(family, venue):
            return {"state": "swing"} if family == "crypto-15m-proven" else {"state": "unproven"}

        with patch.object(self.house.allocator, "family", side_effect=record), \
                patch.object(self.house.research_jobs, "active", side_effect=lambda agent_id: agent_id == busy.id):
            self.assertIsNone(kalshi_founders.seat(self.house))
            self.assertEqual(self.alive(real, holder, bidder, drained, proven, own, busy), [True] * 7)
            (told,) = alerts(self.house, "warning", "flagged founders wait for a seat")
            for rule in ("holding a position or a working order 2", "a proven or swinging family's member 1", "real money 1",
                         "drained or winding down 1", "the founder's own family 1", "research in flight 1"):
                self.assertIn(rule, told)
            # Released, the drained resident may go: the desk waits for a resident to be free, it is not closed for good.
            self.house._house_control(drained, "resume_entries", "test: the drain ended")
            self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertEqual(self.alive(real, holder, bidder, drained, proven, own, busy), [True, True, True, False, True, True, True])

    def test_an_unreadable_family_record_protects_the_resident(self):
        residents = [self.resident() for _ in range(5)]
        self.full()
        with patch.object(self.house.allocator, "family", side_effect=RuntimeError("the allocator's fold failed")):
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(sum(self.alive(*residents)), 5)

    def test_a_desk_whose_record_is_not_negative_yields_nothing(self):
        gone = self.resident(growth=+0.1)
        self.house.kill(gone, "evidence", "test")  # the desk's 7-day record is positive through a member that died
        residents = [self.resident() for _ in range(5)]
        self.full()
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(sum(self.alive(*residents)), 5)
        self.assertEqual(len(alerts(self.house, "warning", "kalshi-crypto-15m's pooled forward record over the last 7 days is not negative")), 1)

    def test_no_flag_no_retirement(self):
        residents = [self.resident() for _ in range(6)]
        self.full()
        doc = json.loads(niches_module.NICHES_PATH.read_text(encoding="utf-8"))
        for desk in doc["niches"]:
            desk.pop("yields_seats", None)
        unflagged = Path(self.dir.name) / "niches.json"
        unflagged.write_text(json.dumps(doc), encoding="utf-8")
        with patch.object(niches_module, "NICHES_PATH", unflagged):
            self.assertEqual(kalshi_founders.yielding(self.house), {})
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(sum(self.alive(*residents)), 6)
        self.assertEqual(len(alerts(self.house, "warning", "no desk yields a seat: no open Kalshi desk carries yields_seats")), 1)
        self.assertEqual(self.house.ledger.count(kinds="agent.died"), 0)


def sports_newcomer():
    from league.house import Newcomer

    return Newcomer(family="sports-favorites", venue="kalshi", what="the founder k1-mlb-model")


if __name__ == "__main__":
    unittest.main()
