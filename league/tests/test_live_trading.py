"""Persistent owner authorization tested only against disposable state and fake venues."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from league.campaigns import CampaignBudget, CampaignClosed, CampaignPacer
from league.constitution import CONSTITUTION
from league.evaluator import Verdict
from league.live_trading import main, policy, read_venue_capital, report
from league.overnight import active, load_policy
from league.tests.test_phase1 import PhaseCase, policy as campaign_policy
from league.tests import test_ladder, test_tuition


CAPITAL = {'alpaca': '500', 'kalshi': '500'}


def research_policy():
    value = load_policy()
    value['caps_usd'] = {'openai': '3', 'sail': '2'}
    return value


class PersistentAuthorization(PhaseCase):
    def expired(self):
        guard = self.budget()
        burst = guard.activate_burst('original-night', research_policy())
        guard.reserve('pending-call', 'foundation-review', '1')
        self.now[0] = burst['ends'] + 3600
        return guard, burst

    def test_reporting_and_deployment_never_authorize_trading(self):
        guard, _ = self.expired()
        before = guard.report()
        shown = report(guard, prepared_capital=CAPITAL)
        self.assertEqual(guard.report(), before)
        self.assertFalse(shown['micro_entries_allowed'])
        self.assertFalse(shown['scaled_entries_allowed'])
        self.assertEqual(shown['unused_burst_allowance_usd'], {'openai': '2', 'sail': '2'})
        self.assertIsNone(self.budget().live_trading())

    def test_activation_survives_phase_expiry_without_resetting_any_dollar(self):
        guard, original = self.expired()
        phase = guard.started, guard.ends, guard.policy
        live = guard.activate_live_trading('earned', CAPITAL)
        self.assertTrue(live['active'])
        self.assertIsNone(live['ends'])
        self.assertTrue(guard.allows_live(2))
        self.assertTrue(guard.allows_live(3))
        self.assertEqual(guard.remaining('openai'), 2)
        self.assertEqual(guard.burst(), original)
        self.now[0] = guard.ends + 90 * 86400
        reopened = self.budget()
        self.assertTrue(reopened.running())
        self.assertTrue(reopened.allows_live(3))
        self.assertEqual((reopened.started, reopened.ends, reopened.policy), phase)
        self.assertEqual(reopened.activate_live_trading('earned', CAPITAL), live)
        self.assertEqual(reopened.report()['pending_calls'], 1)
        reopened.reserve('last-two', 'foundation-review', '2')
        self.assertEqual(reopened.remaining('openai'), 0)
        with self.assertRaises(CampaignClosed):
            reopened.reserve('one-more', 'foundation-review', '.01')
        self.assertTrue(reopened.allows_live(3))  # Funding and financial permission are separate.
        self.assertEqual(reopened.burst(), original)

    def test_identity_and_capital_cannot_be_refilled_by_repeating_activation(self):
        guard, _ = self.expired()
        original = guard.activate_live_trading('earned', CAPITAL)
        for ident, capital in [('new', CAPITAL), ('earned', {'alpaca': '501', 'kalshi': '500'})]:
            with self.subTest(ident=ident, capital=capital), self.assertRaises(CampaignClosed):
                guard.activate_live_trading(ident, capital)
        self.assertEqual(guard.live_trading(), original)

    def test_two_connections_cannot_authorize_different_capital(self):
        a, _ = self.expired()
        guards = [a, self.budget()]
        def enable(i):
            try:
                guards[i].activate_live_trading('owner-' + str(i), CAPITAL)
                return True
            except CampaignClosed:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(enable, range(2))), 1)

    def test_revocation_keeps_risk_and_cannot_be_undone_by_a_retry(self):
        guard, _ = self.expired()
        guard.activate_live_trading('earned', CAPITAL)
        guard.revoke_live_trading()
        self.assertFalse(guard.allows_live(2))
        self.assertFalse(guard.allows_live(3))
        self.assertFalse(guard.activate_live_trading('earned', CAPITAL)['active'])
        self.assertEqual(guard.live_authorization()['policy']['max_loss_usd'], '1000.00')
        self.assertEqual(guard.report()['pending_calls'], 1)

    def test_changed_constitution_cannot_inherit_owner_authorization(self):
        guard, _ = self.expired()
        guard.activate_live_trading('earned', CAPITAL)
        with patch.dict(CONSTITUTION['rungs']['3'], max_share_of_venue=.5):
            self.assertFalse(guard.allows_live(3))
            with self.assertRaises(CampaignClosed):
                guard.activate_live_trading('earned', CAPITAL)

    def test_risk_free_rules_can_change_without_revoking_the_money_grant(self):
        """The grant pins the rules that govern real money; the replay gate and paper death do not."""
        guard, _ = self.expired()
        guard.activate_live_trading('earned', CAPITAL)
        with patch.dict(CONSTITUTION['ladder']['replay'], min_deflated_sharpe=.3), \
                patch.dict(CONSTITUTION['ladder']['paper_death'], max_loss=.05):
            self.assertTrue(guard.allows_live(3))
        with patch.dict(CONSTITUTION['ladder']['paper'], min_active_blocks=3):
            self.assertFalse(guard.allows_live(2))  # the screen that promotes to money is a money rule

    def test_a_legacy_whole_constitution_grant_holds_only_while_money_rules_are_unchanged(self):
        from league.constitution import LEGACY_GRANT_DIGESTS, money_digest
        guard, _ = self.expired()
        guard.activate_live_trading('earned', CAPITAL)
        legacy = next(iter(LEGACY_GRANT_DIGESTS))
        stored = {**policy(CAPITAL), 'constitution_digest': legacy}
        guard.db.execute('UPDATE live_trading SET policy=?', (json.dumps(stored, sort_keys=True, separators=(',', ':')),))
        with patch.dict(LEGACY_GRANT_DIGESTS, {legacy: money_digest()}):
            self.assertTrue(guard.live_trading()['active'])
            with patch.dict(CONSTITUTION['tuition'], max_agents=9):
                self.assertFalse(guard.live_trading()['active'])
        with patch.dict(LEGACY_GRANT_DIGESTS, {legacy: '0' * 64}):
            self.assertFalse(guard.live_trading()['active'])

    def test_the_pre_revision_grant_needs_the_owner_after_the_fast_lane(self):
        """The fast lane (Sept 21 ~22:30 UTC) changed money rules, so the grant recorded before it is
        not carried over silently: the owner ratifies it (`ratify_live_trading`)."""
        from league.constitution import LEGACY_GRANT_DIGESTS, money_digest
        self.assertNotEqual(LEGACY_GRANT_DIGESTS['bfdbbf8567205153a18eed023819e9bf52e5d989dae5d113d60fd5c1a1e5fad1'], money_digest())

    def test_the_owner_ratifies_a_grant_under_revised_money_rules_without_new_capital(self):
        guard, _ = self.expired()
        live = guard.activate_live_trading('earned', CAPITAL)
        with patch.dict(CONSTITUTION['ladder']['paper'], min_active_blocks=3):
            self.assertFalse(guard.live_trading()['active'])
            with self.assertRaises(CampaignClosed):
                guard.ratify_live_trading('someone-else')
            ratified = guard.ratify_live_trading('earned')
            self.assertTrue(ratified['active'])
            self.assertEqual(ratified['policy']['venue_capital_usd'], live['policy']['venue_capital_usd'])
            self.assertEqual(guard.db.execute('SELECT COUNT(*) FROM live_ratifications').fetchone()[0], 1)
        guard.revoke_live_trading()
        with self.assertRaises(CampaignClosed):
            guard.ratify_live_trading('earned')

    def test_exhausted_or_unhealthy_research_cannot_be_reopened(self):
        guard, _ = self.expired()
        with patch.object(guard, 'ready', return_value=False), self.assertRaises(CampaignClosed):
            guard.activate_live_trading('earned', CAPITAL)
        self.assertIsNone(guard.live_trading())
        guard.db.execute("UPDATE commitments SET reserved=3000000 WHERE id='pending-call'")
        with self.assertRaises(CampaignClosed):
            guard.activate_live_trading('earned', CAPITAL)
        self.assertIsNone(guard.live_trading())

    def test_fast_game_is_restored_without_changing_the_research_cohort(self):
        guard, original = self.expired()
        self.assertIsNone(active(guard, self.clock))
        guard.activate_live_trading('earned', CAPITAL)
        effective = active(guard, self.clock)
        self.assertEqual(effective['id'], original['id'])
        self.assertIsNone(effective['ends'])
        self.assertEqual(effective['policy'], original['policy'])
        pacer = CampaignPacer(None, guard, clock=self.clock)
        self.assertEqual(pacer.credit_pool(per_seconds=3600), Decimal('.31'))

    def test_owner_cli_report_is_inert_and_retry_does_not_read_new_deposits(self):
        guard, _ = self.expired()
        with patch('league.live_trading.read_venue_capital', return_value=CAPITAL), \
                patch('league.campaigns.load_policy', return_value=campaign_policy()), \
                patch('sys.stdout', new_callable=io.StringIO):
            main(['--root', str(self.root)])
        self.assertIsNone(guard.live_trading())
        guard.activate_live_trading('earned', CAPITAL)
        with patch('league.live_trading.read_venue_capital', side_effect=AssertionError('no new capital read')), \
                patch('league.campaigns.load_policy', return_value=campaign_policy()), \
                patch('sys.stdout', new_callable=io.StringIO):
            main(['--root', str(self.root), '--enable', 'earned'])


class CapitalSnapshot(TestCase):
    def test_only_cash_not_margin_or_unrealized_assets_is_authorized(self):
        balances = [SimpleNamespace(currency='USD', cash=Decimal('501.999'), equity=Decimal('520'), buying_power=Decimal('2000')),
                    SimpleNamespace(currency='USD', cash=Decimal('490'), equity=Decimal('480'), buying_power=Decimal('500'))]
        with patch('league.service.load_env'), patch('league.service.secret', return_value='test'), \
                patch('league.venues.gateway_broker') as broker:
            broker.return_value.balance.side_effect = balances
            self.assertEqual(read_venue_capital(), {'alpaca': '501.99', 'kalshi': '480.00'})

    def test_invalid_or_unfunded_allocations_are_rejected(self):
        for value in ({'alpaca': 'NaN', 'kalshi': '500'}, {'alpaca': '-1', 'kalshi': '500'},
                      {'alpaca': '10', 'kalshi': '10'}, {'alpaca': '24', 'kalshi': '24'},
                      {'alpaca': '10000', 'kalshi': '1'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy(value)


class PersistentLadder(TestCase):
    def fixture(self, kind=test_tuition.TuitionTest, capital=None):
        f = kind(); f.setUp(); self.addCleanup(f.tearDown)
        guard = CampaignBudget(Path(f.dir.name) / 'campaigns.sqlite', campaign_policy(), clock=f.clock)
        guard.activate_burst('original-night', research_policy())
        f.clock.advance(9 * 3600)
        guard.activate_live_trading('earned', capital or CAPITAL)
        f.house.campaigns = guard
        f.house.pacer = CampaignPacer(f.house.ledger, guard, clock=f.clock)
        f.house.provider = SimpleNamespace(transport=SimpleNamespace(refresh=lambda: True))
        if hasattr(f, 'quote'):
            f.quote(80000)
        return f, guard

    def test_a_qualified_agent_can_audit_and_trade_after_both_old_deadlines(self):
        f, guard = self.fixture(test_ladder.LadderTest)
        h = f.house
        f.clock.advance(3 * 86400)
        agent = h.spawn('climber', 'test', test_ladder.LADDER, reason='test', endowment='2.5')
        h.evaluator.seat(agent.id, 1, 'paper')
        h._state['tried'][agent.id] = agent.code_sha256
        for _ in range(60 * 12):
            f.run_hours(1 / 12, edge=.78)
            if h.evaluator.rung(agent.id) >= 3:
                break
        self.assertEqual(h.evaluator.rung(agent.id), 3)
        self.assertIn(agent.id, f.auditor.seen)
        self.assertTrue(f.real.submitted)
        self.assertTrue(h.books['alpaca'].reconcile().ok)
        self.assertTrue(guard.allows_live(3))
        from league.capital import resize
        resize(h, agent)
        self.assertGreater(h.books['alpaca'].account(agent.id).staked, 50)
        self.assertGreater(h.standing_of(agent.id)['earned_observations'], 0)
        f.run_hours(30, edge=.3)
        decisions = [e.payload['decision'] for e in h.ledger.iter(kinds='eval.verdict', agent=agent.id)]
        self.assertTrue('demote' in decisions or 'die' in decisions)
        self.assertTrue(h.books['alpaca'].reconcile().ok)
        self.assertEqual(h.ledger.verify(), h.ledger.head()[0])

    def test_scaled_agent_can_pass_fifty_dollars_but_cannot_spend_the_other_venue(self):
        from league.capital import resize
        f, guard = self.fixture(capital={'alpaca': '125', 'kalshi': '500'})
        h = f.house
        agent = f.on_micro('winner')
        h.evaluator.promote(agent.id, 3, 'earned test bound')
        with patch('league.capital.kelly_stake', return_value=(Decimal('1000'), {'reason': 'test'})):
            resize(h, agent)
        self.assertEqual(h.books['alpaca'].account(agent.id).staked, Decimal('125'))
        self.assertEqual(h.tuition('alpaca')['headroom_usd'], 0)
        self.assertEqual(h.tuition()['headroom_usd'], 500)
        waiting = f.on_micro('waiting', rung=1)
        h._promote(waiting, Verdict(waiting.id, 1, 'eligible', 'screen', {}))
        self.assertEqual(h.evaluator.rung(waiting.id), 1)
        self.assertEqual(h._state['promotion_status'][waiting.id]['stage'], 'tuition')

    def test_revocation_blocks_queued_buys_but_keeps_exits_and_historical_losses(self):
        f, guard = self.fixture()
        h = f.house
        agent = f.on_micro('trader')
        f.lose_about_five_dollars(agent)
        book = h.books['alpaca']
        # $12, not $1: a crypto buy asked under Alpaca's $10 minimum is refused by the House before it can queue.
        intents, _ = h._intents(agent, book, [{'symbol': 'BTC/USD', 'side': 'buy', 'notional_usd': '12'}])
        self.assertTrue(intents)
        before = len(f.real.submitted)
        guard.revoke_live_trading()
        self.assertEqual(h._submit_wakes('alpaca', [{'agent': agent.id, '_generation': h._generation(agent.id), 'intents': intents}]), [])
        self.assertEqual(len(f.real.submitted), before)
        sell, dropped = h._intents(agent, book, [{'symbol': 'BTC/USD', 'side': 'sell', 'quantity': '.00001'}])
        self.assertTrue(sell)
        self.assertFalse(dropped)
        self.assertGreater(h.tuition('alpaca')['spent_usd'], 4)
        self.assertEqual(h.tuition()['limit_usd'], 1000)


class OwnerWrapper(TestCase):
    def test_only_successful_owner_enable_restarts_the_house(self):
        from scripts.live_trading import main as owner_command
        for args, live, calls in [([], None, 1), (['--enable', 'earned'], {'active': True}, 2),
                                  (['--enable', 'earned'], {'active': False}, 1), (['--disable'], {'active': False}, 1)]:
            result = SimpleNamespace(stdout=json.dumps({'live_trading': live}), check=lambda: None)
            with self.subTest(args=args, live=live), patch('scripts.live_trading.client') as api, \
                    patch('scripts.live_trading.read_state', return_value={'box_id': 'fake'}), \
                    patch('sys.stdout', new_callable=io.StringIO):
                api.return_value.exec.return_value = result
                owner_command(args)
                self.assertEqual(api.return_value.exec.call_count, calls)
                if calls == 2:
                    self.assertEqual(api.return_value.exec.call_args.args[1], ['sh', '/workspace/restart.sh'])
