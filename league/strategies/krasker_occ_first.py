import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEEDS={"venue":"alpaca","horizon":"day","style":"options-simple-breakout","asset_class":"option","symbols":["F","SOFI","AAL","T","RIVN","SNAP","CCL","VALE"],"bars":{"timeframe":"1Day","limit":70},"max_days_to_expiry":28,"wake_minutes":30,"parameter_rules":{"bounds":{"freshness_minutes":[1,60]}}}
PARAMS={"breakout_days":10,"min_move_pct":1.0,"trend_days":5,"min_days":5,"max_days":21,"target_delta":0.5,"max_spread_pct":15.0,"min_premium":0.1,"notional_usd":20.0,"max_open":1,"take_profit_pct":50.0,"stop_pct":30.0,"exit_days":2,"requote_minutes":30,"freshness_minutes":10}

def num(x,d=0.0):
    try:
        y=float(x)
        return y if math.isfinite(y) else d
    except (TypeError,ValueError):
        return d

def ts(x):
    try:
        z=datetime.fromisoformat(str(x).replace("Z","+00:00"))
        return (z if z.tzinfo else z.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        return None

def ny(x):
    z=ts(x)
    return z.astimezone(ZoneInfo("America/New_York")) if z else None

def fresh(x,now,minutes):
    z=ts(x)
    if z is None or now is None:return False
    age=(now-z).total_seconds()
    return -60<=age<=max(1,int(minutes))*60

def stamp(q):
    if not isinstance(q,dict):return None
    for k in ("as_of","timestamp","quote_timestamp","updated_at","t","time"):
        if q.get(k) is not None:return q[k]
    return None

def option_symbol(row):
    if not isinstance(row,dict):return ""
    return str(row.get("occ") or row.get("symbol") or "")

def closes(ctx,s):
    out=[]
    for b in (ctx.get("bars") or {}).get(s) or []:
        x=num(b.get("c"),-1) if isinstance(b,dict) else -1
        if x>0:out.append(x)
    return out

def days(x,now):
    try:return (datetime.strptime(str(x),"%Y-%m-%d").date()-now.date()).days
    except Exception:return None

def right_of(q):
    x=str(q.get("right") or q.get("type") or q.get("option_type") or "").lower()
    return "call" if x in ("call","c") else "put" if x in ("put","p") else ""

def pick(chain,s,right,now,p,budget,utc):
    choices=[]
    for q in chain:
        if not isinstance(q,dict) or str(q.get("underlying") or "")!=s or right_of(q)!=right:continue
        if not fresh(stamp(q),utc,p["freshness_minutes"]):continue
        bid=num(q.get("bid")); ask=num(q.get("ask")); d=days(q.get("expiry"),now)
        if d is None or d< p["min_days"] or d>p["max_days"] or bid<=0 or ask<=bid:continue
        mid=(bid+ask)/2
        if mid<=0 or 100*(ask-bid)/mid>p["max_spread_pct"] or mid<p["min_premium"] or ask*100>budget:continue
        delta=num(q.get("delta"),0)
        if right=="call" and not .30<=delta<=.75:continue
        if right=="put" and not -.75<=delta<=-.30:continue
        choices.append((100*(ask-bid)/mid,abs(abs(delta)-p["target_delta"]),d,q))
    choices.sort(key=lambda x:(x[0],x[1],x[2]))
    return choices[0][3] if choices else None

def decide(ctx):
    p=dict(PARAMS)
    for k,v in (ctx.get("params") or {}).items():
        if k in p:p[k]=num(v,p[k])
    utc=ts(ctx.get("now")); now=ny(ctx.get("now")); intents=[]; cancels=[]
    chain=[q for q in (ctx.get("chain") or []) if isinstance(q,dict)]
    bysym={option_symbol(q):q for q in chain if option_symbol(q)}
    for h in ctx.get("positions") or []:
        if not isinstance(h,dict):continue
        sym=option_symbol(h); q=bysym.get(sym)
        if not q or not fresh(stamp(q),utc,p["freshness_minutes"]):continue
        bid=num(q.get("bid")); cost=num(h.get("average_cost")); d=days(q.get("expiry"),now)
        if bid<=0 or cost<=0:continue
        change=bid/cost-1
        if change>=p["take_profit_pct"]/100 or change<=-p["stop_pct"]/100 or (d is not None and d<=p["exit_days"]):
            intents.append({"occ":sym,"side":"sell","quantity":max(1,int(num(h.get("quantity"),1))),"type":"limit","limit_price":round(bid,2),"reason":"Fresh option bid meets profit, loss or near-expiry exit rule."})
    for o in ctx.get("open_orders") or []:
        if isinstance(o,dict) and o.get("order_id") and utc and ts(o.get("submitted_at")) and (utc-ts(o.get("submitted_at"))).total_seconds()>p["requote_minutes"]*60:
            cancels.append(str(o["order_id"]))
    if now is None or now.weekday()>4 or not 570<=now.hour*60+now.minute<960:
        return {"intents":intents[:8],"cancels":cancels[:20],"thought":"Outside regular options hours; only fresh exits are allowed.","memory":{}}
    if ctx.get("positions") or ctx.get("open_orders"):
        return {"intents":intents[:8],"cancels":cancels[:20],"thought":"Existing exposure or order prevents a new entry.","memory":{}}
    lim=ctx.get("limits") or {}; rung=num(ctx.get("rung"),1); cap=75.0 if rung<=1 else 20.0
    budget=min(p["notional_usd"],cap,num(lim.get("max_order_usd"),cap),max(0,num(ctx.get("cash"))))
    for s in NEEDS["symbols"]:
        a=closes(ctx,s); n=max(2,int(p["breakout_days"])); t=max(2,int(p["trend_days"]))
        if len(a)<max(n,t)+1:continue
        quote=(ctx.get("quotes") or {}).get(s) or {}; qb=num(quote.get("bid")); qa=num(quote.get("ask"))
        if not fresh(stamp(quote),utc,p["freshness_minutes"]) or qb<=0 or qa<=qb:continue
        if (qa-qb)/((qa+qb)/2)>.02:continue
        prev=a[-n-1:-1]; last=a[-1]; move=100*(last/a[-2]-1)
        trend=sum(a[-t:])/t
        right="call" if last>max(prev) and last>trend and move>=p["min_move_pct"] else "put" if last<min(prev) and last<trend and move<=-p["min_move_pct"] else ""
        if not right:continue
        q=pick(chain,s,right,now,p,budget,utc)
        if q is None:continue
        ask=num(q.get("ask")); sym=option_symbol(q)
        if sym and ask>0 and ask*100<=budget:
            intents.append({"occ":sym,"side":"buy","quantity":1,"type":"limit","limit_price":round(ask,2),"reason":"Fresh underlying and option quotes show a confirmed 10-day directional breakout with a one-percent move and controlled spread."})
            break
    return {"intents":intents[:8],"cancels":cancels[:20],"thought":"The proposed candidate relaxes the prior volatility-scaled trigger while preserving freshness, affordability, spread, delta and expiry controls.","memory":{}}
