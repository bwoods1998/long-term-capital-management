"""Review #362 round 3: behavioral regressions with invented quotes, programs and venue responses."""

import datetime as dt
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from league.live import money as M
from league.live.decider import Decider, DeciderError, batch_deadline
from league.tests.test_live_step import HAVE, LiveCase, RESTER

if HAVE:
    from league.live.real import RealBook, mleg_body
    from league.live.state import LiveState
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family, iso


class Funding(unittest.TestCase):
    def test_a_flow_requested_before_the_close_and_executed_overnight_is_not_daily_pnl(self):
        for amount in (D("3000"), D("-1500")):
            with self.subTest(amount=amount):
                s, table = M.Stops(start_equity=D("5481.65")), M.Table.from_constitution()
                s.observe(table, at=100, day="d1", equity=D("5481.65"), last_equity=D("5481.65"),
                          flows=M.FlowBook(100, ()))
                queued = M.FlowBook(300, (), unsettled=("request queued",), pending_amounts=(amount,))
                s.observe(table, at=300, day="d1", equity=D("5481.65"), last_equity=D("5481.65"), flows=queued)
                # Preserve the observed flow baseline across a process restart.
                s = M.Stops.from_state(s.as_state(), D("5481.65"))
                s.observe(table, at=400, day="d2", equity=D("5481.65") + amount, last_equity=D("5481.65"),
                          flows=M.FlowBook(400, ((200, amount),)))
                self.assertEqual(s.day_pnl, D(0))
                self.assertFalse(s.daily_tripped)
                self.assertFalse(s.drawdown_tripped)
                s.observe(table, at=500, day="d2", equity=(D("5481.65") + amount) * D("0.74"),
                          last_equity=D("5481.65"), flows=M.FlowBook(500, ((200, amount),)))
                self.assertTrue(s.daily_tripped, "a deposit must not hide the following day's actual loss")

    def test_a_drawdown_during_a_pending_deposit_is_latched_even_if_it_recovers(self):
        s, table = M.Stops(start_equity=D("1000")), M.Table.from_constitution()
        s.observe(table, at=100, day="d1", equity=D("1000"), last_equity=D("1000"), flows=M.FlowBook(100, ()))
        queued = M.FlowBook(300, (), unsettled=("CSD queued",), pending_amounts=(D("100"),))
        s.observe(table, at=200, day="d1", equity=D("450"), last_equity=D("1000"), flows=queued)
        self.assertTrue(s.drawdown_tripped)
        s.observe(table, at=400, day="d1", equity=D("700"), last_equity=D("1000"),
                  flows=M.FlowBook(400, ((150, D("100")),)))
        self.assertTrue(s.drawdown_tripped)

    def test_a_pending_request_without_a_loss_does_not_block_the_whole_session(self):
        s, table = M.Stops(start_equity=D("1000")), M.Table.from_constitution()
        pending = M.FlowBook(300, (), unsettled=("CSD queued",), pending_amounts=(D("6000"),))
        s.observe(table, at=100, day="d1", equity=D("1000"), last_equity=D("1000"), flows=pending)
        self.assertIsNone(s.blocked())


