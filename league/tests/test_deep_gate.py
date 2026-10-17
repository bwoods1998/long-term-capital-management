"""THE SEAL AND THE LOOK (HISTORY-PLAN.md section 5.3, "Seal", and section 6; league/deep/gate.py, blocks.py,
report.py): `sealed/` is unreadable without the DeepGate; the capability cannot be forged or moved to another store;
a look returns booleans and the ledger keeps no figure (no researcher-visible result from a DVAL run); every
temporary store is removed, after a failure too; one look a version, three a cell, 150 in all; a look the House could
not finish is owed once; the canaries are matched, calendar-blind and judged on the deep key alone; the report is
counts only.

Synthetic deep and equity stores only (league/tests/deep_fakes.py), run in the in-process decider."""

from __future__ import annotations

import json
import os
import stat
import unittest
from pathlib import Path

from league.deep import blind, blocks, config, gate, report
from league.equity.program import load_program
from league.tests import deep_fakes as F

WORLDS = 1500


def numbers(value, path=""):
    """Every (path, value) of a JSON value that is a float (a figure)."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return []
    if isinstance(value, float):
        return [(path, value)]
    if isinstance(value, dict):
        return [hit for k, v in value.items() for hit in numbers(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [hit for i, v in enumerate(value) for hit in numbers(v, f"{path}[{i}]")]
    return [(path, value)]


class TheCapability(unittest.TestCase):
    def setUp(self):
        self.root = F.tmpdir(self)
        self.deep = F.deep_store(self.root / "equity-deep", ("SPY",))

    def test_it_cannot_be_constructed_and_is_minted_only_on_the_marked_store_for_a_named_reason(self):
        with self.assertRaises(TypeError):
            gate.DeepGateCapability()
        with self.assertRaises(blocks.DeepRefused):
            gate.mint_deep_gate_capability(self.root, "s3-look")
        with self.assertRaises(blocks.DeepRefused):
            gate.mint_deep_gate_capability(self.deep, "curiosity")
        self.assertEqual(gate.mint_deep_gate_capability(self.deep, "s3-look").reason, "s3-look")

    def test_sealed_is_unreadable_without_the_gate(self):
        open_store = blocks.DeepStore(self.deep)
        self.assertEqual(open_store.symbols("dval"), ["SPY"], "a name and a count are no market row")
        with self.assertRaises(blocks.DeepRefused):
            open_store.block("dval", "SPY")
        self.assertIn("days", open_store.block("traind", "SPY"))
        sealed = blocks.DeepStore(self.deep, gate=gate.mint_deep_gate_capability(self.deep, "s3-look"))
        self.assertIn("close", sealed.block("dval", "SPY"))
        other = F.deep_store(self.root / "other", ("SPY",))
        with self.assertRaises(blocks.DeepRefused):
            blocks.DeepStore(other, gate=gate.mint_deep_gate_capability(self.deep, "s3-look"))
        with self.assertRaises(blocks.DeepRefused):
            blocks.DeepStore(self.deep, gate="s3-look")

    def test_the_sealed_tree_is_owner_only_marked_and_checked_against_its_manifest(self):
        sealed_dir = self.deep / config.SEALED_DIR
        self.assertEqual(stat.S_IMODE(os.stat(sealed_dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.deep).st_mode), 0o700)
        self.assertTrue((sealed_dir / config.GATE_MARK).is_file())
        block = sealed_dir / "dval" / "SPY.npz"
        self.assertEqual(stat.S_IMODE(os.stat(block).st_mode), 0o600)
        cap = gate.mint_deep_gate_capability(self.deep, "s3-look")
        data = block.read_bytes()
        block.write_bytes(data[:-10] + b"0123456789")
        with self.assertRaises(blocks.DeepMissing):
            blocks.DeepStore(self.deep, gate=cap).block("dval", "SPY")
        block.write_bytes(data)
        (sealed_dir / config.GATE_MARK).unlink()
        with self.assertRaises(blocks.DeepRefused):
            blocks.DeepStore(self.deep, gate=cap).block("dval", "SPY")


class TheLook(unittest.TestCase):
    def setUp(self):
        self.root = F.tmpdir(self)
        self.deep = F.deep_store(self.root / "equity-deep", ("SPY", "QQQ", "XLRE"))
        F.equity_store(self.root / "equity-daily", ("SPY", "QQQ", "XLRE"))
        self.runs = F.InlineRuns(self.root / "equity-daily")
        self.ledger = gate.Ledger(self.deep)
        self.parent = self.root / "looks"
        self.parent.mkdir()

    def version(self, code=None, *, recall=False, cell="equity/momentum/index", fid="f1"):
        return gate.Version(fid=fid, n=1, code=code or F.blind_program(("SPY", "QQQ")), params={}, cell=cell,
                            strong_recall=recall)

    def look(self, v, **kw):
        return gate.look(self.deep, v, self.runs, ledger=self.ledger, identity="deepid", now="2026-10-25T23:00:00Z",
                         worlds=WORLDS, parent=self.parent, **kw)

    def test_one_look_returns_booleans_writes_its_verdict_and_leaves_no_store_behind(self):
        out = self.look(self.version(), reserve=True)
        self.assertEqual(out["status"], "looked")
        self.assertEqual(set(out), {"status", "passed", "deep", "recent"})
        self.assertTrue(all(isinstance(out[k], bool) for k in ("passed", "deep", "recent")))
        self.assertEqual(os.listdir(self.parent), [], "every temporary store is gone")
        stored = json.loads((self.deep / config.LEDGER).read_text())
        self.assertEqual(numbers(stored), [], "the ledger keeps no figure")
        self.assertEqual(stat.S_IMODE(os.stat(self.deep / config.LEDGER).st_mode), 0o600)
        row = stored["looks"][0]
        self.assertEqual((row["kind"], row["attempts"], row["identity"], row["receipt"]),
                         ("look", 1, "deepid", config.RECEIPT_SHA256[:12]))
        roots = {str(r) for kind, r in self.runs.calls if kind == "on_store"}
        self.assertFalse(any(r.startswith(str(self.deep)) for r in roots), "no run reads the deep store itself")
        self.assertEqual([k for k, _ in self.runs.calls].count("recent"), 1)
        self.assertEqual(self.look(self.version())["status"], "already", "one look a version")
        again = gate.Version(fid="f2", n=7, code=F.blind_program(("SPY", "QQQ")), params={}, cell="x",
                             strong_recall=False)
        self.assertEqual(self.look(again)["status"], "already", "the same program in another family is that version")

    def test_without_d2_the_recent_key_is_pending_and_is_read_once_when_d2_is_judged(self):
        v = self.version()
        out = self.look(v)
        self.assertEqual((out["status"], out["passed"], out["recent"]), ("looked", None, None))
        self.assertIsInstance(out["deep"], bool)
        self.assertNotIn("recent", [k for k, _ in self.runs.calls], "no R, V or H run is made before D2")
        self.assertEqual(len(self.ledger.pending()), 1)
        self.runs.calls.clear()
        done = gate.recent_look(self.deep, v, self.runs, ledger=self.ledger, worlds=WORLDS, parent=self.parent)
        self.assertEqual(done["status"], "looked")
        self.assertIsInstance(done["recent"], bool)
        self.assertEqual(done["deep"], out["deep"], "the deep key's verdict stands")
        roots = [str(r) for kind, r in self.runs.calls if kind == "on_store"]
        self.assertFalse(any("deep-A-" in r or "deep-B-" in r for r in roots), "DVAL is not read again")
        self.assertEqual([k for k, _ in self.runs.calls].count("recent"), 1)
        self.assertEqual(self.ledger.pending(), [])
        self.assertEqual(gate.recent_look(self.deep, v, self.runs, ledger=self.ledger, worlds=WORLDS)["status"], "none")
        self.assertEqual(os.listdir(self.parent), [])

    def test_refusals_spend_no_look_and_an_unmeasured_route_waits(self):
        weekday = F.blind_program(("SPY", "QQQ")).replace("    held = {p", "    if ctx.weekday == 1:\n        return out\n    held = {p")
        self.assertEqual(self.look(self.version(weekday))["why"], "not calendar-blind")
        self.assertEqual(self.look(self.version(F.blind_program(("SPY", "XLRE"))))["why"], "not ETF only (DVAL's 15)")
        self.assertEqual(self.look(self.version(recall=True))["status"], "refused")
        self.assertEqual(self.ledger.spent(), [])
        self.assertEqual(len(self.ledger.refused), 3)
        broken = self.look(self.version("NEEDS = {'symbols': ['SPY']}\nPARAMS = {}\n"))
        self.assertEqual(broken["status"], "refused")
        self.assertTrue(broken["why"].startswith("the program does not load"), broken["why"])
        self.assertEqual(len(self.ledger.refused), 4)
        waits = self.look(self.version(F.blind_program(("SPY", "QQQ"), look=12), recall=None))
        self.assertEqual(waits["status"], "waits")
        self.assertEqual((len(self.ledger.spent()), len(self.ledger.refused)), (0, 4), "a wait records nothing")

    def test_a_look_the_house_cannot_finish_is_owed_once_then_spent_and_failed(self):
        real = self.runs.on_store
        calls = {"dval": 0}

        def broken(root, code, params, start, end, k):
            if "deep-A-" in str(root) or "deep-B-" in str(root):
                calls["dval"] += 1
                raise RuntimeError("the child died")
            return real(root, code, params, start, end, k)

        self.runs.on_store = broken
        v = self.version()
        for attempt in (1, 2):
            with self.assertRaises(RuntimeError):
                self.look(v)
            self.assertEqual(self.ledger.row(v.key)["attempts"], attempt)
            self.assertIsNone(self.ledger.row(v.key)["verdict"])
            self.assertEqual(os.listdir(self.parent), [], "removed after the failure too")
        self.assertEqual(self.look(v)["status"], "failed")
        self.assertEqual(self.ledger.row(v.key)["verdict"], "failed")
        self.assertEqual(self.look(v)["status"], "already")

    def test_a_sealed_run_the_program_ended_is_spent_and_failed(self):
        real = self.runs.on_store

        def disqualified(root, code, params, start, end, k):
            run = real(root, code, params, start, end, k)
            if "deep-A-" in str(root) or "deep-B-" in str(root):
                return type(run)({**run.result, "status": "disqualified"}, run.bars)
            return run

        self.runs.on_store = disqualified
        out = self.look(self.version(), reserve=True)
        self.assertEqual((out["status"], out["passed"], out["deep"]), ("looked", False, False))
        self.assertEqual(self.ledger.row(self.version().key)["attempts"], 1, "spent once: not owed again")

    def test_the_budget_and_the_cell(self):
        for i in range(3):
            self.ledger.looks.append({"key": f"k{i}", "kind": "look", "cell": "equity/momentum/index",
                                      "verdict": {"passed": False, "deep": False, "recent": False}})
        self.assertEqual(self.look(self.version())["status"], "cell")
        self.assertEqual(self.look(self.version(cell="equity/reversal/index"), kind="look")["status"], "looked")
        self.ledger.looks += [{"key": f"b{i}", "kind": "look", "cell": f"c{i}", "verdict": None}
                              for i in range(config.LOOK_BUDGET)]
        out = self.look(self.version(F.blind_program(("SPY", "QQQ"), look=14), cell="other"))
        self.assertEqual(out["status"], "budget")

    def test_a_halted_s3_looks_at_nothing(self):
        for i in range(3):
            self.ledger.looks.append({"key": f"c{i}", "kind": "canary", "verdict": {"passed": True, "deep": True,
                                                                                    "recent": None}})
        self.assertTrue(self.ledger.halted())
        self.assertEqual(self.look(self.version())["status"], "halted")
        self.assertEqual(self.runs.calls, [])

    def test_the_canary_slot_is_the_receipts_one_in_each_block_of_ten(self):
        import numpy as np

        slots = [gate.canary_slot(b) for b in range(15)]
        self.assertEqual(slots, [int(np.random.default_rng([20261017, 3, 8, b]).integers(10)) for b in range(15)])
        ledger = gate.Ledger(F.tmpdir(self))
        canaries = []
        for i in range(60):
            due = ledger.canary_due()
            ledger.looks.append({"key": f"k{i}", "kind": "canary" if due else "look", "verdict": None})
            if due:
                canaries.append(i)
        blocks = [i // 10 for i in canaries]
        self.assertEqual(blocks, sorted(set(blocks)), "one canary a block")
        self.assertEqual(len(canaries), 6)
        for i in canaries:
            self.assertGreaterEqual(i % 10, slots[i // 10] if i >= 10 or slots[0] > 0 else 1)
        first = gate.Ledger(F.tmpdir(self))
        self.assertFalse(first.canary_due(), "never before a real look exists to mirror")

    def test_the_canary_is_matched_blind_and_judged_on_the_deep_key_alone(self):
        v = self.version()
        self.look(v)
        while not self.ledger.canary_due():
            self.ledger.looks.append({"key": f"p{len(self.ledger.looks)}", "kind": "look", "cell": "c", "verdict": None})
        canary = gate.canary_for(self.ledger, {v.key: v}, self.runs)
        self.assertIsNotNone(canary)
        load_program(canary.code, name="canary")
        self.assertEqual(blind.scan(canary.code), [])
        self.assertNotIn("ctx.bars", canary.code, "it never reads a price")
        needs = self.runs.needs(canary.code, {})
        self.assertEqual((list(needs["symbols"]), needs["history"]), (["SPY", "QQQ"], 40))
        self.runs.calls.clear()
        out = gate.look(self.deep, canary, self.runs, ledger=self.ledger, identity="deepid", now="t", kind="canary",
                        worlds=WORLDS, parent=self.parent)
        self.assertEqual(out["status"], "looked")
        self.assertIsNone(out["recent"])
        self.assertIsInstance(out["passed"], bool)
        self.assertNotIn("recent", [k for k, _ in self.runs.calls])
        self.assertEqual(self.ledger.canaries()[0]["kind"], "canary")

    def test_the_canary_plan_matches_turnover_holds_and_entries(self):
        rows = {"SPY": {"round_trips": 12.0, "hold": 10.0, "close": 0.5}, "QQQ": {"round_trips": 0.0, "hold": 5.0}}
        plan = gate.canary_plan(rows, seed=3, steps=20_000)
        spy = plan["SPY"]
        entries = sum(1 for a, b in zip("." + spy, spy) if a == "." and b != ".")
        self.assertAlmostEqual(entries / (20_000 / 252.0), 12.0, delta=2.0)
        self.assertAlmostEqual(sum(c != "." for c in spy) / 20_000, 12.0 * 10 / 252.0, delta=0.06)
        closes = sum(1 for a, b in zip("." + spy, spy) if a == "." and b == "c")
        self.assertAlmostEqual(closes / entries, 0.5, delta=0.12)
        self.assertEqual(set(plan["QQQ"]), {"."}, "a symbol the version never traded stays off")
        self.assertEqual(gate.canary_plan(rows, seed=3, steps=200), gate.canary_plan(rows, seed=3, steps=200))
        self.assertNotEqual(gate.canary_plan(rows, seed=4, steps=200), gate.canary_plan(rows, seed=3, steps=200))

    def test_the_canary_code_loads_and_holds_no_date_shaped_text(self):
        import re

        code = gate.canary_code(symbols=["SPY", "GLD"], history=5, seed=2025,
                                per_symbol={"SPY": {"round_trips": 30.0, "hold": 4.0, "close": 0.3, "share": 0.2025},
                                            "GLD": {"round_trips": 5.0, "hold": 20.0, "share": 0.9}})
        load_program(code, name="c")
        self.assertIsNone(re.search(r"(?<![0-9])20(?:19|2[0-9]|30)(?![0-9])", code))
        self.assertIn('"GLD": 0.5', code, "a weight is held to 0.01..0.5")

    def test_the_report_is_counts_only(self):
        self.look(self.version())
        out = report.summary(self.ledger, waiting=2, identity="deepidentity12345")
        self.assertEqual((out["eligible"], out["looked"], out["waiting"]), (3, 1, 2))
        self.assertEqual(sorted(path for path, _ in numbers(out)),
                         [".prediction.deep_zero_edge_passes", ".prediction.deep_zero_edge_rate",
                          ".prediction.zero_edge_passes", ".prediction.zero_edge_rate"],
                         "the receipt's synthetic rates and its predictions are the only figures")
        self.assertEqual((out["recent_pending"], out["passed"]), (1, 0))
        path = report.write(self.deep, out)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class TheSeeds(unittest.TestCase):
    def test_a_versions_floor_seed_is_its_swarm_sha_and_its_ledger_key_its_code_and_params(self):
        from league.swarm.store import code_sha

        code = F.blind_program(("SPY",))
        a = gate.Version(fid="f", n=1, code=code, params={}, cell="c", strong_recall=False)
        b = gate.Version(fid="g", n=2, code=code, params={"look": 3}, cell="c", strong_recall=False)
        self.assertEqual(a.tag, int(code_sha(code)[:8], 16))
        self.assertEqual(a.tag, b.tag)
        self.assertNotEqual(a.key, b.key, "other PARAMS: another version")


if __name__ == "__main__":
    unittest.main()
