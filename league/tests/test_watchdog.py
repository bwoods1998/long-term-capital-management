import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

from league import watchdog as wd
from league.ledger import Ledger
from league.tests.fakes import Clock
from league.watchdog import DeployBusy, Health, HouseHealth, ReleaseError, Releases, RestartScript, SubprocessCanary, Watchdog, read_health

REAL_LEDGER = Path(wd.__file__).resolve().parent / "ledger.py"


def write_health(root, clock, *, living=10, seq=1, frozen=None, age=0, **extra):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    health = {
        "at": wd.iso(clock() - age), "living": living, "dead": 0, "ledger_seq": seq, "real_money": False,
        "books": {"alpaca-paper": {"frozen": frozen, "open_orders": 0}, "kalshi-shadow": {"frozen": None, "open_orders": 2}},
        **extra,
    }
    (root / "health.json").write_text(json.dumps(health), encoding="utf-8")


def make_tree(path, marker="v1"):
    """A code tree as the uploader would hand it over, with everything a release must leave behind."""
    path = Path(path)
    (path / "league" / "__pycache__").mkdir(parents=True)
    (path / "ltcm").mkdir()
    (path / "scripts").mkdir()
    (path / ".data" / "league").mkdir(parents=True)
    (path / "league" / "__init__.py").write_text("", encoding="utf-8")
    (path / "league" / "__main__.py").write_text(f"print({marker!r})\n", encoding="utf-8")
    (path / "league" / "__pycache__" / "__main__.cpython-314.pyc").write_bytes(b"\0bytecode")
    (path / "ltcm" / "broker.py").write_text("# the contracts\n", encoding="utf-8")
    (path / "scripts" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(path / "scripts" / "run.sh", 0o755)
    (path / ".env").write_text("GATEWAY_TOKEN=never-in-a-release\n", encoding="utf-8")
    (path / ".data" / "league" / "ledger.sqlite").write_bytes(b"state")
    (path / "ltcm" / "venue.pem").write_text("a key\n", encoding="utf-8")
    os.symlink("/etc/hostname", path / "ltcm" / "link-out-of-the-tree")
    return path


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.base = self.tmp / "workspace"
        self.clock = Clock()
        self.releases = Releases(self.base, clock=self.clock)
        self.n = 0

    def tearDown(self):
        self.dir.cleanup()

    def tree(self, marker):
        self.n += 1
        return make_tree(self.tmp / f"src-{self.n}", marker)

    def staged(self, release_id, marker=None):
        self.clock.advance(1)
        return self.releases.stage(self.tree(marker or release_id), release_id)


# ------------------------------------------------------------------------------------- health
class ReadHealthTest(Case):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "state"
        self.root.mkdir()

    def ledger(self):
        ledger = Ledger(self.root / "ledger.sqlite", clock=self.clock)
        self.addCleanup(ledger.close)
        return ledger

    def read(self, **kw):
        return read_health(self.root, now=self.clock(), **kw)

    def test_a_fresh_health_file_is_healthy(self):
        write_health(self.root, self.clock, living=7, seq=42, age=20)
        health = self.read()
        self.assertTrue(health.ok, health.reasons)
        self.assertEqual(health.reasons, ())
        self.assertEqual((health.detail["living"], health.detail["ledger_seq"], health.detail["age_seconds"]), (7, 42, 20.0))
        self.assertEqual(health.detail["books"], {"alpaca-paper": None, "kalshi-shadow": None})
        json.dumps(health.to_dict())  # it goes into deploys.jsonl as it is

    def test_missing_unreadable_and_stale(self):
        missing = self.read()
        self.assertFalse(missing.ok)
        self.assertIn("no health.json", missing.reasons[0])
        (self.root / "health.json").write_text("{half a fi", encoding="utf-8")
        self.assertIn("cannot be read", self.read().reasons[0])
        (self.root / "health.json").write_text(json.dumps({"living": 3}), encoding="utf-8")
        self.assertIn("no readable time", self.read().reasons[0])
        write_health(self.root, self.clock, age=301)
        stale = self.read()
        self.assertFalse(stale.ok)
        self.assertIn("301s old", stale.reasons[0])
        self.assertTrue(self.read(max_age_seconds=600).ok)
        write_health(self.root, self.clock, age=-4000)
        self.assertIn("in the future", self.read().reasons[0])

    def test_a_house_stopped_on_purpose_is_not_stale(self):
        write_health(self.root, self.clock, age=5000)
        (self.root / "STOP").write_text("stopped by the operator\n", encoding="utf-8")
        health = self.read()
        self.assertTrue(health.ok, health.reasons)
        self.assertTrue(health.detail["stopped"])

    def test_a_frozen_book(self):
        write_health(self.root, self.clock, frozen="cash differs by 12.5000")
        health = self.read()
        self.assertEqual(health.reasons, ("the alpaca-paper book is frozen: cash differs by 12.5000",))
        self.assertEqual(health.detail["books"]["alpaca-paper"], "cash differs by 12.5000")

    def test_more_than_half_the_agents_gone(self):
        write_health(self.root, self.clock, living=10, seq=1)
        first = self.read()
        write_health(self.root, self.clock, living=5, seq=2)
        self.assertTrue(self.read(previous=first).ok)  # half is not more than half
        write_health(self.root, self.clock, living=4, seq=2)
        gone = self.read(previous=first)
        self.assertFalse(gone.ok)
        self.assertIn("4 agents are alive where there were 10", gone.reasons[0])
        # The baseline is the first reading of the chain, so a slow bleed is still seen.
        write_health(self.root, self.clock, living=6, seq=3)
        second = self.read(previous=first)
        self.assertTrue(second.ok)
        write_health(self.root, self.clock, living=4, seq=4)
        self.assertFalse(self.read(previous=second).ok)
        self.assertEqual(self.read(previous=second).detail["living_baseline"], 10)

    def test_a_ledger_seq_that_does_not_advance(self):
        write_health(self.root, self.clock, seq=50)
        first = self.read()
        self.clock.advance(100)
        write_health(self.root, self.clock, seq=50)
        second = self.read(previous=first)
        self.assertTrue(second.ok, second.reasons)  # a quiet hundred seconds is no stall
        strict = self.read(previous=first, stall_seconds=0)  # between two reads, as a canary asks it
        self.assertFalse(strict.ok)
        self.assertIn("has not advanced from 50", strict.reasons[0])
        self.clock.advance(350)
        write_health(self.root, self.clock, seq=50)
        third = self.read(previous=second)  # the stall clock carries down the chain: 450s now
        self.assertFalse(third.ok)
        self.assertIn("has not advanced from 50 in 450s", third.reasons[0])
        write_health(self.root, self.clock, seq=51)
        self.assertTrue(self.read(previous=third).ok)
        write_health(self.root, self.clock, seq=12)
        self.assertIn("went backwards, from 50 to 12", self.read(previous=first).reasons[0])

    def test_error_alerts_since_a_seq(self):
        ledger = self.ledger()
        ledger.append("ops.started", {"books": []})
        ledger.append("ops.alert", {"level": "error", "text": "an old failure, before the deploy"})
        since = ledger.head()[0]
        ledger.append("ops.alert", {"level": "warning", "text": "kalshi-shadow: could not poll"})
        write_health(self.root, self.clock, seq=ledger.head()[0])
        quiet = self.read(since_seq=since)
        self.assertTrue(quiet.ok, quiet.reasons)
        self.assertEqual((quiet.detail["error_alerts"], quiet.detail["started_since"], quiet.detail["ledger_head"]), (0, 0, 3))
        self.assertTrue(self.read().ok)  # not asked, not counted
        ledger.append("ops.started", {"books": []})
        ledger.append("ops.alert", {"level": "error", "text": "tick failed: KeyError: 'settled'"})
        ledger.append("ops.alert", {"level": "error", "text": "tick failed again"})
        loud = self.read(since_seq=since)
        self.assertFalse(loud.ok)
        self.assertIn("2 error alert(s) since seq 2", loud.reasons[0])
        self.assertIn("tick failed: KeyError: 'settled'", loud.reasons[0])
        self.assertEqual(loud.detail["started_since"], 1)
        self.assertIn("3 error alert(s) since seq 0", self.read(since_seq=0).reasons[0])

    def test_the_hash_chain_only_when_asked(self):
        ledger = self.ledger()
        for n in range(5):
            ledger.append("ops.alert", {"level": "info", "text": f"row {n}"})
        write_health(self.root, self.clock, seq=5)
        checked = self.read(verify=True)
        self.assertTrue(checked.ok, checked.reasons)
        self.assertEqual(checked.detail["ledger_rows_verified"], 5)
        self.assertNotIn("ledger_rows_verified", self.read().detail)
        ledger.close()
        raw = sqlite3.connect(self.root / "ledger.sqlite")
        raw.execute("DROP TRIGGER ledger_no_update")
        raw.execute("UPDATE ledger SET payload = ? WHERE seq = 3", (json.dumps({"level": "info", "text": "edited"}),))
        raw.commit()
        raw.close()
        self.assertTrue(self.read().ok)  # O(n), so only when asked
        broken = self.read(verify=True)
        self.assertFalse(broken.ok)
        self.assertIn("hash chain does not verify: seq 3: digest mismatch", broken.reasons[0])

    def test_no_ledger_is_fine_unless_it_was_to_be_verified(self):
        write_health(self.root, self.clock)
        self.assertTrue(self.read(since_seq=0).ok)
        self.assertEqual(self.read(verify=True).reasons, ("there is no ledger to verify",))
        self.assertIsNone(wd.ledger_head(self.root))

    def test_it_never_writes_the_ledger(self):
        ledger = self.ledger()
        ledger.append("ops.alert", {"level": "error", "text": "x"})
        ledger.close()
        path = self.root / "ledger.sqlite"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        write_health(self.root, self.clock)
        self.assertFalse(self.read(since_seq=0, verify=True).ok)
        self.assertEqual(wd.ledger_head(self.root), 1)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        with wd._ledger_ro(path) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("INSERT INTO ledger (id, kind, agent, at, public, payload, previous_hash, digest) VALUES ('a','b','c','d',1,'{}','e','f')")

    def test_it_reads_beside_a_house_that_is_writing(self):
        ledger = self.ledger()  # open, in WAL mode, as the running House holds it
        ledger.append("ops.started", {"books": []})
        ledger.append("ops.alert", {"level": "error", "text": "seen through the WAL"})
        write_health(self.root, self.clock, seq=2)
        health = self.read(since_seq=1, verify=True)
        self.assertEqual(health.detail["ledger_head"], 2)
        self.assertIn("seen through the WAL", health.reasons[0])
        ledger.append("ops.alert", {"level": "info", "text": "and the House can still write"})


class HouseHealthTest(Case):
    def setUp(self):
        super().setUp()
        self.root = self.base / "state"
        self.root.mkdir(parents=True)
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.ledger.append("ops.started", {"books": []})
        self.ledger.append("ops.alert", {"level": "error", "text": "from the old release, long ago"})

    def beat(self, living=10):
        write_health(self.root, self.clock, living=living, seq=self.ledger.head()[0])

    def test_the_first_reading_is_the_baseline(self):
        reader = HouseHealth(self.root, clock=self.clock)
        self.beat()
        before = reader()
        self.assertTrue(before.ok, before.reasons)  # the old error is before the baseline
        self.assertEqual(reader.since_seq, 2)
        self.clock.advance(30)
        self.ledger.append("ops.started", {"books": []})
        self.beat()
        self.assertTrue(reader().ok)
        self.clock.advance(30)
        self.ledger.append("ops.alert", {"level": "error", "text": "alpaca-paper does not reconcile: cash differs by 3.0000"})
        self.beat()
        bad = reader()
        self.assertFalse(bad.ok)
        self.assertIn("does not reconcile", bad.reasons[0])
        self.clock.advance(30)
        self.beat(living=4)
        self.assertTrue(any("more than half" in r for r in reader().reasons))

    def test_a_house_that_never_restarted_has_proved_nothing(self):
        reader = HouseHealth(self.root, clock=self.clock, restart_within=300)
        self.beat()
        self.assertTrue(reader().ok)
        for _ in range(9):
            self.clock.advance(30)
            self.ledger.append("ops.alert", {"level": "info", "text": "the old process, ticking on"})
            self.beat()
            self.assertTrue(reader().ok)
        self.clock.advance(30)
        self.beat()
        late = reader()
        self.assertFalse(late.ok)
        self.assertIn("has not restarted in the 300s since the promotion", late.reasons[0])
        self.ledger.append("ops.started", {"books": []})
        self.beat()
        self.assertTrue(reader().ok)


# ----------------------------------------------------------------------------------- releases
class ReleasesTest(Case):
    def test_stage_copies_the_code_and_nothing_else(self):
        path = self.releases.stage(self.tree("v1"), "2026-09-19.a1b2c3")
        self.assertEqual(path, self.base / "releases" / "2026-09-19.a1b2c3")
        files = sorted(p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file() or p.is_symlink())
        self.assertEqual(files, [".release.json", "league/__init__.py", "league/__main__.py", "ltcm/broker.py", "scripts/run.sh"])
        self.assertTrue(os.stat(path / "scripts" / "run.sh").st_mode & 0o100)
        manifest = json.loads((path / ".release.json").read_text())
        self.assertEqual((manifest["id"], manifest["files"]), ("2026-09-19.a1b2c3", 4))
        self.assertEqual(manifest["digest"], wd.tree_digest(path)[0])
        self.assertEqual([row["id"] for row in self.releases.list()], ["2026-09-19.a1b2c3"])
        self.assertIsNone(self.releases.current())  # staging promotes nothing
        self.assertEqual(list((self.base / "releases").glob(".staging-*")), [])

    def test_the_same_id_with_the_same_content_is_fine_and_with_other_content_is_refused(self):
        source = self.tree("v1")
        first = self.releases.stage(source, "rel-0001")
        stamp = (first / ".release.json").read_text()
        self.clock.advance(60)
        self.assertEqual(self.releases.stage(source, "rel-0001"), first)
        self.assertEqual(self.releases.stage(self.tree("v1"), "rel-0001"), first)  # another copy of the same code
        self.assertEqual((first / ".release.json").read_text(), stamp)
        # Bytecode the running House wrote into its release does not change what the release is.
        (first / "league" / "__pycache__").mkdir()
        (first / "league" / "__pycache__" / "x.pyc").write_bytes(b"\0")
        self.assertEqual(self.releases.stage(source, "rel-0001"), first)
        with self.assertRaises(ReleaseError) as caught:
            self.releases.stage(self.tree("v2"), "rel-0001")
        self.assertIn("different content", str(caught.exception))
        self.assertIn("'v1'", (first / "league" / "__main__.py").read_text())  # and the release stands as it was
        (source / "scripts" / "run.sh").chmod(0o644)
        with self.assertRaises(ReleaseError):
            self.releases.stage(source, "rel-0001")  # a mode is content too

    def test_what_is_not_a_release(self):
        source = self.tree("v1")
        for bad in ("abc", "", "a" * 65, "../../etc", "has space", "semi;colon", "....", ".hidden", "-rf-", None, 1234):
            with self.assertRaises(ReleaseError, msg=repr(bad)):
                self.releases.stage(source, bad)
        for good in ("abcd", "v1.2.3", "2026-09-19T21_30_a1b2c3d", "a" * 64):
            self.releases.check_id(good)
        with self.assertRaises(ReleaseError):
            self.releases.stage(self.tmp / "nowhere", "rel-0001")
        (self.tmp / "docs").mkdir()
        with self.assertRaises(ReleaseError):
            self.releases.stage(self.tmp / "docs", "rel-0001")
        make_tree(self.base / "checkout")
        shutil.copytree(self.base / "checkout" / "league", self.base / "league")
        with self.assertRaises(ReleaseError) as caught:
            self.releases.stage(self.base, "rel-0001")  # the base itself: it would contain its own releases
        self.assertIn("contains the releases directory", str(caught.exception))
        self.assertEqual(self.releases.list(), [])

    def test_promote_and_rollback(self):
        for release_id in ("rel-0001", "rel-0002", "rel-0003"):
            self.staged(release_id)
        self.assertIsNone(self.releases.current())
        with self.assertRaises(ReleaseError):
            self.releases.rollback()
        with self.assertRaises(ReleaseError):
            self.releases.promote("rel-9999")
        self.releases.promote("rel-0001")
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0001", None))
        self.assertEqual(os.readlink(self.base / "current"), "releases/rel-0001")  # relative: the base can move
        self.assertIn("'rel-0001'", (self.base / "current" / "league" / "__main__.py").read_text())
        self.releases.promote("rel-0002")
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0002", "rel-0001"))
        self.releases.promote("rel-0002")  # again is nothing: previous is not lost to it
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0002", "rel-0001"))
        self.releases.promote("rel-0003")
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0003", "rel-0002"))
        self.assertEqual(self.releases.rollback(), "rel-0002")
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0002", None))
        self.assertTrue((self.base / "releases" / "rel-0003").is_dir())  # kept for the post-mortem
        with self.assertRaises(ReleaseError):
            self.releases.rollback()  # the release rolled back from is nothing to roll back TO
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["current", "releases"])  # no temp link left

    def test_a_directory_in_the_way_is_refused_not_replaced(self):
        self.staged("rel-0001")
        (self.base / "current").mkdir()
        with self.assertRaises(ReleaseError):
            self.releases.promote("rel-0001")
        self.assertTrue((self.base / "current").is_dir())

    def test_there_is_no_moment_without_a_valid_current(self):
        ids = ["rel-0001", "rel-0002", "rel-0003"]
        for release_id in ids:
            self.staged(release_id)
        self.releases.promote(ids[0])
        probe = self.base / "current" / "league" / "__main__.py"
        stop, misses, looks = threading.Event(), [], [0]

        def reader():
            while not stop.is_set():
                try:
                    os.stat(probe)
                    looks[0] += 1
                except OSError as exc:
                    misses.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(2)]
        for thread in threads:
            thread.start()
        try:
            for n in range(600):
                self.releases.promote(ids[(n + 1) % 3])
                if n % 3 == 0:
                    self.releases.rollback()
        finally:
            stop.set()
            for thread in threads:
                thread.join()
        self.assertEqual(misses, [])
        self.assertGreater(looks[0], 0)
        self.assertIn(self.releases.current(), ids)
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.endswith(".tmp")], [])

    def test_prune_keeps_the_newest_and_always_current_and_previous(self):
        ids = [f"rel-000{n}" for n in range(7)]
        for release_id in ids:
            self.staged(release_id)
        self.releases.promote("rel-0000")
        self.releases.promote("rel-0001")  # the two OLDEST are current and previous
        stale = self.base / "releases" / ".staging-dead-1-1"
        stale.mkdir()
        os.utime(stale, (self.clock() - 7200, self.clock() - 7200))
        removed = self.releases.prune(keep=2)
        self.assertEqual(sorted(removed), ["rel-0002", "rel-0003", "rel-0004"])
        self.assertEqual(sorted(row["id"] for row in self.releases.list()), ["rel-0000", "rel-0001", "rel-0005", "rel-0006"])
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0001", "rel-0000"))
        self.assertFalse(stale.exists())
        self.assertEqual(self.releases.prune(keep=0), ["rel-0006", "rel-0005"])
        self.assertEqual(self.releases.prune(keep=0), [])
        self.assertTrue((self.base / "current" / "league" / "__main__.py").is_file())

    def test_the_record_is_append_only_private_and_survives_a_torn_line(self):
        self.releases.record({"stage": "start", "release": "rel-0001"})
        self.clock.advance(2.5)
        self.releases.record({"stage": "verdict", "release": "rel-0001", "verdict": "promoted", "path": Path("/x")})
        self.assertEqual(stat.S_IMODE(os.stat(self.base / "deploys.jsonl").st_mode), 0o600)
        with open(self.base / "deploys.jsonl", "a", encoding="utf-8") as handle:
            handle.write('{"stage": "torn')
        rows = self.releases.history()
        self.assertEqual([row["stage"] for row in rows], ["start", "verdict"])
        self.assertEqual(rows[1]["ts"] - rows[0]["ts"], 2.5)
        self.assertEqual(rows[0]["at"], "2026-09-10T00:26:40.000Z")
        self.assertEqual(self.releases.history(limit=1), rows[1:])

    def test_one_deploy_at_a_time(self):
        with self.releases.lock():
            with self.assertRaises(DeployBusy) as caught:
                with Releases(self.base).lock():
                    self.fail("two holders")
            self.assertIn(str(os.getpid()), str(caught.exception))
        with self.releases.lock():
            pass

    def test_a_canary_root_is_fresh_every_time_and_old_ones_go(self):
        roots = []
        for _ in range(5):
            roots.append(self.releases.canary_root("rel-0001"))
            (roots[-1] / "ledger.sqlite").write_bytes(b"x")
            self.clock.advance(1)
        self.assertEqual(len(set(roots)), 5)
        same_second = self.releases.canary_root("rel-0001"), self.releases.canary_root("rel-0001")
        self.assertNotEqual(*same_second)
        for root in same_second:
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(root.parent, self.base / "canary")
        self.assertEqual(len(list((self.base / "canary").iterdir())), 3)
        self.assertTrue(same_second[1].is_dir())


