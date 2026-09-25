"""Pick the served feature set: robustness of the free model to the recorder's quote cadence
and to history depth. Held-out AUC (chronological split, unseen events) with event bootstrap."""
import json
from collections import defaultdict

import numpy as np

from common import *

quotes, times, tasks = load()
first = first_labels(tasks)
CAT = lambda r: [float(r['cat'] == c) for c in CATNAMES]
S = [KI[k] for k in STATIC]
R2 = [k for k in RICH if k != 'npeer']
R3 = [k for k in R2 if k not in ('chg4', 'rng4', 'nhist')]
V = {
    'lab numeric (5)': lambda r: r['x'],
    'lab numeric + 8 Jev per state': lambda r: r['x'] + r['s'],
    'R1 rich(14) + category': lambda r: r['xc'] + [r['rich'][k] for k in RICH] + CAT(r),
    'R2 rich(13, no npeer) + category': lambda r: r['xc'] + [r['rich'][k] for k in R2] + CAT(r),
    'R3 time-window history only + category': lambda r: r['xc'] + [r['rich'][k] for k in R3] + CAT(r),
    'R2 + 6 static Jev (first label)': lambda r: r['xc'] + [r['rich'][k] for k in R2] + CAT(r) + [r['s1'][i] for i in S],
    'R2 + 8 Jev per state': lambda r: r['xc'] + [r['rich'][k] for k in R2] + CAT(r) + r['s'],
}

# history thinned to >=5-minute spacing per market (a sparser recorder)
thin = {}
for m, v in quotes.items():
    kept = []
    for q in v:
        if not kept or q[0] - kept[-1][0] >= 300:
            kept.append(q)
    thin[m] = kept
thin_t = {m: [q[0] for q in v] for m, v in thin.items()}

res = {}
for h in (300, 900, 3600):
    full = build(quotes, times, tasks, h, 'exec', first)
    train, test, cut = split(full)
    key = lambda r: (r['task']['rowid'], r['entry_t'])
    ytr = np.array([r['move'] for r in train], float); yts = np.array([r['move'] for r in test], float)
    idx = event_index(test)
    P = {}
    for k, fn in V.items():
        P[k] = fit(np.array([fn(r) for r in train]), ytr)[0](np.array([fn(r) for r in test]))
    # cadence / depth variants for R2: same rows (identical entry/outcome), different history
    for tag, kw in (('thin5', dict(hq=thin, ht=thin_t)), ('state4', dict(hlimit=4))):
        alt = {key(r): r for r in build(quotes, times, tasks, h, 'exec', first, **kw)}
        tr2 = [alt[key(r)] for r in train]; ts2 = [alt[key(r)] for r in test]
        fn = V['R2 rich(13, no npeer) + category']
        mdl_full = fit(np.array([fn(r) for r in train]), ytr)[0]
        P[f'R2 trained full, scored on {tag} history'] = mdl_full(np.array([fn(r) for r in ts2]))
        P[f'R2 trained and scored on {tag} history'] = fit(np.array([fn(r) for r in tr2]), ytr)[0](np.array([fn(r) for r in ts2]))
    ci, dci = boot_auc(idx, P, yts, ref='R2 rich(13, no npeer) + category', reps=300)
    res[str(h // 60)] = {k: dict(auc=auc(p, yts), ci=ci[k], d_vs_R2=dci[k], brier=float(np.mean((p - yts) ** 2))) for k, p in P.items()}
    print(f'h={h // 60} test={len(test)}')
    for k in P:
        v = res[str(h // 60)][k]
        print(f'   {k:50s} auc={v["auc"]:.4f} [{v["ci"][0]:.3f},{v["ci"][1]:.3f}] d_vs_R2=[{v["d_vs_R2"][0]:+.4f},{v["d_vs_R2"][1]:+.4f}] brier={v["brier"]:.5f}', flush=True)
json.dump(res, open(HERE + '/results/select_final.json', 'w'), indent=1)
