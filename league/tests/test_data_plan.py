"""THE ALPACA DATA PLAN (release R0, Oct 19, 2026; league/data_plan.py): the House's market-data reads on Alpaca's free
Basic plan. `BasicPlan` is the plan as it answered through the gateway on Oct 19, 2026 (the module docstring's
measurements): SIP snapshots refused, a SIP read ending inside the last 15 minutes refused (a date-only end being the
end of that New York day), OPRA refused, a start after its end a 400. The invented prices are the tests' own."""

import copy
import dataclasses
import datetime as dt
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from decimal import Decimal as D
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league import data_plan as P
from league.equity import live as L
from league.equity import schedule as S
from league.live import money as M
from league.live.venue import MarketData, VenueError, occ_parts, parse_time
from league.tests.test_equity_book import FRIDAY, MONDAY, TUESDAY, BookTest, Harness, at, family_row, iso

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def utc(y, mo, d, h=0, mi=0, s=0) -> float:
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=UTC).timestamp()


class BasicPlan:
    """Alpaca's market data on the Basic plan, for `MarketData`'s GETs (`request(method, url, what=...)`)."""

    RECENT = {"message": "subscription does not permit querying recent SIP data"}
    OPRA = {"message": "subscription does not permit querying OPRA data"}

    def __init__(self, clock, *, bar_rows=None, quotes=None):
        self.clock = clock
        self.bar_rows = bar_rows if bar_rows is not None else {"raw": {}, "all": {}}
        self.quotes = quotes if quotes is not None else {}          # {symbol: (bid, ask)}: a two-sided IEX book
        self.rows: dict[str, dict] = {}                              # {symbol: snapshot row}: one the test wrote
        self.urls: list[str] = []
        self.timeout = 30.0

    @staticmethod
    def _end(value: str) -> float:
        if len(value) == 10:                                        # a date-only end: the end of that New York day
            day = dt.date.fromisoformat(value) + dt.timedelta(days=1)
            return dt.datetime.combine(day, dt.time(), NY).timestamp()
        return parse_time(value)

    @staticmethod
    def _start(value: str) -> float:
        if len(value) == 10:
            return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), UTC).timestamp()
        return parse_time(value)

    def snapshot(self, symbol: str) -> dict:
        if symbol in self.rows:
            return copy.deepcopy(self.rows[symbol])
        bid, ask = self.quotes[symbol]
        t = iso(self.clock() - 1)
        bar = {"t": iso(self.clock() - 60)[:17] + "00Z", "o": float(bid), "h": float(ask), "l": float(bid),
               "c": float(ask), "v": 1234}
        return {"latestQuote": {"bp": float(bid), "ap": float(ask), "bs": 1, "as": 1, "t": t},
                "latestTrade": {"p": float((bid + ask) / 2), "s": 10, "t": t},
                "minuteBar": dict(bar), "dailyBar": dict(bar), "prevDailyBar": dict(bar)}

    def request(self, method, url, *, what=None, headers=None, **_):
        self.urls.append(url)
        parts = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        feed = q.get("feed")
        if parts.path.startswith("/v1beta1/options/"):
            return (403, dict(self.OPRA)) if feed == "opra" else (200, {"snapshots": {}, "next_page_token": None})
        if parts.path == "/v2/stocks/snapshots":
            if feed == "sip":
                return 403, dict(self.RECENT)
            return 200, {s: self.snapshot(s) for s in q["symbols"].split(",")}
        if parts.path == "/v2/stocks/bars":
            limit = self.clock() - 15 * 60
            end = self._end(q["end"]) if q.get("end") else limit
            if feed == "sip" and end > limit:
                return 403, dict(self.RECENT)
            start = self._start(q["start"])
            if start > end:
                return 400, {"message": "end should not be before start"}
            rows = self.bar_rows.get(q.get("adjustment", "raw"), {})
            return 200, {"bars": {s: [dict(r) for r in rows.get(s, []) if start <= parse_time(r["t"]) <= end]
                                  for s in q["symbols"].split(",")}, "next_page_token": None}
        return 404, {"message": "not found"}

    def sent(self, path: str) -> list[dict]:
        """The queries of every request to `path`."""
        return [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)) for u in self.urls
                if urllib.parse.urlsplit(u).path == path]


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = float(t)


