"""THE OWNER'S CHANGE OF THE PINNED DONE RULE (A50, the goal of Oct 16, 2026, 02:10Z; goal-2026-10-10/GOAL-MESSAGE-
SPEED.txt; the captain's amendment A50), each new rule at its edges:

- THE PIN: docs/goals/DONE-RULE-A50.md is the pinned rule (`dlane.DONE["rule_sha256"]`), holding the owner's Done
  verbatim; the Oct 9 rule is `dlane.OLD_DONE`, history read by no module.
- THE SCHEDULE: checkpoints at the 15th counted close, then every 5th (20, 25, 30, ...), fixed by count.
- THE BAR: at least 15 closes, at least 3 from each of at least 2 programs (14 vs 15; 2 vs 3; one program vs two).
  DONE-RULE-A1 A1.1 is unchanged: a claim still needs 2 programs with 5 or more matched closes each.
- A14'S INTENTS: agreed >= 0.95 x S, or S < 40, none missing, and agreed >= S - 1 (S 19, 39, 40, 41, 1; a missing
  session is never the one forgiven; FW6's range, 20 sessions and up, reads exactly as before).
- ITEM 7'S WINDOW: the 3 UTC days ending on the UTC day of the 15th close (across a weekend, across New York's clock
  change, a close after 00:00Z); each later checkpoint every UTC day after the previous one's through its own.
- A READING UNDER ANOTHER PINNED RULE is never carried into this one's checkpoints, and does not silence A8.

Every close, session and figure here is invented."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import re
import unittest
from pathlib import Path

from league.ops import dlane_report as R
from league.ops import forward_db
from league.swarm import dlane
from league.tests.test_dlane_report import NIGHTLY, Fixture
from league.tests.test_dlane_report_dc1 import Base, Research, ep, options_close
from league.tests.test_forward_a14 import DAYS, Reading, close, priced

REPO = Path(__file__).resolve().parents[2]
RULE_FILE = REPO / "docs" / "goals" / "DONE-RULE-A50.md"
#: The owner's Done, verbatim (goal-2026-10-10/GOAL-MESSAGE-SPEED.txt, set by /goal at 02:10Z Oct 16, 2026).
OWNERS_DONE = (
    "agent programs (not House routes) show positive realized after-fee P&L on real money, counted from Oct 10, 2026, "
    "read only at fixed checkpoints: the 15th counted close, then every 5th; >= 15 closes with >= 3 each from >= 2 "
    "programs; live fills match replay (gap <= 15 bp; intents agree on >= 95% of sessions, or all but one when fewer "
    "than 40 are read); research 24/7 within budget without captain on each of the 3 UTC days ending on the checkpoint "
    "day (later checkpoints: every day since the previous one). Then provide the $30k scaling plan (pinned A45). Report "
    "only account-shown profit, with Net after costs beside it.")


def words(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class ThePinnedRule(unittest.TestCase):
    def test_the_rule_file_is_the_pinned_rule_and_holds_the_owners_done_verbatim(self):
        self.assertEqual(hashlib.sha256(RULE_FILE.read_bytes()).hexdigest(), dlane.DONE["rule_sha256"])
        self.assertEqual(dlane.DONE["rule_sha256"], "9693fe0034926fda43270668fbaa40eecb3e8645022ec14fcd6ca94d61980eef")
        text = words(RULE_FILE.read_text())
        self.assertIn(OWNERS_DONE, text)
        for said in ("replaces DONE-RULE.md (sha256 0d007696", "DONE-RULE-A1.md (sha256 333bad06, A1.1-A1.4) stands whole",
                     "fixed by count", "optional stopping", "near a coin flip at zero edge"):
            self.assertIn(said, text)

    def test_the_owners_constants_and_everything_else_as_it_was(self):
        rule = dlane.DONE
        self.assertEqual((rule["min_closes"], rule["min_programs"], rule["min_closes_per_program"]), (15, 2, 3))
        self.assertEqual((rule["first_checkpoint"], rule["checkpoint_every"], rule["research_first_days"]), (15, 5, 3))
        # Unchanged: the routes, the inception, A1 (its sha, its 2 measured programs with 5 matched closes, the gap).
        self.assertEqual((rule["routes_all"], rule["routes_screen"], rule["inception"]),
                         ((":r", ":t", ":i"), (":r",), "2026-09-26T06:23:00Z"))
        self.assertEqual((rule["gap_limit"], rule["gap_min_matched"], rule["min_measured_programs"]), (0.10, 5, 2))
        self.assertEqual(rule["amendment_sha256"], "333bad0679fb9c9a76c1cc0b5248d52c5f84c96e0cff5376f9c8d446a4c4ff0b")
        self.assertEqual(R.DONE_FROM, "2026-10-10T04:00:00Z")
        self.assertEqual((forward_db.A14_GAP_BP, forward_db.A14_AGREE, forward_db.A14_ALL_BUT_ONE_UNDER), (15.0, 0.95, 40))
        self.assertEqual((R.A14_GAP_BP, R.A14_AGREEMENT, R.A14_ALL_BUT_ONE_UNDER),
                         (forward_db.A14_GAP_BP, forward_db.A14_AGREE, forward_db.A14_ALL_BUT_ONE_UNDER))

    def test_the_old_rule_is_kept_visible_and_read_by_nothing(self):
        self.assertEqual(dlane.OLD_DONE, {"rule_sha256": "0d007696c9a6a1cbbd7d2cc345811359ab1cec389cf88f75ceff295bbbc48dca",
                                          "min_closes": 30, "min_closes_per_program": 5, "first_checkpoint": 30,
                                          "checkpoint_every": 10, "research_first_days": 7})
        readers = []
        for path in sorted((REPO / "league").rglob("*.py")):
            if "tests" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                named = (isinstance(node, ast.Name) and node.id == "OLD_DONE"
                         and not isinstance(node.ctx, ast.Store)) or \
                    (isinstance(node, ast.Attribute) and node.attr == "OLD_DONE")
                if named:
                    readers.append(f"{path.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(readers, [], "the Oct 9 rule is history: no module reads it")
        self.assertFalse(hasattr(R, "RESEARCH_FIRST_DAYS"), "item 7's window is the pinned rule's (research_first_days)")

    def test_the_report_carries_the_rule_its_loosenings_and_the_intents_amendment(self):
        self.assertEqual([row["rule"] for row in R.LOOSENED[-4:]],
                         ["Done's checkpoints (A50, the owner's goal of Oct 16)", "Done's bar (A50, the owner's goal of Oct 16)",
                          "A14's intents bound (A50, the owner's goal of Oct 16)",
                          "Done's research 24/7 window (A50, the owner's goal of Oct 16)"])
        rows = {row["rule"]: row for row in R.LOOSENED[-4:]}
        self.assertTrue(all(set(row) == {"rule", "was", "now", "cost"} for row in rows.values()))
        checkpoints, bar, intents, window = rows.values()
        self.assertEqual((checkpoints["was"], bar["was"]), ("the 30th counted close, then every 10th",
                                                            "at least 30 closes, at least 5 from each of at least 2 programs"))
        for said in ("near a coin flip at zero edge", "optional stopping", "mostly market direction"):
            self.assertIn(said, checkpoints["cost"])
        self.assertIn("one bad session is forgiven at small S", intents["cost"])
        self.assertIn("A50 states none beyond the checkpoints'", bar["cost"])
        self.assertIn("A50 states none beyond the checkpoints'", window["cost"])
        # A14's registered sentence stays; the owner's change rides beside it, in the report and in the docs.
        self.assertIn("at least 95% of the counted sessions", R.A14_CONSISTENCY)
        self.assertEqual(R.PREREGISTERED["amended"]["id"], "A50")
        self.assertEqual(R.PREREGISTERED["amended"]["text"], R.A50_INTENTS)
        self.assertIn("all of them but one", R.A50_INTENTS)
        page = words((REPO / "docs" / "operations.md").read_text())
        self.assertIn(R.A50_INTENTS, page)
        log = (REPO / "CHANGELOG.md").read_text()
        heading = "### Done at the 15th close, then every 5th: the owner's new goal (A50)"
        first_deploy = re.search(r"^### \d\d:\d\dZ ", log, re.M).start()
        self.assertTrue(log.index("## Not yet deployed") < log.index(heading) < first_deploy, "under Not yet deployed")


# ================================================================================================== the schedule
class TheSchedule(Base):
    """The meter over invented options closes (league/tests/test_dlane_report_dc1.py's fixture)."""

    def test_14_closes_read_nothing_and_the_15th_is_the_first_checkpoint(self):
        m = self.meter(self.closes(14), now="2026-11-04T14:00:00Z")
        self.assertEqual((m["checkpoints"], m["latest"], m["next_checkpoint"]), ([], None, 15))
        self.assertIn("14 closes of the 15 needed", m["running"]["why"])
        m = self.meter(self.closes(15), now="2026-11-04T14:00:00Z")
        self.assertEqual(([cp["at_close"] for cp in m["checkpoints"]], m["next_checkpoint"]), ([15], 20))
        self.assertEqual((m["latest"]["closes"], m["latest"]["holds"], m["latest"]["final"]), (15, True, True))

    def test_the_checkpoints_are_15_20_25_and_on_fixed_by_count(self):
        for n, want, nxt in ((19, [15], 20), (20, [15, 20], 25), (24, [15, 20], 25), (25, [15, 20, 25], 30),
                             (31, [15, 20, 25, 30], 35), (45, [15, 20, 25, 30, 35, 40, 45], 50)):
            m = self.meter(self.closes(n), now="2026-11-04T14:00:00Z")
            self.assertEqual(([cp["at_close"] for cp in m["checkpoints"]], m["next_checkpoint"]), (want, nxt), n)
            self.assertEqual([cp["closes"] for cp in m["checkpoints"]], want, "each over exactly its first K closes")

    def test_the_meter_asks_each_checkpoint_its_own_research_window(self):
        asked = []

        class Asked(Research):
            def __call__(self, first: str, last: str) -> dict:
                asked.append((first, last))
                return super().__call__(first, last)

        rows = self.closes(25, start="2026-10-13T13:31:00Z", last="2026-10-25T13:31:00Z")
        m = self.meter(rows, now="2026-11-04T14:00:00Z", research=Asked())
        # The 15th close is Oct 20 13:31Z, the 20th Oct 23 01:31Z, the 25th Oct 25 13:31Z (one every 12 hours).
        self.assertEqual(asked, [("2026-10-18", "2026-10-20"), ("2026-10-21", "2026-10-23"), ("2026-10-24", "2026-10-25")])
        self.assertEqual([(cp["research_247"]["first_day"], cp["research_247"]["last_day"]) for cp in m["checkpoints"]],
                         asked)
        # A day that fails inside the 15th's window fails it alone; the 20th reads the days after it.
        m = self.meter(rows, now="2026-11-04T14:00:00Z", research=Research(failed={"2026-10-18"}))
        self.assertEqual([cp["items"]["7"] for cp in m["checkpoints"]], [False, True, True])
        m = self.meter(rows, now="2026-11-04T14:00:00Z", research=Research(failed={"2026-10-17"}))
        self.assertEqual([cp["items"]["7"] for cp in m["checkpoints"]], [True, True, True],
                         "a day before the 3: the 7-day window of the Oct 9 rule would have read it")


# ================================================================================================== the bar
class TheBar(Base):
    def rows(self, a: int, b: int, *, c: int = 0) -> list[dict]:
        """`a` closes of program A, then `b` of B and `c` of C, one every 12 hours from Oct 13, 2026 13:31Z."""
        names = ["prog-a"] * a + ["prog-b"] * b + ["prog-c"] * c
        t = ep("2026-10-13T13:31:00Z")
        rows = [options_close(100 + i, fam, dt.datetime.fromtimestamp(t + i * 43200, dt.timezone.utc).isoformat())
                for i, fam in enumerate(names)]
        return sorted(rows, key=R._order)

    def first(self, rows) -> dict:
        m = self.meter(rows, now="2026-11-04T14:00:00Z")
        self.assertEqual(m["checkpoints"][0]["at_close"], 15)
        return m["checkpoints"][0]

    def test_three_from_each_of_two_programs_meets_the_bar_and_two_does_not(self):
        cp = self.first(self.rows(12, 3))
        self.assertEqual((cp["programs_with_min_closes"], cp["items"]["3"]), (2, True))
        cp = self.first(self.rows(13, 2))
        self.assertEqual((cp["programs_with_min_closes"], cp["items"]["3"]), (1, False))
        self.assertIn("1 programs with 3+ closes of the 2 needed", cp["why"])

    def test_one_program_never_meets_the_bar_and_a_third_is_not_needed(self):
        cp = self.first(self.rows(15, 0))
        self.assertEqual((cp["programs"], cp["programs_with_min_closes"], cp["items"]["3"]), (1, 1, False))
        cp = self.first(self.rows(6, 6, c=3))
        self.assertEqual((cp["programs"], cp["programs_with_min_closes"], cp["items"]["3"]), (3, 3, True))

    def test_a1_1_is_unchanged_so_a_claim_still_needs_two_programs_with_five_matched_closes(self):
        """DONE-RULE-A1 A1.1 (pinned Oct 9, 2026) is not the owner's to have changed here: with 3 closes a program meets
        the bar (item 3) but is not a MEASURED program (5 matched closes), so item 4 fails until two programs have 5."""
        cp = self.first(self.rows(12, 3))
        self.assertEqual((cp["items"]["3"], cp["items"]["4"], cp["measured_programs"], cp["holds"]), (True, False, 1, False))
        self.assertIn("1 programs with 5+ matched closes of the 2 needed (DONE-RULE-A1 A1.1)", cp["why"])
        cp = self.first(self.rows(10, 5))
        self.assertEqual((cp["items"], cp["measured_programs"], cp["holds"]), ({"3": True, "4": True, "7": True}, 2, True))

    def test_the_sign_is_still_the_bar(self):
        rows = self.rows(10, 5)
        for row in rows:
            row["pnl_usd"] = row["cash_usd"] = R.Decimal("-0.01")
        cp = self.first(rows)
        self.assertEqual((cp["items"]["3"], cp["holds"]), (False, False))
        self.assertIn("not above $0", cp["why"])


# ================================================================================================== A14's intents
class TheIntentsBound(unittest.TestCase):
    def test_the_bound_by_hand(self):
        ok = forward_db.a14_intents_ok
        cases = {  # (agreed, S): ok
            (39, 39): True, (38, 39): True, (37, 39): False,            # S 39: one miss passes, two fail
            (40, 40): True, (39, 40): True, (38, 40): True, (37, 40): False,   # S 40: 38 = 0.95 x 40 passes, 37 fails
            (39, 41): True, (38, 41): False,                             # S 41: 0.95 x 41 = 38.95
            (19, 20): True, (18, 20): False,                             # S 20: the two clauses agree
            (18, 19): True, (17, 19): False,                             # S 19: one miss passes (failed under 95%)
            (1, 2): True, (0, 2): False, (0, 1): True, (1, 1): True,      # all but one, literally
            (57, 60): True, (56, 60): False,                             # from 40 on, 95% alone
        }
        for (agreed, sessions), want in cases.items():
            self.assertIs(ok(agreed, sessions), want, (agreed, sessions))
        self.assertIsNone(ok(0, 0), "no session: unmeasured, never held")
        self.assertIs(ok(18, 19, missing=1), False, "a session with no twin row is never the one forgiven")
        self.assertIs(ok(19, 20, missing=1), True, "the 95% reads the counted sessions as registered")

    def test_fw6s_range_reads_as_before(self):
        """FW6 (league/ops/forward_report.py) reads an instance's agreement from 20 sessions; there the owner's clause
        never moves the 95% bound, so FW6 fires exactly as it did."""
        for sessions in range(20, 301):
            for agreed in range(sessions + 1):
                self.assertEqual(forward_db.a14_intents_ok(agreed, sessions) is False, agreed < 0.95 * sessions,
                                 (agreed, sessions))


class TheIntentsReading(Reading):
    """`forward_twins.a14_reading` over one instance's sessions (league/tests/test_forward_a14.py's fixture)."""

    def read_s(self, sessions: int, misses: int, *, missing: int = 0) -> dict:
        return self.held(verdicts=(1,) * (sessions - misses - missing) + (0,) * misses + ("-",) * missing)

    def assert_reads(self, sessions: int, misses: int, ok: bool, by) -> None:
        out = self.read_s(sessions, misses)
        got = (out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["ok"], out["intents"]["ok_by"],
               out["holds"])
        self.assertEqual(got, (sessions, sessions - misses, ok, by, ok), (sessions, misses))
        self.assertEqual(out["intents"]["all_but_one_under"], 40)

    def test_s_39(self):
        self.assert_reads(39, 1, True, "share")              # 38 >= 37.05
        self.assert_reads(39, 2, False, None)                # 37: under 95%, and two misses

    def test_s_40(self):
        self.assert_reads(40, 1, True, "share")
        self.assert_reads(40, 2, True, "share")              # 38 = 0.95 x 40: the owner's ">= 95%"
        self.assert_reads(40, 3, False, None)                # 40 is not "fewer than 40": all but one does not apply

    def test_s_41(self):
        self.assert_reads(41, 2, True, "share")              # 39 >= 38.95
        self.assert_reads(41, 3, False, None)

    def test_under_20_one_miss_is_forgiven_by_the_owners_clause_alone(self):
        self.assert_reads(19, 1, True, "all_but_one")        # 18 < 18.05: failed before A50
        self.assert_reads(19, 2, False, None)
        self.assert_reads(5, 1, True, "all_but_one")
        out = self.read_s(19, 1)
        self.assertIsNone(out["why"])

    def test_a_missing_session_is_not_forgiven_and_holds_the_reading_from_final(self):
        out = self.read_s(19, 0, missing=1)
        self.assertEqual((out["intents"]["missing"], out["intents"]["ok"], out["holds"], out["final"]), (1, False, False, False))
        out = self.read_s(20, 0, missing=1)
        self.assertEqual((out["intents"]["ok"], out["intents"]["ok_by"], out["final"]), (True, "share", False),
                         "the 95% as registered: provisional until the row lands")

    def test_the_fill_gap_half_is_unchanged(self):
        out = self.held(gaps=(-16.0,), verdicts=(1,) * 18 + (0,))
        self.assertEqual((out["gap"]["ok"], out["intents"]["ok"], out["holds"]), (False, True, False))
        out = self.held(gaps=(15.0,), verdicts=(1,) * 18 + (0,))
        self.assertEqual((out["gap"]["ok"], out["holds"]), (True, True))

    def test_the_instances_are_pooled_into_one_s(self):
        self.twins(eq_1=priced(1.0), eq_2=priced(1.0))
        self.rows("fake-alpha@1:r", (1,) * 10 + (0,))
        self.rows("fake-beta@2:r", (1,) * 10, first=0)
        out = self.read([close(1, day=DAYS[11]), close(2, "fake-beta@2:r", day=DAYS[10])])
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["ok"],
                          out["intents"]["ok_by"]), (21, 20, True, "share"))


