"""C-5: what agents ask for: tool.request (name, description, who), tool.blocked / tool.fulfilled outcomes, data.coverage by feed/status,
and asks inside research summaries/journals ('request', 'need', 'missing', 'unavailable')."""
import sqlite3,json,collections,re
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
print('=== tool.request by name (agents, desks, first/last)')
req=collections.defaultdict(lambda: {'agents':set(),'desks':collections.Counter(),'first':None,'last':None,'desc':''})
for at,a,p in db.execute("select at,agent,payload from ledger where kind='tool.request' order by seq"):
    p=json.loads(p); n=p.get('name'); r=req[n]; r['agents'].add(a); r['desks'][desk(a)]+=1; r['first']=r['first'] or at; r['last']=at; r['desc']=p.get('description','')
for n,r in sorted(req.items(),key=lambda x:-len(x[1]['agents'])):
    print(f"{len(r['agents']):3} agents {n:45} {dict(r['desks'])} {r['first'][5:16]}..{r['last'][5:16]}\n      {r['desc'][:260]}")
print('\n=== tool.blocked / tool.fulfilled: status, change, request name, outcome')
for kind in ('tool.blocked','tool.fulfilled'):
    c=collections.Counter()
    for at,a,p in db.execute("select at,agent,payload from ledger where kind=? order by seq",(kind,)):
        p=json.loads(p); rq=p.get('request'); rqn=rq.get('name') if isinstance(rq,dict) else str(rq)[:50]
        c[(p.get('status'),rqn,bool(p.get('change')))]+=1
    print(kind,len(c)); 
    for k,v in c.most_common(60): print('   ',v,k)
print('\n=== tool.blocked outcomes (why), first 120 chars each, grouped')
c=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='tool.blocked' order by seq"):
    p=json.loads(p); rq=p.get('request'); rqn=rq.get('name') if isinstance(rq,dict) else '?'
    c[(rqn,(p.get('outcome') or '')[:140])]+=1
for k,v in c.most_common(40): print('   ',v,k)
print('\n=== tool.fulfilled: request -> change (PR/branch)')
for at,a,p in db.execute("select at,agent,payload from ledger where kind='tool.fulfilled' order by seq"):
    p=json.loads(p); rq=p.get('request'); rqn=rq.get('name') if isinstance(rq,dict) else '?'
    print('   ',at[5:16],p.get('status'),rqn,'->',p.get('change'),'|',(p.get('outcome') or '')[:100])
print('\n=== data.coverage by feed/status/asset (latest per feed)')
last={}
for at,a,p in db.execute("select at,agent,payload from ledger where kind='data.coverage' order by seq"):
    p=json.loads(p); last[(p.get('feed'),p.get('asset'))]=(at,p.get('status'),p.get('cadence'),p.get('source'),p.get('start'),p.get('end'),len(p.get('keys') or []),p.get('point_in_time'))
for k,v in sorted(last.items(),key=lambda x:str(x)): print('   ',k,v)
print('\n=== asks inside research summaries and journals since 09-22 (phrases)')
pat=re.compile(r'(request(ed|ing)? (a |the |an )?([a-z_\- ]{3,60}?)(tool|feed|panel|data|calendar|chain|book|tape|coverage)|(missing|unavailable|no|lacks?|without) (a |the |an )?(point-in-time |historical |intraday |live |real-time )?([a-z_\-/ ]{3,50}?)(feed|panel|data|calendar|chain|order ?book|depth|tape|coverage|history|bars|quotes|snapshots?|api|scoreboard|odds|forecast|observations?))',re.I)
c=collections.Counter(); who=collections.defaultdict(set)
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.research' and at>='2026-09-22T00:00' and (payload like '%\"tool\":\"summary\"%' or payload like '%\"tool\":\"journal\"%')"):
    p=json.loads(p); t=(p.get('summary') or p.get('text') or '')
    for m in pat.finditer(t):
        k=re.sub(r'\s+',' ',m.group(0).lower())[:70]; c[k]+=1; who[k].add(a)
for k,v in c.most_common(60): print(f'   {v:3} {len(who[k]):3} agents  {k}')
