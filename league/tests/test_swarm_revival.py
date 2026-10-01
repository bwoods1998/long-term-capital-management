"""THE OPERATOR'S RUN (league/swarm/researcher.py, Oct 1). The operator revives a retired family as a lineage fork whose
version 1 (author "operator-revive") is the old program WITH its params. Before Oct 1 no revival ran that program: a
`gym_run` with no code reran the latest code with params `{}`, and researchers often wrote new code at once. Now the
harness runs the revived version exactly (its code and params) before the model's turn, recorded as that version, and a
`gym_run` with neither code nor params reruns the latest version exactly. Synthetic programs, parameters and results only
(a fake Gym)."""

from __future__ import annotations

import json

from league.gym.results import failed
from league.swarm.researcher import ALREADY_RUN, OPERATOR_RUN_ATTEMPTS, OPERATOR_RUN_KEY, params_of
from league.swarm.seeds import family_spec
from league.tests.test_swarm_researcher import calls_in
from league.tests.test_swarm_sweep import SweepCase, scored

#: The revived version's params (not its PARAMS defaults): the program the operator validated.
REVIVED = {"vrp_min": 1.4}


class RevivalCase(SweepCase):
    def revive(self, params=None, *, author="operator-revive", suffix="r"):
        """A fork of the seed family, as the operator's revival tool makes one: version 1 is the program with its params."""
        child = self.store.add_family({**family_spec(self.spec), "id": f"{self.fid}-{suffix}"}, origin="operator-revive",
                                      parent=self.fid)
        self.store.add_version(child["id"], self.code, dict(REVIVED if params is None else params), author=author,
                               note="revived to re-run it unchanged under the new evaluator")
        return child["id"]

    def run_(self, fid, args):
        out: dict = {"tool_calls": 0}
        return self.researcher()._gym_run(self.store.family(fid), args, out, author="synthetic"), out

    def robustness(self):
        return [j for j in self.pool.jobs if j.purpose == "robustness"]


