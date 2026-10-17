"""THE SEAL AND THE LOOK (HISTORY-PLAN.md section 5.3, "Seal", and section 6; league/deep/gate.py, blocks.py,
report.py): `sealed/` is unreadable without the DeepGate; the capability cannot be forged or moved to another store;
a look returns booleans and the ledger keeps no figure (no researcher-visible result from a DVAL run); every
temporary store is removed, after a failure too; one look a version, three a cell, 150 in all; a sealed run sent and
not answered is owed once, an error of the House's spends nothing; the ledger fails closed; D2: both keys or neither,
and the reserve is run only inside a begun look, after the deep key; the canaries are matched, calendar-blind and
judged on the deep key alone; the report is counts only.

Synthetic deep and equity stores only (league/tests/deep_fakes.py), run in the in-process decider."""

from __future__ import annotations

import json
import os
import stat
import unittest
from pathlib import Path

from league.deep import blind, blocks, config, gate, report
from league.equity.program import load_program
from league.equity.runner import RunFailed, RunLost
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
        looks = blocks.looks_dir(self.deep)
        self.assertEqual(os.listdir(looks), [], "the DVAL segments' stores, inside the sealed tree, are gone too")
        stored = json.loads((self.deep / config.LEDGER).read_text())
        self.assertEqual(numbers(stored), [], "the ledger keeps no figure")
        self.assertEqual(stat.S_IMODE(os.stat(self.deep / config.LEDGER).st_mode), 0o600)
        row = stored["looks"][0]
        self.assertEqual((row["kind"], row["attempts"], row["identity"], row["receipt"]),
                         ("look", 1, "deepid", config.RECEIPT_SHA256[:12]))
        self.assertEqual((row["seated"], row["source"]), (False, "born"))
        self.assertIsInstance(row["level"], bool, "the level test's answer, report-only")
        roots = [Path(r) for kind, r in self.runs.calls if kind == "on_store"]
        for r in roots:
            self.assertTrue(r.is_relative_to(looks) or r.is_relative_to(self.parent), r)
            self.assertNotEqual(r, self.deep, "no run reads the deep store itself")
        dval = [r for r in roots if r.is_relative_to(looks) and r.relative_to(looks).parts[0].startswith(("deep-A-", "deep-B-"))]
        self.assertEqual(len(dval), 2, "each DVAL segment is written inside sealed/.looks/")
        self.assertEqual([k for k, _ in self.runs.calls].count("recent"), 1)
        self.assertEqual(self.look(self.version())["status"], "already", "one look a version")
        again = gate.Version(fid="f2", n=7, code=F.blind_program(("SPY", "QQQ")), params={}, cell="x",
                             strong_recall=False)
        self.assertEqual(self.look(again)["status"], "already", "the same program in another family is that version")

    def test_d2_both_keys_or_neither(self):
        v = self.version()
        out = self.look(v, reserve=False)
        self.assertEqual(out["status"], "waits", "elane.deep.reserve sealed: no look at all")
        self.assertEqual((self.runs.calls, self.ledger.spent(), self.ledger.refused), ([], [], {}),
                         "no run, no DVAL, no reserve, nothing spent")
        self.assertEqual(os.listdir(self.parent), [])
        done = self.look(v)
        self.assertEqual(done["status"], "looked", "D2 judged (the default): the look reads both keys")
        self.assertTrue(all(isinstance(done[k], bool) for k in ("passed", "deep", "recent")))
        self.assertEqual(done["passed"], done["deep"] and done["recent"], "pass = both keys")
        self.assertEqual([k for k, _ in self.runs.calls].count("recent"), 1)
        self.assertEqual(self.look(v)["status"], "already")

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
        self.runs.calls.clear()
        waits = self.look(self.version(F.blind_program(("SPY", "QQQ"), look=12), recall=None))
        self.assertEqual(waits["status"], "waits")
        self.assertEqual((len(self.ledger.spent()), len(self.ledger.refused)), (0, 4), "a wait records nothing")
        self.assertEqual([k for k, _ in self.runs.calls], [], "a wait is read before any run is made")
        self.assertEqual(os.listdir(self.parent), [])
        strong = self.look(self.version(F.blind_program(("SPY", "QQQ"), look=13), recall=True))
        self.assertEqual(strong["why"], "a strong-recall route on contam_probe's 2001-08 cells")
        self.assertEqual([k for k, _ in self.runs.calls], [], "so is a strong-recall route")
        nameless = gate.Version(fid="f9", n=1, code=F.blind_program(("SPY", "QQQ"), look=15), params={},
                                cell="equity/momentum/index", strong_recall=None, route_known=False)
        self.assertEqual(self.look(nameless)["why"], "no route is named: its 2001-08 recall cannot be read")
        self.assertEqual(len(self.ledger.spent()), 0)

    def broken_dval(self, error):
        real = self.runs.on_store
        calls = {"dval": 0}

        def broken(root, code, params, start, end, k):
            if "deep-A-" in str(root) or "deep-B-" in str(root):
                calls["dval"] += 1
                raise error
            return real(root, code, params, start, end, k)

        self.runs.on_store = broken
        return calls

    def test_an_error_of_the_houses_spends_no_look(self):
        calls = self.broken_dval(RunFailed("the decider child failed the run: BrokenPipeError"))
        v = self.version()
        for _ in range(3):
            with self.assertRaises(RunFailed):
                self.look(v)
            self.assertIsNone(self.ledger.row(v.key), "the attempt is withdrawn: no look spent")
            self.assertEqual(self.ledger.spent(), [])
            self.assertEqual(os.listdir(self.parent), [])
            self.assertEqual(os.listdir(blocks.looks_dir(self.deep)), [], "removed after the failure too")
        self.assertEqual(calls["dval"], 3)
        for error in (ValueError("no price"), RuntimeError("the DVAL run did not finish (no_data)")):
            self.broken_dval(error)
            with self.assertRaises(type(error)):
                self.look(v)
            self.assertIsNone(self.ledger.row(v.key))
        self.runs.on_store = F.InlineRuns(self.root / "equity-daily").on_store
        self.assertEqual(self.look(v)["status"], "looked", "the look is still the version's to take")

    def test_a_sealed_run_that_does_not_return_is_owed_once_then_spent_and_failed(self):
        self.broken_dval(RunLost("the decider did not answer in time"))
        v = self.version()
        out = self.look(v)
        self.assertEqual(out["status"], "lost")
        self.assertEqual((self.ledger.row(v.key)["attempts"], self.ledger.row(v.key)["verdict"]), (1, None))
        self.assertEqual(os.listdir(blocks.looks_dir(self.deep)), [])
        self.assertEqual(self.look(v)["status"], "failed", "the second time: spent and failed")
        self.assertEqual((self.ledger.row(v.key)["attempts"], self.ledger.row(v.key)["verdict"]), (2, "failed"))
        self.assertEqual(self.look(v)["status"], "already")

    def test_a_look_whose_process_was_killed_is_owed_once_then_spent_and_failed(self):
        v = self.version()
        self.ledger.begin({"key": v.key, "fid": "f1", "n": 1, "cell": v.cell, "kind": "look", "at": "t"})
        self.assertEqual(self.look(v)["status"], "looked", "the first kill: owed once more")
        self.assertEqual(self.ledger.row(v.key)["attempts"], 2)
        w = self.version(F.blind_program(("SPY", "QQQ"), look=16), cell="equity/other/index")
        for _ in range(2):
            self.ledger.begin({"key": w.key, "fid": "f1", "n": 1, "cell": w.cell, "kind": "look", "at": "t"})
        self.assertEqual(self.look(w)["status"], "failed", "killed twice: spent and failed, nothing run")
        self.assertEqual(self.ledger.row(w.key)["verdict"], "failed")

    def test_an_open_data_run_that_does_not_return_is_a_refusal_before_anything_sealed(self):
        def lost(code, params):
            raise RunLost("the decider exited")

        self.runs.segments = lost
        out = self.look(self.version())
        self.assertEqual(out["status"], "refused")
        self.assertIn("did not return", out["why"])
        self.assertEqual(self.ledger.spent(), [])

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
                          ".prediction.recent_zero_edge_passes", ".prediction.recent_zero_edge_rate",
                          ".prediction.zero_edge_passes", ".prediction.zero_edge_rate"],
                         "the receipt's synthetic rates and its predictions are the only figures")
        self.assertEqual(out["ledger"], "ok")
        self.assertEqual(out["by_seat"]["unseated"]["looked"], 1)
        self.assertEqual(out["by_seat"]["seated"]["looked"], 0)
        self.assertEqual((out["by_source"]["born"]["looked"], out["by_source"]["seed"]["looked"]), (1, 0))
        self.assertEqual(out["limits"], list(config.LIMITS))
        self.assertIn("alarm", out["canaries"])
        path = report.write(self.deep, out)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_a_seated_seed_is_counted_apart(self):
        v = gate.Version(fid="seed-reversal-index", n=1, code=F.blind_program(("SPY", "QQQ")), params={},
                         cell="beta/reversal/index", strong_recall=False, seated=True, source="seed")
        self.assertEqual(self.look(v)["status"], "looked")
        out = report.summary(self.ledger)
        self.assertEqual((out["by_seat"]["seated"]["looked"], out["by_source"]["seed"]["looked"]), (1, 1))
        self.assertEqual(out["by_source"]["born"]["looked"], 0)


