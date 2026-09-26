from datetime import datetime
from zoneinfo import ZoneInfo

NEEDS = {"venue":"alpaca","horizon":"day","style":"short-horizon-cross-asset-trend-rotation","symbols":["BTC/USD","ETH/USD","SPY","QQQ","GLD","XLE"],"bars":{"timeframe":"1Hour","limit":160},"wake_minutes":60}
PARAMS = {}


def _stock_entry_hours(now):
    # Necessary clock window only; the House still enforces the venue calendar.
    try:
        stamp = datetime.fromisoformat(now.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            return False
        local = stamp.astimezone(ZoneInfo("America/New_York"))
        minute = local.hour * 60 + local.minute
        return local.weekday() < 5 and 570 <= minute < 960
    except (TypeError, ValueError, AttributeError):
        return False


def decide(ctx):
    bars=ctx.get("bars",{})
    symbols=NEEDS["symbols"]
    scores=[]
    for s in symbols:
        rows=bars.get(s,[])
        if len(rows)<30: continue
        c=[]
        for x in rows:
            try: c.append(float(x.get("c",0)))
            except: c.append(0.0)
        if min(c[-25:])<=0: continue
        r24=c[-1]/c[-25]-1.0
        r6=c[-1]/c[-7]-1.0
        scores.append((r24,r6,s))
    scores.sort(reverse=True)
    leader=scores[0] if scores else None
    intents=[]
    positions=ctx.get("positions",[])
    held_symbols={p.get("symbol") for p in positions}
    for p in positions:
        s=p.get("symbol")
        rows=bars.get(s,[])
        score=next((x for x in scores if x[2]==s),None)
        if rows:
            bid=float(ctx.get("quotes",{}).get(s,{}).get("bid") or rows[-1].get("c",0) or 0)
            cost=float(p.get("average_cost") or bid or 0)
            drawdown=(bid/cost-1.0) if bid>0 and cost>0 else 0.0
            rotate=bool(leader and leader[2]!=s and leader[0]>((score[0] if score else -1.0)+0.01))
            weakening=bool(score and (score[0]<-0.002 or score[1]<-0.004))
            if drawdown<=-0.04 or rotate or weakening:
                intents.append({"symbol":s,"side":"sell","quantity":float(p.get("quantity",0)),"type":"market","reason":"Exit on a 4% loss, weakening 24h/6h trend, or a clearly stronger cross-asset leader."})
    pending={o.get("symbol") for o in ctx.get("open_orders",[]) if o.get("side")=="buy"}
    if not positions and not pending and leader and leader[0]>=0.003 and leader[1]>0.0:
        s=leader[2]
        limits=ctx.get("limits",{})
        cash=float(ctx.get("cash",0) or 0)
        equity=float(ctx.get("equity",0) or 0)
        size=min(float(limits.get("max_order_usd",0) or 0),float(limits.get("max_position_usd",0) or 0),cash*0.30,equity*0.30)
        entry_hours = s.endswith("/USD") or _stock_entry_hours(ctx.get("now", ""))
        if size>=10 and entry_hours:
            intents.append({"symbol":s,"side":"buy","notional_usd":round(size,2),"type":"market","reason":"Enter the strongest asset only when 24h momentum is positive and the 6h trend confirms."})
    return {"intents":intents,"cancels":[],"thought":"Short-horizon rotation with stock entries restricted to New York weekday session hours; ranking, crypto entries and exits are unchanged.","memory":ctx.get("memory",{})}
