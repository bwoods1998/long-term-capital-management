"""mcentee-34's corrected child reads the session in New York time (Sept 23, 2026).

The parent hard-coded 14:35-20:55 UTC, which is 9:35-15:55 New York time only in winter. Under
daylight time it sat idle from the 13:30Z open until 14:35Z and read 20:00-20:55Z, after the close,
as the session."""
import json
import unittest
from pathlib import Path

from league import strategies
from league.safety import check_code

HERE = Path(strategies.__file__).resolve().parent
FILE = HERE / "mcentee_34_session_hours.py"
#: The parent's defective function, verbatim: what the child corrects.
PARENT = '''
def date_part(text):
    s = str(text or "")
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else ""


def weekday_date(d):
    try:
        y, m, day = [int(x) for x in d.split("-")]
        if m < 3:
            y -= 1
            m += 12
        k, j = y % 100, y // 100
        w = (day + (13 * (m + 1)) // 5 + k + k // 4 + j // 4 + 5 * j) % 7
        return w not in (0, 1)
    except Exception:
        return True


def regular_session(now):
    s = str(now or "")
    if not weekday_date(date_part(s)):
        return False
    try:
        minute = int(s[11:13]) * 60 + int(s[14:16])
        return 14 * 60 + 35 <= minute <= 20 * 60 + 55
    except Exception:
        return False
'''


def module(code: str) -> dict:
    space: dict = {}
    exec(compile(code, "strategy", "exec"), space)  # noqa: S102 - a vetted strategy file, as the box runs it
    return space


class SessionHours(unittest.TestCase):
    def setUp(self):
        self.code = FILE.read_text(encoding="utf-8")
        self.child = module(self.code)

    def test_the_session_follows_new_york_daylight_time(self):
        session = self.child["regular_session"]
        # Wednesday Sept 23, 2026 (EDT, UTC-4): the session is 13:30-20:00Z.
        self.assertFalse(session("2026-09-23T13:34:00Z"))
        self.assertTrue(session("2026-09-23T13:35:00Z"))
        self.assertTrue(session("2026-09-23T14:05:00.123Z"))
        self.assertTrue(session("2026-09-23T19:55:00Z"))
        self.assertFalse(session("2026-09-23T19:56:00Z"))
        self.assertFalse(session("2026-09-23T20:30:00Z"))  # after the close
        # Wednesday Jan 13, 2027 (EST, UTC-5): 14:30-21:00Z, the window the parent hard-coded.
        self.assertFalse(session("2027-01-13T13:40:00Z"))
        self.assertTrue(session("2027-01-13T14:35:00Z"))
        self.assertTrue(session("2027-01-13T20:55:00Z"))
        self.assertFalse(session("2027-01-13T20:56:00Z"))
        # The days the clocks change: Sunday Nov 1, 2026 and Monday Nov 2.
        self.assertTrue(session("2026-11-02T14:35:00Z"))
        self.assertFalse(session("2026-11-02T13:40:00Z"))
        # Weekends in New York, even when UTC has already moved to Saturday.
        self.assertFalse(session("2026-09-26T15:00:00Z"))
        self.assertTrue(session("2026-09-25T19:50:00Z"))
        self.assertFalse(session("not a time"))
        self.assertFalse(session(None))

    def test_the_parent_had_the_defect_the_child_corrects(self):
        parent = module(PARENT)["regular_session"]
        self.assertFalse(parent("2026-09-23T13:40:00Z"))  # 9:40 in New York: the market is open
        self.assertTrue(parent("2026-09-23T20:30:00Z"))   # 16:30 in New York: the market is shut
        self.assertTrue(self.child["regular_session"]("2026-09-23T13:40:00Z"))
        self.assertFalse(self.child["regular_session"]("2026-09-23T20:30:00Z"))

    def test_it_is_a_described_repair_of_mcentee_34_that_keeps_the_parents_rules(self):
        check_code(self.code)
        row = json.loads((HERE / "mcentee_34_session_hours.json").read_text(encoding="utf-8"))
        self.assertEqual(row["repair"], {"key": "strategy_defect:mcentee-34:76c339a411e9", "parent": "mcentee-34"})
        self.assertEqual(row["family"], "megacaps-reversion")
        self.assertIn("mcentee_34_session_hours", [r["name"] for r in strategies.registry()])
        self.assertEqual(self.child["NEEDS"]["symbols"], ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO"])
        self.assertEqual(self.child["PARAMS"], {"exit_mean_days": 5, "max_days": 5, "notional_usd": 25.0, "max_positions": 4})

    def test_outside_the_session_it_places_nothing(self):
        out = self.child["decide"]({"now": "2026-09-23T20:30:00Z", "params": {}, "positions": [], "open_orders": [],
                                    "cash": 200.0, "limits": {"max_order_usd": 75.0, "max_position_usd": 100.0}, "bars": {}})
        self.assertEqual(out["intents"], [])
