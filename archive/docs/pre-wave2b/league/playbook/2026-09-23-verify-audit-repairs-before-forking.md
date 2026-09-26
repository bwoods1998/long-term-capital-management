# Verify audit repairs before funding descendants

## What happened

The crypto-alts-reversion lineage repeatedly carried a defect already identified by audit:

| Agent | Evidence | Outcome |
| --- | --- | --- |
| haghani | 14 replay trials; $6.99 compute; 30 forward blocks; +0.0357 total log growth | Superseded for `audit_veto:haghani` |
| haghani-40 | Last replay: Sharpe -0.094337, 606 trades, marked passed; zero forward blocks | Superseded for the same defect |
| haghani-41 | Last replay: Sharpe -0.102820, 601 trades, marked passed; zero forward blocks | Superseded for the same defect |
| haghani-42 | Last replay: four closed trades versus ten required; no active out-of-sample block; zero forward blocks | Superseded for the same defect |

All four post-mortems name `haghani_downward_entry` (haghani-34) as the correction. The supplied records do not expose the faulty code, so they do not establish the exact faulty predicate or how it propagated.

The corrected candidate was not an economic success: haghani-34's one replay had 438 trades, Sharpe -0.078587 and deflated Sharpe 0.000256; out-of-sample growth was not above zero. It had no forward blocks and was displaced.

## What failed

Development replay acceptance did not establish that an inherited audit defect was removed. Positive forward growth from the defective parent did not validate its correctness either. Conversely, the named repair did not establish profitability.

These are separate obligations: **remove the defect, then judge the corrected strategy on its own evidence**.

## Before spending again

1. Read the proposed parent's supersession and audit records. Record the applicable repair key and the exact artifact proposed for testing.
2. Inspect whether that artifact contains the identified correction. A new agent name, generation or replay pass is not proof.
3. Specify a defect-specific regression case using the audit's actual failing condition. Demonstrate that the defective parent fails and the proposed child passes. If the condition cannot be recovered from available records, request the audit detail rather than inventing it or buying another economic replay.
4. Keep the regression result separate from return evidence. Do not transfer the parent's +0.0357 log growth to the repaired child or treat haghani-34's correction as a profitable signal.

## Checkable outcome

The next funded descendant of an audit-vetoed artifact should have a recorded parent-fails/child-passes regression result tied to the submitted artifact. A descendant superseded for the same unremoved defect is a failure of this procedure, even if its development replay passed. Repair verification does not waive any replay, forward-risk or promotion gate.
