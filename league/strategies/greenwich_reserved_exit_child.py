NEEDS = {"venue":"kalshi","horizon":"hour","style":"cross-market-confirmed-reversal","series":["KXNFLWINMARGIN","KXNFLOT","KXNFLPASSATT","KXNFLPASSINT","KXDJI","KXCOPPERW","KXTRUEV"],"max_hours_to_close":12,"wake_minutes":5,"parameter_rules":{"bounds":{"move_min":[0.03,0.2],"confirm_min":[0.01,0.12],"risk_share":[0.005,0.04]}}}
PARAMS = {'confirm_min': 0.02876, 'move_min': 0.117033, 'risk_share': 0.017712}
def decide(ctx):
    p=ctx.get('params',PARAMS); mem=ctx.get('memory',{}).get('h',{}); hist={}; out=[]; rows=ctx.get('markets',[])
    mids={m.get('market',''):(float(m.get('yes_bid') or 0)+float(m.get('yes_ask') or 1))/2 for m in rows}
    groups={}
    for m in rows:
        s=str(m.get('series','')); groups.setdefault(s,[]).append(m)
    held={x.get('market'):x for x in ctx.get('positions',[])}; pending={x.get('market') for x in ctx.get('open_orders',[]) if x.get('side')=='buy'}
    reserved_sells={}
    for order in ctx.get('open_orders',[]):
        if order.get('side')=='sell':
            key=(order.get('market'),order.get('leg'))
            remaining=max(0.0,float(order.get('quantity') or 0)-float(order.get('filled') or 0))
            reserved_sells[key]=reserved_sells.get(key,0.0)+remaining
    for m in rows:
        t=m.get('market',''); b=float(m.get('yes_bid') or 0); a=float(m.get('yes_ask') or 1); mid=mids[t]; old=mem.get(t,[]); hist[t]=(old+[mid])[-4:]
        close=float(m.get('hours_to_close') or 99); res=float(m.get('hours_to_resolve') or 99)
        if t in held:
            x=held[t]; leg=x.get('leg'); bid=b if leg=='yes' else 1-a; cost=float(x.get('average_cost') or 0)
            if bid>0 and (bid>=cost+0.06 or bid<=cost-0.09 or close<0.3):
                key=(t,leg)
                q=int(max(0.0,float(x.get('quantity') or 0)-reserved_sells.get(key,0.0)))
                if q:
                    out.append({'market':t,'leg':leg,'side':'sell','quantity':q,'type':'limit','limit_price':round(bid,2),'reason':'Take profit, limit loss, or exit near close.'})
                    reserved_sells[key]=reserved_sells.get(key,0.0)+q
            continue
        if len(old)<3 or t in pending or not (1<=res<=12) or close<0.5 or float(m.get('volume_24h') or 0)<60 or a-b>0.08: continue
        move=old[-1]-old[-2]; retrace=mid-old[-1]
        if abs(move)<float(p.get('move_min',0.07)) or move*retrace>=0 or abs(retrace)<0.01: continue
        peers=[]
        for z in groups.get(str(m.get('series','')),[]):
            zt=z.get('market','')
            if zt!=t and zt in mem and len(mem[zt])>=2: peers.append(mids.get(zt,0)-mem[zt][-1])
        if not peers or sum(1 for d in peers if d*move<0)/len(peers)<0.5: continue
        if abs(sum(peers)/len(peers))<float(p.get('confirm_min',0.025)): continue
        leg='no' if move>0 else 'yes'; bid=1-a if leg=='no' else b; ask=1-b if leg=='no' else a; price=round(min(ask-0.01,bid+0.01),2)
        if price<0.30 or price>=ask: continue
        cap=min(float(ctx.get('cash') or 0)*float(p.get('risk_share',0.015)),float(ctx.get('limits',{}).get('max_order_usd') or 0),float(ctx.get('limits',{}).get('max_position_usd') or 0)); q=int(cap/(price+0.07*price*(1-price)))
        if q: out.append({'market':t,'leg':leg,'side':'buy','quantity':q,'type':'limit','limit_price':price,'post_only':True,'reason':'A quote retraced after a large move, with same-series markets corroborating the reversal.'})
    return {'intents':out[:8],'cancels':[],'thought':'Require a stalled move and corroboration from other observed markets before placing a passive entry. Exit only contracts not already committed to same-leg sells.','memory':{'h':hist}}
