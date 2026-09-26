"""B-0: shared read-only loaders over the 16:28Z snapshot (imported by B-1 .. B-9).

Ledger facts used (checked against league/book.py, league/allocator.py, league/evaluator.py):
- book.fill: Alpaca sells carry `realized` (net of fees, basis includes the buy fee); every Kalshi
  fill is a buy with realized null; Kalshi P&L is book.settle.pnl (= payout - cost, cost includes fee).
- House wind-down exits are logged under the dead agent's name with reason
  "the House is closing this account..." (house.py _wind_down); the horizon rule's exits say
  "The House's horizon rule" (house.py:2664). Dust / venue-fee / cross-house rows are agent=house.
- alloc.board.agents[a] = [band, stake, W_paper, W_real, E, trades, real_trades] (allocator.py _publish_board).
"""
import json
import sqlite3
import pathlib
import collections
import statistics
from datetime import datetime, timezone

S = pathlib.Path('/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad')
SNAP = S / 'snap' / 'ledger.sqlite'
SNAP_AT = '2026-09-23T16:28'
PRACTICE = ('alpaca-paper', 'kalshi-shadow')
REAL = ('alpaca', 'kalshi')
WINDOWS = {
    'since 09-22 13:30Z': ('2026-09-22T13:30', '2026-09-23T16:29'),
    'last 24h (09-22 16:28Z..)': ('2026-09-22T16:28', '2026-09-23T16:29'),
    'since allocator (09-23 08:28Z)': ('2026-09-23T08:28', '2026-09-23T16:29'),
    'today 06:30-16:00Z': ('2026-09-23T06:30', '2026-09-23T16:00'),
}
HOUSE_EXIT = ('the House is closing this account', "The House's horizon rule")


def db():
    return sqlite3.connect(SNAP.as_uri() + '?mode=ro', uri=True)


def f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def ts(at):
    return datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp()


def founder_class(reason: str) -> str:
    r = (reason or '').lower()
    if r.startswith('merton, as architect') or 'architect' in r[:60]:
        return 'architect'
    if 'repair' in r[:120] or 'engineer' in r[:80]:
        return 'repair'
    if 'alpha lab' in r or 'the lab' in r[:80] or r.startswith('lab') or 'graduat' in r[:120]:
        return 'lab'
    if 'foundry' in r or 'hypothesis card' in r or r.startswith('card') or 'card ' in r[:60]:
        return 'foundry'
    if 'founder' in r[:80]:
        return 'house-founder'
    return 'house'


def agents(c=None):
    """agent -> meta from agent.born (+ death)."""
    c = c or db()
    out = {}
    for a, at, pl in c.execute("select agent,at,payload from ledger where kind='agent.born' order by seq"):
        p = json.loads(pl)
        out[a] = {'family': p.get('family'), 'desk': p.get('specialty'), 'horizon': p.get('horizon'),
                  'venue': p.get('venue'), 'founder': p.get('founder'), 'style': p.get('style'),
                  'origin': founder_class(p.get('reason') or ''), 'born_at': at, 'parent': p.get('parent'),
                  'reason': (p.get('reason') or '')[:160], 'died_at': None, 'cause': None,
                  'params': p.get('params'), 'needs': p.get('needs')}
    for a, at, pl in c.execute("select agent,at,payload from ledger where kind='agent.died' order by seq"):
        p = json.loads(pl)
        if a in out:
            out[a]['died_at'] = at
            out[a]['cause'] = p.get('cause')
    return out