class TheRevivedVersionRunsExactly(RevivalCase):
    def test_it_runs_with_its_code_and_params_as_version_one_and_a_pass_becomes_the_best(self):
        rid = self.revive()
        before = self.store.family(rid)
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(rid)
        self.assertNotIn("error", out)
        self.assertEqual(out["operator_run"], 1)
        [job] = self.pool.train()
        self.assertEqual((job.family, job.version, job.code, job.params, job.stress, job.window),
                         (rid, 1, self.code, REVIVED, 1.0, "train"), "its stored code AND params, at the normal spread")
        self.assertEqual([(v["n"], v["author"]) for v in self.store.versions(rid)], [(1, "operator-revive")],
                         "no new version row")
        fam = self.store.family(rid)
        self.assertEqual((fam["revisions"], fam["trials"]), (before["revisions"], before["trials"] + 1),
                         "no revision; one trial against the lineage")
        [run] = self.store.runs(rid, window="train")
        self.assertEqual((run["version"], run["stress"], run["purpose"], run["status"]), (1, 1.0, "train", "ok"))
        state = fam["state"]
        self.assertEqual((state["best_train_version"], state["best_train_run"]), (1, run["run_id"]), "a pass is the best")
        self.assertEqual(state[OPERATOR_RUN_KEY]["ran"], run["run_id"])
        robust = self.robustness()
        self.assertIn((1, 1.5), {(j.version, j.stress) for j in robust}, "the best's 1.5x run is queued")
        self.assertTrue(robust and all(j.params == REVIVED and j.code == self.code for j in robust))
        [body] = self.sail.bodies
        self.assertEqual(body["tool_choice"], "auto", "the model READs the run: it was this cycle's one run")
        context = json.dumps(body["input"])
        self.assertIn("exactly as revived", context)
        self.assertIn(f"the operator's revival of {self.fid}'s program", context)
        self.assertIn("never a reason to retire", context)

    def test_the_next_cycle_never_runs_it_again(self):
        rid = self.revive()
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), 1)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "waiting for the validation"})]}]
        out = self.researcher().cycle(rid)
        self.assertNotIn("operator_run", out)
        self.assertEqual(len(self.pool.train()), 1, "one exact run, never two")
        self.assertEqual(self.sail.bodies[-1]["tool_choice"], "required", "the model's own REVISE turn")
        self.assertIn("run unchanged (its stored code and params)", json.dumps(self.sail.bodies[-1]["input"]))

    def test_a_queued_run_and_a_rewrite_wait_for_the_next_cycle(self):
        rid = self.revive()
        self.store.save_convo(rid, [], {"call_id": "queued-1", "name": "gym_run", "author": "synthetic",
                                        "arguments": {"code": self.code, "params": {"vrp_min": 1.3}}})
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual([j.params for j in self.pool.train()], [REVIVED], "only the operator's run this cycle")
        self.assertEqual(self.store.convo(rid)[1]["call_id"], "queued-1", "the queued run is kept")
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual([j.params for j in self.pool.train()], [REVIVED, {"vrp_min": 1.3}], "it runs next cycle")
        self.assertEqual([v["n"] for v in self.store.versions(rid)], [1, 2])

    def test_a_gym_error_is_retried_next_cycle_then_given_up_with_a_note(self):
        rid = self.revive()
        self.pool.fail = lambda job: "the Gym is restarting" if job.purpose == "train" else None
        for attempt in range(1, OPERATOR_RUN_ATTEMPTS):
            out = self.researcher().cycle(rid)
            self.assertIn("gym:", out["error"])
            self.assertEqual(out["model_calls"], 0, "no model is paid to read a Gym error")
            self.assertEqual(self.store.family(rid)["state"][OPERATOR_RUN_KEY]["tries"], attempt)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "the Gym is down"})]}]
        out = self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), OPERATOR_RUN_ATTEMPTS, "one attempt a cycle")
        self.assertIn("could not run it 3 times", self.store.family(rid)["state"][OPERATOR_RUN_KEY]["gave_up"])
        self.assertEqual(out["model_calls"], 1, "after the last attempt the model goes on")
        notes = self.store.notebook(rid)[-1]["text"] + self.store.notebook(rid)[-2]["text"]
        self.assertIn("could not run version 1", notes)
        self.assertIn("call gym_run with no code and no params", notes, "the note says how to run it")
        self.pool.fail = lambda job: None
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "still nothing"})]}]
        self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), OPERATOR_RUN_ATTEMPTS, "given up: never asked again on this evaluator")

    def test_a_run_that_lands_after_the_wait_is_read_back_and_scored_without_a_second_job(self):
        rid = self.revive()
        self.pool.fail = lambda job: "late" if job.purpose == "train" else None
        out = self.researcher().cycle(rid)
        self.assertIn("gym:", out["error"])
        callback, landed = self.pool.lates[0]
        callback(landed)
        self.assertIsNone(self.store.family(rid)["state"].get("best_train_version"), "a late row is not yet the best")
        self.pool.fail = lambda job: None
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "reading the revived run"})]}]
        out = self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), 1, "read back from the store: no second Gym job")
        self.assertNotIn("stored", out, "the harness's read-back is not the researcher's idle doing (DORMANCY)")
        state = self.store.family(rid)["state"]
        self.assertEqual(state["best_train_version"], 1)
        self.assertEqual(state[OPERATOR_RUN_KEY]["ran"], state["best_train_run"])
        self.assertIn("already recorded", json.dumps(self.sail.bodies[-1]["input"]))



