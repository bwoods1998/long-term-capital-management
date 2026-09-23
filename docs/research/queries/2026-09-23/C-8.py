"""C-8: winners and losers: realized P&L by agent from book.fill (venue+cross; the ledger agent column names the agent; House rows excluded),
practice vs real, plus the latest board (W_paper, W_real, E), plus what each says its edge is (latest journal / summary / playbook)."""
import sqlite3,json,collections
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
r=db.execute("select at,agent,payload from ledger where kind='book.fill' and agent!='house' and payload like '%venue%' order by seq desc limit 1").fetchone()
print('venue fill sample keys:',r[1],list(json.loads(r[2]).keys())); print(r[2][:700])
real=collections.defaultdict(lambda:[0.0,0,0.0]); prac=collections.defaultdict(lambda:[0.0,0,0.0]); house=collections.Counter()
for at,a,p in db.execute("select at,agent,payload from ledger where kind='book.fill'"):
    p=json.loads(p)
    if p.get('source') not in ('venue','cross'): continue
    rz=float(p.get('realized') or 0); fee=float(p.get('fee_usd') or 0)
    if a=='house': house[(p.get('book'),p.get('source'))]+=1; continue
    t=real if p.get('real_money') else prac
    t[a][0]+=rz; t[a][1]+=1; t[a][2]+=fee
print('house-attributed venue/cross fills:',dict(house))
at,p=db.execute("select at,payload from ledger where kind='alloc.board' order by seq desc limit 1").fetchone(); board=json.loads(p)['agents']
def last_words(a):
    out={}
    for kind,tool in (('agent.research','journal'),('agent.research','summary'),('playbook.entry',None)):
        q="select at,payload from ledger where kind=? and agent=? order by seq desc limit 40"
        for at2,p2 in db.execute(q,(kind,a)):
            p2=json.loads(p2)
            if tool and p2.get('tool')!=tool: continue
            out[tool or kind]=(at2[5:16],(p2.get('text') or p2.get('summary') or '').replace('\n',' ')[:420]); break
    return out
print('\n=== REAL realized by agent (sum realized, fills, fees) with board [band,stake,Wp,Wr,E,trades,real_trades]')
for a,(rz,n,fee) in sorted(real.items(),key=lambda x:-x[1][0]): print(f'  {a:22} realized={rz:+8.2f} fills={n:3} fees={fee:6.2f} board={board.get(a)}')
print('\n=== PRACTICE realized: top 12 and bottom 12 (agents alive on board marked *)')
items=sorted(prac.items(),key=lambda x:-x[1][0])
for a,(rz,n,fee) in items[:12]+[('...',(0,0,0))]+items[-12:]: print(f'  {"*" if a in board else " "}{a:22} realized={rz:+8.2f} fills={n:3} fees={fee:6.2f} board={board.get(a)}')
print('\n=== what the winners/losers say (latest journal / summary / playbook)')
for a in ['mullins-2','mullins-6','huang-h51fdd3-2','huang-h427345','haghani-37','meriwether-h2d625d']+[x[0] for x in items[:4]]+[x[0] for x in items[-4:]]:
    print(f'-- {a} real={real.get(a)} prac={prac.get(a)} board={board.get(a)}')
    for k,v in last_words(a).items(): print(f'     [{k} {v[0]}] {v[1]}')
