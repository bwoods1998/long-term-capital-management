"""The swarm's rounds: the hourly tournament, the gate and the nightly forward, the architect
(league/swarm/tournament.py, gate.py, architect.py). A fake Gym pool, a scripted Sail, a fake gateway."""

from __future__ import annotations

import copy
import json
import random
import tempfile
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.architect import Architect
from league.swarm.gate import Gate
from league.swarm.models import ModelRouter
from league.swarm.pool import PoolError
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock, FakeFrontier, FakeMonth, provider, result

SPEC = {"id": "condor-vrp", "mechanism": "Index options price more movement than follows: sell an iron condor.",
        "structure": "iron_condor", "roots": ["SPY"], "dte": [0, 2]}


class FakeGymPool:
    """submit / wait / run: `answer(job)` makes each result; `fail` names families whose jobs fail."""

    def __init__(self, answer):
        self.answer = answer
        self.jobs = []
        self.fail: set[str] = set()
        self.cancelled: list[str] = []

    def submit(self, job):
        self.jobs.append(job)
        return job

    def wait(self, job, timeout=None):
        if job.family in self.fail:
            raise PoolError("the Gym failed")
        return self.answer(job)

    def run(self, job, timeout=None):
        return self.wait(self.submit(job), timeout)

    def cancel_family(self, family):
        self.cancelled.append(family)


def strong(job):
    rng = random.Random(hash((job.family, job.window, job.stress)) & 0xFFFF)
    daily = [rng.gauss(6.0, 10.0) for _ in range(250)]
    return result(job.name, daily=daily, window=job.window, pnl=sum(daily))


def weak(job):
    rng = random.Random(5)
    daily = [rng.gauss(-1.0, 10.0) for _ in range(250)]
    return result(job.name, daily=daily, window=job.window, pnl=sum(daily), mean=-0.01, t=-0.5, quarters="1/4")


class RoundCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.root = Path(self.dir.name)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"
        self.answer = strong
        self.pool = FakeGymPool(lambda job: self.answer(job))
        self.replies: list = []
        self.provider, self.sail = provider(self.root / "p.sqlite", lambda body: self.replies.pop(0) if self.replies else {"text": "{}"})
        self.addCleanup(self.provider.close)
        self.asked: list = []
        self.frontier_text = "{}"
        self.month = FakeMonth(None)
        self.router = ModelRouter(self.store, self.provider, settings=self.settings, month=self.month,
                                  frontier_factory=lambda model: FakeFrontier(model, text=self.frontier_text, asked=self.asked))

    def family(self, fid="condor-vrp", **kw):
        fam = self.store.add_family({**SPEC, "id": fid, **kw}, origin="seed")
        v = self.store.add_version(fam["id"], "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="seed")
        self.store.update_family(fam["id"], best_version=v["n"])
        return self.store.family(fam["id"])


class TournamentTests(RoundCase):
    def test_validation_runs_twice_is_judged_by_the_line_and_the_researcher_sees_only_a_summary(self):
        self.family("a")
        self.family("b")
        self.answer = lambda job: strong(job) if job.family == "a" else weak(job)
        row = Tournament(self.store, self.pool, self.settings, rng=random.Random(1)).run()
        self.assertEqual(sorted((j.family, j.window, j.stress) for j in self.pool.jobs),
                         [("a", "validation", 1.0), ("b", "validation", 1.0)], "one job a family: the Gym runs the stress twin")
        self.assertTrue(row["validation"]["judged"]["a"]["passed"])
        self.assertFalse(row["validation"]["judged"]["b"]["passed"])
        a = self.store.family("a")
        self.assertTrue(a["state"]["gate_ready"])
        self.assertEqual(set(a["state"]["validation_view"]), {"mean_return_on_max_loss", "t", "quarters_positive", "line_met", "checks_not_met"})
        self.assertEqual(a["trials"], 2)
        self.assertEqual(a["state"]["typical_max_loss_usd"], 60.0)
        self.assertAlmostEqual(sum(f["weight"] for f in self.store.families(alive=True)), 1.0)
        [event] = [e for e in self.store.events_after(0) if e["kind"] == "swarm.tournament"]
        self.assertEqual(event["payload"]["totals"]["trials"], 4)
        # The same version is not validated twice.
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual(len(self.pool.jobs), 2)

    def test_a_validation_view_without_its_stress_twin_does_not_pass(self):
        self.family("a")
        self.answer = lambda job: {k: v for k, v in strong(job).items() if k != "stress_1.5"}
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertFalse(out["judged"]["a"]["passed"])
        self.assertIn("stress", self.store.family("a")["state"]["validation_view"]["checks_not_met"])

    def test_retirement_after_thirty_revisions_without_validation_improvement_respects_the_floor(self):
        for i in range(18):
            self.family(f"f{i}")
        self.store.update_family("f3", since_val_revisions=30)
        self.store.update_family("f4", since_val_trials=2000)
        self.store.note("f3", "condors died on trend days")
        t = Tournament(self.store, self.pool, self.settings)
        out = t.retirements(self.store.families(alive=True))
        self.assertEqual(sorted(r["family"] for r in out), ["f3", "f4"])
        self.assertEqual(self.store.family("f3")["band"], "retired")
        self.assertIn("condors died on trend days", self.store.graveyard("trend")[0]["lesson"])
        self.assertIn("f3", self.pool.cancelled)
        for i in range(5, 18):
            self.store.update_family(f"f{i}", since_val_revisions=40)
        out = t.retirements(self.store.families(alive=True))
        self.assertEqual(len(self.store.families(alive=True)), 16, "never below the floor")

    def test_a_banded_family_is_not_retired_by_the_tournament(self):
        for i in range(17):
            self.family(f"f{i}")
        self.store.update_family("f0", since_val_revisions=99, band="candidate")
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])

    def test_a_strong_family_forks_onto_another_root_and_the_child_inherits_the_lineage(self):
        fam = self.family("a")
        self.store.add_run("a", 1, result("x"), window="train", stress=1.0, purpose="train")
        self.store.set_state("a", validation_numbers={"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"})
        t = Tournament(self.store, self.pool, self.settings)
        born = t.forks(self.store.families(alive=True))
        self.assertEqual(born, ["a-on-qqq"])
        child = self.store.family("a-on-qqq")
        self.assertEqual((child["roots"], child["parent"], child["lineage"], child["inherited_trials"]), (["QQQ"], "a", "a", 1))
        self.assertIn("'QQQ'", self.store.latest_version("a-on-qqq")["code"])
        self.assertEqual(t.forks(self.store.families(alive=True)), [], "a cooldown between forks")
        born_events = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"]
        self.assertEqual(born_events[-1]["payload"]["parent"], "a")
        del fam

    def test_a_validation_failure_is_recorded_not_raised(self):
        self.family("a")
        self.pool.fail.add("a")
        out = Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertIn("a", out["errors"])


