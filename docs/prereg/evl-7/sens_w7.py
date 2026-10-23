"""sens_w7.py: the sensitivity cells around W7's worst fresh cell (synthetic): its learner at D = 40 (the lens's own
columns) and D = 63 (EVL-LRN-ON's count), with the draft's after-replay-cost label in place of E7's gross label, and
PREREG-EVL-6's BASE model (symmetric days and events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect) at both
lags. Prints the W7_CELLS json for calib_w7.py's 'sens' grid."""
import json, sys
sys.path.insert(0, ".")
import calib_w7 as w
by = {}
for l in open("w7.fresh.jsonl"):
    r = json.loads(l); by.setdefault(r["cell"], []).append(r)
worst = max(by.items(), key=lambda kv: w.summarise(kv[1])["run1"])
w.grid("search")
spec = dict(worst[1][0]["spec"] or w.SPECS[worst[0]])
out = [dict(spec, extra=0), dict(spec, extra=23), dict(spec, gross=False)]
for lag in (1, 2):
    out.append(dict(shape="t3", phi=0.10, drift=0.0, lag=lag, pool=300, tau=0.0, skew=False, cnt=0.0, rho=0.05,
                    extra=17, null="N1", ic=0.0, T=120, gross=True))
print(json.dumps(out))
