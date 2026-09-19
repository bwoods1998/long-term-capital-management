# The order gateway

The desks run in a Sail cloud VM. The venue private keys do not.

This Worker holds the Kalshi and Alpaca credentials as Worker secrets, authenticates
every request itself, enforces hard caps and a kill switch **before** it forwards anything, and
watches the floor from outside. The VM holds one bearer token. So the worst a compromised, confused or
runaway VM can do is *ask* for an order — it cannot sign one, it cannot exceed the caps, and it
cannot turn the kill switch off, because none of those things live in it.

It is also the reason the floor needs no operator. Every five minutes it reads the published
checkpoint, the Sail credit balance and the state of the box; it resumes and restarts the box by
itself when it can, and it sends mail only when it cannot. Adding Sail credit is the one human
step the design admits.

```
ltcm runtime (Sail VM)                 this Worker                        the venues
  GatewaySigner: a bearer token   ->   KALSHI_PRIVATE_KEY (RSA-PSS)  ->   api.elections.kalshi.com
                                       ALPACA_KEY_ID + _SECRET_KEY   ->   api.alpaca.markets
                                                                          data.alpaca.markets
                                       caps + kill switch (Durable Object)
                                       watchdog cron (checkpoint, balance, box)
```

## Endpoints

Every endpoint takes `Authorization: Bearer $GATEWAY_TOKEN`, compared with `timingSafeEqual`.
Anything else is `401`, including a deployment whose token is missing or shorter than 32
characters.

| Method | Path | What it does |
| --- | --- | --- |
| `GET`/`POST`/`DELETE` | `/v1/kalshi/<path>` | Signs `timestamp + METHOD + /trade-api/v2/<path>` with RSA-PSS SHA-256 (salt 32) and forwards to `https://api.elections.kalshi.com/trade-api/v2/<path>` with the query string. Status and body come back verbatim. |
| `GET`/`POST`/`DELETE` | `/v1/alpaca/<path>` | Adds `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY` and forwards to `https://api.alpaca.markets/<path>`, or to `https://data.alpaca.markets/<path>` when the path is a market-data one (`v2/stocks/`, `v1beta3/`). One venue name, two hosts, one credential. |
| `GET` | `/v1/health` | Caps, today's counters, kill switch, watchdog record, Sail balance and box state, and when each alert last went out. |
| `POST` | `/v1/kill` | Runtime token may engage the kill switch. |
| `POST` | `/v1/unkill` | Only the separate owner token may release it. |

The gateway serves exactly two venues; any other venue name is a `404`.
The Coinbase route was removed on Sept 19, 2026, when the owner closed that account.

Private keys are imported straight into WebCrypto: Kalshi accepts PKCS#8 (`BEGIN PRIVATE KEY`)
or PKCS#1 (`BEGIN RSA PRIVATE KEY`). Alpaca has no private key: its key id and secret are two
headers, added inside the Worker.

## The caps

Enforced atomically inside the `Gate` Durable Object before anything is signed, and only for the
three calls that can create an order — Kalshi `POST portfolio/events/orders` and
`POST portfolio/orders`, Alpaca `POST v2/orders`. **Reads and cancels always
pass**, whatever the counters say.

| Var | Default | Meaning |
| --- | --- | --- |
| `MAX_ORDER_USD` | `50` | Per-order notional. Kalshi: `count x price` in dollars (legacy cent prices and `buy_max_cost` are understood; an unpriced contract is charged its $1.00 settlement ceiling). Alpaca: `notional`, else `qty x` the dearest of its `limit_price`, its `stop_price` and the `X-LTCM-Reference-Price` header; a market order with none of these is priced from the venue's own quote plus 10%, never from the caller. |
| `MAX_DAY_USD` | `400` | Notional for the whole trading day. |
| `MAX_DAY_ORDERS` | `60` | Order count for the whole trading day. |
| `CAP_TIMEZONE` | `America/New_York` | The calendar the day rolls on: the floor's own. |

A refusal is `403` with `{ error, cap }`; the kill switch is `423` with `{ error }`; an order
whose notional cannot be established is `400` rather than a pass. Money is exact BigInt
arithmetic throughout and every partial cent rounds **against** the order.

A reservation is returned only when the forward never reached the venue. A venue that answered at
all keeps its reservation, however it answered: an unconfirmed write is an order until
reconciliation says otherwise.

## The watchdog, and the mail

The `*/5 * * * *` cron reads `https://blakewoods.us/api/capital/checkpoint`, the Sail usage
summary and the box's state, then does the smallest thing that helps:

