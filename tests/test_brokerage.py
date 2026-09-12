from copy import deepcopy
from decimal import Decimal
import json
import unittest

import brokerage


class BrokerageTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads(brokerage.FIXTURE.read_text())

    def test_reconciles_partial_fills_and_excludes_deposits_from_profit(self):
        original = deepcopy(self.case)
        result = brokerage.reconcile(self.case)
        self.assertTrue(result['reconciled'])
        self.assertEqual(result['expected_cash'], '1137.82')
        self.assertEqual(result['expected_positions'], {'DEMO': '4'})
        self.assertEqual(result['unfilled_quantities'], {'demo-buy': '1'})
        self.assertEqual(result['net_external_cashflow'], '200')
        self.assertEqual(result['investment_pnl'], '17.82')
        self.assertEqual(result['fees'], '0.03')
        self.assertEqual(self.case, original)

    def test_fractional_positions_use_exact_decimal_arithmetic(self):
        self.case['opening']['positions']['DEMO']['quantity'] = '0.1'
        self.case['closing']['positions']['DEMO']['quantity'] = '0.3'
        self.case['orders'] = [{'id': 'fraction', 'symbol': 'DEMO', 'side': 'buy', 'quantity': '0.2'}]
        self.case['fills'] = [{'id': 'f', 'order_id': 'fraction', 'quantity': '0.2', 'price': '0.1', 'fee': '0'}]
        self.case['cashflows'] = []
        self.case['closing']['cash'] = '999.98'
        result = brokerage.reconcile(self.case)
        self.assertTrue(result['reconciled'])
        self.assertEqual(result['expected_positions']['DEMO'], '0.3')

    def test_rejects_nonfinite_float_and_unbounded_decimals(self):
        for invalid in ['NaN', 'Infinity', '-Infinity', '1e999999', ' 1', '1_000',
                        '0.123456789', '1000000000000', 1.25, True, None]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                brokerage.number(invalid, 'test')
        self.assertEqual(brokerage.number('0.00000001', 'test'), Decimal('0.00000001'))

    def test_duplicate_fill_rejected_instead_of_double_counting(self):
        self.case['fills'].append(deepcopy(self.case['fills'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate fill'):
            brokerage.reconcile(self.case)

    def test_discrepancies_prevent_reporting_profit_as_reconciled(self):
        self.case['closing']['cash'] = '1137.83'
        self.case['closing']['positions']['DEMO']['quantity'] = '5'
        result = brokerage.reconcile(self.case)
        self.assertFalse(result['reconciled'])
        self.assertEqual(result['cash_difference'], '0.01')
        self.assertEqual(result['position_differences'], {'DEMO': '1'})
        self.assertIsNone(result['investment_pnl'])

    def test_rejects_unknown_order_overfill_and_reversed_funding(self):
        changes = [
            ('fills', 0, 'order_id', 'missing'),
            ('fills', 0, 'quantity', '4'),
            ('cashflows', 0, 'amount', '-250'),
            ('cashflows', 1, 'amount', '50'),
        ]
        for field, index, key, value in changes:
            case = deepcopy(self.case)
            case[field][index][key] = value
            with self.subTest(change=(field, key)), self.assertRaises(ValueError):
                brokerage.reconcile(case)

    def test_non_synthetic_or_non_usd_input_is_rejected(self):
        for field, value in [('synthetic', False), ('currency', 'EUR'), ('schema_version', 2)]:
            case = deepcopy(self.case)
            case[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                brokerage.reconcile(case)


if __name__ == '__main__':
    unittest.main()
