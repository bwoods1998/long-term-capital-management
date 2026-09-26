"""A failed durable reservation cannot remain in an open transaction for a later caller."""
import sqlite3
import tempfile
import unittest

from league.swarm.store import SwarmStore


class AtomicCommit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SwarmStore(self.temp.name)
        self.reader = SwarmStore(self.temp.name)
        self.addCleanup(self.reader.close)
        self.addCleanup(self.store.close)

    def test_denied_commit_rolls_back_before_another_caller_can_use_the_connection(self):
        def deny_commit(action, first, second, database, trigger):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT" else sqlite3.SQLITE_OK
        self.store._db.set_authorizer(deny_commit)
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store.atomic():
                self.store.put("synthetic-reservation", {"usd": 1})
        self.assertFalse(self.store._db.in_transaction)
        self.assertIsNone(self.reader.get("synthetic-reservation"))
        self.store._db.set_authorizer(None)
        with self.store.atomic():
            self.store.put("subsequent-reservation", {"usd": 2})
        self.assertEqual(self.reader.get("subsequent-reservation"), {"usd": 2})
        self.assertIsNone(self.reader.get("synthetic-reservation"))

    def test_nested_atomic_never_commits_or_rolls_back_its_outer_owners_transaction(self):
        with self.store.atomic():
            self.store.put("outer", 1)
            with self.store.atomic():
                self.store.put("inner", 2)
            self.assertTrue(self.store._db.in_transaction)
            self.assertIsNone(self.reader.get("inner"))
            with self.assertRaises(RuntimeError):
                with self.store.atomic():
                    raise RuntimeError("caller handles a nested failure")
            self.assertTrue(self.store._db.in_transaction)
        self.assertEqual(self.reader.get("outer"), 1)
        self.assertEqual(self.reader.get("inner"), 2)
