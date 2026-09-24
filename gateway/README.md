# The order gateway

The House runs in a Sail cloud VM. The venue keys, the OpenAI key and the GitHub token do not.

This Worker holds venue, OpenAI, TypeSafe and GitHub credentials as Worker secrets, authenticates every
request itself, enforces hard caps and a kill switch **before** it forwards anything, and watches
the floor from outside. The VM holds one bearer token. So the worst a compromised, confused or
runaway VM can do is *ask*: it cannot sign an order, exceed the caps, spend past the frontier
model's month, push to the repository or turn the kill switch off, because none of those things
live in it.

```
the House (Sail VM)                    this Worker                          outside
  one bearer token               ->    KALSHI_PRIVATE_KEY (RSA-PSS)    ->   api.elections.kalshi.com
                                       ALPACA_KEY_ID + _SECRET_KEY     ->   api.alpaca.markets
                                       ALPACA_PAPER_KEY_ID + _SECRET_KEY -> paper-api.alpaca.markets
                                         (market data, either pair)    ->   data.alpaca.markets
                                       OPENAI_SECRET_KEY               ->   api.openai.com
                                       GITHUB_TOKEN                    ->   api.github.com
                                       caps, budgets, kill switch (one Durable Object)
                                       watchdog cron (checkpoint, balance, box)
```

## Endpoints

