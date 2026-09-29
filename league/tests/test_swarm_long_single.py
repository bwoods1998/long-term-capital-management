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
from league.swarm.store import (LONG_SINGLE, SINGLE_SIDES, STRUCTURES, priors_of, same_slice, slice_priors, structure_query,
                                 structure_text)
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
        self.assertIn("state the side rule in\nthe sketch and why its calls and puts balance (the drift screen charges whatever net "
                      "exposure it holds)", SYSTEM)
        self.assertNotIn("drift-neutral", SYSTEM, "only as neutral as its side rule (review of #425)")
        self.assertIn("never a long_call and long_put twin pair", SYSTEM)
        self.assertIn("a long_single that revises a call/put twin pair inherits both twins'", SYSTEM)

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


CALLS = "After a large overnight gap up the first hour keeps going; buy calls on the side of the gap."
PUTS = "After a large overnight gap down the first hour keeps going; buy puts on the side of the gap."


class TwinsAndLineages(RoundCase):
    """The review of #425: a long_single that merges a twin pair counts BOTH twins (trials, looks, validated versions); a
    new lineage on a singles' slice counts the newest dead lineage of each type there; and a one-sided twin is refused
    beside a living long_single or the other side of the same idea."""

    def arch(self):
        return Architect(self.store, self.router, self.settings, clock=self.clock)

    def twin(self, fid, structure, mechanism, *, trials, looks=0, retire=True):
        self.store.add_family(spec(fid, structure=structure, mechanism=mechanism), origin="architect")
        version = self.store.add_version(fid, f"# {fid}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n",
                                         {}, author="test")
        self.store.add_run(fid, version["n"], {"run_id": f"validation-{fid}", "status": "ok", "trials": 1,
                                               "summary": {"t_daily": 2.0, "days_traded": 40}},
                           window="validation", stress=1.0, purpose="validation")
        self.store.update_family(fid, trials=trials)
        for n in range(looks):
            self.store.add_look(fid, version["n"], f"{fid}-look-{n}", passed=False, p_value=None, detail={})
        if retire:
            self.clock.advance(60)
            self.store.retire(fid, "idle rule: untested")
        return version

    def dead_pair(self):
        # Review 2's probe: the call twin 40 trials and no looks, the put twin 30 trials and 3 looks; the call retired last.
        self.twin("aftershock-put", "long_put", PUTS, trials=30, looks=3)
        self.twin("aftershock-call", "long_call", CALLS, trials=40)
        self.assertEqual([f["id"] for f in self.store.families(alive=False)], ["aftershock-put", "aftershock-call"])

    def test_a_long_single_that_merges_a_dead_twin_pair_counts_both_twins(self):
        self.dead_pair()
        born = self.arch().admit([{"slug": "aftershock", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2],
                                   "mechanism": MECHANISM}])
        self.assertEqual(born, ["aftershock"])
        fam = self.store.family("aftershock")
        self.assertEqual(fam["parent"], "aftershock-call", "the newest dead twin is its parent")
        self.assertIn("aftershock-put", self.store._connected_lineages(fam["lineage"]), "and the other twin is joined")
        self.assertEqual(self.store.lineage_trials("aftershock"), 70, "40 + 30, never the one twin's 40")
        self.assertEqual(self.store.lineage_looks("aftershock"), 3, "the put twin's three looks: no fresh ration")
        self.assertEqual(self.store.lineage_validated("aftershock")[0], 2, "D2's N: both twins' validated versions")
        self.assertEqual((fam["inherited_trials"], fam["inherited_looks"]), (70, 3), "recorded at birth too")
        # The site's copies of the lineage walk read the link as the store does.
        [agent] = [a for a in sitefeed.site_inputs(self.root)["agents"] if a["id"] == "aftershock"]
        self.assertEqual(agent["record"]["trials"], 70)

    def test_naming_one_twin_as_parent_joins_the_other_too(self):
        self.dead_pair()
        born = self.arch().admit([{"slug": "aftershock-both", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2],
                                   "mechanism": "Overnight gaps continue into the open; pick the gap's side with one option.",
                                   "parent": "aftershock-put"}])
        self.assertEqual(born, ["aftershock-both"])
        self.assertEqual(self.store.family("aftershock-both")["parent"], "aftershock-put")
        self.assertEqual((self.store.lineage_trials("aftershock-both"), self.store.lineage_looks("aftershock-both")), (70, 3))

    def test_a_long_single_continues_a_living_twin_and_joins_the_other(self):
        self.twin("gap-call", "long_call", CALLS, trials=12, looks=1, retire=False)
        self.twin("gap-put", "long_put", PUTS, trials=8, looks=2, retire=False)
        born = self.arch().admit([{"slug": "gap-both", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2],
                                   "mechanism": MECHANISM}])
        self.assertEqual(born, ["gap-both"])
        fam = self.store.family("gap-both")
        self.assertEqual(fam["parent"], "gap-put", "the newest living twin's lineage continues")
        self.assertEqual((self.store.lineage_trials("gap-both"), self.store.lineage_looks("gap-both")), (20, 3))
        self.assertIsNone(fam["spec"].get("prior_lineage"))

    def test_a_one_sided_twin_is_refused_beside_a_living_long_single_or_the_other_side(self):
        arch = self.arch()
        self.assertEqual(arch.admit([{"slug": "gap-both", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2],
                                      "mechanism": MECHANISM}]), ["gap-both"])
        # Review 2's probe: both sides of the same idea on the same roots, beside the living long_single.
        refused = [{"slug": "aftershock-call", "structure": "long_call", "roots": ["SPY"], "dte": [0, 2], "mechanism": CALLS},
                   {"slug": "aftershock-put", "structure": "long_put", "roots": ["SPY"], "dte": [0, 2], "mechanism": PUTS}]
        self.assertEqual(arch.admit(refused), [])
        # On other roots, or another idea, a one-sided single is still admitted (the singles are first-class choices).
        self.assertEqual(arch.admit([{"slug": "qqq-call", "structure": "long_call", "roots": ["QQQ"], "dte": [0, 2],
                                      "mechanism": CALLS},
                                     {"slug": "pin-put", "structure": "long_put", "roots": ["SPY"], "dte": [0, 2],
                                      "mechanism": "Dealers pin the close near large open interest strikes; buy the put away from the pin."}]),
                         ["qqq-call", "pin-put"])

    def test_a_twin_pair_proposed_in_one_pass_births_one_side(self):
        born = self.arch().admit([
            {"slug": "gap-call", "structure": "long_call", "roots": ["SPY", "QQQ"], "dte": [0, 2], "mechanism": CALLS},
            {"slug": "gap-put", "structure": "long_put", "roots": ["QQQ", "SPY"], "dte": [0, 2], "mechanism": PUTS}])
        self.assertEqual(born, ["gap-call"], "the put is the living call's twin (roots in any order)")

    def test_a_new_one_sided_idea_after_a_dead_long_single_keeps_its_own_slices_history(self):
        # Review 2's probe: dead c1 (long_call), dead p1 (long_put), then a long_single s1 of another idea born and died.
        self.twin("c1", "long_call", CALLS, trials=10)
        self.twin("p1", "long_put", PUTS, trials=20)
        other = "Index rebalancing flows move the close; buy the side the rebalance pushes with one option."
        self.assertEqual(self.arch().admit([{"slug": "s1", "structure": "long_single", "roots": ["SPY"], "dte": [0, 2],
                                             "mechanism": other}]), ["s1"])
        s1 = self.store.family("s1")
        self.assertEqual((s1["spec"]["prior_lineage"], s1["spec"]["prior_lineages"]), ("p1", ["p1", "c1"]),
                         "a long_single counts the newest dead lineage of each single on its slice, newest first")
        self.assertEqual(self.store.lineage_trials("s1"), 30)
        self.store.update_family("s1", trials=5)
        self.clock.advance(60)
        self.store.retire("s1", "idle rule: untested")
        born = self.arch().admit([{"slug": "c2", "structure": "long_call", "roots": ["SPY"], "dte": [0, 2],
                                   "mechanism": "Earnings drift in the index heavyweights lifts the open; buy calls early."}])
        self.assertEqual(born, ["c2"])
        c2 = self.store.family("c2")
        self.assertEqual((c2["spec"]["prior_lineage"], c2["spec"]["prior_lineages"]), ("c1", ["c1", "s1"]), "own type first")
        self.assertEqual(self.store.lineage_trials("c2"), 35, "c1's 10 (missed before), s1's 5 and, through s1, p1's 20")
        self.assertEqual(c2["inherited_trials"], 35)
        self.assertEqual(self.store.lineage_looks("c2"), 0, "a prior lineage's looks never count")
        # The site's two copies of the chain walk agree with the store.
        [agent] = [a for a in sitefeed.site_inputs(self.root)["agents"] if a["id"] == "c2"]
        self.assertEqual(agent["record"]["trials"], 35)
        families = {f["id"]: f for f in self.store.families()}
        links = [(r["a"], r["b"]) for r in self.store._all("SELECT a,b FROM lineage_links")]
        self.assertEqual(progress._lines(families["c2"], families, links, prior=True), {"c2", "c1", "s1", "p1"})
        self.assertEqual(progress._lines(families["c2"], families, links, prior=False), {"c2"})

    def test_every_other_structure_keeps_its_one_prior_lineage(self):
        dead = [{"structure": "debit_vertical", "lineage": "v1"}, {"structure": "debit_vertical", "lineage": "v2"}]
        self.assertEqual(slice_priors(dead, "debit_vertical"), ["v2"], "the newest dead lineage, exactly as before")
        self.assertEqual(slice_priors([], "long_single"), [])
        self.twin("v1", "debit_vertical", MECHANISM + " Verticals.", trials=6)
        born = self.arch().admit([{"slug": "v2", "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 2],
                                   "mechanism": "Dealers pin the close near large open interest strikes; a vertical away from it."}])
        self.assertEqual(born, ["v2"])
        v2 = self.store.family("v2")
        self.assertEqual(v2["spec"]["prior_lineage"], "v1")
        self.assertNotIn("prior_lineages", v2["spec"], "one prior: the spec a store before #425 wrote")
        self.assertEqual(priors_of({"prior_lineage": "v1"}), ["v1"])
        self.assertEqual(priors_of({"prior_lineage": "a", "prior_lineages": ["a", "b"]}), ["a", "b"])
        self.assertEqual(priors_of(None), [])

    def test_link_lineages_joins_only_two_real_distinct_lineages(self):
        self.twin("c1", "long_call", CALLS, trials=1, retire=False)
        self.twin("p1", "long_put", PUTS, trials=2, retire=False)
        self.assertFalse(self.store.link_lineages("c1", "c1"))
        self.assertFalse(self.store.link_lineages("c1", "nobody"))
        self.assertTrue(self.store.link_lineages("p1", "c1"))
        self.assertFalse(self.store.link_lineages("c1", "p1"), "once")
        self.assertEqual(self.store.lineage_trials("c1"), 3)


class TheWords(RoundCase):
    def test_the_researcher_reviewer_and_diagnostician_are_told_what_its_orders_are(self):
        text = structure_text("long_single")
        for words in ("one long_call or one long_put", "never \"long_single\"", "side rule", "why its calls and puts balance",
                      "the drift screen charges whatever net exposure it holds"):
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
