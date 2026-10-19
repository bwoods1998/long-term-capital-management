import datetime as dt
import tempfile
import unittest

from league.events import store as S


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_schema_version_is_pinned_and_checked(self):
        self.assertEqual(self.st.meta("schema_version"), str(S.SCHEMA_VERSION))
        self.st.set_meta("schema_version", "999")
        self.st.close()
        with self.assertRaises(RuntimeError):
            S.Store(self.tmp.name)
        self.st = S.Store.__new__(S.Store)  # tearDown's close on a never-opened object
        self.st.db = type("D", (), {"close": lambda self: None})()

    def test_documents_round_trip_by_digest_and_are_idempotent(self):
        a = self.st.put_document(b"<html>results</html>", "EX-99.1")
        b = self.st.put_document(b"<html>results</html>", "EX-99.1")
        self.assertEqual(a, b)
        self.assertEqual(self.st.get_document(a), b"<html>results</html>")
        self.assertEqual(self.st.db.execute("SELECT count(*) FROM documents").fetchone()[0], 1)

    def test_iso_is_utc_with_z_and_refuses_naive_times(self):
        t = dt.datetime(2026, 10, 19, 9, 15, 30, 123, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        self.assertEqual(S.iso(t), "2026-10-19T13:15:30Z")
        self.assertEqual(S.parse_iso("2026-10-19T13:15:30Z"), t.replace(microsecond=0))
        with self.assertRaises(ValueError):
            S.iso(dt.datetime(2026, 10, 19))

    def test_intent_status_only_moves_forward(self):
        with self.st.tx() as db:
            db.execute("INSERT INTO intents(program, version, event, symbol, decided_at, entry_day, entry_at, exit_day, "
                       "exit_at, mode, status) VALUES('P', 1, '8k:x', 'ABC', 'z', '2026-10-19', 'open', '2026-10-19', "
                       "'close', 'shadow', 'planned')")
        self.assertTrue(self.st.move_intent("P", 1, "8k:x", "entered"))
        self.assertFalse(self.st.move_intent("P", 1, "8k:x", "planned"))
        self.assertTrue(self.st.move_intent("P", 1, "8k:x", "exited"))
        self.assertFalse(self.st.move_intent("P", 1, "8k:x", "skipped:late"))

    def test_a_failed_transaction_rolls_back(self):
        with self.assertRaises(ZeroDivisionError):
            with self.st.tx() as db:
                db.execute("INSERT INTO meta(key, value) VALUES('k', 'v')")
                1 / 0
        self.assertIsNone(self.st.meta("k"))


if __name__ == "__main__":
    unittest.main()
