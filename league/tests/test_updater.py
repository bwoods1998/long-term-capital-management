import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from league.tests.fakes import Clock
from league.updater import (REQUIRED_CHECKS, TRUSTED_WORKFLOWS_SHA256, UpdateError, Updater, judge_check_runs, unpack,
                            workflows_digest)
from league.watchdog import Releases

SHA_A = "a" * 40
SHA_B = "b" * 40
#: The workflows every synthetic main carries: the pin a test Updater trusts is computed from them.
WORKFLOWS = {".github/workflows/checks.yml": "name: Checks\n"}


def passed(sha):
    """GitHub's answer for a commit whose required checks all succeeded, from GitHub Actions."""
    return judge_check_runs(sha, {"total_count": len(REQUIRED_CHECKS), "check_runs": [
        {"id": 100 + i, "name": name, "head_sha": sha, "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}}
        for i, name in enumerate(REQUIRED_CHECKS)]})

GOOD = 'NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"]}\nPARAMS = {}\n\ndef decide(ctx):\n    return {"intents": []}\n'


def tarball(files: dict[str, str], *, links: dict[str, str] | None = None, sha: str = SHA_A) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"long-term-capital-management-{sha}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"long-term-capital-management-{sha}/{name}")
            info.type, info.linkname = tarfile.SYMTYPE, target
            archive.addfile(info)
    return buffer.getvalue()


def tree(real_money=False, extra=None, tick_seconds=60):
    files = {
        "league/config.json": json.dumps({"real_money": real_money, "tick_seconds": tick_seconds}),
        "league/game.json": (Path(__file__).resolve().parents[1] / "game.json").read_text(),
        "league/ci.py": "# a real tree carries its own judge; these tests hand `Updater` a stub one\n",
        "league/strategies/registry.json": "[]",
        "league/house.py": "# the house\n",
        "league/__main__.py": "# a release is recognised by this file\n",
        "ltcm/broker.py": "# broker\n",
        "scripts/run.sh": "#!/bin/sh\n",
        "README.md": "not part of a release",
        **WORKFLOWS,
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
        self.sha = SHA_A
        self.main = tarball(tree())
        self.attested = []

    def tearDown(self):
        self.dir.cleanup()

    def attest(self, sha):
        self.attested.append(sha)
        return passed(sha)

    def updater(self, judge=None, attest=None):
        """`judge` stands in for the RUNNING release's `league.ci --content-only` run against the
        candidate (these synthetic trees have no package to run it from); `attest` for GitHub."""
        return Updater(self.base, head=lambda: self.sha, fetch=lambda sha: self.main,
                       launch=lambda source, rid, record=None: self.launched.append((source, rid)),
                       clock=self.clock, judge=judge or (lambda incoming, running: []), attest=attest or self.attest,
                       workflows_pin=workflows_digest(tarball(tree())))

    def test_only_release_trees_travel_and_nothing_strange(self):
        target = self.base / "unpacked"
        unpack(tarball(tree(), links={"league/evil": "/etc/passwd"}), target)
        names = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
        self.assertEqual(names, ["league/__main__.py", "league/ci.py", "league/config.json", "league/game.json", "league/house.py", "league/strategies/registry.json",
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

    @staticmethod
    def content_judge(incoming, running):
        """What the running release's `league.ci --content-only --root <candidate>` reports. In
        production that is a subprocess of the trusted tree; here the checks are called directly."""
        from league import ci

        return (ci.check_strategies(incoming) + ci.check_tools(incoming) + ci.check_game(incoming)
                + ci.check_config(None, incoming, baseline=running))

    def test_main_cannot_turn_real_money_on_whatever_its_own_judge_says(self):
        """The real-money switch is not the incoming tree's to decide, so this one check stays in
        `vet` itself, in code the incoming tree cannot touch."""
        self.main = tarball(tree(real_money=True))
        out = self.updater().check()
        self.assertEqual(out["action"], "refused")
        self.assertIn("real_money", " ".join(out["reasons"]))

    def test_the_incoming_trees_own_checks_refuse_an_unsafe_strategy_and_a_bad_dial(self):
        self.main = tarball(tree(extra={"league/strategies/bad.py": "import os\ndef decide(ctx):\n    return {}\n",
                                        "league/strategies/registry.json": json.dumps([{"name": "bad", "family": "t", "file": "bad.py", "why": "x"}])}))
        out = self.updater(judge=self.content_judge).check()
        self.assertEqual(out["action"], "refused")
        self.assertEqual(self.launched, [])
        self.main = tarball(tree(tick_seconds=5))
        self.assertIn("tick_seconds", " ".join(self.updater(judge=self.content_judge).check()["reasons"]))

    def test_a_candidate_that_changes_its_judge_is_the_owners_deploy(self):
        """Sept 20, 2026 let a tree judge itself so a commit that widened a bound could land. That
        handed the candidate its own verdict. Now a change to the judges is refused here, loudly,
        and never reaches the candidate's own checks at all."""
        wider = (Path(__file__).resolve().parents[1] / "ci.py").read_text().replace(
            '"tick_seconds": (30, 600)', '"tick_seconds": (5, 600)')
        self.main = tarball(tree(tick_seconds=5, extra={"league/ci.py": wider}))
        judged = []
        out = self.updater(judge=lambda incoming, running: judged.append(incoming) or []).check()
        self.assertEqual(out["action"], "refused")
        self.assertIn("league/ci.py", " ".join(out["reasons"]))
        self.assertIn("owner's deploy", " ".join(out["reasons"]))
        self.assertEqual((judged, self.launched), ([], []))
        self.assertIn("main-", out["release"])
        # So is the constitution, and every other file the running ci.py forbids to every role.
        self.main = tarball(tree(extra={"league/constitution.py": "MONEY = 'mine'\n"}))
        self.assertIn("league/constitution.py", " ".join(self.updater().check()["reasons"]))

    def test_the_running_judges_bounds_hold_whatever_the_candidate_widens(self):
        self.main = tarball(tree(tick_seconds=5))
        out = self.updater(judge=self.content_judge).check()
        self.assertEqual(out["action"], "refused")
        self.assertIn("tick_seconds", " ".join(out["reasons"]))

    def test_config_may_move_only_its_dials_from_the_running_release(self):
        self.main = tarball(tree(extra={"league/config.json": json.dumps({"real_money": False, "tick_seconds": 60, "auto_update": False})}))
        out = self.updater(judge=self.content_judge).check()
        self.assertEqual(out["action"], "refused")
        self.assertIn("auto_update is not an operating dial", " ".join(out["reasons"]))

    def test_the_trusted_checks_run_without_the_houses_secrets(self):
        """The checks execute Merton-written strategy code; the House's process holds its three
        tokens in the environment. The subprocess gets a scrubbed one, and the TRUSTED tree's path."""
        import os
        from unittest import mock

        from league import updater as module

        seen, how = {}, {}

        def run(argv, **kw):
            seen.update(kw.get("env") or {"<inherited>": "everything"})
            how.update(argv=argv, cwd=kw.get("cwd"))
            nonce = kw["input"].strip()
            return subprocess.CompletedProcess(argv, 0, f"VERDICT {nonce} {json.dumps({'passed': True, 'problems': []})}\n", "")

        secrets = {"GATEWAY_TOKEN": "g" * 40, "SAIL_API_KEY": "s" * 40, "CAPITAL_PUBLISH_TOKEN": "c" * 40,
                   "LEAGUE_ENV": "/workspace/.env", "PATH": "/usr/bin"}
        trusted = Path(self.dir.name) / "trusted-tree"
        (trusted / "league").mkdir(parents=True)
        (trusted / "league" / "ci.py").write_text("")
        incoming = Path(self.dir.name) / "incoming-tree"
        with mock.patch.dict(os.environ, secrets), mock.patch.object(module.subprocess, "run", run):
            self.assertEqual(Updater(self.base, trusted=trusted)._judged_by_trusted(incoming, self.base / "current"), [])
        self.assertEqual(seen.get("PATH"), "/usr/bin")
        self.assertEqual(seen.get("PYTHONPATH"), str(trusted))
        self.assertEqual(how["cwd"], str(trusted))
        self.assertIn(str(incoming.resolve()), how["argv"])
        for name in ("GATEWAY_TOKEN", "SAIL_API_KEY", "CAPITAL_PUBLISH_TOKEN", "LEAGUE_ENV", "<inherited>"):
            self.assertNotIn(name, seen)

    def test_a_sound_new_strategy_is_let_through(self):
        self.main = tarball(tree(extra={"league/strategies/ok.py": GOOD, "league/strategies/registry.json": json.dumps([{"name": "ok", "family": "t", "file": "ok.py", "why": "x"}])}))
        self.assertEqual(self.updater(judge=self.content_judge).check()["action"], "deploying")

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


class ExactCommitAttestation(UpdaterCase):
    """GitHub's check runs on the exact commit, or nothing deploys."""

    def test_the_rule_counts_only_this_sha_and_only_github_actions(self):
        good = passed(SHA_A)
        self.assertEqual(good["state"], "passed")
        other_head = judge_check_runs(SHA_B, {"check_runs": [dict(run, head_sha=SHA_A) for run in
                                                             [{"id": 1, "name": n, "status": "completed", "conclusion": "success",
                                                               "app": {"slug": "github-actions"}} for n in REQUIRED_CHECKS]]})
        self.assertEqual(other_head["state"], "pending")
        self.assertEqual(other_head["ignored_runs"], len(REQUIRED_CHECKS))
        forged = judge_check_runs(SHA_A, {"check_runs": [{"id": 1, "name": n, "head_sha": SHA_A, "status": "completed", "conclusion": "success",
                                                          "app": {"slug": "engineer-bot"}} for n in REQUIRED_CHECKS]})
        self.assertEqual(forged["state"], "pending")
        runs = [{"id": 1, "name": n, "head_sha": SHA_A, "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}}
                for n in REQUIRED_CHECKS]
        runs.append({"id": 2, "name": REQUIRED_CHECKS[1], "head_sha": SHA_A, "status": "completed", "conclusion": "failure",
                     "app": {"slug": "github-actions"}})
        self.assertEqual(judge_check_runs(SHA_A, {"check_runs": runs})["state"], "failed")  # the re-run that failed decides
        runs[-1] = dict(runs[-1], status="in_progress", conclusion=None)
        self.assertEqual(judge_check_runs(SHA_A, {"check_runs": runs})["state"], "pending")
        for conclusion in ("cancelled", "skipped", "neutral", "timed_out"):
            runs[-1] = dict(runs[-1], status="completed", conclusion=conclusion)
            self.assertEqual(judge_check_runs(SHA_A, {"check_runs": runs})["state"], "failed", conclusion)

    def test_a_later_head_never_inherits_an_earlier_heads_approval(self):
        approved = {SHA_A}
        attest = lambda sha: passed(sha) if sha in approved else judge_check_runs(sha, {"check_runs": []})  # noqa: E731
        self.main = tarball(tree(extra={"league/house.py": "# A\n"}), sha=SHA_A)
        out = self.updater(attest=attest).check()
        self.assertEqual((out["action"], out["sha"]), ("deploying", SHA_A))
        self.assertEqual(out["attestation"]["sha"], SHA_A)
        # main moves on; B's checks have not run. A's green is not B's.
        self.sha = SHA_B
        self.main = tarball(tree(extra={"league/house.py": "# B\n"}), sha=SHA_B)
        out = self.updater(attest=attest).check()
        self.assertEqual(out["action"], "waiting")
        self.assertEqual(len(self.launched), 1)
        # An attestor that answers for the wrong commit has attested nothing.
        out = self.updater(attest=lambda sha: passed(SHA_A)).check()
        self.assertEqual(out["action"], "blocked")
        self.assertEqual(len(self.launched), 1)
        # A tarball that is not of the attested commit is not unpacked at all.
        self.main = tarball(tree(extra={"league/house.py": "# B\n"}), sha=SHA_A)
        self.assertEqual(self.updater(attest=lambda sha: passed(sha)).check()["action"], "blocked")
        self.assertEqual(len(self.launched), 1)
        # B's own checks pass: B deploys, on B's attestation.
        self.main = tarball(tree(extra={"league/house.py": "# B\n"}), sha=SHA_B)
        approved.add(SHA_B)
        out = self.updater(attest=attest).check()
        self.assertEqual((out["action"], out["attestation"]["sha"]), ("deploying", SHA_B))

    def test_no_attestation_fails_closed_and_says_so_once(self):
        import urllib.error

        from league.updater import GitHubChecks

        def unreachable(request, timeout=None):
            raise urllib.error.URLError("[Errno -3] Temporary failure in name resolution")

        self.main = tarball(tree(extra={"league/house.py": "# new\n"}))
        updater = self.updater(attest=GitHubChecks(opener=unreachable))
        out = updater.check()
        self.assertEqual((out["action"], out["new"]), ("blocked", True))
        self.assertIn("floor_box.py hosts --add api.github.com", " ".join(out["reasons"]))
        self.assertEqual(self.launched, [])
        self.assertNotIn(out["release"], updater.tried())  # a blocked head is not a judged tree
        self.assertFalse(updater.check()["new"])            # told once, not every half hour
        boom = self.updater(attest=lambda sha: 1 / 0).check()
        self.assertEqual(boom["action"], "blocked")
        self.assertEqual(self.launched, [])
        # A head that cannot be read at all deploys nothing either.
        broken = Updater(self.base, head=lambda: "not-a-sha", fetch=lambda sha: self.main, launch=lambda *a: self.launched.append(a),
                         clock=self.clock, judge=lambda i, r: [], attest=self.attest)
        self.assertEqual(broken.check()["action"], "blocked")
        self.assertEqual(self.launched, [])

    def test_pending_checks_wait_quietly_then_tell_the_owner(self):
        self.main = tarball(tree(extra={"league/house.py": "# new\n"}))
        updater = self.updater(attest=lambda sha: judge_check_runs(sha, {"check_runs": []}))
        self.assertEqual((updater.check()["action"], updater.check()["new"]), ("waiting", False))
        self.clock.advance(2 * 3600 + 1)
        self.assertTrue(updater.check()["new"])

    def test_changed_workflows_are_refused_without_retiring_the_tree(self):
        self.main = tarball(tree(extra={".github/workflows/checks.yml": "name: Checks\njobs: {tests: {steps: [{run: 'true'}]}}\n",
                                        "league/house.py": "# new\n"}))
        updater = self.updater()
        out = updater.check()
        self.assertEqual(out["action"], "refused")
        self.assertIn(".github/workflows", " ".join(out["reasons"]))
        self.assertNotIn(out["release"], updater.tried())
        self.assertEqual(self.launched, [])

    def test_the_attestation_is_handed_to_the_watchdog(self):
        self.main = tarball(tree(extra={"league/house.py": "# new\n"}))
        records = []
        updater = Updater(self.base, head=lambda: self.sha, fetch=lambda sha: self.main, clock=self.clock, judge=lambda i, r: [],
                          attest=self.attest, launch=lambda source, rid, record=None: records.append(json.loads(record.read_text())),
                          workflows_pin=workflows_digest(tarball(tree())))
        out = updater.check()
        self.assertEqual(out["action"], "deploying")
        self.assertEqual(records[0]["sha"], SHA_A)
        self.assertEqual(records[0]["tree_digest"][:12], out["release"][len("main-"):])
        self.assertEqual({c["name"] for c in records[0]["checks"]}, set(REQUIRED_CHECKS))
        self.assertIn("ci_sha256", records[0]["trusted"])


class TheTrustedCheckerIsTheRunningCopy(unittest.TestCase):
    """The real subprocess, run from a trusted tree whose `league/ci.py` is a stub: whatever the
    candidate's own ci.py says, the verdict is the trusted copy's."""

    STUB = '''import json, sys
nonce = sys.stdin.readline().strip()
root = sys.argv[sys.argv.index("--root") + 1]
print("VERDICT", nonce, json.dumps({"passed": False, "problems": ["trusted judge refused " + root]}))
sys.exit(1)
'''

    def test_the_candidates_own_ci_is_never_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trusted = base / "trusted"
            (trusted / "league").mkdir(parents=True)
            (trusted / "league" / "__init__.py").write_text("")
            (trusted / "league" / "ci.py").write_text(self.STUB)
            candidate = base / "candidate"
            (candidate / "league").mkdir(parents=True)
            (candidate / "league" / "__init__.py").write_text("")
            (candidate / "league" / "ci.py").write_text("import sys\nprint('ci: passed')\nsys.exit(0)\n")
            problems = Updater(base, trusted=trusted)._judged_by_trusted(candidate, trusted)
            self.assertEqual(problems, [f"trusted judge refused {candidate.resolve()}"])

    def test_a_verdict_without_the_nonce_is_no_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            trusted = Path(tmp) / "trusted"
            (trusted / "league").mkdir(parents=True)
            (trusted / "league" / "__init__.py").write_text("")
            (trusted / "league" / "ci.py").write_text("print('VERDICT guessed {\"passed\": true, \"problems\": []}')\n")
            problems = Updater(Path(tmp), trusted=trusted)._judged_by_trusted(Path(tmp), trusted)
            self.assertEqual(len(problems), 1)
            self.assertIn("no verdict", problems[0])

    def test_the_real_trusted_checks_pass_this_repository(self):
        """The production path end to end: this checkout's ci.py, as its own process, judging this
        checkout as a candidate against itself."""
        repo = Path(__file__).resolve().parents[2]
        self.assertEqual(Updater(repo, trusted=repo)._judged_by_trusted(repo, repo), [])


class ThePinsFollowTheRepository(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def test_the_workflow_pin_is_the_workflows_in_this_checkout(self):
        from league.updater import checkout_workflows_digest

        if not (self.ROOT / ".github" / "workflows").is_dir():
            self.skipTest("a release tree carries no .github")
        self.assertEqual(checkout_workflows_digest(self.ROOT), TRUSTED_WORKFLOWS_SHA256,
                         "the workflows changed: set TRUSTED_WORKFLOWS_SHA256 in league/updater.py to the new digest. "
                         "A workflow change reaches the House box only as the owner's deploy.")

    def test_the_required_checks_are_jobs_of_the_checks_workflow(self):
        path = self.ROOT / ".github" / "workflows" / "checks.yml"
        if not path.exists():
            self.skipTest("a release tree carries no .github")
        text = path.read_text()
        self.assertIn("\n  gateway:\n", text)
        self.assertIn("\n  tests:\n", text)
        for name in REQUIRED_CHECKS:
            if name.startswith("tests ("):
                self.assertIn(f'"{name[len("tests ("):-1]}"', text)
        self.assertIn("workflow_dispatch", text)

    def test_the_head_is_read_from_a_ref_advertisement(self):
        from league.updater import resolve_head

        def line(text):
            return f"{len(text) + 4:04x}{text}"

        body = (line("# service=git-upload-pack\n") + "0000" + line(f"{SHA_B} HEAD\0multi_ack symref=HEAD:refs/heads/main\n")
                + line(f"{SHA_A} refs/heads/feature\n") + line(f"{SHA_B} refs/heads/main\n") + "0000").encode()

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        self.assertEqual(resolve_head(opener=lambda request, timeout=None: Response(body)), SHA_B)
        with self.assertRaises(UpdateError):
            resolve_head(opener=lambda request, timeout=None: Response((line(f"{SHA_A} refs/heads/other\n") + "0000").encode()))


class TheWatchdogRecordsTheAttestation(unittest.TestCase):
    def test_every_row_carries_the_sha_and_a_different_tree_is_refused(self):
        from league.watchdog import Health, Watchdog, tree_digest

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            releases = Releases(base)
            source = base / "src"
            unpack(tarball(tree()), source)
            releases.stage(source, "first-release")
            releases.promote("first-release")
            candidate = base / "cand"
            unpack(tarball(tree(extra={"league/house.py": "# new\n"})), candidate)
            dog = Watchdog(releases, run_canary=lambda *a: Health(True), restart_house=lambda: None,
                           read_house_health=lambda: Health(True), sleep=lambda s: None)
            digest = tree_digest(candidate)[0]
            attestation = {"sha": SHA_A, "tree_digest": digest, "state": "passed"}
            out = dog.deploy(candidate, "main-candidate1", watch_seconds=0, attestation=attestation)
            self.assertEqual(out["verdict"], "promoted")
            rows = [r for r in releases.history() if r.get("release") == "main-candidate1"]
            self.assertTrue(rows and all(r.get("sha") == SHA_A for r in rows))
            self.assertEqual(next(r for r in rows if r["stage"] == "start")["attestation"]["sha"], SHA_A)
            other = base / "other"
            unpack(tarball(tree(extra={"league/house.py": "# other\n"})), other)
            out = dog.deploy(other, "main-candidate2", watch_seconds=0, attestation=attestation)
            self.assertEqual(out["verdict"], "refused")
            self.assertIn("not the attested one", " ".join(out["reasons"]))
