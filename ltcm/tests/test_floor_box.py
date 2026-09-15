"""The operator CLI's offline parts: what gets uploaded, what never does, and what run.sh says.

`scripts/floor_box.py` is loaded the way `test_import_research_bank.py` loads its script, so the
repository runs without being installed. Nothing here creates a Sailbox: the commands that would
are driven against a fake client, and the rest is pure local logic.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

import ltcm
from ltcm.sailbox import FLOOR_HOSTS

REPO_ROOT = Path(ltcm.__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "floor_box.py"


def load():
    spec = importlib.util.spec_from_file_location("floor_box_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


floor_box = load()
floor_box_client = floor_box.client


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
        for name in ("ltcm/service.py", "ltcm/config.json", "playbooks/merton.md",
                     "scripts/floor_box.py", "deploy/README.md", "deploy/ltcm.service"):
            with self.subTest(name=name):
                self.assertFalse(floor_box.is_secret(Path(name)))

    def test_the_bundle_carries_the_floor_and_nothing_private(self):
        files = {str(p) for p in floor_box.code_files()}
        for wanted in ("ltcm/service.py", "ltcm/config.json", "ltcm/sailbox.py",
                       "ltcm/hostinfo.py", "scripts/floor_box.py", "deploy/README.md"):
            self.assertIn(wanted, files)
        for forbidden in (".env", ".data/ltcm/keys/kalshi.pem"):
            self.assertNotIn(forbidden, files)
        self.assertFalse([f for f in files if f.endswith((".pem", ".pyc", ".sqlite"))])
        self.assertFalse([f for f in files if "__pycache__" in f])
        self.assertFalse([f for f in files if f.startswith(".data")])

    def test_the_bundle_carries_the_desks_the_playbooks_and_the_tests(self):
        files = {str(p) for p in floor_box.code_files()}
        self.assertTrue([f for f in files if f.startswith("ltcm/desks/")])
        self.assertTrue([f for f in files if f.startswith("playbooks/")])
        self.assertTrue([f for f in files if f.startswith("ltcm/tests/")])
        self.assertTrue([f for f in files if f.startswith("ltcm/adapters/")])


class SecretsCommandTests(unittest.TestCase):
    """`secrets` is the one command that reads a credential, so it is tested with fake ones."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        (home / ".data" / "ltcm" / "keys").mkdir(parents=True)
        self.env = home / ".env"
        self.env.write_bytes(b"NOT_A_REAL_KEY=xyz\n")
        self.env.chmod(0o600)
        self.key = home / ".data" / "ltcm" / "keys" / "kalshi.pem"
        self.key.write_bytes(b"-----BEGIN FAKE-----\n")
        self.key.chmod(0o600)

        self.originals = (floor_box.REPO_ROOT, floor_box.STATE_PATH, floor_box.client)
        floor_box.REPO_ROOT = home
        floor_box.STATE_PATH = home / "box.json"
        self.addCleanup(self._restore)
        floor_box.write_state({"box_id": "sb_1"})
        self.uploads: list[tuple[str, bytes, int]] = []
        floor_box.client = lambda: self._fake()

    def _restore(self):
        floor_box.REPO_ROOT, floor_box.STATE_PATH, floor_box.client = self.originals

    def _fake(self):
        uploads = self.uploads

        class Fake:
            def exec(self, _box, _command, **_kw):
                class Result:
                    stdout = "-rw------- kalshi.pem"
                    output = stdout

                    def check(self):
                        return self
                return Result()

            def upload(self, _box, target, content, *, mode=0o600, **_kw):
                uploads.append((target, content, mode))
                return {"size_bytes": len(content)}

        return Fake()

    def run_it(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = floor_box.cmd_secrets(floor_box.build_parser().parse_args(["secrets"]))
        return code, buffer.getvalue()

    def test_both_the_env_and_the_keys_land_in_the_right_place_mode_600(self):
        code, _ = self.run_it()
        self.assertEqual(code, 0)
        self.assertEqual(
            sorted((t, m) for t, _c, m in self.uploads),
            [("/workspace/.data/ltcm/keys/kalshi.pem", 0o600), ("/workspace/.env", 0o600)],
        )

    def test_the_bytes_are_sent_unchanged_and_never_printed(self):
        _code, printed = self.run_it()
        sent = {target: content for target, content, _m in self.uploads}
        self.assertEqual(sent["/workspace/.env"], self.env.read_bytes())
        self.assertEqual(sent["/workspace/.data/ltcm/keys/kalshi.pem"], self.key.read_bytes())
        self.assertNotIn("NOT_A_REAL_KEY", printed)
        self.assertNotIn("xyz", printed)
        self.assertNotIn("BEGIN FAKE", printed)
        self.assertIn(".env", printed)
        self.assertIn("19 bytes", printed)

    def test_a_readable_by_anyone_credential_is_refused_before_it_is_sent(self):
        self.key.chmod(0o644)
        with self.assertRaises(SystemExit) as caught:
            self.run_it()
        self.assertIn("chmod 600", str(caught.exception))
        self.assertEqual(self.uploads, [])

    def test_the_state_file_records_the_names_only(self):
        self.run_it()
        state = floor_box.read_state()
        self.assertEqual(state["secret_names"], [".env", "kalshi.pem"])
        self.assertNotIn("xyz", floor_box.STATE_PATH.read_text(encoding="utf-8"))

    def test_nothing_to_send_says_so_rather_than_creating_an_empty_env(self):
        self.env.unlink()
        self.key.unlink()
        with self.assertRaises(SystemExit):
            self.run_it()
        self.assertEqual(self.uploads, [])


class BundleTests(unittest.TestCase):
    def test_the_tar_round_trips_with_the_paths_the_box_expects(self):
        files = [Path("ltcm/config.json"), Path("deploy/README.md")]
        blob = floor_box.tarball(files)
        with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
            names = archive.getnames()
            self.assertEqual(sorted(names), ["deploy/README.md", "ltcm/config.json"])
            member = archive.extractfile("ltcm/config.json").read()
        self.assertEqual(member, (REPO_ROOT / "ltcm" / "config.json").read_bytes())

    def test_the_tar_is_deterministic_so_a_redeploy_is_not_noise(self):
        files = [Path("ltcm/config.json")]
        self.assertEqual(floor_box.tarball(files), floor_box.tarball(files))

    def test_shell_scripts_arrive_executable(self):
        with tarfile.open(fileobj=io.BytesIO(floor_box.tarball([Path("ltcm/config.json")]))) as a:
            self.assertEqual(a.getmember("ltcm/config.json").mode, 0o644)


class SupervisorScriptTests(unittest.TestCase):
    def script(self, python="/workspace/.venv/bin/python"):
        return floor_box.render(floor_box.RUN_SH, python).decode()

    def test_it_runs_the_floor_with_the_interpreter_that_has_cryptography(self):
        self.assertIn("/workspace/.venv/bin/python -m ltcm run", self.script())
        self.assertIn("python3 -m ltcm run", self.script("python3"))

    def test_it_waits_thirty_seconds_between_restarts(self):
        self.assertIn("sleep 30", self.script())

    def test_everything_goes_to_the_one_log(self):
        body = self.script()
        self.assertIn(">> /workspace/ltcm.log 2>&1", body)
        self.assertIn("supervisor: floor loop exited", body)

    def test_the_stop_latch_ends_the_loop_rather_than_restarting_it(self):
        body = self.script()
        self.assertIn("while [ ! -e /workspace/STOP ]", body)
        self.assertIn("[ -e /workspace/STOP ] && break", body)

    def test_both_pids_are_written_down_so_stop_can_find_them(self):
        body = self.script()
        self.assertIn("echo $$ > /workspace/run.pid", body)
        self.assertIn("/workspace/loop.pid", body)

    def test_restart_signals_the_loop_and_leaves_the_supervisor_alone(self):
        body = floor_box.render(floor_box.RESTART_SH, "python3").decode()
        self.assertIn("/workspace/loop.pid", body)
        self.assertIn('kill -TERM "$pid"', body)
        self.assertNotIn("run.pid", body)

    def test_the_probe_reports_both_pids_the_latch_and_the_kill_switch(self):
        for marker in ("run.pid", "loop.pid", "/workspace/STOP", "/workspace/.data/ltcm/KILL"):
            self.assertIn(marker, floor_box.PROBE)


class ShellSafetyTests(unittest.TestCase):
    """`python -m ltcm` on the box runs through a shell, so nothing may be interpolated blind."""

    def test_the_kill_reason_is_a_positional_parameter_not_shell_text(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('-m ltcm kill --reason "$1"', source)
        self.assertIn('"floor_box", args.reason', source)

    def test_every_ltcm_command_on_the_box_changes_into_the_workspace_first(self):
        # An exec's working directory on a Sailbox is `/`, where `ltcm` is not importable.
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exec"
        ]
        self.assertTrue(calls)
        checked = 0
        for call in calls:
            segment = ast.get_source_segment(source, call) or ""
            if "-m ltcm" in segment:
                checked += 1
                self.assertIn("cd ", segment, msg=segment)
        self.assertGreaterEqual(checked, 2)

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


class ParserTests(unittest.TestCase):
    def test_every_command_the_owner_is_told_about_exists(self):
        parser = floor_box.build_parser()
        for command in ("create", "secrets", "start", "stop", "status", "logs", "deploy",
                        "checkpoint", "fork", "sleep", "resume", "terminate"):
            with self.subTest(command=command):
                self.assertEqual(parser.parse_args(_args(command)).command, command)

    def test_terminate_needs_the_owner_to_say_yes(self):
        self.assertFalse(floor_box.build_parser().parse_args(["terminate"]).yes)

    def test_stop_waits_two_minutes_by_default(self):
        self.assertEqual(floor_box.build_parser().parse_args(["stop"]).timeout, 120.0)

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
