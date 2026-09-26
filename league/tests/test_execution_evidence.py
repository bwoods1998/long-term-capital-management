"""Invented quotes and fake venues only: evidence never becomes money authority."""
import datetime as dt
import gc
import hashlib
import json
import sqlite3
import tempfile
import unittest
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.gym.fills import FillModel
    from league.live.chains import LiveDay
    from league.live.decider import InlineDecider
    from league.live.evidence import Evidence, FILE, HEALTH, sample
    from league.live.execution_report import comparison, complete_sample, order_report, readonly, report
    from league.live.families import MemoryFamilies
    from league.live.shadow import ShadowBook
    from league.live.state import LiveState
    from league.live.step import OptionsLive
    from league.tests.live_fakes import MONDAY, VERTICAL, Clock, at, family


@unittest.skipUnless(HAVE, "numpy not installed")
class EvidenceStorage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clock = Clock(at(MONDAY, 9, 30))
        self.evidence = Evidence(self.root, clock=self.clock)

    def tearDown(self):
        self.evidence.close()
        self.temp.cleanup()

    def test_failed_write_pending_marker_survives_restart_even_when_health_file_cannot_write(self):
        self.evidence.call("model", FillModel())
        token = self.evidence.call("begin", self.clock())
        with patch.object(self.evidence, "_insert", side_effect=sqlite3.OperationalError("disk full")), \
             patch("league.live.state.write_json_atomic", side_effect=OSError("disk full")):
            self.assertIsNone(self.evidence.call("instance", type("I", (), dict(kind="shadow", key="f@1:s", family="f",
                                        version=1, run_sha="synthetic", tuition=False, band="candidate"))()))
        self.evidence.call("end", token, True)
        self.evidence.close()
        self.assertFalse((self.root / HEALTH).exists())
        self.evidence = Evidence(self.root, clock=self.clock)
        self.evidence.call("model", FillModel())
        result = report(self.root, MONDAY.isoformat())
        self.assertFalse(result["complete"])
        self.assertIn("interrupted_observation", result["gaps"])
        self.assertIn(570, result["coverage"]["missing_minutes"])

    def test_payload_and_event_bounds_preserve_previous_receipts_and_mark_incomplete(self):
        self.evidence.max_events_day = 1
        self.evidence.call("model", FillModel())
        inst = type("I", (), dict(kind="shadow", key="f@1:s", family="f", version=1, run_sha="a",
                                 tuition=False, band="candidate"))()
        self.evidence.call("instance", inst)
        inst.run_sha = "b"
        self.evidence.call("instance", inst)
        self.assertIn(MONDAY.isoformat(), self.evidence.failed)
        self.assertEqual(self.evidence.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
        self.assertTrue(json.loads((self.root / HEALTH).read_text())[MONDAY.isoformat()]["incomplete"])
        self.assertEqual((self.root / FILE).stat().st_mode & 0o777, 0o600)

    def test_model_artifact_comes_from_effective_object_and_preserves_both_versions(self):
        model_path = self.root / "source.json"
        model_path.write_text(json.dumps({"hazard": {"synthetic": 0.2}}))
        model = FillModel.load(model_path)
        first = self.evidence.call("model", model)
        model_path.write_text(json.dumps({"hazard": {"synthetic": 0.9}}))
        self.assertEqual(self.evidence.call("model", model), first)
        second = self.evidence.call("model", FillModel.load(model_path))
        self.assertNotEqual(first["sha256"], second["sha256"])
        rows = self.evidence.db.execute("SELECT hash,body FROM models").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(json.loads(r[1])["hazard"]["synthetic"] for r in rows), [0.2, 0.9])
        self.assertTrue(all(hashlib.sha256(r[1].encode()).hexdigest() == r[0] for r in rows))

    def test_readonly_handle_cannot_mutate_evidence(self):
        self.evidence.call("model", FillModel())
        db = readonly(self.root / FILE)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM models")
        finally:
            db.close()

    def test_report_snapshot_does_not_block_concurrent_observation_writes(self):
        self.evidence.call("model", FillModel())
        reader = readonly(self.root / FILE)
        try:
            self.assertEqual(reader.execute("SELECT count(*) FROM events").fetchone()[0], 0)
            with ThreadPoolExecutor(max_workers=1) as worker:
                future = worker.submit(self.evidence.call, "insert", "paper", "synthetic", "id", {"n": 1})
                future.result(timeout=1)
            self.assertEqual(self.evidence.failed, set())
            self.assertEqual(reader.execute("SELECT count(*) FROM events").fetchone()[0], 0)  # consistent old snapshot
            self.assertEqual(self.evidence.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            self.assertFalse((self.root / HEALTH).exists())
        finally:
            reader.close()

    def test_pinned_snapshot_cannot_grow_wal_past_combined_disk_bound(self):
        self.evidence.max_disk_bytes = 8 * 1024 * 1024
        self.evidence.call("model", FillModel())
        reader = readonly(self.root / FILE)
        try:
            reader.execute("SELECT count(*) FROM events").fetchone()
            for i in range(1000):
                self.evidence.call("insert", "shadow", "synthetic", str(i), {"payload": "x" * 30000})
                if self.evidence.failed:
                    break
            self.assertTrue(self.evidence.failed)
            self.assertGreater(self.evidence.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            self.assertLessEqual(self.evidence.disk_bytes(), self.evidence.max_disk_bytes)
            before = self.evidence.disk_bytes()
            self.evidence.call("insert", "shadow", "synthetic", "after-bound", {"payload": "x" * 30000})
            self.assertEqual(self.evidence.disk_bytes(), before)
        finally:
            reader.close()
        self.evidence.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.assertEqual(Path(str(self.evidence.path) + "-wal").stat().st_size, 0)
        self.assertIn("recorder_write_failure", report(self.root, MONDAY.isoformat())["gaps"])

    def test_disposable_recorder_cycle_closes_its_sqlite_connection(self):
        recorder = Evidence(self.root, clock=self.clock)
        recorder.context = lambda recorder=recorder: recorder
        recorder.call("model", FillModel())
        db = recorder.db
        reference = weakref.ref(recorder)
        del recorder
        gc.collect()
        self.assertIsNone(reference())
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")


@unittest.skipUnless(HAVE, "numpy not installed")
class QuoteMetadata(unittest.TestCase):
    def test_repeated_partial_reads_preserve_contract_receipts_and_rejected_read_provenance(self):
        day = LiveDay(MONDAY, 570, 960, trading_days=[MONDAY])
        chain = day.chain("SPY")
        a, b = "SPY260928C00600000", "SPY260928C00601000"
        stamp = at(MONDAY, 9, 31)
        quote = {"bp": 1, "ap": 1.1, "bs": 5, "as": 6, "t": "2026-09-28T13:31:00Z"}
        chain.record(1, {a: {"latestQuote": quote}}, open_epoch=stamp - 60, received_at=stamp + 1)
        original = sample(day, 1, "SPY", [{"symbol": a}])
        chain.record(1, {b: {"latestQuote": quote}}, open_epoch=stamp - 60, received_at=stamp + 2)
        self.assertEqual(sample(day, 1, "SPY", [{"symbol": a}]), original)
        chain.record(1, {a: {"latestQuote": {k: v for k, v in quote.items() if k not in ("bs", "as")}}},
                     open_epoch=stamp - 60, received_at=stamp + 3)
        missing_size = sample(day, 1, "SPY", [{"symbol": a}])["legs"][0]
        self.assertEqual(missing_size["received_at"], stamp + 3)
        self.assertEqual((missing_size["bid_size_status"], missing_size["ask_size_status"]), ("missing", "missing"))
        chain.record(1, {a: {"latestQuote": dict(quote, bp=1.2)}},
                     open_epoch=stamp - 60, received_at=stamp + 4)
        crossed = sample(day, 1, "SPY", [{"symbol": a}])
        self.assertEqual(crossed["legs"][0]["observation_status"], "crossed")
        self.assertEqual(crossed["legs"][0]["last_read_at"], stamp + 4)
        self.assertEqual(crossed["legs"][0]["received_at"], stamp + 3)
        self.assertEqual(crossed["legs"][0]["bid"], 1)  # rejected observation does not alter engine prices
        fills = [{"symbol": a, "direction": 1, "filled_qty": 1, "vwap": 1.1}]
        self.assertIn("quote_crossed", comparison(crossed, fills, stamp + 5)["missing"])
        chain.record(1, {a: None}, open_epoch=stamp - 60, received_at=stamp + 5)
        self.assertEqual(sample(day, 1, "SPY", [{"symbol": a}])["legs"][0]["observation_status"], "missing_quote")

    def test_stale_missing_and_future_timing_remain_unknown_without_changing_admission(self):
        day = LiveDay(MONDAY, 570, 960, trading_days=[MONDAY])
        chain = day.chain("SPY")
        symbol = "SPY260928C00600000"
        observed = at(MONDAY, 10, 15)
        for raw, expected in (("2026-09-28T13:30:00Z", "quote_stale"),
                              ("2026-09-28T14:16:00Z", "quote_not_observed_by_reference_time"),
                              (None, "quote_timing_unknown")):
            with self.subTest(raw=raw):
                chain.record(45, {symbol: {"latestQuote": {"bp": 1, "ap": 1.1, "bs": 1, "as": 1, "t": raw}}},
                             open_epoch=at(MONDAY, 9, 30, 0), received_at=observed)
                quote = sample(day, 45, "SPY", [{"symbol": symbol}])
                self.assertEqual(quote["status"], "sampled")
                self.assertFalse(complete_sample(quote))
                out = comparison(quote, [{"symbol": symbol, "direction": 1, "filled_qty": 1, "vwap": 1.1}], observed)
                self.assertIsNone(out["natural_slippage_usd"])
                self.assertIn(expected, out["missing"])

    def test_remap_keeps_exact_timestamp_size_provenance_and_missing_time_unknown(self):
        day = LiveDay(MONDAY, 570, 960, trading_days=[MONDAY, MONDAY + dt.timedelta(days=1)])
        chain = day.chain("SPY")
        later = "SPY260929C00601000"
        earlier = "SPY260929C00600000"
        exact = "2026-09-28T13:31:00.123456789Z"
        rows = {later: {"latestQuote": {"bp": 1, "ap": 1.1, "bs": 0, "t": exact}}}
        chain.record(1, rows, open_epoch=at(MONDAY, 9, 30), received_at=at(MONDAY, 9, 31) + 1)
        chain.set_price(1, 600)
        before = sample(day, 1, "SPY", [{"symbol": later, "direction": 1, "ratio": 1}])
        chain.record(2, {earlier: {"latestQuote": {"bp": 2, "ap": 2.1, "bs": 2, "as": 3, "t": "bad"}}},
                     open_epoch=at(MONDAY, 9, 30), received_at=at(MONDAY, 9, 32))
        after = sample(day, 1, "SPY", [{"symbol": later, "direction": 1, "ratio": 1}])
        self.assertEqual(before, after)
        self.assertEqual(after["legs"][0]["quote_time_raw"], exact)
        self.assertEqual(after["legs"][0]["bid_size_status"], "quoted")
        self.assertEqual(after["legs"][0]["ask_size_status"], "missing")
        bad = sample(day, 2, "SPY", [{"symbol": earlier, "direction": 1, "ratio": 1}])
        self.assertEqual(bad["status"], "sampled")  # original admission is unchanged
        self.assertIsNone(bad["legs"][0]["quote_at"])
        self.assertEqual(bad["legs"][0]["quote_time_status"], "invalid")
        chain.quote_revision += 1
        self.assertEqual(sample(day, 1, "SPY", [{"symbol": later}])["status"], "concurrent_update")


class LiveEvidence(LiveCase):
    def paper_only(self):
        self.families = MemoryFamilies()
        self.live = OptionsLive(self.root, market=self.market, real=None, paper=self.paper,
                                families=self.families, decider=InlineDecider(), real_money=False,
                                clock=self.clock, record=self.ledger, fill_model=FillModel())
        return self.live

    def tearDown(self):
        if getattr(self, "live", None) is not None:
            self.live.evidence.close()
        super().tearDown()

    def test_paper_roundtrip_keeps_private_quotes_and_never_books_real_or_fit_evidence(self):
        live = self.paper_only()
        self.run_to(9, 45)
        self.assertTrue(live.proof.passed())
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob("*.sqlite")}
        result = report(self.root, MONDAY.isoformat())
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob("*.sqlite")}
        self.assertEqual(before, after)
        self.assertEqual(result["counts"], {"paper": 2, "shadow": 0, "real": 0})
        self.assertTrue(all(o["gross_cashflow_usd"] is not None for o in result["orders"]))
        self.assertTrue(all(o["submission_sample_comparison"]["natural_slippage_usd"] == 0 for o in result["orders"]))
        self.assertTrue(all(o["broker_fill_latency_seconds"] is None for o in result["orders"]))
        self.assertTrue(all(o["fees_usd"] is None and not o["calibration_eligible"] for o in result["orders"]))
        self.assertEqual(self.venue.sent, [])
        self.assertIsNone(live.book)
        self.assertEqual(live.state.rows("SELECT * FROM orders"), [])
        # Recorder never sends its payload through the publisher/ledger callback.
        ledger = json.dumps(self.ledger.rows)
        for private in ("quote_time_raw", "bid_size_status", "hazard", "model_hashes"):
            self.assertNotIn(private, ledger)

    def test_shadow_complete_trade_survives_forward_export_restart_and_retirement(self):
        self.paper = None
        live = self.make([family("audit", VERTICAL, band="candidate")], real_money=False)
        self.run_to(9, 40)
        self.assertEqual(live.shadow.accounts["audit@1:s"].exported, 1)
        self.assertEqual(json.loads((self.root / "live-shadow.json").read_text())["accounts"][0]["trades"], [])
        live.instances["audit@1:s"].mode = "wind_down"
        live._retire_finished()
        live.shadow.save()
        self.assertEqual(ShadowBook(self.root / "live-shadow.json").accounts, {})
        result = report(self.root, MONDAY.isoformat())
        self.assertEqual(len(result["trades"]), 1)
        self.assertIn("entry_minute", result["trades"][0]["trade"])
        self.assertIn("fees", result["trades"][0]["trade"])
        orders = result["orders"]
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]["decision_minute"], 571)
        self.assertEqual(dt.datetime.fromtimestamp(orders[0]["decision_observed_at"], __import__("zoneinfo").ZoneInfo("America/New_York")).minute, 32)
        self.assertEqual(orders[0]["simulated_fills"][0]["simulated_minute"], 572)

    def test_accepted_paper_open_with_lost_answer_is_linked_across_restart_once(self):
        live = self.paper_only()
        self.paper.submit_mode = "lost"
        self.run_to(9, 35)
        original_cid = live.proof.status()["orders"][0]["cid"]
        self.paper._advance()
        self.paper.submit_mode = "ok"
        live.state.close()
        live.evidence.close()
        self.clock.set(at(MONDAY, 9, 36))
        self.paper_only()
        self.run_to(9, 46)
        result = report(self.root, MONDAY.isoformat())
        self.assertTrue(self.live.proof.passed())
        self.assertEqual(len(result["orders"]), 2)
        opened = next(o for o in result["orders"] if o["id"] == original_cid)
        self.assertEqual(opened["gross_cashflow_usd"], -49)
        self.assertEqual(len(opened["model_hashes"]), 1)
        self.assertEqual(len(self.paper.sent), 2)
        self.assertEqual(len({o["id"] for o in result["orders"]}), 2)

    def test_uneven_paper_cleanup_and_cumulative_snapshots_are_not_double_counted(self):
        self.paper_only()
        self.paper.fill = "uneven"
        self.run_to(9, 36)
        self.paper.fill = "natural"
        self.run_to(9, 48)
        self.assertTrue(self.live.proof.passed())
        result = report(self.root, MONDAY.isoformat())
        self.assertEqual(len(result["orders"]), len(self.paper.sent))
        expected = sum((-1 if leg["side"] == "buy" else 1) * float(leg["filled_qty"])
                       * float(leg.get("filled_avg_price") or 0) * 100
                       for order in self.paper.orders_rows() for leg in (order["legs"] or [order]))
        self.assertAlmostEqual(sum(o["gross_cashflow_usd"] for o in result["orders"]), expected)
        self.assertFalse(any(self.paper.held.values()))

    def test_recorder_failure_does_not_change_paper_close_or_inventory_reconciliation(self):
        live = self.paper_only()
        self.run_to(9, 36)
        self.assertTrue(any(self.paper.held.values()))
        with patch.object(live.evidence, "_insert", side_effect=OSError("disk full")):
            self.run_to(9, 45)
        self.assertTrue(live.proof.passed())
        self.assertFalse(any(self.paper.held.values()))
        self.assertEqual(len(self.paper.sent), 2)
        result = report(self.root, MONDAY.isoformat())
        self.assertIn("recorder_write_failure", result["gaps"])
        self.assertIn("authoritative_order_receipt_missing", result["gaps"])

    def test_real_owned_close_counts_and_fees_survive_recorder_failure(self):
        self.paper = None
        live = self.make([family("audit", VERTICAL, band="probe")])
        self.run_to(9, 33)
        self.assertTrue(live.book.positions)
        with patch.object(live.evidence, "_insert", side_effect=OSError("disk full")):
            self.run_to(9, 41)
        self.assertEqual(live.book.positions, {})
        self.assertFalse(any(self.venue.held.values()))
        self.assertEqual(len(self.venue.sent), 2)
        self.assertEqual(live.book.count_today(MONDAY.isoformat()), 4)
        rows = live.state.rows("SELECT * FROM fills")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["fees"] > 0 for row in rows))
        self.assertEqual(live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False), [])
        self.assertFalse(report(self.root, MONDAY.isoformat())["complete"])

    def test_nonfill_samples_include_working_opportunities_but_not_skipped_minutes(self):
        self.paper = None
        code = VERTICAL.replace('"limit": "natural"', '"limit": {"price": 0.01}')
        live = self.make([family("rest", code, band="candidate")], real_money=False)
        self.run_to(9, 34)
        self.clock.set(at(MONDAY, 9, 38))
        live.minute()
        result = report(self.root, MONDAY.isoformat())
        [order] = result["orders"]
        self.assertEqual(order["nonfill_samples"], 2)
        self.assertEqual(order["incomplete_opportunity_samples"], 1)
        self.assertIn(575, result["coverage"]["missing_minutes"])
        self.assertEqual(order["simulated_fills"], [])

    def test_fill_before_failed_shadow_checkpoint_is_not_counted_twice_after_restart(self):
        self.paper = None
        live = self.make([family("crash", VERTICAL, band="candidate")], real_money=False)
        self.run_to(9, 32)
        self.clock.set(at(MONDAY, 9, 33))
        with patch.object(live.shadow, "save", side_effect=RuntimeError("synthetic crash before checkpoint")):
            with self.assertRaises(RuntimeError):
                live.minute()
        self.assertEqual(live.evidence.db.execute("SELECT count(*) FROM events WHERE kind='fill'").fetchone()[0], 1)
        live.state.close()
        live.evidence.close()
        live = self.make([family("crash", VERTICAL, band="candidate")], real_money=False)
        self.run_to(9, 40)
        result = report(self.root, MONDAY.isoformat())
        self.assertEqual(live.shadow.accounts["crash@1:s"].counts["fills"], 2)
        opened = next(o for o in result["orders"] if o["id"] == "crash@1:s:1")
        self.assertEqual(len(opened["simulated_fills"]), 2)  # both private receipts are retained, never silently deduped
        self.assertEqual([f["checkpointed"] for f in opened["simulated_fills"]], [False, True])
        self.assertIsNone(opened["gross_cashflow_usd"])
        self.assertIsNone(opened["fees_usd"])
        self.assertIn("uncheckpointed_shadow_fill_or_replay", opened["missing"])


