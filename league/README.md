# The league

`league/` is the House: the one trusted process of the rebuilt floor. It keeps the ledger, wakes the
agents, nets and sends their orders, scores them on a four-rung ladder, sizes their real capital by
their evidence (the allocator, since Sept 23, 2026), pays them compute credits, retires them, and
publishes all of it. It decides no trade. What the project is and how the game
works are in [the repository README](../README.md); why each thing is the way it is is in
[the build log](../docs/runs/2026-09-20-overnight-build.md). This page is for someone changing the
code.

The active spending policy and experiment workflow are documented in
[Phase one](../docs/phase-one.md). Production uses persistent campaign allowances; the legacy
fourteen-day pacer remains only for compatibility and isolated fixtures.

The latest execution record is [the north-star build](../docs/runs/2026-09-23-capital-ladder.md)
(Sept 23, 2026: the allocator, sliced exits, the Alpha Lab, a tick that never blocks,
profit-indexed compute and the open desks), after [Dynamism II](../docs/runs/2026-09-23-dynamism-ii.md)
and the [Sept 22 rebuild](../docs/runs/2026-09-22-overnight-rebuild.md);
[operations](../docs/operations.md) is the operator's page, with the switches. The
[chief architect handoff](../docs/design/2026-09-20-chief-architect-handoff.md) describes the
external spending broker and verifier still to be built. Jev, through the gateway's
[Jev lane](../docs/design/2026-09-20-typesafe-pilot.md), is the House's cheap sensor for the
research gate, triage, hypothesis links and exposure reports (`sensors.py`,
[design](../docs/design/2026-09-22-jev-sensor.md)); its answers carry no order, promotion,
spending or merge authority.

## Design rules

- **Standard library only.** `sqlite3`, `urllib`, `decimal`, `hashlib`, `json`, `threading`,
  `unittest`. Nothing to install on the box.
- **One append-only, hash-chained ledger.** Every intent, order, fill, mark, credit move, trial and
  verdict is a row in `ledger.sqlite`. A row's digest covers its identity, its content and the row
  before it; SQLite triggers refuse `UPDATE` and `DELETE`. There is one chain, not one per stream,
  so a reconciliation can pin a total order (`ledger_seq`, `ledger_digest`).
- **State is folded from the ledger.** Books, credit balances, the registry and rungs are rebuilt
  from rows on start, so a restart rebuilds exactly what the ledger records. Ids are derived from
  durable identities: appending the same id with the same content returns the stored row, and with
  different content raises `LedgerConflict`, so a crash and a retry never record a fill or a charge
  twice.
- **Decimal money in the book.** Cash, prices and quantities are `Decimal`, serialized as strings.
  Floats appear in two places only: the statistics (`stats.py`, `evaluator.py`: evidence, not money)
  and inside the sandbox (`ctx` is plain JSON floats; the House converts what comes back to exact
  decimals).
- **Agents' code never runs in the House process.** A strategy's `decide`, its replay, even reading
  its `NEEDS`, run in the agent's own sealed Sailbox (`sandbox.py`). The House uploads a spec, runs
  `runner.py` or `replay.py` there over Sail's exec API, and reads back one line marked with a
  token that is a secret of that run. `LocalSandbox` does the same in a subprocess for tests and
  laptops; it is a process boundary, not a security boundary, and the House refuses it for real
  money.
- **Everything that decides a fate is a ledger row**: every replay trial, every block of growth,
  every look with the alpha it spent, every promotion, demotion, death, audit, grant and charge.
  Payload keys beginning with `_` are private (strategy source is one) and never leave the box.
- **The constitution is not configuration.** `constitution.py` holds the thresholds, written before
  any agent traded; a test pins its digest and the House writes the digest to the ledger at every
  start. `game.json` holds the economy's tunable dials, inside bounds the file itself lists.
  `config.json` holds where things are and four operating dials; it never holds a secret.
- **Replays, research and Merton's role passes run beside the tick.** These tasks
  run on background threads in three lanes that cannot starve one another -- replays, research and
  housekeeping -- so a slow replay never delays a research pass or a deploy; the first real tick took
  six minutes before this rule.
- **The tick never waits on background work** (Sept 23, 2026). Each box has its own lock
  (`SailSandbox.claim`, `patience`). The tick waits at most `Settings.box_wait_seconds` (2 s) for
  an agent's box and `probe_wait_seconds` (15 s) for the probe box, then skips the wake or defers
  the births to the next tick (`SandboxBusy`: nothing ran, nothing charged). Research admissions and
  the lab's births make no Sail call under the lifecycle lock that every wake takes. What was put
  off is in `health.json` `deferred`. At
  05:07Z that day a hung Sail call on the probe box held the first tick for about twelve minutes.
- **Lifecycle changes validate their inputs at commit time.** A wake, research pass, replay or
  audit carries the strategy and rung version it started with. The House rechecks that version
  before applying results and again before submitting a batch of wake intents. A slow model
  response cannot rewrite a retired agent or authorize a replacement strategy's trades.
- **Internal crosses and pooled fill allocations are atomic.** `Ledger.append_many` commits
  each complete group or nothing. Private recovery plans retain exact prices, fees and attribution;
  even a rollback to an older release sees complete normal fill rows. Risk checks reserve earlier
  accepted intents in the same batch before considering later ones.

The [persistent trading command](../docs/runs/2026-09-21-persistent-live-trading.md) enables the
full earned ladder without a deadline, using the owner's fixed current-cash allocation and
only unspent research allowance. Its default report mode and deployment do not activate it.

The current [gate audit](../docs/runs/2026-09-21-game-gate-audit.md) documents the event-based
qualification path and prepared live-learning activation. `episodes.py` folds trusted cash and
position receipts into completed, non-overlapping exposures. `live_pilot.py` records an explicit
owner activation without changing the original campaign, commitments or deadline. Promotion
status is exposed in health and agent research context; qualification is distinct from funding.

## Modules

