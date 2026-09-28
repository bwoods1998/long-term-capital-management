"""THE DRIFT SCREEN on the swarm's side (Sept 27): its settings and their swarm.json override, the run rows that keep the
figures, the tournament's eligibility, the gate's refusal, the researcher's lines and the re-run of a version whose Train
run predates the figures. Invented results only (league/tests/swarm_fakes.py)."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from league.swarm import diagnostics, evidence
from league.swarm import settings as S
from league.swarm.gate import Gate
from league.swarm.researcher import drift_settings, drift_verdict, idle_dead, screen_best, version_drift
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import drift_block, result
from league.tests.test_swarm_researcher import FakePool, ResearcherCase, calls_in
from league.tests.test_swarm_rounds import RoundCase
from league.tests.test_swarm_sweep import SweepCase, scored

FAILING = drift_block(t=0.4, alpha_usd=30.0, drift_usd=900.0)          # the profit is drift: alpha t 0.4
FEW_YEARS = drift_block(t=1.8, alpha_usd=-50.0, drift_usd=400.0)       # a strong pooled t, but alpha negative every year


def train_result(name: str = "p", *, drift: object = "default", t: float = 2.0, **kw) -> dict:
    """An invented Train result with the Gym's per-year block (eligible under the Train score, each year's daily t `t`) and
    a drift block: the fake's passing one by default, the one given, or none (None: a run from before the figures)."""
    r = result(name, **kw)
    r["by_year"] = {str(2022 + i): {"trades": 60, "days": 252, "days_traded": 30, "pnl": 100.0, "t_daily": t,
                                     "mean_return_on_max_loss_daily": 0.01, "quarters_positive": "4/4"} for i in range(3)}
    if drift is None:
        r.pop("drift", None)
    elif drift != "default":
        r["drift"] = copy.deepcopy(drift)
    return r


class Settings(unittest.TestCase):
    def test_the_defaults(self):
        cfg = S.DEFAULTS["tournament"]
        self.assertEqual((cfg["drift_screen"], cfg["drift_min_t"], cfg["drift_years_positive"]), (True, 1.0, None))
        self.assertEqual(drift_settings(S.DEFAULTS), (1.0, None))

    def test_swarm_json_overrides_them(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "swarm.json").write_text(json.dumps({"tournament": {"drift_min_t": 1.5, "drift_years_positive": 3}}))
            loaded = S.load(root, config={})
            self.assertEqual(drift_settings(loaded), (1.5, 3))
            self.assertTrue(loaded["tournament"]["require_robustness"], "the other tournament settings stay")
            (Path(root) / "swarm.json").write_text(json.dumps({"tournament": {"drift_screen": False}}))
            self.assertIsNone(drift_settings(S.load(root, config={})), "JSON false turns it off")

    def test_a_misread_setting_keeps_the_brake_on(self):
        for bad in ("no", 0, None, "false"):
            self.assertIsNotNone(drift_settings({"tournament": {"drift_screen": bad}}), bad)
        self.assertEqual(drift_settings({"tournament": {"drift_min_t": "high", "drift_years_positive": -1}}), (1.0, None))
        self.assertEqual(drift_settings({"tournament": {"drift_min_t": float("nan"), "drift_years_positive": 2.5}}), (1.0, None))
        self.assertEqual(drift_settings({"tournament": {"drift_years_positive": 2.0}}), (1.0, 2))
        self.assertEqual(drift_settings({"tournament": {"drift_min_t": -3.0}}), (1.0, None), "a negative t is no threshold")
        self.assertEqual(drift_settings({"tournament": {"drift_min_t": 0}}), (0.0, None))


