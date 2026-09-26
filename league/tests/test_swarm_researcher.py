"""The inner loop (league/swarm/researcher.py) over the real Provider with a scripted Sail and a fake Gym."""

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.models import ModelRouter
from league.swarm.pool import PoolError
from league.swarm.researcher import Researcher, needs_of, sanitize
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, provider, result

GYM = importlib.util.find_spec("league.gym") is not None


class FakePool:
    def __init__(self, answer=None, fail=None):
        self.jobs = []
        self.answer = answer or (lambda job: result(job.name, roots=job.roots))
        self.fail = fail

    def run(self, job, timeout=None, late=None):
        self.jobs.append(job)
        if self.fail == "late":  # the researcher stops waiting; the Gym's result lands after
            self.late = (late, self.answer(job))
            raise PoolError("the Gym did not answer in time")
        if self.fail:
            raise PoolError(self.fail)
        return self.answer(job)


def calls_in(body, kind="function_call_output"):
    return [i for i in body.get("input", []) if isinstance(i, dict) and i.get("type") == kind]


class ResearcherCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.root = Path(self.dir.name)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.steps: list = []
        self.provider, self.sail = provider(self.root / "p.sqlite", self.script)
        self.addCleanup(self.provider.close)
        self.router = ModelRouter(self.store, self.provider, settings=self.settings)
        self.pool = FakePool()
        self.spec = next(s for s in SEEDS if s["id"] == "condor-vrp")
        self.fam = self.store.add_family(family_spec(self.spec), origin="seed")
        self.code, _ = program_for(self.spec)

    def script(self, body):
        step = self.steps.pop(0) if self.steps else {"text": "done"}
        return step(body) if callable(step) else step

    def researcher(self):
        return Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, starter=program_for, background=False)


class FirstCycle(ResearcherCase):
    def test_the_starter_runs_without_a_model_call(self):
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out.get("starter"), out)
        self.assertEqual(self.sail.bodies, [])
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 1)
        self.assertEqual(self.store.family(self.fam["id"])["best_version"], 1)
        [cycle] = self.store.convo(self.fam["id"])[0]
        self.assertIn("```python", cycle["items"][0]["content"])
        self.assertEqual([e["kind"] for e in self.store.events_after(0)], ["swarm.cycle"])
        self.assertEqual(self.pool.jobs[0].window, "train")


