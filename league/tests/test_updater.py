import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from league.tests.fakes import Clock
from league.updater import UpdateError, Updater, unpack
from league.watchdog import Releases

GOOD = 'NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"]}\nPARAMS = {}\n\ndef decide(ctx):\n    return {"intents": []}\n'


def tarball(files: dict[str, str], *, links: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"long-term-capital-management-main/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"long-term-capital-management-main/{name}")
            info.type, info.linkname = tarfile.SYMTYPE, target
            archive.addfile(info)
    return buffer.getvalue()


def tree(real_money=False, extra=None, tick_seconds=60):
    files = {
        "league/config.json": json.dumps({"real_money": real_money, "tick_seconds": tick_seconds}),
        "league/game.json": (Path(__file__).resolve().parents[1] / "game.json").read_text(),
        "league/strategies/registry.json": "[]",
        "league/house.py": "# the house\n",
        "league/__main__.py": "# a release is recognised by this file\n",
        "ltcm/broker.py": "# broker\n",
        "scripts/run.sh": "#!/bin/sh\n",
        "README.md": "not part of a release",
        ".github/workflows/x.yml": "not part of a release",
        "league/.secret": "dotfiles never travel",
    }
    files.update(extra or {})
    return files


class UpdaterCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = Path(self.dir.name)
        self.clock = Clock()
        self.releases = Releases(self.base)
        source = self.base / "src"
        unpack(tarball(tree()), source)
        self.releases.stage(source, "first-release")
        self.releases.promote("first-release")
        self.launched = []
        self.main = tarball(tree())

    def tearDown(self):
        self.dir.cleanup()

    def updater(self):
        return Updater(self.base, fetch=lambda: self.main, launch=lambda source, rid: self.launched.append((source, rid)), clock=self.clock)

    def test_only_release_trees_travel_and_nothing_strange(self):
        target = self.base / "unpacked"
        unpack(tarball(tree(), links={"league/evil": "/etc/passwd"}), target)
        names = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
        self.assertEqual(names, ["league/__main__.py", "league/config.json", "league/game.json", "league/house.py", "league/strategies/registry.json",
                                 "ltcm/broker.py", "scripts/run.sh"])
        self.assertEqual((target / "scripts/run.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual((target / "league/house.py").stat().st_mode & 0o777, 0o644)
        with self.assertRaises(UpdateError):
            unpack(tarball({"README.md": "x"}), self.base / "empty")

    def test_the_same_main_is_left_alone(self):
        out = self.updater().check()
        self.assertEqual((out["action"], self.launched), ("none", []))
        self.assertEqual(list((self.base / "incoming").iterdir()), [])

    def test_a_new_commit_goes_to_the_watchdog_once(self):
        self.main = tarball(tree(extra={"league/house.py": "# the house, improved\n"}))
        updater = self.updater()
        out = updater.check()
        self.assertEqual(out["action"], "deploying")
        source, release_id = self.launched[0]
        self.assertTrue(release_id.startswith("main-"))
        self.assertEqual((source / "league/house.py").read_text(), "# the house, improved\n")
        # The watchdog records what it did; a tree it already judged is never handed over again.
        self.releases.record({"release": release_id, "stage": "verdict", "verdict": "refused"})
        self.assertEqual(updater.check()["action"], "none")
        self.assertEqual(len(self.launched), 1)

    def test_main_cannot_turn_real_money_on_or_carry_an_unsafe_strategy(self):
        self.main = tarball(tree(real_money=True))
        out = self.updater().check()
        self.assertEqual(out["action"], "refused")
        self.assertIn("real_money", " ".join(out["reasons"]))
        self.main = tarball(tree(extra={"league/strategies/bad.py": "import os\ndef decide(ctx):\n    return {}\n",
                                        "league/strategies/registry.json": json.dumps([{"name": "bad", "family": "t", "file": "bad.py", "why": "x"}])}))
        out = self.updater().check()
        self.assertEqual(out["action"], "refused")
        self.assertEqual(self.launched, [])
        self.main = tarball(tree(tick_seconds=5))
        self.assertIn("tick_seconds", " ".join(self.updater().check()["reasons"]))

    def test_a_sound_new_strategy_is_let_through(self):
        self.main = tarball(tree(extra={"league/strategies/ok.py": GOOD, "league/strategies/registry.json": json.dumps([{"name": "ok", "family": "t", "file": "ok.py", "why": "x"}])}))
        self.assertEqual(self.updater().check()["action"], "deploying")

    def test_it_looks_at_most_once_an_interval(self):
        updater = self.updater()
        self.assertTrue(updater.due())
        updater.check()
        self.assertFalse(updater.due())
        self.clock.advance(1801)
        self.assertTrue(updater.due())


if __name__ == "__main__":
    unittest.main()


class ABusyLockDoesNotRetireACommit(UpdaterCase):
    """`Watchdog.deploy` holds its lock through the canary, the promotion, the restart and the
    whole ten-minute watch. The restart brings a House up whose updater checks on its FIRST tick,
    while that lock is still held -- so the race is not rare, it is what happens after every
    promotion. Retiring the commit on it meant a floor that rewrites itself dropped its own
    improvements one at a time, silently, with no retry and no expiry."""

    def test_a_release_refused_for_a_busy_lock_is_tried_again(self):
        self.main = tarball(tree(extra={"league/house.py": "# the house, improved\n"}))
        updater = self.updater()
        self.assertEqual(updater.check()["action"], "deploying")
        _, release_id = self.launched[0]
        self.releases.record({"release": release_id, "stage": "verdict", "verdict": "refused", "busy": True,
                              "reasons": ["another deploy or rollback is running (pid 123)"]})
        self.assertNotIn(release_id, updater.tried())
        self.assertEqual(updater.check()["action"], "deploying")   # the same content, offered again
        self.assertEqual(len(self.launched), 2)

    def test_a_release_the_watchdog_really_judged_is_not_offered_again(self):
        self.main = tarball(tree(extra={"league/house.py": "# the house, improved\n"}))
        updater = self.updater()
        self.assertEqual(updater.check()["action"], "deploying")
        _, release_id = self.launched[0]
        self.releases.record({"release": release_id, "stage": "verdict", "verdict": "rolled_back",
                              "reasons": ["the alpaca-paper book is frozen"]})
        self.assertIn(release_id, updater.tried())
        self.assertEqual(updater.check()["action"], "none")
        self.assertEqual(len(self.launched), 1)
