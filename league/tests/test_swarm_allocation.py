"""Release B: research compute by expected information value, with structure and mechanism diversity
(league/swarm/allocation.py): the value and its posterior, the share with its pools and caps, the stride turns, the
concurrency, and the birth quota; and that none of it reaches the live path or the evaluator's fingerprint."""

from __future__ import annotations

import ast
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

from league.swarm import allocation as A
from league.swarm import evidence as E
from league.swarm.architect import Architect
from league.swarm.loop import Scheduler
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock
from league.tests.test_claude import message
from league.tests.test_frontier import FakeOpener
from league.tests.test_swarm_graveyard_digest import RouteCase
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_rounds import RoundCase

REPO = Path(__file__).resolve().parents[2]


def row(fid, cls="debit_vertical x etf", t=None, trials=10, structure="debit_vertical", **kw):
    return {"id": fid, "cls": cls, "structure": structure, "t": t, "drift_failed": False, "trials": trials,
            "looks_spent": False, "hold_streak": 0, "gate": False, **kw}


def looks(n=40, mean=-0.8, spread=1.8, cls=("debit_vertical x etf", "long_put x etf"), seed=7):
    rng = random.Random(seed)
    return {f"old{i}": (cls[i % len(cls)], rng.gauss(mean, spread)) for i in range(n)}


# ------------------------------------------------------------------------------------------------------------ settings
class Settings(unittest.TestCase):
    def test_defaults_and_a_misread_value_is_its_default(self):
        c = A.cfg({})
        self.assertEqual((c["mode"], c["scheduler"], c["family_cap"], c["class_cap"], c["explore_share"], c["floor_share"]),
                         ("value", "stride", 0.05, 0.30, 0.35, 0.10))
        self.assertIsNone(c["max_concurrency"], "no expansion unless the operator sets a ceiling")
        self.assertIsNone(c["plan_usd_per_hour"], "no plan: neither expansion nor contraction")
        self.assertEqual(c["max_wait_seconds"], 0, "the floor share bounds every wait: no out-of-order turns by default")
        self.assertEqual((c["births"]["max_share"], c["births"]["min_alive"]), (0.6, None))
        bad = A.cfg({"allocation": {"mode": "greedy", "family_cap": 5, "class_cap": "a", "scheduler": None, "cap_boost": 0,
                                    "plan_usd_per_hour": -3, "max_concurrency": True, "births": {"max_share": 2, "min_alive": -1},
                                    "real_structures": "debit_vertical", "floor_share": 0.8, "explore_share": 0.5}})
        self.assertEqual((bad["mode"], bad["family_cap"], bad["class_cap"], bad["scheduler"], bad["cap_boost"]),
                         ("value", 0.05, 0.30, "stride", 3.0))
        self.assertIsNone(bad["plan_usd_per_hour"])
        self.assertIsNone(bad["max_concurrency"])
        self.assertEqual((bad["births"]["max_share"], bad["births"]["min_alive"]), (0.6, None))
        self.assertEqual(bad["real_structures"], A.DEFAULTS["real_structures"])
        self.assertEqual((bad["floor_share"], bad["explore_share"]), (0.10, 0.35), "pools that add past 1 are the defaults")
        self.assertEqual(A.cfg({"allocation": "on"})["mode"], "value")

    def test_the_real_structures_are_the_constitutions_real_types_and_long_single(self):
        from league.constitution import CONSTITUTION

        real = CONSTITUTION["options_money"]["real_types"]
        self.assertEqual(sorted(A.DEFAULTS["real_structures"]), sorted(set(real) | {"long_single"}),
                         "a grant that changes the real types changes this default in the same release")


# ----------------------------------------------------------------------------------------------------------- the value
class Posterior(unittest.TestCase):
    def test_few_looks_keep_the_defaults_and_a_degenerate_t_is_clipped(self):
        post = A.Posterior({"a": ("c", -1.0), "b": ("c", 0.5)})
        self.assertEqual((post.mean, post.between, post.within), (A.PRIOR_MEAN, A.PRIOR_BETWEEN, A.PRIOR_WITHIN))
        self.assertEqual(post.summary()["weight"], 0.0, "an evidence reset starts on the Sept 30 fit")
        wild = dict(looks())
        wild["broken"] = ("debit_vertical x etf", -1509.276)  # Sept 30: a near-constant daily series
        post = A.Posterior(wild)
        self.assertGreaterEqual(post.mean, -3.0)
        self.assertEqual(post.looks["broken"][1], -A.T_CLIP)
        self.assertAlmostEqual(post.summary()["weight"], 41 / (41 + A.PRIOR_LOOKS), places=4)

    def test_the_looks_move_the_estimates_from_the_prior_smoothly(self):
        """No jump at a count: each look moves the estimates a little, and many looks carry them to their own moments."""
        means = [A.Posterior(looks(n=k, mean=1.0, spread=0.3, seed=3)).mean for k in (3, 4, 10, 40, 400)]
        self.assertEqual(means, sorted(means), "more looks at +1: closer to +1")
        self.assertLess(means[0] - A.PRIOR_MEAN, 0.5, "three looks move the swarm's mean a little")
        self.assertGreater(means[-1], 0.85, "four hundred carry it (they weigh 400/420)")

    def test_near_the_line_is_worth_more_than_far_below_it_and_an_unexplored_class_draws_the_swarms_mean(self):
        post = A.Posterior(looks())
        p = {t: post.pass_probability(*post.family("debit_vertical x etf", t)) for t in (-2.0, 0.0, 1.0, 2.0)}
        self.assertLess(p[-2.0], p[0.0])
        self.assertLess(p[0.0], p[1.0])
        self.assertLess(p[1.0], p[2.0])
        mean, var = post.class_prior("long_butterfly x etf")
        self.assertAlmostEqual(mean, post.mean)
        self.assertGreater(var, post.class_prior("debit_vertical x etf")[1], "no look: the widest spread")

    def test_a_familys_own_look_is_left_out_of_its_class(self):
        data = looks(n=12)
        data["me"] = ("rare x etf", 3.0)
        post = A.Posterior(data)
        self.assertAlmostEqual(post.class_prior("rare x etf", leave_out="me")[0], post.mean)
        self.assertGreater(post.class_prior("rare x etf")[0], post.mean)


