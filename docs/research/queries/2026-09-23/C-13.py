"""C-13: agent.inactive reason=missing_data / provider_failure / paused: detail text grouped by desk (what data is missing), last 48h."""
import sqlite3,json,collections,re
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
for reason in ('missing_data','provider_failure','paused','order_rejected'):
    c=collections.Counter(); ag=collections.defaultdict(set)
    for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.inactive' and at>='2026-09-21T16:28' order by seq"):
        p=json.loads(p)
        if p.get('reason')!=reason: continue
        d=re.sub(r'\d{4}-\d\d-\d\dT[\d:.]+Z?','<t>',(p.get('detail') or '')); d=re.sub(r'\b\d+(\.\d+)?\b','N',d)[:150]
        c[(desk(a),d)]+=1; ag[(desk(a),d)].add(a)
    print(f'=== {reason}: {sum(c.values())} rows')
    for k,v in c.most_common(14): print(f'   {v:3} {len(ag[k]):2}ag {k[0]:22} {k[1]}')
