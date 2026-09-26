"""C-4: why research sessions abstain. From agent.research tool=summary rows (candidate, trials, reason, summary text) since
2026-09-22T00:00, classified by keyword into no-idea / no-data / missing-tool / closed-market / budget / rules / candidate-deferred / other,
by desk and rung (rung from eval.verdict promote/demote/seat/eligible to_rung at the time). Also research.gate skip reasons by desk."""
import sqlite3,json,collections,re
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
DESK={'hilibrand':'kalshi-crypto-strikes','huang':'kalshi-crypto-15m','mullins':'kalshi-weather','meriwether':'kalshi-sports','hufschmid':'kalshi-sports-props','hawkins':'kalshi-prices','leahy':'kalshi-attention','rosenfeld':'alpaca-crypto-majors','haghani':'alpaca-crypto-alts','scholes':'alpaca-index-etfs','mcentee':'alpaca-megacaps','krasker':'alpaca-options'}
desk=lambda a: DESK.get(a.split('-')[0],'?')
moves=collections.defaultdict(list)
for a,at,p in db.execute("select agent,at,payload from ledger where kind='eval.verdict' order by seq"):
    p=json.loads(p)
    if p.get('decision') in ('promote','demote','seat','eligible') and p.get('to_rung') is not None: moves[a].append((at,int(p['to_rung'])))
def rung(a,at):
    r=0
    for t,x in moves.get(a,[]):
        if t<=at: r=x
    return r
CATS=[('no-data',r'no (historical|replay|tape|point-in-time|earnings|option[- ]chain|order ?book|depth|funding|settlement|underlying|spot|price|data|coverage|feed|bars|weather|forecast|scoreboard|injury|lineup|odds|calendar)|missing (data|panel|feed|tape|coverage|input)|tape (is )?(too )?(short|thin|empty|sparse)|coverage (is )?(zero|empty|missing|absent|lacking)|unavailable|not available|lacks|no coverage|insufficient (event )?history|zero fills on|cannot replay|does not (cover|include)|not covered'),
      ('missing-tool',r'tool[_ ]request|request(ed)? (a|the) tool|needs? a (new )?tool|toolsmith|no tool|missing tool|not supported|unsupported|cannot (be )?express|the runtime (lacks|does not)|runtime_status'),
      ('closed-market',r'market(s)? (is|are|was|were) (closed|shut|dark)|session (is )?(closed|shut)|outside (the )?(regular )?session|weekend|no live markets|nothing (is )?live|no markets? (open|listed|live)|off-season|dark'),
      ('budget',r'credit(s)?( are| is)? (low|exhausted|gone|thin)|no credits|out of credits|cannot afford|budget|conserve|save (my|the) (trial|credit)|hold (my|the) (replay )?(budget|trial)|spend(ing)? no|not worth spending|bank(ed)? (the|my)|preserve (the|my) (remaining )?trial|last trial|trials? (left|remaining)'),
      ('rules',r'horizon|max_hours_to_(close|resolve)|must resolve within|rung|bunt|seat|niche is full|league (is|was) full|position cap|order cap|min(imum)? (order|notional|quantity)|post-only|maker[- ]only|deflated sharpe|(the )?bar (of|at)|qualification|policy|constitution|not (allowed|permitted)|refus|forbid'),
      ('no-idea',r'no (new |better |distinct |untested |remaining |viable |credible |falsifiable )?(idea|hypothesis|hypotheses|edge|change|variant)|nothing (new|distinct|left) to (test|try|propose)|exhausted (the )?(idea|hypothes|variant|parameter)|already (been )?(tested|tried|measured)|redundant|duplicate|same (idea|hypothesis)|null result|measured null|no edge|negative evidence|evidence is (weak|negative|thin)|dead|does not work|structurally'),
      ('waiting-forward',r'(let|allow|wait for|accumulate|accrue|await|watch) (the |my |more )?(forward|paper|live|barren|blocks|fills|trades|record|evidence|settlement|session)|forward (test|record|paper)|paper (test|record|evidence)|more (blocks|trades|fills|data|sessions)|too (early|few)|sample (is )?(too )?small|until'),
]
def classify(t):
    t=t.lower(); hits=[k for k,rx in CATS if re.search(rx,t)]
    return hits