@unittest.skipUnless(HAVE, "numpy not installed")
class ReportInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clock = Clock(at(MONDAY, 10, 0))
        self.evidence = Evidence(self.root, clock=self.clock)
        self.model = self.evidence.call("model", FillModel())
        self.state = LiveState(self.root / "live.sqlite", clock=self.clock)
        self.cid = "synthetic-two-day-order"
        self.state.upsert("orders", dict(oid=1, client_id=self.cid, instance="f@1:r", family="f", action="open",
                         type="long_call", root="SPY", legs="[]", qty=2, limit_value=1, limit_price="1",
                         placed_at=self.clock(), day=MONDAY.isoformat(), placed_minute=600,
                         status="partially_filled", filled_qty=1, updated_at=self.clock()), "oid")
        self.body = {"client_order_id": self.cid, "symbol": "SYNTHETIC", "side": "buy", "qty": "2"}
        self.quote = {"status": "sampled", "minute": 600, "legs": [{"symbol": "SYNTHETIC", "bid": .9, "ask": 1,
                      "quote_at": self.clock() - 1, "received_at": self.clock(), "bid_size_status": "quoted",
                      "ask_size_status": "quoted", "observation_status": "accepted"}]}
        self.evidence.call("insert", "real", "submit", self.cid,
                           {"order": {"client_id": self.cid}, "body": self.body, "model": self.model, "quote": self.quote})
        self.clock.set(self.clock() + 60)
        self.answer = {"client_order_id": self.cid, "symbol": "SYNTHETIC", "side": "buy", "filled_qty": "1",
                       "filled_avg_price": "1", "status": "partially_filled", "submitted_at": "2026-09-28T14:00:00Z",
                       "filled_at": "2026-09-28T14:01:00Z"}
        self.evidence.call("insert", "real", "reply", self.cid,
                           {"order": {"client_id": self.cid}, "body": self.body, "model": self.model, "detail": self.answer})
        self.evidence.db.executemany("INSERT INTO coverage VALUES(?,?,1)", [(MONDAY.isoformat(), m) for m in range(570, 961)])
        self.state.execute("INSERT INTO fills(oid,qty,value,fees,at) VALUES(1,1,1,.65,?)", (self.clock(),))

    def tearDown(self):
        self.evidence.close()
        self.state.close()
        self.temp.cleanup()

    def read(self):
        return report(self.root, MONDAY.isoformat())

    def test_later_session_fill_does_not_lend_its_fees_to_earlier_observed_gross(self):
        before = self.read()
        self.assertTrue(before["complete"])
        self.state.execute("INSERT INTO fills(oid,qty,value,fees,at) VALUES(1,1,1,.65,?)",
                           (at(MONDAY + dt.timedelta(days=1), 10, 1),))
        later = self.read()
        self.assertTrue(later["complete"])
        for result in (before, later):
            self.assertEqual(result["orders"][0]["gross_cashflow_usd"], -100)
            self.assertEqual(result["orders"][0]["fees_usd"], .65)
            self.assertEqual(result["orders"][0]["net_cashflow_usd"], -100.65)

    def test_future_working_order_and_proof_status_do_not_change_earlier_day_census(self):
        before = self.read()
        tuesday = MONDAY + dt.timedelta(days=1)
        row = self.state.rows("SELECT * FROM orders WHERE oid=1")[0]
        row.update(oid=2, client_id="future", day=tuesday.isoformat(), status="working",
                   placed_at=at(tuesday, 10, 0), updated_at=at(tuesday, 10, 1))
        self.state.upsert("orders", row, "oid")
        self.state.put("paper_proof", {"day": tuesday.isoformat(), "status": "passed", "open_witness": True,
                                      "close_witness": True, "passed_at": at(tuesday, 10, 5),
                                      "orders": [{"cid": "future-paper", "at": at(tuesday, 10, 1)}]})
        after = self.read()
        self.assertTrue(before["complete"])
        self.assertTrue(after["complete"])
        self.assertEqual(before["orders"], after["orders"])
        self.assertNotIn("paper_proof", after)

    def test_carry_in_closed_after_report_day_still_requires_that_days_receipts(self):
        friday, tuesday = MONDAY - dt.timedelta(days=3), MONDAY + dt.timedelta(days=1)
        row = self.state.rows("SELECT * FROM orders WHERE oid=1")[0]
        row.update(oid=2, client_id="carry-in", day=friday.isoformat(), status="filled",
                   placed_at=at(friday, 15, 0), updated_at=at(tuesday, 10, 1))
        self.state.upsert("orders", row, "oid")
        self.assertIn("authoritative_order_receipt_missing", self.read()["gaps"])
        self.state.execute("UPDATE orders SET updated_at=? WHERE oid=2", (at(friday, 15, 1),))
        self.assertTrue(self.read()["complete"])  # known terminal before the report day
        self.state.execute("UPDATE orders SET status='working' WHERE oid=2")
        self.assertIn("authoritative_order_receipt_missing", self.read()["gaps"])

    def test_future_proof_completion_cannot_rewrite_captured_report_day_status(self):
        self.evidence.call("insert", "paper", "open_witness", "proof",
                           {"proof": {"day": MONDAY.isoformat(), "status": "open_filled", "open_witness": True,
                                      "close_witness": False, "filled_at": self.clock(), "passed_at": None}})
        captured = self.read()["paper_proof"]
        tuesday = MONDAY + dt.timedelta(days=1)
        self.state.put("paper_proof", {"day": MONDAY.isoformat(), "status": "passed", "open_witness": True,
                                      "close_witness": True, "passed_at": at(tuesday, 10, 5), "orders": []})
        after = self.read()
        self.assertEqual(after["paper_proof"], captured)
        self.assertEqual(after["paper_proof"]["status"], "open_filled")

    def test_paper_carry_in_needs_receipts_unless_known_terminal_before_session(self):
        friday = MONDAY - dt.timedelta(days=3)
        work = {"cid": "carry-paper", "at": at(friday, 15, 0), "terminal": True,
                "answer": {"updated_at": "2026-09-29T14:01:00Z"}}
        proof = {"day": friday.isoformat(), "status": "passed", "orders": [work]}
        self.state.put("paper_proof", proof)
        self.assertIn("authoritative_order_receipt_missing", self.read()["gaps"])
        work["answer"]["updated_at"] = "2026-09-25T19:01:00Z"
        self.state.put("paper_proof", proof)
        self.assertTrue(self.read()["complete"])

    def test_input_manifest_binds_fees_proof_health_models_and_coverage(self):
        previous = self.read()
        mutations = [lambda: self.state.execute("UPDATE fills SET fees=.70"),
                     lambda: self.state.put("paper_proof", {"day": MONDAY.isoformat(), "status": "failed"}),
                     lambda: (self.root / HEALTH).write_text(json.dumps({MONDAY.isoformat(): {"incomplete": True}})),
                     lambda: self.evidence.db.execute("UPDATE models SET version='synthetic-corrected-metadata'"),
                     lambda: self.evidence.db.execute("UPDATE coverage SET complete=0 WHERE minute=570")]
        for mutate in mutations:
            mutate()
            current = self.read()
            self.assertNotEqual(previous["input_sha256"], current["input_sha256"])
            self.assertIn("code_sha256", current["input_manifest"])
            previous = current
        self.assertEqual(previous["orders"][0]["net_cashflow_usd"], -100.7)
        self.assertFalse(previous["complete"])

    def test_stale_cumulative_reply_does_not_settle_cashflow_or_fee_scope(self):
        for changed, reason in (({"filled_qty": "0", "filled_avg_price": None}, "cumulative_leg_fill_regressed"),
                                ({"filled_avg_price": ".9"}, "cumulative_price_changed_without_quantity"),
                                ({"filled_at": "2026-09-28T14:00:30Z"}, "broker_timestamp_regressed")):
            with self.subTest(reason=reason):
                self.evidence.call("insert", "real", "reply", self.cid,
                    {"order": {"client_id": self.cid}, "body": self.body, "model": self.model,
                     "detail": dict(self.answer, **changed)})
                current = self.read()["orders"][0]
                self.assertIn(reason, current["missing"])
                self.assertEqual(current["status"], "uncertain")
                self.assertIsNone(current["gross_cashflow_usd"])
                self.assertIsNone(current["fees_usd"])
                self.assertIsNone(current["submission_sample_comparison"]["natural_slippage_usd"])
                self.evidence.db.execute("DELETE FROM events WHERE seq=(SELECT max(seq) FROM events)")

    def test_uncheckpointed_completed_trade_stays_private_uncertain_observation(self):
        self.evidence.call("insert", "shadow", "trade", "f@1:s:trade:1",
                           {"instance": "f@1:s", "detail": {"id": 1, "pnl": 5}, "model": self.model})
        result = self.read()
        self.assertIsNone(result["trades"][0]["trade"])
        self.assertFalse(result["trades"][0]["checkpointed"])
        self.assertEqual(result["trades"][0]["observations"][0]["trade"]["pnl"], 5)
        self.assertIn("uncheckpointed_shadow_trade_or_replay", result["gaps"])

    def test_engine_identity_is_retained_and_changed_comparison_is_incomplete(self):
        self.evidence.call("insert", "real", "reply", self.cid,
            {"order": {"client_id": self.cid}, "body": self.body,
             "model": dict(self.model, engine_bundle="synthetic-engine-B"), "detail": self.answer})
        result = self.read()
        order = result["orders"][0]
        self.assertIn("model_engine_identity_missing_or_changed", order["missing"])
        self.assertEqual(order["engine_bundles"], sorted([self.model["engine_bundle"], "synthetic-engine-B"]))
        self.assertEqual(order["gross_cashflow_usd"], -100)  # measured broker cashflow survives diagnostic uncertainty
        self.assertEqual(result["model_identities"][0]["engine_bundles"], order["engine_bundles"])


