"""Durable paper-candidate admission, folded from the append-only research record.

A full desk is a wait, not a discarded experiment. An uncertain lifecycle write is never
retried automatically. Candidate source remains private, and old deferred receipts retain
their original session identity so installing this queue does not require rewriting history.
"""
from __future__ import annotations

from .ledger import Ledger


class Admissions:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def rows(self):
        found = {}
        for entry in self.ledger.iter(kinds='agent.research'):
            p = entry.payload
            if p.get('tool') not in ('candidate', 'candidate_admission') or not p.get('session'):
                continue
            if p.get('tool') == 'candidate' and p.get('status') not in ('deferred', 'forked', 'fork_error', 'commit_unconfirmed'):
                continue
            session = p['session']
            row = found.setdefault(session, {'session': session, 'agent': entry.agent, 'created_seq': entry.seq})
            row.update(p)
        return sorted(found.values(), key=lambda r: r['created_seq'])

    def pending(self):
        return [r for r in self.rows() if r.get('status') in ('queued', 'deferred', 'admitting') and r.get('_candidate')]

    def enqueue(self, agent, generation, candidate, session):
        prior = next((r for r in self.rows() if r['session'] == session), None)
        if prior:
            return prior
        payload = {'tool': 'candidate_admission', 'status': 'queued', 'session': session,
                   '_generation': list(generation), '_candidate': candidate,
                   'reason': 'passed replay; awaiting a paper seat'}
        self.ledger.append('agent.research', payload, agent=agent, id=f'admission-queued:{session}')
        return {'agent': agent, **payload}

    def record(self, row, status, reason, **details):
        if row.get('status') == status and row.get('reason') == reason:
            return
        self.ledger.append('agent.research', {'tool': 'candidate_admission', 'session': row['session'],
            'status': status, 'reason': reason, **details}, agent=row['agent'])
        row.update(status=status, reason=reason, **details)
