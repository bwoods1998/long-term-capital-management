"""THE LOOK HOLDS (L6(b) and L6(c), the owner's approval of Oct 2, 2026; league/swarm/gate.py `look_hold`).

Every holdout look raises the Holm bar of every later one. The gate HOLDS a look (no look, no try, no review, no audit,
no sealed read) at a long-delta version whose Train profit leans on market drift (drift share >= 0.25 of its own Train
drift fit): recorded in its own table, never as a refusal; a new version that clears it is looked at. On the money path
that hold is a failed look (reviews A1 and B1 of PR #484): the held version's execution tuition ends, even when the hold
lands after a passed review, and its program never trades the incubator.

THE POWER HOLD IS A WAIT, NOT A BAR (release F1, the captain's L4 of Oct 3, 2026; `Gate.wait_look`, `gate.waiting`). A
version whose expected holdout power, at the level the look would have to reach under Holm, is below 0.30 (missing
figures too: fail-closed) gets no look now, and nothing is closed: no hold row, no outcome, no incubator bar, no refusal
row, no look spent. It keeps its gate place under its own marker, is judged again every round (the program bar, the
duplicate rule and the rations still refuse it), and gets its one look when the level allows. It blocks neither its
family's research nor the gate's other families, and no real order goes on it while it waits.

The researcher hears words with no figure (D2a). Each hold is a setting; null restores the gate without it. Every figure
is invented."""

from __future__ import annotations

import json
import random
import re
import unittest
from unittest.mock import patch

from league.ops import scoreboard
from league.swarm import allocation, bands, evidence, incubator
from league.swarm.bands import program_refusal
from league.swarm.gate import (DUPLICATE_STAGE, HOLD_DRIFT_STAGE, HOLD_OUTCOME, HOLD_POWER_STAGE, HOLD_WORDS, LOOK_WAIT,
                               PROGRAM_BAR_STAGE, WAIT_OVER_WORDS, WAIT_STAGES, Gate, holdout_sessions, look_hold_settings,
                               run_sha, sessions_between, waiting)
from league.swarm.researcher import Researcher
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import drift_block, result
from league.tests.test_swarm_d2a_sentinel import printed_forms
from league.tests.test_swarm_incubator import SESSIONS, GateCase, accepts, live_rows
from league.tests.test_swarm_rounds import SPEC, RetiredTuition, RoundCase, strong, weak

PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
#: The figures of a version the holds let through: drift-light Train, and a Validation Sharpe the holdout can judge.
NEUTRAL = dict(alpha=150.0, drift=20.0, beta=200.0)
HEAVY = dict(alpha=100.0, drift=60.0, beta=200.0)  # long-delta, drift share 0.375
STRONG_SHARPE, THIN_SHARPE = 0.2, 0.05


def lean(alpha: float, drift: float, beta: float, *, t: float = 2.0) -> dict:
    """An invented Gym Train `drift` block: every year alike (`swarm_fakes.drift_block`) with beta `beta` (dollars per unit
    return). The default t passes the drift screen."""
    block = drift_block(t=t, alpha_usd=alpha, drift_usd=drift)
    for row in (*block["years"].values(), block["pooled"]):
        row["beta"] = beta
    return block


