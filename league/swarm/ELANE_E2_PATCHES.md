# Release E2: the patches in E1's files, as applied

This file was E2's list of changes for the integrator. It is now the record of what was applied: nothing here is left
to do. E2 (`feat/equity-e2`, carried at 04ca26c9: its A15 review fixes included) was merged into E1's final head
8e11986b on branch `feat/equity-e2-int`, and E1's later commits were merged in after it (bb0f2671, then its review's
fixes, 5472aa99 and 70948154, then its rehearsal on real data, 5084263e, then its verification's fixes and the lot
scale (A20): 1159d421 and e643bca3, then the Probe sleeve at 0.50 x E and the parked sizing-up step: 05f83d9e, E1's
frozen head and the one carried now); E2's own files
(`league/swarm/elane_births.py`, `elane_train.py`, `elane_yield.py`, `elane_seal.py`, `elane_review.py`, their tests,
and its branches in `league/swarm/architect.py` and `league/swarm/researcher.py`) merged with no conflict, and each
patch below went in as one commit, in this order (11 was found by the full suite and added at the integration; 12 to
14 answer the integration's own review, below). The
numbers are the ones the code's comments and docstrings name ("patch 5", "patch 9"). The design is in
[ELANE_E2.md](ELANE_E2.md).

| # | file | what | without it | applied |
|---|---|---|---|---|
| 1 | `league/swarm/loop.py` | the two rounds: `elane` (`Architect.equity_pass`) and `elane_train` (`EquityResearcher.run`) | E2 never runs | as written; re-placed after E1's s2-7 (its equity rounds left the Gym's branch): E2's two start under the research guard alone, outside the branch a Gym that is down closes |
| 2 | (none) | E1's `dlane._born` already skips equity births (A8.12) | | not needed: E1 has it |
| 3 | `league/swarm/allocation.py` | `BirthQuota` skips equity births | equity births (E1's seeds too) dilute the options structure families' window shares | as written |
| 4 | `league/swarm/game.py` | `visible_graveyard` drops equity rows | the diagnostician can read an equity row whose lesson tells a Validation or look outcome (A9 D3) | as written |
| 5 | `league/swarm/tournament.py` | after `n = elane.next_try(...)`, an E2 family is validated only where `elane_train.may_validate` allows | a brand-new E2 family's v1 takes the lineage's one try before it met Train or the review | as written |
| 6 | `league/swarm/policy.json` | the `elane.e2` block, every value its code default | the code defaults apply (the same values) | as written, its lists laid out as the file lays out every list |
| 7 | `league/ci.py`, `league/tests/test_ci.py` | the five E2 modules in `PENDING_GATEWAY`, so in `FORBIDDEN`, and the test's pin | E2's bar, quota, route rule, seal and review could be changed by a role or self-deployed by the updater | re-made by hand (below) |
| 8 | `league/ops/dlane_report.py` | the operator's yield-per-dollar record (`equity_yield`: `elane_yield.report`) | the record is in the store and no report prints it | as written |
| 9 | `league/swarm/store.py` | `retire_gym`'s population floor counts the options families only | E2's families hold the options floor up, so the diagnostician can retire the options population toward zero | as written |
| 10 | `league/ops/stall.py`, `league/ops/preopen.py` | the owner's alarms count the options lanes only: births, the living population, the Gym runs, the dry-births tally, the pre-open population check | E2's births hide a dead options architect, its families a population under its floor, its Train runs on the House (up to ~72 an hour) a stalled Gym | as written |
| 11 | `league/swarm/hook.py` | `SKIPPED_KINDS` gains `swarm.elane` (E2's pass and Train-round events stay in the swarm's own table) | the House's mirror drops each row as an unknown kind and warns the owner; `test_swarm_hook` fails | added at the integration (E2's list did not have it) |
| 12 | `league/swarm/loop.py`, `league/swarm/policy.json` | `Swarm.pace_status` leaves E2's rows (`swarm:elane:` keys) out of the researchers' own spend and takes what E2 spent in the hour, at most E2's pace, off their limit; `elane.e2.pace_share` 0.25 | E2's dollars pause every options researcher (at the first switch values E2's day was the whole pace) while nothing paces E2 | added after the integration's review (loop-1, merge-1) |
| 13 | `league/ops/preopen.py` | check 6 lists the options lanes' live-band families only | every equity family in a live band reads as "missing a band row": check 6 fails each trading day and hides a real options family without one | added after the integration's review (merge-2) |
| 14 | `league/ops/stall.py`, `league/ops/dlane_report.py` | the Validation alarm (runs, inherited verdicts, the families owed one) and Done's item 7 read (births, Gym runs, Validations) count the options lanes; the equity lanes' own are reported beside | one equity Validation reads a stalled options Validation pipeline as moving; a day when only the equity lanes worked reads as research running | added after the integration's review (loop-4, merge-3) |

**Patch 7, re-made.** The diff was written when E1's `PENDING_GATEWAY` still held E1's own four entries. E1's last
commit moved those into `FORBIDDEN`'s own list and into the gateway's merge list, and left `PENDING_GATEWAY` empty, so
the hunks no longer applied. As applied: `PENDING_GATEWAY` holds exactly E2's five modules, `FORBIDDEN` gains them, and
`league/tests/test_ci.py` pins the tuple, the path guard for every role and the updater's wall (`protected_changes`)
on two of them. What this buys now: no role may change the five files and the updater never self-deploys a change to
them. **Still open, outside this release:** the gateway's own merge list (`gateway/lib/protected.mjs`
`MERGE_FORBIDDEN`) does not name the five yet, because `gateway/` ships separately; its next follow-up adds them and
moves them out of `PENDING_GATEWAY`, as E1's did. Until then `league/tests/test_ci.py` allows exactly these five in
`FORBIDDEN` beyond the gateway's list.

