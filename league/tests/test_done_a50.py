"""THE OWNER'S CHANGE OF THE PINNED DONE RULE (A50, the goal of Oct 16, 2026, 02:10Z; goal-2026-10-10/GOAL-MESSAGE-
SPEED.txt; the captain's amendment A50), each new rule at its edges:

- THE PIN: docs/goals/DONE-RULE-A50.md is the pinned rule (`dlane.DONE["rule_sha256"]`), holding the owner's Done
  verbatim; the Oct 9 rule is `dlane.OLD_DONE`, history read by no module.
- THE SCHEDULE: checkpoints at the 15th counted close, then every 5th (20, 25, 30, ...), fixed by count.
- THE BAR: at least 15 closes, at least 3 from each of at least 2 programs (14 vs 15; 2 vs 3; one program vs two).
  DONE-RULE-A1 A1.1 as the captain's A50a(2) changed it: a claim needs 2 programs with 3 or more matched closes each
  (5 before; 3 closes with 2 matched is not a measured program).
- A14'S INTENTS: agreed >= 0.95 x S, or S < 40, none missing, and agreed >= S - 1 (S 19, 39, 40, 41, 1; a missing
  session is never the one forgiven; FW6's range, 20 sessions and up, reads exactly as before).
- ITEM 7'S WINDOW: the 3 UTC days ending on the UTC day of the 15th close (across a weekend, across New York's clock
  change, a close after 00:00Z); each later checkpoint every UTC day after the previous one's through its own.
- A READING UNDER ANOTHER PINNED RULE is never carried into this one's checkpoints, and does not silence A8.
- P(DONE | ZERO EDGE) UNDER THE RULE IN FORCE (DONE-RULE-A50 item 6, the reviews of Oct 16): stated only from a
  `dlane.done_zero_edge_p` block measured under this rule's sha; otherwise "not yet measured", with the Oct 9 rule's
  0.027 beside it, labelled so, and never as the figure.

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
from league.tests.test_dlane_report_dc1 import ALL, Base, Research, ep, options_close
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
        # The captain's A50a(2) (A1.1 at 3) and the reviews' item 6 (the zero-edge figure measured under this rule) are
        # in the pinned file, so its sha moved from the build's first draft (9693fe00, never deployed) to this one.
        self.assertEqual(dlane.DONE["rule_sha256"], "027c12b7cca3f4450b3eee92957dc8c2d6e28a8db9b81625c2ba323528db2491")
        text = words(RULE_FILE.read_text())
        self.assertIn(OWNERS_DONE, text)
        # A1 stood whole in the first draft; since A50a(2) it stands but for A1.1's count, which is 3.
        for said in ("replaces DONE-RULE.md (sha256 0d007696",
                     "DONE-RULE-A1.md (sha256 333bad06, A1.1-A1.4) stands but for A1.1's count of matched closes, which "
                     "the captain's A50a(2) makes 3 (was 5",
                     "Every program with 3 or more matched closes has a gap within +/-0.10",
                     "a program's replay gap is judged on 3 closes instead of 5; for ETF lots the +/-0.10 of max loss is "
                     "far looser than A14's 15 bp",
                     "P(Done | zero edge) under the rule in force is not yet measured",
                     "fixed by count", "optional stopping", "near a coin flip at zero edge"):
            self.assertIn(said, text)
        self.assertNotIn("stands whole", text)
        self.assertNotIn("5 or more matched closes has a gap", text)

    def test_the_owners_constants_and_everything_else_as_it_was(self):
        rule = dlane.DONE
        self.assertEqual((rule["min_closes"], rule["min_programs"], rule["min_closes_per_program"]), (15, 2, 3))
        self.assertEqual((rule["first_checkpoint"], rule["checkpoint_every"], rule["research_first_days"]), (15, 5, 3))
        # Unchanged: the routes, the inception, A1's sha, its 2 measured programs and the gap. A1.1's matched closes are 3
        # since the captain's A50a(2) (5 would block the 15th close in about 92% of paths): this pinned 5 before it.
        self.assertEqual((rule["routes_all"], rule["routes_screen"], rule["inception"]),
                         ((":r", ":t", ":i"), (":r",), "2026-09-26T06:23:00Z"))
        self.assertEqual((rule["gap_limit"], rule["gap_min_matched"], rule["min_measured_programs"]), (0.10, 3, 2))
        self.assertEqual(rule["amendment_sha256"], "333bad0679fb9c9a76c1cc0b5248d52c5f84c96e0cff5376f9c8d446a4c4ff0b")
        self.assertEqual(R.DONE_FROM, "2026-10-10T04:00:00Z")
        self.assertEqual((forward_db.A14_GAP_BP, forward_db.A14_AGREE, forward_db.A14_ALL_BUT_ONE_UNDER), (15.0, 0.95, 40))
        self.assertEqual((R.A14_GAP_BP, R.A14_AGREEMENT, R.A14_ALL_BUT_ONE_UNDER),
                         (forward_db.A14_GAP_BP, forward_db.A14_AGREE, forward_db.A14_ALL_BUT_ONE_UNDER))

    def test_the_old_rule_is_kept_visible_and_read_by_nothing(self):
        # The history keeps A1.1's 5 since A50a(2) made it 3 (`gap_min_matched`), and names the Oct 9 sha once.
        self.assertEqual(dlane.OLD_DONE, {"rule_sha256": "0d007696c9a6a1cbbd7d2cc345811359ab1cec389cf88f75ceff295bbbc48dca",
                                          "min_closes": 30, "min_closes_per_program": 5, "first_checkpoint": 30,
                                          "checkpoint_every": 10, "research_first_days": 7, "gap_min_matched": 5})
        self.assertEqual(dlane.OCT9_RULE_SHA256, dlane.OLD_DONE["rule_sha256"])
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
        # Five rows since the captain's A50a(2) (A1.1's matched closes, 5 -> 3) joined the owner's four.
        self.assertEqual([row["rule"] for row in R.LOOSENED[-5:]],
                         ["Done's checkpoints (A50, the owner's goal of Oct 16)", "Done's bar (A50, the owner's goal of Oct 16)",
                          "A14's intents bound (A50, the owner's goal of Oct 16)",
                          "Done's research 24/7 window (A50, the owner's goal of Oct 16)",
                          "A1.1's matched replay closes (the captain's A50a(2), Oct 16)"])
        rows = {row["rule"]: row for row in R.LOOSENED[-5:]}
        self.assertTrue(all(set(row) == {"rule", "was", "now", "cost"} for row in rows.values()))
        checkpoints, bar, intents, window, a1_1 = rows.values()
        self.assertIn("a program's replay gap is judged on 3 closes instead of 5; for ETF lots the +/-0.10 of max loss is "
                      "far looser than A14's 15 bp", a1_1["cost"])
        self.assertIn("5 or more matched replay closes", a1_1["was"])
        self.assertIn("gap_min_matched 3", a1_1["now"])
        self.assertIn("3+ since the captain's A50a(2)", " ".join(R.TIGHTENED))
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

    def test_a1_1_at_3_so_a_program_with_3_matched_closes_is_measured(self):
        """DONE-RULE-A1 A1.1 as the captain's A50a(2) changed it (02:31Z Oct 16, 2026): 2 programs with 3 or more
        matched closes each. This test held 5 before A50a(2) (12+3 failed item 4 there, 1 measured program): 5 would
        block the 15th close in about 92% of paths and contradict the owner's ">= 3 each"."""
        cp = self.first(self.rows(12, 3))
        self.assertEqual((cp["items"], cp["measured_programs"], cp["holds"]), ({"3": True, "4": True, "7": True}, 2, True))
        cp = self.first(self.rows(10, 5))
        self.assertEqual((cp["items"], cp["measured_programs"], cp["holds"]), ({"3": True, "4": True, "7": True}, 2, True))

    def test_3_closes_with_2_matched_is_not_a_measured_program(self):
        """A close whose twin is final but unpriced is counted by its verdict, never matched: program B then meets the
        bar on 3 closes (item 3) but has 2 matched, under A1.1's 3, so item 4 fails and the checkpoint is final."""
        rows = self.rows(12, 3)
        last_b = [c for c in rows if c["family"] == "prog-b"][-1]
        twins = {str(c["pid"]): {"status": "priced", "final": True,
                                 "twin": {"pnl": float(c["pnl_usd"]), "max_loss": c["max_loss_usd"], "r": 0.0}}
                 for c in rows}
        twins[str(last_b["pid"])] = {"status": "no_fill", "final": True}   # the model did not fill the real open
        m = R.meter(rows, ALL, self.store, previous=None, research=Research(), replay_days={}, fees_as_of="2026-12-31",
                    now=ep("2026-11-04T14:00:00Z"), twins=twins, twins_on=False)
        cp = m["checkpoints"][0]
        self.assertEqual((cp["at_close"], cp["items"]["3"], cp["items"]["4"], cp["measured_programs"], cp["holds"]),
                         (15, True, False, 1, False))
        self.assertIn("1 programs with 3+ matched closes of the 2 needed (DONE-RULE-A1 A1.1)", cp["why"])

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



