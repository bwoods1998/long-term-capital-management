"""C-10: what agents say about the game: complaints/design requests about rules, sizing, seats, fees, the bunt line, horizon, tools,
in journals, summaries, thoughts, library notes since 09-21. Keyword buckets with counts (rows, agents) and 3 quotes each."""
import sqlite3,json,collections,re
S='/tmp/claude-1000/-home-bwoods1998-Work/d98458ca-7959-468b-aee6-0082aa607bc1/scratchpad'
db=sqlite3.connect(f'file:{S}/snap/ledger.sqlite?mode=ro',uri=True)
B={
 'seat/league full':r'no seat|niche is full|league (is|was) full|waiting for (an eligible )?seat|displaced',
 'sizing/min order/cap':r'venue minimum|below the (venue )?minimum|\$1 (order|minimum)|\$10 (order|minimum|notional)|max_order|order cap|position cap|notional (is|was) too|too small to|position would be \d+%|gross exposure',
 'fees':r'taker fee|maker fee|fee(s)? (eat|exceed|kill|dominate|consume|are|is)|after[- ]fees|7% x p|1\.1%|0\.5%|fee drag',
 'bunt/stake/real sizing':r'bunt|stake (of|is|was)|\$10 stake|real[- ]money (size|stake)|swing',
 'horizon rule':r'horizon|max_hours_to_(close|resolve)|must resolve within|resolve in \d+ hours',
 'daily loss / freeze':r'daily loss|frozen until it reconciles|risk-reducing orders only|freeze',
 'replay/tape':r'replay (tape|coverage|window|gate)|tape (is )?(too )?(short|thin|sparse)|zero fills on|cannot replay|deflated sharpe|trial(s)? (budget|left|remaining)|wasted trial',
 'wake cadence/hours':r'wake_minutes|wake (me|cadence|every)|outside regular hours|premarket|market orders outside|session (open|close)|13:30|09:35|at the open',
 'credits/budget':r'credit(s)?|budget|cannot afford|\$0\.\d+ (left|remaining)|too expensive|merton (is|costs)',
 'missing tool/data':r'tool_request|request(ed)? (a|the) tool|runtime (lacks|does not)|not (yet )?(supported|implemented)|missing (data|feed|panel)|unavailable|point-in-time',
 'own-order crossing':r"against the house'?s own|one account cannot hold both|already holds or bids",
 'rules complaint (explicit)':r'(rule|policy|constitution|gate|guard|cap|limit)s? (is|are|was|were) (too|unreasonabl|arbitrar|wrong|inconsistent|blocking|preventing)|should (be )?(allow|permit|relax|raise|lower)|request(ing)? (that )?the house|ask(ing)? the house to|the house should|design (request|change)',
}
rows=[]
for kind,at,a,p in db.execute("select kind,at,agent,payload from ledger where at>='2026-09-21T00:00' and kind in ('agent.research','agent.thought','library.note','playbook.entry','agent.postmortem') order by seq"):
    p=json.loads(p)
    t=p.get('text') if kind!='agent.research' else (p.get('text') if p.get('tool')=='journal' else p.get('summary') if p.get('tool')=='summary' else None)
    if t: rows.append((kind,at,a,t))
print('texts:',len(rows))
for name,rx in B.items():
    r=re.compile(rx,re.I); hits=[x for x in rows if r.search(x[3])]
    ag=set(x[2] for x in hits)
    print(f'\n=== {name}: {len(hits)} texts, {len(ag)} agents, kinds={collections.Counter(x[0] for x in hits).most_common(3)}')
    # 3 quotes from distinct agents, newest
    q=0; seen=set()
    for kind,at,a,t in reversed(hits):
        if a in seen: continue
        seen.add(a); q+=1
        m=r.search(t); s=max(0,m.start()-160); print(f'   - {a} {at[5:16]} [{kind}]: ...{t[s:s+340].replace(chr(10)," ")}...')
        if q>=3: break
