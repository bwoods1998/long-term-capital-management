#!/usr/bin/env python3
"""A-7: the seat market. Births and deaths per hour by cause (24h, 6h), desk occupancy vs max_members, graduates waiting per desk, expected wait."""
import sqlite3, json, collections
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
L=sqlite3.connect(f'file:{S}/snap/lab.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400; H6=SNAP-6*3600; H12=SNAP-12*3600
niches={n['id']:n for n in json.load(open('/home/bwoods1998/Work/ltcm-run/league/niches.json'))['niches']}
for label,since,h in (('24h',H24,24),('12h',H12,12),('6h',H6,6)):
    b=[g for g in agents.values() if g['born']>=since]; d=[g for g in agents.values() if g['died'] and g['died']>=since]
    print(f"## {label}: births {len(b)} ({len(b)/h:.1f}/h) by class {dict(collections.Counter(g['cls'] for g in b))}")
    print(f"      deaths {len(d)} ({len(d)/h:.1f}/h) by cause {dict(collections.Counter(g['cause'] for g in d))}; displaced at r0 {sum(1 for g in d if g['cause']=='displaced' and g['rung_max']==0)}, at r1 {sum(1 for g in d if g['cause']=='displaced' and g['rung_max']>=1)}; displaced with fills {sum(1 for g in d if g['cause']=='displaced' and g['fills']>0)}")
    print(f"      deaths by desk: {dict(collections.Counter(g['niche'] for g in d))}")
print("## desk occupancy vs max_members; graduates waiting (lab passed) per desk; displacements in 24h per desk -> hours per seat turnover")
liv=collections.Counter(g['niche'] for g in agents.values() if g['died'] is None)
disp24=collections.Counter(g['niche'] for g in agents.values() if g['died'] and g['died']>=H24 and g['cause']=='displaced')
waiting=collections.Counter(r[0] for r in L.execute("select niche from graduations where state='passed'"))
merged_unborn={'alpaca-index-etfs':2,'kalshi-sports':1,'kalshi-prices':1,'kalshi-sports-props':1,'alpaca-options':1}  # from A-4 NOT BORN list
tot_wait=0
for nid,n in niches.items():
    cap=n.get('max_members'); w=waiting.get(nid,0); t=disp24.get(nid,0)
    print(f"  {nid:22s} members={liv.get(nid,0):3d}/{cap}  waiting_lab={w:2d} unborn_merged_PRs={merged_unborn.get(nid,0)}  displaced_24h={t:3d} ({t/24:.2f}/h) -> expected wait for a graduate {'n/a' if t==0 else f'{(w+merged_unborn.get(nid,0))*24/t:.1f} h'} (queue {w+merged_unborn.get(nid,0)} / turnover)")
print("  league:", sum(liv.values()), "/ 96; lab graduates waiting", sum(waiting.values()), "; displacements 24h", sum(disp24.values()), f"({sum(disp24.values())/24:.1f}/h)")
print("## who gets the freed seats? births 24h by class vs lab graduates born 24h")
b24=[g for g in agents.values() if g['born']>=H24]
print("  ", dict(collections.Counter(g['cls'] for g in b24)))
print("## grace: displaced agents' age at death (h), by rung, 24h: median, p10, p90")
import statistics
for r in (0,1):
    xs=sorted((g['died']-g['born'])/3600 for g in agents.values() if g['died'] and g['died']>=H24 and g['cause']=='displaced' and g['rung_max']==r)
    if xs: print(f"  r{r}: n={len(xs)} median={statistics.median(xs):.1f} p10={xs[int(0.1*len(xs))]:.1f} p90={xs[int(0.9*len(xs))]:.1f}")
print("## what displaced agents in 24h had done: trials, passed, fills, active blocks (from eval.block), compute spent (from death detail)")
import re
spent=[]; trials=[]; fills=[]
for g in agents.values():
    if g['died'] and g['died']>=H24 and g['cause']=='displaced':
        m=re.search(r'spent \$([0-9.]+) of compute', g.get('death_detail','') or ''); 
        if m: spent.append(float(m.group(1)))
        trials.append(g['trials']); fills.append(g['fills'])
print(f"  n={len(trials)} median trials={statistics.median(trials) if trials else None} with fills={sum(1 for f in fills if f>0)} compute spent: sum=${sum(spent):.2f} median=${statistics.median(spent) if spent else 0:.2f} (n with figure {len(spent)})")
