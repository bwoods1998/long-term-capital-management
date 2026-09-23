"""C-15: what became of each tool.request: join tool.blocked/tool.fulfilled payload.request (ledger id) to tool.request rows (name, agent, desk);
per request name: requests, blocked, fulfilled(answered / change), open. Plus data.coverage latest per feed."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
req={}
for id_,at,a,p in db.execute("select id,at,agent,payload from ledger where kind='tool.request' order by seq"):
    p=json.loads(p); req[id_]=(p.get('name'),a,desk(a),at)
print('requests:',len(req),'ids look like:',list(req)[:2])
out=collections.defaultdict(lambda: collections.Counter()); change=collections.defaultdict(list)
for kind,at,a,p in db.execute("select kind,at,agent,payload from ledger where kind in ('tool.blocked','tool.fulfilled') order by seq"):
    p=json.loads(p); rid=p.get('request'); name=req.get(rid,('<unknown:'+str(rid)[:12],))[0]
    st=p.get('status') or ('fulfilled' if kind=='tool.fulfilled' else 'blocked')
    out[name][(kind,st,bool(p.get('change')))]+=1
    if p.get('change'): change[name].append((at[5:16],p.get('change'),(p.get('outcome') or '')[:160]))
# topic grouping
def topic(n):
    n=(n or '').lower()
    for k,ws in [('sports live score/game state',['score','game_state','match_state','in_game','lineup','live_sports']),('earnings calendar/panel',['earning']),('attention underlying value',['attention','underlier','underlying_value','current_value']),('perp funding/OI',['funding','perp','open_inter','positioning']),('crypto spot/vol next to Kalshi ladder',['spot','vol','underlier','strike_tape','15m']),('sports price-vs-outcome history / in-season tape',['outcome','history','tape','replay','season']),('alt spreads/universe/backfill',['alt','spread','backfill','universe']),('replay engine (bars/clock/diagnostics)',['1hour','aggregation','clock','diagnostic','killed']),('commodity fixings',['fixing','wti','gasoline','lbma'])]:
        if any(w in n for w in ws): return k
    return 'other'
byt=collections.defaultdict(lambda:{'req':0,'agents':set(),'desks':collections.Counter(),'blocked':0,'answered':0,'change':0,'none':0})
for rid,(n,a,d,at) in req.items():
    t=topic(n); b=byt[t]; b['req']+=1; b['agents'].add(a); b['desks'][d]+=1
    o=out.get(n,{})
    b['blocked']+=sum(v for k,v in o.items() if k[0]=='tool.blocked'); b['answered']+=sum(v for k,v in o.items() if k[0]=='tool.fulfilled' and k[1]=='answered'); b['change']+=sum(v for k,v in o.items() if k[2]); b['none']+= 0 if o else 1
print('\n=== by topic: requests, distinct agents, desks | blocked, answered(no change), with a change, no record at all')
for t,b in sorted(byt.items(),key=lambda x:-len(x[1]['agents'])):
    print(f"  {t:48} req={b['req']:3} agents={len(b['agents']):3} {dict(b['desks'])} | blocked={b['blocked']} answered={b['answered']} change={b['change']} no-record={b['none']}")
print('\n=== requests that produced a change (PR/branch)')
for n,ch in change.items():
    for c in ch: print('  ',n,c)
print('\n=== fulfilled status values:',collections.Counter(k[1] for o in out.values() for k in o if k[0]=='tool.fulfilled'))
print('\n=== data.coverage latest per (feed, asset): status, cadence, start..end, keys, point_in_time')
last={}
for at,a,p in db.execute("select at,agent,payload from ledger where kind='data.coverage' order by seq"):
    p=json.loads(p); last[(p.get('feed'),p.get('asset'))]=(at[5:16],p.get('status'),p.get('cadence'),str(p.get('start'))[:10],str(p.get('end'))[:13],len(p.get('keys') or []),p.get('point_in_time'),str(p.get('source'))[:60])
for k,v in sorted(last.items(),key=lambda x:str(x)): print('  ',k,v)
