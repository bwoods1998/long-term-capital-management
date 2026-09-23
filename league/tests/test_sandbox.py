"""Adversarial tests of `league/sandbox.py`.

`LocalSandbox` is driven for real (a subprocess in a private directory). `SailSandbox` is driven
against `FakeSail`, a scripted stand-in for `ltcm.sailbox.SailboxClient` that keeps every call in
order, models each box's status, egress policy and files, and whose `exec` reads the uploaded
`spec.json` to find the run's token, as the real `runner.py` would.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league import sandbox as sandbox_module
from league.sandbox import KIT_FILES, REMOTE_DIR, SEALED, LocalSandbox, Run, SailSandbox, SandboxError, kit_files

IMAGE = "cp_clean_image"

TINY = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "tiny", "symbols": ["BTC/USD"]}
PARAMS = {"notional": 20.0}

def decide(ctx):
    held = [p for p in ctx.get("positions", []) if p["symbol"] == "BTC/USD"]
    if held:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "off"}],
                "thought": "selling", "memory": {"sold": True}}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": ctx["params"]["notional"], "type": "market", "reason": "on"}],
            "thought": "buying", "memory": {"bought": True}}
'''


def tiny_tape(hours: int = 4) -> dict:
    """A sawtooth: low on even five-minute bars, high on odd ones."""
    steps = []
    for hour in range(hours):
        for minute in range(0, 60, 5):
            price = 80000.0 * (1.01 if (minute // 5) % 2 else 0.99)
            steps.append({"t": f"2026-09-10T{hour:02d}:{minute:02d}:00Z", "bars": {"BTC/USD": {"o": price, "h": price, "l": price, "c": price, "v": 1.0}}})
    return {"venue": "alpaca", "horizon": "hour", "step_seconds": 300, "half_spread_bps": 0.5, "steps": steps, "results": {}}


# =================================================================================================
# LocalSandbox
# =================================================================================================
class Local(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.box = LocalSandbox(Path(self.dir.name) / "boxes")

    def tearDown(self):
        self.dir.cleanup()

    def test_it_says_it_is_not_a_security_boundary(self):
        self.assertFalse(LocalSandbox.secure)
        self.assertTrue(SailSandbox.secure)

    def test_decide_round_trip(self):
        run = self.box.decide("tiny-1", TINY, {"positions": [], "params": {"notional": 35.0}})
        self.assertIsInstance(run, Run)
        self.assertTrue(run.result["ok"], run.result)
        self.assertEqual(run.result["intents"][0]["notional_usd"], 35.0)
        self.assertEqual(run.result["memory"], {"bought": True})
        self.assertGreater(run.seconds, 0)
        self.assertFalse(run.created)
        directory = Path(self.dir.name) / "boxes" / "tiny-1"
        self.assertEqual(sorted(p.name for p in directory.iterdir() if p.is_file()), ["options_history.py", "options_replay.py", "replay.py", "runner.py", "safety.py", "spec.json"])

    def test_decide_sees_positions(self):
        run = self.box.decide("tiny-1", TINY, {"positions": [{"symbol": "BTC/USD", "quantity": 0.001}], "params": {}})
        self.assertEqual((run.result["intents"][0]["side"], run.result["thought"]), ("sell", "selling"))

    def test_needs_round_trip(self):
        run = self.box.needs("probe", TINY)
        self.assertEqual(run.result, {"ok": True, "needs": {"venue": "alpaca", "horizon": "hour", "style": "tiny", "symbols": ["BTC/USD"]}, "params": {"notional": 20.0}})

    def test_strategy_errors_come_back_in_the_result(self):
        self.assertIn("code refused", self.box.decide("bad", "import os\ndef decide(ctx):\n    return {}\n", {}).result["error"])
        self.assertIn("ZeroDivisionError", self.box.decide("bad", "def decide(ctx):\n    return 1 / 0\n", {}).result["error"])
        self.assertFalse(self.box.needs("bad", "def nothing():\n    pass\n").result["ok"])

    def test_a_forged_result_line_is_not_believed(self):
        code = "def decide(ctx):\n    print('DECIDE-RESULT  {\"ok\": true, \"intents\": [{\"symbol\": \"FORGED\"}]}')\n    return {'thought': 'honest'}\n"
        run = self.box.decide("forger", code, {})
        self.assertEqual((run.result["thought"], run.result["intents"]), ("honest", []))

    def test_each_run_has_its_own_token(self):
        self.box.decide("tiny-1", TINY, {})
        first = json.loads((Path(self.dir.name) / "boxes" / "tiny-1" / "spec.json").read_text())["token"]
        self.box.decide("tiny-1", TINY, {})
        second = json.loads((Path(self.dir.name) / "boxes" / "tiny-1" / "spec.json").read_text())["token"]
        self.assertEqual((len(first), len(second)), (32, 32))
        self.assertNotEqual(first, second)

    def test_the_environment_is_not_inherited(self):
        with mock.patch.dict(os.environ, {"LTCM_GATEWAY_TOKEN": "do-not-leak"}), mock.patch.object(subprocess, "run", wraps=subprocess.run) as spawned:
            self.box.decide("tiny-1", TINY, {})
        self.assertEqual(set(spawned.call_args.kwargs["env"]), {"PATH"})

    def broken_kit(self, program: str):
        """The kit with `runner.py` replaced at its SOURCE. (The agent's own copy cannot be used
        for this: `_dir` puts the real file back before every run.)"""
        source = Path(self.dir.name) / "stand-in-runner.py"
        source.write_text(program)
        return mock.patch.dict(sandbox_module.KIT_FILES, {"runner.py": str(source)})

    def test_a_program_that_prints_no_result_line_is_an_error_result(self):
        with self.broken_kit("import sys\nsys.stderr.write('kit is broken')\nsys.exit(3)\n"):
            run = self.box.decide("broken", TINY, {})
        self.assertFalse(run.result["ok"])
        self.assertIn("no result line (exit 3)", run.result["error"])
        self.assertIn("kit is broken", run.result["error"])

    def test_a_run_past_the_timeout_is_an_error_result_not_a_hang(self):
        with self.broken_kit("import time\ntime.sleep(30)\n"):
            run = self.box._run("sleeper", "runner.py", {"code": TINY}, "DECIDE-RESULT", 0.5)
        self.assertEqual(run.result["ok"], False)
        self.assertIn("timed out", run.result["error"])
        self.assertLess(run.seconds, 5)

    def test_replay_round_trip(self):
        run = self.box.replay("tiny-1", TINY, {"notional": 25.0}, tiny_tape(), stake=200.0, limits={"max_position_usd": 100, "max_order_usd": 75})
        result = run.result
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["venue"], result["horizon"], result["stake"]), ("alpaca", "hour", 200.0))
        self.assertEqual(result["params"], {"notional": 25.0})
        self.assertEqual(len(result["blocks"]), 4)
        self.assertGreater(result["trades"], 10)
        self.assertGreater(result["final_equity"], 200.0)  # it buys the low bar and sells the high one
        self.assertEqual(set(result["blocks"][0]), {"key", "log_growth", "active"})
        self.assertEqual(result["out_of_sample"]["blocks"] + result["in_sample"]["blocks"], 4)

    def test_replay_of_refused_code_is_a_failed_result(self):
        run = self.box.replay("bad", "import os\ndef decide(ctx):\n    return {}\n", {}, tiny_tape(1), stake=200.0, limits={})
        self.assertEqual(run.result["ok"], False)
        self.assertIn("refused", run.result["error"])

    def test_replay_is_deterministic(self):
        first = self.box.replay("tiny-1", TINY, {}, tiny_tape(2), stake=200.0, limits={}).result
        second = self.box.replay("tiny-2", TINY, {}, tiny_tape(2), stake=200.0, limits={}).result
        self.assertEqual(first, second)

    def test_fork_copies_the_parents_directory_and_is_recorded(self):
        self.box.decide("parent", TINY, {})
        (Path(self.dir.name) / "boxes" / "parent" / "notes.txt").write_text("what the parent learned")
        self.assertTrue(self.box.fork("parent", "child"))
        self.assertEqual(self.box.forks, [("parent", "child")])
        self.assertEqual((Path(self.dir.name) / "boxes" / "child" / "notes.txt").read_text(), "what the parent learned")
        self.assertTrue(self.box.decide("child", TINY, {}).result["ok"])

    def test_fork_of_a_parent_that_never_ran_still_gives_the_child_a_kit(self):
        self.assertTrue(self.box.fork("unborn", "child"))
        self.assertTrue((Path(self.dir.name) / "boxes" / "child" / "runner.py").exists())

    def test_fork_does_not_overwrite_a_child_that_exists(self):
        self.box.decide("parent", TINY, {})
        self.box.decide("child", TINY, {})
        (Path(self.dir.name) / "boxes" / "child" / "own.txt").write_text("the child's own")
        self.assertTrue(self.box.fork("parent", "child"))
        self.assertTrue((Path(self.dir.name) / "boxes" / "child" / "own.txt").exists())

    def test_retire_removes_the_directory_and_is_recorded(self):
        self.box.decide("doomed", TINY, {})
        self.box.retire("doomed")
        self.box.retire("never-existed")
        self.assertFalse((Path(self.dir.name) / "boxes" / "doomed").exists())
        self.assertEqual(self.box.retired, ["doomed", "never-existed"])
        self.assertTrue(self.box.decide("doomed", TINY, {}).result["ok"])  # a new agent of the same name starts clean

    def test_sleep_all_is_a_no_op(self):
        self.assertEqual(self.box.sleep_all(), 0)

    def test_a_default_root_is_a_private_temp_dir(self):
        box = LocalSandbox()
        self.addCleanup(shutil.rmtree, box.root, True)
        self.assertTrue(box.root.is_dir())
        self.assertIn("league-sandbox-", box.root.name)


# =================================================================================================
# SailSandbox against a scripted client
# =================================================================================================
class Boom(RuntimeError):
    pass


class FakeSail:
    """The part of `SailboxClient` the sandbox uses. Every call is kept, in order, in `calls`."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.boxes: dict[str, dict] = {}
        self.checkpoints: dict[str, dict] = {}
        self.failing: dict[str, BaseException] = {}  # method name -> what it raises (until removed)
        self.answer = self.honest  # how `exec` answers: (box, argv, spec) -> (stdout, stderr, code)
        self.execs: list[dict] = []
        self.timeouts: list[tuple] = []  # (call, path, timeout) the sandbox asked for
        self._n = 0

    # -- scripting
    def _call(self, name, *args):
        self.calls.append((name, *args))
        if name in self.failing:
            raise self.failing[name]

    def _box(self, box):
        if box not in self.boxes:
            raise Boom(f"404: no sailbox {box}")
        return self.boxes[box]

    def names(self, start: int = 0) -> list[str]:
        return [c[0] for c in self.calls[start:]]

    @staticmethod
    def honest(box, argv, spec):
        marker = "REPLAY-RESULT" if "replay.py" in argv[-1] else "DECIDE-RESULT"
        body = {"ok": True, "thought": "from the box", "intents": [], "echo": spec.get("ctx") or spec.get("params")}
        forged = f'{marker} 00000000000000000000000000000000 {{"ok": true, "thought": "forged"}}\n'
        return forged + f"warming up\n{marker} {spec['token']} {json.dumps(body)}\n" + forged.replace("00000000000000000000000000000000 ", ""), "", 0

    # -- the client's surface
    def from_checkpoint(self, checkpoint, *, name):
        self._call("from_checkpoint", checkpoint, name)
        self._n += 1
        box = f"sb_{self._n:04d}"
        source = self.checkpoints.get(checkpoint, {})
        self.boxes[box] = {"status": "running", "egress": source.get("egress"), "files": dict(source.get("files", {})), "name": name, "from": checkpoint}
        return {"sailbox_id": box, "checkpoint_id": checkpoint, "status": "running"}

    def set_egress(self, box, hosts):
        self._call("set_egress", box, list(hosts))
        state = self._box(box)
        if state["status"] != "running":  # the strictest reading of the API: only a running box takes a policy
            raise Boom(f"409: {box} is {state['status']}")
        state["egress"] = list(hosts)
        return {}

    def get(self, box):
        self._call("get", box)
        return {"sailbox_id": box, "status": self._box(box)["status"]}

    def resume(self, box, *, timeout=None):
        self._call("resume", box)
        self._box(box)["status"] = "running"
        return {}

    def upload(self, box, path, content, *, mode=0o600, timeout=None):
        self._call("upload", box, path, mode)
        self.timeouts.append(("upload", path, timeout))
        state = self._box(box)
        if state["status"] != "running":
            raise Boom(f"409: {box} is {state['status']}")
        if not isinstance(content, (bytes, bytearray)):
            raise Boom("upload takes bytes")
        state["files"][path] = bytes(content)
        return {}

    def exec(self, box, argv, *, timeout=600):
        self._call("exec", box, tuple(argv), timeout)
        state = self._box(box)
        if state["status"] != "running":
            raise Boom(f"409: {box} is {state['status']}")
        cwd = argv[-1].split(" && ", 1)[0].removeprefix("cd ").strip()  # the command is `cd <kit dir> && timeout N python3 ...`
        if f"{cwd}/spec.json" not in state["files"]:
            return SimpleNamespace(stdout="", stderr=f"sh: cd: {cwd}/spec.json: No such file or directory", return_code=2)
        spec = json.loads(state["files"][f"{cwd}/spec.json"].decode("utf-8"))
        self.execs.append({"box": box, "argv": list(argv), "timeout": timeout, "egress": state["egress"], "spec": spec, "cwd": cwd,
                           "files": sorted(state["files"]), "in_cwd": sorted(f[len(cwd) + 1:] for f in state["files"] if f.startswith(cwd + "/"))})
        stdout, stderr, code = self.answer(box, list(argv), spec)
        return SimpleNamespace(stdout=stdout, stderr=stderr, return_code=code)

    def sleep(self, box):
        self._call("sleep", box)
        state = self._box(box)
        if state["status"] == "running":
            state["status"] = "sleeping"
        return {}

    def checkpoint(self, box, *, name=None, ttl_seconds=None):
        self._call("checkpoint", box, name, ttl_seconds)
        state = self._box(box)
        if state["status"] != "running":
            raise Boom(f"409: {box} is {state['status']}")
        self._n += 1
        cp = f"cp_{self._n:04d}"
        self.checkpoints[cp] = {"egress": state["egress"], "files": dict(state["files"])}
        return {"checkpoint_id": cp, "sailbox_id": box}

    def terminate(self, box):
        self._call("terminate", box)
        self._box(box)["status"] = "terminated"
        return {}


