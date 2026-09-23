#!/usr/bin/env python3
"""A-10: the foundry's cards through replay: eval.trial rows keyed to card lines that were never born; cards by model and by outcome."""
import sqlite3, json, collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
c=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
agents=json.load(open(f'{S}/study/queries/A-1.agents.json'))
cards={}
for at,p in c.execute("select at,payload from ledger where kind='hypothesis.card' order by seq"):
    d=json.loads(p); cards[d['id']]=dict(at=at,line=d.get('line_id'),model=d.get('model'),niche=d.get('niche'),name=d.get('name'),transfer=d.get('transfer'))
print("cards",len(cards),"by model",collections.Counter(v['model'] for v in cards.values()),"transfer",sum(1 for v in cards.values() if v.get('transfer')))
born_lines={g['founder'][5:] for g in agents.values() if g.get('founder','') and str(g['founder']).startswith('card:')}
born_cards={cid for cid in cards if any(cid.startswith(b) or b.startswith(cid[:8]) for b in born_lines)}
print("born from cards:",len(born_cards))
# eval.trial rows by agent name not in born agents
unk=collections.defaultdict(lambda:[0,0])
for a,at,p in c.execute("select agent,at,payload from ledger where kind='eval.trial'"):
    if a in agents: continue
    d=json.loads(p); unk[a][0]+=1; unk[a][1]+= 1 if d.get('passed') else 0
print("eval.trial agents not born:",len(unk),"trials",sum(v[0] for v in unk.values()),"passed",sum(v[1] for v in unk.values()))
byline={}
for cid,v in cards.items():
    ln=v['line']; byline.setdefault(ln,[]).append(cid)
print("card lines:",len(byline))
# match unborn trial agents to card lines
matched=0; mp=0; mt=0
for a,(n,pas) in unk.items():
    if a in byline: matched+=1; mt+=n; mp+=pas
print(f"unborn trial agents matching a card line: {matched} trials={mt} passed={mp}")
print("sample unborn trial agents:", list(unk.items())[:12])
# cards per desk: born / trialed-unborn / no trial
desk=collections.defaultdict(lambda:[0,0,0,0])
for cid,v in cards.items():
    d=desk[v['niche']]; d[0]+=1
    if cid in born_cards: d[1]+=1
    elif v['line'] in unk: d[2]+=1; d[3]+= unk[v['line']][1]>0
for k,d in sorted(desk.items(), key=lambda kv:-kv[1][0]): print(f"  {k:22s} cards={d[0]:3d} born={d[1]:2d} trialed_unborn={d[2]:2d} (passed {d[3]}) untrialed={d[0]-d[1]-d[2]}")
print("cards by hour:", sorted(collections.Counter(v['at'][:13] for v in cards.values()).items()))
