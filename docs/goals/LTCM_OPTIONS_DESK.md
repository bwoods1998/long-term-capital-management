# LTCM run: the options desk (level 3 on a small account)

A second autonomous run, beside the forward-first run (`docs/goals/LTCM_FORWARD_FIRST.md`), with
one job: make the Alpaca account's level-3 options approval a working instrument for the swarm.
Build tonight, trade on practice through the Friday Sept 25 session, and put defined-risk spreads
on real money for the Monday Sept 28 open if the practice record earns it.

- **Why options, and why spreads.** A $25 stake in a stock moves $0.25 on a 1% day. An option gives
  a strategy convexity with a loss bounded by what it paid. But on a $482 account a single
  near-the-money contract on a quality underlying costs $300-2,000, far over the $75 order cap, so
  today's options agents only ever see $0.15-0.75 contracts on F, SOFI, T, AAL, RIVN and SNAP, with
  spreads up to 20% of the premium. That is a lottery ticket, not a trade, and the desk's record
  shows it. A **debit vertical** (buy one strike, sell a farther one, same expiry) caps the loss at
  its net debit: a $1-wide SPY or QQQ vertical near the money costs about $30-60 and can pay up to
  $100. It is the only structure that puts liquid underlyings inside this account's caps, and its
  short leg pays back part of the premium decay that bleeds a long option.
- **Method.** Builders in their own worktrees, adversarial review of anything on the money path,
  practice before real money, forward records decide. No deadline: the run ends when its Done list
  holds.
