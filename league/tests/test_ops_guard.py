"""Read-only SQLite for the House's jobs: nothing writes, an idle WAL file grows no -wal/-shm, cursors close."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.ops import guard


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "x.sqlite"
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE t (id INTEGER, v TEXT)")
        db.executemany("INSERT INTO t VALUES (?, ?)", [(i, f"v{i}") for i in range(1200)])
        db.commit()
        db.close()
        for suffix in ("-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)

    def test_an_idle_wal_database_is_read_immutable_and_grows_no_side_files(self):
        self.assertTrue(guard.idle_wal(self.path))
        self.assertIn("immutable=1", guard.ro_uri(self.path))
        self.assertEqual(guard.read(self.path, lambda db: guard.ids(db, "SELECT count(*) FROM t"))[0], 1200)
        self.assertFalse(os.path.exists(str(self.path) + "-wal"))
        self.assertFalse(os.path.exists(str(self.path) + "-shm"))

    def test_a_read_only_connection_refuses_a_write(self):
        db = guard.connect_ro(self.path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("INSERT INTO t VALUES (1, 'x')")
        finally:
            db.close()

    def test_a_missing_database_is_an_error_not_a_new_file(self):
        with self.assertRaises(sqlite3.OperationalError):
            guard.connect_ro(Path(self.tmp.name) / "absent.sqlite")
        self.assertFalse((Path(self.tmp.name) / "absent.sqlite").exists())

    def test_batched_reads_cover_every_key_in_bounded_batches(self):
        keys = list(range(0, 1200, 2))
        rows = guard.read(self.path, lambda db: guard.batched(db, "SELECT id FROM t WHERE id IN ({marks}) ORDER BY id", keys, size=100))
        self.assertEqual([r["id"] for r in rows], keys)

    def test_the_process_guard_refuses_writable_opens_and_restores_the_real_connect(self):
        real = sqlite3.connect
        with guard.readonly():
            with self.assertRaises(PermissionError):
                sqlite3.connect(str(self.path))
            with self.assertRaises(PermissionError):
                sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True)
            db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
            self.assertEqual(db.execute("SELECT count(*) FROM t").fetchone()[0], 1200)
            db.close()
            sqlite3.connect(":memory:").close()
            with guard.readonly():  # nests
                pass
            with self.assertRaises(PermissionError):
                sqlite3.connect(str(self.path))
        self.assertIs(sqlite3.connect, real)
        self.assertFalse(os.path.exists(str(self.path) + "-wal"))


if __name__ == "__main__":
    unittest.main()
