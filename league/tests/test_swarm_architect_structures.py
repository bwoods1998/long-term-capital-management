"""THE STRUCTURES (Oct 1, 2026; league/swarm/architect.py `allowed_structures`): `architect.structures` names the types a
birth may be. Unset, every type, as before. Set, the GAPS (the architect's and the strategist's) and the coverage in the
requests are of those types only, the request names them, `admit` refuses any other type and the next request names each
refusal, the strategist's packet names them, and the tournament's forks breed only families of an allowed type (one of
another type is never retired for it). Every family, program and number here is invented."""

from __future__ import annotations

import json
import unittest

from league.swarm import architect as arch_mod
from league.swarm.architect import (STRUCTURE_REFUSALS_KEY, Architect, allowed_structures, structures_ignored)
from league.swarm.store import STRUCTURES
from league.swarm.strategist import Strategist
from league.swarm.tournament import Tournament
from league.tests.test_claude import message
from league.tests.test_frontier import FakeOpener
from league.tests.test_swarm_graveyard_digest import RouteCase
from league.tests.test_swarm_rounds import SPEC, RoundCase
from league.tests.test_swarm_strategist import FakeRouter, StrategistCase

#: The gateway's real types at this account's equity (Oct 1, 2026: `options_money.real_types`).
REAL = ["debit_vertical", "long_butterfly", "long_call", "long_put"]
ALLOWED = ("long_call", "long_put", "long_single", "debit_vertical", "long_butterfly")
STRONG = {"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"}


def proposal(i, structure="debit_vertical", roots=("SPY",)):
    return {"slug": f"idea-{i}", "mechanism": f"Mechanism number {i}: a distinct state change the move reverts within days.",
            "structure": structure, "roots": list(roots), "dte": [0, 5], "rejection": "no reversion", "sketch": "enter late"}


class TheSetting(unittest.TestCase):
    def test_unset_or_null_is_every_type_as_before(self):
        self.assertEqual(allowed_structures({}), STRUCTURES)
        self.assertEqual(allowed_structures({"architect": {}}), STRUCTURES)
        self.assertEqual(allowed_structures({"architect": {"structures": None}}), STRUCTURES)
        self.assertIsNone(structures_ignored({"architect": {"structures": None}}))
        self.assertIsNone(structures_ignored({}))

    def test_the_gateways_real_types_admit_long_single_too(self):
        # Every order a long_single sends is a long_call or a long_put: both listed, it is allowed without being named.
        self.assertEqual(allowed_structures({"architect": {"structures": REAL}}), ALLOWED)
        self.assertIsNone(structures_ignored({"architect": {"structures": REAL}}))
        one_side = allowed_structures({"architect": {"structures": ["debit_vertical", "long_call"]}})
        self.assertEqual(one_side, ("long_call", "debit_vertical"), "one side alone does not admit long_single")
        self.assertEqual(allowed_structures({"architect": {"structures": ["long_single", "debit_vertical"]}}),
                         ("long_single", "debit_vertical"), "named, it is allowed without its sides")

    def test_a_setting_it_cannot_use_is_every_type_and_the_event_says_what_was_ignored(self):
        for raw in ([], ["debit_vertcal"], "debit_vertical", {"debit_vertical": True}, 3, [None, 7]):
            self.assertEqual(allowed_structures({"architect": {"structures": raw}}), STRUCTURES, repr(raw))
            self.assertEqual(json.loads(structures_ignored({"architect": {"structures": raw}})), raw, repr(raw))
        partly = {"architect": {"structures": ["debit_vertical", "iron_condr"]}}
        self.assertEqual(allowed_structures(partly), ("debit_vertical",))
        self.assertEqual(json.loads(structures_ignored(partly)), ["iron_condr"], "an unknown entry alone")


