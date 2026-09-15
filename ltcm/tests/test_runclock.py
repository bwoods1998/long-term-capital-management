"""The run clock folds how long, how much and how profitable from the floor's own records."""

from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from ltcm.runclock import RunClock, fold, infra_estimate


class FoldTests(unittest.TestCase):
    def test_the_clock_starts_at_the_first_session_and_counts_todays(self):
        run = fold(
            "2026-09-18T12:00:00.000Z",
            session_starts=["2026-09-15T18:11:22.000Z", "2026-09-16T00:30:00.000Z", "2026-09-18T08:10:00.000Z"],
            decisions=7,
            marks=[],
            live_pnl_usd="12.50",
            model_spend_today_usd="0.41",
            model_spend_total_usd="6.20",
            infra_spend_total_usd="0.83",
            uptime_seconds=3600,
            models_used=["DeepSeek V4 Pro", "GLM-5.3", "DeepSeek V4 Pro"],
        )
        self.assertEqual(run["started_at"], "2026-09-15T18:11:22.000Z")
        self.assertEqual(run["sessions_total"], 3)
        self.assertEqual(run["sessions_today"], 1)
        self.assertEqual(run["decisions_total"], 7)
        self.assertEqual(run["sail_spend_total_usd"], "7.03")
        self.assertEqual(run["pnl_total_usd"], "12.50")
        self.assertEqual(run["pnl_per_sail_dollar"], "1.77")
        self.assertEqual(run["models_used"], ["DeepSeek V4 Pro", "GLM-5.3"])
        self.assertEqual(run["uptime_seconds"], 3600)

    def test_availability_is_the_share_of_marks_that_landed(self):
        at = "2026-09-16T00:00:00.000Z"
        # One day since the start: 288 five-minute marks expected; 144 landed.
        marks = [f"2026-09-15T{h:02d}:{m:02d}:00.000Z" for h in range(24) for m in (0, 10, 20, 30, 40, 50)]
        run = fold(
            at,
            session_starts=["2026-09-15T00:00:00.000Z"],
            decisions=0,
            marks=marks,
            live_pnl_usd="0",
            model_spend_today_usd="0",
            model_spend_total_usd="0",
            infra_spend_total_usd=None,
            uptime_seconds=None,
            models_used=[],
        )
        self.assertEqual(run["availability_7d_pct"], "50.0")
        self.assertIsNone(run["sail_infra_spend_total_usd"])
        self.assertIsNone(run["pnl_per_sail_dollar"], "no spend means no ratio, not infinity")

    def test_a_brand_new_floor_has_no_availability_yet(self):
        run = fold(
            "2026-09-15T18:12:00.000Z",
            session_starts=["2026-09-15T18:11:22.000Z"],
            decisions=0,
            marks=[],
            live_pnl_usd="0",
            model_spend_today_usd="0.03",
            model_spend_total_usd="0.03",
            infra_spend_total_usd="0",
            uptime_seconds=60,
            models_used=[],
        )
        self.assertIsNone(run["availability_7d_pct"])
        self.assertEqual(run["pnl_per_sail_dollar"], "0.00")

    def test_a_loss_is_a_signed_ratio(self):
        run = fold(
            "2026-09-18T12:00:00.000Z",
            session_starts=["2026-09-15T18:11:22.000Z"],
            decisions=1,
            marks=[],
            live_pnl_usd="-3.30",
            model_spend_today_usd="0",
            model_spend_total_usd="2.00",
            infra_spend_total_usd="0.20",
            uptime_seconds=0,
            models_used=[],
        )
        self.assertEqual(run["pnl_per_sail_dollar"], "-1.50")

    def test_the_infra_estimate_is_the_daily_rate_over_the_run(self):
        self.assertEqual(infra_estimate("2026-09-15T00:00:00.000Z", "2026-09-17T00:00:00.000Z", "0.30"), Decimal("0.60"))


class Event:
    def __init__(self, at):
        self.at = at


class FakeLog:
    def __init__(self, events):
        self.events = events

    def read(self, kind=None, limit=100, **kwargs):
        return [Event(at) for at in self.events.get(kind, [])][:limit]


class FakeProvider:
    def spent_today(self, desk_id=None):
        return Decimal("0.41")

    def spent_since(self, hours=24.0):
        return Decimal("6.20") if hours > 24 else Decimal("0.41")


class RunClockTests(unittest.TestCase):
    def test_it_reads_every_component_and_survives_each_one_failing(self):
        log = FakeLog({
            "desk.session_started": ["2026-09-15T18:11:22.000Z", "2026-09-16T00:30:00.000Z"],
            # Two desks marked in the same cycle: one cycle landed, not two.
            "ledger.mark": ["2026-09-15T18:20:00.000Z", "2026-09-15T18:20:00.000Z"],
            "risk.decision": ["2026-09-15T18:30:00.000Z"] * 3,
        })
        clock = RunClock(
            log,
            provider=FakeProvider(),
            live_pnl=lambda at: Decimal("4.00"),
            uptime=lambda: 1234,
            models_used=lambda: ["DeepSeek V4 Pro"],
            sail_usage=lambda: {"infra_spend_usd": "0.50"},
        )
        run = clock.read("2026-09-16T12:00:00.000Z")
        self.assertEqual(run["sessions_total"], 2)
        self.assertEqual(run["decisions_total"], 3)
        self.assertEqual(run["sail_model_spend_total_usd"], "6.20")
        self.assertEqual(run["sail_infra_spend_total_usd"], "0.50")
        self.assertEqual(run["pnl_total_usd"], "4.00")
        self.assertEqual(run["uptime_seconds"], 1234)
        # 18:11 to 12:00 next day is 214 cycles of five minutes; one landed.
        self.assertEqual(run["availability_7d_pct"], "0.4")

        def boom(*args, **kwargs):
            raise RuntimeError("down")

        broken = RunClock(
            SimpleNamespace(read=boom),
            provider=SimpleNamespace(spent_today=boom, spent_since=boom),
            live_pnl=boom,
            uptime=boom,
            models_used=boom,
            sail_usage=boom,
        )
        run = broken.read("2026-09-16T12:00:00.000Z")
        self.assertEqual(run["sessions_total"], 0)
        self.assertEqual(run["sail_spend_total_usd"], "0.00")  # infra estimate over a zero-length run
        self.assertEqual(run["pnl_total_usd"], "0.00")

    def test_without_sails_number_the_box_cost_is_estimated_from_the_daily_rate(self):
        log = FakeLog({"desk.session_started": ["2026-09-15T00:00:00.000Z"]})
        run = RunClock(log, infra_usd_per_day="0.30").read("2026-09-17T00:00:00.000Z")
        self.assertEqual(run["sail_infra_spend_total_usd"], "0.60")


if __name__ == "__main__":
    unittest.main()
