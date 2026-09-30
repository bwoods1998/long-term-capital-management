"""Release B: research compute by expected information value, with structure and mechanism diversity
(league/swarm/allocation.py): the value and its posterior, the share with its pools and caps, the stride turns, the
concurrency, and the birth quota; and that none of it reaches the live path or the evaluator's fingerprint."""

from __future__ import annotations

import ast
import json
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
        self.assertIsNone(c["plan_usd_per_hour"], "the pace's limit is the plan")
        bad = A.cfg({"allocation": {"mode": "greedy", "family_cap": 5, "class_cap": "a", "scheduler": None, "cap_boost": 0,
                                    "plan_usd_per_hour": -3, "max_concurrency": True, "births": {"max_share": 2, "min_alive": -1},
                                    "real_structures": "debit_vertical", "floor_share": 0.8, "explore_share": 0.5}})
        self.assertEqual((bad["mode"], bad["family_cap"], bad["class_cap"], bad["scheduler"], bad["cap_boost"]),
                         ("value", 0.05, 0.30, "stride", 3.0))
        self.assertIsNone(bad["plan_usd_per_hour"])
        self.assertIsNone(bad["max_concurrency"])
        self.assertEqual((bad["births"]["max_share"], bad["births"]["min_alive"]), (0.4, None))
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
        wild = dict(looks())
        wild["broken"] = ("debit_vertical x etf", -1509.276)  # Sept 30: a near-constant daily series
        post = A.Posterior(wild)
        self.assertGreaterEqual(post.mean, -3.0)
        self.assertEqual(post.looks["broken"][1], -A.T_CLIP)
        self.assertTrue(post.summary()["fitted"])

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
        self.assertTrue(all(s >= 0.10 / n - 1e-12 for s in shares.values()))
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

    def test_a_capped_class_never_takes_a_family_below_its_floor(self):
        rows = [row(f"big{i}", cls="big", t=1.5) for i in range(5)] + [row(f"s{i}", cls=f"small{i}") for i in range(20)]
        shares, report = A.value_shares(rows, self.post, {"allocation": {"class_cap": 0.05, "family_cap": 1.0}})
        self.assertTrue(all(s >= 0.10 / 25 - 1e-12 for s in shares.values()))
        self.assertIn("big", report["capped_classes"])

    def test_the_caps_excess_never_flows_to_a_family_worth_nothing(self):
        rows = [row(f"big{i}", cls="big") for i in range(30)] + [row("spent", cls="small", looks_spent=True),
                                                                 row("alive", cls="small")]
        shares, _ = A.value_shares(rows, self.post, {})
        self.assertAlmostEqual(shares["spent"], 0.10 / 32, msg="the floor only")
        self.assertGreater(shares["alive"], shares["spent"] * 5)

    def test_the_exploration_share_goes_to_classes_not_head_counts(self):
        rows = [row(f"big{i}", cls="big") for i in range(40)] + [row("lone", cls="lone")]
        c = {"allocation": {"class_cap": 1.0, "family_cap": 1.0}}
        shares, report = A.value_shares(rows, A.Posterior({}), c)
        self.assertAlmostEqual(report["pools"]["explore"], 0.35)
        # Equal class values: the lone family takes half the exploration share, 40 families the other half.
        self.assertGreater(shares["lone"], 0.35 / 2)
        self.assertLess(shares["big0"], 0.35 / 2 / 40 + 0.55 / 41 + 0.10 / 41 + 1e-9)

    def test_edges(self):
        self.assertEqual(A.value_shares([], self.post, {}), ({}, {"mode": "value", "families": 0}))
        only_gate = [row("g1", gate=True), row("g2", gate=True)]
        shares, report = A.value_shares(only_gate, self.post, {})
        self.assertEqual(shares, {"g1": 0.5, "g2": 0.5})
        spent = [row("s1", looks_spent=True), row("s2", looks_spent=True, t=1.0)]
        shares, _ = A.value_shares(spent, self.post, {})
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertAlmostEqual(shares["s1"], shares["s2"], msg="no value anywhere: evenly")
        one, _ = A.value_shares([row("solo")], self.post, {})
        self.assertEqual(one, {"solo": 1.0}, "a cap relaxes when it cannot hold")
        validated_only = [row("v1", t=1.5), row("v2", t=-1.0)]
        shares, report = A.value_shares(validated_only, self.post, {})
        self.assertEqual(report["pools"]["explore"], 0.0, "no unvalidated family: the exploration share is the decision share's")
        self.assertGreater(shares["v1"], shares["v2"])


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

    def test_the_legacy_order(self):
        fams = [{"id": "a", "weight": 0.1}, {"id": "b", "weight": 0.8}, {"id": "c", "weight": 0.1}]
        self.assertEqual([f["id"] for f in A.legacy_order(fams, 3, last={})], ["b", "a", "c"])

    def test_useful(self):
        self.assertTrue(A.useful({"weight": None}, 10, {}), "a newborn has not been judged")
        self.assertTrue(A.useful({"weight": 0.05}, 10, {}))
        self.assertFalse(A.useful({"weight": 0.01}, 10, {}))


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
        fid = sched.take(idle_seconds=0)
        # Useful: at least half the average share (1/3): a and b are, c is not.
        self.assertEqual(sched.queued_useful, sum(1 for f in ("a", "b") if f != fid))
        sched.release(fid, {})
        legacy, _ = self.run_turns({"allocation": {"scheduler": "legacy"}})
        self.assertGreater(legacy["a"], legacy["b"], "legacy: the favourite first, by a minute's head start a unit of share")
        self.assertGreater(legacy["b"], legacy["c"])


