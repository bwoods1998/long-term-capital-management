"""B-4 (L2 winners/losers): for the top 5 practice records (W_paper on the last board, >=3 closed
trades), the real records (W_real) and the 5 worst: mechanism (agent.born style/family/params and
the first lines of the strategy code), size per trade as a share of the purse, trades/day, hold time,
maker share, and where the P&L came from (settlement vs resale)."""
import importlib.util, collections, json, re
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-4.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); F = B0.fills(c); ST = B0.settles(c); BD = B0.boards(c)
last = BD[-1][2]
PURSE = 200.0


def code_of(a):
    r = c.execute("select payload from ledger where kind in ('agent.strategy','agent.born') and agent=? order by seq desc limit 1", (a,)).fetchone()
    if not r:
        return ''
    return json.loads(r[0]).get('_code') or ''


def profile(a):
    m = A.get(a) or {}
    book_p = 'kalshi-shadow' if m.get('venue') == 'kalshi' else 'alpaca-paper'
    book_r = 'kalshi' if m.get('venue') == 'kalshi' else 'alpaca'
    out = {}
    for label, book in (('practice', book_p), ('real', book_r)):
        fl = [r for r in F if r['agent'] == a and r['book'] == book]
        st = [s for s in ST if s['agent'] == a and s['book'] == book]
        buys = [r for r in fl if r['side'] == 'buy']
        sells = [r for r in fl if r['realized'] is not None]
        if not fl and not st:
            continue
        first = min(r['at'] for r in fl); lastat = max([r['at'] for r in fl] + [s['at'] for s in st])
        days = max((B0.ts(lastat) - B0.ts(first)) / 86400, 1 / 24)
        closed = len(st) + len(sells)
        pnl = sum(s['pnl'] for s in st) + sum(r['realized'] for r in sells)
        holds = [(B0.ts(s['at']) - B0.ts(s['opened_at'])) / 3600 for s in st if s['opened_at']] + [(B0.ts(r['at']) - B0.ts(r['opened_at'])) / 3600 for r in sells if r['opened_at']]
        maker = sum(1 for r in fl if r['liq'] == 'maker')
        sizes = [r['notional'] for r in buys]
        base = PURSE if label == 'practice' else None
        if label == 'real':
            stk = [B0.f(json.loads(pl).get('usd')) for (pl,) in c.execute("select payload from ledger where kind='book.stake' and agent=? and json_extract(payload,'$.book')=?", (a, book))]
            base = max(sum(stk), 10.0)
        rets = [s['pnl'] / s['cost'] for s in st if s['cost']] + [r['realized'] / (r['notional'] - r['realized']) for r in sells if r['notional']]
        out[label] = dict(fills=len(fl), closed=closed, pnl=round(pnl, 2), days=round(days, 2), per_day=round(closed / days, 2),
                          hold_h=round(B0.med(holds), 2) if holds else None, maker=f'{maker}/{len(fl)}',
                          size_med=round(B0.med(sizes), 2) if sizes else None, size_share=f'{B0.med(sizes)/base*100:.1f}%' if sizes else None,
                          ret_med=f'{B0.med(rets)*100:+.2f}%' if rets else None, win=f'{sum(1 for x in rets if x>0)}/{len(rets)}',
                          settled=len(st), fees=round(sum(r['fee'] for r in fl), 2), symbols=collections.Counter(r['symbol'][:10] for r in buys).most_common(3))
    return out


rows = [(a, r) for a, r in last.items() if len(r) >= 7]
prac = sorted([(a, r) for a, r in rows if r[5] >= 3], key=lambda x: -x[1][2])
real = sorted([(a, r) for a, r in rows if r[6] >= 1 or r[0] in ('bunt', 'swing')], key=lambda x: -x[1][3])
worst = sorted([(a, r) for a, r in rows if r[5] >= 3], key=lambda x: x[1][2])
# dead agents are not on the board: take the worst practice records from settlements/fills too
dead_pnl = collections.defaultdict(float)
for s in ST:
    if s['book'] in B0.PRACTICE: dead_pnl[s['agent']] += s['pnl']
for r in F:
    if r['book'] in B0.PRACTICE and r['realized'] is not None: dead_pnl[r['agent']] += r['realized']
worst_dead = sorted(dead_pnl.items(), key=lambda kv: kv[1])[:5]

for title, group in (('TOP 5 PRACTICE (W_paper, >=3 trades)', prac[:5]), ('REAL RECORDS (W_real)', real), ('WORST 5 ON BOARD (W_paper, >=3 trades)', worst[:5])):
    print('\n' + '=' * 100 + '\n' + title)
    for a, r in group:
        m = A.get(a) or {}
        code = code_of(a)
        doc = re.search(r'"""(.*?)"""', code, re.S)
        style = re.search(r'"style":\s*"([^"]+)"', code)
        print(f"\n--- {a} | {m.get('venue')} {m.get('desk')} | family {m.get('family')} | horizon {m.get('horizon')} | origin {m.get('origin')} | band {r[0]} stake {r[1]} | Wp {r[2]:.4f} Wr {r[3]:.4f} E {r[4]:.4f} trades {r[5]} real {r[6]}")
        print(f"    style: {style.group(1) if style else m.get('style')} | params {m.get('params')} | born {m.get('born_at','')[5:16]} | parent {m.get('parent')}")
        print(f"    born reason: {m.get('reason','')[:150]}")
        if doc: print('    doc:', ' '.join(doc.group(1).split())[:300])
        for label, p in profile(a).items():
            print(f'    {label}: {p}')
print('\n' + '=' * 100 + '\nWORST 5 LIFETIME PRACTICE P&L (incl. dead):')
for a, v in worst_dead:
    m = A.get(a) or {}
    print(f"\n--- {a} | {m.get('venue')} {m.get('desk')} | family {m.get('family')} | origin {m.get('origin')} | died {m.get('died_at')} {m.get('cause')} | P&L ${v:+.2f}")
    print(f"    born reason: {m.get('reason','')[:150]}")
    for label, p in profile(a).items():
        print(f'    {label}: {p}')
