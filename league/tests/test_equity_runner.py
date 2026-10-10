"""The equity runs' entry points (A3): in-process `run_bars`, and `Isolated`, which slices the store in the parent and
asks the decider child to run the program. The child is hooks' (`league.equity.child`); here a fake decider answers the
"equity" kind's "needs" and "run" ops in-process, its answers through JSON as the real child's are.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from league.equity import config, synth
from league.equity.program import CodeRefused, load_program
from league.equity.runner import RUN_BUDGET_SECONDS, Isolated, ProgramRefused, Run, RunFailed, run_bars
from league.equity.store import LOOK, StoreRefused, mint_equity_gate_capability
from league.tests.test_equity_engine import gym_sizing

D = dt.date
CODE = """
NEEDS = {"symbols": ["SPY", "QQQ"], "history": 15, "max_hold_sessions": 5}
PARAMS = {"share": 0.25}

def decide(ctx):
    out = [{"sell": p["id"], "at": "open"} for p in ctx.positions if p["held_sessions"] >= 2]
    c = ctx.bars["SPY"].close
    if c[-1] < c[-2]:
        out.append({"buy": "SPY", "share": ctx.params["share"], "at": "close"})
    return out
"""


class FakeDecider:
    """The "equity" kind in-process: "needs" loads the program, "run" calls `run_bars`; answers through JSON."""

    def __init__(self, *, fail=None, answer=None):
        self.calls: list[tuple[str, str, dict, float | None]] = []
        self.fail, self.answer = fail, answer

    def kind(self, kind, op, payload, *, budget_seconds=None):
        self.calls.append((kind, op, dict(payload), budget_seconds))
        if self.fail == op:
            raise RuntimeError("the child died")
        if self.answer is not None and op in self.answer:
            return self.answer[op]
        try:
            if op == "needs":
                program = load_program(payload["code"], name=payload["name"], params=payload["params"])
                out = {"ok": True, "needs": program.needs.as_dict(), "sha": program.sha, "run_sha": program.run_sha}
            elif op == "run":
                out = {"ok": True, "result": run_bars(payload["code"], payload["params"], payload["bars"],
                                                      name=payload["name"], k=payload["k"],
                                                      capital=payload["capital"])}
            else:
                out = {"ok": False, "error": f"no op {op}"}
        except CodeRefused as exc:
            out = {"ok": False, "refused": True, "error": str(exc)}
        return json.loads(json.dumps(out, allow_nan=False))


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_store(Path(cls.dir.name) / "equity-daily", symbols=("SPY", "QQQ"),
                                         end=D(2026, 10, 9), gate=True)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def setUp(self):
        patcher = gym_sizing()
        patcher.start()
        self.addCleanup(patcher.stop)


class InProcess(Case):
    def test_run_bars_loads_and_replays(self):
        from league.equity.store import EquityStore

        bars = EquityStore(self.root).bars(["SPY", "QQQ"], "validation", history=15)
        result = run_bars(CODE, {"share": 0.2}, bars, name="dip", k=1.5, capital="2000")
        self.assertEqual((result["status"], result["program"], result["k"], result["capital"]), ("ok", "dip", 1.5,
                                                                                                    "2000"))
        self.assertEqual(result["params"], {"share": 0.2})
        json.dumps(result, allow_nan=False)
        with self.assertRaises(CodeRefused):
            run_bars("import os\n" + CODE, None, bars)


class Parent(Case):
    def test_validation_slices_the_window_with_history_and_never_sends_a_path(self):
        decider = FakeDecider()
        run = Isolated(decider, self.root).validation(CODE, None, name="dip")
        self.assertIsInstance(run, Run)
        self.assertEqual(run.result["status"], "ok")
        self.assertEqual((run.bars.window, run.bars.first, run.bars.symbols), ("validation", 15, ("SPY", "QQQ")))
        self.assertEqual((run.bars.day(run.bars.first), run.bars.day(run.bars.n - 1)), (D(2025, 1, 2), D(2025, 12, 31)))
        self.assertEqual([c[1] for c in decider.calls], ["needs", "run"], "NEEDS first: the parent never executes it")
        _, _, payload, budget = decider.calls[1]
        self.assertEqual(budget, RUN_BUDGET_SECONDS)
        self.assertEqual(set(payload), {"code", "params", "name", "bars", "k", "capital"})
        self.assertIs(payload["bars"], run.bars)
        self.assertFalse(any(str(self.root) in str(v) for k, v in payload.items() if k != "bars"))
        self.assertEqual(run.result["start"], "2025-01-02")

    def test_train_and_the_floors_segments(self):
        iso = Isolated(FakeDecider(), self.root)
        run = iso.train(CODE, None, name="dip", start=D(2023, 1, 3), end=D(2023, 6, 30), k=1.5)
        self.assertEqual((run.result["window"], run.result["start"], run.result["end"], run.result["k"]),
                         ("train", "2023-01-03", "2023-06-30", 1.5))
        segments = iso.segments(CODE, None, name="dip")
        self.assertEqual([(r.result["start"], r.result["end"]) for r in segments],
                         [(a.isoformat(), b.isoformat()) for a, b in config.TRAIN_ERA_SEGMENTS])
        self.assertTrue(all(r.bars.window == "train" for r in segments))
        self.assertEqual(iso.needs(CODE, {"share": 0.5}, name="dip"),
                         {"symbols": ["SPY", "QQQ"], "history": 15, "max_hold_sessions": 5})

    def test_the_look_needs_the_gates_capability_and_reads_to_the_last_close(self):
        iso = Isolated(FakeDecider(), self.root)
        with self.assertRaises(StoreRefused):
            iso.look(CODE, None, name="dip", gate=object())
        run = iso.look(CODE, None, name="dip", gate=mint_equity_gate_capability(self.root, "the one look"))
        self.assertEqual((run.bars.window, run.result["window"]), (LOOK, LOOK))
        self.assertEqual((run.result["start"], run.result["end"]), (config.LOOK_FIRST.isoformat(), "2026-10-09"))
        self.assertEqual(run.bars.day(run.bars.first - 1), D(2025, 12, 31), "history from Validation")

    def test_failures_and_refusals(self):
        with self.assertRaises(ProgramRefused):
            Isolated(FakeDecider(), self.root).validation("import os\n" + CODE, None, name="bad")
        self.assertTrue(issubclass(ProgramRefused, CodeRefused))
        for decider in (FakeDecider(fail="run"), FakeDecider(fail="needs"),
                        FakeDecider(answer={"run": {"ok": True, "result": {"status": "error", "reason": "x"}}}),
                        FakeDecider(answer={"run": {"ok": False, "error": "deadline"}}),
                        FakeDecider(answer={"run": {"ok": True}}), FakeDecider(answer={"run": "no"}),
                        FakeDecider(answer={"needs": {"ok": True, "needs": {"symbols": ["TSLA"]}}})):
            with self.subTest(calls=decider.answer or decider.fail), self.assertRaises(RunFailed):
                Isolated(decider, self.root).validation(CODE, None, name="dip")


if __name__ == "__main__":
    unittest.main()