@unittest.skipUnless(HAVE, "numpy not installed")
class Recovery(LiveCase):
    def test_an_old_assignment_is_still_excluded_after_the_activity_cursor_exists(self):
        self.venue.activity_rows += [
            {"id": "old", "activity_type": "OPASN", "symbol": "SPY260925C00600000", "qty": "1",
             "date": "2026-09-25", "transaction_time": "2026-09-25T20:00:00Z"},
            {"id": "new", "activity_type": "OPEXP", "symbol": "SPY260926C00600000", "qty": "1",
             "date": "2026-09-26", "transaction_time": "2026-09-26T12:00:00Z"}]
        live = self.make([])
        self.run_to(9, 38)
        self.assertEqual(live.state.get("activities_cursor"), "2026-09-26")
        self.assertFalse([n for n in self.notices if n["stop"] == "assignment"])

    def test_a_program_exit_preempts_another_positions_resting_close_after_two_minutes(self):
        live = self.make([family("tp", VERTICAL, params={"hold": 600}), family("exit", VERTICAL, params={"hold": 600})])
        self.run_to(9, 31)
        positions = {p.family: p for p in live.book.positions.values()}
        tp, exiting = positions["tp"], positions["exit"]
        live._send_close(tp, live.day, 1, forced=False, why="resting target", out={},
                         intent={"close": tp.pid, "limit": {"price": 9.99}})
        blocker = live.book.closing_order(tp.pid)
        live._send_close(exiting, live.day, 1, forced=False, why="stop", out={})
        self.run_to(9, 36)
        self.assertIn(blocker.venue_id, self.venue.cancels)
        self.assertNotIn(exiting.pid, live.book.positions)

    def test_a_forced_exit_preempts_a_resting_close_and_a_waiting_forced_exit_obeys_cutoff(self):
        live = self.make([family("tp", VERTICAL, params={"hold": 600, "dte": 0}),
                          family("exit", VERTICAL, params={"hold": 600, "dte": 0})])
        self.run_to(9, 31)
        tp, exiting = list(live.book.positions.values())
        live._send_close(tp, live.day, 1, forced=False, why="resting target", out={},
                         intent={"close": tp.pid, "limit": {"price": 9.99}})
        blocker = live.book.closing_order(tp.pid)
        live._send_close(exiting, live.day, 1, forced=True, why="orphan", out={})
        self.assertIn(blocker.venue_id, self.venue.cancels)
        self.run_to(9, 33)
        self.assertNotIn(exiting.pid, live.book.positions)
        live.pending_exits[tp.pid] = {"forced": True, "why": "expiry", "day": MONDAY.isoformat(), "queued_at": self.clock()}
        before = len(self.venue.sent)
        self.clock.set(at(MONDAY, 15, 25))
        live.minute()
        self.assertEqual(len(self.venue.sent), before)
        self.assertNotIn(tp.pid, live.pending_exits)

    def test_exit_only_programs_reload_and_repeated_failure_becomes_an_orphan(self):
        live = self.make([family("vert", VERTICAL, params={"hold": 10})])
        self.run_to(9, 31)
        self.families.rows.clear()
        live._families_at = float("-inf")
        self.run_to(9, 32)
        inst = live.instances["vert@1:r"]
        self.assertEqual(inst.mode, "exit_only")
        live.decider._runners.pop(inst.key)
        self.run_to(9, 35)
        self.assertFalse(inst.error)
        self.run_to(9, 42)
        self.assertFalse(live.book.positions, "the recovered exit-only program closes its own position")

    def test_unrecoverable_exit_only_programs_are_closed_by_the_house(self):
        live = self.make([family("vert", VERTICAL, params={"hold": 600})])
        self.run_to(9, 31)
        self.families.rows.clear()
        live._families_at = float("-inf")
        self.run_to(9, 32)
        live.decider._runners.pop("vert@1:r")
        with patch.object(live.decider, "load", side_effect=DeciderError("unavailable")):
            self.run_to(9, 40)
        self.assertFalse(live.book.positions)
        self.assertTrue(any("five minutes" in text for _, text in self.alerts))

    def test_demotion_cancels_working_opens_before_they_can_fill(self):
        live = self.make([family("rest", RESTER, params={"hold": 600})])
        self.run_to(9, 31)
        [order] = list(live.book.orders.values())
        self.families.rows["rest"]["forward"] = {"negative": True}
        live._families_at = float("-inf")
        self.run_to(9, 32)
        self.assertIn(order.venue_id, self.venue.cancels)
        self.assertFalse(live.book.positions)

    def test_disqualification_cancels_an_open_and_survives_restart_and_family_refresh(self):
        rows = [family("rest", RESTER, params={"hold": 600})]
        live = self.make(rows)
        self.run_to(9, 31)
        [order] = list(live.book.orders.values())
        live._stats("rest@1:r", {"stats": {"disqualified": "too many errors"}})
        self.assertIn(order.venue_id, self.venue.cancels)
        live.state.close()
        again = self.make(rows)
        self.clock.set(at(MONDAY, 9, 32))
        self.run_to(9, 40)
        self.assertFalse(again.book.positions)
        self.assertEqual(len(self.venue.sent), 1, "a refreshed or restarted dead version does not gain new opens")

    def test_real_exports_include_a_slow_older_position_after_a_newer_one_closed(self):
        live = self.make([family("slow", VERTICAL, params={"hold": 12}), family("fast", VERTICAL, params={"hold": 2})])
        self.run_to(9, 36)
        self.assertTrue([r for r in self.families.forward_rows("fast") if r["source"] == "real"])
        self.market.spot -= 3
        self.run_to(9, 46)
        rows = [r for r in self.families.forward_rows("slow") if r["source"] == "real"]
        self.assertEqual(len(rows), 1)
        self.assertLess(rows[0]["pnl"], 0)
        live._export_real()
        self.assertEqual(len([r for r in self.families.forward_rows("slow") if r["source"] == "real"]), 1)

    def _liquidate_outside_the_house(self):
        self.clock.set(at(MONDAY, 14, 50))
        live = self.make([family("vert", VERTICAL, params={"hold": 600, "dte": 0})])
        self.run_to(14, 50)
        [pos] = list(live.book.positions.values())
        self.venue.fill = "none"
        self.clock.set(at(MONDAY, 15, 45))
        self.venue.held.clear()
        return live, pos

    def _liquidation_fills(self, pos):
        return [{"id": f"liq-{i}", "activity_type": "FILL", "symbol": leg.symbol,
                 "side": "sell" if leg.side > 0 else "buy", "qty": str(pos.opened_qty * leg.ratio),
                 "price": "0.40" if leg.side > 0 else "0.15", "transaction_time": iso(at(MONDAY, 15, 45))}
                for i, leg in enumerate(pos.legs)]

    def test_external_expiry_liquidation_clears_caps_and_exports_actual_fills_once(self):
        live, pos = self._liquidate_outside_the_house()
        self.venue.activity_rows.extend(self._liquidation_fills(pos))
        self.clock.set(at(MONDAY, 16, 0))
        live.minute()
        self.assertFalse(live.book.positions)
        rows = [r for r in self.families.forward_rows("vert") if r["source"] == "real"]
        self.assertEqual(len(rows), 1)
        closed = live.state.rows("SELECT * FROM positions WHERE pid=?", (pos.pid,))[0]
        self.assertIn("external fills", closed["reason"])
        self.assertAlmostEqual(closed["exit_value_qty"], 0.25 * pos.opened_qty)
        self.assertEqual(live.book.exposure("vert", day=MONDAY.isoformat(), week_start=MONDAY.isoformat()).family_open, 0)

    def test_missing_external_prices_stay_out_of_evidence_until_the_venue_provides_them(self):
        live, pos = self._liquidate_outside_the_house()
        self.clock.set(at(MONDAY, 16, 0))
        out = live.minute()
        self.assertFalse(live.book.positions)
        self.assertEqual(out["unpriced_closes"], 1)
        self.assertIn("fill values", live.real_block())
        self.assertFalse([r for r in self.families.forward_rows("vert") if r["source"] == "real"])
        self.venue.activity_rows.extend(self._liquidation_fills(pos))
        self.clock.set(at(MONDAY, 16, 16))
        live.minute()
        self.assertEqual(len([r for r in self.families.forward_rows("vert") if r["source"] == "real"]), 1)


class Deadline(unittest.TestCase):
    def test_production_child_refuses_to_start_without_its_network_namespace(self):
        d = Decider()
        d.isolated, d.netns = True, False
        try:
            with self.assertRaisesRegex(DeciderError, "requires a network namespace"):
                d.ping()
            self.assertIsNone(d.proc)
        finally:
            d.close()

    def test_no_input_reader_cannot_hold_the_house_beyond_the_deadline(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        d = Decider()
        d.proc = child
        started = time.monotonic()
        try:
            with self.assertRaises(DeciderError):
                d._ask(("ping", "x" * 500000), 0.05)
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertIsNone(d.proc, "no synchronous reload extends the expired budget")
        finally:
            d.close()
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_batch_budget_is_clamped_to_the_remaining_minute(self):
        self.assertEqual(batch_deadline(1, 100, 0.25), 0.25)
        self.assertEqual(batch_deadline(1, 100, -1), 0)


if __name__ == "__main__":
    unittest.main()
