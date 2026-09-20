import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from league.ledger import ChainBroken, HOUSE, Ledger, LedgerConflict, LedgerError, public_view


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "ledger.sqlite"
        self.ledger = Ledger(self.path, clock=lambda: 1789000000.5)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_rows_chain_and_verify(self):
        a = self.ledger.append("agent.born", {"name": "a"}, agent="a1")
        b = self.ledger.append("credit.grant", {"usd": "1.50"}, agent="a1")
        self.assertEqual(a.previous_hash, "genesis")
        self.assertEqual(b.previous_hash, a.digest)
        self.assertEqual(self.ledger.verify(), 2)
        self.assertEqual(self.ledger.head(), (2, b.digest))
        self.assertEqual(a.at, "2026-09-10T00:26:40.500Z")

    def test_same_id_same_content_is_idempotent(self):
        first = self.ledger.append("book.fill", {"q": "1"}, agent="a1", id="fill-1")
        again = self.ledger.append("book.fill", {"q": "1"}, agent="a1", id="fill-1")
        self.assertEqual(first, again)
        self.assertEqual(self.ledger.count(), 1)

    def test_same_id_different_content_conflicts(self):
        self.ledger.append("book.fill", {"q": "1"}, agent="a1", id="fill-1")
        with self.assertRaises(LedgerConflict):
            self.ledger.append("book.fill", {"q": "2"}, agent="a1", id="fill-1")
        with self.assertRaises(LedgerConflict):
            self.ledger.append("book.fill", {"q": "1"}, agent="a2", id="fill-1")

    def test_unknown_kind_and_bad_payload_refused(self):
        with self.assertRaises(LedgerError):
            self.ledger.append("desk.thought", {})
        with self.assertRaises(LedgerError):
            self.ledger.append("agent.thought", ["not", "a", "dict"])
        with self.assertRaises(LedgerError):
            self.ledger.append("agent.thought", {"x": float("nan")})

    def test_rows_cannot_be_updated_or_deleted(self):
        self.ledger.append("agent.born", {"name": "a"}, agent="a1")
        raw = sqlite3.connect(str(self.path))
        with self.assertRaises(sqlite3.DatabaseError):
            raw.execute("UPDATE ledger SET payload = '{}'")
        with self.assertRaises(sqlite3.DatabaseError):
            raw.execute("DELETE FROM ledger")
        raw.close()

    def test_an_edit_behind_the_triggers_is_found(self):
        for i in range(3):
            self.ledger.append("credit.charge", {"usd": str(i)}, agent="a1")
        raw = sqlite3.connect(str(self.path))
        raw.execute("DROP TRIGGER ledger_no_update")
        raw.execute("UPDATE ledger SET payload = '{\"usd\":\"9\"}' WHERE seq = 2")
        raw.commit()
        raw.close()
        with self.assertRaises(ChainBroken):
            self.ledger.verify()

    def test_a_deleted_row_is_found(self):
        for i in range(3):
            self.ledger.append("credit.charge", {"usd": str(i)}, agent="a1")
        raw = sqlite3.connect(str(self.path))
        raw.execute("DROP TRIGGER ledger_no_delete")
        raw.execute("DELETE FROM ledger WHERE seq = 2")
        raw.commit()
        raw.close()
        with self.assertRaises(ChainBroken):
            self.ledger.verify()

    def test_agent_view_is_own_public_rows_without_private_keys(self):
        self.ledger.append("agent.thought", {"text": "mine", "_prompt": "secret"}, agent="a1")
        self.ledger.append("agent.thought", {"text": "theirs"}, agent="a2")
        self.ledger.append("provider.request", {"cost": "0.01"}, agent="a1")
        view = self.ledger.agent_view("a1")
        self.assertEqual([row["payload"] for row in view], [{"text": "mine"}])

    def test_public_view_strips_nested_private_keys(self):
        self.assertEqual(public_view({"a": [{"_x": 1, "y": 2}], "_b": 1}), {"a": [{"y": 2}]})

    def test_reads_filter_and_page(self):
        for i in range(5):
            self.ledger.append("credit.charge", {"i": i}, agent="a1" if i % 2 else "a2")
        self.ledger.append("ops.alert", {"m": "x"})
        self.assertEqual(len(self.ledger.read(kinds="credit.charge")), 5)
        self.assertEqual(len(self.ledger.read(kinds=["credit.charge", "ops.alert"], agent=HOUSE)), 1)
        newest = self.ledger.read(kinds="credit.charge", limit=2, newest=True)
        self.assertEqual([e.payload["i"] for e in newest], [3, 4])
        self.assertEqual(self.ledger.last("credit.charge", agent="a2").payload["i"], 4)
        self.assertEqual([e.payload["i"] for e in self.ledger.iter(kinds="credit.charge", agent="a1")], [1, 3])
        self.assertEqual(self.ledger.count(kinds="credit.charge", agent="a1"), 2)

    def test_concurrent_appends_keep_one_chain(self):
        def work(n):
            for i in range(25):
                self.ledger.append("credit.charge", {"n": n, "i": i}, agent=f"a{n}")

        threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.ledger.verify(), 100)

    def test_reopening_continues_the_chain(self):
        a = self.ledger.append("agent.born", {"name": "a"}, agent="a1")
        self.ledger.close()
        self.ledger = Ledger(self.path)
        b = self.ledger.append("agent.died", {"why": "credits"}, agent="a1")
        self.assertEqual(b.previous_hash, a.digest)
        self.assertEqual(self.ledger.verify(), 2)

    def test_atomic_batch_is_invisible_to_other_connections_until_every_row_commits(self):
        rows = [{"kind": "book.fill", "payload": {"q": str(n)}, "id": f"fill-{n}"} for n in range(3)]
        original = self.ledger._append_one
        reader = sqlite3.connect(str(self.path), isolation_level=None)
        observed = []

        def observe_during_transaction(**row):
            entry = original(**row)
            observed.append(reader.execute("SELECT COUNT(*) FROM ledger").fetchone()[0])
            return entry

        try:
            with patch.object(self.ledger, "_append_one", side_effect=observe_during_transaction):
                entries = self.ledger.append_many(rows)
            self.assertEqual(observed, [0, 0, 0])
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM ledger").fetchone()[0], 3)
            self.assertEqual([entry.seq for entry in entries], [1, 2, 3])
            self.assertEqual(self.ledger.append_many(rows), entries)
            self.assertEqual(self.ledger.verify(), 3)
        finally:
            reader.close()

    def test_a_later_conflict_or_invalid_payload_rolls_back_the_whole_new_batch(self):
        self.ledger.append("book.fill", {"q": "original"}, id="existing")
        for bad, error in (({"kind": "book.fill", "payload": {"q": "changed"}, "id": "existing"}, LedgerConflict),
                           ({"kind": "book.fill", "payload": {"oversized": "x" * 200_001}}, LedgerError),
                           ({"kind": "unknown", "payload": {}}, LedgerError)):
            with self.subTest(error=error.__name__, kind=bad["kind"]):
                with self.assertRaises(error):
                    self.ledger.append_many([{"kind": "book.fill", "payload": {"q": "new"}, "id": "new"}, bad])
                self.assertIsNone(self.ledger.get("new"))
                self.assertEqual(self.ledger.verify(), 1)

    def test_an_interrupt_inside_a_batch_rolls_back_and_the_connection_remains_usable(self):
        original = self.ledger._append_one

        def interrupted(**row):
            original(**row)
            raise KeyboardInterrupt()

        with patch.object(self.ledger, "_append_one", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.ledger.append_many([{"kind": "book.fill", "payload": {}, "id": "interrupted"}])
        self.assertIsNone(self.ledger.get("interrupted"))
        self.ledger.append("book.fill", {}, id="after")
        self.assertEqual(self.ledger.verify(), 1)


if __name__ == "__main__":
    unittest.main()
