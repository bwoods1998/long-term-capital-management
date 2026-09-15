# The order gateway

The desks run in a Sail cloud VM. The venue private keys do not.

This Worker holds the Kalshi and Coinbase credentials as Worker secrets, signs every request
itself, enforces hard caps and a kill switch **before** it forwards anything, and watches the
floor from outside. The VM holds one bearer token. So the worst a compromised, confused or
runaway VM can do is *ask* for an order — it cannot sign one, it cannot exceed the caps, and it
cannot turn the kill switch off, because none of those things live in it.

It is also the reason the floor needs no operator. Every five minutes it reads the published
checkpoint, the Sail credit balance and the state of the box; it resumes and restarts the box by
itself when it can, and it sends mail only when it cannot. Adding Sail credit is the one human
step the design admits.

```
ltcm runtime (Sail VM)                 this Worker                        the venues
  GatewaySigner: a bearer token   ->   KALSHI_PRIVATE_KEY (RSA-PSS)  ->   api.elections.kalshi.com
                                       COINBASE_API_SECRET (CDP JWT) ->   api.coinbase.com
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
| `GET`/`POST`/`DELETE` | `/v1/coinbase/<path>` | Mints a CDP JWT bound to `METHOD api.coinbase.com/<path>` and forwards to `https://api.coinbase.com/<path>`. |
| `GET` | `/v1/health` | Caps, today's counters, kill switch, watchdog record, Sail balance and box state, and when each alert last went out. |
| `POST` | `/v1/kill` / `/v1/unkill` | Engages or releases the kill switch. Returns the health body. |

Private keys are imported straight into WebCrypto: Kalshi accepts PKCS#8 (`BEGIN PRIVATE KEY`)
or PKCS#1 (`BEGIN RSA PRIVATE KEY`); Coinbase accepts an Ed25519 secret as base64 (the 32-byte
seed or the 64-byte seed-then-public form), a DER blob, or an ECDSA PEM in PKCS#8 or SEC1 form,
signing `ES256` as raw `r || s`.

## The caps

Enforced atomically inside the `Gate` Durable Object before anything is signed, and only for the
three calls that can create an order — Kalshi `POST portfolio/events/orders` and
`POST portfolio/orders`, Coinbase `POST api/v3/brokerage/orders`. **Reads and cancels always
pass**, whatever the counters say.

| Var | Default | Meaning |
| --- | --- | --- |
| `MAX_ORDER_USD` | `50` | Per-order notional. Kalshi: `count x price` in dollars (legacy cent prices and `buy_max_cost` are understood; an unpriced contract is charged its $1.00 settlement ceiling). Coinbase: `quote_size`, else `base_size x` the `X-LTCM-Reference-Price` header the caller sends, else `base_size x limit_price`. |
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

# Coinbase CDP: the key id (organizations/.../apiKeys/...) and the secret, either the base64
# Ed25519 secret or the full ECDSA PEM.
npx wrangler secret put COINBASE_KEY_NAME
npx wrangler secret put COINBASE_API_SECRET

# Sail, for the watchdog: the API key. Without it the watchdog only reports.
npx wrangler secret put SAIL_API_KEY
```

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
builds Kalshi and Coinbase in gateway mode: a `GatewaySigner` that carries only the bearer token,
a `VenueClient` that rewrites every call onto `<gateway_url>/v1/<venue>/...` and drops the venue
auth headers, and a Coinbase order POST that adds `X-LTCM-Reference-Price` from the desk's own
quote so the gateway can price it against the caps. No key file, no key id and no venue secret is
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
