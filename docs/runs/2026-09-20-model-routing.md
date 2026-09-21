# Model routing decision — September 20, 2026

The justified change is to add fast, bounded Luna assistance for research blockers, retain Sail
Pro Flex for economical exploration, and retain Astra for architecture and difficult review.
Terra and Sol are available through the gateway but have not earned a default role in this
project. This is a provisional routing decision from a small coding pilot, not a ranking of
trading ability.

## What was actually measured

Three frozen tasks used actual stuck agents and the complete strategy contract: repair
Meriwether-13's parameter configuration, produce a BTC-only five-minute-bar hypothesis for
Huang-3, and propose a different long-only crypto rule for Rosenfeld. The same task inputs
were used across the compared routes. Each initial task/model combination had one attempt.

| Route | Output allowance | Time per task | Reported cost for three tasks | Structural checks passed |
|---|---:|---:|---:|---:|
| Sail Pro Flex, production settings | 32,000 | 264–598 seconds | $0.04585743 | 3/3 |
| OpenAI Astra | 6,000 | 55–98 seconds | $0.74 | 3/3 |
| OpenAI Luna | 6,000 | 25–29 seconds | $0.03 | 2/3 |
| OpenAI Terra | 6,000 | 36–45 seconds | $0.17 | 2/3 |
| OpenAI Sol | 6,000 | 47–77 seconds | $0.39 | 2/3 |

Structural checks included source safety, literal NEEDS/PARAMS, parameter validity, venue and
horizon compatibility, sealed module loading and an empty-input decision. They do not establish
that the requested hypothesis was implemented correctly or that it makes money.

The first six Sail calls used a 6,000-token allowance and all produced incomplete responses.
The production-setting follow-up above was explicitly run after observing that failure; it
must not be presented as a pre-registered equal-token comparison. It also must not be omitted
to make production Sail appear incapable of these tasks.

One additional Luna call received the exact parameter-validation error from its failed
Rosenfeld task. It repaired the configuration in 21.333 seconds for another reported $0.01,
and the sealed structural checks passed. That is an observed bounded repair cycle, not three
initial successes.

The 22 paid requests across all arms and this repair reported **$1.47309697** in model charges.
OpenAI figures are conservative gateway cost headers rounded up to cents; Sail figures are
provider usage estimates. These are not invoices and exclude sandbox hosting and interactive
engineering. Reservations and invoices are distinct. All temporary validation boxes were
confirmed terminated.

The subsequent Jev probe exposed that cent rounding could falsely exceed a tiny Luna
reservation. The gateway now returns six-decimal receipts; the table above preserves its
original measured headers. The [foundation report](2026-09-20-foundation-progress.md) records
the fix and the narrowly scoped reconciliation of the three affected later calls.

## Failures that a pass count hides

- Astra's sports repair also changed decision guards; the production Sail repair preserved the
  decision AST. Faster completion is not permission to ignore task fidelity.
- Terra's sports code used forbidden `.format`. Its structurally valid Huang code omitted the
  requested five-minute bar declaration; its Rosenfeld hypothesis remained close to the prior
  strategy family.
- Sol's Rosenfeld output reached the token limit without a complete required artifact.
- Luna's first Rosenfeld output contradicted its own ordered-window parameter rule. The
  explicit error-feedback repair passed, and both attempts remain in the evidence.

## Implemented routing

PR #20 admits priced Astra, Sol, Terra and Luna text calls through the existing Cloudflare
gateway, reserves conservative costs before calls, and retains reservations when bills are
ambiguous. The gateway was deployed and the account's model access verified.

PR #22 provides Luna startup grants: one per family/niche/current campaign, at most twelve
across the floor, and at most $0.25 reserved per grant. The aggregate maximum is $3 **within**
the existing automated OpenAI allocation, not an extra allowance. Births, deaths and restarts
do not renew a grant. Proposed code must still use the normal replay and adoption path.
The combined House release passed its canary and ten-minute watch at 6:04 PM Pacific;
all 20 shipped changed files matched and all four books reconciled. See the
[foundation run report](2026-09-20-foundation-progress.md).

By 6:32 PM, the first production startup grant had completed for Meriwether-14 and returned
strategy code for $0.007397. This is runtime acceptance of the grant path, not a replay pass.

Calls originate in the trusted House Sailbox, pass through the gateway, and run on OpenAI's
API. OpenAI weights are not running locally in Sail. Trading sandboxes remain credential-free
and network-isolated; the House provides their tools and inference.

Future routing should minimize total cost and elapsed time per **verified useful result**,
including failed attempts, repairs and hosting. Keep a fresh task set for confirmation before
changing the whole swarm. A larger model should earn escalation on the task where its
additional cost is worthwhile. Production does not yet implement a general adaptive router.

Standard short-context API input/output prices per million tokens are Luna $0.20/$1.20,
Terra $2/$12, Sol $4/$20 and Astra $10/$50. Cache writes and long contexts have separate rates;
the gateway reserves against conservative supported ceilings. Sol's published price is
promotional through at least November 21, 2026.
[Official OpenAI pricing, checked September 20](https://developers.openai.com/api/docs/pricing).

## Evidence and reproducibility

The frozen packets, complete responses, provider usage, failed attempts, validation receipts
and sandbox retirement records are retained privately in the observation directory and House
pilot directories. They contain strategy code and are not published into this repository.
The code changes and CI results are public:

- [PR #20](https://github.com/bwoods1998/long-term-capital-management/pull/20)
- [PR #22](https://github.com/bwoods1998/long-term-capital-management/pull/22)
- [PR #23](https://github.com/bwoods1998/long-term-capital-management/pull/23)

The first three-task packet has SHA-256
`437297d4331dd50a557d1cf90cb70a3375af026216da089b12dc9877dd6b1258`;
the nine-call intermediate-tier packet has SHA-256
`bd1f6972147031cc4926b87fc73e8ebf3ca8681d3bb5745b3773b04a22bb1425`.
All temporary validation boxes were confirmed terminated.
