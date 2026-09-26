"""B-3 (L2 real money): every real fill and settlement since the grant (Sept 21) with agent, venue,
market, notional, P&L, fees, maker/taker and size against the stake; per real agent now (last
alloc.board): stake, W_real, E, real trades, U5 stake, days to swing at its real-trade rate; and
which paper agents would be seated under bunt_at 1.005 / bunt_min_trades 3 with their forward records
(from the 5-minute alloc.board series 08:30Z-16:25Z).
"""
import importlib.util, collections, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-3.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); F = B0.fills(c); ST = B0.settles(c); O = B0.orders(c); BD = B0.boards(c)
BUNT = {'kalshi': 10.0, 'alpaca': 25.0}

# stake per agent per real book over time (book.stake rows)
stakes = collections.defaultdict(list)
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='book.stake' order by seq"):
    import json; p = json.loads(pl)
    if p.get('book') in B0.REAL:
        stakes[(a, p['book'])].append((seq, at, B0.f(p.get('usd')), p.get('note')))


def staked_at(a, book, seq):
    return sum(u for s, _, u, _ in stakes.get((a, book), []) if s <= seq)


print('=== every real venue fill since 2026-09-21 (at | agent | book | side | symbol | q | px | notional | fee | liq | realized | stake then | size % of stake | reason)')
tot = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])
for r in F:
    if r['book'] not in B0.REAL or r['at'] < '2026-09-21':
        continue
    st = staked_at(r['agent'], r['book'], r['seq'])
    share = r['notional'] / st * 100 if st > 0 else float('nan')
    o = O.get(r['order_id']) or {}
    print(f"{r['at'][5:16]} | {r['agent']} | {r['book']} | {r['side']} | {r['symbol']} | {r['q']:g} | {r['px']:.4f} | ${r['notional']:.2f} | fee {r['fee']:.3f} | {r['liq']} | {o.get('type')} | realized {r['realized']} | stake ${st:.2f} | {share:.0f}% | {r['reason'][:70]}")
    t = tot[(r['book'], r['liq'])]; t[0] += 1; t[1] += r['notional']; t[2] += r['fee']
print('fills by (book, liquidity): n, notional, fees:', {k: (v[0], round(v[1], 2), round(v[2], 3)) for k, v in tot.items()})
print('\n=== every real settlement (at | agent | market | right | result | q | cost | payout | pnl | held h)')
sp = collections.defaultdict(lambda: [0, 0.0, 0])
for s in ST:
    if s['book'] not in B0.REAL:
        continue
    held = (B0.ts(s['at']) - B0.ts(s['opened_at'])) / 3600 if s['opened_at'] else float('nan')
    print(f"{s['at'][5:16]} | {s['agent']} | {s['symbol']} | {s['right']} | {s['result']} | {s['q']:g} | ${s['cost']:.2f} | ${s['payout']:.2f} | {s['pnl']:+.2f} | {held:.1f}h")
    x = sp[s['agent']]; x[0] += 1; x[1] += s['pnl']; x[2] += s['pnl'] > 0
print('settlements per agent (n, pnl, wins):', {k: (v[0], round(v[1], 2), v[2]) for k, v in sp.items()})
real_pnl = sum(s['pnl'] for s in ST if s['book'] in B0.REAL) + sum(r['realized'] or 0 for r in F if r['book'] in B0.REAL and r['realized'] is not None)
print(f'real realized P&L since grant: ${real_pnl:+.2f}; venue fees on real fills ${sum(r["fee"] for r in F if r["book"] in B0.REAL):.2f}')

# promotions to real money (rung 2) and their evidence
print('\n=== promotions to rung 2 (bunt) with evidence at promotion')
promos = {}
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='eval.verdict' order by seq"):
    p = json.loads(pl)
    if p.get('decision') in ('promote', 'seat') and int(p.get('to_rung') or 0) == 2:
        ev = (p.get('numbers') or {}).get('evidence') or p.get('evidence') or {}
        promos.setdefault(a, []).append((seq, at, ev, (p.get('reason') or '')[:90]))
        print(f"{at[5:16]} {a} {p.get('decision')} E={ev.get('E')} Wp={ev.get('W_paper')} Wr={ev.get('W_real')} trades={ev.get('trades')} settled={ev.get('settled')} | {(p.get('reason') or '')[:100]}")
print('\n=== demotions / sizes')
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='eval.verdict' and (json_extract(payload,'$.decision') in ('demote','size','die')) order by seq"):
    p = json.loads(pl)
    print(f"{at[5:16]} {a} {p.get('decision')} rung={p.get('rung')} to={p.get('to_rung')} stake={p.get('stake_usd')} moved={p.get('moved_usd')} | {(p.get('reason') or '')[:110]}")

