"""Explicit abandonment retains evidence, serializes population decisions, and ends only research work."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from league.swarm.architect import Architect
from league.swarm.gate import Gate
from league.swarm.researcher import RETIRE_IDLE_EVALUATIONS, Researcher, idle_dead, idle_evaluations, idle_limit
from league.swarm.seeds import family_spec
from league.swarm.store import SwarmStore
from league.swarm.tournament import IDLE_CAUSE, Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase, strong, weak
from league.tests.test_swarm_store import StoreCase, SPEC
from league.tests.test_swarm_pool import PoolCase, job as pool_job


class StoreRetirement(StoreCase):
    def retire(self, store, fid, floor=0):
        return store.retire_gym(fid, "The mechanism does not survive its rejection test.", floor=floor, source="researcher")

    def test_duplicate_retirement_preserves_evidence_and_pending_look_but_clears_research(self):
        fam = self.store.add_family(SPEC, origin="seed")
        fid = fam["id"]
        version = self.store.add_version(fid, "PARAMS = {'secret_level': 7}\n", {}, author="synthetic")
        self.store.update_family(fid, best_version=version["n"])
        self.store.add_run(fid, 1, result("before"), window="train", stress=1, purpose="train")
        self.store.add_look(fid, 1, "previous-look", passed=False, p_value=.4, detail={})
        marker = {"sha": "pending-look", "n": 1, "token": "synthetic"}
        self.store.set_state(fid, look_inflight=marker, rewrite_ready={"code": "private rewrite"})
        self.store.save_convo(fid, [{"cycle": 1, "items": []}], {"arguments": {"code": "pending"}})
        before = (self.store.lineage_trials(fid), self.store.lineage_looks(fid, include_inflight=True))
        self.assertFalse(self.retire(self.store, fid)["already_retired"])
        self.assertTrue(self.retire(self.store, fid)["already_retired"])
        after = self.store.family(fid)
        self.assertEqual((self.store.lineage_trials(fid), self.store.lineage_looks(fid, include_inflight=True)), before)
        self.assertEqual((after["best_version"], self.store.versions(fid)[0]["sha"]), (1, version["sha"]))
        self.assertEqual(after["state"]["look_inflight"], marker)
        self.assertIsNone(after["state"]["rewrite_ready"])
        self.assertIsNone(self.store.convo(fid)[1])
        self.assertEqual(len(self.store.graveyard()), 1)
        self.assertEqual(len(self.store.notebook(fid)), 1)
        self.assertEqual([e["kind"] for e in self.store.events_after(0)], ["swarm.retired"])
        self.assertIsNone(self.store.set_band(fid, "candidate", reason="stale promotion"))

    def test_candidate_probe_and_sized_refusals_change_no_state(self):
        for band in ("candidate", "probe", "sized"):
            fam = self.store.add_family({**SPEC, "id": band}, origin="seed")
            self.store.set_band(fam["id"], band, reason="synthetic")
            self.store.save_convo(fam["id"], [], {"arguments": {}})
            before = self.store.family(fam["id"])
            events = self.store.events_after(0)
            self.assertEqual(self.retire(self.store, fam["id"])["status"], "refused")
            self.assertEqual(self.store.family(fam["id"]), before)
            self.assertEqual(self.store.convo(fam["id"])[1], {"arguments": {}})
            self.assertEqual(self.store.events_after(0), events)
            self.assertEqual(self.store.notebook(fam["id"]), [])

    def test_nonstring_and_empty_reasons_are_refused_without_writes(self):
        fid = self.store.add_family(SPEC, origin="seed")["id"]
        before = self.store.family(fid)
        for reason in (None, "", "  ", 7, [], {}):
            self.assertEqual(self.store.retire_gym(fid, reason, floor=0, source="researcher")["status"], "refused")
        self.assertEqual(self.store.family(fid), before)
        self.assertEqual((self.store.events_after(0), self.store.graveyard(), self.store.notebook(fid)), ([], [], []))

    def test_two_connections_cannot_retire_below_the_same_floor(self):
        ids = [self.store.add_family({**SPEC, "id": f"f{i}"}, origin="seed")["id"] for i in range(3)]
        other = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(other.close)
        start = threading.Barrier(2)

        def retire(store, fid):
            start.wait()
            return self.retire(store, fid, floor=2)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(retire, store, fid) for store, fid in zip((self.store, other), ids)]
            statuses = sorted(f.result()["status"] for f in futures)
        self.assertEqual(statuses, ["refused", "retired"])
        self.assertEqual(len(self.store.families(alive=True)), 2)

    def test_promotion_wins_before_retirement_and_retirement_blocks_a_stale_save(self):
        fid = self.store.add_family(SPEC, origin="seed")["id"]
        other = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(other.close)
        self.assertEqual(other.set_band(fid, "candidate", reason="gate won"), "gym")
        before = self.store.family(fid)
        self.assertEqual(self.retire(self.store, fid)["status"], "refused")
        self.assertEqual(self.store.family(fid), before)
        other.set_band(fid, "gym", reason="synthetic demotion")
        self.retire(other, fid)
        self.store.save_convo(fid, [{"cycle": 2, "items": []}], {"arguments": {"code": "stale"}})
        self.assertIsNone(self.store.convo(fid)[1])
        self.assertEqual(self.store.convo(fid)[0][0]["cycle"], 2, "history survives; runnable work does not")

    def test_fitted_reason_is_private_and_the_public_event_uses_strict_filtering(self):
        fid = self.store.add_family(SPEC, origin="seed")["id"]
        self.store.add_version(fid, "PARAMS = {'secret_level': 7}\n", {}, author="synthetic")
        reason = "The secret level was seven. The measured count was 123. Costs defeated the mechanism."
        self.store.retire_gym(fid, reason, floor=0, source="researcher")
        public = json.dumps(self.store.events_after(0))
        self.assertNotIn("seven", public)
        self.assertNotIn("123", public)
        self.assertNotIn("secret level", public)
        self.assertIn("Costs defeated the mechanism.", public)
        self.assertIn(reason, self.store.notebook(fid)[0]["text"])
        self.assertIn(reason, self.store.graveyard()[0]["lesson"])


class ResearcherRetirement(ResearcherCase):
    """`retire` is offered on a READ turn only above `population.start` with two validations (the sprint, Sept 26); these
    cases put the family there (start 0, two validations) unless they test the guard itself."""

    def setUp(self):
        super().setUp()
        self.settings["population"]["floor"] = 0
        self.settings["population"]["start"] = 0
        self.store.update_family(self.fam["id"], validations=2)
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append

    def final_call(self):
        return ("retire", {"reason": "Costs defeated the mechanism."})

    def tools_of(self, body):
        return [t["name"] for t in body["tools"]]

    def test_a_retire_on_the_revise_turn_is_refused_and_the_revision_runs(self):
        self.researcher().cycle(self.fam["id"])
        self.steps = [{"calls": [self.final_call(), ("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertNotIn("retired", out)
        self.assertNotIn("error", out, "a refused retire is never a cycle error")
        self.assertEqual(self.tools_of(self.sail.bodies[0]), ["gym_run"], "REVISE never offers retire")
        self.assertEqual(len(self.pool.jobs), 2, "the revision ran")
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fam["id"])[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        self.assertEqual(outputs[0]["status"], "refused")
        self.assertEqual(self.store.family(self.fam["id"])["band"], "gym")

    def test_retire_is_offered_on_read_only_above_the_start_with_two_validations(self):
        self.researcher().cycle(self.fam["id"])
        for start, validations, offered in ((0, 2, True), (1, 2, False), (0, 1, False)):
            self.settings["population"]["start"] = start
            self.store.update_family(self.fam["id"], validations=validations)
            self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3 + validations / 10 + start}})]}, {"text": "read it"}]
            self.researcher().cycle(self.fam["id"])
            self.assertEqual("retire" in self.tools_of(self.sail.bodies[-1]), offered, (start, validations))
            status = next(i["content"] for i in reversed(self.sail.bodies[-1]["input"])
                          if i.get("role") == "user" and "Now: if a run just came back" in str(i.get("content")))
            self.assertEqual("call retire" in status, offered)

    def test_a_retire_on_read_is_terminal_and_restart_skips_it(self):
        self.researcher().cycle(self.fam["id"])
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [self.final_call(), ("notebook", {"action": "append", "text": "Should never run"})]}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out["retired"])
        self.assertEqual(self.cancelled, [self.fam["id"]])
        items = self.store.convo(self.fam["id"])[0][-1]["items"]
        calls = [i["call_id"] for i in items if i.get("type") == "function_call"]
        outputs = [i for i in items if i.get("type") == "function_call_output"]
        self.assertEqual([i["call_id"] for i in outputs], calls)
        self.assertEqual([json.loads(i["output"]).get("status") for i in outputs][-2:], ["retired", "refused"])
        self.assertEqual(self.researcher().cycle(self.fam["id"])["skipped"], "retired")
        self.assertEqual(len(self.store.notebook(self.fam["id"])), 1)

    def test_read_retirement_cancels_an_earlier_queued_run_and_keeps_the_completed_run(self):
        researcher = self.researcher()
        researcher.cycle(self.fam["id"])
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.5}}), self.final_call(), ("submit", {"run_id": "ignored"})]}]
        out = researcher.cycle(self.fam["id"])
        self.assertEqual((out["trials"], len(self.pool.jobs), out["pending_run"]), (1, 2, False))
        self.assertEqual(self.store.family(self.fam["id"])["best_version"], 1)
        self.assertIsNone(self.store.convo(self.fam["id"])[1])
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fam["id"])[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        self.assertEqual([r.get("status") for r in outputs][-3:], ["cancelled", "retired", "refused"])
        self.assertEqual(len([e for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]), 1)
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.note"], [])

    def test_a_floor_refusal_is_no_cycle_error_and_no_backoff(self):
        from league.swarm.loop import Scheduler

        self.settings["population"]["floor"] = 1  # offered (start 0), then refused by the store's floor
        self.researcher().cycle(self.fam["id"])
        scheduler = Scheduler(self.store, clock=self.clock)
        self.assertEqual(scheduler.take(), self.fam["id"])
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"calls": [self.final_call()]}, {"text": "ok"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertNotIn("retired", out)
        self.assertNotIn("error", out)
        self.assertTrue(out["retire_refused"])
        self.assertEqual(self.store.family(self.fam["id"])["band"], "gym")
        scheduler.release(self.fam["id"], out)
        self.clock.advance(5)
        self.assertEqual(scheduler.take(), self.fam["id"], "no cooldown: the family's next cycle comes at once")
        self.assertEqual(self.store.graveyard(), [])

    def test_a_floor_refusal_keeps_an_earlier_queued_run(self):
        self.settings["population"]["floor"] = 1
        self.researcher().cycle(self.fam["id"])
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.5}}), self.final_call()]}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out["pending_run"], "the refusal changes nothing: the queued run opens the next cycle")
        self.assertIsNotNone(self.store.convo(self.fam["id"])[1])
        self.assertEqual(out["trials"], 1)

    def test_retirement_during_a_model_request_refuses_all_returned_tools(self):
        self.researcher().cycle(self.fam["id"])
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)

        def retire_inflight(body):
            other.retire_gym(self.fam["id"], "The mechanism failed.", floor=0, source="tournament")
            return {"calls": [("gym_run", {"params": {"vrp_min": 1.3}}), ("notebook", {"action": "append", "text": "late"})]}

        self.steps = [retire_inflight]
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out["retired"])
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertIsNone(self.store.convo(self.fam["id"])[1])
        self.assertGreater(out["cost_usd"], 0, "the accepted model request is still charged")

    def test_a_train_result_after_retirement_counts_without_changing_the_best(self):
        self.researcher().cycle(self.fam["id"])
        before = self.store.family(self.fam["id"])

        def retire_during_run(job):
            self.store.retire_gym(job.family, "The mechanism failed.", floor=0, source="tournament")
            return result(job.name, mean=5.0, t=10.0)

        self.pool.answer = retire_during_run
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}]
        out = self.researcher().cycle(self.fam["id"])
        after = self.store.family(self.fam["id"])
        self.assertTrue(out["retired"])
        self.assertEqual(after["trials"], before["trials"] + 1)
        self.assertEqual((after["best_train"], after["best_version"]), (before["best_train"], before["best_version"]))
        self.assertEqual(out["model_calls"], 1)

    def test_a_rewrite_finishing_after_retirement_is_private_evidence_not_a_pending_run(self):
        self.researcher().cycle(self.fam["id"])
        self.store.update_family(self.fam["id"], stall=5)

        def retire_during_rewrite(body):
            self.store.retire_gym(self.fam["id"], "The mechanism failed.", floor=0, source="researcher")
            return {"text": "```python\n" + self.code + "\n```"}

        self.steps = [retire_during_rewrite]
        self.researcher().cycle(self.fam["id"])
        state = self.store.family(self.fam["id"])["state"]
        self.assertIsNone(state["rewrite_ready"])
        self.assertEqual(state["rewrite_after_retirement"]["code"].strip(), self.code.strip())
        self.assertEqual(len(self.sail.bodies), 1)
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertEqual(self.researcher().cycle(self.fam["id"])["skipped"], "retired")


class ResearcherIdleRetirement(ResearcherCase):
    """THE IDLE RULE (R3, Sept 27): a dead family (`retire_idle_evaluations` Gym evaluations since its birth or last
    validation without an eligible Train version, or three times as many with a best Train score below zero; never while
    a validated version awaits the gate) may retire with the population AT its start; only `population.floor` holds it.
    Every Train run here is ineligible (10 trades a year) unless a case says otherwise."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=1, floor=0)  # one family alive: at the start, above the floor
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=10)
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append

    def idle(self, evaluations=RETIRE_IDLE_EVALUATIONS, fid=None):
        self.store.update_family(fid or self.fam["id"], since_val_trials=evaluations)

    def read_turn(self, *calls, researcher=None, params=None):
        """One cycle: a REVISE (a new version: one more evaluation), then a READ turn making `calls`."""
        self.read_body = len(self.sail.bodies) + 1
        self.steps = [{"calls": [("gym_run", {"params": params or {"vrp_min": 1.3}})]}, {"calls": list(calls)}, {"text": "ok"}]
        return (researcher or self.researcher()).cycle(self.fam["id"])

    def offered(self):
        return "retire" in [t["name"] for t in self.sail.bodies[self.read_body]["tools"]]

    def status(self):
        """The cycle's status (written before its REVISE turn: the idle count before the new evaluation)."""
        return next(i["content"] for i in reversed(self.sail.bodies[self.read_body]["input"])
                    if i.get("role") == "user" and "Now: if a run just came back" in str(i.get("content")))

    def test_the_default_counts_evaluations(self):
        self.assertEqual(self.settings["researcher"]["retire_idle_evaluations"], RETIRE_IDLE_EVALUATIONS)
        self.assertEqual(RETIRE_IDLE_EVALUATIONS, 150)
        self.assertNotIn("retire_idle_revisions", self.settings["researcher"])

    def test_a_dead_family_retires_at_the_start_and_its_lesson_is_written(self):
        self.researcher().cycle(self.fam["id"])
        fam = self.store.family(self.fam["id"])
        self.assertIsNone(fam["best_train"], "no eligible Train version")
        self.assertEqual(fam["validations"], 0, "the old rule (two validations, above the start) would refuse")
        self.idle(150)
        reason = "The mechanism made 10 trades a year at best. Condors on this root are dead."
        out = self.read_turn(("retire", {"reason": reason}))
        self.assertTrue(self.offered(), "READ offers retire to a dead family at the start")
        self.assertIn("made no eligible Train version in 150 Gym evaluations since its birth", self.status())
        self.assertTrue(out["retired"])
        self.assertNotIn("error", out)
        self.assertEqual(self.store.family(self.fam["id"])["band"], "retired")
        self.assertEqual(self.cancelled, [self.fam["id"]])
        [lesson] = self.store.graveyard()
        self.assertIn(reason, lesson["lesson"])
        self.assertIn("Tried 2 versions", lesson["lesson"])
        self.assertIn(f"Retired by researcher: {reason}", self.store.notebook(self.fam["id"])[-1]["text"])
        [event] = [e for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(event["payload"]["cause"], "Condors on this root are dead.", "a figure never reaches the public cause")

    def test_below_the_idle_count_the_old_rule_still_applies(self):
        self.researcher().cycle(self.fam["id"])
        self.idle(148)  # the REVISE turn's new evaluation makes 149
        out = self.read_turn(("retire", {"reason": "Costs defeated the mechanism."}))
        self.assertEqual(self.store.family(self.fam["id"])["since_val_trials"], 149)
        self.assertFalse(self.offered())
        self.assertNotIn("eligible Train version in", self.status())
        self.assertTrue(out["retire_refused"])
        self.assertIsNone(self.store.family(self.fam["id"])["retired_at"])

    def test_a_family_that_loops_one_placeholder_is_counted_by_its_evaluations(self):
        """The case the rule is for (live: hundreds of cycles on a dozen versions): an unchanged program re-run makes no
        new version (the store returns the existing one), but every evaluation is a trial and counts. The Gym answers an
        identical re-run with the same run_id: the store keeps one row and still counts the trial."""
        self.settings["researcher"]["retire_idle_evaluations"] = 12
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots, trades=0), "run_id": "one-placeholder"}
        self.researcher().cycle(self.fam["id"])  # the starter: version 1
        for _ in range(12):  # twelve cycles re-running the latest version unchanged (no `code`, the same params)
            self.steps = [{"calls": [("gym_run", {"params": {}})]}, {"text": "holding dormant"}]
            self.researcher().cycle(self.fam["id"])
        fam = self.store.family(self.fam["id"])
        self.assertLessEqual(fam["revisions"], 2, "re-runs make no new version")
        self.assertEqual(fam["trials"], 13)
        self.assertEqual(len(self.store.runs(self.fam["id"], window="train", limit=50)), 1, "one row, every trial counted")
        self.assertEqual(idle_evaluations(fam), 13)
        self.assertEqual(idle_dead(fam, self.settings), "made no eligible Train version in 13 Gym evaluations since its birth")
        self.assertTrue(self.researcher().can_retire(fam))
        # A researcher that never calls retire: the tournament's fallback retires it by the same rule.
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(row["family"], self.fam["id"])
        self.assertEqual(self.store.family(self.fam["id"])["band"], "retired")
        self.assertEqual(self.cancelled, [self.fam["id"]])

    def test_a_family_with_an_eligible_version_cannot_retire_under_the_idle_rule(self):
        self.pool.answer = lambda job: result(job.name, roots=job.roots)  # eligible: a positive best Train score
        self.researcher().cycle(self.fam["id"])
        self.idle(1000)
        out = self.read_turn(("retire", {"reason": "Costs defeated the mechanism."}))
        fam = self.store.family(self.fam["id"])
        self.assertGreater(fam["best_train"], 0)
        self.assertIsNone(idle_dead(fam, self.settings))
        self.assertFalse(self.offered(), "at the start with no validations: the old rule refuses, the idle rule does not apply")
        self.assertTrue(out["retire_refused"])
        self.assertNotIn("error", out)
        self.assertIsNone(fam["retired_at"])
        self.assertEqual(self.store.graveyard(), [])

    def test_a_best_train_score_below_zero_counts_only_after_three_times_the_limit(self):
        """A negative best only says every eligible version so far lost in its worst Train year: a normal stage of a
        family's ramp, so it gets three times as long as a family with no eligible version at all."""
        fam = {**self.store.family(self.fam["id"]), "since_val_trials": 150}
        self.assertIn("no eligible Train version in 150 Gym evaluations", idle_dead({**fam, "best_train": None}, self.settings))
        self.assertIsNone(idle_dead({**fam, "best_train": -0.4}, self.settings), "negative at the limit: still ramping")
        self.assertIsNone(idle_dead({**fam, "best_train": -0.4, "since_val_trials": 3 * 150 - 1}, self.settings))
        self.assertEqual(idle_dead({**fam, "best_train": -0.4, "since_val_trials": 450}, self.settings),
                         "kept its best Train score below zero over 450 Gym evaluations since its birth")
        self.assertIsNone(idle_dead({**fam, "best_train": 0.0, "since_val_trials": 10 ** 6}, self.settings))
        self.assertIsNone(idle_dead({**fam, "best_train": None, "band": "candidate"}, self.settings))

    def test_off_and_misread_limits_turn_the_rule_off(self):
        fam = {**self.store.family(self.fam["id"]), "best_train": None, "since_val_trials": 10 ** 6}
        for off in (0, None, -5, True, False, "many", [150], float("nan"), float("inf")):
            self.settings["researcher"]["retire_idle_evaluations"] = off
            self.assertEqual(idle_limit(self.settings), 0, repr(off))
            self.assertIsNone(idle_dead(fam, self.settings), f"{off!r} turns the rule off (true is not a limit of one)")
        self.settings["researcher"]["retire_idle_evaluations"] = 200.0
        self.assertEqual(idle_limit(self.settings), 200)
        del self.settings["researcher"]["retire_idle_evaluations"]
        self.assertEqual(idle_limit(self.settings), RETIRE_IDLE_EVALUATIONS, "absent: the default")

    def test_the_idle_count_starts_again_at_each_validation(self):
        fam = {**self.store.family(self.fam["id"]), "best_train": None, "trials": 170, "since_val_trials": 170, "validations": 1}
        self.assertEqual(idle_evaluations(fam), 170, "no validation mark (a family validated before R3): since_val_trials")
        marked = {**fam, "state": {"validated_trials": 40}}
        self.assertEqual(idle_evaluations(marked), 130)
        self.assertIsNone(idle_dead(marked, self.settings))
        self.assertEqual(idle_dead({**marked, "trials": 190}, self.settings),
                         "made no eligible Train version in 150 Gym evaluations since its last validation")
        self.assertEqual(idle_evaluations({**marked, "state": {"validated_trials": True}}), 170, "a boolean is no mark")

    def test_a_family_whose_validated_version_awaits_the_gate_is_never_dead(self):
        """A validation can pass on a version whose best Train score is below zero (the 1.5x gate checks P&L): while
        its audit or holdout look is owed or out, the gate decides, not the clock."""
        self.researcher().cycle(self.fam["id"])
        self.store.update_family(self.fam["id"], best_train=-0.5, validations=1)
        self.idle(460)  # past three times the limit, short of the tournament's own evaluation rule
        self.store.set_state(self.fam["id"], gate_ready=True)
        self.assertIsNone(idle_dead(self.store.family(self.fam["id"]), self.settings))
        out = self.read_turn(("retire", {"reason": "Dead."}))
        self.assertFalse(self.offered())
        self.assertNotIn("Gym evaluations since", self.status())
        self.assertTrue(out["retire_refused"])
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])
        self.store.set_state(self.fam["id"], gate_ready=False, look_inflight={"sha": "a-look", "n": 1, "token": "t"})
        self.assertIsNone(idle_dead(self.store.family(self.fam["id"]), self.settings), "a holdout look is out")
        self.store.set_state(self.fam["id"], look_inflight=None)
        self.assertIn("below zero", idle_dead(self.store.family(self.fam["id"]), self.settings), "the gate refused it: dead")

    def test_the_floor_still_holds_for_a_dead_family(self):
        self.settings["population"]["floor"] = 1
        self.researcher().cycle(self.fam["id"])
        self.idle(150)
        out = self.read_turn(("retire", {"reason": "The mechanism is dead."}))
        self.assertFalse(self.offered(), "at the floor: not offered")
        self.assertTrue(out["retire_refused"])
        self.assertNotIn("eligible Train version in", self.status(), "no nudge while the family may not retire")
        # A stale "above the floor" read: the store's own count refuses at the floor (the dead family's floor, not the start).
        r = self.researcher()
        self.assertEqual(r.retire_floor(self.store.family(self.fam["id"])), 1)
        r.can_retire = lambda fam: True
        out = self.read_turn(("retire", {"reason": "Dead."}), researcher=r, params={"vrp_min": 1.5})
        self.assertTrue(out["retire_refused"])
        self.assertNotIn("error", out)
        self.assertIsNone(self.store.family(self.fam["id"])["retired_at"])
        self.assertEqual(self.store.graveyard(), [])

    def test_a_dead_familys_retirement_goes_below_the_start_down_to_the_floor_only(self):
        other = self.store.add_family({**family_spec(self.spec), "id": "other-dead"}, origin="seed")
        self.settings["population"].update(start=2, floor=1)
        self.researcher().cycle(self.fam["id"])
        self.idle(150)
        self.idle(150, fid=other["id"])
        self.assertTrue(self.researcher().can_retire(self.store.family(other["id"])))
        out = self.read_turn(("retire", {"reason": "The mechanism is dead."}))
        self.assertTrue(out["retired"])
        self.assertEqual(len(self.store.families(alive=True)), 1, "below the start (2), at the floor (1)")
        self.assertFalse(self.researcher().can_retire(self.store.family(other["id"])), "the floor holds the last one")