class Value(unittest.TestCase):
    def setUp(self):
        self.post = A.Posterior(looks())
        self.c = A.cfg({})

    def v(self, **kw):
        return A.value_of(row("f", **kw), self.post, self.c)

    def test_the_discounts(self):
        base = self.v()["value"]
        self.assertGreater(base, 0)
        self.assertEqual(self.v(looks_spent=True)["value"], 0.0, "the gate can never look again")
        self.assertEqual(self.v(gate=True)["value"], 0.0)
        self.assertAlmostEqual(self.v(drift_failed=True)["value"], base * A.DRIFT_FAILED)
        self.assertAlmostEqual(self.v(hold_streak=3)["value"], base * A.HOLDING)
        self.assertAlmostEqual(self.v(hold_streak=2)["value"], base)
        self.assertAlmostEqual(self.v(trials=90)["value"] / self.v(trials=10)["value"], (1 + 10 / 80) / (1 + 90 / 80))
        self.assertAlmostEqual(self.v(structure="credit_vertical")["value"], base * 0.5, msg="shadow-only: half")
        self.assertAlmostEqual(self.v(structure="long_single")["value"], base)

    def test_a_family_past_the_t_check_but_not_at_the_gate_is_as_undecided_as_one_on_the_line(self):
        newborn = self.v(trials=0)["value"]
        far_above = self.v(t=6.0, trials=0)
        self.assertGreater(far_above["p"], 0.5)
        self.assertAlmostEqual(far_above["value"], 0.25, msg="another check failed it: the most value there is")
        self.assertGreater(far_above["value"], newborn)

    def test_depth_reads_the_ideas_trials_not_only_the_familys_own(self):
        fam = {"id": "reborn", "structure": "debit_vertical", "trials": 0, "inherited_trials": 1443, "validations": 0,
               "state": {}, "band": "gym"}
        r = A.row_of(fam, cls="debit_vertical x etf", looks_spent=False)
        self.assertEqual((r["trials"], r["own_trials"]), (1443, 0), "a reborn mechanism is not a young one")
        young = A.row_of({**fam, "inherited_trials": 0}, cls="debit_vertical x etf", looks_spent=False)
        self.assertLess(A.value_of(r, self.post, self.c)["value"] * 10, A.value_of(young, self.post, self.c)["value"])

    def test_depth_reads_the_lineages_trials_now_not_the_snapshot_at_birth(self):
        """Verification of #448: a lineage linked after birth (a long_single's twins) grew its N while depth stayed put."""
        fam = {"id": "twin", "structure": "long_single", "trials": 12, "inherited_trials": 30, "validations": 0,
               "state": {}, "band": "gym"}
        self.assertEqual(A.row_of(fam, cls="long_single x etf", looks_spent=False, lineage_trials=900)["trials"], 900)
        self.assertEqual(A.row_of(fam, cls="long_single x etf", looks_spent=False, lineage_trials=20)["trials"], 42,
                         "never fewer than its own and inherited trials")
        self.assertEqual(A.row_of(fam, cls="long_single x etf", looks_spent=False)["trials"], 42, "unread: the snapshot")

    def test_a_validated_version_the_gate_is_done_with_is_no_evidence_of_the_next_look(self):
        """Verification of #448: a family refused at review or failed at its holdout look kept its validation t >= 2 and
        took the most value there is (q = min(p, 1/2)), so the swarm would fund the lineage the holdout just refuted."""
        fam = {"id": "refuted", "structure": "debit_vertical", "trials": 10, "inherited_trials": 0, "validations": 2,
               "state": {"validation_numbers": {"t": 2.7}, "gated_sha": "x", "gate_ready": False}, "band": "gym"}
        live = A.row_of(fam, cls="debit_vertical x etf", looks_spent=False)
        done = A.row_of(fam, cls="debit_vertical x etf", looks_spent=False, gate_done=True)
        self.assertEqual((live["t"], done["t"], done["gate_done"]), (2.7, None, True))
        unvalidated = self.v(trials=10)
        self.assertGreater(A.value_of(live, self.post, self.c)["value"], unvalidated["value"], "its t read as it stood")
        judged = A.value_of(done, self.post, self.c)
        self.assertAlmostEqual(judged["value"], unvalidated["value"] * A.GATE_DONE)
        self.assertEqual(judged["why"], "gate done with its validated version")
        # One verdict, one discount: the gate refuses a drift-failed version too.
        self.assertAlmostEqual(self.v(drift_failed=True, gate_done=True)["value"], unvalidated["value"] * A.DRIFT_FAILED)
        never = A.row_of({**fam, "validations": 0}, cls="debit_vertical x etf", looks_spent=False, gate_done=True)
        self.assertFalse(never["gate_done"], "no validation: nothing for the gate to be done with")


# ----------------------------------------------------------------------------------------------------------- the share
def sept30(n_new=60):
    """The House at 15:33Z Sept 30 in shape: three old families at t -0.73, 0.33 and -0.04 with many trials, one young
    validated family at 1.03, and a population of young debit verticals, most of one class."""
    rows = [row("neg", t=-0.73, trials=153), row("low", t=0.33, trials=140), row("flat", t=-0.04, trials=160),
            row("near", t=1.03, trials=16, cls="debit_vertical x etf+names")]
    rows += [row(f"new{i}", trials=5 + i % 30, cls="debit_vertical x etf" if i % 4 else "debit_vertical x names")
             for i in range(n_new)]
    rows += [row("fly", trials=4, cls="long_butterfly x etf", structure="long_butterfly")]
    return rows


