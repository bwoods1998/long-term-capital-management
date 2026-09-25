## Part A results (research sessions)

### A1. Population as specified: gate `run` sessions (non-sampled)

n train 3991 (o1 668, o2 508, $91.58); n held-out 2157 (o1 602, o2 550, $91.69); held-out agents 253

Mean Jev p: train 0.186, held-out 0.249; share p<0.1: train 14%, held-out 2%

| score (higher = run) | AUC o1 held-out [95% agent-clustered] | AUC o2 held-out | AUC o2 train |
|---|---|---|---|
| jev_p | 0.622 [0.587, 0.652] | 0.623 [0.588, 0.655] | 0.704 |
| trigger_kind | 0.756 [0.707, 0.796] | 0.754 [0.707, 0.797] | 0.798 |
| streak (neg) | 0.735 [0.694, 0.769] | 0.731 [0.687, 0.767] | 0.798 |
| record_class | 0.835 [0.791, 0.872] | 0.831 [0.791, 0.869] | 0.510 |
| fills_or_settles | 0.313 [0.284, 0.343] | 0.312 [0.281, 0.344] | 0.427 |
| any_new_evidence | 0.412 [0.375, 0.450] | 0.408 [0.370, 0.446] | 0.472 |
| prev_outcome | 0.702 [0.671, 0.735] | 0.699 [0.664, 0.734] | 0.754 |
| deterministic_model | 0.847 [0.810, 0.877] | 0.844 [0.805, 0.877] | 0.828 |
| det_model+jev | 0.846 [0.809, 0.876] | 0.843 [0.804, 0.877] | 0.829 |

Logistic weights (standardized features, fitted on train, label o2): {"deterministic": {"kind_rate": 0.37, "log1p_streak": -0.56, "record_rate": 0.085, "fills_or_settles": -0.308, "prev_outcome_rate": 0.405, "any_new": -0.177, "log1p_hours_since_prev": 0.143}, "combined": {"kind_rate": 0.366, "log1p_streak": -0.555, "record_rate": 0.084, "fills_or_settles": -0.311, "prev_outcome_rate": 0.4, "any_new": -0.187, "log1p_hours_since_prev": 0.146, "jev_p": 0.023}}

Skip curve on the held-out window (threshold = the train quantile that skips share q of train sessions; skip when score < threshold). Columns: held-out share of sessions skipped / dollars skipped / candidates (o1) lost / replay passes (o2) lost.

| score | q=0.1 | q=0.2 | q=0.3 | q=0.4 | q=0.5 | q=0.6 | q=0.7 | q=0.8 | q=0.9 |
|---|---|---|---|---|---|---|---|---|---|
| jev_p | 1%/1%/0%/0% | 3%/2%/1%/1% | 6%/4%/3%/3% | 13%/11%/7%/7% | 17%/14%/10%/9% | 27%/24%/17%/16% | 45%/44%/30%/29% | 63%/65%/50%/50% | 81%/83%/76%/76% |
| trigger_kind | 1%/1%/1%/1% | 25%/8%/3%/3% | 25%/8%/3%/3% | 28%/13%/6%/5% | 43%/19%/9%/7% | 56%/39%/31%/29% | 69%/59%/53%/53% | 78%/63%/56%/56% | 98%/99%/95%/94% |
| prev_outcome | 0%/0%/0%/0% | 0%/0%/0%/0% | 0%/0%/0%/0% | 61%/52%/37%/36% | 61%/52%/37%/36% | 61%/52%/37%/36% | 61%/52%/37%/36% | 68%/56%/39%/38% | 73%/60%/45%/44% |
| deterministic_model | 26%/6%/1%/1% | 31%/7%/1%/1% | 33%/9%/2%/1% | 35%/9%/2%/2% | 38%/11%/3%/2% | 41%/13%/4%/3% | 44%/17%/7%/7% | 66%/48%/28%/27% | 81%/68%/56%/56% |
| det_model+jev | 26%/6%/1%/1% | 31%/7%/1%/1% | 33%/9%/2%/1% | 35%/9%/2%/2% | 38%/11%/3%/2% | 41%/13%/4%/3% | 44%/17%/8%/7% | 67%/49%/29%/28% | 81%/69%/56%/56% |

