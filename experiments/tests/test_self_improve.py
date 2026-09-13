"""Offline controller and synthetic gate tests. Oracle answers never hit a provider."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import portfolio as p
import research_eval as evaluation
import self_improve as s


class SelfImproveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'ledger.sqlite'
        self.db = p.database(self.path)
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 700)
        self.suites = s.load_suites()
        self.cases = {case['claim']: case for rows in self.suites.values() for case in rows}
        self.calls = []
        self.candidate = evaluation.SYSTEM_PROMPT + '\nBefore deciding, verify every scope and citation.'
        self.deadline = p.iso(time.time() + 3600)
        for target, replacement in [('credential_fingerprint', '1' * 64), ('preflight_task', None)]:
            mock = patch.object(p, target, return_value=replacement)
            mock.start(); self.addCleanup(mock.stop)

    def start(self, key='test-cycle', candidate=None):
        return s.start(self.db, key, self.deadline, candidate_prompt=candidate)

    def answer(self, case):
        return {'verdict': case['expected']['verdict'],
                'evidence_ids': sorted({group[0] for group in case['expected']['required_evidence_groups']}),
                'reason': 'Synthetic oracle used only for offline controller tests.'}

    def api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, body, request_id))
        if method == 'GET':
            run = self.db.execute('SELECT * FROM runs WHERE response_id=?', (route.split('/')[-1],)).fetchone()
            body = json.loads(run['request']); request_id = run['id']
        data = json.loads(body['input'][1]['content'])
        if 'development_cases' in data:
            value = {'prompt': self.candidate}
        else:
            case = self.cases[data['claim']]
            value = self.answer(case)
            if body['input'][0]['content'] == evaluation.SYSTEM_PROMPT and case['id'] in {'dev-cash-remainder', 'val-rounded-reconciliation'}:
                value['verdict'] = 'insufficient'; value['evidence_ids'] = []
        return {'id': 'resp_' + request_id, 'status': 'completed', 'model': body['model'],
                'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(value)}]}],
                'usage': {'input_tokens': 1000, 'output_tokens': 100, 'input_tokens_details': {'cached_tokens': 0}}}

    def finish(self, identifier):
        with patch.object(p, 'api', side_effect=self.api):
            for _ in range(80):
                result = s.advance(self.db, identifier)
                if result['state'] != 'running':
                    return result
        self.fail('Offline cycle did not finish')

    def test_suites_are_new_separate_balanced_and_all_authored_answers_pass(self):
        old = {s._fingerprint(c) for c in evaluation.load_cases()}
        all_cases = [c for rows in self.suites.values() for c in rows]
        self.assertEqual(len(all_cases), 16)
        self.assertFalse(old & {s._fingerprint(c) for c in all_cases})
        for rows in self.suites.values():
            self.assertEqual([sum(c['expected']['verdict'] == verdict for c in rows) for verdict in evaluation.VERDICTS], [3, 3, 2])
            self.assertTrue(all(evaluation.grade(self.answer(c), c)['passed'] for c in rows))
        self.assertFalse({e['text'] for c in self.suites['development'] for e in c['evidence']} &
                         {e['text'] for c in self.suites['validation'] for e in c['evidence']})

    def test_start_freezes_current_reasonable_baseline_and_inputs_without_network_or_reservations(self):
        with patch.object(p, 'api') as api:
            identifier = self.start()
            self.assertEqual(self.start(), identifier)
            api.assert_not_called()
        protocol = s._cycle(self.db, identifier)
        self.assertEqual(protocol['baseline']['prompt'], evaluation.SYSTEM_PROMPT)
        self.assertEqual(protocol['max_calls'], 33)
        self.assertEqual(protocol['max_cents'], 330)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.start(candidate=self.candidate)
        with self.assertRaises(ValueError):
            self.start(key='validation-reuse')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE improvement_cycles SET protocol_json=? WHERE id=?', ('{}', identifier))
        self.db.rollback()

    def test_generation_has_development_feedback_but_never_validation_data(self):
        identifier = self.start()
        with patch.object(p, 'api', side_effect=self.api):
            for _ in range(9):
                s.advance(self.db, identifier)
        request = json.loads(self.db.execute("SELECT request_json FROM improvement_requests WHERE stage='proposal'").fetchone()[0])
        content = request['input'][1]['content']
        decoded = json.loads(content)
        self.assertEqual(len(decoded['development_grades']), 8)
        self.assertEqual(decoded['development_cases'], self.suites['development'])
        for case in self.suites['validation']:
            self.assertNotIn(case['claim'], content)
            self.assertNotIn(case['expected']['rationale'], content)
        self.assertEqual(s._candidate(self.db, identifier), self.candidate)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM improvement_requests WHERE split='validation'").fetchone()[0], 0)

    def test_proposal_accepts_only_one_strict_optional_json_envelope(self):
        payload = json.dumps({'prompt': self.candidate})
        for text in (payload, '```json\n' + payload + '\n```', '```\r\n' + payload + '\r\n```'):
            self.assertEqual(s._proposal(text), self.candidate)
        for text in ('{"prompt":"one","prompt":"two"}', '{"prompt":NaN}', '[]',
                     '{"prompt":"ok","other":1}', payload + '\n{}', 'Here: ' + payload,
                     '```json\n' + payload + '\n```\nTrailing',
                     '```json\n' + payload + '\n```\n```json\n{}\n```'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                s._proposal(text)

    def test_fenced_proposal_is_frozen_without_redraft_or_new_allowance(self):
        identifier = self.start()
        def fenced(*args, **kwargs):
            response = self.api(*args, **kwargs)
            content = response['output'][0]['content'][0]
            if json.loads(content['text']).get('prompt'):
                content['text'] = '```json\n' + content['text'] + '\n```'
            return response
        with patch.object(p, 'api', side_effect=fenced):
            for _ in range(9):
                s.advance(self.db, identifier)
        self.assertEqual(s._candidate(self.db, identifier), self.candidate)
        self.assertEqual(s.status(self.db, identifier)['costs']['calls'], 9)
        self.assertEqual(s.status(self.db, identifier)['costs']['reserved_cents'], 90)

    def test_autonomous_cycle_promotes_only_complete_pairwise_gain_and_retains_history(self):
        identifier = self.start()
        result = self.finish(identifier)
        self.assertEqual(result['state'], 'promoted')
        self.assertEqual(result['finalized_evaluations'], 32)
        self.assertEqual(result['finalized_proposals'], 1)
        self.assertEqual(result['costs']['calls'], 33)
        self.assertEqual(result['costs']['reserved_cents'], 330)
        self.assertEqual(s.champion(self.db)['prompt'], self.candidate)
        self.assertEqual(result['decision']['rule']['splits']['validation']['gains'], ['val-rounded-reconciliation'])
        event_before = self.db.execute('SELECT COUNT(*) FROM improvement_events').fetchone()[0]
        with patch.object(p, 'api') as api:
            advanced = s.advance(self.db, identifier)
            recorded = s.status(self.db, identifier)
            self.assertEqual({k: v for k, v in advanced.items() if k != 'recorded_at'},
                             {k: v for k, v in recorded.items() if k != 'recorded_at'})
            api.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM improvement_events').fetchone()[0], event_before)
        calls_before = result['costs']
        restored = s.rollback(self.db, 1, 'Offline rollback demonstration')
        self.assertEqual(restored['prompt'], evaluation.SYSTEM_PROMPT)
        self.assertEqual(s.status(self.db, identifier)['costs'], calls_before)
        self.assertEqual(s.status(self.db, identifier)['decision']['decision'], 'promoted')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM improvement_events WHERE kind='rollback'").fetchone()[0], 1)

    def test_paired_model_requests_withhold_answers_and_counterbalance_validation_order(self):
        identifier = self.start(candidate=self.candidate)
        self.finish(identifier)
        items = self.db.execute('SELECT * FROM improvement_requests ORDER BY ordinal').fetchall()
        self.assertEqual(len(items), 32)
        first_arms = []
        for index, case in enumerate(self.suites['validation']):
            pair = [row for row in items if row['case_id'] == case['id']]
            first_arms.append(pair[0]['arm'])
            for item in pair:
                body = json.loads(item['request_json'])
                user = json.loads(body['input'][1]['content'])
                self.assertEqual(set(user), {'claim', 'as_of', 'evidence'})
                self.assertNotIn(case['expected']['rationale'], body['input'][1]['content'])
                self.assertEqual(body['model'], s.DEFAULT_MODEL)
        self.assertEqual(first_arms, ['baseline', 'candidate'] * 4)

    def test_rule_rejects_regression_no_gain_and_missing_pairs(self):
        scores = {split: {str(i): {'baseline': i != 0, 'candidate': True} for i in range(8)} for split in ('development', 'validation')}
        self.assertTrue(s.promotion_rule(scores)['eligible'])
        scores['validation']['1']['candidate'] = False
        self.assertFalse(s.promotion_rule(scores)['eligible'])
        scores['validation']['1']['candidate'] = True
        scores['validation']['0']['baseline'] = True
        self.assertFalse(s.promotion_rule(scores)['eligible'])
        del scores['validation']['7']
        self.assertEqual(s.promotion_rule(scores)['reason'], 'incomplete_pairs')

    def test_accepted_response_recovers_original_id_after_restart_and_code_drift(self):
        identifier = self.start()
        def accepted(method, route, body, request_id, **kwargs):
            return {'id': 'resp_' + request_id, 'status': 'in_progress', 'model': body['model']}
        with patch.object(p, 'api', side_effect=accepted):
            s.advance(self.db, identifier)
        row = self.db.execute('SELECT * FROM runs').fetchone()
        self.db.close(); self.db = p.database(self.path); self.addCleanup(self.db.close)
        with patch.object(s, '_code_hash', return_value='changed'), patch.object(p, 'api', side_effect=self.api):
            s.advance(self.db, identifier)
        self.assertEqual(self.calls[-1][0:2], ('GET', '/v1/responses/' + row['response_id']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT reserved_cents FROM runs').fetchone()[0], 10)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM improvement_observations').fetchone()[0], 0)
        self.assertEqual(json.loads(p.get_run(self.db, row['id'])['response'])['status'], 'completed')
        self.assertIsNone(s.status(self.db, identifier)['decision'])
        s._observe(self.db, identifier, s._cycle(self.db, identifier))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM improvement_observations').fetchone()[0], 1)

    def test_reservation_orphan_is_reused_without_second_hold(self):
        identifier = self.start()
        with patch.object(p, 'execute', side_effect=RuntimeError('crash after reservation')):
            with self.assertRaises(RuntimeError): s.advance(self.db, identifier)
        before = self.db.execute('SELECT id,request FROM runs').fetchone()
        with patch.object(p, 'api', side_effect=self.api): s.advance(self.db, identifier)
        after = self.db.execute('SELECT id,request FROM runs').fetchall()
        self.assertEqual(len(after), 1); self.assertEqual(tuple(after[0]), tuple(before))
        self.assertEqual(self.calls[0][3], before['id'])

    def test_deadline_and_shared_budget_stop_new_admissions_but_accepted_get_can_finish(self):
        identifier = self.start()
        with patch.object(s.time, 'time', return_value=s._time(self.deadline) + 1), patch.object(p, 'api') as api:
            result = s.advance(self.db, identifier); api.assert_not_called()
        self.assertEqual(result['state'], 'deadline'); self.assertEqual(result['costs']['calls'], 0)

    def test_budget_capacity_no_overspend(self):
        identifier = self.start()
        p.set_budget_limit(self.db, 5)
        with patch.object(p, 'api') as api, self.assertRaises(ValueError):
            s.advance(self.db, identifier)
        api.assert_not_called(); self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_controller_lock_and_frozen_request_identity(self):
        identifier = self.start()
        with s.lock(self.db), self.assertRaises(ValueError): s.advance(self.db, identifier)
        with patch.object(p, 'execute', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError): s.advance(self.db, identifier)
        with self.db:
            self.db.execute('UPDATE runs SET purpose=?', ('critique',))
        with patch.object(p, 'api') as api, self.assertRaises(ValueError): s.advance(self.db, identifier)
        api.assert_not_called()

    def test_invalid_candidate_ends_without_replacement_or_validation_calls(self):
        identifier = self.start()
        normal = self.api
        def invalid(method, route, body=None, request_id=None, **kwargs):
            result = normal(method, route, body, request_id, **kwargs)
            if 'development_cases' in json.loads(body['input'][1]['content']):
                result['output'][0]['content'][0]['text'] = '{"prompt":"bad","extra":"field"}'
            return result
        with patch.object(p, 'api', side_effect=invalid):
            for _ in range(9): result = s.advance(self.db, identifier)
        self.assertEqual(result['state'], 'invalid_candidate'); self.assertEqual(result['costs']['calls'], 9)
        with patch.object(p, 'api') as api: s.advance(self.db, identifier); api.assert_not_called()
        self.assertIsNone(s._candidate(self.db, identifier))

    def test_completed_receipt_observation_and_prompt_are_immutable(self):
        identifier = self.start(); self.finish(identifier)
        for table, column in [('decisions', 'receipt_json'), ('observations', 'grade_json'), ('prompts', 'text'), ('requests', 'request_json')]:
            with self.assertRaises(sqlite3.IntegrityError): self.db.execute(f'UPDATE improvement_{table} SET {column}=?', ('changed',))
            self.db.rollback()
        with self.db: self.db.execute('UPDATE improvement_head SET event_id=1')
        with self.assertRaises(ValueError): s.champion(self.db)

    def test_partially_reused_validation_is_consumed_even_with_renamed_ids(self):
        self.start()
        changed = deepcopy(self.suites['validation'])
        for row in changed:
            row['id'] = 'renamed-' + row['id']
        changed[-1]['claim'] = 'A genuinely changed final claim; seven other cases remain consumed.'
        path = Path(self.temp.name) / 'changed-validation.json'
        path.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            s.start(self.db, 'attempt-reuse-seven', self.deadline, validation=path)

    def test_unknown_identity_or_excessive_final_usage_cannot_promote(self):
        identifier = self.start(candidate=self.candidate)
        normal = self.api
        def expensive(method, route, body=None, request_id=None, **kwargs):
            result = normal(method, route, body, request_id, **kwargs)
            if len(self.calls) == 32:
                result['usage']['output_tokens'] = 1000000
            return result
        with patch.object(p, 'api', side_effect=expensive):
            for _ in range(32): result = s.advance(self.db, identifier)
        self.assertEqual(result['state'], 'rejected')
        self.assertEqual(result['decision']['reason'], 'allowance_mismatch')
        self.assertEqual(result['costs']['over_allowance_requests'], 1)
        self.assertEqual(s.champion(self.db)['prompt'], evaluation.SYSTEM_PROMPT)

    def test_unknown_usage_blocks_an_otherwise_passing_candidate(self):
        identifier = self.start(candidate=self.candidate)
        normal = self.api
        def unknown(method, route, body=None, request_id=None, **kwargs):
            result = normal(method, route, body, request_id, **kwargs)
            if len(self.calls) == 32: result.pop('usage')
            return result
        with patch.object(p, 'api', side_effect=unknown):
            for _ in range(32): result = s.advance(self.db, identifier)
        self.assertTrue(result['decision']['rule']['eligible'])
        self.assertEqual(result['state'], 'rejected')
        self.assertEqual(result['decision']['reason'], 'unconfirmed_usage')

    def test_four_inflight_limit_and_deadline_retrieval_preserve_original_ids(self):
        identifier = self.start()
        operations = []
        def queued(method, route, body=None, request_id=None, **kwargs):
            operations.append((method,route))
            if method == 'GET':
                return {'id':route.split('/')[-1], 'status':'in_progress','model':s.DEFAULT_MODEL}
            return {'id':'resp_'+request_id,'status':'in_progress','model':body['model']}
        with patch.object(p,'api',side_effect=queued):
            for _ in range(5): s.advance(self.db,identifier)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],4)
        self.assertEqual([item[0] for item in operations],['POST']*4+['GET'])
        with patch.object(s.time,'time',return_value=s._time(self.deadline)+1),patch.object(p,'api',side_effect=queued):
            s.advance(self.db,identifier)
        self.assertEqual(operations[-1][0],'GET')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],4)

    def test_champion_consumer_is_claim_critic_only_and_never_spends(self):
        self.start()
        case=self.suites['development'][0]
        with patch.object(p,'api') as api:
            request=s.build_current_claim_request(self.db,case['claim'],case['as_of'],case['evidence'])
            api.assert_not_called()
        self.assertEqual(request['contract'],'evidence_critic_verdict_v1')
        self.assertEqual(request['request']['input'][0]['content'],evaluation.SYSTEM_PROMPT)
        self.assertEqual(set(json.loads(request['request']['input'][1]['content'])),{'claim','as_of','evidence'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