class WhatIsNotItsAnswer(RevivalCase):
    """Review of #465: a run the Gym could not finish is not the program's answer; any new evaluation of it is the cycle's
    one run; an attempt still on the Gym is never asked twice; a failure of the attempt itself is counted."""

    def answer_for_the_revival(self, how):
        """The Gym's answer to the operator's job (version 1 at the revived params) made by `how(job)`; others score."""
        self.pool.answer = lambda job: how(job) if (job.version, job.params) == (1, REVIVED) and job.purpose == "train" \
            else scored(job)

    def test_a_run_the_gym_could_not_finish_is_retried_and_never_marked_ran(self):
        rid = self.revive()
        self.answer_for_the_revival(lambda job: failed(job.name, "the worker died (exit -9)"))
        out = self.researcher().cycle(rid)
        self.assertIn("gym:", out["error"])
        self.assertEqual(out["model_calls"], 0)
        record = self.store.family(rid)["state"][OPERATOR_RUN_KEY]
        self.assertEqual((record["tries"], record.get("ran")), (1, None), "a run the Gym could not finish is no answer")
        [row] = self.store.runs(rid, window="train")
        self.assertEqual(row["status"], "error", "its row is kept (no trial)")
        self.assertEqual(self.researcher().operator_owed(self.store.family(rid))["n"], 1, "still owed")
        self.assertIn("runs it first", self.researcher().status(self.store.family(rid)))
        self.pool.answer = scored  # the Gym recovered
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), 2, "asked again next cycle")
        state = self.store.family(rid)["state"]
        self.assertEqual(state[OPERATOR_RUN_KEY]["ran"], state["best_train_run"])

    def test_three_unfinished_runs_give_up_with_a_note(self):
        rid = self.revive()
        self.answer_for_the_revival(lambda job: failed(job.name, "the unit timed out and was killed"))
        for _ in range(OPERATOR_RUN_ATTEMPTS - 1):
            self.assertEqual(self.researcher().cycle(rid)["model_calls"], 0)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "the Gym keeps failing it"})]}]
        out = self.researcher().cycle(rid)
        self.assertEqual(out["model_calls"], 1)
        record = self.store.family(rid)["state"][OPERATOR_RUN_KEY]
        self.assertIn("could not run it 3 times", record["gave_up"])
        self.assertNotIn("ran", record)
        self.assertIn("will not ask again", self.researcher().status(self.store.family(rid)))

    def test_a_disqualified_run_is_its_answer_and_the_cycles_one_run(self):
        rid = self.revive()
        self.answer_for_the_revival(lambda job: {**scored(job), "status": "disqualified"})
        self.store.save_convo(rid, [], {"call_id": "queued-1", "name": "gym_run", "author": "synthetic",
                                        "arguments": {"code": self.code, "params": {"vrp_min": 1.3}}})
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "reading why it was disqualified"})]}]
        out = self.researcher().cycle(rid)
        self.assertEqual([j.params for j in self.pool.train()], [REVIVED], "no second Train job this cycle")
        record = self.store.family(rid)["state"][OPERATOR_RUN_KEY]
        [row] = self.store.runs(rid, window="train")
        self.assertEqual((row["status"], record["ran"]), ("disqualified", row["run_id"]), "its answer")
        self.assertEqual(self.store.convo(rid)[1]["call_id"], "queued-1", "the queued run waits")
        self.assertTrue(out["pending_run"])
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual([j.params for j in self.pool.train()], [REVIVED, {"vrp_min": 1.3}], "it runs next cycle")
        self.assertIsNone(self.researcher().operator_owed(self.store.family(rid)))

    def test_a_waiting_rewrite_waits_for_the_next_cycle(self):
        rid = self.revive()
        rewrite = self.code + "\n# a stronger model's rewrite\n"
        self.store.set_state(rid, rewrite_ready={"code": rewrite, "profile": "pro_balanced"})
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(rid)
        self.assertNotIn("rewrite", out)
        self.assertEqual([(j.version, j.params) for j in self.pool.train()], [(1, REVIVED)], "only the operator's run")
        self.assertEqual(self.store.family(rid)["state"]["rewrite_ready"]["code"], rewrite, "the rewrite is kept")
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(rid)
        self.assertEqual(out["rewrite"], "pro_balanced")
        self.assertEqual([j.code for j in self.pool.train()], [self.code, rewrite], "it runs next cycle")
        self.assertIsNone(self.store.family(rid)["state"].get("rewrite_ready"))

    def test_a_run_call_after_the_operators_run_replaces_the_queued_one(self):
        rid = self.revive()
        self.store.save_convo(rid, [], {"call_id": "queued-1", "name": "gym_run", "author": "synthetic",
                                        "arguments": {"code": self.code, "params": {"vrp_min": 1.3}}})
        self.steps = [{"calls": [("notebook", {"action": "read"})]},
                      {"calls": [("gym_run", {"code": self.code, "params": {"vrp_min": 1.5}, "why": "after the revival"})]}]
        out = self.researcher().cycle(rid)
        self.assertEqual(out["model_calls"], 2, "a READ turn goes on while only last cycle's run is queued")
        self.assertIn("A run call this cycle replaces it", json.dumps(self.sail.bodies[0]["input"]))
        queued = self.store.convo(rid)[1]
        self.assertEqual(queued["arguments"]["params"], {"vrp_min": 1.5}, "the newer call is queued")
        self.assertTrue(out.get("queued_replaced"))
        self.assertEqual([j.params for j in self.pool.train()], [REVIVED])
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual([j.params for j in self.pool.train()], [REVIVED, {"vrp_min": 1.5}], "never the replaced one")

    def test_an_attempt_still_on_the_gym_is_never_asked_twice(self):
        rid = self.revive()
        self.pool.fail = lambda job: "late" if job.purpose == "train" else None
        self.researcher().cycle(rid)
        record = self.store.family(rid)["state"][OPERATOR_RUN_KEY]
        self.assertGreater(record["late_until"], self.clock(), "its wait gave up while the Gym ran it")
        self.pool.fail = lambda job: None
        out = self.researcher().cycle(rid)  # before it lands
        self.assertEqual((len(self.pool.train()), out["model_calls"]), (1, 0), "no second job for one evaluation")
        self.assertIn("still on the Gym", out["error"])
        callback, landed = self.pool.lates[0]
        callback(landed)
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), 1, "read back when it lands")
        state = self.store.family(rid)["state"]
        self.assertEqual(self.store.family(rid)["trials"], 1, "one trial")
        self.assertEqual(state[OPERATOR_RUN_KEY]["ran"], state["best_train_run"])

    def test_an_attempt_that_never_lands_is_asked_again_after_its_wait(self):
        rid = self.revive()
        self.pool.fail = lambda job: "late" if job.purpose == "train" else None
        self.researcher().cycle(rid)
        late_until = self.store.family(rid)["state"][OPERATOR_RUN_KEY]["late_until"]
        self.pool.fail = lambda job: None
        self.clock.advance(late_until - self.clock() + 1)  # it failed on the Gym: nothing landed
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual(len(self.pool.train()), 2, "asked again once its wait is over")
        self.assertTrue(self.store.family(rid)["state"][OPERATOR_RUN_KEY]["ran"])

    def test_a_failure_of_the_attempt_itself_is_counted_and_bounded(self):
        rid = self.revive()

        def boom(job):
            raise RuntimeError("an unexpected failure")

        self.pool.fail = boom
        for attempt in range(1, OPERATOR_RUN_ATTEMPTS):
            out = self.researcher().cycle(rid)
            self.assertEqual(out["model_calls"], 0)
            self.assertEqual(self.store.family(rid)["state"][OPERATOR_RUN_KEY]["tries"], attempt)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "nothing new"})]}]
        out = self.researcher().cycle(rid)
        self.assertEqual(out["model_calls"], 1, "after the last attempt the model goes on")
        self.assertIn("RuntimeError", self.store.family(rid)["state"][OPERATOR_RUN_KEY]["gave_up"])
        self.assertEqual(len(self.pool.train()), OPERATOR_RUN_ATTEMPTS, "one attempt a cycle, then none")

    def test_a_new_train_span_owes_the_run_again(self):
        rid = self.revive()
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        researcher = self.researcher()
        self.assertIsNone(researcher.operator_owed(self.store.family(rid)))
        researcher.train_span = lambda: "2020-01-01"
        self.assertEqual(researcher.operator_record(self.store.family(rid), 1), {}, "the record is per Train span")
        self.assertEqual(researcher.operator_owed(self.store.family(rid))["n"], 1)


