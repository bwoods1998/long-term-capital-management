#!/usr/bin/env python3
"""A-11: why merged strategies stay unborn (ops.alert texts), and how many residents the grace rules protect right now."""
import sqlite3, json, collections
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z')
print("## ops.alert mentioning 'could not be born' / 'enroll' / 'waits for a seat' (last 24h): count and last 5")
rows=[(at,json.loads(p)) for at,p in c.execute("select at,payload from ledger where kind='ops.alert' and at>='2026-09-22T16:28:00Z' order by seq")]
hits=[(at,d) for at,d in rows if any(k in json.dumps(d).lower() for k in ('could not be born','enroll','seat'))]
print("  alerts 24h:",len(rows),"matching:",len(hits))
for at,d in hits[-6:]: print("   ",at[5:16],str(d.get('level')),str(d.get('text') or d)[:230])
print("## ops.alert levels 24h:",collections.Counter(d.get('level') for at,d in rows))
print("## residents now: protected by rung>=2 / W_paper>1 (latest board) / seated <12h / seated <12h session-time desks; the rest are displaceable")
board={}
for at,p in c.execute("select at,payload from ledger where kind='alloc.board' order by seq desc limit 1"):
    board={a:r for a,r in json.loads(p)['agents'].items()}
liv={a:g for a,g in agents.items() if g['died'] is None}
r2=sum(1 for a,g in liv.items() if g['rung_now']>=2)
wpos=sum(1 for a,g in liv.items() if g['rung_now']<2 and a in board and len(board[a])>4 and (board[a][2] or 0)>1)
young=sum(1 for a,g in liv.items() if g['rung_now']<2 and not (a in board and len(board[a])>4 and (board[a][2] or 0)>1) and SNAP-(g['seat_at'] or g['born'])<12*3600)
print(f"  living {len(liv)}: rung>=2 {r2}; W_paper>1 {wpos}; seated <12h (others) {young}; remaining {len(liv)-r2-wpos-young}")
hours_desks={'alpaca-index-etfs','alpaca-megacaps','alpaca-options'}
print("  of the remaining, on desks that keep hours (grace in session time):", sum(1 for a,g in liv.items() if g['rung_now']<2 and not (a in board and len(board[a])>4 and (board[a][2] or 0)>1) and SNAP-(g['seat_at'] or g['born'])>=12*3600 and g['niche'] in hours_desks))
print("  remaining by desk:", collections.Counter(g['niche'] for a,g in liv.items() if g['rung_now']<2 and not (a in board and len(board[a])>4 and (board[a][2] or 0)>1) and SNAP-(g['seat_at'] or g['born'])>=12*3600))
print("  remaining that have traded (protected until 5 closed trades / 3 sessions):", sum(1 for a,g in liv.items() if g['rung_now']<2 and not (a in board and len(board[a])>4 and (board[a][2] or 0)>1) and SNAP-(g['seat_at'] or g['born'])>=12*3600 and g['fills']>0))
