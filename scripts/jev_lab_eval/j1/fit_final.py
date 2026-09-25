"""Fit the J1 move models on ALL development (semantic lab) executable rows and emit
move_model.json (served, free) and move_model_jev_shadow.json (free + cached static Jev answers),
then verify the pure-Python reference against numpy predictions on real lab states."""
import csv
import datetime as dt
import json
from collections import defaultdict

import numpy as np

import move_model_reference as ref
from common import *

VERSION = 'move-v1-20260924'
L2 = 1e-2
LAB5 = ['mid', 'spread', 'log_oi', 'hours', 'drift']
SERVED = LAB5 + ['absdrift', 'ext', 'lvol', 'lhrs', 'hres', 'nhist', 'chg4', 'rng4', 'tchg', 'nochg', 'rng60',
                 'tight', 'pinned', 'cat_crypto', 'cat_weather', 'cat_sports', 'cat_finance', 'cat_other']
JEV_STATIC = ['continuous_threshold', 'relative_return', 'discrete_event', 'ambiguous_settlement',
              'related_exposure', 'missing_catalyst_context']
CAT_TABLE = '; '.join(f"{name}: {', '.join(p)}" for name, p in ref.CATS)
H_DEF = ("H = the recorder's own recorded minute quotes of this market with observed < observed_minute (one quote per "
         "market and minute bucket, first seen wins, recorded from every markets: snapshot as the lab's semantic_quotes; "
         "keep >= 4 h); mid of a quote = (bid+ask)/2")
E_DEF = "E = earlier_quotes (oldest first; the last <= 4 recorded minute quotes before observed_minute)"
DEFS = {
    'mid': '(yes_bid+yes_ask)/2',
    'spread': 'yes_ask-yes_bid',
    'log_oi': 'log1p(max(0,open_interest))/15, 0 if missing',
    'hours': 'min(max(hours_to_close,0),48)/48, 1 if missing',
    'drift': 'mid minus the mid of earlier_quotes[0] (the oldest of up to four prior minute buckets), 0 if none',
    'absdrift': 'abs(drift)',
    'ext': 'abs(mid-0.5)*2',
    'lvol': 'log1p(max(0,volume_24h))/15, 0 if missing',
    'lhrs': 'log1p(max(hours_to_close,0))/log1p(720), not clamped, 1 if missing',
    'hres': 'min(max(hours_to_resolve,0),48)/48, 1 if missing',
    'nhist': 'len(earlier_quotes)/4',
    'chg4': (E_DEF + '; S = [mid of each quote in E..., mid]; number of consecutive pairs in S whose values differ by '
             'more than 1e-9, divided by 4 (0 if E is empty)'),
    'rng4': E_DEF + '; S = [mid of each quote in E..., mid]; max(S)-min(S)',
    'tchg': (H_DEF + '. Walk H from its newest quote backwards while observed_minute-observed <= 14400 s; at the first '
             'quote whose mid differs by more than 1e-9 from the mid of the quote after it (the current mid for the newest '
             'quote), T = (observed_minute - observed of that later quote, or 0 if the later one is the current quote)/60. '
             'If no such quote is found, T = (observed_minute - observed of the oldest quote visited)/60, or 0 if none was '
             'visited. T = min(T,240). Feature = log1p(T)/log1p(240)'),
    'nochg': '1 if the tchg walk found no mid change (including an empty H), else 0',
    'rng60': H_DEF + '. max-min of {mid of every quote in H with observed_minute-observed <= 3600 s} together with the current mid',
    'tight': '1 if spread <= 0.01+1e-9 else 0',
    'pinned': '1 if yes_bid <= 0.01+1e-9 or yes_ask >= 0.99-1e-9 else 0',
}
for c in ('crypto', 'weather', 'sports', 'finance', 'other'):
    DEFS['cat_' + c] = (f"1 if category(series) == '{c}' else 0; category = the first group whose prefix tuple "
                        f"series.upper() starts with, else 'other'. Groups: {CAT_TABLE}")


def vec(r, names, answers=None):
    x = dict(zip(LAB5, r['xc']))
    x.update({k: r['rich'][k] for k in RICH})
    for c in CATNAMES:
        x['cat_' + c] = float(r['cat'] == c)
    if answers is not None:
        x.update(answers)
    return [x[n] for n in names]


def static_answers(r):
    return {k: r['s1'][KI[k]] for k in JEV_STATIC}


def spec(rows, names, jev=False):
    X = np.array([vec(r, names, static_answers(r) if jev else None) for r in rows], float)
    y = np.array([r['move'] for r in rows], float)
    pred, prm = fit(X, y, l2=L2)
    return pred, prm, X, y


def heldout(rows, names, jev=False):
    tr, ts, _ = split(rows)
    pred, _, _, ytr = spec(tr, names, jev)
    Xts = np.array([vec(r, names, static_answers(r) if jev else None) for r in ts], float)
    yts = np.array([r['move'] for r in ts], float)
    return auc(pred(Xts), yts), len(tr), len(ts)


def heldout_s(rows, names):
    """held-out AUC with the 8 per-state Jev answers appended (comparison only)."""
    tr, ts, _ = split(rows)
    X = lambda rs: np.array([vec(r, names) + list(r['s']) for r in rs], float)
    ytr = np.array([r['move'] for r in tr], float); yts = np.array([r['move'] for r in ts], float)
    return auc(fit(X(tr), ytr, l2=L2)[0](X(ts)), yts)


