"""The decider's generic request kinds (release E1, A8.8; league/live/decider.py `kind_load`, `kind`, `kind_drop`;
league/equity/kinds.py; league/equity/child.py): one table maps a kind to the module its isolated child runs, the same
isolation as an options decision (empty environment, rlimits, its own network namespace where the box allows one,
uid 65534 on a root House), every kind load reloaded into a restarted child, and the House's deadline.

The "equity" kind's own semantics are tested in-process with core's functions mocked at their interface (the program,
the ctx, the runner: league/equity/INTERFACES.md 4.4-4.8); the child process is tested with a probe kind defined in this
module (the child imports it), and once with the real "equity" kind, skipped until core lands.

This module is also the probe kind's module: `handle` below runs inside the child, so its top level imports only the
standard library and league.live.decider."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from league.live import decider as D

PROBE = "league.tests.test_equity_decider"
#: The child's entry with the probe kind added to its table (the child starts as the House's would, then runs this).
CHILD = ("from league.equity import kinds\n"
         f"kinds.KINDS['probe'] = {PROBE!r}\n"
         "from league.live.decider import child_main\n"
         "child_main()\n")


def handle(op, payload, state):
    """THE PROBE KIND (in the child): "load"/"drop" an instance; "count" each loaded instance's calls (fresh memory
    after a restart starts at 1); "whoami" the child's environment, pid and limits; "sleep" past a deadline."""
    loaded = state.setdefault("loaded", {})
    if op == "load":
        if payload.get("refuse"):
            return {"ok": False, "refused": True, "error": "probe refused"}
        loaded[payload["key"]] = 0
        return {"ok": True, "needs": {"n": len(loaded)}, "sha": "s", "run_sha": "r"}
    if op == "drop":
        loaded.pop(payload.get("key"), None)
        return {"ok": True}
    if op == "count":
        for key in loaded:
            loaded[key] += 1
        return {"ok": True, "loaded": dict(loaded)}
    if op == "whoami":
        limits = {}
        try:
            for line in Path("/proc/self/limits").read_text().splitlines()[1:]:
                limits[line[:26].strip()] = line[26:].split()[:2]
        except OSError:
            pass
        return {"ok": True, "env": sorted(os.environ), "pid": os.getpid(), "limits": limits}
    if op == "sleep":
        time.sleep(float(payload["seconds"]))
        return {"ok": True}
    return {"ok": False, "error": f"unknown probe op {op!r}"}


class ProbeDecider(D.Decider):
    """The House's Decider, spawned exactly as it spawns (empty env, limits, namespace), running `CHILD`."""

    def _spawn(self, budget_seconds=10.0):
        real = subprocess.Popen

        def popen(command, **kw):
            if "league.live.decider" not in command:
                return real(command, **kw)              # the namespace probe
            i = command.index("-m")
            return real(command[:i] + ["-c", CHILD] + command[i + 2:], **kw)

        with mock.patch.object(D.subprocess, "Popen", side_effect=popen):
            super()._spawn(budget_seconds=budget_seconds)


# ------------------------------------------------------------------------------------------------ in process
class FakeRunner:
    def __init__(self, program):
        self.program, self.calls = program, 0

    def decide(self, ctx):
        self.calls += 1
        ctx["positions"].append({"id": 99})          # a program that mutates what it was given
        return [{"buy": "SPY", "share": 0.5, "at": "close", "tag": self.program.name}]

    def stats(self):
        return {"calls": self.calls, "errors": 0, "timeouts": 0, "seconds": 0.0, "messages": [], "disqualified": False}


class FakeProgram:
    def __init__(self, code, name, params):
        self.code, self.name, self.params = code, name, dict(params or {})
        self.needs = mock.Mock(as_dict=lambda: {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2})
        self.sha, self.run_sha = "sha-" + name, "run-" + name
        self.started = []

    def start(self, *, timeout=1.0, max_errors=25, budget_seconds=None):
        self.started.append((timeout, max_errors, budget_seconds))
        return FakeRunner(self)


def load_program(code, *, name="program", params=None):
    from league.gym.safety import CodeRefused

    if "import os" in code:
        raise CodeRefused("imports os")
    return FakeProgram(code, name, params)


def build(inputs):
    if inputs.get("broken"):
        raise ValueError("t's bar is missing")
    return {"positions": list(inputs["positions"]), "day": inputs["day"]}


def ctx_bytes(ctx):
    return json.dumps(ctx, sort_keys=True).encode()


