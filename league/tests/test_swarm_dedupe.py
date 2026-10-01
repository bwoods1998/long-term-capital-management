"""NO DUPLICATE RUNS, HOLD and DORMANCY (league/swarm/researcher.py, R3: the harness audit of Sept 28 found 44% of cycles
wasted and 45% of trials identical re-runs) and the operator's gate hold (league/swarm/gate.py). A run or sweep variant the
family already evaluated is answered from the store with no job, no trial and no revision; a REVISE turn may hold; a family
whose cycles only hold or get stored results for `researcher.dormant_cycles` cycles is dead for the idle rule. Synthetic
programs, parameters and results only (a fake Gym)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from league.swarm import progress
from league.swarm.__main__ import main as swarm_main
from league.swarm.gate import Gate
from league.swarm.researcher import (ALREADY_RUN, DORMANT_CYCLES, Researcher, awaiting_validation, dormant_count, dormant_limit,
                                     held_at_gate, holding, idle_dead)
from league.swarm.store import dumps
from league.swarm.researcher import SCREENED, idle_cause
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_progress import ProgressCase
from league.tests.test_swarm_researcher import ResearcherCase, calls_in
from league.tests.test_swarm_rounds import RoundCase, weak
from league.tests.test_swarm_sweep import SweepCase, scored

DEAD = "made no new Gym evaluation in its last {n} cycles (only stored results, holds and refused runs)"


class DedupeCase(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.fid = self.fam["id"]

    def first(self):
        self.researcher().cycle(self.fid)  # the starter program as written: version 1, one trial

    def run_(self, args, researcher=None):
        out: dict = {"tool_calls": 0}
        view = (researcher or self.researcher())._gym_run(self.store.family(self.fid), args, out, author="synthetic")
        return view, out

    def counts(self):
        fam = self.store.family(self.fid)
        return fam["trials"], fam["revisions"], fam["since_val_trials"], fam["stall"], len(self.store.versions(self.fid))


class StoredResults(DedupeCase):
    def test_an_identical_rerun_returns_the_stored_result_with_no_trial_and_no_revision(self):
        self.first()
        before = self.counts()
        [starter] = self.store.runs(self.fid, window="train")
        code = self.store.version(self.fid, 1)["code"]
        # The latest version as it is, `{}`, the default spelled out and the same code again: one program, one evaluation.
        for args in ({}, {"params": {}}, {"params": {"vrp_min": 1.2}}, {"code": code, "why": "again"}):
            view, out = self.run_(args)
            self.assertEqual(view["already_run"], ALREADY_RUN, args)
            self.assertEqual((view["status"], view["run_id"], view["version"]), ("ok", starter["run_id"], 1))
            self.assertIn("summary", view)
            self.assertIn("train_score", view, "the same compact view")
            self.assertIn("hold=true", view["next"])
            self.assertEqual(out["stored"], 1)
            self.assertNotIn("trials", out)
            self.assertNotIn("run_id", out, "no run this cycle: a real one may still follow")
        self.assertEqual(len(self.pool.jobs), 1, "no Gym job")
        self.assertEqual(self.counts(), before, "no trial, no revision, no version")
        self.assertEqual(len(self.store.runs(self.fid, window="train")), 1)

    def test_a_changed_param_stress_or_code_runs_and_is_stored_after(self):
        self.first()
        view, out = self.run_({"params": {"vrp_min": 1.3}})
        self.assertNotIn("already_run", view)
        self.assertEqual((len(self.pool.jobs), out["trials"]), (2, 1))
        self.assertEqual(self.counts()[:2], (2, 2), "a new evaluation: a trial and a revision")
        again, out = self.run_({"params": {"vrp_min": 1.3}})
        self.assertEqual((again["already_run"], again["run_id"], len(self.pool.jobs)), (ALREADY_RUN, view["run_id"], 2))
        view, _ = self.run_({"params": {"vrp_min": 1.3}, "stress": 1.5})
        self.assertNotIn("already_run", view, "another stress is another evaluation")
        self.assertEqual(self.run_({"params": {"vrp_min": 1.3}, "stress": 1.5})[0]["already_run"], ALREADY_RUN)
        code = self.store.version(self.fid, 1)["code"] + "\n# the same logic in another file\n"
        view, _ = self.run_({"code": code, "params": {"vrp_min": 1.3}})
        self.assertNotIn("already_run", view, "other code is another program")
        self.assertEqual(len(self.pool.jobs), 4)
        self.assertEqual(self.run_({"code": code, "params": {"vrp_min": 1.3}})[0]["already_run"], ALREADY_RUN)

    def test_another_gym_image_or_engine_runs_again(self):
        gym = {"image": "sbcp_one", "engine": "engine-one"}
        self.pool.image = lambda kind: gym["image"]
        self.pool.bundle = lambda: gym["engine"]
        self.first()
        self.assertEqual(self.run_({})[0]["already_run"], ALREADY_RUN)
        gym["image"] = "sbcp_two"
        self.assertNotIn("already_run", self.run_({})[0], "new data: a new evaluation")
        self.assertEqual(self.run_({})[0]["already_run"], ALREADY_RUN)
        gym["engine"] = "engine-two"
        self.assertNotIn("already_run", self.run_({})[0], "a new engine: a new evaluation")
        self.assertEqual(len(self.pool.jobs), 3)

    def test_a_result_is_keyed_by_the_image_the_pool_stamped_on_it(self):
        """A box still on an older image answered: its result is that image's evaluation, not the current one's."""
        self.pool.image = lambda kind: "sbcp_new"
        self.pool.bundle = lambda: "engine-one"
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots), "gym_image": "sbcp_old", "gym_bundle": "engine-one"}
        self.first()
        self.assertNotIn("already_run", self.run_({})[0])
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots), "gym_image": "sbcp_new", "gym_bundle": "engine-one"}
        self.assertNotIn("already_run", self.run_({})[0])
        self.assertEqual(self.run_({})[0]["already_run"], ALREADY_RUN)
        self.assertEqual(len(self.pool.jobs), 3)

    def test_a_run_that_did_not_complete_is_not_stored(self):
        self.first()
        self.pool.answer = lambda job: result(job.name, status="disqualified", roots=job.roots)
        self.run_({"params": {"vrp_min": 1.3}})
        view, _ = self.run_({"params": {"vrp_min": 1.3}})
        self.assertNotIn("already_run", view)
        self.assertEqual(len(self.pool.jobs), 3, "a failed evaluation runs again")

    def test_a_row_recorded_before_keys_takes_its_key_on_its_next_evaluation(self):
        """The running swarm's placeholder loops have rows without a key: the next identical run is one more trial (the
        Gym's same run_id: the same row), and from then on the row answers."""
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots), "run_id": "legacy-placeholder"}
        self.first()
        row = self.store.run("legacy-placeholder")
        summary = {k: v for k, v in row["summary"].items() if k != "eval_key"}
        self.store._exec("UPDATE runs SET summary=? WHERE run_id=?", (dumps(summary), "legacy-placeholder"))
        self.assertNotIn("already_run", self.run_({})[0])
        self.assertEqual((len(self.pool.jobs), self.store.family(self.fid)["trials"]), (2, 2))
        self.assertEqual(len(self.store.runs(self.fid, window="train")), 1, "one row, every evaluation counted")
        self.assertIn("eval_key", self.store.run("legacy-placeholder")["summary"])
        self.assertEqual(self.run_({})[0]["already_run"], ALREADY_RUN)
        self.assertEqual(len(self.pool.jobs), 2)

    def test_switched_off_every_run_reaches_the_gym(self):
        self.settings["researcher"]["reuse_results"] = False
        self.first()
        self.run_({})
        self.run_({})
        self.assertEqual((len(self.pool.jobs), self.store.family(self.fid)["trials"]), (3, 3))

    def test_a_result_that_landed_late_is_scored_when_it_is_asked_for_again(self):
        """A run the researcher gave up on is recorded when it lands but never scored; asked for again, its stored result
        is scored as a run's would have been (it can become the best)."""
        self.pool.answer = scored  # the Train score follows vrp_min: the starter's default 1.2 scores 2.0, 1.4 scores 3.0
        self.first()
        self.assertEqual(self.store.family(self.fid)["best_train"], 2.0)
        self.pool.fail = "late"
        view, out = self.run_({"params": {"vrp_min": 1.4}})
        self.assertEqual(view["status"], "gym_error")
        late, landed = self.pool.late
        self.pool.fail = None
        late(landed)
        self.assertEqual((self.store.family(self.fid)["trials"], self.store.family(self.fid)["best_train"]), (2, 2.0))
        view, out = self.run_({"params": {"vrp_min": 1.4}})
        self.assertEqual((view["already_run"], view["new_best_train_score"]), (ALREADY_RUN, 3.0))
        fam = self.store.family(self.fid)
        self.assertEqual((fam["best_train"], fam["state"]["best_train_run"], fam["trials"]), (3.0, view["run_id"], 2))
        self.assertTrue(out["improved"])
        self.assertEqual(len(self.pool.jobs), 2)

    def test_a_late_result_is_scored_from_its_row_once_its_full_result_is_pruned(self):
        """The review of R3: a late result was recorded without its Train score, so once pruned it was never scored and
        dedupe forbade running it again. Its row now keeps the score, as a run's does."""
        self.pool.answer = scored  # vrp_min 1.4 scores 3.0; the starter's default scores 2.0
        self.first()
        self.pool.fail = "late"
        self.run_({"params": {"vrp_min": 1.4}})
        late, landed = self.pool.late
        self.pool.fail = None
        late(landed)
        [row] = [r for r in self.store.runs(self.fid, window="train") if r["version"] == 2]
        self.assertEqual((row["summary"]["train_score"], row["summary"]["train_eligible"]), (3.0, True))
        for i in range(8):  # newer runs prune its full result (the newest six and the best are kept)
            self.run_({"params": {"vrp_min": 1.0 + i / 100}})
        self.assertIsNone(self.store.run_result(row["run_id"]), "pruned")
        self.assertEqual(self.store.family(self.fid)["best_train"], 2.0)
        jobs = len(self.pool.jobs)
        view, out = self.run_({"params": {"vrp_min": 1.4}})
        self.assertEqual((view["already_run"], view["new_best_train_score"], len(self.pool.jobs)), (ALREADY_RUN, 3.0, jobs))
        self.assertEqual(self.store.family(self.fid)["best_train"], 3.0)
        self.assertTrue(out["improved"])

    def test_a_stored_row_that_can_no_longer_be_scored_runs_again(self):
        self.first()
        self.run_({"params": {"vrp_min": 1.3}})
        [row] = [r for r in self.store.runs(self.fid, window="train") if r["version"] == 2]
        summary = {k: v for k, v in row["summary"].items() if k not in ("train_score", "train_eligible")}
        self.store._exec("UPDATE runs SET summary=?, path=NULL WHERE run_id=?", (dumps(summary), row["run_id"]))
        view, _ = self.run_({"params": {"vrp_min": 1.3}})
        self.assertNotIn("already_run", view, "neither its full result nor a score: it runs again")
        self.assertEqual(len(self.pool.jobs), 3)
        self.assertEqual(self.run_({"params": {"vrp_min": 1.3}})[0]["already_run"], ALREADY_RUN)

    def test_a_row_recorded_before_keys_takes_its_score_too(self):
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots), "run_id": "legacy-placeholder"}
        self.first()
        row = self.store.run("legacy-placeholder")
        summary = {k: v for k, v in row["summary"].items() if k not in ("eval_key", "train_score", "train_eligible")}
        self.store._exec("UPDATE runs SET summary=? WHERE run_id=?", (dumps(summary), "legacy-placeholder"))
        self.run_({})
        summary = self.store.run("legacy-placeholder")["summary"]
        self.assertTrue({"eval_key", "train_score", "train_eligible"} <= set(summary))

    def test_a_stored_result_on_another_fill_model_runs_again(self):
        """A calibration changed on a box in place (no new image): once a result on the new fill model lands, a stored
        result on the old one is not reused."""
        fill = {"model": "fill-one"}
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots), "fill_model": fill["model"]}
        self.first()
        me = self.researcher()
        self.assertEqual(self.store.runs(self.fid, window="train")[0]["summary"]["fill_model"], "fill-one")
        self.assertEqual(self.run_({}, me)[0]["already_run"], ALREADY_RUN, "no newer fill model seen yet")
        fill["model"] = "fill-two"
        self.assertNotIn("already_run", self.run_({"params": {"vrp_min": 1.3}}, me)[0])
        # The program as written, explicitly (a bare `{}` now reruns the latest version, version 2, exactly: Oct 1).
        self.assertNotIn("already_run", self.run_({"params": {}}, me)[0], "stored on the old fill model: runs again")
        self.assertEqual(self.run_({"params": {}}, me)[0]["already_run"], ALREADY_RUN)
        self.assertEqual(len(self.pool.jobs), 3)

    def test_the_key_sorts_the_roots_as_the_gym_does(self):
        me = self.researcher()

        def key(roots):
            return me.eval_key(self.code, {}, stress=1.0, window="train", roots=roots)

        self.assertEqual(key(["QQQ", "SPY"]), key(["spy", "QQQ"]))
        self.assertNotEqual(key(["SPY"]), key(["SPY", "QQQ"]))

    def test_a_run_landing_late_restarts_the_dormant_count(self):
        self.first()
        self.store.set_state(self.fid, dormant_cycles=5)
        self.pool.fail = "late"
        view, out = self.run_({"params": {"vrp_min": 1.3}})
        self.assertEqual((view["status"], out["gym_asked"]), ("gym_error", True))
        self.assertEqual(dormant_count(self.store.family(self.fid)), 5)
        late, landed = self.pool.late
        late(landed)
        fam = self.store.family(self.fid)
        self.assertEqual((fam["trials"], dormant_count(fam)), (2, 0), "a new evaluation of its own, landed late")

    def test_in_a_cycle_a_stored_result_keeps_the_revise_turn_and_a_new_run_may_follow(self):
        self.first()
        self.steps = [{"calls": [("gym_run", {"params": {}})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.3}, "note": "The filter admitted too many days."})]},
                      {"text": "read it"}]
        out = self.researcher().cycle(self.fid)
        self.assertNotIn("error", out)
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required", "required", "auto"],
                         "a stored result is no run: REVISE again, then READ the new run")
        self.assertEqual(json.loads(calls_in(self.sail.bodies[1])[-1]["output"])["already_run"], ALREADY_RUN)
        self.assertEqual((out["stored"], out["trials"], len(self.pool.jobs)), (1, 1, 2))
        self.assertFalse(out["pending_run"], "the new run was this cycle's run")
        self.assertEqual(dormant_count(self.store.family(self.fid)), 0, "a new evaluation: not dormant")

    def test_a_queued_run_that_already_ran_is_answered_from_the_store_and_revise_follows(self):
        self.first()
        cycles, _ = self.store.convo(self.fid)
        self.store.save_convo(self.fid, cycles, {"call_id": "q", "name": "gym_run", "arguments": {"params": {}}, "author": "synthetic"})
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Nothing new to test until the breakdowns are read."})]}]
        out = self.researcher().cycle(self.fid)
        self.assertIn("had already run: its stored result", json.dumps(self.sail.bodies[0]["input"]))
        self.assertEqual(self.sail.bodies[0]["tool_choice"], "required")
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertEqual((out["stored"], out["hold"], out["dormant_cycles"]), (1, True, 1))
        self.assertIsNone(self.store.convo(self.fid)[1])


