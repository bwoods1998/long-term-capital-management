import json, sys
import calibrate_events as C
ns = json.loads(sys.argv[1])
lo, hi = 0.005, 0.06
for _ in range(9):
    mid = (lo + hi) / 2
    fp = max(C.run(mid, reps=1500, rate_mu=mu, ns=ns, seed=11)[0] for mu in (6.0, 40.0))
    lo, hi = (mid, hi) if fp <= 0.095 else (lo, mid)
alpha = round(lo, 4)
fps = {mu: C.run(alpha, reps=4000, rate_mu=mu, ns=ns, seed=12)[0] for mu in (1.0, 6.0, 40.0, 150.0)}
power = {f"{mu}@{e}": C.run(alpha, reps=1500, rate_mu=mu, edge=e, ns=ns, seed=13) for mu in (6.0, 40.0) for e in (0.002, 0.004, 0.008)}
print(json.dumps({"ns": ns, "alpha_look": alpha, "fp": fps, "power": power}))
