"""RELEASE 1019m (the independent review of the live code, A139): PREREG-EVL-7's LEARNERS NEVER COST R3's BIRTHS THEIR
REAL-MONEY ENTRY FOR NOTHING (league/equity/live.py `_event_decide_lrn`, `_event_learner_cut`, `_event_lrn_said`),
through the real book, invented rows only.

(1) THE WINDOW'S LAST BOOK MINUTE: EVL-LRN-ON's live receipt starts only after the House's close decision, which
finished after the book's 15:49 ET cut-off at every close on record; release 1019j held every birth at learning behind
it with no bound but the cut-off, so the births were never planned. From the last book minute of the window a learner
whose live receipt has not finished takes nothing (it could send nothing by the cut-off) and the births are given their
names. (2) THE DAY'S LINE: EVL-LRN-O1's entries are refused by the event kind's day line while the close rows hold its
room (R5); it took a name a birth wanted, and nobody bought it. A learner the line refuses holds no birth back and takes
no birth's name. (3) The post-close alarm says when births held for the learners were never given their names."""
from __future__ import annotations

import unittest

from league.equity import live as L
from league.events import births as BI
from league.events import learner as LR
from league.events import programs as P
from league.tests import test_events_book as TB
from league.tests import test_events_evl7 as T7
from league.tests.test_events_births import spec

ON, O1 = T7.ON, T7.O1
CLOSE_BIRTH = "EVL-B-NEWSDAY-HI"
OPEN_BIRTH = "EVL-B-8K-502"


def register(h: TB.Harness, pid: str, family: str, rule: dict, **kw) -> P.Program:
    sp = spec(pid, family, rule, **kw)
    h.lane.st.db.execute(
        "INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
        "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, 'docs/births/2026-11-02.jsonl', ?, 0, "
        "'{}', 'x', 'captain', '2026-11-02')",
        (pid, BI.sha(sp), BI.canonical(sp), "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
         "c" * 40))
    return next(b for b in P.load_births(h.lane.st) if b.id == pid)


def buys(h: TB.Harness) -> list[tuple[str, str, str]]:
    return [(r["program"], r["symbol"], r["status"]) for r in h.event_intents("buy")]


def sent(h: TB.Harness) -> list[str]:
    return [b["symbol"] for b in h.bodies() if b.get("side") == "buy"]


