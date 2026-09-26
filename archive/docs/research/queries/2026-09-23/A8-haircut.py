"""A8 (the learn-and-unblock run, Sept 23, 2026): the Alpaca practice haircut per asset class.

The table (`docs/goals/LTCM_LEARN_AND_UNBLOCK.md`): `allocator.evidence.alpaca_paper_haircut_bps` "per
asset class, each from at least 30 measured fills of that class, never below 2 bps a side". A measured
fill is a PRACTICE fill measured against its order's reference price at intent time (B-8's method:
`book.order` `reference_price`, the touch for a market order, the limit for a limit order), because
real Alpaca fills are too few to be the benchmark (2 crypto, 0 equity, 0 option on the 16:28Z
snapshot). Slippage is signed so that + is adverse (a buy above, a sell below the reference) and -
is the practice fill's OPTIMISM (better than the reference).

The rule this query applies: the haircut is charged on every fill's notional, each side, so it must
collect what practice fills overstate, per dollar filled. Two readings of that, and the class is
charged the LARGER, rounded UP to a whole bp, never below 2 bps a side:
- in aggregate: the NOTIONAL-WEIGHTED mean optimism over all the class's measured fills, buys and
  sells together, tail fills included (options' limits filled through);
- per round trip: a position is bought and sold, and both fills overstate it, so the two charges
  must cover the buys' weighted mean optimism plus the sells': half that sum a side. This is what
  covers a class whose optimism sits on one side (crypto sells) for an agent of equal buy and sell
  notional, whatever the population's mix.
The per-side and median figures are printed alongside, and the worse-side reading (every side
charged the worst side's optimism) is shown for the record: it would charge each round trip about
twice what was measured.

Reads the fresh snapshot at $S/snap2/ledger.sqlite when present, else B-0's $S/snap (16:28Z).
"""
import collections
import importlib.util
import math

spec = importlib.util.spec_from_file_location('B0', __file__.replace('A8-haircut.py', 'B-0.py'))
B0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B0)
fresh = B0.S / 'snap2' / 'ledger.sqlite'
if fresh.exists():
    B0.SNAP = fresh
c = B0.db()
head_seq, head_at = c.execute('select seq, at from ledger order by seq desc limit 1').fetchone()
print(f'snapshot {B0.SNAP} (head seq {head_seq} at {head_at})')
F = B0.fills(c, sources=('venue',))
O = B0.orders(c)
SINCE = '2026-09-21'
CLASSES = ('crypto', 'equity', 'option')
FLOOR_BPS, MIN_FILLS = 2, 30


def slip(r, ref):
    return (1 if r['side'] == 'buy' else -1) * (r['px'] - ref) / ref * 1e4


rows = collections.defaultdict(list)  # (asset, side, order type) -> [bps]
weighted = collections.defaultdict(lambda: [0.0, 0.0])  # (asset, side) -> [sum notional x bps, sum notional]
unref = collections.Counter()
for r in F:
    if r['book'] != 'alpaca-paper' or r['at'] < SINCE:
        continue
    o = O.get(r['order_id']) or {}
    ref = o.get('ref')
    if not ref or ref <= 0:
        unref[r['asset']] += 1
        continue
    rows[(r['asset'], r['side'], o.get('type'))].append(slip(r, ref))
    w = weighted[(r['asset'], r['side'])]
    w[0] += r['notional'] * slip(r, ref)
    w[1] += r['notional']

print(f'\n=== alpaca-paper venue fills since {SINCE} vs the order reference at intent time (+ adverse, - optimistic)')
print('asset | side | order type | n | median bps | mean bps | p10 | p90')
for k in sorted(rows, key=lambda k: tuple(str(x) for x in k)):
    v = rows[k]
    print(f'{k[0]} | {k[1]} | {k[2]} | {len(v)} | {B0.med(v):+.2f} | {sum(v) / len(v):+.2f} | {B0.pct(v, 0.1):+.2f} | {B0.pct(v, 0.9):+.2f}')
print('fills with no reference price (not measured):', dict(unref))

print('\n=== per class: the haircut covers the larger of the aggregate and the round-trip optimism (see the docstring)')
table = {}
for asset in CLASSES:
    both = [x for (a, _, _), v in rows.items() if a == asset for x in v]
    sides = {side: [x for (a, s, _), v in rows.items() if a == asset and s == side for x in v] for side in ('buy', 'sell')}
    worst = 0.0
    parts = []
    for side, v in sides.items():
        if not v:
            continue
        m, md = sum(v) / len(v), B0.med(v)
        worst = max(worst, -m, -md)
        parts.append(f'{side} n {len(v)} median {md:+.2f} mean {m:+.2f}')
    num = sum(weighted[(asset, side)][0] for side in ('buy', 'sell'))
    den = sum(weighted[(asset, side)][1] for side in ('buy', 'sell'))
    wmean = num / den if den else 0.0
    side_w = {side: (weighted[(asset, side)][0] / weighted[(asset, side)][1] if weighted[(asset, side)][1] else 0.0) for side in ('buy', 'sell')}
    round_trip = -(side_w['buy'] + side_w['sell']) / 2
    bps = max(FLOOR_BPS, math.ceil(round(max(0.0, -wmean, round_trip), 6)))
    enough = len(both) >= MIN_FILLS
    table[asset] = bps if enough else None
    mean_both = sum(both) / len(both) if both else float('nan')
    print(f'{asset}: n {len(both)} (>= {MIN_FILLS}: {enough}), ${den:,.0f} filled; median {B0.med(both):+.2f}, mean {mean_both:+.2f}, '
          f'NOTIONAL-WEIGHTED mean {wmean:+.2f} (buys {side_w["buy"]:+.2f}, sells {side_w["sell"]:+.2f}; round trip {round_trip:.2f} a side); ' + '; '.join(parts)
          + f' -> haircut {bps} bps a side' + ('' if enough else ' (TOO FEW FILLS: not set)')
          + f' [worse-side reading, for the record: {max(FLOOR_BPS, math.ceil(round(worst, 6)))}]')

real = collections.Counter(r['asset'] for r in F if r['book'] == 'alpaca')
real_slip = collections.defaultdict(list)
for r in F:
    o = O.get(r['order_id']) or {}
    if r['book'] == 'alpaca' and o.get('ref'):
        real_slip[r['asset']].append(slip(r, o['ref']))
print('\n=== real Alpaca fills per class (all time):', dict(real), {k: [round(x, 2) for x in v] for k, v in real_slip.items()})
print('\n=== the table:', table)
