# Level-3 options: debit verticals, a design against the code as it is

> **Status (Sept 23, 2026, workstream O of [the learn-and-unblock plan](../goals/LTCM_LEARN_AND_UNBLOCK.md#o-level-3-options-a-design-and-a-branch-not-a-deploy)).**
> A design and a pushed, unmerged branch (`w2-options/design`), not a deploy. Nothing here runs.
> The pure pieces are built and tested in `league/verticals.py` (imported by nothing in the House);
> everything else in this document is a plan, with the file and line it changes. Line numbers are
> `origin/main` at `b40e737`. It follows section B of
> [the Alpaca stocks and level-3 options proposal](../proposals/2026-09-23-alpaca-stocks-and-level-3-options.md):
> B0 (the gateway refuses multi-leg orders, #187) is deployed; this is B1, debit verticals on
> practice; B2 (real money, maximum-loss metering) needs the owner's ratification and is described
> where it touches B1.

## Owner steps, first

1. **A second Alpaca practice account, with its keys in the gateway.** The practice book reconciles
   to the shared practice account, and a vertical's sold leg is a negative position that
   `Book._adopt_the_venue` refuses to adopt (`league/book.py:2184-2187`: "a negative baseline
   leaves phantom holdings"). A spread on that account, from anyone, freezes every Alpaca practice
   agent for as long as it is open (new entries refused, exits allowed: `reconcile`, `book.py:2130-2161`,
   `ADOPT_AFTER` 3 at `book.py:74`). So the first multi-leg order, and B1's whole practice run,
   need a practice account no running House reconciles. Create it at Alpaca, place its key pair in
   the gateway as a fourth venue (`gateway/lib/router.mjs:48-53`: `VENUES` and `PAPER_VENUES` gain
   `alpaca-paper-2`; never metered, like the first), and name it in `league/config.json` for the B1
   House only.
2. **Settle the three unknowns with the first PRACTICE multi-leg order, never a real one:**
   - does the practice account accept `order_class: "mleg"` orders and report fills per leg
     (`GET /v2/account/activities/FILL`, one row a leg with the leg's OCC symbol), and what
     `order_id` a leg's fill carries (its own child order's, or the parent's);
   - does the real cash account at level 3 accept them (Alpaca's docs list "buy a call spread /
     buy a put spread" under level 3 and do not say cash accounts are excluded; a `GET
     /v2/account/configurations` and one refused-by-cap order through the gateway can answer it
     without spending, once B2's metering exists);
   - how Alpaca handles early assignment of a short leg in a cash account (whether the long leg is
     exercised against it, whether the account is left short a hundred shares, and what
     activity rows say so).
3. **Later, B2:** ratify `option_max_position_usd` meaning maximum loss and the gateway's
   maximum-loss metering (below), which moves the money digest. Long premium only on the real cash
   account stays the rule until then.

## 1. What B1 admits: the debit vertical

The proposal's rules, made exact:

- Two option contracts on one underlying, one expiry and one right (two calls or two puts), one
  bought and one sold in equal numbers.
- **The long leg is the dearer contract: the lower strike of two calls, the higher strike of two
  puts.** That is what makes the order a net debit and bounds its loss at the debit. It is the
  proposal's "long leg nearer the money" exactly when both legs are out of the money (the usual
  case inside the chain's 20% moneyness filter, `house.py:379`), and it is the rule that needs no
  spot price in every case: with both legs in the money the higher call strike is nearer the money,
  and the long lower-strike call is still the debit spread. The same two legs the other way round
  are a credit spread (a written option with a hedge) and are refused.
- Opened and closed only as **one** multi-leg order (`order_class: "mleg"`). Never a leg on its own,
  never a leg through the single-contract path.
- Closed before expiry day. Alpaca auto-exercises a contract in the money by $0.01 or more, and an
  exercised or assigned leg turns a bounded spread into a hundred shares the cash account cannot
  carry (decision 28, `docs/design/2026-09-19-architecture.md:360-366`).
- Counted as **one** closed trade, never a leg each.

### The intent schema

A strategy returns, beside its single-leg intents (`CONTRACT.md` "Options"):

```python
{"spread": "debit_vertical", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.35,
 "legs": [{"occ": "F261016C00013000", "role": "long"}, {"occ": "F261016C00014000", "role": "short"}],
 "reason": "..."}
```

- `spread`: the only value B1 admits is `"debit_vertical"` (`verticals.SPREADS`). Credit verticals,
  condors and calendars are B3.
- `side`: `buy` opens the spread, `sell` closes it, as for one contract. The legs' own sides follow
  from it (a close reverses both), so a strategy cannot write a close whose legs point the wrong way.
- `legs`: exactly two, each named as any option is (`league/venues.py:110-145` `instrument_for`:
  an `occ` code, or `symbol`/`expiry`/`strike`/`right`) plus its `role`, `long` or `short`. A leg
  carries no `side`, `quantity` or `ratio`: a vertical is 1:1.
- `quantity`: whole spreads, at least one.
- `type`/`limit_price`: a limit order only, at the **net price a share**: on a buy the most the
  spread may cost (its debit), on a sell the least the close must receive. Whole cents. A spread
  has no touch to take, so there is no market order.
- `reason`: as every intent (`options_replay.py:217-218`).

`league/verticals.py` `parse_vertical(venue, spec)` is this schema's parser and validator; the
refusals it gives (a credit spread, mixed underlyings/expiries/rights, one strike twice, a third
leg, a stock or a Kalshi market as a leg, a market order, a debit at or over the width, a fraction
of a spread, no reason) are its tests in `league/tests/test_verticals.py`.

### The order it becomes

`verticals.mleg_body` (Alpaca's documented shape, the one `gateway/test/caps.test.mjs:177-185`
refuses today): no top-level `symbol`, `order_class: "mleg"`, `qty` spreads, `type: "limit"`,
`limit_price` the net (a credit negative on a close: Alpaca's documented sign, **unverified**),
`time_in_force: "day"`, `client_order_id` the intent id, and `legs` of `{symbol (OCC), ratio_qty
"1", side, position_intent}`: `buy_to_open`/`sell_to_open` on an open, `sell_to_close`/
`buy_to_close` on a close.

## 2. Maximum loss, and what the caps mean for a spread

- **Maximum loss** = net debit x 100 x quantity, paid in full when the spread is opened on a cash
  account. It is all a debit vertical can lose, however far the underlying moves, provided both legs
  are closed together before expiry day (`verticals.max_loss`).
- **Maximum gain** = (width - net debit) x 100 x quantity (`verticals.max_gain`). A debit at or
  over the width can never pay and is refused at the parser.
- **The order cap** (the gateway's $75, `gateway/wrangler.jsonc:53`; the book's `max_order_usd`,
  `book.py:365`; the rung's `max_order_usd`, `constitution.py:180-190`) bounds the maximum loss of
  one opening order: what it can spend, exactly as a long option's premium x 100 does today
  (`caps.mjs:163-177` `optionNotional`; `book.py:1101-1110`).
- **The position cap** (the rung's `max_position_usd`; on real Alpaca also half the account's
  equity at the ask, `house.py:864-881` `_real_limits`) bounds the maximum loss of the spreads held
  plus this one (`verticals.cap_refusal`, `held_max_loss`). Neither cap is the gross of the two
  legs' premiums, and neither is the width (the margin view, which a cash account never uses).
- **A close is never metered.** It takes risk off, as `ltcm/risk.py:262-266` `reduces_exposure`
  lets an exit through `rule_order_notional` (`risk.py:552-561`) and `rule_cash` (`risk.py:564-577`).
- **What a spread is worth to a seat.** On practice, the rung-1 caps ($100 a position, $75 an
  order, `constitution.py:180`) admit two $0.35 spreads an order. On a real options bunt (staked
  $80, shown $39.99 a contract, `CONTRACT.md:115-128`) a spread's debit fits at $0.39 a share and
  not at $0.40 (`test_verticals.Arithmetic`). The chain's affordability filter (`house.py:1089`,
  `afford = min(order, position) / 100`) must then admit the far leg whatever its ask: what is
  affordable is the net, not each leg.

## 3. One spread is one closed trade

Today a trade is a position gone flat: `allocator.closed_trades` (`allocator.py:157-174`) counts a
`book.fill` row with `realized` set and `flat` true, and `Evaluator.trade_returns`
(`evaluator.py:314-352`) keys a running position by `market_id/symbol/right/expiry/strike`
(`evaluator.py:338-339`) and closes it on `flat`. The book stamps `realized` and `flat` on a SELL
only (`book.py:1406-1416`). A spread closed as two leg rows would be read as one trade on the long
leg's sale (realized, flat) and nothing on the short leg's buy-back, or, if the short leg's opening
sale were booked as a sale, as a "closed trade" the moment the spread opened. Neither is right, and
the proposal's rule is one spread, one trade (and never a leg each: "a condor would count as 4 and
manufacture eligibility").

**The design:**

- The book records a spread's execution as one `book.fill` row per leg, as the venue reports it
  (the ledger stays a record of what happened), and each leg row carries `spread: <key>`
  (`verticals.DebitVertical.key`, `spread:F:alpaca-paper:2026-10-16:call:13/14`) and
  `realized: None`, `flat: None`. One further row, `book.spread` (a new `ledger.KINDS` entry, public
  like `book.fill`), is appended when the spread is flat on both legs, carrying the spread's
  `realized` (the close's net credit less the open's net debit, fees of all four leg fills
  included) and `flat: true`.
- `closed_trades` and `trade_returns` count `book.spread` as they count a flat sale and ignore leg
  rows that carry `spread` (one added condition each; `allocator.py:170`, `evaluator.py:343`).
  `verticals.count_trades` is the reference for the counting itself (per-leg fills folded into
  per-contract positions; one trade each time a group that held a long and a short leg is flat on
  every contract; partial fills, a leg closed first and a close in several orders all count once;
  a lone contract counts nothing).
- The real-money haircut (`allocator.py:150-153`) applies once to the spread's net, not to each leg.

## 4. Exit rules

- **Closed as one multi-leg order**, `side: "sell"` on the same two legs, net credit as the limit.
  A strategy that sells one leg alone is refused (the House parses the single-leg intent against a
  contract held as part of a spread: `house.py:1315-1330` gains a check against the book's spread
  holdings). The House's exit slicing (`Book` `ExitPlan`, `league/README.md` "book.py") is by
  spread, never by leg.
- **Closed before expiry day.** The House's expiry rule sells a long option at the bid from 14:30
  New York on its last day (`house.py:2768-2791`). A spread is closed **the session before**
  expiry day, from 14:30 New York, at the spread's bid (long bid - short ask), again each tick
  until it is gone: on expiry day itself an in-the-money short leg can be assigned intraday, and
  Alpaca exercises by $0.01. No entry within 2 days of expiry (the single-leg rule is "after
  today", `book.py:1139-1140`).
- **A broken spread** (one leg gone: assigned, exercised, or the venue shows one leg only) is
  closed at once by the House at market-open rules, whatever the hour rule says: the remaining leg
  alone is a naked position on a cash account. This is the third unknown's landing place.
- **Wind-down** of a dead agent's spreads is a spread close, in the regular session, as for stocks
  and single options (`docs/operations.md:356-360`).

## 5. The practice-account problem, and the book's negative leg

`Book` has never held a negative position: `Holding.quantity` (`book.py:235-240`) is folded from
fills, `rule_short` (`risk.py:175-189`) refuses a sell beyond the holding, `_ledger_totals`
(`book.py:2043-2053`) and `_venue` (`book.py:1992-2012`) sum signed quantities, and the adapter
already reports a short as a negative quantity (`alpaca.py:228-250`). What changes:

- **Submit.** `Book.submit` takes a `SpreadIntent` (a new frozen dataclass beside `Intent`,
  `book.py:145-185`, holding a `DebitVertical` and an intent id) through its own path: the caps by
  maximum loss (section 2), cash including the four legs' fees, quote age on both legs, the
  specialty (`Limits.asset_classes`), one spread per underlying/expiry/right per agent, and never
  beside a lone contract of the same expiry and right. The single-leg rules (`risk.py`) are not
  run over a leg: the risk layer gains `rule_spread` for the whole.
- **Holdings.** A short leg is a `Holding` with a negative quantity and a negative cost (the
  premium received). `_fill_payload` (`book.py:1375-1425`) computes `realized` on a leg only when
  it is not part of a spread. Marks: a long leg at the bid, a short leg at the ask, so equity
  never flatters an open spread.
- **Reconciliation.** `_reconcile` compares signed positions already; nothing changes for a
  practice book that knows the spread. `_adopt_the_venue` keeps refusing negative adoptions: a
  short leg the ledger does not know is exactly the case that must freeze and be looked at. Hence
  the second practice account for B1's House, and the first House never sees a spread.
- **Expiry.** `expire_options` (`book.py:1934-1960`) writes off a long leg the venue no longer
  shows; a short leg that vanished the same way was exercised against, and the row says so and
  freezes the book (a real-money book) or raises an ops alert (practice).
- **The adapter.** `submit` (`alpaca.py:346-402`) sends `verticals.mleg_body` for a spread intent
  and keeps the long-premium check on single legs; `parse_order` (`alpaca.py:566-596`) reads the
  parent order's `legs` (their `id`s, `filled_qty`, `filled_avg_price`) and `fills`
  (`alpaca.py:462-499`) returns one `Fill` a leg as today, the parent's id in a new `Fill.group`.
  `OrderIntent` (`ltcm/broker.py:226-300`) stays single-instrument; a spread is its own type.

## 6. The gateway's metering (B2, real money, a ratify)

Unchanged for B1 (practice is never metered, `router.mjs:49-51`). For B2:

- `alpacaShapeError` (`caps.mjs:232-248`) admits exactly one more shape, checked before the symbol:
  `order_class: "mleg"`, no top-level `symbol`, `type: "limit"`, `qty` a whole number, two `legs`
  and no more, both standard OCC symbols (`isOptionSymbol`, `caps.mjs:150`) with the same root,
  YYMMDD and C/P, `ratio_qty: "1"` each, and either (`buy` + `buy_to_open`, `sell` + `sell_to_open`)
  with the long leg the dearer strike, or (`sell` + `sell_to_close`, `buy` + `buy_to_close`).
  `ALPACA_ORDER_FIELDS` (`caps.mjs:208-211`) gains `legs`; leg fields are their own set.
- `mlegNotional`: an opening spread is metered at `qty x limit_price x 100`, its maximum loss,
  against `MAX_ORDER_USD_ALPACA` and the day caps; a closing spread is metered at zero but its
  shape is still held, and Alpaca refuses a close of what is not held.
- `option_max_position_usd` (`constitution.py:184-186`) changes meaning to maximum loss, which
  moves the money digest: the grant is re-ratified at the deploy (the runbook in
  `docs/operations.md` "Deploy and roll back").
- Tests beside the existing multi-leg refusals (`caps.test.mjs:171-220`): the $210 spread metered
  at $210 and refused over $75; a $0.70 spread metered at $70 and passed; the written put still
  refused; a credit vertical (short leg dearer) refused; a third leg refused; a close metered at
  zero; `ratio_qty` 2 refused; mixed roots or expiries refused.

## 7. Replay (`league/options_replay.py`)

The desk's rung 0 walks single contracts (`submit`, `options_replay.py:213-269`: OCC only, no
shorts at 248-252; `_Book` positions by OCC, 65-123). For spreads:

- `submit` accepts the schema of section 1 (through the same parser, uploaded beside the module as
  `options_replay.py` is beside `replay.py`), and holds a spread order as one order with two legs.
- A fill needs both legs' estimated quotes met at the net on a later bar (`work`, 178-211): the
  long leg at the worse of the shown and the wider estimated ask, the short at the worse of the
  shown and the wider bid, so a spread's replay cost leans against it as a contract's does; no fill
  unless both contracts printed in the bar (`liquidity`), and no more than 10% of either leg's
  volume.
- Positions are marked at the spread's bid; the expiry offer moves to the session before expiry;
  what is unsold at that bell is written off at the spread's intrinsic value at the last print,
  never at zero for the short leg alone.
- The tape needs both contracts in `contracts` with prints (`options_history.py`); a spread whose
  far leg the history never saw is "not evaluated", not a loss.
- `trade_log` records one row a spread (`_close`, 89-95), so `run_replay`'s counts are spreads.

## 8. The desk brief, and CONTRACT.md

`league/niches.json` `alpaca-options` (line 818; the brief at 843) keeps every sentence about
single contracts and adds, on practice only:

> A DEBIT VERTICAL is the one spread this desk admits (`spread: "debit_vertical"`, two legs of one
> underlying, expiry and right, the long leg the dearer strike, opened and closed as one order at a
> net price). Its most is its net debit x 100 a spread, which is what the caps count; its gain is
> the width less the debit. It is closed the session before expiry, never left to be exercised,
> and one spread counts as one trade. Practice only until the owner ratifies real-money metering.

`league/CONTRACT.md` "Options" (176-207) gains the schema of section 1, the sentence "one spread
is one closed trade, never two", the exit rules of section 4, and, under the bunt limits
(105-135), "a spread's debit x 100 is held to the same number as a contract's premium x 100". Copy
says practice, never paper.

## 9. Test plan

| Layer | Tests | Where |
|---|---|---|
| Pure (built) | parser refusals, arithmetic, caps, order shape, one spread one trade, nothing imports the module | `league/tests/test_verticals.py` (33 tests, green) |
| Book | a spread is one submit and two leg holdings; a lone leg sale refused; caps by maximum loss; marks at bid/ask; reconcile with a negative leg; `book.spread` on flat; expiry-eve close; broken spread closed at once; adoption still refuses an unknown short leg | `test_options.py` `BookRules` (`BookCase`, `FakeBroker` gains mleg fills) |
| Adapter | `mleg_body` sent as given; parent `legs` parsed; per-leg fills grouped | `ltcm/tests/` (recorded responses from the practice order, once seen) |
| House | the schema parsed at `wake`; the chain admits the far leg; the options bunt shown a spread's debit | `test_options.py` `HouseCase` |
| Evidence | `closed_trades` and `trade_returns` count one; the haircut once | `test_allocator.py`, `test_evaluator.py` |
| Gateway (B2) | section 6 | `gateway/test/caps.test.mjs` |
| Replay | fills need both legs; intrinsic write-off; one trade a spread | `test_options_replay.py` |
| Practice run | one expiry and one ex-dividend date on the second practice account before B2 | the run record |

## 10. Estimate

| Piece | Lines (with tests) | Days |
|---|---|---|
| `verticals.py` + tests (built) | 580 | done |
| Book: spread intent, holdings, marks, `book.spread`, expiry eve, broken spread | 450 | 1.5 |
| Adapter + broker: mleg submit, parse, fills | 200 | 0.5 |
| House: schema at wake, chain, limits shown, exits, wind-down | 250 | 1 |
| Evidence: allocator, evaluator, haircut | 100 | 0.5 |
| Replay | 300 | 1 |
| Docs: CONTRACT, niches, README, operations | 120 | 0.5 |
| Gateway (B2) | 200 | 0.5 |
| **Total** | **~2,200** | **5-6 build days**, plus a week on the second practice account |

Inside the proposal's 1,500-2,500 lines and at the top of its 3-5 days: the book's negative leg
and the replay are each larger than the proposal's table allowed, because neither layer has ever
represented a sold contract.

## 11. Unverified

- Everything about Alpaca's multi-leg API as this code base would use it: acceptance on a
  practice account and on a level-3 cash account, per-leg FILL rows and their `order_id`, the
  sign of a credit in `limit_price`, the tick of a net price, and early assignment handling.
- Whether a practice account's `qty` on a short option leg is negative in `GET /v2/positions` (the
  adapter assumes `side: "short"`, `alpaca.py:229`).
- The estimate.

## 12. What this branch holds

`league/verticals.py`: `DebitVertical` (frozen; invariants in `__post_init__`), `parse_vertical`,
`max_loss`, `max_gain`, `cap_refusal`, `fits_caps`, `mleg_body`, `count_trades`, `SPREADS`, `ROLES`.
It imports `league.venues.instrument_for` (the one parser of instrument specs) and
`ltcm.adapters.alpaca.alpaca_symbol` (the OCC builder that exists; `house.py:4838` `occ_symbol` is
a second copy of it, noted and left). Nothing in `league/`, `ltcm/` or `scripts/` imports it, and
`test_verticals.NothingInTheHouseImportsIt` fails the day something does.
