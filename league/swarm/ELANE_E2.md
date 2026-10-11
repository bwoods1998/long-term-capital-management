# Release E2: the swarm breeds share programs for the BETA and EQUITY lanes

E1 gave the equity lanes their live path, engine, store, screen and three captain-seeded programs (league/equity/
INTERFACES.md). E2 makes the swarm itself breed them, around the clock: the architect proposes equity-lane families
with their first program, a minimal researcher iterates each on Train, the first version to pass the Train bar AND the
equity review takes its lineage's one Validation try (E1's look waits for that review on every program the captain did
not seed), and the model routes are chosen by measured yield per dollar. No figure appears here
or in the code: the bar's constants are rules, and the Train map shown to agents is computed on the House from the
swarm's own Train runs.

**The screen is S2** (the captain's amendment A11). The Validation try and the one sealed look of every share program,
seeded or bred, are judged by E1's pinned share screen S2 (league/equity/screen.py; policy.json `elane.screens` pins
its receipt for both lanes; docs/operations.md states the rule and its cost). E2 judges nothing after Train and names
no threshold of the screen: the architect's system text says only that the screen is S2 and that its rule and
false-positive cap were pinned before any look.

## The switch

`elane.mode` "gate" (E1) AND `elane.birth_share` above zero. The release ships the lanes with `mode` "off" and
`birth_share` 0.0 in policy.json, so E2 does nothing until the captain sets both in swarm.json: with either one off
neither of E2's rounds starts, no key is written, no event is made and no model is asked
(league/tests/test_elane_e2_switch.py runs E1's real loop on the committed policy to hold that). At the first
switch-on the captain sets `elane.birth_share` 0.25 and `elane.e2.usd_day` 8.0 (amendment A16); the equity births are
counted apart from the options births (their own population).

**The pace, said plainly** (the captain's decision on the verification's note; the bound is release E2.2's). The
equity lanes' research spend (births, Train research and the equity review together) is paced by two settings the
captain sets with the settings tool, at switch-on or after it, in one command: `elane.e2.pace_share`, E2's hourly pace
in lines of the researchers' Sail model line (shipped 0.25, held to 0-4), and `elane.e2.usd_day`, its dollars a UTC day
(shipped 8.0, held to 0-100): `python3 set_swarm.py elane.e2.pace_share=<lines> elane.e2.usd_day=<dollars> --apply`.
E2's day is the smaller of `usd_day` and a day at its pace, so BOTH must be raised to give the equity lanes more: at
the ceiling's line ($0.3333 an hour) a share of 0.25 is $2.00 a day whatever `usd_day` says, 1.0 is $8.00, 2.0 is
$16.00 and 4.0 is $32.00, each capped by `usd_day`. Left alone they are the shipped 0.25 and 8.0. Beyond the two, E2
is bounded by the House's own Sail day (below), never by half the line.

**E2's dollars: its own pace, counted apart, inside the House's Sail day** (`elane.e2.pace_share`, 0.25, held to 0-4;
`league/swarm/elane_yield.py`). The budget rule gives the swarm one hourly line for Sail models
(`researcher.sail_usd_per_hour` after the budget's overlay: $0.3333 an hour, $8.00 a day, at the owner's ceiling;
$0.0667 an hour at the floor) and one Sail research day (the Sail guard's cap on what the swarm books on Sail in a UTC
day, models and Gym boxes together: $20 at the ceiling). E2's calls are booked as `sail_model` under keys
`swarm:elane:...`, the rows the options researchers' hourly pace sums; the integration review's blocker was that
`usd_day` 8.0 alone made E2 the whole pace (every options researcher slept while E2 spent, and nothing paced E2), and
its fix made E2's dollars a share of the line, at most half. **Release E2.2 (Oct 11, 2026) made the pace E2's own.**
The reason: at most half the line was at most $0.17 an hour, $4 a day, at the ceiling, and the equity lanes stood
still for most of each hour at that pace, while most of the day's Sail research dollars went unspent. The line is only
the model share of a Sail day planned around Gym boxes; an equity Train run needs no Gym box (it runs on the House:
A3), and the owner's goal chooses lanes by measured yield per dollar. Now, read before EVERY model call of E2's (the
equity pass, a Train write, a review or audit read; `elane_yield.hold`):
- **E2's hourly pace** is `pace_share` x the line (`pace_hour`): E2 reads what the swarm booked for its own keys in
  the trailing hour, holds included, and asks nothing at or over it. At the shipped 0.25 that is $0.0833 an hour at
  the ceiling and $0.0167 at the floor; at 4.0, $1.3333 and $0.2667. The budget tightens it with the line.
- **E2's day** is `usd_day` and never more than a day at that pace (`pace_share` x the line x 24), so the budget
  tightens E2 with the line. Once it is spent no equity question is asked until the next UTC day.
- **The House's Sail day** (`sail_day`). E2 reads the Sail guard's own record (the swarm store's kv `guard`, written
  at each of the guard's checks) and, FRESH before each call, the swarm's booked Sail spend of the UTC day (models and
  Gym boxes: the guard's own meter). It asks nothing while the record says the guard is braked, holds new research or
  has no good reading for `guard.stale_seconds`; nor once the day's spend is within a dollar (`SAIL_ROOM_USD`, the
  dollar every question of E2's is held to need) of the line where the guard holds new research: its research cap
  less THE GATE'S RESERVE and, while `guard.pace_day`, the day's even pace. So E2 stops BEFORE the guard would hold
  anyone: the dollar that reaches the guard's line is never E2's, and the day's Sail total never passes the guard's
  cap on E2's account (league/tests/test_elane_e2_yield2.py runs a day at four lines against the real guard, a
  minute at a time). What that does NOT say (the release's independent check, a simulated day): at a high pace E2
  uses the day up to a dollar under the line, so BUSY options lanes then reach the line themselves late in the UTC
  day and all new research, theirs included, waits for midnight (at four lines, one to two and a half hours); and at
  the floor budget, with the options lanes spending at the day's even pace, E2 never has its dollar of room and asks
  nothing all day, where before this release it asked a little. A record with no research cap, or a spend that cannot be read, holds E2 (unknown
  is never money). What follows from the even pace, stated: early in a UTC day E2 has room once the day's due dollars
  exceed the day's spend by that dollar (at once at the ceiling, whose slack is a dollar; hours into the day at the
  floor), and over a day E2 takes what the options lanes leave of the day's pace, no more.
- **The options researchers' pace** (`Swarm.pace_status`, unchanged) leaves E2's rows out of their own spend, as it
  leaves the architect's (F1), and takes what E2 spent in the hour, AT MOST THE LINE'S SHARE, off their limit:
  `min(pace_share, 0.5)` of the line (`elane_yield.usd_hour`, the loop's reading; `LINE_SHARE_MAX`). So whatever E2's
  pace the researchers keep at least half their line: with E2 idle the whole line, with E2 busy at the shipped share
  three quarters of it (the two together fit the line, as before), at a share of a half or more one half. Left as it
  was, a share above one would have taken the whole line and paused every researcher. The heartbeat's
  `researcher_pace.equity` shows that reading: its `limit_usd_per_hour` is the line's share, which above a share of a
  half is no longer E2's own pace (that is in the `dlane` report's `equity_yield`: `usd_hour`, beside
  `line_share_usd_hour`).
- `allocation.plan_usd_per_hour`, when the operator sets one, counts E2's dollars as research spend like any Sail
  model dollar (the plan is the whole research line): with a plan set, E2 at a high pace contracts the researchers'
  workers toward the plan's floor. No plan is set by default.

Stopping, from the lightest:
- `elane.birth_share` 0.0 stops BIRTHS at once. The families already born finish their Train research (the equity
  researcher needs `mode` "gate" alone), and a family that passed Train and the review still takes its Validation try
  and its look in E1's rounds.
- `elane.e2.usd_day` 0.0 with it: no model is asked at all (no program written, no review); what is left is the free
  Train scoring of versions already written.
- `elane.mode` "off" stops everything E2 does. It is E1's own swarm-side rollback, so E1's seeded births, Validations
  and looks stop with it; it is not the money switch (a program already live trades on by its band until
  `equity_money.enabled` is false: docs/operations.md).

## Release E2.2 (Oct 11, 2026): how ctx is read

The first programs the equity researcher wrote on the House mostly read `ctx.bars[sym]` by key
(`ctx.bars[sym]["close"]`) or walked it as rows. The contract said it "carries arrays"; it is ONE object whose six
arrays are read by attribute. Every decide raised a TypeError, the version was disqualified, and its author was told
the error's class and line and nothing of what was wrong, so the revision repeated it; each cost model dollars and
one of the family's scored versions. Three layers, none of which touches a file of E1's code:

1. **The texts.** `league/equity/EQUITY.md` (a document: no identity hashes it) now says what each field of ctx IS,
   read off `league/equity/ctx.py`: a symbol's bars are one object whose six read-only float64 numpy arrays are read
   by attribute, at most `history` + 1 long and SHORTER while fewer sessions lie before the decision (a run from the
   store's first session starts with one element); lots are dicts in a list; `ctx.events`, `ctx.prices` and
   `ctx.caps` are dicts; what a program has (plain builtins, `math`, numpy, no pandas). Its new section "Reading
   ctx" holds a worked rolling-window program and the common faults. One sentence and two lines
   (`elane_review.READING_CTX`) are in the equity architect's lanes block, in the equity researcher's system prompt
   and, after a disqualification or a refusal by the rule below, in its brief. Rules only: no outcome and no figure.
   The generators are handed the whole contract (`elane_train.CONTRACT_CHARS`; a test holds the file under it).
2. **THE READING RULE** (`elane_review.reading_refusals`; static, free), first of the static rules in
   `elane_train.check_code`, so before a version is stored or run. Refused, each with its line and what to write
   instead: a symbol's bars read by key, by position or as rows, iterated, measured, unpacked, handed whole to numpy
   or put into arithmetic, or a field they do not have; a field ctx does not have; a lot or a closed lot read by
   attribute, or by a key it does not have; `ctx.positions` or `ctx.closed` read as a dict; `ctx.events` read by
   attribute or by an unknown flag; `ctx.prices[sym]` or `ctx.caps[sym]` subscripted; and, among the dicts `decide`
   returns, an intent with none or two of "buy", "sell", "cancel" (an empty dict returned for "no order" among
   them), an "at" that is neither "open" nor "close", a buy with neither "share" nor "usd" or a constant size outside
   its range, and a sell that names a symbol or a whole lot. The pass follows a name only while every binding of it
   in its function gives it one kind of value, and an intent only from `decide`'s own return; a name bound two ways,
   a value through a call it does not know, a dict changed after it was written, a read inside a `try` that has a
   handler, and a kind of value the program asks the type of (`isinstance(bars, dict)`) are left alone: never
   refused on a guess. One exception since the release's independent check: a symbol's bars are never a dict or
   rows, so asking THEIR type excuses a misreading only when the program also reads a bar's array by attribute
   somewhere (the sound branch); a helper that reads them "as a dict, else as rows" misreads on every branch and is
   refused, as is `ctx.bars.get(sym, [])` measured or indexed. **What a refusal costs:** the question's model dollars and one of the family's write attempts
   (`train_max_attempts`, 7); never one of its scored versions (`train_budget`, 4), as for the level and memory
   rules. Every shape the rule refuses is run on E1's real isolated runner in the tests and is disqualified there;
   the shapes it leaves alone run clean; the rule's tables are held to E1's own definitions, so a field E1 adds or
   renames fails a test, never a program.
3. **The disqualification's brief.** E1's run result does carry the first error's text (`runtime.disqualified`:
   "25 errors (first: line N: Class: text)"), and E2 keeps that text out of every record and brief on purpose: a
   program chooses its exception's text and reads bars of the 2020-21 reserve as look-back (the design's WHAT ITS
   AUTHOR READS OF IT, below; a test holds it). So the author is shown, beside the verdict, the LINE OF ITS OWN FILE
   the first error was raised at (`elane_train.dq_source`: the program's own code, nothing a run read), what the
   reading rule sees on that line (a version scored before the rule ran is told what it would have refused), else one
   fixed sentence a class of error (`DQ_HINTS`: what a TypeError, an AttributeError, a KeyError, an IndexError most
   often is in an equity program). It is worked out when the brief is written, so the versions already disqualified
   get it too. A first error that is the House's OWN sentence about what decide returned (a malformed intent, a
   return that is no list: E1's closed vocabulary, `INTENT_FAULTS`) is named in the record in fixed words; a count or
   a name the program chose is not repeated.

What it does not catch, stated: a misreading the source does not show (a value through a call the pass does not
follow, a name bound two ways), a window indexed past a short array (the run's first sessions: the brief's IndexError
sentence and the contract's faults say so), NaN compared. Those are still disqualifications or thin years on Train.

## Release E2.4 (Oct 11, 2026): the lanes alarm on their own stalls

In the lanes' first three hours most scored versions were disqualified by the misreading above, families were retired
for it, the lanes were starved at their pace, one equity pass was cut short and another bore nothing because every
proposal named symbols outside the universe. No alarm fired: the stall job (`league/ops/stall.py`) watched the options
lanes, and of the equity lanes it knew only Validation runs and families awaiting a try. The captain found each fault
by hand. Release E2.2 fixed the misreading and the pace. This release makes the House tell the owner when the lanes
next go wrong, and takes away two causes of the barren pass. Of E2's modules it touches the equity pass's request
text and its record of a refusal (`elane_births.py`), the two output settings' bound (`elane_births.py`,
`elane_train.py`) and the reading of the provider's limit and of a setting-shaped failure (`elane_yield.py`); nothing
of E1's.

1. **Four stall causes of the lanes' own** (`league/ops/elane_health.py`; the stall job calls it once at every run).
   What each reads is what E2 already writes: a family's record (`elane_e2`: each version's fails and what a
   disqualification said, the programs refused before a run), the `swarm.elane` events (the equity passes, the Train
   rounds' steps), the rounds that raised, E2's clocks and spend, and the lane's own reading of whether it may ask a
   model now (`elane_yield.hold`, over a read-only reader).
   - `elane_dq`: more than half of the versions scored in the last 6 h, 6 at least, ended DQ, LOAD or RUN (a fault of
     the program against the contract or the sandbox: nothing is said of a mechanism), in at least two families (one
     family's bad programs are no fault of the contract). With fewer than 6 in the 6 h, the last 6 scored since the
     running release started are judged, so the cause does not lapse by itself once the faulty families are retired;
     before the sixth version it stands once 4 of two families could not be judged (most of six, whatever comes). It
     names the first error by its class (`dq_said`'s own closed classes read back) only when one class is more than
     half of the disqualifications, else the classes that tie; and, for a class it names, the reading rule's commonest
     sentence that says it raises that class, or, with none on record, one fixed short sentence of what the class
     most often is (in the owner's step). The owner's step: the text the generators read.
   - `elane_births`: the last 3 passes that asked a model bore no family (every proposal refused, none proposed, cut
     short, no route answered, the pass raised). The commonest refusals by class (how each refusal of
     `EquityPass.admit` begins) and the symbols of the code's universe that `elane.universe` does not hold. The
     owner's step only after 6 h with no birth and only for a way a setting clears; at once when every route refused
     the request for a setting (the pass's event names the `elane.e2` key: item 8).
   - `elane_idle`: families in Train research or births wanted, and the work is not done. STARVED BY WORK LOST: of
     the Train steps due in the last 3 h, 6 at least, more than half were skipped because E2 might ask no model (a
     step's `skipped` is the lane's own `hold`: its pace, its day, the House's Sail day), whether or not a version
     was scored. On Oct 11 a version was scored about hourly while two families in three waited at the pace, and a
     count of idle hours never showed it. Or NOTHING SCORED for 3 h: STARVED when `hold` says E2 may ask no model
     now, BROKEN when it may ask and scores nothing (the owner's step when the rounds raise, the Train runs fail on
     the House's side, the steps fail, or no round starts or judges anything). A starved lane says which line binds
     and names that lever, and nobody is asked: the hourly pace; or the day's line, which is `usd_day` only when it
     is under 24 hours at the pace (`elane_yield.day_line` is the smaller of the two; at the shipped settings the
     day is 24 paces). THE DAY'S DOLLARS SPENT IS NO STALL: while the day's line is spent and a version was scored
     since 00:00 UTC the cause reads clear and says so. A busy lane spends its day before the day ends, every day
     (a call may overshoot the hourly pace, the day's line is 24 paces), and the first build stood on it every
     evening.
   - `elane_refused`: more than half of the programs written in the last 6 h, 8 at least, were refused before a run
     by one static rule. The rule and its commonest sentence. The owner's step: teach the rule.
2. **When a cause is judged.** Only while `elane.mode` is "gate", `elane.birth_share` is above zero, E2's rounds are
   in the tree, the floor is not paused, `elane.e2.usd_day` and `elane.e2.pace_share` are above zero and the store
   holds an equity family or pass. Evidence counts from the first start of the RUNNING RELEASE: the stall job keeps
   {release, since} in `stall.json` (the release directory the heartbeat names, and the `started_at` first seen under
   it), so a release that fixes a fault is not judged on what the generators did before it, and a restart of the same
   release (the watchdog's, a settings apply, a deploy of nothing the lanes read) resets nothing. The idle clock
   alone also starts at the running swarm's own start (a swarm that was down is not idle on the hours it was down),
   and a lane is not judged idle while the swarm itself is not running (a heartbeat ten minutes old: the options
   lanes' causes say that). LANES THAT CANNOT BE READ (the settings, one of E2's readers, the lane's own `hold`) are
   "Not judged" AND an entry of the job's `errors` naming the class: an alarm that cannot see must say so.
3. **Closed words only.** A record's sentences quote what a program wrote (a rule's sentence quotes its source, a
   refusal names the model's lane, symbols and slug), and a disqualification's exception text is the program's own
   choice (the design's WHAT ITS AUTHOR READS OF IT). So nothing of them is repeated: a disqualification is its class
   and line, a static refusal its rule and this module's words for the sentence (`SENTENCES`: the first of the
   rule's own phrases found in it), a refused proposal its class and the symbols of the code's own universe. A test
   runs the equity pass, the static rules and a disqualification's record and reads each back, so a sentence E2
   rewords fails a test there, never silently reads as "another".
4. **No recursion into judges.** The alarm reads records. It never reads, parses or runs a program and applies no
   rule again; it changes no bar, screen, budget, seat, graveyard or refusal rule; it writes nothing (the stall job
   writes its own state file, as before).
5. **The notice.** The gateway words the four (`gateway/lib/email.mjs` `STALL_CAUSES`; the gateway deploys first), so
   each is named in `stall.CAUSES` and is an entry of its own in the mail, keyed by its own name. The first build
   folded them into the cause the swarm's alerts travel in: one gateway key for five things, so each could hold
   back another's mail for 12 hours and a cause that lapsed first was never mailed. `elane_health.mailed` only fits
   an entry to what the gateway prints (the sentence's leading sentences whole inside 400 characters, the telling
   figures first). docs/operations.md says how to read them.
6. **The research funnel** (`elane_health.research_counts`; the funnel's `equity.research`, which the `scoreboard`
   job's receipt carries for the last 24 hours and since the release): equity passes and families born, proposals
   refused by class, programs refused before a run by rule, the Train rounds' steps taken and skipped by reason
   (`train_steps`), versions scored, disqualified and failed by code, bar passes, review refusals and passes,
   families retired, E2's model dollars by purpose. Each count is the event itself; counts and E2's own dollars only.
7. **The architect is not led outside the universe, and is told in closed words** (`elane_births.lanes_text`,
   `_costs_line`, `agenda_text`, `last_text`). The contract-in-brief quoted half-spreads for "the other ETFs", TLT and
   GLD whatever `elane.universe` held, and the agenda speaks of sector ETFs: a pass on the four index ETFs proposed
   sector rotations and every proposal was refused. The line now gives the half-spread of each group the universe
   holds, in its own symbols (the code's `HALF_SPREAD_BP`), and THE UNIVERSE line says a proposal naming any other
   symbol is refused whole. The agenda's priors are unchanged (rules, and the Train map's mechanisms); while the
   universe holds no sector ETF one sentence after THE AGENDA says to read "sector ETFs" as THE UNIVERSE's own
   symbols (`NO_SECTORS`). THE LAST PASS'S REFUSALS are said by class, in the House's one sentence a class with the
   House's own values (`REFUSAL_SAID`: the structures and universe the settings open, the agenda's keys, a card's
   field names, the symbols of the code's universe that are not open and a count of any others). The admission keeps
   those closed facts beside each refusal (its class, the proposal's place in the answer, its lane and agenda key
   when valid). The request used to show each refusal's own text and the proposal's slug, both of which repeat what
   the model wrote (a lane, structure, agenda or symbol as it spelled it), and the next request may be read on
   another route. A PROPOSAL IS NAMED BY ITS PLACE, never its slug: the House's slug rule (`architect.family_slug`:
   lower case, every other run of characters a hyphen, cut at 36) keeps a model's words, so a slug that passed it
   can still carry a sentence. The House's record of the pass keeps slugs and reasons, as before. Unlike the options
   architect's, a pass that proposed nothing replaces the last refusals with none.
8. **The output settings are the provider's to bound** (`elane_yield.OUTPUT_LIMIT`, read from `ltcm/provider.py`
   `MAX_OUTPUT_TOKENS`). `births_max_output_tokens` and `train_max_output_tokens` were bounded at 64,000 while the
   provider refuses a request above its own limit before it is sent, so on Oct 11 a setting inside the lanes' bound
   failed every route of one births pass, and the pass's event said only that no route answered. Both bounds are
   the provider's limit now (a value above it is its default, as any value outside a bound). And a births pass that
   every route refuses for a setting (`elane_yield.setting_fault`: the provider's own codes for a request it never
   sends: the output limit, the effort, an unknown profile) says so in its event in one closed word, the `elane.e2`
   key (`setting`), which `elane_births` reads.

No setting is added and none changes; `ops.json` `{"stall": {"elane": false}}` is the owner's switch for the four
causes. No identity moves.

## The design

1. **Births** (`league/swarm/elane_births.py`). The architect's equity pass (`Architect.equity_pass`, its own loop round)
   is a separate request from the options pass, so the options request, graveyard and births stay byte for byte as
   they were. Its request holds the LANES/EQUITY block (what BETA and EQUITY mean and their labels, the universe by
   class and group, the contract in brief, the ration, the Train bar), THE AGENDA (overnight effect, short-term
   reversal, time-series trend, cross-sectional and sector momentum and rotation, low volatility, turn of the month,
   each with its published prior; post-earnings drift named and refused until earnings data exist), THE EQUITY QUOTA,
   THE EQUITY TRAIN MAP, the equity graveyard that binds (E2's Train refutations and the CLOSED cells), the lineages
   whose one try is taken (seeded programs and Train passes, outcomes sealed), the equity families' Train facts, the
   card vocabulary, and the last pass's refusals. EQUITY.md rides in the system prompt.
   - THE EQUITY QUOTA (`EquityQuota`): the equity lanes' share of the swarm's births over the last 24 hours is
     `elane.birth_share`; a pass asks for the births that bring the lanes to it, at least `min_per_pass` and at most
     `max_per_pass`, never past `max_alive` families in Train research. The equity lanes have their own population (E1's
     `families` filter keeps them out of every options count), so an options population at its ceiling never stops an
     equity birth, and E2 takes no options birth. This is how E2 reads the design's "taken out of the alpha share
     first": the share is of births, and an equity birth takes no options place, so reducing the options births would
     only slow the options refill and free nothing the equity lanes use.
   - THE ADMISSION: lane, structure (a beta card is "etf"), symbols (in `elane.universe`, of the structure's class),
     agenda (an available mechanism), the cell not CLOSED, no family in Train research with the same idea on the same
     slice, a valid card (`cards.validate`, E1's equity admission), THE GRAVEYARD BINDS (a card in the cell of a family E2
     refuted on Train needs a valid `card.rebirth`, read by E1's lane-scoped `cards.RebirthIndex` over E2's own
     refutations only, while `architect.card_rebirth` is "refuse"), NO continued lineage with its try (the parent
     it names, EVERY family of its slice with the same idea, and the row it is reborn from: no seeded program and no
     Train pass in any of them; naming an untried parent hides no tried one), and the quota. The card vocabulary shown is the equity cards' own (E1's
     `elane.INPUTS` and `elane.CLASSES`, no implied vol, chain, skew or intraday holding). A born family's spec carries `lane`, `symbols`, `agenda`, the
     card's sha and `e2_route`; a program that passes the static checks is its version 1.

2. **Train** (`league/swarm/elane_train.py`). THE TRAIN YEARS (amendment A15) are 2016-19 and 2022-24, seven years. A
   version's Train run is two runs of E1's isolated runner, one a span (2016-01-04..2019-12-31 and
   2022-01-03..2024-12-31), each starting flat, summed. 2020-2021 is THE RESERVE, kept for a later accessor: E2 runs no
   session of it, and a result that carries a row of 2020 or 2021 is refused whole exactly as one of 2025 or 2026 is, so
   no 2020-2021 P&L reaches a family's record, the Train map, the yield ledger or a generator. The Train map, the
   briefs and the architect's text say "Train years 2016-19 and 2022-24". What of the reserve does reach Train: its
   bars, as look-back. The 2022-2024 run reads the bars before 2022-01-03 as history (NEEDS `history` + 1 sessions,
   up to 505: the first decision is at the close of the session before the run's first, and E1's store hands it that
   session and `history` before it), as a Validation run looks back on 2024's, so a program with look-back has
   2022-2024 Train figures that are functions of reserve bars, and even a program with no look-back reads the last
   2021 session; no session of the reserve is ever traded or scored (section 4 says what is tested).

   THE BAR equity-v1 (the design's 6b, on the Train years), on the summed runs at 1.0x and 1.5x the half-spread: at
   least 40 closed lots and 20 entry days in each of three or more of the seven Train years; no Train year's daily t
   below -1.0; net P&L above zero at 1.5x; the 1.5x P&L at least half the 1.0x P&L (which must be above zero); and
   STATE, the restart check below. Beside it, never a bar: the same-exposure buy-and-hold, MTE and the drift share.

   THE LOOSENING, stated (A15): the Train bar reads 7 years, not 9. The design's 6b read 2016-2024; without 2020-2021
   a year's t has two years fewer to fall below the floor in, the two P&L rules sum seven years instead of nine, and
   every pass (and the Train map's pooled t) stands on seven years of evidence. "Active in three years" is three of
   seven.
   - STATE, THE RESTART CHECK (A15; `restart_check`), run once the rest of the bar holds: the program is run again
     with its STATE emptied every 20 sessions and must give the uninterrupted run's intents on at least 99% of the
     Train sessions, else the version fails with code STATE (the program's fault, not the House's; like DQ, LOAD, RUN
     and REVIEW it judges a program, never the mechanism, so it refutes nothing). Why: the House's decider child
     restarts on every deploy and a restart empties a program's memory, so a program whose decisions hang on STATE
     would trade live other than its replay. A program that keeps nothing passes; one that counts sessions in STATE
     fails, whatever its clock's period; one that only caches values it can recompute from ctx passes; one whose
     decide fails once its STATE is gone fails. How: through E1's decider kinds (`kind_load`, "decide", `kind_drop`),
     per Train span, instance A is loaded once and instance B is loaded with it and then loaded fresh; at every
     decision session both read the same ctx, built by E1's ctx builder from the span's own 1.0x run (its bars, open
     lots, closed lots, cash, equity and caps), so only memory can make their answers differ.
     THE RESETS ARE OFF THE SPAN'S START (the A15 review): B is emptied 7 sessions into a span (`state_first`) and
     every 20 after (`state_every`): decision sessions 7, 27, 47 and on. Counted from the first session, where A
     starts too, the resets left a session counter whose period divides 20 (a weekly clock of 5, or 2, 4, 10, 20) in
     phase with its reset twin on every session, and it passed; with 7 and 20, a counter of any period falls out of
     phase.
     WHAT MATCHES (the A15 review): a session matches when the two decides ended alike: the same orders in the same
     order, every buy the same size, and the same count of errors in that call (E1's `stats.errors`). A decide that
     raises because STATE was emptied answers nothing, as the uninterrupted one may, so the intents alone would agree;
     live, two failed decides in a row exit the program's lots. Two buys are the same size within one part in a
     million of the sleeve for a `share` (six places, the engine's quantity precision) and a cent for `usd`
     (`SIZE_TOL`): a cache that holds the value ctx gives, summed in another order, differs in the last digits only
     and passes. DECIDED, and the captain may move it (one constant): a value carried from session to session and
     updated in place (a running sum, an average, a peak since entry) fails. ctx's history is adjusted as of each
     session and rounded to four places (EQUITY.md), so the carried value is not the one ctx gives now: on E1's
     synthetic store with dividends such a program's sizes differ past the sixth place on most sessions, and the
     uninterrupted replay is the one that has drifted. The gap is cents on a sleeve, but a program that passes STATE
     is then restart-invariant to six places, whatever compares live with replay later (A14), and the cure is one
     line (recompute from ctx.bars at every call). The bar's text and the researcher's system prompt say so before a
     program is written, and a failed version's brief says how many sessions differed in a buy's size alone and by
     how much, and on how many sessions a decide failed in one run and not the other.
     NEVER A SILENT PASS: each answer's `stats.calls` must equal the decides its instance was asked since its load, so
     an instance the child reloaded is caught whether or not the decider counted a restart (E1's `Decider` reloads its
     instances into a child that died between two requests without counting one); a check that cannot run or finish
     (no decider, no call count or no error count in the answer, a reloaded or missing instance, a span with no
     session) is the House's: the version is not scored, cannot pass, and its `train_max_errors`-th (third) such
     failure since the version was last judged is an alert, sent once (`elane_train_state`). A session an instance was
     disqualified at matches nothing. What the check does not catch, stated: memory that changes the answers of fewer
     than 1% of the sessions (a clock kept in STATE of a hundred sessions or more that moves a few decisions a year),
     and whatever the run's record does not keep for the ctx (the intents the engine refused: `ctx.rejects` is empty
     for both instances).
   - WHAT A VERDICT IS: only the program's own doing is judged: its runs finished (the bar), it was disqualified by its
     own errors ("DQ"), the child refused to load it ("LOAD"), the child failed its run (or its restart check's
     decides) `train_max_errors` times in a row while other programs' Train judgments completed ("RUN"), or its
     intents changed when its STATE was emptied ("STATE"). WHAT ITS AUTHOR READS OF IT: a LOAD refusal's own text
     (the House's static refusal; a program that did not load read no market data); of a disqualification only
     counts, a line of its own file and a known exception class, never the exception's text (a program can put a bar
     of the reserve it reads as look-back there); of a RUN only the failure's class. A failure of the House's (no equity store yet, the store
     being rewritten, a decider child that could not start, a restart check that could not run or finish, "no_data", a
     result outside the Train years) scores nothing, spends no budget and asks no model: the family backs off
     (doubling with every failure, at most six hours) and is tried again; a result outside the Train years is also an
     alert. A STANDING failure of the House's is an alert too (`elane_train_house`): a version's third failure of
     kind "run" (the child fails every program) or "store" (no equity store) since it was last judged, at most once
     every six hours for the lanes; the owner's `swarm_alerts` cause carries it. The House's failures are counted by kind (the A15 review): "in a row" for RUN means the child's failures
     of the version one after another, so a restart check the House interrupted, or a store being rewritten, in
     between starts the row again and never counts toward RUN (a standing pass being scored again is not withdrawn
     on them either); the restart check's alert counts its own kind, whatever failed in between.
   - THE RESEARCHER (`EquityResearcher`, minimal): each round gives a few families one step: re-score a stale pass,
     review a bar pass, score the newest version, or ask the family's birth route for its first program or a revision
     (the brief holds the card, the agenda prior, the bar and the family's own Train versions and review reasons only),
     or retire it. A round starts only when it has work it can do now (a family that must ask a model is none while
     E2 is at its pace or its day is spent; a family at Candidate with nothing left is none), and writes its event
     only when something was done. A question no route answered backs the family off (doubling, at most six hours). The first version that passes the bar AND the review ends the research: it is the lineage's one
     Validation try (`may_validate`, the guard E1's tournament applies; `best_version` set). A spent Train budget or
     attempts cap, or a `stop` after a judged version, retires the family: REFUTED on Train (a graveyard row in E2's own
     words) when the bar judged a version (Y1, Y2, P1 or R1), else STALLED (no graveyard row, no cell count). A `stop`
     before any judged version is not accepted.
   - THE IDENTITY: each verdict carries the equity identity (E1's `evaluator.equity_identity`) it was judged under. A
     pass judged under another identity whose version has had no Validation try is Train-scored again, its restart
     check with it, before E1 may validate it (kept or withdrawn). E1's adoption clears `best_version` and the review state; the round restores both
     for a pass that stands (`upkeep`).
   - THE EQUITY TRAIN MAP: lane x agenda x universe group, with births, Train passes (the best passing pooled t),
     refutations (each with a judged version), stalls, and CLOSED cells (`refuted_cell_cap` refutations, no pass).
     In-sample, labelled so.

3. **The equity review** (`league/swarm/elane_review.py`). E1's look takes a sealed look only of a captain-seeded program
   or of a version whose state carries a passed review and audit of its exact program (`state["review"]`, the gate's
   shape: {"sha": gate.run_sha(version), "verdict": "pass", "audit": {"verdict": "pass"}}).
   - THE LEVEL RULE (static, free): a raw price or volume level (a close, an average or range of prices, a lot's entry
     or mark, a share volume, or the log of one) compared with, offset by, bucketed by or clipped at a constant or a
     PARAMS value is refused before the program is stored or run (`check_code`); a ratio of ONE symbol's levels is
     untouched, and the ratio of two different symbols' prices against a constant is refused as a level is. The pass
     follows what `ctx.bars.items()` and `.values()` yield, a lot's field by `[...]` or `.get`, a helper or a named
     lambda with each call's own arguments, numpy's comparison, arithmetic and table functions, `getattr` with a
     literal name, a constant written as arithmetic or text, `zip` taken apart in a loop, and what the program puts
     into a container of its own and reads back in the same function (`closes[s] = c[-1]`, `xs.append(px)`,
     `STATE["px"] = px`; each string key kept apart, so a counter beside a price stays a counter; what ctx gives, a
     lot's row or PARAMS, is never the program's own whatever it writes there). A loop's body is read twice and its
     refusals are kept on the second reading, so a placeholder a loop fills (`prev = None` ... `px / prev - 1` ...
     `prev = px`) is not read as the number it starts as; a function's body keeps the refusals of both readings (the
     first is the order its statements run in), and on that first reading a key of the program's own that holds
     nothing yet (the price kept from the last call) is unknown. What it cannot follow (a tuple or a dict stored
     whole, a container read in another function, a level's digits, a level through a call it does not know) is the
     paid review's.
   - RUN-START DEPENDENCE, in the same pass (the integration review's seal-1): every judged run starts flat with the
     same capital (`ctx.budget`, a constant in a replay), so a program that reads its own profit since the run began
     and sizes on it (a profit lock) trades one way from a fresh start and another mid-run, and the share screen's
     floor, built from windows of one long run, never sees it: its false-positive line holds only for programs blind
     to their run's start. Refused: `ctx.equity`, `ctx.cash`, `ctx.budget`, `ctx.caps` or a lot's `value`, `pnl` or
     `net` compared with, offset by, bucketed by or clipped at a constant or a PARAMS value, and the sleeve's dollars
     now held against `ctx.budget` or `ctx.caps` in any way (a constant over them and their log are the run's dollars
     still: `1000.0 / ctx.equity`, `math.log(ctx.equity)`). Allowed: sizing proportional to them, a sign or zero
     check, and the position's own state among the sleeve's dollars now (cash over equity, a lot's value over
     equity). FOR THE CAPTAIN: the root is E1's (the floor's worlds never start flat while every judged window does);
     the static rule and the rubric below are the guard until the screen's floor sees fresh starts.
   - THE RUN'S CAPITAL FROM A LOT, in the same pass (the verification's seal-1 residual). The anchor need not come
     from ctx. The House sizes an entry as the asked share of the run's capital, so what a lot cost is that capital
     times a share the program chose itself. A program with no memory at all rebuilt the capital from its own lots (a
     lot's `qty` times its `entry` or `exit`, its `value` less its `pnl`, `exit` times `qty` less `net`), held
     `ctx.cash` or `ctx.equity` against it, and was the profit lock again: on synthetic stores it traded the lock lot
     for lot, and the restart check matched every session, for it keeps nothing in STATE. A program that stops or
     shrinks once it is ahead passes a positive-sum, t-above-a-floor screen far more often than the screen's
     false-positive line says, so this was a hole in the judge for every program the swarm breeds. Now a lot's `qty`
     and what a lot cost ARE the run's anchor: the sleeve's dollars now against them are refused as against
     `ctx.budget`, and they are refused against a constant or a PARAMS value. The pass follows the spellings (a
     number of shares times a price is dollars, dollars over a price a number of shares; a lot's own dollars now
     times or over anything but a constant read as what the lot cost: its `value` over its `mark` is its qty, its
     `value` over its own return its cost; the run's dollars stay the run's dollars through a product of two of
     them, a reciprocal, an exponent, `pow`, their text and a call the pass does not know). The run's dollars come
     first in a mixed value: plus, less, times or over a level, a log or a cross-symbol ratio they are the run's
     dollars still, and so is a value that may hold them and a level (a list of both, the smaller of cash and a
     price); read as the level, `(ctx.equity + px - px) / (ctx.budget + px - px)` was a ratio of two prices and
     the lock passed. ctx's and a lot's counts (`ctx.weekday`, `held_sessions`) are of no unit and known to be; as
     unknowns they took the run's dollars out of the pass's sight. The run's dollars
     written into an intent's `tag` are refused too: the House keeps a lot's tag across a restart, so the first
     equity a run saw, carried from lot to lot, is the lock's memory where the restart check cannot look (the same
     trades as the lock on synthetic stores, every session matched). Allowed: a lot's own return however it is
     written (`mark / entry`, `pnl / value`, `pnl / (qty * entry)`, `pnl / (value - pnl)`), a stop on the average
     entry of several lots (`sum(qty * entry) / sum(qty)` is a price), a sign check, a count of sessions held, a
     size from the sleeve or from `ctx.budget`, a label in a tag. The cost, stated: an honest program that writes a
     lot's weight through its qty (`qty * price / ctx.equity`), or scales a lot's value by a ratio before setting it
     against the sleeve, is refused with the reason and must write the weight as `lot["value"] / ctx.equity`; and a
     program that keeps a price and dollars in one value (a helper returning both in a tuple) and reads the price
     back from it is refused where a price alone would pass.
   - **What the static rule cannot see.** Said plainly, because the two paid readers are the only guard here:
     1. THE POSITION'S OWN STATE USED AS THE ANCHOR. A lot's weight in the sleeve (`lot["value"] / ctx.equity`), a
        lot's `pnl` over `ctx.equity` and the sleeve's cash share (`ctx.cash / ctx.equity`) are allowed against a
        constant: a weight cap is an honest rule. But a weight is the asked share times the lot's own return times
        budget over equity, so a weight set against the lot's own return, or read in the lot's entry session, is the
        run's profit. Nothing static tells that from the honest cap. A program built on it (in the tests:
        `WEIGHT_LOCK`) shrinks its entries once the run is ahead as the lock does, keeps no memory, and passes the
        static rule AND the restart check.
     2. WHAT THE PASS CANNOT FOLLOW: a function reached through an expression (`(lambda d: d["qty"])(lot)`), a tuple
        or a dict stored whole, a container read in another function, a lot's tag read back as a number, a call the
        pass does not know on a value that is not the run's dollars. Such a value is unknown and is never refused on
        a guess, and the run's dollars plus, less, times or over it are unknown with it.
     3. MEMORY IN STATE: the first equity a run saw, kept in STATE, passes the static rule; the Train bar's restart
        check judges it (it fails a program whose trades change when STATE is emptied; in the tests `STATE_KEPT`,
        the verifier's third program, is the lock lot for lot and fails that check).
     4. WHAT THE HOUSE'S OWN ANSWERS TELL: `ctx.rejects`, and whether an entry of constant dollars was filled, cut
        or skipped, say something about the sleeve's cash (a third lot that exists only when cash was left over); the
        pass does not read them.
     The two paid readers' rubric (`REVIEW`, "RUN-START DEPENDENCE", and its fact `run`) names the pattern (the
     capital rebuilt from a program's own lots, a lot's weight or the cash share used as the anchor, the sleeve's
     dollars of an earlier call carried in STATE or in a lot's tag) and ends on the rule itself, which covers the
     spellings it does not list: a rule whose trading depends on how far the run is ahead or
     behind is refused, whatever its spelling. A reader's failure that cites it binds (a verbatim excerpt, the
     reference `run`, a counterexample). The root stays E1's: until the screen's floor sees fresh starts, a profit
     lock the readers miss is judged by a screen whose false-positive line does not hold for it.
   - THE MEMORY RULE (static, free; seal-5): an object that belongs to `numpy` or `math` (`np.typecodes`) is shared
     by every program and run in the swarm's one decider child and survives the restart check's fresh load. A bred
     program calls a module's functions and reads its constants and types; any other object of a module read as a
     value (held, aliased, indexed, passed on, reached by `getattr`, imported by name) is refused. It lives here and
     not in league/gym/safety.py because that file is in the options execution fingerprint and the equity evidence
     identity: for E1's next identity move.
   - THE PAID REVIEW AND AUDIT, at a version's first bar pass and before it is the Validation try: two different models
     (`review_routes`; the audit never on the reviewer's model) read the exact program, its card and its own Train facts
     under the gate's leakage rubric adapted to daily share programs (absolute levels, calendar reconstruction,
     run-start dependence in every spelling, the run's capital rebuilt from a lot and a lot's weight used as the
     anchor among them, lookahead). A failure must be grounded (a verbatim excerpt, a contract reference, a
     counterexample), else it reads
     unclear; `review_max_unclear` unclear reads fail. A failure is a Train failure of that version ("REVIEW") and spends
     no try. The review's dollars are E2's (`usd_day`), on ledger rows of their own ("review:<route>"). WHILE SAIL'S
     BALANCED WINDOW IS FLAGGED STALLED the router answers pro_balanced and k3_balanced on pro_asap for E2's role: a
     candidate is read as the model its fallback reaches and left out of the audit when that is the reviewer's, an
     answer from the reviewer's model all the same is booked, discarded and the next candidate asked in the same
     step, and every question has a key of its own (a repeated key is the Provider's stored answer: booked twice,
     and empty once the router's compaction has blanked it).

4. **No feedback** (`league/swarm/elane_seal.py`, A9 D3). No Validation or look outcome of a share program reaches a
   generator. The equity generators read equity families through `train_facts` only (birth facts and E2's own Train
   record; never a band, a retirement, a validated version, E1's try, look, floor or sigma, a look row, a forward
   record, or a graveyard lesson someone else wrote). The options generators read no equity-lane graveyard row at all
   (architect.py: the digest, `graves`, `unseen`, `graveyard_ids`; researcher.py: the `graveyard` tool; game.py's
   `visible_graveyard` by patch 4, for the diagnostician). The test is invariance: two stores that differ only in what
   happened after Train give the same equity request, researcher brief, route choice, Train map and options graveyard
   reads (league/tests/test_elane_e2_seal.py). THE RESERVE (A15), what is tested and what is not: E2 asks the runner
   for the two Train spans only, so no reserve session is run or scored; no record, stored run, map, ledger or
   generator read holds a figure, a row or a day of 2020-2021, whatever the reserve's P&L would have been; a runner
   that leaks a 2020 row is refused whole. It is NOT true that two markets that differ only in 2020-2021 give every
   E2 record byte for byte the same: on E1's runner the 2022-2024 run reads the bars before 2022-01-03 as look-back
   (`history` + 1 sessions, up to 505), so a program with look-back has 2022-2024 Train rows, P1/R1 sums, a pooled t
   and a Train-map best t that are functions of reserve bars. Its 2016-2019 rows are the same in both markets. Even a
   program with no look-back reads the last 2021 session (one reserve bar is in every 2022-2024 slice); the tested
   one, which holds no price against another, has the same figures of its own throughout, and the buy-and-hold
   reported beside its 2022 moves with that close (league/tests/test_elane_e2_e1.py, on E1's runner). FOR THE
   CAPTAIN: if
   the later Thresholdout accessor needs the reserve's bars unseen too, the look-back before 2022-01-03 must be
   blanked by a hook in E1's runner or store (E2 cannot do it from its own files), at the cost of most of 2022 for a
   long-look-back program.

5. **Yield per dollar** (`league/swarm/elane_yield.py`). One ledger row a model route ("sail:<profile>",
   "openai:<model>", "claude:<role>"): requests, answers, failures, dollars (births and research), births; the Train
   counts are read from E2's records, and the operator's report adds Validation entries, looks, looks passed and live
   programs, each per dollar. THE ROUTE CHOICE: with no births anywhere, the first route of `elane.e2.routes` (cheapest
   list price first); a route is sampled at `min_births` births OR `sample_requests` BIRTH requests (the equity
   pass's own, answered or failed: a route that never bears is measured at zero; a family's Train revisions are
   booked on its birth route's row and count nothing toward the sample); before every route is sampled, every
   `explore_every`-th request goes to the unsampled route furthest from its sample and the rest DEFAULT TO THE
   CHEAPEST ROUTE THAT HAS PRODUCED BIRTHS (the lowest mean dollars a birth request); once every route is sampled, every (`explore_every` x routes)-th request goes to
   the least-requested route (no route starves on early bad luck) and the rest to the most Train passes per dollar,
   smoothed ((passes + 1) / (usd + the pooled dollars a pass); ties: births per dollar, then the cheaper request). The yield the choice reads is Train passes, never a later stage: a choice made on look
   outcomes would feed the holdout back into which model writes the next programs (A9 D3). A family's revisions are
   asked on its birth route, so its cost and its yield sit on one row. `usd_day` caps E2's model dollars a UTC day,
   inside its share of the model line ("The switch"). A call that failed is booked at what the swarm booked for its
   key (a hold for a call that was sent and never answered); one that failed AFTER IT WAS SENT ends the question (no
   other route is asked it on top) and the family backs off.

## The files

| file | what |
|---|---|
| `league/swarm/elane_births.py` | the switch, THE EQUITY QUOTA, the request's blocks, the equity pass and its admission |
| `league/swarm/elane_train.py` | the Train years and the reserve, equity-v1 with its restart check (STATE), what a verdict is, the record, the identity, `may_validate`, the Train map and graveyard, the agenda, the equity researcher |
| `league/swarm/elane_review.py` | the equity review: the level rule with run-start dependence, the memory rule, the paid review and audit's rubric and grounding, the record E1's look reads |
| `league/swarm/elane_yield.py` | the route ledger, the operator's report, THE ROUTE CHOICE, one route a question, E2's hourly pace and day inside the Sail model line |
| `league/swarm/elane_seal.py` | what of an equity family a generator may read; the graveyard filter |
| `league/ops/elane_health.py` | release E2.4: the lanes' own stall causes (`elane_dq`, `elane_births`, `elane_idle`, `elane_refused`), their research funnel, the notice's entries fitted to the gateway's cuts, the operator's report; read-only |
| `league/swarm/architect.py` | `equity_due`, `equity_pass`; equity rows out of the digest, `graves`, `unseen`, `graveyard_ids` |
| `league/swarm/researcher.py` | equity rows out of the `graveyard` tool |
| `league/tests/test_elane_health.py` | release E2.4: each cause standing and each quiet lane not judged, the stall job's machinery, the notice held to the gateway's causes and cuts, Done's item 7, the funnel on an invented day, the closed words held to the code that writes the records, the lanes block on two universes, hostile text in every field of a barren pass, the output settings' bound, and the two replays of Oct 11 on an invented House (`league/tests/elane_e24_house.py`) |
| `league/tests/test_elane_e2_*.py`, `elane_e2_fakes.py` | births, Train (the seven years, the restart check), review, seal (D3 and the reserve), yield; E1's names faked as INTERFACES fixes them |
| `league/tests/test_elane_e2_e1.py` | E2 on E1's own code with the patches (skipped on the skeleton): patch 5 in E1's `equity_round`, E1's `reviewed`, adoption, the lane-scoped graveyard, patches 9 and 10; A15 on E1's runner, ctx builder and decider (in process and a real child killed mid-check): the clocks of 5, 10 and 20 sessions, the decide that fails on an empty STATE, the in-place cache with and without dividends, and what of the reserve reaches Train (look-back) |
| `league/tests/test_elane_e2_switch.py` | the release as it ships on E1: the shipped switches and the settings' bounds, E1's real loop standing still while the lanes are off or the share is zero, one equity pass on the real router, the three identities unmoved, the generators' text naming the pinned screen and no threshold |

## Settings (`elane.e2`; every default in code, and policy.json carries the same block)

Births: `births_every_seconds`, `births_refill_seconds` (while fewer than `start` families research), `start`,
`max_alive`, `min_per_pass`, `max_per_pass`, `window_hours`, `births_max_output_tokens`, `births_effort`,
`families_shown`. Train: `train_budget`, `train_max_attempts`, `train_max_errors`, `train_every_seconds`,
`train_per_round`, `train_max_output_tokens`, `train_effort`, `refuted_cell_cap`. Review: `review_routes`,
`review_max_output_tokens`, `review_effort`, `review_max_unclear`. Routes: `routes`, `min_births`, `sample_requests`,
`explore_every`, `usd_day`, `pace_share`. Each is held to its bound in code; a malformed value is its default. The box's swarm.json
overrides one key at a time (the settings layers merge deep): `usd_day` is held to 0 to 100 dollars a UTC day,
`pace_share` to 0 to 4 lines of the Sail model line (0 to 0.5 before release E2.2; a value outside reads the shipped
0.25), `births_max_output_tokens` and `train_max_output_tokens` to the model provider's own output limit (release
E2.4: `ltcm/provider.py` `MAX_OUTPUT_TOKENS`; 64,000 before, above what the provider takes; a value above the limit
reads the default), and E1's `elane.birth_share` to 0 to 0.5 (a value above reads 0.5; one that is no number reads 0).

## The patches (league/swarm/ELANE_E2_PATCHES.md)

E2 was built on E1's early skeleton and edited no file E1 owned; what it needed there was written as numbered patches.
They are applied: `feat/equity-e2-int` is E1's final head with E2 merged and the patches in, one commit each, and the
patch file is now the record of that (which went in as written, which was re-made, and what is still open at the
gateway). In one line each: the loop's two rounds (1); the options birth quota's window skipping equity births (3);
`game.visible_graveyard` dropping equity rows (4); the tournament validating an E2 family only where
`elane_train.may_validate` allows (5); the `elane.e2` policy block (6); the five modules protected (7); the operator's
yield record in the dlane report (8); the options population's floor in `store.retire_gym` (9); the operator's stall
facts and the pre-open population check counting the options lanes only (10); the House's mirror keeping
`swarm.elane` rows in the swarm's table (11); and, from the integration's review: the researchers' pace counting E2
apart (12), pre-open check 6 reading the options lanes' live bands (13), the Validation alarm and Done's item 7
reading the options lanes with the equity lanes beside (14). E1 already scopes `dlane._born` by lane,
so there is no patch 2. The isolated runner is shared by E1's tournament and E2's Train round; E1's decider serializes
its calls under one lock.

A15 added no patch: the Train spans and the restart check use what E1 already provides (the runner's
`train(start, end)` and `decider`, the decider kinds, the ctx builder), and the restart check's instances live in the
swarm's own decider child under keys of their own, dropped when it ends. Since A15 a version's Train run is four runs
(two spans at two stresses), so E2's runs on the House are up to about 72 an hour. The A15 review's fixes added none
either: the restart check now also reads `stats.errors` from E1's decide answer, which E1's runner already gives
beside `stats.calls` (an answer without it is the House's failure, never a pass).
