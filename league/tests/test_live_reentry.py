"""THE RE-ENTRY RULE and THE COHORT'S OWN RECORD (`league/live/observe.py`, evidence v3). A program practises again, as
a new cohort and a new entrant, only when a release interrupted its cohort; an ended cohort is read by its recorded
ending and never by its evaluator (a rollback to the release before the ladder, then this release again, starts the
interrupted programs and no finished window); each cohort is its own entrant, whatever evaluator comes back; and a
cohort's record is its own accounts' alone, from its own first day, in every read of it: the ladder's, the incubator's
and the swarm's two (the summary's program statistics hold the account bar)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import unittest
from unittest.mock import patch

from league.live import ladder as L
from league.live import observe as O
from league.live.observe import ObserveStore, practice_record, practice_summary
from league.tests.test_live_ladder import (BEFORE_CHECKPOINTS, EVALUATOR, HAVE, NightCase, StoreCase, pattern, rules,
                                           sessions)

E2 = "bundle-2:fills-1:exec-2"
E3 = "bundle-3:fills-1:exec-3"
#: What the release before the ladder writes on every active cohort of another evaluator, byte for byte (its
#: `cohort_candidates`): held here as text, so a change of the constant that reads it fails.
BEFORE = "evaluator changed; a new version needs fresh practice"
FIRST = "2026-10-05"


class ReEntryCase(StoreCase):
    def offered(self, day: str, fid: str = "fam") -> list[str]:
        """The families the first pins of `day` offer to be frozen (never one still in its slot)."""
        return [r["family"] for r in self.store.cohort_candidates([self.program(fid)], day=day, in_session=True)
                if not r.get("practice_frozen")]

    def again(self, day: str, fid: str = "fam") -> dict:
        """The program frozen again on `day`: it must be offered."""
        [row] = [r for r in self.store.cohort_candidates([self.program(fid)], day=day, in_session=True)
                 if not r.get("practice_frozen")]
        return self.store.freeze(row, day=day)

    def row(self, fid: str = "fam") -> tuple:
        return self.store._connect().execute("SELECT status, first_day, evaluator, reason, entrant FROM cohorts WHERE "
                                             "family=?", (fid,)).fetchone()

    def entrants(self) -> list[tuple]:
        return [(e["id"], e["evaluator"], e["entered_day"], e["p_value"]) for e in self.store.entrants(since="2026-01-01")]

    def archive(self) -> list[tuple]:
        return self.store._connect().execute("SELECT evaluator, first_day, reason, entrant, accounts FROM cohort_archive "
                                             "ORDER BY archived_at, rowid").fetchall()

    def judged(self, fid: str = "fam", *, day: str, checkpoint: int, latch: str | None = None) -> int:
        return self.store.add_decision({"day": day, "family": fid, "version": 1, "run_sha": f"sha-{fid}-1", "inputs": "x",
                                        "stats": {}, "p_value": 0.5 if latch is None else 0.001,
                                        "verdict": "fail" if latch is None else f"await_{latch}", "binding": False,
                                        "checkpoint": checkpoint, "latch": latch})

    def earlier_rule_ends(self, fid: str, day: str) -> None:
        """What the release before the ladder does to an active cohort of another evaluator: completed in place."""
        self.store._connect().execute("UPDATE cohorts SET status='complete', completed_day=?, reason=? WHERE family=? "
                                      "AND status='active'", (day, BEFORE, fid))

    def refused(self, day: str, fid: str = "fam") -> None:
        self.assertEqual(self.offered(day, fid), [], f"{fid}: never offered again")
        with self.assertRaises(ValueError):
            self.store.freeze(self.program(fid), day=day)


# ================================================================================================== the rule
class TheRule(unittest.TestCase):
    def reason(self, day, state=None, *, session_over=False, **snapshot):
        return O.changed_reason(FIRST, day, {"ladder": 1, "practice_max_sessions": 60, **snapshot}, state,
                                session_over=session_over)

    def test_only_a_cohort_inside_its_window_with_no_final_verdict_is_interrupted(self):
        days = sessions(FIRST, 70)
        waiting = {"checkpoint": 40, "day": days[39], "receipt": 1, "waits": "prefilter"}
        self.assertEqual(self.reason(FIRST), O.EVALUATOR_CHANGED, "the day it was frozen")
        self.assertEqual(self.reason(days[59]), O.EVALUATOR_CHANGED, "its sixtieth session is still to come")
        self.assertEqual(self.reason(days[45], {"judged": {"40": {}}, "latch": None}), O.EVALUATOR_CHANGED,
                         "judged at its first checkpoint, the lines not met: its last one is still to come")
        self.assertEqual(self.reason(days[60]), O.EVALUATOR_CHANGED_WINDOW, "sixty sessions have passed")
        self.assertEqual(self.reason(days[63]), O.EVALUATOR_CHANGED_WINDOW,
                         "held past its window for its last checkpoint: its window ended all the same")
        for name, state in (("latched and waiting", {"judged": {"40": {}}, "latch": waiting}),
                            ("latched and waiting for its Validation verdict",
                             {"judged": {"40": {}}, "latch": dict(waiting, waits="validation")}),
                            ("latched and answered", {"judged": {"40": {}}, "latch": dict(waiting, waits=None, answer={})}),
                            ("judged at its last checkpoint", {"judged": {"40": {}, "60": {}}, "latch": None})):
            self.assertEqual(self.reason(days[45], state), O.EVALUATOR_CHANGED_FINAL, name)
            self.assertEqual(self.reason(days[45], json.dumps(state)), O.EVALUATOR_CHANGED_FINAL, f"{name}, as stored")
        self.assertEqual(self.reason(days[61], {"judged": {"60": {}}, "latch": dict(waiting, checkpoint=60)}),
                         O.EVALUATOR_CHANGED_FINAL, "held past its window for its answer")

    def test_a_session_that_has_closed_is_behind_it(self):
        days = sessions(FIRST, 61)
        self.assertEqual(self.reason(days[59]), O.EVALUATOR_CHANGED, "before or during its sixtieth session")
        self.assertEqual(self.reason(days[59], session_over=True), O.EVALUATOR_CHANGED_WINDOW,
                         "after its sixtieth session, its last checkpoint not judged: its window ended")
        self.assertEqual(self.reason(days[58], session_over=True), O.EVALUATOR_CHANGED, "after its fifty-ninth")
        self.assertEqual(self.reason(FIRST, session_over=True), O.EVALUATOR_CHANGED)
        self.assertEqual(O.changed_reason(FIRST, FIRST, {"ladder": 1, "practice_max_sessions": 1}, None, session_over=True),
                         O.EVALUATOR_CHANGED_WINDOW, "a one-session window, its session done")
        # A day that is no session day has no session of its own to count: five sessions, Monday to Friday, are behind
        # a cohort on the Saturday, whatever is said of that day.
        saturday = "2026-10-10"
        self.assertEqual(sessions(FIRST, 6)[4:], ["2026-10-09", "2026-10-12"])
        for over in (False, True):
            self.assertEqual(O.changed_reason(FIRST, saturday, {"ladder": 1, "practice_max_sessions": 6}, None,
                                              session_over=over), O.EVALUATOR_CHANGED, over)
            self.assertEqual(O.changed_reason(FIRST, saturday, {"ladder": 1, "practice_max_sessions": 5}, None,
                                              session_over=over), O.EVALUATOR_CHANGED_WINDOW, over)

    def test_a_cohort_frozen_before_the_ladder_keeps_the_old_rules_window(self):
        days = sessions(FIRST, 40)
        old = {"practice_evaluator": EVALUATOR}
        self.assertEqual(O.cohort_window(old), 10)
        self.assertEqual(O.cohort_window(dict(old, practice_max_sessions=36)), 36)
        self.assertEqual(O.cohort_window(old, min_sessions=3, max_sessions=20), 20)
        self.assertEqual(O.cohort_window({"ladder": 1, "practice_max_sessions": 60}, max_sessions=20), 60)
        self.assertEqual(O.changed_reason(FIRST, days[9], old, None), O.EVALUATOR_CHANGED)
        self.assertEqual(O.changed_reason(FIRST, days[10], old, None), O.EVALUATOR_CHANGED_WINDOW)
        latched = json.dumps({"judged": {"40": {}}, "latch": {"waits": "prefilter"}})
        self.assertEqual(O.changed_reason(FIRST, days[5], old, latched), O.EVALUATOR_CHANGED,
                         "no ladder cohort: no checkpoint to have judged it")

    def test_the_earlier_rules_ending_is_its_exact_text(self):
        self.assertEqual(O.EVALUATOR_CHANGED_BEFORE, BEFORE)
        self.assertEqual(len({O.EVALUATOR_CHANGED, O.EVALUATOR_CHANGED_FINAL, O.EVALUATOR_CHANGED_WINDOW,
                              O.EVALUATOR_CHANGED_BEFORE}), 4)


# ================================================================================================== this release's endings
class AReleaseChangesTheEvaluator(ReEntryCase):
    def test_an_interrupted_cohort_is_frozen_again_as_a_new_cohort_and_a_new_entrant(self):
        self.store.freeze(self.program(), day=FIRST)
        days = sessions(FIRST, 50)
        self.judged(day=days[39], checkpoint=40)                  # its first checkpoint: the lines not met
        self.store.evaluator = E2
        snap = self.again(days[45])
        self.assertEqual(snap["practice_evaluator"], E2)
        status, first, evaluator, reason, entrant = self.row()
        self.assertEqual((status, first, evaluator, reason), ("active", days[45], E2, None))
        self.assertEqual(self.store.ladder_state("fam", 1), {"judged": {}, "latch": None}, "its own window: unjudged")
        [(one, e1, d1, p1), (two, e2, d2, p2)] = self.entrants()
        self.assertEqual((e1, d1, p1, e2, d2, p2), (EVALUATOR, FIRST, 0.5, E2, days[45], None),
                         "two trials: the first keeps its p-value")
        self.assertEqual(entrant, two)
        [(evaluator, first, reason, archived, accounts)] = self.archive()
        self.assertEqual((evaluator, first, reason, archived), (EVALUATOR, FIRST, O.EVALUATOR_CHANGED, one))
        self.assertEqual(json.loads(accounts), [])

    def test_a_final_verdict_or_an_ended_window_is_never_started_again(self):
        days = sessions(FIRST, 70)
        for fid in ("last", "over"):
            self.store.freeze(self.program(fid), day=FIRST)
        for fid in ("waiting", "answered", "open"):
            self.store.freeze(self.program(fid), day=days[20])
        self.judged("last", day=days[59], checkpoint=60)          # its last checkpoint: the lines not met
        self.judged("open", day=days[59], checkpoint=40)          # its first: the lines not met, its last to come
        self.judged("waiting", day=days[59], checkpoint=40, latch="prefilter")
        self.judged("answered", day=days[59], checkpoint=40, latch="prefilter")
        self.store.add_answer({"day": days[60], "family": "answered", "version": 1, "inputs": "x", "stats": {},
                               "verdict": "would_promote", "binding": False})
        change = days[62]                                         # "over" is held for its last checkpoint, unjudged
        self.store.evaluator = E2
        self.assertEqual(self.offered(change, "open"), ["open"], "the one a release interrupted")
        self.assertEqual(self.row("open")[::3], ("complete", O.EVALUATOR_CHANGED))
        endings = {"waiting": O.EVALUATOR_CHANGED_FINAL, "answered": O.EVALUATOR_CHANGED_FINAL,
                   "last": O.EVALUATOR_CHANGED_FINAL, "over": O.EVALUATOR_CHANGED_WINDOW}
        for evaluator in (E2, EVALUATOR, E3):                     # under no evaluator, the one it practised under included
            self.store.evaluator = evaluator
            for fid, reason in endings.items():
                self.refused(days[65], fid)
                self.assertEqual(self.row(fid)[::3], ("complete", reason), fid)
        self.assertEqual(len(self.entrants()), 5)
        self.assertEqual(self.archive(), [])

    def three_at_their_sixtieth_session(self) -> tuple[list[str], list[dict]]:
        """Three cohorts on the day of their sixtieth calendar session, their last checkpoint unjudged: one that
        practised it, one that practised every session but it, one that never practised at all."""
        days = sessions(FIRST, 60)
        for fid in ("practised", "missed", "idle"):
            self.store.freeze(self.program(fid), day=FIRST)
        self.add_record("practised", 1, days, [[0.1]] * 60)
        self.add_record("missed", 1, days[:59], [[0.1]] * 59)
        self.store.evaluator = E2
        return days, [self.program(f) for f in ("practised", "missed", "idle")]

    def test_a_release_the_evening_of_its_last_session_finds_its_window_ended(self):
        """The session's end that should have judged its last checkpoint was missed, and the release came that night.
        The window is sixty CALENDAR sessions: once the House's clock says the sixtieth has closed it is behind every
        cohort, one the House never practised that day (it was down all day) included."""
        days, current = self.three_at_their_sixtieth_session()
        out = self.store.cohort_candidates(current, day=days[59], in_session=False, session_over=True)
        self.assertEqual(out, [], "none is offered again")
        for fid, why in (("practised", "sixty sessions practised"), ("missed", "its sixtieth session closed without it"),
                         ("idle", "it never practised, and its sixty sessions passed all the same")):
            self.assertEqual(self.row(fid)[::3], ("complete", O.EVALUATOR_CHANGED_WINDOW), why)
            self.refused(days[59], fid)
        self.assertEqual(self.archive(), [])

    def test_a_release_before_the_open_of_its_last_session_interrupts_it(self):
        days, current = self.three_at_their_sixtieth_session()
        db = self.store._connect()
        db.execute("DELETE FROM trades WHERE family='practised' AND exit_day=?", (days[59],))
        db.execute("UPDATE practice SET last_day=?, sessions=59 WHERE family='practised'", (days[58],))
        out = self.store.cohort_candidates(current, day=days[59], in_session=False, session_over=False)
        self.assertEqual(sorted(r["family"] for r in out), ["idle", "missed", "practised"])
        for fid in ("practised", "missed", "idle"):
            self.assertEqual(self.row(fid)[::3], ("complete", O.EVALUATOR_CHANGED), f"{fid}: its sixtieth still to come")

    def test_a_caller_that_does_not_say_still_finds_a_session_it_practised_behind_it(self):
        """Outside the session a cohort that practised today has today's session behind it, whatever the caller says of
        the clock (it cannot have practised before the open): the stricter of the two readings holds."""
        days, current = self.three_at_their_sixtieth_session()
        out = self.store.cohort_candidates(current, day=days[59], in_session=False)
        self.assertEqual(sorted(r["family"] for r in out), ["idle", "missed"])
        self.assertEqual(self.row("practised")[::3], ("complete", O.EVALUATOR_CHANGED_WINDOW))

    def test_inside_the_session_its_last_session_is_still_running(self):
        days = sessions(FIRST, 60)
        self.store.freeze(self.program(), day=FIRST)
        self.add_record("fam", 1, days, [[0.1]] * 60)
        self.store.evaluator = E2
        self.assertEqual(self.offered(days[59]), ["fam"])
        self.assertEqual(self.row()[::3], ("complete", O.EVALUATOR_CHANGED))

    def test_every_other_ending_is_final_under_every_evaluator(self):
        endings = {"window": ("complete", O.WINDOW_ENDED), "unjudged": ("complete", O.WINDOW_UNJUDGED),
                   "unanswered": ("complete", O.WINDOW_UNANSWERED), "no-reason": ("complete", None),
                   "target": ("complete", "observation target reached"),
                   "old-window": ("complete", "maximum session window reached"),
                   "failed": ("failed", "ladder: its version did not meet the Validation line"),
                   "prefilter": ("failed", "ladder: the pre-filter read did not pass its line"),
                   "retired": ("failed", "ladder: its family retired"),
                   "hygiene": ("failed", "hygiene: its research family retired"),
                   "answerless": ("complete", "ladder: no pre-filter answer within 5 sessions of its checkpoint"),
                   "promoted": ("promoted", "ladder: promoted to Probe (receipt 1)"), "demoted": ("demoted", "ladder: x"),
                   # a text that only resembles an interruption is none
                   "near": ("complete", O.EVALUATOR_CHANGED + "."), "failed-changed": ("failed", O.EVALUATOR_CHANGED),
                   "failed-before": ("failed", BEFORE)}
        db = self.store._connect()
        for fid, (status, reason) in endings.items():
            self.store.freeze(self.program(fid), day=FIRST)
            db.execute("UPDATE cohorts SET status=?, completed_day='2026-10-08', reason=? WHERE family=?",
                       (status, reason, fid))
        for evaluator in (EVALUATOR, E2):
            self.store.evaluator = evaluator
            for fid in endings:
                self.refused("2026-10-12", fid)
        self.assertEqual(self.archive(), [])

    def test_freeze_ends_an_active_cohort_of_another_evaluator_by_the_same_rule(self):
        days = sessions(FIRST, 45)
        for fid in ("open", "final"):
            self.store.freeze(self.program(fid), day=FIRST)
        self.judged("final", day=days[39], checkpoint=40, latch="validation")
        self.store.evaluator = E2                                 # no pins between: `freeze` meets them still active
        self.assertEqual(self.store.freeze(self.program("open"), day=days[42])["practice_evaluator"], E2)
        with self.assertRaises(ValueError):
            self.store.freeze(self.program("final"), day=days[42])
        self.assertEqual(self.row("final")[::3], ("complete", O.EVALUATOR_CHANGED_FINAL))
        self.assertEqual([a[2] for a in self.archive()], [O.EVALUATOR_CHANGED])

    def test_the_old_rules_window_is_the_one_the_house_gave(self):
        """A cohort frozen before the ladder is read by the old rule's window as the House passes it."""
        snapshot = dict(self.program("old"), practice_frozen=True, practice_evaluator="an-older-evaluator")
        db = self.store._connect()
        days = sessions(FIRST, 30)
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot, status, completed_day, reason) "
                   "VALUES('old', 1, 1.0, ?, ?, 'complete', ?, ?)", (FIRST, json.dumps(snapshot), days[12], BEFORE))
        current = [self.program("old")]
        self.assertEqual(self.store.cohort_candidates(current, day=days[20], in_session=True), [], "twelve sessions of ten")
        with self.assertRaises(ValueError):
            self.store.freeze(self.program("old"), day=days[20])
        out = self.store.cohort_candidates(current, day=days[20], in_session=True, max_sessions=20)
        self.assertEqual([r["family"] for r in out], ["old"], "twelve sessions of twenty")
        self.assertTrue(self.store.freeze(out[0], day=days[20])["ladder"], "and `freeze` reads it the same")


