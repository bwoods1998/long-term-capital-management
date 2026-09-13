# An honest future portfolio scoreboard

`performance.py` is an offline synthetic calculator, not a connected portfolio,
backtest, trading strategy, or public performance claim. It consumes supplied
valuations and has no account, price-feed, order, or Schwab imports.

## Required observations

The input declares synthetic USD equity, opening and closing valuations, every
external deposit/withdrawal, and a fictional total-return benchmark. Each flow
requires a valuation immediately before and immediately after the **same canonical
UTC instant**, with the phases explicit in the record. Flow instants must be unique,
ordered, and strictly inside the measurement period. The boundary must satisfy:

```text
equity_after = equity_before + signed_external_flow
```

The calculator refuses missing observations, ambiguous units/timestamps, unexplained
boundary changes, and nonpositive return denominators. It cannot determine whether
the caller omitted a flow or whether a supplied valuation is truthful. This explicit
data requirement prevents silently estimating returns from insufficient snapshots.

For each interval between funding events, divide its ending pre-flow equity by its
starting post-flow equity. Chain those growth factors, then subtract one:

```text
time_weighted_return = product(interval_end / interval_start) - 1
investment_P&L = closing_equity - opening_equity - net_external_funding
```

TWR removes external funding from subperiod growth. P&L remains a dollar amount;
it does not substitute for a rate. This is not money-weighted return or IRR. A
terminal zero valuation can represent a 100% loss; zero equity at the start of a
subsequent interval is rejected. A complete withdrawal requires ending this
measurement before starting a separately funded period.

The benchmark must supply an observation at **every exact portfolio boundary**,
in the same currency, explicitly labeled as a synthetic total-return index. No
interpolation, stale quote, price-only series, or mismatched period is accepted.
The reported difference is percentage points, not alpha or relative wealth growth.

## Expenses and arithmetic

Observed equity must already include incurred portfolio fees. `fees_in_equity`
reports their declared amount but does not deduct it again; this calculator does
not independently reconcile fee transactions. Research API expenses in
`research_expense_outside_portfolio` were paid outside the portfolio and remain a
separate project expense. They are not subtracted from portfolio returns. Paying
an expense from the portfolio would require a different, explicit treatment.

Bounded plain decimal strings preserve exact money arithmetic and growth-factor
products using Decimal. Exact numerator/denominator pairs are retained because
division can repeat forever. Display percentages use 12 decimal places with
half-even rounding; rounded subperiod percentages are never chained. No returns
are annualized and no drawdown or risk-adjusted statistic is inferred.

```sh
python3 performance.py demo --case funding-only
python3 performance.py demo --case fees-only
python3 performance.py demo --case growth-and-funding
python3 -m unittest discover -s tests -p test_performance.py -v
```

The synthetic funding-only example ends with $150 from $100 after net deposits
of $50: P&L and return are both zero. The fee-only example ends with $98 after a
$2 fee: P&L is −$2 and return −2%; its separate $3 research expense is not deducted.
The combined example produces $29 P&L, 19.662983425414% TWR, and a 10.25% benchmark
return. These are authored arithmetic outcomes, not actual portfolio results.
