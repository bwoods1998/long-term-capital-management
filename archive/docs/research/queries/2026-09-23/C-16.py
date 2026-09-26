"""C-16: (a) 'no seat' refusals by agent, whether dead at the time, by date; (b) living members per desk at four instants;
(c) how many refused intents were 'acted' wakes (intent count in agent.woke) on the ETF desk at night."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
died={a:at for at,a in db.execute("select at,agent from ledger where kind='agent.died'")}
born={a:at for at,a in db.execute("select at,agent from ledger where kind='agent.born'")}
c=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.refused' and at>='2026-09-21T16:28' and payload like '%has no seat%'"):
    p=json.loads(p); dead = a in died and died[a]<at
    c[(at[:10],a,'dead' if dead else 'alive',p.get('book'))]+=1
print('=== (a) no-seat refusals by (date, agent, dead?, book)')
for k,v in sorted(c.items()): print('  ',v,k)
print('\n=== (b) living members per desk at instants')
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
for T in ('2026-09-21T18:00','2026-09-22T06:00','2026-09-22T18:00','2026-09-23T06:00','2026-09-23T16:00'):
    cnt=collections.Counter()
    for a,b in born.items():
        if b<=T and (a not in died or died[a]>T): cnt[DESK.get(a.split('-')[0],'?')]+=1
    print('  ',T,dict(sorted(cnt.items())),'total',sum(cnt.values()))
print('\n=== hilibrand / rosenfeld births and deaths in window')
for a in sorted(born):
    if a.split('-')[0] in ('hilibrand','rosenfeld') and (born[a]>='2026-09-21' or died.get(a,'9')>='2026-09-21'): print('  ',a,'born',born[a][5:16],'died',died.get(a,'-')[5:16])
print('\n=== (c) ETF desk night wakes with intents (06-13Z, last 48h): wakes, wakes with intents>0')
w=i=0
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.woke' and agent like 'scholes%' and at>='2026-09-21T16:28' and substr(at,12,2) between '06' and '13'"):
    p=json.loads(p); w+=1; i+= 1 if p.get('intents',0)>0 else 0
print('  ',w,i)
