"""B-10: (a) unrealized paths: sum of active eval.block log growth by book x desk per window (the
board's W_paper is exp of the sum less the haircut); (b) the base rate for ALL agents (not only replay
passes): share with a positive practice record after >= N active blocks, by venue; (c) sanity: are
the positive agents (mullins-2, mullins-6, meriwether-h2d625d, huang-h51fdd3-2) in the replay-pass
set used by B-6, and how many active blocks do they have; (d) one-loss demotion arithmetic for a bunt."""
import importlib.util, collections, json, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-10.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); BL = B0.blocks(c); BD = B0.boards(c)
last = BD[-1][2]
for wname in ('since 09-22 13:30Z', 'since allocator (09-23 08:28Z)'):
    lo, hi = B0.WINDOWS[wname]
    agg = collections.defaultdict(lambda: [0.0, 0, set(), 0, 0])
    for b in BL:
        if not (lo <= b['at'] < hi) or not b['active']:
            continue
        m = A.get(b['agent']) or {}
        k = (b['book'], m.get('desk'))
        a = agg[k]; a[0] += b['g']; a[1] += 1; a[2].add(b['agent']); a[3] += b['g'] > 0; a[4] += b['g'] < 0
    print(f'\n=== active eval.block log growth {wname}: book | desk | agents | active blocks | sum log | mean log/block | +blocks | -blocks')
    for k, a in sorted(agg.items(), key=lambda kv: kv[1][0]):
        print(f'{k[0]} | {k[1]} | {len(a[2])} | {a[1]} | {a[0]:+.4f} | {a[0]/a[1]:+.5f} | {a[3]} | {a[4]}')
# base rate: all agents with >= N active practice blocks, positive share, by venue and horizon
print('\n=== base rate, all agents ever: practice active blocks and sum log growth')
per = collections.defaultdict(lambda: [0, 0.0])
for b in BL:
    if b['book'] in B0.PRACTICE and b['active']:
        per[b['agent']][0] += 1; per[b['agent']][1] += b['g']
for N in (1, 3, 6, 10, 20):
    for venue in ('kalshi', 'alpaca'):
        v = [(a, x) for a, x in per.items() if x[0] >= N and (A.get(a) or {}).get('venue') == venue]
        if v:
            pos = sum(1 for _, x in v if x[1] > 0)
            print(f'  >= {N} active blocks, {venue}: n {len(v)}, positive {pos} ({pos/len(v)*100:.0f}%), median sum log {B0.med([x[1] for _, x in v]):+.4f}')
print('\n=== the positive agents: replay pass on record? active practice blocks, sum log, board W_paper')
trial = {a for (a,) in c.execute("select distinct agent from ledger where kind='eval.trial' and json_extract(payload,'$.passed')=1")}
for a in ('mullins-2', 'mullins-6', 'mullins-13', 'meriwether-h2d625d', 'huang-h51fdd3-2', 'hawkins-19', 'haghani-56', 'meriwether-36'):
    x = per.get(a, [0, 0.0]); b = last.get(a)
    print(f'  {a}: replay pass {a in trial}; active blocks {x[0]}, sum log {x[1]:+.4f}, board Wp {b[2] if b else None}, horizon {(A.get(a) or {}).get("horizon")}')
# one-loss demotion arithmetic
print('\n=== one-loss demotion arithmetic (allocator.py target_band: E < bunt_at*hysteresis = 1.01*0.85 = 0.8585 sends a bunt to paper; real_drawdown_demote 0.35)')
for wp in (1.01, 1.03, 1.05):
    wr_floor = 0.8585 / math.sqrt(wp)
    print(f'  W_paper {wp}: W_real below {wr_floor:.4f} demotes -> a single lost binary position of more than {(1-wr_floor)*100:.1f}% of the real stake (${(1-wr_floor)*10:.2f} on a $10 bunt) demotes; position_share 0.5 allows ${5:.2f}')