class TheLedgerFailsClosed(unittest.TestCase):
    """The review of Oct 17: a damaged ledger, or one of another version, loaded as empty, so every version could be
    looked at on DVAL again and the budget, the cells and the canaries reset unseen. It refuses every look now."""

    def setUp(self):
        self.root = F.tmpdir(self)
        self.deep = F.deep_store(self.root / "equity-deep", ("SPY", "QQQ"))
        self.runs = F.InlineRuns(F.equity_store(self.root / "equity-daily", ("SPY", "QQQ")))

    def test_a_missing_ledger_is_empty_and_a_save_keeps_the_one_before(self):
        ledger = gate.Ledger(self.deep)
        self.assertFalse(ledger.damaged)
        ledger.refuse("k1", "why", identity="i", at="t")
        self.assertFalse((self.deep / config.LEDGER_PREV).exists(), "nothing stood before the first save")
        ledger.refuse("k2", "why", identity="i", at="t")
        prev = json.loads((self.deep / config.LEDGER_PREV).read_text())
        self.assertEqual(set(prev["refused"]), {"k1"}, "the file as it stood before the last save")
        self.assertEqual(stat.S_IMODE(os.stat(self.deep / config.LEDGER_PREV).st_mode), 0o600)

    def test_a_damaged_or_foreign_ledger_refuses_every_look_and_is_never_written_over(self):
        v = gate.Version(fid="f", n=1, code=F.blind_program(("SPY", "QQQ")), params={}, cell="c", strong_recall=False)
        for body in (b"{not json", json.dumps({"version": "deep-ledger-2", "looks": []}).encode(), b"[]",
                     json.dumps({"version": gate.LEDGER_VERSION, "looks": {"a": 1}}).encode()):
            with self.subTest(body[:20]):
                (self.deep / config.LEDGER).write_bytes(body)
                ledger = gate.Ledger(self.deep)
                self.assertTrue(ledger.damaged)
                out = gate.look(self.deep, v, self.runs, ledger=ledger, identity="i", now="t", worlds=WORLDS)
                self.assertEqual(out["status"], "ledger")
                self.assertEqual(self.runs.calls, [], "nothing is run")
                with self.assertRaises(gate.LedgerDamaged):
                    ledger.save()
                self.assertEqual((self.deep / config.LEDGER).read_bytes(), body, "nothing written over it")
                self.assertEqual(report.summary(ledger)["ledger"], "damaged")


