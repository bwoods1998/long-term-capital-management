"""The options desk's structure founders, seated (`league/options_desk.py`, Sept 25, 2026).

`seat_founders` births the options desk's structure founders one a tick, at rung 1 on the structure book,
and when the league is full takes the seat of a resident the seat market offers only if that resident's
desk has a negative 7-day practice record; never one the seat market protects; idempotent across ticks
and restarts."""

import unittest
from unittest import mock

from league import options_desk, seeds as seeds_module
from league.ledger import now_iso
from league.tests.test_house import BUYER
from league.tests.test_options import STRUCTURE_AGENT, StructureHouseCase

CONDOR_SEED = STRUCTURE_AGENT.replace("test-structures", "test-condor")
VERTICAL_SEED = STRUCTURE_AGENT.replace("test-structures", "test-vertical").replace('"iron_condor"', '"debit_vertical"')
BROKEN_SEED = STRUCTURE_AGENT.replace("def decide(ctx):", "import os\n\ndef decide(ctx):")
ALTS_BUYER = BUYER.replace('["BTC/USD"]', '["SOL/USD"]').replace("test-buyer", "test-alts")
TEST_SEEDS = {"test-condor": CONDOR_SEED, "test-vertical": VERTICAL_SEED, "test-broken": BROKEN_SEED}


