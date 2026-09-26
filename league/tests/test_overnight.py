"""A faster game must preserve evidence and its funded window across concurrency/restarts."""
import unittest
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

    def test_an_owner_top_up_raises_the_ceiling_and_resets_nothing(self):
        guard = self.budget(); guard.activate_burst('night', self.small_policy())
        guard.reserve('spent', 'foundation-review', '2')
        self.assertEqual(guard.remaining('openai'), 1)
        guard.top_up('topup-1:openai', 'openai', '5', 'owner added credit')
        guard.top_up('topup-1:openai', 'openai', '5', 'owner added credit')  # idempotent
        import time as _time
        this_month = _time.strftime('%Y-%m', _time.gmtime(guard.clock()))
        self.assertEqual(guard.topped_up('openai', this_month), Decimal('5'))  # the Sail meter's line follows its kind
        self.assertEqual(guard.topped_up('sail', this_month), Decimal('0'))
        self.assertEqual(guard.topped_up('openai', '1999-01'), Decimal('0'))
        self.assertEqual(guard.remaining('openai'), 6)
        self.assertEqual(guard.burst()['policy']['caps_usd']['openai'], '8')
        with self.assertRaises(CampaignClosed):
            guard.top_up('topup-1:openai', 'openai', '9', 'a different amount')
        with self.assertRaises(ValueError):
            guard.top_up('big', 'openai', '1001', 'too much at once')
        self.assertEqual(guard.activate_burst('night', self.small_policy())['id'], 'night')  # still idempotent
        self.assertTrue(guard.reserve('more', 'foundation-review', '5'))

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
        from league.overnight import load_turbo
        turbo = load_turbo()  # the owner's acceleration (turbo.json) sits on top of the burst policy
        self.assertEqual(tuned['research']['min_hours_between'], turbo.get('research_minutes', 15) / 60)
        for field in ('displace_after_epochs','replay_deadline_epochs'):
            self.assertEqual(tuned['economy'][field]*3600, base['economy'][field]*21600)
        self.assertEqual(tuned['economy']['newcomer_seconds'], turbo.get('newcomer_seconds', 600))

    def test_turbo_reallocates_merton_cadence_by_measured_yield(self):
        from unittest.mock import patch
        with patch('league.overnight.load_turbo', return_value={'merton_schedule_hours': {'operator': 4, 'designer': 12, 'nobody': 1, 'teacher': 0}}):
            tuned = game_for(load_game(), {'policy': load_policy()})
        hours = tuned['merton']['schedule_hours']
        self.assertEqual((hours['operator'], hours['designer']), (4.0, 12.0))  # the turbo's allocation
        self.assertEqual(hours['architect'], .5)  # the burst's default stands
        self.assertEqual(hours['teacher'], load_game()['merton']['schedule_hours']['teacher'])  # zero is ignored; the burst
        # no longer accelerates the teacher, whose cadence is a bounded dial (Sept 24, 2026)
        self.assertNotIn('nobody', hours)

    def test_turbo_speeds_the_loop_without_touching_the_stored_policy(self):
        from unittest.mock import patch
        from league import overnight
        policy = load_policy()
        stored = deepcopy(policy)
        with patch.object(overnight, 'load_turbo', return_value={'research_minutes': 5, 'newcomer_seconds': 120,
                                                                 'max_population': 60, 'research_workers': 20,
                                                                 'sail_profile': 'pro_asap'}):
            game = game_for(load_game(), {'policy': policy})
            accelerated = overnight.policy_with_turbo({'policy': policy})
        self.assertEqual(policy, stored)
        self.assertAlmostEqual(game['research']['min_hours_between'], 5 / 60)
        self.assertEqual((game['economy']['newcomer_seconds'], game['economy']['max_population']), (120, 60))
        self.assertEqual(game['research']['profile'], 'pro_asap')
        self.assertEqual(accelerated['research_workers'], 20)

    def test_a_newborn_forks_only_once_it_has_earned_credits(self):
        """Sept 23, 2026: the burst's fork threshold sits above its endowment (turbo), so a newborn
        cannot spend its stake on a parameter copy of itself; one that earns payouts can."""
        from unittest.mock import patch
        from league import overnight
        policy = load_policy()
        with patch.object(overnight, 'load_turbo', return_value={'endowment_usd': 8, 'fork_threshold_usd': 10}):
            game = game_for(load_game(), {'policy': policy})
        economy = game['economy']
        self.assertGreater(float(economy['fork_threshold_usd']), float(economy['endowment_usd']))
        with patch.object(overnight, 'load_turbo', return_value={}):
            self.assertEqual(game_for(load_game(), {'policy': policy})['economy']['fork_threshold_usd'], '2.00')
        self.assertEqual(overnight.load_turbo(), {})  # the repository's turbo.json left with the options overhaul (Sept 26, 2026)

    def test_turbo_out_of_range_is_refused(self):
        from unittest.mock import patch
        from league import overnight
        import json
        with patch.object(overnight.Path, 'read_text', return_value=json.dumps({'research_minutes': 1})):
            with self.assertRaises(ValueError):
                overnight.load_turbo()

    def test_faster_frontier_access_is_for_winners_only(self):
        base = load_game()
        game = game_for(load_game(), {'policy': load_policy()})
        self.assertEqual(game['consult']['cooldown_hours_by_rung'], base['consult']['cooldown_hours_by_rung'])
        self.assertLess(game['consult']['profitable_cooldown_hours_by_rung']['1'], base['consult']['profitable_cooldown_hours_by_rung']['1'])

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