# ================================================================================================== the five leaks, closed
@unittest.skipUnless(HAVE, "numpy not installed")
class TheLeaks(NightCase, ReEntryCase):
    # 1. a cohort that had its WHOLE window gets no second one, whatever evaluator follows
    def test_a_window_that_ended_without_promotion_is_never_tried_again(self):
        self.cohort(returns=[[-0.2, 0.1]] * 60)                   # sixty sessions of a losing record
        for k in (40, 60):
            self.assertEqual(self.night(k)["judged"], 1, k)
        self.assertEqual(self.pins(61), [], "its window ended")
        self.assertEqual(self.status(), ("complete", O.WINDOW_ENDED))
        for evaluator in (E2, E3, EVALUATOR):                     # every release that touches league/live or the Gym
            self.store.evaluator = evaluator
            self.refused(self.days[61])
            self.refused(self.days[69])
        self.assertEqual(len(self.entrants()), 1, "one window, one trial")
        self.assertEqual(self.archive(), [])

    # 2. out and back on one session day: the third cohort is its own entrant and reads none of the first one's closes
    def test_a_deploy_and_rollback_on_one_day_is_a_new_entrant_and_leaks_none_of_that_days_closes(self):
        self.store.freeze(self.program(), day=FIRST)
        days = sessions(FIRST, 5)
        self.add_record("fam", 1, days, [[0.3, 0.3]] * 5)          # program closes under EVALUATOR, the last today
        today = days[-1]
        self.store.evaluator = E2                                 # the deploy, mid-session
        self.again(today)
        self.store.evaluator = EVALUATOR                          # the rollback, the same session
        self.again(today)
        status, first, evaluator, _, entrant = self.row()
        self.assertEqual((status, first, evaluator), ("active", today, EVALUATOR))
        rows = self.entrants()
        self.assertEqual([(e, d, p) for _, e, d, p in rows], [(EVALUATOR, FIRST, None), (E2, today, None),
                                                              (EVALUATOR, today, None)], "three cohorts, three entrants")
        self.assertEqual(len({i for i, *_ in rows}), 3)
        self.assertEqual(entrant, rows[-1][0], "the third cohort names its own row")
        self.assertEqual([json.loads(a[4]) for a in self.archive()], [["a"], ["a"]], "the first cohort's account, barred")
        practice, closes = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=today, through=today)
        self.assertEqual((practice, closes), (None, []), "none of the first cohort's closes of that day, nor its row")
        # Its own account's closes are its record; a judgement writes its own entrant's p-value alone.
        self.store.add("fam@1:o", "fam", 1, [{"id": "n1", "pnl": 10.0, "max_loss": 100.0, "exit_day": today,
                                              "evaluator": EVALUATOR}], account="c")
        self.store.add("fam@1:o", "fam", 1, [{"id": "late", "pnl": 99.0, "max_loss": 100.0, "exit_day": today,
                                              "evaluator": EVALUATOR}], account="a")
        _, closes = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=today, through=today)
        self.assertEqual([c["trade_id"] for c in closes], ["n1"], "a program close of the first cohort's account still "
                                                                  "in flight at the change is the first cohort's")
        self.judged(day=today, checkpoint=40)
        self.assertEqual([p for *_, p in self.entrants()], [None, None, 0.5])

    # 3. the same, days apart: the cohort has its own entrant, inside the trailing window for as long as it practises
    def test_back_on_an_earlier_evaluator_the_cohort_is_counted_as_itself(self):
        self.store.freeze(self.program(), day=FIRST)
        days = sessions(FIRST, 12)
        self.store.evaluator = E2
        self.again(days[5])
        self.store.evaluator = EVALUATOR
        self.again(days[10])
        self.assertEqual(self.row()[:3], ("active", days[10], EVALUATOR))
        day = (dt.date.fromisoformat(FIRST) + dt.timedelta(days=100)).isoformat()
        since = (dt.date.fromisoformat(day) - dt.timedelta(days=90)).isoformat()
        self.assertEqual([(e["evaluator"], e["entered_day"]) for e in self.store.entrants(since=since)],
                         [(EVALUATOR, days[10])], "an active cohort, 66 days in, in the window as its own entrant")

    # 4. a rollback to the release before the ladder, then the SAME release again
    def test_a_rollback_and_the_same_release_again_starts_the_interrupted_and_no_finished_window(self):
        days = sessions(FIRST, 70)
        for fid in ("fam", "edge", "sixtieth", "waiting", "answered", "last", "over", "held"):
            self.store.freeze(self.program(fid), day=FIRST)
        self.judged("waiting", day=days[39], checkpoint=40, latch="validation")
        self.judged("answered", day=days[39], checkpoint=40, latch="prefilter")
        self.store.add_answer({"day": days[40], "family": "answered", "version": 1, "inputs": "x", "stats": {},
                               "verdict": "would_promote", "binding": False})
        self.judged("last", day=days[59], checkpoint=60)
        # The earlier release runs: every active cohort of another evaluator is completed in place, whatever its state.
        self.earlier_rule_ends("fam", days[1])
        self.earlier_rule_ends("edge", days[58])                  # the day of its fifty-ninth session: still inside
        # The day of its sixtieth: the row cannot say whether that session was still running, so it is counted.
        self.earlier_rule_ends("sixtieth", days[59])
        for fid in ("waiting", "answered"):
            self.earlier_rule_ends(fid, days[45])
        self.earlier_rule_ends("last", days[59])
        self.earlier_rule_ends("over", days[60])                  # sixty sessions had passed
        self.earlier_rule_ends("held", days[63])
        back = days[64]                                           # this same release again: the same evaluator
        self.assertEqual(self.store.evaluator, EVALUATOR)
        for fid in ("sixtieth", "waiting", "answered", "last", "over", "held"):
            self.refused(back, fid)
            self.assertEqual(self.row(fid)[::3], ("complete", BEFORE), f"{fid}: its row is left as it was written")
        for fid in ("fam", "edge"):
            self.again(back, fid)
            status, first, evaluator, reason, entrant = self.row(fid)
            self.assertEqual((status, first, evaluator, reason), ("active", back, EVALUATOR, None), fid)
            mine = [e for e in self.store.entrants(since="2026-01-01") if e["family"] == fid]
            self.assertEqual([(e["evaluator"], e["entered_day"]) for e in mine], [(EVALUATOR, FIRST), (EVALUATOR, back)],
                             "the returning evaluator's key does not collide: a new entrant")
            self.assertEqual(entrant, mine[-1]["id"])
        self.assertEqual(sorted((a[1], a[2]) for a in self.archive()), [(FIRST, BEFORE)] * 2)
        self.assertEqual(self.offered(days[65], "fam"), [], "practising: in its slot, never offered")
        # And a changed build after the rollback reads the rows the same way: by their ending, not their evaluator.
        self.store.evaluator = E2
        for fid in ("sixtieth", "waiting", "answered", "last", "over", "held"):
            self.refused(days[66], fid)

    # 4a. the review's two cases: the evening of the sixtieth calendar session, its last checkpoint unjudged
    def test_an_evening_release_after_a_sixtieth_session_the_house_never_practised_starts_nothing_again(self):
        """The House was down on the cohort's sixtieth session (no practice that day, no session's end) and a release
        changes the evaluator that evening, after the close: sixty calendar sessions are behind it."""
        self.store.freeze(self.program(), day=self.days[0])
        self.store._connect().execute(
            "INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, sessions) "
            "VALUES('fam', 1, 'validated', 10000, 1, ?, 2, ?, 59)", (self.days[0], self.days[58]))
        self.store.evaluator = E2
        out = self.store.cohort_candidates([self.program()], day=self.days[59], in_session=False, session_over=True)
        self.assertEqual((out, self.row()[::3]), ([], ("complete", O.EVALUATOR_CHANGED_WINDOW)))
        for evaluator in (E2, E3, EVALUATOR):
            self.store.evaluator = evaluator
            self.refused(self.days[60])
        self.assertEqual((len(self.entrants()), self.archive()), (1, []), "one window, one trial")

    def test_a_rollback_the_evening_of_the_sixtieth_session_starts_nothing_again(self):
        """The earlier rule ends it the evening of its sixtieth session, which it practised, its last checkpoint
        unjudged: its row names that day and nothing more, and this same release never starts it again."""
        self.cohort()
        self.earlier_rule_ends("fam", self.days[59])
        for evaluator in (EVALUATOR, E2):
            self.store.evaluator = evaluator
            self.refused(self.days[60])
        self.assertEqual((self.row()[::3], len(self.entrants()), self.archive()), (("complete", BEFORE), 1, []))

    def test_a_row_the_earlier_rule_ended_that_cannot_be_read_never_reenters(self):
        db = self.store._connect()
        for fid, day, snapshot in (("noday", None, None), ("badday", "soon", None), ("badsnap", "2026-10-06", "{")):
            self.store.freeze(self.program(fid), day=FIRST)
            db.execute("UPDATE cohorts SET status='complete', completed_day=?, reason=?, snapshot=COALESCE(?, snapshot) "
                       "WHERE family=?", (day, BEFORE, snapshot, fid))
            self.assertEqual(self.offered("2026-10-12", fid), [])

    # 5. the earlier cohort's account is never the new cohort's, in any read
    def test_the_old_accounts_wind_down_closes_are_never_the_new_cohorts(self):
        from league.swarm import incubator as SI
        from league.swarm import practice as P

        self.store.freeze(self.program(), day=FIRST)
        self.add_record("fam", 1, sessions(FIRST, 4), [[0.5]] * 4)   # +$200 under EVALUATOR, account "a"
        self.store.evaluator = E2
        day = "2026-10-12"
        self.again(day)
        # The old account "a" winds down under E2: the House marks its closes forced and stamps the running evaluator;
        # a program close of it still in flight at the change is stamped the same and not forced.
        self.store.add("fam@1:o", "fam", 1, [{"id": "w1", "day": day, "pnl": -80.0, "max_loss": 100.0, "exit_day": day,
                                              "forced": True, "evaluator": E2},
                                             {"id": "w2", "day": day, "pnl": 55.0, "max_loss": 100.0, "exit_day": day,
                                              "evaluator": E2}], account="a")
        minute = {"family": "fam", "version": 1, "tier": "validated", "capital": 10000.0, "at": self.now[0], "day": day}
        self.store.practice([dict(minute, account="a", equity=10175.0, status="wound_down")])
        db = self.store._connect()
        self.assertIsNone(db.execute("SELECT 1 FROM practice").fetchone(), "the old account's minutes are not its record")
        self.store.practice([dict(minute, account="b", equity=10000.0)])
        self.assertEqual(db.execute("SELECT base_pnl, pnl_marked, first_day, sessions, account FROM practice").fetchone(),
                         (0.0, 0.0, day, 1, "b"), "a new cohort's practice row starts from zero")
        after = "2026-10-13"
        record = practice_record(self.root, "fam", 1, before=after, evaluator=E2)
        self.assertEqual((record["closes_program"], record["closes_all"], record["pnl_all"], record["sessions"]),
                         (0, 0, 0.0, 1), "the incubator's first look charges it nothing of the old cohort's")
        [row] = P.cohort_status(self.root, today=after)
        self.assertEqual((row["closes_program"], row["closes_all"], row["pnl_all"]), (0, 0, 0.0), "nor does the cohort keep")
        [row] = SI.practice_cohorts(self.root, research={"bundle": "bundle-2", "execution": "exec-2"}, before=after)
        self.assertEqual((row["closes_program"], row["pnl_program"]), (0, 0.0), "nor the swarm's review of practice")
        self.assertEqual(self.store.ladder_rows("fam", 1, evaluator=E2, first_day=day, through=after)[1], [])
        program = [r for r in practice_summary(self.root, sessions=None)["rows"] if r["family"] == "fam"][0]["program"]
        self.assertEqual(program["trades"], 0, "nor the research signal's program statistics")
        # Its own account's closes are all of these reads' record: a program close and its own wind-down.
        self.store.add("fam@1:o", "fam", 1, [{"id": "p1", "day": day, "pnl": 12.0, "max_loss": 100.0, "exit_day": day,
                                              "evaluator": E2},
                                             {"id": "p2", "day": day, "pnl": -5.0, "max_loss": 100.0, "exit_day": day,
                                              "forced": True, "evaluator": E2}], account="b")
        record = practice_record(self.root, "fam", 1, before=after, evaluator=E2)
        self.assertEqual((record["closes_program"], record["closes_all"], record["pnl_all"]), (1, 2, 7.0))
        [row] = P.cohort_status(self.root, today=after)
        self.assertEqual((row["closes_program"], row["closes_all"], row["pnl_all"]), (1, 2, 7.0))
        [row] = SI.practice_cohorts(self.root, research={"bundle": "bundle-2", "execution": "exec-2"}, before=after)
        self.assertEqual((row["closes_program"], row["pnl_program"]), (1, 12.0))
        self.assertEqual([c["trade_id"] for c in self.store.ladder_rows("fam", 1, evaluator=E2, first_day=day,
                                                                        through=after)[1]], ["p1"])
        # A remade account of the same cohort carries on from the cohort's own closes, never the old cohort's.
        self.store.practice([dict(minute, account="c", equity=10000.0, at=self.now[0] + 60.0)])
        self.assertEqual(db.execute("SELECT base_pnl, account FROM practice").fetchone(), (7.0, "c"))

    def test_the_house_is_told_an_earlier_cohorts_account(self):
        self.store.freeze(self.program(), day=FIRST)
        self.add_record("fam", 1, sessions(FIRST, 2), [[0.5]] * 2)
        self.assertFalse(self.store.earlier_account("fam", 1, "a"), "its own")
        self.store.evaluator = E2
        self.again("2026-10-12")
        self.store.evaluator = EVALUATOR                          # the evaluator that made account "a" came back
        self.again("2026-10-13")
        self.assertTrue(self.store.earlier_account("fam", 1, "a"), "made under this evaluator, and still an earlier cohort's")
        self.assertFalse(self.store.earlier_account("fam", 1, "b"))
        self.assertFalse(self.store.earlier_account("other", 1, "a"))
        self.assertFalse(self.store.earlier_account("fam", None, "a"))
        with patch.object(O, "earlier_accounts", side_effect=sqlite3.OperationalError("database is locked")):
            fresh = ObserveStore(self.root, clock=lambda: 1.0)
            self.addCleanup(fresh.close)
            self.assertFalse(fresh.earlier_account("fam", 1, "a"), "unread: asked again next minute, never raised")
        self.assertTrue(fresh.earlier_account("fam", 1, "a"))

    def test_a_file_without_the_archives_accounts_bars_none(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        self.assertEqual(O.earlier_accounts(db, "fam", 1), [])
        db.execute("CREATE TABLE cohort_archive (family TEXT, version INTEGER)")
        self.assertEqual((O.earlier_accounts(db, "fam", 1), O.own_closes(db, "fam", 1)), ([], ("", [])))
        db.execute("ALTER TABLE cohort_archive ADD COLUMN accounts TEXT")
        db.executemany("INSERT INTO cohort_archive VALUES('fam', 1, ?)",
                       [('["a", "b"]',), (None,), ("{",), ('"x"',), ('["b", 7]',)])
        self.assertEqual(O.earlier_accounts(db, "fam", 1), ["7", "a", "b"])
        self.assertEqual(O.own_closes(db, "fam", 1),
                         (" AND account != ? AND account != ? AND account != ?", ["7", "a", "b"]))

    def test_the_swarms_own_read_of_the_archive_is_the_houses(self):
        """`league/swarm/incubator.py` reads the record's file and never imports the live path: its copy of the rule is
        held to the House's on every shape of the archive."""
        from league.swarm import incubator as SI

        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        self.assertEqual(SI._earlier_accounts(db, "fam", 1), O.earlier_accounts(db, "fam", 1))
        db.execute("CREATE TABLE cohort_archive (family TEXT, version INTEGER)")
        self.assertEqual(SI._earlier_accounts(db, "fam", 1), O.earlier_accounts(db, "fam", 1))
        db.execute("ALTER TABLE cohort_archive ADD COLUMN accounts TEXT")
        db.executemany("INSERT INTO cohort_archive VALUES(?, ?, ?)",
                       [("fam", 1, '["a", "b"]'), ("fam", 1, None), ("fam", 1, "{"), ("fam", 1, '"x"'), ("fam", 1, '["b", 7]'),
                        ("fam", 2, '["c"]'), ("other", 1, '["d"]')])
        for family, version, expected in (("fam", 1, ["7", "a", "b"]), ("fam", 2, ["c"]), ("other", 1, ["d"]),
                                          ("none", 1, [])):
            self.assertEqual(SI._earlier_accounts(db, family, version), expected)
            self.assertEqual(O.earlier_accounts(db, family, version), expected)

    # ------------------------------------------------------------------ the false-discovery family counts each try
    def test_both_tries_are_trials_of_the_desk_while_each_is_inside_the_trailing_window(self):
        self.store.freeze(self.program(), day=self.days[0])
        self.store.evaluator = E2
        self.again(self.days[5])
        self.add_record("fam", 1, self.days[5:65], pattern(60))
        db = self.store._connect()
        db.execute("UPDATE trades SET evaluator=?, account='b'", (E2,))
        with patch.object(L.Rules, "from_constitution", return_value=rules()):
            db.execute("UPDATE practice SET sessions=40, last_day=?", (self.days[44],))
            out = self.ladder.end_of_day(self.days[44])
        self.assertEqual((out["judged"], out["entrants"], out["bh_size"]), (1, 2, 2),
                         "the interrupted try, entered eight weeks before, is still a trial of the family")
        self.assertEqual([p for *_, p in self.entrants()][0], None, "and it keeps its own p-value: none was judged")


# ================================================================================================== from its own first day
class FromItsOwnFirstDay(StoreCase):
    """The other half of THE COHORT'S OWN RECORD: a close of the program under the SAME evaluator, on an account no
    archive names, that exited before the cohort's first day is in none of the four reads of the cohort's record."""

    FIRST_DAY = "2026-10-12"

    def setUp(self):
        super().setUp()
        self.store.freeze(self.program(), day=self.FIRST_DAY)
        db = self.store._connect()
        for i, (day, pnl) in enumerate((("2026-10-08", 40.0), ("2026-10-09", 40.0), (self.FIRST_DAY, 7.0),
                                        ("2026-10-13", 5.0))):
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, "
                       "body, exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("fam@1:o", "x", "fam", 1, f"t{i}", day, pnl, 100.0, 1.0, json.dumps({"qty": 1, "fees": 1.3}), day,
                        "program", 0, EVALUATOR))
        db.execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, sessions) "
                   "VALUES('fam', 1, 'validated', 10000, 1, ?, 2, '2026-10-13', 2)", (self.FIRST_DAY,))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone(), (0,), "no account is barred")
        self.assertEqual(O.own_closes(db, "fam", 1), ("", []))

    def test_the_ladders_rows(self):
        _, rows = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=self.FIRST_DAY, through="2026-10-13")
        self.assertEqual([r["trade_id"] for r in rows], ["t2", "t3"])

    def test_the_incubators_record(self):
        record = practice_record(self.root, "fam", 1, before="2026-10-14", evaluator=EVALUATOR)
        self.assertEqual((record["closes_program"], record["pnl_program"], record["closes_all"], record["pnl_all"]),
                         (2, 12.0, 2, 12.0))

    def test_the_swarms_cohort_keep(self):
        from league.swarm import practice as P

        [row] = P.cohort_status(self.root, today="2026-10-14")
        self.assertEqual((row["closes_program"], row["pnl_program"], row["closes_all"], row["pnl_all"]), (2, 12.0, 2, 12.0))

    def test_the_swarms_review_of_practice(self):
        from league.swarm import incubator as SI

        [row] = SI.practice_cohorts(self.root, research={"bundle": "bundle-1", "execution": "exec-1"}, before="2026-10-14")
        self.assertEqual((row["closes_program"], row["pnl_program"]), (2, 12.0))


