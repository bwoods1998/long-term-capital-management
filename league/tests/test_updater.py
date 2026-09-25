import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from league.tests.fakes import Clock
from league.updater import (REQUIRED_CHECKS, TRUSTED_WORKFLOWS_SHA256, UpdateError, Updater, judge_workflow_runs, unpack,
                            workflows_digest)
from league.watchdog import Releases

SHA_A = "a" * 40
SHA_B = "b" * 40
#: The workflows every synthetic main carries: the pin a test Updater trusts is computed from them.
WORKFLOWS = {".github/workflows/checks.yml": "name: Checks\n"}


def run(sha, *, id=1, event="push", status="completed", conclusion="success", path=".github/workflows/checks.yml", branch="main"):
    return {"id": id, "head_sha": sha, "event": event, "status": status, "conclusion": conclusion, "path": path, "head_branch": branch,
            "run_attempt": 1}


def jobs(sha, *, conclusion="success", names=REQUIRED_CHECKS):
    return {"jobs": [{"id": 100 + i, "name": name, "head_sha": sha, "status": "completed", "conclusion": conclusion}
                     for i, name in enumerate(names)]}


def passed(sha):
    """GitHub's answer for a commit whose Checks run and every required job of it succeeded."""
    return judge_workflow_runs(sha, {"workflow_runs": [run(sha)]}, lambda run_id: jobs(sha))


def nothing_yet(sha):
    return judge_workflow_runs(sha, {"workflow_runs": []}, lambda run_id: {"jobs": []})

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
        self.releases = Releases(self.base, clock=self.clock)
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
        self.releases.record({"release": release_id, "stage": "verdict", "verdict": "refused",
                              "reasons": ["canary: the alpaca-paper book is frozen"]})
        self.assertIn(release_id, updater.tried())
        self.assertEqual(updater.check()["action"], "none")
        self.assertEqual(len(self.launched), 1)
        # A release rolled back once is not retired (the release train retries it once, at the next
        # train: `TheReleaseTrain`); rolled back twice, it is.
        self.releases.record({"release": "main-twice", "stage": "start"})
        self.releases.record({"release": "main-twice", "stage": "verdict", "verdict": "rolled_back"})
        self.assertNotIn("main-twice", updater.tried())
        self.releases.record({"release": "main-twice", "stage": "start"})
        self.releases.record({"release": "main-twice", "stage": "verdict", "verdict": "rolled_back"})
        self.assertIn("main-twice", updater.tried())