class Share(unittest.TestCase):
    def setUp(self):
        self.post = A.Posterior(looks())

    def test_it_sums_to_one_every_family_has_its_floor_and_it_is_deterministic(self):
        shares, report = A.value_shares(sept30(), self.post, {})
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        n = len(shares)
        self.assertTrue(all(s >= 0.10 / n - 1e-9 for s in shares.values()))
        again, _ = A.value_shares(sept30(), self.post, {})
        self.assertEqual(shares, again, "no random draw")
        self.assertEqual(report["mode"], "value")
        json.dumps(report)  # the round's event carries it

    def test_the_sept_30_concentration_cannot_happen(self):
        shares, report = A.value_shares(sept30(), self.post, {})
        top3 = sum(sorted(shares.values())[-3:])
        self.assertLessEqual(top3, 3 * 0.05 + 1e-9, "Sept 30: 0.76 of the weight on three families, none at t >= 1")
        avg = 1.0 / len(shares)
        for fid in ("neg", "low", "flat"):
            self.assertLess(shares[fid], avg, f"{fid}: old, far below the line, heavily worked")
        self.assertGreater(shares["near"], shares["neg"] * 5)
        self.assertGreater(shares["near"], avg, "near the line: above the average")
        self.assertGreater(shares["fly"], avg, "an unexplored class's young family: above the average")

    def test_the_class_cap_and_the_family_cap(self):
        shares, report = A.value_shares(sept30(), self.post, {})
        by = {}
        for r in sept30():
            by[r["cls"]] = by.get(r["cls"], 0.0) + shares[r["id"]]
        self.assertTrue(all(s <= 0.05 + 1e-9 for s in shares.values()))
        self.assertIn("debit_vertical x etf", report["capped_classes"])
        # 45 of 65 families in one class: the cap cannot hold within the boost, so it gives way, and says so.
        self.assertLess(by["debit_vertical x etf"], 45 / 65, "still below its head count")
        self.assertTrue(report["class_cap_relaxed"])
        balanced = [row(f"a{i}", cls="a") for i in range(10)] + [row(f"b{i}", cls="b") for i in range(10)] + \
                   [row(f"c{i}", cls="c") for i in range(10)] + [row(f"d{i}", cls="d") for i in range(30)]
        shares, report = A.value_shares(balanced, self.post, {})
        d = sum(s for f, s in shares.items() if f.startswith("d"))
        self.assertAlmostEqual(d, 0.30, places=6, msg="half the families, at most 30% of the share")
        self.assertFalse(report["class_cap_relaxed"])
        self.assertEqual(report["family_cap_spill"], 0.0)
        self.assertEqual(report["largest_class"], {"class": "d", "share": 0.3, "head_share": 0.5})

    def test_a_capped_class_never_takes_a_family_below_its_floor(self):
        rows = [row(f"big{i}", cls="big", t=1.5) for i in range(5)] + [row(f"s{i}", cls=f"small{i}") for i in range(20)]
        shares, report = A.value_shares(rows, self.post, {"allocation": {"class_cap": 0.05, "family_cap": 1.0}})
        self.assertTrue(all(s >= 0.10 / 25 - 1e-9 for s in shares.values()))
        self.assertIn("big", report["capped_classes"])

    def test_a_caps_excess_goes_only_to_families_worth_what_the_average_share_buys(self):
        """Review of #448: the class cap pushed a below-average, shadow-only family in a small class to the family cap.
        Now the excess goes only where it buys at least the value-weighted mean value; what nobody can take relaxes the cap."""
        rows = [row(f"big{i}", cls="big", trials=5) for i in range(30)] + [
            row("weak", cls="small", structure="credit_vertical", trials=150), row("strong", cls="other", trials=0)]
        shares, report = A.value_shares(rows, self.post, {})
        n = len(rows)
        self.assertLess(shares["weak"] * n, 1.0, "worth less than the average unit of share: no boost from the cap")
        self.assertGreaterEqual(shares["strong"] * n, 1.99, "worth more: the cap moves attention to it (to the family cap)")
        self.assertGreater(report["class_cap_in_force"], 0.30, "the cap rose to the lowest level that holds")
        self.assertTrue(report["class_cap_relaxed"], "the rest could go nowhere worth it: the cap gave way")

    def test_the_family_caps_spill_is_not_read_as_the_class_caps(self):
        """Verification of #448: when the families worth the relief were the capped ones, the family cap's excess had
        nowhere to go at any class level, so the class cap "relaxed" to 1.0 and `class_cap_in_force` could never flag."""
        rows = [row(f"hot{i}", cls=f"hot{i}", t=1.8, trials=0) for i in range(3)] + \
               [row(f"cold{i}", cls=f"cold{i}", t=-2.5, trials=400) for i in range(22)]
        shares, report = A.value_shares(rows, self.post, {})
        self.assertFalse(report["class_cap_relaxed"], "every class is one family: the class cap never binds")
        self.assertGreater(report["family_cap_spill"], 0.1)
        self.assertEqual(report["class_cap_in_force"], 0.30)
        self.assertLessEqual(max(shares.values()), max(0.05, 2 / 25) + 1e-9)
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertEqual(report["largest_class"]["head_share"], 0.04)
        self.assertLessEqual(report["largest_class"]["share"], report["class_cap_in_force"])
        # The spill goes by value: never to a family worth nothing while any is worth something.
        rows[-1] = row("cold21", cls="cold21", looks_spent=True)
        shares, _ = A.value_shares(rows, self.post, {})
        self.assertAlmostEqual(shares["cold21"], 0.10 / 25, places=9)

    def test_the_caps_excess_never_flows_to_a_family_worth_nothing(self):
        rows = [row(f"big{i}", cls="big") for i in range(30)] + [row("spent", cls="small", looks_spent=True),
                                                                 row("alive", cls="small")]
        shares, _ = A.value_shares(rows, self.post, {})
        self.assertAlmostEqual(shares["spent"], 0.10 / 32, msg="the floor only")
        self.assertGreater(shares["alive"], shares["spent"] * 5)

    def test_the_exploration_share_buys_breadth_with_diminishing_returns_in_a_classs_size(self):
        rows = [row(f"big{i}", cls="big") for i in range(40)] + [row("lone", cls="lone")]
        c = {"allocation": {"class_cap": 1.0, "family_cap": 1.0}}
        shares, report = A.value_shares(rows, A.Posterior({}), c)
        self.assertAlmostEqual(report["pools"]["explore"], 0.35)
        # Equal values: a class's slice is its value mass over the root of its size, so 40 families take sqrt(40) of the
        # lone family's slice: more per family for the lone one, never half of all of it.
        k = math.sqrt(40)
        self.assertAlmostEqual(shares["lone"], 0.10 / 41 + 0.35 / (1 + k) + 0.55 / 41, places=9)
        self.assertAlmostEqual(shares["big0"], 0.10 / 41 + 0.35 * k / (1 + k) / 40 + 0.55 / 41, places=9)

    def test_a_shadow_only_class_takes_half_the_exploration_slice_of_an_equal_real_one(self):
        """Review of #448: the class split ignored the execution discount, so it cancelled inside the exploration share."""
        rows = [row(f"real{i}", cls="debit_vertical x names") for i in range(4)] + \
               [row(f"shadow{i}", cls="credit_vertical x names", structure="credit_vertical") for i in range(4)]
        c = {"allocation": {"class_cap": 1.0, "family_cap": 1.0, "floor_share": 0.0, "explore_share": 1.0}}
        shares, _ = A.value_shares(rows, A.Posterior({}), c)
        real = sum(v for f, v in shares.items() if f.startswith("real"))
        self.assertAlmostEqual(real, 2 / 3, places=9)
        full, _ = A.value_shares(rows, A.Posterior({}), {"allocation": {"shadow_value": 1.0}})
        self.assertAlmostEqual(full["shadow0"], full["real0"], places=9)
        halved, _ = A.value_shares(rows, A.Posterior({}), {})
        self.assertLess(halved["shadow0"], 0.75 * halved["real0"])

    def test_share_follows_value_and_evidence_is_not_penalised_for_being_evidence(self):
        """Review of #448: families with evidence took no part of the exploration share, so a validated family worth more
        than the unvalidated mean got less share than it. With no class cap binding, share rises with value."""
        rows = [row(f"new{i}", trials=10 + 3 * i) for i in range(30)] + [row("near", t=1.0, trials=40), row("low", t=0.3, trials=40)]
        post = A.Posterior(looks())
        shares, report = A.value_shares(rows, post, {"allocation": {"class_cap": 1.0}})
        c = A.cfg({})
        value = {r["id"]: A.value_of(r, post, c)["value"] for r in rows}
        unvalidated = [r["id"] for r in rows if r["t"] is None]
        mean_value = sum(value[f] for f in unvalidated) / len(unvalidated)
        mean_share = sum(shares[f] for f in unvalidated) / len(unvalidated)
        for fid in ("near", "low"):
            if value[fid] > mean_value:
                self.assertGreaterEqual(shares[fid], mean_share, fid)
        order = sorted(rows, key=lambda r: value[r["id"]])
        self.assertEqual([r["id"] for r in order], sorted((r["id"] for r in rows), key=lambda f: (shares[f], value[f])))

    def test_ties_at_a_cap_are_broken_so_a_top_band_holds_its_number(self):
        """Review of #448: families tied at the family cap let researcher.is_top's `>=` admit more than N."""
        rows = [row(f"hot{i}", cls=f"c{i}", trials=0) for i in range(20)] + [row(f"cold{i}", cls="cold", trials=400)
                                                                               for i in range(40)]
        shares, _ = A.value_shares(rows, self.post, {"allocation": {"family_cap": 0.02}})
        ranked = sorted(shares.values(), reverse=True)
        self.assertEqual(len(set(ranked)), len(ranked), "no two families share a weight")
        top = 12
        self.assertEqual(sum(1 for s in shares.values() if s >= ranked[top - 1]), top)
        self.assertAlmostEqual(sum(shares.values()), 1.0)

    def test_edges(self):
        self.assertEqual(A.value_shares([], self.post, {}), ({}, {"mode": "value", "families": 0, "useful_ids": []}))
        only_gate = [row("g1", gate=True), row("g2", gate=True)]
        shares, report = A.value_shares(only_gate, self.post, {})
        self.assertEqual(sorted(shares), ["g1", "g2"])
        self.assertAlmostEqual(shares["g1"], 0.5, places=9)
        self.assertAlmostEqual(shares["g2"], 0.5, places=9)
        spent = [row("s1", looks_spent=True), row("s2", looks_spent=True, t=1.0)]
        shares, _ = A.value_shares(spent, self.post, {})
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertAlmostEqual(shares["s1"], shares["s2"], msg="no value anywhere: evenly")
        one, _ = A.value_shares([row("solo")], self.post, {})
        self.assertEqual(one, {"solo": 1.0}, "a cap relaxes when it cannot hold")
        validated_only = [row("v1", t=1.5), row("v2", t=-1.0)]
        shares, report = A.value_shares(validated_only, self.post, {})
        self.assertAlmostEqual(report["pools"]["explore"], 0.35, msg="evidence is no bar to the exploration share")
        self.assertGreater(shares["v1"], shares["v2"])

    def test_the_useful_experiments(self):
        """THE CONCURRENCY's useful experiments: worth at least half a fresh family in an unexplored class."""
        rows = [row("fresh", trials=0), row("deep", trials=400), row("spent", looks_spent=True), row("gate", gate=True),
                row("shadow", structure="credit_vertical", trials=60), row("near", t=1.5, trials=60)]
        _, report = A.value_shares(rows, self.post, {})
        self.assertEqual(report["useful_ids"], ["fresh", "near"])
        self.assertEqual(report["useful"], 2)
        self.assertAlmostEqual(report["fresh_value"], A.fresh_value(self.post), places=5)