class TournamentIdleRetirement(RoundCase):
    """The tournament's fallback for a dead family that never calls retire: the same idle rule, down to the floor only."""

    def setUp(self):
        super().setUp()
        # The operator's running swarm.json keeps the old rules far out; the idle rule acts on its own.
        self.settings["tournament"].update(retire_revisions=200, retire_evaluations=10 ** 6)

    def test_dead_families_retire_at_the_start_down_to_the_floor_and_the_rest_stay(self):
        for i in range(7):
            self.family(f"f{i}")
        self.settings["population"].update(start=7, floor=4)
        for fid in ("f0", "f2", "f3", "f4", "f6"):
            self.store.update_family(fid, since_val_trials=150)
        self.store.update_family("f1", since_val_trials=450, best_train=-0.3)  # dead: below zero for three times the limit
        self.store.update_family("f3", best_train=1.2)                          # an eligible version with a positive score
        self.store.update_family("f5", since_val_trials=149)                    # one evaluation short
        self.store.update_family("f6", best_train=-0.3)                         # below zero, still ramping
        self.store.note("f0", "the placeholder never trades")
        t = Tournament(self.store, self.pool, self.settings)
        out = t.retirements(self.store.families(alive=True))
        self.assertEqual([r["family"] for r in out], ["f0", "f1", "f2"])
        self.assertEqual(sorted(f["id"] for f in self.store.families(alive=True)), ["f3", "f4", "f5", "f6"])
        self.assertEqual(out[0]["why"], f"It made no eligible Train version in 150 Gym evaluations since its birth. {IDLE_CAUSE}")
        self.assertIn("kept its best Train score below zero over 450 Gym evaluations", out[1]["why"])
        self.assertIn("f0", self.pool.cancelled)
        lesson = self.store.graveyard("placeholder")[0]
        self.assertEqual(lesson["family"], "f0")
        self.assertIn("made no eligible Train version in 150 Gym evaluations", lesson["lesson"])
        self.assertIn("Retired by the idle rule", lesson["lesson"])
        self.assertIn("not a finding that the mechanism has no edge", lesson["lesson"], "a clock, not a refutation")
        self.assertNotIn("found no Train edge", lesson["lesson"])
        causes = [e["payload"]["cause"] for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(causes, [IDLE_CAUSE] * 3, "the public cause carries no figure")
        # f4 is dead too, but the floor (4) holds it.
        self.assertIsNotNone(idle_dead(self.store.family("f4"), self.settings))
        self.assertEqual(t.retirements(self.store.families(alive=True)), [])
        self.assertEqual(len(self.store.families(alive=True)), 4)

    def test_a_counted_validation_restarts_the_idle_count(self):
        self.answer = weak  # the line fails: nothing awaits the gate
        self.family("a")
        self.settings["population"].update(start=1, floor=0)
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        fam = self.store.family("a")
        self.assertFalse(fam["state"]["gate_ready"])
        self.assertEqual((fam["validations"], fam["trials"], fam["state"]["validated_trials"]), (1, 2, 2),
                         "the mark is taken after the validation's own two trials")
        self.assertNotIn("validated_revisions", fam["state"])
        self.store.update_family("a", trials=2 + 149, since_val_trials=900)
        self.assertEqual(idle_evaluations(self.store.family("a")), 149)
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])
        self.store.bump("a", trials=1, since_val_trials=1)
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertIn("150 Gym evaluations since its last validation", row["why"])

    def test_a_rejudged_recorded_validation_leaves_the_mark(self):
        """`record=False` (a recorded validation judged again: no new trial) is no new validation for the idle rule."""
        self.answer = weak
        self.family("a")
        t = Tournament(self.store, self.pool, self.settings)
        t.validate(self.store.families(alive=True))
        self.store.bump("a", trials=30, since_val_trials=30)
        recorded = t.recorded_validation("a", 1)
        self.assertIsNotNone(recorded)
        self.assertIsNotNone(t.judge("a", 1, recorded, record=False))
        fam = self.store.family("a")
        self.assertEqual((fam["validations"], fam["trials"], fam["state"]["validated_trials"]), (1, 32, 2))
        self.assertEqual(idle_evaluations(fam), 30)

    def test_a_passed_validation_with_a_negative_best_is_not_retired_while_it_awaits_the_gate(self):
        self.family("a")  # the strong answer passes the line: gate_ready
        self.family("b")
        self.settings["population"].update(start=2, floor=0)
        t = Tournament(self.store, self.pool, self.settings)
        t.validate(self.store.families(alive=True))
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        for fid in ("a", "b"):
            self.store.update_family(fid, best_train=-0.5)
            self.store.bump(fid, trials=450, since_val_trials=450)
        self.store.set_state("b", gate_ready=False)  # the gate refused b's version
        self.assertEqual([r["family"] for r in t.retirements(self.store.families(alive=True))], ["b"])
        self.assertIsNone(self.store.family("a")["retired_at"])


