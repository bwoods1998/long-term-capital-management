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
from league.sandbox import KIT_FILES, REMOTE_DIR, SEALED, LocalSandbox, Run, SailSandbox, SandboxError

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
        self.assertEqual(sorted(p.name for p in directory.iterdir() if p.is_file()), ["replay.py", "runner.py", "safety.py", "spec.json"])

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

    def test_a_program_that_prints_no_result_line_is_an_error_result(self):
        directory = self.box._dir("broken")
        (directory / "runner.py").write_text("import sys\nsys.stderr.write('kit is broken')\nsys.exit(3)\n")
        run = self.box.decide("broken", TINY, {})
        self.assertFalse(run.result["ok"])
        self.assertIn("no result line (exit 3)", run.result["error"])
        self.assertIn("kit is broken", run.result["error"])

    def test_a_run_past_the_timeout_is_an_error_result_not_a_hang(self):
        directory = self.box._dir("sleeper")
        (directory / "runner.py").write_text("import time\ntime.sleep(30)\n")
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
        self._box(box)["egress"] = list(hosts)
        return {}

    def get(self, box):
        self._call("get", box)
        return {"sailbox_id": box, "status": self._box(box)["status"]}

    def resume(self, box):
        self._call("resume", box)
        self._box(box)["status"] = "running"
        return {}

    def upload(self, box, path, content, *, mode=0o600):
        self._call("upload", box, path, mode)
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
        spec = json.loads(state["files"][f"{REMOTE_DIR}/spec.json"].decode("utf-8"))
        self.execs.append({"box": box, "argv": list(argv), "timeout": timeout, "egress": state["egress"], "spec": spec, "files": sorted(state["files"])})
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


