# LTCM run: Kalshi at scale, the 24/7 profit engine

A third autonomous run, beside the forward-first run (`docs/goals/LTCM_FORWARD_FIRST.md`) and the
options run (`docs/goals/LTCM_OPTIONS_DESK.md`). Its job: turn Kalshi, the venue where every real
dollar of profit so far was made and the one that never closes, into an engine whose proven
mechanisms carry real capacity, and build the rule that lets new capital enter once proof says it
would be used.

- **Why Kalshi.** Lifetime real Kalshi settlements by family (to Sept 25 01:50Z): sports-central-
  over-under +$30.75 on 3, sports-central-run-under +$19.98 on 9, weather-favorites +$10.22 on 22,
  crypto-strikes-lab-955dae +$6.15 on 22; the five 15-minute crypto families −$40. Practice by desk:
  sports +$163.53 on 176 settlements, weather +$4.21, crypto-15m −$253.97, crypto-strikes −$175.30.
  The one family proven on real money has about $31 a day of capacity at its stake.
- **Why now.** The weekend of Sept 26-28 is college football Saturday, the NFL Sunday and MLB's final
  regular-season weekend: the densest slate of the season for the only mechanisms that have earned.
  The stock and options desks sleep until Monday; Kalshi and crypto are the whole floor.
- **Why not deposits yet.** At 04:06Z Sept 25 Kalshi had $120.85 committed of a $540.45 envelope, and
  the grant says deposits do not enlarge it. Money is not the binding constraint; proven capacity is.
  This run measures exactly when that flips, and builds the rule for the owner's deposit.
- **Method.** Builders in their own worktrees, adversarial review of money code, forward records
  decide, every change verified on the box in its window. No deadline: the run ends when its Done
  list holds, and it spans the weekend.

## The owner's direction

Sept 25, 2026: "I am eager to scale up the balances in each Kalshi and Alpaca account to hit
profitability here in this automation" and "What's the third big goal we should have another
session work on in tandem to reach the north star of the project as soon as possible?"

Standing direction (Sept 23): bold inside the envelope, volatility and losses accepted, docs and repo
clean. Sept 25 04:25Z: no owner steps (no API keys) are available now.

## Coordination with the other two runs

The options plan's "Coordination" section applies to all three runs, with these additions:

- **File owners.** Forward-first owns the allocator, the families' proof, the seat market, the lab
  and the foundry brief; options owns the options desk, the multi-leg gateway route and the book's
  structure handling. This run owns Kalshi strategies and founders (`league/strategies/`), the Kalshi
  desks in `league/niches.json` (seat changes coordinated with forward-first's F3), the sports and
  weather feeds (`league/feeds.py`, `ltcm/data/sports.py`, `ltcm/data/weather.py`), the shard funder
  (`league/shards.py`), capacity studies (`scripts/`), and the scale rule (`league/live_trading.py`,
  `league/grants.py`) after forward-first's Deploy B.
- **Deploys.** One at a time across all three runs, never 13:25-20:05Z on a trading day. Weekends
  have no session: Saturday and Sunday are this run's main deploy and watch windows.
- **The grant.** Ratify after a promotion only when every changed money rule is a row of one of the
  three plans' tables.

## The evidence to re-read at T0

- Every Kalshi family's pooled record on the board (`allocator-board.json` `families.kalshi`),
  real and practice, with capacity.
- The sports desks' members, their mechanisms (MLB totals under/over, run lines, moneyline
  favourites, player props), their fill rates by size, and which leagues they trade.
- The feeds: the `odds` recorder (sports.core.api.espn.com: every provider's line and ESPN's
  predictor for the coming games) and the `sports` scoreboards; the weather ensemble and NWS feeds;
  how far back each is recorded (point-in-time rows for replay).
- Kalshi's sports series for the weekend (NFL, NCAAF, MLB, and any soccer, tennis or golf series
  the survey lists), their volumes, spreads and maker fees; the shard balances for each series'
  shard (sports on shard 3).

## Workstreams

### K1. Model versus market on sports (tonight, before the weekend slate)

- A founder family per league that prices Kalshi game markets (winner, spread, total) from the
  sportsbooks' consensus in the `odds` recorder, de-vigged, and bids post-only where Kalshi's price
  is off the consensus by more than fees plus a margin; takers only where the forward-first run's
  M2 allows. Leagues: NFL, NCAAF, MLB, and any other league the recorder covers with a Kalshi
  series.
- Replay each on the recorded odds history where it exists (point-in-time); where it does not,
  practice is the test, and the record says so.
- The existing proven MLB run-under mechanism gets members on disjoint games (forward-first C7
  does the House side; this run writes the children), and a sibling on NFL and NCAAF totals if the
  replay supports it.
- **Acceptance:** founders seated on every league with a weekend slate by Saturday 15:00Z; their
  first practice fills that day; a replay or a stated reason for each.

