"""Explicit local assignments, durable recovery, and bounded investigator spending.

Enqueue freezes checked inputs without network or inference. Managed investigations
advance only through this queue; review and publication remain separate local acts.
"""
import argparse
from contextlib import closing, contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

import portfolio as p
import investigator as inv
import research_sources as sources

ROOT = Path(__file__).resolve().parent
MAX_JOBS = 2
MAX_JOB_CENTS = 300
ANALYST, CRITIC = inv.ANALYST, inv.CRITIC
NAMESPACE = uuid.UUID('33fa05e2-2cec-48ed-ae01-d41c34d80c2a')
FINAL = {'awaiting_review', 'needs_attention', 'deadline', 'reviewed'}
_active = ContextVar('research_queue_admission', default=None)


class QueueHold(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def initialize(db):
    inv.setup(db)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS research_queue_jobs (
            ordinal INTEGER PRIMARY KEY AUTOINCREMENT, job_key TEXT NOT NULL UNIQUE,
            created REAL NOT NULL, due REAL NOT NULL, deadline REAL NOT NULL,
            input_json TEXT NOT NULL, input_sha256 TEXT NOT NULL,
            investigation_id TEXT NOT NULL UNIQUE, initialized INTEGER NOT NULL DEFAULT 0,
            paused INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'queued',
            next_attempt REAL NOT NULL DEFAULT 0, error_code TEXT);
        CREATE TABLE IF NOT EXISTS research_queue_events (
            id INTEGER PRIMARY KEY, job_key TEXT NOT NULL REFERENCES research_queue_jobs(job_key),
            at REAL NOT NULL, kind TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS frozen_queue_input BEFORE UPDATE OF
            ordinal,job_key,created,due,deadline,input_json,input_sha256,investigation_id ON research_queue_jobs
            BEGIN SELECT RAISE(ABORT,'Queue assignments are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS keep_queue_jobs BEFORE DELETE ON research_queue_jobs
            BEGIN SELECT RAISE(ABORT,'Queue history is permanent'); END;
        CREATE TRIGGER IF NOT EXISTS keep_queue_events_update BEFORE UPDATE ON research_queue_events
            BEGIN SELECT RAISE(ABORT,'Queue events are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS keep_queue_events_delete BEFORE DELETE ON research_queue_events
            BEGIN SELECT RAISE(ABORT,'Queue events are immutable'); END;
    ''')
    return db


@contextmanager
def lock(db):
    filename = db.execute('PRAGMA database_list').fetchone()['file']
    if not filename:
        raise ValueError('Queue requires the persistent private ledger')
    descriptor = os.open(filename + '.research-queue.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another research queue controller owns this ledger') from None
        yield filename
    finally:
        os.close(descriptor)


def timestamp(value):
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Use a timestamp with a timezone')
        value = parsed.timestamp()
    if type(value) not in (int, float) or not Decimal(str(value)).is_finite():
        raise ValueError('Use a finite timestamp')
    return float(value)


def _profiles(model, critic_model, max_turns):
    if (model != ANALYST or critic_model != CRITIC or type(max_turns) is not int or
            not 2 <= max_turns <= 4):
        raise ValueError('Queue permits Pro research, Kimi critique, and two to four research turns')
    profiles = {name: deepcopy(p.TASK_PROFILES[name]) for name in (model, critic_model)}
    limit = (max_turns + 1) * profiles[model]['reserve_cents'] + 2 * profiles[critic_model]['reserve_cents']
    if limit > MAX_JOB_CENTS:
        raise ValueError('The complete research/repair envelope exceeds three dollars')
    return profiles, limit


def _get(db, job_key):
    row = db.execute('SELECT * FROM research_queue_jobs WHERE job_key=?', (job_key,)).fetchone()
    if row is None:
        raise ValueError('Unknown queued assignment')
    data = json.loads(row['input_json'])
    if (p.digest(data) != row['input_sha256'] or data['due'] != row['due'] or
            data['deadline'] != row['deadline'] or row['investigation_id'] !=
            str(uuid.uuid5(NAMESPACE, job_key + ':' + row['input_sha256']))):
        raise ValueError('Queued assignment integrity check failed')
    return row, data


def _event(db, job_key, kind):
    db.execute('INSERT INTO research_queue_events(job_key,at,kind) VALUES(?,?,?)',
               (job_key, time.time(), kind))


def enqueue(db, job_key, question, *, packet=None, model=ANALYST, critic_model=CRITIC,
            max_turns=4, due, deadline, root=ROOT):
    initialize(db)
    if not isinstance(job_key, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}', job_key):
        raise ValueError('Use a stable, nonsecret assignment key of at most eighty characters')
    p.require_text(question, 400, 'research question')
    due, deadline = timestamp(due), timestamp(deadline)
    profiles, limit = _profiles(model, critic_model, max_turns)
    checked = p.validate_packet(deepcopy(packet if packet is not None else p.load_packet()))
    request = {'question': question, 'model': model, 'critic_model': critic_model,
               'max_turns': max_turns, 'due': due, 'deadline': deadline, 'packet': checked}
    with lock(db):
        existing = db.execute('SELECT 1 FROM research_queue_jobs WHERE job_key=?', (job_key,)).fetchone()
        if existing:
            row, frozen = _get(db, job_key)
            if frozen['request'] != request:
                raise ValueError('Assignment key collision: the frozen inputs differ')
            return status(db, job_key)
        now = time.time()
        if not now < deadline <= now + 24 * 3600 or due > deadline:
            raise ValueError('Use a future deadline within one day and a due time no later than it')
        cutoff = p.iso(now)[:10]
        store = sources.SourceStore(root)
        snapshots = {}
        for source in checked['sources']:
            identifier = source['id']
            registered = sources.allowed_source(identifier)
            if source != {key: registered[key] for key in source}:
                raise ValueError('Checked packet source does not match the registered identity')
        for identifier in sources.SOURCE_REGISTRY:
            artifact = store._read(store.path / (identifier + '.json'), cutoff)
            if artifact['id'] != identifier:
                raise ValueError('Frozen source filename does not match its identity')
            snapshots[identifier] = artifact
        data = {'schema_version': 1, 'request': request, **request, 'profiles': profiles,
                'max_reserved_cents': limit, 'evidence_cutoff': cutoff, 'snapshots': snapshots}
        encoded, digest = p.encoded(data), p.digest(data)
        investigation_id = str(uuid.uuid5(NAMESPACE, job_key + ':' + digest))
        with db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM research_queue_jobs').fetchone()[0] >= MAX_JOBS:
                raise ValueError('This queue permits at most two durable assignments; history is not reset')
            db.execute('''INSERT INTO research_queue_jobs
                (job_key,created,due,deadline,input_json,input_sha256,investigation_id)
                VALUES(?,?,?,?,?,?,?)''', (job_key, now, due, deadline, encoded, digest, investigation_id))
            _event(db, job_key, 'enqueued')
    return status(db, job_key)


def _runs(db, row, data):
    prefix = row['investigation_id'] + ':'
    rows = db.execute('SELECT * FROM runs WHERE task_key LIKE ?', (prefix + '%',)).fetchall()
    allowed = {prefix + f'research:{turn}': (data['model'], 'investigate') for turn in range(data['max_turns'])}
    allowed.update({prefix + 'critique': (data['critic_model'], 'critique'),
                    prefix + 'repair': (data['model'], 'investigate'),
                    prefix + 'recheck': (data['critic_model'], 'critique')})
    for run in rows:
        profile = allowed.get(run['task_key'])
        body = json.loads(run['request'])
        frozen_profile = data['profiles'].get(profile[0]) if profile else None
        if (profile is None or body.get('model') != profile[0] or
                body.get('metadata') != {'completion_window': frozen_profile['completion_window']} or
                body.get('max_output_tokens') != frozen_profile['max_output_tokens'] or
                body.get('reasoning') != {'effort': frozen_profile['reasoning_effort']} or
                body.get('background') is not frozen_profile['background'] or run['purpose'] != profile[1] or
                run['reserved_cents'] != data['profiles'][profile[0]]['reserve_cents'] or
                json.loads(run['rates']) != data['profiles'][profile[0]]['rates'] or
                run['packet_sha256'] != p.digest(data['packet'])):
            raise QueueHold('request_contract_changed')
    if sum(run['reserved_cents'] for run in rows) > data['max_reserved_cents']:
        raise QueueHold('assignment_budget_exceeded')
    return rows


def _verify_state(row, data, state):
    if (state['id'] != row['investigation_id'] or state['mode'] != 'tools' or
            any(state[key] != data[key] for key in ('question', 'model', 'critic_model', 'max_turns', 'deadline', 'packet'))):
        raise QueueHold('investigation_collision')
    if state.get('queue_job_key') != row['job_key'] or state.get('queue_input_sha256') != row['input_sha256']:
        raise QueueHold('investigation_not_attached')
    if state['snapshots'] != data['snapshots'] or state['cutoff'] != data['evidence_cutoff']:
        raise QueueHold('frozen_sources_changed')
    for artifact in data['snapshots'].values():
        sources.validate_snapshot(artifact, cutoff=data['evidence_cutoff'])


def require_admission(db, state):
    """Called inside investigator.advance's own lock; ordinary CLI cannot bypass it."""
    active = _active.get()
    filename = db.execute('PRAGMA database_list').fetchone()['file']
    if active != (filename, state.get('queue_job_key')):
        raise ValueError('Managed investigation: resume through research_queue.py')
    row, data = _get(db, state['queue_job_key'])
    _verify_state(row, data, state)
    if row['paused']:
        raise QueueHold('paused')
    if time.time() >= row['deadline']:
        raise QueueHold('deadline')
    if state.get('editorial_amendment') or state['phase'] == 'editorial_recheck':
        raise QueueHold('editorial_review_required')
    rows = _runs(db, row, data)
    if (len(state['run_ids']) != len(set(state['run_ids'])) or
            any(identifier not in {run['id'] for run in rows} for identifier in state['run_ids']) or
            any(run['parent_id'] != state['parent_id'] for run in rows)):
        raise QueueHold('request_contract_changed')
    if state['phase'] in inv.STOPPED or (state['phase'] == 'research' and state['turn'] >= state['max_turns']):
        return
    suffix = f'research:{state["turn"]}' if state['phase'] == 'research' else state['phase']
    existing = next((run for run in rows if run['task_key'] == state['id'] + ':' + suffix), None)
    if existing is not None and existing['response_id']:
        return  # Retrieve the known original response even if later profiles changed.
    try:
        profiles, maximum = _profiles(data['model'], data['critic_model'], data['max_turns'])
    except ValueError:
        raise QueueHold('model_profile_changed') from None
    if profiles != data['profiles'] or maximum != data['max_reserved_cents']:
        raise QueueHold('model_profile_changed')
    if existing is not None:
        return  # Original idempotent submission already has its permanent allowance.
    held = sum(run['reserved_cents'] for run in rows)
    global_held = db.execute('SELECT COALESCE(SUM(reserved_cents),0) FROM runs').fetchone()[0]
    if p.budget_limit(db) - global_held < data['max_reserved_cents'] - held:
        raise QueueHold('budget_wait')


def _attach(db, row, data):
    found = db.execute('SELECT 1 FROM investigations WHERE id=?', (row['investigation_id'],)).fetchone()
    if found is None:
        inv.start(db, data['question'], data['model'], data['critic_model'], data['max_turns'],
                  data['deadline'], data['packet'], investigation_id=row['investigation_id'])
    state = inv.get(db, row['investigation_id'])
    if not state.get('queue_job_key'):
        if (state['mode'] != 'tools' or state['phase'] != 'research' or state['turn'] != 0 or
                state['run_ids'] or state['tool_results'] or state['draft'] is not None or
                any(state[key] != data[key] for key in ('question', 'model', 'critic_model', 'max_turns', 'deadline', 'packet')) or
                _runs(db, row, data)):
            raise QueueHold('investigation_collision')
        state['snapshots'] = deepcopy(data['snapshots'])
        state['cutoff'] = data['evidence_cutoff']
        state['queue_job_key'], state['queue_input_sha256'] = row['job_key'], row['input_sha256']
        state['conversation'] = [{'role': 'user', 'content': inv._prompt(state)}]
        with db:
            db.execute('UPDATE investigations SET state_json=? WHERE id=?', (p.encoded(state), state['id']))
            db.execute('UPDATE research_queue_jobs SET initialized=1 WHERE job_key=?', (row['job_key'],))
            _event(db, row['job_key'], 'investigation_attached')
    _verify_state(row, data, state)
    return state


def pause(db, job_key, paused=True):
    initialize(db)
    _get(db, job_key)
    with db:
        db.execute('UPDATE research_queue_jobs SET paused=? WHERE job_key=?', (int(paused), job_key))
        _event(db, job_key, 'paused' if paused else 'resumed')
    return status(db, job_key)


def status(db, job_key=None):
    initialize(db)
    selected = [job_key] if job_key else [row['job_key'] for row in db.execute('SELECT job_key FROM research_queue_jobs ORDER BY ordinal')]
    jobs = []
    for key in selected:
        row, data = _get(db, key)
        runs = _runs(db, row, data)
        known = [p.run_cost(run) for run in runs]
        visible_state = 'paused' if row['paused'] and row['state'] not in FINAL else row['state']
        reviewed = db.execute('SELECT state_sha256 FROM investigation_reviews WHERE investigation_id=?',
                              (row['investigation_id'],)).fetchone()
        if reviewed:
            investigation = inv.get(db, row['investigation_id'])
            if p.digest(investigation) != reviewed['state_sha256']:
                raise ValueError('Reviewed investigation changed')
            _verify_state(row, data, investigation)
            visible_state = 'reviewed'
        jobs.append({'job_key': key, 'investigation_id': row['investigation_id'], 'state': visible_state,
                     'due_at': p.iso(row['due']), 'deadline': p.iso(row['deadline']), 'initialized': bool(row['initialized']),
                     'error_code': None if reviewed else row['error_code'], 'evidence_cutoff': data['evidence_cutoff'],
                     'source_versions': {identifier: artifact['sha256'] for identifier, artifact in data['snapshots'].items()},
                     'maximum_reserved_usd': str(Decimal(data['max_reserved_cents']) / 100),
                     'reserved_usd': str(Decimal(sum(run['reserved_cents'] for run in runs)) / 100),
                     'known_estimated_usd': str(sum((cost for cost in known if cost is not None), Decimal(0))),
                     'unknown_runs': sum(cost is None for cost in known), 'model_calls': len(runs)})
    return {'schema_version': 1, 'jobs': jobs, 'publication': 'unchanged', 'review': 'manual', 'maximum_jobs': MAX_JOBS}


def _advance(db, filename):
    now = time.time()
    with db:
        db.execute("UPDATE research_queue_jobs SET state='deadline',error_code='deadline' WHERE deadline<=? AND state NOT IN ('awaiting_review','needs_attention','deadline','reviewed')", (now,))
    row = db.execute("SELECT * FROM research_queue_jobs WHERE paused=0 AND due<=? AND state NOT IN ('awaiting_review','needs_attention','deadline','reviewed') ORDER BY due,ordinal LIMIT 1", (now,)).fetchone()
    if row is None or row['next_attempt'] > now:
        return status(db)
    row, data = _get(db, row['job_key'])
    try:
        state = _attach(db, row, data)
        with db:
            db.execute("UPDATE research_queue_jobs SET state='running',error_code=NULL WHERE job_key=?", (row['job_key'],))
        token = _active.set((filename, row['job_key']))
        try:
            inv.advance(db, state['id'], poll_seconds=0)
        finally:
            _active.reset(token)
        state = inv.get(db, state['id'])
        phase = state['phase']
        if db.execute('SELECT 1 FROM investigation_reviews WHERE investigation_id=?', (state['id'],)).fetchone():
            phase = 'reviewed'
        result = {'expired': 'deadline'}.get(phase, phase if phase in FINAL else 'waiting')
        error = None
    except QueueHold as failure:
        error = failure.code
        result = error if error in {'budget_wait', 'deadline'} else 'waiting' if error == 'paused' else 'needs_attention'
    except (ValueError, RuntimeError, OSError):
        result, error = 'waiting', 'advance_unconfirmed'
    with db:
        db.execute('UPDATE research_queue_jobs SET state=?,error_code=?,next_attempt=? WHERE job_key=?',
                   (result, error, time.time() + (60 if error else 3), row['job_key']))
        _event(db, row['job_key'], result)
    return status(db)


def advance(db):
    initialize(db)
    with lock(db) as filename:
        return _advance(db, filename)


def run(db, seconds=300):
    if type(seconds) is not int or not 1 <= seconds <= 21600:
        raise ValueError('Run for one second to six hours')
    initialize(db)
    end = time.monotonic() + seconds
    with lock(db) as filename:
        while time.monotonic() < end:
            result = _advance(db, filename)
            if all(job['state'] in FINAL or job['state'] == 'paused' for job in result['jobs']):
                return result
            time.sleep(min(3, max(0, end - time.monotonic())))
    return status(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    enqueue_parser = commands.add_parser('enqueue')
    enqueue_parser.add_argument('job_key')
    enqueue_parser.add_argument('--question', required=True)
    enqueue_parser.add_argument('--packet', type=Path, required=True)
    enqueue_parser.add_argument('--due', required=True)
    enqueue_parser.add_argument('--deadline', required=True)
    enqueue_parser.add_argument('--model', default=ANALYST)
    enqueue_parser.add_argument('--critic-model', default=CRITIC)
    enqueue_parser.add_argument('--max-turns', type=int, default=4)
    commands.add_parser('status')
    commands.add_parser('advance')
    commands.add_parser('run').add_argument('--seconds', type=int, default=300)
    commands.add_parser('pause').add_argument('job_key')
    commands.add_parser('resume').add_argument('job_key')
    args = parser.parse_args()
    with closing(initialize(p.database())) as db:
        if args.command == 'enqueue':
            result = enqueue(db, args.job_key, args.question, packet=json.loads(args.packet.read_text()),
                             model=args.model, critic_model=args.critic_model, max_turns=args.max_turns,
                             due=args.due, deadline=args.deadline)
        elif args.command in {'pause', 'resume'}:
            result = pause(db, args.job_key, args.command == 'pause')
        elif args.command == 'advance':
            result = advance(db)
        elif args.command == 'run':
            result = run(db, args.seconds)
        else:
            result = status(db)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    # investigator's lazy guard import must share this CLI controller context.
    sys.modules['research_queue'] = sys.modules[__name__]
    main()