# ------------------------------------------------------------------------------------------------- rule 1, the SIP window
class TheSipWindow(unittest.TestCase):
    def test_the_plans_answers_as_measured(self):
        """The reads of Oct 19, 2026 (the module docstring): a refused read is clamped, an answered one is sent as it
        was."""
        first, second = utc(2026, 10, 19, 0, 21, 58), utc(2026, 10, 19, 0, 24, 20)
        cases = [  # (now, end, the plan refused it)
            (first, "2026-10-19T00:07:58Z", True),    # now - 14 min
            (first, "2026-10-19T00:05:58Z", False),   # now - 16 min
            (first, "2026-10-19T00:01:58Z", False),   # now - 20 min
            (first, "2026-10-19", True),              # today (UTC)
            (first, "2026-10-20", True),              # tomorrow
            (first, "2026-10-16", False),             # a past New York day
            (second, "2026-10-18", True),             # today in New York: the day ends at 04:00Z Oct 19
            (second, "2026-10-18T23:59:59Z", False),
        ]
        for now, end, refused in cases:
            sent = P.sip_end(end, now=now)
            if refused:
                self.assertEqual(sent, "2026-10-19T00:05:58Z" if now == first else "2026-10-19T00:08:20Z", end)
            else:
                self.assertEqual(sent, end, end)

    def test_a_date_only_end_is_the_end_of_its_new_york_day(self):
        self.assertEqual(P.bound("2026-10-18", end=True), utc(2026, 10, 19, 4))     # EDT
        self.assertEqual(P.bound("2026-12-01", end=True), utc(2026, 12, 2, 5))      # EST
        self.assertEqual(P.bound("2026-10-18", end=False), utc(2026, 10, 18))       # a start: its earliest reading
        self.assertEqual(P.bound("2026-10-18T20:04:00Z", end=True), utc(2026, 10, 18, 20, 4))
        self.assertIsNone(P.bound("2026-10-18T20:04:00", end=True), "an instant with no zone is no instant")
        self.assertIsNone(P.bound(None, end=True))

    def test_none_stays_none_and_an_unreadable_end_is_sent_as_it_was(self):
        now = utc(2026, 10, 19, 20, 20)
        self.assertIsNone(P.sip_end(None, now=now))
        self.assertEqual(P.sip_end("soon", now=now), "soon")
        self.assertEqual(P.sip_end("2026-10-19T20:04:00Z", now=now), "2026-10-19T20:04:00Z", "exactly the cut-off")
        self.assertEqual(P.sip_end("2026-10-19T20:04:01Z", now=now), "2026-10-19T20:04:00Z")
        self.assertEqual(P.sip_end("2026-10-19T20:04:00Z", now=now + 0.9), "2026-10-19T20:04:00Z", "whole seconds")

    def test_a_window_after_its_clamped_end_is_empty(self):
        now = utc(2026, 10, 19, 20, 20)
        self.assertEqual(P.sip_window("2026-10-19T20:10:00Z", "2026-10-19T20:19:00Z", now=now),
                         ("2026-10-19T20:04:00Z", True))
        self.assertEqual(P.sip_window("2026-10-19T19:00:00Z", "2026-10-19T20:19:00Z", now=now),
                         ("2026-10-19T20:04:00Z", False))
        self.assertEqual(P.sip_window("2026-10-19", "2026-10-20", now=now), ("2026-10-19T20:04:00Z", False))
        self.assertEqual(P.sip_window("2026-10-19T20:10:00Z", None, now=now), (None, True))
        self.assertEqual(P.sip_window(None, None, now=now), (None, False))

    def test_a_jobs_read_is_clamped_only_on_the_sip_history_routes(self):
        now = utc(2026, 10, 20, 1, 0)                                            # direction's 01:00Z run
        bars = {"symbols": "SPY", "timeframe": "1Day", "start": "2024-12-31", "end": "2026-10-19", "feed": "sip"}
        self.assertEqual(P.sip_params("/v1/alpaca/v2/stocks/bars", bars, now=now)["end"], "2026-10-20T00:44:00Z")
        self.assertEqual(bars["end"], "2026-10-19", "the job's own params are never changed in place")
        for path in ("/v1/alpaca/v2/stocks/SPY/bars", "/v1/alpaca/v2/stocks/quotes", "/v1/alpaca/v2/stocks/trades",
                     "/v1/alpaca-paper/v2/stocks/bars"):
            self.assertEqual(P.sip_params(path, bars, now=now)["end"], "2026-10-20T00:44:00Z", path)
        for path in ("/v1/alpaca/v2/stocks/snapshots", "/v1/alpaca/v2/stocks/quotes/latest", "/v1/alpaca/v2/account",
                     "/v1/alpaca/v1beta1/options/bars"):
            self.assertIs(P.sip_params(path, bars, now=now), bars, path)
        for params in ({**bars, "feed": "iex"}, {k: v for k, v in bars.items() if k != "feed"},
                       {k: v for k, v in bars.items() if k != "end"}, {**bars, "end": "2026-10-16"},
                       {**bars, "start": "2026-10-20T00:50:00Z", "end": "2026-10-20T00:59:00Z"}):
            self.assertIs(P.sip_params("/v1/alpaca/v2/stocks/bars", params, now=now), params, params)


