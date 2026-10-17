"""THE DETECTOR (HISTORY-PLAN.md section 5.3; league/deep/blind.py): every calendar reader is flagged by the scan AND by
the behavioural test; a getattr-string reader is caught by behaviour on its own; calendar-blind programs pass both.

Synthetic stores only (league/equity/synth.py), run in the in-process decider."""

from __future__ import annotations

import unittest
from pathlib import Path

from league.deep import blind, config
from league.equity.runner import Isolated
from league.live.decider import InlineDecider
from league.tests import deep_fakes as F

BASE = F.blind_program(("SPY", "QQQ"), history=30)
GUARD = "    held = {p"
READERS = {
    "weekday": "    if ctx.weekday != 0:\n        return out\n",
    "session_of_month": "    if ctx.session_of_month > 3:\n        return out\n",
    "sessions_to_month_end": "    if ctx.sessions_to_month_end > 2:\n        return out\n",
    "events": "    if any(ctx.events.values()):\n        return out\n",
    "events_next": "    if any(ctx.events_next.values()):\n        return out\n",
}


def reader(insert: str) -> str:
    return BASE.replace(GUARD, insert + GUARD)


class Detector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile

        cls._tmp = tempfile.TemporaryDirectory(prefix="deep-blind-")
        cls.root = Path(cls._tmp.name)
        cls.decider = InlineDecider()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def behaves(self, code: str) -> dict:
        def run(store_root, start, end):
            return Isolated(self.decider, store_root).train(code, {}, name="b", start=start, end=end, k=1.0).result

        return blind.behaviour(code, {}, run, symbols=("SPY", "QQQ"), history=30, parent=self.root)

    def test_the_fields_are_prereg_hs_five(self):
        self.assertEqual(set(config.CALENDAR_FIELDS), {"weekday", "session_of_month", "sessions_to_month_end",
                                                       "events", "events_next"})

    def test_every_calendar_reader_is_flagged_by_the_scan_and_by_behaviour(self):
        for field, insert in READERS.items():
            code = reader(insert)
            with self.subTest(field=field):
                self.assertTrue(any(field in hit for hit in blind.scan(code)), blind.scan(code))
                seen = self.behaves(code)
                self.assertFalse(seen["blind"], field)
                self.assertIn("differ", seen["why"])

    def test_a_getattr_string_reader_is_caught_by_behaviour(self):
        code = reader('    if getattr(ctx, "weekday") != 0:\n        return out\n')
        self.assertFalse(self.behaves(code)["blind"], "behaviour alone catches it")
        self.assertTrue(blind.scan(code), "and the scan names the string too")
        check = blind.check(code, {}, lambda *a: {}, symbols=("SPY",), history=1)
        self.assertEqual((check["blind"], check["behaviour"]), (False, None), "the scan refuses first, no run made")

    def test_calendar_blind_programs_pass_both(self):
        for code in (BASE, F.blind_program(("SPY", "QQQ"), history=30, entry_at="close", exit_at="close")):
            self.assertEqual(blind.scan(code), [])
            self.assertEqual(self.behaves(code), {"blind": True, "why": None})

    def test_the_scan_reads_any_object_and_refuses_what_does_not_parse(self):
        self.assertTrue(blind.scan("def decide(c):\n    return c.events_next\n"))
        self.assertEqual(blind.scan("def decide(c):\n    return c.events_count\n"), [])
        self.assertEqual(blind.scan("def decide(:"), ["the program does not parse"])

    def test_the_behavioural_stores_are_removed(self):
        self.behaves(BASE)
        self.assertEqual([p for p in self.root.iterdir() if p.name.startswith("deep-blind-")], [])

    def test_the_two_labelings_differ_in_their_calendar(self):
        from league.equity import store as estore

        first = [d for d, _ in estore.nyse_sessions(config.BEHAVIOUR_SECOND, config.BEHAVIOUR_SECOND)]
        self.assertEqual(first, [config.BEHAVIOUR_SECOND])
        self.assertNotEqual(config.BEHAVIOUR_SECOND.weekday(), 0)


if __name__ == "__main__":
    unittest.main()
