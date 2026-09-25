"""The options desk's structure founders, seated (`league/options_desk.py`, Sept 25, 2026).

`seat_founders` births the options desk's structure founders one a tick, at rung 1 on the structure book;
when the league is full it retires one practice resident a tick by the options desk's seat rule: (a) the
options desk's own residents of a losing family, then (b) residents of the losing Alpaca desks, never a
Kalshi desk, never real money, a winner, a proven family's member, one holding a position while its market
is shut, one with a working order, one born under two hours ago, or a structure agent; twelve at most."""

import dataclasses
import unittest
from unittest import mock

from league import options_desk, seeds as seeds_module
from league.book import Intent
from league.ledger import now_iso
from league.tests.test_house import BUYER
from league.tests.test_options import STRUCTURE_AGENT, StructureHouseCase, call

CONDOR_SEED = STRUCTURE_AGENT.replace("test-structures", "test-condor")
VERTICAL_SEED = STRUCTURE_AGENT.replace("test-structures", "test-vertical").replace('"iron_condor"', '"debit_vertical"')
BROKEN_SEED = STRUCTURE_AGENT.replace("def decide(ctx):", "import os\n\ndef decide(ctx):")
TEST_SEEDS = {"test-condor": CONDOR_SEED, "test-vertical": VERTICAL_SEED, "test-broken": BROKEN_SEED}
SINGLE_LEG = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "asset_class": "option", "symbols": ["F"], "max_days_to_expiry": 21, "style": "test-single"}
PARAMS = {}

def decide(ctx):
    return {"intents": []}
'''
KALSHI = '''
NEEDS = {"venue": "kalshi", "horizon": "day", "series": ["KXHIGHNY"], "style": "test-weather"}
PARAMS = {}

def decide(ctx):
    return {"intents": []}
