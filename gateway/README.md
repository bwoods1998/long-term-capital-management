# The gateway

A Cloudflare Worker (`ltcm-gateway`) that holds every credential that can move money or spend it:
the Brokerage Account's keys (real and paper), OpenAI's key, Anthropic's key, the GitHub token and
Sail's key for its watchdog. The House's Sailbox holds one bearer token and can only ask: it cannot
sign an order, pass a cap, spend past the OpenAI month or the Claude funded total, or release the
kill switch, because none of that lives on the box. Caps and switches change only by editing
`wrangler.jsonc` and deploying, which is the owner's act. The old, long version of this page is
[archive/docs/gateway-README-pre-options.md](../archive/docs/gateway-README-pre-options.md).

```
the House (Sailbox)        this Worker                                  outside
  GATEWAY_TOKEN      ->    ALPACA_KEY_ID / _SECRET_KEY            ->    api.alpaca.markets (the Brokerage Account)
                           ALPACA_PAPER_KEY_ID / _SECRET_KEY      ->    paper-api.alpaca.markets
                           (either pair, market data)             ->    data.alpaca.markets
                           OPENAI_SECRET_KEY                      ->    api.openai.com
                           CLAUDE_API_KEY                         ->    api.anthropic.com
                           GITHUB_TOKEN                           ->    api.github.com
                           (no key: the research library)        ->    export.arxiv.org, arxiv.org/html, ar5iv.labs.arxiv.org
                           caps, the OpenAI month, the Claude funded total, the kill switch (one Durable Object)
                           the watchdog cron (SAIL_API_KEY)       ->    Sail, the site, mail to the owner
```

## Routes the options House uses

Every route takes `Authorization: Bearer $GATEWAY_TOKEN` except `/v1/unkill`, which takes only the
owner's `GATEWAY_ADMIN_TOKEN`; `/v1/kill` takes either (V3-A: stopping is never gated).

| Route | What it does |
|---|---|
| `GET /v1/health` | the kill switch, caps and today's counters, the OpenAI month, the Claude meter (`claude`: funded total, spent, in flight, remaining, holds, overruns, the priced models, `by_role`, `by_agent`, stop reasons, geographies), Sail's balance and the House box's state; never reads a venue itself |
| `POST /v1/kill`, `POST /v1/unkill` | engage the kill switch (either token), release it (owner only); both written to the admin log |
| `/v1/alpaca/<path>` | the Brokerage Account (orders to `api.alpaca.markets`, market data to `data.alpaca.markets`): options under the caps by maximum loss, stock closes, and listed long-only stock and ETF buys under the stock caps (below) |
| `/v1/alpaca-paper/<path>` | the paper account: never metered, not stopped by the kill switch, held to the same defined-risk shapes |
| `POST /v1/frontier/responses`, `GET /v1/frontier/models` | one metered OpenAI Responses call; the models the key reaches |
| `POST /v1/claude/messages` | one Claude Messages call, reserved and settled against the funded total; streamed when `stream: true`; stopped by the kill switch |
| `GET /v1/claude/models`, `GET /v1/claude/request/<id>` | the Claude models the key reaches and which are priced; what became of the House's call `<id>` (its `X-LTCM-Request`): held, settled, unknown, released or absent |
| `POST /v1/github/pr`, `GET /v1/github/pr/<n>[/failures]` | open a pull request from a proposal; read its state and CI |
| `GET /v1/github/pr/<n>/files?head_sha=`, `POST /v1/github/close` | the exact diff of a pull request at one head; close one engineer pull request at its head (V3-A, below) |
| `POST /v1/github/docs` | commit one desk page `docs/runs/desk/<date>[-slug].md` to `main` (V3-A, below) |
| `POST /v1/github/review`, `POST /v1/github/merge` | record the automated reviewer's verdict on an engineer pull request's exact head; squash-merge it inside the walls below (V3-A) |
| `POST /v1/notify` | one notice to the owner: a `live_stop`, a `funding` cliff (V3-A), a `stall` (the self-running release), a `test` |
| `GET /v1/research/search?q=&cat=&max=` | the research library: up to `max` (1-10) arXiv papers posted before 2025 for plain keywords, each pinned to a version (below) |
| `GET /v1/research/read?id=&start=&chars=` | one pinned version's metadata and a window (at most 10,000 characters) of its text |
| `GET /v1/research/health` | the library's pace, lease and day's count (the same `library` block `/v1/health` carries) |

Still in the code until the prune removes them (Wave 2b), and unused by the options House:
`/v1/kalshi/*` and `/v1/kalshi/ws-auth`, `/v1/typesafe/systemone` (Jev), `/v1/web/fetch`,
and the crypto order path. `/v1/notify`
mails the owner a `live_stop` notice when a real-money stop trips (Sept 26, 2026), a `funding`
notice when the budget rule finds a prefund under its card line (V3-A, below), and a `stall` notice when
the House's `stall` job finds the floor not improving itself (below).

