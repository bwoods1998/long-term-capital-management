"""Accounting failures must remain visible: duplicates, deposits, holds, missing categories and mixed cutoffs."""
import copy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from league import project_economics as economics

AT = "2026-09-27T06:25:30Z"
APP = "project-app"


def evidence():
    return {"schema": economics.SCHEMA, "as_of": AT, "cost_start": economics.T0,
            "financial_start": economics.FINANCIAL_START, "errors": [], "sources": {
        "models": {"as_of": AT, "booked_usd": {"sail_model": "10", "openai": "20", "claude": "30", "gym_box": "999"},
                   "holds": {k: {"count": 0, "usd": "0"} for k in economics.MODEL_KINDS}},
        "provider_requests": {"as_of": AT, "cost_basis": "verified_usage_only", "groups": {
            "completed": {"count": 1, "settled_usd": "10", "reserved_usd": "99", "unpriced": 0, "unverified": 0, "unverified_booked_usd": "0"}}},
        "house_accounting": {"as_of": AT, "rows_by_kind": {}},
        "options": {"as_of": AT, "closed_cash_by_pid": {"1": "10"}, "closed": 1, "open_or_unresolved": 0,
                    "fees_already_in_cash_usd": "2", "pending_orders": 0,
                    "last_book_change_at": economics.iso(economics.epoch(AT) - 900),
                    "recon": {"as_of": AT, "frozen": False, "problems": 0, "good": 2}},
        "broker_activity": {"as_of": AT, "read_at": economics.epoch(AT), "start_at": economics.FINANCIAL_START,
                            "fees_by_pid": {"1": "0.20"}, "fees_usd": "-0.50", "crypto_usd": "0", "interest_usd": "0.10",
                            "misc_usd": "0", "unreconciled_usd": "0", "blocking": [], "problems": []}}}


def boxes():
    return {"start_at": economics.T0, "end_at": AT, "pricing_configured": True,
            "finalized_cost_usd_nanos": 1_005_000_000_000, "sailboxes": [
                {"app_id": APP, "sailbox_id": "one", "finalized_cost_usd_nanos": 5_000_000_000,
                 "estimated_active_cost_usd_nanos": 0, "estimated_total_cost_usd_nanos": 5_000_000_000},
                {"app_id": "unrelated-app", "sailbox_id": "foreign", "finalized_cost_usd_nanos": 1_000_000_000_000,
                 "estimated_active_cost_usd_nanos": 0, "estimated_total_cost_usd_nanos": 1_000_000_000_000}]}


def external(usd="7"):
    return {"start_at": economics.T0, "end_at": AT, "usd": usd, "complete": True,
            "incremental_only": True, "source": "attributed receipts plus owner coverage of other inputs"}


