# Balanced research models and original-request recovery

The stock top-family rewrite profile is `k3_balanced`, mapping to
`moonshotai/Kimi-K3` with the `balanced` completion window. The rewrite caller
passes its complete system message and family history, medium reasoning effort,
12,000 maximum output tokens, no tools, and the `swarm-rewrite` cache key.
The isolated bridge preserves these fields. It sends one background Responses
request with streaming off and truncation disabled. It does not substitute a
model, shorten the history, add tools, or estimate actual cost from usage.

[Sail support](https://docs.sailresearch.com/support) documents background
requests for balanced and flex windows, polling by response ID, four terminal
statuses, and the absence of cancel/delete endpoints. The reviewed bridge
supports ASAP and balanced; flex admission is still refused. Stock named
profiles must retain their model and completion window from `ltcm.provider`.

The bridge commits the broker's original scope, request fingerprint and shared
budget reservation before POST. Its separate durable dispatch intent pins
the profile, completion window and exact native request body. On acknowledgement,
it saves the native response ID linked to the immutable original native
observation before checking model and status. A malformed acknowledgement may
still incur liability; it cannot release the reservation.

Polling uses GET only, with a finite local patience limit. A timeout, failed GET,
expired response, or unavailable response handle leaves the original request
and maximum liability unresolved. Local patience is not native cancellation,
a maximum billing horizon, or evidence of a zero invoice. HTTP error text is
not parsed into an invented accepted handle, and POST is never replayed.

`recover_evaluation` is a separate broker and authenticated IPC operation.
It requires the exact original request body, intact original scope and model
policy, a dispatched uncancelled reservation, the original wire intent, and a
durable accepted handle linked to its native observation. It cannot count new
tokens, reserve again, refresh pricing, admit a missing request, or reopen a
withdrawn scope. The router uses this operation for an existing controller claim;
older brokers retain their cache-only recovery behavior. `ModelCapability`
defaults to no recovery callback, preserving unresolved-request refusal for
legacy adapters. A host callback is reviewed authority to retrieve accepted
work, never permission to send another paid request.

Recovery can finish a retained native terminal receipt without another GET.
Concurrent pollers commit one immutable broker terminal receipt. Unknown
invoices remain `cost_usd: null`, `accrued_day: null` in that receipt, with the
original reservation exposed separately as `cost_upper_usd`. Later authoritative
invoice reconciliation belongs to the shared ledger and does not rewrite an
already cached unknown invoice. A matching invoice already settled before a
crash is not settled twice. An authoritative bill above the original maximum
durably breaches the paid scope before the error escapes.

A conservative billable input reservation is distinct from actual prompt size.
Sail's native input plus output plus formatting reserve must still fit the
model's usable context. This change keeps the whole-input, byte, output, effort
and tool bounds and native truncation-disabled behavior unchanged.

The offline tests use fake native Responses acknowledgements and GET results,
synthetic inclusive rate bounds, invoice receipts, CI and host authority. They
exercise the real stock broker, router, private journal, shared budget and Unix
IPC on Python 3.11 and 3.14. They do not establish actual billing guarantees,
tax treatment, accepted-attempt obligations, model availability, production
isolation, checkpoint/data provenance, market qualification or live readiness.
Those facts remain independent admission inputs.
