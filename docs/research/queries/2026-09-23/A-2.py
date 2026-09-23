#!/usr/bin/env python3
"""A-2: compute spend by line. Sources: ledger provider.request (model/profile/request_key prefix, cost_usd),
merton.pass (role, cost_usd), credit.charge (what), ops.budget (sail), campaigns.sqlite commitments."""
import sqlite3, json, collections, time
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-24*3600; H6=SNAP-6*3600
def prefix(k):
    k=str(k or '')
    p=k.split(':')[0]
    return p
print("## provider.request: line (request_key prefix) x model: n, $ (last 24h), $ (last 6h), $ lifetime; hit rate")
agg=collections.defaultdict(lambda:[0,0.0,0.0,0.0,0,0.0,0])
for at,p in c.execute("select at,payload from ledger where kind='provider.request'"):
    d=json.loads(p); t=ep(at)
    key=(prefix(d.get('request_key') or d.get('session_id')), d.get('model'), d.get('profile'))
    cost=float(d.get('cost_usd') or 0); a=agg[key]
    a[3]+=cost; a[6]+=1
    if t>=H24: a[0]+=1; a[1]+=cost
    if t>=H6: a[2]+=cost
    if t>=H24 and d.get('cache'): a[4]+=1; a[5]+=float(d['cache'].get('hit_rate') or 0)
tot24=sum(a[1] for a in agg.values()); tot6=sum(a[2] for a in agg.values()); totl=sum(a[3] for a in agg.values())
for k,a in sorted(agg.items(), key=lambda kv:-kv[1][1]):
    print(f"  {str(k[0]):14s} {str(k[1]):14s} {str(k[2]):16s} n24={a[0]:5d} $24h={a[1]:8.3f} ({a[1]/24:6.3f}/h)  $6h={a[2]:7.3f} ({a[2]/6:6.3f}/h)  $life={a[3]:8.3f} n_life={a[6]}  hit={a[5]/a[4] if a[4] else 0:.2f}")
print(f"  TOTAL provider.request $24h={tot24:.2f} ({tot24/24:.2f}/h) $6h={tot6:.2f} ({tot6/6:.2f}/h) $life={totl:.2f}")
print("\n## provider.request by hour (last 24h): $ per hour, by line")
byh=collections.defaultdict(lambda:collections.defaultdict(float))
for at,p in c.execute("select at,payload from ledger where kind='provider.request' and at>=?",(datetime.fromtimestamp(H24,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),)):
    d=json.loads(p); byh[at[:13]][prefix(d.get('request_key') or d.get('session_id'))]+=float(d.get('cost_usd') or 0)
for h in sorted(byh): print("  ",h, {k:round(v,2) for k,v in sorted(byh[h].items())}, "sum",round(sum(byh[h].values()),2))
print("\n## merton.pass by role: passes, $ lifetime, $ last 24h, passes with files>0, dropped, errors; $ per pass")
mp=collections.defaultdict(lambda:[0,0.0,0.0,0,0,0,0])
for at,p in c.execute("select at,payload from ledger where kind='merton.pass'"):
    d=json.loads(p); r=d.get('role'); a=mp[r]; cost=float(d.get('cost_usd') or 0); a[0]+=1; a[1]+=cost
    if ep(at)>=H24: a[2]+=cost; a[6]+=1
    if (d.get('files') or 0)>0 or d.get('branch'): a[3]+=1
    if d.get('dropped'): a[4]+=1
    if d.get('error'): a[5]+=1
for r,a in sorted(mp.items(), key=lambda kv:-kv[1][1]): print(f"  {r:11s} passes={a[0]:3d} $life={a[1]:7.2f} $24h={a[2]:6.2f} (n24={a[6]}) with_files/branch={a[3]:3d} dropped={a[4]:3d} errors={a[5]:3d} $/pass={a[1]/a[0]:.3f}")
print("\n## credit.charge by what: n, $ lifetime, $ last 24h")
cc=collections.defaultdict(lambda:[0,0.0,0.0])
for at,p in c.execute("select at,payload from ledger where kind='credit.charge'"):
    d=json.loads(p); a=cc[d.get('what')]; a[0]+=1; a[1]+=float(d.get('usd') or 0)
    if ep(at)>=H24: a[2]+=float(d.get('usd') or 0)
