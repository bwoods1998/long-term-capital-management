import json
import tempfile
import unittest
from pathlib import Path

from league import ci


class GuardTest(unittest.TestCase):
    def test_each_role_has_its_own_paths(self):
        self.assertEqual(ci.guard(["league/strategies/new.py", "league/strategies/registry.json"], "architect"), [])
        self.assertEqual(ci.guard(["league/tools/vwap.py", "league/tests/test_tool_vwap.py"], "toolsmith"), [])
        self.assertEqual(ci.guard(["league/game.json"], "designer"), [])
        self.assertEqual(ci.guard(["league/config.json"], "operator"), [])
        self.assertEqual(ci.guard(["league/playbook/2026-09-20-fees.md"], "teacher"), [])
        self.assertTrue(ci.guard(["league/game.json"], "architect"))
        self.assertTrue(ci.guard(["league/house.py"], "operator"))
        self.assertTrue(ci.guard(["league/config.json.bak"], "operator"))
        self.assertTrue(ci.guard(["README.md"], "teacher"))

    def test_nobody_touches_the_constitution_or_the_scorekeeper(self):
        for path in ("league/constitution.py", "league/ledger.py", "league/book.py", "league/evaluator.py", "league/stats.py", "league/ci.py",
                     "league/auditor.py", "league/watchdog.py", "league/safety.py", "league/replay.py", "gateway/lib/caps.mjs", ".github/workflows/checks.yml",
                     "League/Constitution.py", "league/history.py", "league/deep_replay.py"):
            for role in ci.ROLE_PATHS:
                self.assertTrue(ci.guard([path], role), (path, role))
        self.assertTrue(ci.guard(["league/constitution.py"], None))

    def test_traversal_is_refused(self):
        self.assertTrue(ci.guard(["league/strategies/../constitution.py"], "architect"))
        self.assertTrue(ci.guard(["/etc/passwd"], "architect"))

    def test_role_comes_from_the_branch_name(self):
        self.assertEqual(ci.role_of("merton/architect/new-idea-abcd1234"), "architect")
        self.assertIsNone(ci.role_of("merton/owner/x"))
        self.assertIsNone(ci.role_of("main"))
        self.assertIsNone(ci.role_of("merton/architect"))


class ContentTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        for sub in ("league/strategies", "league/tools"):
            (self.root / sub).mkdir(parents=True)
        (self.root / "league/strategies/registry.json").write_text("[]")

    def tearDown(self):
        self.dir.cleanup()

    def strategy(self, name, code, listed=True):
        (self.root / "league/strategies" / f"{name}.py").write_text(code)
        if listed:
            (self.root / "league/strategies/registry.json").write_text(json.dumps([{"name": name, "family": "t", "file": f"{name}.py", "why": "test"}]))

    def test_a_sound_strategy_passes_and_is_replayed(self):
        self.strategy("ok", 'NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "t", "symbols": ["BTC/USD"]}\nPARAMS = {}\n\ndef decide(ctx):\n    return {"intents": []}\n')
        self.assertEqual(ci.check_strategies(self.root), [])

    def test_unsafe_unlisted_or_crashing_strategies_are_refused(self):
        self.strategy("unsafe", "import os\ndef decide(ctx):\n    return {}\n")
        self.assertIn("import os", " ".join(ci.check_strategies(self.root)))
        self.strategy("crashes", 'NEEDS = {"venue": "kalshi", "horizon": "hour", "style": "t", "series": ["KXBTCD"]}\n\ndef decide(ctx):\n    return 1 / 0\n')
        self.assertIn("too many errors", " ".join(ci.check_strategies(self.root)))
        (self.root / "league/strategies/registry.json").write_text("[]")
        self.assertIn("not described", " ".join(ci.check_strategies(self.root)))
        (self.root / "league/strategies/registry.json").write_text(json.dumps([{"name": "ghost", "family": "t", "file": "ghost.py", "why": "x"}]))
        self.assertIn("does not exist", " ".join(ci.check_strategies(self.root)))

    def test_tools_obey_the_same_safety_rules(self):
        (self.root / "league/tools/fine.py").write_text("import math\n\ndef ema(xs, n):\n    return sum(xs[-n:]) / n\n")
        self.assertEqual(ci.check_tools(self.root), [])
        (self.root / "league/tools/bad.py").write_text("import socket\n")
        self.assertIn("socket", " ".join(ci.check_tools(self.root)))

    def test_the_canned_tapes_are_deterministic(self):
        self.assertEqual(ci.regression_tape("alpaca", steps=50), ci.regression_tape("alpaca", steps=50))
        self.assertEqual(ci.regression_tape("kalshi"), ci.regression_tape("kalshi"))
        watched = {"observe": {"symbols": ["BTC/USD"]}, "bars": {"timeframe": "5Min", "limit": 48}}
        self.assertEqual(ci.regression_tape("kalshi", **watched), ci.regression_tape("kalshi", **watched))

    # Sept 24, 2026 (the close-the-gaps run): Merton's repairs of Huang's BTC 15-minute strategy
    # (PRs #217 and #208) failed this check with "required observed bars are missing" whatever they
    # changed: the canned Kalshi tape carried no bars of the spot price a strike strategy watches.
    OBSERVER = ('NEEDS = {"venue": "kalshi", "horizon": "hour", "style": "t", "series": ["KXBTC15M"], "max_hours_to_close": 1,\n'
                '         "observe": {"symbols": ["BTC/USD"]}, "bars": {"timeframe": "5Min", "limit": 48}}\n'
                'PARAMS = {}\n\n'
                'def decide(ctx):\n'
                '    bars = ctx["observed"]["bars"]["BTC/USD"]\n'
                '    if len(bars) < 12 or any(b["c"] <= 0 for b in bars):\n'
                '        raise ValueError("no usable observed bars")\n'
                '    spot = bars[-1]["c"]\n'
                '    return {"intents": [], "thought": "spot %.2f" % BODY}\n')

    def test_a_strategy_that_watches_spot_bars_passes_on_a_clean_body(self):
        self.strategy("watcher", self.OBSERVER.replace("BODY", "spot"))
        self.assertEqual(ci.check_strategies(self.root), [])
        tape = ci.regression_tape("kalshi", steps=240, observe={"symbols": ["BTC/USD"]}, bars={"timeframe": "5Min", "limit": 48})
        self.assertEqual(tape["observed_timeframe"], "5Min")
        first = tape["steps"][0]["t"]
        self.assertGreaterEqual(sum(1 for b in tape["observed_bars"]["BTC/USD"] if b["t"] <= first), 48, "warm-up bars before the first step")
        self.assertLessEqual(tape["observed_bars"]["BTC/USD"][-1]["t"], tape["steps"][-1]["t"])
        self.assertNotIn("observed_bars", ci.regression_tape("kalshi", steps=240), "a strategy that watches nothing gets the tape it always had")

    def test_and_still_fails_on_a_real_defect(self):
        self.strategy("watcher", self.OBSERVER.replace("BODY", "spot / 0"))
        problems = " ".join(ci.check_strategies(self.root))
        self.assertIn("too many errors", problems)
        self.assertNotIn("observed bars are missing", problems)
        self.strategy("wrongframe", self.OBSERVER.replace("BODY", "spot").replace('"5Min"', '"7Min"'))
        self.assertTrue(ci.check_strategies(self.root), "an undeclarable timeframe is still refused")


class RepositoryTest(unittest.TestCase):
    def test_the_repository_as_it_stands_passes_its_own_content_checks(self):
        self.assertEqual(ci.check_strategies() + ci.check_tools() + ci.check_game() + ci.check_config(None), [])


if __name__ == "__main__":
    unittest.main()


class TheDeployedGatewaysPrefix(unittest.TestCase):
    """The gateway's source names branches `merton/`; the DEPLOYED gateway still emitted `astra/`
    on Sept 20, 2026, so every proposal Merton opened landed on a branch the merge workflow ignored
    and sat open for ever, with nothing anywhere saying so. The floor could propose changes to
    itself and never land one."""

    def test_both_prefixes_carry_a_role_and_nothing_else_does(self):
        self.assertEqual(ci.role_of("merton/architect/a-thing"), "architect")
        self.assertEqual(ci.role_of("astra/operator/a-thing"), "operator")
        for branch in ("evil/architect/x", "astra/ledger/x", "merton/ledger/x", "astra/architect", "architect/x", ""):
            self.assertIsNone(ci.role_of(branch), branch)

    def test_the_guard_is_as_tight_under_either_prefix(self):
        for prefix in ci.PREFIXES:
            self.assertEqual(ci.guard(["league/constitution.py"], ci.role_of(f"{prefix}/architect/x")),
                             ["league/constitution.py: no role may change this file"])
            self.assertTrue(ci.guard(["league/game.json"], ci.role_of(f"{prefix}/architect/x")))   # not the architect's
            self.assertEqual(ci.guard(["league/strategies/new.py"], ci.role_of(f"{prefix}/architect/x")), [])

    def test_the_merge_workflow_accepts_both(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "merton.yml").read_text()
        self.assertIn("startsWith(github.head_ref, 'merton/')", text)
        self.assertIn("startsWith(github.head_ref, 'astra/')", text)
