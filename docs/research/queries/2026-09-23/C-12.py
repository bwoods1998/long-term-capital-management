"""C-12: Kalshi realized P&L per agent from book.settle (real and shadow), Alpaca from book.fill realized; House exits separated by
the fill 'reason'/'entry_reason' text ('closing this account'); joined to the latest board and to each agent's stated edge (agent.strategy reason / born reason)."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
r=db.execute("select at,agent,payload from ledger where kind='book.settle' order by seq desc limit 1").fetchone()
print('settle sample:',r[0],r[1],r[2][:600])
p=json.loads(r[2]); print('keys:',list(p.keys()))
# aggregate
settle=collections.defaultdict(lambda: collections.defaultdict(float)); nset=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.settle'"):
    p=json.loads(p); book=p.get('book'); nset[(a,book)]+=1
    for k,v in p.items():
        if k in ('realized','pnl','profit','payout','cost','fee_usd','cash_delta') :
            try: settle[(a,book)][k]+=float(v)
            except: pass
print('\n=== book.settle totals by (agent, book) sorted by realized/pnl')
def val(d): return d.get('realized', d.get('pnl', d.get('cash_delta',0.0)))
for (a,book),d in sorted(settle.items(),key=lambda x:-val(x[1])):
    if nset[(a,book)]>=1: print(f'  {a:22} {book:14} n={nset[(a,book)]:3} ',{k:round(v,2) for k,v in d.items()})
# alpaca fills realized split: agent exits vs House "closing this account"
print('\n=== Alpaca fills: realized by (book) split by House-close vs agent exit (reason text)')
c=collections.defaultdict(lambda:[0.0,0])
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill' and (payload like '%\"book\":\"alpaca%')"):
    p=json.loads(p)
    if p.get('source') not in ('venue','cross'): continue
    rz=float(p.get('realized') or 0); house='House-close' if 'closing this account' in (p.get('reason') or '') else 'agent'
    c[(p.get('book'),house)][0]+=rz; c[(p.get('book'),house)][1]+=1
for k,v in sorted(c.items()): print('  ',k,'realized=',round(v[0],2),'fills=',v[1])
print('\n=== Kalshi settle by book split by whether the agent was dead at settlement (House wind-down)')
died={a:at for at,a in db.execute("select at,agent from ledger where kind='agent.died'")}
c=collections.defaultdict(lambda:[0.0,0])
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.settle'"):
    p=json.loads(p); dead = a in died and died[a]<at
    c[(p.get('book'),'dead-agent(House)' if dead else 'living')][0]+=float(p.get('realized') or p.get('pnl') or p.get('cash_delta') or 0); c[(p.get('book'),'dead-agent(House)' if dead else 'living')][1]+=1
for k,v in sorted(c.items()): print('  ',k,'realized=',round(v[0],2),'n=',v[1])
