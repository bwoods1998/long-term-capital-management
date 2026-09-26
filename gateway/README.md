# The gateway

A Cloudflare Worker (`ltcm-gateway`) that holds every credential that can move money or spend it:
the Brokerage Account's keys (real and paper), OpenAI's key, the GitHub token and Sail's key for its
watchdog. The House's Sailbox holds one bearer token and can only ask: it cannot sign an order, pass
a cap, spend past the OpenAI month or release the kill switch, because none of that lives on the
box. Caps and switches change only by editing `wrangler.jsonc` and deploying, which is the owner's
act. The old, long version of this page is
[archive/docs/gateway-README-pre-options.md](../archive/docs/gateway-README-pre-options.md).

```
the House (Sailbox)        this Worker                                  outside
  GATEWAY_TOKEN      ->    ALPACA_KEY_ID / _SECRET_KEY            ->    api.alpaca.markets (the Brokerage Account)
                           ALPACA_PAPER_KEY_ID / _SECRET_KEY      ->    paper-api.alpaca.markets
                           (either pair, market data)             ->    data.alpaca.markets
                           OPENAI_SECRET_KEY                      ->    api.openai.com
                           GITHUB_TOKEN                           ->    api.github.com
                           caps, the OpenAI month, the kill switch (one Durable Object)
                           the watchdog cron (SAIL_API_KEY)       ->    Sail, the site, mail to the owner
```

## Routes the options House uses

Every route takes `Authorization: Bearer $GATEWAY_TOKEN` except `/v1/unkill`, which takes only the
owner's `GATEWAY_ADMIN_TOKEN`.

| Route | What it does |
|---|---|
| `GET /v1/health` | the kill switch, caps and today's counters, the OpenAI month, Sail's balance and the House box's state; never reads a venue itself |
| `POST /v1/kill`, `POST /v1/unkill` | engage the kill switch (any token), release it (owner only) |
| `/v1/alpaca/<path>` | the Brokerage Account (orders to `api.alpaca.markets`, market data to `data.alpaca.markets`) |
| `/v1/alpaca-paper/<path>` | the paper account: never metered, not stopped by the kill switch, held to the same defined-risk shapes |
| `POST /v1/frontier/responses`, `GET /v1/frontier/models` | one metered OpenAI Responses call; the models the key reaches |
| `POST /v1/github/pr`, `GET /v1/github/pr/<n>[/failures]` | open a pull request from a proposal; read its state and CI |

Still in the code until the prune removes them (Wave 2b), and unused by the options House:
`/v1/kalshi/*` and `/v1/kalshi/ws-auth`, `/v1/typesafe/systemone` (Jev), `/v1/web/fetch`,
and the crypto and stock order paths (the close of an assignment's shares stays). `/v1/notify`
mails the owner a `live_stop` notice when a real-money stop trips (Sept 26, 2026).

## The caps

Enforced atomically before an order is signed, and only on calls that create an order on the real
account. **Reads and cancels always pass.** Deployed values (`wrangler.jsonc`, Sept 26, 2026, the live
path, Wave 5):

| Var | Deployed | Meaning |
|---|---|---|
| `MAX_ORDER_MAX_LOSS_USD`, `MAX_ORDER_EQUITY_SHARE` | 1000, 0.15 | one OPENING order's maximum loss is at most the lower of $1,000 and 15% of the account's equity |
| `MAX_DAY_EQUITY_SHARE`, `MAX_DAY_USD` | 1.0, 10000 | today's opening maximum loss, this order included, at most 100% of equity and never above $10,000 |
| `MAX_DAY_ORDERS` | 300 | the trading day's order count, exits included (under the venue's 390 a day) |
| `CREDIT_MIN_EQUITY_USD` | 2000 | a credit structure (credit vertical, iron condor, iron butterfly) opens only at this equity or more |
| `EQUITY_CAP_MAX_AGE_MS` | 120000 | the oldest equity reading an opening order is sized against |
| `OPTION_STRUCTURES_REAL` | the five types | `debit_vertical,credit_vertical,iron_condor,iron_butterfly,long_butterfly`: what the real account may OPEN |
| `CAP_TIMEZONE` | America/New_York | the calendar the day rolls on |
| `MAX_ORDER_USD`, `MAX_ORDER_USD_KALSHI` | 75, 75 | Kalshi only (dead until the prune removes it) |

- **The equity is the gateway's own reading** (`lib/account.mjs`): `GET v2/account` with the real keys,
  rounded down, kept in the Durable Object and read again on the order path when older than
  `EQUITY_CAP_MAX_AGE_MS`. No fresh reading refuses an OPEN with `503 {cap: "equity"}` (nothing was
  sent; the House sends it again next minute); exits never wait on it. The House cannot raise its own
  caps by reporting a larger account.