## The caps

Enforced atomically before an order is signed, and only on calls that create an order on the real
account. **Reads and cancels always pass.** Deployed values (`wrangler.jsonc`, deployed 23:18Z Sept 26,
2026, version `9634002d`, for the sprint's real money; unchanged since):

| Var | Deployed | Meaning |
|---|---|---|
| `MAX_ORDER_MAX_LOSS_USD`, `MAX_ORDER_EQUITY_SHARE` | 1000, 0.25 | one OPENING order's maximum loss is at most the lower of $1,000 and 25% of the account's equity |
| `MAX_DAY_EQUITY_SHARE`, `MAX_DAY_USD_ALPACA` | 1.0, 10000 | today's opening maximum loss, this order included, at most 100% of equity and never above $10,000 |
| `MAX_DAY_ORDERS` | 300 | the trading day's order count, exits included (under the venue's 390 a day) |
| `MAX_DAY_OPEN_ORDERS` | 250 | no order OPENS once the day's orders (exits included) reach it: the last 50 are kept for exits (`403 {cap: "day_open_orders"}`) |
| `CREDIT_MIN_EQUITY_USD` | 2000 | a credit structure (credit vertical, iron condor, iron butterfly) opens only at this equity or more |
| `EQUITY_CAP_MAX_AGE_MS` | 120000 | the oldest equity reading an opening order is sized against |
| `OPTION_STRUCTURES_REAL` | `debit_vertical,long_butterfly,long_call,long_put` (V3-A part 1 leaves it so; `credit_vertical,iron_condor,iron_butterfly` join it only in the credit-types release, with the constitution's list) | the types a real OPEN may be: exactly the constitution's `options_money.real_types`; the credit types only at `CREDIT_MIN_EQUITY_USD` of the gateway's own equity reading; `off` opens none. Paper structures and closes of already held real positions go whatever it says |
| `STOCK_BUYS_REAL` | `on` (Oct 10, 2026; not yet deployed) | long-only buys of `STOCK_UNIVERSE` on the real account; anything but `on` admits none, and closes go either way |
| `STOCK_ETF_EQUITY_SHARE`, `STOCK_SINGLE_EQUITY_SHARE`, `STOCK_MAX_EQUITY_MULTIPLE`, `STOCK_DAY_EQUITY_MULTIPLE` | 0.5, 0.2, 2, 4 (the code's ceilings) | an ETF position at most 50% of equity, a single stock 20%, the whole long book a margin line at equity x m, m = min(2, the account's multiplier), long options counted m times; the day's stock buys (cancelled ones too) at most 4x equity; a value here can only lower them |
| `CAP_TIMEZONE` | America/New_York | the calendar the day rolls on |
| `MAX_ORDER_USD`, `MAX_ORDER_USD_KALSHI`, `MAX_DAY_USD` | 75, 75, 4000 | Kalshi only (dead until the prune removes it); the real account's orders never spend Kalshi's day |

- **The equity is the gateway's own reading** (`lib/account.mjs`): `GET v2/account` with the real keys,
  rounded down, kept in the Durable Object and read again on the order path when older than
  `EQUITY_CAP_MAX_AGE_MS`. No fresh reading refuses an OPEN with `503 {cap: "equity"}` (nothing was
  sent; the House sends it again next minute); exits never wait on it. The House cannot raise its own
  caps by reporting a larger account.
- **Open or exit is read from the order**, not from `X-LTCM-Purpose`: a structure's legs'
  `position_intent` says whether it opens (metered at its maximum loss against every cap) or closes
  (one micro-dollar, admitted only when the account's positions hold every leg it closes). A single-leg
  `sell_to_close` or `buy_to_close` is admitted only when the account holds that contract long or short
  for its size (`qty_available`); positions that cannot be read are `424 {cap: "positions"}`.
- **Stock orders** close: a sale of shares held long or a buy covering shares held short, at most the
  size held (exits). While `STOCK_BUYS_REAL` is `on` (Oct 10, 2026), a BUY of a symbol not held short
  also goes as an OPEN when it names a symbol of `STOCK_UNIVERSE` (`lib/caps.mjs`: SPY QQQ IWM DIA, the
  eleven SPDR sector ETFs, TLT, GLD, and 18 large US stocks) and is a `limit` `day` order sized in shares
  (fractional allowed; no `notional`), metered at `qty x limit_price`. The gateway reads the account
  (equity, buying power, multiplier), its open orders and its positions fresh, with the real keys, and
  the Gate refuses `403 {cap}`: `stock_order` (the order alone over 50% of equity for an ETF, 20% for a
  stock), `stock_day` (the day's buys with it over 4x equity), `stock_position` (the symbol's long
  market value + its resting buys + buys in flight + this order over that share), `stock_total` (every
  long stock position + every resting stock buy + buys in flight + this order + long options counted
  m times, over equity x m, m = min(2, the account's multiplier): Reg T's overnight line on every
  multiplier), `buying_power` (over the lower of `buying_power` and `regt_buying_power`). A read that
  fails is `503 {cap: "equity"}` (the account, or a margin account with no `regt_buying_power`) or
  `424 {cap: "orders"|"positions"}`. A buy counts as an open in the day's orders and the kill switch
  stops it; it never spends the options' opening maximum loss. Every stock order reads the positions
  fresh, and the Gate serializes closes: a second close of shares a close in flight already takes is
  `409 {cap: "stock_close"}`. No order is ever a short sale; crypto is refused. The running House sells
  every stock position at market (`_close_shares`): the House release that first buys must limit that
  to assignment shares (docs/operations.md).
- A refusal is `403 {error, cap}`; the kill switch is `423` and stops every order-creating call on the
  real account, exits included; an order that cannot be priced is `400`. Every refusal made before
  anything is forwarded that is a `424` or a `5xx` names its `cap` (`equity`, `positions`,
  `credentials`, `setup`): the one 5xx with no `cap` is a `502` after dispatch, which may be an order. Money is exact integer
  arithmetic and partial cents round against the order.
- **Structures** (`order_class: "mleg"`, `lib/caps.mjs`) are read from their legs as one of the
  defined-risk types. Any naked short, uncovered ratio, legging in or out, mixed roots or a
  `limit_price` of the wrong sign (positive is a debit, negative a credit) is a `400` on both accounts.
  If enabled, `OPTION_STRUCTURES_REAL` must equal the constitution's `options_money.real_types`; `league.ci`
  also accepts `off`, the stricter setting.
- `/v1/health` reports `max_loss`: the equity reading and its age, the per-order cap now, today's
  opening maximum loss and its cap, `max_day_usd_alpaca`, whether opens and credit opens are admitted,
  orders today of `max_day_open_orders` and `max_day_orders`; and `stock_buys`: the switch, the three
  shares and the day's multiple, the list, today's buys, the buys in flight, the closes not yet
  answered and whether a buy would be admitted now.

## The OpenAI month

`/v1/frontier/responses` forwards one call to OpenAI's Responses API within `FRONTIER_MONTH_USD`
($707 for September 2026, `FRONTIER_MONTH_MAX_USD` the same): the call's worst case is reserved
before it leaves, settled at the usage OpenAI reports, and a call that does not fit is a `402`. The
reply carries `X-LTCM-Cost-USD` to the microdollar. The cap never goes above funded money; raising it
is a gateway deploy. The owner confirmed a $100 addition on September 26, increasing the aggregate
ceiling from $607 to $707. `FRONTIER_FUNDED_MONTH=2026-09` expires that allowance at October 1
00:00 UTC: from then the month's cap is $0 (`lib/frontier.mjs` `monthCapMicro`; profit indexing
creates no month) and `/v1/frontier/responses` answers `403` ("No frontier budget is configured"). The
owner decided on September 29 that OpenAI is no longer topped up, so no October month is planned; since
then the House's settings send every paid role to Claude and none to OpenAI (Sail stays the fallback). A
later month would need its remaining credit reconciled and its funded month and ceiling deployed.

- **Flex** (Sept 26, 2026): a request may carry `service_tier: "flex"` for a model whose
  `FRONTIER_MODELS` row has a `flex` rate (half the standard one for GPT-6 Astra, Sol and Luna). It is
  reserved at the standard worst case and settled at the flex rate only when the answer reports
  `service_tier: "flex"` (the reply's `X-LTCM-Billed-Tier` says which); a 429 (flex capacity refused)
  settles at zero.
- **Output ceilings**: 16,000 tokens by default; `X-LTCM-Role: <role>` takes that role's ceiling from
  `FRONTIER_ROLE_MAX_OUTPUT` (`{"postmortem": 64000}`), and the reservation is sized from it.

## The Claude funded total

`/v1/claude/messages` forwards one call to Anthropic's Messages API (`lib/claude.mjs`) within
`CLAUDE_USD`, the owner's FUNDED TOTAL on the Anthropic account ($265 deployed since Oct 1, version `4471596a`; $200
from Sept 29). It is not a month:
nothing resets it, so it is raised only by what the owner adds, and raising it is a gateway deploy.
`CLAUDE_MODELS` is the price table and the allowlist, dollars per million tokens: Claude Opus 5.5
($4 input, $5 five-minute write, $0.20 hit, $20 output), Claude Sonnet 5 and Claude Sonnet 5.5 ($2,
$2.50, $0.20, $10; Sonnet 5.5 added 03:59Z Sept 29, 2026, version `7eaede72`). Since PR #417 every row
carries `geo: {"us": 1.1}`: Claude 4.6 and later bill US-only inference at 1.1x every rate, and a
workspace whose default inference geography is "us" is billed so without asking for it. A model not in
the table is a `403`.

- **Reserved at the worst case** before the call leaves: every byte of the request body plus 4,096
  framing tokens, each an input token at the five-minute cache-write rate, and every `max_tokens`
  output token (16,000 unstreamed, 32,000 streamed; thinking is output), at the row's dearest
  geography. A call that does not fit what is left is `402 {cap: "claude_funded"}`; the kill switch is
  `423 {cap: "kill_switch"}`; no key is `503 {cap: "setup"}`. What leaves for Anthropic is the body the
  checks read, serialized again (PR #417: a key given twice cannot pass the checks on one value and
  reach Anthropic with another), and the worst case is sized from those bytes.
- **Settled at Anthropic's usage**: uncached input, cache writes, cache reads and output each at its
  own rate, times the geography's multiplier when the usage names one. A refusal (`stop_reason:
  "refusal"`) and a cut answer are billed at their usage; a 4xx settles at zero. An answer that broke
  after its headers keeps its whole hold (unknown is not free); a hold nothing settled is swept to zero
  after 30 minutes. A cost above its own hold is booked in full and counted as an overrun (`overruns`,
  `overrun_usd`). The reply carries `X-LTCM-Cost-USD`; a streamed reply ends with one `ltcm.cost` event
  (`{cost_usd, known, stop}`); `GET /v1/claude/request/<id>` says what became of a call.
- **What is admitted**: text turns, adaptive thinking (never disabled, never `budget_tokens`; display
  omitted or summarized), `output_config` with an effort (low to max) and a JSON-schema format, up to
  four five-minute cache markers, and (PR #417) the House's OWN tools and its tool loop: custom tools
  with a name, a description, an object `input_schema`, a marker and `eager_input_streaming`;
  `tool_choice` auto or none; `tool_use` blocks (`caller` direct only), `tool_result` blocks with text
  content, and the model's `thinking` (with its signature) and `redacted_thinking` blocks passed back.
  A custom tool runs in the House, so it bills nothing beyond the body, and the tools and every turn
  are bytes of the body the worst case already counts.
- **What is refused** (`400`): anything that runs or bills beyond the body (server and
  Anthropic-defined tools such as web search, code execution, bash, computer and MCP; `strict`,
  `defer_loading`, `allowed_callers`), forced tool choice (`any`, `tool`: a 400 upstream on Sonnet 5.5
  and Opus 5.5), images, documents, sampling parameters, fast mode, `inference_geo`, the one-hour
  cache and an assistant turn last.
- **Who spent it**: `X-LTCM-Role` and `X-LTCM-Agent` file each settled cost under `by_role` and
  `by_agent` in `/v1/health`. The House's roles: `architect`, `audit`, `diagnostician`, `rewrite`,
  `review` and `researcher` (the top band's research cycles, PR #417).

## The research library

`GET /v1/research/*` ([lib/library.mjs](lib/library.mjs), Sept 29, 2026) is how the swarm's agents read the literature:
arXiv's quantitative finance, econometrics, statistics and machine learning on markets, posted BEFORE 2025 and nothing
later. Open web access would let an agent read about the Validation year (2025) and the sealed holdout (2026) and select
on them, so the swarm gets a library instead, and the date rule is enforced here, in code, on every answer:

- **The rule.** An item is served only if its first-posted date (arXiv's `published`, v1) and the date of the version
  served (that version's `updated`) are both before `2025-01-01T00:00:00Z` (`CUTOFF`, a constant, never a var). A paper
  is served as it stood at the end of 2024: its newest version dated before the cutoff, pinned, in a search and in an
  unversioned read alike (that version never changes, as every later version is after the cutoff, so it is kept as
  `e:`). A read that names a version gets that version only when it is itself before the cutoff; a later one is
  answered exactly as a version that does not exist (`404 not_found`), so no answer shows whether a paper was revised
  after 2024. A missing, unparseable or self-contradicting date (a `25xx` id claiming 2024) is refused. Every text passes
  the post-cutoff date scan: in pinned text a forecast or maturity becomes `[date]`; ar5iv's text (not pinned to a
  version) is withheld whole on any match. Email addresses are `[email]`. `withheld` counts what was refused, for the
  House's log only (the House drops it).
- **The search.** Every term is matched in titles and abstracts only (`(ti:<term> OR abs:<term>)`, the cs.LG market words
  too), never `all:`, which also searches comments and journal references an author can add after 2024 without a new
  version. arXiv matches a paper's LATEST version, so a paper revised after 2024 is kept only when every query term is
  in the served version's own title or its own abstract, a phrase within one field as arXiv matches it, plurals folded
  no further than arXiv's stemmer folds them (both checked live, Sept 30, 2026); else words added after 2024 would
  choose it.
- **What the library does not remove.** The models' weights already hold 2025 and the first half of 2026. The library
  adds nothing dated after 2024, but it removes nothing a model already knows, and a pre-2025 citation does not show
  that an idea was chosen without knowledge of 2025-26 (the holdout is not sealed from the models' training either:
  forward results are the clean judge). Two small
  residues are accepted: arXiv's relevance ORDER among admitted items is computed on the latest text, and a paper's
  categories are its current ones (a cross-listing added after 2024 can move it into the library's topics).
- **The sources, exactly.** `https://export.arxiv.org/api/query` (search, and metadata by version), the version-pinned
  `https://arxiv.org/html/<id>v<N>` (its `<article>` only), and `https://ar5iv.labs.arxiv.org/html/<id>` (only when the
  served version is the paper's latest and that latest is before the cutoff, confirmed within the hour by a call for
  the unversioned id ALONE: arXiv answers `<id>` and `<id>v<latest>` with one entry, so an answer to both cannot show
  that a later version was left out). A page that names a later version of its paper than the one served (arXiv's
  watermark and image paths carry it) is never served. No PDF is parsed. Every URL is built here and checked by `checkLibraryUrl` (no page of a new-style id after 2412), redirects
  included (at most two, each paced) and only to the same item: the same API query, the same paper and version on
  arxiv.org, the same paper on ar5iv at no version past its confirmed latest. A page over 3 MB on arxiv.org is read to
  its cut and kept (it is pinned); ar5iv is read only whole. The only headers sent are a User-Agent and Accept. No
  secret.
- **arXiv's terms.** "No more than one request every three seconds, and ... a single connection at a time", for all of
  our machines together; arxiv.org's robots.txt: `Crawl-delay: 15`. The Gate paces every request: one at a time across
  the three hosts, starts 3 s apart on the API and ar5iv and 15 s apart on arxiv.org, a backoff of at least 60 s (or the
  `Retry-After`) after a 403, 429 or 503 (a 403 is how a blocked address is told). No upstream request starts later than
  20 s after the library request came in (else `429 {busy: true}`, with nothing sent or counted); every KV operation and
  Gate call is waited for at most 2 s and never past the request's end (a read not back is a miss, a write is skipped).
  So a library request takes at most 37 s (`WORST_MS`: the budget, one 15 s fetch, a 2 s tail); the House's client waits
  at least 42 s, so it never abandons one mid-flight. A waiter asks the Gate again no sooner than its own host's spacing
  allows, and each second only while a turn could come sooner.
- **The budget.** `LIBRARY_DAY_UPSTREAM` (600) requests to arXiv a UTC day, the whole floor, counted in the Gate by host
  and by role (`library` in `/v1/health`); past it `429 {cap: "library_day"}`. Cache hits are free and answer at the cap;
  `"0"` stops every request to arXiv, and cache hits still answer.
- **Orders first.** The library shares the isolate that serves orders, so its parsing is linear on hostile pages: the
  section-heading scan finds `<h2 ...>`/`<h3 ...>` openings with one part that crosses no tag and tests the class on the
  tag found (a class test inside the pattern backtracked: 3.8 s on 288 KB of one malformed opening), 3 MB of every
  hostile shape the reviews found takes under 20 ms, and it looks at 120 headings at most; a library fault is its own request's `500`,
  and the `library` block of `/v1/health` is read under a guard: a malformed library row reads as
  `{error: "library status unreadable"}`, never as a failed `/v1/health`, which the House would read as the kill switch.
- **The web reader** (`/v1/web/fetch`) refuses arxiv.org, its subdomains and ar5iv.org: arXiv is read through the
  library alone, at its pace and under its date rule.
- **The cache.** A KV namespace bound as `LIBRARY` (the Cache API works on custom domains only): searches 7 days, a
  pinned version's metadata 180 days, a paper's latest version 7 days, text 30 days, "no text" 7 days. Every cached item
  is admitted again on the way out. `X-LTCM-Library: hit|miss`. Without the binding the library answers uncached. Text
  read from arXiv serves our own research only: it is never an event, never on the site, never in git.
- **Refusals** carry `refused` or `cap`: `400 {refused: "query"|"id"}`, `403 {refused: "after_cutoff"|"no_reliable_date"|
  "off_topic"}`, `404 {refused: "not_found"}`, `429 {cap: "library_day"}`, `429 {busy: true}`; a `502`/`503`/`504` when
  arXiv failed or asked us to slow down (arXiv's own error answer is an HTTP 400 Atom feed whose entry id is under
  `https://arxiv.org/api/errors`, verified Sept 29, 2026). A version dated after the cutoff is `404 {refused: "not_found"}`,
  as a version that does not exist.
- **Deploy.** The first deploy that carries it, in this order (the House keeps `research.enabled` false throughout, so
  nothing calls `/v1/research` until the last step): create the namespace, `npx wrangler kv namespace create
  ltcm-gateway-library --binding LIBRARY` (a title of its own: the account also hosts the site; answer no if it offers to
  edit the config); put its id into `wrangler.jsonc` as a top-level key after `"migrations"`: `"kv_namespaces":
  [{ "binding": "LIBRARY", "id": "<id>" }],` (the comment by `LIBRARY_DAY_UPSTREAM` says the same) and merge it with the
  library to `main`; then deploy the gateway from a clean checkout of exactly `origin/main` (`git rev-parse HEAD` equal
  to `git rev-parse origin/main`, `git status --porcelain` empty), never from a branch, which would drop whatever else
  `main` holds: `npm run check && npm test`, `npx wrangler deploy` (as run then; today the pinned
  `npx wrangler@4.129.1 deploy`, below). No Durable Object class is added (a new class would end `wrangler rollback` for
  the gateway that carries real orders); never delete the namespace once a version has bound it.

## The desk's own writes and the admin log (LTCM v3, V3-A)

The 30-day unattended clock needs the House to publish its record and merge its engineer's research-class changes with
no laptop step, and the owner to see that nothing else touched production. Four additions, each walled in code (a
constant changes only by a gateway deploy):

- **`POST /v1/github/docs`** ([lib/desk.mjs](lib/desk.mjs)) `{path, content, message?}`: one file committed straight
  to `main` through the Contents API. The path is `docs/runs/desk/<YYYY-MM-DD>[-<slug>].md` with a real date and
  nothing else; the content is UTF-8 text without NUL, at most 64 KB, carrying no credential the gateway holds and no
  key-shaped text (a private key block, a GitHub token, an `sk-` key): `403 {refused: "secret"}`; the message is
  `desk: <one line>` plus a footer. At most 6 commits a New York day (`429 {cap: "docs_day"}`); the same text again
  commits nothing and takes no place (`{committed: false, unchanged: true}`); GitHub's no gives the place back; no
  answer keeps it. What the page says is the House's own public filter (`league/ops` scoreboard).
- **`POST /v1/github/review`** `{pr, head_sha, verdict: "approve"|"reject", reasons}`: the automated reviewer's
  verdict, kept by the Gate for that exact commit after the pull request is read (open, an
  `engineer/<lane>/<slug>-<hash>` branch of this repository aimed at `main`, headed by `head_sha`). A reject is final
  for its commit (an approve after it is `409 {refused: "review_rejected"}`); a revision is a new commit, reviewed
  again. Rejected commits are kept apart from the verdict list (the last 2,000); once one has been forgotten, an approve
  of a pull request opened no later than it is `409 {refused: "review_forgotten"}`, and an approve recorded no later
  than it no longer counts. Nothing is written to GitHub. The reviewer and the engineer present the same runtime token:
  the gateway records verdicts, it cannot tell who gave them, so the review is as independent as the House's own jobs
  keep it.
- **`POST /v1/github/merge`** `{pr, head_sha}` ([lib/merge.mjs](lib/merge.mjs)): a squash merge of exactly
  `head_sha`, only when the branch is `engineer/<lane>/<slug>-<8 hex>` with a known lane and lives in this repository,
  the pull request is open, no draft and aimed at `main`; the latest `checks.yml` run on that commit finished `success`
  with the jobs `gateway`, `tests (3.11)` and `tests (3.14)` each `success`; an approve and no reject is recorded for
  that commit; no changed file (either name of a rename) is protected ([lib/protected.mjs](lib/protected.mjs): the
  list is `league/ci.py` FORBIDDEN, the updater's own wall, and `league/config.json`, held to that by a test on each
  side: the judges and money rules, the House's job framework `league/ops/`, `league/live/`, `league/gym/`, the swarm's
  gate, bands, evaluator, settings, `policy.json` and store, `ltcm/data/`, `scripts/data/`, every module `league/live/`
  and `league/gym/` import or seal into the decider (`league/__init__.py`, `league/structure_core.py`,
  `ltcm/performance.py`, ...), the swarm's spend limits, the harness loop's objective, `.github/`, `gateway/`,
  `deploy/`, `league/house.py`; tests hold each source list as a subset; a package, compiled module or `.pyc` that would
  shadow a protected module, any `.pth`, `.so` or `sitecustomize.py`, and git's own `.git*` files); every one lies in
  the engineer's lane surfaces (`outside_surface`; below) and inside the branch's own lane (`lane_path`), and a
  candidate's test file is only ever added, never changed, removed or renamed (`outside_surface`); all read whole from
  GitHub's list (at most 300 files); at most 2 merges a New York day (`429 {cap: "merge_day"}`); the kill switch not
  engaged (`423 {cap: "kill_switch"}`: with `auto_update` on a merge is a deploy, and the owner's stop must freeze the
  code being looked at). The day's place is taken in one step with the switch and the review checked again. Every
  refusal names its rule in `refused` (`review_missing`, `review_rejected`, `branch`, `fork`, `base`, `not_open`,
  `draft`, `head_moved`, `protected_path`, `outside_surface`, `lane_path`, `files`, `ci_missing`, `ci_pending`,
  `ci_failed`, `ci_jobs`, `github`, `no_answer`). A merge GitHub refused with a 4xx gives its place back; one nothing
  answered, or answered with a 5xx, keeps it (`merged: "unknown"`); the docs route does the same. The proposal, review,
  close and docs routes stay open under the kill switch: they move no money and land no code.
- **The engineer's pull requests** (WP8b; [lib/github.mjs](lib/github.mjs) `ENGINEER_LANES`): `POST /v1/github/pr` with
  role `engineer` and a `lane`, on the branch `engineer/<lane>/<slug>-<8 hex>`. Each lane writes only its surface:
  `scheduler` `league/swarm/loop.py`; `research` `league/swarm/{researcher,preflight,claude_research}.py`; `memory`
  `league/swarm/{architect,strategist,diagnostician,seeds,mechanisms}.py`; `data` `league/{sailbox,data_job}.py`; and
  every lane may add `league/tests/test_harness_candidate_*.py` (`*` one to eighty of `a-z0-9_`). Never a protected
  path, and only what the harness lanes themselves declare (`ENGINEER_SURFACE`: the unprotected files of the lanes in
  `league/swarm/harness_lanes.py`; a test reads them and fails while the list is wider). Two paths of the table are in
  no harness lane's surface, so they are refused, on this route and the merge route, until `harness_lanes.py` names
  them: the memory lane's `league/swarm/mechanisms.py` and the scheduler lane's `league/swarm/loop.py`. The harness
  loop's own scheduler lane (`league/swarm/improvement.py`) changes the `Scheduler` class's body alone, and the file
  also holds the calls to the Sail guard's brake, so the gateway, which reads no class, admits no write to it: the
  scheduler lane opens and merges new tests only.
  At most 6 files of 512 KiB each, 1.5 MiB a request (the other roles keep 12 files of 64 KiB, 256 KiB a request), and
  at most 2 a New York day, counted apart from the other roles' `GITHUB_MAX_PULLS_PER_DAY` (`429 {cap:
  "engineer_day"}`; `/v1/health` `autonomy.engineer_pulls`). A retry that finds its own pull request, or GitHub's no
  before any branch, gives the place back. `league/ci.py` holds the same table (`ENGINEER_LANES`; a gateway test reads
  it) and its path guard judges `engineer/<lane>/` branches by it.
- **The engineer's base**: an engineer proposal names `base_sha`, the full commit its whole files were written against
  (the running release's attested sha). Before anything is written, every file it carries must read on `main`'s head
  exactly as on that base, present or absent alike; otherwise `409 {refused: "base_moved"}` names the files `main`
  changed since (laying the whole file over them would silently undo them), and the engineer rebuilds on `main`'s head.
  An unknown base is `409 base_unknown`. The pull request's body records the base.
- **`GET /v1/github/pr/<n>/files?head_sha=<40 hex>`** ([lib/pulls.mjs](lib/pulls.mjs)): the files a pull request
  changes at exactly that head, each with GitHub's patch, read whole (at most 300 files; a moved head is
  `409 head_moved`); a patch GitHub left out or one cut at 600 KiB (1.5 MiB in all) makes `complete: false`, which a
  reviewer must read as "not seen". Read-only.
- **`POST /v1/github/close`** `{pr, head_sha}`: closes one open engineer pull request at its exact head inside the merge
  route's walls on the branch (a superseded revision, a rejected one). It never deletes a branch, merges or reopens.
- **The admin log**: every kill and unkill and every call presenting `GATEWAY_ADMIN_TOKEN` (refused anywhere but the
  switch) is written with its time, the caller's kind (`admin`, `runtime`), the route, the method and the answer; a
  call at the switch with no accepted token is not written at all: the Gate serializes every order reservation, so a
  stranger's flood at the public switch must not queue writes in front of them (`unauthorized` stays in `counts`). `/v1/health` carries `admin_log`
  (`counts` and the `last` 20, newest first) and `autonomy` (today's docs commits and merges with the last few, the
  reviews recorded), each read under its own guard. A release whose entry cannot be written releases nothing (`503`);
  an engage never waits on the log.
- **`funding` notices** on `/v1/notify` (`league/ops/budget.py` `notice_facts`): one mail that names each of its
  figures. It says what the meter (`sail` or `claude`) holds; the rate the desk is held to on it a day now (its fixed
  cost plus the research the budget rule throttles it to: a ceiling, never worded as a spend) and the runway at that
  rate (`current_usd_day`, `current_research_usd_day`, `current_runway_days`); what the rule wants for it a day
  (`usd_day`: fixed + the research floor + what profit earned) and the runway at THAT rate (`runway_days`,
  `runs_out_on`), which is the one under the card line and the one in the subject; the amount that restores 90 days at
  the wanted rate and the date to add it by. Both runways are days until the meter's reserve, not until it is empty,
  and each is said as days "above its reserve" (the House sends no reserve figure, so none is printed). What happens
  with no card is one sentence, worded from the runway at the held rate when that was sent and from the wanted rate's
  only when it was not, so the mail never says that the meter lasts some days and that it has none left. It says that
  nothing stops (research stays throttled to what the meter sustains) only when the figures sent show it:
  `current_research_usd_day` above zero, `current_runway_days` at or over `card_line_days`, and a runway left at the
  wanted rate. With research already at 0.00 the throttle has nothing left to cut and the fixed cost still runs the
  meter to its reserve, so the mail says how long the meter lasts at the held rate and promises nothing; a runway
  sent as zero at the rate the closing sentence reads says no runway is left above the reserve. It says that the rule
  never raises a cap or moves money. With no `current_usd_day` (an older House, or a balance the rule could not read
  for research) it claims no current rate, says its figures are the wanted rate, and says that how long the meter
  lasts at the held rate was not sent. The composer invents no figure: one that is not a decimal or a date reads
  `unknown`. `test: true` is marked a drill in the subject and the first line, its figures said to be the drill's. A
  `funding*` notice id is remembered eight days (others 48 hours); `NOTIFY_MAX_PER_DAY` is unchanged.
- **`stall` notices** on `/v1/notify` (the owner's goal of Oct 7, 2026, item 6; `league/ops/stall.py` `notice_facts`):
  one mail lists every cause standing (`causes`, each `cause_facts`), each one of `STALL_CAUSES` (`births`, `gym_runs`,
  `validations`, `braked`, `runway_sail`, `runway_claude`, `owner_deploy`, `paused`, `grant_refused`, `kill_on`; any
  other, an empty list, a repeated cause or more than ten is a 400). The subject is this gateway's own words: `LTCM:
  needs you: <the causes with an owner step>` when there is one, else `LTCM: stalled: <the causes>` (three by name, then
  how many more). The body opens with the owner steps ("Only you can do this", one line each, cut at 400 characters) or
  says nothing needs the owner, then each cause: its words, the House's sentence (one line, cut at 400 characters), its
  figures (at most 16, each name a lower-case word, each value a decimal, a date or time, yes or no or a short
  lower-case token, else `unknown`), how long it has stood (`hours`, `since`) and what the House is doing about it. The
  router keys the dedupe itself (`stallKey`), whatever id the House sends: `stall:owner:<the owner causes, sorted,
  joined by +>`, remembered 12 hours, so a new owner step is mailed at once and the same ones at most every 12 hours;
  `stall:info` when none needs the owner, remembered 24 hours. `NOTIFY_MAX_PER_DAY` holds for stalls too.
- **`ENGINEER_HELD`** (`lib/github.mjs`, the self-running release): `league/swarm/researcher.py` and
  `league/swarm/claude_research.py`, the research lane's files the live path loads, are refused to every engineer
  proposal and merge (`outside_surface`, "held from the engineer in this release"), as the House's engineer holds them
  (`league/ops/engineer.py` `RELEASE_CLASSES`). The research lane writes `league/swarm/preflight.py` and new tests.

The token needs nothing new: Contents and Pull requests read/write already cover the docs commit and the merge, and the
Actions runs and jobs it reads are public on this repository. A branch protection rule on `main` that requires pull
requests or reviews would refuse the docs commit and the merge; the owner keeps `main` as it is or exempts the token.

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
npx wrangler secret put CLAUDE_API_KEY           # the Anthropic account (funded total: CLAUDE_USD)
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
npm run check    # node --check on the worker and every module
npm test         # node --test test/*.test.mjs: no network, keys generated in-process
npx wrangler@4.129.1 deploy
```

The check and the suite need Node alone: no lockfile is tracked, so there is nothing for `npm ci` to install from (it
exits 1), and an `npm install` would leave untracked files in a deploy checkout. Wrangler is run at 4.129.1, the version
`package.json` names, because a bare `npx wrangler` may resolve to a newer one. Run the check and the suite, read the
result, then deploy; roll back with `npx wrangler@4.129.1 rollback <version id>`.
No deploy from 13:25Z to 20:05Z on a trading day except a rollback. Deploy the gateway before a
House release that depends on its change. With the House's updater on (from V3-A part 1) nothing does that by itself:
`gateway/` never reaches the box, so a merged change here holds no House release, while unprotected House code merged
with it or after it ships at the next release train. Merge and deploy the gateway change first, then merge the House
change that needs it.
