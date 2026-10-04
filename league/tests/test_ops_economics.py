"""The close economics on the House: the laptop's numbers on the same receipts, the cutoff, p30, and a run end to end."""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from league import project_economics as PE
from league.ops import economics as E
from league.ops.context import Context

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ops_economics"
#: The synthetic TypeSafe reading before T0 the expected summary was rendered with (the laptop's constant, replaced).
TYPESAFE_BEFORE_T0 = "2.00"


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def load(name):
    return json.loads((FIXTURES / name).read_text())


def comparable(summary):
    """The laptop's render's numbers and verdicts: its prose (each cost's basis, the unknowns) and the snapshot's path
    are its own words and places, not numbers."""
    out = json.loads(json.dumps(summary))
    for cost in out["costs"]:
        cost.pop("basis", None)
    out.pop("unknowns", None)
    out.pop("p30", None)
    out.pop("known_input_cost_subtotal_usd", None)
    out.pop("cost_accounting_complete", None)
    for cost in out["costs"]:
        cost.pop("estimated_active_usd", None)
    out["library_report"].pop("snapshot", None)
    return out


class Render(unittest.TestCase):
    def test_the_saved_receipts_have_the_expected_accounting_with_holds_counted_once(self):
        summary = E.render(load("house.json"), load("library.json"), load("sail.json"), load("external.json"),
                           lib_meta={"snapshot": None, "idempotent": True}, typesafe_before_t0=TYPESAFE_BEFORE_T0)
        self.assertEqual(comparable(summary), load("expected-summary.json"))
        self.assertEqual(summary["net"]["net_usd"], "-165.41")

    def test_the_rules_are_the_reporters(self):
        self.assertEqual((E.T0, E.FS), (PE.T0, PE.FINANCIAL_START))

    def test_without_the_owners_typesafe_figure_the_bound_is_the_whole_meter(self):
        summary = E.render(load("house.json"), load("library.json"), load("sail.json"), None, lib_meta={})
        typesafe = [c for c in summary["costs"] if c["service"].startswith("TypeSafe")][0]
        self.assertEqual(typesafe["usd"], "5.00")
        self.assertFalse(summary["net"]["criterion_5_met"])

    def test_p30_sums_the_trailing_thirty_new_york_days_of_realized_pnl(self):
        summary = {"cutoff": "2026-11-05T21:00:00Z", "realized": {"by_close_day": [
            {"day": "2026-10-06", "closed_positions": 1, "total_usd": "50.00"},
            {"day": "2026-10-07", "closed_positions": 2, "total_usd": "-3.25"},
            {"day": "2026-11-05", "closed_positions": 1, "total_usd": "1.10"}]}}
        got = E.p30(summary)
        self.assertEqual((got["usd"], got["from_day"], got["to_day"], got["closed_positions"]), ("-2.15", "2026-10-07", "2026-11-05", 3))

    def test_the_cutoff_is_the_sessions_own_close(self):
        self.assertEqual(E.zulu(E.cutoff_of(at("2026-10-05T20:10:00Z"))), "2026-10-05T20:00:00Z")
        self.assertEqual(E.zulu(E.cutoff_of(at("2026-11-27T18:10:00Z"))), "2026-11-27T18:00:00Z")  # an early close
        self.assertEqual(E.zulu(E.cutoff_of(at("2026-11-02T21:10:00Z"))), "2026-11-02T21:00:00Z")  # winter
        self.assertEqual(E.zulu(E.cutoff_of(at("2026-10-10T12:00:00Z"))), "2026-10-09T20:00:00Z")  # a Saturday: Friday's

    def test_the_markdown_carries_the_net_and_p30(self):
        summary = E.render(load("house.json"), load("library.json"), load("sail.json"), load("external.json"),
                           lib_meta={"snapshot": None, "idempotent": True}, typesafe_before_t0=TYPESAFE_BEFORE_T0)
        summary["p30"] = E.p30(summary)
        text = E.markdown(summary)
        self.assertIn("**Net = realized - costs** | **-165.41**", text)
        self.assertIn("Trailing 30-day realized options P&L", text)

    def test_claude_gateway_holds_are_counted_once_and_not_called_settled(self):
        house, library = load("house.json"), load("library.json")
        house["costs"]["gateway_health"]["claude"].update(spent_usd="10", settled_usd="8", inflight_usd="2")
        house["costs"]["swarm_spend_after_cutoff"] = []
        library["inputs"]["claude"]["usd"] = "8"
        summary = E.render(house, library, load("sail.json"), load("external.json"), lib_meta={})
        cost = next(c for c in summary["costs"] if c["service"].startswith("Claude"))
        self.assertEqual((cost["usd"], cost["settled_usd"]), ("10.00", "8.00"))

    def test_active_box_estimates_are_accrued_but_never_settled(self):
        sail = load("sail.json")
        sail["t0-cutoff"]["estimated_active_cost_usd_nanos"] = "7000000000"
        summary = E.render(load("house.json"), load("library.json"), sail, load("external.json"), lib_meta={})
        cost = next(c for c in summary["costs"] if c["service"].startswith("Sail"))
        self.assertEqual((cost["settled_usd"], cost["estimated_active_usd"]), ("50.62", "7.00"))
        self.assertGreaterEqual(E.D(cost["usd"]), E.D(cost["settled_usd"]) + E.D(cost["estimated_active_usd"]))

    def test_unread_model_cost_stays_unknown_and_net_cannot_be_claimed(self):
        house, library, sail = load("house.json"), load("library.json"), load("sail.json")
        library["inputs"]["sail_model"]["usd"] = None
        library["complete"] = False
        library["unresolved"] = ["provider settlement unread"]
        house["costs"]["guard_meter_now"]["metered_spent"] = "0"
        house["costs"]["sail_requests_after_cutoff"]["usd"] = "0"
        for row in sail.values():
            row["finalized_cost_usd_nanos"] = "0"
            row["estimated_active_cost_usd_nanos"] = "0"
        summary = E.render(house, library, sail, load("external.json"), lib_meta={})
        cost = next(c for c in summary["costs"] if c["service"].startswith("Sail"))
        self.assertIsNone(cost["usd"])
        self.assertIsNone(summary["total_costs_usd"])
        self.assertIsNone(summary["net"]["net_usd"])
        self.assertIsNotNone(summary["known_input_cost_subtotal_usd"])
        self.assertFalse(summary["cost_accounting_complete"])
        self.assertFalse(summary["net"]["criterion_5_met"])
        self.assertIn("Sail (models + boxes): input cost was not read (unknown, not zero)", summary["unknowns"])

    def test_missing_box_price_is_unknown_even_with_zero_model_spend(self):
        sail = load("sail.json")
        sail["t0-cutoff"].pop("estimated_active_cost_usd_nanos")
        summary = E.render(load("house.json"), load("library.json"), sail, load("external.json"), lib_meta={})
        cost = next(c for c in summary["costs"] if c["service"].startswith("Sail"))
        self.assertIsNone(cost["usd"])
        self.assertIsNone(summary["total_costs_usd"])

    def test_missing_daily_cost_is_unknown_and_does_not_lower_the_daily_total(self):
        house = load("house.json")
        house["costs"]["sail_requests_24h"]["usd"] = None
        summary = E.render(house, load("library.json"), load("sail.json"), load("external.json"), lib_meta={})
        row = next(c for c in summary["burn_per_day"]["rows"] if c["service"] == "Sail models")
        self.assertIsNone(row["last24h_usd"])
        self.assertIsNone(summary["burn_per_day"]["total_last24h_usd"])
        self.assertIsNotNone(summary["burn_per_day"]["total_last4h_pace_per_day_usd"])


