# Options gateway

This Cloudflare Worker holds venue, OpenAI and GitHub credentials. The House authenticates with a scoped bearer token. An owner-only admin token can release the kill switch and never goes to Sail.

Routes serve Alpaca account/option/underlying data, approved option orders, Responses, helper pull requests, health, notify and kill control. Real stock orders only close assigned shares. Crypto, event markets, generic web fetch and the retired model-provider routes are absent. Data GETs remain available during a trading kill.

Real entries reserve maximum loss, including the configured fee policy, against absolute and fresh equity caps. Credit structures need eligible equity and buying power. Ambiguous upstream requests keep their reservations and stable client order identities. Closing risk is routed separately from entry caps. Paper trades only prove the approved multi-leg route.

`wrangler.jsonc` supplies explicit bounds and a funded OpenAI month. Funding a later month is a separate owner decision; a stale month cannot renew its allowance itself. Frontiers account for standard and flex prices and retain worst-case reservations until settlement. GitHub proposals are limited to pure helpers and tests; the Worker cannot merge them.

```sh
npm run check
npm test
```

Owner deployment and secret placement are separate from these tests. Preserve the Durable Object's accounting state across upgrades. Retired venue/provider secrets should be removed by the owner after the matching runtime is retired. `scripts/gateway_admin.py status` reads the running caps and kill state without exposing credential values. See [operations](../docs/operations.md) before any deployment or money switch.
