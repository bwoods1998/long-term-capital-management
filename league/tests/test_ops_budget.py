"""THE BUDGET RULE (league/ops/budget.py, LTCM v3, D4; its rule version 2): the owner's ceiling and the one runway term
(the taper day by day, a cut and a raise), Sail's reserve at the Sail guard's own line, the day's figure set once a UTC
day, the card line, the knobs the dollars buy, the gate's reserve on both meters, the no-forward-edge stop and both
routes to Probe, the fail-closed reads, the tighten-only overlay in `settings.load`, Claude's room under the budget's
daily line, the funding notice (once per meter a week) and the drill. Fakes only: no network, no Sail. Every balance
here is a round example figure, never the account's."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from league.ops import budget as B
from league.swarm import settings as S
from league.swarm.guard import SailGuard, house_line
from league.swarm.models import ModelRouter
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeFrontier, FakeMonth

UTC = dt.timezone.utc
DAY = 86400.0
#: Tuesday Oct 20, 2026, 21:30Z: after that day's close.
NOW = dt.datetime(2026, 10, 20, 21, 30, tzinfo=UTC).timestamp()


def at(*args) -> float:
    return dt.datetime(*args, tzinfo=UTC).timestamp()


#: The Sail guard's own line on the default settings: it brakes under $32 and a braked guard releases at $37.
GUARD = house_line(S.DEFAULTS["guard"])


def inputs(*, sail=600.0, fixed=1.5, claude=100.0, p30=0.0, stop=False, need_sail=0.0, need_claude=0.0, reserve=None):
    """The rule's inputs. `reserve` is Sail's reserve as `gather` hands it (the Sail guard's release line); without it
    the rule's own least reserve (`RESERVE_USD`) is in force, as for Claude."""
    sail_row = {"balance_usd": sail, "fixed_usd_day": fixed, "need_usd": need_sail}
    if reserve is not None:
        sail_row["reserve_usd"] = reserve
    return {"p30_usd": p30, "p30_source": "test", "edge": {"stop": stop, "why": "test edge"},
            "meters": {"sail": sail_row, "claude": {"balance_usd": claude, "fixed_usd_day": 0.0, "need_usd": need_claude}}}


def spend_down(meter: str, balance: float, fixed: float, days: int, reserve: float | None = None) -> list[tuple[float, float]]:
    """(the balance, the research the rule gives on it) day by day while the meter spends its whole day: the fixed cost
    and every research dollar the rule allows (the fastest a balance can fall). Each day is its own first run."""
    out = []
    for _ in range(days):
        given = inputs(sail=balance, fixed=fixed, reserve=reserve) if meter == "sail" else inputs(claude=balance)
        research = B.compute(given, now=NOW)["meters"][meter]["research_usd_day"]
        out.append((round(balance, 4), research))
        balance -= fixed + research
    return out


class Rule(unittest.TestCase):
    def test_the_ceiling_with_a_full_prefund(self):
        doc = B.compute(inputs(), now=NOW)
        sail, claude = doc["meters"]["sail"], doc["meters"]["claude"]
        self.assertEqual((B.RULE_VERSION, doc["rule_version"], doc["schema"]), (2, 2, 2))
        self.assertEqual((B.CEILING_USD_DAY, B.ceiling_usd_day("sail"), B.ceiling_usd_day("claude")), (25.0, 15.0, 10.0),
                         "the owner's ceiling, split 0.6 and 0.4")
        self.assertEqual((sail["research_usd_day"], sail["limited_by"]), (15.0, "ceiling"))
        self.assertEqual((claude["research_usd_day"], claude["limited_by"]), (10.0, "ceiling"))
        self.assertEqual(doc["research_usd_day"], 25.0, "every meter together")
        # Sail: 590 above the reserve at 1.5 fixed + 15 a day; Claude: 95 at 10 a day.
        self.assertEqual((sail["runway_days"], sail["card_runway_days"]), (round(590 / 16.5, 1),) * 2)
        self.assertEqual((claude["runway_days"], claude["card_runway_days"]), (9.5, 9.5))
        self.assertEqual((sail["demand_usd_day"], claude["demand_usd_day"]), (16.5, 10.0), "fixed + its share of the ceiling")
        # The card date is the day the taper starts: when the days at the ceiling fall to the runway term.
        self.assertEqual(sail["card_date"], (dt.date(2026, 10, 20) + dt.timedelta(days=590 / 16.5 - 5)).isoformat())
        self.assertEqual(claude["card_date"], "2026-10-24")
        self.assertEqual((sail["topup_usd"], claude["topup_usd"]), (115.5, 70.0), "7 more days at the rate each wants")
        self.assertEqual(B.short(doc), [], "both hold a week of the ceiling")
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(doc["state"], "research at the ceiling")
        self.assertEqual(doc["direction"], "same")
        self.assertEqual(doc["rule"]["ceiling_usd_day"], 25.0)
        self.assertEqual((doc["rule"]["runway_days"], doc["rule"]["notice_days"], doc["rule"]["topup_days"]), (5, 7, 7))

    def test_never_above_the_ceiling_whatever_was_earned(self):
        """The profit share is still computed and split by need, and sits inside the ceiling: it lifts no meter."""
        before = B.compute(inputs(), now=NOW - DAY)
        doc = B.compute(inputs(p30=120.0, need_sail=30.0, need_claude=10.0), now=NOW, previous=before)
        self.assertEqual(doc["earned_usd_day"], 2.0, "0.5 x 120 / 30")
        self.assertEqual((doc["meters"]["sail"]["earned_usd_day"], doc["meters"]["claude"]["earned_usd_day"]), (1.5, 0.5))
        self.assertEqual((doc["meters"]["sail"]["research_usd_day"], doc["meters"]["claude"]["research_usd_day"]), (15.0, 10.0))
        self.assertEqual((doc["direction"], doc["meters"]["sail"]["direction"]), ("same", "same"))
        self.assertEqual(doc["state"], "research at the ceiling")
        self.assertIn("inside the ceiling", doc["why"][0])
        for sail in (0.0, 20.0, 120.0, 600.0, 1e6):
            for claude in (0.0, 30.0, 90.0, 1e6):
                for p30 in (None, -40.0, 0.0, 120.0, 3000.0, 5e7):
                    doc = B.compute(inputs(sail=sail, claude=claude, p30=p30, need_sail=1.0), now=NOW)
                    self.assertLessEqual(doc["research_usd_day"], B.CEILING_USD_DAY, (sail, claude, p30))
                    for m in B.METERS:
                        self.assertLessEqual(doc["meters"][m]["research_usd_day"], B.ceiling_usd_day(m), (m, sail, claude, p30))
        # Profit hides no short prefund either: the card line is at the ceiling's rate whatever was earned.
        doc = B.compute(inputs(sail=100.0, p30=3000.0, claude=2000.0), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual((doc["earned_usd_day"], sail["research_usd_day"], sail["limited_by"]), (50.0, 15.0, "ceiling"))
        self.assertEqual((sail["demand_usd_day"], sail["card_runway_days"]), (16.5, round(90 / 16.5, 1)))
        self.assertEqual(B.short(doc), ["sail"])

    def test_a_loss_earns_nothing_and_cuts_nothing(self):
        before = B.compute(inputs(p30=120.0), now=NOW - DAY)
        doc = B.compute(inputs(p30=-40.0), now=NOW, previous=before)
        self.assertEqual(doc["earned_usd_day"], 0.0, "a loss earns nothing (and never takes from the ceiling's research)")
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 15.0)
        self.assertEqual((doc["direction"], doc["meters"]["sail"]["direction"]), ("same", "same"))

    def test_a_cut_when_the_prefund_drains_and_a_raise_when_it_is_topped_up(self):
        before = B.compute(inputs(sail=600.0), now=NOW - DAY)
        doc = B.compute(inputs(sail=80.0), now=NOW, previous=before)
        sail = doc["meters"]["sail"]
        # 70 above the reserve less 5 days of the 1.5 fixed, over 5 days.
        self.assertEqual((sail["research_usd_day"], sail["limited_by"], sail["direction"]), (12.5, "runway", "cut"))
        self.assertEqual(sail["runway_days"], 5.0, "the taper holds the runway at the runway term")
        self.assertEqual((doc["direction"], doc["state"]), ("cut", "research under the ceiling"))
        self.assertIn("sail: under 5 days of the ceiling: research 12.5000 of 15.00 a day", doc["why"])
        again = B.compute(inputs(sail=600.0), now=NOW + DAY, previous=doc)
        self.assertEqual((again["direction"], again["meters"]["sail"]["direction"]), ("raise", "raise"))

    def test_the_taper_day_by_day_from_two_example_prefunds(self):
        """A Sail prefund of $250 at $1 a day fixed (its reserve the Sail guard's release line, as the job hands it) and a
        Claude prefund of $150, neither topped up, each spending its whole day: each runs at its share of the ceiling
        while it holds five days of it, then spends a fifth of what it holds above its reserve and five days of fixed cost
        a day. The ceiling is what research may spend, never what it spends: a prefund left alone drains and the research
        with it."""
        release = GUARD["release"]
        sail = spend_down("sail", 250.0, 1.0, 24, reserve=release)
        self.assertEqual(sail, [(250.0, 15.0), (234.0, 15.0), (218.0, 15.0), (202.0, 15.0), (186.0, 15.0), (170.0, 15.0),
                                (154.0, 15.0), (138.0, 15.0), (122.0, 15.0), (106.0, 12.8), (92.2, 10.04), (81.16, 7.832),
                                (72.328, 6.0656), (65.2624, 4.6525), (59.6099, 3.522), (55.0879, 2.6176), (51.4703, 1.8941),
                                (48.5762, 1.3152), (46.261, 0.8522), (44.4088, 0.4818), (42.927, 0.1854), (41.7416, 0.0),
                                (40.7416, 0.0), (39.7416, 0.0)])
        claude = spend_down("claude", 150.0, 0.0, 16)
        self.assertEqual(claude, [(150.0, 10.0), (140.0, 10.0), (130.0, 10.0), (120.0, 10.0), (110.0, 10.0), (100.0, 10.0),
                                  (90.0, 10.0), (80.0, 10.0), (70.0, 10.0), (60.0, 10.0), (50.0, 9.0), (41.0, 7.2),
                                  (33.8, 5.76), (28.04, 4.608), (23.432, 3.6864), (19.7456, 2.9491)])
        for meter, fixed, reserve, days in (("sail", 1.0, release, spend_down("sail", 250.0, 1.0, 60, reserve=release)),
                                            ("claude", 0.0, B.RESERVE_USD["claude"], spend_down("claude", 150.0, 0.0, 60))):
            research = [r for _, r in days]
            self.assertEqual(research, sorted(research, reverse=True), f"{meter}: it only tapers")
            self.assertGreaterEqual(min(research), 0.0, f"{meter}: never below zero")
            self.assertLessEqual(max(research), B.ceiling_usd_day(meter))
            for balance, spent in days:
                if spent > 0:  # research never spends the reserve nor the five days of the House's own fixed cost
                    self.assertGreaterEqual(balance - spent, reserve + B.RUNWAY_DAYS * fixed - 1e-3, (meter, balance))
        # Sail's research ends above its reserve and four days of fixed cost; from there only the fixed cost falls.
        done = next(balance for balance, spent in spend_down("sail", 250.0, 1.0, 60, reserve=release) if spent == 0.0)
        self.assertLessEqual(done, release + B.RUNWAY_DAYS * 1.0)
        self.assertGreater(done, release + (B.RUNWAY_DAYS - 1) * 1.0)

    def test_the_taper_ends_above_the_sail_guards_own_line(self):
        """Sail's reserve is the Sail guard's release line, so from any balance, with no top-up and every day spent whole,
        research reaches zero before the balance meets the line the guard brakes at: the rule never drains the meter
        until the guard stops the gate and pre-open fails. From there only the House's own fixed cost falls."""
        line, release = GUARD["line"], GUARD["release"]
        self.assertEqual((line, release), (32.0, 37.0), "2 x the House's burn + 30, and + 5 to release")
        self.assertGreater(release, B.RESERVE_USD["sail"], "the least reserve is under the guard's line: never the one in force")
        for start in (0.0, 20.0, 36.9, 37.0, 41.9, 42.1, 60.0, 100.0, 117.0, 250.0, 1000.0, 5000.0):
            for fixed in (0.5, 1.0, 1.5, 4.0):
                balance, days = start, 0
                while True:
                    row = B.compute(inputs(sail=balance, fixed=fixed, reserve=release), now=NOW)["meters"]["sail"]
                    self.assertEqual(row["reserve_usd"], release)
                    if row["research_usd_day"] == 0.0:
                        break
                    balance -= fixed + row["research_usd_day"]  # the day spent whole: the fastest the balance can fall
                    days += 1
                    self.assertGreater(balance, release + (B.RUNWAY_DAYS - 1) * fixed - 1e-3, (start, fixed, days))
                    self.assertGreater(balance, line, "a day with research never ends under the guard's brake")
                    self.assertLess(days, 1000, (start, fixed))
                self.assertLessEqual(balance, max(start, release + B.RUNWAY_DAYS * fixed + 1e-3), (start, fixed))
                if start >= release:
                    self.assertGreaterEqual(balance, release, "research was never what took the meter to the line")
        # A reserve under the rule's least is the least (the constant is the floor of the reserve, never a ceiling on it),
        # and a reserve the job could not read is no research: unknown is never money.
        self.assertEqual(B.compute(inputs(sail=100.0, reserve=3.0), now=NOW)["meters"]["sail"]["reserve_usd"], B.RESERVE_USD["sail"])
        for unread in ("lots", float("nan"), -1.0):
            given = inputs(sail=600.0)
            given["meters"]["sail"]["reserve_usd"] = unread
            doc = B.compute(given, now=NOW)
            self.assertEqual((doc["meters"]["sail"]["research_usd_day"], doc["meters"]["sail"]["limited_by"]), (0.0, "unreadable"))
            self.assertIn("sail: the reserve could not be read: no research", doc["why"])
        given = inputs(sail=600.0)
        given["meters"]["sail"]["reserve_usd"] = None
        self.assertEqual(B.compute(given, now=NOW)["meters"]["sail"]["research_usd_day"], 0.0, "a line the job could not read")

    def test_a_second_run_in_the_same_utc_day_keeps_the_days_figure(self):
        """THE DAY'S FIGURE IS SET ONCE. The job runs at 00:30 UTC and again after the close economics; the second reading
        has paid for the day's research, so a taper recomputed from it would put the day's cap under what the day booked.
        A later run the same day raises nothing and lowers nothing for today, and records what it would have set."""
        morning_at, evening_at = at(2026, 10, 20, 0, 30), at(2026, 10, 20, 20, 10)
        morning = B.compute(inputs(sail=80.0), now=morning_at)
        figure = {"day": "2026-10-20", "usd_day": 12.5, "limited_by": "runway", "set_at": "2026-10-20T00:30:00Z"}
        sail = morning["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["would_set_usd_day"], sail["limited_by"], sail["day_figure"]),
                         (12.5, 12.5, "runway", figure), "the first run of the day sets it: (70 - 5 x 1.5) / 5")
        # After the close: the meter has paid for 11.00 of the day's research and most of the day's fixed cost.
        evening = B.compute(inputs(sail=80.0 - 11.0 - 1.25), now=evening_at, previous=morning)
        sail = evening["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["limited_by"], sail["day_figure"]), (12.5, "runway", figure),
                         "today's cap stands: 11.00 is still under it and under its hold line")
        self.assertEqual(sail["would_set_usd_day"], 10.05, "(57.75 - 5 x 1.5) / 5: what this reading would have set")
        self.assertEqual((evening["direction"], sail["direction"], evening["research_usd_day"]), ("same", "same", 22.5))
        self.assertIn("sail: today's figure stands (12.5000 a day, set at 2026-10-20T00:30:00Z); this run's reading would "
                      "set 10.0500", evening["why"])
        self.assertEqual(evening["knobs"], morning["knobs"])
        # The card line is this run's own reading: the owner hears of the balance as it is.
        self.assertLess(sail["card_runway_days"], morning["meters"]["sail"]["card_runway_days"])
        # A top-up the same day raises nothing for today either: the next day's first run sets it.
        topped = B.compute(inputs(sail=600.0), now=evening_at + 600, previous=evening)
        self.assertEqual((topped["meters"]["sail"]["research_usd_day"], topped["meters"]["sail"]["would_set_usd_day"]), (12.5, 15.0))
        # FAIL CLOSED at once: a meter that cannot be read is no research; read again the same day, the day's figure.
        unread = B.compute(inputs(sail=None), now=evening_at + 1200, previous=topped)
        self.assertEqual((unread["meters"]["sail"]["research_usd_day"], unread["meters"]["sail"]["limited_by"],
                          unread["meters"]["sail"]["day_figure"]), (0.0, "unreadable", figure))
        again = B.compute(inputs(sail=40.0), now=evening_at + 1800, previous=unread)
        self.assertEqual((again["meters"]["sail"]["research_usd_day"], again["meters"]["sail"]["would_set_usd_day"]), (12.5, 4.5))
        # The first run of the next UTC day sets that day's figure from its own reading.
        tomorrow = B.compute(inputs(sail=67.75), now=morning_at + DAY, previous=evening)
        sail = tomorrow["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["would_set_usd_day"], sail["direction"]), (10.05, 10.05, "cut"))
        self.assertEqual(sail["day_figure"], {"day": "2026-10-21", "usd_day": 10.05, "limited_by": "runway",
                                              "set_at": "2026-10-21T00:30:00Z"})
        # A meter no run of the day has read yet is set by the first run that reads it.
        blind = B.compute(inputs(sail=None), now=morning_at)
        self.assertIsNone(blind["meters"]["sail"]["day_figure"])
        first = B.compute(inputs(sail=67.75), now=evening_at, previous=blind)
        self.assertEqual((first["meters"]["sail"]["research_usd_day"], first["meters"]["sail"]["day_figure"]["set_at"]),
                         (10.05, "2026-10-20T20:10:00Z"))
        self.assertEqual(first["meters"]["claude"]["day_figure"]["set_at"], "2026-10-20T00:30:00Z", "each meter its own")
        # What sets no day's figure: another version of the rule's file, another format's, a figure that does not read.
        for spoiled in ({**morning, "rule_version": 1}, {**morning, "schema": 1}, "budget", None):
            self.assertEqual(B.compute(inputs(sail=67.75), now=evening_at, previous=spoiled)["meters"]["sail"]["research_usd_day"],
                             10.05, spoiled if not isinstance(spoiled, dict) else (spoiled["schema"], spoiled["rule_version"]))
        for bad in ({"usd_day": "lots"}, {"usd_day": -1.0}, {"limited_by": "unreadable"}, {"day": "2026-10-19"}, {"day": None}):
            spoiled = copy.deepcopy(morning)
            spoiled["meters"]["sail"]["day_figure"].update(bad)
            self.assertEqual(B.compute(inputs(sail=67.75), now=evening_at, previous=spoiled)["meters"]["sail"]["research_usd_day"],
                             10.05, bad)
        # NEVER ABOVE THE CEILING: a day's figure that says more is read as the meter's share of it.
        over = copy.deepcopy(morning)
        over["meters"]["sail"]["day_figure"]["usd_day"] = 500.0
        self.assertEqual(B.compute(inputs(sail=67.75), now=evening_at, previous=over)["meters"]["sail"]["research_usd_day"], 15.0)

    def test_a_late_first_run_of_the_day_adds_back_what_the_day_already_paid(self):
        """THE DAY'S FIRST RUN ADDS BACK WHAT THE DAY ALREADY PAID. A first run that comes late (the 00:30 run missed, a
        deploy in the evening) reads a balance that has paid for part of the day's research: computed from that reading
        alone, the day's cap lands under what the day has booked. The run that sets the day's figure adds back what the
        meter has paid since 00:00 UTC, so it sets the cap a run at 00:30 would have."""
        release = GUARD["release"]
        early_at, late_at = at(2026, 10, 20, 0, 30), at(2026, 10, 20, 20, 10)
        early = B.compute(inputs(sail=100.0, fixed=1.0, reserve=release), now=early_at)["meters"]["sail"]
        self.assertEqual((early["research_usd_day"], early["limited_by"], early["added_back_usd"]), (11.6, "runway", 0.0),
                         "(100 - 37 - 5 x 1) / 5: a taper day")

        def late(paid, sail=100.0 - 10.84, **kw):
            given = inputs(sail=sail, fixed=1.0, reserve=release, **kw)
            given["meters"]["sail"]["paid_today_usd"] = paid
            return given
        # 20:10 UTC: the meter has paid 10.00 of research and 0.84 of the day's fixed cost.
        doc = B.compute(late(10.84), now=late_at)
        sail = doc["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["limited_by"], sail["added_back_usd"], sail["would_set_usd_day"]),
                         (11.6, "runway", 10.84, 11.6), "the cap a first run at 00:30 would have set")
        self.assertEqual(sail["day_figure"], {"day": "2026-10-20", "usd_day": 11.6, "limited_by": "runway",
                                              "set_at": "2026-10-20T20:10:00Z"})
        self.assertIn("sail: the day's first run: the 10.8400 the meter has paid since 00:00 UTC is added back (the day's "
                      "figure is from the balance as the day began)", doc["why"])
        # The control: the same reading with nothing added back is under the 10.00 the day has booked.
        naive = B.compute(inputs(sail=100.0 - 10.84, fixed=1.0, reserve=release), now=late_at)["meters"]["sail"]
        self.assertEqual((naive["research_usd_day"], naive["added_back_usd"]), (9.432, 0.0), "(89.16 - 42) / 5")
        self.assertLess(naive["research_usd_day"], 10.0)
        # Only the day's figure reads it: the runway, the card line and the top-up are the reading as it stands.
        for key in ("balance_usd", "card_runway_days", "card_date", "card_runs_out_on", "topup_usd", "demand_usd_day"):
            self.assertEqual(sail[key], naive[key], key)
        self.assertEqual(sail["runway_days"], round((89.16 - 37.0) / 12.6, 1), "what is left over the day's rate")
        # A later run of the day adds nothing back: the figure stands, and it records its reading as it stands.
        later = B.compute(late(11.5, sail=88.5), now=late_at + 3600, previous=doc)["meters"]["sail"]
        self.assertEqual((later["research_usd_day"], later["added_back_usd"], later["would_set_usd_day"]), (11.6, 0.0, 9.3))
        # Whenever in the day the first run comes, and whatever the day has paid by then, the figure is the same.
        for hour in range(24):
            paid = round(11.6 * hour / 24 + 1.0 * hour / 24, 4)  # the research and the fixed cost of the hours gone
            run = B.compute(late(paid, sail=100.0 - paid), now=at(2026, 10, 20, hour, 5))["meters"]["sail"]
            self.assertEqual(run["research_usd_day"], 11.6, hour)
        # Claude the same (no fixed cost): 40 at 00:00 is (40 - 5) / 5; 3.00 paid by the evening.
        given = inputs(claude=37.0)
        self.assertEqual(B.compute(given, now=late_at)["meters"]["claude"]["research_usd_day"], 6.4)
        given["meters"]["claude"]["paid_today_usd"] = 3.0
        claude = B.compute(given, now=late_at)["meters"]["claude"]
        self.assertEqual((claude["research_usd_day"], claude["added_back_usd"]), (7.0, 3.0))
        # NEVER ABOVE THE CEILING, and never more added back than a day's own most (its share of the ceiling and its
        # fixed cost): a figure that says more is read as that.
        self.assertEqual(B.compute(late(10.84, sail=600.0), now=late_at)["meters"]["sail"]["research_usd_day"], 15.0)
        most = B.compute(late(500.0, sail=50.0), now=late_at)["meters"]["sail"]
        self.assertEqual((most["added_back_usd"], most["research_usd_day"]), (16.0, 4.8), "(50 + 16 - 42) / 5")
        # UNKNOWN IS NEVER MONEY: what could not be read is nothing added back.
        for unread in (None, "lots", -3.0, float("nan"), float("inf"), True):
            row = B.compute(late(unread), now=late_at)["meters"]["sail"]
            self.assertEqual((row["research_usd_day"], row["added_back_usd"]), (9.432, 0.0), unread)
        # FAIL CLOSED is untouched: a meter that cannot be read is no research whatever it has paid.
        blind = B.compute(late(10.84, sail=None), now=late_at)["meters"]["sail"]
        self.assertEqual((blind["research_usd_day"], blind["limited_by"], blind["added_back_usd"]), (0.0, "unreadable", None))
        # A meter the day's earlier run could not read is set by the first run that reads it, with the day added back.
        first = B.compute(late(10.84), now=late_at, previous=B.compute(late(0.0, sail=None), now=early_at))["meters"]["sail"]
        self.assertEqual((first["research_usd_day"], first["added_back_usd"]), (11.6, 10.84))
        # The taper still ends above the Sail guard's line when every day's first run is late: each day's figure is the
        # one its 00:00 balance gives, and the day spends no more than it.
        balance, days = 250.0, 0
        while True:
            want = B.compute(inputs(sail=balance, fixed=1.0, reserve=release), now=early_at)["meters"]["sail"]["research_usd_day"]
            paid = round(0.8 * want + 0.84, 4)  # by 20:10: most of the day's research and of its fixed cost
            got = B.compute(late(paid, sail=balance - paid), now=late_at)["meters"]["sail"]["research_usd_day"]
            self.assertAlmostEqual(got, want, places=3, msg=(days, balance))
            if want == 0.0:
                break
            balance -= got + 1.0
            days += 1
            self.assertGreater(balance, release + (B.RUNWAY_DAYS - 1) * 1.0 - 1e-3, days)
            self.assertLess(days, 100)

    def test_a_tapered_meter_still_asks_for_a_card(self):
        """The review's case under the taper: research tapered to what the meter holds keeps its own runway at the runway
        term, so the card line must be judged at the rate the meter wants (its share of the ceiling)."""
        doc = B.compute(inputs(claude=40.0), now=NOW)
        claude = doc["meters"]["claude"]
        self.assertEqual((claude["limited_by"], claude["research_usd_day"], claude["runway_days"]), ("runway", 7.0, 5.0))
        self.assertEqual(claude["card_runway_days"], 3.5, "40 - 5 over the ceiling's 10 a day")
        self.assertIn("claude", B.short(doc))
        facts = B.notice_facts(doc, "claude", NOW)
        self.assertEqual((facts["balance_usd"], facts["usd_day"], facts["research_usd_day"], facts["runway_days"]),
                         ("40.00", "10.00", "10.00", "3.5"))
        self.assertEqual((facts["current_usd_day"], facts["current_research_usd_day"], facts["current_runway_days"]),
                         ("7.00", "7.00", "5.0"))
        self.assertEqual((facts["topup_usd"], facts["topup_days"], facts["card_line_days"]), ("70.00", 7, 7))
        # Sail just above its reserve and five days of fixed cost: a dime of research, its card line half a day.
        doc = B.compute(inputs(sail=18.0, fixed=1.5), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["runway_days"], sail["card_runway_days"]), (0.1, 5.0, 0.5))
        # Under them: research is already 0, its own runway at fixed alone 3.3 days, its card line 0.3.
        doc = B.compute(inputs(sail=15.0, fixed=1.5), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["runway_days"], sail["card_runway_days"]), (0.0, 3.3, 0.3))
        self.assertIn("sail", B.short(doc))
        # A day later the decayed balance is still told: nothing the rule tapers hides it.
        for balance in (74.0, 60.0, 40.0, 20.0, 6.0):
            self.assertIn("claude", B.short(B.compute(inputs(claude=balance), now=NOW)), balance)
        self.assertNotIn("claude", B.short(B.compute(inputs(claude=75.0), now=NOW)), "70 / 10 is the 7 days of the line")

    def test_research_never_takes_a_meter_under_the_runway_term(self):
        for balance in (0.0, 5.0, 20.0, 90.0, 150.0, 400.0, 2000.0):
            for fixed in (0.0, 0.5, 1.5, 4.0):
                for p30 in (None, -10.0, 0.0, 50.0, 900.0, 50_000.0):
                    doc = B.compute(inputs(sail=balance, fixed=fixed, claude=balance, p30=p30), now=NOW)
                    for m in B.METERS:
                        row = doc["meters"][m]
                        self.assertGreaterEqual(row["research_usd_day"], 0.0)
                        if row["research_usd_day"] > 0:
                            self.assertGreaterEqual(row["runway_days"], B.RUNWAY_DAYS - 0.05, (m, balance, fixed, p30))
                        self.assertLessEqual(row["research_usd_day"], B.ceiling_usd_day(m) + 1e-6)

    def test_the_no_forward_edge_stop_earns_nothing(self):
        doc = B.compute(inputs(p30=600.0, stop=True), now=NOW)
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(doc["state"], "research at the ceiling; no forward edge")
        self.assertTrue(doc["no_forward_edge"])
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 15.0, "the stop is the profit share's: the ceiling's research stays")
        lifted = B.compute(inputs(p30=600.0, stop=False), now=NOW)
        self.assertEqual((lifted["earned_usd_day"], lifted["no_forward_edge"], lifted["state"]), (10.0, False, "research at the ceiling"))

    def test_unknown_is_never_money(self):
        doc = B.compute(inputs(p30=None), now=NOW)
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertIn("p30 unreadable: nothing earned", doc["why"])
        doc = B.compute(inputs(sail=None, p30=900.0), now=NOW)
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 0.0)
        self.assertEqual(doc["meters"]["sail"]["limited_by"], "unreadable")
        self.assertEqual(doc["state"], "research under the ceiling", "Claude's 10 alone")
        self.assertEqual(B.compute(inputs(sail=None, claude=None), now=NOW)["state"], "no research")
        self.assertEqual(B.compute({**inputs(), "meters": {"sail": {"balance_usd": 600.0, "fixed_usd_day": None},
                                                           "claude": {"balance_usd": 100.0, "fixed_usd_day": 0.0}}},
                                   now=NOW)["meters"]["sail"]["research_usd_day"], 0.0, "an unreadable fixed cost too")
        no_edge = B.compute({**inputs(p30=900.0), "edge": None}, now=NOW)
        self.assertEqual(no_edge["earned_usd_day"], 0.0, "no edge state: the stop stands")

    def test_an_empty_meter_is_short_with_the_amount_that_buys_seven_more_days(self):
        doc = B.compute(inputs(sail=60.0, fixed=1.5), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["limited_by"]), (8.5, "runway"), "(50 - 5 x 1.5) / 5")
        self.assertEqual(sail["runway_days"], 5.0)
        self.assertEqual(sail["card_runway_days"], round(50 / 16.5, 1))
        self.assertEqual(sail["card_date"], "2026-10-20", "already under the runway term: the taper has started")
        self.assertEqual(sail["topup_usd"], 115.5, "7 x (1.5 + 15)")
        self.assertEqual(B.short(doc), ["sail"], "Claude's 95 over its reserve is 9.5 days of the 10 it wants")
        empty = B.compute(inputs(claude=3.0), now=NOW)
        claude = empty["meters"]["claude"]
        self.assertEqual((claude["runway_days"], claude["card_runway_days"]), (0.0, 0.0), "under the reserve at either rate")
        self.assertEqual(claude["topup_usd"], 72.0, "the 2 it lacks to its reserve, and 7 days of 10")
        self.assertIn("claude", B.short(empty))

    def test_an_unreadable_balance_reads_its_card_line_elsewhere_but_never_research(self):
        given = inputs(sail=None)
        given["meters"]["sail"].update(notice_balance_usd=60.0, notice_balance_source="the gateway's Sail reading")
        sail = B.compute(given, now=NOW)["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["limited_by"]), (0.0, "unreadable"))
        self.assertEqual((sail["card_runway_days"], sail["topup_usd"]), (round(50 / 16.5, 1), 115.5))
        doc = B.compute(given, now=NOW)
        self.assertIn("sail", B.short(doc))
        self.assertEqual(B.notice_facts(doc, "sail", NOW)["balance_usd"], "60.00")
        self.assertNotIn("sail", B.short(B.compute(inputs(sail=None), now=NOW)), "no reading at all: nothing to say")


class Knobs(unittest.TestCase):
    #: The dollars a day (both meters together, split 0.6 and 0.4) and what they buy: the Sail model pace an hour, the
    #: Gym's boxes, the Claude line, the population ceiling, the architect's scheduled and refill cadences (seconds).
    LEVELS = {25.0: (0.25, 5, 10.0, 25, 2880, 1152), 12.0: (0.12, 2, 4.8, 12, 6000, 2400),
              5.0: (0.05, 1, 2.0, 8, 14400, 5760), 1.0: (0.01, 1, 0.4, 8, 72000, 28800)}

    def test_the_knobs_at_25_12_5_and_1_dollars_a_day(self):
        for total, want in self.LEVELS.items():
            k = B.knobs(total * B.SPLIT["sail"], total * B.SPLIT["claude"])
            self.assertEqual((k["researcher.sail_usd_per_hour"], k["gym.max_boxes"], k["claude.role_usd_day"],
                              k["population.ceiling"], k["architect.every_seconds"], k["architect.refill_seconds"]), want, total)
            sail = total * B.SPLIT["sail"]
            self.assertEqual(k["gym.max_boxes"], max(1, int(sail * 0.6 / 1.6 + 1e-9)), "floor(Sail x 0.6 / 1.6), at least 1")
            self.assertAlmostEqual(k["researcher.sail_usd_per_hour"] * 24, sail * 0.4, places=4, msg="the rest, by the hour")

    def test_the_architects_cadence_follows_the_dollars(self):
        """RULE_VERSION 1 scaled the cadence by the floor, so it was 14,400 s at any dollars: now more dollars are a faster
        architect and fewer a slower one, down to once a day."""
        every = [B.knobs(t * 0.6, t * 0.4)["architect.every_seconds"] for t in (25.0, 12.0, 5.0, 1.0, 0.5)]
        self.assertEqual(every, [2880, 6000, 14400, 72000, 86400])
        self.assertEqual(every, sorted(every))
        for total in (25.0, 12.0, 5.0, 1.0):
            k = B.knobs(total * 0.6, total * 0.4)
            self.assertLess(k["architect.refill_seconds"], k["architect.every_seconds"], "a refill is faster than a scheduled pass")
        fast = B.knobs(600.0, 400.0)  # no budget.json gives this (the ceiling holds): the minimums alone
        self.assertEqual((fast["architect.every_seconds"], fast["architect.refill_seconds"]), (1800, 900))

    def test_no_dollars_buy_almost_nothing(self):
        zero = B.knobs(0, 0)
        self.assertEqual((zero["researcher.sail_usd_per_hour"], zero["claude.role_usd_day"]), (0.0, 0.0))
        self.assertEqual((zero["gym.max_boxes"], zero["population.ceiling"]), (1, 8))
        self.assertEqual((zero["architect.every_seconds"], zero["architect.refill_seconds"]), (86400, 86400))
        self.assertEqual(B.knobs("junk", None), zero)


class Overlay(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def write(self, sail=10.0, claude=6.0, *, at_=NOW - 3600, fixed=1.2, **extra):
        doc = {"schema": B.SCHEMA, "at": at_, "state": "research under the ceiling",
               "meters": {"sail": {"research_usd_day": sail, "fixed_usd_day": fixed}, "claude": {"research_usd_day": claude}},
               **extra}
        (self.root / "budget.json").write_text(json.dumps(doc))

    def overlay(self, settings=None):
        return B.overlay(copy.deepcopy(settings or S.DEFAULTS), self.root, now=NOW)

    def test_tighten_only(self):
        self.write(sail=10.0, claude=6.0)
        out = self.overlay()
        k = B.knobs(10.0, 6.0)
        self.assertEqual(out["gym"]["max_boxes"], min(8, k["gym.max_boxes"]))
        self.assertEqual(out["population"]["ceiling"],
                         max(k["population.ceiling"], S.DEFAULTS["population"]["floor"] + B.BIRTH_MARGIN))
        self.assertEqual(out["population"]["start"], out["population"]["ceiling"], "the start is held under the ceiling")
        self.assertEqual(out["architect"]["every_seconds"], 14400, "max(): the configured 4 h is slower than the budget's")
        self.assertEqual(out["architect"]["refill_seconds"], k["architect.every_seconds"],
                         "the budget's ceiling holds the start down, so every pass is a refill: it never runs faster than "
                         "the budget's scheduled cadence (4500 s: the configured hourly is lifted)")
        self.assertEqual((k["architect.every_seconds"], k["architect.refill_seconds"]), (4500, 1800))
        self.assertEqual(out["budget"]["knobs"]["architect.refill_seconds"], 4500, "the block says the knob as applied")
        self.assertEqual(out["researcher"]["usd_per_hour"], k["researcher.sail_usd_per_hour"],
                         "sail_usd_per_hour unset: the combined pace that then governs Sail is capped")
        self.assertIsNone(out["researcher"]["sail_usd_per_hour"])
        self.assertEqual(out["claude"]["role_usd_day"]["researcher"], 6.0, "100 capped")
        self.assertEqual(out["claude"]["role_usd_day"]["strategist"], 4.0, "4 is already under 6")
        for role in S.DEFAULTS["claude"]["roles"]:
            self.assertLessEqual(out["claude"]["role_usd_day"][role], 6.0, f"{role} gets a line")
        self.assertEqual((out["budget"]["source"], out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]),
                         ("budget.json", 10.0, 6.0))

    def test_a_raise_never_loosens_a_configured_value(self):
        self.write(sail=15.0, claude=10.0)  # the ceiling: the most the rule ever gives
        settings = copy.deepcopy(S.DEFAULTS)
        settings["researcher"]["sail_usd_per_hour"] = 0.2
        settings["gym"]["max_boxes"] = 3
        settings["population"]["ceiling"] = 12
        settings["architect"]["every_seconds"] = 900
        settings["claude"]["role_usd_day"]["strategist"] = 4.0
        out = self.overlay(settings)
        self.assertEqual(out["researcher"]["sail_usd_per_hour"], 0.2, "under the ceiling's 0.25: it stands")
        self.assertEqual(out["researcher"]["usd_per_hour"], 4.0, "the combined pace is not the one in force")
        self.assertEqual(out["gym"]["max_boxes"], 3, "under the ceiling's 5")
        self.assertEqual(out["population"]["ceiling"], 12)
        self.assertEqual(out["architect"]["every_seconds"], 2880, "the budget never makes the architect faster than its dollars")
        self.assertEqual(out["claude"]["role_usd_day"]["strategist"], 4.0)
        self.assertEqual(out["claude"]["role_usd_day"]["researcher"], 10.0, "100 capped at the ceiling's Claude share")

    def test_the_ceiling_is_the_rules_and_the_floor_is_the_fail_safe(self):
        """Two constants. The owner's $25 a day is what the RULE may give a meter that holds its runway. What the swarm
        runs on when the rule was not read (no budget.json, an unreadable, malformed or stale one: a failed budget job)
        is the floor of $5 a day, as before the ceiling: never the ceiling with no runway test."""
        self.assertEqual((B.CEILING_USD_DAY, B.FLOOR_CAP_USD_DAY), (25.0, 5.0))
        self.assertEqual([(B.ceiling_usd_day(m), B.floor_usd_day(m)) for m in B.METERS], [(15.0, 3.0), (10.0, 2.0)])
        block = B.floor_block("no budget.json")
        self.assertEqual((block["sail_usd_day"], block["claude_usd_day"]), (3.0, 2.0))
        self.assertEqual((self.overlay()["budget"]["sail_usd_day"], self.overlay()["budget"]["claude_usd_day"]), (3.0, 2.0),
                         "no budget.json")
        (self.root / "budget.json").write_text("{not json")
        self.assertEqual(B.sail_caps(self.overlay())["research"], 3.0, "an unreadable one")
        self.write(sail=15.0, claude=10.0, at_=NOW - 37 * 3600)  # the job stopped a day and a half ago, at the ceiling
        stale = self.overlay()["budget"]
        self.assertEqual((stale["source"], stale["sail_usd_day"], stale["claude_usd_day"]), ("stale budget.json", 3.0, 2.0))
        self.write(sail=15.0, claude=10.0)  # read an hour ago: the rule's own answer
        fresh = self.overlay()["budget"]
        self.assertEqual((fresh["source"], fresh["sail_usd_day"], fresh["claude_usd_day"]), ("budget.json", 15.0, 10.0))

    def test_a_file_that_says_more_than_the_ceiling_is_read_as_the_ceiling(self):
        """NEVER ABOVE THE CEILING: whatever budget.json says, no meter is read over its share of the owner's $25."""
        for sail, claude in ((500.0, 400.0), (15.01, 10.01), (1e9, 1e9)):
            self.write(sail=sail, claude=claude)
            out = self.overlay()
            self.assertEqual((out["budget"]["source"], out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]),
                             ("budget.json", 15.0, 10.0), (sail, claude))
            self.assertEqual(out["budget"]["knobs"], {**B.knobs(15.0, 10.0), "population.ceiling": 25,
                                                      "architect.refill_seconds": 2880}, "the start of 48 is held down")
            self.assertEqual(B.sail_caps(out)["research"], 15.0)
            self.assertEqual(out["gym"]["max_boxes"], 5)
            self.assertEqual(out["researcher"]["usd_per_hour"], 0.25)

    def test_a_start_over_the_ceiling_cannot_bypass_it(self):
        """The review's case: the floor's ceiling under a configured start of 16 kept the architect refilling hourly
        and reseeding toward 16. (The ceiling is the production floor of 8 + BIRTH_MARGIN: it never falls to the floor.)"""
        settings = copy.deepcopy(S.DEFAULTS)
        settings["population"].update(start=16, ceiling=96, floor=8, reseed_max=4)
        out = self.overlay(settings)  # no budget.json: the floor
        self.assertEqual((out["population"]["ceiling"], out["population"]["start"]), (8 + B.BIRTH_MARGIN, 8 + B.BIRTH_MARGIN))
        self.assertEqual(out["architect"]["refill_seconds"], 14400, "held to the scheduled cadence: every pass is a refill")
        settings["population"].update(start=5)
        self.assertEqual(self.overlay(settings)["population"]["start"], 5, "a start under the ceiling stays")
        self.assertEqual(self.overlay(settings)["architect"]["refill_seconds"], 5760,
                         "and a true refill runs at the budget's own refill cadence (the configured hourly is lifted to it)")
        settings["architect"]["refill_seconds"] = 90000
        self.assertEqual(self.overlay(settings)["architect"]["refill_seconds"], 90000, "a slower refill stays")

    def test_a_configured_value_that_is_not_a_number_is_left_to_its_reader(self):
        self.write()
        settings = copy.deepcopy(S.DEFAULTS)
        settings["gym"]["max_boxes"] = "many"
        settings["claude"]["role_usd_day"] = "lots"  # the router reads a line of 0 for every role
        settings["claude"]["roles"] = ["architect", 7]
        out = self.overlay(settings)
        self.assertEqual(out["gym"]["max_boxes"], "many")
        self.assertEqual(out["claude"]["role_usd_day"], "lots")
        settings["claude"]["role_usd_day"] = {"architect": True, "audit": None}
        out = self.overlay(settings)
        self.assertIs(out["claude"]["role_usd_day"]["architect"], True, "a bool is a line of 0 to the router already")
        self.assertEqual(out["claude"]["role_usd_day"]["audit"], 6.0)

    def test_no_usable_file_is_the_floor(self):
        floor = (B.floor_usd_day("sail"), B.floor_usd_day("claude"))
        cases = {"missing": None, "future": dict(at_=NOW + 3600),
                 "negative": dict(sail=-1.0), "not a number": dict(claude="lots")}
        for name, kw in cases.items():
            (self.root / "budget.json").unlink(missing_ok=True)
            if kw is not None:
                self.write(**kw)
            out = self.overlay()
            self.assertEqual(out["budget"]["source"], "floor", name)
            self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]), floor, name)
            self.assertEqual(out["gym"]["max_boxes"], 1, name)
        (self.root / "budget.json").write_text("{not json")
        self.assertIn("cannot be read", self.overlay()["budget"]["why"])
        (self.root / "budget.json").write_text(json.dumps({"schema": B.SCHEMA + 1, "at": NOW}))
        self.assertEqual(self.overlay()["budget"]["source"], "floor")

    def test_another_rules_file_is_no_file(self):
        """A release on either side of the rule's change reads the other's budget.json as no usable file: rule version 1
        wrote schema 1 (and reads nothing else), this one writes and reads schema 2. So a deploy never runs on the old
        rule's dollars and a rollback never runs on this rule's: each is at the floor until its own job has run."""
        self.assertEqual(B.SCHEMA, 2)
        for said in (0.2329, 15.0):  # a figure under version 1's floor; this rule's ceiling in version 1's format
            (self.root / "budget.json").write_text(json.dumps({"schema": 1, "rule_version": 1, "at": NOW - 3600, "meters": {
                "sail": {"research_usd_day": said, "fixed_usd_day": 1.0}, "claude": {"research_usd_day": said}}}))
            out = self.overlay()
            self.assertEqual((out["budget"]["source"], out["budget"]["why"]), ("floor", "budget.json is not schema 2"))
            self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]),
                             (B.floor_usd_day("sail"), B.floor_usd_day("claude")), said)
        self.write(sail=15.0, claude=10.0)
        self.assertEqual(json.loads((self.root / "budget.json").read_text())["schema"], 2, "what version 1's reader refuses")

    def test_a_stale_file_never_loosens(self):
        """A budget job that stopped: each meter is the lower of the floor and the stale file, never the floor alone."""
        for sail, claude, want in ((0.0, 0.0, (0.0, 0.0)), (0.33, 50.0, (0.33, B.floor_usd_day("claude"))),
                                   (10.0, 6.0, (B.floor_usd_day("sail"), B.floor_usd_day("claude")))):
            self.write(sail=sail, claude=claude, at_=NOW - 37 * 3600)
            out = self.overlay()
            self.assertEqual(out["budget"]["source"], "stale budget.json")
            self.assertIn("stale", out["budget"]["why"])
            self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]), want, (sail, claude))
            self.assertEqual(B.sail_caps(out)["research"], want[0])
        doc = {"schema": B.SCHEMA, "at": NOW - 40 * 3600, "meters": {"sail": {"research_usd_day": 0.0, "limited_by": "unreadable"},
                                                             "claude": {"research_usd_day": "x"}}}
        (self.root / "budget.json").write_text(json.dumps(doc))
        out = self.overlay()
        self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]), (0.0, 0.0),
                         "a meter the stale file could not read (or did not say) is 0, not the floor")

    def test_the_guards_caps_say_whether_they_are_a_reading_of_the_rule(self):
        """`sail_caps`' `read`: the floor, budget.json (a 0 of its own included) and a stale file are the rule's own answer;
        a malformed block and the block of a rule that could not run are not, at the same dollars as ever."""
        floor = B.floor_usd_day("sail")
        self.assertEqual(B.sail_caps(self.overlay()), {"research": floor, "fixed": 1.0, "account": floor + 1.0,
                                                       "source": "floor", "read": True, "gate_reserve": 0.5})
        self.assertEqual(B.sail_caps({}), {"research": floor, "fixed": 1.0, "account": floor + 1.0,
                                           "source": "floor (no budget block)", "read": True, "gate_reserve": 0.5})
        self.assertIs(B.sail_caps({}, self.root, NOW)["read"], True, "the guard's own read of the root")
        for sail, at_, want in ((10.0, NOW - 3600, 10.0), (0.0, NOW - 3600, 0.0), (10.0, NOW - 37 * 3600, floor),
                                (0.0, NOW - 37 * 3600, 0.0)):
            self.write(sail=sail, at_=at_)
            caps = B.sail_caps(self.overlay())
            self.assertEqual((caps["research"], caps["read"]), (want, True), (sail, at_))
            self.assertIs(B.sail_caps({}, self.root, NOW)["read"], True, (sail, at_))
        no_research = {"research": 0.0, "fixed": 1.0, "account": 1.0, "read": False, "gate_reserve": 0.0}
        for bad in ({"sail_usd_day": "lots"}, {"sail_usd_day": -1}, {"sail_usd_day": float("nan")}, "budget", {}, 7):
            self.assertEqual(B.sail_caps({"budget": bad}), {**no_research, "source": "malformed budget block: no research"}, bad)
        block = {"source": "unavailable", "sail_usd_day": 0.0, "claude_usd_day": 0.0, "fixed_sail_usd_day": None, "read": False}
        self.assertEqual(B.sail_caps({"budget": block}), {**no_research, "source": "unavailable"})
        self.assertIs(B.sail_caps({"budget": {**block, "read": True}})["read"], True)
        for said in (None, 0, "yes"):  # the rule's own blocks say nothing; a block that says anything but true is unread
            self.assertIs(B.sail_caps({"budget": {**block, "read": said}})["read"], False, said)

    def test_the_ceiling_never_falls_to_the_population_floor(self):
        """Births and forks stay possible at the floor's dollars (the production floor of 8 and BUILD-2's 8/16)."""
        settings = copy.deepcopy(S.DEFAULTS)
        settings["population"].update(start=16, ceiling=16, floor=8)
        out = self.overlay(settings)  # no budget.json: the floor
        self.assertEqual(out["budget"]["source"], "floor")
        self.assertEqual(out["population"]["ceiling"], 8 + B.BIRTH_MARGIN)
        self.assertGreater(out["population"]["ceiling"], out["population"]["floor"])
        settings["population"]["ceiling"] = 10
        self.assertEqual(self.overlay(settings)["population"]["ceiling"], 10, "still tighten-only: a lower ceiling stands")

    def test_openai_is_closed_by_the_budget(self):
        """OpenAI is no meter of the rule: the overlay leaves it no room, whatever the layers under it say."""
        self.write(sail=500.0, claude=400.0)
        out = self.overlay()
        self.assertEqual(out["guard"]["openai_cap_usd"], 0.0)
        self.assertEqual(out["budget"]["openai_usd_day"], 0.0)

    def test_the_operators_budget_key_is_replaced(self):
        settings = copy.deepcopy(S.DEFAULTS)
        settings["budget"] = {"source": "budget.json", "sail_usd_day": 9999.0, "claude_usd_day": 9999.0}
        out = self.overlay(settings)
        self.assertEqual(out["budget"]["source"], "floor")
        self.assertEqual(out["budget"]["sail_usd_day"], B.floor_usd_day("sail"))


