#!/usr/bin/env python3
"""A-4: Merton's roles: passes, changes (PRs), what merged strategies did afterwards, repairs, lessons."""
import sqlite3, json, collections, re
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400
print("## merton.change by role x status (lifetime | last 24h)")
ct=collections.Counter(); ct24=collections.Counter(); changes=[]
for at,p in c.execute("select at,payload from ledger where kind='merton.change' order by seq"):
    d=json.loads(p); ct[(d.get('role'),d.get('status'))]+=1
    if ep(at)>=H24: ct24[(d.get('role'),d.get('status'))]+=1
    changes.append((at,d))
for k in sorted(ct): print(f"  {k[0]:10s} {k[1]:14s} {ct[k]:3d}  (24h {ct24.get(k,0)})")
print("## merged strategy PRs (architect branch incl. repair-*): strategy name -> born? rung, fills, alive, cause")
born_by_founder={g['founder']:(a,g) for a,g in agents.items() if g.get('founder')}
def norm(s): return re.sub(r'[^a-z0-9]','',s.lower())
merged=[(at,d) for at,d in changes if d.get('status') in ('merged','deployed') and d.get('role')=='architect']
seen=set(); nborn=0; nmerged=0
for at,d in merged:
    br=d['branch']; name=br.split('/')[-1]; name=re.sub(r'-[0-9a-f]{6,8}$','',name); name=re.sub(r'^repair-','',name)
    if name in seen: continue
    seen.add(name); nmerged+=1
    hit=None
    for f,(a,g) in born_by_founder.items():
        if norm(f)==norm(name) or norm(f) in norm(name) or norm(name) in norm(f): hit=(a,g); break
    kind='repair' if '/repair-' in br else 'architect'
    if hit:
        a,g=hit; nborn+=1
        print(f"  {at[5:16]} {kind:9s} #{d.get('number')} {name:42s} -> {a:24s} r{g['rung_max']} fills={g['fills']} alive={g['died'] is None} cause={g.get('cause')} trials={g['trials']}/{g['trials_passed']}")
    else:
        print(f"  {at[5:16]} {kind:9s} #{d.get('number')} {name:42s} -> NOT BORN")
print(f"  merged strategy PRs (distinct): {nmerged}; born: {nborn}")
print("## merton.pass role x outcome: summary starts (first 40 chars) top per role")
for role in ('architect','teacher','toolsmith','operator','designer','engineer','foundry','consultant'):
    cnt=collections.Counter(); cost=0.0; n=0
    for at,p in c.execute("select at,payload from ledger where kind='merton.pass' and json_extract(payload,'$.role')=?",(role,)):
        d=json.loads(p); n+=1; cost+=float(d.get('cost_usd') or 0)
        s=str(d.get('summary') or d.get('answer') or d.get('error') or d.get('skipped') or '')[:50]
        cnt[('PR' if d.get('branch') else ('cards' if d.get('cards') is not None else ('err' if d.get('error') else 'nochange')), s[:45])]+=1
    print(f"  {role}: n={n} ${cost:.2f}")
    for k,v in cnt.most_common(5): print(f"      {v:3d} {k}")
print("## foundry passes: cards per pass, refused, cost")
tot=collections.Counter()
for at,p in c.execute("select at,payload from ledger where kind='merton.pass' and json_extract(payload,'$.role')='foundry'"):
    d=json.loads(p); tot['passes']+=1; tot['cards']+=len(d.get('cards') or []) if isinstance(d.get('cards'),list) else (d.get('cards') or 0); tot['refused']+=1 if d.get('refused') else 0; tot['cost']+=float(d.get('cost_usd') or 0)
print("  ",dict(tot))
print("## repair.status by state: n, $cost, with pr")
ct=collections.defaultdict(lambda:[0,0.0,0])
for at,p in c.execute("select at,payload from ledger where kind='repair.status'"):
    d=json.loads(p); a=ct[d.get('state')]; a[0]+=1; a[1]+=float(d.get('cost_usd') or 0); a[2]+= 1 if d.get('pr') else 0
for k,a in ct.items(): print(f"  {str(k):14s} n={a[0]:4d} ${a[1]:.2f} with_pr={a[2]}")
print("## repair.reported by kind x source: n, distinct keys")
ct=collections.defaultdict(set); n=collections.Counter()
for at,p in c.execute("select at,payload from ledger where kind='repair.reported'"):
    d=json.loads(p); ct[(d.get('kind'),d.get('source'))].add(d.get('key')); n[(d.get('kind'),d.get('source'))]+=1
for k in sorted(n): print(f"  {str(k):34s} rows={n[k]:5d} distinct_keys={len(ct[k])}")
print("## playbook.entry and library.note counts, last 24h; teacher merged titles (24h)")
print("  playbook.entry", c.execute("select count(*) from ledger where kind='playbook.entry'").fetchone(), "24h", c.execute("select count(*) from ledger where kind='playbook.entry' and at>=?",(datetime.fromtimestamp(H24,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),)).fetchone())
print("  library.note", c.execute("select count(*) from ledger where kind='library.note'").fetchone())
for at,d in changes:
    if d.get('role')=='teacher' and d.get('status')=='merged' and ep(at)>=H24: print("   ",at[5:16],d.get('title')[:90])
print("## operator/designer/toolsmith changes: titles and status")
for at,d in changes:
    if d.get('role') in ('operator','designer','toolsmith'): print("   ",at[5:16],d.get('role'),d.get('status'),str(d.get('title'))[:80])
