"""K1 (the Kalshi-scale run, Sept 25, 2026): founder rows flagged `seat_full_league` are seated into a full league.

`House.found` seats founders only below `min_population`, and the league sits at its 128-seat ceiling; the weekend's
model-versus-market sports founders read the live `odds` feed and cannot be replayed for 20 days, so neither `found`
nor `enroll` would seat them. `league/kalshi_founders.py` `seat` births one a births pass, only into a free seat of
its own desk: in a full league, room is made through the House's own seat market first (asked as for a newcomer
without forward evidence, on the desk whose pooled forward record over the last 7 days is the most negative, never on
a desk whose record is not negative), then from a desk whose niches.json row says it `yields_seats` (the
fifteen-minute crypto desk), whose resident dies `desk_closed`, never `displaced`."""
from __future__ import annotations

import json
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from league import kalshi_founders, niches as niches_module
from league.house import Newcomer
from league.book import Book, Intent, Limits
from league.fees import Fees
from league.ledger import now_iso
from league.tests.fakes import FakeBroker
from league.tests.test_house import BUYER, HouseCase
from league.venues import instrument_for

ALTS = BUYER.replace('"BTC/USD"', '"SOL/USD"')  # the alts desk; BUYER sits on the crypto majors desk
MARKET = {"market": "KXBTC15M-26SEP231145-45", "leg": "no"}
FLAGGED = ("k1-mlb-model", "k1-nfl-model", "k1-unflagged", "k1-ncaaf-model", "k1-soccer-model")
GRACE = 12 * 3600 + 1  # past a paper seat's plain grace (`displace_after_epochs` x `epoch_seconds`): a newcomer without evidence waits it out


def row(key, series, *, flag=True, **extra):
    """A founder row of the sports desk, as the Kalshi-scale run writes them (a seed's program pointed at a league)."""
    out = {"seed": "favorites-daily", "key": key, "params": {"min_volume_24h": 2000, "max_hours": 30.0, "min_hours": 5.0},
           "needs": {"series": list(series), "wake_minutes": 30}}
    if flag:
        out["seat_full_league"] = True
    return {**out, **extra}


def alerts(house, level, *words):
    return [e.payload["text"] for e in house.ledger.iter(kinds="ops.alert")
            if e.payload.get("level") == level and all(w in e.payload.get("text", "") for w in words)]