class SettingsLoad(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def test_a_state_root_always_carries_a_budget_and_none_without_one(self):
        loaded = S.load(self.root, config={})
        self.assertEqual(loaded["budget"]["source"], "floor")
        self.assertEqual(loaded["population"]["ceiling"], loaded["population"]["floor"] + B.BIRTH_MARGIN)
        self.assertGreater(loaded["population"]["ceiling"], loaded["population"]["floor"])
        self.assertEqual(loaded["population"]["start"], loaded["population"]["ceiling"], "the start is held under the ceiling")
        self.assertEqual(loaded["guard"]["openai_cap_usd"], 0.0, "no OpenAI room under the budget")
        self.assertNotIn("budget", S.load(None, config={}))
        self.assertEqual(S.load(None, config={})["population"]["ceiling"], 96)

    def test_budget_json_is_applied_last_over_swarm_json(self):
        import time

        (self.root / "swarm.json").write_text(json.dumps({"gym": {"max_boxes": 30}, "budget": {"sail_usd_day": 1e6},
                                                           "guard": {"after_burst_usd_day": 500}}))
        (self.root / "budget.json").write_text(json.dumps({"schema": B.SCHEMA, "at": time.time() - 60, "meters": {
            "sail": {"research_usd_day": 12.0}, "claude": {"research_usd_day": 4.0}}}))
        loaded = S.load(self.root, config={})
        self.assertEqual(loaded["gym"]["max_boxes"], 4, "12 x 0.6 / 1.6: the operator's 30 is tightened")
        self.assertEqual(loaded["budget"]["sail_usd_day"], 12.0)
        self.assertNotIn("burst_until", loaded["guard"])
        self.assertNotIn("after_burst_usd_day", S.DEFAULTS["guard"])

    def test_a_rule_that_cannot_run_is_no_research(self):
        with mock.patch.object(B, "overlay", side_effect=RuntimeError("boom")):
            loaded = S.load(self.root, config={})
        self.assertEqual((loaded["budget"]["sail_usd_day"], loaded["budget"]["claude_usd_day"]), (0.0, 0.0))
        self.assertEqual(loaded["budget"]["source"], "unavailable")
        self.assertIs(loaded["budget"]["read"], False, "no reading of the rule, and the block says so")
        self.assertEqual(B.sail_caps(loaded), {"research": 0.0, "fixed": 1.0, "account": 1.0, "source": "unavailable",
                                               "read": False, "gate_reserve": 0.0})


class Meter:
    def __init__(self, remaining):
        self.value = remaining
        self.last = {}

    def remaining(self):
        from decimal import Decimal

        return Decimal(str(self.value))


class ClaudeRoom(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(NOW)
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["claude"]["usd_cap"] = 10_000.0
        self.router = ModelRouter(self.store, None, settings=self.settings, claude_factory=lambda model: None,
                                  claude_meter=Meter(500))

    def admit(self, required, role="audit"):
        """One Claude admission. By default for the gate's audit, the last stage, which reads the day's whole line; the
        review leaves the audit's hold in it and every other role both (`test_the_gates_holds_are_kept_by_stage`)."""
        errors = []
        out = self.router._claude_admit(role=role, family=None, key="k", model="claude-opus-5-5",
                                        body={"max_tokens": 100, "output_config": {"effort": "high"}}, required=required,
                                        errors=errors)
        return out, errors

    def test_no_block_is_the_routers_own_read(self):
        """Settings handed in without the block (a scheduler change that dropped it) never lift the budget: the router
        reads its store root's budget.json itself, the floor when there is none."""
        self.assertEqual(self.router.claude_budget_room(), B.floor_usd_day("claude"))
        self.assertEqual(self.router.claude_room(), B.floor_usd_day("claude"))
        (Path(self.dir.name) / "budget.json").write_text(json.dumps({"schema": B.SCHEMA, "at": NOW - 60, "meters": {
            "sail": {"research_usd_day": 1.0}, "claude": {"research_usd_day": 0.5}}}))
        self.assertEqual(self.router.claude_budget_room(), 0.5)

    def test_the_gates_holds_are_kept_by_stage(self):
        """THE GATE NEVER WAITS FOR MIDNIGHT, on the paid models: the day's Claude line is kept by stage. Every role but
        the gate's two leaves the review's hold and the audit's; the review leaves the audit's. So late in the day a
        review finds its hold, and the audit still finds its own after that review was paid."""
        self.assertEqual((B.GATE_HOLDS_USD, B.GATE_STAGES), ({"review": 0.65, "audit": 1.30}, ("review", "audit")))
        self.assertEqual([B.paid_model_reserve(role) for role in ("review", "audit", "strategist", "architect", "researcher",
                                                                  "rewrite", "diagnostician", None)],
                         [1.3, 0.0, 1.95, 1.95, 1.95, 1.95, 1.95, 0.0], "no role named is a reading of the line, never a call")
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 4.0}
        rooms = [self.router.claude_budget_room(role) for role in (None, "audit", "review", "strategist")]
        self.assertEqual(rooms[:2], [4.0, 4.0])
        self.assertAlmostEqual(rooms[2], 2.7, places=9)
        self.assertAlmostEqual(rooms[3], 2.05, places=9)
        (request, _), _ = self.admit(2.0, role="strategist")
        self.assertIsNotNone(request, "what the line holds over the gate's holds is the other roles'")
        for role in ("strategist", "architect", "researcher", "rewrite", "diagnostician"):
            (request, kind), errors = self.admit(0.1, role=role)
            self.assertEqual((request, kind), (None, "line"), f"{role}: the last $1.95 of the day is the gate's")
            self.assertIn("research budget's Claude line for today has no room", errors[0])
        # Late in the day: a review finds its hold, and a second review may not spend the audit's.
        (request, _), _ = self.admit(0.65, role="review")
        self.assertIsNotNone(request)
        (request, kind), _ = self.admit(0.1, role="review")
        self.assertEqual((request, kind), (None, "line"), "what is left of the day is the audit's hold")
        (request, _), _ = self.admit(1.3, role="audit")
        self.assertIsNotNone(request, "the audit finds its hold after the review was paid")
        self.assertAlmostEqual(self.store.spent(["claude"]), 3.95, places=9)
        self.assertEqual(self.admit(0.1, role="audit")[0], (None, "line"), "the line itself still binds the gate")
        # The review's case: another role at its limit and reviews first. Pooled, three reviews took the audit's dollar.
        self.clock.advance(DAY)
        self.settings["budget"]["claude_usd_day"] = B.ceiling_usd_day("claude")
        self.store.add_spend("claude", 8.0, detail={"role": "strategist"})
        admitted = [self.admit(0.5, role="review")[0][0] is not None for _ in range(3)]
        self.assertEqual(admitted, [True, False, False], "10.00 - 8.00 - the audit's 1.30 holds one review of 0.50")
        self.assertIsNotNone(self.admit(1.3, role="audit")[0][0], "and the audit's hold is whole")
        # OpenAI is under the same line and leaves the same holds; a line under the audit's hold is all the audit's.
        self.clock.advance(DAY)
        self.settings["budget"]["claude_usd_day"] = 2.0
        errors: list[str] = []
        self.router.month, self.router.frontier_factory = FakeMonth(1000), lambda model: FakeFrontier(model)
        self.assertIsNone(self.router._ask_openai(role="architect", system="s", user="u", family=None, key="k", max_output=1000,
                                                  openai_model="gpt-6-astra", effort="medium", need_usd=1.0, errors=errors))
        self.assertIn("paid-model line", errors[0])
        self.settings["budget"]["claude_usd_day"] = 1.2
        self.assertEqual(self.admit(0.01, role="strategist")[0], (None, "line"))
        self.assertEqual(self.admit(0.5, role="review")[0], (None, "line"))
        self.assertIsNotNone(self.admit(1.0, role="audit")[0][0])
        # At the owner's ceiling the other roles have the line less both holds, the review the line less the audit's.
        self.clock.advance(DAY)
        self.settings["budget"]["claude_usd_day"] = B.ceiling_usd_day("claude")
        self.assertEqual([round(self.router.claude_budget_room(role), 9) for role in ("strategist", "review", "audit")],
                         [8.05, 8.7, 10.0])

    def test_a_handed_block_is_held_to_the_ceiling(self):
        """NEVER ABOVE THE CEILING, whatever way the block came: the Sail guard's caps and the router's room hold a
        `budget` block that says more (settings handed in, never through `settings.load` and `read`) to each meter's
        share of the owner's ceiling."""
        block = {"source": "handed", "sail_usd_day": 500.0, "claude_usd_day": 500.0, "fixed_sail_usd_day": 1.0}
        caps = B.sail_caps({"budget": block})
        self.assertEqual((caps["research"], caps["account"], caps["gate_reserve"], caps["read"]), (15.0, 16.0, 1.5, True))
        self.assertEqual(B.paid_model_room(block, 0.0, 0.0), 10.0)
        self.assertEqual(round(B.paid_model_room(block, 1.0, 0.0, role="strategist"), 9), 7.05)
        self.settings["budget"] = block
        self.assertEqual((self.router.claude_budget_room(), self.router.claude_room()), (10.0, 10.0))
        (request, kind), _ = self.admit(10.5)
        self.assertEqual((request, kind), (None, "line"))
        guard = SailGuard(self.store, self.settings, lambda: (5000.0, 5.0), clock=self.clock, disk_free=lambda: 100.0 * 2 ** 30)
        self.store.add_spend("gym_box", 14.99)
        guard.check()
        self.assertEqual((guard.allows(), guard.last["budget_research_usd_day"]), (True, 15.0))
        self.store.add_spend("gym_box", 0.01)
        self.clock.advance(180)
        guard.check()
        self.assertEqual((guard.allows(), guard.causes), (False, ["research_budget"]), "the day's cap is the ceiling's share")
        # A block under the ceiling is read as it is.
        self.assertEqual(B.sail_caps({"budget": {**block, "sail_usd_day": 14.99}})["research"], 14.99)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 9.5}, 0.0), 9.5)

    def test_the_budgets_claude_dollars_today_cap_the_room_and_admission(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        self.assertEqual(self.router.claude_room(), 2.0)
        (request, kind), _ = self.admit(1.5)
        self.assertIsNotNone(request)
        (request, kind), errors = self.admit(1.0)
        self.assertEqual((request, kind), (None, "line"), "a budget line, not a funding cliff (no_room)")
        self.assertIn("research budget", errors[0])
        self.assertEqual(self.router.claude_funded_room(), 495.0, "the funded room is the gateway's (a fake meter here)")
        self.clock.advance(DAY)  # a new UTC day: its own dollars
        self.assertEqual(self.router.claude_budget_room(), 2.0)

    def test_openai_spend_today_counts_against_the_line_and_openai_is_refused_by_it(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        self.store.add_spend("openai", 1.25)
        self.assertEqual(self.router.claude_budget_room(), 0.75)
        errors: list[str] = []
        out = self.router._ask_openai(role="architect", system="s", user="u", family=None, key="k", openai_model="gpt-6-astra",
                                      max_output=1000, effort="medium", need_usd=1.0, errors=errors)
        self.assertIsNone(out)
        self.assertIn("paid-model line", errors[0])
        self.assertEqual(self.store.spent(["openai"]), 1.25, "nothing admitted")

    def test_an_openai_hold_released_after_midnight_lifts_no_line(self):
        """OpenAI's spend counts on the day its hold was booked, as Claude's does: the true-up or the refusal of a hold
        booked before 00:00 UTC is a negative row today, and it pays for neither model's spend today."""
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        releases = ((0.4 - 3.0, {"settles": "k0"}), (-3.0, {"refused": 429, "releases": "k1"}),
                    (-3.0, {"refused": 429}))  # the last: a refusal row from before it named its hold
        for day, (usd, detail) in enumerate(releases, start=1):
            with self.subTest(detail=detail):
                midnight = NOW - NOW % DAY + day * DAY
                self.clock.t = midnight - 60
                self.store.add_spend("openai", 3.0, detail={"role": "audit", "hold": f"k{day - 1}"})
                self.clock.t = midnight + 60
                self.store.add_spend("openai", usd, detail={"role": "audit", **detail})
                self.assertLess(self.store.spent(["openai"], since=midnight), 0, "today's OpenAI rows sum under 0")
                self.assertEqual(self.router.openai_spent(since=midnight), 0.0)
                self.assertEqual(self.router.claude_budget_room(), 2.0)
                (request, _), _ = self.admit(1.5)
                self.assertIsNotNone(request)
                self.assertEqual(self.router.claude_budget_room(), 0.5, "the line less Claude's own spend today")
                (request, kind), errors = self.admit(1.0)
                self.assertEqual((request, kind), (None, "line"), "yesterday's release bought no Claude today")
                self.assertIn("research budget", errors[0])
                self.store.add_spend("openai", 0.25, detail={"role": "audit", "hold": f"today{day}"})
                self.assertEqual(self.router.claude_budget_room(), 0.25, "nor does it hide OpenAI's spend today")
        # Two calls on one key across 00:00 UTC: the older, larger hold's release meets today's hold and counts for no
        # more than it, so it hides none of today's other OpenAI spend.
        midnight = NOW - NOW % DAY + (len(releases) + 1) * DAY
        self.clock.t = midnight - 60
        self.store.add_spend("openai", 3.0, detail={"role": "audit", "hold": "same"})
        self.clock.t = midnight + 60
        self.store.add_spend("openai", 1.0, detail={"role": "audit", "hold": "same"})
        self.store.add_spend("openai", -3.0, detail={"role": "audit", "refused": 429, "releases": "same"})
        self.store.add_spend("openai", 0.5, detail={"role": "audit", "hold": "other"})
        self.assertEqual(self.router.openai_spent(since=midnight), 0.5)
        self.assertEqual(self.router.claude_budget_room(), 1.5)

    def openai(self, *, takes=0.0, **answer):
        """One `_ask_openai` call (a $1 hold) on a fake client that answers `takes` seconds after the hold is booked."""
        clock = self.clock

        class Slow(FakeFrontier):
            def ask(self, **kw):
                clock.advance(takes)
                return super().ask(**kw)

        self.router.month, self.router.frontier_factory = FakeMonth(1000), lambda model: Slow(model, **answer)
        return self.router._ask_openai(role="audit", system="s", user="u", family=None, key="k", max_output=1000,
                                       openai_model="gpt-6-astra", effort="medium", need_usd=1.0, errors=[])

    def test_an_openai_call_counts_on_its_holds_day_at_its_settled_cost(self):
        """The router's own rows: a refusal names the hold it releases, so a call refused or settled on its hold's day
        counts at its cost that day, and one answered after 00:00 UTC still counts on the day it was held."""
        from league.frontier import FrontierError

        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        refusal = FrontierError("refused", status=429)
        self.assertIsNone(self.openai(fail=refusal))
        self.assertEqual(self.store.spent(["openai"]), 0.0)
        self.assertEqual(self.router.claude_budget_room(), 2.0, "refused on its hold's own day: the line is whole again")
        self.assertEqual(self.openai(cost="0.40")["cost_usd"], 0.4)
        self.assertAlmostEqual(self.router.claude_budget_room(), 1.6, places=6, msg="settled that day: its cost")
        # Held a minute before 00:00 UTC, answered a minute after it: the release is booked on the new day.
        for day, answer in enumerate(({"cost": "0.25"}, {"fail": refusal}), start=1):
            with self.subTest(answer=answer):
                midnight = NOW - NOW % DAY + day * DAY
                self.clock.t = midnight - 60
                self.openai(takes=120.0, **answer)
                self.assertEqual(self.clock(), midnight + 60)
                self.assertLess(self.store.spent(["openai"], since=midnight), 0, "held yesterday, released today")
                self.assertEqual(self.router.claude_budget_room(), 2.0)
                (request, _), _ = self.admit(0.5)
                self.assertIsNotNone(request)
                self.assertEqual(self.router.claude_budget_room(), 1.5, "the line less Claude's own spend today")
                (request, kind), errors = self.admit(1.75)
                self.assertEqual((request, kind), (None, "line"))
                self.assertIn("research budget", errors[0])

    def test_the_line_is_the_protected_rules_arithmetic(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        with mock.patch.object(B, "paid_model_room", return_value=0.42) as rule:
            self.assertEqual(self.router.claude_budget_room(), 0.42)
        rule.assert_called_once()
        with mock.patch.object(B, "paid_model_room", side_effect=RuntimeError("boom")):
            self.assertEqual(self.router.claude_budget_room(), 0.0, "a rule that cannot run is no paid research")
        self.assertIsNone(B.paid_model_room(None, 5.0))
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5), 1.5)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, float("nan")), 0.0)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 1.5, -2.6), 0.5, "each model's spend floored on its own")
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5, 0.25), 1.25)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5, float("nan")), 0.0)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5, None), 0.0)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}), 0.0, "no spend given is no room")
        # The gate's holds, for a named role, by stage: every role but the gate's two leaves both, the review the
        # audit's, the audit none; never under 0.
        self.assertEqual(round(B.paid_model_room({"claude_usd_day": 4.0}, 0.25, role="strategist"), 9), 1.8)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.25, 0.5, role="architect"), 0.0)
        self.assertEqual(round(B.paid_model_room({"claude_usd_day": 2.0}, 0.25, role="review"), 9), 0.45)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.25, role="audit"), 1.75)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, float("nan"), role="audit"), 0.0)
        self.assertIsNone(B.paid_model_room(None, 5.0, role="audit"))

    def test_a_malformed_block_is_no_claude(self):
        for bad in ({"claude_usd_day": "lots"}, {"claude_usd_day": -3}, [], "budget"):
            self.settings["budget"] = bad
            self.assertEqual(self.router.claude_room(), 0.0, bad)
            self.assertEqual(self.admit(0.01)[0], (None, "line"))

    def test_no_reading_of_the_line_is_no_room_never_no_line(self):
        """`claude_budget_room` answers a number whatever it is handed. Were it ever to answer None, that is no room for
        either paid model, at the first read and at the read inside the write transaction: never "no line, admit"."""
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        asked: list[dict] = []
        self.router.month, self.router.frontier_factory = FakeMonth(1000), lambda model: FakeFrontier(model, asked=asked)

        def unread(*first):
            reads = iter(first)  # the line as it reads first, then None for ever
            return mock.patch.object(self.router, "claude_budget_room", side_effect=lambda *role: next(reads, None))

        for first in ((), (2.0,)):
            with self.subTest(first=first):
                with unread(*first):
                    (request, kind), errors = self.admit(0.5)
                self.assertEqual((request, kind), (None, "line"))
                self.assertIn("research budget's Claude line for today has no room", errors[0])
                errors = []
                with unread(*first):
                    out = self.router._ask_openai(role="architect", system="s", user="u", family=None, key="k", max_output=1000,
                                                  openai_model="gpt-6-astra", effort="medium", need_usd=1.0, errors=errors)
                self.assertIsNone(out)
                self.assertEqual(["paid-model line" in e for e in errors], [] if first else [True])
        with unread():
            self.assertEqual(self.router.claude_room(), 0.0)
        self.assertEqual(asked, [], "no call was sent")
        self.assertEqual((self.store.spent(["claude"]), self.store.spent(["openai"])), (0.0, 0.0), "and no hold was booked")
        self.assertIsNotNone(self.admit(0.5)[0][0], "the same call is admitted once the line reads")
        self.assertEqual(self.openai()["route"], "openai")


