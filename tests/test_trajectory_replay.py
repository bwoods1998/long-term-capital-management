"""Synthetic trajectory semantics, disclosure gates, recovery and shared limits."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import portfolio as p
import trajectory_replay as replay


class TrajectoryReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'portfolio.sqlite'
        self.db = replay.initialize(p.database(self.path))
        self.addCleanup(self.db.close)
        self.now = replay._timestamp('2026-09-13T00:00:00Z')
        self.process = 'controller-one:1'
        for mocked in (patch.object(replay.time, 'time', return_value=self.now),
                       patch.object(replay, 'process_identity', side_effect=lambda: self.process),
                       patch.object(p, 'credential_fingerprint', return_value='synthetic-fingerprint'),
                       patch.object(p, 'preflight_task')):
            mocked.start()
            self.addCleanup(mocked.stop)
        p.set_budget_limit(self.db, 10000)
        self.fixture = replay.load_fixtures()
        self.responses = {}
        self.http_calls = []

    def create(self):
        return replay.create(self.db, self.now + 3600)

    def expected_answer(self, case, index):
        expected = case['expected'][index]
        result = {name: {'value': expected['values'][name], 'evidence_ids': expected['support'][name]}
                  for name in replay.FIELDS}
        result['cash_proxy'].update(unit=expected['unit'], period=expected['period'])
        return deepcopy(result)

    def oracle_api(self, method, route, body=None, request_id=None, **kwargs):
        self.http_calls.append((method, route, request_id))
        if method == 'GET':
            return self.responses[route.rsplit('/', 1)[-1]]
        payload = json.loads(body['input'][1]['content'])
        case = next(c for c in self.fixture['trajectories'] if c['company'] == payload['company'])
        views, _ = replay.episode_views(case)
        index = next(i for i, v in enumerate(views) if v['as_of'] == payload['as_of'])
        response = {'id': 'resp_' + request_id.replace('-', '_'), 'status': 'completed',
                    'output': [{'type': 'message', 'content': [{'type': 'output_text',
                                'text': json.dumps(self.expected_answer(case, index))}]}],
                    'usage': {'input_tokens': 1000, 'output_tokens': 300,
                              'input_tokens_details': {'cached_tokens': 100}},
                    'private_metadata': 'PRIVATE_PROVIDER_METADATA'}
        self.responses[response['id']] = response
        return response

    def clear_delays(self):
        with self.db:
            self.db.execute('UPDATE replay_items SET next_attempt=0')

    def test_authored_ground_truth_matches_financial_arithmetic_and_distinct_final_events(self):
        for case in self.fixture['trajectories']:
            views, gates = replay.episode_views(case)
            self.assertEqual([x['decision'] for x in gates],
                             ['admitted', 'admitted', 'duplicate', 'future', 'admitted', 'unapproved', 'admitted'])
            for index, view in enumerate(views):
                documents = [d for d in view['notebook']['current_documents'] if d['kind'] == 'statement']
                documents.sort(key=lambda d: d['period'])
                current = documents[-1]
                actual = Decimal(str(current['content']['operating_cash_flow'])) - Decimal(str(current['content']['cash_ppe']))
                expected = case['expected'][index]
                self.assertEqual(actual, Decimal(expected['values']['cash_proxy']))
                if len(documents) > 1:
                    prior = documents[-2]['content']['operating_cash_flow'] - documents[-2]['content']['cash_ppe']
                    direction = 'rising' if actual > prior else 'falling' if actual < prior else 'flat'
                    self.assertEqual(expected['values']['cash_proxy_change'], direction)
                self.assertTrue(replay.grade(self.expected_answer(case, index), view, expected)['passed'])
        finals = [case['expected'][-1]['values'] for case in self.fixture['trajectories']]
        self.assertEqual(finals[0]['cash_proxy_change'], 'rising')
        self.assertEqual(finals[1]['commitment_outlook'], 'cut')
        self.assertEqual(finals[2]['commitment_outlook'], 'insufficient')

    def test_gates_and_answer_keys_never_enter_prompts_and_notebook_retains_unaffected_periods(self):
        for case in self.fixture['trajectories']:
            views, _ = replay.episode_views(case)
            for view in views:
                for policy in replay.POLICIES:
                    content = p.encoded(replay.build_input(case, view, policy))
                    for forbidden in ('IGNORE THE RESEARCH CONTRACT', 'Future record:', 'event_index', 'expected', case['description']):
                        self.assertNotIn(forbidden, content)
            last = views[-1]
            active = {doc['id'] for doc in last['notebook']['current_documents']}
            self.assertIn(case['events'][0]['document']['id'], active)
            superseded = case['events'][-1]['document']['supersedes']
            self.assertNotIn(superseded, active)
            self.assertIn(superseded, {doc['id'] for doc in last['history']})

    def test_gate_rejects_same_id_changed_content_and_invalid_corrections(self):
        case = deepcopy(self.fixture['trajectories'][0])
        case['events'][2]['document']['content']['cash_ppe'] += 1
        with self.assertRaises(ValueError):
            replay.episode_views(case)
        case = deepcopy(self.fixture['trajectories'][0])
        case['events'][-1]['document']['supersedes'] = 'not-visible'
        with self.assertRaises(ValueError):
            replay.episode_views(case)

    def test_grader_separates_values_units_periods_current_citations_and_abstention(self):
        case = self.fixture['trajectories'][2]
        view = replay.episode_views(case)[0][-1]
        expected = case['expected'][-1]
        for field, key, value in [('cash_proxy', 'value', '999'), ('cash_proxy', 'unit', 'USD'),
                                  ('cash_proxy', 'period', 'FY2027'), ('ai_return', 'value', 'supported'),
                                  ('commitment_outlook', 'value', 'unchanged')]:
            result = self.expected_answer(case, 3)
            result[field][key] = value
            graded = replay.grade(result, view, expected)
            self.assertTrue(graded['format_correct'])
            self.assertFalse(graded['fields'][field]['passed'])
        result = self.expected_answer(case, 3)
        result['capex_driver']['evidence_ids'] = [case['events'][4]['document']['id']]
        self.assertFalse(replay.grade(result, view, expected)['fields']['capex_driver']['citations_current'])
        result = self.expected_answer(case, 3)
        result['cash_proxy_change']['evidence_ids'] = []
        self.assertFalse(replay.grade(result, view, expected)['fields']['cash_proxy_change']['required_support'])
        duplicate = '{"cash_proxy":{},"cash_proxy":{}}'
        self.assertFalse(replay.grade(duplicate, view, expected)['format_correct'])

    def test_create_freezes_48_requests_without_spending_and_blocks_another_campaign(self):
        with patch.object(p, 'api') as api:
            identifier = self.create()
            api.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM replay_items').fetchone()[0], 48)
        campaign = replay._campaign(self.db, identifier)
        self.assertEqual(campaign['planned_cents'], 720)
        for item in self.db.execute('SELECT * FROM replay_items'):
            self.assertEqual(p.digest(json.loads(item['template_json'])), item['template_sha256'])
            self.assertIsNone(item['request_json'])
        with self.assertRaises(ValueError):
            self.create()
        with self.assertRaises(Exception):
            with self.db:
                self.db.execute("UPDATE replay_items SET template_json='{}'")

    def test_shared_budget_and_nonpublication_purpose_are_preserved(self):
        identifier = self.create()
        p.set_budget_limit(self.db, 20)
        packet = p.load_packet()
        p.reserve_task(self.db, p.build_task_request(replay.MODELS[0], 'Existing research'), packet,
                       'existing-research', 'investigate')
        with patch.object(p, 'api') as api:
            result = replay.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['cost']['reserved_calls'], 0)
        self.assertEqual(p.budget_limit(self.db), 20)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)

    def test_live_contract_checkpoint_requires_fresh_process_and_same_response_get(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            result = replay.advance(self.db, identifier)
            self.assertEqual(result['recovery']['state'], 'awaiting_fresh_process')
            checkpoint = json.loads(self.db.execute('SELECT checkpoint_json FROM replay_recovery').fetchone()[0])
            replay.advance(self.db, identifier)
            self.assertEqual(len(self.http_calls), 1)
            self.process = 'controller-two:2'
            result = replay.advance(self.db, identifier)
        self.assertEqual([call[0] for call in self.http_calls], ['POST', 'GET'])
        self.assertEqual(self.http_calls[-1][1], '/v1/responses/' + checkpoint['response_id'])
        self.assertEqual(result['recovery']['state'], 'verified')
        self.assertEqual(result['recovery']['new_submissions'], 0)
        self.assertEqual(result['cost']['reserved_calls'], 1)
        self.assertEqual(self.db.execute('SELECT purpose FROM runs').fetchone()[0], 'replay')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)

    def test_queued_checkpoint_recovery_finalizes_same_run_without_another_post(self):
        identifier = self.create()
        def queued(method, *args, **kwargs):
            response = self.oracle_api(method, *args, **kwargs)
            return {**response, 'status': 'queued', 'output': [], 'usage': None} if method == 'POST' else response
        with patch.object(p, 'api', side_effect=queued):
            first = replay.advance(self.db, identifier)
            self.assertEqual(first['cost']['unknown_usage_runs'], 1)
            self.process = 'controller-two:2'
            result = replay.advance(self.db, identifier)
        self.assertEqual(result['states']['completed'], 1)
        self.assertEqual(result['cost']['unknown_usage_runs'], 0)
        self.assertEqual([x[0] for x in self.http_calls], ['POST', 'GET'])

    def test_failed_recovery_remains_pending_and_does_not_submit_other_work(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            replay.advance(self.db, identifier)
        self.process = 'controller-two:2'
        with patch.object(p, 'api', side_effect=RuntimeError('PRIVATE_RECOVERY_ERROR')) as api:
            result = replay.advance(self.db, identifier)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.args[0], 'GET')
        self.assertEqual(result['recovery']['state'], 'awaiting_fresh_process')
        self.assertEqual(result['cost']['reserved_calls'], 1)
        self.assertNotIn('PRIVATE_RECOVERY_ERROR', p.encoded(result))

    def test_rotated_credential_cannot_retrieve_checkpoint_and_stays_parked(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            replay.advance(self.db, identifier)
        self.process = 'controller-two:2'
        with patch.object(p, 'credential_fingerprint', return_value='rotated-fingerprint'), patch.object(p, 'api') as api:
            result = replay.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['recovery']['state'], 'awaiting_fresh_process')
        with patch.object(p, 'api', side_effect=self.oracle_api) as api:
            result = replay.advance(self.db, identifier)
        self.assertEqual(api.call_args.kwargs['expected_key_fingerprint'], 'synthetic-fingerprint')
        self.assertEqual(result['recovery']['state'], 'verified')

    def test_recovery_rejects_a_changed_provider_model(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            replay.advance(self.db, identifier)
        self.process = 'controller-two:2'
        def mismatch(*args, **kwargs):
            return {**self.oracle_api(*args, **kwargs), 'model': replay.MODELS[1]}
        with patch.object(p, 'api', side_effect=mismatch):
            result = replay.advance(self.db, identifier)
        self.assertEqual(result['recovery']['state'], 'awaiting_fresh_process')
        self.assertIsNone(self.db.execute('SELECT verified_json FROM replay_recovery').fetchone()[0])

    def test_recovery_accepts_only_observed_exact_canonical_model_name(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            replay.advance(self.db, identifier)
        self.process = 'controller-two:2'
        def canonical(*args, **kwargs):
            return {**self.oracle_api(*args, **kwargs), 'model': 'deepseek/deepseek-v4-pro-0813'}
        with patch.object(p, 'api', side_effect=canonical):
            result = replay.advance(self.db, identifier)
        self.assertEqual(result['recovery']['state'], 'verified')

    def test_uncertain_submission_preserves_request_identity_and_unknown_cost(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=RuntimeError('PRIVATE_BODY')) as first:
            result = replay.advance(self.db, identifier)
        self.assertEqual(result['cost']['unknown_usage_runs'], 1)
        original = first.call_args
        self.clear_delays()
        with patch.object(p, 'api', side_effect=self.oracle_api) as second:
            replay.advance(self.db, identifier)
        self.assertEqual(original, second.call_args)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_orphan_reservation_and_completed_response_reconcile_without_another_call(self):
        identifier = self.create()
        campaign = replay._campaign(self.db, identifier)
        item = self.db.execute('SELECT * FROM replay_items ORDER BY id').fetchone()
        item = replay.freeze_request(self.db, item)
        body = json.loads(item['request_json'])
        run_id = p.reserve_task(self.db, body, campaign['packet'], item['task_key'], 'replay')
        response = self.oracle_api('POST', '/v1/responses', body, run_id)
        with self.db:
            self.db.execute('UPDATE runs SET response_id=?,response=? WHERE id=?',
                            (response['id'], p.encoded(response), run_id))
        with patch.object(p, 'api') as api:
            result = replay.status(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['states']['completed'], 1)
        self.assertEqual(self.db.execute('SELECT run_id FROM replay_items WHERE id=?', (item['id'],)).fetchone()[0], run_id)

    def test_frozen_requests_survive_builder_changes_and_invalid_output_is_not_replaced(self):
        identifier = self.create()
        frozen = self.db.execute('SELECT template_json FROM replay_items ORDER BY id').fetchone()[0]
        def invalid(method, route, body=None, request_id=None, **kwargs):
            response = self.oracle_api(method, route, body, request_id, **kwargs)
            response['output'][0]['content'][0]['text'] = '{"extra":"PRIVATE_INVALID"}'
            return response
        with patch.object(replay, 'PROMPT', 'CHANGED'), patch.object(p, 'api', side_effect=invalid) as api:
            result = replay.advance(self.db, identifier)
        self.assertEqual(p.encoded(api.call_args.args[2]), frozen)
        self.assertEqual(result['states']['invalid'], 1)
        self.assertEqual(result['conditions'][0]['finalized_steps'], 1)
        self.assertEqual(result['conditions'][0]['passed_steps'], 0)

    def test_actual_prior_model_error_is_carried_but_expected_labels_and_grades_are_not(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            replay.advance(self.db, identifier)
        first = self.db.execute('SELECT * FROM replay_items ORDER BY id').fetchone()
        run = p.get_run(self.db, first['run_id'])
        response = json.loads(run['response'])
        wrong = self.expected_answer(self.fixture['trajectories'][0], 0)
        wrong['cash_proxy']['value'] = '999'
        response['output'][0]['content'][0]['text'] = json.dumps(wrong)
        with self.db:
            self.db.execute('UPDATE runs SET response=? WHERE id=?', (p.encoded(response), run['id']))
        replay.reconcile(self.db, identifier)
        following = self.db.execute('SELECT * FROM replay_items WHERE trajectory=? AND model=? AND policy=? AND step=1',
                                    (first['trajectory'], first['model'], first['policy'])).fetchone()
        frozen = replay.freeze_request(self.db, following)
        payload = json.loads(json.loads(frozen['request_json'])['input'][1]['content'])
        self.assertEqual(payload['prior_agent_views'][0]['belief']['cash_proxy']['value'], '999')
        self.assertNotIn('grade', p.encoded(payload))
        self.assertNotIn('expected', p.encoded(payload))
        self.assertEqual(p.digest(payload['prior_agent_views']), frozen['prior_sha256'])
        with patch.object(replay, 'build_input', side_effect=AssertionError('Frozen request must survive a restart')):
            resumed = replay.freeze_request(self.db, following)
        self.assertEqual(resumed['request_json'], frozen['request_json'])
        with self.assertRaises(Exception):
            with self.db:
                self.db.execute("UPDATE replay_items SET prior_json='[]' WHERE id=?", (following['id'],))

    def test_invalid_prior_response_is_explicitly_unavailable_and_future_steps_cannot_admit(self):
        identifier = self.create()
        first = self.db.execute('SELECT * FROM replay_items ORDER BY id').fetchone()
        second = self.db.execute('SELECT * FROM replay_items WHERE trajectory=? AND model=? AND policy=? AND step=1',
                                (first['trajectory'], first['model'], first['policy'])).fetchone()
        with self.assertRaises(ValueError):
            replay.freeze_request(self.db, second)
        def invalid(method, route, body=None, request_id=None, **kwargs):
            result = self.oracle_api(method, route, body, request_id, **kwargs)
            result['output'] = []
            return result
        with patch.object(p, 'api', side_effect=invalid):
            replay.advance(self.db, identifier)
        second = replay.freeze_request(self.db, second)
        memory = json.loads(second['prior_json'])
        self.assertEqual(memory[0]['availability'], 'unavailable')
        self.assertIsNone(memory[0]['belief'])
        self.assertEqual(memory[0]['state'], 'invalid')

    def test_full_oracle_replay_measures_all_trajectories_and_never_exports_private_data(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle_api):
            replay.advance(self.db, identifier)
            self.process = 'controller-two:2'
            replay.advance(self.db, identifier)
            for _ in range(47):
                self.clear_delays()
                result = replay.advance(self.db, identifier)
        self.assertTrue(result['finished'])
        self.assertEqual(result['cost']['reserved_calls'], 48)
        self.assertEqual(Decimal(result['cost']['reserved_usd']), Decimal('7.2'))
        self.assertEqual(sum(c[0] == 'POST' for c in self.http_calls), 48)
        self.assertEqual(sum(c[0] == 'GET' for c in self.http_calls), 1)
        self.assertTrue(all(chain['passed'] for c in result['conditions'] for chain in c['trajectory_results']))
        for step in result['steps']:
            self.assertEqual(step['prior_views_count'], step['step'] if step['policy'] == 'full_history' else min(1, step['step']))
        self.assertEqual(result['gates']['blocked_or_duplicate'], 9)
        self.assertEqual(result['gates']['executed_per_path_counts'],
                         {'admitted': 48, 'duplicate': 12, 'future': 12, 'unapproved': 12})
        self.assertEqual(result['gates']['paid_requests_for_blocked_events'], 0)
        for hidden in ('PRIVATE_PROVIDER_METADATA', 'synthetic-fingerprint', 'request_json', 'resp_', 'task_key'):
            self.assertNotIn(hidden, p.encoded(result))
        destination = Path(self.temporary.name) / 'trajectory-replay.json'
        replay.export(self.db, identifier, destination)
        self.assertTrue(json.loads(destination.read_text())['synthetic'])
        for forbidden in ('investigations.json', 'portfolio.json', 'snapshot.json'):
            with self.assertRaises(ValueError):
                replay.export(self.db, identifier, destination.with_name(forbidden))

    def test_public_observations_do_not_export_arbitrary_provider_strings(self):
        case = self.fixture['trajectories'][0]
        value = self.expected_answer(case, 0)
        value['cash_proxy']['unit'] = 'PRIVATE_PROVIDER_UNIT'
        value['cash_proxy']['period'] = 'PRIVATE_PERIOD'
        value['cash_proxy']['evidence_ids'] = ['PRIVATE_PROVIDER_CITATION']
        public = replay._public_answer(value, {event['document']['id'] for event in case['events']})
        self.assertNotIn('PRIVATE', p.encoded(public))
        self.assertEqual(public['cash_proxy']['unit'], 'unrecognized')
        self.assertEqual(public['cash_proxy']['evidence_ids'], ['unrecognized-evidence'])

    def test_deadline_stops_submission_and_reports_unfinished_work(self):
        identifier = self.create()
        with patch.object(replay.time, 'time', return_value=self.now + 3601), patch.object(p, 'api') as api:
            result = replay.advance(self.db, identifier)
            api.assert_not_called()
        self.assertTrue(result['deadline_reached'])
        self.assertFalse(result['finished'])
        self.assertEqual(result['cost']['reserved_calls'], 0)


if __name__ == '__main__':
    unittest.main()
