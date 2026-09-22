# Offline, read-only replay of the research gate over the production ledger (runs on the House box via rx.py).
# Approximate: no market-availability, blocker-lift or Jev relevance triggers; a skipped session is still
# counted in the next streak. Sept 22, 2026 output is in docs/design/2026-09-22-jev-sensor.md.
import sqlite3,json,collections
from datetime import datetime
db=sqlite3.connect('file:/workspace/state/ledger.sqlite?mode=ro',uri=True)
ep=lambda s: datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
niche={a:json.loads(p).get('specialty') for a,p in db.execute("select agent,payload from ledger where kind='agent.born'")}
summ=collections.defaultdict(list)
for seq,a,at,p in db.execute("select seq,agent,at,payload from ledger where kind='agent.research' and json_extract(payload,'$.tool')='summary' order by seq"):
    summ[a].append((seq,ep(at),json.loads(p)))
trig=collections.defaultdict(list)
for seq,a,k,p in db.execute("select seq,agent,kind,payload from ledger where kind in ('book.fill','book.settle','book.refused','agent.strategy','eval.verdict','credit.grant') order by seq"):
    if k=='eval.verdict' and json.loads(p).get('decision') in ('look','progress'): continue
    trig[a].append(seq)
notes=[(seq,a,json.loads(p).get('niche')) for seq,a,p in db.execute("select seq,agent,payload from ledger where kind='library.note' order by seq")]
import bisect
def outcome(p):
    r=str(p.get('reason') or '')
    if r.startswith('provider') or r.startswith('tool outcome'): return 'p'
    if p.get('candidate'): return 'c'
    if int(p.get('trials') or 0)>0: return 't'
    return 'a'
tot=skip=skip_c=skip_cost=0.0; n=0; skips=0; missc=0; costall=0
by=collections.Counter()
for a,rows in summ.items():
    streak=0
    ts=trig[a]
    for i,(seq,t,p) in enumerate(rows):
        n+=1; cost=float(p.get('cost_usd') or 0); costall+=cost
        if i>0:
            pseq,pt,_=rows[i-1]
            fired=bisect.bisect_right(ts,seq)-bisect.bisect_right(ts,pseq)>0
            fired=fired or any(pseq<s<seq and na==niche.get(a) and aa!=a for s,aa,na in notes)
            gap=t-pt
            AFTER=2  # game.json research.gate.after (v0 dials): x2 after two empty passes, x4 after three, x8 cap
            if not fired and streak>=AFTER and gap < min(2**(streak-AFTER+1),8)*3*3600 and gap<24*3600:
                skips+=1; skip_cost+=cost
                o=outcome(p); by[o]+=1
                if o=='c': missc+=1
        o=outcome(p)
        if o=='a': streak+=1
        elif o in 'ct': streak=0
print(json.dumps({'sessions':n,'cost':round(costall,2),'would_skip':skips,'share':round(skips/n,3),'skip_cost':round(skip_cost,2),'skipped_outcomes':by,'skipped_with_candidate':missc,'miss_rate':round(missc/skips,4) if skips else None}))
