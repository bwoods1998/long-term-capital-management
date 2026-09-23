#!/usr/bin/env python3
"""A-6: forward practice results by founder class and desk: eval.block active log-growth since seat, per agent; alloc.board latest W_paper/E."""
import sqlite3, json, collections, statistics
from datetime import datetime, timezone
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
def ep(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
SNAP=ep('2026-09-23T16:28:00Z'); H24=SNAP-86400
fwd=collections.defaultdict(lambda:[0,0,0.0,0.0,0.0])  # blocks, active, sum lg, sum pos, sum neg
for a,at,p in c.execute("select agent,at,payload from ledger where kind='eval.block'"):
    if a not in agents: continue
    d=json.loads(p); f=fwd[a]; f[0]+=1
    if d.get('active'):
        f[1]+=1; lg=float(d.get('log_growth') or 0); f[2]+=lg; f[3]+= max(lg,0); f[4]+=min(lg,0)
board={}
for at,p in c.execute("select at,payload from ledger where kind='alloc.board' order by seq"):
    d=json.loads(p)
    for a,row in d.get('agents',{}).items():
        if len(row)>=7: board[a]=(at,row)
def show(keyf,label):
    print(f"\n## forward by {label}: agents / with>=1 active block / active blocks / sum log-growth / n positive / n negative / mean W_paper (latest board) / n W_paper>1 / n with real band")
    grp=collections.defaultdict(list)
    for a,g in agents.items(): grp[keyf(g)].append(a)
    for k,names in sorted(grp.items(), key=lambda kv:-len(kv[1])):
        act=[a for a in names if fwd[a][1]>0]
        Ws=[board[a][1][2] for a in names if a in board and board[a][1][2] is not None]
        real=[a for a in names if a in board and board[a][1][0] not in ('paper',None)]
        print(f"  {str(k):22s} n={len(names):4d} act={len(act):3d} blocks={sum(fwd[a][1] for a in names):5d} sumLG={sum(fwd[a][2] for a in names):+.4f} pos={sum(1 for a in act if fwd[a][2]>0):3d} neg={sum(1 for a in act if fwd[a][2]<0):3d} meanW={statistics.mean(Ws) if Ws else float('nan'):.4f} W>1={sum(1 for w in Ws if w>1):3d}/{len(Ws)} real={len(real)}")
show(lambda g:g['cls'],'founder class')
show(lambda g:g['niche'],'desk')
show(lambda g:(g['cls'], 'alive' if g['died'] is None else 'dead'),'class x alive')
print("\n## living agents with W_paper>1.0 on the latest board (name, class, desk, band, W_paper, W_real, E, trades, real_trades, seated h)")
liv=[(a,g) for a,g in agents.items() if g['died'] is None and a in board]
rows=sorted(liv, key=lambda ag:-(board[ag[0]][1][2] or 0))
for a,g in rows[:25]:
    at,r=board[a]; print(f"  {a:24s} {g['cls']:14s} {str(g['niche']):22s} {str(r[0]):6s} W={r[2]:.4f} Wr={r[3]} E={r[4]:.4f} tr={r[5]} rt={r[6]} seated_h={(SNAP-(g['seat_at'] or g['born']))/3600:.1f}")
print("  living on board:",len(liv), " W>1:",sum(1 for a,g in liv if (board[a][1][2] or 0)>1), " W<1:",sum(1 for a,g in liv if (board[a][1][2] or 1)<1), " W==1:",sum(1 for a,g in liv if board[a][1][2]==1))
print("  bands:",collections.Counter(board[a][1][0] for a,g in liv))
print("\n## foundry-born agents: name, desk, alive, rung, fills, active blocks, sumLG, W_paper")
for a,g in sorted(agents.items(), key=lambda ag:ag[1]['born']):
    if g['cls'] in ('foundry','lab','house-revival'):
        r=board.get(a,(None,[None]*7))[1]
        print(f"  {a:22s} {g['cls']:13s} {str(g['niche']):22s} alive={g['died'] is None!s:5s} r{g['rung_max']} fills={g['fills']:3d} act={fwd[a][1]:3d} LG={fwd[a][2]:+.4f} W={r[2]} tr={r[5]}")
