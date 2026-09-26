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
from league.tests import REAL_NICHES_PATH
from league.tests.fakes import FakeBroker

#: What the options House never builds (plan "The prune": Kalshi, Jev, the lab, the foundry, the semantic lab, the
#: feeds and recorders, the campaign store and its burst).
CUT_PIECES = ("campaigns", "feeds", "jev_floor", "lab", "hypotheses", "semantic_lab", "shards", "kalshi_data")
#: The House as Wave 2a left it, before the live options path (Wave 5) owns the Alpaca accounts.
NO_LIVE = {"live": {"enabled": False}}
#: The live options path built but its minute thread never started (a test's House must not read a venue).
LIVE = {"live": {"enabled": True, "thread": False, "require_paper_proof": True}}


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
        # The House's real desks (league/niches.json: the options desk alone), not the old tests' legacy fixture.
        patches = [patch("league.niches.NICHES_PATH", REAL_NICHES_PATH),
                   patch.object(service, "load_env"), patch.object(service, "secret", return_value="t" * 40),
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
        house = self.build(research=True, merton=True, publish=True, config=NO_LIVE)
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
        self.assertEqual(house.publisher.broker.venue, "alpaca", "the balance is the Brokerage Account's alone")
        self.assertNotIn("kalshi", [venue for venue, _ in self.made])
        self.assertFalse((Path(self.dir.name) / "state" / "campaigns.sqlite").exists())

    def test_real_money_adds_the_brokerage_account_and_market_data_reads_through_it(self):
        from league.tests.test_sandbox import FakeSail

        with patch("ltcm.adapters.VenueClient") as client:
            house = self.build(real_money=True, sail=FakeSail(), config=NO_LIVE)
        self.assertEqual(list(house.books), ["alpaca-paper", "alpaca", "options-shadow"])
        self.assertTrue(house.books["alpaca"].real_money)
        self.assertIsNotNone(house.kill_switch)
        self.assertEqual({kw["venue"] for _, kw in client.call_args_list}, {"alpaca"}, "market data reads through the real account")
        self.assertFalse(house.grant.allows_live(2), "an empty root has no grant: no real entry")

    def test_without_real_money_market_data_reads_through_the_practice_account(self):
        with patch("ltcm.adapters.VenueClient") as client:
            self.build(real_money=False, config=NO_LIVE)
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
        house = self.build(real_money=True, canary=True, config=LIVE)
        self.assertEqual(list(house.books), ["alpaca-paper", "options-shadow"])
        self.assertIsNone(house.options_live, "a canary never runs the live path")
        for name in CUT_PIECES:
            self.assertIsNone(getattr(house, name, None), name)


class TheLivePath(BuildCase):
    """Wave 5 (Sept 26, 2026): with `live.enabled` the live options path owns both Alpaca accounts: no old Book is
    built for them, and `House.options_live` is the live step, reading and trading through the gateway only."""

    def setUp(self):
        super().setUp()
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed (the live path needs it)")

    def test_the_live_path_owns_the_alpaca_accounts(self):
        from league.live.step import OptionsLive

        with patch("ltcm.adapters.VenueClient") as client:
            house = self.build(real_money=False, config=LIVE)
        self.assertEqual(house.books, {})
        self.assertIsInstance(house.options_live, OptionsLive)
        self.assertIsNone(house.options_live.real, "no real account without real money")
        self.assertEqual(house.options_live.paper.venue, "alpaca-paper")
        self.assertIs(house.options_live.grant, house.grant)
        self.assertEqual({kw["venue"] for _, kw in client.call_args_list}, {"alpaca-paper"})
        self.assertTrue(all(isinstance(kw.get("gateway").headers(), dict) for _, kw in client.call_args_list if kw.get("gateway")))

    def test_with_real_money_it_trades_the_brokerage_account_and_reads_through_it(self):
        from league.tests.test_sandbox import FakeSail

        with patch("ltcm.adapters.VenueClient") as client:
            house = self.build(real_money=True, sail=FakeSail(), config=LIVE)
        self.assertEqual(house.books, {})
        self.assertEqual(house.options_live.real.venue, "alpaca")
        self.assertTrue(house.options_live.real_money)
        self.assertEqual({kw["venue"] for _, kw in client.call_args_list}, {"alpaca", "alpaca-paper"})
        self.assertEqual(house.options_live.real_block(), "the grant options-swarm-20260928 is not active on the money rules in force")

    def test_the_live_path_reads_the_swarms_families_when_the_swarm_is_on_in_the_state(self):
        from league.live.families import SwarmFamilies

        state = Path(self.dir.name) / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "swarm.json").write_text('{"enabled": true}')              # config.json says off; the state turns it on
        with patch("ltcm.adapters.VenueClient"):
            house = self.build(real_money=False, config=LIVE)
        self.assertIsNotNone(house.swarm)
        self.assertIsInstance(house.options_live.families, SwarmFamilies)
        self.assertEqual(house.options_live.families.root, state)

    def test_the_repositorys_config_runs_the_live_path(self):
        config = service.load_config()
        self.assertIs(config["live"]["enabled"], True)
        self.assertIs(config["live"]["require_paper_proof"], True)
        self.assertTrue(service.live_enabled(config))
        self.assertFalse(service.live_enabled(config, canary=True))