class RoundRetirement(RoundCase):
    def test_retirement_during_review_keeps_the_paid_answer_but_starts_no_new_audit(self):
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        review = gate.review

        def retired_while_reviewing(fam, version):
            answer = review(fam, version)
            other.retire_gym(fam["id"], "The mechanism failed.", floor=0, source="researcher")
            return answer

        gate.review = retired_while_reviewing
        gate.run()
        current = self.store.family("a")
        self.assertEqual(current["state"]["review"]["verdict"], "pass")
        self.assertNotIn("audit", current["state"]["review"])
        self.assertEqual(len(self.sail.bodies), 1)
        self.assertEqual([j for j in self.pool.jobs if j.window == "holdout"], [])
        self.assertEqual(len([e for e in self.store.events_after(0)
                              if e["kind"] == "swarm.gate" and e["payload"].get("action") == "review"]), 1)

    def test_restart_releases_a_retired_ancestors_dead_process_look_without_rearming_it(self):
        self.family("ancestor")
        self.store.add_family({**SPEC, "id": "descendant"}, origin="fork", parent="ancestor")
        marker = {"sha": "unfinished-look", "n": 1, "at": self.clock() - 1, "token": "old-process"}
        self.store.set_state("ancestor", validation_version=1, look_inflight=marker)
        self.store.retire_gym("ancestor", "The mechanism failed.", floor=0, source="researcher")
        self.assertEqual(self.store.lineage_looks("descendant", include_inflight=True), 1)
        Gate(self.store, self.pool, self.router, self.settings, clock=self.clock).run()
        state = self.store.family("ancestor")["state"]
        self.assertIsNone(state["look_inflight"])
        self.assertFalse(state["gate_ready"])
        self.assertEqual(self.store.lineage_looks("descendant", include_inflight=True), 0)
        self.assertEqual((self.pool.jobs, self.store.looks()), ([], []))

    def test_current_process_retired_look_reservation_survives_gate_cleanup(self):
        self.family("ancestor")
        gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.clock.advance(1)
        marker = {"sha": "running-look", "n": 1, "at": self.clock(), "token": "current-process"}
        self.store.set_state("ancestor", validation_version=1, look_inflight=marker)
        self.store.retire_gym("ancestor", "The mechanism failed.", floor=0, source="researcher")
        gate.run()
        self.assertEqual(self.store.family("ancestor")["state"]["look_inflight"], marker)
        self.assertEqual(self.store.lineage_looks("ancestor", include_inflight=True), 1)
        self.assertEqual((self.pool.jobs, self.sail.bodies), ([], []))

    def test_stale_tournament_snapshot_shares_the_atomic_population_floor(self):
        for i in range(3):
            self.family(f"f{i}")
            self.store.update_family(f"f{i}", since_val_revisions=30)
        self.settings["population"]["floor"] = 2
        stale = self.store.families(alive=True)
        other = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(other.close)
        other.retire_gym("f0", "Research ended.", floor=2, source="researcher")
        out = Tournament(self.store, self.pool, self.settings).retirements(stale)
        self.assertEqual(out, [])
        self.assertEqual(len(self.store.families(alive=True)), 2)

    def test_late_holdout_keeps_the_reserved_look_and_cannot_promote_a_retired_family(self):
        self.family("a")
        tournament = Tournament(self.store, self.pool, self.settings)
        tournament.validate(self.store.families(alive=True))
        self.pool.slow.add("a")
        self.replies = [{"text": json.dumps({"verdict": "pass"})}] * 2
        Gate(self.store, self.pool, self.router, self.settings).run()
        job, finish = self.pool.landing[0]
        before = self.store.lineage_trials("a")
        marker = self.store.family("a")["state"]["look_inflight"]
        self.store.retire_gym("a", "The mechanism failed.", floor=0, source="researcher")
        self.assertEqual(self.store.family("a")["state"]["look_inflight"], marker)
        self.assertEqual(self.store.lineage_looks("a", include_inflight=True), 1)
        finish(strong(job))
        self.assertEqual(self.store.family("a")["band"], "retired")
        self.assertEqual((self.store.lineage_trials("a"), self.store.lineage_looks("a")), (before + 1, 1))
        self.assertIsNone(self.store.family("a")["state"]["look_inflight"])

    def test_late_validation_records_trials_but_does_not_rearm_or_fork_a_retired_family(self):
        fam = self.family("a")
        self.pool.slow.add("a")
        tournament = Tournament(self.store, self.pool, self.settings)
        tournament.validate([fam])
        job, finish = self.pool.landing[0]
        self.store.retire_gym("a", "The mechanism failed.", floor=0, source="researcher")
        finish(strong(job))
        current = self.store.family("a")
        self.assertEqual((current["trials"], current["state"]["gate_ready"]), (2, False))
        self.assertIsNone(current["validated_version"])
        self.assertIsNone(tournament.fork(fam))

    def test_architect_omits_retired_cached_leaderboard_rows_and_keeps_refill_caps(self):
        self.family("dead")
        self.family("live")
        self.store.put("leaderboard", {"board": [{"family": fid, "band": "gym", "structure": "iron_condor", "roots": ["SPY"]}
                                                   for fid in ("dead", "live")]})
        self.store.retire_gym("dead", "The mechanism failed.", floor=0, source="researcher")
        architect = Architect(self.store, self.router, self.settings, clock=self.clock)
        living = json.loads(architect.prompt().split("(leaderboard):\n", 1)[1].split("\n\nTHE GRAVEYARD", 1)[0])
        self.assertEqual([row["family"] for row in living], ["live"])
        self.assertTrue(architect.refilling())
        self.assertEqual(architect.want(), self.settings["architect"]["max_refill"])
        self.store.put("architect_at", self.clock())
        self.assertFalse(architect.due())


