#!/usr/bin/env python3
"""A-5: the researcher. Sessions (agent.research tool='summary'), gate decisions, abstentions, strategies produced
(agent.strategy), replay passes of rewrites, and the forward result of rewrites (eval.block after the rewrite)."""
import sqlite3, json, collections, statistics
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400; H6=SNAP-6*3600
iso=lambda t: datetime.fromtimestamp(t,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
print("## agent.research rows by tool (24h):", c.execute("select json_extract(payload,'$.tool'),count(*) from ledger where kind='agent.research' and at>=? group by 1 order by 2 desc",(iso(H24),)).fetchall()[:25])
print("## sample summary payloads (3)")
for a,at,p in c.execute("select agent,at,payload from ledger where kind='agent.research' and json_extract(payload,'$.tool')='summary' order by seq desc limit 3"):
    d=json.loads(p); print("  ",a,at,{k:str(v)[:160] for k,v in d.items() if k not in ('_code',)})
print("## summary rows: keys")
keys=collections.Counter(); outcome=collections.Counter(); out24=collections.Counter(); out6=collections.Counter()
sess=[]
for a,at,p in c.execute("select agent,at,payload from ledger where kind='agent.research' and json_extract(payload,'$.tool')='summary'"):
    d=json.loads(p); keys.update(d.keys()); t=ep(at)
    o=d.get('outcome') or d.get('result') or d.get('decision') or ('abstain' if d.get('abstained') else None) or d.get('reason','')[:30]
    outcome[str(o)[:40]]+=1
    if t>=H24: out24[str(o)[:40]]+=1
    if t>=H6: out6[str(o)[:40]]+=1
    sess.append((a,t,d))
print("  keys",dict(keys))
print("  outcomes lifetime", outcome.most_common(15))
print("  outcomes 24h", out24.most_common(15), "n24", sum(out24.values()), "per h", round(sum(out24.values())/24,1))
print("  outcomes 6h", out6.most_common(15), "n6", sum(out6.values()), "per h", round(sum(out6.values())/6,1))
print("## research.gate decisions per hour (24h) and reasons (24h)")
g=collections.Counter(); gr=collections.Counter(); g6=collections.Counter()
for at,p in c.execute("select at,payload from ledger where kind='research.gate' and at>=?",(iso(H24),)):
    d=json.loads(p); g[d.get('decision')]+=1; gr[(d.get('decision'),str(d.get('reason'))[:28])]+=1
    if ep(at)>=H6: g6[d.get('decision')]+=1
print("  24h", dict(g), "per h", {k:round(v/24,1) for k,v in g.items()}, " 6h", dict(g6))
for k,v in gr.most_common(14): print("    ",v,k)
print("## agent.inactive reasons (24h):", c.execute("select json_extract(payload,'$.reason'),count(*) from ledger where kind='agent.inactive' and at>=? group by 1",(iso(H24),)).fetchall())
print("## agent.strategy rows: n lifetime / 24h / 6h; passed_replay; reason class")
st=[]; 
for a,at,p in c.execute("select agent,at,payload from ledger where kind='agent.strategy' order by seq"):
    d=json.loads(p); st.append((a,ep(at),d.get('passed_replay'),str(d.get('reason') or '')[:40], d.get('was') is not None))
n24=[s for s in st if s[1]>=H24]; n6=[s for s in st if s[1]>=H6]
print(f"  lifetime {len(st)} passed_replay={sum(1 for s in st if s[2])} | 24h {len(n24)} passed={sum(1 for s in n24 if s[2])} ({len(n24)/24:.1f}/h) | 6h {len(n6)} passed={sum(1 for s in n6 if s[2])}")
print("  reason classes 24h:", collections.Counter(s[3][:25] for s in n24).most_common(6))
print("  passed_replay values 24h:", collections.Counter(str(s[2]) for s in n24))
print("## eval.trial per hour 24h: n, passed; and by whether the agent's rung was 0 or 1")
tr=collections.Counter(); trp=collections.Counter()
for at,p in c.execute("select at,payload from ledger where kind='eval.trial' and at>=?",(iso(H24),)):
    d=json.loads(p); tr['n']+=1; tr['passed']+= 1 if d.get('passed') else 0
    for r in (d.get('reasons') or [])[:1]: trp[str(r)[:60]]+=1
print("  ",dict(tr), "per h", round(tr['n']/24,1), " top fail reasons:", trp.most_common(6))
print("## forward result of rewrites (agent.strategy with was!=None, 24h): eval.block log_growth after the rewrite, active blocks")
blocks=collections.defaultdict(list)
for a,at,p in c.execute("select agent,at,payload from ledger where kind='eval.block' and at>=?",(iso(H24-86400),)):
    d=json.loads(p); blocks[a].append((ep(at),float(d.get('log_growth') or 0),bool(d.get('active'))))
res=[]
for a,t,passed,reason,was in st:
    if t<H24 or not was: continue
    after=[b for b in blocks.get(a,[]) if b[0]>t]
    act=[b for b in after if b[2]]
    res.append((a,passed,len(act),sum(b[1] for b in act)))
print(f"  rewrites 24h with prior code: {len(res)}; with >=1 active block after: {sum(1 for r in res if r[2]>0)}; positive sum growth: {sum(1 for r in res if r[3]>0)}; negative: {sum(1 for r in res if r[3]<0)}; total growth {sum(r[3] for r in res):+.4f}")
print("  those that passed replay:", [(r[0],r[2],round(r[3],4)) for r in res if r[1] and r[2]>0][:20])
print("## cost per session: provider.request cost (24h) / summaries (24h)")
cost=c.execute("select sum(cast(json_extract(payload,'$.cost_usd') as real)) from ledger where kind='provider.request' and at>=?",(iso(H24),)).fetchone()[0]
sail=c.execute("select sum(cast(json_extract(payload,'$.usd') as real)) from ledger where kind='credit.charge' and json_extract(payload,'$.what')='research tokens' and at>=?",(iso(H24),)).fetchone()[0]
print(f"  luna cost 24h ${cost:.2f}; research tokens charged (luna+sail) ${sail:.2f}; sessions 24h {sum(out24.values())}; $/session (charged) {sail/max(sum(out24.values()),1):.4f}; strategies 24h {len(n24)}; $/strategy {sail/max(len(n24),1):.3f}; $/replay-passing strategy {sail/max(sum(1 for s in n24 if s[2]),1):.3f}")
