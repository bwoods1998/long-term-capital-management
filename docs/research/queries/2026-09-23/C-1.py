"""C-1: L5 coverage table, hour (UTC) x desk, last 48 h of the 16:28Z snapshot.
Desk = agent name prefix (verified == agent.born specialty). Per hour/desk: wakes, ok wakes, wakes with offered>0,
sum offered, intents (agent.intent rows), orders (book.order shares), fills (book.fill source=venue/cross, by ledger agent col),
refusals (book.refused), living members. Class: trades > refused > offered-no-intent > nothing offered > no agents."""
import sqlite3,json,collections,datetime,sys
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options','greenwich':'kalshi-open','london':'alpaca-open'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
T0='2026-09-21T16:28'; T1='2026-09-23T16:29'
H=lambda at: at[:13]
c=collections.defaultdict(lambda: collections.Counter())
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.woke' and at>=? and at<?",(T0,T1)):
    p=json.loads(p); k=(H(at),desk(a)); c[k]['wakes']+=1
    if p.get('ok'): c[k]['ok']+=1
    if p.get('offered',0)>0: c[k]['offered_wakes']+=1; c[k]['offered_sum']+=p['offered']
    c[k]['intents_w']+=p.get('intents',0)
    if p.get('barren'): c[k]['barren']+=1
    if p.get('shut'): c[k]['shut']+=1
    if p.get('book','').endswith('paper') or p.get('book','')=='kalshi-shadow': c[k]['wake_practice']+=1
    else: c[k]['wake_real']+=1
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.intent' and at>=? and at<?",(T0,T1)):
    p=json.loads(p); k=(H(at),desk(a)); c[k]['intents']+=1
    if p.get('book') in ('alpaca','kalshi'): c[k]['intents_real']+=1
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.order' and at>=? and at<?",(T0,T1)):
    p=json.loads(p)
    for sh in p.get('shares') or []:
        k=(H(at),desk(sh.get('agent','?'))); c[k]['orders']+=1
        if p.get('real_money'): c[k]['orders_real']+=1
fa=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill' and at>=? and at<?",(T0,T1)):
    p=json.loads(p); fa[(a=='house',p.get('source'))]+=1
    if p.get('source') in ('venue','cross'):
        ag=a if a!='house' else (p.get('agent') or ((p.get('shares') or [{}])[0].get('agent')) or 'house')
        k=(H(at),desk(ag)); c[k]['fills']+=1
        if p.get('real_money'): c[k]['fills_real']+=1
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.refused' and at>=? and at<?",(T0,T1)):
    k=(H(at),desk(a)); c[k]['refused']+=1
print('fill attribution check (agent col is house?, source):',dict(fa))
# living members per desk per hour
born={};died={}
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.born'"): born[a]=at
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.died'"): died[a]=at
hours=[]
t=datetime.datetime(2026,9,21,17); 
while t<=datetime.datetime(2026,9,23,16): hours.append(t.strftime('%Y-%m-%dT%H')); t+=datetime.timedelta(hours=1)
desks=['kalshi-crypto-strikes','kalshi-crypto-15m','kalshi-weather','kalshi-sports','kalshi-sports-props','kalshi-prices','kalshi-attention','alpaca-crypto-majors','alpaca-crypto-alts','alpaca-index-etfs','alpaca-megacaps','alpaca-options','kalshi-open','alpaca-open']
def alive(d,h):
    n=0
    for a,b in born.items():
        if desk(a)==d and b[:13]<=h and (a not in died or died[a][:13]>=h): n+=1
    return n
def cls(d,h):
    x=c.get((h,d),{})
    if x.get('fills',0)>0: return 'T'
    if x.get('refused',0)>0 and x.get('intents',0)>0: return 'R'
    if x.get('intents',0)>0: return 'I'   # intents but no fill/refusal (resting orders)
    if x.get('offered_wakes',0)>0: return 'O'  # offered, no intent
    if x.get('wakes',0)>0: return 'N'   # woke, nothing offered
    if alive(d,h)==0: return '-'    # no agents
    return 'Z'  # agents alive but no wake this hour
abbr={'kalshi-crypto-strikes':'Kstrk','kalshi-crypto-15m':'K15m','kalshi-weather':'Kwx','kalshi-sports':'Kspt','kalshi-sports-props':'Kprop','kalshi-prices':'Kprc','kalshi-attention':'Katt','alpaca-crypto-majors':'Amaj','alpaca-crypto-alts':'Aalt','alpaca-index-etfs':'Aetf','alpaca-megacaps':'Amega','alpaca-options':'Aopt','kalshi-open':'Kopen','alpaca-open':'Aopen'}
print('legend: T=fills R=refused(no fill) I=intent only(no fill) O=offered-no-intent N=woke,nothing offered Z=agents alive,no wake -=no agents')
print('hour(UTC)        '+' '.join(f'{abbr[d]:>5}' for d in desks))
tot=collections.Counter()
for h in hours:
    row=[cls(d,h) for d in desks]
    for d,r in zip(desks,row): tot[(d,r)]+=1
    print(h[5:13]+'    '+' '.join(f'{r:>5}' for r in row))
print('\n=== per desk: hours by class (of',len(hours),')')
for d in desks:
    print(f'{d:22}',{r:tot[(d,r)] for r in 'TRIONZ-' if tot[(d,r)]})
print('\n=== per desk totals last 48h')
for d in desks:
    s=collections.Counter()
    for (h,dd),x in c.items():
        if dd==d: s.update(x)
    print(f'{d:22}',dict(s))
print('\n=== uncovered hours (no desk with fills or intents) and which desks were offered')
for h in hours:
    row={d:cls(d,h) for d in desks}
    if not any(r in 'TRI' for r in row.values()):
        print(h, {d:r for d,r in row.items() if r in 'ON'})
print('\n=== per hour-of-day (UTC), all 48h: desks with fills / intents / offered-no-intent')
hod=collections.defaultdict(collections.Counter)
for h in hours:
    for d in desks:
        r=cls(d,h); hod[h[11:13]][r]+=1
for k in sorted(hod): print(k, dict(hod[k]))
