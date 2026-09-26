"""Explicit abandonment retains evidence, serializes population decisions, and ends only research work."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from league.swarm.architect import Architect
from league.swarm.gate import Gate
from league.swarm.researcher import Researcher
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase, strong
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
    def setUp(self):
        super().setUp()
        self.settings["population"]["floor"] = 0
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append

    def final_call(self):
        return ("retire", {"reason": "Costs defeated the mechanism."})

    def test_retire_before_any_version_is_terminal_and_restart_skips_it(self):
        self.steps = [{"calls": [self.final_call(), ("gym_run", {"code": self.code}),
                                 ("notebook", {"action": "append", "text": "Should never run"})]}]
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        out = researcher.cycle(self.fam["id"])
        self.assertTrue(out["retired"])
        self.assertEqual((out["model_calls"], len(self.pool.jobs), self.store.versions(self.fam["id"])), (1, 0, []))
        self.assertEqual(self.cancelled, [self.fam["id"]])
        items = self.store.convo(self.fam["id"])[0][-1]["items"]
        calls = [i["call_id"] for i in items if i.get("type") == "function_call"]
        outputs = [i for i in items if i.get("type") == "function_call_output"]
        self.assertEqual([i["call_id"] for i in outputs], calls)
        self.assertEqual([json.loads(i["output"])["status"] for i in outputs], ["retired", "refused", "refused"])
        self.assertEqual(self.researcher().cycle(self.fam["id"])["skipped"], "retired")
        self.assertEqual(len(self.sail.bodies), 1)
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

    def test_floor_refusal_defers_the_cycle_and_uses_increasing_scheduler_backoff(self):
        from league.swarm.loop import Scheduler

        self.settings["population"]["floor"] = 1
        self.researcher().cycle(self.fam["id"])
        scheduler = Scheduler(self.store, clock=self.clock)
        for delay in (60, 120):
            self.assertEqual(scheduler.take(), self.fam["id"])
            self.steps = [{"calls": [self.final_call(), ("gym_run", {"params": {"vrp_min": 1.3}})]}]
            out = self.researcher().cycle(self.fam["id"])
            self.assertTrue(out["retirement_deferred"])
            self.assertNotIn("retired", out)
            self.assertEqual((out["model_calls"], len(self.pool.jobs)), (1, 1))
            self.assertEqual(self.store.family(self.fam["id"])["band"], "gym")
            self.assertIn("minimum", out["error"])
            scheduler.release(self.fam["id"], out)
            self.clock.advance(delay - 1)
            self.assertIsNone(scheduler.take())
            self.clock.advance(1)
        self.assertEqual(self.store.family(self.fam["id"])["trials"], 1)
        self.assertEqual(self.store.graveyard(), [])

    def test_floor_deferral_cancels_an_earlier_queued_run_in_the_same_response(self):
        self.settings["population"]["floor"] = 1
        self.researcher().cycle(self.fam["id"])
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]},
                      {"calls": [("gym_run", {"params": {"vrp_min": 1.5}}), self.final_call()]}]
        out = self.researcher().cycle(self.fam["id"])
        self.assertTrue(out["retirement_deferred"])
        self.assertFalse(out["pending_run"])
        self.assertIsNone(self.store.convo(self.fam["id"])[1])
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


class RoundRetirement(RoundCase):
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
