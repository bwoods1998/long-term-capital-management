"""Pure-Python reference for move_model.json (no numpy).

    features(state, history)                   -> {name: value} for every numeric feature, or None
    predict(model, state, history=None, answers=None, horizon='15', block='horizons') -> P(mid moves) or None

`state` is a semantic-lab-format state: {"observed_minute": int, "market": {yes_bid, yes_ask, open_interest,
volume_24h, hours_to_close, hours_to_resolve, series, ...}, "earlier_quotes": [...], "peers": [...]}.
`history` is the recorder's own recorded minute quotes of THIS market, as a list of
{"observed": minute_bucket_epoch_s, "bid": x, "ask": y}; only entries strictly before
state["observed_minute"] are used, order does not matter. drift/nhist/chg4/rng4 read the state's earlier_quotes
(which the lab built as the last <= 4 entries of that same history); tchg/nochg/rng60 read `history`. The recorder should keep one quote per
(market, minute bucket), first seen wins, from every `markets:` snapshot (the lab's semantic_quotes rule),
so that the cadence matches training; keep at least 4 hours of it. With history=None the state's earlier_quotes
stand in for it; that degraded mode costs about 0.01 AUC ('state4' in the analysis).
`answers` maps Jev question name -> noul probability in [0, 1] (only needed when the block lists questions).

p = 1 / (1 + exp(-(w0 + sum_i w_i * (x_i - mean_i) / sd_i))), logit clipped to [-30, 30].
"""
from __future__ import annotations

import json
import math

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
EPS = 1e-9


def category(series):
    s = (series or '').upper()
    for name, prefixes in CATS:
        if s.startswith(prefixes):
            return name
    return 'other'


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def features(state, history=None):
    """All numeric features of move_model.json for one market state, or None when the model does not
    apply (no valid two-sided quote inside [0, 1], or the market is at/after its close time)."""
    m = state['market']
    bid, ask = _num(m.get('yes_bid')), _num(m.get('yes_ask'))
    if bid is None or ask is None or not 0 <= bid <= ask <= 1:
        return None
    hours = _num(m.get('hours_to_close'))
    if hours is not None and hours <= 0:
        return None
    nb = int(state['observed_minute'])
    # E: the state's earlier_quotes (last <= 4 recorded minute quotes before nb, oldest first)
    eq = sorted((float(q['observed']), float(q['bid']), float(q['ask']))
                for q in (state.get('earlier_quotes') or []) if float(q['observed']) < nb)[-4:]
    # H: the recorder's own recorded minute quotes before nb (degraded fallback: E)
    src = eq if history is None else [(float(q['observed']), float(q['bid']), float(q['ask'])) for q in history]
    hist = sorted(q for q in src if q[0] < nb)
    mid = (bid + ask) / 2
    spread = ask - bid
    oi = _num(m.get('open_interest'))
    vol = _num(m.get('volume_24h'))
    hres = _num(m.get('hours_to_resolve'))
    seq = [(q[1] + q[2]) / 2 for q in eq] + [mid]
    drift4 = mid - seq[0] if eq else 0.0
    chg4 = sum(1 for a, b in zip(seq, seq[1:]) if abs(a - b) > EPS)
    rng4 = max(seq) - min(seq)
    # minutes since the mid last changed, looking back at most 240 minutes
    tchg = None
    prev_mid, oldest = mid, nb
    j = len(hist) - 1
    while j >= 0 and nb - hist[j][0] <= 240 * 60:
        qm = (hist[j][1] + hist[j][2]) / 2
        if abs(qm - prev_mid) > EPS:
            later_t = hist[j + 1][0] if j + 1 < len(hist) else nb
            tchg = (nb - later_t) / 60
            break
        prev_mid, oldest = qm, hist[j][0]
        j -= 1
    nochg = 0.0
    if tchg is None:
        tchg, nochg = (nb - oldest) / 60, 1.0
    tchg = min(tchg, 240.0)
    w60 = [(q[1] + q[2]) / 2 for q in hist if nb - q[0] <= 3600] + [mid]
    cat = category(m.get('series'))
    x = {
        'mid': mid,
        'spread': spread,
        'log_oi': math.log1p(max(0.0, oi)) / 15 if oi is not None else 0.0,
        'hours': min(max(hours, 0.0), 48.0) / 48 if hours is not None else 1.0,
        'drift': drift4,
        'absdrift': abs(drift4),
        'ext': abs(mid - 0.5) * 2,
        'lvol': math.log1p(max(0.0, vol or 0.0)) / 15,
        'lhrs': math.log1p(max(hours, 0.0)) / math.log1p(720) if hours is not None else 1.0,
        'hres': min(max(hres, 0.0), 48.0) / 48 if hres is not None else 1.0,
        'nhist': len(eq) / 4,
        'chg4': chg4 / 4,
        'rng4': rng4,
        'tchg': math.log1p(tchg) / math.log1p(240),
        'nochg': nochg,
        'rng60': max(w60) - min(w60),
        'tight': 1.0 if spread <= 0.01 + EPS else 0.0,
        'pinned': 1.0 if (bid <= 0.01 + EPS or ask >= 0.99 - EPS) else 0.0,
    }
    for c in ('crypto', 'weather', 'sports', 'finance', 'other'):
        x['cat_' + c] = 1.0 if cat == c else 0.0
    return x


def predict(model, state, history=None, answers=None, horizon='15', block='horizons'):
    spec = model[block][str(horizon)]
    x = features(state, history)
    if x is None:
        return None
    z = spec['weights'][0]
    for name, w, mu, sd in zip(spec['features'], spec['weights'][1:], spec['mean'], spec['sd']):
        if name in x:
            v = x[name]
        else:
            if answers is None or answers.get(name) is None:
                return None  # a required Jev answer is missing: no prediction rather than a guess
            v = float(answers[name])
        z += w * (v - mu) / sd
    z = min(max(z, -30.0), 30.0)
    return 1.0 / (1.0 + math.exp(-z))


def load(path):
    with open(path) as fh:
        return json.load(fh)


if __name__ == '__main__':
    import sys
    mdl = load(sys.argv[1] if len(sys.argv) > 1 else 'move_model.json')
    demo = {'observed_minute': 1789962480,
            'market': {'series': 'KXHIGHNY', 'yes_bid': 0.22, 'yes_ask': 0.23, 'open_interest': 2167.22,
                       'volume_24h': 2553.15, 'hours_to_close': 25.1995, 'hours_to_resolve': 39.1995},
            'earlier_quotes': [{'observed': 1789962360, 'bid': 0.22, 'ask': 0.23}]}
    for h in mdl['horizons']:
        print(h, predict(mdl, demo, history=demo['earlier_quotes'], horizon=h))