class PoolRetirement(PoolCase):
    def test_retirement_after_caller_check_and_cancellation_prevents_late_submission(self):
        fid = self.store.add_family(SPEC, origin="seed")["id"]
        pool = self.pool()
        stale_check = self.store.family(fid)
        self.assertIsNone(stale_check["retired_at"])
        other = SwarmStore(self.store.root, clock=self.clock)
        self.addCleanup(other.close)
        other.retire_gym(fid, "The mechanism failed.", floor=0, source="tournament")
        pool.cancel_family(fid)
        job = pool.submit(pool_job(fid))
        self.assertTrue(job.done.is_set())
        self.assertIn("retired", job.error)
        self.assertEqual((pool.queued(), self.calls), (0, []))

    def test_committed_retirement_blocks_queue_handoff_before_cancel_reaches_pool(self):
        fid = self.store.add_family(SPEC, origin="seed")["id"]
        pool = self.pool()
        box = self.ready_box(pool)
        job = pool.submit(pool_job(fid))
        self.clock.advance(9)
        self.store.retire_gym(fid, "The mechanism failed.", floor=0, source="researcher")
        self.assertEqual(pool._take(box), [], "no new batch between retirement commit and cancel_family")
        self.assertTrue(job.done.is_set())
        self.assertEqual(self.calls, [])

    def test_work_handed_to_a_dispatcher_before_retirement_keeps_its_result(self):
        fid = self.store.add_family(SPEC, origin="seed")["id"]
        pool = self.pool()
        box = self.ready_box(pool)
        job = pool.submit(pool_job(fid))
        self.clock.advance(9)
        batch = pool._take(box)
        self.store.retire_gym(fid, "The mechanism failed.", floor=0, source="researcher")
        pool.cancel_family(fid)
        pool.run_batch(box, batch)
        self.assertEqual(pool.wait(job, 0)["status"], "ok")
        self.assertEqual(self.store.family(fid)["band"], "retired")
