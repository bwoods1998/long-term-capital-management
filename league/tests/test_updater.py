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


#: The file these tests change to make a new release: research-class (the engineer's scheduler lane), so the release
#: train ships it. The House's own file is the owner's deploy since the WP8 review: `ci.FORBIDDEN` holds everything the
#: gateway's merge route protects (league/tests/test_ci.py), league/house.py among it.
SHIPS = "league/swarm/loop.py"


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
        self.main = tarball(tree(extra={SHIPS: "# the loop, improved\n"}))
        updater = self.updater()
        out = updater.check()
        self.assertEqual(out["action"], "deploying")
        source, release_id = self.launched[0]
        self.assertTrue(release_id.startswith("main-"))
        self.assertEqual((source / SHIPS).read_text(), "# the loop, improved\n")
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
        # And, since the WP8 review, what the gateway's merge route protects besides (one list: league/tests/test_ci.py):
        # the House itself, its job framework, what the Gym and the decider seal, the harness loop's objective.
        for path in ("league/house.py", "league/ops/jobs.py", "league/structure_core.py", "league/swarm/harness_lanes.py",
                     "league/budget.py", "scripts/floor_box.py"):
            self.main = tarball(tree(extra={path: "# changed\n"}))
            out = self.updater().check()
            self.assertEqual(out["action"], "refused", path)
            self.assertIn(path, " ".join(out["reasons"]))
            self.assertIn("owner's deploy", " ".join(out["reasons"]))
        self.assertEqual(self.launched, [])

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
        self.main = tarball(tree(extra={SHIPS: "# the loop, improved\n"}))
        updater = self.updater()
        self.assertEqual(updater.check()["action"], "deploying")
        _, release_id = self.launched[0]
        self.releases.record({"release": release_id, "stage": "verdict", "verdict": "refused", "busy": True,
                              "reasons": ["another deploy or rollback is running (pid 123)"]})
        self.assertNotIn(release_id, updater.tried())
        self.assertEqual(updater.check()["action"], "deploying")   # the same content, offered again
        self.assertEqual(len(self.launched), 2)

    def test_a_release_the_watchdog_really_judged_is_not_offered_again(self):
        self.main = tarball(tree(extra={SHIPS: "# the loop, improved\n"}))
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

    def test_a_revert_to_a_tree_promoted_before_is_deployed_again(self):
        """main-A promoted, then main-B (it passed its watch, but is bad); the engineer reverts B, so main's tree is A's
        again. That revert is the way back: it must not be answered "already tried" while the box runs B."""
        loop_a, loop_b = "# the loop, improved\n", "# the loop, improved again\n"

        def ship(text):
            self.main = tarball(tree(extra={SHIPS: text}))
            out = updater.check()
            self.assertEqual(out["action"], "deploying", out)
            source, release_id = self.launched[-1]
            if release_id not in [row["id"] for row in self.releases.list()]:
                self.releases.stage(source, release_id)
            self.releases.promote(release_id)
            self.releases.record({"release": release_id, "stage": "start"})
            self.releases.record({"release": release_id, "stage": "verdict", "verdict": "promoted"})
            return release_id

        updater = self.updater()
        rid_a = ship(loop_a)
        self.assertIn(rid_a, updater.tried())  # it is what runs
        rid_b = ship(loop_b)
        self.assertNotIn(rid_a, updater.tried())
        self.assertEqual(ship(loop_a), rid_a)  # the revert ships
        self.assertEqual(self.releases.current(), rid_a)
        self.assertEqual(len(self.launched), 3)
        # Once anything rolled back FROM a tree (the owner's rollback, or a watch's), it stays retired.
        self.releases.record({"deploy": "rollback@1", "release": rid_b, "stage": "rollback", "ok": True, "from": rid_b, "to": "x"})
        self.assertIn(rid_b, updater.tried())

    def test_a_tree_promoted_before_stays_retired_while_the_box_runs_the_owners_release(self):
        """main may lag what the owner deployed by hand: the owner's release is never replaced by a tree main had before."""
        self.releases.record({"release": "main-aaaaaaaaaaaa", "stage": "start"})
        self.releases.record({"release": "main-aaaaaaaaaaaa", "stage": "verdict", "verdict": "promoted"})
        self.assertEqual(self.releases.current(), "first-release")
        self.assertIn("main-aaaaaaaaaaaa", self.updater().tried())


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
        self.main = tarball(tree(extra={SHIPS: "# A\n"}), sha=SHA_A)
        out = self.updater(attest=attest).check()
        self.assertEqual((out["action"], out["sha"]), ("deploying", SHA_A))
        self.assertEqual(out["attestation"]["sha"], SHA_A)
        # main moves on; B's checks have not run. A's green is not B's.
        self.sha = SHA_B
        self.main = tarball(tree(extra={SHIPS: "# B\n"}), sha=SHA_B)
        out = self.updater(attest=attest).check()
        self.assertEqual(out["action"], "waiting")
        self.assertEqual(len(self.launched), 1)
        # An attestor that answers for the wrong commit has attested nothing.
        out = self.updater(attest=lambda sha: passed(SHA_A)).check()
        self.assertEqual(out["action"], "blocked")
        self.assertEqual(len(self.launched), 1)
        # A tarball that is not of the attested commit is not unpacked at all.
        self.main = tarball(tree(extra={SHIPS: "# B\n"}), sha=SHA_A)
        self.assertEqual(self.updater(attest=lambda sha: passed(sha)).check()["action"], "blocked")
        self.assertEqual(len(self.launched), 1)
        # B's own checks pass: B deploys, on B's attestation.
        self.main = tarball(tree(extra={SHIPS: "# B\n"}), sha=SHA_B)
        approved.add(SHA_B)
        out = self.updater(attest=attest).check()
        self.assertEqual((out["action"], out["attestation"]["sha"]), ("deploying", SHA_B))

    def test_no_attestation_fails_closed_and_says_so_once(self):
        import urllib.error

        from league.updater import GitHubChecks

        def unreachable(request, timeout=None):
            raise urllib.error.URLError("[Errno -3] Temporary failure in name resolution")

        self.main = tarball(tree(extra={SHIPS: "# new\n"}))
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
        self.main = tarball(tree(extra={SHIPS: "# new\n"}))
        updater = self.updater(attest=nothing_yet)
        self.assertEqual((updater.check()["action"], updater.check()["new"]), ("waiting", False))
        self.clock.advance(2 * 3600 + 1)
        self.assertTrue(updater.check()["new"])

    def test_changed_workflows_are_refused_without_retiring_the_tree(self):
        self.main = tarball(tree(extra={".github/workflows/checks.yml": "name: Checks\njobs: {tests: {steps: [{run: 'true'}]}}\n",
                                        SHIPS: "# new\n"}))
        updater = self.updater()
        out = updater.check()
        self.assertEqual(out["action"], "refused")
        self.assertIn(".github/workflows", " ".join(out["reasons"]))
        self.assertNotIn(out["release"], updater.tried())
        self.assertEqual(self.launched, [])

    def test_the_attestation_is_handed_to_the_watchdog(self):
        self.main = tarball(tree(extra={SHIPS: "# new\n"}))
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

    def test_the_tests_job_is_never_cut_off_by_its_own_time_limit(self):
        """A run its own limit cancels is no verdict (`judge_workflow_runs`), so a head whose tests outrun the limit is
        never attested. Sept 29-30, 2026: the league's tests alone took up to 17m49s and two 3.11 jobs hit the
        20-minute limit (PR run 36578499862; push run 36689802805 on f082cf5e). The limit keeps a wide margin."""
        import re

        path = self.ROOT / ".github" / "workflows" / "checks.yml"
        if not path.exists():
            self.skipTest("a release tree carries no .github")
        job = path.read_text().split("\n  tests:\n", 1)[1].split("\n    steps:\n", 1)[0]
        limit = re.search(r"^    timeout-minutes: (\d+)$", job, re.MULTILINE)
        self.assertIsNotNone(limit, "the tests job states its own time limit")
        self.assertGreaterEqual(int(limit.group(1)), 30)

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
            unpack(tarball(tree(extra={SHIPS: "# new\n"})), candidate)
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
            unpack(tarball(tree(extra={SHIPS: "# other\n"})), other)
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
        self.main = tarball(tree(extra={SHIPS: "# the loop, improved\n"}))
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
        self.main = tarball(tree(extra={SHIPS: "# the loop, improved twice\n"}), sha=self.sha)
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
        # Not a look at main: only at the nightly stop the launch wrote (V3-A), which is lifted once no
        # deploy is in flight -- this fixture's launch starts none.
        self.assertTrue(updater.due())
        self.assertEqual(updater.check(), {"action": "none", "reason": "looked only at the nightly stop",
                                           "nightly_resumed": f"updater:{self.launched[0][1]}"})
        self.at("2026-09-24T20:12Z")
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