class TheDailyFetchAt1620(unittest.TestCase):
    """The equity book's 16:20 ET read (`schedule.Moments.bars_at`, the constitution's `bars_after_close_s`) still holds
    the day's whole bar: its clamped end lies after the close (16:04 ET), and the bar is stamped inside the window."""

    def offsets(self):
        return M.Table.from_constitution().equity.offsets

    def test_the_clamped_end_is_after_the_close_on_every_kind_of_session(self):
        for day in (dt.date(2026, 10, 19), dt.date(2026, 12, 1), dt.date(2026, 11, 27)):   # EDT, EST, a 13:00 close
            m = S.moments(day, self.offsets())
            self.assertIsNotNone(m, day)
            for late in (3.0, 45.0):                                                  # the House minute's own lateness
                now = m.bars_at + late
                end = (day + dt.timedelta(days=1)).isoformat()                       # what `_fetch_bars` asks for
                sent, empty = P.sip_window((day - dt.timedelta(days=60)).isoformat(), end, now=now)
                self.assertFalse(empty)
                sent_at = P.bound(sent, end=True)
                self.assertGreater(sent_at, m.close_at, f"{day}: the end {sent} is after the close")
                self.assertLessEqual(sent_at, now - 15 * 60, "inside what the plan serves")
                stamp = dt.datetime.combine(day, dt.time(), NY).timestamp()          # the 1Day bar's own time
                self.assertLessEqual(stamp, sent_at)
                close = dt.datetime.fromtimestamp(m.close_at, NY)
                self.assertEqual(dt.datetime.fromtimestamp(P.cutoff(m.bars_at), NY) - close, dt.timedelta(minutes=4))

    def test_the_constitutions_bars_offset_leaves_the_close_inside_the_window(self):
        """A `bars_after_close_s` under the SIP window plus a minute would end the 16:20 read before the close's last
        minute: the day's bar would be read before its close settled. The constitution's (1200) is not one."""
        self.assertGreaterEqual(int(self.offsets()["bars_after_close_s"]), P.SIP_DELAY_SECONDS + 60)