class FounderSeats(HouseCase):
    def new_house(self, **kw):
        house = super().new_house(**kw)
        house.settings.kalshi_founders = True  # the floor's House has it on (service.build); a test's is off by default
        return house

    def setUp(self):
        super().setUp()
        self.flag_rows(self.house)
        self.rules = self.house.game["economy"]

    def flag_rows(self, house):
        # The real rows of niches.json carry the weekend's flagged founders (K1's sports and K3's weather founders, whose
        # shape `test_niches` checks); these tests measure the hook on their own rows, so the real ones are unflagged here.
        for niche in house.niches.values():
            niche.founders = tuple({**f, "seat_full_league": False} if isinstance(f, dict) and f.get("seat_full_league") else f
                                   for f in niche.founders)
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

    def family_of(self, key):
        return next(r for r in self.house.founders() if r["key"] == key)["family"]

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

        def found(names, **kw):
            held.append(self.house._lifecycle_lock._is_owned())
            return real(names, **kw)

        with patch.object(self.house, "found", side_effect=found):
            kalshi_founders.seat(self.house)
        self.assertEqual(held, [True])

    def test_its_needs_probe_is_read_outside_the_lifecycle_lock_and_handed_to_found(self):
        # Every wake takes the lifecycle lock: a Sail call under it stalls the tick (review of PR 159).
        probed, real = [], self.house.sandbox.needs

        def needs(box, code, **kw):
            probed.append(self.house._lifecycle_lock._is_owned())
            return real(box, code, **kw)

        with patch.object(self.house.sandbox, "needs", side_effect=needs):
            born = kalshi_founders.seat(self.house)
        self.assertEqual((born.founder, probed), ("k1-mlb-model", [False]), "one probe, outside the lock, and none inside `found`")

    def test_seat_order_is_priority_then_desk_then_row(self):
        sports = self.house.niches["kalshi-sports"]
        sports.founders = tuple(f for f in sports.founders if f["key"] not in FLAGGED) + (
            row("k1-mlb-model", ["KXMLBGAME"], seat_priority=50),
            row("k1-soccer-model", ["KXEPLGAME"]),  # no priority: 100
            row("k1-nfl-model", ["KXNFLGAME"], seat_priority=10),
            row("k1-ncaaf-model", ["KXNCAAFGAME"], seat_priority=50))
        self.assertEqual([r["key"] for _, r in kalshi_founders.pending(self.house)],
                         ["k1-nfl-model", "k1-mlb-model", "k1-ncaaf-model", "k1-soccer-model"])
        self.assertEqual([kalshi_founders.seat(self.house).founder for _ in range(4)],
                         ["k1-nfl-model", "k1-mlb-model", "k1-ncaaf-model", "k1-soccer-model"])

    def test_a_malformed_row_is_skipped_and_told_once_an_hour_and_the_rest_are_seated(self):
        sports = self.house.niches["kalshi-sports"]
        sports.founders = tuple(f for f in sports.founders if f["key"] not in FLAGGED) + (
            row("k1-mlb-model", ["KXMLBGAME"], seat_full_league="true"),  # a string is not the flag
            row("k1-ncaaf-model", ["KXNCAAFGAME"], seat_priority="first"),
            row("k1-soccer-model", ["KXEPLGAME"], seat_priority=True),
            row("k1-unflagged", ["KXNCAAFGAME"], seat_full_league=False))  # an explicit false is no fault
        keyless = {k: v for k, v in row("k1-nfl-model", ["KXNFLGAME"]).items() if k != "key"}
        with patch.object(sports, "founders", sports.founders + (keyless,)):
            self.assertEqual(kalshi_founders.pending(self.house), [])  # (`House.founders` itself needs a key: CI's test_niches)
        born = kalshi_founders.seat(self.house)
        self.assertIsNone(born)
        self.assertEqual(self.founders_born(), [])
        (told,) = alerts(self.house, "warning", "flagged founder rows of league/niches.json are skipped")
        self.assertIn("4 flagged founder rows", told)
        for what in ("seat_full_league is 'true'", "a flagged row with no key", "k1-ncaaf-model: seat_priority is 'first'",
                     "k1-soccer-model: seat_priority is True"):
            self.assertIn(what, told)
        sports.founders = sports.founders + (row("k1-good", ["KXMLBTOTAL"]),)
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-good")
        self.assertEqual(len(alerts(self.house, "warning", "flagged founder rows of league/niches.json are skipped")), 1)
        self.clock.advance(3601)
        kalshi_founders.pending(self.house)
        self.assertEqual(len(alerts(self.house, "warning", "flagged founder rows of league/niches.json are skipped")), 2)

    def test_a_malformed_yields_seats_flag_yields_nothing_and_is_told(self):
        doc = json.loads(niches_module.NICHES_PATH.read_text(encoding="utf-8"))
        for desk in doc["niches"]:
            if desk["id"] == "kalshi-crypto-15m":
                desk["yields_seats"] = {"floor": "4", "reason": "a string floor"}
        path = Path(self.dir.name) / "niches.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with patch.object(niches_module, "NICHES_PATH", path):
            self.assertEqual(kalshi_founders.yielding(self.house), {})
            self.assertEqual(kalshi_founders.yielding(self.house), {})
        (told,) = alerts(self.house, "warning", "a desk row of league/niches.json yields no seat")
        self.assertIn("kalshi-crypto-15m: yields_seats is {'floor': '4'", told)

    def test_every_flagged_row_and_yielding_desk_in_niches_json_is_well_formed(self):
        doc = json.loads(niches_module.NICHES_PATH.read_text(encoding="utf-8"))
        for desk in doc["niches"]:
            for founder in desk.get("founders") or ():
                if "seat_full_league" in founder:
                    self.assertIn(founder["seat_full_league"], (True, False), founder.get("key"))
                    self.assertTrue(isinstance(founder.get("key"), str) and founder["key"].strip(), desk["id"])
                    priority = founder.get("seat_priority", kalshi_founders.DEFAULT_PRIORITY)
                    self.assertTrue(isinstance(priority, int) and not isinstance(priority, bool), founder["key"])
            if "yields_seats" in desk:
                flag = desk["yields_seats"]
                self.assertEqual(desk["venue"], "kalshi", desk["id"])
                self.assertTrue(isinstance(flag.get("floor"), int) and not isinstance(flag["floor"], bool) and flag["floor"] >= 1)
                self.assertTrue(str(flag.get("reason") or "").strip(), desk["id"])

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


