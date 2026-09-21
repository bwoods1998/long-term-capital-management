"""A faster game must preserve evidence and its funded window across concurrency/restarts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json

from league.campaigns import CampaignClosed, CampaignPacer
from league.economy import Economy, Standing, load_game
from league.overnight import game_for, load_policy, validate
from league.tests.test_phase1 import PhaseCase
from league.tests.test_house import HouseCase


class BurstBudget(PhaseCase):
    def small_policy(self):
        p = load_policy()
        p['caps_usd'] = {'sail':'2', 'openai':'3'}
        return p

    def test_activation_retains_phase_holds_and_cannot_reset_the_clock(self):
        guard = self.budget()
        guard.reserve('older', 'baseline-research', '4')
        original = guard.started, guard.ends, guard.policy
        burst = guard.activate_burst('night', self.small_policy())
        self.assertEqual(guard.remaining('sail'), 2)
        self.assertEqual(guard.report()['pending_calls'], 1)
        self.now[0] += 60
        self.assertEqual(guard.activate_burst('night', self.small_policy()), burst)
        reopened = self.budget()
        self.assertEqual((reopened.started, reopened.ends, reopened.policy), original)
        self.assertEqual(reopened.burst(), burst)
        with self.assertRaises(CampaignClosed):
            reopened.activate_burst('another-night', self.small_policy())
        changed = self.small_policy();changed['caps_usd']['sail'] = '3'
        with self.assertRaises(CampaignClosed):
            reopened.activate_burst('night', changed)
        reopened.settle('older', '1')
        self.assertEqual(reopened.remaining('sail'), 2)  # old hold refunds cannot expand the burst

    def test_cross_connection_reservations_share_one_incremental_allowance(self):
        a = self.budget();a.activate_burst('night', self.small_policy())
        guards = [a, self.budget()]
        def attempt(i):
            try:
                return guards[i % 2].reserve(str(i), 'foundation-review', '1')
            except CampaignClosed:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(20))), 3)
        self.assertEqual(a.remaining('openai'), 0)
        self.assertEqual(a.report()['burst']['committed_usd']['openai'], '3')

    def test_expiry_and_midnight_do_not_release_unknown_costs_or_allow_new_work(self):
        guard = self.budget();burst = guard.activate_burst('night', self.small_policy())
        guard.reserve('pending', 'foundation-review', '2')
        self.now[0] = burst['ends']
        restarted = self.budget()
        self.assertFalse(restarted.running())
        self.assertEqual(restarted.remaining('openai'), 0)
        self.assertEqual(restarted.report()['burst']['committed_usd']['openai'], '2')
        with self.assertRaises(CampaignClosed):
            restarted.reserve('new', 'foundation-review', '.01')
        self.assertFalse(restarted.reserve('pending', 'foundation-review', '2'))
        restarted.settle('pending', '.5')
        self.assertEqual(restarted.report()['pending_calls'], 0)
        self.assertEqual(restarted.remaining('openai'), 0)

    def test_vendor_hosting_increment_and_pending_calls_are_conservative(self):
        guard = self.budget();guard.observe_spend('sail', '100')
        guard.activate_burst('night', self.small_policy())
        guard.reserve('model', 'baseline-research', '.5')
        guard.observe_spend('sail', '101')
        self.assertEqual(guard.remaining('sail'), Decimal('.5'))
        guard.settle('model', '.2')
        self.assertEqual(guard.remaining('sail'), 1)

    def test_burst_pool_uses_eight_hours_not_the_daily_divisor(self):
        guard = self.budget();p = self.small_policy();p['duration_hours'] = 8
        guard.activate_burst('night', p)
        pacer = CampaignPacer(None, guard, clock=self.clock)
        self.assertEqual(pacer.credit_pool(per_seconds=3600), Decimal('.38'))
        self.assertEqual(pacer.room('openai'), 3)

    def test_invalid_policy_cannot_authorize_a_burst(self):
        for key,value in [('duration_hours', 100), ('luna_fraction', float('nan')),
                          ('research_workers',True), ('performance_min_blocks',0)]:
            p = load_policy();p[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(p)


class BurstGame(HouseCase):
    def test_faster_payout_preserves_absolute_paper_grace_and_replay_deadline(self):
        base=load_game();original=deepcopy(base)
        tuned=game_for(base, {'policy':load_policy()})
        self.assertEqual(base, original)
        self.assertEqual(tuned['research']['min_hours_between'], .25)
        for field in ('displace_after_epochs','replay_deadline_epochs'):
            self.assertEqual(tuned['economy'][field]*3600, base['economy'][field]*21600)
        self.assertEqual(tuned['economy']['newcomer_seconds'], 600)

    def test_twice_the_evidenced_growth_earns_eight_times_the_performance_share(self):
        game=game_for(load_game(), {'policy':load_policy()})
        economy=Economy(self.house.ledger,game,clock=self.clock)
        standings=[Standing('a','n',1,.004,25),Standing('b','n',1,.002,25),
                   Standing('lucky','n',1,.50,1)]
        shares=economy.shares(standings, '3')
        floor=Decimal('.15')
        self.assertAlmostEqual(float((shares['a']-floor)/(shares['b']-floor)),8,places=5)
        self.assertEqual(shares['lucky'], floor)
        self.assertLessEqual(sum(shares.values()), 3)

    def test_replay_replacement_requires_completed_opportunity_and_no_active_job(self):
        agent=self.seated();self.house.evaluator.seat(agent.id,0,'test replay')
        self.house._burst={'id':'night','started':self.clock(),'policy':load_policy()}
        rules=game_for(load_game(),self.house._burst)['economy']
        self.clock.advance(600)  # completed opportunity, not a mandatory hour of existence
        self.assertIsNone(self.house._weakest(rules))
        for n in range(2):
            self.house.ledger.append('agent.research',{'tool':'summary','reason':'finished'},agent=agent.id)
        self.assertEqual(self.house._weakest(rules).id,agent.id)
        self.house.research_jobs.enqueue(agent.id,list(self.house._generation(agent.id)))
        self.assertIsNone(self.house._weakest(rules))

    def test_new_paper_strategy_does_not_inherit_the_one_hour_research_lease(self):
        agent=self.seated()
        self.house._burst={'id':'night','started':self.clock(),'policy':load_policy()}
        rules=game_for(load_game(),self.house._burst)['economy']
        self.clock.advance(3601)
        for n in range(3):
            self.house.ledger.append('agent.research',{'tool':'summary','reason':'finished'},agent=agent.id)
        self.assertIsNone(self.house._weakest(rules))
