# Overnight build of the rebuilt floor (night of Sept 19 to 20, 2026)

This file is the builder's place-keeper and, at the end, the report. The goal is
`docs/design/overnight-goal.txt` (every line binds); the designs are
`docs/proposals/2026-09-19-the-game.md` and `docs/design/2026-09-19-architecture.md`.

Started 2026-09-19 06:00 UTC. Eight hours ends 14:00 UTC.

## Where I am

- **Step:** 5 (Astra's roles, CI guard, canary, watchdog). Steps 1 to 4 are built, tested and
  committed; the real end-to-end dry run is ticking (scratch root `dry2`, test tape).
- **Verified so far:** see the step log. League suite 646 tests, site 64, gateway 81 (unchanged).
- **Next:** `league/ci.py`, `league/watchdog.py`, `league/astra.py`; then step 6 (Kelly sizing,
  capital recommendation); then deploy to the House box, runbook, README/docs, final report.
- **Open items to finish before the end:** adversarial test agent's bug list (18 expected
  failures in the suite are its bug demonstrations: fix each, remove the marker); dry-run
  evidence for (b); real Astra audit + architect calls for (c); canary rollback for (d); test
  tape render check for (e); stop the dry run and pause every box; flatten the paper account.

## Decisions and their reasons

(Appended as they are made. Newest last.)

1. **New package `league/` beside `ltcm/`.** The old runtime stays importable while the new one
   is built; old code is removed only when the new code replaces it and the tests prove it.

2. **Kill switch found released at 06:03 UTC and engaged.** `/v1/health` said `kill_switch: false`
   (left off after the Alpaca route checks). The goal says it stays engaged, so `POST /v1/kill`.
   The paper venue ignores it by design, so tonight's paper tests still run.
3. **The ledger is one chain, not one per stream.** `league/ledger.py` copies the mechanics of
   `ltcm/events.py` (canonical JSON, digest over the previous digest, UPDATE/DELETE triggers,
   idempotent ids) with the league's own kinds and an `agent` column. One chain gives a total order
   that a reconciliation can pin (`ledger_seq`, `ledger_digest`).
4. **The old risk engine is reused unchanged.** `ltcm/risk.py` is pure and duck-typed on the
   manifest, so the book builds a `RiskContext` from its own state and runs all 21 rules, then adds
   the league's rules: $75 order cap, rung position caps, cash including fees and slippage, quote
   age, and no order that could trade against the House's own resting order.
5. **Netting rule, v1.** Same-batch market orders on one instrument are netted; the minority side
   is crossed inside the House at the venue's touch with the venue's taker fee (each agent is
   scored exactly as if it had traded alone; the saving accrues to the House row, which keeps the
   books summing to the venue). Limit orders are never pooled (one venue order per intent, so no
   apportioning). An intent that could execute against a House resting order is refused rather
   than cancel-and-crossed: simpler, never a wash trade. Cost: a refused agent loses that fill.
6. **Agents get zero credentials, not a House token.** The House drives each agent's box over the
   Sail exec API (resume, run `decide`, read stdout, sleep) and runs the researcher model and
   tools on the agent's behalf, metered to it. Nothing in an agent's box can reach the House, a
   venue or the gateway. This is inside the constitution's bound ("no credential except a House
   token") and removes the need for House ingress.
7. **Reconciliation uses a baseline.** The paper account holds $100,000 that is not the book's and
   the real accounts hold unallocated cash, so the book records once what the venue held at
   opening; afterwards venue cash must equal baseline plus the book's own cash, to the cent, and
   each position the baseline's plus the agents'. Under a cent (per venue fill since the last
   check) is booked to the House row as dust; more freezes new entries but never exits.

8. **Alpaca fills are booked at the taker's fee; reconciliation returns a maker's difference.**
   Alpaca reports no fee and accepts every order asynchronously, so only the venue knows whether a
   limit order made or took. The book assumes the taker's 0.25% and keeps a per-reconciliation
   allowance; a venue that charged less shows up as surplus coins or cash, booked to the House row.
9. **One account never holds both legs of a Kalshi market.** Kalshi nets YES against NO and pays the
   pair out early, which would stop per-agent legs summing to the venue. The book refuses an
   opening buy on a leg whose opposite leg the House holds or bids. (The real adapter reports a NO
   holding as a negative count; reconciliation reads it that way.)
