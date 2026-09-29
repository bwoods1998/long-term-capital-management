"""`long_single` in the swarm (Sept 29, 2026): ONE family whose program buys calls or puts by its rule, in place of the
call/put twins the architect used to birth (each one-sided, each carrying the market's drift, the pair doubling births).
The store admits it and still refuses an unknown structure; the architect's prompt, GAPS and coverage describe it; its
lineage matching sees the singles it sends; the researcher's, the reviewer's and the diagnostician's words say what its
orders are; the site's progress, the bands and the publisher handle it. Every program and number here is invented."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from league import publish
from league.live import money as M
from league.swarm import bands, progress, sitefeed
from league.swarm.architect import SYSTEM, Architect
from league.swarm.gate import Gate
from league.swarm.researcher import Researcher
from league.swarm.seeds import BUILDS, BUILD_PARAMS, program_for
from league.swarm.store import (LONG_SINGLE, SINGLE_SIDES, STRUCTURES, same_slice, structure_query, structure_text)
from league.tests.test_swarm_progress import ProgressCase
from league.tests.test_swarm_rounds import RoundCase

MECHANISM = "After a large overnight gap the first hour keeps going; buy the side of the gap, calls up and puts down."
NO_PUT = ["debit_vertical", "long_butterfly", "long_call"]


def spec(fid, structure="long_single", roots=("SPY",), mechanism=MECHANISM):
    return {"id": fid, "mechanism": mechanism, "structure": structure, "roots": list(roots), "dte": [0, 2]}


class TheStore(RoundCase):
    def test_a_long_single_family_is_admitted_and_an_unknown_structure_is_still_refused(self):
        self.assertIn(LONG_SINGLE, STRUCTURES)
        self.assertEqual(SINGLE_SIDES, ("long_call", "long_put"))
        fam = self.store.add_family(spec("gap-side"), origin="architect")
        self.assertEqual(fam["structure"], "long_single")
        for bad in ("long_twin", "short_put", "", None, "LONG_SINGLE", "long_single "):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.store.add_family(spec(f"bad-{len(str(bad))}", structure=bad), origin="architect")

    def test_every_declared_structure_trades_types_the_site_and_the_money_table_know(self):
        # A declared structure is an order type, or `long_single`'s two singles: every type an order can carry is one the
        # site's schema (the publisher's STRUCTURE_TYPES) knows.
        for structure in STRUCTURES:
            self.assertTrue(set(M.order_types(structure)) <= set(publish.STRUCTURE_TYPES), structure)
        self.assertNotIn(LONG_SINGLE, publish.STRUCTURE_TYPES)

    def test_identical_code_joins_a_long_single_and_the_single_it_sends(self):
        # Relabeling a single-option program two-sided buys no new looks: identical code on the same roots links lineages.
        code = "# the same program\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
        self.store.add_family(spec("call-side", structure="long_call", mechanism=MECHANISM + " (calls)"), origin="architect")
        self.store.add_family(spec("two-sided"), origin="architect")
        self.store.add_family(spec("vertical", structure="debit_vertical", mechanism=MECHANISM + " (verticals)"), origin="architect")
        for fid in ("call-side", "two-sided", "vertical"):
            self.store.add_version(fid, code, {}, author="test")
        self.assertIn("call-side", self.store._connected_lineages("two-sided"))
        self.assertNotIn("vertical", self.store._connected_lineages("two-sided"), "another structure stays apart")
        self.assertTrue(same_slice("long_single", "long_put") and same_slice("long_call", "long_single"))
        self.assertFalse(same_slice("long_call", "long_put"), "the one-sided singles stay two slices, as before")
        self.assertFalse(same_slice("long_single", "debit_vertical"))


class TheArchitect(RoundCase):
    def arch(self):
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    def test_the_prompt_describes_it_and_asks_for_no_twins(self):
        self.assertIn("long_single", SYSTEM)
        self.assertIn("long_single is one program\nthat buys calls or puts by its rule", SYSTEM)
        self.assertIn("state the side rule in\nthe sketch and why it is drift-neutral", SYSTEM)
        self.assertIn("never a long_call and long_put twin pair", SYSTEM)

    def test_a_single_options_gap_is_long_single_and_never_a_one_sided_twin(self):
        arch = self.arch()
        gaps = arch._gaps_by_root()
        for root, types in gaps.items():
            self.assertIn("long_single", types, root)
            self.assertFalse(set(SINGLE_SIDES) & set(types), f"{root}: a one-sided single is never a gap")
        # A one-sided family does not cover the two-sided gap; a long_single family does, on its roots only.
        self.store.add_family(spec("call-side", structure="long_call", roots=("SPY", "QQQ")), origin="architect")
        self.assertIn("long_single", arch._gaps_by_root()["SPY"])
        self.store.add_family(spec("two-sided", roots=("SPY",), mechanism=MECHANISM + " Both sides."), origin="architect")
        gaps = arch._gaps_by_root()
        self.assertNotIn("long_single", gaps["SPY"])
        self.assertIn("long_single", gaps["QQQ"])
        self.assertIn("long_single on QQQ", arch.gaps())
        self.assertNotIn("long_call on IWM", arch.gaps())

    def test_coverage_counts_long_single_as_its_own_row(self):
        self.store.add_family(spec("two-sided"), origin="architect")
        self.store.update_family("two-sided", trials=9)
        self.store.add_family(spec("call-side", structure="long_call"), origin="architect")
        coverage = self.arch().coverage()
        self.assertEqual(len(coverage), len(STRUCTURES))
        self.assertEqual(coverage["long_single"], {"active_families": 1, "retired_families": 0, "trials": 9, "validated_families": 0})
        self.assertEqual(coverage["long_call"]["active_families"], 1)

    def test_a_long_single_proposal_is_born_and_an_unknown_structure_is_not(self):
        born = self.arch().admit([
            {"slug": "gap-side", "structure": "long_single", "roots": ["SPY", "QQQ"], "dte": [0, 2], "mechanism": MECHANISM,
             "sketch": "calls after a gap up, puts after a gap down: the side follows the gap's sign, so it holds no net drift"},
            {"slug": "gap-twin", "structure": "long_twin", "roots": ["SPY"], "dte": [0, 2], "mechanism": MECHANISM + " Twin."}])
        self.assertEqual(born, ["gap-side"])
        fam = self.store.family("gap-side")
        self.assertEqual((fam["structure"], fam["roots"], fam["band"]), ("long_single", ["SPY", "QQQ"], "gym"))
        [event] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.born"]
        self.assertEqual(event["structure"], "long_single")

    def test_the_same_idea_as_a_dead_twin_continues_its_lineage(self):
        # The call twin died on SPY; the same idea proposed two-sided on SPY inherits its lineage (trials and looks), and a
        # new idea on the slice counts its trials (prior lineage), exactly as a same-structure re-proposal would.
        self.store.add_family(spec("aftershock-call", structure="long_call"), origin="architect")
        self.store.update_family("aftershock-call", trials=40)
        self.store.retire("aftershock-call", "idle rule: untested")
        born = self.arch().admit([
            {"slug": "aftershock", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2], "mechanism": MECHANISM,
             "parent": "aftershock-call"},
            {"slug": "fresh-idea", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2],
             "mechanism": "Dealers pin the close near large open interest strikes; buy the side away from the pin late."}])
        self.assertEqual(born, ["aftershock", "fresh-idea"])
        child = self.store.family("aftershock")
        self.assertEqual((child["parent"], child["lineage"]), ("aftershock-call", "aftershock-call"))
        self.assertEqual(self.store.lineage_trials("aftershock"), 40)
        fresh = self.store.family("fresh-idea")
        self.assertIsNone(fresh["parent"])
        self.assertEqual(fresh["spec"].get("prior_lineage"), "aftershock-call")
        self.assertEqual(self.store.lineage_trials("fresh-idea"), 40)

    def test_its_graveyard_reading_includes_the_singles_it_sends(self):
        self.assertEqual(structure_query("long_single"), "long_single long_call long_put")
        self.assertEqual(structure_query("debit_vertical"), "debit_vertical", "every other family's query is unchanged")


class TheWords(RoundCase):
    def test_the_researcher_reviewer_and_diagnostician_are_told_what_its_orders_are(self):
        text = structure_text("long_single")
        for words in ("one long_call or one long_put", "never \"long_single\"", "side rule", "drift-neutral"):
            self.assertIn(words, text)
        self.assertEqual(structure_text("iron_condor"), "iron_condor", "no other family's prompt changes")
        fam = self.store.add_family(spec("two-sided"), origin="architect")
        me = Researcher(self.store, self.router, self.pool, self.settings, contract="THE CONTRACT", clock=self.clock)
        self.assertIn(f"Structure: {text}. Roots: SPY.", me.brief(fam))
        other = self.store.add_family(spec("vertical", structure="debit_vertical", mechanism=MECHANISM + " Vertical."),
                                      origin="architect")
        self.assertIn("Structure: debit_vertical. Roots: SPY.", me.brief(other))
        asked = []
        router = SimpleNamespace(ask=lambda **kw: asked.append(kw) or {"json": {"verdict": "pass", "reasons": []}},
                                 openai_room=lambda: 0.0)
        version = self.store.add_version("two-sided", "NEEDS = {}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="t")
        gate = Gate(self.store, self.pool, router, self.settings)
        self.assertEqual(gate.review(fam, version)["verdict"], "pass")
        gate.audit(fam, version)
        self.assertTrue(all(f"Structure {text}, roots SPY." in a["user"] for a in asked), [a["user"][:200] for a in asked])
        self.assertEqual(len(asked), 2)
        from league.swarm.diagnostician import Diagnostician

        doctor = Diagnostician(self.store, self.router, self.settings, pool=self.pool, contract="THE CONTRACT", clock=self.clock)
        self.store.update_family("two-sided", best_version=version["n"])
        packet = doctor.packet(self.store.family("two-sided"), {"passed": False, "met": 5, "total": 8, "validations": 1})
        self.assertIn(f"Structure {text}; roots SPY;", packet)

    def test_a_long_single_starter_picks_the_side_by_its_signal(self):
        self.assertIn("long_single", BUILDS)
        self.assertEqual(BUILD_PARAMS["long_single"], {"long_delta": 0.5})
        code, params = program_for({"id": "starter", "mechanism": MECHANISM, "structure": "long_single", "roots": ["SPY"],
                                    "dte": [0, 2], "signal": "orb_break", "rejection": "no follow-through"})
        self.assertIn('return "long_call"', code)
        self.assertIn('return "long_put"', code)
        self.assertNotIn('"long_single"', code.split("def legs_for", 1)[1], "its orders name their own types")
        from league.gym.runtime import load_program

        self.assertTrue(load_program(code, name="starter"), "the Gym's safety check admits it")


class TheSiteAndTheBands(ProgressCase):
    """The public progress (`progress._live`), the bands the live path reads, and the publisher."""

    def two_sided(self, band):
        version = self.family(band=band)
        self.store.update_family("synthetic-family", structure="long_single")
        return version

    def test_a_long_single_candidates_real_structure_check_needs_both_singles(self):
        self.two_sided("candidate")
        value = self.read()
        self.assertEqual(self.checks(value)["real_structure"], (1, 1))
        self.assertEqual(self.checks(value)["credit_equity"], (1, 1))
        self.assertIsNone(value["blocked"])
        import copy

        from league.constitution import CONSTITUTION

        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["real_types"] = NO_PUT
        self.live.table = M.Table.from_constitution(c)
        value = self.read()
        self.assertEqual(self.checks(value)["real_structure"], (0, 1))
        self.assertEqual(value["blocked"], "structure_ineligible")

    def test_the_bands_carry_it_to_the_live_paths_band_rule(self):
        self.two_sided("candidate")
        [row] = bands.read(self.root)
        self.assertEqual((row["family"], row["structure"], row["band"]), ("synthetic-family", "long_single", "candidate"))
        fwd = M.forward_stats([], 0.8)
        self.assertEqual(M.band_for(self.live.table, row, M.D("5481.65"), fwd)[0], "probe")

    def test_the_site_shows_no_type_for_the_declared_structure_and_accepts_the_checkpoint(self):
        self.two_sided("candidate")
        agents = progress.attach(sitefeed.site_inputs(self.root)["agents"], self.root, live=self.live,
                                 account=self.account(), now=self.now)
        [raw] = agents
        self.assertEqual(raw["structure"], "long_single", "the swarm's feed carries the declared structure")
        at = publish.site_instant(self.account()["as_of"])
        shown = publish.site_agent(raw, at)
        self.assertIsNone(shown["structure"], "none of the site's eleven types: null until the site's schema names it")
        self.assertEqual(shown["progress"]["target"], "probe")
        body = publish.build_checkpoint({"agents": agents, "account": self.account()}, at)
        self.assertEqual([a["structure"] for a in body["agents"]], [None])
        self.assertNotIn("long_single", json.dumps(body))
        from league.tests.test_positions_ledger import site_accepts

        self.assertEqual(site_accepts([body]), [True], "the site's own schema takes it")


if __name__ == "__main__":
    unittest.main()
