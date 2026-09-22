"""House-funded startup research, separate from rewards for demonstrated trading skill.

One nonrenewable grant per family/niche in the current campaign, twelve for the whole floor.
The claim is durable before inference; an interrupted/ambiguous call never buys a replacement.
Children and restarts cannot reset it. Candidate code still needs the normal replay/adoption
path. These grants confer neither trading credit nor qualification.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .campaigns import CampaignClosed
from .frontier import Frontier, FrontierError
from .merton import CONSULT

MODEL = 'gpt-6-luna'  # the research model (league/fast_research.py)
MAX_GRANTS = 12
MAX_CALL_USD = Decimal('0.25')  # at most $3 reserved; inside foundation-review, not extra money


class GrantGuard:
    def __init__(self, campaign):
        self.campaign = campaign

    def reserve(self, ident, name, amount):
        if Decimal(amount) > MAX_CALL_USD:
            raise CampaignClosed('research grant exceeds its per-call reservation ceiling')
        return self.campaign.reserve(ident, name, amount)

    def settle(self, ident, amount):
        return self.campaign.settle(ident, amount)


class ResearchGrants:
    def __init__(self, path, frontier, ledger, *, phase: str, clock=time.time):
        self.path, self.frontier, self.ledger = Path(path), frontier, ledger
        self.phase, self.clock = phase, clock
        db = self._db()
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS grants (
                phase TEXT, family TEXT, niche TEXT, agent TEXT, session TEXT, created REAL,
                status TEXT, reply TEXT, PRIMARY KEY(phase,family,niche))''')
            db.commit()
        finally:
            db.close()

    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        return db

    @classmethod
    def funded(cls, path, gateway_url, token, ledger, campaign, *, clock=time.time):
        model = Frontier(gateway_url, token, model=MODEL, spend_guard=GrantGuard(campaign))
        return cls(path, model, ledger, phase=f'{campaign.started:.6f}', clock=clock)

    def request(self, agent, proposal, evidence, *, session, contract):
        record = evidence.get('record') or {}
        if int(record.get('rung', 0)) > 1 or int(record.get('active_blocks') or 0) > 0:
            return {'error': 'startup grants are for untraded research/paper agents; use earned consultation'}
        fields = ('question', 'hypothesis', 'acceptance_check')
        if any(not isinstance(proposal.get(k), str) or len(proposal[k].strip()) < 30 for k in fields):
            return {'error': 'supply a specific question, falsifiable hypothesis and acceptance_check (30+ characters each)'}
        proposal = {k: proposal[k].strip()[:2000] for k in fields}
        key = (self.phase, agent.family, agent.niche)
        # Each invocation owns a separate connection: concurrent workers/restarted processes
        # serialize admission in SQLite, without holding a transaction over a network call.
        db = self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT session,status,reply FROM grants WHERE phase=? AND family=? AND niche=?', key).fetchone()
            if prior:
                if prior[0] == session and prior[1] == 'completed':
                    return json.loads(prior[2])
                return {'error': 'this family/niche already used its startup grant; birth, death and restart do not renew it'}
            if db.execute('SELECT COUNT(*) FROM grants WHERE phase=?', (self.phase,)).fetchone()[0] >= MAX_GRANTS:
                return {'error': 'the campaign startup-grant allocation is exhausted'}
            db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,NULL)', (*key, agent.id, session, self.clock(), 'claimed'))
            db.commit()
        finally:
            db.close()
        ident = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        self.ledger.append('agent.research', {'tool': 'research_grant', 'status': 'claimed',
            'session': session, 'model': self.frontier.model, 'proposal': proposal,
            'max_reserved_usd': str(MAX_CALL_USD)}, agent=agent.id, id='grant-claim:'+ident)
        reply = None
        try:
            reply = self.frontier.ask(system=CONSULT + '\n\nHouse startup research grant: resolve the stated hypothesis. '
                'Preserve known-good code when repairing it. Propose no qualification or budget changes. '
                'Report missing evidence explicitly; your confidence does not establish profit.\n\n' + contract,
                user=json.dumps({'proposal': proposal, 'evidence': evidence}, default=str),
                agent='grant-'+agent.id, max_output_tokens=8000, effort='medium')
            answer = reply.json()
            if not isinstance(answer.get('answer'), str) or len(answer['answer'].strip()) < 20:
                raise FrontierError('grant returned no usable answer')
            if answer.get('code') is not None and not isinstance(answer['code'], str):
                raise FrontierError('grant strategy must be source text')
            result = {'answer': answer['answer'][:6000], 'code': answer.get('code') or '',
                'confidence': str(answer.get('confidence') or 'low')[:20], 'model': reply.model,
                'cost_usd': str(reply.cost_usd), 'house_funded': True,
                'note': 'Proposed code only. Preflight inputs and replay it; the House applies normal qualification rules.'}
        except FrontierError as exc:
            result = {'error': str(exc)[:300], 'house_funded': True,
                'cost_usd': str(reply.cost_usd) if reply else None,
                'note': 'Grant consumed; unknown bills retain their campaign reservation. No automatic retry.'}
        db = self._db()
        try:
            with db:
                db.execute('UPDATE grants SET status=?,reply=? WHERE phase=? AND family=? AND niche=?',
                           ('completed', json.dumps(result), *key))
        finally:
            db.close()
        self.ledger.append('agent.research', {'tool': 'research_grant', 'status': 'completed', 'session': session,
            **{k: v for k, v in result.items() if k != 'code'}, 'wrote_code': bool(result.get('code'))},
            agent=agent.id, id='grant-result:'+ident)
        return result
