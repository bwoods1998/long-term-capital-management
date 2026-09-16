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
        weather = manifest(id="haghani-2", family="weather", parent_id="haghani", capital={"mode": "shadow", "usd": "150"})
        events = manifest(id="mullins", family="kalshi", parent_id=None)
        self.service.manifests = {m.id: m for m in (self.manifest, crypto, weather, events)}
        deployed = self.strategies.bootstrap(self.service.manifests)
        self.assertEqual(
            deployed,
            ["haghani-2/daily_temps", "hilibrand-2/hourly_reversion", "scholes-2/hourly_ranges", "scholes-2/hourly_quotes"],
        )
        self.assertIn("hourly_ranges.py", self.manager.toolbox_files("scholes-2"))
        self.assertTrue(self.strategies.report(self.manifest, "hourly_ranges")["house"])
        self.assertEqual(self.strategies.report(self.manifest, "hourly_quotes")["cadence_seconds"], 300)
        self.assertEqual(self.strategies.report(weather, "daily_temps")["cadence_seconds"], 1800)
        self.assertEqual(self.strategies.bootstrap(self.service.manifests), [], "never twice")
        self.assertEqual(self.strategies.report(events)["strategies"], [])
        # The first tick bootstraps on its own.
        fresh = Strategies(self.service, path=Path(self.temp.name) / "s2.json", config={"starters": True})
        fresh.tick(self.service.manifests, NOW)
        self.assertEqual(sorted(fresh.store.read()), ["haghani-2", "hilibrand-2", "scholes-2"])

    def test_shadow_desks_are_dealt_different_variants_and_the_live_desk_keeps_the_defaults(self):
        from ltcm.strategies import STARTER_VARIANTS, starter_params

        live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        self.assertEqual(starter_params("ranges", live), {})
        self.assertEqual(starter_params("ranges", live, quotes=True), {"buckets": 1})
        dealt = {starter_params("ranges", manifest(id=f"scholes-{n}"))["shrink"] for n in range(2, 8)}
        self.assertGreater(len(dealt), 1, "siblings explore different settings")
        for family, variants in STARTER_VARIANTS.items():
            for n in range(2, 6):
                self.assertIn(starter_params(family, manifest(id=f"desk-{n}", family=family)), variants)
        # The deal is stable: the same desk gets the same variant on every restart.
        self.assertEqual(starter_params("crypto", manifest(id="hilibrand-3", family="crypto")), starter_params("crypto", manifest(id="hilibrand-3", family="crypto")))

    def test_house_params_and_code_follow_the_repo_until_the_desk_makes_them_its_own(self):
        self.strategies.config["starters"] = True
        self.strategies.bootstrap(self.service.manifests)
        self.strategies.store.update(self.manifest.id, "hourly_ranges", params={"min_edge": 0.9}, cadence_seconds=900)
        self.strategies.bootstrap(self.service.manifests)
        row = self.strategies.report(self.manifest, "hourly_ranges")
        self.assertEqual(row["cadence_seconds"], 300)
        self.assertNotEqual(row["params"], {"min_edge": 0.9})
        # A desk that edited its copy keeps it.
        self.manager.files[self.manifest.id]["hourly_ranges.py"] = "def decide(kit, params):\n    return []  # mine\n"
        self.strategies.bootstrap(self.service.manifests)
        self.assertIn("# mine", self.manager.toolbox_files(self.manifest.id)["hourly_ranges.py"])
        # A desk that redeployed it as its own keeps its params too.
        self.strategies.store.update(self.manifest.id, "hourly_ranges", house=False, params={"min_edge": 0.9})
        self.strategies.bootstrap(self.service.manifests)
        self.assertEqual(self.strategies.report(self.manifest, "hourly_ranges")["params"], {"min_edge": 0.9})


