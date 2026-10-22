"""THE PRICE LANE'S DATA LAYER (release 1019i; PREREG-EVL-8's harness plan H2): px.sqlite (league/events/pxstore.py)
and its recorders (league/events/pxdata.py), on a FROZEN CLOCK and an invented market: the Basic plan's 16-minute
clamp on every read, write-once values, the bucket's pacing with the lane first, FLAGGED on a synthetic split, the
270-session backfill resumed after a cut, the PX universe on the lane's own pure core that never writes the lane's
tables, the minute marks, and the House's scheduling (off by default, last of the plan, never near a decision, a
recorder's failure its own). Every symbol, bar and price here is invented.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import births as BI
from league.events import calendar as C
from league.events import house as H
from league.events import pxdata as PX
from league.events import pxstore as PS
from league.events import store as S
from league.events import universe as U

UTC = dt.timezone.utc
NY = C.NY


def wall(day: dt.date, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).astimezone(UTC)


def weekdays(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


D = dt.date(2026, 10, 22)        # the entry session (a Thursday)
P = dt.date(2026, 10, 21)        # the session before it


class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += float(s)


class Market:
    """SIP bars through the gateway's one route (invented): daily bars raw and adjusted (`split`: (symbol, effective day,
    ratio), every bar before the day divided by it in the adjusted series), 1Min bars, every request kept."""

    def __init__(self):
        self.daily = {}      # (symbol, day) -> (close, volume)
        self.minutes = {}    # symbol -> [bar]
        self.split = {}      # symbol -> (day, ratio)
        self.calls = []

    def get_json(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        assert path == PX.BARS_PATH, path
        names = params["symbols"].split(",")
        end = S.parse_iso(params["end"])
        out = {}
        if params["timeframe"] == "1Day":
            start = dt.date.fromisoformat(params["start"])
            for sym in names:
                rows = []
                for (s, day), (c, v) in sorted(self.daily.items()):
                    t = dt.datetime.combine(day, dt.time(4, 0), tzinfo=UTC)
                    if s != sym or day < start or t >= end:
                        continue
                    f = 1.0
                    if params["adjustment"] == "all" and sym in self.split and day < self.split[sym][0]:
                        f = 1.0 / self.split[sym][1]
                    rows.append({"t": S.iso(t), "o": c * f, "h": c * f, "l": c * f, "c": c * f, "v": v, "n": 10, "vw": c * f})
                out[sym] = rows
        else:
            start = S.parse_iso(params["start"])
            for sym in names:
                out[sym] = [b for b in self.minutes.get(sym, []) if start <= S.parse_iso(b["t"]) < end]
        return {"bars": out, "next_page_token": None}

    def requests(self, timeframe=None):
        return [p for _, p in self.calls if timeframe is None or p["timeframe"] == timeframe]


class PxCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "events"
        self.lane = S.Store(self.root)
        self.addCleanup(self.lane.close)
        with self.lane.tx() as db:
            for d in weekdays(dt.date(2025, 6, 1), dt.date(2026, 12, 31)):
                early = int(d == dt.date(2026, 11, 27))
                close = "13:00" if early else "16:00"
                db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, ?)",
                           (d.isoformat(), S.iso(wall(d, "09:30")), S.iso(wall(d, close)), early))
        self.px = PS.PxStore(self.root)
        self.addCleanup(self.px.close)
        self.market = Market()
        self.clock = Clock()
        self.bucket = PX.TokenBucket(clock=self.clock, sleep=self.clock.sleep)
        self.gw = PX.PxGateway(self.market, self.bucket)

    def run_id(self, now):
        return self.px.start_run("test", now=now)


class TheBucket(unittest.TestCase):
    def test_the_lane_first_and_150_a_minute(self):
        clock = Clock()
        b = PX.TokenBucket(clock=clock, sleep=clock.sleep)
        for _ in range(100):           # PX drains it to the lane's reserve and no further
            self.assertTrue(b.take_px())
        self.assertAlmostEqual(b.level(), 50.0)
        self.assertEqual(clock.t, 1000.0, "no wait while tokens are above the reserve")
        self.assertFalse(b.take_px(until=clock.t + 0.1), "a PX read never takes the lane's reserve")
        for _ in range(50):            # the lane takes its reserve at once
            b.take_lane()
        self.assertEqual(clock.t, 1000.0)
        b.take_lane()                  # the lane is never refused: it waits for its token
        self.assertAlmostEqual(clock.t, 1000.4, places=6)
        self.assertEqual(b.taken, {"lane": 51, "px": 100})
        # a PX read waits for the reserve to refill when its bound allows: 51 tokens at 2.5 a second
        start = clock.t
        self.assertTrue(b.take_px(until=clock.t + 60))
        self.assertAlmostEqual(clock.t - start, 51 / 2.5, places=6)

    def test_the_rate_over_a_long_run(self):
        clock = Clock()
        b = PX.TokenBucket(clock=clock, sleep=clock.sleep, reserve=0)
        for _ in range(150 + 300):
            self.assertTrue(b.take_px(until=None))
        self.assertAlmostEqual(clock.t - 1000.0, 120.0, places=6, msg="300 after the first 150: two minutes")

    def test_the_gateway_reads_the_sip_bars_route_only_and_stops_at_its_bound(self):
        clock = Clock()
        late = {"now": False}
        gw = PX.PxGateway(Market(), PX.TokenBucket(clock=clock, sleep=clock.sleep), late=lambda: late["now"])
        with self.assertRaises(ValueError):
            gw.get_json("/v1/alpaca/v2/stocks/ACME/trades", {"feed": "sip"})
        with self.assertRaises(ValueError):
            gw.get_json(PX.BARS_PATH, {"feed": "iex", "symbols": "A", "timeframe": "1Day", "start": "2026-10-01",
                                       "end": "2026-10-02T00:00:00Z"})
        gw.get_json(PX.BARS_PATH, {"feed": "sip", "symbols": "A", "timeframe": "1Day", "start": "2026-10-01",
                                   "end": "2026-10-02T00:00:00Z", "adjustment": "raw"})
        self.assertEqual(gw.requests, 1)
        late["now"] = True
        with self.assertRaises(PX.PxCut):
            gw.get_json(PX.BARS_PATH, {"feed": "sip", "symbols": "A", "timeframe": "1Day", "start": "2026-10-01",
                                       "end": "2026-10-02T00:00:00Z", "adjustment": "raw"})
        self.assertEqual(gw.requests, 1)


class TheClamp(PxCase):
    def test_daily_bars_end_at_sip_end_on_a_frozen_clock(self):
        self.market.daily[("ACME", P)] = (10.0, 1e6)
        self.market.daily[("ACME", D)] = (10.5, 1e6)
        now = wall(D, "15:00")
        PX.daily_bars(self.px, self.gw, ["ACME"], P, D, adj="raw", now=now, run=self.run_id(now))
        [asked] = self.market.requests("1Day")
        self.assertEqual(asked["end"], S.iso(now - dt.timedelta(minutes=16)), "16 minutes ago, not the day after")
        self.assertEqual(asked["feed"], "sip")
        later = wall(D + dt.timedelta(days=1), "10:00")
        PX.daily_bars(self.px, self.gw, ["ACME"], P, P, adj="raw", now=later, run=self.run_id(later))
        self.assertEqual(self.market.requests("1Day")[-1]["end"], "2026-10-22T00:00:00Z", "the day after the last session")

    def test_a_minute_span_is_read_only_once_it_is_whole_on_the_tape(self):
        s = C.session(self.lane, D)
        for i, minute in enumerate(range(0, 31)):
            t = wall(D, "15:00") + dt.timedelta(minutes=minute)
            self.market.minutes.setdefault("ACME", []).append({"t": S.iso(t), "c": 20.0 + i / 100, "v": 100})
        early = wall(D, "15:45")
        out = PX.minutes(self.px, self.gw, ["ACME"], s, "px1530", now=early, run=self.run_id(early))
        self.assertIn("not 16 minutes old", out["waiting"])
        self.assertEqual(self.market.calls, [], "nothing read before the span is whole")
        self.assertIsNone(self.px.minute("ACME", D, "px1530"))
        at = wall(D, "15:46")
        out = PX.minutes(self.px, self.gw, ["ACME"], s, "px1530", now=at, run=self.run_id(at))
        self.assertEqual(out["written"], 1)
        mark = self.px.minute("ACME", D, "px1530")
        self.assertEqual(mark["value"], 20.29, "the bar starting 15:29, never the one starting 15:30")
        self.assertEqual((mark["bars"], mark["last_t"]), (30, S.iso(wall(D, "15:29"))))
        [asked] = self.market.requests("1Min")
        self.assertEqual((asked["start"], asked["end"]), (S.iso(wall(D, "15:00")), S.iso(wall(D, "15:30"))))


class WriteOnce(PxCase):
    def test_a_decided_value_is_written_once_and_never_moves(self):
        now = wall(D, "15:46")
        run = self.run_id(now)
        self.assertTrue(self.px.put_features(D, "0000000001", "on", "ACME", {"zd": -2.5}, decided_at=now,
                                             inputs_at=S.iso(now - dt.timedelta(seconds=30)), bars_from="a", bars_to="b",
                                             source="live", run=run))
        self.assertFalse(self.px.put_features(D, "0000000001", "on", "ACME", {"zd": 9.9}, decided_at=now,
                                              inputs_at=S.iso(now), bars_from="a", bars_to="b", source="backfill",
                                              run=run))
        got = self.px.features(D, "0000000001", "on")
        self.assertEqual((got["value"], got["source"], got["run"]), ({"zd": -2.5}, "live", run))
        with self.assertRaises(ValueError):    # an input fetched after the decision
            self.px.put_features(D, "0000000002", "on", "BETA", {}, decided_at=now,
                                 inputs_at=S.iso(now + dt.timedelta(seconds=1)), bars_from=None, bars_to=None,
                                 source="live", run=run)
        with self.assertRaises(ValueError):
            self.px.put_features(D, "0000000002", "on", "BETA", {}, decided_at=now, inputs_at=S.iso(now),
                                 bars_from=None, bars_to=None, source="replay", run=run)
        # the bars' upsert moves no decided value
        self.px.put_bars([{"symbol": "ACME", "day": P.isoformat(), "t": "x", "c": 10.0}], adj="all", run=run, now=now)
        self.px.put_bars([{"symbol": "ACME", "day": P.isoformat(), "t": "x", "c": 5.0}], adj="all", run=run, now=now)
        self.assertEqual(self.px.features(D, "0000000001", "on")["value"], {"zd": -2.5})

    def test_minutes_flags_and_results_are_written_once(self):
        now = wall(D, "16:30")
        run = self.run_id(now)
        self.assertTrue(self.px.put_minute("ACME", D, "pm", 10.0, bars=5, first_t=None, last_t=None, run=run, now=now))
        self.assertFalse(self.px.put_minute("ACME", D, "pm", 11.0, bars=5, first_t=None, last_t=None, run=run, now=now))
        self.assertEqual(self.px.minute("ACME", D, "pm")["value"], 10.0)
        self.assertTrue(self.px.put_flag(D, "ACME", P, 10.0, 10.0, run=run, now=now))
        self.assertFalse(self.px.put_flag(D, "ACME", P, 10.0, 5.0, run=run, now=now))
        self.assertEqual(self.px.flag(D, "ACME")["flagged"], 0)
        self.assertTrue(self.px.put_result(D, "1", S.LIVE_RULE, None, why="adv", run=run, now=now))
        self.assertFalse(self.px.put_result(D, "1", S.LIVE_RULE, {"symbol": "ACME"}, why=None, run=run, now=now))
        self.assertEqual(self.px.universe(D), {})

    def test_every_px_table_is_refused_to_the_births_facts(self):
        self.assertTrue(PS.TABLES <= BI.FACTS_DENY)
        names = {r[0] for r in self.px.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual({n for n in names if n.startswith("px_")}, set(PS.TABLES))
        with BI.outcome_free(self.px.db):
            for table in PS.TABLES:
                with self.assertRaises(Exception, msg=table):
                    self.px.db.execute(f"SELECT * FROM {table}").fetchall()


class TheSplit(PxCase):
    def test_flagged_on_a_split_effective_d_and_not_on_a_quiet_name(self):
        for sym in ("SPLT", "QUIET", "DIV"):
            self.market.daily[(sym, P)] = (100.0, 1e6)
        self.market.split["SPLT"] = (D, 2.0)          # a 2:1 split effective D: P's adjusted close is half its raw one
        self.market.split["DIV"] = (D, 1.0004)        # a small dividend: inside the 0.1% tolerance
        before = wall(D, "08:59")
        with self.assertRaises(ValueError):
            PX.flags(self.px, self.gw, ["SPLT"], self.lane, D, now=before, run=self.run_id(before))
        now = wall(D, "09:05")
        out = PX.flags(self.px, self.gw, ["SPLT", "QUIET", "DIV", "GONE"], self.lane, D, now=now, run=self.run_id(now))
        self.assertEqual((out["written"], out["flagged"]), (4, 2))
        self.assertEqual(self.px.flag(D, "SPLT")["flagged"], 1)
        self.assertAlmostEqual(self.px.flag(D, "SPLT")["ratio"], 0.5)
        self.assertEqual(self.px.flag(D, "QUIET")["flagged"], 0)
        self.assertEqual(self.px.flag(D, "DIV")["flagged"], 0)
        self.assertEqual(self.px.flag(D, "GONE")["flagged"], 1, "no c*_P read: flagged")
        self.assertTrue(all(p["end"] <= S.iso(now - dt.timedelta(minutes=16)) for p in self.market.requests()))

    def test_an_adjustment_published_later_is_kept_beside_the_bar(self):
        self.market.daily[("SPLT", P)] = (100.0, 1e6)
        first = wall(D, "06:00")
        PX.daily_bars(self.px, self.gw, ["SPLT"], P, P, adj="all", now=first, run=self.run_id(first))
        self.market.split["SPLT"] = (D, 2.0)
        later = wall(D, "09:05")
        out = PX.daily_bars(self.px, self.gw, ["SPLT"], P, P, adj="all", now=later, run=self.run_id(later))
        self.assertEqual(out["moved"], 1)
        [move] = [dict(r) for r in self.px.db.execute("SELECT * FROM px_bar_moves")]
        self.assertEqual((move["c_was"], move["c_now"], move["was_at"]), (100.0, 50.0, S.iso(first)))
        self.assertEqual(self.px.bars("SPLT", [P], "all")[P.isoformat()]["c"], 50.0)


class TheBackfill(PxCase):
    def test_270_sessions_200_symbols_a_request_resumed_after_a_cut(self):
        names = [f"S{i:03d}" for i in range(250)]
        now = wall(D, "22:00")
        cuts = iter([False, False, True])
        out = PX.backfill(self.px, self.gw, names, self.lane, D, now=now, run=self.run_id(now),
                          late=lambda: next(cuts, False))
        self.assertFalse(out["done"])
        self.assertEqual(out["chunks"], 2)
        asked = self.market.requests("1Day")
        self.assertEqual(len(asked), 2)
        self.assertTrue(all(len(p["symbols"].split(",")) <= 200 for p in asked))
        prior = list(C.previous(self.lane, D, 270))
        self.assertEqual(len(prior), 270)
        self.assertEqual({p["start"] for p in asked}, {prior[0].day.isoformat()})
        self.assertIn("SPY", ",".join(p["symbols"] for p in asked), "both benchmarks")
        again = PX.backfill(self.px, self.gw, names, self.lane, D, now=now, run=self.run_id(now))
        self.assertTrue(again["done"])
        self.assertEqual(again["chunks"], 2, "only the adjusted chunks were left")
        self.assertEqual({p["adjustment"] for p in self.market.requests("1Day")}, {"raw", "all"})
        self.assertEqual(len(self.market.requests("1Day")), 4)
        self.assertIsNotNone(self.px.meta("px:backfill:done"))
        self.assertEqual(PX.backfill(self.px, self.gw, names, self.lane, D, now=now, run="x")["requests"], 0)


class TheUniverse(PxCase):
    def seed(self, sym, cik, *, close=20.0, volume=1e6, adjusted=61, operating=True, title="Co"):
        prior = list(C.previous(self.lane, D, 61))
        now = wall(D, "06:00")
        run = self.run_id(now)
        raw = [{"symbol": sym, "day": s.day.isoformat(), "t": "x", "c": close, "v": volume} for s in prior]
        self.px.put_bars(raw, adj="raw", run=run, now=now)
        self.px.put_bars(raw[len(raw) - adjusted:], adj="all", run=run, now=now)
        if operating is not None:
            self.px.db.execute("INSERT INTO cik_info(cik, sic, periodic_form, periodic_at, operating, checked_at) VALUES(?, "
                               "'3571', '10-Q', ?, NULL, ?)", (cik, "2026-08-01" if operating else None, S.iso(now)))
        return {cik: [(sym, title)]}

    def test_pxu_on_the_lanes_core_writing_nothing_of_the_lanes(self):
        tickers = {}
        tickers.update(self.seed("GOOD", "0000000001"))
        tickers.update(self.seed("CHEAP", "0000000002", close=4.0, volume=5e6))
        tickers.update(self.seed("THIN", "0000000003", close=20.0, volume=1e5))
        tickers.update(self.seed("SHORT", "0000000004", adjusted=60))
        tickers.update(self.seed("NEWCO", "0000000005", operating=None))
        tickers.update(self.seed("SHELL", "0000000006", operating=False))
        assets = {t: {"symbol": t, "status": "active", "tradable": True, "class": "us_equity", "exchange": "NYSE"}
                  for rows in tickers.values() for t, _ in rows}
        now = wall(D, "07:45")
        self.px.set_meta("px:backfill:done", S.iso(now))
        refused = PX.universe(self.px, self.lane, D, tickers=tickers, assets=assets, now=now, run="r0")
        self.assertIn("not current", refused["why"])
        self.px.set_meta(f"px:bars:{P.isoformat()}", S.iso(now))
        lane_before = {t: self.lane.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                       for t in ("eligibility", "universe", "cik_info", "bars")}
        out = PX.universe(self.px, self.lane, D, tickers=tickers, assets=assets, now=now, run=self.run_id(now))
        self.assertEqual((out["written"], out["eligible"], out["uncached"]), (5, 1, 1))
        lane_after = {t: self.lane.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in lane_before}
        self.assertEqual(lane_after, lane_before, "the lane's eligibility, universe, cache and bars are never written")
        [good] = self.px.universe(D).values()
        self.assertEqual((good["symbol"], good["prev_close"], good["adv20"], good["adv20sh"], good["bench"],
                          good["adjusted61"]), ("GOOD", 20.0, 20e6, 1e6, "IWM", 61))
        why = {r["cik"]: r["why"] for r in self.px.db.execute("SELECT cik, why FROM px_eligibility")}
        self.assertEqual(why, {"0000000001": None, "0000000002": "price", "0000000003": "adv",
                               "0000000004": "adjusted-bars", "0000000006": "not-operating"})
        again = PX.universe(self.px, self.lane, D, tickers=tickers, assets=assets, now=now, run="r2")
        self.assertEqual(again["written"], 0, "write-once: judged CIKs are not judged again")
        self.assertEqual(PX.names(self.px, D), ["GOOD"])
        self.assertEqual(PX.pm_names(self.px, D), ["GOOD"])

    def test_the_lanes_test_is_the_pure_core_and_its_writer(self):
        prior = list(C.previous(self.lane, D, 20))
        for s in prior:
            self.lane.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', "
                                 "10, 10, 10, 10, 200000, 'x')", (s.day.isoformat(),))
        tickers = {"0000000009": [("ACME", "Acme")]}
        assets = {"ACME": {"symbol": "ACME", "status": "active", "tradable": True, "class": "us_equity",
                           "exchange": "NASDAQ"}}
        core = U.eligible_row(self.lane, "0000000009", D, tickers=tickers, assets=assets, operating_ok=True)
        self.assertEqual(self.lane.db.execute("SELECT COUNT(*) FROM universe").fetchone()[0], 0, "the core writes nothing")
        row = U.eligible(self.lane, "0000000009", D, tickers=tickers, assets=assets, operating_ok=True)
        self.assertEqual(row, core)
        self.assertEqual(self.lane.db.execute("SELECT COUNT(*) FROM universe").fetchone()[0], 1)


class TheMinutes(PxCase):
    def test_the_premarket_needs_three_bars_with_volume(self):
        s = C.session(self.lane, D)
        for sym, vols in (("BUSY", (5, 0, 7, 9)), ("SLOW", (5, 0, 0, 9))):
            for i, v in enumerate(vols):
                self.market.minutes.setdefault(sym, []).append({"t": S.iso(wall(D, "08:10") + dt.timedelta(minutes=i)),
                                                                "c": 30.0 + i, "v": v})
        self.market.minutes["BUSY"].append({"t": S.iso(wall(D, "08:59")), "c": 99.0, "v": 1000})   # outside the span
        now = wall(D, "09:35")
        PX.minutes(self.px, self.gw, ["BUSY", "SLOW", "NONE"], s, "pm", now=now, run=self.run_id(now))
        self.assertEqual(self.px.minute("BUSY", D, "pm")["value"], 33.0)
        self.assertIsNone(self.px.minute("SLOW", D, "pm")["value"], "two bars with volume: no indication")
        self.assertEqual(self.px.minute("NONE", D, "pm")["bars"], 0, "no bar: stored as none, read once")

    def test_an_early_close_and_the_volume_through_1530(self):
        early = dt.date(2026, 11, 27)
        s = C.session(self.lane, early)
        self.assertTrue(s.early)
        self.assertEqual(PX.span_1530(s), (wall(early, "12:00"), wall(early, "12:30")))
        for i in range(0, 200):
            t = wall(early, "09:30") + dt.timedelta(minutes=i)
            self.market.minutes.setdefault("ACME", []).append({"t": S.iso(t), "c": 10.0, "v": 2})
        now = wall(early, "13:30")
        PX.minutes(self.px, self.gw, ["ACME"], s, "v1530", now=now, run=self.run_id(now))
        self.assertEqual(self.px.minute("ACME", early, "v1530")["value"], 2.0 * 180, "09:30 to the bar ending 12:30")


GB = 2 ** 30


class HouseCase(unittest.TestCase):
    """A lane on an invented calendar; the state disk's free space is invented too (100 GB, `PS.disk_free`), so no
    test reads the build machine's own disk."""

    def lane(self, root, **settings):
        from league.tests.test_events_score_batch import FakeHouse, Mono

        self.house = FakeHouse(wall(D, "12:00"))
        self.mono = Mono()
        lane = H.EventLane(self.house, root, settings=settings, monotonic=self.mono, sleep=self.mono.advance)
        lane._redecide_next = dt.datetime(2100, 1, 1, tzinfo=UTC)
        lane._open_checked = dt.datetime(2100, 1, 1, tzinfo=UTC)
        return lane

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "events"
        with S.Store(self.root) as st:
            with st.tx() as db:
                for d in weekdays(dt.date(2025, 6, 1), dt.date(2026, 12, 31)):
                    db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, 0)",
                               (d.isoformat(), S.iso(wall(d, "09:30")), S.iso(wall(d, "16:00"))))
        self.free = 100 * GB
        patch = mock.patch.object(PS, "disk_free", lambda root: self.free)
        patch.start()
        self.addCleanup(patch.stop)

    def at(self, lane, when):
        lane.house.at = when.timestamp()