class StoredSweeps(SweepCase):
    def test_a_sweep_reads_back_the_variants_already_evaluated(self):
        self.first()  # the starter as written (vrp_min's default, 1.2)
        fam = self.store.family(self.fid)
        grid = [{}, {"vrp_min": 1.3}, {"vrp_min": 1.4}]
        view, out = self.sweep(grid)
        self.assertEqual([j.params for j in self.pool.train()[1:]], [{"vrp_min": 1.3}, {"vrp_min": 1.4}])
        self.assertEqual([(r["params"], r["version"]) for r in view["table"] if r.get("already_run")], [({}, 1)])
        self.assertNotIn("already_run", view, "two variants ran")
        self.assertEqual((out["trials"], out["stored"], out["sweep"]["reused"]), (2, 1, 1))
        self.assertIn("run_id", out)
        after = self.store.family(self.fid)
        self.assertEqual((after["revisions"] - fam["revisions"], len(self.store.versions(self.fid))), (1, 3))
        # The same sweep again: every variant is stored. No job, no trial, no version, no revision; no run for the cycle.
        view, out = self.sweep(grid)
        self.assertEqual(view["already_run"], ALREADY_RUN)
        self.assertTrue(all(r["already_run"] == ALREADY_RUN for r in view["table"]))
        self.assertEqual(view["table"][0]["params"], {"vrp_min": 1.4}, "still sorted by the Train score")
        self.assertEqual((len(self.pool.train()), out.get("trials", 0), out["stored"]), (3, 0, 3))
        self.assertNotIn("run_id", out)
        again = self.store.family(self.fid)
        self.assertEqual((again["revisions"], again["trials"], len(self.store.versions(self.fid))),
                         (after["revisions"], after["trials"], 3))

    def test_a_stored_variant_needs_no_room_in_the_gym(self):
        self.first()
        self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.4}])
        me = self.researcher()
        self.assertTrue(me._reserve_sweep("another-family", 24))
        out: dict = {"tool_calls": 0}
        view = me._gym_sweep(self.store.family(self.fid), {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.4}]}, out,
                             author="synthetic")
        self.assertEqual((view["status"], view["already_run"]), ("ok", ALREADY_RUN))
        self.assertNotIn("sweep_busy", out)
        mixed = {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.45}]}
        self.assertEqual(me._gym_sweep(self.store.family(self.fid), mixed, {"tool_calls": 0}, author="synthetic")["status"],
                         "refused", "the new variant needs room")
        me._release_sweep("another-family", 1)
        view = me._gym_sweep(self.store.family(self.fid), mixed, {"tool_calls": 0}, author="synthetic")
        self.assertEqual((view["status"], view["completed"]), ("ok", 2))
        self.assertEqual(me.sweep_room(), 1, "its room came back")

    def test_a_wholly_stored_sweep_in_a_cycle_keeps_the_revise_turn(self):
        self.first()
        self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.4}])
        self.steps = [{"calls": [("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.4}]})]},
                      {"calls": [("gym_run", {"hold": True, "note": "The grid is read; nothing new to try."})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required", "required"])
        self.assertEqual((out["stored"], out.get("trials", 0), out["hold"], out["dormant_cycles"]), (2, 0, True, 1))
        self.assertEqual(len(self.pool.train()), 3)


class Holds(DedupeCase):
    def test_a_hold_adds_nothing_and_ends_the_cycle(self):
        self.first()
        before = self.counts()
        why = "The mechanism needs an input the Gym lacks; nothing new to try."
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": why})]}, {"text": "never asked"}]
        out = self.researcher().cycle(self.fid)
        self.assertIn("hold", next(t for t in self.sail.bodies[0]["tools"] if t["name"] == "gym_run")["parameters"]["properties"])
        self.assertNotIn("error", out)
        self.assertEqual((out["hold"], out["model_calls"], out["tool_calls"]), (True, 1, 1), "a hold ends the cycle")
        self.assertEqual(len(self.pool.jobs), 1, "no Gym job")
        self.assertEqual(self.counts(), before, "no trial, no revision, no version")
        self.assertEqual(self.store.notebook(self.fid)[-1]["text"], f"Held a cycle (no run): {why}")
        self.assertIsNone(self.store.convo(self.fid)[1], "nothing queued")
        output = next(json.loads(i["output"]) for i in self.store.convo(self.fid)[0][-1]["items"]
                      if i.get("type") == "function_call_output")
        self.assertEqual(output["status"], "held")
        self.assertEqual((out["dormant_cycles"], dormant_count(self.store.family(self.fid))), (1, 1))
        event = [e for e in self.store.events_after(0) if e["kind"] == "swarm.cycle"][-1]["payload"]
        self.assertTrue(event["hold"])

    def test_a_hold_with_code_or_params_is_still_a_hold(self):
        """A model passing its current program beside hold=true is a plausible mistake: it holds (the dormancy clause counts
        it), never a refusal that would leave both idle clauses still."""
        self.first()
        before, notes = self.counts(), len(self.store.notebook(self.fid))
        for args, ignored in (({"hold": True, "params": {"vrp_min": 1.3}, "note": "Nothing new."}, "params"),
                              ({"hold": True, "code": self.code, "note": "Nothing new."}, "code"),
                              ({"hold": True, "code": self.code, "params": {"vrp_min": 1.3}}, "code and params")):
            view, out = self.run_(args)
            self.assertEqual(view["status"], "held")
            self.assertIn(f"its {ignored} were ignored", view["ignored"])
            self.assertTrue(out["hold"])
            self.assertNotIn("run_refused", out)
        self.assertEqual((len(self.pool.jobs), len(self.store.notebook(self.fid))), (1, notes + 3))
        self.assertEqual(self.counts(), before, "no trial, no revision, no version")

    def test_a_run_after_a_hold_in_the_same_answer_is_refused(self):
        self.first()
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Nothing new."}), ("gym_run", {"params": {"vrp_min": 1.3}}),
                                 ("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.4}]})]}, {"text": "never asked"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out["hold"], out.get("trials", 0), len(self.pool.jobs), out["pending_run"], out["model_calls"]),
                         (True, 0, 1, False, 1), "a hold ends the cycle: nothing runs or is queued after it")
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fid)[0][-1]["items"] if i.get("type") == "function_call_output"]
        self.assertEqual([o["status"] for o in outputs], ["held", "refused", "refused"])
        self.assertIn("after a hold", outputs[1]["reason"])
        self.assertEqual(out["dormant_cycles"], 1)

    def test_only_the_public_note_reaches_the_notebook_and_the_tape(self):
        self.first()
        view, out = self.run_({"hold": True, "why": "the private reason, never published"})
        self.assertEqual(view["status"], "held")
        self.assertEqual(self.store.notebook(self.fid)[-1]["text"], "Held a cycle (no run): nothing new to run")
        self.assertNotIn("note", out, "`why` is not marked PUBLIC: it never reaches the cycle's note")
        view, out = self.run_({"hold": True, "why": "private", "note": "Waiting on the breakdowns."})
        self.assertEqual((out["note"], self.store.notebook(self.fid)[-1]["text"]),
                         ("Waiting on the breakdowns.", "Held a cycle (no run): Waiting on the breakdowns."))

    def test_a_hold_on_the_read_turn_is_never_queued(self):
        self.first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_run", {"hold": True, "note": "Reading the breakdowns before the next change."})]},
                      {"text": "never asked"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out["hold"], out["pending_run"], out["model_calls"], out["trials"]), (True, False, 2, 1))
        self.assertEqual(dormant_count(self.store.family(self.fid)), 0, "the cycle made a new evaluation")

    def test_hold_reads_a_boolean_or_its_word(self):
        self.assertTrue(holding({"hold": True}))
        self.assertTrue(holding({"hold": "true"}))
        for args in ({}, {"hold": False}, {"hold": "false"}, {"hold": 1}, None, "hold"):
            self.assertFalse(holding(args), args)


class Dormancy(DedupeCase):
    """THE IDLE RULE's dormancy clause: `dormant_cycles` cycles in a row with only stored results, holds and refused runs
    make a family dead (the same floor, gate exemption and graveyard wording as the evaluation clause of #395)."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)  # one family alive: at the start, above the floor
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=10)  # ineligible: no best, nothing to validate
        self.cancelled: list = []
        self.pool.cancel_family = self.cancelled.append

    def hold(self, *, stored=False):
        """One dormant cycle: a hold, after the stored result of an unchanged re-run when `stored`."""
        hold = {"calls": [("gym_run", {"hold": True, "note": "Nothing new."})]}
        self.steps = [{"calls": [("gym_run", {"params": {}})]}, hold] if stored else [hold]
        return self.researcher().cycle(self.fid)

    def dormant(self, n):
        self.store.set_state(self.fid, dormant_cycles=n)
        return self.store.family(self.fid)

    def test_forty_dormant_cycles_make_the_family_dead(self):
        self.assertEqual((DORMANT_CYCLES, self.settings["researcher"]["dormant_cycles"], dormant_limit(self.settings)), (40, 40, 40))
        self.first()
        for i in range(39):
            out = self.hold(stored=bool(i % 2))
            self.assertEqual(out["dormant_cycles"], i + 1)
        fam = self.store.family(self.fid)
        self.assertEqual((fam["trials"], fam["revisions"]), (1, 1), "holds and stored results: no trial, no revision")
        self.assertIsNone(idle_dead(fam, self.settings), "39: not yet")
        self.assertFalse(self.researcher().can_retire(fam))
        self.hold()
        fam = self.store.family(self.fid)
        self.assertEqual(idle_dead(fam, self.settings), DEAD.format(n=40))
        self.assertTrue(self.researcher().can_retire(fam), "a dead family may retire at the start")
        status = self.researcher().status(fam)
        self.assertIn(f"Your family {DEAD.format(n=40)}", status)
        self.assertIn("Cycles in a row without a new Gym evaluation (only stored results, holds and refused runs): 40.", status)
        # A researcher that never calls retire: the tournament's fallback retires it with the idle rule's wording and,
        # since R11-1, the verdict of its Train record: it traded (10 a year), never enough to be eligible.
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(row["why"], f"It {DEAD.format(n=40)}. {idle_cause('thin')}")
        self.assertEqual((self.store.family(self.fid)["band"], self.cancelled), ("retired", [self.fid]))
        [lesson] = self.store.graveyard()
        self.assertIn("Retired by the idle rule", lesson["lesson"])
        self.assertIn("Idle verdict THIN, a tested finding", lesson["lesson"])
        self.assertNotIn("not a finding that the mechanism has no edge", lesson["lesson"], "tested: no longer a clock")
        [event] = [e for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(event["payload"]["cause"], f"{SCREENED}.", "the public cause carries no figure")

    def test_a_new_evaluation_restarts_the_count_and_a_gym_error_leaves_it(self):
        self.first()
        for _ in range(3):
            self.hold()
        self.pool.fail = "the Gym failed twice: exec 503"
        self.steps = [{"calls": [("gym_run", {"params": {}}), ("gym_run", {"params": {"vrp_min": 1.3}})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out["stored"], "gym_error" in out), (1, True))
        self.assertEqual(dormant_count(self.store.family(self.fid)), 3, "it asked for a new run the Gym could not make")
        self.pool.fail = None
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        self.researcher().cycle(self.fid)
        self.assertEqual(dormant_count(self.store.family(self.fid)), 0)

    def test_the_gate_exemption_and_the_floor_hold(self):
        self.first()
        fam = self.dormant(40)
        self.assertEqual(idle_dead(fam, self.settings), DEAD.format(n=40))
        self.store.set_state(self.fid, gate_ready=True)
        fam = self.store.family(self.fid)
        self.assertIsNone(idle_dead(fam, self.settings), "a validated version awaits the gate")
        self.assertFalse(self.researcher().can_retire(fam))
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])
        self.store.set_state(self.fid, gate_ready=False, look_inflight={"sha": "a-look", "n": 1, "token": "t"})
        self.assertIsNone(idle_dead(self.store.family(self.fid), self.settings), "a holdout look is out")
        self.store.set_state(self.fid, look_inflight=None)
        self.assertIsNotNone(idle_dead(self.store.family(self.fid), self.settings))
        self.settings["population"]["floor"] = 1
        self.assertFalse(self.researcher().can_retire(self.store.family(self.fid)), "at the floor: not offered")
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])
        self.assertIsNone(self.store.family(self.fid)["retired_at"])

    def test_a_best_awaiting_validation_is_not_dead(self):
        self.pool.answer = lambda job: result(job.name, roots=job.roots)  # eligible: the starter is the family's best
        self.first()
        fam = self.dormant(40)
        self.assertEqual(fam["best_version"], 1)
        self.assertTrue(awaiting_validation(fam), "its 1.5x run has not landed; the tournament has not validated it")
        self.assertIsNone(idle_dead(fam, self.settings))
        self.store.set_state(self.fid, robust_failed=[1])
        self.assertFalse(awaiting_validation(self.store.family(self.fid)), "it lost at 1.5x: it is never validated")
        self.assertEqual(idle_dead(self.store.family(self.fid), self.settings), DEAD.format(n=40), "whatever its best")
        self.store.set_state(self.fid, robust_failed=[])
        self.store.update_family(self.fid, validated_version=1)
        self.assertFalse(awaiting_validation(self.store.family(self.fid)), "validated: the verdict is in")
        self.assertIsNotNone(idle_dead(self.store.family(self.fid), self.settings))

    def test_off_and_misread_limits_turn_the_clause_off(self):
        self.first()
        fam = self.dormant(10 ** 6)
        for off in (0, None, -5, True, False, "many", [40], float("nan"), float("inf")):
            self.settings["researcher"]["dormant_cycles"] = off
            self.assertEqual(dormant_limit(self.settings), 0, repr(off))
            self.assertIsNone(idle_dead(fam, self.settings), repr(off))
        self.settings["researcher"]["dormant_cycles"] = 12.0
        self.assertEqual(dormant_limit(self.settings), 12)
        self.settings["researcher"].update(dormant_cycles=40, retire_idle_evaluations=0)
        self.assertEqual(idle_dead(fam, self.settings), DEAD.format(n=10 ** 6), "the evaluation clause off: dormancy still counts")


class DormancyAndValidation(RoundCase):
    def test_a_counted_validation_restarts_the_count_and_a_rejudge_does_not(self):
        self.answer = weak  # the line fails: nothing awaits the gate
        self.family("a")
        self.store.set_state("a", dormant_cycles=40)
        t = Tournament(self.store, self.pool, self.settings)
        t.validate(self.store.families(alive=True))
        self.assertEqual(dormant_count(self.store.family("a")), 0, "a verdict is news the researcher may act on")
        self.store.set_state("a", dormant_cycles=7)
        self.assertIsNotNone(t.judge("a", 1, t.recorded_validation("a", 1), record=False))
        self.assertEqual(dormant_count(self.store.family("a")), 7)


    def test_a_candidate_sent_back_to_the_gym_starts_its_dormant_count_afresh(self):
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        self.assertEqual(self.store.family("a")["band"], "candidate")
        self.store.set_state("a", dormant_cycles=45)
        self.store.add_forward("a", "shadow", [{"id": f"t{i}", "day": f"d{i:02d}", "pnl": -5.0, "max_loss": 60.0}
                                               for i in range(25)], version=1)
        self.assertEqual(Gate(self.store, self.pool, self.router, self.settings).judge_forward("a"), {"family": "a", "to": "gym"})
        fam = self.store.family("a")
        self.assertEqual((fam["band"], dormant_count(fam)), ("gym", 0))
        self.assertIsNone(idle_dead(fam, self.settings))


class GateHold(RoundCase):
    def ready(self, fid="a"):
        self.family(fid)
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"])

    def gate(self):
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def passing(self):
        self.replies = [{"text": json.dumps({"verdict": "pass", "reasons": []})}] * 2  # the review and the audit

    def test_a_held_family_is_not_looked_at_and_clearing_the_hold_lets_the_gate_proceed(self):
        self.ready()
        self.assertTrue(self.store.hold_gate("a", reason="the operator reads the program first"))
        self.assertFalse(self.store.hold_gate("no-such-family"))
        self.passing()
        for _ in range(2):
            out = self.gate().run()
            self.assertEqual((out["held"], out["looked"], out["refused"], out["waiting"]), (["a"], [], [], []))
        self.assertEqual((self.sail.bodies, self.asked), ([], []), "no review, no audit")
        self.assertFalse(any(j.window == "holdout" for j in self.pool.jobs), "no look")
        fam = self.store.family("a")
        self.assertTrue(fam["state"]["gate_ready"], "gate_ready is left as it is")
        self.assertEqual((fam["state"]["gate_hold"], fam["band"], self.store.looks()), (True, "gym", []))
        self.assertNotIn("review", fam["state"])
        [held] = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate"]
        self.assertEqual((held["action"], held["by"]), ("gate_hold", "operator"))
        # The status views say so: the researcher's status and the tournament's board.
        me = Researcher(self.store, self.router, self.pool, self.settings, contract="THE CONTRACT", clock=self.clock)
        self.assertIn("held by the operator", me.status(fam))
        self.assertIsNone(idle_dead({**fam, "state": {**fam["state"], "dormant_cycles": 10 ** 6}}, self.settings),
                          "held, it still awaits the gate: never dead")
        board = {r["family"]: r for r in Tournament(self.store, self.pool, self.settings).run()["board"]}
        self.assertEqual((board["a"]["gate"], board["a"]["gate_ready"]), ("held by the operator", True))
        # Cleared, the gate proceeds at its next round: review, audit, one look, a Candidate.
        self.assertTrue(self.store.hold_gate("a", False))
        out = self.gate().run()
        self.assertEqual((out["held"], out["looked"]), ([], [{"family": "a", "passed": True}]))
        self.assertEqual(self.store.family("a")["band"], "candidate")
        self.assertNotIn("held by the operator", me.status(self.store.family("a")))

    def test_a_held_family_awaiting_the_gate_is_retired_by_no_rule(self):
        """The review of R3: the hold spared a held family only the idle rule; the tournament's revision rule, its own
        researcher and the diagnostician could still retire it, and its held look would never happen."""
        self.ready()
        for fid in ("b", "c"):
            self.family(fid)
        self.settings["population"].update(start=1, floor=0)
        self.store.update_family("a", since_val_revisions=31, validations=2)
        self.store.hold_gate("a", reason="the operator reads the program first")
        self.assertTrue(held_at_gate(self.store.family("a")))
        t = Tournament(self.store, self.pool, self.settings)
        self.assertEqual(t.retirements(self.store.families(alive=True)), [])
        me = Researcher(self.store, self.router, self.pool, self.settings, contract="THE CONTRACT", clock=self.clock)
        self.assertFalse(me.can_retire(self.store.family("a")), "two validations above the start, but held")
        refused = self.store.retire_gym("a", "the diagnostician: no capturable edge", floor=0, source="diagnostician")
        self.assertEqual((refused["status"], refused["deferred"]), ("refused", "gate_hold"))
        self.assertIsNone(self.store.family("a")["retired_at"])
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        # Clearing the operator hold still leaves the actual gate work owed.
        self.store.hold_gate("a", False)
        self.assertFalse(me.can_retire(self.store.family("a")))
        self.assertEqual(t.retirements(self.store.families(alive=True)), [])
        self.store.set_state("a", gate_ready=False, extension_hold=None)
        self.assertTrue(me.can_retire(self.store.family("a")))
        [row] = t.retirements(self.store.families(alive=True))
        self.assertEqual((row["family"], row["why"]), ("a", "no validation improvement in 31 revisions"))

    def test_a_hold_without_gate_ready_protects_nothing(self):
        for fid in ("a", "b", "c"):
            self.family(fid)
        self.settings["population"].update(start=1, floor=0)
        self.store.update_family("a", since_val_revisions=31)
        self.store.hold_gate("a")
        self.assertFalse(held_at_gate(self.store.family("a")))
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(row["family"], "a")

    def test_a_hold_set_while_the_review_is_out_stops_the_next_stage(self):
        self.ready()

        def review_then_hold(body):
            self.store.hold_gate("a", reason="held while the review ran")
            return {"text": json.dumps({"verdict": "pass", "reasons": []})}

        self.sail.script = review_then_hold
        out = self.gate().run()
        self.assertEqual((len(self.sail.bodies), out["looked"]), (1, []), "the review ran; the audit after it did not")
        state = self.store.family("a")["state"]
        self.assertEqual((state["review"]["verdict"], state["gate_ready"]), ("pass", True), "the paid review is kept")
        self.assertFalse(any(j.window == "holdout" for j in self.pool.jobs))
        self.sail.script = lambda body: {"text": json.dumps({"verdict": "pass", "reasons": []})}
        self.assertEqual(self.gate().run()["held"], ["a"])
        self.store.hold_gate("a", False)
        out = self.gate().run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}])
        self.assertEqual(len(self.sail.bodies), 2, "the review was not asked again: only the audit")

    def test_the_operator_holds_and_clears_from_the_command_line(self):
        self.ready()

        def cli(*argv):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = swarm_main(list(argv))
            return code, json.loads(buf.getvalue())

        code, answer = cli("hold-gate", "--root", str(self.root), "--family", "a", "--reason", "reading the program")
        self.assertEqual((code, answer), (0, {"family": "a", "found": True, "gate_hold": True, "gate_ready": True,
                                              "retire_exempt": True}))
        code, status = cli("status", "--root", str(self.root))
        self.assertEqual(status["gate_held"], [{"family": "a", "gate": "held by the operator", "gate_ready": True}])
        self.assertEqual(self.gate().run()["held"], ["a"])
        code, answer = cli("hold-gate", "--root", str(self.root), "--family", "a", "--clear")
        self.assertEqual((code, answer["gate_hold"], answer["retire_exempt"]), (0, False, False))
        self.assertEqual(cli("status", "--root", str(self.root))[1]["gate_held"], [])
        self.assertEqual(cli("hold-gate", "--root", str(self.root), "--family", "nobody")[0], 1)
        self.assertEqual(cli("hold-gate", "--root", str(self.root))[0], 2)


class HeldProgress(ProgressCase):
    def test_a_held_family_shows_the_gate_paused_on_the_public_checklist(self):
        self.family()
        self.assertEqual(self.read()["blocked"], "holdout_pending")
        self.store.hold_gate("synthetic-family", reason="private reason never published")
        value = self.read()
        self.assertEqual(value["blocked"], "gate_paused", "the site's closed list has no key of its own for a hold")
        self.assertEqual(progress.clean(value, band="gym"), value)
        self.assertNotIn("private reason", json.dumps(value))
        self.store.hold_gate("synthetic-family", False)
        self.assertEqual(self.read()["blocked"], "holdout_pending")


class MixedSweeps(SweepCase):
    """The review of R3: a sweep that mixes stored variants with new ones, and none of the new ones lands, is a Gym error:
    no run for the cycle (no READ turn), a backoff, and no dormant cycle."""

    def setUp(self):
        super().setUp()
        self.first()
        self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.4}])  # stored from here on
        self.store.set_state(self.fid, dormant_cycles=3)

    @staticmethod
    def failing(why):
        return lambda job: why if job.params.get("vrp_min") == 1.45 else None

    def test_every_new_variant_failing_is_a_gym_error_whatever_the_store_read_back(self):
        self.pool.fail = self.failing("the Gym failed twice: exec 503")
        view, out = self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.4}, {"vrp_min": 1.45}])
        self.assertEqual(view["status"], "gym_error")
        self.assertIn("the Gym failed twice", view["error"])
        self.assertIn("2 of its variants already ran", view["already_run"])
        self.assertEqual((out.get("trials", 0), "run_id" in out, out["gym_asked"], "gym_error" in out), (0, False, True, True))

    def test_in_a_cycle_it_stops_backs_off_and_leaves_the_dormant_count(self):
        self.pool.fail = self.failing("the Gym failed twice: exec 503")
        self.steps = [{"calls": [("gym_sweep", {"variants": [{}, {"vrp_min": 1.3}, {"vrp_min": 1.45}]})]}, {"text": "never asked"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual([b["tool_choice"] for b in self.sail.bodies], ["required"], "no READ turn: nothing new ran")
        self.assertIn("gym:", out["error"], "the family backs off")
        self.assertNotIn("run_id", out)
        self.assertNotIn("dormant_cycles", out)
        self.assertEqual(dormant_count(self.store.family(self.fid)), 3, "the Gym could not make what was asked")

    def test_a_new_variant_landing_late_is_no_dormant_cycle_and_its_trial_restarts_the_count(self):
        self.pool.fail = self.failing("late")
        self.steps = [{"calls": [("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.45}]})]}]
        out = self.researcher().cycle(self.fid)
        self.assertIn("gym_error", out)
        self.assertEqual(dormant_count(self.store.family(self.fid)), 3)
        trials = self.store.family(self.fid)["trials"]
        [(late, landed)] = self.pool.lates
        late(landed)
        fam = self.store.family(self.fid)
        self.assertEqual((fam["trials"], dormant_count(fam)), (trials + 1, 0), "the late trial is a new evaluation")

    def test_a_mixed_sweep_whose_new_variant_lands_is_a_run(self):
        view, out = self.sweep([{"vrp_min": 1.3}, {"vrp_min": 1.45}])
        self.assertEqual((view["status"], out["trials"], out["stored"]), ("ok", 1, 1))
        self.assertIn("run_id", out)
        self.assertEqual(dormant_count(self.store.family(self.fid)), 0, "reset as the new variant was recorded")


class DormancyReview(DedupeCase):
    """The review of R3's dormancy clause: counted in the Gym band only, reset as soon as a new evaluation is recorded,
    and refusal-only cycles count."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=10)  # ineligible: nothing awaits validation
        self.pool.cancel_family = lambda fid: None

    def hold(self):
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Nothing new."})]}]
        return self.researcher().cycle(self.fid)

    def test_a_candidate_holding_is_not_dormant_and_starts_afresh_back_in_the_gym(self):
        self.first()
        self.store.set_state(self.fid, dormant_cycles=10)
        self.store.set_band(self.fid, "candidate", reason="passed its holdout look")
        for _ in range(45):
            out = self.hold()
            self.assertNotIn("dormant_cycles", out)
        self.assertEqual(dormant_count(self.store.family(self.fid)), 0, "holding while its forward record is measured")
        self.store.set_band(self.fid, "gym", reason="its forward record turned negative")
        fam = self.store.family(self.fid)
        self.assertIsNone(idle_dead(fam, self.settings))
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])

    def test_a_new_evaluation_restarts_the_count_before_the_read_turn(self):
        self.first()
        self.store.set_state(self.fid, dormant_cycles=45)
        self.assertTrue(self.researcher().can_retire(self.store.family(self.fid)), "dead at the cycle's start")
        seen: dict = {}

        def read(body):
            seen.update(dormant=dormant_count(self.store.family(self.fid)), tools=[t["name"] for t in body["tools"]])
            return {"calls": [("retire", {"reason": "the mechanism is dead"})]}

        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, read]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(seen["dormant"], 0, "reset as the run was recorded")
        self.assertNotIn("retire", seen["tools"], "not offered on the READ turn after a new run")
        self.assertTrue(out["retire_refused"])
        self.assertIsNone(self.store.family(self.fid)["retired_at"])

    def test_cycles_of_refused_runs_are_dormant(self):
        self.first()
        broken = "import os\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
        for i in range(3):
            self.steps = [{"calls": [("gym_run", {"code": broken})]}] * 3
            out = self.researcher().cycle(self.fid)
            self.assertEqual((out["run_refused"], out.get("trials", 0), out["dormant_cycles"]), (3, 0, i + 1))
        self.steps = [{"calls": [("gym_run", {"hold": True, "code": self.code, "note": "Nothing new."})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out["hold"], out["dormant_cycles"]), (True, 4), "a hold with code is a hold")
        self.assertEqual(len(self.pool.jobs), 1)
        self.store.set_state(self.fid, dormant_cycles=40)
        self.assertEqual(idle_dead(self.store.family(self.fid), self.settings), DEAD.format(n=40))

    def test_a_sweep_refused_for_room_leaves_the_count_unless_the_cycle_also_held(self):
        self.first()
        me = self.researcher()
        self.assertTrue(me._reserve_sweep("another-family", me.max_sweep_jobs))
        sweep = ("gym_sweep", {"variants": [{"vrp_min": 1.3}, {"vrp_min": 1.4}]})
        self.steps = [{"calls": [sweep]}] * 3
        out = me.cycle(self.fid)
        self.assertTrue(out["sweep_busy"])
        self.assertNotIn("run_refused", out, "the Gym's load, not the researcher's doing")
        self.assertNotIn("dormant_cycles", out)
        self.assertEqual(dormant_count(self.store.family(self.fid)), 0)
        self.steps = [{"calls": [sweep]}, {"calls": [("gym_run", {"hold": True, "note": "Nothing new."})]}]
        out = me.cycle(self.fid)
        self.assertEqual((out["sweep_busy"], out["hold"], out["dormant_cycles"]), (True, True, 1))


if __name__ == "__main__":
    import unittest

    unittest.main()
