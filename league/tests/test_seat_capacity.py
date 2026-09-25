"""The seat market's capacity (R2) and births into the proven family (R3), the close-the-gaps run, Sept 24, 2026.

Measured on the 15:06Z snapshot: 82 newcomers waited for a seat (41 lab graduates, the longest 24.5 h since passing; 15
cards, 47.3 h; 11 retained candidates; 15 merged strategies) in a league of 112 of 112. 20 of them waited for
kalshi-crypto-15m, a desk the search had closed (its 8 families with three active blocks there all negative), and a
megacaps graduate whose own forward window lost -0.000142 a block still counted; 50 had waited over two hours and the only
warning said how many, never where or why. 29 paper seats had outlived their desk's evidence clock with no positive record,
while the one waiter with a winning forward window (+0.000102) could not take any of them. The one proven family
(sports-central-run-under: pooled n 19, bound +0.204, real n 5 of the swing's 15) ran its program on one member, and no path
bred it: no House mutation is staked while anyone waits, and a fork needs a free seat in a full league.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from league.constitution import CONSTITUTION
from league.house import SEAT_WAIT_WARN_SECONDS, House, Newcomer
from league.ledger import now_iso
from league.tests.test_house import BUYER
from league.tests.test_hypotheses import FoundryCase
from league.tests.test_lab import DESK, KNOB, LabCase
from league.tests.test_seat_evidence import MAKER, EvidenceCase
from league.tests.test_seat_market import SeatCase, alerts


class NoFoundryCards:
    """The foundry as the House reads it for its closed desks (E2, `Foundry._closed_desks`), with no card of its own."""

    def __init__(self, closed):
        self.closed = dict(closed)

    def _closed_desks(self):
        return dict(self.closed)

    def inventory(self):
        return []

    def evaluations(self):
        return {}

    def enabled(self):
        return False

    def replaces_refill(self):
        return False

    def stats(self):
        return {}


class ClosedDesks(FoundryCase):
    def setUp(self):
        super().setUp()
        self.grace = float(self.rules["epoch_seconds"]) * float(self.rules["displace_after_epochs"])

    def close(self, *desks):
        """The foundry's closed desks (game.json `hypotheses.closed_desks`, read by `Foundry._closed_desks`)."""
        self.house.game.setdefault("hypotheses", {})["closed_desks"] = list(desks)
        self.house._data_cache.pop("search_closed", None)

    def test_a_card_whose_desk_the_search_closes_leaves_the_queue_with_its_reason_and_is_never_counted(self):
        self.call()  # the sawtooth card passes replay on the crypto majors desk
        card = self.card_of("sawtooth")
        self.assertEqual([w["card"] for w in self.house.seat_waiters(fresh=True)["cards"]], [card["id"]])
        self.close(self.DESK)
        self.assertEqual(self.house.seat_waiters(fresh=True)["cards"], [], "the search closed its desk: it left the queue")
        gone = self.house._state["seat_expired"][f"cards:{card['id']}"]
        self.assertEqual((gone["class"], gone["desk"], gone["rule"]), ("cards", self.DESK, "closed"))
        self.assertIn(f"no family on {self.DESK} has a positive forward record", gone["why"])
        row = self.house.ledger.get(f"seat-expired:cards:{card['id']}")
        self.assertEqual((row.kind, row.payload["route"], row.payload["evidence"]["rule"]), ("route.decision", "expired", "closed"))
        self.assertEqual(len(alerts(self.house, "info", "left the seat queue", self.DESK)), 1)
        self.assertEqual(self.house.seat_waiters(fresh=True)["cards"], [])
        self.assertEqual(len(alerts(self.house, "info", "left the seat queue")), 1, "told once")
        self.assertEqual(sum(1 for e in self.house.ledger.iter(kinds="route.decision") if e.payload.get("route") == "expired"), 1)
        report = self.house._seat_market_watch(fresh=True)
        self.assertEqual(report["waiters"]["cards"], 0)
        self.assertEqual(report["expired"]["by_rule"], {"closed": 1})
        self.assertNotIn(self.DESK, report["waiters_by_desk"])
        self.assertEqual(self.house._seats_health()["waiters"]["cards"], 0)
        # ... and the refill never seats it: the foundry's admission skips a closed desk as it skips a reserved one.
        self.rules.update(newcomer_seconds=600, max_population=40)
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual([c["id"] for c in self.foundry.inventory()], [card["id"]], "the foundry's own record is untouched")

    def test_a_closed_desk_holds_its_cap_at_its_members_and_gets_its_cap_back_when_it_reopens(self):
        niche = self.house.niches[self.DESK]
        base = niche.max_members
        first, second = self.seated("first"), self.seated("second")
        self.close(self.DESK)
        held = self.house._follow_the_search()
        self.assertEqual((niche.max_members, held[self.DESK]), (2, {"cap": 2, "base": base, "members": 2}))
        self.house.kill(first, "evidence", "a test death")
        self.house._follow_the_search()
        self.assertEqual(niche.max_members, 1, "it shrinks as its members die; nobody is born there")
        self.clock.advance(3601 + self.grace)  # the survivor has never traded, well past its fair chance and its grace
        self.assertIsNone(self.house._weakest(self.rules, specialty=self.DESK, evidenced=True),
                          "no seat is made on a desk the search closes")
        self.assertEqual(self.house._weakest(self.rules, specialty=self.DESK).id, second.id, "the plain tournament is not the search's")
        self.close()
        self.house._follow_the_search()
        self.assertEqual(niche.max_members, base, "reopened: its niches.json cap again")
        self.assertEqual(self.house._weakest(self.rules, specialty=self.DESK, evidenced=True).id, second.id)


