# Release E2: the patches in E1's files, as applied

This file was E2's list of changes for the integrator. It is now the record of what was applied: nothing here is left
to do. E2 (`feat/equity-e2`, carried at 04ca26c9: its A15 review fixes included) was merged into E1's final head
8e11986b on branch `feat/equity-e2-int`, and E1's later commit bb0f2671 was merged in after it; E2's own files
(`league/swarm/elane_births.py`, `elane_train.py`, `elane_yield.py`, `elane_seal.py`, `elane_review.py`, their tests,
and its branches in `league/swarm/architect.py` and `league/swarm/researcher.py`) merged with no conflict, and each
patch below went in as one commit, in this order (11 was found by the full suite and added at the integration). The
numbers are the ones the code's comments and docstrings name ("patch 5", "patch 9"). The design is in
[ELANE_E2.md](ELANE_E2.md).

| # | file | what | without it | applied |
|---|---|---|---|---|
| 1 | `league/swarm/loop.py` | the two rounds: `elane` (`Architect.equity_pass`) and `elane_train` (`EquityResearcher.run`) | E2 never runs | as written |
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

## What the integration added beside the patches

- **The screen is S2** (amendment A11). The equity architect's system text said the share screen S1 judges the
  Validation try and the look; it names S2 now, and so does the seal's docstring. No threshold and no outcome is in any
  text a generator or a reviewer reads (`league/tests/test_elane_e2_switch.py` holds both).
- **No idle Train round.** `EquityResearcher.due` is false while no family of E2's has a round to be given. Before,
  with `elane.mode` "gate" and `elane.birth_share` 0 (E1 on, E2's births not yet), an empty round wrote its clock and
  one event every ten minutes.
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