class HoldCase(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30}  # the defaults (RoundCase: off)
        # The gate's own hold is what is tested here: the versions reach the gate as one validated before F1's Train
        # screen did (`researcher.train_gate`, which sets a drift carrier aside before it is validated:
        # league/tests/test_swarm_f1_gate_ready.py tests it, and that it never disagrees with this hold).
        self.settings["researcher"]["carrier_screen"] = False
        self.sharpe: dict[str, float | None] = {}
        self.answer = self.gym
        self.replies = [PASS] * 8
        self.gate = Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def gym(self, job):
        """Validation figures that meet the line, with the family's all-days daily Sharpe; every holdout look fails."""
        if job.window == "holdout":
            return weak(job)
        rng = random.Random(f"{job.family}|{job.version}|{job.window}|{job.stress}")
        daily = [round(rng.gauss(6.0, 10.0), 4) for _ in range(250)]
        sharpe = self.sharpe.get(job.family, STRONG_SHARPE)
        out = result(job.name, daily=daily, window=job.window, pnl=round(sum(daily), 2), t=2.5,
                     sharpe_daily=STRONG_SHARPE if sharpe is None else sharpe)
        if sharpe is None:  # a summary without the figure
            out["summary"]["sharpe_daily"] = None
        return out

    def ready(self, fid: str, *, drift: dict | None = NEUTRAL, sharpe: float | None = STRONG_SHARPE, version: int | None = None,
              block: dict | None = None) -> int:
        """`fid`'s version (its first, or a new one when `version` is given) with a Train run carrying `drift` (None: no
        drift fit; `block`: this block as it is), made its best and validated."""
        if self.store.family(fid) is None:
            self.family(fid)
        n = 1
        if version is not None:
            v = self.store.add_version(fid, f"# {fid} v{version}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\n"
                                            f"def decide(ctx):\n    return []  # {version}\n", {}, author="seed")
            n = int(v["n"])
            self.store.update_family(fid, best_version=n)
        train = result(f"{fid}-train-{n}", window="train")
        if block is not None:
            train["drift"] = block
        elif drift is None:
            train.pop("drift", None)
        else:
            train["drift"] = lean(**drift)
        self.store.add_run(fid, n, train, window="train", stress=1.0, purpose="train")
        self.sharpe[fid] = sharpe
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        state = self.store.family(fid)["state"]
        self.assertEqual((state["validation_version"], state["gate_ready"]), (n, True), "validated and gate-ready")
        return n

    def sha(self, fid: str, n: int) -> str:
        return run_sha(self.store.version(fid, n))

    def holdout_jobs(self, fid: str | None = None) -> list:
        return [j for j in self.pool.jobs if j.window == "holdout" and (fid is None or j.family == fid)]

    def paid(self) -> int:
        """Model calls made: Sail's bodies and the gateway's frontier asks."""
        return len(self.sail.bodies) + len(self.asked)

    def hold_events(self, fid: str | None = None) -> list[dict]:
        return [e for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["payload"].get("action") == "look_hold"
                and (fid is None or e["family"] == fid)]

    def assert_held(self, fid: str, n: int, stage: str, *, paid: int = 0, reviewed: bool = False) -> dict:
        """Held at `stage`: one hold row with the researcher's words, the version closed at the gate with outcome "held",
        no look, no try, no review or audit (`reviewed`: the ones made before the hold, kept), no sealed read, no refusal
        row; and, on the money path, a failed look's effects: the program's incubator bar recorded, the House's reader
        refusing it, and no execution-tuition row. Returns the private figures."""
        sha = self.sha(fid, n)
        [row] = self.store.look_holds(fid)
        self.assertEqual((row["stage"], row["version"], row["run_sha"]), (stage, n, sha))
        self.assertEqual(row["reason"], HOLD_WORDS[stage])
        state = self.store.family(fid)["state"]
        self.assertFalse(state["gate_ready"], "gate_ready cleared for this version")
        self.assertEqual(state["gated_sha"], sha)
        self.assertEqual(state["gate_outcome"]["result"], HOLD_OUTCOME)
        self.assertEqual(state["gate"], HOLD_WORDS[stage])
        self.assertEqual(self.holdout_jobs(fid), [], "no sealed read")
        self.assertEqual([x for x in self.store.looks() if x["family"] == fid], [], "no look row")
        self.assertEqual(self.store.lineage_looks(fid, include_inflight=True), 0, "no look spent or reserved")
        self.assertIsNone(self.store.get(f"look_tries:{sha}"), "no try counted")
        self.assertIsNone(state.get("look_inflight"))
        if not reviewed:
            self.assertIsNone(state.get("review"), "no review or audit recorded")
        self.assertEqual(self.paid(), paid, "no review or audit paid for it")
        self.assertEqual(self.store.refusals(fid), [], "a hold is no refusal row")
        fam = self.store.family(fid)
        self.assertEqual(state["incubator_barred"][sha]["why"], f"the gate held its holdout look ({stage})",
                         "the program's incubator bar, recorded first (THE VERDICT FIRST)")
        self.assertIsNotNone(incubator.gate_bar(self.store, fam, n, sha=sha), "the incubator bars it")
        self.assertIsNotNone(program_refusal(state, sha), "the House's reader refuses it")
        self.assertEqual([r for r in bands.read(self.root) if r["family"] == fid], [], "no execution tuition")
        [event] = self.hold_events(fid)
        self.assertEqual((event["payload"]["stage"], event["payload"]["version"]), (stage, n))
        self.assertEqual(set(event["payload"]) - {"action", "version", "sha", "stage", "holds", "_figures"}, set(),
                         "every figure is under the private key")
        self.assertIsNone(waiting(state), "a hold is final: the version holds no place")
        return event["payload"]["_figures"]

    def wait_events(self, fid: str | None = None) -> list[dict]:
        return [e for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["payload"].get("action") == "look_wait"
                and (fid is None or e["family"] == fid)]

    def assert_waiting(self, fid: str, n: int, *, paid: int = 0, reviewed: bool = False) -> dict:
        """THE POWER HOLD IS A WAIT, NOT A BAR: the version keeps its gate place under its own marker and nothing a
        hold writes is written. No hold row, no outcome, no incubator bar, no refusal row, the gate's mark not set; no
        look, no try, no review or audit (`reviewed`: the ones made before the wait, kept), no sealed read; one
        `look_wait` event, its figures private; the researcher's words; and no real order while it waits. Returns the
        private figures."""
        sha = self.sha(fid, n)
        fam = self.store.family(fid)
        state = fam["state"]
        self.assertEqual(self.store.look_holds(fid), [], "a wait is no hold row")
        self.assertEqual(self.store.refusals(fid), [], "nor a refusal row")
        self.assertEqual(self.hold_events(fid), [], "nor a hold's event")
        marker = state[LOOK_WAIT]
        self.assertEqual((marker["sha"], marker["n"], marker["stage"]), (sha, n, HOLD_POWER_STAGE))
        self.assertEqual(waiting(state), marker, "it waits at the gate now, under its own marker")
        self.assertFalse(state["gate_ready"], "gate_ready cleared: a waiting family's share and retirement are a Gym family's")
        self.assertNotEqual(state.get("gated_sha"), sha, "the gate is not done with it")
        self.assertNotIn((state.get("gate_outcome") or {}).get("result"), bands.BAD_OUTCOMES, "no outcome written")
        self.assertNotIn(sha, state.get("incubator_barred") or {}, "no incubator bar")
        self.assertIsNone(incubator.gate_bar(self.store, fam, n, sha=sha), "the incubator's own reader finds no bar")
        self.assertIsNone(program_refusal(state, sha), "nor does the House's reader's belt")
        self.assertEqual(state["gate"], HOLD_WORDS[HOLD_POWER_STAGE])
        self.assertEqual(self.holdout_jobs(fid), [], "no sealed read")
        self.assertEqual([x for x in self.store.looks() if x["family"] == fid], [], "no look row")
        self.assertEqual(self.store.lineage_looks(fid, include_inflight=True), 0, "no look spent or reserved")
        self.assertIsNone(self.store.get(f"look_tries:{sha}"), "no try counted")
        self.assertIsNone(state.get("look_inflight"))
        if not reviewed:
            self.assertIsNone(state.get("review"), "no review or audit recorded")
        self.assertEqual(self.paid(), paid, "no review or audit paid for it")
        self.assertFalse(Tournament(self.store, self.pool, self.settings).gate_spent(fid, n, state),
                         "the gate is not done with it: a validation judged again readies it again")
        self.assertEqual([r for r in bands.read(self.root) if r["family"] == fid], [], "no real order while it waits")
        [event] = self.wait_events(fid)
        self.assertEqual((event["payload"]["stage"], event["payload"]["version"], event["payload"]["holds"]),
                         (HOLD_POWER_STAGE, n, [HOLD_POWER_STAGE]))
        self.assertEqual(set(event["payload"]) - {"action", "version", "sha", "stage", "holds", "_figures"}, set(),
                         "every figure is under the private key")
        return event["payload"]["_figures"]

    def written(self) -> tuple:
        """Everything a gate round can write for a family: its events, rows and state."""
        return (len(self.store.events_after(0)), self.store.look_holds(), self.store.refusals(), self.store.looks(),
                {f["id"]: f["state"] for f in self.store.families()})


