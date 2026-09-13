"""Offline financial research and disk-recovery proof, executed inside a clean VM."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import portfolio as ledger
import research_eval as evaluation
import research_sources as sources

TEST_FILES = ('test_evidence_packet.py', 'test_lab.py', 'test_portfolio.py',
              'test_research_tasks.py', 'test_research_sources.py',
              'test_research_eval.py', 'test_investigator.py', 'test_sail_tracking.py')


def write(name, value):
    path = ROOT / '.proof' / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    return value


def integrity():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for item in manifest['files']:
        data = (ROOT / item['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != item['sha256'] or len(data) != item['bytes']:
            raise ValueError('Uploaded bundle integrity check failed')
    if (ROOT / '.env').exists() or any(name in os.environ for name in (
            'SAIL_API_KEY', 'SCHWAB_APP_KEY', 'SCHWAB_APP_SECRET', 'SCHWAB_TOKEN_PATH')):
        raise ValueError('Offline validation must run without application credentials')
    return hashlib.sha256((ROOT / 'manifest.json').read_bytes()).hexdigest()


def seed():
    manifest_hash = integrity()
    suite = unittest.TestSuite()
    for filename in TEST_FILES:
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=filename))
    output = io.StringIO()
    checked = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
    test_result = {'tests': checked.testsRun, 'failures': len(checked.failures),
                   'errors': len(checked.errors), 'skipped': len(checked.skipped)}
    if not checked.wasSuccessful():
        write('test-failures.json', {'summary': test_result,
                                    'failed_tests': [str(test) for test, _ in checked.failures + checked.errors]})
        raise ValueError('Offline research regression suite failed')
    packet = ledger.load_packet()
    frozen = {}
    for source_id in sources.SOURCE_REGISTRY:
        frozen[source_id] = sources.validate_snapshot(json.loads(
            (ROOT / 'data/sandbox-sources' / (source_id + '.json')).read_text()), '2026-09-12')
    calculation = sources.dispatch('calculate', {'operation': 'subtract', 'left_id': 'ocf-2026',
                                                  'right_id': 'ppe-2026'}, packet, frozen)
    expected = next(fact['value'] for fact in packet['facts'] if fact['id'] == 'cash-after-ppe-2026')
    if calculation['value'] != str(expected):
        raise ValueError('Cash flow calculation diverged from checked evidence')
    passage = sources.dispatch('read_source', {'source_id': 'fy26-call', 'query': 'estimated useful lives'},
                               packet, frozen, '2026-09-12')
    if not passage['matched']:
        raise ValueError('Frozen primary-source passage could not be retrieved')
    cases = evaluation.load_cases()
    oracle_results = [evaluation.grade({'verdict': case['expected']['verdict'],
                                       'evidence_ids': sorted({group[0] for group in
                                                              case['expected']['required_evidence_groups']}),
                                       'reason': 'Synthetic oracle checks the local grader only.'}, case)
                      for case in cases]
    if not all(result['passed'] for result in oracle_results):
        raise ValueError('Frozen evaluation grader contract failed')
    database = ROOT / '.proof/resume.sqlite'
    with ledger.database(database) as db:
        body = ledger.build_task_request('deepseek-ai/DeepSeek-V4-Flash-0731', 'Synthetic restart proof')
        run_id = ledger.reserve_task(db, body, packet, 'sandbox:resume:0', 'investigate')
        db.execute('UPDATE runs SET response_id=?,response=? WHERE id=?',
                   ('resp_sandbox_known', ledger.encoded({'id': 'resp_sandbox_known', 'status': 'queued'}), run_id))
        db.commit()
        row = ledger.get_run(db, run_id)
        state = {'run_id': run_id, 'request_sha256': hashlib.sha256(row['request'].encode()).hexdigest(),
                 'packet_sha256': row['packet_sha256'], 'response_id': row['response_id']}
    return write('seed.json', {'manifest_sha256': manifest_hash, 'tests': test_result,
                               'calculation': calculation, 'oracle_cases_passed': len(oracle_results),
                               'primary_passage_count': len(passage['passages']),
                               'source_hashes': {key: value['sha256'] for key, value in frozen.items()},
                               'resume_state': state})


def verify():
    manifest_hash = integrity()
    before = json.loads((ROOT / '.proof/seed.json').read_text())
    if manifest_hash != before['manifest_sha256']:
        raise ValueError('Bundle changed across VM lifecycle')
    calls = []
    def retrieve(method, route, *args, **kwargs):
        calls.append((method, route))
        if method != 'GET' or route != '/v1/responses/resp_sandbox_known':
            raise AssertionError('Recovery attempted a new paid submission')
        return {'id': 'resp_sandbox_known', 'status': 'completed', 'output': [],
                'usage': {'input_tokens': 0, 'output_tokens': 0}}
    with ledger.database(ROOT / '.proof/resume.sqlite') as db:
        row = ledger.get_run(db, before['resume_state']['run_id'])
        for key in ('packet_sha256', 'response_id'):
            if row[key] != before['resume_state'][key]:
                raise ValueError('Durable response/evidence state changed')
        if hashlib.sha256(row['request'].encode()).hexdigest() != before['resume_state']['request_sha256']:
            raise ValueError('Durable request changed')
        repeat_id = ledger.reserve_task(db, json.loads(row['request']), json.loads(row['packet_json']),
                                        'sandbox:resume:0', 'investigate')
        with patch.object(ledger, 'api', side_effect=retrieve):
            ledger.execute(db, repeat_id, poll_seconds=0)
            ledger.execute(db, repeat_id, poll_seconds=0)
        count = db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        if calls != [('GET', '/v1/responses/resp_sandbox_known')] or count != 1:
            raise ValueError('Restart did not preserve exactly one research step')
    return write('verified.json', {'manifest_sha256': manifest_hash, 'test_summary': before['tests'],
                                   'source_hashes_preserved': True, 'request_and_response_preserved': True,
                                   'reservations': count, 'retrievals': len(calls), 'new_submissions': 0,
                                   'fresh_process_recovery': True})


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'seed', 'verify'}:
        raise SystemExit('Expected seed or verify')
    result = seed() if sys.argv[1] == 'seed' else verify()
    print(json.dumps({'phase': sys.argv[1], 'passed': True,
                      'manifest_sha256': result['manifest_sha256']}, sort_keys=True))