class TournamentAllocates(RoundCase):
    def validated(self, fid, t, mean, *, validations=3, trials=40):
        self.family(fid)
        self.store.update_family(fid, validations=validations, trials=trials)
        self.store.set_state(fid, validation_numbers={"mean": mean, "t": t})

    def test_the_value_mode_writes_the_weights_and_the_round_records_its_report(self):
        self.validated("near", 1.5, 0.02, trials=10)
        self.validated("far", -1.9, -0.03, trials=200)
        for i in range(8):
            self.family(f"new{i}")
        t = Tournament(self.store, None, self.settings, clock=self.clock)
        shares = t.allocate(self.store.families(alive=True))
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertGreater(shares["near"], shares["far"])
        weights = {f["id"]: f["weight"] for f in self.store.families(alive=True)}
        self.assertEqual(weights, shares)
        self.assertEqual(t.allocation["mode"], "value")
        self.assertIn("pools", t.allocation)
        self.assertNotIn("useful_ids", t.allocation, "the ids stay on the tournament, out of the round's event")
        self.assertIsInstance(t.useful, frozenset)
        self.assertEqual(len(t.useful), t.allocation["useful"])

    def test_the_most_advanced_families_lead_the_board_the_planners_read(self):
        """Review of #448: at the floor share, a gate-ready family sorted to the bottom of the board and fell out of the
        architect's and the strategist's first 60 rows."""
        from league.swarm.tournament import board_rank

        for i in range(70):
            self.family(f"seed{i:02d}")
        self.validated("ready", 2.6, 0.04)
        self.store.set_state("ready", gate_ready=True)
        self.family("cand")
        self.store.update_family("cand", band="candidate")
        t = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        shares = t.allocate(self.store.families(alive=True))
        self.assertLess(shares["ready"], 1.0 / 72, "the gate decides it next: the floor share")
        order = [f["id"] for f in sorted(self.store.families(alive=True), key=board_rank)]
        self.assertEqual(order[:2], ["cand", "ready"])
        row = t.run()
        self.assertEqual([r["family"] for r in row["board"][:2]], ["cand", "ready"])
        living = Architect(self.store, self.router, self.settings, clock=self.clock).prompt()
        self.assertIn('"family": "ready"', living.split("LIVING FAMILIES", 1)[1].split("THE GRAVEYARD", 1)[0])

    def test_a_family_the_gate_is_done_with_gets_no_more_than_an_unvalidated_one(self):
        """Verification of #448: refused at review, or failed at its holdout look, a family kept its validation t and sat
        at the family cap. Now the gate's verdict ends that t's say: it reads as an unvalidated family, at half."""
        from league.swarm.gate import run_sha

        for fid in ("refused", "failed", "open"):
            self.validated(fid, 2.7, 0.04, trials=10)
            n = self.store.family(fid)["best_version"]
            self.store.set_state(fid, validation_version=n, gate_ready=False)
        for i in range(40):
            self.family(f"new{i}")
            self.store.update_family(f"new{i}", trials=10)
        sha = run_sha(self.store.version("refused", self.store.family("refused")["best_version"]))
        self.store.set_state("refused", gated_sha=sha, gate_outcome={"sha": sha, "result": "refused"})
        version = self.store.version("failed", self.store.family("failed")["best_version"])
        self.store.add_look("failed", version["n"], run_sha(version), passed=False, p_value=0.4, detail={})
        fams = self.store.families(alive=True)
        self.assertTrue(A.gate_spent(self.store, next(f for f in fams if f["id"] == "failed")), "a look made is spent")
        self.assertFalse(A.gate_spent(self.store, next(f for f in fams if f["id"] == "open")))
        shares = Tournament(self.store, None, self.settings, clock=self.clock).allocate(fams)
        unvalidated = sum(shares[f"new{i}"] for i in range(40)) / 40
        for fid in ("refused", "failed"):
            self.assertLessEqual(shares[fid], unvalidated, fid)
        self.assertGreater(shares["open"], shares["refused"] * 2, "a t the gate has not judged still counts")

    def test_depth_reads_a_lineage_linked_after_birth(self):
        """Verification of #448: `link_lineages` (a long_single continuing one twin) grew a living family's N while its
        depth read the trials it inherited at birth."""
        self.family("old")
        self.store.update_family("old", trials=800)
        for fid in ("twin", "fresh"):
            self.family(fid)
            self.store.update_family(fid, trials=5)
        for i in range(10):
            self.family(f"pad{i}")
        self.assertTrue(self.store.link_lineages(self.store.family("old")["lineage"], self.store.family("twin")["lineage"]))
        self.assertEqual(self.store.family("twin")["inherited_trials"], 0)
        shares = Tournament(self.store, None, self.settings, clock=self.clock).allocate(self.store.families(alive=True))
        self.assertLess(shares["twin"] * 3, shares["fresh"], "its lineage's 805 trials, not its own 5")

    def test_the_planners_read_research_share_with_its_meaning(self):
        """Verification of #448: the planners' `share` changed meaning (how undecided a family is, not its evidence)
        and nothing told them."""
        from league.swarm.strategist import Strategist

        for i in range(4):
            self.family(f"f{i}")
        Tournament(self.store, self.pool, self.settings, clock=self.clock).run()
        architect = Architect(self.store, self.router, self.settings, clock=self.clock)
        prompt = architect.prompt()
        living = json.loads(prompt.split("(leaderboard):\n", 1)[1].split("\n\nTHE GRAVEYARD", 1)[0])
        self.assertTrue(living and all("research_share" in r and "share" not in r for r in living))
        self.assertIn(f"In LIVING FAMILIES, {A.SHARE_LEGEND}.", prompt)
        strategist = Strategist(self.store, self.router, self.settings, clock=self.clock, architect=architect)
        board = strategist._board(self.store.families())
        self.assertTrue(board and all("research_share" in r and "share" not in r for r in board))
        self.assertIn(f"THE BOARD (alive families; {A.SHARE_LEGEND}):", strategist.packet())

    def test_a_lineage_with_its_looks_spent_gets_the_floor(self):
        self.validated("spent", 1.5, 0.02, trials=10)
        self.validated("near", 1.5, 0.02, trials=10)
        for i in range(8):
            self.family(f"new{i}")
        lineage = self.store.family("spent")["lineage"]
        for k in range(E.LOOKS_PER_LINEAGE):
            self.store._exec("INSERT INTO looks(family, lineage, version, run_sha, at, passed, p_value, detail) VALUES(?,?,?,?,?,?,?,?)",
                             ("spent", lineage, 1, f"sha{k}", "2026-09-30T00:00:00Z", 0, 0.5, "{}"))
        shares = Tournament(self.store, None, self.settings, clock=self.clock).allocate(self.store.families(alive=True))
        self.assertAlmostEqual(shares["spent"], 0.10 / 10)
        self.assertGreater(shares["near"], shares["spent"] * 3)

    def test_a_failing_allocation_falls_back_to_the_bandit_and_says_why(self):
        self.validated("pos", 1.0, 0.02)
        self.family("new")
        t = Tournament(self.store, None, self.settings, rng=random.Random(5))
        real = A.allocate_from_store
        A.allocate_from_store = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("store unreadable"))
        try:
            shares = t.allocate(self.store.families(alive=True))
        finally:
            A.allocate_from_store = real
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertEqual(t.allocation["mode"], "bandit")
        self.assertIn("store unreadable", t.allocation["fallback"])

    def test_the_posterior_pools_only_the_running_evaluators_looks(self):
        from league.swarm.evaluator import KEY

        self.family("a")
        self.family("b")
        for fid, image, t in (("a", "img-old", 5.0), ("b", "img-new", -1.0)):
            self.store.add_run(fid, 1, {"run_id": f"v-{fid}", "status": "ok", "trials": 1,
                                        "summary": {"t_daily": t, "gym_image": image, "gym_bundle": "bundle"}},
                               window="validation", stress=1.0, purpose="validation")
        classes = A.classes_from_store(self.store)
        every = A.looks_from_store(self.store, since=0.0, class_of=classes.get)
        self.assertEqual(sorted(every), ["a", "b"], "no evaluator recorded: every look")
        self.store.put(KEY, {"image": "img-new", "bundle": "bundle", "execution": "x"})
        self.assertEqual(sorted(A.looks_from_store(self.store, since=0.0, class_of=classes.get)), ["b"])

    def test_the_bandit_mode_is_r11_5_unchanged(self):
        self.validated("pos", 1.0, 0.02)
        self.validated("neg", -1.0, -0.02)
        self.family("new")
        self.settings["allocation"] = {"mode": "bandit"}
        t = Tournament(self.store, None, self.settings, rng=random.Random(5))
        self.assertAlmostEqual(t.allocate(self.store.families(alive=True))["pos"], 0.15)
        self.assertEqual(t.allocation, {"mode": "bandit"})
        self.assertEqual(t.useful, frozenset(), "nothing expands on the bandit's weights")