class TheDriftHold(HoldCase):
    def test_a_long_delta_drift_heavy_version_is_held_before_any_review_or_sealed_read(self):
        n = self.ready("a", drift=HEAVY)
        with patch.object(Gate, "review", autospec=True, side_effect=Gate.review) as review, \
                patch.object(Gate, "audit", autospec=True, side_effect=Gate.audit) as audit, \
                patch.object(Gate, "look", autospec=True, side_effect=Gate.look) as look:
            out = self.gate.run()
        self.assertEqual((review.call_count, audit.call_count, look.call_count), (0, 0, 0))
        self.assertEqual((out["look_held"], out["looked"], out["refused"]), (["a"], [], []))
        figures = self.assert_held("a", n, HOLD_DRIFT_STAGE)
        self.assertAlmostEqual(figures["drift"]["share"], 180.0 / 480.0)
        self.assertTrue(figures["drift"]["long_delta"])
        self.assertEqual(figures["drift"]["line"], 0.25)
        self.assertFalse(figures["power"]["held"], "the power alone would have let it through")
        # The next round asks nothing of it: closed at the gate.
        again = self.gate.run()
        self.assertEqual((again["look_held"], len(self.store.look_holds("a"))), ([], 1))

    def test_the_share_is_read_against_the_line_and_a_short_or_flat_program_is_never_held_for_drift(self):
        for fid, drift, held in (("at-line", dict(alpha=75.0, drift=25.0, beta=200.0), True),
                                 ("below", dict(alpha=76.0, drift=24.0, beta=200.0), False),
                                 ("short", dict(alpha=100.0, drift=-300.0, beta=-150.0), False),
                                 ("flat", dict(alpha=100.0, drift=0.0, beta=0.0), False)):
            n = self.ready(fid, drift=drift)
            hold = self.gate.look_hold(self.store.family(fid), n)
            self.assertEqual(hold is not None and HOLD_DRIFT_STAGE in hold["holds"], held, fid)

    def test_a_held_version_is_closed_and_a_new_version_that_clears_the_holds_is_looked_at(self):
        self.ready("a", drift=HEAVY)
        self.gate.run()
        state = self.store.family("a")["state"]
        self.assertTrue(Tournament(self.store, self.pool, self.settings).gate_spent("a", 1, state),
                        "the tournament never makes the held version gate-ready again")
        n = self.ready("a", drift=NEUTRAL, version=2)
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual([(j.family, j.version) for j in self.holdout_jobs()], [("a", n)])
        self.assertEqual(len(self.store.look_holds("a")), 1, "the first version's hold only")

    def test_a_version_with_no_drift_fit_is_held_fail_closed(self):
        n = self.ready("a", drift=None)  # the drift screen is off (as RoundCase's), so the gate reaches the hold
        self.gate.run()
        figures = self.assert_held("a", n, HOLD_DRIFT_STAGE)
        self.assertFalse(figures["drift"]["known"])
        self.assertEqual(figures["drift"]["why"], "no Train drift fit")

    def test_a_fit_the_screen_reads_but_without_a_beta_is_held_fail_closed(self):
        self.settings["tournament"]["drift_screen"] = True
        block = lean(**NEUTRAL)
        for row in (*block["years"].values(), block["pooled"]):
            row.pop("beta")
        n = self.ready("a", block=block)
        self.gate.run()
        figures = self.assert_held("a", n, HOLD_DRIFT_STAGE)
        self.assertIn("lacks its alpha, drift or beta", figures["drift"]["why"])

    def test_a_long_delta_fit_with_no_alpha_and_no_drift_is_held_fail_closed(self):
        n = self.ready("a", drift=dict(alpha=0.0, drift=0.0, beta=200.0))
        self.gate.run()
        figures = self.assert_held("a", n, HOLD_DRIFT_STAGE)
        self.assertIsNone(figures["drift"]["share"])


