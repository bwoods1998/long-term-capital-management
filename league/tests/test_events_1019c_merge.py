"""RELEASE 1019c, the merge of `r3/lane-1019c` (#578) and `r2/alarms` (#575): a decision's receipt carries both the
lane's `kept` (league/events/run.py `_scope`: the programs a written look of their group leaves as they were) and the
alarms' verdict tally `verdicts: {needed, answered}` (the stall job's `evl_verdicts`, league/ops/evl_health.py
`tally`). A kept program is asked no verdict, so its events never enter the tally: `evl_verdicts` never waits on a
frozen group. Synthetic data only: every filing, verdict and receipt here is invented."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest

from league.events import calendar as C
from league.events import edgar as E
from league.events import programs as P
from league.events import run as R
from league.events import store as S
from league.ops import evl_health as H
from league.tests.test_events_run import FakeGateway, sec_pages

UTC = dt.timezone.utc


def sec_pages_801(url):
    """`sec_pages`, with the invented 8-K's items read as 8.01 (a material non-earnings 8-K: EVL-8K-READ-O1's family)."""
    page = sec_pages(url)
    return page.replace(b"Item 2.02: Results", b"Item 8.01: Other Events") if url.endswith("-index.htm") else page


class TheTallyLeavesAFrozenGroupOut(unittest.TestCase):
    MONDAY = dt.date(2026, 10, 19)
    AAA = ("0000000001-26-000001", "0000000001")       # accepted 07:05 ET Monday (sec_pages), items 8.01 here

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.now = dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC)
        C.refresh(self.st, FakeGateway({"AAA": 3}), dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec_pages("x/company_tickers.json"), "t"))
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"
        acc, cik = self.AAA
        entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": ["8.01"], "accepted_at": None,
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
        self.assertEqual(E.record_filing(self.st, sec_pages_801, entry, source="current", now=self.now), "fetched")

    def tearDown(self):
        P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    @staticmethod
    def refusing() -> FakeGateway:
        gw = FakeGateway({"AAA": 3})
        gw.post_json = lambda path, body, headers=None: (400, {"error": "invented refusal"})
        return gw

    def decide(self, at: dt.datetime) -> dict:
        return R.decide_open(R.Context(self.st, self.refusing(), sec_pages_801, now=lambda: at), self.MONDAY)

    def latest(self) -> dict:
        row = self.st.db.execute("SELECT status, summary, finished_at FROM receipts WHERE job='decide-open:2026-10-19' "
                                 "ORDER BY id DESC LIMIT 1").fetchone()
        return {"status": row[0], "summary": row[1], "finished_at": row[2]}

    def test_a_frozen_groups_verdicts_are_not_in_the_tally(self):
        first = self.decide(self.now)
        self.assertEqual(first["pending"], {"EVL-8K-READ-O1": 1, "EVL-8K-READ-O1@v2": 1},
                         "Claude refuses: both versions of the READ program wait for the one verdict")
        self.assertEqual(first["verdicts"], {"needed": 1, "answered": 0}, "one (event, prompt) verdict, unanswered")
        self.assertEqual(H.tally(self.latest()), (1, 1), "the stall job reads it: one verdict needed, none answered")
        # A look of version 2 written over Monday freezes its group: both versions of EVL-8K-READ-O1 and its control.
        self.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES(?, 2, 1, ?, 1, 0)",
                           ("EVL-8K-READ-O1", S.iso(C.session(self.st, self.MONDAY).close_at)))
        out = self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))     # the hourly re-decision, inside the window
        self.assertEqual(out["pending"], {}, "the group is kept: nothing waits")
        for key in ("EVL-8K-READ-O1", "EVL-8K-READ-O1@v2", "EVL-CTRL-8K-ALL-O1"):
            self.assertIn("a look of its group is written over this session", out["kept"][key]["why"], key)
        self.assertEqual(out["kept"]["EVL-8K-READ-O1@v2"]["unjudged"], [f"8k:{self.AAA[0]}"],
                         "the READ program's event is left out unjudged (no verdict stored), never asked")
        self.assertEqual(out["verdicts"], {"needed": 0, "answered": 0}, "a kept program is asked nothing: no tally")
        latest = self.latest()
        self.assertEqual(latest["status"], "ok")
        self.assertEqual(H.tally(latest), (0, 0), "evl_verdicts never waits on a frozen group")


if __name__ == "__main__":
    unittest.main()
