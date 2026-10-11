"""The panel runs' entry points (release E4, package D; league/xs/runner.py, league/xs/child.py): the in-process run,
the "panel" kind's five ops inside the decider child, the decider-isolated wrapper and the restart check's stream.

SYNTHETIC DATA ONLY. Three layers:
- with package C's functions replaced at their interface by `test_xs_engine`'s doubles and the panel store by
  `FakeStore` below (in-memory synthetic slices), through the real `InlineDecider` (its pickle and JSON round trip):
  what is held is this package's own logic;
- `WithTheRealCore`: the same entry points over package C's REAL store, ctx, program and synthetic panel
  (`league.xs.synth`). They skip while package C is a stub (as it was when this package was built) and run from the
  moment it is merged;
- `TheChildsRuntime`: a "run" in a subprocess from a copy of the child's sealed runtime files alone."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Sequence
from unittest import mock

import numpy as np

from league.equity import config as e1
from league.equity.store import GATE_MARK, StoreRefused, from_ordinal, mint_equity_gate_capability
from league.live import decider as D
from league.tests import test_xs_engine as fx
from league.xs import child, config, ctx, engine, placebo, program, results, runner, store, synth

CODE = '''
NEEDS = {"panel": "sp500", "history": 20, "max_names": 10, "rebalance": "weekly", "weekday": 0}
PARAMS = {"k": 5}

def decide(ctx):
    ids = sorted(int(i) for i in ctx.ids)
    return {"target": {i: int(10000 / PARAMS["k"]) / 10000 for i in ids[:PARAMS["k"]]}, "at": "open"}
'''
ROTATE = '''
NEEDS = {"panel": "sp500", "history": 20, "max_names": 10, "rebalance": "weekly", "weekday": 0}
PARAMS = {}
STATE = {"n": 0}

def decide(ctx):
    STATE["n"] += 1
    ids = sorted(int(i) for i in ctx.ids)
    start = 5 * (STATE["n"] % 2)
    return {"target": {i: 0.2 for i in ids[start:start + 5]}, "at": "close"}
'''


def core_built() -> bool:
    """Whether package C's functions are built (they raised NotImplementedError as Step 0's stubs)."""
    try:
        config.decision_due(dt.date(2024, 1, 2), "weekly", 0)
        program.parse_needs({"panel": "sp500", "rebalance": "weekly"})
    except NotImplementedError:
        return False
    return True


# ============================================================================================ the store's double
class FakeStore:
    """A double of `store.PanelStore`: in-memory synthetic slices by window (`PANELS`), cut as the store cuts them
    (look-back, then the run's sessions), their ids salted by the run key, a half run's other half invisible."""

    PANELS: dict[str, store.PanelBars] = {}
    asked: list[dict[str, Any]] = []
    LOOK_BACK = 25

    def __init__(self, root: Any, *, gate: Any = None):
        self.root, self.gate = Path(root), gate

    def _check(self, window: str) -> None:
        if window in ("look", "forward") and self.gate is None:
            raise StoreRefused(f"the {window} days open only for the gate")

    def sessions(self, window: str) -> list[dt.date]:
        self._check(window)
        bars = self.PANELS[window]
        return [from_ordinal(int(d)) for d in bars.days[bars.first:]]

    def _piece(self, window: str, run_key: str, start: Any, end: Any, half: Any, aids: Any) -> store.Slice:
        self._check(window)
        bars = self.PANELS[window]
        days = [from_ordinal(int(d)) for d in bars.days]
        run = [i for i in range(bars.first, bars.n) if (start is None or days[i] >= start)
               and (end is None or days[i] <= end)]
        if not run:
            raise StoreRefused("no session in the span")
        lo, hi = max(0, run[0] - self.LOOK_BACK), run[-1] + 1
        names = bars.raw.shape[1] - bars.ref
        ids = np.sort(np.array([int.from_bytes(hashlib.sha256(f"{run_key}|{c}".encode()).digest()[:4], "big") >> 1
                                for c in range(names)], dtype=np.int64)).astype(np.int32)
        elig0 = bars.elig0[lo:hi].copy()
        if half is not None:
            elig0[:, [bars.ref + c for c in range(names) if c % 2 != half]] = False
        piece = fx.changed(bars, days=bars.days[lo:hi], early=bars.early[lo:hi], first=run[0] - lo,
                           raw=bars.raw[lo:hi], adj=bars.adj[lo:hi], elig0=elig0, ids=ids, window=window,
                           dither_key=hashlib.sha256(run_key.encode()).digest())
        self.asked.append({"window": window, "run_key": run_key, "start": start, "end": end, "half": half,
                           "aids": aids, "gate": self.gate})
        return store.Slice(bars=piece, aids=np.arange(1, bars.raw.shape[1] + 1, dtype=np.int32), run_key=run_key)

    def bars(self, window: str, *, history: int, run_key: str, start: Any = None, end: Any = None,
             aids: Any = None) -> store.Slice:
        return self._piece(window, run_key, start, end, None, aids)

    def train(self, start: dt.date, end: dt.date, *, history: int, run_key: str, half: Any = None) -> store.Slice:
        return self._piece("train", run_key, start, end, half, None)


class RunnerCase(fx.EngineCase):
    """The doubles of package C, the fake store and an `InlineDecider`."""

    def setUp(self):
        super().setUp()
        FakeStore.PANELS = {
            "train": fx.panel(sessions=130, first=25),
            "validation": fx.panel(sessions=80, first=25, window="validation", start=dt.date(2025, 3, 3), seed=5),
            "look": fx.panel(sessions=120, first=25, window="look", start=dt.date(2025, 10, 1), seed=6),
            "forward": fx.panel(sessions=70, first=25, window="forward", start=dt.date(2026, 9, 1), seed=7),
        }
        FakeStore.asked = []
        patcher = mock.patch.object(store, "PanelStore", FakeStore)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (Path(self.tmp) / GATE_MARK).write_text("test\n")
        self.gate = mint_equity_gate_capability(self.tmp, "the one look")
        self.decider = D.InlineDecider()
        self.iso = runner.Isolated(self.decider, self.tmp, nice=None)
        self.train_days = FakeStore(self.tmp).sessions("train")


# ================================================================================================ the in-process run
class RunBars(fx.EngineCase):
    def test_it_loads_the_program_and_replays_it(self):
        bars = fx.panel()
        result = runner.run_bars(CODE, None, bars, name="five")
        self.assertEqual((result["status"], result["program"], result["capital"], result["k"]),
                         ("ok", "five", "1000", 1.0))
        self.assertEqual(result["params"], {"k": 5})
        self.assertEqual(result["summary"]["lots"], 5)
        wide = runner.run_bars(CODE, {"k": 6}, bars, name="six", k=1.5, capital="500", placebos=10, calls=True)
        self.assertEqual((wide["capital"], wide["k"], wide["params"]), ("500", 1.5, {"k": 6}))
        self.assertEqual(wide["summary"]["lots"], 6)
        self.assertEqual(wide["placebo"]["n"], 10)
        self.assertTrue(wide["calls"])
        self.assertTrue(all(abs(lot["weight"] - 1 / 6) < 1e-3 for lot in wide["lots"]), "a lot is w x ITS sleeve")

    def test_a_program_that_does_not_load_is_refused_and_a_run_that_breaks_is_an_error_record(self):
        with self.assertRaises(fx.CodeRefused):
            runner.run_bars("refuse me", None, fx.panel())
        broken = runner.run_bars(CODE, None, "not bars")
        self.assertEqual(broken["status"], "error")


# ============================================================================================== the child's five ops
class TheChildsOps(fx.EngineCase):
    def setUp(self):
        super().setUp()
        self.bars = fx.panel()
        self.state: dict[str, Any] = {}
        self.needs = program.Needs("sp500", 20, 10, "weekly", 0, 60)

    def ask(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        """One request as the decider's child answers it: through JSON."""
        return json.loads(json.dumps(D._finite(child.handle(op, payload, self.state)), default=D._plain_default,
                                     allow_nan=False))

    def inputs(self, t: int, positions: Sequence[dict] = (), **book: Any) -> ctx.Inputs:
        book = {"cash": 1000.0, "equity": 1000.0, "budget": 1000.0, "params": {"k": 5}, **book}
        return ctx.inputs_from_panel(self.bars, t, needs=self.needs, positions=positions, **book)

    def test_the_kind_serves_five_ops(self):
        self.assertEqual(child.OPS, ("load", "drop", "decide", "needs", "run"))
        answer = self.ask("train", {})
        self.assertFalse(answer["ok"])
        self.assertIn("unknown panel op 'train'", answer["error"])
        self.assertNotIn("refused", answer)

    def test_load_needs_and_drop(self):
        answer = self.ask("load", {"key": "p@1:r", "code": CODE, "params": {"k": 7}, "name": "p"})
        self.assertEqual((answer["ok"], answer["needs"]["panel"], answer["params"]), (True, "sp500", {"k": 7}))
        self.assertEqual((len(answer["sha"]), len(answer["run_sha"])), (64, 64))
        self.assertEqual(set(self.state["runners"]), {"p@1:r"})
        needs = self.ask("needs", {"code": CODE, "params": {}, "name": "p"})
        self.assertEqual(needs["needs"], {"panel": "sp500", "history": 20, "max_names": 10, "rebalance": "weekly",
                                          "weekday": 0, "max_hold_sessions": 60})
        self.assertEqual(set(self.state["runners"]), {"p@1:r"}, "learning NEEDS keeps nothing")
        self.assertNotEqual(needs["run_sha"], answer["run_sha"], "PARAMS are part of a run's sha")
        self.assertEqual(self.ask("drop", {"key": "p@1:r"}), {"ok": True})
        self.assertEqual(self.state["runners"], {})
        refused = self.ask("load", {"key": "x", "code": "refuse me", "params": {}, "name": "x"})
        self.assertEqual((refused["ok"], refused["refused"]), (False, True))
        self.assertEqual(self.state["runners"], {})

    def test_a_called_decide_plans_the_programs_target_by_the_keep_rule(self):
        self.ask("load", {"key": "a", "code": CODE, "params": {}, "name": "a"})
        t = 40
        ids = sorted(int(i) for i in self.bars.ids)
        held = [{"lid": 4, "col": fx.col_of(self.bars, ids[0]), "qty": 2.0, "value": 180.0, "entry_value": 200.0,
                 "held_sessions": 3, "at": "open", "tag": ""},
                {"lid": 9, "col": fx.col_of(self.bars, ids[20]), "qty": 1.0, "value": 210.0, "entry_value": 200.0,
                 "held_sessions": 8, "at": "close", "tag": ""}]
        inputs = self.inputs(t, held, budget=557.25)
        answer = self.ask("decide", {"jobs": [{"key": "a", "inputs": inputs, "called": True}]})
        row = answer["results"]["a"]
        derived = ctx.derive(inputs)
        wanted = sorted(int(i) for i in ctx.build(inputs).ids)[:5]
        self.assertEqual((row["hold"], row["failed"], row["called"], row["standing"], row["at"]),
                         (False, False, True, False, "open"))
        self.assertEqual(row["target"], {str(i): 0.2 for i in wanted}, "a target's keys come back as strings")
        self.assertEqual({int(k): v for k, v in row["target"].items()}, {i: 0.2 for i in wanted})
        buys = [o for o in row["orders"] if "buy_id" in o]
        self.assertEqual(row["orders"][0], {"sell": 9, "at": "open"})
        self.assertEqual([o["buy_id"] for o in buys], [i for i in wanted if i != ids[0]], "the held name is kept")
        self.assertTrue(all(o["usd"] == 111.45 for o in buys), "w x the sleeve's size, floored to the cent")
        self.assertEqual(row["ctx_sha"], hashlib.sha256(ctx.ctx_bytes(ctx.build(inputs))).hexdigest())
        self.assertEqual(row["ineligible"], ctx.ineligible(inputs, derived))
        self.assertEqual(row["stats"]["calls"], 1)

    def test_every_job_called_or_not_answers_the_ineligible_lots(self):
        self.ask("load", {"key": "a", "code": CODE, "params": {}, "name": "a"})
        t = 40
        out = fx.col_of(self.bars, int(self.bars.ids[3]))
        elig0 = self.bars.elig0.copy()
        elig0[t, out] = False
        self.bars = fx.changed(self.bars, elig0=elig0)
        held = [{"lid": 1, "col": out, "qty": 1.0, "value": 200.0, "entry_value": 200.0, "held_sessions": 2,
                 "at": "open", "tag": ""},
                {"lid": 2, "col": fx.col_of(self.bars, int(self.bars.ids[4])), "qty": 1.0, "value": 200.0,
                 "entry_value": 200.0, "held_sessions": 2, "at": "open", "tag": ""}]
        for called in (True, False):
            answer = self.ask("decide", {"jobs": [{"key": "a", "inputs": self.inputs(t, held), "called": called}]})
            self.assertEqual(answer["results"]["a"]["ineligible"], [1], called)

    def test_a_hold_day_runs_no_program_code_and_plans_the_standing_targets_buys(self):
        self.ask("load", {"key": "a", "code": "def decide(ctx):\n    raise SystemError('never called')\n",
                          "params": {}, "name": "a"})
        t = 41
        ids = sorted(int(i) for i in self.bars.ids)
        held = [{"lid": 1, "col": fx.col_of(self.bars, ids[0]), "qty": 1.0, "value": 200.0, "entry_value": 200.0,
                 "held_sessions": 2, "at": "open", "tag": ""}]
        gone = fx.col_of(self.bars, ids[3])
        elig0 = self.bars.elig0.copy()
        elig0[t, gone] = False                               # one standing id is not eligible at this close
        self.bars = fx.changed(self.bars, elig0=elig0)
        standing = {"target": {str(i): 0.2 for i in ids[:5]}, "at": "close", "exited": [ids[1]], "pending": [ids[2]]}
        job = {"key": "a", "inputs": self.inputs(t, held), "called": False, "standing": standing}
        row = self.ask("decide", {"jobs": [job]})["results"]["a"]
        # ids[0] is held, ids[1] was a House exit, ids[2] has a buy working, ids[3] is not in U today
        self.assertEqual(row["orders"], [{"buy_id": ids[4], "usd": 200.0, "at": "close"}])
        self.assertEqual((row["hold"], row["target"], row["at"], row["standing"], row["failed"], row["ctx_sha"],
                          row["called"]), (True, None, "close", True, False, None, False))
        self.assertEqual(row["stats"]["calls"], 0, "no program code ran")
        # with no standing target a hold day plans nothing; and it needs no loaded runner
        quiet = self.ask("decide", {"jobs": [{"key": "nobody", "inputs": self.inputs(t, held), "called": False}]})
        self.assertEqual((quiet["results"]["nobody"]["orders"], quiet["results"]["nobody"]["failed"],
                          quiet["results"]["nobody"]["stats"]), ([], False, None))

    def test_a_refused_target_a_hold_and_a_malformed_answer_plan_nothing(self):
        cases = {
            "cap": "def decide(ctx):\n    ids = sorted(int(i) for i in ctx.ids)\n"
                   "    return {'target': {i: 0.05 for i in ids[:13]}, 'at': 'open'}\n",
            "hold": "def decide(ctx):\n    return {'hold': True}\n",
            "none": "def decide(ctx):\n    return None\n",
            "bad": "def decide(ctx):\n    return {'target': {int(ctx.ids[0]): 0.9}, 'at': 'open'}\n",
        }
        needs = "NEEDS = {'panel': 'sp500', 'history': 20, 'max_names': 20, 'rebalance': 'weekly'}\nPARAMS = {}\n"
        for key, body in cases.items():
            self.ask("load", {"key": key, "code": needs + body, "params": {}, "name": key})
        self.needs = program.Needs("sp500", 20, 20, "weekly", 0, 60)
        jobs = [{"key": key, "inputs": self.inputs(40), "called": True} for key in cases]
        answer = self.ask("decide", {"jobs": jobs})["results"]
        for key in cases:
            row = answer[key]
            self.assertEqual((row["hold"], row["target"], row["orders"], row["failed"]), (True, None, [], False), key)
        self.assertTrue(engine.refused_whole(answer["cap"]["rejects"]))
        self.assertEqual(answer["bad"]["stats"]["errors"], 1, "a malformed answer is an error, never a failed decide")

    def test_a_failed_decide_a_missing_runner_and_unreadable_inputs(self):
        self.ask("load", {"key": "boom", "code": "def decide(ctx):\n    raise RuntimeError('no')\n", "params": {},
                          "name": "boom"})
        self.ask("load", {"key": "fine", "code": CODE, "params": {}, "name": "fine"})
        jobs = [{"key": "boom", "inputs": self.inputs(40), "called": True},
                {"key": "ghost", "inputs": self.inputs(40), "called": True},
                {"key": "fine", "inputs": "not inputs", "called": True},
                {"key": "fine2", "inputs": self.inputs(40), "called": True}]
        self.state["runners"]["fine2"] = self.state["runners"]["fine"]
        answer = self.ask("decide", {"jobs": jobs})["results"]
        self.assertEqual((answer["boom"]["failed"], answer["boom"]["hold"], answer["boom"]["orders"]),
                         (True, True, []))
        self.assertIn("RuntimeError", answer["boom"]["why"])
        self.assertEqual((answer["ghost"]["missing"], answer["ghost"]["failed"], answer["ghost"]["stats"]),
                         (True, True, None))
        self.assertTrue(answer["fine"]["failed"])
        self.assertTrue(answer["fine"]["error"].startswith("ctx: "))
        self.assertEqual((answer["fine2"]["failed"], answer["fine2"]["hold"]), (False, False),
                         "one job's inputs never cost the batch")
        # a held lot whose column is no member column of the decision: the parent's fault, on a hold day too
        stray = [{"lid": 1, "col": 3, "qty": 1.0, "value": 200.0, "entry_value": 200.0, "held_sessions": 2,
                  "at": "open", "tag": ""}]
        for called in (True, False):
            row = self.ask("decide", {"jobs": [{"key": "fine", "inputs": self.inputs(40, stray), "called": called,
                                               "standing": {"target": {"1": 0.2}, "at": "open"}}]})["results"]["fine"]
            self.assertEqual((row["failed"], row["orders"]), (True, []), called)
            self.assertIn("no member column", row["error"])

    def test_run_answers_the_whole_record_and_raises_its_niceness_once(self):
        seen = []
        with mock.patch.object(child.os, "nice", lambda value: seen.append(value) or 0):
            for _ in range(2):
                answer = self.ask("run", {"code": CODE, "params": {}, "name": "p", "bars": self.bars, "k": 1.0,
                                          "capital": None, "placebos": 8, "seed": 5, "calls": True, "style": False,
                                          "nice": 19})
        self.assertEqual(seen, [0, 19], "read once, raised once a child")
        result = answer["result"]
        self.assertEqual((answer["ok"], result["status"], result["placebo"]["seed"]), (True, "ok", 5))
        self.assertTrue(result["calls"])
        self.assertEqual(self.state["runners"], {}, "a run keeps no runner")
        with mock.patch.object(child.os, "nice", lambda value: seen.append("never")):
            self.ask("run", {"code": CODE, "params": {}, "name": "p", "bars": self.bars, "nice": None})
        self.assertNotIn("never", seen)
        refused = self.ask("run", {"code": "refuse me", "params": {}, "name": "p", "bars": self.bars})
        self.assertEqual((refused["ok"], refused["refused"]), (False, True))


class TheLiveChildPlansTheGymsOrders(fx.EngineCase):
    """I6 at this package's level: the child's "decide" on a Gym decision's inputs reads the Gym's ctx and plans the
    Gym's orders (`plan_orders` is one function), on a decision day and on a standing-target day alike."""

    def test_every_called_decision_and_every_standing_day_of_a_run(self):
        whole = fx.panel()
        bars = fx.no_bar(whole, fx.col_of(whole, int(sorted(whole.ids)[1])), (whole.first,))   # none at the first fill
        result, log = self.run_log(fx.Core.load_program(CODE, name="p"), bars, calls=True)
        state: dict[str, Any] = {}
        child.handle("load", {"key": "p", "code": CODE, "params": {}, "name": "p"}, state)
        needs = program.Needs(**result["needs"])
        called = [p for p in result["picks"] if p["called"]]
        self.assertGreaterEqual(len(called), 5)
        for call, pick in zip(result["calls"], called):
            book = {k: v for k, v in call.items() if k != "t"}
            inputs = ctx.inputs_from_panel(bars, call["t"], needs=needs, params=result["params"], **book)
            row = child.handle("decide", {"jobs": [{"key": "p", "inputs": inputs, "called": True}]},
                               state)["results"]["p"]
            self.assertEqual(row["ctx_sha"], pick["ctx_sha"])
            self.assertEqual(sorted([o["buy_id"], o["usd"]] for o in row["orders"] if "buy_id" in o),
                             sorted(pick["buys"]))
            self.assertEqual([o["sell"] for o in row["orders"] if "sell" in o], [s[0] for s in pick["sells"]])
            self.assertEqual(sorted(row["target"].items()), sorted((s, w) for s, w in pick["targets"]))
        # the standing-target day: the buy the first session could not make, planned again by the same function
        standing = [p for p in result["picks"] if not p["called"]]
        self.assertEqual(len(standing), 1)
        t = fx.day_index(bars, standing[0]["decided"])
        positions = [{"lid": row["lid"], "col": row["col"], "qty": 1.0, "value": 200.0, "entry_value": 200.0,
                      "held_sessions": t - row["entry"], "at": "open", "tag": ""}
                     for row in log.lots if row["entry"] <= t and (row["exit"] is None or row["exit"] > t)]
        inputs = ctx.inputs_from_panel(bars, t, needs=needs, positions=positions, cash=200.0, equity=1000.0,
                                       budget=1000.0, params=result["params"])
        job = {"key": "p", "inputs": inputs, "called": False,
               "standing": {"target": dict(standing[0]["targets"]), "at": standing[0]["at"], "exited": []}}
        row = child.handle("decide", {"jobs": [job]}, state)["results"]["p"]
        self.assertEqual([[o["buy_id"], o["usd"]] for o in row["orders"]], standing[0]["buys"])


# ================================================================================================ the isolated runs
class TheIsolatedRuns(RunnerCase):
    def test_needs_come_through_the_child_and_are_re_parsed(self):
        self.assertEqual(self.iso.needs(CODE, None, name="p")["rebalance"], "weekly")
        with self.assertRaises(runner.ProgramRefused):
            self.iso.needs("refuse me", None, name="p")
        with mock.patch.object(program, "parse_needs", side_effect=program.NeedsRefused("no")):
            with self.assertRaises(runner.RunFailed) as caught:
                self.iso.needs(CODE, None, name="p")
        self.assertIn("do not parse", str(caught.exception))

    def test_a_train_run_one_span_its_run_key_and_its_slice(self):
        start, end = self.train_days[10], self.train_days[70]
        run = self.iso.train(CODE, {"k": 5}, name="p", start=start, end=end)
        self.assertIsInstance(run, runner.Run)
        result, piece = run.result, run.slice
        self.assertEqual((result["status"], result["window"], result["half"]), ("ok", "train", None))
        self.assertEqual((result["start"], result["end"]), (start.isoformat(), end.isoformat()))
        asked = FakeStore.asked[-1]
        self.assertEqual(asked["run_key"], f"{result['run_sha']}|train|{start.isoformat()}")
        self.assertEqual(piece.run_key, asked["run_key"])
        self.assertEqual((asked["start"], asked["end"], asked["half"], asked["gate"]), (start, end, None, None))
        self.assertNotIn("placebo", result)
        self.assertNotIn("calls", result)
        # a result holds the slice's ids, and no aid of the parent's slice
        ids = {int(i) for i in piece.bars.ids}
        self.assertTrue(all(lot["id"] in ids for lot in result["lots"]))
        # another span is another run key, so other ids
        later = self.iso.train(CODE, {"k": 5}, name="p", start=self.train_days[20], end=end)
        self.assertNotEqual(later.slice.run_key, piece.run_key)
        self.assertFalse(ids & {int(i) for i in later.slice.bars.ids})

    def test_a_half_run_the_bars_placebos_the_calls_and_the_style_block(self):
        start, end = self.train_days[0], self.train_days[80]
        block = {"lots": 5, "n": {}, "weight": {}, "sum": {}}
        with mock.patch.object(fx.xs_style, "block", lambda bars, log: block):
            run = self.iso.train(CODE, None, name="p", start=start, end=end, k=1.5, half=1, placebos=20,
                                 calls=True, style=True)
        result = run.result
        self.assertEqual((result["half"], result["k"], FakeStore.asked[-1]["half"]), (1, 1.5, 1))
        self.assertEqual(result["style"], block)
        self.assertEqual(result["placebo"]["n"], 20)
        self.assertEqual(result["placebo"]["seed"], placebo.train_seed(result["run_sha"],
                                                                      f"train|{start.isoformat()}"))
        other = self.iso.train(CODE, None, name="p", start=self.train_days[5], end=end, placebos=20)
        self.assertNotEqual(other.result["placebo"]["seed"], result["placebo"]["seed"],
                            "each span draws its own stream")
        self.assertTrue(result["calls"])
        full = self.iso.train(CODE, None, name="p", start=start, end=end, k=1.5)
        self.assertNotEqual(full.result["universe"], result["universe"])
        self.assertEqual(full.slice.run_key, run.slice.run_key, "a half reads the full run's ids")

    def test_validation_and_the_segments(self):
        run = self.iso.validation(CODE, None, name="p", k=1.5)
        self.assertEqual((run.result["window"], run.result["k"], FakeStore.asked[-1]["window"]),
                         ("validation", 1.5, "validation"))
        first = FakeStore(self.tmp).sessions("validation")[0]
        self.assertEqual(run.slice.run_key, f"{run.result['run_sha']}|validation|{first.isoformat()}")
        spans = ((self.train_days[0], self.train_days[40]), (self.train_days[50], self.train_days[100]))
        with mock.patch.object(config, "TRAIN_SEGMENTS", spans):
            runs = self.iso.segments(CODE, None, name="p")
        self.assertEqual([(r.result["start"], r.result["end"], r.result["k"]) for r in runs],
                         [(a.isoformat(), b.isoformat(), 1.0) for a, b in spans])
        self.assertNotEqual(runs[0].slice.run_key, runs[1].slice.run_key)

    def test_the_looks_run_starts_at_validations_first_session_and_reads_v_and_h(self):
        with self.assertRaises(StoreRefused):
            self.iso.look(CODE, None, name="p", gate=None, placebos=30, seed=1)
        with self.assertRaises(StoreRefused):
            self.iso.look(CODE, None, name="p", gate=object(), placebos=30, seed=1)
        with self.assertRaises(ValueError):
            self.iso.look(CODE, None, name="p", gate=self.gate, placebos=0, seed=1)
        self.assertEqual(FakeStore.asked, [], "nothing is sliced for a look that is refused")
        seed = placebo.look_seed("a" * 64, "b" * 64)
        run = self.iso.look(CODE, None, name="p", gate=self.gate, placebos=30, seed=seed)
        result = run.result
        self.assertIs(FakeStore.asked[-1]["gate"], self.gate)
        self.assertEqual((result["window"], result["placebo"]["n"], result["placebo"]["seed"]), ("look", 30, seed))
        self.assertEqual(set(result["placebo"]["spans"]), {"V", "H"})
        days = results.column(result, "day")
        validation = [d for d in days if d <= e1.WINDOWS["validation"][1].isoformat()]
        holdout = [d for d in days if d >= e1.LOOK_FIRST.isoformat()]
        self.assertEqual(result["placebo"]["spans"]["V"]["days"], len(validation))
        self.assertEqual(result["placebo"]["spans"]["H"]["days"], len(holdout))
        self.assertEqual(result["start"], days[0])
        self.assertLess(days[0], "2026", "the run starts flat in Validation")
        # a lot opened in Validation is still held in the holdout: one run, never two
        self.assertTrue(any(lot["entry_day"] < "2026" and (lot["exit_day"] or "9999") >= "2026-01-02"
                            for lot in result["lots"]))

    def test_the_forward_days_under_the_instances_run_key(self):
        with self.assertRaises(StoreRefused):
            self.iso.forward(CODE, None, name="p", gate=None, start=dt.date(2026, 10, 12))
        days = FakeStore(self.tmp, gate=self.gate).sessions("forward")
        run = self.iso.forward(CODE, None, name="p", gate=self.gate, start=days[10])
        self.assertEqual(run.slice.run_key, f"{run.result['run_sha']}|forward|{days[10].isoformat()}")
        self.assertEqual(run.result["start"], days[10].isoformat())
        twin = self.iso.forward(CODE, None, name="p", gate=self.gate, start=days[10], run_key="fam@3:r",
                                aids=[101, 102])
        self.assertEqual((twin.slice.run_key, FakeStore.asked[-1]["aids"]), ("fam@3:r", [101, 102]))
        self.assertNotEqual(twin.slice.bars.dither_key, run.slice.bars.dither_key)
        self.assertNotIn("placebo", run.result)
        ranked = self.iso.forward(CODE, None, name="p", gate=self.gate, start=days[10], placebos=12, seed=4)
        self.assertEqual((ranked.result["placebo"]["n"], ranked.result["placebo"]["seed"],
                          list(ranked.result["placebo"]["spans"])), (12, 4, ["run"]))

    def test_a_run_goes_through_the_decider_as_one_run_of_the_panel_kind(self):
        seen = []
        real = self.decider.kind

        def kind(name: str, op: str, payload: Any, *, budget_seconds: Any = None) -> Any:
            seen.append((name, op, sorted(payload), budget_seconds))
            return real(name, op, payload, budget_seconds=budget_seconds)

        self.decider.kind = kind
        iso = runner.Isolated(self.decider, self.tmp, budget_seconds=123.0, nice=None)
        iso.train(CODE, None, name="p", start=self.train_days[0], end=self.train_days[40])
        self.assertEqual(seen, [("panel", "needs", ["code", "name", "params"], runner.NEEDS_BUDGET_SECONDS),
                                ("panel", "run", ["bars", "calls", "capital", "code", "k", "name", "nice", "params",
                                                  "placebos", "seed", "style"], 123.0)])
        self.assertEqual((runner.KIND, runner.RUN_BUDGET_SECONDS, runner.NICE), ("panel", 600.0, 19))
        self.assertEqual(runner.Isolated(self.decider, self.tmp).nice, 19)

    def test_what_fails_and_what_is_lost(self):
        start, end = self.train_days[0], self.train_days[40]

        def failing(words: str) -> Any:
            real = self.decider.kind

            def kind(name: str, op: str, payload: Any, *, budget_seconds: Any = None) -> Any:
                if op == "run":
                    raise D.DeciderError(words)
                return real(name, op, payload, budget_seconds=budget_seconds)
            return kind

        for words in runner.SENT_NOT_ANSWERED:
            with mock.patch.object(self.decider, "kind", failing(words)):
                with self.assertRaises(runner.RunLost):
                    self.iso.train(CODE, None, name="p", start=start, end=end)
        with mock.patch.object(self.decider, "kind", failing("the decider's pipe broke")):
            with self.assertRaises(runner.RunFailed) as caught:
                self.iso.train(CODE, None, name="p", start=start, end=end)
        self.assertNotIsInstance(caught.exception, runner.RunLost)
        with self.assertRaises(runner.ProgramRefused):
            self.iso.train("refuse me", None, name="p", start=start, end=end)
        with mock.patch.object(engine, "run", side_effect=ZeroDivisionError("an engine bug")):
            with self.assertRaises(runner.RunFailed) as caught:
                self.iso.train(CODE, None, name="p", start=start, end=end)
        self.assertIn("ZeroDivisionError", str(caught.exception))
        with self.assertRaises(runner.RunFailed) as caught:
            self.iso.train(CODE, None, name="p", start=dt.date(2040, 1, 1), end=dt.date(2040, 2, 1))
        self.assertIn("no session", str(caught.exception))
        for answer in ("text", {"ok": True}, {"ok": False, "error": "busy"}):
            with mock.patch.object(self.decider, "kind", lambda *a, answer=answer, **k: answer):
                with self.assertRaises(runner.RunFailed):
                    self.iso.train(CODE, None, name="p", start=start, end=end)


class TheRestartChecksStream(RunnerCase):
    def setUp(self):
        super().setUp()
        self.run = self.iso.train(ROTATE, None, name="p", start=self.train_days[0], end=self.train_days[90],
                                  k=1.5, calls=True)

    def test_each_called_decisions_inputs_rebuilt_from_the_runs_own_bars(self):
        stream = list(runner.state_stream(self.run))
        called = [p for p in self.run.result["picks"] if p["called"]]
        self.assertEqual(len(stream), len(called))
        self.assertGreaterEqual(len(stream), 10)
        for inputs, pick in zip(stream, called):
            self.assertIsInstance(inputs, ctx.Inputs)
            self.assertEqual(hashlib.sha256(ctx.ctx_bytes(ctx.build(inputs))).hexdigest(), pick["ctx_sha"])
            self.assertEqual(from_ordinal(int(inputs.days[-1])).isoformat(), pick["decided"])
        self.assertTrue(any(inputs.positions for inputs in stream) and any(inputs.closed for inputs in stream))

    def test_two_instances_on_the_stream_one_restarted_differ_only_by_the_programs_own_memory(self):
        """The check package G builds on this stream: an instance loaded once and one loaded FRESH now and then
        decide on the same inputs; a program that keeps a counter in STATE answers differently after a restart."""
        self.decider.kind_load("panel", "A", {"code": ROTATE, "params": {}, "name": "p"})
        self.decider.kind_load("panel", "B", {"code": ROTATE, "params": {}, "name": "p"})
        matches = []
        for n, inputs in enumerate(runner.state_stream(self.run), start=1):
            jobs = [{"key": key, "inputs": inputs, "called": True} for key in ("A", "B")]
            answer = self.decider.kind("panel", "decide", {"jobs": jobs})["results"]
            matches.append(answer["A"]["target"] == answer["B"]["target"] and answer["A"]["at"] == answer["B"]["at"])
            self.assertEqual(answer["A"]["stats"]["calls"], n)
            if n in (3, 10):
                self.decider.kind_drop("panel", "B")
                self.decider.kind_load("panel", "B", {"code": ROTATE, "params": {}, "name": "p"})
        self.assertTrue(all(matches[:3]))
        self.assertFalse(all(matches), "a restart moved the instance that keeps a counter")
        # the uninterrupted instance replays the run's own targets: the stream is the run's
        self.decider.kind_load("panel", "C", {"code": ROTATE, "params": {}, "name": "p"})
        called = [p for p in self.run.result["picks"] if p["called"]]
        for inputs, pick in zip(runner.state_stream(self.run), called):
            row = self.decider.kind("panel", "decide", {"jobs": [{"key": "C", "inputs": inputs, "called": True}]})
            target = row["results"]["C"]["target"]
            self.assertEqual(sorted((int(s), w) for s, w in target.items()), sorted(map(tuple, pick["targets"])))

    def test_a_stream_that_is_not_the_runs_is_the_houses_failure(self):
        with self.assertRaises(runner.RunFailed):
            list(runner.state_stream(runner.Run({**self.run.result, "calls": None}, self.run.slice)))
        tampered = json.loads(json.dumps(self.run.result))
        tampered["calls"][2]["cash"] += 1.0
        with self.assertRaises(runner.RunFailed) as caught:
            list(runner.state_stream(runner.Run(tampered, self.run.slice)))
        self.assertIn("never the program's", str(caught.exception))
        short = json.loads(json.dumps(self.run.result))
        short["calls"].pop()
        with self.assertRaises(runner.RunFailed):
            list(runner.state_stream(runner.Run(short, self.run.slice)))
        moved = json.loads(json.dumps(self.run.result))
        moved["calls"][1]["t"] += 1
        with self.assertRaises(runner.RunFailed):
            list(runner.state_stream(runner.Run(moved, self.run.slice)))
        broken = json.loads(json.dumps(self.run.result))
        broken["calls"][0]["positions"] = "none"
        with self.assertRaises(runner.RunFailed):
            list(runner.state_stream(runner.Run(broken, self.run.slice)))


# ============================================================================================ over the real core
REAL = '''
NEEDS = {"panel": "sp500", "history": 60, "max_names": 8, "rebalance": "weekly", "weekday": 0,
         "max_hold_sessions": 40}
PARAMS = {"k": 6}
STATE = {"calls": 0}


def decide(ctx):
    STATE["calls"] += 1
    ranked = []
    for i in range(ctx.n):
        week = 0.0
        for j in range(1, 6):
            value = float(ctx.ret[i][-j])
            if value == value:
                week += value
        ranked.append((week, int(ctx.ids[i])))
    ranked.sort()
    picks = [slot for _, slot in ranked[:PARAMS["k"]]]
    if len(picks) < 5:
        return {"hold": True}
    return {"target": {slot: 1.0 / len(picks) for slot in picks}, "at": "close" if STATE["calls"] % 3 == 0 else "open"}
'''


@unittest.skipUnless(core_built(), "package C (the panel store, ctx, program and synthetic panels) is a Step 0 stub")
class WithTheRealCore(unittest.TestCase):
    """The same entry points over package C's own functions and a synthetic panel store: no double anywhere."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = synth.synthetic_panel(Path(cls.tmp) / "equity-daily", n_assets=40, seed=11, churn=0.10, gate=True,
                                         vanish=((104, dt.date(2023, 3, 10)),))
        cls.decider = D.InlineDecider()
        cls.iso = runner.Isolated(cls.decider, cls.root, nice=None)
        cls.train = cls.iso.train(REAL, None, name="reversal", start=dt.date(2022, 1, 3), end=dt.date(2023, 6, 30),
                                  placebos=30, calls=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_a_train_run_trades_and_its_record_is_whole(self):
        result = self.train.result
        self.assertEqual((result["status"], result["window"], result["panel"], result["rung"]),
                         ("ok", "train", "sp500", "R0"))
        summary = result["summary"]
        self.assertGreater(summary["lots"], 50)
        self.assertGreater(summary["rebalances"], 40)
        self.assertGreater(summary["invested_days"], 300)
        x, r, bench = (np.array(results.column(result, name)) for name in ("x", "r", "bench"))
        self.assertTrue(np.array_equal(x, r - bench))
        self.assertTrue(np.isfinite(x).all() and float(np.abs(x).sum()) > 0)
        self.assertEqual(summary["t_x"], results.t_stat(x))
        ids = {int(i) for i in self.train.slice.bars.ids}
        self.assertTrue(all(lot["id"] in ids and lot["weight"] <= config.MAX_WEIGHT + 1e-9 for lot in result["lots"]))
        self.assertTrue(all(lot["decided_day"] < lot["entry_day"] for lot in result["lots"]))
        days = results.column(result, "day")
        self.assertTrue(all(lot["entry_day"] < days[-1] for lot in result["lots"]), "no lot at the last session")
        self.assertEqual(result["placebo"]["n"], 30)
        self.assertEqual(len(result["placebo"]["spans"]["run"]["t"]), 30)
        self.assertGreater(result["summary"]["dilution"], 0.5)
        json.dumps(result, allow_nan=False)

    def test_the_same_run_twice_is_the_same_record(self):
        again = self.iso.train(REAL, None, name="reversal", start=dt.date(2022, 1, 3), end=dt.date(2023, 6, 30),
                               placebos=30, calls=True)
        self.assertEqual(again.result["result_sha"], self.train.result["result_sha"])
        self.assertEqual(again.result["picks_sha"], self.train.result["picks_sha"])

    def test_the_restart_checks_stream_rebuilds_every_call(self):
        stream = list(runner.state_stream(self.train))
        self.assertEqual(len(stream), self.train.result["summary"]["calls"])
        self.assertGreater(len(stream), 40)

    def test_a_half_run_and_the_stress_twin(self):
        half = self.iso.train(REAL, None, name="reversal", start=dt.date(2022, 1, 3), end=dt.date(2022, 12, 30),
                              k=1.5, half=0)
        self.assertEqual((half.result["half"], half.result["k"], half.result["status"]), (0, 1.5, "ok"))
        self.assertGreater(half.result["summary"]["lots"], 10)

    def test_validation_and_the_one_look(self):
        validation = self.iso.validation(REAL, None, name="reversal")
        self.assertEqual((validation.result["status"], validation.result["summary"]["days"]), ("ok", 250))
        with self.assertRaises(StoreRefused):
            self.iso.look(REAL, None, name="reversal", gate=None, placebos=20, seed=3)
        gate = mint_equity_gate_capability(self.root, "the one look")
        look = self.iso.look(REAL, None, name="reversal", gate=gate, placebos=20, seed=3)
        spans = look.result["placebo"]["spans"]
        self.assertEqual((spans["V"]["days"], spans["H"]["days"]), (250, 194))
        self.assertEqual(look.result["summary"]["days"], 444)
        # its Validation sessions repeat the Validation run's (the same run key would be needed for the same ids:
        # the two runs are salted apart, so only what no id touches is compared)
        self.assertEqual(results.column(look.result, "day")[:250], results.column(validation.result, "day"))

    def test_the_floors_segments(self):
        runs = self.iso.segments(REAL, None, name="reversal")
        self.assertEqual([r.result["summary"]["days"] for r in runs], [754, 753])
        self.assertTrue(all(r.result["status"] == "ok" for r in runs))

    def test_the_live_child_reads_the_gyms_ctx_and_plans_the_gyms_orders(self):
        result = self.train.result
        self.decider.kind_load("panel", "live", {"code": REAL, "params": {}, "name": "reversal"})
        called = [p for p in result["picks"] if p["called"]]
        for inputs, pick in list(zip(runner.state_stream(self.train), called))[:12]:
            row = self.decider.kind("panel", "decide", {"jobs": [{"key": "live", "inputs": inputs, "called": True}]})
            row = row["results"]["live"]
            self.assertEqual(row["ctx_sha"], pick["ctx_sha"])
            self.assertEqual(sorted([o["buy_id"], o["usd"]] for o in row["orders"] if "buy_id" in o),
                             sorted(pick["buys"]))
            self.assertEqual([o["sell"] for o in row["orders"] if "sell" in o], [s[0] for s in pick["sells"]])
        self.decider.kind_drop("panel", "live")


@unittest.skipUnless(core_built(), "package C (the panel store, ctx, program and synthetic panels) is a Step 0 stub")
@unittest.skipUnless(sys.platform.startswith("linux"), "the child's runtime copy")
class TheChildsRuntime(unittest.TestCase):
    def test_a_panel_run_from_a_copy_of_the_childs_runtime_files_alone(self):
        """A root House's child runs from a copy of `runtime_files()` alone, with an empty environment and -E -s:
        from such a copy the panel kind loads a program, answers its NEEDS and replays it over a synthetic slice."""
        files = D.runtime_files()
        repo = D.REPO
        script = ("import tempfile, datetime\n"
                  "from league.equity import kinds\n"
                  "panel = kinds.module_for('panel')\n"
                  "assert panel.OPS == ('load', 'drop', 'decide', 'needs', 'run'), panel.OPS\n"
                  "from league.xs import store, synth\n"
                  "from league.xs.program import parse_needs\n"
                  f"code = {REAL!r}\n"
                  "state = {}\n"
                  "needs = panel.handle('needs', {'code': code, 'params': {}, 'name': 'p'}, state)\n"
                  "assert needs['ok'] and needs['needs']['panel'] == 'sp500', needs\n"
                  "root = synth.synthetic_panel(tempfile.mkdtemp() + '/equity-daily', n_assets=30, seed=3)\n"
                  "piece = store.PanelStore(root).train(datetime.date(2022, 1, 3), datetime.date(2022, 6, 30),\n"
                  "                                     history=60, run_key='runtime')\n"
                  "answer = panel.handle('run', {'code': code, 'params': {}, 'name': 'p', 'bars': piece.bars,\n"
                  "                              'k': 1.0, 'capital': None, 'placebos': 5, 'nice': None}, state)\n"
                  "assert answer['ok'] and answer['result']['status'] == 'ok', answer\n"
                  "assert answer['result']['lots'], 'the run traded'\n"
                  "print('ran')\n")
        with tempfile.TemporaryDirectory() as tmp:
            for name in files:
                (Path(tmp) / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / name, Path(tmp) / name)
            done = subprocess.run([sys.executable, "-E", "-s", "-c", script], cwd=tmp, capture_output=True, text=True,
                                  timeout=300, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": tmp,
                                                    "OPENBLAS_NUM_THREADS": "1"})
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "ran"), done.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