class SeatFounders(StructureHouseCase):
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

    def plant(self, *names):
        niche = self.house.niches[options_desk.OPTIONS_DESK]
        niche.founders = tuple(niche.founders) + tuple({"seed": name, "key": name} for name in names)

    def born(self):
        return {a.founder: a for a in self.house.registry.agents.values() if a.founder in TEST_SEEDS}

    def block(self, agent_id, growth, *, days_ago=1.0, book="alpaca-paper"):
        self.house.ledger.append("eval.block", {"book": book, "key": f"k{self.clock()}:{growth}:{days_ago}", "log_growth": growth, "active": True},
                                 agent=agent_id, at=now_iso(lambda: self.clock() - days_ago * 86400))

    def full(self):
        self.house.game["economy"]["max_population"] = len(self.house.registry.living())

    # -- who is a structure founder, and what is owed
    def test_only_seeds_whose_needs_say_structures_are_structure_founders(self):
        self.assertTrue(options_desk.declares_structures(CONDOR_SEED))
        self.assertFalse(options_desk.declares_structures(seeds_module.load("options-breakout")))
        self.assertFalse(options_desk.declares_structures("NEEDS = {'structures': 'yes'}\n"))
        self.assertFalse(options_desk.declares_structures("def (:\n"))
        self.assertEqual([f["key"] for f in options_desk.owed(self.house)], ["test-condor", "test-vertical"])

    # -- births
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
        with mock.patch.object(self.house, "founders", side_effect=AssertionError("read the founders")), \
                mock.patch.object(self.house, "_displaceable", side_effect=AssertionError("asked the seat market")):
            self.assertEqual(options_desk.seat_founders(self.house), [])

    def test_a_founder_that_cannot_be_born_is_told_once_and_not_tried_again_until_its_code_changes(self):
        self.plant("test-broken")
        self.house.niches[options_desk.OPTIONS_DESK].founders = tuple(
            f for f in self.house.niches[options_desk.OPTIONS_DESK].founders if f["key"] != "test-condor")  # broken is second now
        options_desk.seat_founders(self.house)  # test-vertical
        born = options_desk.seat_founders(self.house)  # test-broken is refused; nothing else is owed
        self.assertEqual(born, [])
        self.assertIn("test-broken", self.house._state["options_desk"]["refused"])
        with mock.patch.object(self.house, "spawn", side_effect=AssertionError("tried again")):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        warnings = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "test-broken" in str(e.payload)]
        self.assertEqual(len(warnings), 1)

    # -- a full league
    def test_a_full_league_frees_a_seat_only_from_a_desk_whose_seven_day_record_is_negative(self):
        majors = self.house.spawn("buyer", "test-family", BUYER, reason="a resident")  # rung 0: an evidenced newcomer may take it
        alts = self.house.spawn("alts", "test-alts-family", ALTS_BUYER, reason="a resident")
        self.assertEqual((majors.specialty, alts.specialty), ("alpaca-crypto-majors", "alpaca-crypto-alts"))
        self.block(majors.id, 0.02)  # the majors desk is up over the week...
        self.block(alts.id, -0.03)  # ...the alts desk down,
        self.block(alts.id, 0.05, days_ago=8)  # and a gain eight days ago is outside the window
        self.full()
        born = options_desk.seat_founders(self.house)
        self.assertEqual([a.founder for a in born], ["test-condor"])
        self.assertFalse(self.house.registry.get(alts.id).alive)
        self.assertTrue(self.house.registry.get(majors.id).alive)
        self.assertEqual(len(self.house.registry.living()), self.house.game["economy"]["max_population"])
        died = [e.payload for e in self.house.ledger.iter(kinds="agent.died", agent=alts.id)]
        self.assertEqual(died[0].get("cause"), "displaced")
        post = [e.payload["text"] for e in self.house.ledger.iter(kinds="agent.postmortem", agent=alts.id)][0]
        self.assertIn("structure founder test-condor", post)
        self.assertIn("alpaca-crypto-alts", post)
        self.assertIn("-0.0300", post)

    def test_a_full_league_with_no_negative_desk_takes_nobody_and_says_so_once(self):
        majors = self.house.spawn("buyer", "test-family", BUYER, reason="a resident")
        self.block(majors.id, 0.02)
        self.full()
        self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertTrue(self.house.registry.get(majors.id).alive)
        waiting = self.house._state["options_desk"]["waiting"]
        self.assertIn("negative", waiting["why"])
        with mock.patch.object(self.house, "_displaceable", side_effect=AssertionError("asked again at once")):
            self.assertEqual(options_desk.seat_founders(self.house), [])  # asked again in a few minutes, not every tick
        self.clock.now += options_desk.RETRY_SECONDS
        self.assertEqual(options_desk.seat_founders(self.house), [])
        told = [e for e in self.house.ledger.iter(kinds="ops.alert") if "structure founders of the options desk wait" in str(e.payload)]
        self.assertEqual(len(told), 1)

    def test_never_a_resident_the_seat_market_protects(self):
        winner = self.house.spawn("buyer", "test-family", BUYER, reason="a resident")
        self.block(winner.id, -0.04)  # its desk is down...
        self.full()
        with mock.patch.object(self.house, "_displaceable", return_value=[]) as seat_market:  # ...but the seat market protects it
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertTrue(self.house.registry.get(winner.id).alive)
        kwargs = seat_market.call_args.kwargs
        self.assertTrue(kwargs["evidenced"])
        self.assertEqual((kwargs["newcomer"].family, kwargs["newcomer"].venue), ("options-condor", "alpaca"))
        self.assertIsNone(kwargs["specialty"])

    def test_a_desk_owed_to_a_higher_class_of_waiter_is_left_to_it(self):
        majors = self.house.spawn("buyer", "test-family", BUYER, reason="a resident")
        self.block(majors.id, -0.04)
        self.full()
        with mock.patch.object(self.house, "seat_waiters", return_value={"graduates": [{"niche": "alpaca-crypto-majors"}]}):
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertTrue(self.house.registry.get(majors.id).alive)

    def test_a_full_options_desk_frees_a_seat_only_on_itself(self):
        majors = self.house.spawn("buyer", "test-family", BUYER, reason="a resident")
        self.block(majors.id, -0.04)  # a displaceable resident of a losing desk elsewhere...
        niche = self.house.niches[options_desk.OPTIONS_DESK]
        niche.max_members = self.house.members(options_desk.OPTIONS_DESK)  # ...but the options desk itself is full
        with mock.patch.object(self.house, "_displaceable", wraps=self.house._displaceable) as seat_market:
            self.assertEqual(options_desk.seat_founders(self.house), [])
        self.assertEqual(seat_market.call_args.kwargs["specialty"], options_desk.OPTIONS_DESK)
        self.assertTrue(self.house.registry.get(majors.id).alive)
        self.assertIn("options desk is at its cap", self.house._state["options_desk"]["waiting"]["why"])

    def test_the_desk_record_counts_practice_blocks_of_the_last_seven_days_of_every_member_living_or_dead(self):
        majors = self.house.spawn("buyer", "test-family", BUYER, reason="a resident")
        other = self.house.spawn("buyer", "test-family", BUYER.replace("test-buyer", "test-b2"), reason="a resident")
        self.block(majors.id, -0.01)
        self.block(other.id, -0.02)
        self.block(majors.id, 0.50, book="alpaca")  # real money is not the practice record
        self.block(majors.id, -0.50, days_ago=7.5)
        self.house.kill(self.house.registry.get(other.id), "test")
        records = options_desk.desk_records(self.house)
        self.assertEqual(records["alpaca-crypto-majors"]["blocks"], 2)
        self.assertAlmostEqual(records["alpaca-crypto-majors"]["growth"], -0.03)
        self.block(majors.id, 0.04)  # folded incrementally
        self.assertAlmostEqual(options_desk.desk_records(self.house)["alpaca-crypto-majors"]["growth"], 0.01)


if __name__ == "__main__":
    unittest.main()
