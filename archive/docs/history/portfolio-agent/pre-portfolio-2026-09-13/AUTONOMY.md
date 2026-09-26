# Improving the research method

The aim is routine progress without someone approving each source read or model
request. The first improvement loop changes a **claim-level evidence-critic
prompt**. It cannot edit code, modify its tests, increase spending limits, publish
research, or place orders.

## First live result — September 13, 2026 UTC

The loop generated a candidate and **automatically rejected it**. It fixed one
missing-evidence verdict but introduced a cash-classification error: subtracting
lease interest already included in operating cash flow. The current prompt stayed
in place. Recorded decision (`experiments/public/self-improvement.json`)

| Full-pass checks | Current prompt | Candidate |
|---|---:|---:|
| Development | 8 / 8 | 8 / 8 |
| Separate validation | 7 / 8 | 7 / 8 |

The 33 logical calls, including candidate generation, cost an estimated
**$0.00380476**. The candidate gained on one validation case and regressed on
another; equal aggregate scores did not hide the regression. This is a verified
selection-loop result, not a demonstrated improvement in the critic.

The development set was already saturated. A future protocol can stop that
futile promotion attempt earlier; this run kept its original comparison plan.
Its consumed validation cases cannot select another candidate.

```text
Current prompt → Development results → One proposed prompt
                                            ↓
                         Paired development + validation checks
                                            ↓
                             Promote or keep the current prompt
```

## One bounded cycle

1. Freeze the current prompt, model/profile, source cases, grading code, deadline,
   and allowance. The baseline is the existing evidence-critic prompt.
2. Run eight development cases. Generate one candidate from those cases and the
   baseline's recorded results. The generator does not receive validation cases.
3. Compare the frozen candidate and baseline on development and eight separately
   authored validation cases. Validation request order alternates the two prompts.
4. Promote only with **no full-pass regressions and at least one gain in each
   set**. Unknown accounting or a changed current prompt blocks promotion.
   Otherwise retain the current prompt and record why.

The default uses DeepSeek V4 Flash ASAP through Sail. Thirty-two evaluations plus
one proposal reserve at most **$3.30** inside the shared inference ledger. Each
request keeps its original identity through recovery; invalid results do not
silently buy replacement attempts. Promotion and rollback append records rather
than deleting history.

## What the measurement means

The sixteen cases are fictional financial-evidence exercises: arithmetic, dates,
currencies, cash classification, missing disclosures, and related-company
spending. They are distinct from the earlier Microsoft development set.

Grading checks the verdict, output contract, eligible citation IDs, and authored
required evidence groups. It does not establish arbitrary explanation semantics,
market forecasting skill, or robustness on unseen filings. The fixtures are
public and authored by the project; they are not a secret external benchmark.
One validation set can select only one candidate. Further attempts require
fresh validation evidence, not repeated tuning against the same answers.

The selected prompt is available through `build_current_claim_request()` for
new claim audits. It is **not** the full investigator's differently structured
report critic. A successful prompt experiment does not approve a company case or
change model weights.

## Inspect and resume

The public [current state](CURRENT-STATE.md) records what actually ran. Private
commands use the existing Sail setup and ledger:

```bash
# Freeze one campaign without submitting inference.
.venv/bin/python self_improve.py start --key critic-v1 --deadline YYYY-MM-DDTHH:MM:SSZ

# Resume that same ID. This can spend within the frozen allowance.
.venv/bin/python self_improve.py run CYCLE_ID --seconds 600
.venv/bin/python self_improve.py status CYCLE_ID
.venv/bin/python self_improve.py champion
```

The controller stops at a decision, invalid proposal, or deadline. It is not an
installed always-on scheduler. [Sailbox execution](CLOUD-WORKER.md), source
monitoring, method selection, and publication remain distinct components; joining
them into a hosted agent is the next integration step.
