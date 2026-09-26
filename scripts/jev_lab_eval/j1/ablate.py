"""J1 ablations on identical executable rows, chronological 60% split, unseen-event test rows.
Target: 'moves at all' at 5/15/60 min; direction briefly. Writes results/ablate.json."""
import json
import sys
import time

import numpy as np

from common import *

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
MIN_SERIES_ROWS = 200


def onehots(train):
    from collections import Counter
    c = Counter(r['series'] for r in train)
    keep = sorted(s for s, n in c.items() if n >= MIN_SERIES_ROWS)
    return keep


def cat_vec(r):
    return [float(r['cat'] == c) for c in CATNAMES]


def series_vec(r, keep):
    v = [float(r['series'] == s) for s in keep]
    # series too thin to get its own column fall back to their category
    fb = r['series'] not in keep
    return v + [float(fb and r['cat'] == c) for c in CATNAMES]


def arms_for(keep):
    S = [KI[k] for k in STATIC]; Q = [KI[k] for k in QUOTE]
    rich = lambda r: [r['rich'][k] for k in RICH]
    dens = lambda r: [r['rich'][k] for k in DENSITY]
    return {
        'A numeric (lab)': lambda r: r['x'],
        'A2 numeric (canonical drift)': lambda r: r['xc'],
        'B numeric + 8 Jev per state': lambda r: r['x'] + r['s'],
        'C numeric + 6 static Jev, first label': lambda r: r['x'] + [r['s1'][i] for i in S],
        'C2 numeric + all 8 Jev, first label': lambda r: r['x'] + r['s1'],
        'C3 numeric + 6 static first + 2 quote Jev per state': lambda r: r['x'] + [r['s1'][i] for i in S] + [r['s'][i] for i in Q],
        'D numeric + 2 quote Jev per state': lambda r: r['x'] + [r['s'][i] for i in Q],
        'D2 numeric + 6 static Jev per state': lambda r: r['x'] + [r['s'][i] for i in S],
        'E1 numeric + category (5)': lambda r: r['x'] + cat_vec(r),
        'E2 numeric + series table': lambda r: r['x'] + series_vec(r, keep),
        'F rich numeric': lambda r: r['xc'] + rich(r),
        'F2 rich numeric + sampling density': lambda r: r['xc'] + rich(r) + dens(r),
        'G1 rich + series': lambda r: r['xc'] + rich(r) + series_vec(r, keep),
        'G2 rich + series + 8 Jev per state': lambda r: r['xc'] + rich(r) + series_vec(r, keep) + r['s'],
        'G3 rich + series + 6 static first': lambda r: r['xc'] + rich(r) + series_vec(r, keep) + [r['s1'][i] for i in S],
        'G4 rich + series + 6 static first + 2 quote per state': lambda r: r['xc'] + rich(r) + series_vec(r, keep) + [r['s1'][i] for i in S] + [r['s'][i] for i in Q],
        'G5 rich + series + 2 quote per state': lambda r: r['xc'] + rich(r) + series_vec(r, keep) + [r['s'][i] for i in Q],
        'G6 rich + 8 Jev per state': lambda r: r['xc'] + rich(r) + r['s'],
        'G7 rich + 6 static first + 2 quote per state': lambda r: r['xc'] + rich(r) + [r['s1'][i] for i in S] + [r['s'][i] for i in Q],
        'G8 numeric + series + 8 Jev per state': lambda r: r['x'] + series_vec(r, keep) + r['s'],
        'G9 rich + category + 2 quote per state': lambda r: r['xc'] + rich(r) + cat_vec(r) + [r['s'][i] for i in Q],
        'G10 rich + category': lambda r: r['xc'] + rich(r) + cat_vec(r),
        'G11 rich + series + 2 quote first label': lambda r: r['xc'] + rich(r) + series_vec(r, keep) + [r['s1'][i] for i in Q],
    }


