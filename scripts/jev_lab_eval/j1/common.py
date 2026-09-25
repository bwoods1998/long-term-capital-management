"""Shared loading / row construction for the J1 move-sensor analysis.

Row construction is evaluate.py's `build` (executable mode) verbatim, extended with extra
free features computed from the lab-format state and the recorder's own earlier minute quotes
(semantic_quotes), the market's first label (static cache), and a deterministic series category.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
from collections import defaultdict

import numpy as np

import os

#: The working directory holding the private extracts (data/) and results/; never inside the repository.
HERE = os.environ.get('J1_ANALYSIS_DIR', '.')
# Column order of the lab's response answers used by evaluate.py (alphabetical).
K = ['ambiguous_settlement', 'continuous_threshold', 'discrete_event', 'fragile_liquidity',
     'missing_catalyst_context', 'recent_reversal', 'related_exposure', 'relative_return']
STATIC = ['continuous_threshold', 'relative_return', 'discrete_event', 'ambiguous_settlement',
          'related_exposure', 'missing_catalyst_context']
QUOTE = ['fragile_liquidity', 'recent_reversal']
KI = {k: i for i, k in enumerate(K)}

CATS = [
    ('crypto', ('KXBTC', 'KXETH', 'KXSOL', 'KXDOGE', 'KXXRP', 'KXNEAR', 'KXZEC', 'KXHYPE', 'KXBNB', 'KXCRYPTO',
                'KXLTC', 'KXADA', 'KXAVAX', 'KXLINK', 'KXSHIB')),
    ('weather', ('KXHIGH', 'KXLOW', 'KXRAIN', 'KXSNOW', 'KXTEMP', 'KXHURR', 'KXTORN')),
    ('sports', ('KXMLB', 'KXNFL', 'KXNBA', 'KXWNBA', 'KXNHL', 'KXMLS', 'KXNCAA', 'KXT20', 'KXODI', 'KXTEST', 'KXLOL',
                'KXCS2', 'KXDOTA', 'KXVAL', 'KXUCL', 'KXEPL', 'KXLALIGA', 'KXLIGUE1', 'KXSERIEA', 'KXBUNDES', 'KXLIGA',
                'KXBRASILEIRO', 'KXARGPREM', 'KXPGA', 'KXATP', 'KXWTA', 'KXUFC', 'KXF1', 'KXNASCAR', 'KXUEFA', 'KXWT20',
                'KXINTLFRIENDLY', 'KXVALORANT', 'KXFIFA', 'KXCFB')),
    ('finance', ('KXWTI', 'KXGOLD', 'KXSILVER', 'KXDIESEL', 'KXAAAGAS', 'KXINX', 'KXNASDAQ', 'KXDOW', 'KXDJI', 'KXUSD',
                 'KXEUR', 'KXGBP', 'KXJPY', 'KXTNOTE', 'KXSOFR', 'KXFED', 'KXCPI', 'KXNATGAS', 'KXCOPPER', 'KXBRENT')),
]
CATNAMES = ['crypto', 'weather', 'sports', 'finance', 'other']


def category(series):
    s = (series or '').upper()
    for name, prefixes in CATS:
        if s.startswith(prefixes):
            return name
    return 'other'


def f(x):
    return float(x) if x not in ('', None) else None


def load(path=HERE + '/data'):
    quotes = defaultdict(list)
    with open(f'{path}/quotes.csv') as fh:
        for m, t, b, a in csv.reader(fh):
            quotes[m].append((float(t), float(b), float(a)))
    for m in quotes:
        quotes[m].sort()
    times = {m: [q[0] for q in v] for m, v in quotes.items()}
    tasks = []
    with open(f'{path}/tasks.csv') as fh:
        for r in csv.reader(fh):
            (rowid, ent, obs, fin, minute, bid, ask, oi, hrs, eb, ea, series, cost, tok, vol, hres, strike, title,
             npeers, eq, nq, rules_len, subtitle, close_time, started, model) = r[:26]
            labels = [f(x) for x in r[26:34]]
            if None in labels or f(bid) is None or f(ask) is None:
                continue
            tasks.append(dict(rowid=int(rowid), entity=ent, observed=float(obs), finished=float(fin), minute=float(minute),
                              bid=float(bid), ask=float(ask), oi=f(oi), hours=f(hrs), eb=f(eb), ea=f(ea),
                              series=series, cost=float(cost or 0), tokens=int(tok or 0), labels=labels,
                              vol=f(vol), hres=f(hres), strike=f(strike), title=title, npeers=int(npeers or 0),
                              eq=json.loads(eq) if eq else [], nq=int(nq), close_time=close_time))
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


def first_labels(tasks):
    """The market's first label by finish time: what a once-per-market cache would hold."""
    first = {}
    for t in tasks:
        cur = first.get(t['entity'])
        if cur is None or t['finished'] < cur['finished']:
            first[t['entity']] = t
    return {m: t['labels'] for m, t in first.items()}


