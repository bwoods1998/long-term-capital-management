"""A difficult ladder must remain reachable, with explicit funding and real risk enforcement.

Every venue here is FakeBroker; no test can reach a financial account or buy model calls.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from league.campaigns import CampaignBudget, CampaignClosed, CampaignPacer
from league.constitution import CONSTITUTION
from league.evaluator import Verdict
from league.overnight import load_policy
from league.tests.test_phase1 import PhaseCase, policy
from league.tests import test_ladder as ladder_cases, test_tuition as tuition_cases

LADDER = ladder_cases.LADDER


def burst_policy():
    p = load_policy()
    p['caps_usd'] = {'sail': '2', 'openai': '3'}
    return p



# These tests exercise mechanisms (tuition, the timed pilot, audit scoring, concurrency) with the
# micro rung as it stood before the owner's learning-surge revision of Sept 21, 2026 ($25 stake,
# $20 options). The mechanisms are unchanged; only today's numbers moved. Its $10 order and
# position caps are $12 here: Alpaca takes no crypto order under $10 and the House holds a buy to
# that (Sept 22, 2026), so under a $10 cap the ladder strategy's 90%-of-cap buys could not trade.
from unittest.mock import patch as _patch  # noqa: E402
from league.constitution import CONSTITUTION as _CONSTITUTION  # noqa: E402
_LEGACY_MICRO = _patch.dict(_CONSTITUTION["rungs"]["2"], {"stake_usd": "25", "max_position_usd": "12", "max_order_usd": "12", "option_max_position_usd": "20"})


def setUpModule():
    _LEGACY_MICRO.start()


def tearDownModule():
    _LEGACY_MICRO.stop()

class LiveAuthorization(PhaseCase):
    def test_a_research_burst_does_not_implicitly_enable_trading(self):
        guard = self.budget()
        guard.activate_burst('night', burst_policy())
        self.assertFalse(guard.allows_live(2))
        self.assertIsNone(guard.live_pilot())

    def test_explicit_activation_retains_holds_phase_and_fixed_deadline(self):
        guard = self.budget()
        guard.reserve('unknown', 'foundation-review', '1')
        burst = guard.activate_burst('night', burst_policy())
        original = guard.started, guard.ends, guard.policy
        pilot = guard.activate_live_pilot('execution-learning')
        self.assertTrue(guard.allows_live(2))
        self.assertTrue(guard.allows_live(3))
        self.assertEqual(pilot['ends'], burst['ends'])
        reopened = self.budget()
        self.assertEqual((reopened.started, reopened.ends, reopened.policy), original)
        self.assertEqual(reopened.report()['pending_calls'], 1)
        self.now[0] += 100
        self.assertEqual(reopened.activate_live_pilot('execution-learning'), pilot)
        self.now[0] = pilot['ends']
        self.assertFalse(reopened.allows_live(2))
        self.assertFalse(reopened.activate_live_pilot('execution-learning')['active'])
        with self.assertRaises(CampaignClosed):
            reopened.activate_live_pilot('reset-the-budget')

    def test_two_connections_cannot_activate_different_windows(self):
        a = self.budget(); a.activate_burst('night', burst_policy())
        guards = [a, self.budget()]
        def attempt(i):
            try:
                guards[i].activate_live_pilot('live-' + str(i))
                return True
            except CampaignClosed:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt, range(2))), 1)
        self.assertEqual(guards[0].live_pilot(), guards[1].live_pilot())

    def test_closed_or_unfunded_window_cannot_activate(self):
        guard = self.budget()
        with self.assertRaises(CampaignClosed):
            guard.activate_live_pilot('before-research')
        burst = guard.activate_burst('night', burst_policy())
        guard.reserve('all-frontier-credit', 'foundation-review', '3')
        with self.assertRaises(CampaignClosed):
            guard.activate_live_pilot('no-audit-budget')
        self.now[0] = burst['ends']
        with self.assertRaises(CampaignClosed):
            guard.activate_live_pilot('too-late')

    def test_a_different_constitution_cannot_inherit_the_live_grant(self):
        guard = self.budget(); guard.activate_burst('night', burst_policy())
        guard.activate_live_pilot('live')
        with patch.dict(CONSTITUTION['tuition'], max_loss_usd='500'):
            self.assertFalse(guard.allows_live(2))
            with self.assertRaises(CampaignClosed):
                guard.activate_live_pilot('live')


class LivePath(unittest.TestCase):
    def test_unresolved_source_attribution_cannot_buy_audit_capital_or_rewards(self):
        from league.evaluator import Verdict
        f = self.fixture(ladder_cases.LadderTest)
        h = f.house
        self.funding(f)
        agent = h.spawn('tainted', 'ladder-test', LADDER, reason='test', endowment='2.5')
        h.evaluator.seat(agent.id, 1, 'test paper seed')
        h.seat(agent)
        book = h.book_of(agent)
        book._evidence_issues[agent.id] = {'test': {'reason': 'missing owned units'}}
        h._promote(agent, Verdict(agent.id, 1, 'eligible', 'synthetic passing screen', {'book': book.name}))
        self.assertEqual(h.evaluator.rung(agent.id), 1)
        self.assertEqual(f.auditor.seen, [])
        self.assertEqual(h._state['promotion_status'][agent.id]['stage'], 'accounting_integrity')
        self.assertEqual(h._standing(agent, 3600).score_observations, 0)
        self.assertFalse(h._standing(agent, 3600).working)
        self.assertFalse(f.real.submitted)

    def test_attribution_is_checked_again_after_the_paid_audit(self):
        from league.evaluator import Verdict
        f = self.fixture(ladder_cases.LadderTest)
        h = f.house
        self.funding(f)
        agent = h.spawn('race', 'ladder-test', LADDER, reason='test', endowment='2.5')
        h.evaluator.seat(agent.id, 1, 'test paper seed'); h.seat(agent)
        book = h.book_of(agent)
        def audit(*args):
            book._evidence_issues[agent.id] = {'test': {'reason': 'new attribution defect'}}
            return {'approve': True}
        f.auditor.audit = audit
        h._promote(agent, Verdict(agent.id, 1, 'eligible', 'synthetic passing screen', {'book': book.name}))
        h.wait(5)  # the audit runs beside the tick
        self.assertEqual(h.evaluator.rung(agent.id), 1)
        self.assertEqual(h._state['promotion_status'][agent.id]['stage'], 'accounting_integrity')
        self.assertFalse(f.real.submitted)

    def fixture(self, kind=tuition_cases.TuitionTest):
        f = kind(); f.setUp()
        self.addCleanup(f.tearDown)
        return f

    def funding(self, f, activate=True):
        guard = CampaignBudget(Path(f.dir.name) / 'campaigns.sqlite', policy(), clock=f.clock)
        self.addCleanup(guard.close)
        guard.activate_burst('night', burst_policy())
        if activate:
            guard.activate_live_pilot('live')
        f.house.campaigns = guard
        f.house.pacer = CampaignPacer(f.house.ledger, guard, clock=f.clock)
        f.house.provider = SimpleNamespace(transport=SimpleNamespace(refresh=lambda: True))
        return guard

    def test_qualified_paper_can_pass_the_normal_audit_and_execute_on_fake_live_venue(self):
        f = self.fixture(ladder_cases.LadderTest)
        h = f.house
        f.auditor.approve = False
        agent = h.spawn('climber', 'ladder-test', LADDER, reason='test', endowment='2.5')
        h.evaluator.seat(agent.id, 1, 'test paper seed')
        h._state['tried'][agent.id] = agent.code_sha256
        f.run_hours(20, edge=.78)
        self.assertEqual(h.evaluator.rung(agent.id), 1)
        guard = self.funding(f, activate=False)
        seen = len(f.auditor.seen)
        self.assertEqual(h.judge(agent).decision, 'eligible')
        self.assertEqual(h._state['promotion_status'][agent.id]['stage'], 'campaign')
        self.assertEqual(len(f.auditor.seen), seen)
        guard.activate_live_pilot('live')
        f.auditor.policy_digest = 'corrected-test-policy'
        f.auditor.approve = True
        f.clock.advance(31 * 60)
        h.judge(agent)
        h.wait(5)  # the audit runs beside the tick
        self.assertEqual(h.evaluator.rung(agent.id), 2)
        self.assertEqual(h.books['alpaca'].account(agent.id).staked, Decimal('25'))
        f.run_hours(1, edge=.78)
        self.assertTrue(f.real.submitted)
        self.assertTrue(h.books['alpaca'].reconcile().ok)
        self.assertEqual(h.ledger.verify(), h.ledger.head()[0])
        self.assertEqual(guard.live_pilot()['policy']['max_loss_usd'], '200')

    def test_expiry_while_audit_runs_cannot_admit_an_agent(self):
        f = self.fixture(); h = f.house
        guard = self.funding(f)
        agent = h.spawn('waiting', 'test', LADDER, reason='test', endowment='2.5')
        h.evaluator.seat(agent.id, 1, 'paper')
        verdict = Verdict(agent.id, 1, 'eligible', 'screen', {})
        def delayed(*args):
            f.clock.advance(8 * 3600)
            return {'approve': True}
        with patch.object(f.auditor, 'audit', side_effect=delayed):
            h._promote(agent, verdict)
            h.wait(5)  # the audit runs beside the tick
        self.assertEqual(h.evaluator.rung(agent.id), 1)
        self.assertFalse(guard.allows_live(2))
        self.assertFalse(f.real.submitted)
        self.assertEqual(h._state['promotion_status'][agent.id]['stage'], 'campaign')

    def test_expiry_rechecks_queued_entries_at_submission_and_keeps_exits(self):
        f = self.fixture(); h = f.house
        guard = self.funding(f)
        agent = f.on_micro('micro')
        book = h.books['alpaca']
        # $12, not $8: a crypto buy asked under Alpaca's $10 minimum is refused by the House before it can queue.
        intents, dropped = h._intents(agent, book, [{'symbol': 'BTC/USD', 'side': 'buy', 'notional_usd': '12'}])
        self.assertFalse(dropped)
        self.assertTrue(intents)
        outcome = {'agent': agent.id, '_generation': h._generation(agent.id), 'intents': intents}
        f.clock.advance(8 * 3600)
        self.assertEqual(h._submit_wakes('alpaca', [outcome]), [])
        self.assertFalse(f.real.submitted)
        self.assertEqual(h.ledger.last('book.refused', agent=agent.id).payload['book'], 'alpaca')
        # The policy boundary filters entries only; the existing book still validates reducing quantity.
        sell, dropped = h._intents(agent, book, [{'symbol': 'BTC/USD', 'side': 'sell', 'quantity': '.0001'}])
        self.assertFalse(dropped)
        self.assertEqual(sell[0].side, 'sell')

    def test_scaling_does_not_escape_the_eight_seat_two_hundred_dollar_envelope(self):
        f = self.fixture(); h = f.house
        self.funding(f)
        agents = [f.on_micro('micro-' + str(i)) for i in range(8)]
        self.assertEqual(h.tuition()['worst_case_loss_usd'], Decimal('200'))
        self.assertFalse(h.tuition()['room'])
        h._promote(agents[0], Verdict(agents[0].id, 2, 'eligible', 'positive bound', {}))
        self.assertEqual(h.evaluator.rung(agents[0].id), 3)
        self.assertEqual(h.tuition()['seated'], 8)
        self.assertEqual(h.tuition()['worst_case_loss_usd'], Decimal('200'))
        waiting = f.on_micro('waiting', rung=1)
        h._promote(waiting, Verdict(waiting.id, 1, 'eligible', 'screen', {}))
        self.assertEqual(h.evaluator.rung(waiting.id), 1)
        self.assertEqual(h._state['promotion_status'][waiting.id]['stage'], 'tuition')

    def test_sizing_uses_only_remaining_risk_room_and_stops_at_expiry(self):
        from league.capital import resize
        f = self.fixture(); h = f.house
        self.funding(f)
        agents = [f.on_micro('micro-' + str(i)) for i in range(7)]
        h.evaluator.promote(agents[0].id, 3, 'test bound')
        with patch('league.capital.kelly_stake', return_value=(Decimal('500'), {'reason': 'test'})):
            resize(h, agents[0])
            self.assertEqual(h.books['alpaca'].account(agents[0].id).staked, Decimal('50'))
            self.assertEqual(h.tuition()['worst_case_loss_usd'], Decimal('200'))
            self.assertIsNone(resize(h, agents[0]))
            h.evaluator.promote(agents[1].id, 3, 'test bound')
            self.assertIsNone(resize(h, agents[1]))
            f.clock.advance(8 * 3600)
            self.assertIsNone(resize(h, agents[0]))
        self.assertFalse(f.real.submitted)
        self.assertTrue(h.books['alpaca'].reconcile().ok)

    def test_scaled_losses_are_retained_after_demotion_and_expiry(self):
        f = self.fixture(); h = f.house
        self.funding(f)
        agent = f.on_micro('scaled')
        f.lose_about_five_dollars(agent)
        h.evaluator.promote(agent.id, 3, 'test bound')
        self.assertGreater(h.tuition()['spent_usd'], 4)
        self.assertEqual(h.tuition()['worst_case_loss_usd'], Decimal('25'))
        f.clock.advance(8 * 3600)
        self.assertEqual(h.tuition()['worst_case_loss_usd'], Decimal('25'))
        h.evaluator.demote(agent.id, 'test exit')
        h.evaluator.demote(agent.id, 'test exit')
        h._wind_down(agent, h.books['alpaca'])
        self.assertGreater(h.tuition()['spent_usd'], 4)
        self.assertGreater(h.tuition()['worst_case_loss_usd'], 4)
        self.assertTrue(h.books['alpaca'].reconcile().ok)

    def test_exhausted_pilot_moves_scaled_accounts_all_the_way_to_paper(self):
        f = self.fixture(); h = f.house
        self.funding(f)
        agent = f.on_micro('scaled')
        h.evaluator.promote(agent.id, 3, 'test bound')
        # Force the aggregate loss condition, then exercise the real demotion/wind-down path.
        state = {**h.tuition(), 'closed': True, 'spent_usd': Decimal('200')}
        with patch.object(h, 'tuition', return_value=state):
            h._enforce_tuition()
        self.assertEqual(h.evaluator.rung(agent.id), 1)
        self.assertTrue(h.books['alpaca'].account(agent.id).swept)
        self.assertEqual(h.books['alpaca'].account(agent.id).cash, 0)
        self.assertTrue(h.books['alpaca'].reconcile().ok)

    def test_promotion_keeps_earned_paper_rewards_then_upgrades_real_evidence(self):
        f = self.fixture(); h = f.house
        h.game['economy']['performance_min_blocks'] = 5
        agent = f.on_micro('winner', rung=1)
        for i in range(5):
            h.ledger.append('eval.block', {'book': 'alpaca-paper', 'key': str(i),
                'log_growth': .002, 'active': True, 'horizon': 'hour'}, agent=agent.id)
        before = h.standing_of(agent.id)
        h.evaluator.promote(agent.id, 2, 'audited')
        h.seat(agent)
        micro = h.standing_of(agent.id)
        self.assertEqual(micro['active_blocks'], 0)
        self.assertEqual(micro['earned_rung'], 1)
        self.assertEqual(micro['earned_growth'], before['earned_growth'])
        self.assertEqual(micro['earned_observations'], 5)
        for i in range(5):
            h.ledger.append('eval.block', {'book': 'alpaca', 'key': str(i),
                'log_growth': .003, 'active': True, 'horizon': 'hour'}, agent=agent.id)
        h.evaluator.promote(agent.id, 3, 'bounded real evidence')
        scaled = h.standing_of(agent.id)
        self.assertEqual((scaled['active_blocks'], scaled['earned_observations'], scaled['earned_rung']), (0, 5, 3))
        self.assertEqual(scaled['earned_growth'], .003)

    def test_a_live_loss_removes_paper_reward_fallback_immediately(self):
        f = self.fixture(); h = f.house
        h.game['economy']['performance_min_blocks'] = 5
        agent = f.on_micro('winner', rung=1)
        for i in range(5):
            h.ledger.append('eval.block', {'book': 'alpaca-paper', 'key': str(i),
                'log_growth': .002, 'active': True, 'horizon': 'hour'}, agent=agent.id)
        h.evaluator.promote(agent.id, 2, 'audited'); h.seat(agent)
        f.lose_about_five_dollars(agent)
        row = h.standing_of(agent.id)
        self.assertEqual((row['earned_observations'], row['earned_growth']), (0, 0))

    def test_hour_and_day_rewards_use_the_same_time_units(self):
        f = self.fixture(); h = f.house
        h.game['economy']['performance_min_blocks'] = 5
        agent = f.on_micro('winner', rung=1)
        book = h.book_of(agent)
        hours = [{'log_growth': .001, 'active': True, 'horizon': 'hour'} for _ in range(120)]
        days = [{'log_growth': .024, 'active': True, 'horizon': 'day'} for _ in range(5)]
        hourly, daily = [h._reward_evidence(agent, book, rows, 0)[0] for rows in (hours, days)]
        self.assertAlmostEqual(hourly, daily)

    def test_completed_paper_opportunity_can_replace_a_loser_but_protects_a_winner_and_paid_job(self):
        from league.book import Intent
        from league.ledger import now_iso
        from league.overnight import game_for
        from league.economy import load_game
        from league.venues import instrument_for
        f = self.fixture(); h = f.house
        h._burst = {'id': 'test', 'started': f.clock(), 'policy': burst_policy()}
        rules = game_for(load_game(), h._burst)['economy']
        h.game['economy']['performance_min_blocks'] = 5
        loser = f.on_micro('loser', rung=1)
        winner = f.on_micro('winner', rung=1)
        book = h.books['alpaca-paper']
        inst = instrument_for('alpaca-paper', {'symbol': 'BTC/USD'})
        for agent, exit_price in ((loser, 79000), (winner, 82000)):
            for n in range(10):
                f.quote(80000)
                book.submit([Intent.new(agent=agent.id, instrument=inst, side='buy', quantity='.00005',
                    reason='test exposure', created_at=now_iso(f.clock), nonce=f'{agent.id}-buy-{n}')])
                f.clock.advance(30); f.quote(exit_price)
                held = book.account(agent.id).holdings[inst.key].quantity
                book.submit([Intent.new(agent=agent.id, instrument=inst, side='sell', quantity=held,
                    reason='test close', created_at=now_iso(f.clock), nonce=f'{agent.id}-sell-{n}')])
                f.clock.advance(30); book.mark()
        self.assertEqual(h._weakest(rules).id, loser.id)
        h.research_jobs.enqueue(loser.id, list(h._generation(loser.id)))
        self.assertIsNone(h._weakest(rules))

    def test_corrected_audit_policy_gets_one_reconsideration_not_repeated_shopping(self):
        f = self.fixture(); h = f.house
        agent = h.spawn('review', 'test', LADDER, reason='test', endowment='2.5')
        f.auditor.policy_digest = 'corrected-policy'
        h.ledger.append('audit.verdict', {'approve': False, 'summary': 'old evidence'}, agent=agent.id)
        self.assertFalse(h._audit_due(agent))
        f.clock.advance(31 * 60)
        self.assertTrue(h._audit_due(agent))
        h.ledger.append('audit.verdict', {'approve': False, 'summary': 'still a defect',
                                        'policy_digest': f.auditor.policy_digest}, agent=agent.id)
        f.clock.advance(31 * 60)
        self.assertFalse(h._audit_due(agent))
        self.assertEqual(h._audit_wait(agent)['stage'], 'audit_cooldown')


if __name__ == '__main__':
    unittest.main()
