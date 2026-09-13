"""Synthetic frozen dossier exports; no live calls, secrets or ledger mutations."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import dossier as d
import operations
import portfolio as p
from scripts import export_dossier as export
import test_dossier as dossier_fixtures


class DossierExportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = dossier_fixtures.DossierTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.db, self.path = self.fixture.db, self.fixture.path
        self.identifier = self.fixture.create()
        self.frozen = d.protocol(self.db, self.identifier)
        self._seed()

    def _seed(self):
        completed = dict(self.frozen.get('seed_results', {}))
        self.rows = []
        for index, stage in enumerate(self.frozen['stages']):
            parents = {key: completed[key] for key in stage['parents']}
            body, selected = d.request(stage, self.frozen, parents)
            themes = d.THEMES if stage['theme'] == 'all' else (stage['theme'],)
            report = {'headline': 'PRIVATE MODEL HEADLINE', 'metrics': [],
                'claims': [{'text': 'PRIVATE MODEL PROSE', 'evidence_ids': list(selected)[:1]}],
                'caveats': ['PRIVATE CAVEAT'], 'next_tests': ['PRIVATE NEXT TEST']}
            for theme in themes:
                for wanted in self.frozen['rubric']['tasks'][theme]['metrics']:
                    reference = self.frozen['rubric']['expected'][wanted['id']]
                    report['metrics'].append({**wanted, 'value': reference['value'],
                        'evidence_ids': [group[0] for group in reference['required_evidence_groups']]})
            response = self.fixture.response(report, 'resp_synthetic_' + self.identifier + '_' + str(index))
            response['usage']['input_tokens_details']['cached_tokens'] = 100
            response['metadata'] = {'supercached_input_tokens': '0', 'supercache_write_input_tokens': '0'}
            result = {'status': 'completed', 'report': report,
                      'grade': d.grade(report, self.frozen['rubric'], stage['theme'])}
            key = 'dossier:' + self.identifier + ':' + stage['id']
            run_id = p.reserve_task(self.db, body, self.frozen['packet'], key,
                                   'critique' if stage['kind'] == 'critic' else 'investigate')
            with self.db:
                self.db.execute('UPDATE runs SET response_id=?,response=?,observed_seconds=?,error=? WHERE id=?',
                    (response['id'], p.encoded(response), index + 0.5, 'PRIVATE RAW ERROR', run_id))
                self.db.execute('INSERT INTO dossier_steps VALUES(?,?,?,?,?)',
                    (self.identifier, stage['id'], run_id, p.digest(body), p.encoded(result)))
            completed[stage['id']] = result
            self.rows.append((stage, run_id, result))
        self.assertEqual(self.fixture.calls, [])

    def snapshot(self):
        with closing(operations.connect(self.path)) as db:
            result = export.snapshot(db, self.identifier, now=self.fixture.now)
            self.assertEqual(db.total_changes, 0)
            self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0], 1)
            return result

    def change_result(self, index, mutate):
        stage, _, original = self.rows[index]
        changed = deepcopy(original)
        mutate(changed)
        with self.db:
            self.db.execute('DROP TRIGGER IF EXISTS dossier_step_update')
            self.db.execute('UPDATE dossier_steps SET result=? WHERE dossier_id=? AND stage_id=?',
                (p.encoded(changed), self.identifier, stage['id']))

    def test_closed_export_retains_all_costs_but_excludes_private_content(self):
        before = self.path.read_bytes()
        with patch.object(d, 'parse_report', side_effect=AssertionError('Do not reparse')), \
                patch.object(d, 'grade', side_effect=AssertionError('Do not regrade')):
            result = self.snapshot()
        self.assertEqual(before, self.path.read_bytes())
        summary = result['aggregate']
        self.assertEqual(summary['logical_requests'], 12)
        self.assertEqual(summary['distinct_accepted_responses'], 12)
        self.assertEqual(summary['contract_valid_stages'], 12)
        self.assertEqual(summary['graded_stages'], 12)
        self.assertEqual(summary['reserved_usd'], '6.4')
        self.assertEqual(summary['unknown_usage_stages'], 0)
        self.assertEqual(summary['usage']['known_input_tokens'], 12000)
        self.assertEqual(summary['usage']['known_cached_input_tokens'], 1200)
        serialized = json.dumps(result)
        for excluded in ('PRIVATE', self.identifier, 'resp_synthetic_', 'synthetic-fingerprint',
                         'Synthetic source:', 'PRIOR STAGES:', 'output_text'):
            self.assertNotIn(excluded, serialized)
        for _, run_id, _ in self.rows:
            self.assertNotIn(run_id, serialized)

    def test_invalid_final_output_is_ungraded_even_if_raw_json_would_parse(self):
        def invalidate(result):
            result.update(report=None, grade=None, error='PRIVATE INVALID CITATION')
        self.change_result(11, invalidate)
        with patch.object(d, 'parse_report', side_effect=AssertionError('No reparsing')):
            result = self.snapshot()
        final = result['stages'][-1]
        self.assertFalse(final['contract_valid'])
        self.assertFalse(final['grading']['graded'])
        self.assertIsNone(final['grading']['strict_passed'])
        self.assertIsNotNone(final['estimated_usd'])
        self.assertEqual(result['aggregate']['ungraded_stages'], 1)
        self.assertEqual(result['aggregate']['logical_requests'], 12)

    def test_numeric_and_source_coverage_errors_are_separate_frozen_observations(self):
        def change(result):
            check = next(iter(result['grade']['checks'].values()))
            check.update(passed=False, errors=['source_coverage'])
            result['grade']['passed'] -= 1
        self.change_result(11, change)
        grading = self.snapshot()['stages'][11]['grading']
        self.assertEqual(grading['numeric_passed'], 3)
        self.assertEqual(grading['provenance_passed'], 2)
        self.assertEqual(grading['strict_passed'], 2)
        self.assertEqual(grading['error_counts']['source_coverage'], 1)

    def test_unknown_usage_never_becomes_zero_or_drops_its_reservation(self):
        _, run_id, _ = self.rows[0]
        row = self.db.execute('SELECT response FROM runs WHERE id=?', (run_id,)).fetchone()
        response = json.loads(row['response'])
        response.pop('usage')
        with self.db:
            self.db.execute('UPDATE runs SET response=? WHERE id=?', (p.encoded(response), run_id))
        result = self.snapshot()
        self.assertIsNone(result['stages'][0]['usage'])
        self.assertIsNone(result['stages'][0]['estimated_usd'])
        self.assertIsNone(result['aggregate']['estimated_usd'])
        self.assertEqual(result['aggregate']['unknown_usage_stages'], 1)
        self.assertEqual(result['aggregate']['usage']['unknown_stages'], 1)
        self.assertEqual(result['aggregate']['reserved_usd'], '6.4')

    def test_nonterminal_or_unstored_stage_blocks_closed_export(self):
        with self.db:
            self.db.execute('DROP TRIGGER dossier_step_update')
            self.db.execute('UPDATE dossier_steps SET result=NULL WHERE stage_id=?', (self.rows[-1][0]['id'],))
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_orphan_reservation_and_duplicate_provider_identity_are_rejected(self):
        first_id, second_id = self.rows[0][1], self.rows[1][1]
        first = self.db.execute('SELECT response_id FROM runs WHERE id=?', (first_id,)).fetchone()
        row = self.db.execute('SELECT response FROM runs WHERE id=?', (second_id,)).fetchone()
        response = json.loads(row['response']); response['id'] = first['response_id']
        with self.db:
            self.db.execute('UPDATE runs SET response_id=?,response=? WHERE id=?',
                            (first['response_id'], p.encoded(response), second_id))
        with self.assertRaises(ValueError):
            self.snapshot()
        with self.db:
            self.db.execute('UPDATE runs SET task_key=? WHERE id=?',
                            ('dossier:' + self.identifier + ':orphan', second_id))
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_request_evidence_rate_and_grade_integrity_are_checked(self):
        first_id = self.rows[0][1]
        original = dict(self.db.execute('SELECT * FROM runs WHERE id=?', (first_id,)).fetchone())
        for field, value in [('request', '{}'), ('packet_sha256', '0' * 64),
                             ('rates', '{"input":"999","cached":"0","output":"999"}')]:
            with self.subTest(field=field):
                with self.db:
                    self.db.execute('UPDATE runs SET ' + field + '=? WHERE id=?', (value, first_id))
                with self.assertRaises((ValueError, KeyError)):
                    self.snapshot()
                with self.db:
                    self.db.execute('UPDATE runs SET ' + field + '=? WHERE id=?', (original[field], first_id))
        self.change_result(0, lambda result: result['grade'].update(passed=999))
        with self.assertRaises(ValueError):
            self.snapshot()

    def followup(self):
        self.change_result(11, lambda result: result.update(report=None, grade=None))
        self.parent_id = self.identifier
        self.parent_export = self.snapshot()
        self.identifier = d.followup(self.db, self.identifier, '2026-09-13T04:30:00Z')
        self.frozen = d.protocol(self.db, self.identifier)
        self._seed()

    def test_followup_is_separate_complete_measured_work_preserving_original_bytes(self):
        self.followup()
        before = self.path.read_bytes()
        result = self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(result['kind'], 'measured_dossier_followup')
        self.assertEqual(result['parent_protocol_sha256'], self.parent_export['protocol_sha256'])
        self.assertEqual(result['seed_results_sha256'], p.digest(self.frozen['seed_results']))
        self.assertEqual(result['aggregate']['logical_requests'], 2)
        self.assertEqual(result['aggregate']['reserved_usd'], '1.2')
        self.assertEqual(result['aggregate']['graded_metric_checks'], 6)
        self.assertEqual([item['stage'] for item in result['stages']],
                         ['source-complete-revision', 'source-complete-critic'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'research-dossier.json'
            export.write(self.parent_export, original)
            saved = original.read_bytes()
            with self.assertRaises(ValueError):
                export.write(result, original)
            export.write(result, Path(directory) / 'dossier-followup.json')
            self.assertEqual(original.read_bytes(), saved)

    def test_followup_rejects_rehashed_seed_parent_source_or_stage_contract_tampering(self):
        self.followup()
        mutations = [
            lambda value: value['seed_results']['synthesis']['report'].update(headline='changed seed'),
            lambda value: value.update(parent_protocol_sha256='0' * 64),
            lambda value: value.update(source_policy='partial-packet'),
            lambda value: value['snapshots']['fy26-call'].update(text='different source'),
            lambda value: value['stages'].reverse(),
        ]
        with self.db:
            self.db.execute('DROP TRIGGER dossier_protocol_update')
        for mutate in mutations:
            changed = deepcopy(self.frozen)
            mutate(changed)
            with self.db:
                self.db.execute('UPDATE dossiers SET protocol=?,sha256=? WHERE id=?',
                    (p.encoded(changed), p.digest(changed), self.identifier))
            with self.assertRaises(ValueError):
                self.snapshot()
        with self.db:
            self.db.execute('UPDATE dossiers SET protocol=?,sha256=? WHERE id=?',
                (p.encoded(self.frozen), p.digest(self.frozen), self.identifier))
        self.snapshot()

    def test_only_dedicated_atomic_artifact_can_be_written(self):
        result = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'research-dossier.json'
            export.write(result, destination)
            self.assertEqual(json.loads(destination.read_text()), result)
            self.assertEqual(list(Path(directory).iterdir()), [destination])
            with self.assertRaises(ValueError):
                export.write(result, Path(directory) / 'portfolio.json')
            destination.unlink()
            destination.symlink_to(Path(directory) / 'elsewhere')
            with self.assertRaises(ValueError):
                export.write(result, destination)


if __name__ == '__main__':
    unittest.main()
