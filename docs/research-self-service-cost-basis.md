# Ordinary-service research accounting

Schema1 receipts retain the existing certified bound path. Schema2 selects
`observed_self_service` explicitly in both the model receipt and host tariff.
It admits work under the same original local $25 limit using bounded quantities,
fresh applicable prices, known adjustments and original obligations. It does not
promise the provider's final invoice cannot exceed that projection. The ordinary
[terms](https://www.sailresearch.com/terms) permit prospective rate changes and
exclude taxes; [usage](https://docs.sailresearch.com/usage) can be delayed.

The model receipt is `{schema:2,scope,profiles,cost_basis,provenance}`. Each profile
retains `policy,max_request_bytes,billable_input_ceiling,completion_window` and
omits the schema1 agreement declaration. The exact four profiles remain
`flash41_asap`, `flash_asap`, `k3_balanced`, `pro_asap`; model IDs and windows must
match stock source. Policies enforce full input, output, tool and byte limits.
Their static monetary amounts cap the local reservation. A separate fresh price
basis must fit those amounts before every new dispatch; a rate increase above
them refuses rather than silently changing the model or resetting a reservation.
The policy lifetime and local polling timeout are not provider price locks.

The billing receipt is `{schema:2,scope,observed_at,valid_until,tariff,inventory,
cost_basis,provenance}`. `tariff` must exactly match the factual reader's derived
document. The cost basis has these fields:

| Field | Meaning |
| --- | --- |
| `schema,mode,scope` | `2`, `observed_self_service`, original joint scope |
| `observed_at,refresh_by` | Price/fact revalidation interval, at most 300 seconds |
| `future_rate_lock` | Always false |
| `references` | Host-private raw `terms,pricing,quantity_source,account_facts`, each with path, SHA256 and source URL/identity |
| `applicability` | Actual plan, region and provenance, or explicit nulls |
| `model_rates` | Original four profiles' observed input/output prices and fixed request charge |
| `resource_rates` | Observed CPU, RAM, disk and separately persistent volume rates |
| `fees_taxes` | Fee/tax fraction uppers, fixed day fee, creation fee and provenance; null means unknown |
| `prior` | Genuine current UTC day, complete prior-cost upper and provenance; null never means zero |
| `pending` | Original keys, known retained charge projections/uppers and provenance; unbounded entries remain null |
| `provenance` | How the reader's facts were obtained and interpreted |

`quantity_source` contains the exact artifact hash map for the bridge, broker,
cost-basis reader and stock provider. Both the manifest and actual loaded source
bytes are checked. Raw document hashes bind evidence; they do not authenticate
fabricated account facts or interpret an invoice by themselves. An operator must
supply authentic facts through the existing protected receipt channels.

Unknown plan/region, fees/tax, creation fee, prior costs, pending charge exposure,
partial inventory or shared writers refuse paid admission. Foreign pending keys
are refused. Known zero adjustments still require evidence. Existing journal,
cache, scope, inventory, drawdown/kill/execution and isolation checks remain in
place. No receipt creates a new allowance. A passive first-initialization
preflight uses the explicit schema2 facts without SQLite; ordinary admission
requires the intact replay-checked original ledger.

Validated cost increases are retained before the cap decision on every paid
entry: host billing, broker admission, native guest work, reservation and dispatch.
Read-only `billing`, `summary` and initialization preflight do not publish facts.
A higher quote can arrive while the original SQLite connection holds an outer
transaction. The code does not force that transaction to commit or use a second
SQLite writer. It first publishes owner-private immutable fact files under
`observed-cost-facts-v1` in the original broker root, bound to the exact original
`opened` event hash, scope and directory identity. Each file and the directory
are fsynced; a separate atomic completeness manifest records the exact file set
under a fixed file lock. Before the first record, an immutable required-book
witness is separately fsynced beside the directory in the original broker root.
It pins that directory's identity and detects loss even when the first higher
quote was refused and no SQLite synchronization committed. This append survives
a later cap refusal or rollback. Missing, truncated, foreign, symlinked, unpublished or unindexed files refuse
admission. An incomplete crash publication also refuses; it is never discarded
as an empty history. The journal is bounded at 10,000 facts and refuses further
increases at that bound; it has no automatic compaction or evidence deletion.

Replay verifies the original SQLite journal/cache first, then conservatively
projects every retained file fact. Before ordinary mutations, compatible source
synchronizes those hash-bound facts as `observed_facts_retained` events in the
original SQLite journal/cache. A rollback can undo this synchronization but
cannot remove the external fact or its completeness witness. The external
journal must be included in coherent backup, withdrawal and later recovery.
Deleting or copying only the SQLite file cannot preserve this accounting scope.

Original schema1 rows remain byte for byte unchanged. A scope that has never
selected observed admission gains no fact files or new events. Schema2 host
configurations and synchronized mode tags are incompatible with old f38 paid
readers. An old SQLite-only parser also cannot account for newly retained files
when their synchronization rolled back; it must never certify that scope's costs
or restart paid work. Rollback therefore keeps this compatible reader and all
fact files. The compatible reader retains the highest unresolved pending amount,
resource prices and current-day prior/fixed fees. A cheaper observation never
releases an original unpaid obligation. Pending holds carry across restart and
UTC rollover. Completed model output without an all-in bill keeps its hold.

Schema2 final model bills retain original request, response, model, body and UTC
accrual identity and require `inclusive_fees_taxes:true` plus a hash-bound raw
`source_document` reference. Only independently established final all-in charges
settle. Authoritative charges above the original admitted request amount persist
a breach and stop paid work. The actual raw source need not contain invented
local JSON fields. Legacy schema1 bill semantics are unchanged.

The summary names `admission_total_at_observed_rates_usd` and price-basis time.
`total_upper_usd`, `total_upper_nanos` and the future certified-total field are
null in observed mode. `verified_all_in_ceiling`, `provider_final_bill_guaranteed`
and `future_rate_lock` are false; `within_cap` means the local observed admission
projection passes. It is not profit, a final daily bill or provider-enforced
monetary protection.

Full-day native capacities remain reserved. Observed prices alone cannot certify
the original running interval for new pause savings/resume accounting; those
paths refuse and retain the full hold. Already recorded schema1 pause/resume
history is still readable and uses the durable high price view. A terminal GET
does not settle added resource exposure, which remains held across UTC rollover.
Retirement of that additional native all-in exposure needs a separately reviewed
final charge allocation; this version does not fabricate it from a terminal GET.

Rollback must withdraw the scoped runtime first and keep this compatible reader
for original GET recovery/reconciliation. Do not run f38 paid admission on a new
tagged journal, delete its cache, relocate its ledger or reinitialize the scope.
Private setup/bootstrap callers must use `tariff_from_document`; successor
indexes/templates need exact source, artifact, head and CI binding. The old bare
schema1 passive billing callback does not supply schema2 authority and requires
a separately reviewed composed template.

Tests use fabricated raw documents/account facts and copied temporary SQLite.
They demonstrate software admission/refusal, retained exposure and rollback
reader behavior. They do not establish real startup readiness or costs.
