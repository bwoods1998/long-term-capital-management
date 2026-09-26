"""The operator CLI: what gets uploaded, what never does, what run.sh says, and how a release
reaches the House.

`scripts/floor_box.py` is loaded the way `test_import_research_bank.py` loads its script, so the
repository runs without being installed. Nothing here creates a Sailbox or reaches one: every
command is driven against `FakeBox`, a scripted stand-in for the Sail API client, and the clock
the script sleeps on is a fake one.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time as real_time
import unittest
from unittest import mock
from pathlib import Path

import league
from league.sailbox import FLOOR_HOSTS, SailboxError

REPO_ROOT = Path(league.__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "floor_box.py"
PYTHON = "/workspace/.venv/bin/python"
RELEASE_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{12}$")
#: The first run's remains on the box. Nothing the script does for the league may name them.
HISTORY = ("rm -rf /workspace/ltcm", "/workspace/.data", "/workspace/.archive", "/workspace/ltcm.log",
           "/workspace/ltcm/", "/workspace/ltcm ")


def load():
    spec = importlib.util.spec_from_file_location("floor_box_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


floor_box = load()
floor_box_client = floor_box.client


class FakeTime:
    """`time`, as the script uses it, with a clock that only moves when the script sleeps."""

    def __init__(self, start: float = 1_790_000_000.0):
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def gmtime(self, seconds=None):
        return real_time.gmtime(self.now if seconds is None else seconds)

    def strftime(self, fmt, when=None):
        return real_time.strftime(fmt, self.gmtime() if when is None else when)


class Result:
    def __init__(self, stdout: str = "", code: int = 0):
        self.stdout = self.output = stdout
        self.stderr = ""
        self.return_code = code

    @property
    def ok(self) -> bool:
        return self.return_code == 0

    def check(self):
        if not self.ok:
            raise SailboxError(f"command failed on the box (code {self.return_code})")
        return self


class FakeBox:
    """One scripted House box behind the client methods `floor_box` calls. It records every
    command, upload and download, and answers the probe, the watchdog's `status`, the deploy
    log, `deploys.jsonl` and the log tail from the fields below."""

    def __init__(self, **probe: str):
        self.probe = {"run.pid": "-", "loop.pid": "-", "deploy.pid": "-", "stop": "no", "league_stop": "no",
                      "current": "", "previous": "", "runnable": "no", "env": "yes", **probe}
        self.calls: list[tuple] = []
        self.raw: list = []                        # each exec's command as the script passed it
        self.files: dict[str, bytes] = {}
        self.verdict: str | None = None            # what the watchdog decides about the upload
        self.reasons: list[str] = []
        self.verdict_after = 1                     # how many readings show no verdict first
        self.readings = 0
        self.status_is_broken = False
        self.watchdog_alive: list[bool] = [True]   # successive answers; the last one repeats
        self.deploy_log = "2026-09-19T08:00:00.000Z  watchdog: staged"
        self.deploys_jsonl: list[dict] = []
        self.league_log = "tick one\ntick two"
        self.stubborn_loop = False
        self.pip_fails = False
        self.venv = True
        # The structures guard (the review of Deploy G, Sept 25, 2026): what the previous release lacks, what the
        # ledger shows on alpaca-paper, or the error the check answers; and what the watchdog's rollback says.
        self.previous_missing: list[str] = []
        self.ledger = {"structures": [], "orders": []}
        self.guard_error: str | None = None
        self.rollback_answer = {"ok": True, "current": "20260917T070000Z-ba9876543210",
                                "rolled_back_from": "20260918T070000Z-0123456789ab"}

    # ------------------------------------------------------------- what was done, for the asserts
    def execs(self) -> list[str]:
        return [call[1] for call in self.calls if call[0] == "exec"]

    def uploads(self) -> list[str]:
        return [call[1] for call in self.calls if call[0] == "upload"]

    def everything(self) -> list[str]:
        return [call[1] for call in self.calls]

    def release_id(self) -> str:
        """The id of the one release that was uploaded."""
        [target] = [t for t in self.uploads() if t.endswith(".tgz")]
        return target.rpartition("/release-")[2][: -len(".tgz")]

    def verdict_rows(self) -> list[dict]:
        """The watchdog's verdict rows as of this reading: an older deploy's, then this one's."""
        rows = [{"at": "2026-09-19T07:00:00.000Z", "release": "20260918T070000Z-0123456789ab", "stage": "verdict",
                 "verdict": "promoted", "reasons": []}]
        self.readings += 1
        if self.verdict and self.readings > self.verdict_after:
            rows.append({"at": "2026-09-19T08:30:00.000Z", "release": self.release_id(), "stage": "verdict",
                         "verdict": self.verdict, "reasons": list(self.reasons)})
        return rows

    def index(self, needle: str) -> int:
        for n, text in enumerate(self.everything()):
            if needle in text:
                return n
        raise AssertionError(f"nothing the script did mentions {needle!r}")

    # --------------------------------------------------------------------------- the client API
    def exec(self, _box, command, **kw):
        text = command if isinstance(command, str) else " ".join(command)
        if kw.get("background") and not isinstance(command, str):
            raise SailboxError("background applies to a shell command string")
        self.calls.append(("exec", text, kw))
        self.raw.append(command)
        if floor_box.PROBE in text:
            return Result("\n".join(f"{k}={v}" for k, v in self.probe.items()))
        if not isinstance(command, str) and floor_box.STRUCTURE_GUARD_SNIPPET in command:
            if self.guard_error:
                return Result(json.dumps({"error": self.guard_error}))
            ask = json.loads(command[-1])
            answer = {"release": None, "checked": True, "structures": [], "orders": []}
            if ask.get("release"):
                answer["release"] = {"dir": "/workspace/releases/20260917T070000Z-ba9876543210", "missing": list(self.previous_missing)}
                if not self.previous_missing:
                    return Result(json.dumps({**answer, "checked": False}))
            return Result(json.dumps({**answer, **self.ledger}))
        if "-m league.watchdog rollback" in text:
            if self.rollback_answer.get("ok"):
                self.probe.update(current="releases/" + self.rollback_answer["current"])
            return Result(json.dumps(self.rollback_answer, indent=1), 0 if self.rollback_answer.get("ok") else 1)
        if "-m league.watchdog status" in text:
            if self.status_is_broken:
                return Result("Traceback (most recent call last):\n  boom", 1)
            rows = [{k: row[k] for k in ("at", "release", "verdict", "reasons")} for row in self.verdict_rows()]
            return Result(json.dumps({"current": None, "last_deploys": rows}))
        if "-m league.watchdog deploy" in text:
            self.probe["deploy.pid"] = "5001"
            return Result("")
        if "deploy.pid" in text and "tail -n" in text:
            alive = self.watchdog_alive.pop(0) if len(self.watchdog_alive) > 1 else self.watchdog_alive[0]
            return Result(("alive" if alive else "gone") + "\n" + self.deploy_log)
        if "deploys.jsonl" in text:
            rows = self.deploys_jsonl + (self.verdict_rows() if self.status_is_broken else [])
            return Result("\n".join(json.dumps(row) for row in rows))
        if "league.log" in text and "tail -n" in text:
            return Result(self.league_log)
        if "run.sh >/dev/null" in text:
            self.probe.update({"run.pid": "4001", "loop.pid": "4002"})
        if "kill -TERM 4002" in text and not self.stubborn_loop:
            self.probe["loop.pid"] = "-"
        if "kill -KILL 4002" in text:
            self.probe["loop.pid"] = "-"
        if "kill -TERM 4001" in text:
            self.probe["run.pid"] = "-"
        if "-m venv" in text:
            return Result("ok" if self.venv else "no")
        if "pip install" in text:
            return Result("", 1 if self.pip_fails else 0)
        return Result("")

    def upload(self, _box, target, content, *, mode=0o600, **_kw):
        self.calls.append(("upload", target, bytes(content), mode))
        self.files[target] = bytes(content)
        return {"size_bytes": len(content)}

    def download(self, _box, path, **_kw):
        self.calls.append(("download", path))
        if path not in self.files:
            raise SailboxError("no such file", status=404)
        return self.files[path]

    def status(self, box, *, expected_egress=None):
        return {"sailbox_id": box, "name": "ltcm-floor", "status": "running", "egress": ["blakewoods.us"],
                "egress_ok": True, "spend": {"total_usd": 1.25, "from": "2026-09-01T00:00:00Z"}}

    def whoami(self):
        return {"org_id": "org_1", "user_id": "user_1"}

    def find_app(self, name, **_kw):
        return {"id": "app_1", "name": name}

    def create(self, **kw):
        self.calls.append(("create", json.dumps(kw, sort_keys=True, default=str)))
        return {"sailbox_id": "sb_new", "status": "running"}

    def verify_egress(self, _box, policy):
        return {"ok": True, "allowlist": list(policy["allowlist"]), "missing": [], "extra": []}

    def get(self, _box):
        return {"vcpu_count": 1, "memory_mib": 16384, "state_disk_size_gib": 32, "auto_sleep": {"automatic": False}}

    def from_checkpoint(self, source, *, name):
        return {"sailbox_id": "sb_fork", "status": "running"}