class TheHouse(HouseCase):
    """The House's scheduling of the recorders (league/events/house.py `_px_due`)."""

    def test_off_by_default_and_no_bucket(self):
        lane = self.lane(self.root)
        self.assertFalse(lane.px_on)
        self.assertIsNone(lane._bucket)
        with S.Store(self.root) as st:
            self.assertIsNone(lane._px_due(st, wall(D, "23:00"), D, C.session(st, D), []))
        self.assertFalse(PS.path_of(self.root).exists(), "off: px.sqlite is never made")

    def test_on_the_backfill_at_night_never_near_a_decision_and_never_in_the_day(self):
        lane = self.lane(self.root, px_data=True)
        self.assertIsNotNone(lane._bucket)
        with S.Store(self.root) as st:
            s = C.session(st, D)
            self.assertIsNone(lane._px_due(st, wall(D, "12:00"), D, s, []), "the backfill waits for the night")
            task = lane._px_due(st, wall(D, "22:00"), D, s, [])
            self.assertEqual((task.name, task.budget, task.cut), ("px-backfill", H.PX_BUDGET, True))
            nxt = dt.date(2026, 10, 23)
            self.assertIsNone(lane._px_due(st, wall(nxt, "09:06"), nxt, C.session(st, nxt), []),
                              "within 10 minutes of the 09:15 decision")
            self.assertIsNone(lane._px_due(st, wall(nxt, "06:59") + dt.timedelta(minutes=7), nxt,
                                           C.session(st, nxt), []), "07:06 is the day: no backfill")

    def test_the_recorders_after_the_backfill_and_the_plan_puts_them_last(self):
        lane = self.lane(self.root, px_data=True)
        with PS.PxStore(self.root) as px:
            px.set_meta("px:backfill:done", "x")
            px.put_result(D, "1", S.LIVE_RULE, {"symbol": "ACME", "adv20": 3e7}, why=None, run="r",
                          now=wall(D, "07:45"))
        with S.Store(self.root) as st:
            s = C.session(st, D)
            self.assertEqual(lane._px_due(st, wall(D, "07:45"), D, s, []).name, "px-universe")
            self.assertEqual(lane._px_due(st, wall(D, "09:01"), D, s, []).name, "px-flags", "14 minutes before 09:15")
            self.assertIsNone(lane._px_due(st, wall(D, "09:06"), D, s, []), "within 10 minutes of the 09:15 decision")
            self.assertEqual(lane._px_due(st, wall(D, "09:36"), D, s, []).name, "px-flags")
            with PS.PxStore(self.root) as px:
                px.set_meta(f"px:flags:{D}", "x")
            self.assertEqual(lane._px_due(st, wall(D, "09:36"), D, s, []).name, "px-pm")
            self.assertIsNone(lane._px_due(st, wall(D, "15:40"), D, s, []), "the close decision's ten minutes")
            self.assertEqual(lane._px_due(st, wall(D, "16:06"), D, s, []).name, "px-pm")
            with PS.PxStore(self.root) as px:
                px.set_meta(f"px:pm:{D}", "x")
            self.assertEqual(lane._px_due(st, wall(D, "16:06"), D, s, []).name, "px-px1530")

    def test_a_recorder_that_fails_is_its_own_failure(self):
        lane = self.lane(self.root, px_data=True)
        with S.Store(self.root) as st:
            ctx = H.LaneContext(lane, st, H.LaneGateway(object(), lane, None, cut=False), lambda url: b"", lane.now)

            def boom(*a):
                raise RuntimeError("an invented failure")
            out = lane._px(ctx, None, "daily", boom)
            self.assertEqual(out["_status"], "failed")
            self.assertIn("px-daily", lane._failed)
            with PS.PxStore(self.root) as px:
                self.assertEqual(px.last_run("daily")["status"], "failed")
            self.assertTrue(lane._quiet("px-daily", lane.now(), []))
            cut = lane._px(ctx, None, "flags", lambda *a: (_ for _ in ()).throw(PX.PxCut("bound")))
            self.assertEqual(cut["_status"], "cut")
            self.assertNotIn("px-flags", lane._failed, "a cut is no failure")

    def test_the_lane_takes_its_token_first(self):
        lane = self.lane(self.root, px_data=True)
        lane.throttle()
        self.assertEqual(lane._bucket.taken["lane"], 1)
        off = self.lane(self.root)
        off.throttle()       # (no bucket: the lane's spacing alone, as before)