@unittest.skipUnless(HAVE, "numpy not installed")
class TheEquityKindInProcess(unittest.TestCase):
    def setUp(self):
        from league.equity import ctx as C
        from league.equity import program as P
        from league.equity import runner as RN

        self.runs = []

        def run_bars(code, params, bars, **kw):
            load_program(code, name=kw.get("name", "program"), params=params)   # CodeRefused, as the real one
            self.runs.append(((code, params, bars), kw))
            return {"status": "ok", "summary": {"trades": 3}}

        patches = [mock.patch.object(P, "load_program", side_effect=load_program),
                   mock.patch.object(C, "build", side_effect=build), mock.patch.object(C, "ctx_bytes", side_effect=ctx_bytes),
                   mock.patch.object(RN, "run_bars", side_effect=run_bars)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.decider = D.InlineDecider()

    def load(self, key="seed@1:r", code="NEEDS = {}", **kw):
        return self.decider.kind_load("equity", key, {"code": code, "params": {"share": 0.5}, "name": key.split("@")[0],
                                                      "timeout": 1.0, "max_errors": 25, **kw})

    def test_load_decide_and_drop(self):
        self.assertEqual(self.load(), {"needs": {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2},
                                       "sha": "sha-seed", "run_sha": "run-seed"})
        self.assertIn(("equity", "seed@1:r"), self.decider.kind_loaded)
        inputs = {"positions": [{"id": 1}], "day": "2026-10-09"}
        answer = self.decider.kind("equity", "decide", {"jobs": [{"key": "seed@1:r", "inputs": inputs},
                                                                 {"key": "gone@1:r", "inputs": inputs},
                                                                 {"key": "seed@1:r", "inputs": {"broken": True}}]})
        self.assertTrue(answer["ok"])
        result = answer["results"]
        # Two jobs of one key: the last answer stands (the book sends one job a key); a broken ctx is that job's alone.
        self.assertEqual(result["seed@1:r"]["intents"], [])
        self.assertIn("ctx: ValueError", result["seed@1:r"]["error"])
        self.assertEqual(result["gone@1:r"], {"intents": [], "stats": None, "missing": True})
        answer = self.decider.kind("equity", "decide", {"jobs": [{"key": "seed@1:r", "inputs": inputs}]})
        one = answer["results"]["seed@1:r"]
        self.assertEqual(one["intents"], [{"buy": "SPY", "share": 0.5, "at": "close", "tag": "seed"}])
        self.assertEqual(one["stats"]["calls"], 2, "the runner's memory is kept between requests")
        # The provenance is the ctx the program was given, before it could change it.
        self.assertEqual(one["ctx_sha"], hashlib.sha256(ctx_bytes(build(inputs))).hexdigest())
        self.decider.kind_drop("equity", "seed@1:r")
        self.assertNotIn(("equity", "seed@1:r"), self.decider.kind_loaded)
        answer = self.decider.kind("equity", "decide", {"jobs": [{"key": "seed@1:r", "inputs": inputs}]})
        self.assertTrue(answer["results"]["seed@1:r"]["missing"])

    def test_a_refused_program(self):
        with self.assertRaises(D.ProgramRefused):
            self.load(code="import os")
        self.assertEqual(self.decider.kind_loaded, {})
        answer = self.decider.kind("equity", "needs", {"code": "import os", "params": {}, "name": "bad"})
        self.assertEqual((answer["ok"], answer["refused"]), (False, True))
        answer = self.decider.kind("equity", "run", {"code": "import os", "params": {}, "name": "bad", "bars": None})
        self.assertEqual((answer["ok"], answer.get("refused")), (False, True))

    def test_needs_and_run_keep_nothing(self):
        answer = self.decider.kind("equity", "needs", {"code": "NEEDS = {}", "params": {}, "name": "n"})
        self.assertEqual(answer, {"ok": True, "needs": {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2},
                                  "sha": "sha-n", "run_sha": "run-n"})
        self.assertEqual(self.decider._kinds["equity"]["runners"], {})
        answer = self.decider.kind("equity", "run", {"code": "C", "params": {"h": 8}, "name": "r", "bars": {"n": 3},
                                                     "k": 1.5, "capital": "1000"}, budget_seconds=1200)
        self.assertEqual(answer, {"ok": True, "result": {"status": "ok", "summary": {"trades": 3}}})
        args, kw = self.runs[-1]
        self.assertEqual((args, kw), (("C", {"h": 8}, {"n": 3}), {"name": "r", "k": 1.5, "capital": "1000"}))

    def test_unknown_ops_and_kinds_and_the_remembered_routes(self):
        self.assertIn("unknown equity op", self.decider.kind("equity", "train", {})["error"])
        answer = self.decider.kind("options", "decide", {"jobs": []})
        self.assertFalse(answer["ok"])
        self.assertIn("no decider kind", answer["error"])
        for op in ("load", "drop"):
            with self.assertRaises(ValueError):
                self.decider.kind("equity", op, {"key": "k"})

    def test_each_kind_keeps_its_own_state(self):
        from league.equity import kinds as K

        with mock.patch.dict(K.KINDS, {"probe": PROBE}):
            self.decider.kind_load("probe", "seed@1:r", {})
            self.load()
            self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"seed@1:r": 1})
        self.assertEqual(set(self.decider._kinds), {"probe", "equity"})
        self.assertEqual(set(self.decider._kinds["equity"]["runners"]), {"seed@1:r"})

    def test_the_deadlines(self):
        seen = []
        self.decider._ask = lambda message, deadline: seen.append((message[2], deadline)) or {"ok": True}
        self.decider.kind("equity", "decide", {"jobs": [{"key": "a"}, {"key": "b"}]})
        self.decider.kind("equity", "decide", {"jobs": [{"key": "a"}] * 500})
        self.decider.kind("equity", "run", {}, budget_seconds=1200.0)
        self.decider.kind("equity", "needs", {})
        self.assertEqual(seen, [("decide", D.batch_deadline(1.0, 2)), ("decide", D.MAX_BATCH_SECONDS),
                                ("run", 1200.0), ("needs", 30.0)])


