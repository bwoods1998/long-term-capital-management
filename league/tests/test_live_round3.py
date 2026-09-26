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

    def test_new_funding_cannot_permanently_judge_equity_read_before_its_execution(self):
        s, table = M.Stops(start_equity=D("1000")), M.Table.from_constitution()
        s.observe(table, at=100, day="d1", equity=D("1000"), last_equity=D("1000"), flows=M.FlowBook(100, ()))
        s.observe(table, at=200, day="d1", equity=D("1000"), last_equity=D("1000"),
                  flows=M.FlowBook(200, (), unsettled=("CSD queued",), pending_amounts=(D("5000"),)))
        s.observe(table, at=300, day="d1", equity=D("1000"), last_equity=D("1000"),
                  flows=M.FlowBook(301, ((150, D("5000")),)))
        self.assertFalse(s.daily_tripped)
        self.assertFalse(s.drawdown_tripped)
        self.assertIn("funding transition", s.blocked())
        s = M.Stops.from_state(s.as_state(), D("1000"))
        s.observe(table, at=400, day="d1", equity=D("6000"), last_equity=D("1000"),
                  flows=M.FlowBook(400, ((150, D("5000")),)))
        self.assertIsNone(s.blocked())
        self.assertEqual(s.day_pnl, D(0))


@unittest.skipUnless(HAVE, "numpy not installed")
class Recovery(LiveCase):
    def test_funding_execution_between_api_reads_refreshes_equity_before_latching(self):
        self.venue.equity = D("481.65")
        self.venue.activity_rows[0]["status"] = "pending"
        live = self.make([])
        self.run_to(9, 31)
        activities = self.venue.activities

        def execute(types, **kw):
            if "CSD" in types:
                self.venue.equity = D("5481.65")
                self.venue.activity_rows[0]["status"] = "executed"
            return activities(types, **kw)

        self.venue.activities = execute
        live._flows_at = float("-inf")
        self.run_to(9, 32)
        self.assertEqual(M.D(live.account_row["equity"]), D("5481.65"))
        self.assertFalse(live.stops.daily_tripped)
        self.assertFalse(live.stops.drawdown_tripped)
        self.assertEqual(live.stops.day_pnl, D(0))

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

    def test_broken_expired_positions_reconcile_only_their_remaining_external_fills(self):
        live, pos = self._liquidate_outside_the_house()
        short = next(leg for leg in pos.legs if leg.side < 0)
        live.book.remove_contracts(short.symbol, pos.qty * short.ratio, value_share=0, why="assigned")
        self.venue.activity_rows.extend(row for row in self._liquidation_fills(pos) if row["side"] == "sell")
        for hour, minute in ((16, 0), (16, 16)):
            self.clock.set(at(MONDAY, hour, minute))
            live.minute()
        self.assertFalse(live.book.expected_positions())
        self.assertFalse(live.book.frozen)
        rows = [r for r in self.families.forward_rows("vert") if r["source"] == "real"]
        self.assertEqual(len(rows), 1)
        closed = live.state.rows("SELECT * FROM positions WHERE pid=?", (pos.pid,))[0]
        self.assertAlmostEqual(closed["exit_value_qty"], 0.4 * pos.opened_qty)

    def test_a_missed_broken_expiry_is_reconciled_before_the_next_open(self):
        live, pos = self._liquidate_outside_the_house()
        short = next(leg for leg in pos.legs if leg.side < 0)
        live.book.remove_contracts(short.symbol, pos.qty * short.ratio, value_share=0, why="assigned")
        self.venue.activity_rows.extend(row for row in self._liquidation_fills(pos) if row["side"] == "sell")
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 0))
        live.minute()
        self.assertFalse(live.book.positions)
        self.assertEqual(len([r for r in self.families.forward_rows("vert") if r["source"] == "real"]), 1)

    def _cumulative_external_fills(self, *, first_from_orders=False):
        self.clock.set(at(MONDAY, 14, 50))
        live = self.make([family("first", VERTICAL, params={"hold": 600, "dte": 0}),
                          family("second", VERTICAL, params={"hold": 600, "dte": 0})])
        self.run_to(14, 50)
        first, second = sorted(live.book.positions.values(), key=lambda p: p.pid)
        self.venue.fill = "none"
        self.venue.held.clear()

        def fills(pos, suffix, long, short):
            return [{"id": f"fill-{suffix}-{i}", "order_id": f"external-{i}", "activity_type": "FILL",
                     "symbol": leg.symbol, "side": "sell" if leg.side > 0 else "buy",
                     "qty": str(pos.opened_qty * leg.ratio), "price": str(long if leg.side > 0 else short),
                     "transaction_time": iso(at(MONDAY, 15, 45))} for i, leg in enumerate(pos.legs)]

        earlier = fills(first, "a", .40, .15)
        if first_from_orders:
            original_orders = self.venue.orders
            fallback = [{"id": f["order_id"], "status": "filled", "symbol": f["symbol"], "side": f["side"],
                         "filled_qty": f["qty"], "filled_avg_price": f["price"], "filled_at": f["transaction_time"]}
                        for f in earlier]
            self.venue.orders = lambda **kw: original_orders(**kw) + fallback
        else:
            self.venue.activity_rows.extend(earlier)
        self.clock.set(at(MONDAY, 16, 0))
        live.minute()
        if first_from_orders:
            self.venue.activity_rows.extend(earlier)
        self.venue.activity_rows.extend(fills(second, "b", .80, .25))
        self.clock.set(at(MONDAY, 16, 16))
        live.minute()
        rows = live.state.rows("SELECT family, exit_value_qty FROM positions ORDER BY pid")
        self.assertAlmostEqual(rows[0]["exit_value_qty"], first.opened_qty * .25)
        self.assertAlmostEqual(rows[1]["exit_value_qty"], second.opened_qty * .55)
        self.clock.set(at(MONDAY, 16, 32))
        live.minute()
        self.assertEqual(live.state.rows("SELECT family, exit_value_qty FROM positions ORDER BY pid"), rows)

    def test_later_external_fills_use_only_the_unconsumed_value_of_a_cumulative_order(self):
        self._cumulative_external_fills()

    def test_external_order_fallback_then_fill_activities_do_not_double_attribute_value(self):
        self._cumulative_external_fills(first_from_orders=True)


