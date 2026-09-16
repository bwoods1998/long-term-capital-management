"""The Foundry: candidates, parallel backtests, out-of-sample selection, shadow deployment and
the fast-track to live (leap: foundry). No network: sandboxes, the model and records are fakes."""

from __future__ import annotations

import ast
import json
import re
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.foundry import (
    Foundry,
    categorical_pool,
    jitter_variants,
    literal_defaults,
    parse_result,
    runner_code,
    split_evidence,
)
from ltcm.sandbox import SandboxManager
from ltcm.strategies import STARTERS_DIR, Strategies, StrategyStore
from ltcm.tests.test_service import ServiceCase
from ltcm.tests.test_strategies import FakeService, Run, manifest

NOW = "2026-09-16T14:20:00.000Z"
SOURCE = (STARTERS_DIR / "kalshi_favorites.py").read_text(encoding="utf-8")
GOOD_CODE = 'DEFAULTS = {"yes_max": 0.1}\n\n\ndef decide(kit, params):\n    return []\n'


def epoch(at):
    return datetime.strptime(at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


def pnls(in_sample, out_of_sample, n=100, spread=0.05):
    """A run's closed positions: the first 66 of 100 earn `in_sample` each, the rest
    `out_of_sample`, alternating a little either side so the interval has a width."""
    cut = int(n * 66 / 100)
    return [round((in_sample if i < cut else out_of_sample) + (spread if i % 2 else -spread), 6) for i in range(n)]


def result_line(trade_pnls, *, trades=None, unsupported=None, **extra):
    report = {
        "strategy": "x",
        "trades": len(trade_pnls) if trades is None else trades,
        "notional_usd": float(len(trade_pnls)),
        "pnl_usd": round(sum(trade_pnls), 6),
        "trade_pnls": trade_pnls,
        "errors": 0,
        **extra,
    }
    if unsupported:
        report["unsupported"] = unsupported
    return "engine chatter\nBACKTEST-RESULT " + json.dumps(report) + "\n"


def spec_of(code):
    """The spec a runner program carries, read back without running it."""
    found = re.search(r"^SPEC = json\.loads\((.*)\)$", code, re.M)
    return json.loads(ast.literal_eval(found.group(1)))


class Log:
    def __init__(self):
        self.events = []

    def append(self, stream, kind, payload, *, id=None, at=None, public=None):
        self.events.append(SimpleNamespace(stream=stream, kind=kind, payload=payload, id=id, at=at))
        return self.events[-1]

    def read(self, *, stream=None, kind=None, limit=1000, newest=False, **_):
        return [e for e in self.events if (stream is None or e.stream == stream) and (kind is None or e.kind == kind)][-limit:]

    def kinds(self, kind):
        return [e for e in self.events if e.kind == kind]


class Manager:
    """Sandboxes: a strategy run answers quietly, a backtest answers from the test's script."""

    def __init__(self):
        self.files = {}
        self.specs = []
        self.backtests = []
        self.script = lambda spec: result_line(pnls(0.0, 0.0))
        self._lock = threading.Lock()
        self.active = set()
        self.overlap = []
        self.delay = 0.0
        self.refuse = set()

    def toolbox_files(self, desk_id):
        return dict(self.files.get(desk_id, {}))

    def toolbox_save(self, desk_id, name, code, purpose):
        self.files.setdefault(desk_id, {})[f"{name}.py"] = code

    def toolbox_remove(self, desk_id, name):
        return self.files.get(desk_id, {}).pop(f"{name}.py", None) is not None

    def run(self, desk_id, code, *, purpose="", save_as=None, timeout=60):
        if not purpose.startswith("foundry backtest"):
            if purpose.replace("strategy ", "", 1) in self.refuse:
                return Run('STRATEGY-RESULT {"intents": [], "error": "Traceback: boom"}')
            return Run('STRATEGY-RESULT {"intents": [], "notes": "quiet"}')
        with self._lock:
            if desk_id in self.active:
                self.overlap.append(desk_id)
            self.active.add(desk_id)
        try:
            spec = spec_of(code)
            with self._lock:
                self.specs.append(spec)
                self.backtests.append((desk_id, purpose, timeout))
            if self.delay:
                time.sleep(self.delay)
            return Run(self.script(spec))
        finally:
            with self._lock:
                self.active.discard(desk_id)


class Records(Strategies):
    """The runner with a scripted forward record per (desk, strategy)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = {}
        self.record_calls = []

    def record(self, desk_id, name, since=None):
        self.record_calls.append((desk_id, name, since))
        return dict(self.records.get((desk_id, name), {}))


class Provider:
    def __init__(self):
        self.calls = []
        self.spent = Decimal("0")
        self.replies = {}
        self.raises = None

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        if self.raises is not None:
            raise self.raises
        index = int(kwargs["request_key"].rsplit(":", 1)[1])
        return SimpleNamespace(output_text=self.replies.get(index, ""), cost_usd=Decimal("0.07"))

    def spent_today(self, desk_id=None):
        return self.spent


def reply(name, code=GOOD_CODE, params=None, hypothesis="Rest only where the book is two-sided."):
    return "Here it is:\n" + json.dumps({"name": name, "code": code, "params": params or {}, "hypothesis": hypothesis})


class FoundryCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = [epoch(NOW)]
        self.live = manifest(id="mullins", family="kalshi", parent_id=None, capital={"mode": "live", "usd": "142"})
        self.shadows = [manifest(id=f"mullins-{n}", family="kalshi", parent_id="mullins") for n in (2, 3, 4)]
        self.manifests = {m.id: m for m in [self.live, *self.shadows]}
        self.manager = Manager()
        self.log = Log()
        self.service = FakeService(self.manager, self.manifests)
        self.service.log = self.log
        self.service.now = lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(self.clock[0]))
        self.strategies = Records(self.service, path=self.root / "strategies.json", config={"starters": False})
        from ltcm.strategies import _sha

        params = {"mullins": {}, "mullins-2": {"yes_max": 0.05}, "mullins-3": {"yes_min": 0.05, "yes_max": 0.15}, "mullins-4": {"max_hours": 12, "min_volume_24h": 5000}}
        for desk_id, desk_params in params.items():
            self.manager.files[desk_id] = {"kalshi_favorites.py": SOURCE}
            self.strategies.store.update(
                desk_id, "kalshi_favorites", params=desk_params, cadence_seconds=900, house=True, enabled=True,
                code_sha256=_sha(SOURCE), deployed_at="2026-09-16T00:00:00.000Z", runs=10,
            )
        self.strategies.records = {
            ("mullins", "kalshi_favorites"): {"settled": 12, "settled_pnl_usd": "-50", "filled_notional_usd": "500", "fills": 12},
            ("mullins-2", "kalshi_favorites"): {"settled": 10, "settled_pnl_usd": "5", "filled_notional_usd": "50", "fills": 10},
            ("mullins-3", "kalshi_favorites"): {"settled": 10, "settled_pnl_usd": "-3", "filled_notional_usd": "60", "fills": 10},
            ("mullins-4", "kalshi_favorites"): {"settled": 10, "settled_pnl_usd": "-3", "filled_notional_usd": "60", "fills": 10},
        }
        self.equity = {"mullins": Decimal("400"), "mullins-2": Decimal("150"), "mullins-3": Decimal("100"), "mullins-4": Decimal("80")}
        self.alerts = []
        self.provider = None

    def foundry(self, provider=None, **config):
        return Foundry(
            log=self.log,
            strategies=self.strategies,
            sandboxes=lambda: self.manager,
            provider=provider,
            manifests=lambda: self.manifests,
            state_path=self.root / "foundry.json",
            clock=lambda: self.clock[0],
            alert=lambda level, text: self.alerts.append((level, text)),
            config={"families": ["kalshi"], "sandboxes": 4, **config},
            equity=lambda desk_id: self.equity.get(desk_id),
        )

    def row(self, desk_id, name="kalshi_favorites"):
        return self.strategies.store.for_desk(desk_id).get(name)


# --------------------------------------------------------------------------- candidates
class CandidateTests(FoundryCase):
    def test_candidates_are_deterministic_per_cycle_and_explore_inside_the_bounds(self):
        foundry = self.foundry()
        defaults = literal_defaults(SOURCE)
        self.assertEqual(defaults["yes_max"], 0.10)

        frozen = foundry.config["frozen_params"]

        def build(cycle):
            baselines, best, records = foundry.baselines(cycle, "kalshi", "kalshi_favorites", SOURCE, self.live, self.shadows, defaults, frozen)
            variants = foundry.param_candidates(cycle, "kalshi", "kalshi_favorites", SOURCE, defaults, best, baselines, frozen)
            return baselines, best, records, variants

        baselines, best, records, variants = build(7)
        self.assertEqual([b["label"] for b in baselines], ["live mullins", "shadow mullins-2"], "the live settings and the best shadow's")
        self.assertEqual(best, {"yes_max": 0.05}, "the shadow with the better forward return is the best known")
        self.assertTrue(any("mullins-3/kalshi_favorites" in line for line in records))
        self.assertEqual(len(variants), 10)
        self.assertEqual([v["params"] for v in build(7)[3]], [v["params"] for v in variants], "the same cycle deals the same hand")
        self.assertNotEqual([v["params"] for v in build(8)[3]], [v["params"] for v in variants], "the next cycle deals another")
        full = [{**defaults, **v["params"]} for v in variants]
        for params in full:
            self.assertTrue(0.025 <= params["yes_max"] <= 0.075, params["yes_max"])
            self.assertTrue(1000 * 0.5 <= params["min_volume_24h"] <= 1000 * 1.5)
            self.assertIsInstance(params["min_volume_24h"], int)
            self.assertIsNone(params["notional_usd"], "size is never a candidate's")
            self.assertEqual((params["max_new"], params["no_max"]), (3, 0.98), "nor order counts and price guards")
        self.assertIn(False, [p["maker"] for p in full], "a choice from the family's variants is flipped")
        self.assertTrue(all(p["maker"] in (True, False) for p in full))
        self.assertEqual(len({json.dumps(p, sort_keys=True) for p in full}), 10, "no duplicates")
        self.assertEqual(len({v["id"] for v in variants}), 10)

    def test_jitter_helpers_keep_integers_fractions_and_frozen_keys(self):
        base = {"count": 3, "fraction": 0.9, "size": 25.0, "mode": "a", "flag": True}
        pool = categorical_pool([{"mode": "b"}, {"flag": False}], {"mode": "a", "flag": True})
        self.assertEqual(pool, {"flag": [True, False], "mode": ["a", "b"]})
        out = jitter_variants(base, seed="s", count=6, frozen=["size"], pool=pool)
        self.assertEqual(len(out), 6)
        for params, how in out:
            self.assertIsInstance(params["count"], int)
            self.assertGreaterEqual(params["count"], 1)
            self.assertLessEqual(params["fraction"], 1.0)
            self.assertEqual(params["size"], 25.0)
            self.assertTrue(0.1 <= how["scale"] <= 0.5)
        self.assertEqual(out, jitter_variants(base, seed="s", count=6, frozen=["size"], pool=pool))

    def test_invalid_model_code_is_rejected_before_any_backtest(self):
        provider = Provider()
        provider.replies = {
            0: reply("kalshi_favorites_f1", code="import subprocess\n\ndef decide(kit, params):\n    return []\n"),
            1: reply("kalshi_favorites_f1_2"),
        }
        summary = self.foundry(provider).cycle(NOW)
        self.assertEqual(summary["code"]["asked"], 2)
        self.assertEqual(summary["code"]["valid"], 1)
        self.assertIn("subprocess", summary["code"]["rejected"][0])
        tested = {spec["strategy"] for spec in self.manager.specs}
        self.assertIn("kalshi_favorites_f1_2", tested)
        self.assertNotIn("kalshi_favorites_f1", tested, "refused code never reaches a sandbox")
        call = provider.calls[0]
        self.assertEqual((call["profile"], call["desk_id"], call["reasoning_effort"], call["max_output_tokens"]), ("k3", "foundry", "high", 16000))
        self.assertEqual(call["desk_cap_usd_per_day"], "25")
        packet = call["items"][1]["content"]
        self.assertIn("## Baseline backtests", packet)
        self.assertIn("out of sample", packet)
        self.assertIn("def decide(kit, params)", packet, "the source rides along")
        self.assertIn("mullins-2/kalshi_favorites", packet, "and the family's forward record")
        self.assertIn("kit.kalshi_markets", call["items"][0]["content"], "and the kit")

        foundry = self.foundry(provider)
        for bad, reason in (
            ({"code": GOOD_CODE}, "no hypothesis"),
            ({"code": "def decide(kit, params):\n    return [\n", "hypothesis": "x"}, "does not compile"),
            ({"code": "print(1)\n", "hypothesis": "x"}, "decide"),
            ({"code": GOOD_CODE, "hypothesis": "x", "params": {"nested": {"a": 1}}}, "params"),
            ({"code": GOOD_CODE + "#" * 20000, "hypothesis": "x"}, "at most"),
        ):
            with self.assertRaises(ValueError) as caught:
                foundry.validate_code(bad, "kalshi_favorites_f9", self.live, 900)
            self.assertIn(reason, str(caught.exception))
        spec, hypothesis = foundry.validate_code({"code": GOOD_CODE, "hypothesis": "h", "params": {"notional_usd": 99, "yes_max": 0.2, "gone": None}}, "kalshi_favorites_f9", self.live, 900)
        self.assertEqual(spec["params"], {"yes_max": 0.2}, "size and nulls are dropped")

    def test_budget_exhaustion_skips_code_candidates(self):
        provider = Provider()
        provider.spent = Decimal("25.00")
        summary = self.foundry(provider).cycle(NOW)
        self.assertEqual(provider.calls, [])
        self.assertIn("budget", summary["code"]["skipped"])
        self.assertEqual(summary["candidates"], 10, "the settings candidates still run")
        self.assertEqual(len(self.manager.specs), 12)

        from ltcm.provider import BudgetExceeded

        provider = Provider()
        provider.raises = BudgetExceeded("provider_desk_cap")
        self.clock[0] += 3600
        summary = self.foundry(provider).cycle()
        self.assertIn("budget", summary["code"]["skipped"])
        self.assertEqual(summary["code"]["valid"], 0)


# --------------------------------------------------------------------------- backtests and selection
class BacktestTests(FoundryCase):
    def test_every_candidate_runs_in_its_own_sandbox_side_by_side(self):
        self.manager.delay = 0.02
        summary = self.foundry(sandboxes=3).cycle(NOW)
        self.assertEqual(summary["backtested"], 12)
        self.assertEqual(self.manager.overlap, [], "one backtest per sandbox at a time")
        desks = {desk for desk, _, _ in self.manager.backtests}
        self.assertTrue(desks <= {"foundry-0", "foundry-1", "foundry-2"})
        self.assertGreater(len(desks), 1, "in parallel")
        self.assertTrue(all(timeout == 900 for _, _, timeout in self.manager.backtests))
        spec = self.manager.specs[0]
        self.assertEqual((spec["start"], spec["end"], spec["step_minutes"]), ("2026-09-11T14:00:00Z", "2026-09-16T14:00:00Z", 15))
        self.assertEqual((spec["fill_model"], spec["learning_usd"], spec["max_markets"], spec["seed"]), ("conservative", 10, 3000, 7))
        self.assertIn("def decide(", spec["code"])
        hypothesis = self.log.kinds("lab.hypothesis")
        self.assertEqual(len(hypothesis), 1)
        self.assertEqual(hypothesis[0].payload["winner"], "no winner")
        self.assertEqual(hypothesis[0].payload["hypothesis_id"], "foundry-1")

    def test_an_engine_that_cannot_backtest_the_strategy_stops_the_cycle_early(self):
        provider = Provider()
        self.manager.script = lambda spec: result_line([], unsupported="needs forecasts")
        self.manager.delay = 0.05
        summary = self.foundry(provider, sandboxes=1).cycle(NOW)
        self.assertEqual(provider.calls, [], "no model is paid for a strategy the engine cannot replay")
        self.assertIn("cannot backtest", summary["code"]["skipped"])
        self.assertEqual(summary["qualified"], 0)
        self.assertLess(len(self.manager.specs), 12)

    def test_selection_reads_only_out_of_sample_evidence(self):
        foundry = self.foundry()

        def candidate(cid, kind, trade_pnls, **extra):
            report = parse_result(result_line(trade_pnls, **extra))
            return {"id": cid, "kind": kind, "label": cid, "report": report, "evidence": foundry.evidence(report), "error": None}

        baseline = candidate("base", "baseline", pnls(0.1, 0.1))
        in_sample_only = candidate("in-sample", "params", pnls(1.0, -0.05))
        good = candidate("good", "params", pnls(-0.2, 0.2))
        better = candidate("better", "code", pnls(-0.5, 0.3))
        few_oos = candidate("few-oos", "params", pnls(0.5, 0.5, n=70))
        few_total = candidate("few-total", "params", pnls(0.5, 0.5), trades=50)
        inside_margin = candidate("margin", "params", pnls(0.5, 0.105))
        noisy = candidate("noisy", "params", pnls(0.5, 0.2, spread=3.0))
        qualified, reference = foundry.select([baseline, in_sample_only, good, better, few_oos, few_total, inside_margin, noisy])
        self.assertAlmostEqual(reference, 0.1, places=6)
        self.assertEqual([c["id"] for c in qualified], ["better", "good"], "ranked by out-of-sample return per dollar")
        self.assertIn("does not beat", in_sample_only["verdict"])
        self.assertIn("24 out-of-sample positions", few_oos["verdict"])
        self.assertIn("50 trades", few_total["verdict"])
        self.assertIn("does not beat", inside_margin["verdict"])
        self.assertIn("lower bound", noisy["verdict"])
        failed_baseline = {**baseline, "error": "exit 5: sandbox error"}
        self.assertEqual(foundry.select([failed_baseline, good, better])[0], [], "no measured baseline, no winner")
        self.assertIn("no baseline", good["verdict"])
        strict = self.foundry(min_ci_lower=0.35)
        self.assertEqual([c["id"] for c in strict.select([baseline, good, better])[0]], [], "the bound is configurable")

    def test_the_runner_compiles_and_the_result_line_is_the_last_marker(self):
        code = runner_code({"strategy": "kalshi_favorites", "code": SOURCE, "params": {"yes_max": 0.12}}, fraction=0.66)
        compile(code, "main.py", "exec")
        self.assertEqual(spec_of(code)["params"], {"yes_max": 0.12})
        self.assertIn("backtest.main([\"--spec\", path])", code)
        self.assertIn("def split_evidence(", code, "the split ships with the runner")
        self.assertLess(len(code), 40_000)
        self.assertIsNone(parse_result("no marker"))
        self.assertIsNone(parse_result("BACKTEST-RESULT {broken"))
        self.assertEqual(parse_result('BACKTEST-RESULT {"trades": 1}\nBACKTEST-RESULT {"trades": 2}\n'), {"trades": 2})
        split = split_evidence(pnls(0.0, 0.2), 100.0, 0.66)
        self.assertEqual((split["in_sample"]["trades"], split["out_of_sample"]["trades"]), (66, 34))
        self.assertAlmostEqual(split["out_of_sample"]["return_on_notional"], 0.2, places=6)
        self.assertGreater(split["out_of_sample"]["ci95_mean_pnl"][0], 0.15)
        engine = {"in_sample": {"trades": 1}, "out_of_sample": {"trades": 30, "pnl_usd": 3, "return_on_notional": 0.5, "ci95_mean_pnl": [0.01, 0.2]}}
        evidence = self.foundry().evidence({"trades": 90, "split": engine, "trade_pnls_dropped": 90})
        self.assertEqual(evidence["out_of_sample"]["return_on_notional"], 0.5, "the engine's own split is used when it sent one")


# --------------------------------------------------------------------------- deployment and fast-track
def settings_winner(spec):
    params = spec["params"]
    if spec["strategy"] == "kalshi_favorites" and params.get("maker") is False:
        return result_line(pnls(0.0, 0.2 + float(params.get("yes_max", 0.1))))
    return result_line(pnls(0.05, 0.05))


def code_winner(spec):
    if spec["strategy"] == "kalshi_favorites_f1":
        return result_line(pnls(0.0, 0.4))
    return result_line(pnls(0.05, 0.05))


class DeploymentTests(FoundryCase):
    def test_a_settings_winner_goes_to_the_worst_shadow_desk_and_never_the_live_desk(self):
        self.manager.script = settings_winner
        live_before = self.row("mullins")
        foundry = self.foundry()
        summary = foundry.cycle(NOW)
        self.assertEqual(summary["deployed_to"], "mullins-4", "-3 settled like mullins-3, but less equity")
        self.assertEqual(self.row("mullins"), live_before, "the live desk is never touched by a deployment")
        deployment = foundry.state()["deployments"][summary["winner"]]
        row = self.row("mullins-4")
        self.assertEqual(row["params"], deployment["params"])
        self.assertIs(row["params"]["maker"], False)
        self.assertEqual(row["foundry_id"], summary["winner"])
        self.assertEqual(row["promoted_at"], deployment["deployed_at"], "the forward record starts now and bootstrap leaves it alone")
        self.assertTrue(row["note"].startswith(f"foundry {summary['winner']}"))
        runs = [e for e in self.log.kinds("desk.code_run") if e.stream == "desk:mullins-4"]
        self.assertEqual(len(runs), 1)
        self.assertIn("shadow desk mullins-4", runs[0].payload["purpose"])
        self.assertEqual(runs[0].payload["session_id"].split(":strategy:")[1], "kalshi_favorites")
        event = self.log.kinds("lab.hypothesis")[0]
        self.assertEqual(event.stream, "lab")
        self.assertEqual(event.payload["winner"], summary["winner"])
        self.assertEqual(event.payload["deployed_to"], "mullins-4")
        for payload in (event.payload, runs[0].payload):
            text = json.dumps(payload)
            self.assertLess(len(text.encode("utf-8")), 3000)
            self.assertNotIn("<", text)
        # The next cycle's winner spares the desk still proving this one.
        self.clock[0] += 1800
        second = foundry.cycle()
        self.assertEqual(second["deployed_to"], "mullins-3")

    def test_a_code_winner_is_installed_on_the_worst_shadow_desk(self):
        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1"), 1: reply("kalshi_favorites_f1_2", hypothesis="Use <b>markup</b>.")}
        self.manager.script = code_winner
        foundry = self.foundry(provider)
        summary = foundry.cycle(NOW)
        self.assertEqual(summary["deployed_to"], "mullins-4")
        row = self.row("mullins-4", "kalshi_favorites_f1")
        self.assertTrue(row["enabled"])
        self.assertTrue(row["foundry_code"])
        self.assertEqual(row["cadence_seconds"], 900, "the live strategy's cadence")
        self.assertEqual(self.manager.files["mullins-4"]["kalshi_favorites_f1.py"], GOOD_CODE)
        self.assertTrue(self.row("mullins-4")["enabled"], "the shadow keeps its own strategy beside the candidate")
        self.assertNotIn("kalshi_favorites_f1", self.strategies.store.for_desk("mullins"))
        self.assertNotIn("<", json.dumps([e.payload for e in self.log.events]))
        # A later code winner on the same desk replaces the first, file and all.
        self.strategies.store.update("mullins-4", "kalshi_favorites_f1", foundry_id=summary["winner"])
        state = foundry.state()
        state["deployments"][summary["winner"]]["deployed_at"] = "2026-09-15T00:00:00.000Z"
        foundry._write(state)
        self.equity["mullins-2"] = Decimal("1")
        self.strategies.records[("mullins-2", "kalshi_favorites")] = {"settled": 1, "settled_pnl_usd": "-9"}
        self.strategies.records[("mullins-4", "kalshi_favorites")] = {"settled": 1, "settled_pnl_usd": "-90"}
        provider.replies = {0: reply("kalshi_favorites_f2"), 1: reply("kalshi_favorites_f2_2")}
        self.manager.script = lambda spec: result_line(pnls(0.0, 0.4)) if spec["strategy"] == "kalshi_favorites_f2" else result_line(pnls(0.05, 0.05))
        self.clock[0] += 1800
        second = foundry.cycle()
        self.assertEqual(second["deployed_to"], "mullins-4")
        self.assertNotIn("kalshi_favorites_f1", self.strategies.store.for_desk("mullins-4"))
        self.assertNotIn("kalshi_favorites_f1.py", self.manager.files["mullins-4"])
        self.assertEqual(foundry.state()["deployments"][summary["winner"]]["status"], "replaced")


class FastTrackTests(FoundryCase):
    def deploy_settings(self):
        self.manager.script = settings_winner
        foundry = self.foundry()
        summary = foundry.cycle(NOW)
        return foundry, summary["winner"]

    def test_fast_track_needs_both_the_backtest_bound_and_the_forward_record(self):
        foundry, fid = self.deploy_settings()
        deployment = foundry.state()["deployments"][fid]
        self.clock[0] += 3600
        key = ("mullins-4", "kalshi_favorites")
        self.strategies.records[key] = {"settled": 4, "settled_pnl_usd": "2"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "four settlements are not five")
        self.assertIn(("mullins-4", "kalshi_favorites", deployment["deployed_at"]), self.strategies.record_calls, "the record since deployment")
        self.strategies.records[key] = {"settled": 5, "settled_pnl_usd": "-0.01"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "a losing forward record never goes live")
        without_live = {k: v for k, v in self.manifests.items() if k != "mullins"}
        self.strategies.records[key] = {"settled": 5, "settled_pnl_usd": "0.40"}
        self.assertEqual(foundry.fast_track(without_live, []), [], "no live desk, no adoption")
        # A candidate whose backtest bound is not above zero trades in shadow but never goes live.
        state = foundry.state()
        state["deployments"][fid]["oos_ci_lower"] = 0.0
        foundry._write(state)
        self.assertEqual(foundry.fast_track(self.manifests, []), [])
        state["deployments"][fid]["oos_ci_lower"] = deployment["oos_ci_lower"]
        foundry._write(state)

        foundry.halted = lambda: True
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "nothing goes live while the kill switch is engaged")
        foundry.halted = None
        adopted = foundry.fast_track(self.manifests, [])
        self.assertEqual([(a["id"], a["live_desk_id"], a["from"]) for a in adopted], [(fid, "mullins", "mullins-4")])
        live = self.row("mullins")
        self.assertEqual(live["params"], deployment["params"])
        self.assertEqual((live["promoted_from"], live["foundry_id"]), ("mullins-4", fid))
        self.assertTrue(live["promoted_at"] > deployment["deployed_at"], "evidence resets at the adoption")
        self.assertEqual(foundry.state()["deployments"][fid]["status"], "live")
        self.assertTrue(any(level == "info" and f"adopts {fid}" in text for level, text in self.alerts))
        runs = [e for e in self.log.kinds("desk.code_run") if e.stream == "desk:mullins"]
        self.assertEqual(len(runs), 1)
        self.assertIn("takes live desk mullins", runs[0].payload["purpose"])
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "once")

    def test_a_setting_changed_under_the_candidate_is_superseded(self):
        foundry, fid = self.deploy_settings()
        self.strategies.store.update("mullins-4", "kalshi_favorites", params={"yes_max": 0.2}, promoted_at="2026-09-16T15:00:00.000Z")
        self.strategies.records[("mullins-4", "kalshi_favorites")] = {"settled": 9, "settled_pnl_usd": "3"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [])
        self.assertEqual(foundry.state()["deployments"][fid]["status"], "superseded")
        self.assertEqual(self.row("mullins")["params"], {})

    def test_a_code_candidate_is_installed_on_the_live_desk_and_replaces_its_parent(self):
        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1", params={"yes_max": 0.08}), 1: reply("kalshi_favorites_f1_2")}
        self.manager.script = code_winner
        foundry = self.foundry(provider)
        fid = foundry.cycle(NOW)["winner"]
        self.clock[0] += 7200
        self.strategies.records[("mullins-4", "kalshi_favorites_f1")] = {"settled": 6, "settled_pnl_usd": "1.20"}
        adopted = foundry.fast_track(self.manifests, [])
        self.assertEqual([a["kind"] for a in adopted], ["code"])
        row = self.row("mullins", "kalshi_favorites_f1")
        self.assertTrue(row["enabled"])
        self.assertEqual(row["params"], {"yes_max": 0.08})
        self.assertEqual((row["foundry_id"], row["promoted_from"]), (fid, "mullins-4"))
        self.assertEqual(self.manager.files["mullins"]["kalshi_favorites_f1.py"], GOOD_CODE)
        self.assertFalse(self.row("mullins")["enabled"], "the parent strategy is paused, never doubled")

    def test_settings_for_a_strategy_no_shadow_runs_travel_with_the_live_code(self):
        from ltcm.strategies import _sha

        live_code = 'DEFAULTS = {"yes_max": 0.1, "maker": True}\n\n\ndef decide(kit, params):\n    return []\n'
        self.manager.files["mullins"]["kalshi_favorites_f1.py"] = live_code
        self.strategies.store.update("mullins", "kalshi_favorites_f1", params={}, cadence_seconds=600, enabled=True, foundry_code=True, code_sha256=_sha(live_code))
        foundry = self.foundry()
        foundry._save(subject_index={"kalshi": 1})
        self.manager.script = lambda spec: (
            result_line(pnls(0.0, 0.3)) if spec["strategy"] == "kalshi_favorites_f1" and spec["params"].get("maker") is False else result_line(pnls(0.05, 0.05))
        )
        summary = foundry.cycle(NOW)
        self.assertEqual((summary["strategy"], summary["deployed_to"]), ("kalshi_favorites_f1", "mullins-4"))
        deployment = foundry.state()["deployments"][summary["winner"]]
        self.assertEqual(deployment["kind"], "code", "installed with the live desk's code")
        row = self.row("mullins-4", "kalshi_favorites_f1")
        self.assertEqual((row["params"], row["cadence_seconds"], row["foundry_code"]), (deployment["params"], 600, True))
        self.assertEqual(self.manager.files["mullins-4"]["kalshi_favorites_f1.py"], live_code)
        self.clock[0] += 7200
        self.strategies.records[("mullins-4", "kalshi_favorites_f1")] = {"settled": 5, "settled_pnl_usd": "0"}
        self.assertEqual(len(foundry.fast_track(self.manifests, [])), 1)
        live_row = self.row("mullins", "kalshi_favorites_f1")
        self.assertTrue(live_row["enabled"])
        self.assertEqual(live_row["params"], deployment["params"])
        self.assertTrue(self.row("mullins")["enabled"], "nothing else on the live desk is paused")

    def test_a_full_live_desk_makes_room_by_setting_aside_the_candidate_it_replaces(self):
        from ltcm.strategies import _sha

        for name in ("kalshi_extra", "kalshi_favorites_f1"):
            self.manager.files["mullins"][f"{name}.py"] = GOOD_CODE
            self.strategies.store.update("mullins", name, params={}, cadence_seconds=900, enabled=True, code_sha256=_sha(GOOD_CODE), foundry_code=name.endswith("_f1"))
        self.strategies.store.update("mullins", "kalshi_favorites", enabled=False)
        new_code = GOOD_CODE + "# sharper\n"
        self.manager.files["mullins-4"]["kalshi_favorites_f9.py"] = new_code
        self.strategies.store.update("mullins-4", "kalshi_favorites_f9", params={}, cadence_seconds=900, enabled=True, foundry_code=True, foundry_id="fdy-9-abc")
        foundry = self.foundry()
        foundry._add_deployment({
            "id": "fdy-9-abc", "family": "kalshi", "subject": "kalshi_favorites_f1", "strategy": "kalshi_favorites_f9", "kind": "code",
            "desk_id": "mullins-4", "deployed_at": "2026-09-16T10:00:00.000Z", "status": "shadow", "params": {"yes_max": 0.07},
            "code_sha256": _sha(new_code), "cadence_seconds": 900, "trades": 120, "oos_trades": 40, "oos_return": 0.2, "oos_ci_lower": 0.05,
        })
        self.strategies.records[("mullins-4", "kalshi_favorites_f9")] = {"settled": 8, "settled_pnl_usd": "2.5"}
        self.manager.refuse = {"kalshi_favorites_f9"}
        problems = []
        self.assertEqual(foundry.fast_track(self.manifests, problems), [])
        self.assertIn("not adopted", problems[0])
        self.assertTrue(self.row("mullins", "kalshi_favorites_f1")["enabled"], "a refused dry run puts the old candidate back")
        self.assertNotIn("kalshi_favorites_f9", self.strategies.store.for_desk("mullins"))
        self.assertEqual(self.manager.files["mullins"]["kalshi_favorites_f1.py"], GOOD_CODE)
        self.manager.refuse = set()
        adopted = foundry.fast_track(self.manifests, [])
        self.assertEqual([a["id"] for a in adopted], ["fdy-9-abc"])
        rows = self.strategies.store.for_desk("mullins")
        self.assertEqual(sorted(rows), ["kalshi_extra", "kalshi_favorites", "kalshi_favorites_f9"])
        self.assertEqual(rows["kalshi_favorites_f9"]["params"], {"yes_max": 0.07})
        self.assertFalse(rows["kalshi_favorites"]["enabled"], "the paused house starter stays paused, and stays")
        self.assertTrue(rows["kalshi_extra"]["enabled"])
        self.assertNotIn("kalshi_favorites_f1.py", self.manager.files["mullins"])

    def test_a_cycle_never_raises_and_never_runs_twice_at_once(self):
        foundry = self.foundry()

        def broken():
            raise RuntimeError("roster unreadable")

        foundry.manifests = broken
        summary = foundry.cycle(NOW)
        self.assertIn("RuntimeError", summary["failed"])
        self.assertEqual([level for level, _ in self.alerts], ["warning"], "one alert")
        foundry._running.acquire()
        try:
            self.assertIn("already running", foundry.cycle(NOW)["skipped"])
        finally:
            foundry._running.release()
        self.assertEqual(foundry.summary()["failed"], summary["failed"])


# --------------------------------------------------------------------------- the service and the sandboxes
class SandboxLimitTests(unittest.TestCase):
    def test_foundry_sandboxes_get_their_own_fuse_and_run_cap(self):
        from ltcm.tests.test_sandbox import FakeClient

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeClient()
            manager = SandboxManager(client, root / "sandboxes.json", root / "toolbox", image={"checkpoint_id": "sbcp"}, daily_seconds=100)
            manager.set_limits("foundry-", daily_seconds=50_000, max_timeout=900)
            self.assertEqual(manager.limits_for("foundry-3"), (50_000, 900))
            self.assertEqual(manager.limits_for("mullins"), (100, 600))
            manager.run("foundry-0", "print(1)", timeout=900)
            manager.run("mullins", "print(1)", timeout=900)
            timeouts = [call[3] for call in client.calls if call[0] == "exec"]
            self.assertEqual(timeouts, [930, 130], "900 s for a backtest; a desk keeps its cap and fuse")
            manager.toolbox_save("mullins-4", "edge_f3", "x = 1\n", "candidate")
            self.assertTrue(manager.toolbox_remove("mullins-4", "edge_f3"))
            self.assertEqual(manager.toolbox_files("mullins-4"), {})
            self.assertFalse(manager.toolbox_remove("mullins-4", "../../etc"))


class ServiceFoundryTests(ServiceCase):
    def test_the_service_builds_the_foundry_and_runs_it_off_the_tick_at_its_interval(self):
        foundry = self.service.foundry
        self.assertIsNotNone(foundry)
        self.assertFalse(foundry.enabled(), "no sandboxes, no cycles")
        self.assertEqual(foundry.config["interval_minutes"], 30)
        calls = []
        foundry.enabled = lambda: True
        foundry.cycle = lambda at=None: calls.append(at) or {"at": at, "cycle": len(calls)}
        self.tick()
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.service.state()["last_foundry_at"], calls[0])
        self.tick(self.START + 600)
        self.assertEqual(len(calls), 1, "not before the interval")
        self.tick(self.START + 1860)
        self.assertEqual(len(calls), 2)
        self.assertIn("last_foundry", self.service.status())

    def test_a_running_cycle_is_never_started_twice(self):
        self.service.config["background_work"] = True
        foundry = self.service.foundry
        gate = threading.Event()
        calls = []

        def slow(at=None):
            calls.append(at)
            gate.wait(10)
            return {"at": at}

        foundry.enabled = lambda: True
        foundry.cycle = slow
        self.tick()
        first = self.service.state()["last_foundry_at"]
        self.tick(self.START + 1860)
        self.tick(self.START + 3720)
        self.assertEqual(len(calls), 1, "one cycle at a time")
        self.assertEqual(self.service.state()["last_foundry_at"], first)
        gate.set()
        self.service._workers["foundry"]["thread"].join(10)
        self.tick(self.START + 3780)
        self.assertEqual(len(calls), 2, "the next starts once the last is done")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
