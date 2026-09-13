"""No real API requests: assignment recovery, spending bounds, and manual review."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import portfolio as p
import investigator as inv
import research_queue as queue
import research_sources as sources


class ResearchQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / '.data/portfolio.sqlite'
        self.db = queue.initialize(p.database(self.path))
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 9100)
        self.now = queue.timestamp('2026-09-12T22:00:00Z')
        self.calls, self.revise = [], False
        for obj, name, kwargs in [
            (queue.time, 'time', {'side_effect': lambda: self.now}),
            (p, 'preflight_task', {'return_value': None}),
            (p, 'credential_fingerprint', {'return_value': 'synthetic-fingerprint'}),
            (p, 'api', {'side_effect': self.api}),
            (sources, '_download', {'side_effect': AssertionError('Queue must use frozen local sources')}),
        ]:
            item = patch.object(obj, name, **kwargs); item.start(); self.addCleanup(item.stop)
        store = sources.SourceStore(self.root); store._prepare()
        for identifier in sources.SOURCE_REGISTRY:
            text = 'Synthetic evidence. Lease classification affects reported capital expenditure. ' * 30
            artifact = {**sources.allowed_source(identifier), 'text': text,
                        'fetched_at': '2026-09-12T20:00:00Z', 'sha256': hashlib.sha256(text.encode()).hexdigest()}
            (store.path / (identifier + '.json')).write_text(json.dumps(artifact))

    def enqueue(self, key='test-job', **kwargs):
        params = {'root': self.root, 'packet': p.load_packet(), 'due': self.now, 'deadline': self.now + 1800}
        params.update(kwargs)
        result = queue.enqueue(self.db, key, inv.QUESTION, **params)
        self.investigation_id = result['jobs'][0]['investigation_id']
        return result

    def tick(self):
        self.now += 65
        return queue.advance(self.db)

    def response(self, identifier, output=None, status='completed'):
        return {'id': identifier, 'status': status, 'output': output or [],
                'usage': {'input_tokens': 1000, 'output_tokens': 200, 'input_tokens_details': {'cached_tokens': 0}}}

    def api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, request_id))
        state = inv.get(self.db, self.investigation_id)
        identifier = 'resp_' + (request_id or route.rsplit('/', 1)[-1].removeprefix('resp_'))
        if state['phase'] == 'research' and state['turn'] == 0:
            calls = [('read_source', {'source_id': 'fy26-call', 'query': 'lease'}),
                     ('calculate', {'operation': 'subtract', 'left_id': 'ocf-2026', 'right_id': 'ppe-2026'}),
                     ('save_hypothesis', {'statement': 'Accounting definitions may explain the measure.',
                                          'invalidation': 'A full reconciliation could change this view.'})]
            return self.response(identifier, [{'type': 'function_call', 'call_id': f'call_{n}', 'name': name,
                                              'arguments': json.dumps(args)} for n, (name, args) in enumerate(calls)])
        if state['phase'] in {'critique', 'recheck'}:
            value = {'verdict': 'pass', 'summary': 'The limited view fits the evidence.', 'issues': []}
            if self.revise:
                value = {'verdict': 'revise', 'summary': 'Clarify the scope.', 'issues': [{'claim_index': 0,
                         'severity': 'material', 'reason': 'The measure requires qualification.', 'evidence_ids': ['cash-versus-capex']}]}
        else:
            value = {'headline': 'Definitions matter', 'summary': 'Reported amounts reflect accounting definitions.',
                     'claims': [{'text': 'The measures describe different scopes.', 'evidence_ids': [next(iter(state['passages']))]}],
                     'changes': ['Scope needs qualification.'], 'open_questions': ['Can the measures be reconciled?'],
                     'invalidation': ['A full reconciliation could change the conclusion.'], 'change_assessment': 'qualified'}
        return self.response(identifier, [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(value)}]}])

    def test_enqueue_is_local_freezes_inputs_and_same_key_is_idempotent(self):
        result = self.enqueue()
        self.assertEqual(result['jobs'][0]['maximum_reserved_usd'], '3')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 0)
        again = self.enqueue()
        self.assertEqual(again['jobs'][0]['investigation_id'], self.investigation_id)
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.enqueue(max_turns=3)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE research_queue_jobs SET deadline=deadline+1")
        self.db.rollback()
        self.enqueue('second-job')
        with self.assertRaisesRegex(ValueError, 'two durable'):
            self.enqueue('third-job')
        self.assertEqual(p.budget_limit(self.db), 9100)

    def test_changed_cache_is_not_ingested_and_all_sources_freeze_at_enqueue(self):
        self.enqueue()
        _, data = queue._get(self.db, 'test-job')
        frozen = deepcopy(data['snapshots'])
        for path in (self.root / '.data/research/sources').glob('*.json'):
            path.write_text('Changed after enqueue; never read this as evidence')
        self.tick()
        state = inv.get(self.db, self.investigation_id)
        self.assertEqual(state['snapshots'], frozen)
        self.assertEqual(set(frozen), set(sources.SOURCE_REGISTRY))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(state['passages'])

    def test_crash_between_creation_and_attachment_recovers_exact_investigation(self):
        self.enqueue()
        original = inv.start
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(inv, 'start', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.tick()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 1)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, 'research_queue.py'):
            inv.advance(self.db, self.investigation_id)
        self.tick()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 1)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(queue.status(self.db)['jobs'][0]['initialized'])

    def test_accepted_id_pause_and_fresh_connection_resume_without_resubmission(self):
        self.enqueue()
        with patch.object(p, 'api', side_effect=lambda method, route, body=None, request_id=None, **kwargs:
                          self.response('resp_' + request_id, status='queued')) as api:
            self.tick(); self.assertEqual(api.call_count, 1)
        request = self.db.execute('SELECT id,response_id,request FROM runs').fetchone()
        queue.pause(self.db, 'test-job')
        self.tick(); self.assertEqual(self.calls, [])
        queue.pause(self.db, 'test-job', False)
        self.now += 65
        with closing(p.database(self.path)) as fresh:
            queue.advance(fresh)
        self.assertEqual(self.calls[0], ('GET', '/v1/responses/' + request['response_id'], None))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT request FROM runs').fetchone()[0], request['request'])

    def test_managed_direct_cli_cannot_bypass_pause_and_ordinary_start_is_unchanged(self):
        self.enqueue(); self.tick()
        queue.pause(self.db, 'test-job')
        calls = len(self.calls)
        with self.assertRaisesRegex(ValueError, 'research_queue.py'):
            inv.advance(self.db, self.investigation_id)
        self.assertEqual(len(self.calls), calls)
        ordinary = inv.start(self.db, max_turns=4)
        self.assertNotIn('queue_job_key', inv.get(self.db, ordinary))
        self.assertNotEqual(ordinary, self.investigation_id)
        with self.assertRaisesRegex(ValueError, 'canonical'):
            inv.start(self.db, investigation_id='not-a-uuid')

    def test_complete_and_repair_terminal_states_never_review_or_publish(self):
        self.enqueue()
        for _ in range(3): result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'awaiting_review')
        self.assertEqual(len(self.calls), 3)
        self.tick(); self.assertEqual(len(self.calls), 3)
        self.assertEqual(inv.public_snapshot(self.db)['investigations'], [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigation_reviews').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)

    def test_failed_and_invalid_responses_stop_without_automatic_redraft(self):
        for state in ['failed', 'completed']:
            with self.subTest(state=state):
                key = 'failure-' + state
                self.enqueue(key)
                with patch.object(p, 'api', side_effect=lambda method, route, body=None, request_id=None, **kwargs:
                                  self.response('resp_' + request_id, [], state)):
                    self.tick()
                item = next(job for job in queue.status(self.db)['jobs'] if job['job_key'] == key)
                self.assertEqual(item['state'], 'needs_attention')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 2)
        self.assertEqual(inv.public_snapshot(self.db)['investigations'], [])

    def test_reviewed_status_is_derived_without_reopening_or_mutating_job_history(self):
        self.enqueue()
        for _ in range(3):
            self.tick()
        before = queue.status(self.db)['jobs'][0]
        self.assertEqual(before['state'], 'awaiting_review')
        inv.review(self.db, self.investigation_id, 'Test reviewer')
        frozen_state = inv.get(self.db, self.investigation_id)
        stored_row = tuple(self.db.execute('SELECT * FROM research_queue_jobs').fetchone())
        history = [tuple(row) for row in self.db.execute('SELECT * FROM research_queue_events')]
        costs = before['reserved_usd'], before['known_estimated_usd'], before['model_calls']
        calls = len(self.calls)
        changes = self.db.total_changes
        after = queue.status(self.db)['jobs'][0]
        self.assertEqual(after['state'], 'reviewed')
        self.assertEqual((after['reserved_usd'], after['known_estimated_usd'], after['model_calls']), costs)
        self.assertEqual(self.db.total_changes, changes)
        self.tick()
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM research_queue_jobs').fetchone()), stored_row)
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM research_queue_events')], history)
        self.assertEqual(inv.get(self.db, self.investigation_id), frozen_state)
        with self.db:
            self.db.execute("UPDATE investigations SET state_json=json_set(state_json,'$.draft.headline','Changed after review')")
        with self.assertRaisesRegex(ValueError, 'Reviewed investigation changed'):
            queue.status(self.db)

    def test_worst_case_money_and_prior_history_block_new_calls_but_allow_known_get(self):
        self.enqueue()
        p.set_budget_limit(self.db, 299)
        self.assertEqual(self.tick()['jobs'][0]['state'], 'budget_wait')
        self.assertEqual(self.calls, [])
        p.set_budget_limit(self.db, 300)
        with patch.object(p, 'api', side_effect=lambda method, route, body=None, request_id=None, **kwargs:
                          self.response('resp_' + request_id, status='queued')):
            self.tick()
        p.set_budget_limit(self.db, 20)
        self.tick()
        self.assertEqual(self.calls[0][0], 'GET')
        self.tick()
        self.assertEqual(queue.status(self.db)['jobs'][0]['state'], 'budget_wait')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 20)

    def test_bounded_repair_fits_full_reservation_and_editorial_recheck_is_not_run(self):
        self.enqueue(); self.revise = True
        for _ in range(5): result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'needs_attention')
        self.assertEqual(result['jobs'][0]['reserved_usd'], '2.6')
        self.assertEqual(len(self.calls), 5)
        state = inv.get(self.db, self.investigation_id)
        state['phase'] = 'editorial_recheck'; state['editorial_amendment'] = {'editor': 'test'}
        inv.save(self.db, state, 'test_edit')
        with self.db:
            self.db.execute("UPDATE research_queue_jobs SET state='waiting'")
        self.tick()
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(queue.status(self.db)['jobs'][0]['error_code'], 'editorial_review_required')

    def test_due_fifo_and_deadline_do_not_trigger_early_or_late_calls(self):
        self.enqueue(due=self.now + 300)
        self.tick(); self.assertEqual(self.calls, [])
        self.now += 1800
        result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'deadline')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 0)

    def test_one_controller_lock_blocks_competing_submission(self):
        self.enqueue()
        entered, release = threading.Event(), threading.Event()
        def provider(method, route, body=None, request_id=None, **kwargs):
            entered.set(); self.assertTrue(release.wait(5))
            return self.response('resp_' + request_id, status='queued')
        def first():
            with closing(p.database(self.path)) as db:
                return queue.advance(db)
        with patch.object(p, 'api', side_effect=provider) as api, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(first)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(ValueError, 'Another research queue'):
                    queue.advance(self.db)
                self.assertEqual(api.call_count, 1)
            finally:
                release.set()
            future.result()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_changed_profile_and_frozen_snapshot_are_blocked_before_new_reservation(self):
        self.enqueue()
        with patch.dict(p.TASK_PROFILES[queue.ANALYST], {'reserve_cents': 21}):
            result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'needs_attention')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_full_four_turn_repair_path_cannot_exceed_three_dollars(self):
        self.enqueue(); self.revise = True
        p.set_budget_limit(self.db, 300)
        ordinary = self.api
        def provider(method, route, body=None, request_id=None, **kwargs):
            state = inv.get(self.db, self.investigation_id)
            if state['phase'] == 'research' and state['turn'] == 0:
                result = ordinary(method, route, body, request_id, **kwargs)
                result['output'] = [call for call in result['output'] if call.get('name') != 'save_hypothesis']
                return result
            if state['phase'] == 'research' and state['turn'] in {1, 2}:
                self.calls.append((method, route, request_id))
                name, arguments = ('read_source', {'source_id': 'fy26-call', 'query': 'lease'}) if state['turn'] == 1 else (
                    'save_hypothesis', {'statement': 'Additional accounting evidence may refine the distinction.',
                                        'invalidation': 'A direct reconciliation would settle it.'})
                return self.response('resp_' + request_id, [{
                    'type': 'function_call', 'call_id': 'extra_' + str(state['turn']),
                    'name': name, 'arguments': json.dumps(arguments)}])
            return ordinary(method, route, body, request_id, **kwargs)
        with patch.object(p, 'api', side_effect=provider):
            for _ in range(7): result = self.tick()
            self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'needs_attention')
        self.assertEqual(result['jobs'][0]['reserved_usd'], '3')
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 300)

    def test_waiting_first_job_keeps_fifo_and_pause_allows_next_job(self):
        self.enqueue(); first_id = self.investigation_id
        self.enqueue('second-job'); self.investigation_id = first_id
        with patch.object(p, 'api', side_effect=lambda method, route, body=None, request_id=None, **kwargs:
                          self.response('resp_' + request_id, status='queued')) as api:
            queue.advance(self.db)
            queue.advance(self.db)
            self.assertEqual(api.call_count, 1)
            queue.pause(self.db, 'test-job')
            queue.advance(self.db)
            self.assertEqual(api.call_count, 2)

    def test_attached_snapshot_drift_stops_before_more_paid_work(self):
        self.enqueue(); self.tick()
        state = inv.get(self.db, self.investigation_id)
        state['snapshots']['fy26-call']['text'] = 'Drifted private memory'
        inv.save(self.db, state, 'test_drift')
        result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'needs_attention')
        self.assertEqual(result['jobs'][0]['error_code'], 'frozen_sources_changed')
        self.assertEqual(len(self.calls), 1)

    def test_pause_or_deadline_during_preflight_prevents_paid_submission(self):
        self.enqueue()
        with patch.object(p, 'preflight_task', side_effect=lambda model: queue.pause(self.db, 'test-job')):
            result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'paused')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        queue.pause(self.db, 'test-job', False)
        def expire(model):
            self.now += 1800
        with patch.object(p, 'preflight_task', side_effect=expire):
            result = self.tick()
        self.assertEqual(result['jobs'][0]['state'], 'deadline')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_cli_lazy_import_uses_the_same_queue_admission_context(self):
        self.enqueue()
        original_database = p.database
        original_module = sys.modules['research_queue']
        self.addCleanup(sys.modules.__setitem__, 'research_queue', original_module)
        with patch.object(sys, 'argv', ['research_queue.py', 'advance']), \
                patch.object(p, 'database', side_effect=lambda *args: original_database(self.path)), \
                redirect_stdout(io.StringIO()):
            runpy.run_path(str(Path(queue.__file__)), run_name='__main__')
        sys.modules['research_queue'] = original_module
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(queue.status(self.db)['jobs'][0]['state'], 'waiting')


if __name__ == '__main__':
    unittest.main()