class Switch(HouseCase):
    def test_a_house_without_the_switch_seats_no_founder_and_says_nothing(self):
        self.assertFalse(self.house.settings.kalshi_founders, "off unless the floor's House turns it on")
        sports = self.house.niches["kalshi-sports"]
        sports.founders = tuple(sports.founders) + (row("k1-mlb-model", ["KXMLBGAME", "KXMLBTOTAL"]),)
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertNotIn("k1-mlb-model", {a.founder for a in self.house.registry.agents.values()})
        self.assertEqual(alerts(self.house, "warning", "founder"), [])

    def test_the_options_house_never_turns_it_on(self):
        """The options overhaul (Sept 26, 2026): the floor's House seats no Kalshi founder, whatever config.json says."""
        import inspect
        from league import service

        source = inspect.getsource(service.build)
        self.assertIn('kalshi_founders=False', source)
        self.assertNotIn('config.get("kalshi_founders"', source)


class FullLeague(FounderSeats):
    def test_a_full_league_displaces_the_weakest_eligible_resident_of_the_most_negative_desk(self):
        alts, alts_2, majors = self.seated("alts", ALTS), self.seated("alts", ALTS), self.seated("majors")
        self.assertEqual({a.specialty for a in (alts, alts_2, majors)}, {"alpaca-crypto-alts", "alpaca-crypto-majors"})
        self.blocks(alts, -0.01, 6)     # the alts desk: -0.06 over 6 blocks
        self.blocks(majors, -0.002, 6)  # the majors desk: -0.012 over 6 blocks
        self.full()
        self.clock.advance(GRACE)  # past a paper seat's grace: a newcomer without forward evidence may take one
        # The House's own order: a resident that has never traded first (alts_2 has no block of its own).
        self.assertEqual(self.house._weakest(self.rules).id, alts_2.id)
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
        self.assertEqual(text["text"].count("died on rung"), 1, "one postmortem, not one wrapped in another")
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

    def test_a_founder_asks_the_seat_market_as_a_newcomer_without_forward_evidence(self):
        idle = self.seated("idle", ALTS)  # never traded
        loser = self.seated("loser", ALTS)
        self.blocks(loser, -0.01, 6)
        self.full()
        self.clock.advance(3601)  # past a never-traded seat's fair chance, inside the plain grace
        self.assertEqual(self.house._weakest(self.rules, evidenced=True).id, idle.id, "an evidenced newcomer may take it")
        self.assertIsNone(self.house._weakest(self.rules))
        asked = []
        real = self.house._displaceable

        def displaceable(rules, **kw):
            asked.append((kw.get("evidenced"), kw.get("newcomer"), kw.get("specialty")))
            return real(rules, **kw)

        with patch.object(self.house, "_displaceable", side_effect=displaceable):
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(idle.id).alive)
        self.assertEqual(asked, [(False, Newcomer(family=self.family_of("k1-mlb-model"), venue="kalshi", forward=None,
                                                   what="the founder k1-mlb-model"), None)])
        self.clock.advance(GRACE)
        born = kalshi_founders.seat(self.house)
        self.assertEqual(born.founder, "k1-mlb-model")
        self.assertFalse(self.house.registry.get(idle.id).alive)

    def test_a_holder_a_drained_resident_and_a_desks_last_trader_are_never_displaced(self):
        holder, drained, last = self.seated("holder", ALTS), self.seated("drained", ALTS), self.seated("last", ALTS)
        for agent in (holder, drained, last):
            self.blocks(agent, -0.01, 6)
        self.house._house_control(drained, "pause_entries", "test: the House drains it")
        self.full()
        self.clock.advance(GRACE)
        self.assertEqual(len(self.house._displaceable(self.rules)), 3, "the House's own rules would let each go")
        with patch.object(kalshi_founders, "_holding", side_effect=lambda house, agent: agent.id == holder.id), \
                patch.object(self.house, "_last_traders", return_value=[last.id]):
            self.assertIsNone(kalshi_founders.seat(self.house))
            self.assertEqual([self.house.registry.get(a.id).alive for a in (holder, drained, last)], [True] * 3)
            why = self.house._state["seat_refusals"]["founders"]["why"]
            self.assertIn("holding a position or a working order 1", why)
            self.assertIn("drained or winding down 1", why)
            self.house._house_control(drained, "resume_entries", "test: the drain ended")
            self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertEqual([self.house.registry.get(a.id).alive for a in (holder, drained, last)], [True, False, True])

    def test_a_desk_whose_record_is_not_negative_is_never_taken_from(self):
        gone = self.seated("gone", ALTS)
        self.blocks(gone, +0.01, 6)
        self.house.kill(gone, "evidence", "test")  # the alts desk's record is positive through a member that died
        idle = self.seated("idle", ALTS)  # never traded: the House's own rules would let a newcomer take it
        stale = self.seated("stale", ALTS)
        self.blocks(stale, -0.02, 6, at=now_iso(lambda: self.clock() - 8 * 86400))  # negative all told, outside the 7 days
        self.full()
        self.clock.advance(GRACE)
        self.assertIsNotNone(self.house._weakest(self.rules))
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
        self.clock.advance(GRACE)
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
        self.clock.advance(GRACE)
        with patch.object(self.house, "_family_proven", return_value=True), \
                patch.object(self.house.allocator, "family", return_value={"state": "swing"}):
            self.assertIsNotNone(self.house._weakest(self.rules, newcomer=sports_newcomer()),
                                 "the House's rule lets a proven newcomer take a proven family's member")
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(resident.id).alive)

    def test_a_desk_held_for_its_waiters_is_passed_over(self):
        alts, majors = self.seated("alts", ALTS), self.seated("majors")
        self.blocks(alts, -0.01, 6)
        self.blocks(majors, -0.002, 6)
        self.full()
        self.clock.advance(GRACE)
        waiting = {"proven": [], "graduates": [{"niche": "alpaca-crypto-alts", "candidate": "c1"}], "retained": [], "cards": [],
                   "strategies": []}
        with patch.object(self.house, "seat_waiters", return_value=waiting):
            self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertTrue(self.house.registry.get(alts.id).alive, "the alts desk's next seat is its waiting graduate's")
        self.assertFalse(self.house.registry.get(majors.id).alive)

    def test_the_answer_is_asked_again_after_the_probe_and_nobody_dies_when_it_moved(self):
        alts = self.seated("alts", ALTS)
        self.blocks(alts, -0.01, 6)
        self.full()
        self.clock.advance(GRACE)
        real = self.house.sandbox.needs

        def needs(box, code, **kw):
            self.house.evaluator.promote(alts.id, 2, "test: promoted to real money while the probe ran")
            return real(box, code, **kw)

        with patch.object(self.house.sandbox, "needs", side_effect=needs):
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(self.founders_born(), [])
        self.assertTrue(self.house.registry.get(alts.id).alive)
        self.assertEqual(self.house.ledger.count(kinds="agent.died"), 0)
        self.assertIn("real money 1", self.house._state["seat_refusals"]["founders"]["why"])


