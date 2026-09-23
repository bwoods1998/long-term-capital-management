"""C-14: cost and rate of research sessions since 09-22T00:00: sessions/hour, $ spent by abstaining vs acting sessions, by desk; and cost per candidate produced."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
tot=collections.defaultdict(lambda:[0,0.0,0,0.0,0]); hours=set()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.research' and at>='2026-09-22T00:00' and payload like '%\"tool\":\"summary\"%'"):
    p=json.loads(p)
    if p.get('tool')!='summary': continue
    hours.add(at[:13]); d=desk(a); c=float(p.get('cost_usd') or 0)
    abst=not p.get('candidate') and int(p.get('trials') or 0)==0
    t=tot[d]
    if abst: t[0]+=1; t[1]+=c
    else: t[2]+=1; t[3]+=c
    if p.get('candidate'): t[4]+=1
A=sum(v[0] for v in tot.values()); B=sum(v[2] for v in tot.values()); CA=sum(v[1] for v in tot.values()); CB=sum(v[3] for v in tot.values()); K=sum(v[4] for v in tot.values())
print(f'window hours={len(hours)} sessions={A+B} ({(A+B)/len(hours):.0f}/h) abstain={A} (${CA:.2f}, ${CA/max(A,1):.4f} each) act={B} (${CB:.2f}, ${CB/max(B,1):.4f} each) candidates={K} -> ${(CA+CB)/max(K,1):.2f} per candidate')
for d,v in sorted(tot.items(),key=lambda x:-x[1][1]): print(f'  {d:22} abst={v[0]:4} ${v[1]:6.2f}  act={v[2]:3} ${v[3]:6.2f} cand={v[4]}')
