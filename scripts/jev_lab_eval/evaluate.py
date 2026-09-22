"""Capped, free evaluation of the semantic lab's Jev market labels (Sept 22, 2026).

Question: do the eight fixed Jev noul features add out-of-sample predictive and TRADABLE value
over a numeric baseline for later Kalshi midpoint moves, after the spread?

Inputs (read-only extracts of /workspace/state/semantic.sqlite on the House box, made by
extract.py): tasks.csv (every completed market task: focal quote, OI, hours, earlier quote,
8 fixed labels) and quotes.csv (semantic_quotes: market, minute bucket, bid, ask).

Two row constructions per horizon:
  lab-style   entry at the observed state quote; outcome = first quote in [obs+h, obs+h+10m];
              the label must finish before the outcome quote (the lab's own markouts rule).
  executable  a trader can only act once the label exists: fresh labels (finished-observed
              <= 120 s) enter at the observed quote; stale labels enter at the first quote at or
              after `finished` (within 10 min). Outcome = first quote in [entry+h, entry+h+10m].
Chronological split at 60% of the entry-time range; train rows must have their outcome before
the split; test rows start after it, from events (ticker minus last '-' segment) never seen in
training. Arms on identical rows: base rate, numeric logistic, numeric + 8 Jev features.
"""
from __future__ import annotations

import bisect
import csv
import math
import sys
from collections import defaultdict

import numpy as np

K = ['ambiguous_settlement', 'continuous_threshold', 'discrete_event', 'fragile_liquidity',
     'missing_catalyst_context', 'recent_reversal', 'related_exposure', 'relative_return']
HERE = sys.argv[1] if len(sys.argv) > 1 else '.'


def f(x):
    return float(x) if x not in ('', None) else None


def load():
    quotes = defaultdict(list)
    with open(f'{HERE}/quotes.csv') as fh:
        for m, t, b, a in csv.reader(fh):
            quotes[m].append((float(t), float(b), float(a)))
    for m in quotes:
        quotes[m].sort()
    times = {m: [q[0] for q in v] for m, v in quotes.items()}
    tasks = []
    with open(f'{HERE}/tasks.csv') as fh:
        for r in csv.reader(fh):
            ent, obs, fin, minute, bid, ask, oi, hrs, eb, ea, series, cost, tok = r[:13]
            labels = [f(x) for x in r[13:21]]
            if None in labels or f(bid) is None or f(ask) is None:
                continue
            tasks.append(dict(entity=ent, observed=float(obs), finished=float(fin), minute=float(minute),
                              bid=float(bid), ask=float(ask), oi=f(oi), hours=f(hrs), eb=f(eb), ea=f(ea),
                              series=series, cost=float(cost or 0), tokens=int(tok or 0), labels=labels))
    return quotes, times, tasks


def first_at(quotes, times, m, lo, hi):
    ts = times.get(m)
    if not ts:
        return None
    i = bisect.bisect_left(ts, lo)
    if i < len(ts) and ts[i] <= hi:
        return quotes[m][i]
    return None


def last_before(quotes, times, m, t, window=1800):
    ts = times.get(m)
    if not ts:
        return None
    i = bisect.bisect_left(ts, t) - 1
    if i >= 0 and t - ts[i] <= window:
        return quotes[m][i]
    return None


def build(quotes, times, tasks, h, mode):
    rows = []
    for t in tasks:
        m = t['entity']
        fresh = t['finished'] - t['observed'] <= 120
        if mode == 'lab' or fresh:
            et, bid, ask = t['observed'], t['bid'], t['ask']
            drift = (bid + ask) / 2 - (t['eb'] + t['ea']) / 2 if t['eb'] is not None and t['ea'] is not None else 0.0
        else:
            q = first_at(quotes, times, m, t['finished'], t['finished'] + 600)
            if q is None:
                continue
            et, bid, ask = q
            p = last_before(quotes, times, m, et)
            drift = (bid + ask) / 2 - (p[1] + p[2]) / 2 if p else 0.0
        if not 0 <= bid <= ask <= 1:
            continue
        hours = t['hours'] - (et - t['observed']) / 3600 if t['hours'] is not None else None
        if hours is not None and hours <= 0:
            continue
        out = first_at(quotes, times, m, et + h, et + h + 600)
        if out is None or out[0] <= t['finished']:
            continue
        mid, fmid = (bid + ask) / 2, (out[1] + out[2]) / 2
        oi = t['oi']
        x = [mid, ask - bid, math.log1p(max(0, oi)) / 15 if oi is not None else 0,
             min(max(hours, 0), 48) / 48 if hours is not None else 1, drift]
        rows.append(dict(entry_t=et, outcome_t=out[0], event=m.rsplit('-', 1)[0], market=m, fresh=fresh,
                         x=x, s=t['labels'], bid=bid, ask=ask, fbid=out[1], fask=out[2], mid=mid, fmid=fmid,
                         up=int(fmid > mid + 1e-9), move=int(abs(fmid - mid) > 1e-9)))
    return rows


