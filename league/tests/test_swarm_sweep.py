"""`gym_sweep` (league/swarm/researcher.py, R3): many PARAMS variants of one program in one call. Every variant is its own
version, its own Train run and a trial; the sweep is one revision; its jobs share the pool's batches and never supersede one
another; a failed variant costs the others nothing; the REVISE turn still requires a run or a sweep. Synthetic programs,
parameters and results only (a fake Gym)."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.pool import Box, GymJob, GymPool, PoolError
from league.swarm.researcher import Researcher, sweep_tool, sweep_variants
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeDriver, FakeSail, result
from league.tests.test_swarm_researcher import ResearcherCase, calls_in

YEARS = ("y1", "y2", "y3")  # the Train years of a synthetic result (labels only)


def by_year(t: float, *, trades: int = 60, days: int = 30) -> dict:
    """A synthetic per-year block: the same daily t, trades and traded days every Train year, all quarters positive."""
    return {y: {"trades": trades, "days_traded": days, "pnl": 100.0 * t, "t_daily": t,
                "quarter_pnl": {"q1": 5.0, "q2": 5.0, "q3": 5.0, "q4": 5.0}} for y in YEARS}


def scored(job: GymJob, t_of=None) -> dict:
    """A Train result whose Train score follows the job's `vrp_min` (a synthetic surface); `max_open` 1 is too sparse to be
    eligible."""
    r = result(job.name, roots=job.roots)
    params = job.params or {}
    t = (t_of or (lambda p: 3.0 - 5.0 * abs(float(p.get("vrp_min", 1.2)) - 1.4)))(params)
    r["by_year"] = by_year(t, trades=10 if params.get("max_open") == 1 else 60)
    r["params"] = dict(params)
    return r


class SweepPool:
    """The real pool's interface (submit, then wait) with scripted answers: `fail(job)` gives a PoolError's words, "late"
    (the waiter gives up; the result lands after), or None."""

    def __init__(self, answer=None, fail=None):
        self.jobs: list[GymJob] = []
        self.timeouts: list = []
        self.answer = answer or scored
        self.fail = fail or (lambda job: None)
        self.lates: list = []

    def submit(self, job):
        self.jobs.append(job)
        return job

    def wait(self, job, timeout=None, *, late=None, late_fail=None):
        self.timeouts.append(timeout)
        why = self.fail(job)
        if why == "late":
            self.lates.append((late, self.answer(job)))
            raise PoolError(f"the Gym did not answer within {timeout:.0f} s (queue 3)")
        if why:
            raise PoolError(why)
        return self.answer(job)

    def run(self, job, timeout=None, late=None):
        return self.wait(self.submit(job), timeout, late=late)

    def train(self):
        return [j for j in self.jobs if j.purpose == "train"]


class SweepCase(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.pool = SweepPool()
        self.fid = self.fam["id"]

    def first(self):
        self.researcher().cycle(self.fid)  # the starter program: version 1, one trial

    def sweep(self, variants, **args):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._gym_sweep(self.store.family(self.fid), {"variants": variants, **args}, out, author="synthetic")
        return view, out


class Store(SweepCase):
    def test_variants_are_versions_sharing_one_code_file_and_one_revision(self):
        before = self.store.family(self.fid)["revisions"]
        versions = self.store.add_versions(self.fid, self.code, [{"vrp_min": 1.3}, {"vrp_min": 1.5}, {}], author="synthetic")
        self.assertEqual([v["n"] for v in versions], [1, 2, 3])
        self.assertEqual([v["params"] for v in versions], [{"vrp_min": 1.3}, {"vrp_min": 1.5}, {}])
        self.assertEqual({v["path"] for v in versions}, {versions[0]["path"]}, "the code is stored once")
        self.assertTrue(all(v["code"] == self.code for v in versions))
        fam = self.store.family(self.fid)
        self.assertEqual((fam["revisions"] - before, fam["stall"], fam["since_val_revisions"]), (1, 1, 1))
        again = self.store.add_versions(self.fid, self.code, [{"vrp_min": 1.5}, {"vrp_min": 1.6}], author="synthetic")
        self.assertEqual([v["n"] for v in again], [2, 4], "a known variant is its version; a new one shares the file")
        self.assertEqual(again[1]["path"], versions[0]["path"])
        self.assertEqual(self.store.family(self.fid)["revisions"] - before, 2)
        same = self.store.add_versions(self.fid, self.code, [{"vrp_min": 1.3}], author="synthetic")
        self.assertEqual(([v["n"] for v in same], self.store.family(self.fid)["revisions"] - before), ([1], 2),
                         "nothing new: no revision")


class Pool(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["gym"].update({"enabled": True, "image_checkpoint": "sbcp_11111111-aaaa", "batch_programs": 5,
                                     "batch_wait_seconds": 8})

    def job(self, family="f", group=None):
        return GymJob(family=family, version=1, code="NEEDS = {}", params={}, window="train", roots=("SPY",), group=group)

    def test_a_sweeps_jobs_never_supersede_one_another_and_a_later_run_supersedes_them_all(self):
        pool = GymPool(self.store, FakeSail(), self.settings, clock=self.clock, threaded=False)
        mine = [pool.submit(self.job(group="f:sweep:a")) for _ in range(3)]
        other = pool.submit(self.job("g"))
        self.assertEqual(pool.queued(), 4, "three variants and another family's run")
        box = Box("sb_00000001-ffff-ffff-ffff-ffffffffffff", "gym", "sbcp_11111111-aaaa", "ready",
                  driver=FakeDriver(None, "x"), roots=("SPY",), last_used=self.clock())
        pool.boxes[box.id] = box
        self.clock.advance(9)
        self.assertEqual(len(pool._take(box)), 4, "they ride one batch")
        again = [pool.submit(self.job(group="f:sweep:b")) for _ in range(2)]
        run = pool.submit(self.job())
        for j in again:
            with self.assertRaises(PoolError):
                pool.wait(j, 0)
        self.assertFalse(run.done.is_set())
        self.assertFalse(any(j.done.is_set() for j in mine + [other]))

class RealPool(SweepCase):
    def test_a_sweep_on_the_real_pool_is_one_batch_and_every_variant_lands(self):
        calls: list = []

        def answer(name, code, params, window, stress, roots):
            out = scored(GymJob(family="x", version=1, code=code, params=params, window=window, roots=tuple(roots)))
            out["program"] = name
            return out

        self.settings["gym"].update({"enabled": True, "image_checkpoint": "sbcp_11111111-aaaa", "batch_programs": 5,
                                     "batch_wait_seconds": 8})
        self.pool = GymPool(self.store, FakeSail(), self.settings, clock=self.clock, threaded=True,
                            driver_factory=lambda client, box: FakeDriver(client, box, answer=answer, calls=calls))
        self.addCleanup(self.pool.stop, join_seconds=1)
        box = Box("sb_00000001-ffff-ffff-ffff-ffffffffffff", "gym", "sbcp_11111111-aaaa", "ready",
                  driver=FakeDriver(None, "x", answer=answer, calls=calls), roots=("SPY", "QQQ"), last_used=self.clock())
        self.pool.boxes[box.id] = box
        self.pool._spawn(box)  # its dispatcher: a short batch waits for company on the frozen clock, a full one goes
        view, out = self.sweep([{"vrp_min": v} for v in (1.2, 1.3, 1.4, 1.5, 1.6)], code=self.code)
        self.assertEqual(view["status"], "ok", view)
        self.assertEqual(len(calls), 1, "the pool ran the five variants as one day-major batch: none superseded another")
        self.assertEqual(len(calls[0]["programs"]), 5)
        self.assertEqual((view["completed"], len(view["table"]), out["trials"]), (5, 5, 5))
        self.assertEqual(self.store.family(self.fid)["trials"], 5)
        self.assertEqual(len(self.store.runs(self.fid, window="train")), 5)


class Sweeps(SweepCase):
    def test_a_sweep_of_n_variants_makes_n_versions_n_runs_and_n_trials_and_one_revision(self):
        self.first()
        fam = self.store.family(self.fid)
        values = (1.2, 1.3, 1.4, 1.5)
        view, out = self.sweep([{"vrp_min": v} for v in values], why="a grid around the entry filter")
        self.assertEqual(view["status"], "ok")
        jobs = self.pool.train()[1:]
        self.assertEqual(len(jobs), 4)
        self.assertEqual(len({j.group for j in jobs}), 1, "one group: the pool batches them together")
        self.assertTrue(all(j.window == "train" and j.stress == 1.0 and j.purpose == "train" and j.roots == ("SPY",) for j in jobs))
        self.assertEqual(self.pool.timeouts, [1020.0] * 5, "gym_run's timeout policy")
        after = self.store.family(self.fid)
        self.assertEqual(after["trials"] - fam["trials"], 4, "every variant is a trial")
        self.assertEqual(out["trials"], 4)
        self.assertEqual(after["revisions"] - fam["revisions"], 1, "the sweep is one revision")
        runs = [r for r in self.store.runs(self.fid, window="train") if r["summary"].get("sweep")]
        self.assertEqual(len(runs), 4)
        self.assertEqual(sorted(r["summary"]["params"]["vrp_min"] for r in runs), list(values), "params per run")
        for r in runs:
            self.assertEqual(self.store.version(self.fid, r["version"])["params"], r["summary"]["params"],
                             "the run's version holds exactly the params it ran")
        scores = [row["score"] for row in view["table"]]
        self.assertEqual(scores, sorted(scores, reverse=True), "sorted by the Train score")
        top = view["table"][0]
        self.assertEqual(top["params"], {"vrp_min": 1.4})
        for key in ("run_id", "version", "trades", "days", "pnl", "fill_rate", "eligible", "score", "years"):
            self.assertIn(key, top)
        self.assertEqual(set(top["years"]), set(YEARS))
        self.assertEqual(top["years"]["y1"], {"t": 3.0, "trades": 60})
        self.assertEqual(view["run_id"], top["run_id"])
        self.assertEqual(after["state"]["best_train_run"], top["run_id"])
        self.assertEqual(after["state"]["best_train_version"], top["version"])
        self.assertEqual(view["new_best_train_score"], 3.0)
        self.assertTrue(out["improved"])
        self.assertEqual(after["stall"], 0)
        robust = [j for j in self.pool.jobs if j.purpose == "robustness" and j.version == top["version"]]
        self.assertEqual(sorted(j.stress for j in robust), [0.0, 1.5], "the new best's robustness runs are queued")
        self.assertTrue(all(j.params == {"vrp_min": 1.4} for j in robust), "robustness runs the variant's own params")
        self.assertEqual([c[1] for c in after["state"]["train_candidates"]][:3], [r["version"] for r in view["table"][:3]])
        self.assertNotIn("vrp_min", json.dumps(out), "no params in the cycle's event")

    def test_a_submitted_variant_is_validated_with_its_own_params(self):
        self.first()
        view, _ = self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.5}])
        row = next(r for r in view["table"] if r["params"] == {"vrp_min": 1.5})
        answer = self.researcher()._execute(self.store.family(self.fid), "submit", {"run_id": row["run_id"]}, {}, author="synthetic")
        self.assertTrue(answer.get("ok"), answer)
        best = self.store.version(self.fid, self.store.family(self.fid)["best_version"])
        self.assertEqual((best["n"], best["params"]), (row["version"], {"vrp_min": 1.5}))

    def test_failures_of_some_variants_do_not_lose_the_others(self):
        self.first()
        self.pool.fail = lambda job: {1.3: "the Gym failed twice: exec 503", 1.5: "late"}.get(job.params.get("vrp_min"))
        fam = self.store.family(self.fid)
        view, out = self.sweep([{"vrp_min": v} for v in (1.2, 1.3, 1.4, 1.5)])
        self.assertEqual(view["status"], "ok")
        self.assertEqual((view["completed"], len(view["table"]), out["sweep"]["failed"]), (2, 2, 2))
        self.assertEqual(sorted(f["params"]["vrp_min"] for f in view["failed"]), [1.3, 1.5])
        self.assertEqual(self.store.family(self.fid)["trials"] - fam["trials"], 2, "only evaluations are trials")
        self.assertEqual(len(self.store.versions(self.fid)), 5, "every variant keeps its version")
        [(late, landed)] = self.pool.lates
        late(landed)
        self.assertEqual(self.store.family(self.fid)["trials"] - fam["trials"], 3, "a variant that lands late is still a trial")
        runs = [r for r in self.store.runs(self.fid, window="train") if r["summary"].get("sweep")]
        self.assertEqual(sorted(r["summary"]["params"]["vrp_min"] for r in runs), [1.2, 1.4, 1.5])

    def test_a_variant_the_gym_ran_and_failed_is_a_trial_and_ranks_last(self):
        self.first()
        self.pool.answer = lambda job: (result(job.name, status="error", roots=job.roots) if job.params.get("vrp_min") == 1.4
                                        else scored(job))
        fam = self.store.family(self.fid)
        view, out = self.sweep([{"vrp_min": v} for v in (1.4, 1.3)])
        self.assertEqual([r["status"] for r in view["table"]], ["ok", "error"])
        self.assertFalse(view["table"][1]["eligible"])
        self.assertEqual(self.store.family(self.fid)["trials"] - fam["trials"], 2)

    def test_a_sweep_the_gym_cannot_run_at_all_is_a_gym_error_and_keeps_its_versions(self):
        self.first()
        self.pool.fail = lambda job: "the Gym did not answer within 1020 s (queue 9)"
        view, out = self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.5}])
        self.assertEqual(view["status"], "gym_error")
        self.assertEqual(view["versions"], [2, 3])
        self.assertIn("gym_error", out)
        self.assertEqual(self.store.family(self.fid)["trials"], 1)

    def test_an_ineligible_variant_is_listed_with_why_and_never_becomes_the_best(self):
        self.first()
        view, _ = self.sweep([{"vrp_min": 1.4, "max_open": 1}, {"vrp_min": 1.3}])
        self.assertEqual([r["eligible"] for r in view["table"]], [True, False])
        self.assertIn("every Train year needs", view["table"][1]["why_not"])
        self.assertEqual(self.store.family(self.fid)["state"]["best_train_run"], view["table"][0]["run_id"])

    def test_the_base_params_are_shared_and_the_table_shows_each_variants_own(self):
        self.first()
        view, _ = self.sweep([{}, {"vrp_min": 1.5}], params={"vrp_min": 1.3, "short_delta": 0.2})
        self.assertEqual(view["base_params"], {"vrp_min": 1.3, "short_delta": 0.2})
        jobs = self.pool.train()[1:]
        self.assertEqual([j.params for j in jobs], [{"vrp_min": 1.3, "short_delta": 0.2}, {"vrp_min": 1.5, "short_delta": 0.2}])
        self.assertEqual(sorted(json.dumps(r["params"]) for r in view["table"]), ["{\"vrp_min\": 1.5}", "{}"])

    def test_code_omitted_sweeps_the_latest_versions_code(self):
        self.first()
        latest = self.store.latest_version(self.fid)
        self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.5}])
        self.assertEqual([j.code == latest["code"] for j in self.pool.train()[1:]], [True, True])
        self.assertEqual({self.store.version(self.fid, n)["path"] for n in (1, 2, 3)}, {latest["path"]},
                         "the variants share the latest version's file")

    def test_a_new_program_moves_the_roots_as_a_gym_run_does(self):
        self.first()
        pooled = self.code.replace("'roots': ['SPY']", "'roots': ['SPY', 'QQQ']")
        self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.5}], code=pooled)
        self.assertEqual(self.store.family(self.fid)["roots"], ["SPY", "QQQ"])
        self.assertTrue(all(j.roots == ("SPY", "QQQ") and j.code == pooled for j in self.pool.train()[1:]))


class Validation(SweepCase):
    def refused(self, variants, **args):
        self.first()
        jobs = len(self.pool.jobs)
        versions = len(self.store.versions(self.fid))
        view, _ = self.sweep(variants, **args)
        self.assertEqual(view["status"], "refused", view)
        self.assertEqual((len(self.pool.jobs), len(self.store.versions(self.fid))), (jobs, versions), "nothing reached the Gym")
        return view["reason"]

    def test_a_key_outside_params_is_refused(self):
        self.assertIn("not in the program's PARAMS", self.refused([{"vrp_min": 1.3}, {"no_such_knob": 1.0}]))

    def test_a_value_of_another_type_is_refused(self):
        self.assertIn("keeps the type", self.refused([{"vrp_min": 1.3}, {"vrp_min": "high"}]))

    def test_a_date_or_a_year_is_refused(self):
        for bad in (2025, 20250102, "2025-01-02"):
            self.setUp()
            self.assertIn("date", self.refused([{"vrp_min": 1.3}, {"vrp_min": bad}]).lower())

    def test_one_variant_or_too_many_is_refused(self):
        self.assertIn("at least 2", self.refused([{"vrp_min": 1.3}]))
        self.setUp()
        self.assertIn("at most 12", self.refused([{"vrp_min": 1.0 + i / 100} for i in range(13)]))
        self.setUp()
        self.settings["researcher"]["max_sweep_variants"] = 3
        self.assertIn("at most 3", self.refused([{"vrp_min": 1.0 + i / 100} for i in range(4)]))

    def test_repeats_are_dropped_and_a_sweep_of_one_distinct_program_is_refused(self):
        self.assertIn("fewer than 2 distinct", self.refused([{"vrp_min": 1.3}, {"vrp_min": 1.3}]))
        self.setUp()
        self.first()
        view, _ = self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.3}, {"vrp_min": 1.5}])
        self.assertEqual((view["variants"], view["repeats_dropped"]), (2, 1))

    def test_variants_that_are_not_objects_are_refused(self):
        self.assertIn("list of objects", self.refused("vrp_min=1.3"))
        self.setUp()
        self.assertIn("list of objects", self.refused([{"vrp_min": 1.3}, 1.5]))

    def test_a_program_without_a_literal_params_is_refused(self):
        code = self.code.replace("PARAMS = {", "PARAMS = dict(**{", 1)
        code = code.replace("'dte_max': 2}", "'dte_max': 2})", 1)
        self.assertIn("PARAMS as a literal dict", self.refused([{"vrp_min": 1.3}, {"vrp_min": 1.5}], code=code))

    def test_a_switched_off_sweep_is_refused(self):
        self.settings["researcher"]["sweep_enabled"] = False
        self.assertIn("switched off", self.refused([{"vrp_min": 1.3}, {"vrp_min": 1.5}]))

    def test_sweep_variants_merges_in_order(self):
        code = "NEEDS = {'roots': ['SPY']}\nPARAMS = {'a': 1.0, 'b': True}\n"
        out, dropped, why = sweep_variants(code, [{"a": 2.0}, {"b": False}, {"a": 2.0}], {"a": 3.0})
        self.assertIsNone(why)
        self.assertEqual((out, dropped), ([{"a": 2.0}, {"a": 3.0, "b": False}], 1))


class Turns(SweepCase):
    def names(self, body):
        return [t["name"] for t in body["tools"]]

    def test_revise_requires_a_run_or_a_sweep_and_read_offers_the_sweep(self):
        self.first()
        self.steps = [{"calls": [("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.4}], "why": "a grid",
                                                "note": "The filter was too strict."})]},
                      lambda body: {"calls": [("submit", {"run_id": json.loads(calls_in(body)[-1]["output"])["table"][0]["run_id"]})]},
                      {"text": "done"}]
        out = self.researcher().cycle(self.fid)
        self.assertNotIn("error", out)
        revise, read = self.sail.bodies[0], self.sail.bodies[1]
        self.assertEqual((self.names(revise), revise["tool_choice"]), (["gym_run", "gym_sweep"], "required"))
        self.assertEqual((self.names(read), read["tool_choice"]),
                         (["gym_run", "gym_sweep", "read_run", "notebook", "graveyard", "submit"], "auto"))
        self.assertEqual(out["sweep"], {"variants": 2, "completed": 2, "eligible": 2, "failed": 0})
        self.assertEqual(out["note"], "The filter was too strict.")
        fam = self.store.family(self.fid)
        self.assertEqual(self.store.version(self.fid, fam["best_version"])["params"], {"vrp_min": 1.4})
        sweep = next(t for t in revise["tools"] if t["name"] == "gym_sweep")
        self.assertIn("PUBLIC", sweep["parameters"]["properties"]["note"]["description"])
        self.assertIn("2 to 12", sweep["parameters"]["properties"]["variants"]["description"])

    def test_a_second_run_or_sweep_is_queued_and_opens_the_next_cycle(self):
        self.first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.5}]})]}]
        out = self.researcher().cycle(self.fid)
        self.assertTrue(out["pending_run"])
        self.assertEqual(self.store.convo(self.fid)[1]["name"], "gym_sweep")
        self.assertEqual(len(self.pool.train()), 2, "one run this cycle")
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(len(self.pool.train()), 4, "the queued sweep opened the next cycle")
        self.assertEqual(out["sweep"]["variants"], 2)
        body = self.sail.bodies[-1]
        self.assertIn("The gym_sweep you queued last cycle ran:", json.dumps(body["input"]))
        self.assertEqual(body["tool_choice"], "auto", "a completed sweep is read")
        self.assertIsNone(self.store.convo(self.fid)[1])

    def test_a_sweep_after_a_sweep_in_one_cycle_waits(self):
        self.first()
        grid = {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.5}]}
        self.steps = [{"calls": [("gym_sweep", grid), ("gym_sweep", grid)]}, {"text": "ok"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(len(self.pool.train()), 3, "one sweep ran; the other is queued")
        self.assertTrue(out["pending_run"])

    def test_a_run_queued_before_sweeps_existed_still_runs(self):
        self.first()
        cycles, _ = self.store.convo(self.fid)
        self.store.save_convo(self.fid, cycles, {"call_id": "old", "author": "synthetic", "arguments": {"params": {"vrp_min": 1.3}}})
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(self.fid)
        self.assertEqual(self.pool.train()[-1].params, {"vrp_min": 1.3})
        self.assertIsNone(self.pool.train()[-1].group)

    def test_switched_off_the_sweep_is_not_offered_and_revise_still_requires_a_run(self):
        self.first()
        self.settings["researcher"]["sweep_enabled"] = False
        self.steps = [{"calls": [("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.5}]})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual([self.names(b) for b in self.sail.bodies[:2]], [["gym_run"], ["gym_run"]])
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required", "required", "auto"])
        self.assertNotIn("gym_sweep", self.names(self.sail.bodies[2]))
        self.assertEqual(len(self.pool.train()), 2, "the refused sweep reached no Gym; the run did")
        self.assertNotIn("error", out)
        self.assertIn("gym_sweep is switched off", self.sail.bodies[0]["input"][-1]["content"])

    def test_the_limit_in_the_tool_follows_the_setting(self):
        self.settings["researcher"]["max_sweep_variants"] = 6
        tools = self.researcher().tools(revise=True, retire=False)
        sweep = next(t for t in tools if t["name"] == "gym_sweep")
        self.assertEqual(sweep, sweep_tool(6))
        self.assertIn("2 to 6", sweep["parameters"]["properties"]["variants"]["description"])


if __name__ == "__main__":
    unittest.main()
