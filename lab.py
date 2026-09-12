"""One financial extraction, with an inspectable request and persistent budget.

Standard library only. Read lessons/01-first-experiment.md before running.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import time
import uuid
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

from sail_tracking import inference_headers

ROOT = Path(__file__).resolve().parent
MODEL = 'deepseek-ai/DeepSeek-V4-Flash-0731'
RATES = {'input': '0.09', 'cached': '0.02', 'output': '0.18'}
PRICING_DATE = '2026-09-12'
BUDGET_CENTS = 100
RESERVE_CENTS = 1
TERMINAL = {'completed', 'incomplete', 'failed', 'cancelled'}


def fixture():
    return json.loads((ROOT / 'data/msft-2025.json').read_text())


def build_request(case):
    # Answers stay in the local evaluator. Only names and source data go to Sail.
    fact_schema = {'type': 'object', 'additionalProperties': False,
                   'properties': {'value': {'type': 'number'}, 'currency': {'type': 'string'},
                                  'unit': {'type': 'string'}, 'period_end': {'type': 'string'},
                                  'evidence': {'type': 'string'}},
                   'required': ['value', 'currency', 'unit', 'period_end', 'evidence']}
    schema = {'type': 'object', 'additionalProperties': False,
              'properties': {name: fact_schema for name in case['expected']},
              'required': list(case['expected'])}
    prompt = ('Extract the five requested metrics for the fiscal year ended June 30, 2025. '
              'Use only the source below. Keep values in their reported units: currency USD, '
              'unit millions, period_end YYYY-MM-DD. Gross margin here is an amount, not a percentage. '
              'For each metric, copy its entire source data row exactly into evidence. '
              'Return only the requested JSON.\n\nSOURCE:\n' + case['passage'])
    return {'model': MODEL, 'input': prompt, 'max_output_tokens': 2048,
            'background': False, 'metadata': {'completion_window': 'asap'},
            'text': {'format': {'type': 'json_schema', 'name': 'financial_facts',
                                'strict': True, 'schema': schema}}}


def estimate_cost(usage, rates=RATES):
    """USD estimate. Cached input is already part of input, not extra tokens."""
    if not isinstance(usage, dict) or not isinstance(usage.get('input_tokens_details') or {}, dict):
        raise ValueError('Missing or inconsistent token accounting')
    i, o = usage.get('input_tokens'), usage.get('output_tokens')
    c = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
    if any(type(v) is not int or v < 0 for v in (i, o, c)) or c > i:
        raise ValueError('Missing or inconsistent token accounting')
    return ((i-c)*Decimal(rates['input']) + c*Decimal(rates['cached']) +
            o*Decimal(rates['output'])) / Decimal(1_000_000)


def grade(answer, case):
    result = {}
    for name, expected in case['expected'].items():
        actual = answer.get(name) if isinstance(answer, dict) else None
        if not isinstance(actual, dict):
            result[name] = {'passed': False, 'errors': ['missing fact']}
            continue
        errors = []
        value = actual.get('value')
        if type(value) not in (int, float) or value != expected:
            errors.append('value')
        for field, wanted in [('currency', 'USD'), ('unit', 'millions'), ('period_end', case['period']),
                              ('evidence', case['evidence_rows'][name])]:
            if actual.get(field) != wanted:
                errors.append(field)
        result[name] = {'passed': not errors, 'errors': errors}
    return result


def database(path=None):
    location = path or ROOT / '.data/runs.sqlite'
    location.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(location, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY, created REAL NOT NULL, reserved_cents INTEGER NOT NULL,
        request TEXT NOT NULL, case_json TEXT NOT NULL, prediction TEXT NOT NULL,
        rates TEXT NOT NULL, pricing_date TEXT NOT NULL,
        response_id TEXT, response TEXT, observed_seconds REAL, error TEXT)''')
    return db


def reserve(db, body, case, prediction):
    encoded = json.dumps(body, sort_keys=True)
    # Fixed model/output cap and a small request envelope bound this v1 workload.
    # The one-cent allowance is deliberately larger than its list-price estimate.
    if len(encoded.encode()) > 8000 or body['model'] != MODEL or body['max_output_tokens'] != 2048:
        raise ValueError('Request outside the v1 spending envelope')
    run_id = str(uuid.uuid4())
    with db:
        db.execute('BEGIN IMMEDIATE')
        held = db.execute('SELECT COALESCE(SUM(reserved_cents),0) FROM runs').fetchone()[0]
        if held + RESERVE_CENTS > BUDGET_CENTS:
            raise ValueError('Local $1 budget exhausted; no request submitted')
        db.execute('INSERT INTO runs(id,created,reserved_cents,request,case_json,prediction,rates,pricing_date) VALUES(?,?,?,?,?,?,?,?)',
                   (run_id, time.time(), RESERVE_CENTS, encoded, json.dumps(case), prediction,
                    json.dumps(RATES), PRICING_DATE))
    return run_id


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_api_key():
    path = ROOT / '.env'
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('Expected an owner-readable regular .env file')
    keys = [s.partition('=')[2] for s in path.read_text().splitlines() if s.startswith('SAIL_API_KEY=')]
    if len(keys) != 1 or not keys[0]:
        raise ValueError('Missing SAIL_API_KEY')
    return keys[0]


def api(method, route, body=None, request_id=None, expected_key_fingerprint=None):
    key = load_api_key()
    if (expected_key_fingerprint is not None and
            hashlib.sha256(key.encode()).hexdigest() != expected_key_fingerprint):
        raise ValueError('Sail credential changed; refusing ambiguous submission under a different key')
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    if request_id:
        headers['Idempotency-Key'] = request_id
    if route == '/v1/responses' or route.startswith('/v1/responses/'):
        headers.update(inference_headers())
    payload = json.dumps(body, sort_keys=True).encode() if body is not None else None
    req = Request('https://api.sailresearch.com' + route, data=payload, headers=headers, method=method)
    try:
        with build_opener(NoRedirect).open(req, timeout=30) as response:
            return json.loads(response.read(2_000_000))
    except HTTPError as error:
        # Do not print raw provider responses, headers, or credentials.
        raise RuntimeError(f'HTTP {error.code}; submission may need reconciliation. No automatic retry.') from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError('Network or response error; no automatic retry. Reservation retained.') from None


def preflight():
    models = api('GET', '/v1/models')
    if MODEL not in {m['id'] for m in models.get('data', [])}:
        raise ValueError('Configured model is not listed')
    summary = api('GET', '/v2/usage/summary?range=period')
    balance = summary.get('balance')
    if (summary.get('available') is not True or summary.get('has_metronome_customer') is not True or
        summary.get('balance_unavailable') is not False or type(balance) not in (int, float) or
        not Decimal(str(balance)).is_finite() or balance < RESERVE_CENTS):
        raise ValueError('Could not confirm sufficient reported credit')


def execute(db, run_id):
    row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown run ID')
    prior = json.loads(row['response']) if row['response'] else {}
    if prior.get('status') in TERMINAL:
        return report(db, run_id)
    try:
        if row['response_id']:
            result = api('GET', '/v1/responses/' + row['response_id'])
        else:
            if time.time() - row['created'] > 23*3600:
                raise ValueError('Uncertain submission older than 23h. Reconcile manually; refusing to resubmit.')
            result = api('POST', '/v1/responses', json.loads(row['request']), run_id)
        deadline = time.monotonic() + 45
        while True:
            response_id = result.get('id')
            if not isinstance(response_id, str) or not response_id.startswith('resp_') or '/' in response_id:
                raise ValueError('Unexpected response ID; reservation retained')
            with db:
                db.execute('UPDATE runs SET response_id=?, response=?, observed_seconds=?, error=NULL WHERE id=?',
                           (response_id, json.dumps(result), time.time()-row['created'], run_id))
            if result.get('status') in TERMINAL or time.monotonic() >= deadline:
                break
            time.sleep(3)
            result = api('GET', '/v1/responses/' + response_id)
    except (RuntimeError, ValueError) as error:
        with db:
            db.execute('UPDATE runs SET error=? WHERE id=?', (str(error), run_id))
        print(str(error))
    report(db, run_id)


def report(db, run_id):
    row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown run ID')
    response = json.loads(row['response'] or '{}')
    content = ''.join(part.get('text', '') for item in (response.get('output') or [])
                      if isinstance(item, dict) for part in (item.get('content') or [])
                      if isinstance(part, dict) and part.get('type') == 'output_text')
    try:
        answer = json.loads(content)
    except ValueError:
        answer = None
    grades = grade(answer, json.loads(row['case_json']))
    passed = sum(g['passed'] for g in grades.values())
    try:
        cost = str(estimate_cost(response.get('usage') or {}, json.loads(row['rates'])))
    except ValueError:
        cost = None
    result = {'run_id': run_id, 'model': json.loads(row['request'])['model'],
              'status': response.get('status', 'submission_unconfirmed'),
              'prediction': row['prediction'], 'answer': answer, 'grades': grades,
              'facts_passed': passed, 'facts_total': len(grades),
              'successful_task': passed == len(grades) and response.get('status') == 'completed',
              'estimated_usd': cost, 'usage': response.get('usage'),
              'observed_wall_seconds': row['observed_seconds'],
              'timing_note': 'Includes queueing, network, polling and any pause before resume; not GPU execution time.',
              'pricing_date': row['pricing_date'],
              'source_url': json.loads(row['case_json'])['source_url'],
              'request_sha256': hashlib.sha256(row['request'].encode()).hexdigest(),
              'error': row['error']}
    (ROOT / '.data' / f'{run_id}.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    if result['status'] not in TERMINAL:
        print(f'Resume this same run: python3 lab.py resume {run_id}')
    print('Cost is a list-price estimate, not a settled invoice. One-cent allowance remains held.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('preview', help='Show exactly what the model sees; no API calls')
    run = sub.add_parser('run', help='Submit one paid trial within the local budget')
    run.add_argument('--prediction', required=True, help='Your expectation, recorded before the result')
    for command in ['resume', 'report']:
        sub.add_parser(command).add_argument('run_id')
    args = parser.parse_args()
    case = fixture()
    if args.command == 'preview':
        print(json.dumps(build_request(case), indent=2))
        print('No API calls. One live run holds $0.01 against the $1 local budget.')
        return
    with database() as db:
        if args.command == 'run':
            preflight()
            run_id = reserve(db, build_request(case), case, args.prediction)
            print('Reserved trial:', run_id, flush=True)
            execute(db, run_id)
        elif args.command == 'resume':
            execute(db, args.run_id)
        else:
            report(db, args.run_id)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
