import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS={"venue":"alpaca","horizon":"day","style":"options-short-trend","asset_class":"option","symbols":["F","SOFI","T","AAL","RIVN","SNAP","CCL","VALE"],"bars":{"timeframe":"1Day","limit":40},"max_days_to_expiry":30,"wake_minutes":30}
PARAMS={"trend_days":5,"exit_mean_days":5,"min_days":3,"max_days":30,"target_delta":0.55,"max_spread_pct":15.0,"min_premium":0.10,"notional_usd":20.0,"max_open":2,"take_profit_pct":40.0,"stop_pct":35.0,"exit_days":2,"requote_minutes":30,"rv_window":20,"max_iv_rv":1.6,"max_chase_sigma":2.5,"max_chase_floor":0.02,"rsi_entry":30.0,"rsi_high":70.0}

def num(x,d=0.0):
    try:
        y=float(x)
        return y if math.isfinite(y) else d
    except (TypeError,ValueError):
        return d

def dt(x):
    try:
        z=str(x).replace("Z","+00:00")
        a=datetime.fromisoformat(z)
        if a.tzinfo is None: a=a.replace(tzinfo=timezone.utc)
        return a.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None

def occ(x):
    return str(x.get("occ") or x.get("symbol") or "") if isinstance(x,dict) else ""

def expiry(s):
    s=str(s).upper()
    for i in range(6,len(s)):
        if s[i] in "CP" and s[i-6:i].isdigit():
            q=s[i-6:i]
            return "20%s-%s-%s"%(q[:2],q[2:4],q[4:6])
    return None

def fresh(r,now):
    q=dt(r.get("as_of"))
    return q is not None and now is not None and 0 <= (now-q).total_seconds() <= 36*3600

def closes(ctx,symbol):
    out=[]
    for b in (ctx.get("bars") or {}).get(symbol) or []:
        if isinstance(b,dict):
            c=num(b.get("c"))
            if c>0: out.append(c)
    return out

def choose(rows,symbol,leg,now,p,budget):
    best=None
    for r in rows:
        if not isinstance(r,dict) or r.get("underlying")!=symbol or r.get("right")!=leg or not fresh(r,now): continue
        e=dt(str(r.get("expiry"))+"T16:00:00-04:00")
        if e is None: continue
        days=(e.date()-now.date()).days
        bid,ask=num(r.get("bid")),num(r.get("ask"))
        if not (0<bid<ask) or days<p["min_days"] or days>p["max_days"]: continue
        mid=(bid+ask)/2.0
        if mid<=0 or 100*(ask-bid)/mid>p["max_spread_pct"] or mid<p["min_premium"] or 100*ask>budget: continue
        delta=num(r.get("delta"),0.0)
        if delta==0: continue
        score=(abs(abs(delta)-p["target_delta"]),days,100*(ask-bid)/mid)
        if best is None or score<best[0]: best=(score,r,ask,days)
    return best

def decide(ctx):
    p=dict(PARAMS)
    for k,v in (ctx.get("params") or {}).items():
        if k in p: p[k]=num(v,p[k])
    memory=dict(ctx.get("memory") or {})
    memory["wakes"]=int(memory.get("wakes",0))+1
    now=dt(ctx.get("now"))
    positions=[x for x in ctx.get("positions") or [] if isinstance(x,dict) and num(x.get("quantity"))>0]
    orders=ctx.get("open_orders") or []
    working={occ(x) for x in orders if isinstance(x,dict)}
    bids={occ(x):num(x.get("bid")) for x in ctx.get("chain") or [] if isinstance(x,dict) and fresh(x,now) and num(x.get("bid"))>0}
    intents=[]
    for pos in positions:
        s=occ(pos)
        if not s or s in working: continue
        cost,mark=num(pos.get("average_cost")),num(pos.get("mark"))
        change=mark/cost-1 if cost>0 else 0
        ex=pos.get("expiry") or expiry(s)
        e=dt(str(ex)+"T16:00:00-04:00") if ex else None
        dte=(e.date()-now.date()).days if e and now else 999
        if change>=p["take_profit_pct"]/100 or change<=-p["stop_pct"]/100 or dte<=p["exit_days"]:
            bid=bids.get(s,0)
            if bid>0:
                intents.append({"occ":s,"side":"sell","quantity":int(num(pos.get("quantity"))),"type":"limit","limit_price":round(max(0.01,bid),2),"reason":"Fresh positive bid for profit, loss, or expiry-proximity exit."})
    if now is None or now.weekday()>=5 or now.hour*60+now.minute<585 or now.hour*60+now.minute>=930:
        return {"intents":intents[:8],"cancels":[],"thought":"Outside the option session; managing exits only.","memory":memory}
    lim=ctx.get("limits") or {}
    cash=num(ctx.get("cash"),0.0)
    budget=min(p["notional_usd"],num(lim.get("max_order_usd"),20.0),num(lim.get("max_position_usd"),100.0),cash*0.95)
    busy={occ(x) for x in positions}|working
    slots=max(0,int(p["max_open"])-len(busy))
    rows=[x for x in ctx.get("chain") or [] if isinstance(x,dict)]
    for symbol in NEEDS["symbols"]:
        if slots<=0: break
        c=closes(ctx,symbol)
        n=max(2,int(p["trend_days"]))
        if len(c)<n+1: continue
        recent=c[-1]-c[-2]
        base=c[-n-1]
        leg="call" if recent>0 and c[-1]>base else ("put" if recent<0 and c[-1]<base else "")
        if not leg: continue
        found=choose(rows,symbol,leg,now,p,budget)
        if found is None: continue
        _,row,ask,days=found
        s=occ(row)
        if not s or s in busy: continue
        intents.append({"occ":s,"side":"buy","quantity":1,"type":"limit","limit_price":round(ask,2),"post_only":False,"reason":"Recent daily close confirms a %d-day directional trend; fresh OPRA ask and bounded premium selected."%n})
        busy.add(s); slots-=1
    memory["positions"]=len(positions)
    return {"intents":intents[:8],"cancels":[],"thought":"Testing a shorter directional trend to produce measurable paper entries while retaining fresh-quote and spread controls.","memory":memory}
