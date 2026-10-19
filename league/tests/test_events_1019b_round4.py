"""Release 1019b's fourth round (the captain's, after the third reviews): a real-money decision reads a FILING only once
it was FETCHED before the decision time (league/events/book.py `_stored_before`), and the shadow's one position per
issuer also looks ahead (league/events/programs.py `_held_recently`, amendment A72). Synthetic data only."""

import datetime as dt
import tempfile
import unittest

from league.events import book as EB
from league.events import calendar as C
from league.events import programs as P
from league.events import store as S
from league.tests.test_events_run import FakeGateway

UTC = dt.timezone.utc
SHA_RAW, SHA_TEXT = "a" * 64, "b" * 64


class AFilingIsStoredWhenItIsFetched(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = S.Store(self.tmp.name)
        self.addCleanup(self.st.close)
        for sha, at in ((SHA_RAW, "2026-11-04T20:46:40Z"), (SHA_TEXT, "2026-11-04T20:45:00Z")):
            self.st.db.execute("INSERT INTO documents(sha, kind, bytes, path, stored_at) VALUES(?, 'raw', 1, 'x', ?)",
                               (sha, at))
        self.lane = EB.Lane(self.st.root / S.DB_NAME)
        self.addCleanup(self.lane.close)

    def at(self, text):
        return S.parse_iso(text)

    def test_a_filing_listed_before_the_decision_and_fetched_after_it_is_not_stored_before(self):
        row = {"accession": "0000000001-26-000001", "raw_sha": SHA_RAW, "text_sha": SHA_TEXT,
               "received_at": "2026-11-04T20:40:00Z"}
        self.assertFalse(EB._stored_before(row, self.at("2026-11-04T20:46:00Z"), self.lane),
                         "C1's 15:46 ET close decision: the filing was fetched at 15:46:40")
        self.assertTrue(EB._stored_before(row, self.at("2026-11-04T20:47:00Z"), self.lane))

    def test_the_latest_document_time_counts_and_an_unreadable_one_fails_closed(self):
        row = {"accession": "0000000001-26-000002", "raw_sha": SHA_TEXT, "text_sha": None,
               "received_at": "2026-11-04T20:40:00Z"}
        self.assertTrue(EB._stored_before(row, self.at("2026-11-04T20:46:00Z"), self.lane))
        missing = dict(row, raw_sha="c" * 64)
        self.assertFalse(EB._stored_before(missing, self.at("2026-11-04T23:00:00Z"), self.lane), "no document row")
        self.assertTrue(EB._stored_before(dict(row, raw_sha=None), self.at("2026-11-04T23:00:00Z"), self.lane),
                        "a row naming no document (none the House writes) is read by its listing time")
        self.assertFalse(EB._stored_before(row, self.at("2026-11-04T23:00:00Z"), None), "no lane to read it from")
        listed_late = dict(row, received_at="2026-11-04T20:50:00Z")
        self.assertFalse(EB._stored_before(listed_late, self.at("2026-11-04T20:46:00Z"), self.lane),
                         "never before its listing time")

    def test_a_news_article_is_stored_when_it_is_read(self):
        row = {"id": "n1", "received_at": "2026-11-04T13:10:00Z"}
        self.assertTrue(EB._stored_before(row, self.at("2026-11-04T13:15:00Z"), self.lane))
        self.assertFalse(EB._stored_before(row, self.at("2026-11-04T13:05:00Z"), self.lane))


class OnePositionPerIssuerLooksAhead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = S.Store(self.tmp.name)
        self.addCleanup(self.st.close)
        C.refresh(self.st, FakeGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 11, 2), dt.date(2026, 12, 31))]
        self.prog = P.BY_KEY[("EVL-INS-BUY-O1", 2)]

    def intent(self, day, status="planned", cik="0000000009"):
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, 'S', ?, 'z', ?, 'open', ?, "
                           "'close', NULL, 'shadow', ?, NULL)",
                           (self.prog.id, self.prog.version, f"ev:{day}:{status}", cik, day.isoformat(),
                            day.isoformat(), status))

    def test_a_late_event_for_an_earlier_session_is_skipped_beside_a_later_written_intent(self):
        d = self.days
        self.intent(d[6])                                   # written first (decided on time)
        self.assertTrue(P._held_recently(self.st, self.prog, "0000000009", d[3]), "3 sessions before: skipped (A72)")
        self.assertTrue(P._held_recently(self.st, self.prog, "0000000009", d[1]), "5 sessions before: skipped")
        self.assertFalse(P._held_recently(self.st, self.prog, "0000000009", d[0]), "6 sessions before: free")
        self.assertFalse(P._held_recently(self.st, self.prog, "0000000010", d[3]), "another issuer")

    def test_the_look_back_is_unchanged_and_a_skip_is_no_holding(self):
        d = self.days
        self.intent(d[1])
        self.assertTrue(P._held_recently(self.st, self.prog, "0000000009", d[6]), "held within the last 5 sessions")
        self.assertFalse(P._held_recently(self.st, self.prog, "0000000009", d[7]))
        self.intent(d[20], status="skipped:issuer-held")
        self.assertFalse(P._held_recently(self.st, self.prog, "0000000009", d[18]), "a skipped intent holds nothing")


if __name__ == "__main__":
    unittest.main()