class GateTests(RoundCase):
    def ready(self, fid="a"):
        self.family(fid)
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"])

    def test_review_then_one_holdout_look_then_candidate_and_the_researcher_hears_only_pass(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}]
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}])
        [look] = [j for j in self.pool.jobs if j.window == "holdout"]
        self.assertTrue(look.gate.startswith("holdout look a"))
        fam = self.store.family("a")
        self.assertEqual((fam["band"], fam["state"]["gate"]), ("candidate", "pass"))
        self.assertEqual(fam["state"]["banded_version"], 1)
        self.assertEqual(len(self.store.looks()), 1)
        self.assertEqual(self.sail.bodies[0]["model"], "deepseek-ai/DeepSeek-V4-Pro-0813", "no OpenAI room: the Sail reviewer")
        # A second round does not look at the same version again.
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len([j for j in self.pool.jobs if j.window == "holdout"]), 1)
        gate_rows = [e for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["payload"].get("action") == "look"]
        self.assertIn("_line", gate_rows[0]["payload"], "the numbers stay private")

    def test_a_failed_review_is_a_refusal_and_costs_no_look(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "fail", "reasons": ["counts sessions to known events"]})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(self.store.refusals("a")[0]["stage"], "review")
        self.assertIn("counts sessions", self.store.family("a")["state"]["gate"])

    def test_an_unclear_review_is_asked_again_then_refused(self):
        self.ready()
        self.replies = [{"text": "hmm"}, {"text": "hmm"}, {"text": "hmm"}]
        for _ in range(3):
            Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(len(self.store.refusals("a")), 1)

    def test_openai_reviews_when_the_month_has_room(self):
        self.ready()
        self.month.value = 100
        self.frontier_text = json.dumps({"verdict": "pass"})
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.asked[0]["model"], "gpt-6-sol")
        self.assertEqual(self.sail.bodies, [])
        self.assertAlmostEqual(self.store.spent(["openai"]), 0.40)

    def test_a_failing_holdout_is_a_fail_and_the_band_stays(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
        self.answer = lambda job: weak(job) if job.window == "holdout" else strong(job)
        Gate(self.store, self.pool, self.router, self.settings).run()
        fam = self.store.family("a")
        self.assertEqual((fam["band"], fam["state"]["gate"]), ("gym", "fail"))

    def test_three_looks_a_lineage(self):
        self.ready()
        self.store.update_family("a", inherited_looks=3)
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(self.store.refusals("a")[0]["stage"], "rations")

    def test_the_leakage_alarm_stops_the_gate(self):
        self.ready()
        for i in range(10):
            self.store.add_look("a", 1, f"sha{i}", passed=i < 4, p_value=0.01, detail={})
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertTrue(out["alarm"])
        self.assertTrue(self.store.get("leakage_alarm"))
        self.assertEqual(self.sail.bodies, [])

    def test_no_gate_image_no_look(self):
        self.ready()
        self.settings["gym"]["gate_checkpoint"] = None
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["waiting"], ["a"])
        self.assertEqual(self.store.looks(), [])

    def test_the_nightly_forward_records_trades_and_demotes_a_negative_candidate(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.answer = lambda job: {**weak(job), "trades": [{"id": i, "day": "2026-09-28", "entry_minute": 600 + i, "root": "SPY",
                                                            "type": "iron_condor", "pnl": -5.0, "max_loss": 60.0} for i in range(25)]}
        gate = Gate(self.store, self.pool, self.router, self.settings)
        self.clock.advance(86400)
        self.assertTrue(gate.forward_due())
        out = gate.forward()
        self.assertEqual(out["trades"], 25)
        self.assertEqual(out["moves"], [{"family": "a", "to": "gym"}])
        self.assertFalse(gate.forward_due(), "once a day")
        self.store.set_band("a", "candidate", reason="test")
        self.clock.advance(86400)
        gate.forward()
        self.assertEqual(len([t for t in self.store.forward("a") if t["source"] == "nightly"]), 25, "a rerun replaces, never doubles")
        self.assertEqual([j.gate for j in self.pool.jobs if j.window == "forward"], ["nightly forward replay"] * 2)

    def test_the_swarm_never_makes_a_probe_or_a_sized(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.store.add_forward("a", "shadow", [{"id": f"t{i}", "day": "d", "pnl": 10.0, "max_loss": 50.0} for i in range(30)])
        self.assertIsNone(Gate(self.store, self.pool, self.router, self.settings).judge_forward("a"))
        self.assertEqual(self.store.family("a")["band"], "candidate")


class ArchitectTests(RoundCase):
    PROPOSAL = {"families": [
        {"slug": "gamma-scalp-spy", "mechanism": "Dealers short gamma amplify afternoon moves; buy a straddle when they are.",
         "structure": "long_straddle", "roots": ["SPY"], "dte": [0, 1], "rejection": "straddles lose", "sketch": "buy at 13:00"},
        {"slug": "bad", "mechanism": "x", "structure": "iron_condor", "roots": ["SPY"]},
        {"slug": "index-calendar", "mechanism": "A calendar on the index where the front kinks over the back month.",
         "structure": "calendar", "roots": ["XSP"]},
        {"slug": "naked", "mechanism": "Sell naked puts because they usually expire worthless and pay.", "structure": "short_put",
         "roots": ["SPY"]},
        {"slug": "tsla", "mechanism": "Single-name momentum after earnings with debit verticals on the move.", "structure": "debit_vertical",
         "roots": ["TSLA"]}]}

    def test_it_admits_only_well_formed_families_and_they_read_the_graveyard(self):
        self.family("old")
        self.store.bury("old", "straddles on SPY bled theta on quiet days")
        self.replies = [{"text": json.dumps(self.PROPOSAL)}]
        out = Architect(self.store, self.router, self.settings).run()
        self.assertEqual(out["born"], ["gamma-scalp-spy"])
        fam = self.store.family("gamma-scalp-spy")
        self.assertEqual((fam["origin"], fam["structure"]), ("architect", "long_straddle"))
        self.assertTrue(fam["spec"]["lessons"])
        self.assertIn("sketch", self.store.notebook("gamma-scalp-spy")[0]["text"])
        self.assertEqual(self.sail.bodies[0]["model"], "moonshotai/Kimi-K3")

    def test_astra_when_openai_has_room_and_sail_when_it_refuses(self):
        self.month.value = 50
        self.frontier_text = json.dumps(self.PROPOSAL)
        out = Architect(self.store, self.router, self.settings).run()
        self.assertEqual((out["route"], self.asked[0]["model"]), ("openai", "gpt-6-astra"))
        self.router.frontier_factory = lambda model: FakeFrontier(model, fail=RuntimeError("HTTP 402 month"))
        self.replies = [{"text": json.dumps({"families": []})}]
        self.clock.advance(20000)
        out = Architect(self.store, self.router, self.settings).run()
        self.assertEqual(out["route"], "sail")

    def test_every_four_hours(self):
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertTrue(a.due())
        self.replies = [{"text": json.dumps({"families": []})}]
        a.run()
        self.clock.advance(4 * 3600 - 1)
        self.assertFalse(a.due())
        self.clock.advance(2)
        self.assertTrue(a.due())

    def test_the_openai_cap_is_the_swarms_too(self):
        self.month.value = 500
        self.store.add_spend("openai", 149.5)
        self.assertLess(self.router.openai_room(), 1.0)

    def test_the_ceiling_bounds_it(self):
        self.settings["population"]["ceiling"] = 1
        self.family("only")
        out = Architect(self.store, self.router, self.settings).run()
        self.assertEqual(out["born"], [])
        self.assertEqual(self.sail.bodies, [])

    def test_gaps_name_uncovered_slices(self):
        self.family("a")
        gaps = Architect(self.store, self.router, self.settings).gaps()
        self.assertNotIn("iron_condor on SPY", gaps)
        self.assertIn("iron_condor on QQQ", gaps)
        self.assertNotIn("calendar on XSP", gaps)


if __name__ == "__main__":
    unittest.main()