class ThePowerHold(HoldCase):
    """THE POWER HOLD IS A WAIT, NOT A BAR (the module docstring)."""

    def test_a_version_the_holdout_cannot_judge_waits_before_any_review_or_sealed_read(self):
        self.assertEqual(WAIT_STAGES, {HOLD_POWER_STAGE}, "the power hold alone waits; the drift hold stays final")
        n = self.ready("a", sharpe=THIN_SHARPE)
        with patch.object(Gate, "review", autospec=True, side_effect=Gate.review) as review, \
                patch.object(Gate, "audit", autospec=True, side_effect=Gate.audit) as audit, \
                patch.object(Gate, "look", autospec=True, side_effect=Gate.look) as look:
            out = self.gate.run()
        self.assertEqual((review.call_count, audit.call_count, look.call_count), (0, 0, 0))
        self.assertEqual((out["look_waiting"], out["look_held"], out["looked"], out["refused"]), (["a"], [], [], []))
        figures = self.assert_waiting("a", n)
        power = figures["power"]
        self.assertEqual((power["sessions"], power["level"], power["looks_before"]), (holdout_sessions(), 0.05, 0))
        self.assertAlmostEqual(power["power"], evidence.holdout_power(THIN_SHARPE, holdout_sessions(), 0.05))
        self.assertLess(power["power"], 0.30)
        self.assertFalse(figures["drift"]["held"])
        # Judged again each round, and nothing more is written: no second event, no row, the state as it was.
        before = self.written()
        for _ in range(3):
            self.clock.advance(300)
            again = self.gate.run()
            self.assertEqual((again["look_waiting"], again["look_held"], again["looked"], again["refused"]), (["a"], [], [], []))
        self.assertEqual(self.written(), before)
        self.assert_waiting("a", n)

    def flat_and_todays_bar(self) -> tuple[float, float, float]:
        """(the flat bar, today's bar, today's level): the least Validation daily Sharpe that clears the power hold at
        0.05 and at the level the next look faces under Holm across the looks on record, by the code's own functions."""
        level = evidence.holm_level([x["p_value"] for x in self.store.looks()])
        line = look_hold_settings(self.settings)[1]
        return (scoreboard.sharpe_for_power(line, holdout_sessions(), evidence.HOLDOUT_ALPHA),
                scoreboard.sharpe_for_power(line, holdout_sessions(), level), level)

    def between_the_bars(self, fid: str = "a") -> int:
        """Three failed looks on record, and `fid`'s version validated with a Sharpe between the flat bar and today's."""
        self.bystanders("x", "y", "z")
        for i, (other, p) in enumerate((("x", 0.64), ("y", 0.71), ("z", 0.58))):
            self.store.add_look(other, 1, f"{i}" * 64, passed=False, p_value=p, detail={})
        flat, today, level = self.flat_and_todays_bar()
        self.assertEqual(level, 0.0125, "the fourth look's level under Holm")
        self.assertLess(flat, today)
        sharpe = round((flat + today) / 2.0, 4)
        self.assertTrue(flat < sharpe < today)
        return self.ready(fid, sharpe=sharpe)

    def test_between_the_flat_bar_and_todays_bar_it_waits_and_is_not_barred(self):
        n = self.between_the_bars()
        out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["look_held"], out["refused"], out["looked"]), (["a"], [], [], []))
        figures = self.assert_waiting("a", n)["power"]
        self.assertEqual((figures["level"], figures["looks_before"]), (0.0125, 3))
        self.assertLess(figures["power"], 0.30, "under today's bar")
        self.assertGreater(evidence.holdout_power(figures["sharpe_daily"], holdout_sessions(), 0.05), 0.30,
                           "and over the flat bar: a hold for good would have burned a version the next rule looks at")
        self.assertEqual(len(self.store.looks()), 3, "no look spent on it: the next look's level is as it was")

    def test_when_the_level_later_allows_it_it_gets_its_one_look(self):
        n = self.between_the_bars()
        self.gate.run()
        self.assert_waiting("a", n)
        self.clock.advance(300)
        # The level the hold reads rises to the whole 0.05 (as a changed rule would set it): the hold no longer fires.
        with patch.object(evidence, "holm_level", return_value=evidence.HOLDOUT_ALPHA):
            out = self.gate.run()
        self.assertEqual((out["looked"], out["look_waiting"], out["look_held"], out["refused"]),
                         ([{"family": "a", "passed": False}], [], [], []))
        self.assertEqual([(j.family, j.version) for j in self.holdout_jobs()], [("a", n)], "its one look")
        self.assertEqual(self.paid(), 2, "behind its review and its audit")
        state = self.store.family("a")["state"]
        self.assertEqual((state["gated_sha"], state["gate_outcome"]["result"], state["gate"]), (self.sha("a", n), "failed", "fail"))
        self.assertIsNone(waiting(state), "the gate is done with it")
        self.assertEqual(self.store.lineage_looks("a"), 1)
        self.assertEqual(len(self.wait_events("a")), 1, "one event: the first time it waited")
        self.assertEqual(self.store.look_holds(), [], "and never a hold row")
        for _ in range(2):  # one look a program: never a second
            with patch.object(evidence, "holm_level", return_value=evidence.HOLDOUT_ALPHA):
                again = self.gate.run()
            self.assertEqual((again["looked"], again["look_waiting"]), ([], []))
        self.assertEqual(len(self.holdout_jobs()), 1)

    def test_a_wait_that_ends_is_told_and_a_pass_is_a_candidate(self):
        """The wait over, the version is at the gate as any ready one: the researcher hears it, the review and the audit
        are paid, and a look that passes makes the family a Candidate in the same round."""
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_waiting("a", n)
        self.answer = lambda job: strong(job) if job.window == "holdout" else self.gym(job)
        told: list[str] = []
        tell = Gate.tell
        with patch.object(Gate, "tell", autospec=True, side_effect=lambda g, fid, answer, **kw: (told.append(answer),
                                                                                              tell(g, fid, answer, **kw))[1]):
            self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.01}  # the owner's setting moved
            out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": True}])
        self.assertEqual(told, [WAIT_OVER_WORDS, "pass"])
        self.assertEqual(self.store.family("a")["band"], "candidate")

    def test_a_validation_judged_again_readies_it_and_it_waits_again_with_no_second_event(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_waiting("a", n)
        # The tournament judges the same version again (a best submitted again, a result recorded): gate-ready again.
        tournament = Tournament(self.store, self.pool, self.settings)
        tournament.judge("a", n, tournament.recorded_validation("a", n), record=False)
        self.assertTrue(self.store.family("a")["state"]["gate_ready"])
        self.assertIsNone(waiting(self.store.family("a")["state"]), "ready: the round takes it up as any ready version")
        out = self.gate.run()
        self.assertEqual(out["look_waiting"], ["a"])
        self.assert_waiting("a", n)
        # Validated again and found short of the line, it holds no place: the gate takes nothing of it up.
        self.store.set_state("a", validation_line={**self.store.family("a")["state"]["validation_line"], "passed": False})
        self.assertIsNone(waiting(self.store.family("a")["state"]))
        out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["looked"], out["refused"], self.holdout_jobs()), ([], [], [], []))

    def test_a_wait_never_ends_on_a_validation_judged_again_and_failed_meanwhile(self):
        """The tournament's round runs beside the gate's. A waiting version it judges again and finds short of the line,
        after the gate's round read the family and before the wait would end, is not made ready: the wait's end is
        checked again under the store's lock."""
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_waiting("a", n)

        def judged_again(gate, fam, version):
            self.store.set_state("a", validation_line={"passed": False})  # the tournament's verdict, landing now
            return None  # and the hold would no longer fire

        with patch.object(Gate, "look_hold", autospec=True, side_effect=judged_again):
            out = self.gate.run()
        state = self.store.family("a")["state"]
        self.assertEqual((out["looked"], out["look_waiting"], self.paid(), self.holdout_jobs()), ([], [], 0, []))
        self.assertFalse(state["gate_ready"], "no place was made ready for a version that no longer meets the line")
        self.assertEqual(state["gate"], HOLD_WORDS[HOLD_POWER_STAGE], "and nothing new was told")

    def test_a_waiting_version_is_still_held_for_good_by_the_drift_hold(self):
        n = self.ready("a", drift=dict(alpha=80.0, drift=20.0, beta=200.0), sharpe=THIN_SHARPE)  # drift share 0.20
        self.gate.run()
        self.assert_waiting("a", n)
        self.settings["gate"]["look_holds"] = {"drift_share": 0.15, "min_power": 0.30}  # the owner tightens the drift line
        out = self.gate.run()
        self.assertEqual((out["look_held"], out["look_waiting"]), (["a"], []))
        self.assert_held("a", n, HOLD_DRIFT_STAGE)
        self.assertEqual(self.gate.run()["look_waiting"], [], "closed: it waits no more")

    def bystanders(self, *fids: str) -> None:
        """Families with no version: their looks count, and the tournament validates nothing of theirs."""
        for fid in fids:
            self.store.add_family({**SPEC, "id": fid}, origin="seed")

    def test_the_power_is_taken_at_the_level_the_next_look_must_reach_under_holm(self):
        sharpe = 0.12  # power ~0.49 at a first look, ~0.31 at a third, ~0.27 at a fourth
        self.bystanders("x", "y", "z")
        n = self.ready("a", sharpe=sharpe)
        self.assertIsNone(self.gate.look_hold(self.store.family("a"), n), "a first look")
        for i, (fid, p) in enumerate((("x", 0.64), ("y", 0.71))):
            self.store.add_look(fid, 1, f"{i}" * 64, passed=False, p_value=p, detail={})
        self.assertIsNone(self.gate.look_hold(self.store.family("a"), n), "a third look: level 0.05 / 3")
        self.store.set_state("z", look_inflight={"sha": "f" * 64, "n": 1, "at": self.clock()})
        hold = self.gate.look_hold(self.store.family("a"), n)
        self.assertEqual(hold["stage"], HOLD_POWER_STAGE, "a look in flight elsewhere counts as a failed one: 0.05 / 4")
        self.assertEqual((hold["figures"]["power"]["level"], hold["figures"]["power"]["inflight_elsewhere"]), (0.0125, 1))
        # Really in flight (`Gate.flying_elsewhere`): a marker a dead process left, or one whose look never came back, is
        # no look. A hold on it would close the version, and bar its program from the incubator, for a look no one made.
        for stale in (self.gate.started_at - 1.0, None, "not a time"):
            self.store.set_state("z", look_inflight={"sha": "f" * 64, "n": 1, **({"at": stale} if stale is not None else {})})
            self.assertEqual(len(self.store.looks_inflight()), 1)
            self.assertIsNone(self.gate.look_hold(self.store.family("a"), n), "a third look still: level 0.05 / 3")
        self.store.set_state("z", look_inflight=None)
        self.store.add_look("z", 1, "f" * 64, passed=False, p_value=0.58, detail={})
        self.gate.run()
        self.assert_waiting("a", n)

    def test_a_version_with_no_validation_sharpe_or_no_session_count_waits_fail_closed(self):
        n = self.ready("a", sharpe=None)
        self.gate.run()
        figures = self.assert_waiting("a", n)
        self.assertIsNone(figures["power"]["power"])
        n = self.ready("b", sharpe=STRONG_SHARPE)
        with patch("league.swarm.gate.holdout_sessions", return_value=None):
            out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["looked"]), (["a", "b"], []), "no figure, no look")
        figures = self.assert_waiting("b", n)
        self.assertIsNone(figures["power"]["sessions"])
        # The calendar answers again: b's wait is over and it gets its look (a hold would have closed it for good).
        out = self.gate.run()
        self.assertEqual((out["looked"], out["look_waiting"]), ([{"family": "b", "passed": False}], ["a"]))

    def test_both_holds_firing_record_the_drift_hold_with_both_named(self):
        n = self.ready("a", drift=HEAVY, sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_held("a", n, HOLD_DRIFT_STAGE)
        [event] = self.hold_events("a")
        self.assertEqual(event["payload"]["holds"], [HOLD_DRIFT_STAGE, HOLD_POWER_STAGE])

    def test_the_look_asks_again_under_the_lock(self):
        """A look that lands between the round's hold check and its own look lowers the power: no look starts."""
        sharpe = 0.12
        self.bystanders("x", "y", "z")
        n = self.ready("a", sharpe=sharpe)
        for i, (fid, p) in enumerate((("x", 0.64), ("y", 0.71), ("z", 0.58))):
            self.store.add_look(fid, 1, f"{i}" * 64, passed=False, p_value=p, detail={})
        fam = self.store.family("a")
        self.assertIsNone(self.gate.look(fam, self.store.version("a", n), self.sha("a", n)))
        self.assertEqual(self.holdout_jobs("a"), [])
        state = self.store.family("a")["state"]
        self.assertIsNone(state.get("look_inflight"))
        self.assertTrue(state["gate_ready"], "the next round makes it wait")
        self.gate.run()
        self.assert_waiting("a", n)


class TheWaitBlocksNothing(HoldCase):
    """A waiting version blocks neither its family's other work nor the gate's other families, and it is still refused
    by the checks that refuse."""

    def test_the_gates_other_families_are_looked_at_and_face_no_stricter_level_for_it(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.ready("b")
        out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["looked"]), (["a"], [{"family": "b", "passed": False}]))
        self.assert_waiting("a", n, paid=2)  # b's review and audit
        [look] = [e for e in self.store.events_after(0) if e["payload"].get("action") == "look"]
        self.assertEqual((look["family"], look["payload"]["_inflight_elsewhere"], look["payload"]["_line"]["numbers"]["looks_before"]),
                         ("b", 0, 0), "a wait is no look in flight: it raises no one's level")
        self.assertEqual(self.gate.flying_elsewhere("b"), [])
        self.assertEqual(self.store.lineage_looks("a", include_inflight=True), 0, "and reserves none of its lineage's rations")

    def test_its_family_researches_on_and_a_newer_version_takes_the_place(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        fam = self.store.family("a")
        row = allocation.row_of(fam, cls="x", looks_spent=False, gate_done=allocation.gate_spent(self.store, fam))
        self.assertEqual((row["gate"], row["gate_done"]), (False, False),
                         "not at the floor share of a family at the gate, and not discounted as one the gate is done with")
        self.assertFalse(fam["state"]["gate_ready"], "the idle rule and the retirement rules read it as any Gym family")
        # Its researcher writes a version the holdout can judge: validated, it takes the gate place and is looked at.
        newer = self.ready("a", sharpe=STRONG_SHARPE, version=2)
        state = self.store.family("a")["state"]
        self.assertEqual((state["validation_version"], state["gate_ready"], state[LOOK_WAIT]["n"]), (newer, True, n))
        self.assertIsNone(waiting(state), "the marker names the earlier version: it holds no place")
        out = self.gate.run()
        self.assertEqual((out["looked"], out["look_waiting"]), ([{"family": "a", "passed": False}], []))
        self.assertEqual([(j.family, j.version) for j in self.holdout_jobs()], [("a", newer)])
        self.assertEqual(len(self.wait_events("a")), 1)

    def test_a_retired_family_waits_no_more(self):
        self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.store.retire("a", "a test retirement of this family")
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.01}  # the hold would no longer fire
        out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["looked"], self.holdout_jobs(), self.paid()), ([], [], [], 0))

    def twin(self, fid: str, of: str = "a") -> str:
        """Another family holding `of`'s program (the same code and parameters: the same run sha)."""
        self.store.add_family({**SPEC, "id": fid}, origin="seed")
        v = self.store.add_version(fid, self.store.version(of, 1)["code"], {}, author="seed")
        self.assertEqual(self.sha(fid, v["n"]), self.sha(of, 1))
        return self.sha(fid, v["n"])

    def test_a_waiting_version_is_still_refused_by_the_program_bar(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_waiting("a", n)
        self.twin("b")
        self.store.refuse("b", 1, "audit", "a verdict on the same program, made in another family")
        out = self.gate.run()
        self.assertEqual((out["refused"], out["look_waiting"], out["looked"]), (["a"], [], []))
        self.assertEqual([(r["stage"], r["version"]) for r in self.store.refusals("a")], [(PROGRAM_BAR_STAGE, n)])
        state = self.store.family("a")["state"]
        self.assertEqual((state["gated_sha"], state["gate_outcome"]["result"]), (self.sha("a", n), "refused"))
        self.assertIsNone(waiting(state))
        self.assertEqual(self.gate.run()["look_waiting"], [])

    def test_a_waiting_version_is_still_refused_by_the_duplicate_rule(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_waiting("a", n)
        sha = self.twin("b")
        self.store.add_look("b", 1, sha, passed=False, p_value=0.9, detail={})  # the same program was looked at elsewhere
        out = self.gate.run()
        self.assertEqual((out["refused"], out["look_waiting"], out["looked"]), (["a"], [], []))
        self.assertEqual([r["stage"] for r in self.store.refusals("a")], [DUPLICATE_STAGE])
        self.assertIsNone(waiting(self.store.family("a")["state"]))

    def test_a_waiting_version_is_still_refused_by_the_rations(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.assert_waiting("a", n)
        for i in range(3):  # the lineage's three looks are spent meanwhile
            self.store.add_look("a", 10 + i, f"{i}" * 64, passed=False, p_value=0.9, detail={})
        out = self.gate.run()
        self.assertEqual((out["refused"], out["look_waiting"]), (["a"], []))
        self.assertEqual([(r["stage"], r["version"]) for r in self.store.refusals("a")], [("rations", n)])
        self.assertIsNone(waiting(self.store.family("a")["state"]))

    def test_the_operators_hold_stops_a_waiting_version_too(self):
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        self.store.hold_gate("a", reason="a test hold")
        with patch.object(evidence, "holm_level", return_value=evidence.HOLDOUT_ALPHA):
            self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.01}
            out = self.gate.run()
            self.assertEqual((out["held"], out["looked"], out["look_waiting"]), (["a"], [], []))
            self.store.hold_gate("a", hold=False)
            out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual([(j.family, j.version) for j in self.holdout_jobs()], [("a", n)])

    def test_the_marker_alone_is_no_place(self):
        """`waiting` reads the family's state as it stands: a marker that outlived its wait names no place."""
        n = self.ready("a", sharpe=THIN_SHARPE)
        self.gate.run()
        state = self.store.family("a")["state"]
        marker = state[LOOK_WAIT]
        self.assertEqual(waiting(state), marker)
        for change in ({"gate_ready": True}, {"gated_sha": marker["sha"]}, {"look_inflight": {"sha": marker["sha"]}},
                       {"validation_version": n + 1}, {"validation_version": None}, {"validation_line": None},
                       {"validation_line": {"passed": False}}, {"validation_line": "passed"},
                       {LOOK_WAIT: None}, {LOOK_WAIT: "x"}, {LOOK_WAIT: {"n": n}}, {LOOK_WAIT: {"sha": "", "n": n}},
                       {LOOK_WAIT: {"sha": 7, "n": n}}, {LOOK_WAIT: {"sha": marker["sha"], "n": True}}):
            self.assertIsNone(waiting({**state, **change}), change)
        for unread in (None, "x", [], 3):
            self.assertIsNone(waiting(unread))


class TheOrder(HoldCase):
    """A hold never takes a refusal's place: the checks that refuse (and spend no look) come first."""

    def test_a_duplicate_is_refused_as_a_duplicate_not_held(self):
        self.ready("a")
        self.store.add_family({**SPEC, "id": "b"}, origin="seed")  # the same code and params: the same program
        v = self.store.add_version("b", self.store.version("a", 1)["code"], {}, author="seed")
        self.store.update_family("b", best_version=v["n"])
        self.assertEqual(self.sha("b", 1), self.sha("a", 1))
        self.ready("b", drift=HEAVY, sharpe=THIN_SHARPE)  # both at the gate before a's look; b's figures would be held
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual((out["refused"], out["look_held"]), (["b"], []))
        self.assertEqual([r["stage"] for r in self.store.refusals("b")], [DUPLICATE_STAGE])
        self.assertEqual(self.store.look_holds("b"), [])

    def test_the_drift_screen_and_the_rations_refuse_before_the_holds(self):
        self.ready("a", drift=HEAVY, sharpe=THIN_SHARPE)
        # Its Train alpha fails the drift screen (the gate's own check, in depth: the tournament validates none of these).
        with patch("league.swarm.gate.drift_verdict", return_value={"passed": False, "known": True, "why": "t below"}):
            out = self.gate.run()
        self.assertEqual((out["refused"], out["look_held"]), (["a"], []))
        self.assertEqual([r["stage"] for r in self.store.refusals("a")], ["drift screen"])
        n = self.ready("b", drift=HEAVY, sharpe=THIN_SHARPE)
        for i in range(3):  # the lineage's three looks are spent
            self.store.add_look("b", 10 + i, f"{i}" * 64, passed=False, p_value=0.9, detail={})
        out = self.gate.run()
        self.assertEqual((out["refused"], out["look_held"]), (["b"], []))
        self.assertEqual([(r["stage"], r["version"]) for r in self.store.refusals("b")], [("rations", n)])
        self.assertEqual(self.store.look_holds(), [])


class TheTuition(RetiredTuition, HoldCase):
    """B1 (reviews A1 and B1 of PR #484): a hold can land after the gate's review and audit passed, while the version waits
    (for the gate image here). Execution tuition (`bands.read`: 1-lot real orders) ran a reviewed version while it waited.
    Its look then came, and a failed one ended the tuition; a held version gets no look, so the hold
    itself must end it, and does ("held" is one of `bands.BAD_OUTCOMES`), for good. A version that WAITS for the look's
    bar (the power hold, release F1) is not held and has no outcome: `bands.read` gives it no row while it waits
    (`gate.waiting`), so the tightening stands with nothing closed, and its look, when it comes, ends the tuition as
    any look does. Tuition is retired as shipped (`bands.TUITION_ROWS` False): this class switches its rows on
    (`RetiredTuition`), so the rule that a hold or a wait sends no real order stays pinned for the retired route's
    read."""

    def setUp(self):
        super().setUp()
        from league.gym.driver import build_bundle

        bundle = build_bundle()[1]
        image = "sbcp_synthetic_gym"
        self.pool.image = lambda kind="gym": image
        self.pool.bundle = lambda: bundle
        gym = self.gym
        self.answer = lambda job: {**gym(job), "gym_image": image, "gym_bundle": bundle}
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": image}}))
        self.bystanders = ("x", "y", "z")
        for fid in self.bystanders:
            self.store.add_family({**SPEC, "id": fid}, origin="seed")

    def tuition(self) -> list[str]:
        return [r["family"] for r in bands.read(self.root)]

    def reviewed_and_waiting(self, **kw) -> int:
        """`a` validated, its review and audit passed, waiting for the gate image: a tuition row, as today."""
        n = self.ready("a", **kw)
        self.settings["gym"]["gate_checkpoint"] = None
        self.replies = [PASS, PASS]
        out = self.gate.run()
        self.assertEqual(out["waiting"], ["a"])
        review = self.store.family("a")["state"]["review"]
        self.assertEqual((review["verdict"], review["audit"]["verdict"]), ("pass", "pass"))
        self.assertEqual(self.tuition(), ["a"], "reviewed and waiting: execution tuition runs it (as today)")
        self.settings["gym"]["gate_checkpoint"] = "sbcp_gate"  # the image is ready
        return n

    def looks_land_elsewhere(self) -> None:
        """Three failed looks in other families: the next look faces 0.05 / 4."""
        for i, (fid, p) in enumerate(zip(self.bystanders, (0.64, 0.71, 0.58))):
            self.store.add_look(fid, 1, f"{i}" * 64, passed=False, p_value=p, detail={})

    def test_a_power_wait_after_a_passed_review_sends_no_real_order_while_it_waits(self):
        n = self.reviewed_and_waiting(sharpe=0.12)  # power about 0.49 at a first look: no wait at its review
        self.looks_land_elsewhere()  # about 0.27 at a fourth
        out = self.gate.run()
        self.assertEqual((out["look_waiting"], out["look_held"], out["looked"]), (["a"], [], []))
        self.assertEqual(self.tuition(), [], "no tuition row while it waits, as a failed look would leave none")
        self.assert_waiting("a", n, paid=2, reviewed=True)
        for _ in range(3):
            self.gate.run()
        self.assertEqual(self.tuition(), [], "rounds later: still none")
        self.assertEqual(self.holdout_jobs(), [], "and no look was made")
        # The level allows it again: its one look is made on the review it already paid for, and its verdict ends it.
        with patch.object(evidence, "holm_level", return_value=evidence.HOLDOUT_ALPHA):
            out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual((self.paid(), len(self.holdout_jobs("a")), self.tuition()), (2, 1, []))

    def test_a_wait_found_by_the_looks_recheck_under_the_lock_sends_no_real_order_from_the_next_round(self):
        n = self.reviewed_and_waiting(sharpe=0.12)
        self.looks_land_elsewhere()
        fam = self.store.family("a")
        self.assertIsNone(self.gate.look(fam, self.store.version("a", n), self.sha("a", n)), "no look starts")
        self.assertEqual(self.tuition(), ["a"], "gate_ready kept: the next round records the wait")
        self.gate.run()
        self.assertEqual(self.tuition(), [])
        self.assert_waiting("a", n, paid=2, reviewed=True)

    def test_a_version_reviewed_before_the_holds_are_switched_on_is_held_and_its_tuition_ends(self):
        self.settings["gate"]["look_holds"] = None  # before the deploy
        n = self.reviewed_and_waiting(drift=HEAVY)
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30}  # the deploy
        out = self.gate.run()
        self.assertEqual(out["look_held"], ["a"])
        self.assertEqual(self.tuition(), [])
        self.assert_held("a", n, HOLD_DRIFT_STAGE, paid=2, reviewed=True)

    def test_todays_gate_looks_fails_and_ends_the_tuition(self):
        """The control (holds off): the same version is looked at, the look fails, and the tuition ends; with the holds the
        tuition ends the same way, with no look spent."""
        self.settings["gate"]["look_holds"] = None
        self.reviewed_and_waiting(sharpe=0.12)
        self.looks_land_elsewhere()
        out = self.gate.run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assertEqual(self.store.family("a")["state"]["gate_outcome"]["result"], "failed")
        self.assertEqual(self.tuition(), [])

    def test_the_tuition_and_the_incubator_read_one_list_of_outcomes(self):
        self.assertIs(incubator.BAD_OUTCOMES, bands.BAD_OUTCOMES)
        self.assertEqual(set(bands.BAD_OUTCOMES), {"refused", "failed", "demoted", HOLD_OUTCOME})
        self.assertEqual(program_refusal({"gate_outcome": {"sha": "s", "result": HOLD_OUTCOME}}, "s"),
                         "the gate's outcome for it is held")
        self.assertIsNone(program_refusal({"gate_outcome": {"sha": "other", "result": HOLD_OUTCOME}}, "s"))


#: A long-delta Train fit (beta 200 in every row) with drift share 60 / 160 = 0.375 and t 2: it passes the drift screen.
HEAVY_PASSING = drift_block(t=2.0, alpha_usd=100.0, drift_usd=60.0)


class TheIncubator(GateCase):
    """B2 (review A1 of PR #484): a held program never trades the incubator. Today a failed look bars its program from the
    incubator for good; a hold, which replaces that look, bars it too, first, so the same round's incubator pays no review
    for it and the House's incubator reader refuses it. The program: marked for the incubator (Train and drift passed,
    practised positive), long-delta and drift-heavy, at the gate with its Validation figures."""

    def at_gate(self, *, holds: bool, drift: dict = HEAVY_PASSING, sharpe: float = 0.25) -> tuple[int, str]:
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": 0.30} if holds else None
        n = self.family("a")
        self.train("a", n, drift=drift)
        self.robust("a", n)
        self.cohort("a", n)
        self.practised("a", n, [(SESSIONS[i % 2], 3.0, False) for i in range(5)], days=SESSIONS[:2])
        incubator.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertIn(str(n), self.state("a")["train_passed"], "marked for the incubator")
        # (the default Sharpe: power well above the line, so the drift hold only)
        self.store.set_state("a", gate_ready=True, validation_version=n, validation_image=None, validation_bundle=None,
                             validation_line={"passed": True}, validation_numbers={"sharpe_daily": sharpe})
        self.answer = lambda job: weak(job) if job.window == "holdout" else strong(job)  # a look fails
        return n, run_sha(self.store.version("a", n))

    def assert_barred(self, n: int, sha: str) -> None:
        self.assertIn(sha, self.state("a")["incubator_barred"])
        self.assertNotIn(str(n), self.state("a").get("train_passed") or {}, "its mark is gone")
        self.assertFalse(accepts(self.state("a"), n, sha, self.kv()))
        self.assertEqual(live_rows(self.root, "a", n), [], "the House's incubator reader refuses it")
        self.assertEqual(incubator.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])

    def test_a_held_program_is_barred_from_the_incubator_and_no_incubator_review_is_paid(self):
        n, sha = self.at_gate(holds=True)
        self.replies = [PASS, PASS]  # what an incubator review and audit would answer, were they asked
        out = self.gate().run()
        self.assertEqual(out["look_held"], ["a"])
        self.assertEqual((out.get("incubator") or {}).get("reviewed", []), [], "the incubator reviews no held program")
        self.assertEqual(len(self.sail.bodies) + len(self.asked), 0, "nothing paid at all")
        self.assertEqual(self.state("a")["incubator_barred"][sha]["why"],
                         f"the gate held its holdout look ({HOLD_DRIFT_STAGE})")
        self.assert_barred(n, sha)
        self.gate().run()
        self.assert_barred(n, sha)

    def test_a_waiting_program_is_not_barred_and_no_incubator_review_is_paid_while_the_gate_holds_its_place(self):
        """THE POWER HOLD IS A WAIT: no bar, so its mark stays and its cohort is not ended for it; and while the gate
        holds its place the incubator pays no review of its own (the gate's review and audit serve when its look can
        be made), and the House's incubator reader gives a family whose validated version met the line no row."""
        light = drift_block(t=2.0, alpha_usd=150.0, drift_usd=20.0)  # long-delta, drift share 60 / 510: under the line
        n, sha = self.at_gate(holds=True, drift=light, sharpe=0.05)
        self.replies = [PASS, PASS]  # what an incubator review and audit would answer, were they asked
        out = self.gate().run()
        self.assertEqual((out["look_waiting"], out["look_held"]), (["a"], []))
        self.assertEqual((out.get("incubator") or {}).get("reviewed", []), [])
        self.assertEqual(len(self.sail.bodies) + len(self.asked), 0, "nothing paid at all")
        state = self.state("a")
        self.assertEqual(waiting(state)["sha"], sha)
        self.assertNotIn(sha, state.get("incubator_barred") or {}, "a wait is no bar")
        self.assertIn(str(n), state["train_passed"], "its mark stands")
        self.assertIsNone(incubator.gate_bar(self.store, self.store.family("a"), n, sha=sha))
        self.assertEqual(incubator.due_reviews(self.store, self.settings, self.root, clock=self.clock), [],
                         "the gate holds its place: its own review and audit serve")
        self.assertFalse(incubator.reviewable(self.store, "a", n, sha))
        self.assertEqual(live_rows(self.root, "a", n), [], "no real order while it waits")
        self.gate().run()
        self.assertEqual(len(self.sail.bodies) + len(self.asked), 0)
        # The control: the same version with no place at the gate (never ready, not waiting) is due an incubator review.
        self.store.set_state("a", look_wait=None)
        self.assertEqual([r["version"] for r in incubator.due_reviews(self.store, self.settings, self.root, clock=self.clock)], [n])

    def test_todays_gate_bars_the_same_program_after_its_failed_look(self):
        """The control (holds off): reviewed, audited, looked at, failed, barred. The hold bars it the same, with no look
        spent and no review paid."""
        n, sha = self.at_gate(holds=False)
        self.replies = [PASS, PASS]  # the gate's review and audit
        out = self.gate().run()
        self.assertEqual(out["looked"], [{"family": "a", "passed": False}])
        self.assert_barred(n, sha)


