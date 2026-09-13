# Explore Portfolio Agent

Start with the [project page](https://blakewoods.us/portfolio/). Explore nine companies
across chips, networking, power and cooling, cloud, and applications. The question
is where AI spending becomes durable cash flow—and how much depends on the same
spending cycle. This is a research universe, not a live portfolio.

Microsoft is the first reviewed case. The other companies have source-backed
profiles; that does not mean their investment cases have been reviewed. The
[current state](CURRENT-STATE.md) distinguishes completed work from the next test.

The **Night shift** checkpoint records the nine-company research campaign:
independent cases, skeptical review, revisions, and measured costs. Its
[research notes](NIGHT-SHIFT.md) explain what ran and what still needs checking.
Passing a quote or arithmetic check does not approve a financial conclusion.

## Follow one useful finding

Open **Case** on the [project page](https://blakewoods.us/portfolio/). Change
cash-generation and investment growth to see how they affect the cash remaining
after property purchases. The baseline is Microsoft's checked FY2026 result;
the sliders change assumptions, not a forecast.

The [first case](CURRENT-CASE.md) explains the finding and what could change it.
The [full source audit](REVIEW-CASE.md) preserves the accounting detail.

## Reproduce the arithmetic locally

From a clone of this repository, use Python 3.10+ to read the committed figures:

```sh
python3 - <<'PY'
import json
from decimal import Decimal as D
with open('public/cashflow-bridge.json') as source:
    bridge = json.load(source)
change = sum(D(row['FY2026']) - D(row['FY2025']) for row in bridge['details'])
print('All nine contribution changes:', change, bridge['unit'])
print('Operating cash-flow growth:',
      D(bridge['totals']['FY2026']) - D(bridge['totals']['FY2025']), bridge['unit'])
PY
```

This returns **455** and **46,773**, respectively. It needs no API key, account,
private database, or downloaded source cache. The source dates and link are in the
same JSON file. Explain why selected positive rows would tell a different story.
Before comparing another company, check its currency, fiscal period, and definition
of cash investment; similar labels can represent different measurements.

For the code, `python3 -m unittest discover -s tests -v` runs the offline test suite.
The [optional exercises](../lessons/README.md) go deeper into cash flow, model costs,
and memory; they are not prerequisites for exploring the project.

## Build or run an agent

The [reference index](README.md) links the research runner, setup, and current roadmap.
Paid execution requires your own Sail key and an explicit budget. The repository
contains public results, not the owner's private run history. Commands in the
[operations guide](OPERATIONS.md) inspect an existing local ledger; a fresh clone
has no saved runs to resume.
