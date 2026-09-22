# Upper bound: perfect-foresight direction on the same executable test rows, after the spread.
import numpy as np, evaluate as E
q,t,tasks=E.load()
for h in (300,900,3600):
    rows=E.build(q,t,tasks,h,'exec')
    t0,t1=min(r['entry_t'] for r in rows),max(r['entry_t'] for r in rows); split=t0+0.6*(t1-t0)
    seen={r['event'] for r in rows if r['outcome_t']<split}
    te=[r for r in rows if r['entry_t']>=split and r['event'] not in seen]
    best=np.array([max(r['fbid']-r['ask'], r['bid']-r['fask']) for r in te])
    print(f'h={h//60}min test={len(te)} oracle: profitable-after-spread share={np.mean(best>0):.3f} mean best pnl/contract={best.mean():+.4f} mean if traded only when profitable={best[best>0].mean() if (best>0).any() else 0:+.4f}')
