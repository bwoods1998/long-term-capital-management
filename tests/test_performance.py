"""Offline funding, fee, valuation and benchmark integrity contracts."""
from copy import deepcopy
from decimal import Decimal, localcontext
from datetime import timedelta
from fractions import Fraction
import json
import unittest

import performance as p


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.cases = {case['id']: case for case in json.loads(p.FIXTURE.read_text())}

    def test_deposit_and_withdrawal_are_funding_not_return_or_loss(self):
        result = p.calculate(self.cases['funding-only'])
        self.assertEqual(result['closing_equity'], '150')
        self.assertEqual(result['net_external_funding'], '50')
        self.assertEqual(result['investment_pnl'], '0')
        self.assertEqual(result['time_weighted_return_pct'], '0')
        self.assertTrue(all(row['portfolio_return_pct'] == '0' for row in result['subperiods']))

    def test_fees_lower_equity_once_and_research_expense_does_not_change_return(self):
        case = self.cases['fees-only']
        result = p.calculate(case)
        self.assertEqual(result['investment_pnl'], '-2')
        self.assertEqual(result['time_weighted_return_pct'], '-2')
        self.assertEqual(result['reported_fees_already_in_equity'], '2')
        case['research_expense_outside_portfolio']['value'] = '99'
        self.assertEqual(p.calculate(case)['time_weighted_return_pct'], '-2')
        case['closing']['value'] = '100'; case['fees_in_equity']['value'] = '0'
        self.assertEqual(p.calculate(case)['investment_pnl'], '0')

    def test_chain_matches_independent_rational_oracle_and_aligned_benchmark(self):
        result = p.calculate(self.cases['growth-and-funding'])
        exact = Fraction(110, 100) * Fraction(231, 210) * Fraction(179, 181)
        ratio = result['exact_portfolio_growth_ratio']
        self.assertEqual(Fraction(ratio['numerator']) / Fraction(ratio['denominator']), exact)
        self.assertEqual(result['investment_pnl'], '29')
        self.assertEqual(result['time_weighted_return_pct'], '19.662983425414')
        self.assertEqual(result['benchmark_return_pct'], '10.25')
        self.assertEqual(result['difference_percentage_points'], '9.412983425414')
        self.assertNotEqual(result['time_weighted_return_pct'], '79')

    def test_decimal_accounting_survives_low_ambient_precision_and_tiny_changes(self):
        case = self.cases['fees-only']
        case['opening']['value'] = '999999999999.00000001'
        case['closing']['value'] = '999999999999.00000002'
        with localcontext() as context:
            context.prec = 2
            result = p.calculate(case)
        self.assertEqual(result['investment_pnl'], '0.00000001')
        self.assertEqual(result['exact_portfolio_growth_ratio']['numerator'], case['closing']['value'])
        self.assertEqual(result['exact_portfolio_growth_ratio']['denominator'], case['opening']['value'])

    def test_missing_or_noninstantaneous_flow_valuations_are_rejected(self):
        for phase in ('before', 'after'):
            case = deepcopy(self.cases['funding-only']); del case['external_flows'][0][phase]
            with self.assertRaises(ValueError): p.calculate(case)
            case = deepcopy(self.cases['funding-only'])
            case['external_flows'][0][phase]['at'] = '2026-07-02T00:00:01Z'
            with self.assertRaises(ValueError): p.calculate(case)

    def test_flow_boundary_cannot_hide_market_moves_fees_or_wrong_sign(self):
        for change in ('unexplained_move', 'wrong_sign', 'wrong_kind', 'zero'):
            case = deepcopy(self.cases['funding-only']); flow = case['external_flows'][0]
            if change == 'unexplained_move': flow['after']['value'] = '199'
            if change == 'wrong_sign': flow['amount']['value'] = '-100'
            if change == 'wrong_kind': flow['kind'] = 'dividend'
            if change == 'zero': flow['amount']['value'] = '0'
            with self.assertRaises(ValueError): p.calculate(case)

    def test_duplicate_out_of_order_boundary_and_ambiguous_timestamps_fail(self):
        for at in ('2026-07-01', '2026-07-01T00:00:00', '2026-07-01T00:00:00+00:00',
                   '2026-07-01T00:00:00.1Z', '2026-13-01T00:00:00Z'):
            case = deepcopy(self.cases['funding-only']); case['opening']['at'] = at
            with self.assertRaises(ValueError): p.calculate(case)
        for change in ('duplicate', 'unordered', 'at_start', 'at_end'):
            case = deepcopy(self.cases['funding-only']); flows = case['external_flows']
            if change == 'duplicate': flows[1]['id'] = flows[0]['id']
            if change == 'unordered': flows.reverse()
            if change == 'at_start': flows[0]['at'] = case['opening']['at']
            if change == 'at_end': flows[-1]['at'] = case['closing']['at']
            with self.assertRaises(ValueError): p.calculate(case)

    def test_mismatched_missing_or_different_currency_benchmark_is_rejected(self):
        for change in ('missing', 'shifted', 'currency', 'price_only', 'unit'):
            case = deepcopy(self.cases['funding-only']); benchmark = case['benchmark']
            if change == 'missing': benchmark['observations'].pop(1)
            if change == 'shifted': benchmark['observations'][1]['at'] = '2026-07-02T00:01:00Z'
            if change == 'currency': benchmark['currency'] = 'EUR'
            if change == 'price_only': benchmark['kind'] = 'price_index'
            if change == 'unit': benchmark['observations'][0]['unit'] = 'USD'
            with self.assertRaises(ValueError): p.calculate(case)

    def test_nonpositive_denominators_fail_but_terminal_total_loss_is_valid(self):
        for target in ('opening', 'after_flow', 'benchmark'):
            case = deepcopy(self.cases['funding-only'])
            if target == 'opening': case['opening']['value'] = '0'
            if target == 'after_flow':
                flow = case['external_flows'][1]
                flow['amount']['value'] = '-200'; flow['after']['value'] = '0'
            if target == 'benchmark': case['benchmark']['observations'][1]['value'] = '0'
            with self.assertRaises(ValueError): p.calculate(case)
        case = self.cases['fees-only']; case['closing']['value'] = '0'
        self.assertEqual(p.calculate(case)['time_weighted_return_pct'], '-100')

    def test_ambiguous_numbers_units_and_live_payloads_are_rejected(self):
        for number in (100.0, True, 'NaN', 'Infinity', '1e2', '01', '1000000000000', '0.000000001'):
            case = deepcopy(self.cases['fees-only']); case['opening']['value'] = number
            with self.assertRaises(ValueError): p.calculate(case)
        case = self.cases['fees-only']; case['opening']['unit'] = 'USD millions'
        with self.assertRaises(ValueError): p.calculate(case)
        case['opening']['unit'] = 'USD'; case['synthetic'] = False
        with self.assertRaises(ValueError): p.calculate(case)
        with self.assertRaises(ValueError): json.loads('{"value":"1","value":"2"}', object_pairs_hook=p.unique)

    def test_maximum_boundary_count_retains_exact_large_products(self):
        case = deepcopy(self.cases['fees-only']); equity = Decimal('888888888888.00000001')
        case['opening']['value'] = str(equity)
        for index in range(p.MAX_FLOWS):
            at = (p.stamp(case['opening']['at']) + timedelta(seconds=index + 1)).strftime('%Y-%m-%dT%H:%M:%SZ')
            case['external_flows'].append({'id': 'flow-' + str(index), 'kind': 'deposit', 'at': at,
                'amount': {'value': '1', 'unit': 'USD'}, 'before': {'at': at, 'value': str(equity), 'unit': 'USD'},
                'after': {'at': at, 'value': str(equity + 1), 'unit': 'USD'}})
            case['benchmark']['observations'].insert(-1, {'at': at, 'value': '100', 'unit': 'index_points'})
            equity += 1
        case['closing']['value'] = str(equity)
        result = p.calculate(case)
        self.assertEqual(result['time_weighted_return_pct'], '0')
        self.assertEqual(result['investment_pnl'], '0')
        case['external_flows'].append(deepcopy(case['external_flows'][-1]))
        with self.assertRaises(ValueError): p.calculate(case)


if __name__ == '__main__':
    unittest.main()