class GraduatesLeave(LabCase):
    def setUp(self):
        super().setUp()
        self.rules = self.house.game["economy"]

    def waiting_graduate(self):
        self.queue(KNOB, origin="luna")
        self.lab.evaluate_batch()
        self.niche.max_members = 1
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")  # nobody may be displaced: the graduate waits
        self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat")
        graduates = self.house.seat_waiters(fresh=True)["graduates"]
        self.assertEqual(len(graduates), 1)
        return graduates[0]["candidate"]

    def test_a_graduate_waits_from_its_passing_row_not_from_its_last_retry(self):
        ident = self.waiting_graduate()
        passed = self.house.ledger.get(f"lab.graduate:{ident}:passed")
        self.clock.advance(3 * 3600)
        self.lab.graduate()  # a retry moves the table's `at`, never the wait
        waiting = self.house.seat_waiters(fresh=True)["graduates"][0]
        self.assertAlmostEqual(waiting["since"], self.house._waiting_graduates()[0]["since"])
        from league.house import _epoch
        self.assertEqual(waiting["since"], _epoch(passed.at))

    def test_a_graduate_whose_own_forward_window_loses_leaves_the_queue(self):
        ident = self.waiting_graduate()
        now = self.clock()
        self.lab._x("INSERT INTO forward(candidate, at, window_start, window_end, tape_id, ok, blocks, active_blocks, log_growth,"
                    " mean_log_growth, trades, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ident, now, now - 86400, now, "fwd:test", 1, 4, 4, -0.000568, -0.000142, 6, None))  # the megacaps graduate at 15:06Z
        self.assertEqual(self.house.seat_waiters(fresh=True)["graduates"], [])
        gone = self.house._state["seat_expired"][f"graduates:{ident}"]
        self.assertEqual(gone["rule"], "forward")
        self.assertIn("-0.000142", gone["why"])

    def test_no_seat_is_made_for_a_graduate_on_a_desk_the_search_closes(self):
        self.queue(KNOB, origin="luna")
        self.lab.evaluate_batch()
        self.niche.max_members = 1
        resident = self.seated("resident")  # never trades
        self.clock.advance(3601)  # past its fair chance: an evidenced newcomer may take a never-traded seat
        self.assertEqual(self.house._weakest(self.rules, specialty=DESK, evidenced=True).id, resident.id)
        self.house.hypotheses = NoFoundryCards({DESK: f"no family on {DESK} has a positive forward record over 3 active blocks there"})
        self.house._data_cache.pop("search_closed", None)
        self.assertEqual(self.lab.graduate()[0]["state"], "waiting_seat", "the lab asks the House for a seat and is given none")
        self.assertTrue(self.house.registry.get(resident.id).alive)
        self.assertEqual(self.house.seat_waiters(fresh=True)["graduates"], [])
        self.assertEqual(self.house._state["seat_expired"][f"graduates:{self.house._waiting_graduates()[0]['candidate']}"]["rule"], "closed")


class StaleSeats(EvidenceCase):
    """S3: a waiter with a winning forward window takes the seat of a resident whose desk's evidence clock has run with no
    positive record of its own -- never one inside its clock or its fair chance, a real-money seat, a winner, a resident
    whose own forward window wins, or a proven family's member by an unproven newcomer; one a desk a tick."""

    def trader(self, name="trader", fills=3):
        agent = self.seated(name)
        for _ in range(fills):
            self.buy(agent)
        return agent

    def test_a_forward_scored_newcomer_takes_a_stale_seat_once_its_desks_clock_has_run(self):
        self.desk_clock(3.7)  # alpaca-crypto-alts' clock at 15:06Z
        trader = self.trader()
        scored = Newcomer(forward=0.000102, what="a graduate with a winning window")  # the megacaps graduate at 15:06Z
        with patch.object(self.house, "_resident_forward", return_value=None), patch.object(self.house, "_forward_scorable", return_value=True):
            self.clock.advance(3.7 * 3600 - 60)
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=scored), "inside its desk's clock")
            self.clock.advance(120)
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=scored).id, trader.id, "stale: its clock has run")
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True), "a newcomer with no forward score waits for the S1 record")
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=Newcomer(forward=-0.0001)),
                              "a losing window takes nothing")
        with patch.object(self.house, "_resident_forward", return_value=0.0002):
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=Newcomer(forward=0.0001)),
                              "its own forward window wins: a positive record of its own")
        with patch.object(self.house, "_resident_forward", return_value=0.0):
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=scored).id, trader.id, "a flat window is no record")

    def test_real_money_a_winner_and_a_proven_familys_member_keep_their_stale_seats(self):
        self.desk_clock(3.7)
        real = self.trader("real")
        self.house.evaluator.promote(real.id, 2, "test: real money")
        winner = self.trader("winner")
        self.blocks(winner, 0.003, 1)
        member = self.trader("member")
        self.clock.advance(4 * 3600)
        scored = Newcomer(forward=0.0005, family="another", venue="alpaca")
        with patch.object(self.house, "_resident_forward", return_value=None), patch.object(self.house, "_forward_scorable", return_value=True):
            with self.proven("test-family"):
                self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=scored), "a proven family's member")
                why = {}
                self.house._displaceable(self.rules, evidenced=True, newcomer=scored, why=why)
                self.assertEqual(why, {"real money": 1, "a winner": 1, "a proven family's member": 1})
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=scored).id, member.id)

    def test_a_resident_holding_an_event_contract_to_settle_is_not_stale(self):
        """The review of #276: S3 displaced a stale trader holding open event positions, and its wind-down sold them at the
        bid, losing the settlements its desk's evidence clock waits for. It waits for them now."""
        from decimal import Decimal

        from league.book import Holding
        from league.venues import instrument_for

        self.desk_clock(3.7)
        trader = self.trader()
        scored = Newcomer(forward=0.0005)
        contract = instrument_for("kalshi-shadow", {"symbol": "KXMLBTOTAL-26SEP241840MILPHI-8", "right": "no"})
        account = self.house.book_of(trader).account(trader.id)
        account.holdings[contract.key] = Holding(contract, Decimal("5"), Decimal("4.60"))
        self.clock.advance(4 * 3600)
        with patch.object(self.house, "_resident_forward", return_value=None), patch.object(self.house, "_forward_scorable", return_value=True):
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=scored), "its contracts have not settled")
            del account.holdings[contract.key]  # settled
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=scored).id, trader.id)

    def test_one_stale_seat_a_desk_a_tick(self):
        self.desk_clock(3.7)
        first, second = self.trader("first"), self.trader("second")
        self.clock.advance(4 * 3600)
        scored = Newcomer(forward=0.0005)
        with patch.object(self.house, "_resident_forward", return_value=None), patch.object(self.house, "_forward_scorable", return_value=True):
            loser = self.house._weakest(self.rules, evidenced=True, newcomer=scored)
            self.house.kill(loser, "displaced", "test")
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=scored))
            self.clock.advance(float(self.house.settings.desk_displacement_seconds) + 1)
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=scored).id, (second if loser.id == first.id else first).id)

    def test_a_desk_with_no_clock_measured_keeps_the_plain_grace_and_the_fair_chance_holds_everywhere(self):
        trader = self.trader()
        scored = Newcomer(forward=0.0005)
        with patch.object(self.house, "_resident_forward", return_value=None), patch.object(self.house, "_forward_scorable", return_value=True):
            self.clock.advance(self.grace - 60)
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=scored), "no clock: the plain grace is its clock")
            self.clock.advance(120)
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=scored).id, trader.id)
        self.assertEqual(self.house._stale_seat(trader, self.clock() - 1800, 0.25 * 3600, self.grace, False, self.clock()), False,
                         "a clock under an hour never shortens the fair chance")


