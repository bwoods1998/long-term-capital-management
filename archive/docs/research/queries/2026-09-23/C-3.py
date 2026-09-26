"""C-3: the stock and option desks: today's session (2026-09-23 13:30Z to the 16:28Z snapshot, after fixes #189/#190 at 15:30Z)
vs Sept 22 13:30Z-Sept 23 14:00Z. Wakes, offered, intents, orders, fills, refusals; practice and real."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
def run(T0,T1,label):
    print('=====',label,T0,'->',T1)
    c=collections.defaultdict(collections.Counter); agents=collections.defaultdict(set); intenders=collections.defaultdict(set)
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.woke' and at>=? and at<?",(T0,T1)):
        d=DESK.get(a.split('-')[0]); 
        if not d: continue
        p=json.loads(p); b='real' if p.get('book') in ('alpaca','kalshi') else 'practice'
        c[(d,b)]['wakes']+=1; agents[d].add(a)
        if p.get('ok'): c[(d,b)]['ok']+=1
        else: c[(d,b)]['err']+=1
        if p.get('offered',0)>0: c[(d,b)]['offered_wakes']+=1
        if p.get('shut'): c[(d,b)]['shut_flag']+=1
        c[(d,b)]['intents_in_wake']+=p.get('intents',0)
        c[(d,b)]['dropped']+=len(p.get('dropped') or [])
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.intent' and at>=? and at<?",(T0,T1)):
        d=DESK.get(a.split('-')[0])
        if not d: continue
        p=json.loads(p); b='real' if p.get('book') in ('alpaca','kalshi') else 'practice'; c[(d,b)]['intents']+=1; intenders[d].add(a)
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.order' and at>=? and at<?",(T0,T1)):
        p=json.loads(p); b='real' if p.get('real_money') else 'practice'
        for sh in p.get('shares') or []:
            d=DESK.get(sh.get('agent','').split('-')[0])
            if d: c[(d,b)]['orders']+=1; c[(d,b)]['orders_'+str(p.get('status'))]+=1
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill' and at>=? and at<?",(T0,T1)):
        p=json.loads(p); d=DESK.get(a.split('-')[0])
        if d and p.get('source') in ('venue','cross'):
            b='real' if p.get('real_money') else 'practice'; c[(d,b)]['fills']+=1; c[(d,b)]['fill_qty_usd']+=round(float(p.get('quantity') or 0)*float(p.get('price') or 0)*float((p.get('instrument') or {}).get('multiplier') or 1),2)
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.refused' and at>=? and at<?",(T0,T1)):
        d=DESK.get(a.split('-')[0])
        if not d: continue
        p=json.loads(p); b='real' if p.get('book') in ('alpaca','kalshi') else 'practice'; c[(d,b)]['refused']+=1
        for r in p.get('reasons') or []: c[(d,b)]['R:'+r[:60]]+=1
    for k in sorted(c): print(k, 'agents=',len(agents[k[0]]),'intenders=',len(intenders[k[0]]), dict(c[k]))
    # dropped reasons + wake errors
    dr=collections.Counter(); er=collections.Counter()
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.woke' and at>=? and at<?",(T0,T1)):
        d=DESK.get(a.split('-')[0])
        if not d: continue
        p=json.loads(p)
        for x in p.get('dropped') or []: dr[(d,str(x)[:90])]+=1
        if not p.get('ok'): er[(d,str(p.get('error'))[:90])]+=1
    print('dropped:',dr.most_common(8)); print('errors:',er.most_common(8))
run('2026-09-22T13:30','2026-09-23T14:00','yesterday session window (plan baseline)')
run('2026-09-23T13:30','2026-09-23T16:29','today 13:30Z to snapshot')
run('2026-09-23T15:30','2026-09-23T16:29','today after #189/#190 (15:30Z) to snapshot')
# intents by option desk detail today
print('=== today intents on stock/option desks')
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.intent' and at>='2026-09-23T13:30' and (agent like 'scholes%' or agent like 'mcentee%' or agent like 'krasker%') order by seq"):
    p=json.loads(p); i=p.get('instrument') or {}
    print(at[11:19],a,p.get('book'),p.get('side'),i.get('symbol'),i.get('asset_class'),p.get('order_type'),p.get('limit_price'),p.get('quantity'),(p.get('reason') or '')[:70])
