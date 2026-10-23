"""PREREG-EVL-10 section 2.5's ROOM IN THE BOOK'S MINUTE (release 1019n-r2's money review, its two majors): at its own
auction "no earlier row, R3's births included, ever waits for, keeps room for or is refused for a buy of this file".

- THE TICK (major 1): every earlier row's buy of the tick (the main pass's, the learners' and R3's births', a first send,
  a retry, A80's re-send) is sent BEFORE the decision scheduler's per-file passes (league/equity/live.py
  `_event_step`), so it never waits for READER-2's reads (its picks' daily bars, the account, the eligible list); the
  passes' own work in the tick is bounded from the tick's start (`live.SLOT_TICK_S`, each request's timeout ending by
  it), so it never runs the minute into the next one (live/step.py `_loop` starts the next minute() at the next :03
  counted from the tick's END: a 15:47 tick ending past 15:48:03 skips the 15:48 minute, which carries A140's
  last-minute rule and PREREG-EVL-5's released buys).
- THE ROOM (major 2): a later file's buy is sized with the room every earlier row's buy of the auction still to go keeps
  (`_event_kept_before`: not sent yet, sent back for a reading the gateway could not make, A80's re-send), so an
  earlier row's retry never finds its cash taken by this file's buy; this file's buy waits, keeping nothing.

Invented data only (league/tests/test_events_book.py's harness: no market, no account, no store of the House's)."""

from __future__ import annotations

import contextlib
import datetime as dt
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from league.equity import live as L
from league.events import book as EB
from league.events import learner as LR
from league.events import programs as P
from league.events import screen as SN
from league.live.venue import Submitted
from league.tests import evl10_fakes as F10
from league.tests import test_events_book as TB
from league.tests import test_events_evl5 as T5
from league.tests import test_events_evl7 as T7
from league.tests import test_events_evl10 as T10

ON = T7.ON


def next_tick(ended: float) -> float:
    """When live/step.py `_loop` runs the next minute() after one that ENDED at `ended` (its own formula: the next
    minute's `MINUTE_OFFSET` counted from the end, so a tick ending past it skips that minute)."""
    from league.live.step import MINUTE_OFFSET

    wait = 60.0 - (ended % 60.0) + MINUTE_OFFSET
    if wait >= 60.0:
        wait -= 60.0
    return ended + wait


class TimedClient:
    """A venue client's timeout as league/live/venue.py's is read (`timeout`, per request), for the slow fakes below: a
    request that takes longer than it raises TimeoutError once it has taken it (the fake clock moves)."""

    def __init__(self, clock: Any, timeout: float = 20.0):
        self.clock, self.timeout, self.seen = clock, float(timeout), []

    def take(self, seconds: float) -> None:
        self.seen.append(self.timeout)
        if seconds > self.timeout:
            self.clock.set(self.clock() + self.timeout)
            raise TimeoutError("timed out")
        self.clock.set(self.clock() + seconds)


def closing(h: TB.Harness) -> None:
    h.state.close()
    h.lane.st.close()
    if h.book._event_lane is not None:
        h.book._event_lane.close()


