import datetime as dt
import json
import tempfile
import unittest

from league.events import calendar as C
from league.events import programs as P
from league.events import store as S

UTC = dt.timezone.utc


class FakeCal:
    def get_json(self, path, params=None):
        start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
        out, d = [], start
        while d <= end:
            if d.weekday() < 5:
                out.append({"date": d.isoformat(), "open": "09:30", "close": "16:00"})
            d += dt.timedelta(days=1)
        return out


def add_filing(st, accession, form, cik, accepted, items=(), status="fetched"):
    st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, received_at, source, "
                  "status) VALUES(?, ?, ?, 'Co', ?, ?, ?, ?, 'test', ?)",
                  (accession, form, cik, json.dumps(list(items)), S.iso(accepted), S.iso(accepted + dt.timedelta(minutes=10)),
                   S.iso(accepted), status))


def add_f4(st, accession, cik, accepted, owner, director=1, code="P", acquired="A", shares=1000.0, price=30.0):
    add_filing(st, accession, "4", cik, accepted)
    st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, officer_title, is_ten_pct) "
                  "VALUES(?, ?, 'X', ?, 0, NULL, 0)", (accession, owner, director))
    st.db.execute("INSERT INTO form4_tx(accession, seq, security, tx_date, code, shares, price, acquired, owned_after) "
                  "VALUES(?, 0, 'Common', '2026-10-19', ?, ?, ?, ?, 0)", (accession, code, shares, price, acquired))


class ProgramsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        C.refresh(self.st, FakeCal(), dt.date(2026, 9, 1), dt.date(2026, 12, 31))
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"
        self.elig = {c: {"symbol": s, "adv20": 2e7, "bench": "IWM"} for c, s in
                     (("0000000001", "AAA"), ("0000000002", "BBB"), ("0000000003", "CCC"))}

    def tearDown(self):
        P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    def test_unpinned_registration_refuses(self):
        P.REGISTERED_AT = None
        with self.assertRaises(RuntimeError):
            P.filings_in(self.st, "8-K", dt.datetime(2026, 10, 19, tzinfo=UTC), dt.datetime(2026, 10, 20, tzinfo=UTC))

    def test_open_window_is_exactly_the_events_entering_at_that_open(self):
        lo, hi = P.open_window(self.st, dt.date(2026, 10, 20))
        self.assertEqual((lo, hi), (dt.datetime(2026, 10, 19, 13, 0, tzinfo=UTC), dt.datetime(2026, 10, 20, 13, 0, tzinfo=UTC)))
        for t in (lo, hi - dt.timedelta(seconds=1)):
            self.assertEqual(C.first_open_entry(self.st, t).day, dt.date(2026, 10, 20))
        self.assertEqual(C.first_open_entry(self.st, hi).day, dt.date(2026, 10, 21))

    def test_registration_time_excludes_earlier_events(self):
        add_filing(self.st, "a", "8-K", "0000000001", dt.datetime(2026, 10, 19, 0, 45, tzinfo=UTC), ["2.02"])  # knowable 00:55
        add_filing(self.st, "b", "8-K", "0000000002", dt.datetime(2026, 10, 19, 10, 0, tzinfo=UTC), ["2.02"])
        rows = P.filings_in(self.st, "8-K", dt.datetime(2026, 10, 16, 13, 0, tzinfo=UTC),
                            dt.datetime(2026, 10, 19, 13, 0, tzinfo=UTC))
        self.assertEqual([r["accession"] for r in rows], ["b"])

    def test_read_programs_take_score_two_and_above_and_controls_take_all(self):
        rows = []
        for acc, cik, items in (("e1", "0000000001", ["2.02", "9.01"]), ("e2", "0000000002", ["2.02"]),
                                ("e3", "0000000003", ["8.01"]), ("e4", "0000000009", ["2.02"])):
            add_filing(self.st, acc, "8-K", cik, dt.datetime(2026, 10, 19, 11, 0, tzinfo=UTC), items)
        rows = P.filings_in(self.st, "8-K", *P.open_window(self.st, dt.date(2026, 10, 19)))
        scores = {"e1": 2, "e2": 1, "e3": 3}
        pick = lambda prog: [c.event for c in P.select(P.BY_ID[prog], rows, eligible=self.elig.get,
                                                       verdict=lambda r: scores.get(r["accession"]))]
        self.assertEqual(pick("EVL-ERN-READ-O1"), ["8k:e1"])            # e2 scores 1, e4 is not eligible
        self.assertEqual(pick("EVL-CTRL-ERN-ALL-O1"), ["8k:e1", "8k:e2"])
        self.assertEqual(pick("EVL-8K-READ-O1"), ["8k:e3"])
        self.assertEqual(pick("EVL-CTRL-8K-ALL-O1"), ["8k:e3"])

    def test_c1_needs_the_reaction(self):
        add_filing(self.st, "r1", "8-K", "0000000001", dt.datetime(2026, 10, 19, 11, 0, tzinfo=UTC), ["2.02"])
        add_filing(self.st, "r2", "8-K", "0000000002", dt.datetime(2026, 10, 19, 11, 0, tzinfo=UTC), ["2.02"])
        rows = P.filings_in(self.st, "8-K", *P.close_window(self.st, dt.date(2026, 10, 19)))
        ratios = {"r1": 1.05, "r2": 1.03}
        got = P.select(P.BY_ID["EVL-ERN-REACT-C1"], rows, eligible=self.elig.get, verdict=lambda r: None,
                       reaction=lambda r, u: ratios[r["accession"]])
        self.assertEqual([(c.event, c.rank_key) for c in got], [("8k:r1", 1.05)])

    def test_insider_cluster_triggers_once(self):
        t0 = dt.datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
        add_f4(self.st, "f1", "0000000001", t0, "0000000101", shares=1000, price=30.0)          # $30k, one owner
        add_f4(self.st, "f2", "0000000001", t0 + dt.timedelta(days=1), "0000000102", shares=1000, price=30.0)  # 2 owners, $60k
        add_f4(self.st, "f3", "0000000001", t0 + dt.timedelta(days=2), "0000000103", shares=1000, price=30.0)  # still a cluster
        add_f4(self.st, "f4", "0000000002", t0, "0000000201", director=0, shares=99999, price=99.0)          # not D/O
        add_f4(self.st, "f5", "0000000002", t0, "0000000202", director=1, code="S", acquired="D")          # a sale
        lo, hi = dt.datetime(2026, 10, 19, tzinfo=UTC), dt.datetime(2026, 10, 25, tzinfo=UTC)
        got = P.ins_triggers(self.st, lo, hi)
        self.assertEqual([r["accession"] for r in got], ["f2"])
        self.assertAlmostEqual(got[0]["cluster_value"], 60000.0)

    def test_insider_cluster_needs_two_filings_and_dates_in_the_window(self):
        t0 = dt.datetime(2026, 10, 19, 14, 0, tzinfo=UTC)
        # one joint filing with two directors: one filing only, no cluster
        add_f4(self.st, "j1", "0000000003", t0, "0000000301", shares=2000, price=30.0)
        self.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, officer_title, "
                           "is_ten_pct) VALUES('j1', '0000000302', 'Y', 1, 0, NULL, 0)")
        # a purchase dated three weeks before the filing does not count
        add_filing(self.st, "old", "4", "0000000003", t0 + dt.timedelta(hours=1))
        self.st.db.execute("INSERT INTO form4_owners VALUES('old', '0000000303', 'Z', 1, 0, NULL, 0)")
        self.st.db.execute("INSERT INTO form4_tx VALUES('old', 0, 'Common', '2026-09-28', 'P', 5000, 30.0, 'A', 0)")
        lo, hi = dt.datetime(2026, 10, 19, tzinfo=UTC), dt.datetime(2026, 10, 25, tzinfo=UTC)
        self.assertEqual(P.ins_triggers(self.st, lo, hi), [])
        # a second filing by another director, dated inside the window, completes it
        add_f4(self.st, "j2", "0000000003", t0 + dt.timedelta(days=1), "0000000304", shares=100, price=30.0)
        self.assertEqual([r["accession"] for r in P.ins_triggers(self.st, lo, hi)], ["j2"])
        # and 12 days later a fresh cluster may trigger again
        t1 = t0 + dt.timedelta(days=13)
        add_f4(self.st, "k1", "0000000003", t1, "0000000305", shares=1000, price=30.0)
        add_f4(self.st, "k2", "0000000003", t1 + dt.timedelta(hours=2), "0000000306", shares=1000, price=30.0)
        for acc, day in (("k1", "2026-11-01"), ("k2", "2026-11-01")):
            self.st.db.execute("UPDATE form4_tx SET tx_date=? WHERE accession=?", (day, acc))
        later = P.ins_triggers(self.st, dt.datetime(2026, 10, 31, tzinfo=UTC), dt.datetime(2026, 11, 5, tzinfo=UTC))
        self.assertEqual([r["accession"] for r in later], ["k2"])

    def test_news_one_per_issuer_highest_score_then_earliest(self):
        rows = [{"id": "n1", "cik": "0000000001", "symbol": "AAA", "knowable_at": "2026-10-19T11:00:00Z"},
                {"id": "n2", "cik": "0000000001", "symbol": "AAA", "knowable_at": "2026-10-19T11:05:00Z"},
                {"id": "n3", "cik": "0000000001", "symbol": "AAA", "knowable_at": "2026-10-19T11:10:00Z"},
                {"id": "n4", "cik": "0000000002", "symbol": "BBX", "knowable_at": "2026-10-19T11:00:00Z"}]
        scores = {"n1": 2, "n2": 3, "n3": 3, "n4": 3}
        got = P.select(P.BY_ID["EVL-NEWS-READ-O1"], rows, eligible=self.elig.get, verdict=lambda r: scores[r["id"]])
        self.assertEqual([c.event for c in got], ["news:n2"])   # n4's symbol is not the eligible class
        scores = {"n1": 0, "n2": -1, "n3": -2, "n4": 0}
        got = P.select(P.BY_ID["EVL-CTRL-NEWS-ALL-O1"], rows, eligible=self.elig.get, verdict=lambda r: scores[r["id"]])
        self.assertEqual([c.event for c in got], ["news:n1"])   # a score of 0 beats -1 (no falsy-zero slip)

    def test_intents_hold_rules_and_one_position_per_issuer(self):
        prog = P.BY_ID["EVL-ERN-READ-O3"]
        day = dt.date(2026, 10, 19)
        mk = lambda e, cik, minute: P.Candidate(e, cik, "AAA", dt.datetime(2026, 10, 19, 11, minute, tzinfo=UTC), 2.0, 2, {})
        got = P.write_intents(self.st, prog, day, [mk("8k:x", "0000000001", 0), mk("8k:y", "0000000001", 5)],
                              decided_at=dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC))
        self.assertEqual(got, {"planned": 1, "skipped": 1, "known": 0})
        row = self.st.db.execute("SELECT * FROM intents WHERE event='8k:x'").fetchone()
        self.assertEqual((row["entry_day"], row["entry_at"], row["exit_day"], row["exit_at"]),
                         ("2026-10-19", "open", "2026-10-21", "close"))
        # the issuer is still held two days later: a new event is skipped; 6 sessions after its exit it is not
        later = P.write_intents(self.st, prog, dt.date(2026, 10, 21), [mk("8k:z", "0000000001", 0)],
                                decided_at=dt.datetime(2026, 10, 21, 13, 15, tzinfo=UTC))
        self.assertEqual(later["skipped"], 1)
        free = P.write_intents(self.st, prog, dt.date(2026, 10, 29), [mk("8k:w", "0000000001", 0)],
                               decided_at=dt.datetime(2026, 10, 29, 13, 15, tzinfo=UTC))
        self.assertEqual(free["planned"], 1)
        c1 = P.write_intents(self.st, P.BY_ID["EVL-ERN-REACT-C1"], day, [mk("8k:c", "0000000002", 0)],
                             decided_at=dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC))
        row = self.st.db.execute("SELECT * FROM intents WHERE event='8k:c'").fetchone()
        self.assertEqual((row["entry_at"], row["exit_day"]), ("close", "2026-10-20"))
        self.assertEqual(c1["planned"], 1)


if __name__ == "__main__":
    unittest.main()
