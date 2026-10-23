"""THE DECISION SCHEDULER (release 1019i, A120; league/events/scheduler.py): one pre-registered slot per file at each
auction. The timing table's invariants and its pinned main rows; the House's lane running a file's slot in its own
run with its own bound from its own start, in the same turn as the main decision's receipt, a slot before the main
decision bounded to end before it, a missed slot's receipt and alarm, the catch-up by itself; the book's per-file
pass and per-file send window; and THE SIMULATION on an invented session with every part at its worst bound: every
send before its line, the main rows' intents and picks byte-identical to the path with no file registered."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import unittest
from decimal import Decimal as D_
from unittest import mock

from league.equity import live as L
from league.equity import schedule as ES
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import programs as P
from league.events import run as R
from league.events import scheduler as X
from league.events import store as S
from league.tests import test_events_book as TB
from league.tests import test_events_evl5 as T5
from league.tests import test_events_house as TH
from league.tests.evl6_fakes import on_1019h
from league.tests.v2_walls import on_v2

NY = C.NY
UTC = dt.timezone.utc
DAY = "2026-10-20"


def wall(hhmmss: str, anchor: str = "close") -> X.Wall:
    """A Wall from a full day's New York time, anchored on the open (09:30) or the close (16:00)."""
    h, m, s = (int(x) for x in hhmmss.split(":"))
    base = 9 * 3600 + 30 * 60 if anchor == "open" else 16 * 3600
    return X.Wall(anchor, h * 3600 + m * 60 + s - base)


def with_rows(close: tuple[X.Slot, ...] = (), open_: tuple[X.Slot, ...] = ()) -> dict[str, tuple[X.Slot, ...]]:
    main_open, main_close = X.main_rows()
    return {"open": (main_open, *open_), "close": (main_close, *close)}