# ------------------------------------------------------------------------------------------- the hotfix's own close
class TheHotfixClose(TB.EventTest):
    """THE CLOSE-MARKS HOTFIX'S OWN CLOSE (league/tests/test_events_close_marks.py `TheCloseEntriesGoBeforeTheLine`, A140
    live): PREREG-EVL-5's DROP buy ACME waiting for the lane's close receipt, EVL-LRN-ON's pick GAMA waiting for its own
    live receipt and the birth BETA held behind it; both receipts land at 15:47:40, so all three go at the 15:48 tick.
    With this file pinned, READER-2's live decision names DELT, which its pass plans at that same tick, after the
    learners' pass. A slow data host: the reads below take the seconds given (a request past its client's timeout ends
    at it, `TimedClient`)."""

    def setUp(self):
        super().setUp()
        T7.pin(self)
        self.addCleanup(P.load_births, None)

    def close(self, name: str, *, r2: bool, r2_bars_s: float = 0.0, other_s: float = 0.0, sync_s: float = 0.0
              ) -> tuple[dict[str, float], dict[str, Any], TB.Harness]:
        """One run of the close: ({symbol: seconds after the 15:48:03 tick's start at its buy's send}, READER-2's own
        pass row of the close, the harness). `r2_bars_s`: READER-2's daily bars read (its picks' sigma) at the 15:48
        tick; `other_s`: every other read of the market at that tick; `sync_s`: the tick's steps before the event step
        (the venue's orders read, `_sync_orders`), as a degraded host makes them."""
        root = self.root / name
        root.mkdir()
        with contextlib.nullcontext() if r2 else F10.unpinned_10():
            h = TB.Harness(root)
            try:
                room = T5.TheRoomWhileItWaits
                room.fall(self, h, "ACME", TB.CIK, "e-1", 15.2)        # 0.95: EVL-ERN-DROP-ON
                room.fall(self, h, "BETA", TB.CIK2, "e-2", 15.44)      # 0.965: the birth's alone
                born = room.birth(self, h)
                T7.TheMoney.live(self, h.lane, ON, TB.DAY, [(TB.CIK3, "GAMA", 16.0)], named=None)
                h.symbol("GAMA", last=16.4)
                h.venue.prints[("GAMA", TB.DAY.isoformat(), "close")] = Decimal("16.40")
                h.lane.decided(TB.DAY, "open")
                drop = next(p for p in EB.seatable() if p.id == "EVL-ERN-DROP-ON")
                if r2:
                    T10.r2_live(h.lane, [("0000000009", "DELT", 16.0)])
                    h.symbol("DELT", last=16.4)
                start = TB.at(TB.DAY, 15, 48, 3)
                data = h.market.client = TimedClient(h.clock, 45.0)
                h.venue.client.timeout = 20.0
                bars, sync, submit = h.market.bars, h.book._sync_orders, h.venue.submit
                stamps: dict[str, float] = {}

                def slow_bars(symbols, **kw):
                    if h.clock() >= start:
                        names = [str(s).upper() for s in symbols]
                        late = r2_bars_s if kw.get("timeframe") == "1Day" and "DELT" in names else other_s
                        if late:
                            data.take(late)
                    return bars(symbols, **kw)

                def slow_sync(now, out):
                    if sync_s and h.clock() >= start:
                        h.clock.set(h.clock() + sync_s)
                    return sync(now, out)

                def stamped(body, *, exit):
                    if body.get("side") == "buy":
                        stamps[str(body["symbol"])] = round(h.clock() - start, 1)
                    return submit(body, exit=exit)
                h.market.bars, h.book._sync_orders, h.venue.submit = slow_bars, slow_sync, stamped
                lands = dt.datetime.fromtimestamp(TB.at(TB.DAY, 15, 47, 40), dt.timezone.utc)
                for mm in (46, 47, 48):
                    if mm == 48:
                        rid = h.lane.st.start_receipt(f"decide-close:{TB.DAY.isoformat()}")
                        h.lane.st.finish_receipt(rid, "ok", {SN.program_key(drop.id, drop.version): {"planned": 1},
                                                             born.id: {"planned": 1}})
                        T7.name_live(h.lane.st, ON, TB.DAY, finished=lands)
                    h.tick(15, mm)
                return stamps, h.book._event_summary(TB.DAY.isoformat(), "close-evl10"), h
            finally:
                closing(h)

    def test_reader2s_slow_daily_bars_never_move_an_earlier_buy_of_the_hotfix_close(self):
        """The review's (a): READER-2's 1Day bars read at 20 s. Without the fix the three earlier buys moved from
        15:48:03 to 15:48:23; now each goes at the same time with and without this file, and READER-2's own buy after."""
        off, _, _ = self.close("off", r2=False, r2_bars_s=20.0)
        on, mine, _ = self.close("on", r2=True, r2_bars_s=20.0)
        self.assertEqual(set(off), {"ACME", "GAMA", "BETA"}, "the DROP buy, the learner's pick and the held birth")
        self.assertEqual({k: v for k, v in on.items() if k != "DELT"}, off, "each earlier buy at the same time")
        self.assertIn("DELT", on, "READER-2's buy, planned after them, goes after them")
        self.assertGreaterEqual(on["DELT"], max(off.values()))
        self.assertEqual(mine["programs"][P.R2_ON]["planned"], 1)

    def test_on_a_degraded_host_every_earlier_buy_goes_as_without_this_file_and_none_is_lost(self):
        """The review's (b): the tick's earlier steps at 20 s and every read at 19 s. Without the fix all three earlier
        buys were lost with READER-2 (sent after its 19 s read, past the window's cut-off). Now they go at the same time
        as without it; READER-2's pass, with too little of the tick's bound left at the window's last book minute,
        plans none (its window row, (e))."""
        off, _, _ = self.close("off", r2=False, r2_bars_s=19.0, other_s=19.0, sync_s=20.0)
        on, mine, _ = self.close("on", r2=True, r2_bars_s=19.0, other_s=19.0, sync_s=20.0)
        self.assertEqual(set(off), {"ACME", "GAMA", "BETA"})
        self.assertEqual(on, off, "the same three, at the same times; nothing of this file")
        row = mine["programs"][P.R2_ON]
        self.assertEqual((row["planned"], row["binding"]), (0, L.EVENT_SLOT_WINDOW))
        self.assertIn(L.SLOT_BOUND, mine["why"])