class TheTable(unittest.TestCase):
    def test_module_for(self):
        from league.equity import child, kinds

        self.assertEqual(kinds.KINDS, {"equity": "league.equity.child"})
        self.assertIs(kinds.module_for("equity"), child)
        for bad in ("options", None, 3):
            with self.assertRaises(ValueError):
                kinds.module_for(bad)
        self.assertEqual(child.OPS, ("load", "drop", "decide", "needs", "run"))

    def test_the_childs_runtime_holds_every_kind_module_and_what_it_imports(self):
        """A root House's child runs from a copy of `runtime_files()` alone: from such a copy, with the House's empty
        environment and -E -s, the child imports the decider, the kind table, every kind's module and the modules the
        "equity" kind imports per op (the program, the ctx, the runner), and answers a "run" (the engine over a store
        slice: its calendar is `ltcm.data`'s, imported only when a run reads it)."""
        files = D.runtime_files()
        repo = D.REPO
        for name in D.RUNTIME_FILES:
            self.assertIn(name, files)
        for directory in ("league/equity", "league/gym"):
            for path in (repo / directory).glob("*.py"):
                self.assertIn(path.relative_to(repo).as_posix(), files)
        self.assertFalse([f for f in files if not f.endswith(".py")], "documentation is never copied")
        script = ("import league.live.decider\n"
                  "from league.equity import kinds\n"
                  "for kind in kinds.KINDS:\n"
                  "    kinds.module_for(kind)\n"
                  "import league.equity.program, league.equity.ctx, league.equity.runner, league.equity.store\n"
                  "import tempfile\n"
                  "from league.equity import child, synth\n"
                  "from league.equity.store import EquityStore\n"
                  "code = (\"NEEDS = {'symbols': ['SPY'], 'history': 2}\\nPARAMS = {}\\n\"\n"
                  "        \"def decide(ctx):\\n\"\n"
                  "        \"    return [{'buy': 'SPY', 'share': 0.5}] if not ctx.positions else []\\n\")\n"
                  "root = synth.constant_store(tempfile.mkdtemp(), sessions=12, step=1.0)\n"
                  "bars = EquityStore(root).bars(['SPY'], 'validation', history=2)\n"
                  "state = {}\n"
                  "answer = child.handle('run', {'code': code, 'params': {}, 'name': 'p', 'bars': bars, 'k': 1.0,\n"
                  "                              'capital': None}, state)\n"
                  "assert answer['ok'] and answer['result']['status'] == 'ok', answer\n"
                  "assert answer['result']['lots'], 'the run traded'\n"
                  "print('imported')\n")
        with tempfile.TemporaryDirectory() as tmp:
            for name in files:
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / name, Path(tmp) / name)
            done = subprocess.run([sys.executable, "-E", "-s", "-c", script], cwd=tmp, capture_output=True, text=True,
                                  timeout=120, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": tmp,
                                                    "OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "imported"), done.stderr[-2000:])


# ------------------------------------------------------------------------------------------------ the child process
@unittest.skipUnless(HAVE, "numpy not installed")
@unittest.skipUnless(sys.platform.startswith("linux"), "Linux rlimits and /proc")
class TheKindsChild(unittest.TestCase):
    def setUp(self):
        self.decider = ProbeDecider(timeout=0.5, python=sys.executable, allow_unisolated=True)
        self.addCleanup(self.decider.close)

    def test_the_same_isolation_as_an_options_decision(self):
        os.environ["GATEWAY_TOKEN"] = "x" * 40
        try:
            self.decider.kind_load("probe", "a", {})
            who = self.decider.kind("probe", "whoami", {})
        finally:
            del os.environ["GATEWAY_TOKEN"]
        self.assertTrue(who["ok"])
        self.assertNotIn("GATEWAY_TOKEN", who["env"])
        self.assertNotIn("SAIL_API_KEY", who["env"])
        self.assertNotEqual(who["pid"], os.getpid())
        self.assertEqual(who["pid"], self.decider.pid)
        self.assertEqual(who["limits"]["Max file size"], [str(D.FILE_MB * 1024 * 1024)] * 2)
        self.assertEqual(who["limits"]["Max processes"], ["0", "0"])
        self.assertEqual(who["limits"]["Max address space"], [str(D.MEMORY_MB * 1024 * 1024)] * 2)
        if shutil.which("unshare") and subprocess.run(["unshare", "--net", "--map-root-user", "true"],
                                                      capture_output=True).returncode == 0:
            self.assertTrue(self.decider.netns, "its own network namespace where the box allows one")
            self.assertLessEqual(set(self.decider.ping()["routed_interfaces"]), {"lo"})

    def test_a_restarted_child_has_every_kind_load_again_with_fresh_memory(self):
        self.decider.kind_load("probe", "a", {})
        self.decider.kind_load("probe", "b", {})
        self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"a": 1, "b": 1})
        self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"a": 2, "b": 2})
        first = self.decider.pid
        self.decider._kill()
        self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"a": 1, "b": 1})
        self.assertNotEqual(self.decider.pid, first)
        self.decider.kind_drop("probe", "b")
        self.decider._kill()
        self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"a": 1}, "a dropped load is not reloaded")
        with self.assertRaises(D.ProgramRefused):
            self.decider.kind_load("probe", "c", {"refuse": True})
        self.assertNotIn(("probe", "c"), self.decider.kind_loaded)

    def test_a_child_past_its_deadline_is_killed_restarted_and_reloaded(self):
        self.decider.kind_load("probe", "a", {})
        began = time.monotonic()
        with self.assertRaises(D.DeciderError) as caught:
            self.decider.kind("probe", "sleep", {"seconds": 30}, budget_seconds=0.75)
        self.assertIn("in time", str(caught.exception))
        self.assertLess(time.monotonic() - began, 10.0)
        self.assertEqual(self.decider.restarts, 1)
        self.assertIsNone(self.decider.proc)
        self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"a": 1})

    def test_options_programs_and_kinds_share_one_child(self):
        from league.tests.live_fakes import VERTICAL

        self.decider.load("v", VERTICAL, {}, "vert")
        self.decider.kind_load("probe", "a", {})
        pid = self.decider.pid
        self.decider._kill()
        self.assertEqual(self.decider.kind("probe", "count", {})["loaded"], {"a": 1})
        self.assertNotEqual(self.decider.pid, pid)
        self.assertIn("v", self.decider.loaded, "the options program is still remembered for its next decide")


