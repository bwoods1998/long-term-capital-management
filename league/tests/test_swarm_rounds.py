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
from league.swarm.pool import GymJob, PoolError
from league.swarm.seeds import SEEDS, family_spec
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
        self.slow: set[str] = set()
        self.landing: list = []
        self.cancelled: list[str] = []

    def submit(self, job):
        self.jobs.append(job)
        return job

    def wait(self, job, timeout=None, late=None, late_fail=None):
        if job.family in self.fail:
            raise PoolError("the Gym failed")
        if job.family in self.slow:  # the round stops waiting; the result lands later
            job.late = late
            job.late_fail = late_fail
            self.landing.append((job, late))
            raise PoolError("the Gym did not answer in time")
        return self.answer(job)

    def run(self, job, timeout=None, late=None, late_fail=None):
        return self.wait(self.submit(job), timeout, late, late_fail)

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
        v = self.store.add_version(fam["id"], f"# {fid}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n", {},
                                   author="seed")
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

    def test_a_fork_onto_a_root_a_retired_sibling_searched_inherits_its_trials_and_looks(self):
        self.family("a")
        self.store.add_run("a", 1, result("x"), window="train", stress=1.0, purpose="train")
        self.store.set_state("a", validation_numbers={"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"})
        t = Tournament(self.store, self.pool, self.settings)
        [first] = t.forks(self.store.families(alive=True))
        for i in range(50):
            self.store.add_run(first, 1, result(f"c{i}"), window="train", stress=1.0, purpose="train")
        self.store.add_look(first, 1, "sha-c1", passed=False, p_value=0.5, detail={})
        self.store.retire(first, "no improvement")
        self.store.set_state("a", forked_at=0)
        [second] = t.forks(self.store.families(alive=True))
        self.assertEqual(self.store.family(second)["roots"], self.store.family(first)["roots"])
        self.assertEqual(self.store.lineage_trials(second), 1 + 50)
        self.assertEqual(self.store.lineage_looks(second), 1)

    def test_a_fork_chain_never_counts_an_ancestors_looks_twice(self):
        a = self.family("a")
        self.store.add_look("a", 1, "sha-a", passed=False, p_value=0.5, detail={})
        b = self.store.add_family({**SPEC, "id": "b", "roots": ["QQQ"]}, origin="fork", parent="a")
        self.store.retire("a", "done")
        self.store.set_state("b", validation_numbers={"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"})
        self.store.add_version("b", "# b\nNEEDS = {'roots': ['QQQ']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {}, author="x")
        self.store.update_family("b", best_version=1)
        [c] = Tournament(self.store, self.pool, self.settings).forks(self.store.families(alive=True))
        self.assertEqual(self.store.family(c)["roots"], ["SPY"])
        self.assertEqual(self.store.lineage_looks(c), 1, "a's one look, once")
        del a, b

    def test_a_fork_back_onto_an_ancestors_slice_counts_the_looks_it_spent_there_after_the_fork(self):
        self.family("a")  # SPY
        self.store.set_state("a", validation_numbers={"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"})
        t = Tournament(self.store, self.pool, self.settings)
        [b] = t.forks(self.store.families(alive=True))
        self.assertEqual(self.store.family(b)["roots"], ["QQQ"])
        self.clock.advance(3600)
        for i in range(2):  # a spends two SPY looks after b was born, then retires
            self.store.add_look("a", 1, f"sha-a{i}", passed=False, p_value=0.5, detail={})
        self.store.retire("a", "done")
        self.clock.advance(3600)
        self.store.set_state(b, validation_numbers={"mean": 0.05, "t": 2.5, "sharpe_daily": 0.2, "quarters": "4/4"})
        [c] = t.forks(self.store.families(alive=True))
        self.assertEqual(self.store.family(c)["roots"], ["SPY"])
        self.assertEqual(self.store.lineage_looks(c), 2, "SPY's holdout was looked at twice by this lineage")
        self.assertEqual(self.store.lineage_looks(b), 2, "the whole lineage shares the ration across roots and fork dates")

    def test_a_late_validation_of_an_older_version_never_overwrites_a_newer_one(self):
        self.family("a")
        t = Tournament(self.store, self.pool, self.settings)
        v2 = self.store.add_version("a", "# a2\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return None\n", {}, author="x")
        self.store.update_family("a", best_version=v2["n"])  # the researcher's best moved on to v2
        job = lambda n: GymJob(family="a", version=n, code="", params={}, window="validation", roots=("SPY",))
        self.assertTrue(t.judge("a", v2["n"], strong(job(v2["n"])))["passed"])
        trials = self.store.family("a")["trials"]
        self.assertIsNone(t.judge("a", 1, weak(job(1))), "version 1's result landed late")
        fam = self.store.family("a")
        self.assertEqual((fam["validated_version"], fam["state"]["validation_version"], fam["state"]["gate_ready"]), (2, 2, True))
        self.assertEqual(fam["trials"], trials + 2, "its trials still count")

    def validation_jobs(self):
        return [j for j in self.pool.jobs if j.window == "validation"]

    def test_an_older_version_submitted_again_is_judged_once_not_revalidated_every_hour(self):
        self.family("a")
        t = Tournament(self.store, self.pool, self.settings)
        v2 = self.store.add_version("a", "# a2\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return None\n", {}, author="x")
        self.store.update_family("a", best_version=v2["n"])
        self.answer = weak
        t.validate(self.store.families(alive=True))
        self.store.update_family("a", best_version=1)  # the researcher submits its older (never validated) version
        self.answer = strong
        t.validate(self.store.families(alive=True))
        fam = self.store.family("a")
        self.assertEqual((fam["validated_version"], fam["state"]["validation_version"], fam["state"]["gate_ready"]), (1, 1, True))
        jobs, trials = len(self.validation_jobs()), fam["trials"]
        for _ in range(3):
            t.validate(self.store.families(alive=True))
        self.assertEqual((len(self.validation_jobs()), self.store.family("a")["trials"]), (jobs, trials), "judged once")

    def test_a_version_validated_before_is_judged_again_from_its_recorded_result(self):
        self.family("a")
        t = Tournament(self.store, self.pool, self.settings)
        self.answer = strong
        t.validate(self.store.families(alive=True))
        v2 = self.store.add_version("a", "# a2\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return None\n", {}, author="x")
        self.store.update_family("a", best_version=v2["n"])
        self.answer = weak
        t.validate(self.store.families(alive=True))
        self.assertFalse(self.store.family("a")["state"]["gate_ready"])
        jobs, trials = len(self.validation_jobs()), self.store.family("a")["trials"]
        self.store.update_family("a", best_version=1)  # back to v1
        t.validate(self.store.families(alive=True))
        fam = self.store.family("a")
        self.assertEqual((len(self.validation_jobs()), fam["trials"]), (jobs, trials), "no new Gym run, no new trial")
        self.assertEqual((fam["state"]["validation_version"], fam["state"]["gate_ready"]), (1, True))

    def test_a_recorded_validation_from_another_gym_image_is_not_reused(self):
        self.family("a")
        self.pool.image = lambda kind: "sbcp_gym_v0"
        self.answer = lambda job: {**strong(job), "gym_image": "sbcp_gym_v0"}
        t = Tournament(self.store, self.pool, self.settings)
        t.validate(self.store.families(alive=True))
        v2 = self.store.add_version("a", "# a2\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return None\n", {}, author="x")
        self.store.update_family("a", best_version=v2["n"])
        t.validate(self.store.families(alive=True))
        jobs = len(self.validation_jobs())
        self.pool.image = lambda kind: "sbcp_gym_v1"  # the Gym moved to other data
        self.store.update_family("a", best_version=1)
        t.validate(self.store.families(alive=True))
        self.assertEqual(len(self.validation_jobs()), jobs + 1, "v1 runs again on the new Gym's data")

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
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2
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

    def test_a_slow_look_is_never_started_twice_and_is_recorded_when_it_lands(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 6
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)  # one process
        gate.run()
        self.clock.advance(60)
        gate.run()
        self.assertEqual(len([j for j in self.pool.jobs if j.window == "holdout"]), 1, "in flight: not started again")
        self.assertEqual(self.store.looks(), [])
        job, late = self.pool.landing[0]
        late(strong(job))
        late(strong(job))
        self.assertEqual(len(self.store.looks()), 1, "recorded once, when it landed")
        self.assertEqual(self.store.family("a")["band"], "candidate")

    def test_a_look_the_gym_failed_is_still_owed(self):
        self.ready()
        self.pool.fail.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 4
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        self.pool.fail.clear()
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_look_cut_off_by_a_restart_is_owed_to_the_next_process(self):
        self.ready()
        self.pool.slow.add("a")  # the look is in flight when the process dies
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 4
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.assertEqual(self.store.looks(), [])
        self.clock.advance(60)
        self.pool.slow.clear()
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()  # a new process: no job survived
        self.assertEqual(len(self.store.looks()), 1, "owed and looked")

    def test_a_look_that_fails_after_its_waiter_gave_up_is_owed(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        gate = Gate(self.store, self.pool, self.router, self.settings)
        gate.run()
        job, late = self.pool.landing[0]
        self.assertIsNotNone(job.late_fail)
        job.late_fail("the Gym failed twice")
        self.pool.slow.clear()
        gate.run()
        self.assertEqual(len(self.store.looks()), 1)

    def newer(self, fid, answer, tag="v2"):
        """The researcher's newer best, validated by the tournament (`answer` makes it pass or fail the line)."""
        v = self.store.add_version(fid, f"# {tag}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return None\n", {},
                                   author="x")
        self.store.update_family(fid, best_version=v["n"])
        self.answer = answer
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertEqual(self.store.family(fid)["state"]["validation_version"], v["n"])
        return v

    def alerts(self):
        return [e for e in self.store.events_after(0) if e["kind"] == "swarm.status" and e["payload"].get("alert")
                and e["payload"].get("action") == "look_failed_three_times"]

    def test_a_superseded_versions_look_marker_is_dropped_without_a_refusal_or_an_alert(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.pool.slow.clear()
        self.newer("a", weak)  # v2 fails the line while v1's look is in flight
        self.clock.advance(60)
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)  # a restart
        for _ in range(6):
            gate.run()
            self.clock.advance(300)
        state = self.store.family("a")["state"]
        self.assertIsNone(state.get("look_inflight"), "nothing is owed for a version no longer validated")
        self.assertEqual((self.store.refusals("a"), self.alerts()), ([], []))
        self.assertEqual(len([j for j in self.pool.jobs if j.window == "holdout"]), 1)

    def test_a_late_failure_of_a_superseded_look_clears_its_marker(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        gate.run()
        job, _ = self.pool.landing[0]
        self.pool.slow.clear()
        self.newer("a", weak)
        job.late_fail("the Gym failed twice")
        state = self.store.family("a")["state"]
        self.assertIsNone(state.get("look_inflight"))
        self.assertFalse(state["gate_ready"], "v2 failed its line: not re-armed")
        self.assertEqual(self.store.refusals("a"), [])

    def test_a_look_the_gym_cannot_make_is_refused_and_alerted_once(self):
        self.ready()
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        for _ in range(5):
            gate.owe("a", 1, "sha-a1")
        self.assertEqual(len(self.store.refusals("a")), 1)
        self.assertEqual(len(self.alerts()), 1)

    def test_a_late_result_of_an_older_look_never_clears_the_newer_looks_marker(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 4
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        self.pool.slow.clear()
        self.newer("a", strong)  # v2 passes its line while v1's look is out
        self.pool.slow.add("a")
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()  # v2's look goes out too
        self.assertEqual(len(self.pool.landing), 1, "the older look still reserves the family's place")
        self.clock.advance(2200)
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()  # the old attempt expired
        (job1, late1), (job2, _) = self.pool.landing
        self.assertEqual((job1.version, job2.version), (1, 2))
        late1(weak(job1))  # v1's result lands: a look, and a fail
        self.assertEqual(self.store.family("a")["state"]["look_inflight"]["n"], 2, "v2's marker stands")
        self.pool.slow.clear()
        self.clock.advance(60)
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()  # a restart: v2's look is owed
        self.assertEqual([x["version"] for x in self.store.looks()], [1, 2])

    def test_the_gate_looks_only_at_the_version_still_validated(self):
        self.ready("a")
        self.ready("b")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 8
        store = self.store
        answer = self.answer

        def during_as_look(job):
            if job.family == "a" and job.window == "holdout":  # meanwhile the tournament validates b's newer version
                v3 = store.add_version("b", "NEEDS = {'roots': ['SPY']}\nPARAMS = {'k': 1}\ndef decide(ctx):\n    return None\n", {},
                                       author="x")
                store.update_family("b", validated_version=v3["n"])
                store.set_state("b", validation_version=v3["n"], gate_ready=True)
            return answer(job)

        self.answer = during_as_look
        Gate(self.store, self.pool, self.router, self.settings).run()
        looked_b = [x for x in self.store.looks() if x["family"] == "b"]
        self.assertEqual([x["version"] for x in looked_b], [], "b's superseded version is never looked at")
        self.assertTrue(self.store.family("b")["state"]["gate_ready"], "b's new version keeps its place")

    def test_an_unclear_audit_is_asked_again_before_a_refusal(self):
        self.ready()
        self.month.value = 100
        texts = iter([json.dumps({"verdict": "pass"}), "no verdict here", "still none", json.dumps({"verdict": "pass"})])
        self.router.frontier_factory = lambda model: FakeFrontier(model, text=next(texts), asked=self.asked)
        for _ in range(3):
            Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.refusals("a"), [])
        self.assertEqual(len(self.store.looks()), 1)

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

    def test_openai_reviews_and_astra_audits_when_the_month_has_room(self):
        self.ready()
        self.month.value = 100
        self.frontier_text = json.dumps({"verdict": "pass"})
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual([a["model"] for a in self.asked], ["gpt-6-sol", "gpt-6-astra"])
        self.assertEqual(self.sail.bodies, [])
        self.assertAlmostEqual(self.store.spent(["openai"]), 0.80)
        review = self.store.family("a")["state"]["review"]
        self.assertEqual((review["route"], review["audit"]["route"]), ("openai", "openai"))

    def test_an_audit_that_fails_costs_no_look(self):
        self.ready()
        self.month.value = 100
        answers = iter([json.dumps({"verdict": "pass"}), json.dumps({"verdict": "fail", "reasons": ["counts sessions to the year"]})])
        self.router.frontier_factory = lambda model: FakeFrontier(model, text=next(answers), asked=self.asked)
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(self.store.refusals("a")[0]["stage"], "audit")

    def test_without_openai_room_the_audit_is_a_second_different_sail_model_and_the_owner_is_told(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}, {"text": json.dumps({"verdict": "pass"})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual([b["model"] for b in self.sail.bodies], ["deepseek-ai/DeepSeek-V4-Pro-0813", "moonshotai/Kimi-K3"],
                         "the audit is another model, not a pass-through")
        review = self.store.family("a")["state"]["review"]
        self.assertEqual((review["route"], review["audit"]["route"], review["audit"]["model"]), ("sail", "sail", "k3_balanced"))
        alerts = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.status"
                  and e["payload"].get("action") == "not_the_plans_reviewer"]
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["alert"])
        self.assertEqual(len(self.store.looks()), 1)

    def test_a_sail_audit_that_refuses_costs_no_look(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}, {"text": json.dumps({"verdict": "fail", "reasons": ["a level"]})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.looks(), [])
        self.assertEqual(self.store.refusals("a")[0]["stage"], "audit")

    def test_a_failing_holdout_is_a_fail_and_the_band_stays(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        self.answer = lambda job: weak(job) if job.window == "holdout" else strong(job)
        Gate(self.store, self.pool, self.router, self.settings).run()
        fam = self.store.family("a")
        self.assertEqual((fam["band"], fam["state"]["gate"]), ("gym", "fail"))

    def test_three_looks_a_lineage(self):
        self.ready()
        for i in range(3):  # three looks this lineage already made on the slice (the ration is counted from the looks)
            self.store.add_look("a", 1, f"earlier-{i}", passed=False, p_value=0.5, detail={})
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.store.looks()), 3, "no fourth look")
        self.assertEqual([j for j in self.pool.jobs if j.window == "holdout"], [])
        self.assertEqual(self.store.refusals("a")[0]["stage"], "rations")

    def test_the_leakage_alarm_stops_the_gate(self):
        self.ready()
        for i in range(10):
            self.store.add_look("a", 1, f"sha{i}", passed=i < 4, p_value=0.01, detail={})
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertTrue(out["alarm"])
        self.assertTrue(self.store.get("leakage_alarm"))
        self.assertEqual(self.sail.bodies, [])

    def test_no_gate_image_no_look_but_the_review_runs_and_is_kept(self):
        from league.swarm import bands
        from league.gym.driver import build_bundle

        self.pool.image = lambda kind: "sbcp_synthetic_gym"
        bundle = build_bundle()[1]
        self.pool.bundle = lambda: bundle
        self.answer = lambda job: {**strong(job), "gym_image": "sbcp_synthetic_gym", "gym_bundle": bundle}
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "sbcp_synthetic_gym"}}))
        self.ready()
        self.settings["gym"]["gate_checkpoint"] = None
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["waiting"], ["a"])
        self.assertEqual(self.store.looks(), [])
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["a"], "reviewed and waiting: tuition may run it")
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.sail.bodies), 2, "the review and the audit, neither asked twice")
        self.assertEqual(len(self.store.looks()), 1)

    def test_the_nightly_forward_records_trades_and_demotes_a_negative_candidate(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
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

    def test_a_failed_nightly_replay_keeps_the_record(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        trades = [{"day": f"2026-09-{28 + i // 5}", "pnl": -5.0, "max_loss": 60.0} for i in range(19)]
        self.answer = lambda job: {**weak(job), "trades": trades}
        gate = Gate(self.store, self.pool, self.router, self.settings)
        self.clock.advance(86400)
        gate.forward()
        self.assertEqual(len(self.store.forward("a")), 19)
        self.answer = lambda job: {"status": "error", "trades": [], "summary": {}, "trials": 1, "run_id": "err"}
        self.clock.advance(86400)
        out = gate.forward()
        self.assertEqual(len(self.store.forward("a")), 19, "an error never wipes the record")
        self.assertIn("a", out["failed"])

    def test_the_forward_record_is_the_banded_versions_alone(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.store.add_forward("a", "shadow", [{"id": f"old{i}", "day": f"d{i}", "pnl": -4.0, "max_loss": 60.0, "version": 0}
                                                for i in range(22)])
        self.assertIsNone(Gate(self.store, self.pool, self.router, self.settings).judge_forward("a"),
                          "another version's trades never judge this one")
        self.assertEqual(self.store.family("a")["band"], "candidate")

    def test_a_look_never_undoes_a_newer_validation(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        v2 = self.store.add_version("a", "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return None\n", {}, author="x")
        self.store.update_family("a", best_version=v2["n"])
        self.store.set_state("a", validation_version=v2["n"], gate_ready=True)
        job, late = self.pool.landing[0]
        late(strong(job))
        fam = self.store.family("a")
        self.assertTrue(fam["state"]["gate_ready"], "the newer version still waits for its gate")
        self.assertEqual(fam["best_version"], v2["n"])

    def test_the_swarm_never_makes_a_probe_or_a_sized(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.store.add_forward("a", "shadow", [{"id": f"t{i}", "day": "d", "pnl": 10.0, "max_loss": 50.0} for i in range(30)])
        self.assertIsNone(Gate(self.store, self.pool, self.router, self.settings).judge_forward("a"))
        self.assertEqual(self.store.family("a")["band"], "candidate")


class ArchitectTests(RoundCase):
    FINAL_ROOTS = ["SPY", "QQQ", "IWM", "XSP", "SPXW", "TSLA", "NVDA", "TLT", "AMD", "SLV", "AMZN", "META",
                   "AAPL", "PLTR", "TQQQ", "SMCI", "MARA", "GLD", "TSM", "MSFT", "MU", "BABA", "SMH", "GOOGL", "SOXL"]

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

    def populate(self, n):
        for i in range(n):
            self.store.add_family({**SPEC, "id": f"pop-{i}", "mechanism": f"Idea number {'abcdefghijklmnopqrstuvwxyz'[i % 26]} "
                                   f"{i // 26} of the founding population, a condor on the index."}, origin="seed")

    def many(self, n):
        return {"families": [{"slug": f"new-{i}", "mechanism": f"A distinct mechanism {'abcdefghijklmnop'[i]} for why a spread pays "
                                                                f"on this index after a {'abcdefghijklmnop'[i]} event.",
                              "structure": "iron_condor", "roots": ["QQQ"], "dte": [0, 2]} for i in range(n)]}

    def test_below_the_start_population_the_architect_refills_hourly_up_to_the_gap(self):
        self.populate(40)
        arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.store.put("architect_at", self.clock())
        self.clock.advance(3600)
        self.assertTrue(arch.refilling() and arch.due(), "40 alive of the 48 the swarm starts with: hourly")
        self.replies = [{"text": json.dumps(self.many(12))}]
        out = arch.run()
        self.assertEqual(len(out["born"]), 8, "up to the start population")
        self.assertIn("Propose 3 to 8 new families", self.sail.bodies[-1]["input"][-1]["content"])

    def test_at_the_start_population_it_grows_every_four_hours_three_to_six_at_a_time(self):
        self.populate(50)
        arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.store.put("architect_at", self.clock())
        self.clock.advance(3600)
        self.assertFalse(arch.refilling() or arch.due())
        self.clock.advance(4 * 3600)
        self.assertTrue(arch.due())
        self.replies = [{"text": json.dumps(self.many(12))}]
        self.assertEqual(len(arch.run()["born"]), 6)

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

    def test_a_proposal_on_a_retired_familys_slice_continues_its_lineage(self):
        old = self.family("fly", structure="iron_butterfly", roots=["SPY"],
                          mechanism="Sell the afternoon's at-the-money decay with an iron butterfly on calm days.")
        for i in range(30):
            self.store.add_run("fly", 1, result(f"f{i}"), window="train", stress=1.0, purpose="train")
        self.store.add_look("fly", 1, "sha-fly", passed=False, p_value=0.4, detail={})
        self.store.retire("fly", "no improvement in 30 revisions")
        rows = [{"slug": "fly-again", "mechanism": "Sell the afternoon's at-the-money decay with an iron butterfly on quiet days.",
                 "structure": "iron_butterfly", "roots": ["SPY"], "dte": [0, 1]}]
        [born] = Architect(self.store, self.router, self.settings).admit(rows)
        fam = self.store.family(born)
        self.assertEqual((fam["parent"], fam["lineage"]), ("fly", "fly"))
        self.assertEqual(self.store.lineage_trials(born), 30)
        self.assertEqual(self.store.lineage_looks(born), 1)
        del old

    def test_a_new_idea_on_a_dead_familys_slice_is_a_new_lineage_that_still_counts_its_trials(self):
        self.family("fly", structure="iron_butterfly", roots=["SPY"])
        for i in range(30):
            self.store.add_run("fly", 1, result(f"f{i}"), window="train", stress=1.0, purpose="train")
        self.store.add_look("fly", 1, "sha-fly", passed=False, p_value=0.4, detail={})
        self.store.retire("fly", "no improvement in 30 revisions")
        rows = [{"slug": "news-fly", "mechanism": "After a scheduled macro release the realized move undershoots what options priced.",
                 "structure": "iron_butterfly", "roots": ["SPY"], "dte": [0, 1]}]
        [born] = Architect(self.store, self.router, self.settings).admit(rows)
        fam = self.store.family(born)
        self.assertEqual((fam["parent"], fam["lineage"]), (None, born), "another mechanism: its own lineage")
        self.assertEqual(self.store.lineage_looks(born), 0, "no inherited look ration")
        self.assertEqual(self.store.lineage_trials(born), 30, "the slice's searching still deflates it")
        self.assertEqual(len(self.store.lineage_trial_sharpes(born)), 30, "the same set")
        self.store.add_run("fly", 1, result("late"), window="train", stress=1.0, purpose="train")
        self.assertEqual(self.store.lineage_trials(born), 31)

    def test_every_four_hours(self):
        self.populate(48)  # the start population: the plan's cadence (below it the architect refills hourly)
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertTrue(a.due())
        self.replies = [{"text": json.dumps({"families": []})}]
        a.run()
        self.clock.advance(4 * 3600 - 1)
        self.assertFalse(a.due())
        self.clock.advance(2)
        self.assertTrue(a.due())

    def test_an_openai_call_is_held_before_it_is_sent_and_settled_after(self):
        class Refused(Exception):
            status = 402

        self.month.value = 500
        self.router.frontier_factory = lambda model: FakeFrontier(model, fail=Refused("HTTP 402 month"))
        self.replies = [{"text": json.dumps({"families": []})}]
        Architect(self.store, self.router, self.settings).run()
        self.assertAlmostEqual(self.store.spent(["openai"]), 0.0, msg="a refusal is not billed")
        self.router.frontier_factory = lambda model: FakeFrontier(model, fail=TimeoutError("the gateway did not answer"))
        self.replies = [{"text": json.dumps({"families": []})}]
        self.clock.advance(20000)
        Architect(self.store, self.router, self.settings).run()
        self.assertAlmostEqual(self.store.spent(["openai"]), 2.0, msg="a call lost in flight keeps its hold")

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

    def expanded_prompt(self, *, seeded):
        self.settings["gym"]["roots"] = list(self.FINAL_ROOTS)
        if seeded:
            for spec in SEEDS[:48]:
                self.store.add_family(family_spec(spec), origin="seed")
        self.replies = [{"text": json.dumps({"families": []})}]
        Architect(self.store, self.router, self.settings, clock=self.clock).run()
        body = self.sail.bodies[-1]
        system, user = body["input"][0]["content"], body["input"][-1]["content"]
        self.assertIn("available roots listed in the current request", system)
        self.assertNotIn("Roots: SPY, QQQ, IWM", system)
        self.assertIn(", ".join(self.FINAL_ROOTS), user.split("\n\n", 1)[0])
        gaps = json.loads(user.split("GAPS (uncovered structure types by root; [] means all covered):\n", 1)[1])
        self.assertEqual(set(gaps), set(self.FINAL_ROOTS))
        for root in ("XSP", "SPXW"):
            self.assertFalse({"calendar", "diagonal"} & set(gaps[root]))
        for root in self.FINAL_ROOTS[5:]:
            self.assertEqual(len(gaps[root]), 11, root)
            self.assertTrue({"calendar", "diagonal", "debit_vertical"} <= set(gaps[root]), root)
        return gaps

    def test_empty_expanded_universe_prompt_exposes_every_gap_including_the_last_root(self):
        gaps = self.expanded_prompt(seeded=False)
        self.assertEqual(sum(map(len, gaps.values())), 271)

    def test_seeded_expanded_universe_prompt_preserves_all_new_roots_and_existing_coverage(self):
        gaps = self.expanded_prompt(seeded=True)
        self.assertEqual(sum(map(len, gaps.values())), 241)
        self.assertNotIn("iron_condor", gaps["SPY"])


if __name__ == "__main__":
    unittest.main()