class Screen(unittest.TestCase):
    def test_the_verdicts(self):
        self.assertTrue(evidence.drift_screen(evidence.drift_numbers(drift_block()))["passed"])
        low = evidence.drift_screen(evidence.drift_numbers(FAILING))
        self.assertEqual((low["known"], low["passed"]), (True, False))
        self.assertIn("below 1", low["why"])
        few = evidence.drift_screen(evidence.drift_numbers(FEW_YEARS))
        self.assertFalse(few["passed"])
        self.assertIn("positive in 0 of 3", few["why"])
        self.assertTrue(evidence.drift_screen(evidence.drift_numbers(FAILING), min_t=0.3)["passed"], "the threshold is a setting")
        legacy = evidence.drift_screen(None)
        self.assertEqual((legacy["known"], legacy["passed"]), (False, False))
        self.assertEqual(evidence.drift_screen(evidence.drift_numbers(drift_block(years=("2023", "2024"))))["need"], 1)

    def test_the_figures_drop_the_moments(self):
        numbers = evidence.drift_numbers(drift_block())
        self.assertNotIn("moments", json.dumps(numbers))
        self.assertEqual(evidence.drift_numbers(numbers), numbers, "idempotent: a row's figures read as figures")
        self.assertIsNone(evidence.drift_numbers({"years": {}}))


