import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

from portfolio_runtime.journal import export_records, public_record, publish_journal
from portfolio_runtime.provider import ClosingConnection


def fixture():
    facts, claims = {}, []
    for name, value in [('assets', 100), ('cash', 20), ('debt', 10)]:
        facts[name] = [{'tag': name.title(), 'unit': 'USD', 'observations': [{'end': '2026-06-30', 'val': value, 'accn': '0001234567-26-000001', 'form': '10-Q'}]}]
        claims.append({'symbol': 'TEST', 'metric': name, 'tag': name.title(), 'start': None, 'end': '2026-06-30', 'value': value, 'unit': 'USD'})
    company = {'symbol': 'TEST', 'cik': '0001234567', 'facts': facts}
    result = {'thesis': 'Cash exceeds debt. Valuation remains uncertain.', 'claims': claims, 'questions': [{'symbol': 'TEST', 'question': 'What valuation supports an investment?', 'priority': 5}], 'targets': [], 'confidence': 'medium', 'abstain_reason': None}
    task = {'id': 'w01-company-TEST', 'kind': 'company', 'symbol': 'TEST', 'profile': 'kimi_flex', 'status': 'complete', 'result': json.dumps(result), 'grade': json.dumps({'source_check_passed': True, 'claims_checked': 3, 'errors': []})}
    request = {'status': 'completed', 'created': 1789290000.123, 'updated': 1789290123.456, 'cost': '0.0123'}
    return task, request, {'TEST': company}


