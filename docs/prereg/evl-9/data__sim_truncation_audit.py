"""SYNTHETIC ONLY. The build's TRUNCATION-INVARIANCE AUDIT (an outcome-free leak test): for a sample of candidates,
every feature is recomputed from a copy of the canonical tables CUT at the candidate's decision (rows knowable before
tau, bar sessions before D, each record in the version that existed at tau) and must equal the full build's value. A
feature that reads anything knowable at or after tau differs on some candidates. This script plants four leaks into a
toy feature builder and measures how often a 2,000-candidate audit catches each, and the clean builder's false-alarm
rate. No real data and no label are read."""
import bisect, json, random
R = random.Random(20261022)
NE, DAYS = 400, 300
# toy tables: events (entity, knowable minute, value, edited value + edit minute), daily closes with splits
events = []
for e in range(NE):
    t = 0
    while True:
        t += int(R.expovariate(1 / (60 * 24 * 3)))          # an event every ~3 days
        if t >= DAYS * 1440: break
        edit = t + int(R.expovariate(1 / 30)) if R.random() < 0.3 else None   # 30% edited, ~30 min later
        events.append((e, t, R.randint(20, 120), (R.randint(20, 120) if edit else None), edit))
by_e = {}
for ev in events: by_e.setdefault(ev[0], []).append(ev)
for v in by_e.values(): v.sort(key=lambda x: x[1])
closes, factor = {}, {}
for e in range(NE):
    c, f, row, frow = 50.0, 1.0, [], []
    for d in range(DAYS):
        c *= 1 + 0.02 * R.gauss(0, 1)
        if R.random() < 0.002: c /= 2; f *= 2              # a 2:1 split on day d
        row.append(c); frow.append(f)
    closes[e] = row; factor[e] = frow                     # raw close and the cumulative split count
def adj_close(e, d, asof_day):
    """'all'-adjusted close of day d as a vendor serving on asof_day would give it (later splits rescale)."""
    return closes[e][d] * factor[e][d] / factor[e][min(asof_day, DAYS - 1)]
def feats(e, tau, leak=None, cut=False):
    """tau in minutes; D = the day of tau. cut=True: only what existed at tau."""
    D = tau // 1440
    lo = tau - 7 * 1440
    evs = by_e.get(e, [])
    n = sum(1 for x in evs if lo <= x[1] < tau) if leak != "boundary" else sum(1 for x in evs if lo <= x[1] <= tau + 5)
    last = [x for x in evs if x[1] < tau]
    if last:
        x = last[-1]
        if cut: hl = x[2] if (x[4] is None or x[4] >= tau) else x[3]
        elif leak == "latest_version": hl = x[3] if x[3] is not None else x[2]
        else: hl = x[2] if (x[4] is None or x[4] >= tau) else x[3]
    else: hl = 0
    asof = D if cut else DAYS - 1                        # the full build's vendor data is fetched today
    if leak == "adjusted_level": lvl = round(adj_close(e, D - 1, asof), 6)
    else: lvl = round(closes[e][D - 1], 6)               # levels from RAW closes
    r5 = round(adj_close(e, D - 1, asof) / adj_close(e, D - 6, asof), 9)   # ratios from adjusted closes: safe
    if leak == "window_end": r5 = round(adj_close(e, D, asof) / adj_close(e, D - 5, asof), 9)
    return (n, hl, lvl, r5)
def audit(leak, n=2000):
    bad = 0
    for _ in range(n):
        e = R.randrange(NE); tau = R.randrange(10 * 1440, (DAYS - 2) * 1440)
        if feats(e, tau, leak) != feats(e, tau, None, cut=True):
            bad += 1
    return bad
out = {}
for leak in (None, "boundary", "latest_version", "adjusted_level", "window_end"):
    rates = [audit(leak, 20000) for _ in range(3)]
    out[str(leak)] = {"mismatching_of_20000": rates, "caught_in_all_3_audits": all(r > 0 for r in rates)}
json.dump(out, open("sim_truncation_audit.out.json", "w"), indent=1)
print(json.dumps(out, indent=1))
