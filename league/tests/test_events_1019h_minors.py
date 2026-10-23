"""Release 1019h's minors (the two reviews of release 1019g, b374d862; the captain's decision on PREREG-EVL-5's money
re-review, its option 1). One class an item, each test failing on feat/done-speed's code (88ecf37f) without its fix:

(1) `evl_score`'s "waiting on the tape" excuse (league/ops/evl_health.py `none_marks`) reads the score's own auction
    labels only ('open', 'close', 'first': `TAPE_LABELS`), so PREREG-EVL-5's '0930' minute with no trade never excuses
    an unrelated stuck intent of the name;
(2) R3's outcome-free facts (league/events/births.py `Facts._windows`) window PREREG-EVL-4's and -5's families, so
    their nine rows have selection counts (upper bounds where a price is unread) and the validator's Jaccard reads
    them (PREREG-EVL-5 section 7, "births.py's facts for the new families");
(3) release 1019f's alarms extended to `decide-close-evl5`: `evl_decide` stands on a close PREREG-EVL-5's rows still owe
    their own decision, `evl_verdicts` reads its tallies;
(4) the close lead after a FAILED live run (league/events/house.py `_lead`, `LEAD_ENDS`): no other decision starts
    before its retry, every other task ends before it, and the held turn starts the retry at its time, before the
    book's cut-off;
(5) the waiting room once the lane's close receipt is overdue (league/equity/live.py `HELD_OVERDUE_S`): a waiting
    PREREG-EVL-5 buy keeps no room from a row of PREREG-EVL-1 to -4, still from a birth; the post-close alert is a
    warning when a PREREG row waited for that room and ended unsent;
(6) the shipped calibration script's import (docs/prereg/evl-3/calibrate_events.py, the tag's bytes) and the stale
    doc lines (the running release, the births budget after PREREG-EVL-5).

Synthetic stores, books and weeks only: every event, verdict, order and price here is invented."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.tests.evl6_fakes import on_1019h
from league.equity import live as L
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import programs as P
from league.events import run as R
from league.events import screen as SC
from league.events import score as SCORE
from league.events import store as S
from league.ops import evl_health as EV
from league.tests import evl5_world as W
from league.tests import test_events_book as TB
from league.tests import test_events_evl5 as T5
from league.tests import test_events_house as TH
from league.tests.test_daily_report import Cal
from league.tests.test_evl_health import Lane, backfill_done, et

REPO = Path(__file__).resolve().parents[2]
UTC = dt.timezone.utc
MON, TUE, WED, THU, FRI = (dt.date(2026, 10, d) for d in (19, 20, 21, 22, 23))
FILE4 = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON", "EVL-CTRL-8K-ON", "EVL-CTRL-NEWSPM-ON")
FILE5 = ("EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON", "EVL-NEWS-NIGHT2-ON", "EVL-CTRL-ERN-UNDER-ON")


# ------------------------------------------------------------------------------------------------- (1) the tape's word
class TheTapesWordIsTheScoresOwn(Lane):
    """An entered intent of ACME due by Tuesday's close and still open after the night's pass is a stall; a '0930'
    mark with no price (PREREG-EVL-5's gap minute with no trade, league/events/run.py `_marks_0930`) on or after its
    exit day excuses nothing, while the score's own 'close' mark with no price still does."""

    def mark(self, symbol: str, day: dt.date, label: str) -> None:
        self.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, ?, NULL, NULL, "
                           "?, 'x')", (symbol, day.isoformat(), label, "sip-1min:none" if label == "0930" else "none"))

    def test_a_0930_mark_with_no_price_excuses_no_stuck_intent(self):
        self.intent("8k:a", TUE, status="entered", symbol="ACME")
        self.receipt("score", et(TUE, "20:30"), summary={"day": "2026-10-20", "complete": True})
        now = et(TUE, "23:30")
        self.mark("ACME", WED, R.GAP_LABEL)
        check = self.check("evl_score", now)
        self.assertTrue(check["stalled"], check["what"])
        self.assertEqual((check["numbers"]["open_due"], check["numbers"]["waiting_on_tape"]), (1, 0))
        self.mark("ACME", WED, "close")
        check = self.check("evl_score", now)
        self.assertFalse(check["stalled"], "the score's own 'close' word of no print still excuses it")
        self.assertEqual(check["numbers"]["waiting_on_tape"], 1)

    def test_the_labels_are_the_scores_own(self):
        self.assertEqual(set(EV.TAPE_LABELS), set(SCORE.CONDITIONS) | {"first"})
        self.assertNotIn(R.GAP_LABEL, EV.TAPE_LABELS)


