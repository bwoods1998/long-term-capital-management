"""Recovery and publication tests with synthetic provider responses only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import investigator as agent
import portfolio as ledger
import research_sources as sources


class InvestigatorTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = ledger.database(self.root / 'portfolio.sqlite')
        self.addCleanup(self.db.close)
        ledger.set_budget_limit(self.db, 10000)
        agent.setup(self.db)
        self.calls = []
        self.revise = False
        self.queued = False
        self.api_patch = patch.object(ledger, 'api', side_effect=self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        for name, value in [('preflight_task', None), ('credential_fingerprint', 'synthetic-key-fingerprint')]:
            mocked = patch.object(ledger, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.investigation_id = agent.start(self.db)

    def capture(self, source_id, cutoff=None):
        text = 'Synthetic evidence. Lease classification can affect reported expenditure. ' * 30
        return {**sources.allowed_source(source_id), 'fetched_at': '2026-09-12T20:00:00Z',
                'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}

    def store(self):
        return self

    def response(self, response_id, output):
        return {'id': response_id, 'status': 'completed', 'output': output,
                'usage': {'input_tokens': 1000, 'output_tokens': 200, 'input_tokens_details': {'cached_tokens': 0}}}

    def final_report(self):
        state = agent.get(self.db, self.investigation_id)
        citation = next(iter(state['passages']), 'cash-versus-capex')
        return {'headline': 'Accounting definitions matter',
                'summary': 'Reported expenditure is sensitive to definitions. Underlying commitments require separate evidence.',
                'claims': [{'text': 'Cash spending and total capital commitments are different measures.',
                            'evidence_ids': [citation]}],
                'changes': ['The distinction needs explicit attention.'],
                'open_questions': ['How will future commitments translate into cash payments?'],
                'invalidation': ['A complete reconciliation could change the interpretation.'],
                'change_assessment': 'qualified'}

    def api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, request_id))
        state = agent.get(self.db, self.investigation_id)
        response_id = 'resp_' + (request_id or route.rsplit('/', 1)[-1].removeprefix('resp_'))
        if self.queued and method == 'POST':
            self.queued = False
            return {'id': response_id, 'status': 'queued', 'output': []}
        if state['phase'] == 'research' and state['turn'] == 0 and state['mode'] == 'tools':
            definitions = [('read_source', {'source_id': 'fy26-call', 'query': 'lease'}),
                           ('calculate', {'operation': 'subtract', 'left_id': 'ocf-2026', 'right_id': 'ppe-2026'}),
                           ('save_hypothesis', {'statement': 'Reported measures may move without new commitments.',
                                                'invalidation': 'A full reconciliation could disprove that explanation.'})]
            output = [{'type': 'function_call', 'call_id': f'call_{index}', 'name': name, 'arguments': json.dumps(args)}
                      for index, (name, args) in enumerate(definitions)]
            return self.response(response_id, output)
        if state['phase'] in {'critique', 'recheck', 'editorial_recheck'}:
            value = {'verdict': 'pass', 'summary': 'The claims fit the supplied evidence.', 'issues': []}
            if self.revise:
                value = {'verdict': 'revise', 'summary': 'A qualification is missing.', 'issues': [
                    {'claim_index': 0, 'severity': 'material', 'reason': 'The scope needs a qualification.',
                     'evidence_ids': ['cash-versus-capex']}]}
        else:
            value = self.final_report()
        return self.response(response_id, [{'type': 'message', 'role': 'assistant',
                                           'content': [{'type': 'output_text', 'text': json.dumps(value)}]}])

    def test_complete_loop_needs_explicit_review_and_exports_no_private_trace(self):
        for _ in range(3):
            agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(agent.get(self.db, self.investigation_id)['phase'], 'awaiting_review')
        self.assertEqual(agent.public_snapshot(self.db)['investigations'], [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
        agent.review(self.db, self.investigation_id, 'Test reviewer')
        public = agent.public_snapshot(self.db)
        item = public['investigations'][0]
        self.assertEqual(item['metrics']['model_calls'], 3)
        self.assertEqual(item['metrics']['tool_calls'], 3)
        self.assertEqual(item['result']['claims'][0]['source_ids'], ['fy26-call'])
        serialized = json.dumps(public)
        for private in ('synthetic-key-fingerprint', 'Synthetic evidence.', 'conversation', 'request_id', 'packet_json'):
            self.assertNotIn(private, serialized)
        with self.assertRaises(ValueError):
            agent.save(self.db, agent.get(self.db, self.investigation_id), 'tamper')

    def test_crash_after_reservation_reuses_original_task_and_request(self):
        with patch.object(ledger, 'execute', side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError):
                agent.advance(self.db, self.investigation_id, self.store())
        original = self.db.execute('SELECT id,request FROM runs').fetchone()
        self.assertEqual(len(self.calls), 0)
        agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(self.calls[0][2], original['id'])
        self.assertEqual(self.db.execute('SELECT request FROM runs').fetchone()[0], original['request'])

    def test_final_turn_synthesizes_without_tools_and_can_reach_review(self):
        self.investigation_id = agent.start(self.db, max_turns=2)
        state = agent.get(self.db, self.investigation_id)
        self.assertEqual(state['turn_policy'], agent.TURN_POLICY)
        agent.advance(self.db, self.investigation_id, self.store())
        first = json.loads(self.db.execute('SELECT request FROM runs').fetchone()[0])
        self.assertTrue(first['tools'])
        self.assertIn('Remaining research turns including this request: 2', first['input'][-1]['content'])
        self.assertIn('Remaining turns that permit tools: 1', first['input'][-1]['content'])
        agent.advance(self.db, self.investigation_id, self.store())
        final = json.loads(self.db.execute('SELECT request FROM runs WHERE task_key=?',
                                         (self.investigation_id + ':research:1',)).fetchone()[0])
        self.assertNotIn('tools', final)
        self.assertIn('Remaining research turns including this request: 1', final['input'][-1]['content'])
        self.assertIn('Synthesize the final report now', final['input'][-1]['content'])
        self.assertEqual(agent.get(self.db, self.investigation_id)['phase'], 'critique')
        agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(agent.get(self.db, self.investigation_id)['phase'], 'awaiting_review')
        self.assertEqual(len(self.calls), 3)
        self.assertFalse(agent.public_snapshot(self.db)['investigations'])

    def test_missing_final_turn_checks_stop_before_preflight_or_reservation(self):
        for missing in ['source passage', 'successful calculation', 'saved hypothesis']:
            with self.subTest(missing=missing):
                self.investigation_id = agent.start(self.db, max_turns=2)
                agent.advance(self.db, self.investigation_id, self.store())
                state = agent.get(self.db, self.investigation_id)
                if missing == 'source passage':
                    state['passages'] = {}
                elif missing == 'saved hypothesis':
                    state['hypotheses'] = []
                else:
                    for item in state['tool_results']:
                        if item['name'] == 'calculate':
                            item['success'] = False
                agent.save(self.db, state, 'synthetic_missing_check')
                before = self.db.execute('SELECT COUNT(*),SUM(reserved_cents) FROM runs').fetchone()
                calls = len(self.calls)
                with patch.object(ledger, 'preflight_task', side_effect=AssertionError('No new paid work')):
                    result = agent.advance(self.db, self.investigation_id, self.store())
                    agent.advance(self.db, self.investigation_id, self.store())
                self.assertEqual(result['phase'], 'needs_attention')
                self.assertIn(missing, result['error'])
                self.assertEqual(len(self.calls), calls)
                self.assertEqual(tuple(before), tuple(self.db.execute('SELECT COUNT(*),SUM(reserved_cents) FROM runs').fetchone()))

    def test_final_synthesis_rejects_unrequested_tool_calls_without_running_them(self):
        self.investigation_id = agent.start(self.db, max_turns=2)
        agent.advance(self.db, self.investigation_id, self.store())
        before = deepcopy(agent.get(self.db, self.investigation_id)['tool_results'])
        def unexpected_tool(method, route, body=None, request_id=None, **kwargs):
            return self.response('resp_' + request_id, [{'type': 'function_call', 'call_id': 'unexpected',
                'name': 'calculate', 'arguments': json.dumps({
                    'operation': 'subtract', 'left_id': 'ocf-2026', 'right_id': 'ppe-2026'})}])
        with patch.object(ledger, 'api', side_effect=unexpected_tool), \
                patch.object(agent, '_tool', side_effect=AssertionError('Synthesis must not execute tools')):
            result = agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(result['phase'], 'needs_attention')
        self.assertEqual(agent.get(self.db, self.investigation_id)['tool_results'], before)

    def test_last_gathering_tools_match_only_missing_prerequisites(self):
        state = agent.get(self.db, self.investigation_id)
        state['turn'] = state['max_turns'] - 2
        for passage in (False, True):
            for calculation in (False, True):
                for hypothesis in (False, True):
                    with self.subTest(passage=passage, calculation=calculation, hypothesis=hypothesis):
                        state['passages'] = {'synthetic-passage': {}} if passage else {}
                        state['tool_results'] = [{'name': 'calculate', 'success': calculation}]
                        state['hypotheses'] = [{}] if hypothesis else []
                        messages, tools = agent._research_input(state)
                        expected = {name for name, present in [('read_source', passage), ('calculate', calculation),
                                                              ('save_hypothesis', hypothesis)] if not present}
                        self.assertEqual({item['name'] for item in tools or []}, expected)
                        self.assertIn('Remaining turns that permit tools: 1', messages[-1]['content'])
                        self.assertNotIn('list_sources', expected)
                        if expected:
                            self.assertIn('question-relevant arguments', messages[-1]['content'])
                        else:
                            self.assertIsNone(tools)
                            self.assertIn('Synthesize the report now', messages[-1]['content'])

    def test_restricted_last_gathering_completes_relevant_checks_then_synthesizes(self):
        self.investigation_id = agent.start(self.db, max_turns=3)
        ordinary = self.api
        def focused_provider(method, route, body=None, request_id=None, **kwargs):
            state = agent.get(self.db, self.investigation_id)
            if state['phase'] == 'research' and state['turn'] in {0, 1}:
                self.calls.append((method, route, request_id))
                if state['turn'] == 0:
                    definitions = [('read_source', {'source_id': 'fy26-call', 'query': 'lease'})]
                else:
                    definitions = [('calculate', {'operation': 'subtract', 'left_id': 'ocf-2026', 'right_id': 'ppe-2026'}),
                                   ('save_hypothesis', {'statement': 'The cash remainder may differ from full investment commitments.',
                                                        'invalidation': 'An explicit lease reconciliation could change this view.'})]
                    self.assertEqual({tool['name'] for tool in body['tools']}, {'calculate', 'save_hypothesis'})
                return self.response('resp_' + request_id, [{'type': 'function_call', 'call_id': f'focused_{i}',
                    'name': name, 'arguments': json.dumps(arguments)} for i,(name,arguments) in enumerate(definitions)])
            return ordinary(method, route, body, request_id, **kwargs)
        with patch.object(ledger, 'api', side_effect=focused_provider):
            for _ in range(4):
                result = agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(result['phase'], 'awaiting_review')
        state = agent.get(self.db, self.investigation_id)
        calculation = next(item['result'] for item in state['tool_results'] if item['name'] == 'calculate')
        self.assertEqual(calculation['value'], '66987')
        final = json.loads(self.db.execute('SELECT request FROM runs WHERE task_key=?',
                                         (state['id'] + ':research:2',)).fetchone()[0])
        self.assertNotIn('tools', final)
        self.assertEqual(result['costs']['model_calls'], 4)
        self.assertFalse(agent.public_snapshot(self.db)['investigations'])

    def test_v2_rejects_undeclared_retrieval_before_any_tool_runs(self):
        self.investigation_id = agent.start(self.db, max_turns=3)
        agent.advance(self.db, self.investigation_id, self.store())
        state = agent.get(self.db, self.investigation_id)
        state['hypotheses'] = []
        agent.save(self.db, state, 'synthetic_missing_hypothesis')
        before = deepcopy(state['tool_results'])
        def unrequested(method, route, body=None, request_id=None, **kwargs):
            self.assertEqual([tool['name'] for tool in body['tools']], ['save_hypothesis'])
            return self.response('resp_' + request_id, [
                {'type': 'function_call', 'call_id': 'permitted_first', 'name': 'save_hypothesis',
                 'arguments': json.dumps({'statement': 'Scope may explain the difference.',
                                          'invalidation': 'A full reconciliation could change this view.'})},
                {'type': 'function_call', 'call_id': 'not_permitted', 'name': 'read_source',
                 'arguments': json.dumps({'source_id': 'fy26-call', 'query': 'lease'})}])
        with patch.object(ledger, 'api', side_effect=unrequested), \
                patch.object(agent, '_tool', side_effect=AssertionError('Undeclared tool must not run')):
            result = agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(result['phase'], 'needs_attention')
        self.assertEqual(agent.get(self.db, self.investigation_id)['tool_results'], before)

    def test_v1_last_gathering_request_is_unchanged_and_accepted_body_recovers(self):
        self.investigation_id = agent.start(self.db, max_turns=3)
        state = agent.get(self.db, self.investigation_id)
        del state['turn_policy']
        legacy_prompt = agent._prompt(state)
        state['turn_policy'] = agent.SYNTHESIS_POLICY
        prompt = agent._prompt(state)
        self.assertEqual(prompt, legacy_prompt + '\nTURN POLICY: synthesis-last-v1. The final research turn is reserved for synthesis, '
                         'with no tools. Gather the required passage, calculation, and hypothesis before that turn. '
                         'You may finish earlier once the evidence is sufficient.')
        state['conversation'] = [{'role': 'user', 'content': prompt}]
        agent.save(self.db, state, 'synthetic_v1_state')
        agent.advance(self.db, self.investigation_id, self.store())
        conversation = deepcopy(agent.get(self.db, self.investigation_id)['conversation'])
        self.queued = True
        agent.advance(self.db, self.investigation_id, self.store())
        row = self.db.execute('SELECT id,request,response_id FROM runs WHERE task_key=?',
                              (state['id'] + ':research:1',)).fetchone()
        body = json.loads(row['request'])
        self.assertEqual(body['tools'], [*sources.TOOLS, agent.HYPOTHESIS_TOOL])
        self.assertEqual(body['input'], [*conversation, {'role':'user','content':
            'TURN POLICY: synthesis-last-v1. Remaining research turns including this request: 2. '
            'Remaining turns that permit tools: 1. Gather any missing required checks before the final '
            'synthesis turn: none. Combine independent tool requests when useful; avoid repeating completed '
            'checks. Return the report early if the evidence is sufficient.'}])
        with patch.object(agent, '_research_input', side_effect=AssertionError('Never rebuild accepted v1 input')):
            result = agent.advance(self.db, state['id'], self.store())
        self.assertEqual(result['phase'], 'critique')
        self.assertEqual(self.calls[-1], ('GET', '/v1/responses/' + row['response_id'], None))
        saved = self.db.execute('SELECT id,request,response_id FROM runs WHERE task_key=?',
                                (state['id'] + ':research:1',)).fetchone()
        self.assertEqual(tuple(row), tuple(saved))

    def test_legacy_last_turn_keeps_tools_and_accepted_request_recovery(self):
        self.investigation_id = agent.start(self.db, max_turns=2)
        state = agent.get(self.db, self.investigation_id)
        del state['turn_policy']
        state['conversation'] = [{'role': 'user', 'content': agent._prompt(state)}]
        agent.save(self.db, state, 'synthetic_legacy_state')
        agent.advance(self.db, self.investigation_id, self.store())
        conversation = deepcopy(agent.get(self.db, self.investigation_id)['conversation'])
        self.queued = True
        agent.advance(self.db, self.investigation_id, self.store())
        saved = self.db.execute('SELECT id,request,response_id FROM runs WHERE task_key=?',
                                (self.investigation_id + ':research:1',)).fetchone()
        request = json.loads(saved['request'])
        self.assertTrue(request['tools'])
        self.assertEqual(request['input'], conversation)
        self.assertNotIn('TURN POLICY', ledger.encoded(request))
        with patch.object(agent, '_research_input', side_effect=AssertionError('Frozen request must survive upgrades')), \
                patch.object(ledger, 'preflight_task', side_effect=AssertionError('Known response needs no new admission')):
            result = agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(result['phase'], 'critique')
        self.assertEqual(result['turn_policy'], 'legacy-tools-v0')
        self.assertEqual(self.calls[-1], ('GET', '/v1/responses/' + saved['response_id'], None))
        after = self.db.execute('SELECT id,request,response_id FROM runs WHERE task_key=?',
                               (self.investigation_id + ':research:1',)).fetchone()
        self.assertEqual(tuple(saved), tuple(after))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 2)

    def test_managed_amendment_is_rejected_before_any_mutation(self):
        for _ in range(3):
            agent.advance(self.db, self.investigation_id, self.store())
        self.db.execute('CREATE TABLE research_queue_jobs (investigation_id TEXT)')
        for attached in (True, False):
            with self.subTest(attached=attached):
                state = agent.get(self.db, self.investigation_id)
                if attached:
                    state['queue_job_key'] = 'synthetic-managed-job'
                else:
                    del state['queue_job_key']
                    self.db.execute('INSERT INTO research_queue_jobs VALUES(?)', (state['id'],))
                agent.save(self.db, state, 'synthetic_managed_mapping')
                before = ledger.encoded(state)
                events = self.db.execute('SELECT COUNT(*) FROM investigation_events').fetchone()[0]
                revised = deepcopy(state['draft'])
                revised['headline'] = 'Scoped observations need careful review'
                with self.assertRaisesRegex(ValueError, 'bounded editorial handoff'):
                    agent.amend(self.db, self.investigation_id, revised, 'Test editor')
                self.assertEqual(ledger.encoded(agent.get(self.db, self.investigation_id)), before)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigation_events').fetchone()[0], events)
                self.assertEqual(len(self.calls), 3)

    def test_queued_work_resumes_by_get_and_keeps_frozen_sources(self):
        self.queued = True
        agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(agent.get(self.db, self.investigation_id)['turn'], 0)
        agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual([x[0] for x in self.calls], ['POST', 'GET'])
        state = agent.get(self.db, self.investigation_id)
        old = deepcopy(state['snapshots'])
        with patch.object(self, 'capture', side_effect=AssertionError('Frozen source fetched again')):
            result = agent._tool(state, {'name': 'read_source', 'arguments': json.dumps({
                'source_id': 'fy26-call', 'query': 'classification'})}, self)
        self.assertTrue(result['passages'])
        self.assertEqual(state['snapshots'], old)

    def test_critic_repairs_once_then_stops_without_publication(self):
        self.revise = True
        for _ in range(5):
            agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(agent.get(self.db, self.investigation_id)['phase'], 'needs_attention')
        calls = len(self.calls)
        agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(len(self.calls), calls)
        with self.assertRaises(ValueError):
            agent.review(self.db, self.investigation_id, 'Test reviewer')
        self.assertFalse(agent.public_snapshot(self.db)['investigations'])

    def test_deadline_and_unknown_tools_cannot_start_work(self):
        state = agent.get(self.db, self.investigation_id)
        with self.assertRaises(ValueError):
            agent._tool(state, {'name': 'run_shell', 'arguments': '{"command":"bad"}'}, self)
        state['deadline'] = 1
        agent.save(self.db, state, 'test_deadline')
        agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(self.calls, [])
        self.assertEqual(agent.get(self.db, self.investigation_id)['phase'], 'expired')

    def test_invalid_citations_and_mixed_critic_verdict_are_rejected(self):
        value = self.final_report()
        value['claims'][0]['evidence_ids'] = ['invented-passage']
        state = agent.get(self.db, self.investigation_id)
        with self.assertRaises(ValueError):
            agent.report(value, state)
        state['draft'] = self.final_report()
        with self.assertRaises(ValueError):
            agent.critique({'verdict': 'pass', 'summary': 'Pass', 'issues': [
                {'claim_index': 0, 'severity': 'material', 'reason': 'Not supported.', 'evidence_ids': []}]}, state)

    def test_memory_compaction_preserves_evidence_and_resume_request(self):
        agent.advance(self.db, self.investigation_id, self.store())
        state = agent.get(self.db, self.investigation_id)
        passages = deepcopy(state['passages'])
        state['conversation'].append({'role': 'assistant', 'content': 'Repeated filler. ' * 7000})
        agent.save(self.db, state, 'synthetic_context_growth')
        with patch.object(ledger, 'execute', side_effect=RuntimeError('synthetic restart')):
            with self.assertRaises(RuntimeError):
                agent.advance(self.db, self.investigation_id, self.store())
        state = agent.get(self.db, self.investigation_id)
        self.assertEqual(state['passages'], passages)
        notebook = state['conversation'][1]['content']
        for citation, passage in passages.items():
            self.assertIn(citation, notebook)
            self.assertIn(passage['text'], notebook)
        self.assertIn(state['hypotheses'][0]['statement'], notebook)
        self.assertLess(len(ledger.encoded(state['conversation']).encode()), 72000)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM investigation_events WHERE kind='memory_compacted'").fetchone()[0], 1)
        request = self.db.execute('SELECT request FROM runs WHERE task_key=?', (state['id'] + ':research:1',)).fetchone()[0]
        with patch.object(agent, 'compact_memory', side_effect=AssertionError('Pending request must not be compacted again')):
            agent.advance(self.db, self.investigation_id, self.store())
        self.assertEqual(self.db.execute('SELECT request FROM runs WHERE task_key=?', (state['id'] + ':research:1',)).fetchone()[0], request)
        self.assertEqual(agent.get(self.db, state['id'])['phase'], 'critique')

    def test_only_reviewed_investigations_become_frozen_future_memory(self):
        for _ in range(3):
            agent.advance(self.db, self.investigation_id, self.store())
        pending = agent.start(self.db)
        self.assertEqual(agent.get(self.db, pending)['research_memory'], [])
        agent.review(self.db, self.investigation_id, 'Test reviewer')
        following = agent.start(self.db)
        memory = agent.get(self.db, following)['research_memory']
        self.assertEqual([item['id'] for item in memory], [self.investigation_id])
        self.assertEqual(memory[0]['result'], agent.get(self.db, self.investigation_id)['draft'])
        self.assertEqual(agent.get(self.db, pending)['research_memory'], [])
        self.assertIn('not new evidence', agent.get(self.db, following)['conversation'][0]['content'])

    def test_editorial_correction_preserves_original_and_requires_fresh_critic(self):
        for _ in range(3):
            agent.advance(self.db, self.investigation_id, self.store())
        original = deepcopy(agent.get(self.db, self.investigation_id)['draft'])
        revised = deepcopy(original)
        revised['headline'] = 'Management guidance needs separate verification'
        agent.amend(self.db, self.investigation_id, revised, 'Test editor')
        state = agent.get(self.db, self.investigation_id)
        self.assertEqual(state['initial_draft'], original)
        self.assertEqual(state['editorial_amendment']['before'], original)
        self.assertEqual(state['phase'], 'editorial_recheck')
        with self.assertRaises(ValueError):
            agent.review(self.db, state['id'], 'Test reviewer')
        agent.advance(self.db, state['id'], self.store())
        agent.review(self.db, state['id'], 'Test reviewer')
        self.assertEqual(agent.public_snapshot(self.db)['investigations'][0]['result']['headline'], revised['headline'])
        with self.assertRaises(ValueError):
            agent.amend(self.db, state['id'], original, 'Test editor')

    def test_critic_receives_frozen_prior_memory_for_change_claims(self):
        state = agent.get(self.db, self.investigation_id)
        state['parent_memory'] = {'headline': 'Synthetic earlier view'}
        state['research_memory'] = [{'id': 'prior', 'result': {'summary': 'Earlier investigation'}}]
        for repair in (False, True):
            prompt = agent._critique_input(state, repair)[0]['content']
            self.assertIn('Synthetic earlier view', prompt)
            self.assertIn('Earlier investigation', prompt)
            self.assertIn('not_new_evidence', prompt)

    def test_compaction_metrics_work_with_an_active_voyage(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        state = agent.get(self.db, self.investigation_id)
        state['conversation'].append({'role': 'assistant', 'content': 'Synthetic repeated text. ' * 5000})
        voyage = MagicMock()
        voyage.status = 'running'
        trace = SimpleNamespace(voyage=voyage, state={'status': 'running'})
        token = agent.tracking._active.set(trace)
        try:
            self.assertTrue(agent.compact_memory(self.db, state))
        finally:
            agent.tracking._active.reset(token)
        name = voyage.event.call_args.args[0]
        payload = voyage.event.call_args.kwargs['payload']
        self.assertEqual(name, 'memory.compacted')
        self.assertLess(payload['after_bytes'], payload['before_bytes'])


if __name__ == '__main__':
    unittest.main()
