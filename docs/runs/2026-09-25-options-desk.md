# The options desk — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the options-desk plan](../goals/LTCM_OPTIONS_DESK.md) autonomously, with no deadline, beside the
forward-first run ([its record](2026-09-25-forward-first.md) on `run/forward-first-2026-09-25`),
until its Done list holds.

## The clock

- **T0:** 2026-09-25T05:50:40Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Windows:** Wave 1 (V, spreads on practice) deploys between 10:00Z and 12:25Z Sept 25, after the
  forward-first run's Deploy A and its watch. Friday's session 13:30-20:00Z is watched every 30
  minutes with no deploy. Wave 2 (G, real spreads switched off) deploys after 20:05Z Friday, after the
  forward-first run's Deploy B. The first real spreads, if a family meets O4: Monday Sept 28 13:30Z.

## The owner's message (Sept 25, 2026, 05:47Z)

- The /goal text is the plan's last section; the session received it cut at the start ("section
  says: ..."), so the plan's own copy of the message is the one followed.
- **Read as:** the owner's grant of the gateway's multi-leg route for debit verticals, and of real
  debit verticals once O4's line is met, is specific to this run and takes precedence over the
  forward-first plan's general "multi-leg option orders on either account" line, which this run's
  plan inherits otherwise. Everything else in both "Not authorized" lists holds: no credit spread,
  no naked short, no legging, no multi-leg order on the shared practice account, no test order, no
  cap raise, no owner step.

## The owner's amendment (Sept 25, 2026, received about 06:01Z)

The owner changed course with a bigger mandate and a deadline; it amends the plan. The message
arrived with parts of lines cut off; where a word is missing the reading below says what it was
taken to mean.

- **Today's goal:** fully built, tested and deployed before 13:25Z; the whole US session watched
  (13:30-20:00Z); at 20:00Z at least **3 options agents with positive realized P&L on at least 2
  closed structures each, and a positive total for the options desk's closed structures on the day**,
  measured on conservative fills. If missed, the report says why with numbers. Never force a trade,
  plant an intent or relax a fill rule to hit it.
- **Cut order** (if time runs short, in this order; the rest after 20:05Z): (a) the gateway's
  multi-leg route and the structure-aware book; (b) at least ten replay-passed founders seated on the
  options desk, with seats freed for them; (c) structure PARAMS in the lab and the replay; (d) the
  real-money path.
- **1. Practice on the real Alpaca practice account** (the owner verified: options level 3, margin,
  options buying power about $98.8k; all strategies may share it). The gateway gets a multi-leg route
  for `alpaca-paper` admitting every level-3 DEFINED-RISK structure (debit and credit verticals, iron
  condors and iron butterflies, long butterflies, calendars and diagonals, long straddles and
  strangles), metered at maximum loss; naked short legs, ratio spreads with an uncovered leg and
  legging in or out are refused; the real `alpaca` venue stays refused until O1 flips. The book becomes
  structure-aware (one position per structure, legs matched on every reconcile, one closed trade a
  structure; an unmatched short leg closes the whole structure at once with an error alert; nothing
  held into expiry, on the practice or the real book). `league/book.py` is taken right after the
  forward-first run's H4 merges, through its record. **If the book cannot be ready, the House's shadow
  book is today's fallback** so options agents trade all session, and the practice account follows
  after 20:05Z. Record whether the practice account accepts each structure and how it reports per-leg
  fills (read: the practice account is margin and the real one is cash).
- **2. Built to be profitable:** structures that close within the session or the next day (0-7 day
  expiries on SPY, QQQ and IWM, $1 strikes) with profit targets and time exits in each strategy;
  structural edges (selling rich implied volatility through defined-risk credit structures, debit
  verticals with the intraday and multi-day trend, long straddles only when implied is cheap against
  realized); every founder passes the replay on the options history store with conservative fills
  (long legs at the ask or worse, short legs at the bid or worse, the fee on every leg), ranked by
  out-of-sample replay growth; at least ten founders across distinct mechanisms, one family each
  (debit verticals on index ETFs, iron condors, cheap-IV long straddles, post-earnings drift verticals
  from EDGAR dates, skew trades, calendars into term-structure kinks ...), fed by the chain's quotes,
  greeks and IV, `options_features`, earnings dates and the underlyings' bars; options-desk seats
  freed from desks whose 7-day forward record is negative without breaking the forward-first run's rules.
- **3. The swarm improves itself:** structure type, width, days to expiry, entry delta, profit target
  and exit rule become mutable PARAMS, so the lab breeds structures and not only signals; research on
  options agents reads fills, marks and refusals during the session; intraday edits run through the
  existing edit replay; the families' records are logged every 30 minutes; at the close mechanisms and
  structures are ranked by realized P&L and the ranking goes to the foundry and the lab.
