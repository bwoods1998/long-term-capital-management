"""PREREG-EVL-2's nine programs (registered 2026-10-19T03:04:07Z): their rows, windows, the insider-buy trigger, the
exit at the next open, the limit at entry, and Monday's open and close decided end to end with fakes."""

import datetime as dt
import json
import tempfile
import unittest

from league.events import calendar as C
from league.events import programs as P
from league.events import run as R
from league.events import score as SCORE
from league.events import screen as SC
from league.events import store as S
from league.tests.test_events_run import FakeGateway, sec_pages, weekdays

UTC = dt.timezone.utc
WAVE2 = ("EVL-ERN-REACT-ON", "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON",
         "EVL-INS-BUY-O5", "EVL-ERN-REACT-READ-C1", "EVL-ERN-READ3-O1", "EVL-CTRL-NEWS-DAY-ON")


class DayGateway(FakeGateway):
    """The run test's gateway with minute bars (each symbol's 15:29 ET bar) and news verdicts by symbol."""

    def __init__(self, scores, minute_close):
        super().__init__(scores)
        self.minute_close = minute_close

    def get_json(self, path, params=None):
        if path.endswith("/v2/stocks/bars") and params.get("timeframe") == "1Min":
            sym = params["symbols"]
            day = S.parse_iso(params["end"]).date()
            t29 = dt.datetime.combine(day, dt.time(19, 29), tzinfo=UTC)
            return {"bars": {sym: [{"t": S.iso(t29), "o": 20, "h": 21, "l": 20, "c": self.minute_close[sym], "v": 100}]},
                    "next_page_token": None}
        return super().get_json(path, params)

    def post_json(self, path, body, headers=None):
        text = body["messages"][0]["content"]
        if text.startswith("Stock: "):
            self.claude_calls.append(body)
            sym = text.split()[1].rstrip(".")
            self.last_headers = {"x-ltcm-cost-usd": "0.001"}
            return 200, {"content": [{"type": "text", "text": json.dumps({"score": self.scores[sym], "reasons": []})}],
                         "stop_reason": "end_turn"}
        return super().post_json(path, body, headers)


