# A passing critic can miss the net effect

The final bounded-planning proof produced a valid report, and its Kimi critic
passed it. Independent review still found a problem: the draft highlighted growing
cash contributions from accounts payable and unearned revenue without weighing
the offsetting lines in the full reconciliation. The report remains unpublished.

The source is Microsoft's unaudited annual cash flow statement. The
[checked audit](../data/research/working-capital-audit.json) records all nine changes
in operating assets and liabilities, their exact source passages, and the frozen
source hash. This includes long-term items; it is broader than current working
capital. [Microsoft financial results](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast)

| Change from FY2025 to FY2026 | USD millions |
|---|---:|
| Accounts payable contribution | +4,699 |
| Unearned revenue contribution | +3,923 |
| Other seven contributions combined | −8,167 |
| Net improvement across all nine lines | **+455** |
| Total operating cash flow increase | **+46,773** |

The two positive components are real, but their combined improvement is mostly
offset elsewhere. The full group remained a net cash use: $4,895 million versus
$5,350 million. Those cash-flow adjustments also differ from simply subtracting
one year's balance-sheet balances from another's.

The draft needs two other qualifications. Cash PP&E excludes noncash finance-lease
additions; that does not mean the entire evidence set excludes information about
leases. A strong future cash-flow period could strengthen confidence in durability,
but it would not conclusively establish persistent or AI-specific returns.

## Reproduce the arithmetic without an API call

Run this from the repository root, then compare the rows with the original annual
columns. The same statement also contains quarterly figures, so column selection
matters.

```sh
python3 - <<'PY'
from decimal import Decimal
import json
from pathlib import Path

audit = json.loads(Path('data/research/working-capital-audit.json').read_text())
totals = {year: sum(Decimal(row[year]) for row in audit['rows'])
          for year in audit['periods']}
print(totals)
print('Net change:', totals['FY2026'] - totals['FY2025'], audit['unit'])
PY
```

Then write a two-sentence replacement summary. Preserve the observed improvement,
the offsets, and what remains unknown. That is a more useful review exercise than
counting only well-formed outputs.

This editorial audit does not rewrite the model's frozen report, critic verdict,
or measured cost. The planning change demonstrated completion of required steps;
it did not establish reliable substantive review.
