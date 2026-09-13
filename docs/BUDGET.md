# Allowances and measured charges

The first campaign used permanent cumulative reservations. A request reserving
$0.20 continued to occupy $0.20 even when its final token-price estimate was much
smaller. That was conservative, but it eventually blocked useful work without
indicating that the provider had charged the reserved amount.

`settled-estimates-v1` is an explicitly activated accounting policy. It preserves
every original request, response, allowance, price, protocol and pilot limit.
Its admission calculation is:

```text
committed = immutable settled estimates + all unsettled request allowances
```

Before admitting a request, that commitment plus the new maximum allowance must
fit the existing inference ceiling. SQLite takes its write lock before checking
and inserting, so competing controllers cannot spend the same available room.
Amounts use exact decimal arithmetic; fractional cents are not rounded away.

## Explicit activation and settlement

These commands change local accounting records but make no network or model calls:

```sh
python3 portfolio.py budget --activate-policy settled-estimates-v1 --reviewer 'Owner'
python3 portfolio.py settle RUN_ID
```

Replace `RUN_ID` with an existing logical request identity. Activation does not
settle any request or change the dollar ceiling. Repeating an identical activation
or settlement returns its existing receipt. There is no automatic settlement just
because a provider request completed. Until activation, the original gross
reservation policy remains in force.

A settlement requires an accepted, terminal response with matching identity and
model, its original credential binding, complete usable token accounting, and
valid frozen prices. Completed, incomplete, failed and cancelled responses can all
cost money. Model retirement and later price changes do not reprice old work:
the saved request model and saved rate card remain authoritative.

The receipt binds the request, full response, evidence packet, original allowance,
prices, date, credential identity and exact calculated estimate. Receipt identities
and timestamps are hashed. Additive receipts and settled financial inputs are
immutable, and every accounting read validates their bindings again. A changed or
corrupt receipt stops admission. Settlement does not approve the research content.

Unknown, malformed, unconfirmed and in-flight responses keep their complete
allowances. Positive unapproved Supercache writes cannot settle. A known valid
cost above its allowance is displayed as an excess commitment and blocks new
admissions; it is not silently reduced to the allowance. Such a case needs a
separately reviewed reconciliation capability, not deletion or a replacement run.

## Read the numbers

```sh
python3 operations.py
```

This read-only command reports a separate `budget` object:

| Field | Meaning |
|---|---|
| `gross_historical_reserved_usd` | Every original allowance, including settled work |
| `settled_estimated_usd` | Immutable estimates recorded by explicit settlement |
| `open_reservations_usd` | Full allowances still protecting unsettled work |
| `committed_usd` | Amount used by the active admission policy |
| `available_usd` | Remaining local admission room, not the provider account balance |
| `over_reservation_requests` | Known allowance breaches requiring reconciliation |

The existing inference `reserved_usd` field still means gross historical
reservations. Previously exported artifacts are unchanged. Operations excludes
reviewer names, private receipt identities and provider response identifiers.

These are **token-price estimates, not reconciled provider bills**. A later billing
correction cannot overwrite a settlement or lower a recorded charge; reconciliation
would require a separate additive audited mechanism. Sailbox charges and the
original extraction ledger remain separate from this inference accounting. Keep
their allowance inside the overall owner-authorized project ceiling.

This policy does not reopen the finished experiments, renew their deadlines,
increase their request caps, or grant another slot in the two-job queue pilot.
New work needs its own bounded protocol. The existing ceiling is retained unless
the owner explicitly changes it; opening new admission room is not authorization
to spend without a purpose or to extend a stopped campaign.

## Latest saved accounting

The [current budget snapshot](../public/research-budget.json) includes all completed
work in this build. It preserves the original ceiling and unresolved holds;
settlement receipts do not erase earlier requests or reset pilot limits.
