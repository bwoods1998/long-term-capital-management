#!/usr/bin/env python3
"""A-8b: Kalshi settlements (book.settle) by book and agent; real-equity series from floor.mark."""
import sqlite3, json, collections
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400
print("## book.settle sample"); 
for a,at,p in c.execute("select agent,at,payload from ledger where kind='book.settle' and json_extract(payload,'$.book')='kalshi' order by seq desc limit 2"): print("  ",a,at,p[:600])
keys=collections.Counter()
agg=collections.defaultdict(lambda:[0,0.0,0.0,0,0.0]); pa=collections.defaultdict(lambda:[0,0.0])
for a,at,p in c.execute("select agent,at,payload from ledger where kind='book.settle'"):
    d=json.loads(p); keys.update(d.keys()); b=d.get('book'); r=float(d.get('realized') or d.get('pnl') or d.get('cash_delta') or 0)
    x=agg[b]; x[0]+=1; x[1]+=r; x[2]+=float(d.get('fee_usd') or 0)
    if ep(at)>=H24: x[3]+=1; x[4]+=r
    if b=='kalshi': pa[a][0]+=1; pa[a][1]+=r
print("  keys",dict(keys))
for b,x in agg.items(): print(f"  {b:14s} settles={x[0]:4d} realized={x[1]:+8.2f} fees={x[2]:.2f} | 24h n={x[3]} realized={x[4]:+.2f}")
print("## real kalshi settles per agent: n, realized, class, desk")
for a,x in sorted(pa.items(), key=lambda kv:-kv[1][1]): print(f"  {a:22s} n={x[0]:3d} realized={x[1]:+7.2f} {agents.get(a,{}).get('cls','?'):14s} {str(agents.get(a,{}).get('niche'))}")
print("## floor.mark real_account_equity series (first, then every ~6h, last)")
rows=[(at,json.loads(p)) for at,p in c.execute("select at,payload from ledger where kind='floor.mark' order by seq")]
last=None
for at,d in rows:
    t=ep(at)
    if last is None or t-last>=6*3600 or at==rows[-1][0]:
        print(f"  {at[:16]} real_equity={d.get('real_account_equity')} venues={[(v.get('venue'),v.get('equity')) for v in (d.get('venues') or [])]}")
        last=t
print("## performance fees granted (credit.grant reason like 'performance fee'):", c.execute("select count(*), sum(cast(json_extract(payload,'$.usd') as real)) from ledger where kind='credit.grant' and json_extract(payload,'$.reason') like 'performance fee%'").fetchone())
