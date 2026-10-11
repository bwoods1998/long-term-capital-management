"""THE PANEL'S HALF-SPREADS (release E4, package B; league/ops/equity_spreads.py): D20 as formulas (a sample is the
median of a two-second window's quoted half-spreads; a name's figure the 75th percentile of its kept samples; a
sample above 100 bp dropped and counted; under eight samples the universe's figure; no file, the fallback; never
under the floor), the days and instants sampled (Train years only, 09:32:00 and 15:55:00 New York time), the job's
resumable run through the gateway, and the reader a panel lot's replay twin takes its half-spread from.

Every quote, symbol and aid here is invented; no market quote is read. Package C's `league.xs.store.Universe` is met
at its interface (league/xs/E4_INTERFACES.md 6): the job is tested on what it asks of it."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import stat
import statistics
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import store as eq_store
from league.ops import equity_spreads as SP
from league.ops.context import Context, GatewayError
from league.xs import config as xs_config
from league.xs import store as xs_store

NOW = 1_800_000_000.0
CALENDAR = eq_store.nyse_sessions(dt.date(2016, 1, 4), dt.date(2025, 12, 31))
DAYS = SP.sample_days(CALENDAR)


def utc(day: dt.date, hh: int, mm: int, ss: int = 0, micro: int = 0) -> str:
    moment = dt.datetime.combine(day, dt.time(hh, mm, ss, micro), SP.NEW_YORK).astimezone(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def quote(at: str, bid: float, ask: float) -> dict:
    return {"t": at, "bp": bid, "ap": ask, "bs": 1, "as": 1, "bx": "N", "ax": "N", "c": ["R"], "z": "A"}


class ThePercentile(unittest.TestCase):
    def test_hand_values(self):
        self.assertIsNone(SP.percentile([]))
        self.assertEqual(SP.percentile([4.0]), 4.0)
        self.assertEqual(SP.percentile([1.0, 2.0, 3.0, 4.0, 5.0]), 4.0)             # position 3
        self.assertEqual(SP.percentile([1.0, 2.0, 3.0, 4.0]), 3.25)                 # position 2.25
        self.assertEqual(SP.percentile([5.0, 1.0, 4.0, 2.0, 3.0]), 4.0)             # the order given does not matter
        self.assertEqual(SP.percentile([2.0, 10.0], 75), 8.0)
        self.assertEqual(SP.percentile([1.0, 2.0, 3.0], 50), 2.0)

    def test_it_is_numpys_linear_percentile(self):
        rng = np.random.default_rng(7)
        for n in (2, 3, 7, 8, 9, 48, 96):
            values = (rng.random(n) * 40).tolist()
            self.assertAlmostEqual(SP.percentile(values), float(np.percentile(values, 75)), places=12)


class TheSampleDays(unittest.TestCase):
    def test_eight_full_sessions_a_train_year_at_the_spec_s_indices(self):
        self.assertEqual(tuple(DAYS), xs_config.TRAIN_YEARS)
        early = {d for d, e in CALENDAR if e}
        for year, days in DAYS.items():
            rows = [d for d, _ in CALENDAR if d.year == year]
            self.assertEqual(len(days), SP.SESSIONS_YEAR)
            self.assertEqual(days, sorted(set(days)))
            self.assertFalse(early & set(days))
            for j, day in enumerate(days):
                index = math.floor(Fraction(2 * j + 1, 2) * len(rows) / SP.SESSIONS_YEAR + Fraction(1, 2))
                k = index
                while rows[k] in early:
                    k += 1
                self.assertEqual(day, rows[k], (year, j))

    def test_no_session_outside_the_train_years_is_ever_a_sample_day(self):
        years = {day.year for days in DAYS.values() for day in days}
        self.assertEqual(years, {2017, 2018, 2019, 2022, 2023, 2024})
        for sealed in (2016, 2020, 2021, 2025, 2026):
            self.assertNotIn(sealed, years)
        only_sealed = [row for row in CALENDAR if row[0].year in (2016, 2020, 2021, 2025)]
        self.assertEqual(SP.sample_days(only_sealed), {})

    def year(self, n: int, early=()) -> list[tuple[dt.date, bool]]:
        first = dt.date(2018, 1, 1)
        return [(first + dt.timedelta(days=i), i in early) for i in range(n)]

    def test_the_index_is_round_half_up_of_j_plus_a_half_times_n_over_eight(self):
        rows = self.year(16)
        self.assertEqual([rows.index((d, False)) for d in SP.sample_days(rows)[2018]], [1, 3, 5, 7, 9, 11, 13, 15])
        rows = self.year(100)
        self.assertEqual([(d - rows[0][0]).days for d in SP.sample_days(rows)[2018]], [6, 19, 31, 44, 56, 69, 81, 94])
        # n = 8: (j + 0.5) is a tie every time and goes UP; the last index is held inside the year
        rows = self.year(8)
        self.assertEqual([(d - rows[0][0]).days for d in SP.sample_days(rows)[2018]], [1, 2, 3, 4, 5, 6, 7])

    def test_a_half_day_moves_to_the_next_full_session(self):
        rows = self.year(100, early={19, 20})
        self.assertEqual([(d - rows[0][0]).days for d in SP.sample_days(rows)[2018]], [6, 21, 31, 44, 56, 69, 81, 94])
        # at the year's end there is none after it: the last full session before it
        rows = self.year(100, early={94, 95, 96, 97, 98, 99})
        self.assertEqual([(d - rows[0][0]).days for d in SP.sample_days(rows)[2018]][-1], 93)

    def test_a_year_too_short_to_sample_has_no_day(self):
        self.assertEqual(SP.sample_days(self.year(7)), {})
        self.assertEqual(SP.sample_days([]), {})


class Quotes:
    """The gateway's quotes route as the job meets it: it records every request and answers invented quotes whose
    half-spread is `bp(symbol, start)` basis points of the mid (None: a window with no quote)."""

    def __init__(self, bp=lambda symbol, start: 4.0):
        self.bp = bp
        self.calls: list[dict] = []
        self.raises = None

    def get(self, path, params=None):
        self.calls.append({"path": path, **dict(params or {})})
        if self.raises is not None:
            exc = self.raises(len(self.calls), dict(params or {}))
            if exc is not None:
                raise exc
        symbol, start = params["symbols"], params["start"]
        bp = self.bp(symbol, start)
        if bp is None:
            return {"quotes": {}, "next_page_token": None}
        mid = 50.0
        half = mid * bp / 1e4
        return {"quotes": {symbol: [quote(start, mid - half, mid + half)] * 3}, "next_page_token": None}


class TheSample(unittest.TestCase):
    DAY = dt.date(2023, 3, 8)        # winter time
    SUMMER = dt.date(2023, 7, 12)

    def gateway(self, rows):
        class One:
            calls = []

            def get(self, path, params=None):
                self.calls.append((path, dict(params)))
                return rows if not callable(rows) else rows()

        return One()

    def test_one_request_of_the_two_seconds_from_the_instant_in_new_york_time(self):
        for day, time_et, start, end in ((self.DAY, "09:32:00", "2023-03-08T14:32:00Z", "2023-03-08T14:32:02Z"),
                                         (self.SUMMER, "09:32:00", "2023-07-12T13:32:00Z", "2023-07-12T13:32:02Z"),
                                         (self.SUMMER, "15:55:00", "2023-07-12T19:55:00Z", "2023-07-12T19:55:02Z"),
                                         (self.DAY, "09:30:30", "2023-03-08T14:30:30Z", "2023-03-08T14:30:32Z")):
            gateway = self.gateway({"quotes": {}})
            gateway.calls.clear()
            self.assertIsNone(SP.sample(gateway, "ZZZ", day, time_et, asof=day.isoformat()))
            self.assertEqual(gateway.calls, [(SP.QUOTES, {"symbols": "ZZZ", "start": start, "end": end, "limit": 50,
                                                          "feed": "sip", "sort": "asc", "asof": day.isoformat()})])
        self.assertEqual((SP.QUOTES, SP.TIMES_ET, SP.EARLY_ET, SP.WINDOW_S, SP.LIMIT),
                         ("/v1/alpaca/v2/stocks/quotes", ("09:32:00", "15:55:00"), "09:30:30", 2, 50))
        gateway = self.gateway({"quotes": {}})
        gateway.calls.clear()
        SP.sample(gateway, "ZZZ", self.DAY, "09:32:00", asof=None)
        self.assertNotIn("asof", gateway.calls[0][1])

    def test_the_sample_is_the_median_of_the_valid_quotes_half_spreads(self):
        at = lambda ss, micro=0: utc(self.DAY, 9, 32, ss, micro)  # noqa: E731
        rows = [quote(at(0), 99.98, 100.02),                       # 2 bp
                quote(at(0, 500000), 99.95, 100.05),               # 5 bp
                quote(at(1), 99.90, 100.10),                       # 10 bp
                quote(at(1), 0.0, 100.10),                         # no bid
                quote(at(1), 100.10, 100.10),                      # locked
                quote(at(1), 100.20, 100.10),                      # crossed
                quote(at(1), float("nan"), 100.10),
                quote(at(1), None, 100.10),                        # no bid at all
                quote(utc(self.DAY, 9, 31, 59), 90.0, 110.0),      # before the window
                quote(utc(self.DAY, 9, 32, 3), 90.0, 110.0)]       # after it
        got = SP.sample(self.gateway({"quotes": {"ZZZ": rows}}), "ZZZ", self.DAY, "09:32:00", asof=None)
        self.assertAlmostEqual(got, 0.0005, places=12)
        want = statistics.median([(100.02 - 99.98) / 200.0, (100.05 - 99.95) / 200.0, (100.10 - 99.90) / 200.0])
        self.assertEqual(got, want)
        # an even count: the mean of the middle two; the venue's nine-digit fractions are read
        rows = [quote("2023-03-08T14:32:00.123456789Z", 99.98, 100.02),
                quote("2023-03-08T14:32:01.000000001Z", 99.94, 100.06)]
        got = SP.sample(self.gateway({"quotes": {"ZZZ": rows}}), "ZZZ", self.DAY, "09:32:00", asof=None)
        self.assertAlmostEqual(got, (0.0002 + 0.0006) / 2, places=12)

    def test_a_window_with_no_valid_quote_is_none(self):
        for answer in ({"quotes": {}}, {"quotes": None}, {"quotes": {"ZZZ": None}}, {"quotes": {"ZZZ": []}},
                       {"quotes": {"OTHER": [quote(utc(self.DAY, 9, 32), 1.0, 2.0)]}},
                       {"quotes": {"ZZZ": [quote(utc(self.DAY, 9, 32), 0.0, 2.0)]}}):
            self.assertIsNone(SP.sample(self.gateway(answer), "ZZZ", self.DAY, "09:32:00", asof=None))

    def test_an_answer_that_is_not_the_venues_is_refused(self):
        at = utc(self.DAY, 9, 32, 1)
        for answer in (None, [], {"bars": {}}, {"quotes": []}, {"quotes": {"ZZZ": {}}}, {"quotes": {"ZZZ": ["x"]}},
                       {"quotes": {"ZZZ": [{"t": None, "bp": 90.0, "ap": 110.0}]}},                     # no time
                       {"quotes": {"ZZZ": [{"t": "2023-03-08T09:32:01", "bp": 90.0, "ap": 110.0}]}},    # no zone
                       {"quotes": {"ZZZ": [{"bp": 90.0, "ap": 110.0}]}},
                       {"quotes": {"ZZZ": [{"t": at, "bp": "99.98", "ap": "100.02"}]}},   # prices as text: never
                       {"quotes": {"ZZZ": [quote(at, 99.98, 100.02), {"t": at, "bp": True, "ap": 100.02}]}}):
            with self.assertRaises(ValueError, msg=answer):
                SP.sample(self.gateway(answer), "ZZZ", self.DAY, "09:32:00", asof=None)

        def down():
            raise GatewayError("GET quotes: HTTP 500", status=500)

        with self.assertRaises(GatewayError):
            SP.sample(self.gateway(down), "ZZZ", self.DAY, "09:32:00", asof=None)

    def test_no_day_outside_the_train_years_is_ever_asked_for(self):
        gateway = self.gateway({"quotes": {}})
        gateway.calls.clear()
        for year in (2016, 2020, 2021, 2025, 2026):
            with self.assertRaisesRegex(ValueError, "Train years only"):
                SP.sample(gateway, "ZZZ", dt.date(year, 3, 9), "09:32:00", asof=None)
        self.assertEqual(gateway.calls, [])


def taken(values) -> dict:
    return {f"2022-01-{i + 1:02d}": v for i, v in enumerate(values)}


class TheTable(unittest.TestCase):
    """D20: a name's 75th percentile of its kept samples; a sample above 100 bp dropped and counted; the universe's
    figure; what a fill is charged."""

    def test_a_names_figure_is_the_75th_percentile_of_its_kept_samples(self):
        out = SP.summarize({"100": {"exchange": "NYSE", "open": taken([1.0, 2.0, 3.0, 4.0, 5.0, None, 250.0, 100.0]),
                                    "close": taken([2.0, 10.0])}})
        # kept at the open: 1, 2, 3, 4, 5 and exactly 100 (at the line: kept); 250 is dropped; None is no sample
        self.assertEqual(out["names"], {"100": {"open_bp": 4.75, "close_bp": 8.0, "n_open": 6, "n_close": 2}})
        self.assertEqual(out["counts"], {"NYSE": {"open": {"kept": 6, "dropped": 1, "empty": 1},
                                                  "close": {"kept": 2, "dropped": 0, "empty": 0}}})
        self.assertEqual(out["dropped"], {"NYSE": {"open": round(1 / 7, 4), "close": 0.0}})
        self.assertEqual(out["dropped_all"], {"open": round(1 / 7, 4), "close": 0.0})
        self.assertEqual((out["full"], out["warnings"]), (0, []))
        self.assertEqual(xs_config.HS_MAX_BP, 100.0)

    def test_the_line_is_the_books_own_two_percent_of_the_mid(self):
        from league.equity import live

        self.assertEqual(xs_config.HS_MAX_BP / 1e4 * 2, float(live.MAX_ENTRY_SPREAD))

    def test_the_universes_figure_is_the_75th_percentile_of_the_floored_name_figures_with_eight_samples(self):
        floor = xs_config.HS_FLOOR_BP
        samples = {
            "100": {"exchange": "NYSE", "open": taken([1.0] * 8), "close": taken([1.0] * 8)},       # under the floor
            "101": {"exchange": "NYSE", "open": taken([6.0] * 8), "close": taken([4.0] * 8)},
            "102": {"exchange": "NASDAQ", "open": taken([8.0] * 9), "close": taken([5.0] * 8)},
            "103": {"exchange": "NASDAQ", "open": taken([10.0] * 12), "close": taken([20.0] * 7)},  # 7 at the close
            "104": {"exchange": None, "open": taken([90.0] * 7), "close": taken([None] * 9)},       # too few; none
        }
        out = SP.summarize(samples)
        self.assertEqual(out["default"], {"open_bp": SP.percentile([floor, 6.0, 8.0, 10.0]),
                                          "close_bp": SP.percentile([floor, 4.0, 5.0])})
        self.assertEqual(out["default"], {"open_bp": 8.5, "close_bp": 4.5})
        self.assertEqual(out["names"]["100"], {"open_bp": 1.0, "close_bp": 1.0, "n_open": 8, "n_close": 8})
        self.assertEqual(out["names"]["104"], {"open_bp": 90.0, "close_bp": None, "n_open": 7, "n_close": 0})
        self.assertEqual(out["full"], 3)
        self.assertEqual(sorted(out["counts"]), ["NASDAQ", "NYSE", "unknown"])
        self.assertEqual(out["counts"]["unknown"]["close"], {"kept": 0, "dropped": 0, "empty": 9})
        self.assertEqual(out["dropped"]["unknown"], {"open": 0.0, "close": None})
        self.assertEqual(SP.MIN_SAMPLES, 8)

    def test_with_no_name_of_eight_samples_the_universes_figure_is_the_fallback(self):
        out = SP.summarize({"100": {"exchange": "NYSE", "open": taken([4.0] * 7), "close": taken([4.0] * 7)}})
        fallback = xs_config.HS_FALLBACK_BP
        self.assertEqual(out["default"], {"open_bp": fallback[0], "close_bp": fallback[1]})
        self.assertEqual(SP.summarize({})["default"], {"open_bp": 10.0, "close_bp": 5.0})

    def test_what_a_fill_is_charged(self):
        floor = xs_config.HS_FLOOR_BP
        table = SP.summarize({
            "100": {"exchange": "NYSE", "open": taken([1.0] * 8), "close": taken([7.0] * 8)},
            "101": {"exchange": "NYSE", "open": taken([6.0] * 8), "close": taken([40.0] * 7)},
            "102": {"exchange": "NYSE", "open": taken([9.0] * 8), "close": taken([5.0] * 8)}})
        self.assertEqual(table["default"], {"open_bp": 7.5, "close_bp": 6.5})   # of 3, 6, 9 and of 5, 7
        self.assertEqual(SP.name_bp(table, 100), (floor, 7.0))            # a figure under the floor is the floor
        self.assertEqual(SP.name_bp(table, "101"), (6.0, 6.5))            # seven samples: the universe's figure
        self.assertEqual(SP.name_bp(table, 102), (9.0, 5.0))
        self.assertEqual(SP.name_bp(table, 999), (7.5, 6.5))              # a name never sampled: the universe's
        self.assertEqual(SP.name_bp(None, 100), xs_config.HS_FALLBACK_BP)  # no file: 10 bp and 5 bp
        self.assertEqual(SP.name_bp({}, 100), (10.0, 5.0))
        low = {"names": {}, "default": {"open_bp": 0.5, "close_bp": 0.5}}
        self.assertEqual(SP.name_bp(low, 1), (floor, floor))
        for table_ in (table, None, low):
            for aid in (100, 101, 102, 999):
                self.assertGreaterEqual(min(SP.name_bp(table_, aid)), floor)
        self.assertEqual(floor, 3.0)

    def test_a_dropped_share_above_a_tenth_at_a_fill_point_is_a_warning(self):
        wide = {str(aid): {"exchange": "NYSE", "open": taken([4.0] * 8 + [300.0] * 2), "close": taken([4.0] * 10)}
                for aid in range(100, 130)}
        tight = {str(aid): {"exchange": "NASDAQ", "open": taken([4.0] * 10), "close": taken([4.0] * 10)}
                 for aid in range(130, 150)}
        out = SP.summarize({**wide, **tight})
        self.assertEqual(out["dropped"], {"NASDAQ": {"open": 0.0, "close": 0.0}, "NYSE": {"open": 0.2, "close": 0.0}})
        self.assertEqual(out["dropped_all"], {"open": 0.12, "close": 0.0})
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("12% of the 500 spread samples at the open", out["warnings"][0])
        self.assertIn("NYSE 20%", out["warnings"][0])
        self.assertNotIn("NASDAQ", out["warnings"][0])
        self.assertEqual(SP.summarize(dict(list(wide.items())[:10]))["warnings"], [], "too few samples to say")
        self.assertEqual((SP.DROPPED_WARNING, SP.DROPPED_MIN), (0.10, 200))


class Universe:
    """Package C's `Universe` at its interface: the members the test fixed, the same every day unless told."""

    members_of: dict = {}
    asked: list = []
    fail: Exception | None = None

    def __init__(self, root):
        type(self).asked.append(("open", Path(root)))
        if type(self).fail is not None:
            raise type(self).fail

    def members(self, day):
        type(self).asked.append(("members", day))
        rows = type(self).members_of
        return list(rows(day) if callable(rows) else rows)

    def aid(self, symbol, day):
        for aid, name in self.members(day):
            if name == symbol:
                return aid
        raise KeyError(symbol)