class JournalTests(unittest.TestCase):
    def test_only_final_fields_exact_filing_sources_and_observed_timestamps(self):
        task, request, companies = fixture()
        task['body'] = 'NEVER PUBLIC PRIVATE PROMPT'
        request['response'] = 'NEVER PUBLIC INTERNAL REASONING'
        record = public_record(task, request, companies, run_id='run-one')
        self.assertEqual(record['outcome'], 'passed')
        self.assertEqual(record['metrics']['latency_seconds'], 123.333)
        self.assertEqual(record['claims'][0]['source']['url'], 'https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/0001234567-26-000001-index.html')
        self.assertNotIn('NEVER PUBLIC', json.dumps(record))
        self.assertEqual(record['id'], public_record(task, request, companies, run_id='run-one')['id'])
        self.assertNotEqual(record['id'], public_record(task, request, companies, run_id='run-two')['id'])

    def test_rechecks_facts_even_if_stored_grade_claims_passed(self):
        task, request, companies = fixture()
        result = json.loads(task['result']); result['claims'][0]['value'] = 999
        task['result'] = json.dumps(result)
        record = public_record(task, request, companies, run_id='run')
        self.assertEqual(record['outcome'], 'unverified')
        self.assertIsNone(record['case']); self.assertEqual(record['claims'], [])

    def test_unknown_fields_sensitive_text_and_failed_requests_never_leak_prose(self):
        for mutation in [lambda x: x.update(reasoning='private'), lambda x: x.update(thesis='Bearer sensitive-secret'), lambda x: x.update(thesis='Email private@example.com'), lambda x: x.update(thesis='<script>danger</script>')]:
            task, request, companies = fixture(); result = json.loads(task['result']); mutation(result); task['result'] = json.dumps(result)
            record = public_record(task, request, companies, run_id='run')
            self.assertEqual(record['outcome'], 'unverified'); self.assertIsNone(record['case'])
        task, request, companies = fixture(); request['status'] = 'failed'
        record = public_record(task, request, companies, run_id='run')
        self.assertEqual(record['outcome'], 'failed'); self.assertIsNone(record['case'])

    def test_operational_cache_write_and_inflight_requests_are_not_findings(self):
        task, request, companies = fixture(); request['status'] = 'running'
        self.assertIsNone(public_record(task, request, companies, run_id='run'))
        request['status'] = 'completed'; task['kind'] = 'cache_write'
        self.assertIsNone(public_record(task, request, companies, run_id='run'))

    def test_unsettled_terminal_record_waits_for_final_cost_and_observed_timestamp(self):
        task, request, companies = fixture()
        for status in ['completed', 'failed']:
            request['status'], request['cost'] = status, None
            self.assertIsNone(public_record(task, request, companies, run_id='run'))
            request['cost'], request['updated'] = '0.015', 1789290150.0
            record = public_record(task, request, companies, run_id='run')
            self.assertEqual(record['metrics']['cost_usd'], '0.015')
            self.assertEqual(record['metrics']['latency_seconds'], 149.877)

    def test_publication_retries_exact_records_and_marks_receipts_only_after_acceptance(self):
        task, request, companies = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); rp, qp = root / 'research.sqlite', root / 'requests.sqlite'
            with sqlite3.connect(rp, factory=ClosingConnection) as db:
                db.execute('CREATE TABLE tasks(id,kind,symbol,profile,status,result,grade,created)')
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)', (*[task[k] for k in ['id','kind','symbol','profile','status','result','grade']], request['created']))
            with sqlite3.connect(qp, factory=ClosingConnection) as db:
                db.execute('CREATE TABLE requests(task_id,status,created,updated,cost)')
                db.execute('INSERT INTO requests VALUES(?,?,?,?,?)', (task['id'], *[request[k] for k in ['status','created','updated','cost']]))
            evidence = {'companies': list(companies.values())}
            self.assertEqual(len(list(export_records(rp, qp, evidence, run_id='test-run'))), 1)
            # Partial consumption must release both read-only DB handles too.
            actual_connect, connections = sqlite3.connect, []
            def observed_connect(*args, **kwargs):
                connection = actual_connect(*args, **kwargs)
                connections.append(connection)
                return connection
            with patch('portfolio_runtime.journal.sqlite3.connect', side_effect=observed_connect):
                stream = export_records(rp, qp, evidence, run_id='test-run')
                next(stream)
                stream.close()
            self.assertEqual(len(connections), 2)
            for connection in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute('SELECT 1')
            research, client = types.SimpleNamespace(path=rp,evidence=evidence), types.SimpleNamespace(path=qp)
            config = {'run_id': 'test-run', 'state_dir': directory, 'publish_url': 'https://blakewoods.us/api/portfolio/state', 'injected_auth': True}
            requests = []
            class Opener:
                fail = True
                def open(self, req, timeout):
                    requests.append(req.data)
                    if self.fail: raise RuntimeError('PRIVATE TRANSPORT DETAILS')
                    return Response()
            class Response:
                status = 200
                def __enter__(self): return self
                def __exit__(self, *args): pass
            opener = Opener()
            with sqlite3.connect(qp, factory=ClosingConnection) as db:
                db.execute('UPDATE requests SET cost=NULL')
            self.assertEqual(publish_journal(config, research, client, opener=opener), {'published': 0, 'pending': 0, 'error': None})
            self.assertEqual(requests, [])
            with sqlite3.connect(qp, factory=ClosingConnection) as db:
                db.execute('UPDATE requests SET cost=?,updated=?', ('0.02', request['updated'] + 5))
            self.assertEqual(publish_journal(config, research, client, opener=opener)['error'], 'publication_unconfirmed')
            opener.fail = False
            self.assertEqual(publish_journal(config, research, client, opener=opener), {'published': 1, 'pending': 0, 'error': None})
            self.assertEqual(requests[0], requests[1])
            self.assertEqual(json.loads(requests[1])['entries'][0]['metrics']['cost_usd'], '0.02')
            self.assertEqual(publish_journal(config, research, client, opener=opener)['published'], 0)
            self.assertEqual(len(requests), 2)
            self.assertEqual((root / 'journal-publications.sqlite').stat().st_mode & 0o077, 0)


if __name__ == '__main__':
    unittest.main()