**A15 (the reserve and the restart check) and its review's fixes needed no patch.** Everything they read, E1
provides: the isolated runner's `train(start, end)` and `decider`, the decider kinds (`kind_load`,
`kind(..., "decide", ...)`, `kind_drop`), the decide answer's `stats.calls` and `stats.errors`, and the ctx builder. A
hook that is missing fails safe: the restart check is then the House's failure (the version is not scored and cannot
pass; the third such failure of a version raises the `elane_train_state` alert, once), never a pass.

## Carried from E2's A15 review, for the captain (nothing here is a patch today)

- **The reserve's bars reach Train as look-back.** E2 runs no session of 2020-2021 and keeps no row, figure or day of
  it. But E1's runner hands a 2022-2024 run its NEEDS `history` + 1 sessions before 2022-01-03 (up to 505: E1's fix
  a00ab9f9 gives the first decision its whole window), so the 2022-2024 Train figures of a program with look-back
  are functions of 2020-2021 bars, and even a program with no look-back reads the last 2021 session
  (league/tests/test_elane_e2_e1.py `ReserveOnE1` says exactly what holds). If the later Thresholdout accessor needs
  those bars unseen too, that is a new change in E1's runner or store (a blanked look-back, e.g. a `history_floor`
  day), which E2's files cannot make; it would cost a long-look-back program most of its 2022.
- **For E1's owner: a program's own failed decide, live.** The Gym engine exits a program's lots after two failed
  decides in a row (EQUITY.md). Live, the child's decide answer carries no such flag, and `EquityBook._decide` treats
  only a failed decider request, a missing result or `ok` False as failed, so a program whose own decide raises twice
  keeps its lots until `max_hold_sessions`. E2 does not lean on either behaviour (its restart check compares
  `stats.errors`), so a program whose decide fails only after a restart is refused on Train whichever way E1 settles
  it.
- **Decided in E2, and the captain may move it (one constant):** a value a program carries from session to session and
  updates in place (a running sum, a peak since entry) fails STATE, because ctx's history is re-adjusted each session;
  the cure for an author is to recompute from `ctx.bars` at every call.

## What the integration's review found, and what was done (three reviewers, Oct 10-11)

Each has a test that failed before and passes after; the blockers and majors first.

- **E2's dollars paused the options researchers and nothing paced E2** (blocker; patch 12). E2's dollars are now a
  share of the Sail model line, counted apart: `elane.e2.pace_share` (0.25) of `researcher.sail_usd_per_hour` is E2's
  hourly pace, read from the swarm's own meter for E2's keys before each model call; E2's day is `usd_day` and never
  more than a day at that pace, so the budget's floor tightens it; the researchers keep the line less what E2 took,
  at most its pace. FOR THE CAPTAIN: the split is `pace_share`; at the ceiling E2 has $2.00 a day and the first
  switch value `usd_day` 8.0 is a cap above it.
