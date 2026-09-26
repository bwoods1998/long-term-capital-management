# Reconcile altcoin execution before more mutations

## What the records show

The crypto-alts-reversion family has conflicting evidence:

- **haghani:** forward log growth **+0.023151 over 23 blocks**. Its promotion-hold record reports **21 active blocks, 23 trades**, mean **0.00100657**, and lower confidence bound **-0.00062025**. Positive cumulative growth is not a positive lower bound.
- Three supplied haghani replays returned **-42.58%, -34.37%, and -34.98%**, with **540, 552, and 555 trades**. All failed out-of-sample growth and the deflated-Sharpe gate.
- The current pre-audit is **red**, flagging **cent_rounding**, for code hash `8d50f78b06f166798fd503b43ba754205cf9c0be1bb1f752758c5631093b7eae`. The promotion process is in **audit_cooldown**.
- Dead descendants **haghani-27** and **haghani-28** had **230/224 replay trades**, Sharpe **-0.0464/-0.0517**, and deflated Sharpe **0.00339/0.00220**. They spent **$0.25/$0.26**, produced no forward blocks, and were displaced. Their replay failures were not small-sample failures.

## What this does—and does not—establish

The incumbent's forward result does not validate descendants. Conversely, these replays do not prove that its forward accounting is wrong: code versions, periods, and execution assumptions are not matched in the supplied records. The rounding flag is a concrete audit lead, not a demonstrated explanation for the losses.

## Before spending on another edge-search mutation

1. Attach the audited code hash, configuration, symbols, periods, and execution assumptions to the forward and replay records. Mark unmatched results as unmatched; do not compare them as a controlled experiment.
2. Inspect the flagged rounding path using archived orders and fills where available. Compare intended quantity, submitted quantity, venue precision, filled notional, fees, residual inventory, and resulting cash/P&L. Establish the expected rounding behavior rather than guessing a fix from the flag name.
3. Separate accounting discrepancies from market-period differences and simulated-fill assumptions. Replay uses bar-based fills and lacks historical queue-position/adverse-selection calibration; do not assume those fills reproduce forward execution.
4. Resolve or document the defect before requesting another production audit, and respect the recorded cooldown. Repeating an unchanged audit or cloning the strategy supplies no reconciliation evidence.

## How to judge the next step

Produce a version-matched reconciliation with explicit residual discrepancies. If code changes, record the new hash and obtain the required audit clearance; do not relabel the old positive forward record as evidence for the repair. Any subsequent forward evaluation remains subject to existing gates. No capital increase is justified by this discrepancy alone.