# ----------------------------------------------------------------------------------------------------------- the turns
class Turns(unittest.TestCase):
    def serve(self, shares, turns=600, max_wait=0.0):
        """One worker, every family always ready: the order a stride scheduler serves them in."""
        st = A.StrideTurns()
        fams = [{"id": f, "weight": w} for f, w in shares.items()]
        got = {f: 0 for f in shares}
        last: dict[str, float] = {}
        for i in range(turns):
            f = st.order(fams, len(fams), now=float(i), last=last, max_wait=max_wait)[0]["id"]
            st.took(f, shares[f], len(fams))
            last[f] = float(i)
            got[f] += 1
        return got

    def test_under_contention_turns_follow_the_shares(self):
        got = self.serve({"a": 0.6, "b": 0.3, "c": 0.1})
        self.assertAlmostEqual(got["a"] / 600, 0.6, delta=0.02)
        self.assertAlmostEqual(got["b"] / 600, 0.3, delta=0.02)
        self.assertAlmostEqual(got["c"] / 600, 0.1, delta=0.02)

    def test_a_starving_family_goes_first_and_a_newcomer_banks_no_credit(self):
        got = self.serve({"a": 0.98, "b": 0.02}, turns=400, max_wait=100.0)
        self.assertGreaterEqual(got["b"], 4, "one turn at least every 100")
        st = A.StrideTurns()
        fams = [{"id": "old", "weight": 0.5}]
        for _ in range(50):
            st.took("old", 0.5, 2)
        newcomer = {"id": "new", "weight": 0.5}
        order = st.order([fams[0], newcomer], 2, now=0.0, last={}, max_wait=0)
        self.assertEqual(order[0]["id"], "new", "joins at the current pass: ahead of one who just ran")
        st.took("new", 0.5, 2)
        seq = []
        for _ in range(6):
            f = st.order([fams[0], newcomer], 2, now=0.0, last={}, max_wait=0)[0]
            st.took(f["id"], 0.5, 2)
            seq.append(f["id"])
        self.assertEqual(sorted(seq), ["new"] * 3 + ["old"] * 3, "then they alternate: no banked credit either way")
        st.forget(["new"])
        self.assertNotIn("old", st.passes)

    def test_an_out_of_order_turn_never_moves_the_virtual_time(self):
        """Review of #448: serving a starving family moved the virtual time to its far-ahead tag, resetting everyone."""
        st = A.StrideTurns()
        st.took("a", 0.5, 2)
        st.took("b", 0.5, 2)
        st.passes["slow"] = 100.0
        before = st.now_pass
        st.took("slow", 0.01, 2, out_of_order=True)
        self.assertEqual(st.now_pass, before)
        self.assertGreater(st.passes["slow"], 100.0, "it still pays its stride")
        self.assertTrue(A.StrideTurns.starving("slow", now=50.0, last={"slow": 0.0}, max_wait=30.0))
        self.assertFalse(A.StrideTurns.starving("slow", now=50.0, last={"slow": 0.0}, max_wait=0.0), "0: off")

    def test_the_floor_share_bounds_every_wait_without_the_starvation_rule(self):
        shares = {f"hi{i}": 0.09 for i in range(10)}
        shares.update({f"lo{i}": 0.1 / 100 for i in range(10)})
        got = self.serve(shares, turns=2000)
        self.assertTrue(all(got[f"lo{i}"] >= 2 for i in range(10)), got)

    def test_the_legacy_order(self):
        fams = [{"id": "a", "weight": 0.1}, {"id": "b", "weight": 0.8}, {"id": "c", "weight": 0.1}]
        self.assertEqual([f["id"] for f in A.legacy_order(fams, 3, last={})], ["b", "a", "c"])

    def test_queued_useful(self):
        ready = [{"id": "a"}, {"id": "b"}, {"id": "newborn"}]
        self.assertEqual(A.queued_useful(ready, {"a", "c"}), 1)
        self.assertEqual(A.queued_useful(ready, ()), 0, "nobody valued: nothing useful")


