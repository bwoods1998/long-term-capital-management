# Read the whole cash-flow bridge

This dossier asks a financial question: **Does Microsoft's reported growth support
confidence in durable cash generation from its infrastructure investment?**
The rubric (`experiments/data/research/dossier-rubric.json`) contains 64 numerical checks across
cash flow, investment, and demand. Its sources are two public Microsoft disclosures
dated July 29, 2026, captured in September. They contain company-wide results and
management commentary, not an AI-only investment return.

The exercises below only read committed files. Predict first, then run the code.

## 1. Profit grew. Where did the cash-flow increase come from?

Start with the nine-row audit (`experiments/data/research/working-capital-audit.json`).
Accounts payable and unearned revenue contributed more cash than in the prior
year. Before calculating, predict whether the **whole** operating asset/liability
group supplied cash or consumed it. Does the change in those two rows explain
most of the increase in operating cash flow?

Use the annual columns, not the adjacent quarter. This group includes long-term
items, so calling it only current working capital would narrow its actual scope.
These are cash-flow adjustments, not simple differences between balance-sheet
balances. [Microsoft cash-flow statements](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast)

Now reconcile the full bridge. Net income is the starting point; four adjustment
categories and the nine-row group reconcile it to operating cash flow.

```sh
python3 - <<'PY'
import json
from decimal import Decimal as D
r = json.load(open('data/research/dossier-rubric.json'))
value = lambda key: D(r['expected'][key]['value'])
for check in r['reconciliation_checks']:
    print('\n' + check['id'], '(USD millions)')
    for key in check['right_metrics']:
        print(key, value(key))
    print('Sum:', sum(value(key) for key in check['right_metrics']))
    print('Reported:', value(check['left_metric']))
PY
```

Explain which contributors dominate the arithmetic change. Then separate
**reconciliation** from **persistence**: an investment-gain reversal, deferred-tax
adjustment, or depreciation add-back is not evidence that the same cash benefit
will recur. Stock compensation is added back in this cash reconciliation; it
does not thereby become economically free.

The key check: the nine-row group improved by $455 million while total operating
cash flow increased by $46,773 million. Write two sentences that retain the
positive payable/unearned-revenue contributions **and** their offsets.
[Checked reconciliation](../pre-portfolio-2026-09-13/REVIEW-CASE.md)

## 2. Make the investment measures coexist

Management reported quarterly capex of $41 billion, finance leases of $5.6 billion,
and cash PP&E of $35.8 billion. Add the last two. Is that an exact reconciliation?
The source does not explain the resulting difference; naming rounding as a
possible issue does not establish its cause.
[Microsoft earnings call](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4)

Inspect the requested investment measures and their distinct periods:

```sh
python3 - <<'PY'
import json
r = json.load(open('data/research/dossier-rubric.json'))
for metric in r['tasks']['investment']['metrics']:
    answer = r['expected'][metric['id']]
    print(metric['id'], answer['value'], answer['unit'], answer['period'])
PY
```

Explain why annual cash PP&E, quarterly finance leases, calendar-year guidance,
and a useful-life change effective the next fiscal year cannot be casually added
together. Cash PP&E is shown positive as spending in the dossier, although the
statement reports an outflow. Operating cash flow less that spending is a defined
company-wide cash remainder, not a complete measure of infrastructure commitments.

Name the additional lease and commitment disclosures needed for a complete bridge.
Keep management's investment outlook distinct from observed construction activity.

## 3. Audit the answer, not just its score

| Check | What to inspect |
|---|---|
| Schema | Did the response provide the required fields and decimal strings? |
| Numerical value | Do signs, units, periods, all rows, and calculated totals agree? |
| Provenance | Do the cited chunks contain both the column header and the relevant rows or operands? |
| Financial meaning | Does the explanation include offsets and preserve uncertainty about causes and future returns? |

In the rubric, `tasks` specifies what analysts receive; `expected` contains the
withheld answer key. `source_spans` binds citations to exact offsets and hashes.
`qualitative_rubric` lists questions for substantive review; numerical matches do
not automatically pass them.

For demand, challenge this inference: “Azure grew and contracted backlog expanded,
therefore AI investment returns are established.” Distinguish revenue, RPO,
recognition timing, cash collection, and returns. Identify the missing incremental
AI cash flows and invested-capital denominator. The defensible answer can be
“not determinable from these sources” without implying zero or negative returns.

## What the model comparison buys

The twelve-stage protocol gives Pro and Kimi independent assignments for each
theme, then reconciles each pair against the sources. Synthesis, critique, and a
revision follow. Reference values are withheld; reconciliation receives earlier
outputs and error categories. Original failures remain part of the record.

Inspect an existing dossier without advancing paid work:

```sh
python3 dossier.py status DOSSIER_ID
```

Compare missing metrics, numerical errors, citation failures, and the quality of
the corrected explanation. Agreement between models is not an independent source.
Pro uses Flex and Kimi uses ASAP, so this is not an isolated model-speed comparison.

Count every stage when assessing cost per useful dossier, including failed or
unhelpful stages. The $6.40 maximum reservation is an allowance, not the bill.
Returned-token estimates, unknown usage, and reservations remain separate. This
lesson describes the protocol; it does not claim the models have completed it or
passed substantive review.
