"""Candidate data preflight and engineering requests must report actual availability."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from league.capabilities import coverage_needs
from league.researcher import Pass
from league.tests.test_house import HouseCase
from league.tests.test_researcher import ResearchCase


NEEDS = {'venue': 'kalshi', 'horizon': 'hour', 'style': 'favorites', 'series': ['KXBTC15M'],
         'observe': {'symbols': ['BTC/USD', 'BNB/USD']}, 'bars': {'timeframe': '5Min', 'limit': 60}}


class CandidateCoverageValidation(unittest.TestCase):
    def setUp(self):
        self.agent = SimpleNamespace(venue='kalshi', horizon='hour', needs=deepcopy(NEEDS))

    def test_inputs_are_bounded_before_any_data_read(self):
        for change in ({'symbols': 'BTC/USD'}, {'observe': []}, {'bars': []},
                       {'bars': {'limit': True}}, {'bars': {'limit': 201}},
                       {'bars': {'timeframe': 'tick'}}, {'venue': 'alpaca'},
                       {'horizon': 'day'}, {'observe': {'symbols': ['BTC/USD'] * 7}},
                       {'series': ['KXBTC15M'] * 13}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                coverage_needs(self.agent, {**NEEDS, **change})

    def test_preflight_does_not_mutate_candidate_or_current_needs(self):
        proposed = deepcopy(NEEDS)
        out = coverage_needs(self.agent, proposed)
        out['observe']['symbols'].clear()
        self.assertEqual(proposed, NEEDS)
        self.assertEqual(self.agent.needs, NEEDS)


class CandidateCoverageHouse(HouseCase):
    def agent(self):
        return self.house.registry.born(name='coverage', family='test', code='def decide(ctx): return {}',
            needs={'venue': 'kalshi', 'horizon': 'hour', 'series': ['KXBTC15M']}, specialty='kalshi-crypto-15m')

    def tape(self, needs):
        return 'frozen-test', {'venue': 'kalshi', 'horizon': 'hour', 'steps': [],
                              'observed_bars': {'BTC/USD': [{'t': '2026-09-20T00:00:00Z', 'c': 100}]}}

    def test_one_missing_symbol_does_not_hide_available_bars(self):
        agent = self.agent()
        before = deepcopy(agent.needs)
        self.house.tape_for = self.tape
        self.house.sandbox.needs = lambda *a, **k: self.fail('preflight must not buy a probe')
        self.house.sandbox.replay = lambda *a, **k: self.fail('preflight must not buy a replay')
        report = self.house.research_coverage(agent, NEEDS)
        self.assertEqual(report['missing_observed_symbols'], ['BNB/USD'])
        self.assertEqual(report['observed_bars']['BTC/USD']['rows'], 1)
        self.assertFalse(report['observed_inputs_available'])
        self.assertTrue(report['proposed_inputs'])
        self.assertEqual(agent.needs, before)
        self.assertEqual(self.house.ledger.count(kinds='eval.trial'), 0)
        narrower = deepcopy(NEEDS)
        narrower['observe']['symbols'] = ['BTC/USD']
        self.assertTrue(self.house.research_coverage(agent, narrower)['observed_inputs_available'])

    def test_bad_candidate_does_not_reach_the_data_provider(self):
        self.house.tape_for = lambda *a: self.fail('invalid reads must be refused before fetching')
        result = self.house.research_coverage(self.agent(), {**NEEDS, 'observe': {'symbols': 'BTC/USD'}})
        self.assertEqual(result['mode'], 'unavailable')
        self.assertFalse(result['counted_as_trial'])

    def test_replay_error_identifies_only_the_missing_symbol(self):
        self.house.tape_for = self.tape
        with self.assertRaisesRegex(ValueError, 'missing for BNB/USD; use replay_coverage'):
            self.house._run_replay(self.agent(), 'unused', NEEDS, {})
        self.assertEqual(self.house.ledger.count(kinds='experiment.started'), 0)


class CandidateCoverageTool(ResearchCase):
    def test_tool_forwards_proposed_needs_without_changing_the_agent(self):
        seen = []
        researcher = self.researcher([], coverage=lambda agent, needs=None:
            seen.append((agent.id, needs)) or {'counted_as_trial': False})
        researcher._execute(self.parent, 'replay_coverage', {'needs': NEEDS}, Pass(self.parent.id), 's')
        self.assertEqual(seen, [(self.parent.id, NEEDS)])
        self.assertNotIn('observe', self.parent.needs)

    def test_current_coverage_keeps_the_legacy_one_argument_callback(self):
        researcher = self.researcher([], coverage=lambda agent: {'agent': agent.id})
        self.assertEqual(researcher._execute(self.parent, 'replay_coverage', {}, Pass(self.parent.id), 's'),
                         {'agent': self.parent.id})
