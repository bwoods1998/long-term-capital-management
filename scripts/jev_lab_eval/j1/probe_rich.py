"""Sanity checks on the rich free features: drop-one / add-one importance, fresh-only test rows,
per-feature univariate AUC (train and test), and leave-series-out generalisation of Jev static answers."""
import json
import numpy as np
from common import *

quotes, times, tasks = load()
first = first_labels(tasks)
S = [KI[k] for k in STATIC]; Q = [KI[k] for k in QUOTE]
CAT = lambda r: [float(r['cat'] == c) for c in CATNAMES]
out = {}
for h in (900, 3600):
    rows = build(quotes, times, tasks, h, 'exec', first)
    train, test, cut = split(rows)
    ytr = np.array([r['move'] for r in train], float); yts = np.array([r['move'] for r in test], float)
    names = ['mid', 'spread', 'log_oi', 'hours48', 'drift4'] + RICH
    M = lambda rs: np.array([r['xc'] + [r['rich'][k] for k in RICH] + CAT(r) for r in rs])
    Xtr, Xts = M(train), M(test)
    nb = len(names)
    full = auc(fit(Xtr, ytr)[0](Xts), yts)
    print(f'\nh={h // 60} rich+category full test AUC={full:.4f}')
    print('  univariate test AUC (sign-free: max(a,1-a)) and drop-one / add-one-to-lab-numeric AUC:')
    base5 = list(range(5))
    a5 = auc(fit(Xtr[:, base5], ytr)[0](Xts[:, base5]), yts)
    for j, n in enumerate(names):
        u = auc(Xts[:, j], yts); u = max(u, 1 - u)
        keep = [i for i in range(Xtr.shape[1]) if i != j]
        d = auc(fit(Xtr[:, keep], ytr)[0](Xts[:, keep]), yts) - full
        add = auc(fit(Xtr[:, base5 + ([j] if j >= 5 else [])], ytr)[0](Xts[:, base5 + ([j] if j >= 5 else [])]), yts) - a5
        print(f'   {n:9s} univ={u:.3f} drop={d:+.4f} add_to_lab5={add:+.4f}')
    # fresh-only test rows (live rows are fresh)
    fr = np.array([r['fresh'] for r in test])
    for nm, fn in [('lab numeric', lambda r: r['x']), ('lab numeric + 8 Jev', lambda r: r['x'] + r['s']),
                   ('rich+category', lambda r: r['xc'] + [r['rich'][k] for k in RICH] + CAT(r)),
                   ('rich+category+8 Jev', lambda r: r['xc'] + [r['rich'][k] for k in RICH] + CAT(r) + r['s'])]:
        p = fit(np.array([fn(r) for r in train]), ytr)[0](np.array([fn(r) for r in test]))
        print(f'  fresh-only test ({fr.sum()} rows) {nm:22s} auc={auc(p[fr], yts[fr]):.4f}  stale-only={auc(p[~fr], yts[~fr]):.4f}')
    # leave-series-out: chronological train rows from other series, test rows (unseen events) from held-out series
    series = sorted({r['series'] for r in rows})
    rng = np.random.default_rng(3)
    perm = list(rng.permutation(series))
    folds = [perm[i::5] for i in range(5)]
    arms = {
        'rich+category': lambda r: r['xc'] + [r['rich'][k] for k in RICH] + CAT(r),
        'rich+category+6 static first': lambda r: r['xc'] + [r['rich'][k] for k in RICH] + CAT(r) + [r['s1'][i] for i in S],
        'rich+category+8 Jev per state': lambda r: r['xc'] + [r['rich'][k] for k in RICH] + CAT(r) + r['s'],
        'lab numeric+category': lambda r: r['x'] + CAT(r),
        'lab numeric+6 static first': lambda r: r['x'] + [r['s1'][i] for i in S],
        'lab numeric+8 Jev per state': lambda r: r['x'] + r['s'],
    }
    P = {k: np.full(len(test), np.nan) for k in arms}
    tser = np.array([r['series'] for r in test])
    for fs in folds:
        fs = set(fs)
        tr = [r for r in train if r['series'] not in fs]
        ti = np.where(np.isin(tser, list(fs)))[0]
        if len(ti) == 0:
            continue
        ytr2 = np.array([r['move'] for r in tr], float)
        for k, fn in arms.items():
            P[k][ti] = fit(np.array([fn(r) for r in tr]), ytr2)[0](np.array([fn(test[i]) for i in ti]))
    ok = ~np.isnan(P['rich+category'])
    idx = event_index([test[i] for i in np.where(ok)[0]])
    ci, dci = boot_auc(idx, {k: v[ok] for k, v in P.items()}, yts[ok], ref='rich+category', reps=200)
    print(f'  leave-series-out (5 folds of series; {ok.sum()} test rows):')
    for k in arms:
        print(f'   {k:32s} auc={auc(P[k][ok], yts[ok]):.4f} [{ci[k][0]:.3f},{ci[k][1]:.3f}] d_vs_rich+cat=[{dci[k][0]:+.3f},{dci[k][1]:+.3f}]')
    out[str(h // 60)] = {k: dict(auc=auc(P[k][ok], yts[ok]), ci=ci[k], d=dci[k]) for k in arms}
json.dump(out, open(HERE + '/results/leave_series_out.json', 'w'), indent=1)
