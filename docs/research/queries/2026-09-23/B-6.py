"""B-6 (L3 replay -> practice): for every agent with a passed replay (eval.trial passed=true, the first pass) and a practice record afterwards (eval.block on its practice book): replay
oos_mean_log_growth / sharpe / deflated_sharpe against practice sum of active-block log growth (the
board's W_paper is exp of this less the haircut). Spearman rank correlation; share of replay passes
positive after 6+ active blocks; by desk and family; the ETH prior-window fade generality."""
import importlib.util, collections, json, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-6.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); BL = B0.blocks(c); BD = B0.boards(c)
last = BD[-1][2]
trial = {}
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='eval.trial' order by seq"):
    p = json.loads(pl)
    if p.get('passed') and a not in trial:  # the FIRST pass: blocks after it count
        trial[a] = dict(seq=seq, at=at, oos=B0.f(p.get('oos_mean_log_growth')), sharpe=B0.f(p.get('sharpe')), dsr=B0.f(p.get('deflated_sharpe')),
                        ret=B0.f(p.get('return_pct')), trades=p.get('trades'), blocks=p.get('blocks'), family=p.get('family'), mdd=B0.f(p.get('max_drawdown')))
prac = collections.defaultdict(lambda: dict(active=0, g=0.0, n=0, first=None))
for b in BL:
    if b['book'] in B0.PRACTICE and b['agent'] in trial and b['seq'] > trial[b['agent']]['seq']:
        r = prac[b['agent']]; r['n'] += 1
        if b['active']:
            r['active'] += 1; r['g'] += b['g']; r['first'] = r['first'] or b['at']


def spearman(x, y):
    n = len(x)
    if n < 3: return float('nan')
    rx = {v: i for i, v in enumerate(sorted(range(n), key=lambda i: x[i]))}
    ry = {v: i for i, v in enumerate(sorted(range(n), key=lambda i: y[i]))}
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


pairs = [(a, trial[a], prac[a]) for a in trial if prac[a]['active'] >= 1]
print(f'replay passes on record: {len(trial)}; with >=1 active practice block after the pass: {len(pairs)}; with >=6: {sum(1 for _,_,p in pairs if p["active"]>=6)}')
for minb in (1, 3, 6, 10):
    sub = [(a, t, p) for a, t, p in pairs if p['active'] >= minb]
    if len(sub) < 3: continue
    x = [t['oos'] for _, t, _ in sub]; y = [p['g'] for _, _, p in sub]
    xs = [t['sharpe'] for _, t, _ in sub]; xd = [t['dsr'] for _, t, _ in sub]
    pos = sum(1 for v in y if v > 0)
    print(f'>= {minb} active blocks: n {len(sub)}, practice positive {pos} ({pos/len(sub)*100:.0f}%), mean practice log {sum(y)/len(y):+.4f}, Spearman(oos, practice) {spearman(x,y):+.3f}, Spearman(sharpe, practice) {spearman(xs,y):+.3f}, Spearman(deflated, practice) {spearman(xd,y):+.3f}')
    # replay sign vs practice sign
    q = collections.Counter(('replay+' if t['oos'] > 0 else 'replay-', 'prac+' if p['g'] > 0 else 'prac-') for _, t, p in sub)
    print('   sign table:', dict(q))
    # top replay quartile forward
    sub_sorted = sorted(sub, key=lambda z: -z[1]['oos'])
    k = max(1, len(sub) // 4)
    top = sub_sorted[:k]; bot = sub_sorted[-k:]
    print(f'   top replay quartile (n {k}): mean practice {sum(p["g"] for _,_,p in top)/k:+.4f}, positive {sum(1 for _,_,p in top if p["g"]>0)}; bottom quartile: mean {sum(p["g"] for _,_,p in bot)/k:+.4f}, positive {sum(1 for _,_,p in bot if p["g"]>0)}')
print('\nby desk (>=3 active blocks): desk | n | practice positive | mean practice log | mean replay oos | Spearman')
byd = collections.defaultdict(list)
for a, t, p in pairs:
    if p['active'] >= 3: byd[(A.get(a) or {}).get('desk')].append((t, p))
for d, v in sorted(byd.items(), key=lambda kv: -len(kv[1])):
    x = [t['oos'] for t, _ in v]; y = [p['g'] for _, p in v]
    print(f'{d} | {len(v)} | {sum(1 for g in y if g>0)} | {sum(y)/len(y):+.4f} | {sum(x)/len(x):+.5f} | {spearman(x,y):+.3f}')
print('\nby family (>=2 agents with >=3 active blocks): family | desk | agents | practice positive | sum practice log | mean replay oos')
byf = collections.defaultdict(list)
for a, t, p in pairs:
    if p['active'] >= 3: byf[((A.get(a) or {}).get('family'), (A.get(a) or {}).get('desk'))].append((a, t, p))
fams = [(k, v) for k, v in byf.items() if len(v) >= 2]
neg = 0
for (fam, d), v in sorted(fams, key=lambda kv: sum(p['g'] for _, _, p in kv[1])):
    s = sum(p['g'] for _, _, p in v); neg += s < 0
    print(f'{fam} | {d} | {len(v)} | {sum(1 for _,_,p in v if p["g"]>0)} | {s:+.4f} | {sum(t["oos"] for _,t,_ in v)/len(v):+.5f} | agents {[a for a,_,_ in v][:6]}')
print(f'families with >=2 forward-tested replay passes: {len(fams)}, negative forward: {neg}')
print('\nETH-fade-like families (name contains eth/fade/window):')
for (fam, d), v in byf.items():
    if any(k in (fam or '').lower() for k in ('eth', 'fade', 'window')):
        print(f'  {fam} | {d} | agents {len(v)} | sum practice log {sum(p["g"] for _,_,p in v):+.4f} | replay oos mean {sum(t["oos"] for _,t,_ in v)/len(v):+.5f}')
