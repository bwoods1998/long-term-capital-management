"""scripts/evl_migrate.py (release R1, WP1): the desktop's event store copied onto the House box once, in chunks with
their SHA-256 read back, checked file by file and table by table on the box, put in place by one rename, and refused
when the box's target is not empty, when a document is missing or corrupt, or while the desktop's timers run. The box
is a scratch directory here; the box's half (the snippets) runs with this Python, as it does on the box."""

from __future__ import annotations

import datetime as dt
import gzip
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from league.events import store as S

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("evl_migrate_test", ROOT / "scripts" / "evl_migrate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = load()


class FakeSail:
    """The Sail API's upload and exec, on a scratch 'box': `corrupt` names chunks whose first upload arrives damaged."""

    def __init__(self, corrupt=()):
        self.corrupt = set(corrupt)
        self.uploads = []
        self.execs = []

    def upload(self, box, path, content, *, mode=0o600, timeout=300.0):
        name = Path(path).name
        self.uploads.append(name)
        if name in self.corrupt:
            self.corrupt.discard(name)
            content = bytes([content[0] ^ 0xFF]) + content[1:]
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {}

    def exec(self, box, command, *, timeout=600, on_output=None):
        self.execs.append(command[2][:40] if len(command) > 2 else command)
        done = subprocess.run(list(command), capture_output=True, text=True, timeout=timeout)
        return type("Result", (), {"stdout": done.stdout, "stderr": done.stderr, "return_code": done.returncode})()


class Migrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.source = base / "desktop" / "evl"
        self.box = base / "box"
        (self.box / "state").mkdir(parents=True)
        self.work = base / "work"
        self.work.mkdir()
        now = dt.datetime(2026, 10, 21, 1, 0, tzinfo=dt.timezone.utc)
        with S.Store(self.source) as st:
            self.docs = [st.put_document((f"document {i} " * 200).encode(), "TEXT", now=now) for i in range(12)]
            st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, received_at, "
                          "source, status) VALUES('0000000001-26-000001', '8-K', '0000000001', 'Co', '[\"2.02\"]', ?, ?, ?, "
                          "'current', 'fetched')", ("2026-10-20T21:00:00Z", "2026-10-20T21:10:00Z", "2026-10-20T21:01:00Z"))
            st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, status, score, answered_at, usd) VALUES("
                          "'8k:0000000001-26-000001', 'p', 'm', 'ok', 3, '2026-10-20T21:12:00Z', 0.002)")
            rid = st.start_receipt("record", now=now)
            st.finish_receipt(rid, "ok", {}, now=now)
        (self.source / "record.log").write_text("not copied\n")
        (self.source / "tmp").mkdir()

    def migrate(self, api, **kw):
        kw.setdefault("timers", lambda: [])
        return M.migrate(api, "sb_test", self.source, remote_root=str(self.box), python=sys.executable,
                         chunk_mib=kw.pop("chunk_mib", 0.001), work=self.work, say=lambda text: None, **kw)

    def target(self):
        return self.box / "state" / "events"

    def test_the_store_lands_whole_by_one_rename_and_the_uploads_go(self):
        api = FakeSail()
        out = self.migrate(api)
        self.assertTrue(out["ok"])
        self.assertGreater(out["chunks"], 1)                              # 1 KiB chunks: several
        target = self.target()
        self.assertTrue((target / "events.sqlite").is_file())
        self.assertFalse((target / "record.log").exists())               # only the store and its documents
        self.assertFalse((target / "MANIFEST.json").exists())
        self.assertTrue((target / "migrated.json").is_file())             # the manifest, kept as the record
        with S.Store(target) as st:                                       # the House lane opens it as its own
            self.assertEqual(st.db.execute("SELECT count(*) FROM verdicts").fetchone()[0], 1)
            self.assertEqual(st.db.execute("SELECT count(*) FROM receipts WHERE job='record'").fetchone()[0], 1)
            for sha in self.docs:
                self.assertEqual(st.get_document(sha), [(f"document {i} " * 200).encode() for i in range(12)]
                                 [self.docs.index(sha)])
        self.assertEqual(out["counts"]["documents"], 12)
        self.assertFalse(any(p.name.startswith("evl-migrate-") for p in (self.box / ".upload").iterdir()))
        self.assertFalse(any(p.name.startswith(".events-incoming-") for p in (self.box / "state").iterdir()))
        self.assertEqual(list(self.work.iterdir()), [])                   # the local scratch is cleaned too

    def test_a_second_migration_is_refused_before_anything_is_sent(self):
        self.migrate(FakeSail())
        again = FakeSail()
        with self.assertRaises(M.Refused) as refused:
            self.migrate(again)
        self.assertIn("not empty", refused.exception.why)
        self.assertEqual(again.uploads, [])

    def test_an_empty_target_is_taken(self):
        self.target().mkdir()
        self.assertTrue(self.migrate(FakeSail())["ok"])

    def test_a_chunk_damaged_on_the_way_is_sent_again(self):
        api = FakeSail(corrupt={"part-00001"})
        out = self.migrate(api)
        self.assertTrue(out["ok"])
        self.assertEqual(api.uploads.count("part-00001"), 2)
        self.assertEqual(api.uploads.count("part-00000"), 1)

    def test_a_missing_or_corrupt_document_refuses_the_copy(self):
        db = sqlite3.connect(str(self.source / "events.sqlite"))
        try:
            path = db.execute("SELECT path FROM documents LIMIT 1").fetchone()[0]
        finally:
            db.close()
        doc = self.source / path
        doc.write_bytes(gzip.compress(b"not what its name says"))
        with self.assertRaises(M.Refused) as refused:
            self.migrate(FakeSail())
        self.assertIn("does not match its digest", refused.exception.why)
        doc.unlink()
        with self.assertRaises(M.Refused) as refused:
            self.migrate(FakeSail())
        self.assertIn("missing", refused.exception.why)
        self.assertFalse(self.target().exists())

    def test_refused_while_the_desktop_lane_runs(self):
        api = FakeSail()
        with self.assertRaises(M.Refused) as refused:
            self.migrate(api, timers=lambda: ["ltcm-evl-record.timer"])
        self.assertIn("systemctl --user stop", refused.exception.why)
        self.assertEqual(api.execs, [])
        self.assertTrue(self.migrate(FakeSail(), timers=lambda: ["ltcm-evl-record.timer"], allow_running=True)["ok"])

    def test_the_box_refuses_a_bundle_that_does_not_match(self):
        """The box's half checks the joined bundle against the sha the desktop sent, and leaves nothing in place."""
        updir = self.box / ".upload" / "evl-migrate-x"
        updir.mkdir(parents=True)
        (updir / "part-00000").write_bytes(b"garbage")
        ask = {"dir": str(updir), "target": str(self.target()), "staging": str(self.box / "state" / ".events-incoming-x"),
               "parts": ["part-00000"], "sha256": "0" * 64}
        done = subprocess.run([sys.executable, "-c", M.FINISH_SNIPPET, json.dumps(ask)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("sha256", json.loads(done.stdout.strip().splitlines()[-1])["why"])
        self.assertFalse(self.target().exists())

    def test_the_dry_run_sends_nothing(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "evl_migrate.py"), "--source", str(self.source),
                              "--dry-run", "--workdir", str(self.work), "--chunk-mib", "0.01"],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        summary = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertTrue(summary["ok"] and summary["dry_run"])
        self.assertEqual(summary["counts"]["verdicts"], 1)
        self.assertEqual(list(self.work.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
