"""Settings as code (V3-A, Oct 2, 2026; league/swarm/settings.py SETTINGS AS CODE, scripts/settings_migrate.py): the
repo's `league/swarm/policy.json` sits between config.json and `<state>/swarm.json`, the owner's switches are read
from swarm.json only, a missing policy.json changes nothing, and the migration moves swarm.json's research settings into
policy.json without changing the settings in effect. Every value here is invented, but for the committed file's own:
`TheCommittedPolicy` judges it by value and by the House's own loop."""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.ops import budget as B
from league.swarm import settings as S
from league.swarm.loop import Swarm
from league.swarm.seeds import SEEDS, family_spec
from league.swarm.store import SwarmStore
from league.tests import EMPTY_POLICY_PATH, REAL_POLICY_PATH
from league.tests import test_swarm_loop as L
from league.tests.swarm_fakes import Clock

REPO = Path(__file__).resolve().parents[2]


def migrate_module():
    spec = importlib.util.spec_from_file_location("settings_migrate", REPO / "scripts" / "settings_migrate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def swarm_json(self, doc):
        (self.root / "swarm.json").write_text(json.dumps(doc))


class TheLayer(Case):
    CONFIG = {"swarm": {"population": {"start": 40, "floor": 12}, "architect": {"every_seconds": 9000}}}

    def test_the_order_is_defaults_config_policy_swarm_json(self):
        self.swarm_json({"population": {"floor": 9}, "gym": {"max_boxes": 3}})
        policy = {"population": {"start": 20, "floor": 10}, "gym": {"max_boxes": 2, "start_boxes": 1},
                  "researcher": {"sail_usd_per_hour": 0.4}}
        with mock.patch.object(S, "budget_overlay", lambda out, root: out):  # the layers alone (the budget is its own test)
            out = S.load(self.root, config=self.CONFIG, policy=policy)
        self.assertEqual(out["population"], {**S.DEFAULTS["population"], "start": 20, "floor": 9})
        self.assertEqual((out["gym"]["max_boxes"], out["gym"]["start_boxes"]), (3, 1), "swarm.json over policy over defaults")
        self.assertEqual(out["architect"]["every_seconds"], 9000, "config.json where the policy says nothing")
        self.assertEqual(out["researcher"]["sail_usd_per_hour"], 0.4)
        self.assertEqual(out["_policy"], {"state": "ok", "why": None, "ignored": []})

    def test_the_owners_switches_are_never_read_from_the_policy(self):
        self.swarm_json({"enabled": False})
        out = S.load(self.root, config={}, policy={"enabled": True, "live": {"incubator": True}, "population": {"start": 12}})
        self.assertIs(out["enabled"], False)
        self.assertIs(out["live"]["incubator"], False)
        self.assertEqual(S.policy_layer({"live": None, "population": {"start": 12}})[1]["state"], "ok",
                         "an owner key is ignored, whatever its shape")
        self.assertEqual(out["population"]["start"], 12, "the rest of the policy holds")
        self.assertEqual(out["_policy"]["ignored"], ["enabled", "live"])
        self.assertIs(S.load(self.root, config={}, policy={"enabled": True})["enabled"], False)
        (self.root / "swarm.json").unlink()
        self.assertIs(S.load(self.root, config={}, policy={"enabled": True})["enabled"], False, "not even with no swarm.json")

    def test_a_missing_policy_file_is_no_layer(self):
        self.swarm_json({"population": {"floor": 9}})
        layer, status = S.read_policy(self.root / "nowhere.json")
        self.assertEqual((layer, status["state"]), ({}, "absent"))
        with mock.patch.object(S, "budget_overlay", lambda out, root: out):  # the layers alone (the budget holds the start)
            before = S.load(self.root, config=self.CONFIG, policy={})
        self.assertEqual(before["population"]["floor"], 9)
        self.assertEqual(before["population"]["start"], 40)

    def test_a_malformed_policy_file_is_ignored_and_says_why(self):
        for text in ("{not json", "[1, 2]", "null"):
            path = self.root / "policy.json"
            path.write_text(text)
            layer, status = S.read_policy(path)
            self.assertEqual((layer, status["state"]), ({}, "malformed"), text)
            self.assertTrue(status["why"])

    def test_a_policy_that_breaks_the_defaults_shape_is_dropped_whole(self):
        self.swarm_json({})
        for doc, path in (({"gym": None, "population": {"start": 12}}, "gym"), ({"researcher": 0.4}, "researcher"),
                          ({"gate": {"look_holds": 0.3}}, "gate.look_holds"), ({"population": {"start": {"n": 1}}},
                                                                               "population.start"),
                          ({"claude": {"role_model": []}}, "claude.role_model")):
            layer, status = S.policy_layer(doc)
            self.assertEqual((layer, status["state"]), ({}, "malformed"), doc)
            self.assertIn(path, status["why"])
            with mock.patch.object(S, "budget_overlay", lambda out, root: out):  # the layers alone, as above
                out = S.load(self.root, config={}, policy=doc)
            self.assertEqual(out["_policy"]["state"], "malformed")
            self.assertIsInstance(out["gym"], dict)
            self.assertIsInstance(out["researcher"], dict)
            self.assertEqual(out["population"]["start"], S.DEFAULTS["population"]["start"], "nothing of it is read")

    def test_a_documented_null_a_key_without_a_default_and_a_note_are_the_policys_to_set(self):
        doc = {"sail_fallback": None, "gate": {"look_holds": None}, "allocation": {"mode": "x"}, "_about": 3,
               "architect": {"openai_model": None}, "gym": {"train_split": None}}
        layer, status = S.policy_layer(doc)
        self.assertEqual(status["state"], "ok")
        out = S.load(None, config={}, policy=doc)
        self.assertIsNone(out["sail_fallback"])
        self.assertIsNone(out["gate"]["look_holds"])

    def test_the_repo_policy_file_is_read_by_default(self):
        self.assertEqual(REAL_POLICY_PATH, REPO / "league" / "swarm" / "policy.json")
        with mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH):  # the House's file, not the tests' empty layer
            layer, status = S.read_policy()
            self.assertEqual(status["state"], "ok", "the committed policy.json is a JSON object in the defaults' shape")
            self.assertEqual(S.policy_shape(json.loads(S.POLICY_PATH.read_text())), [])
            self.assertEqual(status["ignored"], [], "the committed policy.json never sets the owner's switches")
            with_repo, without = S.load(None, config={}), S.load(None, config={}, policy={})
        self.assertEqual(with_repo.pop("_policy"), status)
        without.pop("_policy")
        self.assertEqual(with_repo, S._merge(without, layer))

    def test_the_tests_read_a_layer_that_sets_nothing(self):
        self.assertEqual(S.POLICY_PATH, EMPTY_POLICY_PATH, "league/tests/__init__.py: never the House's settings")
        layer, status = S.read_policy()
        self.assertEqual(status, {"state": "ok", "why": None, "ignored": []})
        self.assertEqual([key for key in layer if not key.startswith("_")], [])
        with_layer, without = S.load(None, config={}), S.load(None, config={}, policy={})
        self.assertEqual({k: v for k, v in with_layer.items() if not k.startswith("_")},
                         {k: v for k, v in without.items() if not k.startswith("_")})

    def test_the_sail_fallback_default(self):
        self.assertEqual(S.DEFAULTS["sail_fallback"], {"k3_balanced": "pro_asap", "pro_balanced": "pro_asap"})
        self.assertEqual(S.DEFAULTS["sail_fallback_same_model"], ["audit"])

    def test_the_policy_file_is_a_protected_path_for_harness_candidates(self):
        from league.swarm import harness_lanes

        self.assertEqual(harness_lanes.protected_touch([("M", "league/swarm/policy.json")]),
                         ["M league/swarm/policy.json (sealed)"])