@unittest.skipUnless(HAVE, "numpy not installed")
@unittest.skipUnless(sys.platform.startswith("linux"), "Linux rlimits and /proc")
class TheEquityKindsChild(unittest.TestCase):
    """The real "equity" kind in the House's child (core's program and ctx, hooks' child)."""

    CODE = '''
import numpy as np

NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}
PARAMS = {"share": 0.5}

def decide(ctx):
    return [{"buy": "SPY", "share": ctx.params["share"], "at": "close", "tag": "probe"}]
'''

    def test_needs_and_load_in_the_child(self):
        from league.equity import program as P

        try:
            local = P.load_program(self.CODE, name="probe")
        except NotImplementedError as exc:
            self.skipTest(f"core is not on this branch yet ({exc})")
        decider = D.Decider(timeout=0.5, python=sys.executable, allow_unisolated=True)
        try:
            answer = decider.kind("equity", "needs", {"code": self.CODE, "params": {}, "name": "probe"})
            self.assertTrue(answer["ok"], answer)
            self.assertEqual((answer["needs"], answer["sha"]), (local.needs.as_dict(), local.sha))
            info = decider.kind_load("equity", "probe@1:r", {"code": self.CODE, "params": {}, "name": "probe",
                                                             "timeout": 0.5, "max_errors": 25})
            self.assertEqual(info["run_sha"], local.run_sha)
            self.assertEqual(info["params"], {"share": 0.5}, "the merged PARAMS: the live ctx's, as the Gym's (I6)")
            over = decider.kind_load("equity", "probe@2:r", {"code": self.CODE, "params": {"share": 0.25},
                                                             "name": "probe", "timeout": 0.5, "max_errors": 25})
            self.assertEqual(over["params"], {"share": 0.25})
            refused = decider.kind("equity", "needs", {"code": "import os\n" + self.CODE, "params": {}, "name": "bad"})
            self.assertEqual((refused["ok"], refused["refused"]), (False, True))
        finally:
            decider.close()


if __name__ == "__main__":
    unittest.main()