class Rows(unittest.TestCase):
    def test_a_train_rows_summary_keeps_the_figures_and_a_validation_row_has_none(self):
        with tempfile.TemporaryDirectory() as root:
            store = SwarmStore(root)
            self.addCleanup(store.close)
            fam = store.add_family({"id": "f", "mechanism": "An invented mechanism for the drift rows test.", "structure": "iron_condor",
                                    "roots": ["SPY"]}, origin="seed")
            v = store.add_version(fam["id"], "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="t")
            row = store.add_run("f", v["n"], train_result(), window="train", stress=1.0, purpose="train")
            self.assertEqual(store.run(row["run_id"])["summary"]["drift"], evidence.drift_numbers(drift_block()))
            other = store.add_run("f", v["n"], {**train_result(), "run_id": "v1"}, window="validation", stress=1.0, purpose="validation")
            self.assertNotIn("drift", store.run(other["run_id"])["summary"])
            store.prune_runs("f")
            self.assertEqual(version_drift(store, store.family("f"), v["n"]), evidence.drift_numbers(drift_block()))

    def test_only_a_normal_spread_run_carries_a_versions_figures(self):
        """The review of #398: `float(stress or 1.0)` read a mid run's stress 0.0 as 1.0, so zero-cost figures passed."""
        with tempfile.TemporaryDirectory() as root:
            store = SwarmStore(root)
            self.addCleanup(store.close)
            store.add_family({"id": "f", "mechanism": "An invented mechanism for the mid-row check.", "structure": "iron_condor",
                              "roots": ["SPY"]}, origin="seed")
            v = store.add_version("f", "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="t")
            row = store.add_run("f", v["n"], train_result("old", drift=None), window="train", stress=1.0, purpose="train")
            store.set_state("f", best_train_run=row["run_id"], best_train_version=v["n"])
            store.add_run("f", v["n"], train_result("mid", drift=drift_block(t=1.4)), window="train", stress=0.0, purpose="robustness")
            store.add_run("f", v["n"], train_result("hot", drift=drift_block(t=1.4)), window="train", stress=1.5, purpose="robustness")
            self.assertIsNone(version_drift(store, store.family("f"), v["n"]), "neither the mid nor the 1.5x run's figures")
            self.assertFalse(drift_verdict(store, store.family("f"), v["n"], S.DEFAULTS)["known"])
            store.add_run("f", v["n"], train_result("again", drift=FAILING), window="train", stress=1.0, purpose="drift")
            self.assertEqual(version_drift(store, store.family("f"), v["n"]), evidence.drift_numbers(FAILING),
                             "its Train run made again for the figures")

    def test_the_best_runs_figures_are_read_without_a_scan(self):
        with tempfile.TemporaryDirectory() as root:
            store = SwarmStore(root)
            self.addCleanup(store.close)
            store.add_family({"id": "f", "mechanism": "An invented mechanism for the lazy lookup.", "structure": "iron_condor",
                              "roots": ["SPY"]}, origin="seed")
            v = store.add_version("f", "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="t")
            row = store.add_run("f", v["n"], train_result(), window="train", stress=1.0, purpose="train")
            store.set_state("f", best_train_run=row["run_id"], best_train_version=v["n"])
            with patch.object(SwarmStore, "version_runs", side_effect=AssertionError("scanned")):
                self.assertEqual(version_drift(store, store.family("f"), v["n"]), evidence.drift_numbers(drift_block()))
            self.assertEqual(len(store.version_runs("f", v["n"], window="train", stress=1.0)), 1)


class Tournaments(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["tournament"]["drift_screen"] = True

    def with_train(self, fid: str, drift: object = "default") -> None:
        self.family(fid)
        self.store.add_run(fid, 1, train_result(fid, drift=drift), window="train", stress=1.0, purpose="train")

    def test_only_a_version_that_passes_is_validated(self):
        self.with_train("pass")
        self.with_train("drift", FAILING)
        self.with_train("years", FEW_YEARS)
        self.with_train("legacy", None)
        self.family("norun")
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual([j.family for j in self.pool.jobs], ["pass"])
        self.assertEqual(sorted(out["failed_drift"]), ["drift", "years"])
        self.assertEqual(sorted(out["waiting_drift"]), ["legacy", "norun"], "no figures yet: it waits, it is not refused")
        self.assertTrue(out["judged"]["pass"]["passed"])

    def test_a_version_at_the_screen_is_validated_when_it_is_off(self):
        self.with_train("drift", FAILING)
        self.settings["tournament"]["drift_screen"] = False
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual((out["queued"], out["failed_drift"]), (1, []))

    def test_a_failing_best_is_demoted_and_the_next_candidate_that_passes_is_validated(self):
        """The review of #398: a drift-failing best was a zombie (never validated, never replaced). It is marked, demoted like
        a loss at 1.5x, and the next candidate stands in its place in the same round."""
        self.family("z")
        v2 = self.store.add_version("z", "# z two\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {},
                                    author="t")
        r1 = self.store.add_run("z", 1, train_result("z1", drift=FAILING), window="train", stress=1.0, purpose="train")
        r2 = self.store.add_run("z", v2["n"], train_result("z2"), window="train", stress=1.0, purpose="train")
        self.store.update_family("z", best_train=3.0)
        self.store.set_state("z", best_train_version=1, best_train_run=r1["run_id"],
                             train_candidates=[[3.0, 1, r1["run_id"]], [2.0, v2["n"], r2["run_id"]]])
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual(out["failed_drift"], ["z"])
        self.assertEqual([(j.family, j.version) for j in self.pool.jobs], [("z", v2["n"])], "the next candidate, validated")
        fam = self.store.family("z")
        self.assertEqual((fam["best_version"], fam["state"]["best_train_version"], fam["best_train"]), (None, v2["n"], 2.0))
        self.assertIn("1", fam["state"]["drift_failed"])
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIn("fails the drift screen", fam["state"]["robust_why"]["1"])
        self.assertEqual([e["payload"]["action"] for e in self.store.events_after(0) if e["kind"] == "swarm.robustness"], ["demoted"])

    def test_a_family_whose_every_candidate_fails_counts_as_idle(self):
        self.with_train("z", FAILING)
        self.store.update_family("z", best_train=2.0, since_val_trials=200, trials=200)
        self.store.set_state("z", best_train_version=1, train_candidates=[[2.0, 1, "r"]])
        self.assertIsNone(idle_dead(self.store.family("z"), self.settings), "a positive best is not idle")
        screen_best(self.store, "z", self.settings)
        fam = self.store.family("z")
        self.assertIsNone(fam["best_train"])
        self.assertIn("no eligible Train version", idle_dead(fam, self.settings))

    def test_a_validated_version_that_fails_earns_no_fork_and_no_share_by_its_validation(self):
        for fid in ("a", "b"):
            self.family(fid)
            self.store.set_state(fid, validation_version=1, validation_numbers={"mean": 0.05, "t": 3.0, "sharpe_daily": 0.2,
                                                                                  "quarters": "4/4"})
            self.store.update_family(fid, validations=4)
        self.store.set_state("a", drift_failed={"1": "its drift-adjusted alpha has t 0.4 over Train, below 1"})
        t = Tournament(self.store, self.pool, self.settings)
        born = t.forks(self.store.families(alive=True))
        self.assertEqual([self.store.family(c)["parent"] for c in born], ["b"], "only the family whose validation stands forks")
        seen = []
        real = evidence.thompson
        with patch("league.swarm.tournament.evidence.thompson", side_effect=lambda rows, **kw: seen.extend(rows) or real(rows, **kw)):
            t.allocate([self.store.family("a"), self.store.family("b")])
        rows = {r["id"]: r for r in seen}
        self.assertEqual((rows["a"]["mean"], rows["a"]["t"]), (None, None), "counted as unvalidated")
        self.assertEqual(rows["b"]["t"], 3.0)

    def test_the_screen_reads_the_submitted_best_and_a_rerun_of_it(self):
        self.with_train("a", None)  # version 1's only Train run predates the figures
        t = Tournament(self.store, self.pool, self.settings)
        self.assertEqual(t.validate(self.store.families(alive=True))["waiting_drift"], ["a"])
        self.store.set_state("a", robustness={"1": {"drift": {"status": "ok", **evidence.drift_numbers(drift_block())}}})
        self.assertEqual(t.validate(self.store.families(alive=True))["queued"], 1, "its run made again carries passing figures")


class Gates(RoundCase):
    def ready(self, drift: object) -> None:
        self.family("a")
        self.store.add_run("a", 1, train_result("a", drift=drift), window="train", stress=1.0, purpose="train")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))  # the screen is off here
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        self.settings["tournament"]["drift_screen"] = True

    def test_the_gate_refuses_a_look_at_a_version_that_fails_and_pays_no_review(self):
        self.ready(FAILING)
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["refused"], ["a"])
        self.assertEqual(self.store.refusals("a")[0]["stage"], "drift screen")
        self.assertIn("drift", self.store.refusals("a")[0]["reason"])
        fam = self.store.family("a")
        self.assertTrue(fam["state"]["gate"].startswith("fail (the drift screen:"))
        self.assertEqual(fam["state"]["gate_outcome"]["result"], "refused")
        self.assertFalse(fam["state"]["gate_ready"])
        self.assertEqual((self.sail.bodies, self.asked, self.store.looks()), ([], [], []), "no review, no audit, no look")
        self.assertEqual([j for j in self.pool.jobs if j.window == "holdout"], [])
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.store.refusals("a")), 1, "refused once")

    def test_a_version_whose_figures_are_owed_waits_without_a_refusal(self):
        self.ready(None)
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual((out["waiting"], out["refused"], self.store.refusals("a")), (["a"], [], []))
        self.assertEqual(self.sail.bodies, [])

    def test_a_version_that_passes_goes_on_to_its_review(self):
        self.ready("default")
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}])