### K2. Capacity at size (measured, weekend)

- For every Kalshi family with a positive pooled record: the book depth at its prices (the
  orderbook through the gateway's read route), the fill rate at 1×, 2×, 4× and 8× its current order
  size from its own history, and markets a day in its band. The result is a capacity curve: dollars
  a day it could earn at each stake, and where fills halve.
- A standing table in the run record and on the board: each proven or near-proven family's
  capacity at its stake and at 4×, and the envelope that would use it.
- **Acceptance:** a curve for each family with a positive record; the sum of capacity against the
  committed envelope.

### K3. 24/7 coverage

- Every hour of the weekend has at least one Kalshi desk with members whose markets are open and
  inside their horizon: sports by day, crypto strikes and weather overnight. The watch lists hours
  with no offered market and no intent.
- Weather: the ensemble transfer card (the foundry's `first_transfer`) priced across every daily
  high, low and rain series the desk can reach, since favourites alone measure $0.24 a day.
- Crypto strikes: the lab-955dae and lab-1b9d16 families' far-from-spot favourite makers are the
  positive ones on real money; add members on disjoint strikes and hours, and keep the 15-minute
  desk closed while its record is negative.
- **Acceptance:** no weekend hour without a live Kalshi desk; the ensemble card seated.

### K4. Shards and execution

- The shard funder keeps each shard a family trades funded before its slate (sports on shard 3 before
  Saturday's games), within its existing limits.
- Every refusal on a real Kalshi book over the weekend is classified (per-event cap, maker-only,
  longshot floor, horizon, shard), and strategies are corrected by children, not by loosening the
  rules.

### K5. The scale rule (after forward-first's Deploy B)

- A new grant version the owner ratifies, never activated by the run: a deposit enters a venue's
  envelope in tranches, each tranche unlocked only when the proven families on that venue use at
  least 70% of the current envelope at their capacity curve's fill rate for 3 consecutive days, and
  the floor's real P&L on that venue is positive over those days. Losses count in full; the throttle
  and kill switch stay.
- `scripts/live_trading.py` gains a read-only `--scale-report`: per venue, committed against
  envelope, capacity used, the tranche the evidence would unlock today, and the deposit that would
  put it to work. That report, not a hunch, is when the owner deposits.
- **Acceptance:** the rule built, reviewed, merged switched off, with the report printing today's
  numbers; the owner's ratification command in the report.

### I. Open inputs: everything useful, through the right doors

The owner, Sept 25, 2026: "Can we also expand the allow list incredibly broadly? I'm not sure why we
wouldn't want everything useful there for agents and they know they can use these online resources."

Agents meet the internet through three doors, and each widens differently:

- **Strategy boxes stay sealed** (no network, `league/safety.py`): a strategy must behave the same
  in replay, practice and real money, and live web reads cannot be replayed without lookahead.
  Strategies see the web only as recorded, point-in-time feeds (`ctx["feeds"]`).
- **I1. Research reads the web** (`league/researcher.py` tools; `gateway/`, protected, a gateway
  deploy). A `web_fetch` tool beside `web_search`: any public http(s) URL, fetched BY THE GATEWAY
  (the House box's egress stays exact-host: it holds the Sail key and the gateway token, and Sail's
  allowlist ignores wildcards anyway). GET only; no cookies or credentials forwarded; private,
  link-local and metadata addresses refused; redirects re-checked; response converted to text and
  capped (about 200 KB); a per-agent daily fetch budget charged in credits; fetched text is data,
  never instructions, and the research brief says so. Each fetch is a `tool` row with the URL.
- **I2. Recorders for every useful key-free host** (`league/feeds.py` `RECORDERS`,
  `scripts/floor_box.py` `LEAGUE_HOSTS`). Broad, not curated to a dozen: the run adds any host that
  is key-free, public, permits automated access in its terms, and answers without a bot wall, each
  with a recorder that stores point-in-time rows so replay can use it. Start with what the desks
  need most: Polymarket's public market data (cross-venue pricing for every Kalshi desk), league
  stats and schedules (MLB, NHL, NBA, NFL, NCAA public APIs), Wikipedia pageviews (attention),
  GDELT (news volume and tone), Cboe's public delayed data (options and VIX), public crypto exchange
  market data (order books, funding, open interest), NOAA/NWS products beyond forecasts, BLS and
  Treasury releases, Kalshi's own public trade history. Refused: anything behind a login, a key,
  a paid plan or a captcha (those are the owner's), and anything whose terms forbid bots.
- **I3. Agents ask, the run approves by rule.** A `tool.request` or research summary naming a data
  source becomes, within the run: the rule check above, the host added
  (`python3 scripts/floor_box.py hosts --add <host>` from `~/Work/ltcm-deploy`, then `LEAGUE_HOSTS`
  by PR), a recorder, and a `library.note` telling the desk the feed exists. The watch lists
  requests and what became of each.
- **Acceptance:** `web_fetch` used by research with rows on the ledger; at least 20 new hosts
  recorded with point-in-time rows; every agent data request of the run answered (built, or refused
  with the rule it failed); a strategy naming a new feed seated.

### W. The watch (the weekend)

- Every 30 minutes from Saturday 15:00Z to Sunday 23:59Z: Kalshi real and practice fills and
  settlements by family and league, refusals by class, capacity used, shard balances, the scale
  report.
- Bugs are fixed with regression tests. No deploy while a game a real family holds is in play,
  unless it is a rollback.

## Money-rule bounds for this run

| Rule | Now | Allowed range | Why |
|---|---|---|---|
| K5 `grant.scale_tranches` (new; a new grant version) | none: deposits never enter the envelope | the tranche rule above, activated only by the owner's ratify | the deposit follows proof |
| `allocator.max_event_share` on sports families | 0.25 | 0.25-0.35 for a PROVEN family only | a proven family's one game per member (C7) should hold its share of the stake |

**Egress (the owner's standing approval, Sept 25, 2026):** this run may add any data host that meets
I2's rule to the House box's allowlist and to `LEAGUE_HOSTS` without asking, and may deploy the
gateway's `web_fetch` route with its tests green. It may not give a strategy box network access, add
a host that needs a key or login, or send any credential to a fetched host.

Everything else follows the forward-first plan's "Authorized" and "Not authorized" lists. In
particular: no deposits or transfers between venues, no cap above funded money, no test orders, no
forced trades.

## The scoreboard

| # | Metric | Baseline (Sept 25) | Target by Monday 13:00Z |
|---|---|---|---|
| 1 | Kalshi real settled P&L over the weekend | — | positive, with the families that earned it named |
| 2 | Kalshi families proven on the real record; their summed capacity a day | 1; about $31 | ≥ 3; ≥ $100 |
| 3 | Kalshi committed / envelope | $121 / $540 | ≥ 50% committed on proven families |
| 4 | Weekend hours with no live Kalshi desk | unmeasured | 0 |
| 5 | Model-versus-market sports founders seated; leagues covered | 0; MLB only | one per league with a slate; NFL, NCAAF, MLB |
| 6 | The sports family's swing | 9 of 15 real settlements (10 under forward-first M1) | reached, or the count |
| 7 | The scale report | none | prints committed, capacity used and the tranche per venue |
| 8 | Data hosts recorded; research web reads a day; agent data requests answered | 25 hosts in code, search only; — | ≥ 45 hosts recorded; `web_fetch` in use; every request answered |

## Done

- The weekend watch and the scoreboard at T0, Saturday's close, Sunday's close and Monday 13:00Z
  are in the run record;
- K1-K4 and I1-I3 live and verified in their windows; K5 built, reviewed, merged switched off, with the owner's
  command;
- tests and CI green; no harness incident caused by this run; neither other run blocked;
- docs, memory and the repo current and clean; the report delivered with the owner's next decisions:
  the deposit (with the scale report's numbers), the Odds API key, which desks to close.

## The /goal message

```
/goal Execute docs/goals/LTCM_KALSHI_SCALE.md (branch goal/kalshi-scale-2026-09-25; merge it to main first) autonomously with no deadline, beside the forward-first and options runs, until its Done list holds.

- Direction: make Kalshi, where all our real profit has come from and which never closes, the swarm's 24/7 profit engine. Put model-versus-market sports founders on every league with a slate this weekend (college football Saturday, NFL Sunday, MLB's final weekend), priced from the sportsbook consensus the odds recorder already captures; grow the proven sports family on disjoint games; measure every positive family's capacity at 1x-8x its size; keep a live Kalshi desk in every hour of the weekend; open the web to the swarm broadly (workstream I: research reads any public page through the gateway's web_fetch, recorders for every useful key-free data host with point-in-time history, agents' data requests approved by rule; you have my standing approval to add any host that meets I2's rule without asking); and build the scale rule so my deposits enter the envelope only when proven families would use them. Be bold inside the envelope: I accept volatility and losses.
- Coordinate with the other two runs exactly as the plan's "Coordination" section says: file owners, one deploy at a time across all three, no deploy 13:25-20:05Z on a trading day or while a real family's game is in play, and ratify after a promotion only when every changed money rule is a row of one of the three plans' tables.
- Authority: the forward-first plan's "Authorized" list applied to this run's workstreams, plus this plan's money table. The scale rule is built and merged switched off; only I ratify it. Nothing in "Not authorized": no deposits, no transfers, no cap raises, no test or forced trades. No owner steps needed.
- Method: builders in worktrees, adversarial review of money code, verify on the box in each window, watch the weekend every 30 minutes, fix bugs with tests, report at Monday 13:00Z with the scoreboard, the scale report's numbers and my next decisions.
```