class EconomicsReport(unittest.TestCase):
    def report(self, state=None, usage=None, extra=None):
        return economics.report(state or evidence(), usage or boxes(), app_id=APP, external=extra or external())

    def test_scoped_box_bill_replaces_gym_estimate_and_foreign_apps(self):
        report = self.report()
        self.assertEqual(report["inputs"]["sail_boxes"]["usd"], "5.000000")
        self.assertEqual(report["comparison_only"]["booked_gym_box_estimate_usd"], "999")
        self.assertFalse(report["comparison_only"]["included_in_total"])
        self.assertTrue(report["complete"], report["unresolved"])
        self.assertLess(Decimal(report["known_input_subtotal_usd"]), 100)

    def test_fees_are_already_in_cash_and_posted_delta_is_applied_once(self):
        report = self.report()
        self.assertEqual(report["trading"]["book_closed_net_cash_usd"], "10.000000")
        self.assertEqual(report["trading"]["realized_options_net_usd"], "10.200000")
        self.assertEqual(report["trading"]["other_reconciled_account_activity_usd"], "-0.400000")
        self.assertEqual(Decimal(report["project_net_usd"]), Decimal("9.80") - Decimal(report["known_input_subtotal_usd"]))
        state = evidence()
        state["sources"]["broker_activity"]["fees_by_pid"]["99"] = "-0.10"
        out = self.report(state)
        self.assertEqual(out["trading"]["realized_options_net_usd"], "10.200000")
        self.assertEqual(out["trading"]["other_reconciled_account_activity_usd"], "-0.500000")

    def test_diagnostic_fees_are_notes_not_an_extra_charge_or_veto(self):
        state = evidence()
        state["sources"]["broker_activity"]["problems"] = ["a fee on an order the live book does not hold"] * 8
        out = self.report(state)
        self.assertTrue(out["complete"], out["unresolved"])
        self.assertEqual(out["project_net_usd"], self.report()["project_net_usd"])
        self.assertEqual(len(out["trading"]["diagnostic_notes"]), 8)

    def test_known_unreconciled_dollars_remain_visible_in_existing_profit_convention(self):
        state = evidence()
        state["sources"]["broker_activity"]["unreconciled_usd"] = "-1.25"
        out = self.report(state)
        self.assertEqual(out["trading"]["account_unreconciled_usd"], "-1.250000")
        self.assertFalse(out["trading"]["broker_reconciled"])
        self.assertTrue(out["complete"], out["unresolved"])
        self.assertEqual(Decimal(out["known_realized_less_known_inputs_usd"]), Decimal(self.report()["project_net_usd"]) - Decimal("1.25"))

    def test_deposits_and_account_equity_never_create_profit(self):
        state = evidence()
        state.update(account_equity="1000000", deposits="999000", withdrawals="4")
        state["sources"]["broker_activity"].update(cash="1000000", deposits="999000")
        self.assertEqual(self.report(state)["project_net_usd"], self.report()["project_net_usd"])

    def test_actual_provider_cost_is_alternative_to_booked_sail_not_an_addition(self):
        state = evidence()
        state["sources"]["provider_requests"]["groups"]["completed"]["settled_usd"] = "8"
        out = self.report(state)
        self.assertEqual(out["inputs"]["sail_model"]["usd"], "8.000000")
        self.assertEqual(out["inputs"]["sail_model"]["booked_usd"], "10.000000")
        self.assertIsNone(out["project_net_usd"])
        self.assertEqual(Decimal(out["known_input_subtotal_usd"]), Decimal(self.report()["known_input_subtotal_usd"]) - 2)

    def test_holds_and_provider_reserves_are_not_extra_settled_invoices(self):
        state = evidence()
        state["sources"]["models"]["holds"]["claude"] = {"count": 1, "usd": "5"}
        state["sources"]["provider_requests"]["groups"]["prepared"] = {
            "count": 1, "unpriced": 1, "settled_usd": "0", "reserved_usd": "1000", "unverified": 0, "unverified_booked_usd": "0"}
        out = self.report(state)
        self.assertEqual(out["inputs"]["claude"]["usd"], "25.000000")
        self.assertEqual(Decimal(out["known_input_subtotal_usd"]), Decimal(self.report()["known_input_subtotal_usd"]) - 5)
        self.assertIsNone(out["project_net_usd"])

    def test_missing_external_costs_are_unknown_and_explicit_verified_zero_is_zero(self):
        out = economics.report(evidence(), boxes(), app_id=APP)
        self.assertIsNone(out["inputs"]["external_engineering_and_other"]["usd"])
        self.assertIsNone(out["project_net_usd"])
        self.assertTrue(self.report(extra=external("0"))["complete"])
        overlap = external("5")
        overlap["incremental_only"] = False
        self.assertIsNone(self.report(extra=overlap)["inputs"]["external_engineering_and_other"]["usd"])

    def test_missing_model_category_or_provider_amount_does_not_become_zero(self):
        state = evidence()
        del state["sources"]["models"]["booked_usd"]["claude"]
        self.assertIsNone(self.report(state)["inputs"]["claude"]["usd"])
        state = evidence()
        state["sources"]["provider_requests"]["groups"]["completed"]["settled_usd"] = None
        self.assertIsNone(self.report(state)["inputs"]["sail_model"]["usd"])
        for bad in (["unreadable"], {"completed": None}, {"completed": {"count": 1}}):
            state["sources"]["provider_requests"]["groups"] = bad
            self.assertIsNone(self.report(state)["inputs"]["sail_model"]["usd"])

    def test_live_box_estimate_is_separate_and_not_final_billing(self):
        usage = boxes()
        usage["sailboxes"][0].update(estimated_active_cost_usd_nanos=2_000_000_000, estimated_total_cost_usd_nanos=7_000_000_000)
        out = self.report(usage=usage)
        self.assertEqual(out["inputs"]["sail_boxes"]["usd"], "5.000000")
        self.assertEqual(Decimal(out["provisional_subtotal_with_active_box_estimate_usd"]), Decimal(out["known_input_subtotal_usd"]) + 2)
        self.assertIsNone(out["project_net_usd"])

    def test_duplicate_box_or_wrong_start_cannot_double_charge(self):
        usage = boxes()
        usage["sailboxes"].append(copy.deepcopy(usage["sailboxes"][0]))
        self.assertIsNone(self.report(usage=usage)["inputs"]["sail_boxes"]["usd"])
        usage = boxes()
        usage["start_at"] = economics.FINANCIAL_START
        self.assertIsNone(self.report(usage=usage)["inputs"]["sail_boxes"]["usd"])

    def test_subscriptions_keep_the_financial_basis_not_the_earlier_cost_start(self):
        out = self.report()
        expected = Decimal(80) * Decimal(86400) / economics.MONTH_SECONDS
        self.assertEqual(out["inputs"]["thetadata_usd"]["usd"], economics.money(expected))
        self.assertEqual(out["cost_start"], "2026-09-26T06:23:14Z")
        self.assertEqual(out["financial_start"], "2026-09-26T06:25:30Z")

    def test_fresh_but_asynchronous_sources_cannot_claim_reconciled_net(self):
        state = evidence()
        state["sources"]["broker_activity"]["as_of"] = economics.iso(economics.epoch(AT) - 60)
        out = self.report(state)
        self.assertTrue(out["trading"]["cached_broker_receipt_consistent"])
        self.assertFalse(out["trading"]["broker_reconciled"])
        self.assertIsNone(out["project_net_usd"])
        usage = boxes()
        usage["end_at"] = economics.iso(economics.epoch(AT) - 5)
        self.assertIsNone(self.report(usage=usage)["project_net_usd"])
        state = evidence()
        state["sources"]["house_accounting"]["as_of"] = economics.iso(economics.epoch(AT) - 5)
        self.assertIsNone(self.report(state)["project_net_usd"])

    def test_stale_receipt_late_book_change_or_blocking_liability_prevents_known_profit(self):
        for change in ("stale", "late_fill", "blocking"):
            state = evidence()
            broker = state["sources"]["broker_activity"]
            if change == "stale":
                broker["as_of"] = economics.iso(economics.epoch(AT) - 601)
            elif change == "late_fill":
                broker["as_of"] = economics.iso(economics.epoch(AT) - 60)
                state["sources"]["options"]["last_book_change_at"] = economics.iso(economics.epoch(AT) - 30)
            else:
                broker["blocking"] = ["unresolved assignment shares"]
            out = self.report(state)
            self.assertIsNone(out["trading"]["realized_options_net_usd"], change)
            self.assertIsNone(out["project_net_usd"], change)

    def test_open_inventory_keeps_complete_net_unknown(self):
        state = evidence()
        state["sources"]["options"]["open_or_unresolved"] = 1
        out = self.report(state)
        self.assertEqual(out["trading"]["realized_options_net_usd"], "10.200000")
        self.assertIsNone(out["project_net_usd"])
        self.assertIsNone(out["known_realized_less_known_inputs_usd"])

    def test_missing_inventory_and_reconciliation_fields_do_not_become_clear(self):
        for field in ("pending_orders", "recon", "open_or_unresolved"):
            state = evidence()
            del state["sources"]["options"][field]
            self.assertIsNone(self.report(state)["project_net_usd"], field)
        state = evidence()
        del state["sources"]["house_accounting"]["rows_by_kind"]
        self.assertIsNone(self.report(state)["project_net_usd"])

    def test_private_snapshots_are_idempotent_concurrently_and_keep_history(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "reports"
            value = self.report()
            with ThreadPoolExecutor(max_workers=4) as pool:
                paths = list(pool.map(lambda _: economics.persist(directory, value), range(8)))
            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(len(list(directory.iterdir())), 1)
            self.assertEqual(stat.S_IMODE(paths[0].stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            changed = copy.deepcopy(value)
            changed["complete"] = False
            self.assertNotEqual(economics.persist(directory, changed), paths[0])
            self.assertEqual(json.loads(paths[0].read_text()), value)


class CollectReadOnly(unittest.TestCase):
    def test_provider_receipt_uses_request_time_and_never_counts_reservations_as_cost(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = sqlite3.connect(root / "swarm-provider.sqlite")
            db.execute("CREATE TABLE requests(created_at TEXT,status TEXT,cost_usd TEXT,reserved_usd TEXT,error TEXT)")
            db.executemany("INSERT INTO requests VALUES (?,?,?,?,?)", [
                ("2026-09-25T23:00:00Z", "completed", "9000", "10000", None),
                ("2026-09-26T09:00:00Z", "completed", "1.25", "20", None),
                ("2026-09-26T10:00:00Z", "incomplete", "0.25", "5", None),
                ("2026-09-26T11:00:00Z", "prepared", None, "2", None),
                ("2026-09-26T12:00:00Z", "abandoned", None, "3", None),
                ("2026-09-26T13:00:00Z", "completed", "40", "40", "usage_unsettled")])
            db.commit()
            db.close()
            source = economics.collect(root, clock=lambda: economics.epoch(AT))["sources"]["provider_requests"]
            self.assertEqual(source["groups"]["completed"]["settled_usd"], "1.250000")
            self.assertEqual(source["groups"]["completed"]["count"], 2)
            self.assertEqual(source["groups"]["completed"]["unverified_booked_usd"], "40.000000")
            state = evidence()
            state["sources"]["provider_requests"] = source
            out = economics.report(state, boxes(), app_id=APP, external=external())
            self.assertEqual(out["inputs"]["sail_model"]["usd"], "1.500000")
            self.assertIn("provider has 2 unpriced request(s); reservations are not added as invoices", out["unresolved"])

    def test_late_settlement_of_a_prior_period_call_cannot_reduce_current_cost(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = sqlite3.connect(root / "swarm.sqlite")
            db.executescript("CREATE TABLE spend(seq INTEGER,epoch REAL,kind TEXT,usd REAL,detail TEXT); CREATE TABLE kv(key TEXT,value TEXT);")
            start, at = economics.epoch(economics.T0), economics.epoch(AT)
            db.executemany("INSERT INTO spend VALUES (?,?,?,?,?)", [
                (1, start - 10, "claude", 10, '{"hold":"old","request":"old-request"}'),
                (2, start - 5, "openai", 20, '{"hold":"prior-openai"}'),
                (3, start + 10, "claude", -9, '{"settles":"old","request":"old-request"}'),
                (4, start + 20, "openai", -18, '{"settles":"prior-openai"}'),
                (5, start + 30, "claude", 6, '{"hold":"new","request":"new-request"}'),
                (6, start + 40, "claude", -2, '{"settles_hold":"new-request"}'),
                (7, start + 50, "openai", 5, '{"hold":"new-openai"}'),
                (8, start + 60, "openai", -1, '{"settles":"new-openai"}')])
            db.executemany("INSERT INTO kv VALUES (?,?)", [("unsettled", "{}"), ("claude_unsettled", "{}")])
            db.commit()
            db.close()
            models = economics.collect(root, clock=lambda: at)["sources"]["models"]
            self.assertEqual(models["booked_usd"]["claude"], "4.000000")
            self.assertEqual(models["booked_usd"]["openai"], "4.000000")
            self.assertEqual(models["holds"]["openai"]["usd"], "0.000000")
            self.assertEqual(models["prior_period_settlements_excluded"], {"claude": 1, "openai": 1})

    def test_negative_settlements_and_unmatched_holds_are_preserved_without_db_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "swarm.sqlite"
            db = sqlite3.connect(path)
            db.executescript("CREATE TABLE spend(seq INTEGER,epoch REAL,kind TEXT,usd REAL,detail TEXT); CREATE TABLE kv(key TEXT,value TEXT);")
            at = economics.epoch(AT)
            db.executemany("INSERT INTO spend VALUES (?,?,?,?,?)", [
                (1, at - 10, "claude", 10, '{"hold":"a"}'), (2, at - 5, "claude", -4, '{"settles_hold":"a"}'),
                (3, at - 4, "openai", 20, '{"hold":"lost-response"}'),
                (4, economics.epoch(economics.T0) - 1, "sail_model", 500, '{}')])
            db.executemany("INSERT INTO kv VALUES (?,?)", [("unsettled", "{}"), ("claude_unsettled", "{}")])
            db.commit()
            db.close()
            before = path.read_bytes()
            receipt = economics.collect(root, clock=lambda: at)
            models = receipt["sources"]["models"]
            self.assertEqual(models["booked_usd"]["claude"], "6.000000")
            self.assertNotIn("sail_model", models["booked_usd"])
            self.assertEqual(models["holds"]["openai"], {"count": 1, "usd": "20.000000"})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(set(p.name for p in root.iterdir()), {"swarm.sqlite"})

    def test_missing_state_never_creates_empty_databases_or_known_zero_profit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            receipt = economics.collect(root, clock=lambda: economics.epoch(AT))
            self.assertEqual(list(root.iterdir()), [])
            out = economics.report(receipt, None, app_id=APP)
            self.assertIsNone(out["trading"]["book_closed_net_cash_usd"])
            self.assertIsNone(out["inputs"]["sail_model"]["usd"])
            self.assertIsNone(out["project_net_usd"])


if __name__ == "__main__":
    unittest.main()