# ------------------------------------------------------------------------------------------------------ the table
class TheTable(unittest.TestCase):
    def test_the_pinned_table_holds_its_invariants_and_its_main_rows_are_todays_constants(self):
        self.assertEqual(X.check(), [])
        self.assertEqual([s.file for s in X.slots("open")], ["main"])
        # (release 1019n-r2: PREREG-EVL-10's frozen row is the close table's LAST row, its section 2.4's Slot exactly)
        self.assertEqual([s.file for s in X.slots("close")], ["main", "evl10"])
        self.assertEqual(X.slot("evl10", "close"), X.Slot("evl10", "close", 10.0, "close-r2", start=X.Wall("close", -1200),
                                                          never_past=X.Wall("close", -940),
                                                          send_from=X.Wall("close", -780),
                                                          send_until=X.Wall("close", -660), catchup=None))
        o, c = X.main_slot("open"), X.main_slot("close")
        self.assertEqual(o.start.text(), "09:15:00")
        self.assertEqual((o.send_from.text(), o.send_until.text()), ("09:16:00", "09:27:00"))
        self.assertEqual(c.start.text(), "15:47:00")
        self.assertEqual((c.send_from.text(), c.send_until.text()), ("15:47:00", "15:49:00"))
        self.assertEqual(c.start.text(early=True), "12:47:00", "an early close moves every close-side row")
        self.assertEqual(o.bound, H.DECIDE_BUDGET)
        self.assertEqual(c.bound, H.DECIDE_BUDGET)
        # the rows are the House's and the book's own constants, never literals of their own
        self.assertEqual(o.start, X.Wall("open", -900))
        self.assertEqual(C.OPEN_DECIDE_AT, dt.time(9, 15))
        self.assertEqual(c.start.seconds, -int(C.CLOSE_DECIDE_BEFORE.total_seconds()) + int(H.CLOSE_GRACE.total_seconds()))
        off = ES.EVENT_DEFAULTS
        self.assertEqual((o.send_from.seconds, o.send_until.seconds),
                         (-off["open_send_before_open_s"], -off["open_until_before_open_s"]))
        self.assertEqual((c.send_from.seconds, c.send_until.seconds),
                         (-off["close_send_before_close_s"], -off["close_until_before_close_s"]))
        self.assertEqual((o.kind, c.kind, o.catchup, c.catchup), ("open", "close", None, None))
        self.assertEqual((o.receipt(dt.date(2026, 10, 20)), c.receipt(dt.date(2026, 10, 20))),
                         ("decide-open:2026-10-20", "decide-close:2026-10-20"))

    def test_the_digest_is_pinned(self):
        """The table is one pinned constant per auction: a row that moves moves this digest (update it with the
        docs' timing table, docs/events.md)."""
        self.assertEqual(X.digest()[:8], "3514111b", X.canonical())
        # (release 1019n-r2: the main rows alone, as release 1019i's table had them, still read 40a08163)
        self.assertEqual(X.digest({"open": (X.main_slot("open"),), "close": (X.main_slot("close"),)})[:8], "40a08163")

    def test_check_refuses_a_slot_that_sends_after_the_cut_off_or_runs_into_the_main_decision(self):
        late = X.Slot("f", "close", 30.0, "close-f", after=("main",), never_past=wall("15:48:30"),
                      send_from=wall("15:47:00"), send_until=wall("15:49:30"), catchup="close-f-cu")
        self.assertIn("close: f sends after the auction's cut-off 15:49:00", X.check(with_rows((late,))))
        into = X.Slot("g", "close", 50.0, "close-g", start=wall("15:46:00"), never_past=wall("15:46:10"),
                      send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-g-cu")
        [problem] = [p for p in X.check(with_rows((into,))) if p.startswith("close: g starts before")]
        self.assertIn("can run into it", problem)
        fine = dataclasses.replace(into, bound=40.0)
        self.assertEqual(X.check(with_rows((fine,))), [])
        follower = X.Slot("h", "close", 10.0, "close-h", after=("zzz",), never_past=wall("15:48:40"),
                          send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-h-cu")
        self.assertIn("close: h follows zzz, which is not an earlier row", X.check(with_rows((follower,))))
        twice = X.Slot("f", "close", 30.0, "close-f2", after=("main",), never_past=wall("15:48:30"),
                       send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-f2-cu")
        self.assertIn("close: f has two rows", X.check(with_rows((dataclasses.replace(late, send_until=wall("15:49:00")), twice))))
        no_never = dataclasses.replace(late, send_until=wall("15:49:00"), never_past=None)
        self.assertIn("close: f has no never_past (a slot must be missable)", X.check(with_rows((no_never,))))
        pre = X.Slot("p", "open", 60.0, "prepass-p:open", start=wall("09:00:00", "open"), never_past=wall("09:13:00", "open"),
                     prepass=True)
        self.assertEqual(X.check(with_rows(open_=(pre,))), [])
        self.assertEqual(pre.job, "prepass-p:open", "a pre-pass's receipt is its kind itself")

    def test_a_follower_starts_on_the_receipts_it_follows_and_an_early_close_moves_every_close_row(self):
        session = C.Session(dt.date(2026, 11, 27), TH.et("2026-11-27", "09:30"), TH.et("2026-11-27", "13:00"), True)
        s = X.Slot("f", "close", 120.0, "close-f", after=("main",), never_past=wall("15:48:40"),
                   send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-f-cu")
        self.assertEqual(X.window(s, session, {"main": None}), (None, TH.et("2026-11-27", "12:48") + dt.timedelta(seconds=40)))
        at = TH.et("2026-11-27", "12:47") + dt.timedelta(seconds=31)
        self.assertEqual(X.window(s, session, {"main": at})[0], at)
        clamped = dataclasses.replace(s, not_before=wall("15:48:00"))
        self.assertEqual(X.window(clamped, session, {"main": at})[0], TH.et("2026-11-27", "12:48"))
        self.assertEqual(X.main_slot("close").start.at(session), TH.et("2026-11-27", "12:47"))
        open_at, close_at = session.open_at.timestamp(), session.close_at.timestamp()
        self.assertEqual(X.send_window(s, open_at, close_at), (TH.et("2026-11-27", "12:47").timestamp(),
                                                              TH.et("2026-11-27", "12:49").timestamp()))

    def test_worst_case_states_which_slots_cannot_fit_on_a_bad_day(self):
        lrn = X.Slot("lrn", "close", 120.0, "close-lrn", after=("main",), never_past=wall("15:49:30"),
                     send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-lrn-cu")
        meta = X.Slot("meta", "close", 15.0, "close-meta", after=("main",), never_past=wall("15:48:40"),
                      send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-meta-cu")
        table = with_rows((lrn, meta))
        self.assertEqual(X.check(table), [])
        rows = {r["file"]: r for r in X.worst_case("close", table)}
        self.assertEqual(rows["main"]["finish"], "15:49:30")
        self.assertEqual((rows["lrn"]["start"], rows["lrn"]["finish"], rows["lrn"]["sends_fit_at_worst"]),
                         ("15:49:30", "15:51:30", False))
        self.assertTrue(rows["meta"]["missed_at_worst"], "a 15 s slot that must start by 15:48:40 is missed at the worst")
        text = X.table_text(table)
        self.assertIn("| lrn | on main's receipt | 15:49:30 | 120 s | 15:47:00-15:49:00 | `decide-close-lrn:<day>` | "
                      "`decide-close-lrn-cu:<day>` | main |", text)

    def test_file_of_reads_the_registered_parts(self):
        self.assertEqual(X.file_of("EVL-ERN-READ-O1"), "main")
        X.register(X.Part("sim", run=lambda *a: {}, programs=lambda: ("EVL-ERN-DROP-ON",), since=lambda: None))
        self.addCleanup(X.unregister, "sim")
        self.assertEqual(X.file_of("EVL-ERN-DROP-ON"), "sim")
        self.assertEqual(X.file_of(P.BY_KEY[("EVL-ERN-DROP-ON", 1)]), "sim")
        self.assertEqual([s.file for s in X.live_files("close")], ["evl10"],
                         "a part with no `since` runs nothing, even with a row (PREREG-EVL-10's, pinned, runs)")
        with self.assertRaises(ValueError):
            X.register(X.Part("main", run=lambda *a: {}))


# ---------------------------------------------------------------------------------------------- the House's lane
class SimCase(TH.LaneCase):
    """A lane whose sleep moves the House's clock (the held turn), a registered part `sim` whose live run SLEEPS ITS
    WHOLE BOUND (the worst case) and a part `pre` before the main decision, with their rows in the table."""

    SINCE = "2026-10-20T00:00:00Z"

    def setUp(self):
        super().setUp()
        self.ran: list[tuple[str, str]] = []
        self.parts: list[dict] = []
        self.table = with_rows()
        patch = mock.patch.dict(X.TABLE, self.table, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(X.unregister, "sim")
        self.addCleanup(X.unregister, "pre")
        self.addCleanup(X.unregister, "second")

    def new_lane(self, redecide=False, **settings):
        lane = super().new_lane(redecide, **settings)

        def sleep(seconds: float) -> None:
            self.mono.advance(seconds)
            self.clock.advance(seconds)
        lane._sleep = sleep
        self.ran = []
        note = lane._note

        def noted(name, status, summary, began):
            self.ran.append((name, S.iso(lane.now())))
            return note(name, status, summary, began)
        lane._note = noted
        return lane

    def rows(self, *rows: X.Slot, auction: str = "close") -> None:
        X.TABLE[auction] = (X.main_slot(auction), *rows)
        self.assertEqual(X.check(), [])

    def part(self, file: str, *, sleep: float | None = None, fail: bool = False, programs=(), catchup=True) -> X.Part:
        case = self

        def run(ctx, day, auction, slot, rid):
            began = ctx.mono()
            case.parts.append({"file": file, "day": day.isoformat(), "auction": auction, "started": S.iso(ctx.now()),
                               "deadline_in": None if ctx.deadline is None else round(ctx.deadline - began, 3),
                               "kind": "live"})
            if fail:
                raise RuntimeError("the part broke")
            if sleep is not None:
                case.mono.advance(sleep)
                case.clock.advance(sleep)
            if sleep is not None and ctx.deadline is not None and ctx.mono() > ctx.deadline:
                raise R.Deadline("the part's own bound")
            return {f"{file}-program": {"planned": 1}, "took": sleep}

        def later(ctx, day, auction, slot, rid):
            case.parts.append({"file": file, "day": day.isoformat(), "auction": auction, "kind": "catchup"})
            return {f"{file}-program": {"planned": 1}, "catchup": True}
        part = X.Part(file, run=run, catchup=later if catchup else None, programs=lambda: tuple(programs),
                      since=lambda: S.parse_iso(case.SINCE))
        X.register(part)
        return part

    def opened(self, day: str = DAY) -> None:
        with self.store() as st:
            rid = st.start_receipt(f"decide-open:{day}", now=TH.et(day, "09:15"))
            st.finish_receipt(rid, "ok", {}, now=TH.et(day, "09:16"))

    def receipt(self, job: str) -> dict:
        rows = self.receipts(job)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def main_summary(self) -> str:
        return self.receipt(f"decide-close:{DAY}")["summary"]


class TheSlotsInTheHeldTurn(SimCase):
    SIM = X.Slot("sim", "close", 20.0, "close-sim", after=("main",), never_past=wall("15:49:30"),
                 send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-sim-cu")
    PRE = X.Slot("pre", "close", 40.0, "close-pre", start=wall("15:46:00"), never_past=wall("15:46:10"),
                 send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-pre-cu")

    def test_every_part_at_its_worst_bound_runs_in_its_own_slot_and_the_main_decision_keeps_its_time(self):
        """THE SIMULATION: `pre` (40 s, before the main decision) sleeps its whole bound, the main close decision
        starts at 15:47:00 exactly as today, and `sim` (20 s) starts on the main receipt's finish in the same turn
        with its own 20 s from its own start; the main receipt's summary is byte-identical to a lane with no part."""
        self.opened()
        self.at(TH.et(DAY, "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()                                     # (no part registered: today's path)
        before = self.main_summary()
        plain = [(n, at) for n, at in self.ran]
        self.assertEqual(plain[-1][0], "decide-close")
        # the same session again, with the two parts and their rows
        self.tearDown()
        self.setUp()
        self.rows(self.PRE, self.SIM)
        self.part("pre", sleep=40.0)
        self.part("sim", sleep=20.0)
        self.opened()
        self.at(TH.et(DAY, "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()
        names = [n for n, _ in self.ran]
        self.assertEqual(names[-2:], ["decide-close", "slot-close-sim"], names)
        self.assertLess(names.index("slot-close-pre"), names.index("decide-close"), names)
        self.assertIn("record", names[names.index("slot-close-pre"):], "the record pass due at 15:46:40 still ran in the lead")
        main = self.receipt(f"decide-close:{DAY}")
        self.assertEqual(main["started_at"], TH.et(DAY, "15:47").strftime("%Y-%m-%dT%H:%M:%SZ"), "at 15:47:00, as today")
        self.assertEqual(main["summary"], before, "the main receipt is byte-identical to the path with no part")
        pre = self.receipt(f"decide-close-pre:{DAY}")
        self.assertEqual((pre["started_at"], pre["status"]), (TH.et(DAY, "15:46").strftime("%Y-%m-%dT%H:%M:%SZ"), "ok"))
        self.assertLessEqual(pre["finished_at"], TH.et(DAY, "15:46").strftime("%Y-%m-%dT%H:%M:%SZ").replace("46:00", "46:40"))
        sim = self.receipt(f"decide-close-sim:{DAY}")
        self.assertEqual(sim["started_at"], main["finished_at"], "the follower starts on the main receipt's finish")
        self.assertEqual(sim["status"], "ok")
        self.assertEqual(S.parse_iso(sim["finished_at"]) - S.parse_iso(sim["started_at"]), dt.timedelta(seconds=20))
        summary = json.loads(sim["summary"])
        self.assertEqual(summary["sim-program"], {"planned": 1})
        self.assertEqual(summary["slot"]["bound"], 20.0)
        [pre_part, sim_part] = self.parts
        self.assertLessEqual(pre_part["deadline_in"], 40.0, "its own bound from its own start")
        self.assertEqual(sim_part["deadline_in"], 20.0, "the follower's bound is its own, never the main decision's")
        self.assertLess(S.parse_iso(sim["finished_at"]), TH.et(DAY, "15:49"), "before the send line")
        self.assertIsNone(self.lane.health()["running"])
        self.assertEqual(self.lane.health()["slots"]["close-sim"]["status"], "ok")
        self.assertEqual(self.lane.health()["timing_table"], X.digest()[:8])
        self.assertEqual(self.house.levels(), ["info"], "no alarm: every slot ran")

    def test_a_slot_before_the_main_decision_is_bounded_to_end_before_it(self):
        """`pre` at 15:46:00 with a part that would run 60 s: the task's bound ends it DECISION_MARGIN before 15:47:00
        (a read past it is cut, the receipt `cut`, final) and the main decision still starts at 15:47:00."""
        self.rows(self.PRE, self.SIM)
        self.part("pre", sleep=60.0)
        self.part("sim", sleep=1.0)
        self.opened()
        self.at(TH.et(DAY, "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()
        [pre_part] = [p for p in self.parts if p["file"] == "pre"]
        self.assertLessEqual(pre_part["deadline_in"], 55.0, "never into the main decision's margin")
        pre = self.receipt(f"decide-close-pre:{DAY}")
        self.assertEqual(pre["status"], "cut")
        self.assertIn("ran past its own bound", json.loads(pre["summary"])["why"])
        main = self.receipt(f"decide-close:{DAY}")
        self.assertEqual(main["started_at"], TH.et(DAY, "15:47").strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(main["status"], "ok")
        self.assertEqual(self.receipt(f"decide-close-sim:{DAY}")["status"], "ok")
        self.assertIn(("warning", mock.ANY), [(lvl, mock.ANY) for lvl, _ in self.house.alerts])
        [text] = [t for lvl, t in self.house.alerts if lvl == "warning"]
        self.assertIn("decision slot pre close", text)

    def test_a_part_that_fails_is_final_for_the_auction_and_the_catch_up_decides_it_later(self):
        self.rows(self.SIM)
        self.part("sim", fail=True)
        self.opened()
        self.at(TH.et(DAY, "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()
        sim = self.receipt(f"decide-close-sim:{DAY}")
        self.assertEqual(sim["status"], "failed")
        self.assertIn("RuntimeError: the part broke", json.loads(sim["summary"])["why"])
        [text] = [t for lvl, t in self.house.alerts if lvl == "warning"]
        self.assertIn("decided later by itself (decide-close-sim-cu)", text)
        # no retry inside the window: the next turn runs no slot
        self.at(TH.et(DAY, "15:48"))
        self.lane._next_look = float("-inf")
        self.lane.run()
        self.assertEqual(len(self.receipts(f"decide-close-sim:{DAY}")), 1)
        # the catch-up, after the window, after the record pass, once
        self.at(TH.et(DAY, "16:30"))
        with self.store() as st:
            rid = st.start_receipt("record", now=self.clock_dt())
            st.finish_receipt(rid, "ok", {}, now=self.clock_dt())
        self.lane._next_look = float("-inf")
        self.lane.run()
        cu = self.receipt(f"decide-close-sim-cu:{DAY}")
        self.assertEqual(cu["status"], "ok")
        self.assertEqual(json.loads(cu["summary"])["catchup"], True)
        self.assertEqual([p["kind"] for p in self.parts], ["live", "catchup"])
        self.lane._next_look = float("-inf")
        self.lane.run()
        self.assertEqual(len(self.receipts(f"decide-close-sim-cu:{DAY}")), 1, "a written decision is never decided again")

    def test_a_slot_whose_window_closed_with_no_run_is_missed_with_a_receipt_and_an_alarm(self):
        """The lane was down from 15:44 to 15:50: the main decision is made late (still live), `sim`'s window
        (never past 15:49:30) has closed: a `missed` receipt, a warning, and the catch-up owed."""
        self.rows(self.SIM)
        self.part("sim", sleep=1.0)
        self.opened()
        self.at(TH.et(DAY, "15:50"))
        self.mark_recorded()
        self.lane.run()
        self.assertEqual(self.receipt(f"decide-close:{DAY}")["status"], "ok")
        self.lane._next_look = float("-inf")
        self.lane.run()
        sim = self.receipt(f"decide-close-sim:{DAY}")
        self.assertEqual(sim["status"], "missed")
        self.assertIn("closed with no run of it", json.loads(sim["summary"])["why"])
        [text] = [t for lvl, t in self.house.alerts if lvl == "warning"]
        self.assertIn("decision slot sim close", text)
        self.assertIn("never traded at that auction", text)
        self.assertEqual(self.lane.health()["slots"]["close-sim"]["status"], "missed")
        self.assertEqual([p["kind"] for p in self.parts], ["catchup"], "no live run; the catch-up owed at once")
        self.assertEqual(self.receipt(f"decide-close-sim-cu:{DAY}")["status"], "ok")
        with self.store() as st:
            task = self.lane._slot_catchup_due(st, self.clock_dt(), dt.date(2026, 10, 20),
                                               self.lane._decide_receipts(st, self.clock_dt()), [])
        self.assertIsNone(task, "once")

    def test_an_auction_before_the_parts_registration_is_neither_run_nor_missed(self):
        """`sim` registered at 16:00 ET of the day: today's close slot (15:47) was never its; no run, no `missed`
        receipt, no alarm, and no catch-up owed for it."""
        self.rows(self.SIM)
        self.SINCE = TH.et(DAY, "16:00").strftime("%Y-%m-%dT%H:%M:%SZ")
        self.part("sim", sleep=1.0)
        self.opened()
        with self.store() as st:
            rid = st.start_receipt(f"decide-close:{DAY}", now=TH.et(DAY, "15:47"))
            st.finish_receipt(rid, "ok", {}, now=TH.et(DAY, "15:47") + dt.timedelta(seconds=20))
        self.at(TH.et(DAY, "16:30"))
        self.mark_recorded()
        for _ in range(4):
            self.lane._next_look = float("-inf")
            self.lane.run()
        self.assertEqual(self.receipts(f"decide-close-sim:{DAY}"), [])
        self.assertEqual(self.receipts(f"decide-close-sim-cu:{DAY}"), [])
        self.assertEqual(self.parts, [])
        self.assertNotIn("warning", self.house.levels())

    def test_a_second_file_follows_the_first_and_never_waits_for_its_outcome(self):
        """`second` follows `sim`: it starts when `sim`'s receipt is finished, whatever that status (`sim` fails)."""
        second = X.Slot("second", "close", 10.0, "close-second", after=("sim",), never_past=wall("15:49:30"),
                        send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-second-cu")
        self.rows(self.SIM, second)
        self.part("sim", fail=True)
        self.part("second", sleep=5.0)
        self.opened()
        self.at(TH.et(DAY, "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()
        sim = self.receipt(f"decide-close-sim:{DAY}")
        two = self.receipt(f"decide-close-second:{DAY}")
        self.assertEqual((sim["status"], two["status"]), ("failed", "ok"))
        self.assertEqual(two["started_at"], sim["finished_at"])
        self.assertEqual([n for n, _ in self.ran][-3:], ["decide-close", "slot-close-sim", "slot-close-second"])

    def test_an_open_slot_runs_on_the_open_receipt_in_the_same_turn(self):
        morning = X.Slot("sim", "open", 30.0, "open-sim", after=("main",), never_past=wall("09:25:00", "open"),
                         send_from=wall("09:16:00", "open"), send_until=wall("09:27:00", "open"), catchup="open-sim-cu")
        self.rows(morning, auction="open")
        self.part("sim", sleep=30.0)
        self.at(TH.et(DAY, "09:15") + dt.timedelta(seconds=20))
        self.mark_recorded()
        self.lane.run()
        names = [n for n, _ in self.ran]
        self.assertEqual(names[-2:], ["decide-open", "slot-open-sim"], names)
        sim = self.receipt(f"decide-open-sim:{DAY}")
        self.assertEqual(sim["started_at"], self.receipt(f"decide-open:{DAY}")["finished_at"])
        self.assertLess(S.parse_iso(sim["finished_at"]), TH.et(DAY, "09:27"))

    def test_a_pending_slot_receipt_is_never_a_verdict_pass(self):
        """A file's slot receipt finished `pending` (its part waits on its own verdicts) is the file's; the lane's
        verdict targets never read it as a decision kind of their own."""
        self.rows(self.SIM)
        self.part("sim", sleep=1.0)
        self.opened()
        with self.store() as st:
            rid = st.start_receipt(f"decide-close-sim:2026-10-19", now=TH.et("2026-10-19", "15:48"))
            st.finish_receipt(rid, "pending", {"sim-program": {"planned": 0}}, now=TH.et("2026-10-19", "15:48"))
            latest = self.lane._decide_receipts(st, self.clock_dt())
            session = C.session(st, dt.date(2026, 10, 20))
            urgent, early = self.lane._verdict_targets(st, TH.et(DAY, "12:00"), dt.date(2026, 10, 20), session, latest, [])
        self.assertNotEqual((urgent or ("", None, None))[0], "close-sim")


class ThePrePass(SimCase):
    def test_a_pre_pass_runs_last_inside_its_window_once(self):
        pre = X.Slot("sim", "close", 60.0, "prepass-sim:close", start=wall("15:30:00"), never_past=wall("15:43:00"),
                     prepass=True)
        self.rows(pre)
        case = self

        def prepass(ctx, day, auction, slot, rid):
            case.parts.append({"file": "sim", "kind": "prepass", "deadline_in": round(ctx.deadline - ctx.mono(), 3)})
            return {"read": 3}
        X.register(X.Part("sim", run=lambda *a: {}, prepass=prepass, since=lambda: S.parse_iso(self.SINCE)))
        self.opened()
        self.at(TH.et(DAY, "15:29"))
        self.mark_recorded()
        self.lane.run()
        self.assertEqual(self.receipts(f"prepass-sim:close:{DAY}"), [], "not before its window")
        self.at(TH.et(DAY, "15:31"))
        self.mark_recorded()
        for _ in range(8):
            self.lane._next_look = float("-inf")
            self.lane.run()
            if self.receipts(f"prepass-sim:close:{DAY}"):
                break
        got = self.receipt(f"prepass-sim:close:{DAY}")
        self.assertEqual((got["status"], json.loads(got["summary"])), ("ok", {"read": 3}))
        self.assertLessEqual(self.parts[0]["deadline_in"], 60.0)
        for _ in range(4):
            self.lane._next_look = float("-inf")
            self.lane.run()
        self.assertEqual(len(self.receipts(f"prepass-sim:close:{DAY}")), 1, "once")


# ------------------------------------------------------------------------------------------------------ the book
@on_v2
@on_1019h
class TheBooksPasses(TB.EventTest):
    """The book: the main pass plans only main programs (byte-identical to the path with no file registered), a
    file's pass plans its buys once its slot receipt is made, inside its own send window, after every main row."""

    SIM = X.Slot("sim", "close", 20.0, "close-sim", after=("main",), never_past=wall("15:49:30"),
                 send_from=wall("15:47:00"), send_until=wall("15:49:00"), catchup="close-sim-cu")

    def setUp(self):
        super().setUp()
        self.addCleanup(P.load_births, None)
        patch = mock.patch.dict(X.TABLE, with_rows(), clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(X.unregister, "sim")

    def claim(self, slot: X.Slot = SIM, *programs: str) -> None:
        X.TABLE["close"] = (X.main_slot("close"), slot)
        self.assertEqual(X.check(), [])
        X.register(X.Part("sim", run=lambda *a: {}, catchup=lambda *a: {}, programs=lambda: tuple(programs),
                          since=lambda: TH.et("2026-10-19", "12:00")))

    def fall(self, h: TB.Harness, symbol: str, cik: str, acc: str, mark: float, *, score: int = 1) -> None:
        T5.TheRoomWhileItWaits.fall(self, h, symbol, cik, acc, mark, score=score)

    def slot_receipt(self, h: TB.Harness, status: str = "ok", *names: str, when: tuple[int, int, int] = (15, 47, 40)) -> None:
        when_dt = dt.datetime.fromtimestamp(TB.at(TB.DAY, *when), UTC)
        rid = h.lane.st.start_receipt(f"decide-close-sim:{TB.DAY.isoformat()}", now=when_dt)
        h.lane.st.finish_receipt(rid, status, {name: {"planned": 1} for name in names}, now=when_dt)

    def sent(self, h: TB.Harness) -> list[tuple[str, str]]:
        return [(b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy"]

    def main_rows(self, h: TB.Harness) -> list[tuple]:
        return [(r["program"], r["symbol"], r["status"], r["limit_px"], r["rank_key"]) for r in h.event_intents("buy")
                if X.file_of(r["program"]) == "main"]

    def decision(self, h: TB.Harness, at: str) -> dict:
        [row] = h.state.rows("SELECT * FROM eq_event_decisions WHERE day=? AND at=?", (TB.DAY.isoformat(), at))
        return json.loads(row["summary"]) | {"status": row["status"]}

    def world(self, h: TB.Harness) -> None:
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)               # 0.95: EVL-ERN-DROP-ON (PREREG-EVL-5, learning)
        self.fall(h, "GAMA", TB.CIK3, "e-3", 16.8, score=0)     # 1.05: EVL-ERN-REACT-C1 (PREREG-EVL-2, learning)
        h.lane.decided(TB.DAY, "open")
        rid = h.lane.st.start_receipt(f"decide-close:{TB.DAY.isoformat()}")
        h.lane.st.finish_receipt(rid, "ok", {"EVL-ERN-DROP-ON": {"planned": 1}, "EVL-ERN-REACT-C1": {"planned": 1}})

    def test_the_main_pass_is_byte_identical_and_the_file_sends_inside_its_window_after_the_main_rows(self):
        h = self.harness()
        self.world(h)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        plain_rows, plain_summary = self.main_rows(h), self.decision(h, "close")
        plain_sent = self.sent(h)
        self.assertEqual(sorted(s for s, _ in plain_sent), ["ACME", "GAMA"], "no file registered: today's path")
        # the same world with EVL-ERN-DROP-ON claimed by the file `sim`
        h.state.close()
        h.lane.st.close()
        self.setUp()
        self.claim(self.SIM, "EVL-ERN-DROP-ON")
        h = self.harness()
        self.world(h)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            out = h.tick(hh, mm)
        self.assertEqual(self.main_rows(h), [r for r in plain_rows if r[0] != "EVL-ERN-DROP-ON"],
                         "the main rows' intents are byte-identical")
        mine = self.decision(h, "close")
        self.assertEqual({k: v for k, v in mine["programs"].items() if k != "EVL-ERN-DROP-ON"},
                         {k: v for k, v in plain_summary["programs"].items() if k != "EVL-ERN-DROP-ON"})
        self.assertNotIn("EVL-ERN-DROP-ON", mine["programs"], "the file's program is not the main pass's")
        self.assertEqual(self.sent(h), [("GAMA", "2")], "the main row went at 15:47; the file waits for its receipt")
        self.assertIn(L.EVENT_SLOT_WAIT, str(out.get("event_decide_sim")))
        self.slot_receipt(h, "ok", "EVL-ERN-DROP-ON", when=(15, 47, 40))
        h.tick(15, 48)
        self.assertEqual(self.sent(h), [("GAMA", "2"), ("ACME", "2")], "the file's buy, after every main row, in its window")
        sim = self.decision(h, "close-sim")
        self.assertEqual((sim["status"], sim["file"], sim["programs"]["EVL-ERN-DROP-ON"]["planned"]), ("done", "sim", 1))
        [acme] = [r for r in h.event_intents("buy") if r["symbol"] == "ACME"]
        self.assertEqual((acme["program"], acme["status"]), ("EVL-ERN-DROP-ON", "sent"))
        h.tick(15, 49)
        self.assertEqual(len(self.sent(h)), 2, "nothing at or after the line")

    def test_a_receipt_that_is_final_without_being_made_trades_nothing_and_a_window_that_closed_trades_nothing(self):
        self.claim(self.SIM, "EVL-ERN-DROP-ON")
        h = self.harness()
        self.world(h)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.slot_receipt(h, "cut", when=(15, 47, 30))
        out = h.tick(15, 48)
        self.assertEqual(self.sent(h), [("GAMA", "2")])
        sim = self.decision(h, "close-sim")
        self.assertEqual(sim["status"], "done")
        self.assertIn("is cut: its rows are decided later by themselves and never traded", sim["why"])
        self.assertIn("never traded", str(out.get("event_decide_sim")))
        # a narrower window that closed before the receipt
        h.state.close()
        h.lane.st.close()
        self.setUp()
        narrow = dataclasses.replace(self.SIM, send_until=wall("15:48:00"))
        self.claim(narrow, "EVL-ERN-DROP-ON")
        h = self.harness()
        self.world(h)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.slot_receipt(h, "ok", "EVL-ERN-DROP-ON", when=(15, 47, 50))
        h.tick(15, 48)
        self.assertEqual(self.sent(h), [("GAMA", "2")], "its window closed at 15:48:00: nothing of it is sent")
        self.assertIn("send window closed", self.decision(h, "close-sim")["why"])
        h.tick(15, 49)
        self.assertEqual(self.sent(h), [("GAMA", "2")])

    def test_a_files_buy_planned_inside_its_window_is_not_sent_after_its_own_line(self):
        """The file's line is 15:48:30: a buy planned at the 15:48 tick goes then; the 15:49 tick sends nothing."""
        narrow = dataclasses.replace(self.SIM, send_until=wall("15:48:30"))
        self.claim(narrow, "EVL-ERN-DROP-ON")
        h = self.harness()
        self.world(h)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.slot_receipt(h, "ok", "EVL-ERN-DROP-ON", when=(15, 47, 50))
        h.tick(15, 48)
        self.assertEqual(self.sent(h), [("GAMA", "2"), ("ACME", "2")])
        window = EB.send_window("sim", "close", TB.at(TB.DAY, 9, 30, 0), TB.at(TB.DAY, 16, 0, 0))
        self.assertEqual(window, (TB.at(TB.DAY, 15, 47, 0), TB.at(TB.DAY, 15, 48, 30)))
        h.tick(15, 49)
        self.assertEqual(len(self.sent(h)), 2, "nothing at or after the auction's line either")

    def test_the_adapter_reads_the_table(self):
        self.assertEqual(EB.slot_of("EVL-ERN-DROP-ON"), "main")
        self.assertEqual(EB.slot_files("close"), [])
        self.assertIsNone(EB.send_window("sim", "close", 0.0, 0.0))
        self.claim(self.SIM, "EVL-ERN-DROP-ON")
        self.assertEqual(EB.slot_of("EVL-ERN-DROP-ON"), "sim")
        self.assertEqual(EB.slot_of(P.BY_KEY[("EVL-ERN-READ-O1", 2)]), "main")
        self.assertEqual(EB.slot_files("close"), ["sim"])
        self.assertEqual(EB.slot_files("open"), [])
        self.assertEqual(EB.send_window("sim", "close", 0.0, 57600.0), (57600.0 - 780.0, 57600.0 - 660.0))
        h = self.harness()
        self.assertIsNone(EB.slot_receipt(h.lane.st, "sim", "close", TB.DAY))
        self.slot_receipt(h, "pending", "EVL-ERN-DROP-ON")
        self.assertEqual(EB.slot_receipt(h.lane.st, "sim", "close", TB.DAY), "pending")
        self.assertIsNone(EB.slot_receipt(None, "sim", "close", TB.DAY))


if __name__ == "__main__":
    unittest.main()