class CancelAndRecordTests(StrategyCase):
    def setUp(self):
        super().setUp()
        self.log_events = []

        class Event:
            def __init__(self, payload):
                self.payload = payload

        def read(stream=None, kind=None, limit=None):
            return [Event(p) for s, k, p in self.log_events if s == stream and k == kind]

        self.service.log.read = read
        self.open_orders = []
        self.service.gateway = type("G", (), {"open_orders": lambda g, desk_id: list(self.open_orders)})()

    def test_a_strategy_may_cancel_only_its_own_resting_orders(self):
        self.strategies.deploy(self.manifest, "edge", 600, {})
        self.log_events.append(("desk:scholes-2", "desk.intent", {"intent_id": "oi-mine", "session_id": "scholes-2:20260916-0400:strategy:edge"}))
        self.log_events.append(("desk:scholes-2", "desk.intent", {"intent_id": "oi-session", "session_id": "scholes-2:20260916-0405:cadence:04:05"}))
        self.open_orders = [
            {"order_id": "ord-mine", "intent_id": "oi-mine", "instrument": {"market_id": "KXBTC-26SEP1600-B75950", "right": "yes"}, "side": "buy", "quantity": "10", "limit_price": "0.20", "status": "accepted", "submitted_at": "2026-09-16T04:00:00.000Z"},
            {"order_id": "ord-session", "intent_id": "oi-session", "instrument": {"market_id": "KXETH-26SEP1601-B2402", "right": "no"}, "side": "buy", "quantity": "5", "limit_price": "0.60", "status": "accepted", "submitted_at": "2026-09-16T04:05:00.000Z"},
        ]
        seen = self.strategies.open_orders_for(self.manifest)
        self.assertEqual([(o["order_id"], o["strategy"]) for o in seen], [("ord-mine", "edge"), ("ord-session", None)])
        self.manager.script = lambda d, c: Run("STRATEGY-RESULT " + json.dumps({"intents": [], "cancels": ["ord-mine", "ord-session", "ord-nope"], "notes": "requote"}))
        out = self.strategies.tick(self.service.manifests, NOW)
        cancelled = [c for c in self.service.contexts[-1].seen if c[0] == "cancel_order"]
        self.assertEqual(cancelled, [("cancel_order", ("ord-mine",))])
        self.assertIn("1 cancelled", self.strategies.report(self.manifest, "edge")["last_notes"])
        self.assertEqual(out[0]["approved"], 0)

    def test_a_live_strategy_sizes_up_only_after_it_has_earned_it(self):
        live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        self.manager.files["scholes"] = {"edge.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.deploy(live, "edge", 600, {})
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"))
        wins = [("desk:scholes", "desk.outcome", {"pnl": "0.50", "rationale_excerpt": "[strategy edge] x"}) for _ in range(20)]
        self.log_events += [("desk:scholes", "desk.intent", {"intent_id": "oi-1", "session_id": "scholes:20260916-0400:strategy:edge"})] + wins
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("30"), "twenty settled winners: three times learning size")
        self.log_events.append(("desk:scholes", "desk.outcome", {"pnl": "-40", "rationale_excerpt": "[strategy edge] y"}))
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "a losing record goes back to learning size")
        self.assertEqual(self.strategies.size_cap(self.manifest, "edge"), Decimal("15"), "a shadow desk keeps its learning size")

    def test_the_record_attributes_fills_and_settlements_to_the_strategy(self):
        self.strategies.deploy(self.manifest, "edge", 600, {})
        self.log_events += [
            ("desk:scholes-2", "desk.intent", {"intent_id": "oi-1", "session_id": "scholes-2:20260916-0400:strategy:edge"}),
            ("desk:scholes-2", "desk.intent", {"intent_id": "oi-2", "session_id": "scholes-2:20260916-0405:cadence:04:05"}),
            ("broker:scholes-2", "broker.order", {"order_id": "ord-1", "intent_id": "oi-1"}),
            ("broker:scholes-2", "broker.order", {"order_id": "ord-2", "intent_id": "oi-2"}),
            ("broker:scholes-2", "broker.fill", {"order_id": "ord-1", "quantity": "20", "price": "0.65", "fee": "0.32"}),
            ("broker:scholes-2", "broker.fill", {"order_id": "ord-2", "quantity": "5", "price": "0.10", "fee": "0.01"}),
            ("desk:scholes-2", "desk.outcome", {"pnl": "7.00", "rationale_excerpt": "[strategy edge] NO at 0.65 has edge"}),
            ("desk:scholes-2", "desk.outcome", {"pnl": "-4.50", "rationale_excerpt": "[strategy edge] YES at 0.20"}),
            ("desk:scholes-2", "desk.outcome", {"pnl": "9.00", "rationale_excerpt": "Exit stale offside long"}),
        ]
        row = self.strategies.report(self.manifest, "edge")
        self.assertEqual((row["fills"], row["filled_notional_usd"], row["fees_usd"]), (1, "13.00", "0.32"))
        self.assertEqual((row["settled"], row["wins"], row["settled_pnl_usd"]), (2, 1, "2.50"))