# ================================================================================================== item 7's window
def at(*stamps: str) -> list[dict]:
    return [{"closed_at": ep(s)} for s in stamps]


class TheResearchWindow(unittest.TestCase):
    def test_the_first_reads_the_3_utc_days_ending_on_its_close_day_across_a_weekend(self):
        # The 15th close on Monday Oct 19, 2026: Saturday, Sunday and Monday.
        rows = at(*["2026-10-14T15:00:00Z"] * 14, "2026-10-19T14:30:00Z")
        self.assertEqual(R.research_window(rows, 15, None), ("2026-10-17", "2026-10-19"))
        # On a Saturday: Thursday to Saturday (a weekend close is an options expiry booked late).
        rows = at(*["2026-10-14T15:00:00Z"] * 14, "2026-10-24T01:11:00Z")
        self.assertEqual(R.research_window(rows, 15, None), ("2026-10-22", "2026-10-24"))

    def test_utc_days_across_new_yorks_clock_change(self):
        # New York leaves daylight time on Sunday Nov 1, 2026 (a 25-hour day there); the window is three UTC days.
        rows = at(*["2026-10-30T15:00:00Z"] * 14, "2026-11-02T14:45:00Z")
        self.assertEqual(R.research_window(rows, 15, None), ("2026-10-31", "2026-11-02"))
        # And entering it, Sunday Mar 14, 2027.
        rows = at(*["2027-03-12T15:00:00Z"] * 14, "2027-03-15T13:45:00Z")
        self.assertEqual(R.research_window(rows, 15, None), ("2027-03-13", "2027-03-15"))

    def test_a_close_after_midnight_utc_reads_its_utc_day(self):
        # Monday evening in New York, 01:11Z Tuesday: the window ends on Tuesday, the close's UTC day.
        rows = at(*["2026-10-14T15:00:00Z"] * 14, "2026-10-20T01:11:00Z")
        self.assertEqual(R.research_window(rows, 15, None), ("2026-10-18", "2026-10-20"))

    def test_a_later_checkpoint_reads_every_day_after_the_previous_ones_through_its_own(self):
        stamps = ["2026-10-14T15:00:00Z"] * 14 + ["2026-10-19T14:30:00Z"] + ["2026-10-21T15:00:00Z"] * 4 + \
                 ["2026-10-23T19:59:00Z"] + ["2026-10-23T20:00:00Z"] * 4 + ["2026-10-26T14:00:00Z"]
        rows = at(*stamps)
        self.assertEqual(R.research_window(rows, 20, 15), ("2026-10-20", "2026-10-23"))
        self.assertEqual(R.research_window(rows, 25, 20), ("2026-10-24", "2026-10-26"), "across the weekend")
        same = at(*["2026-10-14T15:00:00Z"] * 14, "2026-10-19T14:30:00Z", *["2026-10-19T15:00:00Z"] * 5)
        self.assertEqual(R.research_window(same, 20, 15), ("2026-10-19", "2026-10-19"),
                         "two checkpoints on one UTC day: the later reads that day")

    def test_the_reports_running_view_keeps_its_seven_days(self):
        self.assertEqual(R.RESEARCH_BESIDE_DAYS, 7, "done.research_247_last_7_days: beside the meters, never a reading")