def fills(c=None, sources=('venue', 'cross')):
    c = c or db()
    rows = []
    for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='book.fill' order by seq"):
        p = json.loads(pl)
        if p.get('source') not in sources:
            continue
        inst = p.get('instrument') or {}
        mult = f(inst.get('multiplier'), 1.0)
        q, px = f(p.get('quantity')), f(p.get('price'))
        reason = p.get('reason') or ''
        rows.append({'seq': seq, 'agent': a, 'at': at, 'book': p['book'], 'side': p.get('side'), 'q': q, 'px': px,
                     'notional': abs(q * px * mult), 'fee': f(p.get('fee_usd')), 'venue_fee': f(p.get('venue_fee')),
                     'realized': None if p.get('realized') is None else f(p.get('realized')), 'flat': p.get('flat'),
                     'liq': p.get('liquidity'), 'order_id': p.get('order_id'), 'intent_id': p.get('intent_id'),
                     'opened_at': p.get('opened_at'), 'asset': inst.get('asset_class'), 'symbol': inst.get('symbol') or inst.get('market_id'),
                     'reason': reason, 'entry_reason': p.get('entry_reason'), 'source': p.get('source'),
                     'house_exit': reason.startswith(HOUSE_EXIT), 'real': bool(p.get('real_money'))})
    return rows


def settles(c=None):
    c = c or db()
    rows = []
    for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='book.settle' order by seq"):
        p = json.loads(pl)
        inst = p.get('instrument') or {}
        rows.append({'seq': seq, 'agent': a, 'at': at, 'book': p['book'], 'pnl': f(p.get('pnl')), 'cost': f(p.get('cost')),
                     'payout': f(p.get('payout')), 'q': f(p.get('quantity')), 'opened_at': p.get('opened_at'),
                     'symbol': inst.get('symbol') or inst.get('market_id'), 'asset': inst.get('asset_class'),
                     'result': p.get('result'), 'right': inst.get('right'), 'reason': p.get('reason') or '', 'real': bool(p.get('real_money'))})
    return rows


def orders(c=None):
    """order_id -> the last book.order row (status), plus the first reference price and type."""
    c = c or db()
    out = {}
    for seq, at, pl in c.execute("select seq,at,payload from ledger where kind='book.order' order by seq"):
        p = json.loads(pl)
        oid = p.get('order_id')
        if not oid:
            continue
        row = out.setdefault(oid, {'book': p.get('book'), 'type': p.get('order_type'), 'liq': p.get('liquidity'),
                                   'ref': f(p.get('reference_price'), None), 'limit': f(p.get('limit_price'), None),
                                   'side': p.get('side'), 'statuses': [], 'first_at': at, 'post_only': p.get('post_only'),
                                   'shares': p.get('shares') or [], 'q': f(p.get('quantity')),
                                   'asset': (p.get('instrument') or {}).get('asset_class'), 'real': bool(p.get('real_money'))})
        row['statuses'].append(p.get('status'))
        row['last'] = p.get('status')
        row['last_reason'] = p.get('reason')
    return out


def boards(c=None):
    c = c or db()
    out = []
    for seq, at, pl in c.execute("select seq,at,payload from ledger where kind='alloc.board' order by seq"):
        p = json.loads(pl)
        out.append((seq, at, p.get('agents') or {}, p.get('throttle'), p.get('envelope')))
    return out


def blocks(c=None):
    c = c or db()
    rows = []
    for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='eval.block' order by seq"):
        p = json.loads(pl)
        rows.append({'seq': seq, 'agent': a, 'at': at, 'book': p.get('book'), 'key': p.get('key'), 'active': bool(p.get('active')),
                     'g': f(p.get('log_growth')), 'exposure': f(p.get('exposure')), 'start': f(p.get('start_equity')),
                     'end': f(p.get('end_equity')), 'first_mark_seq': p.get('first_mark_seq'), 'horizon': p.get('horizon')})
    return rows


def pct(v, q):
    if not v:
        return float('nan')
    v = sorted(v)
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def med(v):
    return statistics.median(v) if v else float('nan')


if __name__ == '__main__':
    A = agents()
    print('agents', len(A), collections.Counter(a['origin'] for a in A.values()))
    pre = collections.Counter(a['reason'][:45] for a in A.values())
    for k, v in pre.most_common(25):
        print(v, repr(k))
