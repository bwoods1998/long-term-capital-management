"""The watch (`scripts/floor_watch.py`) reads what it says it reads.

Sept 24, 2026 (the close-the-gaps run, workstream B and L3): `--since` was compared as text with
the ledger's `at`, an ISO stamp with `T`; sqlite's `datetime('now', '-1 hour')` yields a space
instead, and since a space sorts before `T` that admitted the whole day. The newest hourly yield
row was looked up as `"what": "yield"` with a space, which the ledger's canonical JSON never
writes, so the watch never printed a yield row. These tests run the box snippet itself against a
throwaway state directory.
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


if __name__ == "__main__":
    unittest.main()