class Population(SeatCase):
    """R2 (3): the league grows toward turbo.json's ceiling only while Sail's runway, as the House's Sail meter measures it,
    is over `economy.population_runway_days`; it is held at `economy.max_population_short_runway` otherwise."""

    def setUp(self):
        super().setUp()
        self.house._burst = {"id": "test-burst", "started": 0.0, "policy": {"minimum_research_passes": 2}}
        self.house._population_ceiling = 128
        self.rules.update(population_runway_days=1.5, max_population_short_runway=112, max_population=128)

    def readings(self, balance, spent, *, hours=24, every=900):
        """The Sail meter's rows (league/budget.py `Budget.check`): one every fifteen minutes, `spent_usd` its fall."""
        end = self.clock()
        n = int(hours * 3600 / every)
        for i in range(n + 1):
            at = end - (n - i) * every
            self.house.ledger.append("ops.budget", {"what": "sail", "balance_usd": f"{balance + spent * (n - i):.2f}",
                                                    "spent_usd": f"{spent:.2f}", "month_usd": "0", "cap_usd": "300", "mode": "open"},
                                     at=now_iso(lambda at=at: at))
        self.house._data_cache.pop("sail_runway", None)

    def test_the_population_grows_to_the_ceiling_only_while_sails_runway_is_over_a_day_and_a_half(self):
        self.readings(162.30, 0.36)  # $34.56 a day against $162.30: 4.6 days over the $5 reserve (15:06Z: 4.5)
        report = self.house._population_rule()
        self.assertEqual((self.rules["max_population"], report["max_population"]), (128, 128))
        self.assertGreater(report["runway_days"], 4.5)
        self.assertAlmostEqual(report["sail"]["burn_usd_per_day"], 34.56, places=1)
        self.assertEqual(alerts(self.house, "info", "population is now"), [])
        self.clock.advance(25 * 3600)
        self.readings(40.0, 0.36)  # a day later the balance is $40: about a day at the same burn
        report = self.house._population_rule()
        self.assertEqual(self.rules["max_population"], 112)
        self.assertLess(report["runway_days"], 1.5)
        self.assertEqual(len(alerts(self.house, "warning", "population is now 112 (was 128)")), 1)

    def test_an_unread_meter_holds_the_population_and_no_burst_leaves_it_alone(self):
        self.house._population_rule()
        self.assertEqual(self.rules["max_population"], 112, "growth needs a measured runway")
        self.house._burst = None
        self.rules["max_population"] = 7
        self.assertIsNone(self.house._population_rule())
        self.assertEqual(self.rules["max_population"], 7)

    def test_health_shows_the_population_rule(self):
        self.readings(162.30, 0.36)
        self.house._population_rule()
        self.house._health({"at": now_iso(self.clock)})
        health = json.loads((Path(self.house.root) / "health.json").read_text())
        self.assertEqual(health["seats"]["population"]["max_population"], 128)
        self.assertIn("Sail's runway", health["seats"]["population"]["rule"])


