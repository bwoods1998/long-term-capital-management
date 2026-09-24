"""The watch (`scripts/floor_watch.py`) reads what it says it reads.

Sept 24, 2026 (the close-the-gaps run, workstream B and L3): `--since` was compared as text with
the ledger's `at`, an ISO stamp with `T`; sqlite's `datetime('now', '-1 hour')` yields a space
instead, and since a space sorts before `T` that admitted the whole day. The newest hourly yield
row was looked up as `"what": "yield"` with a space, which the ledger's canonical JSON never
writes, so the watch never printed a yield row. These tests run the box snippet itself against a
throwaway state directory.

The watch shows the seat market by evidence (S1-S4 of the close-the-gaps run, Sept 24, 2026).

`scripts/floor_watch.py` runs a read-only snippet on the House box and prints what the owner's plan asks to
be watched. The review of #245 found the seat line carried only the waiters and the displaceable count: the
seats holding no evidence (`seats_holding_none`), the desks' evidence clocks the grace follows, why a class
of waiter (the retained candidates too) was last refused a seat, and the House-sent sales stopped after three
identical refusals reached no operator. The snippet runs here against a state directory built for the test.
"""


from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from league.ledger import Ledger
from league.tests.fakes import Clock
from scripts import floor_watch


class TheSinceStamp(unittest.TestCase):
    def test_a_space_separated_stamp_becomes_the_ledgers_iso_form(self):
        self.assertEqual(floor_watch.normalize_since("2026-09-24 00:42:00"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24T00:42:00"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24T00:42:00.123Z"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24T02:42:00+02:00"), "2026-09-24T00:42:00")
        self.assertEqual(floor_watch.normalize_since("2026-09-24"), "2026-09-24T00:00:00")

    def test_what_is_not_a_time_is_refused(self):
        for bad in ("yesterday", "", "2026-13-01T00:00:00", "now-1h"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                floor_watch.normalize_since(bad)

    def test_the_space_form_would_have_admitted_the_whole_day(self):
        # The defect itself: string order, which is what the snippet's `at >= ?` compares.
        late_in_the_day = "2026-09-24T00:05:00.000Z"
        self.assertTrue(late_in_the_day >= "2026-09-24 23:00:00", "the raw space form admits a row from before it")
        self.assertFalse(late_in_the_day >= floor_watch.normalize_since("2026-09-24 23:00:00"))

    def test_the_command_line_normalizes_it(self):
        parser = floor_watch.parser()
        self.assertEqual(parser.parse_args(["--since", "2026-09-24 00:42:00"]).since, "2026-09-24T00:42:00")
        with self.assertRaises(SystemExit):
            parser.parse_args(["--since", "not a time"])


class TheBoxSnippet(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def run_snippet(self, since, health):
        (self.root / "health.json").write_text(json.dumps(health), encoding="utf-8")
        done = subprocess.run([sys.executable, "-c", floor_watch.BOX_SNIPPET, since, str(self.root)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_it_prints_the_yield_row_the_repeating_warnings_and_the_health_failures(self):
        since = floor_watch.normalize_since(self.ledger.append("ops.started", {}).at)
        self.clock.advance(60)
        self.ledger.append("ops.budget", {"what": "yield", "spend_usd": {"research": "1.3349"}, "evidence": {"research": {"candidates": 3}},
                                          "usd_per": {"research": {"candidates": "0.4450"}},
                                          "by_profile": {"pro_asap": {"sessions": 4, "candidates": 1}},
                                          "since": "2026-09-23T23:49:28.127Z", "until": "2026-09-24T00:49:28.127Z"})
        self.ledger.append("ops.alert", {"level": "error", "text": "a warning repeated 10 times in 30 minutes: the lab's step failed (IndexError)"})
        repeating = [{"text": "the lab's step failed (IndexError: list index out of range)", "count": 12,
                      "first_seen": "2026-09-23T23:21:59Z", "last_seen": "2026-09-23T23:44:48Z"}]
        failures = [{"check": "lab_evaluates", "text": "the lab evaluated nothing in the last hour while 607 candidates are queued",
                     "since": "2026-09-23T23:37:17Z"}]
        out = self.run_snippet(since, {"at": "2026-09-24T01:00:00Z", "living": 3, "dead": 0, "books": {},
                                       "repeating_warnings": repeating, "failures": failures,
                                       "research_economy": {"sail_cap": {"capped": False, "last_hour_usd": "1.27", "cap_usd": "2"}}})
        self.assertEqual(out["yield"]["spend_usd"], {"research": "1.3349"})
        self.assertEqual(out["yield"]["by_profile"], {"pro_asap": {"sessions": 4, "candidates": 1}})
        self.assertEqual(out["repeating_warnings"], repeating)
        self.assertEqual(out["failures"], failures)
        self.assertEqual(out["research_economy"]["sail_cap"]["last_hour_usd"], "1.27")
        text = floor_watch.render(out, {}, {"frontier": {"settled_usd": 390.1, "inflight_usd": 4.2, "previous": {"month": "2026-08"}}})
        self.assertIn("## repeating warnings", text)
        self.assertIn("12x since 2026-09-23T23:21:59Z", text)
        self.assertIn("## health failures", text)
        self.assertIn("607 candidates are queued", text)
        self.assertIn("settled_usd", text)

    def test_the_window_starts_where_the_stamp_says_not_at_midnight(self):
        self.ledger.append("ops.alert", {"level": "warning", "text": "early in the day"})
        self.clock.advance(3 * 3600)
        cut = self.ledger.append("ops.started", {}).at
        self.clock.advance(60)
        self.ledger.append("ops.alert", {"level": "warning", "text": "after the cut"})
        since = floor_watch.normalize_since(cut.replace("T", " "))
        out = self.run_snippet(since, {"at": cut, "living": 0, "dead": 0, "books": {}})
        self.assertEqual(out["alerts"], ["1x warning: after the cut"])


class TheGatewayRead(unittest.TestCase):
    def test_the_frontier_fields_deploy_a_added_are_asked_for(self):
        for key in ("settled_usd", "inflight_usd", "previous"):
            self.assertIn(repr(key), floor_watch.GATEWAY_SNIPPET)


ROOT = Path(__file__).resolve().parents[2]


class SeatMarketLine(unittest.TestCase):
    def test_the_watch_shows_the_seats_holding_none_the_clocks_the_refusals_and_the_stopped_sales(self):
        from scripts import floor_watch

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            ledger = Ledger(state / "ledger.sqlite")
            ledger.append("agent.born", {"venue": "kalshi", "founder": "house", "family": "weather-favorites"}, agent="mullins-30")
            ledger.close()
            seats = {"at": "2026-09-24T08:00:00Z", "waiters": {"graduates": 2, "retained": 1, "cards": 0, "strategies": 0},
                     "waiters_by_desk": {"kalshi-weather": 2}, "displaceable": 3, "never_traded_past_grace": 1,
                     "waiting_over_an_hour": True,
                     "seats_holding_none": {"count": 2, "ids": ["mullins-30", "hawkins-9"]},
                     "evidence_clocks": {"at": "2026-09-24T05:37:00Z", "hours": {"kalshi-weather": 31.8, "kalshi-attention": None}},
                     "last_refused_birth": {"retained": {"count": 1, "why": "none could be seated: their desks are full", "at": "t"}}}
            (state / "health.json").write_text(json.dumps({"at": "2026-09-24T08:00:00Z", "release": "r", "seats": seats}))
            refusal = {"why": "HTTP # order qty must be >= minimal qty", "quantity": "0.5", "count": 3, "order": "o-1",
                       "detail": "HTTP 403 order qty must be >= minimal qty of order 1", "at": "t", "epoch": 0}
            (state / "house.json").write_text(json.dumps({"wind_down_refusals": {"haghani-9": {"alpaca-paper": {"crypto:LINKUSD": refusal}}}}))
            run = subprocess.run([sys.executable, "-c", floor_watch.BOX_SNIPPET, "2026-09-24T00:00:00", str(state)],
                                 capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            box = json.loads(run.stdout.strip().splitlines()[-1])
        block = box["blocks"]["seats"]
        self.assertEqual(block["seats_holding_none"], {"count": 2, "ids": ["mullins-30", "hawkins-9"]})
        self.assertEqual(block["evidence_clocks"], {"kalshi-weather": 31.8, "kalshi-attention": None})
        self.assertEqual(block["waiters"]["retained"], 1)
        self.assertIn("none could be seated", block["refused"]["retained"])
        self.assertEqual(len(box["blocks"]["wind_down_stopped"]), 1)
        text = floor_watch.render(box, {}, {})
        self.assertIn("holding none 2 ['mullins-30', 'hawkins-9']", text)
        self.assertIn("kalshi-weather", text)
        self.assertIn("haghani-9 alpaca-paper crypto:LINKUSD refused 3x", text)


class TickStepsLine(unittest.TestCase):
    """C-perf (Sept 24, 2026): the tick took 51-64 s and nothing said which step cost what. The House
    writes `tick_steps` in health.json; the watch prints the last tick's slowest steps, each step's
    slowest in the hour, and each background lane's last run."""

    def test_the_watch_prints_the_slowest_steps(self):
        steps = {"last": {"at": "2026-09-24T08:45:00Z", "total_seconds": 63.1,
                          "steps": {"health": 12.4, "wakes": 41.2, "mark:kalshi": 3.3, "poll:kalshi": 1.1, "cancel_stale": 0.01,
                                    "save_state": 0.2, "due": 0.3, "publish": 4.6}},
                 "ticks_in_hour": 52,
                 "slowest_hour": [{"step": "wakes", "seconds": 47.9, "at": "2026-09-24T08:21:00Z"},
                                  {"step": "health", "seconds": 13.0, "at": "2026-09-24T08:40:00Z"}],
                 "background": {"research": {"key": "research:haghani-9", "seconds": 132.4, "state": "finished", "at": "t"}}}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            Ledger(state / "ledger.sqlite").close()
            (state / "health.json").write_text(json.dumps({"at": "2026-09-24T08:45:00Z", "release": "r", "tick_duration_seconds": 50.7,
                                                           "tick_steps": steps}))
            run = subprocess.run([sys.executable, "-c", floor_watch.BOX_SNIPPET, "2026-09-24T00:00:00", str(state)],
                                 capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            box = json.loads(run.stdout.strip().splitlines()[-1])
        ticks = box["tick_steps"]
        self.assertEqual(ticks["last"], [["wakes", 41.2], ["health", 12.4], ["publish", 4.6], ["mark:kalshi", 3.3], ["poll:kalshi", 1.1],
                                         ["due", 0.3]])
        self.assertEqual(ticks["slowest_hour"][0], ["wakes", 47.9, "2026-09-24T08:21:00Z"])
        text = floor_watch.render(box, {}, {})
        self.assertIn("## tick steps: last 63.1s: wakes 41.2s, health 12.4s, publish 4.6s", text)
        self.assertIn("slowest in the hour (52 ticks): wakes 47.9s at 08:21:00, health 13.0s at 08:40:00", text)
        self.assertIn("background research 132.4s (research:haghani-9, finished)", text)

    def test_a_health_file_without_them_prints_nothing_for_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            Ledger(state / "ledger.sqlite").close()
            (state / "health.json").write_text(json.dumps({"at": "2026-09-24T08:45:00Z", "release": "r"}))
            run = subprocess.run([sys.executable, "-c", floor_watch.BOX_SNIPPET, "2026-09-24T00:00:00", str(state)],
                                 capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            box = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertNotIn("## tick steps", floor_watch.render(box, {}, {}))


if __name__ == "__main__":
    unittest.main()