#: The plain values of DEFAULTS a null switches off, each documented where it is read (settings.py's comments on DEFAULTS;
#: architect.py and gate.py for their OpenAI models). A null anywhere else in the committed policy is no setting.
NULLS = frozenset({
    "researcher.top_profile", "researcher.hold_idle_seconds", "researcher.hold_idle_max_seconds",
    "researcher.retire_idle_evaluations", "researcher.dormant_cycles", "researcher.extension_hold_checks",
    "tournament.retire_every_seconds", "tournament.exploit_per_positive", "architect.max_alive_per_class",
    "architect.openai_model", "gate.review_openai_model", "gate.look_holds.drift_share", "gate.look_holds.min_power",
    "sail_fallback.k3_balanced", "sail_fallback.pro_balanced", "sail_fallback_same_model"})


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def wrong_kind(layer, defaults=S.DEFAULTS, prefix=""):
    """The paths where a policy layer's plain value is not of DEFAULTS' kind: a switch that is not JSON true or false; a
    number that is not a finite number of zero or more (text, a bool and a negative are none: the budget's overlay leaves
    such a value as it is, `league.ops.budget._tighten`); text or a list that is something else; a null outside `NULLS`.
    Blocks are `settings.policy_shape`'s; a key DEFAULTS lacks, or one whose default is null, is not judged."""
    bad = []
    for key, value in layer.items():
        if str(key).startswith("_") or key not in defaults or defaults[key] is None:
            continue
        path, default = f"{prefix}{key}", defaults[key]
        if isinstance(default, dict):
            bad += wrong_kind(value, default, f"{path}.") if isinstance(value, dict) else []
        elif value is None:
            bad += [] if path in NULLS else [path]
        elif isinstance(default, bool):
            bad += [] if isinstance(value, bool) else [path]
        elif number(default):
            bad += [] if number(value) and value >= 0 else [path]
        elif not isinstance(value, type(default)):
            bad.append(path)
    return bad


