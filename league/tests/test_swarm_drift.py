"""THE DRIFT SCREEN on the swarm's side (Sept 27): its settings and their swarm.json override, the run rows that keep the
figures, the tournament's eligibility, the gate's refusal, the researcher's lines and the re-run of a version whose Train
run predates the figures. Invented results only (league/tests/swarm_fakes.py)."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from league.swarm import diagnostics, evidence
from league.swarm import settings as S
from league.swarm.gate import Gate
from league.swarm.researcher import drift_settings, drift_verdict, version_drift
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import drift_block, result
from league.tests.test_swarm_researcher import FakePool, ResearcherCase
from league.tests.test_swarm_rounds import RoundCase

FAILING = drift_block(t=0.4, alpha_usd=30.0, drift_usd=900.0)          # the profit is drift: alpha t 0.4
FEW_YEARS = drift_block(t=1.8, alpha_usd=-50.0, drift_usd=400.0)       # a strong pooled t, but alpha negative every year


def train_result(name: str = "p", *, drift: object = "default", **kw) -> dict:
    """An invented Train result with the Gym's per-year block (eligible under the Train score) and a drift block: the
    fake's passing one by default, the one given, or none (None: a run from before the figures)."""
    r = result(name, **kw)
    r["by_year"] = {str(2022 + i): {"trades": 60, "days": 252, "days_traded": 30, "pnl": 100.0, "t_daily": 2.0,
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
        status = researcher.status(fam)
        self.assertIn("Drift screen of version 1", status)
        self.assertIn("FAILS", status)
        self.steps = [{"text": "ok"}]
        before = len(self.pool.queued)
        self.researcher().cycle(fid)  # a new process: the figures landed, so no drift run is queued again
        self.assertEqual([j.stress for j in self.pool.queued[before:]], [1.5, 0.0])

    def test_a_best_with_figures_needs_no_run_again_and_its_view_shows_the_lines(self):
        self.drift = "default"
        self.researcher().cycle(self.fam["id"])
        self.assertEqual([j.stress for j in self.pool.queued], [1.5, 0.0])
        status = self.researcher().status(self.store.family(self.fam["id"]))
        self.assertIn("passes", status)
        view = diagnostics.train_view(train_result(), screen=drift_settings(self.settings))
        self.assertEqual(set(view["drift"]), {"2022", "2023", "2024", "train", "screen", "note"})
        self.assertEqual(view["drift"]["2022"], "drift-adjusted alpha $150 (t 2.00), drift $20, beta $2 per 1% move")
        self.assertTrue(view["drift"]["screen"].startswith("passes"))
        failing = diagnostics.train_view(train_result(drift=FAILING), screen=(1.0, None))
        self.assertTrue(failing["drift"]["screen"].startswith("fails: its drift-adjusted alpha has t 0.4"))
        self.assertNotIn("drift", diagnostics.train_view(train_result(drift=None)))
        self.assertIn("drift", diagnostics.section(train_result(), "drift"))
        self.assertIn("error", diagnostics.section(train_result(drift=None), "drift"))

    def test_the_prompt_says_drift_is_not_an_edge(self):
        from league.swarm.researcher import ROLE, TOOLS

        self.assertIn("DRIFT IS NOT AN EDGE", ROLE)
        self.assertIn("drift", next(t for t in TOOLS if t["name"] == "read_run")["parameters"]["properties"]["section"]["description"])


if __name__ == "__main__":
    unittest.main()