class TwoHours(SeatCase):
    """R2 (4): no newcomer waits over two hours, or one warning an hour names its desk, the count and the rule."""

    def test_a_newcomer_waiting_over_two_hours_is_named_with_its_desk_the_count_and_the_rule(self):
        self.house.niches["alpaca-crypto-majors"].max_members = 1
        real = self.seated("real")
        self.house.evaluator.promote(real.id, 2, "test: real money")
        since = self.clock() - 3 * 3600
        waiting = {"proven": [], "graduates": [{"candidate": "c1", "niche": "alpaca-crypto-majors", "family": "lab-family", "since": since}],
                   "retained": [], "cards": [], "strategies": []}
        with patch.object(self.house, "seat_waiters", return_value=waiting):
            report = self.house._seat_market_watch(fresh=True)
            row = report["over_two_hours"]["alpaca-crypto-majors"]
            self.assertEqual((row["count"], row["longest_hours"], row["longest"]), (1, 3.0, "graduates:c1"))
            self.assertEqual(row["rule"], "its 1 seat (1 member) is held: 1 real money")
            told = alerts(self.house, "warning", "waited over 2 hours", "alpaca-crypto-majors", "1 real money")
            self.assertEqual(len(told), 1)
            self.assertEqual(report["longest_wait"]["reason"], row["rule"])
            self.house._seat_market_watch(fresh=True)
            self.assertEqual(len(alerts(self.house, "warning", "waited over 2 hours")), 1, "once an hour a desk")
            self.house._health({"at": now_iso(self.clock)})
            health = json.loads((Path(self.house.root) / "health.json").read_text())
            longest = health["seats"]["longest_wait"]
            self.assertEqual((longest["class"], longest["id"], longest["desk"], longest["hours"]), ("graduates", "c1", "alpaca-crypto-majors", 3.0))
            self.assertEqual(longest["reason"], row["rule"])
            self.clock.advance(3601)
            self.house._seat_market_watch(fresh=True)
            self.assertEqual(len(alerts(self.house, "warning", "waited over 2 hours")), 2)

    def test_a_waiter_under_two_hours_is_not_told_and_a_free_seat_says_so(self):
        since = self.clock() - (SEAT_WAIT_WARN_SECONDS - 60)
        waiting = {"proven": [], "graduates": [{"candidate": "c1", "niche": "alpaca-crypto-majors", "since": since}],
                   "retained": [], "cards": [], "strategies": []}
        with patch.object(self.house, "seat_waiters", return_value=waiting):
            self.assertEqual(self.house._seat_market_watch(fresh=True)["over_two_hours"], {})
            self.clock.advance(120)
            rule = self.house._seat_market_watch(fresh=True)["over_two_hours"]["alpaca-crypto-majors"]["rule"]
        self.assertIn("a seat is free", rule)


