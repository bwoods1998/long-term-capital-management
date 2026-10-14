"""SEAL X3 (release E4, package D): THE LIVE CTX IS THE GYM'S CTX, and the live decision is the Gym's decision.

`league.xs.ctx.build` is the one constructor of a panel ctx. The Gym's engine feeds it `inputs_from_panel` (a slice of
the store); the live book feeds it `inputs_from_fetch` (the venue-shaped rows of its 16:20 fetch). On package C's
helper `league.xs.synth.same_ctx_cases` (20 random decision days of a synthetic panel, both sides built under ONE run
key and ONE aid set, the live side's columns being REF, that day's members and two held names that have left the
index, at least one day straddling an index change) the two ctxs are equal BYTE FOR BYTE, the dither included; and
the decider child's "decide" (league/xs/child.py) answers the same ctx sha, the same target, the same orders and the
same ineligible lots on both.

SYNTHETIC DATA ONLY (`league.xs.synth`: seeded pseudo-random prices on the NYSE calendar; no market row). Both sides
of a case are built under one vintage of the adjusted series: a live fetch is not byte-identical to a later store's
by assumption (the vendor rounds adjustment=all prices to the cent, and a dividend restates them), and the nightly I6
job measures the real thing on the House.

Everything here is package C's code under test through package D's entry points, so the whole module skips while
package C is a Step 0 stub (as it was when this package was built) and runs from the moment it is merged."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from league.equity.store import mint_equity_gate_capability
from league.tests.test_xs_runner import core_built
from league.xs import child, config, ctx, engine, synth

PROGRAM = '''
NEEDS = {"panel": "sp500", "history": 60, "max_names": 12, "rebalance": "weekly", "weekday": 0}
PARAMS = {"k": 5}


def decide(ctx):
    ranked = []
    for i in range(ctx.n):
        value = float(ctx.ret[i][-1])
        ranked.append((value if value == value else 0.0, int(ctx.ids[i])))
    ranked.sort()
    return {"target": {slot: 0.2 for _, slot in ranked[:PARAMS["k"]]}, "at": "open"}
'''


def live(case: dict[str, Any]) -> ctx.Inputs:
    """The live path's `Inputs` of a case: from the venue-shaped rows of its fetch."""
    return ctx.inputs_from_fetch(case["raw_rows"], case["all_rows"], day=case["day"], columns=case["columns"],
                                 **case["common"])