class OwnRead(unittest.TestCase):
    """The protected budget does not rest on the scheduler lane passing the block: the Sail guard and the router read
    the store root's budget.json themselves when the settings carry none, and every Swarm step's settings carry it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def test_the_guard_reads_the_budget_itself_without_a_block(self):
        from league.swarm.guard import budget_caps

        settings = {"guard": {"house_burn_usd_day": 1.0}}
        self.assertEqual(budget_caps(settings, self.root, NOW)["research"], B.floor_usd_day("sail"))
        (self.root / "budget.json").write_text(json.dumps({"schema": B.SCHEMA, "at": NOW - 60, "meters": {
            "sail": {"research_usd_day": 0.0}, "claude": {"research_usd_day": 0.0}}}))
        caps = budget_caps(settings, self.root, NOW)
        self.assertEqual(caps["research"], 0.0, "a budget of 0 on disk is 0, not the floor")
        self.assertIn("own read", caps["source"])

    def test_every_swarm_step_carries_the_budget_block(self):
        from league.swarm.loop import Swarm
        from league.tests import test_swarm_loop as L

        case = L.LoopCase("run")
        case.setUp()
        self.addCleanup(case.doCleanups)
        sw = Swarm(case.root, settings=case.settings, config={}, store=case.store, router=case.router, pool=case.pool,
                   sleep=lambda s: None)
        self.assertIs(sw.guard.settings, sw.settings, "the guard reads the Swarm's own settings dict")
        sw.guard = case.guard
        sw.step()
        self.assertIn("budget", sw.settings)
        self.assertEqual(sw.settings["budget"]["source"], "floor")
        self.assertEqual(sw.settings["guard"]["openai_cap_usd"], 0.0)
        self.assertGreater(sw.settings["population"]["ceiling"], sw.settings["population"]["floor"])


class Edge(unittest.TestCase):
    def test_sessions_are_counted_from_the_first_monday(self):
        self.assertEqual(B.edge_state(at(2026, 10, 5, 19, 0), [])["sessions"], 0, "before Monday's close")
        self.assertEqual(B.edge_state(at(2026, 10, 5, 21, 0), [])["sessions"], 1)
        self.assertEqual(B.edge_state(at(2026, 10, 12, 21, 0), [])["sessions"], 6)

    def test_sixty_sessions_without_a_promotion_stop_the_profit_share(self):
        before = B.edge_state(at(2026, 12, 28, 22, 0), [])
        self.assertEqual((before["sessions"], before["stop"]), (59, False))
        after = B.edge_state(at(2026, 12, 29, 21, 30), [])
        self.assertEqual((after["sessions"], after["stop"]), (60, True), "Thanksgiving and Christmas are not sessions")
        self.assertIn("no forward edge", after["why"])

    def test_a_promotion_lifts_it_and_restarts_the_count(self):
        lifted = B.edge_state(at(2026, 12, 29, 21, 30), [at(2026, 10, 9, 15, 0), at(2026, 12, 1, 15, 0)])
        self.assertEqual((lifted["anchor"], lifted["stop"]), ("2026-12-02", False))
        self.assertEqual(lifted["sessions"], 19)

    def test_an_unreadable_record_counts_as_none(self):
        out = B.edge_state(at(2026, 12, 29, 21, 30), None)
        self.assertTrue(out["stop"])
        self.assertIn("could not be read", out["why"])


class FakeSail:
    def __init__(self, per_day=None, fail=False):
        self.per_day = per_day or {"sb_house": 1.2, "sb_data": 0.3}
        self.fail = fail
        self.calls = []

    def spend(self, *, sailbox=None, since=None, until=None, app=None):
        self.calls.append((sailbox, since, until))
        if self.fail:
            raise OSError("sail is down")
        return {"estimated_total_cost_usd_nanos": int(self.per_day[sailbox] * 7 * 1e9)}


class Job(unittest.TestCase):
    """`run(ctx)` end to end over a state root of fakes."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.clock = Clock(NOW)
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"braked": False, "last": {"balance": 600.0, "at": NOW - 120}})
        self.clock.t = NOW - 2 * DAY
        store.add_spend("sail_model", 9.0)
        store.add_spend("gym_box", 12.0)
        store.add_spend("claude", 7.0)
        self.clock.t = NOW - 9 * DAY
        store.add_spend("claude", 500.0)  # outside the need window
        self.clock.t = NOW
        store.close()
        (self.root / "data").mkdir()
        (self.root / "data" / "data_box.json").write_text(json.dumps({"box_id": "sb_data"}))
        self.book([(1, 50.0, NOW - 6 * DAY, NOW - 5 * DAY), (2, -10.0, NOW - 3 * DAY, NOW - 2 * DAY),
                   (3, 400.0, NOW - 41 * DAY, NOW - 40 * DAY), (4, 99.0, at(2026, 9, 25), at(2026, 9, 27))])
        (self.root / "publish.json").write_text(json.dumps({"activity": {"reading": {"fees_by_pid": {"1": "-0.02", "3": "-1"}}}}))
        self.sent: list[dict] = []
        self.answer = {"sent": True}
        self.health = {"claude": {"cap_usd": 400, "spent_usd": 185, "inflight_usd": 10, "configured": True}}
        self.alerts: list[tuple[str, str]] = []
        self.sail = FakeSail()

    def book(self, rows, *, qty=0):
        from league.live.state import LiveState

        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        for pid, cash, opened, closed in rows:
            state.db.execute(
                "INSERT INTO positions(pid, instance, family, type, root, legs, qty, opened_qty, entry, max_loss_share, "
                "collateral, fees, cash, opened_at, opened_day, opened_minute, status, closed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, "i", "f", "debit_vertical", "SPY", "[]", qty, 1, 1.0, 0.1, 0.0, 0.1, cash, opened, "d", 0, "closed", closed))
        state.close()

    def ctx(self, **kw):
        return {"root": self.root, "now": kw.get("now", NOW), "config": {"backup": {"box_id": "sb_house"}},
                "sail": kw.get("sail", self.sail), "gateway_health": kw.get("health", lambda: self.health),
                "notify": kw.get("notify", self.notify), "alert": lambda level, text: self.alerts.append((level, text))}

    def notify(self, facts):
        self.sent.append(dict(facts))
        return self.answer

    def doc(self):
        return json.loads((self.root / "budget.json").read_text())

    def test_the_day_is_computed_from_the_houses_own_reads(self):
        from league.ops import economics
        # A clean day: the close economics ran and reads what the book reads (no summary yet is said, as a warning).
        with mock.patch.object(economics, "latest", lambda root: self.summary("39.98")):
            receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["inputs"]["p30_usd"], 39.98, "50 - 0.02 + (-10): the 40-day and pre-basis closes are out")
        self.assertIn("the live book", doc["inputs"]["p30_source"])
        self.assertAlmostEqual(doc["earned_usd_day"], 0.5 * 39.98 / 30, places=4)
        sail, claude = doc["inputs"]["meters"]["sail"], doc["inputs"]["meters"]["claude"]
        self.assertEqual((sail["balance_usd"], sail["fixed_usd_day"], sail["need_usd"]), (600.0, 1.5, 21.0))
        self.assertEqual((sail["reserve_usd"], doc["meters"]["sail"]["reserve_usd"], doc["meters"]["claude"]["reserve_usd"]),
                         (GUARD["release"], 37.0, 5.0), "Sail's reserve is the Sail guard's release line; Claude's the rule's")
        self.assertIn("the Sail guard's release line", sail["reserve_source"])
        # 400 - 185: the gateway's spent_usd already holds the 10 in flight, so it is not subtracted twice.
        self.assertEqual((claude["balance_usd"], claude["need_usd"]), (215.0, 7.0), "cap - spent: the holds are in spent")
        self.assertEqual(sorted(c[0] for c in self.sail.calls), ["sb_data", "sb_house"])
        self.assertEqual(doc["meters"]["sail"]["need_share"], 0.75)
        self.assertEqual(receipt["errors"], [])
        self.assertEqual(self.alerts, [], "a clean day raises nothing")
        self.assertEqual(self.sent, [], "no meter is short")
        block, why = B.read(self.root, NOW + 3600)  # what the next settings.load reads
        self.assertIsNone(why)
        self.assertEqual(block["sail_usd_day"], doc["meters"]["sail"]["research_usd_day"])
        self.assertEqual(block["fixed_sail_usd_day"], 1.5)

    def test_sails_reserve_is_the_sail_guards_own_release_line(self):
        """Read from the guard's own arithmetic over the settings the swarm runs on (`guard.house_line`), so the rule's
        zero point follows the guard's line wherever the operator puts it, and is never under the rule's least."""
        def reserve(guard=None):
            (self.root / "swarm.json").write_text(json.dumps({"guard": guard or {}}))
            B.run(self.ctx())
            return self.doc()["meters"]["sail"]["reserve_usd"]

        self.assertEqual(reserve(), 37.0, "2 x 1.00 + 30 + 5")
        self.assertEqual(reserve({"margin_usd": 50.0}), 57.0)
        self.assertEqual(reserve({"house_burn_usd_day": 3.0, "release_margin_usd": 10.0}), 46.0)
        self.assertEqual(reserve({"house_burn_usd_day": 1.0, "measured_burn": True}), 38.0,
                         "a guard on the measured burn: Sail's fixed cost of 1.50 a day is the House's burn")
        self.assertEqual(reserve({"house_burn_usd_day": 0.0, "margin_usd": 0.0, "release_margin_usd": 0.0}), B.RESERVE_USD["sail"],
                         "never under the rule's least")
        for cfg in ({}, {"margin_usd": 50.0}, {"house_burn_usd_day": 3.0, "measured_burn": True}):
            fixed = 4.0
            lines = house_line(cfg, fixed if cfg.get("measured_burn") else 0.0)
            self.assertEqual(B._sail_reserve(cfg, fixed, []), (lines["release"], "the Sail guard's release line "
                                                                                  "(league/swarm/guard.py house_line)"))
        # A line that cannot be read is no Sail research (unknown is never money), and the job says so.
        errors: list[str] = []
        self.assertEqual(B._sail_reserve({"margin_usd": "lots"}, 1.0, errors), (None, "the Sail guard's line could not be read"))
        self.assertEqual(errors, ["Sail's reserve: the Sail guard's line could not be read: no Sail research"])
        with mock.patch.object(B, "_sail_reserve", side_effect=lambda cfg, fixed, errors: (
                errors.append("Sail's reserve: the Sail guard's line could not be read: no Sail research")
                or (None, "the Sail guard's line could not be read"))):
            receipt = B.run(self.ctx(now=NOW + DAY))
        sail = self.doc()["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["limited_by"], sail["reserve_usd"]), (0.0, "unreadable", None))
        self.assertTrue(any("Sail's reserve" in e for e in receipt["errors"]))

    def test_the_jobs_second_run_of_a_utc_day_keeps_the_days_cap(self):
        """The job as scheduled on a session day: 00:30 UTC, then after the close economics. The second run reads a
        balance that has paid for the day's research; the day's cap in budget.json stays what the first run set, the
        guard's caps with it, and the receipt records what the second reading would have set."""
        morning, evening = at(2026, 10, 21, 0, 30), at(2026, 10, 21, 20, 10)
        self.reading(100.0, morning - 60)
        first = B.run(self.ctx(now=morning))
        self.assertEqual(first["meters"]["sail"], {"research_usd_day": 11.1, "would_set_usd_day": 11.1, "limited_by": "runway",
                                                   "runway_days": 5.0, "card_date": "2026-10-21", "direction": "same"},
                         "(100 - 37 - 5 x 1.5) / 5: a taper day")
        self.reading(100.0 - 9.9 - 1.2, evening - 60)  # 9.90 of research booked (under the hold line at 9.99) and the fixed cost
        second = B.run(self.ctx(now=evening))
        self.assertEqual((second["meters"]["sail"]["research_usd_day"], second["meters"]["sail"]["would_set_usd_day"]),
                         (11.1, 8.88), "today's cap stands; (88.9 - 44.5) / 5 is what this reading would have set")
        self.assertEqual((second["direction"], second["meters"]["sail"]["direction"]), ("same", "same"))
        block, _ = B.read(self.root, evening + 60)
        caps = B.sail_caps({"budget": block})
        self.assertEqual((caps["research"], caps["gate_reserve"]), (11.1, 1.11), "what the guard holds the day to")
        self.assertEqual(self.doc()["meters"]["sail"]["day_figure"]["set_at"], "2026-10-21T00:30:00Z")
        # A guard reading gone stale at the second run is no research at once; the next day's first run sets its own.
        self.reading(88.9, evening - 7 * 3600)
        self.assertEqual(B.run(self.ctx(now=evening + 600))["meters"]["sail"]["research_usd_day"], 0.0)
        self.reading(88.9, morning + DAY - 60)
        third = B.run(self.ctx(now=morning + DAY))
        self.assertEqual((third["meters"]["sail"]["research_usd_day"], third["meters"]["sail"]["would_set_usd_day"]), (8.88, 8.88))

    def account(self, name, *, start):
        """A state root of its own whose Sail meter the REAL guard reads (league/swarm/guard.py: its balance, its meter
        of the UTC day, the swarm's booked spend), beginning at 23:57 UTC of the day before `start` (00:00 UTC) with
        $100.00 on Sail. Returns (root, store, clock, check): `check(balance)` is one guard reading at the clock's time."""
        root = self.root / name
        root.mkdir()
        clock = Clock(start - 180)
        store = SwarmStore(root, clock=clock)
        self.addCleanup(store.close)
        settings = copy.deepcopy(S.DEFAULTS)
        settings["budget"] = {"source": "budget.json", "sail_usd_day": 12.0, "claude_usd_day": 8.0, "fixed_sail_usd_day": 1.2}
        reading = [100.0]
        guard = SailGuard(store, settings, lambda: (reading[0], 5.0), clock=clock, disk_free=lambda: 100.0 * 2 ** 30)

        def check(balance):
            reading[0] = balance
            return guard.check()
        check(100.0)
        return root, store, clock, check

    def run_at(self, root, now, claude_left):
        return B.run({**self.ctx(now=now), "root": root,
                      "gateway_health": lambda: {"claude": {"remaining_usd": claude_left, "configured": True}}})

    def test_a_late_first_run_of_the_day_sets_the_cap_a_run_at_00_30_would_have(self):
        """THE DAY'S FIRST RUN ADDS BACK WHAT THE DAY ALREADY PAID, the job end to end over the real guard's store. Two
        accounts with the same day: in one the job runs at 00:30 UTC; in the other that run was missed and the first
        run of the day is the one after the close, at 20:10 UTC, on a balance that has paid for the day so far. Both set
        the same cap for the day, on each meter."""
        day = at(2026, 10, 21)
        fixed = 1.2  # the House box's own billing a day (the fake's): Sail's fixed cost
        figures = {}
        for name, first_run in (("early", day + 1800), ("late", day + 20 * 3600 + 600)):
            root, store, clock, check = self.account(name, start=day)
            # 00:27 UTC: a first model call booked, and 27 minutes of the fixed cost.
            clock.t = day + 600
            store.add_spend("sail_model", 0.01)
            clock.t = day + 27 * 60
            check(100.0 - 0.01 - fixed * 27 / 1440)
            if name == "early":
                receipt = self.run_at(root, first_run, claude_left=40.0)
                figures[name] = {m: receipt["meters"][m]["research_usd_day"] for m in B.METERS}
                doc = json.loads((root / "budget.json").read_text())
                self.assertEqual(doc["meters"]["sail"]["added_back_usd"], 0.0325, "the half hour's own fall: 0.01 + 0.0225")
            # The day: 9.90 more of Sail research booked (the Gym's box time is booked above the provider's bill: 5.90
            # booked, 3.90 billed), 3.00 of Claude, an OpenAI row this meter does not pay, and the fixed cost to 20:07 UTC.
            clock.t = day + 15 * 3600
            store.add_spend("gym_box", 5.9)
            store.add_spend("sail_model", 4.0)
            store.add_spend("claude", 3.0, detail={"role": "audit"})
            store.add_spend("openai", 1.0, detail={"role": "architect"})
            clock.t = day + 20 * 3600 + 7 * 60
            paid = 0.01 + 3.9 + 4.0 + fixed * 1207 / 1440
            check(100.0 - paid)
            store.close()
            receipt = self.run_at(root, day + 20 * 3600 + 600, claude_left=37.0)
            doc = json.loads((root / "budget.json").read_text())
            sail, claude = doc["meters"]["sail"], doc["meters"]["claude"]
            if name == "early":  # its second run of the day: the figure stands, nothing is added back
                self.assertEqual((sail["added_back_usd"], claude["added_back_usd"]), (0.0, 0.0))
                self.assertEqual((sail["would_set_usd_day"], claude["would_set_usd_day"]), (9.6168, 6.4),
                                 "the reading as it stands: (91.084 - 43) / 5 and (37 - 5) / 5")
                self.assertEqual(sail["day_figure"]["set_at"], "2026-10-21T00:30:00Z")
            else:
                figures[name] = {m: receipt["meters"][m]["research_usd_day"] for m in B.METERS}
                given = doc["inputs"]["meters"]
                self.assertEqual((given["sail"]["paid_today_usd"], given["claude"]["paid_today_usd"]), (round(paid, 4), 3.0))
                self.assertEqual(given["sail"]["paid_today_source"], f"the Sail guard's meter today ({paid:.4f}), at most the "
                                 "booked research (9.9100) and a day of fixed cost")
                self.assertEqual((sail["added_back_usd"], claude["added_back_usd"]), (round(paid, 4), 3.0))
                self.assertEqual(sail["day_figure"]["set_at"], "2026-10-21T20:10:00Z")
            # What the guard holds the day to: over the 9.91 booked and over its hold line, so nothing brakes or holds.
            caps = B.sail_caps({"budget": B.read(root, day + 20 * 3600 + 660)[0]})
            self.assertEqual((caps["research"], caps["gate_reserve"]), (11.4, 1.14), name)
            self.assertLess(9.91, caps["research"] - caps["gate_reserve"], name)
        self.assertEqual(figures["late"], figures["early"], "the same day's cap, whenever the first run comes")
        self.assertEqual(figures["early"], {"sail": 11.4, "claude": 7.0}, "(100 - 37 - 5 x 1.2) / 5 and (40 - 5) / 5")

    def test_what_the_day_paid_is_read_from_the_guards_meter_and_bounded_by_what_was_booked(self):
        """What a first run adds back is never more than the meter really fell today, and never more than the day booked
        (with a day of fixed cost): unknown is nothing added."""
        day = at(2026, 10, 21)
        now = day + 20 * 3600
        rows = [("gym_box", day + 3600, 5.0), ("sail_model", day + 7200, 2.0), ("claude", day + 7200, 3.0),
                ("claude", day + 9000, -0.5), ("sail_model", day + 19 * 3600 + 1800, 4.0)]

        def swarm(spent, meter_day="2026-10-21"):
            return {"metered_today": {"day": meter_day, "spent": spent}, "today": rows}
        paid = lambda reads, read_at=now - 3600, fixed=1.0: B._sail_paid_today(reads, read_at, now, fixed)[0]  # noqa: E731
        # The guard's own meter (the provider's dollars: the Gym's booked box time is an estimate above the bill).
        self.assertEqual(paid(swarm(5.5)), 5.5, "under the 7.00 booked by the reading at 19:00 and a day of fixed cost")
        # A guard that did not read across midnight meters the hours before it into today: the booked research bounds it.
        self.assertEqual(paid(swarm(60.0)), 8.0, "7.00 booked by the reading + 1.00: the row booked after the reading is out")
        self.assertEqual(paid(swarm(60.0), read_at=now), 12.0, "11.00 booked + 1.00")
        self.assertEqual(paid(swarm(60.0), fixed=2.5), 9.5)
        # A reading from before 00:00 UTC has paid for nothing of today; no meter of today is nothing known.
        self.assertEqual(B._sail_paid_today(swarm(5.5), day - 60, now, 1.0),
                         (0.0, "no reading of today: nothing added back"))
        self.assertEqual(B._sail_paid_today(swarm(5.5), None, now, 1.0)[0], 0.0)
        for reads in (swarm(5.5, meter_day="2026-10-20"), swarm("lots"), swarm(-1.0), swarm(None), {"metered_today": None},
                      {"metered_today": "meter", "today": rows}, {}):
            self.assertEqual(B._sail_paid_today(reads, now - 3600, now, 1.0),
                             (0.0, "the Sail guard kept no meter of today: nothing added back"), reads.get("metered_today"))
        # Claude: the swarm's own Claude rows of today (a true-up included), never OpenAI's, never under 0.
        self.assertEqual(B._claude_paid_today(swarm(0.0), now), (2.5, "the swarm's Claude spend booked today"))
        self.assertEqual(B._claude_paid_today({"today": [("claude", day + 60, -4.0), ("openai", day + 60, 9.0)]}, now)[0], 0.0,
                         "a release of yesterday's hold is no spend under 0")
        self.assertEqual(B._claude_paid_today({}, now)[0], 0.0)
        self.assertEqual(B._booked_today([("claude", "soon", 1.0), ("claude", day + 60, "lots"), ("claude",), None,
                                          ("claude", day - 1, 5.0), ("claude", now + 1, 5.0), ("claude", day, 0.25)],
                                         ("claude",), now, now), 0.25, "rows that do not read, and rows of another day, are out")
        # The production reader: the store's own meter of the day and its rows since 00:00 UTC, read-only.
        clock = Clock(day - 3600)
        store = SwarmStore(self.root, clock=clock)
        store.add_spend("gym_box", 9.0)  # the day before
        clock.t = day + 3600
        store.add_spend("gym_box", 5.0)
        store.add_spend("claude", 3.0)
        store.add_spend("openai", 1.0)
        store.put("metered_today", {"day": "2026-10-21", "spent": 4.2})
        store.close()
        reads = B._swarm_reads(self.root, now, [])
        self.assertEqual((reads["metered_today"], sorted(reads["today"])),
                         ({"day": "2026-10-21", "spent": 4.2}, [("claude", day + 3600, 3.0), ("gym_box", day + 3600, 5.0)]))
        (self.root / "swarm.sqlite").unlink()
        empty = B._swarm_reads(self.root, now, [])
        self.assertEqual((empty["metered_today"], empty["today"]), (None, []), "no store: nothing added back")

    def test_every_read_that_fails_is_closed(self):
        (self.root / "live.sqlite").unlink()
        self.book([(9, 50.0, NOW - 6 * DAY, NOW - 5 * DAY)], qty=1)  # a "closed" row still holding contracts
        receipt = B.run(self.ctx(sail=FakeSail(fail=True), health=lambda: (_ for _ in ()).throw(OSError("down"))))
        doc = self.doc()
        self.assertIsNone(doc["inputs"]["p30_usd"])
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(doc["meters"]["claude"]["research_usd_day"], 0.0)
        self.assertEqual(doc["inputs"]["meters"]["sail"]["fixed_usd_day"], 1.0, "guard.house_burn_usd_day")
        self.assertTrue(receipt["warning"])
        self.assertTrue(any("box spend" in e for e in receipt["errors"]))
        self.assertEqual(len(self.alerts), 1, "fail-closed is a House warning, not silence")
        self.assertEqual(self.alerts[0][0], "warning")
        self.assertIn("Claude's balance", self.alerts[0][1])

    def test_a_stale_guard_reading_gives_sail_no_research(self):
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": 600.0, "at": NOW - 7 * 3600}})
        store.close()
        receipt = B.run(self.ctx())
        self.assertEqual(self.doc()["meters"]["sail"]["research_usd_day"], 0.0)
        self.assertTrue(any("no fresh reading" in e for e in receipt["errors"]))
        self.assertEqual(len(self.alerts), 1)

    def test_one_failed_guard_read_before_the_job_keeps_the_last_good_balance(self):
        """The review's case: a single Sail blip just before 00:30Z must not zero the day's Sail research."""
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": None, "at": NOW - 60}, "last_good": {"balance": 600.0, "at": NOW - 240}})
        store.close()
        B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["inputs"]["meters"]["sail"]["balance_usd"], 600.0)
        self.assertIn("last good", doc["inputs"]["meters"]["sail"]["balance_source"])
        self.assertGreater(doc["meters"]["sail"]["research_usd_day"], 0.0)

    def test_a_paused_swarm_still_tells_the_owner_from_the_gateways_sail_reading(self):
        """The review's case: the swarm paused, the guard's reading goes stale while the House box burns Sail."""
        self.reading(600.0, NOW - 7 * 3600)
        self.health["sail"] = {"balance_usd": 40.0, "checked_at": B._iso(NOW - 600)}
        self.answer = {"sent": True}
        receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 0.0, "the gateway's reading is never research")
        self.assertEqual([n["meter"] for n in receipt["notices"]], ["sail"])
        self.assertEqual(self.sent[0]["balance_usd"], "40.00")
        self.health["sail"] = {"balance_usd": 40.0, "checked_at": B._iso(NOW - 8 * 3600)}
        (self.root / B.NOTICES_FILE).unlink()
        self.assertEqual(B.run(self.ctx())["notices"], [], "a stale gateway reading is no reading either")

    def economics(self, summary, *, p30=None):
        """A stand-in for league/ops/economics.py's two readers with WP2's own shapes: `latest(root)` -> the newest
        summary or None, `p30(summary, *, days=30)` -> {"usd": "<decimal>", ...}. On the module itself: it is in the
        release, so `budget._p30` finds the real one whatever `sys.modules` says."""
        from league.ops import economics

        return mock.patch.multiple(economics, latest=lambda root: summary,
                                   p30=p30 or (lambda summary, *, days=30: {"usd": summary["p30"]["usd"], "days": days}))

    def summary(self, usd="300.00", *, cutoff=NOW - 3600, **extra):
        """A close summary as far as the budget and the economics' own `p30` read it: one close day worth `usd`."""
        closes = [{"day": B._ny_day(cutoff).isoformat(), "total_usd": usd, "closed_positions": 1}]
        return {"cutoff": B._iso(cutoff), "p30": {"usd": usd}, "positions": [], "reconciliation": {"blocking": []},
                "realized": {"by_close_day": closes}, **extra}

    #: The source the budget names when the close economics (a summary cut three hours before NOW) cuts the book's read.
    CUT = f"league.ops.economics.p30 (cutoff {B._iso(NOW - 3 * 3600)}): below the live book's own read, which caps it"

    def test_the_close_economics_p30_may_cut_what_was_earned_never_raise_it(self):
        """The close economics (league/ops/economics.py) is a second source: an inflated p30 there must not lift the
        budget past the live book's own read (the D4 rule), but a smaller one (more fees found) is used."""
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: self.summary("300.00", cutoff=NOW - 3 * 3600)):
            B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
        self.assertIn("the live book", self.doc()["inputs"]["p30_source"])
        with mock.patch.object(economics, "latest", lambda root: self.summary("12.50", cutoff=NOW - 3 * 3600)):
            B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 12.5)
        self.assertEqual(self.doc()["inputs"]["p30_source"], self.CUT)

    def test_an_unreadable_book_earns_nothing_whatever_the_economics_says(self):
        from league.ops import economics
        (self.root / "live.sqlite").unlink()
        self.book([(9, 50.0, NOW - 6 * DAY, NOW - 5 * DAY)], qty=1)  # a "closed" row still holding contracts
        with mock.patch.object(economics, "latest", lambda root: self.summary("300.00", cutoff=NOW - 3 * 3600)):
            B.run(self.ctx())
        self.assertIsNone(self.doc()["inputs"]["p30_usd"])
        self.assertEqual(self.doc()["earned_usd_day"], 0.0)

    def test_a_losing_month_in_the_close_economics_is_a_number_not_a_fallback(self):
        """A negative p30 is a loss, never "no number": the book (which can read positive) does not stand in for it."""
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: self.summary("-3.10", cutoff=NOW - 3 * 3600)):
            receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual((doc["inputs"]["p30_usd"], doc["inputs"]["p30_source"]), (-3.1, self.CUT))
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(receipt["errors"], [])

    def test_a_job_that_reports_failed_is_a_failed_receipt(self):
        """The grant's refusal ({"status": "failed"}) is never recorded as ok."""
        from league.ops.__main__ import run_job

        fake = types.ModuleType("fake_grant")
        fake.run = lambda ctx: {"status": "failed", "action": "none", "error": "the digest moved with no owner deploy"}
        with mock.patch("importlib.import_module", return_value=fake):
            out = run_job("grant", root=self.root, due_at=NOW, ctx=types.SimpleNamespace(alerts=[]))
        self.assertEqual(out["status"], "failed")
        self.assertIn("the digest moved", out["error"])
        fake.run = lambda ctx: {"status": "ok", "action": "none"}
        with mock.patch("importlib.import_module", return_value=fake):
            self.assertEqual(run_job("grant", root=self.root, due_at=NOW, ctx=types.SimpleNamespace(alerts=[]))["status"], "ok")

    def test_a_stale_close_economics_falls_back_to_the_book(self):
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: self.summary("300.00", cutoff=NOW - 3 * DAY)):
            receipt = B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
        self.assertIn("the close economics is stale: the live book's own read is used", receipt["errors"])

    def test_unknown_close_economics_is_never_replaced_by_the_book(self):
        """The review's case: the economics says unknown; the book's read (+39.98 here) must not stand in for it."""
        cases = {"not a number": self.summary(usd=None),
                 "unpriced close": self.summary(positions=[{"pid": 7, "status_at_cutoff": "unpriced_close"}]),
                 "blocking": self.summary(reconciliation={"blocking": ["an expiry the book has not settled"]}),
                 "pending at the cutoff": self.summary(reconciliation={"blocking": [], "pending_orders_at_cutoff": [3]}),
                 # A summary too malformed to inspect (its positions are no list) is unknown, not a crashed job.
                 "malformed": self.summary(positions=7)}
        for name, summary in cases.items():
            self.alerts.clear()
            with self.economics(summary):
                B.run(self.ctx())
            self.assertIsNone(self.doc()["inputs"]["p30_usd"], name)
            self.assertEqual(self.doc()["earned_usd_day"], 0.0, name)
            self.assertEqual(len(self.alerts), 1, name)
        with self.economics(self.summary(), p30=lambda summary, *, days=30: (_ for _ in ()).throw(KeyError("cutoff"))):
            B.run(self.ctx())
        self.assertIsNone(self.doc()["inputs"]["p30_usd"], "a p30 that raises is unknown, not the book")

    def test_no_fresh_summary_falls_back_to_the_book_and_says_so(self):
        for summary in (None, self.summary(cutoff=NOW - 5 * DAY)):
            with self.economics(summary):
                receipt = B.run(self.ctx())
            self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
            self.assertTrue(any("live book's own read is used" in e for e in receipt["errors"]))
        # Monday 00:30Z: Friday's close is still the latest (counted in sessions, not hours). Its 12.50 is under the
        # book's 39.98, so it is the number (a larger one would be capped by the book and show nothing).
        with self.economics(self.summary("12.50", cutoff=at(2026, 10, 16, 20, 10))):
            B.run(self.ctx(now=at(2026, 10, 19, 0, 30)))
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 12.5, "a weekend's summary is still read")
        self.assertTrue(B.economics_fresh(at(2026, 10, 16, 20, 10), at(2026, 10, 20, 0, 30)) is False,
                        "Monday's close came and went: Friday's summary is stale")

    def test_a_fresh_summary_without_its_closes_by_day_is_unknown_and_says_so(self):
        """`realized.by_close_day` is the list the economics' own p30 sums. A fresh summary without it would read 0.00
        from nothing: it is unknown (never that 0.00, never the book's +39.98), and the job says so."""
        from league.ops import economics
        said = "the close economics' summary holds no closes by day (realized.by_close_day): p30 is unknown"
        shapes = {"no realized": None, "no by_close_day": {}, "a null": {"by_close_day": None},
                  "not a list": {"by_close_day": {}}}
        for name, realized in shapes.items():
            self.alerts.clear()
            summary = self.summary("12.50", cutoff=NOW - 3 * 3600, realized=realized)
            self.assertEqual(economics.p30(summary)["usd"], "0.00", f"{name}: what the economics' p30 makes of it")
            with mock.patch.object(economics, "latest", lambda root: summary):
                receipt = B.run(self.ctx())
            doc = self.doc()
            self.assertEqual((doc["inputs"]["p30_usd"], doc["inputs"]["p30_source"]), (None, said), name)
            self.assertEqual(doc["earned_usd_day"], 0.0, name)
            self.assertEqual(receipt["errors"], [said], name)
            self.assertEqual(len(self.alerts), 1, name)
        quiet = self.summary("12.50", cutoff=NOW - 3 * 3600, realized={"by_close_day": []})
        with mock.patch.object(economics, "latest", lambda root: quiet):
            receipt = B.run(self.ctx())
        self.assertEqual((self.doc()["inputs"]["p30_usd"], receipt["errors"]), (0.0, []), "no closes in the window is a number")

    def test_a_close_summary_that_is_not_a_summary_is_said_and_the_book_stands(self):
        """`economics.latest` answering anything but a summary or None is never passed over in silence."""
        from league.ops import economics
        for summary in (["2026-10-20"], "summary.json", 0, False):
            self.alerts.clear()
            with mock.patch.object(economics, "latest", lambda root: summary):
                receipt = B.run(self.ctx())
            self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98, repr(summary))
            self.assertIn("the live book", self.doc()["inputs"]["p30_source"])
            self.assertEqual(receipt["errors"], [f"the close economics' summary is not a mapping ({type(summary).__name__}): "
                                                 "the live book's own read is used"], repr(summary))
            self.assertEqual(len(self.alerts), 1, repr(summary))
        with mock.patch.object(economics, "latest", side_effect=OSError("gone")):
            receipt = B.run(self.ctx())
        self.assertEqual(receipt["errors"], ["the close economics could not be read (OSError): the live book's own read is used"],
                         "a read that failed is said once")

    def test_the_books_own_read_is_unknown_on_what_profit_calls_unknown(self):
        """The review's case: an expired structure closed at the venue but not priced (unpriced_close, a real -80) must
        not leave +60 of other closes to fund research."""
        from league.live.state import LiveState

        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        state.db.execute("UPDATE positions SET status='unpriced_close', closed_at=NULL WHERE pid=2")
        state.close()
        value, why = B.book_p30(self.root, NOW)
        self.assertIsNone(value)
        self.assertIn("unpriced_close", why)
        B.run(self.ctx())
        self.assertIsNone(self.doc()["inputs"]["p30_usd"])
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        state.db.execute("UPDATE positions SET status='closed', closed_at=? WHERE pid=2", (NOW - 2 * DAY,))
        state.db.execute("INSERT INTO kv(key, value) VALUES('recon', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (json.dumps({"frozen": "a fill the venue does not show"}),))
        state.close()
        self.assertEqual(B.book_p30(self.root, NOW), (None, "reconciliation is frozen: p30 is unknown"))
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        state.db.execute("DELETE FROM kv WHERE key='recon'")
        state.close()
        self.assertEqual(B.book_p30(self.root, NOW)[0], 39.98)
        (self.root / "publish.json").write_text(json.dumps({"activity": {"reading": {"fees_by_pid": {}, "blocking": ["x"]}}}))
        self.assertIsNone(B.book_p30(self.root, NOW)[0], "a blocking account reading is unknown")

    def look(self, family, *, passed, at_, sha=None):
        """A holdout look in the swarm's own record, as the gate writes it (`SwarmStore.add_look`)."""
        store = SwarmStore(self.root, clock=Clock(at_))
        store.add_look(family, 1, sha or f"sha-{family}-{at_}", passed=passed, p_value=0.01 if passed else 0.6, detail={})
        store.close()

    def band(self, family, band_from, band_to, at_, reason="passed the holdout and trades a real type that fits the Probe's cap"):
        store = SwarmStore(self.root, clock=Clock(at_))
        store.event("swarm.band", family, {"band_from": band_from, "band_to": band_to, "reason": reason})
        store.close()

    def test_a_probe_earned_by_a_passed_look_is_forward_edge(self):
        """The fast lane: a passed look makes a Candidate and the Money table moves it to Probe. That Probe lifts the
        no-forward-edge stop as a ladder promotion does, at the move's own time, once a look."""
        late = at(2026, 12, 29, 21, 30)

        def stop():
            errors: list[str] = []
            reads = B._swarm_reads(self.root, late, errors)
            B.run(self.ctx(now=late))
            edge = self.doc()["inputs"]["edge"]
            return reads["probes"], reads["promotions"], edge["anchor"], edge["stop"]

        self.assertEqual(stop(), ([], [], "2026-10-05", True), "sixty sessions and no Probe")
        # A move to Probe with no passed look behind it is none: no look at all, a failed look, another family's look,
        # a look that came after the move.
        self.band("f1", "candidate", "probe", at(2026, 11, 2, 15, 0))
        self.look("f2", passed=False, at_=at(2026, 11, 3, 14, 0))
        self.band("f2", "candidate", "probe", at(2026, 11, 3, 15, 0))
        self.look("other", passed=True, at_=at(2026, 11, 4, 14, 0))
        self.band("f3", "candidate", "probe", at(2026, 11, 4, 15, 0))
        self.band("f4", "candidate", "probe", at(2026, 11, 5, 15, 0))
        self.look("f4", passed=True, at_=at(2026, 11, 5, 16, 0))
        self.assertEqual(stop(), ([], [], "2026-10-05", True))
        # The passed look, then the Money table's move: the Probe that look earned.
        self.look("f5", passed=True, at_=at(2026, 12, 1, 14, 0))
        self.band("f5", "gym", "candidate", at(2026, 12, 1, 14, 0), reason="passed its holdout look")
        self.assertEqual(stop(), ([], [], "2026-10-05", True), "a Candidate is shadow only: no Probe yet")
        self.band("f5", "candidate", "probe", at(2026, 12, 1, 15, 0))
        self.assertEqual(stop(), ([at(2026, 12, 1, 15, 0)], [], "2026-12-02", False))
        doc = self.doc()
        self.assertIs(doc["no_forward_edge"], False)
        self.assertNotIn("no forward edge", doc["state"])
        self.assertEqual(doc["inputs"]["edge"]["sessions"], 19)
        # Sizing up, a demotion back to Probe and a return to Probe on the same look are no new Probe.
        self.band("f5", "probe", "sized", at(2026, 12, 8, 15, 0), reason="sized")
        self.band("f5", "sized", "probe", at(2026, 12, 9, 15, 0), reason="its real trades lose")
        self.band("f5", "probe", "candidate", at(2026, 12, 10, 15, 0), reason="its type no longer fits the Probe's cap")
        self.band("f5", "candidate", "probe", at(2026, 12, 11, 15, 0))
        self.assertEqual(stop()[0::2], ([at(2026, 12, 1, 15, 0)], "2026-12-02"), "one Probe a passed look")
        # A second passed look of the family (a new version) earns its own Probe, at its own move.
        self.look("f5", passed=True, at_=at(2026, 12, 14, 14, 0), sha="sha-f5-v2")
        self.band("f5", "probe", "candidate", at(2026, 12, 14, 14, 30), reason="a new version")
        self.band("f5", "candidate", "probe", at(2026, 12, 14, 15, 0))
        self.assertEqual(stop(), ([at(2026, 12, 1, 15, 0), at(2026, 12, 14, 15, 0)], [], "2026-12-15", False))
        # The look's Probes are the swarm's own record: they stand when the ladder's cannot be read, and the job says so.
        (self.root / "observe.sqlite").write_bytes(b"not a database")
        probes, promotions, anchor, stopped = stop()
        self.assertEqual((probes, promotions, anchor, stopped), ([at(2026, 12, 1, 15, 0), at(2026, 12, 14, 15, 0)], None,
                                                                 "2026-12-15", False))
        edge = self.doc()["inputs"]["edge"]
        self.assertIs(edge["promotions_readable"], False)
        self.assertIn("the ladder's record could not be read", edge["why"])

    def test_a_demotion_from_sized_is_no_looks_probe_even_with_a_passed_look_behind_it(self):
        """The ladder put the family at Probe (its receipt), it was sized up, a look of it passed meanwhile, and the Money
        table demoted it from Sized: a move to Probe from Sized is no Probe a look earned, whatever looks stand."""
        import sqlite3

        db = sqlite3.connect(self.root / "observe.sqlite")
        db.execute("CREATE TABLE ladder_decisions (id INTEGER PRIMARY KEY, day TEXT, family TEXT, version INTEGER, "
                   "verdict TEXT NOT NULL, at REAL NOT NULL)")
        db.execute("INSERT INTO ladder_decisions VALUES (7, '2026-11-10', 'lad', 1, 'promote', ?)", (at(2026, 11, 10, 21, 0),))
        db.commit()
        db.close()
        self.band("lad", "gym", "probe", at(2026, 11, 10, 21, 1), reason="the forward ladder promoted it (practice receipt 7)")
        self.band("lad", "probe", "sized", at(2026, 11, 17, 15, 0), reason="sized")
        self.look("lad", passed=True, at_=at(2026, 11, 18, 14, 0))
        self.band("lad", "sized", "probe", at(2026, 11, 19, 15, 0), reason="its real trades lose")
        reads = B._swarm_reads(self.root, at(2026, 12, 29, 21, 30), [])
        self.assertEqual((reads["probes"], reads["promotions"]), ([], [at(2026, 11, 10, 21, 1)]))

    def test_two_passed_looks_before_one_move_are_one_probe_and_a_return_is_none(self):
        """Two passed looks of a family stand before its first move to Probe: that move answers both, so a later return to
        Probe with no new look is no new Probe."""
        self.look("f", passed=True, at_=at(2026, 11, 2, 14, 0), sha="a")
        self.look("f", passed=True, at_=at(2026, 11, 3, 14, 0), sha="b")
        self.band("f", "candidate", "probe", at(2026, 11, 4, 15, 0))
        self.band("f", "probe", "candidate", at(2026, 11, 5, 15, 0), reason="its type no longer fits the Probe's cap")
        self.band("f", "candidate", "probe", at(2026, 11, 6, 15, 0))
        self.assertEqual(B._swarm_reads(self.root, at(2026, 12, 29, 21, 30), [])["probes"], [at(2026, 11, 4, 15, 0)])

    def test_a_ladder_promotion_and_a_looks_probe_both_count_and_the_later_one_anchors(self):
        import sqlite3

        db = sqlite3.connect(self.root / "observe.sqlite")
        db.execute("CREATE TABLE ladder_decisions (id INTEGER PRIMARY KEY, day TEXT, family TEXT, version INTEGER, "
                   "verdict TEXT NOT NULL, at REAL NOT NULL)")
        db.execute("INSERT INTO ladder_decisions(id, day, family, version, verdict, at) VALUES (7, '2026-11-10', 'lad', 1, "
                   "'promote', ?)", (at(2026, 11, 10, 21, 0),))
        db.commit()
        db.close()
        self.band("lad", "gym", "probe", at(2026, 11, 10, 21, 1), reason="the forward ladder promoted it (practice receipt 7)")
        self.look("fast", passed=True, at_=at(2026, 11, 20, 14, 0))
        self.band("fast", "candidate", "probe", at(2026, 11, 20, 15, 0))
        errors: list[str] = []
        reads = B._swarm_reads(self.root, at(2026, 12, 29, 21, 30), errors)
        self.assertEqual((reads["promotions"], reads["probes"], errors), ([at(2026, 11, 10, 21, 1)], [at(2026, 11, 20, 15, 0)], []))
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        self.assertEqual(self.doc()["inputs"]["edge"]["anchor"], "2026-11-21")
        # The ladder's own move is never also a look's Probe, whatever looks its family holds.
        self.look("lad", passed=True, at_=at(2026, 11, 9, 14, 0))
        self.assertEqual(B._swarm_reads(self.root, at(2026, 12, 29, 21, 30), errors)["probes"], [at(2026, 11, 20, 15, 0)])

    def test_a_move_to_probe_with_no_receipt_and_no_passed_look_lifts_nothing(self):
        store = SwarmStore(self.root, clock=Clock(at(2026, 12, 1, 15, 0)))
        # The Money table's own moves with no passed look in the swarm's record (and a demotion from Sized) are no
        # promotion: the look's Probe is `test_a_probe_earned_by_a_passed_look_is_forward_edge`.
        store.event("swarm.band", "f1", {"band_from": "candidate", "band_to": "probe", "reason": "holdout pass"})
        store.event("swarm.band", "f2", {"band_from": "sized", "band_to": "probe", "reason": "demoted"})
        store.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        edge = self.doc()["inputs"]["edge"]
        self.assertEqual((edge["anchor"], edge["stop"]), ("2026-10-05", True))
        store = SwarmStore(self.root, clock=Clock(at(2026, 12, 1, 15, 0)))
        store.event("swarm.band", "f3", {"band_from": "gym", "band_to": "probe",
                                         "reason": "the forward ladder promoted it (practice receipt 12)"})
        store.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        edge = self.doc()["inputs"]["edge"]
        self.assertEqual((edge["anchor"], edge["stop"]), ("2026-12-02", False))

    def test_a_ladder_decision_to_promote_counts_too(self):
        import sqlite3

        db = sqlite3.connect(self.root / "observe.sqlite")
        db.execute("CREATE TABLE ladder_decisions (id INTEGER PRIMARY KEY, day TEXT, family TEXT, version INTEGER, "
                   "verdict TEXT NOT NULL, at REAL NOT NULL)")
        db.executemany("INSERT INTO ladder_decisions(day, family, version, verdict, at) VALUES (?,?,?,?,?)",
                       [("2026-11-30", "f1", 1, "would_promote", at(2026, 11, 30, 21, 0)),
                        ("2026-12-01", "f2", 1, "promote", at(2026, 12, 1, 21, 0)),
                        ("2026-12-02", "f3", 1, "blocked", at(2026, 12, 2, 21, 0))])
        db.commit()
        db.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        self.assertEqual(self.doc()["inputs"]["edge"]["anchor"], "2026-12-02")

    def reading(self, balance, at_):
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": balance, "at": at_}})
        store.close()

    def test_a_short_meter_is_told_once_a_week_and_only_when_sent(self):
        self.reading(60.0, NOW - 60)
        self.answer = {"sent": False, "reason": "no mail binding"}
        receipt = B.run(self.ctx())
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(receipt["notices"][0]["sent"])
        facts = self.sent[0]
        self.assertEqual(facts["kind"], "funding")
        self.assertEqual(facts["notice_id"], "funding:sail:2026-W43:r2", "the meter, the ISO week and the rule's version")
        # At the rate it wants: 1.5 fixed + its 15 of the ceiling (the 39.98 of profit is inside the ceiling): 23 above
        # the reserve (the Sail guard's release line, 37) is 1.4 days of research left at the ceiling.
        self.assertEqual((facts["meter"], facts["balance_usd"], facts["usd_day"], facts["research_usd_day"], facts["runway_days"]),
                         ("sail", "60.00", "16.50", "15.00", "1.4"))
        # At the rate the rule holds it to now: tapered to (23 - 5 x 1.5) / 5 a day, which keeps 5 days.
        self.assertEqual((facts["current_usd_day"], facts["current_research_usd_day"], facts["current_runway_days"]),
                         ("4.60", "3.10", "5.0"))
        # What buys 7 more days at the ceiling, the line it is under, and the day the taper starts (it has).
        self.assertEqual((facts["topup_usd"], facts["topup_days"], facts["card_line_days"], facts["card_date"]),
                         ("115.50", 7, 7, "2026-10-20"))
        # The same amount and days under rule version 1's names: a gateway still on that rule's composer (it is its own
        # deploy, and a House rollback does not take it back) reads only those, and must never mail "add unknown".
        self.assertEqual((facts["restore_usd"], facts["restore_days"]), (facts["topup_usd"], facts["topup_days"]))
        self.assertEqual(sorted(facts), sorted([
            "kind", "notice_id", "meter", "balance_usd", "usd_day", "fixed_usd_day", "research_usd_day", "runway_days",
            "runs_out_on", "current_usd_day", "current_research_usd_day", "current_runway_days", "topup_usd", "topup_days",
            "restore_usd", "restore_days", "card_line_days", "card_date", "at", "test"]),
            "no account figure beyond the balance and the rates it always said")
        self.assertIs(facts["test"], False)
        self.answer = {"sent": True}
        B.run(self.ctx(now=NOW + 3600))
        self.assertEqual(len(self.sent), 2, "not told yet: tried again")
        self.reading(59.0, NOW + 2 * DAY - 60)
        B.run(self.ctx(now=NOW + 2 * DAY))
        self.assertEqual(len(self.sent), 2, "told: at most once every 7 days")
        self.assertIn("at most once", self.doc()["notices"][0]["why"])
        self.reading(58.0, NOW + 8 * DAY - 60)
        B.run(self.ctx(now=NOW + 8 * DAY))
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(self.sent[-1]["notice_id"], "funding:sail:2026-W44:r2")

    def test_what_another_version_of_the_rule_told_is_not_this_rules_notice(self):
        """The first run after the rule's change: version 1 told this meter yesterday (its 60-day line, its amount for 90
        days). This rule's days and amount are other ones, so the owner is told again, under an id the gateway has not
        seen this week; from then on at most once every 7 days, as ever."""
        self.reading(60.0, NOW - 60)
        for record in ({"sent_at": NOW - DAY, "notice_id": "funding:sail:2026-W43"},
                       {"sent_at": NOW - DAY, "notice_id": "funding:sail:2026-W43", "rule_version": 1}):
            self.sent.clear()
            (self.root / B.NOTICES_FILE).write_text(json.dumps({"sail": record}))
            receipt = B.run(self.ctx())
            self.assertEqual([(n["meter"], n["sent"]) for n in receipt["notices"]], [("sail", True)], record)
            self.assertEqual(self.sent[0]["notice_id"], "funding:sail:2026-W43:r2")
            told = json.loads((self.root / B.NOTICES_FILE).read_text())["sail"]
            self.assertEqual((told["sent_at"], told["rule_version"]), (NOW, B.RULE_VERSION))
        B.run(self.ctx(now=NOW + 3600))
        self.assertEqual(len(self.sent), 1, "this rule's own notice: at most once every 7 days")

    def test_a_failing_gateway_is_an_error_not_a_crash(self):
        self.reading(60.0, NOW - 60)

        def down(facts):
            raise OSError("gateway down")
        receipt = B.run(self.ctx(notify=down))
        self.assertFalse(receipt["notices"][0]["sent"])
        self.assertTrue(any("funding notice" in e for e in receipt["errors"]))
        self.assertFalse((self.root / B.NOTICES_FILE).exists())

    def test_the_drill_sends_a_test_notice_and_checks_the_closed_read(self):
        out = B.drill(self.ctx(), "claude")
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["checks"]["throttled_and_still_seen"], "the production shape: Claude's fixed cost is 0")
        self.assertEqual(self.sent[-1]["test"], True)
        self.assertEqual(self.sent[-1]["notice_id"], f"funding-test:claude:2026-W43:{int(NOW // 60)}")
        self.assertEqual(self.sent[-1]["meter"], "claude")
        self.assertFalse((self.root / "budget.json").exists(), "a drill writes no budget")
        self.assertFalse((self.root / B.NOTICES_FILE).exists())
        with self.assertRaises(ValueError):
            B.drill(self.ctx(), "openai")

    def test_a_second_drill_in_the_week_has_its_own_id_and_a_duplicate_is_not_delivered(self):
        B.drill(self.ctx(), "claude")
        B.drill(self.ctx(now=NOW + 3600), "claude")
        self.assertNotEqual(self.sent[0]["notice_id"], self.sent[1]["notice_id"], "the gateway remembers ids 8 days")
        self.answer = {"sent": True, "duplicate": True}
        out = B.drill(self.ctx(), "claude")
        self.assertFalse(out["sent"], "a duplicate sent no mail: the drill proves nothing")
        self.assertFalse(out["ok"])

    def test_the_claude_balance_never_subtracts_the_holds_twice(self):
        self.assertEqual(B._claude_balance({"claude": {"cap_usd": "300", "spent_usd": "185", "inflight_usd": "10",
                                                       "remaining_usd": "115"}}), 115.0)
        self.assertEqual(B._claude_balance({"claude": {"cap_usd": 300, "spent_usd": 185, "inflight_usd": 10}}), 115.0)
        self.assertIsNone(B._claude_balance({"claude": {"configured": False}}))
        self.assertIsNone(B._claude_balance({"claude": {"cap_usd": "x", "spent_usd": 1}}))


if __name__ == "__main__":
    unittest.main()