The ≥30% dollars / ≤10% replay-pass test: threshold = the one that skips the most TRAIN dollars with train o2 loss ≤ 10%, applied unchanged to held-out.

| score | threshold | train: sessions/dollars/o1/o2 skipped | held-out: sessions/dollars/o1/o2 skipped | meets ≥30% $ and ≤10% o2 on held-out? |
|---|---|---|---|---|
| jev_p | 0.11 | 22%/16%/9%/8% | 3%/2%/1%/1% | no |
| trigger_kind | 0.03839 | 20%/16%/5%/3% | 25%/8%/3%/3% | no |
| prev_outcome | 0.05751 | 0%/0%/0%/0% | 0%/0%/0%/0% | no |
| deterministic_model | 0.05387 | 47%/39%/11%/10% | 38%/11%/3%/2% | no |
| det_model+jev | 0.05279 | 47%/38%/11%/10% | 37%/11%/3%/2% | no |

### Jev p by trigger kind (held-out AUC within kind; kinds with ≥20 sessions and ≥3 of each class)

| trigger kind | split | n | $ | o1 | o2 | mean p | AUC o1 | AUC o2 |
|---|---|---|---|---|---|---|---|---|
| refusal_prompt | test | 540 | 6.94 | 28 | 23 | 0.19 | 0.639 [0.517, 0.762] | 0.610 [0.474, 0.732] |
| book.fill | test | 507 | 6.21 | 12 | 8 | 0.22 | 0.566 [0.450, 0.722] | 0.615 [0.448, 0.799] |
| clock | test | 448 | 32.65 | 230 | 213 | 0.23 | 0.600 [0.559, 0.658] | 0.597 [0.551, 0.657] |
| library.note | test | 279 | 18.27 | 129 | 128 | 0.28 | 0.635 [0.576, 0.690] | 0.633 [0.574, 0.688] |
| book.settle | test | 217 | 3.98 | 13 | 9 | 0.23 | 0.567 [0.397, 0.746] | 0.594 [0.356, 0.794] |
| heartbeat | test | 162 | 3.50 | 15 | 11 | 0.43 | 0.515 [0.374, 0.654] | 0.505 [0.350, 0.668] |
| lesson | test | 145 | 10.82 | 70 | 63 | 0.26 | 0.664 [0.591, 0.730] | 0.634 [0.554, 0.700] |
| book.refused | test | 125 | 1.30 | 4 | 4 | 0.17 | 0.611 [0.366, 1.000] | 0.611 [0.366, 1.000] |
| repair.status | test | 70 | 3.10 | 50 | 41 | 0.29 | 0.560 [0.391, 0.700] | 0.626 [0.499, 0.761] |
| backoff_elapsed | test | 58 | 4.46 | 15 | 14 | 0.17 | 0.795 [0.560, 0.951] | 0.769 [0.552, 0.928] |
| eval.block | test | 42 | 3.19 | 13 | 12 | 0.24 | 0.578 [0.400, 0.777] | 0.615 [0.441, 0.809] |
| code | test | 37 | 1.25 | 33 | 31 | 0.37 | 0.788 [0.538, 1.000] | 0.567 [0.282, 0.899] |
| jev | test | 26 | 1.10 | 8 | 6 | 0.18 | 0.455 [0.216, 0.761] | 0.362 [0.156, 0.643] |
| market | test | 19 | 0.52 | 5 | 5 | 0.22 | n/a | n/a |
| agent.strategy | test | 6 | 0.12 | 0 | 0 | 0.36 | n/a | n/a |
| tool.fulfilled | test | 4 | 0.25 | 2 | 2 | 0.28 | n/a | n/a |
| window | test | 4 | 0.09 | 1 | 1 | 0.20 | n/a | n/a |
| eval.verdict | test | 3 | 0.68 | 1 | 1 | 0.32 | n/a | n/a |
| credit.grant | test | 3 | 0.12 | 0 | 0 | 0.18 | n/a | n/a |
| unblocked | test | 2 | 0.06 | 1 | 1 | 0.11 | n/a | n/a |
| backoff_elapsed | train | 958 | 18.34 | 45 | 35 | 0.12 | 0.584 [0.491, 0.691] | 0.557 [0.433, 0.671] |
| library.note | train | 942 | 25.27 | 175 | 115 | 0.19 | 0.655 [0.604, 0.712] | 0.638 [0.575, 0.703] |
| clock | train | 682 | 17.53 | 283 | 219 | 0.23 | 0.514 [0.445, 0.569] | 0.528 [0.451, 0.587] |
| book.fill | train | 525 | 8.57 | 20 | 14 | 0.20 | 0.591 [0.502, 0.685] | 0.621 [0.509, 0.728] |
| code | train | 197 | 3.79 | 95 | 94 | 0.39 | 0.422 [0.346, 0.518] | 0.426 [0.350, 0.525] |
| book.settle | train | 163 | 4.38 | 8 | 6 | 0.21 | 0.597 [0.289, 0.768] | 0.724 [0.482, 0.890] |
| refusal_prompt | train | 158 | 2.39 | 4 | 3 | 0.18 | 0.865 [0.703, 0.983] | 0.845 [0.655, 1.000] |
| credit.grant | train | 153 | 3.43 | 7 | 2 | 0.13 | 0.548 [0.380, 0.724] | n/a |
| jev | train | 129 | 3.08 | 4 | 0 | 0.13 | 0.716 [0.542, 0.911] | n/a |
| book.refused | train | 62 | 1.84 | 3 | 3 | 0.14 | 0.910 [0.736, 1.000] | 0.910 [0.736, 1.000] |
| eval.verdict | train | 50 | 0.93 | 4 | 4 | 0.21 | 0.644 [0.260, 0.958] | 0.644 [0.260, 0.958] |
| market | train | 45 | 1.55 | 11 | 7 | 0.14 | 0.763 [0.634, 0.871] | 0.742 [0.559, 0.889] |
| window | train | 34 | 0.83 | 7 | 4 | 0.15 | 0.582 [0.220, 0.897] | 0.708 [0.000, 1.000] |
| heartbeat | train | 21 | 1.22 | 5 | 4 | 0.44 | 0.688 [0.344, 0.941] | 0.640 [0.263, 0.947] |
| tool.fulfilled | train | 10 | 0.16 | 0 | 0 | 0.21 | n/a | n/a |
| lesson | train | 10 | 0.36 | 0 | 0 | 0.35 | n/a | n/a |
| unblocked | train | 3 | 0.06 | 1 | 1 | 0.12 | n/a | n/a |
| repair.status | train | 3 | 0.15 | 0 | 0 | 0.20 | n/a | n/a |
| eval.block | train | 3 | 0.08 | 0 | 0 | 0.17 | n/a | n/a |
| agent.strategy | train | 1 | 0.01 | 0 | 0 | 0.28 | n/a | n/a |

