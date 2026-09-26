#!/usr/bin/env python3
"""A-2b: reconcile the OpenAI month: campaigns commitments joined to responses.profile, last 24h / 6h / lifetime, per hour."""
import sqlite3, collections, time
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
k=sqlite3.connect(f'file:{S}/snap/campaigns.sqlite?mode=ro',uri=True)
SNAP=datetime.fromisoformat('2026-09-23T16:28:00+00:00').timestamp(); H24=SNAP-86400; H6=SNAP-6*3600
print("## commitments x responses.profile: n, $settled 24h, $/h, $6h, $/h, $lifetime, pending reserved $ (no cost yet)")
q="""select coalesce(r.profile,'(no response row)') p, c.kind, count(*), 
  sum(case when c.created>=? then coalesce(c.cost,0) else 0 end)/1e6,
  sum(case when c.created>=? then coalesce(c.cost,0) else 0 end)/1e6,
  sum(coalesce(c.cost,0))/1e6,
  sum(case when c.cost is null then c.reserved else 0 end)/1e6,
  sum(case when c.created>=? then 1 else 0 end)
  from commitments c left join responses r on r.commitment=c.id group by 1,2 order by 4 desc"""
for p,kind,n,d24,d6,dl,pend,n24 in k.execute(q,(H24,H6,H24)):
    print(f"  {p:22s} {kind:7s} n={n:6d} n24={n24:6d} $24h={d24:8.2f} ({d24/24:5.2f}/h) $6h={d6:7.2f} ({d6/6:5.2f}/h) $life={dl:8.2f} pending=${pend:6.2f}")
print("## responses profiles:", k.execute("select profile,count(*) from responses group by 1").fetchall())
print("## commitments without a response row, by kind and cost: n, $24h, $life")
print("  ", k.execute("select c.kind, count(*), sum(case when c.created>=? then coalesce(c.cost,0) else 0 end)/1e6, sum(coalesce(c.cost,0))/1e6, sum(case when c.cost is null then c.reserved else 0 end)/1e6 from commitments c left join responses r on r.commitment=c.id where r.id is null group by 1",(H24,)).fetchall())
print("## openai settled per hour (last 24h) vs ledger provider.request+merton.pass per hour")
byh=collections.defaultdict(float)
for cr,cost in k.execute("select created,cost from commitments where kind='openai' and created>=? and cost is not null",(H24,)):
    byh[datetime.fromtimestamp(cr,timezone.utc).strftime('%dT%H')]+=cost/1e6
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
import json
led=collections.defaultdict(lambda:collections.defaultdict(float))
for at,kind,p in c.execute("select at,kind,payload from ledger where kind in ('provider.request','merton.pass','audit.verdict') and at>=?",(datetime.fromtimestamp(H24,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),)):
    d=json.loads(p); led[at[8:13].replace('-','')+'' if False else at[8:10]+'T'+at[11:13]][kind]+=float(d.get('cost_usd') or 0)
for h in sorted(set(byh)|set(led)):
    l=led.get(h,{}); print(f"  {h}: commitments ${byh.get(h,0):6.2f} | provider.request ${l.get('provider.request',0):5.2f} merton.pass ${l.get('merton.pass',0):5.2f} audit ${l.get('audit.verdict',0):4.2f}  sum ${sum(l.values()):6.2f}")
print("## cost distribution of openai commitments 24h with a response profile: per-profile mean $ per call")
for p,n,mean,mx in k.execute("select r.profile,count(*),avg(c.cost)/1e6,max(c.cost)/1e6 from commitments c join responses r on r.commitment=c.id where c.kind='openai' and c.created>=? and c.cost is not null group by 1",(H24,)): print(f"  {p:22s} n={n:6d} mean=${mean:.4f} max=${mx:.3f}")
print("## sample commitment ids by profile (24h)")
for p,i,cost,res in k.execute("select r.profile,c.id,c.cost,c.reserved from commitments c join responses r on r.commitment=c.id where c.created>=? group by r.profile",(H24,)): print("  ",p,i[:50],cost,res)