# ------------------------------------------------------------------------------------------------- (2) the facts
class TheFactsSeeTheLaterFiles(unittest.TestCase):
    """The invented week of PREREG-EVL-5's tests (league/tests/evl5_world.py, decided as the House decides it): the
    facts as of Wed Oct 28 count every row of PREREG-EVL-4 and -5 (the review of release 1019g: all nine read 0), each
    count at least the events the row's shadow decided (an upper bound where a price is unread), the rows that read no
    price exactly those on the decided sessions; the facts still read no refused table; the validator's Jaccard reads
    them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.world = W.World(Path(cls.tmp.name) / "lane")
        W.the_week(cls.world)
        cls.st = cls.world.st
        P.load_births(cls.st)

    @classmethod
    def tearDownClass(cls):
        P.load_births(None)
        cls.world.close()
        cls.tmp.cleanup()

    def decided(self, prog: P.Program) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for r in self.st.db.execute("SELECT entry_day, event FROM intents WHERE program=? AND version=? AND status NOT "
                                    "LIKE 'skipped%'", (prog.id, prog.version)):
            out.setdefault(str(r["entry_day"]), set()).add(str(r["event"]))
        return out

    def test_every_row_of_the_two_files_is_counted_and_covers_its_shadow(self):
        facts = BI.Facts(self.st, W.N_DAY)
        listed = {p["id"]: p for p in facts.facts()["programs"]}
        exact = {"EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON", "EVL-CTRL-NEWSPM-ON"}
        for pid in FILE4 + FILE5:
            prog = P.BY_ID[pid]
            with self.subTest(pid):
                self.assertGreater(listed[pid]["selected"], 0, "counted (release 1019g's facts read 0)")
                by = {d.isoformat(): set(v) for d, v in facts.selected(prog).items() if v}
                for day, events in self.decided(prog).items():
                    self.assertLessEqual(events, by.get(day, set()), f"{day}: the shadow's events are in the facts")
                    if pid in exact:
                        self.assertEqual(events, by.get(day, set()), f"{day}: a row that reads no price, as decided")
        self.assertIn("8k:0000000002-26-000001", {e for v in facts.selected(P.BY_ID["EVL-8K-REACT-ON"]).values()
                                                  for e in v}, "an upper bound: the reaction is unread")

    def test_the_facts_still_read_no_price_return_look_or_band(self):
        said: list[str] = []
        self.st.db.set_trace_callback(said.append)
        try:
            facts = BI.Facts(self.st, W.N_DAY)
            for pid in FILE4 + FILE5:
                facts.count(P.BY_ID[pid])
        finally:
            self.st.db.set_trace_callback(None)
        refused = re.compile(r"\b(bars|marks|outcomes|looks|bands|band_history|real_fills|universe|meta)\b", re.I)
        self.assertGreater(len(said), 50)
        self.assertEqual([q for q in said if refused.search(q)], [])

    def test_the_validators_jaccard_reads_them(self):
        """A record birth whose events are EVL-ERN-DROP-ON's (every earnings 8-K of D's close window, its reaction
        unread): against PREREG-EVL-4's and -5's rows alone it is DROP's duplicate (release 1019g's facts gave it 0
        against them and accepted it)."""
        facts = BI.Facts(self.st, W.N_DAY)
        dip = {"spec": {"id": "EVL-B-ERN-DIP", "version": 1, "family": "ern-react", "rule": {"react_max": 0.96},
                        "entry": "close", "exit": "open", "hold": 1, "rank": "none", "seatable": False}, "why": "x"}
        later = tuple(p for p in P.PROGRAMS if p.prereg in (4, 5) and p.spec is None)
        with mock.patch.object(BI, "RECORD_MIN_RATE", 0), mock.patch.object(P, "PROGRAMS", later):
            [out] = BI.validate(self.st, facts, [dip], night=W.N_DAY)
        self.assertFalse(out["ok"])
        self.assertIn(out["jaccard"]["with"], ("EVL-ERN-DROP-ON", "EVL-CTRL-ERN-UNDER-ON"))
        self.assertGreaterEqual(out["jaccard"]["max"], BI.JACCARD_MAX)

    def test_no_reading_of_the_grammar_moves(self):
        # The minors moved neither (`fix/1019h-minors` read 3 and 890806ff); release 1019h's A109 (the architect on
        # Claude Opus 5.5, league/tests/test_events_1019h_architect.py) moved both, the model being in the sha's spec.
        # (release 1019i: the prompt tells PREREG-EVL-6's restated charge, 0.13 a seatable spec, from the budget, so
        # its sha moved with PARSE_VERSION 5, the prompt's text and its version pinned together: A95)
        self.assertEqual((BI.PARSE_VERSION, BI.prompt_sha()[:8]), (5, "1442a2a2"),
                         "more Jaccard targets only refuse more: no refused answer can turn accepted")
        self.assertEqual(set(BI.FILE_FAMILIES), set(P.CLOSE_FAMILIES_4) | set(P.CLOSE_FAMILIES_5))
        self.assertTrue(set(BI.FILE_FAMILIES).isdisjoint(BI.FAMILIES), "no birth names one")


# ------------------------------------------------------------------------------------------------- (3) the alarms
class FiveKind(Lane):
    """(3) Thursday Oct 22's close decided by a release without PREREG-EVL-5's rows (its receipt names PREREG-EVL-4's
    and no row of PREREG-EVL-5; registered 21:26:21Z Oct 21, before that close's decision): `evl_decide` stands 2 h after
    the stall job first saw it, `evl_verdicts` reads `decide-close-evl5`'s tally, and both clear once it is made."""

    def setUp(self):
        super().setUp()
        backfill_done(self.st)
        C.refresh(self.st, Cal(), dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        four = {SC.program_key(p.id, p.version): {"planned": 0} for p in SC.file_programs(4)}
        self.receipt("decide-open:2026-10-22", et(THU, "09:15"))
        self.receipt("decide-close:2026-10-22", et(THU, "15:47"),
                     summary={**four, "evl5_error": "PartDeadline: past its bound", "verdicts": {"needed": 0, "answered": 0}})
        self.receipt("decide-open:2026-10-23", et(FRI, "09:15"))
        self.kept: dict = {}

    def checks(self, now, **kw):
        return EV.checks(self.ctx(), self.root, now, kept=self.kept, **kw)

    def test_the_judges_own_reading_names_the_close(self):
        self.assertEqual(SC.made_without(self.st, FRI, prereg=5), {THU: False})
        self.assertEqual(SC.made_without(self.st, FRI), {}, "PREREG-EVL-4's rows were decided")

    def test_a_close_still_owed_its_own_decision_stands_and_clears_once_made(self):
        first = self.checks(et(FRI, "08:00"))["evl_decide"]
        self.assertFalse(first["stalled"])
        self.assertEqual(first["numbers"]["five_waiting"], 0, "first seen now")
        self.assertEqual(sorted(self.kept[EV.KEPT_FIVE]), ["2026-10-22"])
        self.assertEqual(self.kept[EV.KEPT_FOUR], {})
        self.assertFalse(self.checks(et(FRI, "09:59"))["evl_decide"]["stalled"])
        check = self.checks(et(FRI, "10:01"))["evl_decide"]
        self.assertTrue(check["stalled"], check["what"])
        self.assertEqual((check["numbers"]["five_first"], check["numbers"]["five_state"], check["numbers"]["five_hours"],
                          check["numbers"]["four_waiting"]), ("2026-10-22", "never", 2.0, 0))
        self.assertIn("PREREG-EVL-5's rows of the close of 2026-10-22 are still to decide by themselves 2.0 h after a "
                      "release decided it without them or their part of it failed: its decide-close-evl5 was never run",
                      check["what"])
        self.receipt(f"decide-{SC.FIVE_KIND}:2026-10-22", et(FRI, "10:12"), status="pending",
                     summary={"verdicts": {"needed": 2, "answered": 1}})
        self.assertEqual(self.checks(et(FRI, "10:20"))["evl_decide"]["numbers"]["five_state"], "pending")
        verdicts = self.checks(et(FRI, "10:40"))["evl_verdicts"]
        self.assertTrue(verdicts["stalled"], "its tally is read: 1 verdict unanswered 28 minutes past its run")
        self.assertEqual(verdicts["numbers"]["first_held"], "close-evl5:2026-10-22")
        self.assertIn("1 verdicts the event lane's close decision of PREREG-EVL-5's rows of 2026-10-22 needs",
                      verdicts["what"])
        self.receipt(f"decide-{SC.FIVE_KIND}:2026-10-22", et(FRI, "10:41"),
                     summary={"verdicts": {"needed": 2, "answered": 2}})
        done = self.checks(et(FRI, "10:50"))
        self.assertFalse(done["evl_decide"]["stalled"])
        self.assertFalse(done["evl_verdicts"]["stalled"])
        self.assertEqual(self.kept[EV.KEPT_FIVE], {}, "a close no longer waiting is dropped")

    def test_both_files_waiting_are_named_apart(self):
        self.receipt("decide-close:2026-10-22", et(THU, "16:30"), summary={})   # decided again, naming neither file
        self.checks(et(FRI, "08:00"))
        check = self.checks(et(FRI, "10:31"))["evl_decide"]
        self.assertEqual((check["numbers"]["four_waiting"], check["numbers"]["five_waiting"]), (1, 1))
        self.assertIn("PREREG-EVL-4's rows of the close of 2026-10-22", check["what"])
        self.assertIn("PREREG-EVL-5's rows of the close of 2026-10-22", check["what"])
        self.assertEqual(check["onset"], et(FRI, "08:00"))


# ------------------------------------------------------------------------------------------------- (4) the lead
class TheLeadAfterAFailedLiveRun(TH.LaneCase):
    """(4) The review of release 1019g: the lead ended at ANY receipt of the live close decision, a failed one included,
    so after one failed live run (an OSError, a gateway 429) another decision started with the whole DECIDE_BUDGET and
    the retry came after the book's 15:49:00 cut-off. Now the lead ends only when a run has finished `ok` or `pending`
    (or the decision is no longer live): the turn keeps going after the failure, no other decision starts, every other
    task ends DECISION_MARGIN before the retry, and the retry starts at its time (the failed run's start + DECIDE_RETRY)
    in the same turn."""

    opened = T5.TheLanesTurnForItsCloseDecision.opened
    decisions = T5.TheLanesTurnForItsCloseDecision.decisions

    def new_lane(self, redecide=False, **settings):
        """The lane whose sleep moves the House's clock (as TheLanesTurnForItsCloseDecision's)."""
        lane = super().new_lane(redecide, **settings)

        def sleep(seconds: float) -> None:
            self.mono.advance(seconds)
            self.clock.advance(seconds)
        lane._sleep = sleep
        return lane

    def flaky(self, *, redecide_seconds: float = 140.0, fail_first: bool = True):
        """R.decide_close whose first live run of Tuesday's close starts its receipt and raises (as a gateway 429 in
        its eligibility reads would; `fail_first`); a run of Monday's close takes `redecide_seconds` on the House's
        clock."""
        real = R.decide_close
        tries: list[str] = []

        def run(ctx, day, **kw):
            if fail_first and day == TUE and not kw.get("backfill_run") and not tries:
                tries.append(S.iso(ctx.now()))
                ctx.store.start_receipt("decide-close:2026-10-20", now=ctx.now())
                raise OSError("429 Too Many Requests (invented)")
            out = real(ctx, day, **kw)
            if day == MON:
                self.clock.advance(redecide_seconds)
            return out
        return mock.patch.object(R, "decide_close", run)

    def setUp(self):
        super().setUp()
        self.opened()
        self.lane._looks[("close", TUE)] = H.VerdictLook(TH.et("2026-10-20", "15:40"), 0, False)

    def test_a_failed_live_run_is_retried_at_its_time_in_the_same_turn_before_a_queued_redecision(self):
        self.at(TH.et("2026-10-20", "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane._redecide.add(("close", MON))
        made = self.decisions()
        with self.flaky():
            self.lane.run()
        closes = self.receipts("decide-close:2026-10-20")
        self.assertEqual([(r["status"], r["started_at"]) for r in closes],
                         [("failed", "2026-10-20T19:47:00Z"), ("ok", "2026-10-20T19:48:00Z")],
                         "the retry at the failed run's start + DECIDE_RETRY, in the same turn")
        self.assertLess(closes[-1]["finished_at"], "2026-10-20T19:48:40Z", "before the book's last minute")
        self.assertEqual(made[:2], [("close", "2026-10-20", "2026-10-20T19:47:00Z"),
                                    ("close", "2026-10-20", "2026-10-20T19:48:00Z")])
        if len(made) > 2:
            self.assertEqual(made[2][:2], ("close", "2026-10-19"), "the re-decision after the live one, whole")
        self.assertTrue(any(level == "warning" and "decide-close failed (OSError" in text
                            for level, text in self.house.alerts), "the failed run is warned as before")
        self.assertIsNone(self.lane.health()["running"])

    def test_a_turn_after_a_failed_run_starts_no_other_decision_before_its_retry(self):
        """The review's timeline: the failed run closed at 15:47:00, the next publish at 15:47:23 ET with Monday's
        re-decision queued. The re-decision used to start then (140 s) and the retry came at 15:50:03."""
        with self.store() as st:
            rid = st.start_receipt("decide-close:2026-10-20", now=TH.et("2026-10-20", "15:47"))
            st.finish_receipt(rid, "failed", {"why": "OSError: invented"}, now=TH.et("2026-10-20", "15:47"))
        self.mark_recorded(TH.et("2026-10-20", "15:46") + dt.timedelta(seconds=40))
        self.at(TH.et("2026-10-20", "15:47") + dt.timedelta(seconds=23))
        self.lane._redecide.add(("close", MON))
        made = self.decisions()
        with self.flaky(fail_first=False):
            self.lane.run()
        self.assertEqual(made[0], ("close", "2026-10-20", "2026-10-20T19:48:00Z"), "the retry first, at its time")
        self.assertTrue(all(when >= "2026-10-20T19:48:00Z" for _, _, when in made))
        [_, ok] = self.receipts("decide-close:2026-10-20")
        self.assertEqual((ok["status"], ok["started_at"]), ("ok", "2026-10-20T19:48:00Z"))

    def test_inside_the_lead_every_other_task_ends_before_the_retry(self):
        with self.store() as st:
            at = TH.et("2026-10-20", "15:47")
            rid = st.start_receipt("decide-close:2026-10-20", now=at)
            st.finish_receipt(rid, "failed", {"why": "OSError: invented"}, now=at + dt.timedelta(seconds=2))
            now = at + dt.timedelta(seconds=10)
            self.at(now)
            task = H.Task("record", lambda ctx, deadline: {}, H.RECORD_BUDGET)
            bound = self.lane._deadline(st, now, task) - self.mono()
            self.assertAlmostEqual(bound, 60 - 10 - H.DECISION_MARGIN, places=3,
                                   msg="to end DECISION_MARGIN before the retry at 15:48:00, not RECORD_BUDGET")
            self.assertEqual(self.lane._close_hold(st, now), at + H.DECIDE_RETRY, "the held turn waits for the retry")
            self.assertEqual(self.lane._lead(st, now), at, "a failed run keeps the lead")
            for status, keeps in (("cut", True), ("running", True), ("pending", False), ("ok", False)):
                rid = st.start_receipt("decide-close:2026-10-20", now=now)
                if status != "running":
                    st.finish_receipt(rid, status, {}, now=now)
                self.assertEqual(self.lane._lead(st, now) is not None, keeps, status)
                st.db.execute("DELETE FROM receipts WHERE id=?", (rid,))
            late = TH.et("2026-10-20", "15:46") + H.LIVE_WITHIN + dt.timedelta(seconds=1)
            self.assertIsNone(self.lane._lead(st, late), "no longer live: its last retry has passed")
            with mock.patch.object(R, "five_programs", return_value=[]):
                self.assertIsNone(self.lane._lead(st, now), "no PREREG-EVL-5 rows: no lead")


# ------------------------------------------------------------------------------------------------- (5) the room
@on_1019h
class TheRoomOnceOverdue(TB.EventTest):
    """(5) THE CAPTAIN'S DECISION on PREREG-EVL-5's money re-review (option 1): once the lane's close receipt is still
    unfinished one book minute before the close window's cut-off (15:48:00 ET on a full day), a waiting PREREG-EVL-5
    buy keeps no room from a row of PREREG-EVL-1 to -4 after it in ROOM's order (it still keeps it from R3's births);
    the post-close alert is a warning when a PREREG row waited for that room and ended unsent. Invented figures as
    TheRoomWhileItWaits' ($45 free: one learning buy of two shares at $20.00 fits, two do not)."""

    fall = T5.TheRoomWhileItWaits.fall
    birth = T5.TheRoomWhileItWaits.birth
    receipt = T5.TheRoomWhileItWaits.receipt
    sent = T5.TheRoomWhileItWaits.sent
    buy = T5.TheRoomWhileItWaits.buy

    def setUp(self):
        super().setUp()
        self.addCleanup(P.load_births, None)

    def probe_then_learning(self) -> TB.Harness:
        h = self.harness()
        h.options.reserved_usd = 1905.0
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)                # EVL-ERN-DROP-ON at Probe
        self.fall(h, "GAMA", TB.CIK3, "e-3", 16.8, score=0)      # EVL-ERN-REACT-C1 at learning
        h.lane.band("EVL-ERN-DROP-ON", "probe", version=1)
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16)):
            h.tick(hh, mm)
        return h

    def alerts(self, h: TB.Harness) -> list[str]:
        return [level for level, text in h.alerts if "PREREG-EVL-5" in text]

    def test_an_earlier_files_row_goes_once_the_receipt_is_overdue(self):
        h = self.probe_then_learning()
        for mm in (46, 47):
            h.tick(15, mm, 40)
        self.assertEqual(self.sent(h), [], "before the overdue minute ROOM holds as release 1019g built it")
        self.assertIn(L.HELD_ROOM, self.buy(h, "GAMA")["why"])
        h.tick(15, 48, 40)                                       # (one book minute before 15:49:00, no receipt)
        self.assertEqual(self.sent(h), [("GAMA", "2")], "the learning row of PREREG-EVL-1 goes with the cash")
        self.assertIn(EB.PART_WAIT, self.buy(h, "ACME")["why"], "the Probe row still waits for the lane")
        self.receipt(h, "EVL-ERN-DROP-ON")                       # (15:48:50 ET)
        h.tick(15, 49, 40)
        h.tick(16, 2, 10)
        self.assertEqual(self.buy(h, "ACME")["status"], "missed")
        [said] = [p for k, p in h.events if k == "equity.alert" and "evl5_held_unsent" in p]
        self.assertEqual((said["evl5_held_unsent"], said["room_waited"], said["room_waited_prereg"]), (1, 0, 0))
        self.assertEqual(self.alerts(h), ["info"])

    def test_a_birth_still_waits_for_the_room_once_overdue(self):
        h = self.harness()
        h.options.reserved_usd = 1905.0
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)
        self.fall(h, "BETA", TB.CIK2, "e-2", 15.44)
        born = self.birth(h)
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16)):
            h.tick(hh, mm)
        for mm in (46, 47, 48):
            h.tick(15, mm, 40)
        self.assertEqual(self.sent(h), [], "R3's birth after the waiting row still leaves it the cash")
        self.assertIn(L.HELD_ROOM, self.buy(h, "BETA")["why"])
        h.tick(15, 49, 40)
        h.tick(16, 2, 10)
        [said] = [p for k, p in h.events if k == "equity.alert" and "evl5_held_unsent" in p]
        self.assertEqual((said["room_waited"], said["room_waited_prereg"]), (1, 0))
        self.assertEqual(self.alerts(h), ["info"], "a birth that waited: info, as release 1019g said it")
        self.assertFalse(EB.room_free_overdue(born.id, born.version))

    def test_a_prereg_row_that_waited_and_ended_unsent_is_a_warning(self):
        """The book's minutes are irregular: none between 15:48:00 and the 15:49:00 cut-off (a slow tick), so the
        learning row of PREREG-EVL-1 that waited for the Probe row's room ends unsent: the alert is a warning the first
        time."""
        h = self.probe_then_learning()
        for mm in (46, 47):
            h.tick(15, mm, 40)
        h.tick(15, 49, 30)
        h.tick(16, 2, 10)
        self.assertEqual(self.buy(h, "GAMA")["status"], "missed")
        self.assertIn(L.HELD_AHEAD, self.buy(h, "GAMA")["why"])
        [said] = [p for k, p in h.events if k == "equity.alert" and "evl5_held_unsent" in p]
        self.assertEqual((said["room_waited"], said["room_waited_prereg"], said["recent"]), (1, 1, []))
        self.assertEqual(self.alerts(h), ["warning"])

    def test_the_rows_freed_are_the_earlier_files_alone(self):
        self.assertTrue(all(EB.room_free_overdue(p.id, p.version) for p in P.PREREG_PROGRAMS if p.prereg < 5))
        self.assertFalse(any(EB.room_free_overdue(p.id, p.version) for p in P.PREREG_PROGRAMS if p.prereg == 5))
        self.assertFalse(EB.room_free_overdue("EVL-NOT-A-PROGRAM", 1))
        self.assertTrue(all(EB.prereg_row(p.id, p.version) for p in P.PREREG_PROGRAMS))
        self.assertEqual(L.HELD_OVERDUE_S, 60.0)
        kept = L.HeldAhead(orders=2, held=[7, 8], overdue=True)
        self.assertEqual((kept.for_buy(True).orders, kept.for_buy(True).held), (0, []), "freed: none of the room")
        self.assertIs(kept.for_buy(False), kept, "a birth's buy: all of it")
        early = L.HeldAhead(orders=2, held=[7, 8])
        self.assertIs(early.for_buy(True), early, "before the overdue minute: all of it, for every row")