def fit(X, y, l2=1e-2, iters=30):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    reg = np.eye(Z.shape[1]) * l2 * len(X)
    reg[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + reg @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + reg + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return lambda Xn: 1 / (1 + np.exp(-np.clip(np.hstack([np.ones((len(Xn), 1)), (Xn - mu) / sd]) @ w, -30, 30)))


def auc(p, y):
    order = np.argsort(p, kind='mergesort')
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    # average ties
    ps = p[order]
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2
        i = j + 1
    npos, nneg = y.sum(), len(y) - y.sum()
    if npos == 0 or nneg == 0:
        return float('nan')
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def scores(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return dict(brier=float(np.mean((p - y) ** 2)), logloss=float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), auc=auc(p, y))


def trade(rows, p, thr):
    pnl, fric, n = [], [], 0
    for r, q in zip(rows, p):
        if q > thr:
            pnl.append(r['fbid'] - r['ask']); fric.append(r['fmid'] - r['mid'])
        elif q < 1 - thr:
            pnl.append(r['bid'] - r['fask']); fric.append(r['mid'] - r['fmid'])
    if not pnl:
        return dict(n=0, pnl=None, fric=None)
    return dict(n=len(pnl), pnl=float(np.mean(pnl)), fric=float(np.mean(fric)), total=float(np.sum(pnl)))


def event_bootstrap(test, pa, pb, y, reps=300, seed=7):
    rng = np.random.default_rng(seed)
    ev = np.array([r['event'] for r in test])
    uniq = np.unique(ev)
    idx = {e: np.where(ev == e)[0] for e in uniq}
    diffs = []
    for _ in range(reps):
        pick = np.concatenate([idx[e] for e in rng.choice(uniq, len(uniq))])
        diffs.append(np.mean((pa[pick] - y[pick]) ** 2) - np.mean((pb[pick] - y[pick]) ** 2))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def evaluate(rows, label):
    if len(rows) < 200:
        print(f'{label}: {len(rows)} rows, insufficient'); return
    t0, t1 = min(r['entry_t'] for r in rows), max(r['entry_t'] for r in rows)
    split = t0 + 0.6 * (t1 - t0)
    train = [r for r in rows if r['outcome_t'] < split]
    seen = {r['event'] for r in train}
    test = [r for r in rows if r['entry_t'] >= split and r['event'] not in seen]
    flat = 1 - np.mean([r['move'] for r in rows])
    print(f'\n== {label}: rows={len(rows)} markets={len({r["market"] for r in rows})} events={len({r["event"] for r in rows})} '
          f'flat_mid_share={flat:.3f} fresh_share={np.mean([r["fresh"] for r in rows]):.3f}')
    print(f'   train={len(train)} (events {len(seen)})  test={len(test)} (events {len({r["event"] for r in test})}, unseen only)')
    if len(train) < 100 or len(test) < 100:
        print('   insufficient train/test'); return
    Xn = lambda rs: np.array([r['x'] for r in rs])
    Xs = lambda rs: np.array([r['x'] + r['s'] for r in rs])
    te = test
    hs = np.mean([(r['ask'] - r['bid']) / 2 for r in te]); mv = np.mean([abs(r['fmid'] - r['mid']) for r in te])
    print(f'   test mean |mid move|={mv:.4f}  mean half-spread={hs:.4f}  (move/half-spread={mv / hs if hs else float("nan"):.2f})')
    for target in ('up', 'move', 'dir'):
        tr = train if target != 'dir' else [r for r in train if r['move']]
        ts = te if target != 'dir' else [r for r in te if r['move']]
        if len(tr) < 100 or len(ts) < 50:
            print(f'   [{target}] insufficient'); continue
        key = 'move' if target == 'move' else 'up'
        ytr, yts = np.array([r[key] for r in tr], float), np.array([r[key] for r in ts], float)
        base = np.full(len(ts), ytr.mean())
        pn = fit(Xn(tr), ytr)(Xn(ts)); pj = fit(Xs(tr), ytr)(Xs(ts))
        sb, sn, sj = scores(base, yts), scores(pn, yts), scores(pj, yts)
        lo, hi = event_bootstrap(ts, pn, pj, yts)
        print(f'   [{target}] n_test={len(ts)} base_rate={ytr.mean():.3f}')
        for name, s in (('base rate', sb), ('numeric', sn), ('numeric+jev', sj)):
            print(f'      {name:12s} brier={s["brier"]:.5f} logloss={s["logloss"]:.5f} auc={s["auc"]:.4f}')
        print(f'      jev brier gain vs numeric={sn["brier"] - sj["brier"]:+.5f} (event bootstrap 95% [{lo:+.5f},{hi:+.5f}])')
        if target == 'dir':
            # Trade every test row (flat ones included: flatness is not known in advance).
            ytr_all = np.array([r['up'] for r in tr], float)
            mn, mj = fit(Xn(tr), ytr_all), fit(Xs(tr), ytr_all)
            qn, qj = mn(Xn(te)), mj(Xs(te))
            for thr in (0.55, 0.6, 0.7):
                a, b = trade(te, qn, thr), trade(te, qj, thr)
                fa, fb = trade([r for r in te if r['fresh']], qn[[r['fresh'] for r in te]], thr), trade([r for r in te if r['fresh']], qj[[r['fresh'] for r in te]], thr)
                fmt = lambda d: f"n={d['n']:5d} pnl/contract={d['pnl']:+.4f} frictionless={d['fric']:+.4f}" if d['n'] else 'n=0'
                print(f'      trade thr={thr}: numeric {fmt(a)} | +jev {fmt(b)}')
                print(f'                 fresh-only: numeric {fmt(fa)} | +jev {fmt(fb)}')


def main():
    quotes, times, tasks = load()
    cost = sum(t['cost'] for t in tasks); tok = sum(t['tokens'] for t in tasks)
    fresh = np.mean([t['finished'] - t['observed'] <= 120 for t in tasks])
    lag = np.median([t['finished'] - t['observed'] for t in tasks])
    print(f'completed market tasks={len(tasks)} markets={len({t["entity"] for t in tasks})} '
          f'quotes={sum(len(v) for v in quotes.values())} market-label cost=${cost:.4f} input_tokens={tok} '
          f'fresh(<=120s) share={fresh:.3f} median label lag={lag:.0f}s')
    for h in (300, 900, 3600):
        for mode in ('lab', 'exec'):
            evaluate(build(quotes, times, tasks, h, mode), f'h={h // 60}min {mode}')


if __name__ == '__main__':
    main()
