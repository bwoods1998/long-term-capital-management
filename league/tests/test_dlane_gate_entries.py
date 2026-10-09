"""A DIRECTION VERDICT SAYS HOW IT WAS SCREENED (Oct 10, 2026; the readiness audit's M5). Under D2 a direction version
that misses the Validation line still goes to the gate when D2's pre-check passes, but the tournament's verdict said
only `passed` (the line), so every count read the entry as a failed Validation: eqp-realcalm-drift-call reached Probe
with `validation_verdicts` {"17": passed false}; the daily funnel (league/ops/funnel.py) and the dlane report's lane
funnel showed 0 direction passes; A3's gate-wait leg could never fire for the lane. The verdict row and the version's
record now carry `entered` and the lane's `screen`; the funnels count them; A3 reads them (and the lineage's try).
`passed` keeps meaning the line, and an alpha verdict is the record it always was. Every figure is invented."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.ops import dlane_report as R
from league.ops import funnel as FN
from league.ops import scoreboard as SB
from league.swarm import dlane
from league.swarm import settings as S
from league.swarm.store import SwarmStore, iso
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_dlane_d1b import committed_policy
from league.tests.test_dlane_report import GATE, Fixture as ReportFixture
from league.tests.test_swarm_rounds import RoundCase, strong

D2 = {"mode": "gate", "screen": "D2", "structures": ["long_single"]}


def precheck_only(job):
    """A Validation that misses the line and passes D2's pre-check (the review's own fixture, test_dlane_d1b)."""
    return result(job.name, window=job.window, t=0.5, mean=0.01, quarters="1/4")


class TheVerdictRow(RoundCase):
    def setUp(self):
        super().setUp()
        self.settings["dlane"] = dict(D2)
        self.settings["researcher"]["extension_hold_checks"] = 0

    def validate(self):
        with mock.patch.object(S, "read_policy", committed_policy):
            return Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))

    def test_a_d2_entry_is_recorded_as_entered_and_the_alpha_record_is_as_before(self):
        self.answer = lambda job: precheck_only(job) if job.family == "d" else strong(job)
        self.family("d", lane="direction")
        self.family("a")
        judged = self.validate()["judged"]
        self.assertEqual((judged["d"]["passed"], judged["d"]["entered"], judged["d"]["screen"]), (False, True, "D2"))
        state = self.store.family("d")["state"]
        self.assertTrue(state["gate_ready"], "it went to the gate")
        self.assertFalse(state["validation_line"]["passed"], "the line is as judged: tuition reads it")
        self.assertEqual({k: state["validation_verdicts"]["1"][k] for k in ("passed", "entered", "screen")},
                         {"passed": False, "entered": True, "screen": "D2"})
        # The alpha lane's verdict row and record: exactly the keys they always had.
        self.assertEqual(set(judged["a"]), {"version", "passed", "mean", "t"})
        self.assertTrue(judged["a"]["passed"])
        self.assertEqual(set(self.store.family("a")["state"]["validation_verdicts"]["1"]), {"passed", "at", "evaluator"})

    def test_a_direction_version_that_missed_both_is_recorded_as_not_entered(self):
        self.answer = lambda job: result(job.name, window=job.window, t=-0.5, mean=-0.01, quarters="1/4")
        self.family("d", lane="direction")
        row = self.validate()["judged"]["d"]
        self.assertEqual((row["passed"], row["entered"], row["screen"]), (False, False, "D2"))
        self.assertFalse(self.store.family("d")["state"].get("gate_ready"))

    def test_the_rollback_and_s_c_say_so(self):
        self.answer = strong
        self.settings["dlane"] = {"mode": "gate", "screen": "S-C"}
        self.family("d", lane="direction")
        row = self.validate()["judged"]["d"]
        self.assertEqual((row["passed"], row["entered"], row["screen"]), (True, True, "S-C"))
        self.settings["dlane"] = {"mode": "off"}
        self.family("e", lane="direction")
        row = self.validate()["judged"]["e"]
        self.assertEqual(set(row), {"version", "passed", "mean", "t"}, "the lane off: the record before the lane")
        self.assertEqual(set(self.store.family("e")["state"]["validation_verdicts"]["1"]), {"passed", "at", "evaluator"})


NOW = 1_791_000_000.0


class TheDailyFunnel(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = SwarmStore(self.root, clock=lambda: NOW - 3600.0)
        self.addCleanup(self.store.close)

    def round(self, judged):
        self.store.event("swarm.tournament", None, {"validation": {"judged": judged}})

    def page(self):
        funnel = FN.read(self.root, self.root, "r9", NOW)
        return SB.build(day="2026-10-10", release="r9", economics=None, deploys={}, budget=None,
                        ladder={"entrants": "n/a", "in_practice": "n/a", "promoted": "n/a", "bh_family_size": "n/a"},
                        jobs={"ok": 1}, written_at="23:30Z", funnel=funnel, stalls={"causes": {}})

    def test_a_d2_entry_counts_as_entered_split_by_screen_and_passed_stays_the_line(self):
        self.round({"a": {"passed": True, "version": 1}, "b": {"passed": False, "version": 1}})
        self.round({"d": {"passed": False, "entered": True, "screen": "D2"},
                    "e": {"passed": False, "entered": False, "screen": "D2"},
                    "f": {"passed": True, "entered": True, "screen": "S-C"}})
        day = FN.window(self.root, NOW - 86400.0, NOW)
        self.assertEqual(day["validations"], {"judged": 5, "passed": 2, "entered": 3, "by_screen": {
            "D2": {"judged": 2, "passed": 0, "entered": 1}, "S-C": {"judged": 1, "passed": 1, "entered": 1}}})
        text = self.page()
        self.assertIn("| Validations judged (passed) | 5 (2) | n/a |", text)
        self.assertIn("| Validations sent to the gate (the line, or D2's pre-check) | 3 | n/a |", text)
        self.assertEqual(SB.public_problems(text), [])

    def test_with_no_pre_check_entry_the_page_is_as_before(self):
        self.round({"a": {"passed": True}, "b": {"passed": False}})
        self.assertEqual(FN.window(self.root, NOW - 86400.0, NOW)["validations"],
                         {"judged": 2, "passed": 1, "entered": 1, "by_screen": {}})
        self.assertNotIn("sent to the gate", self.page())


class TheReport(ReportFixture):
    def alarms(self):
        out = R.alarms(self.store, GATE, R.Lanes(self.store), {"positions": [], "instances": []}, [],
                       {"basis_in_force": "gross", "room_gross_units": 3.0},
                       {"all": {"checkpoints": []}, "screen": {"checkpoints": []}}, {"tripped": False},
                       {"cap_usd": 128.9}, None, now=self.now, today="2026-10-20")
        return {a["id"]: a for a in out}

    def test_the_lane_funnel_counts_a_direction_entry_and_the_alpha_lane_is_as_before(self):
        self.fam("dir-a", lane="direction")
        self.fam("alp-b")
        self.store.event("swarm.tournament", None, {"validation": {"judged": {
            "dir-a": {"passed": False, "entered": True, "screen": "D2"}, "alp-b": {"passed": True}}}})
        out = R.funnel(self.store, R.Lanes(self.store), [], now=self.now, hours=24.0)
        self.assertEqual(out["direction"]["validations"], {"judged": 1, "passed": 0, "entered": 1})
        self.assertEqual(out["alpha"]["validations"], {"judged": 1, "passed": 1})

    def test_a3_counts_an_entry_waiting_for_its_look_and_never_a_refused_one(self):
        old = iso(self.now - 13 * 3600)
        self.fam("dir-v", lane="direction", validation_verdicts={"3": {"passed": False, "entered": True, "at": old}})
        # A D2 entry recorded before this release: its verdict says passed false, its lineage's try says entered.
        self.fam("dir-t", lane="direction", validation_verdicts={"17": {"passed": False, "at": old}},
                 **{dlane.TRY_KEY: {"version": 17, "at": old, "first": True, "entered": True}})
        # Entered and refused at the review (dir-qqq-ivlow-3d-call v38, 20:23Z Oct 9): it waits for nothing.
        self.fam("dir-r", lane="direction", validation_verdicts={"38": {"passed": False, "entered": True, "at": old}})
        self.store.refuse("dir-r", 38, "review", "the reviewer could not reach a verdict three times")
        # Entered 2 hours ago: not yet a wait.
        self.fam("dir-n", lane="direction", validation_verdicts={"1": {"passed": False, "entered": True,
                                                                        "at": iso(self.now - 2 * 3600)}})
        self.assertEqual(self.alarms()["A3"]["gate"], ["dir-t", "dir-v"])
        self.store.add_look("dir-v", 3, "sha-3", passed=False, p_value=0.5, detail={})
        self.assertEqual(self.alarms()["A3"]["gate"], ["dir-t"])
        self.assertIn("entered the gate", self.alarms()["A3"]["text"])


if __name__ == "__main__":
    unittest.main()
