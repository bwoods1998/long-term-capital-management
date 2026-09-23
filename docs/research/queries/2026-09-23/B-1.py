"""B-1 (L2): realized P&L split by desk, family, horizon, asset class, UTC hour, entry type,
liquidity and founder; practice and real; agents' decisions vs the House's exits; three windows.

Realized = Alpaca sell fills' `realized` (net of fees) + Kalshi settlements' `pnl` (net of fees).
Fees = fee_usd on every fill (both legs). Kalshi entry hour = opened_at of the settled position.
"""
import sys, importlib.util, collections
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-1.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)

c = B0.db(); A = B0.agents(c); F = B0.fills(c); ST = B0.settles(c); O = B0.orders(c)


def meta(a):
    m = A.get(a) or {}
    return m.get('desk') or '?', m.get('family') or '?', m.get('horizon') or '?', m.get('origin') or '?'


def events(lo, hi):
    """one row per closed trade: (book, agent, at, entry_at, pnl, fee, notional, asset, liq, otype, house_exit)."""
    out = []
    for r in F:
        if r['realized'] is None or not (lo <= r['at'] < hi):
            continue
        o = O.get(r['order_id']) or {}
        out.append(dict(book=r['book'], agent=r['agent'], at=r['at'], entry_at=r['opened_at'] or r['at'], pnl=r['realized'],
                        fee=r['fee'], notional=r['notional'], asset=r['asset'], liq=r['liq'], otype=o.get('type') or '?',
                        house=r['house_exit'], kind='sell'))
    for s in ST:
        if not (lo <= s['at'] < hi):
            continue
        died = (A.get(s['agent']) or {}).get('died_at')
        house = bool(died and died < s['at'])  # settled after the agent died: the House held it to settlement
        out.append(dict(book=s['book'], agent=s['agent'], at=s['at'], entry_at=s['opened_at'] or s['at'], pnl=s['pnl'], fee=0.0,
                        notional=s['cost'], asset=s['asset'], liq=None, otype='settle', house=house, kind='settle'))
    # fees on buys in the window (both legs count as cost)
    return out


def split(rows, key):
    agg = collections.defaultdict(lambda: [0.0, 0.0, 0, 0.0, 0])  # pnl agents, pnl house, n, notional, n_house
    for r in rows:
        k = key(r)
        a = agg[k]
        if r['house']:
            a[1] += r['pnl']; a[4] += 1
        else:
            a[0] += r['pnl']; a[2] += 1
        a[3] += r['notional']
    return agg


def show(title, agg, top=40):
    print(f'\n### {title}: key | agent P&L $ | n | per trade $ | House-exit P&L $ | n_house | notional $')
    for k, v in sorted(agg.items(), key=lambda kv: kv[1][0] + kv[1][1])[:top]:
        per = v[0] / v[2] if v[2] else float('nan')
        print(f'{k} | {v[0]:+.2f} | {v[2]} | {per:+.3f} | {v[1]:+.2f} | {v[4]} | {v[3]:.0f}')


for wname, (lo, hi) in B0.WINDOWS.items():
    rows = events(lo, hi)
    print('\n' + '=' * 100 + f'\nWINDOW {wname}: {len(rows)} closed trades/settlements')
    fees = collections.defaultdict(float)
    for r in F:
        if lo <= r['at'] < hi:
            fees[r['book']] += r['fee']
    print('fees paid on fills by book (both legs):', {k: round(v, 2) for k, v in fees.items()})
    show('by book', split(rows, lambda r: r['book']))
    show('by book x desk', split(rows, lambda r: (r['book'], meta(r['agent'])[0])))
    show('by book x family', split(rows, lambda r: (r['book'], meta(r['agent'])[1])), top=60)
    show('by book x horizon', split(rows, lambda r: (r['book'], meta(r['agent'])[2])))
    show('by book x asset class', split(rows, lambda r: (r['book'], r['asset'])))
    show('by book x order type', split(rows, lambda r: (r['book'], r['otype'])))
    show('by book x liquidity (exit fill)', split(rows, lambda r: (r['book'], r['liq'])))
    show('by book x founder class', split(rows, lambda r: (r['book'], meta(r['agent'])[3])))
    show('by practice/real x entry UTC hour', split(rows, lambda r: ('real' if r['book'] in B0.REAL else 'practice', r['entry_at'][11:13])), top=48)
    show('by book x agent (worst 25)', split(rows, lambda r: (r['book'], r['agent'])), top=25)
    agg = split(rows, lambda r: (r['book'], r['agent']))
    print('\n### best 12 agents by P&L')
    for k, v in sorted(agg.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:12]:
        print(f'{k} | {v[0]:+.2f} | {v[2]} | house {v[1]:+.2f}')
