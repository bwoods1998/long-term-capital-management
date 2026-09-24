"""Durable paper-candidate admission, folded from the append-only research record.

A full desk is a wait, not a discarded experiment. An uncertain lifecycle write is never
retried automatically. Candidate source remains private, and old deferred receipts retain
their original session identity so installing this queue does not require rewriting history.
"""
from __future__ import annotations

import copy
import threading
import weakref
from typing import Any

from .ledger import Ledger


def _admission(p: Any) -> bool:
    """Is this `agent.research` payload part of an admission: an admission's own receipt, or a research
    candidate whose fork is deferred, done, failed or unconfirmed."""
    if p.get('tool') not in ('candidate', 'candidate_admission') or not p.get('session'):
        return False
    return not (p.get('tool') == 'candidate' and p.get('status') not in ('deferred', 'forked', 'fork_error', 'commit_unconfirmed'))


def _fold(found: dict[str, dict[str, Any]], entry: Any) -> None:
    p = entry.payload
    if not _admission(p):
        return
    session = p['session']
    row = found.setdefault(session, {'session': session, 'agent': entry.agent, 'created_seq': entry.seq})
    row.update(p)


class _Fold:
    """Every admission one ledger holds, folded once, then only from the rows after `cursor`.

    Sept 24, 2026 (R6-perf): `rows()` read every `agent.research` row there is to find the admissions
    among them -- on the snapshot of 17:27Z, 79,585 rows and 46.7 MB of JSON for 1,588 sessions, about
    1.1 s of CPU on the developer machine each time -- and the House asked on every tick (health.json
    `candidate_admissions`), at each newcomer turn (`_refill`) and twice for each research candidate it
    admits (`enqueue`, on the research threads). The ledger is append-only and the fold reads rows in
    sequence order, so folding the new rows onto the old answer IS the answer read afresh."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cursor = 0
        self.found: dict[str, dict[str, Any]] = {}

    def rows(self, ledger: Ledger) -> list[dict[str, Any]]:
        with self.lock:
            for entry in ledger.iter(kinds='agent.research', after=self.cursor):
                _fold(self.found, entry)
                self.cursor = entry.seq
            # Copies, as a fresh read's were: a caller's `record` updates its own row, never the fold's.
            return copy.deepcopy(sorted(self.found.values(), key=lambda r: r['created_seq']))


#: One fold a ledger, shared by every `Admissions` over it (the House builds one for each question).
_FOLDS: weakref.WeakKeyDictionary[Ledger, _Fold] = weakref.WeakKeyDictionary()
_FOLDS_LOCK = threading.Lock()


class Admissions:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def rows(self, agent=None):
        """Every admission, folded by session; `agent` reads one author's rows only (its own index). The
        whole queue is folded incrementally (`_Fold`); one author's is read afresh, as before."""
        if agent is None:
            with _FOLDS_LOCK:
                fold = _FOLDS.get(self.ledger)
                if fold is None:
                    fold = _FOLDS[self.ledger] = _Fold()
            return fold.rows(self.ledger)
        found = {}
        for entry in self.ledger.iter(kinds='agent.research', agent=agent):
            _fold(found, entry)
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
