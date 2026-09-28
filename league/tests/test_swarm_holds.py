"""R4 (Sept 28): after R3 let researchers hold, 2,223 of 2,364 cycles in ten minutes were holds (a holding family came
back every ~12 s), and dead families held on because a hold never reaches the READ turn that offered `retire`, until the
hourly round (the operator retired 60 by hand). HOLD BACKOFF (league/swarm/loop.py `Scheduler`, `hold_wait`); a dead
family's REVISE offers retire (league/swarm/researcher.py); THE IDLE PASS between the hourly rounds
(league/swarm/tournament.py `Tournament.idle_pass`)."""

from __future__ import annotations

import copy
import tempfile
import time
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.loop import HOLD_IDLE_MAX_SECONDS, HOLD_IDLE_SECONDS, Scheduler, hold_wait
from league.swarm.researcher import DORMANT_CYCLES, awaiting_validation, held_at_gate, idle_dead
from league.swarm.seeds import SEEDS, family_spec
from league.swarm.store import SwarmStore
from league.swarm.tournament import IDLE_CAUSE, Tournament
from league.tests.swarm_fakes import Clock, result
from league.tests.test_swarm_loop import LoopCase
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase

DEAD = f"made no new Gym evaluation in its last {DORMANT_CYCLES} cycles (only stored results, holds and refused runs)"