# ================================================================================================== an older file
class AnOlderFile(StoreCase):
    def test_entrants_keyed_by_evaluator_are_rebuilt_one_a_row_and_named_by_their_cohorts(self):
        path = self.root / "keyed"
        path.mkdir()
        db = sqlite3.connect(str(path / "observe.sqlite"))
        db.executescript(BEFORE_CHECKPOINTS)
        snapshot = json.dumps(dict(self.program("kept"), practice_frozen=True, practice_evaluator=E2, ladder=1,
                                   practice_max_sessions=60))
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot, evaluator) VALUES('kept', 1, 9, "
                   "'2026-10-12', ?, ?)", (snapshot, E2))
        db.execute("INSERT INTO cohort_archive(family, version, evaluator, admitted_at, first_day, snapshot, status, "
                   "archived_at) VALUES('kept', 1, ?, 1, '2026-10-05', '{}', 'complete', 9)", (EVALUATOR,))
        db.executemany("INSERT INTO entrants(family, version, run_sha, evaluator, entered_at, entered_day, p_value, p_day) "
                       "VALUES('kept', 1, 'sha-kept-1', ?, ?, ?, ?, ?)",
                       [(E2, 9, "2026-10-12", None, None), (EVALUATOR, 1, "2026-10-05", 0.4, "2026-10-09")])
        db.commit()
        db.close()
        for _ in range(2):                                        # opened twice: rebuilt once
            store = ObserveStore(path, clock=lambda: 10.0)
            store.evaluator = E2
            db = store._connect()
            self.assertEqual(db.execute("SELECT id, evaluator, entered_day, p_value FROM entrants ORDER BY id").fetchall(),
                             [(1, EVALUATOR, "2026-10-05", 0.4), (2, E2, "2026-10-12", None)], "in admission order")
            self.assertEqual(db.execute("SELECT entrant FROM cohorts").fetchone(), (2,))
            self.assertEqual(db.execute("SELECT entrant, accounts FROM cohort_archive").fetchone(), (1, None))
            self.assertEqual([r[1] for r in db.execute("PRAGMA index_list(entrants)") if r[1] == "entrants_day"],
                             ["entrants_day"])
            store.close()
        store = ObserveStore(path, clock=lambda: 11.0)
        store.evaluator = E2
        self.addCleanup(store.close)
        store.add_decision({"day": "2026-12-09", "family": "kept", "version": 1, "inputs": "y", "stats": {}, "p_value": 0.2,
                            "verdict": "fail", "binding": False, "checkpoint": 40})
        self.assertEqual(store._connect().execute("SELECT p_value FROM entrants ORDER BY id").fetchall(), [(0.4,), (0.2,)])


if __name__ == "__main__":
    unittest.main()