# ------------------------------------------------------------------------------------------------- (6) the docs
class TheShippedFilesAndTheDocs(unittest.TestCase):
    """(6) PREREG-EVL-5's calibration script imports PREREG-EVL-3's `calibrate_events` from ../evl-3: the tree now
    carries that file, byte for byte the tags' (`prereg-evl-3` and `prereg-evl-5` hold the same blob), and the script
    itself and PREREG-EVL-5.md are untouched; the docs say the running release and the births budget after
    PREREG-EVL-5."""

    CALIBRATE = "docs/prereg/evl-3/calibrate_events.py"

    def test_the_script_finds_the_module_it_imports(self):
        script = REPO / "docs/prereg/evl-5/calib_evl5.py"
        tree = ast.parse(script.read_text())
        inserted = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == "evl-3"]
        self.assertTrue(inserted, "the script inserts ../evl-3 on its path")
        module = script.parent.parent / "evl-3" / "calibrate_events.py"
        self.assertTrue(module.is_file(), "the module it imports is in the tree")
        self.assertEqual(module.relative_to(REPO).as_posix(), self.CALIBRATE)
        names = {n.name for n in ast.parse(module.read_text()).body if isinstance(n, ast.FunctionDef)}
        self.assertIn("signflip_p", names)
        self.assertEqual(hashlib.sha256(module.read_bytes()).hexdigest(), CALIBRATE_SHA, "the tags' bytes")
        self.assertEqual(hashlib.sha256(script.read_bytes()).hexdigest(), FROZEN["docs/prereg/evl-5/calib_evl5.py"])
        self.assertEqual(hashlib.sha256((REPO / "docs/prereg/PREREG-EVL-5.md").read_bytes()).hexdigest(),
                         FROZEN["docs/prereg/PREREG-EVL-5.md"], "the frozen file, byte for byte")

    def test_the_running_release_and_the_births_budget_are_current(self):
        changelog = (REPO / "CHANGELOG.md").read_text()
        head = changelog.split("## Not yet deployed", 1)[1].split("\n### ", 1)[0]
        self.assertIn("`20261022T053527Z-05c3dc2f4422` (release 1019g", head)
        self.assertNotIn("The running House release is `20261019T205943Z-90834d01c78d`", head)
        operations = (REPO / "docs/operations.md").read_text()
        self.assertRegex(operations, r"## Release 1019g \(Oct 22, 2026\)[^\n]*deployed 05:36Z Oct 22")
        events = (REPO / "docs/events.md").read_text()
        for stale in ("at most 18 seatable births", "eighteen seatable births", "PREREG-EVL-1 to -4's twelve use 1.2",
                      "`feat/evl-5` merged in, A94), not yet deployed"):
            self.assertNotIn(stale, events)
        self.assertNotIn("at most 18 seatable births", BI.__doc__)
        self.assertEqual(int(round(SC.LANE_BUDGET * 10)) - len(P.PREREG_SEATING) * BI.CHARGE_TENTHS, 15)
        self.assertIn("at most fifteen seatable births", events)


#: docs/prereg/evl-3/calibrate_events.py at the tags `prereg-evl-3` and `prereg-evl-5` (blob c3c42371).
CALIBRATE_SHA = "eeb7d0b19483695c54d8bb9268aa9877c5896e6c8252dc306daef5d07b909d92"
#: The frozen files of PREREG-EVL-5 (A92; league/tests/test_events_evl5.py pins the same).
FROZEN = {"docs/prereg/PREREG-EVL-5.md": "48b19fdeb0059cb9ee4c48784cce1de2d543e692fd2df47882c3fef764aabdf4",
          "docs/prereg/evl-5/calib_evl5.py": "b33b2738d09821b3d883271e180c72f61b13f22a8d30239bb519dfdd9d7f73ce"}


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