class FullDesk(FounderSeats):
    def test_a_full_founder_desk_waits_and_nobody_is_displaced_on_it(self):
        resident = self.house.found(["football-favorites"])[0]  # an unflagged founder of the sports desk
        elsewhere = self.seated("elsewhere", ALTS)
        self.blocks(elsewhere, -0.01, 6)  # a negative desk elsewhere, and a league with room: the desk is what is full
        self.house.niches["kalshi-sports"].max_members = 1
        self.clock.advance(GRACE)
        self.assertIsNotNone(self.house._weakest(self.rules, specialty="kalshi-sports", evidenced=True))
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertTrue(self.house.registry.get(resident.id).alive and self.house.registry.get(elsewhere.id).alive)
        self.assertEqual(self.house.ledger.count(kinds="agent.died"), 0)
        self.assertIn("its desk is full (1 of 1), and a founder takes only a free seat of its own desk",
                      self.house._state["seat_refusals"]["founders"]["why"])
        self.assertEqual(len(alerts(self.house, "warning", "flagged founders wait for a seat")), 1)
        self.house.niches["kalshi-sports"].max_members = 2  # the run raises the desk's cap: the next pass seats one
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertTrue(self.house.registry.get(resident.id).alive)

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
        self.assertEqual(text["text"].count("died on rung"), 1, "one postmortem, not one wrapped in another")
        self.assertTrue(self.house.registry.get(idle.id).code, "the program stays in the graveyard")
        # Stamped as `kill` stamps a displacement: the seat market takes no second resident of the desk this tick.
        kept = {}
        self.house._displaceable(self.rules, specialty=self.DESK, evidenced=True, why=kept)
        self.assertIn("one displacement a desk a tick", kept)

    def test_a_noisy_winner_goes_and_an_evidenced_winner_stays(self):
        # Sept 25, 2026, 22:00Z: crypto-15m's pooled record was -4.17 over 375 active blocks, but 6 of its 7 members had a
        # positive own mean (three on noise: t 0.32, 0.19, one block), so the seat market's plain "a winner" kept them all
        # and the desk never yielded. On this path a winner needs evidence: >= 6 active blocks and a one-sided t >= 1.0.
        losers = [self.resident() for _ in range(3)]
        for agent in losers:
            self.order(agent, "0.94", post_only=True)  # each holds a working order: kept for that, whatever its record
        noisy = self.resident(growth=0.05, blocks=4)
        self.blocks(noisy, -0.04, 4)  # mean +0.005 over 8 blocks, t about 0.29
        evidenced = self.resident(growth=0.01, blocks=6)  # the same positive growth every block
        self.full()
        born = kalshi_founders.seat(self.house)
        self.assertEqual(born.founder, "k1-mlb-model")
        self.assertEqual(self.alive(noisy, evidenced, *losers), [False, True, True, True, True])
        self.assertEqual(self.house.registry.get(noisy.id).cause, "desk_closed")

    def test_a_desk_that_gave_up_a_seat_this_tick_yields_none_until_the_next(self):
        # The forward-first run's F3 shrinks this desk in the same births pass, before this line: one seat a desk a tick.
        residents = [self.resident() for _ in range(5)]
        self.full()
        self.house._desk_displaced[self.DESK] = self.clock()
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(sum(self.alive(*residents)), 5)
        self.assertEqual(len(alerts(self.house, "warning", "kalshi-crypto-15m already gave up a seat this tick")), 1)
        self.clock.advance(float(self.house.settings.tick_seconds) + 1)
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-mlb-model")
        self.assertEqual(sum(self.alive(*residents)), 4)

    def test_found_refusing_or_raising_after_a_retirement_was_decided_kills_nobody(self):
        residents = [self.resident() for _ in range(5)]
        self.full()
        with patch.object(self.house, "found", side_effect=RuntimeError("the registry write failed")):
            self.assertIsNone(kalshi_founders.seat(self.house))
        with patch.object(self.house, "found", side_effect=ValueError("its NEEDS read an unknown feed")):
            self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(sum(self.alive(*residents)), 5)
        self.assertEqual(self.house.ledger.count(kinds="agent.died"), 0)
        self.assertEqual(len(alerts(self.house, "warning", "flagged founders could not be seated", "the registry write failed")), 1)
        self.assertEqual(len(alerts(self.house, "warning", "flagged founder k1-mlb-model could not be born")), 1)
        self.assertEqual(kalshi_founders.seat(self.house).founder, "k1-nfl-model", "the refused program waits for a new version")
        self.assertEqual(sum(self.alive(*residents)), 4)

    def test_a_restart_seats_no_founder_twice_and_retires_no_one_more(self):
        residents = [self.resident() for _ in range(6)]
        self.full()
        born = kalshi_founders.seat(self.house)
        self.assertEqual(sum(self.alive(*residents)), 5)
        self.house.close(wait=None)
        self.house = self.new_house()  # the same root: the registry and house.json are read back
        self.flag_rows(self.house)
        self.house.books["kalshi-shadow"] = Book("kalshi-shadow", self.kalshi, self.house.ledger, fees=Fees("kalshi"),
                                                 real_money=False, clock=self.clock)
        self.house.game["economy"]["max_population"] = self.rules["max_population"]
        nfl = kalshi_founders.seat(self.house)
        self.assertEqual((born.founder, nfl.founder), ("k1-mlb-model", "k1-nfl-model"))
        self.assertEqual(sum(self.alive(*residents)), 4, "one retirement a birth, the floor of 4 reached")
        self.assertIsNone(kalshi_founders.seat(self.house))
        self.assertEqual(self.founders_born(), ["k1-mlb-model", "k1-nfl-model"])
        self.assertEqual(self.house.ledger.count(kinds="agent.died"), 2)

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


