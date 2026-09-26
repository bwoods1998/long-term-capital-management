"""C-6: latest alloc.board (band, stake, W_paper, W_real, E, trades, real_trades) + realized by agent from book.fill
(practice vs real, venue/cross fills, ledger agent col), + fill attribution check, + W_real over time for real agents."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
at,p=db.execute("select at,payload from ledger where kind='alloc.board' order by seq desc limit 1").fetchone()
b=json.loads(p); ag=b['agents']
print('board at',at,'throttle',b.get('throttle'),'envelope',b.get('envelope'))
print('bands:',collections.Counter(v[0] for v in ag.values()))
rows=[(a,v) for a,v in ag.items() if len(v)>=7]
rows.sort(key=lambda x:-x[1][4])
print('\n=== top 12 by E (band, stake, W_paper, W_real, E, trades, real_trades)')
for a,v in rows[:12]: print('  ',a,v)
print('=== bottom 10 by E'); 
for a,v in rows[-10:]: print('  ',a,v)
print('=== agents with real trades'); 
for a,v in rows:
    if v[6]: print('  ',a,v)
print('=== never traded:',sum(1 for a,v in rows if v[5]==0 and v[6]==0),'of',len(rows))
# realized by agent (book.fill payload 'realized'?) check keys of a venue fill
r=db.execute("select at,agent,payload from ledger where kind='book.fill' and payload like '%\"source\": \"venue\"%' order by seq desc limit 1").fetchone()
print('\nvenue fill sample:',r[0],r[1],r[2][:900])
c=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill'"):
    p=json.loads(p); c[(p.get('source'),a=='house',p.get('book'))]+=1
print('fill (source, agent==house, book):',sorted(c.items(),key=lambda x:-x[1]))