class ModelCycles(ResearcherCase):
    def run_first(self):
        self.researcher().cycle(self.fam["id"])

    def test_revise_run_read_note_submit(self):
        self.run_first()
        better = self.code.replace('"entry_delta"', '"entry_delta"')  # same shape, a new version by params
        self.steps = [{"calls": [("gym_run", {"code": better, "params": {"vrp_min": 1.4}, "why": "fewer, richer entries"})]},
                      lambda body: {"calls": [("notebook", {"action": "append", "text": "Richer entries cut the trade count."}),
                                              ("submit", {"run_id": json.loads(calls_in(body)[-1]["output"])["run_id"], "note": "best"})]},
                      {"text": "Next I will widen the wings."}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertNotIn("error", out)
        self.assertEqual(out["model_calls"], 3)
        self.assertEqual(out["tool_calls"], 3)
        self.assertGreater(out["cost_usd"], 0)
        fam = self.store.family(self.fam["id"])
        self.assertEqual((fam["revisions"], fam["best_version"], fam["trials"]), (2, 2, 2))
        self.assertEqual(self.store.notebook(self.fam["id"])[-1]["text"], "Richer entries cut the trade count.")
        first = self.sail.bodies[0]
        self.assertEqual(first["prompt_cache_key"], f"swarm-{self.fam['id']}")
        self.assertIn("THE CONTRACT", first["input"][0]["content"])
        self.assertEqual(([t["name"] for t in first["tools"]], first["tool_choice"]), (["gym_run", "retire"], "required"),
                         "the revise turn takes an explicit research action")
        second = self.sail.bodies[1]
        self.assertEqual(([t["name"] for t in second["tools"]], second["tool_choice"]),
                         (["gym_run", "read_run", "notebook", "graveyard", "submit", "retire"], "auto"), "the read turn has every tool")
        self.assertEqual(first["reasoning"]["effort"], "minimal")
        self.assertEqual(first["model"], "deepseek-ai/DeepSeek-V4-Flash-0731")
        self.assertEqual(self.store.spent(["sail_model"]) > 0, True)

    def test_a_second_run_waits_for_the_next_cycle_and_starts_it(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"code": self.code, "params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_run", {"code": self.code, "params": {"vrp_min": 1.5}})]}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out["pending_run"])
        self.assertEqual(len(self.pool.jobs), 2)
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 3, "the carried run ran first")
        self.assertEqual(self.pool.jobs[-1].params, {"vrp_min": 1.5})
        body = self.sail.bodies[-1]
        outputs = {i["call_id"] for i in calls_in(body)}
        calls = {i["call_id"] for i in calls_in(body, "function_call")}
        self.assertEqual(outputs, calls, "every call in the history has its output")
        self.assertFalse(any(i.get("type") == "reasoning" for i in body["input"]))

    def test_another_root_is_another_family(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"code": self.code.replace("'roots': ['SPY']", "'roots': ['QQQ']")})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 1)
        output = json.loads(calls_in(self.sail.bodies[-1])[-1]["output"])
        self.assertEqual(output["status"], "refused")
        self.assertIn("another family", output["reason"])
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 1)

    def test_a_date_in_the_parameter_overrides_is_refused_before_the_gym(self):
        self.run_first()
        for bad in ({"vrp_min": 2025}, {"vrp_min": 20250102}, {"vrp_min": 2025.0}):
            self.steps = [{"calls": [("gym_run", {"params": bad})]}, {"text": "ok"}]
            self.researcher().cycle(self.fam["id"])
            self.assertIn("date", json.loads(calls_in(self.sail.bodies[-1])[-1]["output"])["reason"].lower())
        self.assertEqual(len(self.pool.jobs), 1, "none reached the Gym")

    def test_a_refused_input_stays_in_revise_until_a_run_completes(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 2025}})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required", "required", "auto"])
        self.assertEqual(len(self.pool.jobs), 2, "the refused input consumed no run; the repair ran once")
        self.assertEqual((out["trials"], self.store.family(self.fam["id"])["trials"]), (1, 2))
        self.assertNotIn("error", out)

    def test_a_queued_refusal_is_reported_truthfully_and_revised(self):
        self.run_first()
        cycles, _ = self.store.convo(self.fam["id"])
        self.store.save_convo(self.fam["id"], cycles, {"call_id": "queued-bad", "author": "synthetic",
                                                    "arguments": {"params": {"vrp_min": 2025}}})
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fam["id"])
        first = self.sail.bodies[0]
        self.assertEqual(first["tool_choice"], "required")
        context = json.dumps(first["input"])
        self.assertIn("queued last cycle did not complete a Gym run", context)
        self.assertIn("a date or a year", context)
        self.assertNotIn("queued last cycle ran:", context)
        self.assertEqual((len(self.pool.jobs), out["trials"]), (2, 1))
        self.assertIsNone(self.store.convo(self.fam["id"])[1])
        self.assertNotIn("error", out)

    def test_a_refused_stronger_rewrite_needs_repair_before_read(self):
        self.run_first()
        cycles, _ = self.store.convo(self.fam["id"])
        self.store.save_convo(self.fam["id"], cycles, {"call_id": "old-queued", "author": "synthetic",
                                                    "arguments": {"params": {"vrp_min": 1.5}}})
        self.store.set_state(self.fam["id"], rewrite_ready={"code": "def decide(:", "profile": "pro_asap"})
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required", "auto"])
        self.assertEqual(len(self.pool.jobs), 2, "the rewrite supersedes the old queued input even when refused")
        self.assertEqual(self.pool.jobs[-1].params, {"vrp_min": 1.3})
        self.assertEqual(out["trials"], 1)

    def test_an_unsuccessful_gym_evaluation_keeps_the_one_run_budget_and_revises(self):
        self.run_first()
        self.pool.answer = lambda job: result(job.name, status="failed", roots=job.roots)
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.5}})]}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required", "required"])
        self.assertEqual((len(self.pool.jobs), out["trials"]), (2, 1), "failed evidence still counts exactly once")
        self.assertTrue(out["pending_run"], "the repair runs next cycle, within the existing one-run limit")

    def test_an_ambiguous_rewrite_run_does_not_dispatch_a_second_run(self):
        self.run_first()
        self.store.set_state(self.fam["id"], rewrite_ready={"code": self.code, "profile": "pro_asap"})
        self.pool.fail = "late"
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(self.sail.bodies[0]["tool_choice"], "required")
        self.assertEqual(len(self.pool.jobs), 2, "the uncertain rewrite still consumes the cycle's dispatch")
        self.assertTrue(out["pending_run"])
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 1)
        callback, landed = self.pool.late
        callback(landed)
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 2, "late evidence keeps its original count")

    def test_a_required_reply_without_a_tool_is_a_bounded_failure_with_backoff(self):
        from league.swarm.loop import Scheduler

        self.run_first()
        self.steps = [{"text": "no experiment"}, {"calls": [("gym_run", {})]}]
        researcher = self.researcher()
        scheduler = Scheduler(self.store, clock=self.clock)
        self.assertEqual(scheduler.take(), self.fam["id"])
        out = researcher.cycle(self.fam["id"])
        self.assertEqual((out["model_calls"], out["tool_calls"], len(self.pool.jobs)), (1, 0, 1))
        self.assertIn("required research action returned no tool call", out["error"])
        self.assertEqual(out["protocol_error"], "required research action returned no tool call")
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 1)
        self.assertEqual(len(self.steps), 1, "no unbounded model retry")
        self.assertEqual(self.store.convo(self.fam["id"])[0][-1]["cycle"], 2, "the failed response remains auditable")
        scheduler.release(self.fam["id"], out)
        self.clock.advance(5)
        self.assertIsNone(scheduler.take(), "a protocol failure uses the existing error cooldown")

    def test_rewrites_are_asap_on_their_own_small_fuse_and_wait_for_the_pace(self):
        self.run_first()
        self.assertEqual(self.settings["researcher"]["rewrite_profile"], "pro_asap")
        self.store.update_family(self.fam["id"], stall=5)
        r = self.researcher()
        r.pace = lambda: True  # over the swarm's hourly pace: no rewrite now
        self.steps = [{"text": "ok"}]
        out = r.cycle(self.fam["id"])
        self.assertNotIn("rewrite_asked", out)
        r.pace = lambda: False
        self.steps = [{"text": "```python\n" + self.code + "\n```"}, {"text": "ok"}]
        r.cycle(self.fam["id"])
        body = self.sail.bodies[-2]
        self.assertEqual(body["model"], "deepseek-ai/DeepSeek-V4-Pro-0813")
        import sqlite3

        db = sqlite3.connect(str(self.provider.path))
        desks = {row[0] for row in db.execute("SELECT desk_id FROM requests")}
        db.close()
        self.assertIn(f"{self.fam['id']}:rewrite", desks, "the rewrite has its own fuse")

    @unittest.skipUnless(GYM, "the Gym's safety check")
    def test_a_date_literal_is_refused_before_the_gym(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"code": self.code + "\nYEAR = 2025\n"})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertIn("date", json.loads(calls_in(self.sail.bodies[-1])[-1]["output"])["reason"].lower())

    def test_read_run_sees_only_its_own_train_runs(self):
        self.run_first()
        other = self.store.add_family({**family_spec(self.spec), "id": "other"}, origin="seed")
        theirs = self.store.add_run(other["id"], 1, result("x"), window="train", stress=1.0, purpose="train")
        mine = self.store.runs(self.fam["id"])[0]
        self.steps = [{"calls": [("read_run", {"run_id": theirs["run_id"], "section": "trades"}),
                                 ("read_run", {"run_id": mine["run_id"], "section": "trades", "page": 0})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        outs = [json.loads(o["output"]) for o in calls_in(self.sail.bodies[-1])]
        self.assertEqual(outs[0], {"error": "no such Train run of your family"})
        self.assertIn("trades", outs[1])

    def test_a_gym_failure_keeps_the_version_and_says_so(self):
        self.run_first()
        self.pool.fail = "the Gym did not answer"
        self.steps = [{"calls": [("gym_run", {"code": self.code, "params": {"vrp_min": 1.3}})]}, {"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertIn("gym_error", out)
        self.assertEqual(self.store.family(self.fam["id"])["revisions"], 2)

    def test_a_runs_note_goes_to_the_notebook(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}, "note": "entries were too rare"})]}, {"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(out["note"], "entries were too rare")
        self.assertEqual(self.store.notebook(self.fam["id"])[-1]["text"], "entries were too rare")
        self.assertEqual(self.pool.jobs[-1].params, {"vrp_min": 1.3}, "no code: the latest version with new params")

    def test_a_queued_run_the_gym_cannot_run_costs_no_model_call_and_stays_queued(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"calls": [("gym_run", {"params": {"vrp_min": 1.5}})]}]
        self.researcher().cycle(self.fam["id"])
        calls = len(self.sail.bodies)
        self.pool.fail = "the Gym did not answer"
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.sail.bodies), calls, "no model paid to read a Gym error")
        self.assertIn("gym:", out["error"])
        self.assertTrue(self.store.convo(self.fam["id"])[1], "the run stays queued")
        self.pool.fail = None
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(self.pool.jobs[-1].params, {"vrp_min": 1.5})

    def queue_one(self):
        self.run_first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"calls": [("gym_run", {"params": {"vrp_min": 1.5}})]}]
        self.researcher().cycle(self.fam["id"])
        return len(self.sail.bodies)

    def test_a_queued_run_is_retried_twice_on_a_transient_error_then_the_model_hears_why(self):
        calls = self.queue_one()
        self.pool.fail = "the Gym did not answer within 1020 s (queue 3)"
        for _ in range(2):
            self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.sail.bodies), calls, "two quiet retries")
        self.steps = [{"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.sail.bodies), calls + 1, "the third failure goes to the model")
        self.assertIn("did not answer", json.dumps(self.sail.bodies[-1]["input"]))
        self.assertIsNone(self.store.convo(self.fam["id"])[1], "no longer queued")
        self.assertIn("gym:", out["error"])

    def test_a_queued_run_the_gym_refuses_is_not_retried(self):
        calls = self.queue_one()
        self.pool.fail = "the Gym has no train data for QQQ yet (it holds SPY)"
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(len(self.sail.bodies), calls + 1, "the model hears it at once")
        self.assertIn("no train data", json.dumps(self.sail.bodies[-1]["input"]))
        self.assertIsNone(self.store.convo(self.fam["id"])[1])

    def test_a_stalled_family_still_asks_for_its_rewrite_while_its_run_waits(self):
        self.queue_one()
        self.store.update_family(self.fam["id"], stall=5)
        self.pool.fail = "the Gym did not answer within 1020 s (queue 3)"
        self.steps = [{"text": "```python\n" + self.code + "\n```"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(out.get("rewrite_asked"), "pro_asap", out)

    def test_a_run_that_lands_after_the_researcher_gave_up_is_still_a_trial(self):
        self.run_first()
        self.pool.fail = "late"
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 1)
        late, landed = self.pool.late
        late(landed)
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 2)

    def test_notes_reach_the_tape_at_most_every_few_cycles(self):
        self.run_first()
        for i in range(3):
            self.steps = [{"calls": [("notebook", {"action": "append", "text": f"lesson {'abc'[i]} learned"})]}, {"text": "ok"}]
            self.researcher().cycle(self.fam["id"])
        notes = [e for e in self.store.events_after(0) if e["kind"] == "swarm.note"]
        self.assertEqual([n["payload"]["text"] for n in notes], ["lesson a learned"])

    def test_the_status_shows_validation_only_as_mean_t_quarters_and_the_line(self):
        self.run_first()
        self.store.set_state(self.fam["id"], validation_view={"mean_return_on_max_loss": 0.01, "t": 1.2, "quarters_positive": "2/4",
                                                             "line_met": False, "checks_not_met": ["t"]}, gate="fail")
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        status = self.sail.bodies[-1]["input"][-1]["content"]
        self.assertIn('"t": 1.2', status)
        self.assertIn("The gate's last answer: fail.", status)

    def test_a_stall_buys_one_rewrite_from_a_stronger_model_asked_in_the_background(self):
        self.run_first()
        self.store.update_family(self.fam["id"], stall=5)
        self.steps = [{"text": "Here it is:\n```python\n" + self.code.replace("'vrp_min': 1.2", "'vrp_min': 1.25") + "\n```\nWider."},
                      {"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(out.get("rewrite_asked"), "pro_asap", out)
        self.assertEqual(self.sail.bodies[0]["model"], "deepseek-ai/DeepSeek-V4-Pro-0813")
        fam = self.store.family(self.fam["id"])
        self.assertEqual((fam["rewrites"], fam["stall"]), (1, 0))
        self.assertTrue(fam["state"]["rewrite_ready"]["code"])
        self.steps = [{"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(out.get("rewrite"), "pro_asap", "the rewrite is the next cycle's run")
        self.assertEqual(self.store.latest_version(self.fam["id"])["author"], "pro_asap")
        self.assertIsNone(self.store.family(self.fam["id"])["state"]["rewrite_ready"])

    def test_rewrites_are_spaced_and_capped(self):
        self.run_first()
        r = self.researcher()
        for _ in range(2):
            self.store.update_family(self.fam["id"], stall=5)
            self.steps = [{"text": "no code"}, {"text": "ok"}]
            r.cycle(self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["rewrites"], 1, "an hour apart")
        self.assertIn("no program", self.store.family(self.fam["id"])["state"]["rewrite_error"])
        for _ in range(6):
            self.clock.advance(3601)
            self.store.update_family(self.fam["id"], stall=5)
            self.steps = [{"text": "no code"}, {"text": "ok"}]
            r.cycle(self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["rewrites"], 4, "four a day")

    def test_a_top_ten_family_stalls_into_kimi(self):
        self.run_first()
        for i in range(3):
            other = self.store.add_family({**family_spec(self.spec), "id": f"other-{i}"}, origin="seed")
            self.store.update_family(other["id"], weight=0.01)
        self.store.update_family(self.fam["id"], stall=5, weight=0.5)
        self.settings["researcher"]["top_rewrite_families"] = 1
        self.steps = [{"text": "```python\n" + self.code + "\n```"}, {"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(out.get("rewrite_asked"), "k3_balanced")
        self.assertEqual(self.sail.bodies[0]["model"], "moonshotai/Kimi-K3")

    def test_a_spent_budget_ends_the_cycle_quietly(self):
        self.run_first()
        self.settings["researcher"]["family_usd_day"] = 0.000001
        self.steps = [{"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertIn("budget", out["error"].lower())

    def test_a_retired_family_is_skipped(self):
        self.store.retire(self.fam["id"], "test")
        self.assertEqual(self.researcher().cycle(self.fam["id"])["skipped"], "retired")


class RateLimits(unittest.TestCase):
    def test_a_rate_limit_is_waited_out_twice_then_raised(self):
        from ltcm.provider import Provider, ProviderError

        from league.tests.swarm_fakes import ScriptedSail

        with tempfile.TemporaryDirectory() as d:
            store = SwarmStore(Path(d))
            sail = ScriptedSail(lambda body: {"text": "ok"})
            fails = {"n": 2}

            def transport(method, route, body=None, idempotency_key=None):
                if method == "POST" and fails["n"] > 0:
                    fails["n"] -= 1
                    raise ProviderError("provider_http_429", retry_after=1)
                return sail(method, route, body, idempotency_key)

            prov = Provider(Path(d) / "p.sqlite", transport=transport, floor_cap_usd_per_day="100")
            slept = []
            router = ModelRouter(store, prov, settings=copy.deepcopy(S.DEFAULTS), sleep=slept.append)
            response = router.sail("flash_asap", [{"role": "user", "content": "hi"}], family="f", key="k1")
            self.assertEqual((response.output_text, slept), ("ok", [1, 1]))
            fails["n"] = 3
            with self.assertRaises(ProviderError):
                router.sail("flash_asap", [{"role": "user", "content": "hi"}], family="f", key="k2")
            prov.close()
            store.close()

    def test_a_call_that_timed_out_is_booked_at_its_hold(self):
        from ltcm.provider import Provider, ProviderError

        with tempfile.TemporaryDirectory() as d:
            store = SwarmStore(Path(d))

            def transport(method, route, body=None, idempotency_key=None):
                raise ProviderError("provider_transport_timeout")  # sent; Sail may have run it and billed it

            prov = Provider(Path(d) / "p.sqlite", transport=transport, floor_cap_usd_per_day="100")
            router = ModelRouter(store, prov, settings=copy.deepcopy(S.DEFAULTS), sleep=lambda s: None)
            items = [{"role": "user", "content": "hi"}]
            with self.assertRaises(ProviderError):
                router.sail("flash_asap", items, family="f:rewrite", key="k1", max_output=8000)
            booked = store.spent(["sail_model"])
            self.assertGreater(booked, 0)
            self.assertEqual(booked, float(prov._db.execute("SELECT reserved_usd FROM requests").fetchone()[0]), "the Provider's hold")
            self.assertEqual(store._one("SELECT family FROM spend")["family"], "f", "booked to the family, not its role's desk")

            def refuse(method, route, body=None, idempotency_key=None):
                raise ProviderError("provider_http_400", detail="bad request")  # refused outright: never billed

            prov.transport = refuse
            with self.assertRaises(ProviderError):
                router.sail("flash_asap", items, family="f", key="k2")
            self.assertEqual(store.spent(["sail_model"]), booked)
            prov.close()
            store.close()


class Holds(unittest.TestCase):
    """A call that fails after it was sent is booked at its hold ONCE; its settled cost replaces the hold, never adds to it
    (S7). Sail answers the POST 'in progress' and the Provider stops polling at once (poll_timeout 0)."""

    def setUp(self):
        from ltcm.provider import Provider

        from league.tests.swarm_fakes import response_payload

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = SwarmStore(Path(self.dir.name))
        self.addCleanup(self.store.close)
        self.done = False
        self.fail_code = None
        payload = {}

        def transport(method, route, body=None, idempotency_key=None):
            from ltcm.provider import ProviderError

            if self.fail_code:
                raise ProviderError(self.fail_code)
            if method == "POST":
                payload.update(response_payload(body["model"], text="ok"))
                return {"id": payload["id"], "status": "in_progress", "model": body["model"]}
            if self.done:
                return payload
            return {"id": payload["id"], "status": "in_progress", "model": payload["model"]}

        self.prov = Provider(Path(self.dir.name) / "p.sqlite", transport=transport, floor_cap_usd_per_day="100", poll_timeout=0,
                             sleep=lambda s: None)
        self.addCleanup(self.prov.close)
        self.router = ModelRouter(self.store, self.prov, settings=copy.deepcopy(S.DEFAULTS), sleep=lambda s: None)
        self.items = [{"role": "user", "content": "hi"}]

    def ask(self, key="k1"):
        return self.router.sail("k3_balanced", self.items, family="f:audit", key=key, max_output=6000)

    def cost(self):
        return float(self.prov._db.execute("SELECT cost_usd FROM requests").fetchone()[0])

    def test_a_timed_out_call_asked_again_books_its_cost_not_its_hold_and_its_cost(self):
        from ltcm.provider import ProviderError

        for _ in range(3):  # three rounds while it is still running: one hold
            with self.assertRaises(ProviderError):
                self.ask()
        hold = float(self.prov._db.execute("SELECT reserved_usd FROM requests").fetchone()[0])
        self.assertAlmostEqual(self.store.spent(["sail_model"]), hold, places=6)
        self.done = True
        self.ask()
        self.assertAlmostEqual(self.store.spent(["sail_model"]), self.cost(), places=6)

    def test_a_hold_the_provider_settles_or_releases_later_is_trued_up(self):
        from ltcm.provider import ProviderError

        with self.assertRaises(ProviderError):
            self.ask("k1")
        with self.assertRaises(ProviderError):
            self.ask("k2")
        self.done = True
        self.prov.reconcile_stale(now=time.time() + 3600)  # the loop's sweep: both settle
        self.router.settle_holds()
        costs = sum(float(r[0]) for r in self.prov._db.execute("SELECT cost_usd FROM requests"))
        self.assertAlmostEqual(self.store.spent(["sail_model"]), costs, places=6)
        self.assertEqual(self.store.get("unsettled") or {}, {})

    def test_a_released_hold_is_reversed(self):
        from ltcm.provider import ProviderError

        self.fail_code = "provider_transport_timeout"  # the POST's answer was lost: Sail may or may not have it
        with self.assertRaises(ProviderError):
            self.ask()
        self.assertGreater(self.store.spent(["sail_model"]), 0)
        self.prov.reconcile_stale(now=time.time() + 3600)  # never accepted: the Provider releases its hold
        self.assertEqual(self.prov._db.execute("SELECT status FROM requests").fetchone()[0], "abandoned")
        self.router.settle_holds()
        self.assertAlmostEqual(self.store.spent(["sail_model"]), 0.0, places=9)

    def test_a_server_error_nothing_accepted_books_nothing(self):
        from ltcm.provider import ProviderError

        self.fail_code = "provider_http_503"
        with self.assertRaises(ProviderError):
            self.ask()
        self.assertEqual(self.store.spent(["sail_model"]), 0.0)


class Compaction(ResearcherCase):
    def test_old_conversations_leave_the_providers_file_and_costs_stay(self):
        import sqlite3

        self.router.sail("flash_asap", [{"role": "user", "content": "x" * 5000}], family="f", key="old")
        db = sqlite3.connect(str(self.provider.path))
        db.execute("UPDATE requests SET updated_at='2020-01-01T00:00:00'")
        db.commit()
        self.assertEqual(self.router.compact(), 1)
        body, response, cost = db.execute("SELECT body, response, cost_usd FROM requests").fetchone()
        self.assertEqual((body, response), ("{}", None))
        self.assertIsNotNone(cost)
        self.assertEqual(self.router.compact(), 0)
        self.assertGreater(float(self.provider.spent_today("f")), 0)
        db.close()


class History(ResearcherCase):
    def test_history_is_cut_in_chunks_and_old_outputs_shortened(self):
        r = self.researcher()
        cycles = [{"cycle": i, "items": [{"type": "function_call", "call_id": f"c{i}", "name": "gym_run", "arguments": "{}"},
                                         {"type": "function_call_output", "call_id": f"c{i}", "output": "x" * 9000}]} for i in range(4)]
        kept = r.trim(cycles)
        self.assertEqual([c["cycle"] for c in kept], [0, 1, 2, 3], "up to four kept whole")
        self.assertTrue(all(len(c["items"][1]["output"]) < 3000 for c in kept[:-1]))
        self.assertEqual(len(kept[-1]["items"][1]["output"]), 9000, "the last cycle whole")
        self.assertEqual([c["cycle"] for c in r.trim(cycles + [{"cycle": 4, "items": []}])], [3, 4], "then cut back to two at once")


class Helpers(unittest.TestCase):
    def test_needs_of_reads_the_literal(self):
        self.assertEqual(needs_of('NEEDS = {"roots": ["SPY"]}\n'), {"roots": ["SPY"]})
        self.assertIsNone(needs_of("NEEDS = make()\n"))
        self.assertIsNone(needs_of("def ("))

    def test_sanitize_drops_orphans_and_reasoning(self):
        items = [{"type": "reasoning", "content": "x"}, {"type": "function_call", "call_id": "a", "name": "n", "arguments": "{}", "id": "fc"},
                 {"type": "function_call_output", "call_id": "b", "output": "{}"}, {"role": "user", "content": "hi"}]
        self.assertEqual(sanitize(items), [{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