10. **The loss-rate gate is exact, not Wilson.** The statistics builder measured the one-sided
    Wilson bound at 92 to 94% coverage for clean records; the gate now uses Clopper-Pearson. A
    record of clean +0.5% wins risking 7% needs 46 of them, not 40.
11. **Founders start on paper.** The first dry run showed honest replays failing most seeds (crypto
    reversion Sharpe below zero after fees; Kalshi favourites deflated Sharpe 0.85 against the 0.90
    line). Paper costs nothing and forward evidence is what counts, so the twelve founding seeds
    are seated on rung 1 at birth; their replay still runs and still counts as their family's first
    trial. Everything born later (forks, mutations, Astra's strategies) must pass replay first.
12. **Niche floors are paid only to qualified agents (rung 1 and up), and a rung-0 agent that has
    not passed replay within three epochs is retired.** A floor for an agent that does nothing
    would pay for squatting on a population slot.
13. **Replays and research run beside the tick, never inside it.** The first real tick took six
    minutes because a Kalshi tape build and a flex-window model call ran inline.
14. **The site got a test tape** (`/api/capital/t/test/...`, viewed at `/capital/?tape=test`): the
    same Durable Object class under another name, allow-listed to `test` and `canary`. The
    production tape stays empty until go-live, which also keeps the gateway's old watchdog quiet
    (it acts only on a published production checkpoint).
15. **Web search is Sail's search API** (found working with the project key; price unpublished, so
    the House charges agents a conservative $0.01 a query), with Google News RSS as the fallback.
16. **Agent boxes are forks of the first run's lab image checkpoint** (python3 present), sealed with
    an egress allowlist of one never-resolving host because Sail refuses an empty allowlist.
    Verified live: DNS fails inside the box; decide takes about 9 s a wake; a fork takes about 25 s.

## Step log

### Step 1: ledger and order book (done about 06:20 UTC)

Built `league/ledger.py`, `league/fees.py`, `league/book.py`, `league/venues.py`.

Verified:
- 40 league tests pass (12 ledger, 28 book); the old runtime suite still passes (1,696).
- **Live check against the real Alpaca paper account through the gateway**
  (scratch `book_live.py`): two agents staked $200 each; three netted buys (BTC twice, ETH), then
  one agent sold out while the other bought (crossed inside the House, only the difference sent),
  then everything closed. The book reconciled to the venue after every stage: cash differences
  -$0.0015, -$0.0024, +$0.0021 (all under a cent, booked as dust), no position differences, 47
  ledger rows verified.
- What the live check taught, all now in the code and the tests: Alpaca takes the 0.25% crypto
  taker fee out of the coins on a buy and out of the proceeds (rounded up to the cent) on a sell,
  and reports a fee of zero; every order comes back `accepted` and fills a moment later (so
  "still open" does not mean maker); positions come back as `BTCUSD` for orders in `BTC/USD`.

### Step 2: evaluator rungs 0 and 1 (done about 06:45 UTC)

`league/stats.py` (97 tests), `league/replay.py` (61), `league/tapes.py` (39, plus a live smoke
check: 72 BTC bars through the gateway, 27 live KXBTCD markets, a 12-hour Kalshi tape in 13 s),
`league/paper.py` (42: the Kalshi shadow venue), `league/evaluator.py`, `league/constitution.py`.

### Step 3: economy and lifecycle (done about 07:10 UTC)

`league/economy.py`, `league/agents.py`, `league/sandbox.py`, `league/runner.py`,
`league/commons.py`, `league/researcher.py`, `league/rules.py`, `league/seeds/` (12 seeds, 131
tests), `league/house.py`, `league/budget.py`. Sail sandbox verified live (decision 16). First real
dry run (three seeds): replays ran in Sail boxes in 10 s each and were recorded as trials.

### Step 4: auditor and publisher (built; live checks pending)

`league/frontier.py`, `league/auditor.py`, `league/publish.py`, `league/service.py`,
`league/__main__.py`. The publisher's real output passes the site's own `validCheckpoint` and
`validEventBatch`. Site changes deployed (version 64cdf966): test tape, practice positions with a
tag, research tool phrases; production checkpoint still 404 (clean).

## Spend tonight

- Sail at start: to be read from `/v2/usage/summary` before the first box is resumed.
- OpenAI at start: read from the gateway's `/v1/health` frontier block.