class ExactCommitAttestation(UpdaterCase):
    """GitHub's check runs on the exact commit, or nothing deploys."""

    def test_only_a_real_run_of_the_pinned_workflow_on_this_sha_counts(self):
        judge = lambda runs, listed=None: judge_workflow_runs(SHA_A, {"workflow_runs": runs},  # noqa: E731
                                                              lambda run_id: listed if listed is not None else jobs(SHA_A))
        self.assertEqual(judge([run(SHA_A)])["state"], "passed")
        self.assertEqual(judge([run(SHA_A, event="workflow_dispatch")])["state"], "passed")
        self.assertEqual(judge([run(SHA_A, event="schedule")])["state"], "passed")
        # Another commit's green, a pull request's preview, another workflow, another branch: none of them.
        self.assertEqual(judge([run(SHA_B)])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, event="pull_request")])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, event="pull_request_target")])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, path=".github/workflows/evil.yml")])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, branch="feature")])["state"], "pending")
        # A green run whose jobs are not the required ones, or not on this sha, is a failure:
        # check runs created through the API by some other workflow are not jobs of this run.
        self.assertEqual(judge([run(SHA_A)], jobs(SHA_A, names=("tests (3.11)",)))["state"], "failed")
        self.assertEqual(judge([run(SHA_A)], jobs(SHA_B))["state"], "failed")
        self.assertEqual(judge([run(SHA_A)], jobs(SHA_A, conclusion="skipped"))["state"], "failed")
        # The newest run with a verdict decides: a later failure blocks, a later success (a re-run,
        # the hourly run) clears a flaky one; a newer run still going is waited for; a cancelled
        # or skipped run says nothing.
        self.assertEqual(judge([run(SHA_A, id=1), run(SHA_A, id=2, conclusion="failure")])["state"], "failed")
        self.assertEqual(judge([run(SHA_A, id=1, conclusion="failure"), run(SHA_A, id=2)])["state"], "passed")
        self.assertEqual(judge([run(SHA_A, id=1), run(SHA_A, id=2, status="in_progress", conclusion=None)])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, id=2), run(SHA_A, id=1, status="in_progress", conclusion=None)])["state"], "passed")
        self.assertEqual(judge([run(SHA_A, status="in_progress", conclusion=None)])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, conclusion="cancelled")])["state"], "pending")
        self.assertEqual(judge([run(SHA_A, id=1, conclusion="cancelled"), run(SHA_A, id=2)])["state"], "passed")
        self.assertEqual(judge([run(SHA_A, id=1), run(SHA_A, id=2, conclusion="cancelled")])["state"], "passed")
        self.assertEqual(judge([run(SHA_A, id=1, conclusion="timed_out")])["state"], "failed")

    def test_a_later_head_never_inherits_an_earlier_heads_approval(self):
        approved = {SHA_A}
        attest = lambda sha: passed(sha) if sha in approved else nothing_yet(sha)  # noqa: E731
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

    def test_the_production_attestor_reads_the_run_then_its_jobs(self):
        import email.message
        import urllib.error

        from league.updater import GitHubChecks

        asked = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(request, timeout=None):
            asked.append(request.full_url)
            if "/jobs" in request.full_url:
                return Response(json.dumps(jobs(SHA_A)).encode())
            return Response(json.dumps({"workflow_runs": [run(SHA_A, id=77)]}).encode())

        out = GitHubChecks(opener=opener)(SHA_A)
        self.assertEqual((out["state"], out["run"]["id"]), ("passed", 77))
        self.assertIn(f"actions/runs?head_sha={SHA_A}", asked[0])
        self.assertIn("actions/runs/77/jobs", asked[1])

        def limited(request, timeout=None):
            headers = email.message.Message()
            headers["X-RateLimit-Remaining"] = "0"
            raise urllib.error.HTTPError(request.full_url, 403, "rate limited", headers, None)

        out = GitHubChecks(opener=limited)(SHA_A)
        self.assertEqual(out["state"], "unavailable")
        self.assertIn("rate limit", out["reasons"][0])

    def test_pending_checks_wait_quietly_then_tell_the_owner(self):
        self.main = tarball(tree(extra={"league/house.py": "# new\n"}))
        updater = self.updater(attest=nothing_yet)
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


class AnUnreadableAttestationIsNoAttestation(unittest.TestCase):
    def test_the_watchdog_refuses_without_retiring_the_tree(self):
        from league import watchdog
        from league.updater import Updater as U

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            import contextlib

            with contextlib.redirect_stdout(io.StringIO()):
                code = watchdog.main(["deploy", "--base", str(base), "--source", str(base / "nowhere"), "--id", "main-abcdef123456",
                                      "--attestation", str(base / "missing.json")])
            self.assertEqual(code, watchdog.EXIT_CODES["refused"])
            rows = Releases(base).history()
            self.assertEqual(rows[-1]["verdict"], "refused")
            self.assertNotIn("main-abcdef123456", U(base).tried())