class BoxCase(unittest.TestCase):
    """A recorded box, a fake client, a fake clock, and a three-file working tree to release."""

    probe: dict[str, str] = {}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.box = FakeBox(**self.probe)
        self.clock = FakeTime()
        tree = [Path("league/__main__.py"), Path("league/config.json"), Path("deploy/README.md")]
        for patch in (
            mock.patch.object(floor_box, "STATE_PATH", Path(self.temp.name) / "box.json"),
            mock.patch.object(floor_box, "client", lambda: self.box),
            mock.patch.object(floor_box, "time", self.clock),
            mock.patch.object(floor_box, "code_files", lambda: list(tree)),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        floor_box.write_state({"box_id": "sb_1", "python": PYTHON, "uploads": {"league/service.py": "abc"}})

    def run_cmd(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            args = floor_box.build_parser().parse_args(list(argv))
            code = floor_box.COMMANDS[args.command](args)
        return code, buffer.getvalue()



class SecretGuardTests(unittest.TestCase):
    """The code path must be incapable of carrying a credential, not merely careful."""

    def test_every_credential_shape_is_refused(self):
        for name in (
            ".env",
            ".env.local",
            "ltcm/keys/kalshi.pem",
            ".data/ltcm/keys/coinbase.pem",
            ".data/ltcm/events.sqlite",
            "deploy/server.key",
            "certs/client.crt",
        ):
            with self.subTest(name=name):
                self.assertTrue(floor_box.is_secret(Path(name)))

    def test_ordinary_code_is_not_mistaken_for_one(self):
        for name in ("league/service.py", "league/config.json", "playbooks/merton.md",
                     "scripts/floor_box.py", "deploy/README.md", "deploy/league.service"):
            with self.subTest(name=name):
                self.assertFalse(floor_box.is_secret(Path(name)))

    def test_the_bundle_carries_the_floor_and_nothing_private(self):
        files = {str(p) for p in floor_box.code_files()}
        for wanted in ("league/service.py", "league/config.json", "league/sailbox.py",
                       "league/broker.py", "scripts/floor_box.py", "deploy/README.md",
                       "league/__main__.py", "league/service.py", "league/watchdog.py",
                       "league/config.json"):
            self.assertIn(wanted, files)
        for forbidden in (".env", ".data/ltcm/keys/kalshi.pem"):
            self.assertNotIn(forbidden, files)
        self.assertFalse([f for f in files if f.endswith((".pem", ".pyc", ".sqlite"))])
        self.assertFalse([f for f in files if "__pycache__" in f])
        self.assertFalse([f for f in files if f.startswith(".data")])

    def test_the_bundle_carries_the_desks_the_playbooks_and_the_tests(self):
        files = {str(p) for p in floor_box.code_files()}
        self.assertTrue([f for f in files if f.startswith("league/swarm/")])
        self.assertTrue([f for f in files if f.startswith("league/gym/")])
        self.assertTrue([f for f in files if f.startswith("league/tests/")])
        self.assertTrue([f for f in files if f.startswith("league/adapters/")])

    def test_a_release_is_the_league_and_what_it_imports_from_the_first_run(self):
        self.assertEqual(floor_box.UPLOAD_TREES[0], "league")
        for tree in ("league", "scripts", "deploy"):
            self.assertIn(tree, floor_box.UPLOAD_TREES)
        files = {str(p) for p in floor_box.code_files()}
        for wanted in ("league/live/", "league/gym/", "league/swarm/", "league/tools/", "league/data/", "league/broker.py", "league/risk.py", "league/provider.py"):
            self.assertTrue([f for f in files if f.startswith(wanted)], wanted)




class BundleTests(unittest.TestCase):
    def test_the_tar_round_trips_with_the_paths_the_box_expects(self):
        files = [Path("league/config.json"), Path("deploy/README.md")]
        blob = floor_box.tarball(files)
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            names = archive.getnames()
            self.assertEqual(sorted(names), ["deploy/README.md", "league/config.json"])
            member = archive.extractfile("league/config.json").read()
        self.assertEqual(member, (REPO_ROOT / "league" / "config.json").read_bytes())

    def test_the_tar_is_deterministic_so_the_same_tree_is_the_same_release(self):
        files = [Path("league/config.json")]
        first = floor_box.tarball(files)
        # gzip stamps its header with the time unless told not to: a second later, the same tree
        # would hash to another release.
        with mock.patch("time.time", return_value=real_time.time() + 86400):
            second = floor_box.tarball(files)
        self.assertEqual(first, second)
        self.assertEqual(first[4:8], b"\0\0\0\0")

    def test_shell_scripts_arrive_executable(self):
        with tarfile.open(fileobj=io.BytesIO(floor_box.tarball([Path("league/config.json")]))) as a:
            self.assertEqual(a.getmember("league/config.json").mode, 0o644)

    def test_a_release_id_is_the_time_it_was_sent_and_the_content_it_carries(self):
        blob = floor_box.tarball([Path("league/config.json")])
        release = floor_box.release_id_for(blob, now=1_790_000_000)
        self.assertRegex(release, RELEASE_ID)
        self.assertEqual(release, "20260921T141320Z-" + hashlib.sha256(blob).hexdigest()[:12])
        self.assertEqual(floor_box.content_of(release), hashlib.sha256(blob).hexdigest()[:12])
        # The watchdog's own rule for an id (league.watchdog.RELEASE_ID), so it is never refused for its name.
        from league.watchdog import Releases

        self.assertEqual(Releases.check_id(release), release)

    def test_a_link_names_its_release(self):
        self.assertEqual(floor_box.release_of("releases/20260919T080000Z-abcdef012345"), "20260919T080000Z-abcdef012345")
        self.assertIsNone(floor_box.release_of(""))
        self.assertIsNone(floor_box.release_of(None))


class SupervisorScriptTests(unittest.TestCase):
    def script(self, python=PYTHON):
        return floor_box.render(floor_box.RUN_SH, python).decode()

    def test_it_runs_the_league_with_the_recorded_interpreter_the_env_file_and_the_state_dir(self):
        self.assertIn(f"LEAGUE_ENV=/workspace/.env {PYTHON} -m league run --root /workspace/state "
                      ">> /workspace/league.log 2>&1 &", self.script())
        self.assertIn("python3 -m league run --root /workspace/state", self.script("python3"))
        self.assertNotIn("-m ltcm", self.script())

    def test_it_resolves_current_again_on_every_restart(self):
        body = self.script()
        loop = body[body.index("while ! stopped; do"):]
        self.assertIn("cd /workspace/current || {", loop)
        self.assertIn("sleep 30; continue; }", loop)
        self.assertLess(loop.index("cd /workspace/current"), loop.index("-m league run"))

    def test_it_waits_thirty_seconds_between_restarts(self):
        self.assertIn("\n  sleep 30\n", self.script())

    def test_everything_goes_to_the_one_log_and_never_to_the_first_runs(self):
        body = self.script()
        self.assertIn(">> /workspace/league.log 2>&1", body)
        self.assertIn("supervisor: the House exited", body)
        self.assertNotIn("ltcm.log", body)

    def test_either_stop_file_ends_the_loop_rather_than_restarting_it(self):
        body = self.script()
        self.assertIn("stopped() { [ -e /workspace/STOP ] || [ -e /workspace/state/STOP ]; }", body)
        self.assertIn("while ! stopped; do", body)
        self.assertIn("stopped && break", body)

    def test_both_pids_are_written_down_so_stop_can_find_them(self):
        body = self.script()
        self.assertIn("echo $$ > /workspace/run.pid", body)
        self.assertIn("/workspace/loop.pid", body)

    def test_restart_signals_the_loop_and_leaves_the_supervisor_and_the_links_alone(self):
        body = floor_box.render(floor_box.RESTART_SH, "python3").decode()
        self.assertIn("/workspace/loop.pid", body)
        self.assertIn('kill -TERM "$pid"', body)
        self.assertNotIn("run.pid", body)
        code = "\n".join(line for line in body.splitlines() if not line.startswith("#"))
        for untouched in ("current", "previous", "ln ", "run.sh", "setsid", "STOP"):
            self.assertNotIn(untouched, code)

    def test_the_probe_reports_the_pids_both_stop_files_and_both_links(self):
        for marker in ("run.pid", "loop.pid", "deploy.pid", "[ -e /workspace/STOP ]", "[ -e /workspace/state/STOP ]",
                       "readlink /workspace/current", "readlink /workspace/previous", "/workspace/.env"):
            self.assertIn(marker, floor_box.PROBE)
        for history in HISTORY:
            self.assertNotIn(history, floor_box.PROBE)


class SupervisorRunTests(unittest.TestCase):
    """run.sh for real, under /bin/sh, against a directory laid out like the box and an
    "interpreter" that writes down how it was started."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for release in ("r1", "r2"):
            (self.root / "releases" / release / "league").mkdir(parents=True)
        (self.root / "state").mkdir()
        os.symlink("releases/r1", self.root / "current")
        self.python = self.root / "python"

    def supervise(self, interpreter: str) -> str:
        self.python.write_text("#!/bin/sh\n" + interpreter, encoding="utf-8")
        self.python.chmod(0o755)
        body = floor_box.RUN_SH.format(root=self.root, python=self.python).replace("sleep 30", "sleep 0")
        (self.root / "run.sh").write_text(body, encoding="utf-8")
        done = subprocess.run(["/bin/sh", str(self.root / "run.sh")], timeout=30, capture_output=True, text=True,
                              env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "ROOT": str(self.root)})
        self.assertEqual(done.returncode, 0, done.stderr)
        log = self.root / "league.log"
        return log.read_text(encoding="utf-8") if log.exists() else ""

    def test_the_house_starts_inside_the_release_with_the_env_file_and_the_state_dir(self):
        log = self.supervise('echo "cwd=$(pwd -P) env=$LEAGUE_ENV args=$*"; touch "$ROOT/state/STOP"\n')
        self.assertIn(f"cwd={self.root}/releases/r1 env={self.root}/.env args=-m league run --root {self.root}/state", log)
        self.assertIn("supervisor: stopped", log)
        self.assertFalse((self.root / "run.pid").exists())
        self.assertFalse((self.root / "loop.pid").exists())

    def test_a_promotion_takes_effect_at_the_next_restart(self):
        # The first House moves `current` to r2, as a promotion does, and exits; the second must
        # start in r2, and ends the loop with the supervisor's own latch.
        log = self.supervise(
            'echo "ran in $(basename "$(pwd -P)")"\n'
            'if [ "$(basename "$(pwd -P)")" = r1 ]; then ln -sfn releases/r2 "$ROOT/current"; '
            'else touch "$ROOT/STOP"; fi\n'
        )
        self.assertEqual([line for line in log.splitlines() if line.startswith("ran in")], ["ran in r1", "ran in r2"])

    def test_either_stop_file_keeps_the_house_from_starting_at_all(self):
        for latch in ("STOP", "state/STOP"):
            with self.subTest(latch=latch):
                (self.root / latch).write_text("stopped\n", encoding="utf-8")
                self.assertNotIn("ran", self.supervise('echo "ran"\n'))
                (self.root / latch).unlink()

    def test_without_a_current_release_it_waits_and_says_so_rather_than_running_anything(self):
        (self.root / "current").unlink()
        # No House can end this loop, so the latch is written by the wait itself.
        self.python.write_text("#!/bin/sh\necho ran\n", encoding="utf-8")
        body = floor_box.RUN_SH.format(root=self.root, python=self.python).replace("sleep 30; continue", f"touch {self.root}/STOP; continue")
        (self.root / "run.sh").write_text(body, encoding="utf-8")
        subprocess.run(["/bin/sh", str(self.root / "run.sh")], timeout=30, check=True, capture_output=True)
        log = (self.root / "league.log").read_text(encoding="utf-8")
        self.assertIn("no " + str(self.root / "current"), log)
        self.assertNotIn("ran", log.replace("no " + str(self.root / "current"), ""))


class ShellSafetyTests(unittest.TestCase):
    """What runs on the box runs through a shell, so nothing may be interpolated blind."""

    def test_the_stop_reason_is_a_positional_parameter_not_shell_text(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"floor_box", args.reason', source)
        self.assertNotIn("{args.reason}", source)

    def test_no_command_of_the_first_runs_is_left(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for gone in ("-m ltcm", "unkill", "keep_kill_switch", "keep-kill-switch", "ltcm.log 2>"):
            self.assertNotIn(gone, source)

    def test_every_league_command_on_the_box_changes_into_a_release_first(self):
        # An exec's working directory on a Sailbox is `/`, where `league` is not importable.
        release = "20260919T080000Z-abcdef012345"
        for line in (floor_box.watchdog_launch(PYTHON, release, watch=True), floor_box.watchdog_status(PYTHON, release)):
            with self.subTest(line=line):
                change = f"cd /workspace/current 2>/dev/null || cd /workspace/incoming/{release}; "
                self.assertIn(change, line)
                self.assertLess(line.index(change), line.index("-m league"))

    def test_a_pid_the_probe_could_not_read_is_ignored_rather_than_crashing(self):
        self.assertEqual(floor_box._pid("4321"), 4321)
        for bad in ("-", "", None, "1", "0", "nope", "12; rm -rf /"):
            with self.subTest(bad=bad):
                self.assertIsNone(floor_box._pid(bad))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = floor_box.STATE_PATH
        floor_box.STATE_PATH = Path(self.temp.name) / ".data" / "ltcm" / "box.json"
        self.addCleanup(lambda: setattr(floor_box, "STATE_PATH", self.original))

    def test_state_round_trips_and_is_owner_only(self):
        floor_box.write_state({"box_id": "sb_1", "size": "s"})
        self.assertEqual(floor_box.read_state()["box_id"], "sb_1")
        self.assertEqual(floor_box.STATE_PATH.stat().st_mode & 0o777, 0o600)

    def test_a_missing_or_broken_state_file_reads_as_empty(self):
        self.assertEqual(floor_box.read_state(), {})
        floor_box.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        floor_box.STATE_PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(floor_box.read_state(), {})

    def test_state_holds_no_credential(self):
        floor_box.write_state(
            {"box_id": "sb_1", "egress_allowlist": list(FLOOR_HOSTS),
             "secret_names": ["kalshi.pem"], "checkpoints": []}
        )
        raw = floor_box.STATE_PATH.read_text(encoding="utf-8").lower()
        for marker in ("bearer", "sk-", "private key", "begin ec", "api_key"):
            self.assertNotIn(marker, raw)
        # Names of the files that were pushed are fine; their contents are never here.
        self.assertIn("kalshi.pem", raw)

    def test_a_command_without_a_box_says_to_create_one(self):
        with self.assertRaises(SystemExit) as caught:
            floor_box.require_box({})
        self.assertIn("create", str(caught.exception))

    def test_the_recorded_allowlist_is_what_status_checks_against(self):
        hosts = ["api.sailresearch.com", "blakewoods.us"]
        self.assertEqual(floor_box.expected_policy({"egress_allowlist": hosts})["allowlist"], hosts)

    def test_without_a_record_the_expected_policy_is_the_packaged_one(self):
        policy = floor_box.expected_policy({})
        for host in FLOOR_HOSTS:
            self.assertIn(host, policy["allowlist"])


class HostsAddTests(unittest.TestCase):
    """`hosts --add` widens the live allowlist and records what the API confirmed."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = floor_box.STATE_PATH
        floor_box.STATE_PATH = Path(self.temp.name) / ".data" / "ltcm" / "box.json"
        self.addCleanup(lambda: setattr(floor_box, "STATE_PATH", self.original))
        floor_box.write_state({"box_id": "sb_1", "egress_allowlist": list(FLOOR_HOSTS)})

    def test_the_exact_gateway_host_joins_the_list_and_is_written_down(self):
        live = {"allowlist": list(FLOOR_HOSTS) + ["*.workers.dev"]}
        seen: dict[str, list[str]] = {}

        class Client:
            def egress(self, box):
                return {"document": dict(live)}

            def set_egress(self, box, allowlist):
                seen["sent"] = list(allowlist)
                live["allowlist"] = list(allowlist)
                return {"document": dict(live)}

        with mock.patch.object(floor_box, "SailboxClient", Client):
            args = floor_box.build_parser().parse_args(
                ["hosts", "--add", "ltcm-gateway.example.workers.dev"]
            )
            self.assertEqual(floor_box.cmd_hosts(args), 0)
        self.assertIn("ltcm-gateway.example.workers.dev", seen["sent"])
        self.assertIn("*.workers.dev", seen["sent"])  # nothing that was there is dropped
        state = floor_box.read_state()
        self.assertIn("ltcm-gateway.example.workers.dev", state["egress_allowlist"])
        self.assertEqual(state["gateway_host"], "ltcm-gateway.example.workers.dev")
        # And `status` now checks against the widened list, not the packaged default.
        self.assertIn("ltcm-gateway.example.workers.dev", floor_box.expected_policy(state)["allowlist"])

    def test_a_host_the_api_did_not_keep_is_an_error_not_a_silent_success(self):
        class Client:
            def egress(self, box):
                return {"document": {"allowlist": list(FLOOR_HOSTS)}}

            def set_egress(self, box, allowlist):
                return {"document": {"allowlist": list(FLOOR_HOSTS)}}

        with mock.patch.object(floor_box, "SailboxClient", Client):
            args = floor_box.build_parser().parse_args(["hosts", "--add", "gw.example.workers.dev"])
            with self.assertRaises(SystemExit) as caught:
                floor_box.cmd_hosts(args)
        self.assertIn("gw.example.workers.dev", str(caught.exception))
        self.assertNotIn("gw.example.workers.dev", floor_box.read_state().get("egress_allowlist", []))


class ParserTests(unittest.TestCase):
    def test_every_command_the_owner_is_told_about_exists(self):
        parser = floor_box.build_parser()
        for command in ("create", "secrets", "start", "stop", "status", "logs", "deploy", "rollback",
                        "checkpoint", "fork", "sleep", "resume", "terminate"):
            with self.subTest(command=command):
                self.assertEqual(parser.parse_args(_args(command)).command, command)

    def test_terminate_needs_the_owner_to_say_yes(self):
        self.assertFalse(floor_box.build_parser().parse_args(["terminate"]).yes)

    def test_stop_waits_two_minutes_by_default(self):
        self.assertEqual(floor_box.build_parser().parse_args(["stop"]).timeout, 120.0)

    def test_deploy_waits_twenty_five_minutes_for_a_verdict_unless_told_not_to_wait(self):
        args = floor_box.build_parser().parse_args(["deploy"])
        self.assertEqual((args.timeout, args.no_wait), (1500.0, False))
        self.assertTrue(floor_box.build_parser().parse_args(["deploy", "--no-wait"]).no_wait)

    def test_the_first_runs_flags_are_gone(self):
        for argv in (["deploy", "--all"], ["deploy", "--prune"], ["start", "--keep-kill-switch"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                floor_box.build_parser().parse_args(argv)

    def test_fork_names_the_checkpoint_it_comes_from(self):
        args = floor_box.build_parser().parse_args(["fork", "--from", "sbcp_1"])
        self.assertEqual(args.source, "sbcp_1")
        self.assertFalse(args.i_know)

    def test_create_defaults_to_a_private_size_s_box_with_the_wildcard_gateway(self):
        args = floor_box.build_parser().parse_args(["create"])
        self.assertEqual((args.visibility, args.gateway_host, args.name, args.app),
                         ("private", "*.workers.dev", "ltcm-floor", "ltcm"))


def _args(command: str) -> list[str]:
    return {"fork": ["fork", "--from", "sbcp_1"]}.get(command, [command])


class ForkSafetyTests(unittest.TestCase):
    """A fork inherits memory, so a running loop would carry on in the copy."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = floor_box.STATE_PATH
        floor_box.STATE_PATH = Path(self.temp.name) / "box.json"
        self.addCleanup(lambda: setattr(floor_box, "STATE_PATH", self.original))

    def test_a_checkpoint_taken_with_the_loop_running_is_refused(self):
        floor_box.write_state(
            {"box_id": "sb_1",
             "checkpoints": [{"checkpoint_id": "sbcp_hot", "loop_was_running": True}]}
        )
        args = floor_box.build_parser().parse_args(["fork", "--from", "sbcp_hot"])
        with self.assertRaises(SystemExit) as caught:
            floor_box.cmd_fork(args)
        self.assertIn("second floor", str(caught.exception))

    def test_the_refusal_can_be_overridden_deliberately(self):
        floor_box.write_state(
            {"box_id": "sb_1",
             "checkpoints": [{"checkpoint_id": "sbcp_hot", "loop_was_running": True}]}
        )
        args = floor_box.build_parser().parse_args(["fork", "--from", "sbcp_hot", "--i-know"])

        class Reached(Exception):
            pass

        class NoNetwork:
            def from_checkpoint(self, *_a, **_k):
                raise Reached("the guard let this through")

        self.addCleanup(lambda: setattr(floor_box, "client", floor_box_client))
        floor_box.client = lambda: NoNetwork()
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(Reached):
            floor_box.cmd_fork(args)

    def test_a_checkpoint_with_the_loop_stopped_forks_without_a_prompt(self):
        floor_box.write_state(
            {"box_id": "sb_1",
             "checkpoints": [{"checkpoint_id": "sbcp_cold", "loop_was_running": False}]}
        )
        args = floor_box.build_parser().parse_args(["fork", "--from", "sbcp_cold"])

        class Reached(Exception):
            pass

        class NoNetwork:
            def from_checkpoint(self, *_a, **_k):
                raise Reached("no guard in the way")

        self.addCleanup(lambda: setattr(floor_box, "client", floor_box_client))
        floor_box.client = lambda: NoNetwork()
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(Reached):
            floor_box.cmd_fork(args)


class DeployTests(BoxCase):
    """A deploy uploads one bundle, unpacks it into `incoming/`, hands it to the in-box watchdog
    and reports what the watchdog decided. It moves no link and restarts nothing itself."""

    probe = {"run.pid": "4001", "loop.pid": "4002", "current": "releases/20260918T070000Z-0123456789ab",
             "previous": "releases/20260917T070000Z-ba9876543210", "runnable": "yes"}

    def setUp(self):
        super().setUp()
        self.box.files["/workspace/run.sh"] = floor_box.render(floor_box.RUN_SH, PYTHON)

    def launch(self) -> tuple[str, dict]:
        [call] = [c for c in self.box.calls if c[0] == "exec" and "-m league.watchdog deploy" in c[1]]
        return call[1], call[2]

    def test_the_bundle_is_uploaded_unpacked_into_incoming_and_named_by_its_content(self):
        self.box.verdict = "promoted"
        code, _ = self.run_cmd("deploy")
        self.assertEqual(code, 0)
        release = self.box.release_id()
        self.assertRegex(release, RELEASE_ID)
        [(_, target, blob, mode)] = [c for c in self.box.calls if c[0] == "upload" and c[1].endswith(".tgz")]
        self.assertEqual((target, mode), (f"/workspace/.upload/release-{release}.tgz", 0o600))
        self.assertEqual(release.rpartition("-")[2], hashlib.sha256(blob).hexdigest()[:12])
        self.assertTrue(release.startswith(real_time.strftime("%Y%m%dT%H%M%SZ", real_time.gmtime(1_790_000_000))))
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            self.assertEqual(sorted(archive.getnames()), ["deploy/README.md", "league/__main__.py", "league/config.json"])
        [unpack] = [text for text in self.box.execs() if "tar -xzf" in text]
        self.assertIn(f"mkdir -p /workspace/incoming/{release}", unpack)
        self.assertIn(f"tar -xzf /workspace/.upload/release-{release}.tgz -C /workspace/incoming/{release} --no-same-owner", unpack)
        self.assertIn(f"rm -f /workspace/.upload/release-{release}.tgz", unpack)
        # Never over /workspace itself, which is how the first run's deploy replaced running code.
        self.assertNotIn("-C /workspace ", unpack)

    def test_the_watchdog_is_launched_detached_from_the_known_good_code_with_the_env_file(self):
        self.box.verdict = "promoted"
        self.run_cmd("deploy")
        release = self.box.release_id()
        line, kw = self.launch()
        self.assertEqual(
            line,
            f"umask 077; cd /workspace/current 2>/dev/null || cd /workspace/incoming/{release}; "
            f"LEAGUE_ENV=/workspace/.env setsid nohup {PYTHON} -m league.watchdog deploy --base /workspace "
            f"--source /workspace/incoming/{release} --id {release} "
            "> /workspace/deploy.log 2>&1 < /dev/null & echo $! > /workspace/deploy.pid",
        )
        self.assertTrue(kw.get("background"))
        self.assertNotIn("--watch-seconds", line)  # a House is running: it is watched

    def test_things_happen_in_the_only_order_that_works(self):
        self.box.verdict = "promoted"
        self.run_cmd("deploy")
        order = [self.box.index(step) for step in (
            floor_box.PROBE, "/workspace/restart.sh.new", "mv -f /workspace/run.sh.new /workspace/run.sh",
            ".tgz", "tar -xzf", "-m league.watchdog deploy", "-m league.watchdog status")]
        self.assertEqual(order, sorted(order))

    def test_it_never_moves_a_link_restarts_the_loop_or_touches_a_stop_file_itself(self):
        self.box.verdict = "promoted"
        self.run_cmd("deploy")
        for text in self.box.execs():
            if floor_box.PROBE in text:
                continue
            for forbidden in ("ln -s", "/workspace/previous", "restart.sh;", "sh /workspace/restart.sh", "kill ", "/STOP"):
                self.assertNotIn(forbidden, text)
            self.assertNotRegex(text, r"(mv|rm|ln)\b[^;&|]*\s/workspace/current(\s|$)")

    def test_promoted_is_exit_zero_and_is_written_down(self):
        self.box.verdict = "promoted"
        self.box.verdict_after = 3
        code, printed = self.run_cmd("deploy")
        self.assertEqual(code, 0)
        self.assertIn(f"PROMOTED: {self.box.release_id()}", printed)
        self.assertEqual(self.clock.slept, [15.0, 15.0, 15.0])
        state = floor_box.read_state()
        entry = state["releases"][-1]
        self.assertEqual((entry["id"], entry["verdict"], entry["watched"], entry["replaces"]),
                         (self.box.release_id(), "promoted", True, "20260918T070000Z-0123456789ab"))
        self.assertEqual(len(entry["sha256"]), 64)
        self.assertNotIn("uploads", state)  # the first run's per-file digests are gone for good

    def test_a_refusal_is_exit_two_with_the_watchdogs_reasons(self):
        self.box.verdict, self.box.reasons = "refused", ["canary: tick 1: it exited 1: RuntimeError: GATEWAY_TOKEN is not set"]
        code, printed = self.run_cmd("deploy")
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", printed)
        self.assertIn("GATEWAY_TOKEN is not set", printed)
        self.assertEqual(floor_box.read_state()["releases"][-1]["reasons"], self.box.reasons)

    def test_a_rollback_is_exit_three_and_a_failure_exit_four(self):
        for verdict, expected in (("rolled_back", 3), ("failed", 4)):
            with self.subTest(verdict=verdict):
                self.setUp()
                self.box.verdict, self.box.reasons = verdict, ["reading 3: the alpaca-paper book is frozen: drift"]
                code, printed = self.run_cmd("deploy")
                self.assertEqual(code, expected)
                self.assertIn(verdict.upper(), printed)
                self.assertIn("the alpaca-paper book is frozen", printed)
                self.assertEqual(floor_box.read_state()["releases"][-1]["verdict"], verdict)

    def test_an_older_releases_verdict_is_never_mistaken_for_this_ones(self):
        self.box.verdict = None  # `status` only ever shows the older release's "promoted"
        code, printed = self.run_cmd("deploy", "--timeout", "60")
        self.assertEqual(code, 1)
        self.assertNotIn("PROMOTED", printed)

    def test_no_verdict_in_time_is_exit_one_and_stays_pending(self):
        code, printed = self.run_cmd("deploy", "--timeout", "90", "--poll-seconds", "30")
        self.assertEqual(code, 1)
        self.assertIn("NO VERDICT", printed)
        self.assertIn("no verdict after 90s", printed)
        self.assertIn("watchdog: staged", printed)  # the tail of deploy.log is shown
        self.assertEqual(self.clock.slept, [30.0, 30.0, 30.0])
        self.assertEqual(floor_box.read_state()["releases"][-1]["verdict"], "pending")

    def test_a_watchdog_that_died_without_a_verdict_is_said_at_once_not_after_the_timeout(self):
        self.box.watchdog_alive = [False]
        self.box.deploy_log = "/workspace/.venv/bin/python: No module named league"
        code, printed = self.run_cmd("deploy")
        self.assertEqual(code, 1)
        self.assertIn("exited without recording a verdict", printed)
        self.assertIn("No module named league", printed)
        self.assertEqual(len(self.clock.slept), 1)  # dead twice in a row, fifteen seconds apart

    def test_a_status_that_cannot_answer_falls_back_to_the_record_it_appends_to(self):
        self.box.status_is_broken = True
        self.box.verdict = "rolled_back"
        code, _ = self.run_cmd("deploy")
        self.assertEqual(code, 3)

    def test_no_wait_returns_as_soon_as_the_watchdog_is_launched(self):
        code, printed = self.run_cmd("deploy", "--no-wait")
        self.assertEqual(code, 0)
        self.assertIn("launched", printed)
        self.launch()
        self.assertFalse([t for t in self.box.execs() if "-m league.watchdog status" in t])
        self.assertEqual(self.clock.slept, [])
        self.assertEqual(floor_box.read_state()["releases"][-1]["verdict"], "pending")

    def test_the_same_tree_as_current_is_not_sent_again(self):
        blob = floor_box.tarball(floor_box.code_files())
        self.box.probe["current"] = "releases/20260918T070000Z-" + hashlib.sha256(blob).hexdigest()[:12]
        code, printed = self.run_cmd("deploy")
        self.assertEqual(code, 0)
        self.assertIn("nothing to deploy", printed)
        self.assertEqual(self.box.uploads(), [])

    def test_a_second_deploy_is_refused_while_the_first_is_still_being_judged(self):
        self.box.probe["deploy.pid"] = "5001"
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("deploy")
        self.assertIn("still running", str(caught.exception))
        self.assertEqual(self.box.uploads(), [])

    def test_a_supervisor_left_by_the_first_run_is_refused_not_restarted_into(self):
        self.box.files["/workspace/run.sh"] = b"#!/bin/sh\n/workspace/.venv/bin/python -m ltcm run >> /workspace/league.log 2>&1 &\n"
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("deploy")
        self.assertIn("`stop`", str(caught.exception))
        self.assertEqual(self.box.uploads(), [])

    def test_without_the_env_file_the_canary_cannot_pass_so_nothing_is_sent(self):
        self.box.probe["env"] = "no"
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("deploy")
        self.assertIn("secrets", str(caught.exception))
        self.assertEqual(self.box.uploads(), [])

    def test_a_box_that_cannot_be_probed_is_sent_nothing(self):
        self.box.exec = mock.Mock(side_effect=SailboxError("sailbox is paused"))
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("deploy")
        self.assertIn("paused", str(caught.exception))
        self.assertEqual(self.box.uploads(), [])

    def test_only_the_last_twenty_releases_are_remembered_newest_last(self):
        state = floor_box.read_state()
        for n in range(25):
            floor_box.remember_release(state, {"id": f"r{n:02d}", "verdict": "promoted"})
        floor_box.remember_release(state, {"id": "r24", "verdict": "rolled_back"})
        self.assertEqual(len(state["releases"]), 20)
        self.assertEqual([state["releases"][0]["id"], state["releases"][-1]["id"]], ["r05", "r24"])
        self.assertEqual(state["releases"][-1]["verdict"], "rolled_back")


class FirstDeployTests(BoxCase):
    """With nothing to watch, the watchdog is told not to: canary, promote, return."""

    def launch_line(self) -> str:
        [line] = [t for t in self.box.execs() if "-m league.watchdog deploy" in t]
        return line

    def test_a_first_deploy_passes_watch_seconds_zero_and_runs_from_the_upload(self):
        self.box.verdict = "promoted"
        code, printed = self.run_cmd("deploy")
        self.assertEqual(code, 0)
        release = self.box.release_id()
        line = self.launch_line()
        self.assertIn(f"--id {release} --watch-seconds 0 > /workspace/deploy.log", line)
        self.assertIn(f"cd /workspace/current 2>/dev/null || cd /workspace/incoming/{release}; ", line)
        self.assertIn("there is no current release", printed)
        self.assertIn("scripts/floor_box.py start", printed)  # promoted, and the loop is not up
        entry = floor_box.read_state()["releases"][-1]
        self.assertEqual((entry["watched"], entry["replaces"]), (False, None))

    def test_a_current_release_whose_loop_is_not_running_is_not_watched_either(self):
        self.box.probe.update(current="releases/20260918T070000Z-0123456789ab", runnable="yes")
        self.box.verdict = "promoted"
        _, printed = self.run_cmd("deploy")
        self.assertIn("--watch-seconds 0", self.launch_line())
        self.assertIn("the loop is not running", printed)

    def test_a_supervisor_between_two_houses_is_still_a_house_to_watch(self):
        self.box.probe.update(current="releases/20260918T070000Z-0123456789ab", runnable="yes", **{"run.pid": "4001"})
        self.box.files["/workspace/run.sh"] = floor_box.render(floor_box.RUN_SH, PYTHON)
        self.box.verdict = "promoted"
        self.run_cmd("deploy")
        self.assertNotIn("--watch-seconds", self.launch_line())

    def test_a_current_link_that_leads_nowhere_counts_as_no_current_release(self):
        self.box.probe.update(current="releases/20260918T070000Z-0123456789ab", runnable="no", **{"loop.pid": "4002"})
        self.box.verdict = "promoted"
        self.run_cmd("deploy")
        self.assertIn("--watch-seconds 0", self.launch_line())


class StartStopTests(BoxCase):
    probe = {"current": "releases/20260918T070000Z-0123456789ab", "runnable": "yes", "stop": "yes", "league_stop": "yes"}

    def test_start_refuses_when_there_is_no_current_release(self):
        self.box.probe.update(current="", runnable="no")
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("start")
        self.assertIn("deploy first", str(caught.exception))
        self.assertFalse([t for t in self.box.execs() if "run.sh" in t])
        self.assertFalse([t for t in self.box.execs() if "rm -f" in t])  # the latches stay too

    def test_start_removes_both_stop_files_and_launches_the_supervisor_detached(self):
        code, printed = self.run_cmd("start")
        self.assertEqual(code, 0)
        self.assertIn("sh -c rm -f /workspace/STOP /workspace/state/STOP", self.box.execs())
        [launch] = [c for c in self.box.calls if c[0] == "exec" and "run.sh >" in c[1]]
        self.assertEqual(launch[1], "setsid /bin/sh /workspace/run.sh >/dev/null 2>&1 < /dev/null")
        self.assertTrue(launch[2].get("background"))
        self.assertLess(self.box.index("rm -f /workspace/STOP"), self.box.index("setsid /bin/sh /workspace/run.sh"))
        self.assertIn("supervisor=4001  loop=4002", printed)
        self.assertIn("started_at", floor_box.read_state())

    def test_start_puts_the_leagues_run_sh_in_place_first_whatever_was_there(self):
        self.box.files["/workspace/run.sh"] = b"#!/bin/sh\npython -m ltcm run\n"
        self.run_cmd("start")
        self.assertEqual(self.box.files["/workspace/run.sh.new"], floor_box.render(floor_box.RUN_SH, PYTHON))
        self.assertLess(self.box.index("mv -f /workspace/run.sh.new /workspace/run.sh"), self.box.index("setsid /bin/sh"))

    def test_start_runs_no_first_run_command_and_leaves_the_kill_switch_alone(self):
        self.run_cmd("start")
        for text in self.box.execs():
            for forbidden in ("ltcm", "unkill", "KILL", "kill"):
                self.assertNotIn(forbidden, text.replace(floor_box.PROBE, ""))
        self.assertEqual(self.box.execs().count("sh -c " + floor_box.PROBE), 2)

    def test_start_does_nothing_when_the_supervisor_is_already_up(self):
        self.box.probe.update({"run.pid": "4001", "loop.pid": "4002"})
        code, printed = self.run_cmd("start")
        self.assertEqual(code, 0)
        self.assertIn("already running", printed)
        self.assertEqual(self.box.execs(), ["sh -c " + floor_box.PROBE])  # it looked, and did nothing

    def test_start_says_so_when_the_supervisor_does_not_come_up(self):
        original = self.box.exec
        self.box.exec = lambda box, command, **kw: Result("") if "run.sh >" in str(command) else original(box, command, **kw)
        code, printed = self.run_cmd("start")
        self.assertEqual(code, 1)
        self.assertIn("did not come up", printed)

    def test_stop_writes_both_latches_before_it_signals_anything(self):
        self.box.probe.update({"run.pid": "4001", "loop.pid": "4002", "stop": "no", "league_stop": "no"})
        code, printed = self.run_cmd("stop", "--reason", "it's $(time); to stop")
        self.assertEqual(code, 0)
        [latch] = [c for c in self.box.calls if c[0] == "exec" and "stopped by floor_box" in c[1]]
        self.assertIn("for f in /workspace/STOP /workspace/state/STOP; do", latch[1])
        self.assertIn("mkdir -p /workspace/state", latch[1])
        # The reason travels as "$1": it is never part of the shell text.
        self.assertTrue(latch[1].endswith("floor_box it's $(time); to stop"))
        self.assertIn('"$1"', latch[1])
        self.assertLess(self.box.index("stopped by floor_box"), self.box.index("kill -TERM 4002"))
        self.assertLess(self.box.index("kill -TERM 4002"), self.box.index("kill -TERM 4001"))
        self.assertIn("quiesced", printed)
        self.assertIn("stopped_at", floor_box.read_state())

    def test_stop_never_calls_the_first_run_and_never_touches_the_kill_switch_or_the_links(self):
        self.box.probe.update({"run.pid": "4001", "loop.pid": "4002"})
        _, printed = self.run_cmd("stop")
        for text in self.box.execs():
            body = text.replace(floor_box.PROBE, "")
            for forbidden in ("ltcm", "-m league", "python", "/workspace/current", "/workspace/previous", "restart.sh"):
                self.assertNotIn(forbidden, body)
        self.assertIn("agent boxes are the loop's to put to sleep", printed)
        self.assertIn("kill switch", printed)
        self.assertIn("changes neither", printed)

    def test_a_loop_that_will_not_finish_is_killed_and_the_cost_of_that_is_said(self):
        self.box.probe.update({"run.pid": "4001", "loop.pid": "4002"})
        self.box.stubborn_loop = True
        code, printed = self.run_cmd("stop", "--timeout", "20")
        self.assertEqual(code, 0)
        self.assertIn("kill -KILL 4002 2>/dev/null || true", " | ".join(self.box.execs()))
        self.assertIn("did not put its agent boxes to sleep", printed)

    def test_stop_with_nothing_running_still_latches(self):
        code, printed = self.run_cmd("stop")
        self.assertEqual(code, 0)
        self.assertIn("no floor loop was running", printed)
        self.assertTrue([t for t in self.box.execs() if "stopped by floor_box" in t])
        self.assertFalse([t for t in self.box.execs() if "kill -" in t])


class StatusTests(BoxCase):
    probe = {"run.pid": "4001", "loop.pid": "4002", "current": "releases/20260919T080000Z-abcdef012345",
             "previous": "releases/20260918T070000Z-0123456789ab", "runnable": "yes", "league_stop": "yes"}
    HEALTH = {"at": "2026-09-19T08:40:00.000Z", "living": 12, "dead": 3, "ledger_seq": 4567, "real_money": False,
              "release": "20260919T080000Z-abcdef012345",
              "books": {"alpaca-paper": {"frozen": None, "open_orders": 4}, "kalshi-shadow": {"frozen": "drift of $1.20", "open_orders": 0}}}

    def setUp(self):
        super().setUp()
        self.box.files["/workspace/state/health.json"] = json.dumps(self.HEALTH).encode()
        self.box.deploys_jsonl = [
            {"at": "2026-09-19T08:10:00.000Z", "release": "20260919T080000Z-abcdef012345", "stage": "verdict",
             "verdict": "promoted", "reasons": []},
            {"at": "2026-09-19T08:10:01.000Z", "release": "20260919T080000Z-abcdef012345", "stage": "prune", "removed": ["r0"]},
        ]

    def test_json_carries_the_loop_the_releases_the_last_deploy_row_the_health_and_the_log(self):
        code, printed = self.run_cmd("status", "--json", "--tail", "2")
        self.assertEqual(code, 0)
        report = json.loads(printed)
        self.assertEqual(report["loop"], {"supervisor_pid": "4001", "loop_pid": "4002", "alive": True, "probe_error": None,
                                          "stop_latch": False, "league_stop": True})
        self.assertEqual(report["release"]["current"], "20260919T080000Z-abcdef012345")
        self.assertEqual(report["release"]["previous"], "20260918T070000Z-0123456789ab")
        self.assertEqual(report["release"]["current_link"], "releases/20260919T080000Z-abcdef012345")
        self.assertEqual(report["release"]["last_deploy_row"]["stage"], "prune")  # the LAST line, whatever it is
        self.assertFalse(report["release"]["deploy_running"])
        self.assertEqual(report["house_health"], self.HEALTH)
        self.assertEqual(report["log_tail"], ["tick one", "tick two"])
        self.assertNotIn("kill_switch", json.dumps(report))

    def test_it_reads_the_houses_state_dir_and_the_leagues_log(self):
        self.run_cmd("status")
        self.assertEqual([c[1] for c in self.box.calls if c[0] == "download"], ["/workspace/state/health.json"])
        self.assertTrue([t for t in self.box.execs() if "tail -n 15 /workspace/league.log" in t])
        self.assertTrue([t for t in self.box.execs() if "/workspace/deploys.jsonl" in t])

    def test_the_plain_report_says_the_same_things(self):
        _, printed = self.run_cmd("status")
        for wanted in ("current=20260919T080000Z-abcdef012345  previous=20260918T070000Z-0123456789ab",
                       "stop_latch=False league_stop=True", "last deploy  2026-09-19T08:10:01.000Z",
                       "ledger_seq=4567 real_money=False", "kalshi-shadow: FROZEN: drift of $1.20",
                       "alpaca-paper: ok, 4 open order(s)", "/workspace/league.log", "tick two"):
            self.assertIn(wanted, printed)

    def test_a_box_with_nothing_on_it_yet_reads_as_that_not_as_an_error(self):
        self.box.files.clear()
        self.box.deploys_jsonl = []
        self.box.probe.update(current="", previous="", runnable="no")
        self.box.league_log = ""
        code, printed = self.run_cmd("status")
        self.assertEqual(code, 0)
        self.assertIn("current=None  previous=None", printed)
        self.assertIn("no /workspace/state/health.json yet", printed)
        self.assertIn("nothing in /workspace/deploys.jsonl yet", printed)

    def test_a_failed_probe_is_unknown_not_a_dead_loop(self):
        original = self.box.exec
        def exec_(box, command, **kw):
            if floor_box.PROBE in " ".join(command):
                raise SailboxError("disk full")
            return original(box, command, **kw)
        self.box.exec = exec_
        _, printed = self.run_cmd("status", "--json")
        report = json.loads(printed)
        self.assertIsNone(report["loop"]["alive"])
        self.assertIn("disk full", report["loop"]["probe_error"])

    def test_a_pending_release_gets_its_verdict_the_next_time_status_is_read(self):
        state = floor_box.read_state()
        floor_box.remember_release(state, {"id": "20260919T080000Z-abcdef012345", "verdict": "pending", "reasons": []})
        floor_box.write_state(state)
        self.run_cmd("status")
        entry = floor_box.read_state()["releases"][-1]
        self.assertEqual((entry["verdict"], entry["verdict_at"]), ("promoted", "2026-09-19T08:10:00.000Z"))

    def test_logs_tails_the_leagues_log_and_the_deploy_log_on_request(self):
        _, printed = self.run_cmd("logs", "-n", "7")
        self.assertIn("tick two", printed)
        self.assertIn("tail -n 7 /workspace/league.log", self.box.execs()[-1])
        self.run_cmd("logs", "--deploy")
        self.assertIn("tail -n 100 /workspace/deploy.log", self.box.execs()[-1])


class CreateTests(BoxCase):
    def setUp(self):
        super().setUp()
        floor_box.write_state({})

    def test_create_lays_out_the_box_and_leaves_the_code_to_deploy(self):
        code, printed = self.run_cmd("create")
        self.assertEqual(code, 0)
        state = floor_box.read_state()
        self.assertEqual((state["box_id"], state["python"], state["releases"]), ("sb_new", PYTHON, []))
        self.assertNotIn("uploads", state)
        self.assertFalse([t for t in self.box.uploads() if t.endswith(".tgz")])
        layout = [t for t in self.box.execs() if "mkdir -p /workspace/releases" in t][0]
        for wanted in ("/workspace/state", "/workspace/canary", "/workspace/incoming", "touch /workspace/league.log"):
            self.assertIn(wanted, layout)
        self.assertEqual(self.box.files["/workspace/run.sh.new"], floor_box.render(floor_box.RUN_SH, PYTHON))
        self.assertLess(printed.index("floor_box.py secrets"), printed.index("floor_box.py deploy"))
        self.assertLess(printed.index("floor_box.py deploy"), printed.index("floor_box.py start"))

    def test_missing_numpy_stops_setup_instead_of_leaving_a_nonfunctional_house(self):
        self.box.pip_fails = True
        with self.assertRaisesRegex(SystemExit, "numpy installation failed"):
            self.run_cmd("create")
        self.assertFalse(any("cryptography" in call for call in self.box.execs()))

    def test_without_a_venv_the_system_interpreter_is_recorded(self):
        self.box.venv = False
        self.run_cmd("create")
        self.assertEqual(floor_box.read_state()["python"], "python3")
        self.assertIn(b"python3 -m league run", self.box.files["/workspace/run.sh.new"])


class HistoryTests(BoxCase):
    """`/workspace/ltcm`, `/workspace/.data`, `/workspace/.archive` and `/workspace/league.log` are the
    first run's record. No command, upload or download the script issues for the league names
    them, whatever order the owner runs things in."""

    def everything_issued(self) -> list[str]:
        home = Path(self.temp.name)
        (home / "league").mkdir()
        (home / "league" / "config.json").write_text('{"gateway_url": "https://gw.example.workers.dev"}', encoding="utf-8")
        env = home / ".env"
        env.write_bytes(b"SAIL_API_KEY=sail-1\nGATEWAY_TOKEN=gw-1\nCAPITAL_PUBLISH_TOKEN=pub-1\nKALSHI_KEY_ID=venue\n")
        env.chmod(0o600)
        issued: list[str] = []
        floor_box.write_state({})
        self.run_cmd("create")
        with mock.patch.object(floor_box, "REPO_ROOT", home):
            self.run_cmd("secrets")
        issued += self.box.everything()
        for probe, commands in (
            ({}, [("deploy",), ("deploy", "--no-wait")]),
            ({"current": "releases/20260918T070000Z-0123456789ab", "runnable": "yes"}, [("start",), ("status",), ("status", "--json"), ("logs",), ("logs", "--deploy")]),
            ({"run.pid": "4001", "loop.pid": "4002", "current": "releases/20260918T070000Z-0123456789ab", "runnable": "yes"},
             [("deploy",), ("stop",), ("fork", "--from", "sbcp_1")]),
        ):
            for argv in commands:
                self.box = FakeBox(**probe)
                self.box.verdict = "promoted"
                self.box.files["/workspace/run.sh"] = floor_box.render(floor_box.RUN_SH, PYTHON)
                self.run_cmd(*argv)
                issued += self.box.everything()
        return issued

    def test_nothing_issued_names_a_history_path(self):
        issued = self.everything_issued()
        self.assertGreater(len(issued), 60)
        for text in issued:
            for history in HISTORY:
                self.assertNotIn(history, text + " ")

    def test_everything_destructive_stays_inside_the_leagues_own_paths(self):
        allowed = ("/workspace/incoming", "/workspace/.upload/", "/workspace/STOP", "/workspace/state/STOP",
                   "/workspace/run.pid", "/workspace/loop.pid", "/workspace/deploy.pid")
        for text in self.everything_issued():
            for match in re.finditer(r"\brm\s+(-\w+\s+)*([^;&|]+)", text.replace(floor_box.PROBE, "")):
                for target in match.group(2).split():
                    self.assertTrue(target.startswith(allowed), f"{target!r} in {text!r}")
            self.assertNotRegex(text, r"tar -xzf \S+ -C /workspace(\s|$)")

    def test_in_gateway_mode_secrets_deletes_nothing_and_says_whose_step_an_old_key_is(self):
        home = Path(self.temp.name)
        (home / "league").mkdir()
        (home / "league" / "config.json").write_text('{"gateway_url": "https://gw.example.workers.dev"}', encoding="utf-8")
        env = home / ".env"
        env.write_bytes(b"SAIL_API_KEY=sail-1\nGATEWAY_TOKEN=gw-1\nCAPITAL_PUBLISH_TOKEN=pub-1\n")
        env.chmod(0o600)
        floor_box.write_state({"box_id": "sb_1", "secret_names": [".env", "kalshi.pem"]})
        with mock.patch.object(floor_box, "REPO_ROOT", home):
            code, printed = self.run_cmd("secrets")
        self.assertEqual(code, 0)
        self.assertEqual(self.box.execs(), [])
        self.assertEqual(self.box.uploads(), ["/workspace/.env"])
        self.assertIn("kalshi.pem", printed)
        self.assertIn("owner's step", printed)
        state = floor_box.read_state()
        self.assertEqual((state["secret_names"], state["legacy_key_names"]), ([".env"], ["kalshi.pem"]))


class LeagueHostsTests(unittest.TestCase):
    def test_only_current_services_are_required(self):
        have = ["api.sailresearch.com", "sailbox-api.sailresearch.com", "blakewoods.us", "*.workers.dev"]
        with mock.patch.object(floor_box, "floor_config", lambda: {"gateway_url": "https://gw.example.workers.dev/"}):
            missing = floor_box.missing_league_hosts(have)
            self.assertIn("gw.example.workers.dev", missing)
            self.assertIn("api.github.com", missing)
            self.assertFalse(any("kalshi" in x or "weather" in x for x in missing))
            self.assertEqual(floor_box.missing_league_hosts(have + missing), [])


# --------------------------------------------------------------------------- the structures guard
# The review of Deploy G (Sept 25, 2026): nothing mechanical stopped a rollback, or a deploy, of a release older than
# G while alpaca-paper holds a structure. The older code cannot fold the venue's legs (the practice book freezes for
# every agent on it) and its wind-down sells a structure's first leg alone: a naked short.

CODE = "debit_vertical|+1SPY260928C00580000|-1SPY260928C00581000"
HELD = {"structures": [{"agent": "structure-7", "code": CODE, "quantity": "1"}], "orders": []}
LACKS = [rel + ": " + marker for rel, marker in floor_box.STRUCTURE_AWARE_MARKERS]


def guard_asks(box: FakeBox) -> list[dict]:
    """The JSON argument of each structures check the script ran on the box (its last argv element)."""
    return [json.loads(command[-1]) for command in box.raw if not isinstance(command, str)
            and floor_box.STRUCTURE_GUARD_SNIPPET in command]


class RollbackTests(BoxCase):
    """`rollback` asks the in-box watchdog to roll back, from the previous release, after the structures guard."""

    probe = {"run.pid": "4001", "loop.pid": "4002", "current": "releases/20260918T070000Z-0123456789ab",
             "previous": "releases/20260917T070000Z-ba9876543210", "runnable": "yes"}

    def rollbacks(self) -> list[tuple]:
        return [c for c in self.box.calls if c[0] == "exec" and "-m league.watchdog rollback" in c[1]]

    def guard_asks(self) -> list[dict]:
        return guard_asks(self.box)

    def test_a_structure_aware_previous_release_is_rolled_back_to_by_the_watchdog_with_the_reason_as_a_parameter(self):
        code, printed = self.run_cmd("rollback", "--reason", "G's watch; rm -rf / $(x)")
        self.assertEqual(code, 0)
        [ask] = self.guard_asks()
        self.assertEqual(ask["release"], "/workspace/previous")
        self.assertEqual(ask["book"], "alpaca-paper")
        [command] = [c for c in self.box.raw if not isinstance(c, str) and "-m league.watchdog rollback" in " ".join(c)]
        # The reason is a positional parameter, never shell text; it runs from the previous release's code.
        self.assertEqual(command, ["sh", "-c", 'cd "$1" && exec "$2" -m league.watchdog rollback --base "$3" --reason "$4"',
                                   "floor_box", "/workspace/previous", PYTHON, "/workspace", "G's watch; rm -rf / $(x)"])
        self.assertEqual(len(self.rollbacks()), 1)
        self.assertIn("ROLLED BACK: 20260918T070000Z-0123456789ab -> 20260917T070000Z-ba9876543210", printed)
        self.assertIn("--ratify options-swarm-20260928", printed)
        self.assertLess(self.box.index("floor_box structure guard"), self.box.index("-m league.watchdog rollback"))

    def test_past_g_while_alpaca_paper_holds_a_structure_is_refused_and_nothing_is_rolled_back(self):
        self.box.previous_missing = list(LACKS)
        self.box.ledger = dict(HELD)
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("rollback")
        refusal = str(caught.exception)
        self.assertTrue(refusal.startswith("REFUSED: the previous release 20260917T070000Z-ba9876543210 lacks the structure-aware practice code"))
        self.assertIn(f"structure-7 holds 1 {CODE}", refusal)
        self.assertIn("naked short", refusal)
        self.assertIn("--force-structures-risk", refusal)
        self.assertEqual(self.rollbacks(), [])

    def test_an_open_structure_order_refuses_it_too(self):
        self.box.previous_missing = LACKS[:1]
        self.box.ledger = {"structures": [], "orders": [{"order_id": "o-9", "code": CODE, "side": "buy", "status": "accepted"}]}
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("rollback")
        self.assertIn(f"order o-9 (buy {CODE}, accepted)", str(caught.exception))
        self.assertEqual(self.rollbacks(), [])

    def test_past_g_with_alpaca_paper_flat_goes(self):
        self.box.previous_missing = list(LACKS)
        code, printed = self.run_cmd("rollback")
        self.assertEqual(code, 0)
        self.assertIn("the ledger shows no structure held or ordered on alpaca-paper, so it may go", printed)
        self.assertEqual(len(self.rollbacks()), 1)

    def test_a_check_that_cannot_read_the_box_refuses(self):
        self.box.guard_error = "OperationalError: unable to open database file"
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("rollback")
        self.assertIn("could not be read (OperationalError: unable to open database file)", str(caught.exception))
        self.assertEqual(self.rollbacks(), [])

    def test_the_owner_can_force_it_and_is_warned_loudly(self):
        self.box.previous_missing = list(LACKS)
        self.box.ledger = dict(HELD)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code, printed = self.run_cmd("rollback", "--force-structures-risk")
        self.assertEqual(code, 0)
        self.assertIn("WARNING: --force-structures-risk: the previous release", printed)
        self.assertIn("WARNING: --force-structures-risk", errors.getvalue())
        self.assertEqual(len(self.rollbacks()), 1)

    def test_no_rollback_during_a_deploy_or_without_a_previous_release(self):
        self.box.probe["deploy.pid"] = "5001"
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("rollback")
        self.assertIn("a deploy is running", str(caught.exception))
        self.box.probe.update({"deploy.pid": "-", "previous": ""})
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("rollback")
        self.assertIn("no previous release", str(caught.exception))
        self.assertEqual((self.rollbacks(), self.guard_asks()), ([], []))

    def test_a_rollback_the_watchdog_could_not_make_is_exit_one(self):
        self.box.rollback_answer = {"ok": False, "error": "no previous release to roll back to", "current": "x"}
        code, printed = self.run_cmd("rollback")
        self.assertEqual(code, 1)
        self.assertIn("ROLLBACK FAILED: no previous release to roll back to", printed)


class DeployStructureGuardTests(BoxCase):
    """`deploy` sends no tree without the structure-aware practice code while alpaca-paper holds a structure."""

    probe = DeployTests.probe

    def setUp(self):
        super().setUp()
        self.box.files["/workspace/run.sh"] = floor_box.render(floor_box.RUN_SH, PYTHON)
        self.box.verdict = "promoted"

    def test_a_tree_before_g_is_refused_while_alpaca_paper_holds_a_structure(self):
        self.box.ledger = dict(HELD)
        with self.assertRaises(SystemExit) as caught:
            self.run_cmd("deploy")
        self.assertTrue(str(caught.exception).startswith("REFUSED: this working tree lacks the structure-aware practice code"))
        self.assertEqual(self.box.uploads(), [])
        self.assertFalse([t for t in self.box.execs() if "-m league.watchdog deploy" in t])
        [ask] = guard_asks(self.box)
        self.assertEqual((ask["release"], ask["state"], ask["book"]), (None, "/workspace/state", "alpaca-paper"))

    def test_a_ledger_that_cannot_be_read_refuses_it_and_force_sends_it(self):
        self.box.guard_error = "the box could not run the check"
        with self.assertRaises(SystemExit):
            self.run_cmd("deploy")
        self.assertEqual(self.box.uploads(), [])
        with contextlib.redirect_stderr(io.StringIO()):
            code, printed = self.run_cmd("deploy", "--force-structures-risk")
        self.assertEqual(code, 0)
        self.assertIn("WARNING: --force-structures-risk: this working tree lacks", printed)
        self.assertEqual(len([u for u in self.box.uploads() if u.endswith(".tgz")]), 1)

    def test_a_tree_with_the_structure_code_never_reads_the_ledger(self):
        tree = [Path("league/__main__.py"), Path("league/config.json"), Path("league/live/real.py"), Path("league/live/paper.py")]
        self.box.ledger = dict(HELD)
        with mock.patch.object(floor_box, "code_files", lambda: list(tree)):
            code, _ = self.run_cmd("deploy")
        self.assertEqual(code, 0)
        self.assertFalse([t for t in self.box.execs() if "floor_box structure guard" in t])

    def test_the_markers_are_read_from_the_files_sent(self):
        self.assertEqual(floor_box.structure_gaps([Path("league/live/real.py"), Path("league/live/paper.py")]), [])
        self.assertEqual(floor_box.structure_gaps([Path("league/live/real.py")]), [LACKS[1]])
        self.assertEqual(floor_box.structure_gaps([]), LACKS)


class StructureGuardSnippetTests(unittest.TestCase):
    """The read-only snippet, run for real against a ledger written here, as the box's interpreter runs it."""

    NOW = real_time.time()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.seq = 0

    def iso(self, ago: float = 0.0) -> str:
        return real_time.strftime("%Y-%m-%dT%H:%M:%S.000Z", real_time.gmtime(self.NOW - ago))

    def ledger(self, rows: list[tuple[str, str, dict]], *, ago: float = 0.0) -> None:
        import sqlite3
        from league.ledger import SCHEMA
        db = sqlite3.connect(self.state / "ledger.sqlite")
        db.executescript(SCHEMA)
        for kind, agent, payload in rows:
            self.seq += 1
            db.execute("insert into ledger (id, kind, agent, at, public, payload, previous_hash, digest) values (?,?,?,?,?,?,?,?)",
                       (f"r{self.seq}", kind, agent, payload.pop("_at", self.iso(ago)), 1,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")), "p", f"d{self.seq}"))
        db.commit()
        db.close()

    @staticmethod
    def inst(code: str | None = CODE, venue: str = "alpaca") -> dict:
        return {"asset_class": "option", "symbol": "SPY", "venue": venue, "multiplier": "100", "expiry": "2026-09-28",
                "strike": "580", "right": "call", "market_id": code, "currency": "USD"}

    def fill(self, delta: str, *, book: str = "alpaca-paper", code: str | None = CODE) -> dict:
        return {"book": book, "instrument": self.inst(code), "position_delta": delta, "cash_delta": "0", "quantity": delta.lstrip("-")}

    def order(self, order_id: str, status: str, *, side: str = "buy", reason: str = "", at: str | None = None) -> dict:
        row = {"book": "alpaca-paper", "order_id": order_id, "instrument": self.inst(), "side": side, "status": status,
               "reason": reason, "quantity": "1", "order_type": "limit", "shares": [{"agent": "structure-9", "intent_id": "i", "quantity": "1"}]}
        if at:
            row["_at"] = at
        return row

    def run_guard(self, release: Path | None = None) -> dict:
        ask = {"state": str(self.state), "release": str(release) if release else None, "book": "alpaca-paper",
               "markers": [list(pair) for pair in floor_box.STRUCTURE_AWARE_MARKERS], "house": floor_box.LEDGER_HOUSE,
               "terminal": list(floor_box.TERMINAL_STATUSES), "never_arrived": floor_box.NEVER_ARRIVED,
               "recheck_seconds": floor_box.NEVER_ARRIVED_RECHECK_SECONDS}
        done = subprocess.run([sys.executable, "-c", floor_box.STRUCTURE_GUARD_SNIPPET, json.dumps(ask)],
                              capture_output=True, text=True, timeout=60, cwd="/")
        self.assertEqual(done.returncode, 0, done.stderr)
        [line] = done.stdout.splitlines()
        return json.loads(line)

    def test_it_folds_structure_positions_on_alpaca_paper_only(self):
        self.ledger([
            ("book.fill", "structure-1", self.fill("1")),                        # held
            ("book.fill", "structure-2", self.fill("2")), ("book.fill", "structure-2", self.fill("-2")),   # closed
            ("book.fill", "structure-3", self.fill("1")), ("book.settle", "structure-3", {"book": "alpaca-paper", "instrument": self.inst(), "payout": "0"}),
            ("book.fill", "structure-4", self.fill("1", book="options-shadow")),  # another book
            ("book.fill", "structure-5", self.fill("1", code=None)),             # a single contract
            ("book.fill", "structure-6", self.fill("-1")), ("book.fill", "structure-6", self.fill("1")),  # oversold, then held
            ("book.fill", "house", self.fill("-1")),                              # the House row's break row, short
        ])
        answer = self.run_guard()
        self.assertTrue(answer["checked"])
        self.assertEqual(answer["structures"], [{"agent": "house", "code": CODE, "quantity": "-1"},
                                                {"agent": "structure-1", "code": CODE, "quantity": "1"},
                                                {"agent": "structure-6", "code": CODE, "quantity": "1"}])
        self.assertEqual(answer["orders"], [])

    def test_open_structure_orders_and_a_buy_the_book_still_asks_about_count(self):
        self.ledger([
            ("book.order", "house", self.order("o-open", "new")),
            ("book.order", "house", self.order("o-done", "new")), ("book.order", "house", self.order("o-done", "filled")),
            ("book.order", "house", self.order("o-lost", "rejected", reason=floor_box.NEVER_ARRIVED)),
            ("book.order", "house", self.order("o-old", "rejected", reason=floor_box.NEVER_ARRIVED, at=self.iso(3600))),
            ("book.order", "house", self.order("o-sell", "rejected", side="sell", reason=floor_box.NEVER_ARRIVED)),
        ])
        answer = self.run_guard()
        self.assertEqual(sorted(row["order_id"] for row in answer["orders"]), ["o-lost", "o-open"])
        self.assertEqual(answer["orders"][0]["agents"], ["structure-9"])
        self.assertEqual(answer["structures"], [])

    def test_a_release_with_the_code_is_never_read_past_and_one_without_it_is_named(self):
        (self.state / "ledger.sqlite").write_bytes(b"not a database")
        release = self.root / "releases" / "g"
        (release / "league" / "live").mkdir(parents=True)
        (release / "league" / "live" / "real.py").write_text("class RealBook:\n")
        (release / "league" / "live" / "paper.py").write_text("class PaperProof:\n")
        link = self.root / "previous"
        link.symlink_to(release)
        answer = self.run_guard(link)
        self.assertEqual(answer, {"release": {"dir": str(release.resolve()), "missing": []}, "checked": False, "structures": [], "orders": []})
        (release / "league" / "live" / "paper.py").write_text("# no proof\n")
        answer = self.run_guard(link)
        self.assertIn("error", answer)  # the ledger is read now, and cannot be: the caller refuses
        self.assertIn("DatabaseError", answer["error"])

    def test_an_absent_ledger_holds_nothing_and_a_read_only_one_is_read(self):
        self.assertEqual(self.run_guard(), {"release": None, "checked": True, "ledger": "absent", "structures": [], "orders": [], "rows": 0})
        self.ledger([("book.fill", "structure-1", self.fill("1"))])
        (self.state / "ledger.sqlite").chmod(0o444)
        self.state.chmod(0o555)
        self.addCleanup(self.state.chmod, 0o755)
        self.assertEqual(self.run_guard()["structures"], [{"agent": "structure-1", "code": CODE, "quantity": "1"}])

    def test_current_live_inventory_or_frozen_recon_refuses_an_old_release(self):
        from league.live.state import LiveState
        state = LiveState(self.state / "live.sqlite")
        try:
            state.put("paper_proof", {"status": "open_sent", "open_cid": "lost-post"})
            self.assertEqual(self.run_guard()["orders"][0]["order_id"], "paper-proof")
            state.put("paper_proof", {"status": "passed"})
            self.assertEqual(self.run_guard()["orders"], [])
            state.put("paper_proof", {"status": "passed", "inventory": {"synthetic-contract": "1"}})
            self.assertEqual(self.run_guard()["orders"][0]["order_id"], "paper-proof")
            state.put("paper_proof", {"status": "passed"})
            state.put("recon", {"frozen": "unknown venue inventory"})
            self.assertIn("frozen", self.run_guard()["error"])
        finally:
            state.close()
        (self.state / "live.sqlite").write_bytes(b"corrupt")
        self.assertIn("error", self.run_guard())

    def test_its_constants_are_the_houses_own(self):
        from league import ledger
        self.assertEqual(floor_box.NEVER_ARRIVED, "the venue has no such order")
        self.assertEqual(floor_box.NEVER_ARRIVED_RECHECK_SECONDS, 900)
        self.assertEqual(floor_box.LEDGER_HOUSE, ledger.HOUSE)
        self.assertEqual(floor_box.STRUCTURE_PRACTICE_BOOK, "alpaca-paper")
        # This tree carries both markers (it is Deploy G or later).
        for rel, marker in floor_box.STRUCTURE_AWARE_MARKERS:
            self.assertIn(marker, (REPO_ROOT / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
