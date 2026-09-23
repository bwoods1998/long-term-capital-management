#!/usr/bin/env python3
"""A-3: the Alpha Lab. lab.sqlite candidates/batches/calls/graduations + ledger lab.graduate, holdout.access, lab.stats."""
import sqlite3, json, collections, time
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
L=sqlite3.connect(f'file:{S}/snap/lab.sqlite?mode=ro',uri=True)
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-24*3600
fmt=lambda t: datetime.fromtimestamp(t,timezone.utc).strftime('%m-%dT%H:%M')
print("## lab window:", fmt(L.execute("select min(created) from candidates").fetchone()[0]), "->", fmt(L.execute("select max(created) from candidates").fetchone()[0]), "hours", round((L.execute("select max(created)-min(created) from candidates").fetchone()[0])/3600,1))
print("## candidates by origin: n, evaluated, eligible, gate-passed, archived(elite), median fitness of gate-passers")
for o,n,ev,el,g in L.execute("select origin,count(*),sum(evaluated is not null),sum(coalesce(eligible,0)),sum(coalesce(gate,0)) from candidates group by 1 order by 2 desc"):
    fits=[r[0] for r in L.execute("select fitness from candidates where origin=? and gate=1 and fitness is not null order by fitness",(o,))]
    print(f"  {o:8s} n={n:5d} evaluated={ev:5d} eligible={el:5d} gate={g:4d}  gate/eval={g/max(ev,1):.2f}  median_fit_gate={fits[len(fits)//2] if fits else None}")
print("## candidates by status:", L.execute("select status,count(*) from candidates group by 1").fetchall())
print("## candidates by niche: n, gate", L.execute("select niche,count(*),sum(coalesce(gate,0)) from candidates group by 1 order by 2 desc").fetchall())
print("## archive (elites):", L.execute("select count(*), count(distinct niche) from archive").fetchone(), "by niche", L.execute("select niche,count(*) from archive group by 1").fetchall())
print("## calls by kind/model: n, written, refused, $cost, $royalty; per hour over last 24h")
for r in L.execute("select kind,model,count(*),sum(written),sum(refused),round(sum(cast(cost_usd as real)),3),round(sum(cast(royalty_usd as real)),3),sum(error is not null) from calls group by 1,2"): print("  ",r)
r=L.execute("select count(*),round(sum(cast(cost_usd as real)),3),sum(written) from calls where at>=?",(H24,)).fetchone(); print("  last 24h calls:",r, " $/h", round(r[1]/24,3), " $/written", round(r[1]/max(r[2],1),4))
print("  calls first/last:", fmt(L.execute("select min(at) from calls").fetchone()[0]), fmt(L.execute("select max(at) from calls").fetchone()[0]))
print("## batches: n, candidates, ok, eligible, gate, archived, seconds, sail_usd")
r=L.execute("select count(*),sum(candidates),sum(ok),sum(eligible),sum(gate),sum(archived),round(sum(seconds)),round(sum(cast(sail_usd as real)),3) from batches").fetchone(); print("  ",r, " sec/candidate", round(r[6]/max(r[1],1),2), " $sail/candidate", round(r[7]/max(r[1],1),5))
r=L.execute("select count(*),sum(candidates),sum(gate),round(sum(seconds)),round(sum(cast(sail_usd as real)),3) from batches where at>=?",(H24,)).fetchone(); print("  last 24h:",r)
print("## graduations by state:", L.execute("select state,count(*) from graduations group by 1").fetchall())
print("## graduations detail (state, niche, origin via candidates, at, detail)")
for cand,niche,lineage,line,fam,state,agent,at,detail in L.execute("select candidate,niche,lineage,line,family,state,agent,at,detail from graduations order by at"):
    o=L.execute("select origin,fitness,trades from candidates where id=?",(cand,)).fetchone()
    print(f"  {fmt(at)} {state:16s} {niche:20s} {str(o):40s} agent={agent} | {detail[:150]}")
print("## ledger lab.graduate events by state and hour")
ct=collections.Counter()
for at,p in c.execute("select at,payload from ledger where kind='lab.graduate'"):
    d=json.loads(p); ct[(at[:13],d.get('state'))]+=1
for k,v in sorted(ct.items()): print("  ",k,v)
print("## holdout.access: n by agent class/outcome (payload keys)")
keys=collections.Counter(); who=collections.Counter()
for a,at,p in c.execute("select agent,at,payload from ledger where kind='holdout.access'"):
    d=json.loads(p); keys.update(k for k in d if k!='_detail'); who[a.split('-')[0]]+=1
print("  keys",dict(keys)); print("  by desk-prefix",who.most_common())
for a,at,p in c.execute("select agent,at,payload from ledger where kind='holdout.access' order by seq desc limit 2"):
    d=json.loads(p); print("  sample",a,at,{k:str(v)[:120] for k,v in d.items() if k!='_detail'})
print("## lab.stats last row"); 
for at,p in c.execute("select at,payload from ledger where kind='lab.stats' order by seq desc limit 1"): print("  ",at,p[:1500])
print("## lab.stats: sum over rows of evaluated, born_total, openai_usd, sail")
tot=collections.Counter()
for at,p in c.execute("select at,payload from ledger where kind='lab.stats'"):
    d=json.loads(p); tot['evaluated']+=d.get('evaluated',0); tot['openai']+=float(d.get('spend',{}).get('openai_usd',0)); tot['sail']+=float(d.get('spend',{}).get('sail_usd_estimate',0)); tot['rows']+=1; tot['window_h']+=d.get('window_seconds',0)/3600
print("  ",dict(tot))