NAMES = [(100 + i, f"Q{chr(65 + i)}Z") for i in range(6)]            # invented symbols: QAZ, QBZ, ...
PER_DAY = len(NAMES) * 3                                             # every name is a fixed name here: 3 calls a day
TOTAL = 48 * PER_DAY


class TheJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.root = self.state / SP.STORE_DIR
        (self.root / "universe").mkdir(parents=True)
        (self.root / "universe" / "UNIVERSE_MANIFEST.json").write_text("{}")
        (self.root / "universe" / "assets.json").write_text(json.dumps(
            {str(aid): {"symbol": name, "alpaca": {"exchange": "NYSE" if aid % 2 else "NASDAQ"} if aid != 105 else None}
             for aid, name in NAMES}))
        self.now = NOW
        self.gateway = Quotes()
        Universe.members_of, Universe.asked, Universe.fail = list(NAMES), [], None
        for patch in (mock.patch.object(xs_store, "Universe", Universe),):
            patch.start()
            self.addCleanup(patch.stop)
        quiet = mock.patch.object(xs_config, "quiet", return_value=None)
        self.quiet = quiet.start()
        self.addCleanup(quiet.stop)
        self.slept: list[float] = []

    def ctx(self) -> Context:
        return Context("equity_spreads", root=self.state, due_at=self.now, clock=lambda: self.now, gateway=self.gateway,
                       config={}, settings_value={})

    def go(self, ctx: Context | None = None) -> dict:
        return SP.run(ctx or self.ctx(), sleep=self.slept.append)

    def file(self) -> dict:
        return json.loads((self.root / SP.FILE).read_text())

    def limit(self, **values):
        patch = mock.patch.multiple(SP, **values)
        patch.start()
        self.addCleanup(patch.stop)

    # ---- the walls and the switches
    def test_it_asks_the_quiet_windows_first_with_its_own_wall(self):
        self.quiet.return_value = "inside the open wall"
        self.assertEqual(self.go(), {"status": "skipped", "why": "inside the open wall"})
        self.quiet.assert_called_once_with(NOW, SP.WALL_S)
        self.assertEqual((SP.WALL_S, self.gateway.calls, Universe.asked, (self.root / SP.FILE).exists()),
                         (3000, [], [], False))
        self.quiet.side_effect = RuntimeError("no calendar")
        ctx = self.ctx()
        out = self.go(ctx)
        self.assertEqual((out["status"], self.gateway.calls), ("skipped", []))
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning"])

    def test_before_the_universe_exists_it_is_skipped_and_an_unreadable_one_is_a_failed_receipt(self):
        (self.root / "universe" / "UNIVERSE_MANIFEST.json").unlink()
        self.assertEqual(self.go(), {"status": "skipped", "why": "no universe yet"})
        self.assertEqual(Universe.asked, [])
        (self.root / "universe" / "UNIVERSE_MANIFEST.json").write_text("{}")
        for fail in (NotImplementedError("a stub"), eq_store.MissingData("assets.json does not match its manifest")):
            Universe.fail = fail
            out = self.go()
            self.assertEqual((out["status"], out["ok"]), ("failed", False))
            self.assertIn("the universe cannot be read", out["error"])
        self.assertEqual(self.gateway.calls, [])
        self.assertFalse((self.root / SP.FILE).exists())

    def test_with_no_gateway_client_it_is_a_failed_receipt_and_nothing_is_written(self):
        class NoClient(Context):
            @property
            def gateway(self):
                raise GatewayError("GATEWAY_TOKEN is not set")

        ctx = NoClient("equity_spreads", root=self.state, due_at=NOW, clock=lambda: NOW, config={}, settings_value={})
        out = self.go(ctx)
        self.assertEqual((out["status"], out["ok"]), ("failed", False))
        self.assertIn("no gateway", out["error"])
        self.assertFalse((self.root / SP.FILE).exists())

    def test_the_budgets_sit_inside_the_wall(self):
        from league.ops import equity_data

        self.assertEqual(SP.STORE_DIR, equity_data.STORE_DIR)
        self.assertLess(SP.BUDGET_S + 2 * 45.0, SP.WALL_S)        # room for one last request and the file
        self.assertLess(SP.CALLS_RUN * SP.PAUSE_S, SP.BUDGET_S)
        self.assertEqual((SP.CALLS_RUN, SP.SESSIONS_YEAR, SP.EARLY_NAMES, SP.VERSION, SP.FILE),
                         (6000, 8, 20, "xs-spreads-v1", "spreads.json"))

    # ---- a whole backfill
    def test_a_whole_backfill_and_the_file_it_leaves(self):
        figures = {"QAZ": 2.0, "QBZ": 6.0, "QCZ": 8.0, "QDZ": 10.0, "QEZ": 400.0, "QFZ": None}

        def bp(symbol, start):
            """Each name's invented half-spread, half as wide again at 09:30:30 (13:30:30Z or 14:30:30Z)."""
            early = start[11:19] in ("13:30:30", "14:30:30")
            return None if figures[symbol] is None else figures[symbol] * (1.5 if early else 1.0)

        self.gateway.bp = bp
        ctx = self.ctx()
        out = self.go(ctx)
        self.assertEqual(out["calls"], TOTAL)
        self.assertEqual((out["ok"], out["remaining"], out["done"], out["calls_total"], out["errors"], out["refused"]),
                         (True, 0, True, TOTAL, 0, 0))
        self.assertEqual((out["sampled"], out["empty"]), (48 * 5 * 3, 48 * 3))
        self.assertEqual((out["names"], out["full"]), (6, 4))
        self.assertEqual(out["dropped"], {"open": 0.2, "close": 0.2})
        self.assertEqual(self.slept, [SP.PAUSE_S] * TOTAL)
        held = self.file()
        self.assertLessEqual({"version", "sampled", "names", "default", "dropped", "calls", "done"}, set(held))
        self.assertEqual((held["version"], held["calls"], held["done"], held["runs"]), (SP.VERSION, TOTAL, True, 1))
        self.assertEqual(held["sampled"], {str(y): [d.isoformat() for d in days] for y, days in DAYS.items()})
        self.assertEqual(held["names"]["100"], {"open_bp": 2.0, "close_bp": 2.0, "n_open": 48, "n_close": 48})
        self.assertEqual(held["names"]["104"], {"open_bp": None, "close_bp": None, "n_open": 0, "n_close": 0})
        self.assertEqual(held["names"]["105"], {"open_bp": None, "close_bp": None, "n_open": 0, "n_close": 0})
        self.assertEqual(held["default"], {"open_bp": SP.percentile([3.0, 6.0, 8.0, 10.0]), "close_bp": 8.5})
        self.assertEqual(held["dropped"], {"NASDAQ": {"open": round(48 / 144, 4), "close": round(48 / 144, 4)},
                                           "NYSE": {"open": 0.0, "close": 0.0},
                                           "unknown": {"open": None, "close": None}})
        self.assertEqual(held["samples"]["105"]["exchange"], "unknown")
        self.assertEqual(stat.S_IMODE((self.root / SP.FILE).stat().st_mode), 0o600)
        # the dropped share at both fill points is above the line: a House warning each, counts and shares only
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning", "warning"])
        # what a fill is charged, read back from the file: the floor, a figure, the universe's for the two without
        table = SP.read(self.root)
        self.assertEqual([SP.name_bp(table, aid) for aid in (100, 101, 104, 105)],
                         [(3.0, 3.0), (6.0, 6.0), (8.5, 8.5), (8.5, 8.5)])
        # the first week's comparison of the instants: the fixed names, the two medians, nothing else
        self.assertEqual(held["early_names"], [aid for aid, _ in NAMES])
        self.assertEqual(out["early"], {"names": 6, "pairs": 48 * 5, "early_et": "09:30:30", "open_et": "09:32:00",
                                        "median_early_bp": 12.0, "median_open_bp": 8.0})
        # neither the file nor the receipt nor an alert names a symbol
        for text in (json.dumps(held), json.dumps(out), json.dumps(ctx.alerts)):
            for _, symbol in NAMES:
                self.assertNotIn(symbol, text)

    def test_every_request_is_one_symbol_one_window_of_a_train_year_with_its_own_day_as_of(self):
        self.go()
        self.assertEqual(len(self.gateway.calls), TOTAL)
        instants = set()
        for call in self.gateway.calls:
            self.assertEqual((call["path"], call["limit"], call["feed"], call["sort"]), (SP.QUOTES, 50, "sip", "asc"))
            self.assertIn(call["symbols"], {name for _, name in NAMES})
            start = dt.datetime.fromisoformat(call["start"].replace("Z", "+00:00"))
            end = dt.datetime.fromisoformat(call["end"].replace("Z", "+00:00"))
            local = start.astimezone(SP.NEW_YORK)
            self.assertEqual((end - start).total_seconds(), SP.WINDOW_S)
            self.assertIn(local.year, xs_config.TRAIN_YEARS)
            self.assertEqual(call["asof"], local.date().isoformat())
            self.assertIn(local.date(), DAYS[local.year])
            instants.add(local.strftime("%H:%M:%S"))
        self.assertEqual(instants, {"09:30:30", "09:32:00", "15:55:00"})
        for sealed in ("2016", "2020", "2021", "2025", "2026"):
            self.assertFalse([c for c in self.gateway.calls if sealed in c["start"][:4] or sealed in c["asof"][:4]])
        self.assertEqual({day for kind, day in Universe.asked if kind == "members"},
                         {day for days in DAYS.values() for day in days})

    # ---- resumable
    def test_a_run_stops_at_its_call_budget_and_the_next_goes_on_where_it_stopped(self):
        self.limit(CALLS_RUN=300)
        seen: list[tuple] = []
        for night in range(1, 4):
            self.now = NOW + night * 86400.0
            out = self.go()
            self.assertEqual((out["calls"], out["calls_total"], out["remaining"], out["done"]),
                             (min(300, TOTAL - 300 * (night - 1)), min(300 * night, TOTAL),
                              max(0, TOTAL - 300 * night), 300 * night >= TOTAL))
            seen = [(c["symbols"], c["start"]) for c in self.gateway.calls]
            self.assertEqual(len(seen), len(set(seen)), "a sample already answered was asked again")
        self.assertEqual(len(seen), TOTAL)
        self.assertEqual((self.file()["runs"], self.file()["calls"]), (3, TOTAL))

    def test_the_file_is_rewritten_as_a_run_goes_so_a_killed_run_loses_little(self):
        self.limit(SAVE_EVERY=10)

        def killed(n, params):
            return KeyboardInterrupt() if n == 26 else None

        self.gateway.raises = killed
        with self.assertRaises(KeyboardInterrupt):
            self.go()
        held = self.file()
        self.assertEqual((held["calls"], held["done"], held["remaining"]), (20, False, TOTAL - 20))
        self.gateway.raises = None
        out = self.go()
        self.assertEqual((out["calls"], out["calls_total"], out["done"]), (TOTAL - 20, TOTAL, True))

    def test_a_run_asks_no_more_once_its_seconds_are_spent(self):
        ctx = Context("equity_spreads", root=self.state, due_at=NOW, gateway=self.gateway, config={},
                      settings_value={}, clock=lambda: NOW + 100.0 * len(self.gateway.calls))
        out = self.go(ctx)
        self.assertEqual((out["ok"], out["calls"], out["done"]), (True, int(SP.BUDGET_S / 100), False))
        self.assertEqual(out["remaining"], TOTAL - 24)

    # ---- errors and refusals
    def test_an_error_leaves_the_sample_owed_and_ten_in_a_row_end_the_run(self):
        def flaky(n, params):
            return GatewayError("GET quotes: HTTP 502", status=502) if n in (3, 4, 9) or 40 <= n < 50 else None

        self.gateway.raises = flaky
        ctx = self.ctx()
        out = self.go(ctx)
        self.assertEqual((out["status"], out["ok"], out["calls"], out["errors"]), ("failed", False, 49, 13))
        self.assertIn("10 requests in a row failed", out["error"])
        self.assertIn("HTTP 502", out["error"])
        self.assertEqual((out["sampled"], out["remaining"], out["calls_total"]), (36, TOTAL - 36, 49))
        self.gateway.raises = None
        before = len(self.gateway.calls)
        out = self.go()
        self.assertEqual((out["ok"], out["calls"], out["done"]), (True, TOTAL - 36, True))
        asked = [(c["symbols"], c["start"]) for c in self.gateway.calls]
        self.assertEqual(len(set(asked)), TOTAL)
        self.assertEqual(len(asked) - before, TOTAL - 36)

    def test_a_rate_limit_is_waited_out_and_the_same_sample_asked_again(self):
        limited = {2: 1, 5: 2, 9: 3}              # the n-th item is answered 429 this many times before its answer
        seen: dict[tuple, int] = {}

        def busy(n, params):
            item = (params["symbols"], params["start"])
            seen[item] = seen.get(item, 0) + 1
            order = list(seen).index(item) + 1
            return GatewayError("GET quotes: HTTP 429", status=429) if seen[item] <= limited.get(order, 0) else None

        self.gateway.raises = busy
        self.limit(CALLS_RUN=30)
        out = self.go()
        # items 2 and 5 are answered on their second and third try; item 9 is still 429 after both waits: an error
        self.assertEqual((out["ok"], out["errors"], out["calls"]), (True, 1, 30))
        self.assertEqual(out["sampled"] + out["empty"], 30 - (1 + 2 + 3))
        self.assertEqual([w for w in self.slept if w != SP.PAUSE_S], [5.0, 5.0, 20.0, 5.0, 20.0])
        self.assertEqual((SP.BACKOFF_S, SP.RATE_LIMITED), ((5.0, 20.0), 429))
        self.assertEqual(out["remaining"], TOTAL - (out["sampled"] + out["empty"]))

    def test_a_run_whose_windows_are_mostly_empty_keeps_them_and_says_so(self):
        self.gateway.bp = lambda symbol, start: None if symbol in ("QAZ", "QBZ") else 4.0
        self.limit(CALLS_RUN=120)
        ctx = self.ctx()
        out = self.go(ctx)
        # 18 requests a day: six whole days (two of six names empty) and the first four names of the seventh
        self.assertEqual((out["ok"], out["calls"], out["empty"], out["sampled"]), (True, 120, 6 * 6 + 6, 6 * 12 + 6))
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning"])
        self.assertIn("42 of this run's 120 windows held no valid quote", ctx.alerts[0]["text"])
        self.assertEqual(self.file()["remaining"], TOTAL - 120)

    def test_a_malformed_answer_is_an_error_not_a_sample(self):
        answers = iter([{"bars": {}}, None])

        class Odd(Quotes):
            def get(self, path, params=None):
                good = super().get(path, params)
                return next(answers, good)

        self.gateway = Odd()
        out = self.go()
        self.assertEqual((out["ok"], out["errors"], out["remaining"]), (True, 2, 2))

    def test_a_request_the_venue_refuses_is_an_answer_of_no_sample(self):
        def refuses(n, params):
            refused = GatewayError("GET quotes: HTTP 422 invalid symbol", status=422)
            return refused if params["symbols"] == "QCZ" else None

        self.gateway.raises = refuses
        out = self.go()
        self.assertEqual((out["ok"], out["refused"], out["done"], out["errors"]), (True, 48 * 3, True, 0))
        self.assertEqual(self.file()["names"]["102"], {"open_bp": None, "close_bp": None, "n_open": 0, "n_close": 0})
        calls = len(self.gateway.calls)
        self.now += SP.MONTHLY_S + 1
        self.assertEqual(self.go()["calls"], 0)
        self.assertEqual(len(self.gateway.calls), calls, "a refused sample is not asked again")
        self.assertEqual(SP.REFUSED_STATUS, (400, 404, 422))

    def test_a_run_the_venue_mostly_refuses_keeps_none_of_its_refusals(self):
        self.gateway.raises = lambda n, params: GatewayError("GET quotes: HTTP 400 bad request", status=400) \
            if n % 2 else None
        out = self.go()
        self.assertEqual((out["status"], out["ok"], out["calls"], out["refused"]), ("failed", False, 50, 25))
        self.assertIn("the venue refused 25 of 50 requests", out["error"])
        self.assertEqual(out["remaining"], TOTAL - 25)
        held = self.file()
        answered = sum(len(row[p]) for row in held["samples"].values() for p in SP.POINTS) \
            + sum(len(row) for row in held["early"].values())
        self.assertEqual(answered, 25)
        self.assertTrue(all(v is not None for row in held["samples"].values() for p in SP.POINTS
                            for v in row[p].values()))
        self.gateway.raises = None
        self.assertEqual(self.go()["calls"], TOTAL - 25)

    # ---- then monthly, new assets only
    def test_once_done_it_looks_for_new_assets_monthly_and_asks_only_theirs(self):
        self.assertTrue(self.go()["done"])
        calls, asked = len(self.gateway.calls), len(Universe.asked)
        self.now = NOW + SP.MONTHLY_S - 60.0
        out = self.go()
        self.assertEqual(out["status"], "skipped")
        self.assertIn("monthly", out["why"])
        self.assertEqual((len(self.gateway.calls), len(Universe.asked)), (calls, asked))
        # a month on, with one new asset that was a member from 2023 on: only its samples are asked
        self.now = NOW + SP.MONTHLY_S + 60.0
        Universe.members_of = lambda day: NAMES + ([(900, "QNEW")] if day.year >= 2023 else [])
        out = self.go()
        new = [c for c in self.gateway.calls[calls:]]
        self.assertEqual((out["calls"], out["done"], {c["symbols"] for c in new}), (32, True, {"QNEW"}))
        self.assertEqual({c["start"][:4] for c in new}, {"2023", "2024"})
        held = self.file()
        self.assertEqual(held["names"]["900"]["n_open"], 16)
        self.assertEqual(held["early_names"], [aid for aid, _ in NAMES], "the fixed names stay the first run's")
        self.assertEqual(held["runs"], 2)

    def test_a_file_of_another_version_is_never_overwritten(self):
        (self.root / SP.FILE).write_text(json.dumps({"version": "something-else", "samples": {}}))
        before = (self.root / SP.FILE).read_bytes()
        out = self.go()
        self.assertEqual((out["status"], out["ok"]), ("failed", False))
        self.assertIn("move it aside", out["error"])
        self.assertEqual(((self.root / SP.FILE).read_bytes(), self.gateway.calls), (before, []))
        self.assertIsNone(SP.read(self.root))


