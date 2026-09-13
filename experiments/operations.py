"""Read-only operational summary of the portfolio research ledger.

No inference, source retrieval, credentials, or brokerage imports. Provider
completion and editorial acceptance remain separate measures.
"""
import argparse
from collections import Counter
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import time

import portfolio as p

ROOT = Path(__file__).resolve().parent
PURPOSES = ('thesis', 'investigate', 'critique', 'evaluation', 'replay', 'policy_probe', 'robustness', 'cache_research')
PROVIDER_STATES = {'completed', 'failed', 'cancelled', 'incomplete', 'queued', 'in_progress'}
INVESTIGATION_STATES = {'research', 'critique', 'repair', 'recheck', 'editorial_recheck',
                        'awaiting_review', 'needs_attention', 'expired'}
QUEUE_STATES = {'queued', 'running', 'waiting', 'budget_wait', 'awaiting_review', 'needs_attention', 'deadline', 'reviewed'}


def connect(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('An existing regular research ledger is required')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def _object(text):
    value = json.loads(text or '{}')
    if not isinstance(value, dict):
        raise ValueError('Expected a saved object')
    return value


def _cost(rows):
    known, unknown, held = Decimal(0), 0, 0
    states = Counter()
    accepted = set()
    for row in rows:
        held += row['reserved_cents']
        response = _object(row['response'])
        state = response.get('status')
        if state not in PROVIDER_STATES:
            state = 'unconfirmed' if row['error'] else 'reserved'
        states[state] += 1
        if row['response_id']:
            accepted.add(row['response_id'])
        value = p.run_cost(row)
        if value is None:
            unknown += 1
        else:
            known += value
    return {'logical_requests': len(rows), 'accepted_responses': len(accepted),
            'provider_states': dict(sorted(states.items())),
            'known_estimated_usd': format(known, 'f'), 'unknown_usage_requests': unknown,
            'estimated_usd': format(known, 'f') if not unknown else None,
            'reserved_usd': format(Decimal(held) / 100, 'f')}


def snapshot(db, now=None):
    """One consistent database read; never invoke mutating subsystem status APIs."""
    if db.in_transaction:
        raise ValueError('Use a connection without an active transaction')
    now = time.time() if now is None else now
    db.execute('BEGIN')
    try:
        tables = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'runs' not in tables:
            raise ValueError('Research ledger has no request table')
        rows = db.execute('SELECT * FROM runs ORDER BY created,id').fetchall()
        if any(row['purpose'] not in PURPOSES for row in rows):
            raise ValueError('Unknown request purpose; update the summary contract explicitly')
        result = {'schema_version': 1, 'generated_at': p.iso(now),
                  'scope': 'portfolio_research_ledger',
                  'inference': _cost(rows),
                  'budget': p.budget_accounting(db),
                  'purposes': [{'purpose': purpose, **_cost([r for r in rows if r['purpose'] == purpose])}
                               for purpose in PURPOSES if any(r['purpose'] == purpose for r in rows)],
                  'investigations': None, 'queue': None, 'source_watch': None,
                  'limitations': [
                      'Token-price estimates are not reconciled bills; unknown usage remains unknown.',
                      'Reservations are conservative admission allowances, not money spent.',
                      'Provider completion is not a correct answer or editorial acceptance.',
                      'This ledger excludes the original extraction experiment and cloud VM charges.',
                      'A saved observation does not prove a controller is still running.'
                  ]}
        reviewed_ids = set()
        if {'investigations', 'investigation_reviews'} <= tables:
            reviews = {r['investigation_id']: r['state_sha256'] for r in db.execute('SELECT * FROM investigation_reviews')}
            states = Counter()
            reviewed = 0
            for row in db.execute('SELECT id,state_json FROM investigations'):
                state = _object(row['state_json'])
                phase = state.get('phase')
                if phase not in INVESTIGATION_STATES:
                    raise ValueError('Unknown investigation phase')
                if row['id'] in reviews:
                    if p.digest(state) != reviews[row['id']]:
                        raise ValueError('Reviewed investigation changed')
                    reviewed += 1
                    reviewed_ids.add(row['id'])
                else:
                    states[phase] += 1
            result['investigations'] = {'reviewed': reviewed,
                                       'unreviewed_states': dict(sorted(states.items())),
                                       'total': reviewed + sum(states.values())}
        if 'research_queue_jobs' in tables:
            jobs = db.execute('SELECT investigation_id,state,paused FROM research_queue_jobs').fetchall()
            states = Counter()
            for job in jobs:
                if job['state'] not in QUEUE_STATES:
                    raise ValueError('Unknown queue state')
                states['reviewed' if job['investigation_id'] in reviewed_ids else job['state']] += 1
            result['queue'] = {'jobs': len(jobs), 'paused': sum(bool(r['paused']) for r in jobs),
                               'states': dict(sorted(states.items()))}
        if {'source_watch_observations', 'source_watch_reviews', 'source_watch_versions'} <= tables:
            observations = db.execute('SELECT state,finished FROM source_watch_observations').fetchall()
            result['source_watch'] = {
                'observations': len(observations),
                'last_observed_at': p.iso(max(r['finished'] for r in observations)) if observations else None,
                'retained_versions': db.execute('SELECT COUNT(*) FROM source_watch_versions').fetchone()[0],
                'reviewed_candidates': db.execute('SELECT COUNT(*) FROM source_watch_reviews').fetchone()[0]}
        return result
    finally:
        db.rollback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / '.data/portfolio.sqlite')
    args = parser.parse_args()
    try:
        with closing(connect(args.database)) as db:
            result = snapshot(db)
    except (ValueError, TypeError, KeyError, sqlite3.Error, OSError):
        parser.exit(1, 'Cannot summarize the research ledger; inspect its schema and integrity locally.\n')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
