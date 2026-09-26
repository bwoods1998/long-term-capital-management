"""C-7: (a) the Sept 22 wake gap: ledger rows and wakes per hour 09-22T05..15 with ops.started/deploy/alert; (b) agent.inactive reasons by desk;
(c) per Kalshi desk, hour-of-day: wakes and mean markets offered (last 48h); (d) Kalshi series prefix x hour-of-day of book.order (all time, both books)
to show which series are live around the clock; (e) shard mapping from code/ledger."""
import sqlite3,json,collections,re
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
print('=== (a) rows and wakes per hour 09-22T04..16')
for h,n,w in db.execute("select substr(at,1,13),count(*),sum(kind='agent.woke') from ledger where at>='2026-09-22T04' and at<'2026-09-22T16' group by 1"): print('  ',h,n,w)
for kind,at,a,p in db.execute("select kind,at,agent,payload from ledger where kind in ('ops.started','ops.deploy') and at>='2026-09-22T03' and at<'2026-09-22T16' order by seq"): print('  ',kind,at,a,p[:160])
print('  alerts in window:')
for kind,at,a,p in db.execute("select kind,at,agent,payload from ledger where kind='ops.alert' and at>='2026-09-22T06' and at<'2026-09-22T15' order by seq limit 25"): print('  ',at[5:16],p[:200])
print('\n=== (b) agent.inactive reasons by desk (all time) and inactive spells > 3h ending in the last 48h')
c=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.inactive'"):
    p=json.loads(p); c[(desk(a),p.get('reason'))]+=1
for k,v in sorted(c.items(),key=lambda x:-x[1]): print('  ',v,k)
print('\n=== (c) Kalshi desks by hour of day: wakes, mean offered per wake, share of wakes with offered>0 (last 48h)')
h=collections.defaultdict(lambda: collections.defaultdict(lambda:[0,0,0]))
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.woke' and at>='2026-09-21T16:28'"):
    d=desk(a); p=json.loads(p); x=h[d][at[11:13]]; x[0]+=1; x[1]+=p.get('offered',0) or 0; x[2]+= 1 if (p.get('offered',0) or 0)>0 else 0
for d in ['kalshi-crypto-strikes','kalshi-crypto-15m','kalshi-weather','kalshi-sports','kalshi-sports-props','kalshi-prices','kalshi-attention','alpaca-crypto-majors','alpaca-crypto-alts','alpaca-index-etfs','alpaca-megacaps','alpaca-options']:
    print(f'  {d:22}',' '.join(f"{k}:{v[0]}/{(v[1]/v[0]):.0f}" for k,v in sorted(h[d].items())))
print('\n=== (d) Kalshi book.order by series prefix x hour-of-day (all time, all Kalshi books); rows = orders')
c=collections.defaultdict(collections.Counter)
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.order' and (payload like '%\"book\":\"kalshi%' or payload like '%\"book\": \"kalshi%')"):
    p=json.loads(p); m=(p.get('instrument') or {}).get('market_id') or ''
    ser=m.split('-')[0]; c[ser][at[11:13]]+=1
for ser,cn in sorted(c.items(),key=lambda x:-sum(x[1].values()))[:30]:
    hours=sorted(cn); print(f'  {ser:22} n={sum(cn.values()):4} hours-with-orders={len(hours):2} ',''.join('#' if f'{k:02d}' in cn else '.' for k in range(24)))
print('\n=== (d2) kalshi fills (venue) by series prefix and hour-of-day (all time, both kalshi books)')
c=collections.defaultdict(collections.Counter)
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill' and (payload like '%\"book\":\"kalshi%' or payload like '%\"book\": \"kalshi%')"):
    p=json.loads(p)
    if p.get('source')!='venue': continue
    m=((p.get('instrument') or {}).get('market_id') or ''); ser=m.split('-')[0]; c[ser][at[11:13]]+=1
for ser,cn in sorted(c.items(),key=lambda x:-sum(x[1].values()))[:25]:
    print(f'  {ser:22} n={sum(cn.values()):4} ',''.join('#' if f'{k:02d}' in cn else '.' for k in range(24)))
