"""Offline autonomy contracts: real SQLite reservations, synthetic sources, fake provider."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import overnight as o
import portfolio as p


class OvernightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = p.database(self.root / 'ledger.sqlite')
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 5000)
        self.now = 1789282800.0
        self.calls = []
        self.pending = False
        self.unknown_usage = set()
        self.bad_revision = set()
        self.malformed = set()
        self.fail_posts = set()
        self.evidence = {'schema_version': 1, 'evidence_as_of': '2026-09-13',
                         'question': 'What cash generation supports this synthetic spending chain?', 'companies': []}
        for symbol in o.SYMBOLS:
            text = 'Synthetic FY2026 USD millions. Operating cash flow 100; cash investment 40. Demand may depend on a shared spending cycle.'
            digest = hashlib.sha256(text.encode()).hexdigest()
            self.evidence['companies'].append({'symbol': symbol, 'company': symbol + ' Fixture',
                'question': 'Which evidence would change this synthetic case?', 'documents': [{
                    'id': 'doc-' + symbol.lower(), 'title': 'Synthetic annual report',
                    'url': 'https://example.com/' + symbol.lower(), 'published_at': '2026-09-01',
                    'available_as_of': '2026-09-01', 'source_sha256': digest,
                    'passages': [{'id': 'quote-' + symbol.lower(), 'text': text, 'sha256': digest,
                                  'start': 0, 'end': len(text)}]}]})
        self.prefix = {'prefix': 'Synthetic dated common-source prefix; no account data.',
                       'expires_at': p.iso(self.now + 12 * 3600), 'prefix_sha256': 'b' * 64}
        for target, name, kwargs in [
            (o, 'ROOT', {'new': self.root}),
            (o.cloud.cloud, 'SESSION_ROOT', {'new': self.root / 'compute'}),
            (o, 'hashes', {'return_value': {'fixture.py': 'a' * 64}}),
            (o.time, 'time', {'side_effect': lambda: self.now}),
            (o.cache, 'validate_existing_prefix', {'return_value': self.prefix}),
            (p, 'credential_fingerprint', {'return_value': 'c' * 64}),
            (p, 'api', {'side_effect': self.api}),
            (p, 'preflight_task', {'return_value': None}),
        ]:
            mocked = patch.object(target, name, **kwargs)
            mocked.start()
            self.addCleanup(mocked.stop)

    def start(self, key='synthetic-overnight'):
        return o.start(self.db, self.evidence, key)

    def case(self, symbol):
        quote = 'quote-' + symbol.lower()
        return {'symbol': symbol, 'headline': 'PRIVATE_DRAFT: synthetic cash conversion',
            'metrics': [{'id': key, 'label': label, 'value': number, 'unit': 'USD millions',
                         'period': 'FY2026', 'evidence_id': quote, 'quote': source_quote}
                        for key, label, number, source_quote in [
                            ('ocf', 'Operating cash flow', '100', 'Operating cash flow 100'),
                            ('investment', 'Cash investment', '40', 'cash investment 40')]],
            'claims': [{'id': 'cash', 'text': 'Operating cash flow is 100 in the synthetic source.',
                        'evidence_ids': [quote], 'quotes': [{'evidence_id': quote, 'text': 'Operating cash flow 100'}],
                        'kind': 'reported'}],
            'cash_flow_bridge': {'status': 'available', 'operating_cash_flow_metric_id': 'ocf',
                                'cash_investment_metric_id': 'investment', 'remainder': '60',
                                'caveat': 'Company-wide synthetic residual, not AI profit.'},
            'dependencies': [],
            'watchpoints': [{'question': 'Would investment outgrow operating cash flow?', 'evidence_ids': [quote]}],
            'limitations': ['Synthetic evidence is for offline testing only.']}

    def output(self, stage_id):
        symbol, kind = stage_id.split(':')
        quote = 'quote-' + symbol.lower()
        if kind in ('baseline', 'independent', 'revision', 'repair'):
            if stage_id in self.malformed:
                return {'symbol': symbol, 'headline': 'PRIVATE_DRAFT malformed', 'metrics': 7}
            result = self.case(symbol)
            if kind == 'revision' and symbol in self.bad_revision:
                result['cash_flow_bridge']['remainder'] = '61'
            return result
        if kind == 'scout':
            return {'symbol': symbol, 'questions': [], 'limitations': ['Dated scouting only.']}
        if kind == 'critic':
            return {'symbol': symbol, 'issues': [], 'missing_evidence': [], 'verdict': 'pass'}
        if kind.startswith('judge-'):
            return {'symbol': symbol, 'preferred': 'A', 'reasons': [{'text': 'Exact cash figures are present.',
                'evidence_ids': [quote]}], 'limitations': ['Mechanical support is not semantic approval.']}
        if kind == 'watchlist':
            return {'symbol': symbol, 'next_checks': [], 'limitations': ['No live forecasts.']}
        if kind in ('map-critic', 'map-review'):
            return {'issues': [], 'most_important_missing_evidence': [], 'verdict': 'pass'}
        return {'headline': 'PRIVATE_DRAFT: conceptual dependence map', 'connections': [],
                'shared_risks': [], 'scenarios': [], 'limitations': ['No contracts inferred.']}

    def api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, request_id, deepcopy(body)))
        if method == 'POST':
            row = p.get_run(self.db, request_id)
            response_id = 'resp_' + request_id.replace('-', '')
        else:
            response_id = route.rsplit('/', 1)[-1]
            row = self.db.execute('SELECT * FROM runs WHERE response_id=?', (response_id,)).fetchone()
        stage_id = row['task_key'].split(':', 2)[-1]
        if method == 'POST' and stage_id in self.fail_posts:
            raise RuntimeError('Synthetic uncertain transport failure')
        request = json.loads(row['request'])
        response = {'id': response_id, 'model': request['model'],
                    'status': 'queued' if self.pending else 'completed', 'output': []}
        if not self.pending:
            response['output'] = [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(self.output(stage_id))}]}]
            if stage_id not in self.unknown_usage:
                response['usage'] = {'input_tokens': 100, 'output_tokens': 50,
                                     'input_tokens_details': {'cached_tokens': 20}}
        return response

    def finish(self, identifier):
        for _ in range(100):
            value = o.advance(self.db, identifier)
            self.assertLessEqual(value['inflight_requests'], 6)
            if value['state'] == 'complete':
                return value
        self.fail('Synthetic campaign did not finish within its bounded stage count')

    def test_prepare_is_network_free_immutable_and_idempotent(self):
        identifier = self.start()
        frozen = o.protocol(self.db, identifier)
        self.assertEqual(len(frozen['stages']), 86)
        self.assertLessEqual(frozen['max_reservation_cents'], 4000)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(self.start(), identifier)
        self.evidence['question'] += ' Changed.'
        with self.assertRaisesRegex(ValueError, 'different frozen inputs'):
            self.start()
        self.assertEqual(o.protocol(self.db, identifier), frozen)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE overnight_campaigns SET sha256='altered'")
        self.db.rollback()
        self.assertEqual(self.calls, [])

    def test_full_campaign_completes_86_stages_but_skips_nine_unneeded_repairs(self):
        identifier = self.start()
        value = self.finish(identifier)
        self.assertEqual(value['completed_steps'], 86)
        self.assertEqual(value['submitted_requests'], 77)
        self.assertEqual(value['unknown_requests'], 0)
        self.assertGreater(Decimal(value['estimated_usd']), 0)
        posts = [call for call in self.calls if call[0] == 'POST']
        self.assertEqual(len(posts), len({call[2] for call in posts}))
        before = deepcopy(self.calls)
        self.assertEqual(o.advance(self.db, identifier)['state'], 'complete')
        self.assertEqual(self.calls, before)
        for symbol in o.SYMBOLS:
            step = self.db.execute('SELECT * FROM overnight_steps WHERE campaign_id=? AND stage_id=?',
                                   (identifier, symbol + ':repair')).fetchone()
            self.assertIsNone(step['run_id'])
            self.assertEqual(json.loads(step['result'])['reused_stage'], symbol + ':revision')
        self.assertTrue(all(c['approved'] is False for c in value['companies']))

    def test_pending_provider_work_never_exceeds_six_reserved_slots(self):
        identifier = self.start()
        self.pending = True
        for _ in range(5):
            value = o.advance(self.db, identifier)
            self.assertEqual(value['submitted_requests'], 6)
            self.assertLessEqual(value['inflight_requests'], 6)
        self.assertEqual(sum(c[0] == 'POST' for c in self.calls), 6)
        self.assertGreater(sum(c[0] == 'GET' for c in self.calls), 0)

    def test_orphan_reservation_is_recovered_without_duplicate_or_different_request(self):
        identifier = self.start()
        original = p.reserve_task
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt('Synthetic crash after reservation commit')
        with patch.object(p, 'reserve_task', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            o.advance(self.db, identifier)
        old = dict(self.db.execute('SELECT * FROM runs').fetchone())
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM overnight_steps').fetchone()[0], 0)
        o.advance(self.db, identifier)
        mapped = self.db.execute('SELECT * FROM overnight_steps WHERE run_id=?', (old['id'],)).fetchone()
        self.assertIsNotNone(mapped)
        self.assertEqual(p.get_run(self.db, old['id'])['request'], old['request'])
        self.assertEqual([c[2] for c in self.calls if c[0] == 'POST'].count(old['id']), 1)

    def test_uncertain_post_reuses_original_id_and_exact_body(self):
        identifier = self.start()
        self.fail_posts.add('NVDA:scout')
        o.advance(self.db, identifier)
        o.advance(self.db, identifier)
        uncertain = self.db.execute("SELECT id FROM runs WHERE task_key LIKE '%:NVDA:scout'").fetchone()['id']
        first = next(c for c in self.calls if c[0] == 'POST' and c[2] == uncertain)
        self.fail_posts.clear()
        o.advance(self.db, identifier)
        attempts = [c for c in self.calls if c[0] == 'POST' and c[2] == first[2]]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs WHERE id=?', (first[2],)).fetchone()[0], 1)

    def test_deadline_reconciles_only_accepted_ids_and_retains_unknown_reservations(self):
        identifier = self.start()
        self.pending = True
        self.fail_posts.add('NVDA:scout')
        o.advance(self.db, identifier)
        o.advance(self.db, identifier)
        calls_before = len(self.calls)
        rows_before = self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        self.now = o.protocol(self.db, identifier)['deadline'] + 1
        self.pending = False
        value = o.advance(self.db, identifier)
        self.assertEqual(value['state'], 'deadline')
        self.assertTrue(all(c[0] == 'GET' for c in self.calls[calls_before:]))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], rows_before)
        self.assertEqual(value['unknown_requests'], 1)
        self.assertGreater(Decimal(value['estimated_usd']), 0)

    def test_code_drift_can_get_existing_response_but_never_buy_or_regrade(self):
        identifier = self.start()
        self.pending = True
        o.advance(self.db, identifier)
        o.advance(self.db, identifier)
        self.pending = False
        before = len(self.calls)
        with patch.object(o, 'hashes', return_value={'fixture.py': 'd' * 64}):
            value = o.advance(self.db, identifier)
        self.assertEqual(value['state'], 'needs_attention')
        self.assertTrue(all(c[0] == 'GET' for c in self.calls[before:]))
        self.assertEqual(value['submitted_requests'], 6)
        self.assertEqual(value['completed_steps'], 0)

    def test_financial_arithmetic_failure_buys_only_one_conditional_repair(self):
        self.bad_revision.add('NVDA')
        identifier = self.start()
        value = self.finish(identifier)
        self.assertEqual(value['submitted_requests'], 78)
        results = o.saved_results(self.db, identifier)
        self.assertFalse(results['NVDA:revision']['checks']['valid'])
        self.assertTrue(results['NVDA:repair']['checks']['valid'])
        self.assertEqual(results['NVDA:revision']['report']['cash_flow_bridge']['remainder'], '61')
        self.assertEqual(results['NVDA:repair']['report']['cash_flow_bridge']['remainder'], '60')

    def test_actual_prompt_code_change_still_recovers_accepted_ids_from_saved_bodies(self):
        identifier = self.start()
        self.pending = True
        o.advance(self.db, identifier)
        o.advance(self.db, identifier)
        original_rows = [dict(row) for row in self.db.execute('SELECT * FROM runs ORDER BY id')]
        self.pending = False
        before = len(self.calls)
        # Unlike changing only a reported hash, changing the request builder
        # models an actual source edit between process termination and resume.
        with patch.object(o, 'hashes', return_value={'fixture.py': 'e' * 64}), \
                patch.object(o, 'request', side_effect=AssertionError('New prompt code must not rebuild accepted work')):
            value = o.advance(self.db, identifier)
        self.assertEqual(value['state'], 'needs_attention')
        self.assertEqual(value['submitted_requests'], 6)
        self.assertEqual(value['completed_steps'], 0)
        self.assertEqual(len(self.calls) - before, 6)
        self.assertTrue(all(call[0] == 'GET' for call in self.calls[before:]))
        for row in original_rows:
            after = p.get_run(self.db, row['id'])
            self.assertEqual(after['request'], row['request'])
            self.assertEqual(after['response_id'], row['response_id'])

    def test_frozen_rates_drift_stops_admission_and_flags_attention(self):
        identifier = self.start()
        changed = deepcopy(p.TASK_PROFILES)
        changed[o.PRO]['rates']['output'] = '1.99'
        with patch.object(p, 'TASK_PROFILES', changed):
            value = o.advance(self.db, identifier)
        self.assertEqual(value['state'], 'needs_attention')
        self.assertEqual(value['submitted_requests'], 0)
        self.assertEqual(self.calls, [])

    def test_malformed_final_case_cannot_crash_or_contaminate_cross_company_context(self):
        self.malformed.update({'NVDA:revision', 'NVDA:repair'})
        identifier = self.start()
        value = self.finish(identifier)
        context = o.cross_context(o.protocol(self.db, identifier), o.saved_results(self.db, identifier))
        self.assertTrue(context['cases']['NVDA']['unavailable'])
        self.assertFalse(any(x['symbol'] == 'NVDA' for x in context['source_excerpts']))
        self.assertEqual(value['state'], 'complete')
        self.assertFalse(value['companies'][0]['revised_checks']['valid'])

    def test_judge_inputs_are_anonymous_and_counterbalanced_across_companies(self):
        identifier = self.start()
        frozen = o.protocol(self.db, identifier)
        results = {}
        for symbol in o.SYMBOLS:
            for kind, marker in [('baseline', 'FIRST_METHOD'), ('revision', 'REVISED_METHOD')]:
                report = self.case(symbol);report['headline'] = marker
                results[symbol + ':' + kind] = {'report': report, 'checks': {'valid': True}}
        for symbol in ('NVDA', 'TSM'):
            for kind in ('judge-pro', 'judge-kimi'):
                stage = next(s for s in frozen['stages'] if s['id'] == symbol + ':' + kind)
                request = o.request(stage, frozen, results)
                content = request['input'][-1]['content']
                context = json.loads(content.split('\n\n', 1)[1])
                expected = ('FIRST_METHOD', 'REVISED_METHOD') if symbol == 'NVDA' else ('REVISED_METHOD', 'FIRST_METHOD')
                self.assertEqual((context['A']['report']['headline'], context['B']['report']['headline']), expected)
                for label in ('A', 'B'):
                    self.assertFalse({'model', 'run_id', 'response_id', 'stage_id', 'reused_stage'} & context[label].keys())
                self.assertNotIn(o.PRO, content)
                self.assertNotIn(o.JUDGE, content)

    def test_terminal_missing_usage_keeps_known_spend_visible_and_unknown_held(self):
        self.unknown_usage.add('NVDA:scout')
        identifier = self.start()
        value = self.finish(identifier)
        self.assertEqual(value['unknown_requests'], 1)
        self.assertGreater(Decimal(value['estimated_usd']), 0)
        row = self.db.execute("SELECT * FROM runs WHERE task_key LIKE '%:NVDA:scout'").fetchone()
        with self.assertRaisesRegex(ValueError, 'Usage remains unknown'):
            p._settlement_facts(row)
        self.assertEqual(row['reserved_cents'], 20)

    def test_public_export_contains_only_counts_checks_and_no_private_draft_or_ids(self):
        identifier = self.start()
        self.finish(identifier)
        o.report(self.db, identifier)
        raw = (self.root / 'public/overnight-research.json').read_text()
        public = json.loads(raw)
        for secret in (identifier, 'PRIVATE_DRAFT', 'Operating cash flow 100', 'resp_', 'write_run_id', 'source_file', 'raw_if_invalid'):
            self.assertNotIn(secret, raw)
        self.assertEqual(public['completed_steps'], 86)
        self.assertTrue(all(c['approved'] is False for c in public['companies']))
        self.assertIn('PRIVATE_DRAFT', (self.root / '.data/overnight' / identifier / 'results.json').read_text())

    def test_provider_metrics_preserve_unknown_usage_and_exclude_private_payloads(self):
        self.unknown_usage.add('NVDA:scout')
        original = self.api
        def measured(*args, **kwargs):
            response = original(*args, **kwargs)
            response['metadata'] = {'supercached_input_tokens': '10',
                                    'supercache_write_input_tokens': '0',
                                    'private_note': 'PRIVATE_PROVIDER_METADATA'}
            return response
        identifier = self.start()
        with patch.object(p, 'api', side_effect=measured):
            self.finish(identifier)
        metrics = o.sail_metrics(self.db, identifier)
        self.assertEqual(sum(g['requests'] for g in metrics['models'].values()), 77)
        self.assertEqual(sum(g['known_requests'] for g in metrics['models'].values()), 76)
        self.assertEqual(sum(g['unknown_requests'] for g in metrics['models'].values()), 1)
        self.assertEqual(sum(g['input_tokens'] for g in metrics['models'].values()), 7600)
        self.assertEqual(sum(g['cached_tokens'] for g in metrics['models'].values()), 1520)
        self.assertEqual(metrics['supercache']['observed_hit_requests'], 76)
        self.assertEqual(metrics['supercache']['observed_reused_tokens'], 760)
        self.assertEqual(metrics['supercache']['new_write_requests'], 0)
        self.assertLess(Decimal(metrics['supercache']['hit_request_estimated_usd']),
                        Decimal(metrics['supercache']['same_usage_ordinary_cache_counterfactual_usd']))
        raw = json.dumps(metrics)
        for value in (identifier, 'PRIVATE_PROVIDER_METADATA', 'PRIVATE_DRAFT', 'resp_', 'source_file'):
            self.assertNotIn(value, raw)

    def test_cloud_checkpoint_has_no_resource_work_until_an_actual_final_case_exists(self):
        identifier = self.start()
        with patch.object(o.cloud, 'prepare') as prepare, patch.object(o.cloud, 'create') as create, \
                patch.object(o.cloud, 'verify') as verify:
            o.cloud_checkpoint(self.db, identifier)
        prepare.assert_not_called(); create.assert_not_called(); verify.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_cloud_checkpoint_rejects_evidence_mismatch_before_creation(self):
        identifier = self.start()
        session = o.cloud.cloud.SESSION_ROOT / ('overnight-' + identifier)
        session.mkdir(parents=True)
        state = {'phase': 'prepared', 'finished': False}
        (session / 'state.json').write_text('{}')
        cases = {'NVDA:repair': {'report': self.case('NVDA')}}
        files = {'companies/' + c['symbol'] + '.json': p.encoded(o.validators(c, self.evidence['evidence_as_of'])).encode()
                 for c in self.evidence['companies']}
        files['companies/NVDA.json'] = b'{}'
        with patch.object(o, 'saved_results', return_value=cases), \
                patch.object(o.cloud.cloud, '_load', return_value=(session, state)), \
                patch.object(o.cloud, '_bundle', return_value=files), \
                patch.object(o.cloud, 'create') as create, patch.object(o.cloud, 'verify') as verify:
            o.cloud_checkpoint(self.db, identifier)
        create.assert_not_called(); verify.assert_not_called()
        diagnostic = json.loads((self.root / '.data/overnight' / identifier / 'cloud-diagnostic.json').read_text())
        self.assertEqual(diagnostic['error_type'], 'ValueError')

    def test_cloud_verifier_failure_is_cleaned_up_and_never_auto_creates_again(self):
        identifier = self.start()
        session = o.cloud.cloud.SESSION_ROOT / ('overnight-' + identifier)
        session.mkdir(parents=True); (session / 'state.json').write_text('{}')
        state = {'phase': 'ready', 'finished': False, 'tool_receipts': {}, 'persistence_verified': False}
        cases = {'NVDA:repair': {'report': self.case('NVDA')}}
        files = {'companies/' + c['symbol'] + '.json': p.encoded(o.validators(c, self.evidence['evidence_as_of'])).encode()
                 for c in self.evidence['companies']}
        with patch.object(o, 'saved_results', return_value=cases), \
                patch.object(o.cloud.cloud, '_load', return_value=(session, state)), \
                patch.object(o.cloud, '_bundle', return_value=files), \
                patch.object(o.cloud, 'create') as create, \
                patch.object(o.cloud, 'verify', side_effect=RuntimeError('PRIVATE_ERROR_BODY')) as verify, \
                patch.object(o.cloud, 'finish') as finish:
            o.cloud_checkpoint(self.db, identifier)
            o.cloud_checkpoint(self.db, identifier)
        create.assert_not_called(); verify.assert_called_once(); finish.assert_called_once()
        diagnostic = (self.root / '.data/overnight' / identifier / 'cloud-diagnostic.json').read_text()
        self.assertNotIn('PRIVATE_ERROR_BODY', diagnostic)
        self.assertEqual(json.loads(diagnostic)['error_type'], 'RuntimeError')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_cloud_cleanup_remains_allowed_after_inference_deadline(self):
        identifier = self.start()
        session = o.cloud.cloud.SESSION_ROOT / ('overnight-' + identifier)
        session.mkdir(parents=True); (session / 'state.json').write_text('{}')
        self.now = o.protocol(self.db, identifier)['deadline'] + 10
        with patch.object(o.cloud.cloud, '_load', return_value=(session, {'phase': 'ready', 'finished': False})), \
                patch.object(o.cloud, 'finish') as finish, patch.object(o.cloud, 'create') as create:
            o.cloud_checkpoint(self.db, identifier, finish=True)
        finish.assert_called_once_with(session); create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
