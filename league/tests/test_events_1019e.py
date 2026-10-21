"""RELEASE 1019e: the captain's A83 (3), release 1019d's review minors, and the births' group freeze, on the synthetic
week of PREREG-EVL-4's tests (league/tests/evl4_world.py, invented rows only) and R3's invented store:

- A83 (3)(i) PREREG-EVL-4'S PART OF A CLOSE DECISION IS ISOLATED (league/events/run.py `decide_close`): an exception in
  it that is not the task's time bound finishes the decision with the earlier rows' results (their intents exactly as
  with no failure, the receipt `ok`), records it in `evl4_error`, and names none of PREREG-EVL-4's programs, so the judge
  reads the close as made without their rows (league/events/screen.py `names`, `made_without`) and their own decision
  (`decide-close-evl4`) decides them; a time bound (`run.Deadline`, the House's `LaneDeadline`) still stops the task,
  and their own decision's failure is its own;
- A83 (3)(ii) THE PM ROWS' VERDICTS ARE ASKED WHEN EVL-NEWS-READ-O1'S GROUP IS FROZEN: a written look of that group
  over D (A74 (5)) leaves D's open decision asking nothing, so D's close decision asks the PROMPT-NEWS verdicts its PM
  rows need, with the same stored prompt and the article rendered as the open decision renders it, each stored once;
  the frozen group itself is asked nothing and written nothing; with no freeze the close decision asks none (1019d);
- A74 (5) FOR R3'S BIRTHS: a READ birth's group is the birth and its derived control (league/events/run.py `_group`);
  every PREREG id's group is its table's alone."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import calendar as C
from league.events import programs as P
from league.events import run as R
from league.events import screen as SC
from league.events import store as S
from league.events import verdicts as V
from league.tests import evl4_world as W

D, PRIOR, NEXT = W.D_DAY, W.P_DAY, W.N_DAY
et = W.et
FOUR = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON", "EVL-CTRL-8K-ON", "EVL-CTRL-NEWSPM-ON")


def rows_of_the_week(w: W.World) -> None:
    """The invented rows of `evl4_world.the_week`, without its decisions (and without HHH's late earnings 8-K)."""
    w.filing("0000000001-26-000001", "AAA", accepted=et(PRIOR, 16, 30), items=("2.02", "7.01"))
    w.filing("0000000001-26-000002", "AAA", accepted=et(D, 11, 0), items=("8.01",))
    w.filing("0000000002-26-000001", "BBB", accepted=et(PRIOR, 18, 0), items=("8.01",))
    w.filing("0000000003-26-000001", "CCC", accepted=et(D, 11, 0), items=("1.01", "9.01"))
    w.article("n-ddd-1", "DDD", knowable=et(D, 10, 30))
    w.filing("0000000004-26-000001", "DDD", accepted=et(D, 12, 0), items=("8.01",))
    w.article("n-eee-1", "EEE", knowable=et(D, 7, 0))
    w.article("n-fff-1", "FFF", knowable=et(D, 8, 0))
    w.filing("0000000006-26-000001", "FFF", accepted=et(D, 13, 0), items=("8.01",))
    w.insider_buy("0000000007-26-000001", "GGG", accepted=et(PRIOR, 17, 0), usd=60_000.0)
    w.article("n-ggg-1", "GGG", knowable=et(D, 7, 30), symbols=["GGG", "AAA"])
    w.filing("0000000008-26-000001", "HHH", accepted=et(D, 10, 0), items=("8.01",))


def to_the_close(w: W.World) -> None:
    """D's decisions as the House makes them, up to (not including) its live close decision at 15:47 ET."""
    w.at(et(PRIOR, 15, 47)).decide("close", PRIOR)
    w.at(et(D, 7, 31)).decide("open", D, ask_only=True)
    w.at(et(D, 7, 32)).decide("close", D, ask_only=True)
    w.at(et(D, 9, 15, 30)).decide("open", D)
    w.at(et(D, 12, 30)).decide("close", D, ask_only=True)
    w.at(et(D, 15, 17)).decide("close", D, ask_only=True)


class Case(unittest.TestCase):
    def world(self, name: str) -> W.World:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        w = W.World(Path(tmp.name) / name)
        self.addCleanup(w.close)
        rows_of_the_week(w)
        return w

    @staticmethod
    def intents(w: W.World, *, four: bool, day: dt.date = D) -> list[tuple]:
        return [r for r in w.intents() if (r[0] in FOUR) == four and r[6] == day.isoformat()]

    @staticmethod
    def receipts(w: W.World, job: str) -> list[tuple[str, dict]]:
        return [(str(r["status"]), json.loads(r["summary"] or "{}"))
                for r in w.st.db.execute("SELECT status, summary FROM receipts WHERE job=? ORDER BY id", (job,))]


# ------------------------------------------------------------------------------------------------ A83 (3)(i)
class PreregFourFailsAlone(Case):
    def failing_close(self, target: str, error: BaseException) -> tuple[W.World, W.World, dict]:
        """The same day twice: decided whole (`whole`), and with `target` of PREREG-EVL-4's part raising `error` at D's
        live close decision (`broken`)."""
        whole, broken = self.world("whole"), self.world("broken")
        for w in (whole, broken):
            to_the_close(w)
        whole.at(et(D, 15, 47)).decide("close", D)
        real = getattr(R, target)

        def boom(*args, **kwargs):
            raise error
        with mock.patch.object(R, target, side_effect=boom):
            out = broken.at(et(D, 15, 47)).decide("close", D)
        self.assertIsNotNone(real)
        return whole, broken, out

    def test_a_failure_in_its_reads_finishes_the_decision_with_the_earlier_rows_and_names_none_of_its_programs(self):
        whole, broken, out = self.failing_close("_rows_4", RuntimeError("an invented failure of the 8-K window read"))
        self.assertEqual(out["evl4_error"], "RuntimeError: an invented failure of the 8-K window read")
        self.assertEqual(self.intents(broken, four=False), self.intents(whole, four=False),
                         "every earlier row's intents exactly as the whole decision wrote them")
        self.assertGreater(len(self.intents(whole, four=False)), 5)
        self.assertEqual(self.intents(broken, four=True), [], "none of PREREG-EVL-4's rows is written")
        self.assertGreater(len(self.intents(whole, four=True)), 3)
        [*_, (status, summary)] = self.receipts(broken, f"decide-close:{D.isoformat()}")
        self.assertEqual(status, "ok", "the receipt is finished with the earlier rows' results: their looks never wait")
        self.assertEqual(summary["evl4_error"], out["evl4_error"])
        for key in ("EVL-ERN-REACT-C1", "EVL-ERN-REACT-ON@v2", "EVL-NEWS-READ-ON@v2", "EVL-NEWS-REACT-ON@v2"):
            self.assertTrue(SC.names(summary, key), key)
            self.assertFalse(SC._waits_on(status, json.dumps(summary), key), key)
        for key in FOUR:
            self.assertFalse(SC.names(summary, key), f"{key} is named nowhere: made without its rows")
        self.assertEqual(SC.made_without(broken.st, D), {D: False}, "their own decision is due")
        self.assertEqual(SC.made_without(whole.st, D), {})
        # Their own decision (as the House's lane runs it, a backfill) decides them, and makes the close for all five.
        got = R.decide_close(broken.at(et(D, 15, 52)).ctx, D, backfill_run=True, evl4_only=True)
        self.assertNotIn("evl4_error", got)
        self.assertEqual([r[:4] + r[12:13] for r in self.intents(broken, four=True)],
                         [r[:4] + r[12:13] for r in self.intents(whole, four=True)],
                         "the same events, symbols and statuses as the whole decision's")
        self.assertEqual(SC.made_without(broken.st, D), {})
        [(status4, summary4)] = self.receipts(broken, f"decide-{SC.FOUR_KIND}:{D.isoformat()}")
        self.assertEqual(status4, "ok")
        self.assertTrue(all(SC.names(summary4, key) for key in FOUR))

    def test_its_marks_and_its_excluded_moves_are_inside_the_part_too(self):
        for target in ("_marks_1530", "_skip_excluded"):
            with self.subTest(target=target):
                whole, broken, out = self.failing_close(target, ValueError(f"invented {target}"))
                self.assertEqual(out["evl4_error"], f"ValueError: invented {target}")
                self.assertEqual(self.intents(broken, four=False), self.intents(whole, four=False))
                [*_, (status, summary)] = self.receipts(broken, f"decide-close:{D.isoformat()}")
                self.assertEqual(status, "ok")
                self.assertFalse(any(SC.names(summary, key) for key in FOUR), summary)
                self.assertEqual(SC.made_without(broken.st, D), {D: False})

    def test_the_task_bound_still_stops_the_task_and_their_own_decisions_failure_is_its_own(self):
        w = self.world("bound")
        to_the_close(w)
        with mock.patch.object(R, "_rows_4", side_effect=R.Deadline("the task's bound")):
            with self.assertRaises(R.Deadline):
                w.at(et(D, 15, 47)).decide("close", D)
        [*_, (status, _)] = self.receipts(w, f"decide-close:{D.isoformat()}")
        self.assertEqual(status, "running", "unfinished, as before: the House closes it cut and decides it again")
        from league.events import house as H

        self.assertTrue(issubclass(H.LaneDeadline, R.Deadline), "the House's bound is the run's Deadline")
        with mock.patch.object(R, "_rows_4", side_effect=RuntimeError("invented")):
            with self.assertRaises(RuntimeError):
                R.decide_close(w.at(et(D, 15, 50)).ctx, D, backfill_run=True, evl4_only=True)

    def test_the_verdict_asks_of_the_earlier_rows_stand_when_it_fails_in_ask_only(self):
        w = self.world("asks")
        w.at(et(PRIOR, 15, 47)).decide("close", PRIOR)
        with mock.patch.object(R, "_rows_4", side_effect=RuntimeError("invented")):
            out = w.at(et(D, 15, 17)).decide("close", D, ask_only=True)
        self.assertEqual(out["evl4_error"], "RuntimeError: invented")
        self.assertFalse(any(key in (out.get("pending") or {}) for key in FOUR))
        self.assertIn("doc:AAA", w.gw.asked(), "the earlier rows' asks (REACT-READ-C1's PROMPT-DOC of AAA's earnings) made")


# ------------------------------------------------------------------------------------------------ A83 (3)(ii)
class PmRowsAskWhenTheAskingGroupIsFrozen(Case):
    def look(self, w: W.World, program: str, version: int) -> None:
        """A written look of `program` as of NEXT's close: it covers D's intents of every program of its group."""
        w.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES(?, ?, 1, ?, 1, 0)",
                        (program, version, S.iso(C.session(w.st, NEXT).close_at)))

    def asked_news(self, w: W.World) -> list[str]:
        return [a for a in w.gw.asked() if a.startswith("news:")]

    def test_a_frozen_news_read_group_leaves_the_close_decision_to_ask_its_pm_rows_verdicts(self):
        free, frozen = self.world("free"), self.world("frozen")
        self.look(frozen, "EVL-NEWS-READ-O1", 2)
        for w in (free, frozen):
            w.at(et(PRIOR, 15, 47)).decide("close", PRIOR)
            w.at(et(D, 7, 31)).decide("open", D, ask_only=True)
        self.assertEqual(self.asked_news(free), ["news:EEE", "news:FFF"], "EVL-NEWS-READ-O1's open asks them")
        self.assertEqual(self.asked_news(frozen), [], "its group frozen over D: the open decision asks nothing")
        for w in (free, frozen):
            w.at(et(D, 7, 32)).decide("close", D, ask_only=True)
        self.assertEqual(self.asked_news(free), ["news:EEE", "news:FFF", "news:DDD"],
                         "with no freeze the close asks no PM row's verdict (1019d): only NEWS-READ-ON's day news")
        self.assertEqual(self.asked_news(frozen), ["news:DDD", "news:EEE"],
                         "the close asks the verdicts its PM rows need, after the earlier rows' own: EEE (FFF's 8-K of "
                         "D puts it in the F8K(D) skip, so no PM row needs FFF's)")
        for w in (free, frozen):
            w.at(et(D, 9, 15, 30)).decide("open", D)
            w.at(et(D, 12, 30)).decide("close", D, ask_only=True)
            w.at(et(D, 15, 17)).decide("close", D, ask_only=True)
            w.at(et(D, 15, 47)).decide("close", D)
            w.at(et(D, 16, 41)).decide("close", D, live=False)
        self.assertEqual(self.asked_news(frozen), ["news:DDD", "news:EEE"], "each asked once, stored once")
        news = V.PROMPTS["news"]
        for w, fff in ((free, [("news:n-fff-1", news.sha, V.MODEL, 2)]), (frozen, [])):
            rows = [tuple(r) for r in w.st.db.execute("SELECT event, prompt_sha, model, score FROM verdicts WHERE event "
                                                      "LIKE 'news:%' ORDER BY event")]
            self.assertEqual(rows, [("news:n-ddd-1", news.sha, V.MODEL, 2), ("news:n-eee-1", news.sha, V.MODEL, 3)] + fff,
                             "the same stored prompt (no new one), one verdict an event")
        def pm_bodies(w: W.World) -> dict[str, dict]:
            return {b["messages"][0]["content"].split()[1]: b for b in w.gw.claude_calls
                    if b["messages"][0]["content"].startswith("Stock: EEE")}
        self.assertEqual(pm_bodies(frozen), pm_bodies(free), "the very request D's open decision sends: prompt and rendering")
        self.assertEqual(len(pm_bodies(frozen)), 1)
        # The PM rows decide in both worlds alike; the frozen group asked and wrote nothing on D.
        pm = ("EVL-NEWSPM-READ-ON", "EVL-CTRL-NEWSPM-ON")
        got = {w: [r[:4] + r[12:13] for r in w.intents() if r[0] in pm and r[6] == D.isoformat()] for w in (free, frozen)}
        self.assertEqual(got[frozen], got[free])
        self.assertEqual({r[0] for r in got[frozen]}, set(pm), "EVL-NEWSPM-READ-ON and its control decide EEE")
        group = ("EVL-NEWS-READ-O1", "EVL-CTRL-NEWS-ALL-O1")
        self.assertEqual([r for r in frozen.intents() if r[0] in group and r[6] == D.isoformat()], [],
                         "the frozen group itself is written nothing")
        self.assertTrue([r for r in free.intents() if r[0] in group and r[6] == D.isoformat()])
        [*_, (status, summary)] = self.receipts(frozen, f"decide-close:{D.isoformat()}")
        self.assertEqual(status, "ok")
        self.assertFalse(any(key in summary["pending"] for key in pm), "no PM row waits on an ask no one makes")
        [*_, (_, opened)] = self.receipts(frozen, f"decide-open:{D.isoformat()}")
        self.assertEqual(sorted(opened["kept"]), ["EVL-CTRL-NEWS-ALL-O1", "EVL-NEWS-READ-O1", "EVL-NEWS-READ-O1@v2"])

    def test_another_groups_look_never_moves_the_asks(self):
        w = self.world("other")
        self.look(w, "EVL-8K-READ-ON", 1)
        w.at(et(PRIOR, 15, 47)).decide("close", PRIOR)
        w.at(et(D, 7, 31)).decide("open", D, ask_only=True)
        before = len(w.gw.claude_calls)
        w.at(et(D, 7, 32)).decide("close", D, ask_only=True)
        self.assertEqual([a for a in w.gw.asked()[before:] if a.startswith("news:")], ["news:DDD"],
                         "EVL-NEWS-READ-O1's open decision asked the PM rows' verdicts: the close asks only its day news")


