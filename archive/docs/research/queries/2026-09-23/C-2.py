"""C-2: refusal reasons by desk and hour-of-day, last 48 h; plus every 'shard' mention in refusals, orders and alerts."""
import sqlite3,json,collections,re
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
T0='2026-09-21T16:28'
def norm(r):
    r=re.sub(r'\$[0-9.]+','$X',r); r=re.sub(r'\b\d+(\.\d+)?\b','N',r); return r[:110]
byd=collections.defaultdict(collections.Counter); byh=collections.defaultdict(collections.Counter); bybook=collections.Counter()
n=0
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.refused' and at>=?",(T0,)):
    p=json.loads(p); n+=1; bybook[(p.get('book'),desk(a))]+=1
    for r in p.get('reasons') or []:
        byd[desk(a)][norm(r)]+=1; byh[at[11:13]][norm(r)]+=1
print('refusals last 48h:',n); print('by (book,desk):',sorted(bybook.items(),key=lambda x:-x[1]))
print('\n=== reasons by desk')
for d,cn in byd.items():
    print(d, sum(cn.values()))
    for r,k in cn.most_common(8): print('    ',k,r)
print('\n=== top reasons by hour of day (UTC)')
for h in sorted(byh):
    print(h, sum(byh[h].values()), byh[h].most_common(3))
print('\n=== shard mentions (any kind, any time)')
c=collections.Counter(); ex={}
for kind,at,a,p in db.execute("select kind,at,agent,payload from ledger where payload like '%shard%'"):
    c[kind]+=1
    if kind not in ex: ex[kind]=(at,a,p[:400])
for k,v in c.items(): print(k,v,ex[k])
print('\n=== insufficient_shard_balance rows by day')
c=collections.Counter()
for kind,at,a,p in db.execute("select kind,at,agent,payload from ledger where payload like '%insufficient_shard_balance%'"):
    c[(kind,at[:10],desk(a) if a!='house' else 'house')]+=1
for k,v in sorted(c.items()): print(k,v)