def block(prm, names, dev_auc, dev_auc_numeric):
    return dict(features=list(names), mean=[float(v) for v in prm['mean']], sd=[float(v) for v in prm['sd']],
                weights=[float(v) for v in prm['w']], l2=L2, dev_auc=round(dev_auc, 4), dev_auc_numeric=round(dev_auc_numeric, 4))


def main():
    quotes, times, tasks = load()
    first = first_labels(tasks)
    iso = lambda t: dt.datetime.fromtimestamp(t, dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    served, lab5, shadow_j, shadow_n = {}, {}, {}, {}
    nrows, t_lo, t_hi, stats, fitted = {}, [], [], {}, {}
    for h in (300, 900, 3600):
        H = str(h // 60)
        rows = [r for r in build(quotes, times, tasks, h, 'exec', first) if r['fresh']]  # live rows are fresh
        nrows[H] = len(rows)
        t_lo.append(min(r['entry_t'] for r in rows)); t_hi.append(max(r['outcome_t'] for r in rows))
        a_served, ntr, nts = heldout(rows, SERVED)
        a_lab5, _, _ = heldout(rows, LAB5)
        a_shadow, _, _ = heldout(rows, SERVED + JEV_STATIC, jev=True)
        a_lab_j8 = heldout_s(rows, LAB5)
        a_srv_j8 = heldout_s(rows, SERVED)
        p_s, prm_s, X_s, y = spec(rows, SERVED)
        p_l, prm_l, X_l, _ = spec(rows, LAB5)
        p_j, prm_j, X_j, _ = spec(rows, SERVED + JEV_STATIC, jev=True)
        served[H] = block(prm_s, SERVED, a_served, a_lab5)
        lab5[H] = block(prm_l, LAB5, a_lab5, a_lab5)
        shadow_j[H] = block(prm_j, SERVED + JEV_STATIC, a_shadow, a_served)
        shadow_n[H] = block(prm_s, SERVED, a_served, a_served)
        stats[H] = dict(rows=len(rows), heldout_train=ntr, heldout_test=nts, move_rate=float(y.mean()),
                        heldout_auc=dict(served=a_served, lab5=a_lab5, shadow=a_shadow, lab5_plus_8jev_state=a_lab_j8, served_plus_8jev_state=a_srv_j8),
                        insample_auc=dict(served=auc(p_s(X_s), y), lab5=auc(p_l(X_l), y), shadow=auc(p_j(X_j), y)))
        fitted[H] = dict(rows=rows, p_s=p_s, p_l=p_l, p_j=p_j)
        print(H, stats[H], flush=True)
    numeric = [dict(name=n, definition=DEFS[n]) for n in SERVED]
    fitted_on = dict(rows=nrows, **{'from': iso(min(t_lo)), 'to': iso(max(t_hi))},
                     source='semantic.sqlite market tasks, executable rows')  # fresh subset only
    main_model = dict(version=VERSION, fitted_on=fitted_on, questions=dict(per_market=[], per_state=[]),
                      numeric=numeric, horizons=served, numeric_only=lab5)
    shadow = dict(version=VERSION + '-jev-shadow', fitted_on=fitted_on,
                  questions=dict(per_market=JEV_STATIC, per_state=[]), numeric=numeric,
                  horizons=shadow_j, numeric_only=shadow_n)
    json.dump(main_model, open(HERE + '/move_model.json', 'w'), indent=1)
    json.dump(shadow, open(HERE + '/move_model_jev_shadow.json', 'w'), indent=1)
    json.dump(stats, open(HERE + '/results/fit_final_stats.json', 'w'), indent=1)

    # ---- verification of the pure-Python reference on real lab states ----
    states = json.load(open(HERE + '/data/verify_states.json'))
    mm = ref.load(HERE + '/move_model.json'); sm = ref.load(HERE + '/move_model_jev_shadow.json')
    report = {}
    for H, F in fitted.items():
        byrow = {}
        for r in F['rows']:
            if r['fresh'] and str(r['task']['rowid']) in states:
                byrow.setdefault(str(r['task']['rowid']), r)
        ids = sorted(byrow)[:100]
        diffs = defaultdict(list)
        degraded = []
        for rid in ids:
            r = byrow[rid]; st = states[rid]['state']
            m = st['market']['market']
            nb = st['observed_minute']
            hist = [dict(observed=t, bid=b, ask=a) for (t, b, a) in quotes[m] if t < nb]
            ans = static_answers(r)
            x_s = np.array([vec(r, SERVED)]); x_l = np.array([vec(r, LAB5)]); x_j = np.array([vec(r, SERVED + JEV_STATIC, ans)])
            diffs['served'].append(abs(ref.predict(mm, st, hist, horizon=H) - float(F['p_s'](x_s)[0])))
            diffs['numeric_only(lab5)'].append(abs(ref.predict(mm, st, hist, horizon=H, block='numeric_only') - float(F['p_l'](x_l)[0])))
            diffs['shadow+jev'].append(abs(ref.predict(sm, st, hist, answers=ans, horizon=H) - float(F['p_j'](x_j)[0])))
            degraded.append((ref.predict(mm, st, None, horizon=H), float(F['p_s'](x_s)[0])))
        report[H] = {k: dict(n=len(v), max_abs_diff=max(v)) for k, v in diffs.items()}
        d = np.array(degraded)
        report[H]['state_only_history'] = dict(n=len(d), max_abs_diff=float(np.abs(d[:, 0] - d[:, 1]).max()),
                                               corr=float(np.corrcoef(d[:, 0], d[:, 1])[0, 1]))
        print('verify', H, report[H], flush=True)
    json.dump(report, open(HERE + '/results/verify_reference.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