class TheSettings(HoldCase):
    def test_null_restores_todays_gate(self):
        self.settings["gate"]["look_holds"] = None
        self.ready("a", drift=None, sharpe=None)  # every figure missing: both holds would fire
        with patch("league.swarm.gate.version_drift", side_effect=AssertionError("no figure is read")):
            out = self.gate.run()
        self.assertEqual((out["looked"], out["look_held"]), ([{"family": "a", "passed": False}], []))
        self.assertEqual(len(self.holdout_jobs("a")), 1)
        self.assertEqual(self.paid(), 2, "the review and the audit, as today")
        self.assertEqual((self.store.look_holds(), self.hold_events()), ([], []))
        self.assertEqual(self.store.family("a")["state"]["gate_outcome"]["result"], "failed")

    def test_each_hold_is_its_own_switch(self):
        self.settings["gate"]["look_holds"] = {"drift_share": None, "min_power": 0.30}
        self.ready("a", drift=HEAVY)
        self.assertEqual(self.gate.run()["looked"], [{"family": "a", "passed": False}], "the drift hold is off")
        n = self.ready("b", drift=HEAVY, sharpe=THIN_SHARPE)
        self.assertEqual(self.gate.run()["look_waiting"], ["b"], "the power hold is on, and it is a wait")
        self.assertEqual((self.store.look_holds("b"), waiting(self.store.family("b")["state"])["stage"]), ([], HOLD_POWER_STAGE))
        self.assertEqual(self.holdout_jobs("b"), [])
        del n
        self.settings["gate"]["look_holds"] = {"drift_share": 0.25, "min_power": None}
        self.ready("c", sharpe=THIN_SHARPE)
        self.assertEqual(self.gate.run()["looked"], [{"family": "c", "passed": False}], "the power hold is off")

    def test_the_settings_are_read_as_a_brake(self):
        self.assertEqual(look_hold_settings({}), (0.25, 0.30))
        self.assertEqual(look_hold_settings({"gate": {}}), (0.25, 0.30))
        self.assertEqual(look_hold_settings({"gate": {"look_holds": None}}), (None, None))
        self.assertEqual(look_hold_settings({"gate": {"look_holds": {"drift_share": None}}}), (None, 0.30))
        self.assertEqual(look_hold_settings({"gate": {"look_holds": {"min_power": 0.5}}}), (0.25, 0.5))
        for bad in (False, "off", 0, [], {"drift_share": "0.1", "min_power": 2}, {"drift_share": True, "min_power": -1},
                    {"drift_share": float("nan")}):
            self.assertEqual(look_hold_settings({"gate": {"look_holds": bad}}), (0.25, 0.30), bad)


