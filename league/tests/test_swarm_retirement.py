"""Explicit abandonment retains evidence, serializes population decisions, and ends only research work."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from league.swarm.architect import Architect
from league.swarm.gate import Gate
from league.swarm import bands
from league.swarm.evaluator import KEY, adopt, identity
from league.swarm.researcher import (RETIRE_GUARD_DAYS, RETIRE_IDLE_EVALUATIONS, SCREENED, SELF_REFUTED, TOOLS, VERDICTS_KEY,
                                     Researcher, awaiting_validation, dead_slot, idle_cause, idle_dead, idle_evaluations,
                                     idle_limit, record_verdict, retire_guard, validated_at)
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
    cases put the family there (start 0, two validations, its best validated) unless they test the guard itself."""

    def setUp(self):
        super().setUp()
        self.settings["population"]["floor"] = 0
        self.settings["population"]["start"] = 0
        # Two validations, of its best (the starter, version 1): no best awaits validation (THE VALIDATION WAIT, H1).
        self.store.update_family(self.fam["id"], validations=2, validated_version=1)
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append

    def final_call(self):
        return ("retire", {"reason": "Costs defeated the mechanism."})

    def tools_of(self, body):
        return [t["name"] for t in body["tools"]]

    def test_a_tested_family_can_retire_on_revise_without_buying_another_run(self):
        self.researcher().cycle(self.fam["id"])
        self.steps = [{"calls": [self.final_call(), ("gym_run", {"params": {"vrp_min": 1.3}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out["retired"])
        self.assertNotIn("error", out, "a refused retire is never a cycle error")
        self.assertEqual(self.tools_of(self.sail.bodies[0]), ["gym_run", "gym_sweep", "retire"])
        self.assertEqual(len(self.pool.jobs), 1, "the abandoned family's queued revision never runs")
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fam["id"])[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        self.assertEqual(outputs[0]["status"], "retired")
        self.assertEqual(self.store.family(self.fam["id"])["band"], "retired")

    def test_retire_uses_the_floor_not_the_start_with_two_validations(self):
        self.researcher().cycle(self.fam["id"])
        for start, validations, offered in ((0, 2, True), (96, 2, True), (0, 1, False)):
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
        self.assertIn(f"Retired by researcher: {SELF_REFUTED}: {reason}", self.store.notebook(self.fam["id"])[-1]["text"],
                      "its own researcher's retirement is SELF-REFUTED in the graveyard (R11-1)")
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

    def test_a_family_that_loops_one_placeholder_is_dead_by_its_dormant_cycles(self):
        """The case the rule is for (live: hundreds of cycles on a dozen versions). Since NO DUPLICATE RUNS (R3) an unchanged
        program re-run is answered from the store: no version, no run, no trial, so the evaluation count no longer moves.
        Those cycles are dormant instead, and the dormancy clause makes the family dead after `dormant_cycles` of them."""
        self.settings["researcher"].update(retire_idle_evaluations=12, dormant_cycles=12)
        self.pool.answer = lambda job: {**result(job.name, roots=job.roots, trades=0), "run_id": "one-placeholder"}
        self.researcher().cycle(self.fam["id"])  # the starter: version 1
        for i in range(12):  # twelve cycles re-running the latest version unchanged (no `code`, the same params)
            self.steps = [{"calls": [("gym_run", {"params": {}})]}, {"text": "holding dormant"}]
            out = self.researcher().cycle(self.fam["id"])
            self.assertEqual((out["stored"], out.get("trials", 0), out["dormant_cycles"]), (1, 0, i + 1))
        fam = self.store.family(self.fam["id"])
        self.assertEqual((fam["revisions"], fam["trials"]), (1, 1), "re-runs make no version and no trial")
        self.assertEqual(len(self.pool.jobs), 1, "only the starter reached the Gym")
        self.assertEqual(len(self.store.runs(self.fam["id"], window="train", limit=50)), 1)
        self.assertEqual(idle_evaluations(fam), 1)
        self.assertEqual(idle_dead(fam, self.settings),
                         "made no new Gym evaluation in its last 12 cycles (only stored results, holds and refused runs)")
        self.assertTrue(self.researcher().can_retire(fam))
        # A researcher that never calls retire: the tournament's fallback retires it by the same rule.
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(row["family"], self.fam["id"])
        self.assertEqual(row["why"], "It made no new Gym evaluation in its last 12 cycles (only stored results, holds and "
                                     f"refused runs). {IDLE_CAUSE}", "the idle rule's wording")
        self.assertEqual(self.store.family(self.fam["id"])["band"], "retired")
        self.assertEqual(self.cancelled, [self.fam["id"]])
        [lesson] = self.store.graveyard()
        self.assertIn("Retired by the idle rule", lesson["lesson"])
        self.assertIn("not a finding that the mechanism has no edge", lesson["lesson"])

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

    def test_a_dead_family_retires_at_the_floor_and_a_researching_one_does_not(self):
        """THE FLOOR COUNTS RESEARCH (F1): the floor counts the families that are researching, so a dead slot leaves at the
        floor and a family that is not dead still may not."""
        self.assertTrue(self.settings["population"]["floor_researching"], "the default")
        self.settings["population"]["floor"] = 1
        self.researcher().cycle(self.fam["id"])
        self.store.update_family(self.fam["id"], trials=20)  # tested (ten counted trials), not dead: the floor's one
        out = self.read_turn(("retire", {"reason": "Costs defeated the mechanism."}))
        self.assertFalse(self.offered(), "a researching family at the floor: not offered")
        self.assertTrue(out["retire_refused"])
        r = self.researcher()
        r.can_retire = lambda fam: True  # a stale read: the store's own count still refuses a family the floor counts
        out = self.read_turn(("retire", {"reason": "Costs."}), researcher=r, params={"vrp_min": 1.4})
        self.assertTrue(out["retire_refused"])
        self.assertIsNone(self.store.family(self.fam["id"])["retired_at"])
        self.idle(150)  # dead by the idle rule: the floor does not count it
        self.assertFalse(dead_slot({**self.store.family(self.fam["id"]), "since_val_trials": 100}, self.settings))
        self.assertTrue(dead_slot(self.store.family(self.fam["id"]), self.settings))
        out = self.read_turn(("retire", {"reason": "The mechanism is dead."}), params={"vrp_min": 1.5})
        self.assertTrue(self.offered(), "a dead slot is offered retire at the floor")
        self.assertIn("eligible Train version in", self.status())
        self.assertTrue(out["retired"])
        self.assertEqual(self.store.families(alive=True), [], "the floor never holds a dead family for its own sake")

    def test_the_floor_still_holds_for_a_dead_family_while_it_counts_every_family(self):
        self.settings["population"].update(floor=1, floor_researching=False)  # the switch: every living family counts
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
        """With the floor counting every family (`population.floor_researching` false), as before F1."""
        other = self.store.add_family({**family_spec(self.spec), "id": "other-dead"}, origin="seed")
        self.settings["population"].update(start=2, floor=1, floor_researching=False)
        self.researcher().cycle(self.fam["id"])
        self.idle(150)
        self.idle(150, fid=other["id"])
        self.assertTrue(self.researcher().can_retire(self.store.family(other["id"])))
        out = self.read_turn(("retire", {"reason": "The mechanism is dead."}))
        self.assertTrue(out["retired"])
        self.assertEqual(len(self.store.families(alive=True)), 1, "below the start (2), at the floor (1)")
        self.assertFalse(self.researcher().can_retire(self.store.family(other["id"])), "the floor holds the last one")

    def test_dead_families_retire_below_the_start_and_the_floor_holds_only_the_living(self):
        """THE FLOOR COUNTS RESEARCH (F1): two dead families and one that researches, a floor of 1. Both dead ones may
        retire; the one that researches is the floor's."""
        other = self.store.add_family({**family_spec(self.spec), "id": "other-dead"}, origin="seed")
        living = self.store.add_family({**family_spec(self.spec), "id": "living"}, origin="seed")
        self.settings["population"].update(start=3, floor=1)
        self.researcher().cycle(self.fam["id"])
        self.idle(150)
        self.idle(150, fid=other["id"])
        self.store.update_family(living["id"], trials=20)
        r = self.researcher()
        self.assertTrue(r.can_retire(self.store.family(other["id"])))
        self.assertFalse(r.can_retire(self.store.family(living["id"])), "one family researches: it is the floor")
        out = self.read_turn(("retire", {"reason": "The mechanism is dead."}))
        self.assertTrue(out["retired"])
        self.assertTrue(r.can_retire(self.store.family(other["id"])), "the second dead slot is not held either")
        self.assertEqual(self.store.retire_gym(other["id"], "Dead.", floor=1, source="researcher",
                                               counts=r.floor_counts())["status"], "retired")
        refused = self.store.retire_gym(living["id"], "Costs.", floor=1, source="researcher", counts=r.floor_counts())
        self.assertEqual((refused["status"], refused["deferred"]), ("refused", "population_floor"))
        self.assertEqual([f["id"] for f in self.store.families(alive=True)], ["living"])


class TournamentIdleRetirement(RoundCase):
    """The tournament's fallback for a dead family that never calls retire: the same idle rule, down to the floor only."""

    def setUp(self):
        super().setUp()
        # The operator's running swarm.json keeps the old rules far out; the idle rule acts on its own.
        self.settings["tournament"].update(retire_revisions=200, retire_evaluations=10 ** 6)

    def test_dead_families_retire_at_the_start_down_to_the_floor_and_the_rest_stay(self):
        for i in range(7):
            self.family(f"f{i}")
        self.settings["population"].update(start=7, floor=4, floor_researching=False)  # every family counts, as before F1
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
        self.assertEqual(out[1]["why"], "It kept its best Train score below zero over 450 Gym evaluations since its birth. "
                                        f"{idle_cause('scored')}", "a Train score: a tested verdict (R11-1)")
        self.assertIn("f0", self.pool.cancelled)
        lesson = self.store.graveyard("placeholder")[0]
        self.assertEqual(lesson["family"], "f0")
        self.assertIn("made no eligible Train version in 150 Gym evaluations", lesson["lesson"])
        self.assertIn("Retired by the idle rule", lesson["lesson"])
        self.assertIn("not a finding that the mechanism has no edge", lesson["lesson"], "a clock, not a refutation")
        self.assertNotIn("found no Train edge", lesson["lesson"])
        causes = [e["payload"]["cause"] for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(causes, [IDLE_CAUSE, f"{SCREENED}.", IDLE_CAUSE], "the public cause carries no figure")
        # f4 is dead too, but the floor (4) holds it.
        self.assertIsNotNone(idle_dead(self.store.family("f4"), self.settings))
        self.assertEqual(t.retirements(self.store.families(alive=True)), [])
        self.assertEqual(len(self.store.families(alive=True)), 4)
        # THE FLOOR COUNTS RESEARCH (F1, the default): the dead f4 is not one of the floor's four, so it leaves too, and
        # the three that are not dead stay, at any floor.
        self.settings["population"].update(floor_researching=True)
        self.assertEqual([r["family"] for r in t.retirements(self.store.families(alive=True))], ["f4"])
        self.settings["population"].update(floor=7)
        self.assertEqual(t.retirements(self.store.families(alive=True)), [])
        self.assertEqual(sorted(f["id"] for f in self.store.families(alive=True)), ["f3", "f5", "f6"])

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
        self.assertEqual(t.retirements(self.store.families(alive=True)), [], "the extension evidence is still held")
        self.store.set_state("b", extension_hold=None)  # its outstanding extension was also resolved
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


# ------------------------------------------------------------------------------------ THE VALIDATED-FAMILY GUARD (Oct 1)
#: The words googl-lags-msft-ai-cloud-qqq-flat's researcher retired it with on Sept 30, 17 seconds after the adoption.
GOOGL_REASON = ("The mechanism is proven and validated (v27, 8/8 validation checks) but every attempt to extend or "
                "re-express it failed the drift screen or volume requirements. The evaluator has changed, meaning my "
                "validated v27 must be re-evaluated under the new evaluator before it can count, and holding further only "
                "accumulates idle cycles.")


def line_of(met, total=8):
    return {"passed": met == total, "checks": {f"c{i}": i < met for i in range(total)}}


class ValidatedFamilyGuard(ResearcherCase):
    """Oct 1: googl-lags-msft-ai-cloud-qqq-flat, the swarm's only D2-tuition family (8 of 8 on Validation, review and
    audit passed, tuition traded), was retired by its own researcher's `retire` 17 seconds after an evaluator adoption
    archived its validation, "because the evaluator changed". Its researcher may not retire it while it holds a version
    that passed the line, archived or not, unless that version fails the line under the current evaluator."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=0, floor=0)
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append
        self.fid = self.fam["id"]
        self.researcher().cycle(self.fid)  # the starter: version 1 on Train

    def validate(self, n=1, *, met=8, image="old-image", bundle="gym-engine-3-old"):
        """Version n validated as the tournament recorded it before Oct 1 (its run row and its line; no verdict record).
        One validation and 73 trials, as googl had: the retire tool is offered (`retire_min_trials`)."""
        row = result(f"val-{n}", window="validation")
        row.update(gym_image=image, gym_bundle=bundle)
        self.store.add_run(self.fid, n, row, window="validation", stress=1.0, purpose="validation")
        self.store.update_family(self.fid, validated_version=n, best_validation=0.46, validations=1, trials=73)
        self.store.set_state(self.fid, validation_line=line_of(met), validation_version=n, validation_image=image,
                             validation_bundle=bundle)

    def googl(self):
        """Validated 8 of 8 at 16:30Z; the evaluator adopted at 20:08:57Z (archived and cleared); retire at 20:09:14Z."""
        self.validate(1)
        self.clock.advance(3 * 3600 + 38 * 60 + 35)
        self.assertTrue(adopt(self.store, identity("new-image", bands._bundle()))["adopted"])
        self.clock.advance(17)

    def retire_cycle(self, reason=GOOGL_REASON):
        """A REVISE turn that calls retire, then a run; then a READ turn. (out, the tool outputs, the REVISE request)."""
        first = len(self.sail.bodies)
        self.steps = [{"calls": [("retire", {"reason": reason}), ("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"text": "read it"}]
        out = self.researcher().cycle(self.fid)
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fid)[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        return out, outputs, self.sail.bodies[first]

    @staticmethod
    def status_of(body):
        return next(i["content"] for i in reversed(body["input"])
                    if i.get("role") == "user" and "Now: if a run just came back" in str(i.get("content")))

    def alive(self):
        fam = self.store.family(self.fid)
        return fam["band"] == "gym" and fam["retired_at"] is None

    def test_the_googl_scenario_is_refused_with_its_reason_and_its_program(self):
        self.googl()
        state = self.store.family(self.fid)["state"]
        self.assertIsNone(state["validation_line"], "the adoption cleared the line")
        self.assertTrue(state["previous_evaluator_selection"]["validation_line"]["passed"], "and archived it")
        out, outputs, body = self.retire_cycle()
        self.assertIn("retire", [t["name"] for t in body["tools"]], "the offer is unchanged (`can_retire`)")
        self.assertTrue(out["retire_refused"])
        self.assertEqual(out["retire_guarded"], 1)
        self.assertNotIn("retired", out)
        self.assertNotIn("error", out, "a refusal is a tool answer, never a cycle error (no backoff)")
        answer = outputs[0]
        self.assertEqual((answer["status"], answer["guard"], answer["version"]), ("refused", "validated_version", 1))
        self.assertIn("passed the validation line before the evaluator changed", answer["reason"])
        self.assertIn("an evaluator change is never a reason to retire", answer["reason"])
        self.assertIn("Re-run version 1 unchanged", answer["reason"])
        version = self.store.version(self.fid, 1)
        self.assertEqual(answer["program"], {"version": 1, "code": version["code"], "params": version.get("params") or {}})
        self.assertTrue(self.alive())
        self.assertEqual((self.store.graveyard(), self.cancelled), ([], []))
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.retired"], [])
        self.assertFalse(any("Retired by" in n["text"] for n in self.store.notebook(self.fid)))
        status = self.status_of(body)
        self.assertIn("passed the validation line before the evaluator changed", status)
        self.assertNotIn("call retire", status, "a guarded family is never urged to retire")

    def test_the_prompt_and_the_tool_say_an_evaluator_change_is_never_a_reason_to_retire(self):
        from league.swarm.researcher import ROLE, TOOLS

        self.assertIn("AN EVALUATOR CHANGE IS NEVER A REASON TO RETIRE", ROLE)
        self.assertIn("validates it again under the current evaluator by itself", ROLE)
        [tool] = [t for t in TOOLS if t["name"] == "retire"]
        self.assertIn("an evaluator change is never a reason to retire", tool["description"])
        self.googl()
        self.retire_cycle()
        self.assertIn("AN EVALUATOR CHANGE IS NEVER A REASON TO RETIRE", self.sail.bodies[-1]["input"][0]["content"])

    def test_a_failed_validation_of_that_version_under_the_current_evaluator_is_a_refutation(self):
        self.googl()
        self.store.update_family(self.fid, best_version=1)  # its researcher re-ran version 1 unchanged: its best again
        failed = result("val-again", window="validation", mean=-0.01, t=-0.5, quarters="1/4", pnl=-100.0)
        row = Tournament(self.store, self.pool, self.settings, clock=self.clock).judge(self.fid, 1, failed)
        self.assertFalse(row["passed"])
        record = self.store.family(self.fid)["state"][VERDICTS_KEY]["1"]
        self.assertEqual((record["passed"], record["evaluator"]), (False, self.store.get(KEY)))
        self.assertIsNone(self.researcher().guarded(self.store.family(self.fid)))
        out, outputs, _ = self.retire_cycle("Version 1 failed the validation line under the current evaluator.")
        self.assertTrue(out["retired"])
        self.assertFalse(self.alive())
        self.assertIn(SELF_REFUTED, self.store.family(self.fid)["retire_reason"])

    def test_the_refutation_survives_another_version_replacing_the_line(self):
        """The tournament's per-version record: version 1 fails under the current evaluator, then version 2's validation
        replaces the family's line. Version 1's archived pass is refuted all the same; a pass of 2 would guard it."""
        self.googl()
        tournament = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        failed = result("val-1", window="validation", mean=-0.01, t=-0.5, quarters="1/4", pnl=-100.0)
        self.store.update_family(self.fid, best_version=1)
        self.assertFalse(tournament.judge(self.fid, 1, failed)["passed"])
        self.store.add_version(self.fid, self.code + "\n# another version\n", {}, author="test")
        self.store.update_family(self.fid, best_version=2)
        self.assertFalse(tournament.judge(self.fid, 2, dict(failed, run_id="val-2"))["passed"])
        state = self.store.family(self.fid)["state"]
        self.assertEqual((state["validation_version"], sorted(state[VERDICTS_KEY])), (2, ["1", "2"]))
        self.assertIsNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))
        # Without the record (a verdict written before Oct 1) the archived pass of 1 stands unrefuted.
        self.store.set_state(self.fid, **{VERDICTS_KEY: None})
        self.assertEqual(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())["version"], 1)

    def test_a_record_is_the_versions_latest_verdict_whatever_evaluator_judged_it(self):
        """The tournament writes a version's record with each of its verdicts, so a record is newer than any archive of
        that version: a recorded failure under an earlier evaluator refutes an archived pass, and a recorded pass under
        one is no refutation (it guards, archived)."""
        self.validate(1)  # passed before the records were kept
        adopt(self.store, identity("new-image", bands._bundle()))
        between = self.store.get(KEY)
        failed = record_verdict({}, 1, False, evaluator=between, at=self.store.now())
        self.store.set_state(self.fid, **{VERDICTS_KEY: failed})
        self.adopt_again()
        self.assertNotEqual(self.store.get(KEY), between)
        self.assertIsNone(self.guard(), "refuted under the evaluator in force then: the next adoption never revives it")
        passed = record_verdict({}, 1, True, evaluator=between, at=self.store.now())
        self.store.set_state(self.fid, **{VERDICTS_KEY: passed})
        guard = self.guard()
        self.assertEqual((guard["version"], guard["archived"]), (1, True), "a pass under an earlier evaluator guards")

    def test_a_passed_line_under_the_current_evaluator_guards_too(self):
        self.validate(1, image=None, bundle=None)
        out, outputs, body = self.retire_cycle()
        self.assertTrue(out["retire_refused"])
        self.assertTrue(self.alive())
        self.assertEqual(outputs[0]["version"], 1)
        self.assertNotIn("program", outputs[0], "no archived version to re-run")
        self.assertIn("Keep researching beside it", self.status_of(body))

    def test_a_failed_validation_alone_never_guards(self):
        """googl's fork (-on): its only validation failed 5 of 8 checks, then the adoption archived it."""
        self.validate(1, met=3)
        adopt(self.store, identity("new-image", bands._bundle()))
        self.assertIsNone(self.researcher().guarded(self.store.family(self.fid)))
        out, _, body = self.retire_cycle("The mechanism is exhausted: version 1 failed 5 of 8 checks.")
        self.assertTrue(out["retired"])
        self.assertIn("call retire", self.status_of(body))

    def test_the_guard_lapses_retire_guard_days_after_the_last_validation(self):
        self.googl()
        fam = self.store.family(self.fid)
        at = validated_at(self.store, self.fid, 1, fam["state"])
        self.assertEqual(self.settings["researcher"].get("retire_guard_days", RETIRE_GUARD_DAYS), 14.0)
        self.clock.advance(at + 14 * 86400 - 60 - self.clock())
        self.assertIsNotNone(self.researcher().guarded(self.store.family(self.fid)))
        self.clock.advance(120)
        self.assertIsNone(self.researcher().guarded(self.store.family(self.fid)))
        self.assertTrue(self.retire_cycle()[0]["retired"])

    def test_the_setting(self):
        self.googl()
        for value, guarded in ((0, False), (-3, False), (None, True), (True, True), ("off", True), (float("nan"), True),
                               (1, True), (0.0001, False)):
            with self.subTest(value=value):
                self.settings["researcher"]["retire_guard_days"] = value
                self.assertEqual(self.researcher().guarded(self.store.family(self.fid)) is not None, guarded)
        self.settings["researcher"]["retire_guard_days"] = 0
        self.assertTrue(self.retire_cycle()[0]["retired"], "0 turns the guard off")

    def test_operator_retirement_is_unaffected(self):
        self.googl()
        self.assertEqual(self.store.retire_gym(self.fid, "The operator retires it.", floor=0, source="operator")["status"],
                         "retired")

    def test_the_tournaments_rules_are_unaffected(self):
        self.googl()
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)
        trials = self.store.family(self.fid)["trials"] + RETIRE_IDLE_EVALUATIONS
        self.store.update_family(self.fid, trials=trials, since_val_trials=trials)
        self.assertIsNotNone(self.researcher().guarded(self.store.family(self.fid)))
        [row] = Tournament(self.store, self.pool, self.settings, clock=self.clock).retirements(self.store.families(alive=True))
        self.assertEqual(row["family"], self.fid)
        self.assertFalse(self.alive())

    # The second adoption (the House adopted at Sept 30 20:08Z and again at Oct 1 03:51Z, 7h43m apart): it replaces
    # `previous_evaluator_selection` with the selection the first one already cleared, so the archived pass is no longer
    # in the family's state. The guard reads the adoptions' own events and the tournament's verdicts instead.
    SECOND_ADOPTION = 7 * 3600 + 43 * 60

    def adopt_again(self, image="newer-image"):
        self.clock.advance(self.SECOND_ADOPTION)
        self.assertTrue(adopt(self.store, identity(image, bands._bundle()))["adopted"])

    def judge(self, n, *, passed, name=None):
        """Version n judged on Validation by the real tournament (its best now), so its verdict record is written."""
        self.store.update_family(self.fid, best_version=n)
        row = (result(name or f"val-{n}", window="validation") if passed else
               result(name or f"val-{n}", window="validation", mean=-0.01, t=-0.5, quarters="1/4", pnl=-100.0))
        verdict = Tournament(self.store, self.pool, self.settings, clock=self.clock).judge(self.fid, n, row)
        self.assertEqual(verdict["passed"], passed)
        return verdict

    def test_a_second_adoption_does_not_lift_the_guard(self):
        """googl's timeline with a pass written before the verdicts were kept (no record), then a second adoption."""
        self.googl()
        self.adopt_again()
        state = self.store.family(self.fid)["state"]
        self.assertIsNone(state["previous_evaluator_selection"]["validation_line"], "the second adoption archived nulls")
        self.assertIsNone(state.get(VERDICTS_KEY))
        guard = retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, True), "read from the first adoption's event")
        out, outputs, body = self.retire_cycle()
        self.assertTrue(out["retire_refused"])
        self.assertEqual(out["retire_guarded"], 1)
        self.assertNotIn("retired", out)
        self.assertTrue(self.alive())
        version = self.store.version(self.fid, 1)
        self.assertEqual(outputs[0]["program"], {"version": 1, "code": version["code"], "params": version.get("params") or {}})
        self.assertIn("passed the validation line before the evaluator changed", self.status_of(body))
        self.adopt_again("newest-image")  # a third one too
        self.assertEqual(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())["version"], 1)

    def test_a_recorded_pass_survives_any_number_of_adoptions(self):
        self.judge(1, passed=True)
        record = self.store.family(self.fid)["state"][VERDICTS_KEY]["1"]
        self.assertTrue(record["passed"])
        for image in ("newer-image", "newest-image"):
            self.adopt_again(image)
        state = self.store.family(self.fid)["state"]
        self.assertIsNone(state["previous_evaluator_selection"]["validation_line"])
        self.assertEqual(state[VERDICTS_KEY]["1"], record, "no adoption clears the record")
        guard = retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, True), "judged under an earlier evaluator")
        self.assertTrue(self.retire_cycle()[0]["retire_refused"])
        self.assertTrue(self.alive())

    def test_a_failure_under_the_current_evaluator_after_a_second_adoption_still_refutes(self):
        self.googl()
        self.adopt_again()
        self.judge(1, passed=False, name="val-again")  # its researcher re-ran version 1 unchanged; it fails now
        self.assertIsNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))
        out, _, _ = self.retire_cycle("Version 1 failed the validation line under the current evaluator.")
        self.assertTrue(out["retired"])
        self.assertFalse(self.alive())

    def test_a_pass_under_the_current_evaluator_survives_another_versions_failure(self):
        """No adoption: version 1 passes, then version 2's failure replaces the family's line. Version 1 still guards."""
        self.judge(1, passed=True)
        self.store.set_state(self.fid, gate_ready=False)  # its holdout look spent
        self.store.add_version(self.fid, self.code + "\n# another version\n", {}, author="test")
        self.judge(2, passed=False)
        state = self.store.family(self.fid)["state"]
        self.assertEqual((state["validation_version"], state["validation_line"]["passed"]), (2, False))
        self.assertEqual({k: v["passed"] for k, v in state[VERDICTS_KEY].items()}, {"1": True, "2": False})
        guard = retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, False))
        out, outputs, body = self.retire_cycle("Version 2 failed validation; the mechanism is exhausted.")
        self.assertTrue(out["retire_refused"])
        self.assertEqual(outputs[0]["version"], 1)
        self.assertNotIn("program", outputs[0], "judged under the current evaluator: nothing to re-run")
        self.assertTrue(self.alive())
        self.assertIn("Your family holds version 1, which passed the validation line.", self.status_of(body))
        # A failure of version 1 itself under the current evaluator ends it.
        self.judge(1, passed=False, name="val-1-again")
        self.assertIsNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))

    def guard(self):
        return retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())

    # A failed re-run under an in-between evaluator (the review of 1c0daf04): version 1 passes under E1, E2 is adopted,
    # version 1 is re-run unchanged and fails under E2 (the guard lets the family go), then E3 is adopted. The E2
    # adoption's event still holds the E1 pass, but it is no longer version 1's latest verdict: the failure refuted it.
    def test_a_failure_under_an_in_between_evaluator_stays_a_refutation_after_the_next_adoption(self):
        """googl's timeline, its pass written before the records were kept (the review's case A)."""
        self.googl()
        self.judge(1, passed=False, name="val-again")
        self.assertIsNone(self.guard())
        self.adopt_again()
        self.assertIsNone(self.guard(), "its record of the failure is newer than any adoption's archive of it")
        out, _, body = self.retire_cycle("Version 1 failed the validation line when re-run under the new evaluator.")
        self.assertTrue(out["retired"])
        self.assertNotIn("retire_refused", out)
        self.assertNotIn("passed the validation line before the evaluator changed", self.status_of(body))
        self.assertFalse(self.alive())

    def test_a_recorded_pass_failed_under_an_in_between_evaluator_stays_refuted(self):
        """The same timeline with the E1 pass recorded (the review's case B)."""
        self.judge(1, passed=True)
        self.store.set_state(self.fid, gate_ready=False)
        self.adopt_again("e2-image")
        self.judge(1, passed=False, name="val-again")
        self.assertIsNone(self.guard())
        self.adopt_again("e3-image")
        self.assertIsNone(self.guard())
        self.assertTrue(self.retire_cycle("Version 1 failed the validation line under E2.")[0]["retired"])
        self.assertFalse(self.alive())

    def test_an_unrecorded_failure_in_a_newer_archive_refutes_an_older_archived_pass(self):
        """The failure written before the records were kept: only the E3 adoption's archive shows it. Walked newest
        first, it refutes the E2 adoption's archived pass, through any number of further adoptions."""
        self.googl()
        self.judge(1, passed=False, name="val-again")
        self.store.set_state(self.fid, **{VERDICTS_KEY: None})
        self.adopt_again()
        archived = self.store.family(self.fid)["state"]["previous_evaluator_selection"]
        self.assertEqual((archived["validation_version"], archived["validation_line"]["passed"]), (1, False))
        self.assertIsNone(self.guard())
        self.adopt_again("newest-image")  # E4: archives nulls; E3's event still shows the failure
        self.assertIsNone(self.store.family(self.fid)["state"]["previous_evaluator_selection"]["validation_line"])
        self.assertIsNone(self.guard())
        self.assertTrue(self.retire_cycle("Version 1 failed the validation line when re-run.")[0]["retired"])

    def test_another_versions_failure_in_a_newer_archive_refutes_nothing_of_it(self):
        """Version 2 fails under E2, then E3 is adopted: version 1's archived E1 pass is still its latest verdict and
        guards, with the records kept or without them."""
        self.googl()
        self.store.add_version(self.fid, self.code + "\n# another version\n", {}, author="test")
        self.judge(2, passed=False)
        self.adopt_again()
        self.assertEqual(self.store.family(self.fid)["state"]["previous_evaluator_selection"]["validation_version"], 2)
        guard = self.guard()
        self.assertEqual((guard["version"], guard["archived"]), (1, True))
        self.store.set_state(self.fid, **{VERDICTS_KEY: None})
        guard = self.guard()
        self.assertEqual((guard["version"], guard["archived"]), (1, True))
        self.assertTrue(self.retire_cycle()[0]["retire_refused"])
        self.assertTrue(self.alive())

    def test_a_recorded_pass_lapses_with_the_window(self):
        self.judge(1, passed=True)
        self.adopt_again()
        self.clock.advance(14 * 86400 - self.SECOND_ADOPTION - 60)
        self.assertIsNotNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))
        self.clock.advance(120)
        self.assertIsNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))

    def test_an_unknown_validation_time_never_guards_without_a_limit(self):
        """A passed line with no validation run and no record: in the state alone it does not guard; archived by an
        adoption it guards from that adoption, which the validation preceded, for the window and no longer."""
        self.store.update_family(self.fid, validated_version=1, validations=1, trials=73)
        self.store.set_state(self.fid, validation_line=line_of(8), validation_version=1)
        self.assertIsNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))
        self.clock.advance(3600)
        adopt(self.store, identity("new-image", bands._bundle()))
        adopted = self.clock()
        self.adopt_again()
        guard = retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock())
        self.assertEqual((guard["version"], guard["archived"]), (1, True))
        self.clock.advance(adopted + 14 * 86400 + 60 - self.clock())
        self.assertIsNone(retire_guard(self.store, self.store.family(self.fid), self.settings, now=self.clock()))

    def test_record_verdict_keeps_the_newest_versions(self):
        state: dict = {}
        for n in range(1, 70):
            at = f"2026-10-01T00:{n // 60:02d}:{n % 60:02d}Z"
            state[VERDICTS_KEY] = record_verdict(state, n, n % 2 == 0, evaluator=None, at=at)
        kept = state[VERDICTS_KEY]
        self.assertEqual(len(kept), 64)
        self.assertEqual(min(int(k) for k in kept), 6)
        state[VERDICTS_KEY] = record_verdict(state, 6, True, evaluator={"image": "i"}, at="2026-10-02T00:00:00Z")
        self.assertEqual(state[VERDICTS_KEY]["6"], {"passed": True, "at": "2026-10-02T00:00:00Z", "evaluator": {"image": "i"}})