class RetryTests(StrategyCase):
    def test_a_house_starter_whose_dry_run_failed_is_tried_again_on_a_later_build(self):
        self.strategies.config["starters"] = True
        self.manager.script = lambda d, c: Run('STRATEGY-RESULT {"intents": [], "error": "AttributeError: hint"}', 1)
        self.assertEqual(self.strategies.bootstrap(self.service.manifests), [])
        row = self.strategies.report(self.manifest, "hourly_ranges")
        self.assertEqual((row["enabled"], row["house"]), (False, True))
        self.assertIn("AttributeError", row["last_error"])
        self.assertEqual(self.strategies.tick(self.service.manifests, NOW), [], "a disabled starter never runs")
        # The next build's dry run passes: the starter is deployed after all.
        self.manager.script = lambda d, c: Run('STRATEGY-RESULT {"intents": [], "notes": "quiet"}')
        self.assertEqual(self.strategies.bootstrap(self.service.manifests), ["scholes-2/hourly_ranges", "scholes-2/hourly_quotes"])
        self.assertTrue(self.strategies.report(self.manifest, "hourly_ranges")["enabled"])


class HelperTests(unittest.TestCase):
    def test_the_runner_renders_and_compiles(self):
        from ltcm.strategies import RUNNER

        code = RUNNER % {"params": json.dumps(json.dumps({"a": 1})), "context": json.dumps(json.dumps({"now": NOW})), "name": "edge", "max_intents": 5}
        compile(code, "main.py", "exec")
        self.assertIn("from toolbox import edge as strategy", code)
        self.assertIn("series_hint", code)

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
        seconds = {"1m": 60, "5m": 300, "15m": 900}.get(interval, 3600)
        wiggle = 0.001 * (seconds / 3600) ** 0.5  # a quiet tape at any bar size
        closes = [base * (1 + wiggle * ((i * 7) % 5 - 2)) for i in range(limit)]
        if symbol.startswith("SOL"):  # a crash: the last close far below the mean
            closes[-1] = base * 0.9
        return [{"close": f"{c:.2f}"} for c in closes]

    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        base = self.spot if symbol.startswith("BTC") else 2400.0
        if symbol.startswith("SOL"):
            base = 2400.0 * 0.9
        return {"bid": f"{base - 1:.2f}", "ask": f"{base + 1:.2f}", "last": f"{base:.2f}"}

    def kalshi_series(self, series, limit=200, status="open"):
        # The listing carries bounds and stale, mis-scaled prices, as Kalshi's does; the live
        # book comes from kalshi_market, one call per ticker.
        if series != "KXBTC":
            return []
        return [
            {"ticker": "KXBTC-26SEP1600-B75950", "yes_sub_title": "$75,900 to 75,999.99", "status": "active",
             "close_time": "2026-09-16T04:40:00Z", "yes_bid": "0.0003", "yes_ask": "0.0006"},  # at the money
            {"ticker": "KXBTC-26SEP1600-B80050", "yes_sub_title": "$80,000 to 80,099.99", "status": "active",
             "close_time": "2026-09-16T04:40:00Z", "yes_bid": "0.0001", "yes_ask": "0.0002"},  # far tail
            {"ticker": "KXBTC-26SEP1600-T76000", "title": "BTC above $76,000", "status": "active",
             "close_time": "2026-09-16T04:40:00Z", "yes_bid": "0.40", "yes_ask": "0.44"},  # a threshold: skipped
        ]

    def kalshi_market(self, ticker):
        self.quoted = getattr(self, "quoted", []) + [ticker]
        live = {
            "KXBTC-26SEP1600-B75950": {"ticker": ticker, "yes_bid": "0.03", "yes_ask": "0.06", "no_ask": "0.97"},  # priced at 6%
            "KXBTC-26SEP1600-B80050": {"ticker": ticker, "yes_bid": "0.01", "yes_ask": "0.02", "no_ask": "0.99"},
        }
        return live.get(ticker)


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
        self.assertEqual(kit.quoted[0], "KXBTC-26SEP1600-B75950", "the nearest bucket is quoted live first")
        # A held bucket is never bought again.
        kit.context["positions"] = [{"market_id": "KXBTC-26SEP1600-B75950"}]
        self.assertEqual(load_starter("hourly_ranges").decide(kit, {})["intents"], [])

    def test_the_quoting_starter_rests_both_legs_under_fair_and_replaces_drifted_quotes(self):
        kit = FakeKit()
        out = load_starter("hourly_quotes").decide(kit, {"buckets": 1, "spread": 0.04})
        intents = out["intents"]
        self.assertEqual([i["instrument"]["right"] for i in intents], ["yes", "no"])
        yes, no = intents
        self.assertEqual(yes["instrument"]["market_id"], "KXBTC-26SEP1600-B75950")
        self.assertLess(Decimal(yes["limit_price"]), Decimal("0.06"), "a resting bid sits under the ask")
        self.assertLess(Decimal(no["limit_price"]), Decimal("0.97"))
        self.assertIn("resting YES bid", yes["rationale"])
        self.assertEqual(out["cancels"], [])
        # A quote already resting at fair stays; a stale one is cancelled and replaced.
        kit.context["open_orders"] = [
            {"order_id": "ord-keep", "strategy": "hourly_quotes", "market_id": "KXBTC-26SEP1600-B75950", "right": "yes", "limit_price": yes["limit_price"], "submitted_at": "2026-09-16T04:08:00Z"},
            {"order_id": "ord-stale", "strategy": "hourly_quotes", "market_id": "KXBTC-26SEP1600-B75950", "right": "no", "limit_price": no["limit_price"], "submitted_at": "2026-09-16T03:00:00Z"},
            {"order_id": "ord-other", "strategy": "hourly_ranges", "market_id": "KXBTC-26SEP1600-B75950", "right": "no", "limit_price": "0.50", "submitted_at": "2026-09-16T03:00:00Z"},
        ]
        again = load_starter("hourly_quotes").decide(kit, {"buckets": 1, "spread": 0.04})
        self.assertEqual(again["cancels"], ["ord-stale"])
        self.assertEqual([i["instrument"]["right"] for i in again["intents"]], ["no"], "only the cancelled leg is re-placed")

    def test_the_temperature_starter_prices_buckets_from_the_forecast(self):
        from ltcm.starters import daily_temps as _  # noqa: F401 -- importable as a package module too

        class WeatherKit(FakeKit):
            def weather_cities(self):
                return [{"name": "New York", "series": "KXHIGHNY", "station": "KNYC"}]

            def weather(self, city):
                return {"city": city, "days": [{"date": "2026-09-16", "day_high": "81.0"}, {"date": "2026-09-17", "day_high": "77.0"}]}

            def kalshi_series(self, series, limit=200, status="open"):
                if series != "KXHIGHNY":
                    return []
                return [
                    {"ticker": "KXHIGHNY-26SEP16-B81.5", "yes_sub_title": "81° to 82°", "status": "active", "close_time": "2026-09-17T05:00:00Z", "yes_bid": "0.0010", "yes_ask": "0.0011"},
                    {"ticker": "KXHIGHNY-26SEP16-T82", "yes_sub_title": "83° or above", "status": "active", "close_time": "2026-09-17T05:00:00Z", "yes_bid": "0.0001", "yes_ask": "0.0002"},
                    {"ticker": "KXHIGHNY-26SEP16-T75", "yes_sub_title": "74° or below", "status": "active", "close_time": "2026-09-17T05:00:00Z", "yes_bid": "0.0001", "yes_ask": "0.0002"},
                ]

            def kalshi_market(self, ticker):
                live = {
                    "KXHIGHNY-26SEP16-B81.5": {"yes_bid": "0.12", "yes_ask": "0.15"},  # the forecast bucket priced at 15%
                    "KXHIGHNY-26SEP16-T82": {"yes_bid": "0.30", "yes_ask": "0.33"},
                    "KXHIGHNY-26SEP16-T75": {"yes_bid": "0.02", "yes_ask": "0.04"},
                }
                return live.get(ticker)

        module = load_starter("daily_temps")
        self.assertEqual(module.settlement_day("KXHIGHNY-26SEP16-B81.5"), "2026-09-16")
        self.assertAlmostEqual(module.probability({"yes_sub_title": "81° to 82°"}, 81.0, 2.5), 0.31, delta=0.02)
        kit = WeatherKit()
        out = module.decide(kit, {"cities": ["New York"]})
        intents = out["intents"]
        self.assertTrue(intents, out)
        best = intents[0]
        self.assertEqual(best["instrument"]["market_id"], "KXHIGHNY-26SEP16-B81.5")
        self.assertEqual((best["instrument"]["right"], best["limit_price"]), ("yes", "0.15"))
        self.assertIn("forecast high 81F", best["rationale"])

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