# ================================================================================================== another rule's reading
class AReadingUnderAnotherRule(Fixture):
    def thirty(self) -> None:
        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        for _ in range(15):
            self.close("dir-a", pnl=5.0)
            self.close("dir-b", pnl=5.0)
        self.replays("dir-a", ["2026-10-05"])
        self.replays("dir-b", ["2026-10-05"])
        self.steady()
        self.posted()

    def test_is_never_carried_and_does_not_silence_a8(self):
        self.thirty()
        first = self.report(settings=NIGHTLY)
        cps = first["done"]["screen"]["checkpoints"]
        self.assertEqual([(cp["at_close"], cp["final"], cp["holds"]) for cp in cps],
                         [(15, True, True), (20, True, True), (25, True, True), (30, True, True)])
        self.assertEqual(first["rule"]["sha256"], dlane.DONE["rule_sha256"])
        self.assertEqual(first["rule"]["research_first_days"], 3)
        # Under the same rule: frozen and said once.
        same = self.report(settings=NIGHTLY, previous=first)
        self.assertTrue(all(cp.get("frozen") for cp in same["done"]["screen"]["checkpoints"]))
        self.assertNotIn("A8", [a["id"] for a in same["alarms"]])
        # The same report as if written under the Oct 9 rule: nothing of it is carried, and A8 says each checkpoint.
        old = json.loads(json.dumps(first, default=str))
        old["rule"]["sha256"] = dlane.OLD_DONE["rule_sha256"]
        fresh = self.report(settings=NIGHTLY, previous=old)
        self.assertFalse(any(cp.get("frozen") for meter in ("all", "screen") for cp in fresh["done"][meter]["checkpoints"]))
        self.assertEqual(len([a for a in fresh["alarms"] if a["id"] == "A8"]), 8, "4 checkpoints a meter, said afresh")

    def test_the_running_view_of_item_7_is_seven_days(self):
        out = self.report()
        view = out["done"]["research_247_last_7_days"]
        self.assertEqual((view["first_day"], view["last_day"]), ("2026-10-13", "2026-10-19"))


if __name__ == "__main__":
    unittest.main()
