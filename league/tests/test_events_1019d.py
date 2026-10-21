"""RELEASE 1019d: PREREG-EVL-4's programs (`feat/evl-4`, #579) merged onto release 1019c (A69's fast path to a final
record, A74 (5)'s look-group freeze, A79's withdrawal of A74 (6)). Held here, on the synthetic week of PREREG-EVL-4's
tests (league/tests/evl4_world.py, invented rows only), what neither side held alone:

- A WRITTEN LOOK OF A PREREG-EVL-4 GROUP (EVL-8K-READ-ON with its control EVL-CTRL-8K-ON; EVL-NEWSPM-READ-ON with
  EVL-CTRL-NEWSPM-ON; EVL-8K-REACT-ON alone) freezes the group in a re-decision of its close, whole or PREREG-EVL-4's
  rows decided by themselves (`evl4_only`): asked nothing, written nothing (no intent, no `skipped:excluded` move),
  each event its rule would take named as left out; every other group of the close decided as before;
- A RECEIPT THAT KEPT A PREREG-EVL-4 PROGRAM NAMES IT (league/events/screen.py `names`): its close is made for it
  (`final_until`, `made_without`), as release 1019c's `_waits_on` reads a kept program's, so the freeze never holds
  the next look back and no `decide-close-evl4` is run again for it;
- THE VERDICT TALLY counts PREREG-EVL-4's rows' verdicts (the stall job's `evl_verdicts` sees their wait, as it saw
  their `pending` before the tally);
- THE DAILY REPORT counts what PREREG-EVL-4's own decision (`decide-close-evl4`) kept out."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from league.events import calendar as C
from league.events import report as RP
from league.events import run as R
from league.events import screen as SC
from league.events import store as S
from league.ops import evl_health as EH
from league.tests import evl4_world as W

D, PRIOR, NEXT = W.D_DAY, W.P_DAY, W.N_DAY
et = W.et
JJJ_8K = "0000000010-26-000001"     # an 8.01 8-K of JJJ on D, stored after D's close decision (the late row)
BBB_ERN = "0000000002-26-000009"    # an earnings 8-K of BBB on D, stored late: EXCLUDES BBB on D (ERN(D))


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = W.World(Path(self.tmp.name) / "lane")
        self.addCleanup(self.w.close)
        self.st = self.w.st

    def rows(self, program: str, day: dt.date = D) -> list[tuple]:
        return [tuple(r) for r in self.st.db.execute("SELECT event, symbol, status, why FROM intents WHERE program=? AND "
                                                     "version=1 AND entry_day=? ORDER BY event",
                                                     (program, day.isoformat()))]

    def look(self, program: str, as_of: dt.date = NEXT) -> None:
        """A written look of `program` (version 1, its seating version) as of `as_of`'s close: D's intents of a close
        entry exit at NEXT's open, so a look as of NEXT covers them (league/events/run.py `_scope`)."""
        self.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES(?, 1, 1, ?, 1, 0)",
                           (program, S.iso(C.session(self.st, as_of).close_at)))

    def late_rows(self) -> None:
        """Two rows of D stored after D's close decision: JJJ's 8.01 8-K (F8K(D): every 8-K row's rule takes it; JJJ's
        T29 minute closes at 1.06 x) and BBB's earnings 8-K (ERN(D): it EXCLUDES BBB, whose F8K(D) intents are planned).
        JJJ's T29 mark is stored as the decision's own read would store it, so a kept program reads it without a fetch."""
        self.w.filing(JJJ_8K, "JJJ", accepted=et(D, 12, 30), items=("8.01",), stored=et(D, 16, 20))
        self.w.filing(BBB_ERN, "BBB", accepted=et(D, 13, 30), items=("2.02",), stored=et(D, 16, 20))
        self.st.db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('JJJ', ?, "
                           "'1530', 21.2, 'x', 'sip-1min', 'x')", (D.isoformat(),))

    def latest(self, job: str) -> tuple[str, dict]:
        row = self.st.db.execute("SELECT status, summary FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                                 (job,)).fetchone()
        return str(row["status"]), json.loads(row["summary"])


class ALookFreezesAPreregFourGroup(Case):
    def test_a_whole_redecision_keeps_the_group_and_decides_every_other(self):
        """A look of EVL-8K-READ-ON over D: a whole re-decision of D's close keeps it and its control (both asked and
        written nothing: JJJ's late 8-K lands in neither, BBB's planned intents are NOT moved to skipped:excluded by
        BBB's late earnings 8-K), names JJJ as left out of each, and decides EVL-8K-REACT-ON (its own group) whole:
        it takes JJJ. Its receipt names the kept two, so D's close is made for them: no look waits on it and no
        `decide-close-evl4` is due."""
        W.the_week(self.w)
        before = {p: self.rows(p) for p in ("EVL-8K-READ-ON", "EVL-CTRL-8K-ON")}
        self.assertIn(("8k:0000000002-26-000001", "BBB", "planned", None), before["EVL-8K-READ-ON"])
        self.look("EVL-8K-READ-ON")
        self.late_rows()
        asked = len(self.w.gw.claude_calls)
        out = self.w.at(et(NEXT, 17, 0)).decide("close", D, live=False)
        self.assertEqual(sorted(out["kept"]), ["EVL-8K-READ-ON", "EVL-CTRL-8K-ON"])
        for key in out["kept"]:
            self.assertEqual(out["kept"][key]["why"], "a look of its group is written over this session "
                                                      f"(EVL-8K-READ-ON look 1 as of {NEXT.isoformat()})")
            self.assertEqual(self.rows(key), before[key], f"{key}: nothing written, nothing moved")
        self.assertEqual(out["kept"]["EVL-CTRL-8K-ON"]["events"], [f"8k:{JJJ_8K}"], "the control's rule takes JJJ")
        self.assertEqual(out["kept"]["EVL-8K-READ-ON"]["unjudged"], [f"8k:{JJJ_8K}"],
                         "no verdict stored for JJJ, and none asked for a kept program")
        self.assertNotIn("doc:JJJ", self.w.gw.asked()[asked:], "a kept program is asked nothing")
        self.assertIn(f"8k:{JJJ_8K}", {r[0] for r in self.rows("EVL-8K-REACT-ON") if r[2] == "planned"},
                      "another group of the same file is decided whole")
        self.assertNotIn("EVL-8K-REACT-ON", out["kept"])
        status, summary = self.latest(f"decide-close:{D.isoformat()}")
        self.assertEqual(status, "ok")
        for key in ("EVL-8K-READ-ON", "EVL-CTRL-8K-ON"):
            self.assertNotIn(key, summary)
            self.assertTrue(SC.names(summary, key), f"{key}: kept is named")
            self.assertFalse(SC._waits_on(status, json.dumps(summary), key))
        self.assertEqual(SC.made_without(self.st, NEXT), {}, "made for every program of PREREG-EVL-4")
        final, why = SC.final_until(self.st, "EVL-8K-READ-ON", 1, NEXT, et(NEXT, 17, 5))
        self.assertNotIn("made without its rows", why)

    def test_their_own_decision_keeps_the_group_and_its_receipt_makes_the_close(self):
        """D's close decided last by a release without PREREG-EVL-4's rows (its receipt names none of them), and a look
        of EVL-NEWSPM-READ-ON's control over D: their own decision (`evl4_only`) keeps EVL-NEWSPM-READ-ON and its
        control, decides the 8-K rows, and its receipt makes D's close for all five; no earlier row is decided."""
        W.the_week(self.w)
        rid = self.st.start_receipt(f"decide-close:{D.isoformat()}", now=et(NEXT, 16, 50))
        self.st.finish_receipt(rid, "ok", {"pending": {}}, now=et(NEXT, 16, 51))      # a release without the rows
        self.assertEqual(SC.made_without(self.st, NEXT), {D: False})
        before = {p: self.rows(p) for p in ("EVL-NEWSPM-READ-ON", "EVL-CTRL-NEWSPM-ON")}
        earlier = [tuple(r) for r in self.st.db.execute("SELECT * FROM intents WHERE program NOT IN (?, ?, ?, ?, ?) "
                                                        "ORDER BY program, version, event", W_FOUR)]
        self.look("EVL-CTRL-NEWSPM-ON")
        self.late_rows()
        self.w.now = et(NEXT, 17, 0)
        out = R.decide_close(self.w.ctx, D, backfill_run=True, evl4_only=True)
        self.assertEqual(sorted(out["kept"]), ["EVL-CTRL-NEWSPM-ON", "EVL-NEWSPM-READ-ON"])
        for key, rows in before.items():
            self.assertEqual(self.rows(key), rows, key)
        self.assertEqual(out["skipped_excluded"], 2, "BBB's planned READ-ON and CTRL-8K-ON intents: not frozen")
        self.assertEqual(self.rows("EVL-8K-READ-ON")[0][:3], ("8k:0000000002-26-000001", "BBB", "skipped:excluded"))
        status, summary = self.latest(f"decide-{SC.FOUR_KIND}:{D.isoformat()}")
        self.assertEqual(status, "ok")
        self.assertEqual(SC.made_without(self.st, NEXT), {}, "their own decision made the close for all five")
        for program in W_FOUR:
            self.assertTrue(SC.names(summary, program), program)
            _, why = SC.final_until(self.st, program, 1, NEXT, et(NEXT, 17, 5))
            self.assertNotIn("made without its rows", why, program)
        self.assertEqual([tuple(r) for r in self.st.db.execute("SELECT * FROM intents WHERE program NOT IN (?, ?, ?, ?, ?) "
                                                               "ORDER BY program, version, event", W_FOUR)], earlier,
                         "no earlier row is decided by it")
        kept = RP.program_status(self.st, "EVL-CTRL-NEWSPM-ON", 1, D)["kept_out"]
        self.assertEqual(kept, {"events": 0, "unjudged": 0}, "no late PM row: nothing left out")
        self.assertEqual(RP.kept_out(self.st, D).keys(), {"EVL-NEWSPM-READ-ON", "EVL-CTRL-NEWSPM-ON"},
                         "the report reads `decide-close-evl4`'s kept entries too")

    def test_without_kept_in_names_the_freeze_would_hold_the_look_for_ever(self):
        """The merge's one reading of the judge (release 1019d): a receipt whose only mention of a PREREG-EVL-4 program
        is under `kept` names it. Read without it, the close a freeze kept would be 'made without its rows' for good:
        `decide-close-evl4` finds it kept again, and the program's next look would never be computed."""
        summary = {"pending": {}, "kept": {"EVL-8K-READ-ON": {"why": "x", "look": "y", "events": [], "unjudged": []}}}
        self.assertTrue(SC.names(summary, "EVL-8K-READ-ON"))
        self.assertTrue(SC.names(json.dumps(summary), "EVL-8K-READ-ON"))
        self.assertFalse(SC.names(summary, "EVL-8K-REACT-ON"))
        self.assertFalse(SC.names({"pending": {}, "kept": ["EVL-8K-READ-ON"]}, "EVL-8K-READ-ON"), "only a mapping")
        self.assertFalse(SC.names({"why": "cut"}, "EVL-8K-READ-ON"))


W_FOUR = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON", "EVL-CTRL-8K-ON", "EVL-CTRL-NEWSPM-ON")


class RefusingGateway(W.Gateway):
    """The synthetic gateway, with Claude refusing every PROMPT-DOC verdict of CCC."""

    def post_json(self, path, body, headers=None):
        if "(ticker CCC)" in body["messages"][0]["content"]:
            self.claude_calls.append(body)
            return 400, {"error": "invented refusal"}
        return super().post_json(path, body, headers)


class TheTallyCountsPreregFour(unittest.TestCase):
    def test_a_wait_of_its_rows_reaches_the_stall_jobs_tally(self):
        """CCC's 1.01 8-K on D: EVL-8K-READ-ON waits for its PROMPT-DOC verdict, which Claude refuses. The close
        decision's receipt is pending on it AND its tally counts it unanswered (no earlier close row needs that
        verdict), so `evl_verdicts` holds the decision; before the merge the tally said 0 of 0."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        w = W.World(Path(tmp.name) / "lane", RefusingGateway())
        self.addCleanup(w.close)
        w.filing("0000000003-26-000001", "CCC", accepted=et(D, 11, 0), items=("1.01", "9.01"))
        w.at(et(D, 9, 15, 30)).decide("open", D)
        out = w.at(et(D, 15, 47)).decide("close", D)
        self.assertEqual(out["pending"], {"EVL-8K-READ-ON": 1})
        self.assertEqual(out["verdicts"], {"needed": 1, "answered": 0})
        row = dict(w.st.db.execute("SELECT * FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                                   (f"decide-close:{D.isoformat()}",)).fetchone())
        self.assertEqual(EH.tally(row), (1, 1))


if __name__ == "__main__":
    unittest.main()