@unittest.skipUnless(core_built(), "package C (the panel store, ctx, program and synthetic panels) is a Step 0 stub")
class TheLiveCtxIsTheGymsCtx(unittest.TestCase):
    HISTORY = 60

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = synth.synthetic_panel(
            Path(cls.tmp) / "equity-daily", n_assets=60, seed=5, churn=0.25, gate=True,
            dividends={103: [(dt.date(2025, 3, 14), 0.41), (dt.date(2025, 9, 12), 0.41)],
                       117: [(dt.date(2025, 6, 6), 1.25)]},
            splits={109: (dt.date(2025, 5, 19), 4.0)})
        cls.cases = synth.same_ctx_cases(cls.root, history=cls.HISTORY, count=20, seed=0, window="validation")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_twenty_days_byte_for_byte_across_an_index_change(self):
        self.assertEqual(len(self.cases), 20)
        self.assertEqual(len({case["day"] for case in self.cases}), 20)
        self.assertTrue(any(case["straddles"] for case in self.cases), "one day straddles an index change")
        for case in self.cases:
            with self.subTest(day=case["day"]):
                gym = ctx.build(case["gym"])
                fetched = ctx.build(live(case))
                self.assertEqual(ctx.ctx_bytes(gym), ctx.ctx_bytes(fetched))
                self.assertGreater(gym.n, 20)
                self.assertEqual(len(gym.positions), 3)
                # the two held names that have left the index keep a column, an id and a mark, and are no slot
                slots = {int(i) for i in gym.ids}
                gone = [lot for lot in gym.positions if lot["slot"] not in slots]
                self.assertEqual(len(gone), 2)
                self.assertEqual(sorted(ctx.ineligible(case["gym"], ctx.derive(case["gym"]))), [1, 2])

    def test_both_sides_are_one_run_key_and_one_aid_set(self):
        for case in self.cases:
            gym, fetched = case["gym"], live(case)
            self.assertTrue(np.array_equal(gym.ids, fetched.ids))
            self.assertEqual(gym.dither_key, fetched.dither_key)
            self.assertTrue(np.array_equal(gym.elig0, fetched.elig0))
            self.assertEqual(len(case["columns"]), len(config.REF) + len(gym.ids))
            self.assertEqual(case["columns"][:len(config.REF)], list(config.REF))

    def test_the_dither_is_in_the_bytes(self):
        """Under another run's dither key the same day is another ctx: what is compared is the dithered ctx, never
        an undithered one that would agree whatever the key."""
        case = self.cases[0]
        other = dataclasses.replace(case["gym"], dither_key=hashlib.sha256(b"another run").digest())
        self.assertNotEqual(ctx.ctx_bytes(ctx.build(other)), ctx.ctx_bytes(ctx.build(case["gym"])))
        again = dataclasses.replace(case["gym"], dither_key=bytes(case["gym"].dither_key))
        self.assertEqual(ctx.ctx_bytes(ctx.build(again)), ctx.ctx_bytes(ctx.build(case["gym"])))

    def test_a_bar_that_differs_is_a_ctx_that_differs(self):
        """The comparison has teeth: one close of one name moved by a cent in the fetch is another ctx."""
        case = self.cases[1]
        gym = ctx.build(case["gym"])
        symbol = case["columns"][len(config.REF) + int(np.flatnonzero(case["gym"].elig0[len(config.REF):])[0])]
        rows = {name: [dict(row) for row in series] for name, series in case["all_rows"].items()}
        rows[symbol][-3]["c"] = round(rows[symbol][-3]["c"] + 0.01, 2)
        raw = {name: [dict(row) for row in series] for name, series in case["raw_rows"].items()}
        raw[symbol][-3]["c"] = round(raw[symbol][-3]["c"] + 0.01, 4)
        moved = ctx.inputs_from_fetch(raw, rows, day=case["day"], columns=case["columns"], **case["common"])
        self.assertNotEqual(ctx.ctx_bytes(ctx.build(moved)), ctx.ctx_bytes(gym))

    def test_the_child_answers_one_decision_on_both(self):
        """The decider child on the Gym's inputs and on the live fetch's: the same ctx sha, the same target, the
        same orders by the KEEP rule and the same ineligible lots, on a decision day and on a hold day."""
        state: dict[str, Any] = {}
        loaded = child.handle("load", {"key": "p", "code": PROGRAM, "params": {}, "name": "p"}, state)
        self.assertTrue(loaded["ok"], loaded)
        for case in self.cases[:8]:
            with self.subTest(day=case["day"]):
                answers = []
                for inputs in (case["gym"], live(case)):
                    row = child.handle("decide", {"jobs": [{"key": "p", "inputs": inputs, "called": True}]}, state)
                    answers.append(row["results"]["p"])
                gym, fetched = answers
                for key in ("ctx_sha", "target", "at", "orders", "rejects", "ineligible", "hold", "failed"):
                    self.assertEqual(gym[key], fetched[key], key)
                self.assertEqual(gym["ctx_sha"], hashlib.sha256(ctx.ctx_bytes(ctx.build(case["gym"]))).hexdigest())
                self.assertEqual((gym["hold"], gym["failed"], len(gym["target"])), (False, False, 5))
                self.assertEqual(gym["ineligible"], [1, 2], "the two held names that left the index")
                # the third lot is of an eligible name: kept if targeted, else sold; five names end up held
                sells = [o["sell"] for o in gym["orders"] if "sell" in o]
                buys = [o for o in gym["orders"] if "buy_id" in o]
                self.assertTrue({1, 2} <= set(sells))
                self.assertEqual(len(buys) + (3 not in sells), 5)
                self.assertTrue(all(o["usd"] == 200.0 for o in buys))
                # a hold day: no program code, the standing target's buys, the same on both sides
                standing = {"target": gym["target"], "at": "close", "exited": []}
                quiet = [child.handle("decide", {"jobs": [{"key": "p", "inputs": inputs, "called": False,
                                                           "standing": standing}]}, state)["results"]["p"]
                         for inputs in (case["gym"], live(case))]
                self.assertEqual(quiet[0], quiet[1])
                self.assertEqual((quiet[0]["ctx_sha"], quiet[0]["failed"], quiet[0]["ineligible"]),
                                 (None, False, [1, 2]))
                self.assertEqual(sorted(o["buy_id"] for o in quiet[0]["orders"]),
                                 sorted(o["buy_id"] for o in engine.plan_orders(
                                     gym["target"], "close", [{"lid": 3, "id": next(
                                         lot["slot"] for lot in ctx.build(case["gym"]).positions if lot["id"] == 3)}],
                                     1000.0, standing=True)[0]))

    def test_the_train_window_and_the_sealed_look_agree_too(self):
        for window, gate in (("train", None), ("look", mint_equity_gate_capability(self.root, "the I6 seal"))):
            cases = synth.same_ctx_cases(self.root, history=self.HISTORY, count=6, seed=3, window=window, gate=gate)
            self.assertEqual(len(cases), 6)
            for case in cases:
                with self.subTest(window=window, day=case["day"]):
                    self.assertEqual(ctx.ctx_bytes(ctx.build(case["gym"])), ctx.ctx_bytes(ctx.build(live(case))))


if __name__ == "__main__":
    unittest.main()