# ------------------------------------------------------------------------------------------------- the live path's reads
class ThePlansMarketData(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(at(dt.date(2026, 10, 19), 16, 20))
        self.alpaca = BasicPlan(self.clock, quotes={"SPY": (D("600.00"), D("600.02")), "QQQ": (D("500.00"), D("500.04"))})
        self.market = P.PlanMarketData(self.alpaca, option_feed="off", stock_feed="sip", snapshot_feed="iex",
                                       clock=self.clock)

    def test_snapshots_are_iexs_without_its_bars(self):
        rows = self.market.stocks(["spy", "QQQ"])
        self.assertEqual(self.alpaca.sent("/v2/stocks/snapshots"), [{"symbols": "QQQ,SPY", "feed": "iex"}])
        self.assertEqual(sorted(rows), ["QQQ", "SPY"])
        for row in rows.values():
            self.assertEqual(sorted(row), ["latestQuote", "latestTrade"], "no IEX bar reaches a reader")
        self.assertEqual(rows["SPY"]["latestQuote"]["ap"], 600.02)

    def test_the_old_shape_is_refused_by_the_plan(self):
        """The release before R0 read SIP snapshots: the plan refuses them, as it did on Oct 19."""
        old = MarketData(self.alpaca, option_feed="opra", stock_feed="sip", clock=self.clock)
        with self.assertRaisesRegex(VenueError, "recent SIP data"):
            old.stocks(["SPY"])
        with self.assertRaisesRegex(VenueError, "recent SIP data"):
            old.bars(["SPY"], timeframe="1Day", start="2026-09-01", end="2026-10-20")
        with self.assertRaisesRegex(VenueError, "OPRA"):
            old.chain("SPY", expiry_from="2026-10-19", expiry_to="2026-10-23")

    def test_one_feed_for_both_keeps_the_snapshots_bars(self):
        both = P.PlanMarketData(self.alpaca, option_feed="off", stock_feed="iex", snapshot_feed="iex", clock=self.clock)
        self.assertIn("minuteBar", both.stocks(["SPY"])["SPY"])
        self.assertEqual(P.PlanMarketData(self.alpaca, stock_feed="iex").snapshot_feed, "iex")

    def test_the_bars_ask_inside_the_sip_window_and_return_the_days_bar(self):
        day = dt.date(2026, 10, 19)
        self.alpaca.bar_rows["raw"]["SPY"] = [{"t": f"{d}T04:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 9}
                                              for d in ("2026-10-15", "2026-10-16", "2026-10-19")]
        rows = self.market.bars(["SPY"], timeframe="1Day", start="2026-09-01", end=(day + dt.timedelta(days=1)).isoformat())
        [sent] = self.alpaca.sent("/v2/stocks/bars")
        self.assertEqual((sent["start"], sent["end"], sent["feed"]), ("2026-09-01", "2026-10-19T20:04:03Z", "sip"))
        self.assertEqual([r["t"][:10] for r in rows["SPY"]], ["2026-10-15", "2026-10-16", "2026-10-19"])
        self.market.bars(["SPY"], timeframe="1Day", start="2026-09-01", end="2026-10-16")
        self.assertEqual(self.alpaca.sent("/v2/stocks/bars")[-1]["end"], "2026-10-16", "a past end is sent as it was")
        self.market.bars(["SPY"], timeframe="1Day", start="2026-09-01")
        self.assertNotIn("end", self.alpaca.sent("/v2/stocks/bars")[-1], "no end: the plan's own default")

    def test_a_window_the_plan_cannot_serve_yet_is_empty_and_never_sent(self):
        asked = len(self.alpaca.urls)
        out = self.market.bars(["SPY", "qqq"], timeframe="1Min", start=iso(self.clock() - 300), end=iso(self.clock()))
        self.assertEqual(out, {"QQQ": [], "SPY": []})
        self.assertEqual(len(self.alpaca.urls), asked)
        with self.assertRaises(ValueError):
            self.market.bars(["SPY"], timeframe="1Min", start=iso(self.clock() - 300), adjustment="split")

    def test_iex_bars_are_never_clamped(self):
        iex = P.PlanMarketData(self.alpaca, stock_feed="iex", snapshot_feed="iex", clock=self.clock)
        iex.bars(["SPY"], timeframe="1Day", start="2026-09-01", end="2026-10-20")
        self.assertEqual(self.alpaca.sent("/v2/stocks/bars")[-1]["end"], "2026-10-20")

    def test_options_off_refuses_at_once_and_asks_nothing(self):
        for read in (lambda: self.market.chain("SPY", expiry_from="2026-10-19", expiry_to="2026-10-23", max_pages=2),
                     lambda: self.market.contracts(["SPY261023C00600000"], timeout=3.0)):
            with self.assertRaisesRegex(VenueError, "options market data is off"):
                read()
        self.assertEqual(self.alpaca.urls, [])
        self.assertEqual(self.market.calls, 0, "no request counted: the plan's allowance is not spent")

    def test_an_option_feed_the_plan_serves_reads_as_before(self):
        on = P.PlanMarketData(self.alpaca, option_feed="indicative", stock_feed="sip", snapshot_feed="iex", clock=self.clock)
        self.assertEqual(on.chain("SPY", expiry_from="2026-10-19", expiry_to="2026-10-23"), {})
        self.assertEqual(self.alpaca.sent("/v1beta1/options/snapshots/SPY")[0]["feed"], "indicative")


class TheServiceAndTheConfiguration(unittest.TestCase):
    def test_the_configuration_names_the_plans_feeds(self):
        from league.service import load_config

        config = load_config()
        self.assertEqual((config["alpaca_feed"], config["alpaca_snapshot_feed"], config["alpaca_option_feed"]),
                         ("sip", "iex", "off"))

    def test_the_live_path_is_built_on_the_plans_market_data(self):
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover
            self.skipTest("numpy not installed")
        from league import service

        built = {}

        class Live:
            def __init__(self, root, *, market, **kw):
                built["market"] = market

        house = mock.Mock()
        config = {**service.load_config(), "gateway_url": "https://gateway.test"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch("league.live.step.OptionsLive", Live), \
                mock.patch.object(service, "gateway_kill_switch", return_value=lambda: False):
            service.options_live(house, Path(tmp), config, real_money=False, token=lambda: "t" * 40)
        market = built["market"]
        self.assertIsInstance(market, P.PlanMarketData)
        self.assertEqual((market.stock_feed, market.snapshot_feed, market.option_feed), ("sip", "iex", "off"))
        old = {k: v for k, v in config.items() if k != "alpaca_snapshot_feed"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch("league.live.step.OptionsLive", Live), \
                mock.patch.object(service, "gateway_kill_switch", return_value=lambda: False):
            service.options_live(house, Path(tmp), old, real_money=False, token=lambda: "t" * 40)
        self.assertEqual(built["market"].snapshot_feed, "iex", "without the key: IEX, the plan's real-time feed")

    def test_the_plan_is_behind_the_wall(self):
        from league import ci

        self.assertIn("league/data_plan.py", ci.FORBIDDEN)
        self.assertTrue(ci.guard(["league/data_plan.py"], None))


# ------------------------------------------------------------------------------------------------- the equity book on Basic
class PlanHarness(Harness):
    """The equity book's harness with its market data the live path's, on `BasicPlan` (its bars the test market's)."""

    plan = True

    def new_book(self) -> L.EquityBook:
        if not hasattr(self, "alpaca"):
            self.alpaca = BasicPlan(self.clock, bar_rows=self.market.bar_rows, quotes=self.market.quotes)
        if self.plan:
            self.data = P.PlanMarketData(self.alpaca, option_feed="off", stock_feed="sip", snapshot_feed="iex",
                                         clock=self.clock)
        else:
            self.data = MarketData(self.alpaca, option_feed="opra", stock_feed="sip", clock=self.clock)
        return L.EquityBook(self.state, self.venue, self.data, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=lambda: self.E, options_book=self.options,
                            clock=self.clock, record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                            alert=lambda level, text: self.alerts.append((level, text)))


class OldHarness(PlanHarness):
    plan = False


class TheEquityBookOnBasic(BookTest):
    def harness(self, cls=PlanHarness, *, case: str = "", **kw):
        root = self.root / case if case else self.root
        root.mkdir(parents=True, exist_ok=True)
        h = cls(root, **kw)
        self.addCleanup(h.state.close)
        return h

    def decided(self, cls=PlanHarness):
        h = self.harness(cls)
        h.families.rows = {"seed-overnight-spy": family_row()}
        inst = h.instance()
        h.decide_setup(MONDAY)
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5}]
        return h, inst

    def monday_bars(self, h):
        return h.state.rows("SELECT adjustment FROM eq_bars WHERE day=? AND symbol='SPY'", ("2026-10-12",))

    def test_the_1620_read_holds_the_days_bar_and_the_decide_follows(self):
        h, inst = self.decided()
        h.tick(16, 21)
        sent = h.alpaca.sent("/v2/stocks/bars")
        self.assertEqual({q["adjustment"] for q in sent}, {"raw", "all"})
        for q in sent:
            self.assertEqual(q["feed"], "sip")
            end = parse_time(q["end"])
            self.assertGreater(end, at(MONDAY, 16, 0, 0), "after the close")
            self.assertLessEqual(end, h.clock() - 15 * 60, "inside what the plan serves")
        self.assertEqual({r["adjustment"] for r in self.monday_bars(h)}, {"raw", "all"})
        h.tick(16, 31)
        self.assertEqual(h.state.get("eq_decide")["status"], "done")
        self.assertEqual([i.kind for i in h.intents(instance=inst.id) if i.status == "planned"], ["buy"])

    def test_the_release_before_could_not_read_the_day(self):
        h, _ = self.decided(OldHarness)
        h.tick(16, 21)
        self.assertEqual(self.monday_bars(h), [], "the plan refused the 16:20 read")
        self.assertTrue(h.alpaca.sent("/v2/stocks/bars"))

    def test_the_morning_audit_reads_the_decision_again(self):
        h, inst = self.decided()
        h.tick(16, 31)
        self.assertEqual(h.state.get("eq_decision")["end"], "2026-10-13", "the decision's own end, unchanged")
        h.tick(8, 31, day=TUESDAY)                       # Tuesday's own date: the plan refuses it as sent until midnight
        self.assertEqual(h.state.get("eq_decision")["audit"], "ok")
        self.assertEqual(h.alpaca.sent("/v2/stocks/bars")[-1]["end"], "2026-10-13T12:15:03Z")
        self.assertEqual([i.status for i in h.intents(instance=inst.id, kind="buy")], ["planned"])

    # -------------------------------------------------------------------------------- the limits from IEX's quote
    #: When the tests' IEX quotes and trades were made: in Monday's session, before the first send.
    QUOTED = at(MONDAY, 9, 30, 45)

    def quote(self, h, symbol="SPY", *, bid, ask, t=None, trade=None, trade_t=None):
        row = {"latestQuote": {"bp": bid, "ap": ask, "bs": 1, "as": 1, "t": iso(self.QUOTED if t is None else t)}}
        if trade is not None:
            row["latestTrade"] = {"p": trade, "s": 5, "t": iso(self.QUOTED if trade_t is None else trade_t)}
        h.alpaca.rows[symbol] = row

    def entry(self, h):
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        return it

    def test_an_entry_buys_at_iexs_ask_and_its_collar(self):
        h = self.harness()
        self.entry(h)
        self.quote(h, bid=600.00, ask=600.04)
        h.tick(9, 31)
        [sent] = h.venue.sent
        self.assertEqual((sent["side"], D(sent["limit_price"])), ("buy", L.limit_for("buy", D("600.04"), 10)))
        self.assertEqual(h.alpaca.sent("/v2/stocks/snapshots")[0]["feed"], "iex")

    def test_a_zero_or_one_sided_quote_never_becomes_a_buy_limit(self):
        for n, (bid, ask) in enumerate(((600.00, 0), (0, 600.04), (0, 0), (600.05, 600.04), (None, 600.04),
                                        (600.00, -1))):
            with self.subTest(bid=bid, ask=ask):
                h = self.harness(case=f"case{n}")
                it = self.entry(h)
                self.quote(h, bid=bid, ask=ask)
                h.tick(9, 31)
                h.tick(9, 32)
                self.assertEqual(h.venue.sent, [])
                self.assertEqual(h.get_intent(it.iid).why, "no usable quote for SPY this minute")

    def test_a_quote_from_before_the_open_is_refused(self):
        h = self.harness()
        it = self.entry(h)
        self.quote(h, bid=600.00, ask=600.04, t=at(MONDAY, 9, 29, 0))
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [])
        self.assertEqual(h.get_intent(it.iid).why, "no usable quote for SPY this minute")

    def test_a_zero_bid_never_becomes_a_sale_limit(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        self.quote(h, bid=0, ask=600.04, trade=601.0, trade_t=at(FRIDAY, 15, 59, 0))       # Friday's trade: stale
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [])
        self.assertEqual(h.get_intent(it.iid).why, "no usable bid for SPY this minute")
        self.quote(h, bid=0, ask=600.04, trade=600.5)                            # this session's trade: priced on it
        h.tick(9, 32)
        [sent] = h.venue.sent
        self.assertEqual((sent["side"], D(sent["limit_price"])), ("sell", L.limit_for("sell", D("600.5"), 10)))

    def test_a_zero_bid_never_reads_as_a_quote_through_a_working_sale(self):
        """At the widest collar a working order is re-priced only when the quote moved through its limit; IEX's 0 for
        a side with no order is no quote, never one far through the limit (the sale stays working)."""
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.venue.fill = "none"
        self.quote(h, bid=600.00, ask=600.04)
        for mm in range(31, 39):
            h.tick(9, mm)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40, 50])
        self.assertEqual(orders[-1].status, "working")
        cancels = list(h.venue.cancels)                                          # the four re-prices' own
        self.quote(h, bid=0, ask=600.04)
        h.tick(9, 39)
        h.tick(9, 40)
        self.assertEqual(len(h.orders()), 5)
        self.assertEqual(h.orders()[-1].status, "working")
        self.assertEqual(h.venue.cancels, cancels, "nothing cancelled for a side IEX does not quote")


