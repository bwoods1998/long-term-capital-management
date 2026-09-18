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
#: The house starter's frozen settings, which every candidate of it carries.
FROZEN_HOUSE = {"max_new": 5, "max_open_per_series": 2, "no_max": 0.96, "notional_usd": None, "pages": 8}
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


def marker_of(code):
    """The run's own result marker, as the runner program prints it."""
    return ast.literal_eval(re.search(r"^MARKER = (.*)$", code, re.M).group(1))


def as_runner(text, code):
    """A scripted engine answer as the runner prints it: result lines under the run's marker."""
    marker = marker_of(code)
    return "\n".join(marker + line[len("BACKTEST-RESULT "):] if line.startswith("BACKTEST-RESULT ") else line for line in str(text).split("\n"))


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
            return Run(as_runner(self.script(spec), code))
        finally:
            with self._lock:
                self.active.discard(desk_id)


class Records(Strategies):
    """The runner with a scripted forward record per (desk, strategy)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = {}
        self.record_calls = []

    def record(self, desk_id, name, since=None, **options):
        self.record_calls.append((desk_id, name, since, *sorted(options.items())))
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
    def test_exit_only_strategy_does_not_starve_paused_entry_research(self):
        self.manifests["hilibrand"] = SimpleNamespace(id="hilibrand", family="crypto", live=True)
        self.strategies.store.update("hilibrand", "hourly_reversion", enabled=False, house=True)
        self.strategies.store.update("hilibrand", "spot_quotes", enabled=True, house=True, params={"bid": False})
        foundry = self.foundry(paused_research_families=["crypto"])
        self.assertEqual(foundry.subjects("crypto", self.manifests), ["hourly_reversion", "spot_quotes"])
        self.strategies.store.update("hilibrand", "hourly_reversion_f90", enabled=True)
        self.assertEqual(foundry.subjects("crypto", self.manifests), ["hourly_reversion_f90", "spot_quotes"])

    def test_excluded_strategies_are_never_subjects(self):
        self.manifests["hilibrand"] = SimpleNamespace(id="hilibrand", family="crypto", live=True)
        self.strategies.store.update("hilibrand", "hourly_reversion", enabled=True, house=True)
        self.strategies.store.update("hilibrand", "spot_quotes", enabled=True, house=True)
        self.strategies.store.update("hilibrand", "perp_reversion", enabled=True, house=True)
        self.assertEqual(self.foundry().subjects("crypto", self.manifests), ["hourly_reversion", "perp_reversion", "spot_quotes"])
        self.assertEqual(self.foundry(excluded_strategies=["spot_quotes"]).subjects("crypto", self.manifests), ["hourly_reversion", "perp_reversion"])

    def test_the_code_generator_is_told_the_fees_the_backtest_charges(self):
        # Sept 17, 2026: the prompt still said Kalshi rounds to the cent and Coinbase charges
        # 0.25%/0.60% while the backtest charged $0.0001 rounding and 0.5%/1.2%.
        from ltcm.backtest import DEFAULT_SPEC, kalshi_taker_fee

        text = self.foundry().instructions("kalshi_favorites_x")
        self.assertNotIn("ceil(0.07", text)
        self.assertIn("rounded up to $0.0001", text)
        self.assertEqual(kalshi_taker_fee(0.02, 1), 0.0014)
        maker, taker = DEFAULT_SPEC["coinbase_maker_fee"], DEFAULT_SPEC["coinbase_taker_fee"]
        self.assertIn(f"Coinbase {maker * 100:g}% maker and {taker * 100:g}% taker", text)

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
            self.assertTrue(10000 * 0.5 <= params["min_volume_24h"] <= 10000 * 1.5)
            self.assertIsInstance(params["min_volume_24h"], int)
            self.assertIsNone(params["notional_usd"], "size is never a candidate's")
            self.assertEqual((params["max_new"], params["no_max"]), (5, 0.96), "nor order counts and price guards")
        self.assertIn(False, [p["maker"] for p in full], "a choice from the family's variants is flipped")
        self.assertTrue(all(p["maker"] in (True, False) for p in full))
        self.assertEqual(len({json.dumps(p, sort_keys=True) for p in full}), 10, "no duplicates")
        self.assertEqual(len({v["id"] for v in variants}), 10)

    def test_spot_quotes_candidates_never_move_the_fee_guard(self):
        # Sept 17, 2026: maker_fee and min_margin are numbers in spot_quotes' DEFAULTS; jittered,
        # they set the spread a bid needs below the account's real round trip.
        foundry = self.foundry()
        source = (STARTERS_DIR / "spot_quotes.py").read_text(encoding="utf-8")
        defaults = literal_defaults(source)
        frozen = foundry.config["frozen_params"]
        self.assertTrue({"maker_fee", "min_margin"} <= set(frozen))
        variants = foundry.param_candidates(3, "crypto", "spot_quotes", source, defaults, {"spread": 0.015}, [], frozen)
        self.assertEqual(len(variants), 10)
        for variant in variants:
            params = {**defaults, **variant["params"]}
            self.assertEqual((params["maker_fee"], params["min_margin"]), (0.005, 0.002), variant["params"])
        self.assertIn("0.5% maker and 0.9% taker", foundry.instructions("spot_quotes_f3"))

    def test_authenticated_fees_reach_prompt_spec_and_cache_key(self):
        foundry = self.foundry()
        rates = {"maker": "0.003", "taker": "0.007", "age_seconds": 1}
        self.strategies.service = SimpleNamespace(venue_fee_rates=lambda: {"coinbase": rates})
        self.assertIn("Coinbase 0.3% maker and 0.7% taker", foundry.instructions("hourly_reversion_f3"))
        candidate = {"strategy": "hourly_reversion", "code": GOOD_CODE}
        window = {"start": NOW, "end": NOW, "step_minutes": 15, "coinbase_fees": foundry.coinbase_fees()}
        rates["taker"] = "0.008"
        first = foundry.spec_for(candidate, window)
        self.assertEqual((first["coinbase_maker_fee"], first["coinbase_taker_fee"]), (0.003, 0.007), "one tier snapshot for all candidates in a cycle")
        second = foundry.spec_for(candidate, {**window, "coinbase_fees": foundry.coinbase_fees()})
        self.assertNotEqual(first, second, "fee changes invalidate result cache specs")
        rates["age_seconds"] = 901
        with self.assertRaisesRegex(ValueError, "fees unavailable"):
            foundry.coinbase_fees()
        rates.update(age_seconds=0, maker="NaN")
        with self.assertRaises(ValueError):
            foundry.coinbase_fees()

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
    def test_quarantined_workers_do_not_consume_candidates_or_deadlock_empty_pool(self):
        self.manager.ready_for_run = lambda desk_id: desk_id == "foundry-1"
        summary = self.foundry(sandboxes=3, code_candidates=0).cycle(NOW)
        self.assertTrue(summary["backtested"])
        self.assertEqual({desk for desk, _, _ in self.manager.backtests}, {"foundry-1"})
        self.manager.ready_for_run = lambda desk_id: False
        before = len(self.manager.backtests)
        self.assertIn("awaiting execution confirmation", self.foundry().cycle(NOW)["skipped"])
        self.assertEqual(len(self.manager.backtests), before)

    def test_a_slow_repair_does_not_hold_back_another_valid_candidate(self):
        repair_started, release = threading.Event(), threading.Event()
        class MixedProvider(Provider):
            def respond(self, profile, items, **kwargs):
                key = kwargs["request_key"]
                if ":repair:" in key:
                    repair_started.set()
                    release.wait(4)
                    text = reply("kalshi_favorites_f1")
                elif key.endswith(":0"):
                    text = "broken JSON"
                else:
                    repair_started.wait(2)
                    text = reply("kalshi_favorites_f1_2")
                return SimpleNamespace(output_text=text, cost_usd=Decimal("0.07"))
        foundry = self.foundry(MixedProvider(), repair_invalid_code=True)
        worker = threading.Thread(target=lambda: foundry.cycle(NOW))
        worker.start()
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not any(s["strategy"] == "kalshi_favorites_f1_2" for s in self.manager.specs):
                time.sleep(.01)
            self.assertTrue(repair_started.is_set())
            self.assertTrue(any(s["strategy"] == "kalshi_favorites_f1_2" for s in self.manager.specs))
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())

    def test_pending_model_work_emits_factual_heartbeat_without_invented_thoughts(self):
        from unittest.mock import patch
        from concurrent.futures import wait
        seen = []
        def heartbeat_once(futures, **kwargs):
            if kwargs.get("return_when") and not seen:
                seen.append(True)
                return set(), set(futures)
            return wait(futures, **kwargs)
        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1"), 1: reply("kalshi_favorites_f1_2")}
        with patch("ltcm.foundry.wait_futures", side_effect=heartbeat_once):
            self.foundry(provider).cycle(NOW)
        messages = [e.payload for e in self.log.kinds("lab.progress")]
        self.assertTrue(any(p.get("pending_models") and "model jobs still running" in p["message"] for p in messages))

    def test_exact_successful_result_survives_restart_without_new_evidence(self):
        import queue
        window = {"start": "2026-09-01T00:00:00Z", "end": "2026-09-06T00:00:00Z", "step_minutes": 15}
        ids = queue.Queue()
        ids.put("foundry-0")
        def candidate(foundry, cycle):
            return foundry._candidate(cycle, "baseline", "house", "kalshi_favorites", "kalshi_favorites", {}, SOURCE)
        first = self.foundry(result_cache=True)
        first._backtest(candidate(first, 1), window, ids)
        restarted = self.foundry(result_cache=True)
        cached = restarted._backtest(candidate(restarted, 2), window, ids)
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(cached["seconds"], 0)
        self.assertEqual(len(self.manager.backtests), 1)
        self.assertEqual(ids.qsize(), 1)
        restarted._backtest(candidate(restarted, 3), dict(window, end="2026-09-07T00:00:00Z"), ids)
        self.assertEqual(len(self.manager.backtests), 2)

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
        # Sept 17, 2026: the Kalshi family replays ten days (`family_window_days`), other families five.
        self.assertEqual((spec["start"], spec["end"], spec["step_minutes"]), ("2026-09-06T14:00:00Z", "2026-09-16T14:00:00Z", 15))
        self.assertEqual((spec["fill_model"], spec["learning_usd"], spec["max_markets"], spec["seed"]), ("conservative", 10, 8000, 7), "the Kalshi family sees more of the board (`family_max_markets`)")
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
        self.assertEqual(summary["backtested"], 0, "unsupported reports are not successful measurements")
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
        self.assertIn("not measured", good["verdict"])
        strict = self.foundry(min_ci_lower=0.35)
        self.assertEqual([c["id"] for c in strict.select([baseline, good, better])[0]], [], "the bound is configurable")

    def test_the_runner_compiles_and_the_result_line_is_the_last_marker(self):
        code = runner_code({"strategy": "kalshi_favorites", "code": SOURCE, "params": {"yes_max": 0.12}}, fraction=0.66, token="t0k3n", min_interval=1.2)
        compile(code, "main.py", "exec")
        self.assertEqual(spec_of(code)["params"], {"yes_max": 0.12})
        self.assertIn("engine.run_backtest(SPEC, history=history)", code, "the report is the engine's return value, not its printout")
        self.assertIn("min_interval=MIN_INTERVAL", code)
        self.assertIn("MIN_INTERVAL = 1.2", code)
        self.assertEqual(marker_of(code), "BACKTEST-RESULT t0k3n ")
        self.assertIn("def split_evidence(", code, "the split ships with the runner")
        self.assertLess(len(code), 40_000)
        self.assertIsNone(parse_result("no marker", "t0k3n"))
        self.assertIsNone(parse_result("BACKTEST-RESULT t0k3n {broken", "t0k3n"))
        self.assertEqual(parse_result('BACKTEST-RESULT t0k3n {"trades": 1}\nBACKTEST-RESULT t0k3n {"trades": 2}\n', "t0k3n"), {"trades": 2})
        self.assertEqual(parse_result('BACKTEST-RESULT t0k3n {"trades": 1}\nBACKTEST-RESULT {"trades": 99}\n', "t0k3n"), {"trades": 1}, "a line without the run's token is never read")
        self.assertIsNone(parse_result('x BACKTEST-RESULT t0k3n {"trades": 3}', "t0k3n"), "only at the start of a line")
        self.assertEqual(self.foundry().min_interval(), 0.6, "four sandboxes share the floor's 0.15 s")
        self.assertEqual(self.foundry(sandboxes=8).min_interval(), 1.2)
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
    def test_with_deploy_live_the_winner_joins_the_live_book_as_its_own_row_and_is_pruned_on_a_losing_record(self):
        """The arena (Sept 18, 2026): a candidate earns its forward record with real fills at
        learning size on the live desk; a losing record retires it, a full desk drops its worst."""
        self.manager.script = settings_winner
        live_before = self.row("mullins")
        foundry = self.foundry(deploy_live=True, max_explorers_per_desk=1)
        summary = foundry.cycle(NOW)
        self.assertEqual(summary["deployed_to"], "mullins")
        fid = summary["winner"]
        deployment = foundry.state()["deployments"][fid]
        self.assertEqual((deployment["status"], deployment["role"], deployment["live_desk_id"]), ("live", "winner", "mullins"))
        name = deployment["strategy"]
        self.assertRegex(name, r"^kalshi_favorites_f\d+_\d+$")
        self.assertEqual(self.row("mullins"), live_before, "the house row is untouched: the candidate is its own row")
        row = self.row("mullins", name)
        self.assertTrue(row["foundry_explorer"])
        self.assertEqual(row["params"], deployment["params"])
        self.assertIn(f"{name}.py", self.manager.toolbox_files("mullins"))
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "a live row has nothing to fast-track")
        # A losing forward record retires it from the book.
        self.clock[0] += 3600
        self.strategies.records[("mullins", name)] = {"settled": 5, "fills": 5, "settled_pnl_usd": "-1.20"}
        pruned = foundry.prune_explorers(self.manifests)
        self.assertEqual([(p["desk_id"], p["strategy"]) for p in pruned], [("mullins", name)])
        self.assertIsNone(self.row("mullins", name))
        self.assertEqual(foundry.state()["deployments"][fid]["status"], "retired")
        # A record that holds stays, and the size ramp is the strategies' business.
        summary = foundry.cycle(self.service.now())
        again = summary["winner"]
        self.strategies.records[("mullins", foundry.state()["deployments"][again]["strategy"])] = {"settled": 9, "fills": 9, "settled_pnl_usd": "3"}
        self.assertEqual(foundry.prune_explorers(self.manifests), [])
        # At capacity, a young explorer is protected: the next candidate goes to a shadow desk
        # instead, and the live row keeps trading. Past the protection window it makes room.
        self.clock[0] += 3600
        summary = foundry.cycle(self.service.now())
        self.assertEqual(len(foundry.explorer_rows("mullins")), 1, "the live row under protection stays")
        self.assertNotEqual(summary.get("deployed_to"), "mullins")
        self.clock[0] += 7 * 3600
        summary = foundry.cycle(self.service.now())
        if summary.get("deployed_to") == "mullins":
            self.assertEqual(len(foundry.explorer_rows("mullins")), 1, "past protection the old row made room")

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
        self.strategies.records[key] = {"settled": 4, "fills": 4, "settled_pnl_usd": "2"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "four settlements are not five")
        self.assertIn(("mullins-4", "kalshi_favorites", deployment["deployed_at"], ("opened_since", True)), self.strategies.record_calls, "positions opened since deployment")
        self.strategies.records[key] = {"settled": 5, "fills": 5, "settled_pnl_usd": "-0.01"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "a losing forward record never goes live")
        self.strategies.records[key] = {"settled": 5, "fills": 5, "settled_pnl_usd": "0.40", "fees_usd": "0.41"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "nor one that loses after fees")
        self.strategies.records[key] = {"settled": 5, "fills": 0, "settled_pnl_usd": "0.40"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "nor settlements without fills of its own")
        without_live = {k: v for k, v in self.manifests.items() if k != "mullins"}
        self.strategies.records[key] = {"settled": 5, "fills": 5, "settled_pnl_usd": "0.40", "fees_usd": "0.10"}
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

    def test_a_favorites_candidate_needs_the_evidence_gate_on_its_forward_record(self):
        """Sept 17, 2026: five or six favorites at 0.93 settling at P&L >= 0 is what a strategy
        with no edge produces about 70% of the time."""
        foundry, fid = self.deploy_settings()
        self.clock[0] += 3600
        key = ("mullins-4", "kalshi_favorites")
        favorites = {"asset_class": "event", "avg_entry_price": "0.93", "avg_fee_per_contract": "0"}
        self.strategies.records[key] = {"settled": 6, "fills": 6, "settled_pnl_usd": "4.20", "losses": 0, **favorites}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "six of the 43 settlements a 0.93 favorite needs")
        self.assertEqual(foundry.state()["deployments"][fid]["status"], "shadow", "still earning its record")
        self.strategies.records[key] = {"settled": 45, "fills": 45, "settled_pnl_usd": "1.50", "losses": 3, **favorites}
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "three losses in 45: the loss rate could be over breakeven")
        cheap = {"settled": 6, "fills": 6, "settled_pnl_usd": "1.00", "losses": 1, "asset_class": "event", "avg_entry_price": "0.45"}
        self.strategies.records[key] = cheap
        self.assertEqual(len(foundry.fast_track(self.manifests, [])), 1, "a payoff that is not lopsided keeps the forward-count rule")

    def test_a_lopsided_candidate_with_the_evidence_goes_live(self):
        foundry, fid = self.deploy_settings()
        self.clock[0] += 3600
        self.strategies.records[("mullins-4", "kalshi_favorites")] = {
            "settled": 45, "fills": 45, "settled_pnl_usd": "20.40", "losses": 1,
            "asset_class": "event", "avg_entry_price": "0.93", "avg_fee_per_contract": "0",
        }
        self.assertEqual([a["id"] for a in foundry.fast_track(self.manifests, [])], [fid])

    def test_a_retired_family_is_never_picked_and_nothing_of_it_goes_live(self):
        foundry, fid = self.deploy_settings()
        self.clock[0] += 3600
        self.strategies.records[("mullins-4", "kalshi_favorites")] = {"settled": 9, "fills": 9, "settled_pnl_usd": "3"}
        retired = self.foundry(excluded_families=["kalshi"])
        self.assertEqual(retired.fast_track(self.manifests, []), [])
        self.assertEqual(retired.state()["deployments"][fid]["status"], "shadow")
        specs = len(self.manager.specs)
        self.clock[0] += 3600
        summary = retired.cycle()
        self.assertEqual(summary["skipped"], "no backtestable family has desks")
        self.assertEqual(len(self.manager.specs), specs, "no backtests for a retired family")
        self.assertEqual([a["id"] for a in foundry.fast_track(self.manifests, [])], [fid], "the same record goes live for a family still in play")

    def test_a_setting_changed_under_the_candidate_is_superseded(self):
        foundry, fid = self.deploy_settings()
        self.strategies.store.update("mullins-4", "kalshi_favorites", params={"yes_max": 0.2}, promoted_at="2026-09-16T15:00:00.000Z")
        self.strategies.records[("mullins-4", "kalshi_favorites")] = {"settled": 9, "fills": 9, "settled_pnl_usd": "3"}
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
        self.strategies.records[("mullins-4", "kalshi_favorites_f1")] = {"settled": 6, "fills": 6, "settled_pnl_usd": "1.20"}
        adopted = foundry.fast_track(self.manifests, [])
        self.assertEqual([a["kind"] for a in adopted], ["code"])
        row = self.row("mullins", "kalshi_favorites_f1")
        self.assertTrue(row["enabled"])
        self.assertEqual(row["params"], {"yes_max": 0.08, **FROZEN_HOUSE}, "the candidate's settings, the parent's sizes and guards")
        self.assertEqual((row["foundry_id"], row["promoted_from"]), (fid, "mullins-4"))
        self.assertEqual(self.manager.files["mullins"]["kalshi_favorites_f1.py"], GOOD_CODE)
        self.assertFalse(self.row("mullins")["enabled"], "the parent strategy is paused, never doubled")

    def test_paused_house_can_only_be_replaced_by_strong_new_forward_code(self):
        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1"), 1: reply("kalshi_favorites_f1_2")}
        self.manager.script = code_winner
        foundry = self.foundry(provider, paused_replacement_families=["kalshi"])
        summary = foundry.cycle(NOW)
        self.strategies.store.update("mullins", "kalshi_favorites", enabled=False)
        key = ("mullins-4", "kalshi_favorites_f1")
        self.strategies.records[key] = {"settled": 6, "fills": 6, "settled_pnl_usd": "1.2"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [])
        self.assertEqual(foundry.state()["deployments"][summary["winner"]]["status"], "shadow")
        self.strategies.records[key] = {"settled": 30, "independent_settled": 30, "fills": 30, "settled_pnl_usd": "6", "fees_usd": "1",
                                      "returns": [[f"2026-09-{14 + i % 3}", 0.02] for i in range(30)]}
        self.assertEqual(len(foundry.fast_track(self.manifests, [])), 1)
        self.assertFalse(self.row("mullins")["enabled"])
        self.assertTrue(self.row("mullins", "kalshi_favorites_f1")["enabled"])

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
        self.strategies.records[("mullins-4", "kalshi_favorites_f1")] = {"settled": 5, "fills": 5, "settled_pnl_usd": "0"}
        self.assertEqual(len(foundry.fast_track(self.manifests, [])), 1)
        live_row = self.row("mullins", "kalshi_favorites_f1")
        self.assertTrue(live_row["enabled"])
        self.assertEqual(live_row["params"], deployment["params"])
        self.assertTrue(self.row("mullins")["enabled"], "nothing else on the live desk is paused")
        self.assertEqual(self.manager.files["mullins"]["kalshi_favorites_f1.py"], live_code)

    def test_a_full_live_desk_makes_room_by_setting_aside_the_candidate_it_replaces(self):
        from ltcm.strategies import _sha

        self.strategies.config["max_per_desk"] = 3  # the case is about a full desk
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
        self.strategies.records[("mullins-4", "kalshi_favorites_f9")] = {"settled": 8, "fills": 8, "settled_pnl_usd": "2.5"}
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
        self.assertEqual(rows["kalshi_favorites_f9"]["params"], {"yes_max": 0.07}, "GOOD_CODE, the parent's code, has no frozen settings")
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


# --------------------------------------------------------------------------- review of Sept 16, 2026
def tape_position(log, desk, name, n, opened, settled, held, pnl="0.10", fee="0"):
    """One position on the tape the way the gateway writes it: intent, order and fill when it
    opened, and the outcome (dated when it settled, with how long it was held)."""
    from ltcm.broker import Instrument

    leg = Instrument(asset_class="event", symbol=f"KXF-{desk}-{n}", venue="kalshi", right="no", market_id=f"KXF-{desk}-{n}")
    log.events += [
        SimpleNamespace(stream=f"desk:{desk}", kind="desk.intent", id=None, at=opened, payload={"intent_id": f"i-{desk}-{n}", "session_id": f"{desk}:20260916-1200:strategy:{name}"}),
        SimpleNamespace(stream="broker:shadow", kind="broker.order", id=None, at=opened, payload={"order_id": f"o-{desk}-{n}", "intent_id": f"i-{desk}-{n}"}),
        SimpleNamespace(stream="broker:shadow", kind="broker.fill", id=None, at=opened, payload={"order_id": f"o-{desk}-{n}", "quantity": "10", "price": "0.90", "fee": fee, "instrument": leg.to_dict()}),
        SimpleNamespace(stream=f"desk:{desk}", kind="desk.outcome", id=None, at=settled, payload={"pnl": pnl, "rationale_excerpt": f"[strategy {name}] NO bid", "instrument": leg.key, "held_for_hours": held}),
    ]


FAKE_ENGINE = """
import contextlib, sys