class Gateway:
    """The gateway as the economics reads it: GET only; an empty account record."""

    def __init__(self):
        self.gets = []

    def get(self, path, params=None):
        self.gets.append(path)
        if path == "/v1/health":
            return {"claude": {"spent_usd": "1.00", "inflight_usd": "0", "remaining_usd": "9", "cap_usd": "10"},
                    "sail": {"balance_usd": "50", "spend_usd": "1"}, "typesafe": {"spent_usd": "0"},
                    "frontier": {"month": "2026-10", "spent_usd": "0", "cap_usd": "0"}, "kill_switch": False}
        if path == "/v1/alpaca/v2/account":
            return {"status": "ACTIVE", "equity": "100.00", "accrued_fees": "0"}
        if "activities" in path or path.endswith("/orders") or path.endswith("/positions"):
            return []
        return {}

    def post(self, path, body):
        raise AssertionError("economics never posts")


class Sail:
    def get(self, box):
        return {"sailbox_id": box, "app_id": "app_test"}

    def spend(self, *, app=None, since=None, until=None, sailbox=None):
        return {"pricing_configured": True, "start_at": since, "end_at": until, "finalized_cost_usd_nanos": "1000000000",
                "estimated_active_cost_usd_nanos": "0", "estimated_total_cost_usd_nanos": "1000000000",
                "sailboxes": [{"sailbox_id": "sb_00000001", "app_id": app, "finalized_cost_usd_nanos": "1000000000",
                               "estimated_active_cost_usd_nanos": "0", "estimated_total_cost_usd_nanos": "1000000000"}]}


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.root.mkdir()
        db = sqlite3.connect(self.root / "swarm.sqlite")
        db.execute("CREATE TABLE spend (seq INTEGER PRIMARY KEY, epoch REAL, at TEXT, kind TEXT, usd REAL, detail TEXT)")
        db.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO spend(epoch, at, kind, usd, detail) VALUES (?, '2026-10-01T00:00:00Z', 'gym_box', 0.5, '{}')",
                   (at("2026-10-01T00:00:00Z"),))
        db.commit()
        db.close()
        db = sqlite3.connect(self.root / "swarm-provider.sqlite")
        db.execute("CREATE TABLE requests (status TEXT, cost_usd REAL, reserved_usd REAL, error TEXT, created_at TEXT)")
        db.commit()
        db.close()
        db = sqlite3.connect(self.root / "ledger.sqlite")
        db.execute("CREATE TABLE ledger (seq INTEGER PRIMARY KEY, kind TEXT, at TEXT, payload TEXT)")
        db.commit()
        db.close()
        os.environ["SAILBOX_ID"] = "sb_00000001"
        self.addCleanup(os.environ.pop, "SAILBOX_ID", None)

    def test_a_run_on_an_empty_book_writes_the_private_summary_read_only(self):
        now = at("2026-10-05T20:10:00Z")
        before = {p.name: p.stat().st_mtime_ns for p in self.root.iterdir()}
        gateway = Gateway()
        ctx = Context("economics", root=self.root, due_at=now, config={"performance": {"start_equity": "100.00"}},
                      clock=lambda: now, gateway=gateway, sail=Sail(), settings_value={})
        out = E.run(ctx)
        self.assertEqual(out["cutoff"], "2026-10-05T20:00:00Z")
        folder = self.root / "economics" / "20261005-close"
        summary = json.loads((folder / "summary.json").read_text())
        self.assertEqual(summary["realized"]["realized_options_pnl_usd"], "0.00")
        self.assertEqual(summary["p30"]["usd"], "0.00")
        self.assertTrue((folder / "summary.md").read_text().startswith("# LTCM economics at the 2026-10-05T20:00:00Z cutoff"))
        self.assertTrue(json.loads((folder / "receipts" / "library-run.json").read_text())["idempotent"])
        self.assertEqual(os.stat(folder / "summary.json").st_mode & 0o777, 0o600)
        self.assertEqual(E.latest(self.root)["cutoff"], "2026-10-05T20:00:00Z")
        # Read-only: the House's databases were not touched, and only GETs went out.
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in self.root.iterdir() if p.name in before}, before)
        self.assertNotIn("swarm.sqlite-wal", {p.name for p in self.root.iterdir()})
        self.assertIn("/v1/health", gateway.gets)


if __name__ == "__main__":
    unittest.main()