# ================================================================================================== P(Done | zero edge)
#: The sentence the report says while no figure measured under the rule in force is set (the task of the reviews' fix).
UNMEASURED = ("P(Done | zero edge) under the rule in force is not yet measured (the 0.027 beside it was simulated under "
              "the Oct 9 rule)")
FIRST_DRAFT = "9693fe0034926fda43270668fbaa40eecb3e8645022ec14fcd6ca94d61980eef"   # this build's first draft, never deployed


def measured(**over) -> dict:
    """A measured block for `dlane.done_zero_edge_p` (an invented figure and source)."""
    return {"value": 0.21, "horizon": "Fri Oct 23, 2026", "source_sha256": "ab" * 32,
            "measured_under": dlane.DONE["rule_sha256"], **over}


def figures(node, path=""):
    """Every (path, number) in a nested report block."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from figures(v, f"{path}.{k}")
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield path, node


class TheZeroEdgeFigure(unittest.TestCase):
    """DONE-RULE-A50 item 6: P(Done | zero edge) rides with every claim, and under the rule in force it is the figure
    measured under it or nothing. Every figure in `dlane.ZERO_EDGES` was simulated under the Oct 9 rule (30 closes, 5
    each, read every 10th): stated beside, labelled so, never as the figure for A50's rule."""

    def test_unmeasured_says_so_plainly_and_0_027_rides_only_beside(self):
        for settings in (None, {"dlane": {"mode": "gate"}}, {"dlane": {"mode": "gate", "done_zero_edge_p": 0.027}}):
            out = R.zero_edge(settings)
            self.assertEqual((out["measured"], out["value"], out["note"]), (False, None, UNMEASURED), settings)
            self.assertEqual((out["label"], out["rule_sha256"]), (R.ZERO_EDGE_LABEL, dlane.DONE["rule_sha256"]))
            self.assertNotIn("refused", out, "no block was written")
            beside = out["beside"]
            self.assertEqual((beside["value"], beside["by"], beside["measured_under"]),
                             (0.027, dlane.ZERO_EDGE["by"], dlane.OCT9_RULE_SHA256))
            self.assertEqual(beside["rule"], "the Oct 9 rule (DONE-RULE.md), not the rule in force")
            self.assertEqual([p for p, v in figures(out) if v == 0.027], [".beside.value"], "0.027 is never the figure")
        self.assertTrue(all(z["measured_under"] == dlane.OCT9_RULE_SHA256 for z in dlane.ZERO_EDGES.values()))
        self.assertNotEqual(dlane.OCT9_RULE_SHA256, dlane.DONE["rule_sha256"])

    def test_a_block_measured_under_the_rule_in_force_is_stated(self):
        out = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": measured()}})
        self.assertEqual({k: out[k] for k in ("measured", "value", "horizon", "source_sha256", "measured_under")},
                         {"measured": True, "value": 0.21, "horizon": "Fri Oct 23, 2026", "source_sha256": "ab" * 32,
                          "measured_under": dlane.DONE["rule_sha256"]})
        self.assertNotIn("note", out)
        self.assertNotIn("refused", out)
        self.assertEqual(out["beside"]["value"], 0.027, "the Oct 9 rule's figure stays beside, labelled")
        self.assertEqual(R.zero_edge({"dlane": {"done_zero_edge_p": measured(value=0)}})["value"], 0.0)

    def test_a_block_measured_under_another_rule_is_never_stated(self):
        for other in (dlane.OCT9_RULE_SHA256, FIRST_DRAFT, "cd" * 32):
            out = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": measured(measured_under=other)}})
            self.assertEqual((out["measured"], out["value"], out["note"]), (False, None, UNMEASURED), other)
            self.assertIn(f"measured under the rule {other[:8]}, not the rule in force", out["refused"])
            self.assertNotIn(0.21, [v for _, v in figures(out)], "the other rule's figure is not stated at all")

    def test_a_malformed_block_is_never_stated(self):
        for bad in (measured(value=1.5), measured(value=True), measured(value="0.21"), measured(value=float("nan")),
                    measured(horizon=""), measured(horizon=None), measured(source_sha256="ab"),
                    measured(measured_under=dlane.DONE["rule_sha256"].upper()), {"value": 0.21}):
            out = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": bad}})
            self.assertEqual((out["measured"], out["value"], out["note"]), (False, None, UNMEASURED), bad)
            self.assertIn("block is malformed", out["refused"])
            self.assertEqual(out["beside"]["value"], 0.027, "a block takes the number's place: the default beside")
            self.assertIn("refused", dlane.cfg({"dlane": {"done_zero_edge_p": bad}})["done_zero_edge_measured"])
        self.assertIsNone(dlane.cfg({"dlane": {"done_zero_edge_p": 0.027}})["done_zero_edge_measured"])

    def test_a_setting_number_is_beside_and_never_the_figure(self):
        out = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": 0.13}})
        self.assertEqual((out["measured"], out["value"]), (False, None))
        self.assertEqual(out["note"], "P(Done | zero edge) under the rule in force is not yet measured (the 0.13 beside it "
                                      "is a setting's figure, under no rule this code names)")
        self.assertEqual(out["beside"]["value"], 0.13)
        self.assertNotIn("measured_under", out["beside"])
        rolled = R.zero_edge({"dlane": {"mode": "gate", "done_zero_edge_p": 0.024}})
        self.assertEqual((rolled["value"], rolled["beside"]["value"], rolled["beside"]["measured_under"]),
                         (None, 0.024, dlane.OCT9_RULE_SHA256))
        self.assertEqual(rolled["note"], UNMEASURED.replace("0.027", "0.024"))

    def test_the_equity_note_rides_on_the_options_figure_beside(self):
        out = R.zero_edge(None, equity_closes=2)
        self.assertEqual((out["beside"]["applies_to"], out["beside"]["equity_closes"], out["beside"]["equity_note"]),
                         ("the options Probe rules only", 2, R.ZERO_EDGE_EQUITY_NOTE))
        self.assertNotIn("equity_note", out, "the measured figure, when there is one, is not the options rules' only")

    def test_a_block_may_be_the_code_default(self):
        """A later release may ship the measured block in `DEFAULTS` itself: the number beside then falls back to
        `ZERO_EDGE`'s, and the block is read when no layer sets the key."""
        from unittest import mock

        with mock.patch.dict(dlane.DEFAULTS, {"done_zero_edge_p": measured()}):
            c = dlane.cfg({"dlane": {"mode": "gate"}})
            self.assertEqual((c["done_zero_edge_p"], c["done_zero_edge_measured"]["value"]), (0.027, 0.21))
            self.assertTrue(R.zero_edge(None)["measured"])
            self.assertFalse(R.zero_edge({"dlane": {"done_zero_edge_p": 0.027}})["measured"], "a layer's number wins")

    def test_the_settings_layers_carry_a_block(self):
        """The block may sit in policy.json (its shape check reads no `dlane` key) or in the box's swarm.json over the
        number; a number in swarm.json over a policy block is the number again (said in docs/operations.md)."""
        import tempfile

        from league.swarm import settings as S

        policy = json.loads((REPO / "league" / "swarm" / "policy.json").read_text())
        self.assertEqual(policy["dlane"]["done_zero_edge_p"], 0.027, "the repository ships the number: not measured")
        with_block = json.loads(json.dumps(policy))
        with_block["dlane"]["done_zero_edge_p"] = measured()
        self.assertEqual(S.policy_layer(with_block)[1]["state"], "ok")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(R.zero_edge(S.load(tmp, policy=with_block))["measured"])
            self.assertFalse(R.zero_edge(S.load(tmp, policy=policy))["measured"])
            (Path(tmp) / "swarm.json").write_text(json.dumps({"dlane": {"done_zero_edge_p": measured()}}))
            self.assertEqual(R.zero_edge(S.load(tmp, policy=policy))["value"], 0.21)
            (Path(tmp) / "swarm.json").write_text(json.dumps({"dlane": {"done_zero_edge_p": 0.027}}))
            self.assertFalse(R.zero_edge(S.load(tmp, policy=with_block))["measured"])


