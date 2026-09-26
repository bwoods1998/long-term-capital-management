"""C-9: stratified sample for L7.1: journals (agent.research tool=journal), abstentions (agent.inactive reason=abstained),
lab submissions (lab.sqlite candidates origin in agent/sol), audit verdicts (audit.verdict summary), last research turns (summary rows).
Strata: desk x rung (0/1/2) x founder (house seed / foundry card / lab / repair / architect). Prints ~80 items with ids."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
lab=sqlite3.connect(f'file:{S}/snap/lab.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
founder={}
for a,p in db.execute("select agent,payload from ledger where kind='agent.born'"):
    p=json.loads(p); f=p.get('founder') or ''; r=(p.get('reason') or '').lower()
    founder[a]=('card' if f.startswith('card:') else 'lab' if f.startswith('lab:') else 'seed' if f and '_' not in f and '-' in f and not f.startswith(('haghani','mcentee','scholes','krasker','meriwether','hawkins','leahy','hufschmid','mullins','huang','hilibrand','rosenfeld')) else 'repair/architect' if f else ('fork/house' if 'fork' in r or 'child' in r or 'mutation' in r else 'house'))
print('founder classes:',collections.Counter(founder.values()))
moves=collections.defaultdict(list)
for a,at,p in db.execute("select agent,at,payload from ledger where kind='eval.verdict' order by seq"):
    p=json.loads(p)
    if p.get('decision') in ('promote','demote','seat','eligible') and p.get('to_rung') is not None: moves[a].append((at,int(p['to_rung'])))
def rung(a,at):
    r=0
    for t,x in moves.get(a,[]):
        if t<=at: r=x
    return r
seen=collections.Counter(); n=0
print('\n##### JOURNALS (agent.research tool=journal), newest first, max 2 per desk x rung x founder')
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.research' and payload like '%\"tool\":\"journal\"%' order by seq desc"):
    p=json.loads(p)
    if p.get('tool')!='journal': continue
    k=('J',desk(a),rung(a,at),founder.get(a,'?'))
    if seen[k]>=2: continue
    seen[k]+=1; n+=1
    print(f'[J{n}] {a} {k[1]} r{k[2]} {k[3]} {at[5:16]}: ',(p.get('text') or '').replace('\n',' ')[:600])
print('\n##### ABSTENTIONS (agent.inactive reason=abstained), newest first, max 1 per desk x rung')
m=0
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.inactive' and payload like '%abstained%' order by seq desc"):
    p=json.loads(p)
    if p.get('reason')!='abstained': continue
    k=('A',desk(a),rung(a,at))
    if seen[k]>=1: continue
    seen[k]+=1; m+=1
    print(f'[A{m}] {a} {k[1]} r{k[2]} {founder.get(a,"?")} {at[5:16]}: ',(p.get('detail') or '').replace('\n',' ')[:500])
print('\n##### LAB SUBMISSIONS by agents (lab.sqlite candidates origin agent/sol)')
q=0
for row in lab.execute("select id,niche,origin,author,idea,status,eligible,gate,fitness,trades,summary,created from candidates where origin in ('agent','sol') order by created desc"):
    q+=1
    if q>18: break
    print(f'[L{q}] {row[3]} {row[1]} origin={row[2]} status={row[5]} elig={row[6]} gate={row[7]} fit={row[8]} trades={row[9]}: idea=',(row[4] or '')[:200].replace('\n',' '),'| summary=',(row[10] or '')[:200].replace('\n',' '))
print('\n##### AUDIT VERDICTS (all 21)')
v=0
for at,a,p in db.execute("select at,agent,payload from ledger where kind='audit.verdict' order by seq"):
    p=json.loads(p); v+=1
    print(f'[V{v}] {a} {desk(a)} {at[5:16]} approve={p.get("approve")} conf={p.get("confidence")} blocks={p.get("blocks_at_audit")} ${p.get("cost_usd")}: ',(p.get('summary') or '').replace('\n',' ')[:420])
print('\n##### LAST RESEARCH TURNS (summary rows with a candidate or trials>0), newest first, max 1 per desk')
w=0
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.research' and payload like '%\"tool\":\"summary\"%' order by seq desc"):
    p=json.loads(p)
    if p.get('tool')!='summary' or not (p.get('candidate') or int(p.get('trials') or 0)>0): continue
    k=('S',desk(a))
    if seen[k]>=1: continue
    seen[k]+=1; w+=1
    print(f'[S{w}] {a} {k[1]} r{rung(a,at)} {founder.get(a,"?")} {at[5:16]} cand={p.get("candidate")} trials={p.get("trials")} ${p.get("cost_usd")}: ',(p.get('summary') or '').replace('\n',' ')[:520])
print('\nTOTAL items:',n+m+min(q,18)+v+w)
