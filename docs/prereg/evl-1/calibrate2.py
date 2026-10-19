import calibrate_looks as C
lo, hi = 0.005, 0.05
for _ in range(8):
    mid = (lo + hi) / 2
    fp = C.run(mid, reps=3000, rate_mu=40.0)
    lo, hi = (mid, hi) if fp <= 0.095 else (lo, mid)
alpha = round(lo, 4)
print({"alpha_look": alpha, "fp": {mu: C.run(alpha, reps=5000, rate_mu=mu) for mu in (1.0, 6.0, 40.0, 150.0)}})