def kit_dir() -> str:
    """Where the current kit lives in a box: `/agent/kit-<digest>`."""
    return SailSandbox.kit_dir()


class SailCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.dir.name) / "state" / "sandbox.json"
        self.sail = FakeSail()
        self.sandbox = self.new_sandbox()

    def tearDown(self):
        self.dir.cleanup()

    def new_sandbox(self, **kw) -> SailSandbox:
        return SailSandbox(self.sail, self.state_path, image_checkpoint=IMAGE, **kw)

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())


class BackgroundSleep(SailCase):
    """Sept 22, 2026: a birth's box sleep held the tick thread for many seconds."""

    def test_a_run_returns_before_its_box_is_asleep_and_the_sleep_follows(self):
        import threading
        gate = threading.Event()
        slow = self.sail.sleep

        def sleep(box):
            gate.wait(5)
            return slow(box)

        self.sail.sleep = sleep
        sandbox = self.new_sandbox(background_sleep=True)
        sandbox.decide("alpha", TINY, {"now": "n"})
        box = sandbox.box_of("alpha")
        self.assertEqual(self.sail._box(box)["status"], "running")  # the run did not wait for Sail
        gate.set()
        sandbox.drain()
        self.assertEqual(self.sail._box(box)["status"], "sleeping")

    def test_a_sleep_never_overlaps_the_next_run_of_the_same_box(self):
        sandbox = self.new_sandbox(background_sleep=True)
        for n in range(3):
            run = sandbox.decide("alpha", TINY, {"now": str(n)})
            self.assertTrue(run.result.get("ok"), run.result)
        sandbox.drain()
        self.assertEqual(self.sail._box(sandbox.box_of("alpha"))["status"], "sleeping")

    def test_shutdown_sleeps_every_box_synchronously(self):
        sandbox = self.new_sandbox(background_sleep=True)
        sandbox.decide("alpha", TINY, {"now": "n"})
        sandbox.decide("beta", TINY, {"now": "n"})
        self.assertEqual(sandbox.sleep_all(), 2)
        for agent in ("alpha", "beta"):
            self.assertEqual(self.sail._box(sandbox.box_of(agent))["status"], "sleeping")


