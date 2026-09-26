"""The options House (the options overhaul, Sept 26, 2026, Wave 2a): `service.build` makes only the options
pieces, the tick runs no branch of a cut feature, and two pluggable steps wait for the swarm (Wave 4) and the
live options path (Wave 5).

Built here exactly as the floor builds it (`service.build`), over fake brokers and no network."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from league import service
from league.live_trading import LiveGrant
from league.tests.fakes import FakeBroker

#: What the options House never builds (plan "The prune": Kalshi, Jev, the lab, the foundry, the semantic lab, the
#: feeds and recorders, the campaign store and its burst).
CUT_PIECES = ("campaigns", "feeds", "jev_floor", "lab", "hypotheses", "semantic_lab", "shards", "kalshi_data")


def no_network(*args, **kwargs):
    raise OSError("no network in tests")


class BuildCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)  # registered first, so it runs after every House is closed
        self.made: list[tuple[str, dict]] = []

    def broker(self, venue, **kwargs):
        self.made.append((venue, kwargs))
        return FakeBroker(venue)

    def build(self, *, real_money=False, config=None, sail=None, **kw):
        config = {**service.load_config(), "options_history": False, **(config or {}), "real_money": real_money}
        patches = [patch.object(service, "load_env"), patch.object(service, "secret", return_value="t" * 40),
                   patch("league.venues.gateway_broker", side_effect=self.broker),
                   patch("urllib.request.urlopen", side_effect=no_network)]
        if sail is not None:
            patches.append(patch("league.sailbox.SailboxClient", return_value=sail))
        for p in patches:
            p.start()
        try:
            options = dict(research=False, publish=False, merton=False, local_sandbox=sail is None)
            options.update(kw)
            house = service.build(Path(self.dir.name) / "state", config=config, **options)
        finally:
            for p in reversed(patches):
                p.stop()
        self.addCleanup(house.close, wait=None)
        return house


class Build(BuildCase):
    def test_practice_books_only_without_real_money_and_no_cut_piece(self):
        house = self.build(research=True, merton=True, publish=True)
        self.assertEqual(list(house.books), ["alpaca-paper", "options-shadow"])
        for name in CUT_PIECES:
            self.assertIsNone(getattr(house, name, None), name)
        self.assertEqual((house.swarm, house.options_live), (None, None))
        self.assertIsInstance(house.grant, LiveGrant)
        self.assertEqual(house.grant.path.name, "live-grant.sqlite")
        self.assertFalse(house.settings.credit_economy)
        self.assertEqual((house.settings.deep_replay, house.settings.holdout_gate, house.settings.lab_box,
                          house.settings.kalshi_founders, house.settings.niche_survey_hours), (False, False, "", False, 0.0))
        self.assertIsNone(house.researcher.jev if hasattr(house.researcher, "jev") else None)
        self.assertIsNone(getattr(house.researcher, "traces", None))
        self.assertIsNone(getattr(house.researcher, "grants", None))
        self.assertEqual(sorted(house.publisher.real_brokers), ["alpaca"], "the balance is the Brokerage Account's alone")
        self.assertNotIn("kalshi", [venue for venue, _ in self.made])
        self.assertFalse((Path(self.dir.name) / "state" / "campaigns.sqlite").exists())

    def test_real_money_adds_the_brokerage_account_and_market_data_reads_through_it(self):
        from league.tests.test_sandbox import FakeSail

        with patch("ltcm.adapters.VenueClient") as client:
            house = self.build(real_money=True, sail=FakeSail())
        self.assertEqual(list(house.books), ["alpaca-paper", "alpaca", "options-shadow"])
        self.assertTrue(house.books["alpaca"].real_money)
        self.assertIsNotNone(house.kill_switch)
        self.assertEqual({kw["venue"] for _, kw in client.call_args_list}, {"alpaca"}, "market data reads through the real account")
        self.assertFalse(house.grant.allows_live(2), "an empty root has no grant: no real entry")

    def test_without_real_money_market_data_reads_through_the_practice_account(self):
        with patch("ltcm.adapters.VenueClient") as client:
            self.build(real_money=False)
        self.assertEqual({kw["venue"] for _, kw in client.call_args_list}, {"alpaca-paper"})

    def test_no_absent_key_switches_a_cut_feature_on(self):
        config = {k: v for k, v in service.load_config().items()
                  if k not in ("feeds", "jev", "lab", "semantic_lab", "research_traces", "kalshi_founders", "deep_replay",
                               "holdout_gate", "auto_update")}
        house = self.build(config=config, research=True, merton=True)
        for name in CUT_PIECES:
            self.assertIsNone(getattr(house, name, None), name)
        self.assertIsNone(house.updater)
        source = inspect.getsource(service.build)
        for key in ("feeds", "jev", "semantic_lab", "research_traces", "kalshi_founders", "lab", "deep_replay", "holdout_gate"):
            self.assertNotIn(f'config.get("{key}"', source, key)

    def test_a_canary_is_practice_only_and_builds_nothing_cut(self):
        house = self.build(real_money=True, canary=True)
        self.assertEqual(list(house.books), ["alpaca-paper", "options-shadow"])
        for name in CUT_PIECES:
            self.assertIsNone(getattr(house, name, None), name)


class Step:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def tick(self, house, *, open_for_business):
        self.calls.append(open_for_business)
        if self.fail:
            raise RuntimeError("a step that breaks")
        return {"ran": len(self.calls)}


class PluggableSteps(BuildCase):
    def test_each_step_runs_once_a_tick_with_its_lap_and_its_summary(self):
        house = self.build()
        house.swarm, house.options_live = Step(), Step()
        summary = house.tick()
        self.assertEqual((house.swarm.calls, house.options_live.calls), ([True], [True]))
        self.assertEqual((summary["swarm"], summary["options_live"]), ({"ran": 1}, {"ran": 1}))
        steps = house._tick_last["steps"]
        self.assertIn("swarm", steps)
        self.assertIn("options_live", steps)
        order = list(steps)
        self.assertLess(order.index("options_live"), order.index("allocator"), "the live path runs before the mark pass")
        self.assertLess(order.index("research"), order.index("swarm"))

    def test_a_failing_step_is_a_warning_and_the_tick_goes_on(self):
        house = self.build()
        house.swarm = Step(fail=True)
        summary = house.tick()
        self.assertNotIn("swarm", summary)
        self.assertIn("publish", house._tick_last["steps"])
        texts = [e.payload["text"] for e in house.ledger.iter(kinds="ops.alert")]
        self.assertTrue(any("the swarm step failed" in t for t in texts), texts)

    def test_a_paused_house_tells_the_steps_it_is_not_open_for_business(self):
        house = self.build()
        house.swarm = Step()
        with patch.object(type(house), "paused", return_value={"reason": "maintenance"}):
            house.tick()
        self.assertEqual(house.swarm.calls, [False])

    def test_unfilled_steps_run_nothing_and_health_says_which_are_filled(self):
        import json

        house = self.build()
        house.tick()
        self.assertNotIn("swarm", house._tick_last["steps"])
        health = json.loads((Path(self.dir.name) / "state" / "health.json").read_text())
        self.assertEqual(health["pluggable_steps"], {"options_live": False, "swarm": False})
        self.assertIs(health["credit_economy"], False)


if __name__ == "__main__":
    unittest.main()
