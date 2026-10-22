"""End to end with fakes: record a filing, decide Monday's open, check the intents and what was paid for."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from league.tests.evl6_fakes import on_1019h
from league.events import programs as P
from league.events import run as R
from league.events import store as S

FIX = Path(__file__).resolve().parent / "fixtures" / "evl"
UTC = dt.timezone.utc


def weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


class FakeGateway:
    def __init__(self, scores):
        self.scores = scores
        self.claude_calls = []
        self.last_headers = {}

    def get_json(self, path, params=None):
        if path.endswith("/v2/calendar"):
            s, e = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
            return [{"date": d.isoformat(), "open": "09:30", "close": "16:00"} for d in weekdays(s, e)]
        if path.endswith("/v2/assets"):
            return [{"symbol": sym, "status": "active", "tradable": True, "class": "us_equity", "exchange": "NASDAQ"}
                    for sym in ("AAA", "BBB")]
        if path.endswith("/v2/stocks/bars"):
            end = S.parse_iso(params["end"])
            start = dt.date.fromisoformat(params["start"])
            return {"bars": {sym: [{"t": f"{d}T04:00:00Z", "o": 20, "h": 20, "l": 20, "c": 20, "v": 1_000_000}
                                   for d in weekdays(start, (end - dt.timedelta(minutes=1)).date())]
                             for sym in params["symbols"].split(",")}, "next_page_token": None}
        if path.endswith("/v1beta1/news"):
            return {"news": [], "next_page_token": None}
        raise AssertionError(path)

    def post_json(self, path, body, headers=None):
        self.claude_calls.append(body)
        text = body["messages"][0]["content"]
        score = next(v for k, v in self.scores.items() if f"ticker {k}" in text)
        self.last_headers = {"x-ltcm-cost-usd": "0.002"}
        return 200, {"content": [{"type": "text", "text": json.dumps({"score": score, "guidance": "raised", "reasons": []})}],
                     "stop_reason": "end_turn"}


def sec_pages(url):
    tickers = {"0": {"cik_str": 1, "ticker": "AAA", "title": "Alpha Inc."},
               "1": {"cik_str": 2, "ticker": "BBB", "title": "Beta Inc."}}
    if url.endswith("company_tickers.json"):
        return json.dumps(tickers).encode()
    if "action=getcompany" in url:
        return b"<feed><company-info><assigned-sic>3571</assigned-sic></company-info><entry><filing-type>10-Q</filing-type>" \
               b"<filing-date>2026-08-01</filing-date></entry></feed>"
    if url.endswith("-index.htm"):
        acc = url.rsplit("/", 1)[1].replace("-index.htm", "")
        accepted = {"0000000001-26-000001": "2026-10-19 07:05:00", "0000000002-26-000002": "2026-10-19 07:10:00",
                    "0000000001-26-000003": "2026-10-19 07:20:00", "0000000002-26-000004": "2026-10-18 20:00:00"}[acc]
        return (f'<div class="infoHead">Accepted</div><div class="info">{accepted}</div>'
                f'<div class="infoHead">Items</div><div class="info">Item 2.02: Results</div>'
                f'<table><tr><td>1</td><td>press release</td><td><a href="/Archives/x/{acc}/ex99.htm">ex99.htm</a></td>'
                f'<td>EX-99.1</td><td>100</td></tr></table>').encode()
    if url.endswith("ex99.htm"):
        return ("<html><body>" + "Quarterly results were strong and guidance was raised. " * 10 + "</body></html>").encode()
    raise AssertionError(url)


@on_1019h
class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.now = dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC)
        self.gw = FakeGateway({"AAA": 3, "BBB": 1})
        self.ctx = R.Context(self.st, self.gw, sec_pages, now=lambda: self.now)
        from league.events import calendar as C
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec_pages("x/company_tickers.json"), "t"))
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"

    def tearDown(self):
        P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    def entry(self, acc, cik):
        return {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": ["2.02"], "accepted_at": None,
                "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}

    def test_monday_open_end_to_end(self):
        from league.events import edgar as E
        for acc, cik in (("0000000001-26-000001", "0000000001"), ("0000000002-26-000002", "0000000002"),
                         ("0000000001-26-000003", "0000000001"),     # AAA again Monday: one position per issuer
                         ("0000000002-26-000004", "0000000002")):    # Sunday 20:00 ET = 00:00Z: before registration
            self.assertEqual(E.record_filing(self.st, sec_pages, self.entry(acc, cik), source="current", now=self.now), "fetched")
        out = R.decide_open(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["EVL-ERN-READ-O1"]["planned"], 1)       # AAA scored 3; BBB scored 1
        self.assertEqual(out["EVL-CTRL-ERN-ALL-O1"]["planned"], 2)
        rows = {(r["program"], r["symbol"]): dict(r) for r in self.st.db.execute("SELECT * FROM intents")}
        o1 = rows[("EVL-ERN-READ-O1", "AAA")]
        self.assertEqual((o1["entry_day"], o1["entry_at"], o1["exit_day"], o1["mode"]), ("2026-10-19", "open", "2026-10-19", "shadow"))
        self.assertEqual(o1["decided_at"], "2026-10-19T13:15:00Z")
        # two AAA filings: one position per issuer (the second is skipped); each event was read once
        skipped = self.st.db.execute("SELECT count(*) FROM intents WHERE program='EVL-ERN-READ-O1' AND version=1 AND status LIKE 'skipped%'").fetchone()[0]
        self.assertEqual(skipped, 1)
        self.assertEqual(len(self.gw.claude_calls), 3)
        self.assertTrue(all(c["model"] == "claude-haiku-4-5-20251001" and c["temperature"] == 0 for c in self.gw.claude_calls))
        again = R.decide_open(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(again["EVL-ERN-READ-O1"]["known"], 2)
        self.assertEqual(len(self.gw.claude_calls), 3)               # replay reads the stored verdicts
        # Release 1019c: the decision's receipt tallies the distinct verdicts it needed and those stored (the stall job's
        # `evl_verdicts`): three events, each read once whatever programs read it.
        summary = json.loads(self.st.db.execute("SELECT summary FROM receipts WHERE job='decide-open:2026-10-19' ORDER BY id "
                                                "DESC").fetchone()[0])
        self.assertEqual(summary["verdicts"], {"needed": 3, "answered": 3})


    def test_read_programs_wait_for_verdicts(self):
        from league.events import edgar as E
        E.record_filing(self.st, sec_pages, self.entry("0000000001-26-000001", "0000000001"), source="current", now=self.now)
        refusing = FakeGateway({"AAA": 3})
        refusing.post_json = lambda path, body, headers=None: (400, {"error": "temperature may only be 0"})
        ctx = R.Context(self.st, refusing, sec_pages, now=lambda: self.now)
        out = R.decide_open(ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["pending"], {"EVL-ERN-READ-O1": 1, "EVL-ERN-READ-O3": 1,  # PREREG-EVL-2's two READ rows too
                                          "EVL-ERN-GUIDE-O1": 1, "EVL-ERN-READ3-O1": 1,
                                          "EVL-ERN-READ-O1@v2": 1, "EVL-ERN-GUIDE-O1@v2": 1})  # and PREREG-EVL-3's
        self.assertEqual(out["EVL-CTRL-ERN-ALL-O1"]["planned"], 1)       # controls need no verdict
        asked = R.decide_open(ctx, dt.date(2026, 10, 19), ask_only=True)   # the House's verdicts ahead of a decision
        self.assertEqual(asked["pending"], out["pending"], "version 1 and version 2 of one program count apart")
        status, summary = self.st.db.execute("SELECT status, summary FROM receipts WHERE job='decide-open:2026-10-19'").fetchone()
        self.assertEqual(status, "pending")
        self.assertEqual(json.loads(summary)["verdicts"], {"needed": 1, "answered": 0}, "asked, refused: no answer stored")
        self.assertIsNone(self.st.db.execute("SELECT 1 FROM intents WHERE program='EVL-ERN-READ-O1' AND version=1").fetchone())
        later = R.decide_open(self.ctx, dt.date(2026, 10, 19))          # the gateway admits it now
        self.assertEqual(later["pending"], {})
        self.assertEqual(later["EVL-ERN-READ-O1"]["planned"], 1)


    def test_c1_close_decision_reads_the_1529_bar_against_the_last_close_before_acceptance(self):
        from league.events import edgar as E
        for acc, cik in (("0000000001-26-000001", "0000000001"), ("0000000002-26-000002", "0000000002")):
            E.record_filing(self.st, sec_pages, self.entry(acc, cik), source="current", now=self.now)
        minute = {"AAA": 20.9, "BBB": 20.5}   # the prior close is 20 (FakeGateway's daily bars): 1.045 and 1.025

        def get_json(path, params=None, base=self.gw.get_json):
            if path.endswith("/v2/stocks/bars") and params.get("timeframe") == "1Min":
                sym = params["symbols"]
                end = S.parse_iso(params["end"])
                bars = [{"t": S.iso(end - dt.timedelta(minutes=k)), "o": 20, "h": 21, "l": 19, "c": minute[sym], "v": 100}
                        for k in (3, 2, 1)]  # bars starting 15:27, 15:28, 15:29 (the last ends at 15:30)
                return {"bars": {sym: bars}, "next_page_token": None}
            return base(path, params)
        self.gw.get_json = get_json
        late = dt.datetime(2026, 10, 19, 19, 46, 30, tzinfo=UTC)          # 15:46:30 EDT
        ctx = R.Context(self.st, self.gw, sec_pages, now=lambda: late)
        out = R.decide_close(ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["EVL-ERN-REACT-C1"]["planned"], 1)
        row = self.st.db.execute("SELECT * FROM intents WHERE program='EVL-ERN-REACT-C1'").fetchone()
        self.assertEqual((row["symbol"], row["entry_at"], row["exit_day"]), ("AAA", "close", "2026-10-20"))
        self.assertAlmostEqual(row["rank_key"], 20.9 / 20)
        self.assertEqual(row["decided_at"], "2026-10-19T19:46:00Z")
        mark = self.st.db.execute("SELECT * FROM marks WHERE symbol='AAA'").fetchone()
        self.assertEqual((mark["label"], mark["px"]), ("1530", 20.9))


if __name__ == "__main__":
    unittest.main()
