"""Release 1019c (the review of r1/alarms, its majors 1 and 4; the review of r2/alarms, its majors 1 and 2; the owner's
goal of Oct 19, 2026, items 4 and 5): MEASURED metered spend (league/ops/metered.py), read from the meters themselves at
every stall run (the Sail guard's meter, the gateway's Claude and OpenAI meters) into `<state>/metered.json`, a UTC day's
figure (the day budget rule 3 holds every line on) against the cap the rule set for that day, the stall job's
`cap_breach`, THE CAP BREACH HOLD (`<state>/cap-hold.json`) and costs to date over the days the ledger covers. Invented
readings only."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from league.ops import budget as B
from league.ops import metered as MT
from league.swarm.store import SwarmStore
from league.tests.v2_cost import on_v2_cost

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
MON, TUE, WED, THU = dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21), dt.date(2026, 10, 22)


def et(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).timestamp()


def utc(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=UTC).timestamp()


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

    def see(self, at, *, sail=None, sail_at=None, claude=None, openai=None, cap=5.0, cap_at=None, month="2026-10",
            previous=None):
        MT.observe(self.ledger, now=at, sail=None if sail is None else (sail_at or at, sail), claude=claude,
                   openai=None if openai is None else MT.openai_reading(health(openai=openai, month=month,
                                                                                previous=previous)),
                   cap=cap, cap_at=cap_at)

    def test_a_days_spend_is_each_meter_at_its_end_less_at_its_start_on_the_line_between_readings(self):
        # Readings every half hour from 23:20 UTC Monday: Sail's meter rises $0.06 an hour, Claude's $0.10 an hour.
        start = utc(MON, "23:20")
        for i in range(0, 50):
            at = start + i * 1800
            self.see(at, sail=500.0 + 0.03 * i, claude=40.0 + 0.05 * i)
        figure = MT.day_figure(self.ledger, TUE, utc(TUE, "23:50"))
        hours = 23 + 50 / 60                                                       # 00:00 to the last reading, 23:50
        self.assertAlmostEqual(figure["sail"], round(0.06 * hours, 4), places=3)
        self.assertAlmostEqual(figure["claude"], round(0.10 * hours, 4), places=3)
        self.assertEqual(figure["cloudflare"], B.CLOUDFLARE_USD_DAY)
        self.assertAlmostEqual(figure["spent"], figure["sail"] + figure["claude"] + figure["cloudflare"], places=4)
        self.assertFalse(figure["whole"], "the day is not over")
        self.assertTrue(figure["so_far"])
        self.assertEqual(figure["from"], "2026-10-20T00:00:00Z", "measured from 00:00 UTC: readings on both sides of it")
        self.assertEqual((figure["cap"], figure["over"]), (5.0, False))
        # FOR CERTAIN: each meter's rise between its first and last reading of the day (00:20 to 23:50), never the share
        # of the rise across 00:00 UTC that the line between 23:50 Monday and 00:20 Tuesday gives Tuesday.
        self.assertAlmostEqual(figure["certain"], round(0.06 * 23.5 + 0.10 * 23.5 + B.CLOUDFLARE_USD_DAY, 4), places=3)
        self.assertLess(figure["certain"], figure["spent"])

    def test_the_day_is_the_utc_day_the_lines_are_held_on(self):
        """00:00 UTC, never New York's midnight: the Sail guard's and the router's `now - now % 86400`, the lane's
        `_spend_today` and budget.json's day's figure."""
        self.assertEqual(MT.day_bounds(TUE), (utc(TUE, "00:00"), utc(WED, "00:00")))
        self.assertEqual(MT.utc_day(et(MON, "20:30")), TUE, "20:30 ET Monday is Tuesday's UTC day")
        self.assertEqual(MT.utc_day(et(TUE, "19:59")), TUE)
        for at in (et(MON, "20:00"), et(TUE, "00:00"), et(TUE, "19:59")):
            self.assertEqual(at - at % 86400, MT.day_bounds(MT.utc_day(at))[0])
        # Spend after 20:00 ET Monday is Tuesday's (UTC): it counts against Tuesday's cap, never Monday's.
        self.see(et(MON, "19:00"), claude=10.0)
        self.see(et(MON, "19:50"), claude=10.0)
        self.see(et(MON, "20:10"), claude=10.0)
        self.see(et(MON, "20:40"), claude=14.0)
        self.see(et(MON, "23:00"), claude=14.0)
        self.assertEqual(MT.day_figure(self.ledger, TUE, et(MON, "23:00"))["claude"], 4.0)
        self.assertEqual(MT.day_figure(self.ledger, MON, et(MON, "23:00"))["claude"], 0.0)

    def test_a_fall_or_a_reset_is_no_spend_and_a_repeated_reading_is_not_counted_twice(self):
        t = utc(TUE, "05:00")
        self.see(t, sail=100.0, claude=10.0)
        self.see(t + 1800, sail=100.5, claude=10.2)
        self.see(t + 3600, sail=0.0, claude=3.0)        # both meters reset (a new store, a new gateway object)
        self.see(t + 5400, sail=0.25, claude=3.1, sail_at=t + 5400)
        self.see(t + 7200, sail=0.25, sail_at=t + 5400)  # the guard has not read since: the same reading again
        sail = self.ledger["series"]["sail"]
        self.assertEqual([round(v, 4) for _, v in sail], [0.0, 0.5, 0.5, 0.75])
        self.assertEqual([round(v, 4) for _, v in self.ledger["series"]["claude"]], [0.0, 0.2, 0.2, 0.3])
        self.assertEqual(self.ledger["began"], {"sail": t, "claude": t, "openai": None}, "when each meter was first read")

    def test_openai_carries_on_across_a_month_from_the_old_months_total(self):
        t = utc(dt.date(2026, 10, 31), "19:00")
        self.see(t, openai=2.0, month="2026-10")
        self.see(t + 3 * 3600, openai=0.4, month="2026-11", previous={"month": "2026-10", "settled_usd": "2.300000"})
        self.assertEqual([round(v, 4) for _, v in self.ledger["series"]["openai"]], [0.0, 0.7], "0.3 then 0.4")

    def test_the_days_cap_is_the_highest_the_rule_set_for_it_and_none_is_the_no_profit_cap(self):
        """THE CAP THE RULE SET FOR THE DAY (the review of r2/alarms, its major 1): the rule sets a day's lines at its
        first run and only raises them within it, so the day is judged against the highest cap its budget.json gave,
        never the lowest one seen."""
        t = utc(TUE, "01:00")
        self.see(t, claude=1.0, cap=9.5)
        self.see(t + 1800, claude=1.1, cap=7.0)
        self.see(t + 3600, claude=1.2, cap=12.0)
        self.assertEqual(self.ledger["caps"][TUE.isoformat()], 12.0)
        self.see(t + 5400, claude=1.3, cap=None)   # budget.json not usable this run: the holders run on the floor's lines
        self.assertEqual(self.ledger["caps"][TUE.isoformat()], 12.0, "an unusable read lowers nothing")
        self.see(t + 7200, claude=1.4, cap=900.0)
        self.assertEqual(self.ledger["caps"][TUE.isoformat()], B.CEILING_USD_DAY, "never above the owner's ceiling")
        self.assertEqual(MT.day_cap(self.ledger, WED), B.BASE_USD_DAY, "no budget.json read for the day: FAIL CLOSED")
        self.assertEqual(MT.day_figure(self.ledger, WED, utc(WED, "01:00"))["cap"], B.BASE_USD_DAY)
        # A budget.json the rule computed before 00:00 UTC and still in force after it counts for both days; one dated
        # ahead of the run counts for neither.
        other = MT.empty()
        MT.observe(other, now=utc(WED, "00:20"), sail=None, claude=2.0, openai=None, cap=8.0, cap_at=utc(TUE, "23:55"))
        self.assertEqual(other["caps"], {TUE.isoformat(): 8.0, WED.isoformat(): 8.0})
        MT.observe(other, now=utc(WED, "00:50"), sail=None, claude=2.1, openai=None, cap=20.0, cap_at=utc(WED, "03:00"))
        self.assertEqual(other["caps"], {TUE.isoformat(): 8.0, WED.isoformat(): 8.0})

    @on_v2_cost
    def test_a_close_that_lifts_the_cap_and_research_mid_day_is_no_breach(self):
        """(On budget rule 3's figures, league/tests/v2_cost.py.) The review's case: the day ran at the $5 cap's lines until a profitable close lifted the cap to $12 and the
        top-up raise lifted research to the new lines; the day then spent $9 in all, inside its raised lines. Judged
        against the lowest cap ($5), that read as a breach; it is under the day's $12."""
        self.see(utc(TUE, "00:20"), sail=10.0, claude=10.0, cap=5.0)
        self.see(utc(TUE, "19:50"), sail=11.5, claude=12.5, cap=5.0)     # $4 by the close: under the $5
        self.see(utc(TUE, "20:50"), sail=11.6, claude=12.6, cap=12.0)    # the close's budget run: the cap $12
        self.see(utc(TUE, "23:50"), sail=14.0, claude=15.0, cap=12.0)    # the raised lines spent
        figure = MT.day_figure(self.ledger, TUE, utc(TUE, "23:50"))
        self.assertGreater(figure["at_least"], B.BASE_USD_DAY)
        self.assertEqual((figure["cap"], figure["over"]), (12.0, False))
        self.assertFalse(MT.cap_check(self.ledger, utc(TUE, "23:50"))["stalled"])

    def test_goal_v3s_base_is_the_cap_of_a_day_no_budget_json_was_read_for(self):
        """Goal V3 (budget rule 4): a day the stall job read no usable budget.json for is judged at the rule's no-profit
        $10 (FAIL CLOSED at the base, never above it), and no cap is read above the owner's $50; a day the rule set at
        rule 3's $5 keeps its $5 (metered.json keeps each day's cap as the rule in force then set it)."""
        self.assertEqual((B.BASE_USD_DAY, B.CEILING_USD_DAY), (10.0, 50.0))
        self.assertEqual(MT.day_cap(self.ledger, WED), 10.0)
        t = utc(TUE, "01:00")
        self.see(t, claude=1.0, cap=5.0)                 # rule 3's file, read before the deploy
        self.see(t + 3600, claude=7.5, cap=None)         # the deploy: another rule's file is no file, nothing lowered
        self.assertEqual(MT.day_cap(self.ledger, TUE), 5.0)
        self.see(t + 7200, claude=7.6, cap=10.0)         # rule 4's first run of the day
        self.assertEqual(MT.day_cap(self.ledger, TUE), 10.0)
        self.see(t + 9000, claude=7.7, cap=75.0)
        self.assertEqual(MT.day_cap(self.ledger, TUE), 50.0, "never above the owner's $50")
        self.see(utc(TUE, "23:50"), sail=0.0, claude=9.0, cap=50.0)
        figure = MT.day_figure(self.ledger, TUE, utc(TUE, "23:50"))
        self.assertEqual((figure["cap"], figure["over"]), (50.0, False))

    def test_over_the_cap_is_what_the_readings_show_at_the_least(self):
        t = utc(TUE, "00:10")
        self.see(t, claude=100.0, cap=5.0)
        self.see(utc(TUE, "14:00"), claude=105.2, cap=5.0)   # $5.20 of Claude and no Sail reading at all
        figure = MT.day_figure(self.ledger, TUE, utc(TUE, "14:05"))
        self.assertIsNone(figure["spent"], "Sail had no reading: the day's whole spend is not known")
        self.assertAlmostEqual(figure["at_least"], 5.2 + B.CLOUDFLARE_USD_DAY, places=4)
        self.assertTrue(figure["over"], "over the cap on what is known at the least")
        self.assertTrue(figure["certainly_over"], "both readings inside the day: certain")
        check = MT.cap_check(self.ledger, utc(TUE, "14:05"))
        self.assertTrue(check["stalled"])
        self.assertIn("Metered compute on the UTC day 2026-10-20 is $5.36 so far, over that day's cap of $5.00",
                      check["what"])
        self.assertIn("at least: sail had no reading", check["what"])
        self.assertEqual((check["numbers"]["cap_usd"], check["numbers"]["so_far"], check["owner_step"]), (5.0, True, None))
        self.assertEqual((check["numbers"]["sail_read_at"], check["numbers"]["claude_read_at"]),
                         (None, "2026-10-20T14:00:00Z"), "when each meter was last read: a stopped one is plain")
        self.assertIs(check["numbers"]["held"], False, "no hold handed in: none said")

    def test_yesterdays_whole_day_over_its_cap_stands_the_next_day(self):
        self.see(utc(MON, "23:50"), sail=10.0, claude=10.0, cap=5.0)
        self.see(utc(TUE, "12:00"), sail=12.0, claude=12.0, cap=5.0)
        self.see(utc(WED, "00:20"), sail=12.1, claude=13.5, cap=5.0)   # Tuesday: 2.0 + 0.1 of the last hour, 3.5 of Claude
        MT.finish_days(self.ledger, utc(WED, "00:20"))
        kept = self.ledger["days"][TUE.isoformat()]
        self.assertTrue(kept["final"])
        self.assertTrue(kept["whole"])
        self.assertTrue(kept["over"])
        check = MT.cap_check(self.ledger, utc(WED, "09:00"))
        self.assertTrue(check["stalled"])
        self.assertIn("Metered compute on the UTC day 2026-10-20 was $", check["what"])
        self.assertEqual(check["numbers"]["so_far"], False)
        # Under the cap both days: nothing stands.
        quiet = MT.empty()
        MT.observe(quiet, now=utc(TUE, "01:00"), sail=(utc(TUE, "01:00"), 1.0), claude=1.0, openai=None, cap=5.0)
        MT.observe(quiet, now=utc(TUE, "13:00"), sail=(utc(TUE, "13:00"), 2.0), claude=2.0, openai=None, cap=5.0)
        self.assertFalse(MT.cap_check(quiet, utc(TUE, "13:00"))["stalled"])
        self.assertIn("under the day's cap of $5.00", MT.cap_check(quiet, utc(TUE, "13:00"))["what"])
        self.assertFalse(MT.cap_check(MT.empty(), utc(TUE, "13:00"))["judged"], "no reading yet: not judged")

    def test_a_meter_that_stopped_reading_never_passes_for_under_the_cap(self):
        """A missed meter fails closed: six hours with no reading of Sail's or Claude's meter (the ledger at least that
        old) is no judgement of the cap, and the cause stands for it."""
        self.see(utc(TUE, "01:00"), sail=1.0, claude=1.0)
        self.see(utc(TUE, "03:00"), claude=1.2)                     # the Sail guard has stopped reading
        early = MT.cap_check(self.ledger, utc(TUE, "05:00"))
        self.assertEqual((early["stalled"], early["numbers"]["blind"]), (False, "none"), "4 hours: not yet")
        self.see(utc(TUE, "07:30"), claude=1.3)
        blind = MT.cap_check(self.ledger, utc(TUE, "07:30"))
        self.assertEqual((blind["stalled"], blind["numbers"]["blind"]), (True, "sail"))
        self.assertIn("The cap cannot be judged: sail's meter has had no reading for 6 hours or more", blind["what"])

    def test_update_reads_the_guards_meter_and_the_gateway_and_keeps_its_file_private(self):
        store = SwarmStore(self.root, clock=lambda: utc(TUE, "10:00"))
        store.put("guard", {"last": {"balance": 300.0, "metered_spent": 812.5, "at": utc(TUE, "10:01")},
                            "last_good": {"balance": 300.0, "at": utc(TUE, "10:00")}})
        store.close()
        budget = {"schema": B.SCHEMA, "cap_usd_day": 6.5, "at": utc(TUE, "09:30")}
        ledger = MT.update(self.root, utc(TUE, "10:20"), health=health(claude=55.0), budget=budget)
        self.assertEqual(ledger["series"]["sail"], [[utc(TUE, "10:00"), 0.0]], "at the guard's own good reading")
        self.assertEqual(ledger["series"]["claude"], [[utc(TUE, "10:20"), 0.0]])
        self.assertEqual(ledger["caps"][TUE.isoformat()], 6.5)
        self.assertIsNone(ledger["hold"])
        on_disk = json.loads((self.root / MT.FILE).read_text())
        self.assertEqual((on_disk["raw"]["sail"], on_disk["schema"]), (812.5, MT.SCHEMA))
        self.assertNotIn("hold", on_disk, "the hold is its own file")
        self.assertEqual((self.root / MT.FILE).stat().st_mode & 0o777, 0o600)
        again = MT.update(self.root, utc(TUE, "10:50"), health=None, budget=None)  # the gateway unread this run
        self.assertEqual(len(again["series"]["claude"]), 1)
        self.assertEqual(again["caps"][TUE.isoformat()], 6.5, "no usable budget.json this run: the day keeps its cap")
        # A ledger of another schema (release r1's New York days) is none.
        (self.root / MT.FILE).write_text(json.dumps({**on_disk, "schema": 1}))
        self.assertEqual(MT.load(self.root), MT.empty())


class CostsToDate(unittest.TestCase):
    """THE COSTS TO DATE (the review of r2/alarms, its major 2): measured over the days the ledger covers, from the later
    of the first fill's day and the first day both meters were read, so a ledger begun after the first fill never leaves
    the to-date figure unknown for good, and says what it covers."""

    def readings(self, start: float, n: int, every: float = 1800.0) -> tuple[dict, float]:
        ledger = MT.empty()
        for i in range(n):
            at = start + i * every
            MT.observe(ledger, now=at, sail=(at, 100.0 + 0.05 * i), claude=50.0 + 0.05 * i, openai=None, cap=5.0)
            MT.finish_days(ledger, at)
        return ledger, start + (n - 1) * every

    def test_since_adds_the_kept_days_and_says_what_it_cannot(self):
        ledger, now = self.readings(utc(MON, "23:50"), 120)
        span = MT.since(ledger, TUE, now)
        self.assertEqual((span["days"], span["from"], span["first"]), (3, "2026-10-20", "2026-10-20"))
        self.assertIsNotNone(span["usd"])
        self.assertEqual((span["partial"], span["missing"]), (False, []), "every day before today whole")
        earlier = MT.since(ledger, dt.date(2026, 10, 15), now)
        self.assertEqual((earlier["from"], earlier["partial"]), ("2026-10-19", True),
                         "the first fill before the ledger: measured from the ledger's first day, said partial")
        self.assertIsNotNone(earlier["usd"])
        self.assertGreaterEqual(earlier["usd"], span["usd"])
        nothing = MT.since(MT.empty(), TUE, now)
        self.assertEqual((nothing["usd"], nothing["from"], nothing["partial"]), (None, None, True))

    def test_a_ledger_that_starts_a_day_after_the_first_fill(self):
        """The review's case: real fills from Tuesday (release 1019b), metered.json from Wednesday 05:00 UTC (release
        1019c, deployed later). Thursday's costs to date are Wednesday's and Thursday's so far, said to be measured since
        Wednesday and partly, never unknown for good."""
        ledger, now = self.readings(utc(WED, "05:00"), 70)   # to 15:30 UTC Thursday
        span = MT.since(ledger, TUE, now)
        self.assertEqual((span["from"], span["first"], span["partial"]), ("2026-10-21", "2026-10-20", True))
        self.assertEqual(span["days"], 2)
        self.assertEqual(span["missing"], [], "no day inside the ledger misses a meter")
        wed = ledger["days"][WED.isoformat()]
        thu = MT.day_figure(ledger, THU, now)
        self.assertAlmostEqual(span["usd"], round(wed["spent"] + thu["spent"], 4), places=4)
        self.assertFalse(wed["whole"], "Wednesday was measured from 05:00 UTC")

    def test_a_ledger_that_starts_mid_day_on_the_first_fills_day(self):
        """Release 1019c on time (deployed 06:00 UTC on the first fill's day): the first day is measured from the
        ledger's first reading and the span says partial."""
        ledger, now = self.readings(utc(TUE, "06:00"), 40)
        span = MT.since(ledger, TUE, now)
        self.assertEqual((span["from"], span["partial"], span["days"]), ("2026-10-20", True, 2))
        whole_days = MT.since(ledger, WED, now)
        self.assertEqual((whole_days["from"], whole_days["partial"]), ("2026-10-21", False))

    def test_a_day_a_meter_missed_counts_what_the_others_show_and_is_named(self):
        ledger = MT.empty()
        MT.observe(ledger, now=utc(TUE, "00:10"), sail=(utc(TUE, "00:10"), 10.0), claude=10.0, openai=None, cap=5.0)
        MT.observe(ledger, now=utc(TUE, "23:50"), sail=(utc(TUE, "23:50"), 11.0), claude=11.0, openai=None, cap=5.0)
        for hhmm in ("00:20", "12:00", "23:50"):   # Wednesday: the Sail guard stopped reading; Claude goes on
            MT.observe(ledger, now=utc(WED, hhmm), sail=None, claude=11.0 + int(hhmm[:2]) / 10, openai=None, cap=5.0)
        MT.finish_days(ledger, utc(WED, "23:50"))
        span = MT.since(ledger, TUE, utc(WED, "23:50"))
        self.assertEqual((span["missing"], span["missing_n"], span["partial"]), (["2026-10-21"], 1, True))
        wed = MT.day_figure(ledger, WED, utc(WED, "23:50"))
        self.assertIsNone(wed["spent"])
        tue = ledger["days"][TUE.isoformat()]
        self.assertAlmostEqual(span["usd"], round(tue["spent"] + wed["at_least"], 4), places=4)


class TheHold(unittest.TestCase):
    """THE CAP BREACH HOLD (the review of r2/alarms, its major 1): written while today is over its cap for certain, read
    by every line the budget holds, lapsing with its UTC day, lifted when the day's cap rises above what it spent."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_at(self, at: float, *, claude: float, cap: float = 5.0, budget_at: float | None = None) -> dict:
        budget = {"schema": B.SCHEMA, "cap_usd_day": cap, "at": at - 600 if budget_at is None else budget_at}
        return MT.update(self.root, at, health=health(claude=claude), budget=budget)

    def test_written_over_the_cap_read_by_the_budget_and_lapsing_with_its_day(self):
        self.run_at(utc(TUE, "00:20"), claude=10.0)
        self.assertIsNone(self.run_at(utc(TUE, "06:20"), claude=12.0)["hold"], "$2.16: under the $5")
        hold = self.run_at(utc(TUE, "09:20"), claude=16.0)["hold"]
        self.assertEqual((hold["day"], hold["since"], hold["cap_usd"]), ("2026-10-20", "2026-10-20T09:20:00Z", 5.0))
        self.assertAlmostEqual(hold["spent_usd"], 6.0 + B.CLOUDFLARE_USD_DAY, places=4)
        self.assertEqual(B.cap_hold(self.root, utc(TUE, "10:00"))["day"], "2026-10-20")
        later = self.run_at(utc(TUE, "11:20"), claude=16.5)["hold"]
        self.assertEqual(later["since"], "2026-10-20T09:20:00Z", "the onset kept, run to run")
        self.assertEqual((self.root / B.HOLD_FILE).stat().st_mode & 0o777, 0o600)
        # The next UTC day has no hold, whatever the file says, until a run removes it.
        self.assertIsNone(B.cap_hold(self.root, utc(WED, "00:01")))
        self.assertIsNone(self.run_at(utc(WED, "00:20"), claude=16.6)["hold"])
        self.assertFalse((self.root / B.HOLD_FILE).exists())

    def test_a_cap_raised_above_the_days_spend_lifts_the_hold(self):
        self.run_at(utc(TUE, "00:20"), claude=10.0)
        self.assertIsNotNone(self.run_at(utc(TUE, "19:50"), claude=16.0)["hold"])
        self.assertIsNone(self.run_at(utc(TUE, "20:50"), claude=16.1, cap=12.0)["hold"], "the close's profit: $12")
        self.assertIsNone(B.cap_hold(self.root, utc(TUE, "21:00")))

    def test_yesterdays_late_spend_never_holds_today(self):
        """A lump of Monday's lane verdicts at 23:55 UTC, and nothing since: the line between the readings of 23:50 and
        00:20 gives Tuesday two thirds of it (the alarm says so), but what the readings put inside Tuesday for certain is
        none of it, so no line of Tuesday is held."""
        self.run_at(utc(MON, "23:50"), claude=10.0)
        out = self.run_at(utc(TUE, "00:20"), claude=17.5)
        figure = MT.day_figure(out, TUE, utc(TUE, "00:20"))
        self.assertTrue(figure["over"], "the line's share: $5.00 of the $7.50 and Cloudflare's $0.16")
        self.assertFalse(figure["certainly_over"])
        self.assertIsNone(out["hold"])
        self.assertIsNone(self.run_at(utc(TUE, "00:50"), claude=17.6)["hold"], "$0.10 for certain since 00:20")

    def test_a_hold_file_that_does_not_read_or_is_another_schemas_is_no_hold(self):
        path = self.root / B.HOLD_FILE
        for text in ("{not json", json.dumps([1]), json.dumps({"schema": 9, "day": "2026-10-20"}),
                     json.dumps({"schema": B.HOLD_SCHEMA, "day": "2026-10-19"})):
            path.write_text(text)
            self.assertIsNone(B.cap_hold(self.root, utc(TUE, "12:00")), text)
        self.assertIsNone(B.cap_hold(None, utc(TUE, "12:00")))
        path.write_text(json.dumps({"schema": B.HOLD_SCHEMA, "day": "2026-10-20", "spent_usd": 6.2, "cap_usd": 5.0}))
        self.assertEqual(B.cap_hold(self.root, utc(TUE, "12:00"))["spent_usd"], 6.2)


if __name__ == "__main__":
    unittest.main()