class ThePlan(unittest.TestCase):
    def test_the_fixed_names_come_first_each_days_early_sample_before_its_two_others(self):
        names = [(100 + i, f"Q{i:02d}") for i in range(50)]
        days = {2017: DAYS[2017][:2], 2018: DAYS[2018][:1]}
        owed = SP.plan(lambda day: names, days, {})
        fixed = owed["early_names"]
        self.assertEqual(fixed, [100 + 2 * i for i in range(20)])            # 50 members at even steps of 2
        self.assertEqual(owed["total"], 3 * (50 * 2 + 20))
        items = owed["items"]
        self.assertEqual(len(items), owed["total"])
        head, tail = items[:3 * 20 * 3], items[3 * 20 * 3:]
        self.assertTrue(all(aid in fixed for _, aid, _, _ in head))
        self.assertFalse(any(aid in fixed for _, aid, _, _ in tail))
        self.assertEqual([kind for kind, aid, _, day in head[:6]], ["early", "open", "close"] * 2)
        self.assertEqual([i[3] for i in head], sorted(i[3] for i in head))
        self.assertEqual({kind for kind, *_ in tail}, {"open", "close"})
        self.assertEqual(tail[0], ("open", 101, "Q01", DAYS[2017][0]))

    def test_what_has_an_answer_is_not_owed(self):
        day = DAYS[2017][0].isoformat()
        state = {"samples": {"100": {"open": {day: 4.0}, "close": {day: None}}}, "early": {"100": {day: 5.0}},
                 "early_names": [100]}
        owed = SP.plan(lambda d: [(100, "QAZ"), (101, "QBZ")], {2017: DAYS[2017][:1]}, state)
        self.assertEqual(owed["items"], [("open", 101, "QBZ", DAYS[2017][0]), ("close", 101, "QBZ", DAYS[2017][0])])
        self.assertEqual((owed["total"], owed["early_names"]), (5, [100]))

    def test_the_fixed_names_are_spread_over_the_first_days_members(self):
        self.assertEqual(SP.early_names(range(100, 600)), [100 + 25 * i for i in range(20)])
        self.assertEqual(SP.early_names([7, 5, 6]), [5, 6, 7])
        self.assertEqual(SP.early_names([]), [])

    def test_the_report_pairs_the_two_instants_on_the_same_name_and_day(self):
        state = {"early_names": [100, 101],
                 "early": {"100": {"d1": 9.0, "d2": 30.0, "d3": 12.0}, "101": {"d1": None, "d2": 8.0}},
                 "samples": {"100": {"open": {"d1": 3.0, "d2": 5.0}}, "101": {"open": {"d1": 2.0, "d2": 500.0}}}}
        self.assertEqual(SP.early_report(state), {"names": 2, "pairs": 3, "early_et": "09:30:30", "open_et": "09:32:00",
                                                  "median_early_bp": 9.0, "median_open_bp": 5.0})
        self.assertEqual(SP.early_report({})["pairs"], 0)
        self.assertIsNone(SP.early_report({})["median_early_bp"])