class DeskRecords(FounderSeats):
    DESK = "alpaca-crypto-alts"

    def test_a_block_counts_by_when_it_began_not_when_its_row_was_written(self):
        agent = self.seated("alts", ALTS)
        old = now_iso(lambda: self.clock() - 8 * 86400)[:13]
        fresh = now_iso(lambda: self.clock() - 86400)[:13]
        for key, growth in ((old, -0.5), (fresh, -0.01), (fresh[:10], -0.02)):  # a backlog row written now, an hour, a day
            self.house.ledger.append("eval.block", {"log_growth": growth, "active": True, "book": "alpaca-paper", "key": key},
                                     agent=agent.id)
        self.house.ledger.append("eval.block", {"log_growth": -0.4, "active": False, "book": "alpaca-paper", "key": fresh},
                                 agent=agent.id)  # not active: not counted
        blocks, growth = kalshi_founders.desk_records(self.house)[self.DESK]
        self.assertEqual(blocks, 2)
        self.assertAlmostEqual(growth, -0.03)

    def test_it_is_kept_an_hour_reads_only_new_rows_and_keeps_only_the_window(self):
        agent = self.seated("alts", ALTS)
        self.blocks(agent, -0.01, 6)
        self.assertEqual(kalshi_founders.desk_records(self.house)[self.DESK][0], 6)
        self.blocks(agent, -0.01, 2)
        self.assertEqual(kalshi_founders.desk_records(self.house)[self.DESK][0], 6, "kept an hour")
        reads = []
        real = self.house.ledger.iter

        def spy(**kw):
            reads.append(kw.get("after", 0))
            return real(**kw)

        self.clock.advance(3601)
        with patch.object(self.house.ledger, "iter", side_effect=spy):
            self.assertEqual(kalshi_founders.desk_records(self.house)[self.DESK][0], 8)
        self.assertEqual(len(reads), 1)
        self.assertGreater(reads[0], 0, "after the cursor, never the whole ledger again")
        self.clock.advance(8 * 86400)
        self.assertEqual(kalshi_founders.desk_records(self.house), {})
        tape = self.house._data_cache[kalshi_founders._TAPE_KEY][1]
        self.assertEqual(tape.rows, [], "the rows leave with the window")


def sports_newcomer():
    from league.house import Newcomer

    return Newcomer(family="sports-favorites", venue="kalshi", what="the founder k1-mlb-model")


class EvidencedWinner(unittest.TestCase):
    def test_a_winner_on_the_yield_path_needs_six_blocks_and_a_t_of_one(self):
        ok = kalshi_founders.evidenced_winner
        self.assertTrue(ok([0.01] * 6, 6), "the same positive growth every block is evidence")
        self.assertFalse(ok([0.01] * 5, 6), "too few blocks")
        self.assertFalse(ok([0.05, -0.04] * 4, 6), "positive mean, t about 0.29: noise")
        self.assertFalse(ok([-0.01] * 6, 6))
        self.assertTrue(ok([0.02, 0.01, 0.03, 0.02, 0.01, 0.02], 6))
        self.assertFalse(ok([], 6))


if __name__ == "__main__":
    unittest.main()