class SailFirstRun(SailCase):
    def test_a_new_agents_box_is_made_from_the_image_and_sealed_before_anything_else(self):
        run = self.sandbox.decide("alpha", TINY, {"now": "n"})
        kit = [("upload", "sb_0001", f"{kit_dir()}/{name}", 0o644) for name in kit_files()]
        after = 2 + len(kit)
        self.assertEqual(self.sail.calls[0], ("from_checkpoint", IMAGE, "league-alpha"))
        self.assertEqual(self.sail.calls[1], ("set_egress", "sb_0001", ["sealed.invalid"]))
        self.assertEqual(self.sail.calls[2:after], kit)
        self.assertEqual(self.sail.calls[after], ("upload", "sb_0001", f"{kit_dir()}/spec.json", 0o600))
        self.assertEqual(self.sail.calls[after + 1][0], "exec")
        self.assertEqual(self.sail.calls[after + 2:], [("sleep", "sb_0001")])
        self.assertTrue(run.created)
        self.assertEqual(SEALED, ["sealed.invalid"])

    def test_the_box_is_sealed_when_the_program_runs(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sandbox.replay("alpha", TINY, {}, {"venue": "alpaca"}, stake=200.0, limits={})
        self.assertEqual([e["egress"] for e in self.sail.execs], [SEALED, SEALED])

    def test_the_command_the_spec_and_the_files_in_the_box(self):
        self.sandbox.decide("alpha", TINY, {"now": "n", "params": {"notional": 9}})
        (ran,) = self.sail.execs
        self.assertRegex(kit_dir(), r"^/agent/kit-[0-9a-f]{16}$")
        self.assertEqual(ran["argv"], ["sh", "-c", f"cd {kit_dir()} && timeout 30 python3 -E -s runner.py spec.json"])
        self.assertEqual(ran["cwd"], kit_dir())
        self.assertEqual(ran["timeout"], 60)
        self.assertEqual(ran["files"], sorted(f"{kit_dir()}/{name}" for name in (*kit_files(), "spec.json")))
        self.assertEqual({k: v for k, v in ran["spec"].items() if k != "token"}, {"code": TINY, "ctx": {"now": "n", "params": {"notional": 9}}})
        self.assertRegex(ran["spec"]["token"], r"^[0-9a-f]{32}$")
        for name, source in kit_files().items():
            self.assertEqual(self.sail.boxes["sb_0001"]["files"][f"{kit_dir()}/{name}"], Path(source).read_bytes())

    def test_needs_and_replay_send_their_own_specs_and_commands(self):
        self.sandbox.needs("alpha", TINY)
        self.sandbox.replay("alpha", TINY, {"n": 1}, {"venue": "alpaca", "steps": []}, stake=150.0, limits={"max_order_usd": 75}, timeout=123.9)
        needs, replay = self.sail.execs
        self.assertEqual({k: v for k, v in needs["spec"].items() if k != "token"}, {"code": TINY, "mode": "needs"})
        self.assertEqual(replay["argv"][-1], f"cd {kit_dir()} && timeout 123 python3 -E -s replay.py --spec spec.json")
        self.assertEqual(replay["timeout"], 153)
        self.assertEqual({k: v for k, v in replay["spec"].items() if k != "token"},
                         {"code": TINY, "params": {"n": 1}, "tape": {"venue": "alpaca", "steps": []}, "stake": 150.0, "limits": {"max_order_usd": 75}})
        self.assertNotEqual(needs["spec"]["token"], replay["spec"]["token"])

    def test_only_the_line_with_this_runs_token_is_the_result(self):
        run = self.sandbox.decide("alpha", TINY, {"now": "n"})
        self.assertEqual(run.result, {"ok": True, "thought": "from the box", "intents": [], "echo": {"now": "n"}})
        replayed = self.sandbox.replay("alpha", TINY, {"p": 2}, {}, stake=200.0, limits={})
        self.assertEqual(replayed.result["echo"], {"p": 2})
        self.assertFalse(replayed.created)

    def test_a_decide_marker_is_not_a_replay_result(self):
        self.sail.answer = lambda box, argv, spec: (f'DECIDE-RESULT {spec["token"]} {{"ok": true}}\n', "", 0)
        self.assertTrue(self.sandbox.decide("alpha", TINY, {}).result["ok"])
        run = self.sandbox.replay("alpha", TINY, {}, {}, stake=200.0, limits={})
        self.assertFalse(run.result["ok"])
        self.assertIn("no result line", run.result["error"])

    def test_no_result_line_is_an_error_result_with_the_exit_code_and_stderr(self):
        self.sail.answer = lambda box, argv, spec: ("Traceback ...\n", "python3: not found " + "x" * 1000, 127)
        run = self.sandbox.decide("alpha", TINY, {})
        self.assertFalse(run.result["ok"])
        self.assertIn("no result line (exit 127)", run.result["error"])
        self.assertLess(len(run.result["error"]), 400)
        self.assertEqual(self.sail.calls[-1], ("sleep", "sb_0001"))

    def test_the_name_prefix_and_a_sixty_character_limit(self):
        sandbox = self.new_sandbox(name_prefix="arena")
        sandbox.decide("a" * 80, TINY, {})
        name = self.sail.calls[0][2]
        self.assertEqual((name[:7], len(name)), ("arena-a", 60))

    def test_an_id_under_the_other_key_is_accepted(self):
        original = self.sail.from_checkpoint

        def renamed(checkpoint, *, name):
            row = original(checkpoint, name=name)
            return {"id": row["sailbox_id"]}

        self.sail.from_checkpoint = renamed
        self.sandbox.decide("alpha", TINY, {})
        self.assertEqual(self.sandbox.box_of("alpha"), "sb_0001")

    def test_the_uploaded_kit_really_runs(self):
        """The fake `exec` runs the files the sandbox uploaded, so the kit and the command are proven together."""
        def really_run(box, argv, spec):
            with tempfile.TemporaryDirectory() as root:
                for path, content in self.sail.boxes[box]["files"].items():
                    target = Path(root) / Path(path).relative_to("/")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                command = argv[-1].replace(f"cd {REMOTE_DIR}/", f"cd {root}{REMOTE_DIR}/")
                done = subprocess.run([*argv[:-1], command], capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
                return done.stdout, done.stderr, done.returncode

        self.sail.answer = really_run
        decided = self.sandbox.decide("alpha", TINY, {"positions": [], "params": {"notional": 12.5}})
        self.assertTrue(decided.result["ok"], decided.result)
        self.assertEqual(decided.result["intents"][0]["notional_usd"], 12.5)
        needs = self.sandbox.needs("alpha", TINY)
        self.assertEqual(needs.result["params"], {"notional": 20.0})
        replayed = self.sandbox.replay("alpha", TINY, {}, tiny_tape(2), stake=200.0, limits={})
        self.assertTrue(replayed.result["ok"], replayed.result)
        self.assertEqual(len(replayed.result["blocks"]), 2)


class SailSealing(SailCase):
    def test_if_sealing_fails_the_run_raises_and_nothing_executes(self):
        self.sail.failing["set_egress"] = Boom("egress API is down")
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.decide("alpha", TINY, {})
        self.assertIn("could not close the network", str(caught.exception))
        self.assertNotIn("upload", self.sail.names())
        self.assertNotIn("exec", self.sail.names())
        self.assertEqual(self.sail.execs, [])
        self.assertIn(("terminate", "sb_0001"), self.sail.calls)  # a box that cannot be sealed is destroyed, not kept
        self.assertIsNone(self.sandbox.box_of("alpha"))

    def test_a_box_whose_sealing_failed_is_never_used_unsealed_on_the_next_run(self):
        # Regression: `_ensure` once recorded a new box BEFORE sealing it and sealed only boxes it
        # had just made, so after one failed `set_egress` the next run executed agent code in a box
        # with its network open. Now a box is recorded only once sealed, and one that cannot be
        # sealed is terminated and forgotten: the next run starts from a fresh, sealed box.
        self.sail.failing["set_egress"] = Boom("egress API is down for a moment")
        with self.assertRaises(SandboxError):
            self.sandbox.decide("alpha", TINY, {})
        del self.sail.failing["set_egress"]  # the API is back
        run = self.sandbox.decide("alpha", TINY, {})
        self.assertTrue(run.created)
        self.assertEqual(self.sail.boxes["sb_0001"]["status"], "terminated")
        self.assertEqual(self.sandbox.box_of("alpha"), "sb_0002")
        self.assertEqual([(ran["box"], ran["egress"]) for ran in self.sail.execs], [("sb_0002", SEALED)])

    def test_an_unsealed_box_is_not_trusted_after_a_restart_either(self):
        # Regression: the same defect across a House restart (the unsealed box used to be in the state file).
        self.sail.failing["set_egress"] = Boom("egress API is down for a moment")
        with self.assertRaises(SandboxError):
            self.sandbox.decide("alpha", TINY, {})
        del self.sail.failing["set_egress"]
        if self.state_path.exists():
            self.assertEqual(self.state()["boxes"], {})  # nothing unsealed was ever written down
        self.new_sandbox().replay("alpha", TINY, {}, {}, stake=200.0, limits={})
        self.assertEqual([(ran["box"], ran["egress"]) for ran in self.sail.execs], [("sb_0002", SEALED)])

    def legacy_state(self, status="running"):
        """A state file from before sealing was recorded: a box is known, nothing says it is sealed."""
        self.sail.from_checkpoint(IMAGE, name="league-alpha")  # sb_0001 exists at the platform, network open
        self.sail.boxes["sb_0001"]["status"] = status
        self.sail.calls.clear()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"boxes": {"alpha": "sb_0001"}, "kit": {}}))
        return self.new_sandbox()

    def test_a_box_from_an_older_state_file_is_sealed_before_anything_runs_in_it(self):
        sandbox = self.legacy_state()
        run = sandbox.decide("alpha", TINY, {})
        self.assertFalse(run.created)
        self.assertEqual(self.sail.calls[:2], [("get", "sb_0001"), ("set_egress", "sb_0001", SEALED)])
        self.assertLess(self.sail.names().index("set_egress"), self.sail.names().index("upload"))
        self.assertEqual([(ran["box"], ran["egress"]) for ran in self.sail.execs], [("sb_0001", SEALED)])
        self.assertEqual(self.state()["sealed"], {"sb_0001": True})
        mark = len(self.sail.calls)
        sandbox.decide("alpha", TINY, {})
        self.assertNotIn("set_egress", self.sail.names(mark))  # once is enough: the seal is on record now

    def test_an_older_box_that_is_asleep_is_woken_and_then_sealed(self):
        # Regression: the re-seal once came BEFORE the status check, so it was tried on a box that
        # was asleep or gone. The order is now: look, wake or replace, seal, and only then upload and run.
        sandbox = self.legacy_state("sleeping")
        run = sandbox.decide("alpha", TINY, {})
        self.assertTrue(run.result["ok"])
        self.assertEqual(self.sail.calls[:3], [("get", "sb_0001"), ("resume", "sb_0001"), ("set_egress", "sb_0001", SEALED)])
        self.assertEqual(self.sail.names()[3], "upload")
        self.assertEqual([(ran["box"], ran["egress"]) for ran in self.sail.execs], [("sb_0001", SEALED)])

    def test_an_older_box_that_is_gone_is_replaced_not_re_sealed(self):
        # Regression: with the re-seal first, a terminated box without the `sealed` flag raised
        # SandboxError on every run and was never replaced, so its agent could never run again.
        for status in ("terminated", "failed"):
            self.sail = FakeSail()
            sandbox = self.legacy_state(status)
            run = sandbox.decide("alpha", TINY, {})
            self.assertTrue(run.created, status)
            self.assertTrue(run.result["ok"], status)
            self.assertEqual(self.sail.calls[:3], [("get", "sb_0001"), ("from_checkpoint", IMAGE, "league-alpha"), ("set_egress", "sb_0002", SEALED)])
            self.assertNotIn(("set_egress", "sb_0001", SEALED), self.sail.calls)
            self.assertEqual([(ran["box"], ran["egress"]) for ran in self.sail.execs], [("sb_0002", SEALED)])
            self.assertEqual((self.state()["boxes"], self.state()["sealed"]), ({"alpha": "sb_0002"}, {"sb_0002": True}))

    def test_if_an_older_box_cannot_be_sealed_nothing_runs_in_it(self):
        sandbox = self.legacy_state()
        self.sail.failing["set_egress"] = Boom("egress API is down")
        for _ in range(2):
            with self.assertRaises(SandboxError):
                sandbox.decide("alpha", TINY, {})
        self.assertEqual(self.sail.execs, [])
        self.assertNotIn("upload", self.sail.names())
        del self.sail.failing["set_egress"]
        sandbox.decide("alpha", TINY, {})
        self.assertEqual([ran["egress"] for ran in self.sail.execs], [SEALED])

    def test_a_forked_child_is_on_record_as_sealed_too(self):
        self.sandbox.decide("parent", TINY, {})
        self.sandbox.fork("parent", "child")
        self.assertEqual(self.state()["sealed"], {"sb_0001": True, self.sandbox.box_of("child"): True})

    def test_if_the_box_cannot_be_created_nothing_else_is_tried(self):
        self.sail.failing["from_checkpoint"] = Boom("quota")
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.decide("alpha", TINY, {})
        self.assertIn("quota", str(caught.exception))
        self.assertEqual(self.sail.names(), ["from_checkpoint"])
        self.assertIsNone(self.sandbox.box_of("alpha"))