# ------------------------------------------------------------------------------------------------------ the concurrency
class Concurrency(unittest.TestCase):
    def eff(self, allocation=None, researcher=None, **kw):
        settings = {"researcher": {"concurrency": 24, **(researcher or {})}, "allocation": allocation or {}}
        args = {"queued_useful": 0, "running": 24, "spent_usd_hour": 1.0, "pace_limit": 4.0, **kw}
        return A.effective_concurrency(settings, **args)

    def test_the_plans_level_by_default(self):
        self.assertEqual(self.eff()["workers"], 24)
        self.assertEqual(self.eff(queued_useful=30)["workers"], 24, "no ceiling set: never above the plan's level")

    def test_it_expands_while_useful_experiments_wait_and_spend_is_under_the_plan(self):
        out = self.eff({"max_concurrency": 48}, queued_useful=10)
        self.assertEqual((out["workers"], out["why"]), (34, "useful experiments queued: expanded"))
        self.assertEqual(self.eff({"max_concurrency": 48}, queued_useful=100)["workers"], 48)
        self.assertEqual(self.eff({"max_concurrency": 48}, queued_useful=10, spent_usd_hour=3.5)["workers"], 24,
                         "at 0.875 of the plan: no expansion")
        self.assertEqual(self.eff({"max_concurrency": 48}, queued_useful=0)["workers"], 24, "nothing useful waits")

    def test_it_contracts_to_the_spend_plan(self):
        out = self.eff({"plan_usd_per_hour": 2.0}, spent_usd_hour=4.0)
        self.assertEqual((out["workers"], out["why"]), (12, "over the spend plan: contracted"))
        self.assertEqual(self.eff({"plan_usd_per_hour": 2.0, "min_concurrency": 6}, spent_usd_hour=40.0)["workers"], 6)
        self.assertEqual(self.eff(spent_usd_hour=8.0)["workers"], 12, "no plan: the pace's limit is the plan")
        self.assertEqual(self.eff(pace_limit=None, spent_usd_hour=100.0)["workers"], 24, "neither: the plan's level")

    def test_bounds(self):
        self.assertEqual(A.concurrency_bounds({}), (48, 48, 4))
        self.assertEqual(A.concurrency_bounds({"researcher": {"concurrency": 2}, "allocation": {"max_concurrency": 64}}), (2, 64, 2))
        self.assertEqual(A.concurrency_bounds({"researcher": {"concurrency": 30}, "allocation": {"max_concurrency": 10}}), (30, 30, 4))


class SwarmConcurrency(LoopCase):
    def test_the_swarm_reads_its_concurrency_caches_it_and_reports_it(self):
        self.settings["researcher"]["concurrency"] = 4
        self.settings["allocation"] = {"max_concurrency": 8}
        sw = self.swarm()
        self.assertEqual(sw.concurrency_status()["workers"], 4, "nothing queued: the plan's level")
        sw.scheduler.queued_useful = 10
        self.assertEqual(sw.concurrency_status()["workers"], 4, "read at most every 10 s")
        sw._concurrency = None
        self.assertEqual(sw.concurrency_status()["workers"], 8, "useful experiments queued, spend under the plan")
        self.assertEqual(sw.status()["concurrency"]["workers"], 8)
        sw._grow_workers()
        self.assertEqual(sw.workers, [], "no threads before run() starts them")


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
        self.alive(30)
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
        self.assertEqual(len(born), 2, "40% of a pass of five")
        self.settings["allocation"] = {"births": {"max_share": 1.0}}
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertEqual(len(a.admit([proposal(i, "long_butterfly", ("QQQ",)) for i in range(10, 13)])), 3, "1.0: no cap")

    def test_the_population_guard_rests_the_days_rule(self):
        self.born("debit_vertical", 30)
        a = Architect(self.store, self.router, self.settings, clock=self.clock)  # nobody alive: under half of the start
        self.assertIn("the day's rule rests", a.prompt())
        born = a.admit([proposal(i) for i in range(6)])
        self.assertEqual(len(born), 4, "the pass's cap alone: 40% of its want of 12")

    def test_the_run_event_counts_the_refusals(self):
        self.born("debit_vertical", 30)
        self.alive(30)
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        a.router = type("R", (), {"ask": lambda self, **kw: {"json": {"families": [proposal(1), proposal(2), proposal(3)]},
                                                              "route": "sail", "cost_usd": 0.0}})()
        out = a.run()
        self.assertEqual(out["structure_capped"], {"vertical": 2})
        self.assertEqual(len(out["born"]), 1)


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
