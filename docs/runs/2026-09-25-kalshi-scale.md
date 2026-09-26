# Kalshi at scale — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the Kalshi-scale plan](../goals/LTCM_KALSHI_SCALE.md) autonomously, with no deadline, beside the
forward-first run ([its record](2026-09-25-forward-first.md) on `run/forward-first-2026-09-25`) and the
options run ([its record](2026-09-25-options-desk.md) on `run/options-desk-2026-09-25`), until its Done
list holds.

## The clock

- **T0:** 2026-09-25T06:05:01Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Windows:** Friday's US session 13:30-20:00Z has no deploy (13:25-20:05Z). The weekend has no stock or
  options session; its deploy windows are the hours when no game a real Kalshi family holds is in play
  (Friday's MLB slate runs to about 03:00-05:00Z Saturday). Saturday 15:00Z is K1's acceptance line
  (founders seated on every league with a slate). The watch runs every 30 minutes from Saturday 15:00Z to
  Sunday 23:59Z; the report is at Monday Sept 28 13:00Z.
- **Progress notes:** a scoreboard reading and a short state note at Saturday's close, Sunday's close and
  Monday 13:00Z, and a line at every deploy.

## The owner's message (Sept 25, 2026, at T0)

- The /goal text is the plan's last section; the session received the "Method" line with words run
  together ("builders in workmoney code, verify on thebox in each window ... report at Monday 13:00Z
  wireport's numbers and mynext decisions"). **Read as** the plan's own copy: builders in worktrees,
  adversarial review of money code, verify on the box in each window, watch the weekend every 30
  minutes, fix bugs with tests, report at Monday 13:00Z with the scoreboard, the scale report's numbers
  and the owner's next decisions.
- **Authority:** the forward-first plan's "Authorized" list applied to this run's workstreams, plus this
  plan's money table (K5's new grant version, built and merged switched off, ratified only by the owner;
  `allocator.max_event_share` 0.25-0.35 for a PROVEN sports family). The owner's standing approval to add
  any data host that meets I2's rule to the box allowlist and `LEAGUE_HOSTS`, and to deploy the gateway's
  `web_fetch` route with its tests green. Nothing in "Not authorized": no deposits, no transfers, no cap
  raises, no test or forced trades, no network for a strategy box, no keyed or login host, no credential
  sent to a fetched host. No owner steps.

## The first hour's decisions

1. **The plan to main.** PR #301 (docs only: a release tree holds `league/`, `ltcm/`, `scripts/`,
   `playbooks/`, `deploy/`, so the updater ships nothing for it, as the forward-first run measured at
   04:44Z).