class TheCloseBirths(TB.EventTest):
    """A close-entry birth at learning (a day-news article of BRTH with its PROMPT-NEWS verdict), EVL-LRN-ON live and
    pinned, E $2,000, ample cash; the lane's own close decision done."""

    def build(self, *, pinned: bool = True) -> TB.Harness:
        T7.pin(self, T7.REG7 if pinned else None)
        self.addCleanup(P.load_births, None)
        h = self.harness()
        birth = register(h, CLOSE_BIRTH, "news-day", {"score_max": -2}, exit_="open")
        h.lane.article("n-1", "BRTH", knowable=TB.iso(TB.DAY, 11, 0))
        h.lane.verdict("n-1", -3, answered=TB.iso(TB.DAY, 11, 5), news=True)
        h.lane.universe(TB.DAY, "BRTH", TB.CIK2, 16.0)
        h.lane.intent(birth, "news:n-1", "BRTH", TB.CIK2, TB.DAY, TB.NEXT)
        h.symbol("BRTH", last=17.0, sd=0.02)
        if pinned:
            LR.ensure(h.lane.st.db)
        self.ready(h)
        return h

    def test_a_late_learner_receipt_leaves_the_birth_its_close_entry(self):
        """ON's live receipt finishes at 15:49:30 (after the cut-off): at the 15:48:03 tick it takes nothing and the birth
        is planned and sent; before release 1019m the birth was never planned."""
        h = self.build()
        for mm in (46, 47):
            h.tick(15, mm)
        main = h.book._event_summary(TB.DAY.isoformat(), "close")
        self.assertIn(CLOSE_BIRTH, main["learners"]["deferred"], "before the last minute the birth waits for ON (R4)")
        self.assertEqual(sent(h), [], "nothing before the last minute")
        h.tick(15, 48)                                       # 15:48:03 ET: the window's last book minute
        self.assertEqual(buys(h), [(CLOSE_BIRTH, "BRTH", "sent")], "the birth goes in the last minute's buy phase")
        self.assertEqual(sent(h), ["BRTH"])
        lrn = h.book._event_summary(TB.DAY.isoformat(), "close-lrn")
        self.assertIn("late", lrn["programs"][ON], "ON took nothing: section 1.9's window (A140)")
        self.assertEqual(lrn["late"], [ON])
        self.assertTrue(any(k == "equity.alert" and p.get("learners_late") == [ON] for k, p in h.events))
        T7.TheMoney.live(self, h.lane, ON, TB.DAY, [(TB.CIK, "ACME", 20.0)], named=None)
        T7.name_live(h.lane.st, ON, TB.DAY, finished=T7.et(TB.DAY, 15, 49, 30))
        for mm in (49, 50):
            h.tick(15, mm)
        self.assertEqual(sent(h), ["BRTH"], "ON's late receipt buys nothing: the auction is decided")
        h.tick(16, 5)                                        # the close has ended: no births were lost, nothing more said
        said = [(level, text) for level, text in h.alerts if "PREREG-EVL-7" in text]
        self.assertEqual(len(said), 1, said)
        self.assertEqual(said[0][0], "warning", "A140's warning at the last minute, once")
        self.assertIn("still pending", said[0][1])

    def test_a_learner_on_time_still_comes_first(self):
        """ON's live receipt in by 15:47:55: the learners' decision is made at 15:48:03 as before (no window)."""
        h = self.build()
        for mm in (46, 47):
            h.tick(15, mm)
        T7.TheMoney.live(self, h.lane, ON, TB.DAY, [], named=None)
        T7.name_live(h.lane.st, ON, TB.DAY, finished=T7.et(TB.DAY, 15, 47, 55))
        h.tick(15, 48)
        lrn = h.book._event_summary(TB.DAY.isoformat(), "close-lrn")
        self.assertNotIn("late", lrn)
        self.assertNotIn("late", lrn["programs"].get(ON) or {})
        self.assertEqual(sent(h), ["BRTH"])

    def test_without_a_tick_in_the_last_minute_the_lost_births_are_alarmed(self):
        """A book that misses the window's last minute (its 15:47 minute ran past 15:48:03): the births held for the
        learners are never planned, with no intent and no ledger row; the post-close alarm says so as a WARNING."""
        h = self.build()
        for mm in (46, 47):
            h.tick(15, mm)
        h.tick(15, 49)
        self.assertEqual(buys(h), [])
        h.tick(16, 5)
        said = [(level, text) for level, text in h.alerts if "PREREG-EVL-7" in text]
        self.assertEqual(len(said), 1, said)
        self.assertEqual(said[0][0], "warning")
        self.assertIn(CLOSE_BIRTH, said[0][1])
        self.assertIn("never given their names", said[0][1])
        h.tick(16, 6)
        self.assertEqual(len([t for _, t in h.alerts if "PREREG-EVL-7" in t]), 1, "said once a session")

    def test_without_the_learners_the_birth_is_decided_by_the_book_at_1547(self):
        h = self.build(pinned=False)
        for mm in (46, 47):
            h.tick(15, mm)
        self.assertEqual(sent(h), ["BRTH"])


class TheLateLaneWithTheLearner(TB.EventTest):
    """The timing review's case (release 1019j live): a close-entry R3 birth (its event alone) and a PREREG-EVL-5 row
    (EVL-ERN-DROP-ON), EVL-LRN-ON pinned, E $2,000, ample cash; the lane's own close receipt late (15:52 ET, Oct 21) or
    in time (15:47:40, the batched decision of release 1019m: league/tests/test_events_1019m_marks.py)."""

    def world(self) -> TB.Harness:
        from league.tests import test_events_1019g as G

        T7.pin(self)
        self.addCleanup(P.load_births, None)
        h = self.harness(cash="2000")
        LR.ensure(h.lane.st.db)
        G.register_birth(h, self)
        G.fall(h, "ACME", TB.CIK, "e-1")                       # DROP's event (0.95)
        G.fall(h, "BETA", TB.CIK2, "e-2", reaction=0.965)      # the birth's alone
        h.lane.decided(TB.DAY, "open")
        self.G = G
        return h

    def lane_close(self, h: TB.Harness) -> None:
        from league.events import book as EB
        from league.events import screen as SN

        prog = next(p for p in EB.seatable() if p.id == self.G.DROP)
        self.G.lane_close(h, SN.program_key(prog.id, prog.version))

    def test_a_late_lane_loses_only_preregevl5s_entry_and_the_birth_still_goes(self):
        h = self.world()
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47), (15, 48)):
            h.tick(hh, mm)
        self.assertEqual([s for s, _ in self.G.sent(h)], ["BETA"], "the birth at 15:48:03; DROP waits for the lane")
        h.tick(15, 49)
        self.lane_close(h)
        T7.name_live(h.lane.st, ON, TB.DAY, finished=T7.et(TB.DAY, 15, 52, 30))
        h.tick(15, 52)
        self.assertEqual([s for s, _ in self.G.sent(h)], ["BETA"], "nothing after the cut-off")

    def test_a_lane_in_time_sends_drop_and_the_birth(self):
        h = self.world()
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.lane_close(h)                                     # 15:47:40
        T7.name_live(h.lane.st, ON, TB.DAY, finished=T7.et(TB.DAY, 15, 47, 55))
        h.tick(15, 48)
        self.assertEqual(sorted(s for s, _ in self.G.sent(h)), ["ACME", "BETA"])


