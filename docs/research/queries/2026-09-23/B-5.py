"""B-5 (L2 sizing): order size as a share of the $200 practice purse per desk (median, p90) from
book.order rows (each agent share x reference/limit price), since the allocator went live and
since Sept 22 13:30Z; does small sizing explain the slow W; a 3x what-if on the top agents' E
(W3 = prod(1 + 3 r_i) over their closed-trade returns as a share of the purse)."""
import importlib.util, collections, json, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-5.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); F = B0.fills(c); ST = B0.settles(c); BD = B0.boards(c)
last = BD[-1][2]
PURSE = 200.0
for wname in ('since allocator (09-23 08:28Z)', 'since 09-22 13:30Z'):
    lo, hi = B0.WINDOWS[wname]
    sizes = collections.defaultdict(list); agents_seen = collections.defaultdict(set)
    seen = set()
    for seq, at, pl in c.execute("select seq,at,payload from ledger where kind='book.order' and at>=? and at<? order by seq", (lo, hi)):
        p = json.loads(pl)
        oid = p.get('order_id')
        if p.get('book') not in B0.PRACTICE or oid in seen or p.get('side') != 'buy':
            continue
        seen.add(oid)
        px = B0.f(p.get('limit_price')) or B0.f(p.get('reference_price'))
        mult = B0.f((p.get('instrument') or {}).get('multiplier'), 1.0)
        for sh in p.get('shares') or []:
            a = sh.get('agent'); m = A.get(a) or {}
            usd = B0.f(sh.get('quantity')) * px * mult
            if usd > 0:
                sizes[(p['book'], m.get('desk'))].append(usd); agents_seen[(p['book'], m.get('desk'))].add(a)
    print('\n' + '=' * 90 + f'\n{wname}: buy orders on practice books, size as a share of the $200 purse')
    print('book | desk | agents | orders | median $ | median % | p90 $ | p90 % | max $')
    for k, v in sorted(sizes.items()):
        print(f'{k[0]} | {k[1]} | {len(agents_seen[k])} | {len(v)} | {B0.med(v):.2f} | {B0.med(v)/PURSE*100:.1f}% | {B0.pct(v,0.9):.2f} | {B0.pct(v,0.9)/PURSE*100:.1f}% | {max(v):.2f}')
    allv = [x for k, v in sizes.items() if k[0] == 'kalshi-shadow' for x in v]
    print(f'kalshi-shadow all: n {len(allv)} median ${B0.med(allv):.2f} ({B0.med(allv)/PURSE*100:.1f}%) p90 ${B0.pct(allv,0.9):.2f}')
    allv = [x for k, v in sizes.items() if k[0] == 'alpaca-paper' for x in v]
    print(f'alpaca-paper all: n {len(allv)} median ${B0.med(allv):.2f} ({B0.med(allv)/PURSE*100:.1f}%) p90 ${B0.pct(allv,0.9):.2f}')

# per-trade return as share of purse, and what W looks like at 1x and 3x for the top agents
print('\n' + '=' * 90 + '\nclosed-trade returns as a share of the purse (lifetime, practice): agent | desk | n | median $ | median % of purse | W(1x) | W(3x) | E(1x) | E(3x) | board Wp')
rets = collections.defaultdict(list)
for s in ST:
    if s['book'] in B0.PRACTICE: rets[s['agent']].append(s['pnl'] / PURSE)
for r in F:
    if r['book'] in B0.PRACTICE and r['realized'] is not None: rets[r['agent']].append(r['realized'] / PURSE)
rows = []
for a, v in rets.items():
    if len(v) < 3:
        continue
    w1 = math.prod(1 + x for x in v); w3 = math.prod(max(1 + 3 * x, 0.01) for x in v)
    b = last.get(a)
    rows.append((a, (A.get(a) or {}).get('desk'), len(v), B0.med(v) * PURSE, B0.med(v) * 100, w1, w3, math.sqrt(w1), math.sqrt(w3), b[2] if b and len(b) >= 7 else None))
rows.sort(key=lambda x: -x[5])
for x in rows[:12]:
    print(f'{x[0]} | {x[1]} | {x[2]} | {x[3]:+.2f} | {x[4]:+.3f}% | {x[5]:.4f} | {x[6]:.4f} | {x[7]:.4f} | {x[8]:.4f} | {x[9]}')
print('...')
for x in rows[-6:]:
    print(f'{x[0]} | {x[1]} | {x[2]} | {x[3]:+.2f} | {x[4]:+.3f}% | {x[5]:.4f} | {x[6]:.4f} | {x[7]:.4f} | {x[8]:.4f} | {x[9]}')
pos = [x for x in rows if x[5] > 1]
print(f'\nagents with >=3 closed trades: {len(rows)}; W(1x)>1: {len(pos)}; E(1x)>=1.01: {sum(1 for x in rows if x[7]>=1.01)}; E(3x)>=1.01: {sum(1 for x in rows if x[8]>=1.01)}; E(3x)<0.9: {sum(1 for x in rows if x[8]<0.9)}')
# median absolute trade return per desk
byd = collections.defaultdict(list)
for a, v in rets.items():
    byd[(A.get(a) or {}).get('desk')].extend(v)
print('\nmedian |return| per closed trade as % of purse, by desk (lifetime practice):')
for d, v in sorted(byd.items(), key=lambda kv: -len(kv[1])):
    print(f'  {d}: n {len(v)}, median |r| {B0.med([abs(x) for x in v])*100:.3f}%, mean r {sum(v)/len(v)*100:+.3f}%, win {sum(1 for x in v if x>0)}/{len(v)}')
