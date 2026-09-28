# What blakewoods.us/capital accepts from the House's publisher (schema 2)

Source of truth: `personal-site/capital/schema.js` (the validators, run by the Worker before storing and
by the page before drawing), `personal-site/lib/capital.mjs` (the Durable Object) and
`personal-site/capital/capital.js` (the page), as of Sept 26, 2026 (the options swarm; personal-site
branch `capital/options-reset`). `site_checkpoint.json` and `site_events.json` beside this file are
`league/publish.py`'s own output (`build_checkpoint` and `to_events`, pinned by `test_publish.py`;
`LTCM_WRITE_SITE_FIXTURES=1` rewrites them), and `personal-site/test/league-contract.test.mjs` publishes
and draws them (`LTCM_FIXTURES=<this folder>`).

**exact** = these keys and no others; an unknown key anywhere is a 400, never ignored.

## The licence

ThetaData's and the market-data subscription's terms forbid publishing quotes, bids, asks, spreads,
implied vols, greeks, surfaces, or parameters fitted from them, and both repositories are public. So:

- No block has a field for any of them. The publisher builds every block key by key (an allowlist), and
  the site refuses any key it does not name.
- Every sentence (an agent's `mechanism`, a note's `text`, a trade's `why`, the swarm's news) must
  be **quote-free**: no decimal number (`\d\.\d`), no dollar or cent amount (`$120`, `45¢`), and no number
  within 16 characters after, or 2 before, a quote word (bid, ask, offer, mid, midpoint, nbbo, spread,
  wide, width, iv, implied, vol, volatility, skew, delta, gamma, theta, vega, greek, premium, quote,
  quoted, price, priced, pricing, mark, cent, and their plurals). The publisher masks exactly these with
  `…` (`scrub_quotes`); whole numbers elsewhere stay ("3 contracts", "45 DTE", "the 570 strike").
- No sentence names a venue (`alpaca`, `kalshi`, `coinbase`, anywhere, any case): the account is "the
  Brokerage Account", and the publisher writes "the broker" (`scrub_venues`).
- A program, its parameters and anything a program reads never publish.

## Transport

| | |
|---|---|
| Auth | `Authorization: Bearer <CAPITAL_PUBLISH_TOKEN>`, token >= 32 chars. 401 otherwise. |
| `POST /api/capital/events` | `{schema_version: 2, events: [...]}` exact, 1-100 events, ids unique, <= 512 KiB. Reply `{stored, replayed}`. Every `account.mark` is also archived as the balance history. |
| `POST /api/capital/history` | a batch of `account.mark` only: a backfill, not broadcast. |
| `POST /api/capital/checkpoint` | one checkpoint, <= 512 KiB. Reply `{published_at, agents}`. `published_at` must be later than the stored one (409) unless byte-identical (200), and at most a minute ahead of the server (400). |
| `POST /api/capital/reset?confirm=erase-everything` | erases `events`, `floor_history`, `checkpoint` and the roster (`desks` table) of that record. |
| Reads | `GET /api/capital/checkpoint` (404 until the first checkpoint), `/events?stream=&kind=&after=&limit=`, `/history`, `/agents`, `/agents/<id>`, and the WebSocket `/stream?streams=`. |
| Test tapes | the same under `/api/capital/t/test/...` and `/api/capital/t/canary/...`, separate storage, same token. |
| Idempotency | same event `id` + same `digest` = replayed; same `id` + different `digest` = 409 and the whole batch is rolled back. |

Scalars: `instant` = `YYYY-MM-DDTHH:MM:SS.mmmZ` exactly; `money` = unsigned plain decimal, at most 8
places, no exponent; `signedMoney` = `money` with an optional `-`; `day` = `YYYY-MM-DD`; `slug` =
`^[a-z0-9-]{1,40}$`; `underlying` = `^[A-Z][A-Z0-9.]{0,9}$`; counts are JSON integers. Every time inside a
checkpoint is at most a minute after its `published_at`.

## Events (exact payloads)

| Kind | Stream | Payload |
|---|---|---|
| `agent.note` | `agent:<id>` | `{text}`: 1-2,000 chars of quote-free words. An agent's decision in its own words. |
| `agent.trade` | `agent:<id>` | `{action: open\|close, real: bool, underlying, structure, legs: 1-4, expiry: day, quantity: 1-10,000, max_loss_usd, pnl_usd, why}`. An open has `max_loss_usd` (money) and `pnl_usd: null`; a close has `pnl_usd` (signedMoney) and `max_loss_usd` money or null. `why` is quote-free prose (<= 240, may be empty). Never a price or a strike. |
| `swarm.news` | `swarm` | `{agent: slug \| null, text}`: 1-300 chars of quote-free words. Births, band moves, retirements, audits. A sentence about an agent starts with its verb ("moves from Gym to Candidate: ...") and names the agent in `agent`, never in the words (a name like "Skew Revert 2" would lose its number to the quote rule); `null` is the House's own news. |
| `account.mark` | `account` | `{equity, cash, as_of}`: one reading of the Brokerage Account. |

