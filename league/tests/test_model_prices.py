"""Every model the league may call has a gateway price and a campaign ceiling (Sept 22, 2026).

The gateway refuses a model it has no price for, and the campaign refuses one it has no ceiling
for, so a model named in the league but missing from either fails closed: research stops.
GPT-6 Sol and Luna were added to both on the day they launched; this keeps the two tables and
the league's model constants from drifting apart again.
"""
from __future__ import annotations

import json
import re
import unittest
from decimal import Decimal
from pathlib import Path

import json as _json

from league import fast_research, grants
from league.hypotheses import foundry_model
from league.frontier import MODEL, MODEL_CEILINGS
from league.routing import TABLE

REPO = Path(__file__).resolve().parents[2]


def gateway_prices() -> dict:
    text = (REPO / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")
    match = re.search(r'"FRONTIER_MODELS":\s*("(?:[^"\\]|\\.)*")', text)
    return json.loads(json.loads(match.group(1)))


class ModelPrices(unittest.TestCase):
    def test_every_model_the_league_calls_is_priced_twice(self):
        prices = gateway_prices()
        game = _json.loads((REPO / "league" / "game.json").read_text(encoding="utf-8"))
        called = {MODEL, fast_research.MODEL, grants.MODEL, foundry_model(game) or MODEL} | {r.model for r in TABLE.values() if r.model.startswith("gpt-")}
        for model in sorted(called):
            with self.subTest(model=model):
                self.assertIn(model, prices, "the gateway would refuse it")
                self.assertIn(model, MODEL_CEILINGS, "the campaign would refuse it")

    def test_a_ceiling_is_never_below_the_dearest_rate_the_gateway_bills(self):
        prices = gateway_prices()
        for model, (inp, out) in MODEL_CEILINGS.items():
            with self.subTest(model=model):
                row = prices[model]
                self.assertGreaterEqual(inp, Decimal(str(max(row["input"], row["long_input"]))))
                self.assertGreaterEqual(out, Decimal(str(max(row["output"], row["long_output"]))))

    def test_research_runs_on_gpt_6_luna(self):
        self.assertEqual(fast_research.MODEL, "gpt-6-luna")
        self.assertEqual(grants.MODEL, fast_research.MODEL)
        self.assertEqual(MODEL_CEILINGS["gpt-6-luna"], (Decimal("0.25"), Decimal("0.75")))
        # The judge is not moved: real-money admission keeps the independent strongest reviewer.
        self.assertEqual(TABLE["audit"].model, "gpt-6-astra")


class FoundryModel(unittest.TestCase):
    @unittest.skip('Wave 2b deletes the hypothesis foundry: the options overhaul (Sept 26, 2026) took its game.json block and the non-options desks out')
    def test_the_foundry_writes_on_gpt_6_sol_and_the_judges_keep_astra(self):
        game = _json.loads((REPO / "league" / "game.json").read_text(encoding="utf-8"))
        self.assertEqual(foundry_model(game), "gpt-6-sol")
        self.assertEqual(TABLE["audit"].model, "gpt-6-astra")

    def test_an_empty_setting_keeps_the_house_model(self):
        self.assertIsNone(foundry_model({"hypotheses": {"model": ""}}))
        self.assertIsNone(foundry_model({}))


if __name__ == "__main__":
    unittest.main()
