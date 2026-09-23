#!/usr/bin/env python3
"""A-1: the funnel. Every agent ever born: founder class, desk, family, rungs reached, time at each
stage, fills, death cause. Snapshot ledger only (read-only)."""
import sqlite3, json, collections, statistics, sys, re
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z')

def founder_class(p):
    """Who founded the agent, from the birth payload."""
    f=p.get('founder'); r=str(p.get('reason') or ''); parent=p.get('parent')
    if f and str(f).startswith('lab:'): return 'lab'
    if f and str(f).startswith('card:'): return 'foundry'
    if r.startswith('revived under the loosened replay gate'): return 'house-revival'
    if r.startswith('Merton, as architect'):
        # enroll() births both architect strategies and the repair engineer's merged fixes with this reason;
        # repairs carry a defect-style founder name (guard/fix/occ/identity/check/resolve)
        return 'repair' if (f and re.search(r'guard|fix|occ|identity|check|resolve|exits|prices_|subcent|entry', str(f))) else 'architect'
    if f and not parent: return 'seed'
    if r.startswith('a parameter mutation') or r.startswith('a House-staked'): return 'house-mutation'
    if r.startswith('The same edge') or r.startswith('Single-variable') or len(r)>60: return 'agent-fork'
    return 'other:'+r[:30]

agents={}
for seq,a,at,p in c.execute("select seq,agent,at,payload from ledger where kind='agent.born' order by seq"):
    d=json.loads(p)
    agents[a]=dict(seq=seq,born=ep(at),founder=d.get('founder'),reason=str(d.get('reason') or '')[:120],parent=d.get('parent'),
                   family=d.get('family'),niche=d.get('specialty'),venue=d.get('venue'),horizon=d.get('horizon'),
                   cls=founder_class(d),rung_max=0,rung_now=0,seat_at=None,r2_at=None,r3_at=None,died=None,cause=None,
                   trials=0,trials_passed=0,first_trial=None,first_pass=None,fills=0,fills_real=0,strategies=0)
# forks carry the child's reason in agent.forked; refine founder class for children
for seq,a,at,p in c.execute("select seq,agent,at,payload from ledger where kind='agent.forked'"):
    d=json.loads(p); ch=d.get('child')
    if ch in agents:
        agents[ch]['forked_by']=a; agents[ch]['fork_reason']=d.get('reason'); agents[ch]['staked_by']=d.get('staked_by')
        if agents[ch]['cls'] in ('house-mutation','agent-fork','other'):
            agents[ch]['cls']='house-mutation' if (d.get('staked_by')=='house' or d.get('reason') in ('population','')) else 'agent-fork'
for seq,a,at,p in c.execute("select seq,agent,at,payload from ledger where kind='eval.trial' order by seq"):
    if a not in agents: continue
    d=json.loads(p); g=agents[a]; g['trials']+=1
    if g['first_trial'] is None: g['first_trial']=ep(at)
    if d.get('passed'):
        g['trials_passed']+=1
        if g['first_pass'] is None: g['first_pass']=ep(at)
for seq,a,at,p in c.execute("select seq,agent,at,payload from ledger where kind='eval.verdict' order by seq"):
    if a not in agents: continue
    d=json.loads(p)
    if d.get('decision') in ('seat','promote','demote'):
        to=int(d.get('to_rung') or 0); g=agents[a]; g['rung_now']=to; g['rung_max']=max(g['rung_max'],to)
        if to==1 and g['seat_at'] is None: g['seat_at']=ep(at)
        if to==2 and g['r2_at'] is None: g['r2_at']=ep(at)
        if to==3 and g['r3_at'] is None: g['r3_at']=ep(at)
for seq,a,at,p in c.execute("select seq,agent,at,payload from ledger where kind='agent.died'"):
    if a in agents:
        d=json.loads(p); agents[a]['died']=ep(at); agents[a]['cause']=d.get('cause'); agents[a]['death_detail']=d.get('detail','')[:200]
# agent trades only: exclude the House's dust sweeps and its closing of dead agents' accounts
for a,b,n in c.execute("select agent,json_extract(payload,'$.book'),count(*) from ledger where kind='book.fill' and json_extract(payload,'$.source')!='dust' and coalesce(json_extract(payload,'$.reason'),'') not like 'the House is closing%' group by 1,2"):
    if a in agents:
        agents[a]['fills']+=n
        if b in ('alpaca','kalshi'): agents[a]['fills_real']+=n
for a,n in c.execute("select agent,count(*) from ledger where kind='agent.strategy' group by 1"):
    if a in agents: agents[a]['strategies']=n

def med(xs):
    xs=[x for x in xs if x is not None];
    if not xs: return None
    xs=sorted(xs); return (round(statistics.median(xs)/3600,1), round(xs[min(len(xs)-1,int(0.9*len(xs)))]/3600,1), len(xs))

