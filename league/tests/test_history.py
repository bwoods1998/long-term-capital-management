"""The deep-history store: resumable chunks, coverage accounting, unavailable versus unfetched."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import urllib.parse
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from league import history
from league.history import Chunk, HistoryStore, Ingestor, RateLimiter, chunk_ranges, publish_coverage
from league.ledger import Ledger
from league.tapes import TIMEFRAME_SECONDS, iso, parse_time

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc).timestamp()


def _days(start: str, end: str):
    day = date.fromisoformat(start)
    while day < date.fromisoformat(end):
        yield day
        day += timedelta(days=1)


class FakeAlpaca:
    """Answers the data endpoints the way Alpaca does: multi-symbol, paged, oldest first.

    `listed` is when each symbol begins trading; before it the venue has nothing. `fail_after`
    makes the transport fail from that call on (a killed network), `refuse` answers 422."""

    def __init__(self, listed=None, *, fail_after=None, page=10_000, quotes=True):
        self.listed = {k: parse_time(v) for k, v in (listed or {}).items()}
        self.fail_after, self.page, self.quotes = fail_after, page, quotes
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def _bars(self, symbol, timeframe, start, end, adjustment):
        step = TIMEFRAME_SECONDS[timeframe]
        crypto = "/" in symbol
        t = (int(start) // step) * step
        out = []
        while t <= end:
            moment = datetime.fromtimestamp(t, timezone.utc)
            weekday = moment.weekday() < 5
            if timeframe == "1Day":
                keep = crypto or weekday
                stamp = t if crypto else t + 4 * 3600  # an equity's daily bar opens at NY midnight
            else:
                keep = crypto or (weekday and 14 <= moment.hour < 21)
                stamp = t
            if keep and start <= stamp <= end and stamp >= self.listed.get(symbol, 0):
                price = 100.0 + (stamp % 86400) / 86400.0
                factor = 0.9 if adjustment == "all" else 1.0
                out.append({"t": iso(stamp), "o": price * factor, "h": price * factor + 1, "l": price * factor - 1,
                            "c": price * factor + 0.5, "v": 1000, "n": 10, "vw": price * factor})
            t += step
        return out

    def request(self, method, url, headers=None, body=None, what="venue"):
        with self._lock:
            self.calls.append(url)
            count = len(self.calls)
        if self.fail_after is not None and count > self.fail_after:
            raise ConnectionError("the network went away")
        parsed = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if parsed.path.endswith("/calendar"):
            out = []
            for day in _days(q["start"], str(date.fromisoformat(q["end"]) + timedelta(days=1))):
                if day.weekday() < 5:
                    out.append({"date": str(day), "open": "09:30", "close": "16:00"})
            return 200, out
        symbols = q["symbols"].split(",")
        if any(s.startswith("BAD") for s in symbols):
            return 422, {"message": "invalid symbol"}
        start, end = parse_time(q["start"]), parse_time(q["end"])
        if parsed.path.endswith("/quotes"):
            symbol = symbols[0]
            if not self.quotes or end < self.listed.get(symbol, 0):
                return 200, {"quotes": {}, "next_page_token": None}
            return 200, {"quotes": {symbol: [{"t": datetime.fromtimestamp(end - 0.25, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z",
                                              "bp": 100.0, "bs": 3, "ap": 100.02, "as": 4, "bx": "P", "ax": "Q", "c": ["R"]}]},
                         "next_page_token": None}
        if parsed.path.endswith("/trades"):
            symbol = symbols[0]
            return 200, {"trades": {symbol: [{"t": iso(start + 1), "p": 100.01, "s": 5, "x": "V", "i": 1, "c": ["@"]}]},
                         "next_page_token": None}
        rows = [(s, bar) for s in symbols for bar in self._bars(s, q["timeframe"], start, end, q.get("adjustment", "raw"))]
        offset = int(q.get("page_token") or 0)
        limit = min(int(q.get("limit") or 10_000), self.page)
        page = rows[offset:offset + limit]
        grouped: dict = {}
        for s, bar in page:
            grouped.setdefault(s, []).append(bar)
        more = offset + limit < len(rows)
        return 200, {"bars": grouped, "next_page_token": str(offset + limit) if more else None}


def _ingestor(store, client, **kw):
    return Ingestor(store, client, feed="sip", rate_per_minute=1_000_000, workers=kw.pop("workers", 2), clock=lambda: NOW,
                    sleep=lambda s: None, **kw)


class ChunkGridTest(unittest.TestCase):
    def test_years_for_daily_and_months_otherwise(self):
        self.assertEqual(chunk_ranges("1Day", date(2016, 3, 1), date(2018, 1, 5)),
                         [(date(2016, 3, 1), date(2017, 1, 1)), (date(2017, 1, 1), date(2018, 1, 1)), (date(2018, 1, 1), date(2018, 1, 5))])
        months = chunk_ranges("1Hour", date(2024, 11, 15), date(2025, 2, 1))
        self.assertEqual(months, [(date(2024, 11, 15), date(2024, 12, 1)), (date(2024, 12, 1), date(2025, 1, 1)), (date(2025, 1, 1), date(2025, 2, 1))])

    def test_plan_is_daily_first_newest_first_and_dual_adjusted_only_for_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            plan = _ingestor(store, FakeAlpaca()).plan(["SPY", "BTC/USD"], ["5Min", "1Day"], "2024-01-01", "2026-01-01")
            self.assertEqual(plan[0].timeframe, "1Day")
            self.assertEqual(plan[0].start, date(2025, 1, 1))  # newest first
            daily = {(c.symbols, c.adjustment) for c in plan if c.timeframe == "1Day"}
            self.assertEqual(daily, {(("SPY",), "raw"), (("SPY",), "all"), (("BTC/USD",), "raw")})
            self.assertEqual({c.adjustment for c in plan if c.timeframe == "5Min"}, {"raw"})
            self.assertEqual({c.feed for c in plan if "BTC/USD" in c.symbols}, {"us"})


class ResumeTest(unittest.TestCase):
    def test_an_interrupted_run_resumes_where_it_stopped_and_matches_a_clean_run(self):
        symbols, frames = ["SPY", "QQQ", "BTC/USD"], ["1Day", "1Hour"]
        with tempfile.TemporaryDirectory() as clean_dir, tempfile.TemporaryDirectory() as broken_dir:
            clean = HistoryStore.at_root(clean_dir)
            ing = _ingestor(clean, FakeAlpaca())
            plan = ing.plan(symbols, frames, "2025-01-01", "2025-07-01")
            ing.run(plan)
            total_calls = len(ing.client.calls)

            broken = HistoryStore.at_root(broken_dir)
            dying = FakeAlpaca(fail_after=9)
            first = _ingestor(broken, dying, retries=0, workers=1)
            first.run(first.plan(symbols, frames, "2025-01-01", "2025-07-01"))
            states = {r["state"] for r in broken.chunk_rows()}
            self.assertIn("failed", states)
            self.assertIn("done", states)
            done_before = {(r["symbol"], r["timeframe"], r["adjustment"], r["start"]) for r in broken.chunk_rows() if r["state"] == "done"}

            healthy = FakeAlpaca()
            second = _ingestor(broken, healthy)
            second.run(second.plan(symbols, frames, "2025-01-01", "2025-07-01"))
            # Nothing done before was fetched again; everything else was.
            refetched = set()
            for url in healthy.calls:
                q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}
                for s in q["symbols"].split(","):
                    refetched.add((s, q["timeframe"], q.get("adjustment", "raw"), q["start"][:10]))
            self.assertFalse(done_before & refetched, "a completed chunk was fetched again")
            self.assertLess(len(healthy.calls), total_calls)
            self.assertEqual({r["state"] for r in broken.chunk_rows()}, {"done"})
            for symbol in symbols:
                for frame in frames:
                    adj = "raw"
                    feed = "us" if "/" in symbol else "sip"
                    a = clean.bars(symbol, frame, 0, NOW, feed=feed, adjustment=adj)
                    b = broken.bars(symbol, frame, 0, NOW, feed=feed, adjustment=adj)
                    self.assertEqual(a, b)
                    self.assertTrue(a)

    def test_a_stop_signal_ends_the_run_between_chunks_and_nothing_is_half_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            stop = threading.Event()
            client = FakeAlpaca()
            ing = _ingestor(store, client, workers=1)
            original = ing.fetch_bars

            def once(chunk, symbols, run=None):
                out = original(chunk, symbols, run)
                stop.set()
                return out

            ing.fetch_bars = once
            plan = ing.plan(["SPY"], ["1Hour"], "2025-01-01", "2025-06-01")
            ing.run(plan, stop=stop)
            rows = store.chunk_rows()
            self.assertEqual(len(rows), 1)  # one chunk committed, the rest untouched
            self.assertEqual(sum(1 for c in plan if ing.pending(c)), len(plan) - 1)

    def test_paging_is_followed_to_the_end_inside_one_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca(page=50)
            ing = _ingestor(store, client)
            ing.run(ing.plan(["SPY", "QQQ"], ["1Hour"], "2025-03-01", "2025-04-01"))
            self.assertGreater(len(client.calls), 2)
            rows = store.bars("QQQ", "1Hour", 0, NOW, feed="sip", adjustment="raw")
            self.assertEqual(len(rows), 21 * 7)  # 21 weekdays in March 2025, seven fake hours each
            self.assertEqual(sum(r["calls"] for r in store.chunk_rows()), len(client.calls))


class CoverageTest(unittest.TestCase):
    def test_unavailable_partial_unfetched_and_failed_are_told_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca(listed={"HOOD": "2021-07-29T04:00:00Z"})
            ing = _ingestor(store, client)
            ing.run(ing.plan(["HOOD", "SPY", "BTC/USD"], ["1Day"], "2020-01-01", "2022-01-01"))
            # Before the listing: the venue answered with nothing -- unavailable, not missing.
            before = store.coverage("HOOD", "1Day", "2020-01-01", "2021-01-01", feed="sip")
            self.assertEqual(before["status"], "unavailable")
            self.assertEqual(before["unavailable"], [["2020-01-01", "2021-01-01"]])
            listed = store.coverage("HOOD", "1Day", "2021-01-01", "2022-01-01", feed="sip")
            self.assertEqual(listed["status"], "covered")
            both = store.coverage("HOOD", "1Day", "2020-06-01", "2021-12-31", feed="sip")
            self.assertEqual(both["status"], "partial")
            self.assertEqual(both["available_from"], "2021-07-29T04:00:00Z")
            # Never asked for: a gap in the store.
            gap = store.coverage("SPY", "1Day", "2018-01-01", "2019-01-01", feed="sip")
            self.assertEqual(gap["status"], "unfetched")
            self.assertEqual(gap["rows"], 0)
            self.assertEqual(store.coverage("SPY", "1Hour", "2021-01-01", "2021-02-01", feed="sip")["status"], "unfetched")
            # The other adjustment is its own series.
            self.assertEqual(store.coverage("SPY", "1Day", "2021-01-01", "2022-01-01", feed="sip", adjustment="all")["status"], "covered")
            # A refusal is a failure, recorded, retried, and read as unfetched.
            bad = _ingestor(store, FakeAlpaca(), retries=0)
            bad.run(bad.plan(["BADX"], ["1Day"], "2021-01-01", "2022-01-01"))
            failed = store.coverage("BADX", "1Day", "2021-01-01", "2022-01-01", feed="sip")
            self.assertEqual(failed["status"], "unfetched")
            self.assertEqual(failed["failed"], [["2021-01-01", "2022-01-01"]])
            self.assertIn("422", [r for r in store.chunk_rows() if r["symbol"] == "BADX"][0]["error"])

    def test_a_failure_never_overwrites_a_completed_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            chunk = Chunk("bars", ("SPY",), "1Day", "sip", "raw", date(2020, 1, 1), date(2021, 1, 1))
            store.commit_chunk(chunk, "SPY", state="done", rows=[(1577941200, 1, 1, 1, 1, 1, 1, 1)], params={})
            store.commit_chunk(chunk, "SPY", state="failed", error="HTTP 503", params={})
            self.assertEqual(store.chunk_state("bars", "SPY", "1Day", "sip", "raw", date(2020, 1, 1), date(2021, 1, 1)), "done")

    def test_intraday_months_before_the_first_daily_bar_are_inferred_unavailable_without_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca(listed={"HOOD": "2021-07-29T04:00:00Z"})
            ing = _ingestor(store, client, workers=1)
            ing.run(ing.plan(["HOOD"], ["1Day"], "2021-01-01", "2022-01-01"))
            calls = len(client.calls)
            ing.run(ing.plan(["HOOD"], ["1Hour"], "2021-01-01", "2021-09-01"))
            # July (the listing month) and August only, raw and adjusted.
            self.assertEqual(len(client.calls) - calls, 4)
            inferred = [r for r in store.chunk_rows() if r["timeframe"] == "1Hour" and r["state"] == "empty"]
            self.assertEqual(len(inferred), 12)
            self.assertIn("inferred", json.loads(inferred[0]["params"]))

    def test_a_range_reaching_the_present_stays_open_and_is_fetched_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca()
            ing = _ingestor(store, client)
            plan = ing.plan(["SPY"], ["1Day"], "2026-01-01")
            ing.run(plan)
            self.assertEqual({r["state"] for r in store.chunk_rows()}, {"open"})
            self.assertEqual(store.coverage("SPY", "1Day", "2026-06-01", "2026-09-20", feed="sip")["status"], "covered")
            self.assertTrue(all(ing.pending(c) for c in plan))

    def test_provenance_is_recorded_per_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp, clock=lambda: NOW)
            ing = _ingestor(store, FakeAlpaca())
            ing.run(ing.plan(["SPY"], ["1Day"], "2024-01-01", "2025-01-01"))
            row = [r for r in store.chunk_rows() if r["adjustment"] == "all"][0]
            self.assertEqual((row["source"], row["feed"], row["state"]), ("alpaca", "sip", "done"))
            params = json.loads(row["params"])
            self.assertEqual((params["adjustment"], params["feed"], params["timeframe"]), ("all", "sip", "1Day"))
            self.assertEqual(row["fetched_at"], NOW)
            raw = store.bars("SPY", "1Day", 0, NOW, feed="sip", adjustment="raw")[0]
            adj = store.bars("SPY", "1Day", 0, NOW, feed="sip", adjustment="all")[0]
            self.assertAlmostEqual(adj["c"] / raw["c"], 0.9 * (raw["c"] - 0.5) / raw["c"] + 0.5 / raw["c"], places=6)

    def test_the_house_records_each_finished_run_once_as_data_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                code = history.main(["ingest", "--root", tmp, "--symbols", "SPY,BTC/USD", "--timeframes", "1Day",
                                     "--since", "2024-01-01", "--until", "2025-01-01", "--feed", "sip", "--rate", "100000"],
                                    client=FakeAlpaca())
            self.assertEqual(code, 0)
            ledger = Ledger(Path(tmp) / "ledger.sqlite")
            self.assertEqual(publish_coverage(ledger, tmp), 1)
            self.assertEqual(publish_coverage(ledger, tmp), 0)  # idempotent
            row = ledger.last("data.coverage")
            self.assertFalse(row.public)
            payload = row.payload
            self.assertEqual((payload["source"], payload["status"]), ("alpaca", "finished"))
            self.assertEqual(payload["chunks"]["done"], 3)  # SPY raw, SPY all, BTC raw
            self.assertTrue(any("survivorship" in text for text in payload["limitations"]))
            series = {(s["symbol"], s["adjustment"]): s for s in payload["series"]}
            self.assertEqual(series[("BTC/USD", "raw")]["feed"], "us")
            with redirect_stdout(io.StringIO()) as text:
                history.main(["coverage", "--root", tmp])
            self.assertIn("SPY", text.getvalue())
            ledger.close()

    def test_a_killed_run_is_recorded_as_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            store._db.execute("INSERT INTO runs (run, pid, started_at, status, args) VALUES ('old', 999999999, 1, 'running', '{}')")
            ledger = Ledger(Path(tmp) / "ledger.sqlite")
            publish_coverage(ledger, tmp)
            self.assertEqual(ledger.last("data.coverage").payload["status"], "interrupted")
            store.begin_run({})
            self.assertEqual([r["status"] for r in store.runs() if r["run"] == "old"], ["interrupted"])
            ledger.close()


class QuoteTest(unittest.TestCase):
    def test_probes_store_the_prevailing_quote_at_each_session_close_plus_latency(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca()
            ing = _ingestor(store, client, workers=1)
            plan = ing.probe_plan(["SPY"], "2025-03-03", "2025-03-05", grid="1Hour")
            ing.run(plan)
            rows = store.probes("SPY", 0, NOW, feed="sip")
            # 09:30-16:00 New York in March 2025 before DST: 14:30-21:00 UTC; hourly bars close on the
            # hour, so the probes are 15:00..21:00, seven a day.
            self.assertEqual(len(rows), 14)
            first = rows[0]
            self.assertEqual(iso(first["t"]), "2025-03-03T15:00:00Z")
            self.assertEqual(iso(rows[6]["t"]), "2025-03-03T21:00:00Z")
            self.assertAlmostEqual(first["at"], first["t"] + history.PROBE_LATENCY_SECONDS)
            self.assertEqual(first["quote_ns"] % 1000, 123)  # nanoseconds survive
            self.assertLess(first["quote_ns"] / 1e9, first["at"])
            self.assertEqual((first["bp"], first["ap"]), (100.0, 100.02))
            asked = [u for u in client.calls if "/quotes" in u]
            self.assertTrue(all("sort=desc" in u and "limit=1" in u for u in asked))
            cover = store.coverage("SPY", "1Hour", "2025-03-03", "2025-03-05", feed="sip", kind="probes")
            self.assertEqual(cover["status"], "covered")

    def test_a_probe_with_no_quote_in_the_lookback_is_unavailable_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            ing = _ingestor(store, FakeAlpaca(quotes=False))
            ing.run(ing.probe_plan(["SPY"], "2025-03-03", "2025-03-04", grid="1Hour"))
            rows = store.probes("SPY", 0, NOW, feed="sip")
            self.assertTrue(rows)
            self.assertTrue(all(r["quote_ns"] is None and r["bp"] is None for r in rows))
            self.assertEqual(store.coverage("SPY", "1Hour", "2025-03-03", "2025-03-04", feed="sip", kind="probes")["status"], "unavailable")

    def test_a_weekend_has_no_equity_probes_and_trades_are_windowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca()
            ing = _ingestor(store, client, workers=1)
            ing.run(ing.probe_plan(["SPY"], "2025-03-08", "2025-03-10", grid="1Hour"))
            self.assertFalse([u for u in client.calls if "/quotes" in u])
            ing.run(ing.trade_plan(["SPY", "BTC/USD"], "2025-03-10", "2025-03-11"))
            self.assertEqual(len([u for u in client.calls if "/trades" in u]), 7)


class RateTest(unittest.TestCase):
    def test_the_bucket_holds_the_rate(self):
        clock = [0.0]
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds

        limiter = RateLimiter(1500, clock=lambda: clock[0], sleep=sleep)
        for _ in range(250):
            limiter.acquire()
        # 1,500 a minute is 25 a second: 250 calls take about nine seconds after the first burst.
        self.assertGreaterEqual(clock[0], 8.9)
        self.assertLessEqual(clock[0], 10.1)
        limiter.back_off(30)
        before = clock[0]
        limiter.acquire()
        self.assertGreaterEqual(clock[0] - before, 29.9)


class UniverseTest(unittest.TestCase):
    def test_core_starts_with_the_liquid_tier_and_all_adds_every_niche_symbol(self):
        core, every = history.universe("core"), history.universe("all")
        self.assertEqual(core[:5], list(history.TIER_ONE))
        self.assertIn("XLK", core)
        self.assertIn("NVDA", core)
        self.assertIn("SOFI", every)
        self.assertIn("DOGE/USD", every)
        self.assertLessEqual(set(core), set(every) | {"SOL/USD"})






from league.tests.test_house import HouseCase  # noqa: E402


class HouseHookTest(HouseCase):
    def test_the_tick_records_a_finished_ingestion_once_and_the_switch_turns_it_off(self):
        root = self.house.root
        with redirect_stdout(io.StringIO()):
            history.main(["ingest", "--root", str(root), "--symbols", "SPY", "--timeframes", "1Day", "--since", "2024-01-01",
                          "--until", "2025-01-01", "--feed", "sip", "--rate", "100000"], client=FakeAlpaca())
        self.house.settings.history_coverage = False
        self.house.tick()
        self.assertEqual(self.house.ledger.count(kinds="data.coverage"), 0)
        self.house.settings.history_coverage = True
        self.house.tick()
        self.assertEqual(self.house.ledger.count(kinds="data.coverage"), 1)
        self.clock.advance(600)
        self.house.tick()
        self.assertEqual(self.house.ledger.count(kinds="data.coverage"), 1)  # once per run


if __name__ == "__main__":
    unittest.main()


class RefreshAdjustedTest(unittest.TestCase):
    def test_refresh_refetches_only_the_adjusted_chunks_fetched_before_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp, clock=lambda: NOW - 10)
            ing = _ingestor(store, FakeAlpaca())
            plan = ing.plan(["SPY"], ["1Day"], "2023-01-01", "2025-01-01")
            ing.run(plan)
            client = FakeAlpaca()
            again = Ingestor(store, client, feed="sip", rate_per_minute=1_000_000, clock=lambda: NOW, sleep=lambda s: None,
                             refresh_adjusted_before=NOW + 1)
            again.run(again.plan(["SPY"], ["1Day"], "2023-01-01", "2025-01-01"))
            self.assertEqual(len(client.calls), 2)
            self.assertTrue(all("adjustment=all" in url for url in client.calls))


class CallBudgetTest(unittest.TestCase):
    def test_a_call_budget_stops_scheduling_and_the_run_resumes_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca()
            ing = _ingestor(store, client, workers=1)
            plan = ing.plan(["SPY"], ["1Hour"], "2025-01-01", "2026-01-01")
            ing.run(plan, max_calls=5)
            self.assertEqual(len(client.calls), 5)
            self.assertEqual(sum(1 for c in plan if ing.pending(c)), len(plan) - 5)
            rest = _ingestor(store, FakeAlpaca(), workers=1)
            rest.run(plan)
            self.assertEqual(sum(1 for c in plan if rest.pending(c)), 0)


class ProbeBudgetTest(unittest.TestCase):
    def test_a_budget_spent_inside_a_probe_day_leaves_that_day_unfetched_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HistoryStore.at_root(tmp)
            client = FakeAlpaca()
            ing = _ingestor(store, client, workers=3)
            plan = ing.probe_plan(["SPY", "QQQ"], "2025-03-03", "2025-03-06", grid="1Hour")
            ing.run(plan, max_calls=8)
            self.assertLessEqual(len(client.calls), 8)
            self.assertNotIn("failed", {r["state"] for r in store.chunk_rows()})
            self.assertTrue(any(ing.pending(c) for c in plan))