# ------------------------------------------------------------------------------------------------ A74 (5), births
class ABirthsLookFreezesItsControl(unittest.TestCase):
    def test_a_read_birth_groups_with_its_derived_control_and_no_prereg_group_moves(self):
        from league.tests import test_events_births as TB

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(TB.unload)
        before = {p.id: R._group(p.id) for p in P.PREREG_PROGRAMS}
        s = TB.Synth(Path(tmp.name))
        self.addCleanup(s.st.close)
        s.register(TB.spec("EVL-B-ERN-TOP", "ern", {"score_min": 3}, rank="score"), "2026-11-03T01:00:00Z")
        s.register(TB.spec("EVL-B-8K-502", "8k", {"items": ["5.02"]}), "2026-11-03T01:00:00Z", seq=1)
        P.load_births(s.st)
        self.assertEqual({p.id: R._group(p.id) for p in P.PREREG_PROGRAMS}, before, "every PREREG group is its table's")
        pair = frozenset({"EVL-B-ERN-TOP", "EVL-B-ERN-TOP-CTRL"})
        self.assertEqual((R._group("EVL-B-ERN-TOP"), R._group("EVL-B-ERN-TOP-CTRL")), (pair, pair))
        self.assertEqual(R._group("EVL-B-8K-502"), frozenset({"EVL-B-8K-502"}), "a birth that reads no verdict: alone")
        s.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES('EVL-B-ERN-TOP', 1, 1, ?, 1, 0)",
                        (S.iso(C.session(s.st, dt.date(2026, 11, 20)).close_at),))
        kept = R._scope(s.st, "open", dt.date(2026, 11, 10), dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc))
        self.assertIsNotNone(kept(P.BY_KEY[("EVL-B-ERN-TOP-CTRL", 1)]), "its control's record stays as the look read it")
        self.assertIsNotNone(kept(P.BY_KEY[("EVL-B-ERN-TOP", 1)]))
        self.assertIsNone(kept(P.BY_KEY[("EVL-B-8K-502", 1)]))
        self.assertIsNone(kept(P.BY_KEY[("EVL-ERN-READ-O1", 2)]), "no PREREG program is frozen by a birth's look")


if __name__ == "__main__":
    unittest.main()