class ValidationWait(ResearcherCase):
    """THE VALIDATION WAIT (Oct 1, H1): seven of the ten families that made a drift-passing Train version retired themselves
    before the tournament validated it. A family whose best Train version awaits validation is not offered `retire`, a
    call is refused with the reason, and the status says so in place of any offer; the tournament's verdict, pass or
    fail, ends it, and so does a demotion. Nothing else about the offer moves."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=0, floor=0)
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append
        self.fid = self.fam["id"]
        self.researcher().cycle(self.fid)  # the starter: version 1, eligible, the family's best; its 1.5x run not back
        self.store.update_family(self.fid, trials=12)  # tested (`retire_min_trials`): retire would be offered

    def retire_cycle(self, reason="The condor never pays for its wings on Train: refuted."):
        """A REVISE turn that calls retire, then holds. (out, the tool outputs, the REVISE request)."""
        first = len(self.sail.bodies)
        self.steps = [{"calls": [("retire", {"reason": reason}), ("gym_run", {"hold": True, "note": "Waiting."})]}]
        out = self.researcher().cycle(self.fid)
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fid)[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        return out, outputs, self.sail.bodies[first]

    @staticmethod
    def status_of(body):
        return next(i["content"] for i in reversed(body["input"])
                    if i.get("role") == "user" and "Now: if a run just came back" in str(i.get("content")))

    def alive(self):
        fam = self.store.family(self.fid)
        return fam["band"] == "gym" and fam["retired_at"] is None

    def test_a_tested_family_whose_best_awaits_validation_is_not_offered_retire_and_hears_why(self):
        fam = self.store.family(self.fid)
        self.assertTrue(awaiting_validation(fam))
        r = self.researcher()
        self.assertTrue(r.retire_earned(fam), "only the wait withholds the offer")
        self.assertFalse(r.can_retire(fam))
        out, outputs, body = self.retire_cycle()
        self.assertNotIn("retire", [t["name"] for t in body["tools"]], "not offered")
        self.assertTrue(out["retire_refused"])
        self.assertEqual(out["retire_awaiting"], 1, "the cycle's record names the version the tournament owes a verdict")
        self.assertNotIn("retired", out)
        self.assertNotIn("error", out, "a refusal is a tool answer, never a cycle error (no backoff)")
        self.assertEqual(outputs[0]["status"], "refused")
        self.assertIn("retire is not offered on this turn", outputs[0]["reason"])
        self.assertIn("Your best Train version (1) awaits validation", outputs[0]["reason"])
        self.assertIn("retire is offered once the tournament has validated it", outputs[0]["reason"])
        status = self.status_of(body)
        self.assertIn("Your best Train version (1) awaits validation", status)
        self.assertNotIn("call retire", status, "never urged to retire while it waits")
        self.assertTrue(self.alive())
        self.assertEqual((self.store.graveyard(), self.cancelled), ([], []))
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.retired"], [])

    def test_a_landed_1_5x_run_does_not_end_the_wait_the_tournaments_verdict_does(self):
        # The 1.5x run landed with a profit: the tournament validates the version at its next round; until then it waits.
        self.store.set_state(self.fid, robustness={"1": {"stress_1.5": {"status": "ok", "pnl": 120.0}}})
        fam = self.store.family(self.fid)
        self.assertTrue(awaiting_validation(fam))
        self.assertFalse(self.researcher().can_retire(fam))
        out, outputs, _ = self.retire_cycle()
        self.assertTrue(out["retire_refused"])
        self.assertIn("awaits validation", outputs[0]["reason"])
        self.assertTrue(self.alive())
        # The verdict is in (`validated_version`: a pass or a failure alike): the offer is back, and the retire goes through.
        self.store.update_family(self.fid, validated_version=1)
        fam = self.store.family(self.fid)
        self.assertFalse(awaiting_validation(fam))
        self.assertTrue(self.researcher().can_retire(fam))
        out, outputs, body = self.retire_cycle()
        self.assertIn("retire", [t["name"] for t in body["tools"]], "offered again")
        self.assertNotIn("awaits validation", self.status_of(body))
        self.assertEqual(outputs[0]["status"], "retired")
        self.assertTrue(out["retired"])
        self.assertNotIn("retire_awaiting", out)
        self.assertEqual(self.store.family(self.fid)["band"], "retired")
        self.assertEqual(self.cancelled, [self.fid])

    def test_a_demotion_ends_the_wait_too(self):
        # A loss at 1.5x: the version is never validated (`robust_failed`), so nothing is owed and the offer is back.
        self.store.set_state(self.fid, robust_failed=[1])
        fam = self.store.family(self.fid)
        self.assertFalse(awaiting_validation(fam))
        self.assertTrue(self.researcher().can_retire(fam))
        out, _, body = self.retire_cycle()
        self.assertIn("retire", [t["name"] for t in body["tools"]])
        self.assertTrue(out["retired"])

    def test_a_best_that_changes_between_the_offer_and_the_call_is_refused_by_the_tool(self):
        self.store.update_family(self.fid, validated_version=1)  # offered: its best is validated

        def answer(body):
            self.assertIn("retire", [t["name"] for t in body["tools"]], "offered on this turn")
            # A late Train result made version 2 the best before the call runs: the tool re-reads the family and refuses.
            self.store.add_version(self.fid, self.code, {"vrp_min": 1.4}, author="test")
            self.store.update_family(self.fid, best_version=2)
            return {"calls": [("retire", {"reason": "Refuted."}), ("gym_run", {"hold": True, "note": "Waiting."})]}

        self.steps = [answer]
        out = self.researcher().cycle(self.fid)
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fid)[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        self.assertTrue(out["retire_refused"])
        self.assertNotIn("error", out)
        self.assertEqual((outputs[0]["status"], outputs[0]["guard"], outputs[0]["version"]), ("refused", "awaiting_validation", 2))
        self.assertIn("Your best Train version (2) awaits validation", outputs[0]["reason"])
        self.assertEqual(out["retire_awaiting"], 2)
        self.assertTrue(self.alive())
        self.assertEqual(self.store.graveyard(), [])

    def test_the_status_says_so_only_in_place_of_an_offer(self):
        self.store.update_family(self.fid, trials=1)  # not tested, not dead, not holding: there is no offer to withhold
        fam = self.store.family(self.fid)
        self.assertTrue(awaiting_validation(fam))
        self.assertFalse(self.researcher().retire_earned(fam))
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Waiting."})]}]
        self.researcher().cycle(self.fid)
        status = self.status_of(self.sail.bodies[-1])
        self.assertNotIn("awaits validation", status)
        self.assertNotIn("call retire", status)

    def test_the_tool_says_so(self):
        [tool] = [t for t in TOOLS if t["name"] == "retire"]
        self.assertIn("Never offered while your best Train version awaits validation", tool["description"])