class HoldBackoff(unittest.TestCase):
    """The scheduler's side, on the cycle outcome the researcher reports (`hold`, `trials`, `pending_run`)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.fid = self.store.add_family(family_spec(SEEDS[0]), origin="seed")["id"]
        self.sched = Scheduler(self.store, clock=self.clock, settings=self.settings)

    def take(self):
        return self.sched.take(idle_seconds=0)

    def hold(self, dormant=1, **out):
        """One turn of the family whose cycle ended in a hold, its dormant count as the researcher left it."""
        self.store.set_state(self.fid, dormant_cycles=dormant)
        self.assertEqual(self.take(), self.fid)
        self.sched.release(self.fid, {"family": self.fid, "hold": True, "dormant_cycles": dormant, **out})

    def back_after(self, seconds):
        """The family is not taken a second before `seconds` and is taken at `seconds` (then released idle)."""
        self.clock.advance(seconds - 1)
        self.assertIsNone(self.take(), f"still waiting {seconds - 1} s after the hold")
        self.clock.advance(1)
        self.assertEqual(self.take(), self.fid, f"back {seconds} s after the hold")
        self.sched.release(self.fid, {"family": self.fid})

    def test_the_defaults(self):
        r = S.DEFAULTS["researcher"]
        self.assertEqual((r["hold_idle_seconds"], r["hold_idle_max_seconds"], r["idle_seconds"]), (300, 1800, 5))
        self.assertEqual((HOLD_IDLE_SECONDS, HOLD_IDLE_MAX_SECONDS), (300, 1800))
        self.assertEqual(S.DEFAULTS["tournament"]["retire_every_seconds"], 300)

    def test_a_hold_waits_hold_idle_seconds_and_no_longer(self):
        self.hold()
        self.assertIsNone(self.take(), "held: not taken again at once")
        self.back_after(300)
        self.assertEqual(self.take(), self.fid, "a turn that was no hold leaves no wait")

    def test_the_wait_doubles_only_past_the_dormancy_clause_and_is_capped(self):
        waits = {d: hold_wait(self.settings, d) for d in (0, 1, 2, 39, 40, 41, 42, 43, 44, 500)}
        self.assertEqual(waits, {0: 300, 1: 300, 2: 300, 39: 300, 40: 300, 41: 600, 42: 1200, 43: 1800, 44: 1800, 500: 1800})
        # A family that only holds reaches the dormancy clause in forty base waits (~3.3 hours), not ~19.
        self.assertEqual(sum(hold_wait(self.settings, d) for d in range(1, DORMANT_CYCLES + 1)), DORMANT_CYCLES * 300)
        self.settings["researcher"]["dormant_cycles"] = 0  # the clause off: doubling from the second hold
        self.assertEqual([hold_wait(self.settings, d) for d in (1, 2, 3, 4, 5)], [300, 600, 1200, 1800, 1800])
        # In the scheduler: a family past the clause (one the idle rule exempts) waits longer at each hold.
        self.settings["researcher"]["dormant_cycles"] = DORMANT_CYCLES
        for dormant, wait in ((41, 600), (42, 1200), (43, 1800), (44, 1800)):
            self.hold(dormant)
            self.back_after(wait)

    def test_off_and_misread_settings(self):
        r = self.settings["researcher"]
        for off in (0, 0.0, None):
            r["hold_idle_seconds"] = off
            self.assertEqual(hold_wait(self.settings, 45), 0.0, repr(off))
        self.hold()
        self.assertEqual(self.take(), self.fid, "backoff off: back after idle_seconds as before")
        self.sched.release(self.fid, {"family": self.fid})
        for bad in (True, "300", -5, float("nan"), float("inf"), [300]):
            r["hold_idle_seconds"] = bad
            self.assertEqual(hold_wait(self.settings, 1), HOLD_IDLE_SECONDS, f"{bad!r} is misread: the default")
        r["hold_idle_seconds"] = 60
        r["hold_idle_max_seconds"] = None
        self.assertEqual(hold_wait(self.settings, 45), 60, "a null cap turns the doubling off")
        r["hold_idle_max_seconds"] = 30
        self.assertEqual(hold_wait(self.settings, 45), 60, "a cap under the base is the base")
        r["hold_idle_max_seconds"] = "much"
        self.assertEqual(hold_wait(self.settings, 45), HOLD_IDLE_MAX_SECONDS)
        del r["hold_idle_seconds"], r["hold_idle_max_seconds"]
        self.assertEqual(hold_wait(self.settings, 41), 600, "absent: the defaults")
        self.assertEqual(hold_wait({}, 1), HOLD_IDLE_SECONDS, "a scheduler without settings uses the defaults")

    def test_a_new_evaluation_or_a_queued_run_keeps_todays_turns(self):
        self.assertEqual(self.take(), self.fid)
        for out in ({"hold": True, "trials": 1}, {"hold": True, "pending_run": True}, {"pending_run": True}, {"trials": 3},
                    {"stored": 1}, {"hold": True, "retired": True}):
            self.store.set_state(self.fid, dormant_cycles=45)
            self.sched.release(self.fid, {"family": self.fid, **out})
            self.assertEqual(self.take(), self.fid, f"{out}: no hold wait")

    def test_news_lifts_the_wait_at_once(self):
        # A result of its own landed after the cycle (a late Train run, a robustness run, a validation): its trials rose.
        self.hold()
        self.store.bump(self.fid, trials=1, since_val_trials=1)
        self.assertEqual(self.take(), self.fid)
        self.sched.release(self.fid, {"family": self.fid})
        # Its dormant count restarted (a counted validation, a return to the Gym).
        self.hold(DORMANT_CYCLES + 3)
        self.store.set_state(self.fid, dormant_cycles=0)
        self.assertEqual(self.take(), self.fid)
        self.sched.release(self.fid, {"family": self.fid})
        # A stronger model's rewrite is ready: it is the next cycle's run.
        self.hold()
        self.store.set_state(self.fid, rewrite_ready={"code": "PARAMS = {}", "profile": "pro_asap"})
        self.assertEqual(self.take(), self.fid)
        self.sched.release(self.fid, {"family": self.fid})
        self.store.set_state(self.fid, rewrite_ready=None)
        # Its dormant count restarted between the cycle's end and the release: no wait at all.
        self.store.set_state(self.fid, dormant_cycles=0)
        self.assertEqual(self.take(), self.fid)
        self.sched.release(self.fid, {"family": self.fid, "hold": True, "dormant_cycles": 7})
        self.assertEqual(self.take(), self.fid)
        self.sched.release(self.fid, {"family": self.fid})
        # Anything else is no news.
        self.hold()
        self.store.set_state(self.fid, note_seen=True)
        self.store.update_family(self.fid, weight=0.9)
        self.assertIsNone(self.take())

    def test_other_families_run_while_one_waits(self):
        other = self.store.add_family(family_spec(SEEDS[1]), origin="seed")["id"]
        self.store.update_family(self.fid, weight=0.9)  # the bandit's favourite would go first
        self.hold()
        self.assertEqual(self.sched.waiting(), 1)
        self.assertEqual(self.take(), other)
        self.clock.advance(300)
        self.assertEqual(self.sched.waiting(), 0)


class HoldCycles(ResearcherCase):
    """The researcher's real cycle outcome through the scheduler."""

    def turn(self, sched, researcher):
        fid = sched.take(idle_seconds=0)
        if fid is None:
            return None
        out = researcher.cycle(fid)
        sched.release(fid, out)
        return out

    def test_a_hold_backs_its_family_off_and_a_new_run_or_a_queued_run_does_not(self):
        sched = Scheduler(self.store, clock=self.clock, settings=self.settings)
        r = self.researcher()
        self.assertTrue(self.turn(sched, r)["starter"])
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Nothing new to test until the breakdowns are read."})]}]
        out = self.turn(sched, r)
        self.assertEqual((out["hold"], out.get("trials", 0), out["dormant_cycles"], out["pending_run"]), (True, 0, 1, False))
        self.assertIsNone(self.turn(sched, r), "held: no turn")
        self.clock.advance(299)
        self.assertIsNone(self.turn(sched, r))
        self.clock.advance(1)
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"calls": [("gym_run", {"params": {"vrp_min": 1.5}})]}]
        out = self.turn(sched, r)
        self.assertEqual((out["trials"], out["pending_run"]), (1, True), "a new run, and the next one queued")
        self.assertNotIn(self.fam["id"], sched.held)
        self.steps = [{"text": "read it"}]
        out = self.turn(sched, r)
        self.assertIsNotNone(out, "a family with a run queued comes back at once, as before")
        self.assertEqual(self.pool.jobs[-1].params, {"vrp_min": 1.5})


