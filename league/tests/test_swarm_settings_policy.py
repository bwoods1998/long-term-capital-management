"""Settings as code (V3-A, Oct 2, 2026; league/swarm/settings.py SETTINGS AS CODE, scripts/settings_migrate.py): the
repo's `league/swarm/policy.json` sits between config.json and `<state>/swarm.json`, the owner's switches are read
from swarm.json only, a missing policy.json changes nothing, and the migration moves swarm.json's research settings into
policy.json without changing the settings in effect. Every value here is invented, but for the committed file's own:
`TheCommittedPolicy` judges it by value and by the House's own loop."""

from __future__ import annotations

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
    """The House's research settings as committed (`REAL_POLICY_PATH`): a pull request changes the file and the updater
    ships it, and the league's other tests read an empty layer in its place (league/tests/__init__.py). So it is judged
    here, by value and by the House's own loop, as the House reads it after the migration: config.json, the policy, and
    a swarm.json that holds the owner's switches alone. A policy that sets nothing passes (the file before the migration)."""

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

    def test_it_sets_no_budget_and_loosens_no_line_of_the_guard(self):
        layer, _ = S.read_policy()
        self.assertNotIn("budget", layer, "THE BUDGET is never a setting: settings without a state root would carry it")
        with_policy, without = S.load(None)["guard"], S.load(None, policy={})["guard"]
        for line in ("house_burn_usd_day", "margin_usd", "openai_reserve_usd"):
            # The Sail guard's brake line, the budget rule's fixed cost and the OpenAI month's reserve: the release's own
            # (settings.py, the owner's deploy) or tighter.
            self.assertGreaterEqual(with_policy[line], without[line], f"guard.{line}")

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
