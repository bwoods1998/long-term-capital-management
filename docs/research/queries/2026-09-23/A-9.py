#!/usr/bin/env python3
"""A-9: 'never traded' under several definitions for the 96 living residents."""
import sqlite3, json, collections
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
liv={a:g for a,g in agents.items() if g['died'] is None}
fills=collections.defaultdict(list)
for a,at,p in c.execute("select agent,at,payload from ledger where kind='book.fill'"):
    d=json.loads(p); fills[a].append((ep(at), d.get('book'), d.get('source'), str(d.get('reason') or '').startswith('the House is closing')))
def cnt(pred,label):
    n=sum(1 for a,g in liv.items() if not any(pred(a,g,f) for f in fills.get(a,[])))
    print(f"  {label:70s} never: {n}/96")
cnt(lambda a,g,f: True, "any fill row at all (incl. House dust/closing)")
cnt(lambda a,g,f: f[2]!='dust' and not f[3], "agent fill (excl. dust/closing), any time, any book")
cnt(lambda a,g,f: f[2]!='dust' and not f[3] and f[0]>=(g['seat_at'] or g['born']), "agent fill since its rung-1 seat")
cnt(lambda a,g,f: f[2]!='dust' and not f[3] and f[0]>=ep('2026-09-23T06:30:00Z'), "agent fill since 06:30Z today (floor_watch window)")
cnt(lambda a,g,f: f[2]!='dust' and not f[3] and f[0]>=ep('2026-09-22T16:28:00Z'), "agent fill in the last 24h")
cnt(lambda a,g,f: f[2]=='venue' and not f[3], "source=venue fill (excl. closing)")
# intents and orders
ints=collections.Counter(a for (a,) in c.execute("select agent from ledger where kind='agent.intent'"))
ords=collections.Counter(a for (a,) in c.execute("select agent from ledger where kind='book.order'"))
print(f"  living with no agent.intent ever: {sum(1 for a in liv if ints.get(a,0)==0)}/96; with no book.order ever: {sum(1 for a in liv if ords.get(a,0)==0)}/96")
wakes=collections.Counter(a for (a,) in c.execute("select agent from ledger where kind='agent.woke' and at>='2026-09-22T16:28:00Z'"))
W='2026-09-22T16:28:00Z'
q=lambda k: c.execute("select count(*) from ledger where kind=? and at>=?",(k,W)).fetchone()[0]
nf=sum(1 for a in agents for f in fills.get(a,[]) if f[0]>=ep(W) and f[2]!='dust' and not f[3])
print(f"  24h: wakes(living) {sum(wakes.get(a,0) for a in liv)}; intents {q('agent.intent')}; orders {q('book.order')}; refused {q('book.refused')}; cancels {q('book.cancel')}; agent fills {nf}")