@unittest.skipUnless(HAVE, "numpy not installed")
class BandRace(LiveCase):
    def swarm_live(self, band="candidate"):
        from league.live.families import SwarmFamilies
        from league.swarm.store import SwarmStore

        live = self.make([])
        store, other = SwarmStore(self.root), SwarmStore(self.root)
        self.addCleanup(store.close)
        self.addCleanup(other.close)
        store.add_family({"id": "vert", "mechanism": "An invented mechanism for concurrency tests.", "structure": "debit_vertical",
                          "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        version = store.add_version("vert", VERTICAL, {"hold": 600}, author="test")
        store.set_state("vert", banded_version=1, banded_sha=version["sha"], typical_by_version={"1": 50},
                        forward={"negative": False},
                        live_promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 1) if band == "probe" else None)
        store.set_band("vert", band, reason="synthetic pass")
        live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: live.families._store.close() if live.families._store is not None else None)
        live.account_row = self.venue.account()
        return live, store, other

    def tuition_live(self, *, hold=2):
        import json
        from league.gym.driver import build_bundle
        from league.swarm.gate import run_sha

        live, store, other = self.swarm_live("gym")
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "synthetic-image"}}))
        version = store.add_version("vert", VERTICAL, {"hold": hold}, author="synthetic")
        sha = run_sha(version)
        store.set_state("vert", validation_version=version["n"], validation_line={"passed": True},
                        validation_image="synthetic-image", validation_bundle=build_bundle()[1],
                        review={"sha": sha, "verdict": "pass", "audit": {"verdict": "pass"}})
        return live, store, other, f"vert@{version['n']}:t"

    def on_decision(self, live, key, change):
        decide = live._decide
        changed = []

        def interrupted(day, jobs, out):
            answers = decide(day, jobs, out)
            if not changed and any(j["key"] == key for j in jobs):
                change()
                changed.append(True)
            return answers

        live._decide = interrupted
        return changed

    def intervene(self, live, change):
        read = live.families.forward_rows

        def altered(fid):
            rows = read(fid)
            change()
            return rows

        live.families.forward_rows = altered

    def test_concurrent_gate_demotion_is_not_overwritten_or_scheduled_for_real_money(self):
        live, store, other = self.swarm_live()

        def demote():
            other.set_state("vert", forward={"negative": True})
            other.set_band("vert", "gym", reason="negative forward record")

        self.intervene(live, demote)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "gym")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertNotIn("vert", live.state.get("band_moves", {}))

    def test_new_evidence_without_a_band_change_still_invalidates_a_promotion(self):
        live, store, other = self.swarm_live()
        self.intervene(live, lambda: other.add_forward("vert", "nightly", [
            {"id": str(i), "day": "2026-09-28", "pnl": -10, "max_loss": 50, "version": 1} for i in range(20)]))
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "candidate")
        self.assertNotIn("vert@1:r", live.instances)

    def test_replaced_or_retired_identity_cannot_confirm_an_old_probe(self):
        live, store, other = self.swarm_live("probe")
        old = live.families.read()[0]
        forward = live.families.forward_rows("vert")
        version = other.add_version("vert", VERTICAL, {"hold": 601}, author="test")
        other.set_state("vert", banded_version=2, banded_sha=version["sha"])
        self.assertFalse(live.families.confirm_band(old, "probe", "unchanged", forward))
        other.set_state("vert", banded_version=1)
        other.retire("vert", "synthetic retirement")
        self.assertFalse(live.families.confirm_band(old, "probe", "unchanged", forward))

    def test_failed_confirmation_preserves_exit_ownership_and_cancels_new_entries(self):
        live, store, other = self.swarm_live("probe")
        self.run_to(9, 31)
        self.assertTrue(live.book.positions)
        self.intervene(live, lambda: other.set_state("vert", forward={"negative": True}))
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances["vert@1:r"].mode, "exit_only")
        self.assertTrue(live.book.positions)

    def test_self_retired_gym_tuition_keeps_its_position_exit_owner(self):
        live, store, _, key = self.tuition_live()
        self.run_to(9, 31)
        self.assertTrue(live.book.positions)
        self.assertTrue(live.instances[key].tuition)
        retired = store.retire_gym("vert", "The research mechanism failed.", floor=0, source="researcher")
        self.assertEqual(retired["status"], "retired")
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances[key].mode, "exit_only")
        self.assertTrue(live.book.positions, "retirement does not discard venue inventory")
        self.run_to(9, 35)
        self.assertFalse(live.book.positions)
        opens = [body for body in self.venue.sent if body["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertEqual(len(opens), 1, "the retired tuition program cannot reopen")
        self.assertEqual(store.forward("vert"), [], "tuition remains outside qualifying forward evidence")

    def test_retirement_during_a_tuition_decision_refuses_its_returned_open(self):
        live, store, other, key = self.tuition_live()
        changed = self.on_decision(live, key, lambda: other.retire_gym(
            "vert", "The mechanism failed.", floor=0, source="researcher"))
        self.run_to(9, 31)
        self.assertTrue(changed)
        self.assertEqual(store.family("vert")["band"], "retired")
        self.assertEqual((self.venue.sent, live.book.positions, live.book.orders), ([], {}, {}))
        self.assertIn("no longer eligible", self.ledger.of("live.refusal")[-1][0]["why"])

    def test_retirement_during_a_tuition_decision_keeps_its_returned_close(self):
        live, store, other, key = self.tuition_live(hold=1)
        self.run_to(9, 31)
        self.assertTrue(live.book.positions)
        self.on_decision(live, key, lambda: other.retire_gym(
            "vert", "The mechanism failed.", floor=0, source="researcher"))
        self.run_to(9, 32)
        self.assertEqual(store.family("vert")["band"], "retired")
        self.assertEqual(live.book.positions, {})
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.venue.sent], ["buy_to_open", "sell_to_close"])

    def test_demotion_during_a_real_decision_refuses_its_returned_open(self):
        live, store, other = self.swarm_live("probe")
        self.on_decision(live, "vert@1:r", lambda: other.set_band("vert", "gym", reason="synthetic demotion"))
        self.run_to(9, 31)
        self.assertEqual(store.family("vert")["band"], "gym")
        self.assertEqual((self.venue.sent, live.book.positions), ([], {}))

    def test_new_negative_evidence_during_a_real_decision_refuses_its_returned_open(self):
        live, store, other = self.swarm_live("probe")
        self.on_decision(live, "vert@1:r", lambda: other.set_state("vert", forward={"negative": True}))
        self.run_to(9, 31)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual((self.venue.sent, live.book.positions), ([], {}))

    def test_new_negative_raw_trades_during_a_decision_refuse_entry_before_summary_refresh(self):
        live, store, other = self.swarm_live("probe")
        self.on_decision(live, "vert@1:r", lambda: other.add_forward("vert", "nightly", [
            {"id": str(i), "day": "2026-09-28", "pnl": -10, "max_loss": 50, "version": 1} for i in range(20)]))
        self.run_to(9, 31)
        self.assertFalse(store.family("vert")["state"]["forward"]["negative"], "the cached summary is still stale")
        self.assertEqual((self.venue.sent, live.book.positions), ([], {}))

    def test_forward_rows_changing_between_sizing_and_admission_refuse_the_stale_order(self):
        live, store, other = self.swarm_live("probe")

        def after_decision():
            self.intervene(live, lambda: other.add_forward("vert", "nightly", [
                {"id": str(i), "day": "2026-09-28", "pnl": -10, "max_loss": 50, "version": 1} for i in range(20)]))

        self.on_decision(live, "vert@1:r", after_decision)
        self.run_to(9, 31)
        self.assertEqual(len(store.forward("vert")), 20)
        self.assertEqual((self.venue.sent, live.book.positions), ([], {}))

    def test_replaced_version_during_a_real_decision_refuses_its_returned_open(self):
        live, store, other = self.swarm_live("probe")

        def replace():
            version = other.add_version("vert", VERTICAL, {"hold": 601}, author="synthetic")
            other.set_state("vert", banded_version=version["n"], banded_sha=version["sha"])

        self.on_decision(live, "vert@1:r", replace)
        self.run_to(9, 31)
        self.assertEqual((self.venue.sent, live.book.positions), ([], {}))

    def test_demotion_during_a_shadow_decision_refuses_its_returned_open(self):
        live, store, other = self.swarm_live("candidate")
        live.real_money = False
        self.run_to(9, 31)
        account = live.shadow.accounts["vert@1:s"]
        self.on_decision(live, "vert@1:s", lambda: other.set_band("vert", "gym", reason="synthetic demotion"))
        self.run_to(9, 33)
        self.assertEqual((account.orders, account.positions, account.counts["opens"]), ({}, {}, 0))
        self.assertEqual(self.venue.sent, [])

    def test_retirement_with_a_waiting_shadow_open_withdraws_it_before_the_next_fill(self):
        live, store, other = self.swarm_live("candidate")
        live.real_money = False
        self.run_to(9, 32)
        account = live.shadow.accounts["vert@1:s"]
        self.assertEqual((len(account.orders), len(account.positions)), (1, 0))
        other.set_band("vert", "gym", reason="synthetic demotion")
        other.retire_gym("vert", "The mechanism failed.", floor=0, source="researcher")
        self.run_to(9, 34)
        self.assertEqual((account.orders, account.positions, account.trades), ({}, {}, []))

    def test_unreadable_shadow_entry_permission_does_not_drop_an_owned_close(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 600})], real_money=False)
        self.run_to(9, 33)
        account = live.shadow.accounts["vert@1:s"]
        [pos] = account.positions.values()
        with patch.object(live.families, "admit_open", side_effect=RuntimeError("store unavailable")):
            live._shadow_intents("vert@1:s", account, live.day, 2,
                                 [{"open": "debit_vertical"}, {"close": pos.pid, "limit": "natural"}])
        self.assertTrue(pos.closing)
        self.run_to(9, 36)
        self.assertEqual(account.positions, {})
        self.assertEqual(len(account.trades), 1)

    def test_entry_admission_releases_the_swarm_transaction_before_venue_io(self):
        live, store, other = self.swarm_live("probe")
        submit = self.venue.submit
        checked = []

        def outside_transaction(body, *, exit):
            other.set_state("vert", venue_io_observed=True)
            checked.append(True)
            return submit(body, exit=exit)

        self.venue.submit = outside_transaction
        self.run_to(9, 31)
        self.assertEqual(checked, [True])
        self.assertTrue(store.family("vert")["state"]["venue_io_observed"])
        self.assertTrue(live.book.positions)

    def test_retirement_after_local_admission_keeps_the_inflight_fill_and_its_exit_owner(self):
        live, store, other, key = self.tuition_live()
        submit = self.venue.submit

        def retire_after_admission(body, *, exit):
            if not exit:
                self.assertEqual(len(live.book.orders), 1, "the order was durably admitted before venue I/O")
                other.retire_gym("vert", "The mechanism failed.", floor=0, source="researcher")
            return submit(body, exit=exit)

        self.venue.submit = retire_after_admission
        self.run_to(9, 31)
        self.assertEqual(store.family("vert")["band"], "retired")
        self.assertTrue(live.book.positions, "the in-flight fill remains owned after retirement")
        self.run_to(9, 35)
        self.assertEqual(live.book.positions, {})
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.venue.sent], ["buy_to_open", "sell_to_close"])

    def test_missing_forward_evidence_does_not_start_a_real_instance(self):
        live = self.make([family("vert", VERTICAL)])
        live.account_row = self.venue.account()
        with patch.object(live.families, "forward_rows", side_effect=RuntimeError("read unavailable")):
            live.sync_families(self.clock(), force=True)
        self.assertNotIn("vert@1:r", live.instances)

    def test_promotion_wait_survives_a_crash_before_the_local_move_record(self):
        from league.live.families import SwarmFamilies

        live, store, other = self.swarm_live()
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual(store.family("vert")["state"]["live_promoted_at"], self.clock())
        live.state.execute("DELETE FROM kv WHERE key='band_moves'")  # the Swarm transaction was the last durable write
        live.state.close()
        again = self.make([])
        again.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: again.families._store.close() if again.families._store is not None else None)
        self.assertFalse(again._real_eligible("vert"))
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        self.assertTrue(again._real_eligible("vert"))

    def test_missing_legacy_promotion_time_waits_a_session_and_persists_first_sight(self):
        live, store, other = self.swarm_live("probe")
        other.set_state("vert", live_promoted_at=None)
        live.sync_families(self.clock(), force=True)
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(live.state.get("real_first_seen")["vert"], self.clock())
        self.clock.set(at(MONDAY, 12, 0))
        self.assertFalse(live._real_eligible("vert"))
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        self.assertTrue(live._real_eligible("vert"))

    def test_a_repromotion_uses_the_latest_durable_time_for_whole_probe_sessions(self):
        live, store, other = self.swarm_live("probe")
        live.state.put("band_moves", {"vert": {"band": "probe", "at": at(MONDAY - dt.timedelta(days=7), 9, 0)}})
        other.set_state("vert", live_promoted_at=self.clock())  # new promotion committed before the local write crashed
        self.assertFalse(live._real_eligible("vert"))
        self.assertEqual(live._probe_sessions("vert", "probe"), 0)
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 16, 0))
        self.assertEqual(live._probe_sessions("vert", "probe"), 1)


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
