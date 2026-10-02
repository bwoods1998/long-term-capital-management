"""league/ops/drills.py: the monthly drills job asks the updater for the rollback drill (never runs it in its own child),
checks the verdict the drill leaves on the record, and runs the funding drill on every meter."""
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
        self.now = [NOW]
        self.funded = []

    def tearDown(self):
        self.dir.cleanup()

    def ctx(self, **extra):
        def funding(ctx, meter):
            self.funded.append(meter)
            return {"drill": "funding", "meter": meter, "ok": True, "root": "/private", "checks": {"cliff_seen": True}}

        return {"root": self.root, "base": self.base, "now": lambda: self.now[0], "funding_drill": funding, **extra}

    def test_the_request_is_where_the_updater_reads_it(self):
        self.assertEqual(drills.REQUEST, DRILL_REQUEST)

    def test_the_rollback_drill_is_requested_not_run(self):
        out = drills.request_rollback(self.ctx())
        self.assertEqual(json.loads((self.root / DRILL_REQUEST).read_text())["at"], iso(NOW))
        self.assertEqual((out["requested_ts"], out.get("replaced")), (NOW, None))
        self.assertTrue(drills.request_rollback(self.ctx())["replaced"], "one request stands at a time")
        self.assertFalse(hasattr(drills, "launch_rollback"), "nothing in the job's child starts a watchdog")

    def test_the_verdict_is_read_after_the_request_and_a_leftover_request_withdrawn(self):
        requested = drills.request_rollback(self.ctx())
        (self.root / DRILL_REQUEST).unlink()  # the updater took it
        self.now[0] += 600
        self.assertIsNone(drills.check_rollback(self.ctx(), requested), "still due")
        rows = [{"ts": NOW - 86400, "stage": "drill", "outcome": "rolled_back", "ok": True, "release": "drill-old"},
                {"ts": NOW + 1500, "stage": "restart", "ok": True, "release": "drill-20261003T152500Z"},
                {"ts": NOW + 2700, "stage": "drill", "outcome": "promoted", "ok": False, "release": "drill-20261003T152500Z",
                 "reasons": ["the watch did not roll the drill copy back"]}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
        out = drills.check_rollback(self.ctx(), requested)
        self.assertEqual((out["ok"], out["outcome"], out["release"]), (False, "promoted", "drill-20261003T152500Z"))
        self.assertNotIn("withdrawn", out)
        # A verdict with the request still on disk (an earlier drill's row): the request is withdrawn all the same.
        requested = drills.request_rollback(self.ctx())
        self.now[0] += 60
        (self.base / "deploys.jsonl").write_text(json.dumps({"ts": self.now[0], "stage": "drill", "outcome": "refused",
                                                             "ok": False, "reasons": ["inside the session"]}) + "\n")
        out = drills.check_rollback(self.ctx(), requested)
        self.assertEqual((out["ok"], out["withdrawn"]), (False, True))
        self.assertFalse((self.root / DRILL_REQUEST).exists())

    def test_the_funding_drill_runs_on_every_meter_and_one_failing_fails_it(self):
        out = drills.drill_funding(self.ctx())
        self.assertTrue(out["ok"])
        self.assertEqual(self.funded, ["sail", "claude"])
        self.assertNotIn("root", out["meters"]["sail"], "no private path in the receipt")

        def funding(ctx, meter):
            if meter == "claude":
                raise RuntimeError("gateway down")
            return {"ok": True}

        out = drills.drill_funding(self.ctx(funding_drill=funding))
        self.assertFalse(out["ok"])
        self.assertIn("gateway down", out["meters"]["claude"]["error"])
        self.assertIn("claude", out["error"])

    def test_the_budget_rules_own_funding_drill_runs_by_default(self):
        sent = []
        ctx = self.ctx(notify=lambda facts: sent.append(facts) or {"sent": True}, config={})
        ctx.pop("funding_drill")
        out = drills.drill_funding(ctx)
        self.assertEqual(sorted(out["meters"]), ["claude", "sail"])
        self.assertTrue(out["ok"], out)
        self.assertTrue(all(f.get("test") is True for f in sent), sent)
        self.assertEqual(len(sent), 2)


if __name__ == "__main__":
    unittest.main()