class TheArchitect(RoundCase):
    def restrict(self, types=REAL):
        self.settings["architect"]["structures"] = list(types)

    def arch(self):
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    def test_the_gaps_are_of_the_allowed_types_only(self):
        before = self.arch()._gaps_by_root()
        self.assertIn("iron_condor", before["SPY"], "unset: every type, as before")
        self.restrict()
        gaps = self.arch()._gaps_by_root()
        for root, types in gaps.items():
            self.assertEqual(types, ["long_single", "debit_vertical", "long_butterfly"], root)
        self.store.add_family({**SPEC, "id": "vert-spy", "structure": "debit_vertical"}, origin="seed")
        self.assertEqual(self.arch()._gaps_by_root()["SPY"], ["long_single", "long_butterfly"])
        self.assertNotIn("iron_condor on QQQ", self.arch().gaps())
        self.assertIn("long_butterfly on QQQ", self.arch().gaps())

    def test_admit_refuses_a_type_outside_it_and_records_the_refusal(self):
        self.restrict()
        a = self.arch()
        born = a.admit([proposal(1), proposal(2, "iron_condor", ("QQQ",)), proposal(3, "long_single", ("IWM",)),
                        proposal(4, "credit_vertical", ("SPY", "QQQ")), proposal(5, "long_put", ("QQQ",))])
        self.assertEqual(born, ["idea-1", "idea-3", "idea-5"])
        self.assertEqual(a.not_allowed, [{"slug": "idea-2", "structure": "iron_condor", "roots": ["QQQ"]},
                                         {"slug": "idea-4", "structure": "credit_vertical", "roots": ["SPY", "QQQ"]}])
        self.assertIsNone(self.store.family("idea-2"))
        self.assertEqual([e["payload"]["structure"] for e in self.store.events_after(0) if e["kind"] == "swarm.born"],
                         ["debit_vertical", "long_single", "long_put"])

    def test_unset_it_admits_every_type_as_before(self):
        a = self.arch()
        born = a.admit([proposal(1, "iron_condor"), proposal(2, "calendar", ("QQQ",)), proposal(3, "credit_vertical", ("IWM",))])
        self.assertEqual(born, ["idea-1", "idea-2", "idea-3"])
        self.assertEqual(a.not_allowed, [])
        self.assertNotIn("STRUCTURES (architect.structures)", a.prompt())
        self.assertNotIn("NOT BORN FOR THEIR STRUCTURE", a.prompt())

    def test_the_request_names_the_allowed_types_and_shows_only_their_coverage(self):
        self.restrict()
        text = self.arch().prompt()
        self.assertIn("STRUCTURES (architect.structures): propose only these types, the ones real money can open on this "
                      "account now: long_call, long_put, long_single, debit_vertical, long_butterfly. A proposal of any other "
                      "type is not born.", text)
        self.assertLess(text.index("on these roots only"), text.index("STRUCTURES (architect.structures)"))
        label = "RESEARCH COVERAGE (effort, not profitability; validated means evaluated, not passed):\n"
        coverage = json.loads(text.split(label, 1)[1].split("\n\n", 1)[0])
        self.assertEqual(tuple(coverage), ALLOWED)
        gaps = json.loads(text.split("GAPS (uncovered structure types by root; [] means all covered):\n", 1)[1].split("\n\n", 1)[0])
        self.assertFalse({t for types in gaps.values() for t in types} - set(ALLOWED))
        self.assertEqual(len(self.arch().coverage()), len(STRUCTURES), "the coverage table itself keeps every row")

    def test_a_pass_refusal_is_named_in_the_next_request_and_a_clean_pass_clears_it(self):
        self.restrict()
        self.settings["architect"]["openai_model"] = None
        self.replies = [{"text": json.dumps({"families": [proposal(1), proposal(2, "iron_condor", ("QQQ",)),
                                                          proposal(3, "long_straddle", ("SPY", "IWM"))]})}]
        a = self.arch()
        out = a.run()
        self.assertEqual(out["born"], ["idea-1"])
        self.assertEqual(out["structure_not_allowed"], {"iron_condor": 1, "long_straddle": 1})
        self.assertEqual(out["structures"], list(ALLOWED))
        self.assertNotIn("structures_ignored", out)
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.architect"]
        self.assertEqual(event["structure_not_allowed"], {"iron_condor": 1, "long_straddle": 1})
        kept = self.store.get(STRUCTURE_REFUSALS_KEY)
        self.assertEqual([r["slug"] for r in kept["rows"]], ["idea-2", "idea-3"])
        text = a.prompt()
        self.assertIn("NOT BORN FOR THEIR STRUCTURE (proposals at ", text)
        self.assertIn("- idea-2 (iron_condor on QQQ): not born: iron_condor is not one of the allowed types", text)
        self.assertIn("- idea-3 (long_straddle on SPY,IWM): not born: long_straddle is not one of the allowed types", text)
        self.assertIn("architect.structures allows only long_call, long_put, long_single, debit_vertical, long_butterfly", text)
        # The next pass sends that request, and having refused nothing it clears the refusals.
        self.clock.advance(4000)
        self.replies = [{"text": json.dumps({"families": [proposal(4, "long_butterfly", ("IWM",))]})}]
        out = a.run()
        self.assertIn("- idea-2 (iron_condor on QQQ): not born", self.sail.bodies[-1]["input"][-1]["content"])
        self.assertEqual(out["born"], ["idea-4"])
        self.assertNotIn("structure_not_allowed", out)
        self.assertEqual(self.store.get(STRUCTURE_REFUSALS_KEY)["rows"], [])
        self.assertNotIn("NOT BORN FOR THEIR STRUCTURE", a.prompt())

    def test_unset_a_pass_writes_no_refusal_row(self):
        self.replies = [{"text": json.dumps({"families": [proposal(1, "iron_condor")]})}]
        out = self.arch().run()
        self.assertEqual(out["born"], ["idea-1"])
        self.assertFalse({"structures", "structure_not_allowed", "structures_ignored"} & set(out))
        self.assertIsNone(self.store.get(STRUCTURE_REFUSALS_KEY))

    def test_a_setting_it_cannot_use_is_reported_in_the_pass(self):
        self.settings["architect"]["structures"] = ["debit_vertcal"]
        self.replies = [{"text": json.dumps({"families": [proposal(1, "iron_condor")]})}]
        out = self.arch().run()
        self.assertEqual(out["born"], ["idea-1"], "an unusable list is ignored: every type, as before")
        self.assertEqual(json.loads(out["structures_ignored"]), ["debit_vertcal"])
        self.assertNotIn("structures", out)


