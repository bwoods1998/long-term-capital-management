"""Bounded evidence-critic prompt selection, using the shared Sail request ledger.

A champion is a prompt for this narrow critic contract, not a reviewed financial
finding. Synthetic authored validation is one-use, public, and not proof of
investment skill or general agent improvement. No code edits or publication.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

import portfolio as p
import research_eval as evaluation

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/research/improvement'
MODELS = ('deepseek-ai/DeepSeek-V4-Pro-0813', 'deepseek-ai/DeepSeek-V4-Flash-0731')
DEFAULT_MODEL = MODELS[1]
MAX_CENTS = 700
MAX_INFLIGHT = 4
PROPOSAL_POLICY = 'single-json-envelope-v1'
NAMESPACE = uuid.UUID('d0f6d22e-3527-4487-932a-a16a7ee333f5')
GENERATOR = '''Improve the supplied evidence-critic system prompt using only the
provided synthetic DEVELOPMENT cases and baseline results. Preserve the verdict
meanings, source-only evidence boundary, publication cutoff, and strict output
JSON contract. Favor transferable decision checks over memorized case names,
IDs or numbers. Do not add browsing, tools, outside knowledge, or new abilities.
Validation cases and answers are not supplied. Return only one JSON object with
exactly one field: {"prompt":"complete revised system prompt"}. The prompt must
be nonempty and at most 12000 characters. No markdown fences or commentary.'''


def initialize(db):
    if db.in_transaction:
        raise ValueError('Use a connection without an active transaction')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS improvement_prompts (sha256 TEXT PRIMARY KEY, text TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS improvement_events (id INTEGER PRIMARY KEY, created REAL NOT NULL,
        kind TEXT NOT NULL, prompt_sha256 TEXT NOT NULL REFERENCES improvement_prompts(sha256),
        previous_sha256 TEXT, payload_json TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE);
      CREATE TABLE IF NOT EXISTS improvement_head (id INTEGER PRIMARY KEY CHECK(id=1),
        event_id INTEGER NOT NULL REFERENCES improvement_events(id), prompt_sha256 TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS improvement_cycles (id TEXT PRIMARY KEY, job_key TEXT NOT NULL UNIQUE,
        created REAL NOT NULL, inputs_sha256 TEXT NOT NULL, validation_signature TEXT NOT NULL UNIQUE,
        protocol_json TEXT NOT NULL, protocol_sha256 TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS improvement_candidates (cycle_id TEXT PRIMARY KEY REFERENCES improvement_cycles(id),
        prompt_sha256 TEXT NOT NULL REFERENCES improvement_prompts(sha256), origin TEXT NOT NULL,
        proposal_run_id TEXT REFERENCES runs(id), created REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS improvement_requests (cycle_id TEXT NOT NULL REFERENCES improvement_cycles(id),
        ordinal INTEGER NOT NULL, stage TEXT NOT NULL, split TEXT, case_id TEXT, arm TEXT,
        task_key TEXT NOT NULL UNIQUE, request_json TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        PRIMARY KEY(cycle_id,ordinal));
      CREATE TABLE IF NOT EXISTS improvement_observations (cycle_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
        run_id TEXT NOT NULL UNIQUE REFERENCES runs(id), response_sha256 TEXT NOT NULL,
        grade_json TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(cycle_id,ordinal),
        FOREIGN KEY(cycle_id,ordinal) REFERENCES improvement_requests(cycle_id,ordinal));
      CREATE TABLE IF NOT EXISTS improvement_decisions (cycle_id TEXT PRIMARY KEY REFERENCES improvement_cycles(id),
        created REAL NOT NULL, receipt_json TEXT NOT NULL, sha256 TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS improvement_closures (cycle_id TEXT PRIMARY KEY REFERENCES improvement_cycles(id),
        reason TEXT NOT NULL, created REAL NOT NULL);
    ''')
    for table in ('prompts', 'events', 'cycles', 'candidates', 'requests', 'observations', 'decisions', 'closures'):
        for action in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS improvement_{table}_no_{action.lower()}
                BEFORE {action} ON improvement_{table} BEGIN SELECT RAISE(ABORT,'Improvement history is immutable'); END''')
    db.commit()


@contextmanager
def lock(db):
    path = db.execute('PRAGMA database_list').fetchone()['file']
    if not path:
        raise ValueError('A persistent shared ledger is required')
    descriptor = os.open(path + '.self-improve.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another improvement controller owns the ledger') from None
        yield
    finally:
        os.close(descriptor)


def _time(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise ValueError('Deadline must be an exact UTC timestamp')
    try:
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('Invalid UTC timestamp') from None
    return at.timestamp()


def _code_hash():
    return p.digest({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                     for name in ('self_improve.py', 'research_eval.py')})


def _prompt(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 12000:
        raise ValueError('Prompt must be nonempty and at most12000 characters')
    return value


def _store_prompt(db, value):
    value = _prompt(value)
    sha = p.digest(value)
    db.execute('INSERT OR IGNORE INTO improvement_prompts VALUES(?,?)', (sha, value))
    if db.execute('SELECT text FROM improvement_prompts WHERE sha256=?', (sha,)).fetchone()[0] != value:
        raise ValueError('Prompt hash collision')
    return sha


def _event(db, kind, prompt_sha, payload):
    last = db.execute('SELECT sha256 FROM improvement_events ORDER BY id DESC LIMIT 1').fetchone()
    previous = last[0] if last else None
    body = {'created': time.time(), 'kind': kind, 'prompt_sha256': prompt_sha,
            'previous_sha256': previous, 'payload': payload}
    seq = db.execute('INSERT INTO improvement_events(created,kind,prompt_sha256,previous_sha256,payload_json,sha256) VALUES(?,?,?,?,?,?)',
        (body['created'], kind, prompt_sha, previous, p.encoded(payload), p.digest(body))).lastrowid
    db.execute('INSERT INTO improvement_head VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET event_id=excluded.event_id,prompt_sha256=excluded.prompt_sha256', (seq, prompt_sha))
    return seq


def champion(db):
    """Verify the append-only event chain and its current pointer without changing it."""
    previous = None
    last = None
    for row in db.execute('SELECT * FROM improvement_events ORDER BY id'):
        body = {'created': row['created'], 'kind': row['kind'], 'prompt_sha256': row['prompt_sha256'],
                'previous_sha256': row['previous_sha256'], 'payload': json.loads(row['payload_json'])}
        if row['previous_sha256'] != previous or p.digest(body) != row['sha256']:
            raise ValueError('Champion history hash mismatch')
        previous, last = row['sha256'], row
    pointer = db.execute('SELECT * FROM improvement_head WHERE id=1').fetchone()
    if last is None:
        if pointer:
            raise ValueError('Champion pointer lacks history')
        return None
    if not pointer or pointer['event_id'] != last['id'] or pointer['prompt_sha256'] != last['prompt_sha256']:
        raise ValueError('Champion pointer differs from immutable history')
    prompt = db.execute('SELECT text FROM improvement_prompts WHERE sha256=?', (last['prompt_sha256'],)).fetchone()
    if not prompt or p.digest(prompt[0]) != last['prompt_sha256']:
        raise ValueError('Champion prompt hash mismatch')
    return {'event_id': last['id'], 'sha256': last['prompt_sha256'], 'prompt': prompt[0]}


def _fingerprint(case):
    return p.digest({'claim': case['claim'], 'as_of': case['as_of'],
                     'evidence': sorted((x['text'], x['published_at']) for x in case['evidence'])})


def load_suites(development=DATA / 'development.json', validation=DATA / 'validation.json'):
    suites = {'development': evaluation.load_cases(development), 'validation': evaluation.load_cases(validation)}
    if any(len(rows) != 8 for rows in suites.values()):
        raise ValueError('This protocol requires exactly8 development and8 validation cases')
    ids = [row['id'] for rows in suites.values() for row in rows]
    fingerprints = [_fingerprint(row) for rows in suites.values() for row in rows]
    old = evaluation.load_cases()
    if len(set(ids)) != 16 or len(set(fingerprints)) != 16 or set(fingerprints) & {_fingerprint(c) for c in old}:
        raise ValueError('Development, validation and old regression examples must be distinct')
    dev_evidence = {x['text'] for c in suites['development'] for x in c['evidence']}
    if dev_evidence & {x['text'] for c in suites['validation'] for x in c['evidence']}:
        raise ValueError('Validation cannot reuse development evidence')
    return suites


def _packet(identifier):
    return p.validate_packet({'schema_version': 1, 'id': 'synthetic-prompt-improvement',
        'symbol': 'SYNTHETIC', 'company': 'Fictional improvement fixtures',
        'question': 'Does a bounded critic prompt improve on separate authored validation cases?',
        'evidence_as_of': '2026-06-30',
        'sources': [{'id': 'protocol', 'title': 'Authored synthetic prompt-selection protocol',
                     'url': 'https://example.invalid/synthetic/improvement', 'published_at': '2026-06-30'}],
        'facts': [{'id': 'version', 'label': 'Protocol version', 'value': 1, 'unit': 'version', 'period': '2026', 'source_id': 'protocol'}],
        'context': [{'id': 'binding', 'text': 'Synthetic critic protocol: ' + identifier, 'source_id': 'protocol'}]})


def start(db, key, deadline, model=DEFAULT_MODEL, candidate_prompt=None,
          development=DATA / 'development.json', validation=DATA / 'validation.json'):
    initialize(db)
    if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', key) or model not in MODELS:
        raise ValueError('Use a stable short job key and an approved model')
    suites = load_suites(development, validation)
    inputs = {'deadline': deadline, 'model': model, 'suites': suites,
              'candidate_prompt': _prompt(candidate_prompt) if candidate_prompt is not None else None}
    end = _time(deadline)
    with lock(db), db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM improvement_cycles WHERE job_key=?', (key,)).fetchone()
        if existing:
            if existing['inputs_sha256'] != p.digest(inputs):
                raise ValueError('Job key collision: frozen inputs changed')
            return existing['id']
        if end <= time.time():
            raise ValueError('Use a future deadline')
        current = champion(db)
        if not current:
            sha = _store_prompt(db, evaluation.SYSTEM_PROMPT)
            _event(db, 'initialize', sha, {'scope': 'evidence_critic', 'baseline': 'research_eval.SYSTEM_PROMPT'})
            current = champion(db)
        profile = p.validate_task_envelope(p.build_task_request(model, evaluation.build_case_input(suites['development'][0])))
        maximum = (32 + int(candidate_prompt is None)) * profile['reserve_cents']
        if maximum > MAX_CENTS:
            raise ValueError('Profile exceeds the bounded seven-dollar protocol')
        identifier = str(uuid.uuid5(NAMESPACE, key))
        protocol = {'schema_version': 1, 'synthetic': True, 'inputs': inputs,
                    'baseline': current, 'profile': profile, 'implementation_sha256': _code_hash(),
                    'generator': GENERATOR, 'proposal_policy': PROPOSAL_POLICY,
                    'max_calls': 33 if candidate_prompt is None else 32,
                    'max_cents': maximum, 'max_inflight': MAX_INFLIGHT, 'packet': _packet(identifier)}
        signature = p.digest(sorted(_fingerprint(c) for c in suites['validation']))
        proposed_cases = {_fingerprint(c) for c in suites['validation']}
        for prior in db.execute('SELECT protocol_json FROM improvement_cycles'):
            consumed = {_fingerprint(c) for c in json.loads(prior[0])['inputs']['suites']['validation']}
            if proposed_cases & consumed:
                raise ValueError('Validation cases already consumed; author a genuinely fresh suite before another candidate')
        db.execute('INSERT INTO improvement_cycles VALUES(?,?,?,?,?,?,?)',
            (identifier, key, time.time(), p.digest(inputs), signature, p.encoded(protocol), p.digest(protocol)))
        if candidate_prompt is not None:
            sha = _store_prompt(db, candidate_prompt)
            db.execute('INSERT INTO improvement_candidates VALUES(?,?,?,?,?)', (identifier, sha, 'explicit', None, time.time()))
        return identifier


def _cycle(db, identifier):
    row = db.execute('SELECT * FROM improvement_cycles WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise ValueError('Unknown improvement cycle')
    protocol = json.loads(row['protocol_json'])
    if p.digest(protocol) != row['protocol_sha256']:
        raise ValueError('Frozen protocol hash mismatch')
    return protocol


def _candidate(db, identifier):
    row = db.execute('SELECT p.* FROM improvement_candidates c JOIN improvement_prompts p ON p.sha256=c.prompt_sha256 WHERE c.cycle_id=?', (identifier,)).fetchone()
    if row and p.digest(row['text']) != row['sha256']:
        raise ValueError('Candidate prompt hash mismatch')
    return row['text'] if row else None


def _content(response):
    return ''.join(part.get('text', '') for item in response.get('output', []) if isinstance(item, dict)
                   for part in item.get('content', []) if isinstance(part, dict) and part.get('type') == 'output_text')


def _proposal(value):
    """Accept one complete JSON object, optionally inside one exact fence."""
    value = value.strip()
    wrapper = re.fullmatch(r'```(?:json)?\r?\n([\s\S]*?)\r?\n```', value)
    if wrapper:
        value = wrapper.group(1)

    def nonfinite(_):
        raise ValueError('Non-finite proposal field')

    output = json.loads(value, object_pairs_hook=evaluation._unique_object, parse_constant=nonfinite)
    if not isinstance(output, dict) or set(output) != {'prompt'}:
        raise ValueError('Invalid proposal fields')
    return _prompt(output['prompt'])


def _request_run(db, protocol, item):
    row = db.execute('SELECT * FROM runs WHERE task_key=?', (item['task_key'],)).fetchone()
    if p.digest(json.loads(item['request_json'])) != item['request_sha256']:
        raise ValueError('Frozen request changed')
    if row and (row['request'] != item['request_json'] or row['packet_json'] != p.encoded(protocol['packet']) or
                row['packet_sha256'] != p.digest(protocol['packet']) or row['parent_id'] is not None or
                row['purpose'] != 'evaluation' or row['reserved_cents'] != protocol['profile']['reserve_cents'] or
                row['rates'] != p.encoded(protocol['profile']['rates']) or row['pricing_date'] != protocol['profile']['pricing_date']):
        raise ValueError('Reserved task identity or accounting differs from frozen request')
    return row


def _observe(db, identifier, protocol):
    if protocol['implementation_sha256'] != _code_hash():
        return  # Retrieval may resume; grading must use the frozen implementation.
    cases = {c['id']: c for rows in protocol['inputs']['suites'].values() for c in rows}
    for item in db.execute('SELECT * FROM improvement_requests WHERE cycle_id=? ORDER BY ordinal', (identifier,)).fetchall():
        run = _request_run(db, protocol, item)
        prior = db.execute('SELECT * FROM improvement_observations WHERE cycle_id=? AND ordinal=?', (identifier, item['ordinal'])).fetchone()
        if prior:
            if not run or prior['run_id'] != run['id'] or prior['response_sha256'] != p.digest(json.loads(run['response'] or '{}')):
                raise ValueError('Final response changed after grading')
            continue
        response = json.loads(run['response'] or '{}') if run else {}
        if response.get('status') not in p.TERMINAL:
            continue
        model = protocol['inputs']['model']
        identity = response.get('id') == run['response_id'] and response.get('model') in {model, p.RESPONSE_MODEL_ALIASES.get(model)}
        if item['stage'] == 'proposal':
            proposed = None
            try:
                if not identity or response['status'] != 'completed' or protocol['proposal_policy'] != PROPOSAL_POLICY:
                    raise ValueError('Invalid proposal')
                proposed = _proposal(_content(response))
            except (ValueError, TypeError, KeyError):
                pass
            grade = {'passed': proposed is not None, 'proposal_valid': proposed is not None}
        else:
            proposed = None
            grade = evaluation.grade(_content(response) if identity and response['status'] == 'completed' else None, cases[item['case_id']])
        with db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO improvement_observations VALUES(?,?,?,?,?,?)',
                (identifier, item['ordinal'], run['id'], p.digest(response), p.encoded(grade), time.time()))
            if item['stage'] == 'proposal' and proposed is not None:
                sha = _store_prompt(db, proposed)
                db.execute('INSERT INTO improvement_candidates VALUES(?,?,?,?,?)', (identifier, sha, 'generated', run['id'], time.time()))
            elif item['stage'] == 'proposal':
                db.execute('INSERT OR IGNORE INTO improvement_closures VALUES(?,?,?)', (identifier, 'invalid_candidate', time.time()))


def _generation_input(db, identifier, protocol):
    rows = db.execute("SELECT grade_json FROM improvement_observations o JOIN improvement_requests r USING(cycle_id,ordinal) WHERE r.cycle_id=? AND r.split='development' AND r.arm='baseline' ORDER BY r.ordinal", (identifier,)).fetchall()
    if len(rows) != 8:
        raise ValueError('All development baseline observations are required')
    return [{'role': 'system', 'content': protocol['generator']}, {'role': 'user', 'content': p.encoded({
        'baseline_prompt': protocol['baseline']['prompt'],
        'development_cases': protocol['inputs']['suites']['development'],
        'development_grades': [json.loads(row[0]) for row in rows]})}]


def _definitions(db, identifier, protocol):
    """No validation request can exist until the candidate is frozen."""
    suites = protocol['inputs']['suites']
    baseline = [('development', c, 'baseline') for c in suites['development']]
    candidate = _candidate(db, identifier)
    if candidate is None:
        observed = db.execute('SELECT COUNT(*) FROM improvement_observations WHERE cycle_id=?', (identifier,)).fetchone()[0]
        return baseline + ([('proposal', None, None)] if observed == 8 else [])
    definitions = baseline + ([('proposal', None, None)] if protocol['inputs']['candidate_prompt'] is None else [])
    definitions += [('development', c, 'candidate') for c in suites['development']]
    for index, case in enumerate(suites['validation']):
        definitions.extend(('validation', case, arm) for arm in (('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')))
    return definitions


def _freeze_requests(db, identifier, protocol):
    for ordinal, (split, case, arm) in enumerate(_definitions(db, identifier, protocol)):
        existing = db.execute('SELECT 1 FROM improvement_requests WHERE cycle_id=? AND ordinal=?', (identifier, ordinal)).fetchone()
        if existing:
            continue
        if protocol['implementation_sha256'] != _code_hash():
            raise ValueError('Implementation changed; only existing frozen requests may resume')
        if split == 'proposal':
            messages = _generation_input(db, identifier, protocol)
        else:
            messages = evaluation.build_case_input(case)
            messages[0]['content'] = protocol['baseline']['prompt'] if arm == 'baseline' else _candidate(db, identifier)
        body = p.build_task_request(protocol['inputs']['model'], messages)
        if p.validate_task_envelope(body) != protocol['profile']:
            raise ValueError('The approved profile changed')
        with db:
            db.execute('INSERT INTO improvement_requests VALUES(?,?,?,?,?,?,?,?,?)',
                (identifier, ordinal, 'proposal' if split == 'proposal' else 'evaluate', None if case is None else split,
                 case['id'] if case else None, arm, f'improve:{identifier}:{ordinal}', p.encoded(body), p.digest(body)))


def promotion_rule(grades):
    """Pairwise full-pass dominance, plus at least one gain in EACH split."""
    metrics = {}
    for split in ('development', 'validation'):
        rows = grades.get(split, {})
        if len(rows) != 8 or any(set(pair) != {'baseline', 'candidate'} or any(type(v) is not bool for v in pair.values()) for pair in rows.values()):
            return {'eligible': False, 'reason': 'incomplete_pairs', 'splits': metrics}
        regressions = sorted(key for key, pair in rows.items() if pair['baseline'] and not pair['candidate'])
        gains = sorted(key for key, pair in rows.items() if not pair['baseline'] and pair['candidate'])
        metrics[split] = {'baseline_passed': sum(pair['baseline'] for pair in rows.values()),
                         'candidate_passed': sum(pair['candidate'] for pair in rows.values()),
                         'gains': gains, 'regressions': regressions}
    eligible = all(not row['regressions'] and row['gains'] for row in metrics.values())
    return {'eligible': eligible, 'reason': 'improved_without_regressions' if eligible else 'no_measured_dominance', 'splits': metrics}


def _costs(db, identifier, protocol):
    runs = []
    for item in db.execute('SELECT * FROM improvement_requests WHERE cycle_id=?', (identifier,)):
        run = _request_run(db, protocol, item)
        if run:
            runs.append(run)
    estimates, breaches = [], 0
    for row in runs:
        try:
            facts = p._settlement_facts(row)
            estimate = Decimal(facts['estimated_usd'])
            estimates.append(estimate)
            breaches += estimate * 100 > row['reserved_cents']
        except (ValueError, TypeError, KeyError):
            estimates.append(None)
    return {'calls': len(runs), 'reserved_cents': sum(r['reserved_cents'] for r in runs),
            'known_estimated_usd': format(sum((x for x in estimates if x is not None), Decimal(0)), 'f'),
            'unknown_usage_requests': sum(x is None for x in estimates), 'over_allowance_requests': breaches}



def _decide(db, identifier, protocol):
    if protocol['implementation_sha256'] != _code_hash():
        return
    if db.execute('SELECT 1 FROM improvement_decisions WHERE cycle_id=?', (identifier,)).fetchone():
        return
    rows = db.execute('SELECT r.split,r.case_id,r.arm,o.grade_json FROM improvement_requests r JOIN improvement_observations o USING(cycle_id,ordinal) WHERE r.cycle_id=? AND r.stage=?', (identifier, 'evaluate')).fetchall()
    if len(rows) != 32:
        return
    grades = {'development': {}, 'validation': {}}
    for row in rows:
        grades[row['split']].setdefault(row['case_id'], {})[row['arm']] = json.loads(row['grade_json'])['passed']
    rule = promotion_rule(grades)
    costs = _costs(db, identifier, protocol)
    with db:
        db.execute('BEGIN IMMEDIATE')
        head = champion(db)
        reason = rule['reason']
        if head['sha256'] != protocol['baseline']['sha256'] or head['event_id'] != protocol['baseline']['event_id']:
            reason = 'stale_champion'
        elif costs['unknown_usage_requests']:
            reason = 'unconfirmed_usage'
        elif costs['over_allowance_requests'] or costs['reserved_cents'] > protocol['max_cents'] or costs['calls'] > protocol['max_calls']:
            reason = 'allowance_mismatch'
        try:
            p.require_budget_capacity(db, 0)
        except ValueError:
            reason = 'global_budget_breach'
        promote = rule['eligible'] and reason == 'improved_without_regressions'
        candidate = db.execute('SELECT prompt_sha256 FROM improvement_candidates WHERE cycle_id=?', (identifier,)).fetchone()[0]
        receipt = {'schema_version': 1, 'cycle_id': identifier, 'protocol_sha256': p.digest(protocol),
                   'decision': 'promoted' if promote else 'rejected', 'reason': reason,
                   'baseline_sha256': protocol['baseline']['sha256'], 'candidate_sha256': candidate,
                   'rule': rule, 'costs': costs, 'scope': 'authored_synthetic_evidence_critic_only'}
        db.execute('INSERT INTO improvement_decisions VALUES(?,?,?,?)', (identifier, time.time(), p.encoded(receipt), p.digest(receipt)))
        if promote:
            _event(db, 'promote', candidate, {'cycle_id': identifier, 'receipt_sha256': p.digest(receipt)})


def advance(db, identifier):
    initialize(db)
    with lock(db):
        protocol = _cycle(db, identifier)
        _observe(db, identifier, protocol)
        _decide(db, identifier, protocol)
        if db.execute('SELECT 1 FROM improvement_decisions WHERE cycle_id=?', (identifier,)).fetchone():
            return status(db, identifier)
        items = db.execute('SELECT * FROM improvement_requests WHERE cycle_id=? ORDER BY ordinal', (identifier,)).fetchall()
        pending = [(item, _request_run(db, protocol, item)) for item in items
                   if not db.execute('SELECT 1 FROM improvement_observations WHERE cycle_id=? AND ordinal=?', (identifier, item['ordinal'])).fetchone()]
        accepted = sorted(((item, run) for item, run in pending if run and run['response_id']),
                          key=lambda pair: pair[1]['created'] + (pair[1]['observed_seconds'] or 0))
        closed = db.execute('SELECT reason FROM improvement_closures WHERE cycle_id=?', (identifier,)).fetchone()
        expired = time.time() >= _time(protocol['inputs']['deadline'])
        if closed or expired:
            if not closed:
                with db:
                    db.execute('INSERT INTO improvement_closures VALUES(?,?,?)', (identifier, 'deadline', time.time()))
            if accepted:
                p.execute(db, accepted[0][1]['id'], poll_seconds=0)
                _observe(db, identifier, protocol)
                _decide(db, identifier, protocol)
            return status(db, identifier)
        # Existing accepted requests stay recoverable even after implementation/profile drift.
        implementation_matches = protocol['implementation_sha256'] == _code_hash()
        try:
            current_profile = p.validate_task_envelope(p.build_task_request(protocol['inputs']['model'],
                [{'role': 'system', 'content': protocol['baseline']['prompt']}]))
        except ValueError:
            current_profile = None
        if not implementation_matches or current_profile != protocol['profile']:
            if accepted:
                p.execute(db, accepted[0][1]['id'], poll_seconds=0)
                _observe(db, identifier, protocol)
                _decide(db, identifier, protocol)
                return status(db, identifier)
            raise ValueError('Only accepted requests may recover after implementation or profile drift')
        unsubmitted = [(item, run) for item, run in pending if run and not run['response_id']]
        if unsubmitted:
            chosen, run = unsubmitted[0]
        elif len(accepted) >= protocol['max_inflight']:
            chosen, run = accepted[0]
        else:
            _freeze_requests(db, identifier, protocol)
            item = next((i for i in db.execute('SELECT * FROM improvement_requests WHERE cycle_id=? ORDER BY ordinal', (identifier,))
                         if _request_run(db, protocol, i) is None), None)
            if item is None:
                if not accepted:
                    return status(db, identifier)
                chosen, run = accepted[0]
            else:
                if protocol['implementation_sha256'] != _code_hash() or p.validate_task_envelope(json.loads(item['request_json'])) != protocol['profile']:
                    if accepted:
                        p.execute(db, accepted[0][1]['id'], poll_seconds=0)
                        _observe(db, identifier, protocol)
                        return status(db, identifier)
                    raise ValueError('Only previously accepted requests may resume after profile or code changes')
                costs = _costs(db, identifier, protocol)
                if costs['calls'] >= protocol['max_calls'] or costs['reserved_cents'] + protocol['profile']['reserve_cents'] > protocol['max_cents']:
                    raise ValueError('Frozen improvement allowance exhausted')
                p.require_budget_capacity(db, protocol['profile']['reserve_cents'])
                p.preflight_task(protocol['inputs']['model'])
                if time.time() >= _time(protocol['inputs']['deadline']):
                    return status(db, identifier)
                run_id = p.reserve_task(db, json.loads(item['request_json']), protocol['packet'], item['task_key'], 'evaluation')
                chosen, run = item, p.get_run(db, run_id)
        if time.time() >= _time(protocol['inputs']['deadline']) and not run['response_id']:
            return status(db, identifier)
        p.execute(db, run['id'], poll_seconds=0)
        _observe(db, identifier, protocol)
        _decide(db, identifier, protocol)
        return status(db, identifier)


def status(db, identifier):
    protocol = _cycle(db, identifier)
    decision = db.execute('SELECT * FROM improvement_decisions WHERE cycle_id=?', (identifier,)).fetchone()
    if decision and p.digest(json.loads(decision['receipt_json'])) != decision['sha256']:
        raise ValueError('Decision receipt hash mismatch')
    closure = db.execute('SELECT reason FROM improvement_closures WHERE cycle_id=?', (identifier,)).fetchone()
    counts = dict(db.execute('SELECT r.stage,COUNT(*) FROM improvement_requests r JOIN improvement_observations o USING(cycle_id,ordinal) WHERE r.cycle_id=? GROUP BY r.stage', (identifier,)).fetchall())
    return {'id': identifier, 'state': json.loads(decision['receipt_json'])['decision'] if decision else
            closure[0] if closure else 'deadline' if time.time() >= _time(protocol['inputs']['deadline']) else 'running',
            'recorded_at': p.iso(time.time()), 'implementation_matches': protocol['implementation_sha256'] == _code_hash(),
            'finalized_evaluations': counts.get('evaluate', 0), 'finalized_proposals': counts.get('proposal', 0),
            'max_calls': protocol['max_calls'], 'max_cents': protocol['max_cents'],
            'costs': _costs(db, identifier, protocol), 'champion': {k: v for k, v in champion(db).items() if k != 'prompt'},
            'decision': json.loads(decision['receipt_json']) if decision else None}


def build_current_claim_request(db, claim, as_of, evidence, model=DEFAULT_MODEL):
    """Build ONLY a claim-level critic request; never the investigator report critic.

    Construction does not reserve, submit, execute tools or approve research. A
    caller must use the ordinary shared ledger and its own authorized task key.
    """
    _time(as_of + 'T00:00:00Z')
    p.require_text(claim, 2000, 'claim')
    if not isinstance(evidence, list) or len(evidence) > 20:
        raise ValueError('Expected a bounded evidence list')
    seen = set()
    for item in evidence:
        p.exact_keys(item, ['id', 'text', 'published_at', 'source_url'], 'critic evidence')
        for key, maximum in [('id', 80), ('text', 12000), ('source_url', 600)]:
            p.require_text(item[key], maximum, key)
        _time(item['published_at'] + 'T00:00:00Z')
        if item['id'] in seen or not item['source_url'].startswith('https://'):
            raise ValueError('Evidence must have unique IDs and HTTPS provenance')
        seen.add(item['id'])
    current = champion(db)
    if not current:
        raise ValueError('Initialize an improvement cycle before selecting a champion')
    body = p.build_task_request(model, [{'role': 'system', 'content': current['prompt']},
        {'role': 'user', 'content': p.encoded({'claim': claim, 'as_of': as_of, 'evidence': evidence})}])
    return {'contract': 'evidence_critic_verdict_v1', 'champion_sha256': current['sha256'],
            'champion_event_id': current['event_id'], 'request': body}


def rollback(db, target_event, reason):
    initialize(db)
    p.require_text(reason, 240, 'rollback reason')
    with lock(db), db:
        db.execute('BEGIN IMMEDIATE')
        head = champion(db)
        target = db.execute('SELECT * FROM improvement_events WHERE id=? AND kind IN (?,?)', (target_event, 'initialize', 'promote')).fetchone()
        if not head or not target:
            raise ValueError('Choose a prior initial or promoted champion event')
        _event(db, 'rollback', target['prompt_sha256'], {'target_event': target_event, 'reason': reason, 'previous_event': head['event_id']})
        return champion(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=None)
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('start')
    new.add_argument('--key', required=True)
    new.add_argument('--deadline', required=True)
    new.add_argument('--model', choices=MODELS, default=DEFAULT_MODEL)
    new.add_argument('--candidate', type=Path)
    new.add_argument('--development', type=Path, default=DATA / 'development.json')
    new.add_argument('--validation', type=Path, default=DATA / 'validation.json')
    for name in ('advance', 'status', 'run'):
        cmd = commands.add_parser(name); cmd.add_argument('id')
        if name == 'run':
            cmd.add_argument('--seconds', type=int, default=600)
    commands.add_parser('champion')
    old = commands.add_parser('rollback'); old.add_argument('event', type=int); old.add_argument('--reason', required=True)
    args = parser.parse_args()
    try:
        db = p.database(args.database)
        initialize(db)
        if args.command == 'start':
            result = {'id': start(db, args.key, args.deadline, args.model, args.candidate.read_text() if args.candidate else None, args.development, args.validation)}
        elif args.command == 'advance':
            result = advance(db, args.id)
        elif args.command == 'status':
            result = status(db, args.id)
        elif args.command == 'champion':
            result = champion(db)
        elif args.command == 'rollback':
            result = rollback(db, args.event, args.reason)
        else:
            if not 1 <= args.seconds <= 3600:
                raise ValueError('Run window must be1–3600 seconds')
            end = time.monotonic() + args.seconds
            result = status(db, args.id)
            while time.monotonic() < end and result['state'] == 'running':
                result = advance(db, args.id)
                if result['state'] == 'running':
                    time.sleep(1)
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, TypeError, sqlite3.Error, OSError):
        parser.exit(1, 'Improvement step blocked; inspect frozen contract and shared ledger locally. No replacement work was created.\n')
    finally:
        if 'db' in locals():
            db.close()


if __name__ == '__main__':
    main()