def history_features(quotes, times, m, nb, bid, ask, limit=None):
    """Free quote-history features at the current minute bucket nb from the recorder's own
    earlier minute quotes (strictly before nb) plus the current quote (bid, ask)."""
    ts = times.get(m, [])
    i = bisect.bisect_left(ts, nb)  # quotes[m][:i] are strictly earlier
    hist = quotes[m][:i] if ts else []
    if limit is not None:
        hist = hist[-limit:]
    mid = (bid + ask) / 2
    eq = hist[-4:]
    seq = [(q[1] + q[2]) / 2 for q in eq] + [mid]
    drift4 = mid - seq[0] if eq else 0.0
    chg4 = sum(1 for a, b in zip(seq, seq[1:]) if abs(a - b) > 1e-9)
    rng4 = max(seq) - min(seq)
    # minutes since the mid last changed (look back <= 240 min); if unchanged throughout the
    # available history, the age of the oldest quote inside the window (capped at 240).
    tchg = None
    prev_mid = mid
    oldest = nb
    j = len(hist) - 1
    while j >= 0 and nb - hist[j][0] <= 240 * 60:
        qm = (hist[j][1] + hist[j][2]) / 2
        if abs(qm - prev_mid) > 1e-9:
            # the later quote (index j+1, or the current one) is where the new mid first appeared
            later_t = hist[j + 1][0] if j + 1 < len(hist) else nb
            tchg = (nb - later_t) / 60
            break
        prev_mid = qm
        oldest = hist[j][0]
        j -= 1
    nochg = 0.0
    if tchg is None:
        tchg = (nb - oldest) / 60
        nochg = 1.0
    tchg = min(tchg, 240.0)
    w60 = [(q[1] + q[2]) / 2 for q in hist if nb - q[0] <= 3600] + [mid]
    rng60 = max(w60) - min(w60)
    n60 = len(w60) - 1
    chg60 = sum(1 for a, b in zip(w60, w60[1:]) if abs(a - b) > 1e-9)
    span4 = min((nb - eq[0][0]) / 3600, 4.0) if eq else 4.0
    return dict(drift4=drift4, chg4=chg4 / 4, rng4=rng4, nhist=len(eq) / 4, tchg=math.log1p(tchg) / math.log1p(240),
                nochg=nochg, rng60=rng60, n60=n60 / 60, chg60=min(chg60, 20) / 20, span4=span4 / 4)


RICH = ['absdrift', 'ext', 'lvol', 'npeer', 'lhrs', 'hres', 'nhist', 'chg4', 'rng4', 'tchg', 'nochg', 'rng60', 'tight', 'pinned']
DENSITY = ['n60', 'chg60', 'span4']


