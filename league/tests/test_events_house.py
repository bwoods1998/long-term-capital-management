"""The event lane on the House (release R1, WP1; league/events/house.py): the publisher hook and the tick, the one
bounded task a turn, decisions first and at their times, verdicts asked before the decisions that read them (with the
decision's own code), the resumable record pass, the nightly jobs, the backfill, paid work held by PAUSE and the
day's line, warnings that never become an error, and `house.feeds` left None. Synthetic data only."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.events import calendar as C
from league.events import house as H
from league.events import programs as P
from league.events import run as R
from league.events import score as SC
from league.events import store as S
from league.tests.test_events_run import weekdays
from ltcm.tests.fakes import Clock

UTC = dt.timezone.utc
NY = C.NY
TICKERS = {"0": {"cik_str": 1, "ticker": "AAA", "title": "Alpha Inc."},
           "1": {"cik_str": 2, "ticker": "BBB", "title": "Beta Inc."},
           "2": {"cik_str": 3, "ticker": "CCC", "title": "Gamma Inc."}}


def et(day: str, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(h, m), tzinfo=NY).astimezone(UTC)


class Mono:
    """The lane's monotonic clock: tests move it, and the lane's throttle 'sleeps' by moving it."""

    def __init__(self):
        self.t = 10_000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


class FakeGateway:
    """Alpaca data (calendar, assets, 1Day and 1Min bars, news, the account) and Claude through the gateway."""

    def __init__(self, scores=None, *, cost="0.002"):
        self.scores = scores or {"AAA": 3, "BBB": 1, "CCC": 2}
        self.cost = cost
        self.claude_calls = []
        self.gets = []
        self.last_headers = {}
        self.news = []
        self.fail = None
        self.claude_status = 200

    def get_json(self, path, params=None):
        self.gets.append(path)
        if self.fail:
            raise self.fail
        if path.endswith("/v2/calendar"):
            s, e = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
            return [{"date": d.isoformat(), "open": "09:30", "close": "16:00"} for d in weekdays(s, e)]
        if path.endswith("/v2/assets"):
            return [{"symbol": sym, "status": "active", "tradable": True, "class": "us_equity", "exchange": "NASDAQ",
                     "name": "x", "easy_to_borrow": True} for sym in ("AAA", "BBB", "CCC")]
        if path.endswith("/v2/stocks/bars"):
            end = S.parse_iso(params["end"])
            start = dt.date.fromisoformat(params["start"][:10])
            if params.get("timeframe") == "1Min":
                return {"bars": {params["symbols"]: [{"t": S.iso(end - dt.timedelta(minutes=1)), "o": 20, "h": 21, "l": 20,
                                                      "c": 21.0, "v": 100}]}, "next_page_token": None}
            return {"bars": {sym: [{"t": f"{d}T04:00:00Z", "o": 20, "h": 20, "l": 20, "c": 20, "v": 1_000_000}
                                   for d in weekdays(start, (end - dt.timedelta(minutes=1)).date())]
                             for sym in params["symbols"].split(",")}, "next_page_token": None}
        if path.endswith("/v1beta1/news"):
            lo, hi = S.parse_iso(params["start"]), S.parse_iso(params["end"])
            rows = [a for a in self.news if lo <= S.parse_iso(a["created_at"]) < hi]
            return {"news": rows, "next_page_token": None}
        if path.endswith("/v2/account"):
            return {"equity": "2000.00"}
        if path.endswith("/trades"):                                      # a closing print on the listing exchange
            close = S.parse_iso(params["start"]) + dt.timedelta(seconds=5)
            return {"trades": [{"t": S.iso(close), "x": "Q", "c": ["@", "6"], "p": 20.0, "s": 100}],
                    "next_page_token": None}
        raise AssertionError(path)

    def post_json(self, path, body, headers=None):
        if self.fail:
            raise OSError("down")
        self.claude_calls.append(body)
        if self.claude_status != 200:
            return self.claude_status, {"error": "refused"}
        text = body["messages"][0]["content"]
        ticker = next((k for k in self.scores if f"ticker {k}" in text or text.startswith(f"Stock: {k}.")), None)
        self.last_headers = {"x-ltcm-cost-usd": self.cost}
        return 200, {"content": [{"type": "text", "text": json.dumps({"score": self.scores.get(ticker, 0),
                                                                       "guidance": "raised", "reasons": []})}],
                     "stop_reason": "end_turn"}


class FakeSEC:
    """www.sec.gov: the tickers file, the company feed (operating test), the current feeds, index pages, documents and
    a daily index. `slow` moves the lane's monotonic clock on each filing fetch (index page or document)."""

    def __init__(self, mono=None):
        self.filings = {}      # accession -> {form, cik, company, accepted (ET wall), items}
        self.current = {"8-K": [], "4": []}
        self.daily = {}        # YYYYMMDD -> [accession]
        self.calls = []
        self.mono = mono
        self.slow = 0.0
        self.fail = None

    def add(self, acc, cik, accepted_et, *, form="8-K", items=("2.02",), company="Co", current=True):
        self.filings[acc] = {"form": form, "cik": cik, "company": company, "accepted": accepted_et, "items": list(items)}
        if current:
            self.current[form].insert(0, acc)

    def __call__(self, url):
        self.calls.append(url)
        if self.fail:
            raise self.fail
        if url.endswith("company_tickers.json"):
            return json.dumps(TICKERS).encode()
        if "action=getcompany" in url:
            return (b"<feed><company-info><assigned-sic>3571</assigned-sic></company-info><entry><filing-type>10-Q"
                    b"</filing-type><filing-date>2026-08-01</filing-date></entry></feed>")
        if "action=getcurrent" in url:
            form = "8-K" if "type=8-K" in url else "4"
            if "start=0&" not in url:
                return b"<feed></feed>"
            return self._atom(form).encode()
        if "/daily-index/" in url:
            key = url.rsplit("form.", 1)[1].split(".")[0]
            if key not in self.daily:
                from league.events.gw import GatewayError
                raise GatewayError(404, "SEC")
            lines = []
            for acc in self.daily[key]:
                f = self.filings[acc]
                lines.append(f"{f['form']:<12}{f['company']:<40}{int(f['cik']):<12}{key}    edgar/data/{int(f['cik'])}/"
                             f"{acc}.txt")
            return ("\n".join(lines) + "\n").encode()
        if url.endswith("-index.htm"):
            self._tick()
            acc = url.rsplit("/", 1)[1].replace("-index.htm", "")
            f = self.filings[acc]
            items = "".join(f"Item {i}: x " for i in f["items"])
            return (f'<div class="infoHead">Accepted</div><div class="info">{f["accepted"]}</div>'
                    f'<div class="infoHead">Items</div><div class="info">{items}</div>'
                    f'<table><tr><td>1</td><td>press release</td><td><a href="/Archives/x/{acc}/ex99.htm">ex99.htm</a></td>'
                    f'<td>EX-99.1</td><td>100</td></tr></table>').encode()
        if url.endswith("ex99.htm"):
            self._tick()
            return ("<html><body>" + "Quarterly results were strong and guidance was raised. " * 10 + "</body></html>").encode()
        raise AssertionError(url)

    def _tick(self):
        if self.mono is not None and self.slow:
            self.mono.advance(self.slow)

    def _atom(self, form):
        out = ["<feed>"]
        for acc in self.current[form]:
            f = self.filings[acc]
            wall = dt.datetime.strptime(f["accepted"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY)
            items = " ".join(f"Item {i}: x" for i in f["items"])
            out.append(f'<entry><title>{form} - {f["company"]} ({f["cik"]}) (Filer)</title>'
                       f'<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/'
                       f'{int(f["cik"])}/{acc.replace("-", "")}/{acc}-index.htm"/>'
                       f'<summary type="html">Filed: x AccNo: {acc} Size: 1 KB {items}</summary>'
                       f'<updated>{wall.isoformat()}</updated></entry>')
        out.append("</feed>")
        return "".join(out)


class FakeHouse:
    """What the lane reads of the House: its clock, its alerts, PAUSE, its closing flag and its background lane (run
    at once here)."""

    def __init__(self, clock):
        self.clock = clock
        self.alerts = []
        self.pause = None
        self._closing = threading.Event()
        self.background = []
        self.publisher = None
        self.feeds = None

    def alert(self, level, text, **payload):
        self.alerts.append((level, text))

    def paused(self):
        return self.pause

    def _background(self, key, work, *args):
        self.background.append(key)
        work(*args)
        return True

    def levels(self):
        return [level for level, _ in self.alerts]


class LaneCase(unittest.TestCase):
    """A lane on a temporary store with the calendar, a ticker snapshot taken before Tuesday Oct 20's 07:30 ET, and
    PREREG-EVL-1's real registration time (Mon Oct 19, 01:08:38Z)."""

    start = "2026-10-20T11:00:00Z"   # Tue Oct 20, 07:00 ET

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state" / "events"
        self.clock = Clock(self.start)
        self.mono = Mono()
        self.house = FakeHouse(self.clock)
        self.gw = FakeGateway()
        self.sec = FakeSEC(self.mono)
        with S.Store(self.root) as st:
            C.refresh(st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
            st.set_meta("evl:lane:sessions_at", self.start)
            st.set_meta("tickers@2026-10-19T11:00:05Z", st.put_document(json.dumps(TICKERS).encode(), "company_tickers"))
            st.set_meta("tickers@2026-10-20T11:00:05Z", st.put_document(json.dumps(TICKERS).encode(), "company_tickers"))
            for kind, wall in (("open", "09:15"), ("close", "15:47")):   # Monday's decisions: the desktop made them
                rid = st.start_receipt(f"decide-{kind}:2026-10-19", now=et("2026-10-19", wall))
                st.finish_receipt(rid, "ok", {}, now=et("2026-10-19", wall))
            st.set_meta("evl:backfill:2026-10-15", "done")
            st.set_meta("evl:backfill:2026-10-16", "done")
        self.gw.gets.clear()
        self.lane = self.new_lane()

    def new_lane(self, redecide=False, **settings):
        lane = H.EventLane(self.house, self.root, gateway=self.gw, sec=self.sec, settings=settings, monotonic=self.mono,
                           sleep=self.mono.advance)
        if not redecide:   # the hourly re-decision is its own test's
            lane._redecide_next = dt.datetime(2100, 1, 1, tzinfo=UTC)
        return lane

    def at(self, when):
        self.clock.set(when)

    def store(self):
        return S.Store(self.root)

    def turn(self):
        self.lane.run()
        return dict(self.lane.health()["last"] or {})

    def receipts(self, job):
        with self.store() as st:
            return [dict(r) for r in st.db.execute("SELECT * FROM receipts WHERE job=? ORDER BY id", (job,))]

    def fetched_8k(self, acc, cik, accepted_et, items=("2.02",)):
        """A filing the live pass has stored and fetched (as the desktop's store holds them)."""
        from league.events import edgar as E

        self.sec.add(acc, cik, accepted_et, items=items, current=False)
        entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": list(items), "accepted_at": None,
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
        with self.store() as st:
            self.assertEqual(E.record_filing(st, self.sec, entry, source="current", now=self.clock_dt()), "fetched")

    def clock_dt(self):
        return dt.datetime.fromtimestamp(self.clock(), UTC)

    def mark_recorded(self, when=None):
        """A record receipt, so the record pass is not due for two minutes."""
        with self.store() as st:
            rid = st.start_receipt("record", now=when or self.clock_dt())
            st.finish_receipt(rid, "ok", {}, now=when or self.clock_dt())


class TheHook(unittest.TestCase):
    def test_the_lane_waits_for_its_store_and_never_makes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            house = FakeHouse(Clock("2026-10-20T13:00:00Z"))
            lane = H.EventLane(house, Path(tmp) / "events", gateway=FakeGateway(), sec=FakeSEC())
            self.assertFalse(lane.due())
            self.assertFalse(lane.due())
            lane.run()
            self.assertFalse((Path(tmp) / "events").exists())
            self.assertEqual([lvl for lvl, _ in house.alerts], ["info"])   # said once
            self.assertIn("waits for its store", house.alerts[0][1])
            self.assertFalse(lane.shipped())
            S.Store(Path(tmp) / "events").close()      # the migration made it
            house.clock.advance(61)
            self.assertTrue(lane.due())

    def test_a_stop_file_idles_the_lane_without_a_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            house = FakeHouse(Clock("2026-10-20T13:00:00Z"))
            root = Path(tmp) / "events"
            S.Store(root).close()
            (root / H.STOP_FILE).write_text("operator\n")
            lane = H.EventLane(house, root, gateway=FakeGateway(), sec=FakeSEC())
            self.assertFalse(lane.due())
            lane.run()
            self.assertTrue(lane.health()["stopped"])
            self.assertEqual([lvl for lvl, _ in house.alerts], ["info"])
            self.assertIn("stopped by", house.alerts[0][1])
            (root / H.STOP_FILE).unlink()
            house.clock.advance(61)
            self.assertTrue(lane.due())

    def test_the_wrapped_publisher_publishes_as_before_then_turns_the_lane(self):
        calls = []
        lane = SimpleNamespace(turn=lambda house: calls.append("turn"))
        inner = SimpleNamespace(publish=lambda house: calls.append("publish"), state={"x": 1})
        wrapped = H.LanePublisher(inner, lane)
        wrapped.publish(object())
        self.assertEqual(calls, ["publish", "turn"])
        self.assertEqual(wrapped.state, {"x": 1})                      # every other attribute is the original's

        def broken(house):
            raise RuntimeError("site down")
        calls.clear()
        with self.assertRaises(RuntimeError):                           # still the House's "publishing failed"
            H.LanePublisher(SimpleNamespace(publish=broken), lane).publish(object())
        self.assertEqual(calls, ["turn"])
        H.LanePublisher(None, lane).publish(object())                   # a House with no publisher still turns it
        self.assertEqual(calls, ["turn", "turn"])
        with self.assertRaises(AttributeError):
            H.LanePublisher(None, lane).anything

    def test_a_turn_never_raises_into_the_tick(self):
        house = FakeHouse(Clock("2026-10-20T13:00:00Z"))
        lane = H.EventLane(house, "/nonexistent/events", gateway=FakeGateway(), sec=FakeSEC())
        lane.ready = mock.Mock(side_effect=RuntimeError("disk"))
        self.assertFalse(lane.due())
        house._background = mock.Mock(side_effect=RuntimeError("no thread"))
        lane.ready = mock.Mock(return_value=True)
        lane.turn(house)                                                # warned, not raised
        self.assertEqual(house.levels(), ["warning"])


class TheService(unittest.TestCase):
    def config(self, enabled):
        cfg = {"gateway_url": "https://gw.example", "events": {"enabled": enabled, "verdict_usd_day": 4.0}}
        return cfg if enabled is not None else {"gateway_url": "https://gw.example"}

    def test_attached_only_when_switched_on_in_the_houses_own_loop_on_its_box(self):
        from league.service import attach_event_lane

        with tempfile.TemporaryDirectory() as tmp:
            for enabled, jobs, canary, on_box in ((None, True, False, True), (False, True, False, True),
                                                  ("yes", True, False, True), (True, False, False, True),
                                                  (True, True, True, True), (True, True, False, False)):
                house = SimpleNamespace(publisher="original", feeds=None)
                got = attach_event_lane(house, Path(tmp), self.config(enabled), token=lambda: "t" * 20, jobs=jobs,
                                        canary=canary, on_box=on_box)
                self.assertIsNone(got, (enabled, jobs, canary, on_box))
                self.assertEqual(house.publisher, "original")
            publisher = SimpleNamespace(publish=lambda house: None)
            house = SimpleNamespace(publisher=publisher, feeds=None, clock=lambda: 0.0)
            lane = attach_event_lane(house, Path(tmp), self.config(True), token=lambda: "t" * 20, jobs=True,
                                     canary=False, on_box=True)
            self.assertIsInstance(lane, H.EventLane)
            self.assertEqual(lane.root, Path(tmp) / "events")
            self.assertEqual(lane.verdict_usd_day, 4.0)
            self.assertIsInstance(house.publisher, H.LanePublisher)
            self.assertIs(house.publisher.inner, publisher)
            self.assertIsNone(house.feeds)                              # never the feeds lane's object
            self.assertEqual(lane.gateway().url, "https://gw.example")
            self.assertEqual(lane.gateway().token(), "t" * 20)          # the House's own token source

    def test_the_shipped_config_has_it_on_from_release_1019b_and_never_on_a_canary(self):
        from league.service import load_config

        cfg = load_config()
        self.assertIs(cfg["events"]["enabled"], True, "release 1019b switches the lane on (the owner's deploy)")
        self.assertTrue(H.events_enabled(cfg))
        self.assertFalse(H.events_enabled(cfg, canary=True), "never on a canary")
        self.assertFalse(H.events_enabled({**cfg, "events": {**cfg["events"], "enabled": False}}), "false is off")
        self.assertFalse(H.events_enabled({}))
        self.assertFalse(H.events_enabled({"events": {"enabled": True}}, canary=True))
        self.assertTrue(H.events_enabled({"events": {"enabled": True}}))

    def test_the_cli_constants_agree(self):
        from league.events import __main__ as CLI

        self.assertEqual(H.REDECIDE_SESSIONS, CLI.REDECIDE_SESSIONS)


class DecisionsFirst(LaneCase):
    def test_the_open_decision_at_its_time_live_with_its_intents_at_0915(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")   # after Monday's close
        self.at(et("2026-10-20", "09:16"))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("decide-open", "ok"))
        with self.store() as st:
            rows = {r["program"]: dict(r) for r in st.db.execute("SELECT * FROM intents")}
        self.assertEqual(rows["EVL-ERN-READ-O1"]["decided_at"], S.iso(et("2026-10-20", "09:15")))
        self.assertIsNone(rows["EVL-ERN-READ-O1"]["why"])               # live: within 10 minutes of 09:15
        self.assertEqual(rows["EVL-ERN-READ-O1"]["entry_day"], "2026-10-20")
        # the next turn is not the same decision again
        self.assertNotEqual(self.turn()["task"], "decide-open")

    def test_a_missed_decision_is_a_backfill_and_the_live_one_goes_first(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.at(et("2026-10-21", "09:16"))                              # Tuesday's and Wednesday's both undecided
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-open")
        self.assertEqual([r["job"] for r in self.receipts("decide-open:2026-10-21")], ["decide-open:2026-10-21"])
        self.assertEqual(self.receipts("decide-open:2026-10-20"), [])
        self.assertEqual(self.turn()["task"], "decide-open")             # then Tuesday's, as a backfill
        with self.store() as st:
            row = st.db.execute("SELECT why FROM intents WHERE program='EVL-ERN-READ-O1'").fetchone()
        self.assertEqual(row["why"], "backfill")

    def test_the_close_decision_a_minute_after_its_time(self):
        self.at(et("2026-10-20", "15:46"))
        self.mark_recorded()
        with self.store() as st:                                         # the open decision was made
            rid = st.start_receipt("decide-open:2026-10-20", now=et("2026-10-20", "09:15"))
            st.finish_receipt(rid, "ok", {}, now=et("2026-10-20", "09:16"))
        self.assertNotEqual(self.turn().get("task"), "decide-close")
        self.at(et("2026-10-20", "15:47"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-close")
        self.assertEqual(self.receipts("decide-close:2026-10-20")[0]["status"], "ok")

    def test_a_backlog_never_starves_the_record_pass_but_a_live_decision_goes_first(self):
        self.at(et("2026-10-22", "11:00"))                               # Tuesday's and Wednesday's decisions missed
        self.assertEqual(self.turn()["task"], "record")                 # no record pass yet: it goes first
        for _ in range(3):
            self.assertIn(self.turn()["task"], ("decide-open", "decide-close"))
        self.clock.advance(4 * 60)                                       # past a second cadence: the record pass
        self.assertEqual(self.turn()["task"], "record")
        self.at(et("2026-10-23", "09:16"))                               # a live decision beats a starved pass
        self.assertEqual(self.turn()["task"], "decide-open")
        self.assertEqual(self.receipts("decide-open:2026-10-23")[0]["status"], "ok")

    def test_no_task_runs_into_a_decision(self):
        with self.store() as st:
            nxt = self.lane._next_decision(st, et("2026-10-20", "09:14"))
            self.assertEqual(nxt, et("2026-10-20", "09:15"))
            task = H.Task("record", lambda ctx, deadline: {}, H.RECORD_BUDGET)
            bound = self.lane._deadline(st, et("2026-10-20", "09:14"), task) - self.mono()
            self.assertEqual(bound, 60.0 - H.DECISION_MARGIN)
            decide = H.Task("decide-open", lambda ctx, deadline: {}, H.DECIDE_BUDGET)
            self.assertEqual(self.lane._deadline(st, et("2026-10-20", "09:14"), decide) - self.mono(), H.DECIDE_BUDGET)

    def test_a_decision_cut_by_its_bound_goes_on_at_the_next_turn(self):
        for n, cik in ((1, "0000000001"), (2, "0000000002"), (3, "0000000003")):
            self.fetched_8k(f"000000000{n}-26-000101", cik, "2026-10-19 17:00:00")
        self.sec.slow = 0.0
        real = self.sec.__call__

        def slow(url):
            if "action=getcompany" in url:
                self.mono.advance(100)                                   # EDGAR's company feed at its slowest
            return real(url)
        self.lane._sec_base = slow
        self.at(et("2026-10-20", "09:16"))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("decide-open", "cut"))
        self.assertEqual(self.receipts("decide-open:2026-10-20")[0]["status"], "cut")
        last = self.turn()                                               # the cik_info rows it read are kept
        self.assertEqual((last["task"], last["status"]), ("decide-open", "ok"))
        self.assertEqual(self.receipts("decide-open:2026-10-20")[-1]["status"], "ok")

    def test_the_hourly_redecision_of_the_last_sessions_after_the_record_pass(self):
        self.lane = self.new_lane(redecide=True)
        self.at(et("2026-10-21", "10:00"))
        with self.store() as st:
            for day in ("2026-10-20", "2026-10-21"):
                for kind in ("open", "close"):
                    if day == "2026-10-21" and kind == "close":
                        continue
                    rid = st.start_receipt(f"decide-{kind}:{day}", now=et(day, "09:20"))
                    st.finish_receipt(rid, "ok", {}, now=et(day, "09:21"))
        self.assertEqual(self.turn()["task"], "record")                 # the record pass first
        tasks = [self.turn()["task"] for _ in range(5)]
        self.assertEqual(tasks, ["decide-open", "decide-close", "decide-open", "decide-close", "decide-open"])
        self.assertEqual(self.receipts("decide-open:2026-10-19")[-1]["status"], "ok")   # oldest first
        self.assertEqual(len(self.receipts("decide-open:2026-10-19")), 2)
        self.assertNotIn(self.turn().get("task"), ("decide-open", "decide-close"))
        self.clock.advance(3600)
        self.mark_recorded()
        self.assertIn(self.turn()["task"], ("decide-open", "decide-close"))


class VerdictsEarly(LaneCase):
    def test_verdicts_are_asked_from_0730_with_the_decisions_own_code_and_the_decision_asks_none(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.fetched_8k("0000000002-26-000102", "0000000002", "2026-10-20 07:05:00")
        self.at(et("2026-10-20", "07:20"))
        self.mark_recorded()
        self.assertNotEqual(self.turn().get("task"), "verdicts")       # before 07:30 the universe is not fixed yet
        self.assertEqual(self.gw.claude_calls, [])
        self.at(et("2026-10-20", "07:31"))
        self.mark_recorded()
        last = self.turn()
        self.assertEqual(last["task"], "verdicts")
        self.assertEqual(len(self.gw.claude_calls), 2)
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT count(*) FROM intents").fetchone()[0], 0)   # no decision yet
            self.assertEqual(st.db.execute("SELECT count(*) FROM receipts WHERE job LIKE 'decide-%:2026-10-20'")
                             .fetchone()[0], 0)
            jobs = {r[0] for r in st.db.execute("SELECT job FROM receipts")}
        self.assertTrue({"verdicts", "universe"} <= jobs)
        self.at(et("2026-10-20", "09:16"))
        self.assertEqual(self.turn()["task"], "decide-open")
        self.assertEqual(len(self.gw.claude_calls), 2)                   # the decision read the stored verdicts
        with self.store() as st:
            planned = {r[0] for r in st.db.execute("SELECT program FROM intents WHERE status='planned'")}
        self.assertIn("EVL-ERN-READ-O1", planned)                        # AAA scored 3

    def test_ask_only_asks_what_the_decision_would_and_writes_nothing_else(self):
        """The same fixture decided twice: the full decision's Claude calls are exactly ask_only's."""
        bodies = {}
        for mode in ("ask_only", "decide"):
            with tempfile.TemporaryDirectory() as tmp:
                gw, sec = FakeGateway(), FakeSEC()
                with S.Store(tmp) as st:
                    C.refresh(st, gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
                    st.set_meta("tickers@2026-10-20T11:00:05Z", st.put_document(json.dumps(TICKERS).encode(), "t"))
                    from league.events import edgar as E
                    for n, (cik, wall, items) in enumerate((("0000000001", "2026-10-19 17:00:00", ("2.02",)),
                                                            ("0000000002", "2026-10-20 07:05:00", ("8.01",)),
                                                            ("0000000003", "2026-10-20 06:00:00", ("2.02", "9.01")))):
                        acc = f"000000000{n + 1}-26-0002{n:02d}"
                        sec.add(acc, cik, wall, items=items, current=False)
                        E.record_filing(st, sec, {"form": "8-K", "cik": cik, "accession": acc, "items": [],
                                                  "accepted_at": None, "index_url": None}, source="current",
                                        now=et("2026-10-20", "08:00"))
                    with st.tx() as db:
                        for i, sym in enumerate(("AAA", "BBB")):
                            created = et("2026-10-20", "07:00") + dt.timedelta(minutes=i)
                            db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, "
                                       "headline, summary, symbols, live) VALUES(?, ?, NULL, ?, ?, 'benzinga', 'h', 's', "
                                       "?, 1)", (str(i + 1), S.iso(created), S.iso(created),
                                                 S.iso(created + dt.timedelta(minutes=2)), json.dumps([sym])))
                    ctx = R.Context(st, gw, sec, now=lambda: et("2026-10-20", "09:15"))
                    if mode == "ask_only":
                        out = R.decide_open(ctx, dt.date(2026, 10, 20), ask_only=True)
                        self.assertEqual(st.db.execute("SELECT count(*) FROM intents").fetchone()[0], 0)
                        self.assertEqual(st.db.execute("SELECT count(*) FROM receipts").fetchone()[0], 0)
                        self.assertEqual(out["pending"], {})                 # every verdict stored now
                    else:
                        R.decide_open(ctx, dt.date(2026, 10, 20))
                        self.assertGreater(st.db.execute("SELECT count(*) FROM intents").fetchone()[0], 0)
                bodies[mode] = sorted(json.dumps(b, sort_keys=True) for b in gw.claude_calls)
        self.assertEqual(len(bodies["decide"]), 5)                       # three 8-Ks and two headlines
        self.assertEqual(bodies["ask_only"], bodies["decide"])

    def test_the_close_decisions_day_news_is_asked_through_the_session(self):
        self.at(et("2026-10-20", "11:00"))
        with self.store() as st:
            rid = st.start_receipt("decide-open:2026-10-20", now=et("2026-10-20", "09:15"))
            st.finish_receipt(rid, "ok", {}, now=et("2026-10-20", "09:16"))
            created = et("2026-10-20", "10:30")
            st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                          "summary, symbols, live) VALUES('9', ?, NULL, ?, ?, 'benzinga', 'h', 's', ?, 1)",
                          (S.iso(created), S.iso(created), S.iso(created + dt.timedelta(minutes=2)), json.dumps(["CCC"])))
        self.mark_recorded()
        last = self.turn()
        self.assertEqual(last["task"], "verdicts")
        self.assertEqual(len(self.gw.claude_calls), 1)                   # PREREG-EVL-2's day news (NEWS-READ-ON)
        self.assertTrue(self.gw.claude_calls[0]["messages"][0]["content"].startswith("Stock: CCC."))
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT count(*) FROM receipts WHERE job='decide-close:2026-10-20'")
                             .fetchone()[0], 0)

    def test_a_pending_decision_waits_while_its_verdicts_get_no_answer_then_decides(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.gw.claude_status = 400                                       # the gateway refuses every call
        self.at(et("2026-10-20", "09:16"))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("decide-open", "pending"))
        self.assertEqual(self.turn().get("task"), "record")             # no answer: no verdict task spins on it
        calls = len(self.gw.claude_calls)                                # (the pass asked the close decision's once)
        for _ in range(6):
            self.clock.advance(60)
            self.turn()
        self.assertEqual(len(self.gw.claude_calls), calls)               # nothing asked again inside the backoff
        self.gw.claude_status = 200                                      # the gateway admits it now
        self.at(et("2026-10-20", "09:27"))
        self.mark_recorded()
        tasks = [self.turn().get("task") for _ in range(3)]
        self.assertEqual(tasks[0], "decide-open")
        self.assertEqual(self.receipts("decide-open:2026-10-20")[-1]["status"], "ok")
        verdict_receipts = [json.loads(r["summary"]) for r in self.receipts("verdicts")]
        self.assertTrue(any(r.get("refused") for r in verdict_receipts))
        self.assertTrue(any(r.get("answered") for r in verdict_receipts))
        with self.store() as st:
            why = st.db.execute("SELECT why FROM intents WHERE program='EVL-ERN-READ-O1'").fetchone()[0]
        self.assertEqual(why, "backfill")                                # decided 12 minutes late: a backfill

    def test_a_pending_decision_decides_as_soon_as_its_verdicts_are_stored(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.at(et("2026-10-20", "09:16"))
        self.mark_recorded()
        with mock.patch.object(self.lane, "claude_refusal", return_value="deadline"):   # its asks ran out of time
            last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("decide-open", "pending"))
        self.assertEqual(self.turn()["task"], "verdicts")                # pending: its verdicts, before the record pass
        self.assertEqual(self.turn()["task"], "decide-open")             # all stored: decided at once, not in 5 minutes
        self.assertEqual(self.receipts("decide-open:2026-10-20")[-1]["status"], "ok")

    def test_paused_house_and_the_days_line_hold_verdicts(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.fetched_8k("0000000002-26-000102", "0000000002", "2026-10-19 18:00:00")
        self.fetched_8k("0000000003-26-000103", "0000000003", "2026-10-19 19:00:00")
        self.house.pause = {"reason": "maintenance"}
        self.at(et("2026-10-20", "07:31"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "verdicts")
        self.assertEqual(self.gw.claude_calls, [])                       # PAUSE: no paid call
        self.assertTrue(any(json.loads(r["summary"]).get("cut_paused") for r in self.receipts("verdicts")))
        self.house.pause = None
        lane = self.new_lane(verdict_usd_day=0.003)                       # two calls of $0.002 cross the line
        self.lane = lane
        self.mark_recorded()
        self.turn()
        self.assertEqual(len(self.gw.claude_calls), 2)
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT count(*) FROM verdicts").fetchone()[0], 2)
        self.assertIn("warning", self.house.levels())                    # said, once
        self.assertTrue(any("line for verdicts" in text for _, text in self.house.alerts))


class TheBudgetsLine(LaneCase):
    """Release 1019c (the review of r1/alarms, its major 1): the lane's verdicts take their daily line from budget rule 3,
    the lower of `events.verdict_usd_day` and the budget's allowance for the lane (league/ops/budget.py `lane_allowance`),
    so they and every other metered dollar stay under the day's cap."""

    def budget(self, lane_usd_day, *, at=None):
        from league.ops import budget as B

        doc = {"schema": B.SCHEMA, "rule_version": B.RULE_VERSION, "at": self.clock() if at is None else at,
               "cap_usd_day": 5.0, "meters": {"claude": {"lane_usd_day": lane_usd_day, "limited_by": "ceiling"}}}
        (self.root.parent / "budget.json").write_text(json.dumps(doc))

    def three_filings(self):
        self.fetched_8k("0000000001-26-000101", "0000000001", "2026-10-19 17:00:00")
        self.fetched_8k("0000000002-26-000102", "0000000002", "2026-10-19 18:00:00")
        self.fetched_8k("0000000003-26-000103", "0000000003", "2026-10-19 19:00:00")

    def test_the_budgets_allowance_holds_the_verdicts_under_the_config(self):
        self.three_filings()
        self.budget(0.003)                                               # two calls of $0.002 cross the budget's line
        self.at(et("2026-10-20", "07:31"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "verdicts")
        self.assertEqual(len(self.gw.claude_calls), 2, "the third waits: the budget's $0.003, under the config's $5")
        health = self.lane.health()
        self.assertEqual(health["verdict_line_usd"], 0.003)
        self.assertTrue(health["verdict_line_source"].startswith("the budget's allowance: budget.json"),
                        health["verdict_line_source"])
        self.assertTrue(any(json.loads(r["summary"]).get("cut_cap") for r in self.receipts("verdicts")))
        self.assertTrue(any("line for verdicts is reached (the budget's allowance" in text for _, text in self.house.alerts))

    def test_the_config_holds_when_it_is_lower_and_no_budget_is_the_rules_floor(self):
        self.lane = self.new_lane(verdict_usd_day=0.003)
        self.budget(4.0)
        self.assertEqual(self.lane.verdict_line(self.clock_dt()), {"usd_day": 0.003, "source": "events.verdict_usd_day"})
        (self.root.parent / "budget.json").unlink()
        self.lane = self.new_lane()
        line = self.lane.verdict_line(self.clock_dt())
        self.assertEqual(line["usd_day"], 3.0, "no budget.json: the rule's own no-profit lane line, never the config's $5")
        self.assertIn("the floor (no budget.json yet)", line["source"])
        self.budget(0.0)                                                 # the rule could not read the Claude meter
        self.assertEqual(self.lane.verdict_line(self.clock_dt())["usd_day"], 0.0)
        with mock.patch("league.ops.budget.lane_allowance", side_effect=RuntimeError("boom")):
            self.assertEqual(self.lane.verdict_line(self.clock_dt())["usd_day"], 0.0, "no allowance read: no paid call")

    def test_a_line_of_nothing_asks_nothing(self):
        self.three_filings()
        self.budget(0.0)
        self.at(et("2026-10-20", "07:31"))
        self.mark_recorded()
        self.turn()
        self.assertEqual(self.gw.claude_calls, [])


class TheRecordPass(LaneCase):
    def test_bounded_and_resumable(self):
        for n in range(1, 4):
            self.sec.add(f"000000000{n}-26-000301", f"000000000{n}", f"2026-10-20 06:5{n}:00")
        self.sec.add("0000000009-26-000309", "0000000009", "2026-10-20 06:58:00")    # an unlisted filer: never fetched
        self.gw.news = [{"id": 77, "created_at": "2026-10-20T10:55:00Z", "updated_at": None, "headline": "h",
                         "summary": "s", "source": "benzinga", "symbols": ["AAA"]}]
        self.sec.slow = 50.0                       # each filing: an index page and a document, 100 s (the bound is 90)
        self.at(et("2026-10-20", "07:01"))
        last = self.turn()
        self.assertEqual(last["task"], "record")
        with self.store() as st:
            status = dict(st.db.execute("SELECT accession, status FROM filings").fetchall())
            self.assertEqual(st.db.execute("SELECT count(*) FROM news").fetchone()[0], 1)
        self.assertEqual(len(status), 4)                                  # every new entry is stored at once
        self.assertEqual(sum(1 for s in status.values() if s == "fetched"), 1)   # the bound is read between filings
        self.assertEqual(status["0000000009-26-000309"], "listed")
        self.clock.advance(121)
        self.sec.slow = 0.0
        self.assertEqual(self.turn()["task"], "record")
        with self.store() as st:
            status = dict(st.db.execute("SELECT accession, status FROM filings").fetchall())
        self.assertEqual(sorted(a for a, s in status.items() if s == "fetched"),
                         ["0000000001-26-000301", "0000000002-26-000301", "0000000003-26-000301"])
        self.assertEqual(status["0000000009-26-000309"], "listed")
        self.assertEqual(self.receipts("record")[-1]["status"], "ok")

    def test_no_tickers_copy_holds_the_8ks_not_the_news_or_the_form_4s(self):
        with self.store() as st:
            st.db.execute("DELETE FROM meta WHERE key LIKE 'tickers@%'")
        self.sec.add("0000000001-26-000301", "0000000001", "2026-10-20 06:51:00")
        self.gw.news = [{"id": 78, "created_at": "2026-10-20T10:55:00Z", "updated_at": None, "headline": "h",
                         "summary": "s", "source": "benzinga", "symbols": ["AAA"]}]
        real = self.sec.__call__

        def no_tickers(url):
            if url.endswith("company_tickers.json"):
                raise OSError("sec down")
            return real(url)
        self.lane._sec_base = no_tickers
        self.at(et("2026-10-20", "07:01"))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("record", "ok"))
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT status FROM filings").fetchone()[0], "listed")   # waits, not lost
            self.assertEqual(st.db.execute("SELECT count(*) FROM news").fetchone()[0], 1)
        summary = json.loads(self.receipts("record")[-1]["summary"])
        self.assertIn("error", summary["tickers"])
        self.assertEqual(summary["8-K"]["waiting"], 1)

    def test_every_two_minutes(self):
        self.at(et("2026-10-20", "07:01"))
        self.assertEqual(self.turn()["task"], "record")
        self.clock.advance(60)
        self.assertNotEqual(self.turn().get("task"), "record")
        self.clock.advance(61)
        self.assertEqual(self.turn()["task"], "record")

    def test_the_record_pass_asks_todays_verdicts_with_the_time_left(self):
        self.sec.add("0000000001-26-000301", "0000000001", "2026-10-20 07:40:00")
        self.at(et("2026-10-20", "07:52"))
        with self.store() as st:   # the 07:00 snapshot, the backfill and the nightly jobs are not this test's
            st.set_meta("evl:backfill:2026-10-15", "done")
            st.set_meta("evl:backfill:2026-10-16", "done")
            st.set_meta("evl:backfill:2026-10-19", "done")
        self.assertEqual(self.turn()["task"], "record")
        self.assertEqual(len(self.gw.claude_calls), 1)
        receipt = json.loads(self.receipts("record")[-1]["summary"])
        self.assertEqual(receipt["verdicts"][0]["decision"], "open")
        self.assertEqual(receipt["verdicts"][0]["missing"], 0)


class Nightly(LaneCase):
    def test_equity_after_the_close_then_score_screen_and_report(self):
        self.at(et("2026-10-20", "16:04"))
        self.mark_recorded()
        with self.store() as st:
            for kind, t in (("open", "09:15"), ("close", "15:46")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-20", now=et("2026-10-20", t))
                st.finish_receipt(rid, "ok", {}, now=et("2026-10-20", t))
        self.lane._redecide_next = et("2026-10-21", "00:00")
        self.assertEqual(self.turn()["task"], "equity")
        with self.store() as st:
            self.assertEqual(st.meta(SC.equity_key(dt.date(2026, 10, 20))), repr(2000.0))
        self.at(et("2026-10-20", "20:31"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "score")
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "screen")
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "report")
        self.assertTrue((self.root / "reports" / "2026-10-20.txt").exists())
        self.mark_recorded()
        self.assertNotIn(self.turn().get("task"), ("score", "screen", "report", "equity"))

    def test_the_screen_task_runs_the_band_review_of_the_real_fills(self):
        """PREREG-EVL-3 section 2 on the House: after the night's looks, the screen task reviews the real fills the
        House's book wrote back (league/events/bands.py `review`): a Probe program whose last 50 real-money events lost
        more than $150 net is back at learning, and the screen's receipt says so."""
        from league.events import bands as BA

        with self.store() as st:
            for kind, t in (("open", "09:15"), ("close", "15:46")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-20", now=et("2026-10-20", t))
                st.finish_receipt(rid, "ok", {}, now=et("2026-10-20", t))
            st.set_meta(SC.equity_key(dt.date(2026, 10, 20)), repr(2000.0))
            BA.set_band(st, "EVL-ERN-READ-O1", 2, "probe", since="2026-10-19T20:00:00Z", why="look 1 passed")
            for i in range(50):                       # $3.50 lost on each of the last 50: -$175, past -$150
                for side, price, t in (("buy", 10.0, "13:30"), ("sell", 9.65, "20:00")):
                    BA.record_fill(st, program="EVL-ERN-READ-O1", version=2, event=f"8k:invented-{i}", side=side,
                                   qty=10, price=price, fee=0.0, filled_at=f"2026-10-20T{t}:{i:02d}Z", band="probe")
        self.lane._redecide_next = et("2026-10-21", "00:00")
        self.at(et("2026-10-20", "20:31"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "score")
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "screen")
        with self.store() as st:
            self.assertEqual(BA.bands(st)[("EVL-ERN-READ-O1", 2)], "learning")
        summary = json.loads(self.receipts("screen")[-1]["summary"])
        self.assertEqual(summary["review"], [{"program": "EVL-ERN-READ-O1", "version": 2, "band": "learning"}])

    def test_the_score_pass_is_bounded_and_resumable(self):
        intents = [{"program": "EVL-ERN-READ-O1", "version": 1, "event": f"8k:{n}"} for n in range(5)]
        settled = []

        def settle_one(st, gw, intent, *, now):
            settled.append(intent["event"])
            self.mono.advance(50)
            return "settled"
        self.at(et("2026-10-20", "20:31"))
        with mock.patch.object(SC, "due", return_value=intents), mock.patch.object(SC, "settle_one", settle_one):
            with self.store() as st:
                ctx = H.LaneContext(self.lane, st, H.LaneGateway(self.gw, self.lane, None, cut=False), self.sec,
                                    self.lane.now)
                first = self.lane._score(ctx, self.mono() + H.SCORE_BUDGET)
                self.assertFalse(first["complete"])
                self.assertEqual(settled, ["8k:0", "8k:1", "8k:2"])
                second = self.lane._score(ctx, self.mono() + H.SCORE_BUDGET)
                self.assertTrue(second["complete"])
                self.assertEqual(settled, [f"8k:{n}" for n in range(5)])  # each once
        self.assertEqual([r["status"] for r in self.receipts("score")], ["partial", "ok"])

    def test_the_tickers_snapshot_at_seven_on_a_weekday(self):
        with self.store() as st:
            st.db.execute("DELETE FROM meta WHERE key LIKE 'tickers@2026-10-20%'")
        self.at(et("2026-10-20", "06:59"))
        self.mark_recorded()
        self.assertNotEqual(self.turn().get("task"), "tickers")
        self.at(et("2026-10-20", "07:01"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "tickers")
        with self.store() as st:
            keys = [r[0] for r in st.db.execute("SELECT key FROM meta WHERE key LIKE 'tickers@2026-10-20%'")]
        self.assertEqual(keys, [f"tickers@{S.iso(et('2026-10-20', '07:01'))}"])


class TheBackfill(LaneCase):
    def test_a_filing_the_live_pass_missed_is_fetched_and_its_session_decided_again(self):
        self.sec.add("0000000002-26-000401", "0000000002", "2026-10-19 16:30:00", current=False)
        self.sec.daily["20261019"] = ["0000000002-26-000401"]
        self.at(et("2026-10-20", "11:00"))
        self.mark_recorded()
        with self.store() as st:
            for day in ("2026-10-15", "2026-10-16"):
                st.set_meta(f"evl:backfill:{day}", "done")
            for kind, day, t in (("open", "2026-10-20", "09:15"),):
                rid = st.start_receipt(f"decide-{kind}:{day}", now=et(day, t))
                st.finish_receipt(rid, "ok", {}, now=et(day, t))
        self.lane._redecide_next = et("2026-10-21", "00:00")
        self.lane._looks[("open", dt.date(2026, 10, 20))] = H.VerdictLook(self.clock_dt(), 0, False)
        self.lane._looks[("close", dt.date(2026, 10, 20))] = H.VerdictLook(self.clock_dt(), 0, False)
        self.lane._events_at = et("2026-10-20", "00:00")
        with self.store() as st:   # Monday's decisions were made too
            for kind, t in (("open", "09:15"), ("close", "15:46")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-19", now=et("2026-10-19", t))
                st.finish_receipt(rid, "ok", {}, now=et("2026-10-19", t))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("backfill", "ok"))
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT status FROM filings WHERE accession='0000000002-26-000401'")
                             .fetchone()[0], "fetched")
            self.assertEqual(st.meta("evl:backfill:2026-10-19"), "done")
        self.assertIn(("open", dt.date(2026, 10, 20)), self.lane._redecide)   # its entry session, decided again
        self.assertEqual(self.turn()["task"], "decide-open")

    def test_an_unpublished_index_waits_an_hour(self):
        self.at(et("2026-10-20", "11:00"))
        with self.store() as st:
            for day in ("2026-10-15", "2026-10-16"):
                st.set_meta(f"evl:backfill:{day}", "done")
        due = self.lane._backfill_due
        with self.store() as st:
            self.assertEqual(due(st, self.clock_dt(), dt.date(2026, 10, 20), []), dt.date(2026, 10, 19))
            ctx = H.LaneContext(self.lane, st, H.LaneGateway(self.gw, self.lane, None, cut=False), self.sec, self.lane.now)
            out = self.lane._backfill(ctx, dt.date(2026, 10, 19), self.mono() + 90)
            self.assertEqual(out["_status"], "waiting")
            self.assertIsNone(due(st, self.clock_dt(), dt.date(2026, 10, 20), []))
            self.assertEqual(due(st, self.clock_dt() + dt.timedelta(hours=1), dt.date(2026, 10, 20), []),
                             dt.date(2026, 10, 19))
        self.assertEqual([lvl for lvl, _ in self.house.alerts if lvl == "warning"], [])


class Failures(LaneCase):
    def test_a_failing_lane_warns_at_most_hourly_per_task_and_never_errors(self):
        self.gw.fail = OSError("gateway down")
        self.sec.fail = OSError("sec down")
        self.at(et("2026-10-20", "09:00"))
        for _ in range(120):                                              # two hours of turns, a minute apart
            self.lane.run()
            self.clock.advance(60)
        levels = self.house.levels()
        self.assertNotIn("error", levels)
        warnings = [text for level, text in self.house.alerts if level == "warning"]
        self.assertGreater(len(warnings), 0)
        per_task = {}
        for text in warnings:
            task = text.split("the event lane's ", 1)[1].split(" failed", 1)[0]
            per_task[task] = per_task.get(task, 0) + 1
        self.assertTrue(all(n <= 2 for n in per_task.values()), per_task)   # once an hour each, over two hours

    def test_a_record_pass_that_fails_closes_its_receipt_and_waits(self):
        self.at(et("2026-10-20", "07:01"))
        with mock.patch.object(H.EventLane, "_record_steps", side_effect=RuntimeError("boom")):
            last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("record", "failed"))
        self.assertEqual(self.receipts("record")[-1]["status"], "failed")
        self.clock.advance(180)
        self.assertNotEqual(self.turn().get("task"), "record")           # FAIL_BACKOFF, not every turn
        self.clock.advance(600)
        self.assertEqual(self.turn()["task"], "record")


class OnTheHousesTick(unittest.TestCase):
    """The real House: its tick's publish turns the lane on the feeds lane (`feeds:evl`), `house.feeds` stays None, and
    a lane whose every task fails costs warnings, never an error alert."""

    def setUp(self):
        from league.tests.test_house import HouseCase

        self.case = HouseCase("setUp")
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.house = self.case.house
        self.clock = self.case.clock
        self.clock.now = et("2026-10-20", "09:16").timestamp()          # Tue Oct 20
        self.root = Path(self.house.root) / "events"
        self.gw = FakeGateway()
        with S.Store(self.root) as st:
            C.refresh(st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
            st.set_meta("evl:lane:sessions_at", "2026-10-20T13:00:00Z")
            st.set_meta("tickers@2026-10-20T11:00:05Z", st.put_document(json.dumps(TICKERS).encode(), "t"))
            for kind, wall in (("open", "09:15"), ("close", "15:47")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-19", now=et("2026-10-19", wall))
                st.finish_receipt(rid, "ok", {}, now=et("2026-10-19", wall))
        self.mono = Mono()

    def attach(self, gw):
        lane = H.EventLane(self.house, self.root, gateway=gw, sec=FakeSEC(), monotonic=self.mono, sleep=self.mono.advance)
        lane._redecide_next = dt.datetime(2100, 1, 1, tzinfo=UTC)
        self.house.publisher = H.LanePublisher(self.house.publisher, lane)
        return lane

    def alerts(self, level):
        return [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if e.payload.get("level") == level]

    def test_the_tick_runs_the_lane_on_the_feeds_lane(self):
        lane = self.attach(self.gw)
        self.house.tick()
        self.house.wait(30)
        jobs = [e.payload for e in self.house.ledger.iter(kinds="ops.job") if e.payload.get("key") == H.BACKGROUND_KEY]
        self.assertEqual([j["state"] for j in jobs], ["started", "finished"])
        self.assertEqual(lane.health()["last"]["task"], "decide-open")    # the 09:15 decision, first
        self.assertIsNone(self.house.feeds)
        with S.Store(self.root) as st:
            self.assertEqual(st.db.execute("SELECT status FROM receipts WHERE job='decide-open:2026-10-20'")
                             .fetchone()[0], "ok")
        self.assertEqual(self.alerts("error"), [])

    def test_a_failing_lane_on_the_tick_is_warnings_never_an_error(self):
        broken = FakeGateway()
        broken.fail = OSError("gateway down")
        lane = self.attach(broken)
        lane._sec_base = FakeSEC()
        lane._sec_base.fail = OSError("sec down")
        for _ in range(40):                                               # twenty minutes of thirty-second ticks
            self.house.tick()
            self.house.wait(30)
            self.clock.advance(30)
        self.assertEqual(self.alerts("error"), [])
        lane_warnings = [a for a in self.alerts("warning") if "event lane" in a.get("text", "")]
        self.assertGreater(len(lane_warnings), 0)
        self.assertLess(len(lane_warnings), 10)                            # the House's repeat rule never fires
        jobs = [e.payload for e in self.house.ledger.iter(kinds="ops.job") if e.payload.get("key") == H.BACKGROUND_KEY]
        self.assertTrue(jobs and all(j["state"] in ("started", "finished") for j in jobs))   # never "failed"

    def test_the_legacy_feed_paths_answer_as_with_no_feeds(self):
        """The lane is never `house.feeds`: with it attached, the House's research capabilities (which every
        non-None `feeds` changes, whatever it holds) read exactly as before."""
        agent = self.case.seated()
        before = self.house.research_capabilities(agent)
        self.attach(self.gw)
        self.house.tick()
        self.house.wait(30)
        self.assertIsNone(self.house.feeds)
        self.assertEqual(self.house.research_capabilities(agent), before)
        # why the lane takes the publisher hook: any non-None feeds object changes this answer
        self.house.feeds = SimpleNamespace(describe=lambda: {})
        try:
            self.assertNotEqual(self.house.research_capabilities(agent), before)
        finally:
            self.house.feeds = None


if __name__ == "__main__":
    unittest.main()
