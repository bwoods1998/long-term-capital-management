# Private project economic reconciliation

`scripts/project_economics.py` reads accounting metadata and writes immutable private reports. It sends no orders,
makes no provider purchases or network calls, and never writes the live, swarm, provider or House databases. It does
not change the public Profit field or any trading gate. Keep receipts and reports outside this public repository.

The cost interval begins at **2026-09-26T06:23:14Z**. Real options cash and the existing subscription proration begin
at the preserved financial basis, **2026-09-26T06:25:30Z**. Neither date moves with a restart, a deployment or a loss.

Collect local state metadata with an existing read-only operator access path, then reconcile the resulting receipt:

```sh
python scripts/project_economics.py collect --state /private/state > /private/economics-state.json
python scripts/project_economics.py report \
  --evidence /private/economics-state.json \
  --boxes /private/provider-box-receipt.json \
  --app-id PROJECT_APP_ID \
  --output-root /private/project-economics
```

Use a private parent directory/umask for raw receipts. The report writer creates new directories as `0700` and files
as `0600`. It names reports by a content hash, creates them atomically without overwriting existing snapshots, and
returns the same path when given identical evidence. The CLI keeps source receipts under `receipts/<sha>.json` so a
later collection cannot erase the evidence behind an old report. Input receipt hashes, source timestamps, accounting bases,
subscription rates, reservation details and reconciliation notes travel with every report. No automatic production
collector or reporting schedule is installed by this command.

Each dollar has one place:

* Sail model cost uses settled request receipts. Swarm model bookings are a reconciliation comparison; unpriced
  requests and outstanding holds stay unresolved. A Provider `usage_unsettled` cost is its conservative reservation,
  kept separately from measured cost until invoice reconciliation. OpenAI and Claude use recorded cost less identifiable outstanding
  reservations. Negative settlement entries are retained, attributed to the call's original admission interval.
* Box cost uses the provider's per-box rows for the specified project app. Finalized costs replace the booked Gym
  estimate; the estimate is shown only for comparison. Active estimated usage is a separate provisional amount.
  Global provider totals and unrelated apps are excluded. Deposited provider credit is not an invoice.
* ThetaData and market-data subscriptions use `league.publish`'s existing rates and 365.25-day-year proration.
  `--subscription-rates` accepts the existing `subscriptions_monthly_usd` mapping when the project's configuration
  overrides those rates. The receipt records the rates used.
* Closed real position cash already includes execution fees, including House positions and retired families.
  `trading_profit.complete` applies posted broker fee corrections once and retains Other and known Unreconciled
  account activity. Diagnostic notes alone do not block known cash. Blocking liabilities, stale readings, pending
  orders and invalidated book snapshots do. Later posted fees may revise the record.
* Account deposits, withdrawals, balance movement and practice P&L are not profits. This report does not mark open
  positions; open or unresolved inventory prevents a complete realized project Net.

`known_input_subtotal_usd` is the sum of available settled/finalized inputs and prorated subscriptions. It is useful
while categories are unresolved, but is not the cost of the complete project. The provisional subtotal adds only
active box estimates. `known_realized_less_known_inputs_usd` remains a partial figure. Only `project_net_usd`, with
`complete: true`, claims all-input Net.

Under the existing Profit convention a known signed Unreconciled dollar amount is included once, with its diagnostic
notes intact. Such a report may have complete dollar coverage while `broker_reconciled` is false. That flag and any
blocking liability remain separate; this report grants no trading or profitability gate approval.

The collector timestamps its separate database reads honestly. Cached broker activity and provider billing often
end at different times. Freshness may make the cached broker receipt internally consistent, but the report will not
call different cutoffs reconciled. Complete Net requires receipts covering the same cutoff; this initial tool does
not retroactively slice mutable provider records or synthesize a common cutoff. Settling outstanding requests,
obtaining finalized provider billing and establishing common-cutoff coverage remain operator-mediated.

External engineering, standalone inference and any other incremental project inputs remain unknown until there are
attributed receipts or explicit owner coverage. Do not fill a missing input with zero. An optional `--external` JSON
receipt has `start_at` equal to the cost start, `end_at` equal to the report cutoff, a nonnegative `usd`, `complete:
true`, `incremental_only: true`, and a nonempty `source` describing the receipts/owner declaration. `incremental_only`
asserts that none of the model, box or subscription charges already counted above is included again. An explicit
owner-confirmed zero is permitted; silence is not a zero. The pending owner answer is not presumed here.