class ProvenFamily(EvidenceCase):
    """R3: the proven family's program (its anchor's code, and the House's mutations of its PARAMS) is born first on its
    desk until `economy.proven_family_members` living members run it; a member that inherited the family's name with
    other code is not its program."""

    def setUp(self):
        super().setUp()
        self.rules.update(newcomer_seconds=600, proven_family_members=4)
        self.anchor = self.seated("anchor")
        self.house.evaluator.promote(self.anchor.id, 2, "test: a bunt on real money")
        self.buy(self.anchor)
        # A research child of the anchor, born with another program under the family's name (meriwether-h2d625d-2: a
        # moneyline-favourites file its parent never ran). Its code differs beyond PARAMS: a resting post-only bid.
        self.other = self.house.spawn("other", "test-family", MAKER, parent=self.anchor.id, reason="a research candidate with new code")
        self.house.evaluator.seat(self.other.id, 1, "test")

    def test_the_proven_familys_program_is_born_first_up_to_its_member_count(self):
        with self.proven("test-family"):
            rows = self.house._proven_programs()
            self.assertEqual([(r["family"], r["anchor"].id, [a.id for a in r["running"]], r["wanted"]) for r in rows],
                             [("test-family", self.anchor.id, [self.anchor.id], 3)], "the member with other code is not its program")
            self.assertEqual([w["family"] for w in self.house.seat_waiters(fresh=True)["proven"]], ["test-family"])
            child = self.house._proven_births(self.rules)
            self.assertEqual((child.code_sha256, child.parent, child.family, child.specialty),
                             (self.anchor.code_sha256, self.anchor.id, "test-family", self.anchor.specialty))
            self.assertNotEqual(child.params, self.anchor.params, "a mutation of its PARAMS, never a copy")
            self.assertEqual(self.house.evaluator.rung(child.id), 0, "replayed like any mutation before practice")
            route = self.house.ledger.get(f"birth-route:{child.id}").payload
            self.assertEqual((route["route"], route["evidence"]["anchor"]), ("proven_family", self.anchor.id))
            self.assertIsNone(self.house._proven_births(self.rules), "paced at the newcomer cadence")
            born = [child]
            for _ in range(3):
                self.clock.advance(601)
                born.append(self.house._proven_births(self.rules))
            self.assertIsNotNone(born[2])
            self.assertIsNone(born[3], "four living members run its program now")
            self.assertEqual(self.house.seat_waiters(fresh=True)["proven"], [])

    def test_a_proven_familys_birth_goes_first_and_its_desk_is_held_for_it(self):
        from league.tests.test_seat_market import SPY  # a newcomer of another desk

        self.rules["max_population"] = len(self.house.registry.living()) + 1  # one free seat
        strategy = {"name": "a-merged-strategy", "family": "gap-fade", "why": "a test strategy", "code": SPY}
        with self.proven("test-family"), patch("league.strategies.all_strategies", return_value=[strategy]):
            idle = self.seated("idle")  # never trades: an evidenced newcomer's seat past its fair chance
            self.rules["max_population"] += 1
            self.clock.advance(3601)
            self.assertIsNone(self.house._weakest(self.rules, specialty=self.anchor.specialty, evidenced=True,
                                                  newcomer=Newcomer(family="another", venue="alpaca")),
                              "the desk's next seat is the proven family's")
            self.assertIsNotNone(self.house._weakest(self.rules, specialty=self.anchor.specialty, evidenced=True,
                                                     newcomer=Newcomer(family="test-family", venue="alpaca")))
            self.house._births(self.rules)
            born = [a for a in self.house.registry.living() if a.parent == self.anchor.id and a.code_sha256 == self.anchor.code_sha256]
            self.assertEqual(len(born), 1, "the proven family's birth took the free seat first")
            self.assertNotIn("a-merged-strategy", {a.founder for a in self.house.registry.agents.values()})

    def test_no_birth_into_a_family_at_its_measured_capacity_or_without_an_anchor_that_trades(self):
        with self.proven("test-family"):
            with patch("league.lab.family_at_capacity", return_value=True):
                self.assertIn("capacity", self.house._proven_programs()[0]["held"])
                self.assertEqual(self.house.seat_waiters(fresh=True)["proven"], [])
                self.assertIsNone(self.house._proven_births(self.rules))
            self.house.kill(self.anchor, "evidence", "a test death")
            self.assertEqual(self.house._proven_programs(), [], "the member with other code never becomes the program")
            self.assertIsNone(self.house._proven_births(self.rules))

    def test_an_unproven_family_is_never_bred_first(self):
        self.assertEqual(self.house._proven_programs(), [])
        self.assertIsNone(self.house._proven_births(self.rules))


