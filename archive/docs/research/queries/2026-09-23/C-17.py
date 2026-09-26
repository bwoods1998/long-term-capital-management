"""C-17: (a) the 576 ETF-desk 'outside regular hours' refusals: distinct intent ids, agents, and whether each intent id has an agent.intent row;
(b) causes of death and rung at death for hilibrand/rosenfeld agents dying in the window; (c) same for all desks (churn rate)."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
ids=collections.Counter(); ag=collections.Counter(); first={}; last={}
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.refused' and at>='2026-09-21T16:28' and payload like '%outside regular hours%'"):
    p=json.loads(p); i=p.get('intent_id'); ids[i]+=1; ag[a]+=1; first.setdefault(i,at); last[i]=at
print('(a) refusals:',sum(ids.values()),'distinct intent ids:',len(ids),'agents:',dict(ag))
has=0
for i in ids:
    if db.execute("select 1 from ledger where kind='agent.intent' and payload like ? limit 1",(f'%{i}%',)).fetchone(): has+=1
print('   intent ids with an agent.intent row:',has)
for i,n in ids.most_common(6): print('   ',i[:20],n,'x',first[i][5:16],'..',last[i][5:16])
# sample one refused payload's reason text
r=db.execute("select payload from ledger where kind='book.refused' and at>='2026-09-21T16:28' and payload like '%outside regular hours%' order by seq desc limit 1").fetchone()
print('   sample:',r[0][:300])
# what kind of order: look up the agent.intent for the most common id
i=ids.most_common(1)[0][0]
r=db.execute("select at,agent,payload from ledger where kind='agent.intent' and payload like ? limit 1",(f'%{i}%',)).fetchone()
print('   its intent:',r[0] if r else None,(r[2][:400] if r else ''))
print('\n(b) deaths in window by desk x cause (all desks), and hilibrand/rosenfeld detail')
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
c=collections.Counter(); det=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.died' and at>='2026-09-21T16:28'"):
    p=json.loads(p); d=DESK.get(a.split('-')[0],'?'); c[(d,p.get('cause'))]+=1
    if d in ('kalshi-crypto-strikes','alpaca-crypto-majors'): det[(d,p.get('cause'),(p.get('detail') or '')[:90])]+=1
for k,v in sorted(c.items()): print('  ',v,k)
print('  detail:')
for k,v in det.most_common(12): print('   ',v,k)
print('\n births in window:',db.execute("select count(*) from ledger where kind='agent.born' and at>='2026-09-21T16:28'").fetchone(),' deaths:',db.execute("select count(*) from ledger where kind='agent.died' and at>='2026-09-21T16:28'").fetchone())
