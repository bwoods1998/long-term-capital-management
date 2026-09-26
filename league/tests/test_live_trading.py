"""The owner's grant of real money, `options-swarm-20260928` (`league/live_trading.py`), tested only
against disposable state and fake venues.

The options overhaul (Sept 26, 2026, trap 1) built it fresh in its own store, for the Brokerage
Account alone, and moved every call site of the campaign store's grant to it, so real money turns
on and off only through it:

- no grant -> no real entry, and no promotion onto real money;
- an active grant -> entries allowed, inside its capital (the lower of equity and the ceiling);
- revoked -> exits only, for good;
- a money rule changed (the digest moved) -> no entry until the owner ratifies;
- a deposit -> ratifying raises capital, up to the ceiling;
- an empty state root works (no campaign database).
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from league.constitution import CONSTITUTION, money_digest
from league.evaluator import Verdict
from league.live_trading import (GRANT_ID, STORE, GrantClosed, LiveGrant, ceiling, holds, main, policy, read_equity,
                                 smallest_stake)
from league.tests import test_tuition
from league.tests.fakes import Clock

D = Decimal
EQUITY = "481.62"   # the Brokerage Account's cash at T0 of the options run
CEILING = "5500"    # $481.62 plus the owner's planned $5,000 deposit


class GrantCase(TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "state"
        self.clock = Clock()

    def grant(self):
        grant = LiveGrant(self.root / STORE, clock=self.clock)
        self.addCleanup(grant.close)
        return grant


class ThePolicy(TestCase):
    def test_capital_is_the_lower_of_equity_and_the_ceiling_on_the_brokerage_account_only(self):
        low = policy(EQUITY, CEILING)
        self.assertEqual((low["capital_usd"], low["max_loss_usd"], low["venue_capital_usd"]), ("481.62", "481.62", {"alpaca": "481.62"}))
        self.assertEqual((low["venues"], low["max_rung"], low["expires"]), (["alpaca"], 3, None))
        self.assertEqual(low["constitution_digest"], money_digest())
        self.assertEqual(low["max_agents"], int(D("481.62") // smallest_stake()))
        high = policy("7000", CEILING)
        self.assertEqual((high["capital_usd"], high["equity_usd"], high["ceiling_usd"]), ("5500.00", "7000.00", "5500.00"))

    def test_nonsense_and_oversized_or_unfunded_capital_is_refused(self):
        for equity, top in (("NaN", CEILING), ("-1", CEILING), (EQUITY, "10000.01"), ("1", CEILING), (EQUITY, "1"), ("x", CEILING)):
            with self.subTest(equity=equity, ceiling=top), self.assertRaises(ValueError):
                policy(equity, top)
        self.assertEqual(policy("10000", "10000")["capital_usd"], "10000.00")

    def test_a_policy_naming_another_venue_or_digest_never_holds(self):
        good = policy(EQUITY, CEILING)
        self.assertTrue(holds(good))
        self.assertFalse(holds({**good, "venues": ["alpaca", "kalshi"]}))
        self.assertFalse(holds({**good, "venue_capital_usd": {"alpaca": "400", "kalshi": "81.62"}}))
        self.assertFalse(holds({**good, "constitution_digest": "0" * 64}))
        self.assertFalse(holds({**good, "version": 1}))

    def test_the_ceiling_is_the_config_and_the_shipped_one_is_5500(self):
        from league.service import load_config

        self.assertEqual(ceiling(load_config()), D("5500"))
        self.assertEqual(ceiling({"live_trading": {"ceiling_usd": "123.456"}}), D("123.45"))
        with self.assertRaises(ValueError):
            ceiling({})

    def test_equity_is_read_through_the_gateway_as_a_balance_only(self):
        balance = SimpleNamespace(currency="USD", cash=D("457.05"), equity=D("481.789"), buying_power=D("2000"))
        with patch("league.service.load_env"), patch("league.service.secret", return_value="t" * 40), \
                patch("league.venues.gateway_broker") as broker:
            broker.return_value.balance.return_value = balance
            self.assertEqual(read_equity({"gateway_url": "https://gateway.invalid"}), D("481.78"))
        self.assertEqual(broker.call_args.args[0], "alpaca")
        self.assertFalse(broker.return_value.submit.called)


class TheStore(GrantCase):
    def test_an_empty_root_has_no_grant_and_allows_nothing(self):
        grant = self.grant()
        self.assertIsNone(grant.current())
        self.assertIsNone(grant.live_authorization())
        self.assertFalse(grant.allows_live(2))
        self.assertFalse(grant.allows_live(3))
        self.assertFalse((self.root / "campaigns.sqlite").exists(), "no campaign database is made or needed")

    def test_enable_activates_only_the_live_rungs(self):
        grant = self.grant()
        live = grant.enable(GRANT_ID, EQUITY, CEILING)
        self.assertTrue(live["active"])
        self.assertEqual((live["id"], live["revoked"], live["ends"]), (GRANT_ID, None, None))
        self.assertEqual([grant.allows_live(r) for r in (0, 1, 2, 3, 4)], [False, False, True, True, False])
        self.assertEqual(self.grant().current(), live, "a second connection reads the same grant")

    def test_a_deposit_is_answered_by_ratifying_up_to_the_ceiling(self):
        grant = self.grant()
        self.assertEqual(grant.enable(GRANT_ID, EQUITY, CEILING)["policy"]["capital_usd"], "481.62")
        self.clock.advance(3600)
        landed = grant.ratify(GRANT_ID, "5481.62", CEILING)
        self.assertTrue(landed["active"])
        self.assertEqual(landed["policy"]["capital_usd"], "5481.62")
        above = grant.ratify(GRANT_ID, "7200", CEILING)
        self.assertEqual(above["policy"]["capital_usd"], "5500.00", "never above the owner's ceiling")
        self.assertEqual(len(grant.ratifications()), 2)
        self.assertEqual(json.loads(grant.ratifications()[0]["old_policy"])["capital_usd"], "481.62")
        lower = grant.ratify(GRANT_ID, "300", CEILING)
        self.assertEqual(lower["policy"]["capital_usd"], "300.00", "a loss lowers it at the next ratification")

    def test_enabling_again_reads_capital_afresh_and_never_forks_a_second_grant(self):
        grant = self.grant()
        grant.enable(GRANT_ID, EQUITY, CEILING)
        again = grant.enable(GRANT_ID, "900", CEILING)
        self.assertEqual(again["policy"]["capital_usd"], "900.00")
        with self.assertRaises(GrantClosed):
            grant.enable("someone-else", EQUITY, CEILING)
        self.assertEqual(grant.current()["id"], GRANT_ID)

    def test_two_connections_cannot_create_two_grants(self):
        guards = [self.grant(), self.grant()]

        def enable(i):
            try:
                guards[i].enable(f"owner-{i}", EQUITY, CEILING)
                return True
            except GrantClosed:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(enable, range(2))), 1)

    def test_revocation_is_for_good_and_keeps_the_capital_accounting(self):
        grant = self.grant()
        grant.enable(GRANT_ID, EQUITY, CEILING)
        self.clock.advance(60)
        revoked = grant.revoke()
        self.assertFalse(revoked["active"])
        self.assertFalse(grant.allows_live(2))
        self.assertFalse(grant.allows_live(3))
        self.assertEqual(grant.live_authorization()["policy"]["venue_capital_usd"], {"alpaca": "481.62"})
        for action in (grant.enable, grant.ratify):
            with self.subTest(action=action.__name__), self.assertRaises(GrantClosed):
                action(GRANT_ID, EQUITY, CEILING)
        self.assertFalse(grant.current()["active"])
        # A new identity may follow once the first is revoked.
        self.clock.advance(60)
        self.assertTrue(grant.enable("options-swarm-next", EQUITY, CEILING)["active"])

    def test_a_money_rule_change_holds_entries_until_the_owner_ratifies(self):
        grant = self.grant()
        grant.enable(GRANT_ID, EQUITY, CEILING)
        with patch.dict(CONSTITUTION["tuition"], max_agents=CONSTITUTION["tuition"]["max_agents"] + 1):
            self.assertFalse(grant.current()["active"])
            self.assertFalse(grant.allows_live(2))
            ratified = grant.ratify(GRANT_ID, EQUITY, CEILING)
            self.assertTrue(ratified["active"])
            self.assertEqual(ratified["policy"]["constitution_digest"], money_digest())
        self.assertFalse(grant.allows_live(2), "back on the old rules, the grant pinned on the new ones holds nothing")

    def test_risk_free_rules_can_change_without_revoking_the_grant(self):
        grant = self.grant()
        grant.enable(GRANT_ID, EQUITY, CEILING)
        with patch.dict(CONSTITUTION["ladder"]["replay"], min_deflated_sharpe=.3), \
                patch.dict(CONSTITUTION["ladder"]["paper_death"], max_loss=.05):
            self.assertTrue(grant.allows_live(3))

    def test_a_grant_not_yet_started_allows_nothing(self):
        grant = self.grant()
        grant.enable(GRANT_ID, EQUITY, CEILING)
        grant.db.execute("UPDATE grants SET started=?", (self.clock() + 60,))
        self.assertFalse(grant.allows_live(2))


class OwnerCommand(GrantCase):
    def run_main(self, *args, equity=EQUITY):
        with patch("league.live_trading.read_equity", return_value=D(equity)) as read, \
                patch("league.live_trading.ceiling", return_value=D(CEILING)), patch("sys.stdout", new_callable=io.StringIO):
            out = main(["--root", str(self.root), *args])
        return out, read

    def test_the_report_on_an_empty_root_is_inert(self):
        out, read = self.run_main()
        self.assertIsNone(out["live_trading"])
        self.assertFalse(out["micro_entries_allowed"])
        self.assertEqual(out["prepared_policy"]["capital_usd"], EQUITY)
        self.assertIsNone(self.grant().current())

    def test_enable_ratify_and_disable(self):
        out, _ = self.run_main("--enable")
        self.assertEqual((out["live_trading"]["id"], out["live_trading"]["active"]), (GRANT_ID, True))
        out, read = self.run_main("--ratify", equity="5481.62")
        self.assertTrue(read.called)
        self.assertEqual(out["live_trading"]["policy"]["capital_usd"], "5481.62")
        out, read = self.run_main("--disable")
        self.assertFalse(read.called, "revoking reads no balance")
        self.assertFalse(out["live_trading"]["active"])
        with self.assertRaises(GrantClosed):
            self.run_main("--enable")

    def test_the_box_wrapper_runs_the_grant_on_the_state_root_and_restarts_nothing(self):
        from scripts.live_trading import GRANT_ID as SCRIPT_GRANT, main as owner_command

        self.assertEqual(SCRIPT_GRANT, GRANT_ID)
        for args, tail in [([], []), (["--enable"], ["--enable", GRANT_ID]), (["--ratify"], ["--ratify", GRANT_ID]),
                           (["--disable"], ["--disable"])]:
            result = SimpleNamespace(stdout=json.dumps({"live_trading": {"active": True}}), check=lambda: None)
            with self.subTest(args=args), patch("scripts.live_trading.client") as api, \
                    patch("scripts.live_trading.read_state", return_value={"box_id": "fake"}), \
                    patch("scripts.live_trading.require_box", return_value="fake"), \
                    patch("sys.stdout", new_callable=io.StringIO):
                api.return_value.exec.return_value = result
                owner_command(args)
                self.assertEqual(api.return_value.exec.call_count, 1, "one command, no restart")
                command = api.return_value.exec.call_args.args[1]
                self.assertIn("from league.live_trading import main", command[2])
                self.assertEqual(command[3:], ["--root", "/workspace/state", *tail])


class TheHouseAsksOnlyTheGrant(TestCase):
    """A real-money House with the real store in its state root (the fixture of `test_tuition`)."""

    def setUp(self):
        self.f = test_tuition.TuitionTest()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.house = self.f.house
        self.house.grant = LiveGrant(self.house.root / STORE, clock=self.f.clock)
        self.addCleanup(self.house.grant.close)
        self.book = self.house.books["alpaca"]
        self.agent = self.f.on_micro("trader")

    def buy(self):
        return self.house._intents(self.agent, self.book, [{"symbol": "BTC/USD", "side": "buy", "notional_usd": "12"}])

    def sell(self):
        return self.house._intents(self.agent, self.book, [{"symbol": "BTC/USD", "side": "sell", "quantity": ".00001"}])

    def submitted(self, intents):
        before = len(self.f.real.submitted)
        self.house._submit_wakes("alpaca", [{"agent": self.agent.id, "_generation": self.house._generation(self.agent.id),
                                             "intents": intents}])
        return len(self.f.real.submitted) - before

    def enable(self, equity=EQUITY):
        return self.house.grant.enable(GRANT_ID, equity, CEILING)

    def test_a_house_on_an_empty_root_builds_its_own_empty_grant(self):
        from league.house import House, Settings
        from league.tests.fakes import FakeBroker
        from league.tests.test_ladder import InProcessSandbox

        with tempfile.TemporaryDirectory() as tmp:
            house = House(Path(tmp) / "state", brokers={"alpaca": FakeBroker("alpaca")}, sandbox=InProcessSandbox(),
                          settings=Settings(real_money=True, research=False), clock=Clock())
            try:
                self.assertIsInstance(house.grant, LiveGrant)
                self.assertEqual(house.grant.path, Path(tmp) / "state" / STORE)
                self.assertFalse(house.grant.allows_live(2))
                self.assertFalse(house.allocator._live_open("alpaca"))
            finally:
                house.close(wait=None)

    def test_no_grant_means_no_real_entry_and_no_promotion_onto_real_money(self):
        _, dropped = self.buy()
        self.assertTrue(dropped, "the buy is refused where it is asked")
        self.assertIn("no new real-money entries", " ".join(dropped))
        waiting = self.f.on_micro("waiting", rung=1)
        self.house._promote(waiting, Verdict(waiting.id, 1, "eligible", "screen", {}))
        self.assertEqual(self.house.evaluator.rung(waiting.id), 1)
        self.assertEqual(self.house._state["promotion_status"][waiting.id]["stage"], "campaign")
        self.assertFalse(self.house.allocator._live_open("alpaca"))
        self.assertFalse(self.house.allocator._swing_released())

    def test_an_active_grant_allows_entries_inside_its_capital(self):
        self.enable()
        intents, dropped = self.buy()
        self.assertTrue(intents)
        self.assertFalse(dropped)
        self.assertEqual(self.submitted(intents), 1)
        self.assertEqual(self.house.allocator.grant_capital("alpaca"), D(EQUITY))
        self.assertEqual(self.house.tuition("alpaca")["limit_usd"], D(EQUITY))
        self.assertTrue(self.house.allocator._live_open("alpaca"))

    def test_revoked_means_exits_only(self):
        self.enable()
        intents, _ = self.buy()
        self.assertTrue(intents)
        self.house.grant.revoke()
        self.assertEqual(self.submitted(intents), 0, "a buy queued before the revocation does not leave")
        _, dropped = self.buy()
        self.assertTrue(dropped)
        sells, dropped = self.sell()
        self.assertTrue(sells)
        self.assertFalse(dropped)
        self.assertEqual(self.house.tuition("alpaca")["limit_usd"], D(EQUITY), "the revoked grant's capital still bounds the book")

    def test_a_moved_digest_holds_entries_until_ratified(self):
        self.enable()
        with patch.dict(CONSTITUTION["tuition"], max_agents=CONSTITUTION["tuition"]["max_agents"] + 1):
            _, dropped = self.buy()
            self.assertTrue(dropped)
            self.house.grant.ratify(GRANT_ID, EQUITY, CEILING)
            intents, dropped = self.buy()
            self.assertTrue(intents)
            self.assertFalse(dropped)

    def test_a_deposit_ratified_raises_the_envelope_up_to_the_ceiling(self):
        self.enable()
        self.assertEqual(self.house.allocator.grant_capital("alpaca"), D(EQUITY))
        self.house.grant.ratify(GRANT_ID, "5481.62", CEILING)
        self.assertEqual(self.house.allocator.grant_capital("alpaca"), D("5481.62"))
        self.house.grant.ratify(GRANT_ID, "9000", CEILING)
        self.assertEqual(self.house.allocator.grant_capital("alpaca"), D(CEILING))

    def test_no_call_site_asks_the_campaign_store_for_real_money(self):
        import re

        root = Path(__file__).resolve().parents[1]
        for name in ("house.py", "allocator.py", "capital.py", "shards.py", "merton.py"):
            text = (root / name).read_text()
            self.assertIsNone(re.search(r"campaigns\S*\.(allows_live|live_authorization|live_trading)\(", text), name)
            self.assertIsNone(re.search(r"getattr\((self\.)?house, ['\"]campaigns['\"], None\)\s*\n\s*.*(allows_live|live_authorization)", text), name)
