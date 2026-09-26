"""C-11: (a) whole-ledger scan: hours with ledger rows but zero agent.woke (House up, nobody waking), and the kinds written in the
Sept 22 07:35-14:11Z hole; (b) inactive spells: agent.inactive rows -> resumed at next agent.woke of that agent; who is inactive at the
snapshot end by desk and reason; agent-hours inactive in the last 48h by reason."""
import sqlite3,json,collections,datetime
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
T=lambda s: datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
print('=== (a) hours with rows but 0 wakes, whole ledger')
gap=[]
for h,n,w in db.execute("select substr(at,1,13),count(*),sum(kind='agent.woke') from ledger group by 1"):
    if w==0: gap.append((h,n))
print(len(gap),'hours:',gap)
print('kinds in 09-22T08..14:',db.execute("select kind,count(*) from ledger where at>='2026-09-22T08' and at<'2026-09-22T14' group by kind order by 2 desc limit 12").fetchall())
print('last wake before hole / first after:',db.execute("select max(at) from ledger where kind='agent.woke' and at<'2026-09-22T08'").fetchone(),db.execute("select min(at) from ledger where kind='agent.woke' and at>'2026-09-22T08'").fetchone())
print('ops.alert/ops.job in hole (sample):',[(r[0][11:16],r[1][:120]) for r in db.execute("select at,payload from ledger where kind in ('ops.alert') and at>='2026-09-22T07:30' and at<'2026-09-22T14:15' order by seq limit 8")])
print('ops.job kinds in hole:',db.execute("select substr(payload,1,60),count(*) from ledger where kind='ops.job' and at>='2026-09-22T08' and at<'2026-09-22T14' group by 1 order by 2 desc limit 6").fetchall())
# (b) inactive spells
print('\n=== (b) inactive spells')
wakes=collections.defaultdict(list)
for at,a in db.execute("select at,agent from ledger where kind='agent.woke' order by seq"): wakes[a].append(at)
died={a:at for at,a in db.execute("select at,agent from ledger where kind='agent.died'")}
import bisect
END='2026-09-23T16:28:30Z'
spells=[]
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.inactive' order by seq"):
    p=json.loads(p); ws=wakes.get(a,[]); i=bisect.bisect_right(ws,at); resume=ws[i] if i<len(ws) else None
    end=resume or died.get(a) or END
    spells.append((a,desk(a),p.get('reason'),at,end,resume is not None,(T(end)-T(at)).total_seconds()/3600))
print('spells:',len(spells),'resumed by a wake:',sum(1 for s in spells if s[5]))
byr=collections.defaultdict(lambda:[0,0.0])
for s in spells: byr[s[2]][0]+=1; byr[s[2]][1]+=s[6]
print('by reason (count, total hours, median h):')
for r,(n,h) in sorted(byr.items(),key=lambda x:-x[1][1]):
    hs=sorted(s[6] for s in spells if s[2]==r); print(f'   {str(r):18} n={n:4} hours={h:8.1f} median={hs[len(hs)//2]:.1f}')
# agent-hours inactive in last 48h by reason and desk
W0=T('2026-09-21T16:28:00Z'); W1=T(END)
ah=collections.defaultdict(float); ad=collections.defaultdict(float)
for a,d,r,st,en,res,h in spells:
    s=max(T(st),W0); e=min(T(en),W1)
    if e>s: ah[r]+=(e-s).total_seconds()/3600; ad[d]+=(e-s).total_seconds()/3600
print('agent-hours inactive in last 48h by reason:',{k:round(v,1) for k,v in sorted(ah.items(),key=lambda x:-x[1])})
print('by desk:',{k:round(v,1) for k,v in sorted(ad.items(),key=lambda x:-x[1])})
# living agent-hours in window for the denominator
born={a:at for at,a in db.execute("select at,agent from ledger where kind='agent.born'")}
tot=0.0
for a,b in born.items():
    s=max(T(b),W0); e=min(T(died.get(a,END)),W1)
    if e>s: tot+=(e-s).total_seconds()/3600
print('living agent-hours in window:',round(tot,1),' inactive share:',round(100*sum(ah.values())/tot,1),'%')
print('\n=== inactive at snapshot end (no wake after the inactive row, agent alive)')
cur=collections.Counter(); ex=collections.defaultdict(list)
for a,d,r,st,en,res,h in spells:
    if not res and a not in died: cur[(d,r)]+=1; ex[(d,r)].append((a,st[5:16],round(h,1)))
alive=[a for a in born if a not in died]
print('alive:',len(alive),' inactive now:',sum(cur.values()))
for k,v in sorted(cur.items(),key=lambda x:-x[1]): print('  ',v,k,ex[k][:4])