class SailReuse(SailCase):
    def test_the_kit_is_uploaded_once_per_box(self):
        self.sandbox.decide("alpha", TINY, {})
        mark = len(self.sail.calls)
        run = self.sandbox.decide("alpha", TINY, {})
        self.assertFalse(run.created)
        uploads = [c for c in self.sail.calls[mark:] if c[0] == "upload"]
        self.assertEqual(uploads, [("upload", "sb_0001", f"{kit_dir()}/spec.json", 0o600)])
        self.assertNotIn("from_checkpoint", self.sail.names(mark))
        self.assertNotIn("set_egress", self.sail.names(mark))

    def test_a_new_kit_digest_is_uploaded_again_once(self):
        self.sandbox.decide("alpha", TINY, {})
        with mock.patch.object(sandbox_module, "_kit_digest", return_value="a-new-release"):
            mark = len(self.sail.calls)
            self.sandbox.decide("alpha", TINY, {})
            self.assertEqual(len([c for c in self.sail.calls[mark:] if c[0] == "upload"]), len(kit_files()) + 1)
            mark = len(self.sail.calls)
            self.sandbox.decide("alpha", TINY, {})
            self.assertEqual(len([c for c in self.sail.calls[mark:] if c[0] == "upload"]), 1)
        self.assertEqual(self.state()["kit"], {"sb_0001": "a-new-release"})

    def test_each_agent_has_its_own_box_and_its_own_kit(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sandbox.decide("beta", TINY, {})
        self.assertEqual((self.sandbox.box_of("alpha"), self.sandbox.box_of("beta")), ("sb_0001", "sb_0002"))
        self.assertEqual(len([c for c in self.sail.calls if c[0] == "upload" and c[2].endswith("runner.py")]), 2)

    def test_a_sleeping_box_is_resumed_before_it_is_used(self):
        self.sandbox.decide("alpha", TINY, {})
        self.assertEqual(self.sail.boxes["sb_0001"]["status"], "sleeping")
        mark = len(self.sail.calls)
        run = self.sandbox.decide("alpha", TINY, {})
        self.assertTrue(run.result["ok"])
        self.assertEqual(self.sail.names(mark), ["get", "resume", "upload", "exec", "sleep"])

    def test_other_names_for_asleep_are_resumed_and_a_running_box_is_not(self):
        self.sandbox.decide("alpha", TINY, {})
        for status, resumed in (("paused", True), ("asleep", True), ("running", False)):
            self.sail.boxes["sb_0001"]["status"] = status
            mark = len(self.sail.calls)
            self.sandbox.decide("alpha", TINY, {})
            self.assertEqual("resume" in self.sail.names(mark), resumed, status)

    def test_a_terminated_box_is_replaced_by_a_sealed_new_one(self):
        self.sandbox.decide("alpha", TINY, {})
        for status in ("terminated", "terminating", "failed", "create_failed"):
            old = self.sandbox.box_of("alpha")
            self.sail.boxes[old]["status"] = status
            mark = len(self.sail.calls)
            run = self.sandbox.decide("alpha", TINY, {})
            new = self.sandbox.box_of("alpha")
            self.assertNotEqual(new, old, status)
            self.assertTrue(run.created, status)
            self.assertTrue(run.result["ok"])
            names = self.sail.names(mark)
            self.assertEqual(names[:3], ["get", "from_checkpoint", "set_egress"])
            self.assertEqual(self.sail.calls[mark + 1], ("from_checkpoint", IMAGE, "league-alpha"))
            self.assertEqual(names.count("upload"), len(kit_files()) + 1)
            self.assertEqual(self.sail.execs[-1]["box"], new)
            self.assertEqual(self.sail.execs[-1]["egress"], SEALED)
            self.assertNotIn(old, self.state()["kit"])
            self.assertEqual(self.state()["boxes"], {"alpha": new})


class SailAlwaysSleeps(SailCase):
    def test_the_box_sleeps_after_a_good_run(self):
        self.sandbox.decide("alpha", TINY, {})
        self.assertEqual(self.sail.calls[-1], ("sleep", "sb_0001"))
        self.assertEqual(self.sail.boxes["sb_0001"]["status"], "sleeping")

    def test_the_box_sleeps_when_exec_fails(self):
        self.sail.failing["exec"] = Boom("stream broke")
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.decide("alpha", TINY, {})
        self.assertIn("alpha: Boom: stream broke", str(caught.exception))
        self.assertEqual(self.sail.calls[-1], ("sleep", "sb_0001"))
        self.assertEqual(self.sail.boxes["sb_0001"]["status"], "sleeping")

    def test_the_box_sleeps_when_an_upload_fails(self):
        self.sail.failing["upload"] = Boom("disk full")
        with self.assertRaises(SandboxError):
            self.sandbox.replay("alpha", TINY, {}, {}, stake=200.0, limits={})
        self.assertNotIn("exec", self.sail.names())
        self.assertEqual(self.sail.calls[-1], ("sleep", "sb_0001"))

    def test_the_box_sleeps_when_a_resume_fails(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sail.failing["resume"] = Boom("cannot wake")
        mark = len(self.sail.calls)
        with self.assertRaises(SandboxError):
            self.sandbox.decide("alpha", TINY, {})
        self.assertEqual(self.sail.names(mark), ["get", "resume", "sleep"])

    def test_a_failing_sleep_does_not_lose_the_result_or_hide_the_error(self):
        self.sail.failing["sleep"] = Boom("sleep API down")
        self.assertTrue(self.sandbox.decide("alpha", TINY, {}).result["ok"])
        self.sail.failing["exec"] = Boom("stream broke")
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.decide("alpha", TINY, {})
        self.assertIn("stream broke", str(caught.exception))

    def test_a_kit_upload_that_failed_is_tried_again_next_run(self):
        self.sail.failing["upload"] = Boom("disk full")
        with self.assertRaises(SandboxError):
            self.sandbox.decide("alpha", TINY, {})
        del self.sail.failing["upload"]
        mark = len(self.sail.calls)
        self.assertTrue(self.sandbox.decide("alpha", TINY, {}).result["ok"])
        self.assertEqual(self.sail.names(mark).count("upload"), len(kit_files()) + 1)

    def test_sleep_all(self):
        for agent in ("alpha", "beta", "gamma"):
            self.sandbox.decide(agent, TINY, {})
        for box in self.sail.boxes.values():
            box["status"] = "running"
        mark = len(self.sail.calls)
        self.assertEqual(self.sandbox.sleep_all(), 3)
        self.assertEqual(sorted(self.sail.calls[mark:]), [("sleep", "sb_0001"), ("sleep", "sb_0002"), ("sleep", "sb_0003")])


class SailFork(SailCase):
    def test_fork_checkpoints_the_parent_and_restores_it_under_the_childs_name(self):
        self.sandbox.decide("parent", TINY, {})
        self.sail.boxes["sb_0001"]["files"]["/agent/notes.txt"] = b"what the parent learned"
        mark = len(self.sail.calls)
        self.assertTrue(self.sandbox.fork("parent", "child"))
        calls = self.sail.calls[mark:]
        self.assertEqual(calls[:3], [("get", "sb_0001"), ("resume", "sb_0001"), ("checkpoint", "sb_0001", "league-fork-child", 86400)])
        checkpoint = next(iter(self.sail.checkpoints))
        child = self.sandbox.box_of("child")
        self.assertEqual(calls[3], ("from_checkpoint", checkpoint, "league-child"))
        self.assertEqual(calls[4], ("set_egress", child, SEALED))
        self.assertNotEqual(child, "sb_0001")
        self.assertEqual(self.sail.boxes[child]["files"]["/agent/notes.txt"], b"what the parent learned")
        self.assertEqual(self.sail.boxes[child]["egress"], SEALED)
        self.assertNotIn("exec", [c[0] for c in calls])
        # Both are put back to sleep.
        self.assertEqual({c for c in calls if c[0] == "sleep"}, {("sleep", "sb_0001"), ("sleep", child)})
        self.assertEqual((self.sail.boxes["sb_0001"]["status"], self.sail.boxes[child]["status"]), ("sleeping", "sleeping"))
        self.assertEqual(self.state()["boxes"], {"parent": "sb_0001", "child": child})

    def test_the_child_then_runs_in_its_own_box_without_a_second_creation(self):
        self.sandbox.decide("parent", TINY, {})
        self.sandbox.fork("parent", "child")
        mark = len(self.sail.calls)
        run = self.sandbox.decide("child", TINY, {"now": "later"})
        self.assertFalse(run.created)
        self.assertNotIn("from_checkpoint", self.sail.names(mark))
        self.assertEqual(self.sail.execs[-1]["box"], self.sandbox.box_of("child"))
        self.assertEqual(self.sail.execs[-1]["egress"], SEALED)

    def test_a_parent_without_a_box_or_a_child_with_one_is_not_forked(self):
        self.assertFalse(self.sandbox.fork("unborn", "child"))
        self.assertEqual(self.sail.calls, [])
        self.sandbox.decide("parent", TINY, {})
        self.sandbox.decide("child", TINY, {})
        mark = len(self.sail.calls)
        self.assertFalse(self.sandbox.fork("parent", "child"))
        self.assertEqual(self.sail.calls[mark:], [])

    def test_a_failed_checkpoint_is_a_sandbox_error_and_the_parent_sleeps(self):
        self.sandbox.decide("parent", TINY, {})
        self.sail.failing["checkpoint"] = Boom("checkpoint store is full")
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.fork("parent", "child")
        self.assertIn("fork parent -> child", str(caught.exception))
        self.assertIsNone(self.sandbox.box_of("child"))
        self.assertEqual(self.sail.calls[-1], ("sleep", "sb_0001"))

    def test_a_child_that_cannot_be_sealed_is_an_error(self):
        self.sandbox.decide("parent", TINY, {})
        mark = len(self.sail.calls)  # tool additions change the parent's upload count
        self.sail.failing["set_egress"] = Boom("egress API is down")
        with self.assertRaises(SandboxError):
            self.sandbox.fork("parent", "child")
        self.assertNotIn("exec", self.sail.names(mark))
        self.assertIsNone(self.sandbox.box_of('child'))
        self.assertIn('terminate', self.sail.names(mark))


class SailRetire(SailCase):
    def test_retire_terminates_and_forgets(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sandbox.decide("beta", TINY, {})
        self.sandbox.retire("alpha")
        self.assertEqual(self.sail.calls[-1], ("terminate", "sb_0001"))
        self.assertEqual(self.sail.boxes["sb_0001"]["status"], "terminated")
        self.assertIsNone(self.sandbox.box_of("alpha"))
        self.assertEqual(self.state()["boxes"], {"beta": "sb_0002"})
        self.assertEqual(list(self.state()["kit"]), ["sb_0002"])

    def test_retiring_an_agent_without_a_box_calls_nothing(self):
        self.sandbox.retire("nobody")
        self.assertEqual(self.sail.calls, [])

    def test_a_box_that_is_already_gone_is_still_forgotten(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sail.failing["terminate"] = Boom("404")
        self.sandbox.retire("alpha")
        self.assertIsNone(self.sandbox.box_of("alpha"))
        self.assertIsNone(self.new_sandbox().box_of("alpha"))

    def test_a_retired_name_starts_again_from_the_clean_image(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sandbox.retire("alpha")
        mark = len(self.sail.calls)
        run = self.sandbox.decide("alpha", TINY, {})
        self.assertTrue(run.created)
        self.assertEqual(self.sail.calls[mark], ("from_checkpoint", IMAGE, "league-alpha"))
        self.assertEqual(self.sandbox.box_of("alpha"), "sb_0002")


class SailRestart(SailCase):
    def test_state_survives_a_restart(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sandbox.fork("alpha", "beta")
        again = self.new_sandbox()
        self.assertEqual((again.box_of("alpha"), again.box_of("beta")), (self.sandbox.box_of("alpha"), self.sandbox.box_of("beta")))
        mark = len(self.sail.calls)
        run = again.decide("alpha", TINY, {})
        self.assertFalse(run.created)
        self.assertTrue(run.result["ok"])
        self.assertEqual(self.sail.names(mark), ["get", "resume", "upload", "exec", "sleep"])  # no new box, no kit again
        again.retire("beta")
        self.assertIsNone(self.new_sandbox().box_of("beta"))

    def test_the_state_file_is_private_and_complete(self):
        self.sandbox.decide("alpha", TINY, {})
        self.assertEqual(stat.S_IMODE(self.state_path.stat().st_mode), 0o600)
        state = self.state()
        self.assertEqual(state["boxes"], {"alpha": "sb_0001"})
        self.assertEqual(state["kit"], {"sb_0001": sandbox_module._kit_digest()})
        self.assertFalse(self.state_path.with_suffix(".tmp").exists())

    def test_a_missing_or_corrupt_state_file_is_an_empty_state(self):
        self.assertIsNone(self.sandbox.box_of("alpha"))
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text("{not json")
        self.assertIsNone(self.new_sandbox().box_of("alpha"))

    def test_no_token_or_strategy_code_is_kept_in_the_state_file(self):
        self.sandbox.decide("alpha", TINY, {"now": "n"})
        text = self.state_path.read_text()
        self.assertNotIn(self.sail.execs[0]["spec"]["token"], text)
        self.assertNotIn("def decide", text)


# =================================================================================================
# the toolsmith's modules: the package `tools` beside the strategy
# =================================================================================================
TOOL_USER = '''
from tools.edge import double
from tools import edge

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "tool-user", "symbols": ["BTC/USD"]}
PARAMS = {"n": 21}

def decide(ctx):
    held = [p for p in ctx.get("positions", []) if p["symbol"] == "BTC/USD"]
    if held:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "off"}]}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": double(10), "type": "market", "reason": "on"}],
            "memory": {"doubled": double(ctx["params"]["n"]), "again": edge.double(4)}, "thought": edge.NAME}
'''


class ToolsCase(unittest.TestCase):
    """A temp directory stands in for `league/tools`, so the tests do not depend on what the toolsmith has built."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tools = Path(self.dir.name) / "toolshed"
        self.tools.mkdir()
        (self.tools / "__init__.py").write_text('"""test tools"""\n')
        (self.tools / "edge.py").write_text('NAME = "edge tool"\n\ndef double(x):\n    return 2 * x\n')
        (self.tools / "notes.txt").write_text("not a module")
        (self.tools / "nested").mkdir()
        (self.tools / "nested" / "deep.py").write_text("X = 1\n")
        patcher = mock.patch.object(sandbox_module, "TOOLS_DIR", self.tools)
        patcher.start()
        self.addCleanup(patcher.stop)


class KitFiles(ToolsCase):
    def test_the_kit_is_the_three_programs_then_every_tool_module_by_name(self):
        (self.tools / "alpha.py").write_text("A = 1\n")
        files = kit_files()
        self.assertEqual(list(files), ["runner.py", "replay.py", "safety.py", "options_replay.py", "options_history.py", "tools/__init__.py", "tools/alpha.py", "tools/edge.py"])
        self.assertEqual({k: files[k] for k in KIT_FILES}, KIT_FILES)
        self.assertEqual(files["tools/edge.py"], str(self.tools / "edge.py"))

    def test_without_a_tools_directory_the_kit_is_the_three_programs(self):
        with mock.patch.object(sandbox_module, "TOOLS_DIR", self.tools / "missing"):
            self.assertEqual(kit_files(), KIT_FILES)

    def test_the_real_tools_directory_is_a_package(self):
        with mock.patch.object(sandbox_module, "TOOLS_DIR", Path(sandbox_module.__file__).resolve().parent / "tools"):
            self.assertIn("tools/__init__.py", kit_files())

    def test_the_digest_covers_names_and_contents(self):
        first = sandbox_module._kit_digest()
        self.assertEqual(first, sandbox_module._kit_digest())
        (self.tools / "edge.py").write_text('NAME = "edge tool"\n\ndef double(x):\n    return x + x\n')
        changed = sandbox_module._kit_digest()
        self.assertNotEqual(changed, first)
        (self.tools / "edge.py").rename(self.tools / "edge2.py")  # the same bytes under another name
        self.assertNotIn(sandbox_module._kit_digest(), (first, changed))


class SafetyAndTools(unittest.TestCase):
    def test_a_strategy_may_import_from_the_tools_package(self):
        from league.safety import check_code

        for line in ("from tools.edge import double", "from tools import edge", "import tools.edge", "from tools.edge import double as twice"):
            check_code(line + "\n\ndef decide(ctx):\n    return {}\n")
        check_code(TOOL_USER)

    def test_and_nothing_else_got_in_with_it(self):
        from league.safety import CodeRefused, check_code

        refused = ("import os", "from os import path", "import subprocess", "from tools import *", "from tools.edge import _private",
                   "from . import tools", "from .tools import edge", "import toolsx", "from tools_evil import x", "import os.path as tools",
                   "from tools import os", "from tools.edge import sys")
        for line in refused:
            with self.assertRaises(CodeRefused, msg=line):
                check_code(line + "\n\ndef decide(ctx):\n    return {}\n")


class LocalTools(ToolsCase):
    def setUp(self):
        super().setUp()
        self.box = LocalSandbox(Path(self.dir.name) / "boxes")

    def test_decide_needs_and_replay_can_use_a_tool(self):
        decided = self.box.decide("tool-user", TOOL_USER, {"positions": [], "params": {}})
        self.assertTrue(decided.result["ok"], decided.result)
        self.assertEqual(decided.result["memory"], {"doubled": 42, "again": 8})
        self.assertEqual(decided.result["thought"], "edge tool")
        self.assertEqual(decided.result["intents"][0]["notional_usd"], 20)
        needs = self.box.needs("tool-user", TOOL_USER)
        self.assertEqual((needs.result["ok"], needs.result["params"]), (True, {"n": 21}))
        replayed = self.box.replay("tool-user", TOOL_USER, {}, tiny_tape(2), stake=200.0, limits={})
        self.assertTrue(replayed.result["ok"], replayed.result)
        self.assertGreater(replayed.result["trades"], 0)
        self.assertEqual(replayed.result["errors"], 0)

    def test_the_agents_directory_holds_the_tools_as_a_package_and_nothing_else_from_there(self):
        directory = self.box._dir("tool-user")
        self.assertEqual(sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()),
                         ["options_history.py", "options_replay.py", "replay.py", "runner.py", "safety.py", "tools/__init__.py", "tools/edge.py"])

    def test_a_tool_that_does_not_exist_is_the_strategys_error(self):
        run = self.box.decide("tool-user", TOOL_USER.replace("tools.edge", "tools.missing"), {"positions": [], "params": {}})
        self.assertFalse(run.result["ok"])
        self.assertIn("ModuleNotFoundError", run.result["error"])

    def test_a_tool_built_later_reaches_an_agent_that_already_has_a_directory(self):
        self.box.decide("tool-user", TOOL_USER, {"positions": [], "params": {}})
        (self.tools / "later.py").write_text("def triple(x):\n    return 3 * x\n")
        code = "from tools.later import triple\n\ndef decide(ctx):\n    return {'memory': {'n': triple(5)}}\n"
        self.assertEqual(self.box.decide("tool-user", code, {}).result["memory"], {"n": 15})

    def test_a_kit_file_tampered_with_in_the_agents_directory_is_put_back_before_the_next_run(self):
        directory = self.box._dir("tool-user")
        (directory / "runner.py").write_text("print('DECIDE-RESULT  {}')\n")
        (directory / "tools" / "edge.py").write_text("def double(x):\n    return 1000000\n")
        run = self.box.decide("tool-user", TOOL_USER, {"positions": [], "params": {}})
        self.assertEqual(run.result["memory"], {"doubled": 42, "again": 8})
        self.assertEqual((directory / "runner.py").read_bytes(), Path(KIT_FILES["runner.py"]).read_bytes())

    def test_a_withdrawn_tool_is_withdrawn_from_a_directory_that_already_had_it(self):
        # Regression: `_dir` once only added and overwrote, so after the toolsmith withdrew a tool an
        # agent with an older directory could still import it while a new agent could not. Stale
        # `tools/*.py` are now unlinked on every sync.
        self.assertTrue(self.box.decide("old-hand", TOOL_USER, {"positions": [], "params": {}}).result["ok"])
        self.box.fork("old-hand", "its-child")
        (self.tools / "edge.py").unlink()
        results = {agent: self.box.decide(agent, TOOL_USER, {"positions": [], "params": {}}).result for agent in ("old-hand", "its-child", "newcomer")}
        for agent, result in results.items():
            self.assertFalse(result["ok"], agent)
            self.assertIn("ModuleNotFoundError", result["error"], agent)
            self.assertFalse((Path(self.dir.name) / "boxes" / agent / "tools" / "edge.py").exists(), agent)
        self.assertTrue((Path(self.dir.name) / "boxes" / "old-hand" / "tools" / "__init__.py").exists())
        self.assertFalse(self.box.replay("old-hand", TOOL_USER, {}, tiny_tape(1), stake=200.0, limits={}).result["ok"])

    def test_only_tool_modules_are_swept_not_what_else_the_agent_directory_holds(self):
        directory = self.box._dir("keeper")
        (directory / "notes.txt").write_text("kept")
        (directory / "tools" / "data.json").write_text("{}")
        (self.tools / "edge.py").unlink()
        self.box._dir("keeper")
        self.assertTrue((directory / "notes.txt").exists())
        self.assertTrue((directory / "tools" / "data.json").exists())
        self.assertTrue((directory / "runner.py").exists())

    def test_a_fork_carries_the_tools(self):
        self.box.decide("parent", TOOL_USER, {"positions": [], "params": {}})
        self.box.fork("parent", "child")
        self.assertTrue(self.box.decide("child", TOOL_USER, {"positions": [], "params": {}}).result["ok"])


class SailTools(ToolsCase):
    def setUp(self):
        super().setUp()
        self.sail = FakeSail()
        self.sandbox = SailSandbox(self.sail, Path(self.dir.name) / "state.json", image_checkpoint=IMAGE)

    def uploads(self, start=0):
        return [c[2] for c in self.sail.calls[start:] if c[0] == "upload"]

    def test_the_tools_are_uploaded_with_the_kit_as_a_package(self):
        self.sandbox.decide("alpha", TOOL_USER, {})
        kit = kit_dir()
        self.assertEqual(self.uploads(), [f"{kit}/runner.py", f"{kit}/replay.py", f"{kit}/safety.py", f"{kit}/options_replay.py", f"{kit}/options_history.py", f"{kit}/tools/__init__.py",
                                          f"{kit}/tools/edge.py", f"{kit}/spec.json"])
        modes = {c[2]: c[3] for c in self.sail.calls if c[0] == "upload"}
        self.assertEqual(modes[f"{kit}/tools/edge.py"], 0o644)
        self.assertEqual(modes[f"{kit}/spec.json"], 0o600)
        files = self.sail.boxes["sb_0001"]["files"]
        self.assertEqual(files[f"{kit}/tools/edge.py"], (self.tools / "edge.py").read_bytes())
        self.assertFalse([f for f in files if f.endswith(("notes.txt", "deep.py"))])
        self.assertEqual(self.sail.execs[0]["egress"], SEALED)

    def test_a_new_tool_is_a_new_kit_and_is_uploaded_once_to_a_box_that_exists(self):
        self.sandbox.decide("alpha", TOOL_USER, {})
        first_kit = kit_dir()
        mark = len(self.sail.calls)
        self.sandbox.decide("alpha", TOOL_USER, {})
        self.assertEqual(self.uploads(mark), [f"{first_kit}/spec.json"])
        (self.tools / "later.py").write_text("def triple(x):\n    return 3 * x\n")
        second_kit = kit_dir()
        self.assertNotEqual(second_kit, first_kit)  # a new kit is a new directory
        mark = len(self.sail.calls)
        self.sandbox.decide("alpha", TOOL_USER, {})
        self.assertEqual(self.uploads(mark), [f"{second_kit}/{name}" for name in kit_files()] + [f"{second_kit}/spec.json"])
        self.assertIn(f"{second_kit}/tools/later.py", self.uploads(mark))
        self.assertEqual(self.sail.execs[-1]["cwd"], second_kit)
        mark = len(self.sail.calls)
        self.sandbox.decide("alpha", TOOL_USER, {})
        self.assertEqual(self.uploads(mark), [f"{second_kit}/spec.json"])

    def test_a_withdrawn_tool_is_not_in_the_directory_the_program_runs_from(self):
        # Regression: the kit was once uploaded over one fixed directory and nothing was ever
        # removed, so a tool the toolsmith withdrew stayed importable in every box that had it
        # (and in their forks), while new boxes lacked it. Each kit version now has its own
        # directory `/agent/kit-<digest>`, and programs run from there.
        self.sandbox.decide("alpha", TOOL_USER, {})
        old_kit = kit_dir()
        self.assertIn("tools/edge.py", self.sail.execs[-1]["in_cwd"])
        (self.tools / "edge.py").unlink()  # withdrawn
        (self.tools / "other.py").write_text("X = 1\n")
        self.sandbox.decide("alpha", TOOL_USER, {})
        ran = self.sail.execs[-1]
        self.assertEqual(ran["cwd"], kit_dir())
        self.assertNotEqual(ran["cwd"], old_kit)
        self.assertEqual(ran["in_cwd"], ["options_history.py", "options_replay.py", "replay.py", "runner.py", "safety.py", "spec.json", "tools/__init__.py", "tools/other.py"])
        self.assertIn(f"{old_kit}/tools/edge.py", ran["files"])  # the old kit is still on the disk, and out of reach of `import tools`
        self.sandbox.fork("alpha", "child")
        self.sandbox.decide("child", TOOL_USER, {})
        self.assertNotIn("tools/edge.py", self.sail.execs[-1]["in_cwd"])

    def test_a_withdrawn_tool_really_cannot_be_imported_in_a_box_that_once_had_it(self):
        self.sail.answer = self.really_run
        self.assertTrue(self.sandbox.decide("alpha", TOOL_USER, {"positions": [], "params": {}}).result["ok"])
        (self.tools / "edge.py").unlink()
        run = self.sandbox.decide("alpha", TOOL_USER, {"positions": [], "params": {}})
        self.assertFalse(run.result["ok"])
        self.assertIn("ModuleNotFoundError", run.result["error"])
        replayed = self.sandbox.replay("alpha", TOOL_USER, {}, tiny_tape(1), stake=200.0, limits={})
        self.assertFalse(replayed.result["ok"])

    def really_run(self, box, argv, spec):
        """Run the uploaded files for real, the whole of the box's disk under a temp root."""
        with tempfile.TemporaryDirectory() as root:
            for path, content in self.sail.boxes[box]["files"].items():
                target = Path(root) / Path(path).relative_to("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            command = argv[-1].replace(f"cd {REMOTE_DIR}/", f"cd {root}{REMOTE_DIR}/")
            done = subprocess.run([*argv[:-1], command], capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
            return done.stdout, done.stderr, done.returncode

    def test_the_uploaded_kit_really_runs_a_strategy_that_uses_a_tool(self):
        self.sail.answer = self.really_run
        decided = self.sandbox.decide("alpha", TOOL_USER, {"positions": [], "params": {"n": 5}})
        self.assertTrue(decided.result["ok"], decided.result)
        self.assertEqual(decided.result["memory"], {"doubled": 10, "again": 8})
        replayed = self.sandbox.replay("alpha", TOOL_USER, {}, tiny_tape(1), stake=200.0, limits={})
        self.assertTrue(replayed.result["ok"], replayed.result)
        self.assertEqual(replayed.result["errors"], 0)


if __name__ == "__main__":
    unittest.main()
