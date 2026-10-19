"""Release 1019c (the review of r1/alarms, its majors 1 and 4; the owner's goal of Oct 19, 2026, items 4 and 5): MEASURED
metered spend (league/ops/metered.py), read from the meters themselves at every stall run (the Sail guard's meter, the
gateway's Claude and OpenAI meters) into `<state>/metered.json`, a New York day's figure against that day's cap, and the
stall job's `cap_breach`. Invented readings only."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from league.ops import budget as B
from league.ops import metered as MT
from league.swarm.store import SwarmStore

NY = ZoneInfo("America/New_York")
TUE, WED = dt.date(2026, 10, 20), dt.date(2026, 10, 21)


def et(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).timestamp()


def health(claude=None, month="2026-10", openai=None, previous=None):
    out = {"kill_switch": False}
    if claude is not None:
        out["claude"] = {"settled_usd": f"{claude:.6f}", "spent_usd": f"{claude + 0.5:.6f}", "inflight_usd": "0.500000"}
    if openai is not None:
        out["frontier"] = {"month": month, "settled_usd": f"{openai:.6f}", "spent_usd": f"{openai:.2f}",
                           "previous": previous}
    return out


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = MT.empty()

    def see(self, at, *, sail=None, sail_at=None, claude=None, openai=None, cap=5.0, month="2026-10", previous=None):
        MT.observe(self.ledger, now=at, sail=None if sail is None else (sail_at or at, sail), claude=claude,
                   openai=None if openai is None else MT.openai_reading(health(openai=openai, month=month,
                                                                                previous=previous)),
                   cap=cap)

    def test_a_days_spend_is_each_meter_at_its_end_less_at_its_start_on_the_line_between_readings(self):
        # Readings every half hour from 23:20 ET Monday: Sail's meter rises $0.06 an hour, Claude's $0.10 an hour.
        start = et(dt.date(2026, 10, 19), "23:20")
        for i in range(0, 50):
            at = start + i * 1800
            self.see(at, sail=500.0 + 0.03 * i, claude=40.0 + 0.05 * i)
        figure = MT.day_figure(self.ledger, TUE, et(TUE, "23:50"))
        hours = 23 + 50 / 60                                                       # 00:00 to the last reading, 23:50
        self.assertAlmostEqual(figure["sail"], round(0.06 * hours, 4), places=3)
        self.assertAlmostEqual(figure["claude"], round(0.10 * hours, 4), places=3)
        self.assertEqual(figure["cloudflare"], B.CLOUDFLARE_USD_DAY)
        self.assertAlmostEqual(figure["spent"], figure["sail"] + figure["claude"] + figure["cloudflare"], places=4)
        self.assertFalse(figure["whole"], "the day is not over")
        self.assertTrue(figure["so_far"])
        self.assertEqual(figure["from"], "2026-10-20T04:00:00Z", "measured from 00:00 ET: readings on both sides of it")
        self.assertEqual((figure["cap"], figure["over"]), (5.0, False))

    def test_a_fall_or_a_reset_is_no_spend_and_a_repeated_reading_is_not_counted_twice(self):
        t = et(TUE, "01:00")
        self.see(t, sail=100.0, claude=10.0)
        self.see(t + 1800, sail=100.5, claude=10.2)
        self.see(t + 3600, sail=0.0, claude=3.0)        # both meters reset (a new store, a new gateway object)
        self.see(t + 5400, sail=0.25, claude=3.1, sail_at=t + 5400)
        self.see(t + 7200, sail=0.25, sail_at=t + 5400)  # the guard has not read since: the same reading again
        sail = self.ledger["series"]["sail"]
        self.assertEqual([round(v, 4) for _, v in sail], [0.0, 0.5, 0.5, 0.75])
        self.assertEqual([round(v, 4) for _, v in self.ledger["series"]["claude"]], [0.0, 0.2, 0.2, 0.3])

    def test_openai_carries_on_across_a_month_from_the_old_months_total(self):
        t = et(dt.date(2026, 10, 31), "19:00")
        self.see(t, openai=2.0, month="2026-10")
        self.see(t + 3 * 3600, openai=0.4, month="2026-11", previous={"month": "2026-10", "settled_usd": "2.300000"})
        self.assertEqual([round(v, 4) for _, v in self.ledger["series"]["openai"]], [0.0, 0.7], "0.3 then 0.4")

    def test_the_days_cap_is_the_lowest_it_was_and_no_budget_is_the_no_profit_cap(self):
        t = et(TUE, "01:00")
        self.see(t, claude=1.0, cap=9.5)
        self.see(t + 1800, claude=1.1, cap=7.0)
        self.see(t + 3600, claude=1.2, cap=12.0)
        self.assertEqual(self.ledger["caps"][TUE.isoformat()], 7.0)
        self.see(t + 5400, claude=1.3, cap=None)   # budget.json not usable: FAIL CLOSED at the rule's lowest cap
        self.assertEqual(self.ledger["caps"][TUE.isoformat()], B.BASE_USD_DAY)

    def test_over_the_cap_is_what_the_readings_show_at_the_least(self):
        t = et(TUE, "00:10")
        self.see(t, claude=100.0, cap=5.0)
        self.see(et(TUE, "14:00"), claude=105.2, cap=5.0)   # $5.20 of Claude and no Sail reading at all
        figure = MT.day_figure(self.ledger, TUE, et(TUE, "14:05"))
        self.assertIsNone(figure["spent"], "Sail had no reading: the day's whole spend is not known")
        self.assertAlmostEqual(figure["at_least"], 5.2 + B.CLOUDFLARE_USD_DAY, places=4)
        self.assertTrue(figure["over"], "over the cap on what is known at the least")
        check = MT.cap_check(self.ledger, et(TUE, "14:05"))
        self.assertTrue(check["stalled"])
        self.assertIn("Metered compute on 2026-10-20 is $5.36 so far, over that day's cap of $5.00", check["what"])
        self.assertIn("at least: sail had no reading", check["what"])
        self.assertEqual((check["numbers"]["cap_usd"], check["numbers"]["so_far"], check["owner_step"]), (5.0, True, None))

    def test_yesterdays_whole_day_over_its_cap_stands_the_next_day(self):
        self.see(et(TUE, "00:00") - 600, sail=10.0, claude=10.0, cap=5.0)
        self.see(et(TUE, "12:00"), sail=12.0, claude=12.0, cap=5.0)
        self.see(et(WED, "00:20"), sail=12.1, claude=13.5, cap=5.0)   # Tuesday: 2.0 + 0.1 of the last hour, 3.5 of Claude
        MT.finish_days(self.ledger, et(WED, "00:20"))
        kept = self.ledger["days"][TUE.isoformat()]
        self.assertTrue(kept["final"])
        self.assertTrue(kept["whole"])
        self.assertTrue(kept["over"])
        check = MT.cap_check(self.ledger, et(WED, "09:00"))
        self.assertTrue(check["stalled"])
        self.assertIn("Metered compute on 2026-10-20 was $", check["what"])
        self.assertEqual(check["numbers"]["so_far"], False)
        # Under the cap both days: nothing stands.
        quiet = MT.empty()
        MT.observe(quiet, now=et(TUE, "01:00"), sail=(et(TUE, "01:00"), 1.0), claude=1.0, openai=None, cap=5.0)
        MT.observe(quiet, now=et(TUE, "13:00"), sail=(et(TUE, "13:00"), 2.0), claude=2.0, openai=None, cap=5.0)
        self.assertFalse(MT.cap_check(quiet, et(TUE, "13:00"))["stalled"])
        self.assertIn("under the day's cap of $5.00", MT.cap_check(quiet, et(TUE, "13:00"))["what"])
        self.assertFalse(MT.cap_check(MT.empty(), et(TUE, "13:00"))["judged"], "no reading yet: not judged")

    def test_update_reads_the_guards_meter_and_the_gateway_and_keeps_its_file_private(self):
        store = SwarmStore(self.root, clock=lambda: et(TUE, "10:00"))
        store.put("guard", {"last": {"balance": 300.0, "metered_spent": 812.5, "at": et(TUE, "10:01")},
                            "last_good": {"balance": 300.0, "at": et(TUE, "10:00")}})
        store.close()
        budget = {"schema": B.SCHEMA, "cap_usd_day": 6.5}
        ledger = MT.update(self.root, et(TUE, "10:20"), health=health(claude=55.0), budget=budget)
        self.assertEqual(ledger["series"]["sail"], [[et(TUE, "10:00"), 0.0]], "at the guard's own good reading")
        self.assertEqual(ledger["series"]["claude"], [[et(TUE, "10:20"), 0.0]])
        self.assertEqual(ledger["caps"][TUE.isoformat()], 6.5)
        on_disk = json.loads((self.root / MT.FILE).read_text())
        self.assertEqual(on_disk["raw"]["sail"], 812.5)
        self.assertEqual((self.root / MT.FILE).stat().st_mode & 0o777, 0o600)
        again = MT.update(self.root, et(TUE, "10:50"), health=None, budget=None)  # the gateway unread this run
        self.assertEqual(len(again["series"]["claude"]), 1)
        self.assertEqual(again["caps"][TUE.isoformat()], B.BASE_USD_DAY, "no usable budget.json: the no-profit cap")

    def test_since_adds_the_kept_days_and_says_what_it_cannot(self):
        t0 = et(dt.date(2026, 10, 19), "23:50")
        for i in range(0, 120):
            at = t0 + i * 1800
            self.see(at, sail=float(i) * 0.05, claude=float(i) * 0.05)
        now = t0 + 119 * 1800
        MT.finish_days(self.ledger, now)
        span = MT.since(self.ledger, TUE, now)
        self.assertEqual(span["days"], 3)
        self.assertIsNotNone(span["usd"])
        missing = MT.since(self.ledger, dt.date(2026, 10, 15), now)
        self.assertIsNone(missing["usd"])
        self.assertEqual(missing["missing"][0], "2026-10-15")


if __name__ == "__main__":
    unittest.main()
