"""B-2 (L2): decompose today's practice losses (06:30-16:00Z) into signal, costs, sizing and the
House's exits of dead agents' positions.

Costs measured: (a) venue fees on both legs (fee_usd), (b) the allocator's 10 bps/side Alpaca practice
haircut (constitution allocator.evidence.alpaca_paper_haircut_bps; NOT in the book's realized, so
reported beside it), (c) slippage of taker fills against the order's reference price (book.order
`reference_price` = the touch for market orders, the limit for limit orders; book.py _route).
The half-spread itself (touch vs mid) is not on the ledger: it needs quotes at intent time.
Signal-at-touch = realized + fees (what the entries and exits made before venue costs).
Sizing = the share of net loss that came from the largest 10% of closed positions by entry notional.
"""
import importlib.util, collections
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-2.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); F = B0.fills(c); ST = B0.settles(c); O = B0.orders(c)
lo, hi = B0.WINDOWS['today 06:30-16:00Z']
HAIRCUT_BPS = 10

for book in ('alpaca-paper', 'kalshi-shadow'):
    print('\n' + '=' * 90 + f'\n{book} {lo}..{hi}')
    closes = []  # (pnl_net, fee_exit, notional_entry, house, agent, symbol)
    if book == 'alpaca-paper':
        for r in F:
            if r['book'] == book and r['realized'] is not None and lo <= r['at'] < hi:
                closes.append(dict(pnl=r['realized'], notional=r['notional'], house=r['house_exit'], agent=r['agent'], sym=r['symbol'], at=r['at'], asset=r['asset']))
    else:
        for s in ST:
            if s['book'] == book and lo <= s['at'] < hi:
                died = (A.get(s['agent']) or {}).get('died_at')
                closes.append(dict(pnl=s['pnl'], notional=s['cost'], house=bool(died and died < s['at']), agent=s['agent'], sym=s['symbol'], at=s['at'], asset=s['asset']))
    net = sum(x['pnl'] for x in closes)
    house = sum(x['pnl'] for x in closes if x['house'])
    agent_net = net - house
    fees = sum(r['fee'] for r in F if r['book'] == book and lo <= r['at'] < hi)
    fills_n = sum(1 for r in F if r['book'] == book and lo <= r['at'] < hi)
    notional_filled = sum(r['notional'] for r in F if r['book'] == book and lo <= r['at'] < hi)
    haircut = notional_filled * HAIRCUT_BPS / 1e4 if book == 'alpaca-paper' else 0.0
    # slippage vs reference on taker fills
    slip = 0.0; slip_n = 0; slip_bps = []
    for r in F:
        if r['book'] != book or not (lo <= r['at'] < hi):
            continue
        o = O.get(r['order_id'])
        if not o or not o.get('ref') or r['liq'] != 'taker':
            continue
        sign = 1 if r['side'] == 'buy' else -1
        adverse = sign * (r['px'] - o['ref']) * r['q']
        slip += adverse; slip_n += 1; slip_bps.append(sign * (r['px'] - o['ref']) / o['ref'] * 1e4)
    print(f'closed trades/settlements: {len(closes)}  net realized ${net:+.2f}  of which House-held/exited ${house:+.2f} ({sum(1 for x in closes if x["house"])} rows)  agents\' own ${agent_net:+.2f}')
    print(f'fills in window: {fills_n}, notional filled ${notional_filled:,.0f}, venue fees ${fees:.2f}, practice haircut (10 bps/side, allocator only) ${haircut:.2f}')
    print(f'taker slippage vs reference: n={slip_n}, ${slip:+.2f} adverse, median {B0.med(slip_bps):+.1f} bps, mean {sum(slip_bps)/len(slip_bps) if slip_bps else float("nan"):+.1f} bps')
    signal = net + fees
    print(f'signal at the touch (net + fees) ${signal:+.2f}; costs: fees ${fees:.2f} ({fees/abs(net)*100 if net else 0:.0f}% of |net|), haircut ${haircut:.2f} (extra, in W only), slippage ${slip:+.2f}')
    # sizing: largest 10% of positions by entry notional
    cl = sorted(closes, key=lambda x: -x['notional'])
    k = max(1, len(cl) // 10)
    big = cl[:k]
    print(f'sizing: largest 10% positions (n={k}, notional >= ${big[-1]["notional"]:.0f}) P&L ${sum(x["pnl"] for x in big):+.2f} = {sum(x["pnl"] for x in big)/net*100 if net else 0:.0f}% of net; median entry notional ${B0.med([x["notional"] for x in cl]):.2f}, p90 ${B0.pct([x["notional"] for x in cl],0.9):.2f}')
    losers = [x for x in cl if x['pnl'] < 0]; winners = [x for x in cl if x['pnl'] > 0]
    print(f'win rate {len(winners)}/{len(cl)}; gross wins ${sum(x["pnl"] for x in winners):+.2f}, gross losses ${sum(x["pnl"] for x in losers):+.2f}; avg win ${B0.med([x["pnl"] for x in winners]) if winners else 0:+.3f} med, avg loss med ${B0.med([x["pnl"] for x in losers]) if losers else 0:+.3f}')
    byagent = collections.defaultdict(lambda: [0.0, 0])
    for x in closes:
        byagent[x['agent']][0] += x['pnl']; byagent[x['agent']][1] += 1
    print('worst 8 agents:', [(a, round(v[0], 2), v[1], (A.get(a) or {}).get('desk'), 'dead' if (A.get(a) or {}).get('died_at') else 'alive') for a, v in sorted(byagent.items(), key=lambda kv: kv[1][0])[:8]])
    print('best 5 agents:', [(a, round(v[0], 2), v[1], (A.get(a) or {}).get('desk')) for a, v in sorted(byagent.items(), key=lambda kv: -kv[1][0])[:5]])
    byasset = collections.defaultdict(float)
    for x in closes: byasset[x['asset']] += x['pnl']
    print('by asset class:', {k: round(v, 2) for k, v in byasset.items()})
    bysym = collections.defaultdict(float)
    for x in closes: bysym[x['sym'][:14]] += x['pnl']
    print('worst symbols:', [(k, round(v, 2)) for k, v in sorted(bysym.items(), key=lambda kv: kv[1])[:8]])
    # House exits detail
    hx = [x for x in closes if x['house']]
    if hx:
        print('House-exit rows:', [(x['agent'], x['sym'][:12], round(x['pnl'], 2), x['at'][11:16]) for x in hx][:20])
