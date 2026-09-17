"""Strategies: code a desk deploys to trade for it between sessions (leap: strategies)."""

from __future__ import annotations

import importlib.util
import json
import time
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
#: After three days of settlements: the evidence gate resamples days.
AFTER = "2026-09-18T06:00:00.000Z"


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

    def test_a_strategys_stated_expiry_reaches_the_intent_clamped_to_the_window(self):
        # Sept 17, 2026: a strategy states when the venue should cancel its bid, as a timestamp.
        self.strategies.deploy(self.manifest, "edge", 600, {})
        intents = [
            {**INTENT, "expires_at": "2026-09-16T05:40:00Z"},
            {**INTENT, "quantity": "41", "expires_at": "2026-09-30T00:00:00Z"},
            {**INTENT, "quantity": "42", "expires_at": "2026-09-16T04:10:30Z"},
        ]
        self.manager.script = lambda d, c: Run("STRATEGY-RESULT " + json.dumps({"intents": intents}))
        self.strategies.tick(self.service.manifests, NOW)
        stated = [intent.expires_at for intent in self.service.contexts[-1].intents]
        self.assertEqual(stated, ["2026-09-16T05:40:00.000Z", "2026-09-18T04:10:00.000Z", "2026-09-16T04:12:00.000Z"])

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
            ["haghani-2/daily_temps", "hilibrand-2/hourly_reversion", "hilibrand-2/spot_quotes", "mullins/kalshi_favorites", "scholes-2/hourly_ranges", "scholes-2/hourly_quotes"],
        )
        self.assertIn("hourly_ranges.py", self.manager.toolbox_files("scholes-2"))
        self.assertTrue(self.strategies.report(self.manifest, "hourly_ranges")["house"])
        self.assertEqual(self.strategies.report(self.manifest, "hourly_quotes")["cadence_seconds"], 300)
        self.assertEqual(self.strategies.report(weather, "daily_temps")["cadence_seconds"], 1800)
        self.assertEqual(self.strategies.bootstrap(self.service.manifests), [], "never twice")
        self.assertEqual([s["name"] for s in self.strategies.report(events)["strategies"]], ["kalshi_favorites"])
        # The first tick bootstraps on its own.
        fresh = Strategies(self.service, path=Path(self.temp.name) / "s2.json", config={"starters": True})
        fresh.tick(self.service.manifests, NOW)
        self.assertEqual(sorted(fresh.store.read()), ["haghani-2", "hilibrand-2", "mullins", "scholes-2"])

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
            def __init__(self, payload, at=None):
                self.payload, self.at = payload, at

        def read(stream=None, kind=None, limit=None, newest=False):
            return [Event(p, *rest) for s, k, p, *rest in self.log_events if (stream is None or s == stream) and k == kind]

        self.service.log.read = read
        self.open_orders = []
        self.service.gateway = type("G", (), {"open_orders": lambda g, desk_id: list(self.open_orders)})()

    def settled(self, desk, count, pnl="0.50", price="0.50", days=3, name="edge"):
        """`count` settled positions of 10 contracts at `price`, spread over `days` days."""
        out = []
        for n in range(count):
            ticker = f"KXA-{desk}-{len(self.log_events)}-{n}"
            out.append((f"desk:{desk}", "desk.outcome", {
                "pnl": pnl, "rationale_excerpt": f"[strategy {name}] x", "instrument": f"event:{ticker}:kalshi:no:{ticker}",
                "entry_price": price, "quantity": "10", "entry_fees": "0",
            }, f"2026-09-{16 + n % days:02d}T05:00:00.000Z"))
        return out

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

    def test_a_live_strategy_sizes_up_only_after_its_record_passes_the_evidence_gate(self):
        live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        self.manager.files["scholes"] = {"edge.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.deploy(live, "edge", 600, {})
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"))
        self.log_events += [("desk:scholes", "desk.intent", {"intent_id": "oi-1", "session_id": "scholes:20260916-0400:strategy:edge"})]
        self.log_events += self.settled("scholes", 20)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "twenty settled winners were enough before Sept 17, 2026; the gate needs 25")
        self.log_events += self.settled("scholes", 5)
        self.assertEqual(self.strategies.report(live, "edge")["evidence"]["passes"], True, "25 over three days, every day positive")
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "passing at the 25 the gate needs is the start of the ramp, not a step")
        self.log_events += self.settled("scholes", 25)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("20"), "50 of the 75 (3 x 25) that reach the top: halfway")
        self.log_events += self.settled("scholes", 25)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("30"), "75: the top, three times learning size while the desk's limit cannot be read")
        self.log_events += self.settled("scholes", 25)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("30"), "and no further")
        self.log_events.append(("desk:scholes", "desk.outcome", {"pnl": "-40", "rationale_excerpt": "[strategy edge] y", "instrument": "event:KXB:kalshi:no:KXB",
                                                                 "entry_price": "0.50", "quantity": "10", "entry_fees": "0"}, "2026-09-16T09:00:00.000Z"))
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "a bad day in the record goes back to learning size")
        self.assertEqual(self.strategies.size_cap(self.manifest, "edge"), Decimal("15"), "a shadow desk keeps its learning size")
        self.assertIn("bootstrap", self.strategies.report(live, "edge")["evidence"]["reason"], "the desk reads the gate's verdict")
        self.assertNotIn("returns", self.strategies.report(live, "edge"), "not the 500 numbers behind it")

    def test_a_lucky_favorites_record_stays_at_learning_size(self):
        """Sept 17, 2026: six favorites at 0.93, six wins, lifted the size under the old gate. A
        breakeven strategy does that 65% of the time."""
        live = manifest(id="mullins", family="kalshi", parent_id=None, capital={"mode": "live", "usd": "400"})
        self.manager.files["mullins"] = {"favorites.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.config["earned_settled"] = 6
        self.strategies.deploy(live, "favorites", 900, {})
        self.log_events += [("desk:mullins", "desk.intent", {"intent_id": "oi-f", "session_id": "mullins:20260916-0400:strategy:favorites"})]
        self.log_events += self.settled("mullins", 6, pnl="0.70", price="0.93", name="favorites")
        self.assertEqual(self.strategies.size_cap(live, "favorites"), Decimal("10"), "6 of the 43 settlements a 0.93 favorite needs")
        verdict = self.strategies.report(live, "favorites")["evidence"]
        self.assertEqual((verdict["kind"], verdict["passes"], verdict["n_needed"]), ("lopsided", False, 43))
        self.log_events += self.settled("mullins", 36, pnl="0.70", price="0.93", name="favorites")
        self.log_events += self.settled("mullins", 1, pnl="-9.30", price="0.93", name="favorites")
        verdict = self.strategies.report(live, "favorites")["evidence"]
        self.assertEqual((verdict["passes"], verdict["n_needed"]), (True, 43), "43 settled, one loss: the loss rate is under breakeven")
        self.assertEqual(self.strategies.size_cap(live, "favorites"), Decimal("10"), "a breakeven favorite passes here about a fifth of the time: still learning size")
        self.log_events += self.settled("mullins", 43, pnl="0.70", price="0.93", name="favorites")
        self.assertEqual(self.strategies.size_cap(live, "favorites"), Decimal("20"), "86 of the 129 that reach the top")
        self.log_events += self.settled("mullins", 43, pnl="0.70", price="0.93", name="favorites")
        self.assertEqual(self.strategies.size_cap(live, "favorites"), Decimal("30"))
        self.log_events += self.settled("mullins", 6, pnl="-9.30", price="0.93", name="favorites")
        self.assertEqual(self.strategies.size_cap(live, "favorites"), Decimal("10"), "7 losses in 135 is over what breakeven allows at this count: back to learning size")

    def test_an_earning_strategy_ramps_toward_the_desks_order_limit(self):
        live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "1000"})
        self.manager.files["scholes"] = {"edge.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.deploy(live, "edge", 600, {})

        class Ledger:
            def state(self, at):
                return type("S", (), {"equity": Decimal("1000")})()

        self.service.ledgers = {"scholes": Ledger()}
        fit = (Decimal("1000") * min(live.limits.max_order_notional_pct, live.limits.max_position_pct) * Decimal("0.9")).quantize(Decimal("0.01"))
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "no record: learning size")
        self.log_events += [("desk:scholes", "desk.intent", {"intent_id": "oi-1", "session_id": "scholes:20260916-0400:strategy:edge"})]
        self.log_events += self.settled("scholes", 20)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "not yet through the gate: learning size")
        self.log_events += self.settled("scholes", 5)
        self.assertEqual(fit, Decimal("225.00"))
        # Sept 17, 2026 review: the ramp was settled / n_needed, and the gate needs n_needed, so the
        # run a record first passed took the desk from $10 to its $225 limit. Now it is linear from
        # learning size at n_needed (25) to the limit at full_size_multiple x n_needed (75).
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("10"), "through the gate at 25: still learning size")
        self.log_events += self.settled("scholes", 1)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("14.30"), "one more settlement: a fiftieth of the way")
        self.log_events += self.settled("scholes", 24)
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("117.50"), "50: halfway to the limit")
        self.log_events += self.settled("scholes", 25)
        self.assertEqual(self.strategies.size_cap(live, "edge"), fit, "75: the desk's full order limit")
        self.log_events += self.settled("scholes", 30)
        self.assertEqual(self.strategies.size_cap(live, "edge"), fit, "never above it")
        self.strategies.config["evidence"] = {"full_size_multiple": 5}
        self.assertEqual(self.strategies.size_cap(live, "edge"), Decimal("182.00"), "105 settled at a multiple of 5: (105 - 25) / 100 of the way")
        self.strategies.config["evidence"] = {"full_size_multiple": 1}
        self.assertEqual(self.strategies.size_cap(live, "edge"), fit, "a multiple of 1 is the old step, on purpose only")

    def test_an_outcome_without_an_instrument_does_not_take_a_favorites_record_off_the_loss_rate_rule(self):
        """Sept 17, 2026 review: one outcome naming no instrument made the record's asset class
        unknown, and an unknown record is judged by the bootstrap. Thirty favorites at 0.93 over
        three days, every day positive, pass the bootstrap; the loss-rate rule needs 43."""
        live = manifest(id="mullins", family="kalshi", parent_id=None, capital={"mode": "live", "usd": "400"})
        self.manager.files["mullins"] = {"favorites.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.deploy(live, "favorites", 900, {})
        self.log_events += [("desk:mullins", "desk.intent", {"intent_id": "oi-f", "session_id": "mullins:20260916-0400:strategy:favorites"})]
        self.log_events += self.settled("mullins", 30, pnl="0.70", price="0.93", name="favorites")
        self.log_events.append(("desk:mullins", "desk.outcome", {"pnl": "0.70", "rationale_excerpt": "[strategy favorites] x", "entry_price": "0.93",
                                                                 "quantity": "10", "entry_fees": "0"}, "2026-09-17T05:00:00.000Z"))
        record = self.strategies.record("mullins", "favorites")
        self.assertEqual(record["asset_class"], "event")
        verdict = self.strategies.assess(record)
        self.assertEqual((verdict["kind"], verdict["passes"]), ("lopsided", False))
        self.assertEqual(self.strategies.size_cap(live, "favorites"), Decimal("10"))

    def test_the_ramp_runs_from_n_needed_to_its_multiple(self):
        from ltcm.strategies import earned_ramp

        self.assertEqual(earned_ramp(43, 43), Decimal(0))
        self.assertEqual(earned_ramp(86, 43), Decimal("0.5"))
        self.assertEqual(earned_ramp(129, 43), Decimal(1))
        self.assertEqual(earned_ramp(500, 43), Decimal(1))
        self.assertEqual(earned_ramp(10, 43), Decimal(0), "under n_needed is never negative")
        self.assertEqual(earned_ramp(50, 25, "2"), Decimal(1))
        self.assertEqual(earned_ramp(25, 25, 1), Decimal(1))
        self.assertEqual(earned_ramp(2, 0, 3), Decimal("0.5"), "n_needed is at least one")
        self.assertEqual(earned_ramp(50, 25, "nonsense"), Decimal("0.5"), "an unreadable multiple is 3")

    def test_a_shrinking_desk_is_sized_to_fit_its_own_limits(self):
        """Scholes at $33 with a 15% cap: a $10 learning order is refused forever; $4.45 trades."""
        live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        equity = {"scholes": Decimal("33"), self.manifest.id: Decimal("1000")}

        class Ledger:
            def __init__(self, value):
                self.value = value

            def state(self, at):
                return type("S", (), {"equity": self.value})()

        self.service.ledgers = {k: Ledger(v) for k, v in equity.items()}
        pct = min(live.limits.max_order_notional_pct, live.limits.max_position_pct)
        self.assertEqual(self.strategies.size_cap(live, "edge"), (Decimal("33") * pct * Decimal("0.9")).quantize(Decimal("0.01")))
        self.assertLess(self.strategies.size_cap(live, "edge"), Decimal("10"))
        self.assertEqual(self.strategies.size_cap(self.manifest, "edge"), Decimal("15"), "a rich desk keeps its learning size")

    def test_the_record_attributes_fills_and_settlements_to_the_strategy(self):
        self.strategies.deploy(self.manifest, "edge", 600, {})
        self.log_events += [
            ("desk:scholes-2", "desk.intent", {"intent_id": "oi-1", "session_id": "scholes-2:20260916-0400:strategy:edge"}),
            ("desk:scholes-2", "desk.intent", {"intent_id": "oi-2", "session_id": "scholes-2:20260916-0405:cadence:04:05"}),
            ("broker:kalshi", "broker.order", {"order_id": "ord-1", "intent_id": "oi-1", "desk_id": "scholes-2"}),
            ("broker:shadow", "broker.order", {"order_id": "ord-2", "intent_id": "oi-2", "desk_id": "scholes-2"}),
            ("broker:kalshi", "broker.fill", {"order_id": "ord-1", "quantity": "20", "price": "0.65", "fee": "0.32"}),
            ("broker:shadow", "broker.fill", {"order_id": "ord-2", "quantity": "5", "price": "0.10", "fee": "0.01"}),
            ("desk:scholes-2", "desk.outcome", {"pnl": "7.00", "rationale_excerpt": "[strategy edge] NO at 0.65 has edge"}),
            ("desk:scholes-2", "desk.outcome", {"pnl": "-4.50", "rationale_excerpt": "[strategy edge] YES at 0.20"}),
            ("desk:scholes-2", "desk.outcome", {"pnl": "9.00", "rationale_excerpt": "Exit stale offside long"}),
        ]
        row = self.strategies.report(self.manifest, "edge")
        self.assertEqual((row["fills"], row["filled_notional_usd"], row["fees_usd"]), (1, "13.00", "0.32"))
        self.assertEqual((row["settled"], row["wins"], row["settled_pnl_usd"]), (2, 1, "2.50"))


class ParallelRunTests(StrategyCase):
    def test_desks_run_side_by_side_one_run_per_desk(self):
        import threading as _threading

        gate = _threading.Event()
        started = []
        other = manifest(id="scholes-3")
        self.service.manifests[other.id] = other
        for desk in (self.manifest, other):
            self.manager.files[desk.id] = {"edge.py": "def decide(kit, params):\n    return []\n", "second.py": "def decide(kit, params):\n    return []\n"}
            self.strategies.deploy(desk, "edge", 300, {})
            self.strategies.deploy(desk, "second", 300, {})
        real = self.strategies.run_one

        def slow(manifest_, name, row, at):
            started.append((manifest_.id, name))
            gate.wait(5)
            return real(manifest_, name, row, at)

        self.strategies.run_one = slow
        self.strategies.config["parallel_runs"] = 4
        self.assertEqual(self.strategies.tick(self.service.manifests, NOW), [], "dispatched, not awaited")
        deadline = time.time() + 5
        while len(started) < 2 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(sorted(d for d, _ in started), ["scholes-2", "scholes-3"], "one run per desk, both desks at once")
        self.strategies.tick(self.service.manifests, NOW)
        self.assertEqual(len(started), 2, "a desk with a run in flight is not dispatched again")
        gate.set()
        done = self.strategies.wait(10)
        self.assertEqual(sorted(r["desk_id"] for r in done), ["scholes-2", "scholes-3"])


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

    def test_the_starters_price_kalshis_fee_to_the_hundredth_of_a_cent(self):
        # Sept 17, 2026: the venue charged a 1-lot at 0.02 $0.0014; rounded to the cent it was $0.01.
        from ltcm.backtest import kalshi_taker_fee

        for name in ("kalshi_favorites", "daily_temps", "hourly_ranges"):
            fee = load_starter(name)._fee
            self.assertEqual((fee(0.02), fee(0.93), fee(0.50)), (0.0014, 0.0046, 0.0175), name)
            for cents in range(1, 100):
                self.assertEqual(fee(cents / 100), kalshi_taker_fee(cents / 100, 1), (name, cents))

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

    def test_the_ranges_starter_prices_thresholds_on_every_crypto_series(self):
        from ltcm.starters import hourly_ranges as ranges

        spot, sigma = 100.0, 0.01
        self.assertAlmostEqual(ranges._model_probability(("above", 100.0), spot, sigma), 0.5, places=6)
        self.assertAlmostEqual(ranges._model_probability(("above", 101.0), spot, sigma) + ranges._model_probability(("below", 101.0), spot, sigma), 1.0, places=9)
        self.assertLess(ranges._model_probability(("between", 99.0, 101.0), spot, sigma), 1.0)
        self.assertEqual(ranges._strike({"strike_type": "greater", "floor_strike": "75000"}), ("above", 75000.0))
        self.assertEqual(ranges._strike({"strike_type": "less", "cap_strike": "2400"}), ("below", 2400.0))
        self.assertEqual(ranges._strike({"strike_type": "between", "floor_strike": "75900", "cap_strike": "76000"}), ("between", 75900.0, 76000.0))
        self.assertEqual(ranges._strike({"yes_sub_title": "$75,900 to 75,999.99"}), ("between", 75900.0, 75999.99))
        self.assertIn("KXBTCD", ranges.CRYPTO_SERIES)
        self.assertEqual(ranges.DEFAULTS["series"], "all")

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

    def test_the_spot_quoting_starter_rests_post_only_and_offers_what_it_holds(self):
        kit = FakeKit()
        out = load_starter("spot_quotes").decide(kit, {"symbols": ["BTC-USD", "ETH-USD"]})
        bids = out["intents"]
        self.assertEqual([i["instrument"]["symbol"] for i in bids], ["BTC-USD", "ETH-USD"])
        btc = bids[0]
        self.assertTrue(btc["post_only"])
        self.assertEqual(btc["side"], "buy")
        self.assertLess(Decimal(btc["limit_price"]), Decimal("75935"), "a bid under the touch")
        self.assertAlmostEqual(float(btc["quantity"]) * float(btc["limit_price"]), 15.0, delta=0.1)
        # Holding BTC: the bid gives way to a post-only offer over cost for the whole holding.
        kit.context["positions"] = [{"symbol": "BTC-USD", "asset_class": "crypto", "quantity": "0.0002", "average_cost": "75000"}]
        kit.context["open_orders"] = [{"order_id": "ord-bid", "strategy": "spot_quotes", "symbol": "BTC-USD", "side": "buy", "limit_price": btc["limit_price"], "submitted_at": "2026-09-16T04:09:00Z"}]
        again = load_starter("spot_quotes").decide(kit, {"symbols": ["BTC-USD"]})
        self.assertEqual(again["cancels"], ["ord-bid"], "the bid no longer belongs")
        offer = again["intents"][0]
        self.assertEqual((offer["side"], offer["post_only"], offer["quantity"]), ("sell", True, "0.000200"))
        self.assertGreater(Decimal(offer["limit_price"]), Decimal("75300"), "over cost by the spread")

    def test_the_spot_quoting_starter_bids_over_dust_and_never_offers_more_than_it_holds(self):
        kit = FakeKit()
        kit.context["positions"] = [{"symbol": "BTC-USD", "asset_class": "crypto", "quantity": "0.00000164", "average_cost": "75693.78"}]
        out = load_starter("spot_quotes").decide(kit, {"symbols": ["BTC-USD"]})
        self.assertEqual([i["side"] for i in out["intents"]], ["buy"], "12 cents of BTC is dust: bid as if flat")
        kit.context["positions"] = [{"symbol": "BTC-USD", "asset_class": "crypto", "quantity": "0.00049996", "average_cost": "75000"}]
        offer = load_starter("spot_quotes").decide(kit, {"symbols": ["BTC-USD"]})["intents"][0]
        self.assertEqual((offer["side"], offer["quantity"]), ("sell", "0.000499"), "rounded down, never above the holding")

    def test_the_favorites_starter_rests_no_bids_on_liquid_longshots_one_per_event(self):
        kit = FakeKit()
        board = [
            {"ticker": "KXFEDMENTION-26SEP16-TARIFF", "title": "Powell says tariff", "status": "active", "close_time": "2026-09-16T20:00:00Z", "yes_bid": "0.04", "yes_ask": "0.06", "volume_24h": "25000"},
            {"ticker": "KXFEDMENTION-26SEP16-RECESSION", "title": "Powell says recession", "status": "active", "close_time": "2026-09-16T20:00:00Z", "yes_bid": "0.03", "yes_ask": "0.05", "volume_24h": "20000"},
            {"ticker": "KXRAIN-26SEP16-PVD", "title": "Rain in Providence", "status": "active", "close_time": "2026-09-17T04:00:00Z", "yes_bid": "0.07", "yes_ask": "0.08", "volume_24h": "19000"},
            {"ticker": "KXMLBGAME-26SEP16NYYBOS-NYY", "title": "Yankees", "status": "active", "close_time": "2026-09-17T02:00:00Z", "yes_bid": "0.55", "yes_ask": "0.57", "volume_24h": "90000"},
            {"ticker": "KXTHIN-26SEP16-X", "title": "thin", "status": "active", "close_time": "2026-09-16T20:00:00Z", "yes_bid": "0.02", "yes_ask": "0.05", "volume_24h": "10"},
        ]
        kit.kalshi_markets = lambda max_close_hours=36, pages=5: list(board)
        out = load_starter("kalshi_favorites").decide(kit, {})
        bids = out["intents"]
        self.assertEqual([b["instrument"]["market_id"] for b in bids], ["KXFEDMENTION-26SEP16-TARIFF", "KXRAIN-26SEP16-PVD"], "one per event; the favorite game and the thin market are skipped")
        self.assertEqual(bids[1]["limit_price"], "0.92", "a one-cent spread joins the best NO bid rather than taking")
        bid = bids[0]
        self.assertEqual((bid["instrument"]["right"], bid["side"], bid["limit_price"], bid["post_only"]), ("no", "buy", "0.95", True))
        self.assertIn("longshots resolve YES less often", bid["rationale"])
        kit.context["open_orders"] = [{"order_id": "ord-old", "strategy": "kalshi_favorites", "market_id": "KXFEDMENTION-26SEP16-TARIFF", "submitted_at": "2026-09-16T02:00:00Z"}]
        again = load_starter("kalshi_favorites").decide(kit, {})
        self.assertEqual(again["cancels"], ["ord-old"], "a stale bid is requoted")

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



class LateDeskBootstrapTests(StrategyCase):
    def test_a_desk_that_appears_after_the_first_tick_still_gets_its_starters(self):
        """The evolution loop breeds a child at night; the child trades from its first tick, not
        from the next restart."""
        self.strategies.config["starters"] = True
        self.strategies.tick(self.service.manifests, NOW)
        self.assertIn("hourly_ranges", self.strategies.store.for_desk(self.manifest.id))
        child = manifest(id="scholes-9", family="ranges", parent_id="scholes", capital={"mode": "shadow", "usd": "150"})
        self.service.manifests[child.id] = child
        self.strategies.tick(self.service.manifests, NOW)
        self.assertIn("hourly_ranges", self.strategies.store.for_desk("scholes-9"))
        self.assertIn("hourly_quotes", self.strategies.store.for_desk("scholes-9"))
        deployed_twice = self.strategies.store.for_desk(self.manifest.id)["hourly_ranges"].get("deployed_at")
        self.strategies.tick(self.service.manifests, NOW)
        self.assertEqual(self.strategies.store.for_desk(self.manifest.id)["hourly_ranges"].get("deployed_at"), deployed_twice, "never twice")


class HeldLegQuoteTests(unittest.TestCase):
    def test_a_filled_leg_is_a_position_and_is_not_quoted_again(self):
        kit = FakeKit()
        kit.context["positions"] = [
            {"asset_class": "event", "market_id": "KXBTC-26SEP1600-B75950", "symbol": "KXBTC-26SEP1600-B75950", "right": "yes", "quantity": "40"}
        ]
        out = load_starter("hourly_quotes").decide(kit, {"buckets": 1, "spread": 0.04})
        self.assertEqual([i["instrument"]["right"] for i in out["intents"]], ["no"], "the YES leg filled; only NO is still quoted")


if __name__ == "__main__":
    unittest.main()


class PromotionTests(StrategyCase):
    def setUp(self):
        super().setUp()
        self.log_events = []

        class Event:
            def __init__(self, payload, at=None):
                self.payload, self.at = payload, at

        def read(stream=None, kind=None, limit=None, newest=False):
            return [Event(p, *rest) for s, k, p, *rest in self.log_events if (stream is None or s == stream) and k == kind]

        self.service.log.read = read
        self.service.gateway = type("G", (), {"open_orders": lambda g, desk_id: []})()
        self.live = manifest(id="scholes", parent_id=None, capital={"mode": "live", "usd": "142"})
        self.other = manifest(id="scholes-3")
        for m in (self.live, self.other):
            self.service.manifests[m.id] = m
            self.manager.files[m.id] = {"edge.py": "def decide(kit, params):\n    return []\n"}
        self.strategies.deploy(self.live, "edge", 600, {"min_edge": 0.02, "vol_bars": 24, "window": "1h"}, house=True)
        self.strategies.deploy(self.manifest, "edge", 600, {"min_edge": 0.0, "vol_bars": 36, "window": "5m"}, house=True)
        self.strategies.deploy(self.other, "edge", 600, {"min_edge": 0.01, "vol_bars": 32, "window": "15m"}, house=True)

    def trades(self, desk, pnl_each, count, *, price="0.50", days=3, first_day=16):
        """`count` settled positions of 10 contracts at `price`, dealt across `days` days from
        Sept `first_day`: the evidence gate resamples days, so a record needs more than one."""
        for n in range(len(self.log_events), len(self.log_events) + count):
            at = f"2026-09-{first_day + n % days:02d}T05:00:00.000Z"
            ticker = f"KXA-{desk}-{n}"
            self.log_events += [
                (f"desk:{desk}", "desk.intent", {"intent_id": f"oi-{desk}-{n}", "session_id": f"{desk}:20260916-0400:strategy:edge"}, at),
                (f"broker:{desk}", "broker.order", {"order_id": f"ord-{desk}-{n}", "intent_id": f"oi-{desk}-{n}"}, at),
                (f"broker:{desk}", "broker.fill", {"order_id": f"ord-{desk}-{n}", "quantity": "10", "price": price, "fee": "0"}, at),
                (f"desk:{desk}", "desk.outcome", {"pnl": pnl_each, "rationale_excerpt": "[strategy edge] x", "instrument": f"event:{ticker}:kalshi:no:{ticker}",
                                                  "entry_price": price, "quantity": "10", "entry_fees": "0"}, at),
            ]

    def test_the_best_shadow_variant_takes_the_live_desk_and_the_others_are_dealt_around_it(self):
        self.trades("scholes-2", "1.00", 30)   # +1 on 5 of notional, every day: +0.20 per dollar
        self.trades("scholes-3", "0.10", 30)   # +0.02 per dollar
        self.trades("scholes", "-0.50", 30)    # the live setting loses
        out = self.strategies.promote(self.service.manifests, AFTER)
        self.assertEqual([(p["desk_id"], p["strategy"], p["from"]) for p in out], [("scholes", "edge", "scholes-2")])
        self.assertEqual(Decimal(out[0]["lower_bound"]), Decimal("0.2"))
        live_row = self.strategies.store.for_desk("scholes")["edge"]
        self.assertEqual(live_row["params"], {"min_edge": 0.0, "vol_bars": 36, "window": "5m"})
        self.assertEqual((live_row["promoted_at"], live_row["promoted_from"]), (AFTER, "scholes-2"))
        self.assertEqual(self.strategies.store.for_desk("scholes-2")["edge"]["params"], {"min_edge": 0.0, "vol_bars": 36, "window": "5m"}, "the winner stays as the control")
        dealt = self.strategies.store.for_desk("scholes-3")["edge"]
        self.assertEqual(dealt["params"]["window"], "5m", "choices are copied")
        self.assertTrue(27 <= dealt["params"]["vol_bars"] <= 45 and dealt["params"]["vol_bars"] != 36 or dealt["params"]["vol_bars"] == 36, "dials move by up to a quarter")
        self.assertEqual(dealt["promoted_at"], AFTER)
        kinds = [(s, k, p.get("purpose")) for s, k, p, *_ in self.service.log.events if k == "desk.code_run" and "promoted" in str(p.get("purpose"))]
        self.assertEqual(kinds, [("desk:scholes", "desk.code_run", "strategy edge promoted: scholes-2's settings take the live desk")])
        self.assertTrue(any("promotion: scholes/edge adopts scholes-2" in text for _, text in self.service.alerts))
        # The next hour: nothing changed, the live record is measured since the promotion, so no second promotion.
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [], "once an hour")
        self.strategies._last_promotion_at = None
        self.assertEqual(self.strategies.promote(self.service.manifests, "2026-09-18T08:30:00.000Z"), [], "the live setting is now the winner's")

    def test_no_promotion_without_the_evidence_gate_and_a_lower_bound_over_the_live_return(self):
        self.trades("scholes-2", "1.00", 24)
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [], "24 settlements are not the gate's 25")
        self.strategies._last_promotion_at = None
        self.trades("scholes-3", "1.00", 30, days=1)
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [], "thirty winners in one day are one block, not evidence")
        self.strategies._last_promotion_at = None
        self.trades("scholes-2", "1.00", 1)
        self.trades("scholes", "1.50", 12)  # live earns +0.30 per dollar; the shadow's lower bound is +0.20
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [])
        self.strategies._last_promotion_at = None
        self.trades("scholes-2", "3.00", 30)  # +0.60 per dollar on top: a lower bound near +0.41
        out = self.strategies.promote(self.service.manifests, AFTER)
        self.assertEqual([p["from"] for p in out], ["scholes-2"])
        self.assertGreater(Decimal(out[0]["lower_bound"]), Decimal("0.30"))

    def test_a_positive_return_with_one_bad_day_is_not_promoted(self):
        """The old gate read the point estimate: +0.027 per dollar after twelve settlements
        promoted. Resampling the days finds the bad one in more than a fifth of the draws."""
        self.trades("scholes-2", "1.00", 20, days=2)                # +0.20 per dollar on Sept 16 and 17
        self.trades("scholes-2", "-1.60", 10, days=1, first_day=18)  # -0.32 per dollar on Sept 18
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [])
        record = self.strategies.record("scholes-2", "edge", since=NOW)
        self.assertGreater(Decimal(record["settled_pnl_usd"]), 0)
        self.assertEqual(self.strategies.assess(record)["passes"], False)

    def test_a_shadow_favorites_variant_with_six_wins_in_six_is_not_promoted(self):
        """Sept 17, 2026: the promotion gate on the box was 6 settled with a positive return. At
        0.93 a breakeven favorite wins six in a row 65% of the time."""
        self.strategies.config["promotion"] = {"min_settled": 6}
        self.trades("scholes-2", "0.70", 6, price="0.93")
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [])
        self.strategies._last_promotion_at = None
        self.trades("scholes-3", "0.70", 42, price="0.93")
        self.trades("scholes-3", "-9.30", 3, price="0.93")  # +1.50 in all, three losses in 45: over breakeven's 7%
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [])
        self.strategies._last_promotion_at = None
        self.trades("scholes-2", "0.70", 38, price="0.93")
        self.trades("scholes-2", "-9.30", 1, price="0.93")  # one loss in 45
        self.assertEqual([p["from"] for p in self.strategies.promote(self.service.manifests, AFTER)], ["scholes-2"])

    def test_the_forward_record_counts_only_positions_opened_since_a_deployment(self):
        """leap: foundry -- settlements are dated when they settle; a candidate deployed at 14:20
        must not be credited with the positions the old settings opened at noon."""
        from ltcm.broker import Instrument

        since = "2026-09-16T14:20:00.000Z"

        def position(n, opened, settled, held, pnl="0.10", fill_at=None):
            leg = Instrument(asset_class="event", symbol=f"KXA-{n}", venue="kalshi", right="no", market_id=f"KXA-{n}")
            self.log_events += [
                ("desk:scholes-2", "desk.intent", {"intent_id": f"oi-f{n}", "session_id": "scholes-2:20260916-1200:strategy:edge"}, opened),
                ("broker:shadow", "broker.order", {"order_id": f"ord-f{n}", "intent_id": f"oi-f{n}"}, opened),
                ("broker:shadow", "broker.fill", {"order_id": f"ord-f{n}", "quantity": "10", "price": "0.90", "fee": "0.01", "instrument": leg.to_dict()}, fill_at or opened),
                ("desk:scholes-2", "desk.outcome", {"pnl": pnl, "rationale_excerpt": "[strategy edge] NO", "instrument": leg.key, "held_for_hours": held}, settled),
            ]

        for n in range(5):  # the old settings' positions, opened at noon, settling at three
            position(n, "2026-09-16T12:00:00.000Z", "2026-09-16T15:00:00.000Z", "3.0")
        plain = self.strategies.record("scholes-2", "edge", since=since)
        self.assertEqual(plain["settled"], 5, "dated by settlement, the old positions count in the plain record")
        forward = self.strategies.record("scholes-2", "edge", since=since, opened_since=True)
        self.assertEqual((forward["settled"], forward["fills"], float(forward["settled_pnl_usd"])), (0, 0, 0.0))
        for n in range(5, 8):  # opened after the deployment
            position(n, "2026-09-16T14:30:00.000Z", "2026-09-16T16:30:00.000Z", "2.0", pnl="0.20")
        position(8, "2026-09-16T14:22:00.000Z", "2026-09-16T16:22:00.000Z", "2.0")  # rounding could put it before
        position(9, "2026-09-16T14:30:00.000Z", "2026-09-16T16:30:00.000Z", None)  # its opening is unknown
        position(10, "2026-09-16T14:40:00.000Z", "2026-09-16T16:40:00.000Z", "2.0", fill_at="2026-09-16T12:00:00.000Z")  # no fill since
        forward = self.strategies.record("scholes-2", "edge", since=since, opened_since=True)
        self.assertEqual((forward["settled"], forward["wins"], forward["settled_pnl_usd"]), (3, 3, "0.60"))
        self.assertEqual((forward["fills"], forward["fees_usd"]), (5, "0.05"))

    def test_promotion_leaves_a_foundry_adoption_and_its_shadow_trials_alone(self):
        """leap: foundry -- an adoption resets the live evidence; until Sept 16, 2026 the hourly
        promotion read that as "no live score" and swapped the settings within the hour, and it
        re-dealt the shadow row the Foundry was still proving."""
        store = self.strategies.store
        store.update("scholes", "edge", params={"min_edge": 0.03, "vol_bars": 20, "window": "1h"}, promoted_at="2026-09-16T04:30:00.000Z", foundry_id="fdy-1-live")
        store.update("scholes-3", "edge", params={"min_edge": 0.05, "vol_bars": 30, "window": "15m"}, promoted_at="2026-09-16T04:30:00.000Z", foundry_id="fdy-2-trial")
        self.trades("scholes-2", "1.00", 30)
        self.assertEqual(self.strategies.promote(self.service.manifests, AFTER), [], "no live record since the adoption yet")
        self.assertEqual(store.for_desk("scholes")["edge"]["params"], {"min_edge": 0.03, "vol_bars": 20, "window": "1h"})
        self.strategies._last_promotion_at = None
        self.trades("scholes", "-0.50", 12)  # measured, and losing: now the family's record decides
        out = self.strategies.promote(self.service.manifests, "2026-09-18T07:00:00.000Z")
        self.assertEqual([p["from"] for p in out], ["scholes-2"])
        live = store.for_desk("scholes")["edge"]
        self.assertEqual(live["params"], {"min_edge": 0.0, "vol_bars": 36, "window": "5m"})
        self.assertIsNone(live["foundry_id"], "a promotion's settings are its own")
        trial = store.for_desk("scholes-3")["edge"]
        self.assertEqual(trial["params"], {"min_edge": 0.05, "vol_bars": 30, "window": "15m"}, "the Foundry's trial is not re-dealt")
        self.assertEqual(trial["promoted_at"], "2026-09-16T04:30:00.000Z")

    def test_bootstrap_leaves_a_promoted_setting_alone(self):
        from ltcm.strategies import STARTERS_DIR
        self.strategies.config["starters"] = True
        self.strategies.store.update("scholes", "hourly_ranges", house=True, enabled=True, params={"min_edge": 0.0, "vol_bars": 36}, cadence_seconds=300, promoted_at=LATER, runs=3)
        self.manager.files["scholes"]["hourly_ranges.py"] = (STARTERS_DIR / "hourly_ranges.py").read_text()
        self.strategies.bootstrap({"scholes": self.live})
        self.assertEqual(self.strategies.store.for_desk("scholes")["hourly_ranges"]["params"], {"min_edge": 0.0, "vol_bars": 36}, "the house params do not overwrite a promotion")