class GymRunWithNothing(RevivalCase):
    def test_no_code_and_no_params_rerun_the_latest_version_with_its_params(self):
        self.first()  # the starter, version 1, params {}
        self.run_(self.fid, {"params": {"vrp_min": 1.3}})  # version 2
        view, _ = self.run_(self.fid, {"stress": 1.5, "why": "the same program at the gate's stress"})
        job = self.pool.train()[-1]
        self.assertEqual((job.params, job.version, job.stress), ({"vrp_min": 1.3}, 2, 1.5), "its params carry over")
        self.assertEqual(view["version"], 2)
        self.assertEqual(len(self.store.versions(self.fid)), 2, "no new version row: it is the latest version")
        again, _ = self.run_(self.fid, {})
        self.assertEqual((again["already_run"], again["version"]), (ALREADY_RUN, 2), "the same evaluation as version 2's")

    def test_explicit_params_still_replace_them(self):
        self.first()
        self.run_(self.fid, {"params": {"vrp_min": 1.3}})
        self.run_(self.fid, {"params": {}, "stress": 1.5})
        self.assertEqual((self.pool.train()[-1].params, self.pool.train()[-1].version), ({}, 1), "{} is the program as written")

    def test_a_revived_version_rerun_with_nothing_is_itself(self):
        rid = self.revive()
        view, _ = self.run_(rid, {"why": "re-run it unchanged"})
        self.assertEqual((self.pool.train()[-1].params, view["version"]), (REVIVED, 1))
        self.assertEqual(len(self.store.versions(rid)), 1)