- **Where it lives.** This plan; the run record `docs/runs/<T0 date>-options-desk.md`; the design
  already written for this work, `docs/design/2026-09-24-level-3-debit-verticals.md` on branch
  `w2-options/design` (draft PR #210), with its pure pieces in `league/verticals.py` and their
  tests.

## The owner's direction

Sept 25, 2026: "It seems like a big glaring failure that we don't have more activity on my Alpaca
account especially if I have level 3 options access which would be incredible for a star trader to
utilize with the current small Alpaca balance (ie buying 0.25 of a share in Meta isn't going to be
as powerful as trading in options). What do you think is the best thing we could do to solve this
tonight and then watch and iterate on this tomorrow when the market opens."

The standing direction of Sept 23 holds: be bold inside the envelope, volatility and losses
accepted, docs and repo kept clean. "You can ignore the things that require things from me like
api keys" (Sept 25, 04:25Z): this run needs no owner step.

## The evidence (Sept 25, 2026, 04:06-05:40Z)

| Fact | Number |
|---|---|
| Options agents ever / living | 21 / 7 |
| Their families | options-pullback 16, options-breakout 5: two mechanisms |
| Underlyings they are shown | F, SOFI, T, AAL, RIVN, SNAP, CCL, PFE, INTC, BAC, HOOD and similar |
| Why | `House._chain` shows contracts whose ask is at most `min(max_order, max_position) / 100`: $0.75 on practice, $0.40 on an $80 real probe |
| Practice record | 73 fills; 29 active blocks, summed log growth −0.354; family bound −0.107 |
| Real record | krasker-14, two contracts for $34 on Sept 24, marked near $17, draining under R5 |
| What the gateway allows | one leg, limit, whole contracts, `buy_to_open` or `sell_to_close` only; `order_class` other than `simple` and any `legs` field refused (#187) |
| Order cap | $75 an Alpaca order (`MAX_ORDER_USD_ALPACA`); an option counted at premium × 100 |
| Options history on the box | 120,566 contracts, 6.2 M bars, 316 k recorded OPRA quotes, 132 coverage rows, 1,033 feature rows |
| Real Alpaca account | about $482 equity; 5 crypto probes and the draining options probe |

What this says: the desk's losses are the instrument, not the idea of options. Nothing here
proves that spreads will make money; it says single contracts inside these caps cannot be a fair
test, and debit verticals can be.

## What "done" looks like

1. **Tonight (by 13:25Z Sept 25):** strategies can express a debit vertical; a House options
   shadow book fills them conservatively on live OPRA quotes; the chain shows liquid underlyings
   priced by net debit; at least six spread founders across distinct mechanisms are seated; the
   replay judges verticals on the options history.
2. **Friday's session (13:30-20:00Z):** spread agents trade on practice all session; the watch
   records every wake, intent, fill and refusal every 30 minutes; bugs are fixed after 20:05Z.
3. **The weekend:** the real path (the gateway's multi-leg route with maximum-loss metering, the
   real book's spread accounting, the money rules) is built, reviewed, deployed switched off, and
   switched on after 20:05Z Friday or over the weekend only for families whose practice and replay
   records meet the spread probe line below, with the grant re-ratified.
4. **Monday's open (13:30Z Sept 28):** the first real spreads, or the exact numbers why none
   qualified.

## Coordination with the forward-first run

Two autonomous runs share one repo, one House and one grant. These rules keep them from breaking
each other; the forward-first run's owner message is extended the same way (see the end).

- **Read before you write.** At T0 and before every merge, read the forward-first run record
  (`docs/runs/2026-09-25-forward-first.md` on its branch `run/forward-first-2026-09-25`) for its
  current wave, its file owners and its next deploy. Never edit a file that run lists as owned in
  its current wave. Work that needs one waits, or goes in as a small hook after that wave merges.
- **New modules first.** The spread work lives in new files wherever it can: `league/verticals.py`
  (from #210), `league/options_shadow.py`, `league/strategies/` founders, tests. Hooks into
  `house.py`, `book.py`, `constitution.py` and the gateway are kept small and rebased on the
  latest main.
- **One deploy at a time.** Before an owner deploy, read the box's `deploys.jsonl` and
  `ops.started`; never start one while another release is in its canary or watch, and never
  within 30 minutes of the forward-first run's announced deploy. The watchdog's lock refuses a
  second deploy anyway: a refusal is a wait, not a retry loop.
- **The grant.** Money changes of this run are the rows of its own table below. They merge to
  main only minutes before the deploy that carries them. After ANY promotion that leaves the grant
  inactive, whichever run sees it first ratifies `earned-live-20260921` within a minute, if and only
  if every money-rule change in the new digest is a row of one of the two plans' tables; otherwise
  it rolls back and records why.
- **No deploy between 13:25Z and 20:05Z on a trading day**, except a rollback. The forward-first
  run's release train (H3) holds the updater to the same.
- **A message to the other run is a line in your own record plus a PR comment on its open PR**,
  never an edit to its record.

## Clock and authority

- **T0** is the first `date -u` after reading this plan, written into the run record and committed.
- **Authorized:** everything the forward-first plan's "Authorized" list grants, applied to this
  run's workstreams; the money-rule table below with a re-ratify of `earned-live-20260921`
  within a minute of each promotion that moves the digest (at most two digest changes for this
  run); a gateway deploy that adds the multi-leg route of G below, with its tests green; real
  debit verticals on the Alpaca cash account inside the envelope once O4's line is met.
- **Not authorized:** everything in the forward-first plan's "Not authorized" list; in particular
  a credit spread, a naked short option, a spread whose sold leg can exist without its bought leg
  (legging in or out), a ratio spread, a calendar, anything past expiry day, multi-leg orders on
  the shared practice account (they would freeze every Alpaca practice agent: the design's owner
  step 1), a test order of any kind, raising the $75 order cap.

**Money-rule bounds for this run.** Every other money rule stays as it is.

| Rule | Now | Allowed range | Why |
|---|---|---|---|
| O1 `allocator.option_spreads_real` (new; the book and the gateway read it) | absent: no multi-leg order anywhere | `false` until O4's line is met by at least one family, then `true` | the switch: real spreads go live by a digest change, never by a deploy alone |
| O2 `allocator.spread_probe_usd` (new) | none (`option_bunt_usd` $80 for one contract) | $80-150 for an agent whose program trades debit verticals | a probe that can hold one or two $30-60 verticals, never a whole account |
| O3 `allocator.spread_position_share` (new) | the option rule: one contract of at most half the stake | 0.5-1.0 of the stake in maximum loss (net debit × 100 × spreads) | a vertical's loss is bounded at its debit, so its cap reads the bound, not the premium of either leg |
| O4 `allocator.spread_probe_line` (new) | the bunt line (E ≥ 1.01, 5 closed trades) | a debit-vertical family is probe-eligible when its pooled record has ≥ 3 closed spreads on practice with W_paper ≥ 1.01, OR ≥ 1 closed practice spread plus a passed replay on the options history with ≥ 20 spreads and positive out-of-sample growth; R5 (no probe on a losing family) applies unchanged | one Friday session gives a day-horizon spread agent 1-3 closes: the replay on 6.2 M recorded bars carries the rest of the evidence |
| O5 `evidence.alpaca_paper_haircut_bps.option_spread` (new) | none | 24-60 bps a side, from the first ≥ 30 shadow spread fills | shadow spread fills must stay conservative |

## Workstreams, in order

### O0. T0 (first hour)

- Read both run records, the design on `w2-options/design`, and the options desk's live state:
  agents, chain rows, the real account's positions and orders.
- Merge `w2-options/design` into a working branch from current main (the design's line numbers
  are from `b40e737`; re-derive them). `league/verticals.py` and its tests go to main first:
  they touch nothing in the House.
- Baseline scoreboard rows (below) into the record.

### V. Spreads on practice before the open (Wave 1; deploy by 12:30Z Sept 25)

- **V1. The intent.** Strategies return the design's `{"spread": "debit_vertical", ...}` intent
  (section 1); `verticals.parse_vertical` validates it; `CONTRACT.md` gains the section. A
  single-leg option intent is unchanged.
- **V2. The chain by net debit** (`house.py` `_chain`, a small hook). A strategy whose NEEDS asks
  for `"spreads": true` is shown contracts whose ask exceeds the single-contract affordability
  line, on liquid underlyings (SPY, QQQ, IWM, the megacaps, XLF, XLE and whatever its NEEDS
  names), grouped by expiry with strikes adjacent, each row keeping `bid`, `ask`, `iv`, `delta`,
  `volume`, `open_interest` where the feed has it. A pair is affordable when its net debit at the
  touches (long ask minus short bid) × 100 fits the order cap and the position cap.
- **V3. The options shadow book** (`league/options_shadow.py`, new; a practice book the House
  owns, like `kalshi-shadow`, with no venue account and nothing to reconcile). A spread order fills
  only when both legs can fill at once at conservative prices: the long leg at its recorded ask or
  worse, the short leg at its bid or worse, the net inside the limit; nothing fills in the quote the
  decision saw; no fill over 10% of either leg's shown size; the replay's $0.05 a contract fee on
  each leg; a spread is marked at the long bid minus the short ask. Closing is one order, both legs.
  From 14:30 New York on the day before expiry the House closes it at those marks; nothing is held
  into expiry day. One closed spread is one closed trade for the evaluator, the allocator and the
  family record (the design's `book.spread` row).
- **V4. The replay** (`league/options_replay.py`): a vertical replays on the options history with
  the same fill rules as V3 (the bars' estimated touches where no OPRA quote was recorded, the
  recorded quotes where one was). Acceptance: a founder's replay result reproduces by hand on two
  sampled spreads.
- **V5. The founders.** Six or more spread strategies, each a distinct mechanism and its own
  family, written from the House's own inputs, each passing the V4 replay before seating. Starting
  points, for the builders to test and discard freely:
  - trend verticals: a call or put vertical in the direction of the 20-day trend on SPY, QQQ and
    IWM, 7-21 days out, entered on a pullback, closed at 50-70% of maximum gain or 2 days before
    expiry;
  - cheap-vol verticals: buy the vertical when `options_features` shows `atm_iv` under the
    underlying's 20-day realized volatility;
  - earnings drift: a vertical on a megacap the day after its EDGAR earnings filing, in the
    direction of the gap (the earnings feed is recorded since Sept 24);
  - skew: a put vertical when `skew_25d` is extreme relative to its own history, or a call
    vertical when calls are cheap against puts;
  - mean reversion on index ETFs after a 2-sigma day;
  - one long straddle or strangle built from two single-leg buys (long premium only, allowed
    today), as the control that needs no multi-leg route.
- **V6. Seats.** The options desk gets 8 more seats (16) while spreads are new, taken from desks
  whose 7-day forward record is negative, or through the forward-first run's seat rules if its F3
  is live. A spread founder is never displaced before its desk's evidence clock has run from its
  first fill.
- **Acceptance before 13:25Z:** the release carrying V1-V6 promoted and watched; six or more
  spread agents seated with replay passes on record; one shadow spread order accepted and resting
  or filled in the first session hour.

### W. The watch, Friday Sept 25, 13:30-20:00Z (no deploy)

- Every 30 minutes, into the record: spread agents' wakes, intents, shadow orders, fills and
  refusals; single-leg options agents the same; chain rows shown per agent; each spread's mark
  and the net debit paid against the mid; any error alert.
- Bugs are written down with the evidence and fixed after 20:05Z, unless one freezes a book or
  corrupts evidence, in which case roll back.
- At the close: the scoreboard rows, and each spread family's record (closed spreads, W_paper,
  replay), with which families meet O4.

### G. Real spreads (Wave 2; build during the session, deploy after 20:05Z Friday)

- **G1. The gateway's multi-leg route** (`gateway/lib/caps.mjs`, `router.mjs`; protected). Admit
  exactly the debit vertical and nothing else: `order_class: "mleg"`, two legs, one underlying,
  one expiry, one right, ratio 1:1, the long leg the dearer contract (the lower call strike, the
  higher put strike), `buy_to_open` with `sell_to_open` together on an open and `sell_to_close`
  with `buy_to_close` together on a close, a positive limit on an open, `day`. Metered at maximum
  loss: net debit × 100 × quantity against the $75 order cap and the day cap; a close is metered at
  zero. A short leg anywhere else, a credit, a third leg, a lone `sell_to_open`, or a spread whose
  long leg is not the dearer is refused with the reason. The existing single-leg rules stay. Tests
  in `gateway/test/`; an adversarial review before deploy; the gateway reads `option_spreads_real`
  from a gateway variable set in the same deploy that flips O1, never before.
- **G2. The real book's spreads** (`league/book.py`; protected; the design's section on the book's
  negative leg). The real account holds a short leg as a negative position only inside a spread the
  book knows; reconciliation matches legs by spread; an unmatched short leg is an error alert that
  closes the whole spread with one multi-leg order at once. The venue's per-leg fills are adopted
  into one `book.spread` row.
- **G3. Assignment and expiry.** No spread is held into expiry day (closed from 14:30 New York the
  day before). If the venue ever reports an assignment or an exercise, the House closes what
  remains at once, with an error alert and a record row. The first real multi-leg order an agent
  sends also answers the design's open question of whether the cash account accepts `mleg`: a
  refusal is recorded and the switch goes back to `false`; it is never retried by hand.
- **G4. The money set** (O1-O5): one digest change, ratified within a minute of promotion. O1 stays
  `false` in this deploy unless a family already meets O4; flipping it later is the second digest
  change.
- **Acceptance:** G1-G3 deployed and verified with the switch off (a spread intent refused by the
  book with the switch's reason); O1 flipped only on O4's evidence, recorded with the family's
  numbers.

### M. Monday Sept 28, 13:30Z

- The first real spreads, watched every 30 minutes: orders, per-leg fills, the book's spread row,
  reconciliation, the gateway's metering, the mark. A failure of any leg-matching or metering check
  sets O1 back to `false` by rollback, and the report says what happened.

### B. Bugs, and D. Docs

- Every bug found gets a regression test. README (the options section and the grant's digest
  history), operations (the spread switch, the shadow book, assignment handling), `CONTRACT.md`,
  `league/README.md`, the run record and the memory note are current at the end; merged worktrees
  and branches removed; #210 closed as merged or superseded.

## The scoreboard

| # | Metric | Baseline (Sept 25) | Target |
|---|---|---|---|
| 1 | Options agents living; distinct options families | 7; 2 | ≥ 14; ≥ 8 |
| 2 | Options intents and fills in a session (practice) | a handful of single contracts | ≥ 20 spread intents, ≥ 5 shadow spread fills on Friday |
| 3 | Median underlying price of contracts traded | about $10-30 (F, SOFI, T) | ≥ $100 (index ETFs and megacaps) |
| 4 | Median bid-ask spread paid, as a share of premium or net debit | up to 20% | ≤ 8% |
| 5 | Spread families meeting O4 by Monday 13:00Z | 0 | ≥ 1, or the numbers why not |
| 6 | Real options activity Monday | one draining contract | real spreads by an O4 family, or the numbers why not |
| 7 | Harness incidents this run caused (a frozen book, a rollback, a deploy in session) | — | 0 |

## Lessons (read before starting)

- Everything in the forward-first plan's "Lessons to read before starting" applies.
- The shared Alpaca practice account must never see a multi-leg order: a negative leg freezes every
  practice agent until it is gone.
- Option quotes are OPRA via Alpaca; replay touches are estimated around prints where no quote was
  recorded, and a replay row says which (`quote_source`).
- Alpaca auto-exercises a contract in the money by $0.01 at expiry; a cash account cannot carry
  the result. Nothing is held into expiry day.
- Evidence stays honest: a shadow fill that would not have happened at the venue is a defect, and
  practice results never stand in for real ones on the board.

## Done

- The Friday watch and the Monday first-hour watch are in the record with the scoreboard at T0,
  Friday's close and Monday 14:30Z;
- the spread path is live on practice, and on real money for any family that met O4 (or the
  numbers why none did);
- tests and CI green; no harness incident caused by this run; the forward-first run never blocked
  or clobbered;
- docs, memory and the repo current and clean; the report delivered with the owner's next
  decisions (a larger options stake, credit spreads, a second practice account).

## The /goal message

```
/goal Execute docs/goals/LTCM_OPTIONS_DESK.md (branch goal/options-desk-2026-09-25; merge it to main first) autonomously with no deadline, beside the forward-first run, until its Done list holds.

- Direction: make level-3 options a real instrument for the swarm. Debit verticals on liquid underlyings trade on practice through today's session (by 13:25Z), and on real money from Monday's open for any family whose record earns it. Be bold inside the envelope: I accept volatility and losses on Alpaca.
- Coordinate with the forward-first run exactly as the plan's "Coordination" section says: read its record before every merge, never edit a file its current wave owns, one deploy at a time, no deploy 13:25-20:05Z on a trading day, and ratify earned-live-20260921 after any promotion only when every changed money rule is a row of one of the two plans' tables.
- Authority: the plan's "Authorized" list, including the money table O1-O5 (at most two digest changes, each re-ratified within a minute of promotion) and the gateway's multi-leg route for debit verticals only. Nothing in "Not authorized": no credit spreads, no naked shorts, no legging, no multi-leg orders on the shared practice account, no test orders, no cap raises. No owner steps needed.
- Method: builders in worktrees; adversarial review of the gateway, book and allocator changes; watch today's session every 30 minutes with no deploy; fix bugs after 20:05Z; report Friday's close and Monday's first hour with the scoreboard and my next decisions.
```

And one line to paste into the forward-first session so it knows the other run exists:

```
A second run is executing docs/goals/LTCM_OPTIONS_DESK.md beside yours. Follow its "Coordination" section: before each merge and deploy, read its record (docs/runs/<date>-options-desk.md on its run branch), don't edit files its current wave lists as owned, one deploy at a time, and after any promotion that leaves the grant inactive, ratify only if every changed money rule is in one of the two plans' tables.
```
