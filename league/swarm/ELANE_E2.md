# Release E2: the swarm breeds share programs for the BETA and EQUITY lanes

E1 gave the equity lanes their live path, engine, store, screen and three captain-seeded programs (league/equity/
INTERFACES.md). E2 makes the swarm itself breed them, around the clock: the architect proposes equity-lane families
with their first program, a minimal researcher iterates each on Train, the first version to pass the Train bar AND the
equity review takes its lineage's one Validation try (E1's look waits for that review on every program the captain did
not seed), and the model routes are chosen by measured yield per dollar. No figure appears here
or in the code: the bar's constants are rules, and the Train map shown to agents is computed on the House from the
swarm's own Train runs.

## The switch

`elane.mode` "gate" (E1) AND `elane.birth_share` above zero. E1 ships the lanes with `mode` "off" and `birth_share`
0.0, so E2 does nothing until the captain sets both in swarm.json. The equity researcher (Train) needs `mode` "gate"
alone, so families already born finish their Train research if births are paused. Rollback: `elane.birth_share` 0.0
stops births at once; `elane.mode` "off" stops everything E2 does (E1's own rollback).

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
     refutations only, while `architect.card_rebirth` is "refuse"), a continued lineage that has no try (no seeded
     program and no Train pass in it), and the quota. The card vocabulary shown is the equity cards' own (E1's
     `elane.INPUTS` and `elane.CLASSES`, no implied vol, chain, skew or intraday holding). A born family's spec carries `lane`, `symbols`, `agenda`, the
     card's sha and `e2_route`; a program that passes the static checks is its version 1.