# ----------------------------------------------------------------------------------- watchdog
class World:
    """Everything the watchdog is given: a canary, a restart and a health reader, all scripted."""

    def __init__(self, clock):
        self.clock = clock
        self.canary = Health(True, (), {"ticks": "fine"})
        self.canary_calls = []
        self.restarts = 0
        self.restart_error = None
        self.readings = []  # what the House says, in order; after the script runs out it is healthy
        self.reads = 0
        self.slept = []
        self.lines = []

    def run_canary(self, release_dir, canary_root, ticks):
        self.canary_calls.append((Path(release_dir), Path(canary_root), ticks))
        if isinstance(self.canary, Exception):
            raise self.canary
        return self.canary

    def restart_house(self):
        self.restarts += 1
        if self.restart_error is not None:
            raise self.restart_error
        return {"ran": True}

    def read_house_health(self):
        self.reads += 1
        reading = self.readings.pop(0) if self.readings else Health(True, (), {"living": 10})
        if isinstance(reading, BaseException):
            raise reading
        return reading

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.clock.advance(seconds)


GOOD = Health(True, (), {"living": 10})


def bad(reason):
    return Health(False, (reason,), {"living": 10})


class WatchdogTest(Case):
    def setUp(self):
        super().setUp()
        self.world = World(self.clock)
        self.dog = Watchdog(
            self.releases, run_canary=self.world.run_canary, restart_house=self.world.restart_house,
            read_house_health=self.world.read_house_health, clock=self.clock, sleep=self.world.sleep, log=self.world.lines.append,
        )

    def running(self, release_id="rel-0001"):
        """A box that is already running a release."""
        self.staged(release_id)
        self.releases.promote(release_id)

    def story(self):
        return [row["stage"] for row in self.releases.history()]

    def test_a_healthy_release_is_promoted(self):
        self.running("rel-0001")
        result = self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual((result["verdict"], result["reasons"]), ("promoted", []))
        self.assertEqual((result["current"], result["previous"]), ("rel-0002", "rel-0001"))
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0002", "rel-0001"))
        self.assertEqual(self.world.restarts, 1)
        self.assertEqual(result["readings"], 20)  # 600s, every 30s
        self.assertEqual(self.world.slept, [30] * 20)
        self.assertEqual(self.world.reads, 21)  # and the one before the promotion
        self.assertEqual(self.world.canary_calls[0][0], self.base / "releases" / "rel-0002")
        self.assertEqual(self.world.canary_calls[0][2], 3)
        self.assertEqual(self.story(), ["start", "stage", "canary", "house_before", "promote", "restart"] + ["watch"] * 20 + ["verdict"])
        self.assertEqual(result["stages"], self.releases.history())
        self.assertIn("rel-0002: promoted", self.world.lines)

    def test_a_canary_that_fails_is_refused_and_current_is_untouched(self):
        self.running("rel-0001")
        self.world.canary = Health(False, ("tick 1: it exited 1: RuntimeError: the new code is broken",), {"runs": [{"exit": 1}]})
        result = self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual(result["verdict"], "refused")
        self.assertEqual(result["reasons"], ["canary: tick 1: it exited 1: RuntimeError: the new code is broken"])
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0001", None))
        self.assertEqual((self.world.restarts, self.world.reads, self.world.slept), (0, 0, []))  # the House never noticed
        self.assertTrue((self.base / "releases" / "rel-0002").is_dir())  # staged, for the post-mortem; never current
        self.assertEqual(self.story(), ["start", "stage", "canary", "verdict"])
        canary = self.releases.history()[2]
        self.assertEqual((canary["ok"], canary["detail"]), (False, {"runs": [{"exit": 1}]}))

    def test_a_canary_that_cannot_even_run_is_refused(self):
        self.running("rel-0001")
        for failure in (TimeoutError("the box is wedged"), "not a Health"):
            self.world.canary = failure
            self.n += 1
            result = self.dog.deploy(self.tree(f"v{self.n}"), f"rel-bad{self.n}")
            self.assertEqual(result["verdict"], "refused", failure)
            self.assertEqual(self.releases.current(), "rel-0001")
        self.assertEqual(self.world.restarts, 0)

    def test_a_house_that_goes_bad_after_promotion_is_rolled_back(self):
        self.running("rel-0001")
        self.world.readings = [GOOD, GOOD, GOOD, GOOD, GOOD, bad("the alpaca-paper book is frozen: cash differs by 3.0000")]
        result = self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual(result["verdict"], "rolled_back")
        self.assertEqual(result["reasons"], ["reading 5: the alpaca-paper book is frozen: cash differs by 3.0000"])
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0001", None))
        self.assertEqual(self.world.restarts, 2)  # into the new release, and back out of it
        self.assertEqual(result["readings"], 5)
        self.assertEqual(self.story(), ["start", "stage", "canary", "house_before", "promote", "restart"] + ["watch"] * 5 + ["rollback", "restart", "verdict"])
        rows = self.releases.history()
        rollback, restart, verdict = rows[-3:]
        self.assertEqual((rollback["from"], rollback["to"], restart["after"]), ("rel-0002", "rel-0001", "rollback"))
        self.assertEqual((verdict["verdict"], verdict["current"]), ("rolled_back", "rel-0001"))
        self.assertTrue((self.base / "releases" / "rel-0002").is_dir())

    def test_the_grace_period_is_two_readings_and_no_more(self):
        self.running("rel-0001")
        self.world.readings = [GOOD, bad("stale: the new process is still starting"), bad("stale: the new process is still starting")]
        self.assertEqual(self.dog.deploy(self.tree("v2"), "rel-0002")["verdict"], "promoted")
        grace = [row["grace"] for row in self.releases.history() if row["stage"] == "watch"]
        self.assertEqual(grace, [True, True] + [False] * 18)
        self.world.readings = [GOOD, GOOD, GOOD, bad("health.json is 400s old")]
        result = self.dog.deploy(self.tree("v3"), "rel-0003")
        self.assertEqual((result["verdict"], result["readings"]), ("rolled_back", 3))
        self.assertEqual(self.releases.current(), "rel-0002")

    def test_a_reader_that_fails_is_a_bad_reading(self):
        self.running("rel-0001")
        self.world.readings = [GOOD, GOOD, GOOD, GOOD, OSError("the disk is gone")]
        result = self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual(result["verdict"], "rolled_back")
        self.assertIn("could not be read (OSError: the disk is gone)", result["reasons"][0])

    def test_a_restart_that_fails_backs_the_promotion_out(self):
        self.running("rel-0001")
        self.world.restart_error = RuntimeError("restart.sh exited 1")
        result = self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual(result["verdict"], "rolled_back")
        self.assertEqual(self.releases.current(), "rel-0001")
        self.assertEqual(self.world.restarts, 2)
        self.assertIn("could not be restarted into rel-0002", result["reasons"][0])
        self.assertEqual(self.world.slept, [])

    def test_a_first_release_that_goes_bad_has_nowhere_to_go_back_to(self):
        self.world.readings = [GOOD, GOOD, GOOD, bad("there is no health.json: no tick has finished")]
        result = self.dog.deploy(self.tree("v1"), "rel-0001")
        self.assertEqual(result["verdict"], "failed")
        self.assertIn("no previous release", result["reasons"][-1])
        self.assertEqual(self.releases.current(), "rel-0001")  # something to run beats nothing to run
        self.assertEqual(self.story()[-2:], ["rollback", "verdict"])
        self.assertEqual(wd.EXIT_CODES["failed"], 4)

    def test_refusals_before_the_canary(self):
        self.running("rel-0001")
        again = self.dog.deploy(self.tree("rel-0001"), "rel-0001")
        self.assertEqual(again["verdict"], "refused")
        self.assertIn("already current", again["reasons"][0])
        self.staged("rel-0002", "one thing")
        clash = self.dog.deploy(self.tree("another thing"), "rel-0002")
        self.assertEqual(clash["verdict"], "refused")
        self.assertIn("different content", clash["reasons"][0])
        self.assertEqual(self.dog.deploy(self.tree("x"), "../up")["verdict"], "refused")
        self.assertEqual(self.dog.deploy(self.tmp / "nowhere", "rel-0003")["verdict"], "refused")
        self.assertEqual((self.world.canary_calls, self.world.restarts, self.releases.current()), ([], 0, "rel-0001"))

    def test_a_second_deploy_is_refused_while_one_runs(self):
        self.running("rel-0001")
        with self.releases.lock():
            result = self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual(result["verdict"], "refused")
        self.assertIn("another deploy", result["reasons"][0])
        self.assertFalse((self.base / "releases" / "rel-0002").exists())
        self.assertEqual(self.story(), ["verdict"])

    def test_watch_lengths(self):
        self.running("rel-0001")
        unwatched = self.dog.deploy(self.tree("v2"), "rel-0002", watch_seconds=0)
        self.assertEqual((unwatched["verdict"], unwatched["readings"], self.world.slept), ("promoted", 0, []))
        short = self.dog.deploy(self.tree("v3"), "rel-0003", watch_seconds=30, watch_every=30)
        self.assertEqual((short["verdict"], short["readings"]), ("promoted", 3))  # never a verdict on grace readings alone
        tuned = self.dog.deploy(self.tree("v4"), "rel-0004", canary_ticks=5, watch_seconds=120, watch_every=10)
        self.assertEqual((tuned["readings"], self.world.canary_calls[-1][2]), (12, 5))

    def test_every_canary_gets_a_fresh_root_that_is_not_the_houses_state(self):
        self.running("rel-0001")
        (self.base / "state").mkdir()
        self.dog.deploy(self.tree("v2"), "rel-0002", watch_seconds=0)
        self.clock.advance(5)
        self.dog.deploy(self.tree("v3"), "rel-0003", watch_seconds=0)
        roots = [call[1] for call in self.world.canary_calls]
        self.assertEqual(len(set(roots)), 2)
        for root in roots:
            self.assertEqual(root.parent, self.base / "canary")
            self.assertEqual(list(root.iterdir()), [])
        self.assertEqual(list((self.base / "state").iterdir()), [])

    def test_an_interrupted_watch_says_so(self):
        self.running("rel-0001")
        self.world.readings = [GOOD, GOOD, KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            self.dog.deploy(self.tree("v2"), "rel-0002")
        self.assertEqual(self.story()[-1], "interrupted")
        self.assertEqual(self.releases.history()[-1]["current"], "rel-0002")
        with self.releases.lock():  # and the lock was let go
            pass

    def test_old_releases_are_pruned_after_a_promotion_but_never_the_way_back(self):
        self.running("rel-0000")
        for n in range(1, 8):
            self.clock.advance(10)
            self.assertEqual(self.dog.deploy(self.tree(f"v{n}"), f"rel-000{n}", watch_seconds=0)["verdict"], "promoted")
        self.assertEqual(sorted(row["id"] for row in self.releases.list()), [f"rel-000{n}" for n in range(3, 8)])
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-0007", "rel-0006"))

    def test_the_operators_rollback(self):
        self.running("rel-0001")
        self.dog.deploy(self.tree("v2"), "rel-0002", watch_seconds=0)
        result = self.dog.rollback("it looked wrong on the site")
        self.assertEqual((result["ok"], result["current"], result["rolled_back_from"]), (True, "rel-0001", "rel-0002"))
        self.assertEqual(self.world.restarts, 2)
        self.assertEqual(self.releases.history()[-2]["reason"], "it looked wrong on the site")
        nothing = self.dog.rollback()
        self.assertEqual((nothing["ok"], nothing["current"]), (False, "rel-0001"))
        self.assertEqual(self.world.restarts, 2)


# -------------------------------------------------------------------- the real thing, in small
FAKE_MAIN = '''
import argparse, json, os, sys, time
from pathlib import Path

from league.ledger import Ledger, now_iso

BEHAVIOUR = {behaviour!r}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--root")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args()
    assert args.canary and args.no_publish and os.environ.get("LEAGUE_CANARY") == "1", "a canary must be told it is one"
    assert Path.cwd() == Path(__file__).resolve().parents[1], "a canary runs from its own release"
    root = Path(args.root)
    ledger = Ledger(root / "ledger.sqlite")
    if args.command == "verify":
        print(json.dumps({{"ledger_rows_verified": ledger.verify()}}))
        return 1 if BEHAVIOUR == "unreconciled" else 0
    ledger.append("ops.started", {{"release": BEHAVIOUR}})
    if BEHAVIOUR == "raises":
        raise RuntimeError("the new code is broken")
    if BEHAVIOUR == "hangs":
        time.sleep(120)
    if BEHAVIOUR == "alerts":
        ledger.append("ops.alert", {{"level": "error", "text": "alpaca-paper does not reconcile: cash differs by 3.0000"}})
    health = {{"at": now_iso(), "living": 5, "dead": 0, "ledger_seq": ledger.head()[0], "real_money": False,
              "books": {{"alpaca-paper": {{"frozen": "cash differs" if BEHAVIOUR == "frozen" else None, "open_orders": 0}}}}}}
    (root / "health.json").write_text(json.dumps(health))
    ledger.close()
    print("OK")
    return 0


raise SystemExit(main())
'''


def fake_release(path, behaviour):
    """A tiny `league` package: its `tick` writes a real ledger and a health file, or does not."""
    package = Path(path) / "league"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(FAKE_MAIN.format(behaviour=behaviour), encoding="utf-8")
    shutil.copy(REAL_LEDGER, package / "ledger.py")  # the real ledger, so the read-only checks are real
    return Path(path)


class RealSubprocessTest(Case):
    """The production canary (`python3 -m league tick` in a subprocess, from the release, with a
    timeout) against releases that are tiny fake packages."""

    def setUp(self):
        super().setUp()
        self.world = World(self.clock)
        (self.base / "state").mkdir(parents=True)
        self.canary = SubprocessCanary(python=sys.executable, tick_timeout=30, protected=[self.base / "state"])
        self.dog = Watchdog(
            self.releases, run_canary=self.canary, restart_house=self.world.restart_house,
            read_house_health=self.world.read_house_health, clock=self.clock, sleep=self.world.sleep,
        )

    def deploy(self, behaviour, release_id, **kw):
        self.clock.advance(1)
        return self.dog.deploy(fake_release(self.tmp / f"src-{release_id}", behaviour), release_id, **kw)

    def test_good_code_is_promoted_and_broken_code_never_becomes_current(self):
        good = self.deploy("ok", "rel-good")
        self.assertEqual(good["verdict"], "promoted", good["reasons"])
        self.assertEqual((self.releases.current(), self.world.restarts), ("rel-good", 1))
        canary = [row for row in good["stages"] if row["stage"] == "canary"][0]
        self.assertEqual([run["command"].split()[0] for run in canary["detail"]["runs"]], ["tick", "tick", "tick", "verify"])
        self.assertEqual([run["exit"] for run in canary["detail"]["runs"]], [0, 0, 0, 0])
        self.assertEqual(canary["detail"]["health"]["ledger_rows_verified"], 3)  # three ticks, three ops.started
        self.assertIn("OK", canary["detail"]["runs"][0]["stdout"])
        self.assertEqual(list((self.base / "state").iterdir()), [])  # the House's state was never touched
        self.assertTrue((Path(canary["canary_root"]) / "ledger.sqlite").exists())
        self.assertFalse((self.base / "releases" / "rel-good" / "league" / "__pycache__").exists())  # nor the release

        for behaviour, release_id, why in (
            ("raises", "rel-raises", "tick 1: it exited 1: RuntimeError: the new code is broken"),
            ("alerts", "rel-alerts", "after tick 1: 1 error alert(s) since seq 0"),
            ("frozen", "rel-frozen", "after tick 1: the alpaca-paper book is frozen: cash differs"),
            ("unreconciled", "rel-unrec", "verify: it exited 1"),
        ):
            result = self.deploy(behaviour, release_id)
            self.assertEqual(result["verdict"], "refused", behaviour)
            self.assertIn(why, result["reasons"][0])
            self.assertEqual(self.releases.current(), "rel-good")
        self.assertEqual(self.world.restarts, 1)  # none of them ever restarted the House
        refused = [row for row in self.releases.history() if row["stage"] == "canary" and row["release"] == "rel-raises"][0]
        self.assertIn("Traceback (most recent call last)", refused["detail"]["runs"][0]["stderr"])

        # And a release that passes its canary but sickens the real House is rolled back to the good one.
        self.world.readings = [GOOD, GOOD, GOOD, bad("3 error alert(s) since seq 40; the first, at seq 41: tick failed: KeyError")]
        sick = self.deploy("ok", "rel-sick")
        self.assertEqual((sick["verdict"], self.releases.current(), self.world.restarts), ("rolled_back", "rel-good", 3))
        verdicts = [(row["release"], row["verdict"]) for row in self.releases.history() if row["stage"] == "verdict"]
        self.assertEqual(verdicts, [("rel-good", "promoted"), ("rel-raises", "refused"), ("rel-alerts", "refused"),
                                    ("rel-frozen", "refused"), ("rel-unrec", "refused"), ("rel-sick", "rolled_back")])

    def test_a_tick_that_hangs_is_killed_and_refused(self):
        self.canary.tick_timeout = 1.5
        result = self.deploy("hangs", "rel-hangs", canary_ticks=1)
        self.assertEqual(result["verdict"], "refused")
        self.assertIn("did not finish in 1s and was killed", result["reasons"][0])
        self.assertIsNone(self.releases.current())

    def test_a_canary_is_never_run_on_the_houses_state(self):
        release = self.releases.stage(fake_release(self.tmp / "src", "ok"), "rel-0001")
        for root in (self.base / "state", self.base / "state" / "inner", self.base):
            health = self.canary(release, root, 1)
            self.assertFalse(health.ok)
            self.assertIn("never runs on the House's state", health.reasons[0])
        self.assertEqual(list((self.base / "state").iterdir()), [])


class CommandLineTest(Case):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = wd.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_deploy_status_and_rollback(self):
        self.base.mkdir()
        (self.base / "restart.sh").write_text(f"#!/bin/sh\necho restarted >> {self.base}/restarts.log\necho signalled\n", encoding="utf-8")
        base = ["--base", str(self.base)]
        code, first = self.run_cli("deploy", *base, "--source", str(fake_release(self.tmp / "a", "ok")), "--id", "rel-000a", "--canary-ticks", "1", "--watch-seconds", "0")
        self.assertEqual((code, first["verdict"], first["current"]), (0, "promoted", "rel-000a"))
        code, broken = self.run_cli("deploy", *base, "--source", str(fake_release(self.tmp / "b", "raises")), "--id", "rel-000b", "--canary-ticks", "1", "--watch-seconds", "0")
        self.assertEqual((code, broken["verdict"], broken["current"]), (2, "refused", "rel-000a"))
        code, second = self.run_cli("deploy", *base, "--source", str(fake_release(self.tmp / "c", "ok")), "--id", "rel-000c", "--canary-ticks", "1", "--watch-seconds", "0")
        self.assertEqual((code, second["current"], second["previous"]), (0, "rel-000c", "rel-000a"))

        code, seen = self.run_cli("status", *base)
        self.assertEqual((code, seen["current"], seen["previous"], seen["current_link"]), (0, "rel-000c", "rel-000a", "releases/rel-000c"))
        self.assertEqual(sorted(row["id"] for row in seen["releases"]), ["rel-000a", "rel-000b", "rel-000c"])
        self.assertEqual([row["verdict"] for row in seen["last_deploys"]], ["promoted", "refused", "promoted"])
        self.assertFalse(seen["house"]["ok"])  # no House has ever ticked in this base

        code, back = self.run_cli("rollback", *base, "--reason", "a test")
        self.assertEqual((code, back["current"]), (0, "rel-000a"))
        self.assertEqual((self.base / "restarts.log").read_text().count("restarted"), 3)  # two promotions and the rollback
        code, again = self.run_cli("rollback", *base)
        self.assertEqual((code, again["ok"]), (1, False))
        code, pruned = self.run_cli("prune", *base, "--keep", "1")
        self.assertEqual((code, pruned["removed"]), (0, ["rel-000b"]))

    def test_restart_script(self):
        self.base.mkdir()
        self.assertEqual(RestartScript(self.base)()["ran"], False)  # no script: touch nothing
        (self.base / "restart.sh").write_text("#!/bin/sh\necho 'signalled 4242'\n", encoding="utf-8")
        self.assertEqual(RestartScript(self.base)(), {"ran": True, "exit": 0, "output": "signalled 4242"})
        (self.base / "restart.sh").write_text("#!/bin/sh\necho 'kill: no such process'\nexit 1\n", encoding="utf-8")
        with self.assertRaises(RuntimeError) as caught:
            RestartScript(self.base)()
        self.assertIn("no such process", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


class InheritedFreeze(ReadHealthTest):
    """A release is judged on what it breaks, not on what it inherited.

    Sept 19, 2026: the Alpaca paper book froze on the league's first tick, and the release that
    fixed the freeze was rolled back by the watchdog because the book was frozen while it watched.
    """

    def test_a_book_frozen_before_the_promotion_is_not_the_releases_doing(self):
        write_health(self.root, self.clock, frozen="cash differs by 12.5000")
        self.assertFalse(self.read().ok)  # a canary, which inherits nothing, still fails
        healthy = self.read(inherited_frozen=["alpaca-paper"])
        self.assertTrue(healthy.ok, healthy.reasons)
        self.assertEqual(healthy.detail["frozen_before"], ["alpaca-paper"])

    def test_the_alerts_a_frozen_book_goes_on_making_are_inherited_too(self):
        """Sept 20, 2026: two releases in a row were rolled back on these -- including the one
        carrying the fix for that very book. The floor could not heal itself and no release of any
        kind could land while the book kept saying, every five minutes, what was already true."""
        ledger = self.ledger()
        ledger.append("ops.started", {"books": []})
        since = ledger.head()[0]
        ledger.append("ops.alert", {"level": "error", "text": "alpaca-paper does not reconcile: cash differs by -40.0000"})
        ledger.append("ops.alert", {"level": "error", "text": "alpaca-paper does not reconcile: cash differs by -40.0000"})
        write_health(self.root, self.clock, seq=ledger.head()[0], frozen="cash differs by -40.0000")
        loud = self.read(since_seq=since)
        self.assertFalse(loud.ok)  # a canary inherits nothing and still catches them
        quiet = self.read(since_seq=since, inherited_frozen=["alpaca-paper"])
        self.assertTrue(quiet.ok, quiet.reasons)
        self.assertEqual((quiet.detail["error_alerts"], quiet.detail["inherited_alerts"]), (0, 2))
        ledger.append("ops.alert", {"level": "error", "text": "tick failed: KeyError: 'settled'"})
        broke = self.read(since_seq=since, inherited_frozen=["alpaca-paper"])
        self.assertFalse(broke.ok)  # what the release really did break still counts
        self.assertIn("tick failed", broke.reasons[0])

    def test_a_book_that_freezes_under_the_release_is(self):
        write_health(self.root, self.clock, frozen="cash differs by 12.5000")
        health = self.read(inherited_frozen=["kalshi"])
        self.assertEqual(health.reasons, ("the alpaca-paper book is frozen: cash differs by 12.5000",))

    def test_the_watch_reads_what_was_broken_before_it_looks(self):
        from league.watchdog import HouseHealth

        write_health(self.root, self.clock, frozen="cash differs by 12.5000")
        watch = HouseHealth(self.root, clock=self.clock, max_age_seconds=300, stall_seconds=0, restart_within=None)
        self.assertTrue(watch().ok, "the freeze was already there when the watch began")
        write_health(self.root, self.clock, frozen=None, seq=2)
        self.assertTrue(watch().ok)


class FrozenByThePreviousProcess(ReadHealthTest):
    """Sept 24, 2026, 15:37-15:39Z: Deploy C was rolled back on a freeze the OLD House recorded in its
    last tick, 30 s before the promotion, in a health.json the new House had not yet replaced. The watch
    after a promotion counts a frozen book only in a health.json dated at or after the House's first
    `ops.started` since the promotion; a canary and `status` still count every freeze."""

    def test_a_freeze_the_old_process_wrote_before_the_house_restarted_is_not_the_releases(self):
        ledger = self.ledger()
        since = ledger.head()[0]
        write_health(self.root, self.clock, frozen="cash differs by -0.0269", age=190)
        promoted = self.clock() - 30
        waiting = self.read(since_seq=since, inherited_before=promoted)
        self.assertTrue(waiting.ok, waiting.reasons)  # no ops.started yet: the old process's file
        self.assertEqual(waiting.detail["frozen_by_previous_process"], ["alpaca-paper"])
        ledger.append("ops.started", {"books": []})  # the new House starts; its first tick is not done
        started = self.read(since_seq=since, inherited_before=promoted)
        self.assertTrue(started.ok, started.reasons)
        self.assertEqual(started.detail["frozen_by_previous_process"], ["alpaca-paper"])

    def test_a_freeze_in_a_health_file_the_new_house_wrote_is_the_releases(self):
        ledger = self.ledger()
        since = ledger.head()[0]
        ledger.append("ops.started", {"books": []})
        write_health(self.root, self.clock, frozen="cash differs by -0.0269")  # dated now: after the start
        health = self.read(since_seq=since, inherited_before=self.clock() - 60)
        self.assertEqual(health.reasons, ("the alpaca-paper book is frozen: cash differs by -0.0269",))
        self.assertNotIn("frozen_by_previous_process", health.detail)

    def test_a_canary_and_a_reading_without_the_ledger_still_count_it(self):
        write_health(self.root, self.clock, frozen="cash differs by -0.0269", age=190)
        self.assertFalse(self.read().ok)  # a canary: no promotion, nothing inherited
        self.assertFalse(self.read(since_seq=0, inherited_before=self.clock() - 30).ok)  # no ledger: nobody can say whose file it is
        ledger = self.ledger()
        since = ledger.head()[0]
        self.assertFalse(self.read(since_seq=since).ok)  # `status`: no promotion to measure from

    def test_a_restart_whose_time_cannot_be_read_leaves_the_freeze_counted(self):
        ledger = self.ledger()
        since = ledger.head()[0]
        ledger.append("ops.started", {"books": []})
        with sqlite3.connect(self.root / "ledger.sqlite") as db:
            started = db.execute("SELECT at FROM ledger WHERE kind = 'ops.started'").fetchone()[0]
        write_health(self.root, self.clock, frozen="cash differs by -0.0269", age=190)
        real = wd.epoch
        with unittest.mock.patch.object(wd, "epoch", lambda value: None if value == started else real(value)):  # a row no reader can date
            health = self.read(since_seq=since, inherited_before=self.clock() - 30)
        self.assertEqual(health.reasons, ("the alpaca-paper book is frozen: cash differs by -0.0269",))

    def test_the_old_file_still_goes_stale(self):
        ledger = self.ledger()
        since = ledger.head()[0]
        ledger.append("ops.started", {"books": []})
        write_health(self.root, self.clock, frozen="cash differs by -0.0269", age=400)
        health = self.read(since_seq=since, inherited_before=self.clock() - 30, max_age_seconds=300)
        self.assertFalse(health.ok)
        self.assertEqual(len(health.reasons), 1)
        self.assertIn("health.json is 400s old", health.reasons[0])

    def test_the_watch_replays_the_rollback_of_deploy_c(self):
        from league.watchdog import HouseHealth

        ledger = self.ledger()
        ledger.append("ops.started", {"books": []})  # the old House, long before
        self.clock.advance(3600)
        write_health(self.root, self.clock, frozen=None, seq=ledger.head()[0], age=160)
        watch = HouseHealth(self.root, clock=self.clock, max_age_seconds=300, stall_seconds=450, restart_within=None)
        self.assertTrue(watch().ok)  # the reading before the promotion: nothing frozen, nothing inherited
        self.assertEqual(watch.inherited_frozen, ())
        # The old House's last tick, begun before the promotion, froze the practice book and wrote its file.
        write_health(self.root, self.clock, frozen="cash differs by -0.0269", seq=ledger.head()[0], age=160)
        self.clock.advance(30)
        first = watch()
        self.assertTrue(first.ok, first.reasons)
        self.assertEqual(first.detail["frozen_by_previous_process"], ["alpaca-paper"])
        ledger.append("ops.started", {"books": []})  # the new House starts; its first tick is not done
        self.clock.advance(30)
        self.assertTrue(watch().ok, "still the old process's file")
        self.clock.advance(30)
        write_health(self.root, self.clock, frozen=None, seq=ledger.head()[0])  # the new House's first tick
        self.assertTrue(watch().ok)
        self.clock.advance(30)
        write_health(self.root, self.clock, frozen="cash differs by -0.0328", seq=ledger.head()[0] + 1)
        bad = watch()
        self.assertFalse(bad.ok, "a freeze under the new release is its own")
        self.assertEqual(bad.reasons, ("the alpaca-paper book is frozen: cash differs by -0.0328",))


class HealthFailuresAndInheritedConditions(ReadHealthTest):
    """L3 (Sept 24, 2026). health.json `failures` (today: "the lab evaluated nothing in the last hour
    while its queue is not empty") is a bad reading, and so is an escalated warning. What the
    watchdog does with them: a canary, which inherits nothing, refuses on either; the watch after a
    promotion counts a condition that BEGAN before the promotion (`since`, `began_at`) as inherited,
    never as the new release's doing -- an hour of lab idleness cannot begin inside a ten-minute
    watch, so the watch never rolls a release back for it; and `status` shows it as a reason."""

    FAILURE = {"check": "lab_evaluates", "text": "the lab evaluated nothing in the last hour while 618 candidates are queued"}

    def test_a_health_failure_is_a_bad_reading(self):
        write_health(self.root, self.clock, failures=[{**self.FAILURE, "since": wd.iso(self.clock() - 4000)}])
        health = self.read()
        self.assertFalse(health.ok)
        self.assertEqual(health.reasons, ("health failure (lab_evaluates): the lab evaluated nothing in the last hour while 618 candidates are queued",))

    def test_one_that_began_before_the_promotion_is_inherited_and_one_after_it_is_not(self):
        write_health(self.root, self.clock, failures=[{**self.FAILURE, "since": wd.iso(self.clock() - 4000)}])
        healthy = self.read(inherited_before=self.clock() - 600)
        self.assertTrue(healthy.ok, healthy.reasons)
        self.assertEqual(healthy.detail["inherited_failures"], ["lab_evaluates"])
        write_health(self.root, self.clock, failures=[{**self.FAILURE, "since": wd.iso(self.clock() - 30)}])
        self.assertFalse(self.read(inherited_before=self.clock() - 600).ok)
        write_health(self.root, self.clock, failures=[{**self.FAILURE, "since": "not a time"}])
        self.assertFalse(self.read(inherited_before=self.clock() - 600).ok, "a failure that cannot say when it began is not inherited")

    def test_an_error_whose_condition_began_before_the_promotion_is_inherited(self):
        ledger = self.ledger()
        ledger.append("ops.started", {"books": []})
        since = ledger.head()[0]
        ledger.append("ops.alert", {"level": "error", "text": "a warning repeated 10 times in 30 minutes: the lab's step failed (IndexError)",
                                    "repeated": {"count": 10}, "began_at": wd.iso(self.clock() - 3000)})
        ledger.append("ops.alert", {"level": "error", "text": "health failure: the lab evaluated nothing in the last hour",
                                    "failure": "lab_evaluates", "began_at": wd.iso(self.clock() - 4000)})
        write_health(self.root, self.clock, seq=ledger.head()[0])
        self.assertFalse(self.read(since_seq=since).ok, "a canary inherits nothing")
        quiet = self.read(since_seq=since, inherited_before=self.clock() - 600)
        self.assertTrue(quiet.ok, quiet.reasons)
        self.assertEqual((quiet.detail["error_alerts"], quiet.detail["inherited_alerts"]), (0, 2))
        ledger.append("ops.alert", {"level": "error", "text": "a warning repeated 10 times in 30 minutes: something new",
                                    "began_at": wd.iso(self.clock() - 60)})
        broke = self.read(since_seq=since, inherited_before=self.clock() - 600)
        self.assertFalse(broke.ok, "a run of repeats that began under the release is the release's doing")
        self.assertIn("something new", broke.reasons[0])


class TheWatchNeverRollsBackForTheLab(Case):
    def test_the_labs_hour_of_nothing_is_read_as_inherited_through_the_watch(self):
        root = self.base / "state"
        root.mkdir(parents=True)
        ledger = Ledger(root / "ledger.sqlite", clock=self.clock)
        self.addCleanup(ledger.close)
        ledger.append("ops.started", {"books": []})
        failure = {"check": "lab_evaluates", "text": "the lab evaluated nothing in the last hour while 12 candidates are queued",
                   "since": wd.iso(self.clock() - 3300)}
        write_health(root, self.clock, seq=ledger.head()[0])
        watch = HouseHealth(root, clock=self.clock, restart_within=None)
        self.assertTrue(watch().ok)  # the reading before the promotion
        for _ in range(4):
            self.clock.advance(150)  # 55 minutes of nothing before the promotion becomes an hour inside the watch
            ledger.append("ops.started", {"books": []})
            ledger.append("ops.alert", {"level": "error", "text": f"health failure: {failure['text']}", "failure": "lab_evaluates",
                                        "began_at": failure["since"]})
            write_health(root, self.clock, seq=ledger.head()[0], failures=[failure])
            reading = watch()
            self.assertTrue(reading.ok, reading.reasons)
        self.assertFalse(read_health(root, now=self.clock()).ok, "status still says so")


# ------------------------------------------------------------------------------- environment
def raised(make, *, inside=None, cause=None, suppress=False):
    """The exception `make()` raises, raised the way the House's clients raise theirs: inside the
    handler of `inside` (so `inside` is its `__context__`), `from cause`, or `from None`."""
    try:
        if inside is None:
            if cause is not None:
                raise make() from cause
            raise make()
        try:
            raise inside
        except BaseException:
            if suppress:
                raise make() from None
            raise make()
    except BaseException as exc:  # noqa: BLE001
        return exc


class TheEnvironmentClassifier(unittest.TestCase):
    """H2 (the forward-first run, Sept 25, 2026): an alert about a call outside the House's process is
    marked `environment` only when the SERVICE failed -- a 5xx, 429, 408 or 425, a timeout, a refused,
    reset or unreachable connection, a name that did not resolve -- never when this code did."""

    def http_error(self, url, code, msg):
        import urllib.error

        error = urllib.error.HTTPError(url, code, msg, {}, io.BytesIO(b""))
        self.addCleanup(error.close)
        return error

    def test_a_services_failure_is_marked(self):
        import errno
        import http.client
        import socket
        import urllib.error

        from league.publish import PublishError
        from league.sandbox import SandboxError
        from ltcm.data import TransportError as DataTransportError
        from ltcm.provider import TransportError as ProviderTransportError
        from ltcm.sailbox import SailboxError

        sail_503 = SailboxError("sailbox api 503: prepare checkpoint warm snapshot: rpc error: code = DeadlineExceeded", status=503)
        for exc in (
            sail_503,  # Sept 24-25, 2026: 73 of these rolled back six releases
            SailboxError("sailbox api 429: slow down", status=429),
            raised(lambda: SailboxError("sailbox transport failed: TimeoutError"), inside=TimeoutError("timed out"), suppress=True),
            raised(lambda: SandboxError("agent: SailboxError: sailbox api 502: bad gateway"), cause=SailboxError("sailbox api 502", status=502)),
            self.http_error("https://api.github.com/x", 502, "Bad Gateway"),
            urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused")),
            urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution")),
            socket.gaierror(socket.EAI_NONAME, "Name or service not known"),
            TimeoutError("The read operation timed out"),
            ConnectionResetError(errno.ECONNRESET, "reset by peer"),
            http.client.RemoteDisconnected("Remote end closed connection without response"),
            OSError(errno.ENETUNREACH, "Network is unreachable"),
            PublishError("the site refused the checkpoint: HTTP 503 upstream", status=503),
            raised(lambda: PublishError("the site did not answer: URLError"), inside=urllib.error.URLError(TimeoutError("timed out")),
                   suppress=True),
            # Sept 23, 2026: five wakes failed on the gateway's read timeout (haghani-52 at 07:35:14Z the first)
            raised(lambda: DataTransportError("GET https://ltcm-gateway/v1/alpaca-paper/v2/orders/x failed: The read operation timed out"),
                   cause=TimeoutError("The read operation timed out")),
            raised(lambda: ProviderTransportError("provider_http_503"),
                   inside=self.http_error("https://api.sail/v1", 503, "Service Unavailable"), suppress=True),
        ):
            with self.subTest(exc=repr(exc)[:90]):
                self.assertTrue(wd.service_failed(exc))
                self.assertEqual(wd.environment("sail", exc), {"environment": "sail"})

    def test_this_codes_own_failure_is_never_marked(self):
        """The unit test the brief asks for: an alert on the Sail path raised by a code exception is the House's."""
        import errno
        import http.client
        import urllib.error

        from league.publish import PublishError
        from league.sandbox import SandboxError
        from ltcm.provider import TransportError as ProviderTransportError
        from ltcm.sailbox import SailboxError

        sail_503 = SailboxError("sailbox api 503", status=503)
        for exc in (
            TypeError("unsupported operand type(s) for +: 'int' and 'str'"),
            KeyError("sailbox_id"),
            AttributeError("'NoneType' object has no attribute 'get'"),
            ValueError("not JSON"),
            raised(lambda: KeyError("checkpoint_id"), inside=sail_503),  # a bug in the handler of a 503 is still a bug
            raised(lambda: TypeError("bad payload"), inside=urllib.error.URLError(TimeoutError("timed out"))),
            urllib.error.URLError("unknown url type: htps"),  # a URL this code built
            http.client.InvalidURL("nonnumeric port: 'x'"),
            raised(lambda: SandboxError("agent: TypeError: bad payload"), cause=TypeError("bad payload")),
            SailboxError("sailbox api 400: invalid ttl_seconds", status=400),  # a payload this code built
            SailboxError("sailbox api 401: bad key", status=401),
            SailboxError("sailbox api 404: no such box", status=404),
            SailboxError("not a Sailbox id"),  # the client's own validation: no status, no network under it
            self.http_error("https://api.github.com/x", 404, "Not Found"),
            PublishError("the site refused the checkpoint: HTTP 400 schema", status=400),
            ProviderTransportError("provider_key_missing"),
            RuntimeError("sailbox api 503: said in words, not a status"),
            RuntimeError("1 running boxes are named ltcm-floor"),
            FileNotFoundError(errno.ENOENT, "No such file or directory"),
            sqlite3.OperationalError("database is locked"),
            None,
        ):
            with self.subTest(exc=repr(exc)[:90]):
                self.assertFalse(wd.service_failed(exc))
                self.assertEqual(wd.environment("sail", exc), {})
        self.assertEqual(wd.environment("", sail_503), {}, "no service named, no marker")


class EnvironmentAlertsInTheWatch(ReadHealthTest):
    """H2: an error alert marked `environment` is counted in the reading's detail and never a reason,
    in the watch after a promotion and in the canary alike; an unmarked one still is."""

    SAIL = "The daily backup of the House box failed on Sail's side (SailboxError: sailbox api 503: prepare checkpoint warm snapshot)."

    def test_an_environment_alert_is_counted_and_never_a_reason(self):
        ledger = self.ledger()
        ledger.append("ops.started", {"books": []})
        since = ledger.head()[0]
        ledger.append("ops.alert", {"level": "error", "text": self.SAIL, "environment": "sail", "failures": 1,
                                    "began_at": wd.iso(self.clock())})  # began INSIDE the watch: nothing to inherit
        ledger.append("ops.alert", {"level": "error", "text": "a warning repeated 10 times in 30 minutes: publishing failed (PublishError)",
                                    "environment": "site", "began_at": wd.iso(self.clock())})
        write_health(self.root, self.clock, seq=ledger.head()[0])
        for label, kw in (("the watch", {"inherited_before": self.clock() - 600}), ("a canary", {})):
            with self.subTest(label):
                health = self.read(since_seq=since, **kw)
                self.assertTrue(health.ok, health.reasons)
                self.assertEqual((health.detail["error_alerts"], health.detail["environment_alerts"]), (0, 2))
                self.assertEqual(health.detail["environment_first"], {"seq": since + 1, "service": "sail", "text": self.SAIL})

    def test_the_houses_own_errors_still_roll_back_beside_an_outage(self):
        ledger = self.ledger()
        ledger.append("ops.started", {"books": []})
        since = ledger.head()[0]
        ledger.append("ops.alert", {"level": "error", "text": self.SAIL, "environment": "sail"})
        ledger.append("ops.alert", {"level": "error", "text": "tick failed: KeyError: 'settled'"})
        ledger.append("ops.alert", {"level": "error", "text": "a marker that is not a service", "environment": True})
        ledger.append("ops.alert", {"level": "error", "text": "an empty marker", "environment": "  "})
        write_health(self.root, self.clock, seq=ledger.head()[0])
        health = self.read(since_seq=since, inherited_before=self.clock() - 600)
        self.assertFalse(health.ok)
        self.assertEqual((health.detail["error_alerts"], health.detail["environment_alerts"]), (3, 1))
        self.assertIn("3 error alert(s) since seq 1; the first, at seq 3: tick failed: KeyError: 'settled'", health.reasons[0])

    def test_no_environment_alert_is_zero(self):
        ledger = self.ledger()
        since = ledger.head()[0]
        write_health(self.root, self.clock, seq=since)
        health = self.read(since_seq=since)
        self.assertEqual(health.detail["environment_alerts"], 0)
        self.assertNotIn("environment_first", health.detail)
