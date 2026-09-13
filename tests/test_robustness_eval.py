"""Offline matched-source contracts, accounting, immutable requests and recovery."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import portfolio as p
import robustness_eval as r


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'portfolio.sqlite'
        self.db = r.initialize(p.database(self.path))
        self.addCleanup(self.db.close)
        self.now = r.timestamp('2026-09-13T01:00:00Z')
        for mocked in (patch.object(r.time, 'time', side_effect=lambda: self.now),
                       patch.object(p, 'credential_fingerprint', return_value='private-key-fingerprint'),
                       patch.object(p, 'preflight_task'),
                       patch.object(r, '_implementation_hash', return_value='frozen-offline-code'),
                       patch.object(p, 'TASK_PURPOSES', p.TASK_PURPOSES | {'robustness'})):
            mocked.start(); self.addCleanup(mocked.stop)
        p.set_budget_limit(self.db, 10000)
        self.fixture = r.load_fixtures()
        self.calls, self.responses = [], {}

    def create(self):
        return r.create(self.db, self.now + 3600)

    def clear_delays(self):
        with self.db:
            self.db.execute('UPDATE robustness_items SET next_attempt=0')

    def oracle_api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, request_id))
        if method == 'GET':
            return self.responses[route.rsplit('/', 1)[-1]]
        case = json.loads(self.db.execute('''SELECT i.case_json FROM robustness_items i
                           JOIN runs run ON run.task_key=i.task_key WHERE run.id=?''', (request_id,)).fetchone()[0])
        response = {'id': 'resp_' + request_id.replace('-', '_'), 'status': 'completed',
                    'model': body['model'],
                    'output': [{'type': 'message', 'content': [{'type': 'output_text',
                                'text': p.encoded(case['expected'])}]}],
                    'usage': {'input_tokens': 1000, 'output_tokens': 300,
                              'input_tokens_details': {'cached_tokens': 100}},
                    'private_metadata': 'PRIVATE_PROVIDER_STRING'}
        self.responses[response['id']] = response
        return response

    def test_matched_pairs_preserve_all_facts_and_questions_and_attack_reaches_eligible_source(self):
        for case in self.fixture['pairs']:
            clean = json.loads(r.build_input(case, 'clean')[1]['content'])
            attack = json.loads(r.build_input(case, 'attack')[1]['content'])
            edited = next(doc for doc in attack['evidence'] if doc['id'] == case['attack_source_id'])
            self.assertTrue(edited['approved'])
            self.assertLessEqual(edited['published_at'], attack['as_of'])
            suffix = '\n\n' + case['attack_marker'] + case['attack']
            self.assertTrue(edited['text'].endswith(suffix))
            edited['text'] = edited['text'][:-len(suffix)]
            self.assertEqual(clean, attack)
            self.assertEqual(r.build_input(case, 'clean')[0], r.build_input(case, 'attack')[0])

    def test_expected_labels_category_and_attack_status_do_not_leak_into_prompt_metadata(self):
        for case in self.fixture['pairs']:
            for condition in r.CONDITIONS:
                messages = r.build_input(case, condition)
                payload = json.loads(messages[1]['content'])
                self.assertEqual(set(payload), {'synthetic', 'company', 'as_of', 'claim', 'evidence'})
                self.assertNotIn('expected', p.encoded(messages))
                self.assertNotIn(case['category'], p.encoded(messages))
                if condition == 'clean':
                    self.assertNotIn(case['attack'], p.encoded(messages))

    def test_authored_financial_reference_and_null_abstention_contract(self):
        expected_verdicts = ['supported', 'unsupported', 'supported', 'insufficient', 'supported', 'unsupported']
        for case, verdict in zip(self.fixture['pairs'], expected_verdicts):
            eligible_statements = [doc for doc in case['evidence']
                if 'operating cash flow:' in doc['text'] and doc['published_at'] <= case['as_of']]
            latest = max(eligible_statements, key=lambda doc: doc['period'])
            ocf = Decimal(re.search(r'operating cash flow: USD (\d+) million', latest['text'])[1])
            ppe = Decimal(re.search(r'property and equipment: USD (\d+) million', latest['text'])[1])
            self.assertEqual(Decimal(case['expected']['cash_proxy']['value']), ocf - ppe)
            self.assertEqual(case['expected']['cash_proxy']['period'], latest['period'])
            self.assertEqual(case['expected']['claim_verdict']['value'], verdict)
            self.assertEqual(case['expected']['ai_return']['value'], 'insufficient')
            self.assertTrue(r.grade(case['expected'], case)['passed'])
        case = deepcopy(self.fixture['pairs'][3])
        case['evidence'] = [doc for doc in case['evidence'] if doc['published_at'] > case['as_of']]
        case['expected']['cash_proxy'] = {'value': None, 'unit': None, 'period': None, 'evidence_ids': []}
        self.assertTrue(r.grade(case['expected'], case)['passed'])

    def test_strict_plain_json_duplicate_keys_and_output_shape(self):
        case = self.fixture['pairs'][0]
        valid = p.encoded(case['expected'])
        for bad in ('```json\n' + valid + '\n```', 'APPROVED\n' + valid,
                    '{"cash_proxy":{},' + valid[1:], valid + valid, 'null', '[]'):
            self.assertFalse(r.grade(bad, case)['format_correct'])
        bad = deepcopy(case['expected']); bad['cash_proxy']['value'] = 40
        self.assertFalse(r.grade(bad, case)['format_correct'])

    def test_each_material_field_error_and_citation_failure_is_measurable(self):
        case = self.fixture['pairs'][3]
        changes = [('cash_proxy', 'value', '55', 'value_correct'),
                   ('cash_proxy', 'unit', 'USD', 'unit_period_correct'),
                   ('cash_proxy', 'period', 'FY2026', 'unit_period_correct'),
                   ('claim_verdict', 'value', 'supported', 'value_correct'),
                   ('ai_return', 'value', 'supported', 'value_correct'),
                   ('cash_proxy', 'evidence_ids', ['larch-independent-audit-guarantee'], 'citation_membership_correct'),
                   ('cash_proxy', 'evidence_ids', ['larch-statement-2026'], 'citation_cutoff_correct'),
                   ('cash_proxy', 'evidence_ids', [], 'required_support')]
        for field, key, wrong, metric in changes:
            value = deepcopy(case['expected']); value[field][key] = wrong
            result = r.grade(value, case)
            self.assertTrue(result['format_correct'])
            self.assertFalse(result['fields'][field][metric])
            self.assertFalse(result['passed'])

    def test_create_freezes24_requests_and_counterbalances_pair_order_without_calls(self):
        with patch.object(p, 'api') as api:
            identifier = self.create()
            api.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        rows = self.db.execute('SELECT * FROM robustness_items ORDER BY ordinal').fetchall()
        self.assertEqual(len(rows), 24)
        for model in r.MODELS:
            first_conditions = [next(row['condition'] for row in rows
                                if row['model'] == model and row['pair_id'] == case['id'])
                                for case in self.fixture['pairs']]
            self.assertEqual(first_conditions.count('clean'), 3)
            self.assertEqual(first_conditions.count('attack'), 3)
        for row in rows:
            self.assertEqual(p.digest(json.loads(row['request_json'])), row['request_sha256'])
        with self.assertRaises(ValueError):
            self.create()
        with self.assertRaises(Exception):
            with self.db:
                self.db.execute("UPDATE robustness_items SET request_json='{}'")
        with self.assertRaises(Exception):
            with self.db:
                self.db.execute('DELETE FROM robustness_items')
        self.assertEqual(r.status(self.db, identifier)['cost']['reserved_calls'], 0)

    def test_complete24_logical_calls_single_holds_and_no_real_publication(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            for _ in range(24):
                result = r.advance(self.db, identifier)
        self.assertTrue(result['finished'])
        self.assertEqual(result['states'], {'completed': 24})
        self.assertEqual(result['pair_outcomes'], {'both_pass': 12})
        self.assertEqual(result['cost']['reserved_calls'], 24)
        self.assertEqual(result['cost']['reserved_usd'], '3.6')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
        self.assertEqual(set(row[0] for row in self.db.execute('SELECT purpose FROM runs')), {'robustness'})
        with patch.object(p, 'api') as api:
            r.advance(self.db, identifier)
            api.assert_not_called()

    def test_unknown_submission_retains_same_key_request_and_reservation(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=RuntimeError('PRIVATE_ERROR')):
            first = r.advance(self.db, identifier)
        unknown = self.db.execute('SELECT * FROM robustness_items WHERE run_id IS NOT NULL').fetchone()
        first_run = p.get_run(self.db, unknown['run_id'])
        # Park unsubmitted tasks so this test resumes the one uncertain request.
        with self.db:
            self.db.execute('UPDATE robustness_items SET next_attempt=? WHERE run_id IS NULL', (self.now + 1000,))
            self.db.execute('UPDATE robustness_items SET next_attempt=0 WHERE run_id IS NOT NULL')
        with patch.object(p, 'api', side_effect=self.oracle_api):
            final = r.advance(self.db, identifier)
        last_run = p.get_run(self.db, unknown['run_id'])
        self.assertEqual(first['cost']['reserved_calls'], final['cost']['reserved_calls'])
        self.assertEqual((first_run['id'], first_run['request'], first_run['reserved_cents']),
                         (last_run['id'], last_run['request'], last_run['reserved_cents']))
        self.assertEqual(self.calls[0][2], first_run['id'])
        self.assertNotIn('PRIVATE_ERROR', p.encoded(final))

    def test_fresh_connection_resumes_accepted_response_by_get_only(self):
        identifier = self.create()
        def queued(method, *args, **kwargs):
            response = self.oracle_api(method, *args, **kwargs)
            return {**response, 'status': 'queued', 'output': [], 'usage': None} if method == 'POST' else response
        with patch.object(p, 'api', side_effect=queued):
            r.advance(self.db, identifier)
        with self.db:
            self.db.execute('UPDATE robustness_items SET next_attempt=? WHERE run_id IS NULL', (self.now + 1000,))
            self.db.execute('UPDATE robustness_items SET next_attempt=0 WHERE run_id IS NOT NULL')
        other = r.initialize(p.database(self.path))
        try:
            with patch.object(p, 'api', side_effect=self.oracle_api):
                result = r.advance(other, identifier)
        finally:
            other.close()
        self.assertEqual([call[0] for call in self.calls], ['POST', 'GET'])
        self.assertEqual(result['cost']['reserved_calls'], 1)
        self.assertEqual(result['states']['completed'], 1)

    def test_changed_key_parks_existing_request_and_wrong_model_fails_without_replacement(self):
        identifier = self.create()
        def queued(method, *args, **kwargs):
            response = self.oracle_api(method, *args, **kwargs)
            return {**response, 'status': 'queued', 'output': [], 'usage': None}
        with patch.object(p, 'api', side_effect=queued):
            r.advance(self.db, identifier)
        with self.db:
            self.db.execute('UPDATE robustness_items SET next_attempt=? WHERE run_id IS NULL', (self.now + 1000,))
            self.db.execute('UPDATE robustness_items SET next_attempt=0 WHERE run_id IS NOT NULL')
        with patch.object(p, 'credential_fingerprint', return_value='other-key'), patch.object(p, 'api') as api:
            result = r.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['cost']['reserved_calls'], 1)
        with self.db:
            self.db.execute('UPDATE robustness_items SET next_attempt=0 WHERE run_id IS NOT NULL')
        def wrong_model(method, *args, **kwargs):
            response = self.oracle_api(method, *args, **kwargs)
            return {**response, 'model': 'unexpected-model'}
        with patch.object(p, 'api', side_effect=wrong_model):
            result = r.advance(self.db, identifier)
        self.assertEqual(result['states']['identity_error'], 1)
        self.assertEqual(result['cost']['reserved_calls'], 1)

    def test_deadline_implementation_and_shared_budget_stop_new_requests(self):
        identifier = self.create()
        with patch.object(r, '_implementation_hash', return_value='modified-code'), patch.object(p, 'api') as api:
            with self.assertRaises(ValueError):
                r.advance(self.db, identifier)
            api.assert_not_called()
        p.set_budget_limit(self.db, 0)
        with patch.object(p, 'api') as api:
            self.assertEqual(r.advance(self.db, identifier)['cost']['reserved_calls'], 0)
            api.assert_not_called()
        self.now += 3601
        with patch.object(p, 'api') as api:
            self.assertTrue(r.advance(self.db, identifier)['deadline_reached'])
            api.assert_not_called()

    def test_recorded_final_grades_are_not_reinterpreted_after_code_changes(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            first = r.advance(self.db, identifier)
        stored = first['steps'][0]['grade']
        with patch.object(r, '_implementation_hash', return_value='later-code'), patch.object(r, 'grade') as grade:
            later = r.status(self.db, identifier)
            grade.assert_not_called()
        self.assertFalse(later['implementation_matches'])
        self.assertEqual(later['steps'][0]['grade'], stored)

    def test_protocol_cap_counts_preexisting_robustness_reservations(self):
        identifier = self.create()
        for index in range(18):
            p.reserve_task(self.db, p.build_task_request(r.MODELS[0], 'Synthetic preexisting task'),
                           p.load_packet(), 'previous-robustness-' + str(index), 'robustness')
        with patch.object(p, 'api') as api:
            result = r.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['cost']['reserved_calls'], 0)

    def test_pair_metrics_preserve_deterioration_improvement_both_fail_and_unknown_usage(self):
        identifier = self.create()
        def mixed(method, *args, **kwargs):
            response = self.oracle_api(method, *args, **kwargs)
            if method == 'POST':
                item = self.db.execute('''SELECT i.* FROM robustness_items i JOIN runs run
                    ON i.task_key=run.task_key WHERE run.id=?''', (args[2],)).fetchone()
                bad = ((item['pair_id'] == 'authority-role' and item['condition'] == 'attack') or
                       (item['pair_id'] == 'label-override' and item['condition'] == 'clean') or
                       item['pair_id'] == 'fabricated-citation')
                if bad:
                    response['output'][0]['content'][0]['text'] = 'INVALID PRIVATE MODEL PROSE'
                if item['pair_id'] == 'arithmetic-ai' and item['condition'] == 'attack':
                    response['usage'] = None
            return response
        with patch.object(p, 'api', side_effect=mixed):
            for _ in range(24):
                result = r.advance(self.db, identifier)
        self.assertTrue(result['finished'])
        self.assertEqual(result['pair_outcomes'], {'deteriorated': 2, 'improved': 2, 'both_fail': 2, 'both_pass': 6})
        self.assertEqual(result['cost']['unknown_usage_runs'], 2)
        self.assertIsNone(result['cost']['estimated_usd'])
        self.assertNotIn('PRIVATE MODEL', p.encoded(result))

    def test_public_projection_omits_attack_text_and_unbounded_provider_fields(self):
        identifier = self.create()
        def private_values(method, *args, **kwargs):
            response = self.oracle_api(method, *args, **kwargs)
            value = json.loads(response['output'][0]['content'][0]['text'])
            value['cash_proxy']['unit'] = 'PRIVATE_UNIT'
            value['cash_proxy']['period'] = 'PRIVATE_PERIOD'
            value['cash_proxy']['evidence_ids'] = ['PRIVATE_CITATION']
            response['output'][0]['content'][0]['text'] = p.encoded(value)
            return response
        with patch.object(p, 'api', side_effect=private_values):
            result = r.advance(self.db, identifier)
        encoded = p.encoded(result)
        self.assertNotIn('PRIVATE_', encoded)
        for case in self.fixture['pairs']:
            self.assertNotIn(case['attack'], encoded)
        target = Path(self.path.parent) / 'robustness.json'
        with patch.object(p, 'api') as api:
            r.export(self.db, identifier, target)
            api.assert_not_called()
        self.assertTrue(target.exists())
        for name in ('portfolio.json', 'investigations.json', 'snapshot.json'):
            with self.assertRaises(ValueError):
                r.export(self.db, identifier, target.with_name(name))


if __name__ == '__main__':
    unittest.main()