- **4. Real money follows proof, fast:** Monday 13:30Z real debit verticals for a family meeting O4, O1
  flipped by a ratified digest change. Credit spreads and condors on the real cash account once a
  family's practice record plus replay meets O4 and the first real order shows the account accepts
  the structure, metered at maximum loss (width minus credit, x100): the second digest change. A
  structure whose maximum loss cannot be computed is refused. Sizing by the allocator's family ladder
  inside the $75 order cap; never a cap raise, deposit or transfer. **Held for the owner's
  confirmation before it is used (Monday):** the real-money credit-structure grant, because the lines
  that carry it arrived cut.
- **5. Honest evidence:** the practice haircut conservative and measured (O5); Alpaca's practice fills
  are optimistic; a structure counts once; a practice result never stands in for a real one.
- **6. The watch:** every 30 minutes, no deploy 13:25-20:05Z, a rollback only if a book is frozen or
  evidence corrupted. At 20:00Z the report: the target's verdict, every options agent's realized P&L
  and closed structures, which structures and mechanisms made or lost, bugs, what ships after 20:05Z,
  and the owner's decisions for Monday's real-money open.

**What changes in the plan's rules:** the plan's "Not authorized" line "multi-leg orders on the shared
practice account" and "a credit spread" are lifted for PRACTICE by the owner's amendment (defined-risk
structures only). "No naked shorts, no legging, no ratio spread with an uncovered leg, no test orders,
no cap raises" stand. On real money nothing changes until the owner confirms item 4's credit grant.