for k,a in sorted(cc.items(), key=lambda kv:-kv[1][1]): print(f"  {str(k):18s} n={a[0]:6d} $life={a[1]:8.2f} $24h={a[2]:7.2f}")
print("\n## ops.budget what=sail: latest rows (spent_usd, balance_usd, month_usd, cap_usd) and rate over last 24h")
rows=[(at,json.loads(p)) for at,p in c.execute("select at,payload from ledger where kind='ops.budget' and json_extract(payload,'$.what')='sail' order by seq")]
print("  first",rows[0][0],{k:rows[0][1].get(k) for k in ('spent_usd','balance_usd','month_usd','cap_usd','mode')})
print("  last ",rows[-1][0],{k:rows[-1][1].get(k) for k in ('spent_usd','balance_usd','month_usd','cap_usd','mode')})
past=[r for r in rows if ep(r[0])<=H24]
if past: 
    r0=past[-1]; print("  24h ago",r0[0],{k:r0[1].get(k) for k in ('spent_usd','balance_usd','month_usd')})
    try: print("  sail spent over 24h: $",round(float(rows[-1][1]['spent_usd'])-float(r0[1]['spent_usd']),2), " balance delta $",round(float(rows[-1][1]['balance_usd'])-float(r0[1]['balance_usd']),2))
    except Exception as e: print(e)
print("\n## ops.budget payout rows (epoch payouts): last 5")
for at,p in c.execute("select at,payload from ledger where kind='ops.budget' and json_extract(payload,'$.what')='payout' order by seq desc limit 5"): print("  ",at,p[:300])
print("\n## ops.budget expedition rows: last 3")
for at,p in c.execute("select at,payload from ledger where kind='ops.budget' and json_extract(payload,'$.what')='expedition' order by seq desc limit 3"): print("  ",at,p[:500])
print("\n## campaigns.sqlite commitments: $ settled by kind, last 24h / 6h / lifetime; pending reserved")
k=sqlite3.connect(f'file:{S}/snap/campaigns.sqlite?mode=ro',uri=True)
for kind in ('openai','sail'):
    r=k.execute("select count(*), coalesce(sum(cost),0)/1e6, coalesce(sum(case when cost is null then reserved else 0 end),0)/1e6, sum(case when cost is null then 1 else 0 end) from commitments where kind=? and created>=?",(kind,H24)).fetchone()
    r6=k.execute("select coalesce(sum(cost),0)/1e6 from commitments where kind=? and created>=?",(kind,H6)).fetchone()
    rl=k.execute("select count(*), coalesce(sum(cost),0)/1e6, coalesce(sum(case when cost is null then reserved else 0 end),0)/1e6 from commitments where kind=?",(kind,)).fetchone()
    print(f"  {kind}: 24h n={r[0]} settled=${r[1]:.2f} ({r[1]/24:.2f}/h) pending_reserved=${r[2]:.2f} (n={r[3]});  6h settled=${r6[0]:.2f} ({r6[0]/6:.2f}/h);  lifetime n={rl[0]} settled=${rl[1]:.2f} pending=${rl[2]:.2f}")
print("  commitments id prefixes (24h):", k.execute("select substr(id,1,instr(id,':')-1) p, kind, count(*), round(coalesce(sum(cost),0)/1e6,2) from commitments where created>=? group by 1,2",(H24,)).fetchall())
print("  meter:",k.execute("select * from meter").fetchall(), "meter_balance:",k.execute("select * from meter_balance").fetchall(), "gateway_bonus:",k.execute("select * from gateway_bonus").fetchall())
print("  phase:",[str(r)[:400] for r in k.execute("select * from phase")])
print("  burst:",[str(r)[:600] for r in k.execute("select * from burst")])
print("\n## hypothesis.card cost fields & audit.verdict cost")
n=0; tot=0.0
for at,p in c.execute("select at,payload from ledger where kind='audit.verdict'"):
    d=json.loads(p); n+=1; tot+=float(d.get('cost_usd') or 0)
print(f"  audit.verdict n={n} $={tot:.2f}")
for at,p in c.execute("select at,payload from ledger where kind='hypothesis.card' order by seq desc limit 1"):
    d=json.loads(p); print("  card sample keys:", {kk:(str(v)[:80]) for kk,v in d.items() if kk!='_code'})