class TheZeroEdgeInTheReport(Fixture):
    """The `dlane` job's report, written: `done.p_done_zero_edge` from the box's settings."""

    def run_report(self, **dlane_extra) -> dict:
        from types import SimpleNamespace

        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"mode": "gate", **dlane_extra}}))
        self.fam("dir-a", lane="direction")
        self.close("dir-a", pnl=-10.0)
        out = R.run(SimpleNamespace(root=self.root, now=lambda: self.now, config={}, alert=lambda level, text: None))
        self.assertTrue(out["ok"])
        return json.loads((self.root / R.FILE).read_text())["done"]["p_done_zero_edge"]

    def test_not_yet_measured_in_the_report_as_shipped(self):
        zero = self.run_report()
        self.assertEqual((zero["measured"], zero["value"], zero["note"], zero["beside"]["value"]),
                         (False, None, UNMEASURED, 0.027))

    def test_measured_under_the_rule_in_force_in_the_report(self):
        zero = self.run_report(done_zero_edge_p=measured())
        self.assertEqual((zero["measured"], zero["value"], zero["horizon"], zero["measured_under"]),
                         (True, 0.21, "Fri Oct 23, 2026", dlane.DONE["rule_sha256"]))

    def test_measured_under_the_first_draft_is_not_stated_in_the_report(self):
        zero = self.run_report(done_zero_edge_p=measured(measured_under=FIRST_DRAFT))
        self.assertEqual((zero["measured"], zero["value"], zero["note"]), (False, None, UNMEASURED))


if __name__ == "__main__":
    unittest.main()
