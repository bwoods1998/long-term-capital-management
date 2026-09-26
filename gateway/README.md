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
                                       (no credential at all)          ->   one public http(s) page, for research
                                       caps, budgets, kill switch (one Durable Object)
                                       watchdog cron (checkpoint, balance, box)
```

## Endpoints

Every endpoint but one takes `Authorization: Bearer $GATEWAY_TOKEN`, compared with
`timingSafeEqual`. `/v1/unkill` takes `$GATEWAY_ADMIN_TOKEN` instead, and only that. Anything else
is `401`, including a deployment whose token is missing or shorter than 32 characters.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/v1/health` | Kill switch, caps, today's order counters, the caps by maximum loss on the real Alpaca account (`max_loss`: the equity reading and its age, the per-order cap now, today's opening maximum loss and its cap, whether opens and credit opens are admitted, orders today of 300), the frontier month (spent, what of it is settled and what is still in flight, the month that ended, the cap in force and its profit-indexed parts from the stored equity reading, calls, cost by agent), today's pull requests, the watchdog's record, Sail balance, runway and box state, and when each alert last went out. It never reads a venue itself (Sept 23, 2026). |
| `POST` | `/v1/kill` | Engages the kill switch. The runtime token may: stopping is never gated. |
| `POST` | `/v1/unkill` | Releases it. **Owner token only**; the runtime token is a `401` here. |
| `GET`/`POST`/`DELETE` | `/v1/kalshi/<path>` | Signs `timestamp + METHOD + /trade-api/v2/<path>` with RSA-PSS SHA-256 (salt 32) and forwards to `https://api.elections.kalshi.com/trade-api/v2/<path>` with the query string. Status and body come back verbatim. |
| `GET`/`POST`/`DELETE` | `/v1/alpaca/<path>` | Adds `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY` and forwards to `https://api.alpaca.markets/<path>`, or to `https://data.alpaca.markets/<path>` when the path is a market-data one (`v2/stocks/`, `v1beta3/`). The real account. |
| `GET`/`POST`/`DELETE` | `/v1/alpaca-paper/<path>` | The same paths with the paper key pair, forwarded to `https://paper-api.alpaca.markets/<path>` (market data still goes to the data host). Never metered, and not stopped by the kill switch: see below. Its option orders are held to the defined-risk shapes ([Multi-leg structures](#multi-leg-structures-sept-25-2026)). |
| `GET` | `/v1/kalshi/ws-auth` | The three handshake headers for Kalshi's WebSocket (`/trade-api/ws/v2`), good for 30 seconds. The only route that hands the VM credential material, and what it hands over is short-lived and read-only: Kalshi takes no order over its WebSocket. The first run used it; the league does not. |
| `POST` | `/v1/frontier/responses` | One metered call to the frontier model (OpenAI Responses API). See [The frontier month](#the-frontier-month). |
| `POST` | `/v1/typesafe/systemone` | Bounded Jev shadow pilot; requires `X-LTCM-Request`, pinned `jev-1.13.0`, inline state and choice/noul questions. Uses `TYPE_SAFE_TOKEN` only in this Worker. |
| `GET` | `/v1/frontier/models` | The model ids the key can reach, and which of them are priced. Free. |
| `POST` | `/v1/github/pr` | Opens one pull request from a proposal `{role, slug, title, body, files}`. See [Pull requests](#pull-requests). Not stopped by the kill switch: it moves no money. |
| `GET` | `/v1/github/pr/<number>` | That pull request's `state`, `merged`, `mergeable_state`, `head` and its check runs counted into `success`, `failure` or `pending`, so the VM watches CI with no GitHub credential. Free. |
| `POST` | `/v1/web/fetch` | Reads one public page for research, `{"url", "agent"}`, and answers its readable text. No credential is sent; private, local and own-domain addresses are refused on the request and every redirect; 3,000 pages a UTC day across the floor. See [Research reads the web](#research-reads-the-web). Not stopped by the kill switch: it moves no money. |
| `POST` | `/v1/notify` | Mails the owner one trade notice composed here from the facts posted (`kind` of `trade`, `settled`, `test`, `disk_low`, or `live_stop` since Sept 26, 2026: `{stop: drawdown|daily|reconciliation|assignment, text, equity, at}` when a real-money stop trips; 32 KiB at most). A `notice_id` makes a repeat a no-op for 48 hours; `NOTIFY_MAX_PER_DAY` (300) a trading day, then `429`. The first run's desks used it; the league does not call it. |

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
| `MAX_ORDER_USD` | `75` | `50` | Per-order notional, **Kalshi only** since Sept 26, 2026 (the real Alpaca account is capped by maximum loss, below). Kalshi: `count x price` in dollars (legacy cent prices and `buy_max_cost` are understood; an unpriced contract is charged its $1.00 settlement ceiling). Alpaca: `notional`, else `qty x` a price. A limit order uses the dearer of its own positive `limit_price` and the `X-LTCM-Reference-Price` header, which can therefore raise what it is worth and never lower it; a market order is priced from the venue's own quote plus 10%, never from the caller's header or a price field. Only `market` and `limit` orders are priced. |
| `MAX_ORDER_USD_KALSHI` | `75` | unset | Kalshi's own per-order cap. The tighter of it and `MAX_ORDER_USD` applies. `MAX_ORDER_USD_ALPACA` is gone (Sept 26, 2026): not deployed, and not read for the real Alpaca account if set. |
| `MAX_DAY_USD` | `10000` | `400` | Kalshi's notional for the trading day; and the absolute ceiling on the real Alpaca account's opening maximum loss a day (the owner's whole envelope). |
| `MAX_DAY_ORDERS` | `300` | `60` | Order count for the whole trading day, both real venues together, exits included (under the venue's 390 a day). |
| `MAX_ORDER_MAX_LOSS_USD`, `MAX_ORDER_EQUITY_SHARE` | `1000`, `0.15` | the same | The real Alpaca account: one OPENING order's maximum loss is at most the lower of the two, the share taken of the account's equity. |
| `MAX_DAY_EQUITY_SHARE` | `1.0` | the same | The real Alpaca account: today's opening maximum loss, this order included, is at most this share of equity, and never above `MAX_DAY_USD`. |
| `CREDIT_MIN_EQUITY_USD` | `2000` | the same | A credit structure (`credit_vertical`, `iron_condor`, `iron_butterfly`) opens on the real account only at this equity or more. |
| `EQUITY_CAP_MAX_AGE_MS` | `120000` | the same | The oldest equity reading an opening order is sized against; older, the order path reads the account again. |
| `CAP_TIMEZONE` | `America/New_York` | the same | The calendar the day rolls on: the floor's own. |
| `OPTION_STRUCTURES_REAL` | `debit_vertical,credit_vertical,iron_condor,iron_butterfly,long_butterfly` | `off` | The multi-leg structure types the real Alpaca account admits, comma-separated: since Sept 26, 2026 the five Alpaca closes in one order. `off`, or any name that is not a type, admits none. See [Multi-leg structures](#multi-leg-structures-sept-25-2026). |

Sized for two accounts of about $800 each: one order is never more than a tenth of an account,
and a day's submitted notional is a few times the floor's capital because resting quotes are
replaced as prices move. `league/constitution.py` repeats the three numbers so the House refuses
first and can say why; this is where they are enforced.

### Caps by maximum loss (Sept 26, 2026)

The options-swarm plan (`docs/goals/LTCM_OPTIONS_SWARM.md`, "Money") sizes by **maximum loss**, never by
premium, and the real Alpaca account's caps follow its equity (`lib/account.mjs`):

- **The reading.** The gateway reads the equity itself, `GET v2/account` (`equity`) with the real keys, no redirect
  followed, rounded down, and keeps it in the gate (`alpaca-equity`, apart from the profit index's reading). An
  opening order uses a reading at most `EQUITY_CAP_MAX_AGE_MS` old and reads the account again otherwise; with no
  such reading it is a `503` (`Retry-After: 30`) that reserves and sends nothing, and the gate checks the age again
  itself (`cap: equity`). Health reports the reading and never takes one.
- **Opens and exits are read from the order, never from `X-LTCM-Purpose`.** Opens: a multi-leg open of an admitted
  type (its maximum loss) and a single-leg `buy_to_open` (premium x 100 x qty). Exits: a multi-leg close, a single-leg
  `buy_to_close` (both only when the account holds what they close), a single-leg `sell_to_close`, and a stock close.
  An exit never waits on the equity read and meets no dollar cap.
- **The caps.** An open's maximum loss is at most the lower of `MAX_ORDER_MAX_LOSS_USD` and `MAX_ORDER_EQUITY_SHARE`
  of equity (`cap: order`); today's opening maximum loss with it at most `MAX_DAY_EQUITY_SHARE` of equity and never
  above `MAX_DAY_USD` (`cap: day_max_loss`); a credit type opens only at `CREDIT_MIN_EQUITY_USD` or more
  (`cap: credit_equity`). Every order, exits included, counts against `MAX_DAY_ORDERS`; the kill switch is unchanged.
- **Stock closes assigned shares only.** The one stock order the real account takes is a sale of a stock it holds
  long, or a buy covering a stock it holds short, for at most what it holds available (`qty_available`), in shares,
  market or limit: read from its signed positions (a `424` when they cannot be read) and reserved as an exit at one
  micro-dollar. Every other stock order, and every crypto order, is a `400`. `alpaca-paper` is unchanged.

A refusal is `403` with `{ error, cap }` (`order`, `day_orders`, `day_notional`, `day_max_loss` or `credit_equity`); the kill switch
is `423` with `{ error }` and stops **every** order-creating call on a real venue, exits included;
an order whose notional cannot be established is `400` rather than a pass, and a market order the
venue cannot quote is `503`. Money is exact BigInt arithmetic throughout and every partial cent
rounds **against** the order.

An Alpaca order is priced only as one instrument named by a top-level `symbol`, spelled as a stock
ticker (`AAPL`, `BRK.B`), a crypto pair (`BTC/USD`) or a standard OCC option symbol (a root of one
to six capital letters). Each of these is a `400` before any quote is read:
- an `order_class` other than `simple`, or any `legs` field (multi-leg, bracket, OCO, OTO), except a
  multi-leg order of a type `OPTION_STRUCTURES_REAL` admits (none as deployed; below);
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

### Multi-leg structures (Sept 25, 2026)

The options-desk run (`docs/goals/LTCM_OPTIONS_DESK.md`, amended by the owner on Sept 25, 2026)
lets options agents trade level-3 **defined-risk** structures. `lib/caps.mjs` reads a multi-leg
order (`order_class: "mleg"`, the shape in Alpaca's
[level-3 guide](https://docs.alpaca.markets/docs/options-level-3-trading)) as ONE structure from its
legs alone, by the rules of the structure spec that `league/structures.py` implements:

| Type | Legs (one root, whole contracts, no contract twice) |
| --- | --- |
| `debit_vertical` | one long, one short, one expiry and right; the long leg the dearer strike (lower call, higher put) |
| `credit_vertical` | the same, the short leg the dearer strike |
| `iron_condor` | long put < short put < short call < long call, one expiry |
| `iron_butterfly` | the same with the short put and short call at one strike |
| `long_butterfly` | one right and expiry: long 1 low, short 2 middle (`ratio_qty` 2), long 1 high, equal wings |
| `calendar` | one right and strike: short the near expiry, long the far |
| `diagonal` | one right: short near, long far, the long strike at least as favourable (a call's lower, a put's higher) |
| `long_straddle`, `long_strangle` | a long call and a long put of one expiry, one strike or two |

The order around the legs is `qty` (whole structures), `type: "limit"`, `time_in_force: "day"`,
`limit_price`, 2-4 `legs` of exactly `{symbol, ratio_qty, side, position_intent}` (a standard OCC
symbol, `ratio_qty` 1 or a butterfly body's 2, a side that agrees with the intent), an optional
`client_order_id`, and nothing else: no top-level `symbol` or `side`. A structure opens whole (every
leg `buy_to_open` or `sell_to_open`) and closes whole (every leg `sell_to_close` or `buy_to_close`,
named by what each leg was). Each of these is a `400` naming the reason, on both accounts:
- a short leg whose right has no long leg: *"A short leg with no long leg of its right covering it
  is a naked short: refused."*;
- a ratio other than a butterfly's body: *"A ratio_qty other than a long butterfly's body of 2 leaves
  a leg uncovered: refused."*; a broken-wing butterfly; a calendar or diagonal whose short leg
  expires last; a diagonal whose long strike is less favourable; any leg set that is not a type;
- legs that open and close at once (legging in or out, or a roll), mixed roots, a contract twice;
- a `limit_price` of the wrong sign (below), zero on an open, a credit at or over the collateral, or
  a debit at or over a bounded structure's maximum value (the checks `structures.held_limit` makes).
  A close at zero passes: it can only give a worthless structure away, or buy one back for nothing,
  which the expiry-day close of a structure bid at zero must be able to send.

**The sign of `limit_price`.** Alpaca's
[orders reference](https://docs.alpaca.markets/reference/postorder) (read Sept 25, 2026): for `mleg`,
"a positive value indicates a debit ... a negative value signifies a credit". alpaca-py's reference
says the same; the level-3 guide's own iron-condor example (a positive `1.80` for a short condor)
contradicts it and is not followed. Opening a debit type and buying back a credit type are debits
(positive); opening a credit type and selling a debit type to close are credits (negative). A limit
of the other sign is refused, never re-read: a short condor opened at a positive limit would PAY to
sell premium.

**The practice account** (`alpaca-paper`) forwards every type, opened and closed, unmetered and past
the kill switch as before. Its other option orders pass only as a single-leg `buy_to_open`,
`sell_to_close` or `buy_to_close` (the last can only buy back a short the account holds: the book's
repair of an unmatched short leg); a single-leg `sell_to_open` is a naked short and refused, and so is
a single-leg option with no `position_intent`, an option named by an asset id, or a field the check
decides on (`symbol`, `legs`, `order_class`, `position_intent`, `side`) spelled any other way. A body
that is not JSON is a `400`. Stock and crypto orders pass exactly as before.

**The real account** refuses every multi-leg OPEN while `OPTION_STRUCTURES_REAL` is `off` (as
deployed until Sept 26, 2026; it now names the five types Alpaca closes in one order), and an open of any type the variable does not name. A type it names is metered at its **maximum loss**: a debit type at
`limit_price x 100 x qty`, a credit type at `(collateral - credit) x 100 x qty` (the collateral is the
width, or a condor's wider wing), against the caps by maximum loss like any open (above; until Sept 26, 2026
`MAX_ORDER_USD_ALPACA`'s $75): at $500 of equity a $0.70 debit vertical is $70 and passes 15% of it, a $0.80 one is refused. The open or close is read
from the legs' `position_intent`, never from `X-LTCM-Purpose`: an open labelled an exit is still
metered. A close takes risk off and is metered at zero; the gate counts every order and refuses a
zero reservation, so a close reserves one micro-dollar as an exit (health rounds it up to a cent):
the kill switch and the order count stop it, the dollar caps do not. Since Sept 25, 2026 (the route's
review, MINOR 1) a real close is admitted only when the account **holds every leg it closes** -- a
`sell_to_close` leg held long and a `buy_to_close` leg held short, at least `qty x ratio_qty` contracts
each -- read from a signed `GET v2/positions` on the real account, reused for `POSITIONS_CACHE_MS`
(5 s); a close of a leg not held is a `400` (it would open a position), and positions that cannot be
read are a `424` that reserves nothing (a 4xx, never a 5xx: the House's adapter reads a 5xx as "the
venue may have it" and would hold the close as unknown for a minute of polls; a 4xx is sent again at its
next tick). A leg counts what the account has **available** (`qty_available`, never more than `qty`), so
legs already committed to a resting close are not closed twice, and a close admitted from the cached
reading takes its legs out of it. The read never follows a redirect (it carries the real account's keys).
The practice account is unchanged.

**A short leg bought back alone** (Sept 25, 2026, the review of Deploy G, MAJOR 2). A single-leg option
order is long premium only on the real account (`buy_to_open`, `sell_to_close`), with one exception: a
`buy` with `buy_to_close`, the book's buy-back of a short leg a broken real structure left (an uneven
fill, a long leg sold alone, an assignment). It is admitted by the same rule as a structure close, read as
a one-leg close: the account's signed positions must show that contract held **short** for at least `qty`
(available), or it is a `400` ("A single-leg buy_to_close must buy back a short leg the real account
holds: ..."), and unread positions are a `424`. Admitted, it is an exit whatever `X-LTCM-Purpose` says,
reserved at one micro-dollar (the kill switch and the order count stop it, the dollar caps do not), its
limit uncapped, and it leaves the cached reading. Before this, the real route refused it as not long
premium and the naked short stayed on the account while the House retried it every reading.

**The list gates opens only** (the review of g/money, Sept 25, 2026). A real CLOSE of **any** defined-risk
type goes whatever `OPTION_STRUCTURES_REAL` says -- `off` included -- once the account's positions show
every leg held: it only takes risk off, and every shape rule (no legging, no naked short, the sign of the
limit) still holds on it. Until then `off` refused closes too, and `league.ci` makes `off` the only
configuration while O1 is off, so any gateway deploy from such a tree would have stranded a held
structure into expiry. Admitting a type to OPEN is a money-digest change the owner ratifies:
`OPTION_STRUCTURES_REAL` admits exactly the constitution's `allocator.option_spread_real_types` while
`allocator.option_spreads_real` (O1) is true, and `off` while it is false, and `league.ci`
(`check_structures`) refuses a tree where the two disagree, so the two change in one deploy. The gateway
can be deployed at `off` at any time, a structure held or not.

**Rollbacks while the real account holds a structure.** Never roll the House back past Deploy G, or past
Track P's Alpaca adapter, while the real book holds a structure: a House before G refuses every real
structure intent, closes included (only its 15:30 expiry close is sent, through an adapter that cannot
send one multi-leg order), and a House with G but without that adapter holds every real structure order
back, closes included (`House._structure_unsendable`: never leg by leg; an error alert says so once a
day). Close or let the House close the structure first, or roll forward.

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
only with a complete response), `max_output_tokens` missing or outside 1 to 16,000, or to the ceiling its role names (`400`), a body
over 512 KiB (`413`), no `OPENAI_SECRET_KEY` (`503`). A provider `4xx` is settled at zero; a
provider error, a timeout (570 seconds since Sept 21, 2026; it was 280) or a reply with no readable
usage keeps its whole reservation, because unknown is not free. Since Sept 23, 2026 the House settles
its own campaign commitment for a verified call at this meter's `X-LTCM-Cost-USD`, and releases the
hold of a refused (4xx) call; a call with no answer keeps its worst case on both lines, until the
House absorbs its own hold into this month six hours later (below).

### Flex and role ceilings (Sept 26, 2026)

- **Flex.** `service_tier: "flex"` is admitted for a model whose `FRONTIER_MODELS` row carries a `flex` object (its
  rates, each at most the standard one; deployed at exactly half for `gpt-6-astra`, `gpt-6-sol` and `gpt-6-luna`); for
  any other model it is a `403`. A flex call is reserved at the standard worst case, and settled at the flex rates
  only when the answer reports `"service_tier": "flex"` (`X-LTCM-Billed-Tier` says which). A `429`, flex's capacity
  refusal, settles at zero like every provider `4xx`. Other tiers stay refused.
- **Role ceilings.** `X-LTCM-Role` (a slug) names the call's role, and `FRONTIER_ROLE_MAX_OUTPUT` (deployed
  `{"postmortem": 64000}`) that role's output ceiling; any other role, or none, keeps 16,000. The reservation is sized
  from the `max_output_tokens` admitted under it.

### What the month counts (Sept 24, 2026)

`/v1/health` `frontier` splits the month three ways, and the House's OpenAI meter reads all of it
(`league/campaigns.py` `observe_month`):

- `spent_usd`: every call's cost, or its hold while it has none. It falls whenever a call settles
  below its worst case, and starts at zero on the 1st (UTC).
- `inflight_usd`: the holds of calls reserved and not yet settled, to the microdollar. A call cut
  off before it could settle (a deploy or a crash mid-call) stays here, and in `spent_usd`, for the
  rest of the month. A hold reserved before Sept 24, 2026 was never counted here.
- `settled_usd`: `spent_usd` less `inflight_usd`, to the microdollar. It rises, except once at
  this deploy: a call the code before it reserved was never counted in flight, so when that call
  settles below its worst case, `settled_usd` falls by the difference. The House keeps the
  highest reading, so a fall only delays its check.
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
`docs/operations.md`, The OpenAI meter). While a reading is fresh, the House's own OpenAI line
never reads above this month's `cap_usd` less `spent_usd` (less what the House committed since
the reading), so aligning `FRONTIER_MONTH_USD` to the funded balance bounds the House too. Deploy
the gateway before the House release that reads these fields; a House that finds no `settled_usd`
releases nothing.

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

## Research reads the web

`POST /v1/web/fetch` with `{"url": "...", "agent": "..."}` (Sept 25, 2026, `lib/fetch.mjs`). The
House box's egress is exact-host -- it holds the Sail key and this Worker's token, and Sail's
allowlist ignores wildcards -- so a research agent's `web_fetch` (league/researcher.py) is read
here, on Cloudflare's egress, instead. The strategy boxes stay sealed: only the House calls this,
on an agent's behalf.

What goes out: a `GET`, with exactly three headers -- `User-Agent: LTCM-research/1.0
(+https://blakewoods.us/capital)`, an `Accept` for HTML, JSON, XML and text, and
`Accept-Language: en`. No cookie, no `Authorization`, no credential of any kind, and never a
header the caller sent.

What is refused, on the request **and on every redirect hop** (redirects are followed by hand,
`redirect: 'manual'`, at most 5), before anything is fetched:

- a scheme other than `http` or `https`; a port other than the scheme's default; a user or
  password in the URL; a URL longer than 2,048 characters;
- an IP-literal host that is not public: private (10/8, 172.16/12, 192.168/16), loopback,
  link-local (169.254/16, with the metadata address 169.254.169.254 named), CGNAT (100.64/10),
  multicast, unspecified, reserved and documentation ranges; for IPv6, anything outside global
  unicast (2000::/3) -- loopback, unspecified, IPv4-mapped, IPv4-compatible, NAT64, ULA
  (fc00::/7), link-local, multicast -- and the Teredo, 6to4 and documentation prefixes inside it.
  The URL parser has already turned `2130706433`, `0x7f.1` and `127.1` into `127.0.0.1`;
- `localhost`, `*.localhost`, `*.local`, `*.internal` (so `metadata.google.internal`),
  `*.home.arpa`, `*.localdomain`, a host with no dot, and this Worker's own domain (its host and,
  on workers.dev, its account's subdomain).

A refused URL is `403 {"error", "url", "refused": "url" | "redirect"}` and, when refused on the
request, takes none of the day's places. Names are not resolved here: a public name that resolves
to a private address is left to Cloudflare's egress, which has no route to private networks.

What comes back: `{url, final_url, status, content_type, title, text, truncated, bytes,
fetched_at}`. A page that answers non-2xx is still a `200` from the gateway, with the page's own
`status`. The read has 15 seconds in all; the body is read to 2 MiB and no further. It reads
`text/*`, `application/json`, `application/xml`, `application/rss+xml`, `application/atom+xml`
and `application/xhtml+xml`; any other type, none, or a `Content-Type` that is not a well-formed
media type of at most 127 characters is `415` naming it (`(none)`, `(malformed)`). HTML becomes
readable text: the title on its own, and the body without scripts, styles, `noscript`, `svg`,
`template` or the head, links kept as their text, list items and table cells marked, entities
decoded, whitespace collapsed. JSON, XML and plain text come back as they are. The text is cut at
200,000 characters, with `truncated: true` (as it is when the body passed 2 MiB). A page that did
not answer in time is `504`, one that failed is `502`, too many redirects is `502`.

The HTML is read in one forward pass, linear in the page: no pattern is retried at every `<`
(the first reader's regexes were super-linear: 32 KB of `<a<a<a...` took 22 seconds on a test
machine, and a 2 MiB page far longer). A tag that never closes, or a script, style or comment that never ends, ends the text
there, as it would in a browser. The page is read in the same isolate that serves the order
routes, so one isolate reads at most `MAX_IN_FLIGHT` (4) pages at once; one more is
`429 {"busy": true}` with `Retry-After: 5`, before it takes a place of the day's cap.

The floor reads at most **3,000 pages a UTC day** together (`DAY_CAP`), counted in the `Gate` in
one step with the page's agent, and reported in `/v1/health` as `web_fetch: {day, fetches, cap,
by_agent}`; over it is `429 {"cap": "web_fetch_day"}`. The House keeps its own budget of 20 pages
per agent a day, charged like a search. Every answer about a URL names it (`url`), so the House
can tell a page the gateway judged from a gateway that could not act (a bad body, the cap, busy,
a Worker error). It charges and counts a judged read and also a Worker error (`5xx` naming no
url, which is how a page that exhausted the Worker ends) or a timeout: only a request refused
before any read (`4xx` naming no url) or never received is free.

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
  `floor_stopped`: credit at or under the reserve (since Sept 26, 2026 the schema-2 checkpoint has
  no `budget.mode`, and a stale checkpoint is `box_not_running`'s, not this). Runway is credit above
  the reserve over the trailing day's Sail spend.
- `box_not_running`: a recovery failed, the box is stopped and this pass did not bring it back,
  or a restart went out earlier and the floor is still quiet. A parked box is therefore mailed
  about every six hours even before go-live.
- `kill_switch_engaged`, for as long as it is engaged; `caps_exhausted`.
- `daily_digest` in the 21:00 UTC hour: equity (the schema-2 checkpoint's `account.equity`),
  profit since the reset (equity less `performance.start_equity` less `net_flows`, unknown when any
  is missing), orders, Sail spend, runway, box state.

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
`league/frontier.py` calls `/v1/frontier/responses`, `league/merton.py` calls `/v1/github/pr`,
`league/commons.py` calls `/v1/web/fetch` for research's `web_fetch`, and
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