class QueueingPool(FakePool):
    """`run` answers at once (the researcher's own runs); `submit` holds robustness runs until a test lands them."""

    def __init__(self, answer):
        super().__init__(answer)
        self.queued: list = []

    def submit(self, job):
        self.queued.append(job)
        return job


class Researchers(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.drift: object = None  # the researcher's runs come back from before the figures
        self.pool = QueueingPool(lambda job: train_result(job.name, roots=job.roots, drift=self.drift))

    def test_a_best_from_before_the_figures_is_run_again_and_its_figures_reach_the_status(self):
        researcher = self.researcher()
        researcher.cycle(self.fam["id"])
        fid = self.fam["id"]
        jobs = [(j.version, j.window, j.stress, j.purpose) for j in self.pool.queued]
        self.assertEqual(jobs, [(1, "train", 1.5, "robustness"), (1, "train", 0.0, "robustness"), (1, "train", 1.0, "robustness")])
        fam = self.store.family(fid)
        self.assertIn("predates the drift figures", researcher.status(fam))
        self.assertFalse(drift_verdict(self.store, fam, 1, self.settings)["known"])
        again = self.pool.queued[2]
        trials = fam["trials"]
        again.late(train_result("again", drift=FAILING))
        fam = self.store.family(fid)
        self.assertEqual(fam["trials"], trials + 1, "the run made again is a trial")
        self.assertEqual(fam["state"]["robustness"]["1"]["drift"]["status"], "ok")
        verdict = drift_verdict(self.store, fam, 1, self.settings)
        self.assertEqual((verdict["known"], verdict["passed"]), (True, False))
        self.assertEqual((fam["best_version"], fam["state"]["best_train_version"], fam["best_train"]), (None, None, None),
                         "its figures failed: demoted, and it had no other candidate")
        self.assertIn("1", fam["state"]["drift_failed"])
        status = researcher.status(fam)
        self.assertIn("version 1 fails the drift screen", status)
        self.steps = [{"text": "ok"}]
        before = len(self.pool.queued)
        self.researcher().cycle(fid)  # a new process: the demoted version needs no robustness run at all
        self.assertEqual(self.pool.queued[before:], [])

    def test_a_drift_run_that_fails_three_times_demotes_its_version(self):
        """The review of #398: a version whose figures could never be made sat in front of the family for good."""
        researcher = self.researcher()
        researcher.cycle(self.fam["id"])  # version 1, from before the figures; its drift run queued
        fid = self.fam["id"]
        v2 = self.store.add_version(fid, self.code, {"vrp_min": 1.45}, author="t")
        r2 = self.store.add_run(fid, v2["n"], train_result("v2"), window="train", stress=1.0, purpose="train")
        state = self.store.family(fid)["state"]
        self.store.set_state(fid, train_candidates=list(state["train_candidates"]) + [[1.0, v2["n"], r2["run_id"]]])
        for _ in range(3):
            researcher.robust_landed(fid, 1, "drift", None, {"status": "failed", "reason": "the Gym failed the unit"})
        fam = self.store.family(fid)
        self.assertEqual(fam["state"]["robust_failed"], [1])
        self.assertIn("drift figures failed 3 times", fam["state"]["robust_why"]["1"])
        self.assertEqual(fam["state"]["best_train_version"], v2["n"], "the next candidate takes its place")

    def test_a_run_whose_figures_fail_never_becomes_the_best_and_submit_says_why(self):
        self.drift = "default"
        self.researcher().cycle(self.fam["id"])  # the starter: passes, version 1 the best at score 2.0
        fid = self.fam["id"]
        self.drift = FAILING
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "ok"}]
        self.pool.answer = lambda job: train_result(job.name, roots=job.roots, drift=self.drift, t=3.0)
        self.researcher().cycle(fid)
        view = json.loads(calls_in(self.sail.bodies[-1])[-1]["output"])
        self.assertFalse(view["train_score"]["eligible"])
        self.assertIn("fails the drift screen", view["train_score"]["why_not_eligible"])
        self.assertNotIn("new_best_train_score", view, "its score of 3.0 beat the best's 2.0, but not the screen")
        fam = self.store.family(fid)
        self.assertEqual((fam["state"]["best_train_version"], fam["best_train"]), (1, 2.0))
        self.assertIn("2", fam["state"]["drift_failed"])
        refused = self.researcher()._local_tool(fam, "submit", {"run_id": view["run_id"]}, {})
        self.assertIn("fails the drift screen", refused["error"])
        ok = self.researcher()._local_tool(fam, "submit", {"run_id": fam["state"]["best_train_run"]}, {})
        self.assertTrue(ok["ok"])
        self.assertTrue(ok["drift"].startswith("it passes the drift screen: drift-adjusted alpha $450 (t 2.00)"), ok["drift"])

    def test_a_best_with_figures_needs_no_run_again_and_its_view_shows_the_lines(self):
        self.drift = "default"
        self.researcher().cycle(self.fam["id"])
        self.assertEqual([j.stress for j in self.pool.queued], [1.5, 0.0])
        status = self.researcher().status(self.store.family(self.fam["id"]))
        self.assertIn("passes", status)
        view = diagnostics.train_view(train_result(), screen=drift_settings(self.settings))
        self.assertEqual(set(view["drift"]), {"2022", "2023", "2024", "train", "screen", "note"})
        self.assertEqual(view["drift"]["2022"], "drift-adjusted alpha $150 (t 2.00), drift $20, beta $2 per 1% move, held 100 of 250 days")
        self.assertTrue(view["drift"]["screen"].startswith("passes"))
        failing = diagnostics.train_view(train_result(drift=FAILING), screen=(1.0, None))
        self.assertTrue(failing["drift"]["screen"].startswith("fails: its drift-adjusted alpha has t 0.4"))
        self.assertNotIn("drift", diagnostics.train_view(train_result(drift=None)))
        self.assertIn("drift", diagnostics.section(train_result(), "drift"))
        self.assertIn("error", diagnostics.section(train_result(drift=None), "drift"))

    def test_the_drift_lines_never_cost_the_researcher_a_table(self):
        """The diagnostic's size cap drops the long tables first: the drift lines sit outside it."""
        big = train_result()
        big["breakdown"] = {name: {f"{name}-{i}": {"n": 10, "pnl": 1.0, "win_rate": 0.5, "pnl_per_max_loss": 0.01} for i in range(60)}
                            for name in diagnostics.BREAKDOWNS}
        without = diagnostics.train_view({**big, "drift": None})
        with_drift = diagnostics.train_view(big, screen=(1.0, None))
        self.assertLess(len(without["by"]), len(diagnostics.BREAKDOWNS), "the cap dropped tables")
        self.assertEqual(set(with_drift["by"]), set(without["by"]))
        self.assertIn("drift", with_drift)

    def test_the_prompt_says_drift_is_not_an_edge(self):
        from league.swarm.researcher import ROLE, TOOLS

        self.assertIn("DRIFT IS NOT AN EDGE", ROLE)
        self.assertIn("drift", next(t for t in TOOLS if t["name"] == "read_run")["parameters"]["properties"]["section"]["description"])



class Sweeps(SweepCase):
    def test_a_sweep_row_whose_figures_fail_is_not_counted(self):
        """The sweep's peak (vrp_min 1.4, the highest Train score) is drift: it never becomes the best or heads the table."""
        def answer(job):
            r = scored(job)
            if (job.params or {}).get("vrp_min") == 1.4:
                r["drift"] = copy.deepcopy(FAILING)
            return r

        self.pool.answer = answer
        self.first()
        view, out = self.sweep([{"vrp_min": 1.4}, {"vrp_min": 1.35}])
        rows = {r["params"].get("vrp_min"): r for r in view["table"]}
        self.assertFalse(rows[1.4]["eligible"])
        self.assertIn("fails the drift screen", rows[1.4]["why_not"])
        self.assertEqual(rows[1.4]["drift"]["alpha_t"], 0.4)
        self.assertTrue(rows[1.35]["eligible"])
        self.assertEqual(view["table"][0]["params"], {"vrp_min": 1.35}, "the passing row heads the table")
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["best_train_version"], rows[1.35]["version"])
        self.assertIn(str(rows[1.4]["version"]), fam["state"]["drift_failed"])


if __name__ == "__main__":
    unittest.main()
