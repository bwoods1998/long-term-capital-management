"""Settings as code (V3-A, Oct 2, 2026; league/swarm/settings.py SETTINGS AS CODE, scripts/settings_migrate.py): the
repo's `league/swarm/policy.json` sits between config.json and `<state>/swarm.json`, the owner's switches are read
from swarm.json only, a missing policy.json changes nothing, and the migration moves swarm.json's research settings into
policy.json without changing the settings in effect. Every value here is invented."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.loop import Swarm
from league.swarm.store import SwarmStore
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

    def test_the_repo_policy_file_is_read_by_default(self):
        layer, status = S.read_policy()
        self.assertEqual(status["state"], "ok", "the committed policy.json is a JSON object")
        self.assertEqual(status["ignored"], [], "the committed policy.json never sets the owner's switches")
        with_repo, without = S.load(None, config={}), S.load(None, config={}, policy={})
        self.assertEqual(with_repo.pop("_policy"), status)
        without.pop("_policy")
        self.assertEqual(with_repo, S._merge(without, layer))

    def test_the_sail_fallback_default(self):
        self.assertEqual(S.DEFAULTS["sail_fallback"], {"k3_balanced": "pro_asap", "pro_balanced": "pro_asap"})


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
            self.m.plan({"gate": {"every_seconds": 5}}, policy={"gate": None}, config={})
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
        swarm.write_text("[]")
        code, report = self.run_tool(*common, "--apply")
        self.assertEqual(code, 2)
        self.assertIn("refused", report)


if __name__ == "__main__":
    unittest.main()