'''
HOURS = 3600.0


class SeatCase(StructureHouseCase):
    def setUp(self):
        super().setUp()
        options_desk._DECLARES.clear()
        rows = [{"name": name, "file": f"{name}.py", "family": f"options-{name.split('-', 1)[1]}", "why": f"the {name} test founder"}
                for name in TEST_SEEDS]
        original = seeds_module.load
        for patcher in (mock.patch.object(seeds_module, "SEEDS", list(seeds_module.SEEDS) + rows),
                        mock.patch.object(seeds_module, "load", side_effect=lambda name: TEST_SEEDS.get(name) or original(name))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.plant("test-condor", "test-vertical")
        self.addCleanup(options_desk._DECLARES.clear)
        self.n = 0

    def plant(self, *names):
        niche = self.house.niches[options_desk.OPTIONS_DESK]
        # The desk's two single-leg founders stay; its real structure founders (options-gap-drift since Sept 25,
        # 2026) are left out so each test seats exactly the planted ones.
        kept = tuple(f for f in niche.founders if f["key"] in ("options-breakout", "options-pullback") or f["key"] in TEST_SEEDS)
        niche.founders = kept + tuple({"seed": name, "key": name} for name in names if name not in {f["key"] for f in kept})

    def born(self):
        return {a.founder: a for a in self.house.registry.agents.values() if a.founder in TEST_SEEDS}

    def block(self, agent_id, growth, *, days_ago=0.5, book="alpaca-paper"):
        self.n += 1
        self.house.ledger.append("eval.block", {"book": book, "key": f"k{self.n}", "log_growth": growth, "active": True},
                                 agent=agent_id, at=now_iso(lambda: self.clock() - days_ago * 86400))
        self.house._data_cache.pop("family_forward", None)

    def resident(self, code=BUYER, family="test-family", growth=None, name="resident", seat=False):
        self.n += 1
        agent = self.house.spawn(name, family, code.replace("PARAMS = {", f"PARAMS = {{'n': {self.n}, ", 1), reason="a resident")
        if seat and self.house.evaluator.rung(agent.id) < 1:
            self.house.evaluator.seat(agent.id, 1, "test")
        if growth is not None:
            self.block(agent.id, growth)
        return agent

    def options_resident(self, growth, family="options-pullback"):
        return self.resident(SINGLE_LEG, family=family, growth=growth, name="krasker")

    def full(self):
        self.house.game["economy"]["max_population"] = len(self.house.registry.living())

    def grown_up(self):
        self.at(self.clock() + 3 * HOURS)  # 14:00 in New York: residents are past the rule's two hours, in the session

    def retired(self):
        return [e.agent for e in self.house.ledger.iter(kinds="agent.died") if e.payload.get("cause") == options_desk.CAUSE]


class Births(SeatCase):
    def test_only_seeds_whose_needs_say_structures_are_structure_founders(self):
        self.assertTrue(options_desk.declares_structures(CONDOR_SEED))
        self.assertFalse(options_desk.declares_structures(seeds_module.load("options-breakout")))
        self.assertFalse(options_desk.declares_structures("NEEDS = {'structures': 'yes'}\n"))
        self.assertFalse(options_desk.declares_structures("def (:\n"))
        self.assertEqual([f["key"] for f in options_desk.owed(self.house)], ["test-condor", "test-vertical"])

    def test_one_founder_a_tick_on_practice_and_on_the_structure_book_then_nothing(self):
        first = options_desk.seat_founders(self.house)
        self.assertEqual([a.founder for a in first], ["test-condor"])
        agent = first[0]
        self.assertEqual((agent.specialty, agent.name, agent.family), ("alpaca-options", "krasker", "options-condor"))
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertTrue(self.house.is_structure_agent(agent))
        book = self.house.book_of(agent)
        self.assertEqual(book.name, "options-shadow")
        self.assertTrue(book.account(agent.id).funded)
        self.assertEqual([a.founder for a in options_desk.seat_founders(self.house)], ["test-vertical"])
        self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertEqual(set(self.born()), {"test-condor", "test-vertical"})
        self.assertEqual(self.retired(), [])  # room in the league: nobody retired

    def test_idempotent_across_a_restart_and_the_single_contract_founders_are_not_its_to_seat(self):
        options_desk.seat_founders(self.house)
        self.house.close(wait=None)
        self.house = self.new_house()
        self.plant("test-condor", "test-vertical")
        self.assertEqual([f["key"] for f in options_desk.owed(self.house)], ["test-vertical"])
        options_desk.seat_founders(self.house)
        options_desk.seat_founders(self.house)
        self.assertEqual(sorted(self.born()), ["test-condor", "test-vertical"])
        self.assertFalse([a for a in self.house.registry.agents.values() if a.founder in ("options-breakout", "options-pullback")])

    def test_cheap_when_nothing_is_owed(self):
        options_desk.seat_founders(self.house)
        options_desk.seat_founders(self.house)
        self.full()
        with mock.patch.object(self.house, "founders", side_effect=AssertionError("read the founders")), \
                mock.patch.object(self.house, "standings", side_effect=AssertionError("read the standings")), \
                mock.patch.object(self.house.sandbox, "needs", side_effect=AssertionError("probed")):
            self.assertEqual(options_desk.seat_founders(self.house), [])

    def test_a_failure_costs_only_this_step_and_a_sail_error_is_the_births_passs_to_defer(self):
        from league.sandbox import SandboxError

        with mock.patch.object(options_desk, "owed", side_effect=RuntimeError("a bug")):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertTrue([e for e in self.house.ledger.iter(kinds="ops.alert") if "founder seating failed" in str(e.payload)])
        with mock.patch.object(self.house.sandbox, "needs", side_effect=SandboxError("Sail is down")):
            with self.assertRaises(SandboxError):
                options_desk.seat_founders(self.house)

    def test_a_founder_that_cannot_be_born_is_told_once_and_not_tried_again_until_its_code_changes(self):
        niche = self.house.niches[options_desk.OPTIONS_DESK]
        niche.founders = tuple(f for f in niche.founders if f["key"] != "test-condor")
        self.plant("test-broken")
        options_desk.seat_founders(self.house)  # test-vertical
        self.assertEqual(options_desk.seat_founders(self.house), [])  # test-broken is refused
        self.assertIn("test-broken", self.house._state["options_desk"]["refused"])
        with mock.patch.object(self.house, "spawn", side_effect=AssertionError("tried again")):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        warnings = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "test-broken" in str(e.payload)]
        self.assertEqual(len(warnings), 1)


class ThePopulationStep(SeatCase):
    def test_the_births_pass_seats_the_founders_after_enroll(self):
        order = []
        with mock.patch.object(self.house, "enroll", side_effect=lambda: order.append("enroll")), \
                mock.patch.object(options_desk, "seat_founders", side_effect=lambda house: order.append(("seat", house))), \
                mock.patch.object(self.house, "_refill", side_effect=lambda rules: order.append("refill")):
            self.house._births(self.house.game["economy"])
        self.assertEqual(order, ["enroll", ("seat", self.house), "refill"])

    def test_a_tick_births_a_founder(self):
        self.house.tick()
        self.assertEqual(sorted(self.born()), ["test-condor"])


class TheSeatRule(SeatCase):
    def test_the_options_desks_own_losing_family_goes_first_most_negative_first(self):
        mild = self.options_resident(-0.05)
        worst = self.options_resident(-0.17)
        crypto = self.resident(growth=-0.40)  # an Alpaca desk far more negative: still after (a)
        self.grown_up()
        self.full()
        born = options_desk.seat_founders(self.house)
        self.assertEqual([a.founder for a in born], ["test-condor"])
        self.assertEqual(self.retired(), [worst.id])
        self.assertEqual(len(self.house.registry.living()), self.house.game["economy"]["max_population"])
        self.at(self.clock() + 60)
        options_desk.seat_founders(self.house)  # one a tick: the next tick takes the next
        self.assertEqual(self.retired(), [worst.id, mild.id])
        self.assertTrue(self.house.registry.get(crypto.id).alive)

    def test_the_death_is_its_own_cause_with_a_postmortem_naming_the_founder_and_the_rule_and_is_counted(self):
        loser = self.options_resident(-0.10)
        self.grown_up()
        self.full()
        options_desk.seat_founders(self.house)
        died = [e.payload for e in self.house.ledger.iter(kinds="agent.died", agent=loser.id)][0]
        self.assertEqual(died["cause"], "options_seat")
        post = [e.payload["text"] for e in self.house.ledger.iter(kinds="agent.postmortem", agent=loser.id)][0]
        self.assertIn("structure founder test-condor", post)
        self.assertIn("seat rule", post)
        self.assertIn("rule (a)", post)
        note = [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "options desk seat rule"]
        self.assertEqual((note[0]["retired"], note[0]["count"], note[0]["cap"], note[0]["rule"]), (loser.id, 1, 12, "a"))
        self.assertEqual(options_desk.retired_count(self.house), 1)
        self.house.close(wait=None)
        self.house = self.new_house()  # counted from the ledger: a restart (or a lost house.json) keeps the count
        self.assertEqual(options_desk.retired_count(self.house), 1)

    def test_then_the_losing_alpaca_desks_most_negative_first_and_never_a_kalshi_desk(self):
        up = self.resident(BUYER.replace('["BTC/USD"]', '["SOL/USD"]').replace("test-buyer", "test-alts"), growth=0.30)  # alts desk: up
        weak = self.resident(growth=-0.02)
        weaker = self.resident(growth=-0.06)
        self.resident(growth=0.01)  # a winner on the losing majors desk (the desk nets -0.07)
        kalshi = self.resident(KALSHI, family="test-weather", growth=-0.90)
        self.assertEqual((up.specialty, weak.specialty, kalshi.specialty), ("alpaca-crypto-alts", "alpaca-crypto-majors", "kalshi-weather"))
        self.grown_up()
        self.full()
        options_desk.seat_founders(self.house)
        self.assertEqual(self.retired(), [weaker.id])
        self.at(self.clock() + 60)
        options_desk.seat_founders(self.house)
        self.assertEqual(self.retired(), [weaker.id, weak.id])
        self.assertTrue(self.house.registry.get(kalshi.id).alive)
        self.assertTrue(self.house.registry.get(up.id).alive)

    def test_on_a_losing_desk_one_that_never_traded_goes_before_a_trader_at_the_same_record(self):
        loser = self.resident(growth=-0.05)  # makes the majors desk lose
        trader, idle = self.resident(), self.resident()
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "side": "buy", "quantity": "1", "price": "1", "source": "test"},
                                 agent=trader.id)
        self.house.kill(self.house.registry.get(loser.id), "test")
        self.grown_up()
        self.full()
        chosen, why, numbers = options_desk.retiree(self.house)
        self.assertEqual((chosen.id, numbers["rule"], numbers["traded"]), (idle.id, "b", False))
        self.assertIn("never having traded", why)

    def test_what_the_rule_always_keeps(self):
        agents = {name: self.options_resident(-0.10) for name in ("real", "winner", "proven", "working", "shut", "structure")}
        self.house.registry.agents[agents["structure"].id].needs["structures"] = True  # a structure agent of a losing family
        young_at = self.clock() + 2 * HOURS
        self.grown_up()
        young = self.options_resident(-0.30)  # born an hour ago
        self.at(young_at + HOURS)
        real = {agents["real"].id: 2}
        standings = [dataclasses.replace(s, rung=real.get(s.agent, s.rung), mean_growth=0.01 if s.agent == agents["winner"].id else s.mean_growth)
                     for s in self.house.standings()]
        book = self.house.books["alpaca-paper"]
        for name in ("working", "shut"):
            self.house.seat(agents[name])
        contract = call(occ="F261009C00013000")
        self.broker.set_quote(contract, "0.40", "0.44")
        book.submit([Intent.new(agent=agents["working"].id, instrument=contract, side="buy", quantity="1", order_type="limit", limit_price="0.41",
                                reason="rests", created_at=now_iso(self.clock), nonce="w")])
        filled = book.submit([Intent.new(agent=agents["shut"].id, instrument=contract, side="buy", quantity="1", order_type="limit", limit_price="0.44",
                                         reason="held", created_at=now_iso(self.clock), nonce="s")])[0]
        self.assertEqual(filled.status, "filled", filled.detail)
        self.full()
        with mock.patch.object(self.house, "standings", return_value=standings), \
                mock.patch.object(self.house, "_family_proven", side_effect=lambda family, venue: family == "options-proven"), \
                mock.patch("league.venues.market_hours", return_value=False):
            self.house.registry.agents[agents["proven"].id].family = "options-proven"
            self.block(agents["proven"].id, -0.10)  # its own family loses too, so only "proven" can keep it
            self.house._data_cache.pop("family_forward", None)
            chosen, why, numbers = options_desk.retiree(self.house)
        self.assertIsNone(chosen, why)
        self.assertEqual(numbers["kept"], {"real money": 1, "a winner": 1, "a proven family's member": 1, "a working order": 1,
                                           "holding a position while its market is shut": 1, "a structure agent": 1,
                                           "born less than two hours ago": 1})
        self.assertTrue(self.house.registry.get(young.id).alive)

    def test_a_positive_own_record_or_a_winning_family_keeps_an_options_resident(self):
        self.options_resident(0.02)  # its own week is up (the family nets negative below)
        self.options_resident(-0.03, family="options-breakout-win")
        self.block(self.options_resident(-0.01, family="options-breakout-win").id, 0.50)  # that family nets positive
        self.options_resident(-0.30)  # makes options-pullback lose
        self.grown_up()
        self.full()
        chosen, _, numbers = options_desk.retiree(self.house, desk_only=True)
        self.assertEqual((numbers["rule"], chosen.family, numbers["own"]), ("a", "options-pullback", -0.3))

    def test_twelve_at_most_and_none_while_no_founder_is_owed(self):
        self.options_resident(-0.10)
        self.grown_up()
        self.full()
        with mock.patch.object(options_desk, "retired_count", return_value=options_desk.RETIRE_CAP):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertEqual(self.retired(), [])
        self.assertIn("its 12 residents", self.house._state["options_desk"]["waiting"]["why"])
        self.house._state["options_desk"].pop("waiting")
        with mock.patch.object(options_desk, "owed", return_value=[]):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertEqual(self.retired(), [])

    def test_nobody_to_retire_is_said_once_and_asked_again_in_a_few_minutes(self):
        self.resident(growth=0.02)
        self.grown_up()
        self.full()
        self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertIn("no resident may be retired", self.house._state["options_desk"]["waiting"]["why"])
        with mock.patch.object(options_desk, "retiree", side_effect=AssertionError("asked again at once")):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.at(self.clock() + options_desk.RETRY_SECONDS)
        self.assertEqual(options_desk.seat_founders(self.house), [])
        told = [e for e in self.house.ledger.iter(kinds="ops.alert") if "structure founders of the options desk wait" in str(e.payload)]
        self.assertEqual(len(told), 1)

    def test_a_full_options_desk_retires_only_on_itself(self):
        self.resident(growth=-0.40)  # a losing Alpaca desk's resident: not a seat on the options desk
        self.grown_up()
        niche = self.house.niches[options_desk.OPTIONS_DESK]
        niche.max_members = self.house.members(options_desk.OPTIONS_DESK)
        self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertEqual(self.retired(), [])
        mine = self.options_resident(-0.05)
        self.grown_up()
        niche.max_members = self.house.members(options_desk.OPTIONS_DESK)
        self.house._state["options_desk"].pop("waiting")
        options_desk.seat_founders(self.house)
        self.assertEqual(self.retired(), [mine.id])
        self.assertLessEqual(self.house.members(options_desk.OPTIONS_DESK), niche.max_members)

    def test_it_runs_under_the_lifecycle_lock_and_probes_outside_it(self):
        self.options_resident(-0.10)
        self.grown_up()
        self.full()
        seen = {}
        probe, spawn, kill = self.house.sandbox.needs, self.house.spawn, self.house.kill

        def held():
            return self.house._lifecycle_lock._is_owned()

        def watch(name, fn):
            def run(*args, **kw):
                seen[name] = held()
                return fn(*args, **kw)
            return run

        with mock.patch.object(self.house.sandbox, "needs", side_effect=watch("probe", probe)), \
                mock.patch.object(self.house, "spawn", side_effect=watch("spawn", spawn)), \
                mock.patch.object(self.house, "kill", side_effect=watch("kill", kill)):
            options_desk.seat_founders(self.house)
        self.assertEqual(seen, {"probe": False, "spawn": True, "kill": True})


class SafeRetirement(SeatCase):
    def test_a_retirement_that_fails_leaves_the_founder_unborn_and_the_league_at_its_ceiling(self):
        resident = self.options_resident(-0.10)
        self.grown_up()
        self.full()
        ceiling = self.house.game["economy"]["max_population"]
        with mock.patch.object(self.house, "kill", side_effect=RuntimeError("a venue error in the wind-down")):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertEqual(len(self.house.registry.living()), ceiling)
        self.assertTrue(self.house.registry.get(resident.id).alive)
        self.assertEqual(self.born(), {})
        self.assertTrue([e for e in self.house.ledger.iter(kinds="ops.alert") if "could not be retired" in str(e.payload)])

    def test_a_founder_the_probe_refuses_retires_nobody(self):
        resident = self.options_resident(-0.10)
        self.grown_up()
        self.full()
        refused = mock.Mock(result={"ok": False, "error": "a syntax error"}, seconds=0.1, created=False)
        with mock.patch.object(self.house.sandbox, "needs", return_value=refused):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertTrue(self.house.registry.get(resident.id).alive)
        self.assertEqual(self.retired(), [])
        self.assertIn("test-condor", self.house._state["options_desk"]["refused"])

    def test_the_seat_is_freed_before_the_birth(self):
        self.options_resident(-0.10)
        self.grown_up()
        self.full()
        order = []
        kill, spawn = self.house.kill, self.house.spawn
        with mock.patch.object(self.house, "kill", side_effect=lambda *a, **k: (order.append("kill"), kill(*a, **k))), \
                mock.patch.object(self.house, "spawn", side_effect=lambda *a, **k: (order.append("spawn"), spawn(*a, **k))[1]):
            options_desk.seat_founders(self.house)
        self.assertEqual(order, ["kill", "spawn"])


class TheCanary(SeatCase):
    def test_found_and_founders_never_birth_a_structure_founder(self):
        """A fresh (canary) House is under `min_population`, and `found` births every niche founder at once: the
        structure founders are `seat_founders`' alone, one a tick."""
        keys = {row["key"] for row in self.house.founders()}
        self.assertFalse(keys & set(TEST_SEEDS))
        self.assertIn("options-breakout", keys)  # the single-contract founders are still `found`'s
        with mock.patch.object(self.house, "spawn", wraps=self.house.spawn) as spawn:
            self.house.found(["options-breakout", "test-condor", "test-vertical"])
        self.assertEqual(self.born(), {})
        self.assertEqual([c.kwargs.get("founder") for c in spawn.call_args_list], ["options-breakout"])
        self.assertEqual([f["key"] for f in options_desk.owed(self.house)], ["test-condor", "test-vertical"])


class Records(SeatCase):
    def test_practice_blocks_of_the_last_seven_days_of_every_member_living_or_dead(self):
        majors = self.resident()
        other = self.resident()
        self.block(majors.id, -0.01)
        self.block(other.id, -0.02)
        self.block(majors.id, 0.50, book="alpaca")  # real money is not the practice record
        self.block(majors.id, -0.50, days_ago=7.5)
        self.house.kill(self.house.registry.get(other.id), "test")
        desks = options_desk.desk_records(self.house)
        self.assertEqual((desks["alpaca-crypto-majors"]["blocks"], desks["alpaca-crypto-majors"]["agents"]), (2, 2))
        self.assertAlmostEqual(desks["alpaca-crypto-majors"]["growth"], -0.03)
        self.assertAlmostEqual(options_desk.records(self.house)[majors.id]["growth"], -0.01)
        self.block(majors.id, 0.04)  # folded incrementally
        self.assertAlmostEqual(options_desk.desk_records(self.house)["alpaca-crypto-majors"]["growth"], 0.01)


if __name__ == "__main__":
    unittest.main()
