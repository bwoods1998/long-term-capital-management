# What blakewoods.us accepts from the league publisher

Source of truth: `personal-site/capital/schema.js` (cited as `S:<line>`), the Durable Object
`personal-site/lib/capital.mjs` (`D:<line>`) and the page `personal-site/capital/capital.js`
(`P:<line>`), as of 2026-09-19. `site_checkpoint.json` and `site_events.json` beside this file
are accepted by those validators and draw all five sections; `personal-site/test/league-contract.test.mjs`
proves it on every `npm test`. **REQUIRED** = the body is refused (HTTP 400) without it.
**exact** = these keys and no others. **shape** = required keys plus only the listed optional keys.
An unknown key anywhere in a checked object is a 400, never ignored.

## 0. Transport

| | |
|---|---|
| Auth | `Authorization: Bearer <CAPITAL_PUBLISH_TOKEN>`, token >= 32 chars (D:46). 401 otherwise. |
| Body | `Content-Type: application/json` (415 otherwise, D:63). No query string on a POST (400), except `reset`. |
| `POST /api/capital/events` | event batch, <= 512 KiB (S:7). Reply `{stored, replayed}`. Archives every `floor.mark` into the balance history as well. |
| `POST /api/capital/history` | event batch of `floor.mark` only (D:198). Backfill: not broadcast, not on the tape. |
| `POST /api/capital/checkpoint` | one checkpoint, <= 512 KiB (S:8; 256 KiB before personal-site #4, Sept 23, 2026). Reply `{published_at, desks}`. |
| `POST /api/capital/reset?confirm=erase-everything` | wipes events, history, checkpoint, desks of that floor (D:344). |
| Test tape | the same four (and every GET, and the socket) under `/api/capital/t/<tape>/...`. **`<tape>` is `test` or `canary`, nothing else** (`TAPES`, S:115-116, D:17). Separate storage per tape, same token. View at `/capital/?tape=test` (P:9); the status dot there follows the connection. Any other name is a 404 from the worker and wakes no object. |
| Idempotency | same event `id` + same `digest` = replayed, no error. Same `id` + different `digest` = **409 and the whole batch is rolled back** (D:135). |
| Checkpoint order | `published_at` must be > the stored one (409, D:148) unless the body is byte-identical (200). `published_at` later than the server clock + 60 s = 400 (D:144). |
| Retention | newest 20,000 events (D:24); balance history is kept for good, served as <= 2,048 points. |

## 1. Scalar formats (every one is a JSON string unless noted)

| Name | Rule | Line |
|---|---|---|
| `instant` | `YYYY-MM-DDTHH:MM:SS.mmmZ` exactly: UTC, 3 ms digits, `Z`, a real date. Python `isoformat()` (`+00:00`, 6 digits) is refused. | S:125 |
| `money` | `^(?:0\|[1-9]\d{0,14})(?:\.\d{1,8})?$`, <= 32 chars. Unsigned, no `+`, no exponent (`1E+2`), no `.5`, no `1.`, no leading zeros, <= 8 decimals. | S:127-129 |
| `signedMoney` | `money` with an optional leading `-`. | S:130 |
| `percentValue` | signed, <= 6 decimals. | S:131 |
| `counter(max)` | JSON integer, 0..max (default 1e9). Not a string, not a float. | S:132 |
| `deskId` | `^[a-z0-9-]{1,40}$`. League ids (`^[a-z][a-z0-9-]{1,38}$`) fit; **a 39-char name forked to `name-2` is 41 chars and is refused**, in the id and in every `desk:<id>` stream. | S:110 |
| `venueName` | `^[a-z0-9-]{1,24}$` (`kalshi`, `alpaca`). | S:111 |
| `eventId` | `^[A-Za-z0-9:_.-]+$`, 1..200 chars. **No `/`**: never build an id from `BTC/USD`. | S:117 |
| `digest` | `^[a-f0-9]{64}$` (lowercase). Only the format is checked; it is the idempotency fingerprint. | S:118 |
| `text(max)` | non-blank string <= max, no `<`, no control char except tab, LF, CR. **Every max counts JavaScript `.length` (UTF-16 units)**: an emoji is 2 there and 1 in Python, so the publisher cuts with `publish.js_cut`, never `[:max]`. | S:139, S:93 |
| `prose(max)` | as `text` but may be `""`. | S:137 |

## 2. Event batch

`{schema_version: 1, events: [...]}` **exact**; 1..100 events; ids unique within the batch (S:262-268).

Event (S:246-261): keys `id, stream, kind, at, payload, digest` all REQUIRED, `seq` (counter) the
only other key allowed. `id` eventId, `at` instant, `digest` digest, `kind` one of `EVENT_KINDS`
(S:24-64), `stream` one of `risk committee evolution lab ops` or `(desk|ledger|broker):[a-z0-9-]{1,40}`
(S:119). **The kind's prefix must equal the stream's family** (`desk.*` on `desk:<id>`, `broker.*`
on `broker:<x>`, `lab.*` on `lab`), the one exception being `floor.mark`, pinned to `ops` (S:69, S:257-258).

Every payload (S:150-176), fixed-shape or free-form:

- a JSON object, <= 20 KiB serialized (S:10); depth <= 8, <= 100 keys per object, <= 500 items per array (S:19-21);
- keys match `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$` and never start with `_` (S:100, S:166). **A dict keyed by `BTC/USD` is refused.**
- numbers finite; strings <= 8000 chars, no `<`, no control chars (tab/LF/CR are fine);
- no credential shapes: `\bsk-`, `\bbearer[ :]`, `\bapca-`, case-insensitive (S:95);
- no `javascript: vbscript: data: file: blob:` followed by a non-space (S:99): "the data:5 rows" is refused, "the data: 5 rows" is not;
- **every `scheme://...` in any string must be `https://` on one of** `sec.gov www.sec.gov efts.sec.gov blakewoods.us github.com kalshi.com finance.yahoo.com`, no port, no userinfo (S:71, S:142-155). One Reuters or alpaca.markets link in a thought, a `web_search` argument or a library title fails the event, and one failed event fails its whole batch. Strip or de-link URLs before publishing.

Fixed payloads exist only for `risk.review`, `floor.mark`, `desk.forecast`, `desk.exit_plan`,
`lab.calibration` (S:216-242). The other five kinds below are free-form: the validator requires
nothing, so "page reads" is what the page needs in order to draw the line.

| Kind | Stream | Validator requires | Page reads (P: line) |
|---|---|---|---|
| `desk.thought` | `desk:<agent>` | payload rules only | `text` non-blank (markdown stripped); `session_id` ties its research to it (P:599, P:673). Initial load: newest 60. |
| `desk.tool_call` | `desk:<agent>` | payload rules only | `tool` must be a key of `RESEARCH` (P:549) or the line is dropped; `arguments` object; `session_id`. New tools and the argument each reads: `web_search{query}` `library_search{query}` `library_read{title}` `library_write{title}` `replay{purpose}` `request_tool{name}` `playbook_read{}`. Older: `event_markets news weather_forecast calendar memo_read memory_read outcomes positions run_code strategy_report quote bars`. Newest 100. |
| `broker.fill` | `broker:<venue>` (not `desk:`) | payload rules only | **`desk_id`** (deskId; the stream names the venue, so without it the fill is not drawn), `instrument{symbol, asset_class, market_id?, right?}`, `side` `buy`/`sell`, `quantity`, `price` (money string). `real_money` boolean decides the practice tag when present, else the desk's `mode` in the checkpoint (P:616). `shadow: true` or stream `broker:shadow` is always practice. Hidden when `settlement === true`, when `note` is non-empty, when `desk_id == "settlement"`, or when the id or `fill_id` contains `reversal`. Event contracts (`asset_class: "event"` or symbol `KX...`) read "bought 20 YES on ... at 93¢"; others "bought 0.000437 BTC at $80,950.00". Newest 60. |
| `desk.outcome` | `desk:<agent>` | payload rules only | `market_id` (or `instrument`), `result` (`yes`/`no`/`sold`/...), `pnl` (signed decimal string; > 8 decimals tolerated), `rationale_excerpt` (the "why"; a leading `[strategy name]` becomes a tag), **`real_money` boolean** (decides real vs practice; absent = the desk's mode today, P:805), `held_for_hours` (number or numeric string), optional `entry_price exit_price quantity instrument.right`. Newest 200. |
| `lab.progress` | `lab` | payload rules only | `message` non-blank; `stage: "learn"` reads "learning", anything else "testing". **`component: "league"` makes the speaker "League"** (P:607); `component: "execution"` reads "monitoring / Execution"; any other or no component is the first run's "Foundry". Newest 60. |
| `floor.mark` | **`ops`** only | **shape**: REQUIRED `account_equity` money, `account_cash` money, `as_of` instant, `venues` (below); optional `voids` (1..100 eventIds of earlier marks to leave off the chart) and `reason` text(1000). Nothing else (S:223-227). | `account_equity` at the event's `at` is one chart point. |

`venues` (S:178-189): array of 1..8 rows, one per venue, never empty. Row **shape**: REQUIRED
`venue` venueName, `equity` money, `cash` money, `as_of` instant; optional `stale` boolean (present
only when the row is a repeat of the last good read).

## 3. Checkpoint

Top level (S:465): **shape**. REQUIRED `schema_version` (= 1), `published_at` instant, `floor`,
`desks`, `committee`, `budget`. Optional `infra`, `run`, `lab`, `watch`, `board`. Whole body <= 512 KiB (S:503; the publisher leaves the least important rows out until it fits, `Publisher.fit`).
Every instant inside must be <= `published_at` unless noted.

### floor (S:472-493) shape

| Key | Req | Type |
|---|---|---|
| `equity`, `cash`, `capital_usd` | REQUIRED | money (unsigned) |
| `daily_pnl` | REQUIRED | signedMoney |
| `since_inception_pct` | REQUIRED | percentValue |
| `benchmark` | REQUIRED | `null`, or exact `{name: text(60), return_pct: percentValue}` |
| `live_equity` | optional | money |
| `live_daily_pnl` | optional | signedMoney |
| `live_desks`, `shadow_desks` | optional | counter(MAX_DESKS = 160) or null |
| `account_equity`, `account_cash`, `venues` | optional, **all three or none** (S:485-491) | money, money, `venues` as in section 2, every `as_of` <= `published_at` |
| `performance` | optional, **only with the account block** (S:486) | below |

`performance` (S:394-402) **exact** `{start_at, start_equity, net_flows, verified_at}`: `start_at`
instant <= `published_at`; `start_equity` money > 0; `net_flows` signedMoney or null; `verified_at`
instant or null; **both null or neither**; `start_at <= verified_at <= published_at`.

The page shows **Total profit** only when all of this holds, else a dash (P:738-751):
`start_at == "2026-09-19T04:56:53.000Z"` exactly (P:26, = `ltcm/config.json account_performance.start_at`);
`start_equity` = the baseline (`"1021.9251"`); `net_flows` not null; `published_at - verified_at <= 10 min`;
every `venues` row has no `stale: true`; `account_equity` present. Profit = `account_equity - start_equity - net_flows`.
The chart = the baseline + archived `floor.mark`s between `start_at` and `published_at` + the checkpoint's own `account_equity`.

### desks: array, <= 160 (`MAX_DESKS`; 100 before personal-site #4), ids unique (S:494-496). Row (S:311-313, S:344-377) shape

REQUIRED, all 19:

| Key | Type |
|---|---|
| `id` | deskId |
| `name` | text(80). The page title-cases a slug itself: `crypto-reversion-2` reads "Crypto Reversion 2" (P:154); a name with capitals or spaces is shown as given. |
| `family` | deskId (so `alpaca-hour-reversion`, never `alpaca/hour/reversion`). A first-run partner surname (`merton rosenfeld hawkins krasker mullins hilibrand`) as the `family`, or as the first word of an `id`, makes the page show that partner's name instead. |
| `generation` | counter(10000) |
| `parent_id` | deskId or null; never equal to `id`. The parent need not be in the checkpoint. |
| `mode` | `live` or `shadow` (`paper` = legacy shadow) (S:74). Decides where the desk's positions are listed (below) and is the real/practice fallback for events without `real_money`. |
| `venues` | array of <= 8 distinct venueName (may be empty) |
| `capital_usd`, `cost_usd`, `max_drawdown_pct` | money (unsigned) |
| `equity`, `cash`, `daily_pnl` | signedMoney |
| `return_pct` | percentValue |
| `days_live` | counter(100000) |
| `orders` | counter |
| `status` | `active halted paused retired` (S:78) |
| `gate` | `null`, or exact `{name: text(80), passed: boolean, evidence: payload <= 4 KiB}`. `evidence.decisions` (integer) is the page's decision count when there is no lab curve. |
| `updated_at` | instant <= `published_at` |

Optional (S:313): `positions` (<= 50, below) · `pnl_usd` signedMoney · `next_session_at` instant or
null (may be in the future) · `live_session` exact `{session_id: text(200), trigger: text(60), started_at: instant}`
(present only while in session; `cadence:HH:MM` reads "sat down for the HH:MM slot") ·
`budget_factor` money in (0, 10] · `mutation` exact `{model_profile, reasoning_effort, session_shift_minutes, memory_limit, persona_trait, model_changed}` ·
`calibration` exact `{n, brier, since}` · `strategies` (<= 8, S:332) · `working` (<= 20, S:317).

The capital board's fields (personal-site #4, Sept 23, 2026), each optional:

| Key | Type |
|---|---|
| `band` | `replay paper bunt swing star` (`BANDS`). `paper` is the House's word; the page says Practice and never shows "paper". Without the allocator the publisher sends the rung's band (0 replay, 1 paper, 2 bunt, 3 swing) and none of the three below. |
| `stake_usd` | money or null: the real stake on `bunt swing star`, null otherwise. Published with 2 places. |
| `evidence` | null, or shape `{W_paper, W_real, E, trades}` + optional `real_trades`: multiples are unsigned decimal strings with <= 6 places (published with exactly 6, `"1.034512"`), trades counters. |
| `last_move` | null, or exact `{at, from_band, to_band, reason}`: `at` instant <= `published_at` + 60 s, `from_band` a band or null, `to_band` a band, `reason` prose(300). |

### board (optional; personal-site #4) shape

REQUIRED `bands`, `moves`; optional `throttle`, `enabled` boolean.
`bands`: `{<venueName>: {<band>: exact {count: counter(100000), capital_usd: money}}}`, <= 8 venues.
`moves`: <= 50, ids unique, oldest first; each shape REQUIRED `id` eventId, `at` instant (<= `published_at`
+ 60 s), `agent` deskId, `from_band` band or null, `to_band` band, `reason` prose(300); optional
`venue` venueName, `stake_usd` money or null. `throttle`: exact `{active: boolean, floor_pnl_usd:
signedMoney, envelope_usd: money}`. The page reads the lanes' notes from `bands`, the trail from
`moves` (deduplicated against the tape by id: the House uses the `eval.verdict` ledger id), and
says so above the lanes when the throttle is on.

Band moves on the tape are `lab.progress` (component `league`) sentences the page parses:
`<agent> climbs|drops from <Replay|Practice|Bunt|Swing|Star> to <Band>[ with a $<stake> real stake]: <reason>.`
and `<agent>'s real stake is now $<stake>[ (<Bunt|Swing|Star>)]: <reason>.` The old
`<agent> climbs|drops from rung N to rung M: <reason>.` still parses.

### position row (S:281-297) shape

REQUIRED, all 13: `instrument` · `side` one of `long short yes no` · `quantity`, `entry_price`,
`mark_price`, `market_value` money (unsigned) · `unrealized_pnl` signedMoney · `opened_at` instant
<= `published_at` · `thesis` prose(240) (the "why"; `""` allowed, first sentence is shown) ·
`target_price`, `stop_price` money or null · `time_stop_at` instant or null (future allowed) ·
`exit_orders` array <= 8 of exact `{id: text(120), kind: target|stop|time_stop|desk, price: money|null}`.
Optional: `intent_id` text(120) or null, `session_id` text(200) or null.

`instrument` (S:193-201) **shape**: REQUIRED `symbol` text(80), `asset_class` text(24), `venue`
venueName; optional strings <= 80 or null: `multiplier expiry strike right market_id currency`.
`BTC/USD` and `BTC-USD` both read "BTC"; a `KX...` ticker reads as its market.

How the Open table draws them (P:756-775, P:791): `live` desks' positions first, by `market_value`,
untagged; then `shadow` desks' positions, by `market_value`, each with the "practice" tag the closed
table uses. Positions under $0.50 of `market_value` are dust on either book: counted, not listed.
A mixed book is headed "2 real · 5 practice". With no real-money position the panel reads
"No real-money position open. $1,022 in cash across Kalshi and Alpaca. 1 practice position below."
So a shadow agent's `positions` (with a `thesis`) are worth publishing from its first day.

### lab (S:434-441) exact `{experiments, curve, calibration}`

`experiments`: array <= 12, may be `[]` (row S:420). `calibration`: exact `{n: counter, brier: money|null}`.
`curve`: array <= 40, one row per generation. Row (S:429-433) **exact, 8 keys**:
`generation` counter(10000) · `desks` counter(160) · `decisions` counter · `cost_usd` money ·
`pnl_usd` signedMoney · `cost_adjusted_excess_pct` percentValue · `brier` money or null ·
`pnl_per_inference_usd` signedMoney. The bar is `cost_adjusted_excess_pct`; a row with
`decisions == 0` is not drawn. With no `lab`, the page falls back to desks' `pnl_usd / capital_usd` by generation.

### run (S:451-462) exact, 13 keys

`started_at` instant <= `published_at` (**the Running clock counts from this, nothing else**, P:520) ·
`uptime_seconds` counter · `availability_7d_pct` money <= 100 or null · `sessions_total`, `sessions_today`
(<= total), `decisions_total` counter · `sail_model_spend_today_usd`, `sail_model_spend_total_usd`,
`sail_spend_total_usd` money · `sail_infra_spend_total_usd` money or null · `pnl_total_usd` signedMoney ·
`pnl_per_sail_dollar` signedMoney or null · `models_used` array <= 8 of text(40).

### budget (S:406-415) shape

REQUIRED `spent_today_usd` money, `cap_usd` money. Optional `mode` (`open throttled stopped unknown`),
`balance_usd` and `runway_days` money or null, `spendable_usd burn_usd_per_day reserve_usd desk_fuse_usd` money.

### committee (S:498-501) exact

`{last_memo_at: instant <= published_at | null, allocations: {<deskId>: money, ...}}` (<= 160 entries, `{}` allowed).

### infra (S:380-391) shape

REQUIRED `host` text(40). Optional, each nullable: `box_id`, `region` text(120); `checkpoint_count`,
`uptime_seconds`, `requests_today` counter; `spend_usd` money.