class NoFigures(HoldCase):
    def test_the_researcher_reads_no_figure_of_a_hold_or_a_wait(self):
        sharpe = 0.0371937  # a distinctive Validation Sharpe; power about 0.13
        n = self.ready("a", sharpe=sharpe)
        self.gate.run()
        figures = self.assert_waiting("a", n)
        self.ready("b", drift=dict(alpha=113.71, drift=87.29, beta=413.77))
        self.gate.run()
        drift = self.assert_held("b", 1, HOLD_DRIFT_STAGE)["drift"]
        for words in (*HOLD_WORDS.values(), WAIT_OVER_WORDS):
            self.assertIsNone(re.search(r"\d", words), "the hold's and the wait's words carry no figure")
        sealed = [sharpe, figures["power"]["power"], figures["power"]["level"], drift["share"]]
        forms = {f for value in sealed for f in printed_forms(value, whole=False) if sum(c.isdigit() for c in f) >= 4}
        researcher = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False)
        for fid, stage in (("a", HOLD_POWER_STAGE), ("b", HOLD_DRIFT_STAGE)):
            fam = self.store.family(fid)
            status = researcher.status(fam)
            self.assertIn(HOLD_WORDS[stage], status)
            rows = [("hold row", row["reason"]) for row in self.store.look_holds(fid)]
            self.assertEqual(len(rows), int(fid == "b"), "a wait writes no row")
            for where, text in (("status", status), ("brief", researcher.brief(fam)), ("gate", fam["state"]["gate"]), *rows):
                leaked = [f for f in forms if re.search(rf"(?<!\d){re.escape(f)}(?!\d)", text)]
                self.assertEqual(leaked, [], f"{fid} {where} shows a hold's figure")


