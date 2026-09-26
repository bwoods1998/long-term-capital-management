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
        self.slow: set[str] = set()
        self.landing: list = []
        self.cancelled: list[str] = []

    def submit(self, job):
        self.jobs.append(job)
        return job

    def wait(self, job, timeout=None, late=None):
        if job.family in self.fail:
            raise PoolError("the Gym failed")
        if job.family in self.slow:  # the round stops waiting; the result lands later
            job.late = late
            self.landing.append((job, late))
            raise PoolError("the Gym did not answer in time")
        return self.answer(job)

    def run(self, job, timeout=None, late=None):
        return self.wait(self.submit(job), timeout, late)

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

    def test_a_slow_look_is_never_started_twice_and_is_recorded_when_it_lands(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 3
        Gate(self.store, self.pool, self.router, self.settings).run()
        Gate(self.store, self.pool, self.router, self.settings).run()
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
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        self.pool.fail.clear()
        Gate(self.store, self.pool, self.router, self.settings).run()
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

    def test_without_openai_room_the_audit_is_recorded_as_the_sail_reviewer(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.sail.bodies), 1, "no second Sail call")
        review = self.store.family("a")["state"]["review"]
        self.assertEqual(review["audit"]["route"], "sail-reviewer")
        events = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["payload"].get("action") == "review"]
        self.assertTrue(events[0]["not_the_plans_reviewer"])
        self.assertEqual(len(self.store.looks()), 1)

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

    def test_no_gate_image_no_look_but_the_review_runs_and_is_kept(self):
        from league.swarm import bands

        self.ready()
        self.settings["gym"]["gate_checkpoint"] = None
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
        out = Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(out["waiting"], ["a"])
        self.assertEqual(self.store.looks(), [])
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["a"], "reviewed and waiting: tuition may run it")
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(len(self.sail.bodies), 1, "the review is not asked twice")
        self.assertEqual(len(self.store.looks()), 1)

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

    def test_a_failed_nightly_replay_keeps_the_record(self):
        self.ready()
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
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
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.store.add_forward("a", "shadow", [{"id": f"old{i}", "day": f"d{i}", "pnl": -4.0, "max_loss": 60.0, "version": 0}
                                                for i in range(22)])
        self.assertIsNone(Gate(self.store, self.pool, self.router, self.settings).judge_forward("a"),
                          "another version's trades never judge this one")
        self.assertEqual(self.store.family("a")["band"], "candidate")

    def test_a_look_never_undoes_a_newer_validation(self):
        self.ready()
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}]
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

    def test_a_proposal_on_a_retired_familys_slice_continues_its_lineage(self):
        old = self.family("fly", structure="iron_butterfly", roots=["SPY"])
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

    def test_every_four_hours(self):
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


if __name__ == "__main__":
    unittest.main()