# --------------------------------------------------------------------------------------------------- the tick bound
class TheTickBound(TB.EventTest):
    """THE 15:47 TICK OF A CLOSE (the lane's close decision made by the book's main pass at 15:47:03 after its wait):
    EVL-NEWS-READ-ON's BETA (a main row) and READER-2's GAMA, planned in its own pass at the same tick."""

    def setUp(self):
        super().setUp()
        T7.pin(self, None)
        self.addCleanup(P.load_births, None)

    def day(self, name: str, *, r2: bool, main_s: float = 0.0, r2_s: float = 0.0, data_timeout: float = 45.0
            ) -> tuple[dict[str, float], float, float, TB.Harness, TimedClient]:
        """({symbol: seconds after 15:47:03 at its buy's send}, when the 15:47 tick ended, when live/step.py runs the
        next one, the harness, the data client). `main_s`: each market read of the tick that is not READER-2's daily
        bars; `r2_s`: READER-2's (its picks' sigma). Each honours the data client's timeout (`TimedClient`)."""
        with contextlib.nullcontext() if r2 else F10.unpinned_10():
            return self._day(name, main_s=main_s, r2_s=r2_s, data_timeout=data_timeout)

    def _day(self, name: str, *, main_s: float, r2_s: float, data_timeout: float
             ) -> tuple[dict[str, float], float, float, TB.Harness, TimedClient]:
        root = self.root / name
        root.mkdir()
        h = TB.Harness(root)
        self.addCleanup(closing, h)
        LR.ensure(h.lane.st.db)
        T10.day_news(h.lane, "n-1", "BETA", TB.CIK2)
        T10.r2_live(h.lane, [(TB.CIK3, "GAMA", 16.0)])
        h.lane.decided(TB.DAY, "open")
        for sym in ("BETA", "GAMA"):
            h.symbol(sym, last=17.0, sd=0.02)
        start = TB.at(TB.DAY, 15, 47, 3)
        data = h.market.client = TimedClient(h.clock, data_timeout)
        data.mine = []
        h.venue.client.timeout = 20.0
        bars, submit = h.market.bars, h.venue.submit
        sent: dict[str, float] = {}

        def slow_bars(symbols, **kw):
            if start <= h.clock() < start + 60:
                mine = kw.get("timeframe") == "1Day" and "GAMA" in [str(s).upper() for s in symbols]
                late = r2_s if mine else main_s
                if mine:
                    data.mine.append(data.timeout)      # (the timeout READER-2's own read was given)
                if late:
                    try:
                        data.take(late)
                    except TimeoutError:
                        raise RuntimeError("the data client timed out") from None
            return bars(symbols, **kw)

        def stamped(body, *, exit):
            if body.get("side") == "buy":
                sent.setdefault(str(body["symbol"]), round(h.clock() - start, 1))
            return submit(body, exit=exit)
        h.market.bars, h.venue.submit = slow_bars, stamped
        for hh, mm in ((9, 15), (9, 16), (15, 46)):
            h.tick(hh, mm)
        h.tick(15, 47)
        ended = h.clock() + 0.5            # (the tick's own work: the fake clock does not move for it)
        nxt = next_tick(ended)
        return sent, ended - start, nxt, h, data

    def test_an_earlier_rows_send_never_waits_for_reader2s_read(self):
        """The review's (a) of the tick: READER-2's daily bars read at 20 s. BETA, a main row planned at 15:47, is
        sent at once with and without this file (without the fix: only after READER-2's read, 20 s later)."""
        off = self.day("off", r2=False, r2_s=20.0)
        on = self.day("on", r2=True, r2_s=20.0)
        self.assertEqual(off[0], {"BETA": 0.0})
        self.assertEqual(on[0]["BETA"], 0.0, "the earlier row's send waits for no read of this file")
        self.assertEqual(on[0]["GAMA"], 20.0, "READER-2's buy goes after its own read")

    def test_a_slow_data_host_never_makes_the_1547_tick_skip_the_1548_minute(self):
        """The review's (c): every market read at 14 s. Without the fix the 15:47 tick ended past 15:48:03 only with
        this file (live/step.py then skips the 15:48 minute). Now READER-2's pass starts only with `SLOT_PASS_LEAST_S`
        of the tick's bound left: the tick ends when it ends without this file, and READER-2 plans and buys at 15:48."""
        off = self.day("off", r2=False, main_s=14.0, r2_s=14.0)
        on = self.day("on", r2=True, main_s=14.0, r2_s=14.0)
        self.assertEqual(on[1], off[1], "the 15:47 tick ends as without this file")
        self.assertEqual(on[2], TB.at(TB.DAY, 15, 48), "the 15:48 tick runs")
        self.assertEqual(on[0], off[0], "BETA at the same time; nothing of this file at 15:47")
        h = on[3]
        self.assertFalse(h.book._event_decided(TB.DAY.isoformat(), "close-evl10"), "its pass waited for the next tick")
        self.assertNotIn(P.R2_ON, [r["program"] for r in h.event_intents("buy")], "not planned at 15:47")
        h.tick(15, 48)
        self.assertIn(P.R2_ON, [r["program"] for r in h.event_intents("buy")], "planned at the 15:48 tick")
        self.assertIn("GAMA", [b["symbol"] for b in h.bodies() if b.get("side") == "buy"], "and sent there")

    def test_a_hanging_read_of_its_pass_ends_by_the_bound_and_the_next_minute_runs(self):
        """Each of the main pass's reads at 3 s (12 s in all) and READER-2's daily bars hanging (a data client of 50 s):
        without the bound the 15:47 tick ends at 15:48:05 and the 15:48 tick is skipped. With it, its read's timeout
        ends at the bound (the sigma unread: the stricter weight), its buy waits for the next tick and goes there."""
        on = self.day("on", r2=True, main_s=3.0, r2_s=61.0, data_timeout=50.0)
        sent, ended, nxt, h, data = on
        self.assertEqual(nxt, TB.at(TB.DAY, 15, 48), "the 15:48 tick runs")
        self.assertLessEqual(ended, L.SLOT_TICK_S + 0.5, "the later files' work ended by the tick's bound")
        self.assertEqual(len(data.mine), 1, "READER-2's one daily bars read")
        self.assertLessEqual(data.mine[0], L.SLOT_TICK_S - 12.0, "its timeout ended at the bound, not the client's 50 s")
        self.assertEqual(data.timeout, 50.0, "the client's own timeout restored after it")
        self.assertEqual(sent, {"BETA": 12.0}, "BETA after the main pass's own reads; nothing of this file at 15:47")
        [gama] = [r for r in h.event_intents("buy") if r["program"] == P.R2_ON]
        self.assertEqual(gama["status"], "planned")
        self.assertIn(L.SLOT_BOUND, gama["why"], "not sent in the tick: the bound had passed")
        self.assertEqual(Decimal(str(gama["weight"])), Decimal(str(EB.STRICT_WEIGHT)), "its sigma unread: strict")
        h.tick(15, 48)
        self.assertIn("GAMA", [b["symbol"] for b in h.bodies() if b.get("side") == "buy"], "sent at the 15:48 tick")

    def test_a_pass_with_too_little_of_the_bound_left_waits_and_at_the_last_minute_writes_its_window_row(self):
        h2 = self.day("least", r2=True)[3]
        out: dict = {}
        adapter = h2.book._event_adapter()
        s = EB.settings()
        em = L.S.event_moments(TB.DAY, s.offsets)
        h2.state.execute("DELETE FROM eq_event_decisions WHERE at='close-evl10'")
        h2.state.execute("DELETE FROM eq_event_intents WHERE program=?", (P.R2_ON,))
        start = TB.at(TB.DAY, 15, 47, 3)
        h2.clock.set(start + L.SLOT_TICK_S - L.SLOT_PASS_LEAST_S + 1)
        h2.book._event_decide_slots(start, em, "close", s, adapter, out, bound=start + L.SLOT_TICK_S)
        self.assertIn("waits for the next tick", out["event_decide_evl10"])
        self.assertFalse(h2.book._event_decided(TB.DAY.isoformat(), "close-evl10"), "nothing of it written")
        last = TB.at(TB.DAY, 15, 48, 3)
        h2.clock.set(last + L.SLOT_TICK_S - L.SLOT_PASS_LEAST_S + 1)
        h2.book._event_decide_slots(last, em, "close", s, adapter, out, bound=last + L.SLOT_TICK_S)
        row = h2.book._event_summary(TB.DAY.isoformat(), "close-evl10")
        self.assertEqual((row["programs"][P.R2_ON]["planned"], row["programs"][P.R2_ON]["binding"],
                          row["programs"][P.R2_ON]["picks"]), (0, L.EVENT_SLOT_WINDOW, 1), "(e)'s window row")


