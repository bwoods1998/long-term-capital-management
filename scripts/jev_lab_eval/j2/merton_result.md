## Part B results (Merton)

### B1. Passes by role, Sept 22 00:00Z - Sept 25 06:00Z

| role | passes | $ | errors | produced an artifact | downstream yield | 'nothing' passes | $ on 'nothing' | train / held-out passes |
|---|---|---|---|---|---|---|---|---|
| consultant | 112 | 59.25 | 7 | 89 | 30 | 23 | 9.01 | 35 / 77 |
| architect | 54 | 44.18 | 5 | 11 | 10 | 43 | 31.77 | 44 / 10 |
| engineer | 207 | 28.10 | 2 | 52 | 49 | 155 | 16.98 | 108 / 99 |
| teacher | 38 | 16.85 | 0 | 27 | 27 | 11 | 4.35 | 30 / 8 |
| foundry | 43 | 11.45 | 7 | 36 | 36 | 7 | 1.10 | 30 / 13 |
| toolsmith | 15 | 7.01 | 0 | 1 | 1 | 14 | 6.25 | 13 / 2 |
| operator | 22 | 5.21 | 0 | 0 | 0 | 22 | 5.21 | 18 / 4 |
| designer | 6 | 2.73 | 0 | 0 | 0 | 6 | 2.73 | 5 / 1 |
| auditor (audit.verdict) | 20 | 4.29 | - | 5 approvals | - | - | - | not asked (a refusal is a product) |

Consultant detail: {"code": 27, "no code": 13, "code + candidate + replay passed": 30, "code + candidate": 15, "no code + candidate + replay passed": 1, "code + replay passed": 17, "no code + replay passed": 7, "no code + candidate": 2}
Engineer later repair states (within 24 h) for passes that opened a PR: {"canary,observing,patching,rejected,reproducing,revising,testing": 1, "canary,observing,patching,reproducing,revising,testing,verified": 1, "canary,observing,testing,verified": 1, "canary,observing,testing": 41, "canary,dormant,observing,patching,reproducing,revising,testing": 1, "canary,observing,patching,reproducing,revising,testing": 4, "dormant,patching,reproducing,revising,testing": 2, "testing": 1}

### B2. All roles: label `nothing` (1 = the pass produced nothing)

train n 283 (176 nothing, $98.67); held-out n 214 (105 nothing, $76.11)

| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |
|---|---|---|
| m1_nothing | 0.623 | 0.501 [0.413, 0.582] |
| m2_missing | 0.525 | 0.345 [0.260, 0.431] |
| m3_house | 0.524 | 0.411 [0.345, 0.482] |
| m4_strategy | 0.535 | 0.567 [0.467, 0.667] |
| m5_known | 0.673 | 0.736 [0.649, 0.810] |
| role (train rate) | 0.823 | 0.771 [0.689, 0.839] |
| engineer: attempt>1 or an earlier empty pass on the key | 0.499 | 0.482 [0.456, 0.504] |
| consultant: agent consulted before | 0.470 | 0.350 [0.288, 0.426] |
| request mentions missing data (regex) | 0.489 | 0.491 [0.471, 0.514] |

Question chosen on train: `m5_known` (train AUC 0.673).
Role + `m5_known` logistic (weights [1.467, -0.126]): held-out AUC 0.787 [0.698, 0.870]

Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):

| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |
|---|---|---|---|---|
| m5_known | 0.65 | 18%/8%, 9% | 20%/11%, 12% | $8.13 |
| role (train rate) | 0.811 | 28%/48%, 7% | 8%/16%, 4% | $12.11 |
| role + jev (logistic) | 0.788 | 29%/48%, 9% | 11%/17%, 4% | $12.57 |

### B2. All roles: label `no_yield` (1 = the pass produced nothing)

train n 283 (197 nothing, $98.67); held-out n 214 (147 nothing, $76.11)

| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |
|---|---|---|
| m1_nothing | 0.656 | 0.581 [0.490, 0.672] |
| m2_missing | 0.589 | 0.469 [0.365, 0.564] |
| m3_house | 0.511 | 0.449 [0.363, 0.527] |
| m4_strategy (flipped on train) | 0.574 | 0.612 [0.504, 0.696] |
| m5_known | 0.652 | 0.569 [0.491, 0.649] |
| role (train rate) | 0.816 | 0.562 [0.443, 0.666] |
| engineer: attempt>1 or an earlier empty pass on the key | 0.496 | 0.473 [0.435, 0.501] |
| consultant: agent consulted before | 0.541 | 0.479 [0.418, 0.532] |
| request mentions missing data (regex) | 0.510 | 0.520 [0.507, 0.536] |

Question chosen on train: `m1_nothing` (train AUC 0.656).
Role + `m1_nothing` logistic (weights [1.418, -0.078]): held-out AUC 0.549 [0.418, 0.662]

Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):

| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |
|---|---|---|---|---|
| m1_nothing | 0.41 | 14%/17%, 8% | 9%/11%, 3% | $8.20 |
| role (train rate) | 0.847 | 28%/48%, 8% | 8%/16%, 6% | $12.11 |
| role + jev (logistic) | 0.857 | 33%/50%, 9% | 34%/57%, 40% | $43.10 |

### B3. consultant only: label `nothing` (1 = the pass produced nothing)

train n 35 (11 nothing, $16.75); held-out n 77 (12 nothing, $42.50)

| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |
|---|---|---|
| m1_nothing | 0.712 | 0.740 [0.505, 0.935] |
| m2_missing | 0.633 | 0.571 [0.353, 0.803] |
| m3_house | 0.761 | 0.609 [0.415, 0.769] |
| m4_strategy | 0.792 | 0.596 [0.413, 0.766] |
| m5_known (flipped on train) | 0.739 | 0.423 [0.244, 0.626] |
| role (train rate) | 0.500 | 0.500 [0.500, 0.500] |
| engineer: attempt>1 or an earlier empty pass on the key | 0.500 | 0.500 [0.500, 0.500] |
| consultant: agent consulted before | 0.564 | 0.450 [0.256, 0.584] |
| request mentions missing data (regex) | 0.483 | 0.553 [0.455, 0.637] |

Question chosen on train: `m4_strategy` (train AUC 0.792).
Role + `m4_strategy` logistic (weights [0.0, 0.944]): held-out AUC 0.596 [0.413, 0.766]

Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):

| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |
|---|---|---|---|---|
| m4_strategy | 0.58 | 17%/15%, 8% | 4%/3%, 3% | $1.14 |
| role (train rate) | inf | 0%/0%, 0% | 0%/0%, 0% | $0.00 |
| role + jev (logistic) | 0.498 | 17%/15%, 8% | 4%/3%, 3% | $1.14 |

### B3. consultant only: label `no_yield` (1 = the pass produced nothing)

train n 35 (30 nothing, $16.75); held-out n 77 (52 nothing, $42.50)

| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |
|---|---|---|
| m1_nothing | 0.720 | 0.744 [0.645, 0.851] |
| m2_missing | 0.680 | 0.503 [0.344, 0.633] |
| m3_house | 0.650 | 0.594 [0.461, 0.717] |
| m4_strategy | 0.600 | 0.453 [0.317, 0.589] |
| m5_known (flipped on train) | 0.573 | 0.473 [0.320, 0.640] |
| role (train rate) | 0.500 | 0.500 [0.500, 0.500] |
| engineer: attempt>1 or an earlier empty pass on the key | 0.500 | 0.500 [0.500, 0.500] |
| consultant: agent consulted before | 0.767 | 0.459 [0.361, 0.549] |
| request mentions missing data (regex) | 0.567 | 0.558 [0.521, 0.594] |

Question chosen on train: `m1_nothing` (train AUC 0.720).
Role + `m1_nothing` logistic (weights [0.0, 0.389]): held-out AUC 0.744 [0.645, 0.851]

Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):

| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |
|---|---|---|---|---|
| m1_nothing | 0.79 | 3%/1%, 0% | 0%/0%, 0% | $0.00 |
| role (train rate) | inf | 0%/0%, 0% | 0%/0%, 0% | $0.00 |
| role + jev (logistic) | 0.956 | 3%/1%, 0% | 0%/0%, 0% | $0.00 |

### B3. engineer only: label `nothing` (1 = the pass produced nothing)

train n 108 (81 nothing, $13.36); held-out n 99 (74 nothing, $14.74)

| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |
|---|---|---|
| m1_nothing (flipped on train) | 0.572 | 0.644 [0.506, 0.793] |
| m2_missing | 0.543 | 0.401 [0.208, 0.570] |
| m3_house (flipped on train) | 0.737 | 0.788 [0.652, 0.905] |
| m4_strategy (flipped on train) | 0.699 | 0.688 [0.537, 0.819] |
| m5_known | 0.556 | 0.386 [0.258, 0.528] |
| role (train rate) | 0.500 | 0.500 [0.500, 0.500] |
| engineer: attempt>1 or an earlier empty pass on the key | 0.481 | 0.394 [0.313, 0.484] |
| consultant: agent consulted before | 0.500 | 0.500 [0.500, 0.500] |
| request mentions missing data (regex) | 0.500 | 0.500 [0.500, 0.500] |

Question chosen on train: `m3_house (flipped on train)` (train AUC 0.737).
Role + `m3_house (flipped on train)` logistic (weights [0.0, 0.638]): held-out AUC 0.788 [0.652, 0.905]

Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):

| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |
|---|---|---|---|---|
| m3_house (flipped on train) | 0.97 | 27%/17%, 7% | 12%/7%, 4% | $1.10 |
| role (train rate) | inf | 0%/0%, 0% | 0%/0%, 0% | $0.00 |
| role + jev (logistic) | 0.821 | 27%/17%, 7% | 12%/7%, 4% | $1.10 |

### B3. engineer only: label `no_yield` (1 = the pass produced nothing)

train n 108 (82 nothing, $13.36); held-out n 99 (76 nothing, $14.74)

| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |
|---|---|---|
| m1_nothing (flipped on train) | 0.574 | 0.619 [0.484, 0.778] |
| m2_missing | 0.549 | 0.400 [0.206, 0.560] |
| m3_house (flipped on train) | 0.746 | 0.769 [0.620, 0.891] |
| m4_strategy (flipped on train) | 0.718 | 0.662 [0.515, 0.795] |
| m5_known | 0.552 | 0.384 [0.268, 0.507] |
| role (train rate) | 0.500 | 0.500 [0.500, 0.500] |
| engineer: attempt>1 or an earlier empty pass on the key | 0.480 | 0.411 [0.318, 0.505] |
| consultant: agent consulted before | 0.500 | 0.500 [0.500, 0.500] |
| request mentions missing data (regex) | 0.500 | 0.500 [0.500, 0.500] |

Question chosen on train: `m3_house (flipped on train)` (train AUC 0.746).
Role + `m3_house (flipped on train)` logistic (weights [0.31, 0.665]): held-out AUC 0.769 [0.620, 0.891]

Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):

| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |
|---|---|---|---|---|
| m3_house (flipped on train) | 0.97 | 27%/17%, 8% | 12%/7%, 4% | $1.10 |
| role (train rate) | inf | 0%/0%, 0% | 0%/0%, 0% | $0.00 |
| role + jev (logistic) | 0.831 | 27%/17%, 8% | 12%/7%, 4% | $1.10 |
