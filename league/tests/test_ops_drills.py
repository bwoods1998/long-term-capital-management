"""league/ops/drills.py: the monthly drills job asks the updater for the rollback drill (never runs it in its own child),
reports the last one on the record, and runs the funding drill per meter."""
import json
import tempfile
import unittest
from pathlib import Path

from league.ops import drills
from league.updater import DRILL_REQUEST
from league.watchdog import iso

NOW = 1_791_039_600.0  # 2026-10-03T15:00:00Z, the first Saturday of October


class TheDrillsJob(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = Path(self.dir.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.alerts = []
        self.funded = []

    def tearDown(self):
        self.dir.cleanup()

    def ctx(self, **extra):
        def funding(ctx, meter):
            self.funded.append(meter)
            return {"drill": "funding", "meter": meter, "ok": True, "root": "/private", "checks": {"cliff_seen": True}}

        return {"root": self.root, "base": self.base, "now": NOW, "due_at": NOW, "funding_drill": funding,
                "alert": lambda level, text: self.alerts.append((level, text)), **extra}

    def test_the_request_is_where_the_updater_reads_it(self):
        self.assertEqual(drills.REQUEST, DRILL_REQUEST)

    def test_the_rollback_drill_is_requested_not_run(self):
        out = drills.run(self.ctx())
        path = self.root / DRILL_REQUEST
        self.assertTrue(out["rollback"]["requested"])
        self.assertEqual(json.loads(path.read_text())["at"], iso(NOW))
        self.assertEqual(self.funded, ["sail", "claude"])
        self.assertNotIn("root", out["funding"][0], "no private path in the receipt")
        self.assertTrue(out["ok"])
        self.assertEqual(out["not_built"], list(drills.NOT_BUILT))
        self.assertEqual([level for level, _ in self.alerts], ["info"], "no drill on the record yet")
        # A request the updater never took is replaced, and the receipt says so.
        self.assertTrue(drills.run(self.ctx())["rollback"]["replaced_unlaunched"])

    def test_the_last_drill_on_the_record_is_reported_and_a_failure_warned(self):
        rows = [{"at": iso(NOW - 50 * 86400), "stage": "drill", "outcome": "rolled_back", "release": "drill-old"},
                {"at": iso(NOW - 28 * 86400), "stage": "verdict", "verdict": "promoted", "release": "main-abc"},
                {"at": iso(NOW - 28 * 86400), "stage": "drill", "outcome": "failed", "ok": False, "release": "drill-20260905T150000Z",
                 "reasons": ["the watch did not roll the drill copy back"]}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
        out = drills.run(self.ctx())
        self.assertEqual((out["last_rollback_drill"]["release"], out["last_rollback_drill"]["outcome"]), ("drill-20260905T150000Z", "failed"))
        [(level, text)] = self.alerts
        self.assertEqual(level, "warning")
        self.assertIn("did not roll the drill copy back", text)

    def test_a_funding_drill_that_fails_is_a_warning_and_the_job_not_ok(self):
        def funding(ctx, meter):
            if meter == "claude":
                raise RuntimeError("gateway down")
            return {"ok": True}

        out = drills.run(self.ctx(funding_drill=funding))
        self.assertFalse(out["ok"])
        self.assertIn("gateway down", out["funding"][1]["error"])
        self.assertTrue(any("claude funding drill did not pass" in text for _, text in self.alerts))

    def test_the_budget_rules_own_funding_drill_runs_by_default(self):
        sent = []
        ctx = self.ctx(notify=lambda facts: sent.append(facts) or {"sent": True}, config={})
        ctx.pop("funding_drill")
        out = drills.run(ctx)
        self.assertEqual([r["meter"] for r in out["funding"]], ["sail", "claude"])
        self.assertTrue(all(f.get("test") is True for f in sent), sent)
        self.assertEqual(len(sent), 2)


if __name__ == "__main__":
    unittest.main()
