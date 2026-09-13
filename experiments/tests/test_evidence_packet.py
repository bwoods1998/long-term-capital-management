"""Catch period/sign/calculation mistakes in the checked initial packet."""
import json
from pathlib import Path
import unittest


class EvidencePacketTests(unittest.TestCase):
    def test_cash_after_ppe_uses_same_year_and_positive_spend(self):
        packet = json.loads((Path(__file__).resolve().parents[1] / 'data/thesis/msft-ai-infrastructure.json').read_text())
        facts = {fact['id']: fact for fact in packet['facts']}
        for year in ('2025', '2026'):
            ocf, spend, result = (facts[f'{key}-{year}'] for key in ('ocf', 'ppe', 'cash-after-ppe'))
            self.assertGreater(spend['value'], 0)
            self.assertEqual(result['value'], ocf['value'] - spend['value'])
            for fact in (ocf, spend, result):
                self.assertEqual(fact['period'], f'FY{year}')
                self.assertEqual(fact['unit'], 'USD millions')
        self.assertGreater(facts['ocf-2026']['value'], facts['ocf-2025']['value'])
        self.assertLess(facts['cash-after-ppe-2026']['value'], facts['cash-after-ppe-2025']['value'])


if __name__ == '__main__':
    unittest.main()
