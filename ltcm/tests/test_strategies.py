"""Strategies: code a desk deploys to trade for it between sessions (leap: strategies)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.manifest import DeskManifest
from ltcm.strategies import STARTERS, STARTERS_DIR, Strategies, _capped_quantity, _parse_result
from ltcm.tests.test_manifest import SAMPLE
from ltcm.tests.test_tools import FakeContext

NOW = "2026-09-16T04:10:00.000Z"
LATER = "2026-09-16T04:21:00.000Z"


def manifest(**overrides):
    data = {
        **SAMPLE,
        "id": "scholes-2",
        "family": "ranges",
        "parent_id": "scholes",
        "venues": ["kalshi"],
        "instruments": {**SAMPLE["instruments"], "asset_classes": ["event", "crypto"], "deny": []},
        "tools": ["quote", "propose_order", "run_code", "deploy_strategy", "undeploy_strategy", "strategy_report"],
        "capital": {"mode": "shadow", "usd": "142"},
    }
    data.update(overrides)
    return DeskManifest.from_dict(data)


class Run:
    def __init__(self, stdout, exit_code=0):
        self.stdout = stdout
        self.exit_code = exit_code
        self.seconds = Decimal("1.5")
        self.code_sha256 = "ab" * 32
        self.sandbox = "sb_lab-scholes-2"
        self.saved_as = None


class FakeManager:
    """Answers a run with whatever the test scripted, and keeps a toolbox per desk."""

    def __init__(self):
        self.files = {}
        self.runs = []
        self.script = lambda desk_id, code: Run('STRATEGY-RESULT {"intents": [], "notes": "quiet"}')

    def toolbox_files(self, desk_id):
        return dict(self.files.get(desk_id, {}))

    def toolbox_save(self, desk_id, name, code, purpose):
        self.files.setdefault(desk_id, {})[f"{name}.py"] = code

    def run(self, desk_id, code, *, purpose="", save_as=None, timeout=60):
        self.runs.append((desk_id, purpose, timeout, code))
        return self.script(desk_id, code)


class Log:
    def __init__(self):
        self.events = []

    def append(self, stream, kind, payload, *, id=None, at=None):
        self.events.append((stream, kind, payload, id, at))


class FakeService:
    def __init__(self, manager, manifests):
        self.sandboxes = manager
        self.manifests = manifests
        self.config = {"learning": {"shadow_notional_usd": "15", "live_kalshi_usd": "10", "live_coinbase_usd": "25"}}
        self.log = Log()
        self.alerts = []
        self.contexts = []
        self.clock = [NOW]

    def now(self):
        return self.clock[0]

    def alert(self, level, text):
        self.alerts.append((level, text))

    def context(self, manifest, session_id=None):
        ctx = FakeContext()
        ctx.session_id = session_id
        self.contexts.append(ctx)
        return ctx


INTENT = {
    "instrument": {"asset_class": "event", "symbol": "KXBTC-26SEP1600-B75950", "market_id": "KXBTC-26SEP1600-B75950", "right": "no"},
    "side": "buy",
    "quantity": "40",
    "order_type": "limit",
    "limit_price": "0.78",
    "rationale": "spot 75,936; p(in bucket) 0.075; NO at 0.78 has 0.05 of edge",
    "holding_period_hours": 1,
}


class StrategyCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = FakeManager()
        self.manifest = manifest()
        self.service = FakeService(self.manager, {self.manifest.id: self.manifest})
        self.strategies = Strategies(self.service, path=Path(self.temp.name) / "strategies.json", config={"starters": False})
        self.manager.files[self.manifest.id] = {"edge.py": "def decide(kit, params):\n    return []\n"}


class DeployTests(StrategyCase):
    def test_a_deploy_needs_a_saved_module_with_decide_and_a_sane_cadence(self):
        with self.assertRaises(ValueError):
            self.strategies.deploy(self.manifest, "Bad Name", 600, {})
        with self.assertRaises(ValueError):
            self.strategies.deploy(self.manifest, "missing", 600, {})
        self.manager.files[self.manifest.id]["nodecide.py"] = "x = 1\n"
        with self.assertRaises(ValueError):
            self.strategies.deploy(self.manifest, "nodecide", 600, {})
        with self.assertRaises(ValueError):
            self.strategies.deploy(self.manifest, "edge", 60, {})
        self.assertEqual(self.manager.runs, [], "nothing ran for a refused deploy")

    def test_a_deploy_dry_runs_the_code_records_it_and_publishes_the_run(self):
        row = self.strategies.deploy(self.manifest, "edge", 600, {"min_edge": 0.03}, note="range pricing")
        self.assertEqual((row["name"], row["cadence_seconds"], row["params"], row["runs"]), ("edge", 600, {"min_edge": 0.03}, 0))
        self.assertEqual(len(self.manager.runs), 1)
        desk_id, purpose, timeout, code = self.manager.runs[0]
        self.assertEqual(purpose, "strategy edge")
        self.assertIn("from toolbox import edge as strategy", code)
        self.assertIn("dry_run", code)
        kinds = [e[1] for e in self.service.log.events]
        self.assertEqual(kinds, ["desk.code_run"])
        payload = self.service.log.events[0][2]
        self.assertTrue(payload["purpose"].startswith("strategy edge deployed every 600s"))
        self.assertEqual(payload["session_id"], "scholes-2:20260916-0410:strategy:edge")
        self.assertEqual(self.strategies.report(self.manifest)["strategies"][0]["name"], "edge")
        self.assertEqual(self.strategies.undeploy(self.manifest, "edge"), {"undeployed": "edge"})
        self.assertEqual(self.strategies.report(self.manifest)["strategies"], [])

    def test_a_failing_dry_run_is_refused_with_the_error(self):
        self.manager.script = lambda d, c: Run('STRATEGY-RESULT {"intents": [], "error": "NameError: spot"}', 1)
        with self.assertRaises(ValueError) as caught:
            self.strategies.deploy(self.manifest, "edge", 600, {})
        self.assertIn("NameError", str(caught.exception))

    def test_a_desk_runs_at_most_the_configured_number(self):
        self.strategies.config["max_per_desk"] = 1
        self.strategies.deploy(self.manifest, "edge", 600, {})
        self.manager.files[self.manifest.id]["other.py"] = "def decide(kit, params):\n    return []\n"
        with self.assertRaises(ValueError):
            self.strategies.deploy(self.manifest, "other", 600, {})


class TickTests(StrategyCase):
    def test_a_due_strategy_runs_and_its_intents_go_through_propose_order(self):
        self.strategies.deploy(self.manifest, "edge", 600, {})
        self.manager.script = lambda d, c: Run(
            "pricing 4 buckets\nSTRATEGY-RESULT " + json.dumps({"intents": [INTENT], "notes": "one bucket cheap", "log": ["4 candidates"]})
        )
        first = self.strategies.tick(self.service.manifests, NOW)
        self.assertEqual(first, [{"desk_id": "scholes-2", "strategy": "edge", "intents": 1, "approved": 1, "error": False}])
        ctx = self.service.contexts[-1]
        self.assertEqual(ctx.session_id, "scholes-2:20260916-0410:strategy:edge")
        intent = ctx.intents[0]
        self.assertEqual(intent.session_id, "scholes-2:20260916-0410:strategy:edge")
        self.assertEqual(intent.quantity, Decimal("40"))  # a shadow desk keeps its own size
        self.assertEqual(intent.limit_price, Decimal("0.78"))
        self.assertEqual(intent.time_in_force, "gtc")
        self.assertTrue(intent.rationale.startswith("[strategy edge] spot 75,936"))
        row = self.strategies.report(self.manifest, "edge")
        self.assertEqual((row["runs"], row["intents"], row["approved"], row["errors"], row["last_run_at"]), (1, 1, 1, 0, NOW))
        run_events = [e for e in self.service.log.events if e[1] == "desk.code_run"]
        self.assertEqual(run_events[-1][2]["purpose"], "strategy edge: 1 intent(s), 1 approved")
        self.assertIn("pricing 4 buckets", run_events[-1][2]["stdout"])
        self.assertIn("one bucket cheap", run_events[-1][2]["stdout"])
        # Not due again until the cadence has passed.
        self.assertEqual(self.strategies.tick(self.service.manifests, "2026-09-16T04:15:00.000Z"), [])
        self.assertEqual(len(self.strategies.tick(self.service.manifests, LATER)), 1)

    def test_a_live_desks_strategy_is_capped_at_learning_size(self):
        live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        self.manager.files["scholes"] = {"edge.py": "def decide(kit, params):\n    return []\n"}
        self.service.manifests = {"scholes": live}
        self.strategies.deploy(live, "edge", 600, {})
        self.manager.script = lambda d, c: Run("STRATEGY-RESULT " + json.dumps({"intents": [INTENT]}))
        self.strategies.tick(self.service.manifests, NOW)
        intent = self.service.contexts[-1].intents[0]
        self.assertEqual(intent.quantity, Decimal("12"), "40 x 0.78 = 31.20 is over the $10 learning size; 12 x 0.78 = 9.36 is not")

    def test_market_orders_are_refused_and_errors_are_recorded_not_raised(self):
        self.strategies.deploy(self.manifest, "edge", 600, {})
        self.manager.script = lambda d, c: Run("STRATEGY-RESULT " + json.dumps({"intents": [{**INTENT, "order_type": "market", "limit_price": None}]}))
        out = self.strategies.tick(self.service.manifests, NOW)
        self.assertEqual(out[0]["approved"], 0)
        self.assertEqual(self.service.contexts[-1].intents, [])
        self.manager.script = lambda d, c: Run("Traceback...\nZeroDivisionError: division by zero\n", 1)
        out = self.strategies.tick(self.service.manifests, LATER)
        self.assertEqual(out[0]["error"], True)
        row = self.strategies.report(self.manifest, "edge")
        self.assertEqual(row["errors"], 1)
        self.assertIn("ZeroDivisionError", row["last_error"])
        self.assertTrue(any("error" in e[2]["purpose"] for e in self.service.log.events if e[1] == "desk.code_run"))

    def test_idle_runs_publish_once_an_hour(self):
        self.strategies.deploy(self.manifest, "edge", 600, {})
        before = len(self.service.log.events)
        self.strategies.tick(self.service.manifests, NOW)  # idle, just published by the deploy
        self.assertEqual(len(self.service.log.events), before)
        self.strategies.tick(self.service.manifests, "2026-09-16T05:20:00.000Z")
        self.assertEqual(len(self.service.log.events), before + 1)

    def test_runs_per_tick_are_bounded_and_oldest_first(self):
        self.strategies.config["max_runs_per_tick"] = 1
        for name in ("a1", "b2"):
            self.manager.files[self.manifest.id][f"{name}.py"] = "def decide(kit, params):\n    return []\n"
            self.strategies.deploy(self.manifest, name, 600, {})
        self.strategies.store.update(self.manifest.id, "b2", last_run_at="2026-09-16T03:00:00.000Z")
        self.strategies.store.update(self.manifest.id, "a1", last_run_at="2026-09-16T03:30:00.000Z")
        out = self.strategies.tick(self.service.manifests, NOW)
        self.assertEqual([o["strategy"] for o in out], ["b2"])


class BootstrapTests(StrategyCase):
    def test_desks_of_a_family_with_a_starter_get_it_once(self):
        self.strategies.config["starters"] = True
        crypto = manifest(id="hilibrand-2", family="crypto", parent_id="hilibrand", venues=["coinbase"], capital={"mode": "shadow", "usd": "487"})
        events = manifest(id="mullins", family="kalshi", parent_id=None)
        self.service.manifests = {m.id: m for m in (self.manifest, crypto, events)}
        deployed = self.strategies.bootstrap(self.service.manifests)
        self.assertEqual(deployed, ["hilibrand-2/hourly_reversion", "scholes-2/hourly_ranges"])
        self.assertIn("hourly_ranges.py", self.manager.toolbox_files("scholes-2"))
        self.assertTrue(self.strategies.report(self.manifest, "hourly_ranges")["house"])
        self.assertEqual(self.strategies.bootstrap(self.service.manifests), [], "never twice")
        self.assertEqual(self.strategies.report(events)["strategies"], [])
        # The first tick bootstraps on its own.
        fresh = Strategies(self.service, path=Path(self.temp.name) / "s2.json", config={"starters": True})
        fresh.tick(self.service.manifests, NOW)
        self.assertEqual(sorted(fresh.store.read()), ["hilibrand-2", "scholes-2"])


class HelperTests(unittest.TestCase):
    def test_the_result_line_is_the_last_marker_and_bad_lines_are_nothing(self):
        self.assertIsNone(_parse_result(""))
        self.assertIsNone(_parse_result("no marker here"))
        self.assertIsNone(_parse_result("STRATEGY-RESULT not json"))
        self.assertEqual(_parse_result('x\nSTRATEGY-RESULT {"intents": [1]}\n')["intents"], [1])
        self.assertEqual(_parse_result('STRATEGY-RESULT {"notes": "n"}')["intents"], [])

    def test_the_learning_cap_keeps_whole_contracts_and_fractional_coins(self):
        event = {"instrument": {"asset_class": "event"}, "quantity": "40", "limit_price": "0.78"}
        self.assertEqual(_capped_quantity(event, Decimal("10")), "12")
        self.assertEqual(_capped_quantity({**event, "quantity": "5"}, Decimal("10")), "5")
        self.assertEqual(_capped_quantity({**event, "limit_price": "0.99", "quantity": "30"}, Decimal("0.5")), "1")
        coin = {"instrument": {"asset_class": "crypto"}, "quantity": "0.01", "limit_price": "75000"}
        self.assertEqual(_capped_quantity(coin, Decimal("25")), "0.00033333")


class FakeKit:
    """The kit a starter sees, with a market that is plainly cheap."""

    def __init__(self, now="2026-09-16T04:10:00.000Z", spot=75936.0):
        self.context = {"now": now, "positions": [], "learning_usd": "15", "live": False}
        self.log = []
        self.spot = spot

    def say(self, text):
        self.log.append(text)

    def bars(self, symbol, interval="1h", limit=60, asset_class="crypto", venue="coinbase"):
        base = 75000.0 if symbol.startswith("BTC") else 2400.0
        closes = [base * (1 + 0.001 * ((i * 7) % 5 - 2)) for i in range(limit)]  # a quiet tape
        if symbol.startswith("SOL"):  # a crash: the last close far below the mean
            closes[-1] = base * 0.9
        return [{"close": f"{c:.2f}"} for c in closes]

    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        base = self.spot if symbol.startswith("BTC") else 2400.0
        if symbol.startswith("SOL"):
            base = 2400.0 * 0.9
        return {"bid": f"{base - 1:.2f}", "ask": f"{base + 1:.2f}", "last": f"{base:.2f}"}

    def kalshi_series(self, series, limit=200, status="open"):
        if series != "KXBTC":
            return []
        return [
            {"ticker": "KXBTC-26SEP1600-B75950", "yes_sub_title": "$75,900 to $75,999.99", "status": "open",
             "close_time": "2026-09-16T04:40:00Z", "yes_bid": "0.03", "yes_ask": "0.06"},  # at the money, priced at 6%
            {"ticker": "KXBTC-26SEP1600-B80050", "yes_sub_title": "$80,000 to $80,099.99", "status": "open",
             "close_time": "2026-09-16T04:40:00Z", "yes_bid": "0.01", "yes_ask": "0.02"},  # far tail
            {"ticker": "KXBTC-26SEP1600-T76000", "title": "BTC above $76,000", "status": "open",
             "close_time": "2026-09-16T04:40:00Z", "yes_bid": "0.40", "yes_ask": "0.44"},  # a threshold: skipped
        ]

    def kalshi_market(self, ticker):
        return None


def load_starter(name):
    spec = importlib.util.spec_from_file_location(f"starter_{name}", STARTERS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StarterTests(unittest.TestCase):
    def test_every_family_starter_exists_and_defines_decide(self):
        for family, name in STARTERS.items():
            module = load_starter(name)
            self.assertTrue(callable(getattr(module, "decide", None)), family)

    def test_the_ranges_starter_buys_the_cheap_at_the_money_bucket(self):
        kit = FakeKit()
        out = load_starter("hourly_ranges").decide(kit, {})
        intents = out["intents"]
        self.assertEqual(len(intents), 1, out)
        intent = intents[0]
        self.assertEqual(intent["instrument"]["market_id"], "KXBTC-26SEP1600-B75950")
        self.assertEqual((intent["instrument"]["right"], intent["side"], intent["order_type"]), ("yes", "buy", "limit"))
        self.assertEqual(intent["limit_price"], "0.06")
        self.assertEqual(intent["quantity"], str(int(15 / 0.06)))
        self.assertIn("edge after fees", intent["rationale"])
        # A held bucket is never bought again.
        kit.context["positions"] = [{"market_id": "KXBTC-26SEP1600-B75950"}]
        self.assertEqual(load_starter("hourly_ranges").decide(kit, {})["intents"], [])

    def test_the_reversion_starter_buys_the_crash_and_leaves_the_rest(self):
        kit = FakeKit()
        out = load_starter("hourly_reversion").decide(kit, {})
        intents = out["intents"]
        self.assertEqual([i["instrument"]["symbol"] for i in intents], ["SOL-USD"])
        intent = intents[0]
        self.assertEqual(intent["holding_period_hours"], 12)
        self.assertLess(Decimal(intent["stop_price"]), Decimal(intent["limit_price"]))
        self.assertGreater(Decimal(intent["target_price"]), Decimal(intent["limit_price"]))
        # Sized to the kit's learning size ($15 here), not the starter's own default.
        self.assertAlmostEqual(float(intent["quantity"]) * float(intent["limit_price"]), 15.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