class TheResearchEconomyDials(unittest.TestCase):
    """L2 (Sept 24, 2026, the close-the-gaps run): the risk-free dials this wave adds, and the one
    turbo dial that never reached the House.

    `load_turbo` copied only the keys of `TURBO_RANGES` and `sail_profile`, so the turbo layer's
    `merton_schedule_hours` -- the re-allocation of Merton's cadence by measured yield recorded in
    turbo.json on Sept 22 and 23 (operator 48 h, designer 96 h, toolsmith 48 h, architect 24 h) --
    was dropped, and the burst's own defaults ran instead: the snapshot's ledger shows the teacher
    sitting down about hourly and the architect every 30 to 60 minutes on Sept 23."""

    @unittest.skip("Wave 2b deletes overnight.py: the options overhaul (Sept 26, 2026) took turbo.json out of the repository")
    def test_the_repository_turbo_carries_merton_and_the_sail_research_cap(self):
        from league import overnight

        turbo = overnight.load_turbo()
        self.assertEqual(turbo["merton_schedule_hours"]["teacher"], 12)
        self.assertEqual(turbo["sail_research_usd_per_hour"], 2)
        hours = game_for(load_game(), {"policy": load_policy()})["merton"]["schedule_hours"]
        self.assertEqual(hours["teacher"], 12.0)
        self.assertEqual(hours, {role: float(v) for role, v in turbo["merton_schedule_hours"].items()})

    def test_out_of_bounds_turbo_dials_are_refused(self):
        from unittest.mock import patch
        from league import overnight

        for bad in ({"sail_research_usd_per_hour": 0.5}, {"sail_research_usd_per_hour": 5}, {"sail_research_usd_per_hour": "2"},
                    {"merton_schedule_hours": {"teacher": 4}}, {"merton_schedule_hours": {"teacher": 25}},
                    {"merton_schedule_hours": {"operator": 0}}, {"merton_schedule_hours": {"nobody": 3}}):
            with patch.object(overnight.Path, "read_text", return_value=json.dumps(bad)):
                with self.assertRaises(ValueError, msg=bad):
                    overnight.load_turbo()

    def test_the_game_file_pauses_the_code_roles_and_bounds_the_teacher(self):
        from league.economy import check_bounds

        game = load_game()
        self.assertEqual(sorted(game["merton"]["paused_until_profit"]), ["architect", "designer", "operator", "toolsmith"])
        self.assertEqual(game["merton"]["schedule_hours"]["teacher"], 12)
        self.assertNotIn("gate", game["research"])  # Jev's research gate left game.json with the options overhaul (Sept 26, 2026)
        for mutate in (lambda g: g["merton"]["schedule_hours"].update(teacher=5), lambda g: g["merton"]["schedule_hours"].update(teacher=25),
                       lambda g: g["merton"].update(paused_until_profit=["architect", "auditor"])):
            changed = deepcopy(game)
            mutate(changed)
            with self.assertRaises(ValueError):
                check_bounds(changed)
        for subset in ([], ["teacher"], ["architect", "toolsmith", "operator", "designer", "teacher"]):
            changed = deepcopy(game)
            changed["merton"]["paused_until_profit"] = subset
            check_bounds(changed)  # any subset of Merton's roles