class ThePanelHalfSpread(unittest.TestCase):
    """The reader a panel lot's replay twin takes its half-spread from (package B's patch 11 to league/ops/twins.py)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / SP.STORE_DIR
        Universe.members_of = [(100, "QAZ"), (101, "QBZ"), (102, "QCZ"), (555, "QXZ")]
        Universe.asked, Universe.fail = [], None
        patch = mock.patch.object(xs_store, "Universe", Universe)
        patch.start()
        self.addCleanup(patch.stop)

    def panel(self, aids, hs, *, break_sha: str | None = None) -> None:
        folder = self.root / xs_store.PANEL_DIR
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "aids.npy", np.asarray(aids, dtype=np.int32))
        np.save(folder / "hs.npy", np.asarray(hs, dtype=np.float64))
        shas = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in ("aids.npy", "hs.npy")}
        if break_sha:
            shas[break_sha] = "0" * 64
        (folder / "PANEL_MANIFEST.json").write_text(json.dumps({"version": "xs-panel-v1", "sha256": shas}))

    def test_it_reads_the_open_and_the_close_figure_of_the_asset_the_symbol_named_that_day(self):
        self.panel([1, 2, 100, 101, 102], [[0.0001, 0.0001], [0.0002, 0.0002], [0.0010, 0.0005], [0.0003, 0.0004],
                                           [0.0, 0.0005]])
        reader = SP.panel_half_spread(self.root)
        self.assertEqual(reader("QAZ", "2027-01-05"), (0.0010, 0.0005))
        self.assertEqual(reader("QBZ", "2027-01-05"), (0.0003, 0.0004))
        self.assertIsNone(reader("QCZ", "2027-01-05"), "a row that is not two positive fractions prices nothing")
        self.assertIsNone(reader("NOPE", "2027-01-05"), "no asset traded under the symbol that day")
        self.assertIsNone(reader("QXZ", "2027-01-05"), "an asset with no column in the panel")
        self.assertIsNone(reader("QAZ", "not a day"))
        self.assertEqual(Universe.asked[0], ("open", self.root))

    def test_with_no_panel_store_there_is_no_reader_and_one_that_cannot_be_read_says_so(self):
        self.assertIsNone(SP.panel_half_spread(self.root), "no panel store: as before release E4")
        self.assertEqual(Universe.asked, [])
        good = ([100, 101], [[0.001, 0.0005], [0.001, 0.0005]])
        for why, build in (("hs.npy does not match", lambda: self.panel(*good, break_sha="hs.npy")),
                           ("aids.npy does not match", lambda: self.panel(*good, break_sha="aids.npy")),
                           ("not two figures an asset", lambda: self.panel([100, 101], [[0.001, 0.0005]]))):
            build()
            with self.assertRaisesRegex(LookupError, why):
                SP.panel_half_spread(self.root)
        self.panel(*good)
        self.assertIsNotNone(SP.panel_half_spread(self.root))
        (self.root / xs_store.PANEL_DIR / "hs.npy").unlink()
        with self.assertRaisesRegex(LookupError, "FileNotFoundError"):
            SP.panel_half_spread(self.root)
        self.panel(*good)
        for fail in (NotImplementedError("a stub"), eq_store.MissingData("no universe")):
            Universe.fail = fail
            with self.assertRaises(LookupError):
                SP.panel_half_spread(self.root)

    def test_the_fill_points_are_the_panels_columns(self):
        self.assertEqual(SP.POINTS, ("open", "close"))
        self.assertEqual(len(SP.POINTS), len(SP.TIMES_ET))


# ------------------------------------------------------------------------------------------------- a panel lot's twin
def panel_lot(lid: int = 7, *, symbol: str = "QAZ", entry_at: str = "open", exit_at: str = "close",
              opened_day: str = "2027-02-01", exit_day: str = "2027-02-03") -> dict:
    """An invented closed `eq_lots` row of a name outside E1's universe (league/equity/live.py SCHEMA)."""
    return {"lid": lid, "instance": "panel-fam@1:r", "family": "panel-fam", "version": 1, "lane": "equity",
            "symbol": symbol, "class": "stock" if symbol != "SPY" else "etf", "qty": "2.500000",
            "opened_qty": "2.500000", "entry_px": "40.06", "entry_notional": "100.15", "entry_at": entry_at,
            "fees": "0.02", "div": "0", "mark": None, "marked_at": None, "opened_at": 1.0, "opened_day": opened_day,
            "status": "closed", "exit_px": "42.90", "exit_at": exit_at, "exit_day": exit_day, "closed_at": 2.0,
            "cash": "7.08", "reason": "program", "probe": 1, "tag": "xs", "iid": None, "info": "{}"}