class TheFigures(unittest.TestCase):
    def test_the_drift_lean_is_the_pooled_fit_over_the_years_the_screen_counts(self):
        block = evidence.drift_numbers(lean(**HEAVY))
        lean_ = evidence.drift_lean(block, first_year=2022)
        self.assertEqual((lean_["known"], lean_["long_delta"], lean_["years"]), (True, True, 3))
        self.assertAlmostEqual(lean_["share"], 180.0 / 480.0)
        # A year the screen leaves out (before the running span) is left out here too, and the rest pooled again.
        block = lean(**NEUTRAL)
        block["years"]["2021"] = {**block["years"]["2022"], "alpha_usd": 0.0, "drift_usd": 900.0, "beta": 900.0}
        block["pooled"].update(alpha_usd=450.0, drift_usd=960.0, beta=500.0)
        out = evidence.drift_lean(evidence.drift_numbers(block), first_year=2022)
        self.assertEqual(out["years"], 3)
        self.assertAlmostEqual(out["share"], 60.0 / 510.0)
        self.assertAlmostEqual(out["beta"], 200.0)
        whole = evidence.drift_lean(evidence.drift_numbers(block))
        self.assertAlmostEqual(whole["share"], 960.0 / 1410.0, msg="no span: the pooled line as the Gym wrote it")
        self.assertFalse(evidence.drift_lean(None)["known"])
        self.assertFalse(evidence.drift_lean({"years": {}, "pooled": {"alpha_usd": 1.0}})["known"])

    def test_the_holm_level_is_the_gates_own_rule(self):
        self.assertEqual(evidence.holm_level([]), 0.05)
        self.assertEqual(evidence.holm_level([0.47, 0.62, 0.71]), 0.0125)
        self.assertAlmostEqual(evidence.holm_level([0.9] * 9), 0.005)
        # An earlier look that rejected lowers no bar: the next faces its rank's level.
        self.assertAlmostEqual(evidence.holm_level([0.001, 0.9]), 0.025)
        for previous in ([], [0.5], [0.2, 0.7], [0.001, 0.9], [0.01, 0.02, 0.9]):
            level = evidence.holm_level(previous)
            self.assertTrue(evidence.holm_passes(level, previous)[0])
            self.assertFalse(evidence.holm_passes(level * 1.0001, previous)[0])

    def test_the_power_is_the_normal_approximation_of_the_one_sided_test(self):
        # Phi(0.2 sqrt(100) - z(0.95)) = Phi(0.355); Phi(0.3 sqrt(120) - z(0.99)) = Phi(0.960).
        self.assertAlmostEqual(evidence.holdout_power(0.2, 100, 0.05), 0.6388, places=4)
        self.assertAlmostEqual(evidence.holdout_power(0.3, 120, 0.01), 0.8315, places=4)
        self.assertAlmostEqual(evidence.holdout_power(0.0, 120, 0.05), 0.05)
        self.assertLess(evidence.holdout_power(0.2, 100, 0.005), evidence.holdout_power(0.2, 100, 0.05))
        for bad in ((None, 120, 0.05), (0.1, 1, 0.05), (0.1, None, 0.05), (0.1, 120, 0.0), (0.1, 120, 1.0),
                    (float("nan"), 120, 0.05), (True, 120, 0.05)):
            self.assertIsNone(evidence.holdout_power(*bad), bad)

    def test_the_holdout_has_its_sessions(self):
        self.assertEqual(holdout_sessions(), sessions_between("2026-01-02", "2026-09-25"))
        self.assertEqual(sessions_between("2026-01-02", "2026-01-09"), 6)
        self.assertEqual(sessions_between("2026-04-03", "2026-04-03"), None, "Good Friday: no session")
        self.assertIsNone(sessions_between("2026-01-02", "not a day"))
        self.assertTrue(150 < holdout_sessions() < 200)

    def test_a_calendar_that_failed_once_is_asked_again(self):
        """A failure is never kept for the process (each hold is for good); a count is."""
        first, last = "2026-02-02", "2026-02-06"
        with patch("ltcm.data.us_equity_session", side_effect=OSError("the calendar is away")):
            self.assertIsNone(sessions_between(first, last))
        self.assertEqual(sessions_between(first, last), 5)


if __name__ == "__main__":
    unittest.main()
