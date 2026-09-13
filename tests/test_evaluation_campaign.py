"""Campaign persistence, spending boundaries, and public reporting without APIs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from contextvars import ContextVar
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import evaluation_campaign as campaigns
import portfolio as p
import research_eval as evaluation


FLASH = 'deepseek-ai/DeepSeek-V4-Flash-0731'
KIMI = 'moonshotai/Kimi-K3'


class EvaluationCampaignTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'portfolio.sqlite'
        self.now = campaigns._timestamp('2026-09-12T22:00:00Z')
        for target, name, value in ((campaigns.time, 'time', self.now),
                                     (p, 'credential_fingerprint', 'test-key-fingerprint')):
            mock = patch.object(target, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        budget = patch.object(p, 'BUDGET_CENTS', 10000)
        budget.start()
        self.addCleanup(budget.stop)
        self.db = campaigns.initialize(p.database(self.path))
        self.addCleanup(self.db.close)
        self.cases = evaluation.load_cases()
        self.packet = p.load_packet()

    def create(self, cases=None, **options):
        return campaigns.create(self.db, options.pop('models', [FLASH]),
                                repeats=options.pop('repeats', 1),
                                cases=cases if cases is not None else self.cases[:1],
                                deadline=self.now + 3600, **options)

    def answer(self, case):
        return {'verdict': case['expected']['verdict'],
                'evidence_ids': sorted({group[0] for group in case['expected']['required_evidence_groups']}),
                'reason': 'PRIVATE_MODEL_REASON'}

    def case_for(self, body):
        data = json.loads(body['input'][1]['content'])
        return next(case for case in self.cases if (case['claim'], case['as_of']) ==
                    (data['claim'], data['as_of']))

    def response(self, run_id, answer=None, status='completed'):
        return {'id': 'resp_' + run_id.replace('-', '_'), 'status': status,
                'output': [{'type': 'message', 'content': [{'type': 'output_text',
                            'text': json.dumps(answer if answer is not None else self.answer(self.cases[0]))}]}],
                'usage': {'input_tokens': 100, 'output_tokens': 50,
                          'input_tokens_details': {'cached_tokens': 20}},
                'private_metadata': 'PRIVATE_PROVIDER_METADATA'}

    def oracle_api(self, method, route, body=None, run_id=None, **options):
        self.assertEqual(method, 'POST')
        self.assertEqual(route, '/v1/responses')
        return self.response(run_id, self.answer(self.case_for(body)))

    def clear_delay(self):
        with self.db:
            self.db.execute('UPDATE evaluation_items SET next_attempt=0')

    def test_create_freezes_cases_prompts_and_models_without_paid_or_budget_actions(self):
        original = copy.deepcopy(self.cases[:2])
        with patch.object(p, 'api') as api, patch.object(p, 'reserve_task') as reserve:
            identifier = self.create(original, models=[FLASH, p.MODEL], repeats=2)
            api.assert_not_called()
            reserve.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(p.budget_limit(self.db), 10000)
        original[0]['claim'] = 'Changed after creation'
        campaign = campaigns._campaign(self.db, identifier)
        self.assertNotEqual(campaign['cases'][0]['claim'], original[0]['claim'])
        self.assertEqual(p.digest(campaign['cases']), campaign['cases_sha256'])
        self.assertEqual(p.digest(campaign['prompts']), campaign['prompts_sha256'])
        for model in [FLASH, p.MODEL]:
            for case in campaign['cases']:
                request = campaign['prompts']['baseline'][model][case['id']]
                data = json.loads(request['input'][1]['content'])
                self.assertEqual(set(data), {'claim', 'as_of', 'evidence'})
                self.assertNotIn(case['expected']['rationale'], p.encoded(request))
                p.validate_task_envelope(request)
        result = campaigns.status(self.db, identifier)
        self.assertEqual(result['planned_calls'], 8)
        self.assertEqual(sum(item['metrics']['cases'] for item in result['conditions']), 8)
        self.assertTrue(all(item['metrics']['pass_rate'] == 0 for item in result['conditions']))

    def test_frozen_prompt_is_used_even_if_current_builder_changes(self):
        identifier = self.create()
        frozen = self.db.execute('SELECT request_json FROM evaluation_items').fetchone()[0]
        with patch.object(evaluation, 'SYSTEM_PROMPT', 'CHANGED_PROMPT'), \
                patch.object(p, 'api', side_effect=self.oracle_api) as api:
            result = campaigns.advance(self.db, identifier)
        self.assertEqual(p.encoded(api.call_args.args[2]), frozen)
        self.assertTrue(result['finished'])
        self.assertEqual(result['conditions'][0]['metrics']['pass_rate'], 1)

    def test_shared_budget_includes_other_research_and_is_never_increased(self):
        p.set_budget_limit(self.db, p.TASK_PROFILES[FLASH]['reserve_cents'])
        p.reserve_task(self.db, p.build_task_request(FLASH, 'Existing research'), self.packet,
                       'existing-investigation', 'investigate')
        identifier = self.create()
        with patch.object(p, 'api') as api:
            result = campaigns.advance(self.db, identifier)
            api.assert_not_called()
        self.assertFalse(result['finished'])
        self.assertEqual(result['cost']['reserved_calls'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(p.budget_limit(self.db), p.TASK_PROFILES[FLASH]['reserve_cents'])
        self.assertEqual(list(self.directory.glob('*.sqlite')), [self.path])

    def test_uncertain_submission_resumes_same_request_and_id(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=RuntimeError('PRIVATE_EXCEPTION')) as first:
            result = campaigns.advance(self.db, identifier)
        self.assertEqual(result['states'], {'unknown': 1})
        self.assertEqual(result['cost']['unknown_cost_runs'], 1)
        self.assertGreater(Decimal(result['cost']['reserved_usd']), 0)
        self.clear_delay()
        with patch.object(p, 'api', side_effect=self.oracle_api) as second:
            result = campaigns.advance(self.db, identifier)
        self.assertEqual(first.call_args, second.call_args)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(result['cost']['execution_attempts'], 2)
        self.assertEqual(result['cost']['reserved_calls'], 1)
        self.assertTrue(result['finished'])
        self.assertNotIn('PRIVATE_EXCEPTION', p.encoded(result))

    def test_resume_repairs_crash_between_reservation_and_item_link(self):
        identifier = self.create()
        item = self.db.execute('SELECT * FROM evaluation_items').fetchone()
        run_id = p.reserve_task(self.db, json.loads(item['request_json']), self.packet,
                                item['task_key'], 'evaluation')
        self.assertIsNone(self.db.execute('SELECT run_id FROM evaluation_items').fetchone()[0])
        with patch.object(p, 'api', side_effect=self.oracle_api) as api:
            result = campaigns.advance(self.db, identifier)
        self.assertEqual(api.call_args.args[3], run_id)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT run_id FROM evaluation_items').fetchone()[0], run_id)
        self.assertTrue(result['finished'])

    def test_completed_ledger_response_is_graded_after_crash_without_another_call(self):
        identifier = self.create()
        item = self.db.execute('SELECT * FROM evaluation_items').fetchone()
        run_id = p.reserve_task(self.db, json.loads(item['request_json']), self.packet,
                                item['task_key'], 'evaluation')
        response = self.response(run_id)
        with self.db:
            self.db.execute('UPDATE runs SET response_id=?,response=? WHERE id=?',
                            (response['id'], p.encoded(response), run_id))
        with patch.object(p, 'api') as api:
            result = campaigns.advance(self.db, identifier)
            api.assert_not_called()
        self.assertTrue(result['finished'])
        self.assertEqual(result['conditions'][0]['metrics']['passed'], 1)

    def test_invalid_completed_answer_is_final_and_never_redrafted(self):
        identifier = self.create()
        def invalid(method, route, body=None, run_id=None, **options):
            return self.response(run_id, {**self.answer(self.cases[0]), 'extra': 'PRIVATE_EXTRA'})
        with patch.object(p, 'api', side_effect=invalid) as api:
            result = campaigns.advance(self.db, identifier)
            self.clear_delay()
            campaigns.advance(self.db, identifier)
            self.assertEqual(api.call_count, 1)
        self.assertTrue(result['finished'])
        self.assertEqual(result['states'], {'invalid': 1})
        self.assertEqual(result['conditions'][0]['metrics']['passed'], 0)
        self.assertEqual(result['cost']['unknown_cost_runs'], 0)
        self.assertGreater(Decimal(result['cost']['estimated_known_usd']), 0)

    def test_known_background_response_is_retrieved_without_new_post(self):
        identifier = self.create(models=[p.MODEL])
        item = self.db.execute('SELECT * FROM evaluation_items').fetchone()
        run_id = p.reserve_task(self.db, json.loads(item['request_json']), self.packet,
                                item['task_key'], 'evaluation')
        with self.db:
            self.db.execute('UPDATE runs SET response_id=?,response=?,key_fingerprint=? WHERE id=?',
                            ('resp_existing', p.encoded({'id': 'resp_existing', 'status': 'queued'}),
                             'test-key-fingerprint', run_id))
        response = self.response(run_id)
        response['id'] = 'resp_existing'
        with patch.object(p, 'api', return_value=response) as api:
            result = campaigns.advance(self.db, identifier)
        api.assert_called_once_with('GET', '/v1/responses/resp_existing',
                                    expected_key_fingerprint='test-key-fingerprint')
        self.assertTrue(result['finished'])
        self.assertEqual(self.db.execute('SELECT operation FROM evaluation_attempts').fetchone()[0], 'retrieve')

    def test_uniform_critic_sees_same_evidence_and_both_right_and_wrong_initial_answers(self):
        identifier = self.create(self.cases[:2], critic_model=KIMI)
        seen = []
        def provider(method, route, body=None, run_id=None, **options):
            case = self.case_for(body)
            answer = self.answer(case)
            if body['model'] == FLASH and case['id'] == self.cases[0]['id']:
                answer['verdict'] = 'unsupported'
            if body['model'] == KIMI:
                data = json.loads(body['input'][1]['content'])
                initial = json.loads(body['input'][-1]['content'])
                self.assertEqual(data, {key: case[key] for key in ('claim', 'as_of', 'evidence')})
                self.assertEqual(set(initial), {'initial_verdict'})
                self.assertNotIn(case['expected']['rationale'], p.encoded(body))
                seen.append(initial['initial_verdict']['verdict'])
            return self.response(run_id, answer)
        with patch.object(p, 'api', side_effect=provider) as api:
            campaigns.advance(self.db, identifier)
            result = campaigns.advance(self.db, identifier)
            self.assertEqual(api.call_count, 4)
        self.assertCountEqual(seen, ['supported', 'unsupported'])
        self.assertTrue(result['finished'])
        comparison = result['comparisons'][0]
        self.assertEqual(comparison['scheduled_pairs'], 2)
        self.assertEqual(comparison['finalized_pairs'], 2)
        self.assertEqual(comparison['before']['label_correct_rate'], 0.5)
        self.assertEqual(comparison['after']['label_correct_rate'], 1)
        self.assertEqual(comparison['extra_cost']['reserved_calls'], 2)
        self.assertGreater(Decimal(comparison['extra_cost']['estimated_known_usd']), 0)

    def test_critic_still_runs_uniformly_when_initial_output_is_invalid(self):
        identifier = self.create(critic_model=KIMI)
        def provider(method, route, body=None, run_id=None, **options):
            if body['model'] == FLASH:
                return self.response(run_id, {'unusable': True})
            self.assertEqual(json.loads(body['input'][-1]['content']), {'initial_verdict': None})
            return self.response(run_id)
        with patch.object(p, 'api', side_effect=provider) as api:
            campaigns.advance(self.db, identifier)
            result = campaigns.advance(self.db, identifier)
            self.assertEqual(api.call_count, 2)
        self.assertTrue(result['finished'])
        self.assertEqual(result['comparisons'][0]['before']['passed'], 0)
        self.assertEqual(result['comparisons'][0]['after']['passed'], 1)

    def test_global_call_admission_cap_is_atomic_across_campaigns(self):
        with patch.object(campaigns, 'MAX_CALLS', 2):
            identifiers = [self.create(self.cases[:2], max_calls=2) for _ in range(2)]
            def advance(identifier):
                with closing(p.database(self.path)) as db:
                    return campaigns.advance(db, identifier, workers=2)
            with patch.object(p, 'api', side_effect=self.oracle_api) as api:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(advance, identifiers))
                self.assertEqual(api.call_count, 2)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 2)
            self.assertEqual(self.db.execute('SELECT SUM(admitted) FROM evaluation_items').fetchone()[0], 2)
            self.assertEqual(sum(result['cost']['reserved_calls'] for result in results), 2)

    def test_overlapping_advances_do_not_execute_one_item_twice(self):
        identifier = self.create()
        started = threading.Event()
        release = threading.Event()
        def provider(*args, **options):
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return self.oracle_api(*args, **options)
        def first_advance():
            with closing(p.database(self.path)) as db:
                return campaigns.advance(db, identifier)
        with patch.object(p, 'api', side_effect=provider) as api:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(first_advance)
                try:
                    self.assertTrue(started.wait(timeout=5))
                    campaigns.advance(self.db, identifier)
                    self.assertEqual(api.call_count, 1)
                finally:
                    release.set()
                self.assertTrue(future.result()['finished'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_deadline_prevents_calls_and_reservations(self):
        identifier = self.create()
        with patch.object(campaigns.time, 'time', return_value=self.now + 3601), patch.object(p, 'api') as api:
            result = campaigns.advance(self.db, identifier)
            api.assert_not_called()
        self.assertTrue(result['deadline_reached'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        with self.assertRaises(ValueError):
            campaigns.create(self.db, [FLASH], deadline='2026-09-14T00:00:00Z')

    def test_planned_critic_calls_count_toward_the_cap(self):
        with self.assertRaises(ValueError):
            self.create(self.cases, models=[FLASH, p.MODEL, KIMI], repeats=2, critic_model=KIMI)
        with self.assertRaises(ValueError):
            self.create(max_calls=129)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM evaluation_campaigns').fetchone()[0], 0)

    def test_cost_includes_failed_and_unknown_runs_and_export_uses_whitelist(self):
        identifier = self.create(self.cases[:3])
        def provider(method, route, body=None, run_id=None, **options):
            case = self.case_for(body)
            if case['id'] == self.cases[2]['id']:
                raise RuntimeError('PRIVATE_PROVIDER_EXCEPTION')
            return self.response(run_id, self.answer(case),
                                 status='failed' if case['id'] == self.cases[1]['id'] else 'completed')
        with patch.object(p, 'api', side_effect=provider):
            result = campaigns.advance(self.db, identifier)
        cost = result['cost']
        self.assertEqual(cost['reserved_calls'], 3)
        self.assertEqual(cost['unknown_cost_runs'], 1)
        self.assertFalse(cost['cost_complete'])
        self.assertEqual(cost['usage'], {'input_tokens': 200, 'cached_tokens': 40, 'output_tokens': 100})
        self.assertGreater(Decimal(cost['estimated_known_usd']), 0)
        self.assertEqual(Decimal(cost['reserved_usd']),
                         Decimal(p.TASK_PROFILES[FLASH]['reserve_cents'] * 3) / 100)
        with patch.object(p, 'api') as api:
            payload = campaigns.export(self.db, identifier, self.directory / 'public.json')
            api.assert_not_called()
        text = p.encoded(payload)
        for marker in ('PRIVATE_', 'run_id', 'response_id', 'request_json', 'packet_json',
                       'task_key', 'key_fingerprint', 'required_evidence_groups', 'validation_error'):
            self.assertNotIn(marker, text)
        for row in self.db.execute('SELECT id,response_id FROM runs'):
            self.assertNotIn(row['id'], text)
            if row['response_id']:
                self.assertNotIn(row['response_id'], text)
        self.assertEqual(json.loads((self.directory / 'public.json').read_text()), payload)
        self.assertEqual(payload['conditions'][0]['metrics']['cases'], 3)

    def test_frozen_integrity_failure_stops_execution(self):
        identifier = self.create()
        with self.db:
            self.db.execute('UPDATE evaluation_campaigns SET cases_json=? WHERE id=?', ('[]', identifier))
        with patch.object(p, 'api') as api:
            with self.assertRaises(ValueError):
                campaigns.advance(self.db, identifier)
            api.assert_not_called()

    def test_reconciliation_does_not_rewrite_unchanged_terminal_or_waiting_items(self):
        identifier = self.create(self.cases[:2])
        def provider(method, route, body=None, run_id=None, **options):
            case = self.case_for(body)
            return self.response(run_id, self.answer(case),
                                 status='queued' if case['id'] == self.cases[0]['id'] else 'completed')
        with patch.object(p, 'api', side_effect=provider):
            campaigns.advance(self.db, identifier)
        before = self.db.total_changes
        with patch.object(p, 'api') as api:
            campaigns.reconcile(self.db, identifier)
            campaigns.reconcile(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual({row['state'] for row in self.db.execute('SELECT state FROM evaluation_items')},
                         {'waiting', 'completed'})

    def test_worker_threads_receive_the_callers_tracking_context(self):
        identifier = self.create(self.cases[:2])
        marker = ContextVar('test_evaluation_tracking', default=None)
        token = marker.set('safe-trace-marker')
        seen = []
        def provider(*args, **options):
            seen.append(marker.get())
            return self.oracle_api(*args, **options)
        try:
            with patch.object(p, 'api', side_effect=provider), \
                    patch.object(campaigns.tracking, 'event') as event:
                result = campaigns.advance(self.db, identifier, workers=2)
            self.assertTrue(result['finished'])
            self.assertEqual(seen, ['safe-trace-marker', 'safe-trace-marker'])
            self.assertEqual(event.call_count, 2)
            for call in event.call_args_list:
                self.assertEqual(set(call.args[1]), {'model', 'stage', 'status', 'passed'})
        finally:
            marker.reset(token)

    def test_combined_export_keeps_campaign_conditions_distinct_without_double_counting(self):
        first = self.create()
        second = self.create(critic_model=KIMI)
        with patch.object(p, 'api', side_effect=self.oracle_api):
            campaigns.advance(self.db, first)
            campaigns.advance(self.db, second)
            campaigns.advance(self.db, second)
        with patch.object(p, 'api') as api:
            result = campaigns.export_combined(self.db, [first, second], self.directory / 'combined.json')
            api.assert_not_called()
        self.assertEqual(len(result['campaigns']), 2)
        self.assertEqual(len(result['campaigns'][0]['comparisons']), 0)
        self.assertEqual(len(result['campaigns'][1]['comparisons']), 1)
        self.assertEqual(result['cost']['reserved_calls'], 3)
        self.assertEqual(result['cost']['usage']['input_tokens'], 300)
        self.assertNotIn('PRIVATE_', p.encoded(result))
        with self.assertRaises(ValueError):
            campaigns.export_combined(self.db, [first, first], self.directory / 'duplicate.json')


if __name__ == '__main__':
    unittest.main()