`structure` is one of `long_call long_put debit_vertical credit_vertical iron_condor iron_butterfly
long_butterfly long_straddle long_strangle calendar diagonal`. What the publisher makes of the ledger
(`to_events`): `agent.thought` and a research `summary` -> `agent.note`; `book.fill` (source `venue` or
`cross`) of an option or a structure held as one instrument -> `agent.trade` (a buy opens, a sale with
`realized` closes; an open's maximum loss is its held price x multiplier x quantity); `book.settle` ->
a close; `floor.mark` rows carrying `brokerage_equity` (the publisher's own, every five minutes) ->
`account.mark`; `agent.born`, `agent.died`, `eval.verdict` with `band_from`/`band_to` in the five bands,
`audit.verdict` and a held or deploying `ops.deploy` -> `swarm.news`. Anything else (crypto, Kalshi,
the old ladder's bands, alerts, credits) publishes nothing.

## Checkpoint (exact; every block present, null or empty until the House has it)

```
{schema_version: 2, published_at, run, account, performance, compute, gym, agents, structures}
```

| Block | Shape |
|---|---|
| `run` | `{started_at: instant \| null}`: the House's first `ops.started` on its new ledger. The page's timer. |
| `account` | `null` or `{equity, cash, as_of, stale: bool}`: the Brokerage Account. `stale` repeats the last good reading. |
| `performance` | `null` or `{start_at, start_equity (> 0), net_flows: signedMoney \| null, verified_at: instant \| null}`: the profit basis; flows and their check both or neither; `start_at <= verified_at <= published_at`. |
| `compute` | `null` or `{as_of, sail_usd, openai_usd, thetadata_usd, market_data_usd, other_usd}`, each money or null: spend since the reset. |
| `gym` | `null` or `{as_of, trials, market_years (one decimal), families_alive, families_retired}`, each nullable. The pace, never a result. |
| `agents` | <= 160, ids unique: `{id, family, mechanism, structure \| null, band, born_at \| null, retired_at \| null, record: {trials, revisions, forward: tally \| null, real: tally \| null}}`, tally `{trades, wins (<= trades), pnl_usd}`. `band` is `gym candidate probe sized retired`. The page names an agent by its id ("condor-vrp-3" reads "Condor Vrp 3"). |
| `structures` | <= 100, ids unique: `{id, agent, underlying, structure, legs, expiry, quantity, real, opened_at, max_loss_usd, pnl_usd \| null}`. |

An agent may additionally carry `progress`, either null (unavailable) or
`{target: candidate|probe|sized|maintain, checks: [{key, done, need}], blocked: null|fixed_reason}`.
The target's ordered checklist, key and blocker allowlists, and count bounds are defined in
`league/swarm/progress.py` and mirrored by the site's validator. Binary verdicts use `need: 1`;
counts are integers clipped at the public requirement. No research statistic, return, quote,
fitted parameter, raw blocker text or holdout number appears. Progress is checklist completion,
not a probability or an expected promotion date. Sized's `maintain` has no higher band.

Gym checks bind the selected version to the current Gym image and engine; changed connected-lineage
trial counts withhold the cached deflated-Sharpe pass. Live-band checks bind the banded version and
recorded holdout, and count its forward record once per market day (real before shadow before nightly).
Real trade counts cover that selected version only. Probe sessions use the latest durable promotion
time and complete exchange sessions. Reading progress never changes a band, grant, order or evidence.

The masthead shows **Profit** from the optional `trading: {as_of, pnl_usd}` block: the full real-options
record, including marked open positions, and what the account's own activity adds outside them (below). Missing, unpriced or stale trading P&L displays a dash; the
reading must be within ten minutes of both the checkpoint and the current time. Deposits, withdrawals,
compute costs and the account's starting balance do not enter this number. **Running** is elapsed time
since `run.started_at`, falling back to the reset's performance basis when the run timestamp is absent.

Since Sept 28, 2026 Profit is **complete**: it includes the House's D3 calibration round trips (real money on the
owner's account, labelled "House calibration") and the account's own activity outside the book's positions, so
that the positions table below adds up to it to the cent (`league/trading_profit.py`, `league/account_activity.py`).

## The positions table (optional, only beside `trading`)

The owner's line of sight into what the agents trade: every real-options position on the Brokerage Account since
`performance.start_at`, open and closed, with its dollar P&L after fees. `site_checkpoint_positions.json` beside this
file is `site_checkpoint.json` plus `trading` and `positions` (`build_checkpoint`, pinned by `test_publish.py`).
`site_schema.js` beside it is a copy of the site's `capital/schema.js` (personal-site commit 6ee749c, the positions-ledger
release of Sept 28, 2026): `test_positions_ledger.py` runs the site's own `validCheckpoint` over both fixtures and over the tables
the House builds, in node (the review of #408 found the two sides' blocks disagreeing because each tested only its own
fixture). Copy the site's file here whenever its schema changes.

```
positions: {
  as_of: instant,                       // == trading.as_of
  rows: [{                              // <= 300, ids unique; open first (newest opened first), then closed (latest closed first)
    id: "real:<pid>",
    source: "agent" | "calibration" | "house",
    agent: slug | null,                 // the agent's id when source is "agent", else null
    underlying, structure,              // `structure` is one of the eleven types above
    right: "call" | "put" | "both",     // must fit the structure (the site's STRUCTURE_RIGHTS)
    legs: 1-4,
    quantity: 1-10,000,                 // contracts opened
    open_quantity: 0..quantity,         // still held: at least 1 when open, 0 when closed
    status: "open" | "closed",
    expiry: day,                        // the nearest leg's
    opened_at: instant,                 // to the minute: the broker's fill time where the book kept it, else the book's
    closed_at: instant | null,          // to the minute, null exactly when open, never before opened_at; a close the
                                        // broker made at expiry with no fill yet priced: 16:00 New York on its expiry
    pnl_usd: cents | null               // closed: realized; open: at the House's current value; after fees (the broker's
                                        // posted fees once every leg's has posted, the book's estimate until then);
                                        // null when unpriced (Profit is then null too)
  }],
  earlier: {positions: counter, pnl_usd: cents | null} | null,   // the positions not listed, as one line: the oldest
                                        // closed past 300 (or past the byte limit), and any row the table's fields
                                        // cannot describe, open or closed (the House alerts on those, and on an open
                                        // one past the limit); null pnl only while Profit is null
  other: {as_of: instant, fees_usd, crypto_usd, interest_usd, misc_usd} | null,   // each cents: "Other account
        // activity": fees no position carries (pass-through charges, a liquidation's fee true-up, a fee on an order
        // the book does not hold), crypto fees (not the leftover coins' dust), interest, other returns
  unreconciled_usd: cents | null        // what the account shows that the book cannot account for; "0.00" when they
                                        // agree; null only while Profit is null and the account was not read
}
```

The rule the site checks, in whole cents: when `trading.pnl_usd` is not null, every line is not null and the rows +
`earlier.pnl_usd` + the four parts of `other` + `unreconciled_usd` equal it exactly. A nonzero `unreconciled_usd` is
shown as its own line and the House alerts on it; it is never folded into a row. A row's share of Profit is the page's
own arithmetic (`pnl_usd` / Profit), not a published field. The block has no prose and no field that is a price, a
strike, a mark or a leg's code: only what a position is and its dollars. An open row's P&L read with its maximum loss
(in `structures` and on the tape) implies the House's current value of it per contract; the public-data rules allow a
position's dollar P&L, and valuing open rows from a quote at least fifteen minutes old instead is the owner's decision.
The page names an agent's row with the same `display_name` as its dot (the Worker's annotation, as for agents and
events); a `calibration` row reads "House calibration".

A site that refuses a checkpoint carrying the block (400: an older site's exact keys, or a row or a sum it rejects) gets
the same checkpoint again without it, and is offered the table again half an hour later; the House warns once per
distinct reply of the site, quoting it. So either repository may deploy first. Old pages validate strictly too: the
Worker omits `positions` from checkpoint reads unless asked for it with `?progress=1&positions=1`.

The account chart separately shows recorded Brokerage Account balances, which include funding flows.
The chart has its own start: it may begin after an owner's deposit, so its first point need not be the
account's starting balance, and a later deposit or withdrawal moves the line. **Profit** never moves
with funding: it always nets deposits and withdrawals out, whatever the chart's start. The
`performance` and `compute` blocks remain available in the payload and account details; they do not
replace the masthead's trading P&L. Subscription costs remain prorated from `performance.start_at`.
