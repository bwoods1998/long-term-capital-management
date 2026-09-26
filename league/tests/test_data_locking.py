"""The account/session and cross-host image/nightly locks, without a vendor connection."""

import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
sys.path.insert(0, str(DATA))
import locking
import images


class Locks(unittest.TestCase):
    def test_session_lock_refuses_a_second_owner_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.lock"
            with locking.process_lock(path):
                with self.assertRaises(RuntimeError):
                    with locking.process_lock(path):
                        self.fail("a second ThetaData client was allowed")
            with locking.process_lock(path):
                pass

    def test_remote_lease_is_exclusive_and_cannot_be_released_by_another_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            try:
                self.assertEqual(locking.lease_command(root, "acquire", "first"), 0)
                self.assertEqual(locking.lease_command(root, "acquire", "second"), 1)
                self.assertEqual(locking.lease_command(root, "release", "second"), 1)
                self.assertEqual(locking.lease_command(root, "renew", "first"), 0)
            finally:
                locking.lease_command(root, "release", "first")
            self.assertEqual(locking.lease_command(root, "acquire", "second"), 0)
            self.assertEqual(locking.lease_command(root, "release", "second"), 0)


class ImageCompleteness(unittest.TestCase):
    def test_a_checkpoint_cannot_succeed_after_its_lease_is_lost(self):
        held = [True]
        calls = []
        def check():
            if not held[0]:
                raise RuntimeError("lost lease")
        def checkpoint(*args, **kwargs):
            calls.append(args[0])
            held[0] = False
            return {"checkpoint_id": "sbcp_unowned"}
        with self.assertRaisesRegex(RuntimeError, "lost lease"):
            images.checkpoint_with_retry(SimpleNamespace(checkpoint=checkpoint), "sb_gate", name="test",
                                         ttl_seconds=86400, check_lease=check, sleep=lambda _: None)
        self.assertEqual(calls, ["sb_gate"])

    def test_retries_and_invalidated_tasks_do_not_inflate_the_image_counts(self):
        rows = [{"type": "task", "stage": 3, "task": "one", "status": "ok"},
                {"type": "task", "stage": 3, "task": "one", "status": "ok"},
                {"type": "task", "stage": 3, "task": "two", "status": "ok"},
                {"type": "task", "stage": 3, "task": "two", "status": "invalidated"}]
        self.assertEqual(images.stage_done(rows, (3,), {"3": 2}), {"3": {"done": 1, "planned": 2}})