# per real agent now
seq_last, at_last, last, throttle, env = BD[-1]
print(f'\n=== last board {at_last} throttle={throttle} envelope={env}')
print('agent | venue | band | stake | W_paper | W_real | E | trades | real_trades | U5 stake | real closed trades total | first real at | real trades/day | days to 8 trades | real P&L')
for a, row in sorted(last.items(), key=lambda kv: kv[1][0]):
    if row[0] in ('bunt', 'swing', 'star'):
        band, stake, wp, wr, e, tr, rtr = row[:7]
        venue = (A.get(a) or {}).get('venue') or ('kalshi' if a.split('-')[0] in ('mullins', 'hawkins', 'huang', 'hilibrand', 'meriwether', 'rosenfeld') else 'alpaca')
        u5 = BUNT[venue] * min(max(wr, 1.0), 1.5)
        rf = [r for r in F if r['agent'] == a and r['book'] in B0.REAL]
        rs = [s for s in ST if s['agent'] == a and s['book'] in B0.REAL]
        closed = len(rs) + sum(1 for r in rf if r['realized'] is not None and r['flat'] is not False)
        first = min([r['at'] for r in rf] + [s['at'] for s in rs], default=None)
        days = (B0.ts(B0.SNAP_AT + ':00Z') - B0.ts(first)) / 86400 if first else float('nan')
        rate = closed / days if first and days > 0 else 0
        need = max(0, 8 - closed)
        pnl = sum(s['pnl'] for s in rs) + sum(r['realized'] or 0 for r in rf if r['realized'] is not None)
        print(f"{a} | {venue} | {band} | {stake} | {wp:.4f} | {wr:.4f} | {e:.4f} | {tr} | {rtr} | ${u5:.2f} | {closed} | {first} | {rate:.2f}/d | {need/rate if rate else float('inf'):.1f} d | ${pnl:+.2f}")

# lower-line what-if from the board series
print('\n=== what-if bunt_at 1.005 / bunt_min_trades 3 (Kalshi: settled>=2 proxy = trades>=2): paper agents that would have qualified but did not under 1.01/5(3)')
settled_by = collections.defaultdict(list)
for s in ST:
    if s['book'] == 'kalshi-shadow':
        settled_by[s['agent']].append(s['seq'])
firstq = {}
for seq, at, ag, _, _ in BD:
    for a, row in ag.items():
        if row[0] != 'paper' or len(row) < 7:
            continue
        band, stake, wp, wr, e, tr, rtr = row[:7]
        venue = (A.get(a) or {}).get('venue')
        settled = sum(1 for s in settled_by.get(a, []) if s <= seq)
        enough_low = tr >= 3 or (venue == 'kalshi' and settled >= 2)
        enough_now = tr >= 5 or (venue == 'kalshi' and settled >= 3)
        low = enough_low and e >= 1.005
        now = enough_now and e >= 1.01
        if low and not now and a not in firstq:
            firstq[a] = (seq, at, wp, e, tr, settled)
ups = downs = 0; deltas = []
for a, (seq, at, wp, e, tr, settled) in sorted(firstq.items(), key=lambda kv: kv[1][0]):
    row = last.get(a)
    m = A.get(a) or {}
    if row and len(row) >= 7:
        d = math.log(row[2] / wp) if wp > 0 and row[2] > 0 else float('nan')
        deltas.append(d); ups += d > 0; downs += d < 0
        print(f"{a} ({m.get('venue')},{m.get('desk')}) qualified-low at {at[5:16]}: Wp {wp:.4f} E {e:.4f} trades {tr} settled {settled} -> now Wp {row[2]:.4f} E {row[4]:.4f} trades {row[5]} band {row[0]}; forward log {d:+.4f}")
    else:
        print(f"{a} ({m.get('venue')},{m.get('desk')}) qualified-low at {at[5:16]}: Wp {wp:.4f} E {e:.4f} trades {tr} -> gone from board (died {m.get('died_at')} {m.get('cause')})")
print(f'lower-line cohort: {len(firstq)} agents; forward: {ups} up, {downs} down, mean forward log {sum(deltas)/len(deltas) if deltas else float("nan"):+.4f}, median {B0.med(deltas):+.4f}')
# and who is qualifying right now under the lower line
print('\n=== on the last board, paper agents meeting the lower line now:')
for a, row in last.items():
    if row[0] == 'paper' and len(row) >= 7:
        venue = (A.get(a) or {}).get('venue'); settled = len(settled_by.get(a, []))
        if row[4] >= 1.005 and (row[5] >= 3 or (venue == 'kalshi' and settled >= 2)):
            print(a, venue, (A.get(a) or {}).get('desk'), 'Wp', row[2], 'E', row[4], 'trades', row[5], 'settled', settled, 'meets 1.01/5:', row[4] >= 1.01 and (row[5] >= 5 or (venue == 'kalshi' and settled >= 3)))
