"""Check the financial oracle without model calls or account access."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / 'data/research/dossier-rubric.json'
CAPTURES = ROOT.parent / '.data/research/sources'


def reported_number(value):
    value = value.replace('$', '').replace(',', '')
    return Decimal('-' + value[1:-1] if value.startswith('(') else value)


class DossierRubricTests(unittest.TestCase):
    def setUp(self):
        self.rubric = json.loads(RUBRIC.read_text())
        self.expected = self.rubric['expected']

    def test_analyst_tasks_specify_the_contract_without_reference_answers(self):
        identifiers = []
        self.assertEqual(set(self.rubric['tasks']), {'cashflow', 'investment', 'demand'})
        for task in self.rubric['tasks'].values():
            self.assertEqual(set(task), {'instruction', 'metrics'})
            self.assertTrue(task['instruction'])
            for metric in task['metrics']:
                self.assertEqual(set(metric), {'id', 'unit', 'period'})
                reference = self.expected[metric['id']]
                self.assertEqual(metric['unit'], reference['unit'])
                self.assertEqual(metric['period'], reference['period'])
                identifiers.append(metric['id'])
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(set(identifiers), set(self.expected))
        self.assertIn('expected', self.rubric['model_visibility']['exclude'])
        self.assertIn('reported_rows', self.rubric['model_visibility']['exclude'])

    def test_complete_annual_rows_use_correct_columns_and_preserve_outflow_sign(self):
        rows = {row['id']: row for row in self.rubric['reported_rows']}
        audit = json.loads((ROOT / 'data/research/working-capital-audit.json').read_text())
        self.assertEqual(len(audit['rows']), 9)
        for audit_row in audit['rows']:
            identifier = audit_row['label'].lower().replace(' ', '_').replace('-', '_')
            for year in audit['periods']:
                self.assertEqual(self.expected[identifier + '_' + year.lower()]['value'], audit_row[year])
        for identifier, row in rows.items():
            self.assertEqual(row['column_order'], ['FY2026 Q4', 'FY2025 Q4', 'FY2026', 'FY2025'])
            self.assertEqual(row['unit'], 'USD millions')
            self.assertEqual(len(row['reported_cells']), 4)
            for year, index in [('FY2026', 2), ('FY2025', 3)]:
                raw = reported_number(row['reported_cells'][index])
                reference = self.expected[identifier + '_' + year.lower()]
                if identifier == 'cash_ppe':
                    self.assertLess(raw, 0)
                    self.assertEqual(row['operation'], 'negate')
                    raw = -raw
                else:
                    self.assertEqual(row['operation'], 'identity')
                self.assertEqual(raw, Decimal(reference['value']))
                self.assertEqual(reference['period'], year)
        for year in ('fy2026', 'fy2025'):
            self.assertLess(Decimal(self.expected['operating_assets_liabilities_total_' + year]['value']), 0)

    def test_every_derived_number_and_the_full_ocf_bridges_reconcile(self):
        for calculation in self.rubric['derived_checks']:
            self.assertEqual(calculation['operation'], 'linear_combination')
            computed = Decimal(0)
            for term in calculation['terms']:
                self.assertIn(term['coefficient'], ('-1', '1'))
                computed += Decimal(self.expected[term['metric_id']]['value']) * Decimal(term['coefficient'])
            self.assertEqual(computed, Decimal(self.expected[calculation['metric_id']]['value']), calculation['metric_id'])
        for bridge in self.rubric['reconciliation_checks']:
            self.assertEqual(len(bridge['right_metrics']), 6)
            self.assertEqual(Decimal(self.expected[bridge['left_metric']]['value']),
                             sum(Decimal(self.expected[key]['value']) for key in bridge['right_metrics']))
        self.assertEqual(self.expected['operating_cash_flow_change']['value'], '46773')
        self.assertEqual(self.expected['operating_assets_liabilities_change']['value'], '455')
        self.assertEqual(self.expected['remaining_seven_contribution_change']['value'], '-8167')
        # Preserve the reported rounded-data inconsistency rather than force an equality.
        self.assertEqual(Decimal(self.expected['component_minus_reported_capex_fy2026_q4']['value']), Decimal('0.4'))

    def test_citations_bind_complete_chunks_to_the_frozen_primary_sources(self):
        notes = json.loads((ROOT / 'data/research/source-notes.json').read_text())
        metadata = {item['id']: item for item in notes['initial_captures']}
        for identifier, source in self.rubric['sources'].items():
            for key in ('url', 'published_at', 'fetched_at', 'sha256'):
                self.assertEqual(source[key], metadata[identifier][key])
        for identifier, span in self.rubric['source_spans'].items():
            self.assertEqual(identifier, f'{span["source_id"]}:{span["start"]}:{span["end"]}')
            self.assertEqual(span['start'] % 1800, 0)
            self.assertEqual(span['end'], min(span['start'] + 1800, metadata[span['source_id']]['normalized_characters']))
            self.assertEqual(span['snapshot_sha256'], metadata[span['source_id']]['sha256'])
            self.assertRegex(span['span_sha256'], r'^[0-9a-f]{64}$')
        for metric in self.expected.values():
            self.assertTrue(re.fullmatch(r'-?\d+(?:\.\d+)?', metric['value']))
            self.assertTrue(metric['required_evidence_groups'])
            for group in metric['required_evidence_groups']:
                self.assertTrue(group)
                self.assertTrue(set(group) <= self.rubric['source_spans'].keys())
        # The RPO sentence crosses a chunk boundary; one half is insufficient.
        self.assertEqual(self.expected['commercial_rpo']['required_evidence_groups'],
                         [['fy26-call:21600:23400'], ['fy26-call:23400:25200']])

    @unittest.skipUnless(all((CAPTURES / (source + '.json')).is_file()
                            for source in ('fy26-results', 'fy26-call')),
                         'Original public-source captures are local and not committed')
    def test_available_original_captures_match_every_span_and_reported_cell(self):
        texts = {}
        for identifier, source in self.rubric['sources'].items():
            snapshot = json.loads((CAPTURES / (identifier + '.json')).read_text())
            self.assertEqual(hashlib.sha256(snapshot['text'].encode()).hexdigest(), source['sha256'])
            texts[identifier] = snapshot['text']
        for span in [*self.rubric['source_spans'].values(), *self.rubric['reported_rows']]:
            text = texts[span['source_id']][span['start']:span['end']]
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), span['span_sha256'])
            if 'reported_cells' in span:
                self.assertEqual(text.splitlines()[-4:], span['reported_cells'])


if __name__ == '__main__':
    unittest.main()