class TheReserveStaysSealed(unittest.TestCase):
    """D2 (A58): the 2020-21 reserve is judged inside S3 beside the deep key and never alone. Its one run (`recent`) is
    made only inside a begun look, after the deep key's DVAL runs; never for a refusal, a wait, a canary or with
    the reserve sealed."""

    def setUp(self):
        self.root = F.tmpdir(self)
        self.deep = F.deep_store(self.root / "equity-deep", ("SPY", "QQQ"))
        F.equity_store(self.root / "equity-daily", ("SPY", "QQQ"))
        self.runs = F.InlineRuns(self.root / "equity-daily")
        self.ledger = gate.Ledger(self.deep)
        self.seen: list[tuple] = []
        real_recent, real_on_store = self.runs.recent, self.runs.on_store

        def recent(code, params):
            row = self.ledger.row(gate.version_key(code, params))
            dval = sum(1 for kind, r in self.runs.calls if kind == "on_store" and ("deep-A-" in str(r) or "deep-B-" in str(r)))
            self.seen.append(("recent", None if row is None else (row["attempts"], row["verdict"]), dval))
            return real_recent(code, params)

        def on_store(root, code, params, start, end, k):
            if start.year in (2020, 2021) and not ("deep-A-" in str(root) or "deep-B-" in str(root)):
                self.seen.append(("reserve-dated open run", str(root)))
            return real_on_store(root, code, params, start, end, k)

        self.runs.recent, self.runs.on_store = recent, on_store

    def look(self, v, **kw):
        return gate.look(self.deep, v, self.runs, ledger=self.ledger, identity="i", now="t", worlds=WORLDS, **kw)

    def version(self, **kw):
        base = dict(fid="f", n=1, code=F.blind_program(("SPY", "QQQ")), params={}, cell="c", strong_recall=False)
        return gate.Version(**{**base, **kw})

    def test_the_reserve_is_run_once_inside_the_begun_look_after_the_deep_key(self):
        self.assertEqual(self.look(self.version())["status"], "looked")
        self.assertEqual(self.seen, [("recent", (1, None), 2)],
                         "once, with the look begun and under way, after both DVAL segments' runs")

    def test_never_for_a_refusal_a_wait_a_canary_or_with_the_reserve_sealed(self):
        self.look(self.version(code=F.blind_program(("SPY", "XLRE"))))
        self.look(self.version(code=F.blind_program(("SPY", "QQQ"), look=12), strong_recall=None))
        self.look(self.version(code=F.blind_program(("SPY", "QQQ"), look=13)), reserve=False)
        weekday = F.blind_program(("SPY", "QQQ"), look=14).replace("    held = {p", "    if ctx.weekday == 1:\n        return out\n    held = {p")
        self.look(self.version(code=weekday))
        v = self.version()
        self.look(v)
        self.seen.clear()
        while not self.ledger.canary_due():
            self.ledger.looks.append({"key": f"p{len(self.ledger.looks)}", "kind": "look", "cell": "x", "verdict": None})
        canary = gate.canary_for(self.ledger, {v.key: v}, self.runs)
        self.assertEqual(self.look(canary, kind="canary")["status"], "looked")
        self.assertEqual(self.seen, [], "no reserve run but the real look's own")

    def test_only_the_gate_calls_the_reserves_run_and_only_the_house_runs_names_it(self):
        import ast

        repo = Path(__file__).resolve().parents[2]
        callers = []
        for path in sorted((repo / "league").rglob("*.py")):
            if path.is_relative_to(repo / "league" / "tests"):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and \
                                inner.func.attr == "recent" and isinstance(inner.func.value, ast.Name) and \
                                inner.func.value.id == "runs":
                            callers.append(f"{path.relative_to(repo).as_posix()}:{node.name}")
        self.assertEqual(sorted(set(callers)), ["league/deep/gate.py:_recent_key"])
        readers = [*sorted((repo / "league" / "deep").glob("*.py")),
                   *(repo / "league" / "ops" / f"{name}.py" for name in ("deep_report", "equity_deep", "contam_probe"))]
        named = sorted(path.relative_to(repo).as_posix() for path in readers if "config.RESERVE" in path.read_text())
        self.assertEqual(named, ["league/deep/screen3.py", "league/ops/deep_report.py"],
                         "the House's runs make the reserve's run; screen3 reads its dates for the CRASH positions")


