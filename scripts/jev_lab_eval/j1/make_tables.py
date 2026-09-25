"""Render results/*.json into markdown tables (results/tables.txt) for report.md."""
import json
import datetime as dt

from common import HERE

A = json.load(open(HERE + '/results/ablate.json'))
S = json.load(open(HERE + '/results/select_final.json'))
L = json.load(open(HERE + '/results/leave_series_out.json'))
F = json.load(open(HERE + '/results/fit_final_stats.json'))
V = json.load(open(HERE + '/results/verify_reference.json'))
out = []
w = out.append
ci = lambda c: f'[{c[0]:.3f}, {c[1]:.3f}]'
dci = lambda c: f'[{c[0]:+.3f}, {c[1]:+.3f}]'

w('### Ablation: "moves at all", executable rows, held-out unseen events\n')
for h in ('5', '15', '60'):
    H = A[h]
    cut = dt.datetime.fromtimestamp(H['cut'], dt.UTC).strftime('%Y-%m-%d %H:%MZ')
    w(f"**{h} min.** rows {H['rows']:,}; train {H['train']:,} ({H['train_events']} events); test {H['test']:,} "
      f"({H['test_events']} unseen events); split at {cut}; test move rate {H['base_rate_test']:.3f}.\n")
    w('| arm | k | AUC [95% CI] | ΔAUC vs lab numeric [95%] | ΔAUC vs G1 rich+series [95%] | Brier |')
    w('|---|---:|---|---|---|---:|')
    for name, s in H['arms'].items():
        w(f"| {name} | {s['k']} | {s['auc']:.3f} {ci(s['auc_ci'])} | {dci(s['d_vs_numeric_ci'])} | {dci(s['d_vs_G1_ci'])} | {s['brier']:.4f} |")
    w('')

w('### Within-category AUC (pooled models, test rows of one category)\n')
keys = ['A numeric (lab)', 'B numeric + 8 Jev per state', 'C numeric + 6 static Jev, first label',
        'D numeric + 2 quote Jev per state', 'E1 numeric + category (5)', 'E2 numeric + series table', 'F rich numeric',
        'G1 rich + series', 'G2 rich + series + 8 Jev per state', 'G4 rich + series + 6 static first + 2 quote per state']
short = ['A lab num', 'B +8 Jev', 'C +6 static', 'D +2 quote', 'E1 +cat', 'E2 +series', 'F rich', 'G1 rich+ser', 'G2 G1+8 Jev', 'G4 G1+6s+2q']
w('| h | category | n / events | ' + ' | '.join(short) + ' | G2−G1 [95%] | B−A [95%] |')
w('|---|---|---|' + '---:|' * len(short) + '---|---|')
for h in ('5', '15', '60'):
    for c, v in A[h]['per_category'].items():
        if v.get('skipped'):
            if v['n']:
                w(f"| {h} | {c} | {v['n']:,} / {v['events']} | " + ' | '.join('—' for _ in short) + ' | too few events | |')
            continue
        a = v['arms']
        w(f"| {h} | {c} | {v['n']:,} / {v['events']} | " + ' | '.join(f"{a[k]['auc']:.3f}" for k in keys) +
          f" | {dci(a['G2 rich + series + 8 Jev per state']['d_vs_G1_ci'])} | {dci(a['B numeric + 8 Jev per state']['d_vs_numeric_ci'])} |")
w('')

w('### Served-model candidates and recorder-cadence robustness (held-out)\n')
w('| model | 5 min AUC [95%] | 15 min AUC [95%] | 60 min AUC [95%] | 15 min Δ vs R2 [95%] |')
w('|---|---|---|---|---|')
for k in S['15']:
    w(f"| {k} | " + ' | '.join(f"{S[h][k]['auc']:.3f} {ci(S[h][k]['ci'])}" for h in ('5', '15', '60')) + f" | {dci(S['15'][k]['d_vs_R2'])} |")
w('')

w('### Leave-series-out (5 folds of series; train on other series, test unseen events of held-out series)\n')
w('| arm | 15 min AUC [95%] | Δ vs rich+category | 60 min AUC [95%] | Δ vs rich+category |')
w('|---|---|---|---|---|')
for k in L['15']:
    w(f"| {k} | {L['15'][k]['auc']:.3f} {ci(L['15'][k]['ci'])} | {dci(L['15'][k]['d'])} | {L['60'][k]['auc']:.3f} {ci(L['60'][k]['ci'])} | {dci(L['60'][k]['d'])} |")
w('')

w('### Direction (moving mids only; P(up | moved)), held-out AUC\n')
w('| arm | 5 min | 15 min | 60 min |')
w('|---|---:|---:|---:|')
for k in A['5']['direction']['arms']:
    w(f"| {k} | " + ' | '.join(f"{A[h]['direction']['arms'][k]['auc']:.3f}" for h in ('5', '15', '60')) + ' |')
w('| n test (moving rows) | ' + ' | '.join(f"{A[h]['direction']['n_test']:,}" for h in ('5', '15', '60')) + ' |')
w('')

w('### Final fit on all development rows\n')
w('| h | rows | move rate | held-out AUC served / lab-5 / shadow(+6 static Jev) | in-sample AUC served / lab-5 / shadow |')
w('|---|---:|---:|---|---|')
for h, s in F.items():
    ho, ins = s['heldout_auc'], s['insample_auc']
    w(f"| {h} | {s['rows']:,} | {s['move_rate']:.3f} | {ho['served']:.4f} / {ho['lab5']:.4f} / {ho['shadow']:.4f} | "
      f"{ins['served']:.4f} / {ins['lab5']:.4f} / {ins['shadow']:.4f} |")
w('')
w('### Reference implementation check (pure Python vs numpy, real lab states)\n')
w('| h | block | n | max abs diff |')
w('|---|---|---:|---:|')
for h, v in V.items():
    for k, d in v.items():
        extra = f" (corr {d['corr']:.4f})" if 'corr' in d else ''
        w(f"| {h} | {k} | {d['n']} | {d['max_abs_diff']:.2e}{extra} |")
open(HERE + '/results/tables.txt', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
