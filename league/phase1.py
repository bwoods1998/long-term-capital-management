"""Read-only phase-one progress report. Never activates or extends a spending campaign."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import sqlite3
import time


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def report(root: str | Path, *, now=None):
    root, now = Path(root), time.time() if now is None else now
    db = connect(root / 'campaigns.sqlite')
    try:
        phase = dict(db.execute('SELECT * FROM phase').fetchone())
        policy = json.loads(phase['policy'])
        costs = [dict(r) for r in db.execute('SELECT kind,COUNT(*) calls,SUM(COALESCE(cost,0)) settled_micro_usd,SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END) held_micro_usd,SUM(cost IS NULL) unresolved FROM commitments GROUP BY kind')]
        meters = [dict(r) for r in db.execute('SELECT meter.*,checked,failed FROM meter LEFT JOIN meter_health USING(id)')]
        burst = None
        live_trading = None
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='burst'").fetchone():
            row = db.execute('SELECT * FROM burst').fetchone()
            if row:
                burst = {**dict(row), 'policy': json.loads(row['policy']), 'meters': json.loads(row['meters'])}
                burst['running'] = burst['started'] <= now < burst['ends']
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_trading'").fetchone():
            row = db.execute('SELECT * FROM live_trading').fetchone()
            if row:
                from .live_trading import policy as live_policy
                live_trading = {**dict(row), 'policy': json.loads(row['policy'])}
                live_trading['active'] = (row['revoked'] is None and row['started'] <= now
                    and live_trading['policy'] == live_policy(live_trading['policy']['venue_capital_usd']))
    finally:
        db.close()
    since = datetime.fromtimestamp(phase['started'], timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    db = connect(root / 'ledger.sqlite')
    try:
        rows = [(r['kind'], json.loads(r['payload'])) for r in db.execute(
            'SELECT kind,payload FROM ledger WHERE at>=? AND kind IN (?,?,?,?,?,?) ORDER BY seq',
            (since, 'experiment.started', 'experiment.finished', 'ops.job', 'eval.trial', 'agent.research', 'agent.mutation'))]
        requests = {}
        for r in db.execute("SELECT id,agent,at,kind,payload FROM ledger WHERE kind IN ('tool.request','tool.blocked','tool.fulfilled') ORDER BY seq"):
            p = json.loads(r['payload'])
            if r['kind'] == 'tool.request':
                requests[r['id']] = {'id': r['id'], 'agent': r['agent'], 'at': r['at'], 'name': p.get('name'), 'status': 'open'}
            elif p.get('request') in requests:
                blocked = r['kind'] == 'tool.blocked' or (p.get('status') == 'answered' and str(p.get('outcome') or '').lower().startswith('cannot be a pure tool'))
                requests[p['request']].update(status='blocked' if blocked else 'fulfilled', outcome=p.get('outcome'))
    finally:
        db.close()
    started = {p['attempt']: p for k,p in rows if k == 'experiment.started'}
    finished = {p['attempt']: p for k,p in rows if k == 'experiment.finished'}
    jobs = [p for k,p in rows if k == 'ops.job' and p.get('state') in ('finished', 'failed')]
    begun_jobs = {p['job'] for k,p in rows if k == 'ops.job' and p.get('state') == 'started'}
    latency = {}
    def lane_of(key):
        if key == 'merton:follow':
            return 'housekeeping'
        if key == 'niche-survey':
            return 'survey'
        return key.split(':')[0]
    for lane in ('research', 'replay', 'merton', 'survey', 'housekeeping'):
        lane_jobs = [p for p in jobs if lane_of(p['key']) == lane]
        stats = {'finished': len(lane_jobs), 'failed': sum(p['state'] == 'failed' for p in lane_jobs)}
        for field in ('queued_seconds', 'running_seconds', 'elapsed_seconds'):
            values = sorted(float(p.get(field, 0)) for p in lane_jobs)
            stats[field] = {name: round(values[min(len(values)-1, math.ceil(len(values)*q)-1)], 3) if values else None
                            for name,q in [('p50', .5), ('p95', .95), ('max', 1)]}
        latency[lane] = stats
    trials = [p for k,p in rows if k == 'eval.trial']
    conclusions = [p for k,p in rows if k == 'agent.research' and p.get('tool') == 'summary']
    research = {'completed_sessions': len(conclusions),
                'reasons': dict(Counter(p.get('reason', 'unknown') for p in conclusions)),
                'with_candidate': sum(bool(p.get('candidate')) for p in conclusions),
                'reported_cost_usd': str(sum((Decimal(str(p.get('cost_usd') or 0)) for p in conclusions), Decimal(0))),
                'note': 'Session costs exclude unfinished work. Research latency counts worker attempts, including deferrals. Replay tools can include smoke checks; eval.trial is the counted-trial source.'}
    research['by_profile'] = {}
    for profile in sorted({p.get('profile', 'legacy_unrecorded') for p in conclusions}):
        group = [p for p in conclusions if p.get('profile', 'legacy_unrecorded') == profile]
        elapsed = sorted(float(p['elapsed_seconds']) for p in group if p.get('elapsed_seconds') is not None)
        research['by_profile'][profile] = {'completed': len(group), 'with_candidate': sum(bool(p.get('candidate')) for p in group),
            'reported_cost_usd': str(sum((Decimal(str(p.get('cost_usd') or 0)) for p in group), Decimal(0))),
            'median_session_seconds': elapsed[len(elapsed)//2] if elapsed else None,
            'reasons': dict(Counter(p.get('reason', 'unknown') for p in group))}
    if (root / 'research.sqlite').exists():
        db = connect(root / 'research.sqlite')
        try:
            research['durable_jobs'] = [dict(r) for r in db.execute(
                'SELECT status,COUNT(*) count,SUM(resumes) resumes FROM research_jobs GROUP BY status')]
            research['pending'] = [dict(r) for r in db.execute("SELECT session,agent,status,created,updated,available,reason,resumes FROM research_jobs WHERE status IN ('queued','working','ready','applying') ORDER BY created,session")]
        finally:
            db.close()
    grants = []
    if (root / 'grants.sqlite').exists():
        db = connect(root / 'grants.sqlite')
        try:
            for row in db.execute('SELECT agent,family,niche,created,status,reply FROM grants WHERE phase=? ORDER BY created', (f"{phase['started']:.6f}",)):
                grant = dict(row)
                reply = json.loads(grant.pop('reply') or '{}')
                grants.append({**grant, 'model': reply.get('model'), 'cost_usd': reply.get('cost_usd'),
                               'wrote_code': bool(reply.get('code')), 'error': reply.get('error')})
        finally:
            db.close()
    db = connect(root / 'recordings.sqlite')
    try:
        count, size, first, last = db.execute('SELECT COUNT(*),COALESCE(SUM(length(payload)),0),MIN(received),MAX(received) FROM snapshots').fetchone()
        evicted = db.execute("SELECT value FROM recorder_meta WHERE key='evicted'").fetchone()[0]
    finally:
        db.close()
    ends = phase['started'] + float(policy['duration_hours']) * 3600
    running = bool(live_trading and live_trading['active']) or (phase['started'] <= now < ends and (not burst or burst['running']))
    return {'phase': phase['id'], 'started': phase['started'], 'ends': ends, 'running': running,
            'policy': policy, 'burst': burst, 'live_trading': live_trading, 'costs': costs, 'vendor_meters': meters,
            'experiments': {'started': len(started), 'finished': len(finished),
                            'unfinished_attempts': sorted(set(started)-set(finished)),
                            'latest': list(finished.values())[-5:]},
            'trials': {'total': len(trials), 'with_manifest': sum(bool(p.get('experiment')) for p in trials),
                       'passed': sum(bool(p.get('passed')) for p in trials)},
            'mutation_rejections': dict(Counter(p.get('reason', 'unknown') for k,p in rows
                                                if k == 'agent.mutation' and p.get('status') == 'rejected')),
            'tool_requests': {'by_status': dict(Counter(r['status'] for r in requests.values())),
                              'blocked': [r for r in requests.values() if r['status'] == 'blocked']},
            'startup_grants': grants,
            'jobs_without_finish': sorted(begun_jobs - {p['job'] for p in jobs}), 'latency': latency, 'research': research,
            'recordings': {'kind': 'sampled_rest_snapshots', 'count': count, 'compressed_bytes': size,
                           'first_received': first, 'last_received': last, 'evicted': evicted},
            'interpretation': 'Unfinished work may still be running or may have been interrupted. Historical passes do not establish live profitability. External reserves are allowances, not invoices.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.root), indent=2))


if __name__ == '__main__':
    main()