def utc(text: str) -> float:
    from datetime import datetime, timezone

    return datetime.strptime(text, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()


class TheReleaseTrain(unittest.TestCase):
    """H3 of the forward-first run (Sept 25, 2026): the House restarted 26 times in the 24 hours to
    04:23Z (24-37 a day Sept 20-24), seven of them inside the Sept 24 US session, and each restart
    kills the research and wakes in flight. The updater shipped main whenever it had a green run: at
    21:16, 22:21, 23:00, 23:39, 00:38 and 01:14Z that night. Now a head that may ship waits for the
    train (one every `release_train_hours`), for the end of the session on a trading day, and for 30
    quiet minutes after a start; it says why and when, once per head per reason."""

    # UpdaterCase's fixture, not its tests (a subclass would run them all again).
    attest, updater = UpdaterCase.attest, UpdaterCase.updater

    def setUp(self):
        UpdaterCase.setUp(self)
        self.main = tarball(tree(extra={"league/house.py": "# the house, improved\n"}))
        self.ledger = None

    def tearDown(self):
        if self.ledger is not None:
            self.ledger.close()
        UpdaterCase.tearDown(self)

    def at(self, text):
        self.clock.now = utc(text)

    def started(self):
        """The House's `ops.started`, on the ledger the updater reads read-only (`<base>/state`)."""
        from league.ledger import Ledger

        if self.ledger is None:
            (self.base / "state").mkdir(exist_ok=True)
            self.ledger = Ledger(self.base / "state" / "ledger.sqlite", clock=self.clock)
        self.ledger.append("ops.started", {"release": "first-release"})

    def shipped(self, release_id, sha=SHA_B, *, verdict="promoted", promoted=True):
        """The rows `Watchdog._deploy` writes for an attested (updater) deploy, at the clock's time."""
        base = {"deploy": f"{release_id}@{int(self.clock())}", "release": release_id, "sha": sha}
        self.releases.record({**base, "stage": "start", "attestation": {"sha": sha}})
        self.releases.record({**base, "stage": "canary", "ok": True})
        if promoted:
            self.releases.record({**base, "stage": "promote", "ok": True})
        self.releases.record({**base, "stage": "verdict", "verdict": verdict})

    def train_rows(self):
        return [row for row in self.releases.history() if row.get("stage") == "train"]

    def test_a_head_inside_the_us_session_waits_for_its_close(self):
        self.at("2026-09-24T15:00Z")  # a Thursday; the session is 13:30-20:00Z
        updater = self.updater()
        out = updater.check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["session"], []))
        self.assertEqual(out["next_eligible_at"], "2026-09-24T20:05:00Z")
        self.assertIn("2026-09-24 is a trading day", " ".join(out["reasons"]))
        self.assertIn("next eligible 2026-09-24T20:05:00Z", out["reasons"])
        self.assertEqual(list((self.base / "incoming").iterdir()), [])
        self.at("2026-09-24T20:04Z")
        self.assertEqual(updater.check()["action"], "held")
        self.at("2026-09-24T20:05Z")
        self.assertEqual(updater.check()["action"], "deploying")

    def test_a_launch_that_would_restart_the_house_inside_the_session_waits_too(self):
        # The canary took 2.2-4.0 minutes from launch to restart on Sept 24-25, then a ten-minute
        # watch that may roll back: a launch at 13:00Z restarts the House inside the session.
        self.at("2026-09-24T13:00Z")
        self.assertEqual(self.updater().check()["holds"], ["session"])
        self.at("2026-09-24T12:54Z")
        self.assertEqual(self.updater().check()["action"], "deploying")

    def test_the_winter_session_is_the_calendars_own_hours(self):
        # December: EST, the session 14:30-21:00Z. The window is its own, five minutes each side.
        self.at("2026-12-01T20:30Z")
        out = self.updater().check()
        self.assertEqual((out["action"], out["next_eligible_at"]), ("held", "2026-12-01T21:05:00Z"))

    def test_a_weekend_and_an_nyse_holiday_are_not_a_session(self):
        for moment in ("2026-09-26T15:00Z", "2026-09-27T15:00Z", "2026-09-07T15:00Z", "2026-11-26T15:00Z"):
            # Saturday, Sunday, Labor Day, Thanksgiving: the House's calendar calls them closed.
            with self.subTest(moment=moment):
                self.launched.clear()
                self.at(moment)
                self.assertEqual(self.updater().check()["action"], "deploying")
                self.assertEqual(len(self.launched), 1)

    def test_a_head_three_hours_after_the_last_ship_waits_for_the_train(self):
        self.at("2026-09-24T21:00Z")
        self.shipped("main-000000000001")
        self.at("2026-09-25T00:00Z")
        updater = self.updater()
        out = updater.check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["train"], []))
        self.assertEqual(out["next_eligible_at"], "2026-09-25T01:00:00Z")
        self.assertIn("main-000000000001 (promoted)", out["reasons"][0])
        self.at("2026-09-25T01:00Z")
        self.assertEqual(updater.check()["action"], "deploying")

    def test_the_train_is_the_running_releases_dial_inside_the_checkers_bounds(self):
        from league import ci
        from league.updater import RELEASE_TRAIN_HOURS, train_hours

        self.assertEqual(ci.CONFIG_DIALS["release_train_hours"], (2, 6))
        repository = Path(__file__).resolve().parents[2]
        self.assertEqual(json.loads((repository / "league" / "config.json").read_text())["release_train_hours"], RELEASE_TRAIN_HOURS)
        self.assertEqual(train_hours(repository), 4.0)
        trusted = self.base / "trusted"
        (trusted / "league").mkdir(parents=True)
        for value, hours in ((3, 3.0), (9, 6.0), (1, 2.0), ("x", 4.0), (None, 4.0)):
            config = {"real_money": False} if value is None else {"real_money": False, "release_train_hours": value}
            (trusted / "league" / "config.json").write_text(json.dumps(config))
            self.assertEqual(train_hours(trusted), hours, value)
        # Two hours: the same ship holds a head at 1 h and lets it go at 2 h.
        self.at("2026-09-26T02:00Z")
        self.shipped("main-000000000001")
        self.at("2026-09-26T03:00Z")
        (trusted / "league" / "config.json").write_text(json.dumps({"release_train_hours": 2}))
        updater = Updater(self.base, head=lambda: self.sha, fetch=lambda sha: self.main, trusted=trusted,
                          launch=lambda source, rid, record=None: self.launched.append((source, rid)), clock=self.clock,
                          judge=lambda incoming, running: [], attest=self.attest, workflows_pin=workflows_digest(tarball(tree())))
        self.assertEqual(updater.check()["next_eligible_at"], "2026-09-26T04:00:00Z")
        # And the operator's checker holds a pull request to the same bounds.
        (trusted / "league" / "config.json").write_text(json.dumps({"real_money": False, "release_train_hours": 7}))
        self.assertIn("release_train_hours", " ".join(ci.check_config(None, trusted)))

    def test_a_head_twenty_minutes_after_a_start_waits(self):
        self.at("2026-09-26T10:00Z")
        self.started()
        self.at("2026-09-26T10:20Z")
        updater = self.updater()
        out = updater.check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["recent_start"], []))
        self.assertEqual(out["next_eligible_at"], "2026-09-26T10:30:00Z")
        self.assertIn("the House started at 2026-09-26T10:00:00Z", out["reasons"][0])
        self.at("2026-09-26T10:30Z")
        self.assertEqual(updater.check()["action"], "deploying")

    def test_a_head_outside_all_three_ships(self):
        self.at("2026-09-25T00:00Z")
        self.shipped("main-000000000001")
        self.at("2026-09-25T05:00Z")  # five hours on, before the Friday session's lead
        self.started()
        self.at("2026-09-25T06:00Z")  # an hour after the House started
        out = self.updater().check()
        self.assertEqual(out["action"], "deploying")
        self.assertEqual(len(self.launched), 1)

    def test_the_next_eligible_time_clears_every_hold(self):
        # A ship at 11:00Z on a trading day: the train lifts at 15:00Z, inside the session, so the
        # next release is the session's end, not the train's.
        self.at("2026-09-24T11:00Z")
        self.shipped("main-000000000001")
        self.at("2026-09-24T12:00Z")
        out = self.updater().check()
        self.assertEqual((out["holds"], out["next_eligible_at"]), (["train"], "2026-09-24T20:05:00Z"))
        self.at("2026-09-24T14:00Z")
        self.started()
        self.at("2026-09-24T14:10Z")
        out = self.updater().check()
        self.assertEqual((sorted(out["holds"]), out["next_eligible_at"]), (["recent_start", "session", "train"], "2026-09-24T20:05:00Z"))

    def test_a_protected_head_is_still_refused_at_once(self):
        self.at("2026-09-24T15:00Z")  # inside the session and the train: the refusal does not wait
        self.shipped("main-000000000001")
        self.main = tarball(tree(extra={"league/constitution.py": "MONEY = 'mine'\n"}))
        out = self.updater().check()
        self.assertEqual(out["action"], "refused")
        self.assertIn("league/constitution.py", " ".join(out["reasons"]))
        self.assertIn("owner's deploy", " ".join(out["reasons"]))
        self.assertEqual((self.launched, self.train_rows()), ([], []))

    def test_a_held_head_is_judged_once_when_it_goes_not_at_every_look(self):
        judged = []
        self.at("2026-09-24T15:00Z")
        updater = self.updater(judge=lambda incoming, running: judged.append(incoming) or [])
        updater.check()
        updater.check()
        self.assertEqual(judged, [])
        self.at("2026-09-24T20:10Z")
        self.assertEqual(updater.check()["action"], "deploying")
        self.assertEqual(len(judged), 1)

    def test_a_skip_is_told_once_per_head_per_reason_across_restarts(self):
        self.at("2026-09-24T15:00Z")
        updater = self.updater()
        self.assertTrue(updater.check()["new"])
        self.assertFalse(updater.check()["new"])
        self.assertFalse(self.updater().check()["new"])  # a restarted House reads deploys.jsonl
        rows = self.train_rows()
        self.assertEqual([(r["sha"], r["holds"], r["verdict"], r.get("unjudged")) for r in rows], [(SHA_A, ["session"], "held", True)])
        self.assertEqual(rows[0]["next_eligible_at"], "2026-09-24T20:05:00Z")
        # A new reason for the same head is told once more; a new head is told afresh.
        self.shipped("main-000000000001")
        self.assertTrue(self.updater().check()["new"])
        self.assertFalse(self.updater().check()["new"])
        self.sha = "c" * 40
        self.main = tarball(tree(extra={"league/house.py": "# the house, improved twice\n"}), sha=self.sha)
        self.assertTrue(self.updater().check()["new"])
        self.assertEqual(len(self.train_rows()), 3)
        held = {row["release"] for row in self.train_rows()}
        self.assertEqual(len(held), 2)
        self.assertEqual(held & self.updater().tried(), set())  # a held head is never retired

    def test_the_house_writes_one_row_per_new_hold_and_no_warning(self):
        """`House._update` (unchanged) writes `ops.deploy` when `new` and alerts only a refusal, a
        block or a wait: a held head is a row with its reasons, not an alert."""
        from types import SimpleNamespace

        from league.house import House

        self.at("2026-09-24T15:00Z")
        rows, alerts = [], []
        house = SimpleNamespace(updater=self.updater(), ledger=SimpleNamespace(append=lambda kind, payload: rows.append((kind, payload))),
                                alert=lambda level, text: alerts.append(level), _state={}, _state_lock=__import__("threading").Lock(), clock=self.clock)
        House._update(house)
        House._update(house)
        self.assertEqual([(kind, payload["action"]) for kind, payload in rows], [("ops.deploy", "held")])
        self.assertIn("next eligible 2026-09-24T20:05:00Z", rows[0][1]["reasons"])
        self.assertEqual((alerts, house._state), ([], {}))

    def test_the_sites_news_calls_a_held_head_a_wait_not_a_refusal(self):
        from league.publish import league_news

        self.at("2026-09-24T15:00Z")
        out = self.updater().check()
        payload = {k: v for k, v in out.items() if k in ("action", "release", "reasons", "files", "sha", "attestation")}  # House._update's row
        news = league_news("ops.deploy", "house", payload)
        self.assertIn("waits for the release train", news)
        self.assertIn("next eligible 2026-09-24T20:05:00Z", news)
        self.assertNotIn("refused", news)

    def test_a_rolled_back_attempt_counts_for_the_train_and_is_retried_once(self):
        self.at("2026-09-26T02:00Z")
        updater = self.updater()
        self.assertEqual(updater.check()["action"], "deploying")
        _, release_id = self.launched[0]
        self.shipped(release_id, SHA_A, verdict="rolled_back")
        self.at("2026-09-26T03:00Z")
        out = updater.check()
        self.assertEqual((out["action"], out["holds"]), ("held", ["train"]))
        self.assertIn("(rolled_back)", out["reasons"][0])
        self.at("2026-09-26T06:00Z")
        self.assertEqual(updater.check()["action"], "deploying")  # the same tree, once more
        self.assertEqual([rid for _, rid in self.launched], [release_id, release_id])
        self.shipped(release_id, SHA_A, verdict="rolled_back")
        self.at("2026-09-26T11:00Z")
        self.assertEqual(updater.check()["action"], "none")  # twice rolled back: retired
        self.assertEqual(len(self.launched), 2)

    def test_a_canary_refusal_restarted_nothing_and_does_not_hold_the_train(self):
        self.at("2026-09-26T02:00Z")
        self.shipped("main-000000000001", verdict="refused", promoted=False)
        self.at("2026-09-26T02:30Z")
        self.assertEqual(self.updater().check()["action"], "deploying")

    def test_an_owner_deploy_is_not_a_train_ship_but_its_start_is_a_start(self):
        self.at("2026-09-26T02:00Z")
        base = {"deploy": "20260926T020000Z-abc@1", "release": "20260926T020000Z-abc"}  # no sha: floor_box.py's
        for stage in ("start", "promote", "verdict"):
            self.releases.record({**base, "stage": stage, "ok": True, "verdict": "promoted"})
        self.started()
        self.at("2026-09-26T02:40Z")
        self.assertEqual(self.updater().check()["action"], "deploying")

    def test_an_in_flight_deploy_holds_the_next_head(self):
        self.at("2026-09-26T02:00Z")
        self.releases.record({"deploy": "main-000000000001@1", "release": "main-000000000001", "sha": SHA_B, "stage": "start"})
        self.at("2026-09-26T02:05Z")
        self.assertEqual(self.updater().check()["holds"], ["train"])

    def test_the_next_look_is_when_the_hold_lifts(self):
        self.at("2026-09-24T19:50Z")
        updater = self.updater()
        self.assertEqual(updater.check()["action"], "held")
        self.at("2026-09-24T20:00Z")
        self.assertFalse(updater.due())
        self.at("2026-09-24T20:05Z")
        self.assertTrue(updater.due())  # fifteen minutes on, not thirty
        self.assertEqual(updater.check()["action"], "deploying")
        self.at("2026-09-24T20:10Z")
        self.assertFalse(updater.due())

    def test_the_calendar_is_the_houses(self):
        from league import house, updater

        self.assertIs(updater.us_equity_session, house.us_equity_session)

    def test_an_unreadable_ledger_holds_as_a_fresh_start(self):
        self.at("2026-09-26T10:00Z")
        (self.base / "state").mkdir()
        (self.base / "state" / "ledger.sqlite").write_bytes(b"not a database, " * 64)
        out = self.updater().check()
        self.assertEqual((out["action"], out["holds"]), ("held", ["recent_start"]))
        self.assertIn("the ledger could not be read", out["reasons"][0])