class DeadExit(ResearcherCase):
    """A dead family (`idle_dead`) is offered retire on its REVISE turn, below `population.start`, down to the floor.
    Every Train run here is ineligible (10 trades a year): no best awaits validation unless a case says so."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=48, floor=1)
        self.other = self.store.add_family({**family_spec(self.spec), "id": "other-family"}, origin="seed")
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=10)
        self.cancelled = []
        self.pool.cancel_family = self.cancelled.append
        self.fid = self.fam["id"]
        self.researcher().cycle(self.fid)  # the starter: version 1, ineligible

    def dormant(self, n=DORMANT_CYCLES, fid=None):
        self.store.set_state(fid or self.fid, dormant_cycles=n)

    def tools(self):
        body = self.sail.bodies[-1]
        return [t["name"] for t in body["tools"]], body["tool_choice"]

    def alive(self):
        return sorted(f["id"] for f in self.store.families(alive=True))

    def test_a_dead_family_below_the_start_is_offered_retire_on_revise_and_retires(self):
        self.dormant(DORMANT_CYCLES - 1)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "The signal never fires often enough: refuted."})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(self.tools(), (["gym_run", "gym_sweep"], "required"), "not dead yet: a REVISE revises or holds")
        self.assertEqual(out["dormant_cycles"], DORMANT_CYCLES)
        self.assertEqual(idle_dead(self.store.family(self.fid), self.settings), DEAD)
        self.assertLess(len(self.alive()), self.settings["population"]["start"], "below the start")
        reason = "Condors on this root never reach the trade count: the mechanism is refuted."
        self.steps = [{"calls": [("retire", {"reason": reason})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(self.tools(), (["gym_run", "gym_sweep", "retire"], "required"), "dead: REVISE offers retire")
        status = next(i["content"] for i in reversed(self.sail.bodies[-1]["input"])
                      if i.get("role") == "user" and "Now: if a run just came back" in str(i.get("content")))
        self.assertIn(f"Your family {DEAD}", status)
        self.assertTrue(out["retired"])
        self.assertNotIn("error", out)
        self.assertEqual(self.store.family(self.fid)["band"], "retired")
        self.assertEqual(self.alive(), ["other-family"])
        self.assertEqual(self.cancelled, [self.fid])
        [lesson] = self.store.graveyard()
        self.assertIn(reason, lesson["lesson"])
        self.assertEqual(len(self.pool.jobs), 1, "no Gym job after the starter")

    def test_a_family_at_the_gate_held_awaiting_validation_or_outside_the_gym_never_retires(self):
        self.store.add_version(self.fid, self.code, {"vrp_min": 1.4}, author="test")
        cases = {
            "gate_ready": ({"gate_ready": True}, {}),
            "held at the gate": ({"gate_ready": True, "gate_hold": True}, {}),
            "awaiting validation": ({}, {"best_version": 2}),          # its best not validated, its 1.5x run not back
            "a candidate": ({}, {"band": "candidate"}),
        }
        for name, (state, fields) in cases.items():
            with self.subTest(name):
                self.store.set_state(self.fid, **{"gate_ready": False, "gate_hold": False, "dormant_cycles": DORMANT_CYCLES * 3,
                                                  **state})
                self.store.update_family(self.fid, **{"band": "gym", "best_version": None, **fields})
                fam = self.store.family(self.fid)
                self.assertIsNone(idle_dead(fam, self.settings) if not held_at_gate(fam) else None)
                self.assertFalse(self.researcher().can_retire(fam))
                if name == "awaiting validation":
                    self.assertTrue(awaiting_validation(fam))
                if name != "a candidate":
                    self.steps = [{"calls": [("retire", {"reason": "Dead."}), ("gym_run", {"hold": True, "note": "Waiting."})]}]
                    out = self.researcher().cycle(self.fid)
                    self.assertEqual(self.tools(), (["gym_run", "gym_sweep"], "required"), "not offered")
                    self.assertTrue(out["retire_refused"])
                    self.assertNotIn("error", out)
                self.assertEqual(Tournament(self.store, self.pool, self.settings).idle_pass()["retired"], [])
                self.assertIsNone(self.store.family(self.fid)["retired_at"])
        self.assertEqual(self.store.graveyard(), [])

    def test_the_floor_stops_retirement(self):
        self.settings["population"]["floor"] = 2  # two alive: at the floor
        self.dormant()
        self.dormant(fid="other-family")
        self.steps = [{"calls": [("retire", {"reason": "Dead."}), ("gym_run", {"hold": True, "note": "At the floor."})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(self.tools(), (["gym_run", "gym_sweep"], "required"), "at the floor: not offered")
        self.assertTrue(out["retire_refused"])
        self.assertEqual(Tournament(self.store, self.pool, self.settings).idle_pass()["retired"], [])
        # A stale "above the floor" read: the store's own count refuses at the floor.
        r = self.researcher()
        r.can_retire = lambda fam: True
        self.steps = [{"calls": [("retire", {"reason": "Dead."}), ("gym_run", {"hold": True, "note": "At the floor."})]}]
        out = r.cycle(self.fid)
        self.assertTrue(out["retire_refused"])
        self.assertEqual(self.alive(), [self.fid, "other-family"])
        # One above the floor: the idle pass retires one of the two dead families, the least favoured, and stops.
        self.settings["population"]["floor"] = 1
        self.store.update_family(self.fid, weight=0.6)
        self.store.update_family("other-family", weight=0.4)
        t = Tournament(self.store, self.pool, self.settings)
        self.assertEqual([row["family"] for row in t.idle_pass()["retired"]], ["other-family"])
        self.assertEqual(t.idle_pass()["retired"], [], "the floor holds the last one")
        self.assertEqual(self.alive(), [self.fid])


class IdlePass(RoundCase):
    """THE IDLE PASS: the idle rule alone (none of the round's other rules), every `tournament.retire_every_seconds`."""

    def test_due_every_retire_every_seconds_and_off_by_zero_null_or_a_misread_value(self):
        t = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        self.assertTrue(t.idle_due(), "a new process runs one at once")
        t.idle_pass()
        self.assertFalse(t.idle_due())
        self.clock.advance(299)
        self.assertFalse(t.idle_due())
        self.clock.advance(1)
        self.assertTrue(t.idle_due())
        for off in (0, None, -300, True, "300", float("nan"), float("inf")):
            self.settings["tournament"]["retire_every_seconds"] = off
            self.assertFalse(t.idle_due(), repr(off))

    def test_it_retires_only_dead_families_by_the_idle_rule(self):
        for i in range(8):
            self.family(f"f{i}")
            self.store.update_family(f"f{i}", validated_version=1)  # validated: nothing awaits validation ...
        self.store.update_family("f2", validated_version=None)       # ... but f2's best does
        self.settings["population"].update(start=8, floor=0)          # at the start
        self.store.update_family("f0", since_val_trials=150)          # dead: no eligible Train version in 150 evaluations
        for fid in ("f1", "f2", "f3", "f4", "f5"):
            self.store.set_state(fid, dormant_cycles=DORMANT_CYCLES)  # f1 dead by the dormancy clause
        self.store.set_state("f3", gate_ready=True)                   # at the gate
        self.store.set_state("f4", gate_ready=True, gate_hold=True)   # held there by the operator
        self.store.update_family("f5", band="candidate")              # outside the Gym band
        self.store.set_state("f6", dormant_cycles=DORMANT_CYCLES - 1)  # one cycle short
        self.store.update_family("f7", since_val_revisions=500)       # the round's own rule, not the pass's
        out = Tournament(self.store, self.pool, self.settings, clock=self.clock).idle_pass()
        self.assertEqual([row["family"] for row in out["retired"]], ["f0", "f1"])
        self.assertEqual(out["alive"], 6)
        self.assertEqual(out["retired"][1]["why"], f"It {DEAD}. {IDLE_CAUSE}", "the round's wording")
        self.assertEqual(sorted(self.pool.cancelled), ["f0", "f1"])
        lesson = next(g for g in self.store.graveyard() if g["family"] == "f1")
        self.assertIn("not a finding that the mechanism has no edge", lesson["lesson"], "a clock, not a refutation")
        causes = [e["payload"]["cause"] for e in self.store.events_after(0) if e["kind"] == "swarm.retired"]
        self.assertEqual(causes, [IDLE_CAUSE] * 2)


class IdlePassInTheLoop(LoopCase):
    def test_the_main_loop_runs_the_idle_pass_between_the_hourly_rounds_and_wires_the_backoff(self):
        sw = self.swarm()
        self.assertIs(sw.scheduler.settings, sw.settings, "the scheduler reads the settings the loop re-reads")
        self.assertEqual(sw.status()["holding"], 0, "the heartbeat counts the families waiting out a hold")
        sw.seed()  # 48 founders; the first tournament an hour away
        dead = [f["id"] for f in self.store.families(alive=True)[:3]]
        for fid in dead:
            self.store.set_state(fid, dormant_cycles=DORMANT_CYCLES)
        sw.step()
        for t in list(sw.rounds.values()):
            t.join(30)
        self.assertNotIn("tournament", sw.rounds)
        self.assertIn("idle", sw.rounds)
        self.assertEqual(sorted(f["id"] for f in self.store.families(alive=False)), sorted(dead))
        self.assertEqual(len(self.store.families(alive=True)), 45)
        self.assertFalse(sw.tournament.idle_due(), "the next pass in five minutes")
        sw.tournament.idle_at = time.time() - 301
        self.assertTrue(sw.tournament.idle_due())


if __name__ == "__main__":
    unittest.main()