class TheCommittedPolicy(L.LoopCase):
    """The House's research settings as committed (`REAL_POLICY_PATH`): a pull request changes the file and the owner's
    deploy ships it (`league/ci.py` FORBIDDEN names it, so the updater ships no change to it), and the league's other
    tests read an empty layer in its place (league/tests/__init__.py). So it is judged here, by value and by the House's
    own loop, as the House reads it after the migration: config.json, the policy, and a swarm.json that holds the
    owner's switches alone. A policy that sets nothing passes (the file before the migration)."""

    def setUp(self):
        super().setUp()
        (self.root / "swarm.json").write_text(json.dumps({"enabled": True}))
        patch = mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH)
        patch.start()
        self.addCleanup(patch.stop)

    def test_every_value_it_sets_is_of_the_defaults_kind(self):
        doc = {"architect": {"every_seconds": None, "max_alive_per_class": None, "openai_model": None, "agenda": 3},
               "population": {"start": "sixteen", "ceiling": True, "floor": -1}, "gym": {"enabled": 1, "roots": "SPY"},
               "claude": {"usd_cap": float("inf"), "role_usd_day": {"strategist": "six", "review": "five"}},
               "gate": {"look_holds": None, "every_seconds": 300.5}, "researcher": {"probe_year": "x"}, "_note": 1}
        self.assertEqual(wrong_kind(doc), ["architect.every_seconds", "architect.agenda", "population.start",
                                           "population.ceiling", "population.floor", "gym.enabled", "gym.roots",
                                           "claude.usd_cap", "claude.role_usd_day.strategist"], "the judge itself")
        layer, status = S.read_policy()
        self.assertEqual(status["state"], "ok")
        self.assertEqual(wrong_kind(layer), [], "a switch is true or false, a number a finite number of zero or more, text "
                                                "is text, a list a list, and a null stands only where its reader takes one")
        population = S.load(None)["population"]
        self.assertLessEqual(population["floor"], population["start"])
        self.assertLessEqual(population["start"], population["ceiling"])

    def test_fast_lane_v2_switches_the_drift_screen_and_the_look_holds_off(self):
        """FAST LANE V2 (Oct 7, 2026; D2, direction counts): the committed policy turns the drift screen's refusal off and
        both look holds off (`gate.look_holds` null), and the House reads them so."""
        from league.swarm.gate import look_hold_settings
        from league.swarm.researcher import drift_settings

        layer, status = S.read_policy()
        self.assertEqual(status["state"], "ok")
        self.assertIs(layer["tournament"]["drift_screen"], False)
        self.assertIsNone(layer["gate"]["look_holds"])
        loaded = S.load(self.root)
        self.assertIsNone(loaded["gate"]["look_holds"])
        self.assertIs(loaded["tournament"]["drift_screen"], False)
        self.assertEqual(look_hold_settings(loaded), (None, None))
        self.assertIsNone(drift_settings(loaded))

    def test_it_sets_no_budget_and_loosens_no_line_of_the_guard(self):
        layer, _ = S.read_policy()
        self.assertNotIn("budget", layer, "THE BUDGET is never a setting: settings without a state root would carry it")
        with_policy, without = S.load(None)["guard"], S.load(None, policy={})["guard"]
        for line in ("house_burn_usd_day", "margin_usd", "openai_reserve_usd"):
            # The Sail guard's brake line, the budget rule's fixed cost and the OpenAI month's reserve: the release's own
            # (settings.py, the owner's deploy) or tighter.
            self.assertGreaterEqual(with_policy[line], without[line], f"guard.{line}")
        from league.swarm.guard import house_line

        # The line a braked guard releases at is THE BUDGET's Sail reserve (league/ops/budget.py): the release's own or higher.
        self.assertGreaterEqual(house_line(with_policy)["release"], house_line(without)["release"])
        self.assertEqual(house_line(with_policy), {"house": 1.0, "line": 32.0, "release": 37.0})

    def test_the_budget_binds_it(self):
        loaded = S.load(self.root)  # no budget.json: the floor
        block = loaded["budget"]
        self.assertEqual((block["source"], block["sail_usd_day"], block["claude_usd_day"]),
                         ("floor", B.floor_usd_day("sail"), B.floor_usd_day("claude")))
        knobs, researcher = block["knobs"], loaded["researcher"]
        pace = researcher["usd_per_hour"] if researcher["sail_usd_per_hour"] is None else researcher["sail_usd_per_hour"]
        self.assertLessEqual(pace, knobs["researcher.sail_usd_per_hour"])
        self.assertLessEqual(loaded["gym"]["max_boxes"], knobs["gym.max_boxes"])
        self.assertLessEqual(loaded["population"]["ceiling"], knobs["population.ceiling"])
        self.assertGreaterEqual(loaded["architect"]["every_seconds"], knobs["architect.every_seconds"])
        self.assertEqual(loaded["guard"]["openai_cap_usd"], 0.0, "no OpenAI room under the budget")
        lines = loaded["claude"]["role_usd_day"]
        self.assertEqual([r for r in loaded["claude"]["roles"] if r not in lines], [], "a line for every role Claude answers")
        self.assertEqual({r: v for r, v in lines.items() if not (number(v) and 0 <= v <= knobs["claude.role_usd_day"])}, {},
                         "no role's Claude line is over the budget's, and none is a value the overlay leaves alone")

    def at_usd_day(self, total):
        """The settings the House loads with the budget at `total` dollars a day (split as the rule splits them)."""
        import time

        (self.root / "budget.json").write_text(json.dumps({"schema": B.SCHEMA, "at": time.time() - 60, "meters": {
            "sail": {"research_usd_day": total * B.SPLIT["sail"], "fixed_usd_day": 1.0},
            "claude": {"research_usd_day": total * B.SPLIT["claude"]}}}))
        loaded = S.load(self.root)
        self.assertEqual(loaded["budget"]["source"], "budget.json")
        return loaded

    def test_at_the_owners_ceiling_it_lets_the_budget_reach_its_knobs(self):
        """The budget only tightens, so the policy's own values are caps it works inside. At the owner's $25 a day they
        let it reach what those dollars buy: seven Gym boxes, the Sail model pace, the policy's own architect cadences
        (never the floor's four hours), 25 families and the start of 16. (Sail's $20 since the operator's split of Oct 9,
        2026: the policy's caps were five boxes and 0.25 an hour, what $15 bought.)"""
        loaded = self.at_usd_day(B.CEILING_USD_DAY)
        knobs = B.knobs(20.0, 5.0)
        self.assertEqual((loaded["budget"]["sail_usd_day"], loaded["budget"]["claude_usd_day"]), (20.0, 5.0))
        self.assertEqual((loaded["gym"]["max_boxes"], knobs["gym.max_boxes"]), (7, 7), "floor(20 x 0.6 / 1.6)")
        self.assertEqual((loaded["researcher"]["sail_usd_per_hour"], knobs["researcher.sail_usd_per_hour"]),
                         (0.333333, 0.333333), "20 x 0.4 / 24, under the policy's 0.34")
        self.assertEqual((loaded["architect"]["every_seconds"], loaded["architect"]["refill_seconds"]), (7200, 1200),
                         "the policy's own cadences: the budget's (2880 and 1152 s) are faster, so it holds neither back")
        self.assertEqual((loaded["population"]["floor"], loaded["population"]["start"], loaded["population"]["ceiling"]),
                         (8, 16, 25))
        layer, _ = S.read_policy()
        for path, cap, knob in (("gym.max_boxes", layer["gym"]["max_boxes"], knobs["gym.max_boxes"]),
                                ("researcher.sail_usd_per_hour", layer["researcher"]["sail_usd_per_hour"],
                                 knobs["researcher.sail_usd_per_hour"]),
                                ("population.ceiling", layer["population"]["ceiling"], knobs["population.ceiling"])):
            self.assertGreaterEqual(cap, knob, f"{path}: the policy's cap is not under what the ceiling's dollars buy")
        for path, cadence, knob in (("every_seconds", layer["architect"]["every_seconds"], knobs["architect.every_seconds"]),
                                    ("refill_seconds", layer["architect"]["refill_seconds"], knobs["architect.refill_seconds"])):
            self.assertGreaterEqual(cadence, knob, f"architect.{path}: the budget does not slow the policy's cadence")
        caps = B.sail_caps(loaded)
        self.assertEqual((caps["research"], caps["account"], caps["gate_reserve"]), (20.0, 21.0, 2.0))

    def test_an_operators_tighter_setting_stands_under_the_ceiling(self):
        """swarm.json may run the swarm under what the ceiling's dollars buy (the budget only tightens, and so may the
        operator): fewer boxes and a lower population ceiling stand, and with the start at that ceiling (not held down by
        the budget) the policy's own cadences stand too."""
        (self.root / "swarm.json").write_text(json.dumps({"enabled": True, "population": {"ceiling": 16}, "gym": {"max_boxes": 2}}))
        loaded = self.at_usd_day(B.CEILING_USD_DAY)
        self.assertEqual((loaded["gym"]["max_boxes"], loaded["population"]["ceiling"], loaded["population"]["start"]), (2, 16, 16))
        self.assertEqual((loaded["architect"]["every_seconds"], loaded["architect"]["refill_seconds"]), (7200, 1200))
        self.assertEqual(loaded["researcher"]["sail_usd_per_hour"], 0.333333)
        self.assertEqual(B.sail_caps(loaded)["research"], 20.0, "the day's cap is the rule's, whatever the knobs are")

    def test_the_paid_model_lines_are_the_gates_and_the_strategists(self):
        """Claude's $5 a day at the ceiling (the operator's split of Oct 9, 2026; $10 before): the gate's review and audit
        and the strategist have a line; the researchers, the rewrites, the diagnostician and the architect have none (the
        stronger models bought no Validation pass). The strategist's $3 (it was $6) leaves the gate's two holds inside the
        $5. The House's weekly post-mortem (league/ops/postmortem.py) keeps its own $1 line from the defaults: the job
        serves its role itself, one call a week."""
        lines = self.at_usd_day(B.CEILING_USD_DAY)["claude"]["role_usd_day"]
        self.assertEqual({r: v for r, v in lines.items() if v}, {"review": 5.0, "audit": 5.0, "strategist": 3.0,
                                                                 "postmortem": 1.0})
        self.assertEqual({r for r, v in lines.items() if not v}, {"architect", "researcher", "rewrite", "diagnostician"})
        for role, hold in B.GATE_HOLDS_USD.items():
            self.assertGreaterEqual(lines[role], hold, f"{role}: its line holds its hold")
        self.assertLessEqual(lines["strategist"], B.ceiling_usd_day("claude") - sum(B.GATE_HOLDS_USD.values()),
                             "what the strategist may take leaves the gate's holds")

    def test_the_gates_holds_cover_what_the_router_books(self):
        """THE GATE'S HOLDS (`budget.GATE_HOLDS_USD`, kept inside the day's Claude line by stage) are sized by what the
        router really books for the gate's review and audit on this policy: the larger of the call's need and its
        request's own worst case (`claude_request`), for the largest program the Gym accepts."""
        from league.gym.safety import MAX_CODE_CHARS
        from league.swarm import gate as G
        from league.swarm.models import ModelRouter

        loaded = self.at_usd_day(B.CEILING_USD_DAY)
        router = ModelRouter(self.store, None, settings=loaded, claude_factory=lambda model: None, claude_meter=None)
        program = ("x = 1\n" * MAX_CODE_CHARS)[:MAX_CODE_CHARS]  # a newline every six characters: more bytes than code is
        contract = json.dumps(G.gate_contract(), sort_keys=True)
        needs = {"review": 0.5, "audit": float(loaded["gate"].get("audit_need_usd", 1.0))}  # league/swarm/gate.py's own
        for head, role, effort in (("", "review", "medium"), ("AUDIT. ", "audit", "high")):
            user = (f"{head}Family f0123456789ab: {'a mechanism in words. ' * 20}\nStructure debit_vertical, roots SPY, QQQ.\n\n"
                    f"Runtime contract (actual deployed source): {contract}\n\n```python\n{program}\n```\nPARAMS overrides: {{}}")
            _, worst = router.claude_request(G.REVIEW, user, effort=effort, role=role)
            self.assertGreater(worst, needs[role], f"{role}: for a program this large the request's worst case is the hold")
            self.assertLessEqual(max(needs[role], worst), B.GATE_HOLDS_USD[role], f"{role}: the hold the router books")
        self.assertEqual(B.GATE_STAGES, ("review", "audit"), "the gate's order: the review leaves the audit's hold")

    def test_fewer_dollars_tighten_every_knob(self):
        """$12, $5 and $1 a day on the committed policy: (boxes, pace, ceiling, start, every, refill, each Claude line)."""
        want = {12.0: (3, 0.16, 12, 12, 7200, 6000, 2.4), 5.0: (1, 0.066667, 12, 12, 14400, 14400, 1.0),
                1.0: (1, 0.013333, 12, 12, 72000, 72000, 0.2)}
        for total, (boxes, pace, ceiling, start, every, refill, line) in want.items():
            loaded = self.at_usd_day(total)
            self.assertEqual((loaded["gym"]["max_boxes"], loaded["researcher"]["sail_usd_per_hour"]), (boxes, pace), total)
            self.assertEqual((loaded["population"]["ceiling"], loaded["population"]["start"]), (ceiling, start), total)
            # The budget's ceiling is under the policy's start of 16: every pass is a refill, held to the scheduled cadence.
            self.assertEqual((loaded["architect"]["every_seconds"], loaded["architect"]["refill_seconds"]), (every, refill), total)
            lines = loaded["claude"]["role_usd_day"]
            self.assertEqual((lines["review"], lines["audit"], lines["strategist"]), (line, line, line), total)

    def test_the_houses_loop_runs_on_it(self):
        with contextlib.redirect_stdout(io.StringIO()):
            sw = Swarm(self.root, store=self.store, router=self.router, pool=self.pool, guard=self.guard,
                       sleep=lambda s: None)  # the settings are its own load
            self.router.settings = self.pool.settings = sw.settings  # as in the House: every piece reads the Swarm's dict
            ready = sw.gym_ready()
            born = sw.seed()
            for spec in SEEDS:  # a full population first (THE STRUCTURES may found fewer than the start)
                if sw.architect.refilling() and spec["id"] not in born:
                    self.store.add_family(family_spec(spec), origin="seed")
            sw.step()  # the notices, the guard, the pool, the gate, the architect's own cadence
            self.join_rounds()
            self.store.put("tournament_at", 0.0)
            sw.step()  # the tournament is due
            self.join_rounds()
            for fam in self.store.families(alive=True)[:2]:
                self.store.retire(fam["id"], "test")
            self.store.put("architect_at", 0.0)
            sw.step()  # fewer alive than the start: the architect refills
            self.join_rounds()
        self.assertEqual(sw.settings["_policy"], {"state": "ok", "why": None, "ignored": []})
        self.assertEqual(sw.settings["budget"]["source"], "floor")
        self.assertEqual({"gate", "tournament", "architect"} <= set(sw.rounds), ready,
                         "with the Gym on, the rounds ran on the policy's settings (with it off, none starts)")
        failed = [e["payload"] for e in self.store.events_after(0, limit=10_000)
                  if e["kind"] == "swarm.status" and (e["payload"] or {}).get("error")]
        self.assertEqual(failed, [], "no round raised")


