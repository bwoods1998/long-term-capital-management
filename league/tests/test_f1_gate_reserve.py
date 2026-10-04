"""RELEASE F1 WHERE TWO OF ITS STREAMS MEET (Oct 3, 2026): budget rule 2's GATE'S RESERVE and the fast lane's sealed look.

The owner's rule 2: "a program trades real money at Probe size as soon as it passes Validation and the unseen-market
test". His rule 3: research "up to $25 a day". The two meet at the end of a research day. If research could spend the
whole day's Sail dollars, a program that met the line in the evening would wait at the gate until 00:00 UTC for its
look. So the last tenth of the day is the gate's (league/ops/budget.py `gate_reserve`, league/swarm/guard.py): from
there the researchers' cycles, the births (the architect's, a reseed's and the tournament's own forks) and the architect
stop, and the tournament's validation round, the gate round and the nightly forward go on to the day's cap, where
everything stops.

The REAL pieces of both streams, together: `guard.SailGuard` over the caps `budget.sail_caps` gives from a budget.json
at the owner's ceiling; `loop.Swarm.step`; `tournament.Tournament` and `gate.Gate` under the switches the tree ships
(`gate.SEALED_LOOKS` True: the look is the route to Probe); `models.ModelRouter` under the day's paid-model line. The
Gym, Sail and the frontier are fakes (`test_swarm_rounds`, `swarm_fakes`: invented numbers); the fake pool asks the guard
for a box by its kind, as `pool.GymPool` does. Each stream pins its own half (`test_swarm_guard.Reserve`,
`test_swarm_loop`, `test_fast_lane`); this is the two in one process.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from league.ops import budget as BU
from league.swarm import gate as G
from league.swarm import settings as S
from league.swarm.guard import SWARM_SAIL_KINDS, SailGuard
from league.swarm.loop import Swarm
from league.swarm.models import ModelRouter
from league.swarm.pool import GymJob, GymPool, PoolError
from league.swarm.store import SwarmStore
from league.tests.evaluator_fakes import reviewed
from league.tests.swarm_fakes import Clock, FakeFrontier, FakeMonth, provider
from league.tests.test_swarm_rounds import SPEC, FakeGymPool, RoundCase, strong, weak

PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}


class Pool(FakeGymPool):
    """`FakeGymPool` with what `Swarm.step` asks of a pool. A job runs only where the guard allows its box's kind, as
    `pool.GymPool` asks it (`allowed(box.kind)`: a gate box for a job with a gate reason, a Gym box for every other)."""

    def __init__(self, answer, allowed):
        super().__init__(answer)
        self.allowed = allowed
        self.ran: list[tuple[str, str]] = []
        self.refused: list[tuple[str, str]] = []
        self.scaled: list[str] = []

    def wait(self, job, timeout=None, late=None, late_fail=None):
        kind = "gate" if job.gate else "gym"
        if not self.allowed(kind):
            self.refused.append((kind, job.window))
            raise PoolError("the guard allows no box")
        self.ran.append((kind, job.window))
        return super().wait(job, timeout, late, late_fail)

    def manage(self):
        return {}

    def status(self):
        return {}

    def scale_to_zero(self, why, **kw):
        self.scaled.append(why)


class TheLastTenthOfTheDay(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        # The code's defaults whatever the repository's policy.json comes to say (the join is in the code).
        for patcher in (mock.patch.object(S, "POLICY_PATH", self.root / "no-policy.json"),
                        mock.patch("league.swarm.loop.log", lambda message: None)):  # the swarm's log is not this test's
            patcher.start()
            self.addCleanup(patcher.stop)
        # One synthetic clock for the budget record, settings read, admissions and Provider accounting.
        wall = time.time()
        self.clock = Clock(wall - wall % 86400 + 12 * 3600)
        # The day's budget as the `budget` job writes it at THE OWNER'S CEILING, and the owner's own file: a Gym, and the
        # screens and holds that judge a Train run these invented families do not have left out (their own tests'
        # subject: `test_swarm_rounds.RoundCase` leaves out the same).
        (self.root / "budget.json").write_text(json.dumps({"schema": BU.SCHEMA, "at": self.clock(), "meters": {
            meter: {"research_usd_day": BU.ceiling_usd_day(meter)} for meter in BU.METERS}}))
        (self.root / "swarm.json").write_text(json.dumps({
            "enabled": True, "gym": {"enabled": True, "image_checkpoint": "sbcp_gym", "gate_checkpoint": "sbcp_gate"},
            "tournament": {"require_robustness": False, "drift_screen": False}, "gate": {"look_holds": None},
            "architect": {"require_card": False}}))
        with mock.patch("time.time", self.clock):
            self.settings = S.load(self.root, config={})
        self.cap = BU.ceiling_usd_day("sail")
        self.reserve = BU.gate_reserve(self.cap)
        self.assertEqual((self.settings["budget"]["source"], self.settings["budget"]["sail_usd_day"]), ("budget.json", self.cap))
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.guard = SailGuard(self.store, self.settings, lambda: (5000.0, 5.0), clock=self.clock,
                               disk_free=lambda: 100.0 * 2 ** 30)
        self.pool = Pool(lambda job: strong(job) if job.family == "a" else weak(job), self.guard.allows)
        self.replies: list = []
        self.provider, self.sail = provider(self.root / "p.sqlite",
                                            lambda body: self.replies.pop(0) if self.replies else {"text": "{}"},
                                            clock=self.clock)
        self.addCleanup(self.provider.close)
        self.router = ModelRouter(self.store, self.provider, settings=self.settings, month=FakeMonth(None),
                                  frontier_factory=lambda model: FakeFrontier(model))
        self.swarm = Swarm(self.root, settings=self.settings, config={}, store=self.store, router=self.router,
                           pool=self.pool, guard=self.guard, clock=self.clock, sleep=lambda s: time.sleep(min(s, 0.02)))
        self.addCleanup(self.join_rounds)  # registered last, so it runs first: no round outlives the store it writes to
        # What makes new research, and the nightly forward (its own replay is not what meets here): each only named.
        self.ran: list[str] = []
        sw = self.swarm
        sw.gate.forward_due = lambda: True
        sw.gate.forward = lambda: self.ran.append("forward") or {}
        sw.architect_pass = lambda: self.ran.append("architect") or {}
        sw.reseed = lambda: self.ran.append("reseed") or []
        sw.diagnostician.due = lambda: True
        sw.diagnostician.run = lambda: self.ran.append("diagnostician") or {}

    @staticmethod
    def join_rounds(seconds=30):
        for thread in threading.enumerate():
            if thread.name.startswith("round-"):
                thread.join(seconds)

    def family(self, fid):
        fam = self.store.add_family({**SPEC, "id": fid}, origin="seed")
        code = f"# {fid}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n"
        version = self.store.add_version(fam["id"], code, {}, author="seed")
        self.store.update_family(fam["id"], best_version=version["n"])

    def step(self, **due):
        """One pass of the main loop a few minutes on (the guard reads again), its rounds joined; the rounds it started.
        `due` names the rounds whose last run is put back so that they are due."""
        self.clock.advance(400)
        for name in due:
            self.store.put(f"{name}_at", 1.0)
        self.swarm.rounds.clear()
        self.ran.clear()
        self.swarm.step()
        self.join_rounds()
        return set(self.swarm.rounds)

    def booked(self):
        now = self.clock()
        return self.store.spent(SWARM_SAIL_KINDS, since=now - now % 86400)

    def born(self):
        """How the families born by the swarm itself came (the two this test founds are no event)."""
        return [e["payload"].get("origin") for e in self.store.events_after(0) if e["kind"] == "swarm.born"]

    def test_research_stops_and_the_sealed_gate_still_makes_its_look_until_the_days_cap(self):
        self.assertIs(G.SEALED_LOOKS, True, "release F1 ships the sealed look as the route to Probe")
        self.assertEqual((self.cap, self.reserve), (15.0, 1.5))
        self.family("a")
        self.family("b")
        self.store.put("gate_at", self.clock() + 400)  # the gate's round is not due in the first pass (it follows validation)
        # Research has booked nine tenths of the day's Sail dollars.
        self.store.add_spend("gym_box", self.cap - self.reserve)
        rounds = self.step(tournament=True, architect=True)
        self.assertEqual((self.guard.braked, self.guard.research_held), (False, True), self.guard.reason)
        self.assertIn("the last 1.50 is kept for validation, the gate and the nightly forward", self.guard.held)
        self.assertEqual((self.guard.allows(), self.guard.allows("gym"), self.guard.allows("gate"), self.guard.allows("research"),
                          self.guard.allows("architect"), self.guard.allows("birth")), (True, True, True, False, False, False))
        self.assertEqual((rounds - {"idle"}, self.ran), ({"tournament", "forward"}, ["forward"]),
                         "validation and the nightly forward go on; no architect pass, no reseed, no diagnostician")
        self.assertTrue(self.store.get("tournament_at"), "and the architect was due but for the hold")
        self.assertTrue(self.store.family("a")["state"]["gate_ready"], "a met the line in the hold: validated on a Gym box")
        self.assertIn(("gym", "validation"), self.pool.ran)
        self.assertEqual((self.born(), len(self.store.families())), ([], 2),
                         "and the round forked nothing, though a is worth a fork: a fork is a birth")
        # The next pass, still in the hold: the gate's round reads it, audits it and makes its one look on a gate box.
        self.replies = [PASS, PASS]
        rounds = self.step(gate=True, architect=True)
        self.assertEqual((self.guard.braked, self.guard.research_held), (False, True))
        self.assertEqual((rounds - {"idle"}, self.ran), ({"gate", "forward"}, ["forward"]))
        looks = self.store.looks()
        self.assertEqual([(look["family"], look["passed"]) for look in looks], [("a", 1)], "the look was made in the hold")
        self.assertEqual(self.store.family("a")["band"], "candidate", "and a pass is a Candidate at once")
        self.assertIn(("gate", "holdout"), self.pool.ran)
        self.assertEqual((self.pool.refused, self.pool.scaled), ([], []), "a hold is no brake: no box refused, no Gym scaled down")
        self.assertEqual([e for e in self.store.events_after(0) if e["kind"] == "swarm.cycle"], [], "no researcher cycle")
        self.assertEqual(self.born(), [], "no birth of any kind in the hold")
        # The day's cap itself: everything stops, the gate's rounds included, until 00:00 UTC.
        self.store.add_spend("gym_box", round(self.cap - self.booked(), 4))
        rounds = self.step(tournament=True, gate=True, architect=True)
        self.assertEqual((self.guard.braked, self.guard.causes), (True, ["research_budget"]))
        self.assertEqual((rounds, self.ran, self.born()), (set(), [], []))
        self.assertEqual(len(self.pool.scaled), 1, "the brake scales the Gym to zero, as ever")
        self.assertFalse(self.guard.allows("gate"))
        # A new UTC day: its own dollars and its own reserve. The same pass starts research again (the control: the hold
        # alone was what stopped the architect).
        self.clock.advance(86400)
        rounds = self.step(tournament=True, gate=True, architect=True)
        self.assertEqual((self.guard.braked, self.guard.research_held, self.guard.allows("research")), (False, False, True))
        self.assertTrue({"tournament", "gate", "forward", "architect"} <= rounds, rounds)
        self.assertIn("architect", self.ran)
        self.assertIn("diagnostician", self.ran)
        self.assertEqual(self.born(), ["fork"], "and the tournament's round forks a again")

    def test_the_architects_own_spend_is_outside_the_pace_and_inside_the_day(self):
        """WHERE THE RESEARCH STREAM MEETS THE RESERVE (the captain's B5). The researchers' hourly pace leaves out the
        architect's own passes (`loop.architect_spent`), so one pass never pauses every researcher. That is built on
        top of the reserve, not beside it: the Sail guard's day counts every dollar of those passes, so the architect's
        own spend brings the hold, and at the hold the architect stops although the pace would let it run. And a park
        is counted toward dormancy only while a cycle could have run: never in the hold."""
        sw = self.swarm
        counted: list[int] = []
        sw.scheduler.count_parked = lambda: counted.append(1) or []
        sw.architect.due = lambda: True
        sw.architect.refilling = lambda: True
        self.store.put("tournament_at", self.clock() + 10 ** 6)  # no tournament round: this is about the architect alone
        self.store.put("gate_at", self.clock() + 10 ** 6)
        pace = float(self.settings["researcher"]["usd_per_hour"])
        self.assertEqual((self.settings["researcher"].get("sail_usd_per_hour"), pace),
                         (None, self.settings["budget"]["knobs"]["researcher.sail_usd_per_hour"]),
                         "the pace in force is the budget's own knob")
        # The architect's passes of the last hour, by its own request keys: under the reserve, far over the pace.
        under = self.cap - self.reserve - 1.0
        self.assertGreater(under, pace)
        self.store.add_spend("sail_model", under, family="swarm", detail={"desk": "swarm", "key": "swarm:architect:1791030654"})
        self.step()
        status = sw.pace_status()
        self.assertEqual((status["spent_last_hour_usd"], status["paused"]), (0.0, False),
                         "the architect's own pass is no part of the researchers' hour")
        self.assertAlmostEqual(self.booked(), under, msg="and every dollar of it is in the guard's day")
        self.assertEqual((self.guard.braked, self.guard.research_held, self.ran.count("architect"), len(counted)),
                         (False, False, 1, 1), "under the reserve the architect runs and a park is counted")
        # One more pass of its own reaches the reserve: the hold, on the architect's dollars alone.
        self.store.add_spend("sail_model", 1.0, family="swarm", detail={"desk": "swarm", "key": "swarm:architect:1791034254"})
        self.step()
        self.assertEqual((self.guard.braked, self.guard.research_held, self.guard.allows("research")), (False, True, False),
                         self.guard.held)
        self.assertFalse(sw.over_pace(), "the pace would still let the architect run")
        self.assertEqual((self.ran.count("architect"), self.ran.count("reseed"), len(counted)), (0, 0, 1),
                         "the hold stops it first, and no park is counted while no cycle could run")
        # The rest of the day's cap, again its own dollars: the brake, as for any Sail dollar.
        self.store.add_spend("sail_model", self.reserve, family="swarm", detail={"desk": "swarm", "key": "swarm:architect:1791037854"})
        self.step()
        self.assertEqual((self.guard.braked, self.guard.causes, len(counted)), (True, ["research_budget"], 1))
        # A new UTC day: the architect and the count go on.
        self.clock.advance(86400)
        self.step()
        self.assertEqual((self.guard.braked, self.guard.research_held, self.ran.count("architect"), len(counted)),
                         (False, False, 1, 2))

    def looks_failed(self):
        return [e["payload"] for e in self.store.events_after(0)
                if e["kind"] == "swarm.gate" and e["payload"].get("action") == "look_failed"]

    def test_a_look_the_brake_kept_from_a_gate_box_is_no_try_and_never_a_refusal(self):
        """A BRAKED ROUND IS NOT A TRY (B11, league/swarm/gate.py). The day's cap lands while a gate round is already
        under way: its look is queued, the guard allows no gate box, and the look never runs. Before B11 each such round
        counted a try and the third refused the program for good ("the gate box could not make this holdout look three
        times") with its incubator bar, although nobody judged it and no box failed. Now the tries stay as they were,
        the place stays ready, and the look is made when the guard allows a box again."""
        self.family("a")
        self.store.put("gate_at", self.clock() + 10 ** 6)  # the loop starts no gate round of its own: this test runs them
        self.step(tournament=True)
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        sha = G.run_sha(self.store.version("a", 1))
        gate = self.swarm.gate
        # The round has already paid for both readers before the brake lands. Strict model admission permits no
        # fresh paid review after the cap; only this cached review/audit can proceed to the still-queued look.
        self.replies = [PASS, PASS]
        fam, version = self.store.family("a"), self.store.version("a", 1)
        review = gate.review(fam, version)
        audit = gate.audit(fam, version)
        self.store.set_state("a", review={**review, "sha": sha, "version": 1, "audit": audit})
        self.assertEqual(len(self.sail.bodies), 2)
        # The day's cap: the guard brakes everything, the gate's boxes included.
        self.store.add_spend("gym_box", round(self.cap - self.booked(), 4))
        self.clock.advance(400)
        self.guard.check()
        self.assertEqual((self.guard.braked, self.guard.allows("gate"), gate.braked()), (True, False, True))
        for round_ in range(4):  # a round already running when the brake landed, four times over
            out = gate.run()
            self.assertEqual((out["looked"], out["refused"]), ([], []), round_)
            state = self.store.family("a")["state"]
            self.assertEqual((state["gate_ready"], state.get("look_inflight"), state.get("gated_sha")), (True, None, None),
                             "the look is owed again, its place kept")
            self.assertIsNone(self.store.get(f"look_tries:{sha}"), "no try counted")
        self.assertEqual(self.pool.refused, [("gate", "holdout")] * 4, "the guard allowed no gate box")
        self.assertEqual([(e["braked"], e["error"]) for e in self.looks_failed()], [(True, "the guard allows no box")] * 4)
        self.assertEqual((self.store.refusals("a"), self.store.looks()), ([], []), "no refusal and no look")
        self.assertNotIn(sha, self.store.family("a")["state"].get("incubator_barred") or {}, "and no bar")
        self.assertEqual(len(self.sail.bodies), 2, "the review and the audit were paid once and are kept")
        # A new UTC day: the guard allows a box. A Gym that fails then IS a try, counted from where the tries stood.
        self.clock.advance(86400)
        self.guard.check()
        self.assertEqual((self.guard.braked, gate.braked()), (False, False))
        self.pool.fail.add("a")
        self.assertEqual(gate.run()["looked"], [])
        self.assertEqual((self.store.get(f"look_tries:{sha}"), "braked" in self.looks_failed()[-1]), (1, False))
        self.pool.fail.clear()
        out = gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}], "and the look is made: its one look")
        self.assertEqual((self.store.family("a")["band"], len(self.store.looks())), ("candidate", 1))


class TheRealPoolsQueue(RoundCase):
    """A BRAKED ROUND IS NOT A TRY on the REAL `pool.GymPool` (no box: nothing is forked here): a look whose waiter
    gives up with its job still in the queue is "abandoned before it ran", and whether that is a try is the guard's
    answer to the pool's own question."""

    def setUp(self):
        super().setUp()
        self.allowed = {"gym": True, "gate": False}
        self.settings["gym"]["image_checkpoint"] = "sbcp_gym"
        self.pool = GymPool(self.store, None, self.settings, clock=self.clock, threaded=False,
                            allowed=lambda kind: self.allowed[kind])
        self.pool._bundle_version = "gym-engine-test"  # the pool's own bundle, named without building one
        self.gate = G.Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)
        self.family("a")
        self.sha = G.run_sha(self.store.version("a", 1))
        self.store.set_state("a", gate_ready=True, validation_version=1, validation_line={"passed": True},
                             validation_image="sbcp_gym", validation_bundle="gym-engine-test",
                             validation_numbers={"sharpe_daily": 0.2}, review=reviewed(self.sha))
        # The gate waits its run timeout and ten minutes for a look: a hundredth of a second here.
        waits = mock.patch.object(G.settings_mod, "run_timeout", return_value=-599.99)
        waits.start()
        self.addCleanup(waits.stop)

    def round(self):
        out = self.gate.run()
        self.assertEqual((out["looked"], out["refused"], self.pool.queue), ([], [], []), "the look never ran")
        state = self.store.family("a")["state"]
        self.assertEqual((state["gate_ready"], state.get("look_inflight"), state.get("gated_sha")), (True, None, None))
        [event] = [e["payload"] for e in self.store.events_after(self.seen) if e["payload"].get("action") == "look_failed"]
        self.seen = self.store.events_after(0)[-1]["seq"]
        return event

    def test_a_look_abandoned_in_the_queue_is_a_try_only_while_the_guard_allows_a_gate_box(self):
        self.seen = 0
        job = GymJob(family="a", version=1, code="", params={}, window="holdout", roots=("SPY",), gate="a look")
        self.assertEqual((job.attempts, job.result, job.late), (0, None, None), "a job no box took")
        for _ in range(4):
            event = self.round()
            self.assertIs(event.get("braked"), True)
            self.assertIn("did not answer within", event["error"])
            self.assertIsNone(self.store.get(f"look_tries:{self.sha}"), "braked: no try")
        self.assertEqual(self.store.refusals("a"), [])
        # The guard allows a gate box and none comes all the same (the pool's own trouble): tries, and at the third the
        # refusal, as before.
        self.allowed["gate"] = True
        for tries in (1, 2):
            self.assertNotIn("braked", self.round())
            self.assertEqual(self.store.get(f"look_tries:{self.sha}"), tries)
        self.gate.run()
        self.assertEqual((self.store.get(f"look_tries:{self.sha}"), [r["stage"] for r in self.store.refusals("a")]), (3, ["gym"]))


if __name__ == "__main__":
    unittest.main()
