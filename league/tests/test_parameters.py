"""Regression: children born with 108% probabilities or an inverted entry band."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from league import parameters, seeds
from league.runner import needs_of
from league.tests.test_house import BUYER, HouseCase


BINARY = '''
NEEDS = {'venue': 'kalshi', 'horizon': 'hour', 'style': 'test', 'series': ['KXBTCD']}
PARAMS = {'bid_min': 0.9, 'bid_max': 0.97, 'max_open': 6, 'notional_usd': 10.0}
def decide(ctx):
    return {'intents': [], 'memory': {}}
'''


class ParameterDomains(unittest.TestCase):
    def test_real_production_failures_are_rejected(self):
        for params in ({'bid_min': 1.076411, 'bid_max': 1.080175},
                       {'bid_min': .948687, 'bid_max': .923309}):
            with self.subTest(params=params), self.assertRaisesRegex(ValueError, 'invalid parameters'):
                parameters.mutate(params, seed='newcomer:52', needs={'venue': 'kalshi'})

    def test_many_children_preserve_domains_types_and_change_one_knob(self):
        parent = {'bid_min': .9, 'bid_max': .97, 'no_bid_min': .88, 'max_open': 6,
                  'notional_usd': 10., 'maker': True, 'unknown_units': 1.08, 'symbols': ['BTC/USD']}
        original = deepcopy(parent)
        children = []
        for seed in range(1000):
            child = parameters.mutate(parent, seed=str(seed), needs={'venue': 'kalshi'})
            self.assertTrue(0 <= child['bid_min'] <= child['bid_max'] <= 1)
            self.assertTrue(0 <= child['no_bid_min'] <= 1)
            self.assertIs(type(child['max_open']), int)
            self.assertIs(child['maker'], True)
            self.assertEqual(child['unknown_units'], parent['unknown_units'])
            self.assertEqual(sum(parent[k] != child[k] for k in parent), 1)
            children.append(child)
        self.assertEqual(parent, original)
        self.assertGreater(len({str(c) for c in children}), 100)

    def test_declared_units_enable_a_custom_knob_and_frozen_knobs_stay_fixed(self):
        params = {'custom': 0., 'notional_usd': 10.}
        needs = {'parameter_rules': {'bounds': {'custom': [0, 1]}, 'frozen': ['notional_usd']}}
        child = parameters.mutate(params, seed='zero', needs=needs)
        self.assertGreater(child['custom'], 0)
        self.assertLessEqual(child['custom'], 1)
        self.assertEqual(child['notional_usd'], 10)
        self.assertEqual(child, parameters.mutate(dict(reversed(list(params.items()))), seed='zero', needs=needs))

    def test_undeclared_numbers_do_not_create_identical_children(self):
        with self.assertRaisesRegex(ValueError, 'no distinct valid'):
            parameters.mutate({'mystery': 1.1}, seed='a')

    def test_a_finite_exhausted_space_does_not_repeat_a_living_configuration(self):
        needs = {'parameter_rules': {'bounds': {'count': [1, 2]}}}
        with self.assertRaisesRegex(ValueError, 'no distinct valid'):
            parameters.mutate({'count': 1}, seed='a', needs=needs, excluded=[{'count': 2}])

    def test_declared_rules_cannot_broaden_probability_units(self):
        needs = {'venue': 'kalshi', 'parameter_rules': {'bounds': {'bid_max': [-100, 100]}}}
        self.assertFalse(parameters.inspect({'bid_max': 1.08}, needs)['valid'])

    def test_invalid_rule_shapes_fail_with_a_reason(self):
        for rules in (None, [], {'typo': 1}, {'bounds': []}, {'bounds': {'x': [2, 1]}},
                      {'bounds': {'x': [False, 1]}}, {'bounds': {'missing': [0, 1]}},
                      {'ordered': 'x'}, {'ordered': [['x', 'missing']]}, {'frozen': 'x'}):
            with self.subTest(rules=rules):
                self.assertFalse(parameters.inspect({'x': 0.}, {'parameter_rules': rules})['valid'])

    def test_nested_nonfinite_values_and_boolean_or_string_prices_are_refused(self):
        for bad in ({'bid_min': True}, {'bid_min': '.9'}, {'x': [float('nan')]},
                    {'x': {'nested': float('inf')}}, {'x': 10 ** 400}):
            with self.subTest(params=bad):
                self.assertFalse(parameters.inspect(bad, {'venue': 'kalshi'})['valid'])

    def test_dollar_prices_are_not_treated_as_probabilities(self):
        self.assertTrue(parameters.inspect({'bid_max': 200.0}, {'venue': 'alpaca'})['valid'])

    def test_overflowing_proposals_are_refused_without_crashing_the_house(self):
        with self.assertRaisesRegex(ValueError, 'no distinct valid'):
            parameters.mutate({'max_open': 10 ** 308}, seed='extreme', scale=1)

    def test_clock_window_and_custom_relationships_are_enforced(self):
        cases = [({'buy_start': 960, 'buy_end': 930}, {}),
                 ({'flat_at': 1500}, {}), ({'lookback': 201}, {'bars': {'limit': 200}}),
                 ({'max_open': 1.2}, {}), ({'rsi_entry': 120.}, {}),
                 ({'lower': 2, 'upper': 1}, {'parameter_rules': {'ordered': [['lower', 'upper']]}})]
        for params, needs in cases:
            with self.subTest(params=params):
                self.assertFalse(parameters.inspect(params, needs)['valid'])

    def test_every_seed_has_valid_defaults_and_valid_mutations(self):
        for seed in seeds.SEEDS:
            description = needs_of(seeds.load(seed['name']))
            for trial in range(20):
                with self.subTest(seed=seed['name'], trial=trial):
                    child = parameters.mutate(description['params'], seed=str(trial), needs=description['needs'])
                    self.assertTrue(parameters.inspect(child, description['needs'])['valid'])


class ParameterAdmission(HouseCase):
    def legacy(self):
        agent = self.house.spawn('binary', 'test', BINARY)
        bad = {**agent.params, 'bid_min': 1.076411, 'bid_max': 1.080175}
        self.house.ledger.append('agent.strategy', {'_code': agent.code, 'params': bad,
            'needs': agent.needs, 'code_sha256': agent.code_sha256, 'reason': 'historical bad mutation'}, agent=agent.id)
        self.house.registry.refresh()
        return self.house.registry.get(agent.id)

    def test_invalid_birth_is_not_registered_or_endowed(self):
        with self.assertRaisesRegex(ValueError, 'invalid parameters'):
            self.house.spawn('bad', 'test', BINARY, params={'bid_min': 1.08})
        self.assertEqual(self.house.registry.living(), [])
        self.assertEqual(self.house.ledger.count(kinds='agent.born'), 0)

    def test_invalid_candidate_does_not_fetch_tape_or_run_or_count_a_trial(self):
        agent = self.house.spawn('binary', 'test', BINARY)
        with patch.object(self.house, 'tape_for') as tape, patch.object(self.house.sandbox, 'replay') as replay:
            result = self.house._candidate_replay(agent, BINARY.replace("'bid_min': 0.9", "'bid_min': 1.08"))
        self.assertFalse(result['counted_as_trial'])
        self.assertIn('invalid parameters', result['error'])
        tape.assert_not_called()
        replay.assert_not_called()
        self.assertEqual(self.house.ledger.count(kinds='eval.trial'), 0)
        self.assertEqual(self.house.ledger.count(kinds='experiment.started'), 0)

    def test_legacy_invalid_replay_is_refused_before_any_paid_work(self):
        agent = self.legacy()
        with patch.object(self.house, '_run_replay') as run:
            result = self.house._replay_own(agent)
        run.assert_not_called()
        self.assertEqual(result['skipped'], 'invalid parameters')
        with patch.object(self.house, 'tape_for') as tape, self.assertRaisesRegex(ValueError, 'invalid parameters'):
            self.house._run_replay(agent, agent.code, agent.needs, agent.params)
        tape.assert_not_called()

    def test_legacy_read_preserves_history_and_explains_the_problem_to_research(self):
        agent = self.legacy()
        count = self.house.ledger.count(kinds='agent.strategy')
        report = self.house.research_capabilities(agent)['parameters']
        self.assertFalse(report['valid'])
        self.assertIn('bid_min', '; '.join(report['errors']))
        self.assertEqual(agent.params['bid_min'], 1.076411)
        self.assertEqual(self.house.ledger.count(kinds='agent.strategy'), count)

    def test_legacy_invalid_parent_does_not_pay_for_or_endow_a_child(self):
        agent = self.legacy()
        self.house.economy.grant(agent.id, '20', 'test')
        before = self.house.economy.balance(agent.id)
        with patch.object(self.house.sandbox, 'needs') as probe:
            self.assertIsNone(self.house.fork(agent))
            self.assertIsNone(self.house.fork(agent))
        probe.assert_not_called()
        self.assertEqual(self.house.economy.balance(agent.id), before)
        self.assertEqual(self.house.ledger.count(kinds='agent.born'), 1)
        self.assertEqual(self.house.ledger.count(kinds='agent.mutation'), 1)

    def test_stale_retained_invalid_candidate_cannot_be_adopted(self):
        agent = self.house.spawn('binary', 'test', BINARY)
        outcome = SimpleNamespace(candidate={'code': BINARY, 'needs': agent.needs,
            'params': {**agent.params, 'bid_min': 1.08}, 'passed': True})
        self.assertIsNone(self.house._commit_research(agent.id, self.house._generation(agent.id), outcome))
        self.assertEqual(agent.params['bid_min'], .9)
        self.assertEqual(self.house.ledger.last('agent.research').payload['status'], 'not_adopted')

    def test_legacy_parameter_repair_stays_unqualified_and_preserves_evidence(self):
        agent = self.legacy()
        generation = self.house._generation(agent.id)
        before_credit = self.house.economy.balance(agent.id)
        self.house.ledger.append('eval.trial', {'passed': False, 'trades': 0}, agent=agent.id)
        candidate = {'code': BINARY, 'needs': agent.needs, 'params': {**agent.params, 'bid_min': .9, 'bid_max': .97},
                     'passed': False, 'purpose': 'repair invalid probabilities', 'numbers': {'trades': 0}}
        out = SimpleNamespace(candidate=candidate, consulted='')
        self.assertIsNone(self.house._commit_research(agent.id, generation, out))
        repaired = self.house.registry.get(agent.id)
        self.assertEqual(repaired.params['bid_min'], .9)
        self.assertEqual(repaired.code, BINARY)
        self.assertEqual(self.house.evaluator.rung(agent.id), 0)
        self.assertEqual(self.house.ledger.count(kinds='eval.trial', agent=agent.id), 1)
        self.assertEqual(self.house.ledger.count(kinds='eval.verdict', agent=agent.id), 0)
        self.assertEqual(self.house.economy.balance(agent.id), before_credit)

    def test_a_failed_repair_cannot_change_decision_logic(self):
        agent = self.legacy()
        old = dict(agent.params)
        candidate = {'code': BINARY.replace("'memory': {}", "'memory': {'changed': True}"),
                     'needs': agent.needs, 'params': {**old, 'bid_min': .9, 'bid_max': .97},
                     'passed': False, 'purpose': 'not just a repair', 'numbers': {'trades': 0}}
        self.house._commit_research(agent.id, self.house._generation(agent.id), SimpleNamespace(candidate=candidate, consulted=''))
        self.assertEqual(self.house.registry.get(agent.id).params, old)
        self.assertFalse(parameters.same_logic(BINARY, BINARY.replace("'bid_min': 0.9", "'bid_min': probe()")))

    def test_refill_tries_a_valid_parent_after_an_invalid_one(self):
        invalid = self.legacy()
        valid = self.house.spawn('healthy', 'test', BINARY)
        self.house.economy.grant(invalid.id, '20', 'test')
        rules = self.house.game['economy']
        rules.update(newcomer_seconds=600, max_population=3, min_population=0)
        self.clock.advance(601)
        child = self.house._refill(rules)
        self.assertEqual(child.parent, valid.id)
        self.assertTrue(parameters.inspect(child.params, child.needs)['valid'])

    def test_no_resident_is_displaced_when_no_distinct_mutation_exists(self):
        code = BUYER.replace('PARAMS = {"notional": 20.0}', 'PARAMS = {}')
        weak = self.seated('weak', code)
        other = self.seated('other', code)
        rules = self.house.game['economy']
        rules.update(newcomer_seconds=600, max_population=2, min_population=0)
        self.clock.advance(601)
        with patch.object(self.house, '_weakest', return_value=weak):
            self.assertIsNone(self.house._refill(rules))
        self.assertTrue(weak.alive and other.alive)
        self.assertEqual(self.house.ledger.count(kinds='agent.died'), 0)

    def test_population_cadence_is_checked_before_displacing_anyone(self):
        weak = self.seated('weak')
        self.seated('other')
        rules = self.house.game['economy']
        rules.update(newcomer_seconds=600, max_population=2, min_population=0)
        self.clock.advance(601)
        self.house._state['last_newcomer']['at'] = self.clock()
        with patch.object(self.house, '_weakest', return_value=weak):
            self.assertIsNone(self.house._refill(rules))
        self.assertTrue(weak.alive)

    def test_options_smoke_uses_the_candidate_parameters_and_inputs(self):
        agent = self.house.spawn('options', 'test', seeds.load('options-breakout'), specialty='alpaca-options')
        self.house.seat(agent)
        candidate = seeds.load('options-pullback')
        expected = needs_of(candidate)
        with patch.object(self.house, 'snapshot', wraps=self.house.snapshot) as snapshot, \
                patch.object(self.house.sandbox, 'decide', wraps=self.house.sandbox.decide) as decide:
            result = self.house._candidate_replay(agent, candidate)
        self.assertTrue(result['passed'], result)
        measured = snapshot.call_args.args[0]
        self.assertEqual(measured.params, expected['params'])
        self.assertEqual(measured.needs['bars'], expected['needs']['bars'])
        self.assertEqual(decide.call_args.args[2]['params'], expected['params'])
        self.assertEqual(agent.params['breakout_days'], 20)
