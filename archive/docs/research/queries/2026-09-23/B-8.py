"""B-8 (L3 fills): real vs practice fills per book / asset class: slippage against the order's
reference price (book.order reference_price: the touch for market orders, the limit for limit
orders), fees per notional, maker share, reject and refusal rates (book.order status, book.refused
reasons), maker fill rates (filled / resting orders) shadow vs real, and how many real fills exist per
asset class (the haircut table needs 30+ per class)."""
import importlib.util, collections, json
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-8.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); F = B0.fills(c); O = B0.orders(c)
since = '2026-09-21'
print('=== venue fills since', since, ': book | asset | liquidity | n | notional | fees | fee bps of notional | median adverse bps vs reference | mean | n with ref')
agg = collections.defaultdict(lambda: dict(n=0, notional=0.0, fee=0.0, slip=[]))
for r in F:
    if r['at'] < since or r['source'] != 'venue':
        continue
    o = O.get(r['order_id']) or {}
    k = (r['book'], r['asset'], r['liq'])
    g = agg[k]; g['n'] += 1; g['notional'] += r['notional']; g['fee'] += r['fee']
    if o.get('ref'):
        sign = 1 if r['side'] == 'buy' else -1
        g['slip'].append(sign * (r['px'] - o['ref']) / o['ref'] * 1e4)
for k, g in sorted(agg.items()):
    s = g['slip']
    print(f"{k[0]} | {k[1]} | {k[2]} | {g['n']} | ${g['notional']:.0f} | ${g['fee']:.2f} | {g['fee']/g['notional']*1e4 if g['notional'] else 0:.1f} bps | {B0.med(s):+.1f} | {sum(s)/len(s) if s else float('nan'):+.1f} | {len(s)}")
print('\n=== real fills per asset class (haircut table needs 30+):', collections.Counter((r['book'], r['asset']) for r in F if r['book'] in B0.REAL and r['source'] == 'venue'))
print('\n=== market-order slippage vs the touch, by book x asset x side (venue fills, taker, order_type market):')
agg2 = collections.defaultdict(list)
for r in F:
    o = O.get(r['order_id']) or {}
    if r['source'] != 'venue' or o.get('type') != 'market' or not o.get('ref'):
        continue
    sign = 1 if r['side'] == 'buy' else -1
    agg2[(r['book'], r['asset'], r['side'])].append(sign * (r['px'] - o['ref']) / o['ref'] * 1e4)
for k, v in sorted(agg2.items()):
    print(f'  {k}: n {len(v)}, median {B0.med(v):+.1f} bps, mean {sum(v)/len(v):+.1f} bps, p90 {B0.pct(v,0.9):+.1f}')
print('\n=== limit orders: fill price vs limit (should be 0 or better):')
agg3 = collections.defaultdict(list)
for r in F:
    o = O.get(r['order_id']) or {}
    if r['source'] != 'venue' or o.get('type') != 'limit' or not o.get('limit'):
        continue
    sign = 1 if r['side'] == 'buy' else -1
    agg3[(r['book'], r['asset'])].append(sign * (r['px'] - o['limit']) / o['limit'] * 1e4)
for k, v in sorted(agg3.items()):
    print(f'  {k}: n {len(v)}, median {B0.med(v):+.1f} bps, mean {sum(v)/len(v):+.1f}, min {min(v):+.1f}, max {max(v):+.1f}')

print('\n=== order outcomes per book (unique order ids, last status), since', since)
st = collections.defaultdict(collections.Counter)
for oid, o in O.items():
    if o['first_at'] < since:
        continue
    st[(o['book'], o['type'], o['liq'])][o['last']] += 1
for k, v in sorted(st.items()):
    tot = sum(v.values())
    print(f"  {k}: total {tot} | " + ', '.join(f'{s} {n} ({n/tot*100:.0f}%)' for s, n in v.most_common()))
print('\n=== maker (post-only limit) orders: filled share, shadow vs real:')
for book in ('kalshi-shadow', 'kalshi'):
    v = [o for o in O.values() if o['book'] == book and o['liq'] == 'maker' and o['first_at'] >= since]
    filled = sum(1 for o in v if o['last'] in ('filled', 'partially_filled'))
    canc = sum(1 for o in v if o['last'] in ('cancelled', 'expired'))
    rej = sum(1 for o in v if o['last'] == 'rejected')
    resting = sum(1 for o in v if o['last'] in ('accepted', 'new'))
    print(f'  {book}: {len(v)} maker orders; filled {filled} ({filled/len(v)*100 if v else 0:.0f}%), cancelled/expired {canc} ({canc/len(v)*100 if v else 0:.0f}%), rejected {rej}, still resting {resting}')
print('\n=== rejected orders: reasons (last reason) per book:')
rr = collections.defaultdict(collections.Counter)
for o in O.values():
    if o['last'] == 'rejected' and o['first_at'] >= since:
        rr[o['book']][(o['last_reason'] or '')[:90]] += 1
for b, v in rr.items():
    print(f'  {b}: {sum(v.values())} rejected')
    for k, n in v.most_common(6): print(f'     {n} x {k}')
print('\n=== book.refused per book (reasons), since', since)
ref = collections.defaultdict(collections.Counter); refn = collections.Counter()
for at, a, pl in c.execute("select at,agent,payload from ledger where kind='book.refused' and at>=? order by seq", (since,)):
    p = json.loads(pl); refn[p.get('book')] += 1
    for x in p.get('reasons') or []:
        ref[p.get('book')][x[:100]] += 1
intents = collections.Counter(json.loads(pl).get('book') for (pl,) in c.execute("select payload from ledger where kind='agent.intent' and at>=?", (since,)))
for b in refn:
    print(f'  {b}: {refn[b]} refusals of {intents.get(b)} intents ({refn[b]/max(intents.get(b,1),1)*100:.0f}%)')
    for k, n in ref[b].most_common(8): print(f'     {n} x {k}')