- **Pre-open check 6 failed once any equity family held a live band** (major; patch 13). E1's line.
- **A bred program could read its own profit since the run began** (major). The level rule now refuses RUN-START
  DEPENDENCE (the sleeve's dollars of the run against a constant, a PARAMS value or the run's anchor; their
  reciprocal, their log and a product with the anchor's reciprocal too), and the rubric
  and its facts name it. FOR THE CAPTAIN: the root is E1's screen (its floor's worlds never start flat while every
  judged window does), so the false-positive line beside a live trade is true only for programs blind to their run's
  start; the captain's seeds are (they read no dollar of the sleeve).
- **After an equity identity adoption a re-bred near-copy took a second look** (major; E1's code). Fixed at the root
  by E1 (8ffdc6bb, carried): the look's Train series stays with the look and `same_lineage` fails closed. A test here
  holds it for an E2-born family.
- **The admission checked one lineage for a spent try.** It checks the declared parent, every family of the slice
  with the same idea and the rebirth row.
- **The level rule missed natural shapes** (`ctx.bars.items()`, a helper handed a level, a lot's `.get`, numpy's
  `greater`/`subtract`/`mod`/`digitize`/`searchsorted`, `float('400')`, `400 + 0`, the ratio of two different
  symbols' prices). Each is refused now, and so are the same level put into a container of the program's own and
  read back (`closes[s] = c[-1]`, `xs.append(px)`, `STATE["px"] = px`), taken out of a `zip`, or read by a named
  lambda. The pass also stopped refusing scale-free programs for a placeholder a loop fills (`prev = None` ...
  `px / prev - 1`; a running low kept from a sentinel; the last call's price kept in STATE): a loop's refusals are
  kept on its second reading, and a key of the program's own that holds nothing yet is unknown, not zero.
- **Memory in an object of numpy's** (`np.typecodes`) survived the restart check and was shared by every run in the
  decider child. E2's own static MEMORY rule refuses it for every bred program. NOT changed: league/gym/safety.py
  and E1's child (both in an identity); FOR E1's OWNER, with the next identity move: the same rule in safety.py or a
  child forked a run, so the seeds' and the options Gym's programs are covered too.
- **A LOAD refusal's reason never reached its author; a disqualification's own words must not.** The record keeps
  the House's refusal text for LOAD, and counts, a line and a known exception class for DQ.
- **The audit could not complete while Sail's balanced window was stalled**, and each retry re-read one key (booked
  again; empty after the router's compaction; three empties failed the version). The audit skips a candidate whose
  fallback reaches the reviewer's model, asks the next candidate when the answer came from it all the same, and every
  question has a key of its own.
- **A timed-out call booked a hold E2's line never saw**, every other route was asked the same question, and the
  family asked again next round. The failed call is booked at its hold, ends its question, and the family backs off.
- **A route was "sampled" on its families' revisions.** The sample and the cheapest-route price read birth requests.
- **The Validation alarm and Done's item 7 pooled the lanes** (patch 14).
- **A standing failure of the House's never alerted** (no store, a child that cannot start): `elane_train_house`.
- **An idle Train round every ten minutes** while any family of E2's lived: a round starts only with work it can do.
- **E1's history + 1 slice** (a00ab9f9) made two reserve tests and the "504 sessions" wording stale: every 2022-2024
  run holds the last 2021 bar; the tests and the A15 sentences say so.

**The three identities still did not move**: these fixes touch `league/swarm/` (E2's modules, `loop.py`,
`policy.json`), `league/ops/` and the tests. E1's own review fixes, carried by the merge, move the equity identity
before its first look (E1's changelog says so); that is E1's move, not E2's.

## What the verification found (Oct 11)

An independent verifier read the head above (b08a91dd) and found no blocker and no major left. What it did find, as
done on E1's frozen head 05f83d9e:

- **The profit lock with no memory** (the residual of seal-1). The House sizes an entry as the asked share of the
  run's capital, so what a lot cost is that capital times a share the program chose. A bred program rebuilt the
  capital from its own lots (a lot's `qty` times its `entry` or `exit`, its `value` less its `pnl`, `exit` times `qty`
  less `net`) and held `ctx.cash` or `ctx.equity` against it: the reviewer's lock, lot for lot on synthetic stores,
  with nothing in STATE for the restart check to catch. The level rule now reads a lot's `qty` and what a lot cost as
  the run's anchor, follows the spellings (shares times a price, dollars over a price, a lot's dollars scaled by its
  own return, a product of dollars, a reciprocal, an exponent, `pow`, text, a call the pass does not know), and
  refuses the run's dollars written into a lot's `tag` (the House keeps a tag across a restart: the same lock, every
  session of the restart check matched). Found while closing it, and closed with it: a value that mixed the run's
  dollars with a level read as the level, so the reviewer's own lock written `(ctx.equity + px - px) / (ctx.budget +
  px - px)` was a ratio of two prices and passed; and ctx's counts read as unknown, so equity and budget each times
  `ctx.weekday + 1` passed too. The run's dollars now come first in a mixed value, and a count is of no unit. A lot's own return however it is written, a stop on several lots' average
  entry, a hold count and a size from `ctx.budget` pass as before. The rubric and its fact `run` name the capital
  rebuilt from a lot and end on the rule: a rule whose trading depends on how far the run is ahead or behind is
  refused, whatever its spelling. WHAT THE STATIC RULE STILL CANNOT SEE is in [ELANE_E2.md](ELANE_E2.md) under that
  name: above all a lot's weight in the sleeve set against its own return, which is the run's profit and cannot be
  told from an honest weight cap. A program built on it passes the static rule and the restart check, so there the
  two paid readers are the only guard. FOR THE CAPTAIN: the root is still E1's screen floor (no fresh starts).
- **The review's hold was read once for two calls** (nit). `EquityResearcher.review_step` reads `elane_yield.hold`
  again before the audit stage, so the audit never starts on dollars the review's own call has just used up.
- **A doubled clause in `version_text`** (nit): one clause now.
- **The pace split** (a note; the captain's decision). `elane.e2.pace_share` ships 0.25 with its bound 0 to 0.5,
  unchanged. The documents say plainly that the equity lanes' research spend is that share of the researchers'
  hourly pace, that `elane.e2.usd_day` is only a cap above it, and that the captain sets the share with the settings
  tool at switch-on. No code changed for it.

The three identities did not move: these changes touch `league/swarm/elane_review.py`, `elane_train.py`,
`elane_births.py`, their tests and the documents.

## What the integration added beside the patches

- **The screen is S2** (amendment A11). The equity architect's system text said the share screen S1 judges the
  Validation try and the look; it names S2 now, and so does the seal's docstring. No threshold and no outcome is in any
  text a generator or a reviewer reads (`league/tests/test_elane_e2_switch.py` holds both).
- **No idle Train round.** `EquityResearcher.due` is false while no family of E2's has a round to be given. Before,
  with `elane.mode` "gate" and `elane.birth_share` 0 (E1 on, E2's births not yet), an empty round wrote its clock and
  one event every ten minutes. (The review above took it further: no round without work it can do now.)
- **The shipped switches, tested on E1's real loop** (`league/tests/test_elane_e2_switch.py`): policy.json ships
  `elane.mode` "off" and `elane.birth_share` 0 with the code's defaults in `elane.e2`; the settings layers take
  `elane.birth_share`, `elane.e2.usd_day` and every other `elane.e2` key from swarm.json one key at a time, each held
  inside its bound in code; with the lanes off, or the share at zero, neither round starts and E2 writes no key, makes
  no event and asks no model; one equity pass on the real router is born and booked.
- **The three identities did not move** (read before the merge and after the last commit): the equity evidence
  identity and its list (A13), the options execution fingerprint and the money digest. E2 adds no file to what any of
  them hashes, and none of those files reads an E2 module (the same test).

## What E2 reads of E1 (no patch)

- `SwarmStore.add_family` takes "etf" and "stock" for a spec whose `lane` is "beta" or "equity"; `families(alive=,
  lanes=)` keeps the equity families out of every options read.
- `elane.on`, `elane.cfg`, `elane.LABELS`, `elane.BETA_NOTE`, `elane.SEEDS_KEY`, `elane.INPUTS`, `elane.CLASSES`,
  `elane.isolated_runner(root)`, `elane.reviewed` (the record E2 writes), `elane.next_try` (patch 5 runs after it).
- `cards.validate` for equity cards and `cards.RebirthIndex` with its lane-scoped equity rows.
- `evaluator.equity_identity` (each E2 verdict's stamp) and `evaluator.adopt_equity` (which clears `best_version` and
  `review`; E2's round restores both for a pass that stands).
- The isolated runner, shared by E1's tournament and E2's Train round (E1's decider serializes its calls under one
  lock): `Isolated.train(code, params, name=, start=, end=, k=)` for each Train span, and for the restart check its
  `decider`, the decider kinds, the decide answer's `stats.calls`, `stats.errors` and `stats.disqualified`,
  `ctx.inputs_from_bars`, `ctx.lot_row` and `ctx.closed_row`. E2's instances are keyed
  "e2-state:<family>:<span>:<a|bN>" and dropped when the check ends.