class GenomeStrategyTests(StrategyCase):
    def test_install_saves_the_code_and_deploys_it_and_the_genome_reaches_every_desk_of_the_family(self):
        spec = {"name": "sharper_vol", "cadence_seconds": 600, "params": {"window": "5m"}, "code": "def decide(kit, params):\n    return []\n"}
        row = self.strategies.install(self.manifest, spec, note="lab experiment exp-1")
        self.assertEqual((row["name"], row["cadence_seconds"], row["params"], row["note"]), ("sharper_vol", 600, {"window": "5m"}, "lab experiment exp-1"))
        self.assertIn("sharper_vol.py", self.manager.files["scholes-2"])
        # An adopted strategy in the genome lands on a desk of the family that lacks it.
        other = manifest(id="scholes-3")
        self.service.manifests[other.id] = other
        self.manager.files["scholes-3"] = {}
        self.service.evolution = type("E", (), {"genome": lambda self, family: [{"experiment_id": "exp-1", "change": {"strategy": spec}}] if family == "ranges" else []})()
        self.strategies.config["starters"] = True
        deployed = self.strategies.bootstrap({other.id: other, self.manifest.id: self.manifest})
        self.assertIn("scholes-3/sharper_vol", deployed)
        self.assertNotIn("scholes-2/sharper_vol", deployed, "already there")
        self.assertEqual(self.strategies.store.for_desk("scholes-3")["sharper_vol"]["note"], "house genome: experiment exp-1")