### A2. Gate runs plus the House's refusal fast path (F2 routes it through the gate)

n train 4149 (o1 672, o2 511, $93.96); n held-out 2697 (o1 630, o2 573, $98.63); held-out agents 257

Mean Jev p: train 0.186, held-out 0.238; share p<0.1: train 14%, held-out 2%

| score (higher = run) | AUC o1 held-out [95% agent-clustered] | AUC o2 held-out | AUC o2 train |
|---|---|---|---|
| jev_p | 0.650 [0.614, 0.682] | 0.650 [0.613, 0.682] | 0.704 |
| trigger_kind | 0.786 [0.748, 0.820] | 0.790 [0.749, 0.826] | 0.802 |
| streak (neg) | 0.636 [0.598, 0.673] | 0.635 [0.598, 0.672] | 0.779 |
| record_class | 0.852 [0.819, 0.878] | 0.852 [0.816, 0.881] | 0.510 |
| fills_or_settles | 0.353 [0.322, 0.383] | 0.350 [0.320, 0.379] | 0.428 |
| any_new_evidence | 0.388 [0.351, 0.426] | 0.384 [0.344, 0.420] | 0.465 |
| prev_outcome | 0.712 [0.683, 0.741] | 0.711 [0.678, 0.742] | 0.757 |
| deterministic_model | 0.859 [0.829, 0.883] | 0.860 [0.828, 0.885] | 0.830 |
| det_model+jev | 0.858 [0.829, 0.883] | 0.859 [0.828, 0.884] | 0.832 |