Every endpoint but one takes `Authorization: Bearer $GATEWAY_TOKEN`, compared with
`timingSafeEqual`. `/v1/unkill` takes `$GATEWAY_ADMIN_TOKEN` instead, and only that. Anything else
is `401`, including a deployment whose token is missing or shorter than 32 characters.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/health` | Kill switch, caps, today's order counters, the frontier month (spent, what of it is settled and what is still in flight, the month that ended, the cap in force and its profit-indexed parts from the stored equity reading, calls, cost by agent), today's pull requests, the watchdog's record, Sail balance, runway and box state, and when each alert last went out. It never reads a venue itself (Sept 23, 2026). |
| `POST` | `/v1/kill` | Engages the kill switch. The runtime token may: stopping is never gated. |
| `POST` | `/v1/unkill` | Releases it. **Owner token only**; the runtime token is a `401` here. |
| `GET`/`POST`/`DELETE` | `/v1/kalshi/<path>` | Signs `timestamp + METHOD + /trade-api/v2/<path>` with RSA-PSS SHA-256 (salt 32) and forwards to `https://api.elections.kalshi.com/trade-api/v2/<path>` with the query string. Status and body come back verbatim. |
| `GET`/`POST`/`DELETE` | `/v1/alpaca/<path>` | Adds `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY` and forwards to `https://api.alpaca.markets/<path>`, or to `https://data.alpaca.markets/<path>` when the path is a market-data one (`v2/stocks/`, `v1beta3/`). The real account. |
| `GET`/`POST`/`DELETE` | `/v1/alpaca-paper/<path>` | The same paths with the paper key pair, forwarded to `https://paper-api.alpaca.markets/<path>` (market data still goes to the data host). Never metered, and not stopped by the kill switch: see below. |
| `GET` | `/v1/kalshi/ws-auth` | The three handshake headers for Kalshi's WebSocket (`/trade-api/ws/v2`), good for 30 seconds. The only route that hands the VM credential material, and what it hands over is short-lived and read-only: Kalshi takes no order over its WebSocket. The first run used it; the league does not. |
| `POST` | `/v1/frontier/responses` | One metered call to the frontier model (OpenAI Responses API). See [The frontier month](#the-frontier-month). |
| `POST` | `/v1/typesafe/systemone` | Bounded Jev shadow pilot; requires `X-LTCM-Request`, pinned `jev-1.13.0`, inline state and choice/noul questions. Uses `TYPE_SAFE_TOKEN` only in this Worker. |
| `GET` | `/v1/frontier/models` | The model ids the key can reach, and which of them are priced. Free. |
| `POST` | `/v1/github/pr` | Opens one pull request from a proposal `{role, slug, title, body, files}`. See [Pull requests](#pull-requests). Not stopped by the kill switch: it moves no money. |
| `GET` | `/v1/github/pr/<number>` | That pull request's `state`, `merged`, `mergeable_state`, `head` and its check runs counted into `success`, `failure` or `pending`, so the VM watches CI with no GitHub credential. Free. |
| `POST` | `/v1/notify` | Mails the owner one trade notice composed here from the facts posted (`kind` of `trade`, `settled` or `test`; 32 KiB at most). A `notice_id` makes a repeat a no-op for 48 hours; `NOTIFY_MAX_PER_DAY` (300) a trading day, then `429`. The first run's desks used it; the league does not call it. |

The gateway serves exactly three venue names: `kalshi`, `alpaca` and `alpaca-paper`. Any other is
a `404`. The Coinbase route was removed on Sept 19, 2026, when the owner closed that account.

**Why paper is unmetered and ignores the kill switch.** No money is behind it. The caps and the
switch exist to bound what real money can lose; the paper league is how the floor learns, and it
must keep learning while real trading is halted. A paper order never reaches the `Gate` at all, so
it cannot use up the day's real order count either. Paper shares Alpaca's path allowlist, so it can
do nothing the real route cannot.

Private keys are imported straight into WebCrypto: Kalshi accepts PKCS#8 (`BEGIN PRIVATE KEY`)
or PKCS#1 (`BEGIN RSA PRIVATE KEY`). Alpaca has no private key: its key id and secret are two
headers, added inside the Worker. Auth headers the caller sends are never forwarded.

### The only paths it signs

Anything not on this list is `403 Not a path this gateway signs.` before any key is touched: no
batched orders, no withdrawals, no transfers out, no key management, no account configuration.

| Venue | Method | Paths |
| --- | --- | --- |
| Kalshi | `GET` | `portfolio/balance`, `positions`, `fills`, `settlements`, `deposits`, `withdrawals`; `portfolio/orders[/<id>]`; `portfolio/intra_exchange_instance_transfer[s][/<id>]`; `markets`, `series`, `events`, each with an optional id, then optionally `orderbook`, `candlesticks`, `history` or `markets`, then an optional id; `exchange/status`, `exchange/schedule` |
| Kalshi | `POST` | `portfolio/orders`, `portfolio/events/orders`, `portfolio/intra_exchange_instance_transfer` (money between shards of the owner's own account; it cannot leave the account), `account/api_usage_level/upgrade` |
| Kalshi | `DELETE` | `portfolio/orders/<id>`, `portfolio/events/orders/<id>` |
| Alpaca, real and paper | `GET` | `v2/account`, `v2/account/activities[/<TYPE>]`, `v2/positions[/<id>]`, `v2/orders[/<id>]`, `v2/orders:by_client_order_id`, `v2/clock`, `v2/calendar`, `v2/assets[/<id>]`; market data: `v2/stocks[/<symbol>]/quotes|trades|bars|snapshot[s][/latest]`, `v1beta3/crypto/<loc>/[latest/]quotes|trades|bars|snapshots` |
| Alpaca, real and paper | `POST` | `v2/orders` |
| Alpaca, real and paper | `DELETE` | `v2/orders/<id>` (one order; there is no cancel-all and no close-position route) |

A forwarded path has no empty, `.` or `..` segment; a request body is 256 KiB at most (`413`);
a venue that does not answer in 30 seconds is a `502`; a venue whose secrets are missing is a `503`.

## The caps

Enforced atomically inside the `Gate` Durable Object before anything is signed, and only for the
three calls that can create an order on a real venue: Kalshi `POST portfolio/events/orders` and
`POST portfolio/orders`, Alpaca `POST v2/orders`. **Reads and cancels always pass**, whatever the
counters or the kill switch say. A cap is changed only by editing `wrangler.jsonc` and
redeploying, which is a change the owner makes, not one the VM can.

| Var | Deployed | Default in code | Meaning |
| --- | --- | --- | --- |
| `MAX_ORDER_USD` | `75` | `50` | Per-order notional. Kalshi: `count x price` in dollars (legacy cent prices and `buy_max_cost` are understood; an unpriced contract is charged its $1.00 settlement ceiling). Alpaca: `notional`, else `qty x` a price. A limit order uses the dearer of its own positive `limit_price` and the `X-LTCM-Reference-Price` header, which can therefore raise what it is worth and never lower it; a market order is priced from the venue's own quote plus 10%, never from the caller's header or a price field. Only `market` and `limit` orders are priced. |
| `MAX_ORDER_USD_KALSHI`, `MAX_ORDER_USD_ALPACA` | `75`, `75` | unset | A venue's own per-order cap. The tighter of it and `MAX_ORDER_USD` applies. |
| `MAX_DAY_USD` | `4000` | `400` | Notional for the whole trading day, both real venues together. |
| `MAX_DAY_ORDERS` | `2000` | `60` | Order count for the whole trading day, both real venues together. |
| `CAP_TIMEZONE` | `America/New_York` | the same | The calendar the day rolls on: the floor's own. |

Sized for two accounts of about $800 each: one order is never more than a tenth of an account,
and a day's submitted notional is a few times the floor's capital because resting quotes are
replaced as prices move. `league/constitution.py` repeats the three numbers so the House refuses
first and can say why; this is where they are enforced.

A refusal is `403` with `{ error, cap }` (`order`, `day_orders` or `day_notional`); the kill switch
is `423` with `{ error }` and stops **every** order-creating call on a real venue, exits included;
an order whose notional cannot be established is `400` rather than a pass, and a market order the
venue cannot quote is `503`. Money is exact BigInt arithmetic throughout and every partial cent
rounds **against** the order.

An Alpaca order is priced only as one instrument named by a top-level `symbol`, spelled as a stock
ticker (`AAPL`, `BRK.B`), a crypto pair (`BTC/USD`) or a standard OCC option symbol (a root of one
to six capital letters). Each of these is a `400` before any quote is read:
- an `order_class` other than `simple`, or any `legs` field (multi-leg, bracket, OCO, OTO);
- a `type` other than `market` or `limit`. A stop, stop-limit or trailing stop fills at market once
  it triggers, so nothing in its body bounds what it spends. `stop_price`, `trail_price` and
  `trail_percent` are not accepted;
- a field outside `ALPACA_ORDER_FIELDS` in `lib/caps.mjs`;
- a missing symbol, or any other spelling. An adjusted option contract (a digit in its root, as in
  `XYZ1261016P00005000`) is refused rather than priced, because it can deliver other than 100
  shares;
- a market order that carries a `limit_price`, a limit order without a positive one, or a body with
  both `qty` and `notional`.

These are the only shapes the House sends. Until Sept 23, 2026 a multi-leg order with no top-level
symbol was priced as a stock, so a $210 debit spread was metered at $2.10. Until the same day's
review, several other shapes were also underpriced:
- an adjusted-contract written put worth $5,000 was metered at $50.00;
- a market order carrying `limit_price: "0.01"` was metered from the caller's header at $1.00;
- a trailing buy was metered at the ask, though it cannot fill until the price has risen.

An order sent with `X-LTCM-Purpose: exit` skips the two dollar caps (not the order count, and not
the kill switch), so a position can always be closed however the day's budget was spent. The
header is the caller's own claim; the order count still bounds a VM that lies. The league's book
sets it on a sell, so an exit passes the dollar caps while an entry is still metered by them.

A reservation is returned only when the forward never reached the venue. A venue that answered at
all keeps its reservation, however it answered, and so does a timeout after dispatch: an
unconfirmed write is an order until reconciliation says otherwise.

## Jev shadow pilot

`POST /v1/typesafe/systemone` uses the Worker secret `TYPE_SAFE_TOKEN`. It admits only the
versioned `jev-1.13.0`, inline text/JSON state, and 1–16 explicit choice/noul questions. The
request body is limited to 64 KiB. This is an experiment interface; the trading and release
loops do not act on its answers. The shared lab supplies fallible classifications to research
context and evaluates them separately against future observations.

The external gate has a **$42 lifetime allowance** (`TYPESAFE_PILOT_USD`: $20 until Sept 23, 2026,
when it was aligned to the metered $16.14 plus the owner's funded $26) **and 500,000 accepted calls**. It was to expire at
2026-09-21 11:01:16.977 UTC (`TYPESAFE_PILOT_END`); `TYPESAFE_PERSISTENT` is `true`, so it no longer
expires and only the allowance and the call count close it ($16.12 and 137,961 calls used at
23:50Z Sept 22, 2026). These counters never reset by day, month or deployment. Retained
$20 `foundation-review` campaign reservations back the first $20 of the allowance; the rest is the
owner's funded Jev balance. This
is a cross-provider pilot earmark from that existing research allocation, not an OpenAI bill
or an addition to the phase budget. Keep that reservation until the route has expired or is
closed and its provider bill is reconciled. `/v1/health.typesafe` reports Jev usage separately.

Every request needs a unique `X-LTCM-Request` (letters, digits, colon, underscore, hyphen;
maximum 128 characters). Admission stores that id and the request digest before forwarding.
Reusing an accepted identity returns 409, including after a timeout or restart; it never buys
a second request. Store the response durably on the caller and investigate ambiguous results
instead of silently generating a new id. No provider retries or redirects are followed.

At the published $0.042/M input-token price and free output, a 64k-token request costs less
than $0.003; the gate reserves a full cent. Missing/invalid usage or ambiguous errors retain
the cent. Valid usage settles in microdollars; a charge exceeding its reservation closes
further admission. `X-LTCM-Cost-USD` has six decimals; `X-LTCM-Cost-Known` distinguishes a usage
charge from a retained reservation. Output types and distributions are checked, but a valid
shape is not evidence that a decision is correct. Source: [TypeSafe models](https://docs.typesafe.ai/models).

## The frontier month

`POST /v1/frontier/responses` forwards one call to `https://api.openai.com/v1/responses` with
`OPENAI_SECRET_KEY`, inside `FRONTIER_MONTH_USD` (**$408** a UTC calendar month since Sept 23, 2026: metered $308.46 plus the owner's funded ~$100; it was $374, and $300 before Sept 21). Existing monthly
spend remains counted when the configured cap increases; the House's immutable campaign
allowance is an additional restriction.
A call is priced twice. Before it leaves, at its worst case: every byte of the request as input at
one byte per token plus framing, at the long-context ceiling, every allowed output token used; that much is reserved, and a call whose
worst case does not fit in what is left of the month is a `402` with `cap: frontier_month`. After
it returns, at the usage the provider reports, and the difference is given back. The reply carries
`X-LTCM-Cost-USD` with six decimal places, and `X-LTCM-Agent` on the request attributes the
cost in `/v1/health`. The aggregate health display still rounds to cents. Meter receipts must
retain microdollars: rounding a cheap Luna receipt to one cent previously created a false
campaign reservation breach, found and corrected during the Jev comparison.

### Compute follows profit (Sept 23, 2026)

The month's cap grows with verified profit on the two real accounts:

```
cap = FRONTIER_MONTH_USD + COMPUTE_PROFIT_SHARE x max(0, venue_equity - EQUITY_BASELINE_USD)
```

The cap is also held to `FRONTIER_MONTH_MAX_USD` when that var is set.

- **How equity is read.** The gateway reads `venue_equity` itself, read-only, with the venue keys it already holds:
  - Kalshi: `GET /portfolio/balance`, cash plus the positions' value;
  - Alpaca: `GET /v2/account`, `equity`.

  The House cannot report its own profit to buy compute. Both reads round down, and a missing Kalshi position value counts as nothing.
- **Caching.** A reading is kept ten minutes. It is taken again by the next `/v1/frontier/responses` after that, which reads Kalshi and then Alpaca with an 8-second timeout each.
- **Health never reads the venues** (Sept 23, 2026). `/v1/health` reports the stored reading and never refreshes it. The House reads its kill switch there on the order path and treats a slow answer as the switch engaged, and until this change a health request more than ten minutes after the last reading read both venues inline. So the cap and parts it reports are as old as the last frontier call's reading, and once that reading is twenty minutes old it reports exactly `FRONTIER_MONTH_USD` until the next frontier call reads the accounts again. The House reads its mirror of the raise from `/v1/health`, so its line follows the same reading.
- **Dials:**
  - `COMPUTE_PROFIT_SHARE`: 0.3.
  - `EQUITY_BASELINE_USD`: the live grant's capital, $517.75 at Kalshi plus $500 at Alpaca, which is $1017.75.
- **Arithmetic.** All in micro-dollars. The raise is rounded down.
- **The old cap is the floor, and nothing fails open.** The cap is exactly `FRONTIER_MONTH_USD` when any of these is true:
  - indexing is not configured (no share, a share outside 0 to 1, or no baseline);
  - there is no month configured;
  - either venue fails to answer, or answers without its field (half a reading is no reading);
  - the last good reading is more than twenty minutes old.
- **Health.** `/v1/health` `frontier` reports:
  - the cap in force as `cap_usd`;
  - the configured month as `base_cap_usd`;
  - the parts as `profit_index`: `share`, `baseline_usd`, `max_cap_usd`, `equity_usd`, `kalshi_usd`, `alpaca_usd`, `profit_usd`, `earned_usd` (what the share buys), `bonus_usd` (what the cap in force carries of it), `read_at`, `read_ok` and `reason`.
- **The House's line.** The House's own OpenAI line (the burst in `league/campaigns.py`) is raised by exactly `cap_usd - base_cap_usd`, never more, and that raise lapses if the gateway has not been read for thirty minutes (`CampaignBudget.mirror_gateway_bonus`).
- **Setting the baseline.** Set `EQUITY_BASELINE_USD` to the accounts' equity at the grant, so that only profit raises the cap. Check `profit_index.equity_usd` against it after deploying.
- **The cap stays inside funded money.** The raise could otherwise pass the OpenAI account's prepaid credit. The owner's rule is that no cap exceeds funded money, so `FRONTIER_MONTH_MAX_USD` is set to the month ($408) and the raise buys nothing until the owner funds more.
  - Health still reports what profit earned: `profit_index.earned_usd` beside the `bonus_usd` the cap carries.
  - Raise `FRONTIER_MONTH_MAX_USD` with each OpenAI top-up bought from profit.
- **Sail is not indexed.** Sail is prepaid and cannot be funded from profit; auto-recharge is the owner's decision.

`FRONTIER_MODELS`, in dollars per million tokens. A model absent from it is a `403`: an unpriced
call is an uncapped one.

| Model | Input (cache write) | Uncached | Cached input | Output |
| --- | --- | --- | --- | --- |
| `gpt-6-astra` | 12.50 | 10.00 | 1.00 | 50 |
| `gpt-5.6-sol` | 5.00 | 4.00 | 0.40 | 20 |
| `gpt-5.6-terra` | 2.50 | 2.00 | 0.20 | 12 |
| `gpt-5.6-luna` | 0.25 | 0.20 | 0.02 | 1.20 |
| `gpt-6-sol` | 2.50 | 2.00 | 0.20 | 10 |
| `gpt-6-luna` | 0.125 | 0.10 | 0.01 | 0.50 |

Input is priced at the cache-write rate, the dearest an input token can be, so the meter errs
high. When the usage block reports `input_tokens_details.cache_write_tokens` (GPT-5.6 and later
do), the written tokens settle at the write rate, cached reads at the cached rate and the rest at
`uncached`, the list rate; a table row without `uncached` settles every unread token as a write,
as before. Requests above 272,000 input tokens use the configured long-context rates (2x input
and cached input, 1.5x output). Only inline text and standard service are admitted; stored
conversations, attachments, built-in tools and other service tiers have no price here.
Prompt-cache hints are admitted because they change the bill only through that usage block
(Sept 22, 2026): `prompt_cache_key` (`[A-Za-z0-9._:-]{1,64}`), `prompt_cache_retention`
(`in_memory` or `24h`), `prompt_cache_options` (`mode` implicit or explicit, `ttl` `30m`, no
`prewarm`) and, on system, developer and user messages, `input_text` blocks carrying
`prompt_cache_breakpoint: {"mode": "explicit"}`, at most four per request. Anything else is a `400`.
These are conservative estimates, not provider invoices. Also refused: a streaming or background call (`400`: the usage that settles the bill arrives
only with a complete response), `max_output_tokens` missing or outside 1 to 16,000 (`400`), a body
over 512 KiB (`413`), no `OPENAI_SECRET_KEY` (`503`). A provider `4xx` is settled at zero; a
provider error, a timeout (570 seconds since Sept 21, 2026; it was 280) or a reply with no readable
usage keeps its whole reservation, because unknown is not free. Since Sept 23, 2026 the House settles
its own campaign commitment for a verified call at this meter's `X-LTCM-Cost-USD`, and releases the
hold of a refused (4xx) call; a call with no answer keeps its worst case on both lines, until the
House absorbs its own hold into this month six hours later (below).

### What the month counts (Sept 24, 2026)

`/v1/health` `frontier` splits the month three ways, and the House's OpenAI meter reads all of it
(`league/campaigns.py` `observe_month`):

- `spent_usd`: every call's cost, or its hold while it has none. It falls whenever a call settles
  below its worst case, and starts at zero on the 1st (UTC).
- `inflight_usd`: the holds of calls reserved and not yet settled, to the microdollar. A call cut
  off before it could settle (a deploy or a crash mid-call) stays here, and in `spent_usd`, for the
  rest of the month. A hold reserved before Sept 24, 2026 was never counted here.
- `settled_usd`: `spent_usd` less `inflight_usd`, to the microdollar. It only rises.
- `previous`: the month that ended, with its `spent_usd` and `settled_usd` as they stood when it
  ended, or null. The next month's first call keeps it (`FRONTIER_PREVIOUS_KEY`). A call still in
  flight at midnight is refused its settle (its month has ended), so the old month keeps its whole
  worst case.

How a call settles:

| The answer | Settled at |
| --- | --- |
| `2xx` with a usage block | its metered cost |
| `2xx` whose usage cannot be read | its whole worst case |
| a provider `4xx` | zero: refused before any generation |
| `503` whose body is OpenAI's error object of type `service_unavailable_error` | zero (since Sept 24, 2026): OpenAI says the model lacked the capacity to process the request ([error codes](https://developers.openai.com/api/docs/guides/error-codes)). Two such answers on Sept 22, 2026 kept their worst case, $2.02 for one |
| any other `5xx`: a `500` `server_error`, a `502`, a `504`, a `503` from an edge | its whole worst case: a server error can come after the model has worked, and an edge answers for a call the provider may still have billed |
| no answer (a timeout, a network error), or an answer cut off mid-body | its whole worst case. Until Sept 24, 2026 a body cut off mid-read threw past the settle ("error code: 1101") and left the hold in flight |

**The House's meter.** The House reads this month on every tick and feeds its OpenAI meter a
figure that never falls: the month's highest `spent_usd` plus the finals of earlier months
(`previous`). An OpenAI hold of its own with no answer, made since the meter began counting and
older than six hours, is absorbed into that figure: the gateway reserved the call's worst case
here before calling OpenAI, so this month already counts it once. It releases nothing unless this
month's `settled_usd` has grown by at least what the House settled since its anchor (see
`docs/operations.md`, The OpenAI meter). Deploy the gateway before the House release that reads
these fields; a House that finds no `settled_usd` releases nothing.

## Pull requests

The frontier model proposes changes to the floor: a strategy, a tool, a game dial, a lesson. A
change reaches the repository **only as a pull request**, and the credential that can open one
lives only here, like the venue keys. CI on GitHub judges each pull request
(`.github/workflows/merton.yml`) and that workflow merges the ones that pass. **There is
deliberately no merge route**, and nothing in the gateway approves, closes, force-pushes or deletes.

Every rule is enforced here first and by the repository's own CI (`league/ci.py`) again:

| Role | May write |
| --- | --- |
| `architect` | `league/strategies/…` |
| `toolsmith` | `league/tools/…`, `league/tests/test_tool_…` |
| `operator` | exactly `league/config.json` |
| `designer` | exactly `league/game.json` |
| `teacher` | `league/playbook/…` |

- A path is relative and normalized: no `..`, no `.`, no empty segment, no leading `/`, no
  backslash, no control character, no `.git…` segment, at most 200 characters. Any other path is a
  `403` that names it.
- Refused for every role, by name, even if a role's paths were loosened later:
  `league/constitution.py`, `ci.py`, `ledger.py`, `book.py`, `evaluator.py`, `stats.py`,
  `auditor.py`, `watchdog.py`, `safety.py`, `replay.py`, `updater.py`, and anything under
  `gateway/` or `.github/`.
- 1 to 12 files of UTF-8 text, 64 KiB each, 256 KiB a request; `slug` is
  `^[a-z0-9][a-z0-9-]{1,48}$`; the title is one line of 120 characters, the body 8000. The pull
  request's body ends `Opened by Merton (<role>) through the LTCM gateway.`
- The branch is `merton/<role>/<slug>-<first 8 hex of sha256 over the files>`, so a retry of the
  same proposal is the same branch. **The DEPLOYED worker still emits the old `astra/` prefix**, and
  the merge workflow accepts both until the gateway is redeployed from this source: before it did,
  every proposal landed on a branch the guard, the judge and the merge job all ignored, and sat open
  for ever. A retry that finds its branch (the same tree, or the same
  files when `main` has moved since) and its open pull request makes nothing and returns them. A
  branch of that name holding anything else is a `409`, never overwritten; so is a proposal that
  changes nothing on `main`.
- `GITHUB_MAX_PULLS_PER_DAY` (**96**) a UTC day, counted in the `Gate` in one step; over it is
  `429`. What is counted is a branch made: a refused proposal, a GitHub outage before the branch,
  and a retry cost nothing, and a branch request that never answered is counted as made.
- Without `GITHUB_TOKEN` or `GITHUB_REPO` both routes are `503 {"error": "GitHub is not
  configured."}`. Any GitHub failure is a `502` with one short line that names the step; the
  token is stripped from it even if GitHub echoed it.

The reply is `{"ok": true, "branch", "number", "url", "head"}`.

## The watchdog, and the mail

The `*/5 * * * *` cron reads the **production** checkpoint
(`https://blakewoods.us/api/capital/checkpoint`), the Sail usage summary and the state of the
House box (`SAILBOX_ID`), then does the smallest thing that helps.

**While the production tape is empty it touches nothing.** A checkpoint that cannot be read (the
route is a `404` until the floor first publishes to production) is recorded as
`checkpoint_unreachable` and the pass neither resumes nor restarts anything. The league's test and
canary tapes are other URLs and are never read. So the watchdog starts acting at go-live, when
the House first publishes to the production tape, and stops again if that tape is cleared.

Once there is a checkpoint:

- older than `CHECKPOINT_STALE_SECONDS` (deployed `1800`; `900` in code) → run `RESTART_COMMAND`
  (`/workspace/restart.sh`) on the box via `POST /v1/sailboxes/<id>/exec` with an
  `idempotency_key`, at most once per `RESTART_COOLDOWN_SECONDS` (1800). The attempt itself opens
  the cooldown, confirmed or not, so a box that cannot come back is not restarted in a loop.
- box `paused` or `sleeping` **and** Sail credit above `RESERVE_USD` (10) → resume it, then run the
  restart. A top-up can restore this account-level availability check without a human step; it cannot renew the House campaign allowance or its expiry.
- box stopped with credit at or under the reserve → left stopped, and the owner is told.
  Resuming a box that cannot pay for a model call only spends the remainder faster.
- box `terminated` or otherwise unrecoverable → never resumed.

`/workspace/restart.sh` (written by `scripts/floor_box.py`) signals the running
`python -m league run`; the box's supervisor then starts a fresh House from `/workspace/current`
thirty seconds later. It never starts a supervisor that is not up, so a House the owner stopped
stays stopped: a resumed box then costs its hourly rate and trades nothing.

**Two watchdogs, two jobs.** This one keeps the box alive and the loop running. The in-box one,
`league/watchdog.py`, only chooses *which release* `current` points at: it stages a deploy, runs
it as a canary, promotes it, watches its health and rolls back. It never touches Sail and never
publishes; this one never touches releases. Both restart the loop through the same `restart.sh`,
and a restart from either is the same harmless signal.

Mail goes out through the `EMAIL` binding, at most once per six hours per kind
(`ALERT_EVERY_SECONDS`), whether or not there is a checkpoint:

- `sail_balance_low`: credit under `LOW_BALANCE_USD` (60) or under `LOW_RUNWAY_DAYS` (7) of runway;
  `sail_balance_critical`: under `CRITICAL_BALANCE_USD` (20) or `CRITICAL_RUNWAY_DAYS` (2);
  `floor_stopped`: credit at or under the reserve, or a checkpoint whose `budget.mode` is
  `stopped`. Runway is credit above the reserve over the trailing day's Sail spend.
- `box_not_running`: a recovery failed, the box is stopped and this pass did not bring it back,
  or a restart went out earlier and the floor is still quiet. A parked box is therefore mailed
  about every six hours even before go-live.
- `kill_switch_engaged`, for as long as it is engaged; `caps_exhausted`.
- `daily_digest` in the 21:00 UTC hour: equity, day P&L, orders, Sail spend, runway, box state.

A mail failure never takes the pass down, and an alert that did not send is not recorded as sent.

Sail reports money as fractional US **cents**, so a `balance` of `3106.14` is $31.06. Its
`range` parameter understands `1h`, `6h`, `24h`, `7d`, `30d` and `period` and silently falls back
to 30 days for anything else, which is why `SAIL_USAGE_RANGE` is `24h` and not `1d`.

## Setting it up

The owner runs these; nothing in this repository ever reads or writes a venue secret. Each command
prompts for the value on a hidden line. Run them from `gateway/`.

```bash
cd gateway

# The runtime's bearer token: random, 32+ characters. The House box gets this one and no other.
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
npx wrangler secret put GATEWAY_TOKEN

# Kalshi: the key id (UUID) and the RSA private key, PKCS#8 or PKCS#1 PEM, BEGIN/END lines and
# all. Paste the whole file for the key.
npx wrangler secret put KALSHI_KEY_ID
npx wrangler secret put KALSHI_PRIVATE_KEY

# Alpaca, the real account: the key id and the secret key.
npx wrangler secret put ALPACA_KEY_ID
npx wrangler secret put ALPACA_SECRET_KEY

# Alpaca, the paper account (venue alpaca-paper): its own key pair, from the paper dashboard.
npx wrangler secret put ALPACA_PAPER_KEY_ID
npx wrangler secret put ALPACA_PAPER_SECRET_KEY

# OpenAI, for /v1/frontier/*. Without it those two routes answer 503.
npx wrangler secret put OPENAI_SECRET_KEY

# Sail, for the watchdog: the API key. Without it the watchdog only reports.
npx wrangler secret put SAIL_API_KEY

# GitHub, for /v1/github/pr: a FINE-GRAINED personal access token (github.com/settings/
# personal-access-tokens), never a classic one. Repository access: "Only select repositories",
# this one repository (the GITHUB_REPO var). Repository permissions: Contents read and write,
# Pull requests read and write, and nothing else (Metadata read is added by GitHub and cannot be
# removed). No Workflows, no Administration, no Actions: the token must not be able to edit CI
# or the branch rules, and with no Workflows permission GitHub itself refuses any push that
# touches .github/workflows. Without it the two GitHub routes answer 503.
npx wrangler secret put GITHUB_TOKEN
```

The check runs the status route counts are readable with the permissions above on a public
repository. On a private one GitHub asks for Checks read as well; if
`GET /v1/github/pr/<n>` answers `502 … (check runs)`, add that one read permission and nothing
more.

The eleventh secret, `GATEWAY_ADMIN_TOKEN`, is the owner's own: provision it with
`python3 scripts/gateway_admin.py provision` from the repository root, which generates it, stores
it mode 600 under `.data/ltcm/keys/` and runs `npx wrangler secret put GATEWAY_ADMIN_TOKEN` in
`gateway/` for you. It is never uploaded to a Sailbox. `python3 scripts/gateway_admin.py unkill`
releases the kill switch with it; `kill` and `status` use the ordinary token.

Mail needs no secret: it goes out through the `EMAIL` binding (`send_email` in `wrangler.jsonc`),
from `ALERT_FROM` to `ALERT_TO`. Without the binding the watchdog still runs and simply does not
mail.

Check what is placed with `npx wrangler secret list`: it prints names, never values, and should
show exactly the eleven names above. On Sept 20, 2026 all eleven are placed. `GITHUB_TOKEN` went in that morning, and two of Merton's
pull requests were opened through this route, judged by CI and merged with no human in the loop
(#7, a teacher's lesson, and #8, an operator's change to a dial, which took effect on the running
floor within the hour).

The first run's Coinbase secrets (`COINBASE_KEY_NAME`, `COINBASE_API_SECRET`) are obsolete:
nothing reads them, and they were already gone from the deployed Worker on Sept 20. If the list
ever shows one, delete it:

```bash
npx wrangler secret delete COINBASE_KEY_NAME
npx wrangler secret delete COINBASE_API_SECRET
```

Then set the House box's id in `wrangler.jsonc` and deploy:

```jsonc
"vars": { "SAILBOX_ID": "sb_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", ... }
```

```bash
npx wrangler deploy
curl -s -H "Authorization: Bearer $GATEWAY_TOKEN" https://ltcm-gateway.<subdomain>.workers.dev/v1/health
```

## How the House uses it

`league/config.json` names the Worker in `gateway_url`, and the House box's `.env` holds
`GATEWAY_TOKEN`. `league/venues.py` builds every venue adapter in gateway mode: a `GatewaySigner`
that carries only the bearer token and a `VenueClient` (both from `ltcm/adapters`) that rewrites
every call onto `<gateway_url>/v1/<venue>/...` and drops the venue auth headers. There is no
direct, key-in-process mode in the league: no key file, key id or venue secret exists on Sail.
`league/frontier.py` calls `/v1/frontier/responses`, `league/merton.py` calls `/v1/github/pr`, and
`league/service.py` reads `/v1/health` so the House knows the kill switch is engaged and can refuse
first. The adapters' gateway mode is covered by `ltcm/tests/test_adapters_gateway.py`.

## Working on it

```bash
cd gateway
npm install
npm run check   # node --check on the worker and every module
npm test        # node --test test/*.test.mjs: 104 tests, WebCrypto, no network, no key material on disk
npx wrangler deploy
```

Run the check and the suite, read the real result, and only then deploy: never chain a deploy on
a filter's exit status.

Every key the suite uses is generated in-process for the test that uses it: signatures are
checked by verifying them with the public half of the key that signed them, so the recipes are
tested rather than asserted.
