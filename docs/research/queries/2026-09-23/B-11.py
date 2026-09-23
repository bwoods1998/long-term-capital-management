"""B-11: (a) W_real per real settlement for the real agents from the board series (log W_real gained
per closed real trade, and the implied settlements/days to E 1.5); (b) families re-bred after a member
died of evidence (agent.died cause) -- births of the same family after that death; (c) the allocator's
sweeps since 08:28Z in dollars (book.stake notes)."""
import importlib.util, collections, json, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-11.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); BD = B0.boards(c); ST = B0.settles(c)
print('=== (a) W_real path on the boards for the real agents: agent | first board (W_real, real_trades) | last (W_real, real_trades) | log W_real per real trade | settlements/day | days to W_real needed for E 1.5')
for a in ('mullins-2', 'mullins-6', 'hawkins-19', 'meriwether-h2d625d', 'huang-h51fdd3-2'):
    path = [(at, ag[a][3], ag[a][6], ag[a][2]) for _, at, ag, _, _ in BD if a in ag and len(ag[a]) >= 7]
    if not path: continue
    at0, w0, t0, _ = path[0]; at1, w1, t1, wp = path[-1]
    rs = [s for s in ST if s['agent'] == a and s['book'] == 'kalshi']
    first = min([s['opened_at'] for s in rs if s['opened_at']], default=None)
    days = (B0.ts(B0.SNAP_AT + ':00Z') - B0.ts(first)) / 86400 if first else float('nan')
    per_trade = math.log(w1) / t1 if t1 else float('nan')
    need = 1.5 / math.sqrt(wp)
    todo = (math.log(need) - math.log(w1)) / per_trade if per_trade and per_trade > 0 else float('inf')
    rate = len(rs) / days if days and days > 0 else 0
    print(f'{a} | {at0[5:16]} ({w0:.4f}, {t0}) | {at1[5:16]} ({w1:.4f}, {t1}) | {per_trade:+.4f} | {rate:.1f}/d over {days:.1f} d | needs W_real {need:.3f}: {todo:.0f} more settlements = {todo/rate if rate else float("inf"):.1f} d at the historic rate')
print('\n=== (b) families re-bred after a member died of evidence: family | evidence deaths | births after the first such death | members alive now | alive members practice P&L')
deaths = collections.defaultdict(list)
for a, m in A.items():
    if m.get('cause') == 'evidence':
        deaths[m['family']].append((m['died_at'], a))
pnl = collections.defaultdict(float)
for s in ST:
    if s['book'] == 'kalshi-shadow': pnl[s['agent']] += s['pnl']
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='book.fill' and json_extract(payload,'$.book')='alpaca-paper' and json_extract(payload,'$.realized') is not null"):
    pnl[a] += B0.f(json.loads(pl).get('realized'))
rows = []
for fam, d in deaths.items():
    first = min(x[0] for x in d)
    after = [a for a, m in A.items() if m['family'] == fam and m['born_at'] > first]
    alive = [a for a, m in A.items() if m['family'] == fam and not m.get('died_at')]
    rows.append((fam, len(d), len(after), len(alive), round(sum(pnl[a] for a in alive), 2), after[:4]))
for r in sorted(rows, key=lambda r: -r[2]):
    print(r)
print(f'families with an evidence death: {len(rows)}; re-bred after it: {sum(1 for r in rows if r[2] > 0)}; births after evidence deaths: {sum(r[2] for r in rows)}')
print('\n=== (c) allocator sweeps since 08:28Z')
sw = collections.defaultdict(float); n = 0
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='book.stake' and at>='2026-09-23T08:28' order by seq"):
    p = json.loads(pl)
    if (p.get('note') or '').startswith('allocator'):
        sw[(a, p['book'])] += B0.f(p.get('usd')); n += 1
print({k: round(v, 2) for k, v in sw.items()}, 'total', round(sum(sw.values()), 2), 'moves', n)