class Wave2Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.now = dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC)
        self.gw = DayGateway({"AAA": 3, "BBB": 1}, {"AAA": 21.0, "BBB": 20.5})
        self.ctx = R.Context(self.st, self.gw, sec_pages, now=lambda: self.now)
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec_pages("x/company_tickers.json"), "t"))
        self._pinned = (P.REGISTERED_AT, P.REGISTERED_AT_2)
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"

    def tearDown(self):
        P.REGISTERED_AT, P.REGISTERED_AT_2 = self._pinned
        self.st.close()
        self.tmp.cleanup()

    # ------------------------------------------------------------------------------------------- the rows
    def test_the_nine_rows_and_the_judge_lists(self):
        self.assertEqual(self._pinned[1], "2026-10-19T03:04:07Z")
        rows = [p for p in P.PROGRAMS if p.prereg == 2]
        self.assertEqual(tuple(p.id for p in rows), WAVE2)
        self.assertEqual([p.id for p in rows if p.seatable], list(WAVE2[:5]))
        self.assertTrue(all(p.version == 1 for p in rows))
        self.assertEqual({p.id for p in rows if p.exit_at == "open"},
                         {"EVL-ERN-REACT-ON", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON", "EVL-CTRL-NEWS-DAY-ON"})
        self.assertTrue(all(p.prereg == 1 and p.exit_at == "close" and p.rule in ("min2", "none") or not p.reads
                            for p in P.PROGRAMS[:9]))
        self.assertEqual(set(SC.SEATABLE[4:]), set(WAVE2[:5]))
        self.assertEqual(set(SC.RECORDS[5:]), set(WAVE2[5:]))
        self.assertEqual(SC.CONTROLS["EVL-ERN-GUIDE-O1"], "EVL-CTRL-ERN-ALL-O1")
        self.assertEqual(SC.CONTROLS["EVL-NEWS-READ-ON"], "EVL-CTRL-NEWS-DAY-ON")
        self.assertTrue(all(SC.HOLDS[p] == 1 for p in WAVE2 if p != "EVL-INS-BUY-O5"))
        self.assertEqual(SC.HOLDS["EVL-INS-BUY-O5"], 5)

    def test_the_day_news_window_ends_at_t29(self):
        self.assertEqual(P.day_news_window(self.st, dt.date(2026, 10, 19)),
                         (dt.datetime(2026, 10, 19, 13, 0, tzinfo=UTC), dt.datetime(2026, 10, 19, 19, 29, tzinfo=UTC)))
        self.assertEqual(P.day_news_window(self.st, dt.date(2026, 11, 2))[1],          # EST
                         dt.datetime(2026, 11, 2, 20, 29, tzinfo=UTC))

    def test_an_overnight_program_exits_at_the_next_open(self):
        day = dt.date(2026, 10, 19)
        cand = P.Candidate("8k:x", "0000000001", "AAA", dt.datetime(2026, 10, 19, 15, 0, tzinfo=UTC), 1.05, None, {})
        for pid, exit_day, exit_at in (("EVL-ERN-REACT-ON", "2026-10-20", "open"), ("EVL-ERN-REACT-C1", "2026-10-20", "close"),
                                       ("EVL-INS-BUY-O5", "2026-10-23", "close")):
            P.write_intents(self.st, P.BY_ID[pid], day, [cand], decided_at=dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC))
            row = self.st.db.execute("SELECT exit_day, exit_at FROM intents WHERE program=?", (pid,)).fetchone()
            self.assertEqual((row["exit_day"], row["exit_at"]), (exit_day, exit_at), pid)
        ladder = SCORE.exit_ladder(self.st, dt.date(2026, 10, 20), "open")
        self.assertEqual((ladder[0][0].day, ladder[0][1]), (dt.date(2026, 10, 20), "open"))
        self.assertEqual((ladder[1][0].day, ladder[1][1]), (dt.date(2026, 10, 21), "close"))

    def test_the_limit_at_entry_binds_the_second_wave_only(self):
        uni = {"prev_close": 10.0}
        self.assertTrue(SCORE._above_limit({"program": "EVL-ERN-REACT-ON"}, uni, 12.51))
        self.assertFalse(SCORE._above_limit({"program": "EVL-ERN-REACT-ON"}, uni, 12.50))
        self.assertFalse(SCORE._above_limit({"program": "EVL-ERN-REACT-C1"}, uni, 30.0))     # PREREG-EVL-1: no limit
        self.assertTrue(SCORE._above_limit({"program": "EVL-INS-BUY-O1"}, {"prev_close": None}, 5.0))

    # ------------------------------------------------------------------------------------------- insider buys
    def _form4(self, acc, cik, accepted, owners, txs):
        knowable = accepted + dt.timedelta(minutes=10)
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, received_at, "
                           "source, status) VALUES(?, '4', ?, 'Co', '[]', ?, ?, ?, 'current', 'fetched')",
                           (acc, cik, S.iso(accepted), S.iso(knowable), S.iso(knowable)))
        for i, (director, officer, ten) in enumerate(owners):
            self.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, is_director, is_officer, is_ten_pct) "
                               "VALUES(?, ?, ?, ?, ?)", (acc, f"9{i}{acc[-3:]}", director, officer, ten))
        for seq, (day, code, acq, shares, price) in enumerate(txs):
            self.st.db.execute("INSERT INTO form4_tx(accession, seq, tx_date, code, shares, price, acquired) "
                               "VALUES(?, ?, ?, ?, ?, ?, ?)", (acc, seq, day, code, shares, price, acq))

    def test_the_insider_buy_trigger(self):
        at = dt.datetime(2026, 10, 19, 21, 0, tzinfo=UTC)        # Mon 17:00 ET
        self._form4("a-001", "0000000001", at, [(1, 0, 0)], [("2026-10-16", "P", "A", 1000, 30.0), ("2026-10-19", "P", "A", 1000, 30.0)])
        self._form4("a-002", "0000000002", at, [(0, 1, 0)], [("2026-10-19", "P", "A", 1000, 40.0)])          # $40k
        self._form4("a-003", "0000000003", at, [(0, 0, 1)], [("2026-10-19", "P", "A", 10000, 40.0)])         # 10% owner only
        self._form4("a-004", "0000000004", at, [(1, 0, 0)], [("2026-10-05", "P", "A", 10000, 40.0)])         # 14 days old
        self._form4("a-005", "0000000005", at, [(1, 0, 0)], [("2026-10-19", "P", "A", 10000, None),          # no price: 0
                                                               ("2026-10-19", "S", "D", 10000, 40.0)])
        self._form4("a-006", "0000000006", at, [(1, 0, 0), (0, 0, 1)], [("2026-10-10", "P", "A", 2000, 25.0),  # joint: once
                                                                         ("2026-10-18", "A", "A", 9000, 0.0)])
        got = {r["accession"]: r["purchase_value"] for r in P.ins_buys(self.st, at - dt.timedelta(hours=1),
                                                                         at + dt.timedelta(hours=1))}
        self.assertEqual(got, {"a-001": 60000.0, "a-006": 50000.0})

    # ------------------------------------------------------------------------------------------- end to end
    def test_monday_open_guide_top_and_their_registration_time(self):
        from league.events import edgar as E
        for acc, cik in (("0000000001-26-000001", "0000000001"), ("0000000002-26-000002", "0000000002"),
                         ("0000000001-26-000003", "0000000001")):
            entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": ["2.02"], "accepted_at": None,
                     "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
            self.assertEqual(E.record_filing(self.st, sec_pages, entry, source="current", now=self.now), "fetched")
        # knowable 11:15Z (AAA), 11:20Z (BBB), 11:30Z (AAA again): the second wave counts only after its own time
        P.REGISTERED_AT_2 = "2026-10-19T11:25:00Z"
        out = R.decide_open(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["EVL-ERN-READ-O1"]["planned"], 1)          # AAA's first filing (PREREG-EVL-1)
        self.assertEqual(out["EVL-ERN-GUIDE-O1"]["planned"], 1)         # AAA's third filing only (raised, score 3)
        self.assertEqual(out["EVL-ERN-READ3-O1"]["planned"], 1)
        events = {r["program"]: r["event"] for r in self.st.db.execute("SELECT program, event FROM intents WHERE status='planned' AND version=1")}
        self.assertEqual(events["EVL-ERN-GUIDE-O1"], "8k:0000000001-26-000003")
        self.assertEqual(events["EVL-ERN-READ-O1"], "8k:0000000001-26-000001")
        P.REGISTERED_AT_2 = "2026-10-19T03:04:07Z"
        self.st.db.execute("DELETE FROM intents WHERE program IN ('EVL-ERN-GUIDE-O1', 'EVL-ERN-READ3-O1')")
        out = R.decide_open(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["EVL-ERN-GUIDE-O1"]["planned"], 2)         # AAA (3) and BBB (1): both "raised", >= 1
        self.assertEqual(out["EVL-ERN-READ3-O1"]["planned"], 1)         # AAA only

    def _news(self, nid, symbol, knowable):
        created = knowable - dt.timedelta(minutes=2)
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, summary, "
                           "symbols, live) VALUES(?, ?, ?, ?, ?, 'benzinga', 'h', 's', ?, 1)",
                           (nid, S.iso(created), S.iso(created), S.iso(created), S.iso(knowable), json.dumps([symbol])))

    def test_monday_close_decides_the_day_news_and_overnight_programs(self):
        self._news("n1", "AAA", dt.datetime(2026, 10, 19, 14, 0, tzinfo=UTC))   # 10:00 ET
        self._news("n2", "AAA", dt.datetime(2026, 10, 19, 15, 0, tzinfo=UTC))   # AAA again: one a day
        self._news("n3", "BBB", dt.datetime(2026, 10, 19, 16, 0, tzinfo=UTC))   # BBB: score 1, +2.5%
        self._news("n4", "BBB", dt.datetime(2026, 10, 19, 19, 35, tzinfo=UTC))  # after T29: no program takes it
        self._news("n5", "AAA", dt.datetime(2026, 10, 19, 12, 55, tzinfo=UTC))  # pre-market: NEWS-READ-O1's, not these
        self.now = dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC)
        out = R.decide_close(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["pending"], {})
        self.assertEqual(out["events"]["day_news"], 3)
        self.assertEqual(out["EVL-NEWS-READ-ON"]["planned"], 1)          # AAA (3); BBB scored 1
        self.assertEqual(out["EVL-CTRL-NEWS-DAY-ON"]["planned"], 2)      # AAA and BBB, any score
        self.assertEqual(out["EVL-NEWS-REACT-ON"]["planned"], 1)         # AAA 21/20 = 1.05; BBB 1.025
        self.assertEqual(out["EVL-ERN-REACT-C1"]["planned"], 0)
        rows = {(r["program"], r["symbol"]): dict(r) for r in self.st.db.execute(
            "SELECT * FROM intents WHERE status='planned'")}
        react = rows[("EVL-NEWS-REACT-ON", "AAA")]
        self.assertEqual((react["event"], react["entry_day"], react["entry_at"], react["exit_day"], react["exit_at"]),
                         ("news:n1", "2026-10-19", "close", "2026-10-20", "open"))
        self.assertAlmostEqual(react["rank_key"], 1.05)
        self.assertEqual(rows[("EVL-NEWS-READ-ON", "AAA")]["event"], "news:n1")   # tie on score: the earliest
        asked = sorted(c["messages"][0]["content"].split()[1].rstrip(".") for c in self.gw.claude_calls)
        self.assertEqual(asked, ["AAA", "AAA", "BBB"])                    # n1, n2, n3: each read once
        again = R.decide_close(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(again["EVL-NEWS-REACT-ON"]["known"], 2)
        self.assertEqual(len(self.gw.claude_calls), 3)

    def test_the_close_decisions_verdict_tally_names_its_reading_programs(self):
        """Release 1019c (the review of r1/alarms, its major 3): the close decision's receipt carries the verdict tally
        `verdicts: {needed, answered}` (the distinct (event, prompt) verdicts its reading programs need), so the stall
        job's evl_verdicts sees a close-entry READ program (NEWS-READ-ON, versions 1 and 2) wait as it sees the open's."""
        self._news("n1", "AAA", dt.datetime(2026, 10, 19, 14, 0, tzinfo=UTC))
        self._news("n3", "BBB", dt.datetime(2026, 10, 19, 16, 0, tzinfo=UTC))
        self.now = dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC)
        answer = self.gw.post_json
        self.gw.post_json = lambda path, body, headers=None: (400, {"error": "refused by the gateway"})
        asked = R.decide_close(self.ctx, dt.date(2026, 10, 19), ask_only=True)
        self.assertEqual(asked["verdicts"], {"needed": 2, "answered": 0}, "two articles, one verdict each, for all programs")
        self.assertIsNone(self.st.db.execute("SELECT 1 FROM receipts WHERE job='decide-close:2026-10-19'").fetchone(),
                          "ask_only writes no receipt")
        out = R.decide_close(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["pending"], {"EVL-NEWS-READ-ON": 2, "EVL-NEWS-READ-ON@v2": 2, "EVL-CTRL-NEWS-DAY-ON": 2},
                         "the control ranks by the same verdicts, so it waits too")
        status, summary = self.st.db.execute("SELECT status, summary FROM receipts WHERE job='decide-close:2026-10-19' "
                                             "ORDER BY id DESC").fetchone()
        self.assertEqual((status, json.loads(summary)["verdicts"]), ("pending", {"needed": 2, "answered": 0}))
        self.gw.post_json = answer
        out = R.decide_close(self.ctx, dt.date(2026, 10, 19))
        self.assertEqual(out["pending"], {})
        status, summary = self.st.db.execute("SELECT status, summary FROM receipts WHERE job='decide-close:2026-10-19' "
                                             "ORDER BY id DESC").fetchone()
        self.assertEqual((status, json.loads(summary)["verdicts"]), ("ok", {"needed": 2, "answered": 2}))


if __name__ == "__main__":
    unittest.main()
