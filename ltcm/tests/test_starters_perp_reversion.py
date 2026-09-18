"""The perpetual futures reversion starter: universe by contract notional, both directions,
fee hurdle in contract fees. A fake kit; no network (leap: futures, Sept 17, 2026)."""

from __future__ import annotations

import importlib.util
import unittest

from ltcm.backtest import check_code
from ltcm.strategies import STARTERS_DIR

NOW = "2026-09-17T23:10:00.000Z"


def load():
    spec = importlib.util.spec_from_file_location("starter_perp_reversion", STARTERS_DIR / "perp_reversion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FUTURES = [
    {"symbol": "BIP-20DEC30-CDE", "root": "BTC", "price": 76300.0, "contract_size": 0.01, "contract_usd": 763.0, "perpetual": True, "volume_usd": 268e6, "quote_increment": 5.0},
    {"symbol": "ETP-20DEC30-CDE", "root": "ETH", "price": 2444.0, "contract_size": 0.1, "contract_usd": 244.4, "perpetual": True, "volume_usd": 110e6, "quote_increment": 0.5},
    {"symbol": "AVP-20DEC30-CDE", "root": "AVAX", "price": 7.55, "contract_size": 10, "contract_usd": 75.5, "perpetual": True, "volume_usd": 3.8e5, "quote_increment": 0.01},
    {"symbol": "BIT-25SEP26-CDE", "root": "BTC", "price": 76455.0, "contract_size": 0.01, "contract_usd": 764.5, "perpetual": False, "volume_usd": 80e6, "quote_increment": 5.0},
]


class PerpKit:
    def __init__(self, closes, *, equity="450", positions=(), orders=(), quotes=None):
        self.context = {"now": NOW, "positions": list(positions), "open_orders": list(orders), "learning_usd": "25", "live": True,
                        "equity_usd": equity, "fee_rates": {"coinbase": {"maker": "0.005", "taker": "0.009", "future_contract": "0.20", "age_seconds": 1}}}
        self.closes = closes
        self.quotes = quotes or {}
        self.log = []

    def say(self, text):
        self.log.append(text)

    def futures(self, root=None):
        return [dict(r) for r in FUTURES]

    def bars(self, symbol, interval="1h", limit=60, asset_class="crypto", venue="coinbase"):
        return [{"close": c} for c in self.closes.get(symbol, [])][-limit:]

    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        return self.quotes.get(symbol) or {}


def flat(price, n=37):
    return [price] * n


class PerpReversionTests(unittest.TestCase):
    def test_the_universe_is_perps_a_desk_can_hold_one_of(self):
        module = load()
        rows = module._universe(PerpKit({}), {**module.DEFAULTS}, 450.0)
        self.assertEqual([r["symbol"] for r in rows], ["ETP-20DEC30-CDE", "AVP-20DEC30-CDE"], "BTC's $763 contract is over 60% of $450; the dated BIT is not a perp")
        self.assertEqual([r["symbol"] for r in module._universe(PerpKit({}), {**module.DEFAULTS}, 300.0)], ["AVP-20DEC30-CDE"], "a $300 desk cannot hold the $244 ETH contract at 60%")

    def test_a_spike_is_sold_short_and_a_drop_is_bought_with_a_complete_plan(self):
        spike = flat(2400.0, 36) + [2460.0]  # last close far above a flat mean
        kit = PerpKit({"ETP-20DEC30-CDE": spike, "AVP-20DEC30-CDE": flat(7.55)}, quotes={"ETP-20DEC30-CDE": {"bid": "2459.5", "ask": "2460"}})
        out = load().decide(kit, {})
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["instrument"]["asset_class"], intent["instrument"]["symbol"], intent["side"], intent["quantity"]), ("future", "ETP-20DEC30-CDE", "sell", "1"))
        self.assertEqual(intent["limit_price"], "2459", "a tick under the bid, on the half-dollar tick")
        self.assertEqual(intent["target_price"], "2402", "the window's mean (the spike is in it), rounded up to the tick for a short")
        self.assertGreater(float(intent["stop_price"]), 2459.0, "a short's stop is above entry")
        self.assertEqual(intent["holding_period_hours"], 4)
        self.assertEqual(intent["expire_after_seconds"], 120)
        drop = flat(2400.0, 36) + [2340.0]
        kit = PerpKit({"ETP-20DEC30-CDE": drop, "AVP-20DEC30-CDE": flat(7.55)}, quotes={"ETP-20DEC30-CDE": {"bid": "2340", "ask": "2340.5"}})
        intent = load().decide(kit, {})["intents"][0]
        self.assertEqual((intent["side"], intent["limit_price"], intent["target_price"]), ("buy", "2341", "2398"), "a tick over the ask; the mean rounded down to the tick for a long")
        self.assertLess(float(intent["stop_price"]), 2341.0)

    def test_a_small_move_does_not_clear_the_contract_fees_and_spread(self):
        # A $75 AVAX contract: two 20-cent fees are 0.53% of notional; a 0.4% move is not enough.
        closes = flat(7.55, 36) + [7.52]
        sd_free = [7.55 + (0.001 if i % 2 else -0.001) for i in range(36)] + [7.52]
        kit = PerpKit({"AVP-20DEC30-CDE": sd_free, "ETP-20DEC30-CDE": flat(2444.0)}, quotes={"AVP-20DEC30-CDE": {"bid": "7.52", "ask": "7.53"}})
        out = load().decide(kit, {"z_entry": 1.0})
        self.assertEqual(out["intents"], [])
        self.assertTrue(any("no entry" in line for line in kit.log), kit.log)

    def test_held_or_working_contracts_are_not_re_entered_and_the_code_passes_the_screen(self):
        spike = flat(2400.0, 36) + [2460.0]
        kit = PerpKit({"ETP-20DEC30-CDE": spike, "AVP-20DEC30-CDE": flat(7.55)}, positions=[{"symbol": "ETP-20DEC30-CDE", "asset_class": "future", "quantity": "-1"}],
                      quotes={"ETP-20DEC30-CDE": {"bid": "2459.5", "ask": "2460"}})
        self.assertEqual(load().decide(kit, {})["intents"], [])
        check_code((STARTERS_DIR / "perp_reversion.py").read_text(encoding="utf-8"))


class ThinContractTests(unittest.TestCase):
    def test_a_thin_contract_is_judged_on_the_bars_it_has_once_there_are_twelve(self):
        spike = [2400.0] * 19 + [2460.0]  # 20 closes, under the 36 the window asks for
        kit = PerpKit({"ETP-20DEC30-CDE": spike, "AVP-20DEC30-CDE": [7.55] * 5}, quotes={"ETP-20DEC30-CDE": {"bid": "2459.5", "ask": "2460"}})
        out = load().decide(kit, {"max_intents": 2})
        self.assertEqual([i["instrument"]["symbol"] for i in out["intents"]], ["ETP-20DEC30-CDE"])
        self.assertTrue(any("AVP-20DEC30-CDE: only 5 bars" in line for line in kit.log), kit.log)
