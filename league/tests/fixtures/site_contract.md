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

The page shows **Total profit** = `account.equity - performance.start_equity - performance.net_flows`
only when the account is fresh (within ten minutes of `published_at`) and not stale, and the funding was
verified within ten minutes; the basis is never one dated before the page's `PERFORMANCE_START_AT` (the
reset). **After compute** = total profit minus the sum of the five compute parts, only when every part
is known. The publisher's defaults: Sail from the Sail meter's `ops.budget` rows, OpenAI null until the
House's `site_inputs()` gives it, ThetaData ($80 a month) and market data ($1,000 a year) prorated from
`performance.start_at`, other 0.