# ------------------------------------------------------------------------------------------------- the jobs' gateway
class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class Opener:
    """The gateway's /v1/alpaca market data on the Basic plan, through `urllib`'s opener interface."""

    def __init__(self, clock, bars):
        self.clock, self.bars, self.urls = clock, bars, []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        parts = urllib.parse.urlsplit(request.full_url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        plan = BasicPlan(self.clock, bar_rows={"raw": self.bars, "all": self.bars, "split": self.bars})
        status, body = plan.request("GET", "https://data.alpaca.markets" + parts.path.replace("/v1/alpaca", "", 1)
                                    + "?" + parts.query)
        raw = json.dumps(body).encode()
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, "refused", {}, io.BytesIO(raw))
        return _Response(raw)

    def ends(self):
        return [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)).get("end") for u in self.urls]


class TheJobsGateway(unittest.TestCase):
    def days(self, *days):
        return {s: [{"t": f"{d}T04:00:00Z", "o": 1.0, "h": 2.0, "l": 1.0, "c": 2.0, "v": 9} for d in days]
                for s in ("SPY", "QQQ", "IWM")}

    def test_direction_at_0100z_reads_the_days_closes(self):
        """`direction` asks for SIP closes to today's New York date: refused all day as sent, read through the window."""
        from league.ops import direction
        from league.ops.context import Context, Gateway

        clock = Clock(utc(2026, 10, 20, 1, 0))
        opener = Opener(clock, self.days("2026-10-16", "2026-10-19"))
        with tempfile.TemporaryDirectory() as tmp:
            gw = Gateway("https://gateway.test", lambda: "t" * 40, opener=opener, clock=clock)
            ctx = Context("direction", root=tmp, due_at=clock(), config={"gateway_url": "https://gateway.test"},
                          clock=clock, gateway=gw, settings_value={})
            receipt = direction.run(ctx)
            self.assertTrue(receipt.get("ok"), receipt)
            self.assertEqual(opener.ends(), ["2026-10-20T00:44:00Z"])
            doc = json.loads((Path(tmp) / direction.FILE).read_text())
            self.assertEqual(sorted(doc["closes"]["SPY"]), ["2026-10-16", "2026-10-19"], "Monday's close is kept")

    def test_a_past_read_and_a_non_sip_read_go_as_they_were(self):
        from league.ops.context import Gateway

        clock = Clock(utc(2026, 10, 20, 1, 0))
        opener = Opener(clock, self.days("2026-10-16"))
        gw = Gateway("https://gateway.test", lambda: "t" * 40, opener=opener, clock=clock)
        gw.get("/v1/alpaca/v2/stocks/bars", {"symbols": "SPY", "timeframe": "1Day", "start": "2026-10-01",
                                             "end": "2026-10-16", "feed": "sip"})
        gw.get("/v1/alpaca/v2/stocks/bars", {"symbols": "SPY", "timeframe": "1Day", "start": "2026-10-01",
                                             "end": "2026-10-20", "feed": "iex"})
        self.assertEqual(opener.ends(), ["2026-10-16", "2026-10-20"])

    def test_the_equity_stores_nightly_read_at_2230z(self):
        """`equity_data` (22:30Z) reads the universe through the session it calls closed: its date was refused as sent
        until 04:00Z; the minute check's 04:00-20:00 ET window ends in the future at 18:30 ET."""
        from league.ops import equity_data
        from league.ops.context import Gateway

        clock = Clock(utc(2026, 10, 19, 22, 30))
        opener = Opener(clock, self.days("2026-10-16", "2026-10-19"))
        gw = Gateway("https://gateway.test", lambda: "t" * 40, opener=opener, clock=clock)
        last = equity_data.last_closed(clock())
        self.assertEqual(last, dt.date(2026, 10, 19))
        rows = equity_data.fetch(gw, ["SPY"], "2026-10-01", last.isoformat(), adjustment="raw")
        self.assertEqual([r["t"][:10] for r in rows["SPY"]], ["2026-10-16", "2026-10-19"])
        equity_data.fetch(gw, ["SPY"], equity_data._utc(last, 4), equity_data._utc(last, 20), adjustment="raw",
                          timeframe="1Min")
        self.assertEqual(opener.ends(), ["2026-10-19T22:14:00Z", "2026-10-19T22:14:00Z"])