rows=list(agents.values())
print("agents born:",len(rows),"living:",sum(1 for g in rows if g['died'] is None))
def funnel(keyf,label):
    print(f"\n## funnel by {label}: born / any trial / passed replay / reached r1 / r2 / r3 / living / living never-filled / died / displaced")
    grp=collections.defaultdict(list)
    for g in rows: grp[keyf(g)].append(g)
    for k,gs in sorted(grp.items(), key=lambda kv:-len(kv[1])):
        n=len(gs)
        print(f"{str(k):28s} {n:4d} {sum(1 for g in gs if g['trials']>0):4d} {sum(1 for g in gs if g['trials_passed']>0):4d} "
              f"{sum(1 for g in gs if g['rung_max']>=1):4d} {sum(1 for g in gs if g['rung_max']>=2):3d} {sum(1 for g in gs if g['rung_max']>=3):3d} "
              f"{sum(1 for g in gs if g['died'] is None):4d} {sum(1 for g in gs if g['died'] is None and g['fills']==0):4d} "
              f"{sum(1 for g in gs if g['died']):4d} {sum(1 for g in gs if g['cause']=='displaced'):4d}"
              f"   life_med/p90_h={med([ (g['died'] or SNAP)-g['born'] for g in gs])}")
funnel(lambda g:g['cls'],'founder class')
funnel(lambda g:g['niche'],'desk')
funnel(lambda g:g['family'],'family (top)') if '--family' in sys.argv else None

print("\n## time in stage (hours): birth->first trial, birth->first pass, first pass->seat(r1), seat->r2, r2->r3")
print(" birth->first trial", med([g['first_trial']-g['born'] for g in rows if g['first_trial']]))
print(" birth->first pass ", med([g['first_pass']-g['born'] for g in rows if g['first_pass']]))
print(" birth->seat r1    ", med([g['seat_at']-g['born'] for g in rows if g['seat_at']]))
print(" seat r1->r2       ", med([g['r2_at']-g['seat_at'] for g in rows if g['r2_at'] and g['seat_at']]))
print(" seat r1->r2 (from birth if no seat row)", med([g['r2_at']-(g['seat_at'] or g['born']) for g in rows if g['r2_at']]))
print(" r2->r3            ", med([g['r3_at']-g['r2_at'] for g in rows if g['r3_at'] and g['r2_at']]))
print(" r1 time until death (displaced, r1)", med([g['died']-(g['seat_at'] or g['born']) for g in rows if g['died'] and g['cause']=='displaced' and g['rung_max']==1]))
print(" r0 time until death (displaced, r0)", med([g['died']-g['born'] for g in rows if g['died'] and g['cause']=='displaced' and g['rung_max']==0]))

print("\n## deaths: cause x founder class")
ct=collections.Counter((g['cause'],g['cls']) for g in rows if g['died'])
for k,v in sorted(ct.items(), key=lambda kv:-kv[1]): print(f"  {k[0]:12s} {k[1]:16s} {v}")
print("\n## deaths: cause x rung at death")
ct=collections.Counter((g['cause'],g['rung_max']) for g in rows if g['died'])
for k,v in sorted(ct.items(), key=lambda kv:-kv[1]): print(f"  {k[0]:12s} r{k[1]} {v}")
disp=[g for g in rows if g['cause']=='displaced']
print(f"\n## displaced: {len(disp)}; with any fill {sum(1 for g in disp if g['fills']>0)}; with >=3 fills {sum(1 for g in disp if g['fills']>=3)}; with real fills {sum(1 for g in disp if g['fills_real']>0)}; median life h {med([g['died']-g['born'] for g in disp])}")
print("   displaced by desk: n / had fills")
ct=collections.defaultdict(lambda:[0,0])
for g in disp: ct[g['niche']][0]+=1; ct[g['niche']][1]+= g['fills']>0
for k,v in sorted(ct.items(), key=lambda kv:-kv[1][0]): print(f"   {str(k):24s} {v[0]:4d} {v[1]:4d}")

print("\n## the living, by desk: n / rung0 / rung1 / rung2 / rung3 / never filled / median age h / median hours since seat")
liv=[g for g in rows if g['died'] is None]
ct=collections.defaultdict(list)
for g in liv: ct[g['niche']].append(g)
for k,gs in sorted(ct.items(), key=lambda kv:-len(kv[1])):
    print(f"   {str(k):24s} {len(gs):3d} {sum(1 for g in gs if g['rung_now']==0):3d} {sum(1 for g in gs if g['rung_now']==1):3d} {sum(1 for g in gs if g['rung_now']==2):3d} {sum(1 for g in gs if g['rung_now']==3):3d} {sum(1 for g in gs if g['fills']==0):3d}  age={med([SNAP-g['born'] for g in gs])} seated={med([SNAP-g['seat_at'] for g in gs if g['seat_at']])}")
print(f"living total {len(liv)}; never filled {sum(1 for g in liv if g['fills']==0)}; rung0 {sum(1 for g in liv if g['rung_now']==0)} r1 {sum(1 for g in liv if g['rung_now']==1)} r2 {sum(1 for g in liv if g['rung_now']==2)} r3 {sum(1 for g in liv if g['rung_now']==3)}")
print("living by founder class:", collections.Counter(g['cls'] for g in liv))
print("\n## the 30 enroll() births (architect or repair): founder name, class, rung_max, fills, alive")
for g in rows:
    if g['reason'].startswith('Merton, as architect'): print(f"   {g['founder']:40s} {g['cls']:10s} r{g['rung_max']} fills={g['fills']} alive={g['died'] is None} desk={g['niche']}")
print("living never-filled by founder class:", collections.Counter(g['cls'] for g in liv if g['fills']==0))
print("living rung-0 age h by class:", {k:med([SNAP-g['born'] for g in liv if g['cls']==k and g['rung_now']==0]) for k in set(g['cls'] for g in liv)})
json.dump({a:{k:v for k,v in g.items()} for a,g in agents.items()}, open(f'{S}/study/queries/A-1.agents.json','w'))