- **Open or exit is read from the order**, not from `X-LTCM-Purpose`: a structure's legs'
  `position_intent` says whether it opens (metered at its maximum loss against every cap) or closes
  (one micro-dollar, admitted only when the account's positions hold every leg it closes).
- **Stock orders** only close an assignment: a sale of shares held long or a buy covering shares held
  short, at most the size held; every other stock or crypto order on the real account is refused.
- A refusal is `403 {error, cap}`; the kill switch is `423` and stops every order-creating call on the
  real account, exits included; an order that cannot be priced is `400`. Money is exact integer
  arithmetic and partial cents round against the order.
- **Structures** (`order_class: "mleg"`, `lib/caps.mjs`) are read from their legs as one of the
  defined-risk types. Any naked short, uncovered ratio, legging in or out, mixed roots or a
  `limit_price` of the wrong sign (positive is a debit, negative a credit) is a `400` on both accounts.
  `OPTION_STRUCTURES_REAL` must equal the constitution's `options_money.real_types`; `league.ci`
  refuses a tree where they disagree.
- `/v1/health` reports `max_loss`: the equity reading and its age, the per-order cap now, today's
  opening maximum loss and its cap, whether opens and credit opens are admitted, orders today.

## The OpenAI month

`/v1/frontier/responses` forwards one call to OpenAI's Responses API within `FRONTIER_MONTH_USD`
($607 for September 2026, `FRONTIER_MONTH_MAX_USD` the same): the call's worst case is reserved
before it leaves, settled at the usage OpenAI reports, and a call that does not fit is a `402`. The
reply carries `X-LTCM-Cost-USD` to the microdollar. The cap never goes above funded money; raising it
is a gateway deploy.

- **Flex** (Sept 26, 2026): a request may carry `service_tier: "flex"` for a model whose
  `FRONTIER_MODELS` row has a `flex` rate (half the standard one for GPT-6 Astra, Sol and Luna). It is
  reserved at the standard worst case and settled at the flex rate only when the answer reports
  `service_tier: "flex"` (the reply's `X-LTCM-Billed-Tier` says which); a 429 (flex capacity refused)
  settles at zero.
- **Output ceilings**: 16,000 tokens by default; `X-LTCM-Role: <role>` takes that role's ceiling from
  `FRONTIER_ROLE_MAX_OUTPUT` (`{"postmortem": 64000}`), and the reservation is sized from it.

## The watchdog

A cron every five minutes reads the site's production checkpoint, Sail's balance and the House box's
state. It runs `/workspace/restart.sh` on the box when the checkpoint is over `CHECKPOINT_STALE_SECONDS`
(1800) old, at most once per `RESTART_COOLDOWN_SECONDS` (1800); it resumes a paused or sleeping box
when Sail credit is above `RESERVE_USD` ($10); and it mails the owner about a low balance or runway,
a box not running, an engaged kill switch or exhausted caps, plus a digest at 21:00 UTC. It reads the
site's schema 2: `account.equity`, and profit since the reset (equity less `performance.start_equity`
and `net_flows`); the "stopped for lack of credit" mail keys on Sail's balance at the reserve. While the
checkpoint route answers 404 (after a site reset, before the House's first checkpoint) it touches
nothing. It never chooses a release: that is the in-box watchdog ([deploy/README.md](../deploy/README.md)).

## Secrets

The owner places them from `gateway/`, each on a hidden prompt; nothing in this repository reads or
writes one.

```sh
npx wrangler secret put GATEWAY_TOKEN            # the House's bearer token, 32+ random characters
npx wrangler secret put ALPACA_KEY_ID            # the Brokerage Account
npx wrangler secret put ALPACA_SECRET_KEY
npx wrangler secret put ALPACA_PAPER_KEY_ID      # the paper account
npx wrangler secret put ALPACA_PAPER_SECRET_KEY
npx wrangler secret put OPENAI_SECRET_KEY
npx wrangler secret put SAIL_API_KEY             # the watchdog
npx wrangler secret put GITHUB_TOKEN             # fine-grained: this repository, contents and pull requests only
python3 ../scripts/gateway_admin.py provision    # GATEWAY_ADMIN_TOKEN, kept mode 600 under .data/ltcm/keys/
npx wrangler secret list                         # names only, never values
```

`KALSHI_KEY_ID`, `KALSHI_PRIVATE_KEY` and `TYPE_SAFE_TOKEN` are dead once the prune lands; the owner
deletes them with `npx wrangler secret delete <NAME>`.

## Working on it

```sh
cd gateway
npm install
npm run check    # node --check on the worker and every module
npm test         # node --test test/*.test.mjs: no network, keys generated in-process
npx wrangler deploy
```

Run the check and the suite, read the result, then deploy; roll back with `npx wrangler rollback`.
No deploy from 13:25Z to 20:05Z on a trading day except a rollback. Deploy the gateway before a
House release that depends on its change.