class TheRetry(RouteCase):
    def test_a_truncated_answers_refusals_reach_its_retry(self):
        self.settings["architect"]["structures"] = list(REAL)
        text = json.dumps({"families": [proposal(1, "iron_condor"), proposal(2, roots=("QQQ",))]})
        cut = message(text[: text.rfind('"sketch"')], stop="max_tokens", cost="0.31")  # one complete family: the condor
        retry = self.answer([proposal(3, "iron_butterfly", ("IWM",)), proposal(4, "long_butterfly", ("IWM",))])
        opener = FakeOpener(cut, retry)
        a = self.architect(self.router(opener))
        out = a.run()
        self.assertEqual(out["born"], ["idea-4"])
        self.assertEqual(out["structure_not_allowed"], {"iron_condor": 1, "iron_butterfly": 1})
        sent = opener.calls[1][0].data.decode("utf-8")
        self.assertIn("idea-1 (iron_condor on SPY): not born: iron_condor is not one of the allowed types", sent,
                      "the retry's request names the cut answer's refusal")
        self.assertEqual([r["slug"] for r in self.store.get(STRUCTURE_REFUSALS_KEY)["rows"]], ["idea-1", "idea-3"])


class TheStrategist(StrategistCase):
    def packet(self):
        return Strategist(self.store, FakeRouter(), self.settings, clock=self.clock).packet()

    def test_unset_the_packet_is_as_before(self):
        packet = self.packet()
        self.assertNotIn("STRUCTURE TYPES THE ARCHITECT MAY PROPOSE", packet)
        self.assertIn("iron_condor on SPY", packet)

    def test_set_the_packet_names_the_allowed_types_and_its_gaps_and_coverage_are_theirs(self):
        self.settings["architect"]["structures"] = list(REAL)
        packet = self.packet()
        self.assertIn("STRUCTURE TYPES THE ARCHITECT MAY PROPOSE (a proposal of any other type is not born; the coverage "
                      "and the gaps above are of these types only): long_call, long_put, long_single, debit_vertical, "
                      "long_butterfly. When a direction names a structure, name one of these.", packet)
        gaps = json.loads(packet.split("GAPS (uncovered structure types by root):\n", 1)[1].split("\n\n", 1)[0])
        self.assertTrue(gaps)
        self.assertFalse({g.split(" on ")[0] for g in gaps} - set(ALLOWED))
        coverage = json.loads(packet.split("RESEARCH COVERAGE (effort, not profitability):\n", 1)[1].split("\n\n", 1)[0])
        self.assertEqual(tuple(coverage), ALLOWED)
        self.assertNotRegex(packet.split("STRUCTURE TYPES THE ARCHITECT MAY PROPOSE", 1)[1].split("\n\n", 1)[0],
                            r"(?i)money|account|dollar|capital|real", "no word the section's validator refuses")


class TheForks(RoundCase):
    def strong(self, fid, structure):
        self.family(fid, structure=structure, mechanism=f"{fid}: a mechanism with a reason to exist and a validation.")
        self.store.set_state(fid, validation_numbers=dict(STRONG))

    def test_a_family_of_a_type_outside_it_does_not_breed_and_is_not_retired(self):
        self.settings["architect"]["structures"] = list(REAL)
        self.strong("condor", "iron_condor")
        self.strong("vertical", "debit_vertical")
        self.store.set_state("condor", validation_numbers={**STRONG, "t": 4.0})  # the strongest: it would fork first
        self.settings["tournament"]["fork_top"] = 1
        t = Tournament(self.store, self.pool, self.settings)
        self.assertEqual(t.forks(self.store.families(alive=True)), ["vertical-on-qqq"], "the top fork slot goes to a real type")
        self.assertIsNone(t.fork(self.store.family("condor")), "nor does a direct fork breed it")
        self.assertIsNone(self.store.family("condor")["retired_at"], "it keeps researching")

    def test_unset_every_type_forks_as_before(self):
        self.strong("condor", "iron_condor")
        t = Tournament(self.store, self.pool, self.settings)
        self.assertEqual(t.forks(self.store.families(alive=True)), ["condor-on-qqq"])

    def test_the_tournament_reads_the_architects_own_rule(self):
        self.assertIs(arch_mod.allowed_structures, __import__("league.swarm.tournament", fromlist=["x"]).allowed_structures)


if __name__ == "__main__":
    unittest.main()