class SailFirstRun(SailCase):
    def test_a_new_agents_box_is_made_from_the_image_and_sealed_before_anything_else(self):
        run = self.sandbox.decide("alpha", TINY, {"now": "n"})
        kit = [("upload", "sb_0001", f"{REMOTE_DIR}/{name}", 0o644) for name in KIT_FILES]
        self.assertEqual(self.sail.calls[0], ("from_checkpoint", IMAGE, "league-alpha"))
        self.assertEqual(self.sail.calls[1], ("set_egress", "sb_0001", ["sealed.invalid"]))
        self.assertEqual(self.sail.calls[2:5], kit)
        self.assertEqual(self.sail.calls[5], ("upload", "sb_0001", f"{REMOTE_DIR}/spec.json", 0o600))
        self.assertEqual(self.sail.calls[6][0], "exec")
        self.assertEqual(self.sail.calls[7:], [("sleep", "sb_0001")])
        self.assertTrue(run.created)
        self.assertEqual(SEALED, ["sealed.invalid"])

    def test_the_box_is_sealed_when_the_program_runs(self):
        self.sandbox.decide("alpha", TINY, {})
        self.sandbox.replay("alpha", TINY, {}, {"venue": "alpaca"}, stake=200.0, limits={})
        self.assertEqual([e["egress"] for e in self.sail.execs], [SEALED, SEALED])

    def test_the_command_the_spec_and_the_files_in_the_box(self):
        self.sandbox.decide("alpha", TINY, {"now": "n", "params": {"notional": 9}})
        (ran,) = self.sail.execs
        self.assertEqual(ran["argv"], ["sh", "-c", "cd /agent && timeout 30 python3 -E -s runner.py spec.json"])
        self.assertEqual(ran["timeout"], 60)
        self.assertEqual(ran["files"], sorted(f"/agent/{name}" for name in (*KIT_FILES, "spec.json")))
        self.assertEqual({k: v for k, v in ran["spec"].items() if k != "token"}, {"code": TINY, "ctx": {"now": "n", "params": {"notional": 9}}})
        self.assertRegex(ran["spec"]["token"], r"^[0-9a-f]{32}$")
        for name, source in KIT_FILES.items():
            self.assertEqual(self.sail.boxes["sb_0001"]["files"][f"/agent/{name}"], Path(source).read_bytes())

    def test_needs_and_replay_send_their_own_specs_and_commands(self):
        self.sandbox.needs("alpha", TINY)
        self.sandbox.replay("alpha", TINY, {"n": 1}, {"venue": "alpaca", "steps": []}, stake=150.0, limits={"max_order_usd": 75}, timeout=123.9)
        needs, replay = self.sail.execs
        self.assertEqual({k: v for k, v in needs["spec"].items() if k != "token"}, {"code": TINY, "mode": "needs"})
        self.assertEqual(replay["argv"][-1], "cd /agent && timeout 123 python3 -E -s replay.py --spec spec.json")
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
                command = argv[-1].replace(f"cd {REMOTE_DIR} ", f"cd {root}{REMOTE_DIR} ")
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
        # BUG (HIGH, security): sandbox.py:162-173. `_ensure` writes the new box into the state
        # file BEFORE it calls `set_egress`, and only a box it has just created is ever sealed.
        # When sealing fails, the run raises (good) but the box stays recorded; the next
        # `decide`/`replay` for that agent finds it, resumes it, uploads the kit and EXECUTES THE
        # AGENT'S CODE IN A BOX WITH ITS NETWORK OPEN, with no second attempt to seal. One
        # transient Sail API error at creation turns into a permanently unsealed box, across House
        # restarts (the state file survives). Forks take the same path (`fork` -> `_ensure`).
        # FIX: record the box only after `set_egress` succeeds, and on failure `terminate` it
        # (best effort) and forget it; or keep a `sealed` map in the state and (re)seal any box
        # not marked sealed before every run.
        self.sail.failing["set_egress"] = Boom("egress API is down for a moment")
        with self.assertRaises(SandboxError):
            self.sandbox.decide("alpha", TINY, {})
        del self.sail.failing["set_egress"]  # the API is back
        try:
            self.sandbox.decide("alpha", TINY, {})
        except SandboxError:
            pass  # refusing to run would be fine too
        for ran in self.sail.execs:
            self.assertEqual(ran["egress"], SEALED, "agent code ran in a box whose network was never closed")

    def test_an_unsealed_box_is_not_trusted_after_a_restart_either(self):
        # BUG: the same defect as above, seen across a House restart: the unsealed box is in the
        # state file, and a new `SailSandbox` runs code in it without sealing it.
        self.sail.failing["set_egress"] = Boom("egress API is down for a moment")
        with self.assertRaises(SandboxError):
            self.sandbox.decide("alpha", TINY, {})
        del self.sail.failing["set_egress"]
        try:
            self.new_sandbox().replay("alpha", TINY, {}, {}, stake=200.0, limits={})
        except SandboxError:
            pass
        for ran in self.sail.execs:
            self.assertEqual(ran["egress"], SEALED)

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
        self.assertEqual(uploads, [("upload", "sb_0001", "/agent/spec.json", 0o600)])
        self.assertNotIn("from_checkpoint", self.sail.names(mark))
        self.assertNotIn("set_egress", self.sail.names(mark))

    def test_a_new_kit_digest_is_uploaded_again_once(self):
        self.sandbox.decide("alpha", TINY, {})
        with mock.patch.object(sandbox_module, "_kit_digest", return_value="a-new-release"):
            mark = len(self.sail.calls)
            self.sandbox.decide("alpha", TINY, {})
            self.assertEqual(len([c for c in self.sail.calls[mark:] if c[0] == "upload"]), len(KIT_FILES) + 1)
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
            self.assertEqual(names.count("upload"), len(KIT_FILES) + 1)
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
        self.assertEqual(self.sail.names(mark).count("upload"), len(KIT_FILES) + 1)

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
        self.sail.failing["set_egress"] = Boom("egress API is down")
        with self.assertRaises(SandboxError):
            self.sandbox.fork("parent", "child")
        self.assertNotIn("exec", self.sail.names(8))


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


if __name__ == "__main__":
    unittest.main()