class SchedulerTurns(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        for fid, w in (("a", 0.6), ("b", 0.3), ("c", 0.1)):
            self.store.add_family({"id": fid, "mechanism": f"Mechanism {fid}: dealers rebalance late and the move reverts.",
                                   "structure": "debit_vertical", "roots": ["SPY"]}, origin="seed")
            self.store.update_family(fid, weight=w)

    def run_turns(self, settings, n=300):
        sched = Scheduler(self.store, clock=self.clock, settings=settings)
        got = {"a": 0, "b": 0, "c": 0}
        for _ in range(n):
            fid = sched.take(idle_seconds=0)
            got[fid] += 1
            sched.release(fid, {})
            self.clock.advance(1)
        return got, sched

    def test_the_scheduler_serves_by_share_and_counts_the_queue(self):
        got, sched = self.run_turns({})
        self.assertAlmostEqual(got["a"] / 300, 0.6, delta=0.03)
        self.assertAlmostEqual(got["c"] / 300, 0.1, delta=0.03)
        sched.useful_ids = lambda: frozenset({"a", "b"})  # the tournament's last allocation
        fid = sched.take(idle_seconds=0)
        self.assertEqual(sched.queued_useful, sum(1 for f in ("a", "b") if f != fid))
        sched.release(fid, {})
        legacy, _ = self.run_turns({"allocation": {"scheduler": "legacy"}})
        self.assertGreater(legacy["a"], legacy["b"], "legacy: the favourite first, by a minute's head start a unit of share")
        self.assertGreater(legacy["b"], legacy["c"])


# ------------------------------------------------------------------------------------------------------ the concurrency
class Concurrency(unittest.TestCase):
    def eff(self, allocation=None, researcher=None, **kw):
        settings = {"researcher": {"concurrency": 24, **(researcher or {})}, "allocation": allocation or {}}
        args = {"queued_useful": 0, "running": 24, "spent_usd_hour": 1.0, **kw}
        return A.effective_concurrency(settings, **args)

    def test_no_plan_is_the_plans_level_whatever_waits_or_is_spent(self):
        """Review of #448: with no explicit plan the controller read the Sail pace's limit and expanded on it."""
        self.assertEqual(self.eff()["workers"], 24)
        out = self.eff({"max_concurrency": 48}, queued_useful=30, spent_usd_hour=0.0)
        self.assertEqual((out["workers"], out["why"]), (24, "no allocation.plan_usd_per_hour: the plan's level"))
        self.assertEqual(self.eff({"max_concurrency": 48}, spent_usd_hour=100.0)["workers"], 24, "nor contracts")
        self.assertEqual(self.eff()["spend_kinds"], ["sail_model", "gym_box"])

    def test_it_expands_while_useful_experiments_wait_and_research_spend_is_under_the_plan(self):
        plan = {"max_concurrency": 48, "plan_usd_per_hour": 4.0}
        out = self.eff(plan, queued_useful=10)
        self.assertEqual((out["workers"], out["why"]), (34, "useful experiments queued: expanded"))
        self.assertEqual(self.eff(plan, queued_useful=100)["workers"], 48)
        self.assertEqual(self.eff(plan, queued_useful=10, spent_usd_hour=3.5)["workers"], 24, "at 0.875 of the plan: no expansion")
        self.assertEqual(self.eff(plan, queued_useful=0)["workers"], 24, "nothing useful waits")
        self.assertEqual(self.eff({"plan_usd_per_hour": 4.0}, queued_useful=10)["workers"], 24, "no ceiling: never above the level")

    def test_it_contracts_to_the_spend_plan(self):
        out = self.eff({"plan_usd_per_hour": 2.0}, spent_usd_hour=4.0)
        self.assertEqual((out["workers"], out["why"]), (12, "over the spend plan: contracted"))
        self.assertEqual(self.eff({"plan_usd_per_hour": 2.0, "min_concurrency": 6}, spent_usd_hour=40.0)["workers"], 6)

    def test_bounds(self):
        self.assertEqual(A.concurrency_bounds({}), (48, 48, 4))
        self.assertEqual(A.concurrency_bounds({"researcher": {"concurrency": 2}, "allocation": {"max_concurrency": 64}}), (2, 64, 2))
        self.assertEqual(A.concurrency_bounds({"researcher": {"concurrency": 30}, "allocation": {"max_concurrency": 10}}), (30, 30, 4))


class SwarmConcurrency(LoopCase):
    def test_the_swarm_reads_its_concurrency_caches_it_and_reports_it(self):
        self.settings["researcher"]["concurrency"] = 4
        self.settings["allocation"] = {"max_concurrency": 8, "plan_usd_per_hour": 5.0}
        sw = self.swarm()
        self.assertEqual(sw.concurrency_status()["workers"], 4, "nothing queued: the plan's level")
        sw.scheduler.queued_useful = 10
        self.assertEqual(sw.concurrency_status()["workers"], 4, "read at most every 10 s")
        sw._concurrency = None
        self.assertEqual(sw.concurrency_status()["workers"], 8, "useful experiments queued, research spend under the plan")
        self.assertEqual(sw.status()["concurrency"]["workers"], 8)
        sw.store.add_spend("gym_box", 6.0)  # the Gym's boxes count against the plan, not only Sail's models
        sw._concurrency = None
        self.assertEqual(sw.concurrency_status()["why"], "over the spend plan: contracted")
        sw._grow_workers()
        self.assertEqual(sw.workers, [], "no threads before run() starts them")

    def test_the_scheduler_reads_the_tournaments_useful_experiments(self):
        sw = self.swarm()
        sw.tournament.useful = frozenset({"x"})
        self.assertEqual(set(sw.scheduler.useful_ids()), {"x"})


# ---------------------------------------------------------------------------------------------------- the birth quota
def proposal(i, structure="debit_vertical", roots=("SPY",)):
    return {"slug": f"idea-{i}", "mechanism": f"Mechanism number {i}: a distinct state change the move reverts within days.",
            "structure": structure, "roots": list(roots), "dte": [0, 5], "rejection": "no reversion", "sketch": "enter late"}


class BirthQuota(RoundCase):
    def born(self, structure, n):
        for i in range(n):
            self.store.event("swarm.born", f"{structure}-{i}", {"structure": structure, "roots": ["SPY"], "origin": "architect"})

    def alive(self, n):
        for i in range(n):
            self.store.add_family({"id": f"pop-{i}", "mechanism": f"Population member {i}: some long mechanism text here.",
                                   "structure": "long_call" if i % 2 else "iron_condor", "roots": ["SPY" if i % 3 else "XSP"]},
                                  origin="seed")

    def test_the_buckets(self):
        self.assertEqual({A.bucket_of(s) for s in ("long_single", "long_call", "long_put")}, {"single"})
        self.assertEqual(A.bucket_of("debit_vertical"), A.bucket_of("credit_vertical"))
        self.assertEqual(A.bucket_of("long_butterfly"), "butterfly")
        self.assertEqual(A.bucket_of("something_new"), "something_new")
        from league.swarm.store import STRUCTURES
        self.assertTrue(all(s in A._BUCKET_OF for s in STRUCTURES), "every structure type has a family")

    def test_a_full_structure_family_is_refused_past_its_first_and_the_request_says_so(self):
        self.born("debit_vertical", 30)
        self.born("long_call", 2)
        self.alive(40)  # at least three quarters of the start (48): the quota holds
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        text = a.prompt()
        self.assertIn("BIRTH QUOTAS", text)
        self.assertIn("- vertical (debit_vertical, credit_vertical): 30 of 32 (94%), FULL", text)
        self.assertIn("- single (long_single, long_call, long_put): 2 of 32 (6%), open", text)
        born = a.admit([proposal(1), proposal(2), proposal(3, "long_single", ("QQQ",)), proposal(4, "long_butterfly", ("IWM",)),
                        proposal(5)])
        self.assertEqual(born, ["idea-1", "idea-3", "idea-4"], "one vertical a pass while the family is full")
        self.assertEqual(a.structure_capped, {"vertical": 2})

    def test_a_pass_bears_at_most_its_share_of_one_structure_family(self):
        self.alive(30)
        self.settings["population"]["start"] = 30  # at the start: the pass wants `max_new`
        self.settings["architect"]["max_new"] = 5
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertEqual(a.want(), 5)
        born = a.admit([proposal(i, "long_butterfly", ("IWM",)) for i in range(5)])
        self.assertEqual(len(born), 3, "60% of a pass of five")
        self.settings["allocation"] = {"births": {"max_share": 1.0}}
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertEqual(len(a.admit([proposal(i, "long_butterfly", ("QQQ",)) for i in range(10, 13)])), 3, "1.0: no cap")

    def test_the_population_guard_rests_the_whole_quota(self):
        """Review of #448: below the guard the pass's cap still held, so a one-structure architect thinned the population
        well below it (to about births over the retirement hazard)."""
        self.born("debit_vertical", 30)
        self.alive(35)  # under three quarters of the start (48)
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertIn("they rest in this pass (fewer than 36 families live)", a.prompt())
        born = a.admit([proposal(i) for i in range(6)])
        self.assertEqual(len(born), 6, "every well-formed proposal")
        self.assertEqual(a.structure_capped, {})

    def test_the_run_event_counts_the_refusals(self):
        self.born("debit_vertical", 30)
        self.alive(40)
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        a.router = type("R", (), {"ask": lambda self, **kw: {"json": {"families": [proposal(1), proposal(2), proposal(3)]},
                                                              "route": "sail", "cost_usd": 0.0}})()
        out = a.run()
        self.assertEqual(out["structure_capped"], {"vertical": 2})
        self.assertEqual(len(out["born"]), 1)
        self.assertIsNone(a.pass_quota, "the pass's quota ends with the pass")
        a.router = type("R", (), {"ask": lambda self, **kw: (_ for _ in ()).throw(RuntimeError("no route"))})()
        self.assertIn("no route", a.run()["error"])
        self.assertIsNone(a.pass_quota, "and with a pass that failed")


class QuotaAcrossTheRetry(RouteCase):
    """Review of #448: each admit built its own quota, so a truncated pass's retry got a second per-pass allowance."""

    def test_a_truncated_pass_and_its_retry_share_one_quota(self):
        self.settings["allocation"] = {"births": {"max_share": 0.05, "min_alive": 0}}  # one vertical a pass
        text = json.dumps({"families": [proposal(i, roots=(("SPY", "QQQ", "IWM")[i % 3],)) for i in range(2)]})
        cut = message(text[: text.rfind('"sketch"')], stop="max_tokens", cost="0.31")  # one complete family
        opener = FakeOpener(cut, self.answer([proposal(10 + i, roots=(("QQQ", "IWM")[i],)) for i in range(2)]))
        a = self.architect(self.router(opener))
        out = a.run()
        self.assertEqual(len(out["born"]), 1, "the retry's verticals meet the pass's full quota")
        self.assertEqual(out["structure_capped"], {"vertical": 2})
        self.assertEqual(out["truncated"]["retry"]["born"], 0)
        self.assertIsNone(a.pass_quota, "the pass's quota ends with the pass")


# ------------------------------------------------------------------------------------------------ the evidence boundary
class NeverOnTheLivePath(unittest.TestCase):
    LIVE = [REPO / "league" / "swarm" / n for n in ("store.py", "bands.py", "gate.py", "evaluator.py", "settings.py",
                                                     "researcher.py", "pool.py", "evidence.py", "diagnostics.py", "public.py",
                                                     "inputs.py", "claude_research.py")]

    def imports(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
        return names

    def test_no_module_the_live_path_loads_imports_the_allocator(self):
        for path in self.LIVE + sorted((REPO / "league" / "live").glob("*.py")):
            names = self.imports(path)
            self.assertFalse({"allocation", "league.swarm.allocation", ".allocation"} & names, path.name)
            self.assertNotIn("tournament", names, path.name)

    def test_the_evaluators_fingerprint_does_not_cover_the_allocator(self):
        from league.gym.driver import LEAGUE_FILES

        self.assertFalse(any("swarm" in str(f) for f in LEAGUE_FILES), LEAGUE_FILES)


if __name__ == "__main__":
    unittest.main()