#: meriwether-h2d625d's shape: KXMLBTOTAL central run-unders (sports-central-run-under, the proven family) ...
RUN_UNDER = '''
NEEDS = {"venue": "kalshi", "horizon": "day", "style": "central-run-entertainment-premium", "series": ["KXMLBTOTAL"],
         "max_hours_to_close": 48, "wake_minutes": 30}
PARAMS = {}

def decide(ctx):
    return {"intents": [], "thought": "wait for a central under before play"}
'''
#: ... meriwether-h2d625d-2's: a moneyline-favourites file its parent never ran, on other series, another style ...
MONEYLINE_FAVOURITES = RUN_UNDER.replace('"central-run-entertainment-premium"', '"sports-moneyline-deep-favourites"').replace(
    '["KXMLBTOTAL"]', '["KXNCAAFGAME", "KXEPLGAME"]').replace("wait for a central under before play", "buy a deep favourite")
#: ... and a fix of the same program: the same markets and style, a maker entry instead of a taker one.
RUN_UNDER_MAKER_FIX = RUN_UNDER.replace("wait for a central under before play", "rest a post-only bid at the bid")


class NewCodeFamilies(EvidenceCase):
    """The family-attribution defect (Sept 24, 2026): a research fork or a retained candidate with NEW code was born into its
    parent's family whatever it traded, so a different mechanism inherited the family's proof -- meriwether-h2d625d-2, a CFB
    and soccer moneyline-favourites file, carries sports-central-run-under, the KXMLBTOTAL run-unders' proven family. On the
    15:06Z snapshot 98 children had been born into their parent's family with other code beyond PARAMS (39 living), and 71 of
    them (28 living) named other markets or another style."""

    def setUp(self):
        # The Sept 24 rule this class pins is the label rule: C8 (the forward-first run, Sept 25, 2026; the constitution's
        # `allocator.family_key` "mechanism") keys every birth by its mechanism instead, which league/tests/test_family_key.py
        # tests. Without the key a birth keeps its label, with this rule for a research fork: the rollback form.
        label = patch.dict(CONSTITUTION["allocator"], {"family_key": "label"})
        label.start()
        self.addCleanup(label.stop)
        super().setUp()
        self.house.close(wait=None)  # a House with a Kalshi practice book too, as test_seat_evidence's RetainedCandidates
        from league.economy import load_game
        from league.house import House, Settings
        from league.sandbox import LocalSandbox
        from league.tests.fakes import FakeBroker

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(Path(self.dir.name) / "house-families", brokers={"alpaca-paper": self.broker,
                                                                             "kalshi-shadow": FakeBroker("kalshi-shadow", family="kalshi")},
                           sandbox=LocalSandbox(Path(self.dir.name) / "boxes-families"), alpaca_data=self.data, clock=self.clock,
                           settings=Settings(mark_every_seconds=0, research=False), game=game)
        self.rules = self.house.game["economy"]

    def retained(self, code):
        """A replay-passed research candidate as the admission queue keeps it (test_seat_evidence's RetainedCandidates)."""
        from league import niches as niches_module
        from league.lab import static_literal

        needs = niches_module.constrain(static_literal(code, "NEEDS"), self.house.niches[DESK])
        return {"code": code, "params": static_literal(code, "PARAMS"), "needs": needs, "passed": True, "purpose": "a retained candidate",
                "numbers": {"trades": 40, "passed": True, "return_pct": 12.0}}

    def queued(self, author, candidate, session):
        from league.admissions import Admissions

        queue = Admissions(self.house.ledger)
        row = queue.enqueue(author.id, self.house._generation(author.id), candidate, session)
        queue.record(row, "deferred", "niche is full; waiting for an eligible seat")
        return row

    def parent(self):
        parent = self.house.spawn("meriwether", "sports-central-run-under", RUN_UNDER, reason="the run-unders")
        self.house.evaluator.seat(parent.id, 1, "test")
        self.house.economy.grant(parent.id, "100", "test: a parent that can fork")
        self.assertEqual(parent.specialty, "kalshi-sports")
        return parent

    def test_a_research_fork_with_other_markets_and_style_is_born_into_its_own_family(self):
        parent = self.parent()
        child = self.house.fork(parent, code=MONEYLINE_FAVOURITES, reason="a research candidate", passed_replay=True)
        root = hashlib.sha256("sports-central-run-under|sports-moneyline-deep-favourites".encode()).hexdigest()[:6]
        self.assertEqual(child.family, f"sports-moneyline-deep-favourites-{root}")
        self.assertLessEqual(len(child.family), 40)
        self.assertEqual(child.parent, parent.id, "its parent is on its birth row as before")
        born = self.house.ledger.get(f"born:{child.id}").payload
        self.assertEqual(born["family"], child.family)
        self.assertIn("born into its own family", born["reason"])
        again = self.house.fork(parent, code=MONEYLINE_FAVOURITES.replace("buy a deep favourite", "buy a deeper favourite"),
                                reason="another research candidate", passed_replay=True)
        self.assertEqual(again.family, child.family, "one research direction from one family is one family")

    def test_a_fix_of_the_same_program_keeps_its_family(self):
        parent = self.parent()
        child = self.house.fork(parent, code=RUN_UNDER_MAKER_FIX, reason="a maker fix", passed_replay=True)
        self.assertEqual(child.family, "sports-central-run-under", "the same markets and style: a fix of the family's program")
        self.assertNotIn("born into its own family", self.house.ledger.get(f"born:{child.id}").payload["reason"])

    def test_a_retained_candidate_on_other_markets_is_born_into_its_own_family(self):
        author = self.seated("author")
        candidate = self.retained(BUYER.replace('"BTC/USD"', '"ETH/USD"'))  # the same desk, another market
        self.queued(author, candidate, "research:author:1")
        self.house.kill(author, "displaced", "test")
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual(child.parent, author.id)
        self.assertNotEqual(child.family, author.family)
        self.assertTrue(child.family.startswith("crypto-majors-test-buyer-"), child.family)


class WaiterNames(unittest.TestCase):
    def test_every_class_is_named_in_the_singular_and_the_plural(self):
        """Sept 24, 2026: an appended "s" wrote "8 merged strategys" into the owner's alert at 18:56:18Z."""
        self.assertEqual(House._waiters_named("strategies", 8), "8 merged strategies")
        self.assertEqual(House._waiters_named("strategies", 1), "1 merged strategy")
        self.assertEqual(House._waiters_named("proven", 3), "3 proven family's births")
        self.assertEqual(set(House.SEAT_WAITER_PLURALS), set(House.SEAT_WAITER_NAMES))