class TheOpenLearnerTheLineRefuses(TB.EventTest):
    """At the open, an 8-K birth at learning wants BRTH; EVL-LRN-O1 (whose entries the day order line refuses while the
    close rows hold its room, R5) is named with BRTH too."""

    def build(self, *, pinned: bool) -> TB.Harness:
        T7.pin(self, T7.REG7 if pinned else None)
        self.addCleanup(P.load_births, None)
        h = self.harness()
        birth = register(h, OPEN_BIRTH, "8k", {"items": ["5.02"]})
        TB.earnings(h.lane, "b-1", TB.CIK2, "BRTH", items=("5.02",))
        h.lane.intent(birth, "8k:b-1", "BRTH", TB.CIK2, TB.DAY, TB.DAY)
        h.symbol("BRTH", last=17.0, sd=0.02)
        if pinned:
            LR.ensure(h.lane.st.db)
            T7.TheMoney.live(self, h.lane, O1, TB.DAY, [(TB.CIK2, "BRTH", 16.0)], named=None)
        self.ready(h)
        return h

    def test_the_birth_buys_its_name_as_without_the_learners(self):
        without = self.build(pinned=False)
        without.tick(9, 15)
        without.tick(9, 16)
        self.assertEqual(sent(without), ["BRTH"])

    def test_a_learner_the_line_refuses_holds_nothing_back_and_takes_no_birth_name(self):
        h = self.build(pinned=True)
        h.tick(9, 15)
        main = h.book._event_summary(TB.DAY.isoformat(), "open")
        self.assertNotIn("learners", main, "O1 can send nothing here: no cut, no birth held back")
        self.assertEqual(main["programs"][OPEN_BIRTH].get("planned"), 1)
        h.tick(9, 16)
        self.assertEqual(sent(h), ["BRTH"], "the birth's buy goes while O1's receipt is still running")
        T7.name_live(h.lane.st, O1, TB.DAY, finished=T7.et(TB.DAY, 9, 16, 30))
        for mm in range(17, 27):
            h.tick(9, mm)
        lrn = h.book._event_summary(TB.DAY.isoformat(), "open-lrn")
        self.assertIn("line", lrn["programs"][O1], "the line's refusal is said on O1's summary")
        self.assertEqual(lrn["programs"][O1].get("skipped"), {"name_given": 1}, "BRTH was the birth's")
        self.assertEqual(sent(h), ["BRTH"])
        self.assertEqual([b for b in buys(h) if b[0] == O1], [])

    def test_at_the_open_a_learner_still_pending_at_the_last_minute_leaves_the_birth_its_entry(self):
        """Release 1019m: A140's last book minute at the OPEN too. A learner the line TAKES (here: patched) holds the
        birth back; its live receipt never lands by 09:26:03, so the birth is planned and sent then."""
        from unittest import mock

        with mock.patch.object(L.EquityBook, "_event_line_refuses", lambda *a, **k: None, create=True):
            h = self.build(pinned=True)
            h.tick(9, 15)
            main = h.book._event_summary(TB.DAY.isoformat(), "open")
            self.assertIn(OPEN_BIRTH, main["learners"]["deferred"])
            for mm in range(16, 26):
                h.tick(9, mm)
            self.assertEqual(sent(h), [], "the birth waits for O1's receipt until the last minute")
            h.tick(9, 26)                                    # 09:26:03 ET: the open window's last book minute
            self.assertEqual(sent(h), ["BRTH"])
            lrn = h.book._event_summary(TB.DAY.isoformat(), "open-lrn")
            self.assertEqual(lrn["late"], [O1])

    def test_the_line_check_reads_the_keep_of_an_entry_not_planned(self):
        h = self.build(pinned=True)
        h.tick(9, 15)
        inst = h.book._instance(L.instance_key(O1, 1))
        from league.events import book as EB

        s = EB.settings()
        why = h.book._event_line_refuses(inst, TB.DAY.isoformat(), "open", s, h.book._event_adapter())
        self.assertIn("PREREG-EVL-7 section 1.9's day order line", why or "")
        close = h.book._instance(L.instance_key(ON, 1))
        self.assertIsNone(h.book._event_line_refuses(close, TB.DAY.isoformat(), "close", s, h.book._event_adapter()),
                          "EVL-LRN-ON at the close: the line takes its entry")


if __name__ == "__main__":
    unittest.main()
