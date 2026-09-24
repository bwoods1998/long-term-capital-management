"""The tick's own clock: `health.json` `tick_steps` (C-perf, Sept 24, 2026, the close-the-gaps run).

Measured on the box, Sept 24, 2026 08:40-08:50Z: the House's tick (`tick_duration_seconds`) took
51-64 s, ticks landed 70-80 s apart waking 5-16 agents each (30-40 s at plan time), and the House
process used about 74% of the box's one vCPU. health.json had no per-step timing, so nobody could
say which step cost what. It now carries the last tick's seconds per step, each step's slowest in
the last hour, and each background lane's last run (which is not in the tick's time).
"""

from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from league.ledger import now_iso
from league.tests.test_house import HouseCase


class TheTickSteps(HouseCase):
    def health(self):
        return json.loads((self.house.root / "health.json").read_text(encoding="utf-8"))["tick_steps"]

    def test_a_house_that_has_not_ticked_says_so(self):
        steps = self.health()  # written at startup
        self.assertEqual((steps["last"], steps["slowest_hour"], steps["ticks_in_hour"]), (None, [], 0))

    def test_the_last_tick_is_timed_step_by_step_by_name(self):
        self.seated()
        self.house.tick()
        steps = self.health()
        last = steps["last"]
        for name in ("replay_rules", "feeds", "poll:alpaca-paper", "cancel_stale", "order_path_invariants", "due", "wakes",
                     "wind_downs", "mark:alpaca-paper", "judge:alpaca-paper", "allocator", "floor_invariants", "research",
                     "schedule", "history_coverage", "merton", "hypotheses", "lab", "shards", "payout", "notices", "horizon",
                     "tuition", "population", "save_state", "publish", "health"):
            self.assertIn(name, last["steps"])
            self.assertGreaterEqual(last["steps"][name], 0)
        self.assertEqual(last["at"], json.loads((self.house.root / "health.json").read_text())["at"])
        self.assertAlmostEqual(last["total_seconds"], sum(last["steps"].values()), delta=0.01 * len(last["steps"]))
        self.assertEqual(steps["ticks_in_hour"], 1)
        self.assertEqual({row["step"] for row in steps["slowest_hour"]} <= set(last["steps"]), True)

    def test_a_slow_step_is_the_slowest_for_an_hour(self):
        invariants = self.house._floor_invariants

        def slow():
            time.sleep(0.3)
            return invariants()

        with patch.object(self.house, "_floor_invariants", slow):
            self.house.tick()
        steps = self.health()
        last = steps["last"]["steps"]
        self.assertEqual(max(last, key=last.get), "floor_invariants")
        self.assertGreaterEqual(last["floor_invariants"], 0.3)
        self.assertEqual(steps["slowest_hour"][0]["step"], "floor_invariants")
        slow_at = steps["slowest_hour"][0]["at"]
        self.clock.advance(1800)
        self.house.tick()  # half an hour on, a quick tick: still the hour's slowest step
        steps = self.health()
        self.assertLess(steps["last"]["steps"]["floor_invariants"], 0.3)
        self.assertEqual((steps["slowest_hour"][0]["step"], steps["slowest_hour"][0]["at"]), ("floor_invariants", slow_at))
        self.assertEqual(steps["ticks_in_hour"], 2)
        self.clock.advance(1900)
        self.house.tick()  # the slow tick is over an hour old
        steps = self.health()
        hour = {row["step"]: row["seconds"] for row in steps["slowest_hour"]}
        self.assertLess(hour.get("floor_invariants", 0), 0.3)
        self.assertEqual(steps["ticks_in_hour"], 2)

    def test_each_background_lane_s_last_run_is_in_health_and_not_in_the_tick(self):
        self.assertTrue(self.house._background("feeds:test", time.sleep, 0.2))
        self.house.wait(10)

        def broken():
            raise RuntimeError("down")

        self.assertTrue(self.house._background("replay:test", broken))
        self.house.wait(10)
        self.house.tick()
        steps = self.health()
        feeds, replay = steps["background"]["feeds"], steps["background"]["replay"]
        self.assertEqual((feeds["key"], feeds["state"]), ("feeds:test", "finished"))
        self.assertGreaterEqual(feeds["seconds"], 0.2)
        self.assertEqual((replay["key"], replay["state"]), ("replay:test", "failed"))
        self.assertEqual(feeds["at"], now_iso(self.clock))


if __name__ == "__main__":
    unittest.main()
