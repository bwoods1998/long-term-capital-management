# Overnight build of the rebuilt floor (night of Sept 19 to 20, 2026)

This file is the builder's place-keeper and, at the end, the report. The goal is
`docs/design/overnight-goal.txt` (every line binds); the designs are
`docs/proposals/2026-09-19-the-game.md` and `docs/design/2026-09-19-architecture.md`.

Started 2026-09-19 06:00 UTC. Eight hours ends 14:00 UTC.

## Where I am

- **Step:** 2 (evaluator rungs 0 and 1). Step 1 is done and committed.
- **Verified so far:** step 1 (see the step log).
- **Next:** `league/evaluator.py` (statistics, trial counting, verdicts), `league/paper.py` (Kalshi
  shadow broker), `league/replay.py` (mechanical replay).

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

## Step log

### Step 1: ledger and order book (done 06:50 UTC)

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

## Spend tonight

- Sail at start: to be read from `/v2/usage/summary` before the first box is resumed.
- OpenAI at start: read from the gateway's `/v1/health` frontier block.
