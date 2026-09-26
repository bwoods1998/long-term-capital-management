# Deposits are not returns

A public portfolio balance would be an attractive scoreboard, but it can rise
simply because you add money. Before connecting an account, this synthetic exercise
teaches the observations required to distinguish funding from performance.
All commands run locally with standard Python, without keys or network requests.

## Predict the funding-only result

Start with $100. Deposit $100, then withdraw $50. Nothing else changes. You finish
with $150. Predict dollar P&L and percentage return before inspecting:

```sh
python3 performance.py demo --case funding-only
```

Net funding is $50. P&L is $150 − $100 − $50 = $0. Return is also zero. Deposits
did not create investment profit; withdrawals did not create an investment loss.
Orders and fills are separate accounting concepts from these external flows.

To calculate returns, knowing just the final balance and total deposits is
insufficient. We need an equity valuation immediately before and after each flow.
The difference between those two values must exactly match that funding amount.
Without both observations, the calculator refuses to invent a result.

## Chain growth across funding boundaries

The combined fixture follows this path:

| Event | Equity |
|---|---:|
| Start | $100 |
| Grow before deposit | $110 |
| Deposit $100 | $210 |
| Grow before withdrawal | $231 |
| Withdraw $50 | $181 |
| Pay $2 portfolio fee; finish | $179 |

The three growth factors are 110/100, 231/210, and 179/181. Multiply them and
subtract one. Predict whether the result equals the 79% raw balance increase:

```sh
python3 performance.py demo --case growth-and-funding
```

The time-weighted return is about 19.663%, while dollar P&L is $29. Those answer
different questions. The fictional benchmark rises 5%, then 5%, then stays flat:
its chained return is 10.25%, not 10%. The difference is about 9.413 percentage
points. This three-day example says nothing about real investment skill.

## Account for costs once

```sh
python3 performance.py demo --case fees-only
```

A portfolio starting at $100 and ending at $98 after a $2 fee has a −2% return.
Subtracting that fee again would be wrong: the observed equity already includes
it. The separate $3 research API expense was paid outside the portfolio; it belongs
on the project's operating-cost ledger. It does not turn portfolio return into −5%.

Finally, edit a **copy** of the fixture in Python memory: remove a pre-deposit
valuation, or shift a benchmark observation by one minute, then call
`performance.calculate(case)`. Explain why each must fail before trying it. A
benchmark from another period can produce a persuasive but invalid comparison.

The [performance contract](../pre-portfolio-2026-09-13/PERFORMANCE.md) explains the strict timestamp,
unit, denominator and rounding rules. Decimal preserves exact cash arithmetic;
some return fractions repeat, so the result retains their exact numerator and
denominator alongside explicitly rounded percentages. This remains a synthetic
foundation; no real account performance is displayed or inferred.
