# Kalshi execution accounting and receipt recovery

On September 21 at 16:06:49 UTC, Huang VI bought 10 YES contracts in
`KXDOGE15M-26SEP211215-15`. Read-only order and fill receipts agree: execution
price **$0.55**, principal **$5.50**, fee **$0.1733**, total **$5.6733**. The old
adapter recorded $0.0055 per contract and no fee. Reconciliation correctly froze
new entries on a **$5.6183** cash discrepancy, and the deployment watch rolled back.
The market subsequently settled NO at 16:15:06 UTC: the actual trade lost $5.6733.
This is an execution-path finding and a losing trade, not evidence of profitability.

## Wire contracts

- [Create Order V2](https://docs.kalshi.com/api-reference/orders/create-order-v2)
  reports `average_fill_price` in fixed-point YES dollars and `average_fee_paid`
  per contract. A NO intent complements the YES execution price once; its fee
  is never complemented. IOC zero/partial fills retain the requested quantity
  and reflect final cancellation when no remainder is working.
- [Get Order](https://docs.kalshi.com/api-reference/orders/get-order) reports
  cumulative `taker_fill_cost_dollars` plus `maker_fill_cost_dollars`. Their sum
  divided by filled quantity is the actual leg execution average. The order's
  limit is not its execution price. Dollar fee totals include maker and taker.
- GET's [directional outcome](https://docs.kalshi.com/getting_started/order_direction)
  can name the opposite of the agent's original leg: selling YES appears as
  buying NO. Historical account receipts confirm that cumulative cost follows
  that returned outcome (e.g. 10 YES sold at $0.25 report $7.50 of NO cost).
  The Book complements that average back to the original leg before attributing
  the sale; this also covers selling NO and partial-fill polling.
- Legacy integer-cent fields remain supported explicitly. Zero-valued modern
  fields take precedence over legacy values. Missing execution price or fees
  in a V2 acknowledgement defer attribution until a complete order receipt;
  an incomplete acknowledgement never becomes a made-up fill at the limit.

## Append-only recovery

`league/accounting.py` runs inside a real Kalshi book's normal reconciliation.
It reads venue orders; it never submits, cancels, transfers, stakes or changes
the account baseline. New Kalshi fills carry `venue_accounting_version: 2`.

Recovery requires an old terminal, fully allocated order; matching venue ID,
instrument, side and quantity; explicit cumulative cost and fee receipt fields;
and the precise known signature: recorded price × 100 equals the receipt price,
with no recorded fees. Multiple partial allocations or repeated participating
agents are deliberately not reconstructed from an ambiguous cumulative average.
Unavailable or unproven receipts leave the normal reconciliation check in force.

For each original allocation, trusted account replay computes the difference
between the recorded and receipt-corrected state. The House appends a
`book.fill_correction` linking the original fill, normalized receipt, corrected
price/fee/cash, and exact deltas for cash, fees, realized P&L and remaining cost
basis. Original ledger rows and all position quantities remain intact. A
settlement or partial sale before recovery is handled by replay, not by assuming
the original contracts are still held. One atomic append covers the allocations;
deterministic IDs and normal ledger folding make restart recovery idempotent.

## Evidence after a correction

Earlier marks and derived results for the affected agent/book remain in the
audit trail but are excluded from promotion, drift, rewards, audit packets and
recent-trade summaries. Completed exposure calculations retain the cash
correction and discard an exposure spanning it; subsequent episodes use the
corrected capital. New observation blocks start from corrected marked equity.
Fresh evidence counters do not have to catch up to invalid old observation
counts before another evaluation. Already-spent statistical error allowances
remain spent. Actual losses remain in cash, cost basis, realized P&L and the positive-equity
promotion check. The correction does not forgive a loss or create a promotion.

Agents receive the receipt and money correction through `book_accounting`.
The public activity feed also reports the correction. Historical events are not
rewritten, so an original execution/settlement card can retain its original
incorrect value alongside the later correction. Current account totals use the
corrected ledger state.

## Validation

Regression tests cover V2 YES/NO price units, per-contract fees, incomplete
acknowledgements, explicit zero, legacy cents, maker/taker cost aggregation,
IOC partial/zero fills, polled YES/NO exits, open and settled recovery, partial exits, unavailable
or mismatched receipts, ambiguous partial allocations, restart after a committed
correction, unchanged quantities/baselines, excluded contaminated evidence and
fresh episodes/blocks with corrected capital. Adapter-to-book tests verify that
complete and incomplete acknowledgements converge to exactly one correctly
priced and fee-inclusive allocation without a real venue mutation.

Production acceptance and reconciliation results belong in the dated
[run report](../runs/2026-09-21-live-hour.md).
