"""B-9 (L3 is E fair across venues): W_paper distribution by venue on the last board; the rate at
which each venue's paper agents reach E >= 1.01 with enough trades (Kalshi 3 settlements, Alpaca 5
closed trades); time from the first board appearance to the bunt line; and the size of a single
closed trade's effect on W per venue."""
import importlib.util, collections, json, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-9.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); BD = B0.boards(c); ST = B0.settles(c); F = B0.fills(c)
last = BD[-1][2]
settled = collections.Counter(s['agent'] for s in ST if s['book'] == 'kalshi-shadow')
byv = collections.defaultdict(list)
for a, r in last.items():
    if len(r) < 7: continue
    v = (A.get(a) or {}).get('venue') or '?'
    byv[v].append((a, r))
print('last board', BD[-1][1])
for v, rows in byv.items():
    wp = [r[2] for _, r in rows]
    enough = [(a, r) for a, r in rows if (r[5] >= 5 or (v == 'kalshi' and settled[a] >= 3))]
    q = [(a, r) for a, r in enough if r[4] >= 1.01]
    traded = [(a, r) for a, r in rows if r[5] >= 1]
    print(f'\n{v}: agents on board {len(rows)}; W_paper median {B0.med(wp):.4f}, p25 {B0.pct(wp,0.25):.4f}, p75 {B0.pct(wp,0.75):.4f}, >1: {sum(1 for x in wp if x>1)}, ==1 (no record): {sum(1 for x in wp if abs(x-1)<1e-9)}')
    print(f'   with >=1 closed trade: {len(traded)}; with enough trades for a bunt: {len(enough)}; of those E>=1.01: {len(q)} ({len(q)/len(enough)*100 if enough else 0:.0f}%); bands: {collections.Counter(r[0] for _, r in rows)}')
    print('   E>=1.01 & enough:', [(a, round(r[4], 4), r[5]) for a, r in q])
    print('   E>=1.01 but not enough trades:', [(a, round(r[4], 4), r[5], settled[a]) for a, r in rows if r[4] >= 1.01 and (a, r) not in enough])
# how far the ever-qualifiers got, over the board series
print('\n=== across all 83 boards: agents that ever met the bunt line (E>=1.01 with enough trades) by venue, and how long after their first board row')
first_seen = {}; ever = {}
for seq, at, ag, _, _ in BD:
    for a, r in ag.items():
        if len(r) < 7: continue
        first_seen.setdefault(a, at)
        v = (A.get(a) or {}).get('venue')
        enough = r[5] >= 5 or (v == 'kalshi' and sum(1 for s in ST if s['agent'] == a and s['book'] == 'kalshi-shadow' and s['seq'] <= seq) >= 3)
        if enough and r[4] >= 1.01 and a not in ever:
            ever[a] = at
cnt = collections.Counter((A.get(a) or {}).get('venue') for a in ever)
tot = collections.Counter((A.get(a) or {}).get('venue') for a in first_seen)
print('ever qualified by venue:', dict(cnt), 'of agents seen on boards:', dict(tot))
for a, at in sorted(ever.items(), key=lambda kv: kv[1]):
    print(f'  {a} ({(A.get(a) or {}).get("venue")}, {(A.get(a) or {}).get("desk")}): first board {first_seen[a][5:16]}, met line {at[5:16]}, now {last.get(a, ["gone"])[0]}')
# per-trade effect on W by venue: median |pnl|/purse per closed practice trade
per = collections.defaultdict(list)
for s in ST:
    if s['book'] == 'kalshi-shadow': per['kalshi'].append(abs(s['pnl']) / 200)
for r in F:
    if r['book'] == 'alpaca-paper' and r['realized'] is not None: per['alpaca'].append(abs(r['realized']) / 200)
for v, x in per.items():
    print(f'{v}: median |closed-trade P&L| as % of the purse {B0.med(x)*100:.3f}% (n {len(x)}); trades needed at that size for +1% W: {1/ (B0.med(x)*100) if x else float("nan"):.0f}')
# real-venue block counts: hour vs day horizon per venue
hz = collections.Counter(((A.get(a) or {}).get('venue'), (A.get(a) or {}).get('horizon')) for a in last)
print('horizon by venue on the board:', dict(hz))