class TheConfigAfterThePrune(unittest.TestCase):
    def test_config_game_and_niches_carry_only_what_the_options_house_reads(self):
        import json

        root = Path(service.__file__).resolve().parent
        config = service.load_config()
        for key in ("jev", "lab", "semantic_lab"):
            self.assertNotIn(key, config)
        # The site's reset (Sept 26, 2026, 07:21Z): the Brokerage Account's equity once Wave 0 closed the leftovers.
        self.assertEqual(config["performance"], {"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"})
        self.assertEqual(service.performance_of(config), config["performance"])
        self.assertIsNone(service.performance_of({"performance": {"start_at": None, "start_equity": None}}),
                          "no half-filled record reaches the publisher")
        self.assertEqual(service.performance_of({"performance": {"start_at": "2026-09-26T12:00:00Z", "start_equity": "5481.62"}}),
                         {"start_at": "2026-09-26T12:00:00Z", "start_equity": "5481.62"})
        self.assertIn("gym", config)
        self.assertIn("swarm", config)
        self.assertIs(config["real_money"], False, "the new House's first owner deploy runs without real money (plan Wave 7)")
        game = json.loads((root / "game.json").read_text())
        for key in ("lab", "lab_bounds", "hypotheses", "horizon", "horizon_bounds", "research_bounds"):
            self.assertNotIn(key, game)
        self.assertNotIn("gate", game["research"])
        self.assertNotIn("lift", game["merton"])
        desks = json.loads(REAL_NICHES_PATH.read_text())["niches"]
        self.assertEqual([d["id"] for d in desks], ["alpaca-options"])
        for name in ("turbo.json", "repairs.json", "research_routes.json", "routing_evidence.json", "jev_move_model.json",
                     "jev_move_model_jev_shadow.json"):
            self.assertFalse((root / name).exists(), name)
        from league import strategies

        self.assertTrue(all(row["file"].startswith(("krasker_", "options_")) for row in strategies.registry(root / "strategies")))