# --------------------------------------------------------------------------------------------------------- the room
class TheRoom(TB.EventTest):
    """THE ROOM AN EARLIER ROW'S BUY STILL TO GO KEEPS (the review's 424 case): $2,000 of equity with $115 of it in cash
    from 15:47; EVL-NEWS-READ-ON's BETA is sent back once with a 424 `bars` at the 15:47 tick (nothing was sent; it goes
    again next minute, `EVENT_RETRY_CAPS`); READER-2's GAMA is planned at the same tick."""

    def setUp(self):
        super().setUp()
        T7.pin(self, None)
        self.addCleanup(P.load_births, None)

    def day(self, name: str, *, r2: bool, upto: tuple[int, int] = (15, 48)) -> TB.Harness:
        with contextlib.nullcontext() if r2 else F10.unpinned_10():
            return self._day(name, upto)

    def _day(self, name: str, upto: tuple[int, int]) -> TB.Harness:
        root = self.root / name
        root.mkdir()
        h = TB.Harness(root)
        self.addCleanup(closing, h)
        LR.ensure(h.lane.st.db)
        T10.day_news(h.lane, "n-1", "BETA", TB.CIK2)
        T10.r2_live(h.lane, [(TB.CIK3, "GAMA", 16.0)])
        h.lane.decided(TB.DAY, "open")
        h.lane.decided(TB.DAY, "close")
        for sym in ("BETA", "GAMA"):
            h.symbol(sym, last=17.0, sd=0.02)
        account = h.venue.account

        def tight():   # (an equity of $2,000 with $115 of it in cash: the rest invested elsewhere)
            row = account()
            if h.clock() >= TB.at(TB.DAY, 15, 47, 0):
                row = dict(row) | {"cash": "115", "buying_power": "115"}
            return row
        h.venue.account = tight
        submit = h.venue.submit
        refused = {"n": 0}

        def first_beta_424(body, *, exit):
            if body.get("side") == "buy" and body["symbol"] == "BETA" and refused["n"] == 0:
                refused["n"] += 1
                h.venue.sent.append(dict(body))
                return Submitted(False, {"error": "refused", "cap": "bars"}, "HTTP 424 the gateway could not read the "
                                 "bars", status=424)
            return submit(body, exit=exit)
        h.venue.submit = first_beta_424
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47), (15, 48)):
            if (hh, mm) > upto:
                break
            h.tick(hh, mm)
        return h

    @staticmethod
    def buy(h: TB.Harness, symbol: str) -> Mapping[str, Any]:
        [row] = [r for r in h.event_intents("buy") if r["symbol"] == symbol]
        return row

    def test_an_earlier_rows_retry_is_never_refused_for_reader2s_buy(self):
        off, on = self.day("off", r2=False), self.day("on", r2=True)
        self.assertEqual(self.buy(off, "BETA")["status"], "sent", "without this file: BETA's re-send at 15:48 goes")
        self.assertEqual(self.buy(on, "BETA")["status"], "sent", "with it too (without the fix: refused, no share fit)")
        def beta(h: TB.Harness) -> list[tuple]:
            return [(b["symbol"], b["qty"], b.get("limit_price")) for b in h.bodies() if b["symbol"] == "BETA"]
        self.assertEqual(beta(on), beta(off), "the same bodies, the same size")
        order = [b["symbol"] for b in on.bodies() if b.get("side") == "buy"]
        self.assertEqual(order[:2], ["BETA", "BETA"], "no buy of this file before the earlier row's re-send")
        self.assertNotEqual(self.buy(on, "GAMA")["status"], "planned", "this file's buy ended: what was left, or none")

    def test_while_the_earlier_buy_may_still_send_this_files_buy_waits_keeping_nothing(self):
        on = self.day("on", r2=True, upto=(15, 47))
        gama = self.buy(on, "GAMA")
        self.assertEqual(gama["status"], "planned", "it waits")
        self.assertIn(L.HELD_EARLIER, gama["why"], "for the room the earlier row's buy still to go keeps")
        self.assertNotIn(L.HELD_AHEAD, gama["why"], "never counted as PREREG-EVL-5's wait (its own words)")
        self.assertEqual([b["symbol"] for b in on.bodies() if b.get("side") == "buy"], ["BETA"], "nothing of it sent")
        s = EB.settings()
        kept = on.book._event_kept_before(TB.DAY.isoformat(), "close", s, on.book._event_adapter(), 1,
                                          lambda family: L._slot_of(on.book._event_adapter(), family))
        self.assertEqual(kept.held, [int(self.buy(on, "BETA")["iid"])], "BETA's room is kept, nothing of this file's")
        self.assertGreater(kept.usd, 0)
        self.assertEqual(kept.words, L.HELD_EARLIER)


if __name__ == "__main__":
    unittest.main()