def build(quotes, times, tasks, h, mode='exec', first=None, hq=None, ht=None, hlimit=None):
    """evaluate.py's build (verbatim logic) plus extra fields."""
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
        # ---- extensions ----
        nb = math.floor(et / 60) * 60
        hf = history_features(hq or quotes, ht or times, m, nb, bid, ask, hlimit)
        elapsed = (et - t['observed']) / 3600
        hres = t['hres'] - elapsed if t['hres'] is not None else None
        rich = dict(absdrift=abs(hf['drift4']), ext=abs(mid - 0.5) * 2,
                    lvol=math.log1p(max(0, t['vol'] or 0)) / 15, npeer=t['npeers'] / 8,
                    lhrs=math.log1p(max(hours, 0)) / math.log1p(720) if hours is not None else 1.0,
                    hres=min(max(hres, 0), 48) / 48 if hres is not None else 1.0,
                    nhist=hf['nhist'], chg4=hf['chg4'], rng4=hf['rng4'], tchg=hf['tchg'], nochg=hf['nochg'],
                    rng60=hf['rng60'], tight=float(ask - bid <= 0.01 + 1e-9),
                    pinned=float(bid <= 0.01 + 1e-9 or ask >= 0.99 - 1e-9),
                    n60=hf['n60'], chg60=hf['chg60'], span4=hf['span4'])
        canon = [mid, ask - bid, x[2], x[3], hf['drift4']]
        rows.append(dict(entry_t=et, outcome_t=out[0], event=m.rsplit('-', 1)[0], market=m, fresh=fresh,
                         x=x, xc=canon, s=t['labels'], s1=first[m] if first else None, rich=rich,
                         series=t['series'], cat=category(t['series']), task=t,
                         bid=bid, ask=ask, fbid=out[1], fask=out[2], mid=mid, fmid=fmid,
                         up=int(fmid > mid + 1e-9), move=int(abs(fmid - mid) > 1e-9)))
    return rows


def split(rows):
    t0, t1 = min(r['entry_t'] for r in rows), max(r['entry_t'] for r in rows)
    cut = t0 + 0.6 * (t1 - t0)
    train = [r for r in rows if r['outcome_t'] < cut]
    seen = {r['event'] for r in train}
    test = [r for r in rows if r['entry_t'] >= cut and r['event'] not in seen]
    return train, test, cut


def fit(X, y, l2=1e-2, iters=30):
    """evaluate.py's Newton logistic fit; returns (predict, params)."""
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
    pred = lambda Xn: 1 / (1 + np.exp(-np.clip(np.hstack([np.ones((len(Xn), 1)), (Xn - mu) / sd]) @ w, -30, 30)))
    return pred, dict(mean=mu, sd=sd, w=w)


def auc(p, y):
    p = np.asarray(p, float); y = np.asarray(y, float)
    npos = y.sum(); nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return float('nan')
    u, inv, cnt = np.unique(p, return_inverse=True, return_counts=True)
    csum = np.cumsum(cnt)
    avg_rank = csum - (cnt - 1) / 2.0
    ranks = avg_rank[inv]
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def scores(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return dict(brier=float(np.mean((p - y) ** 2)),
                logloss=float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), auc=auc(p, y))


def event_index(test):
    ev = np.array([r['event'] for r in test])
    uniq = np.unique(ev)
    idx = [np.where(ev == e)[0] for e in uniq]
    return idx


def _wauc_prep(p, y):
    u, inv = np.unique(np.asarray(p, float), return_inverse=True)
    return inv, len(u), np.asarray(y, float)


def _wauc(prep, wts):
    """AUC of a sample where row i appears wts[i] times (== AUC of the concatenated resample)."""
    inv, ng, y = prep
    pos = np.bincount(inv, wts * y, minlength=ng)
    neg = np.bincount(inv, wts * (1 - y), minlength=ng)
    P, N = pos.sum(), neg.sum()
    if P == 0 or N == 0:
        return float('nan')
    below = np.cumsum(neg) - neg
    return float((pos * (below + 0.5 * neg)).sum() / (P * N))


def boot_auc(idx, preds, y, ref=None, reps=300, seed=7):
    """Event-clustered bootstrap: 95% intervals for each arm's AUC and (if ref) the AUC difference vs ref.
    Resampling events with replacement == weighting each row by its event's draw count."""
    rng = np.random.default_rng(seed)
    n = len(idx)
    ev_of_row = np.empty(sum(len(i) for i in idx), dtype=np.int64)
    for e, ix in enumerate(idx):
        ev_of_row[ix] = e
    preps = {k: _wauc_prep(p, y) for k, p in preds.items()}
    res = {k: [] for k in preds}
    diff = {k: [] for k in preds}
    for _ in range(reps):
        counts = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        wts = counts[ev_of_row]
        if (wts * y).sum() == 0 or (wts * (1 - y)).sum() == 0:
            continue
        a = {k: _wauc(preps[k], wts) for k in preds}
        for k in preds:
            res[k].append(a[k])
            if ref is not None:
                diff[k].append(a[k] - a[ref])
    ci = {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for k, v in res.items()}
    dci = {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for k, v in diff.items()} if ref else None
    return ci, dci