class TheCanaryAlarm(unittest.TestCase):
    def test_the_report_only_alarm_reads_the_receipts_own_rate_and_never_halts(self):
        ledger = gate.Ledger(F.tmpdir(self))
        ledger.looks.append({"key": "c0", "kind": "canary", "verdict": {"passed": True, "deep": True, "recent": None}})
        self.assertEqual(gate.band_upper(1, config.CANARY_REFERENCE), 0)
        self.assertTrue(ledger.canary_alarm(), "one deep pass of one canary is past the band at 0.78%")
        self.assertFalse(ledger.halted(), "the pre-registered halt is at 15%: it does not fire")
        receipt = json.loads((Path(__file__).resolve().parents[2] / config.RECEIPT_PATH).read_text())
        self.assertEqual(config.CANARY_REFERENCE,
                         max(receipt["canary"]["synthetic_canary_deep_pass_raw_k2"].values()))
        for _ in range(30):
            ledger.looks.append({"key": f"c{len(ledger.looks)}", "kind": "canary",
                                 "verdict": {"passed": False, "deep": False, "recent": None}})
        self.assertFalse(ledger.canary_alarm())


class ASegmentWithAGap(unittest.TestCase):
    """The review of Oct 17: one missing session of a NEEDS fund made the look fail on the data. Such a segment is not
    scored, so no look is spent on it."""

    def test_the_audits_gaps_unscore_the_segment_before_any_look(self):
        root = F.tmpdir(self)
        deep = F.deep_store(root / "equity-deep", ("SPY", "QQQ"))
        manifest = json.loads((deep / config.MANIFEST).read_text())
        manifest["audit"]["gaps"] = {"dval": {"QQQ": 1}}
        (deep / config.MANIFEST).write_text(json.dumps(manifest))
        runs = F.InlineRuns(F.equity_store(root / "equity-daily", ("SPY", "QQQ")))
        ledger = gate.Ledger(deep)
        v = gate.Version(fid="f", n=1, code=F.blind_program(("SPY", "QQQ")), params={}, cell="c", strong_recall=False)
        out = gate.look(deep, v, runs, ledger=ledger, identity="i", now="t", worlds=WORLDS)
        self.assertEqual((out["status"], out["why"]), ("refused", "fewer than 750 scored DVAL sessions"))
        self.assertEqual(ledger.spent(), [], "no look is spent on a gap")
        self.assertFalse(any("deep-A-" in str(r) or "deep-B-" in str(r) for k, r in runs.calls if k == "on_store"))


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
