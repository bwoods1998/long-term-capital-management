"""B-7 (L3 practice -> real): every promotion to real money (rung 2) since the grant: the agent's
W_paper and E at promotion (from the verdict's evidence when the allocator wrote it, else from the
first board / its practice record then) against its W_real after its first 1, 3, 5 real closed
trades (from the 5-minute alloc.board series and the real fills/settles). n is small."""
import importlib.util, collections, json, math
spec = importlib.util.spec_from_file_location('B0', __file__.replace('B-7.py', 'B-0.py')); B0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B0)
c = B0.db(); A = B0.agents(c); F = B0.fills(c); ST = B0.settles(c); BD = B0.boards(c); BL = B0.blocks(c)
promos = []
for seq, a, at, pl in c.execute("select seq,agent,at,payload from ledger where kind='eval.verdict' order by seq"):
    p = json.loads(pl)
    if p.get('decision') in ('promote', 'seat') and int(p.get('to_rung') or 0) == 2:
        ev = (p.get('numbers') or {}).get('evidence') or {}
        promos.append((seq, a, at, ev))
print('promotions to rung 2:', len(promos))
print('agent | desk | promoted | Wp@promo | E@promo | practice log before promo (active blocks) | real closed now | real P&L | W_real after 1 / 3 / 5 / all trades | W_real last board | outcome')
for seq, a, at, ev in promos:
    m = A.get(a) or {}
    book_p = 'kalshi-shadow' if m.get('venue') == 'kalshi' else 'alpaca-paper'
    book_r = 'kalshi' if m.get('venue') == 'kalshi' else 'alpaca'
    g_before = sum(b['g'] for b in BL if b['agent'] == a and b['book'] == book_p and b['active'] and b['seq'] <= seq)
    n_before = sum(1 for b in BL if b['agent'] == a and b['book'] == book_p and b['active'] and b['seq'] <= seq)
    wp = ev.get('W_paper') or round(math.exp(g_before), 4)
    e = ev.get('E') or round(math.sqrt(math.exp(g_before)), 4)
    closes = sorted([(s['seq'], s['at'], s['pnl'], s['cost']) for s in ST if s['agent'] == a and s['book'] == book_r and s['seq'] > seq] +
                    [(r['seq'], r['at'], r['realized'], r['notional'] - r['realized']) for r in F if r['agent'] == a and r['book'] == book_r and r['realized'] is not None and r['seq'] > seq])
    # W_real proxy after n trades: cumulative return on cost compounded (the board's W_real is the wealth index on the stake; both shown)
    stake0 = next((B0.f(json.loads(pl).get('usd')) for (pl,) in c.execute("select payload from ledger where kind='book.stake' and agent=? and json_extract(payload,'$.book')=? and json_extract(payload,'$.usd')>0 order by seq", (a, book_r))), 10.0)
    def w_after(n):
        # wealth on the first real stake after n closed trades (cumulative P&L over the stake lent)
        return 1 + sum(x[2] for x in closes[:n]) / stake0
    wr_board = None
    for _, bat, ag, _, _ in BD:
        if a in ag and len(ag[a]) >= 7: wr_board = ag[a][3]
    pnl = sum(x[2] for x in closes)
    outcome = 'died' if m.get('died_at') else ('demoted' if any(json.loads(pl).get('decision') == 'demote' for (pl,) in c.execute("select payload from ledger where kind='eval.verdict' and agent=? and seq>?", (a, seq))) else 'on real')
    print(f"{a} | {m.get('desk')} | {at[5:16]} | {wp} | {e} | {g_before:+.4f} ({n_before}) | {len(closes)} | ${pnl:+.2f} | {w_after(1):.4f} / {w_after(3):.4f} / {w_after(5):.4f} / {w_after(len(closes)):.4f} (cum P&L / first stake ${stake0:.0f}) | board {wr_board} | {outcome}")