@unittest.skipUnless(HAVE, "numpy not installed")
class ReportArithmetic(unittest.TestCase):
    def test_engine_change_makes_shadow_replay_amount_unknown_even_with_same_model(self):
        model = {"sha256": "same-fit", "version": "same-v", "engine_bundle": "engine-A"}
        events = [{"seq": 1, "source": "shadow", "kind": "decision", "at": 1,
                   "data": {"model": model, "work": {"arrival_mi": 2}, "quote": {"minute": 571}, "recorder_run": "run"}},
                  {"seq": 2, "source": "shadow", "kind": "fill", "at": 2,
                   "data": {"model": dict(model, engine_bundle="engine-B"), "work": {"filled": 1}, "recorder_run": "run",
                            "detail": {"qty": 1, "value": 1, "cashflow": -100, "fees": .1, "simulated_minute": 572}}}]
        out = order_report("shadow", "f@1:s:1", events, {"run": 3})
        self.assertEqual(out["model_hashes"], ["same-fit"])
        self.assertEqual(out["engine_bundles"], ["engine-A", "engine-B"])
        self.assertIn("model_engine_identity_missing_or_changed", out["missing"])
        self.assertIsNone(out["gross_cashflow_usd"])
        self.assertIsNone(out["fees_usd"])

    def test_credit_ratio_quantities_signs_and_unknown_fee_provenance(self):
        body = {"qty": "1", "limit_price": "-1", "legs": [
            {"symbol": "a", "side": "buy", "ratio_qty": "2"},
            {"symbol": "b", "side": "sell", "ratio_qty": "1"}]}
        answer = {"status": "filled", "submitted_at": "2026-09-28T13:31:00Z", "filled_at": "2026-09-28T13:31:02Z",
                  "legs": [{"symbol": "a", "side": "buy", "filled_qty": "2", "filled_avg_price": ".5"},
                           {"symbol": "b", "side": "sell", "filled_qty": "1", "filled_avg_price": "2"}]}
        quote = {"status": "sampled", "minute": 571, "legs": [
            {"symbol": "a", "bid": .4, "ask": .5, "quote_at": 10, "received_at": 11},
            {"symbol": "b", "bid": 2, "ask": 2.2, "quote_at": 10, "received_at": 11}]}
        events = [{"source": "paper", "kind": "submit", "at": 12,
                   "data": {"work": {"body": body}, "quote": quote, "model": {"sha256": "synthetic"}}},
                  {"source": "paper", "kind": "order_observed", "at": 14,
                   "data": {"detail": {"answer": answer}, "model": {"sha256": "synthetic"}}}]
        out = order_report("paper", "cid", events)
        self.assertEqual(out["gross_cashflow_usd"], 100)
        self.assertEqual(out["submission_sample_comparison"]["natural_slippage_usd"], 0)
        self.assertAlmostEqual(out["submission_sample_comparison"]["half_spreads"], 1)
        self.assertEqual(out["broker_fill_latency_seconds"], 2)
        self.assertIsNone(out["fees_usd"])
        quote["legs"][0]["quote_at"] = None
        unknown = order_report("paper", "cid", events)
        self.assertIsNone(unknown["submission_sample_comparison"]["natural_slippage_usd"])
        self.assertIn("quote_timing_unknown", unknown["missing"])


if __name__ == "__main__":
    unittest.main()