| Module | What it does |
|---|---|
| `ledger.py` | `Ledger`: the append-only, hash-chained SQLite record. `append` (idempotent on id), `read`/`iter`/`last`, `verify()` re-hashes the chain, `agent_view()` and `public_view()` are the only ways rows leave. `KINDS` lists every row kind and whether it is public. |
| `book.py` | `Book`: one netting book per venue account. Folds each agent's cash and holdings from the ledger; runs every intent through the first run's 21 risk rules plus the league's (since Sept 23, 2026 ~16:00 UTC a real-money bunt's per-desk daily-loss line is set where it cannot bind, `allocator.bunt_daily_loss`, and the real book's halt is `allocator.real_halt` of the venue's grant capital, both from the two callables the House gives a real book, `band_of` and `halt_basis_usd`; `risk_lines(agent)` reports the lines in force; an equity limit order may be fractional and is a `day` order, A7; since Sept 23, 2026 ~22:00 UTC each account's opening equity for the UTC day, which both daily-loss lines read, is kept in `day_open.<book>.json` beside the ledger with the ledger's head when it was taken, and a restart restores it and replays that day's later `book.stake` rows, so a restart mid-day forgets no loss and counts no stake twice) (the $75 order cap, the rung's position and order caps, cash including fees, quote age, no shorts, no leverage, no ENTRY that could trade against the House's own resting order, never both legs of a Kalshi market; since Sept 24, 2026 (D3) an exit that could is cleared instead (`_clear_the_way`): the seller's own crossing order is cancelled; a peer's bid at or above the market's bid is cancelled at the venue and, once the venue has confirmed the cancel and its fills (`cancel` books a read AFTER the cancel, with two short re-reads for Alpaca's `pending_cancel`), crossed inside the House as one `book.cross_plan` (`_cross_resting`: the seller a taker at the market's bid, never under its own limit, the bidder a maker at its own limit, the House row keeping the gap, no cross without a fresh market bid, `cross-house` rows mirroring each fill, the exit never also netted, what is left of the bid not re-placed); bids under the market's bid are left and the exit goes to the venue one price step above them (`_floored_exit`); any doubt rests it post-only at the ask (`_post_only_exit`), and every re-priced order's rows carry the reason and the agent's own terms (`house_repriced`): the agent's next sell of the instrument cancels such an order first (`_withdraw_repriced`) and each poll re-prices it or sends the agent's order again once nothing is in the way (`_recheck_repriced`); and the real book's entry rules (X0: `allocator.longshot_floor_real`, `real_entry_liquidity` with the House's `family_taker` callable, `max_event_share` on an event = a ticker's first two segments, Kalshi's own event, as `league/tapes.py` and the evaluator read it), each absent with its key, listed in `risk_lines(agent)["entry_rules"]`); nets one batch's market orders and crosses the minority side inside the House at the venue's touch and taker fee; attributes venue fills pro rata; reconciles to the venue against a baseline taken at start, booking under a cent a fill as dust and freezing new entries (never exits) on more -- except that a PRACTICE book takes the venue's word after three readings that do not reconcile, moving the difference to the House's own baseline (no agent's record is flattered) rather than stopping every agent on that venue indefinitely, and since Sept 24, 2026 books any cash difference under `PRACTICE_DUST_USD` ($1.00) to the House row as dust at once while every position agrees and no order is in doubt (a `detail` beginning "practice book:"; the venue's option fees and fill rounding froze `alpaca-paper` daily and rolled Deploy C back); a real-money book still freezes, and says so. Since Sept 23, 2026 a sell worth more than the order cap (an exit, a wind-down, the horizon rule, a stop) is an `ExitPlan`: slices of at most the cap, each its own venue order with a deterministic client order id, their fills attributed to the one intent per slice, the book reconciled after each. The plan is durable (`book.exit_plan` rows), so a refused or partly filled slice leaves the rest to the next `poll`, and a restart resumes it without sending a slice twice. The book counts an Alpaca market order as the gateway does, at the ask plus 10% (`GATEWAY_MARKET_MARKUP`). Entries are unchanged: one order of at most the cap. A Kalshi limit order filled with no fee is booked as the maker's fill (#174, Sept 23, 2026): the book labelled every limit order not marked post-only a taker's, and the auditor vetoed a paper agent for "zero-fee taker executions" that were resting orders paying the maker's fee. |
| `fees.py` | `Fees(venue)`: what a fill costs, as measured. Alpaca crypto takes 0.25% out of the coins on a buy and out of the proceeds on a sell and reports a fee of zero; Kalshi's taker formula is rounded up to $0.0001 an order. |
| `venues.py` | `gateway_broker(name, ...)`: the first run's Alpaca and Kalshi adapters in gateway mode. `alpaca-paper` is the same adapter signed with the paper keys. `market_hours` for equities. |
| `constitution.py` | `CONSTITUTION`, `digest()`, `PINNED_DIGEST`. Changing it means changing the pinned digest too, in a commit the owner makes. |
| `stats.py` | Pure functions: `log_growth`, `mean_bounds` (one-sided t bounds, with its own `t_quantile`), `spend` (alpha per look), `lopsided` and `lopsided_growth_lcb` (the exact Clopper-Pearson loss-rate gate), `deflated_sharpe`, `cusum_decay`, `quarter_kelly`, `max_drawdown`. Degenerate data returns `None`, never raises. |
| `evaluator.py` | `Evaluator`: `record_trial` (scores a replay and counts it against the candidate and its ancestors), `observe` (turns equity marks into blocks of log growth), `judge` (looks, promotion eligibility, death -- the screen reads a TRAILING drawdown window because a running maximum never falls, and a look that spends no alpha is not rationed; since Sept 23, 2026 the screen also counts the block in progress (`_unfinished_growth`), and a daily agent on a Kalshi book with 3 settled trades on its rung is screened after one finished day (`_settled_lane`); since the owner's swing-and-bunt revision of the same day, promotion to scaled size spends `ladder.promotion_alpha` while death spends `alpha`, and replay's out-of-sample floor is `ladder.replay.min_oos_growth`), `drift` (a CUSUM on the edge per closed trade against the record of the rung below, on rungs 2 and 3), `promote`/`demote`/`seat`. `closed_trade_rows` is the one definition of a closed trade (an instrument gone flat), read by `trade_returns` and the allocator's family record; since Sept 24, 2026 (D4) the counts that gate a move to real money are INDEPENDENT (`independent_closed`, `_settled_lane`): once per event on the event books (`event_key`: an explicit event ticker, else the market ticker's first two segments) under `allocator.independent_settlements`. It reads the ledger and writes `eval.*` rows; the House acts on the verdicts. |
| `replay.py` | Rung 0: walks a strategy over a tape one step at a time with conservative fills (a resting order fills only when a later step trades strictly through it). Self-contained (standard library plus `safety.py`): it is uploaded into the agent's box as it is. `run_batch` (Sept 23, 2026, the Alpha Lab) replays many candidates over one tape read once, each in a process of its own (by default at most 2 GB above what it inherits, and 300 s), and returns for each exactly what `run_replay` would. A candidate the batch's time budget did not reach, or one the box could not start a process for, comes back `not evaluated`, never as a result against it. |
| `options_history.py` | `OptionsHistory`: a resumable SQLite store of listed-option contracts (expired ones included), OPRA trade bars, optional prints and the House's recorded live OPRA quotes, with `data.coverage` rows (`asset: option`). Builds the options desk's replay tape (a contract exists from its first print; quotes are ESTIMATED from prints, since Alpaca has no historical option quotes) and the equity desks' `options_features` (Black-Scholes IV, 25-delta skew, volume and trade counts), stamped with when each became available. `python -m league.options_history ingest ...`; the House refreshes it daily. |
| `options_replay.py` | The options desk's rung 0, reached from `replay.py` for a tape with `asset_class: option`: point-in-time listing, the 100 multiplier, an assumed $0.05 a contract a fill, limit orders filled only by later bars (at the worse of the shown and a conservative touch when marketable, else only on a print a tick through, or at a recorded OPRA touch), liquidity limits, day orders, the 14:30 expiry offer and a write-off at zero. Uploaded into the box beside `replay.py`. |
| `feeds.py` | `FeedRecorder`: the feeds the House records for its strategies, in `feeds.sqlite`, on the one-slot `feeds` lane. Live feeds are stamped with the House's receive time and never backfilled -- ESPN scoreboards of the leagues the sports desks trade (every 60 s while a game is on or about to start, else every 15 minutes, never a past date), perpetual funding and open interest (every 5 minutes) -- and history feeds (`HISTORY_FEEDS`) with the moment the source says each value became final, backfilled over the replay window: Deribit's DVOL and OKX's settled funding (Sept 23). Sept 24, 2026 (workstream I): the recorders of the hosts the owner allowed are `Source`s in `RECORDERS` -- `weather` (Open-Meteo ensembles per settlement station and NWS climate day), `nws`, `forecast` (lead 1-3 day forecasts, history stamped 11:00 local standard time), `earnings` (8-K Item 2.02 at EDGAR's acceptance time, sparse history), `earnings_date` (Nasdaq), `rates` (NY Fed), `treasury` (par yields), `odds` (ESPN core lines and predictor), `tsa`, `polls` (RCP, blocked by its bot wall), `oi` (OKX hourly open interest, history), and the keyed `eia` and `consensus` (The Odds API), which wait (`waiting_for`) until the owner's key is in the House's `.env` and the host is in `scripts/floor_box.py` LEAGUE_HOSTS. A new recorder is a `Source` subclass: `keys`, `key_of` (its NEEDS vocabulary), `fetcher`, then `poll` (live: a payload, `UNCHANGED` or the exception per key; `batch` for one request answering every key) or `page` (history: the rows of one request with `reached`/`exhausted`, as `_page` for `vol`), plus `asks` (which tool-request names it answers) and its describe texts. Every feed: unchanged content stored once, a failure a failed poll with nothing stored (a key a source does not list, `NOT_LISTED`, or a site that refuses the House, `BLOCKED`, is said in health, not warned hourly; a source whose failed poll is read in full at its next one names a key in the hourly warning only after `Source.warn_after` failures in a row, `earnings` three, with 45 s for EDGAR's slow browse feed, Sept 24, 2026), a `data.coverage` row (`asset: feed`, `host`) an hour, a block in health.json and `describe()`. `NEEDS["feeds"]` puts the latest rows in `ctx["feeds"]`; a replay shows them point in time and is refused as unsupported input (not a trial) until a live feed spans the replay gate's `min_blocks` or a history feed's backfill is in. Fetchers and parsers live in `ltcm/data/` (`openmeteo`, `weather`, `edgar`, `nasdaq`, `rates`, `sports`, `attention`, `derivs`, `eia`, `oddsapi`), each tested on payloads recorded Sept 24, 2026 (`ltcm/tests/fixtures/feeds`). |
| `history.py` | The deep-history store (`<root>/history/history.sqlite`) and `python -m league.history ingest|coverage`: Alpaca bars since 2016 (raw and adjusted), quote probes and trade windows, fetched in resumable chunks through the gateway; unavailable (the venue had nothing) is kept apart from unfetched (a gap in the store). Each finished run becomes a `data.coverage` ledger row. `series_without_bars` (Sept 24, 2026) names each symbol a tape over a fetched window would hold no bar of, with where its history begins: `House._deep_tape` refuses such a development tape as unsupported input and `House._holdout` refuses before opening the seal (D1's root: an ADA/USD tape over 2025 was built with no steps and the lab's step failed on it for hours). |
| `deep_replay.py` | Tapes from the history store, built by the same `AlpacaData` code as live ones; the development window before the sealed holdout; `HoldoutSeal` (one evaluation per version, a budget per line, `holdout.access` rows, coarse numbers only). |
| `tapes.py` | `AlpacaData` and `KalshiData`: recorded tapes for replay and live snapshots of the same shape. A bar is stamped with the moment it closed; a Kalshi row carries only what was on the screen; a capped board is a seeded draw that never looks at volume or results. Since Sept 24, 2026 (L4) a Kalshi tape reads the settled listing a whole UTC day at a time (`_settled_day`): a settled day has the same URL every time, so `ltcm.history`'s disk cache answers it after the first read, and the day still settling is served from memory for `settled_listing_ttl` (600 s), then read again only from the line settled at the last read (12 h before it). Before, a tape's first window began at its own moving start and the settling day was read whole for every tape: KXETHD's listing, seven pages at a time, for every Kalshi tape built. Since Sept 24, 2026 (C-perf) a settled day is read from History once a process and kept in memory (`_remember_settled`): only the fields the tape reads (`SETTLED_FIELDS`; a new reader of the settled rows adds its field there), times as epoch seconds (`parse_time`'s own answer), equal text and decimals held once a day, at most `SETTLED_MEMO_ROWS` (400,000) rows, the least recently used day out first; `settled_memo_rows = 0` reads History every time. Before, the disk cache answered but every row was parsed again for every tape (and logged as if fetched: `History.kalshi_settled` now says only what it fetched); a 14-day tape of KXBTC, KXBTCD, KXETH and KXETHD took about 58 s every time on the developer machine, and 10-12 s once its days are held (about a quarter of the CPU: a median 80 against 19.5 CPU-seconds, interleaved). |
| `paper.py` | `KalshiShadowBroker`: a simulated Kalshi account over live quotes. Holds no credential and sends nothing. State in `kalshi-shadow.json`. |
| `sim.py` | `SimBroker`: a simulated Alpaca account that behaves as the paper venue was measured to. A canary House trades on it, never on the shared paper account. |
| `economy.py` | `Economy`: balances folded from `credit.*` rows; `grant`, `charge` (never refused: the compute is already spent), `transfer`, `shares`/`payout` (a quarter as niche floors, three quarters won on growth SQUARED x root active blocks x the rung's weight; before anyone is profitable the won share goes to the least-bad TRADER, never split evenly), `can_fork`, `box_cost`. `load_game` and `check_bounds` read `game.json`. |
| `game.json` | The economy's dials (pool, floor share, rung weights, endowments, fork threshold, population bounds, the audit's cooldowns and who pays for it, research cadence and pace, the foundry, the Alpha Lab) and the bounds the game designer must stay inside (`bounds`, `horizon_bounds`, `merton_bounds`, and since Sept 24, 2026 `lab_bounds`: `economy.check_bounds`). |
| `agents.py` | `Registry` and `Agent`: identity, strategy versions, lineage, niche (`venue/horizon/style`) and fate, folded from the ledger. The House adopts code in place on rung 0 or on paper with no record to protect (no holding, working order, active block or closed trade). New code for an agent on real money always starts as a child. |
| `niches.py`, `niches.json` | The specialties: each desk's venue, horizons, universe, brief, founders and seats (`max_members`), and the daily survey that lets a Kalshi universe follow the season (`survey`, `apply_survey`). `constrain` cuts a strategy's NEEDS to its desk. Since Sept 23, 2026 two open desks (`"open": true`), `kalshi-open` and `alpaca-open`, 8 seats each, admit any market of their venue (`admits`; Kalshi's `^KXMVE` combos and options excluded). A strategy there is shown only what it names, twelve at most (`MAX_UNIVERSE`), or, when it names nothing it may trade, the first twelve of a discovery list `OPEN_DISCOVERY` (24) long: on Kalshi the survey's busiest series, those no desk covers first; on Alpaca the other Alpaca desks' symbols, coins first. `match` seats a program with no desk on the one desk that claims most of what it names, and on its venue's open desk only when it spans desks or names markets no desk lists (`spanning`). |
| `sandbox.py` | `SailSandbox` (one Sailbox per agent, forked from `agent_image_checkpoint`, sealed with an egress allowlist of `sealed.invalid` before it is recorded, destroyed if it cannot be sealed) and `LocalSandbox`. Both offer `decide`, `needs`, `replay`, `replay_batch`, `fork`, `retire`, `sleep_all`. Since Sept 23, 2026 (E3): a reentrant lock per box; `claim` holds a box for a block of work, waiting at most so long; `patience` makes a call from this thread give up on a busy box with `SandboxBusy` (nothing ran, nothing charged). Sail calls carry tighter timeouts than the client's: a resume, a checkpoint and a batch's result download 120 s, a new box 180 s, an upload 60 s plus 4 s a megabyte. A background sleep gives up after 60 s on a box a run holds, and `sleep_all` puts boxes to sleep side by side for at most 60 s. `replay_batch` runs many candidates in one box against a tape uploaded once, gzipped, under its SHA-256; a tape that reaches into the sealed holdout is refused before anything is sent (`TapeRefused`). `bind` adopts a box made elsewhere (the lab's); if Sail reports it gone, `BoundBoxGone` is raised and it is never replaced from the agents' image. |
| `runner.py` | Runs one `decide` (or reads `NEEDS`) inside the box: 5 second limit, strategy prints discarded, one `DECIDE-RESULT <token>` line, then `os._exit`. |
| `safety.py` | `check_code`: the import whitelist and the banned constructs (no underscore attributes, no attribute assignment, no `eval`/`exec`/`open`/`getattr`). Ported from the first run's Foundry, where it was hardened against real attempts. Imports nothing from the league. |
| `commons.py` | `Commons`: web search (Sail's search API, Google News RSS as fallback, $0.01 charged per query), the research library, the tool-request queue (ordered by demand; unresolved and blocked engineering requests remain visible until explicitly resolved), the playbook. All of it is ledger rows. |
| `researcher.py` | `Researcher`: a cheap model's tool loop for one agent (a Sail model, or GPT-6 Luna through the gateway for the share of sessions `fast_research.ResearchRouter` sends there), every token and tool call charged to that agent. Its `replay` tool is a counted trial. A passing candidate is adopted on rung 0 and forked above it. A session the provider failed (`research_gate.provider_fault`: HTTP 500, 502, 503, 504, 529) has its research-token charges refunded in one `credit.grant` (`refund_provider_fault`, Sept 24, 2026). |
| `rules.py` | `rules_text(game)`: what every agent is told, generated from the constitution and `game.json` so it cannot drift from what is enforced. |
| `jev.py` | `Sensor`: Jev (TypeSafe jev-1.13.0 through the gateway) as a cheap yes/no sensor. Answers are cached by the caller's key, batched 16 questions a request, capped per UTC day (dollars, calls, calls per purpose) before any call, and an unconfirmed call is counted at the worst case. After a failure a breaker opens and callers decide without it. Labels carry no order, promotion, spending or merge authority. |
| `sensors.py` | `JevFloor`, the House's one hook for the Jev work below (`config.json` `jev`): `research_due` (from `House._gate`), `tick` (inactivity sweep; triage, links and exposure as background jobs while open for business) and `health` (`health.json` `jev`). |
| `research_gate.py` | `ResearchGate`: skips a clock-due research pass only when nothing relevant changed. The triggers are fills, settlements, refusals, code or rung, material verdicts, a fulfilled request, credits (not the routine epoch payout, since Sept 23, 2026), a niche note, market availability and a lifted blocker. Since Sept 23, 2026 (`clock_runs: winners_and_idle`) the clock alone runs nobody but a winner (a positive earned record) or an idle agent: everyone else researches only on a trigger (the list above plus an active forward block, an audit or repair verdict about it, and a teacher's lesson naming its desk or family), the heartbeat and the sample; and after `abstain_lock_after` (3) empty sessions only its own fill, settlement or refusal wakes it until a session produces a candidate. Each row carries `trigger` and `record`, and `report()` prices each trigger (`by_trigger`). It backs off repeated empty passes on the v0 dials (`game.json` `research.gate`), waits out known blockers, keeps a 24 h heartbeat, asks Jev only whether an out-of-niche note matters, and samples 10% of skips. `Inactivity` writes `agent.inactive` when a reason changes. `report()` and `python -m league.research_gate LEDGER` print skipped sessions, estimated savings, the sampled miss rate and Jev spend. Since Sept 24, 2026 (L2): `lock_profile` is the profile a locked agent's new session runs on (`abstain_lock_profile`, flash_asap; `routing.TaskRouter.research_settings` applies it); `provider_fault` is the refund's predicate and `completed_pass` the one definition of a pass that the gate's streak, the House's empty-pass count and displacement read, so no refunded session is counted as a pass. Since Sept 25, 2026 (F2 and X2, rules 9-12; `clock_runs: real_positions`): the clock runs only an agent on real money that holds a position or a working order or met a refusal since its last session (and rung 0); everyone else researches on a trigger, an idle program on its barren outcome (`idle_runs`), with a 72-hour practice heartbeat counted from first sight (24 h on real money); a practice agent pauses after three abstaining sessions until its next fill; the sample draws once per six hours an agent; a refusal triggers research once per agent, reason and day (`refusal_class`, `refusal_news` for the House's fast path); a lesson is the teacher's and wakes only the `lesson_arm` half. Rows carry `money`; `report()` adds `by_money` and `refusals_deduped`; `scripts/gate_replay.py` replays the rules on a ledger. |
| `triage.py` | `Triage`: tool requests, post-mortems, abstentions and journals/thoughts become deduplicated `repair.reported` rows (`source: triage`) with their evidence and affected agents. Grouping is exact first, with the repair worklist's keys and excerpts so both reporters fold into one job; Jev decides "same missing feed?" (merge only at high confidence), "does this report a bug?" and "same defect?". |
| `hypothesis_memory.py` | `HypothesisMemory`: stated mechanisms (cards, candidate purposes, docstrings) linked as `hypothesis.link` (rewording / related / distinct; exact or Jev). A link never changes genealogy or trial counts. `failure_history(ref)` returns a mechanism's own failures beside its linked mechanisms'. |
| `exposure.py` | `Exposure`: open bets grouped across agents by Kalshi event and series and Alpaca underlying, plus Jev-related contracts. Report only (`health.json` `jev.exposure`); the risk layer decides. |
| `seeds/` | The fourteen founding strategy files (Kalshi, crypto, equity and options) and `all_seeds()`. They are data, not modules: nothing imports them. |
| `strategies/` | Strategies Merton adds as architect, and the engineer's corrected children; each `<stem>.py` is described by its own `<stem>.json` (`name`, `family`, `why`, and `repair` for a corrected child), so two proposals never rewrite one shared file. The House enrolls each once, on rung 0, corrected children first (`House.enroll`). Since Sept 23, 2026 a full league makes room for them (`Settings.enroll_displaces`): the seat of an agent still running the code a repair corrects, else the weakest eligible resident. With the foundry on, a corrected child is instead replayed under its own line BEFORE any seat (`Foundry.takes_strategy`, later on Sept 23, 2026: the engineer's 16 children had 0 forward blocks and 7 died on rung 0): it is born only on a pass, through the refill like a card, seated on paper, with the strategy's name as its founder; a child that fails is never born, and its repair job closes with the replay's reasons. Once a corrected child is born, the agents off real money still running that code are retired as `superseded`. The code a repair corrects is the sha in a `strategy_defect:<agent>:<sha12>` key, or its named parent's code; a repair that names neither (a bug report about a desk) retires nothing. A strategy that cannot be born is tried again only when its file changes. The shared `registry.json` is retired (Sept 22, 2026) and CI refuses a Merton branch that writes it. |
| `tools/` | Pure helper modules Merton adds as toolsmith; uploaded beside the strategy so it may `from tools.<name> import ...`. Empty at the start. |
| `playbook/` | Lessons Merton adds as teacher, one markdown file each; the House loads each into the ledger's playbook once, and again when its text changes (Sept 23, 2026). |
| `house.py` | `House`: `found`, `spawn`, `enroll`, `seat`, `wake`, `judge`, `kill`, `fork`, `research`, `keep_population`, `tick`. `Settings` are the House's own dials. Since Sept 23, 2026 (E3) `tick()` runs with box patience (`Settings.box_wait_seconds`, 2 s): a wake whose box is busy is due again on the next tick. `_births` (a proven family's program first since R3, then forks, founders, merged strategies, the refill) runs holding the probe box (`_probe_turn`, `probe_wait_seconds`, 15 s) or is deferred (`_defer`, `health.json` `deferred`), and a Sail failure in it is deferred instead of failing the tick. `_admit_researched` reads a research candidate's NEEDS holding only the probe box, then births it under the lifecycle lock, re-reading its queue row so it is never born twice; `_admission_gate` holds the checks that make no Sail call. A replay box that does not answer is infrastructure, never a trial. On TERM, `begin_close` starts no new background work and no births. The mark pass calls `Allocator.rebalance`, and the tick schedules the Alpha Lab's step (`lab.tick`). `standings()` builds the table once a tick, on the tick's own thread, and reuses it while the living roster is unchanged (#173: ranking every agent afresh for displacement, the refill and the foundry had taken about 80% of a 191 s tick); anywhere else it is built fresh. The order path's own guards (workstream B, Sept 23, 2026): `_fit_order_type` turns an option market intent into a limit at the touch and re-prices a crossing post-only Kalshi order one tick inside it; `_submit_wakes` drops the intents of an agent whose seat on the book is gone, with one warning a day (`_note_unseated`) instead of a `book.refused` row each; `due` drains a backlog (a resumed House) one desk at a time, the desk longest without a wake first (`_every_desk_first`, `desk_woke` in house.json); and `_order_path_invariants` warns once a day about a refusal for an agent that is not alive, and once per half hour about a round-the-clock desk with living members and no wake for 30 minutes while the House is not paused (since Sept 24, 2026 counted from its oldest living member's birth too, and at twice its briskest member's `wake_minutes` when that is longer). `_offered` counts, for a Kalshi wake, only the markets of the series its NEEDS names that resolve inside its horizon: the busiest live series a desk shows a program whose own are dark make a `shut` wake, not a `barren` one. Since Sept 24, 2026: `alert` escalates a warning that repeats (`alert_key` folds numbers and ids; the same text 10 times in 30 minutes is one error alert with the last payload and `began_at`, listed in `health.json` `repeating_warnings` until quiet for 30 minutes; the runs live in house.json); `_health_failures` reports `health.json` `failures` for the watchdog (`lab_evaluates`: an hour with candidates queued and no batch); `research_due` starts no new Sail session while the last hour's Sail research spend has reached turbo.json `sail_research_usd_per_hour` (`_sail_cap_state`); and a session the provider broke is closed as cancelled and given back in 15 minutes. |
| `budget.py` | `Budget`: reads Sail's credit balance, counts a month's spend as the sum of its falls, returns `open` or `stopped`, and says on the ledger when that changes. It guards the ACCOUNT only -- the month's line (the constitution's, plus the owner's recorded top-ups that month) and the reserve -- because it once also latched on the expedition's budget and, since `Pacer.spent` only grows, that latch had no key. |
| `campaigns.py`, `campaigns.json` | `CampaignBudget`: the owner-funded campaign and its burst. Every paid call reserves a hold before it is sent and settles from its response; unknown costs keep their holds. The Sail balance meter (`meter_required`), the owner's top-ups, and the live grant (`live_trading`, `ratify_live_trading`). `absorb_stale` (Sept 23, 2026) settles at $0 the Sail holds older than the meter's lag that have no response, because the meter already counts their charge; each release is kept in `cost_reconciliations`, and nothing is released while the meter is unhealthy or behind what has been settled. `mirror_gateway_bonus` (Sept 23, 2026) raises the burst's OpenAI line by exactly the gateway's profit-indexed raise, never more (at most $1,000), and the raise lapses when it has not been mirrored for 30 minutes (`GATEWAY_BONUS_SECONDS`). `CampaignPacer` paces the House by it. No role may change either file. |
| `live_trading.py` | The owner's persistent grant: `policy(venue_capital)` (agents = the allocation divided by the micro stake, or by the smallest real stake while the allocator is enabled -- the $10 Kalshi probe since Sept 24, 2026, 101 seats on $1,017.75, the loss line = the allocation, pinned to `money_digest`), and `--enable`, `--disable` and `--ratify` (the same capital under revised money rules), run on the box by `scripts/live_trading.py`. |
| `grants.py` | Phase-scoped Luna startup grants, claimed durably before the call; one per family/niche, twelve maximum and $0.25 reserved each. |
| `frontier.py` | `Frontier.ask`: one metered call through the gateway's `/v1/frontier/responses`; the cost comes back in `X-LTCM-Cost-USD`. Priced Astra, Sol, Terra and Luna routes, GPT-5.6 and GPT-6; the default is Astra. The campaign hold is the call's worst case at the model's ceiling rates. Since Sept 23, 2026 a verified call settles it at the gateway's metered cost (before, at every token's long-context ceiling when that was higher), a refused one (HTTP 4xx) at $0, and a call with no answer keeps it. `frontier_tier` and `TIER_ROLES` say which work the month's remainder still pays for. `FrontierMonth.profit_bonus` (Sept 23, 2026) is what the gateway's profit indexing adds to the month (`cap_usd` less `base_cap_usd` in `/v1/health`), read with `remaining`, and `House.frontier_remaining` mirrors it onto the campaign. |
| `hypotheses.py` | `Foundry`: the hypothesis foundry that replaced routine House-staked mutation refill (Sept 22, 2026). It asks Merton, on GPT-6 Sol at high effort, for 3-4 `hypothesis.card`s for a desk. Routes, offered in this order: up to `transfer_share` (0.3) of recent calls port a family with an earned forward record (real money first) to the best-scored desk of its venue where it was never tried; up to `fast_share` (0.5) go to the desk in `fast_desks` with the best forward yield of its own foundry children (`desk_forward`, from active `eval.block` rows), then the fewest recent cards (before Sept 23, 2026 always the best-scored one), and never to a desk whose foundry-born agents are negative over `fast_lane_min_blocks` (6) active blocks until one family there is positive over `fast_lane_reopen_blocks` (3); up to `exploration_share` go to the least-explored desk; the rest to the desk the evidence favours. Each card has a mechanism, data, edge after costs, horizon, rejection evidence and a whole strategy file. The packet adds horizon guidance (`prefer_horizon`), forward results by family on the desk, the league's edge map (`winning_mechanisms`), on a transfer call the ported mechanism in words (never code), and the fees, the Kalshi maker fee included. A card is replayed through `House._candidate_replay` under the id its child would carry, and only a passer is born, onto paper. A family with 15 counted failures and no pass is retired (`disproven`, or `blocked_data`/`blocked_infra` plus a `repair.reported` row). Every birth gets a `route.decision` saying why it happened. Dials in `game.json` `hypotheses`. **E2 and E3 of the close-the-gaps run (Sept 24, 2026; `foundry-2026-09-24.1`).** Cards are model-versus-market mechanisms: the packet's `data.recorded_feeds` lists the recorders a card on the desk may read (`DESK_FEEDS`, with what each is, how to declare it and whether a replay can judge it now), and a card must state `fee` (what each trade pays) and `edge_needed` (the gap between model and price that clears it) or it is refused before its replay. `fast_desks` is the deep-market desks (megacaps, index ETFs, crypto majors, both open desks); `closed_desks` (kalshi-crypto-strikes, kalshi-crypto-15m) get no call on any route until a family there is positive over `closed_reopen_blocks` (3) active forward blocks on that desk (`_closed_desks`, from `_closed_desk_forward`: the `eval.block` rows of the family's members that lived on the desk, one block a block key however many members were active in it; not `House.family_forward`, which pools a family over every desk and counts each member's block). `first_transfer` is the first transfer the transfer route tries (`_first_transfer`): the weather favourites scaled on the ensemble's fair value on their own desk, a packet `transfer` marked `scale` with its own `ask` and feeds, once, then the ordinary ports. The packet's `forward_on_this_desk` carries each family's measured capacity from the mechanism ledger (`_capacity`: `Allocator.family`'s estimate and `lab.family_at_capacity`), and a family at its capacity gets no evidence-driven House mutation. Options has no replay, so no card can be admitted there. |
| `lab.py` | `Lab`: the Alpha Lab (Sept 23, 2026). A MAP-Elites archive in `lab.sqlite`: per cell (desk, horizon, trades per day, correlation with the live book's real returns) the program with the best out-of-sample growth after fees on the lab's search tape (the first two thirds of the House's own replay tape, never the holdout). Seeds are living agents' programs, foundry cards and founders; children are parameter mutants, Luna's mutations and crossovers and, every `leap_every` calls, a Sol leap. A step breeds (up to `param_children`, 48) whenever fewer than `batch_size` queued candidates have a fresh built tape (`ready_queued`, #173), since each seed waits for a tape of its own. Batches run on the lab box (`labbox.py`) off the tick (`replay:lab:step`). The fittest gate-passing program of a cell is replayed by the House (`_candidate_replay`, a counted trial on its own line) and the sealed holdout where it applies (`_holdout`, with one budget per lab lineage, and never the last `holdout_reserve` evaluation of a line still living), then born on paper with `founder` `lab:<lineage>`, at most `max_births_per_hour`. A birth reads its NEEDS holding only the probe box, never under the lifecycle lock (`waiting_probe` when the box is busy), and a graduate waiting for a seat (`waiting_seat`) is asked again at most every ten minutes. The lab stops while the House is closing, stopped, paused or staging a release, when the Sail allowance or meter has stopped it, and for five minutes after a failed batch (an hour, with an error alert, when its bound box is gone). An OpenAI tier below `all` stops only its Luna and Sol calls (C2, Sept 23, 2026: `breed` skips those phases before any packet is built and `_ask` refuses them; parameter children, batches and graduation go on, and the skipped phases are on record in `lab.stats` `llm` and `health.json` `lab`). The lab watches itself on every tick (`_watch`): closed for `closed_alert_minutes` (30) it says so once (a warning naming the refusal, an info when it works again; the since-when is in `meta`, so a restart does not reset it), and a graduate that has waited `seat_wait_alert_hours` (6) for a seat is named once. `lab.stats` rows (every 10 minutes) and `lab.graduate`/`lab.royalty` rows are private. Royalties: `royalty_share` of a graduate's performance fee pays the lab's line. Researchers get `lab_query` and `lab_submit`; agents with evidence get `research.evidence_max_turns`. Dials in `game.json` `lab`; runs only where `config.json` `lab` names a box (`box_id`). **S2 (Sept 23, 2026, the learn-and-unblock run).** Queue order is `PRIORITY`: an agent's submissions, then seeds and the Luna/Sol children together, then parameter mutants (at priority 2 behind their elite's dozens of mutants, 0 of 394 LLM-written children were evaluated in six hours); `_next_batch` visits the reserved origins' rows first on the largest-group turn, so their tapes are built first, and reserves a third of the batch for them on the chosen tape (`reserved_share`, a half, since E1 below). Tapes are keyed by `tape_key` (NEEDS without `style`, `parameter_rules`, `wake_minutes`, `max_hours_to_close`): a Luna child that differs from its parent only there is the parent's tape, not a build of its own, and only a tape the House had to build counts against `max_tapes_per_step`. Each result keeps `tape_source` (`history-dev` or `live`), so the graduation's ration check (`_holdout_refusal`, before any House trial; the ledger of that day shows no trial on any rationed line) does not depend on the tape cache after a restart. **Forward windows** (`forward_windows`, every `forward_every_minutes` from the step, on the lab box): the archived elites and the graduates waiting for seats are replayed on the steps of their tape that came after their code was frozen (`forward_cut` at the hour after the evaluation or the graduation's pass: no search, replay or holdout saw them; on an Alpaca tape the earlier bars become warm-up history), at most `forward_candidates_per_run` (48) candidates and `forward_box_seconds` (90) a run, never scored first (the graduates waiting for seats before the elites among those, since D1), then least recently scored; on the deep-replay Alpaca desks, whose House tape is 2025 history, the lab builds the live tape of the last `forward_days` (7) through the House's Alpaca adapter, once a run. Each run writes one row per candidate to the `forward` table of `lab.sqlite` (window, blocks, active blocks, log growth, trades; the archive's fitness is never touched) and `forward_at` in `meta` afterwards, so a restart resumes from the table. The record RANKS: `forward_score` (mean log growth per block, None under `forward_min_active_blocks` active blocks; `waiting()` and health.json carry it for the House's seat market), `elites` (a winning window before every untested program, a losing one after them; that order decides who graduates first and what agents see first) and `lineage_weights` (a lineage whose pooled window loses, -1; wins, +1). It never counts as practice evidence, never promotes, never writes `eval.*` or `holdout.*` rows and never changes a gate result. **Floor feedback**: `_floor_score` reads each born graduate's row on the allocator's board (practice: W_paper above or below 1 after `forward_min_trades` closed trades, +1/-1; real: W_real after a real trade, +1/-1; else its standing as before; a death -1), and the lineage score is clamped to [-3, 3] before 2^score, so a lineage keeps between an eighth and eight times the search whatever the floor says. **Priors**: `priors` reads every ```lab-prior``` block in the latest text of each lesson in the ledger's playbook (`playbook.entry`; see `league/playbook/README.md`); `pause-param-forks` breeds no parameter mutant of the named family/lineage/desk/cell until `until` (`forward-positive`: the lineage's own window is positive; a day; or for good). The first is `2026-09-23-pause-prior-window-fade-forks.md`. **Holdout budgets and fresh windows (S1.1)**: the seal's window is `deep_replay.HOLDOUT`, fixed, and `HoldoutSeal.used` counts a lineage's opened rows over every window; re-issuing a lineage's three evaluations for a new window was NOT built, because the only data a new sealed window could be cut from (the live tapes since May 2026) has already been replayed thousands of times by agents' own trials, so it is not unseen and a fresh budget on it would loosen the seal. The honest counterpart is the forward window: data that arrives after a program is frozen ranks it; it never buys another look at the seal. (Every `holdout.access` row already records its `window`, so the old-window counts are on record if the window is ever moved by an owner deploy of `deep_replay.py`.) **D1 (Sept 24, 2026): the step says why, and no candidate stops it.** From 23:21:59Z Sept 23 every step failed with an IndexError (115 identical warnings in 2 h 18 min, no traceback, nothing escalated): a queued Luna child asked for ADA/USD alone, whose hourly development window the history store had fetched and found empty (ADA/USD trades on Alpaca from Feb 2026), and `_search_tape` read the first step of a tape that had none. A tape with no steps is now unsupported input (its row blocked, the answer kept for the hour); anything else a queued row's NEEDS, tape or result raises blocks that row (`_block_row`, one warning a step naming the rows, at most `row_errors_per_step` (8) a step, past which the step fails instead: a defect that breaks every row is the lab's). Each phase of `step` (royalties, seed, breed, the batches, graduation, the forward windows) is guarded on its own (`_guarded`): a failure is a warning with its `phase` and `_traceback` (the last 2,000 characters of `traceback.format_exc()`, private: `public_view` strips it), and the phases after it still run. `_note_step` keeps `failures_in_a_row`, `failures_first_at`, `last_failure` and, after `failures_alert_after` (5) in a row, `failing_since` in `meta` with ONE error alert carrying the traceback; a step that works again clears them (an info if it had escalated). `health()` and `lab.stats` carry `failing_since`, `failures_in_a_row` and `error`. **The tape index** (`_tape_index`, `meta` `tape_index`): every search tape built in the last six hours, its key, when, the lab's tape id (what `batches.tape_id` names), the House's tape id and its source (`history-dev`: rebuilt from the history store on the House's own disk; `live`: fetched). Not the tape: a search copy is cut again from the House's tape. After a restart `ready_queued` (`_ready_keys`) counts the rows whose tape the House holds in its cache or rebuilds from disk, so the step evaluates before it breeds (after the 23:40Z restart it was 0, and every step bred first). **Residents' forward windows (S2 of the close-the-gaps run, Sept 24, 2026)**: `forward_due` also takes every living agent's current program on a desk the lab searches (`_residents`, by `resident_candidate`: the file with its parameters written in, as `seed` admits it; queued, evaluated or failed, never blocked), never-scored graduates first, then residents, then elites, then least recently scored, inside the run's own budget; a resident's window starts after its program was frozen (`_program_frozen`: its birth or its latest `agent.strategy` row) on a `forward_resident_cut_hours` (6) grid, so the residents of one tape share a batch. `resident_forward` is what the House's seat market compares a newcomer's forward score with. **Tapes the House will never fetch** (Sept 24, 2026): a build the House's tape reader refuses for its size ("ask for a shorter window", `TOO_LONG`) is unsupported input and its row is blocked (mcentee-hddb4ae's three megacaps submissions had been re-queued at priority 0 every hour); a build that fails the same way `tape_failures_before_block` (12) hourly tries in a row is too, with one warning (`meta` `tape_failures`); and a row whose tape failed this hour never decides a batch's turn. **E1 of the close-the-gaps run (Sept 24, 2026): the lab as a search.** At T0 2,137 of the 3,641 candidates were parameter mutants and 16 of the 18 born graduates were nudges; after Deploy A the lab ran 63 batches of 84 candidates in an hour (1.3 a batch: 65 of the 69 Luna children queued at T4 asked for NEEDS of their own, a tape each, and a step builds four). `_next_batch` groups the queue by tape and builds at most one tape a batch; whose turn it is is `batch_turn(turn, reserved_share)`: `reserved_share` (game.json `lab`, 0.5, `lab_bounds` 0.33-0.75, held to them where it is read) of the turns build the tape where the programs someone wrote wait (`RESERVED_ORIGINS`: submissions first, then the tape with the most rows), the others alternate the queue's oldest row and the largest group of any origin; and `reserved_quota` gives the written programs that share of every batch where they wait. `graduate` holds (`_hold`, before the House's replay and again before a waiting graduate's birth, in its own `graduations` state `held`, detail `held: ...`: not `passed`, so the House's seat market (`_waiting_graduates`) and the scoreboard do not count it as a waiter, while `forward_due` scores it as one) a candidate whose forward window loses (search fitness only admits) or, with no window of its own, whose mechanism's windows on its desk lose on average (`_mechanism_forward`: only elites, waiting graduates and residents are scored, so a cell walked past a held elite would reach its untested parameter twins), one whose desk was offered markets for `idle_desk_hours` (48) with no intent unless a feed it asked for arrived in that time (`_idle_desk`: a `tool.fulfilled` for one of its agents' `tool.request`s that is not the toolsmith's refusal, `DECLINED` "cannot be a pure tool", whatever its status, or a feed its programs or requests name whose first `data.coverage` row with data was recorded then: the row's time, never its `start`, which for a backfilled feed is months back), and a nudge: the same program beyond PARAMS (`mechanism_digest`: the syntax tree without the PARAMS literal, docstrings, and NEEDS `style`, `parameter_rules`, `wake_minutes`, `max_hours_to_close`) as a living program of its desk, unless its forward score is above the desk's living median (`_desk_median`, the residents' ranked scores; zero while none has one). `held` (counts by reason) is in `lab.stats` and health.json. Breeding (`_pick_parent`) multiplies a parent's lineage weight by its own forward window (`FORWARD_BREEDING`: x2 winning, x0.25 losing); `lineage_weights` adds each archive lineage's family score from the mechanism ledger (`_family_score`: `Allocator.family` read through `families.score`, +1 proven or swinging, -1 negative past the proof's count) and weighs 0 a lineage whose family is at its measured capacity (`family_at_capacity`: the swing held by capacity, or `families.capacity_holds` at twice its size; never measured again here), which is then never drawn. Sol's leaps go to `deep_desks` first, and never to a desk the idle rule holds while one a leap's graduates may be born onto is left. Luna is told (`lab-2026-09-24.1`) that a child on its parent's NEEDS runs in the parent's batch and that a parameter-only child is a nudge. |
| `labbox.py` | `LabBox`: the Alpha Lab's batch evaluator (Sept 23, 2026). `evaluate(candidates, tape_id, tape, ...)` answers one result per candidate, in order, each exactly what a single replay returns, from a batch on the lab's own Sailbox (`sandbox.replay_batch`, `replay.run_batch`, at most 256 a batch). The tape goes to the box once, keyed by its SHA-256, and is sent again only when the box says it lost it. Only development data enters: a tape in or across the sealed holdout is refused before anything is sent. `LabBox.from_config` binds `config.json` `lab.box_id` (made by `scripts/lab_box.py create`, size l, sealed). A failure of the box or of Sail is a `SandboxError`, never a candidate's result. In `ci.FORBIDDEN` with `lab.py`: it produces the numbers a lab candidate is judged by, and it is the door that keeps the holdout out of the lab box. |
| `auditor.py` | `Auditor.audit` (the evidence packet and the veto; `charge=False` when the House pays, which `game.json` `audit.house_pays` makes the default from Sept 23, 2026, and each verdict records `paid_by`) and `score` (what each veto cost or saved, scaled to the micro stake). The House decides when it runs: after promotion to the micro rung (`ladder.paper.audit` "after"), or before it for an agent with a known defect. |
| `preaudit.py` | `PreAudit`: a free, deterministic look at a paper agent's code and first wakes (errors, dropped intents, refusals, barren wakes, cent rounding). It files repair reports and a promotion-status mark, never a kill; a red mark makes the frontier audit come before any promotion (`House._known_defect`, Sept 23, 2026). |
| `merton.py` | `Merton`: the schedule and one pass of each pull-request role, brought round sooner while the day's frontier allowance is unspent; `consult`, where he WRITES the hiring agent a strategy file rather than advising it; `GatewayForge` (production) and `GhForge` (the owner's machine, through `gh`); `evidence_from(house)`, which shows the architect how each desk's members are really faring and the operator the checker's own bounds (and, since Sept 24, 2026, no private `_`-prefixed key of an alert or budget row). `paused_until_profit` (game.json, Sept 24, 2026): those roles do not sit down while `RealPnl` -- the realized result of the real books' settlements and closing fills over the last 24 hours -- is not positive, with one `ops.budget` "merton pause" row per role when it pauses or resumes; `pause_state` is health.json's view of it. F4 (Sept 25, 2026): the consultant may be paused the same way (`consult_paused`); `consult_verdict` judges a paid consult productive if the agent retained a candidate or changed its strategy within `merton.lift.consult_sessions` (2) sessions, `consult_price_multiple` doubles an agent's next consult for each unproductive one in a row (up to 8x; `Researcher._consult` applies it to the minimum credits and the charge), and `consult_blocks` gives its forward blocks before and after. |
| `worklist.py` | The repair worklist: the fold over `repair.reported` / `repair.status` (dedupe by key, original evidence kept, priority = agents x recurrence x severity, states proposed ... verified / rejected / dormant) and `Sources`, the deterministic reporters: audit vetoes, refusal reasons across 3+ agents or wakes, CI-refused Merton PRs, tool requests and the toolsmith's blocked verdicts, research that names a missing input. Jev triage writes `source: triage` rows and is folded the same way. |
| `engineer.py` | The repair engineer, Merton's sixth job with no more authority than the others: one paid patch a step for the top admitted job, a pull request through the same gateway route and path guard, CI's failure text read back (`GET /v1/github/pr/<n>/failures`) for at most `max_attempts` revisions, then `canary` (the running release holds the files), `observing` and `verified` only if the signal has not recurred. Strategy defects become new child strategies, which since Sept 23, 2026 are replayed before any seat (`Foundry.takes_strategy`, from `House.enroll`) and born only on a pass, a failed one closing the job with the replay's reasons (`_child_refused`); and a `strategy_defect` is bought only while its parent is alive and has a fill of its own (`_parent_idle`; a dead parent's is `rejected`, an untraded one's waits free); anything outside the role paths is `dormant: needs core authority`. Settings in `engineer.json` (owner-only). `scripts/repair_drill.py --plant` files a labeled synthetic job through the House's `repairs-inbox/` (the House stays the ledger's only writer); a drill asks no model and spends nothing. Each step leaves the queue in `<state>/repairs.json`. |
| `yield_ledger.py` | `YieldLedger` (Sept 23, 2026): one `ops.budget` row an hour (`what: "yield"`), folded from rows that already exist: spend by paid line (research tokens, each Merton role, audits) and the evidence each produced (sessions, abstentions, candidates, replay passes, active and positive forward blocks, cards, proposals, lessons, consult answers and failures), with `usd_per` unit, and (Sept 24, 2026) `by_profile`: research sessions, candidates, provider failures, token dollars and `candidates_per_usd` by model profile. Replay passes and forward blocks are credited to the line that wrote the code (a card's to the foundry, `lab:` to the lab, a merged repair's child to the engineer, an architect's strategy to the architect, the rest to research). Runs on the foundry's bookkeeping tick. Since Sept 25, 2026 (F4) lessons are the teacher's only (post-mortems counted before), the row carries `lift` (`lifts`: the teacher's lesson arm against its control on forward growth over 3 days, the consultant's next 6 blocks against its previous 6 and dollars per positive block beside research's, the engineer's repairs verified per dollar, each with a `verdict`), and the tick first writes the due `consult.outcome` rows (`consult_outcomes`). |
| `ci.py` | `python3 -m league.ci`: the path guard (`ROLE_PATHS`, `FORBIDDEN`, `CONFIG_DIALS`), content checks for strategies, tools, `game.json` and `config.json`, then the suite. Also makes the canned regression tapes; since Sept 24, 2026 the Kalshi tape carries deterministic `observed_bars` for the symbols a strategy's NEEDS observe, at its declared timeframe, so a strike strategy that watches spot bars can pass (Merton's PRs #217 and #208 could not). |
| `capital.py` | `kelly_stake` and `resize` (rung 3), `recommend` (the standing capital recommendation, an `ops.recommendation` row). `resize` and `top_up_micro` stand down while the allocator is enabled. |
| `allocator.py` | Capital is the ladder (Sept 23, 2026). `evidence` computes `W_paper` (Alpaca paper haircut, per asset class since A8: `_haircut_rate`), `W_real`, `E` and the trade counts. `target_band`, `bunt_stake` (a bunt keeps what it makes: `bunt_usd` × clamp(W_real, 1, `swing_at`) under `allocator.bunt_growth`; an options bunt is `allocator.option_bunt_usd`), `swing_stake` and `limits_for` are pure rules. `band_of` and `halt_basis_usd` are the two facts a real `Book` reads for the constitution's daily-loss keys (`allocator.bunt_daily_loss`, `allocator.real_halt`). `Allocator.rebalance` makes the mark pass's moves, stakes, deaths and performance fee inside the envelope and the throttle. `_size` never refills a losing bunt (W_real under 1), but lends one that was lent less than its target (the base, or the throttle's half of it) up to it, net of what it has been lent (`account.staked`): a bunt seated before a base raise, or halved by the throttle, is restored to the base less its own losses (Sept 23, 2026). `Allocator.board()` is what the publisher and the watch read. **Promotion on proof (Sept 24, 2026, the close-the-gaps run).** `closed_trades` counts once per event on the event books (D4). `family_record` is a family's pooled forward record: every member ever born, living or dead, one observation per independent event (per closed trade on Alpaca), ln(1 + r) of `Evaluator.trade_returns` read through each trade's own ledger position (what had been lent by then; an Alpaca practice trade less the practice haircut E takes off the same fills), members of one event pooled at the largest weight (real 1, practice 0.5), the weighted mean, sd, n_eff and the one-sided `family_proven.confidence` bound on Student's t, with a lopsided record also held to `stats.lopsided_growth_lcb` at that confidence (`family_proven.lopsided_gate`), the maker and taker records apart; `TradeTape` folds fills, settlements, stakes and cutoffs by kind after a cursor, so a pass reads only new rows. `Allocator.family` caches a record per pass; `tier` is "probe" (`probe_bunt_usd`) or "bunt" (`bunt_usd`) by the family's proof; `family_taker` is the book's `real_entry_liquidity` fact. "probe" is a first-class band: the board's rung-2 rows, its `bands` summary and the verdicts' `band_from`/`band_to` say "probe" or "bunt" (the publisher and the site know it since #222 and personal-site #6), while the rung and the book's daily-loss rule (`band_of`) read "bunt" for both. Board rows carry `family`, `family_state`, `family_bound`, `family_n`; verdicts and the audit's `allocation_context` carry the family record (the context also its `tier`). `target_band` applies the hysteresis exit only after `hysteresis_after_settled` independent real results in the stay (`Evidence.real_stay_closed`), and `limits_for` holds a Kalshi position to `position_share_event` of the stake. **The family swing (Deploy B, Sept 24, 2026).** The family record moved to `families.py` (this module keeps `family_record`, `TradeTape`, `_pool` and `_family_rule` as thin wrappers, so a test that patches `allocator.family_record` still stands in for it). `_begin_pass` computes every followed family once (every living agent's, and every proven or swinging one) and moves its state in the mechanism ledger (`families.next_state`, kept in `allocator.json` `families` with its `since`; the first start restores them from the last `family.record` rows); a read between passes computes the same state without writing it, and a record that cannot be read is an unproven family's for money without moving its state. `tier` stays the proof ("bunt" for a proven or swinging family); `rung2_band` names a swinging family's rung-2 member "swing" on the board, the tape and the book (`band_of`: the book's own daily-loss rule, as every swing). `target_stake` stakes a swinging family's member at `families.swing_target` (never under its bunt; a rung-3 agent never under it either); a newcomer the pass's record did not count shares the family's caps with one more member (`_swing_for`) and is counted once seated (`_admit`); the swing holds only while the live grant releases rung 3 (`_swing_released`, read once a pass). A proven family's entry is judged at its real count's checkpoint (`families.entry_look`: 15 real settlements and every `entry_every` more, on the first that many real events, at `entry_confidence`), and it stays while `families.swing_ready` holds at 80%. The entry is audited: `_request_family_audit` starts one on the audit lane (`audit:family:<family>@<venue>`) against the member with the most real closed trades, with the family packet (`_family_packet`) and `allocation_context` (`_family_swing_context`); the verdict lands in `allocator.json` `family_audits` (from the ledger's `audit.verdict` `family_swing` after a restart), and `audit_standing` never reads it as the member's own verdict; a veto waits out `game.json` `audit.cooldown_hours`, an error `error_cooldown_hours`, and an approval licenses entries until it lapses (`_swing_approval`, `_lapse_approval`: the family leaves the swing, or a member takes a new program or is born into the family after the audit looked, which the tape reads from `agent.strategy` and `agent.born`; a swing already running is untouched), and the next entry is audited again. `swing_allowed` is `allocator.swing_requires_proven_family` (read by `House._commit_promotion` too). `_persist_families` writes `family.record` rows at most every five minutes for families whose row changed (digests in `allocator.json` `family_rows`). The board's rows add `capacity` (`usd_per_day`, `binds`) and `stake_limit`, and its top level `families` (per venue, per family: `families.row_of`). `family_forward` is a drop-in for `House.family_forward` (the House's births and the foundry through `_losing_family`), and `family_score`/`lineage_score` are what `Lab.lineage_weights` may read. **No probe on a losing family (R5, Sept 24, 2026; `allocator.family_probe`).** `_begin_pass` reads every family's forward record once (`forward`: `family_forward` on the pass's tape) and folds the ledger's probe demotions since the last pass (`fold_demotions` over `eval.verdict` and `family.record` rows after `allocator.json` `probe_holds.cursor`: a demotion from rung 2 is a probe's by its `band_from`, or, naming no band -- drift, an audit's veto, tuition -- by the family's last `family.record` state before it; `unfunded` never); the first fold reads the whole ledger, so a House that lost the file holds the same families. `probe_gate` is "losing" (`families.losing` at `losing_min_blocks`), "held" (`probe_hold`: the earliest of the family's probe demotions whose record since has not turned -- the active blocks that BEGAN after the demotion (`first_mark_seq`, the tape's `began`), positive over as many as the pass finds them, `families.gaining` via `_turned`; a turn is for good and `_prune_holds` drops it, and each demotion is its own hold) or "unreadable" (a failed tape, fold or forward read this pass: no probe is seated or lent more, nobody is demoted for it), for a PROBE only: a proven or swinging family's agent never. `_bunt` waits a gated promotion (`family_losing`, `family_held`, `family_unreadable`) before any audit or displacement, `refuses_probe` asks again when an audit approves a known defect's seat (the one-line hook in `House._commit_promotion`), and `_weakest_bunt` never displaces a probe of a probe newcomer's own family. Step 2 of the pass returns a seated probe on a losing family to practice (`_drain_probe` -> `_move_down`, `rule: "allocator.family_probe"`) when `_unflat` says the demotion path sells nothing: event contracts are held to settlement; working bids are cancelled first, as the path itself does (a cancel the venue does not answer leaves it waiting and the pass going on); any other holding it would sell (dust is booked) or a buy still in question at the venue waits, once flat, and `_size` lends it nothing more meanwhile; a family whose record cannot be read demotes nobody. The board's rows add `equity_usd` (beside `stake_usd`, the net loan), `family_forward` and `probe_gate`, and each family its `swing_clock` (`families.swing_clock`, R3); the publisher sends none of them to the site. It is a money judge, in `ci.FORBIDDEN`. |
| `families.py` | The mechanism ledger (C1 of the close-the-gaps run, Deploy B, Sept 24, 2026): the one place a family's record is computed. `TradeTape` folds, by kind after a cursor, every agent's fills, settlements, stakes and evidence cutoffs, the House's buy orders by member (`Bid`: a family's capacity) and every agent's `eval.block`s. `family_record` is the pooled forward record (every member ever born, one observation an independent event, practice 0.5 and real 1, the one-sided bound and the loss-rate gate for a lopsided record, maker and taker apart, the REAL-only record with each event's first close, active blocks, the edge per dollar at risk, and `capacity`: markets bid a day, fill rates by bid size, real settlements a day, dollars a day at the stake). Its unit is `family_proven.unit`: "at_risk" (`at_risk_value`: ln(1 + 1% x made / at risk) / 1%, finite at a whole loss; `risked_at_close` reads each position's cost; each event weighs what it put at risk against its member's mean on that book, so the record is sum made / sum at risk) or "account" (Deploy A's account growth). `event_share` is the most of a stake one event may hold (what Kelly's at-risk fraction becomes a stake through), and `change_view` what makes a `family.record` row worth writing again. `pool` also returns the `honest_bound` (the t bound and the gate: the smaller) and Kelly's `variance` (at least the loss-rate model's for a lopsided record). `entry_checkpoint` and `entry_look` (the entry, at its checkpoint), `swing_ready` (the hold, at the table's 80% every pass), `positive_since`, `capacity_holds` and `swing_target` are the family swing's pure rules (`allocator.family_swing`); `next_state`, `row_of`, `restore_states`, `losing` and `score` the ledger's. A money judge, in `ci.FORBIDDEN`. |
| `shards.py` | The Kalshi shard funder (Sept 23, 2026, U2). Kalshi runs markets on several exchange shards and an order on an unfunded one fails with `insufficient_shard_balance`. `ShardFunder.tick` runs on the tick (a cursor scan of new `book.order` rows: a real order refused that way is a warning alert naming the agent, market and shard, and a pass is requested); `ShardFunder.run` is the hourly pass on its own background lane (never behind Merton or the backup): reads the cash per shard, works out the wanted shards from the `exchange_index` of the markets the living Kalshi desks are offered plus every shard holding a real position or resting order, and tops up each one under `FLOOR_USD` ($20) with `TOP_UP_USD` ($30) from the richest other shard that keeps its floor (`KEEP_USD` $60 on shard 0) and the stakes of the desks on it (a stake whose shard cannot be told is kept on every donor). A shard where a real order was refused is topped up on the venue's word even above the floor, once an hour. Bounds: $100 a move, $200 a rolling day counted from the ledger (a move whose outcome is unknown counts); nothing under the kill switch, an inactive grant, a pause or a frozen real book, read again before every move; a failed move backs the shard off an hour; a blocked or failed pass tries again in five minutes. Every move is an `ops.alert` with a `shard_move` payload (transfer id, amounts, balances before and after). State in `shards.json`; `health.json` `shards`. A money mover, in `ci.FORBIDDEN`. |
| `publish.py` | `Publisher`: cleans ledger rows into the site's exact event and checkpoint shapes and posts them. Cursor in `publish.json`. Since Sept 23, 2026 each desk row carries `band`, `stake_usd`, `evidence` and `last_move`, and the checkpoint a `board` (bands per venue, the last 50 moves, the throttle), from `Allocator.board()`, or from rungs until the allocator has drawn one. Since Sept 24, 2026 (C4, the mechanism ledger) a desk row also carries its family's `family_state` and `family_n` (`site_family_fields`: both or neither), the board the proven and compounding families (`site_families`: at most eight, compounding first, each with its honest lower bound, the stake of a member on real money and how many there are, and its capacity a day; and the unproven count), and the lab's hourly reading (`site_lab`, from the newest `lab.stats` row while it is at most 30 minutes old: strategies tested in the last hour and graduates waiting for a seat, with or without the allocator). The site validates every one of them (`personal-site` `capital/schema.js`) and refuses a checkpoint with a field it does not know: a new field ships on the site first. The roster is bounded to the site's `MAX_DESKS` (160, with the last 8 dead) and its checkpoint size, since a checkpoint over either is refused whole. |
| `service.py` | `build(root, ...)`: the real House from `config.json` and three secrets (`GATEWAY_TOKEN`, `SAIL_API_KEY`, `CAPITAL_PUBLISH_TOKEN`), read from the environment or a 0600 `.env`. `canary=True` builds a House that can hurt nothing. |
| `__main__.py` | `python3 -m league run | tick | found | status | verify | stop | start`. |
| `watchdog.py` | `python3 -m league.watchdog deploy | status | rollback | prune`: releases on the box, the canary, promotion, the watch, the rollback. Imports nothing else from the package at import time. `read_health` reads `health.json` `failures` as bad readings (Sept 24, 2026), and with `inherited_before` (the watch passes the promotion's moment) counts a failure whose `since`, or an error alert whose `began_at`, is earlier as inherited, never a rollback: the lab's idle hour cannot roll back a release, a canary still refuses on it, `status` shows it. A frozen book in a `health.json` dated before the House's first `ops.started` since the promotion is the old process's (`frozen_by_previous_process`), not the release's. |
| `updater.py` | How merged code reaches the House box with no human step: every half hour it reads `main`'s head and downloads that exact commit (public, no credential). GitHub's API must show the pinned Checks workflow and every required job of it passed on that sha. A change to the judges (the running release's `ci.FORBIDDEN`), to the workflows or to `real_money` is refused as the owner's deploy. The RUNNING release's content checks judge the tree (`league.ci --content-only --root <tree>`, its own process with a scrubbed environment; until Sept 22, 2026 each tree judged itself). Then it hands the tree to the watchdog for canary, promotion, watch and rollback. A tree the watchdog really judged is never tried again; one refused only because another deploy held the lock is, because the promotion's own restart makes that race the normal case. |
| `CONTRACT.md` | The strategy contract. |
| `config.json` | Gateway and site URLs, the agent image checkpoint, `real_money`, the operating dials, the performance baseline. |

## The life of one tick

`House.tick()` is the whole loop (`python3 -m league run` calls it every `tick_seconds`, 60).

1. **Settle and poll.** For every book: advance the simulated venues (`advance()` fills resting
   shadow orders the market has traded through), poll resting orders for fills, apply new Kalshi
   settlements. One venue's outage is an alert and does not stop the others.
2. **Check the budget.** `open` or `stopped`: the Sail account's line (`budget.py`), then the
   campaign, whose Sail meter must have been read and whose allowance must be open; a maintenance
   pause also closes business. Once the meter has been read, every ten minutes, Sail holds older
   than an hour with no response are absorbed into it (`CampaignBudget.absorb_stale`, Sept 23,
   2026) and an `ops.budget` "holds absorbed" row says so. OpenAI's meter is the gateway's frontier
   month, read here on every tick (`FrontierMonth` into `CampaignBudget.observe_month`, Sept 24,
   2026): OpenAI holds older than six hours with no answer are absorbed into it the same way, the
   House's OpenAI line never reads above what that month has left while it is read, and a gateway
   unread for three minutes stops paid OpenAI work (the tier reads "audits" and an alert says so),
   never the floor. When stopped, only
   agents holding real-money positions or orders are woken, so they can exit; research, Merton,
   payouts and births wait.
3. **Wake each agent that is due** (at most 16 a tick, 6 side by side; its own `wake_minutes`, 5 to
   1,440). If its code has not had its replay, one is started in the background. A rung-0 agent
   stops here. Otherwise the House seats it (limits and stake for its rung), builds its snapshot
   (its account, its open orders, closed bars and the touch, or Kalshi's open markets), runs
   `decide` in its box, charges the box seconds, keeps its `memory`, records its `thought`, applies
   its cancels and converts its intents to exact decimals. A malformed intent is dropped and
   reported; a failed wake is an alert, never a failed tick. Since Sept 23, 2026 a wake whose box
   background work holds (its research replaying a candidate there) waits at most 2 s, then is
   skipped and due again on the next tick (`deferred` `wakes`).
   **The wake skip (Sept 24, 2026).** An agent everything of which keeps the regular US session (a
   stock or option desk, an open desk naming no coin) is not woken while the session is shut
   (`_shut_session`): no snapshot, no box, no order, no `agent.woke` row. Its cadence and its idle
   bookkeeping stand (`_note_wake`, so research is paced as before), `_next_wake` wakes it a few
   seconds after the bell, where a held position's exit goes at once, and `health.json`
   `wakes_skipped` counts the skips by desk. In the 48 hours to T0 of the close-the-gaps run 2,891 of
   9,884 wakes were such wakes (9,424 billed box seconds, 75 refused market orders, 21 research
   sessions pulled forward by those refusals). An agent still woken outside the session (an open
   desk naming a coin) has its stock or option entries refused by the House with a reason it reads.
   **Paused entries (X1, Sept 24, 2026).** An agent that paused its entries (`pause_entries`,
   `Registry.entries_paused`) has every buy its code sends held before sizing: counted as `held` on
   `agent.woke`, never a `book.refused` row (which would pull a research pass forward each wake),
   and its resting buys that are its alone are cancelled when the pause is made and at each wake
   (`_cancel_paused_entries`). Its sells, cancels and settlements go on. Held buys are not activity
   (review of #249, P3): the wake counts it barren when it is shown live markets (the stuck rule
   and research's idle cadence read that), `_displaceable` takes a resident paused past the grace
   like one that never traded, and the seat report counts it as holding none (`_paused_past`,
   `_seats_holding_none`). The allocator promotes a paused agent to no real band (its
   status says "paused"), and after `allocator.PAUSED_STAKE_AFTER_SECONDS` (24 h) holds a paused
   real agent's stake to the probe by free cash only (P2; the board row's `entries_paused_since`).
   **The horizon's basis (X2, Sept 24, 2026).** `resolution.resolution(row, close)` is when a Kalshi
   market is expected to pay and what that is judged by: its scheduled (expected) expiration where
   the venue gives one, its close otherwise, never the deprecated latest date it may expire
   (`ltcm/data/kalshi.py` keeps `expected_expiration_time` apart). The venue gives one for every
   market seen (1.36 million cached rows, review of #249), but where it lies two days or more after
   the close it is a deadline (the diesel prints, the AI-share weeklies), and the market is judged
   by its close plus its series' measured settle lag (`resolution.SettleLags`: the p95 of the last
   40 of its settled markets before the day, at least 20; fed by every Kalshi tape's settled
   markets and kept in `settle_lags.json` beside the House's state; review of #249, P1), or by the
   deadline while that cannot be measured. `league/resolution.py` is a money judge
   (`ci.FORBIDDEN`: an updater release cannot change what the book admits), and it reads
   `settle_lags.json` as untrusted data: an entry that settled before its close or is not three
   finite times with a real deadline is ignored, each lag is clamped to [0, its deadline], and a
   series needs 20 good settlements. The live view's `hours_to_resolve`, a replay tape's and the
   book's horizon rule (`KalshiData.resolves_at`, `resolution_of`) read it alike. A Kalshi entry past the horizon is refused by the House before
   the book (`_horizon_refusal`), saying which it was judged by; what it cannot look up it leaves
   to the book.
4. **Submit one batch per book**, so opposite market orders on one instrument net inside the House.
5. **Every `mark_every_seconds` (300), per book:** poll, mark every account, reconcile to the venue
   (a mismatch is an error alert and freezes new entries; a practice book's cents are booked as dust,
   `book.PRACTICE_DUST_USD`). Then judge each living agent on that
   book: close finished blocks of log growth, take a look if one is due, and act on the verdict:
   `die` kills; `eligible` promotes. From paper that needs real money on, the owner's grant, room
   in the capital envelope and no audit cooldown running. Since Sept 23, 2026 the agent then takes
   the micro stake at once and Merton's audit follows on the micro rung, in the background; an
   agent with a known defect (a red pre-audit, or a merged corrected child of its code) is audited
   first, as before. On rung 2 the House commits an audit after promotion that finished before a
   restart, or starts one that is owed, and a veto demotes to paper. A micro agent down 20% since
   promotion returns to paper. On rungs 2 and 3 a drift alarm demotes, and the House winds the account down and re-seats the agent on the book of its new rung.
   Retry unfinished exits for dead agents and abandoned books, preserve working sells, record
   their final evidence (including later settlements), and sweep closed accounts' free cash.
   Since Sept 23, 2026 a wind-down's sale of a stock or an option waits for the regular session
   (`wind_down_held` in `house.json`, told once as an info alert): outside it the book refused the
   market sell on every mark pass (576 "market orders outside regular hours" and 116 "an option
   order must be a limit order" refusals in a day, all from the House liquidating dead agents), and
   `_release_wind_downs` places it in the first tick after the bell. A coin's or a Kalshi position's
   wind-down is not held. After the allocator, `_floor_invariants` reads the ledger's rows since its
   saved cursor (never the whole ledger; every five minutes) and raises an ops warning once per
   condition: a desk offered markets for an hour with no intent from any of its agents (once a desk
   an hour; since Sept 24, 2026 a desk whose offered agents are all day programs after a day without
   an intent, once a day, `QUIET_DESK_DAY_SECONDS`), and a real-money bunt frozen by a daily-loss rule
   (once an agent a day).
   **Since Sept 23, 2026, while `allocator.enabled`, capital is the ladder.** After the books are
   marked, `Allocator.rebalance` runs (`allocator.py`). The screen and the micro bound above no
   longer promote: an `eligible` verdict is held, and `micro_demotion`, `capital.resize` and
   `top_up_micro` stand down. Death, drift and replay stay. The pass:
   1. Reads each followed family's pooled record once (`families.family_record`, through the pass's
      ledger position) and moves its state in the mechanism ledger (unproven, proven, swing; a
      family whose REAL record qualifies for the swing has its first entry audited in the
      background), then every agent's evidence: `W_paper`, `W_real` and `E` (`Evaluator.wealth`).
   2. Pays the performance fee on new realized real profit.
   3. Kills paper agents under `die_below`.
   4. Moves bands down: hysteresis (once the stay has `hysteresis_after_settled` independent real
      results), or a 35% real drawdown straight back to paper; and (R5, Sept 24, 2026) a probe whose
      family's pooled forward record is losing (`allocator.family_probe`: at or below zero after 6
      active blocks, the House's own breeding line) goes back to practice, on Alpaca only once it
      holds nothing the demotion path would sell (dust is booked; its working bids are cancelled
      first, as the path itself does; `_unflat`).
   5. Moves bands up, best E first, inside the envelope: a probe when the agent's family is not
      proven, a bunt when it is (a swinging family's newcomer at the family swing's stake), but no
      probe from a losing family nor from one held by a probe's demotion until the family's record
      since that demotion turns positive over 6 active blocks (`probe_gate`; each demotion its own hold). A known defect is audited before
      the bunt, and the first agent-level swing is audited.
   6. Sizes every real stake toward its target (a probe's, a bunt's or the family swing's, by the
      family's state), up to the envelope's headroom and down by free cash only.
   7. Publishes the board (`allocator-board.json`, `alloc.board` rows, `Allocator.board()` for
      the site; its `families` block, each family's `swing_clock` there since R3), and every five
      minutes at most a `family.record` row for each family whose record changed.
6. **Start due research passes** in the background, stuck agents first and then whoever has waited
   longest. The base interval is three hours, or one for an agent that cannot act at all, and 15
   minutes for both while the funded burst is in force (`turbo.json`). The legacy pacer also halves
   it while the day's Sail is underspent; the campaign never does. The agent's own record then
   scales it (`game.json` `research.pace`): a winner waits 0.1 of it, a loser on paper or above 8
   times, and an agent with no earned record 3 times, unless it is idle (Sept 23, 2026). The
   research gate may back off further. Research runs only for an agent with more than twice the
   minimum credits, and none at all from the moment a release is staged, because the restart would
   throw the pass away half-read. Eligibility is checked again when a queued worker actually starts.
   A passing candidate is adopted on rung 0 or on paper with no record; otherwise it becomes a
   fork. A failed candidate that at least trades can replace an empty paper strategy after ten
   barren wakes. A later failed replay does not discard an earlier passing candidate. Research
   that finishes after retirement or a code change is recorded without changing that agent.
   **Entry controls (X1, Sept 24, 2026).** The researcher's `pause_entries`, `resume_entries` and
   `edit_params` only record a request (`agent.research`, tool `control`, status `requested`, id
   `control-request:<session>:<n>`); `edit_params` first has the House replay the edit
   (`_edit_replay`: numeric PARAMS `parameters.inspect` lists as mutable, inside their bounds, on a
   book of half the practice stake and caps, judged by the replay gate with this look and every
   earlier edit look of the line in the deflation, no `eval.trial`, never the holdout, one a day
   passed or not, read in full by `_edit_looks`; an `edit_replay` row).
   After any candidate and before the job is done, the pass's entry controls are applied
   (`_apply_controls`; a restart resumes an unfinished job and applies them): each an
   `agent.strategy` row restating the strategy in force with `control`
   (`pause_entries`, `resume_entries` or `edit_params`), `was`, the agent's `note` and the
   `reason` carried from the row before (so `hypotheses._mechanism` still reads the strategy's).
   A pause or resume row adopts nothing: `allocator.adopted_strategy` passes over it, so it moves
   no generation (an audit in flight, a promotion, a death and a waiting candidate's admission are
   keyed to it) and sets no audit verdict aside, and a buy decided before a pause is held at
   `_submit_wakes`. An edit is a new strategy: none is made while an audit of the agent runs or is
   owed, or while its latest audit is a veto (the generation moves, which drops an audit in flight,
   and `allocator.audit_standing` reads no verdict from before it), nor on rung 2 or above while an
   audit's approval of the strategy as it runs stands (nothing audits a seated swing again). What
   cannot be made is a `not_applied` status row saying why; ids make a restart's second look a
   no-op.
   Selected candidates are saved privately as soon as replay selects them, including candidates
   whose later fork is deferred or fails. That journal preserves work; it does not automatically
   retry admission or resume an interrupted provider conversation.
7. **Start Merton's due roles** in the background, and ask the gateway what CI made of each open
   pull request (a refused one is still asked, every 15 minutes, for 14 days). Step the repair
   engineer (`engineer.py`) beside them: new reports, admissions, free follow-ups, and at most one
   paid patch, paced and inside the frontier tier that still pays for code.
   Then the **hypothesis foundry** (`hypotheses.py`). On every tick it labels new
   births, and every ten minutes it retires exhausted families. It makes at most one paid call per
   `call_minutes` (10), and only when all of the following hold:
   - the House is neither paused nor staging a release;
   - a seat is open on an eligible desk;
   - the frontier tier still pays for code work;
   - the day's OpenAI allowance and the foundry's own window budget ($40 per 24 hours) have room;
   - no replay-passing card is already waiting for a seat;
   - fewer than `max_pending_cards` (8) of its cards await replay. With 0, any pending card or
     running card replay holds the call, as before Sept 23, 2026;
   - its own previous call has finished. Since Sept 23, 2026 other Merton passes no longer hold
     it up, though a running foundry call still holds the scheduled roles back, because those run
     one at a time.

   The call's cards are replayed one after another in the replay lane. A card whose replay box
   does not answer stays pending, and the rest of that batch is not charged an attempt.

   Then the **Alpha Lab** (`lab.py`, Sept 23, 2026), where `config.json` names a lab box: when the
   House is open for business and the lab is open (whatever the OpenAI tier: below `all` only its
   Luna and Sol calls stop, since C2 on Sept 23, 2026), the tick schedules one step on the replay
   lane (`replay:lab:step`), runs the lab's own watch (closed for half an hour, a graduate waiting
   six hours for a seat: one warning each) and does no lab work itself. A step seeds, breeds,
   evaluates batches on the lab box for up to `step_seconds` (240), graduates, once an hour replays
   its elites and waiting graduates on their forward windows (S2, Sept 23, 2026), pays royalties and
   writes `lab.stats`. Each of those phases runs on its own: one that fails is told with its traceback
   and the rest still run, and five failed steps in a row raise one error alert (D1, Sept 24, 2026).
8. **Once an epoch:** load new and changed lessons from `playbook/`, resize rung-3 stakes, raise a
   rung-2 stake to the current micro stake where the capital envelope has room, write the capital
   recommendation, pay the pool, score the auditor's vetoes.
9. **Keep the population:** kill agents at zero credits, rung-0 agents past the replay deadline, and
   agents stuck barren with too little left to research their way out (the culling runs even when
   the Sail meter has stopped the floor; only the refill waits for business); fork agents above the
   fork threshold (rung 1 and up, once an epoch); re-found any seed never born if the population is
   under its floor; enroll merged strategies, at most three a tick and corrected children first
   (since Sept 23, 2026 a full league makes room for each, and a born corrected child retires the
   agents off real money still running the code it corrects); and fill the last seat. Research
   candidates that passed replay go first. With the foundry on, the next is a replay-passing
   hypothesis card, taken from the desk with the best evidence first. After that comes a mutation of
   a parent that is earning forward and whose family is not retired, capped at a share of the day's
   births. Otherwise nobody is added: a desk's emptiness no longer breeds anything. When the league
   is full, a newcomer displaces the worst agent that has had a fair chance, which is never one on
   real money, never a profitable one, and never one that has traded while an idle one remains.
   Paper equity and option agents begin their grace period at their first offered trading
   opportunity, so a weekend birth does not exhaust the grace before the market opens. Since
   Sept 23, 2026 that grace is counted in regular-session time (`house.session_time`); one that is
   trading, hourly or daily, keeps its seat until it has closed the allocator's `bunt_min_trades`
   or had `displace_trading_after_sessions` (game.json, 3) sessions; one holding a stock or
   contract while the market is shut is not removed before the open; and a rewrite of one that
   has never traded does not restart its clock.
   **The seat market follows evidence** (Sept 23, 2026, the learn-and-unblock run; measured on the
   16:28Z snapshot: 312 of 345 deaths were displacements, 254 of them of rung-0 House mutations
   after a median three hours, while 20 lab graduates, 6 replay-passed cards and 6 merged
   strategies waited). `House.seat_waiters` lists who waits, by class in `SEAT_WAITERS` order:
   Alpha Lab graduates (replay and sealed holdout passed), replay-passed foundry cards, merged
   strategies. While any of them waits `_refill` stakes no mutation; a waiting graduate's desk is
   held from cards and merged strategies, a waiting card's from merged strategies
   (`_reserved_desks`). Each of the three asks `_weakest(..., evidenced=True)`: a newcomer with
   forward evidence may take a rung-0 seat, or a rung-1 seat that has never traded since its
   current program's opportunity, inside its holder's grace -- once that seat has had its fair
   chance (`_fair_chance`, Sept 24, 2026: its desk's evidence clock capped at the plain grace, never
   under an hour; after Deploy B evidenced waiters took each other's seats 33 s to 14 min after
   birth) -- (a desk that keeps hours only once its
   first regular session has closed, #190), and never a trader short of its record on any desk,
   a winner, real money or a position held through a shut market. Replay-only code ranks before
   code that passed replay, and at most one resident a desk is displaced in a tick. A waiter class
   that cannot be born is recorded (`seat_refusals` in house.json, `seats.last_refused_birth` in
   health.json) and told as a warning once an hour a class; more than
   `economy.seat_waiters_warning` (8) newcomers waiting for over an hour is a warning too
   (`_seat_market_watch`, hourly, also `seats.displaceable` and `seats.never_traded_past_grace`).
   Every desk keeps one seat for a member that trades (`_mutation_room`: a rung-0 mutation never
   takes a desk's last free seat while no member has a fill since its seat, and never displaces a
   desk's last trading member), because two crypto desks had no trading member for 34 of 48 hours
   while "full" of replay-only children. And no House mutation, parameter fork or revival of a
   family whose pooled forward record (`family_forward`: every member's active `eval.block`, living
   or dead) is negative after `economy.losing_family_min_blocks` (6) active blocks is made
   (`_losing_family`, an info alert once an hour a family); a child with different code -- a
   research candidate's fork, a card, a graduate -- is judged on its own.
   **Evidence is measured before a seat is lost** (S1-S4 and L1 of the close-the-gaps run, Sept 24,
   2026; measured on the T0 snapshot: 103 deaths in 24 h, median life 14.3 h, 70 before three fills,
   traders with 38, 26 and 24 fills displaced, and mullins-14's replay-passed candidate cancelled with
   it). Each desk's **evidence clock** -- the Kaplan-Meier median hours from a member's first own fill
   to its third independent settlement over the last `EVIDENCE_CLOCK_DAYS` (7), the scoreboard's
   definition (`measure_evidence_clocks`, events counted as the allocator counts them; the House's
   closing sales at a death are the House's, never a member's settlement) -- is measured
   at startup and daily (`evidence_clocks`, house.json `evidence_clocks`, an info alert when it
   changes); a paper seat's grace is the larger of the plain grace and its desk's clock, the clock in
   wall-clock hours (a desk that keeps hours still needs its twelve session hours), and a clock the
   median never reached leaves the plain grace. `_displaceable` takes a `Newcomer` (family, venue,
   forward score): a resident with `FORWARD_RULE_FILLS` (3) fills since its program's opportunity
   goes only to a newcomer whose forward score beats the resident's own forward record
   (`Lab.resident_forward`; none of its own yet, and it stays -- unless the lab can never score it,
   `Lab.can_score`: an options or unreplayed desk, a blocked program, where the plain tournament
   judges it as before); a proven family's resident
   (`Allocator.family`) goes to no unproven newcomer unless it never traded and its grace has run;
   never-traded residents past their grace go first, then a losing family's members. The lab's
   graduates (`Lab._newcomer`), merged strategies and research candidates (as their parent's family)
   ask as themselves; the House's mutation refill and the foundry's card pass ask as nobody in
   particular (no proof, no forward score). A dead author's retained candidate is evidenced, a living
   author's is not (a new paper seat keeps its grace against it, as before). `_trading_pending` reads the bunt line's settled route on an event book.
   **Retained candidates** (S3): `kill` hands a dying resident's latest replay-passed research
   candidate to the seat queue (`_hand_off_retained`: its admission goes `orphaned`, a `retained`
   waiter in house.json), and the admission pass of `_refill` adopts, once an author, the candidates
   cancelled with authors that died within `RETAINED_TTL_SECONDS` (72 h) before this rule
   (`_adopt_orphans`); `_admit_orphan` seats them first, a proven family's before the rest, then the longest wait -- House-staked, born on the author's line with
   the author as parent, seated on paper, a `retained` birth route -- dropping one that cannot be born,
   that a living agent already runs, or that is past the 72 hours. `SEAT_WAITERS` ranks them with the
   graduates. **Seats holding none** (S4): the hourly watch lists the residents off real money with no
   ranked forward score, no fill since their program's opportunity and no grace left
   (`_seats_holding_none`, `seats.seats_holding_none`).
   **The seat market's capacity** (R2 and R3 of the close-the-gaps run, Sept 24, 2026; measured on the
   15:06Z snapshot: 82 newcomers waited -- 41 graduates, the longest 24.5 h since passing; 15 cards,
   47.3 h; 11 retained candidates; 15 merged strategies -- in a league of 112 of 112, 50 of them over
   two hours; 20 waited for kalshi-crypto-15m, which the search had closed). A waiter the search has
   closed leaves the queue (`_expire_waiters`, from `seat_waiters`): its desk is closed by the
   foundry's rule (`Foundry._closed_desks`, E2: `hypotheses.closed_desks` until a family there is
   positive over `closed_reopen_blocks` active blocks on that desk) or the lab's idle rule
   (`Lab._idle_desk`, E1), both read through `_search_closed_desks` every ten minutes, or -- a lab
   graduate -- its own forward window loses (`Lab.forward_score`). It leaves with its reason: a
   `route.decision` row `seat-expired:<class>:<id>` (once), house.json `seat_expired` (a week), an info
   alert at most once an hour a desk; it is asked again each pass and is a waiter again once its reason
   is gone (its desk reopened, its window no longer loses: the review of #276). An expired retained
   candidate is held, never seated, until its desk reopens or its 72-hour TTL drops it, an expired
   merged strategy is not enrolled (one whose defect a living resident still runs is never expired: it
   takes that resident's seat), no card is admitted onto a closed desk (`_refill` passes the closed
   desks to the foundry as reserved), and an evidenced newcomer is given no seat on a desk the search
   closes (`_displaceable`). While the foundry closes a desk the House holds its cap at its members
   (`_follow_the_search`, read in each tick before the foundry's and the lab's steps, so the first tick
   after a restart never shows them niches.json's cap); it gets its niches.json cap back when it reopens. Graduates wait from the
   ledger's `lab.graduate:<id>:passed` row, cards from their passing evaluation, merged strategies
   from when the House first saw them (their desk read from their literal NEEDS). **S3, a stale seat**
   (`_stale_seat`): a newcomer with a winning forward window takes the seat of a practice resident
   whose desk evidence clock has run (its seat older than the clock -- the plain grace where none is
   measured -- and its fair chance; on a desk that keeps hours, a session closed since) with no
   positive record of its own (no winning standing, no positive forward window), past the S1 forward
   rule and the trading and screen protections; never inside its clock or fair chance, never real
   money, a winner, a proven family's member by an unproven newcomer or a position held through a
   shut market; one a desk a tick. **Capacity follows the waiters**: niches.json's caps follow the
   44 that remained at 15:06Z (see its note), and the league grows toward turbo.json
   `max_population` (128) only while Sail's runway -- the Sail meter's latest balance less
   `sail_reserve_usd` over the trailing day's falls (`_sail_runway`) -- is over
   `economy.population_runway_days` (1.5); otherwise, or unread (a meter that cannot be read too), it is
   held at `economy.max_population_short_runway` (112), killing nobody (`_population_rule`, which sets the
   league's `max_population` that the lab, the foundry and the House all read). Once held it grows again
   only over the floor by `POPULATION_RUNWAY_BAND_DAYS` (a quarter day, house.json `population_held`):
   the runway moves 2.6% a reading at the 90th percentile and rose with no top-up in half the readings,
   so at the floor it flipped with the readings and the league crept up (the review of #276). **The invariant**: a
   newcomer waiting over `SEAT_WAIT_WARN_SECONDS` (two hours) is named once an hour a desk with the
   count, the longest wait and the rule that holds it (`_overdue`, `_held_by`: a free seat the birth
   passes have not reached, or the residents' protections counted by `_displaceable`'s `why`);
   health.json `seats` carries `longest_wait`, `over_two_hours`, `expired`, `caps` and `population`,
   and the watch prints them. **R3, births into the proven family** (`_proven_births`, first in
   `_births`; `SEAT_WAITERS` class `proven`, ahead of every other): a proven family's program -- its
   anchor's code beyond PARAMS (`lab.mechanism_digest`; the anchor is the living member on the
   highest rung with fills of its own that runs the markets and style of the family's founding
   program, `_family_program`) -- is bred by the path the House already uses for a program
   (a House-staked mutation of the anchor's PARAMS inside their bounds, `_mutated_params`, on its line,
   code and family), one birth a tick at the newcomer cadence a family, until
   `economy.proven_family_members` (4) living members run it; the child is replayed like any
   mutation and reaches real money through the bunt line on its own record. While births are owed no
   newcomer of another family may displace a resident of its desk, and the desk is reserved from cards
   (and, in a full league, from merged strategies); a free seat there is not held (the lab seats a
   graduate, the admission pass a retained candidate and `enroll` a merged strategy into a free seat
   without asking).
   No birth for a family at its measured capacity (E3) or a losing one, nor for an hour for one whose
   program has no distinct valid PARAMS mutation left (`PROVEN_UNBRED_RETRY_SECONDS`: nothing is owed,
   so its desk is not held from other families meanwhile). A member that inherited the
   family's name with other code is not its program (meriwether-h2d625d-2). **A new program, a new
   family** (Sept 24, 2026): a research fork (`fork` with code) or a retained candidate
   (`_admit_orphan`) whose NEEDS name other markets (venue, series, symbols) or another style than its
   parent's program now is born into a family of its own (`_program_family`: `<desk>-<style>-<6 hex>`,
   rooted in the parent's family; the parent stays on its birth row), so a different mechanism never
   inherits a family's proof; a fix of the same program (the same markets and style) keeps the family,
   whose record already splits maker and taker -- and a PROVEN family only when that program is the
   family's founding one (`_family_program`: its first member's NEEDS at birth), so a member that
   carries the name with another program (meriwether-h2d625d-2) cannot pass the proof to its forks
   (the review of #276). On the 15:06Z snapshot 98 children had been born into
   their parent's family with other code beyond PARAMS (39 living); 71 (28 living) named other markets
   or another style and would have had their own. Agents already born keep their ledger's family.
   **Corrected children supersede** (L1, gated by
   the constitution's `allocator.corrected_child_supersedes`): `_supersede_by_research`, beside
   `_retire_superseded` in `enroll`, retires a living parent whose research child passed replay and
   whose own account of its program names the parent's entry as the defect (`entry_defect`:
   liquidity, fee or side, each a claimed defect; "the opposite side" is none), when that account is
   of the parent's CURRENT program (`_program_account`: the child's rewrite of a copy of the parent's
   code, or the parent's research candidate made while it ran that code -- never the child's fix of
   its own earlier file, which is how meriwether-h2d625d-2's maker rewrite read at T0), borne out by the
   programs (`_entry_fills`: a taker parent, and `posts_maker_entries`: a child whose entries rest
   post-only, for a liquidity or fee defect), and never a parent whose family's pooled TAKER record is
   proven positive (`_taker_proven`: `Allocator.family_taker`, the record the real book's X0 rule reads to
   let the family take; the skip is told once, `supersede_skipped`) -- demoted from real money through the evaluator first; the child
   enters real money on its own evidence. A pair it found nothing in is looked at again hourly.
   **Dust and refused wind-downs** (Sept 24, 2026): a holding the venue will not trade (worth under a
   cent even at the ask -- one under a cent at its mark, the last bid, is quoted again -- or under the
   venue's minimal order quantity where its asset record states one)
   is booked as dust (`_book_dust`: off the account, onto the House row, as `Book._position_dust`
   books a reconciliation's crumbs, both rows one ledger group) instead of sent, and the same refusal of a House-sent sale
   `WIND_DOWN_REFUSALS` (3) times in a row stops its retries with one warning naming the order
   (`wind_down_refusals` in house.json), until the holding changes or a day has passed
   (`WIND_DOWN_RETRY_SECONDS`).
   Since Sept 23, 2026 every birth of this step (forks, founders, merged strategies, the refill)
   holds the probe box for the whole step, where each birth reads its NEEDS. When background work
   has that box, the step waits at most `probe_wait_seconds` (15 s) and the births are deferred to
   the next tick (`deferred` `births`); a Sail failure among them is deferred the same way. The
   culling above them still runs.
10. **Save `house.json`, publish, write `health.json`.** A publishing failure is a warning: the site
    is downstream of the floor, never upstream. `health.json` `deferred` lists what the ticks of the
    last hour put off because a box was busy or Sail did not answer, and `tick_steps` (Sept 24,
    2026) what each step of the last tick took, on the monotonic clock (`_TickLaps`: every moment of
    the tick belongs to one step, from `replay_rules` to the health block itself), each step's
    slowest in the last hour, and each background lane's last run. A new step of `_tick` gets a
    `lap("its name")` after it, or its time goes to the next step's name.

The book's side of the order path, since Sept 23, 2026 (workstream B, from the study of the
ledger): an order the venue never acknowledged (`new`, `unknown`) is closed as "the venue has no
such order" only once the venue has said so on two polls at least `NEVER_ARRIVED_SECONDS` (60 s)
apart -- one answer is remembered, not believed -- and for `NEVER_ARRIVED_RECHECK_SECONDS` (15 min)
after that verdict the poll keeps asking; an order the venue has after all is revived on the record
(a `found` row) and its fills booked, so a fill can no longer be stranded as a position diff.
(Measured: 153 alpaca-paper orders closed that way on one look by Sept 23, 149 of them the venue's
own 403 refusals an older adapter read as unknown, 4 lost in a gateway outage; none had filled.) A
venue answer that closes an order without a fill carries the venue's reason on the `book.order` row
(148 kalshi-shadow rejections had an empty one: every one "post-only order would cross"). The market
slices of a sliced exit wait while the market is shut instead of being refused slice by slice, and
the plan's time-to-live counts again from the open. And a book that has never traded re-reads its
baseline only while no position differs: a cash diff beside a position diff is a fill the book does
not know yet, and taking its cash into the baseline left the book a fill's worth off for good.

## The strategy contract

[`CONTRACT.md`](CONTRACT.md): the file's shape (`NEEDS`, `PARAMS`, `decide(ctx)`), the allowed
imports, everything in `ctx`, what `decide` returns, and how replay scores it. The same file runs
in replay, on paper and with real money. It is handed to the researcher model and to Merton as
architect and toolsmith, so a change to it changes what they write.

## State on disk

Everything the House keeps is under one directory, `--root` (default `.data/league`; on the box,
`/workspace/state`).

| Path | What it holds |
|---|---|
| `ledger.sqlite` | The ledger. The only record that matters; everything else can be rebuilt or lost. |
| `house.json` | The House's working memory: each agent's next wake, `memory`, last research, the code hash that has had its replay, last marks, last settlement stamp. Mode 0600. |
| `sandbox.json` | Which Sailbox belongs to which agent. |
| `kalshi-shadow.json` | The Kalshi shadow account: cash, positions, orders, fills, settlements applied. |
| `provider.sqlite` | The metered record of cheap-model calls (the first run's `Provider`). Absent with `--no-research`. |
| `publish.json` | The publisher's cursor into the ledger and its last mark time. |
| `health.json` | Rewritten every tick: living, dead, frozen books, open orders, `ledger_seq`, `real_money`, release, tick duration, and queued/running background jobs with elapsed times. The watchdog reads it. |
| `allocator.json`, `allocator-board.json` | The allocator's state (the throttle, the performance fee's cursor; since Sept 24, 2026 each family's state and since in the mechanism ledger, a swing's entry, the family swing's audits and the digest of each family's last `family.record` row) and its board, rewritten every mark pass: each agent's band, stake and evidence, the last 50 moves, bands per venue, the throttle and the envelope (Sept 23, 2026), and since Deploy B each row's family state, capacity and stake limit and the board's `families` block. A lost `allocator.json` restores the family states from the ledger's last `family.record` rows; a swing's audit approval is not in them, so a family restored in the swing keeps swinging and one restored below it is audited again at its next entry. |
| `day_open.<book>.json` | Each account's opening equity for the UTC day on that book, with the ledger's head when it was taken (Sept 23, 2026): what both daily-loss lines read. Written when an opening is taken, never when a stake adjusts one; a restart restores today's and replays that day's later `book.stake` rows from the ledger. Marks live in memory only, so before a restored account is first compared after a restart its unmarked holdings are quoted once (review of #211): valued at cost until the first mark pass, a winner read as the day's loss and a loser's loss was hidden. Another day's file is ignored; a lost or unreadable file is the old behaviour, a fresh opening at the next check. |
| `shards.json` | The Kalshi shard funder's state (Sept 23, 2026): the `book.order` cursor of its refusal scan, the last check, the learned series-to-shard map, the last balances per shard, the wanted shards, the shards a blocked pass still owes a refusal (`pending`), the shards backing off after a failed move or a top-up on a refusal's word, and the rolling day's moved total. A lost file re-reads the balances and re-learns the map at the next pass; the day's cap is counted from the ledger, not from here. |
| `lab.sqlite` | The Alpha Lab's archive: `candidates`, `archive` (one elite a cell), `batches`, `calls`, `graduations` and `meta` (Sept 23, 2026). A lost file means an empty archive, searched again from the seeds; the ledger keeps the `lab.*` rows. |
| `STOP` | If present, the `run` loop ends after the tick in hand. `python3 -m league stop` writes it, `start` removes it. |
| `jev.sqlite` | The Jev sensor's cached answers and every call's intent, status, cost and latency (what the daily caps are checked against). |
| `research-gate.json`, `triage.json`, `hypothesis-memory.json` | The research gate's per-agent baselines, streaks and skip episodes, plus current inactivity reasons; triage's cursor, groups, aliases and pending questions; the mechanism index. The gate re-baselines from the ledger if its file is lost. Links are idempotent by pair. A lost `triage.json` makes triage re-report history under the same keys. |
| `cache/` | Kalshi history and news, a byte-capped disk cache. |
| `boxes/`, `alpaca-sim.json` | Only with `--local-sandbox` (one private directory per agent) and `--canary` (the simulated Alpaca account). |

## Tests

```sh
python3 -m unittest discover -s league/tests -t .        # the complete league suite
python3 -m unittest league.tests.test_book               # one module
python3 -m league.ci --no-tests                          # the content checks alone
```

No test touches a network, a venue or Sail: `league/tests/fakes.py` has a fake broker that behaves
as Alpaca's paper venue was measured to, and a clock. One test is slow on purpose:
`test_ladder.py` (about 40 s) runs a whole House through paper, the audit, micro-real, scaled
sizing and decay back down, and is the only place every rule is seen working together. While
iterating, skip it by running the modules you touched.

`test_order_path.py` holds the regression tests of the Sept 23, 2026 study's order-path defects
(the fittings, the seat guard, the desk-fair drain, the invariants, "no such order" on two looks and
the revival, the venue's reason, slices held for the open); each failed before its fix.

`league/tests/fixtures/site_contract.md` is what the site accepts, with the two JSON fixtures the
site's own validators are tested against.

## The replay regression

`test_replay_regression.py` replays every founding seed over two deterministic canned tapes
(`ci.regression_tape`) and compares trades, fills, maker fills, refusals, errors, steps, blocks,
final equity and fees with `tests/fixtures/replay_regression.json`. A change to the simulator, the
fee model, the safety rules or a seed that moves any number fails here by name, so a change to the
arithmetic cannot pass as a refactor. To accept an intended change, re-record the fixture and
commit it with the change:

```sh
python3 -m league.tests.test_replay_regression --record
```

## What the league imports from `ltcm/`

The first run's runtime is kept as a library. These are the only modules the league imports
(`grep -rn "from ltcm" league/ --include=*.py`, tests aside):

| `ltcm` module | Used by | For |
|---|---|---|
| `ltcm.broker` | `book`, `fees`, `house`, `paper`, `sim`, `publish`, `venues` | `Instrument`, `OrderIntent`, `Order`, `Fill`, `Quote`, the `Broker` protocol and its errors, `money`, `instant` |
| `ltcm.risk` | `book` | `RiskEngine` and `RiskContext`: all 21 pre-trade rules, unchanged, and the event-cluster keys |
| `ltcm.sim` | `fees` | `FeeModel` (the Kalshi fee arithmetic) |
| `ltcm.adapters` | `venues`, `tapes`, `service` | `VenueClient`, `GatewaySigner`, the credential types |
| `ltcm.adapters.alpaca`, `ltcm.adapters.kalshi` | `venues`, `paper` | `AlpacaBroker`, `KalshiBroker`, Kalshi's price grid and contract helpers |
| `ltcm.data` | `venues` | `market_open_at` (the US equity calendar) |
| `ltcm.data.kalshi` | `paper`, `tapes`, `service` | `KalshiMarketData`, `parse_price_ranges`; `ltcm/data/kalshi_fees.json` is the list of series that charge makers |
| `ltcm.data.news` | `service` | `News`, the Google News RSS reader behind the search fallback |
| `ltcm.history` | `tapes`, `service` | `History`: settled Kalshi markets and candles, throttled and cached |
| `ltcm.provider` | `service` | `Provider`: the Sail Responses client with its rate card and cost records |
| `ltcm.sailbox` | `service` | `SailboxClient`: create, fork, exec, egress, checkpoints |
| `ltcm.performance` | `publish` | `AccountPerformance`: the funding-flow reader behind the profit figure |

Those modules in turn import `ltcm.events`, `ltcm.manifest`, `ltcm.data.yahoo` and
`ltcm.data.coinbase`. `scripts/floor_box.py` also uses `ltcm.sailbox`. Nothing else in `ltcm/` is
imported or run; see [`ltcm/README.md`](../ltcm/README.md).
