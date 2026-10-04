import json
import tempfile
import unittest
from pathlib import Path

from league import ci


class GuardTest(unittest.TestCase):
    def test_isolated_research_authority_and_aliases_never_self_deploy_into_the_house(self):
        from league.updater import protected_changes

        modules = ("research_state", "research_transport", "research_adapters", "research_ipc",
                   "research_controller", "research_sandbox", "research_host")
        with tempfile.TemporaryDirectory() as tmp:
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            forbidden = []
            for module in modules:
                for rel in (f"league/swarm/{module}.py", f"league/swarm/{module}/__init__.py",
                            f"league/swarm/{module}.cpython-314-x86_64-linux-gnu.so"):
                    for role in (*ci.ROLE_PATHS, None, "engineer/data", "engineer/research"):
                        self.assertTrue(ci.guard([rel], role), (rel, role))
                    target = incoming / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"unreviewed isolated authority")
                    forbidden.append(rel)
            control = incoming / "league/swarm/library.py"
            control.write_text("VALUE = 1\n")
            self.assertEqual(sorted(p.split(":")[0] for p in protected_changes(incoming, running)), sorted(forbidden))

    def test_compute_commitments_and_dispatch_cannot_be_changed_or_shadowed_automatically(self):
        for module in ("compute", "daily_compute", "pool"):
            for path in (f"league/swarm/{module}.py", f"league/swarm/{module}/__init__.py",
                         f"League/Swarm/{module}.PY", f"league/swarm/{module}.so"):
                for role in (*ci.ROLE_PATHS, None, "engineer/data", "engineer/research"):
                    self.assertTrue(ci.guard([path], role), (path, role))

        # The running release must refuse new aliases too: they need not modify
        # the protected .py at all to replace the next process's budget code.
        from league.updater import protected_changes

        with tempfile.TemporaryDirectory() as tmp:
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            protected = []
            for module in ("compute", "daily_compute", "pool"):
                for rel in (f"league/swarm/{module}/__init__.py", f"league/swarm/{module}.so"):
                    target = incoming / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"candidate budget override")
                    protected.append(rel)
            ordinary = incoming / "league/swarm/library.py"
            ordinary.write_text("VALUE = 1\n")
            self.assertEqual(sorted(p.split(":")[0] for p in protected_changes(incoming, running)), sorted(protected))
        self.assertEqual(ci.guard(["league/swarm/computex.py", "league/swarm/library.py"], None), [])

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

    def test_the_houses_protected_jobs_are_judges_too(self):
        """V3-A: the budget rule, the standing grant and the drills (league/ops/) change only by the owner's deploy; since
        the WP8 review so does the framework that schedules and runs them (the whole of league/ops/)."""
        import tempfile

        from league.updater import protected_changes

        for path in ("league/ops/budget.py", "league/ops/drills.py", "league/ops/grant.py", "league/ops/"):
            self.assertIn(path, ci.FORBIDDEN)
        for path in ("league/ops/budget.py", "league/ops/drills.py", "league/ops/grant.py", "league/ops/jobs.py",
                     "league/ops/registry.py", "league/ops/__init__.py"):
            for role in ci.ROLE_PATHS:
                self.assertTrue(ci.guard([path], role), (path, role))
            self.assertTrue(ci.guard([path], None), path)
        with tempfile.TemporaryDirectory() as tmp:
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            for root, text in ((running, "RULE = 1\n"), (incoming, "RULE = 2\n")):
                (root / "league" / "ops").mkdir(parents=True)
                (root / "league" / "swarm").mkdir(parents=True)
                (root / "league" / "ops" / "budget.py").write_text(text)
                (root / "league" / "ops" / "jobs.py").write_text(text)
                (root / "league" / "swarm" / "library.py").write_text(text)
            # The research-class file beside them (league/swarm/library.py) changed too, and is not the owner's deploy.
            self.assertEqual([p.split(":")[0] for p in protected_changes(incoming, running)],
                             ["league/ops/budget.py", "league/ops/jobs.py"])

    def test_the_updaters_wall_and_the_gateways_merge_list_are_one_list(self):
        """A path the gateway will not merge must not self-deploy either, whatever route put it on main (V3-A
        integration): `FORBIDDEN` (read by `league.updater.protected_changes`) is the gateway's `MERGE_FORBIDDEN` but for
        `MERGE_ONLY` (the configuration, whose bounded dials the running release's checks judge).
        gateway/test/merge.test.mjs checks FORBIDDEN is inside the gateway's list from its side."""
        import re

        source = (ci.REPO / "gateway" / "lib" / "protected.mjs").read_text(encoding="utf-8")
        block = re.search(r"MERGE_FORBIDDEN = Object\.freeze\(\[([\s\S]*?)\]\);", source)
        self.assertIsNotNone(block)
        gateway = set(re.findall(r"'([^']+)'", re.sub(r"//[^\n]*", "", block.group(1))))
        self.assertGreater(len(gateway), 40)
        self.assertEqual(set(ci.FORBIDDEN) - gateway, set(), "the updater protects these; the gateway would merge them")
        self.assertEqual(gateway - set(ci.FORBIDDEN), set(ci.MERGE_ONLY), "the gateway protects these; the updater would deploy them")
        for path in ("league/swarm/bands.py", "league/swarm/store.py", "ltcm/data/us_equity_session.py", "deploy/restart.sh",
                     "league/gym/engine.py", "league/swarm/guard.py",
                     # the WP8 review's additions to the gateway's list, which the updater's wall gained with them
                     "league/__init__.py", "league/structure_core.py", "league/structures.py", "ltcm/performance.py",
                     "league/swarm/policy.json", "league/swarm/funding.py", "league/budget.py", "league/grants.py",
                     "league/swarm/harness_lanes.py", "league/swarm/harness_judges/research.py", "playbooks/harness-improvement.md",
                     "docs/goals/x.md", "scripts/floor_box.py", "league/house.py", "CHANGELOG.md", "changelog.md"):
            self.assertTrue(ci.guard([path], None), path)
        # The engineer's lane files are none of them: a lane the path guard admits is never one the wall refuses.
        for lane, paths in ci.ENGINEER_LANES.items():
            self.assertEqual(ci.guard(list(paths), f"engineer/{lane}"), [], lane)
        import tempfile

        from league.updater import protected_changes

        with tempfile.TemporaryDirectory() as tmp:
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            for root, text in ((running, "X = 1\n"), (incoming, "X = 2\n")):
                for rel in ("league/swarm/bands.py", "ltcm/data/us_equity_session.py", "league/swarm/library.py"):
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text(text)
            self.assertEqual([p.split(":")[0] for p in protected_changes(incoming, running)],
                             ["league/swarm/bands.py", "ltcm/data/us_equity_session.py"])
        # A name is compared without case on both sides, as the gateway compares (an entry may carry capitals).
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ci, "FORBIDDEN", ci.FORBIDDEN + ("league/Mixed_Case.py",)):
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            for root, text in ((running, "X = 1\n"), (incoming, "X = 2\n")):
                (root / "league").mkdir(parents=True)
                (root / "league" / "mixed_case.py").write_text(text)
            self.assertEqual([p.split(":")[0] for p in protected_changes(incoming, running)], ["league/mixed_case.py"])
            self.assertTrue(ci.guard(["league/MIXED_case.py"], None))

    def test_what_feeds_or_enforces_the_budget_is_protected(self):
        """D4: the budget rule changes only by the owner's deploy, so neither may what applies it (every module that calls
        `sail_caps`, the overlay or the Claude budget room) nor what budget.py imports to compute it. The Sail client and
        the notifier are transports (the arithmetic on their answers is budget.py's), and the close economics may only
        cut p30 (`budget._p30` takes the smaller of it and the book): those three are named here on purpose."""
        import ast
        import re

        def protected(path: str) -> bool:
            return any(path == f or (f.endswith("/") and path.startswith(f)) for f in ci.FORBIDDEN)

        callers = re.compile(r"\bsail_caps\(|\bclaude_budget_room\(|budget_mod\.overlay\(|from \.\.?ops\.budget import|"
                             r"from \.\.?ops import budget|from league\.ops(\.budget)? import (budget|sail_caps|overlay)")
        found = []
        for top in ("league", "ltcm", "scripts"):
            for path in (ci.REPO / top).rglob("*.py"):
                rel = path.relative_to(ci.REPO).as_posix()
                if "/tests/" in rel or rel.startswith("league/tests/"):
                    continue
                if callers.search(path.read_text(encoding="utf-8", errors="replace")):
                    found.append(rel)
        self.assertIn("league/swarm/guard.py", found)
        self.assertIn("league/swarm/settings.py", found)
        self.assertIn("league/swarm/models.py", found)
        self.assertEqual([rel for rel in found if not protected(rel)], [])

        transports = {"league/sailbox.py", "ltcm/notify.py", "league/ops/economics.py"}
        tree = ast.parse((ci.REPO / "league" / "ops" / "budget.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                parent = ["league", "ops"][: 3 - node.level] if node.level else []
                module = parent + ((node.module or "").split(".") if node.module else [])
                for alias in node.names:
                    # `from league.swarm import settings` imports the module league/swarm/settings.py.
                    for parts in (module + [alias.name], module):
                        if parts and parts[0] in ("league", "ltcm"):
                            hits = [c for c in ("/".join(parts) + ".py", "/".join(parts) + "/__init__.py") if (ci.REPO / c).exists()]
                            if hits:
                                imported.add(hits[0])
                                break
        self.assertIn("league/ops/economics.py", imported)
        self.assertEqual(sorted(p for p in imported if not protected(p) and p not in transports), [])
        for path in ("league/ops/context.py", "league/swarm/guard.py", "league/swarm/models.py", "league/swarm/settings.py"):
            self.assertTrue(ci.guard([path], None), path)

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

    def test_nothing_merges_a_proposal_by_itself(self):
        """The options overhaul (Sept 26, 2026, trap 3): Merton's merge job is off; the guard and the judge still report."""
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "merton.yml").read_text()
        merge = text.split("\n  merge:\n", 1)[1]
        self.assertIn("\n    if: false\n", merge.split("\n    steps:\n", 1)[0])
        self.assertIn("\n  guard:\n", text)
        self.assertIn("\n  judge:\n", text)

    def test_the_checks_install_the_gym_only_when_the_tree_pins_it_and_run_both_suites(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "checks.yml").read_text()
        self.assertIn("if [ -f requirements-gym.txt ]; then python3 -m pip install", text)
        self.assertIn("discover -s ltcm/tests -t .", text)
        self.assertIn("discover -s league/tests -t .", text)


class TheEngineersLanes(unittest.TestCase):
    """LTCM v3, V3-A, WP8b: a branch `engineer/<lane>/<slug>-<8 hex>` may change only its lane's surface and add new
    `test_harness_candidate_*` tests, the same table the gateway admits and merges by (`gateway/lib/github.mjs`
    ENGINEER_LANES; a gateway test holds the two equal)."""

    SURFACES = {
        "scheduler": ("league/swarm/loop.py",),
        "research": ("league/swarm/researcher.py", "league/swarm/preflight.py", "league/swarm/claude_research.py"),
        "memory": ("league/swarm/architect.py", "league/swarm/strategist.py", "league/swarm/diagnostician.py",
                   "league/swarm/seeds.py", "league/swarm/mechanisms.py"),
        "data": ("league/sailbox.py", "league/data_job.py"),
    }

    def test_the_lanes_are_the_gateways_and_the_old_roles_are_unchanged(self):
        self.assertEqual(ci.ENGINEER_LANES, self.SURFACES)
        self.assertEqual(ci.ENGINEER_TESTS, "league/tests/test_harness_candidate_*.py")
        for lane, paths in self.SURFACES.items():
            self.assertEqual(ci.ROLE_PATHS[f"engineer/{lane}"], (*paths, ci.ENGINEER_TESTS))
        self.assertEqual({role: ci.ROLE_PATHS[role] for role in ("architect", "toolsmith", "operator", "designer", "teacher")}, {
            "architect": ("league/strategies/",), "toolsmith": ("league/tools/", "league/tests/test_tool_"),
            "operator": ("league/config.json",), "designer": ("league/game.json",), "teacher": ("league/playbook/",)})
        self.assertEqual(len(ci.ROLE_PATHS), 9)

    def test_the_lane_comes_from_the_branch_name_in_the_gateways_exact_shape(self):
        for lane in self.SURFACES:
            self.assertEqual(ci.role_of(f"engineer/{lane}/a-thing-0123abcd"), f"engineer/{lane}")
        for branch in ("engineer/a-thing-0123abcd", "engineer/execution/a-thing-0123abcd", "engineer/research/a-thing",
                       "engineer/research/a-thing-0123ABCD", "engineer/research/a/thing-0123abcd", "engineer/research/-thing-0123abcd",
                       "engineer/Research/a-thing-0123abcd", "engineer/research/a-thing-0123abcd\n", "engineer/research",
                       "merton/engineer/research/a-thing-0123abcd", "merton/engineer/a-thing", "astra/engineer/x", "engineer/", ""):
            self.assertIsNone(ci.role_of(branch), branch)
        self.assertEqual(ci.role_of("merton/architect/new-idea-abcd1234"), "architect")

    def test_each_lane_changes_its_own_surface_and_new_tests_and_nothing_else(self):
        tests = ["league/tests/test_harness_candidate_preflight.py", "league/tests/test_harness_candidate_x_2.py",
                 "league/tests/test_harness_candidate_0.py"]
        for lane, paths in self.SURFACES.items():
            role = ci.role_of(f"engineer/{lane}/a-thing-0123abcd")
            self.assertEqual(ci.guard([*paths, *tests], role), [], lane)
            for other, theirs in self.SURFACES.items():
                if other != lane:
                    for path in theirs:
                        self.assertEqual(ci.guard([path], role), [f"{path}: outside what the {role} may change "
                                                                  f"({', '.join((*paths, ci.ENGINEER_TESTS))})"], (lane, path))
            for path in ("league/ops/agenda.py", "league/swarm/models.py", "league/swarm/harness_lanes.py", "League/Swarm/Loop.py",
                         "league/swarm/loop_v2.py", "league/tests/test_swarm_loop.py", "league/tests/test_harness_candidate_.py",
                         "league/tests/test_harness_candidate_x.pyc", "league/tests/test_harness_candidate_x/y.py",
                         "league/tests/test_harness_candidate_X.py", "league/tests/test_harness_candidate_a-b.py",
                         "league/tests/sub/test_harness_candidate_x.py", "league/tests/test_tool_x.py", "league/strategies/x.py"):
                self.assertTrue(ci.guard([path], role), (lane, path))
            for path in ("league/ci.py", "league/constitution.py", "league/ops/budget.py", "league/live/step.py", "gateway/lib/github.mjs",
                         ".github/workflows/checks.yml", "league/swarm/../ci.py"):
                self.assertTrue(ci.guard([path], role), (lane, path))
        # Nor does a lane's file or a new test reach any other role.
        for role in ("architect", "toolsmith", "operator", "designer", "teacher"):
            self.assertTrue(ci.guard(["league/swarm/loop.py"], role))
            self.assertTrue(ci.guard(["league/tests/test_harness_candidate_x.py"], role))

    def test_a_new_tests_name_is_bounded_as_the_gateways(self):
        """The name after `test_harness_candidate_` is 1 to 80 of a-z, 0-9 and `_`: the gateway's bound
        (`gateway/lib/github.mjs` ENGINEER_TEST), read from its source here so the two copies of the rule admit the same
        names."""
        import re

        source = (ci.REPO / "gateway" / "lib" / "github.mjs").read_text(encoding="utf-8")
        gateway = re.search(r"ENGINEER_TEST = /\^league\\/tests\\/test_harness_candidate_(.+?)\\\.py\$/;", source)
        self.assertIsNotNone(gateway, "gateway/lib/github.mjs declares ENGINEER_TEST")
        self.assertEqual(ci.ENGINEER_TEST_NAME, gateway.group(1))
        self.assertEqual(ci.ENGINEER_TEST_NAME, "[a-z0-9_]{1,80}")
        name = "league/tests/test_harness_candidate_{}.py"
        for lane in self.SURFACES:
            role = f"engineer/{lane}"
            self.assertEqual(ci.guard([name.format("x"), name.format("x" * 80), name.format("a_1" * 26 + "_z")], role), [], lane)
            for stem in ("", "x" * 81, "x" * 200):
                self.assertEqual(ci.guard([name.format(stem)], role),
                                 [f"{name.format(stem)}: outside what the {role} may change "
                                  f"({', '.join((*self.SURFACES[lane], ci.ENGINEER_TESTS))})"], (lane, len(stem)))

    def test_guard_branch_judges_an_engineer_branch_by_its_lane(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                                       *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

            git("init", "-q", "-b", "main")
            (root / "league" / "swarm").mkdir(parents=True)
            (root / "league" / "tests").mkdir()
            (root / "league" / "swarm" / "loop.py").write_text("A = 1\n")
            (root / "league" / "swarm" / "library.py").write_text("B = 1\n")
            (root / "league" / "swarm" / "models.py").write_text("C = 1\n")
            git("add", "-A")
            git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            (root / "league" / "swarm" / "loop.py").write_text("A = 2\n")
            (root / "league" / "tests" / "test_harness_candidate_loop.py").write_text("X = 1\n")
            git("add", "-A")
            git("commit", "-q", "-m", "lane")
            self.assertEqual(ci.guard_branch(base, "HEAD", "engineer/scheduler/faster-loop-0123abcd", root=root), [])
            self.assertEqual(ci.guard_branch(base, "HEAD", "engineer/research/faster-loop-0123abcd", root=root),
                             [f"league/swarm/loop.py: outside what the engineer/research may change "
                              f"({', '.join((*self.SURFACES['research'], ci.ENGINEER_TESTS))})"])
            self.assertEqual(ci.guard_branch(base, "HEAD", "engineer/faster-loop-0123abcd", root=root),
                             [f"engineer/faster-loop-0123abcd: not a branch name of the form {ci.BRANCH_FORMS}"])
            (root / "league" / "swarm" / "library.py").write_text("B = 2\n")
            git("commit", "-q", "-am", "outside")
            self.assertEqual(ci.guard_branch(base, "HEAD", "engineer/scheduler/faster-loop-0123abcd", root=root),
                             [f"league/swarm/library.py: outside what the engineer/scheduler may change "
                              f"(league/swarm/loop.py, {ci.ENGINEER_TESTS})"])
            # A path that feeds or enforces the budget is no lane's at all (FORBIDDEN, V3-A integration).
            (root / "league" / "swarm" / "models.py").write_text("C = 2\n")
            git("commit", "-q", "-am", "protected")
            self.assertIn("league/swarm/models.py: no role may change this file",
                          ci.guard_branch(base, "HEAD", "engineer/scheduler/faster-loop-0123abcd", root=root))

    def test_a_lane_may_only_add_a_test_never_change_remove_or_rename_one(self):
        """harness_lanes' NEW_TEST: an earlier candidate's retained test is never modified, removed or renamed away."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                                       *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

            git("init", "-q", "-b", "main")
            (root / "league" / "swarm").mkdir(parents=True)
            (root / "league" / "tests").mkdir()
            (root / "league" / "swarm" / "loop.py").write_text("A = 1\n")
            kept = root / "league" / "tests" / "test_harness_candidate_prior.py"
            kept.write_text("PINNED = 1\n")
            git("add", "-A")
            git("commit", "-q", "-m", "base")
            base = git("rev-parse", "HEAD")
            branch = "engineer/scheduler/faster-loop-0123abcd"
            (root / "league" / "tests" / "test_harness_candidate_new.py").write_text("X = 1\n")
            git("add", "-A")
            git("commit", "-q", "-m", "a new test")
            self.assertEqual(ci.guard_branch(base, "HEAD", branch, root=root), [])
            self.assertEqual(ci.engineer_test_problems(base, "HEAD", cwd=root), [])
            for change in ("modify", "remove", "rename"):
                git("checkout", "-q", "-B", change, base)
                if change == "modify":
                    kept.write_text("PINNED = 2\n")
                elif change == "remove":
                    kept.unlink()
                else:
                    kept.rename(root / "league" / "tests" / "test_harness_candidate_moved.py")
                git("add", "-A")
                git("commit", "-q", "-m", change)
                problems = ci.guard_branch(base, "HEAD", branch, root=root)
                self.assertIn("league/tests/test_harness_candidate_prior.py: an engineer lane may only add a new test, "
                              "never change or remove one", problems, change)