def run_backtest(spec, history=None):
    namespace = {"__name__": "backtest_" + spec["strategy"]}
    with contextlib.redirect_stdout(sys.stderr):
        exec(compile(spec["code"], "strategy", "exec"), namespace)
        try:
            namespace["decide"](object(), {})
        except Exception:
            pass
    pnls = [0.01 * ((i % 3) - 1) for i in range(90)]
    return {"strategy": spec["strategy"], "trades": 90, "notional_usd": 90.0, "pnl_usd": sum(pnls), "trade_pnls": pnls, "errors": 0}
"""


class ReviewTests(FoundryCase):
    """The adversarial review of the Foundry (Sept 16, 2026), one test per defect it found."""

    def test_the_forward_record_ignores_positions_the_old_settings_opened(self):
        self.manager.script = settings_winner
        foundry = self.foundry()
        summary = foundry.cycle(NOW)
        deployment = foundry.state()["deployments"][summary["winner"]]
        self.assertEqual((deployment["desk_id"], deployment["deployed_at"]), ("mullins-4", NOW))
        self.strategies.record = Strategies.record.__get__(self.strategies)  # the real record over the tape
        for n in range(5):  # opened by the old settings at noon, settled after the deployment
            tape_position(self.log, "mullins-4", "kalshi_favorites", n, "2026-09-16T12:00:00.000Z", "2026-09-16T15:00:00.000Z", "3.0")
        self.clock[0] += 3600
        self.assertEqual(self.strategies.record("mullins-4", "kalshi_favorites", since=NOW)["settled"], 5, "dated by settlement")
        self.assertEqual(foundry.fast_track(self.manifests, []), [], "none of them came from the new settings")
        self.assertEqual(self.row("mullins")["params"], {}, "the live desk keeps its settings")
        for n in range(5, 10):  # the new settings' own positions
            tape_position(self.log, "mullins-4", "kalshi_favorites", n, "2026-09-16T14:30:00.000Z", "2026-09-16T15:10:00.000Z", "0.7")
        adopted = foundry.fast_track(self.manifests, [])
        self.assertEqual([a["id"] for a in adopted], [summary["winner"]])
        self.assertEqual(self.row("mullins")["params"], deployment["params"])

    def test_settings_go_only_where_the_backtested_code_runs_and_live_code_must_still_match(self):
        self.manager.script = settings_winner
        for desk_id in ("mullins-2", "mullins-3", "mullins-4"):
            self.manager.files[desk_id]["kalshi_favorites.py"] = SOURCE + "\n# the desk's own edit\n"
        problems = []
        foundry = self.foundry()
        summary = foundry.cycle(NOW)
        self.assertIsNone(summary["deployed_to"], "no shadow desk runs the code the settings were backtested with")
        self.assertIn("no shadow desk", " ".join(summary["problems"]))
        for desk_id in ("mullins-2", "mullins-3", "mullins-4"):
            self.manager.files[desk_id]["kalshi_favorites.py"] = SOURCE
        self.clock[0] += 1800
        summary = foundry.cycle()
        fid = summary["winner"]
        self.assertEqual(summary["deployed_to"], "mullins-4")
        self.manager.files["mullins"]["kalshi_favorites.py"] = SOURCE + "\n# the live desk rewrote it\n"
        self.strategies.records[("mullins-4", "kalshi_favorites")] = {"settled": 9, "fills": 9, "settled_pnl_usd": "3"}
        self.clock[0] += 3600
        self.assertEqual(foundry.fast_track(self.manifests, problems), [])
        self.assertEqual(foundry.state()["deployments"][fid]["status"], "superseded")
        self.assertEqual(self.row("mullins")["params"], {})

    def test_model_code_that_could_reach_the_interpreter_is_refused(self):
        foundry = self.foundry()
        body = "\n\ndef decide(kit, params):\n    return []\n"
        escapes = {
            "import atexit": "import atexit" + body,
            "import sys": "import sys" + body,
            "from ltcm": "from ltcm import backtest" + body,
            "importlib": "import importlib" + body,
            "a re-exported sys": "import statistics\n\ndef decide(kit, params):\n    statistics.sys.stdout.write('x')\n    return []\n",
            "the simulator": "def decide(kit, params):\n    kit._sim.closed.append({})\n    return []\n",
            "a dunder": "def decide(kit, params):\n    return kit.bars.__self__\n",
            "patching a module": "import json\n\ndef decide(kit, params):\n    json.dumps = str\n    return []\n",
            "patching a class": "import random\nR = random.Random\n\ndef decide(kit, params):\n    R.choices = None\n    return []\n",
            "a computed getattr": "def decide(kit, params):\n    return getattr(kit, '_' + 'sim')\n",
            "getattr as a value": "import functools\n\ndef decide(kit, params):\n    return functools.reduce(getattr, ['_sim'], kit)\n",
            "format lookups": "def decide(kit, params):\n    return '{0._sim}'.format(kit)\n",
            "frames": "def decide(kit, params):\n    g = (x for x in [1])\n    return g.gi_frame.f_back\n",
            "a finalizer": "class Late:\n    def __del__(self):\n        print('BACKTEST-RESULT {}')\n" + body,
            "update_wrapper": "import functools\n\ndef decide(kit, params):\n    functools.update_wrapper(kit, kit)\n    return []\n",
            "a match on a private attribute": "def decide(kit, params):\n    match kit:\n        case object(_sim=s):\n            return s\n    return []\n",
            "eval": "def decide(kit, params):\n    return eval('1')\n",
            "a metaclass": "class X(metaclass=type):\n    pass\n" + body,
            "typing internals": "from typing import get_type_hints" + body,
        }
        for label, code in escapes.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    foundry.validate_code({"code": code, "hypothesis": "h"}, "kalshi_favorites_f9", self.live, 900)
        for path in sorted(p for p in STARTERS_DIR.glob("*.py") if p.name != "__init__.py"):
            with self.subTest(path.name):
                foundry.validate_code({"code": path.read_text(encoding="utf-8"), "hypothesis": "h"}, "kalshi_favorites_f9", self.live, 900)
        fine = "import math\nfrom collections import defaultdict\n\ndef decide(kit, params):\n    rows = defaultdict(list)\n    rows['a'].append(math.sqrt(4))\n    return [] if getattr(kit, 'context', None) is None else []\n"
        foundry.validate_code({"code": fine, "hypothesis": "h"}, "kalshi_favorites_f9", self.live, 900)

    def test_nothing_a_strategy_prints_passes_for_the_runners_result(self):
        """Even code that slips past the checker: the report is the engine's return value, a
        SystemExit is a failed run, exit handlers never run, and only this run's token is read."""
        import os
        import subprocess
        import sys

        forged = json.dumps({"strategy": "x", "trades": 120, "notional_usd": 120.0, "errors": 0, "trade_pnls": [0.5] * 120})
        strategies = {
            "atexit": (
                "import atexit, sys\n"
                f"atexit.register(lambda: sys.__stdout__.write('BACKTEST-RESULT {forged}\\n'))\n"
                "def decide(kit, params):\n"
                f"    sys.__stdout__.write('BACKTEST-RESULT {forged}\\n')\n"
                f"    print('BACKTEST-RESULT {forged}')\n"
                "    return []\n"
            ),
            "exit": (
                "def decide(kit, params):\n"
                f"    print('BACKTEST-RESULT {forged}')\n"
                "    raise SystemExit(0)\n"
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "ltcm"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "backtest.py").write_text(FAKE_ENGINE, encoding="utf-8")
            (package / "history.py").write_text("class History:\n    def __init__(self, **kwargs):\n        self.kwargs = kwargs\n", encoding="utf-8")
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": temp, "PYTHONDONTWRITEBYTECODE": "1"}
            for label, code in strategies.items():
                with self.subTest(label):
                    token = "a1b2c3"
                    program = runner_code({"strategy": "kalshi_favorites_f7", "code": code, "params": {}}, token=token)
                    done = subprocess.run([sys.executable, "-c", program], cwd=temp, env=env, capture_output=True, text=True, timeout=60)
                    self.assertEqual(done.returncode, 0, done.stderr[-500:])
                    self.assertEqual([line for line in done.stdout.splitlines() if line.startswith("BACKTEST-RESULT a1b2c3 ")][-1:], done.stdout.splitlines()[-1:], "the run's line is the last")
                    report = parse_result(done.stdout, token)
                    self.assertIsNotNone(report)
                    self.assertNotEqual(report.get("trades"), 120, "the forged line is never read")
                    if label == "atexit":
                        self.assertEqual((report["trades"], report["errors"]), (90, 0), "the engine's own report")
                        self.assertNotIn(forged, done.stdout.splitlines()[-1])
                    else:
                        self.assertEqual(report["errors"], 1)
                        self.assertIn("SystemExit", report["unsupported"])

    def test_two_mutations_of_one_parent_never_trade_live_together(self):
        provider = Provider()
        winners = {"kalshi_favorites_f1", "kalshi_favorites_f2"}
        self.manager.script = lambda spec: result_line(pnls(0.0, 0.4)) if spec["strategy"] in winners else result_line(pnls(0.05, 0.05))
        foundry = self.foundry(provider)
        provider.replies = {0: reply("kalshi_favorites_f1"), 1: reply("kalshi_favorites_f1_2")}
        first = foundry.cycle(NOW)
        self.clock[0] += 1800
        provider.replies = {0: reply("kalshi_favorites_f2", code=GOOD_CODE.replace("0.1", "0.12")), 1: reply("kalshi_favorites_f2_2")}
        second = foundry.cycle()
        self.assertEqual((first["strategy"], second["strategy"]), ("kalshi_favorites", "kalshi_favorites"))
        self.assertEqual({first["deployed_to"], second["deployed_to"]}, {"mullins-4", "mullins-3"})
        self.clock[0] += 7200
        self.strategies.records[(first["deployed_to"], "kalshi_favorites_f1")] = {"settled": 6, "fills": 6, "settled_pnl_usd": "1.0"}
        self.strategies.records[(second["deployed_to"], "kalshi_favorites_f2")] = {"settled": 6, "fills": 6, "settled_pnl_usd": "1.0"}
        adopted = foundry.fast_track(self.manifests, [])
        self.assertEqual(len(adopted), 1, "the second was measured against a parent the live desk no longer runs")
        live = self.strategies.store.for_desk("mullins")
        enabled = sorted(name for name, row in live.items() if row.get("enabled", True))
        self.assertEqual(enabled, [adopted[0]["strategy"]])
        other = second["winner"] if adopted[0]["id"] == first["winner"] else first["winner"]
        self.assertEqual(foundry.state()["deployments"][other]["status"], "superseded")
        self.assertEqual(foundry.subjects("kalshi", self.manifests), [adopted[0]["strategy"]], "the paused parent is not mutated again")
        # And a stray enabled line on the live desk is paused when a mutation joins it.
        from ltcm.strategies import _sha

        self.manager.files["mullins"]["kalshi_favorites_f0.py"] = GOOD_CODE
        self.strategies.store.update("mullins", "kalshi_favorites_f0", params={}, cadence_seconds=900, enabled=True, foundry_code=True, code_sha256=_sha(GOOD_CODE))
        new_code = GOOD_CODE + "# sharper\n"
        self.manager.files["mullins-2"]["kalshi_favorites_f9.py"] = new_code
        self.strategies.store.update("mullins-2", "kalshi_favorites_f9", params={}, cadence_seconds=900, enabled=True, foundry_code=True, foundry_id="fdy-9-abc")
        foundry._add_deployment({
            "id": "fdy-9-abc", "family": "kalshi", "subject": adopted[0]["strategy"], "strategy": "kalshi_favorites_f9", "kind": "code",
            "desk_id": "mullins-2", "deployed_at": "2026-09-16T10:00:00.000Z", "status": "shadow", "params": {},
            "code_sha256": _sha(new_code), "cadence_seconds": 900, "trades": 120, "oos_trades": 40, "oos_return": 0.2, "oos_ci_lower": 0.05,
        })
        self.strategies.records[("mullins-2", "kalshi_favorites_f9")] = {"settled": 8, "fills": 8, "settled_pnl_usd": "2.5"}
        self.strategies.store.remove("mullins", "kalshi_favorites")
        self.assertEqual([a["id"] for a in foundry.fast_track(self.manifests, [])], ["fdy-9-abc"])
        live = self.strategies.store.for_desk("mullins")
        self.assertEqual(sorted(name for name, row in live.items() if row.get("enabled", True)), ["kalshi_favorites_f9"])

    def test_a_live_baseline_that_is_not_measured_sets_no_bar_and_pays_no_model(self):
        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1"), 1: reply("kalshi_favorites_f1_2")}

        def script(spec):
            params = spec["params"]
            if spec["strategy"] == "kalshi_favorites" and params == {}:
                return "timeout: the run was killed at 900 s\n"  # the live baseline
            if params == {"yes_max": 0.05}:
                return result_line(pnls(0.0, 0.0))  # the shadow baseline
            return result_line(pnls(0.0, 0.12))  # every candidate beats the shadow's bar

        self.manager.script = script
        summary = self.foundry(provider).cycle(NOW)
        self.assertEqual((summary["qualified"], summary["winner"], summary["deployed_to"]), (0, None, None))
        self.assertEqual(provider.calls, [], "no model is paid when nothing could qualify")
        self.assertIn("not measured", summary["code"]["skipped"])
        verdicts = [c.get("verdict") for c in summary["candidates_detail"] if c["kind"] != "baseline"]
        self.assertTrue(verdicts and all("not measured" in str(v) for v in verdicts), verdicts)
        self.assertEqual(self.log.kinds("lab.hypothesis")[0].payload["winner"], "no winner")

        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1"), 1: reply("kalshi_favorites_f1_2")}
        self.manager.script = lambda spec: "the desk's sandbox time for today is used up"
        self.clock[0] += 3600
        summary = self.foundry(provider).cycle()
        self.assertEqual(provider.calls, [], "every run failing pays no model either")
        self.assertEqual(summary["model_cost_usd"], "0")

    def test_engine_errors_disqualify_a_candidate_and_leave_a_baseline_unmeasured(self):
        def script(spec):
            if spec["strategy"] == "kalshi_favorites" and spec["params"].get("maker") is False:
                return result_line(pnls(0.0, 0.3), errors=4, notes=["candle load failed (HistoryError); those markets have no prices"])
            return result_line(pnls(0.05, 0.05))

        self.manager.script = script
        summary = self.foundry().cycle(NOW)
        self.assertEqual(summary["qualified"], 0)
        errored = [c for c in summary["candidates_detail"] if (c.get("report") or {}).get("errors")]
        self.assertTrue(errored)
        self.assertTrue(all("engine errors" in str(c["verdict"]) for c in errored))
        self.manager.script = lambda spec: result_line(pnls(0.05, 0.05), errors=1) if spec["params"] == {} else result_line(pnls(0.0, 0.3))
        self.clock[0] += 3600
        summary = self.foundry().cycle()
        self.assertEqual(summary["qualified"], 0, "a baseline that saw fewer markets sets no bar")
        self.assertIn("not measured", summary["code"]["skipped"] or "")

    def test_frozen_settings_bind_the_code_a_model_writes(self):
        provider = Provider()
        loose = (
            "DEFAULTS = {'yes_max': 0.1, 'no_max': 0.999, 'max_new': 40, 'max_open_per_series': 50, 'pages': 50}\n\n"
            "def decide(kit, params):\n    p = {**DEFAULTS, **params}\n    return []\n"
        )
        provider.replies = {0: reply("kalshi_favorites_f1", code=loose, params={"no_max": 0.9999}), 1: reply("kalshi_favorites_f1_2")}
        self.manager.script = lambda spec: result_line(pnls(0.0, 0.4)) if spec["strategy"].startswith("kalshi_favorites_f1") else result_line(pnls(0.05, 0.05))
        foundry = self.foundry(provider)
        summary = foundry.cycle(NOW)
        self.assertIn("frozen", summary["code"]["rejected"][0])
        self.assertNotIn("kalshi_favorites_f1", {spec["strategy"] for spec in self.manager.specs})
        self.assertEqual(summary["winner"] and foundry.state()["deployments"][summary["winner"]]["strategy"], "kalshi_favorites_f1_2")
        dealt = self.row(summary["deployed_to"], "kalshi_favorites_f1_2")["params"]
        self.assertEqual({k: dealt[k] for k in FROZEN_HOUSE}, FROZEN_HOUSE, "the shadow runs the parent's sizes and guards")
        for code, reason in (
            ("DEFAULTS = dict(yes_max=0.1, max_new=40)\n\ndef decide(kit, params):\n    return []\n", "literal"),
            ("DEFAULTS = {'yes_max': 0.1, 'notional_usd': 50}\n\ndef decide(kit, params):\n    return []\n", "frozen"),
        ):
            with self.assertRaises(ValueError) as caught:
                foundry.validate_code({"code": code, "hypothesis": "h"}, "kalshi_favorites_f9", self.live, 900, source=SOURCE)
            self.assertIn(reason, str(caught.exception))
        keep = "DEFAULTS = {'yes_max': 0.2, 'max_new': 5, 'no_max': 0.96}\n\ndef decide(kit, params):\n    return []\n"
        foundry.validate_code({"code": keep, "hypothesis": "h"}, "kalshi_favorites_f9", self.live, 900, source=SOURCE)

    def test_an_adoption_never_reverts_the_live_desks_newer_code(self):
        from ltcm.strategies import _sha

        v1 = 'DEFAULTS = {"yes_max": 0.1, "maker": True}\n\ndef decide(kit, params):\n    return []\n'
        self.manager.files["mullins"]["desk_edge.py"] = v1
        self.strategies.store.update("mullins", "desk_edge", params={}, cadence_seconds=600, enabled=True, code_sha256=_sha(v1))
        foundry = self.foundry()
        foundry._save(subject_index={"kalshi": 1})
        self.manager.script = lambda spec: result_line(pnls(0.0, 0.3)) if spec["strategy"] == "desk_edge" and spec["params"].get("yes_max", 0.1) > 0.11 else result_line(pnls(0.05, 0.05))
        summary = foundry.cycle(NOW)
        self.assertEqual((summary["strategy"], foundry.state()["deployments"][summary["winner"]]["kind"]), ("desk_edge", "code"))
        v2 = v1.replace("return []", "return []  # v2: the desk's fix for a loss")
        self.manager.files["mullins"]["desk_edge.py"] = v2
        self.strategies.store.update("mullins", "desk_edge", code_sha256=_sha(v2))
        self.clock[0] += 30 * 3600
        self.strategies.records[(summary["deployed_to"], "desk_edge")] = {"settled": 5, "fills": 5, "settled_pnl_usd": "0"}
        self.assertEqual(foundry.fast_track(self.manifests, []), [])
        self.assertEqual(self.manager.files["mullins"]["desk_edge.py"], v2, "the desk's own newer version stays")
        self.assertEqual(foundry.state()["deployments"][summary["winner"]]["status"], "superseded")

    def test_published_runs_stay_under_the_size_limit_in_bytes(self):
        from ltcm.events import canonical

        provider = Provider()
        provider.replies = {0: reply("kalshi_favorites_f1", params={"exclude_prefixes": ["<" * 790]}, hypothesis="\U0001d54f" * 300), 1: reply("kalshi_favorites_f1_2")}
        self.manager.script = lambda spec: result_line(pnls(0.0, 0.4)) if spec["strategy"] == "kalshi_favorites_f1" else result_line(pnls(0.05, 0.05))
        summary = self.foundry(provider).cycle(NOW)
        self.assertEqual(summary["deployed_to"], "mullins-4")
        published = [e for e in self.log.events if e.kind in ("desk.code_run", "lab.hypothesis")]
        self.assertTrue(any(e.kind == "desk.code_run" and e.stream == "desk:mullins-4" for e in published))
        for event in published:
            text = canonical(event.payload)
            self.assertLess(len(text.encode("utf-8")), 3300, event.kind)
            self.assertNotIn("<", text)


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
        self.assertEqual(foundry.config["interval_minutes"], 2)
        calls = []
        foundry.enabled = lambda: True
        foundry.cycle = lambda at=None: calls.append(at) or {"at": at, "cycle": len(calls)}
        self.tick()
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.service.state()["last_foundry_at"], calls[0])
        self.tick(self.START + 60)
        self.assertEqual(len(calls), 1, "not before the interval")
        self.tick(self.START + 360)
        self.assertEqual(len(calls), 2)
        self.assertIn("last_foundry", self.service.status())

    def test_research_lanes_run_side_by_side_on_their_own_sandboxes_and_state(self):
        """The arena (Sept 18, 2026): a Kalshi lane and a crypto lane, each a Foundry of its own."""
        self.service.close()
        self.service = self.build(foundry={"lanes": [
            {"name": "kalshi", "families": ["kalshi"], "sandboxes": 2, "sandbox_offset": 0},
            {"name": "crypto", "families": ["crypto"], "sandboxes": 2, "sandbox_offset": 2},
        ]})
        lanes = self.service.foundries
        self.assertEqual([f.config["families"] for f in lanes], [["kalshi"], ["crypto"]])
        self.assertEqual([f.config["sandbox_offset"] for f in lanes], [0, 2])
        self.assertEqual([f.state_path.name for f in lanes], ["foundry.json", "foundry-crypto.json"])
        self.assertIs(self.service.foundry, lanes[0])
        calls = []
        for lane in lanes:
            lane.enabled = lambda: True
            lane.cycle = lambda at=None, lane=lane: calls.append(lane.config["name"]) or {"at": at, "cycle": 1}
        self.tick()
        self.assertEqual(sorted(calls), ["crypto", "kalshi"], "both lanes cycle on the same tick")
        state = self.service.state()
        self.assertIn("last_foundry_at", state)
        self.assertIn("last_foundry_at_1", state)
        self.assertEqual(sorted(self.service.status()["foundry_lanes"]), ["crypto", "kalshi"])

    def test_the_foundry_reads_the_evolution_loops_retired_families(self):
        self.service.close()
        self.service = self.build(evolution={"target_variants": 1, "excluded_families": ["ranges"]}, foundry={"excluded_families": ["weather"]})
        self.assertEqual(self.service.foundry.config["excluded_families"], ["ranges", "weather"])
        self.assertEqual(self.service.evolution.excluded_families(), {"ranges"})

    def test_the_packaged_config_retires_the_ranges_family(self):
        from ltcm.strategies import STARTERS_DIR as starters

        config = json.loads((starters.parent / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("ranges", config["foundry"]["families"])
        self.assertIn("ranges", config["evolution"]["excluded_families"])
        # Sept 18, 2026: the pooled favorites record passed the evidence gate, and the firm's
        # per-cluster cap on the live floor went from 8% to 12% (per market 3.5% to 6%).
        # Sept 18, 2026 (the arena): the owner accepts the volatility; 10% a market, 25% a cluster.
        self.assertEqual(config["event_rules"]["max_event_cluster_floor_pct"], "0.25")
        self.assertTrue(config["foundry"]["deploy_live"], "candidates earn their record on the live book")
        self.assertFalse(config["sessions"]["shadow_enabled"], "shadow desks run strategies, not chat sessions")

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
