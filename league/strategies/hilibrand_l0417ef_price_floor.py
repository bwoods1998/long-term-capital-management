import math,statistics
NEEDS={'venue':'kalshi','horizon':'hour','style':'spot-priced-binary-maker','series':['KXBTCD','KXETHD'],'max_hours_to_close':5,'wake_minutes':5,'bars':{'timeframe':'5Min','limit':180},'observe':{'symbols':['BTC/USD','ETH/USD']},'parameter_rules':{'bounds':{'edge_min':[0.02,0.12],'min_hours':[0.15,1.0],'max_hours':[1,5],'max_spread':[0.01,0.05],'notional_usd':[1,20]}}}
PARAMS = {'edge_min': 0.06, 'max_hours': 4, 'max_spread': 0.03, 'min_hours': 0.343, 'notional_usd': 6}
def decide(ctx):
 p={**PARAMS,**(ctx.get('params') or {})}; mapping={'KXBTCD':'BTC/USD','KXETHD':'ETH/USD'}; bars=ctx.get('observed',{}).get('bars',{}); busy={x.get('market') for x in ctx.get('positions',[])+ctx.get('open_orders',[])}; best=None
 entry_floor=0.30 if ctx.get('rung',0)>=2 else 0.15
 for m in ctx.get('markets',[]):
  s=mapping.get(m.get('series')); h=m.get('hours_to_resolve',m.get('hours_to_close')); rows=bars.get(s,[]) if s else []; k=m.get('strike'); yb=m.get('yes_bid'); ya=m.get('yes_ask')
  if not s or m.get('market') in busy or h is None or not p['min_hours']<=h<=p['max_hours'] or not k or yb is None or ya is None or ya-yb>p['max_spread']:continue
  c=[r.get('c') for r in rows[-120:] if r.get('c',0)>0]
  if len(c)<40:continue
  r=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]; sigma=max(.18,statistics.stdev(r)*math.sqrt(12*8760)); z=math.log(c[-1]/k)/(sigma*math.sqrt(h/8760)); py=.5*(1+math.erf(z/math.sqrt(2)))
  for leg,prob,bid,ask in [('yes',py,yb,ya),('no',1-py,1-ya,1-yb)]:
   price=round(bid,2)
   if entry_floor<=price<ask and prob-price>=p['edge_min'] and (best is None or prob-price>best[0]):best=(prob-price,m['market'],leg,price)
 intents=[]
 if best:
  edge,t,leg,price=best; lim=ctx.get('limits',{}); risk=ctx.get('event_risk',{}).get('remaining_by_market_usd',{}).get(t,lim.get('max_order_usd',10)); q=int(min(p['notional_usd'],lim.get('max_order_usd',10),lim.get('max_position_usd',10),risk,max(0,ctx.get('cash',0))*.9)/price)
  if q and q*price>=1:intents=[{'market':t,'leg':leg,'side':'buy','quantity':q,'type':'limit','limit_price':price,'post_only':True,'reason':'Conservative spot/strike binary estimate clears the non-crossing maker bid by the configured edge.'}]
 return {'intents':intents,'cancels':[],'thought':'Price both binary legs from spot distance and remaining time; enter only on modeled value above a bid meeting the entry-price floor.','memory':{}}