# ------------------------------------------------------------------------------------------------- the options path off
try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False

if HAVE_NUMPY:
    from league.tests.live_fakes import VERTICAL, family
    from league.tests.live_fakes import Market as LiveMarket
    from league.tests.test_live_step import LiveCase

    class OptionsOffMarket(LiveMarket):
        """The live fakes' market with its option reads refused as `PlanMarketData` refuses them with the feed off."""

        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self.option_reads = 0

        def chain(self, underlying, **kw):
            self.option_reads += 1
            raise VenueError(f"market data chain {underlying}: {P.OPTIONS_OFF}")

        def contracts(self, symbols, **kw):
            self.option_reads += 1
            raise VenueError(f"market data contracts: {P.OPTIONS_OFF}")
else:  # pragma: no cover
    LiveCase = unittest.TestCase


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TheOptionsPathOff(LiveCase):
    """With the option feed off no options position opens, of any kind, and nothing is said about it: the programs are
    never asked (no chain, no snapshot), the House's own routes find nothing to price, and no alert, refusal or owner
    notice is raised, minute after minute."""

    def setUp(self):
        super().setUp()
        self.market = OptionsOffMarket(self.clock)
        self.venue.market = self.paper.market = self.market
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": True, "house_test": True,
                                                                   "incubator": True}}))

    def test_a_probe_family_opens_nothing_and_the_minutes_stay_quiet(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        out = self.run_to(9, 45)
        self.assertEqual(out["state"], "session")
        options = lambda sent: [o for o in sent if o.get("legs") or o.get("order_class") == "mleg"  # noqa: E731
                                or occ_parts(str(o.get("symbol") or "")) is not None]
        self.assertEqual(options(self.venue.sent), [], "no real options order of any kind")
        self.assertEqual(options(self.paper.sent), [], "no practice options order either (the stock proof's share "
                                                       "round trip is the equity book's)")
        self.assertEqual(self.venue.sent, [], "nothing at all on the real account")
        self.assertEqual(live.book.positions, {})
        self.assertEqual(sum(len(a.positions) + len(a.orders) for a in live.shadow.accounts.values()), 0)
        self.assertEqual(self.alerts, [], "nothing is said")
        self.assertEqual(self.notices, [], "no owner notice")
        self.assertEqual(self.ledger.of("live.refusal"), [], "no program was asked, so none was refused")
        self.assertTrue(any(P.OPTIONS_OFF in e for e in out.get("data_errors") or []), out.get("data_errors"))
        self.assertGreater(self.market.option_reads, 0)
        self.assertIsNone(live.real_block(), "nothing else blocks real money: the options path is closed by its data")


if __name__ == "__main__":
    unittest.main()
