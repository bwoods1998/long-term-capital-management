"""Refresh (21:36Z snapshot): what changed after the 16:28Z snapshot and after Deploy A (17:34Z).
python3 R-1.py <ledger.sqlite> <lab.sqlite>"""
import json, sqlite3, sys, collections, datetime
db = sqlite3.connect(sys.argv[1]); lab = sqlite3.connect(sys.argv[2])
T0, A = '2026-09-23T16:28', '2026-09-23T17:34:17'
born = {a: json.loads(p) for a, p in db.execute("select agent, payload from ledger where kind='agent.born'")}
desk = lambda a: (born.get(a) or {}).get('specialty') or '?'
def rows(kind, since):
    return [(at, a, json.loads(p)) for at, a, p in db.execute("select at, agent, payload from ledger where kind=? and at>=? order by seq", (kind, since))]
print('== funnel since 16:28Z')
births = collections.Counter(); deaths = collections.Counter()
for at, a, p in rows('agent.born', T0):
    f = str(p.get('founder') or ''); r = str(p.get('reason') or '')
    births['lab' if f.startswith('lab:') else 'card' if f.startswith('card:') else 'architect/repair' if r.startswith('Merton') else 'house']  += 1
for at, a, p in rows('agent.died', T0): deaths[p.get('cause')] += 1
print(' births', dict(births), ' deaths', dict(deaths))
moves = [(at[11:19], a, p.get('decision'), p.get('from_rung'), p.get('to_rung')) for at, a, p in rows('eval.verdict', T0) if p.get('decision') in ('promote', 'demote')]
up = collections.Counter((m[3], m[4]) for m in moves if m[2] == 'promote'); dn = collections.Counter((m[3], m[4]) for m in moves if m[2] == 'demote')
print(' promotions', dict(up), ' demotions', dict(dn))
print(' to real money:', [(m[0], m[1]) for m in moves if m[2] == 'promote' and m[4] == 2])
print('== real money since Deploy A')
pnl = collections.defaultdict(float); n = collections.Counter(); notional = collections.defaultdict(float)
for at, a, p in rows('book.fill', A):
    if p.get('book') in ('kalshi', 'alpaca') and p.get('source') != 'dust':
        n[p['book'] + ' fills'] += 1; notional[p['book']] += abs(float(p['quantity']) * float(p['price']) * float((p.get('instrument') or {}).get('multiplier') or 1))
        if p.get('realized') is not None: pnl[p['book']] += float(p['realized'])
for at, a, p in rows('book.settle', A):
    if p.get('book') in ('kalshi', 'alpaca'): n[p['book'] + ' settles'] += 1; pnl[p['book']] += float(p.get('pnl') or 0)
print(' ', dict(n), {k: round(v, 2) for k, v in notional.items()}, 'realized', {k: round(v, 2) for k, v in pnl.items()})
print('== practice since 16:28Z (agents only; realized + settlements)')
pp = collections.defaultdict(float); pn = collections.Counter()
for at, a, p in rows('book.fill', T0):
    if p.get('book') in ('alpaca-paper', 'kalshi-shadow') and p.get('source') != 'dust' and p.get('realized') is not None and 'House is closing' not in str(p.get('reason') or ''):
        pp[(p['book'], desk(a))] += float(p['realized']); pn[(p['book'], desk(a))] += 1
for at, a, p in rows('book.settle', T0):
    if p.get('book') == 'kalshi-shadow': pp[(p['book'], desk(a))] += float(p.get('pnl') or 0); pn[(p['book'], desk(a))] += 1
tot = collections.defaultdict(float)
for (b, d), v in sorted(pp.items(), key=lambda kv: kv[1]): tot[b] += v; print(f'  {b:13} {d:24} {v:9.2f} ({pn[(b, d)]})')
print('  totals', {k: round(v, 2) for k, v in tot.items()})
print('== stock and options desks since Deploy A (practice)')
st = collections.Counter()
for kind in ('agent.woke', 'agent.intent', 'book.fill', 'book.refused'):
    for at, a, p in rows(kind, A):
        d = desk(a)
        if d not in ('alpaca-index-etfs', 'alpaca-megacaps', 'alpaca-options', 'alpaca-open'): continue
        if kind == 'book.fill' and (p.get('source') == 'dust' or 'House is closing' in str(p.get('reason') or '')): continue
        st[(d, kind)] += 1
print(' ', dict(sorted(st.items())))
fl = collections.Counter()
for at, a, p in rows('book.order', A):
    inst = p.get('instrument') or {}
    if inst.get('asset_class') == 'equity' and p.get('order_type') == 'limit':
        q = str(p.get('quantity')); fl['fractional' if '.' in q and float(q) != int(float(q)) else 'whole'] += 1
print('  equity limit orders since A:', dict(fl))
print('== lab')
ev = lab.execute("select count(*) from candidates where evaluated >= ?", (datetime.datetime(2026, 9, 23, 16, 28, tzinfo=datetime.timezone.utc).timestamp(),)).fetchone()[0]
byo = dict(lab.execute("select origin, count(*) from candidates where evaluated is not null group by origin").fetchall())
print('  evaluated since 16:28Z', ev, ' evaluated by origin (lifetime)', byo)
print('  graduations by state', dict(lab.execute("select state, count(*) from graduations group by state").fetchall()))
hours = collections.Counter(datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%H') for (t,) in lab.execute("select evaluated from candidates where evaluated >= ?", (datetime.datetime(2026, 9, 23, 16, 0, tzinfo=datetime.timezone.utc).timestamp(),)))
print('  evaluated per UTC hour', dict(sorted(hours.items())))
print('== research gate triggers since 16:28Z')
gt = collections.Counter((p.get('decision'), p.get('trigger')) for at, a, p in rows('research.gate', T0))
print(' ', dict(gt.most_common(10)))
