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

**This run's current wave, file owners and deploys (kept current):**

| Wave | State | Files owned |
|---|---|---|
| 1 (V, the practice deploy; Track S and, if ready, Track P) | building | Track S, new: `league/structures.py` (every defined-risk structure, held as one position), `league/options_shadow.py`, `league/options_desk.py` (seating the structure founders), structure founders in `league/seeds/` (new files and their `SEEDS` rows), their tests; `league/verticals.py`; `league/options_replay.py`; `league/service.py` (the options-shadow book beside kalshi-shadow); `league/config.json` (a new `options_structures` key only); `league/house.py` `_chain` and new options hooks outside the forward-first run's listed regions (the structure intent at wake, a structure agent's book, the structures in a wake's context, the expiry-day close); the `alpaca-options` row of `league/niches.json`; `league/CONTRACT.md` "Options". Track P: `gateway/lib/caps.mjs`, `gateway/lib/router.mjs`, `gateway/test/` (the multi-leg route, practice only), `ltcm/adapters/alpaca.py` (multi-leg orders and per-leg fills), `league/book.py` (structure-aware; only after the forward-first run's H4 has merged) |
| 2 (G, real structures, switch off) | after 20:05Z | `league/allocator.py` and `league/constitution.py` (O1-O5), only after the forward-first run's Wave 1 has merged; the gateway's real-venue metering |

- **Announced deploys:** Deploy V (practice; no money-digest change expected) between 10:00Z and
  12:25Z Sept 25, never within 30 minutes of the forward-first run's Deploy A; its exact start is
  written here first. Deploy G (the gateway's multi-leg route and the book's spreads, switch off;
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
4. **After your Wave 1** (not before): Wave 2 here maps the `options-shadow` practice book into the
   evidence the allocator and the family records read (`PAPER_BOOK` in `allocator.py` and
   `families.py`), a few lines, for O4.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | PR #299 |

## Progress notes

## Watch log

## Report