rows=[]
for at,a,p in db.execute("select at,agent,payload from ledger where kind='agent.research' and at>='2026-09-22T00:00' and payload like '%\"tool\":\"summary\"%' order by seq"):
    p=json.loads(p)
    if p.get('tool')!='summary': continue
    rows.append((at,a,desk(a),rung(a,at),p))
print('summary rows since 09-22:',len(rows))
c=collections.Counter((p.get('reason'),bool(p.get('candidate')),int(p.get('trials') or 0)>0) for *_,p in rows)
print('by (reason, candidate, ran trials):',c.most_common())
abst=[r for r in rows if not r[4].get('candidate') and int(r[4].get('trials') or 0)==0]
print('abstained (no candidate, no trials):',len(abst),'of',len(rows),'=',round(100*len(abst)/max(1,len(rows)),1),'%')
print('\n=== abstention share by desk (abstained/all summaries)')
bd=collections.defaultdict(lambda:[0,0])
for r in rows:
    bd[r[2]][1]+=1
    if not r[4].get('candidate') and int(r[4].get('trials') or 0)==0: bd[r[2]][0]+=1
for d,(x,n) in sorted(bd.items(),key=lambda x:-x[1][1]): print(f'{d:22} {x:4}/{n:4} {100*x/n:5.1f}%')
print('\n=== abstention share by rung')
br=collections.defaultdict(lambda:[0,0])
for r in rows:
    br[r[3]][1]+=1
    if not r[4].get('candidate') and int(r[4].get('trials') or 0)==0: br[r[3]][0]+=1
for d,(x,n) in sorted(br.items()): print(f'rung {d} {x:4}/{n:4} {100*x/n:5.1f}%')
print('\n=== keyword classes among abstentions (multi-label; first-hit primary)')
prim=collections.Counter(); multi=collections.Counter(); byd=collections.defaultdict(collections.Counter); byr=collections.defaultdict(collections.Counter)
for at,a,d,r,p in abst:
    h=classify(p.get('summary') or '')
    pr=h[0] if h else 'other'
    prim[pr]+=1; byd[d][pr]+=1; byr[r][pr]+=1
    for x in h: multi[x]+=1
n=len(abst)
print('primary:',[(k,v,f'{100*v/n:.0f}%') for k,v in prim.most_common()])
print('any-mention:',[(k,v,f'{100*v/n:.0f}%') for k,v in multi.most_common()])
print('by desk (primary):')
for d in byd: print(f'  {d:22}',byd[d].most_common(4))
print('by rung (primary):')
for r in sorted(byr): print(f'  rung {r}',byr[r].most_common(5))
print('\n=== research.gate decisions since 09-22 by desk (skip reasons collapsed)')
g=collections.defaultdict(collections.Counter)
for at,a,p in db.execute("select at,agent,payload from ledger where kind='research.gate' and at>='2026-09-22T00:00'"):
    p=json.loads(p); r=p.get('reason') or ''
    r=re.sub(r'backoff:\d+','backoff',r); g[desk(a)][(p.get('decision'),r)]+=1
tot=collections.Counter()
for d in g:
    for k,v in g[d].items(): tot[k]+=v
print('all:',tot.most_common())
for d in g: print(f'  {d:22}',g[d].most_common(5))
# dump abstention texts sample for reading: one per desk x rung, up to 40
print('\n=== sample abstention summaries (desk,rung,agent,at): ')
seen=collections.Counter()
for at,a,d,r,p in abst[::-1]:
    if seen[(d,r)]>=2: continue
    seen[(d,r)]+=1
    print(f'-- {d} r{r} {a} {at[5:16]} ${p.get("cost_usd")} cls={classify(p.get("summary") or "")}\n   ',(p.get('summary') or '').replace('\n',' ')[:520])