def main():
    t_start = time.time()
    quotes, times, tasks = load()
    first = first_labels(tasks)
    out = {}
    for h in (300, 900, 3600):
        rows = build(quotes, times, tasks, h, 'exec', first)
        train, test, cut = split(rows)
        keep = onehots(train)
        arms = arms_for(keep)
        H = {}
        H['rows'] = len(rows); H['train'] = len(train); H['test'] = len(test)
        H['train_events'] = len({r['event'] for r in train}); H['test_events'] = len({r['event'] for r in test})
        H['cut'] = cut; H['series_columns'] = keep
        ytr = np.array([r['move'] for r in train], float); yts = np.array([r['move'] for r in test], float)
        H['base_rate_train'] = float(ytr.mean()); H['base_rate_test'] = float(yts.mean())
        preds = {}
        res = {}
        for name, fn in arms.items():
            Xtr = np.array([fn(r) for r in train], float); Xts = np.array([fn(r) for r in test], float)
            pr, _ = fit(Xtr, ytr)
            p = pr(Xts); preds[name] = p
            res[name] = scores(p, yts); res[name]['k'] = Xtr.shape[1]
        idx = event_index(test)
        ci, dci = boot_auc(idx, preds, yts, ref='A numeric (lab)', reps=REPS)
        _, dci_g1 = boot_auc(idx, preds, yts, ref='G1 rich + series', reps=REPS)
        _, dci_e2 = boot_auc(idx, preds, yts, ref='E2 numeric + series table', reps=REPS)
        for name in arms:
            res[name]['auc_ci'] = ci[name]; res[name]['d_vs_numeric_ci'] = dci[name]
            res[name]['d_vs_G1_ci'] = dci_g1[name]; res[name]['d_vs_E2_ci'] = dci_e2[name]
        H['arms'] = res
        # ---- per category, pooled models' predictions on test rows of that category ----
        cats = {}
        catv = np.array([r['cat'] for r in test])
        for c in CATNAMES:
            m = catv == c
            n = int(m.sum())
            evs = {test[i]['event'] for i in np.where(m)[0]}
            if n < 300 or len(evs) < 4 or yts[m].min() == yts[m].max():
                cats[c] = dict(n=n, events=len(evs), skipped=True)
                continue
            sub = [test[i] for i in np.where(m)[0]]
            sidx = event_index(sub)
            sp = {k: v[m] for k, v in preds.items()}
            cci, cd = boot_auc(sidx, sp, yts[m], ref='A numeric (lab)', reps=max(100, REPS // 2))
            _, cdg = boot_auc(sidx, sp, yts[m], ref='G1 rich + series', reps=max(100, REPS // 2))
            cats[c] = dict(n=n, events=len(evs), base=float(yts[m].mean()),
                           arms={k: dict(auc=auc(sp[k], yts[m]), ci=cci[k], d_vs_numeric_ci=cd[k], d_vs_G1_ci=cdg[k]) for k in sp})
        H['per_category'] = cats
        # ---- direction (moving mids only), brief ----
        trm = [r for r in train if r['move']]; tsm = [r for r in test if r['move']]
        yd_tr = np.array([r['up'] for r in trm], float); yd_ts = np.array([r['up'] for r in tsm], float)
        dres = {}
        for name in ('A numeric (lab)', 'B numeric + 8 Jev per state', 'G1 rich + series', 'G2 rich + series + 8 Jev per state'):
            fn = arms[name]
            pr, _ = fit(np.array([fn(r) for r in trm], float), yd_tr)
            p = pr(np.array([fn(r) for r in tsm], float))
            dres[name] = scores(p, yd_ts)
        H['direction'] = dict(n_test=len(tsm), arms=dres)
        out[str(h // 60)] = H
        print(f'h={h // 60}: rows={len(rows)} train={len(train)} test={len(test)} ({H["test_events"]} events) '
              f'{time.time() - t_start:.0f}s', flush=True)
        for name, s in res.items():
            print(f'   {name:55s} k={s["k"]:3d} auc={s["auc"]:.4f} [{s["auc_ci"][0]:.3f},{s["auc_ci"][1]:.3f}] '
                  f'dNum=[{s["d_vs_numeric_ci"][0]:+.3f},{s["d_vs_numeric_ci"][1]:+.3f}] dG1=[{s["d_vs_G1_ci"][0]:+.3f},{s["d_vs_G1_ci"][1]:+.3f}] brier={s["brier"]:.5f}', flush=True)
        for c, v in cats.items():
            if v.get('skipped'):
                print(f'   [{c}] n={v["n"]} events={v["events"]} skipped'); continue
            a = v['arms']
            print(f'   [{c}] n={v["n"]} events={v["events"]} base={v["base"]:.3f} ' + ' '.join(
                f'{k.split()[0]}={a[k]["auc"]:.3f}' for k in a))
        print('   direction:', {k: round(v['auc'], 4) for k, v in dres.items()}, flush=True)
    import os
    os.makedirs(HERE + '/results', exist_ok=True)
    json.dump(out, open(HERE + '/results/ablate.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