def official(o: float, c: float) -> dict:
    return {"o": str(o), "h": str(max(o, c) + 1), "l": str(min(o, c) - 1), "c": str(c), "v": "1000000", "audit": "ok",
            "sha": "x" * 64}


BARS = {"2027-02-01": official(40.0, 41.0), "2027-02-03": official(42.0, 43.0)}


class APanelLotsTwin(unittest.TestCase):
    """Package B's patch 11 to league/ops/twins.py: a lot of a name outside E1's universe is priced at the panel's
    half-spreads, the open's figure for a fill at the open and the close's for a fill at the close; with none it stays
    unpriceable; a lot of E1's universe never asks."""

    PAIR = (0.0010, 0.0005)

    def twin(self, row=None, **kw):
        from league.ops import twins

        return twins.equity_twin(row or panel_lot(), BARS, at=NOW, **kw)

    def test_an_open_entry_pays_the_opens_figure_and_a_close_exit_the_closes(self):
        asked = []

        def reader(symbol, day):
            asked.append((symbol, day))
            return self.PAIR

        rec = self.twin(panel_hs=reader)
        self.assertEqual((rec["status"], rec["final"], rec["why"]), ("priced", True, None))
        self.assertEqual(asked, [("QAZ", "2027-02-01")])
        self.assertEqual((rec["hs_bp"], rec["hs_exit_bp"], rec["hs_source"]), (10.0, 5.0, "panel"))
        self.assertEqual((rec["entry_official"], rec["exit_official"]), (40.0, 43.0))
        self.assertEqual(rec["twin"]["entry_px"], round(40.0 * (1 + 0.0010), 6))
        self.assertEqual(rec["twin"]["exit_px"], round(43.0 * (1 - 0.0005), 6))
        stress = self.twin(panel_hs=reader, k=1.5)
        self.assertEqual(stress["twin"]["entry_px"], round(40.0 * (1 + 0.0015), 6))
        self.assertEqual(stress["twin"]["exit_px"], round(43.0 * (1 - 0.00075), 6))

    def test_a_close_entry_pays_the_closes_figure_and_an_open_exit_the_opens(self):
        rec = self.twin(panel_lot(entry_at="close", exit_at="open"), panel_hs=lambda symbol, day: self.PAIR)
        self.assertEqual((rec["entry_official"], rec["exit_official"]), (41.0, 42.0))
        self.assertEqual((rec["hs_bp"], rec["hs_exit_bp"]), (5.0, 10.0))
        self.assertEqual(rec["twin"]["entry_px"], round(41.0 * (1 + 0.0005), 6))
        self.assertEqual(rec["twin"]["exit_px"], round(42.0 * (1 - 0.0010), 6))

    def test_with_no_figure_the_lot_is_unpriceable_as_before(self):
        want = ("unpriceable", True, "QAZ is not in the universe (no half-spread)")
        rec = self.twin()
        self.assertEqual((rec["status"], rec["final"], rec["why"]), want)
        for answer in (None, (), (0.001,), (0.001, 0.0), (0.001, float("nan")), ("x", 0.001), (0.001, 0.001, 0.001),
                       {"open": 0.001, "close": 0.001}):
            rec = self.twin(panel_hs=lambda symbol, day, a=answer: a)
            self.assertEqual((rec["status"], rec["final"], rec["why"]), want, answer)
            self.assertNotIn("hs_source", rec)

    def test_a_panel_store_that_cannot_be_read_leaves_the_lot_waiting(self):
        def unread(symbol, day):
            raise LookupError("panel/hs.npy does not match its manifest")

        rec = self.twin(panel_hs=unread)
        self.assertEqual((rec["status"], rec["final"]), ("unpriceable", False))
        self.assertIn("cannot be read", rec["why"])
        self.assertIn("does not match its manifest", rec["why"])

    def test_a_lot_of_e1s_universe_never_asks_the_panel(self):
        def boom(symbol, day):
            raise AssertionError("an E1 lot asked the panel for a half-spread")

        row = panel_lot(symbol="SPY")
        rec = self.twin(row, panel_hs=boom)
        self.assertEqual(rec, self.twin(row))
        self.assertEqual(rec["status"], "priced")
        self.assertNotIn("hs_source", rec)
        self.assertNotIn("hs_exit_bp", rec)

    def round(self, lots, reader):
        """`equity_round` over a book of `lots`, `panel_half_spread` answering `reader` (an exception: raised)."""
        from league.equity.live import SCHEMA
        from league.live.state import LiveState
        from league.ops import twins
        from league.swarm.store import SwarmStore

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        store = SwarmStore(root)
        self.addCleanup(store.close)
        live = LiveState(root / "live.sqlite")
        self.addCleanup(live.close)
        live.db.executescript(SCHEMA)
        for row in lots:
            live.upsert("eq_lots", row, "lid")
            for day, b in BARS.items():
                live.upsert("eq_bars", {"day": day, "symbol": row["symbol"], "adjustment": "raw", "o": b["o"],
                                        "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "fetched_at": 0.0,
                                        "sha": b["sha"], "audit": b["audit"]}, "day, symbol, adjustment")
        opened = mock.Mock(side_effect=reader if isinstance(reader, Exception) else None, return_value=reader)
        with mock.patch.object(SP, "panel_half_spread", opened):
            out = twins.equity_round(root, now=NOW, store=store)
        return out, twins.equity_records(store), opened, root

    def test_the_round_never_opens_the_panel_store_for_a_book_of_e1_lots(self):
        out, records, opened, _ = self.round([panel_lot(1, symbol="SPY")], lambda symbol, day: self.PAIR)
        self.assertEqual((out["judged"], records["eq:1"]["status"]), ({"priced": 1}, "priced"))
        opened.assert_not_called()

    def test_the_round_prices_a_panel_lot_from_the_panel_store_opened_once(self):
        out, records, opened, root = self.round([panel_lot(1, symbol="SPY"), panel_lot(2), panel_lot(3, symbol="QBZ")],
                                                lambda symbol, day: self.PAIR if symbol == "QAZ" else None)
        opened.assert_called_once_with(root / SP.STORE_DIR)
        self.assertEqual(out["judged"], {"priced": 2, "unpriceable": 1})
        self.assertEqual((records["eq:2"]["status"], records["eq:2"]["hs_source"], records["eq:2"]["hs_bp"]),
                         ("priced", "panel", 10.0))
        self.assertEqual((records["eq:3"]["status"], records["eq:3"]["final"]), ("unpriceable", True))

    def test_with_no_panel_store_a_panel_lot_is_unpriceable_and_with_an_unreadable_one_it_waits(self):
        out, records, opened, _ = self.round([panel_lot(2)], None)
        self.assertEqual((out["judged"], records["eq:2"]["status"], records["eq:2"]["final"]),
                         ({"unpriceable": 1}, "unpriceable", True))
        for fail in (LookupError("panel/hs.npy does not match its manifest"), RuntimeError("anything else")):
            out, records, opened, _ = self.round([panel_lot(1, symbol="SPY"), panel_lot(2), panel_lot(4)], fail)
            self.assertEqual((out["judged"], out["pending"], sorted(records)), ({"priced": 1}, 2, ["eq:1"]))
            self.assertTrue(all("cannot be read" in why for why in out["pending_why"]))
            opened.assert_called_once()


if __name__ == "__main__":
    unittest.main()
