"""C-20: last 24 h (09-22T16:28 -> 09-23T16:28): per UTC hour, desks with venue fills / with intents / offered-no-intent; min and median."""
import sqlite3,json,collections,statistics
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
T0='2026-09-22T16:28'
f=collections.defaultdict(set); i=collections.defaultdict(set); o=collections.defaultdict(set); rf=collections.defaultdict(set)
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill' and at>=? and agent!='house'",(T0,)):
    p=json.loads(p)
    if p.get('source') in ('venue','cross'):
        f[at[:13]].add(desk(a))
        if p.get('real_money'): rf[at[:13]].add(desk(a))
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.intent' and at>=?",(T0,)): i[at[:13]].add(desk(a))
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.woke' and at>=?",(T0,)):
    if json.loads(p).get('offered',0)>0: o[at[:13]].add(desk(a))
hours=sorted(set(f)|set(i)|set(o))
rows=[(h,len(f[h]),len(i[h]),len(o[h]),len(rf[h])) for h in hours]
for r in rows: print(' ',r[0][5:], 'fills:',r[1],'intents:',r[2],'offered:',r[3],'real fills:',r[4])
print('desks with fills per hour: min',min(r[1] for r in rows),'median',statistics.median(r[1] for r in rows),'max',max(r[1] for r in rows))
print('hours with a real fill:',sum(1 for r in rows if r[4]>0),'of',len(rows))
