# Fast lane screen benchmark 1 (fast_lane_screen_1)

Run 2026-10-07T17:10:08+00:00 on tree e67907ce9806deddad7d3e13819a8bf7ea042e62 (receipt hashes verified). Acceptance: In every null world (gauss, t3, skew, ar, mid), the floor-eligible per-program false-positive rate's exact one-sided 95% upper bound (Clopper-Pearson, league.stats.exact_upper) is at most 2%. If it holds, the constants ship. If any world fails, MIN_T is raised by 0.1, a new receipt is frozen and the run is made again, until it holds. A result never loosens a constant.

**Verdict: ACCEPTED: the constants ship.**

Input: 601 distinct programs (350 floor-eligible) in 288 lineages (193 with a floor-eligible program; the largest holds 14).

## False positives (no-edge programs that reach Validation and pass the screen)

| Null world | Screen, eligible (95% upper) | Screen, all | Validation alone | Look given Validation | Per lineage (<= 3 looks) | Today's rule |
|---|---|---|---|---|---|---|
| gauss | 0.49% (0.59%) | 0.29% | 4.71% | 10.32% | 0.89% | 0.05% |
| t3 | 0.51% (0.62%) | 0.30% | 4.57% | 11.09% | 0.91% | 0.03% |
| skew | 0.23% (0.31%) | 0.14% | 3.16% | 7.24% | 0.44% | 0.03% |
| ar | 1.19% (1.36%) | 0.70% | 8.19% | 14.57% | 2.15% | 0.10% |
| mid | 0.18% (0.25%) | 0.10% | 2.19% | 8.14% | 0.31% | 0.01% |

Per lineage, the largest lineage's rate: gauss 6.25% (14 programs); t3 5.00% (14 programs); skew 3.75% (14 programs); ar 12.50% (14 programs); mid 3.75% (14 programs).

drift_only (direction profit, reported, never a bar): screen 2.14%, Validation 10.89%, today's rule 0.07%.

## Power (floor-eligible, planted all-days yearly Sharpe)

| Sharpe | Screen | Validation alone | Today's rule |
|---|---|---|---|
| 1 | 8.31% | 24.69% | 0.69% |
| 2 | 40.09% | 60.09% | 10.69% |
| 3 | 77.71% | 88.86% | 44.29% |

## The cost of each kept check (removed in turn): floor-eligible false positives in each null world, and power

| Removed | FP gauss | FP t3 | FP skew | FP ar | FP mid | Power S1 | Power S2 | Power S3 |
|---|---|---|---|---|---|---|---|---|
| t | 0.50% | 0.77% | 0.27% | 1.22% | 0.19% | 8.51% | 40.31% | 77.77% |
| dsr | 0.52% | 0.54% | 0.23% | 1.29% | 0.22% | 8.83% | 41.29% | 78.43% |
| quarters | 0.49% | 0.51% | 0.23% | 1.19% | 0.18% | 8.34% | 40.14% | 77.74% |
| stress | 0.49% | 0.53% | 0.23% | 1.21% | 0.18% | 8.51% | 40.74% | 78.20% |
| mean | 0.49% | 0.51% | 0.23% | 1.19% | 0.18% | 8.31% | 40.09% | 77.71% |
| look_pnl | 0.49% | 0.51% | 0.23% | 1.19% | 0.18% | 8.31% | 40.09% | 77.71% |
| look_sharpe | 0.49% | 0.52% | 0.23% | 1.24% | 0.18% | 8.49% | 41.66% | 81.49% |

## Volume and dollars

- Programs validated in the snapshot's last 7 days: 435 (287 floor-eligible).
- If all were no-edge, at the worst null world's rates: 23.5 false Validation passes and 3.42 false Probes a week.
- A demoted false Probe loses about 3 x its maximum loss: $120-375 for $40-125 tickets; the $400 budget covers 1-3 demotions; false Probes could cost $410.82-1283.81 a week.

## The look's own size at 0.10 (no edge, 184 sessions)

- ar: P(p <= 0.10) 11.92%, P(p <= 0.05) 6.70%, P(lcb95 > 0) 6.70% (n 6000).
- gauss: P(p <= 0.10) 10.83%, P(p <= 0.05) 5.72%, P(lcb95 > 0) 5.72% (n 6000).
- sparse: P(p <= 0.10) 8.72%, P(p <= 0.05) 4.25%, P(lcb95 > 0) 4.25% (n 6000).

## Contamination

Stated, not measured: 123 of the holdout's 184 sessions (through 2026-06-30) are inside the training of Opus 5.5 (cutoff June 2026); the cutoffs of DeepSeek-V4-Flash (about 93% of versions), Kimi-K3 and GPT-6 Astra are unknown. A synthetic benchmark cannot measure it. Every look carries its 61-session tail from 2026-07-01 beside it (numbers.tail), weak in power and never a bar.

The tail look's power (normal approximation, level 0.10, an every-session program): Sharpe 1: 21.49% on the 61-session tail, 33.47% on the 184-session look; Sharpe 2: 38.30% on the 61-session tail, 66.55% on the 184-session look; Sharpe 3: 57.71% on the 61-session tail, 90.01% on the 184-session look.
