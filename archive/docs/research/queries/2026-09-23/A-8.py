#!/usr/bin/env python3
"""A-8: real money against compute. Real fills (books alpaca, kalshi): realized P&L, fees, by agent and by House/agent; real agent-hours
(time spent at rung>=2); stakes; compute burn per hour; the stake and edge a break-even swarm needs."""
import sqlite3, json, collections
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400
print("## real fills by book x source x House?: n, realized $, fees $, notional $ (lifetime | 24h)")
agg=collections.defaultdict(lambda:[0,0.0,0.0,0.0,0,0.0])
per_agent=collections.defaultdict(lambda:[0,0.0,0.0,None,None])
for a,at,p in c.execute("select agent,at,payload from ledger where kind='book.fill' and json_extract(payload,'$.book') in ('alpaca','kalshi')"):
    d=json.loads(p); house = d.get('source')=='dust' or str(d.get('reason') or '').startswith('the House is closing')
    key=(d['book'],d.get('source'),'house' if house else 'agent'); r=float(d.get('realized') or 0); fee=float(d.get('fee_usd') or 0)
    q=float(d.get('quantity') or 0)*float(d.get('price') or 0)*float((d.get('instrument') or {}).get('multiplier') or 1)
    x=agg[key]; x[0]+=1; x[1]+=r; x[2]+=fee; x[3]+=q
    if ep(at)>=H24: x[4]+=1; x[5]+=r
    pa=per_agent[a]; pa[0]+=1; pa[1]+=r; pa[2]+=fee; pa[3]=pa[3] or ep(at); pa[4]=ep(at)
for k,x in sorted(agg.items()): print(f"  {str(k):40s} n={x[0]:4d} realized={x[1]:+8.2f} fees={x[2]:6.2f} notional={x[3]:8.2f} | 24h n={x[4]} realized={x[5]:+.2f}")
tot=sum(x[1] for x in agg.values()); tot24=sum(x[5] for x in agg.values())
print(f"  TOTAL real realized lifetime {tot:+.2f} (24h {tot24:+.2f}); fees {sum(x[2] for x in agg.values()):.2f}")
print("## per real agent: fills, realized, fees, first->last fill h, class, desk, rung, hours at rung>=2")
r2h=0.0; n_real=0
for a,pa in sorted(per_agent.items(), key=lambda kv:-kv[1][1]):
    g=agents.get(a,{}); h2=None
    if g.get('r2_at'): h2=((g['died'] or SNAP)-g['r2_at'])/3600; r2h+=h2; n_real+=1
    print(f"  {a:22s} fills={pa[0]:3d} realized={pa[1]:+7.2f} fees={pa[2]:5.2f} span_h={(pa[4]-pa[3])/3600:5.1f} {g.get('cls','?'):14s} {str(g.get('niche')):22s} r{g.get('rung_max')} h_at_r2={h2 if h2 is None else round(h2,1)}")
print(f"  agents ever at rung>=2: {sum(1 for g in agents.values() if g.get('r2_at'))}; real agent-hours (rung>=2, lifetime) = {sum(((g['died'] or SNAP)-g['r2_at'])/3600 for g in agents.values() if g.get('r2_at')):.1f} h")
allr2=sum(((g['died'] or SNAP)-g['r2_at'])/3600 for g in agents.values() if g.get('r2_at'))
print(f"  real realized per real agent-hour: ${tot/allr2:+.4f}/h" if allr2 else "")
print("## book.stake real_money=true: rows, sum, latest per agent")
st=collections.defaultdict(list)
for a,at,p in c.execute("select agent,at,payload from ledger where kind='book.stake' and json_extract(payload,'$.real_money')=1"):
    d=json.loads(p); st[a].append((at,float(d.get('usd') or 0),d.get('note')))
for a,v in st.items(): print(f"  {a:22s} n={len(v)} latest={v[-1]}")
print("## floor.mark latest: real account equity and venues")
for at,p in c.execute("select at,payload from ledger where kind='floor.mark' order by seq desc limit 1"):
    d=json.loads(p); print("  ",at, {k:(str(v)[:300]) for k,v in d.items()})
for at,p in c.execute("select at,payload from ledger where kind='floor.mark' and at<=? order by seq desc limit 1",(datetime.fromtimestamp(H24,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),)):
    d=json.loads(p); print("  24h ago",at, {k:(str(v)[:200]) for k,v in d.items() if k in ('real_account_equity','account_equity')})
print("## practice realized (agents only, excl. House dust/closing) by book, 24h and lifetime")
for b in ('alpaca-paper','kalshi-shadow'):
    r=c.execute("select count(*), sum(cast(json_extract(payload,'$.realized') as real)), sum(cast(json_extract(payload,'$.fee_usd') as real)) from ledger where kind='book.fill' and json_extract(payload,'$.book')=? and json_extract(payload,'$.source')!='dust' and coalesce(json_extract(payload,'$.reason'),'') not like 'the House is closing%'",(b,)).fetchone()
    r24=c.execute("select count(*), sum(cast(json_extract(payload,'$.realized') as real)) from ledger where kind='book.fill' and json_extract(payload,'$.book')=? and json_extract(payload,'$.source')!='dust' and coalesce(json_extract(payload,'$.reason'),'') not like 'the House is closing%' and at>=?",(b,datetime.fromtimestamp(H24,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))).fetchone()
    h=c.execute("select count(*), sum(cast(json_extract(payload,'$.realized') as real)) from ledger where kind='book.fill' and json_extract(payload,'$.book')=? and (json_extract(payload,'$.source')='dust' or coalesce(json_extract(payload,'$.reason'),'') like 'the House is closing%')",(b,)).fetchone()
    print(f"  {b}: agents lifetime n={r[0]} realized={r[1] or 0:+.2f} fees={r[2] or 0:.2f} | 24h n={r24[0]} realized={r24[1] or 0:+.2f} | House (dust/closing) n={h[0]} realized={h[1] or 0:+.2f}")
