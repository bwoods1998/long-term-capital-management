# Explore or reproduce

[Open the project](https://blakewoods.us/portfolio/). Pick a company, switch periods, and try a different cash-generation or capital-spending assumption. The sliders are sensitivities, not forecasts.

The basic question is **how much operating cash remains after the company’s stated capital deductions?** It does not isolate AI profitability. Other cash uses can sit outside that calculation.

## Reproduce the nine cash bridges

A public clone and Python 3.10+ are enough. No key, paid request or private database is needed:

```sh
python3 - <<'PYTHON'
import json
from decimal import Decimal as D
with open('public/cash-map.json') as source:
    companies = json.load(source)['companies']
for c in companies:
    for prefix in ('', 'prior_'):
        cash = D(c[prefix + 'operating_cash'])
        spending = sum(D(d['prior_value' if prefix else 'value']) for d in c['deductions'])
        assert cash - spending == D(c[prefix + 'cash_remaining'])
    print(c['symbol'], c['period'], c['currency'], c['cash_remaining'], 'million')
PYTHON
```

All 18 bridges must balance. Each company’s JSON record includes its primary source and accounting definition. [Read the financial context](AI-STACK.md).

## Read the agent’s result

The [latest experiment](NIGHT-SHIFT.md) preserves first drafts, critics, revisions and checks. Public files contain typed measurements; private model drafts are not included in a clone. The website loads saved data and cannot start paid work.

## Work on the code

Run `python3 -m unittest discover -s tests -v` for the offline tests. The [technical reference](README.md) links architecture, setup and operations. Executing new research requires your own Sail key and an explicit budget; inspection commands do not create missing private history.
