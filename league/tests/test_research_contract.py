"""Resolve the published debit-vertical examples on invented quotes only."""

import ast
import copy
from pathlib import Path
import re
import unittest

from league.gym.ctx import Snapshot
from league.gym.legs import Refused, resolve_open
from league.gym.venue import rules_for


def debit_examples():
    contract = (Path(__file__).resolve().parents[1] / "CONTRACT.md").read_text(encoding="utf-8")
    section = contract.split("### Debit-vertical legs\n", 1)[1].split("**Close**:", 1)[0]
    return [ast.literal_eval(block) for block in re.findall(r"```python\n(.*?)\n```", section, re.DOTALL)]


def fabricated_chain(*, missing_neighbors=False):
    strikes = [100, 100] if missing_neighbors else [99, 100, 101, 99, 100, 101]
    calls = [True, False] if missing_neighbors else [True, True, True, False, False, False]
    bids = [0.95, 0.95] if missing_neighbors else [1.45, 0.95, 0.45, 0.45, 0.95, 1.45]
    return Snapshot("SPY", 600, 100, [1] * len(strikes), strikes, calls, bids,
                    [bid + 0.05 for bid in bids], [10] * len(strikes), [10] * len(strikes))


class DebitContractExamples(unittest.TestCase):
    def test_published_examples_resolve_and_reversed_offsets_are_refused(self):
        examples = debit_examples()
        self.assertEqual(len(examples), 2)
        self.assertEqual({example["legs"][0]["right"] for example in examples}, {"C", "P"})
        for example in examples:
            with self.subTest(right=example["legs"][0]["right"]):
                order = resolve_open(example, fabricated_chain(), rules_for("SPY"), buying_power=1000)
                self.assertEqual((order.type, order.qty), ("debit_vertical", 1))
                self.assertEqual([leg.side for leg in order.legs], [1, -1])
                self.assertTrue(0 < order.max_loss_share < 1)
                self.assertEqual(order.legs[0].dte, order.legs[1].dte)
                reversed_example = copy.deepcopy(example)
                reversed_example["legs"][1]["offset"] *= -1
                with self.assertRaisesRegex(Refused, "dearer"):
                    resolve_open(reversed_example, fabricated_chain(), rules_for("SPY"), buying_power=1000)

    def test_missing_neighbor_is_a_structural_refusal(self):
        for example in debit_examples():
            with self.subTest(right=example["legs"][0]["right"]):
                with self.assertRaises(Refused):
                    resolve_open(example, fabricated_chain(missing_neighbors=True), rules_for("SPY"), buying_power=1000)


if __name__ == "__main__":
    unittest.main()