2. **The floor at T0 (06:03-06:10Z, read-only).** Release `20260925T040816Z-532b1cd9b20c` (H1's
   stop-then-deploy of #294 at 04:09Z); no book frozen; the Kalshi envelope $546.83 with $109.23
   committed (20%); throttle off (floor P&L +$10.75). Shards: 0 $346.52, 1 $0.00, 2 $68.08, 3 $76.98
   (floor $20, day cap $200, nothing moved in 24 h); football's game series sit on shard 0, MLB's on 3.
3. **Where the weekend's Kalshi money is (public API, 06:08Z).** College football: KXNCAAFGAME 240
   events listed ($2.27 M traded in 24 h), KXNCAAFSPREAD 113 events ($1.31 M), KXNCAAFTOTAL 114
   ($0.74 M), median spread 2-3 cents. NFL: KXNFLGAME 31 events ($1.20 M), KXNFLSPREAD and
   KXNFLTOTAL 16 each ($0.57 M, $0.32 M), spreads 1 cent. MLB: KXMLBGAME 43 events ($0.24 M),
   KXMLBTOTAL 13 ($0.07 M), KXMLBSPREAD 13 ($0.01 M).
4. **What the odds recorder holds (feeds.sqlite, 06:07Z).** `odds` has recorded since 08:35Z Sept 24, a
   league every 30 minutes, games starting within 36 hours, at most 16 a league; ONE provider (Draft
   Kings) per game, de-vigged, with ESPN's predictor for football. Two gaps for K1: ESPN's default
   college-football scoreboard is its featured board (18 games recorded for this weekend, against
   Kalshi's 113 spread events), and the 16-game cap cuts Saturday's slate further. The soccer boards
   were last stored Sept 23 (to check).
5. **How a founder gets a seat.** `House.found()` seats a niche's founder rows at rung 1 without a
   replay, but it runs only below `min_population` or from the CLI (a second House on the ledger: not an
   option). The league sits at its 128 ceiling. K1 needs a House hook that seats this run's founder rows
   into a full league through `_displaceable`, as the options run's `options_desk.seat_founders` does for
   its desk; a founder reading the live `odds` feed on a day-horizon desk could not be replayed for 20
   days, so practice is its test and the record says so.
6. **Deploy windows.** Forward-first's Deploy A is 08:00-09:30Z today and its Deploy B moved to
   Saturday's quiet window (about 05:00-15:00Z); the options run's Deploy V is 10:00-12:25Z today and
   its Deploy G follows B. This run's first House deploy (K1) therefore goes in Friday's gap after the
   session: from 20:10Z until the first pitch of an MLB game the proven family holds (about 22:00Z;
   CHC-BOS game 2 starts 22:05Z), its exact start written below first.

## Coordination with the other two runs

This run follows the options plan's "Coordination" section across three runs, as all three records now
say: before each merge and deploy it reads the other two records (current waves, file owners, announced
deploys); it edits no file another run's current wave owns; one deploy at a time across the three, none
13:25-20:05Z on a trading day, none while a real Kalshi family's game is in play (except a rollback), never
inside another release's canary or watch, never within 30 minutes of another run's announced deploy; after
any promotion that leaves the grant inactive it ratifies `earned-live-20260921` only if every changed money
rule is a row of one of the three plans' tables, else rolls back and records why. Whichever run deploys the
gateway second rebases on the first and re-runs the gateway tests. Messages to another run are lines here
plus a comment on its open PR.

**A fourth run (the owner's message, about 06:30Z):** `docs/goals/LTCM_JEV_SENSES.md` (branch
`goal/jev-2026-09-25`). It owns only the Jev files (`league/jev.py`, `sensors.py`, `triage.py`,
`hypothesis_memory.py`, `exposure.py`, `semantic_lab.py`, `jev_features.py`, `scripts/jev_lab_eval/`,
`gateway/lib/typesafe.mjs`, `config.json`'s `jev` block) and lands small hooks into `research_gate.py`,
`feeds.py` and `lab.py` only after the waves that own those files merge; it changes no money rule. From
now on: one deploy at a time across FOUR runs, and any gateway deploy rebases on the other runs' gateway
changes (the options run's multi-leg route, the Jev run's `typesafe.mjs`) and re-runs every gateway test.
This run's `feeds.py` changes merge with Deploy K1; the Jev run's hook follows them.

**This run's current wave, file owners and deploys (kept current):**

| Wave | State | Files owned |
|---|---|---|
| 1 (Deploy K1, Friday after 20:05Z) | building | K1: `league/feeds.py` (the `odds` and `sports` recorders), `ltcm/data/sports.py`, a new model-versus-market seed `league/seeds/sports_consensus.py` with one `SEEDS` row appended at the END of `league/seeds/__init__.py`, the `kalshi-sports` row of `league/niches.json` (founder rows), K3: a new seed `league/seeds/weather_ensemble.py` (its `SEEDS` rows at the end too) and the `kalshi-weather` row of `league/niches.json`, a new `league/kalshi_founders.py` and ONE call line in `house.py`'s births pass right after the options run's `options_desk.seat_founders(self)`; K2/K3/K4: new read-only scripts (`scripts/kalshi_capacity.py`, `scripts/kalshi_watch.py`); I1: `league/researcher.py` (the `web_fetch` tool beside `web_search`), `league/commons.py` (`web_fetch`; I3's `block` beside `fulfil`) and the gateway's `web_fetch` route (new `gateway/lib/fetch.mjs`, its line in the router, `gateway/test/`) |
| 2 (after forward-first's Deploy B) | K5 reviewed, merges after B; K5b after B | K5: `league/live_trading.py`, `league/grants.py`, `scripts/live_trading.py` (`--scale-report`), one `ci.FORBIDDEN` line; K5b: `Allocator.grant_capital` (one line), the board's envelope row, `House.tuition` (house.py ~3625-3646). **I2/I3 moved into wave 1 (Deploy K1)**: `league/open_feeds.py`, the registration and host backoff in `league/feeds.py`, `Commons.block`, new fetchers in `ltcm/data/`, `LEAGUE_HOSTS` |

- **Not touched by this run:** the allocator, the families' proof, the seat market's rules, the lab, the
  foundry brief, `book.py`, `constitution.py` (K5's grant version lives in `grants.py`), the options desk,
  the `alpaca-options` row.
- **Announced deploys:** **Deploy K1** (House; no money-digest change) Friday Sept 25 from about 21:05Z: after the
  forward-first run's Deploy A (moved by the usage-limit outage to 20:10Z, done about 20:35Z) plus 30 minutes, agreed
  10:36Z. It must START by 21:45Z: the proven family's open real positions begin at 22:40Z (PIT-DET, TB-PHI), then
  ATL-MIA 23:10Z, TEX-MIN 00:10Z, AZ-SD 01:40Z, LAD-SF 02:15Z; else it moves to Saturday after B, G and D-J1. **Exact start (written 19:59Z): 30 minutes after Deploy A's watch ends (A starts 20:10Z; expected ~21:05Z), no earlier than 21:00Z and no later than 21:45Z: the gateway's `web_fetch` route first (`npx wrangler deploy --tag <sha>` from `~/Work/ltcm-deploy/gateway` at origin/main), then the House (`python3 scripts/floor_box.py deploy`, loop running, watch on).** Deploy A's watch ended 20:21:56Z (release `20260925T201002Z-1fdb97fd591f`, grant on `d7d910fe`), so **Deploy K1 starts at 20:52Z** (written 20:23Z); #320 merged to main at 20:22:36Z (`adccc8ef`, CI green on `06514113`).
  A **gateway deploy** of `web_fetch` (no money rule) in the same Friday gap or Saturday's quiet window
  after forward-first's Deploy B and the options run's Deploy G, rebased on the options run's gateway
  change. **Saturday Sept 26's order (agreed 12:30Z, each after the previous watch + 30 min, none while a real Kalshi family's game is in play):** forward-first's B 06:00Z, the options run's G ~07:00Z, forward-first's C ~08:00Z, the Jev run's D-J2 + its J5 gateway ~09:00Z, then this run's K2 before ~15:30Z. Game times checked (Kalshi tickers, ESPN): Friday's last MLB first pitch 02:15Z (LAD-SF), Saturday's first 17:10Z, college kickoffs from 16:00Z (practice founders only), Sunday MLB 19:05-19:20Z, NFL 17:00Z. **Deploy K2** (House: K5, K5b and any fix the weekend watch finds; I2 moved into K1) in a weekend quiet window after
  B, G and D-J1, its start written here first.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | PR #301 |
| 0.3 | First-hour decisions | done 06:20Z (above) |
| 0.4 | The scoreboard at T0 | done (below) |
| K1a-review | Three-lens review of the sports seed, the recorders and the listing keys | **done** (10:57Z, `82785f0` on the PR; consensus 48, listing + replay regression 9, seeds + niches 170 OK; ci passed): fixed one game bought twice through two Kalshi codes (confirmed on the PR head; both now skipped as ambiguous), a doubleheader ticker without G1/G2 on a two-game day (skipped: MLB 66 of 69 now), bids out of view kept unchecked (now re-priced from their own ticker or cancelled; all cancelled with a feed absent), cancels over the runner's 20 dropped (soonest start first), memory past 8 KB (40 bids at most), a taker refusal forgotten after 12 outcomes (24 h memory), a `fee_multiplier` mutation halving football fees (never under the series' own), taker sizing ignoring its fee, a snapshot without a rung (held to the 30¢ floor), `min_price` floor 0.05 → 0.15, crashes on odd values, and live/replay disagreeing on a bad listing floor (`replay.py`, two lines). Left: the Normal ladder model unmeasured; far games' 2 h refresh vs 90 min stale (bids re-placed, queue lost, no money) |
| K1a | Recorder coverage (the full college slate, per-game odds cadence, soccer draw prices) + the model-versus-market seed `sports-consensus` + founder rows (NFL, NCAAF, MLB) | built, PR #312 (33 new tests; feeds 37, recorders 40, ltcm 1859, seeds/replay/seat caps 134, niches 39 OK; ci passed): college board = ESPN's FBS + FCS week boards (71 + 65 games, all 346 NCAAF events Kalshi lists Sept 25-28); daily leagues add dated boards for today and the next 36 h; odds per game every 30 min inside 6 h, 2 h before, ≤ 20 games a 5-minute pass; draw, total and spread prices parsed (ESPN answers Draft Kings only); matched NFL 45/45, NCAAF 346/346, MLB 67/69 (2 rescheduled), MLS 15/15, Liga MX 9/9; winners 1.2¢, ladders 3¢, key numbers 3 and 7 skipped, MLB spreads only at the book's run line; founders NCAAF 10, MLB 20, NFL 30, MLS 60, Liga MX 70; sports desk 19 → 24. **Fixed (10:34Z):** a wake showed at most 200 markets soonest to close, so games in progress blinded a pre-game founder on game day; opt-in NEEDS `min_hours_to_close` and `max_markets` (≤ 500) in `tapes.py`, the Kalshi wake in `house.py`, `replay.py` (protected: owner deploy) and `niches.py`; founders NFL/NCAAF 3.0 h / 500, MLB 3.0 / 300, soccer 0.5 / 200 (markets expire 3.00 h after the start on 306 of 346 NCAAF events). Pre-game games a founder can enter: NCAAF at 17:00Z Saturday 38 of 89 (was 0), NFL at 18:00Z Sunday 5 of 5 (was 0); a college wake carries ~305 KB (500 markets 144 KB, board 78 KB, odds 84 KB). Tests: listing window + tapes 80, consensus + replay regression 35, open desks + niches 63, shards 39 OK |
| K1b | `league/kalshi_founders.py`: flagged founder rows seated into the full league | built 07:05Z, PR #308; **reviewed** (three lenses, 10:43Z, `bb047a8` on the PR; founders 32 + seat market 235 tests OK): own-desk displacement removed (a founder takes only a free seat of its own desk), the league-wide path asks without evidence, `seat_priority` order, the desk record cached hourly and counted by each block's own time (3 ms refresh on a 166,600-row ledger); fixed: `found()` called Sail under `_lifecycle_lock` (now `found(..., described=)` with the probe read before the lock), protections on both paths, a doubled postmortem, same-tick churn on the yielding desk, per-kind alert rate limits, malformed rows warned. Left: `lab.py` `_floor_score` scores a `desk_closed` graduate's death −1 (protected, forward-first's F1: asked); a crash between birth and retirement leaves the league one over until a natural death |
| K2 | `scripts/kalshi_capacity.py`: fill curves at 1x-8x from own orders, Kalshi's public prints and books | built (`k2/capacity` `1d8a1fb`, 12 tests OK, ci passed; first table below); ships with K1 |
| K3 | Ensemble-priced weather founders (`weather_ensemble` seed, every station's high and low) | built, PR #310 (27 tests; 223 seed/niche/replay/parameter tests OK; ci passed): four regional founders (west 40, east 50, texas 60, central 70; one family each), weather desk 17 → 21 seats, five missing low series added (all 20 stations' highs and lows), rain left out; fair from the 82 members with a per-station bias measured on Kalshi's settlements Aug 1-Sep 24, widened, smoothed, the NWS blended in, shrunk halfway to the mid; makers at 5¢ (brackets) / 8¢ (thresholds) after the fee, takers only above 20¢; highs until 06:00 LST on the day, lows until 23:00 the evening before. **The builder's own test: a stand-in of this pricing scored worse than Kalshi's mid (Brier 0.161 vs 0.134 highs, 0.149 vs 0.121 lows); its takers lost on lows; maker bids on favourites earned ~3¢ a contract with or without the model.** **Reviewed** (three lenses, 10:33Z, six fixes: a malformed feed row crashed the whole wake, bids out of view were not cancelled, a threshold whose title and brackets disagree is now skipped, the lows' cutoff bound tightened, side matching, no climate day on or before the bias table's end ever priced) and the lows corrected −1.7 F (the members' day-ahead warm bias); `2100c7f` on the PR; 33 weather + 170 seed/niche tests OK |
| K5 | The scale rule, switched off, and `--scale-report` | built, PR #313 (`65d5b99`; scale rule 33, live_trading 19, grants 7 OK; ci passed); version 2 of the grant in a new `live_grant_versions` table, on only by the owner's `python scripts/live_trading.py --ratify earned-live-20260921 --grant-version 2`; version 1 byte-for-byte and its digest `4c8e2607…` pinned; capacity used = proven families' `members_real × stake × m*` (m* the largest multiple before fills halve, from K2's JSON or the board); unlock at ≥ 70% on 3 complete UTC days AND the venue's real P&L above zero over them; tranche min(deposit left, 0.5 × envelope); relock below −0.30 × the tranche. On the T0 board: capacity used $30 = 5.5% (with K2's curve $240 = 43.9%): no tranche. **Gap:** one line in `Allocator.grant_capital` (forward-first's file) reads the unlocked tranches; asked 07:22Z; **agreed 07:24Z:** this run adds it in a small PR after Deploy B merges, reviewed by the forward-first run, shipped by an owner deploy, with tests that (a) version 2 unratified leaves the envelope, the money digest and `PINNED_DIGEST` byte-for-byte unchanged, (b) `scale_state` failing adds 0, never a guess, (c) the envelope stays capped by the grant's `max_loss_usd` / venue capital as ratified, a tranche exactly what the owner's version-2 ratify pinned. **Reviewed** (three lenses, 10:53Z, `8be2465` on the PR; scale rule 46, live_trading 19, grants 7 OK): fixed a re-ratification that erased withdrawals (a tranche withdrawn at 03:00Z came back when the owner re-ratified at 06:00Z; earlier version-2 periods now replay first under their own rule), the report deciding from K2's study although the ratified rule reads the family records (K2 now a labelled what-if), a day with no mark pass counted as $0 (now unmeasured, failing the profit condition), a half-written mark pass read as P&L, the version-1 pin compared against a copy (now main's own file by its git blob `03973f92…`), `league/grants.py` unprotected (now in `ci.FORBIDDEN`), ratify writing before the version-2 policy was built; added `scale_unlocked(root, venue)` for K5b (exact unlocked tranches, $0 unratified without reading the ledger, $0 on failure). Left for the owner: complete days only at the ratification moment, one allocator reading suffices for a day, the relock line at the tranche's full size after an equity cap. Merges after Deploy B |
| I1 | `web_fetch` for research through the gateway | built 06:40Z, PR #305 (gateway 174 tests pass, researcher 64 OK, commons+fast_research 37 OK, ci passed): `POST /v1/web/fetch`, SSRF rules on every hop, 2 MiB read / 200k text, 3,000 a day; House tool 20 a day an agent at $0.01, rows `agent.research` tool `web_page`. **Reviewed** (three lenses, 07:14Z, `4249601` fast-forwarded onto the PR): six defects fixed with tests: a super-linear HTML reader (32 KB of `<a<a<a` took 22.7 s in the isolate that serves the order routes; now one linear pass, 2 MiB in ~20 ms), no concurrency bound (now 4 pages an isolate, 429 `busy`), a page that crashed the Worker was free forever (now charged when the Worker read it), a forgeable quote marker (now a random nonce), an unbounded content type, an overflowing `start`; gateway 178/178, researcher+commons 82 OK. Left for the deploy: a probe that `127.0.0.1.nip.io` and `169.254.169.254.nip.io` fail at Cloudflare's egress; the account's plan (CPU limit); fetched text copied into library notes loses its wrapper |
| I2/I3 | Recorders for key-free hosts; requests answered by rule (fulfilled by a recorder's `asks`, or blocked with the rule it fails) | built, PR #309 (282 tests OK; ci passed): **21 new hosts** (25 → 46) in one module `league/open_feeds.py`: settlement-grade weather (`cli` NWS climate reports from mesonet.agron.iastate.edu, stamped at issue, backfilled; `metar` aviationweather.gov; `ghcnd` NCEI; `cli_text` tgftp.nws.noaa.gov), `kalshi_candles` (hourly, 14 days backfilled, for K2), macro (`bls`, `fiscal`, `fx` ECB, `cot` CFTC, `fomc`, `bls_releases`, `bea_releases`, `fuel` EIA tables), notices (`presidential` whitehouse.gov, `federal_register`, `halts` nasdaqtrader), attention and signals (`pageviews` wikimedia, `gdelt`, `fear_greed`, `mempool`, `storms` NHC, `quakes` USGS). Refused by their terms (bots, non-commercial or proprietary-trading bans, keys): Polymarket, MLB statsapi, NHL, NBA/WNBA, NCAA, Sleeper, Coinbase Exchange, Kraken spot, Bitstamp, Binance.US, DefiLlama, CoinGecko, Blockchain.com, Cboe, FRED, Cleveland Fed, GDPNow, Census, AAA gas, Metaculus, Manifold, PredictIt and others; Gemini borderline (left). I3: `Commons.block` answers an open request a refusal rule names and no recorder meets (`tool.blocked`, owner `owner` for keyed, `no-source` otherwise). **Reviewed** (three lenses, 11:14Z, `7d59962` on the PR; 238 tests OK): fixed a hung host holding the one-slot feeds lane (GDELT's hang would have taken 58% of it; now a per-host backoff, 4%, and a due sports board never waits over 60 s; it covers the older recorders too), history passes not giving way to a due board, a restart re-asking every source at once (BLS's 25 keyless queries), BLS retrying a 503 every 5 minutes, Kalshi candles' counts not point in time, three request names routed to the wrong or keyed recorder. Left: `feeds.sqlite` grows ~4 MB a day with no pruning of `polls` (predates this PR); `worklist.py` labels a rule refusal as the toolsmith's. **Moved into Deploy K1** (11:16Z): reviewed, its hosts already allowed, and the weekend's windows are crowded. **The 21 hosts added to the box's allowlist at 10:40Z** (`floor_box.py hosts --add`, the owner's standing approval; 58 hosts now; no release, no restart) and probed once from the box at 10:41Z: 20 answer 200; `api.gdeltproject.org` timed out in the TLS handshake (15 s): retried before K2 |
| K1c | Tennis, MMA, golf, cricket on the ESPN league map + match-winner founders | built (`k1c/more-sports`, 337 + 147 tests OK, ci passed); **reviewed** (11:08Z, `8e6a291`: an accent-folding hole that could match "Dũng Smith" to any "D... Smith", a crash on an impossible ticker date losing the wake's cancels, crashes on malformed input, takers sized over cash by their fee, a sub-penny divide-by-zero, `min_price` below the practice floor; the recorder byte-for-byte unchanged for every other league); merged into #320. **Go/no-go (probed live 10:40-10:56Z): only UFC has ESPN lines** (DraftKings moneylines on 10 of Saturday's 12 fights); tennis (ATP, WTA; ITF not on ESPN), golf, cricket and F1 have scoreboards but empty lines, so nothing prices their Kalshi markets: tennis needs the owner's paid `ODDS_API_KEY` (report). Built: UFC cards as one board row per fight, the odds request with the card id, a head-to-head seed `sports_h2h.py` (the consensus seed is at 38,749 of the 40,000-character limit), matching by fighter name only on a unique match, prices joined by ESPN athlete id, a 1.5% draw/no-contest pull toward 0.5 (Kalshi settles those 50/50), makers at 2¢, takers at 6¢; founder `h2h-ufc` (priority 80), sports desk 24 → 25. UFC also sits on the book: 16 of 18 matched markets within 1.1¢ of the de-vigged line (median 0.55¢) |
| I1b | Research's system prompt carries only the contract sections an agent needs (`contract_for(topics)` from the forward-first run's #330 in `Researcher._system`): research sends the whole contract every turn (~89 KB a turn; ~19 KB unused for agents without options, feeds or open desks), and #330 cut Merton/engineer bytes 42% | after #330 is on main (forward-first's Deploy C); keep the prompt cache stable per topic set |
| K2-int | Deploy K2's integration `k2/integration` (K5 #313 + K5b, on main `0f117bbb` with Deploy B) | draft PR #348 (22:20Z; scale rule, grants, allocator, tuition, house, founders 228 OK; ci passed); CI running; deploys in this run's Saturday slot after B, G, C and D-J2 |
| K5b | The allocator reads unlocked tranches: `grant_capital` returns the ratified capital + `live_trading.scale_unlocked(state, venue)`; the board's envelope row carries `unlocked_usd`; `House.tuition` (house.py ~3625-3646) reads the same number, so tranches reach every band; the text the owner ratifies says "unlocked tranches raise the envelope, the tuition line and the throttle's dollar line by the same amount"; tests (a) unratified changes nothing, (b) a failure adds 0, (c) capped as ratified, and one each for tuition and the throttle (agreed with the forward-first run 10:55Z) | **built** (21:26Z, `k5b/allocator-tranches` `bc02bfdd` on `b/integration` + K5: scale rule + grants 60, allocator + tuition 79, book + live pilot + constitution 108, house 47, live trading 19 OK; Kalshi 517.75 + 273.41 = 791.16 on K5's fixture, throttle trips at -387.35 instead of -305.33); **reviewed** (21:44Z, `6d209dbc`): the rule's decision is made once a UTC day and at the owner's ratification and kept in `scale-decided.json` (keyed by the grant and its ratification rows); between decisions only the relock line and the equity cap are checked (`grants.watch`); a transient failure with a tranche live changes nothing, while no record, another ratification's record or one over a day old adds $0 (all in the ratified text's `scale_tranches.reading`); reads between decisions 1.4-2.1 ms instead of a 0.61 s replay every 5 minutes on a live-size 1.06 M-row ledger; the daily replay still grows ~0.09 s a day of ledger (left); `capital.resize` (allocator disabled) ignores tranches, documented; scale rule + grants 65, allocator + tuition 79, house 47, live trading 19 OK | PR after Deploy B; owner deploy |
| K1-int | Deploy K1's integration `k1/integration` (K1a, K1b, K1c, K3, W, K2, I1's House side, I2/I3) | **CI green 12:15Z at `d05e391`** (tests 3.11 9m25s, 3.14 10m27s, gateway): after two fixes (the `kalshi_founders` switch; CONTRACT.md trimmed to FEEDS.md); the tree merged with forward-first's `a/integration` (Deploy A, `553c3ce`) merges cleanly and passes 569 key tests (12:15Z). Earlier: draft PR #320 at `c2d78de` (11:22Z: main merged in after the options run's Deploy V #317; three conflicts kept both sides: `house.py` imports, the births pass `options_desk.seat_founders(self)` then `kalshi_founders.seat(self)`, the README rows, SEEDS main's row then ours; 794 touched tests OK incl. the options desk's; CI running), before that `b630d3f` (I2 added 11:16Z: 712 league tests of the touched modules OK, the ltcm suite 1942 OK after one scoreboard test learned the new host block; K1c 11:10Z), first at `483784a` on main `c683dc3` (11:05Z): conflicts resolved (the caps line; SEEDS rows K1's then K3's; `test_seeds` restricted to the fourteen by name), tests following the merged rows (weather cap 21; two shared seed files; the founder tests unflag the real rows); 632 touched tests OK, ci passed; CI running; rebased onto main after Deploys V and A, K1c added if reviewed |
| W | `scripts/kalshi_watch.py` (this session) | built, 3 tests OK, run on the box 06:20Z; on `k/watch`, ships with K1 |

## The scoreboard at T0

Read-only on the box at 06:03-06:15Z Sept 25 (`allocator-board.json` at 06:03:51Z, `health.json`,
`feeds.sqlite`, the ledger).

| # | Metric | Reading at T0 | Target by Monday 13:00Z |
|---|---|---|---|
| 1 | Kalshi real settled P&L over the weekend | not begun; lifetime real Kalshi +$34.69 on 127 settlements: sports-central-over-under +$30.75 (3), sports-central-run-under +$23.45 (13), weather-favorites +$10.22 (22), crypto-strikes-lab-955dae +$6.87 (27), prices-favorites +$3.87 (5), crypto-strikes-lab-1b9d16 +$0.40 (9); the 15-minute crypto families and vol-shock −$40.86 | positive, with the families that earned it named |
| 2 | Kalshi families proven; their summed capacity a day | 1 of 28: sports-central-run-under (n 26, bound +0.092; real n 12, bound +0.093), $31.70 a day at $6.00 (fill 1.0, 19.3 markets a day) | ≥ 3; ≥ $100 |
| 3 | Kalshi committed / envelope | $109.23 / $546.83 (20%); on the proven family $16.62 (meriwether-h2d625d's bunt) | ≥ 50% on proven families |
| 4 | Weekend hours with no live Kalshi desk | unmeasured; real Kalshi agents: 1 bunt (sports run-under), 6 probes (2 crypto strikes, 3 weather favourites, 1 sports over-under at stake $0) | 0 |
| 5 | Model-versus-market sports founders seated; leagues covered | 0; MLB only (the run-under family's totals) | one per league with a slate; NFL, NCAAF, MLB |
| 6 | The sports family's swing | 12 real independent settlements; look at 15 (10 under forward-first's M1, in its Deploy B); days_to_swing 0.51 | reached, or the count |
| 7 | The scale report | none | prints committed, capacity used and the tranche per venue |
| 8 | Data hosts recorded; research web reads a day; agent data requests answered | 25 hosts in `LEAGUE_HOSTS`; research has `web_search` only (0 fetches); 211 `tool.request` rows lifetime (118 `tool.fulfilled`, 121 `tool.blocked`), the newest 05:23:54Z | ≥ 45 hosts recorded; `web_fetch` in use; every request of the run answered |

## Deploy K1: the runbook

1. **By 19:30Z:** every builder's PR green; the adversarial reviews (the two seeds and the seating hook: three lenses
   each, in `*/review` worktrees) merged into their branches; the other three records read (their deploys, owners);
   `deploys.jsonl` and `floor_box.py status` show no deploy in flight; the proven family's open positions and their
   games' first pitches read from the box (no deploy while one is in play).
2. **Integration** `k1/integration` from `origin/main` (with Deploy A's and V's merges in): merge
   `k1/sports-consensus`, `k1/founder-seats`, `k3/weather-ensemble`, `k/watch`, `k2/capacity` and the House side of
   `i1/web-fetch`, one at a time with `git -c rerere.enabled=false merge`, committing each merge before the next;
   the `SEEDS` rows of both seeds and the options run's at the end of `league/seeds/__init__.py`; the
   `kalshi_founders` call line right after the options run's `options_desk.seat_founders(self)`. Targeted tests on
   the tmpfs, `league.ci --no-tests`, a PR, CI's job states read (a cancelled job is not a pass).
3. **The gateway first** (no money rule): `web_fetch` rebased on the options run's gateway change, `npm run check &&
   npm test` green, `npx wrangler deploy --tag <sha>` in `gateway/`, `/v1/health` read back.
4. **The House:** merge the PR; `~/Work/ltcm-deploy` at `origin/main`; `python3 scripts/floor_box.py deploy` (the
   loop running, so the watchdog's watch runs). No money-digest change: after promotion the grant reads active on
   `535a7f15` (or whatever Deploy A left), and a ratify check writes nothing.
5. **Verify in the window:** `ops.started` on the release; the canary never runs the founders' path (`Settings.kalshi_founders` is off there), so the floor's first births pass after the start is its only test: watch it, and record each founder's `found()` timing (the NEEDS probe before the lock, the birth under it) and the births pass's and tick's seconds; one founder born a births pass, each displacement by rule
   (reason names the founder); the college board and the odds rows covering Saturday's slate (≥ 60 games with
   lines); the founders' first wakes offered markets, their intents and practice orders; no new error alerts; tick
   p50; each founder's replay recorded as the wait it is ("unsupported input: feeds recorded live since"), never a
   failed trial, so the forward-first run's F1/F3 ranking reads it as no replay record (asked 06:58Z). Then the gateway fetch from a research pass (the `web_fetch` ledger row).

## Interruptions

- **07:30-10:30Z Sept 25: the account's usage limit** (HTTP 429, "session limit, resets 3:30am America/Los_Angeles") stopped five of this run's agents mid-work (the K1 wake fix, I2, and the seat-hook, weather-seed and scale-rule reviews); the other runs stalled too (Deploy A did not happen in its 08:00-09:30Z window; main moved only by Merton's #314-316). Nothing was lost: each worktree kept its uncommitted work. Resumed at 10:32Z in priority order, Deploy K1's path first (the wake fix, the seat-hook review, the weather review), then I2 and the K5 review; the limit is shared by four runs, so this run keeps at most three agents at once from here. Two waiter loops of the K5 builder (`pgrep -f` matching its own command line, 3 h 20 min) were stopped; its `test_live_trading` run had finished (19 OK).

- **11:44Z: #320's first CI run was cancelled at its 20-minute limit** (main's suite takes 7-8). With the weekend's founder rows flagged in `niches.json`, every unrelated House test's births pass seated a real founder, each birth probing its NEEDS (`test_house` grew a `meriwether`). Fixed (`0773e13`): `Settings.kalshi_founders` (default off) gates `kalshi_founders.seat()`; `service.build` turns it on for the floor and never for the canary, whose ticks the watchdog times; the founder tests turn it on in their own Houses; a test that a House without it seats nobody. Founder + House tests 97 OK, 616 more House-heavy tests OK.

- **12:02Z: #320's second CI run failed one test of 3,695** (`test_repairs` restart test: the job went `dormant` on the per-job spend limit). The engineer and every Merton pass read `CONTRACT.md` whole as their system prompt; K1 had grown it 69.0 → 81.7 KB, and with a $1.75 hold booked the default $5.00 ceiling had only a few hundred bytes of room even on main. Fixed (`d05e391`): the Sept 26 feeds' full texts move to `league/FEEDS.md` (the same texts reach agents through `runtime_status`), `CONTRACT.md` keeps the declaration and a line per feed (75.4 KB, +6.4 KB over main), and the restart test, which is about the restart's bookkeeping, raises its ceiling and says why. The margin itself is worth the forward-first run's attention (every run's CONTRACT growth is paid on every engineer and Merton call).

## Findings before the builders report

- **No agent has ever declared `weather`, `nws`, `forecast` or `odds`** (every `agent.born` row to 06:30Z Sept 25:
  feeds declared by 20 agents in all, `funding` 11, `vol` 9, `oi` 1). The recorders of Sept 24 hold 10 ensemble runs per
  station and 60 days of forecast history, and the sports odds since 08:35Z Sept 24, but no strategy reads them: the
  foundry's planned `first_transfer` (the weather favourites on the ensemble's fair value) never produced a seated
  agent. K1 and K3 seed the model-versus-market founders directly, seated as founders (rung 1, practice as the test),
  because a day-horizon strategy reading a live feed cannot be replayed until 20 days are recorded.
- **The watch's first reading (18:00Z Sept 24 to 06:20Z Sept 25).** Every hour had a live real-money Kalshi desk
  (5-10 real agents woken with markets offered each hour, 6-14 real intents). Real settled +$20.31: MLB +$18.42 on
  9 events (the run-under bunt +$3.98 on 7 of them, taking every entry; the over-under probe +$14.44 on 2), crypto
  strikes +$0.54 on 14 events (135 post-only orders, 20 fills), prices +$1.35. Real refusals 95: per-event cap 67,
  maker-only 24, horizon 4. Practice settled −$17.58 (NFL −$59.24 on 2 events; NCAAF +$30.93 on 1; the 15-minute
  crypto desk +$11.93 on 83 events). Five real `book.fill` rows are the House's dust (`source: dust`, no instrument,
  −$0.0003 to −$0.0007 each), not trades: the watch keeps them out.
- **MLB's regular season ends Sunday Sept 27.** The one proven real family trades MLB totals; its markets shrink to
  the postseason's few games from Tuesday. Its capacity after this weekend is a fraction of today's $31.70 a day,
  which the scale report and K2 must say, and which makes a football sibling (NFL and NCAAF central unders) the
  mechanism's continuation if the evidence supports it (the study below).
- **The proven family's mechanism, measured on the whole market (06:30-06:50Z).** A study on Kalshi's public record
  (the session's scratch `under_study.py`): every settled KXMLBTOTAL event Sept 4-24 matched to ESPN's board (239 of
  277), buy NO on the central strike (pre-game NO price in 0.38-0.62, volume-weighted over the 7 hours before
  start−1h from Kalshi's public trade prints; the outcome is Kalshi's own `result`). The under won 107 of 239 (44.8%)
  at an average NO price of 0.499: mean −14.2% a dollar after the taker fee, t −2.19. It runs in regimes over dates: Sept 4-19
  negative on 14 of 16 days, Sept 20-24 positive every day (35 of 53). The family's entire record (meriwether-h2d625d,
  first close 02:01Z Sept 23, practice 20-lot and real 2-20-lot NO takers) sits on three slate dates inside that last
  stretch, so n 26 / bound +0.092 measures one regime, not the mechanism. **Verified and corrected by the forward-first
  run (07:08Z, four independent checks; numbers in its record, "The proven sports family, verified"):** the family's
  program rebuilt with its own rules on all 277 games lost 12.2% a dollar (t −1.91); KXMLBTOTAL's `fee_multiplier` is
  0.5 (a real fill pays 0.035·C·P(1−P)), so this study's 0.07 doubled the fee while its VWAP sat 0.6-0.8¢ under the
  ask, and the two roughly cancel (−13.8% a dollar at the ask with the right fee); 37 games were skipped because ESPN
  writes ARI/CHW where Kalshi writes AZ/CWS; and same-night games are NOT correlated (intraclass correlation −0.003):
  the defect is time, a proof with no distinct-dates requirement, not clustering within a night. Its decisions: M1 at
  10 plus a five-distinct-dates gate at every swing look; M3 seats members only when the proof spans five or more
  dates and only members running the proven code; the same gate on `family_proven` is an owner decision in its report. NFL totals (43 games since Aug 27, preseason included): the central under won
  22/43 at 0.510, −3.6% a dollar, t −0.24: no premium; NCAAF totals (269 games matched of 421 since Aug 27): 128/269 (47.6%) at 0.514, −10.1% a dollar, t −1.68. Sent to the forward-first run at 06:52Z (it owns the family
  proof, the swing at 10 and M3's members); this run changes nothing of theirs, writes no football sibling of the
  mechanism, and puts model-versus-market pricing (K1, K3) ahead of behavioural premia.
- **K1's premise, measured point in time (06:55Z).** Every `odds` row recorded since 08:35Z Sept 24 (one provider,
  Draft Kings, de-vigged) against Kalshi's winner-market public prints in the 30 minutes before the row: MLB 112
  readings on 10 games, mean Kalshi − DK +0.6¢, median gap 0.7¢, p90 1.4¢, none ≥ 3¢; WNBA 56 on 4 games, median
  1.3¢, p90 2.2¢; NCAAF 6 on 4 games, median 1.8¢, p90 2.7¢. Kalshi's winner markets sit on the book's line, so a
  model-versus-market founder earns there only as a maker inside the spread (thin, adverse selection the risk); the
  spread and total ladders, thinner and wider, are where a larger gap can exist. Sent to the K1 builder for its
  defaults (winner threshold about 1-1.5¢ after the maker fee, ladders about 3¢, taking only above 6¢, requotes on
  line moves).
- **No seat can be freed for a founder today (07:05Z).** Health's seat market reads displaceable 0 for an evidenced newcomer (`_displaceable(rules, evidenced=True)`, 128 of 128 living, 71 waiters: 35 graduates, 18 merged strategies, 16 cards). A hook that seats founders only through `_displaceable` seats nobody until the forward-first run's F3 (Saturday). Closing a desk (`dormant`) stops births there but keeps its residents. Proposed to the forward-first run (07:05Z): the hook retires, one per births pass, the weakest PRACTICE resident of `kalshi-crypto-15m` (this plan's K3: that desk stays closed while its record is negative; practice −$254, real −$40.86) down to F3's floor of 4, never real money, a position, or a proven family's member, and seats a founder in the same call; the desk's cap goes 8 → 4. The seating builder builds it gated by a `yields_seats` flag on the desk row. The options run was told its founder hook meets the same wall. **Agreed by the forward-first run (06:55Z)** with five conditions, all taken: the line after the options line once Deploy A is on main, under the births' lifecycle lock; one retirement a pass, never real money, a proven or swinging family's member, a position or working order, or one mid-wind-down, floor 4; the death's own cause `desk_closed` (not `displaced`, so the displacement share and F3's tenure rules do not count it) with the postmortem naming the founder and the desk's record; nothing deleted; founders only into a free seat of their own desk, inside 128. Founders keep `found()`'s rule (rung 1; their replay runs and waits for 20 days of live-feed recording, a wait and not a trial). Also: the 18 waiting merged strategies include `hilibrand-event-budget-child`, the corrected child of hilibrand-lc04657, whose 104 real per-event-cap refusals in 24 h are this weekend's largest refusal class (K4); it waits for F3's strategy seats.
- **Research's `web_search` is Google News headlines only** (found by the I1 builder): Sail's paid search was unwired on Sept 20 (#16, docs/phase-one.md: "Unpriced paid Sail web search is disabled in this phase; the existing news fallback remains"). `web_fetch` gives research the pages; finding them still leans on news, the library and the agents' own knowledge. Re-enabling a paid search is a compute decision this run leaves to the owner (report).
- **K2's first capacity table (ledger to 06:46Z, board 06:40Z; 1x = the family's real position size, $6 run-under, $2 the rest; maker fills from Kalshi's public prints in each market's resting window, taker fills from books read at 06:46Z).**

  | family | markets a day | fill 1x/2x/4x/8x | $ a day 1x/2x/4x/8x | fills halve | envelope 1x/4x |
  |---|---|---|---|---|---|
  | sports-central-run-under (proven) | 19.1 | .96/.94/.91/.90 | 29.95/58.90/114.29/225.06 | >256x | $90/$360 |
  | sports-central-over-under | 11.1 | .99/.98/.97/.94 | 22.17/43.86/87.05/169.02 | >256x | $10/$40 |
  | weather-lab-b8b1fe | 31.4 | .82/.82/.81/.80 (floor .72) | 5.04/10.07/19.88/39.30 | >256x (floor 173x) | $30/$120 |
  | crypto-15m-prior-window-reset | 27.3 | 1.00 (one book) | 2.53/5.06/10.11/20.23 | >256x | $10/$40 |
  | crypto-strikes-lab-1b9d16 | 35.1 | .60/.59/.58/.57 (floor .42-.36) | 2.16/4.25/8.42/16.50 | >256x | $10/$40 |
  | prices-lab-cd96fa | 15.8 | .56/.54/.52/.51 | 0.86/1.67/3.22/6.31 | >256x | $10/$40 |
  | weather-favorites | 26.5 | .90/.90/.89/.88 (floor .73-.66) | 0.37/0.74/1.47/2.91 | >256x | $40/$160 |
  | prices-favorites | 13.7 | .56/.54/.52/.51 | 0.20/0.38/0.74/1.45 | 221x (floor 50x) | $20/$80 |

  Totals: proven $29.95 a day at 1x, $114.29 at 4x (envelope $90 / $360); all eight positive $63.28 / $245.18 (envelope $220 / $880) against $109.23 committed of $546.83. **Liquidity does not bind below 8x on any positive family: edge and the count of proven families do.** The dollars a day multiply by the board's `edge_per_dollar`, which for run-under is its streak's +0.27; on the three-week market-wide measure above the same mechanism's edge is −0.14, so its curve is a curve of volume, not of profit. Checked against real fills: the print-based estimate matched crypto strikes (0.59 vs 0.59) and over-stated the weather favourites (0.81 vs 0.60 really filled; the strict floor 0.25): plan on the floor there.
- **Seats for founders this weekend (07:10Z, the box):** 7-day desk records from active `eval.block` rows: crypto-15m −3.99 summed log growth on 323 active blocks (8 living), crypto-strikes −0.83 on 169, options −0.59 on 30, sports-props −0.35 on 9; positive: sports +1.87 on 61 (19 of 19 seats held), weather +0.51 on 55 (17 of 17). Crypto-15m yields 4 seats above its floor; the House's own seat market frees none; so four founders trade before F3, in `seat_priority` order: NCAAF 10, MLB 20, NFL 30, the busiest weather group 40.
- **Practice understates makers (the Jev run's markout, 06:32Z, Sept 22-25):** the practice book fills a resting quote only when a venue trade prints through it, so practice makers are picked off by construction: 15-minute markouts −$185 on 240 marked practice maker fills (weather −$0.35 a fill, sports −$0.25, crypto −$2.78) against −$1.40 on 71 real ones (weather +$0.01, crypto −$0.02). K1's and K3's founders are makers: their practice records will read worse than the same bids on real money. The allocator's proof weighs practice at 0.5; whether practice maker evidence should carry a measured correction is the forward-first run's to decide, and the report says so.
- **Where Kalshi's unpriced volume is (the Jev run's J4 map, `docs/design/2026-09-25-kalshi-market-map.md`, #318, public API at 07:15Z: 1,654 series with ≥ 100 contracts in 24 h, 59.3 M contracts):** the desks cover 208 series, 53% of the volume, and 20.4 M of that covered volume has no recorded feed pricing it. The biggest near-term (settling within 48 h) volume with no feed is tennis (KXWTAMATCH 10.03 M, KXATPMATCH 2.85 M, KXITFMATCH 0.51 M), golf (KXDPWORLDTOUR 3.06 M), cricket (KXT20MATCH 1.07 M), soccer friendlies (0.62 M), UFC (0.26 M), F1 (0.19 M). ESPN's public scoreboards cover tennis, golf, cricket, MMA and F1, which `SPORTS_SERIES` does not map. Tennis trades around the clock: queued as K1c (ESPN league map + match-winner founders, tennis first) for the next agent slot.
- **Open agent data requests at T0** (in the watch window): `mlb_point_in_time_lineup_pitcher_feed` (hufschmid-39),
  `mlb_player_prop_reference_history` (hufschmid-38), `historical_external_crypto_indexes` (rosenfeld-h35c05b),
  `crypto_spot_rebalance_events` (haghani-l22bffc), and five for the options and equity desks (earnings panels,
  replay provenance) that name no new data host. I2's recorders answer the first and third by their `asks()`; the
  others are to be blocked with the rule they fail (I3's new path: no path answered a refusal before).

## Progress notes

- **22:40Z Sept 25:** #348 (Deploy K2) CI green (3.11 10m36s, 3.14 14m57s). The forward-first run moves Deploy B up: it starts once the proven family's last two real games of the night settle (AZ-SD 01:40Z, LAD-SF 02:15Z; 4 of its 6 settled by 22:40Z, net −$4.15), not at 06:00Z; its exact start in its record.
- **22:18Z Sept 25: Deploy B merged to main ahead of its deploy** (by the forward-first run, main `0f117bbb`, carrying #343 and #347): Merton's #346 (strategy files, merged 21:55Z) would otherwise have been shipped by the updater at ~22:26Z, restarting the House as the proven family's games began; B's protected files make the updater refuse main's heads until B deploys. Main holds B's money rules (digest `acff5c64`) unreleased and unratified: this run does not owner-deploy main before B at 06:00Z.
- **22:05Z Sept 25: why no founder is seated, and the fix riding Deploy B.** Births since the start: two lab graduates and one of the proven family's owed births took seats by displacement (evidenced newcomers); no founder. The sports desk has 12 of 25 seats and weather 17 of 21: only the league's 128 binds. The House's seat market frees nothing for an unevidenced founder, and crypto-15m's yield path kept 6 of its 7 members as "a winner" by the seat market's plain rule (own mean growth > 0; the 7th is real money) while the desk's pooled 7-day record was −4.17 over 375 active blocks: own records h427345-4 +0.158/27 blocks (t 2.46), hd8ff7c +0.028/8 (t 3.58), l5aa23e +0.361/30 (t 1.51), h51fdd3-7 +0.021/26 (t 0.32), hd8ff7c-8 +0.008/15 (t 0.19), h51fdd3-9 one block. Agreed with the forward-first run (22:03Z): on the yield path only a winner needs evidence (≥ 6 active blocks, one-sided t ≥ 1.0), and a desk that gave up a seat this tick (F3 or the seat market) gives none. #347 (`k1/yield-evidence`, founder tests 37 OK) rides Deploy B (merged at its ~05:00Z pre-flight, as #343), so the first founders are seated from ~06:10Z Saturday, three of them from crypto-15m's noise members down to its floor of 4, then whatever F3 frees.
- **21:05Z Sept 25: Deploy K1 promoted; a feeds starvation found; Deploy K1-fix announced.** The House: release `20260925T205243Z-8f1ce807b14d` staged 20:53:01Z, promoted 20:54:38Z, `ops.started` 20:56:05Z, the watch passed (verdict at 21:04:46Z, exit 0); grant active on `d7d910fe` (no digest change); tick 4.5 s; 21 warnings, 0 errors. **Founders: none seated yet** (10 wait): the league is full; the House's own seat market frees nobody (21 residents inside grace or clock, 7 winners, ...), and crypto-15m's yield path found no resident it may retire (of 7: research in flight 4, a winner 1, a position or working order 1, real money 1): the births pass tries every 300 s. **The odds recorder polls nothing** (last 18:48:12Z, before K1): with the evening's boards live (due every 60 s) and a pass of ~80 s, every live `Source` gives way to a due board on every pass and never polls (bls, halts, gdelt, fomc, presidential, pageviews: `next_due` 1970, 0 polls). Fixed in #343 (`_gives_way`: at most 240 s, one starved recorder a pass; a regression test; 203 feeds tests OK). **Deploy K1-fix was announced for tonight and then withdrawn (21:12Z)** to keep the House's restarts down (forward-first's target ≤ 6 a day; Friday already over): the forward-first run merges the branch `k1/feeds-starvation` into Deploy B's integration directly (B at 06:00Z Saturday; #343 lands on main with B's protected merge ~05:55Z), so odds flow from about 06:10Z Saturday. #343 is NOT merged to main alone: the House runs main's head (K1), so main + #343 would differ only in an unprotected file and the updater's release train could ship it during the proven family's games (the train knows the US session, not the game rule: raised with the forward-first run, for Merton's night merges too).
- **20:52Z Sept 25: Deploy K1 began.** Pre-checks 20:50Z: the proven family's six real positions all start 22:40Z or later; no deploy in flight (the updater refused main's head `main-430be6cbd3a4` at 20:44Z: a protected path, as designed). **The gateway first:** the deployed version was `0d46e90` (the options run's V); main's gateway differs from it only by I1; `npm run check && npm test` 201/201; `npx wrangler deploy --tag adccc8e` → version `b4048689-f844-4398-a6f9-50bc4209f002` at 20:52:13Z. Probed from the box (20:52:22Z): example.com 200 (129 characters); en.wikipedia.org/wiki/United_States 2 MiB read in 0.5 s, 192,700 characters, truncated (no CPU limit met); `127.0.0.1.nip.io` and `169.254.169.254.nip.io` answered only Cloudflare's own 16-byte 403 (nothing internal reached); `localhost` refused by the gateway; `/v1/health` `web_fetch` {fetches 4, cap 3000}. **Then the House** (`floor_box.py deploy` at `adccc8ef`, the loop running, watch on): started 20:53Z.
- **19:35Z Sept 25.** Main (options founders, tape cache, exit fixes; Merton #340-#341) merged into #320 (`af32fa36`): SEEDS main's twelve options rows then ours, `replay_regression.json` rebuilt by a per-key three-way merge (only our ten entries differ from main); 641 touched + 79 options-founder tests OK, ci passed; CI running. Deploy A (#323) is set for 20:10Z; the options run's fixes deploy comes after A and K1. Gateway tooling checked (`npx wrangler` 4.141.0, logged in).
- **14:45Z Sept 25 (a reading during the US session; no deploy).** Release `20260925T114915Z-007e06151f53` (the Jev run's D-J1). `kalshi_watch` 10:00-14:42Z: a live real-money Kalshi desk every hour; real settled −$1.58 (weather favourites +$0.58 on 4 events, crypto strikes +$0.62 on 5, a new crypto-15m probe `huang-l9abdce-3` of the lab family `crypto-15m-btc-5m-continuation-8c83cc` −$2.78 on 2: the allocator's promotion, forward-first's domain; this run's seat hook never takes a real-money agent); real refusals 47 per-event cap, 9 maker-only; shards 0 $333.90, 2 $66.24, 3 $76.98. GDELT now answers the box 429 (rate-limited from Sail's IP): I2's per-host backoff holds it off. #320 green at `d05e391`, waiting for Deploy A (20:10Z).

## Watch log

## Report