class TheNightlyDaemonStopsFirst(unittest.TestCase):
    """V3-A (WP1): the owner's release procedure stops the nightly forward daemon before a deploy so a
    release change never lands mid-job, and lifts the stop after the verdict. The updater does the same:
    `<state>/data/nightly.stop` with `updater:<release-id>`, a launch only once `nightly.lock` is free
    (asked look by look, at most ten minutes), the stop lifted once no deploy is in flight, and only if
    it still carries the marker."""

    attest = UpdaterCase.attest

    def setUp(self):
        UpdaterCase.setUp(self)
        self.main = tarball(tree(extra={SHIPS: "# the loop, improved\n"}))
        self.clock.now = utc("2026-09-26T02:00Z")  # a Saturday: no session, no train, no start
        self.flight: str | None = None
        self.data = self.base / "state" / "data"
        self.data.mkdir(parents=True)
        self.held_lock = None

    def tearDown(self):
        self.release_lock()
        UpdaterCase.tearDown(self)

    def updater(self, **kw):
        return Updater(self.base, head=lambda: self.sha, fetch=lambda sha: self.main,
                       launch=lambda source, rid, record=None: self.launched.append((source, rid)),
                       clock=self.clock, judge=kw.pop("judge", lambda incoming, running: []), attest=self.attest,
                       workflows_pin=workflows_digest(tarball(tree())), in_flight=lambda: self.flight, **kw)

    def hold_lock(self, **beat):
        """The daemon's lifetime lock, held as `scripts/data/locking.py` `process_lock` holds it, and its
        heartbeat (`scripts/data/nightly.py daemon`): by default idle, its next job hours off."""
        import fcntl

        self.held_lock = (self.data / "nightly.lock").open("a+")
        fcntl.flock(self.held_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.heartbeat(**beat)

    def heartbeat(self, **beat):
        from league.watchdog import iso

        beat = {"pid": 77, "start": "1", "release": "/workspace/releases/first-release", "at": self.clock(), "state": "waiting",
                "busy": False, "next_wake": iso(self.clock() + 4 * 3600), **beat}
        (self.data / "nightly.heartbeat").write_text(json.dumps(beat))

    def release_lock(self):
        if self.held_lock is not None:
            self.held_lock.close()
            self.held_lock = None

    def stop(self):
        path = self.data / "nightly.stop"
        return path.read_text().strip() if path.exists() else None

    def test_an_idle_daemon_is_stopped_and_the_head_launches_at_once(self):
        out = self.updater().check()
        self.assertEqual(out["action"], "deploying")
        release = self.launched[0][1]
        self.assertEqual(self.stop(), f"updater:{release}")
        self.assertEqual(out["nightly"], {"stop": f"updater:{release}", "waited_seconds": 0.0})

    def test_a_running_daemon_is_waited_for_look_by_look_then_the_head_launches(self):
        self.hold_lock()
        updater = self.updater()
        first = updater.check()
        self.assertEqual((first["action"], first["new"], self.launched), ("stopping_nightly", True, []))
        release = first["release"]
        self.assertEqual(self.stop(), f"updater:{release}")
        self.assertTrue((self.base / "incoming" / release).is_dir())
        self.clock.advance(10)
        self.assertFalse(updater.due())
        self.clock.advance(10)
        self.assertTrue(updater.due())  # twenty seconds on, not half an hour
        again = updater.check()
        self.assertEqual((again["action"], again["new"], self.launched), ("stopping_nightly", False, []))
        self.release_lock()
        self.clock.advance(20)
        self.assertTrue(updater.due())
        out = updater.check()
        self.assertEqual((out["action"], [rid for _, rid in self.launched]), ("deploying", [release]))
        self.assertEqual(out["nightly"]["waited_seconds"], 40.0)
        self.assertEqual(self.stop(), f"updater:{release}")  # held through the canary, the promotion and the watch

    def test_the_house_writes_one_row_for_the_wait_and_marks_the_deploy_only_at_the_launch(self):
        from types import SimpleNamespace

        from league.house import House

        self.hold_lock()
        rows, alerts = [], []
        house = SimpleNamespace(updater=self.updater(), ledger=SimpleNamespace(append=lambda kind, payload: rows.append((kind, payload))),
                                alert=lambda level, text, **payload: alerts.append(level), _state={},
                                _state_lock=__import__("threading").Lock(), clock=self.clock)
        House._update(house)
        self.clock.advance(20)
        House._update(house)
        self.assertEqual([(kind, payload["action"]) for kind, payload in rows], [("ops.deploy", "stopping_nightly")])
        self.assertEqual((alerts, house._state), ([], {}))
        self.release_lock()
        self.clock.advance(20)
        House._update(house)
        self.assertEqual([payload["action"] for _, payload in rows], ["stopping_nightly", "deploying"])
        self.assertEqual(house._state, {"deploying_at": self.clock()})

    def test_a_busy_daemon_is_never_stopped_mid_job(self):
        """The House's supervisor kills a stopped daemon two minutes on, busy or not: the stop waits for idle."""
        from league.watchdog import iso

        self.hold_lock(state="running", busy=True, day="2026-09-25")
        updater = self.updater()
        out = updater.check()
        self.assertEqual((out["action"], self.stop()), ("stopping_nightly", None))
        self.assertIn("running a job (2026-09-25)", out["reasons"][0])
        for beat in ({"state": "waiting", "busy": False, "next_wake": iso(self.clock() + 90)},   # its next job is due within a poll or two
                     {"state": "complete", "busy": False},                                     # a catch-up may follow
                     {"at": self.clock() - 200}):                                              # a heartbeat that says nothing now
            self.clock.advance(20)
            self.heartbeat(**beat)
            out = updater.check()
            self.assertEqual((out["action"], self.stop()), ("stopping_nightly", None), beat)
        self.clock.advance(20)
        self.heartbeat()
        self.assertEqual(updater.check()["action"], "stopping_nightly")
        self.assertEqual(self.stop(), f"updater:{out['release']}")  # idle now: stopped, and the lock still held
        self.release_lock()
        self.clock.advance(20)
        self.assertEqual(updater.check()["action"], "deploying")

    def test_a_daemon_that_does_not_stop_in_ten_minutes_holds_the_head_and_lifts_the_stop(self):
        self.hold_lock()
        updater = self.updater()
        release = updater.check()["release"]
        for _ in range(29):
            self.clock.advance(20)
            self.assertEqual(updater.check()["action"], "stopping_nightly")
        self.clock.advance(20)
        out = updater.check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["nightly"], []))
        self.assertIn("was not stopped within 10 minutes: the nightly data job has not let go of its lock", out["reasons"][0])
        self.assertIsNone(self.stop())
        self.assertFalse((self.base / "incoming" / release).exists())
        self.assertFalse((self.base / "incoming" / f"{release}.attestation.json").exists())
        self.assertNotIn(release, updater.tried())  # a moment's verdict, not the tree's
        self.release_lock()
        self.clock.advance(1800)
        self.assertEqual(updater.check()["action"], "deploying")

    def test_an_operators_own_stop_is_obeyed_and_never_lifted(self):
        (self.data / "nightly.stop").write_text("")
        updater = self.updater()
        out = updater.check()
        self.assertEqual((out["action"], out["nightly"]["stop"]), ("deploying", ""))
        self.clock.advance(120)
        self.assertFalse(updater.due())  # nobody's marker: nothing for the updater to lift
        self.assertIsNone(updater._settle_nightly())
        self.assertEqual(self.stop(), "")

    def test_the_stop_is_lifted_after_the_verdict_and_only_if_it_is_still_ours(self):
        updater = self.updater()
        updater.check()
        release = self.launched[0][1]
        self.flight = "a watchdog is running (pid 4242, deploy.pid)"
        self.clock.advance(61)
        self.assertTrue(updater.due())
        self.assertEqual(updater.check(), {"action": "none", "reason": "looked only at the nightly stop"})
        self.assertEqual(self.stop(), f"updater:{release}")  # the watch is still on
        self.flight = None
        self.clock.advance(61)
        self.assertTrue(updater.due())
        self.assertEqual(updater.check()["nightly_resumed"], f"updater:{release}")
        self.assertIsNone(self.stop())
        [row] = [r for r in self.releases.history() if r.get("stage") == "nightly"]
        self.assertEqual((row["action"], row["marker"], row["unjudged"]), ("resumed", f"updater:{release}", True))
        self.assertNotIn("release", row)
        # Somebody else's stop written over it in the meantime stays.
        (self.data / "nightly.stop").write_text("operator: by hand\n")
        self.clock.advance(61)
        self.assertFalse(updater.due())
        self.assertIsNone(updater._settle_nightly())
        self.assertEqual(self.stop(), "operator: by hand")

    def test_a_house_that_starts_after_a_crash_lifts_an_orphaned_stop(self):
        (self.data / "nightly.stop").write_text("updater:main-0123456789ab\n")
        self.flight = "a watchdog is running (pid 4242, deploy.pid)"
        self.sha = "github is out of reach"  # nothing else of the look matters here
        self.assertEqual(self.updater().check()["action"], "blocked")
        self.assertEqual(self.stop(), "updater:main-0123456789ab")  # a deploy is in flight: its verdict lifts it
        self.flight = None
        self.assertEqual(self.updater().check()["action"], "blocked")
        self.assertIsNone(self.stop())

    def test_a_drills_stop_is_the_drills_own_until_it_is_two_hours_old(self):
        import os

        path = self.data / "nightly.stop"
        path.write_text("drill:drill-20261003T150000Z\n")
        updater = self.updater()
        self.assertIsNone(updater._settle_nightly())
        old = path.stat().st_mtime - 2 * 3600 - 1
        os.utime(path, (old, old))
        self.assertEqual(updater._settle_nightly(), "drill:drill-20261003T150000Z")
        self.assertFalse(path.exists())

    def test_no_launch_beside_another_deploy(self):
        self.flight = "a watchdog is running (pid 4242, deploy.pid)"
        out = self.updater().check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["deploy"], []))
        self.assertIn("another deploy is in flight", out["reasons"][0])
        self.assertIsNone(self.stop())
        self.assertEqual([p.name for p in (self.base / "incoming").iterdir()], [])

    def test_a_deploy_that_begins_while_the_daemon_stops_holds_the_launch(self):
        self.hold_lock()
        updater = self.updater()
        updater.check()
        self.flight = "a watchdog is running (pid 4242, deploy.pid)"
        self.release_lock()
        self.clock.advance(20)
        out = updater.check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["deploy"], []))
        self.assertIsNone(self.stop())

    def test_a_session_that_begins_while_the_daemon_stops_holds_the_launch(self):
        self.clock.now = utc("2026-09-28T12:46Z")  # a Monday, 9 minutes before the session's lead begins
        self.hold_lock()
        updater = self.updater()
        self.assertEqual(updater.check()["action"], "stopping_nightly")
        self.clock.now = utc("2026-09-28T12:56Z")
        self.release_lock()
        out = updater.check()
        self.assertEqual((out["action"], out["holds"], self.launched), ("held", ["session"], []))
        self.assertIsNone(self.stop())

    def test_the_launch_scrubs_the_environment_and_writes_deploy_pid(self):
        import os
        from types import SimpleNamespace
        from unittest import mock

        from league import updater as module
        from league.watchdog import deploy_in_flight

        seen = {}

        def popen(argv, **kw):
            seen.update(argv=argv, **kw)
            return SimpleNamespace(pid=4242)

        secrets = {"GATEWAY_TOKEN": "g" * 40, "SAIL_API_KEY": "s" * 40, "CAPITAL_PUBLISH_TOKEN": "c" * 40, "PATH": "/usr/bin",
                   "HOME": "/root", "SSL_CERT_FILE": "/etc/ssl/cert.pem", "AWS_SECRET_ACCESS_KEY": "x" * 40}
        with mock.patch.dict(os.environ, secrets), mock.patch.object(module.subprocess, "Popen", popen):
            Updater(self.base, attest=self.attest)._launch(self.base / "incoming" / "main-0123456789ab", "main-0123456789ab")
        env = seen["env"]
        self.assertEqual({k: env.get(k) for k in ("PATH", "HOME", "SSL_CERT_FILE", "LEAGUE_ENV")},
                         {"PATH": "/usr/bin", "HOME": "/root", "SSL_CERT_FILE": "/etc/ssl/cert.pem", "LEAGUE_ENV": str(self.base / ".env")})
        for name in ("GATEWAY_TOKEN", "SAIL_API_KEY", "CAPITAL_PUBLISH_TOKEN", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(name, env)
        self.assertEqual(seen["argv"][1:4], ["-m", "league.watchdog", "deploy"])
        self.assertTrue(seen["start_new_session"])
        self.assertEqual((self.base / "deploy.pid").read_text(), "4242\n")
        self.assertEqual((self.base / "deploy.pid").stat().st_mode & 0o777, 0o600)
        # What floor_box's probe and the updater's own check read: a live watchdog under that pid.
        self.assertIn("pid 4242", deploy_in_flight(self.base, argv_of=lambda pid: ["python3", "-m", "league.watchdog", "deploy"]))
        self.assertIsNone(deploy_in_flight(self.base, argv_of=lambda pid: ["python3", "-m", "league", "run"]))
        self.assertIsNone(deploy_in_flight(self.base, argv_of=lambda pid: None))


    # ------------------------------------------------------------ review of V3-A (Oct 2)
    def test_a_night_that_keeps_failing_does_not_keep_releases_out(self):
        """A failing night is idle in `retry`, its next try at most 300 s off (`Controller.retry_seconds`), for
        as long as it fails: with a ten-minute margin no head ever launched."""
        self.hold_lock(state="retry", next_wake=None, retry_at=self.clock() + 300, error="RuntimeError: the data box is down")
        updater = self.updater()
        out = updater.check()
        self.assertEqual((out["action"], self.stop()), ("stopping_nightly", f"updater:{out['release']}"))
        self.release_lock()  # the supervisor TERMs it at the stop; it was sleeping, so nothing was cut short
        self.clock.advance(20)
        self.assertEqual(updater.check()["action"], "deploying")

    def test_a_daemon_that_keeps_every_release_out_for_hours_is_stopped_anyway_with_a_warning(self):
        from types import SimpleNamespace

        from league.house import House

        self.hold_lock(state="running", busy=True, day="2026-09-25")
        updater = self.updater()
        for _ in range(31):  # ten minutes of waiting, then held on `nightly`
            out = updater.check()
            self.clock.advance(20)
            self.heartbeat(state="running", busy=True, day="2026-09-25")
        self.assertEqual((out["action"], out["holds"], self.stop()), ("held", ["nightly"], None))
        self.clock.advance(6 * 3600)
        self.heartbeat(state="running", busy=True, day="2026-09-25")
        alerts = []
        house = SimpleNamespace(updater=updater, ledger=SimpleNamespace(append=lambda kind, payload: None),
                                alert=lambda level, text, **payload: alerts.append((level, text)), _state={},
                                _state_lock=__import__("threading").Lock(), clock=self.clock)
        House._update(house)
        self.assertEqual(self.stop(), f"updater:{out['release']}")  # written over a busy daemon
        self.release_lock()
        self.clock.advance(20)
        House._update(house)
        self.assertEqual([rid for _, rid in self.launched], [out["release"]])
        [(level, text)] = alerts
        self.assertEqual(level, "warning")
        self.assertIn("kept every updater release out since", text)
        self.assertIn("running a job (2026-09-25)", text)

    def test_a_held_head_is_judged_once_and_not_at_all_beside_a_deploy(self):
        judged = []
        self.flight = "a watchdog is running (pid 4242, deploy.pid)"
        updater = self.updater(judge=lambda incoming, running: judged.append(incoming.name) or [])
        self.assertEqual(updater.check()["holds"], ["deploy"])
        self.assertEqual(judged, [])  # the cheap question first
        self.flight = None
        self.hold_lock(state="running", busy=True, day="2026-09-25")
        self.clock.advance(1800)
        self.assertEqual(updater.check()["action"], "stopping_nightly")
        for _ in range(30):
            self.clock.advance(20)
            self.heartbeat(state="running", busy=True, day="2026-09-25")
            out = updater.check()
        self.assertEqual(out["holds"], ["nightly"])
        self.release_lock()
        self.clock.advance(1800)
        self.assertEqual(updater.check()["action"], "deploying")
        self.assertEqual(len(judged), 1)

    def test_spent_trees_in_incoming_are_swept_once_nothing_is_in_flight(self):
        from unittest import mock

        from league import updater as module

        incoming = self.base / "incoming"
        for name in ("main-0123456789ab", "drill-20261003T150000Z", "20261001T120000Z-0123456789ab"):
            (incoming / name / "league").mkdir(parents=True)
        (incoming / "main-0123456789ab.attestation.json").write_text("{}")
        updater = self.updater()
        self.flight = "a watchdog is running (pid 4242, deploy.pid)"
        with mock.patch.object(module, "INCOMING_STALE_SECONDS", -1):
            self.assertEqual(updater._sweep_incoming(), [])
            self.flight = None
            self.assertEqual(sorted(updater._sweep_incoming()), ["drill-20261003T150000Z", "main-0123456789ab", "main-0123456789ab.attestation.json"])
        self.assertEqual([p.name for p in incoming.iterdir()], ["20261001T120000Z-0123456789ab"])  # the owner's upload stays
        (incoming / "main-fedcba987654").mkdir()
        self.assertEqual(updater._sweep_incoming(), [])  # fresh: perhaps not launched yet
        self.assertEqual(updater._sweep_incoming(now=__import__("time").time() + 3601), ["main-fedcba987654"])

    def test_a_watchdog_that_exits_is_reaped(self):
        from types import SimpleNamespace

        polls = []
        done = SimpleNamespace(pid=1, poll=lambda: polls.append("done") or 0)
        going = SimpleNamespace(pid=2, poll=lambda: polls.append("going"))
        updater = self.updater()
        updater._children = [done, going]
        updater.due()
        self.assertEqual((polls, updater._children), (["done", "going"], [going]))


class TheDrillCopyBreaksItself(unittest.TestCase):
    """V3-A (WP1): a House started from a rollback drill's copy (`DRILL_BREAK` in a `drill-...` release)
    raises an error alert at every tick and never looks at main; any other release ignores the file."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = Path(self.dir.name)
        self.clock = Clock()

    def tearDown(self):
        self.dir.cleanup()

    def release(self, name, marker=True):
        root = self.base / "releases" / name
        (root / "league").mkdir(parents=True)
        if marker:
            (root / "DRILL_BREAK").write_text(json.dumps({"drill": name, "copy_of": "main-0123456789ab"}))
        return root

    def updater(self, trusted):
        def never(*_):
            raise AssertionError("a drill copy never looks at main")

        return Updater(self.base, trusted=trusted, head=never, fetch=never, attest=never, launch=never, clock=self.clock)

    def test_a_drill_copy_breaks_at_every_tick(self):
        from types import SimpleNamespace

        from league.house import House

        updater = self.updater(self.release("drill-20261003T150000Z"))
        rows, alerts = [], []
        house = SimpleNamespace(updater=updater, ledger=SimpleNamespace(append=lambda kind, payload: rows.append((kind, payload))),
                                alert=lambda level, text, **payload: alerts.append((level, text, payload)), _state={},
                                _state_lock=__import__("threading").Lock(), clock=self.clock)
        for _ in range(3):
            self.assertTrue(updater.due())
            House._update(house)
            self.clock.advance(30)
        self.assertEqual([level for level, _, _ in alerts], ["error"] * 3)
        self.assertTrue(alerts[0][1].startswith("drill: deliberate break"))
        self.assertIn("main-0123456789ab", alerts[0][1])
        self.assertEqual(alerts[0][2], {"drill": "drill-20261003T150000Z"})
        self.assertEqual((rows, house._state), ([], {}))

    def test_a_copy_whose_drill_died_launches_its_own_recovery_once(self):
        """The drill's process holds deploy.pid until its rollback restarted this House: a copy that sees no
        deploy in flight for fifteen minutes was left current by a drill that died."""
        import os
        from types import SimpleNamespace
        from unittest import mock

        from league import updater as module

        flight = ["a watchdog is running (pid 4242, deploy.pid)"]
        updater = Updater(self.base, trusted=self.release("drill-20261003T150000Z"), clock=self.clock, in_flight=lambda: flight[0],
                          head=None, fetch=None, attest=lambda sha: {}, launch=None)
        spawned = []

        def popen(argv, **kw):
            spawned.append((argv, kw))
            return SimpleNamespace(pid=5151, poll=lambda: None)

        with mock.patch.object(module.subprocess, "Popen", popen), mock.patch.dict(os.environ, {"GATEWAY_TOKEN": "g" * 40}):
            for _ in range(40):  # twenty minutes with the drill alive: nothing
                self.assertNotIn("recovery", updater.check())
                self.clock.advance(30)
            flight[0] = None
            for _ in range(30):  # fourteen and a half minutes since the drill went
                self.assertNotIn("recovery", updater.check())
                self.clock.advance(30)
            out = updater.check()
            self.assertEqual((out["action"], out["recovery"]["pid"], out["new"]), ("drill", 5151, True))
            for _ in range(5):
                self.clock.advance(30)
                again = updater.check()
            self.assertEqual(again["action"], "drill")
            self.assertIn("drill-recover launched", again["reasons"][-1])
        [(argv, kw)] = spawned
        self.assertEqual(argv[1:5], ["-m", "league.watchdog", "drill-recover", "--base"])
        self.assertIn("drill orphaned", argv[-1])
        self.assertTrue(kw["start_new_session"])
        self.assertNotIn("GATEWAY_TOKEN", kw["env"])
        self.assertEqual((self.base / "deploy.pid").read_text(), "5151\n")
        rows = [r for r in Releases(self.base).history() if r.get("stage") == "drill"]
        self.assertEqual([(r["outcome"], r["release"]) for r in rows], [("orphaned", "drill-20261003T150000Z")])

    def test_the_file_in_any_other_release_is_nothing(self):
        for name in ("main-0123456789ab", "20261003T150000Z-0123456789ab"):
            self.assertIsNone(Updater(self.base, trusted=self.release(name), clock=self.clock).drill, name)
        self.assertIsNone(Updater(self.base, trusted=self.release("drill-20261003T160000Z", marker=False), clock=self.clock).drill)

    def test_an_unreadable_marker_in_a_drill_copy_still_breaks(self):
        root = self.release("drill-20261003T150000Z")
        (root / "DRILL_BREAK").write_text("not json")
        self.assertEqual(Updater(self.base, trusted=root, clock=self.clock).drill,
                         {"release": "drill-20261003T150000Z", "unreadable": True})


class TheUpdaterIsOffUnlessTheConfigSaysOn(unittest.TestCase):
    """The options overhaul (Sept 26, 2026, trap 3): the in-box updater could not carry the prune, so it
    was off until V3-A turned it on (D5), and a config that does not name the key never switches it on."""

    def test_the_shipped_config_turns_it_on(self):
        from league import service

        self.assertIs(service.load_config()["auto_update"], True)
        self.assertTrue(service.auto_update(service.load_config()))
        self.assertEqual(service.load_config()["release_train_hours"], 4)

    def test_a_missing_key_means_off_and_only_true_means_on(self):
        from league.service import auto_update

        self.assertFalse(auto_update({}))
        for value in (False, None, 0, 1, "true", "yes"):
            self.assertFalse(auto_update({"auto_update": value}), value)
        self.assertTrue(auto_update({"auto_update": True}))


class TheDrillRequest(unittest.TestCase):
    """The monthly `drills` job (league/ops/drills.py) asks for the rollback drill with a file; the updater, in the
    House's own process, launches it detached (never the job's child: its limits, its priority, its death at restart)."""

    setUp, tearDown, attest = UpdaterCase.setUp, UpdaterCase.tearDown, UpdaterCase.attest

    def request(self, at=None):
        from league.watchdog import iso

        path = self.base / "state" / "ops" / "drill-request.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": iso(self.clock() if at is None else at), "by": "league.ops.drills"}))
        return path

    def updater(self, **kw):
        self.started = []
        self.flight = kw.pop("flight", None)
        return Updater(self.base, head=lambda: self.sha, fetch=lambda sha: self.main,
                       launch=lambda source, rid, record=None: self.launched.append((source, rid)), clock=self.clock,
                       judge=lambda incoming, running: [], attest=self.attest, workflows_pin=workflows_digest(tarball(tree())),
                       in_flight=lambda: self.flight, launch_watchdog=lambda args: self.started.append(args) or 999)

    def test_a_request_is_launched_detached_once_nothing_is_in_flight(self):
        path = self.request()
        updater = self.updater(flight="a watchdog is running (pid 5, deploy.pid)")
        out = updater.check()
        self.assertEqual(self.started, [])
        self.assertTrue(path.exists(), "kept for the next look")
        self.assertNotEqual(out["action"], "drill_launched")
        self.flight = None
        self.clock.advance(1800)
        out = updater.check()
        self.assertEqual((out["action"], out["pid"], out["new"]), ("drill_launched", 999, True))
        self.assertEqual(self.started, [["drill-rollback", "--base", str(self.base), "--here"]])
        self.assertFalse(path.exists())
        self.clock.advance(1800)
        self.assertNotEqual(updater.check()["action"], "drill_launched")
        self.assertEqual(len(self.started), 1)

    def test_the_default_launch_is_the_drill_itself_in_deploy_pid(self):
        """`_spawn` gives the drill its own session, the scrubbed environment and ITS pid in deploy.pid. With `--here`
        the drill runs in that very process, so the pid it finds in deploy.pid is its own (ignored); without it the
        command re-ran itself as a child that took the launch's pid for a deploy in flight, and refused."""
        import os
        from types import SimpleNamespace
        from unittest import mock

        from league import updater as module
        from league.watchdog import deploy_in_flight

        self.request()
        spawned = []

        def popen(argv, **kw):
            spawned.append((argv, kw))
            return SimpleNamespace(pid=6161, poll=lambda: None)

        updater = Updater(self.base, head=lambda: self.sha, fetch=lambda sha: self.main, launch=lambda *a: None, clock=self.clock,
                          judge=lambda incoming, running: [], attest=self.attest, workflows_pin=workflows_digest(tarball(tree())),
                          in_flight=lambda: None)
        with mock.patch.object(module.subprocess, "Popen", popen), mock.patch.dict(os.environ, {"GATEWAY_TOKEN": "g" * 40}):
            out = updater.check()
        self.assertEqual((out["action"], out["pid"]), ("drill_launched", 6161))
        [(argv, kw)] = spawned
        self.assertEqual(argv[1:], ["-m", "league.watchdog", "drill-rollback", "--base", str(self.base), "--here"])
        self.assertTrue(kw["start_new_session"])
        self.assertNotIn("GATEWAY_TOKEN", kw["env"])
        self.assertEqual((self.base / "deploy.pid").read_text(), "6161\n")
        drill = lambda pid: ["python3", "-m", "league.watchdog", *argv[3:]]  # noqa: E731
        self.assertIsNone(deploy_in_flight(self.base, argv_of=drill, ignore_pid=6161), "the drill's own pid")
        self.assertIn("pid 6161", deploy_in_flight(self.base, argv_of=drill), "a deploy in flight to everyone else")

    def test_a_stale_or_unreadable_request_is_dropped_with_a_row(self):
        from league.updater import DRILL_REQUEST_TTL_SECONDS

        path = self.request(at=self.clock() - DRILL_REQUEST_TTL_SECONDS - 60)
        updater = self.updater()
        updater.check()
        self.assertFalse(path.exists())
        path.write_text("not json")
        self.clock.advance(1800)
        updater.check()
        self.assertEqual(self.started, [])
        self.assertEqual([r["outcome"] for r in self.releases.history() if r.get("stage") == "drill"], ["dropped", "dropped"])