**How the run meets it (06:02Z):** one representation for every structure: a structure is held as ONE
long option-class instrument priced at its net value plus its collateral (zero for a debit structure,
the widest wing for a credit one), so its cost is its maximum loss, the caps meter it exactly, it is
bought to open and sold to close, a flat sale is one closed trade, and no book holds a negative leg.
Two tracks: **S** (the House's options shadow book, all structures; ships today whatever happens) and
**P** (the gateway's multi-leg route for `alpaca-paper`, the adapter's multi-leg orders and fills and the
structure-aware practice book; ships today only if built, reviewed and CI-green by about 11:30Z, else
after 20:05Z with Monday's open as its first session). A config switch says which venue the options
desk's structures go to, so the choice is made at the deploy and undone by a rollback.

## Coordination with the forward-first run

Read before every merge and deploy: the forward-first record's "Coordination with the options-desk
run" section (its current wave, file owners and announced deploys).

**Three runs (the owner's message, about 06:04Z):** a third run executes `docs/goals/LTCM_KALSHI_SCALE.md`
(branch `goal/kalshi-scale-2026-09-25`; record `docs/runs/<date>-kalshi-scale.md` on its run branch). The
coordination rules now span three runs: before each merge and deploy, read all three records (current
waves, file owners, announced deploys); one deploy at a time across the three, none 13:25-20:05Z on a
trading day, and **none while a real Kalshi family's game is in play**, except a rollback; after any
promotion that leaves the grant inactive, ratify `earned-live-20260921` only if every changed money rule
is a row of one of the THREE plans' tables (forward-first, options desk, Kalshi scale), else roll back and
record why. The Kalshi run owns: Kalshi strategies and founders in `league/strategies/`, the Kalshi desks'
seats in `league/niches.json` (with forward-first's F3), `league/feeds.py`, `ltcm/data/sports.py`,
`ltcm/data/weather.py`, `league/shards.py`, new capacity scripts, the gateway's new `web_fetch` route,
`LEAGUE_HOSTS` additions, and after forward-first's Deploy B the scale rule in `league/live_trading.py` and
`league/grants.py`. **The gateway:** its `web_fetch` route and this run's multi-leg route both touch
`gateway/`; whichever deploys the gateway second rebases on the first and re-runs the gateway tests. This
run's founders live in `league/seeds/` (options only) and its seats in the `alpaca-options` row, so no
file of the Kalshi run's is touched.

**Four runs (the owner's message, about 06:15Z):** a fourth run executes `docs/goals/LTCM_JEV_SENSES.md`. It
owns only the Jev files (`league/jev.py`, `sensors.py`, `triage.py`, `hypothesis_memory.py`, `exposure.py`,
`semantic_lab.py`, `jev_features.py`, `scripts/jev_lab_eval/`, `gateway/lib/typesafe.mjs`, `config.json`'s
`jev` block), lands small hooks into `research_gate.py`, `feeds.py` and `lab.py` only after the waves that
own them merge, and changes no money rule. One deploy at a time across the four runs; any gateway deploy
rebases on the others' gateway changes and re-runs every gateway test. No file of this run's overlaps (this
run's `config.json` change is its own new `options_structures` key).

**This run's current wave, file owners and deploys (kept current):**

| Wave | State | Files owned |
|---|---|---|
| 1 (V, the practice deploy; Track S and, if ready, Track P) | building | Track S, new: `league/structures.py` (every defined-risk structure, held as one position), `league/options_shadow.py`, `league/options_desk.py` (seating the structure founders), structure founders in `league/seeds/` (new files and their `SEEDS` rows), their tests; `league/verticals.py`; `league/options_replay.py`; `league/service.py` (the options-shadow book beside kalshi-shadow); `league/config.json` (a new `options_structures` key only); `league/house.py` `_chain` and new options hooks outside the forward-first run's listed regions (the structure intent at wake, a structure agent's book, the structures in a wake's context, the expiry-day close); the `alpaca-options` row of `league/niches.json`; `league/CONTRACT.md` "Options". Track P: `gateway/lib/caps.mjs`, `gateway/lib/router.mjs`, `gateway/test/` (the multi-leg route, practice only), `ltcm/adapters/alpaca.py` (multi-leg orders and per-leg fills), `league/book.py` (structure-aware; only after the forward-first run's H4 has merged) |
| 2 (G, real structures, switch off) | after 20:05Z | `league/allocator.py` and `league/constitution.py` (O1-O5), only after the forward-first run's Wave 1 has merged; the gateway's real-venue metering |

- **Announced deploys:** Deploy V (practice; no money-digest change expected; the House release and
  the gateway's practice multi-leg route, the gateway first) between 10:00Z and 12:25Z Sept 25, never
  within 30 minutes of the forward-first run's Deploy A; its exact start and end are written here.
  **D-J1 slot (the Jev run, asked 06:28Z):** open for 12:15-12:55Z only if V's watch ends by 11:45Z;
  otherwise Saturday after Deploy B and Deploy G. State: pending V. Deploy G (the gateway's multi-leg route and the book's spreads, switch off;
  money-digest change 1 of 2) after the forward-first run's Deploy B, not before 20:05Z Sept 25.

**Requests to the forward-first run (06:05Z; also a comment on its PR #297):**

1. **One call line in the population step**, right after `self.enroll()` in `league/house.py` (your
   Wave 0 "births pass" region, and "births" in Wave 1): `options_desk.seat_founders(self)`. The logic
   lives in this run's new `league/options_desk.py`: it births at most one structure founder a tick
   until the options desk's founders are seated, and when the league is full it takes the seat of the
   first resident `_displaceable` offers on a desk whose 7-day forward record is negative, so every
   protection of yours holds (never real money, a winner, one inside its grace or evidence clock, a
   proven family's member, or one holding a position while its market is shut). It must be live in
   Deploy V (10:00-12:25Z today). May this run add the line once your Wave 0 is on main, or will you
   carry it in yours? Either answer in your record's coordination section is enough.
2. **`league/book.py`** passes to this run once H4 is on main (the owner's amendment): please write
   the merge time in your record.
3. **Deploy V** may include a gateway deploy (the multi-leg route for `alpaca-paper` only; no money
   digest change), in the same 10:00-12:25Z window, never within 30 minutes of your Deploy A.
5. **(06:40Z, after the Kalshi run's finding that health's `seats.displaceable` is 0 even for an evidenced
   newcomer: 128/128 living, 71 waiters at 05:43Z)** an explicit seat rule inside `options_desk.py`: one
   practice resident retired per tick while a structure founder is owed, at most 12 in all; first the
   options desk's own practice residents on a family with a negative pooled forward record whose own
   7-day practice record is <= 0 (krasker-10 -0.174, krasker-21 -0.145, krasker-13 -0.111, krasker-19
   -0.051; options-pullback pooled -0.598), then practice residents of Alpaca desks whose desk 7-day
   practice record is negative (alpaca-crypto-majors -0.059, alpaca-index-etfs -0.032, alpaca-open
   -0.023 at 06:36Z) whose own record is <= 0 or who never traded, weakest first; never real money, a
   winner, a proven family's member, one holding a position while its market is shut, one under 2 hours
   old, or a Kalshi desk. Consent asked on PR #297 by 10:00Z.
4. **After your Wave 1** (not before): Wave 2 here maps the `options-shadow` practice book into the
   evidence the allocator and the family records read (`PAPER_BOOK` in `allocator.py` and
   `families.py`), a few lines, for O4.

**The forward-first run's answers (its record, 06:07Z):** (1) this run adds the call line
`options_desk.seat_founders(self)` after `self.enroll()` itself once Deploy A is on main, one line, every
`_displaceable` protection inherited; their F-seats builder keeps it; (2) `league/book.py` passes to this
run the moment H4 merges (time written in their record); their Wave 1 then touches `book.py` only in two
small hunks (M2's refusal text, M6's Alpaca maker/taker `_liquidity`) rebased onto this run's; (3) Deploy V
with the gateway's practice route in 10:00-12:25Z agreed; they will not deploy 09:30-13:25Z; (4) the
`PAPER_BOOK` mapping for `options-shadow` after their Wave 1. Their Deploy B moved to a quiet window after
the Friday-night MLB slate (about 05:00-15:00Z Saturday Sept 26), so this run's Deploy G shares that window,
one deploy at a time, its start written here first.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | PR #299 merged 06:15:46Z |
| S1 | The options shadow book (`s1/shadow` 01f3da5) | built 06:59Z: `OptionsShadowBroker` (fills only on a strictly newer quote, at the structure's ask/bid, at most 10% of any leg's shown size shared across orders and persisted, session only, day orders, $0.05 a contract a leg, marks at the bid, expiry net settles at intrinsic or far-leg value, never written off at zero), `service.py` book `options-shadow` ($100,000 practice cash), `config.json` `options_structures`, `fees.py` structure fees on this venue, `book.py` settle/ledger-id/cross guard; 43 own tests, 413 across neighbours OK; its own review's 3 serious findings fixed. Follow-ups asked 07:00Z: a structure may open on its expiry day until 14:30 NY (0 DTE; `Book.check` refused it), and a zero bid marks a structure at zero (the book kept the last mark) |
| H | Machine load | 07:03Z: the shared Mac at load ~49 on 8 cores, 0 GB free (four runs); every builder here limited to one test or replay process at a time; full suites to CI |
| P1 | The gateway's multi-leg route (`p/gateway` 5bdf70e) | built 06:26Z (180/180 gateway tests); adversarial review 06:49Z: **SHIP** (729 real adapter bodies of today's practice traffic pass unchanged; the real venue identical to before across 1,216 tricky cases with `OPTION_STRUCTURES_REAL` off; the classifier agrees with `structures.py` on 134,664 leg sets). MAJOR for Track P: Alpaca refuses a one-order close of a calendar ("mleg uncovered short contracts not allowed"), very likely also straddles, strangles and diagonals, so the practice account admits only the five types whose close is covered (verticals, iron condors, iron and long butterflies); the others trade on the shadow book. MINOR before the real switch: a real close reserves one micro-dollar and trusts the venue to refuse closing legs not held (check held legs first); an overstated comment about the sign convention's evidence |

## The scoreboard at T0

Read-only from the box's ledger at 06:14Z Sept 25 (`q_base.py` in the session scratchpad), the Sept 24
session (13:30-20:00Z) as the day's baseline.

| # | Metric | Baseline | Target |
|---|---|---|---|
| 1 | Options agents living; distinct options families | 7 (all `options-pullback`); 21 ever (16 pullback, 5 breakout) | >= 14; >= 8 (the amendment: >= 10 founders, one family each) |
| 2 | Options intents and fills in a session (practice) | 117 wakes, 28 intents, 27 practice fills (+2 real), all single contracts | >= 20 structure intents, >= 5 structure fills |
| 3 | Median underlying level of contracts traded | median strike $14 (AAL 14 fills, RIVN 4, SOFI 4, PFE 2, SNAP 2, T, F, VALE) | >= $100 (SPY, QQQ, IWM) |
| 4 | Median bid-ask paid, a share of premium or net | single contracts at $0.05-0.60 (spreads up to 20%) | <= 8% |
| 5 | **The amended target at 20:00Z:** agents with positive realized P&L on >= 2 closed structures; the desk's closed-structure total | Sept 24 single contracts on practice: 16 closes, +$1.97 in all; positive on >= 2 closes: krasker-11 (+$14.00 on 3), krasker-6 (+$14.00 on 3), krasker-14 (+$12.00 on 4); krasker-16 +$16.97 on 1 | >= 3 agents, each >= 2 closed STRUCTURES, positive; desk total positive |
| 6 | Structure families meeting O4 by Monday 13:00Z | 0 | >= 1, or the numbers why not |
| 7 | Real options activity Monday | krasker-14's two contracts (AAL, $34), draining | real structures by an O4 family, or the numbers why not |
| 8 | Harness incidents this run caused | - | 0 |

## Progress notes

## Watch log

## Report