- checkpoint older than `CHECKPOINT_STALE_SECONDS` (900) → run `RESTART_COMMAND` on the box via
  `POST /v1/sailboxes/<id>/exec` with an `idempotency_key`, at most once per
  `RESTART_COOLDOWN_SECONDS` (1800). The attempt itself opens the cooldown, confirmed or not, so
  a box that cannot come back is left stopped rather than restarted in a loop.
- box `paused` or `sleeping` **and** balance above `LOW_BALANCE_USD` → resume it, then restart.
  A top-up alone brings the floor back with no human step.
- box paused on the last of the credit → left paused, and the owner is told. Resuming a box that
  cannot finish its session only spends the remainder faster.
- box `terminated` or otherwise unrecoverable → never resumed.

Mail goes out through the `EMAIL` binding, at most once per six hours per kind
(`ALERT_EVERY_SECONDS`): `sail_balance_low` (under `LOW_BALANCE_USD`, 60),
`sail_balance_critical` (under `CRITICAL_BALANCE_USD`, 20), `box_not_running`,
`kill_switch_engaged`, `caps_exhausted`, and `daily_digest` in the 21:00 UTC hour with equity,
day P&L, orders, Sail spend and box state. A mail failure never takes the pass down, and an
alert that did not send is not recorded as sent.

Sail reports money as fractional US **cents**, so a `balance` of `3106.14` is $31.06. Its
`range` parameter understands `1h`, `6h`, `24h`, `7d`, `30d` and `period` and silently falls back
to 30 days for anything else, which is why `SAIL_USAGE_RANGE` is `24h` and not `1d`.

## Setting it up

The owner runs these; nothing in this repository ever reads or writes a secret. Each command
prompts for the value on a hidden line.

```bash
cd gateway

# A random token of 32+ characters. The runtime gets this one and nothing else.
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
npx wrangler secret put GATEWAY_TOKEN

# Kalshi: the key id (UUID) and the RSA private key, PKCS#8 or PKCS#1 PEM, BEGIN/END lines and
# all. Paste the whole file for the key.
npx wrangler secret put KALSHI_KEY_ID
npx wrangler secret put KALSHI_PRIVATE_KEY

# Alpaca: the key id and the secret key of the trading account.
npx wrangler secret put ALPACA_KEY_ID
npx wrangler secret put ALPACA_SECRET_KEY

# Sail, for the watchdog: the API key. Without it the watchdog only reports.
npx wrangler secret put SAIL_API_KEY
```

Provision the separate owner credential with `python3 scripts/gateway_admin.py provision`
from the repository root. It is stored mode 600 under `.data/ltcm/keys/`, never uploaded to
the trading VM. Release an external kill explicitly with `python3 scripts/gateway_admin.py unkill`.
The runtime credential cannot release it. Alpaca market orders use an independent
venue quote plus a 10% reservation buffer; caller references cannot lower a limit order's
notional. A network timeout after dispatch retains its cap reservation because acceptance is unknown.

Then set the box id in `wrangler.jsonc` and redeploy:

```jsonc
"vars": { "SAILBOX_ID": "sb_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", ... }
```

```bash
npx wrangler deploy
curl -s -H "Authorization: Bearer $GATEWAY_TOKEN" https://ltcm-gateway.<subdomain>.workers.dev/v1/health
```

## Switching the runtime to gateway mode

In `ltcm/config.json`:

```json
"gateway_url": "https://ltcm-gateway.<subdomain>.workers.dev",
"gateway_token_env": "GATEWAY_TOKEN"
```

and put `GATEWAY_TOKEN=<the same token>` in the VM's `.env`. `service._make_live_broker` then
builds each live venue in gateway mode: a `GatewaySigner` that carries only the bearer token and
a `VenueClient` that rewrites every call onto `<gateway_url>/v1/<venue>/...` and drops the venue
auth headers. An order POST may add `X-LTCM-Reference-Price` from the desk's own quote; the
gateway uses it only to raise, never to lower, what the order is worth against the caps. No key file, no key id and no venue secret is
read in that mode — `.data/ltcm/keys/` can be deleted from the VM entirely.

Setting `gateway_url` back to `null` restores direct, key-in-process mode. Both paths are covered
by `ltcm/tests/test_adapters_gateway.py`.

## Working on it

```bash
npm install
npm test     # node --test test/*.test.mjs, WebCrypto, no network, no key material on disk
npm run check
npx wrangler deploy
```

Every key the suite uses is generated in-process for the test that uses it: signatures are
checked by verifying them with the public half of the key that signed them, so the recipes are
tested rather than asserted.