Logistic weights (standardized features, fitted on train, label o2): {"deterministic": {"kind_rate": 0.432, "log1p_streak": -0.451, "record_rate": 0.092, "fills_or_settles": -0.284, "prev_outcome_rate": 0.437, "any_new": -0.203, "log1p_hours_since_prev": 0.15}, "combined": {"kind_rate": 0.423, "log1p_streak": -0.444, "record_rate": 0.09, "fills_or_settles": -0.29, "prev_outcome_rate": 0.428, "any_new": -0.221, "log1p_hours_since_prev": 0.155, "jev_p": 0.04}}

Skip curve on the held-out window (threshold = the train quantile that skips share q of train sessions; skip when score < threshold). Columns: held-out share of sessions skipped / dollars skipped / candidates (o1) lost / replay passes (o2) lost.

| score | q=0.1 | q=0.2 | q=0.3 | q=0.4 | q=0.5 | q=0.6 | q=0.7 | q=0.8 | q=0.9 |
|---|---|---|---|---|---|---|---|---|---|
| jev_p | 1%/1%/0%/0% | 4%/3%/2%/1% | 8%/5%/3%/3% | 16%/12%/7%/7% | 21%/15%/10%/10% | 31%/25%/18%/17% | 50%/45%/31%/30% | 67%/65%/50%/51% | 84%/84%/76%/76% |
| trigger_kind | 1%/1%/1%/1% | 20%/8%/3%/2% | 40%/15%/8%/6% | 42%/19%/10%/9% | 50%/23%/12%/10% | 65%/43%/34%/32% | 75%/61%/55%/54% | 82%/66%/58%/57% | 99%/99%/95%/95% |
| prev_outcome | 0%/0%/0%/0% | 0%/0%/0%/0% | 0%/0%/0%/0% | 67%/54%/38%/38% | 67%/54%/38%/38% | 67%/54%/38%/38% | 67%/54%/38%/38% | 73%/58%/41%/40% | 77%/62%/47%/46% |
| deterministic_model | 21%/6%/1%/1% | 26%/8%/2%/1% | 29%/9%/3%/2% | 32%/11%/3%/3% | 33%/13%/4%/3% | 46%/16%/6%/5% | 53%/20%/9%/7% | 72%/50%/30%/29% | 86%/72%/61%/60% |
| det_model+jev | 21%/6%/1%/1% | 26%/8%/2%/2% | 29%/9%/3%/2% | 31%/11%/3%/2% | 33%/12%/4%/3% | 46%/16%/6%/5% | 53%/20%/9%/7% | 72%/50%/30%/29% | 86%/72%/60%/60% |

The ≥30% dollars / ≤10% replay-pass test: threshold = the one that skips the most TRAIN dollars with train o2 loss ≤ 10%, applied unchanged to held-out.

| score | threshold | train: sessions/dollars/o1/o2 skipped | held-out: sessions/dollars/o1/o2 skipped | meets ≥30% $ and ≤10% o2 on held-out? |
|---|---|---|---|---|
| jev_p | 0.11 | 22%/16%/9%/8% | 4%/3%/2%/1% | no |
| trigger_kind | 0.03831 | 23%/19%/5%/4% | 40%/15%/8%/6% | no |
| prev_outcome | 0.05515 | 0%/0%/0%/0% | 0%/0%/0%/0% | no |
| deterministic_model | 0.05264 | 47%/40%/11%/10% | 33%/12%/4%/3% | no |
| det_model+jev | 0.05223 | 46%/39%/11%/10% | 33%/11%/3%/3% | no |

### A3. F2-surviving subset: sessions of A2 that F2's rules 9-12 would still run (replayed)

n train 1345 (o1 283, o2 230, $32.97); n held-out 1228 (o1 301, o2 270, $39.05); held-out agents 178

Mean Jev p: train 0.234, held-out 0.252; share p<0.1: train 4%, held-out 1%

| score (higher = run) | AUC o1 held-out [95% agent-clustered] | AUC o2 held-out | AUC o2 train |
|---|---|---|---|
| jev_p | 0.701 [0.660, 0.732] | 0.715 [0.674, 0.748] | 0.669 |
| trigger_kind | 0.845 [0.811, 0.876] | 0.856 [0.823, 0.887] | 0.809 |
| streak (neg) | 0.789 [0.746, 0.825] | 0.789 [0.745, 0.827] | 0.767 |
| record_class | 0.887 [0.857, 0.915] | 0.885 [0.851, 0.914] | 0.526 |
| fills_or_settles | 0.221 [0.191, 0.252] | 0.215 [0.184, 0.245] | 0.290 |
| any_new_evidence | 0.482 [0.448, 0.508] | 0.475 [0.437, 0.503] | 0.470 |
| prev_outcome | 0.724 [0.687, 0.757] | 0.732 [0.695, 0.771] | 0.745 |
| deterministic_model | 0.879 [0.845, 0.907] | 0.896 [0.864, 0.925] | 0.816 |
| det_model+jev | 0.875 [0.842, 0.904] | 0.893 [0.861, 0.924] | 0.826 |