class AnEmptyRootTicksOptionsOnly(BuildCase):
    """The Done line of Wave 2a: a local tick of the floor's House on an EMPTY state root (fake brokers, no network)
    runs only options code. What was built, what the tick ran (its steps) and what it wrote (the ledger's kinds)."""

    #: Every ledger kind a first options tick may write: the start, the books' baselines and reconciliation, the
    #: allocator's board, the House's own jobs and budget rows, the teacher's lessons, the audit's score, and the births
    #: of the options desk's founders (their endowment and first charge, their seats and stakes, any displacement).
    FIRST_TICK_KINDS = {"ops.started", "book.baseline", "book.reconciled", "alloc.board", "ops.job", "ops.budget",
                        "playbook.entry", "audit.counterfactual", "agent.born", "credit.grant", "credit.charge",
                        "route.decision", "eval.verdict", "book.stake", "agent.postmortem", "agent.died", "ops.alert"}
    #: Steps of the tick whose piece the options House never builds: each is a lap of nothing.
    NOTHING = ("feeds", "jev", "hypotheses", "lab", "shards", "history_coverage")

    def test_one_tick_on_an_empty_root(self):
        import collections

        root = Path(self.dir.name) / "state"
        self.assertFalse(root.exists())
        house = self.build(research=True, merton=True, config=NO_LIVE)
        summary = house.tick()
        house.wait(60)
        self.assertEqual(sorted(p.name for p in root.iterdir() if p.name.startswith(("campaigns", "kalshi", "feeds", "jev", "lab"))), [])
        kinds = collections.Counter(e.kind for e in house.ledger.iter())
        self.assertLessEqual(set(kinds), self.FIRST_TICK_KINDS, kinds)
        born = [e.payload for e in house.ledger.iter(kinds="agent.born")]
        self.assertTrue(born, "the options desk's founders are seated")
        self.assertEqual({(b.get("niche") or b.get("specialty"), b.get("venue")) for b in born}, {("alpaca-options", "alpaca")})
        self.assertTrue(all(a.venue == "alpaca" and a.niche == "alpaca-options" for a in house.registry.agents.values()))
        self.assertEqual(set(summary["reconciled"]), {"alpaca-paper", "options-shadow"})
        steps = house._tick_last["steps"]
        for step in self.NOTHING:
            self.assertLess(steps.get(step, 0.0), 0.05, step)
        self.assertNotIn("meter", steps, "no campaign meter")
        self.assertNotIn("swarm", steps)
        self.assertEqual([e for e in house.ledger.iter(kinds="ops.budget") if e.payload.get("what") in ("expedition", "payout", "burst-ended")], [],
                         "no credit payout and no burst")
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
        house = self.build(config=NO_LIVE)
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
        house = self.build(config=NO_LIVE)
        house.swarm = Step(fail=True)
        summary = house.tick()
        self.assertNotIn("swarm", summary)
        self.assertIn("publish", house._tick_last["steps"])
        texts = [e.payload["text"] for e in house.ledger.iter(kinds="ops.alert")]
        self.assertTrue(any("the swarm step failed" in t for t in texts), texts)

    def test_a_paused_house_tells_the_steps_it_is_not_open_for_business(self):
        house = self.build(config=NO_LIVE)
        house.swarm = Step()
        with patch.object(type(house), "paused", return_value={"reason": "maintenance"}):
            house.tick()
        self.assertEqual(house.swarm.calls, [False])

    def test_unfilled_steps_run_nothing_and_health_says_which_are_filled(self):
        import json

        house = self.build(config=NO_LIVE)
        house.tick()
        self.assertNotIn("swarm", house._tick_last["steps"])
        health = json.loads((Path(self.dir.name) / "state" / "health.json").read_text())
        self.assertEqual(health["pluggable_steps"], {"options_live": False, "swarm": False})
        self.assertIs(health["credit_economy"], False)

    def test_the_house_merges_the_steps_site_inputs(self):
        from decimal import Decimal

        class Swarm(Step):
            def site_inputs(self):
                return {"gym": {"trials": 9}, "agents": [{"id": "a"}], "compute": {"as_of": "2026-09-28T14:00:00Z", "sail_usd": "1.50", "openai_usd": "2.00"}}

        class Live(Step):
            def site_inputs(self):
                return {"structures": [{"id": "real:1"}], "compute": {"sail_usd": "0.25"}}

        house = self.build(config=NO_LIVE)
        self.assertEqual(house.site_inputs(), {})
        house.swarm, house.options_live = Swarm(), Live()
        merged = house.site_inputs()
        self.assertEqual(merged["gym"], {"trials": 9})
        self.assertEqual(merged["agents"], [{"id": "a"}])
        self.assertEqual(merged["structures"], [{"id": "real:1"}])
        self.assertEqual(merged["compute"]["sail_usd"], Decimal("1.75"))
        self.assertEqual(merged["compute"]["openai_usd"], "2.00")
        house.options_live.site_inputs = lambda: 1 / 0
        self.assertEqual(house.site_inputs()["agents"], [{"id": "a"}], "a failing step costs its own blocks only")


if __name__ == "__main__":
    unittest.main()
