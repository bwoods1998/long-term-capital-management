import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from ltcm import events
from ltcm.events import EventConflict, EventError, EventLog, ChainBroken


class EventLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.sqlite"
        self.clock = [1_789_000_000.5]
        self.log = EventLog(self.path, clock=lambda: self.clock[0])

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def test_append_and_read_chain(self):
        first = self.log.append("desk:alpha", "desk.thought", {"session_id": "s1", "text": "hello"}, id="a")
        second = self.log.append("desk:alpha", "desk.memo", {"session_id": "s1", "title": "t", "text": "m"}, id="b")
        other = self.log.append("risk", "risk.decision", {"intent_id": "x", "desk_id": "alpha", "approved": True, "reasons": []})
        self.assertEqual(first.previous_hash, events.GENESIS)
        self.assertEqual(second.previous_hash, first.digest)
        self.assertEqual(other.previous_hash, events.GENESIS)
        self.assertEqual(first.at, "2026-09-10T00:26:40.500Z")
        self.assertTrue(first.public)
        rows = self.log.read(stream="desk:alpha")
        self.assertEqual([r.id for r in rows], ["a", "b"])
        self.assertEqual(self.log.count(), 3)
        self.assertEqual(self.log.streams(), ["desk:alpha", "risk"])
        self.assertEqual(self.log.verify(), 3)

    def test_idempotent_ids(self):
        payload = {"session_id": "s1", "text": "same"}
        first = self.log.append("desk:a", "desk.thought", payload, id="dup")
        again = self.log.append("desk:a", "desk.thought", payload, id="dup")
        self.assertEqual(first.digest, again.digest)
        self.assertEqual(self.log.count(), 1)
        with self.assertRaises(EventConflict):
            self.log.append("desk:a", "desk.thought", {"session_id": "s1", "text": "different"}, id="dup")

    def test_default_publicity_and_private_keys(self):
        intent = self.log.append("desk:a", "desk.intent", {"intent_id": "i", "_prompt": "secret", "nested": {"_key": 1, "ok": 2}})
        self.assertFalse(intent.public)
        self.assertEqual(intent.to_public()["payload"], {"intent_id": "i", "nested": {"ok": 2}})
        request = self.log.append("ops", "provider.request", {"request_id": "r"})
        self.assertFalse(request.public)
        self.assertEqual(self.log.read(stream="ops", public_only=True), [])
        forced = self.log.append("desk:a", "desk.thought", {"text": "x"}, public=False)
        self.assertFalse(forced.public)

    def test_a_live_order_review_is_public(self):
        self.assertEqual(events.KINDS["risk.review"], "public")
        review = self.log.append(
            "risk",
            "risk.review",
            {
                "intent_id": "i",
                "desk_id": "rosenfeld",
                "verdict": "block",
                "reason": "The rationale argues to sell.",
                "model": "zai-org/GLM-5.3",
            },
        )
        self.assertTrue(review.public)
        self.assertEqual(review.to_public()["payload"]["verdict"], "block")

    def test_validation(self):
        with self.assertRaises(EventError):
            self.log.append("bogus", "desk.thought", {})
        with self.assertRaises(EventError):
            self.log.append("desk:", "desk.thought", {})
        with self.assertRaises(EventError):
            self.log.append("desk:a", "not.a.kind", {})
        with self.assertRaises(EventError):
            self.log.append("desk:a", "desk.thought", ["list"])  # type: ignore[arg-type]
        with self.assertRaises(EventError):
            self.log.append("desk:a", "desk.thought", {"x": float("nan")})

    def test_immutability_triggers(self):
        self.log.append("desk:a", "desk.thought", {"text": "x"}, id="a")
        db = sqlite3.connect(str(self.path))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE events SET payload = '{}' WHERE id = 'a'")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("DELETE FROM events WHERE id = 'a'")
        db.close()

    def test_verify_detects_tampering(self):
        self.log.append("desk:a", "desk.thought", {"text": "x"}, id="a")
        self.log.append("desk:a", "desk.thought", {"text": "y"}, id="b")
        db = sqlite3.connect(str(self.path))
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET payload = '{\"text\":\"z\"}' WHERE id = 'a'")
        db.commit()
        db.close()
        with self.assertRaises(ChainBroken):
            self.log.verify()

    def test_concurrent_appends_keep_one_chain(self):
        def worker(n):
            for i in range(25):
                self.log.append("desk:a", "desk.thought", {"text": f"{n}-{i}"}, id=f"{n}-{i}")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.log.count("desk:a"), 100)
        self.assertEqual(self.log.verify(), 100)

    def test_read_filters_and_last(self):
        for i in range(5):
            self.log.append("desk:a", "desk.thought", {"text": str(i)}, id=f"t{i}")
        self.log.append("desk:a", "desk.memo", {"title": "m", "text": "x"}, id="m")
        after = self.log.read(stream="desk:a", after=2, limit=2)
        self.assertEqual([e.id for e in after], ["t2", "t3"])
        self.assertEqual(self.log.last("desk:a").id, "m")
        self.assertEqual(self.log.last("desk:a", "desk.thought").id, "t4")
        self.assertEqual(len(self.log.read(kind="desk.memo")), 1)
        self.assertEqual(self.log.latest_seq(), 6)
        self.assertEqual(len(list(self.log.iter_all())), 6)

    def test_now_iso_format(self):
        self.assertEqual(events.now_iso(lambda: 0), "1970-01-01T00:00:00.000Z")
        self.assertEqual(events.now_iso(lambda: 1.9996), "1970-01-01T00:00:01.999Z")



class NewestReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(Path(self.tmp.name) / "events.sqlite", clock=lambda: 1_789_000_000.0)

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def test_newest_returns_the_last_n_in_sequence_order(self):
        for n in range(6):
            self.log.append("desk:a", "desk.thought", {"session_id": "s", "text": str(n)}, id=f"t{n}")
        oldest = [e.payload["text"] for e in self.log.read(kind="desk.thought", limit=4)]
        newest = [e.payload["text"] for e in self.log.read(kind="desk.thought", limit=4, newest=True)]
        self.assertEqual(oldest, ["0", "1", "2", "3"])
        self.assertEqual(newest, ["2", "3", "4", "5"], "the recent tape, still oldest first")
        self.assertEqual(
            [e.payload["text"] for e in self.log.read(kind="desk.thought", limit=100, newest=True)],
            ["0", "1", "2", "3", "4", "5"],
        )


if __name__ == "__main__":
    unittest.main()


class FoldCacheTests(unittest.TestCase):
    """leap: throughput -- identical fold reads share one answer briefly; cursor reads never do."""

    def test_a_fold_read_is_cached_briefly_and_a_cursor_read_is_not(self):
        import tempfile
        from pathlib import Path
        from ltcm import events as events_module
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp) / "e.sqlite")
            log.append("desk:a", "desk.thought", {"session_id": "s", "text": "one"})
            first = log.read(kind="desk.thought", limit=5000, newest=True)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000, newest=True)), 1, "within the window the fold answer is shared")
            log.append("desk:b", "desk.memo", {"session_id": "s", "title": "t", "text": "m"})
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000, newest=True)), 1, "another kind's append leaves the fold")
            log.append("desk:a", "desk.thought", {"session_id": "s", "text": "two"})
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000, newest=True)), 2, "an append of the kind is seen at once")
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000)), 2, "an oldest-first read is never cached")
            self.assertEqual(len(log.read(kind="desk.thought", after=0, limit=10)), 2, "a small read is never cached")
            self.assertEqual(len(log.read(kind="desk.thought", after=1, limit=5000, newest=True)), 1, "a cursor read is never cached")
            log.forget_folds()
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000, newest=True)), 2)
            self.assertEqual(len(log.read(stream="desk:a", kind="desk.thought", limit=5000, newest=True)), 2)
            log.append("desk:c", "desk.thought", {"session_id": "s", "text": "three"})
            self.assertEqual(len(log.read(stream="desk:a", kind="desk.thought", limit=5000, newest=True)), 2, "another stream's append leaves a stream fold")
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000, newest=True)), 3, "but refreshes the kind-wide fold")
            fresh = log.read(kind="desk.thought", limit=5000, newest=True)
            fresh.append(None)
            self.assertEqual(len(log.read(kind="desk.thought", limit=5000, newest=True)), 3, "a caller's edits never reach the cache")
            log.close() if hasattr(log, "close") else None