Logistic weights (standardized features, fitted on train, label o2): {"deterministic": {"kind_rate": 0.596, "log1p_streak": -0.069, "record_rate": 0.191, "fills_or_settles": -0.473, "prev_outcome_rate": 0.431, "any_new": -0.063, "log1p_hours_since_prev": 0.079}, "combined": {"kind_rate": 0.622, "log1p_streak": -0.081, "record_rate": 0.204, "fills_or_settles": -0.454, "prev_outcome_rate": 0.472, "any_new": -0.038, "log1p_hours_since_prev": 0.077, "jev_p": -0.105}}

Skip curve on the held-out window (threshold = the train quantile that skips share q of train sessions; skip when score < threshold). Columns: held-out share of sessions skipped / dollars skipped / candidates (o1) lost / replay passes (o2) lost.

| score | q=0.1 | q=0.2 | q=0.3 | q=0.4 | q=0.5 | q=0.6 | q=0.7 | q=0.8 | q=0.9 |
|---|---|---|---|---|---|---|---|---|---|
| jev_p | 5%/3%/2%/1% | 11%/10%/4%/3% | 15%/12%/6%/5% | 25%/18%/12%/10% | 39%/36%/20%/17% | 52%/54%/29%/26% | 64%/63%/40%/38% | 79%/75%/59%/58% | 90%/88%/80%/80% |
| trigger_kind | 0%/0%/0%/0% | 41%/16%/4%/3% | 41%/16%/4%/3% | 41%/16%/4%/3% | 61%/31%/12%/9% | 76%/52%/46%/41% | 93%/87%/81%/80% | 93%/87%/81%/80% | 97%/97%/89%/89% |
| prev_outcome | 0%/0%/0%/0% | 0%/0%/0%/0% | 0%/0%/0%/0% | 67%/52%/35%/32% | 67%/52%/35%/32% | 67%/52%/35%/32% | 73%/58%/44%/41% | 73%/58%/44%/41% | 100%/100%/100%/100% |
| deterministic_model | 43%/16%/3%/2% | 45%/16%/4%/3% | 48%/19%/4%/3% | 56%/27%/7%/5% | 62%/32%/10%/7% | 64%/33%/11%/8% | 65%/36%/14%/11% | 79%/59%/41%/38% | 92%/82%/79%/77% |
| det_model+jev | 47%/19%/4%/3% | 48%/19%/4%/3% | 50%/20%/5%/3% | 57%/27%/7%/5% | 62%/32%/10%/7% | 64%/32%/11%/8% | 65%/33%/11%/9% | 79%/59%/42%/39% | 90%/81%/76%/74% |

The ≥30% dollars / ≤10% replay-pass test: threshold = the one that skips the most TRAIN dollars with train o2 loss ≤ 10%, applied unchanged to held-out.

| score | threshold | train: sessions/dollars/o1/o2 skipped | held-out: sessions/dollars/o1/o2 skipped | meets ≥30% $ and ≤10% o2 on held-out? |
|---|---|---|---|---|
| jev_p | 0.13 | 17%/13%/10%/9% | 7%/5%/3%/2% | no |
| trigger_kind | 0.1284 | 51%/38%/11%/10% | 61%/31%/12%/9% | yes |
| prev_outcome | 0.0706 | 0%/0%/0%/0% | 0%/0%/0%/0% | no |
| deterministic_model | 0.1319 | 56%/44%/12%/10% | 63%/32%/11%/8% | yes |
| det_model+jev | 0.1244 | 53%/42%/11%/10% | 63%/32%/10%/7% | yes |

F2 drop (A2 minus A3), held-out: 1469 sessions, $59.58, o1 329, o2 303; mean Jev p 0.23 vs 0.25 on the survivors