class TheRoom(HouseCase):
    """THE STORE'S ROOM (release 1019i's review; PREREG-EVL-8's harness plan H2, its risk list: "a size line and a 2 GB
    alarm"; league/events/pxstore.py `room`): px.sqlite under 2 GiB and the state disk above the PX floor (the swarm
    guard's 3 GB and 2 GB more), checked before every PX run and every request of one; without room nothing is
    written, every PX run waits FAIL_BACKOFF, and lane.json says so."""

    def ctx(self, lane, st, gateway=None):
        return H.LaneContext(lane, st, H.LaneGateway(gateway or Market(), lane, None, cut=False), lambda url: b"",
                             lane.now)

    def lane_on(self):
        from league.tests.test_events_score_batch import FakeHouse, Mono

        lane = H.EventLane(FakeHouse(wall(D, "22:00")), self.root, settings={"px_data": True}, monotonic=Mono(),
                           sleep=lambda s: None)
        lane.gateway = lambda: Market()
        return lane

    def test_the_lines(self):
        ok = PS.room(self.root)
        self.assertEqual((ok["ok"], ok["over"], ok["low"], ok["why"]), (True, False, False, None))
        self.assertEqual((PS.MAX_BYTES, PS.FREE_FLOOR_BYTES), (2 * GB, 5 * GB))
        self.free = 5 * GB - 1
        low = PS.room(self.root)
        self.assertFalse(low["ok"])
        self.assertIn("under the PX floor of 5.0 GB", low["why"])
        self.free = None
        self.assertIn("could not be read", PS.room(self.root)["why"], "unread is no room")
        self.free = 100 * GB
        with PS.PxStore(self.root) as px:
            px.set_meta("x", "y")
            self.assertEqual(px.size_bytes(), PS.stored_bytes(self.root))
        with mock.patch.object(PS, "MAX_BYTES", PS.stored_bytes(self.root)):
            over = PS.room(self.root)
        self.assertEqual((over["ok"], over["over"]), (False, True))
        self.assertIn("at or over its", over["why"])

    def test_a_run_without_room_opens_nothing_and_every_px_run_waits(self):
        lane = self.lane_on()
        self.free = 4 * GB
        called = []
        with S.Store(self.root) as st:
            out = lane._px(self.ctx(lane, st), None, "backfill", lambda *a: called.append(a) or {"rows": 1})
            self.assertEqual(out["_status"], "disk")
            self.assertEqual(called, [], "the recorder never ran")
            self.assertFalse(PS.path_of(self.root).exists(), "px.sqlite not even made")
            said = lane.health()["px_store"]
            self.assertEqual((said["ok"], said["free_bytes"]), (False, 4 * GB))
            self.assertIn("under the PX floor", said["why"])
            self.assertEqual(lane._warnings, 1, "warned (at most once an hour)")
            s = C.session(st, D)
            soon: list = []
            later = wall(D, "22:00") + H.PX_EVERY
            self.free = 100 * GB
            self.assertIsNone(lane._px_due(st, later, D, s, soon), "no PX run within FAIL_BACKOFF of a run with no room")
            self.assertIn(wall(D, "22:00") + H.FAIL_BACKOFF, soon)
            task = lane._px_due(st, wall(D, "22:00") + H.FAIL_BACKOFF, D, s, [])
            self.assertEqual(task.name, "px-backfill", "with room again the recorders go on")

    def test_a_store_at_its_line_writes_nothing(self):
        lane = self.lane_on()
        with PS.PxStore(self.root) as px:
            run = px.start_run("daily", now=wall(P, "22:00"))
            px.finish_run(run, "ok", now=wall(P, "22:01"))
        size = PS.stored_bytes(self.root)
        with S.Store(self.root) as st, mock.patch.object(PS, "MAX_BYTES", size):
            out = lane._px(self.ctx(lane, st), None, "daily", lambda *a: {"rows": 1})
        self.assertEqual(out["_status"], "disk")
        self.assertEqual(PS.stored_bytes(self.root), size, "not a byte written")
        with PS.PxStore(self.root) as px:
            self.assertEqual(px.db.execute("SELECT COUNT(*) FROM px_runs").fetchone()[0], 1, "no run row either")

    def test_a_run_stops_before_the_page_that_would_cross_the_line(self):
        lane = self.lane_on()
        market = Market()
        for sym in ("AAA", "BBB"):
            for d in (P, D):
                market.daily[(sym, d)] = (10.0, 1e6)
        lane.gateway = lambda: market

        def two_chunks(ctx, px, gw, run, deadline):
            PX.daily_bars(px, gw, ["AAA"], P, D, adj="raw", now=wall(D, "22:00"), run=run)
            self.free = 4 * GB        # the disk fills between two pages (invented)
            PX.daily_bars(px, gw, ["BBB"], P, D, adj="raw", now=wall(D, "22:00"), run=run)
            return {"rows": 99}
        with S.Store(self.root) as st:
            out = lane._px(self.ctx(lane, st, market), None, "daily", two_chunks)
        self.assertEqual(out["_status"], "disk")
        self.assertEqual(len(market.requests("1Day")), 1, "the second request never went")
        with PS.PxStore(self.root) as px:
            self.assertEqual(px.bars("AAA", [P, D]).keys(), {P.isoformat(), D.isoformat()})
            self.assertEqual(px.bars("BBB", [P, D]), {}, "nothing of the page that would have crossed")
            row = px.last_run("daily")
        self.assertEqual(row["status"], "disk")
        self.assertEqual(row["free_bytes"], 100 * GB, "the free space at its start")
        self.assertGreater(row["size_bytes"], 0, "px.sqlite's size at its end")
        self.assertIsNotNone(lane._px_disk, "every PX run then waits FAIL_BACKOFF")

    def test_an_ok_run_records_its_room(self):
        lane = self.lane_on()
        with S.Store(self.root) as st:
            out = lane._px(self.ctx(lane, st), None, "daily", lambda *a: {"rows": 0})
        self.assertEqual(out["_status"], "ok")
        with PS.PxStore(self.root) as px:
            row = px.last_run("daily")
        self.assertEqual((row["status"], row["free_bytes"]), ("ok", 100 * GB))
        self.assertGreater(row["size_bytes"], 0)
        self.assertTrue(lane.health()["px_store"]["ok"])


class OnlyWarming(unittest.TestCase):
    def test_no_decision_judge_or_money_module_reads_the_price_lanes_store(self):
        """With `events.px_data` on the recorders only warm px.sqlite: no module that decides, judges or trades opens it
        (PREREG-EVL-8's programs, H3, are the first readers, in their own release)."""
        events = Path(__file__).resolve().parents[1] / "events"
        for name in ("run.py", "book.py", "screen.py", "score.py", "bands.py", "done.py", "programs.py", "universe.py"):
            text = (events / name).read_text(encoding="utf-8")
            for word in ("pxstore", "pxdata", "px.sqlite", "PxStore"):
                self.assertNotIn(word, text, f"{name} names {word}")
        equity = Path(__file__).resolve().parents[1] / "equity"
        for path in equity.glob("*.py"):
            self.assertNotIn("pxstore", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
