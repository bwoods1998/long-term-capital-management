"""The inner loop (league/swarm/researcher.py) over the real Provider with a scripted Sail and a fake Gym."""

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
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

    def run(self, job, timeout=None):
        self.jobs.append(job)
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
        return Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, starter=program_for)


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
        self.assertEqual([t["name"] for t in first["tools"]], ["gym_run", "read_run", "notebook", "graveyard", "submit"])
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

    def test_notes_reach_the_tape_at_most_every_few_cycles(self):
        self.run_first()
        for i in range(3):
            self.steps = [{"calls": [("notebook", {"action": "append", "text": f"lesson {i}"})]}, {"text": "ok"}]
            self.researcher().cycle(self.fam["id"])
        notes = [e for e in self.store.events_after(0) if e["kind"] == "swarm.note"]
        self.assertEqual([n["payload"]["text"] for n in notes], ["lesson 0"])

    def test_the_status_shows_validation_only_as_mean_t_quarters_and_the_line(self):
        self.run_first()
        self.store.set_state(self.fam["id"], validation_view={"mean_return_on_max_loss": 0.01, "t": 1.2, "quarters_positive": "2/4",
                                                             "line_met": False, "checks_not_met": ["t"]}, gate="fail")
        self.steps = [{"text": "ok"}]
        self.researcher().cycle(self.fam["id"])
        status = self.sail.bodies[-1]["input"][-1]["content"]
        self.assertIn('"t": 1.2', status)
        self.assertIn("The gate's last answer: fail.", status)

    def test_a_stall_buys_one_rewrite_from_a_stronger_model(self):
        self.run_first()
        self.store.update_family(self.fam["id"], stall=5)
        self.steps = [{"text": "Here it is:\n```python\n" + self.code.replace("vrp_min\": 1.2", "vrp_min\": 1.25") + "\n```\nWider."},
                      {"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertEqual(out.get("rewrite"), "pro_balanced", out)
        self.assertEqual(self.sail.bodies[0]["model"], "deepseek-ai/DeepSeek-V4-Pro-0813")
        fam = self.store.family(self.fam["id"])
        self.assertEqual(fam["rewrites"], 1)
        self.assertEqual(self.store.latest_version(self.fam["id"])["author"], "pro_balanced")

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