#: What the House runs: `python -m league` (the House, with its watchdog and its updater), the swarm's process, the ops
#: runner and the live path. A package stands for every module under it: the runner imports its jobs by name
#: (`league.ops.registry`), and the live path's decider is a process of its own.
HOUSE_ENTRIES = ("league.__main__", "league.house", "league.watchdog", "league.updater", "league.ops", "league.swarm.loop",
                 "league.swarm.__main__", "league.live")
TESTS = "league.tests"


def module_file(name: str, repo: Path = REPO) -> Path | None:
    """The repository file of module `name` (a/b.py, else a/b/__init__.py); None for a module that is not the repository's."""
    base = repo.joinpath(*name.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def imported(name: str, path: Path) -> set[str]:
    """Every module name the import statements of `path` (module `name`) can load, wherever they stand (an import inside
    a function runs when the function does), with `import_module("...")` and `__import__("...")` of a literal name."""
    package = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > len(package):
                continue
            base = package[: len(package) - node.level + 1] if node.level else []
            target = ".".join(base + (node.module.split(".") if node.module else []))
            if target:
                found.add(target)
                found.update(f"{target}.{alias.name}" for alias in node.names)  # `from a import b`: b may be a module
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            called = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if called in ("import_module", "__import__") and isinstance(node.args[0].value, str):
                found.add(node.args[0].value)
    return found


def import_closure(entries, repo: Path = REPO) -> dict[str, str | None]:
    """{module: the module that first led to it} for every repository module reachable from `entries` by static imports;
    a package entry brings every module under it, and a module brings its parent packages (their `__init__` runs first)."""
    todo: list[tuple[str, str | None]] = []
    for entry in entries:
        path = module_file(entry, repo)
        todo.append((entry, None))
        if path is not None and path.name == "__init__.py":
            for sub in sorted(path.parent.rglob("*.py")):
                parts = sub.relative_to(repo).with_suffix("").parts
                todo.append((".".join(parts[:-1] if parts[-1] == "__init__" else parts), entry))
    reached: dict[str, str | None] = {}
    while todo:
        name, via = todo.pop()
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            module = ".".join(parts[:i])
            path = module_file(module, repo)
            if path is None or module in reached:
                continue
            reached[module] = via
            todo.extend((dep, module) for dep in imported(module, path))
    return reached


class TheHouseNeverImportsTheTests(unittest.TestCase):
    """Importing `league.tests` is what switches the suite's isolation on (league/tests/__init__.py): it points
    `settings.POLICY_PATH` at a layer that sets nothing and `niches.NICHES_PATH` at the pre-overhaul desks, for the whole
    process. In a process of the House that would empty the policy layer in production: the swarm would run on
    settings.py's DEFAULTS, not the research settings the owner deployed, and nothing would say so. So no module the
    House can import may import `league.tests` or anything under it: the import closure of the House's entry points is
    walked here by their source (static AST, imports inside functions too) and must not reach it. Two files outside
    that closure do import the tests' fakes today: league/swarm/harness_judges/execution.py (a harness judge, run in
    its own sandboxed process on a candidate's tree) and scripts/verify_learning_gates.py (a laptop tool)."""

    def test_the_closure_of_the_houses_entry_points_never_reaches_the_tests(self):
        from league.ops.registry import JOBS

        for entry in HOUSE_ENTRIES:
            self.assertIsNotNone(module_file(entry), f"{entry} is one of the House's entry points")
        reached = import_closure((*HOUSE_ENTRIES, *sorted({job.module for job in JOBS})))  # a job is imported by name
        for module in ("league.swarm.settings", "league.niches", "league.swarm.loop", "league.live.step", "league.ops.budget",
                       "league.ops.__main__", "league.updater", "league.ci"):
            self.assertIn(module, reached, "the walk covers what the House runs")
        self.assertGreater(len(reached), 150)

        def chain(module):
            out = [module]
            while reached.get(out[-1]) is not None:
                out.append(reached[out[-1]])
            return " <- ".join(out)

        self.assertEqual([chain(m) for m in sorted(reached) if m == TESTS or m.startswith(TESTS + ".")], [],
                         "a module the House can import imports league.tests: the policy layer would be emptied in production")

    def test_the_walk_sees_an_import_wherever_it_stands(self):
        """The judge of the walk itself, on a planted tree: a relative import inside a function, a `from` import of a
        submodule, a literal `import_module`, a package entry's modules and a parent package's `__init__`."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            files = {"league/__init__.py": "", "league/house.py": "from . import clean\n", "league/clean.py": "import json\n",
                     "league/tests/__init__.py": "", "league/tests/fakes.py": "",
                     "league/lazy.py": "def f():\n    from .tests import fakes\n",
                     "league/named.py": "import importlib\nM = importlib.import_module('league.tests')\n",
                     "league/ops/__init__.py": "", "league/ops/job.py": "from league.tests.fakes import X\n",
                     "league/deep/__init__.py": "from .. import tests\n", "league/deep/leaf.py": "",
                     "league/far.py": "import league.deep.leaf\n"}
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text)
            self.assertEqual(sorted(import_closure(["league.house"], repo)), ["league", "league.clean", "league.house"])
            for entry in ("league.lazy", "league.named", "league.ops", "league.far"):
                self.assertIn(TESTS, import_closure([entry], repo), entry)
            self.assertIn("league.tests.fakes", import_closure(["league.lazy"], repo))


class TheNotice(Case):
    def swarm(self):
        store = SwarmStore(self.root, clock=Clock())
        self.addCleanup(store.close)
        swarm = Swarm.__new__(Swarm)  # only the notice's parts: no threads, no pool, no router
        swarm.store = store
        return swarm

    def test_a_malformed_or_overreaching_policy_alerts_once_and_a_missing_one_never(self):
        swarm = self.swarm()
        swarm.settings = {"_policy": {"state": "absent", "why": None, "ignored": []}}
        self.assertIsNone(swarm.policy_notice())
        swarm.settings = {"_policy": {"state": "ok", "why": None, "ignored": []}}
        self.assertIsNone(swarm.policy_notice())
        swarm.settings = {"_policy": {"state": "malformed", "why": "JSONDecodeError: x", "ignored": []}}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            first = swarm.policy_notice()
            again = swarm.policy_notice()
            swarm.settings = {"_policy": {"state": "ok", "why": None, "ignored": ["live"]}}
            owner = swarm.policy_notice()
        self.assertEqual((first["action"], first["alert"]), ("policy_layer", True))
        self.assertIn("not read", first["text"])
        self.assertIsNone(again, "once per distinct problem")
        self.assertIn("live", owner["text"])
        alerts = [e for e in swarm.store.events_after(0) if e["kind"] == "swarm.status"]
        self.assertEqual(len(alerts), 2)


class TheMigration(Case):
    CONFIG = {"swarm": {"population": {"start": 40}}}
    SWARM = {"enabled": True, "_note": "operator note", "live": {"observe": True, "observe_max": 24, "incubator": True},
             "population": {"start": 16, "floor": 8}, "architect": {"every_seconds": 7200, "openai_model": None,
                                                                    "_why": "a private aside"},
             "researcher": {"sail_usd_per_hour": 0.4}, "gym": {"max_boxes": 2, "image_checkpoint": "sbcp_test-1"},
             "claude": {"role_usd_day": {"researcher": 0.0}}}

    def setUp(self):
        super().setUp()
        self.m = migrate_module()

    def test_the_plan_moves_research_settings_keeps_the_owners_and_changes_nothing_in_effect(self):
        policy = {"_about": "the file's note", "population": {"ceiling": 16}, "gym": {"max_boxes": 4}}
        out = self.m.plan(self.SWARM, policy=policy, config=self.CONFIG)
        self.assertEqual(out["swarm"], {"enabled": True, "_note": "operator note",
                                        "live": {"observe": True, "observe_max": 24, "incubator": True}})
        self.assertEqual(out["policy"]["_about"], "the file's note")
        self.assertEqual(out["policy"]["population"], {"ceiling": 16, "start": 16, "floor": 8})
        self.assertEqual(out["policy"]["gym"]["max_boxes"], 2, "swarm.json's value was the one in effect")
        self.assertIsNone(out["policy"]["architect"]["openai_model"], "a null is a setting too")
        self.assertNotIn("_why", out["policy"]["architect"], "a nested note never goes into the public file")
        self.assertEqual(out["notes_left_out"], ["architect._why"])
        self.assertNotIn("enabled", out["policy"])
        self.assertNotIn("live", out["policy"])
        self.assertIn("gym.max_boxes", out["changed"])
        self.assertNotIn("population.ceiling", out["moved"])
        self.assertEqual(out["dollar_lines"], ["claude.role_usd_day.researcher", "researcher.sail_usd_per_hour"])
        self.assertEqual(out["blocks_without_defaults"], [])
        self.assertEqual(self.m.plan({"allocation": {"mode": "x"}}, policy={}, config={})["blocks_without_defaults"],
                         ["allocation"], "read by its module, not settings.py: listed for a look, still moved")
        # The proof the plan rests on, checked again here: the same settings before and after.
        for name in ("swarm.json",):
            (self.root / name).write_text(json.dumps(self.SWARM))
        before = S.load(self.root, config=self.CONFIG, policy=policy)
        (self.root / "swarm.json").write_text(json.dumps(out["swarm"]))
        after = S.load(self.root, config=self.CONFIG, policy=out["policy"])
        before.pop("_policy"), after.pop("_policy")
        self.assertEqual(before, after)

    def test_refusals(self):
        with self.assertRaisesRegex(self.m.MigrationError, "not a JSON object"):
            self.m.plan([1], policy={}, config={})
        with self.assertRaisesRegex(self.m.MigrationError, "credentials"):
            self.m.plan({"gateway": {"api_key": "x"}}, policy={}, config={})
        with self.assertRaisesRegex(self.m.MigrationError, "credentials"):
            self.m.plan({"architect": {"agenda": "sk-abc123"}}, policy={}, config={})
        with self.assertRaisesRegex(self.m.MigrationError, "owner"):
            self.m.plan({}, policy={"enabled": True}, config={})
        with self.assertRaisesRegex(self.m.MigrationError, "would change"):
            # A block the policy holds as null and swarm.json as an object merges differently once moved: refused.
            self.m.plan({"gate": {"look_holds": {"drift_share": 0.3}}}, policy={"gate": {"look_holds": None}}, config={})
        with self.assertRaisesRegex(self.m.MigrationError, "shape"):
            self.m.plan({"researcher": 0.4}, policy={}, config={})
        with self.assertRaisesRegex(self.m.MigrationError, "gateway_token"):
            self.m.plan({"gateway_token": "x"}, policy={}, config={})
        counts = {"architect": {"max_output_tokens": 9000, "graveyard_digest_tokens": 50000}}
        self.assertEqual(self.m.plan(counts, policy={}, config={})["policy"], counts, "a count of tokens is no credential")

    def run_tool(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.m.main(list(args))
        return code, json.loads(out.getvalue())

    def test_a_dry_run_writes_nothing_and_apply_writes_both_files(self):
        swarm, policy, config = self.root / "swarm.json", self.root / "policy.json", self.root / "config.json"
        swarm.write_text(json.dumps(self.SWARM))
        config.write_text(json.dumps(self.CONFIG))
        common = ("--swarm", str(swarm), "--policy", str(policy), "--config", str(config))
        code, report = self.run_tool(*common)
        self.assertEqual((code, report["apply"]), (0, False))
        self.assertFalse(policy.exists())
        self.assertFalse((self.root / "swarm.reduced.json").exists())
        self.assertEqual(json.loads(swarm.read_text()), self.SWARM, "the copy is never touched")
        code, report = self.run_tool(*common, "--apply")
        self.assertEqual(code, 0)
        written = json.loads(policy.read_text())
        self.assertEqual(written["population"], {"start": 16, "floor": 8})
        self.assertEqual(sorted(json.loads((self.root / "swarm.reduced.json").read_text())), ["_note", "enabled", "live"])
        self.assertEqual(json.loads(swarm.read_text()), self.SWARM)
        self.assertIn("cleared its watch", report["order"])
        self.assertIn("rollback to a release without league/swarm/policy.json", report["rollback"])
        code, report = self.run_tool(*common, "--swarm-out", str(swarm), "--apply")
        self.assertEqual(code, 2)
        self.assertIn("keep it", report["refused"])
        self.assertEqual(json.loads(swarm.read_text()), self.SWARM, "the original is never overwritten")
        swarm.write_text("[]")
        code, report = self.run_tool(*common, "--apply")
        self.assertEqual(code, 2)
        self.assertIn("refused", report)


if __name__ == "__main__":
    unittest.main()
