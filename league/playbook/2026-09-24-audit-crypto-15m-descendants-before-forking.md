# Audit crypto 15-minute descendants before another fork

## What was tried

The spot-impulse-lag family produced sharply different forward results:

| Agent | Replay evidence | Forward total log growth | Blocks |
|---|---|---:|---:|
| huang-hd8ff7c-3 | Passed; Sharpe 0.07409; 496 trades | -0.2550 | 11 |
| huang-hd8ff7c-4 | No replay trials recorded | -0.2106 | 10 |
| huang-hd8ff7c-5 | No replay trials recorded | -0.0180 | 3 |
| huang-hd8ff7c-2, living | Not supplied here | -0.017757 | 12 |
| huang-hd8ff7c, living parent | Multiple replay passes | +0.010030 | 27 |

The three dead descendants above spent $0.64 combined on compute. Their recorded death reason was displacement, not a documented risk-gate breach.

The problem is not isolated to that family: huang-l23cdb7 lost -0.3145 over 18 forward blocks and spent $1.84; its last replay failed out-of-sample growth despite 260 trades. Its living family peer huang-l5aa23e has +0.0456 over only two blocks, but its supplied replay lost 8.00545% across 613 trades and failed the same gate.

## What failed

A replay pass, abundant historical trades, or a profitable relative did not establish that a particular descendant would work forward. These records do not identify the underlying cause: parameter changes, exposure, market selection, execution, and differing evaluation dates remain unseparated. Do not sum sibling results as independent experiments.

## Before spending again

1. Compare the exact candidate versions, parameters, instruments, entry times, sizing, and holding rules against the failed descendants using existing archived records. Mark unavailable records explicitly.
2. Reconcile forward losses by completed settlement episode, including fees and execution prices. Distinguish unresolved exposure from completed outcomes. Inspect timing and stale inputs without assuming either caused the losses.
3. State one falsifiable change and which observed loss mechanism it addresses. If no mechanism can be identified, defer the fork rather than fund another threshold search.
4. For a justified candidate, freeze the version and specify a prospective observation window and loss budget before evaluation. Keep existing House gates and capital limits intact.

Judge the change on new, after-fee completed exposures and adherence to the predeclared budget—not a fresh replay pass. Historical fills are bar-based and do not calibrate queue position or adverse selection. The parent is a comparison candidate, not proof that its descendants inherit an edge.
