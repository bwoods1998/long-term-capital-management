#!/usr/bin/env python3
"""A-5b: research sessions: share that produced a candidate / spent a counted replay trial, 24h and 6h; cost per producing session."""
import sqlite3, json, collections
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400; H6=SNAP-6*3600
iso=lambda t: datetime.fromtimestamp(t,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
for label,since in (('24h',H24),('6h',H6)):
    n=0; cand=0; trials=0; cost=0.0; costc=0.0; turns=[]; bycls=collections.defaultdict(lambda:[0,0,0,0.0])
    for a,at,p in c.execute("select agent,at,payload from ledger where kind='agent.research' and json_extract(payload,'$.tool')='summary' and at>=?",(iso(since),)):
        d=json.loads(p); n+=1; cd=str(d.get('candidate'))=='True'; tr=int(d.get('trials') or 0); cs=float(d.get('cost_usd') or 0)
        cand+=cd; trials+= tr>0; cost+=cs; costc+= cs if cd else 0; turns.append(int(d.get('turns') or 0))
        cls=agents.get(a,{}).get('cls','?'); b=bycls[cls]; b[0]+=1; b[1]+=cd; b[2]+= tr>0; b[3]+=cs
    print(f"## {label}: sessions {n} ({n/(24 if label=='24h' else 6):.0f}/h); produced a candidate {cand} ({cand/max(n,1):.0%}); spent a counted trial {trials} ({trials/max(n,1):.0%}); $ {cost:.2f} (${cost/max(n,1):.4f}/session; ${cost/max(cand,1):.3f}/candidate session); median turns {sorted(turns)[len(turns)//2] if turns else None}")
    for k,b in sorted(bycls.items(), key=lambda kv:-kv[1][0]): print(f"    {k:16s} sessions={b[0]:5d} candidate={b[1]:4d} ({b[1]/max(b[0],1):.0%}) trial={b[2]:4d} ${b[3]:.2f}")