2. **Train** (`league/swarm/elane_train.py`). THE TRAIN YEARS (amendment A15) are 2016-19 and 2022-24, seven years. A
   version's Train run is two runs of E1's isolated runner, one a span (2016-01-04..2019-12-31 and
   2022-01-03..2024-12-31), each starting flat, summed. 2020-2021 is THE RESERVE, kept for a later accessor: E2 runs no
   session of it, and a result that carries a row of 2020 or 2021 is refused whole exactly as one of 2025 or 2026 is, so
   no 2020-2021 P&L reaches a family's record, the Train map, the yield ledger or a generator. The Train map, the
   briefs and the architect's text say "Train years 2016-19 and 2022-24". (The 2022 run's first decisions look back on
   2021's bars as history, as a Validation run looks back on 2024's; no session of the reserve is ever traded or
   scored.)

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
     fails; one that only caches values it can recompute from ctx passes. How: through E1's decider kinds (`kind_load`,
     "decide", `kind_drop`), per Train span, instance A is loaded once and instance B is loaded fresh every 20
     sessions; at every decision session both read the same ctx, built by E1's ctx builder from the span's own 1.0x
     run (its bars, open lots, closed lots, cash, equity and caps), so only memory can make their intents differ.
     NEVER A SILENT PASS: each answer's `stats.calls` must equal the decides its instance was asked since its load, so
     an instance the child reloaded is caught whether or not the decider counted a restart (E1's `Decider` reloads its
     instances into a child that died between two requests without counting one); a check that cannot run or finish
     (no decider, no call count in the answer, a reloaded or missing instance, a span with no session) is the House's:
     the version is not scored, cannot pass, and the `train_max_errors`-th (third) failure in a row is an alert
     (`elane_train_state`). A session an instance was disqualified at matches nothing. What the check does not
     catch, stated: memory that changes the intents of fewer than 1% of the sessions, and whatever the run's record
     does not keep for the ctx (the intents the engine refused: `ctx.rejects` is empty for both instances).
   - WHAT A VERDICT IS: only the program's own doing is judged: its runs finished (the bar), it was disqualified by its
     own errors ("DQ"), the child refused to load it ("LOAD"), the child failed its run (or its restart check's
     decides) `train_max_errors` times while other programs' Train judgments completed ("RUN"), or its intents changed
     when its STATE was emptied ("STATE"). A failure of the House's (no equity store yet, the store being rewritten, a
     decider child that could not start, a restart check that could not run or finish, "no_data", a result outside the
     Train years) scores nothing, spends no budget and asks no model: the family backs off (doubling, at most six
     hours) and is tried again; a result outside the Train years is also an alert.
   - THE RESEARCHER (`EquityResearcher`, minimal): each round gives a few families one step: re-score a stale pass,
     review a bar pass, score the newest version, or ask the family's birth route for its first program or a revision
     (the brief holds the card, the agenda prior, the bar and the family's own Train versions and review reasons only),
     or retire it. The first version that passes the bar AND the review ends the research: it is the lineage's one
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
     PARAMS value is refused before the program is stored or run (`check_code`); ratios of levels are untouched.
   - THE PAID REVIEW AND AUDIT, at a version's first bar pass and before it is the Validation try: two different models
     (`review_routes`; the audit never on the reviewer's model) read the exact program, its card and its own Train facts
     under the gate's leakage rubric adapted to daily share programs (absolute levels, calendar reconstruction,
     lookahead). A failure must be grounded (a verbatim excerpt, a contract reference, a counterexample), else it reads
     unclear; `review_max_unclear` unclear reads fail. A failure is a Train failure of that version ("REVIEW") and spends
     no try. The review's dollars are E2's (`usd_day`), on ledger rows of their own ("review:<route>").

4. **No feedback** (`league/swarm/elane_seal.py`, A9 D3). No Validation or look outcome of a share program reaches a
   generator. The equity generators read equity families through `train_facts` only (birth facts and E2's own Train
   record; never a band, a retirement, a validated version, E1's try, look, floor or sigma, a look row, a forward
   record, or a graveyard lesson someone else wrote). The options generators read no equity-lane graveyard row at all
   (architect.py: the digest, `graves`, `unseen`, `graveyard_ids`; researcher.py: the `graveyard` tool; game.py's
   `visible_graveyard` by patch 4, for the diagnostician). The test is invariance: two stores that differ only in what
   happened after Train give the same equity request, researcher brief, route choice, Train map and options graveyard
   reads (league/tests/test_elane_e2_seal.py). THE RESERVE (A15) is tested the same way: two markets that differ only
   in 2020-2021 give every E2 record, stored run, map, ledger and generator read byte for byte the same, none holds a
   figure or a row of those years, and a runner that leaks a 2020 row is refused whole.

5. **Yield per dollar** (`league/swarm/elane_yield.py`). One ledger row a model route ("sail:<profile>",
   "openai:<model>", "claude:<role>"): requests, answers, failures, dollars (births and research), births; the Train
   counts are read from E2's records, and the operator's report adds Validation entries, looks, looks passed and live
   programs, each per dollar. THE ROUTE CHOICE: with no births anywhere, the first route of `elane.e2.routes` (cheapest
   list price first); a route is sampled at `min_births` births OR `sample_requests` requests (answered or failed: a
   route that never bears is measured at zero); before every route is sampled, every `explore_every`-th request goes to
   the unsampled route furthest from its sample and the rest DEFAULT TO THE CHEAPEST ROUTE THAT HAS PRODUCED BIRTHS
   (the lowest mean dollars a request); once every route is sampled, every (`explore_every` x routes)-th request goes to
   the least-requested route (no route starves on early bad luck) and the rest to the most Train passes per dollar,
   smoothed ((passes + 1) / (usd + the pooled dollars a pass); ties: births per dollar, then the cheaper request). The yield the choice reads is Train passes, never a later stage: a choice made on look
   outcomes would feed the holdout back into which model writes the next programs (A9 D3). A family's revisions are
   asked on its birth route, so its cost and its yield sit on one row. `usd_day` caps E2's model dollars a UTC day.

## The files

| file | what |
|---|---|
| `league/swarm/elane_births.py` | the switch, THE EQUITY QUOTA, the request's blocks, the equity pass and its admission |
| `league/swarm/elane_train.py` | the Train years and the reserve, equity-v1 with its restart check (STATE), what a verdict is, the record, the identity, `may_validate`, the Train map and graveyard, the agenda, the equity researcher |
| `league/swarm/elane_review.py` | the equity review: the level rule, the paid review and audit's rubric and grounding, the record E1's look reads |
| `league/swarm/elane_yield.py` | the route ledger, the operator's report, THE ROUTE CHOICE, one route a question |
| `league/swarm/elane_seal.py` | what of an equity family a generator may read; the graveyard filter |
| `league/swarm/architect.py` | `equity_due`, `equity_pass`; equity rows out of the digest, `graves`, `unseen`, `graveyard_ids` |
| `league/swarm/researcher.py` | equity rows out of the `graveyard` tool |
| `league/tests/test_elane_e2_*.py`, `elane_e2_fakes.py` | births, Train (the seven years, the restart check), review, seal (D3 and the reserve), yield; E1's names faked as INTERFACES fixes them |
| `league/tests/test_elane_e2_e1.py` | E2 on E1's own code with the patches (skipped on the skeleton): patch 5 in E1's `equity_round`, E1's `reviewed`, adoption, the lane-scoped graveyard, patches 9 and 10; A15 on E1's runner, ctx builder and decider (in process and a real child killed mid-check) |

## Settings (`elane.e2`; every default in code, the policy.json block in patch 6)

Births: `births_every_seconds`, `births_refill_seconds` (while fewer than `start` families research), `start`,
`max_alive`, `min_per_pass`, `max_per_pass`, `window_hours`, `births_max_output_tokens`, `births_effort`,
`families_shown`. Train: `train_budget`, `train_max_attempts`, `train_max_errors`, `train_every_seconds`,
`train_per_round`, `train_max_output_tokens`, `train_effort`, `refuted_cell_cap`. Review: `review_routes`,
`review_max_output_tokens`, `review_effort`, `review_max_unclear`. Routes: `routes`, `min_births`, `sample_requests`,
`explore_every`, `usd_day`. Each is held to its bound in code; a malformed value is its default.

## The patches (league/swarm/ELANE_E2_PATCHES.md)

E2 edits no file E1 owns. Nine patches for the integrator, each an exact unified diff against the E1 head the patch
file names (feat/equity-e1), applied together to a tree of that head plus this branch's files and tested there (the
patch file says which modules): the loop's two rounds; the birth quota's window skipping equity births;
`game.visible_graveyard` dropping equity rows and the learning game's ceiling counting options families; the tournament
validating an E2 family only where `elane_train.may_validate` allows; the `elane.e2` policy block; the five modules
protected (E1's `PENDING_GATEWAY`); the operator's yield record in the dlane report; the options population's floor in
`store.retire_gym`; the operator's stall facts and the pre-open population check counting the options lanes only.
E1 already scopes `dlane._born` by lane, so the release before's patch 2 is gone. The isolated runner is shared by E1's
tournament and E2's Train round; E1 hooks' decider serializes its calls under one lock.

A15 added no patch and changed no diff: the Train spans and the restart check use what E1 already provides (the
runner's `train(start, end)` and `decider`, the decider kinds, the ctx builder; the patch file lists them), and the
restart check's instances live in the swarm's own decider child under keys of their own, dropped when it ends. Only
patch 10's description moved (a version is four Train runs now, so E2's runs an hour doubled).