class NoDoubleRun(RevivalCase):
    def test_a_matching_run_of_version_one_is_enough(self):
        rid = self.revive()
        self.run_(rid, {"code": self.code, "params": dict(REVIVED)})  # its researcher ran it exactly itself
        self.assertEqual((len(self.pool.train()), len(self.store.versions(rid))), (1, 1))
        researcher = self.researcher()
        self.assertIsNone(researcher.operator_owed(self.store.family(rid)))
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "nothing new"})]}]
        out = researcher.cycle(rid)
        self.assertNotIn("operator_run", out)
        self.assertEqual(len(self.pool.train()), 1, "no double run")
        self.assertIn("run unchanged", researcher.status(self.store.family(rid)))

    def test_the_same_program_under_another_version_is_enough(self):
        defaults = {"vrp_min": params_of(self.code)["vrp_min"]}  # its PARAMS default spelled out: one program with `{}`
        rid = self.revive(params=defaults)
        self.store.add_version(rid, self.code, {}, author="model")  # version 2: the same program
        self.run_(rid, {"code": self.code, "params": {}})
        self.assertEqual([j.version for j in self.pool.train()], [2])
        self.assertIsNone(self.researcher().operator_owed(self.store.family(rid)), "NO DUPLICATE RUNS: one evaluation")

    def test_a_run_on_another_evaluator_does_not_count(self):
        rid = self.revive()
        self.run_(rid, {"code": self.code, "params": dict(REVIVED)})
        self.assertIsNone(self.researcher().operator_owed(self.store.family(rid)))
        self.pool.image = lambda kind: "sbcp_new-image"  # a new Gym adopted: its image and engine bundle
        self.pool.bundle = lambda: "engine-bundle-new"
        self.assertEqual(self.researcher().operator_owed(self.store.family(rid))["n"], 1, "an adoption owes the run again")
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        self.assertEqual([(j.version, j.params) for j in self.pool.train()], [(1, REVIVED), (1, REVIVED)])
        self.assertIsNone(self.researcher().operator_owed(self.store.family(rid)), "once on each evaluator")


class Untouched(RevivalCase):
    def test_versions_others_wrote_are_never_run_by_the_harness(self):
        for author in ("model", "seed", "deepseek-ai/DeepSeek-V4-Pro"):
            fid = self.revive(author=author, suffix=author.split("/")[0])
            self.assertIsNone(self.researcher().operator_owed(self.store.family(fid)), author)
            self.assertEqual(self.researcher().operator_text(self.store.family(fid)), "")
            self.steps = [{"calls": [("gym_run", {"hold": True, "note": "nothing yet"})]}]
            out = self.researcher().cycle(fid)
            self.assertNotIn("operator_run", out)
        self.assertEqual(self.pool.train(), [], "the model's hold ran nothing, and the harness ran nothing")

    def test_retired_and_banded_families_are_untouched(self):
        retired = self.revive(suffix="dead")
        self.store.update_family(retired, retired_at=self.store.now())
        banded = self.revive(suffix="cand")
        self.store.set_band(banded, "candidate", reason="synthetic")
        researcher = self.researcher()
        for fid in (retired, banded):
            self.assertIsNone(researcher.operator_owed(self.store.family(fid)), fid)
        self.assertEqual(researcher.cycle(retired).get("skipped"), "retired")
        self.assertEqual(self.pool.train(), [])
        self.assertNotIn(OPERATOR_RUN_KEY, self.store.family(retired)["state"])

    def test_the_operator_version_need_not_be_the_latest(self):
        rid = self.revive()
        self.store.add_version(rid, self.code + "\n# the researcher's edit\n", {}, author="model")  # version 2, never run
        self.assertEqual(self.researcher().operator_owed(self.store.family(rid))["n"], 1)
        self.steps = [{"text": "read it"}]
        self.researcher().cycle(rid)
        [job] = self.pool.train()
        self.assertEqual((job.version, job.params), (1, REVIVED), "the operator's version, not the latest")
        self.assertEqual(len(self.store.versions(rid)), 2)
        outputs = [json.loads(i["output"]) for i in calls_in(self.sail.bodies[-1])]
        self.assertEqual(outputs, [], "the harness's run is no tool call of the model's")
