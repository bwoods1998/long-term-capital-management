# Operating the options House

How to pause, deploy, roll back, inspect and recover the House, the gateway, the data box and the
Gym, and the switches that govern them. The design is in [design.md](design.md). Commands run from
the repository root on the owner's machine unless they say "on the box". Sections that depend on
the swarm or live path describe their implementation, not evidence that production trading is
enabled. This page describes the tree it is in, release V3-A part 1, which is live since Oct 3, 2026: **Now** says
what production runs today. Current direction is in [the goal](goals/LTCM_OPTIONS_SWARM.md); the old operator's page
is [archive/docs/operations.md](../archive/docs/operations.md).

## C3 (A45) of the scaling plan (Oct 15, 2026): the Scaled band, shipped dark: `feat/scale-c3` (stacked on C2), not deployed

C3 builds the scaling plan's ladder (a program that beat its own same-risk buy-and-hold on live closes, judged outside
the House at each Done checkpoint, sized up one rung at a time) and SHIPS IT DARK: no rung is live, and with no pin-sha
row every sizing, line and reading is C2's exactly. The first rung is Blake's later deploy of a pin and of its sha256
row, after Done's first checkpoint receipt; every raise after it is another such deploy (plan 11 item 7).

- **The rows** (`league/constitution.py`, the block `equity_money.scaled` under the table; shares and multiples only,
  never a dollar; reader league/equity/bands.py `scaled_settings`, never league/live/money.py):
  - `pin_sha256` "": DARK. A sha256 here is the pin's bytes' (the pin holds E_P and the rungs in dollars and words; it
    is private, never in the repository). C2's E_P is read from the re-ratification of the very release that carries
    this block, so that release cannot carry the pin's sha256: the row ships unset (the captain's decision).
  - `rungs` R1 0.50, R2 1.25, R3 2.25, R4 4.00, R5 6.75: each rung's sleeve as a multiple of E_P (the plan's table 3.2);
    `max_sleeve_share` 0.50: no sleeve above 0.50 x E (the Sized sleeve bound's own top).
  - `lines`, THE SCALED LINES (Blake's amendment of his goal's item 4): `in_force` false, so nothing goes past R1 and no
    lot carries the Scaled mark; with it true, `window_share` 0.18 x the Scaled sleeves in force over the last
    `window_sessions` (20) sessions (the worst net stretch, as the Probe window's), `total_share` 0.36 x the largest
    Scaled sleeves reached (net, since the ladder's start), `program_share` 0.10 (the program line from R2), and
    `family_line_probe_only` false (plan 3.4's third loosening, separable: the swarm's -$300 family line reads
    Probe-marked lots only).
  - Bounds: each multiple and share at most the plan's (a row may only tighten), rungs never decreasing, the window at
    least 20 sessions, the sha "" or 64 lowercase hex. A table without the block is dark.
- **The pin and the setting.** The House reads the same private pin C2 reads (`/workspace/state/scale-pin.json`). From
  C3 on it may also hold `plan_sha256` (the plan's) and `rungs` {"eq|<family>|v<N>": 0 to 5} (a pin that names a rung
  must carry the plan's sha256); C2's E_P reading is untouched by them. A rung is read ONLY from a pin whose bytes are
  the row's sha256. A program's rung is the LOWER of the pin's and the swarm's setting `elane.scale` (`swarm.json`:
  `{"rung": n, "programs": {"eq|<family>|v<N>": n}}`, each 0 to 5, default 5 and none; a setting may only lower;
  unreadable is the last good value, else every rung 0, and an unreadable setting sizes at Probe that minute). "Stop
  the ladder" is `elane.scale.rung` 0, the same evening. A LOWERING STICKS FOR THAT PIN (the ratchet, kept per pin
  sha256: the rung the pin was first read at, at most R1 without the lines, lowered by every lowering of the setting
  seen after it, for a seated program or not), so putting the setting back raises nothing, nor does switching the lines
  on later: only a new pin, Blake's deploy, raises a rung again (plan 4.2). A cap already in `swarm.json` when a new pin
  is first read holds while it is there and is not learned (that pin is Blake's rung); an unreadable setting teaches
  nothing.
- **Sizing at a rung** (league/equity/live.py `EquityBook._scale_for`): a live share program in the Probe band (never a
  panel, a Sized program or an options family) sizes at min(its rung's multiple x THE MATCHING PIN'S E_P, 0.50 x E),
  never through C2's frozen pool (`_sleeve_equity`). The account's walls bind as before through `size_entry`: an ETF
  at most 0.50 x E across all programs, 1.00 x E invested, the cash reserve. The decide's view shows the same sleeve.
  A newer version of a family is at Probe at once (the pin names a version).
- **The marks.** An R1 buy and its lot carry the PROBE mark: they count in the $400 window and the $800 total (closes
  and open risk), EDM1's -$300 line and the swarm's -$300 family line, as any Probe lot. R1 is a loosening of A37's
  0.33 sleeve for one program, said in plan 3.2 with A37's measured costs. From the yes, an R2-and-up buy carries the
  SCALED mark (`eq_orders.probe` 2); its lot has `probe` 0 and `info` {"rung", "scaled"}: its close counts in the Scaled
  lines, never in the Probe window, the total or EDM1's line; its open risk leaves the Probe room of both lanes
  (`probe_figures`, the one path by which equity open risk reaches either; verified: `equity_open_risk` is display
  only), and a Scaled entry is sized to the Scaled room (the lower of the window's and the total's, less the Scaled
  open risk at the shared weights). While the lines are not in force a Scaled-marked lot counts as a Probe one.
- **The House's own step-downs** (`_scale_now`, every minute, and D3 at each entry's sizing too; plan 4.3): D3, a
  program line hit (EVERYTHING the program version realized, every real lot whatever its marks, since its last rung
  change at most -$300 at R1 and -10% of its sleeve from R2; or since it first reached R1 at most the line of the
  highest rung it reached): that program back to Probe, for good. D5, the Scaled window reached: Scaled opens pause (no
  Scaled entry fits the room), said once; the down-one-rung is the captain's setting. D6, the Scaled total reached:
  every program back to Probe and that version of the plan closed FOR GOOD (kv `eq_scale` keeps every closed version
  and every version the ladder ran under; a pin of a closed version finds it closed; only a version never run on this
  box reopens the ladder, with its window and total counted from that minute and from no sleeve, and one error-level
  standing alert dated when its pin was written). Every other step-down (D1, D2, D4, D5's down-one-rung, D8) is the
  captain's same-day `elane.scale`, from the receipt, and D7 is the pin's version key. So after a kill switch or a stop
  clears, Scaled programs resume at their rungs unless the captain lowered them. Nothing is ever sold or placed by a
  rung: lots exit by their own rules.
- **A pin that does not match its row** (none there, unreadable, another file, rungs that cannot be read): NO NEW SCALED
  LOT. A program this box last read at a rung waits (`SCALE_REFUSAL`; its entry is missed at its cut-off), every other
  one trades at Probe, exits go on. The Probe and panel pool then sizes on min(E, the E_P of the LAST PIN THAT MATCHED
  the row on this box, kv `eq_scale_ep`), never on the mismatched pin's (C2 alone would follow any readable pin), and
  with no matching pin ever read on this box no equity open goes at all (`SCALE_POOL_REFUSAL`, House-wide, as C2 for
  a pin never read). One standing error alert a process (`began_at` its first minute), health `scaled` `state`
  "mismatch", and the pre-open check FAILS (league/ops/preopen.py). The plan's section 9 says "no new equity lot":
  the build narrows that to no new Scaled lot once a matching pin was read here (an amendment for the captain's
  packet: it keeps Done's pace and the consistency clause; the pool cannot follow a pin the row does not name). While
  the row is "" (dark) all of this is C2's exactly.
- **Fail closed** (the review of Oct 15): a memory (`eq_scale`) that cannot be read, or that is gone once it was written
  (`eq_scale_seen` remembers it), sizes every program at Probe, is never written over, and is one standing error alert
  dated its first minute (`eq_scale_unread`; health `scaled.state` "memory"; the pre-open check fails; repair it from
  the private ledger, and only removing both keys on purpose is a fresh start); an unreadable `elane.scale` sizes at
  Probe that minute and notes nothing (no rung change, no ratchet, no window reading); D3 is
  judged at each entry's sizing too, so a close of that very minute sends the program back before its entry; a rung that
  changes during an entry (the setting, a program line) sends no more shares under other marks (one intent, one lot,
  one mark); a line of zero (a row tightened to nothing) is hit by the first loss, never by no loss.
- **What is kept** (private live.sqlite, kv `eq_scale`): each program's rung as last read, its last change, when it first
  reached R1, its highest rung, the programs sent back, the ladder's closure, the largest Scaled sleeves reached
  (dollars: the total's base), and since when the pin has not matched. Records `equity.scale` (private ledger kind).
  Health `scaled` {state, why, lines, rungs, out, closed, window, since}: never a figure, never a sha.
- **Dark is C2 exactly.** `league/tests/test_scaled_inert.py` runs one synthetic book through the House's code (an open
  window and a close window, fills, an exit, a working buy, a panel, a Sized program, closed lots of each mark) and
  compares every sizing stated to `size_entry`, every order and lot (marks and `info`), the decide views, the panel's
  budget, the equity Probe figures, both lanes' Probe budget and room, the EDM1 records, the forward rows, the Done
  meter's equity closes, counts and beside-figures and the family line with `league/tests/fixtures/scaled_inert_c2.json`,
  which the same scenario wrote on C2's head (22646a97) under Python 3.14 and 3.11: identical, the book's own memory
  too. With the pin's own row and the ladder stopped, every sizing, line and reading is identical. (A set row that no
  pin on the box ever matched opens no new equity lot: plan 9, not inert by design.) Three independent lens reviews
  found 0 bytes moved in their own dark scenarios. The rules: `league/tests/test_equity_scaled.py`.
- **Identities.** Money digest `4cd610a5` -> `558dc3a2`, constitution `18636b3f` -> `d4e59a79` (`PINNED_DIGEST`); with
  the block left out both are C2's exactly (`league/tests/equity_design.py` `DIGESTS_C2`, `before_scaled`). The options
  execution fingerprint `b60410ad` and the equity identity `78022ca6` do not move: league/equity/live.py, bands.py and
  families.py and league/swarm/elane.py are plumbing outside both, and no file of league/live/, the Gym or the equity
  evidence changes.
- **Deploy**: ONE owner release with C2's parts A and B (after release 1016a), never 12:55-20:05Z on a trading day; the
  standing grant re-ratifies on `558dc3a2`, and C2's pin step reads THAT ratification. Verify: the ids above, health
  equity `scaled.state` "dark", no `equity.scale` record, the pre-open check's line "the Scaled band is dark".
- **Rollback**: the release before C3 ONLY while no Scaled-marked lot has ever existed (count them read only:
  `SELECT count(*) FROM eq_lots WHERE info LIKE '%"scaled":true%'`); after that only `pin_sha256` "" in one owner
  deploy, because C2 counts only Probe-marked closes, so past Scaled losses would escape both budgets. Going dark (or
  withdrawing the yes) after Scaled losses puts every Scaled lot, open or closed, into the Probe window, the $800 total
  and the room, which can stop the Probe opens of BOTH lanes. Open lots exit by their own rules.
- **Where the build and the pinned plan differ** (the three lens reviews' calls: (a) accepted as built, (b) fixed, (c)
  an amendment for the captain's packet): 1 (c) plan 9's "no new equity lot" narrowed to no new Scaled lot once a
  matching pin was read here (the pool on the last matching pin's E_P; none ever matched, no equity open), and the
  deploy preflight not built yet (owed in `ship_house.sh` before the first rung); 2 (a) the account-size check of plan
  3.2 / 4.2 left to the receipt (each sleeve at most 0.50 x E, every account wall through `size_entry`); 3 (a) the
  per-pin ratchet, stricter than the plan; 4 (a) the step-downs split between the House (D3, D5's pause, D6) and the
  captain's same-day setting (D1, D2, D4, D5's step, D8), told to Blake; 4b (a, b) D6 on realized loss, a closed
  version closed for good; 4c (a) D3 counted from the House's first reading of the rung; 4d (b) both program lines
  read everything realized; 5 (a) `family_line_probe_only` a separate row Blake's yes must set; 6 (a) withdrawing the
  yes or going dark puts every Scaled lot in the Probe budget (told to Blake); 7 (a) elane reads live.sqlite read only;
  8 (a) the smaller ones: Scaled lots keep their Probe slot, the pin's name, health's `scaled`, a refused Scaled entry
  counts toward the idle clock, every rung raise a captain build, no rung status in a public alert. The CHANGELOG's C3
  entry holds the same table.

## C2 (A45) of the scaling plan (Oct 15, 2026): the options sizing-up step parked, and the Probe pool frozen at E_P: `feat/scale-c2`, not deployed

C2 is the scaling plan's precondition for any deposit or ceiling release, built in two commits so the owner can deploy
the options row alone first. Every part is a tightening and changes no size at today's E.

**Part B, the Probe pool frozen at E_P** (`league/equity/live.py`: `PROBE_PIN_FILE`, `read_probe_pin`,
`EquityBook._pin_now`, `_sleeve_equity`; plumbing, outside the options fingerprint and the equity identity; the
review of Oct 15 made the pin's reading survive a restart and a lost file):

- **What it does.** E_P is the sizing E on the day C2 is deployed, in dollars, in a PRIVATE pin file on the House's
  state root, `/workspace/state/scale-pin.json` (a JSON object whose `probe_e_usd` is E_P; the owner's step writes it
  once C2 is live, from the grant's capital ratified around C2's money digest, and before any deposit or ceiling
  release; from C3 on it also carries the plan's sha256 and the rungs, which this part does not read). It is never
  committed, never in a test and never in a published file. Once it is read, every program's sleeve sizes on min(E,
  E_P): the Probe sleeve (`probe.sleeve_share` x E), the panel's (`panel.sleeve_share` x E) and a Sized one's (the step
  is parked), at the send (`_size`), at a share program's decide (`_inputs`) and at a panel's budget (`_panel_budget`).
  A deposit then never grows the Probe pool; an E below E_P sizes on E. What scales with E stays on E: an ETF's or a
  stock's share of E and the invested cap (the goal's walls); the shared loss budget is dollars and is untouched. The
  book reads the pin every minute (`tick`'s first step) and at each sizing.
- **THE FILE'S NAME IS NOT THE PLAN'S.** The scaling plan (section 9) gives the pin another name, one that carries the
  plan's target figure, which this public repository does not carry; so the House reads `scale-pin.json`
  (`PROBE_PIN_FILE`), a deviation from the plan, said here. The plan's script reads E_P from the private ledger, not
  from the pin, so nothing else reads the name; C3 and the captain's pin step use `scale-pin.json`.
- **No pin, and none ever read on this box, no freeze.** With no file there and no marker (below) every sleeve sizes on
  E, field for field as before C2, and nothing is recorded, alerted or written: part B deploys dark and changes no size
  until the pin is written.
- **What is kept.** A pin read is kept in the House's private live.sqlite (it holds the lots' and the cash's figures
  already; it is never a published file): E_P under the kv `eq_probe_pin_good`, and a marker with no figure under
  `eq_probe_pin` (the pin's sha256, when it was first read, and since when it has been unreadable, if it is). Health,
  the records and the alerts carry neither the figure nor the sha (a pin's bytes are guessable).
- **A pin that cannot be read fails closed, never to E.** Unreadable: not a regular file (a link, even to a good pin, a
  link to nothing, a directory, a FIFO, a device: never followed and never waited on), any read error, more than 64 KiB,
  not a JSON object, `probe_e_usd` missing, a bool, or not a finite number above zero; and a pin GONE once one was read
  on this box (the marker says so: a lost pin never turns the freeze off). Then every sleeve sizes on min(E, the last
  E_P read on this box), across restarts. Only when no E_P was ever read on this box does the send size NOTHING (the
  entry waits, as for any figure it cannot read, and is missed at its cut-off), and then every open is refused
  House-wide (`_open_block`), so the seat rule's open note leaves those sessions out of every seat's idle clock; the
  decide's own view (ctx.budget and its caps) reads E in that case, so no program is handed a budget of nothing, and
  what it plans opens nothing. A refused open still costs the consistency clause (A14 reads intents whether they
  filled), so that case is the one to fix first.
- **How it is told.** ONE error alert a process, written as a standing condition: an `ops.alert` row whose `began_at` is
  the first minute this box found the pin unreadable (kept in the marker across restarts), written through the book's
  record hook because the alert hook (league/live/step.py, inside the options fingerprint) carries no payload. The watch
  after a promotion counts one that began under the release before as inherited (league/watchdog.py `inherited_before`),
  so a bad pin does not roll every release back; one that began under the new release is its failure. Health shows
  `probe_pin` (`state` absent, read or unreadable, `why`, `since`, `held`), and the pre-open check FAILS on an
  unreadable pin (league/ops/preopen.py `check_equity`), so the stall mail says it before the open. Each change of state
  is a record (`equity.probe_pin`, a private ledger kind registered in league/ledger.py); its repair is a warning. No
  figure is in any of them.
- **What it does not freeze.** The options Probe structure (`options_money.probe.max_loss_share` x E) is read in
  `league/live/money.py`, inside the options execution fingerprint, so part B does not touch it: the plan holds it at
  today's dollars by each step's row, deployed before each deposit, which part A's tight end 0.005 allows.
- **Identities.** None moves: money `4cd610a5` and constitution `18636b3f` are part A's, fingerprint `b60410ad`, equity
  `78022ca6`. The grant holds as part A left it.
- **Deploy**: an owner deploy after part A (or with it), never 12:55-20:05Z on a trading day. Verify: the ids above;
  `health.json` equity `probe_pin.state` "absent" (no pin yet) and no `equity.probe_pin` record; the pre-open check's
  equity line tells "no Probe pin, and none was ever read on this box".
- **Proof**: `league/tests/test_equity_probe_pin.py` (no pin is E field for field and writes nothing; a pin below E
  freezes every sleeve, the walls on E; a pin above E sizes on E; the panel and a Sized sleeve follow; a regular file
  only, a FIFO never hangs; unreadable with none ever read sizes nothing and refuses House-wide; unreadable at a restart
  sizes on the kept E_P; a lost pin after a read stays frozen; the standing alert is inherited by the watch; the
  pre-open check fails on it; the figure is kept in one private key and said nowhere).
- **Rollback**: deploy the release before part B. To end the freeze without one, replace the pin (never remove it: a
  removed pin is read as unreadable once one was read on this box). No digest moves.

**Part A, the options row:**

- **The options row** (`league/constitution.py`, the comment above `options_money`): `options_money.sized.min_trades`
  20 -> 1000, inside its bound (20 to 1000) at its tight end, as `equity_money.sized.min_trades` was parked on Oct 11.
  Sized is the one route by which an options family's stake grows with E (Kelly on the lower bound, up to
  `sized.max_loss_share` a structure and `sized.family_share` a family) with no test against the same-risk
  buy-and-hold, and a Sized open carries no Probe mark, so its closes sit outside the $400 window, the $800 total and
  the program lines. With 1000 no options family reaches Sized (`money.sized_ok`), and a family the swarm holds at
  Sized is read back to Probe by the live path's band pass (`step._move_band`, `money.band_for`) while real money is
  on; nothing it holds is sold. The swarm's progress report shows `forward_trades` against 1000. The rule stays
  pre-registered as written (its own count is 20); the row is switched back only with a test that counts what Sized
  risks.
- **The bound's tight end** (`OPTIONS_MONEY_BOUNDS` `probe.max_loss_share` 0.02-0.10 -> 0.005-0.10): it lets a later
  step's row hold one Probe structure at the dollars it holds today while E grows. It admits only tighter rows; the
  row in force stays 0.10 x E. The bounds are no row of the constitution, so this moves no digest.
- **Identities.** The row moves the money digest `cfcc94b1` -> `4cd610a5` and the constitution digest `60796aed` ->
  `18636b3f` (`PINNED_DIGEST`); with the row set back the digests are main's exactly, so the bound alone moves
  neither. The options execution fingerprint `b60410ad` and the equity identity `78022ca6` do not move (no file of
  league/live, the Gym or the equity evidence changes): no evidence reset. `league/tests/equity_design.py` keeps the
  older pins as `DIGESTS_OPF1` (`before_options_park`), and every older table's helper sets the row back.
- **Deploy**: an owner deploy (the constitution is the owner's file), never 12:55-20:05Z on a trading day. The standing
  grant re-ratifies on the new money digest at the House's start (`league/ops/grant.py`; `scripts/live_trading.py
  --ratify` on the box if it refuses). Verify: the four ids above, the grant ratified on `4cd610a5`, real money on,
  and no `live.band` record moving an options family to Sized from the deploy on.
- **Its cost.** No options family can size up while it stands; a family with a real edge trades one Probe structure.
- **Proof**: `league/tests/test_options_sized_parked.py` (no family reaches Sized below 1000 trades, a Sized family
  read back to Probe, every Probe open planned the same, the tight end, the digests); `test_live_money` tests the rule
  at its own 20 (`pre_registered`).
- **Rollback**, one owner deploy: `sized.min_trades` 20 (re-pin `PINNED_DIGEST`); the money digest moves back and the
  grant re-ratifies.

## Release 1015e (Oct 15, 2026): the equity birth cells, research dollars by lane, the watchdog on an interrupted box, the equity book's own shares: `rel/1015e`, not deployed

Release 1015e is main `0b978378` (#557, the running release `20261015T075939Z-89d93d40bfda`) with three pull requests
merged, #552, #551 and #549, a follow-up to #549's watchdog and a docs pass. **Two deploys from one commit:** the House
by an owner deploy (`league/swarm/elane_births.py`, `league/ops/` and `league/ops/economics.py` are protected files),
never 12:55-20:05Z on a trading day, then the gateway (`npx --no-install wrangler@4.129.1 deploy` from `gateway/`).
**No identity moves** (fingerprint `b60410ad`, equity `78022ca6`, money `cfcc94b1`, constitution `60796aed`) and no
setting changes: the grant holds as it is.

- **The equity birth cells** (#552): the equity pass's request lists the cells the equity graveyard binds (**The
  equity lanes' births**, "The equity birth cells"). The binding itself is unchanged.
- **Research dollars by lane** (#551): the `dlane` report's `lane_yield` section (same section, "Research dollars by
  lane"). An operator's reading: nothing gates on it.
- **The account reading knows the equity book's own shares** (#549, the House half; `league/account_activity.py`,
  `league/ops/economics.py`). The reading predated release E1 and read every share fill on the account as an
  assignment's, so from the first real share buy (13:32Z Oct 12) every budget run's `budget.json` carried the error
  "the account reading names an event the book has not settled (blocking): p30 is unknown", and the site's Profit and
  the close economics' `reconciled` were unknown while the lane held a lot. It now reads the equity book's orders and
  open lots: a share fill on one of its orders is left out, and `shares_held` counts only shares beyond its open
  lots, so a real assignment beside held lots still waits for its own shares.
- **The watchdog asks an interrupted box back** (#549 and its follow-up, the gateway;
  [gateway/README.md](../gateway/README.md), the watchdog). A box Sail lists `interrupted_restorable` above the reserve
  is asked back with Sail's resume once a 15-minute window, at most 48 times an interruption, never forked; after 3
  calls or 45 minutes (at once on Sail's `terminal_unavailable`) the owner gets ONE message naming Sail's community
  Slack with the words to post. The six-hourly "the desks are not running" is quiet while the watchdog asks, and goes
  again once the 48 calls are used up and the box is still down. `/v1/health` shows the episode at `watchdog.restore`.
- **Verify after it** (read-only, ten minutes on): the ids above; `budget.json` `errors` empty (the account reading's
  block gone); the next equity births pass's request carrying EQUITY BIRTH CELLS; the next `dlane` report carrying
  `lane_yield`; the gateway deploy's printed version id (the rollback's target is the one it replaced).
- **Rollback:** the House, `python3 scripts/floor_box.py rollback` to `20261015T075939Z-89d93d40bfda` (main
  `0b978378`); the gateway, `npx --no-install wrangler@4.129.1 rollback <the version the deploy replaced>`. Nothing is
  migrated.

## Release U (Oct 15, 2026): E4 step two with panel seats through FWD1-R only, the SIP gap hand-off, a post-close checkpoint: `rel/u`, deployed 03:28Z Oct 15 (House `20261015T032807Z-35a60d3ba499`, main `aec0c8a5`, #548)

Release U is release T (`rel/e4-fwd1`, PR #546: E4 step one with A32, the forward screen FWD1-R, R-SEC), with the SIP
gap hand-off (`fix/nightly-sip-gap`, PR #545: **The source gap**, in the CHANGELOG) and E4's step two
(`feat/equity-e4-step2`: **The panel lane**, below) merged in, plus two changes of its own. Step two's probe wiring
(B1) is not in it (the captain's A34 (4): forward only).

**Panel seats come through FWD1-R only (the captain's A34, 18:42Z Oct 14, 2026, from study XS1-R).** XS1-R's verdict of
record is D3: no historical XS1 look, forward only (a memory-holding author passes XS1 as built at 10-99%). So the
House holds the panel's whole historical route in code, never in a setting (`league/swarm/elane_xs.py`
`A34_FORWARD_ONLY`, as R-SEC holds the sector programs'):
- **no sealed Validation try** for a panel family (`elane.try_open` False): a sealed pre-check would make its lineage
  one that reached one, which is never FWD1-R's case N, the one case A34 seats. Nothing is spent and nothing retires
  on it;
- **no XS1 look** whatever `elane.panel.look_rule` says ("hold", "xs1" or anything else): the look waits with "A34: no
  historical XS1 look and no sealed Validation try for a panel program ...", in its gate state, in the heartbeat's
  `equity.panel.look` and in the direction report's `panel_lane.look`;
- **a panel seat exists only on a FWD1-R forward pass seated through the panel pool** (`elane_xs.forward_seats`, once
  an equity round right after `elane_forward.step`, league/swarm/gate.py `equity_round`). `elane_forward.step` makes a
  case-N panel pass eligible (one a mechanism cell). The pool then makes it a Candidate of the panel pool, proven on
  the xs identity in force, when it is in the Gym band and not held, the lane is live, the pool has a free seat (the
  lower of `equity_money.panel.seats`, 1, and `elane.panel.seats`, less the panel families at Probe and the panel
  Candidates holding a forward seat), `elane_forward.seat_refused` is None (case N, the permit file still listing the
  pass of that version and run sha, ONE LIVE FORWARD SEAT A MECHANISM CELL over both types), and the verdict's engine
  label names the equity and xs identities in force. `elane_forward.mark_seated` is written in the transaction that
  moves the band: both or neither. The roster gives it its row (the verdict's words stand beside it), and the
  EquityBook seats it at Probe and sizes it by the panel row (0.10 x E). A family once seated on its pass is never
  seated again by this path;
- **any other panel Candidate is seatless** (league/swarm/bands.py `equity_seating`): one a historical look made, or
  a band written by hand, takes no row, no instance and no order, and the roster's `seatless_why` says A34;
- beside every trade of a panel program seated on a forward pass, the direction report states FWD1-R's sentence for
  it, which for a panel pass carries A34's two sentences (the zero-edge rate at its checkpoint; why there is no
  historical look).

**Switches and defaults.** Every one ships off, so release U trades nothing new on its own: `elane.panel.mode` "off",
`elane.panel.look_rule` "hold" (A34 holds every value anyway), `elane.panel.seats` 2 (it may only lower the row),
`elane.fwd1.mode` "record" (the job judges; it seats nothing) and
`elane.fwd1.seats` "off", and the money row `equity_money.panel` {"seats": 1, "sleeve_share": "0.10"}. No panel
program is seated until a FWD1-R panel pass exists (at the earliest about Fri Oct 23: five forward sessions after the
pin, A34) AND `elane.fwd1.seats` is "on" AND the panel lane is live (mode "live", the universe deploy, the I6, the twin
marker). With `elane.fwd1.seats` "off" nothing panel is seated; one seated before the switch went down keeps its seat
under the money rows' own demotion (as an ETF forward seat does), and `elane.panel.mode` under "live" takes it away
(league/swarm/elane_xs.py `seat_word`: its lots exit at the next open).

**A second Sail checkpoint after the close** (league/backup.py; **Recover**, below). The daily checkpoint falls where
the last success left it (about 13:28Z in October 2026). On every NYSE session day, from 45 minutes after the close
(16:45 New York: 20:45Z in summer, 21:45Z in winter; 13:45 after an early close) to New York's midnight, the House
takes one more, `league-YYYY-MM-DD-close` (the session's date), kept as long as the daily one (seven days, Sail's TTL).
Its ledger rows are `ops.deploy` rows with `what` "backup_close" and the session's `day`, so the daily schedule, its
alerts and the pre-open's backup check read the daily rows alone, as before; the pre-open shows the post-close one
beside, never as a condition. A daily checkpoint already taken after that close covers the evening. A failed try is
tried again on the daily one's backoff (30 min, 1 h, ...) while the evening lasts, and is a WARNING, marked "sail" when
Sail is why: never an error, so it never rolls a release back.

**Identities.** The options execution fingerprint `b60410ad` and the equity identity `78022ca6` do not move. The money
digest and the constitution digest move once, by step two's panel row alone: `5b95d73e` -> `de5ed74e` and `4ef472e1` ->
`111ede85`, so **the standing grant re-ratifies at the House's start**. The xs identity is `2f0083bc`, release T's
(step two does not move it).

**Rollback.** Repoint to release T (main of `6b0c41bb`) or to A32's main `47ed6872`; retire every panel family in the
store first (E4's own rule: a code rollback past E4 retires the panel families first). Before a panel program is
seated nothing of the panel trades, so the rollback sells nothing. The post-close checkpoints left behind expire at
their TTL; the release before keeps taking the daily one.

## The forward screen FWD1-R (Oct 2026): `feat/equity-fwd1`, deployed 03:28Z Oct 15 in release U

E3 records every equity program's forward days and judges nothing. **FWD1-R judges them**: a program may take a seat on
sessions that came after its code and the screen were frozen, so the judged sessions' contamination is zero by
construction (no model can have memorized days that had not happened). The captain adopted it as its review wrote it
(A33, 17:01Z Oct 14, 2026, from the study FWD1-1014: PREREG `7383626c`, RESULT, HOUSE-RULE-FWD1 and REVIEW "adopt with
fixes"), not as the study's headline. Rule: `league/ops/fwd1_rule.py`; job: `league/ops/forward_screen.py`; receipt:
`docs/benchmarks/forward_screen_fwd1.json` (v2); seat path: `league/swarm/elane_forward.py`.

**No identity moves.** Nothing under `league/live/`, `league/gym/`, `league/xs/`, no evidence module of
`league/equity/` and not `league/constitution.py` changes: the options execution fingerprint, the equity identity, the
money digest and the constitution digest are those of the tree it is cut from (`feat/equity-e4-m3` at `6f99652d`). It
ships in RELEASE T (branch `rel/e4-fwd1`): E4 step one merged with A32 (`feat/equity-e4-a32`, PR #544, which carries
PR #543), this screen, and R-SEC (below); release T's ids are E4 step one with A32's (the money digest `5b95d73e` and
the constitution digest `4ef472e1` are A32's sleeve, 0.50 x E at six seats).

**The rule** (one verdict a LINEAGE of the forward registry):
- **Who.** A lineage is judged on its REPRESENTATIVE, fixed before any forward day of it exists: of its rows with the
  lineage's earliest `first_day`, the lowest pid whose reason is train_pass, seed or live, else the lowest pid. Every
  version stays in the denominator. The job sights a lineage once, but it reads the representative again on each run
  until a forward day of it exists (`forward_screen.repick`, release 1015e). A passing version registered after the
  sighting with the same first_day then replaces a failed one, with an append-only `repicked` event. A re-pick changes
  which version is judged, never what it is judged as: the row's type, case, judged flag and reason stay, and a better
  pid that would change one is not taken. "No forward day" means: no row of the record for any pid of the lineage
  (`fwd_days`, `fwd_checks`, `fwd_ll`, `fwd_twins`, `fwd_lotgap`, `fwd_part`), no night of the record through its
  first_day, its first_day's session not yet open, and no judge row for it. The job is quiet from 09:00 New York on a
  session, so the night before the first_day is the last run that re-picks. A better pid not taken is written once as
  a `kept` event and the job warns. A store that cannot be read re-picks nothing. The placebo seed follows the new row
  hash, and is fixed from then on. CASE at FWD1_START: **N** when no version ever reached a sealed pre-check (an S1,
  S2 or XS1 Validation try, its pre-check or a look: the forward record's tags and the family's state); a PANEL
  lineage that reached XS1's is case **XS1**; an ETF lineage that reached one is NOT judged (no forward verdict for an
  S1/S2 look); a lineage that already trades (a live row) needs none; a stock program is not covered.
- **Days.** The representative's counted days (status "ok", no `audit_mismatch`) under ONE engine id, from FWD1_START =
  max(its first_day, the first session after the release carrying the pin began running).
- **Series.** ETF: r and r15, the live-like re-price r_ll in place of r where `fwd_ll` holds one (and r15 + (r_ll - r)
  for r15); PANEL: the residual x = r - w b and x15 = r15 - w b. Each day less g x sides (the weights of the shadow's
  lots in and out that session). g: ETF 2 bp a side, raised to the measured mean adverse gap a side of the closed live
  ETF lots (`fwd_lotgap.side_gap_bp`), rounded up; PANEL 3 bp until 20 live panel lots are measured, then the larger of
  2 bp and their measured gap, rounded up. A checkpoint row keeps the g it read.
- **Statistic.** At k = 5, 10, 15, 20, 30, 40, 60: t_k = mean / sd (ddof 1) x sqrt(k) by math.fsum; a pass needs t_k >=
  c_used, fsum(x) > 1e-12 and fsum(x15) > 1e-12, and for a PANEL lineage the placebo leg: at most 119 of 999 matched
  placebo portfolios (XS1's law, seeded by the receipt's sha and the representative's row hash) at or above t_k. PASS
  at the first checkpoint that passes; FAIL for good at 60; nothing judges a lineage after its verdict.
- **Bar.** c_used = max(c_G, c_own + 0.05) on the 0.01 grid (ineligible above 5.00): c_G PANEL N **2.06**, PANEL XS1
  **3.16** (E3's D2 3% kept beside the look's 12% a program), ETF N **2.61** (WEAK). c_own is the study's exact own
  floor (cap 0.12 case N, 0.024 case XS1) on the program's Train-era 60-session windows: its runs at k 1.0 and 1.5 over
  2016-19 and 2022-24 (ETF; S2's cells) or XS1's two Train segments (PANEL; XS1's cells), from the pools' third
  session (the House's `POOL_SKIP`), computed once a representative and only when a checkpoint's t reaches c_G.
- **Limits.** At most ONE live forward seat a mechanism cell (lane / agenda / universe group) at a time, ETF and panel
  alike; FGS (E3's 20/60/120/250 at 3%) is never also applied; one engine id a verdict: after an engine change a
  pending lineage WAITS until the new id holds its representative's rows for every judged day (E3's night writes the
  ETF rows, the panel night the panel rows hours later, a program the budget left stale a night later), then a judged
  day whose r, w, b or r15 moved voids it, unless it moved only because the vendor restated the store's history (both
  bars hashes known and different, and E3's own `restated` event, bars "moved", covering the day); one that leaves
  them as they were is carried, with an event naming the pid; a case-N lineage that reaches a sealed pre-check after
  its start is void (a panel pre-check refused before any Validation read, `reached` False, is none). A34: a panel
  lineage's only route to a seat is case N; a case-XS1 pass is recorded and takes no seat.

**What the receipt measured at these bars** (the study's own code on its pass-A arrays, Train-era data only: the
script reproduced the study's pinned bars 2.05, 2.06 and 3.16 first; at 2.06 every figure equals receipt v1's):

| type and case | worst-regime FP at zero edge: point / 97.5% bound | pass by 60 at zero edge, haircut world | power by 60, same world |
|---|---|---|---|
| PANEL N, 2.06 | 11.8% / 12.5% (IN, 60-day storm) | 9.0% at 3 bp (11.1% with no haircut) | +20%/yr 48.8% (ratio 5.4); +10%/yr 23.5% |
| PANEL XS1, 3.16 | 2.4% / 2.6% (with the look's 12%: at most 15%) | 1.8% at 3 bp | +20%/yr 16.6%; +10%/yr 5.1% |
| ETF N, 2.61 (WEAK) | 2.8% / 5.5% (no single family or regime cell over 15%; the worst S2-archetype cell 14.9%) | 1.4% at 2 bp | +10%/yr 2.4% (ratio 1.7) |

The receipt also carries the pass rates by checkpoint, by regime and decile, the fills table (with the panel's 3 bp),
the drift-kept rate of the ETF twins, the registry's expected zero-edge passes for 10 to 100 lineages, and the
loosenings with their costs. **The loosening, stated (A33):** E3 pre-registered its forward gate at 20/60/120/250
sessions and 3%; FWD1-R reads from 5 sessions at the goal's own 15% for never-looked lineages. Most early passes are
luck (45% of zero-edge panel passes come at checkpoint 5); an ETF forward pass says almost nothing about skill.

**The pin starts the clock.** policy.json `elane.forward_screen` holds the receipt's sha256 and every figure the
House prints (CI: `league/tests/test_fwd1_rule.py` `ThePin` holds the sha to the file and each figure to the
receipt's; the loader refuses a pin whose plan, bars, margin, haircut, caps or placebo law is not the code's). The job
writes the time the release carrying the pin began running (the deploy record's `promoted` verdict of the running
release, else its first sighting) once a sha, and FWD1_START is the session after the first close after it: deployed
before Thursday Oct 15's close, the first judged session is Friday Oct 16. Days before it are never judged; a lineage
registered earlier enters mid-run. **Whoever pins it must not read `fwd_days` first** (the review's F8).

**The job** `forward_screen` (league/ops/registry.py, after `forward_shadow` and after `forward_xs`; in a pause too;
skipped inside 09:00-17:30 New York on a session) reads the forward record and the swarm store read-only and writes
`<state>/forward-screen.sqlite` (append-only: the pin, the sides, the lineages, the own floors, the checkpoints of
record, the verdicts; its one UPDATE is a lineage's re-pick before any forward day, after its `repicked` event),
`<state>/forward-screen-permits.json` (ids and words only: no t, no P&L) and
`<state>/forward-screen-report.json` (operator-only: counts by type and case and status, the registry's expected
zero-edge passes against the observed, every pass's sentence and each stalled lineage's cause). Each day's SIDES (the
weights of the shadow's lots in and out, which the record does not keep) come from the representative's own forward
run in the job's own decider child (E3's `Shadow` slice, package J's panel run), kept for the days that run
reproduces, or that were RESTATED (after an ex-day E3 keeps the first-written r and no run reproduces it again: the
run's bars hash of the day's decision differs from the stored one and its lots in and out that session are the
record's); no line of E3's night changes. A would-be pass's reading (t, sums, haircut, live-like flag) is kept on the
night it is first read, and a checkpoint that waits on its floor or its placebo leg is judged on it. ONE PANEL STORE A
JOB RUN (every panel run reads one panel night's store: the ops child's 500 MB above its start holds the two maps once,
measured at the production panel's size), E4's clock rule (`elane_xs.steady`) on every panel run. Its child seconds:
`elane.fwd1.cpu_seconds_night` (900) A NIGHT, shared by the night's two runs, one run `run_budget_seconds` (300) and
never past THE DEADLINE (the earlier of its 1,800 s wall and the next pre-open, less 120 s; its grace 2 h, so the run
after `forward_xs` is done before the pre-open). A failure of the House leaves a checkpoint unwritten and marks
nobody; the next night reads the same first k days. THE STALL RULE: a lineage whose next step waited on the House on
five of the record's nights under one engine id is "stalled": no run, reported, nothing marked, asked again at a new
engine id; a lineage that waited goes after those that did not. Statuses in the permit file: pending, pass, fail,
void, ineligible, stopped (its representative stopped in the record), stalled, superseded (another receipt's).

**The sentence beside a forward-passed trade** (`fwd1_rule.beside`: in the verdict row and the report, and beside
every trade of a program seated on a forward pass in the direction report, `dlane_report.EquityScreens`): the type and
case, the checkpoint and the start, t against c_used (global and own floor), the shadow P&L (PANEL: residual) after
costs and the haircut, the worst-regime FP and its bound against the budget (case XS1: and the combined 15%), the
contamination sentence, power against the zero-edge rate IN THE SAME FILL WORLD, the WEAK flag (ETF always; PANEL at
checkpoint 10 or earlier), for ETF the program's OWN drift-kept rate from its own floor windows, and the registry's
forward passes against the expected number at zero edge.

**The seat path, built and OFF.** `elane.fwd1.seats` "off" (policy.json and the code). Turned "on" (swarm.json:
`"elane": {"fwd1": {"seats": "on"}}`): a lineage the permit file lists pending, pass or fail takes no sealed
Validation try (`elane.try_open`), and an unreadable permit file refuses every equity try; an ETF pass becomes a
Candidate THROUGH THE ROSTER (the seat rule in force decides its seat; the Probe money rows size and demote it) when
its family is in the Gym band with the judged version under the identity the verdict was read under, one live forward
seat a mechanism cell. **A panel pass is made eligible only**, case N only (A34) and one a mechanism cell at a time: no
panel seat exists in E4's step one, and the panel seat pool is step two's (`feat/equity-e4-step2`, B3). **The
obligation that pool takes on** (league/xs/E4_INTERFACES.md section 8, item 25): it seats a panel family on a forward
pass only when `elane_forward.seat_refused(store, fam, settings)` is None and records it with
`elane_forward.mark_seated` in the same transaction as the band move; `eligible(state)` alone is not the contract.
**Built in release U** (`elane_xs.forward_seats`; **Release U**, above): the panel pool's one way to a seat.

**Switches and rollback.** `elane.fwd1.mode` "off" stops the job (nothing judged; the forward record goes on);
`elane.fwd1.seats` "off" stops every effect on the swarm. Without the pin (`elane.forward_screen` absent, or a block
this code does not load) no verdict is read. A seated program keeps its seat under the money rules' own demotion.

**Sector, bond and gold programs are forward-only (R-SEC, release T).** The captain's decision from the widening
review of Oct 14, 2026 (A19 and A31 still hold for every historical look; A33's ETF case N is the one route): an equity
family whose symbols (the store's roots, its spec's `roots` and `symbols`) name anything outside the four index ETFs
(`league/equity/config.py` `INDEX_ETFS`: SPY, QQQ, IWM, DIA) takes **no sealed Validation try** (`elane.try_open`
False, so no 2025 pre-check) and **no sealed look** (`elane.look` holds it before the sealed run: no look spent, no
refusal row, no bad gate outcome, one "waiting" record), **whatever `elane.fwd1.seats` says and whether or not the
permit file lists its lineage** (`elane.forward_only`, code and not a setting). Nothing retires it for that reason: it
stays in the Gym band, case N for FWD1-R (ETF case N, bar 2.61, labelled WEAK), and its only path to a seat is a forward
pass with `elane.fwd1.seats` "on". A family whose symbols cannot be read, or that names none, is held the same way
(fail closed). An index-only family is unchanged; a panel family is not affected (A34 governs it). Every symbol outside
the four is held alike, a single stock's included (no stock card is admitted while `elane.structures` is ["etf"]).
Tests: `league/tests/test_elane_rsec.py` (XLK, TLT and SPY with XLK, with the switch absent, off and on, the permit
file empty or listing the lineage in every status; an index-only family's try and look unchanged; the forward seat).

**The widening route** (the captain's, after release T is running; with R-SEC live, widening is a setting). Check
first, each on the box read-only: R-SEC is in the running release (this section's tests green on its head); policy.json
`elane.fwd1` has mode "record" and `elane.forward_screen` the receipt's 64-hex sha, and `forward-screen.sqlite` has its
one `fwd1_pins` row;
`elane.forward.mode` is not "off" and the last `forward_register` receipt is ok; no family yet names XL*, TLT or GLD
(one that predates the release is retired before the switch); the Sail balance covers the births; no share or option
order is in flight; outside 12:55-20:05Z. Then on the owner's machine, a dry run and the same line with `--apply`:
`python3 set_swarm.py 'elane.universe=["SPY","QQQ","IWM","DIA","XLB","XLC","XLE","XLI","XLK","XLP","XLRE","XLU","XLV","XLY","TLT","GLD"]' elane.birth_share=0.5`.
SPY stays first (the `forward_shadow` canary reads `universe[0]`); the whole list goes in one call (the first sector
registration locks the sectors controls to it); **XLF stays out** until the House store's 2016-09-19 XLF row is
corrected. The dry run must print only those two keys moving. `elane.fwd1.seats` "on" is a separate, later step, taken
before the first checkpoint-5 night (it also makes every listed index lineage forward-only).
**Its cost, stated:** A19's four-symbol list is loosened for forward-only lineages; the loosening carried is A33's own
(an ETF forward pass at 2.61 says almost nothing about skill; one live forward seat a mechanism cell bounds the
near-copies); births spend research dollars on the Sail routes up to `elane.e2.usd_day`.
**Its rollback:** `python3 set_swarm.py 'elane.universe=["SPY","QQQ","IWM","DIA"]' elane.birth_share=0 --apply`, in
force at the next loop pass (swarm.json is read every loop); it stops new sector births only. The sector families
already born still take no sealed try or look (R-SEC); to stop their forward seats, `elane.fwd1.seats=off` (it stops
every forward seat, index and panel included), then retire them in the House store. A code rollback to a release
without R-SEC is NOT safe while a sector family is alive: retire every family that names a symbol outside the four
index ETFs first, or its next 300 s equity round takes the 2025 pre-check and a look, and A33(4) then bars it from
forward evidence for good.

**The equity graveyard's universe group (`fix/graveyard-group`, Oct 15, 2026; a reported loosening).** At 03:40Z Oct 15
the captain widened `elane.universe` to the sixteen ETFs (A35). The first births pass (03:43:16Z) proposed six sector
cards (a trend, a rotation, a low-volatility, a reversal and an overnight-after-a-down-day card, and a beta
turn-of-month card) and the graveyard refused all six, each by an index row of its cell: "graveyard: its cell
(trend_momentum / equity:etf / days_11_plus / underlying_price) holds 1 graveyard row(s) killed by a mechanism verdict,
the newest trend-spy (REFUTED) ...". The cell had no universe group, so a mechanism refuted on SPY, QQQ, IWM and DIA
closed it on the sector, bond and gold ETFs, which are other hypotheses (industry momentum, sector rotation, a defensive
asset's premium). **The rule, equity cards and rows only** (`league/swarm/cards.py`, THE EQUITY GRAVEYARD'S UNIVERSE
GROUP: `universe_group`, `row_group`, `groups_meet`, `graveyard_key`, `budget_cells`, `RebirthIndex.matched`): an equity
card's graveyard cell is its class, lane-scoped structure family and holding AND its universe group, the group
`elane_train.symbols_group` gives its symbols (index, sectors, defensive, stocks, or a mix such as index+sectors: the
Train map's, FWD1-R's mechanism cells' and the forward controls' groups); a row's group is that of every symbol it is
known by (its card's, its graveyard roots, its spec's). A row binds an equity card only when their groups **meet**
(share a group): an index row binds index cards and no sector, bond or gold card; a sector row binds the sector cards; a
mixed row binds a card on any group it traded; a mixed card is bound by the rows of each of its groups, so naming one
extra symbol of another group escapes no row (a mix without an index symbol is free of the index rows; a mix with one is
bound by them). Neither "equal" nor "contained in" would hold that: with equality SPY+XLK escapes an index row and a
sector row alike, and with containment a card adds one symbol to escape. A card or row whose symbols cannot be read, or
that names a symbol outside every group, has no group and meets every group (fail closed: the release before's binding).
**The rebirth budget:** each single group of an equity cell has its own `architect.max_rebirths_per_cell`
(`budget_cells`: the claimed row's class, family and holding, and one group), and a rebirth spends the budget of every
group ITS CARD trades, never the claimed row's label: it needs room in each and counts once in each. So naming one extra
symbol of another group reaches no other budget (an XLE+SPY card claiming an index row needs room in the sectors budget
too), and a mixed label such as index+sectors is never a budget of its own. A card with no group (fail closed) is
charged to the groups of the row it claims; an options rebirth's budget is `cell_of`'s, as before. The claim's tests are
unchanged. A card no row binds that carries a claim on a row only the group kept from binding it (a sector card naming
an index row, as the 03:43Z refusals asked for) is born without the claim (`dropped`), so it spends no index row's
budget. The refusal names the group ("... / underlying_price / universe group index"); the equity request's graveyard
header and its closed refusal words say a row binds the cards whose group meets one it traded.
**What does not change:** `cards.key_of`, `matches`, `cell_of`, `infer_key` and the stored card keys (the born payload,
the cell yields, the researcher's lineage reading and the memory judge read them); every options card, alpha or
direction (no group: `elane.card_lane` is None), its rows, verdicts, cells and lines, byte for byte; a panel card (its
own "equity:panel" cell, no symbols); FWD1-R's one live forward seat a mechanism cell (league/ops/forward_screen.py
`cell_of`: `elane_train.cell_of` of the program's NEEDS symbols, never a card key), every screen, the sealed data, the
money rules, the Train bar and R-SEC. On the live store every equity row before the widening trades index ETFs, so
every index card is bound by exactly the rows it was. Tests: `league/tests/test_elane_graveyard_group.py` (GOLDEN: the
options readings and the index cards' verdicts on a fixture store equal to release U's `aec0c8a5`; the six sector
cards free of their index rows and born by the equity pass, an index card of the same idea refused; the group rule for
sector, mixed and defensive rows and cards, fail closed; the budget by group, charged to every group a card trades:
an XLE+SPY card claiming an index row, and an XLE card claiming a QQQ+XLV row, are refused once the sectors budget is
spent, as release U refused them; FWD1-R's cell).
**Its cost, stated:** more equity lineages are tried: an idea refuted on the index may be born on the sectors, on TLT
and GLD, and in a mix without an index symbol, once a group (and again only through a valid rebirth claim once a row of
that group binds it; each such rebirth spends the budget of every group its card trades, so the rebirths a window allows
grow by one `max_rebirths_per_cell` for each single group, never for a mixed label). Every such lineage is forward-only
under R-SEC (no sealed Validation try, no S2 look); its only route to money is FWD1-R ETF case N, whose per-program
false-positive rate is unchanged (the receipt's 2.8% worst-regime point, 5.5% bound; 1.4% passing by checkpoint 60 at
zero edge in the haircut world). The count of lucky forward passes grows with the lineages (about 1.4% of each added
zero-edge lineage by checkpoint 60), capped by one live forward seat a mechanism cell (lane / agenda / universe group),
and the money rules size and demote every seat as before.
**Its rollback:** a code rollback to release U (the graveyard then binds sector cards by index rows again; families
already born are unaffected), or the widening's own rollback above (no new sector births).

**Inspect** (on the box, read-only): `sqlite3 -readonly <state>/forward-screen.sqlite "SELECT lineage, verdict, k, day
FROM fwd1_verdicts"`, `... "SELECT lineage, k, passed, why FROM fwd1_checks ORDER BY lineage, k"`, and
`<state>/forward-screen-report.json`.

**Stated limits.** The panel placebo leg draws on one panel run over the judged sessions started flat at FWD1_START (a
lot carried in from before a mid-run start is not in its draws, and the run's last session opens no lot); a span that
holds a session of the program's own disqualified run fails the leg closed, one the House left out waits. At c >= 2.06
the leg never bound on the study's twins.
The fill gap is modelled until 20 live panel lots (and the ETF lots) measure it. The sides cost one forward run of
a representative a checkpoint it reaches (seven at most), and its own floor its Train-era runs once, in the job's own
child inside `cpu_seconds_night` (one core): a lineage left over waits a night, its checkpoint still the first k days. ETF lineages with an S2 look have no
forward route. The stand-ins are 2010-19 and 2022-24 history; none is the truth for October 2026 onward.

## The panel lane (release E4, "breadth", Oct 2026): `feat/equity-e4`, deployed 03:28Z Oct 15 in release U, shipped switched off

E1 gave the equity lanes a live path and E2 made the swarm breed share programs for it, on four index ETFs. E4 opens
the place where independent history is: **the point-in-time S&P 500 PANEL**. A panel program picks 5 to 12 names out
of the day's index members by a symmetric cross-sectional rule (reversal, momentum, industry momentum, low
volatility, rotation), sees salted slots with no ticker and no date, and is judged on its daily **RESIDUAL** (its P&L
after its costs, less the cost-free P&L of the cells its names were picked from) against matched placebo portfolios,
by the screen **XS1**. The contract between the release's packages is `league/xs/E4_INTERFACES.md`; what an author is
shown is `league/xs/XS.md`; the lane in the swarm is `league/swarm/E4.md`; what went into E1's and E2's files is
`league/swarm/e4_patches/` (one file an author; a record once applied).

**What ships (as merged, Oct 11, 2026; nothing of the lane deployed): ONE release, in two steps.** The tree holds
the whole lane: the eight packages of the integration over E1 and E2, the review's and the ship pass's fixes, the
three pieces built since and merged in this order (the forward twin, package J; the probe's panel strata, patch 18:
built, not handed to the House's job; the receipt at the captain's bar, A23), the ship check's fixes (below), and
MAIN AS IT RUNS merged under all of it: `8ab31e32`, deployed 22:51Z Oct 11, with releases E5-S and E2.4 (six seats
at a Probe sleeve of 0.25 x E, the equity lanes' alarms), E5-A (the seat rule "activity-1-free") and E3.1 (an exit's
wait for the practice proof has an end; the twin is re-based after a difference). The records are
`league/xs/E4_INTERFACES.md` sections 10 to 18. **Merged with A32 (Oct 14, 2026):** the tree also holds `47ed6872`
(PR #543, decision A32: the Probe sleeve 0.50 x E at six seats, money digest `5b95d73e`, constitution digest
`4ef472e1`), which deploys FIRST; this release keeps the options execution fingerprint, the equity identity and
both digests as A32 leaves them, and moves only the xs identity.
- **A SHARE PROGRAM'S LIVE PATH IS MAIN'S, ORDER FOR ORDER, at every position of the lane's switch** (the captain's
  ruling at the ship check: six ETF programs hold real-money seats). The live equity book carries the panel kind
  (`league/equity/live.py`, package H), and one of its rules was written for every instance: the spec's decision
  27, B8, a buy cut by a cap waits while an exit of its own program is working. B8 is now the panel kind's alone
  (`EquityBook._cut_waits`). The proof is a recorded comparison (`league/tests/test_equity_etf_orders.py`): the
  rehearsal's harness of the lane's first Monday (the real book, schedule, sizing, stock proof and decider kind
  over a fake venue and invented prices) runs 75 scenarios: the normal Monday, every way a buy can miss, the week
  and its failing weeks, programs that sell and buy in one window, and what main's last release made possible: the
  seat rule over thirteen sessions (an idle seat kept while nobody waits, yielded to a waiting program, one a
  decision day, a session the House refused left out, a yielded program's return) and the forward record's nights
  beside the book (the real registry, shadow and twins: nothing re-based, a missed buy and the twin re-based, the
  practice sale never witnessed and the exits at the 09:45 cut-off); and every one of them again through the real
  swarm reader with the panel switch absent, "off" and at "train" (a panel family in Train research in the store).
  The fixture was recorded on main `8ab31e32` and again on `47ed6872` (A32, the release this one deploys over: it
  doubles a one-ETF lot, so every scenario's sizes moved, and in four a cap admits fewer sends); every POST, cancel,
  fill, alert, line of the seat rule, intent, order, lot, instance row, key of the book, record, minute's answer,
  twin row, twin event and A14 reading of this tree equals it. With B8 as the spec wrote it five scenarios differ,
  and a tree that lost the seat rule's read, the exit wait or the re-base differs in the scenarios recorded for
  each: the test holds that it would see them.
- **What main's three new rules do for a panel program** (decided at the merge; `league/swarm/E4.md` section 7;
  `league/tests/test_equity_panel_on_main.py`). THE SEAT RULE: in step one a panel family never enters the seat
  plan, never counts against the six seats and never holds or yields a seat: the book builds its plan from the
  rows the swarm's reader gives it, and the reader gives a panel family none while the lane is not live, which
  step one cannot be at any setting. (Under the rollback value "first-come" it is the swarm's roster that counts,
  by the Probe band as the store holds it; step one puts no panel family in a band.) THE EXIT WAIT'S END covers a
  basket's exits like any other: its sales and the House's exit of a name that left the eligible set wait for the
  practice sale inside the open window and go at the 09:45 cut-off with the one alert. A basket's BUY of that open
  waits with its own sales (B8) and the cut-off records it missed; the standing target plans it again at the next
  close. THE TWIN'S RE-BASE (A29, as registered) IS APPLIED TO THE PANEL TWIN SINCE STEP TWO, on the panel night's
  own code (league/ops/forward_xs.py `panel_seed`, `PanelChain`; league/xs/book.py `TwinAccount`): a session whose
  orders differ is written as differing; then the twin's book is set to the live basket as it stood after it (each
  live lot bought by the Gym engine in its own entry session at its fill point for its weight of its decision's
  budget; the live decision's buys, sells, House exits and standing target carried) and the sessions after it are
  compared from the same state. One `twin_rebased` event a re-base; every row carries A29's `rebased` and the
  un-re-based twin run's `base_agree` beside. One missed buy counts once; without it one panel miss could fail the
  pooled 95% for every program. The program is loaded once in the night's decider child and asked every decision in
  order (the un-re-based run's through the difference, then the re-based account's): no program text runs in the
  ops process, and a child that restarts is an interruption (the rows compared before it stand). COST, stated: the
  night asks a re-based instance's decides twice (the child's run and the chain).
- **What the deploy changes for a book that holds no panel program, and nothing else:** the live state gains the
  column `eq_instances.kind` ("equity" on every share program's row) and the empty table `eq_rebalances`, both made
  when the book starts; main's book reads neither and trades the same weeks on a state that holds them (checked:
  the rollback). The swarm's start writes the xs identity's mark to its store, and the forward register asks the
  panel reader, which finds nothing. No order, size, time or alert of a share program moves.
- **STEP ONE is this tree, deployed with the lane's switch able to reach "train".** An owner deploy (`league/xs/`,
  `league/ops/` and policy.json are behind CI's wall). policy.json ships `elane.panel.mode` "off"; the captain's one
  settings change to "train" starts the data jobs that night, then panel births in the equity pass, the Train bar
  with its weekly zero-edge column, and the forward shadow of every scored panel version (the job `forward_xs`), so
  that information accrues from the first night. It moves no identity a judge binds to and no money rule: the
  options execution fingerprint, the equity identity and the money digest are main's on both Pythons; only the xs
  identity moves, and no panel band exists under it. **A CODE ROLLBACK PAST THIS RELEASE, once the lane has been at
  "train", takes one step first** (**Rollback past E4**, below): `elane.panel.mode` "off", then every alive panel
  family retired (`scripts/panel_rollback.py --apply`). A release from before E4 knows no panel structure and reads
  every alive panel family as an options family.
- **Above "train" the tree holds itself back, whatever the setting.** At "gate" Validation is scored and both Train
  series are kept, and every look waits: the receipt is pinned, but no look permit exists, because the House's
  probe job is handed no plan. "live" reads as "gate": no universe deploy is in force (`live_from`), so no panel
  program can hold a seat and no panel order can be sent.
- **STEP TWO STILL NEEDS, each the owner's and none of it in this tree:**
  1. **The universe commit** (R-E4b; **The universe deploy**, below): the constitution's stock list, generated by
     `scripts/gen_universe.py` from the House's own `tradable.json`. That file exists only once the lane has been at
     "train" (the `equity_universe` job writes it), so step two cannot be cut before step one has run.
  2. **The money row for a panel sleeve**: BUILT on `feat/equity-e4-step2` (`equity_money.panel`: one panel seat
     of its own at a sleeve of 0.10 x E; **The panel's live rules**, below). It moves the money digest once; it may
     be deployed with the universe or before it (a row no panel program can reach until the universe is in force).
  3. **The gateway patch**, in three parts, each a patch file for the owner (no builder edits `gateway/`): the
     STATIC half of the universe (`gateway/lib/caps.mjs` and its tests made ready for a generated list: it changes
     no list and no order's fate, may be deployed at any time before the universe, and the gateway's own tests are
     green on a grown list only with it applied); the list itself (the same stock list as the constitution's,
     written by `gen_universe.py --gateway-patch`); and the merge list's follow-up for the lane's two protected
     paths (`gateway/lib/protected.mjs` `MERGE_FORBIDDEN`; until it is deployed the two wait in `league/ci.py`
     `PENDING_GATEWAY`, and the updater's wall holds them either way). The first and the third are written and in
     the captain's scratch; the second is generated in step two.
  4. **The owner's deploy**: the gateway first, then the House, both between two pre-opens. `digest()` and
     `money_digest()` move ONCE and the standing grant re-ratifies at the House's start.
  And for a LOOK, which moves no money and no digest: **the hand-over of the probe's panel plan to the House's
  job**, two lines and one allowance in release E3's seal test, the captain's ruling (**The probe's panel strata**,
  below). Until it is given every panel look waits; once it is, a route's permit exists when the probe has
  published that route with the three strata, several Saturdays at the shipped line.

**As integrated (Oct 11, 2026; nothing deployed).** Eight packages are merged on `feat/equity-e4` over E1 and E2 with
their review fixes, and every patch to E1's and E2's files is applied (the record: `league/xs/E4_INTERFACES.md`
section 10). XS1's receipt is in the tree and pinned (`docs/benchmarks/equity_screen_xs_1.json`; policy.json
`elane.screens.equity_xs` is `league.xs.screen.pin` of it, written whole, so a rebuilt receipt lands as one file,
one block and its conformance vectors, and no line of code that judges; the captain's A23 has since landed one, at
c_XS 1.38: **The screen XS1**, below). One test takes the lane from a birth to the Done meter on every package's
real code (`league/tests/test_e4_e2e.py`: a synthetic panel, a fake receipt, a fake venue);
`league/tests/test_e4_integration.py` holds what stands around it. **Three things were not in that tree, by
design:** package J (the forward twin) and package B's probe strata, both built on release E3, and the universe
commit (R-E4b), which waits for the House's own `tradable.json`. (Built since: package J, **The forward twin**,
below; and the probe strata, not yet handed to the House's job: **The probe's panel strata**, below. The universe
commit is step two's.)

**The ship pass (Oct 11, 2026; nothing deployed): main was merged in, and the release was cut in two steps.**
Main's releases E2.2 and E3 (`7d2d3c84`) are merged under the lane (the record: `league/xs/E4_INTERFACES.md`
section 12); the two steps are as stated above. What the merge made true: a panel family is now born with a hidden
year (E3's folds record in the committed policy); a scored panel version IS in E3's forward record from the hour its
Train verdict is written (package J: its own reader beside E3's, its own night after the panel store's); and the
swarm no longer reads the contamination probe's own file (E3's seal forbids it: below, A22 (3)).

**The ship check's fixes (Oct 11, 2026; nothing deployed).** The check of the merged tree and its rehearsal on a
copy of the House's state found one blocker, three majors and the minors; each is closed in this tree
(`league/xs/E4_INTERFACES.md` section 17 is the record).
- **Main had moved** (releases E5-S and E2.4): merged, every line of both kept. The seats and the sleeve are read,
  never assumed, wherever E4 states a size (**The panel's live rules**, below, is restated at the design in force).
  Release E2.4's lane alarms (`league/ops/elane_health.py`) read share programs only: their causes judge E2's own
  Train record, and a panel family keeps the panel's and is watched by the panel's own alarms (**The alarms**,
  below).
- **The live book**: above.
- **The zero-edge job fits the ops child's memory.** It opened the panel store again for every run and kept every
  run whole: at the real panel's size its second run met the 500 MB cap, so every Sunday chunk would have failed.
  A judgment now reads one store, keeps each run's result and lets its slice go, and the restart check cuts a
  slice again when it reads it. Three judgments at 2,455 sessions by 767 columns under the child's own limit peak
  about 80 MB under the cap on the desk with the engine canned (the test holds 30), and the real job run whole
  there under the same limits (eleven programs, 99 runs) peaked 57 MB under it: it fits, and the room is thin. NOT
  MEASURED ON THE BOX. If the first Sunday's receipt fails on memory the lever is a memory room of the row's own
  (the runner gives every job the same 500 MB). The swarm's own judgments use the same code (they were 762 MB a
  judgment on the box, uncapped).
- **No run that lost a decide to the clock is judged.** A decide's limit is one second of WALL time and the box
  stood still for longer: a program of 100 ms a decide met a timeout in three of six runs and gave different lots
  on the same span. In the Train judgment, the zero-edge job and the forward night a run whose runtime shows a
  decide timeout is made again, three times at most, and never read. Timeouts in every one of those runs that
  repeat as a program's do (the same count, or more than 5% of its calls) are the program's: the verdict `SLOW`,
  whose words carry the seconds measured, and which its author reads. Timeouts that do not repeat are the House's:
  nothing scored, a backoff, one alert (`elane_xs_clock`) at the third. On the forward night such a program gets no
  row and goes on E3's retry list. THE COST: up to three times the CPU of an affected run, inside the lane's day
  budget. NOT DONE HERE: the fix at the root (the child's own CPU time, `league/gym/runtime.py`) is inside the
  equity identity and needs a release of its own. VALIDATION AND THE LOOK ASK IT TOO since step two (`steady_runs`:
  every run of the try, the two Train segments and the sealed run, `may_run` before each; the House's clock spends
  nothing at first and owes the try or the look after a backoff; repeating timeouts spend the try as SLOW and the
  look as spent and failed), closed before any look as step one's record said it must be. THE OWE HAS AN END: a
  round of the House's clock in which a sealed run was made is counted, the third spends the Validation try (a
  "clock" run) and the second spends and fails the look (one send of the sealed run, beside a run that never
  returned); while a try is owed no other version of its lineage takes the lineage's try. COST: a box whose clock
  is genuinely unsteady can spend a good program's try or look (`league/swarm/E4.md`).
- **`equity_spreads`' CPU row is 900 s** (was 300): the ops client opens a TLS connection a request, about 70 ms of
  CPU a call on the box, and a night of the backfill asks up to 6,000. At 300 s the child would have been killed on
  each of its nine nights. A kept connection would cut that cost; it is a change to the ops client of every job and
  is not made here. The quotes route itself has not been rehearsed.
- **The data jobs pace their venue calls**: 0.4 s before every bars call, rename test and asset row (at most 150 a
  minute by the pause; they went at about 285), and a call the venue answers 429 waits 30 s, then 65 s. A first
  night's whole fetch is about seven minutes longer for it, inside its wall.
- **`forward_xs` skips where E3's own job skips**: while the House's daily store holds no forward day (it failed
  there, three receipts and three warnings on the first evening at "train"), and while the panel store holds no
  session whose rows are final.
- **Two guards have their tests**: the look's own reading of the lane's mode (a family validated under "gate" took
  its look at "train" with that line removed, and no test said so), and release E3's seal, whose allowance for
  package J is now its five dispatching modules', held both ways.

**The probe's panel strata (package B's patch 18; built Oct 11, 2026; NOT WIRED; nothing deployed).** Release E3's
probe (`league/ops/contam_probe.py`) can now be handed a PLAN of three more strata
(`contam_probe.probe(ctx, panel=contam_xs.plan)`; the plan is `league/ops/contam_xs.py`). **P4**: an index member
against its sector's fund, a month. **P5**: the same, a week. **P6**: the House panel factors (momentum, short-term
reversal, beta: the top third of the index against the bottom third), a month. Each is asked in E3's three eras, a
full grid a cell under E3's own hash rule, the same questions for every route.
- **THE HOUSE'S JOB DOES NOT HAND THE PLAN YET, so on the House the probe is still release E3's, no permit is
  written and every panel look waits.** Two of E3's seal tests leave no import between the two modules: the probe
  may import only what E3's contract lists (nothing of `league/xs`, and not the plan's module), and no ops module
  outside the forward record's own may import the probe. Neither was changed for the probe (package J's change to
  both admits and holds its own module, `forward_xs`, which the probe does not import). So the probe hands the plan
  its calendar and its file's content, and takes the plan's maker as a parameter; and handing it to the House's job
  (`contam_probe.run`) is two lines and ONE allowance in E3's seal test, which is the captain's to give. The patch,
  with its tests' expected results, is in the captain's scratch (`eqe4/p/wiring.patch`). Everything below is what
  the probe does once it is handed the plan, and is held by `league/tests/test_contam_xs.py` in that form.
- **A prompt is built from names and the calendar only**, and every word of it is the probe's: the plan hands in
  tickers (capitals and at most one dot: no figure can ride in one) and period names of the probe's own calendar,
  or the run fails before any route is marked. The fund is not named (the House's sector is statistical, read from
  prices). The members asked about were in the index, unmasked and under one ticker, through the whole era.
- **Truth stays on the House** and comes from the panel store through its own windows: a 2017-19 or 2022-24 period
  by a Train slice, a 2025 or 2026 period by the sealed "look" window alone, which opens only for the gate's
  capability the job mints. No period of 2016, 2020 or 2021 is asked about or read, by base or by end (each Train
  segment's first month and week are left out). A cell's truths are read only once its answers are in.
- **The dollars are the probe's, capped as shipped:** the same `elane.contam.usd_run` a run inside E2's day line,
  the same keys never sent twice, the same rows of E2's ledger. Nothing was raised. The panel adds about 800
  questions to E3's about 1,100 at the shipped cell size (41 batches to 59), so a route's probe takes about 70%
  more dollars and, a Saturday's line being what it is, that many more Saturdays.
- **The result** carries the three strata under `cells` in the probe's own file, in E3's shape (aggregates only);
  E3's own cells and questions are byte for byte what they were (`qset` is still E3's questions' sha; the panel's is
  `panel_qset` beside it, so a membership revision drops a partial's panel cells and nothing of E3's).
- **The permit** (`<state>/xs-look-permit.json`, 0600) is written from that file's content each time a result is
  published and after every other run that had a plan: one row for every route whose published result carries all
  three strata, `at`, `model` and two words a cell (`readable`, `recalled`), no count and no rate. It is what a
  panel look waits on (A22 (3), below). A recalled cell does not hold a look back: the reading is recorded beside
  the look.
- **A route published before the panel's strata existed is due at once** (its result is not whole), E3's cells
  asked again with it. **One route a Saturday** is E3's cadence, unmoved: with N routes the last route's permit is N
  probes away, each of several Saturdays at the shipped line. The captain's levers are E3's (`elane.contam.usd_run`,
  E2's day line) and a run by hand outside a session's walls (`python -m league.ops run contam_probe --state ...`).
- **With `elane.panel.mode` "off", before a panel store and universe exist, or while the panel's coverage verdict is
  "insufficient", the plan's maker answers none and the probe is release E3's to the byte** (no panel stratum, no
  permit). With the lane on it asks the quiet windows first, like every E4 job (the probe's Saturday 00:10Z time
  never meets a wall), and a panel store that cannot be read fails the job before any route is marked or dollar
  spent: the lane's switch is the way back to E3's probe while the store is mended.
- Measured on a synthetic panel of about 900 columns under the ops child's own limits, pinned to one core, with a
  scripted router: the probe with the plan peaks at about 330 MB of the 500 MB the child may add (E3's probe alone:
  about 120 MB), and the nine cells' truths take under 2 seconds of CPU. Not measured on the box.

**Why a panel, and why a residual** (measured the week it was built, rule-level): a raw-P&L screen cannot be opened to
single stocks or sectors, because an author who knows which symbol won a known year passes it far above the owner's
15% wall at zero edge (the captain's A19); and four index ETFs hold only about ten independent lineages. A basket
program closes several lots a week, and its residual does not care which way the index went.

**It ships off, in two steps (the two deploys this page calls R-E4a and R-E4b).**
- **R-E4a (STEP ONE; research; an owner deploy; NO constitution change, so no money-digest move):** the data jobs,
  `league/xs/`, the swarm hooks, XS1's receipt and its pin, the panel half of the forward record (the job
  `forward_xs`) and the probe's panel plan (in the tree, not handed to the House's job). policy.json ships
  `elane.panel.mode` "off", and the captain's settings change takes it to "train". The panel's own identity is
  adopted for the first time (no panel band exists yet).
- **R-E4b (STEP TWO; THE UNIVERSE, with the money row of a panel sleeve; deployed separately; the money digest
  moves ONCE):** the constitution's `equity_money.universe.stock` grows from E1's 18 names to the panel's tradable
  union, with the same list at the gateway. See **The universe deploy** below.
- Neither moves the equity evidence identity (A13) or the options execution fingerprint: nothing of E4 is in
  league/equity's evidence import closure, and no file under `league/live/` or `league/gym/` changes
  (`league/tests/test_xs_identity.py`; `league/tests/test_gen_universe.py` holds that neither identity reads a file of
  the universe's). No options evidence and no ETF evidence is reset.

**With every E4 switch off nothing of E4 runs, spends or trades:** no birth, no Train run, no fetch of the live path,
no model question, AND NO DATA JOB: with `elane.panel.mode` "off" each of the five data jobs (`equity_universe`,
`equity_panel`, `equity_spreads`, `equity_neff`, `french`) answers a `skipped` receipt before its first gateway call
and its first file (`league/ops/equity_universe.py` `lane_off`), as the zero-edge job does. They read the SETTING,
never the effective mode (which reads "off" until they have written the store): **the captain's first step up,
"train", starts the data that night**, and the lane's research follows on its own once the store has a coverage
verdict it can stand on. To read that verdict before any birth, raise the mode with
`elane.panel.birth_share=0` and set the share afterwards. The jobs read only (the gateway's data routes and its web
reader), and none starts with the House: `equity_universe` runs at 01:40Z and `equity_panel` at 01:55Z every night,
each on its own trigger, so a night the membership job fails still fetches the bars, runs the I6 and raises the
panel job's alarms on the last good universe.

**The switch** is `elane.panel.mode` (policy.json; swarm.json over it; read on the next loop pass, no deploy). On the
owner's machine: `python3 set_swarm.py elane.panel.mode=train --apply`. Each step is the captain's, and each falls back
to the one before:

| mode | what it opens | what it needs first (the EFFECTIVE mode, `league/swarm/elane_xs.py` `mode`, reads lower without it) |
|---|---|---|
| "off" | nothing | (the shipped value) |
| "train" | the data jobs (from the SETTING alone); panel births in the equity pass, and the Train bar **equity-xs-v1** | `elane.mode` "gate" (E1's switch); the panel store written (`equity_panel`) with a coverage verdict that is not "insufficient" |
| "gate" | the one Validation try and the one look under XS1 | XS1's receipt pinned (no receipt, no look); the spreads table covering at least `spreads_min_share` of the Train eras' member-days (below it a Train pass is "provisional costs" and the mode reads "train") |
| "live" | a passer may take one of E1's roster seats | `live_ready`: THE PANEL STORE FRESH BY THE CLOCK (its last session is the last closed session or the one before: one missed night is tolerated at the next morning's sends, a second holds every open), the universe deploy in force, today's tradable share of eligible names at least `live_min_tradable_share`, the committed universe younger than `universe_max_age_days`, the last nightly I6 equal, AND the forward twin's marker (`xs-twins.json`, itself no older than the session before the last closed one). Any one missing: the mode reads "gate" |

**Four things hold real money back, by design.** (1) **The twin marker.** Until the panel night of the forward
record (package J: `league/ops/forward_xs.py`, the job `forward_xs`; "The forward twin", below) has written
`xs-twins.json` through the panel store's last session, and whenever that marker is behind, **mode "live" reads as
"gate"**: no panel program opens a position the forward record is not shadowing. (2) **No panel look runs until
release E3's contamination probe has published the panel strata for the route that wrote the program and written
the look permit** (the captain's A22 (3), below; package B's patch to the probe is built and not yet handed to the
House's job: **The probe's panel strata**, above): mode "gate" scores Validation and keeps both Train series, and a
look waits on its route's permit. (3) **The universe deploy** (step two): until it is in force `live_ready` is false
and mode "live" reads as "gate", so no panel program holds a seat. (4) **THE A31 LOOK HOLD**, `elane.panel.look_rule`
(policy.json "hold"; swarm.json over it): no XS1 look before study XS1-R rules (the captain's A31). Under "hold" a
look waits, nothing spent, even with its receipt, its route's permit, its review and its cell's room in place, and
says "A31: no XS1 look before XS1-R rules" in its gate state, in the heartbeat's `equity.panel.look` and in the
direction report's `panel_lane.look`. "xs1" is XS1 as built; any value the tree does not implement holds. Validation
is NOT held: mode "gate" spends each lineage's one try whatever the ruling, so the look runs the night the captain
sets the value the ruling names. A ruling that names a remedy is built as a new value beside "xs1" (R-c: "xs1-rc"),
so a look opens only under code that implements it. A TIGHTENING (a spent look is spent). **XS1-R ruled (the captain's
A34, Oct 14): no historical look, forward only.** Since release U every value holds, "xs1" included, and Validation
is held too (`elane_xs.A34_FORWARD_ONLY`; **Release U**, above): a panel program's one path to a seat is a FWD1-R
forward pass seated through the panel pool. So the order to a first live panel trade is: step
one (this tree, the lane at "train"), the spreads backfill (about nine nights), the probe's wiring and its Saturdays
for the route, the universe deploy with the money row, one panel night with the instance's twin, a free seat and
room in the loss window.

**The forward twin (package J; `league/ops/forward_xs.py`, built on release E3's forward record; no identity and no
digest moves).** With the lane's switch off, or `elane.forward.mode` off, none of it runs or writes.
- **The registry.** Every panel version judged on the Train bar, passed or failed, is registered by the hourly
  `forward_register` (the panel's own reader beside E3's): hash-chained with its code, its PARAMS and its NEEDS,
  `ugroup` "panel:sp500", route "XS1" and alpha 0.03 in the hashed row, dated by the scored event its own bar wrote.
  A style-open passer is a scored version like any other: recorded AND shadowed. No control group holds a panel row.
- **The panel night** (job `forward_xs`, after each `equity_panel`; never inside 09:00-17:30 New York on a session):
  E3's own night on the panel store, the "panel" kind in the forward job's own kind of decider child. It is NOT a
  ride on `forward_shadow` (22:35Z): the panel store is a session behind at that hour, and the marker must be through
  the store's last session by the next close, or the lane would read "twin marker behind" from every close to
  22:35Z, the 16:30 decide included. ONE run a program a night at 1.0x: the pinned pre-registration's forward series
  is the residual and the STRESS residual of one run, and the row's `r15` holds the second in E3's currency (no run
  of the 1.5x-cost book is recorded forward). E3's checkpoints (20, 60, 120, 250 sessions), N_eff, CEY and the BH/BY
  meter read a panel program through the same columns: its excess IS its residual against its matched cells.
- **Rows lag one session, twins two.** The panel engine opens no lot on a slice's last session and reads membership
  two sessions ahead, so with the store through P the night writes each program's rows through P - 1 and each twin's
  rows for decisions through P - 2, and names its night by P - 1 (its own job in `fwd_runs`; E3's stop rules, FW2
  and the funnel each read their own job's nights). COST, stated: once a panel program is registered a day's meters
  (`fwd_cey`, `fwd_meter`, `fwd_groups`) wait for its panel rows: they are written at the morning report after the
  panel night that holds them, the SECOND morning after the day (before: the evening of the day itself), and are
  never partial for that cause.
- **The budget, on one core.** The panel night spends what `forward_shadow` left that evening of
  `elane.forward.cpu_seconds_night` (1,800 s: one budget a night, not raised); the programs it leaves stale go first
  the next night, and FX3 says when two nights running left some. A live instance's twin run is outside it, bounded
  by the night's deadline (08:55 New York). Estimated, not measured on the box: a 250-session program-night is about
  4 s of the build machine's core and three times that on the box, so the whole budget covers about 150 such
  programs a night. All of a night's runs read ONE open of the panel store (the ops child's address space is capped
  500 MB above its start, and each open maps about 120 MB).
- **The twin of a live panel instance.** The registered program run flat from the session after the instance's first
  decision, under the instance's own id as run key (the ids, sector codes and dither the live ctx read). One row a
  decision session: the same sells, the same buys, every buy's WEIGHT within 0.001 (weights, not dollars: the live
  sleeve moves with the account). Not read: a decision whose morning re-read was a mismatch ("audit") and a retired
  instance's sessions ("retired"). A disagreement is data, counted in the Done meter's A14 reading as any program's.
  `fwd_part` and `fwd_lotgap` are E3's, for a panel lot too (no timing part: no minute bars for 500 names).
- **The marker** (`<state>/equity-daily/xs-twins.json`): per alive panel instance `due` and `last`, and the panel
  store's last session. Instance ids and days ONLY: the swarm's process reads that file and nothing else of the
  forward record. A night whose preflight fails moves no marker.
- **Beside a live panel program in the direction report** (never a rule): its shadow twin's residual over its own
  sessions and its REBALANCE sessions agreed k of n with the days that differ; "not recorded yet" until a panel
  night has written its twin.
- **Verify after the deploy** (read-only): with `elane.panel.mode` "off" the job's receipts say `skipped` ("the panel
  lane is off") and `fwd_engines` holds no label with "+xs."; after the first scored panel version is registered the
  next night of either job writes ONE `engine_moved` event (the label gains "+xs." and 12 hex: every program's
  history is written again under it, the older rows stay); the morning after a panel night `fwd_runs` has a row of
  job `forward_xs` named by the session before the panel store's last, `xs-twins.json` is through that store's last
  session, and the registry's chain is "ok".
- **Rollback.** A release from before this one skips the job and stops reading panel rows (they stay, append-only);
  E3's night then hands a registered panel program to its own engine and marks it `data_failed` each night (nobody
  is stopped or tagged for it), and the engine label goes back (a new series, as any label that returns). The
  marker stops moving, so mode "live" reads "gate" from the second session on.
- **Not built, stated.** `fill_minutes` fetches no panel symbol (a panel lot's fill gap has no timing part). The
  forward ROUTE's own verdict (the per-program bar c_FX and the placebo rank over the first n sessions) is a later
  release's, on its own receipt: nothing here judges. No panel control exists, so no RC pair reads a panel group.
  The replay multiple counts a panel family's Train runs and not the panel's independent history: it overstates.

**What a panel program sees and may do** (the pre-registered contract C-XS-1; `league/xs/ctx.py`, `program.py`,
`engine.py`): after the close, one slot an eligible name (a member of the index today and for the next two sessions,
with its history and its three characteristics), each slot a salted number that is stable inside one run and unrelated
across runs; per slot only SCALE-FREE fields (`ret`, `oret`, `iret`, `range`, `rel_volume`, a salted `sector` code, a
`beta` to two decimals) and the same fields of the market; four calendar counts. **No ticker, no date, no price
level, no share count, no dollar volume, no size or liquidity rank, no event flag.** Under them every price is
dithered by half a cent before any ratio is taken, so the cent grid cannot give a level back; and `range` is the
candle's body plus its wicks under a dither that is a fixed SHARE of the close (never cents), so no statistic of it
ranks the slots by price either (dithered in cents like the other prices, a bar with little wick read a range under
its body by a cent over the price, and the slots where that happened were the cheapest names). It answers a target
`{slot: weight}` at the open or the close, long only, each weight at most 0.20, the sum at most 1.00, 5 names or more
when invested. **The KEEP rule** turns a target into lots: a held name that is still in the target is kept untouched; a
name that left it is sold whole; a new name is bought as one lot; at most 12 buys and 12 sells, and a target that
needs more is refused whole. **The sleeve is a CONSTANT-WEIGHT book, in the Gym and live alike** (the pre-registered
contract's C3 and C8: a new name is ONE lot of weight x the budget, and nothing compounds): a buy's room is the
budget less what the open lots COST AT ENTRY, so a loss never shrinks the next lot and a gain in the held names takes
no room from it (`league/xs/engine.py` `_committed`; `league/xs/book.py` `committed`, which the book's sizing reads
for a panel program's sleeve; every wall of the ACCOUNT is still read at its marks). One narrowing, stated: the
open lots' entry weights never pass 1.00, so where a kept lot holds more than the new target gives it the last new
names are cut to the room. The House's own exits are the same in the Gym and live: a name out of the eligible set
at any close is sold at the next open, a lot at its maximum hold likewise, and a name whose bars end exits at its last
close less a 30% haircut (for the lot, its placebo counterparts and its cell's members alike). **The standing
target:** a buy a session could not make (a sale that filled late, a quote too wide, a budget cut, a venue refusal) is
planned again at each following close until the next called decision, in the Gym and live by one function.

**The data** (House only; nothing here is ever committed or sent off the House; `<state>/equity-daily/`):
- `universe/`: point-in-time membership from the public spell file `sp500_ticker_start_end.csv` of
  github.com/fja05680/sp500 at a pinned commit, extended by the changes table of the English Wikipedia article, read
  through the gateway's web reader (`league/ops/equity_universe.py`, job `equity_universe`); the House's `SALT` (32
  random bytes, written once, never in a request, a log, an event or a manifest); `tradable.json`, the dateless
  36-month union the universe deploy is generated from.
- `panel/`: raw and adjusted daily bars of every member spell from 2016, fetched with `asof` inside the spell, with the
  membership and tradable masks and the half-spread table (`league/ops/equity_panel.py`, job `equity_panel`).
  **2020 is never fetched; 2016 and 2021 are history only** (no run has a session in either): the panel's Train years
  are 2017-19 and 2022-24, six of them.
- `spreads.json` (job `equity_spreads`: 2-second quote windows at the instants the book trades, on Train-era sessions
  only), `neff.json` (job `equity_neff`), `french/` (job `french`: skipped, and no alarm, while the House has no route
  to the library).
- `live-bars/<day>.npz`: the 16:20 fetch a live panel decision read, kept for five sessions and audited the next
  morning; `xs-twins.json`: the twin marker (ids and days only).
- **The nightly I6** (`equity_panel`, after the bars): the last session's 253-session window read again from the
  venue and compared with the store, column by column. `i6.equal` is the BARS' verdict within the vendor's cents
  (sessions and raw prices exact; adjusted prices within `rounding_bound`; a volume that went on counting is a
  note), and it also says, for each live panel decision of that day that read bars, whether the bars it read (the
  kept file) are the store's by the book's own rule, over the columns it had. **It is False on a price that differs
  and on nothing the live book itself tolerates**, each of these a count beside it and a warning: `late` (a bar
  served after the 16:20 fetch, which the book decided without and its own morning audit calls a note), `absent` (a
  member tonight's universe run added or dropped as of the day, after the decision's columns were built), and a
  decision with no kept fetch to be held to (its `live` entry is null: unread, never False). A failed decide that
  read no bars is no row of the I6 at all. `i6.bytes_equal` rides beside it: whether the two ctx are the same bytes, which
  a restatement between the store's vintage and the fetch can break while the bars still agree. The lane's readiness
  reads `equal`.
- **The vendor's cents are one bound for both lanes:** `league.xs.config.rounding_bound` IS E1's
  (`league.equity.config.rounding_bound`, re-exported): the panel's Gym, the panel's data audit and the book's morning
  audit of a panel decision cannot drift apart.
- **Coverage is the fact the release rests on** (member-days with a valid bar; `coverage_min` 0.97): the panel
  manifest's verdict is "ok", "low_coverage" (one Train year below the line is dropped from the bar, and said on the
  Train map) or "insufficient" (the lane reads "off"). Any verdict but "ok" is the owner's paid-data question.
- **The quiet windows.** No E4 job may be RUNNING at 09:25-09:45 or 15:50-16:35 ET on a session:
  each asks `league.xs.config.quiet(now, need_s)` with its own wall-clock limit before it starts, and a start that
  could still be working at a wall is skipped (not lost: it runs at its next trigger). **A panel RUN's wall is the
  whole session** (Train, the restart check, Validation, the look, the zero-edge job's runs: `quiet(now, need_s,
  session=True)`, `league.xs.config.RUN_SESSION_ET`): on a session a run starts only when it would be done before
  09:25 ET, or after 16:35 (13:35 on a half day). The box has ONE core, a scored version is a dozen runs of every
  member column back to back, and nobody has timed one there; the day's panel CPU fits several times over in the
  hours left. What it costs, stated: while no run may start a panel family takes no step at all, its researcher's
  model question included (`elane_xs.blocked`), so the panel lane researches at night and on weekends; births in
  the equity pass are not held. The one exception to both is the live path's own 16:20 fetch, 16:30 decide and 08:30 re-read of a
  LIVE panel program, which run in the live process as E1's do. **No daily job can still be working at a pre-open**
  either: due + grace + wall is 04:55Z, 05:50Z and 10:20Z for the three (the spreads job's grace is three hours;
  with six it could hold the one ops child from 12:30Z to 13:20Z, past the pre-open's 40 minutes).

**The screen XS1** (`league/xs/screen.py`; its receipt `docs/benchmarks/equity_screen_xs_1.json`, the study
XSCREEN-1's receipt rebuilt at the captain's bar by the study's own builder (A23, below) and pinned by sha256 in
policy.json `elane.screens.equity_xs`; CI holds the pin to the file). **Every threshold is read from the pinned
receipt at runtime; none is written in code.** With no pinned receipt the screen refuses every program. The rule,
per program:
- **The pre-check**, on Validation (calendar 2025): 20 lots fully exited or 120 sessions with a lot held, AND the
  residual's sum above zero. A failed pre-check spends no look, and it spends the lineage's only try: there is no
  Validation-only retry.
- **The one look**, on the 194 holdout sessions (2026-01-02 through 2026-10-09), from one run that starts flat at
  Validation's first session: pass = the pre-check AND the residual's sum above zero AND **the stress residual's sum
  above zero** (1.5 times the half-spread and every sell fee twice) AND the holdout t at or above **c_used** AND the
  placebo rank at or under the receipt's `alpha_plac` (ahead of 88% of the receipt's 999 matched placebo portfolios,
  whose seed is fixed before the look from the receipt's and the program's hashes).
- **c_used = max(c_XS, the program's own floor + the receipt's margin)**: the screen's bar every program meets, raised
  by the program's own exact 12% point of the holdout-only t on its own Train-era series when that is higher. The own
  floor can only raise the bar. A program whose floor cannot be computed, or whose bar is above 5.00, takes no look
  (nothing spent).
- **Lineage:** one look a lineage. Same lineage = the same template, or a Train daily correlation of 0.7 or more, IN
  THE RESIDUAL OR IN THE UNIVERSE EXCESS, with a panel program already looked at OR already refused at the pre-check. A
  lineage that took an XS1 look takes no S2 look, and the reverse. No Validation, look, placebo-rank or forward
  outcome of a panel program is ever shown to a generator, a researcher or the diagnostician.
- **What a pass says, and does not.** It says the picks beat random same-style picks after their costs. It does NOT say
  the program beats the index or makes money: market, sector, beta and momentum direction are not counted as edge.
  The receipt's sentence says so beside every live panel trade, with the study's measured false-positive figures and
  what the screen does not match (sub-industry, size, value).
- **The bar the House runs is c_XS 1.38 (the captain's A23, Oct 11), not the 1.30 the study registered.**
  - **Why.** The study's mechanical rule adopted 1.30. The study also measured that every real-signal cell's rate is
    understated by a finite-pool bias (up to 2.6 points at 1.30), and reported beside its decision the threshold its
    own rule gives once that bias is added to those cells: 1.38 (the registered receipt's
    `cost_of_rule.c_XS_with_finite_pool_bias`). A known bias left out of a bar is a loosened rule, so the House runs
    the rule's own answer with the bias in. 1.38 is the study's figure; nothing was chosen in this tree.
  - **What moved.** The receipt file: the study's receipt rebuilt at 1.38 by the study's own report and receipt
    builder from its saved run (sha256 `f7ce98b1...`; the registered one, `98acbb83...`, stays the study's result
    and the new file names it under `house_bar`, with how it was built). Every figure the receipt reads "at the
    adopted threshold" is read at 1.38 from the simulations the study saved; none was estimated. Its rule, stratum,
    margin, placebo bar, windows, lineage rule, flags, limits and note are the registered receipt's, word for word.
    The pin: `receipt_sha256`, `c_XS` and the sentence. The conformance vectors: computed again at 1.38 by the
    study's own vector builder (the smallest planted drift that passes, and the t between the screen's bar and the
    own floor, are other worlds at another bar), the inputs file made again from them, and the two by-hand vectors
    derived again (their own floors bind above either bar). The xs identity (the words of two evidence modules of
    `league/xs` about the receipt and the vectors; no statement of either changed, and no panel band exists).
  - **What did not move.** No line that judges, sizes or trades. The options execution fingerprint, the equity
    identity and the money digest are main's. A22's four rules, below, are unchanged.
  - **The cost: about two points of power at +10% a year.** The two receipts' own rows, `power.<archetype>` at
    `XH|N0-S|e10`, first figure (the full gate, own floors on, a planted net residual edge of +10% a year):

    | archetype | at 1.30 | at 1.38 | lost, points |
    |---|---|---|---|
    | X1 | 44.33% | 41.91% | 2.42 |
    | X2 | 46.41% | 44.57% | 1.84 |
    | X3 | 49.83% | 47.35% | 2.48 |
    | X4 | 69.98% | 68.40% | 1.58 |
    | X5 | 28.08% | 26.12% | 1.96 |
    | X6 | 33.86% | 33.47% | 0.39 |
    | X7 | 52.87% | 50.28% | 2.59 |
    | X8 | 67.58% | 65.56% | 2.02 |

    Over the 48 rows of the three calibration sets the holdout-only power falls by 0.29 to 2.64 points (median
    1.93) and the full gate's by 0.25 to 2.59; at +4% a year the full gate's falls by 0.10 to 1.94 (median 1.22),
    from a level that was already low.
  - **What it buys** (`fp_zero_edge_max`, `beside_calibrated_reading`): the largest zero-edge rate of any
    calibration cell is 10.02% (11.15% at 1.30) and its largest 95% bound 13.11% (14.82%); over twenty more
    bootstrap seeds the worst bound no longer reaches the owner's 15% wall (2 seeds of 20 at 1.30, none at 1.38).
    It does not close what A22 holds: the largest style-known rate is still 30.0% (34.9%), and one zero-edge
    mechanism given eight looks still passes at least one in up to 54.9% of worlds (63.1%).
- **A receipt at another bar lands the same way, in one commit:** the file; its pin, by `league.xs.screen.pin`; the
  vector file from the study's vector builder at the new bar, the inputs file made again from it and the two
  by-hand vectors derived again; and the vector file's sha256 in `league/tests/test_e4_stubs.py`. CI holds the pin
  to the file and the three vector files' bar to the pin's (`test_xs_screen.TheCommittedPin`). The vectors
  themselves read no pin: each runs under the bar its own file states. A floor cached under the old bar is run
  again (`screen.floor_fits`).

**The three duties the pre-registration gives the House** (`league/swarm/elane_xs.py`):
1. **Both Train series of every program that reaches the pre-check are kept**, passed or refused: the residual and the
   universe excess, by session (sealed family state; the lineage rule reads them for every later program, and no
   adoption ever clears them).
2. **The XS1 looks of each agenda cell are counted.**
3. **Beside every live panel trade the House states the sentence its receipt fixes**, filled for the program: its bar
   and own floor, its own in-sample rate, the earlier looks in its mechanism cell, whether its P&L is basket-led or
   selection-led, its style label and its flags. The `dlane` report prints it under the label EQUITY (PANEL).

**The captain's A22: what the House holds before any real money on an XS1 pass** (from the study's review; House
rules: the first three are enforced in `league/swarm/elane_xs.py` `look` and held by `league/tests/test_elane_xs.py`
`TheCaptainsA22`, the fourth is a fixture `league/tests/test_xs_screen.py` holds the floor to; A23, above, then
moved the receipt's bar and changed none of them):
1. **A STYLE-OPEN program takes no live seat on an XS1 pass alone.** The study measured that a no-skill tilt to a
   style that happened to win the holdout passes far above the owner's wall. So the House computes each panel
   program's loadings on size, beta, 12-1 momentum and volatility from its Train holdings (`league/xs/style.py`: a
   lot's rank among the day's eligible names at its decision close; a program's loading is the mean over its Train
   lots weighted by each lot's dollars AND by the sessions it was held: what the program held, not what it bought,
   so a tilted core kept for months beside a small counter-tilted satellite churned weekly is read as the core) and marks it style-open by one fixed, tested rule (any loading at or beyond the rule's tilt, or
   too few lots to read). **A style-open passer is RECORDED AND SHADOWED, NEVER SEATED:** the look says passed with
   seat "style-open", the family takes no band and no proof, and the report names it and why. Its way to a seat is
   the forward route. The rule is holdings-based and direction-blind; its cost, stated: a momentum or a low-volatility
   program is style-open by construction.
2. **At most 2 XS1 looks an agenda cell** until a forward verdict exists in that cell (the receipt's
   `family_wise_8_max`: one zero-edge mechanism given eight looks passed at least one in more than half of the
   study's worlds at its worst). No forward verdict can exist before the forward route is measured, so the cap is
   flat in this release. A look the cap holds back is not spent: the family waits.
3. **The equity code review and the contamination probe run BEFORE a panel look.** The review's rubric for a panel
   program refuses an embedded return table and any recognition of a calendar period (and any use of the slot numbers
   beyond naming targets, any search for a price level). The probe is release E3's, with the panel strata: until it
   has a published result for the route that wrote the program, the look waits. **The swarm never opens the probe's
   own file** (release E3's seal: that file holds counts and rates of the eras programs are judged on, and no module
   of `league/swarm` may name it or import the probe). It reads THE LOOK PERMIT, `<state>/xs-look-permit.json`, which
   the probe's job writes when it publishes a route's panel strata: for each route `at`, `model` and, a stratum and
   era, the two words `readable` and `recalled`, and nothing else. The House's job asks four strata of the ETF
   lanes and none of the panel's, and writes no permit: every panel look waits. The panel's three strata and the
   permit's writer are built (`league/ops/contam_xs.py`; **The probe's panel strata**, above) and are not handed
   to that job yet; once they are, a look waits until its own route's probe has been published with them.
4. **A ninth conformance vector**, for the 2022-24-alone floor cell, beside the study's eight
   (`league/tests/fixtures/xs1_conformance_c.json`; `league/tests/test_xs_screen.py`).

**Read it** (read-only, on the box): the swarm log; `swarm.sqlite` events `swarm.status` with
action `elane_xs_train`, `elane_xs_window`, `elane_xs_clock` or `xs_evaluator_adopted`, and `swarm.gate` look events
with screen "XS1"; a panel family's state key `elane_xs` (its Train record: each version's verdict, fails and facts;
a version whose decides ran past their second in every run it was given reads `SLOW` with the seconds measured); kv
`elane_xs_cpu`, `elane_xs_zero_edge` (the weekly zero-edge pass rate of the bar: an alarm above 5%) and
`elane_xs_alerts`; the ops receipts of `equity_universe` and `equity_panel` (the two jobs' own record: counts and
verdicts only, never a price, never a ticker list; they record no House event) and the House's `equity.rebalance`
events (`scaled` when a decision's budget was under its sleeve); **the lane's own state**: the swarm heartbeat's
`equity.panel` ({`setting`, `mode`, `why`}: the mode as set, the EFFECTIVE mode, and the leg that holds it under the
setting) and the dlane report's `equity.panel_lane` (the same, with the equity roster and why each seatless
Candidate holds no seat); `<state>/equity-daily/panel/PANEL_MANIFEST.json` (coverage by year, the
verdict, `hs_share`, the nightly `i6`, `live_from`); in `live.sqlite`, `eq_rebalances` (one row an instance and
decision session) and `eq_instances.kind`.

**A session of a live panel program.** From 16:20 ET the chunked fetch of the day's columns (about 28 gateway calls
over two or three ticks; only while a panel program is live), kept as that day's file; at 16:30 the decide in the
live process's decider (no program code on a hold day; the eligibility of every held name is read every day); at
08:30 the bars are read again and compared with the kept file (a price that differs VOIDS that decision whole: its
planned buys and its program's own planned sells are cancelled together, so the book is never left selling a name at
one open that the standing target of the decision before buys back at the next; the House's own exits stand); next
session E1's own windows send the intents, sells first. A 16:20 fetch that RAISES (the bars route down, a chunk the
House refuses) is read again each minute inside the half-hour grace and is then a decide the House could not make:
one failed decide on a rebalance day, the hold day's alarm on a hold day, asked again every ten minutes and never
after the pre-open. A row the venue serves on a day that is no session, or with a field that is no number, is dropped
and counted (a warning), as the nightly job reads the same answer. Every buy goes through E1's sizing as a stock:
at most 20% of the sleeve and of equity, the invested cap, the House's cash rule, **the shared loss budget with a
stock weighing 0.40**, the $10 minimum. Every wall of E1 holds: long only, cash only, the kill switch and the stops,
never a forced or hand-placed trade. For a panel program a HOLD-day fetch failure of a held name is an alarm and
never counts toward the two-failed-decides exit (the captain's A17); a failed decide on a rebalance day still counts.
**A ticker change inside a held lot** (a few a year across the index): the equity book books the venue's NC activity
onto the lot the day it posts and FREEZES BOTH LANES' OPENS (`eq_freeze`: every equity entry and every options open)
until the owner's `--clear-equity-freeze`; exits go on. The panel's decide goes on too: the lot keeps its column and
its slot under its new symbol, found by the ticker it was bought under until the membership job has read the new
one (`league/xs/book.py` `columns(renamed=)`); the new ticker is not on the constitution's list, so the lot is not
eligible and the House exits it at the next open. The seating pass asks a panel program only on a close's kept
fetch once the next session's pre-open has passed: the panel's bars are never fetched inside a session.

**The panel's live rules (PRE-REGISTERED before `elane.panel.mode` may be "live").** Goal item 4 asks that live
results decide sizing up and demotion by a rule fixed before the first live trade. The text below is the build
spec's section 10.5, copied word for word (its "B10", "8.4", "10.6" and "section 19" are that document's own
numbers: the book patch that builds the record, the Validation step that writes the sigma, the forward twin, and the
owner's open decisions; "70948154" is the E1 commit it read). It was written before three of the captain's
amendments were in force; they change its dollar examples and none of its rules, and are stated after it.

> Goal item 4: live results decide sizing up and demotion by a rule fixed before the first live trade. E1's rules (`league/equity/bands.py` `edm1`,
> `sized_up`, `sized_sleeve_share`; the constitution's `demotion.*` and `sized.*` numbers) are UNCHANGED, as functions and as numbers. What changes is
> what a panel program's record feeds them, because they read each lot as an independent trade and a basket's lots are not: five lots bought on one
> date and sold on another share one market move and one fill minute. Read by lot, (1) the first rebalance's five closes meet `twin_min_closes` 5 with
> five copies of ONE date's fill gap, and a single 09:32 after a rising open sets the program to exits only for good; (2) two months in which the
> basket loses 3% a month give ten returns summing below -1.645 x sigma x sqrt(10) and demote the program on beta while its residual x is positive; (3)
> four weekly rebalances in a rally give twenty closes and a lower bound above zero from four dates. So, for an instance of kind "panel" only (B10,
> `xs.book.date_record`; plumbing: no evidence identity and no money digest moves, and no constitution number changes):
> - **One observation a close DATE.** The version's closed ":r" lots are grouped by `exit_day`. `returns` = one a date, in date order: the date's
>   summed lot cash over its summed entry notional. `n` = the number of close dates. `twin_gaps_bp` = one a date: the entry-notional-weighted mean of
>   `gap_bp` over that date's lots with a priced twin (a date with none gives none). `pnl` and `realized_net` are dollars, as now.
> - **Sigma.** `validation_r_sd` = the version's `sd_date_return` (the 2025 k 1.0 run's sd of the same per-date return; 8.4 writes it under E1's
>   `validation_r_sd_by_version`), so EDM1's sigma is a per-date sd from Validation, never the live lots' own; with none (under 2 close dates in 2025)
>   E1's fallbacks apply to the per-date returns.
> - **The same-risk buy-and-hold.** `bh_pnl` = the lots' dollars held in SPY over their own sessions: the sum over closed lots of entry notional x
>   (SPY's adjustment=all close on the exit day / on the session before the entry day - 1). ONE BASIS, by E1's own rule (`_bh_pnl` at 70948154: two
>   closes from two fetches straddling an ex-date are not one series): every close comes from ONE fetch of SPY over the lots' whole span
>   (`adapter.spy_closes`), made only by the daily band sync and only once the record holds the close dates sizing up needs (`sized.min_trades`:
>   the figure is read by nothing else); None before that and when a close is missing (sizing up then fails `beat_bh`, as E1's does). E1's
>   per-symbol reading would call a stock picker's benchmark the very stocks it picked.
> - **What each E1 threshold then means for a panel program:** EDM1's statistical leg acts from 10 close DATES (`demotion.min_trades`), its twin leg
>   from 5 dates with a priced twin (`twin_min_closes`), sizing up from 20 dates (`sized.min_trades`) with the mean per-date return's lower bound above
>   zero, P&L above `bh_pnl`, and 5 sessions at Probe.
> - **THE COST, stated.** EDM1's statistical leg cannot demote a panel program before its 10th close date: 10 weeks for a weekly program, 10 months
>   for a monthly one (by lot it would have acted after two dates, wrongly). Until then what bounds its loss is unchanged and counts lots in dollars:
>   the program loss line (`demotion.program_loss_usd` -$300, on realized Probe net), the $400 window and $800 total budgets with open risk at 0.40,
>   the daily and drawdown stops and the kill switch. On a $557 sleeve -$300 is 54% of the sleeve: it is a backstop, not a tight leash, and the
>   report says so beside every live panel program.
> - Done's meter is NOT changed here: a closed lot is one close until the owner decides otherwise (section 19); H's report line shows the distinct
>   close dates and the date-clustered t beside it (A14's reporting).
> - Tests (`test_xs_book.py`): the three scenarios above on E1's own `edm1` and `sized_up` (none fires by date; each fires by lot); the per-date
>   returns and gaps on a golden six-lot, two-date fixture; `bh_pnl` against a hand value across a dividend; an ETF instance's record is byte for
>   byte what E1 builds today.

Read with the amendments in force, which the text above predates:
- **THE PANEL SLEEVE AND THE PANEL SEATS (release E4 step two; the constitution's `equity_money.panel`; until the
  pre-registered study EQDONE-5 rules, 1 seat at 0.10).** A panel program holds a seat of a POOL OF ITS OWN
  (`panel.seats`, 1, bound 0 to 2; the swarm's `elane.panel.seats` may only lower it) and never one of the ETF
  programs' `probe.max_programs`: the seat rule ranks the waiting panel programs inside the pool alone, by the
  same K, and the ETF seats, their plan, the idle test and K are untouched. Its sleeve is `panel.sleeve_share` x E
  (0.10, bound 0 to 0.25, never above the Probe sleeve: a table with the Probe sleeve under the panel sleeve is
  refused, so an operator who sets `probe.sleeve_share` to 0 sets `panel.sleeve_share` to 0 with it, or uses
  `panel.seats` 0). The window stays ONE and first come (A8.6 as registered). A program held on a failed leg keeps
  its seat; nobody is seated into it. Rule arithmetic at E = $2,000 (a one-ETF lot at the Probe sleeve 0.50 is
  $500.00, $100.00 of open risk; a stock weighs 0.40):

  | eight names at 0.10 x E | the decision's budget | the basket | its open risk |
  |---|---|---|---|
  | alone, the window untouched | $200.00 (the sleeve) | 8 x $25.00 | $80.00 |
  | beside three HELD one-ETF lots ($300.00 at risk) | $200.00 | 8 x $25.00 | $80.00 ($380.00 of $400 in all) |
  | beside three HELD one-ETF lots and $50 of window loss | $125.00 | 8 x $15.62 | $49.98 |
  | beside four HELD one-ETF lots ($400.00 at risk) | $0 | none | the window is full |

  The whole basket fits beside three one-ETF lots with no loss in the window while 0.19 x E is at most $400 (E up
  to $2,105). THE BUDGET SEES THE LOTS ALREADY HELD, never the other programs' buys planned for the same open
  (`_panel_budget`): the ETF programs' intents are worked first at the open (intent order, and a panel family's id
  sorts after them), so at an open where ETF lots are also bought they take the window's room first and the basket
  is cut name by name at the send or refused, not scaled. A name is 0.0125 x E ($25.00 at E = $2,000), so a basket
  scaled under 800 / E of its sleeve (40% at E = $2,000) has names under the $10 order minimum: they are REFUSED,
  and each refused entry is an A14 difference (a cut one keeps its key and is none). A held basket also takes room
  in the shared window that a later ETF entry would have had (first come), so ETF entries are refused or cut more
  often. Neither cost is measured yet: A32 modelled ETF programs only, and EQDONE-5 measures one panel seat at 0.10
  beside six ETF seats at 0.50 before a panel seat opens.

  ITS COST, PLAINLY: one more program on real money at once (XS1's zero-edge pass rate at the House's bar is at
  most 10.02% a cell); a basket's lots closed at one open are ONE market move, so Done counts a panel program's
  closes by close date (**Done counts a panel program's closes by date**, below) and the direction report states
  the distinct close dates beside every checkpoint; a lot of 0.0125 x E earns or loses cents, so Done's sign is
  carried by the ETF lots and the tally's hole; the -$300 program line is 150% of a 0.10 x E sleeve at E = $2,000.
  The rows of the tables below are the Probe sleeve's, which a panel program took before step two. Rollback:
  `panel.seats` 0 (one money-digest move; nobody is unseated, no lot is sold). Held by
  `league/tests/test_equity_panel_seats.py`.
- **Done counts a panel program's closes by date** (release E4 step two; the review of step two, its major; A
  TIGHTENING until the owner rules otherwise, and the spec's "a closed lot is one close" above is replaced by it).
  Done's 30 closes, every later checkpoint (each 10th) and the "at least 5 each from at least 2 programs" read
  DONE'S COUNTS (league/ops/dlane_report.py `done_counts`): every ETF or options close is one count as before, and
  a PANEL program's lots closed on one New York day are ONE count, placed where the first of them closed (the
  checkpoint of the K-th count reads the closes of the first K counts, `first_counts`). The reading's and each
  program's `closes` are these counts and `lots` stands beside where they differ; `close_dates` (A14_BESIDE_DONE)
  stands beside as before. WHY: one rotation of a 0.10 x E basket is 8 to 12 lots of one date and one market move,
  worth cents; counted a close each it pulled the 30th close and every later checkpoint earlier (Done read more
  often, with no added information) and could meet a second program's 5 on one date alone. COST, STATED: a panel
  program adds one count a rebalance date, so it takes 5 rebalance dates (5 weeks for a weekly program) to be one
  of the 2 programs, and its lots add nothing to the 30 beyond their dates. An ETF-only Done is read exactly as
  before (held by league/tests/test_dlane_report_a14.py `DoneCountsAPanelProgramByDate`). The owner may rule
  otherwise (a lot each, or panel closes counted apart); the captain records the ruling and its cost in
  CAPTAIN-AMENDMENTS before any panel seat opens.
- **The Probe sleeve** is the constitution's `equity_money.probe.sleeve_share` x E. The text's "$557 sleeve" is
  0.25 x E at about $2,229, which IS the design in force since release E5-S (six seats at 0.25 x E; **The seats and
  the sleeve**, below); between E1's deploy and E5-S it was the captain's A20, three seats at 0.50 x E, and
  `set_design` may move the pair again. The rules do not change with the pair; the dollar examples scale with the
  sleeve. What does not scale is the shared loss window: a stock weighs 0.40 of it, so a FULL sleeve of stocks is
  0.40 x the sleeve of open risk against $400.
  **THE RULE THAT KEEPS A BASKET WHOLE: IT IS SCALED TO THE ROOM** (`league/equity/live.py` `_panel_budget`;
  plumbing, no money row and no digest move, and no wall loosened). E1's sizing holds the window a name at a time
  at the send, so where a full basket does not fit, it would buy the first names whole and cut the last, every
  rebalance, while the Gym twin buys them all; a cut name is never resized (the KEEP rule), so the basket would
  stay lopsided until that name is sold. So the budget a panel decision is handed is the smaller of the sleeve and
  what a FULL basket fits now (the program's own lots at their marks plus the loss budget's room over the stock
  weight; the invested cap likewise), and every name is its weight of THAT. Rule arithmetic at E = $2,229:

  | AT THE DESIGN IN FORCE: six seats, sleeve $557.25 | the decision's budget | a five-name basket | its open risk |
  |---|---|---|---|
  | alone, the window untouched | $557.25 (the sleeve) | 5 x $111.45 | $222.90 |
  | after $100 of window loss | $557.25 | 5 x $111.45 | $222.90 |
  | after $200 of window loss | $500.00 | 5 x $100.00 | $200 |
  | beside five ETF programs each holding a one-ETF lot ($278.63 at risk) | $303.43 | 5 x $60.68 | $121.37 |
  | a 12-name basket alone | $557.25 | 12 x $46.43 | $222.90 |

  | AT A20's DESIGN: three seats, sleeve $1,114.50 | the decision's budget | a five-name basket | its open risk |
  |---|---|---|---|
  | alone, the window untouched | $1,000.00 | 5 x $200.00 | $400 (the whole window) |
  | after $100 of window loss | $750.00 | 5 x $150.00 | $300 |
  | beside one ETF program invested and $88.55 of window loss | $500.00 | 5 x $100.00 | $200 |

  (`league/tests/test_e4_e2e.py` trades the first row of the design in force against a fake venue on money's real
  rules: five lots of $111.45, the sleeve whole. `test_equity_book_panel.TheWholeBasketIsScaledToTheRoom` holds
  the scaling itself on a table of its own at A20's design, where a basket alone met the window: its first and
  third rows.) The lot's WEIGHT is the same as its twin's (dollars over the decision's own budget), so the two
  agree. Held lots are never resized, and a budget that fell sells nothing. The send's own sizing still holds every
  wall a name at a time, so a budget that moved between the decision and the open cuts the last name, as before
  (and a name the send CUT stays cut until it is sold; only a name it SKIPPED is bought later by the standing
  target).
  **WHAT THE SCALING DOES NOT DO (the verification's residual; as built, held by the same class's send tests at
  A20's design).** It sizes a basket bought from flat, or rotated whole. Once the lane's lots and the window's loss
  leave less room than the basket holds, a PARTIAL rotation's new name is refused for budget at the send: the sale
  of one name frees 0.40 x that name of room, less than the shortfall, and the program holds one name fewer than
  its Gym twin until a rotation frees more room than is short, or the loss leaves the 20-session window (the
  standing target asks for the name again each close). At A20's design that was after ANY net loss, because a
  basket alone was the whole window (measured there on the fake venue: $100 of loss and one name rotated, the sale
  goes and the buy is refused). At the design in force a basket alone leaves $177.10 of the window, so alone it
  takes a loss above that; beside five invested ETF programs the window is full ($278.63 + $121.37) and it is any
  loss again.
  **THE COST, stated:** the window is one, shared, first come. A panel basket weighs four times what a one-ETF lot
  does ($222.90 against $55.73 of open risk at the design in force), so one panel program and five ETF programs
  ask for $501.53 of a $400 window: whichever buys later is scaled or refused, and the options Probe lane's opens
  wait for what is left (six invested one-ETF programs alone leave it about $66). **This is a money question and
  it is open:** a panel sleeve of its own (a constitution row; the Probe sleeve is now the 0.25 x E the captain
  leaned to for it, so the row would say how a panel program's share and its 0.40 weight sit beside the ETF
  programs', not make its sleeve smaller) is the owner's deploy with a money-digest move, decided with the
  universe before any panel program is seated. Nothing is changed here: in the release that takes the lane to
  "train" no panel program can hold a seat, so no order meets this rule.
- **Sizing up is parked** (the captain's A21: `equity_money.sized.min_trades` 1000, for every equity program): the
  text's "sizing up from 20 dates" reads "from `sized.min_trades` close dates", which no program reaches while the
  step is parked. EDM1's legs, the -$300 program line, the window and the total are as the text says.
- **Hold days** (the captain's A17, granted): for a panel program a hold-day fetch failure of a held name is an alarm
  and never counts toward the two-failed-decides exit; a failed decide on a rebalance day still counts.

**The universe deploy (R-E4b): ONE commit, deployed separately, the money digest moves once.** A panel program can
only buy what the constitution's `equity_money.universe` and the gateway's `STOCK_UNIVERSE` both name, and E1 named 18
stocks. R-E4b grows the stock list to **the panel's tradable union: every symbol that was an S&P 500 member on any
session of the 36 months before the generation day and is tradable, fractionable and unmasked that day**, E1's 18
among them (about 560 names, an estimate). The ETFs do not change; NO bound, share, weight, seat or cap changes.
- **Why a 36-month union and not the day's members.** A list of today's members, regenerated each quarter in a public
  repository, IS a point-in-time membership history. A union says only "was a member at some time in three years",
  carries no date, and needs regenerating about once a year. A name on it that is no member today is simply never
  eligible; a new member is not eligible live until the next regeneration (the store records that, so the replay of
  the day agrees); a removed member is sold by the House's own exit, and a sale of any held symbol always passes the
  gateway, whatever its list.
- **What is committed** is a ticker allow-list, sorted, between two marker comments in each file: no date, no weight,
  no history. `league/equity/config.py` `UNIVERSE` (E1's 35, hashed into the equity identity and every ETF run) is
  NOT changed: it stays inside the constitution's universe (`league/tests/test_equity_money.py`), and the daily ETF
  job still fetches the 35.
- **How** (the owner's machine; a clean checkout of main at a head CI is green on):
  1. On the House the `equity_universe` job writes `<state>/equity-daily/universe/tradable.json` ({"as_of", "stock"})
     once its audit passes. Copy that ONE file to the owner's machine. It is never committed.
  2. `python3 scripts/gen_universe.py --from tradable.json --gateway-patch ~/universe.patch`. It rewrites the
     generated block of `league/constitution.py`, re-pins `PINNED_DIGEST`, prints both digests before and after, and
     writes the gateway's half as a patch (it never writes into `gateway/`). It REFUSES, and writes nothing: a ticker
     outside the gateway's `STOCK_SYMBOL` pattern, an ETF, a symbol twice, a list under 450 or over 650 names, a list
     that lacks one of E1's 18, an input with any key but `as_of` and `stock` or any entry that is not a plain ticker
     (a date beside a symbol), and its own rewrite unless it changes the stock list and nothing else.
  3. `git apply ~/universe.patch` (the owner's step: `gateway/` is the owner's), then
     `python3 scripts/gen_universe.py --from tradable.json --check`, `python3 -m league.ci --no-tests` (the two lists
     are one list: `gateway_stock_problems`) and `cd gateway && npm run check && npm test`.
  4. ONE commit holding `league/constitution.py` and `gateway/lib/caps.mjs`, and nothing else, marked **UNIVERSE (moves
     the money digest; deployed separately)**, with the two digests in this file's entry of CHANGELOG.md. CI green on
     the exact head.
- **What step two carries beside the list.** The gateway's STATIC half (a patch in the captain's scratch: the two
  markers the generated list sits between, and the gateway's tests made to accept a generated list; it changes no
  list, and step 3's `npm test` is green on a grown list only with it applied, so it is applied first or deployed
  earlier). The merge list's follow-up for the lane's two protected paths (**Deploy class**, below). And THE MONEY
  ROW OF A PANEL SLEEVE (`equity_money.panel`, built in step two): the generator's own rewrite changes the stock
  list and nothing else, so the row is its own edit of the constitution, already in the tree; deployed in the same
  release as the universe the money digest moves and the grant re-ratifies once, deployed earlier it moves once
  more (**The panel's live rules**, above).
- **The order of the two deploys, and when.** FIRST the gateway (`npx wrangler@4.129.1 deploy`; a longer allow-list
  there is inert: the House still admits only what its own constitution names). THEN the House release
  (`floor_box.py deploy`), when no order is in flight: `digest()` and `money_digest()` move ONCE and the standing
  grant re-ratifies at the House's start (job `grant`). The House first would only have its new buys refused, never a
  wrong order. **BOTH DEPLOYS GO BETWEEN TWO PRE-OPENS** (after 09:30 ET, before the next 08:30): the order is safe
  but it is not silent, because the pre-open's check 10 holds the DEPLOYED gateway's list equal to the constitution's
  and raises a public warning when they differ. As a second guard that warning names at most 10 tickers a side and
  counts the rest (`league.ci.stock_agreement`), so a gateway deployed on a Friday with the House on Monday posts
  three short lines, not three lists of 540 names.
- **Verify** (read-only): the gateway's `/v1/health` `stock_buys.symbols.stock` has the list's count; on the box the
  grant is ratified on the new money digest (`grant` job receipt; pre-open check 2); the next `equity_panel` run
  records `live_from` in the panel manifest; the next pre-open's check 10 says the deployed gateway's stock list
  agrees with `equity_money`. The equity identity and the options fingerprint are the ones from before the deploy.
- **Roll back.** A House release from before R-E4b brings the old money digest back (the grant re-ratifies on the
  owner's deploy of it) and retires a panel program, whose lots exit at the next open by E1's rule; sells of any held
  symbol always pass the gateway. **THE GATEWAY IS NEVER ROLLED BACK BEFORE THE HOUSE** (a shorter list under a House
  that still buys the long one refuses those buys and, at the next pre-open, warns). E1's guard stands (no release
  older than E1 while an equity lot is open).
- **Afterwards:** regenerate about YEARLY (`universe_max_age_days` 400 is the alarm), or when `live_ready` fails on
  `live_min_tradable_share`. Each is this section again: an owner deploy of both, and one more digest move.
- **Margin, shorts, borrowing:** none. The panel is long only and cash only (A1), inside every wall of the goal.

**Stop it, from the lightest** (each a settings change read on the next loop pass, no deploy; the mode goes DOWN one
step at a time, and each step is the rollback of the one above it):
1. `elane.panel.mode=gate`: no panel program takes or keeps a seat; Validation and looks go on. For a program
   already at Probe: the swarm gives its family no row (`league/swarm/bands.py` `read`), so an entry already planned
   is HELD AT THE SEND (the book asks at every send: `league/equity/live.py` `_seat_block`) and missed at its
   cut-off; at the day's band sync (the 16:30 decide) the book retires its instance on the lane's own word
   ("demoted: the panel lane is not live ..."), it decides no more, and its lots exit at the next open by E1's rule.
   The family's band in the swarm store is NOT moved, so it keeps its roster seat, and when the lane is live again
   the same instance runs again (E1's revival rule); to free the seat for another program, re-band or retire the
   family (`To stop a program`, below). **ONLY THE SWITCH RETIRES. A LEG THAT FAILS ON ITS OWN STOPS THE OPENS AND
   NOTHING ELSE** (the build spec's section 17: "its opens stop, exits go on"): with the switch left at "live" and
   the nightly I6 not equal, the twin marker two sessions behind, the panel store stale, the universe too old or too
   thin, the spreads' share under its bound or the coverage verdict gone, the family has no row (every entry is held
   at the send) and the store's word on its instance is "held": the book KEEPS the instance and its lots, asks it at
   every close as before (its program's sells, its ineligible lots, max hold and the two-failed-decides rule go on),
   and sells nothing on the leg. The book says so once a decision day, critically, with the leg named, and the
   pre-open's check 10 says it again each morning. When the leg holds again the row is back and the standing target
   buys what it owes. To sell a held basket, put the switch down. **A switch or a file that cannot be READ retires
   nobody either:** a swarm.json, a panel manifest or a twin marker caught mid-write gives the family no row (so
   nothing opens) and the store's word is "unknown" (so nothing is sold on it).
2. `elane.panel.mode=train`: no Validation try and no look; births and Train research go on.
3. `elane.panel.mode=off`: no panel birth, no Train run, nothing of the panel in any request, and no data job (each
   answers `skipped`: the store stays as it is and goes stale; a lane switched on again later picks up where it
   stopped: the daily run appends the sessions it missed, and a whole refetch runs when the last one is over six
   and a half days old).
4. E1's switches stand above all of it: `elane.mode=off` stops every equity round, the panel's too; and
   `equity_money.enabled` false (a constitution change) stops every equity open. Exits never wait on a switch.
A panel lot is an equity lot: **Roll back: flatten first** (the next section) is the rule for a House rollback while
one is open.

**Rollback past E4 (a CODE rollback to a release from before this one, such as main `8ab31e32`), after the lane has
been at "train".** The switches above stop the lane inside this release; a release from before it does not know the
lane at all. Its `league/swarm/store.py` scopes every options reader by `OPTIONS_ONLY_SQL` = "structure NOT IN ('etf',
'stock')", so an alive panel family reads there as an OPTIONS family: measured on main `8ab31e32`'s real swarm loop
over a store with three panel families in the Gym band, the tournament gave the class "panel x none" half its
allocation and the options population (the architect's count, the idle pass) counted the three; the options lane's
research and births then share their room with families its code cannot run. It costs no money row (a Gym family
holds no seat). So, in order, while this release still runs:
1. `elane.panel.mode=off` (`python3 set_swarm.py elane.panel.mode=off --apply` on the owner's machine): no panel
   birth after the next loop pass.
2. On the box, from this release: `/workspace/.venv/bin/python /workspace/current/scripts/panel_rollback.py --state
   /workspace/state` lists the alive panel families and their bands (read-only); with `--apply` it retires each
   (`SwarmStore.retire`, one `swarm.retired` event each, in one transaction). It refuses, writing nothing, while the
   setting is not "off" or while a panel family is outside the Gym band (that is **Roll back: flatten first**'s; in
   step one every panel family is in the Gym band). A second run lists none.
3. Only then the code rollback (`python3 scripts/floor_box.py rollback`). The retired rows stay (append-only); this
   release deployed again later reads them as retired panel families. The live book's `eq_instances.kind` and
   `eq_rebalances`, and the forward record's panel rows, need nothing (the step-one paragraph above; **The forward
   twin**'s Rollback).

**What moves what.** A change to an evidence module of `league/xs/` moves the **xs identity**
(`league/xs/identity.py` `xs_fingerprint`): every live PANEL band goes back to the Gym for fresh qualification (no
new try, no new look) and no ETF family is touched. A change to an evidence module of `league/equity/` moves both
identities. `league/xs/book.py` and `identity.py`, `league/equity/live.py` and `kinds.py`, every file of
`league/swarm/` and `league/ops/`, policy.json and the constitution move NO identity. A panel band is current only
under the code the running release holds (its proof names the xs fingerprint and the program's hash), read from the
release's own files, never from a stored value. The constitution's universe moves `digest()` and `money_digest()`,
and nothing else does in E4.

**Deploy class.** Both releases are owner deploys. Behind `league/ci.py`'s wall (`FORBIDDEN`: no role changes them and
the updater never self-deploys them): `league/xs/` (the panel's evidence, its screen XS1, its live adapter),
`league/ops/` (its data jobs), `docs/benchmarks/` (XS1's receipt), `league/swarm/policy.json` (its pin and its
switch), and from this release `league/swarm/elane_xs.py` (the Train bar, the look, lineage, A22's seat rule) and
`scripts/gen_universe.py` (the author of a money rule). **One follow-up at the gateway**: its merge list
(`gateway/lib/protected.mjs` MERGE_FORBIDDEN) gains those two in its next deploy (E2's five and E3's three are in it
already); until then the two wait, alone, in `league/ci.py` `PENDING_GATEWAY`, and the updater's wall holds them
either way. The follow-up is written as one commit's patch for the owner (the gateway's line, `league/ci.py` and its
test's pins together), in the captain's scratch; it is a tightening, moves no id, and may go with either step.

**The alarms** (House alerts, each with its cause; W warning, C critical): the coverage verdict not "ok" (W; C when
"insufficient"); the universe audit failed, or the membership pin did not advance for 60 days (W); the changes table
read cut short (W) and membership staler than `membership_max_stale_days` (W; looks wait); a full refetch failed two
nights running (W); `equity_panel` failed two days running (C while a panel program is live); the nightly I6 not
equal (C: the mode reads at most "gate"); a panel decision's morning re-read "mismatch" (C: its buys are cancelled) or
"unread" (W); the 16:20 fetch decided late and incomplete (W); the spreads table under its bound in mode "gate" or
above (W); the zero-edge pass rate of the Train bar above 5% (W: the bar is too loose); a panel version's judgment
stopped three times by decide timeouts that did not repeat (W, `elane_xs_clock`: the box's clock; no run that lost
a decide is judged); an E4 job or a Train run
found RUNNING at a wall (C); the xs identity moved while a panel lineage is in Probe (C, said before the deploy);
`live_ready` false while a panel program is live (C: its opens stop, its exits go on, and nothing is retired or sold
on it: its entries are held at the send, the book's alert at the day's band sync names the leg, and the pre-open's
check 10 says it again each morning); the twin marker a night behind (W) or two (C); a rebalance
session whose live and twin orders disagree (W); a standing-target buy still unfilled after 5 sessions (W); a
rebalance recorded late (W); two failed panel decides (C: E1's exit rule fires); the committed universe older than
`universe_max_age_days` (W: an owner step); the pre-open's gateway and constitution lists differ (W, at most 10 names
a side: the two deploys were not made between two pre-opens). **Where each is raised:** the lane's own (its
effective mode under its setting with the leg named, the spreads' share under its bound from "gate" up, the
universe's age, a store two nights stale) by the swarm loop at each equity round, once a UTC day each
(`elane_xs.health`: `swarm.status` alerts `elane_xs_mode`, `_spreads`, `_universe_age`, `_stale`); a job found
RUNNING at a wall, or a panel run found running inside a session, by a detector that looks AFTER the work
(`equity_universe.watched` around all six jobs: a critical alert and `wall` in the receipt; `elane_xs._timed` around
every panel run: `elane_xs_wall`);
`live_ready` false while a panel program is live by the book at its band sync and by the pre-open; **the three
that read the forward record** by the forward report (`league/ops/forward_xs.py` `alarms`; each warning is also an
alert of the `forward_report` job, and they ride the direction report's alarms): FX1 the twin marker behind the
panel store (one session: a night missed; from two the lane holds every open, which the book says critically), or
an alive instance's twin behind its due day; FX2 a REBALANCE session whose live and twin orders disagree (told
once, with its cause); FX3 panel programs left stale two panel nights running. The residual beside a close is the
direction report's line ("The forward twin", above). The run record's `factors` (the House's own panel factors)
has no reader in this release (the loadings beside XS1 read French's): the probe's stratum P6 asks about the same
factors and computes its truth by the same rule from the panel store (`league.ops.contam_xs.factor_days`, held equal
to a real run's `factors` by `league/tests/test_contam_xs.py`), not from a run's record.

**Memory of the panel job** (measured at 700 assets x 2,455 sessions under the ops child's own limit, its address
space capped 500 MB above its start): the daily run peaks at about 384 MB of the 527 MB cap whatever the number of
names restated that night, a whole refetch at about 395 MB, the first fetch at about 346 MB. The old store is mapped
by one reader at a time and never while a whole history's answer is held as rows, and a whole history is asked 8
names a request (a page is 10,000 bars whatever the batch, so it costs no call). Each session adds about 0.1 MB.
`league/tests/test_equity_panel.py` `TheJobFitsItsMemory` runs the job at that size under that limit.

**Cost.** Data $0 while the coverage verdict is "ok" (Alpaca SIP through the gateway; the membership sources through
its web reader); model spend stays inside E2's `elane.e2.usd_day` (a panel brief is about a quarter longer; no new
cap); House CPU at most `cpu_seconds_day` of panel Train a day (4 h), the jobs a few minutes, the weekly zero-edge run
under 3 h on Sunday; gateway calls about 45 a day, 56 more a session while a panel program is live, about 1,260 on the
weekly refetch, and 6,000 a night for about nine nights while the spreads table is first filled.
**On the box's one core, estimated and not yet measured there** (E1's engine floor reads about three times
slower on the box than on the build machine; a scored version was timed on a synthetic panel of the real one's
size): a scored panel version is four to five minutes of the core in a dozen runs, its longest run under a minute
against a run budget of ten, the evidence child about 280 MB; the zero-edge job, which stops itself inside its own
budget, will finish about 32 to 40 programs a Sunday, not the 100 `zero_edge_programs` names. **So at
`elane.panel.zero_edge_programs` 100 a box Sunday never completes a week, and the zero-edge alarm (a COMPLETE week's
pass rate above 5%: `league/ops/xs_zero_edge.py` needs the week's programs at `zero_edge_programs`) cannot fire on
the box until that is fixed** (a rolling rate over the kept weeks, or the setting at what a Sunday fits): owed before
"gate" (step two). In step one no look runs, so nothing waits on it. The spreads job's CPU is the tightest row
against its limit. Read each off the first receipts.

**Verify after R-E4a** (read-only): policy.json on the box has the `elane.panel` block with `mode` "off" and
`elane.screens.equity_xs` holding the receipt's sha256; before the switch the swarm log has no panel line,
`swarm.sqlite` no panel family, and the data jobs' receipts say `skipped` ("the panel lane is off"); after the
captain's first step up (`elane.panel.mode=train`), the next night's `equity_universe` and `equity_panel` have
receipts with counts and a coverage verdict, and no price or ticker in them, and from the first scored panel
version the forward record's panel night has its own (**The forward twin**, above: its verify list); the House's
start re-ratifies no grant (the money digest did not move) and sends no ETF band and no options band back to the Gym
(neither identity moved). The Saturday probe's receipt has no `panel` key and `<state>/xs-look-permit.json` does not
exist: the House's job is handed no plan.

**Not handled, stated.** A panel program is shadowed forward from its registration (package J), a style-open
passer too; what the forward route would do with that record is not built. **The House runs XS1 at the bar of the
receipt in the tree** (every threshold is read from it at runtime): the captain's A23 set that bar at 1.38, and the
rebuilt receipt is in the tree with its pin and its vectors. Two of the receipt's rows are not from saved
simulations: the study had saved its two report-only arms (takeovers and collapses; no-skill style tilts) at its
own bar only, so they were run again at 1.38 by the study's own command, after the same command at 1.30 gave the
saved results again; they decide nothing. A held lot's own `ret` (its raw close against its entry) still scatters
against its slot's return path by about a cent over the price (a weaker channel than the one `range` had; the review measured
a rank correlation of 0.45 with one over the price on synthetic panels), and a name whose ADJUSTED price is under
about two dollars (a later split of forty for one and more) is coarse in every field: the code review's "no search
for a price level" is what stands against both. A panel family born while release E3's folds are not recording
(`elane.memory.mode` not "record") has no hidden year: its Train bar reads all six Train years, and the Train map
says so; with the committed policy they record, and a panel family is born with one of the six held out. A panel program whose seat is withdrawn while the lane is
not live keeps its roster seat (its band is not moved). A bar the data audit blanks in the store (a daily bar its
minute bars contradict) is still in a live 16:20 fetch: the nightly I6 blanks the same cells before it compares, and
the decision of that day read the bar. **The spreads' share is of the Train eras' member-days** (`hs_share` in the
panel manifest: the share of them whose name has 8 samples at both fill points). A name is sampled only on Train-era
days it was a member (the last in 2024), so the share climbs through the backfill's nights, stands once the table is
whole (a little under 1.0: the names that were members on fewer than 8 sample days) and is moved by no later change
of the index; under `spreads_min_share` (0.90) the mode reads "train", nothing is validated and a seated program's
opens are held. It was first measured over today's members, where it fell with the index's turnover for ever; that
measure is gone. Its cost stays: every name that joined after 2024 is charged the universe's figure (the 75th
percentile of the measured names) in every run and in its twin. The screen does not match sub-industry, size or value: A22 (1) is the House's answer,
and it withholds a seat from every momentum and low-volatility program. A member added to the index after the last
universe deploy cannot be bought live until the next one (about 5% of names a year); the replay of such a day agrees,
because the store records which symbols the constitution named that day. Membership is read two sessions ahead in the
Gym and live knows only the changes the universe job has read by the decision: a change learnt late is a
live-versus-Gym gap the nightly I6 shows. Entry validity peeks one session ahead in the Gym (data validity, never a
return); live cannot. French's factor files do not reach the House (no route), so XS1's French label reads
"unmeasured" and the receipt's "style-open" flag attaches (the sentence says so); the style reading the House acts
on is its own, from a program's holdings (A22 (1)). `league/equity/config.py` still says in its docstring that the constitution's universe
equals `UNIVERSE`; since R-E4b it is the other way round (inside it), and the file is not edited because a byte
changed there moves the equity identity. Done's meter still counts a closed panel lot as one close; whether a panel
program's closes count by distinct close dates is the owner's open decision, and the report shows both.

## The forward record (release E3, Oct 2026): deployed 14:37Z Oct 11, 2026

E1 (two sections down) gives the equity lanes their live path and E2 (the next section) makes the swarm breed share
programs. E3 **records and measures**. From the first session after the look cap, every equity program the swarm judges
leaves a clean forward record on days no author saw, beside skill-free controls, and the House measures what that record
is worth. It moves no money, gates nothing, shows no generator anything new and writes no verdict: the screens, the
receipts, the sealed windows, the money rules, the stops and the kill switch are the ones E1 and E2 ship. The build's
contract is `league/ops/E3_INTERFACES.md`.

**No identity moves.** Nothing under `league/live/`, `league/gym/`, `league/equity/` or `league/constitution.py`
changes, no decider kind is added and no evidence module imports a file of E3, so the options execution fingerprint,
the equity evidence identity (A13) and the money digest are the ones E2 ships; no evidence is reset and no grant
re-ratifies (`league/tests/test_e3_identities.py`). Read at the integration with the repository's own functions
(`evaluator.execution_fingerprint`, `evaluator.equity_identity`, `constitution.money_digest`): the three are equal
on the E1/E2 tree this release is built on (`feat/equity-e2-int` at `5ad1f01e`) and on this tree, and equal on the
tree the packages were cut from (`5a6906ff`) and on that tree with the five packages merged. Between those two bases
all three DID move, by E1's and E2's own review fixes (the first-decision look-back in the store, the engine's
rounding tolerance, the live book, the money table): that is E1's and E2's deploy to state, not this release's.
**Merged with main** (Oct 11, 2026; main at `87f9fd0c`: releases E1, E2 and E2.2): this tree carries every line of
E2.2 (the reading rule, the contract's worked example, the equity lanes' own pace), and the three ids read on it are
main's, on Python 3.11 and 3.14.
**The forward record is ops only, by process:** `league/swarm`,
`league/equity`, `league/live` and `league/gym` import no E3 ops module and never name the forward store or one of its
tables (`league/tests/test_e3_seal_imports.py`), so no architect, researcher or reviewer can read a forward row. Every
E3 module is behind the updater's wall (`league/ops/`, and the three swarm modules in `league/ci.py` `FORBIDDEN`),
and the gateway's merge list names the three too (`gateway/lib/protected.mjs` `MERGE_FORBIDDEN`: the release's one
change under `gateway/`; nothing waits in `PENDING_GATEWAY`).

**What is recorded.**
- **The registry** (`<state>/forward.sqlite`, 0600, append-only by trigger; `league/ops/forward_db.py`,
  `forward_register.py`, hourly at :25): every equity version judged on the Train bar, PASSED OR FAILED, each
  captain-seeded program and each live instance. Non-passers are registered so that forward statistics are
  survivor-free: "do Train passers beat Train failers on days no author saw" is the one clean test of the bar itself.
  A version that could not be judged (its run failed, it was disqualified, it would not load) has no figure and is not
  registered. Each row freezes the program's text and parameters and is hash-chained; a version whose text does not
  hash to its own sha, or whose NEEDS the lane does not accept, is refused (a `register_skipped` event, once).
- **The controls** (`forward_controls.py`): 50 skill-free controls a universe group (index, sectors, defensive,
  stocks), registered with the group's first program. A control's lots are drawn by a counter hash that reads no bar
  and no price, under a program's position caps, fill points, half-spreads, fees and minimum hold, on an exposure
  grid. It is not matched to any program's turnover, so every comparison with the controls reads its COST-FREE series.
- **The nightly shadow** (`forward_shadow.py`, after the daily store, never inside 09:00-17:30 ET on a session): every
  registered program recomputed whole on its own forward days, in the job's own decider child, at 1.0x and 1.5x the
  half-spread; checkpoints at 20, 60, 120 and 250 counted sessions, then every 250. A checkpoint is recorded, never a
  verdict. Stored days whose recompute differs are a `restated` event, one a program and cause (the first rows stand),
  and every row carries the bars hash of the decision it came from: the vendor rounds adjusted prices to cents (and
  rescales the whole adjusted history on each ex-day), so a later store does not always give a decision the bytes the
  live one read, and a difference for that cause is data, never an error. A program's slice carries its NEEDS
  history + 1 sessions before its first forward day (E1's store hands them), so its first decision reads the bars
  the live book reads at that close. **A label that returns:** after a rollback of an equity evidence module the
  shadow opens a new series, `<label>~<the id it follows>`, so the newest engine id is always the series being
  written. **A night that ran with failures of the House's own** (programs left without rows by the forward store or
  by a child that could not be restarted, controls that could not be drawn, a step that raised, and since Oct 15,
  2026 a live instance's twin that raised or a lot's row not made: the twins' `finish.failed`) raises one House
  warning of counts and class names; nobody is marked and the next night fills what was left out. The panel night
  (`forward_xs`) raises the same warning, `finish.failed` included. An interrupted or deferred twin alone is not in
  it: it heals the next night, and FW9 tells a twin row still missing after that next night. **The night's
  deadline** (300 s before the next session's 09:00 ET) is read by every step, not the program loop alone: past it
  the timing table, each control and each live instance's twin run are `deferred` in the receipt (no failure) and
  the next night writes them, so a morning catch-up never holds the one ops slot into the pre-open jobs. **The
  queue** is a listing (no program text is held for the thousands a night may never reach); the one program a run is
  made of is loaded then, and a text that is not its registered sha's is never run. A program whose last attempt
  failed twice (in the night's child, then alone in a fresh one) stands behind its class until a run of it
  completes, and the loop keeps back a retry's seconds for each program on the retry list.
- **The morning marks** (`forward_audit.py`, 25 minutes before each open): a forward day is marked for the programs
  whose NEEDS hold a symbol the book's morning re-fetch found different, read from the book's own note (kv
  `eq_bars_audit`) and, for a day the note does not name, from its `eq_bars` audit rows; a marked day leaves the
  program's counted days and its row stays. The shadow's night makes up a mark the morning job missed before it reads
  any checkpoint. Then the registry's hash chain is verified whole.
- **The fills** (`fill_minutes.py`, `forward_twins.py`): the send-minute 1Min bars of the universe; the live-like
  price beside each official open and close; the live-like re-price of every shadow day; for each closed live lot, its
  fill gap against E1's twin split into timing and execution; and, session by session, whether the live program's
  intents were the ones a twin run started flat at its first decision gives (a twin set to the live book after each
  session that differs, since the captain's A29: "The twin is re-based after a difference", below).
- **The memory tables** (`league/swarm/elane_folds.py`, `elane_effects.py`, `elane_memory.py`; in the swarm store):
  **the hidden year**, below.
- **The contamination probe** (`contam_probe.py`, Saturday 00:10Z, at most `elane.contam.usd_run` dollars a run, one
  model route a week, inside E2's daily line): each route is asked what it recalls of the eras programs are judged on;
  the House scores the answers against a permutation by whole period and keeps aggregates only
  (`<state>/contamination.json`). A prompt carries no truth and no score. **Its dollars, as built:** a run's bound is
  the smaller of `usd_run` and what is left of the equity lanes' day when it starts (`elane_yield.room`, which E2
  holds to `elane.e2.pace_share` of the Sail model line: well under $3 a day at the shipped share), the room is read
  again before every call, and a run is skipped only when the room is zero; so a probe finishes over several
  Saturdays, keeping the cells it has scored. **A request key is asked once:** every run's keys are its own (the
  route's `attempts` counter is in the key), because the router answers a repeated key from the provider's stored
  row at that row's original cost, and the swarm's loop blanks stored answers after an hour. A cell that a stop cut
  is asked again whole by the next run and paid for again (at most one cell a stop); to keep that rare a cell is
  begun only when the run's dollars cover it at the price of the dearest batch so far, an answer with no text ends
  the run and is never scored, and a key the swarm's spend rows already carry is not asked. Its request keys carry
  the equity lanes' mark (`swarm:elane:probe:...`), so the swarm's meters count it as the equity lanes' spend and
  the options researchers' hourly pace does not read it as theirs. An answer the router's window fallback gave on
  another profile is scored by nothing (one route, one model). **The captain's call:** at `usd_run` 3.0 a probe may take the whole of that
  Saturday's equity research dollars; a smaller value (0.25 to 0.50) leaves the researchers their day.
  **On a tree that carries release E4** the probe can be handed a plan of the panel strata P4-P6
  (`contam_probe.probe(ctx, panel=...)`: asked after its own cells, inside the same dollars; **The probe's panel
  strata**, in the panel lane's section above). The job (`run`) hands none: it is this probe and nothing else.
- **Release receipts** (`release_receipts.py`, read by the stall job): a release declares the funnel metric it expects
  to move (`league/ops/release_receipts.json`); the House reads it back after its window and lists the verdict.
  Listed, never reverted. E3 declares two, each read after a week: program-sessions accrue, and out-of-fold rows.

**Forward days begin after the look cap.** The first forward day is the session after `league.equity.config.LOOK_CAP`
(2026-10-12 while the cap is 2026-10-09): the look reads its 194 calibrated sessions and nothing later, and every day
after them is forward only. A program first decides at the first close after its code existed and has no fill, mark
or P&L before the session after that. The time its code existed is the swarm's own `swarm.elane` event with `pass`
"scored" for that family, version and code sha (the swarm's event log is append-only); with no such event it is the
hour the registry first saw the program. No registry row claims a time before its evidence.

**The forward alpha is pre-registered** (so that no rule can be chosen after the outcomes it would judge). Every
program row E3 writes carries route "S2" and alpha_f "0.03" inside its hashed row, and the forward screen's shape
(`forward_db.FGS`: the statistic, the four checkpoints, the pass rule, the null worlds) is pinned in the store at its
creation (`fwd_kv` `fgs_prereg`, written once and never overwritten). E3 computes no forward verdict. A later release
may judge an E3-era row only by that shape, on the first checkpoint row written for it, at alpha 0.03; the larger
forward alpha (0.12) is open only to a lineage whose first registry row is written after that screen is pinned. The
share screen's 12% and the forward 3% stay inside the owner's 15% a program.

**A14 as coded** (the three pre-registered sentences are below, under "Pre-registered before the first equity
close"; `league/ops/forward_twins.py` `a14_reading`, read by the Done meter at each checkpoint that holds an equity
close):
- the gap: over the checkpoint's equity closes whose E1 twin is final and priced, the SIZE of the mean fill gap is at
  most 15 bp a side. It is read either way: fills better than the official-price model by more than 15 bp a side also
  read "not consistent" (a tightening, listed in the report's `tightened`);
- the intents: for each instance, over the sessions from its first decision through the session before its last
  counted exit, the live and the twin intents agree on at least 95%. A session a split makes unreadable, or one from
  the instance's retirement on (the book asks a retired program nothing), is left out; a session with no twin row is
  not agreed. A disagreement is counted with its cause (the bars differed, they were the same and the program
  differed, or the live decision's bars are not known), and it counts against the 95% whatever its cause. **A
  revived instance** (the book brings a retired instance back under the same key and clears its retirement): the
  retirement is kept in the forward store the night the book shows it, the sessions from it to the one before the
  instance ran again are left out as retired, and from there the instance is read against a twin started flat at
  that session (`twin_retired`, `twin_revived` events). A retirement and a revival that both fall between two
  nights the forward job did not run are seen by nobody;
- unmeasured, A14 does not hold and the checkpoint is not final. A checkpoint that held without A14 can only stop
  holding; none can start. The pinned Done rule is not edited.

**The twin is re-based after a difference, so a miss counts once** (release E3.1, deployed 22:51Z Oct 11, 2026; the
captain's A29, 20:13Z Oct 11;
registered before the first real share order and before any twin row existed; it amends how the intents half above
is COMPUTED, never its bounds: the 95%, the 15 bp, the keys and the pooling are as registered;
`league/ops/forward_twins.py` `live_seed`, `RebasedTwin`).
- **Why.** As registered, every session was compared with a twin run that never misses a fill. The rehearsal of
  the first real-money session measured that ONE missed buy of a program that buys only when flat leaves the live
  book a session behind that twin for good (about half its sessions differ from then on), and that one such program
  fails the pooled 95% bound for every program at the checkpoint. That counts one execution failure many times. The
  clause asks whether live execution matches replay; the number of sessions on which it did not is that measure.
- **The rule.** A session whose intent keys differ is counted as differing, exactly as registered (the same row,
  whatever its cause). THEN the twin's book is set to the live book as it stands after that session, and the
  sessions after it are compared from the same state. A re-based twin that differs again counts again and is
  re-based again.
- **The live book after a session** is read from `live.sqlite`, read-only: the instance's `eq_lots` rows opened on or
  before that session and not closed by it, each with the size its own buy asked (`eq_intents.share` or `usd`), and
  its `eq_intents` rows for the next session decided by then (the program's buys and sells, and the House's own
  planned exits: the maximum hold, a carried exit, a flatten queued by then). No status is read.
- **The re-based twin** is the engine's own account (the same fills at the official prices, the same sizing, fees,
  corporate actions and hold rules): each held lot is bought by the engine in its own entry session for the size its
  buy asked (the replay's lot on the Gym's sleeve: no dollar of the live account enters it), the planned intents are
  executed the next session with no miss, and from then on the program decides. Only the BOOK is set: the program is
  one instance asked every session in order, in the night's decider child. A lot the Gym cannot hold as the live
  book does is counted (`unheld` in the event) and not held: the next session then differs and counts.
- **What is written** (`forward.sqlite`, append-only as before): each session's row with two more columns, `rebased`
  (the re-bases behind the twin it was compared with) and `base_agree` (the same session against the UN-RE-BASED
  twin run, which is still made whole every night); one `twin_rebased` event a re-base (the lots it started from,
  as symbols, days and fill points, and counts). A store from before this release gains the two columns at its next
  writable open (`ALTER TABLE ... ADD COLUMN`: no row is rewritten; an older row reads no re-base and its own
  `agree` as the un-re-based answer). The twin's book is stored nowhere: it is recomputed each night from the rows,
  the live book and the store.
- **Rows written before this release** stand as written and are read by the same rule: the latest stored differing
  session re-bases the twin for the sessions not yet written (the twin goes through the stored sessions after it in
  order); an earlier one, whose next session was already written against the un-re-based twin, re-based nothing
  then and re-bases nothing now.
- **Unchanged.** Every program's un-re-based shadow (its forward record from registration, `fwd_days`) is written
  every night as before, and so is participation (`fwd_part`), which is read against the un-re-based twin run. A
  retired session is unreadable and re-bases nothing; a revived instance's new run starts flat. A session compared
  with a re-based twin has no split rule (its inputs are the engine account's own, which holds a lot's quantity as
  it was at each close); the split rule stands for sessions compared with the twin run.
- **Read it.** Beside each instance, never in a rule: `fills.rebase` of the forward report (and of the `dlane`
  report's `forward_record`) and `a14.rebase` of each Done checkpoint say how many times its twin was re-based and
  the un-re-based twin's own agreement over the same sessions (`rebases`, `sessions`, `agreed`, `share`), so a
  program whose live path has left its replay's days is seen, not hidden. The night's receipt counts `rebased`.
- **Its cost, as the captain stated it.** A program can run for weeks on other days than its unconditional replay
  and still read consistent after the one counted difference; the forward record beside it says so.
- **On the rehearsal's three 30-session paths** (the real book on a fake venue, the real forward stack): the buy
  fills, 28 of 28 and no re-base; Monday's buy missed, one differing session and one re-base, 28 of 29 (as
  registered: 15 of 29); a later rebuy missed once, the same (as registered: 21 of 29).

**The hidden year** (a loosening of the Train bar, reported in the report's `loosened`). A family born while
`elane.memory.mode` is "record" is given one of the seven Train years as its hidden year, by rotation inside its cell
(lane, mechanism, universe group) over the years its symbols can run (a symbol listed later takes none of the years
a stretch of which holds no bar of it; a family with no such year gets none); never 2020 or 2021. Its Train is one
run a SEEN span (each stretch of the other six
years its own run starting flat, exactly as A15 runs its two spans), and the bar, the record, the brief, the Train map
and the stored runs read those runs and nothing else. The hidden year's own run is made after the verdict is recorded
and goes to two sealed tables (`mem_contrib`, `mem_series`) that no generator reads, the family's own researcher
included. **It is made in a decider child of its own** (`elane_memory.hidden_runner`; log
`<state>/equity-hidden-decider.log`), started for one version's hidden runs and closed when they are in: a program's
memory outlives a run wherever its interpreter does, and the swarm's one evidence child runs the family's next
version's seen runs, so a hidden run made there could leave that version a mark of the year. (The same door stands
open between the Validation, look and Train runs that share the evidence child; that is release E1's and E2's to
close, and is said to their owners.) It is run as its own span because a filtered view of a whole-span run cannot hide a year: the sleeve's cash
carries the year's P&L into every later decision. What still reaches a seen run is the hidden year's BARS as
look-back in the stretch after it, as the reserve's do. **The cost:** a family born with a hidden year is judged on
six years, not seven, so more zero-edge versions pass Train and take a Validation try; the share screen's
false-positive rate per program is unchanged (Train is in-sample). A family born earlier keeps seven years.

**The stop rules** (`forward_register.py`). A failure never stops a program. A program stops at its session cap
(`elane.forward.stop_after_sessions` 500 stored sessions for a passer, a seed or a live program;
`stop_fail_after_sessions` 250 for a non-passer), or once its last three completed runs were each disqualified by
its own errors; a stopped program gets its checkpoint (the grid's own when it stopped on a grid count, as the
shipped caps are; a final one off the grid), so what it earned stays in the meters. A program whose run fails alone
on its last three attempted nights while other programs' runs complete is tagged suspect: it runs last and is
counted, never stopped. **The nights are the program's own:** a night the budget left it stale, a night the data
failed it and a night it was not due neither count nor break the run of nights (counted by the calendar, neither
rule could fire once the registry outgrew the night). A decider that cannot start fails the job at its preflight and marks nobody; a missing bar is the data's and
marks nobody; the next night's whole recompute fills the days. **To undo a stop** (the operator, on the box, with no
forward job running): `forward_register.resume(db, "<family>@<version>", why="...", at=time.time())` on
`forward_db.open_db("<state>")`. It writes a `resumed` tag and event; the nights and the stored days before it no
longer count, and the next night fills every day the stop left out.

**The switches** (policy.json ships all three at "record": an unrecorded forward day is lost for good and none of
the three touches money; `<state>/swarm.json` overrides them with no deploy, each read at its job's next run):
- `elane.forward.mode` "off": the forward jobs write `skipped` receipts, the report file says `mode` "off" and holds
  no forward part, and no FW alarm is raised (the report job still writes the memory counts, the probe's file, the
  release receipts and their alarms: RR, CP and MM have other switches or none). `forward.sqlite` stays (append-only
  evidence), and a recompute after the mode returns fills every missed day. **Stated cost:** while it is off no twin row is written, so A14 is unmeasured and no Done
  checkpoint holding an equity close can hold until the mode is back and one night has run.
- `elane.memory.mode` "off": no new hidden year, no ingest, no hidden run. **It does not reach a family already born
  with a hidden year:** that family keeps its seen spans whatever the mode, because its bar must not move under it. A
  defect in the seen spans for such a family is fixed by a DEPLOY, not a switch; until then its versions are a
  failure of the House's (nothing scored, no budget spent, E2's backoff moves the family out of the queue's head)
  and alarm MM1 says so.
- `elane.contam.mode` "off": no probe, and neither CP1 nor CP2 is raised.
- The other keys, each held inside its bound where it is read (`forward_db.BOUNDS`, `contam_probe.BOUNDS`):
  `elane.forward.controls_per_group` (50), `cpu_seconds_night` (1,800 s of child time a night; the rest are stale and
  go first the next night), `run_budget_seconds` (120), `neff_max_members` (1,500; its upper bound of 3,000 fits the
  report job's address space, measured under the job's own limit), `fill_minutes` and `twins` (true); `elane.contam.usd_run` (3.0), `every_days` (28), `batch` (20), `questions_per_cell` (120).

**Read it.** `<state>/forward-report.json` (operator-only, written after each night and 35 minutes before each open)
and the `forward_record` section of the `dlane` report; the funnel counts it apart (`forward_record`: integers only).
The lines: the forward funnel (programs registered by reason, program-sessions today and in all, stale, failed,
without data, suspect, checkpoints, the registry's chain); clean evidence-years (the effective number of independent
lineages a day over 252: compounding is a RISING daily increment, not a rising total); the replay multiple (simulated
program-years over independent evidence-years: a rising multiple means compute is outrunning information); any edge
anywhere (BH and BY at q 0.10 over the lineages, beside the controls' cost-free rate); and the fill gap (timing,
execution, the mean twin gap, participation, intent agreement). No per-program forward figure is shown for a program
without a live instance; no group difference is shown before its pair's own 60th, 120th and 250th usable session.
**The meter's floor:** BH, BY and the reading are shown once the family holds 5 lineages (the controls' side once it
holds 5 controls); under it the report shows the family's size and "too few lineages to read", and the funnel's `bh`
and `by` are 0 (over one or two lineages the count is a verdict on a program). **A day's meters wait for its rows:**
a day is written once no registered program owed it is still awaited for its row (a night the budget cut, a late
vendor bar), or after 3 later nights, then as it stands with a `meter_partial` event; the receipt says which day
waits and for how many programs, and FW5 reads no partial day. **Only an absence the next nights can fill is
awaited:** one that began that day (the program had its row the session before), whatever its cause, or one of
fewer than 3 sessions running of a program that is neither suspect nor behind in the queue. A standing absentee (a
holder of a halted symbol, which has no row until the bar comes; a program that hangs every night) is awaited at the
start of its absence, one or two days, and never again: the days after are written the night itself, are no partial
days, and FW5 reads them; FW2 goes on naming a program that fails night after night. When such a program returns,
the days it missed keep the meters written without it and carry no mark; its own rows are in the record. (Awaited
without end, one such program made every later day three sessions late and partial for good, and FW5 read nothing.) A control without its
row is awaited by the same rule when the night said its data failed.

**What nobody may read yet** (recorded in release E3, shown to no one: no generator, no report, and not the captain
either, who writes seeds and agendas and is therefore an author too):
- the group differences (passers against non-passers, looks passed against failed, each against the pooled
  controls) before a pair's own 60th, 120th and 250th usable session: `fwd_groups` holds the daily means, the report
  prints counts, and a read is one formula fixed before the means exist;
- every figure of the hidden year's out-of-fold tables (`mem_contrib`, `mem_series`): the report prints row counts;
- the forward P&L and the checkpoint t and p of every program without a live instance: the report prints aggregates
  and counts (a seated program's twins are shown, because Done's reading needs them);
- the probe's per-question outcomes, which it never stores (the provider's own store keeps each request and answer,
  on the House only).
Do not query `forward.sqlite` or the `mem_` tables by hand for any of these: a look taken before a read's own
session is a forking path, and the pre-registration above is what makes the later verdicts worth reading. Besides
ops and the Done meter, the one later reader of a per-program forward row is the forward seat rule of a later
release, at the alpha pinned in the row.

**The alarms** ride the `dlane` report's `alarms` (so the stall notice mails a warning) and each is a House alert of
the job that finds it; a text holds ids, counts and dates only. **Each alarm follows its own switch:** with
`elane.forward.mode` off none of FW1-FW9 is raised and no forward part of the report is written; with
`elane.contam.mode` off neither CP1 nor CP2 is; RR1, RR2 and MM1 have no switch. So with the forward record rolled
back the report job still writes the memory counts, the probe's file and the release receipts, and still raises RR,
CP and MM.

| Alarm | Level | Fires when |
|---|---|---|
| FW1 | warning | the mode is "record" and a forward day on which a registered program was owed a row has none by 09:00 ET the next session, or the report is over 36 h old (a stalled job). Silent on an empty registry |
| FW2 | warning | programs left stale two nights running, or a program with a data failure or a run failure on two nights running |
| FW3 | info, or warning | a `restated` event written last night, counted by cause. INFO when every restatement read bars that have moved since (the vendor restates a symbol's adjusted history at each ex-day, rounded to cents: routine, most weeks) or is a control's; WARNING when one read the same bars or cannot say which it read (the recompute itself moved) |
| FW4 | warning | the registry's hash chain does not verify. Owner step: stop the forward jobs and compare with the backup |
| FW5 | warning | the daily clean-evidence increment under its 20-day median for 10 forward days running while equity births continue (generators converging) |
| FW6 | warning | a live instance with 5 or more priced closes whose mean twin gap is beyond the A14 bound either way, or with 20 or more sessions under the A14 agreement bound |
| FW7 | warning | while an equity instance is live: the book's decide step failed for the last session, or ran more than 40 minutes after its close |
| FW8 | warning | the equity evidence identity moved while a lineage is live (the forward record opens a new engine series) |
| FW9 | warning | the ETF lane's twins, from the first session (Oct 15, 2026; FX1 and FX2 are the panel lane's). (a) An ETF instance has a session with no twin row. The sessions run from its first row (its first decision session while it has none) to the session before the one the last E3 night wrote: one night of grace, so a twin interrupted or deferred one night is told only if the next night does not write its row. A retirement it came back from is left out. A retired instance is read while A14 counts or will count one of its lots (one open, or closed since the Done count began), through the session before its last lot closed (`forward_twins._last_needed`); its own retirement's sessions are read, since the twin writes them as "retired" rows. The text counts the sessions and names the first missing one and the latest twin event (interrupted, run sha mismatch, unregistered). A14 counts each as not agreed for a checkpoint that reads this instance, and such a checkpoint is not final. An instance with no registry row is told here too. Silent while `elane.forward.twins` is false. (b) Each twin row whose intents disagree, with its cause, told in the reports of the 24 hours after its row is written (as FX2). FW6 still waits for 20 sessions |
| RR1 | warning | a declared release receipt unread 24 h after its window closed |
| RR2 | info | a release receipt read "flat" or "wrong_way" |
| CP1 | info | a configured model route with no COMPLETED probe for 45 days (for a route no probe ever finished on: since its first attempt, or since the first report that saw it configured), or a readable 2025 or 2026 cell newly "recalled" |
| CP2 | warning | a route whose last three probe attempts added no cell |
| MM1 | warning | the swarm reported a memory failure (a birth without its hidden year, an ingest that failed, a hidden year found void after a code rollback) in the last 24 h |

**Deploy** (an owner deploy of protected files; no order path changes; CI green on the exact head). The gateway
first, as for E2's five modules: its merge list gains the three swarm modules (a tightening only; no route, cap or
key changes). After it, verify
on the House, none of which blocks the build: (1) a decider child started from an ops job answers `ping` and runs the
canary (else `forward_shadow` fails at its preflight every night, FW1 says so and nothing is marked: the fix is a
deploy); (2) the gateway serves 1Min bars with `vw` for the universe 45 minutes after the close (else the fallback
price is used and `fwd_fillgap.field` says which); (3) the probe's router reaches the model routes from an ops child
(else CP2 fires at the third idle attempt); (4) the House's seconds a program-night, from the first three nights'
`fwd_runs`, to set `cpu_seconds_night`; (5) E2's scored versions a day, which set the registry's size; (6) the
probe's spend rows land in the swarm store under the equity lanes' key mark; (7) the swarm starts the hidden run's
own decider child beside its evidence child (`<state>/equity-hidden-decider.log` appears at the first scored version
of a hidden-year family; else each such version raises MM1 and leaves no out-of-fold row, and its verdict stands). **Roll back** by the switches above,
with what each does not reach. A CODE rollback (the previous release) leaves `forward.sqlite`, the fill minutes and
the memory tables where they are: nothing of the older release reads them, a family born with a hidden year is then
scored on E2's two whole spans again (its bar moves: prefer the switches), and when the release returns the shadow
fills every missed day; were an equity evidence module rolled back too, the engine label that returns opens a new
series (above). **A code rollback VOIDS the hidden year of every hidden-year family scored meanwhile:** the older
release judges such a family on all seven years, keeps the hidden year's row in the version's verdict and shows it in
the family's brief, so that family's researcher has seen the year. Nothing restores it. When release E3's code
returns, the family is judged on its seen spans as before, but `elane_memory.ingest` finds the year in its record and
writes no out-of-fold row for any later version of it (their `mem_seen` rows carry `hidden_year` NULL), with one
`swarm.status` alert a family (MM1); the out-of-fold rows written before the rollback stand. The deploy watch's own
rollback in a release's first ten minutes is such a rollback: after one, expect MM1 once for each family scored in
between. **Verified at the integration** (`league/tests/test_e3_end_to_end.py`, the real modules together on a
synthetic market and a synthetic live book): a Train scoring to a Done checkpoint through every job, the generators'
views byte for byte unchanged, and every job a skipped receipt that touches nothing with the three modes off.

## The equity lanes' births (release E2, Oct 2026): deployed 08:25Z Oct 11 (E2.2 11:44Z Oct 11)

E1 (the next section) gives the equity lanes their live path and three captain-seeded programs. E2 makes the swarm
breed share programs itself, for the BETA and EQUITY lanes: the architect's **equity pass** proposes families with their
first program, a minimal **equity researcher** revises each on Train alone, and the first version that passes the
Train bar **equity-v1** AND the **equity review** becomes its lineage's one Validation try. From there the family is
E1's: Validation, one sealed look by the pinned share screen **S2** (A11), then Probe. The design is
`league/swarm/ELANE_E2.md`; what went into E1's files is `league/swarm/ELANE_E2_PATCHES.md` (applied; a record).

**It is swarm-side only.** Nothing under `league/live/`, `league/gym/`, `league/equity/` or `league/constitution.py`
changes, so the options execution fingerprint, the equity evidence identity (A13) and the money digest are the ones E1
ships (read before the merge and after it; `league/tests/test_elane_e2_switch.py` holds that no E2 file is in any of
them). No evidence is reset, no grant re-ratifies. Train runs happen on the House in the swarm's own decider child
(A3: no Gym box, no data leaves the state dir), never on the live book's.

**Switch it on** (after E1 is live: `elane.mode` "gate", the daily store written, the seeds born). On the owner's
machine: `python3 set_swarm.py elane.birth_share=0.25 elane.e2.usd_day=8.0 --apply` (the captain's first values, A16).
Read on the next loop pass; no deploy. **The pace, said plainly:** the equity lanes' research spend (births, Train
research and the equity review together) is paced by TWO settings, and BOTH must be raised to give the lanes more:
`elane.e2.pace_share`, E2's hourly pace in lines of the researchers' Sail model line (shipped 0.25; held to 0-4 since
release E2.2, 0-0.5 before), and `elane.e2.usd_day`, its dollars a UTC day (shipped 8.0; held to 0-100). E2's day is
the smaller of `usd_day` and a day at its pace: at the ceiling's line ($0.3333 an hour) a share of 0.25 is $2.00 a day
whatever `usd_day` says, 1.0 is $8.00, 2.0 is $16.00, 4.0 is $32.00, each capped by `usd_day`. The captain sets them
with the settings tool, at switch-on or after it: `python3 set_swarm.py elane.e2.pace_share=<lines>
elane.e2.usd_day=<dollars> --apply` (for example `elane.e2.pace_share=2.0 elane.e2.usd_day=12.0`: up to $0.67 an hour
and $12 a day); left alone they are the shipped 0.25 and 8.0. Beyond the two, E2 stops a dollar before the line where
the Sail guard holds new research, so it never spends the options researchers' room or the day's cap (the details are
under **The budget** below). The release itself ships `elane.mode` "off" and `elane.birth_share` 0 in
policy.json, and with either one off NOTHING in E2 acts: neither round starts, no key is written, no event is made, no
model is asked (the test runs E1's real loop on the committed policy). The bounds are in code: `elane.birth_share` 0
to 0.5 (above reads 0.5; a value that is no number reads 0, so births stay off); `elane.e2.usd_day` 0 to 100 (outside
reads the default 8); every other `elane.e2` key has its own bound and a malformed value is its default.

**What it then does, on its own cadence:**
- The equity pass (`elane` round; every 2 h, every 30 min while fewer than 8 families are in Train research) asks ONE
  model route for the births that bring the equity lanes to `birth_share` of the last 24 h of births, 1 to 6 a pass,
  never past 24 families in Train research. **Equity births are counted apart from options births** (their own
  population): an options population at its ceiling stops no equity birth, an equity birth takes no options place, and
  the options birth quota, floor and stall alarms count the options lanes only.
- The equity researcher (`elane_train` round; every 10 min, 3 families a round) gives each family one step: score its
  newest version on Train, review a pass, ask its birth route for a program or a revision, or retire it (REFUTED on
  Train with a graveyard row in E2's own words, or STALLED when no version could be judged). A round starts only
  when it has work it can do now: none while every family is past its research, in a backoff, or needs a model E2
  may not ask.
- **How ctx is read (release E2.2).** The first programs the equity researcher wrote mostly read `ctx.bars[sym]` by
  key (`ctx.bars[sym]["close"]`) or as rows: every decide raised a TypeError, the version was disqualified and cost
  one of its family's four scored versions, and its author was told the error's class and line only. Now the contract
  (`league/equity/EQUITY.md`, "Reading ctx") says what each field of ctx is, with a worked program and the common
  faults, and one sentence and two lines of it are in the architect's lanes block and the researcher's system prompt.
  THE READING RULE runs first of the static rules below: a symbol's bars read by key, by position or as rows, a field
  ctx or the bars do not have, a lot read by attribute or by a key it lacks, `ctx.positions` read as a dict, and a
  returned intent with none or two of buy, sell and cancel (an empty dict for "no order" among them), an "at" that
  is no fill point, a buy with no size or a sell by a symbol are refused before the program is stored or run, each
  with its line and what to write instead. A refusal costs the question's model dollars and one of the family's 7
  write attempts, never one of its 4 scored versions. A version that is disqualified all the same (or was, before
  the rule) has, in its author's next brief, the line of its own file the first error was raised at and what is
  wrong there; the exception's own text stays on the House, as before (a program chooses it). Read a refusal in the
  swarm log (`elane_train:` lines, `refused`) or in the family's state (`elane_e2`, `refused`).
- **Three static rules refuse a program before it is stored or run**, each with its reason in the author's next
  brief: the Gym's code rules; the LEVEL rule (a price or volume level, or the ratio of two different symbols'
  prices, held against a constant or a PARAMS value) with RUN-START DEPENDENCE (the sleeve's own dollars of the run,
  `ctx.equity`, `ctx.cash`, `ctx.budget`, `ctx.caps`, a lot's `value`, `pnl` or `qty`, held against a constant, a
  PARAMS value or the run's anchor: a profit lock reads where a window starts, and the screen's false-positive line
  holds only for programs blind to that. The anchor is `ctx.budget`, `ctx.caps` or THE CAPITAL A LOT WAS BOUGHT WITH:
  a lot's `qty` times its `entry` or `exit`, its `value` less its `pnl`, `exit` times `qty` less `net`, and the
  sleeve's dollars written into a lot's `tag`; a program with no memory rebuilt the run's capital that way and was
  the profit lock again, and the restart check passed it. A lot's own return, however it is written, a count of
  sessions held and a size from `ctx.budget` are untouched); and the MEMORY rule (no object of `numpy` or `math` held as memory: it would
  outlive a restart and be shared by every program in the decider child).
- **What the static rule cannot see is the two paid readers' to refuse.** A lot's weight in the sleeve (its `value`
  over `ctx.equity`) and the sleeve's cash share are allowed against a constant, because a weight cap is an honest
  rule; set against the lot's own return, the same weight is the run's profit, and a program built on it locks its
  profit, keeps no memory, and passes the static rule and the restart check. The same holds for a value the pass
  cannot follow, and for the first equity a run saw kept in STATE (the restart check judges that one). The readers'
  rubric names the pattern and ends on the rule: a rule whose trading depends on how far the run is ahead or behind is
  refused, whatever its spelling (`league/swarm/ELANE_E2.md`, "What the static rule cannot see"). So a profit lock
  the two readers both miss reaches the screen, whose false-positive line does not hold for it: read a bred program's
  first live weeks with that in mind until E1's screen floor sees fresh starts.
- **Train is 2016-19 and 2022-24** (A15): seven years, two runs a stress, summed. **2020-21 is the reserve**: no E2
  run has a session in it and a result carrying a row of it is refused whole (alert `elane_train_window`). The
  loosening, stated: the bar reads seven years, not nine.
- The bar ends with **STATE, the restart check** (A15): the program is run again with its memory emptied 7 sessions
  into each span and every 20 after, and must end 99% of the sessions as the uninterrupted run does (the same orders,
  each buy the same size, the same count of failed decides), because the decider child restarts on every deploy. A
  check that cannot run or finish is the House's failure, never a pass: the version is not scored, and its third such
  failure is an alert, sent once (`elane_train_state`).
- **Nothing after Train reaches a generator** (A9 D3): no Validation or look outcome, no band, no retirement after the
  look. The equity generators read Train facts only, and no options generator reads an equity graveyard row.
- **The equity birth cells** (Oct 15, 2026; `elane_births.cells_text`): the equity pass's request lists every cell a
  refuted row of the equity graveyard binds (mechanism_class / lane:structure / holding, with a universe group where
  the graveyard keys one), each with its rows and the inputs each read, as the options architect's BIRTH CELLS have
  since F1 (Oct 3); a graveyard refusal is said in the next request with its cell, in the vocabulary's words only. The
  binding is unchanged (`cards.RebirthIndex.check` reads the card's declared cell and the cell its mechanism text reads
  as). Why: the request showed the refuted rows but never the cells they bind, so on Oct 11 most refusals were cards in
  cells the model was never shown.
- **The route by symbols** (Oct 15, 2026, L2; `elane_births.SYSTEM` and `route_text`). The architect's system prompt
  and lanes block used to say every program gets one Validation try, one sealed look, then real money. Under R-SEC
  that is true only of index-only programs. Now both say the route by symbols. A program on SPY, QQQ, IWM or DIA alone
  takes its lineage's one Validation try and one sealed look by S2, then waits for a Probe seat. A program naming any
  other symbol never takes a sealed try or look. Its only route to money is FWD1-R, on the sessions after it is
  registered: the first verdict comes after 5 forward sessions and is labelled WEAK. A panel program likewise (A34).
  The index set is R-SEC's own (`elane.forward_only` on `INDEX_ETFS`), never a copied list. Rules only: no count, no
  seat yield, no look outcome (A26, A9 D3). THE RATION now says "spent" where it said "looked at".
- **The same route in the rest of the request** (Oct 15, 2026, L2's review follow-up). The Train bar's last sentence
  (`elane_train.bar_text`) ends the lanes block and every family's Train brief. It now says the first passing version
  spends its lineage's one route by its symbols: the try and the look for an index-only program, FWD1-R for any
  other. The panel bar and panel block (`elane_xs.route_words`) say a panel program takes no sealed try and no XS1
  look under A34. THE RATION says what a look compares: a program that has taken its sealed look, or is taking it
  (`elane.same_lineage`). A forward-only lineage is spent by its Train pass and never looked at. The next request
  says a continuation refusal as "a lineage spent by rule". The admission's refusal text is unchanged, because
  `league/ops/elane_health.py` classes refusals by it.
- **The index-only ask** (Oct 15, 2026, L2; `EquityQuota.index_ask`). The quota lines ask that at least 1, and up to
  half (rounded down) of the pass's share-program places, be index-only families in cells no row binds and not
  CLOSED. The ask says where each list is: the birth cells block lists the bound cells, most rows first, and may leave
  some unlisted; THE EQUITY GRAVEYARD lists the CLOSED ones. That is 1 of 3 places at want 3 and 1 to 3 of 6 at want 6.
  With one place (want 1, the quota's floor when the equity lanes are at their share) it asks that place; it stays
  soft. Panel places are not counted. It is a soft ask: no place is reserved, and the admission and the quota are
  unchanged. The ask names
  the block in lower case, so "EQUITY BIRTH CELLS" in a request still means the block is there. Why: after the universe
  widened (03:43Z Oct 15) no pass bore an index family, and every equity birth of the day was forward-only. Watch:
  index births a pass over 24 h, index Train passes and S2 looks, and the seat plan's waiting list on Oct 21-23.
- **Owed:** deriving a card's holding bucket from its program's NEEDS `max_hold_sessions` (in `cards.validate`). It
  was proposed beside L2 and dropped: the verifier found the check mislabelled. Also owed: the researchers' system
  prompts (`elane_train.RESEARCHER_SYSTEM`, `elane_xs.RESEARCHER_SYSTEM`) still say every program takes one Validation
  try. The review rubrics say it too. They stay as L2 left them: a rubric edit changes what every review reads, and a
  panel review record names its rubric by its sha.

**The budget: E2's own pace, inside the House's Sail day.** E2's MODEL dollars (births, Train research and the equity
review together) are Sail research dollars inside the swarm's research budget and under THE GATE'S RESERVE like any
new research, never beside it. The budget rule gives the swarm one hourly line for Sail models
(`researcher.sail_usd_per_hour` after the budget's overlay: $0.3333 an hour, $8.00 a day, at the owner's ceiling;
$0.0667 an hour at the floor) and one Sail research day (the Sail guard's cap on what the swarm books on Sail in a UTC
day, models and Gym boxes together: $20 at the ceiling). E2 is counted apart from the options researchers and held by
three lines, read before each of its model calls. **Why the pace is E2's own (release E2.2):** it was a share of the
line, at most half, which at the ceiling is at most $0.17 an hour and $4 a day; the equity lanes stood still for most
of each hour at that pace while most of the day's Sail research dollars went unspent, because the line is only the
model share of a day planned around Gym boxes and an equity Train run needs no Gym box.
- **E2's hourly pace** is `elane.e2.pace_share` (0.25, held to 0-4) x that line: $0.0833 an hour at the ceiling and
  $0.0167 at the floor with the shipped share, $1.3333 and $0.2667 at four lines. Before each model call E2 reads
  what the swarm booked for its own request keys (`swarm:elane:...`) in the trailing hour, holds for unanswered calls
  included, and asks nothing at or over it.
- **E2's day** is `elane.e2.usd_day` and never more than a day at that pace: $2.00 at the ceiling and $0.40 at the
  floor with the shipped share, so the captain's first value `usd_day` 8.0 is a cap above it and the budget's taper
  tightens E2 with the line. Once the day is spent no equity question is asked until the next UTC day. To give E2
  more, raise BOTH (`python3 set_swarm.py elane.e2.pace_share=2.0 elane.e2.usd_day=12.0 --apply`); the smaller of
  `usd_day` and the share's day binds.
- **The House's Sail day** bounds the rest. E2 reads the Sail guard's own record and, fresh before each call, the
  swarm's booked Sail spend of the UTC day (models and Gym boxes). It asks nothing while the guard is braked, holds
  new research or has no good reading; nor once the day's spend is within a dollar of the line where the guard holds
  new research (its research cap less THE GATE'S RESERVE, and the day's even pace while `guard.pace_day`). So E2
  stops before the guard would hold anyone: the dollar that reaches the guard's line is never E2's, and the day's
  Sail total never passes the guard's cap on E2's account. At a high pace E2 uses the day up to that dollar, so busy
  options lanes reach the line themselves late in the UTC day and all new research waits for midnight (one to two
  and a half hours at four lines); at the floor budget E2 may ask nothing all day. In the log a step skipped for it reads
  "the House's Sail day ..." and the equity pass's line says `skipped` "sail_day" (beside "pace" and "usd_day").
  What follows, stated: early in a UTC day E2 has room once the day's due dollars exceed the day's spend by that
  dollar (at once at the ceiling; hours into the day at the floor), and over a day E2 takes what the options lanes
  leave of the day's even pace, no more.
- **The options researchers** keep at least half their line, whatever E2's pace: their hourly pace does not count
  E2's rows as their own spend (as it never counted the architect's), and what E2 spent in the hour, at most
  `min(pace_share, 0.5)` of the line, comes off their limit. With E2 idle they have the whole line; with E2 busy at
  the shipped share, three quarters; at a share of a half or more, one half. The heartbeat's
  `status.researcher_pace.equity` shows E2's spend and what it took; its `limit_usd_per_hour` is that half-line
  reading, which above a share of a half is NOT E2's own pace: read E2's pace in the `dlane` report's `equity_yield`
  (`usd_hour`, `line_share_usd_hour`, `day_line`). `allocation.plan_usd_per_hour`, when set, counts E2's dollars as
  research spend: with a plan set, E2 at a high pace contracts the researchers' workers toward the plan's floor (no
  plan is set by default).
Per family: at most 4 Train-scored versions and 7 write attempts. A question no route answered backs the family off
(20 minutes, doubling to six hours); a Sail call that timed out after it was sent is booked at its hold and no other
route is asked the same question. Train runs spend no model
dollar (House CPU: up to about 72 short daily-bar runs an hour). After a Train pass the costs are E1's (Validation and
the look on the House; real money only at Probe, inside the shared loss budget).

**Read it** (read-only, on the box):
- The swarm log: one `elane: {...}` line a pass (born, proposed, route, refusals) and one `elane_train: {...}` line a
  round (each family's step; `house` marks a failure of the House's with its retry).
- `swarm.sqlite`: events of kind `swarm.elane` (private) and `swarm.born` with `lane` "beta" or "equity"; kv
  `elane_e2_last` (the last pass's births and refusals), `elane_e2_births_at`, `elane_e2_train_at`; a family's state
  key `elane_e2` (its Train record: each version's verdict and fails, `status` researching, passed, refuted, stalled or
  closed).
- **The yield record**: the `dlane` report's `equity_yield` (kv `elane_yield`). One row a model route
  ("sail:<profile>"): requests, answers, failures, dollars (births, research), births, families, Train-scored, Train
  passes, and, for the operator only, Validation entries, looks, looks passed and live programs, each per dollar; the
  review's dollars are on rows of their own ("review:<route>"); `days` is the spend by UTC day against `usd_day`. The
  route for the next question is chosen from births, dollars and Train passes ONLY, never from a later stage (a choice
  made on look outcomes would feed the holdout back into which model writes programs).
- **Research dollars by lane** (Oct 15, 2026): the `dlane` report's `lane_yield` (league/ops/lane_yield.py). For 24 h
  and 7 days, each research group (`alpha`, `direction`, `equity_lanes`, `panel`): its booked dollars by route, the
  shared pools with the rule that divides each (`allocation`; the harness is said beside, never carried), the funnel's
  counts of the same window with the forward record's registrations and new lineages, `per_usd` and `usd_per`. An
  operator's reading: no generator, screen or route choice reads it.
- Alerts (House warnings through the swarm's status events, in the owner's `swarm_alerts` cause):
  `elane_train_window`, `elane_train_state`, and `elane_train_house` (the equity Train is not running: a version's
  third failure of the House's since it was last judged, the decider child failing every run or no equity store; at
  most once every six hours).
- **The owner's alarms and Done.** The options stall causes (births, population, Gym runs, Validations) and pre-open
  check 6 read the options lanes only; an equity family in a live band is check 10's, and an equity Validation never
  reads a stalled options pipeline as moving (`equity_validation_runs` and `equity_awaiting_ids` are beside). Done's
  item 7 ("births, Gym runs and Validations every UTC day") counts the options lanes; each day's `equity` row (births,
  Train runs, Validations) is reported beside it, never a bar. Counting the equity lanes in those three counts would
  be the owner's change of the pinned rule. The equity lanes' own stall causes are the next bullet; item 7's other
  half, "no owner step waiting", reads theirs like any cause's.
- **The equity lanes' own alarms (release E2.4, deployed 20:25Z Oct 11, the gateway first, then an owner deploy;
  `league/ops/elane_health.py`).** On Oct 11 the lanes' first hours went wrong four ways (most scored
  versions disqualified by one misreading of the contract, a births pass cut short, another refused whole for symbols
  outside the universe, the lanes starved at their pace) and no alarm fired: the captain found each by hand. The
  `stall` job now judges four equity causes at every run, read-only, and raises them like any cause: standing in
  `stall.json`, a House warning, the notice at the job's pace, cleared at the first run where it no longer holds.
  Each is judged only while the lanes are on (`elane.mode` "gate" and `elane.birth_share` above 0), the floor is not
  paused, E2's dollars are not set to zero (`elane.e2.usd_day` or `elane.e2.pace_share` at 0 is the lanes paused by
  setting) and the store holds an equity family or an equity pass at all; and only on evidence since THE RUNNING
  RELEASE first started, so a release that fixes a fault is not judged on what the generators did under the one
  before, and a restart of the same release (the watchdog's, a settings apply) resets nothing. The job keeps that
  start in `stall.json` (`elane`: `release`, the release directory the swarm's heartbeat names, and `since`, the start
  first seen under it) and, under it, what the four keep while that release runs and drop when it changes: `idle`
  (the idle clock), `held` (the last run that read E2 held), `dq` (when `elane_dq` first stood), `unread` (when
  unreadable lanes were last warned) and `broken` (the BROKEN kind `elane_idle` stands on, and since when).
  Otherwise the check reads "Not judged" and says why. **A "Not judged" that is
  no design is an error, and a House warning:** when the swarm's settings, one of E2's own readers, the store or the
  lane's own reading of whether it may ask a model cannot be read, the receipt's `errors` name the class at every
  run ("the equity lanes' readers could not be read (<class>): the four equity causes are not judged") and ONE House
  warning says it every 12 h while it lasts ("stall: the equity lanes' alarm cannot see: ..."). The receipt's
  `warning` flag alone reaches no one: the job's runner does not alert on it. How to read each, and what to do:
  - `elane_dq`: more than half of the versions scored in the last 6 h (6 at least) could not be judged for a fault of
    their own program: disqualified by its errors or timeouts, refused at load, or failed by the decider child, in at
    least two families (one family's bad programs are no fault of the contract: the check reads clear and names the
    family). No mechanism was judged in them. When fewer than 6 fall in the 6 h it judges the last 6 scored since the
    running release started (inside 12 h); and it stands early, before the sixth version, once 4 of two families
    could not be judged (they are most of six whatever comes). **Once it stood under a release it HOLDS** until
    versions scored after it stood are judged by the bar in two families (the generators write programs that run),
    or the release changes: it no longer clears as its window slides past a fault nothing fixed, or when one
    family's bar fails sit beside the retired families' versions and read "half". While it holds for that alone its
    sentence says since when and how many families the bar has judged since (`standing_since`,
    `bar_families_since`). It names the first error's class (TypeError, KeyError, a malformed intent...) only when
    one class is more than half of the disqualifications, else the classes that tie; and, for a class it names, the
    reading rule's commonest sentence for it, or, with none on record, what that class most often is. **Your
    step:** the text the generators read is wrong or silent about it: fix `league/equity/EQUITY.md` "Reading ctx"
    and `elane_review.READING_CTX`, or make a static rule refuse the shape, in a release (Oct 11's was release
    E2.2).
  - `elane_births`: the last 3 equity passes that asked a model bore no family. It says how (every proposal refused,
    none proposed, the answer cut short, no route answered, the pass raised), the commonest refusals in the House's
    own closed words, and the symbols the code knows that `elane.universe` does not hold. Nothing to do for 6 h:
    each pass tells the next its refusals. **After 6 h with no equity birth, your step when a setting clears it:**
    widening `elane.universe` or `elane.structures` is your decision (closed cells and lineages with their try
    bind by design); answers cut short want a higher `elane.e2.births_max_output_tokens` (at most the model
    provider's own output limit, which the step names) or a lower `elane.e2.max_per_pass`; a pass that raises needs
    a release. **At once, your step** when every route refused the request before it was sent for a setting (the
    pass's event names the `elane.e2` key: an output limit above the provider's, an effort or a Sail profile the
    provider does not know): asking again changes nothing until the setting does. Cards refused, an empty answer or
    a route that did not answer stay information.
  - `elane_idle`: **A BROKEN LANE, and only that** (the captain's rulings of Oct 11 on the second and the third
    independent checks). BROKEN is judged first, by the lane's own record, two ways.
    **By its answers, at any time.** Of the PROGRAM QUESTIONS the Train rounds asked a model in the last 6 h (8 at
    least; with fewer in the 6 h, the last 8 asked since the running release started, inside 12 h; before the
    eighth, once 5 are lost: they are most of eight whatever is still to be asked), more than half were LOST TO A
    FAULT: the answer E2 paid for held no program (the round's own words, "the answer held no program": a
    programless, an unreadable and a cut-short answer are all that refusal), or no route answered the question.
    (A stop before any version was judged, the same program sent again and a program a rule refuses are answers
    the lane could read and the generator's own, each in its author's next brief: none is lost to a fault.)
    That is work lost to a fault, never to a setting and never to a rule, and the lane need not be idle for it: a
    lane that still scores a version now and then while most of what it pays for holds no program stands too. A
    question no route answered counts only once no route has answered a program question for 3 h WHILE THE LANES
    KEPT ASKING: the questions none answered since the last one a route did answer, once the first of them is 3 h
    old (less the time the swarm was down) and they span an hour and a half. A route's bad hour heals by itself (the
    question is asked again after its backoff), and a bad quarter of an hour that a hold of E2's followed is not
    three hours unanswered. **Your step** names the routes, each one of `elane.e2.routes` as the swarm loads them
    (any other is "another route" in the sentence and unnamed in the step): for answers with no program, raise
    `elane.e2.train_max_output_tokens` if they are cut short, or take a route out of `elane.e2.routes`; for
    questions none answered, check the routes at the model provider or name routes that answer; else it needs a
    fix, in a release. Before the third check such a lane read "STARVED BY A SETTING, not broken" under any hold,
    pointed to `elane_refused` (which said none was refused) and was never mailed.
    **By its failures, once it is idle.** Work is owed (families in Train research, or births wanted), no version
    was scored for 3 h, and the record since shows two rounds that raised, two Train steps that failed on the
    House's side (or a family waiting out a House backoff after two failures), or two steps that failed with an
    error of their own. **Your step** when its rounds raise (the swarm log's "elane failed" and "elane_train
    failed" lines), when its Train runs fail on the House's side (the `equity_data` job's receipt, the swarm's
    `equity-decider.log`), or when its steps fail with errors (the swarm log's `elane_train` lines).
    Either way it stands WHATEVER E2's own lines hold, with that kind's step, and a second sentence says the line
    when E2 is also held ("BROKEN, whatever E2's own lines hold: ... E2 is also held now: ..."): a lane whose every
    Train run fails, or whose every answer holds no program, scores nothing at any pace.
    **Once it stood under a release it HOLDS** (`stall.json` `elane.broken`: the kind, since when, and for the
    answers the routes it named) until a version is scored after it stood, the release changes or no work is owed.
    While it stands on that alone its sentence says so ("it stood at ... and HOLDS until a version is scored or
    the release changes", with what the hours read show now; `standing_since`, `kept_standing`). Before, a hold of
    E2's that outlasted the 12 h of events the check reads turned a lane nothing had fixed into "STARVED BY A
    SETTING, not broken": in the third check's replay a lane whose Train runs all failed lost its step for 21 hours
    of a day under the Sail guard, and the reminder stopped.
    **Why this cause and not `elane_refused`** (the ruling left the choice to what reads truest to an operator): a
    lane that pays for answers and gets no program cannot do its work, which is what BROKEN says and what its step
    is for (the routes, the output setting). `elane_refused` says the generators write programs ONE RULE refuses
    and asks for that rule to be taught, and the gateway words it "by one rule": no rule refused an answer that
    held no program, and a question no route answered wrote none.
    Else, idle, it stands only when the lane MAY ASK A MODEL and still scores nothing: no hold of E2's was seen
    for those 3 h (not now, not at an earlier run of the job, no Train step or equity pass skipped for want of
    model dollars). **Your step** when no round starts or judges anything (the swarm log's `elane_train` lines);
    questions no route answered and answers with no program that are too few to be most are told and are nobody's
    step, programs refused before a run are `elane_refused`'s, and with no family left and barren passes it points
    at `elane_births`.
    **STARVATION BY A SETTING IS NO STANDING CAUSE.** A lane held by its own hourly pace, its day's dollars or the
    House's Sail day is the budget you chose, at work: the check reads judged, clear, never stands, raises no House
    warning and is never mailed, for an hour or for a whole day. What the setting costs is SAID, in the check's
    sentence and numbers at every run (the receipt and the report): the Train steps due in the last 3 h, taken and
    skipped by reason (`steps_due`, `steps_taken`, `steps_skipped`, `skipped_pace`, `skipped_usd_day`,
    `skipped_sail_day`), whether E2 is held now and by which line (`held_now`), whether a hold was seen in the 3 h
    (`held_lately`), the idle hours (`idle_hours`; `starved` true once they pass 3 on a held lane), and the lever:
    the hourly pace (`elane.e2.pace_share`), or the day's line, which is `elane.e2.usd_day` only when that is under
    24 hours at the hourly pace (at the release's settings it is not, and the lever is the pace again); where the
    budget is at its floor (no usable `budget.json`) it says the budget's line binds before the share, before the
    command (`python3 set_swarm.py elane.e2.pace_share=<lines> --apply`). The research funnel carries the same counts for
    the day and the release (`train_steps`; the passes' `skipped`). **The cost of this ruling: a lane starved by a
    setting is seen in the funnel and the receipt, not in the mail.** Read `train_steps` in the `scoreboard` job's
    receipt when you set a pace: nothing will mail what it costs. And while a hold was seen in the 3 h only what
    the record proves broken stands: programs refused before a run, one failure of a kind, rounds that judge
    nothing, and questions no route answered or answers with no program that are too few to be most are said in
    the held lane's sentence ("Since the lanes went idle ...") and its numbers, and stand on nothing there. A held
    lane with program questions lost says how many and how many it takes (`questions_lost`, `questions_asked`;
    "it stands BROKEN once they are 5 and more than half of those asked"), and does not say "not broken". The
    funnel counts every one (`answers`: `by_rule.no_program`, `unanswered`).
    The idle clock is kept per release (`stall.json` `elane.idle`): from the later of the last version scored and
    when the work became owed, less the time the swarm was down (at a restart, from the heartbeat the last run read
    to the new start), so a broken lane that is restarted every two hours is still judged idle; its hours say "at
    least" unless they start at a version scored. Not judged while the swarm itself is not running (its heartbeat
    ten minutes old), nor while the time taken off for restarts leaves under 3 h of running time (the check then
    says how much was taken off).
  - `elane_refused`: more than half of the programs the generators wrote in the last 6 h (8 at least) were refused
    before a run by ONE static rule (the reading, level or memory rule, the code rules, NEEDS). It names the rule
    and its commonest sentence. As `elane_dq`: when fewer than 8 fall in the 6 h (a slow lane writes one program an
    hour) it judges the last 8 written since the running release started (inside 12 h), and it stands early once 5
    were refused by one rule (most of eight whatever is still to be written). **Your step:** the generators are not
    being taught that rule: teach it where they read it (the contract, the researcher's system prompt,
    `elane_review.READING_CTX`), in a release.

  **In the mail** each of the four is an entry of its own, under its own words (the gateway's, since its deploy
  before this release: "most equity versions could not be judged", "the equity passes bear no family", "the equity
  lanes are idle or starved", "most equity programs refused before a run by one rule") and keyed by its own name:
  an equity owner step is mailed at once whatever the swarm's own alerts told, and theirs whatever these told.
  (The gateway's words for `elane_idle` still say "idle or starved"; the gateway is not changed again for the
  ruling, and a lane starved by a setting no longer reaches the mail under them.)
  Nothing rides "the swarm raised alerts". An entry is the cause's sentence (its leading sentences whole inside the
  mail's 400 characters; the receipt has all of it), its figures (the telling ones first; E2's dollar figures are in
  the sentence, to the tenth of a cent, never among the mail's two-place numbers), what the floor is doing and your
  step. **A House warning keeps your step whole:** where a cause's sentence, what the floor does and the step pass
  the warning's 900 characters, what is shortened is what comes before the step.

  **Read them** with no exec (`python3 scripts/desk_receipts.py`): the `stall` job's receipt holds the four among
  its `checks`, each as it holds every cause (`stalled`, `what`, `numbers`, `doing`, `owner_step`); a check's
  `numbers` say whether it was judged (`judged`), on what (`basis`), for `elane_dq` and `elane_refused` give
  `examples` (the families, versions, lines and classes), and for `elane_dq` the contract's own sentence for the
  class named (`hint`). The research funnel is in the `scoreboard` job's daily receipt, key
  `equity` (`day` and `since_release`, each with `research`: equity passes asked, barren and cut short, proposals
  refused by reason class, programs refused before a run by rule, the Train rounds' steps taken and skipped by
  reason (`train_steps`: `pace`, `usd_day`, `sail_day`, `other`), versions scored, disqualified and failed by
  code, bar passes, review refusals and passes, families retired, E2's model dollars by purpose). On the box,
  read-only: `python3 -m league.ops.elane_health --state /workspace/state [--hours N] [--json]` prints the checks,
  the funnel of the last N hours and each family's versions (fail codes, a disqualification's class and line) and
  refusals (the rule and its sentence in closed words). No text a program or a model wrote is repeated in the
  mail, the House's warning or a standing check's sentences: not an exception's text, not a program's source, not a
  refused proposal's name, not a symbol a model made up. (A check's `examples` and the report name families by
  their ids, and so does the sentence of an `elane_dq` that reads clear for one family.)

  **What the architect is shown of a barren pass** (`league/swarm/elane_births.py` `last_text`), in closed words:
  each refusal by its class, in the House's one sentence for the class with the House's own values (the structures
  and universe the settings open, the agenda's keys, a card's field names, the symbols of the code's own universe
  that are not open and a count of any others), and the proposal by its PLACE in the last answer (with its lane and
  agenda key when it named valid ones). Never a lane, structure, agenda or symbol as the model spelled it, never its
  card's text and never its slug: the House's slug rule keeps a model's words (hyphenated, cut at 36 characters), so
  a slug can carry a sentence to the next reader, who may be another route's model. The House's own record of the
  pass (kv `elane_e2_last`, the `swarm.elane` event) keeps the slugs and reasons, for the operator and this alarm.
  And one sentence after THE AGENDA, while `elane.universe` holds no sector ETF: where a mechanism speaks of sector
  ETFs, read THE UNIVERSE's own symbols. (The contract in the system prompt, `league/equity/EQUITY.md`, still lists
  every symbol the code knows; the request's universe line says only its own are open.)

  **Settings.** The release adds none to `swarm.json` and changes none: the thresholds are constants in
  `league/ops/elane_health.py`, each with its reason. One switch is the owner's, in `ops.json`:
  `{"stall": {"elane": false}}` stops the four from being judged and leaves the rest of the stall alarm as it is
  (`jobs.stall.enabled` false still stops the whole job). The settings its steps name exist already and stay the
  captain's: `elane.mode`, `elane.birth_share`, `elane.universe`, `elane.structures`, `elane.e2.pace_share`,
  `elane.e2.usd_day`, `elane.e2.births_max_output_tokens`, `elane.e2.max_per_pass`, `elane.e2.refuted_cell_cap`,
  `elane.e2.train_max_output_tokens`, `elane.e2.routes`.
  **One bound is tighter:** `elane.e2.births_max_output_tokens` and `elane.e2.train_max_output_tokens` are held to
  the model provider's own output limit (`ltcm/provider.py` `MAX_OUTPUT_TOKENS`, read from it; they were bounded at
  64,000, above what the provider takes, and on Oct 11 a setting inside that bound failed every route of one births
  pass). A value above the limit reads as the code's default (24,000 and 12,000), as any value outside a bound
  does: check `swarm.json` for either before the deploy.
  What else changes at the deploy with no setting: the four causes are judged and told; Done's item 7 counts an
  equity owner step waiting; the funnel carries `equity.research` and the `scoreboard` job's receipt the funnel's
  equity block; `stall.json` gains `elane`; the equity architect's request names the
  costs of the universe's own symbols only and says a proposal naming any other is refused whole (it named "the
  other ETFs", TLT and GLD whatever the universe held, and a pass then proposed sector ETFs the admission
  refused), and tells the last pass's refusals in closed words. It reads, reports and notifies: no screen, bar,
  budget, seat, money rule, graveyard or refusal rule changes, and the three identities do not move.

  **Deploy order: the gateway first.** `gateway/lib/email.mjs` `STALL_CAUSES` words the four causes (the release's
  one change under `gateway/`). A notice that names a cause the gateway does not word is refused whole (a 400:
  nothing of that notice is mailed, the receipt's `errors` say "stall notice not sent" at every run, and the
  House's warnings and `stall.json` go on), so the House release follows the gateway's deploy, never the other way.
  The same holds for a gateway rollback past it while this release runs.

**Stop it**, from the lightest (each read on the next loop pass, no deploy):
1. `elane.birth_share=0`: no more births. The families already born finish their Train research, and one that passed
   Train and the review still takes its Validation try and its look in E1's rounds.
2. `elane.e2.usd_day=0` with it: no model is asked at all (no program written, no review).
3. `elane.mode=off`: everything E2 does stops. It is E1's swarm-side rollback too (no seeded birth, no Validation, no
   look). It is not the money switch: a program already at Probe trades on by its band until `equity_money.enabled`
   is false (E1's **Roll back** below).

**Deploy class.** An owner deploy with or after E1 (`league/swarm/policy.json`, `league/ops/`, `league/swarm/store.py`,
`tournament.py`, `game.py` and `league/ci.py` are FORBIDDEN to the updater). E2's five modules
(`league/swarm/elane_births.py`, `elane_train.py`, `elane_yield.py`, `elane_seal.py`, `elane_review.py`) are FORBIDDEN
from this release on: no role changes them and the updater never self-deploys them. **One follow-up at the gateway**,
made Oct 11, 2026: its merge list (`gateway/lib/protected.mjs` MERGE_FORBIDDEN) names the five, and they are in
`league/ci.py` `FORBIDDEN`'s own list (`PENDING_GATEWAY`, where they waited, is empty).

**Verify after the deploy** (read-only): `policy.json` on the box has the `elane.e2` block and `elane.birth_share` 0;
before the switch the swarm log has no `elane:` or `elane_train:` line and `swarm.sqlite` no `swarm.elane` event; the
three identities are E1's. After the switch: an `elane:` line within the first loop passes, `swarm.born` events with an
equity lane, `elane_train:` lines while a family has a step to take, the heartbeat's `researcher_pace.equity`, and the
`dlane` report's `equity_yield` with a row for the route that answered and its `day_line` and `usd_hour`.

**Not handled, stated.** E2's rounds start only while the Sail guard allows new research (THE GATE'S RESERVE and
the brake hold them, as they hold every round that makes new research); the options Gym being down holds neither, since
an equity Train run needs no Gym box. The restart check
does not catch memory that changes fewer than 1% of sessions. The static rules do not follow a tuple or a dict stored
whole, a container read in another function than it was filled in, or a level's digits (the two paid readers do), and the memory rule covers the programs the swarm breeds, not the seeds or
the options Gym's programs (the root is E1's, for its next identity move). **The reserve's bars reach Train as look-back**: no
2020-21 session is run or scored, but a 2022-24 run reads its NEEDS `history` + 1 sessions before 2022-01-03 (up to
505), so a program with look-back has 2022-24 Train figures that are functions of 2020-21 bars, and even a program
with no look-back reads the last 2021 session; sealing those bars too would
be a change in E1's runner or store, the captain's call when the reserve's accessor is built. Post-earnings drift is
named in the agenda and refused until earnings data exist.

## The equity lane (release E1, Oct 2026): deployed 07:18Z Oct 11

The owner's goal of Oct 10, 2026, on the House's side: agent programs trade long-only ETFs (stocks later, E3) with real
money through the House's own **EquityBook** (`league/equity/live.py`; its tables `eq_lots`, `eq_orders`, `eq_fills`,
`eq_intents`, `eq_bars`, `eq_activities`, `eq_exports`, `eq_instances` in `live.sqlite`). The lane's code is
`league/equity/` (its own identity, `equity_fingerprint`: an equity change never resets the options evidence; see **The
equity identity** below for what moves it), its swarm
side `league/swarm/elane.py`, its contract `league/equity/INTERFACES.md` and `league/equity/EQUITY.md`. E1 deploys with
`equity_money.enabled` TRUE (the captain's A10.2: the switch ships on), `elane.mode` "off" (the captain sets "gate" with
set_swarm.py once the deploy is verified) and the S2 screen's receipt pinned for both lanes (A11); nothing trades until
a program passes its sealed look AND the stock paper proof's BUY stage passes. In E1 the
lane's programs are the three captain-seeded BETA programs (`seed-overnight-qqq`, `seed-reversal-index`,
`seed-overnight-spy`, in the order their looks are taken: agent-written, judged by the swarm's screen like any family,
and said plainly to be seeded);
architect and researcher births in the beta and equity lanes are E2.

**The equity rounds run on their own** (A3: an equity Validation or look runs on the House in the decider child; no Gym
box, no model dollar). While `elane.mode` is "gate" the swarm's main loop births the seeds each pass and starts the
equity rounds on a thread of their own every 5 minutes (`league/swarm/loop.py` `equity_rounds`, `elane.ROUND_SECONDS`):
the tournament's equity step (Validation, the retirements), then the gate's (the one sealed look), so a version
validated in a round takes its look in the same round. **Neither the research budget's brake nor a Gym that is down or
switched off holds them**, and no options round carries them: an options Validation that fails or runs long costs an
equity family nothing. They need only the swarm process running (`enabled` in swarm.json) and `elane.mode` "gate". The
heartbeat's `status.equity` shows the mode and when the last equity round started; the swarm's log has one `equity:`
line a round (who was validated, who was looked at). **A Validation the House could not make is not a failed
pre-check**: `validated` {family: entered} holds real verdicts only (`false` there is a FAILED pre-check, and the
lineage's one try is spent), while a Validation that could not be made (the evidence child could not start, or a run
that ended with no data: nothing is recorded, no try is spent, and it is asked again next round) or that was refused
is named under `validation_errors` {family: the error}, in that line and, until the next round, in the heartbeat's
`status.equity`. Read `equity-decider.log` on the box when one stays there.

**The order of the looks** is the seed list's DECLARED order (`league/swarm/seeds.py` `EQUITY_SEEDS`,
`elane.round_order`): `seed-overnight-qqq, seed-reversal-index, seed-overnight-spy`. It is a decision (the captain's,
Oct 11, 2026, before any Validation or look, from Train-era figures only: amendment A18), because it matters under D3:
of two programs of one lineage (Train daily returns correlating at 0.7 or more, or the same template) the later one
is refused with no look. **The two overnight seeds share a template and are one lineage**, so only one of them is
ever looked at. `seed-overnight-qqq` goes first by that decision; `seed-reversal-index`, a lineage of its own, follows;
`seed-overnight-spy` is last and, once `seed-overnight-qqq` has been looked at (passed OR failed: the lineage's look
is spent either way), it is refused its look as the same lineage and retired with that cause said
(`elane.SAME_LINEAGE`), plainly reported. **The consequence to know: SPY's overnight seed, the one that buys at every
close, is not expected to trade.** `seed-overnight-qqq` buys at a close only after a down close of QQQ, and
`seed-reversal-index` only after a close at least theta below the prior one, so a session with no such close has no
equity buy. Two rules hold the order (`league/swarm/elane.py`):
- `round_order`: both equity rounds walk the seeds as one block in the declared order, whatever second each was born
  in (the store's own order is by the second of birth and then the id: the alphabet's, or a clock tick's);
- `seed_wait`, **strict within a lineage, with no timeout** (amendment A18): each seed's `lineage` in the list
  declares the lineage it is in (the two overnight seeds are one; the reversal seed is its own). A seed's look is
  never taken while a seed declared before it in the same lineage is alive without a verdict: it waits until that
  earlier seed has been looked at (D3 then refuses the later one), has FAILED its Validation pre-check with no retry
  owed, or is retired. So a look the House owes again (a run it could not make, a turn that raised), a slow data job
  or a hold never hands the lineage's one look to the later seed. The wait spends nothing and shows in the round's
  `waits` and in the family's `gate` word. It is asked at the look's last step before the sealed run, so its clock
  counts only the rounds in which the later seed's own look was otherwise ready. After 30 counted minutes
  (`SEED_WAIT_SECONDS`) ONE House warning (`equity_seed_waits`) names both seeds and why the earlier one has no
  verdict yet; it is said again at most daily while the wait lasts, and cleared when the wait ends
  (`equity_seed_wait_over`). **The warning is no timeout: the later seed keeps waiting. The operator's hold on the
  earlier seed (`gate_hold`) holds the later seed of its lineage too; to give the lineage's look to the later seed,
  retire the earlier one.** Seeds of different lineages never wait on each other (`seed-reversal-index` waits for
  nobody, and nobody for it), a family that is no seed waits for none, and a seed whose order cannot be read is not
  looked at that round (nothing spent).
A program refused at the gate before its look retires with its cause said (`elane.SAME_LINEAGE`,
`elane.FLOOR_INELIGIBLE`), not as a spent Validation try. After the first look, read the refusal rows on the box to
confirm that SPY's seed was refused as QQQ's lineage (the figure stays on the House).

**What a look does with a run that went wrong** (`league/swarm/elane.py` `look`):
- a holdout run its own errors ended ("disqualified") is a look SPENT AND FAILED, never judged on its partial series;
- a Train-era run that ended "disqualified" refuses the program at the floor (no look spent);
- a look the House could not make (the capability, the store, the NEEDS call, a child that could not be started or
  did not take the request, an answer that is not a result, no data) is no look and is owed again, however often: it
  counts against no program (each try is a `look_failed` gate event naming the stage);
- a sealed run the child TOOK and did not answer (it ran past its 20-minute budget, or it exited, while the program
  held its holdout) is owed once more, then the look is spent and failed. Each time is a House warning ("the sealed
  equity look of ... was sent and did not return"): read `<state>/equity-decider.log`. The evidence child's hash seed
  is pinned, so the run owed again is the same run.
- a validated version whose recorded run no longer reproduces (the data job wrote the next day, or the equity identity
  moved) is validated again in the next round, the same try, whichever version the family's candidate is by then.

**The switches** (all three must be on for a real equity open; any one off stops new opens):
- `equity_money.enabled` (league/constitution.py, a CON change: the money digest moves and the standing grant re-ratifies
  at the House's start). E1 shipped True on Oct 11 (money digest `7e41909a` at A20's design, three seats at a sleeve
  of 0.50 x E; the digest of the seats and the sleeve in force is in **The seats and the sleeve** below); False
  (`23f17a14` at A20's design) is the stop: the book keeps its tables, runs its exits and reconciles; no equity open.
- `elane.mode` (league/swarm/policy.json, swarm.json over it): "off" (the rollback: no seeded birth, no equity look) or
  "gate".
- `STOCK_BUYS_REAL` (gateway/wrangler.jsonc): deployed "on" with PR #532; while the House's `equity_money.enabled` is
  false nothing sends a buy, so the House's switch is the one that matters. "off" closes the gateway's route (closes go
  either way).
- The screen: **S2 is the gate** (the captain's A11; `league/equity/screen.py` `floor_s2`, `verdict_s2`). Its receipt,
  the study's, is copied verbatim to `docs/benchmarks/equity_screen_2.json` (sha256 `45634dfc...`) and pinned for BOTH
  lanes in policy.json's `elane.screens` (`"screen": "S2"`, `c_R` 0.0, `c_H_floor` 0.95, `c_H_margin` 0.05, `c_X` 0.85,
  `fp_cap` 0.12); with no pinned receipt every equity look is refused (no look spent), and a receipt file at hand
  whose bytes are not the pinned sha256 refuses the screen too (`elane._receipt`; the file never reaches the box, where
  CI's pin of the exact commit stands for it). The rule, per program:
  - Validation's pre-check (calendar 2025, 250 sessions): 20 round trips or 120 invested days, and a P&L above zero.
  - The one sealed look passes when the holdout's P&L is above zero AND its holdout-only daily t is at least c_H,used.
    **c_R is 0**: the pooled t over Validation and the holdout is reported and is never a bar.
  - c_H,used = max(**0.95** (the receipt's floor), c_pF1 + **0.05** (its margin)) on the 0.01 grid. c_pF1 is the
    program's OWN 12% point of the holdout-only t, counted exactly (no seeds) over every placement of a 250-session
    Validation and a 194- or 251-session holdout that share no session, on the program's own 2016-19 and 2022-24
    series. A program with too little of that history, or a c_H,used above 5.00, cannot be looked at (refused before
    the look; nothing spent).
  - **The look cap is 2026-10-09** (A12): every look reads 2026-01-02 through 2026-10-09, exactly the 194 holdout
    sessions the receipt is calibrated on; later days are forward days only. The look waits while the daily store ends
    before the cap (a shorter holdout would fail the verdict's windows and spend the look).
  - Measured (the receipt): the false-positive rate at zero edge is **at most 7.51% over the 336 cells the study
    measured** (5.06% on the archetypes' calibration cells), none above the 12% cap, under the owner's 15% wall.
  - **The stated cost: S2 lets more zero-edge programs pass than S1+F1 did** (1.3 to 7.3 times as many on the study's
    worlds), so a pass under S2 is weaker evidence of edge; the live record and the pre-registered demotion rule (EDM1)
    carry that. In exchange it finds a real edge more often (at +10% a year the study's first archetype passes 18.55%
    of the time against 12.45%).
  - Beside every live trade: the receipt's line with the program's own figures from its own floor (its FP at zero edge,
    its holdout-only rate at c_H,used, its drift-kept pass rate), the S1-X label (alpha or beta, with its FP from an S1
    floor of the same series) and the contamination sentence.
  S1+F1 (A9; receipt `docs/benchmarks/equity_screen_1.json`, the pooled-t bar c_R 1.49) stays in code and in the
  repository as receipt 1's screen. No lane pins it; a pin back to it would be a reviewed policy.json change.
- The stock paper proof, STAGED (A8.7 as amended by A10.1; `league/live/paper.py` `StockPaperProof`, run by the equity
  book in its own OPEN window): stage BUY (kv `paper_proof_stock_buy`) buys a fractional SPY marketable limit on
  `alpaca-paper` from 09:30:30 ET to the 09:45 entry cut-off and passes on its fill, its lot row and the reconciled
  position: it gates every REAL equity BUY, with no end. Stage SELL (kv `paper_proof_stock_sell`) sells that lot in
  the next session's open window, first (real exits wait for it), and passes on the whole sale, the FILL activities
  and the position back at its baseline: it gates every REAL equity SALE, **and that wait has an end (the captain's
  A28, registered before the first real share order; release E3.1, deployed 22:51Z Oct 11, 2026): the session's
  entry cut-off, the open + 900 s (09:45 ET), the
  minute the book stops trying open entries.** The practice sale is sent in the window's first minute and normally
  witnessed in its second, so a real exit normally waits one minute. From the cut-off on EVERY exit goes through the
  normal path whatever the stage says: a program's own sale, the maximum-hold exit, a demoted or retired program's
  lots, a carried exit, the owner's flatten, and a close-window sale (its window, the close - 300 s, is past the
  cut-off by construction, on a half day too: it never waits on the stage). The normal path is unchanged: its
  collar, one working order a symbol, the day's order count, the minimum hold, the gateway's kill switch. The owner
  is told ONCE A SESSION, by one error alert that begins "the sale path is unproven today" and names the stage's own
  reason (its failure, or where its attempt stands), with one `equity.alert` record (kv `eq_sell_unproven` {day, why,
  at}; `league/equity/live.py` `_sell_unproven`). **Why:** an exit must never be blocked; a proof exists to stop new
  risk, not to trap old risk (before A28 a stage that could not pass held every real lot for days, the maximum-hold
  exit and the flatten among them, while it also stopped every new buy). **Its cost, stated:** a real sale can go
  through a path the practice account did not prove that day. A SELL stage that ends its window unpassed is
  "failed": an error alert with the owner's step (look at the practice account's SPY position and orders; that
  alert's words "Real equity lots stay held" are the proof's own, from before A28, and are no longer true past the
  cut-off: `league/live/paper.py` is inside the options execution fingerprint and is not edited for a sentence) and
  **new real buys stop until it passes** (unchanged); the next open window buys again and the one after sells. The
  attempt row is kv `paper_proof_stock`. Only the equity book waits on it (options entries
  never do); its client ids are `lq-pp-...`. **Stage BUY never waits on the options route's own paper proofs**
  (`paper_proof`, `paper_proof_single`): it goes in the first open window after the deploy. While it has nothing to do
  (waiting outside its BUY window, or holding its lot outside the SELL stage's window) the proof makes no call to the
  practice account. It tries once a session: a refused or unfilled practice buy costs a day. **A practice order the
  venue never shows** (its POST answered unknown) is looked up by its client id, never sent again blind, and by the
  equity book's own rule it is LOST after four lookups or ten minutes: one warning, nothing owned by it. A lost buy
  costs that session (the next open window buys again, on a baseline read then); a lost sale goes again at once
  while the practice account still holds the lot, and not at all when it holds less (it may have filled: the SELL
  stage then fails at the window's end, with its error alert, each session until the owner has looked). A lost order
  is looked for again for three days: one the venue shows after all is a second warning, and its fills are the
  practice lot's (no second buy when it is found before the next one).
- **After a Sunday deploy**, each step needing the one before it: the seeds are validated and looked at on Sunday by
  the equity rounds (above), in the declared order; a seed that passes is seated at Probe and decided for Friday's
  close by the book's SEATING PASS (below), so a look passed AFTER the day's decision still trades the next session,
  not the one after; stage BUY goes in Monday's open window (its first send is the 09:31 minute's); the first real
  close-window buy can then go in Monday's close window (the 15:55 minute's send); stage SELL goes in Tuesday's open
  window. **No real buy on Monday** when any of these holds: no seed passed its look before Monday 15:54 ET (the
  seating pass stops a minute before the close window); the seated program's decision on Friday's bars asks for no
  buy (see **The order of the looks**: the seeds expected to trade buy only after a down close); stage BUY not
  passed; or the options route's `paper_proof` is not passed while `live.require_paper_proof` is on (`real_block`
  then refuses every real open in BOTH lanes: check that health shows `paper_proof` passed). An `at: open` intent of
  a program seated after 09:45 ET is recorded missed.

**Cash only, by choice** (amendment A1). The gateway (PR #532) admits margin where the account offers it (its book cap is
equity x min(2, the multiplier), bounded by buying power). The House's equity book in E1 does not use it: margin
interest is not metered yet (the goal forbids hidden costs) and the loss budget binds first. The House rule: the equity
lane's long value + open equity buys + the options' open maximum loss <= E (`equity_money.invested_share` "1.00"); an
equity open is refused while account cash is below 0 or any us_equity position is short. THE HOUSE-WIDE CASH RULE
(A8.1): no real open in either lane may push cash below the reserve. Available cash = cash - |short_market_value| -
every working buy's worst cost (both books) - working reservations - `equity_money.cash_reserve_usd` ($50, above the
gateway's $25 floor). The options book reserves against min(`options_buying_power`, available cash), and equity sizing
reads the same figure. If cash is ever below 0, every open in both lanes refuses and an alarm fires. The same sum
binds option opens (`money.invested_room`): equity lots and working equity buys + the options book's open maximum
loss + the new open at most `invested_share` x E, in `plan_open`, the incubator, the House live test and the
calibration. With no equity lot it never binds before `book_share`. A later release may raise `invested_share` toward
the venue's overnight multiplier once a margin-interest row is metered.

**The loss budget is shared** (A8.6). The options lane's `options_money.probe` rows ($400 net in any rolling 20 sessions,
$800 net in total) bound every agent program's Probe opens in both lanes, read by one `probe_tally`: an open ETF lot
counts 20% of its value, a stock 40%, an option its maximum loss, and ONE slot a program (never one a lot). The
equity lane holds at most the LOWER of its Probe sleeves (`probe.max_programs` x `probe.sleeve_share` x E) and the
invested cap (`invested_share` x E: 1.00 E). A one-ETF program holds half a sleeve; a program that holds several ETFs
can fill its whole sleeve, and where the sleeves ask for more than the account holds the invested cap is the bound:
at most 1.00 x E of ETFs, 0.20 x E of open risk. The options Probe lane keeps the window's rest, $400 less its
realized loss less 0.20 x the equity lots, and no room under the invested cap once the equity lane is invested to
it: **effectively off** while the equity lane is full. Each entry is cut to the budget's room over 0.20, so the lane
stops at $2,000 of ETFs, less five times what the window has lost and the options lane has at risk. **The seats and
the sleeve** below states all of it in figures at the pair in force (the lots, how many fit under each cap, the E
from which the window cuts one, what the options lane keeps). The `dlane` report says so with the figures
(`equity.options_probe_room`: the lane's most, whose `bound` names which rule set it: the sleeves, the invested cap
or the budget; its statement is built from the rows in force).

**The seats and the sleeve are two numbers** (release E5-S, Oct 11, 2026; `equity_money.probe.max_programs` and
`probe.sleeve_share`, league/constitution.py). A program that passed its look takes a seat (who takes a free one is
**The seat rule**, below; it was first come until release E5-A, deployed 22:51Z Oct 11), with a sleeve
of `sleeve_share` x E; its position in one ETF is at most half its sleeve. The pair is set by ONE mechanical step,
`set_design SEATS SLEEVE`, which rewrites the two rows, the swarm's `elane.roster` (league/swarm/policy.json and the
default in league/swarm/elane.py: the seats, written in three places and held equal by a test), `PINNED_DIGEST`, and
the design blocks of four documents (the one below, the constitution's `probe` comment, league/equity/INTERFACES.md
section 17 and the CHANGELOG entry), and nothing else; run again with the same pair it changes nothing. The design in
force, in rule arithmetic of the two numbers:

<!-- equity-design:begin -->
THE DESIGN IN FORCE: 6 seats (`probe.max_programs`, `elane.roster`), a Probe sleeve of 0.33 x E
(`probe.sleeve_share`). A one-ETF program's lot is `position_share.etf` (0.50) of its sleeve: 0.165 x E.
A lot in every seat asks for 0.99 x E of ETFs; the lane holds at most 0.99 x E of them, 0.198 x E of
open risk at weight 0.20. One ETF across programs (the instrument cap, 0.50 x E): 3 whole lots fit; the
next program's lot of it is 0.005 x E. At E = $2,000, the account all cash and nothing realized: 5 of
6 whole lots fit under the invested cap (1.00 x E) and the $50 cash reserve alone, and
6 of 6 in the $400 window alone; the window alone holds all 6 up to E = $2,020.
Whole sleeves (programs that hold several ETFs) ask for 1.98 x E; the lane holds at most 1.00 x E,
0.20 x E of open risk. The options Probe lane keeps $400 less the window's realized loss less 0.20 x
the equity lots: $400 - 0.198 x E against the one-ETF lots above. The gateway's day line (4x
equity of buys a day, a cancelled one too) admits 24 sends of such a lot: 4 entries can each climb the
collar's ladder of 5 sends. A Sized sleeve (the step is parked) would be between 0.33 x E and
0.50 x E.
Money digest `558dc3a2`, full digest `d4e59a79` (`PINNED_DIGEST`); the rollback, `set_design 3 0.50`, is `68f1bca9` / `d244fb10`.
<!-- equity-design:end -->

- **Its source.** The pair is the captain's to set, before Monday's open, from the verdict of the pre-registered
  study EQDONE-3 over seats 3, 4, 5, 6 x sleeve 0.50, 0.33, 0.25 (its design and decision rule pinned before its
  run). The build that made the choice two numbers left a working pair in the tree and is not a release until the
  verdict's pair is set. Every pair of the grid is held by `league/tests/test_equity_design.py` and
  `test_equity_sleeve.py` through the House's own `size_entry`, and each pair's money digest is pinned
  (`league/tests/equity_design.py` `DIGESTS`), so the pair the study names lands on a digest the tree already states.
- **Why the two move together.** Done reads 30 real closes whose P&L sums above zero. More programs trading
  at once make closes sooner, and a smaller lot a program keeps the same shared loss budget over them.
- **Its cost, plainly.** A seat is one passed sealed look, so more seats put more programs, the screen's false
  positives among them, on real money at once. A smaller lot pays the same spread and fees per dollar and earns a
  loss back more slowly. Closes made sooner by long-only index ETFs are weak evidence of skill. **It buys closes, not
  edge and not a higher expected profit.**
- **What does not move.** The owner's caps and loss budget, each applied by `size_entry` to every entry at any pair
  and named when it binds: an ETF at most 0.50 x E across all programs (`instrument`); at most 1.00 x E invested,
  the options' open maximum loss included (`invested`); the House-wide cash reserve (`cash`); the shared loss budget,
  $400 net in any rolling 20 sessions and $800 net in total (`budget`); the program's -$300 line, the kill switch,
  the daily stop and the drawdown stop; the stock paper proof's gates. Long only. A seat only decides who may OPEN.
- **What a pair can make bind that A20's did not** (the block's counts say where). When the seats' lots do not all
  fit, the House cuts or refuses an entry that the Gym, which judges each program alone in its own sleeve, fills, and
  Done's consistency clause (A14) reads that difference, as it did for A20's 0.66. When more programs sit in ONE ETF
  than its whole lots, the later ones are refused there (at a sleeve of 0.33 the next one gets a lot of 0.005 x E,
  which is above the $10 minimum from E = $2,000 on). An equity program with a lot takes one of the options lane's
  eight Probe slots (`options_money.probe.max_open`). And `order_path.max_orders_day` (60 equity orders a day,
  cancels counted, the loose end of its bound) was sized for three programs: N programs that each sell at the open
  and buy at the close use 2 x N orders on a day every order fills at its first send, and up to 18 x N on a day
  every order climbs its whole ladder (five sends and four cancels each), so with more than three seats a day in
  which most orders are re-priced can run out of the count. Entries then wait and are recorded missed at their
  cut-off. AN EXIT IS NEVER STOPPED BY THE EQUITY COUNT (release E4 step two; A28: an exit must never be blocked):
  its sends and cancels are counted, so they stop entries, but an exit meets only the House-wide count, which keeps
  the options book's exits their room under the gateway's day lines; only that count can carry an exit to the next
  session. (Under the equity count a held basket stopped exits: each re-priced sale costs a send and a cancel a rung
  and every lot climbs at once, so 8 to 12 basket lots on a fast open used the 60 before the ETF lots' sales reached
  the rung that fills, and those sales were carried; review-live measured it on the real book.) Nothing is sold for
  it. WHAT THE COUNT STILL COSTS A BASKET: on a day its exits climb the ladder the count can refuse a rotation's new
  buys (review-live: 3 to 20 buys refused on rotation days at 12 names), and each refused entry is an A14
  difference; `elane.panel.max_names` (12) is the captain's lever (fewer names, fewer orders a rotation), a setting
  with no digest move. AND THE HOUSE-WIDE COUNT CARRIES THE EXITS: in the rehearsal of the fix (the reviewer's
  harness, invented prices, a twelve-name basket beside ETF lots on an open whose sales each need their third or
  fourth rung) the equity book's day reached 135 sends and cancels, every exit done that session; those orders
  count against the House's 250, so on such a day the options book's OPENS have that much less room (its exits keep
  theirs).
- **At the deploy**, for the programs the House already holds:
  - **A Candidate waiting for a seat is seated at the first band sync after the House starts on the release**: under
    "first-come" the swarm's reader shows it once `elane.roster` has a free seat (`banded_at`, then id); under the
    seat rule in force the book reads every waiting Candidate and seats the best-ranked (**The seat rule**, below).
    Either way the seating pass
    (every minute between a recorded decision and the next session's close window) moves it to Probe, makes its
    instance and asks it for the same close, so its first order goes in the next session. Nothing else moves in
    that pass. A `swarm.json` in the state root that writes `elane.roster` can only LOWER the seats: one that still
    says 3 keeps three seats until it is raised or removed (`set_swarm.py`).
  - **A buy already planned is sized at its send**, on the table in force then, never at the decision: a `share`
    intent is that share of the sleeve in force; a `usd` intent is cut to that sleeve's own caps (`sleeve_cap`,
    `sleeve_cash`). Its replay twin agrees at any size: the closed-form twin buys the lot's own entry notional and
    reads returns, and the forward record's intent agreement keys a buy by its symbol and fill point, whatever its
    size.
  - **A lot larger than a smaller sleeve is never sold for it.** The House's own exits are the maximum hold, the
    failed decides and a retired or demoted program (`_house_exits`), never a size. The program's next entries are
    held to the sleeve in force: no more of that ETF while the lot is over half the sleeve (`sleeve_cap`), and of
    another ETF only what the sleeve has left (`sleeve_cash`: nothing while the lot alone is over the whole
    sleeve). Seats moved DOWN unseat nobody either: a Probe program keeps its seat, and no new one is given until
    the count in force has room.
- **Rollback**, one owner deploy: `set_design 3 0.50` is A20's seats and sleeve (the seats' bound may stay at six).
  Its money digest is the one the design block above states (the pair's pin in league/tests/equity_design.py
  `DIGESTS`). It was E1's own `7e41909a` until release E5-A put the seat rule's block in the table; with that
  block left out the pair is still on `7e41909a`, to the last hex (`DIGESTS_E5S`: a test holds it). The standing
  grant re-ratifies at the House's start; no
  fingerprint moves and no evidence is reset. Programs seated beyond three keep their seats (above) and are sized
  on the larger sleeve from then on, inside the same caps.
- Proof: `league/tests/test_equity_design.py` (every pair of the grid at a stated E, through `size_entry`; the
  design blocks held to the rows; the deploy's three cases through the real book and the real swarm store),
  `test_equity_sleeve.py` (every pair against the rule written out), `test_constitution`, `test_ci` (the bounds, one
  step past each, the gateway's day line by sleeve), `test_elane` (the seats' three places), `test_equity_money`
  (a move of the pair is a digest of its own, ratified by the owner's deploy alone, and so is the move back).

**A20: the Probe sleeve at 0.50 x E, three seats** (the captain's amendment A20, Oct 11, 2026: the design release E1
deployed at 07:18Z Oct 11, kept here as that decision's record; where it and **The seats and the sleeve** above
differ, that section is the tree. `equity_money.probe.sleeve_share`,
league/constitution.py). The rule then: a program that passed its look took one of three seats, first come, with a
sleeve of 0.50 x E; a program's position in one ETF is at most half its sleeve, so a one-ETF program's lot was
0.25 x E (0.125 x E under the sleeve of 0.25 the branch carried before). Seats, seating and every other row were
unchanged by it.
- **Its source.** A pre-registered study (EQDONE-2: its design and decision rule pinned before any code or figure,
  its code before the run) and that study's review, both finished before the first live equity trade and before the
  result of the options lane's next close was known. Its question: Done reads the sum of the realized P&L of every
  agent program's closes since Oct 10, both lanes together, so a losing close early in that sum must be earned back
  by the lots that follow, and a lot of an eighth of E earns too little to do it. What the larger lot is exposed to
  is long-only index-ETF direction: mostly the market, not alpha.
- **Why 0.50 and not the study rule's 0.66.** The pre-registered rule over first-come designs picked 0.66. Its review
  adopted that with a fallback to 0.50 if entries the House refuses or cuts make live trading differ from the replay
  that Done's consistency clause reads (A14: the live and the shadow intents agree on at least 95% of the counted
  sessions). They do: at 0.66 three one-ETF lots meet the invested cap and the cash reserve, so some entries are cut
  or refused live that the Gym, which judges each program alone in its own sleeve, fills. At 0.50 no cross-program
  cap binds for three one-ETF programs (0.75 x E, under the invested cap; two of them in one ETF are exactly the
  instrument's 0.50 x E), so what a one-ETF program is filled live is what its replay fills.
- **Its cost, plainly.** Against 0.66: a smaller rise in the chance of Done. Against 0.25: about twice the dollar
  swings, losses as much as gains, and twice the spread and fees paid at zero edge. **The larger lot buys variance and
  exposure to the market's direction, not edge and not a higher expected profit.** It was fixed before Monday's
  option result was known and before the first live share trade.
- **What it is.** A loosening of ONE row and its bound (`EQUITY_MONEY_BOUNDS["probe.sleeve_share"]`: 0.25 -> 0.50),
  decided by the captain (Claude) under goal item 4 and reported here with its cost. **It is bounded by the owner's
  caps and loss budget, none of which moved**, and `size_entry` applies each to every entry at any sleeve, naming the
  one that binds:
  - an ETF at most 0.50 x E across all programs (`instrument`): two programs in one ETF hold exactly 0.50 x E
    together, each lot whole, and a third program's entry in that ETF is refused;
  - at most 1.00 x E invested, the options' open maximum loss included (`invested`): three one-ETF lots are 0.75 x E
    and fit; a fourth lot (a seated program's second ETF) fills the cap, and the next entry is refused;
  - the House-wide cash reserve (`cash`): when E is the account's own equity, that fourth lot is cut to the invested
    cap's room less the $50 kept in cash;
  - the shared loss budget, $400 net in any rolling 20 sessions and $800 net in total (`budget`): an entry is cut to
    the budget's room over the ETF weight;
  - the kill switch, the daily stop and the drawdown stop, as before.
- **The risk, stated** (the study's review; rules only, no result of the study). The lane is long only and cash only.
  **The stops do not bound this lane's loss**: a tripped daily or drawdown stop, or the kill switch, blocks entries
  and sells nothing, so lots already held ride the market until their own exits. What bounds the lane's loss is the
  shared budget ($400 net in any rolling 20 sessions with open risk counted at 20% of an ETF lot's value, and $800
  net in total: no new entry beyond their room), EDM1 (a demoted program's lots exit at the next open) and the
  program's -$300 line. An open lot can lose more than the 20% it counts for. **The option-sign note**: by the
  study's own table, if Monday's option (the options lane's open Probe position, which expires Monday) closes at or
  above zero, the smaller lot would have been the better row. One row was shipped, fixed before that result was
  known, and this is its stated price.
- **The sizing-up step is parked** (`equity_money.sized.min_trades` 1000, inside its bound and a tightening; the
  captain's decision on the study's review). The owner's loss budget ($400 net in any rolling 20 sessions, $800 net
  in total) covers all real money, and E1 as built leaves a Sized program's closes outside the Probe window, the
  total and the -$300 line; with the Probe sleeve equal to the Sized cap (0.50, A20's design) the step would size
  nothing up anyway. With 1000 no equity program is Sized, so every equity close stays inside the loss budget's
  tallies, at any Probe sleeve. The
  sizing-up RULE stays pre-registered as written (**Sizing up and demotion** below); the row is switched back only
  together with a change that counts Sized closes in the budget.
- **The money digest** of A20's design is `7e41909a` (full digest `e909eb10`): one move with the E1 block, ratified
  at the House's start on the owner's deploy (07:19Z Oct 11). A move of the sleeve or the seats since is
  `set_design SEATS SLEEVE` (**The seats and the sleeve** above): three seats at 0.25 is `3a7c52d5`. Lots already
  held are not resized: a sleeve applies to the entries sized after it.
- Proof: `league/tests/test_equity_sleeve.py` (at A20's design, stated as a table of its own: three lots of
  0.25 x E with no cap binding, the fourth lot against the invested cap and the cash reserve, two programs in one
  ETF, the budget's cut, a Sized program's sleeve), `test_constitution` and `test_ci` (the bound and one step past
  it), `test_equity_bands_money`, `test_equity_money`, `test_equity_e2e` (the real book's lot).

**The schedule** (New York time; `league/equity/schedule.py`, the offsets in force in `equity_money.order_path`; half days
by the same offsets from the 13:00 close):
- 16:20 the bars: each live program's symbols and the symbol of every lot open, opened or closed that session (a
  retired or demoted program's last lot keeps its exit day's bar for its twin), read even when no program is live,
  1Day raw and adjustment=all through the session just closed, written to `eq_bars` with the arrays' sha (A8.11). A
  missing bar of a held symbol waits for the same 30-minute grace, then the day closes without it. 16:30 the decide:
  one isolated "equity" decider request a session, the intents recorded in `eq_intents` for the NEXT session, at its
  open (`"at": "open"`, the default) or its close (`"at": "close"`), with the House's exits (a lot is held at most its
  program's `max_hold_sessions`, default 20, cap 60: it exits at the open that completes them, the Gym's rule too; a
  demoted, retired or band-dropped program; 2 sessions of failed decides) as `house_exit`. A decide missed by a
  restart runs as a catch-up for the last close. A day's bars fetched again by a later decision keep their morning
  audit while their PRICES are unchanged (the next day's fetch always reads a later volume: the volume is no part of
  the mark).
- **A House exit rule that is due** (max hold, 2 failed decides, a demoted or retired program) goes at the next OPEN
  even when the program planned its own `at: close` sale of that lot: that sale is recorded refused and the program
  reads why in its next rejects, as the Gym rejects it. A program's own sale at the open goes first, and a House exit
  already planned (a carried one, a flatten) stands.
- **An instance is asked once a session**: a decide that runs again (a failed step, a restart between two programs'
  commits) skips a program whose `last_decided_day` is the day. **A failed decide is counted once a session** (kv
  `eq_failed` {instance: day}), whatever failed: the House could not ask (no program loaded, no bar, no ctx, the
  decider), the program's own decide failed (it raised, ran past its limit or is disqualified: the child's answer
  says `failed`, as the Gym engine counts), or the morning audit found a price mismatch. A program the House could
  not ask is asked again every 10 minutes until the next session's pre-open; a program whose own decide failed has
  spent the session (`last_decided_day` moves, no intent recorded: `last_decided_day` is the last session it was
  ASKED, not the last it decided well).
- 08:30 the morning re-fetch audits the last decision's bars against a new fetch: raw open, high, low and close
  exactly, and the adjusted series as the as-of prices a program saw, to the vendor's cent rounding (see **The
  vendor's cents** below). A PRICE mismatch is an error alert and a twin note (kv `eq_bars_audit`), cancels that
  decision's planned buys of the programs that read the symbol and counts one failed decide for each (A8.5: two in a
  row exit the program's lots). A VOLUME-only difference is a note (`eq_decision.volume`,
  `eq_bars_audit[day].volume`, the `equity.bars_audit` record) and nothing else: the 1Day bar's volume goes on
  counting late and after-hours prints after 16:20. Each symbol's rows are marked on its own verdict
  (`eq_bars.audit` ok | mismatch); a symbol the decision did not read is left unmarked.
  09:25 the pre-open: the account, positions and orders read, reconciliation, the plan.
- THE OPEN: exits from 09:30:30; entries after the exits filled or 2 minutes (`exit_wait_s`), sized on cash after the
  exit fills, until 09:45 (a missed entry is recorded, never chased); exits go on until 15:55. THE CLOSE (A2): from
  15:55:00 exits then entries, marketable limits re-priced each minute to 15:59:30, then recorded missed. In the
  close window the entries wait for the window's exits to fill, or one minute (`CLOSE_EXIT_WAIT_S`, 60 s), as the open
  window waits `exit_wait_s`. In either window an entry sized to nothing is not final while an exit may still fill:
  it is sized again each minute and recorded missed at its cut-off. Cost stated: when an exit is still unfilled
  after the wait, an entry that is cut but not to nothing goes at the smaller size, and its target is then fixed by
  that first order. (THIS IS A SHARE PROGRAM'S RULE, and release E4 leaves it as it is: a recorded week holds a
  share program's orders to main's, `league/tests/test_equity_etf_orders.py`. A PANEL program's cut buy WAITS while
  an exit of its own program is still working and goes whole once it has filled, or is recorded missed at its
  cut-off: rule B8 of the panel kind, `EquityBook._cut_waits`.) Collars 10 bp (ETF) / 25 bp (stock) widening to
  50 / 100; an order refused before the venue
  widens no collar. A replacement goes only once the old order is terminal (A8.4), and one buy intent is one lot
  whatever a re-price finds. The book's ENTRIES stop at 60 orders a day (sends and cancels, exits' included, with
  room kept for every open lot's exit), an exit is never stopped by that count, and nothing is sent while the
  House-wide day count would leave less than the options book's exit reserve (A8.3).
- **The send times are effective, not nominal**: 09:30:30 and 15:55:00 are the earliest moments, never the send
  times. The House's minute starts 3 s past the wall minute and the equity book runs after the options minute, so the
  open window's first send is the 09:31 minute's (09:31:03 plus the options minute) and the close window's the 15:55
  minute's (15:55:03 plus the same), with one re-price a minute at most (an order's age is counted in whole House
  minutes, so a minute that started milliseconds early is still a minute). The close window therefore has the 15:55 to
  15:58 minutes, and 15:59's only when the options minute ends before 15:59:30. Nothing is POSTed at or after a
  cut-off by the wall clock (09:45:00 an open entry; 15:59:30 every exit and every close entry), and an order the
  venue still shows working on a later day than its own is cancelled at the first minute that sees it.
- MIN HOLD: a lot is never sold in the session it was bought (a close-bought lot may sell at the next open), kill switch
  included: the gateway's kill switch blocks sells too, so exits wait on it.
- The House jobs: `equity_data` at the House's start and 22:30Z (below); `equity_twins` at the start, 01:15Z and 40
  minutes before each open; the `dlane` report (01:30Z, 30 minutes before each open) reads the twins.

**The seating pass** (`league/equity/live.py` `_seat_step`). Once the day's decision is recorded (kv `eq_decide`
{day, status, at, instances, why, seated_at}), the book reads the equity families again every minute until one minute
before the next session's close window (15:54 ET). A Candidate that has since passed its look and holds a roster seat
goes to Probe, gets its instance and is decided for the same close on the same bars, so its first order goes in the
next session. Nothing else moves in that pass: no demotion, no sizing up, no retirement, no new version of a running
family; those happen once a day at the decision. A record without `instances` (an idle or failed day, or one written
by hand) is closed to the pass. The pass reads the swarm store once a minute around the clock (one read-only
connection and a few rows); a store it cannot read shows in the minute's `equity.families` (`unreadable: ...`), with
no alert until the decide.

**The band sync retires only on positive evidence** (`_sync_instances`, `league/equity/families.py`,
`league/swarm/bands.py` `read(..., strict=True)`). The book retires an instance only on a row that names another
version or a band that does not run, or, for a family with no row, on the swarm store's own record (retired, another
banded version, a band that does not run, a band proof that is not the current equity identity). A swarm store that
cannot be read, a family whose code file or version row cannot be read, or a family the store does not hold changes
nothing: the instance keeps deciding on the program the book holds, a warning alert names it once a decision day, and
the sync runs again each minute until the decide. Every retirement is a warning alert. A retired instance whose
family's row is back in the Probe or Sized band on the same version and program runs again at the next decision
(never an EDM1 demotion, which is sticky for the version). **To stop a program, retire or re-band its family in the
swarm**: `eq_instances.retired_at` set by hand is undone while the row runs.

**Shares on the real account (A8.2;** `league/live/step.py` `_close_shares`**).** A SHORT share position is covered at
once with a market buy of exactly the account's short (the gateway admits no larger buy on a symbol held short): whole
shares first when the short is a share or more with a fraction, the fraction at the next reading (5 minutes in
session, 15 outside). If a program's lot was netted against the assignment its shares are gone and are never bought
back: the equity book closes the lot as `forced`, at the cover's fill price once the House's cover has filled, or at
the lot's mark once a reading finds the short closed outside the House and the account short of the lot; it is
exported with reason `forced`. A refused `lv-shares-` order is an error alert at once and hourly while it lasts, and a
refused cover also mails the owner (stop `assignment`). Owner step: look at the real account's position and close it
by hand if the House cannot; after a short closed by hand run `python3 -m league.live --root <state>
--clear-assignment` (the ledger keeps what the House did not cover). A LONG excess is sold at market after two
readings only on a symbol the equity book holds no lot of, or for the part an assignment or exercise explains; shares
beyond a held lot that nothing explains (a split not yet booked) are never sold: an error alert names them and
reconciliation freezes real entries until the book or the owner accounts for them. health.json `live.shares` shows
the ledger, the House's share orders, a refused order's run, unexplained shares and swallowed lots.

**The two books' reconciliations.** The options book's reconciliation does not judge a us_equity symbol while the
equity book has an order working on it or one that changed in the last two minutes (`equity_hook.flux`, `FLUX_S`); the
equity book's own reconciliation judges it once it settles, and its freeze blocks options opens too. An equity book
that cannot be read gives the empty set: everything is judged (fail closed).

**The minute.** An options pass that raises no longer costs the equity book its minute. The equity book's minute is
skipped (summary `equity.skipped`, one warning a run) only when the real account's reads hung in the options pass
(10 s or more in failed reads) and the pass ended past second 45 of the minute. A failure inside the share handling
(`_close_shares`) is a warning and is read again at the next reading; it never ends the options pass. The owner's two
commands (below) are read first in the equity book's minute, so they stay pending on a minute it skips.

**The data job** (`league/ops/equity_data.py`, `equity_data`): Alpaca SIP daily bars of the universe through the gateway
(`GET v2/stocks/bars`, already allowed), adjustment=raw and adjustment=all, from 2016-01-04 to the last closed session,
the whole history each run (the all series restates every earlier row at a corporate action). The audit must pass
(calendar with no gap or extra day; sane bars; every raw/all ratio jump a split the raw close shows, and no raw jump
the all series did not adjust; volumes; the regular session, the design's fact 1), then
`league.equity.store.write_store` writes `<state>/equity-daily/` atomically with the GATE mark. A failed fetch or
audit writes nothing (a failed receipt, retried in its grace) and the last good store stays; a failed audit's receipt
lists the first five problems of each failed check (symbols, days and verdict words; every decimal figure masked). The
data never leaves the House's state directory (the vendor's terms; a public repository).
- **Volumes**: every raw bar has a volume above zero, or is a FLAT bar of volume 0 (open = high = low = close: a
  session without a trade), which passes and is listed in the manifest's audit (`volume.zero`).
- **The regular session** (SPY's 1Day bar against its 1Min bars on 20 sessions): the session's prints are the minutes
  from 09:30 through the closing minute (16:00; 13:00 on a half day), where the closing cross prints. A day agrees
  when its open is the first minute's open or lies inside the 09:30 minute's range, its close is the last minute's
  close or lies inside the closing minute's range, and its high and low lie between the extreme before the closing
  minute and the extreme with it; the volume is not compared. A field that does not agree is "extended" when it is
  the whole 04:00-20:00 day's figure and no session print shows it, else "neither". **"extended"** (more than 2 of
  the 20 days hold an extended field) FAILS the audit and is a stop for E1 (the store must then be built from 1Min
  bars); **"regular"** needs every day compared, at most 2 stray days and none extended; anything else is
  **"unverified"**, written and warned.
- **Why they read so** (the rehearsal on the House box against real SIP data, Oct 11, 2026; the rules and their
  reasons only: no count read from the vendor's data is written here): as first written both checks were wrong about
  real data and the job could never write a store. A flat bar of volume 0 is a session without a trade; the history
  holds such bars, and history never changes. The daily bar's open is the opening cross (inside the 09:30 minute's
  range) and its close is the closing cross (inside the closing minute's range), while its volume counts prints the
  minute bars leave out; a rule that ended the session before the closing minute and compared the volume could never
  read "regular", and read a close-set high or low as "extended". These correct the checks; they loosen no evidence,
  and a bar truly built from extended hours still fails.

**The vendor's cents** (the rehearsal's other finding; `league/equity/config.py` `rounding_bound`). The vendor rounds
its adjustment=all prices to the cent and restates the whole series at every dividend and split. One bound says how
far that rounding can move a ratio or product of adjusted prices (1.5 x half a cent x the sum of 1 / price), and two
places share it so they cannot drift apart:
- **the Gym engine** (`league/equity/engine.py` `ratio_tolerance`): a step of the all/raw close ratio inside its own
  tolerance is no event. With a fixed bound the engine read the rounding as dividends (cash credited) and as
  anomalies, and read a split whose step the rounding had pushed above its factor as a neighbouring fraction. A
  dividend is credited to within about a cent a share; one smaller than the rounding of its two closes is not
  credited. `engine.py` and `config.py` are evidence modules: this moved the equity identity, before any look.
- **the book's morning audit** (`league/equity/live.py` `_as_of_equal`): two readings of a series an ex-date restated
  give the same as-of prices within that bound. Raw prices are compared exactly. What the audit can still see is a
  move larger than the bound: about 0.03 / price (half a basis point at $600, three at $100).
- **I6 is the two builders on the same bars, not a live ctx against a later store.** After a later event the store's
  as-of prices differ from the ones a live decision saw by up to that rounding, so a live decision's `ctx_sha` does
  not reproduce byte for byte from a later store. A program whose condition sits within that rounding of its
  threshold can decide differently live and in a later replay. A14's intent-agreement reading (95% of counted
  sessions) polices it.
  Owed before E2's births depend on it: as-of prices built from raw bars and per-event factors.
- **The event tables have a first and a last row** (`league/gym/events.py`; `ctx.events`): fomc 2017-02-01 through
  2026-12-09, cpi 2017-01-18 through 2026-09-11, jobs 2017-01-06 through 2026-09-04. Outside a table's rows its flag
  is False on every session, in the Gym and live alike (one constructor): every session of 2016, and live every
  session after the table's last row. The three seeds read no events. `events.py` is in the equity identity, so the
  tables are extended, with verified dates, BEFORE any event-conditioned program is born (E2), never after its look.

**The twins and the Done meter.** `equity_twins` (league/ops/twins.py) prices each closed lot's twin in closed form from
the House's own official opens and closes (`eq_bars`, raw) with the engine's fill function (open and close fills, the
same fees, dividends and split): "priced", "no_bar" or "unpriceable", final once judged, the gap in bp a side (live
minus twin; EDM1 demotes past 15 bp a side over 5 priced closes), each fill's slippage against its official price, and
the same-risk buy-and-hold over the same sessions. The `dlane` report's Done meters count from Oct 10, 2026 (the goal:
`done.counted_from`; every earlier agent close is listed in `done.earlier`, never counted); an equity close is one lot
fully closed, its net cash with fees and dividends, on `:r` (both meters), matched to its own twin; beside every close
and checkpoint ride the lane's label (MARKET BETA or EQUITY), the buy-and-hold, MTE, the screen's line recorded at the
program's look (S2's, `fp.screen` "S2") and "profit from market direction". Done is also read without the three seeded
programs (`done.without_seeded`, A8.12). A checkpoint holding an equity close stays provisional until its lot's broker fees are
posted: the book reads the account's `FEE` activities (the REG and TAF rows without an order id; an option's "OPT REG",
"OPT TAF", "ORF" rows are never an equity lot's) and posts each exit day's rows to that day's equity sales pro rata by
proceeds (`eq_lots.info.fee_basis` "broker", the estimate kept beside); a day without a fee row five sessions on is told
to the owner once a lot. The funnel (`league/ops/funnel.py`) counts the equity lanes apart (`equity`).

**Pre-registered before the first equity close** (the captain's A14, Oct 10, 2026; the same three sentences ride in
every `dlane` report as `done.preregistered`). Consistency is computed since release E3 (each checkpoint's `a14`: the
size of the mean fill gap either way, and the intents; **The forward record**, at the top): a checkpoint that holds
an equity close reads item 4 ("consistent with replay") by A14 beside the pinned rule's own measure, never by the
options replay gap alone (that gap divides by the maximum loss, a long lot's whole notional, so its 0.10 bound is a
thousand basis points). The fill-gap half is the
mean `gap_bp` of the counted equity closes with a final priced twin; the intents-agreement half is read from the
forward record's twins (the live and the shadow intents, session by session); unmeasured, A14 does not hold and the
reading says why. **The intents half is computed against a twin that is re-based after each differing session (the
captain's A29, registered before the first real share order: **The forward record**, "The twin is re-based after a
difference"); the three sentences below and both bounds are as registered.** The close-date figures are computed
since release E4's step two (each checkpoint's `close_dates`: the distinct close dates among its counted closes, all
programs, and the date-clustered t of their P&L, the closes of one date summed; eight lots of a basket sold at one
open are one date), beside and never a rule; no forward rule moves a seat. A reading with no
equity close is read by the pinned rule's own measure, as before. The Done rule itself is unchanged.
- Done's "live fills consistent with their replay" is read at each Done checkpoint, over its counted closes: the mean
  fill gap against the official-price model is at most 15 bp a side AND the live and the shadow intents agree on at
  least 95% of the counted sessions. A checkpoint that does not meet both says "not consistent" beside its P&L.
- Every Done reading is reported beside the number of distinct close dates among its counted closes and a
  date-clustered t of their P&L.
- The forward seat rule is written and inactive: an incumbent with fewer than 5 real closes is never unseated, except
  by EDM1.

The official-price model is the engine's fill (the session's official open or close moved by the half-spread,
`league.equity.engine.fill_price`: what each equity twin is priced with); the shadow intents are the same program's
decisions replayed on the same sessions. Closes that share a close date are one cluster of the t.

**The seat rule** (release E5-A, deployed 22:51Z Oct 11, 2026; the captain's A24, registered 13:42Z Oct 11, before
the first live share close
and before any program waited for a seat, and amended by the captain's A30 at 20:47Z the same day, before the rule
was live; `equity_money.probe.seat` in league/constitution.py holds its name and constants: `rule`
"activity-1-free", `k_floor` "0.25", `idle_sessions` 10). A24 WITH A30 IS THE RULE IN FORCE. It replaced A14's
forward seat sentence above, which was written and never active. The same three sentences ride in every `dlane`
report (`equity.seats.preregistered`; A30's under `amended`):
- The seat rule is "activity-1-free" (the rollback value is "first-come"). A free seat goes to the best-ranked waiting
  passed program. Its rank K is the smaller of its Validation close days and its Train-era close days per 250
  sessions, a day counted only when the lots it closed that day sum to at least 0.25 of its sleeve (read as 0.25 minus
  0.0005, the engine's rounding); ties go to the earlier look pass, then the family id. K reads no P&L and no sealed
  window, and is never printed in public text. A seated program that is flat and has had no buy reach the venue, and
  none cut or refused by the loss budget, for 10 seated sessions is flagged idle: it keeps its seat while nobody waits
  and yields it at once when an unflagged program waits. A buy refused by the instrument cap, the invested cap or cash
  does not count as asked. A yielded program returns only into a free seat, by the same rank, with no new look. No
  trading program is ever stopped by the seat rule: outranking is not adopted. Seeded and bred programs follow the
  same rule, and EDM1 covers waiting programs too. The rule only decides who may open: never a forced or hand-placed
  trade, and no lot is ever sold by it.
- The seat rule's costs, stated: closes concentrate in frequent traders, so Done reached this way is weaker evidence
  of skill; a daily slice of a quarter sleeve can buy rank; a slow, non-idle incumbent keeps its seat.
- Amended before the rule was live (A30). Free seats first: a free seat is filled before the idle test, and an idle
  seat yields only for an unflagged program that would still wait once every free seat is filled; the study that
  measured the rule ran the idle test first, so its gain was measured under that slower order. The idle clock does
  not run while the House refuses every open: a session in which the House refused opens for a House-wide reason
  (paused, the kill switch, a stop, a freeze, the grant not ratified, the paper proof's BUY stage not passed) is left
  out of every program's idle count and of its seated-session count for the idle test. A lost buy is not flat: a buy
  whose answer was lost keeps its program from being read flat, and so from yielding, for as long as the book may
  still take the lost order back, so no seat change ends in a House sale of a lot that shows up afterwards. Stated
  and accepted, not changed: a daily quarter-sleeve slice buys rank and immunity from the idle rule.

In plain words, and where each part lives:
- **Who takes a free seat.** The best-ranked program among those that passed their look and hold no seat. The rank
  is K, a count of how often the program closes a real-sized lot: the smaller of two counts made the same way, on
  its Validation run (2025) and on its Train-era runs (2016-19 and 2022-24, per 250 sessions). A day counts only
  when the lots closed on it add up to a quarter of the sleeve. Ties go to the earlier look pass, then the family
  id. Seeded and bred programs are ranked alike. K reads a lot's size and exit day and nothing else: no price, no
  return, no P&L, no sealed window.
- **Where K comes from.** `elane.look` writes the two counts beside the look, once (the family state's `elane_seat`),
  from the runs it already makes before the sealed run. A program that passed BEFORE this release has no counts:
  the gate's equity round writes them once (`elane.seat_backfill`), the Validation count from the stored run its
  look reproduced (made again when that file is gone), the Train-era count from the Train-era runs made again.
  Neither path mints a gate capability, calls the look or reads a sealed window, and what is kept is four whole
  numbers. Until a program has its counts it ranks after every program that has them; a backfill that fails is a
  House warning, once, and is tried again hourly. K IS NEVER PRINTED: the health page, the ledger and the report
  show a rank POSITION (first, second, ...), and the counts stay in the swarm's store on the box.
- **The idle seat.** At the day's decision (never in the seating pass), a seated program is IDLE when all three
  hold: it has held its seat for ten sessions; it is flat; and it has not ASKED for a buy in the last ten
  sessions. Asked means a buy of its own reached the venue, or the loss budget cut or refused it. A buy refused by
  the instrument cap, the invested cap, cash, its own sleeve or the gateway before the venue is NOT asked. An idle
  program keeps its seat while no unflagged program is left waiting once every free seat is filled. When one is,
  ONE idle program a decision day yields (the lowest K; then the latest seated): its band goes back to Candidate,
  never sticky, its instance is retired with the reason "yielded", and it waits flagged idle, behind every
  unflagged program. It returns only into a free seat, by the same rank, with no new Validation and no new look,
  under the same instance key (its record goes on); seating clears the flag and starts its clock again. Two rare
  traders do not rotate: a seated idle program keeps its seat while only idle-flagged programs wait.
- **Free seats first** (A30 (1): this is A24's reading). At a band sync every free seat is filled before the idle
  test acts: a program that a free seat takes does not wait, so an idle seat yields only for an unflagged program
  that would STILL wait. The study that measured the rule (EQDONE-3) ran the idle test first: with a seat free it
  made the idle program yield and seated it again in the same sync, its clock restarted. Its measured gain of the
  rule is therefore the gain under that slower order; the built order hands an idle seat on sooner in that one
  corner and touches no trading program.
- **Flat** (`_flat`, read from the book's own rows every time; A30 (3)). No lot open or closing; no intent planned
  or sent; and NO ORDER THAT MAY STILL FILL: an order pending, working or unknown at any age, or one GIVEN UP AS
  LOST while the book may still take it back. The order path looks for a lost order in the venue's orders for
  three calendar days after its session's (`LOST_TAKE_BACK_DAYS`) and, when the venue shows it after all, books
  its fills to its program's lot; the seat rule reads such an order as not flat for those days and one more
  (`LOST_HOLDS_SEAT_DAYS`: the two read the day off two clocks, and the seat rule's window is the wider). So a
  program whose buy was lost keeps its seat until the order can no longer come back, and the lot that shows up is
  its own to hold and to sell. Every other order status is the order's end: the order path never reads the venue
  for it again, and a lot is booked by a buy's fill and by nothing else. No program can yield while a lot could
  still be booked to it. Should the book ever hold a lot of a program that yielded (a fault of the order path,
  never the rule's doing), the lot leaves at the next open by the House's rule for a program that no longer runs,
  and an ERROR alert says the seat rule's promise was broken: tell the captain.
- **The idle clock and the House** (A30 (2)). A session in which the House refused every open is left out of every
  program's seated sessions and of its sessions since its last asked buy. HOW A SESSION IS KNOWN TO BE ONE: the
  book keeps a note of its own (`live.sqlite` kv `eq_open_note`), written at every minute in which the windows
  work their entries (the open window's, from 09:30:30 ET or the two minutes its exits are given, to 09:45; the
  close window's, from 15:55 or the minute its exits are given, to 15:59:30), whether or not anybody planned a
  buy, from the House's answer to "may a real equity open of ANY program go now?": exactly what `_open_block` answers
  before it looks at the instance (the House's own `real_block`: real money off, the grant, the kill switch, a
  stop, either book's reconciliation, the assignment latch, the options paper proof, the pause, the account read,
  cash below zero; then the lane's own: `equity_money.enabled` off, the stock proof's BUY stage not passed or its
  SELL stage failed, the equity book's freezes). A window is CLEAR
  from the first minute the House would have opened in it and stays clear. A session is left out when the House
  looked in one of its two windows and never once would have opened there (either window: a program may buy at
  the open or at the close, and a stop that trips at noon refuses the close's entries). One refused minute in a
  window that then cleared leaves nothing out: every entry of that window had its chance. What is NOT one of
  `_open_block`'s answers leaves nothing out either: the day's order count, a quote that cannot be used, a figure
  the sizing could not read that minute. WHY A PROGRAM CANNOT
  FORGE IT: the note is written from the House's own answer for a program that is live by construction
  (`OPEN_PROBE`), whether or not anybody planned a buy; no intent, tag, reason or order of a program is read to
  make it, and nothing a program returns from `decide` is a word of `_open_block`. WHAT IT DOES NOT COVER, stated:
  a session the House did not look at (it was not running in either entry window, or the rule in force was
  "first-come", under which no note is kept) counts as any other; a long outage with programs waiting is the
  watchdog's to end, and the captain may set the rule to "first-come" for its length. The plan shows each holder's
  `left_out` beside its `seated_sessions`, and lists the sessions left out (`left_out`), each with the window and
  the head of the House's reason ("open window: the House is paused"); the reason's whole words, which may hold a
  figure of the account's, stay in the book's note.
- **A seat's first session.** A seat taken before the next session's open (at the day's decision, or in the seating
  pass that evening or morning) counts its sessions from that next session. A seat taken once that session's open
  has begun (09:30:30 ET: in the seating pass during the session, or by a decision caught up after a restart)
  counts from the session AFTER it: the program could not use that open, so the session is not one of its ten.
  (`eq_band_since` keeps the decision day as `day`, as every other reader of the mark knows it, and the session
  the count starts from as `seat`; the plan's `since` shows the latter.) Chosen over dating every seat on the
  decision day, which would have let the idle test name a program after nine whole sessions.
- **What the rule never does.** It stops no program that trades: OUTRANKING IS NOT ADOPTED (a better-ranked arrival
  never makes a seated program exit-only; that would be a new value of `rule`, which the table does not allow, and
  may come only by A24's own pre-registered line). It plans no exit, cancels no order and sells no lot. A program
  is retired by a yield only inside the one state transaction that found it flat, so the House's exit rules
  (`_house_exits`: the maximum hold, two failed decides, a retired or demoted program) have nothing of it to sell.
  THE YIELD WRITES TWO DATABASES AND HAS ONE OUTCOME: the band lives in the swarm's store, everything else in
  `live.sqlite`. The swarm's write is the last statement before the live state's commit, so a live write that
  fails, or a row that changed, rolls the whole yield back with the band untouched; should the commit itself fail
  after the swarm took the band, the band is moved back to the seat's own before the error goes on (an ERROR
  alert when even that cannot be written; the next decision's band sync, which runs before any program is asked,
  then seats the program again by rank or retires it with nothing to sell).
  Every owner line is enforced at every send as before, whatever the seats: `size_entry` is not touched.
- **EDM1 and the waiting.** The demotion rule covers a waiting program that has a real record (one that yielded):
  if EDM1 names it while it waits it is marked sticky and takes no seat again under that version. A seating that
  does not take (the family's row changed under it, or the band rule says no) falls through to the next waiting
  program in the same sync, so a free seat is never held for a program that cannot take it. When EDM1 names a
  waiting program AT ITS SEATING (its twins were priced between two syncs; the seating pass runs no EDM1 pass of
  its own), the book writes the same `waiting_demoted` record and the same House warning as the day's own pass,
  drops its idle flag and takes it out of the plan's waiting list in that same sync.
- **One source.** The book computes the plan and writes it (`live.sqlite` kv `eq_seat`): `health.json`
  `equity.seats` is {rule, seats, holders [family, since, seated_sessions, quiet_sessions, left_out, flat, idle,
  seeded], waiting [family, rank, flagged, seeded], idle (the flagged: only programs that wait; a flag is dropped
  whenever its program's band is live at a sync, under either rule), sticky, left_out [day, why] (the sessions the
  idle clock did not run in), last (the last change of hands and why)}.
  The swarm's `bands.roster(root, lanes=LANES)` reports that same plan under `plan` and says its own lists are by
  pass time; the `dlane` report's `equity.seats` is the plan again, with `seeded_seats` and one sentence saying
  which seats the captain-seeded programs hold. Each change is a ledger record `equity.seat` (seated, yielded,
  returned, passed_over, waiting_demoted), a yield is also a House warning, and the day's decision says the seats
  in one line of its summary.
- **Its costs, as A24 states them.** Closes concentrate in frequent traders, so Done reached this way is weaker
  evidence of skill. A daily slice of a quarter sleeve can buy rank. A slow, non-idle incumbent keeps its seat.
  A30 states and accepts one more of the same kind, unchanged: a daily quarter-sleeve slice buys rank AND immunity
  from the idle rule (a program that buys a quarter of its sleeve at each close and sells it at the next open has
  a K near the top in both windows and is never flat for long; nothing in the pipeline refuses it; if such programs
  appear, the answer is a pre-registered change under a new rule name, not a patch). And one this build found in
  the rule's own words: a sale is not an ask, so a program that held one lot for more than ten sessions is idle at
  the first decision after it is flat, unless a buy of its own reached the venue since; it then yields if an
  unflagged program waits. (The build's other finding, that the idle clock ran on while the House itself refused
  every open, is what A30 (2) changed: such sessions are left out, above.)
- **At the deploy.** Nobody is unseated: every seated program keeps its seat and its seat's own day, and the idle
  clock counts from that day. The open note starts with the release: a session before it has no note and counts
  as any other. The first band sync reads the waiting Candidates; a free seat goes to the best-ranked of them. The
  swarm's next equity round writes K's counts for every passed program.
- **Rollback**, one owner deploy: `equity_money.probe.seat.rule` "first-come". One money-digest move; the standing
  grant re-ratifies at the House's start; no fingerprint moves and no evidence is reset. Under "first-come" the
  band sync and the swarm's read are release E5-S's, line for line (a test holds a recorded week to it): nobody is
  unseated, an idle seat never yields, and a program that had yielded queues as one that came back from Probe
  (behind every fresh Candidate) and runs again under its own instance key when a seat is free: its band and its
  instance come back in the same pass (the seating pass too), it is asked for the same close, and its idle flag
  is dropped. Under "first-come" no open note is kept and the book asks the House nothing it did not ask before;
  a roll forward counts the sessions under "first-come" as any other.
- Proof: `league/tests/test_equity_seats.py` (the row and its bounds; the ranks; 31 conformance vectors,
  `fixtures/equity_seat_vectors.json`; a lot of exactly the floor through the real engine; the look's counts and
  the backfill with no sealed read; each "asked" case through the real sizing and order path; no rotation; no
  sale and no exit-only on any path; EDM1 while waiting; the fall-through; first come on the recorded week,
  `fixtures/equity_seat_first_come.json`; the deploy night); `league/tests/test_equity_seats_a30.py` (A30 and the
  independent check's findings: the lost buy that shows up after all, with the order path asked status by status
  whether it could still book a fill of an order whose program reads flat; the ten-session pause after which no
  trader yields, and the program idle of its own choice that yields at its own tenth session; each House-wide
  reason; what is a refused session and what is not; EDM1 at the seating; the yield's two writes under a live
  write that fails, a row that changed and a commit that fails; the stale flag; first come's return; the seat's
  first session); `league/tests/test_equity_seats_seal.py` (two worlds that differ only in K: every generator
  reads the same bytes, and the seal's list names the key).

**P(Done | zero edge) beside equity closes.** `done.p_done_zero_edge` is the options Probe rules' simulation figure. It
was never measured for share closes: a delta-one lane reaches Done whenever the market rises, so its zero-edge P(Done)
is far higher. With any equity close counted the figure says so (`applies_to`, `equity_note`) and each checkpoint's
`equity` block carries the same sentence (`zero_edge_note`); no figure for the share lanes is stated. The screen's row
beside an equity trade (`fp`) carries S1-X's label as `s1x` (alpha or beta) and the lane's as `lane_label` (MARKET BETA
or EQUITY), never one `label`.

**Sizing up and demotion (pre-registered before the first live trade;** `league/equity/bands.py`, the rows in
`equity_money.sized` and `equity_money.demotion`**).** Fixed here before the first live equity trade, as coded. Both
rules read ONE PROGRAM VERSION's real record (`EquityRecord`, built by the book's `_record_of`): its closed real lots
in close order, each close's net return = its net cash (fees and dividends included) over its entry notional. The
bands move once a day, at the decision's band sync (never in the seating pass, never at send time).
- **Candidate to Probe**: a Candidate that passed its lane's sealed look takes a free roster seat (at most
  `probe.max_programs` live programs; who takes it is **The seat rule** above): a sleeve of `probe.sleeve_share` x E
  (the two numbers in force: **The seats and the sleeve** above).
- **Probe to Sized** (`sized_up`), when ALL hold, checked in this order (the reason recorded names the first that
  fails). **PARKED at the table in force**: `sized.min_trades` is 1000, so no equity program is Sized and every
  equity close stays inside the loss budget's tallies (**A20** above says why); the rule below is the
  rule as pre-registered, switched back only with a change that counts Sized closes in the budget:
  1. at least 20 real closes (`sized.min_trades` as pre-registered; 1000 in force);
  2. the closes have a spread (an sd above zero: closes with no spread at all never size up), their mean net return
     is above zero, and its one-sided 80% lower bound is above zero (`sized.confidence` 0.80: mean - t(0.80, n - 1) x
     sd / sqrt(n), sd the sample's);
  3. the version's summed net cash is above the same-risk buy-and-hold's over the same sessions (`sized.beat_bh`: a
     buy-and-hold that cannot be priced fails it);
  4. at least 5 whole sessions in its live band (`sized.min_probe_sessions`).
- **The same-risk buy-and-hold** (`_bh_pnl`): per symbol, the lots' average exposure over their span (entry notional
  x sessions held, over the span's sessions) held from the close before the first entry to the close of the last
  exit, at adjustment=all closes (total return). It is priced on ONE adjustment basis: the two closes are read from
  `eq_bars` only when one fetch wrote both, else read again in one request at the daily band sync once the record
  holds `sized.min_trades` closes; otherwise the figure is unpriced and `beat_bh` fails that day.
- **The Sized sleeve** (`sized_sleeve_share`, read from the record each time an entry is sized): quarter Kelly on
  that lower bound (`sized.kelly_fraction` 0.25 x the lower bound / the variance of the per-close net return),
  floored to four decimals of E, capped at 0.50 x E (`sized.sleeve_share`) and **never below the Probe's sleeve**:
  a Sized program never trades smaller than a Probe. As coded: max(the Probe's share, min(quarter Kelly, the cap)).
  `sized.sleeve_share` stays 0.50 at every pair of **The seats and the sleeve** (`set_design` does not move it: the
  floor is the Probe's in the code itself, and no Probe sleeve inside its bound is above 0.50). **Where the Probe
  sleeve is 0.50 (A20's design) the cap is the Probe's own share, so the answer is 0.50 x E for every record: a
  Sized program would keep the Probe sleeve and size nothing up; under a smaller Probe sleeve the rule could size a
  program up to 0.50 x E, one more reason the step stays parked.** The rule and its row are left as pre-registered;
  moving `sized.sleeve_share` is a later decision, with its bound. What Sized would still change: a lot bought while Sized
  carries no Probe mark, so its close joins neither the loss budget's realized figures nor the program's own -$300
  line; its open value still counts as open risk at the same weight.
- **Sized stays Sized**: no rule steps a Sized version back to Probe; it leaves its band only by EDM1 (or its
  family's retirement).
- **EDM1, the demotion** (`edm1`): the version goes back to Candidate, exits only, sticky for the version
  (`eq_sticky`: no later reading re-seats it), when ANY holds, checked in this order:
  1. at least 10 real closes (`demotion.min_trades`) and their summed net returns below -1.645 x sigma x sqrt(n)
     (`demotion.z`). **Sigma, in this order** (`edm1_sigma`): the per-trade net-return sd of the version's Validation
     run; else the sample sd of its own real closes once it has 10 of them (and that sd is above 1e-12: equal returns
     are no sd of their own); else the rule's fallback 0.02 (a net return of 2% of notional a trade: a round figure,
     chosen and not measured; a smaller sigma demotes sooner);
  2. its realized Probe net (the net cash of its closed Probe lots) at or below -$300 (`demotion.program_loss_usd`;
     the swarm's `elane.program_loss_usd` retires the family at the same line);
  3. its fills on average more than 15 bp a side BELOW their replay twins over at least 5 priced closes
     (`demotion.twin_gap_bp`, `demotion.twin_min_closes`; a twin gap is the close's live net return minus its
     twin's, in basis points a side). Fills better than the replay never demote.
  A demoted program's lots exit at the next open (the House's exit rule, A8.5). A record that cannot be read (a
  return or a gap that is not a finite number) moves no band that day and is reported.

**The equity identity** (the captain's A13). `equity_fingerprint` hashes the EVIDENCE modules of `league/equity/` only
(`league.swarm.evaluator.EQUITY_EVIDENCE`: `__init__`, `config`, `store`, `program`, `ctx`, `engine`, `results`,
`runner`, `synth`, `sizing`, `screen`, `child`: what Validation, the look and a live decision execute), the four shared
league files, the Gym modules they import, and THE CALENDAR'S THREE FILES (`EQUITY_CALENDAR_FILES`: `ltcm/__init__.py`,
`ltcm/broker.py`, `ltcm/data/__init__.py`: the NYSE calendar the store's session list and the ctx read; a holiday or
early-close rule changed there changes the sessions a Validation or a look runs over). **Treat those three as evidence
files: a byte changed in any of them moves the equity identity.** A change to one of them sends every live equity band
back to the Gym for fresh qualification (no new try, no new look: with its one look spent, a live program does not
come back). An adoption keeps each look's LINEAGE RECORD (the looked version's Train series and template): D3 goes on
binding later programs against every program already looked at, and where a looked-at program keeps no series the next
look writes it again from that program's Train-era runs or waits, never passing D3 unjudged. The PLUMBING is out
(`live`, `actions`, `schedule`, `families`, `bands`, `kinds`): a fix to the EquityBook, its clock, its corporate actions or its band plumbing retires no lineage. The cost
stated: nothing in the identity then proves the live path matches the Gym after such a fix; the I6 ctx test
(`test_equity_i6`) and the equity twins police it. `league/xs/` is the panel kind's slot (`kinds.KINDS["panel"]`): E1
shipped it with a `handle` that refused every op, and release E4 built the panel lane there (**The panel lane**, above)
without touching `league/live` (the options fingerprint) or the equity evidence modules; it has its own identity.

**Roll back: flatten first.** In order, each step verified before the next:
1. `elane.mode` "off" in swarm.json (no seeded birth, no equity look).
2. `equity_money.enabled` false (a CON change; the grant re-ratifies at the start): the book keeps running its exits only.
3. On the box (the House need not stop): `python3 -m league.live --root /workspace/state --flatten-equity "<why>"` (a
   reason is required). The command only writes a key-value (`owner_equity_flatten`); the book reads it first at its
   next minute, in the House's own thread, and runs `EquityBook.flatten` once: every open lot queued to exit at the
   next window through the normal order path (never a market order; the min hold stands, so a lot bought today leaves
   at the next open), recorded as `equity.flatten` with who and why. **The stock paper proof never holds a flatten
   past the entry cut-off (A28):** a flatten read inside the open window before 09:45 ET, on a day the proof's SELL
   stage has not passed, waits with every other exit until the 09:45 minute and is sent in it; read at any later
   minute it is sent in that minute, each time with the session's one "the sale path is unproven today" alert. A
   passed SELL stage holds nothing. `python3 -m league.live --root /workspace/state
   --status` shows the command under `equity.pending_owner_actions` until the House has read it (within a minute; it
   stays pending while the House runs no equity book, and on a minute the equity book skips). A flatten that fails
   keeps its key and is tried again the next minute. Run it again if a lot appears afterwards (a buy that was still
   working when it ran). Wait until health's `equity` line shows no lot held and no order working.
4. Only then `python3 scripts/floor_box.py rollback`. **The guard (A8.9):** `deploy` and `rollback` refuse a release
   that lacks the EquityBook (`EQUITY_BOOK_MARKERS`: `league/equity/live.py` `class EquityBook`) while the box's
   `live.sqlite` has an `eq_lots` row open or closing or an `eq_orders` row working (read-only). `--force-equity-risk` is
   the emergency path only: the older release's `_close_shares` market-sells every share at its first minute (a forced
   close, recorded as one) and its reconciliation freezes on them. Prefer fixing forward.
`STOCK_BUYS_REAL` "off" (a gateway var deploy) closes the gateway's route at any point; closes go either way.

**The equity freeze** (`eq_freeze` in live.sqlite's kv, A8.10). The book sets it, with an error alert, when an activity
it cannot book touches a held symbol: any type outside the dividends and corporate actions it handles, or a rename.
While it stands, `real_block` refuses every real OPEN IN BOTH LANES (options opens too) and the equity book opens
nothing; exits go on. **It never lifts itself.** The owner books the action by hand (the lot's quantity, entry price or
symbol), then on the box: `python3 -m league.live --root /workspace/state --clear-equity-freeze "<why>"` (a key-value,
`owner_equity_clear_freeze`, which the book reads at its next minute: it deletes `eq_freeze` and records who cleared it
and why, `equity.freeze` with `cleared: eq_freeze` and the old reason; opens go again in the same minute). The
reconciliation's own freeze (`eq_recon`, shares held that the book does not explain) is a different one: the command
never lifts it, it lifts itself after two clean readings and needs no command.

**The gateway's stock route as the House sees it** (the gateway README's House-side note, kept here: `gateway/` ships on
its own). The book sends `limit` `day` orders in shares (fractional, six decimals sent; the venue takes nine), never a
notional, market or stop order, with client ids `lq-<nonce>-<eid>-<family slug>` (the state's nonce first, as the
options book's `lv-<nonce>-...`: a rolled-back state never repeats an id the venue has seen; `league/live/real.py`
`ingest` skips every `lq-` id: never a foreign order). A buy is a marketable limit at the ask x (1 + collar), a sale at
the bid x (1 - collar). Each row is written `pending` before the POST; a lost answer is `unknown` and is looked up by its client id, never re-sent blind.
The gateway's answers the book reads: `403 {cap}` (`stock_order`, `stock_position`, `stock_day`, `stock_total`,
`buying_power`): a refusal recorded on the order; `503 equity` (Retry-After 30), `424 orders`, `424 positions`: the
account or its book could not be read, nothing sent; `409 stock_close`: a second close of the same shares in flight;
`423`: the kill switch, buys and sells alike. `503 equity`, `424 orders`, `424 positions` and `409 stock_close` say
nothing was sent and nothing was judged (`RETRY_CAPS`): the book sends the order again at its next minute until the
window's cut-off. They never end an entry and never count toward the three refusals that carry an exit to the next
session; after three in a day on one lot the owner is told once and the exit keeps going each minute. An order
refused before the venue widens no collar. A `403 {cap}` is a verdict: an entry ends refused, and three on an exit in
a session carry it to the next open. A buy is an open for the shared day counts (`MAX_DAY_OPEN_ORDERS` 250,
`MAX_DAY_ORDERS` 300, both books together). The gateway's caps (50% of equity an ETF, 20% a stock, the margin line,
buying power, 4x equity of buys a day) are the backstop under the House's tighter rules, never the rule the House sizes
to. `/v1/health` `stock_buys` shows the switch, the shares, the day's buys and the buys in flight.
**Against the one-ETF lot** (half a Probe sleeve; the gateway reads the account's equity, and E is never above it):
one order and one ETF's position are under the gateway's 50% at any sleeve inside its bound; the lane at its invested
cap (1.00 x E) is at the gateway's book line on a multiplier of 1 (1.00 x equity), which the House's $50 cash reserve
keeps it under; and the gateway's day line counts every buy it admits, a cancelled one too, so it admits 4 over the
lot's share of E sends of such a lot a day: sixteen of a lot of 0.25 x E (A20's), twenty-four of 0.165 x E,
thirty-two of 0.125 x E. Every seat's entry sent once uses a quarter of the line at most, at any pair. An entry can
climb the collar's whole ladder of five sends; how many entries can do that on the same day is that count over five
(three, four, six), and a send past the line meets `stock_day` and ends its entry refused: missed, never chased, and
nothing sold. **The seats and the sleeve** (in the equity lane's section) states both counts at the pair in force,
and `league/tests/test_ci.py` holds the figures to the release's own gateway files (`DAY_LINE` by sleeve;
`WHOLE_LADDERS` names the pairs whose every seat can climb the whole ladder on one day).

## Real stock and ETF buys at the gateway (Oct 10, 2026): deployed 21:18Z Oct 10 (gateway `3cc811b0`, #532)

The owner's goal of Oct 10, 2026: agent programs may trade ETFs, stocks and options with real money. An ETF position at
most 50% of equity, a single stock at most 20%, at most 100% of equity invested in total, or up to the venue's overnight
margin limit (2x) where the account offers margin; never margin for a short sale; no short sales; the kill switch, the
daily stop and the drawdown stop stay; no hidden costs. This branch is the gateway half: the boundary that holds
whatever the House sends. **No House code sends a real stock buy yet**: until a House release does, deploying this
changes nothing the floor does, except that every real stock close now reads the positions fresh and is serialized in
the Gate (below).

**Before the House sends its first buy**: the running House sells EVERY stock position on the real account at market,
on every activities pass (`league/live/step.py` `_close_shares`, written when the only stock it could hold came from an
assignment or exercise), and while any stock is held the assignment latch never lifts (`_stock_held`). A share bought
through this route would be sold at market on the House's next pass: a round trip of spread for nothing, against the
owner's "no hidden costs". The House release that first sends a real stock buy must, in the same release, limit
`_close_shares` (and `_stock_held`) to assignment and exercise shares, for example only while `assignment_latch` is set
or only for symbols tagged as assigned. Until it does, `STOCK_BUYS_REAL` "on" is harmless only because nothing buys.

**What the real account admits now** (`gateway/lib/caps.mjs` "stock and ETF buys on the real account", `router.mjs`
`realStockBuy`, `gate.mjs` `reserveStock`), while `STOCK_BUYS_REAL` is `on`:
- **A BUY of a listed symbol the account does not hold short**: `STOCK_UNIVERSE`, 17 ETFs (SPY QQQ IWM DIA; XLB XLC XLE
  XLF XLI XLK XLP XLRE XLU XLV XLY; TLT GLD) and 18 large US stocks (AAPL MSFT NVDA AMZN GOOGL META BRK.B JPM V UNH XOM
  JNJ PG MA HD AVGO LLY COST). Anything else is a `400`. The list is code: a change is a reviewed pull request and a
  gateway deploy.
- **Its shape**: `type` `limit` with a positive `limit_price` (at most four decimals), `time_in_force` `day`, `qty` in
  shares (fractional to nine decimals; no `notional`), no `position_intent`, `extended_hours` true or false. A notional,
  stop or option-intent buy is a `400` before anything is read; a market, good-till-cancelled or unlisted buy is a `400`
  once the positions (read first, as for every real stock order) show it is not a cover, before the account is read.
- **Its price**: `qty x limit_price`, rounded up. A buy fills at its limit or better, so nothing it spends is above it.
- **Its caps**, read fresh from the account by the gateway itself (`GET v2/orders?status=open`, then `GET v2/positions`,
  then `GET v2/account`, each with the real keys, read-only: in that order a buy that fills between two reads is counted
  twice, never not at all), judged in the Gate's single step that reserves:

  | Cap | Refusal (`403 {cap}`) | Rule |
  |---|---|---|
  | one order | `stock_order` | `qty x limit` at most `STOCK_ETF_EQUITY_SHARE` (0.5) of equity for an ETF, `STOCK_SINGLE_EQUITY_SHARE` (0.2) for a stock |
  | one position | `stock_position` | the symbol's long market value + its resting buys (unfilled part) + buys in flight + this order, at most the same share |
  | the day | `stock_day` | today's real stock buys (every one admitted, a cancelled one too) + this order, at most `STOCK_DAY_EQUITY_MULTIPLE` (4) x equity: a gateway backstop under the House's daily and drawdown stops (which live only in House code) against a looping release or a leaked runtime token |
  | the book | `stock_total` | a MARGIN line, m = min(`STOCK_MAX_EQUITY_MULTIPLE` (2), the account's `multiplier`): every long stock and ETF position's market value + every resting stock buy + buys in flight + this order + every long option (and any other long the venue lends nothing on) counted m times, at most equity x m. That is Reg T's overnight line, `stocks / m + options <= equity`: 100% on a cash or limited-margin account (multiplier 1, which is also what an unreadable multiplier reads as; options count once), 2x on Reg T margin, and 2x overnight on pattern-day-trader margin (4) too, with options held |
  | buying power | `buying_power` | buys in flight + this order at most the LOWER of the venue's `buying_power` and its overnight `regt_buying_power` (both net resting orders). On pattern-day-trader margin `buying_power` is the intraday figure, 4 x (last equity - maintenance margin), which bounds nothing held overnight |

  The four numbers are **ceilings in the code**: a var can only lower them (`"0"` closes the route); above a ceiling
  or malformed reads as the ceiling. Equity and buying power are rounded down, every cap rounds down, and the order's
  price and the options' extra weight round up. A House that reprices a buy (cancel and send again) spends the day's
  cap each time: price to fill.
- **Buys in flight**: the Gate holds each admitted buy for `STOCK_LEDGER_HOLD_MS` (60 s) after its forward is answered
  (the venue's account and positions can lag an order's status); one whose answer never came, for two minutes from
  admission. So a burst of buys cannot pass a cap between two readings, and a buy that fills while the account and
  positions lag is still counted. One the open orders list by its `client_order_id` counts once, the larger of the two.
  A held buy or close is let go early only on a definite answer (the House's cancel-then-resend re-prices every 30 s in
  the close window): a submit the venue refuses with a 4xx other than 408 placed nothing and counts nothing from then;
  and each check reads, by `client_order_id` (`GET v2/orders:by_client_order_id`, read-only, at most 10), the held
  orders the open orders do not list: one `canceled`, `expired` or `rejected` counts only what it filled (shares the
  positions may not show yet), learned once and never read again; one `filled` keeps its whole hold. A read that fails,
  a 5xx, a 408 or no answer keeps the whole hold, and an order sent with no `client_order_id` can only wait it out.
- **It is an open for the day's counts** (`MAX_DAY_OPEN_ORDERS`, `MAX_DAY_ORDERS`) and the kill switch stops it (`423`).
  It never spends the options' opening maximum loss (`MAX_DAY_USD_ALPACA`): the stock book has its own caps.
- **Fails closed**: an account that cannot be read (or has no equity or `buying_power`, or a margin account, multiplier
  above 1, with no readable `regt_buying_power`) is `503 {cap: "equity"}` with `Retry-After: 30`; open orders that cannot be read, a full page of 500, or a resting buy with no limit price (a market
  or stop buy) is `424 {cap: "orders"}`; positions that cannot be read, or a long row with no `market_value`, is
  `424 {cap: "positions"}`. Nothing is reserved or sent.

**Closes, read fresh and serialized** (the review of Oct 10, 2026): a SALE is only ever the close of shares held long,
at most `qty_available`; a BUY of a symbol held short is only a cover, at most the short (`realStockClose`, exits, no
account read). Every real stock order now reads the positions FRESH (never the router's per-isolate cache, which could
still show shares another isolate sold or a short it covered, and so pass a short sale, or a buy as a "cover" past every
stock cap), and the Gate keeps each admitted close in the same in-flight ledger as the buys (`gate.mjs`
`reserveStockClose`). A close reads the open orders, then the positions (an order that fills between the two reads is
counted in both, never in neither), and what is free to close is the lower of `qty_available` and the position less the
open orders on its side (`caps.closeAvailable`). Each admitted close is held `STOCK_LEDGER_HOLD_MS` (60 s) after its
answer, two minutes with none (the design review of Oct 10, 2026: the venue's positions can lag a filled sale while its
order has left the open list, and until then a close was let go after 5 s, so the same shares could be sold again, short).
From the oldest close held, every close since counts as the LARGER of what they ask together and how far what is free has
fallen since that oldest one was admitted (it records what was free then): a close the venue shows, open or filled,
counts once; one it does not show yet still counts; and a fill of an older order (already out of what was free) hides
none. A close is admitted only when its qty is at most what is left. Two sales of the same shares, through one isolate or
two, cannot both go: the second is `409 {cap: "stock_close"}`, nothing sent (the House reads a 4xx as a refusal and
sends it again later). A close with a definite answer is let go early as a buy is (above, **Buys in flight**): refused
with a 4xx, or read done by its `client_order_id` with only what it filled still held. Open orders that cannot be read,
a full page of 500, or an open order on the close's side with no `qty` is `424 {cap: "orders"}`. No order is ever a
short sale, so margin is never used for one, and no buy both covers and opens. With `STOCK_BUYS_REAL` anything but `on`, a real stock buy is what it was (a cover or a `400`). Crypto
stays refused. The practice account (`alpaca-paper`) is unchanged.
**Margin interest** on a margin account is the venue's charge on borrowed cash: the gateway does not meter it, so the
House's economics must count it (no hidden costs).

**Health**: `/v1/health` carries `stock_buys`: `enabled`, the three shares, `day_equity_multiple`, the list,
`day_buys_usd` (today's buys at `qty x limit`), `in_flight`, `in_flight_usd`, `closes_in_flight` (stock closes not yet
answered) and `buys_admitted` (the switch, the kill switch and the day's open-order room; the caps themselves are judged
per buy against a fresh reading).

**Deploy** (an owner deploy, gateway only; no House change, no money digest, no ratify): `cd gateway && npm run check &&
npm test`, then `npx wrangler@4.129.1 deploy` in the money path's window, then `python3 scripts/gateway_admin.py status`
(the kill switch as it was) and `/v1/health` itself with the runtime token (`gateway_admin.py status` prints neither
block): `stock_buys.enabled` true, the shares `0.5`, `0.2`, `2`, `day_equity_multiple` `4`; `max_loss` unchanged. **Roll back**: `STOCK_BUYS_REAL`
`"off"` and deploy (closes keep working), or `npx wrangler@4.129.1 rollback` to the previous version. A stock position
bought before a rollback stays on the account and is closed by an ordinary sale (closes go either way).

## The no-captain automations (Oct 10, 2026): deployed 21:42Z Oct 10 (House `20261010T214125Z-d4667186f969`, gateway `e3f310ee`, #533)

Built on `feat/no-captain` and deployed 21:42Z Oct 10: one gateway deploy, then one owner deploy (`league/ops/budget.py`,
`league/ops/budget_refresh.py` (new), `league/ops/registry.py`, `league/ops/stall.py`; `gateway/lib/email.mjs`,
`gateway/lib/gate.mjs`).
Nothing in `league/swarm/`, `league/live/`, `league/gym/` or `league/constitution.py`; no evidence rule moves.

- **Why.** The owner's Done needs "research runs 24/7 at budget with no captain" (DONE-RULE item 7, read by
  `dlane_report.Research247`). From Oct 7 15:44Z to Oct 10 19:40Z the captain intervened by hand 59 times: 18
  `swarm.json` edits, 11 agenda installs or reverts, 7 budget runs or hand edits of `budget.json`, 17 owner deploys and
  5 gateway deploys, and push notes asking for top-ups. Most were found by reading the log, never by an alarm. These
  four changes take over the ones that recur, ranked by recurrence times their cost to item 7.
- **The top-up raise and the hourly refresh** (`budget.py` `compute` and `refresh`; the new `budget_refresh` job,
  hourly at :35 and at each House start). The day's figure was set once: on Oct 9 a top-up at about 14:29Z left Sail
  research tapered until 00:30Z, and the captain ran the job by hand (once without the House's environment, which
  wrote Claude $0), edited `budget.json` by hand, saw the run after the close put the old figure back (research,
  births and the architect stopped), and ran the job again because the stale ceiling knob held births at 16. Now a
  run whose own reading would set more raises the day's figure to it (raise-only, never above the ceiling, from the
  reading as it stands, `raised_from` and `raised_at` recorded; the knobs and the guard's caps follow at the swarm's
  next loop), and `budget_refresh` reads the meters every hour, writing `budget.json` only when it raises a meter or
  sets a day's first figure. It never lowers a figure, never writes a meter it could not read (the full job's runs
  fail closed, as before), and sends no notice; with no usable file (none, another rule's after a deploy, stale) it is
  the full job, so a deploy that changes the rule no longer waits for 00:30Z or a run by hand. A raise is never bought
  by a fallback: the day's figure keeps the fixed cost and reserve it was set or last raised on (`fixed_usd_day`,
  `reserve_usd`), and a raise is computed on the larger of those and the reading's own, so a failed box-spend read
  (fixed cost back to `guard.house_burn_usd_day`) raises nothing. The figure also keeps the day's first figure and
  every raise (`set_usd_day`, `raises`), which `underspend` prices hour by hour. What it does not fix:
  a day whose first run tapered is still a taper day for item 7 (every `budget` receipt of the day must say
  `ceiling`); only a top-up before the taper saves it.
- **The births jam and the birth yield** (`stall.py`). From the `swarm.architect` events (`architect_tally`): a jam
  (no birth for 6 h while at least 4 passes wanted births: asked a model, found no cell or failed) is now the
  `births` cause with the owner's step at once, naming the main way the passes bore nothing and its lever (an agenda
  through `scripts/agenda_install.py`, `architect.max_rebirths_per_cell`, `architect.max_alive_per_class`, the effort);
  the new `birth_yield` cause (INFO) stands earlier: over 3 h at least 4 passes asked a model and bore at most 1, or the
  card checks refused 80% of their proposals, or no birth in 2 h while 3 passes wanted one. Its numbers count the
  refusals by kind, the incomplete cards' top fields and the rebirth rows pointed at. Nothing loosens the graveyard or
  the card rule by itself. Only a jam a setting or an agenda clears is the owner's step (incomplete cards, the rebirth
  rule, a spent lineage, a cap, no open cell, cut answers); failed model calls (a provider's outage, a poll's timeout)
  heal by themselves and stand as the jam's INFO. The captain caught the graveyard wall of Oct 10 15:41-16:22Z (births
  0/0/0 under agenda v21.4) inside 41 minutes and reverted it at 16:24:59Z; none of these causes would have stood that
  soon. With nobody reading, `birth_yield` would have stood after two dry hours (INFO, mailed at once as a new cause)
  and the jam would have been the owner's notice after six.
- **The swarm's alerts reach the owner** (`stall.py` `swarm_alerts`). Sixteen kinds of `swarm.status` alerts
  (`reader_cut`, `agenda_guard`, `gate_coverage`, `gate_missing_data`, `train_span_pending`, `look_failed_three_times`,
  `game_waits`, `policy_layer`, ...) went only to the swarm's record and the private ledger: the captain found the Sail
  reviewer cutting 4 of 6 gate reviews (a lineage's one try lost) by hand. The cause lists each kind with its count,
  last time and own sentence; the kinds only a setting or a fix clears carry the owner's step (`ALERT_STEPS`), read
  from the state where the swarm keeps it (`stall.alert_states`): `reader_cut` while it fired this UTC day and
  `gate.review_max_output_tokens` is no higher than the cap it met; `agenda_guard`, `policy_layer`,
  `train_span_pending` and `game_waits` from the settings as the swarm loads them; `gate_coverage` from the pool's
  record of the configured gate image; `train_span_mismatch` and `gate_missing_data` while their latest alert (7 days
  back) names the configured image. The swarm raises most of these once, so a kind stands while its condition does
  whatever its alert's age, and clears at the next stall run once it is fixed (a fix before midnight does not fail the
  next day). `look_failed_three_times` is not read: an owner step on the UTC day it fired only. The rest are INFO over
  12 h, and a Sail window's fallback (`sail_window_stall`) and the funding watch's cliff never stand by themselves.
- **Research under its budget, and the settings that bind it** (`stall.py` `underspend`, INFO). Item 7 reads a day with
  no taper as at budget, so a `swarm.json` pin under what the dollars buy was invisible (Oct 9: `gym.max_boxes` 2 under
  the budget's 7, half the paid Gym idle). The cause stands when Sail's booked research today is under 70% of what its
  day's figure buys by now at the guard's even pace (each top-up raise counted from its hour; read from 6 h into the
  day, not while the guard braked 2 h or more), or when two settings that cannot both hold bind. Claude's reading is
  said beside it but never stands by itself: its figure is spent by its roles' calls as the gate and the strategist
  have work (the release sets the architect's and the researchers' lines to 0), never at an even pace. It names every
  setting that binds (`settings_binds`): a cap under the budget's knob (`gym.max_boxes`,
  `researcher.sail_usd_per_hour`, `population.ceiling`, a slower `architect.every_seconds`, `population.start` under
  the ceiling), a conflict (`architect.max_alive_per_class` times the direction lane's classes under
  `dlane.max_alive`: the class cap binds the lane first; an architect Claude line above 0 but under one call's $2
  hold), a value under the release's own (`researcher.dormant_cycles`, `architect.max_refill` under what `policy.json`
  sets: the release's own 12 and 6 are no drift), and the Claude lines at 0. The committed `policy.json` itself holds
  the class-cap pair (12 against 24, one class): it is named, and stands by itself only once the architect's passes of
  the last 6 h met the class cap (`lane_class_capped`); the architect-line conflict always stands.
- **Item 7.** The jam's owner step and the `swarm_alerts` owner kinds are owner steps, so a day on which one stood fails
  item 7 ("an owner step waiting"): such a day needed a human. `birth_yield` and `underspend` are INFO and fail nothing.
- **The notice's pace.** A stall needing nothing from the owner was mailed at most once a day after the last notice of
  either kind, so one cause standing for days held every new one back up to a day (`birth_yield`'s early warning among
  them). Now a cause no notice told in the last 24 hours is mailed at once (`stall.json` `mail.told`), the same causes
  at most once a day; the gateway keys such a notice on its causes (`stall:info:<causes>`, 24 h) instead of one
  `stall:info` key.
- **Deploy order.** (1) The gateway (`cd gateway && npm run deploy`): `gateway/lib/email.mjs` has the words for
  `birth_yield`, `swarm_alerts` and `underspend` and the `stall:info:<causes>` key (`gateway/lib/gate.mjs` keeps it
  24 h); a cause it does not know makes the whole stall notice a 400 (nothing mailed), and an older gateway answers a
  new cause's notice as a duplicate of the day's `stall:info` (tried again each run until the day is out), so the
  gateway goes first. (2) One owner deploy of the House at the branch head. The runner starts `budget_refresh` from the
  deploy (a new job is never `missed` for the days before it).
- **Verify after the deploy** (read-only): an `ops.sqlite` `budget_refresh` receipt at the House's start and every hour
  at :35 (`written` false with its `why` on a quiet hour); the next `stall` receipt's `checks` has `birth_yield`,
  `swarm_alerts` and `underspend` with their numbers (`underspend` `conflicts_binding` 0 on the release's settings);
  `stall.json` `mail.told` after the next notice; after the next top-up, `budget.json`'s
  `meters.<meter>.day_figure.raised_from` within the hour and the swarm's `budget.knobs` following it.
- **Rollback.** The previous House release: its `budget` job reads the raised `day_figure` as the day's figure (the
  extra keys are ignored), its stall job ignores the new causes and `mail.told` in `stall.json`, and the runner never
  starts the unknown `budget_refresh` job. The gateway's extra words are harmless to an older House, which mails a
  stall needing nothing once a day by its own pace whatever key the gateway keeps.

## The always-in card (Oct 10, 2026): deployed 18:00Z Oct 10 (#529)

Built on `fix/always-in-v2` (the second cut; the first, PR #528, was closed on its review), not deployed: one owner
deploy (`league/swarm/cards.py`, `dlane.py`, `architect.py`, `researcher.py`, `tournament.py`, `league/ops/stall.py`
and `league/ops/dlane_report.py`; nothing in `league/live/`, `league/gym/` or `league/constitution.py`). A reported
loosening (the `dlane` report's LOOSENED row) with a behavioural check beside it.

- **Why.** The direction lane trades labelled index beta: calls on SPY, QQQ or IWM held 2-8 sessions. By Oct 10 its
  graveyard cells held 22-43 rows refuted on Train, every one a gated idea (an implied-vol, term-structure, trend or
  open-interest gate). An always-in card (it enters on the clock alone: the lane's own instrument) read the clock, so it
  matched those rows, and it could make no rebirth claim (a claim adds an input the dead row did not read). Direction
  births were about zero and the Probe roster (5 seats, 1 filled) could not fill.
- **The status is declared.** A direction card whose DECLARED inputs are exactly `["clock"]` is always-in
  (`dlane.always_in`). `dlane.card_errors` asks it to say so in words no gated card uses ("always-in" or "no gate" in
  its comparison or falsification; "every session" alone is every direction card's comparison), to name no gate,
  signal or filter switched off, and to leave ablation out (it has no gate to switch off). A dead row is always-in
  when its family's declared card was (its own card, or a fork's by `card_sha`), never by its words, unless its program
  never behaved always-in (G1 refused its version due for Validation, or every version on record failed G1, and it held
  no try).
- **The graveyard** (`cards.RebirthIndex.check`, its direction path only, while the lane is on). An always-in card is
  bound by the always-in direction rows on its roots (the roots each row's family traded or was born on), whatever
  their class or holding, and by no other row; no claim frees it, and a claim it carries is dropped. A DRIFT row still
  binds no direction card. `cards.matches`, `matched`, `text_cell`, the mechanism test's `mechanism_lineage` and the
  memory judge are unchanged: alpha cards (legacy rows included) and gated direction cards are judged as on main.
- **One idea a root** (`architect.admit`). An always-in birth links its lineage to every always-in direction lineage on
  each of its roots (`cards.always_in_families`, `store.link_lineages`), alive or dead, and continues no other: its
  parent and twins, declared or by words, are read among those always-in families alone, so a gated lineage's spent
  try never refuses it and a gated lineage is never merged into a root's always-in try. The ration at birth
  (`dlane.birth_spent` with `living`) reads those lineages with or without a parent, and every living member of them
  claims the try, best or not, so a living always-in family on a root refuses the next always-in birth there. An
  always-in family trades only the roots it was born on (`researcher._admit` refuses NEEDS naming another) and never
  forks (`tournament.lane_forks`). So each root's always-in beta has ONE Validation try and one holdout look, ever,
  while `dlane.val_tries` is 1: at most three in all (SPY, QQQ, IWM), fewer once a family on two roots joins two of
  them.
- **The behavioural check, G1** (`dlane.always_in_entries`), on each 1.0x Train run of an always-in family, over the
  Train years and on each root it traded, in three parts:
  - entries: a root on which it held two or more positions at the open of 10% or more of its sessions is a ladder,
    and must have entered on 90% of ALL its Train sessions (a ladder can always add one; the review's probes, gated
    ladders holding 2-8 sessions, were never flat and passed the flat reading; its cost: a program that opens its
    next call a session before the last one's exit session reads as a ladder, so the brief says to roll on the exit
    session itself); any other root on 90% of its flat sessions (none held at the open), and one flat on fewer than
    20 held a position at nearly every open, which passes this part;
  - size: 90% of its entries' maximum losses within 3x of their median, either way (the same contracts each entry
    vary with the premium inside it; a gate on the size does not);
  - hold: 90% of its closed trades held one session or more and within 2x of their median hold (a same-session exit
    while a gate is off is not a hold).

  It reads only the trades' days, exit days and maximum losses and the run's sessions, which every Train result carries
  (the mechanism test runs on a quarter of families, in shadow), works for any hold, and a gate on the entry (implied
  vol, trend, weekday, month-end), on the size or on the exit leaves a mark in one of the parts. A failing version is
  ineligible (`train_score(..., always_in=True)`, fails `G1`, kept in the compact score). The tournament validates an
  always-in version only with a G1 pass on record (`dlane.always_in_try`; `always_in_refused` in the round, which the
  stall check reads); a family whose version due for Validation was so refused, and that holds none of its lineage's
  tries, retires in `_why` after the ration (`dlane.always_in_failed`, an IDLE death: no row of it binds, it spent no
  try). A G1 failure of any other version (a sweep variant, a version written after the try was sent) only makes that
  version ineligible, and a spent try retires on the ration's own cause, so its verdict binds. What it cannot see: a
  gate that only tilts inside the bands (a size that halves, a hold between 4 and 6 sessions, a strike that keeps the
  risk in band).
- **The view.** The architect's system prompt (`LANE_SYSTEM`), the BIRTH CELLS' header (`LANE_CELLS_NOTE`) and their
  last line (`cards.ALWAYS_IN_LINE`: each lane root open, bound by an always-in row, or its always-in try spent or
  claimed, a living member's claim included, read as `admit` reads it) say the rule; `Architect.closed` reads a lane
  root still open to an always-in birth as a pass that can bear one. An always-in family's card brief says G1 and that
  it trades only its birth roots. The golden prompt pins are unchanged (the ALWAYS-IN line is added only to a list that
  has a cell).
- **The cost.** At most one always-in Validation try per root, each the lane's D2 lottery at 10.37% per program at zero
  edge on mixed worlds (12.39% on 2022-24 worlds; higher when the screen windows rose); profit is index beta minus
  option costs, beside the same-risk buy-and-hold. A self-refuted or refuted always-in family closes its root's
  always-in for good (no claim can free it).
- **Rollback.** Redeploy main before it; nothing it writes needs undoing (links between always-in lineages stay, and
  only join tries that would have counted against the same idea).

## The Probe total at $800 and the program line at -$300 (Oct 10, 2026): deployed 05:36Z (money `fdf2ac7c`, grant ratified 05:37Z)

Built on `feat/probe-total-800`, not deployed: one owner deploy (`league/constitution.py`, `league/swarm/policy.json`
and `league/swarm/dlane.py`, whose line bound is the -300 default). Claude's decision, pre-registered privately as
PREREG-T on Oct 10 under the Probe roster R5 already live, inside the owner's goal as he re-set it on Oct 9, item 4:
"Probe loss budget: $400 net in any rolling 20 sessions and $800 net in total".

- **The rule.** `options_money.probe.loss_total_usd` "400" -> "800", the owner's ceiling (a loosening), and the program
  loss line (DONE-RULE-A1 A1.3) `dlane.program_loss_usd` -200 -> -300 (a second loosening), its bound in `dlane.cfg`
  its default, -300 to -25 (a setting can still only tighten it). The Done meter's zero-edge figure moves with them:
  `dlane.done_zero_edge_p` 0.024 -> 0.027 (`dlane.ZERO_EDGES` labels both, `dlane.ZERO_EDGE` is the one in force).
  Unchanged: the rolling $400 in any 20 sessions, the 10% cap, `open_per_family` 3, `max_open` 8, DM1, the kill switch,
  the daily stop and the drawdown stop. Open Probe risk stays at or under $400 (the window's envelope alone caps it), so
  `money.probe_room` is unchanged. A Probe open must fit the window's $400 and the total's $800; a bad 20-session
  stretch that ages out of the window now leaves room in the total for a second before any Probe gain refills it.
- **It holds at roster 5 only.** PREREG-T measured the pair at `dlane.roster` 5 and nowhere else. At no roster the
  operator's grid found the $800 total almost all cost (+0.11 points of Done for +37 points of the chance of a net below
  -$400), and the House's population ceiling makes no roster behave like a roster near 24, where no one measured the
  pair either. The roster moves by a `swarm.json` setting with no deploy; the pair needs the owner's deploy. So a roster
  rollback (`dlane.roster` 0) or any other count needs the pair's rollback too (below), or a new measurement first.
  Until then the `dlane` report raises **PT1** on every run with the lane on (a warning, so the `stall` job's `dlane`
  cause mails it). The 0.027 zero-edge figure is roster 5's as well.
- **Measured** (the operator's simulation, three paired arms: cross-fit, fixed 2-, 3- and 5-session holds standing in
  for the House's pool, roster 5, arrivals; what it trades is index beta minus option costs, not alpha). "The running
  real net" is the agents' Probe/Sized route and the incubator together, not the Probe alone:

  | | $400 total, -$200 line | $800 total, -$200 line | $800 total, -$300 line (adopted) |
  |---|---|---|---|
  | P(Done) at 12 weeks | 4.6% | 5.3% (paired +0.68 points, SE 0.11) | 5.5% (+0.92, SE 0.15; +0.24 over the middle, SE 0.12) |
  | P(Done) at 24 weeks | 11.6% | 14.2% | 14.4% |
  | P(Done \| zero edge) at 12 / 24 weeks | 2.2% / 6.9% | 2.5% / 8.3% | 2.7% / 9.0% |
  | P(the running real net below -$400 within 12 weeks) | 17.8% | 35.8% | 36.8% |
  | P(the running real net below -$600 within 12 weeks) | 0.6% | 4.1% | 4.4% |
  | 12-week net: 5th percentile | -$396 | -$674 | -$679 |
  | 12-week net: mean / median | +$22 / -$327 | +$28 / -$230 | +$25 / -$231 |
  | P(the 60% drawdown stop trips by 24 weeks) | 21% | 46% | 48% |

  PREREG-T's rule preferred the $800 total alone unless the -$300 line beat it by more than 2 paired SE; it did by a
  hair (2.06 SE).
- **The cost:** about one point of 12-week Done and three of 24-week Done, bought with twice the chance of a running
  real net past -$400 within 12 weeks, about seven times the chance past -$600, and more than twice the chance that the
  account's drawdown stop trips by 24 weeks. Most of it is the total's: the line's own step adds a point to the -$400
  figure, 0.3 to the -$600 one and 1.6 to the drawdown stop's for its 0.24 points of Done. A Done with no edge at all
  becomes more likely too: 2.7% within 12 weeks and 9.0% within 24 (2.2% and 6.9% before), against 5.5% and 14.4% as
  traded. A program may lose $300 of its own realized Probe net before the `dlane` job retires it, $100 more of the
  shared total than before. The `dlane` report lists both rows among its loosened rules with these costs (`LOOSENED`).
- **Identities.** Money digest `0310779c` -> `fdf2ac7c`; constitution digest `ca89ff8a` -> `0adb4f0e`. Nothing under
  `league/live/` or `league/gym/` changes: the execution fingerprint (`31a7e921`), the Gym bundle and the gate contract
  (`397b22b772b3`) do not move, so no evidence reset and no band lost. So `league/live/money.py`'s docstring still
  reads "$400 as set on Oct 9" for `probe.loss_total_usd`: the code reads the constitution's figure, and the words wait
  for the next `league/live` release (editing them alone would move the fingerprint and reset the evidence).
- **The owner's deploy.** (1) CI green on the exact head; no order in flight; never 12:55-20:05Z on a trading day;
  `dlane.roster` 5 on the box. (2) `floor_box.py deploy` from `~/Work/ltcm-deploy`. (3) At the House's start the `grant`
  job re-ratifies on `fdf2ac7c` by itself (receipt `ratified`, trigger `digest`; `python3 scripts/live_trading.py
  --ratify` on the box if it refuses); until then no real entry. (4) Verify: `fast-lane-report.json` `probe_budget`
  reads `budget_usd` "400" and `total_budget_usd` "800"; the next `dlane-report.json` reads
  `probe_envelope.total_budget_usd` 800, `program_loss.line_usd` -300 (a `dlane.program_loss_usd` in the state root's
  `swarm.json` overrides it, held to -300 to -25), `done.p_done_zero_edge.value` 0.027 with no `note`, `roster.seats` 5
  and no PT1; the House's `research_evaluator` keeps `31a7e921`.
- **Roll back** (all of it in one owner deploy): `league/constitution.py` `loss_total_usd` "400" (re-pin
  `PINNED_DIGEST` to `ca89ff8a...`); `league/swarm/policy.json` `dlane.program_loss_usd` -200 and
  `dlane.done_zero_edge_p` 0.024; `league/swarm/dlane.py` the same two in `DEFAULTS` (the line's bound is its default,
  so -200 is the bound again and a setting may again only tighten from it) and `ZERO_EDGE = ZERO_EDGES[0.024]` (the
  report then shows A1.2's figure with its own horizon, holds and source). The money digest goes back to `0310779c` and
  the grant re-ratifies at the House's start; no fingerprint move; PT1 goes quiet. The tests that pin the $800 rules
  (the CHANGELOG entry's Proof list) move in the same commit. A tighter line alone needs no deploy:
  `dlane.program_loss_usd` -200 in the state root's `swarm.json`.

## The ration at birth (Oct 10, 2026): deployed 06:20Z

A direction card whose birth would continue a lineage that has already spent its one Validation try or its one holdout
look is not born (`league/swarm/dlane.py` `birth_spent`, asked by `league/swarm/architect.py` `admit` before
`add_family`). The lineage read is the one the family would join: its parent's (a declared parent on the slice, else the
newest dead family of the same idea on the slice, else a living twin) and, for a `long_single`, every twin lineage the
birth links; their connected component, as `lineage_tries` and `lineage_looks` read it once the family is born. A prior
lineage (a new idea on a dead slice) is not in it. Nor is a card born when a living Gym-band member of that component
already claims the try: one born earlier in the same pass (a truncated answer's retry included), or one whose best
awaits Validation (`researcher.awaiting_validation`: its Validation job may be out, with no run landed yet). The card
becomes a card refusal: the next request lists it under "YOUR LAST PASS'S PROPOSALS REFUSED BY THE CARD CHECKS",
naming the lineage that holds the try and the version that spent or claims it, and the pass's `swarm.architect` event
counts it in `card_refused.spent_lineage` (apart from `rebirth`).

- **Why:** on Oct 10 about half of the lane's births joined such a lineage, and the tournament retired them on
  `SPENT_TRY` 15-60 minutes later without a try: research money, Gym runs and a population slot each, and the architect
  never learned why. The false-positive accounting is unchanged: one try a lineage, and a re-proposed idea still gets none.
- **Read it:** `card_refused.spent_lineage` in the `swarm.architect` events; kv `architect_card_refusals`. `SPENT_TRY`
  retirements of newborns should fall, though not to zero (below).
- **Unchanged:** alpha cards and the lane off (`dlane.mode` "off") are born as before; a birth with no parent (a new
  lineage) is never refused by this rule; a store error refuses nothing (the tournament's rule still retires). Nothing
  in `league/live/`, `league/gym/` or `league/constitution.py`.
- **Not handled** (the tournament still retires the loser on `SPENT_TRY`): a living member of an earlier pass that has
  no best yet claims nothing (it may die without a try), so a birth beside it can still lose the try to it; and a
  lineage joined after birth by identical code (`SwarmStore._link_code`, when a version is added) can still spend a
  newborn's try.
- **The prompt is unchanged on purpose:** the LANES block still says a dead direction idea proposed again "continues its
  lineage, with no try left" (true of the lineage; the card is now refused rather than born). Its text is pinned by
  `test_dlane_trainmap`'s golden digests (the map off is main `d70e00c3`'s text byte for byte), so the card refusal is
  the only channel that says so.
- **The harness guard:** `SwarmStore.looks_over` (`lineage_looks` over a lineage set, which `birth_spent` reads) is a
  sealed read (`harness_lanes.SEALED_READS`), like `lineage_looks`.
- **Roll back:** revert the commit (there is no setting). Swarm-side only: no fingerprint, money or constitution move.

## The Probe roster (Oct 10, 2026): deployed 03:36Z, `dlane.roster` 5 since 03:48Z

`dlane.roster` in the state root's `swarm.json` (a whole number; above 50 reads as 50; absent is no roster) caps how many
families hold the Probe band's seats (`league/swarm/bands.py` `seating`):

- every Probe family holds a seat and is never hidden; a Sized family neither holds one nor waits;
- a Candidate whose structure cannot trade real money (the money table's real types) or with no `state.banded_at` holds
  no seat and is shown as before;
- the other Candidates queue: the fresh ones first, in the order they became Candidates (`banded_at`), then the ones that
  came back from Probe (a demotion), by the time they came back. The first `seats - Probe` hold a seat; the rest WAIT:
  `bands.read` gives the live path no row for them, so they have no shadow or real instance and no money-table band move
  (the gate can still send one back to the Gym on a negative nightly forward record). A demoted family therefore comes
  back to Probe only into a free seat.
- **Fails closed.** The setting is read from `swarm.json` alone (not the policy layer). A file that cannot be read or
  parsed, or a `dlane.roster` that is not a whole number (a string, a bool, a fraction, a negative), keeps this process's
  last good value; with none, no new seat is given (`roster()` says `closed`). No file or no key is no roster.

Lowering the setting never hides a Probe or Sized family, but Candidates past the new count lose their seat: their shadow
books wind down and those closes enter the forward record. A Sized family held back to Probe takes a seat the same way.
Setting it to 0 (or removing the key) releases every waiting Candidate to the money table at its next families pass.

- **Why:** Done needs >= 5 real closes from each of >= 2 programs, and every program at Probe shares one envelope and
  8 slots. Without a roster those slots spread one or two closes over many programs, so the clause fails even for a real
  edge. The operator's pre-registered simulation (REDESIGN-1010, private) chose the value.
- **Read it:** `bands.roster(root)` -> {seats, closed, probe, seated, waiting, seatless}, or None while it is off; the
  `dlane` report's `roster`; pre-open check 6 lists the waiting Candidates as by design (not as missing rows).
- **Set / roll back:** `python3 set_swarm.py dlane.roster=<n> --apply` (owner's machine); `dlane.roster=0` is the
  rollback. No deploy, no fingerprint move: the rule is swarm-side. Once the $800 Probe total and the -$300 line are
  deployed (the section above), they were measured at 5 seats alone: rolling the roster back or setting another count
  needs their rollback too (an owner deploy), or a new measurement first; the `dlane` report raises PT1 until then.
- **Not handled:** a seated family that rarely signals keeps its seat (no idle eviction); the oldest Candidate the money
  table holds for a passing reason (unit fit, embargo) keeps its seat while younger ones wait; a credit-type Candidate
  holds no seat, so if equity ever opens credit types it is outside the roster.

## The weekend fixes, integrated (Oct 10, 2026): `release/weekend-fixes`, deployed 22:57Z Oct 9

One release of the three weekend builds, merged one at a time on main `cf96b72c` (the live release
`20261009T170259Z-404fe99d6c9c`): `wfix/swarm` (M2, M3, M5, m3), `wfix/ops` (the stall alarm's four causes and the
owner-deploy grace, M6 and M12; the Done meter on DONE-RULE-A1, A1.1-A1.4 with M7-M9; the program loss line; m11) and
`wfix/replay` (the per-close fill replay, B1 (c)). Each has its own section below, written on its branch: where one says
another fix is "not in this branch", it is in this release.

**The walls (C0, rule F0), checked at the release head.** Nothing under `league/live/`, `league/gym/` or
`league/constitution.py` changes. The execution fingerprint (`31a7e921`), the money digest (`0310779c`), the
constitution digest (`ca89ff8a`) and the gate contract (`397b22b772b3`, `gate.gate_contract()`) are main's. No Probe
program leaves Probe, no family is reviewed again, no ratification, no evidence reset.

**One join made here: A1.4's finality reads the twins** (`league/ops/dlane_report.py` `finality`). The ops build read
"the replay landed" from the program's NIGHTLY replay; the replay build matched each close to its own twin. Each left
the join to the other, so a reading could be frozen on the nightly fallback just before the close's twin replaced it.
- A close whose twin is FINAL (priced, no_fill, no_contract, unpriceable: final once judged) has its replay landed,
  whatever the nightly has replayed.
- With the twins on (`forward.twins`, the default), a close with no final twin yet (none, or `failed` and to be asked
  again) is `pending_twin`, and the checkpoint's `final_why` says "the per-close twin of N closes has not landed".
- With the twins off (`forward.twins` null), such a close reads the nightly's landing exactly as the ops build did.
- **Its cost:** a twin that keeps failing holds every reading that counts its close provisional, so no Done claim (A8)
  is made on it. It shows in `final_why` and in `replay_twins.by_status.failed`. Switching the twins off puts finality
  back on the nightly. This is a tightening of a Done claim's inputs, never of trading.

**The review's five fixes** (Oct 10, 2026; `league/ops/` only, so the walls above still hold):
- **Item 7 needs a stall receipt** (`Research247.day`). A UTC day with no `stall` receipt (the job failing all day, say
  on an unreadable swarm store, or missed) read "no owner step waiting" on no evidence. It is now not held ("no stall
  receipt"), as a day with no `budget` receipt already was not.
- **The `done` cause keeps an untold claim** (`stall.py`). It read the report's A8, which one report says once: a House
  start (the job's at-start run rewrites the report without it) or a notice the gateway did not send before the next
  `dlane` run lost the claim to a ledger row. It now reads the report's FINAL holding checkpoints (frozen from report
  to report) and stands for each one until a notice carrying it is SENT (`stall.json` `done_told`).
- **The program loss line holds with the lane off** (`dlane_report.lane_off`). The job returned before
  `program_losses` when `dlane.mode` is "off", so the lane's rollback switched off A1.3 for every program, alpha
  included. With the lane off it now still retires a due program (PL1 a House warning, the figures in the receipt) and
  writes no report; with nothing due the receipt is the `skipped` one it always was.
- **A pre-open run** (`registry.py`: the `dlane` job also 30 minutes before each open). A Probe position held to its
  expiry is priced by the House's overnight reconciliation: pid 14's landed at 01:11Z Oct 8, minutes before the 01:30Z
  run, and from Nov 1 (New York on standard time) the same New York hour is 02:11Z, after it. A program that such an
  expiry carried past the line would have traded one more session. About 30 seconds a run.
- **The lane off reads no report** (`stall.py`). With the lane off the job writes no report, so the last one stayed on
  disk and its K5 (an owner step for a lane that is off) and A8 were mailed at every run for good. While the lane is
  off neither `dlane` nor `done` reads it.
- **Costs:** an unread day now holds a checkpoint's item 7 back (no Done claim on it); a Done notice the gateway keeps
  refusing is retried every run (inside the owner notice's 12-hour pace) until it is sent; with the lane off a
  retirement at the line is a House warning and a receipt, not a stall notice; the extra run re-reads the report's
  inputs once a trading day (K5 and A8 may now be raised before the open as well as at 01:30Z).

**Deploy order.** (1) The gateway (`cd gateway && npm run deploy`): `gateway/lib/email.mjs` has the words for the stall
alarm's four new causes, and a House that sends a cause an old gateway does not know gets a 400 for the whole notice.
(2) One owner deploy of the House at the release head. The changed `league/ops/` files (`dlane_report.py`, `stall.py`,
`twins.py`, `direction.py`, `funnel.py`, `scoreboard.py`, `registry.py`, `__init__.py`) and `league/swarm/` files
(`gate.py`, `tournament.py`, `dlane.py`, `settings.py`, `policy.json`, `loop.py`, `researcher.py`) ship together; the
updater refuses the FORBIDDEN ones. Before it, assert the four identities above at the exact head.

**Verify after the deploy** (read-only): the three sections' lists below, and the review's: `stall.json` carries
`done_told` (`[]` until a Done claim is told) and the `done` check reads "No untold Done checkpoint holds."; the
`research_247_last_7_days` days carry `stall_receipts` above 0; the next trading day has a `dlane` receipt due 30
minutes before the open (13:00Z Mon Oct 12, after the 12:30Z `preopen`). Rollback: the previous House release and the
previous gateway version; each section says what its rollback leaves behind (M3's retired families stay retired).

## The swarm-side readiness fixes (Oct 10, 2026): deployed 22:57Z Oct 9 with the weekend fixes

Four fixes from the operator's readiness audit of Oct 9 (its fix list's M2, M3, M5 and m3), cut from main
`cf96b72c` (the live release `20261009T170259Z-404fe99d6c9c`). Swarm-side and ops only: nothing under `league/live/`,
`league/gym/` or `league/constitution.py` changes, so the execution fingerprint (`31a7e921`), the money digest
(`0310779c`) and the gate contract (`397b22b772b3`, `gate.gate_contract()`) do not move. No direction program leaves
Probe (the audit's C0: a fingerprint move would retire every Probe program for good), no family is reviewed again, no
ratification.

**1. An answer cut short is no answer (M2; `league/swarm/gate.py` `AnswerCut`, `Gate._cut_check`).** On Oct 9 four of
six gate reviews on the Sail stand-in came back `incomplete` at max_output_tokens with no text; each read as "unclear",
and the third refused dir-qqq-ivlow-3d-call v38 (20:23Z), a direction lineage's one try lost to a token cap.
- Now a review or audit (the gate's and the incubator's) whose answer is cut (`truncated`, or `incomplete_reason`
  "max_output_tokens") is an error: a `swarm.gate` `review_error` / `audit_error` (or the incubator's) with `cut` true,
  the route, the model and the token figures. No attempt is counted, nothing is barred, and it is asked again next
  round.
- Each ask after a cut carries a new model-call key (`...:<attempt>:cut<k>`): the Provider dedupes on the key, so the
  old key would hand back the stored cut answer. A first ask's key is as before.
- At most `gate.cut_tries_day` (6, swarm.json can set it) cut answers a version, a stage and a UTC day. The sixth
  raises one `swarm.status` alert, `reader_cut` ("raise gate.review_max_output_tokens"); after it that stage is not
  asked again that day (no event, no spend). The next UTC day it is asked again, when Claude's line has refilled.
- A complete answer is judged as before: three complete unclear answers still refuse. `grounded_answer` lives in
  league/gym and is untouched.
- dir-qqq-ivlow-3d-call v38 stays refused (the captain's decision of Oct 9: a loss to a harness bug, not restored).

**2. The ration before the cohort keep (M3; `league/swarm/tournament.py` `_why`).** A direction family whose lineage
spent its one Validation try or its one look now retires at the hourly round even while THE COHORT KEEP holds it. The
keep had spared 8 such families at 20:12Z Oct 9 ("ration"), each holding a population slot with nothing left to try
while births ran 1-2 a pass. The population floor (`population.floor`, 8 in policy.json) still holds.
- **Its cost:** a retired family's practice cohort ends, so its program loses the incubator route (most of these units
  are over the incubator's $75 lot cap anyway). The dlane report's `tightened` lists it.
- The alpha lane and the rollback (`dlane.mode` "off") keep the keep's order exactly: `dlane.lineage_spent` is None for
  them.

**3. A D2 entry is counted as one (M5; `tournament.py` `_verdict` and `lane_screen`, `researcher.record_verdict`,
`league/ops/funnel.py`, `league/ops/scoreboard.py`, `league/ops/dlane_report.py`).**
- A direction verdict now records `entered` (it went to the gate: the line, or D2's Validation pre-check) and the lane's
  `screen` in force ("D2" or "S-C"). It does so in the round's verdict row (`swarm.tournament` `validation.judged`) and
  in the version's `validation_verdicts` record.
- `passed` keeps meaning the Validation line, because the retire guard, the tuition and the alpha lane read it. An alpha
  verdict, and every verdict while the lane is off, is the record it always was.
- **The daily funnel** gains `validations.entered` and `validations.by_screen`. The public page shows one more row,
  "Validations sent to the gate (the line, or D2's pre-check)", only when a window has a pre-check entry. A page without
  one is unchanged.
- **The dlane report:** the direction lane's funnel gains `validations.entered`. A3's gate-wait leg counts a version
  that entered the gate and has waited over 12 h for its look. Its sources are the verdict's `entered`, and the
  lineage's try (`dlane_try.entered`), which covers every D2 entry before this release. A version the gate refused (a
  `refusals` row) is never counted.
- Every earlier funnel that read "direction validations passed 0" undercounted: eqp-realcalm-drift-call v17 entered by
  the pre-check (`validation_verdicts` {"17": passed false}) and is at Probe.

**4. R3 needs a 1.0x profit (m3; `league/swarm/dlane.py` `robust_verdict`).**
- **How it read:** `robust_verdict` reads the 1.0x P&L from the version's Train score (`base["pnl"]`, `pnl_10`), and the
  1.5x P&L summed over the 1.5x run's Train years (`pnl_15`). P1 needs the 1.5x run's own P&L above zero.
- **The bug:** R3 was `pnl_15 >= cost_ratio x pnl_10` alone. For a 1.0x loss the right side is negative, so any 1.5x
  run P1 passes also passed R3. eqp-term-contango-pool-call v6 (1.0x -$1,778.21, 1.5x +$143.23) passed the 1.5x rules
  and spent its lineage's one try on Validation.
- **Now:** a 1.0x P&L at or below zero fails R3, with the reason "it lost money on Train at 1.0x". This is a
  tightening, listed in the dlane report's `tightened`.
- The researcher's brief still words R3 as "at least 0.5 of the 1.0x P&L". The Train map's golden digest of the
  map-off direction brief pins that text, so it is unchanged. The version's own `why` names the new rule.

**Deploy class and rollback.** An owner deploy. `league/swarm/gate.py`, `tournament.py`, `dlane.py` and `settings.py`
and `league/ops/` are FORBIDDEN to the updater. `league/swarm/researcher.py` is not, but it ships with the others.
Before the deploy, check at the exact head that `execution_fingerprint()` is `31a7e921...` and the
`gate_contract()["sha256"]` is `397b22b772b3...`. Roll back to the previous House release.
- Its code reads the new verdict keys and the `*_cut:*` kv rows as unknown and ignores them.
- The families M3 retired stay retired, which is a tightening.

**Verify after the deploy** (read-only):
- The next hourly tournament round retires the spent direction families the keep held. Their `swarm.retired` cause is
  the ration's, and a `swarm.status` `incubator_keep` event has no `spared: ration`.
- The next direction verdict in `swarm.tournament` carries `entered` and `screen`.
- A cut review, if any, shows as `review_error` with `cut` true, and no refusal follows it.
- `dlane-report.json` `tightened` has the R3 and ration rows.

## The weekend fixes, ops side (Oct 10, 2026): deployed 22:57Z Oct 9 with the weekend fixes

The readiness audit of Oct 9 (`scratch/ready-1009/FIXLIST.md`) found that no alarm reached the owner (M6), that the
"owner deploy waiting" mail fired inside the operator's own deploy (M12), and that the Done meter could pass with no
replay evidence (B1), ignored item 7 (M7), read checkpoints before their inputs were final (M8) and had no Net after
costs beside it (M9). The pinned amendment DONE-RULE-A1 (sha256 `333bad06...`, before the first Probe close) tightened
the reading. This branch builds the ops side. Base: main `cf96b72c` (the running release). Nothing under
`league/live/`, `league/gym/` or `league/constitution.py` changes: the execution fingerprint (`31a7e921`), the money
digest (`0310779c`), the constitution digest (`ca89ff8a`) and the gate contract (`397b22b7`) do not move (rule F0: a
fingerprint move would retire every Probe program for good).

**1. The stall alarm** (`league/ops/stall.py`; the cause table under **The stall alarm and the funnel**, below):
- new causes `dlane` (a warning-level alarm in `dlane-report.json`, or the report 30 h stale; K5 holding or disarmed is
  the owner's step), `done` (A8: a FINAL Done checkpoint holds; an owner line told at once, never an owner step
  waiting), `preopen` (the latest pre-open receipt failed a check, or did not run) and `forward` (the ready file late
  after 10:00Z, a nightly error for 6 h, a nightly stop for 2 h: the stop is the owner's step);
- `owner_deploy` gets a 45-minute grace and is skipped while a deploy is in flight (a `start` row with no verdict, or
  the operator's own nightly stop, each at most 2 h old). Oct 9's 16:20Z mail would not have been sent.
- `gateway/lib/email.mjs` `STALL_CAUSES` gains the four causes' words. **Deploy the gateway first:** a House that sends
  a cause the gateway does not know gets a 400 for the whole notice, and nothing is mailed.
- The daily page's "Stalls standing now" (`league/ops/scoreboard.py`) leaves out `done` (`stall.NEWS_CAUSES`): a Done
  claim is the owner's to make, with its evidence, never a "stall" on the public page.

**2. The Done meter** (`league/ops/dlane_report.py`, DONE-RULE + A1):
- **A1.1, consistency measured.** A checkpoint also needs 2 programs with 5+ matched replay closes, each within
  +/-0.10; zero matched closes never passes ("replay untested: k of n closes matched"). Every checkpoint lists every
  program with its closes, matched closes and gap (`by_program`), and `replay_coverage`.
- **Item 7, read** (`research_247`): births, Gym runs and Validations every UTC day of the checkpoint's window (its
  last 7 days for the first checkpoint, every day since the one before for the rest), every `budget` receipt of the
  day at the ceiling (no taper), and no owner step in any `stall` receipt of the day (the `done` cause excepted). The
  operator's edits of `swarm.json` and `budget.json` in the window are listed from their before-copies, never a bar
  (the pinned rule reads "no captain" as no owner step waiting). A checkpoint holds when items 3, 4 and 7 hold.
- **A1.4, final readings.** A reading is FINAL when every counted close's program has been replayed through its exit
  day (or is no longer replayed), its broker fees have posted (fee basis broker, and the activity reading is of a later
  New York day), and the research window has ended. A final reading is frozen (carried from the previous report as it
  was). The meter's `holds` (a Done claim) needs a final reading; `provisional` says when a holding one is not yet
  final. A8 fires only on a final one and names the items.
- **M9, Net after costs** (`done.net_after_costs`): each meter's realized net to the close economics' cutoff, less
  every input cost since T0 on the economics job's basis (Sail billed or metered, Claude through the gateway, OpenAI,
  market data, TypeSafe), and the economics Net beside it. The swarm's booked spend (`costs`) is "comparison only".
- **A1.2:** P(Done | zero edge) is 0.024 with its horizon (12 weeks), holds (3 sessions), budget variant and source
  (`dlane.ZERO_EDGE`); `policy.json` `dlane.done_zero_edge_p` 0.13 -> 0.024. Any other setting says it is not pinned.
  (0.027 since the Probe total at $800, Oct 10, at the top; 0.024 keeps its own label in `dlane.ZERO_EDGES`.)
- **A1.3, the program loss line** (`dlane.program_loss_usd`, -200 in `policy.json`, -300 since Oct 10; a setting can
  only tighten it, to -25): each Probe row carries its program's own realized Probe net and closes, its share of the
  Probe total ($400 then, $800 since Oct 10), and when DM1 can first fire (`dm1`: n > (1.645 sigma / r_floor)^2, 17 at
  the live sigma 2.46). The `dlane` job retires, swarm-side, any program (every lane: the pinned rule names one program)
  whose realized Probe net is at or below the line, every Probe close priced: `SwarmStore.retire`, a public
  `swarm.retired` cause in words, a notebook line and a private `swarm.dlane` event with the figures. The live path then
  puts its real instance on exits only, so its positions close by the House's rules. Alarm PL1 says it; the report's
  `program_loss.retired` names it.
- **m11:** a same-risk buy-and-hold uses the exact entry and exit days' closes or says why (never an older close);
  the `direction` job keeps today's daily bar only once the session has closed (15 minutes after); the funnel counts
  real opens by route; E0's basis says it is the first reading the report saw, not release L-D's deploy reading.

**Not in this branch:** the unpriced and awaiting-expiry rows (m2), the envelope's equity (m5) and the review routes
(m8) of the audit; the per-close fill replay (B1 c); the swarm side (M2, M3, M5, m3).

**Deploy class and order.** (1) A gateway deploy of `gateway/lib/email.mjs` (`cd gateway && npm run deploy`), so the
new causes have words. (2) An owner deploy of the House (`league/ops/` and `league/swarm/policy.json` are FORBIDDEN to
the updater; `league/swarm/dlane.py` too), after asserting the four identities above on the exact head. No
ratification. Rollback: the previous House release (its stall job reads the same `stall.json`, ignoring the new
`nightly_error` key; its report ignores the new keys of the previous report) and the previous gateway version.

**Verify after the deploy** (read-only): the next `stall` receipt's `checks` has `dlane`, `done`, `preopen` and
`forward`; the next `dlane` run's `dlane-report.json` has `done.net_after_costs` with the latest economics cutoff,
`done.p_done_zero_edge.value` 0.024, `program_loss.line_usd` -200, and on `probes[eqp-realcalm-drift-call]` a
`dm1.first_fire_at` of 17; `research_247_last_7_days` lists the days.

## The per-close fill replay (Oct 10, 2026): deployed 22:57Z Oct 9 with the weekend fixes

The readiness audit of Oct 9 (blocker B1): the Done rule's item 4, "live fills consistent with their replay", could pass
with no replay evidence. A real close was matched to its program's NIGHTLY forward replay by (version, entry day), and
that replay drifts out of phase with the real account for good. Direction v17 holds one position to expiry, so its
replay, which entered Oct 8 and holds to Oct 12, could not enter on Oct 9, the day pid 41 opened: pid 41 has no match.
The amendment A1.1 (pinned Oct 9) now requires measured matches; this release makes one for every real close.

**What a twin is** (`league/ops/twins.py`). The real trade's OWN orders, replayed on the gate image by the Gym's own engine
and fill model:
- A fixed Gym program (the puppet; its sha is in every record) holds one real position in its PARAMS: the contracts
  (strike, right, side, ratio, days to expiry on the entry day), the open order's decision minute, limit, size and time in
  force, and every later close order the venue received, at its own day and minute. It finds each contract by exact
  strike, right and expiry at the entry minute and sends the same open at the same limit.
- The House's expiry close is never replayed: the Gym's venue makes its own on the expiry day (the live path's rule). A
  close the gateway or the House refused never reached the venue and is not replayed either. A House-forced close on
  another day (an orphan's) is replayed at the natural.
- One Gym job a close, window "forward" cut to the trade's own sessions, on the gate box (the gate's own reason, as the
  nightly forward), at priority 4 (under the nightly forward's 5). No `runs` row and no trial: a twin is not research,
  and nothing an agent reads changes.
- The verdict: `priced` (one trade entered on the real entry day, over exactly the trade's NYSE sessions); `no_fill` (the
  model would not fill the real open: counted, never a gap); `no_contract` (the image has no two-sided quote of a leg at
  the decision minute, or lacks the entry day); `unpriceable` (a leg past 60 days, a broken structure closed leg by leg,
  a day missing inside the trade's sessions); `failed` (the job failed, or the image stops before the trade's last day:
  asked again up to 3 times a ready day, and again on the next day's image). Everything else is final once judged.
- A priced twin's gap is live minus twin, each P&L over its own maximum loss (the book's cash, as D5 reads it), with both
  exits classified (`exit_agrees`).

**Where it runs.** Its own round in the swarm's loop, after the nightly forward (`league/swarm/loop.py`), once per
`forward.every_seconds` (an hour) per ready day, only while the guard allows the Gym. A close is twinned once the image
holds its exit day: pid 14 (the Oct 8 tuition close, GOOGL, Sept 30 to Oct 7) on the first pass; pid 41 (SPY, Oct 9 to
its Oct 12 expiry) after the Oct 13 data night (about 06:15Z). Cost: one short single-root batch a close on the gate box
(cents a day).

**What reads it.** The swarm store's kv `close_twins` ({pid: record}). The `dlane` report's Done meter
(`replay_gap`): a close with a priced twin is matched to it and pooled with the rest as D5's ratio of sums; a close
whose twin is final but unpriced is counted by verdict (`twin_unpriced`) and never matched to the nightly replay
instead; a close with no record is matched to the nightly replay exactly as before (with no record at all, the
figures are D5's, key for key). `dlane-report.json` `replay_twins` lists every counted close with its verdict, live and
twin return on maximum loss, the gap and both exits.

**The switch.** `swarm.json` `{"forward": {"twins": null}}` (or `false`) turns it off: no job, no read of the live book.
`{"forward": {"twins": {"max_jobs": 12, "attempts": 3}}}` are the defaults. Deleting the kv `close_twins` puts every close
back on the nightly match.

**Walls.** Nothing under `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint
(`31a7e921`), the money digest (`0310779c`) and the gate contract (`397b22b772b3`) do not move, so no Probe program is
sent back to the Gym (C0). The code lives in `league/ops/` (FORBIDDEN to the updater) because it is the Done meter's
input: only the owner's deploy changes how a twin is made or judged.

**Deploy class and rollback.** An owner deploy (`league/ops/` and `league/swarm/settings.py` are FORBIDDEN to the
updater). Roll back to the previous House release: it never reads `close_twins`, and the kv is inert.

**Verify after the deploy** (read-only): the swarm log has a `twins:` line after the next ready day; `swarm.sqlite`
events of kind `swarm.twin` (action "round"); kv `close_twins` holds pid 14 with a verdict; `dlane-report.json`
`replay_twins.by_status` counts it. After Oct 13 ~06:15Z, pid 41's record: `priced` with `twin.exit` "house_close"
expected (the House's expiry close Monday 15:15-15:25 ET, as the Gym's).

## The budget split (Oct 9, 2026): deployed 17:03Z Oct 9

An owner deploy of two operator decisions of Oct 9 (about 16:00Z), cut from main `d70e00c3` (release L-D with D-1,
D-1b and the graveyard). PR #520, the direction Train map, was still open and is not in it. Nothing under
`league/live/`, `league/gym/` or `league/constitution.py` changes, so the execution fingerprint (`31a7e921`), the money
digest (`0310779c`) and the constitution digest (`ca89ff8a`) do not move: no ratification, no evidence reset.

**1. The split** (`league/ops/budget.py` `SPLIT`): Sail 0.6 and Claude 0.4 become Sail 0.8 and Claude 0.2. The owner's
ceiling stays $25 a day, now Sail $20 and Claude $5 (it was $15 and $10).
- **Why** (measured read-only on the House's swarm store, Oct 7 19:30Z to Oct 9 15:37Z):
  - DeepSeek V4 Flash researched as well as Claude Sonnet 5.5 at 38x lower model cost per Train run.
  - Per research dollar (models plus Gym boxes, both windows pooled), Flash brought 3.3x (95% CI 2.2-5.1) more
    families to the Train bar.
  - Claude's researchers had 3 Validation tries and no pass.
  - The first real Probe trade (eqp-realcalm-drift-call v17, 14:26Z Oct 9) was written entirely by Flash.
  - The operator then turned the Claude research band off in `swarm.json` (`researcher.claude_top` 0,
    `claude.role_usd_day` researcher 0 and architect 0). Claude's remaining use is the gate's review and audit and the
    strategist (about $2 a day or less, estimated), plus the House's post-mortem and engineer. The unused share moves
    to Sail, which buys the Gym boxes and the Flash research.
- **What the split moves in the same release** (each derived from it, each pinned by a test):
  - The floor (no usable `budget.json`, or a stale one): $4 of Sail and $1 of Claude a day (was $3 and $2).
  - At the ceiling: 7 Gym boxes (was 5), a Sail model pace of $0.33 an hour (was $0.25), every Claude line at most $5
    (was $10), and the gate's reserve on Sail $2.00 (was $1.50).
  - Claude's room at the ceiling (`paid_model_room`): the audit $5, the review $3.70, every other role $3.05 (was $10,
    $8.70 and $8.05).
  - `league/swarm/policy.json`: `gym.max_boxes` 5 to 7 and `researcher.sail_usd_per_hour` 0.25 to 0.34, so the
    policy's caps let Sail's $20 reach its knobs (5 and 0.25 were what $15 bought). `claude.role_usd_day.strategist` 6
    to 3, so its line leaves the gate's two holds inside Claude's $5.
  - The engineer (`league/ops/engineer.py`): `engineer.usd_day` $4 to $3 and an authoring attempt's cap $3 to $2 (the
    review stays $1), so an attempt and its review fit in a day inside Claude's $5 less the gate's holds.
- **Its cost:**
  - Sail drains faster: about $21 a day with its fixed cost at the ceiling, from about $16. For the same balance, the
    funding notice (two days before research runs out) comes sooner.
  - Claude's $5 keeps the gate's two holds ($1.95), so the strategist, the post-mortem and the engineer share at most
    $3.05 a day.
  - At the floor, Claude's $1 is under the gate's holds. The review runs on its Sail model, and so does the audit unless
    its hold is at most $1. Each raises the gate's "not the plan's reviewer" alert. At the old floor's $2, one review
    and one audit fitted on Claude.
  - The engineer's attempt has a third less to spend.
- **On the box.** Its `swarm.json` wins over `policy.json`. Where it sets `gym.max_boxes` or
  `researcher.sail_usd_per_hour` (the CHANGELOG's last record, Oct 8: 2 and 0.5), those hold Sail's spend under the $20
  until the operator raises them there. Its `claude.role_usd_day` lines are held to $5 by the budget, and the router
  keeps the gate's holds whatever they say.
- **The day's figure.** The rule's version and `budget.json`'s schema stay 2, so a file from before the deploy is read
  as it is, each meter held to its new share. Claude is at most $5 at once. Sail keeps the figure the day's first run
  set (at most $15) until the first budget run of the next UTC day (00:30Z) sets up to $20; until then
  `would_set_usd_day` shows it. The funding notice's id (`funding:<meter>:<UTC day>:r2`) is unchanged.

**2. The `dlane` report's header** (`league/ops/dlane_report.py` `LOOSENED`) adds the direction graveyard rule (PR #519,
deployed 12:44Z Oct 9): a direction card is bound only by direction families' graveyard rows. Its cost: more direction
births may retry ideas similar to dead alpha ones. Each lineage still gets one Validation try and one holdout look, at
D2's measured false-positive rate of 10.4% per program (mixed worlds). The Train map (PR #520) is not in this
release's base, so the header does not list it.

**Deploy class and rollback.** An owner deploy: `league/ops/` and `league/swarm/policy.json` are FORBIDDEN to the
updater (`league/ci.py`). Roll back to the previous House release. Its code reads this release's `budget.json` (the
same schema) held to the old shares, so neither rule's ceiling is passed.

**Verify after the deploy** (read-only): `budget.json` `rule.split` is {sail 0.8, claude 0.2} after the next budget run,
`meters.claude.research_usd_day` is at most 5, and `meters.sail.would_set_usd_day` is up to 20 (the day's figure from
00:30Z the next day). `dlane-report.json` `loosened` names "graveyard alpha rows".

## Release D-1b, the direction lane on D2 (Oct 9, 2026): deployed 10:36Z Oct 9 with D-1

D-1b switches the direction lane's screen to **D2** and meets the reporting terms of the owner's goal of Oct 9: item 4,
"a pre-registered screen whose false-positive rate you have measured, at most 15% per program at zero edge, stated
beside every Probe trade", and item 3, "Tell me 2 days before Sail or Claude runs out". It is Claude's decision
DSCREEN-ADOPT, and it is **a reported loosening** (the cost is below). It ships in the same owner deploy as D-1 (its
section follows), on top of release L-D (deployed 09:04Z Oct 9; its section is below D-1's, and `release/dlane-d1`
carries it: main `40c39435` merged in). Like D-1 it is swarm-side and ops only. Nothing under `league/live/`,
`league/gym/` or `league/constitution.py` changes, so the execution fingerprint (`31a7e921`), the money digest
(`0310779c`) and the constitution digest (`ca89ff8a`) stay release L-D's, the ones in production.

**What it does:**
- **D2 is the direction lane's screen.** `policy.json` sets `dlane.screen` "D2" and pins DSCREEN-2's receipt in
  `dlane.screens.D2`: sha256 `c3605947...` and c 1.00, with the lane's figures. CI holds that sha to
  `docs/benchmarks/direction_screen_2.json`, which is the receipt copied byte for byte. It holds aggregate figures, the
  rule and the shas only (test_dlane `Screen`). The rule was pre-registered before any real world was run:
  - On Validation at 1.0x: at least 50 trades on at least 25 entry days, and a mean entry-day return above zero.
  - After the one sealed look: the pooled entry-day t over the Validation and holdout entry days is at least 1.00,
    AND the holdout's P&L is above zero.

  On exact figures the code's statistic is DSCREEN-2's own, to 3e-15. The Gym's summaries round the daily mean to 6
  decimals and the t to 4, so the gate judges the statistic's **lower bound** over that rounding
  (`dlane.d2_pooled_t_low`). A pass is therefore always a pass of the exact statistic. On 20,000 fixtures there were 0
  extra passes and 3 conservative misses: 1 within 2e-5 of c, and 2 where a window's mean or t rounded to zero. The
  pre-check never opens tuition. The alpha lane keeps S-B byte for byte.
- **Calls only.** `dlane.structures` is `["long_single"]`, so the card check refuses a direction debit vertical and a
  put. D2 is refused (S-C instead) whenever the lane admits any other structure, because it was measured on single calls.
  A new Train bar, **C1**, fails a direction program whose Train trades hold a put or a short leg (a `long_single` card
  may send a put by its code). The brief and the architect's LANES block say "no put, no vertical, no short leg".
  C1 reads only the Train (2022-24) trades, and the Gym's Validation and holdout views carry no trades, so a program
  that buys a put only in conditions 2022-24 never saw (a crash hedge above any 2022-24 VIX close) would pass it. So
  **the calls-only code check** (`dlane.calls_only_code`, the review's finding 3) reads the program's text: a string
  literal of its code or of its parameter overrides (docstrings, dict keys and subscripts aside) that names any open but
  `long_call`, a put ("P", "put") or a short leg ("short"), in any case, refuses it:
  - the researcher's `gym_run` and `gym_sweep` refuse it before any version, job or trial;
  - the tournament never validates such a direction version (`calls_refused`, which the stall alarm reads as owed
    nothing), so it spends no try and opens no tuition;
  - the gate refuses it at stage "calls only" before a review is paid, and the incubator's review fails it with no
    model read.

  A `long_call` open is one long call wherever the Gym's classifier judges it, and the live path resolves an intent with
  the same module, so a program that names no other open sends none by a literal. **What is still open:** the check
  cannot see an open type assembled at run time from pieces other than those words, and **`league/live` has no
  direction calls-only check of its own**. D-1b scheduled that guard for release L-D, and L-D shipped (09:04Z Oct 9)
  without it: the live path still admits a `long_put` for a `long_single` family (`money.DECLARED_TYPES`), so such a
  program at Probe could send a real put. The guard is a `league/live` change, which moves the execution fingerprint
  (an evidence reset: every banded family back to the Gym, rule F0), so it is not in D-1 or D-1b and waits for the
  next planned `league/live` release. Until then the four swarm-side refusals above are the whole wall.
- **One Validation try and one holdout look per direction lineage** (`dlane.val_tries`, `dlane.looks_per_lineage`, both
  fixed at 1). This keeps a lineage's false-positive rate equal to the program's. With two tries it is 16.4% on mixed
  worlds (the receipt's per-lineage reading A). How it works:
  - The tournament validates a direction version only while its connected lineage has no try yet, or when the version
    is that try already (validated again on a new Gym image). It runs one member of a lineage a round (`waiting_lane`),
    and a family whose lineage's try is used is owed none (`spent_lane`; the stall alarm reads it).
  - A late second try is recorded as rows and trials but never judged into the family's state, so it cannot reach the
    gate (`lane_try_refused`). The gate's look ration for a direction lineage is 1 (refusal "rations": "the direction
    lineage's one holdout look is spent").
  - A Gym direction family whose lineage has used its try or its look, with no try of its own still waiting for its
    look, retires. The public cause names the rule and no figure. THE COHORT KEEP and the operator's extension hold
    spare a family from this rule as they spare it from the others; its ration is enforced all the same.
  - A direction family never forks once its lineage has tried.
  - **The try is always judged** (the review's finding 1). The lineage's first try is judged even when the researcher
    moved the family's candidate on (a submit, a better Train run) while its job was out; before, its verdict was
    dropped as stale, the run still counted as the try, and the family retired unjudged. The gate looks at the try's
    own version. A try with no verdict (its result came back from another Gym image), or whose verdict entered the gate
    on another Gym image before its look, is validated again as that very version (`dlane.try_owed`), never the new
    candidate, and spends no new try. A family whose own try has no verdict yet is not retired.

  The alpha lane keeps its counts: tries until retirement, and three looks.
- **The false-positive rate beside every look and every Probe trade** (operator-facing only, never in a prompt):
  - Each direction look's line and its `swarm.gate` event carry `screen`, `fp_lane_mixed`, `fp_lane_2224` and `receipt`.
    Under D2 these are 0.1037, 0.1239 and `c3605947...`; under S-C they are 0.0141 and 0.0209.
  - Each band row of the fast lane's report carries `fp`, the screen that admitted its banded version.
  - The `dlane` report's new `fp_beside_trades` lists every real Probe trade (`:r`, open or closed) and every agent real
    close. Each row gives its program's screen and rates, and the contamination statement rides beside the list. An
    alpha (S-B) row states FAST_LANE_SCREEN_1's bound, at most 2%. Only a Probe or Sized trade (`:r`) opened at or after
    its version's passed look carries that look's screen (the review's finding 5). A tuition or incubator close, even of
    a version that later passed, and a position opened before the look say that no screen admitted them (`fp_why`).
- **The meter warning, two days ahead, once a day.** The `budget` job tells the owner, through the existing `funding`
  notice and the gateway's mail, when research on a meter (Sail or Claude) runs out within 2 days at its current burn.
  The fields are in `budget.json`:
  - `burn_usd_day` is the larger of the rate the rule holds the meter to and its spend over the last 7 days.
  - `out_in_days` counts the days until the lower of the runway at that burn and the days of research left at the
    ceiling falls to the rule's 5-day runway term, where the taper starts cutting research. At the ceiling this is the
    same 7-day card line as before.
  - The notice goes out at most once a day per meter: a day less an hour after the last, under the id
    `funding:<meter>:<UTC day>:r2`, which the gateway dedupes. It was once a week.
  - A meter spent faster than the rule holds it (its burn above the rule's rate) can be short while its card line still
    reads weeks. Its notice then states the burn in the facts the gateway's mail reads (the review's finding 4): the
    "now" figures (`current_*`) are the burn's dollars a day and days above the reserve, and the add-by date
    (`card_date`) is the day research runs out at the burn. So the mail never says "Nothing stops if no card is added"
    or gives a late date while research runs out within the lead. The figures at the rate the rule wants are unchanged.
    The facts' names and the gateway's composer are unchanged; until a composer words the burn as a spend, the mail's
    "held to" sentence reads the burn's dollars.

  "Runs out" means research, not the balance: while research tapers, each day spends a fifth of what is left above the
  reserve, so the balance never reaches it.

**The loosening, with its cost** (from the receipt; also the header of every `dlane` report):
- The lane's false-positive rate per program at zero edge goes from S-C's 1.41% to **10.37%** on mixed worlds (95%
  world interval 9.57-11.16%, cluster 7.90-12.76%). It is **12.39%** on 2022-24 worlds (upper bound 13.29%).
- All census cells: 13.37% (upper bound 14.08%), and 14.11% on 2022-24 worlds (upper bound 15.01%). That is why D2 runs
  only while the lane is calls only.
- Swarm placebos: 4.76%. Power at +10% of maximum loss a trade: 3.22% to 19.95%.
- D2 FAILED the operator's own pre-registered adoption rule (every upper bound at most 12%). Adopting it after seeing
  that result is a post-hoc loosening of that ceiling. The lane's rate stays under the owner's 15%.
- Discrimination is weak: D2 passes mostly programs whose two screen windows rose.
- The Probe loss budget, not the screen, bounds the money: release L-D's $400 of worst net stretch in any 20 sessions
  and a net total, $400 at L-D and $800 since Oct 10 (`options_money.probe`).
- Contamination: every author knows whether those windows rose. The rate is a property of the procedure across
  historical worlds, not a guarantee in this one.

**Roll back.**
- **D2 to S-C, at once and a tightening:** set `dlane.screen` "S-C" in `swarm.json`. It is read on the next loop with no
  restart. A setting can always choose S-C and can never pin a receipt. A version that entered the gate by D2's
  pre-check waits there until D2 is back. One whose look was already out when S-C came in fails that look closed (the
  review's finding 2: the screen is read when the result lands, and it met neither screen's rule; the look's `why`
  says so). The ration and calls only stay.
- **The lane off:** set `dlane.mode` "off" (D-1's rollback, below). It also turns off the ration, C1, the FP keys and
  the report.
- **The meter warning:** the code rollback (`floor_box.py rollback`). The notice's channel and facts did not change.

**Verify after the deploy** (beside D-1's list):
- `screen_effective` reads "D2" with receipt `c3605947...` on the box. Run `python -c "from league.swarm import dlane,
  settings; print(dlane.screen_effective(settings.load('/workspace/state'), 'direction'))"` from `/workspace/current`.
- The first direction look's `swarm.gate` event carries `fp_lane_mixed`.
- `<state>/dlane-report.json` has `fp_beside_trades`, and the loosened list names D2.
- Its `probe_envelope.constitution` reads release L-D's row ("net", 400 over 20 sessions, 400 in total, 8, "dm1"),
  `by_basis` holds both bases with no `error`, and its `in_force` reads as `<state>/fast-lane-report.json`'s
  `probe_budget` of the same night (both run outside market hours).
- `<state>/budget.json` meters carry `out_in_days`.

## Release D-1, the direction lane (Oct 9, 2026): deployed 10:36Z Oct 9

A DIRECTION lane beside the unchanged ALPHA lane: research in which profit from the index's direction counts, reported
beside the same-risk buy-and-hold and never called alpha. Claude's decisions under the owner's goal of Oct 7 (item 4:
direction profit counts when reported beside the same-risk buy-and-hold; item 5: every loosened rule reported with its
cost), after the plan of Oct 9 and its critic. Across 534 pre-registered tests no options alpha survived one-lot costs;
the only after-cost profit ever measured is index direction carried by cheap out-of-the-money calls held a few sessions,
and no affordable structure beat holding the same delta in the stock. So the lane is **leveraged index beta minus option
costs, not alpha**, and every view, brief, status line and report says so: an always-in call program can pass its bar,
and the gate is not tested by it. The code is `league/swarm/dlane.py` (new, protected: its docstring states every rule);
the operator's report is `league/ops/dlane_report.py`.

**It is swarm-side only.** Nothing under `league/live/` or `league/gym/` and nothing in `league/constitution.py`
changes: the execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the constitution digest (`ca89ff8a`)
stay release L-D's, in production since 09:04Z Oct 9, so there is no evidence reset, no evaluator adoption and no
re-ratification. (Built on `ccfa48d5`, D-1 moved none of `ccfa48d5`'s `b4c34031` / `1665c385` / `5698a2f9`; the branch
now carries L-D, main `40c39435`.) It ships by the owner's deploy (`dlane.py`, `league/swarm/policy.json`, `league/ops/`
and the gateway's protected list change) AFTER release L-D (the one evidence reset of Oct 9, deployed 09:04Z, below): no
league/live or league/gym release may ship while a direction family is a Candidate, Probe or Sized, except a
money-safety fix (rule F0: its cost is those bands, which go back to the Gym).

**What it does** (the switches are in the table below):
- **The lane.** A family's lane is its card's (`card.lane`; "alpha" by default, "direction" declared by the architect),
  kept in its spec, inherited by a fork or a child, never changed. Every family born before D-1 is alpha, and an alpha
  card's sha is byte-identical (no `lane` key is ever written for alpha). A direction card must be inside the lane's
  box: mechanism class `equity_premium` (new) or `trend_momentum`; structure `long_single` (calls only) or
  `debit_vertical`; roots SPY, QQQ, IWM; holding `days_1_3` or `days_4_10`; an ablation switch that enters the same
  structure every session (never flat). Graveyard rows whose only verdict is DRIFT do not bind a direction card, and
  since Oct 9 neither does any alpha family's row (**The graveyard**, next).
- **The graveyard** (Oct 9, 2026, after D-1 went live at 10:37Z as main `2b60d94a`; PR #519 from `fix/dlane-graveyard`,
  deployed 12:44Z Oct 9; the operator's decision, **a reported loosening**). A direction card is bound only by the
  graveyard rows of direction families (`league/swarm/cards.py` `RebirthIndex.binds_direction`, `needs_claim`).
  - Why: the House's architect pass of 11:32Z had its direction cards refused by alpha rows, for example
    low-iv-drift-call: "its cell (equity_premium / directional / days_4_10 / clock+implied_vol+underlying_price), and
    the trend_momentum cell its own mechanism text reads as, hold 15 graveyard row(s) ..., the newest
    persistent-ceiling-rejection-put (REFUTED) of the 7 that need a claim". calm-trend-drift-call was refused the same
    way. Those verdicts judged timing edges against drift under the alpha rules. They say nothing about a direction
    program, which direction-v2 judges as labelled beta. The lane has its own multiplicity control: one Validation try
    and one holdout look per lineage, and D2's false-positive rate measured per program.
  - How a row's lane is read (`cards.row_lane`), the way D-1 stores it: the family's spec `lane`, else its card's
    `lane`, else (a fork with no card of its own) the card its spec's `card_sha` names. A family with none of these is
    alpha, which covers every family born before D-1.
  - What still binds: a DRIFT row binds no direction card (unchanged). A direction family's row with any other
    mechanism verdict needs the full rebirth claim (a valid `rebirth`, the row's and the cell's budgets). An alpha
    row is still matched, so a claim a direction card makes on one is checked as on a DRIFT row: a rebirth only when
    it holds, otherwise dropped. The verdict counts alpha rows (`alpha_rows`; the `swarm.born` card carries it).
  - Alpha cards are judged byte for byte as before: every row binds them, direction rows included. `dlane.mode` "off"
    is byte for byte main `2b60d94a`. `test_dlane_graveyard` pins both to that commit's output on a fixture store.
  - The architect's view: the LANES block says a direction card is bound only by direction families' rows. The BIRTH
    CELLS header says so too (`LANE_CELLS_NOTE`), and each line of a cell a direction card may be in
    (`cards.direction_cells`: the lane's classes by its holdings) counts the rows that bind one. `closed` reads a lane
    cell whose rows bind no direction card as one a direction card can bear.
  - Its cost: more direction births may retry ideas similar to dead alpha ones (a call renting a calm trend reads as
    the trend_momentum cell's dead timing edges). Each such lineage still gets one Validation try and one holdout look,
    at D2's measured false-positive rate of 10.4% per program (mixed worlds).
  - Deploy class: the updater (`cards.py` and `architect.py` are not protected paths). Rollback: revert the commit;
    `dlane.mode` "off" rolls back the whole lane. The `dlane` report's loosened-rules header
    (`league/ops/dlane_report.py` `LOOSENED`, an owner-deploy path) lists this rule from the budget-split release
    (**The budget split**, top of this page; not deployed yet). The table below lists it now.
- **The Train map** (Oct 9, 2026; branch `feat/dlane-trainmap`, not deployed; an owner deploy). The architect and the
  direction researchers are shown which call shapes pass direction-v2 on the Train years, so births aim at shapes that
  pass instead of searching for them. After the first direction program reached real money (2.4 h after D-1b), 7 of the
  8 other direction families had no eligible version, mostly on E1 (in the market too few years).
  - **Where it comes from.** The operator's census of call shapes: every SPY, QQQ, IWM and one-on-each-root call cell
    by delta (0.20-0.50), expiry rule (nearest covering, 2-5, 6-10 or 11-20 DTE), hold (2, 3, 5, 8 sessions),
    entry minute (10:30, 15:30 ET) and gate (every session, ivlow, contango, trend and their pairs), one lot at natural
    prices, a new lot every qualifying session. It was scored by the House's own `dlane.train_score` and
    `robust_verdict` (main `d70e00c3`, the committed `dlane` settings) on 2022-24 data only; the dates were filtered
    before any row was read. Of 3,136 cells, 30 pass. Every passer is a 0.20-delta call held 2 to 5 sessions, in the
    market all three Train years: 12 enter every session, 14 under one volatility filter and 4 under both (all
    5-session holds entered at 15:30; stacking both thins 2022 below E4's 60 entry sessions in 308 of the 448 stacked
    cells). 23 of the 30 fit the unit only borderline. IWM alone has none (it loses at 1.5x), and the price-trend gate
    passes none (it sits out 2022 and fails E3). The writer computes every count in the lessons from the census, and
    `test_dlane_trainmap` checks each lesson's claims about the passers against the file's rows.
  - **The file:** `league/swarm/dlane_map.json`, protected like `dlane.py` (`league/ci.py` FORBIDDEN and the gateway's
    `protected.mjs`). It holds only what agents may see: each passing shape in the census's words (roots, delta,
    expiry rule, hold, entry, gate), its pooled S_D to one decimal, the unit's verdict as a word ("fits the unit at
    today's prices: yes/no/borderline"), in-market years, and the census's three lessons. Its header carries the label,
    `built_at`, `inputs_sha256` (the census inputs' manifest), `source_sha256`, the commit and `dlane.py` sha it was
    scored with, and the bar settings it was scored under. There is no dollar unit, price level, price ratio, per-year
    P&L or year outside 2022-24. E5's verdict word rests on the operator's assumed index level (the House prices E5
    live), so a borderline shape can flip either way.
  - **The label**, on every text that shows it: "in-sample: Train years 2022-24, from the operator's census at one-lot
    natural prices; the screen decides", with the lane's note that an always-in call program can pass this bar.
  - **Who sees what** (`dlane.train_map_text`, `train_map_brief`). The architect's LANES block (`lanes_block`, after
    the lane's rules and the graveyard line, before the direction quota) gets every passing shape on one line (at most
    30), the lessons, and "aim direction cards at these shapes and vary the gate, the hold or the root". A direction
    researcher's brief (`dlane.brief_text`, after D-1's words, unchanged) gets the lessons and the 5 best passing shapes
    on its family's roots, then the best on other roots when it has fewer. An IWM family sees 0 of its own and 5 others.
    The researcher has no lane-facts tool; adding one would change every researcher's shared tool prefix, the alpha
    lane's included. A shortfall request's opening line points at the map too.
  - **The reader** (`dlane.train_map`) is cached on the file's size and mtime and never raises. A missing, unreadable or
    malformed file is no map. So is one that is unsafe: every text field (`map_text_problems`) must be one-line ASCII,
    with no `$`, no grouped number, no digit run of four or more but 2022-24, none of 2017-21 or 2025-26 anywhere, no
    three-digit number outside an "N of M" count, and no decimal but a delta target or a one-decimal figure. The label
    must be the code's word for word, the objective direction-v2, and every row in the lane's vocabulary. If the bar's
    settings differ from the ones it was scored under, the text says so.
  - **Its cost:** births aim at in-sample winners. The screen's false-positive rate per program is unchanged (Train is
    in-sample; D2 measured its rate per program, and the ration stays one try and one look a lineage). More programs
    reach the screen, so there are more false passes in count, and more paid reviews and audits. The `dlane` report's
    loosened-rules header lists it (`LOOSENED`), beside the graveyard row that joins it at this deploy.
  - **Switch:** policy.json `dlane.train_map` true. swarm.json `dlane.train_map` false hides it on the next loop (no
    restart), and `dlane.mode` "off" hides it with the lane. The code's default is false: a dropped policy layer shows
    nothing. Off, every text is main `d70e00c3`'s byte for byte (`test_dlane_trainmap`'s golden digests, computed on
    that commit). The alpha lane is untouched: an alpha family's brief and the architect's request with the lane off
    match main's digests.
  - **Deploy:** an owner deploy (`dlane.py`, `policy.json`, `ci.py`, `league/ops/`, `CHANGELOG.md` are protected), in
    the money path's window. Gateway first: `protected.mjs` gains `league/swarm/dlane_map.json`, which needs
    `npx wrangler@4.129.1 deploy`. Until then the deployed merge route does not refuse an edit to the map, but the
    updater does (`ci.FORBIDDEN` ships with the release). Then `floor_box.py deploy`. Nothing under `league/live/`,
    `league/gym/` or `league/constitution.py` changes: the execution fingerprint `31a7e921` and the money digest
    `0310779c` do not move, so there is no evidence reset and no re-ratification. Verify: the first architect pass's
    request carries "TRAIN MAP (in-sample"; a new direction family's brief carries its lessons. Rollback: swarm.json
    `dlane.train_map` false (instant), or `floor_box.py rollback`.
  - **Rebuilding the map** (operator only, never from the box): re-run the census scorer on 2022-24 inputs, reduce it
    with the operator's reducer (scratch `tmap-1009/reduce_map.py`: it verifies the pinned input hashes and writes
    only the agent-safe fields), then run `test_dlane_trainmap` with `LTCM_PRIVATE_FIGURES` naming the operator's
    private figures file (outside the repo, never committed) so its private-figures check runs; without it that
    test is skipped. A new bar (a `dlane.py` change to `train_score`) needs a new map; until then the header's `bar`
    and `scored_with` say what it was scored under.
- **Births.** While the lane holds under `birth_share` (half) of the last 24 hours' births and fewer than `max_alive`
  direction families live, a pass reserves at least half its births for direction (never filled with alpha); the lane
  never holds more than `max_share` (60%) of the window, so alpha keeps at least 40%. The architect's request carries a
  LANES block and the lane's 48-hour failure counts; after 12 hours with no direction birth (the quota open) its next
  pass asks for direction proposals only (`lane_only`). The pass event carries `lane_births`, `lane_refused`,
  `lane_short` (and `lane_class_capped` when the class cap refused direction cards); `swarm.born` payloads carry `lane`
  for direction, a direction parent's fork included.
- **The Train bar, direction-v2** (in place of the worst-year score, for direction families only). On the 1.0x Train run
  (2022-24): E1 in the market in at least 2 of the 3 years; E3 a year mostly out loses no worse than t -1.0 and half its
  average in-market year; E4 60+ entry sessions in each in-market year; E5 one lot's maximum loss with fees at TODAY's
  prices (the House's last closes, `direction-closes.json`) within 10% of equity (`health.json`), "unknown" passing
  (the live path prices every real open again). The score climbed is S_D, the pooled t of daily P&L at 1.0x. On the
  1.5x run, each a demotion: P1 P&L above zero, R2 E1 and E3 again, R3 at least half the 1.0x P&L. Reported, never a
  bar: E2 (every in-market year t >= 0), R1 (the pooled t at 1.5x against 1.5) and the mechanism or ablation test.
  Holds of 2 to 8 sessions are all admissible.
- **No hidden look.** A direction lineage never plays the learning game (`dlane.arm_fraction` 0), and a direction
  family born into a lineage that already has an arm (a control-arm parent, a game lineage's member from before T0, or
  an alpha family given an arm in a direction lineage) sits it out too; direction looks stay out of the game's R1(b) and
  R2. The alpha game is unchanged.
- **The screen** (release D-1b switches it to D2: the section above). The direction lane's holdout look is S-C: the
  Validation line as coded, then p <= 0.20 with a holdout Sharpe at least 0.25 of Validation's. The alpha lane keeps S-B (p <= 0.10, 0.5) byte for byte. D2 (a pre-check, then a
  pooled test) is coded but REFUSED unless a receipt's sha256 and its calibrated c are pinned in the repository's own
  `policy.json` (`dlane.screens.D2`) and CI holds the receipt (`docs/benchmarks/direction_screen_2.json`) to that sha;
  under D2 the Validation pre-check never opens tuition. Every look event records `lane`, `screen` and `receipt`.
- **The leakage alarm per lane.** Alpha unchanged (10 looks, over 30% passing); direction 10 looks, over 60%. With the
  lane off the one alarm counts only the looks the alpha line judged (a look's `detail.lane`), so direction looks made
  while the lane was on never stop the alpha lane. The public checklist's `gate_paused` follows the family's own lane's
  alarm (the site contract is unchanged).
- **The drift screen is a brake on direction:** if `tournament.drift_screen` is switched back on, the researcher's
  screen and the gate's drift defense, which do not know the lanes, refuse direction programs (their profit is drift by
  design) and close the lane's route to Validation. Keep it off while the lane is on.
- **The incubator mark** for a direction family is the direction-v2 verdict in place of the drift screen alone; the
  incubator refuses a direction mark unless the lane's effective mode is "gate". Alpha marks are unchanged.
- **The sigma writer** (for L-D's DM1): the tournament writes `validation_r_sd` (the sd of per-trade P&L per dollar of
  maximum loss in the version's Validation run) beside `typical_max_loss_usd`; L-D's `league/live/families.py` reads it.
  The keys are the reader's exactly: `validation_r_sd_by_version` {str(version): sd} and `validation_r_sd` for
  `validation_version`, a finite float above zero or nothing. `test_dlane_ld_joins` holds the join end to end on the
  merged tree: the figure the tournament writes is the one `SwarmFamilies.read` puts in the band row and DM1 reads.
- **K5, automated** (a tightening): the `dlane` job sets the swarm store's kv `dlane_k5` {at, net, line} once when the
  direction lane's realized net over every route (`:r`, `:t`, `:i`) since the options swarm began is at or below K5's
  line: `dlane.k5_net_usd` (-$600), or after a clear `k5_net_usd` below the net at clearing (kv `dlane_k5_base`). While
  it is set the lane reads "shadow": no new direction Candidate, no incubator direction mark. Only the operator clears
  it (**K5**, below); the job's next run records the clear and re-arms K5.
- **What agents see of the unit (E5):** its verdict only (fits, over the cap with a scale-free hint, or unknown). Today's
  price scale and the cap (a share of the account's equity) are 2026 figures: they stay in the family state and this
  report, never in a view, status line, sweep row, run summary or the architect's request.
- **The class cap and the quota:** the births reserved for direction never exceed the room left under
  `architect.max_alive_per_class` in the classes a direction card can be in (`long_single x etf`, `debit_vertical x etf`);
  a direction card the class cap refused is counted apart in the pass event (`lane_class_capped`) and named in the next
  request.
- **The agenda guard** (D9): the swarm warns the House at its start, and whenever it changes, when `swarm.json`'s
  `architect.agenda_locked` or `architect.agenda` is longer than the architect reads (4,000 characters: it cuts the rest
  silently), not ASCII, or names a hidden year; `scripts/agenda_install.py` refuses such a text before writing it.

**The switches** (`league/swarm/policy.json` "dlane"; `<state>/swarm.json` wins over it; `dlane.cfg` holds each inside
its bound: a malformed value is its default, a number past a bound is the bound; a malformed `mode` reads "shadow"). The
screen, the alarm and K5 can only be TIGHTENED by a setting.

| Key | Committed | Bounds and notes |
|---|---|---|
| `dlane.mode` | `"gate"` | `"off"`: THE ROLLBACK (every path as before D-1, byte for byte; also the code's default); `"shadow"`: births, research and Validation run, no direction Candidate, no incubator direction mark; `"gate"`: everything |
| `dlane.roots`, `structures`, `classes`, `holding` | SPY, QQQ, IWM; long_single (D-1b: calls only; D-1 had debit_vertical too); equity_premium, trend_momentum; days_1_3, days_4_10 | only the lane's own words; `long_call` is also allowed as a structure; D2 is refused while a structure other than `long_single` or `long_call` is admitted |
| `dlane.birth_share`, `max_share`, `min_per_pass`, `max_alive` | 0.5, 0.6, 1, 24 | 0-0.6; >= birth_share, <= 0.8; 0-3; 0-96 |
| `dlane.window_hours`, `min_window`, `lane_only_hours` | 24, 10, 12 | 1-168; 1-1000; 1-168 |
| `dlane.active_share`, `min_active_years`, `out_t_floor`, `out_loss_share`, `min_entry_days` | 0.5, 2, -1.0, 0.5, 60 | 0.3-0.8; 2-3; -1.5-0; 0-1; 40-200 |
| `dlane.cost_ratio`, `c_train` | 0.5, 1.5 | 0.3-1.0; 1.28-3.0 (R1, reported only) |
| `dlane.unit_cap_usd`, `unit_share`, `unit_pref_usd` | null, 0.10, 75 | null or 25-129 (never above the share); 0.01-0.10; 25-129 |
| `dlane.arm_fraction` | 0.0 | 0-1 (0: no direction lineage plays the game) |
| `dlane.screen` | `"D2"` (D-1b; D-1 had `"S-C"`) | `"S-C"` or `"D2"` (D2 only with a pinned receipt and a calls-only lane; else S-C and the reason). `"S-C"` in `swarm.json` is the instant rollback |
| `dlane.screens.S-C` | look_level 0.20, sharpe_share 0.25, fp_unconditional 0.0141, fp_both_windows_rose 0.0222, fp_lane_2224 0.0209 | look_level <= 0.20; sharpe_share >= 0.25 (tighten only); the fp figures are reported beside each look |
| `dlane.screens.D2` | receipt_sha256 `c3605947...`, c 1.0, fp_lane_mixed 0.1037, fp_lane_2224 0.1239, fp_lane_ci_mixed [0.0957, 0.1116], fp_lane_cluster_mixed [0.079, 0.1276], power10 0.1995 (D-1b) | read from the repository's policy.json only, never swarm.json; CI holds the sha to `docs/benchmarks/direction_screen_2.json` and every figure to the receipt's |
| `dlane.val_tries`, `looks_per_lineage` | 1, 1 (D-1b) | fixed at 1: one Validation try and one holdout look per direction lineage |
| `dlane.alarm_min_looks`, `alarm_pass_share` | 10, 0.60 | >= 10; <= 0.60 (tighten only) |
| `dlane.done_zero_edge_p` | 0.027 (the Probe total at $800, Oct 10, at roster 5; 0.024 from DONE-RULE-A1 A1.2; 0.13 before) | reported beside every Done figure: "P(Done \| zero edge), simulation"; at a figure `dlane.ZERO_EDGES` names (0.024, A1.2's; 0.027, PREREG-T's) it carries that figure's horizon, holds, budget, source and who named it, with a `note` when it is not `dlane.ZERO_EDGE` (the rules this code ships); any other figure says it is a setting's |
| `dlane.k5_net_usd`, `k5_clear` | -600, false | -600 to -50 (tighten only); `k5_clear` true clears a set K5 and DISARMS K5 while it stays true (a loosening: the report warns every run; take it out once the clear is recorded) |
| `dlane.program_loss_usd` | -300 (the Probe total at $800, Oct 10, at roster 5; -200 before) | its code default (`DEFAULTS`, -300) to -25 (tighten only): DONE-RULE-A1 A1.3, the `dlane` job retires a program whose own realized Probe net is at or below it |
| `dlane.train_map` | `true` (Oct 9, `feat/dlane-trainmap`) | true shows **The Train map** to the architect and direction researchers while the lane is on; false (swarm.json) hides it at once; the code's default and any value but `true` are false |

**Every loosened rule, with its cost** (the operator's measurements: MONEY's simulation and the critic's; the header of
every `dlane` report, `dlane_report.LOOSENED`):

| Loosened | Was | Now | Cost |
|---|---|---|---|
| Beat your own exposure | every family (agenda v19 item 2) | the alpha lane only | programs whose profit is index beta reach Validation; reported beside the same-risk buy-and-hold, never called alpha |
| The Train objective | the worst Train year's t | direction-v2 (above) for direction | an always-in call program can pass and the gate is not tested by it; more null programs reach Validation (more paid reviews and audits, more false passes in count); the false-positive rate per program screened is unchanged (Train is in-sample) |
| The hidden look | every core-five lineage may play | no direction lineage plays | the game's selection pressure is lost for direction; the lane's false-positive rate at zero edge 0.02% -> 0.70% before the screen change |
| The holdout look (S-C) | p <= 0.10, Sharpe share 0.5 | direction only: p <= 0.20, 0.25 (since D-1b the rollback screen) | false-positive rate at zero edge: the lane 0.70% -> 1.41% (cluster interval 0.54-2.43%), all cells 0.80% -> 1.53%, swarm placebos 0.18% -> 0.27%; 2.22% when both windows rose; power at +10% 1.68% -> 3.22% |
| The holdout look (D2, release D-1b) | S-C | direction only, calls only: the pre-check, then the pooled entry-day t at least 1.00 and the holdout's P&L above zero | the lane 1.41% -> 10.37% on mixed worlds (9.57-11.16%; cluster 7.90-12.76%), 12.39% on 2022-24 worlds (upper bound 13.29%); all cells 13.37% / 14.11% (upper bounds 14.08% / 15.01%); swarm placebos 4.76%; power at +10% 3.22% -> 19.95%; adopted after it failed the operator's own 12% adoption rule (post-hoc); the section above |
| The leakage alarm | one count: 10 looks, over 30% | per lane; direction over 60% | a real direction holdout leak trips later; the paid review, the audit and the post-cutoff tail still check every look |
| The incubator mark | the drift screen alone (the owner's term, Sept 29-30) | direction-v2 for direction families | with no edge about -$36 a week expected, at most $150 a week (about $650 a month); its closes are never evidence |
| Graveyard DRIFT rows | bind every card | not a direction card | buried direction ideas may return, once each, inside the rebirth budgets |
| Graveyard alpha rows (PR #519, deployed 12:44Z Oct 9) | bind every card | alpha cards only: a direction card is bound only by direction families' rows (DRIFT never) | more direction births may retry ideas similar to dead alpha ones; each lineage still gets one Validation try and one holdout look at D2's measured 10.4% false-positive rate per program (mixed worlds); in the `dlane` report's header from the budget-split release (an owner deploy) |
| The Train map (PR #520, deployed 16:17Z Oct 9) | agents read the lane's rules and their own runs, never an operator study's figure | the architect sees the call shapes that pass direction-v2 on the Train years in the operator's census and its lessons; a direction researcher the lessons and the 5 best on its roots; labelled in-sample | births aim at in-sample winners; the screen's false-positive rate per program is unchanged; more programs reach the screen, so more false passes in count (more paid reviews and audits); in the `dlane` report's header from the budget-split release (an owner deploy) |
| The birth quota | no lane | direction about half while behind, at most 60% | alpha births fall from about 73 to about 36 a day mid-way through the game's T0 experiment; the researcher's ROLE prompt (a shared prefix) changes for alpha researchers too, so "alpha golden" holds for code paths only (the game's report says so while the lane is on) |
| The unit | MONEY's pre-registered $75 lane cap | 10% of equity (E5), as the live side | Probe-stage Done averaged over holds 6.3% against 7.8%; P(net <= -$360 in 8 weeks) 0.35 against 0.27 |
| K5's clear | no K5 before D-1 | `dlane.k5_clear` true clears a set K5 at once and disarms K5 while it stays true; the job's next run records the clear and re-arms K5 at -$600 below the net then (deleting the kv clears the same way) | while `k5_clear` stays true the lane can lose past any line with no K5 (the report warns every run); after a clear K5 measures a further -$600 from the net at clearing, not from inception |
| The Probe total (PREREG-T, Oct 10) | $400 net in total (release L-D's setting) | $800, the owner's ceiling (the window's $400 and every other money row unchanged) | with the -$300 line below (the pair as adopted): P(the agents' running real net, Probe/Sized and incubator, below -$400 within 12 weeks) 17.8% -> 36.8%, below -$600 0.6% -> 4.4%; 12-week 5th percentile -$396 -> -$679; P(drawdown stop by 24 weeks) 21% -> 48%; for P(Done) 4.6% -> 5.5% (12 weeks) and 11.6% -> 14.4% (24); zero-edge Done 2.2% -> 2.7% and 6.9% -> 9.0%. The total alone: 35.8%, 4.1%, -$674, 46%; P(Done) 5.3% and 14.2%. Measured at roster 5 alone: a roster rollback or another count needs this rollback too, or a new measurement (PT1; the section at the top) |
| The program loss line (PREREG-T, Oct 10) | -$200 | -$300 | one program may spend $100 more of the shared total before it is retired; its own step over the $800 total alone (paired): the running real net below -$400 within 12 weeks 35.8% -> 36.8%, below -$600 4.1% -> 4.4%; the drawdown stop by 24 weeks 46% -> 48%; zero-edge Done 2.5% -> 2.7% (12 weeks); for P(Done) 5.3% -> 5.5% (12 weeks; +0.24 points, SE 0.12: past PREREG-T's 2-paired-SE preference for the total alone by a hair, 2.06 SE). Roster 5 alone, as the row above |

Tightened: K5 (above); the screen, the alarm and K5's line can only tighten by a setting (the one setting that loosens
K5 is `k5_clear`, in the table above); D2 refused without a pinned receipt; E5 prices one lot at today's prices before
Validation. Release L-D's own loosenings (the NET budget, 8 slots, DM1) and its rolling budget (L9, a tightening of NET:
$400 of worst net stretch in any 20 sessions beside a net total, $400 as L-D set it and $800 since Oct 10) are in its
section and ride in the report's header too.

**The report** (`league/ops/dlane_report.py`; the House's `dlane` job at its start and daily 01:30Z, after the
`direction` closes and the fast lane's report, and since the weekend fixes 30 minutes before each open; in a pause too;
OPERATOR-ONLY, read-only on the swarm and live stores but for K5's kv, the trip and the clear recorded; no site data
contract changes). It writes `<state>/dlane-report.json`; with `dlane.mode` "off" it writes no report (a `skipped`
receipt) and, since the weekend fixes, still holds the program loss line (DONE-RULE-A1 A1.3: a due program is retired,
PL1 a House warning, the receipt carrying the figures). The fast lane's report rows gain `lane` while the lane is on
(off: no key).
- **The header:** the pinned Done rule (its sha256 `0d007696...`), every loosened and tightened rule with its cost, the
  contamination statement, the label "direction lane: leveraged index beta minus option costs; not alpha" on every
  direction figure.
- **The funnel per lane**, 24 hours and 7 days: births, Gym runs by window and their program-years (the Gym is shared:
  direction runs slow alpha's), Validation tries and passes, reviews and audits, holdout looks and passes by the screen
  each recorded, band moves, real closes by route; the bands now; the direction lane's Train-bar failure counts.
- **The Probe envelope** (`probe_envelope`): release L-D's budget as `money.Table` reads it from the constitution
  (`constitution`: `loss_basis`, `loss_budget_usd` over `loss_window_sessions`, `loss_total_usd`, `max_open`,
  `demotion`; on this tree "net", $400 in any 20 sessions, $800 in total, 8, "dm1"), never a figure of its own; the fast
  lane report's own figure (`in_force`); and under each basis, GROSS and NET (`by_basis`, from `real.probe_figures` told
  the basis by name), the window's realized figure (under NET its worst net stretch) and the total's, both rooms, the
  one that binds and the room in units of today's cap (10% of equity). A4 reads the room under the basis in force and
  names the binding envelope; A5 names `probe.demotion`.
- **THE DONE METER** (the pinned rule, read exactly): every real close of an agent program (never calibration, the House
  live test or `house:*`) since 2026-09-26T06:23Z on `:r`, `:t` and `:i`, the one agent real close before D-1 (tuition,
  Oct 8) included; realized after all fees (the broker's posted fees where they have posted, the book's estimate
  otherwise, labelled per close; an unpriced close makes the net unknown); `done_screen` (`:r` only) and `done_all` (all
  three); the bar is 30 closes, 5 closes from each of 2 programs, net > 0; every program with 5+ matched closes (a close
  on a day its version's nightly replay also traded; from the per-close fill replay of Oct 10, a close with a priced
  twin of its own, at the top of this page) has a live-minus-replay gap within +/-0.10 a dollar of maximum loss (a ratio
  of sums, D5's measure, `gap_measure`), and since the weekend fixes (DONE-RULE-A1 A1.1) at least 2 programs must be so
  measured: zero matched closes never passes. Every program is listed at each checkpoint with its closes, matched closes
  and gap (`by_program`, `replay_coverage`), never dropped. Item 7 is read per UTC day (`research_247`, below). It is
  READ only at the 30th close and every 10th after, each reading over exactly the first K closes; it holds when items 3,
  4 and 7 hold, and a Done claim needs it FINAL (A1.4: every counted close's replay landed, its own twin's once the
  twins are on, and its broker fees posted; then frozen); the running figures between are counts, never a reading.
  Beside it always: P(Done | zero edge) (2.7% at 12 weeks under the budget in force, the $800 total and the -$300 line,
  PREREG-T; 2.4% with 3-session holds under L-D's $400, DONE-RULE-A1 A1.2; 0.13 before), Net after costs
  (`done.net_after_costs`, from the close economics), the same-risk buy-and-hold two ways (delta-matched: the entry
  delta held in the stock; dollars at risk held in the index; approximations from daily closes), and, for each
  Candidate, Probe or Sized family, the screen that admitted it with its unconditional and both-windows-rose
  false-positive rates. A Done claim names which meter holds, at which checkpoint, from which routes. No program or
  route is paused, slowed or stopped to protect a figure.
- **The account and the costs:** the equity change since E0 (the first equity reading the report saw, kept in the
  file; not release L-D's deploy reading) beside the agents' and the House's realized closes and the account's other
  activity, the rest labelled unexplained; the swarm's BOOKED research spend by meter since the options swarm began and
  since the lane started, comparison only (the Net is `done.net_after_costs`, on the close economics' basis).
- **The contamination meters,** per lane: (a) the holdout's head-minus-tail Sharpe gap pooled over the looks, (b) the
  mean excess over the same-risk buy-and-hold on Validation (known) against live (unknown), (c) live against the holdout
  per band.

**The alarms** (each a House alert through the job; never an action on money):

| # | Condition | What to do |
|---|---|---|
| A1 | no direction birth in 12 h, the quota open, the lane started 12 h ago or more | nothing: the architect's next pass asks for direction proposals only; if it repeats, read the pass events' `lane_refused` |
| A2 | a direction version cleared every Train bar 24 h ago or more, and no direction Validation try or look since | plumbing: read the tournament's candidate and the gate's holds for those families |
| A3 | a cleared direction best waits for Validation over 6 h, or a direction Validation pass waits for its look over 12 h | a stall: the tournament round or the gate (its review, audit or look hold) |
| A4 | Probe budget room under one unit while a direction Candidate or Probe has fewer than 5 real closes | no path to Sized: report; the budget is never topped up by hand |
| A5 | a direction Probe or Sized program's live fills below its replay by over 0.10 a dollar of maximum loss over 5+ matched closes | watch: D5 demotes at 0.20; no new Probe in that structure until the fill model is explained |
| A6 | fewer than 1 eligible direction version per 50 direction births over 48 h (judged from 50 births) | report the failure counts; never a loosening without a new pinned measurement |
| A7 | more than half of the direction versions that clear E1, E3 and E4 fail E5 | report today's cap and the median failing one lot |
| A8 | a FINAL checkpoint holds (`info`, once a checkpoint; since the weekend fixes only on a final reading, naming items 3, 4 and 7) | read it with the buy-and-hold, P(Done \| zero edge), Net after costs and the contamination meters; it stops nothing. The `stall` job mails the final holding checkpoint at once (its `done` cause, which stands until a notice is sent) |
| DC1 | a Done meter's latest checkpoint (`done.all` or `done.screen`) is final and does not hold, or is still not final at the pre-open of the 2nd session after the New York day of its last counted close (`DC1_SESSIONS`; the `dlane` run at open − 30 min). By design a close is final at the next session's pre-open (a Friday's at Monday's, one before a holiday at the session after it), so this leaves one session of slack (a warning, Oct 15, 2026). A final one's text gives the close count and the items that do not hold. A reading that is not final names no verdict (item 3 holds the net's sign): only the close count, the sessions since and `final_why`. No text has a dollar figure, net, program row or buy-and-hold (a `final_why` clause with a figure is left out) | read the checkpoint in `dlane-report.json` (`done.<meter>.latest`). A House warning, never an owner step: it stops nothing and never fails an item-7 day. A final failing one stands until the next checkpoint |
| PL1 | a program's own realized Probe net is at or below the program loss line (`dlane.program_loss_usd`, -$300 since Oct 10; -$200 before; DONE-RULE-A1 A1.3) | none: the job retires it swarm-side the same run (its real positions exit by the House's rules); the report's `program_loss.retired` names it |
| PT1 | the constitution's Probe total is above $400 or the program loss line below -$200 (the $800 total and the -$300 line, Oct 10), and `dlane.roster` is not 5 (off, closed or another count) | the pair was measured at roster 5 alone: roll it back (an owner deploy: the $800 section at the top), put `dlane.roster` back to 5, or measure the pair at this roster first |
| A9 | every live direction program opened nothing for 10 sessions (`info`) | none: the lane is flat by design |
| K5 | `dlane_k5` is set | the lane is in shadow until the operator clears it (**K5**, below) |
| K5 (disarmed) | `dlane.k5_clear` is true | no loss trips K5 while it is: once the report shows the clear recorded (`k5.last_clear`, the new `k5.line`), take `k5_clear` out of `swarm.json` |

Stop conditions beyond the code's: K8, 7 days after D-1 with no direction look pass: if D2's receipt qualified and D2 is
not on, pin it (an owner deploy of `policy.json`); otherwise report "the screen route is closed in this world" and keep
the incubator route. K9, Nov 9 with fewer than 2 programs at Probe: re-plan and report that Done is not reachable inside
the walls on this evidence. Neither is ever a forced or hand-placed trade.

**The owner's deploy, in order** (the money path's window, 20:05-13:25Z on a trading day; never 12:55-20:05Z; no order in
flight; L-D deployed and verified first: done, 09:04Z Oct 9, House release `20261009T090334Z-cdbf1864a573`):
1. CI green on main's head with D-1 merged (`gateway`, `tests (3.11)`, `tests (3.14)`); the alpha golden tests in it.
   Merging holds the updater's later heads until the owner deploys main's head.
2. The gateway first: `protected.mjs` gains `league/swarm/dlane.py` (its parity test green), then
   `npx wrangler@4.129.1 deploy` (**The protected paths**).
3. `floor_box.py deploy` from `~/Work/ltcm-deploy` (a clean detached checkout of main's head); rollback ready.
4. Verify: the release id; `floor_box.py status` `current`; the money digest unmoved (L-D's `0310779c`) and the
   execution fingerprint unmoved (L-D's `31a7e921`: `python3 -c "from league.swarm.evaluator import
   execution_fingerprint; print(execution_fingerprint())"` on both trees; the kv `research_evaluator` unchanged: no
   adoption ran); the first architect pass's `swarm.architect` event carries `lane_births`; the first direction births'
   `swarm.born` payloads carry `lane`; the `dlane` job's first receipt is `ok` and `<state>/dlane-report.json` reads
   `lane.mode_effective` "gate".
5. Install agenda v21 (below), then nothing else: `policy.json` already sets `dlane.mode` "gate", so the plan's N2
   override in `swarm.json` is not needed (set `dlane.mode` "shadow" there for a staged start).

**Install agenda v21** (the operator's private file; the public repository never holds an agenda), on the box, right
after D-1 verifies and never before (before D-1, `equity_premium` is no class and the lane field is dropped):
1. Copy the pinned file to the box (it never enters the repository), e.g. `/workspace/state/agenda-v21.txt` (mode 600).
2. `cd /workspace/current && /workspace/.venv/bin/python scripts/agenda_install.py check /workspace/state/agenda-v21.txt`:
   exit 0 and `"problems": []` (at most 4,000 characters, ASCII, no hidden year); its `sha256` is the pinned one.
3. `... scripts/agenda_install.py apply /workspace/state/agenda-v21.txt`: it keeps `swarm.json.before-agenda-<stamp>`,
   writes the text into `architect.agenda_locked` and `architect.agenda` (temporary file, read back, mode 600, atomic
   replace) and clears the strategist's section (`architect_agenda_section`; `--keep-section` leaves it). The swarm
   reads it on its next loop: no restart.
4. Verify: the tool's `written` lengths and sha256 are the file's; the next architect pass ran (`swarm.architect`,
   with `lane_births`); the swarm raised no "agenda guard" warning.
The tool refuses (exit 2, nothing written) a text over 4,000 characters, non-ASCII, empty or naming a hidden year.

**K5.** Read the kv: `sqlite3 'file:/workspace/state/swarm.sqlite?mode=ro' "SELECT key, value FROM kv WHERE key IN
('dlane_k5','dlane_k5_base')"` (or the report's `k5` block: `line`, `base_net`, `trip_open`, `last_clear`). Before
clearing it, re-plan (the plan's K5: the lane's losses passed its line) and decide, as separate steps, whether to set
`live.incubator` false and, in the next owner window, `probe.max_open` 0. To clear, either:
1. set `dlane.k5_clear` true in `swarm.json` (keep a before-copy; read every loop: the lane opens at once). The `dlane`
   job's next run (the House's start, 01:30Z, or since the weekend fixes 30 minutes before an open) records the clear:
   it deletes the kv and writes `dlane_k5_base` with the lane's net then, so K5's next line is `k5_net_usd` below that
   net. Then take `k5_clear` out: while it is true K5
   cannot trip at all, and the report warns every run (`K5 is disarmed`); or
2. delete the kv on the box (`cd /workspace/current && /workspace/.venv/bin/python -c "from league.swarm.store import
   SwarmStore; s=SwarmStore('/workspace/state'); s._exec(\"DELETE FROM kv WHERE key='dlane_k5'\"); s.close()"`). No
   setting is needed: the job's next run sees the open trip with no kv and records the clear the same way (at the net
   then; until that run nothing trips, as only the job trips K5).
Never delete `dlane_k5_base` by hand: K5's line would go back to -$600 since inception and trip again at once.

**Roll back.**
- **The lane off, at once:** `dlane.mode` `"off"` in `swarm.json` (keep a before-copy; replace atomically). Read on
  the next loop, no restart. Every family is alpha again (`lane_of`), no direction card is admitted, no quota, LANES
  block, direction score, screen or text is used, the `dlane` job writes no report (since the weekend fixes it still
  retires a program at the program loss line, A1.3, whatever its lane), the fast lane's rows carry no lane, and
  the agenda guard is silent: every path is the release before D-1, byte for byte. Direction families alive then go on
  as alpha families under the alpha rules (their spec and card keep `lane`, read again if the lane comes back on). A set
  K5 kv stays and is harmless while off. The leakage alarm is the one count again, over the looks the alpha line judged
  (direction looks made while the lane was on are left out).
- **Shadow** (`"shadow"`): births, research and Validation go on; no direction Candidate, no incubator direction mark.
- **Agenda v21 back to v19.1:** `scripts/agenda_install.py apply` the v19.1 file (or restore the tool's before-copy of
  `swarm.json` with the same atomic replace). Do this with the lane off: v21 names `equity_premium` and the lane field,
  which the alpha rules refuse.
- **The code:** `floor_box.py rollback` (it restores code only). No re-ratification (the money digest did not move).
  Set `dlane.mode` "off" or agenda v19.1 first, as above: the previous release has no `dlane` block and ignores it, but
  its architect would read v21's lane words and refuse every direction proposal. The previous release's leakage alarm
  counts EVERY look, the direction lane's S-C looks included: once direction looks exist, check the pooled pass share
  first (`sqlite3 'file:/workspace/state/swarm.sqlite?mode=ro' "SELECT count(*), sum(passed) FROM looks"`; at 10 or
  more looks with over 30% passed the old code stops the whole gate and writes the kv `leakage_alarm`), and prefer
  `dlane.mode` "off" on this release, which counts only the alpha line's looks.

## Release L-D (Oct 9, 2026): deployed 09:04Z Oct 9 (House release `20261009T090334Z`, main `40c39435`)

The one planned evidence reset of Oct 9 (the plan of Oct 9, "L: Release L-D", and its critic). Claude's decisions under
the owner's goal of Oct 7: item 4 ("You may set Probe sizing up to 10% of equity at risk per position and a Probe loss
budget up to $400 in total") and item 5 (every loosened rule reported with its cost); and, for the budget's two figures
(L9), the owner's goal as he re-set it on Oct 9 (about 06:20Z), item 4: "Probe loss budget: $400 net in any rolling 20
sessions and $800 net in total (realized Probe losses net of Probe gains, plus the maximum loss of everything open)".
Production runs main `ccfa48d5` (House release `20261009T025942Z`) until it ships. The 10% cap is unchanged; the $400
becomes a rolling 20-session figure beside a $400 total (the owner's ceiling is $800: L9, below); three rules of how the
Probe stage spends them loosen, and the routes beside it keep their room. It changes `league/live/`: the execution fingerprint moves (an evidence reset); the
Gym bundle does not (L5, the marketable natural limit, was dropped on Oct 9 for that reason: **What the deploy
resets**, below); and `league/constitution.py` (the money digest moves: the standing grant re-ratifies by itself at the
House's start).

- **L1, the budget read NET** (`options_money.probe.loss_basis` "net"; allowed exactly "gross" and "net",
  `OPTIONS_MONEY_CHOICES`: "Net", "" or a missing row is refused and nothing trades). The realized part of THE PROBE
  LOSS BUDGET is max(0, -(the summed cash of every closed position a Probe family opened)), from inception, in place of
  GROSS, each such position's own loss summed (`real.probe_tally`; `money.plan_open`'s envelope: realized + every real
  position's open maximum loss + the new open <= $400, two envelopes since L9). A Probe gain now offsets Probe losses;
  a Sized gain never does (it carries no Probe mark). It REVERSES the fast lane review's deliberate GROSS choice of Oct 7 ("a net
  figure let a Sized gain or a Probe gain refill the budget"). The refusal reads "realized net"; the House warning names
  the basis; `fast-lane-report.json` `probe_budget.realized_basis` names the basis in force (it was a fixed "gross").
- **L2, 8 Probe slots** (`probe.max_open` 3 -> 8, its bound 0-3 -> 0-8). The count only: the envelope keeps open Probe
  risk at or under $400, below the daily stop's $451.27 at E = $1,289.34; the dollars bind first (three $129 units fit,
  eight $50 units). Below E = $1,142.86 the $400 is more than the daily stop's line (3 x 10% never was).
- **The Probe room capped at the budget** (the critic, B1). The incubator, the House live test and the calibration keep
  `money.probe_room` of the book's and the day's caps for Probe opens: now min(`max_open` x 10% x E, $400). At 8 slots
  the old formula claimed $1,031.47 at E = $1,289.34 and refused every incubator open; capped, it is $400. At 3 slots
  it is what it was at any E up to $1,333.33 ($386.80 at E = $1,289.34); above that, the $400 a Probe open can hold.
- **L3, DM1 demotion** (`probe.demotion` "dm1"; allowed exactly "dm0" and "dm1"). For a family at Probe or Sized, D5's
  loss leg (-3 x its mean maximum loss) and the forward-negative demotion are off; it is demoted (sticky, exits only,
  back to Candidate) when its version has 10 or more real trades whose returns on maximum loss sum below -1.645 x sigma
  x sqrt(n). Sigma: the sd of r in the banded version's Validation run (the live row's `validation_r_sd`, read by
  `league/live/families.py` from the swarm's state keys `validation_r_sd_by_version` and `validation_r_sd`; the swarm's
  WRITER ships with release D-1, so until then it is absent), else the forward record's sd (its nightly, shadow and real
  days; with 10 real trades the record always has 10), else 2.0. D5's replay-gap leg and the real_bad hold are kept; a
  Candidate keeps every "dm0" check (the negative record included) and DM1 too. Sticky: DM1's line moves with sigma
  (the Candidate's shadow days keep adding to its record; D-1 brings the Validation sd), so the live path keeps the
  version it demoted (live state `dm1_demoted`) and holds it at Candidate for good, whatever sigma or `probe.demotion`
  reads later (`live.band` held rows: "DM1 demoted version N for good"); a new version starts its own record. The live
  path's band, its open refusal and its admission read one answer (`money.negative_demotes`, `money.live_demotion`). It
  applies to every Probe or Sized family, alpha too: the live row carries no lane (no alpha family is near Probe).
- **L9, THE ROLLING PROBE BUDGET** (the owner's goal of Oct 9, item 4, quoted above). `probe.loss_budget_usd` ($400) is
  now the ROLLING figure, over the last `probe.loss_window_sessions` (20) New York trading sessions, today included,
  counted on the repo's NYSE calendar (`ltcm.data.us_equity_session`: weekends, the holidays computed by rule, the
  special closures; `real.probe_window_start`), a close's session its New York close day; beside it the new
  `probe.loss_total_usd` from inception, set to $400 ($800 since Oct 10, at the top): the owner's "$400 net in any
  rolling 20 sessions" is a wall, read as the worst net stretch, and his "$800 net in total" a ceiling, so the total is
  a tighter setting inside it (the operator's decision of Oct 9, after the budget simulation's worst-stretch run,
  **Cost**, below). Each realized figure is `loss_basis`'s over the closed Probe positions it covers. "gross": their
  losses summed. "net": the total's is max(0, -their summed cash) from inception, and the window's is its WORST NET
  STRETCH, the largest max(0, -(the summed cash of the closes on or after s)) over the window's sessions s
  (`real.probe_realized`; the review of L-D, Oct 9): a Probe gain offsets only the Probe losses closed before it in the
  window. With the window's plain net (the build before the review) a +$300 close let $700 of later losses be admitted
  against it, and once the gain aged out the next 20 sessions held $700 net with every open having passed; with the
  worst stretch "$400 net in any rolling 20 sessions" holds over EVERY 20-session window as an outcome, not only at each
  open, and the $400 total from inception (residuals aside: fees above the book's estimate, a structure broken leg by
  leg; `test_ld_release.TheRollingOutcome` runs seasons of admitted opens and checks every window). Under "gross" the
  worst stretch is the whole window, so the figure is the plain sum. A Probe open goes only if BOTH the window's
  realized + every real position's open maximum loss + the open <= $400 AND the total's realized + the same <=
  `probe.loss_total_usd`, $400 (`money.plan_open`; `real.probe_figures` gives both to `RealBook.exposure`); the refusal
  names the envelope that binds ("probe: the loss budget: ... over $400 in any 20 sessions" or "probe: the loss budget
  in total: ... over $400 in total"), exits always go on, and the House's once-a-day warning gives both budgets, both
  realized figures, the open maximum loss and the basis. `fast-lane-report.json` `probe_budget` adds
  `realized_total_usd`, `total_budget_usd`, `window_sessions`, `window_start` and `binding` (`realized_usd` and
  `room_usd` are the window's, its worst stretch under "net", and the tighter envelope's). Bounds: the window 20-2000
  sessions (a longer window is never looser, under either basis: more losses under "gross", more stretches under "net";
  2000 is the rollback's), the total $0-800 (the owner's ceiling: raising the total to $800 later is a CON-only change,
  the money digest moves and the fingerprint does not). Open Probe risk stays at or under $400 (the window's envelope
  alone), so L2's reasoning and `money.probe_room` (min(`max_open` x 10% x E, $400)) are unchanged. Cost, as set: the
  worst net Probe loss from inception stays $400, as under NET alone, and the window adds a second wall: no 20 sessions
  lose more than $400 net, even after earlier Probe gains have refilled the total. A bad stretch that ages out of the
  window frees no room in the total; only Probe gains do. Its measured cost is under **Cost**, below.
- **Not done: the narrower fingerprint** (the critic, N8, optional). `league/live/money.py` stays in the execution
  fingerprint: the practice book's caps read `money.Table` (`shadow._probe_caps`: its open count and family share, and
  a refused table refuses every practice open), and the incubator's pre-registered first-look rule (`practice_ok`)
  lives there, so a money.py change can change practice fills without any other fingerprint move. Every later money-rule
  change in `league/live/` is therefore an evidence reset too (rule F0, below).

**Cost** (MONEY's ladder of Oct 9: the Probe stage alone, 8 weeks, U10% of E, no edge unless said; Done is 30 real
closes, consistent and net positive, averaged over 2/3/5/8-session holds at +5% edge; a model's figures, not this
account's):

| Step | P(net <= -$360) | P(net < -$400) | Mean net: no edge / as traded | Done |
|---|---|---|---|---|
| Fast lane v2 (gross, 3 slots, dm0) | 0.19 | 0.6% | -$8 / -$45 | 0.3% |
| + NET | 0.27 | | -$14 / -$64 | 2.6% |
| + DM1 | 0.30 | | -$16 / -$65 | 3.3% |
| + 8 slots (L-D) | 0.35 | 2.1% (through Sized, outside the budget) | -$20 / -$71 | 6.3% |

- **NET's main effect** (the critic, B2: MONEY's pinned paths over 12 weeks at U10%-M8-net-DM1). Probe gains refill the
  budget, so gross Probe losses pass $400 on most paths: P(gross realized Probe losses > $400) 0.65-0.72 / 0.56-0.62 /
  0.46-0.50 at 2 / 3 / 5-session holds (p95 $2,005-2,088 / $1,709-1,744 / $1,318-1,338); P(the Probe's peak-to-trough
  realized drawdown > $400) 0.45-0.48 / 0.40-0.42 / 0.32-0.34 (worst $2,218-2,322 / $2,134-2,385 / $1,923-2,192);
  P(net Probe < -$400) at most 0.5% / 0.8% / 2.5%. Under GROSS every one stays at or under about $440. Of the three
  readings, NET is the loosest: 12-week Done with 3 programs at Probe, 3-session holds, zero edge: GROSS 0.5%, a
  high-water mark 3.3%, NET 12.9% (+5% edge: 0.7%, 4.7%, 15.6%). Chosen: NET (Claude, Oct 9: the only reading under
  which 30 real closes are reachable; the daily and drawdown stops still bound the whole account).
- **DM1's cost** (the critic: 4,000 bootstrap paths of 30 closes over the 29 cells the direction bar admits): it fires
  within 30 closes 6.5-13% of the time at zero edge, 14-22% at -0.10 a dollar of maximum loss, 29-36% at -0.25 (D5:
  77%, 83%, 90%). A losing program trades longer; the shared $400 envelope, not demotion, is what mostly stops it, and
  one bad program can spend every program's room.
- **The rolling budget's cost** (L9, as set: $400 of worst net stretch in any 20 sessions AND $400 net in total). The
  figures above are MONEY's, under one $400 from inception; the window's are the budget simulation's of Oct 9, its
  worst-stretch variants (seed 202610097, the same 2,000 paths a hold for every row, the D2 screen, 30 direction
  programs, money rules U10%-M8-net-DM1; post-hoc, as traded, holds of 2 / 3 / 5 sessions):

  | Probe loss budget | P(Done) 12 wk | P(Done) 24 wk | P(net Probe < -$400 within 12 wk) | P(60% drawdown stop by 24 wk) |
  |---|---|---|---|---|
  | $400 net in total, no window (L1-L3 alone) | 10.0 / 7.6 / 4.5% | 11.0 / 9.0 / 7.6% | 1.3-2.8% | 8.2-13.0% |
  | $400 window + $800 total (the owner's ceiling) | 7.0 / 3.7 / 1.1% | 14.0 / 10.9 / 7.2% | 37.6-39.2% | 41-46% |
  | **$400 window + $400 total (L-D's setting; the $800 total is in force since Oct 10, at the top)** | 6.0 / 3.3 / 1.0% | 11.1 / 8.7 / 5.9% | 0.9-2.1% | 3.0-8.3% |

  The window costs early Done (a Probe gain no longer refills it for the losses after it, so the first 12 weeks trade
  less). The $800 total buys 1.3-2.9 points of 24-week Done at 18-42 times the chance of a net Probe loss past $400
  within 12 weeks and about 5-14 times the chance of the account's drawdown stop by 24; the setting in force keeps both
  tails at or below where NET alone had them. Raising the total to $800 later is a CON-only change (the money digest
  moves; no fingerprint move, no evidence reset). The simulation's first run modelled the window as a plain rolling
  sum (11.7 / 8.6 / 3.5% and 13.6 / 11.6 / 8.9%), the build before the review, not the rule that ships.

**What the deploy resets** (the evaluator adoption at the House's start: `league/live/` changed, `league/gym/` did not).
As fast lane v2's: every alive family's bests, Train candidates, robustness, validation line and review are re-derived
(about 15 families, about 8 Gym-hours on 2 boxes); looks, trials, refusals and forward rows are kept. No family is
banded, so no band is lost.

**The Gym bundle does not move** (production's `gym-engine-4-e1c896f8d304`). L5, the marketable natural limit
`{"natural": k}`, was dropped from L-D on Oct 9 (the operator's decision, about 07:40Z) for that reason: it changed
`league/gym/legs.py` and `league/gym/PROGRAM.md`, which moved the bundle, so the adoption would have reused no stored
Train or Validation result (every one re-run on the 2 Gym boxes the direction lane shipping that day needs) and cleared
the 2017-19 extension holds, the operator's clears included; `{"price": v}` already lets a program pay through. It waits
for a planned Gym release (rule F0, below). So, as at fast lane v2, the re-derivation reuses recorded results (the same
image and bundle: `evaluator.gym_changed` is false), and the extension holds and their clears stand.

**Every active practice cohort is completed** ("evaluator changed; a new version needs
fresh practice", `observe.cohort_candidates`), the 10 still active of the 12 alpha cohorts admitted on Oct 8 among them:
their incubator first looks (expected about Nov 4-10 under the 30-session window) never come, and a completed (family,
version) never practises again (the plan weighed this: about 4-6 real closes in all, from programs with no measured
edge). Practice refills from versions
that qualify under the new evaluator. After L-D, rule F0 holds: no `league/live/` or `league/gym/` release while any
family (direction or alpha) is Candidate, Probe or Sized, except a money-safety fix, whose cost is that band.

**Identities.** Constitution digest `5698a2f9` -> `ca89ff8a`; money digest `1665c385` -> `0310779c`; the execution
fingerprint `b4c34031` -> `31a7e921` (check a tree with `python3 -c "from league.swarm.evaluator import
execution_fingerprint; print(execution_fingerprint())"`); the Gym bundle unchanged, `gym-engine-4-e1c896f8d304`
(`python3 -c "from league.gym.driver import build_bundle; print(build_bundle()[1])"`). The CON-only rollback's money
digest is `320899d6`, its constitution digest `c9d8ef5b`.

**The owner's deploy, in order.** (1) CI green on the exact head; rollback ready (`floor_box.py rollback` to
`20261009T025942Z`); no order in flight; never 12:55-20:05Z on a trading day. (2) `floor_box.py deploy` from
`~/Work/ltcm-deploy`. (3) At the House's start the `grant` job re-ratifies on `0310779c` by itself (receipt `ratified`,
trigger `digest`; `python3 scripts/live_trading.py --ratify` on the box if it refuses), and the adoption runs (its
`research_evaluator` row carries the new execution fingerprint). (4) After the `fast_lane` job, `<state>/fast-lane-report.json`
`probe_budget` reads `max_open` 8, `realized_basis` "net: ...", `window_sessions` 20, `budget_usd` "400" and
`total_budget_usd` "400"; the practice cohorts active before the deploy read
completed, reason "evaluator changed; a new version needs fresh practice"; `research_evaluator` (the swarm store's kv,
`sqlite3 'file:/workspace/state/swarm.sqlite?mode=ro' "SELECT value FROM kv WHERE key='research_evaluator'"`) reads
`execution` `31a7e921...` with the `bundle` (`gym-engine-4-e1c896f8d304`) and the image unchanged, and
`scripts/extension_hold.py --state /workspace/state` lists the holds it listed before the deploy. (5) Tell the owner in
one line the same hour (NET reverses a reviewed decision and loosens how his $400 is counted; the total is set at $400,
inside his $800).

**Roll back.** The real rollback is CON-only: set `options_money.probe` `loss_basis` "gross", `max_open` 3, `demotion`
"dm0", `loss_total_usd` "400" and `loss_window_sessions` 2000 in `league/constitution.py` (re-pin `PINNED_DIGEST` to
`c9d8ef5b...`, the full digest `league/tests/test_constitution.py` names), one owner deploy. Each value runs fast lane
v2's rule (`league/tests/test_ld_release.py` checks it against a frozen copy of `ccfa48d5`'s code): "gross", 3 and "dm0"
code for code, and the 2000-session window holds every close since the fast lane (it reaches before the calendar's first
year), so the window's figure is the total's and both envelopes are fast lane v2's one $400 envelope: the same
admissions and refusals on the same rows (a refusal's words end "in any 2000 sessions"). The money digest moves to
`320899d6` (the grant re-ratifies at the House's start, as above) and the execution fingerprint does NOT move: no
evidence reset, no band lost. The room stays capped at $400 (at 3 slots it differs only above E = $1,333.33), and a
version DM1 demoted before the rollback stays a Candidate (`dm1_demoted`). With `loss_total_usd` at "400" (the $800
total's rollback, at the top), rolling back L9 alone (`loss_window_sessions` 2000, the other three rows kept) is
CON-only too, but it is not the rule of the build before L9: under "net" the 2000-session window's figure is its worst
net stretch since the fast lane, which is the Probe's drawdown from its high-water mark, so the $400 then binds as the
critic's high-water-mark reading (tighter than NET from inception, which the $400 total also checks); "gross" makes it
fast lane v2's. `floor_box.py rollback` to `20261009T025942Z` instead moves the fingerprint again (one more reset: every
band and practice cohort at that moment) and, once release D-1 has shipped, drops D-1 too; use it only for a broken
release, never to undo a rule.

## The incubator cap (Oct 8, 2026): deployed Oct 8 (House release `20261008T225723Z`, main `a5ff6f9e`)

One money row moves: `options_money.incubator.max_loss_usd` "50" -> "75" (its bound in `OPTIONS_MONEY_BOUNDS` $0-50 ->
$0-75). It is Claude's decision under the owner's goal of Oct 7: item 4 allows up to 10% of equity at risk per Probe
position ($128.84 at E = $1,288.40), and item 5 asks every loosened rule reported with its cost. Nothing else moves:
`week_loss_usd` $150, `max_open` 4, `contracts` 1, the practice rule, the Probe, tuition, calibration, the House live
test, the gateway rows of the table and the gateway's own vars (it has no incubator cap; its per-order cap, the lower of
$1,000 and 25% of E, is $322.10 at that E).

- **What it loosens.** One row, two caps: a structure's maximum loss with its fees, and what a family holds and works,
  each $50 -> $75 (`money.plan_incubator`). The week's bound is unchanged ($150 of net realized loss plus residuals;
  about $650 a month on average, $750 in a five-week month), so at most two $75 units are open at once (three $50 ones
  before it).
- **Why.** The incubator audit of Oct 8 found the $50 cap refuses most one-lot units of the single-name cohorts. Share
  of one-lot units (maximum loss plus open and close fees) at or under $50 -> $75 in the active cohorts' Gym Train
  trades: semis-lead-smallcap 4% -> 71%, smci-mara 40% -> 71%, opening-range 40% -> 62%, china-tech 55% -> 77%,
  peer-skew 50% -> 71%, index-corr 83% -> 98%, earnings-gap 10% -> 17%, megacap 0% -> 3%, semis-supply 2% -> 2%.
- **Cost.** Replayed on the 10 live cohorts' eligible Train runs, with the practice and route caps and no edge after
  costs (-8% of maximum loss a trade, the placebo median), the expected real loss per first-look pass:

  | Practice window | $50 | $75 | Maximum loss sent per pass | Worst simulated pass |
  |---|---|---|---|---|
  | today's (10-18 sessions) | -$0.40 | -$2.45 | $20 -> $224 | -$126 -> -$121 |
  | 30 sessions | -$2.22 | -$25.53 | $53 -> $145 | -$272 -> -$419 |
  | 40 sessions | -$5.52 | -$26.59 | $71 -> $164 | -$310 -> -$424 |

  A worst pass spans several weeks, each within the $150. With zero edge (E = 0) the means are noise around $0. The
  trades are in-sample Train trades over overlapping windows, so read the figures as rough.
- **Alone it opens nothing.** On this tree no cohort holds the Train-and-drift mark the incubator's facts need (the
  tournament's drift screen is off since fast lane v2: its **Stated consequences**, below), and in the audit's replay
  11 of the 12 cohorts never reach the first look's 10 program closes inside today's windows (semis-lead-smallcap about
  half the time). The cap matters once those are fixed, a separate change.

**Identities.** Constitution digest `5edc8956` -> `5698a2f9`; money digest `da5c7542` -> `1665c385`; the execution
fingerprint `b4c34031` and the Gym bundle are unchanged (no `league/gym`, `league/live` or base-file change), so there
is no evidence reset and the practice cohorts carry over.

**The owner's deploy, in order.** (1) CI green on the exact head; rollback ready (`floor_box.py rollback` to the
running release); no order in flight. Merging it holds every later head of the updater until main's head is deployed
by the owner (the constitution is protected), so deploy it right after the merge. (2) `floor_box.py deploy` from
`~/Work/ltcm-deploy`. (3) At the House's start the `grant` job re-ratifies on `1665c385` by itself (**The standing
grant**): its receipt reads `ratified` with the trigger `digest`; if it refuses, `python3 scripts/live_trading.py
--ratify` on the box. (4) `health.json` `options_live.incubator.table.max_loss_usd` reads "75".

**Roll back.** `floor_box.py rollback` is an owner's release change too, so at the House's start the grant re-ratifies
on `da5c7542` by itself (read the receipt; `--ratify` if it refuses). A structure opened under $75 is held and exits as
its program says; no new open is over $50.

## The learning game v1 (Oct 8, 2026): deployed Oct 8 (House release `20261008T190618Z`, main `7b71cb1a`), T0 22:17Z

From T0 no agent sees 2020 or 2021 again, and those two years, scored privately, decide which programs reproduce and
which reach Validation. Researchers keep working on Train 2022-2024 exactly as before. The build spec (Oct 8) holds the
rules, their numbers and the measurement plan; the code is `league/swarm/game.py` (its docstring states every rule). It
ships only by the owner's deploy: it changes `league/swarm/tournament.py`, `league/swarm/policy.json`, `league/ci.py`,
`league/ops/` and the gateway's protected list, and the gateway's held `league/swarm/researcher.py`. Nothing under
`league/gym/` or `league/live/` and nothing in `league/constitution.py` changes: **the execution fingerprint and the
money digest do not move**, there is no evaluator adoption, and Validation, the gate, the holdout look and Probe sizing
are as they were. The one evidence reset is the span switch (below).

**What it does.**
- **Arms.** A family born after T0 whose birth roots are all in the core five plays: its LINEAGE's hash
  (`canary.in_arm`) puts half in the game arm and half in the control arm, so a child stays in its parent's arm.
  Families born before T0, or born with any other root, are legacy: today's rules, no looks. A family's first arm is
  kept (table `game_arms`): a researcher's later change of roots, a setting change (`arm_fraction` applies to new
  lineages) or the game switched off never moves it. Once the game has started, the architect bears on the core five
  only.
- **Looks** (both arms). When a version's 1.5x seen run lands with a profit and the version is the family's best by
  Train score, beats its last looked score by 0.5, its program was never looked at in its lineage, the family has used
  fewer than 4 looks and has none out, one private Train job runs it over 2020-01-02..2021-12-31 at 1.5x (`purpose`
  "private": never a `runs` row, a trial, a notebook line or a view; split in 8 as the retro ran it). The triggers are
  a state: a best that met them while a look was out is looked at when the look lands or at the next round. Control
  also gets a record of every version the tournament validates, once a program. A failed hidden run is queued again
  after 2 h, 3 attempts in all; a program the Gym ends on the hidden years (disqualified, no data, refused) is a landed
  look with both years ineligible. A program is looked at once in its lineage, whatever that look's end.
- **Fitness.** Per hidden year, F = min(the year's all-days t, its drift-adjusted alpha t), eligible with 40 trades on 20
  days and every root of the program with data. Each lineage has a SELECT year and a CONFIRM year (a hash).
- **Gate mode, game arm.** A SELECT PASS (F >= 1.28) reads the CONFIRM year once (at most 2 reads a family, 3 a lineage);
  a PASS that landed in "shadow" is read at the first "gate" round; the family's candidate for Validation is its latest
  CONFIRMED version not yet judged, none without one; 2 Validation tries (of CONFIRMED versions only); its
  Validation t never steers its compute (allocation `t` None); children of the top decile of the last 72 hours' SELECT
  figures (F >= 1.0 before 30 looks), at most 4 a round and 24 a day, each version 1 its parent's looked program plus one
  structural directive (or, 20%, a donor's execution); never forked; three retirement rules first (4 looks without a
  pass, 2 failed CONFIRM reads, 2 failed Validation tries), under the floor, each retiring with the same public words
  ("retired under the learning game's rules"; the report's R5 counts them by rule). The dormancy clause spares such a
  family only while its CONFIRMED version awaits a Validation it can have or a look is out (its best is never validated
  otherwise).
- **What agents see.** A game-arm researcher in "gate" reads one PRIVATE EXAM line in its status (looks used, never a
  figure, tier or year); a child's brief carries its change. The architect and the strategist never read a game-arm
  family; every reader's graveyard drops game-arm rows and the rows of families born before T0 and retired since the
  2020-21 switch (Sept 28 16:10Z: they learned on the hidden years), and their families too. Once a T0 exists this
  holds whatever `game.enabled` says. A family's own views count no trial or mechanism verdict of a child the game bore
  beside it (a parent never reads that it bred), and the architect's and strategist's research shares are renormalized
  over the rows they read. The public site shows no game child. Once the game has started (on, T0, the seen span) the
  strategist's section is refused if it names 2020 or 2021 in digits, and the input card shows "span_mismatch" until it
  is re-audited over 2022 (T0 step 5). Control and legacy researchers otherwise see exactly what they saw before, over
  2022-2024.
- **Practice feedback off** (`practice.feedback` false): no practice P&L in any researcher's status, no practice bonus,
  for both arms.

**The switches** (`league/swarm/policy.json`; `<state>/swarm.json` wins over it):

| Key | Committed | Bounds and notes |
|---|---|---|
| `game.enabled` | `true` | anything but JSON `true` is off |
| `game.mode` | `"gate"` | `"shadow"`: looks recorded for both arms, every game-arm rule off; anything else reads as `"shadow"` |
| `game.arm_fraction` | 0.5 | [0, 1] (0: no new lineage in the game arm); it decides new lineages only: a family's first arm is kept, so GO-WIDE's 1.0 is for new births |
| `game.eta`, `game.looks` | 0.5, 4 | 0.25-1.0; 1-6 |
| `game.c_select`, `game.c_confirm` | 1.28, 1.28 | 1.0-2.33 |
| `game.confirms_family`, `game.confirms_lineage`, `game.val_tries` | 2, 3, 2 | the family's at most the lineage's; lineage at most 3; tries 1-4 |
| `game.parent_quantile`, `parent_window_hours`, `parent_min_looks`, `parent_bootstrap_f` | 0.10, 72, 30, 1.0 | |
| `game.children_per_parent`, `children_per_round`, `children_per_day`, `child_cooldown_hours` | 3, 4, 24, 6 | a round at most the day; a day at most 48 |
| `game.crossover_share`, `donor_max_chars` | 0.2, 6000 | |
| `game.look_retry_hours`, `look_attempts` | 2, 3 | |
| `game.roots`, `seen_from`, `hidden`, `stress`, `salt` | the core five, 2022-01-03, 2020-01-02..2021-12-31, 1.5, `ltcm-game-v1` | `roots` keeps the core five only; `hidden` may only narrow inside 2020-21; a count that is not a whole number is malformed (its default) |
| `gym.train_from` | `"2022-01-03"` | the span switch; the House's `swarm.json` pins `"2020-01-02"` today |
| `gym.allow_earlier_image` | `true` | a 2022-start job may run on the 2020 image (its own start cuts the window) |
| `practice.feedback` | `false` | |

**Before the deploy.** M0a (the realized cost readout, $0) and M0b (the amended retro, $1.5-5, with its rule written
down first; an operator script, not in this tree): GO deploys in `"gate"`, WEAK GO in `"shadow"`, STOP leaves the game
off (`game.enabled` false in `swarm.json`) and the fast lane as it is. The owner merges the deploy (protected files) and
approves the crossover clade rule (a crossover child joins its signal parent's lineage only: approved Oct 8 under the
goal). The owner also redeploys the gateway, whose protected list (`gateway/lib/protected.mjs`) gains
`league/swarm/game.py`: the merge route enforces the list only from that redeploy. It can wait a few days: `game.py` is
in no engineer lane, and `league/swarm/harness_lanes.py` seals it and freezes the architect's and the strategist's game
filters in this same deploy. The deploy alone changes nothing an agent reads while the House's `swarm.json` pins
`gym.train_from` "2020-01-02" (no T0: the game waits, a House warning at each start), except `practice.feedback`
false, which is policy and holds from the deploy: keep the gap from the deploy to T0 short.

**T0, in order** (the operator, on the box):
0. Deploy, then wait until the release has cleared the watchdog's automatic-rollback watch and the updater's `previous`
   is set (the order `scripts/settings_migrate.py` gives, ORDER AT THE DEPLOY). Change nothing in `swarm.json` before:
   an automatic rollback under a 2022 span would stop research (**Roll back**, below).
1. Stop the swarm: `touch /workspace/state/swarm.stop`, then wait until the swarm's process is gone and its heartbeat
   (`/workspace/state/swarm.heartbeat`) stops moving (the House restarts a stopped swarm only once the file is gone).
   Nothing below may run with the swarm up: a strategist pass between them would write a section from the unfiltered
   2020-24 lessons.
2. Keep a before-copy of `<state>/swarm.json`. DELETE its `gym.train_from` key (the policy layer has "2022-01-03"; a
   rollback then falls back to the old policy's "2020-01-02" by itself) rather than pinning "2022-01-03". Set
   `game.mode` to the retro's verdict (`"gate"` or `"shadow"`) and check that `swarm.json` pins nothing else under
   `game` or `practice`. Replace the file atomically, as for **The incubator's off switch** (below).
3. Take every hidden year out of the agents' own text: the locked preamble (`architect.agenda_locked`) and the hand
   agenda (`architect.agenda`) say "Train 2020-24" today; make them say 2022-24. No 2020 or 2021 may remain in either.
4. Clear the strategist's WHERE TO LOOK section (it was written from 2020-24 lessons):
   `cd /workspace/current && /workspace/.venv/bin/python -c "from league.swarm.store import SwarmStore;
   s=SwarmStore('/workspace/state'); s.put('architect_agenda_section', None); s.close()"`. The architect then reads the
   hand agenda until the strategist's next section, which is written from the filtered inputs.
5. Re-audit the input capability card over the seen span (its `train_from` 2022-01-03 or later, the same
   `image_checkpoint`) and install it as **Release A: after promotion** step 4 says (`.tmp`, mode 600, `mv`). Until
   then every brief, control and legacy included, and the architect's request read "Card: unknown (span_mismatch)": the
   card audited from 2020-01-02 would name a hidden day.
6. Start the swarm: `rm /workspace/state/swarm.stop` (the House starts it). Its start migrates every living family's
   best to 2022-2024 (`migrate_objective`: runs over 2020-24 no longer count, robustness starts over; a family's best
   stays empty until it re-runs over 2022-24) and writes T0 once (kv `game_t0`; the log says "the learning game
   starts: T0 ..."). Every family alive then is legacy. If the running span still starts in 2020 (step 2 missed), no
   T0 is written, the log says "the learning game waits" and the House is warned: nobody plays until a start under the
   seen span.
7. Verify: kv `game_t0` set; kv `train_objective` is `worst-train-year-v1` (no `@2020-01-02`); the first births are
   core-five; within hours the first `swarm.game` events (`{family, version, look: "queued"}`, private) and `private`
   Gym jobs; no 2020/2021 date in a researcher's conversation (the report's R1a reads it); a brief's input card is the
   re-audited one, not "span_mismatch".
8. The first report: the `game` job writes `<state>/game/report-<day>.json` at 00:00Z; or now, read-only:
   `cd /workspace/current && /workspace/.venv/bin/python scripts/game_report.py --swarm-root /workspace/state`.

**The report and the pre-registered decisions** (`league/ops/game_report.py`, operator-only: no agent reads it; the
current epoch's looks). R1 plumbing (what the game arm's researchers were shown, never their own words or the library's
answers, scanned for a hidden year, and for two of one look's figures in one text; D1 by lineage within 2.5 SE, judged
from 20 founder lineages; hidden runs failing under 5%; the ineligible share, flagged above half); R2 the selection
carry (Spearman of one hidden year with the other, less Spearman of the seen score with it); R3 what each arm would send
to Validation, on the year its selection never read (control: every look at a validated version); R4 the generation
gain and the SELECT burn meter; R5 flow and cost (and the game's retirements by rule); R6 Validation and money per arm. Intervals: family-cluster bootstrap, 2,000 draws, 90%, seeded. The report's `decisions` reads the rules; the
operator acts:
- Day 1: R1 fails -> `game.mode` `"shadow"` and fix the plumbing (the job also raises a House warning naming the failed
  checks). A leak voids every look before the fix.
- Day 3: Delta rho <= 0 with its interval's upper bound under 0.05 -> `"shadow"`, report, stop the reproduction spend.
- Day 7: G >= +0.3 with its interval above 0, or Delta_sel >= +0.3 likewise -> GO-WIDE (`arm_fraction` 1.0 for new
  births, plan Stage 2, freeze a GAME_SCREEN_1 receipt; Blake approves). Both <= +0.1 -> REVERT. Otherwise EXTEND once
  to day 14 under the same rule.

**Inspect**, on a copy or read-only: `sqlite3 'file:/workspace/state/swarm.sqlite?mode=ro'` with `SELECT arm, role,
COUNT(*) FROM game_looks GROUP BY 1, 2`, `SELECT status, COUNT(*) FROM game_results GROUP BY 1`, `SELECT COUNT(*),
SUM(confirmed) FROM game_confirms`, `SELECT op, COUNT(*) FROM game_children GROUP BY 1`. The four tables are append-only
(triggers) and created on first use; no module but `game.py` reads them. A round's game error is one private
`swarm.status` event `{"action": "game_error", "step", "error": <type>}`.

**Roll back.**
- **The game's rules off, looks still recorded:** `game.mode` `"shadow"` in `swarm.json`; read every loop, no restart.
  Its PASSes are read at the first round back in `"gate"`.
- **The game off:** `game.enabled` false in `swarm.json` and restart. Every family is legacy again: today's candidate,
  Validation, allocation and retirement; no looks; children research on as ordinary families. Train stays 2022-2024.
  The hiding does NOT end: while kv `game_t0` exists, the architect, the strategist and every graveyard reader still
  drop the game arm's families and rows and the hidden-year learners' (their reasons and notes tell SELECT and CONFIRM
  outcomes). Switching it on again under the seen span continues the same epoch (nothing hidden was shown meanwhile).
- **Back to five-year Train as well:** `gym.train_from` `"2020-01-02"`; the next start re-migrates every best to
  2020-2024 (the same reset in reverse) and VOIDS the epoch (kv `game_void_at`, a House warning): its families saw the
  hidden years, so they never play again. Switching back later to the seen span with the game on writes a new T0 (a new
  epoch: the log says "a new epoch"; the report reads the new epoch's looks only); repeat T0 steps 1-5 first (the
  agenda, the strategist's section, the card).
- **The code:** restore the before-copy of `swarm.json` (no `gym.train_from` key, or "2020-01-02") BEFORE or WITH
  `scripts/floor_box.py rollback`, and the same at once if the watchdog rolled the release back by itself. The previous
  release has no `gym.allow_earlier_image`: under a 2022 span on the 2020 image its pool refuses every stamped Train job
  (`train_span_mismatch`) and research stops. With T0 step 2 done as written (the key deleted) the old policy's
  "2020-01-02" holds without an edit. Either way every best re-migrates to 2020-2024 (a second evidence reset), and the
  old code has no quarantine: every reader then sees the game arm's rows. Before deploying the game again, void the
  epoch by hand so its next start begins a new one: `cd /workspace/current && /workspace/.venv/bin/python -c "from
  league.swarm.store import SwarmStore; from league.swarm import game; s=SwarmStore('/workspace/state');
  print(game.void(s)); s.close()"` (on the game's release), then the T0 steps.

**Known gaps.** The models know 2020-21 (COVID, the 2021 rally) and the library serves pre-2025 papers: the hidden years
catch the agents' own overfitting, not knowledge their training holds (the leak scan reads no library answer). Legacy
families alive at T0 keep their own 2020-24 runs (`read_run`) and notes; their lessons are quarantined when they retire,
so nothing they learned reaches another family. Pure counts (the refill, the want, the ceiling, the birth quota's
window) include the game arm by design. A game child's own notes may still reach the public tape as `swarm.note` (no
figure: the masked text of what its researcher wrote); the roster never shows it.

**Accepted amendments to the build spec** (Oct 8, after the build's review): T0 waits for a start under the seen span
(spec 3.2 says the first start with the game on); the input card reads "span_mismatch" for every brief until it is
re-audited (spec 3.8 says control sees exactly today's view); one public retirement cause for all three rules (spec 3.7
names three); no game child on the public site; arms kept from their first assignment (`arm_fraction` for new lineages);
a failed look bars its program; the candidate is the newest CONFIRMED version not yet judged; the game's Validation
tries count CONFIRMED versions only; a shadow PASS read at the first gate round; R1(b)'s D1 by lineage, judged from 20
founder lineages; R1(a) counts a figure only as two of one look's figures in one text the researcher was shown; R3's
control set is every control look at a validated version; a void and new epochs (spec 3.10 has none).

## Fast lane v2 (Oct 7, 2026): deployed 19:13Z Oct 7 (House release `20261007T191231Z`, main `cd58fc8f`)

Release L-D (above, Oct 9) changes four of its rules: the Probe count (3 -> 8), the budget's realized basis (GROSS ->
NET), the budget's span (the $400 in total -> $400 in any rolling 20 sessions beside $400 in total, inside the owner's
goal of Oct 9, which allows $800 in total) and, for Probe and Sized, D5's loss leg and the negative record (-> DM1); the
Probe room is capped at the budget. Their values here are its CON-only rollback.

The owner's goal of Oct 7, item 4: "Real money is the forward test. A program trades at Probe size as soon as it passes a
pre-registered screen whose false-positive rate you have measured." This tree carries it, based on PR #505 (the House
has run it since 16:03Z Oct 7, release `20261007T160204Z`). It ships only by the owner's deploy. What it changes:

- **The screen (D1).** The Validation line is t >= 1.65 on daily P&L (was 2), 2 of 4 quarters (was 3), and the deflated
  Sharpe's N is the program (1), not the lineage's history; the rest is unchanged (50 trades on 25 days, mean above 0,
  profit at 1.5x the half-spread, the probabilistic Sharpe at 0.95). One holdout look a distinct program at a FLAT
  one-sided p <= 0.10 (`evidence.LOOK_LEVEL`): no Holm across looks, so the next look is no longer at 0.0125. Every look
  carries its contamination tail from 2026-07-01 (`numbers.tail`), never a check. The experiment contract, the duplicate
  look, the rations (3 a lineage), the paid review and audit and the leakage alarm are unchanged; a program a paid
  review or audit failed stays failed across the deploy's evaluator adoption (`Gate.paid_verdict`, below). The false-positive
  rate is measured by `scripts/screen_benchmark.py` against its frozen receipt
  (`docs/benchmarks/fast_lane_screen_1.json`), ACCEPTED: the floor-eligible per-program rate is 0.18-0.51% in the iid
  null worlds and 1.19% under AR(0.2) daily P&L (95% upper bound 1.36%, under the 2% cap); power 8%, 40% and 78% at a
  yearly Sharpe of 1, 2 and 3 (today's rule: 0.7%, 11%, 44%). The figures are in
  [FAST_LANE_SCREEN_1.md](benchmarks/FAST_LANE_SCREEN_1.md).
- **Direction counts (D2).** `league/swarm/policy.json` sets `tournament.drift_screen` false and `gate.look_holds` null:
  no version is demoted, refused or held for drift or power. The drift fit and the same-risk buy-and-hold are reported
  beside every screen result and band row by two new jobs: `direction` (`league/ops/direction.py`: at the House's start,
  after the grant, and daily 01:00Z, the Gym roots' daily SIP closes through the gateway's bars route into
  `<state>/direction-closes.json`; XSP and SPXW read SPY; a gateway error is a failed receipt, a House warning and a
  retry) and `fast_lane` (`league/ops/fast_lane.py`: after each `direction` run, read-only, the report into
  `<state>/fast-lane-report.json`, with the last 7 days' Validation rows and every look, band row and the Probe budget;
  a Probe or Sized family whose look has no buy-and-hold is a House warning). `scripts/fast_lane_report.py` is the same
  report on copies with any window. Nothing that decides reads them.
- **The Probe (D3).** One structure (`probe.contracts` 1) whose maximum loss with fees fits 10% of the sizing equity E
  (`probe.max_loss_share` 0.10, bound 0.02-0.10), replacing 5% and the $100 floor (`floor_usd` 0); at most 3 Probe
  positions held or working at once (`probe.max_open`). C3 is kept as it was: a Sized family whose Kelly stake is under
  the Probe's cap (or buys no whole structure) is sized under the Probe's limits, now its one structure, 3 open and
  15% the family; Sized limits apply only at a Kelly stake at its 10% cap. A family the live path confirms onto Probe trades from the next live
  minute: no session wait (`step._real_eligible`; a legacy Probe with no promotion record still waits a session). The
  calibration, the incubator and the House test keep `money.probe_room` (3 x 10% x E: $386.52 at E $1,288.40) of the
  book's and the day's caps, in place of two $100 floors.
- **The Probe loss budget (D4).** $400 (`probe.loss_budget_usd`): realized Probe losses, GROSS (each closed position a
  Probe family opened counts its own loss; a gain, Probe or Sized, never offsets one), plus the maximum loss of every
  real position held or working (`real.probe_tally`, from the live state's rows, restart-safe). A Probe family's open is
  marked at its order (`money.Plan.probe`, kept in the order's `answer` and copied to its position's `info`), so "since
  this release" is the mark itself: no order before it carries one, and a Sized position's result never touches the
  realized figure. A LOST open (its outcome unknown) counts whole until the book finds it at the venue, whatever its
  week, and holds its slot until its first leg expires. An open that would breach the budget is refused (`plan_open`),
  exits go on, and one House warning a New York day says the budget is spent (raising it is the owner's). Sized
  positions held or working count against it and against the 3 (a tightening); a Sized open is never refused by
  either. The kill switch, the daily stop (35%), the drawdown stop (60%), the grant and
  reconciliation still refuse first (`real_block`). At E $1,288.40: the Probe cap $128.84, 3 x $128.84 = $386.52, the
  gateway's per-order cap $322.10 and day cap $1,288.40, the book cap $1,159.56, the daily stop $450.94.
- **Demotion by live results (D5).** A Probe goes exit-only, for good for its version, when its realized real P&L falls
  below -3 x the mean maximum loss of its real positions, or its live fills run below its nightly replay of the same days
  by more than 0.20 a dollar of maximum loss over 5 or more matched real trades (`money.demotion`; chosen, not measured).
  The `swarm.band` and `live.band` events carry the reason; the forward rows are kept. Sizing up (Sized) is unchanged.
- **Tuition within the Probe's cap.** Tuition (`:t`, a real 1-lot of a program that passed Validation only) sends one
  structure only when its maximum loss with fees fits the Probe's cap, 10% of E (`plan_open`; it had only the tuition
  day's $200 and week's $300). It stays outside the Probe count and the Probe budget (below, its reach).
- **A paid verdict binds (`Gate.paid_verdict`).** The deploy's adoption clears the gate's `review` and `gated_sha`; a
  version whose program a paid review or audit failed (a kept refusal at the stage "review" or "audit", in any family
  holding the same program, or a kept bar recording the gate's own failed review or audit) is closed before anything is
  paid: no second review, no look. Refusals at free stages (the drift screen, the rations, the holds) are judged again by
  their own rules, and the incubator's own failed reads still bar only the incubator route (the gate asks its own).

**Identities.** Constitution digest `595228a6` -> `5edc8956`; money digest `42c4a3af` -> `da5c7542` (the grant
re-ratifies by itself at the House's start on the owner's deploy: `league/ops/grant.py`, the digest moved with an owner
deploy row); the execution fingerprint `ba60c473` -> `b4c34031` (league/live changed). Check a tree with
`python3 -c "from league.constitution import digest, money_digest; print(digest(), money_digest())"` and
`python3 -c "from league.swarm.evaluator import execution_fingerprint; print(execution_fingerprint())"`.

**What the deploy resets** (the adoption at the House's start, `SELECTION_KEYS`): every alive family's bests, Train
candidates, submissions, robustness (with `robust_failed` and `drift_failed`), validation line and numbers, review,
`gated_sha`, `gate_outcome`, `train_passed` and incubator reviews. No family is banded, so no band is lost. Looks,
trials, refusals, incubator bars, forward rows and extension holds are kept. The adoption clears every family's bests,
so the tournament validates a family again only once its researcher has re-run Train under the new evaluator and
resubmitted (the first fast-lane looks wait for those Train reruns); a version validated before is then re-judged under
the new line from its recorded result, without a new trial; each pass costs a paid review and audit before its look (a burst, inside the roles'
daily caps): every program the old line, Holm or the holds kept from a look gets one now, except a program a paid
review or audit already failed (closed unpaid, `Gate.paid_verdict`). Practice cohorts reset.

**The owner's deploy, in order.** (1) CI green on the exact head; rollback ready (`floor_box.py rollback` to
`20261007T160204Z`); no order in flight. (2) At the House's start the grant re-ratifies on `da5c7542` and the adoption
runs: verify the grant `active`, the adoption count and the policy layer's state "ok". (3) The box's `swarm.json`: keep
`tournament.drift_screen` false (set since 15:53Z Oct 7); `gate.look_holds` must be ABSENT (a value there would override
the policy's null). (4) The `direction` job ran at start, after the grant: `<state>/direction-closes.json` exists, and
the `fast_lane` job after it: `<state>/fast-lane-report.json` exists. (5) Watch the first families pass after a passed
look: Candidate -> Probe -> `:r` -> the first real order (its order's `answer` carries `"probe": true`); then the Probe
budget in `<state>/fast-lane-report.json` (`probe_budget`), each band row's buy-and-hold and any D5 event.

**Stated consequences.**
- The incubator route stays off: with the drift screen off, `incubator.facts` never marks `train_passed`, so the route
  (off since 15:53Z Oct 7 for this reason) has no candidate; restoring it needs a "drift does not refuse" switch, not
  built here. (Oct 8, 2026: restored without one. The incubator's mark now evaluates the drift screen itself at its
  default thresholds while the tournament's screen is off; see **The incubator** below.)
- The practice caps (`:o`) keep the Probe's sizing from before the fast lane, 5% of the practice capital a structure
  with the $100 one-structure floor (`shadow.PRACTICE_SHARE`, `PRACTICE_FLOOR_USD`); only their open count and family
  share read the Probe row (unchanged at 3 and 15%). Practice evidence (sizes, how many opens run at once) does not move
  with the real Probe's row (D6).
- The grant's smallest real stake (`live_trading.smallest_stake`) stays $100 (`OPTIONS_MIN_STAKE`, the floor's old
  value) with the floor at $0: the standing grant refuses under $100 of capital, its policy reads `stake_usd` 100 and
  `max_agents` capital // 100, exactly as before. No grant refusal is loosened.
- THE TUITION ROUTE'S REACH (an existing route the fast lane widens). Tuition sends real 1-lots, never evidence, for a
  Gym family whose version passed Validation and has not passed its look (`step` "tuition", `:t`): real money BEFORE
  the screen's look, outside the Probe count and the $400 budget. The looser Validation line (2.2-8.2% of no-edge
  eligible programs pass it, FAST_LANE_SCREEN_1), the drift screen and the holds off, and the deploy's
  re-judging of recorded validations all enlarge the set it reaches. Its bounds: one structure within the Probe's cap
  (10% of E, $128.84 at E $1,288.40; new here), the tuition day's $200 and week's $300 of maximum loss. Cost: up to
  $300 a week of real maximum loss on programs that passed Validation only; its losses are real money outside the
  Probe budget, inside the daily and drawdown stops. Switching it off is `options_money.tuition` `day_usd` 0 (a money
  row: the owner's deploy and a re-ratified grant).
- A D5-demoted family stays a Candidate, shadow only, until a release: research acts on Gym families only, and the
  swarm sends a Candidate back to the Gym only on a negative forward record (20 trades, a mean below zero) or an
  evaluator adoption. So a family whose live fills lost while its shadow record stays positive is parked: never
  researched or looked at again, its nightly replays still run (Gym compute). Not changed here (a swarm-side route back
  to the Gym on D5 is the next release's).
- Contamination is MEASURED, weakly, in the report (`league/ops/fast_lane.py`, reported only): each look's holdout
  series split at 2026-07-01 into the 123 in-training sessions and the 61 after Opus 5.5's cutoff (days, P&L, daily
  Sharpe, own bootstrap p, whether that part alone meets the level, the head-minus-tail Sharpe gap); pooled over the
  looks, the mean gap with its t and the head-only against the tail-only pass share; and per live band, its live P&L per
  dollar of maximum loss against its holdout's (live is after every author's training). With a handful of looks the
  pooled measure has little power; DeepSeek-V4-Flash, which wrote most versions, has an unknown cutoff.
- The public site's progress checklist for a Gym family states the quarters need as 3 only (the site's schema,
  `capital/schema.js` `PROGRESS_LIMITS`), and one invalid agent fails the whole checkpoint. The publisher therefore
  withholds a Gym family's checklist (null progress) while the line's need is 2 (`progress.SITE_QUARTERS`); widening the
  site's limit to [2, 3] is the owner's (the site is his), and then `SITE_QUARTERS` follows.
- After this release, any later league/live or league/gym change sends a live Candidate, Probe or Sized family back to
  the Gym for good (its look is spent): the next release that touches either tree must carry F2 plan item 11 (keep a
  live Probe across a release) or ship while no family is banded.
- Loosened, with their measured costs (FAST_LANE_SCREEN_1): t 2 -> 1.65, 3/4 -> 2/4 quarters and N = 1 (Validation
  alone passes 2.2-8.2% of no-edge eligible programs, 4.7% gaussian); Holm -> a flat 0.10 look (a no-edge look passes
  7-15% given Validation; the whole screen 0.18-1.19%, against today's rule's 0.01-0.10%); per lineage with 3 looks
  0.3-2.2%, and 3.8-12.5% for the largest (14-program) lineage; the Probe 5% + $100 floor -> 10% of E (below E $1,000
  tighter than the floor); the drift screen's refusal and both holds off (the drift_only world, a program that only holds
  a Sharpe-1 market factor, passes 2.14%); the next-session wait removed (real money within about 5 minutes of a passed
  look, with no shadow session first); tuition's reach (above: up to $300 a week of real maximum loss on programs that
  passed Validation only). Tightened: one structure a Probe position, 3 at once, the $400 budget (gross realized Probe
  losses; every real position held or working, Sized too, counted at risk; a lost open counted until it is found), D5,
  larger rooms kept for Probe opens, a tuition structure within the Probe's cap, a paid review's or audit's failure
  binding across the adoption. Kept as they were: C3 (a Sized family at a Probe-sized stake under the Probe's limits),
  the practice caps' sizing, the grant's $100 smallest stake.
- ADAPTIVE SEARCH (the screen's rate is per program, not per lineage). The 0.18-1.19% is the rate for one no-edge
  program drawn independently. A lineage that keeps validating versions pays nothing more for repeated Validation tries
  (N = 1), so once it can reach Validation again and again the operative rate is the look's given Validation (7-15%,
  by null world), and with its 3 looks a persistent no-edge lineage passes at least one with probability 1-(1-q)^3:
  20% (skew), 22% (mid), 28% (gauss), 30% (t3), 38% (AR(0.2)). The per-lineage 0.3-2.2% (3.8-12.5% for the largest
  lineage) replays the snapshot's past program counts as independent draws under the old regime: a historical floor,
  not a bound. A new family the architect proposes on a failed mechanism starts a fresh lineage, with fresh looks. A
  near-duplicate (a parameter tweak that changes one fill) is a new program with a new look; its bootstrap, reseeded by
  its run sha over almost the same holdout P&L, has a Monte Carlo error of about 0.007 near p 0.10, so a borderline fail
  can flip on bootstrap noise alone. Binding fixes (a within-lineage level, a near-duplicate rule in `duplicate_look`)
  are the owner's call: D1 asks for a flat look a program.
- The budget against the false-positive volume: 287 floor-eligible programs were validated in the snapshot's last 7
  days; if all were no-edge, that is about 1.4 false Probes a week at the gaussian rate and 3.4 at AR(0.2). That volume
  was measured while the drift screen still kept long-delta programs out of Validation, so with it off these are low
  (a floor). A demoted Probe loses about 3 x its maximum loss ($120-375 for $40-125 tickets), so the $400 covers 1-3
  demotions, and since the budget counts losses gross (a winning Probe never refills it), false positives alone can
  spend it within one to two weeks. Raising it is the owner's decision.
- The D5 replay bound (0.20 a dollar on 5 or more matched trades) is chosen, not measured: its false-demotion rate is
  unknown until live and replay pairs exist; every demotion is reported with its numbers.

## Now (Oct 3, 2026): V3-A part 1 is live, on autopilot

Production runs **V3-A part 1** (A1), the first release of LTCM v3 (the unattended desk), since 08:49:56Z Oct 3, 2026.
PR #489 was merged to main (`266e6861`) and shipped by the owner's deploy that morning; its record is in **The A1
deploy, in order**, below. Where this page says "from A1" or "V3-A", it describes this tree's code, which holds on the
box from that deploy.
Why v3 and its plan are in [the run record](runs/2026-10-02-unattended-desk.md); what A1 carries is in
[the CHANGELOG](../CHANGELOG.md) ("V3-A part 1"); how the unattended machinery works is in **Running unattended**,
below. A merged pull request is still not a deployed feature.

### Production now

**Autopilot** (the owner, about 23:30Z Oct 2: "let this project go in auto pilot for some time"). Production stayed on
the Oct 2 release until the A1 deploy; the evening of Oct 2 cut research to a funded floor, ended three practice
cohorts and repaired the Gym pool's bookkeeping (below). Since the deploy the House runs its own jobs, the swarm
researches inside the budget rule's floor, and the live path trades every New York session. The operator's private
handoff log holds the detail; read it before acting.

**The running House.** `20261003T084912Z-be16b05904ff`, built from main `266e6861` (PR #489, V3-A part 1), promoted
08:49:56Z Oct 3 over `20261002T112610Z-e11710692569`, which is `previous`: the rollback target.
- The gateway runs `e95a2d4a` (deployed 08:46Z Oct 3 from the same commit; `CLAUDE_USD` 265; rollback target
  `4471596a`).
- The money digest is `42c4a3af`, and the grant `options-swarm-20260928` is active. The standing grant ratified it
  once, at its first look on A1, on the trigger `deposit`; the looks after it answer `none`.
- The evaluator's execution fingerprint is `ba60c473…`: three planned evidence resets (Release A, Sept 30; Release B,
  Oct 1; A1, Oct 3).
- `auto_update` is on: a merge to main that changes the release trees and no protected path deploys itself at the next
  release train (**Deploy classes**). At the deploy main's release trees were the running release's.
- 13 families were alive at the deploy. The practice league is empty since evidence reset 3 (below).

**Real money** (on since R2, Sept 27). No family has passed the holdout: 3 looks, all failed. The real orders are the
House's own: D3 calibration round trips (23 closed by the Oct 2 close), the House live test (armed, no order yet), and
one tuition lot held by `googl-lags-msft-ai-cloud-qqq-flat@27:t`, exit-only, whose program exits it before 15:10 New
York on Oct 7 (its expiry cutoff). The incubator is on (`live.incubator` true since 04:01Z Oct 1); a cohort's first look
needs 3 completed sessions and 10 program closes. Project Net since the Sept 26 reset at the Oct 2 close: −$648.51
(realized options P&L −$40.63; input costs $607.88).

**The Oct 2 evening changes** (operator, no deploy):
- 17:04Z and 17:23Z, research to a funded floor (the v3 plan's Phase 0): `population.start` 96 → 16, `population.floor`
  12 → 8, `architect.every_seconds` 1800 → 7200, `researcher.sail_usd_per_hour` 1.3 → 0.25, `gym.max_boxes` 6 → 1,
  `strategist.every_seconds` → 86400 (once a day). The swarm had spent about $29 in the 24 hours to the close; at the
  floor its Sail spend (models plus Gym boxes) is about $5 a day at Sail's own billing.
- 19:03Z, three practice cohorts ended: the two GOOGL-lineage cohorts (holdout-failed, incubator-barred) and
  `qqq-exsemis-residual-smh-flat-on-s-2` v1, whose SPXW chain read failed every live minute (more than the observe
  read's three pages). Nine cohorts remained, until the A1 deploy's evidence reset ended them.
- 19:03Z, the six Gym pool rows left in state `failed` were marked `terminated` (Sail had already ended those boxes).
- 21:00Z, a copy of the box's `swarm.json` became `league/swarm/policy.json` on `release/v3a`, without the private
  agenda text and the burst keys. The box's own file is unchanged.

**`swarm.json` values in effect on the box** (where they differ from the code's defaults, or matter now). The full
file stays on the box and wins over `policy.json`, which was cut from it at 21:00Z Oct 2 (at 08:45Z Oct 3 the box's
file was JSON-equal to that copy). The budget rule then tightens the result (under the table). `policy.json`
holds the same research values (`population.start` 16 and `floor` 8, the architect every 7,200 s on Sail's
`pro_asap` at `high` effort with `claimable_rows` 4 and `structures` `["debit_vertical", "long_single"]`,
`researcher.sail_usd_per_hour` 0.25, `gym.max_boxes` 1, the strategist once a day, Claude only for the gate's review
and audit and the strategist, forks off). The owner's switches (`live.calibration`, `live.house_test`,
`live.incubator` and `live.observe` true, `observe_max` 48) and the private agenda text (`architect.agenda`,
`architect.agenda_locked`: v16c) are only on the box.

| Key | On the box | Since | Default |
|---|---|---|---|
| `population.start`, `floor` | 16, 8 | 17:04Z Oct 2 (96, 12 before) | 48, 16 |
| `architect.every_seconds` | 7200 | 17:04Z Oct 2 (1800 before) | 14400 |
| `architect.max_refill`, `refill_seconds` | 6, 1200 | about 14:00Z Oct 1; 02:47Z Oct 1 | 12, 3600 |
| `architect.sail_profile` | `pro_asap` (DeepSeek-V4-Pro, asap queue) | 12:49Z Oct 2 | `k3_balanced` |
| `architect.sail_effort` | `high` | 12:54Z Oct 2 | `medium` |
| `architect.claimable_rows` | 4 | 05:26Z Oct 2 | 0 |
| `architect.cell_yield` | null (the owner: claims first) | - | null |
| `architect.structures` | `["debit_vertical", "long_single"]` | 15:22:15Z Oct 1 | null |
| `architect.max_rebirths_per_cell` | 6 | 15:22Z Oct 1 | 3 |
| `architect.agenda_locked`, `architect.agenda` | agenda v16c in both (private; sha256 `c7a46dca0707…`) | 15:22:15Z Oct 1 | empty |
| `strategist.every_seconds` | 86400 | 17:04Z Oct 2 | 10800 |
| `claude.role_usd_day.architect` | 0 | 11:54Z Oct 2 | none |
| `claude.usd_cap` | 263 | 20:33Z Oct 1 | 100 |
| `tournament.fork_top` | 0 | 05:03Z Oct 2 | 3 |
| `gate.look_holds` | the default (on) | the 11:26Z Oct 2 release | `{"drift_share": 0.25, "min_power": 0.30}` |
| `researcher.sail_usd_per_hour` | 0.25 | 17:23Z Oct 2 (1.3 before) | null |
| `researcher.top_families`, `researcher.claude_top` | 0, 0 | Sept 30 | 10, 12 |
| `researcher.stall_revisions`, `diagnostician.enabled` | 10000, false | 16:41Z Sept 30 | 5, true |
| `gym.start_boxes`, `max_boxes` | 2, 1 | Release A, Sept 30; 17:23Z Oct 2 | 4, 8 |
| `live.incubator`, `live.house_test` | true, true | 04:01Z Oct 1; 00:17:28Z Sept 29 | false, false |
| `research.enabled` | false | - | false |
| `guard.burst_until`, `burst_cap_usd` | 2026-10-05T00:00Z, $900 (still in the box's file; A1 retired them and no code reads them) | Sept 27 | Sept 28's open, $350 |

**The budget rule tightens these, last** (since A1). With no `budget.json` before the first `budget` run the floor is
in force. Read on the box at 09:00Z Oct 3: the researchers' Sail pace is $0.05 an hour (the table's 0.25 is the box's
value, capped), the population's ceiling and start are 12 (16 in the table), the architect passes every 14,400 s
(7200 in the table), and OpenAI's cap is 0.

**What else holds now.**
- The research burst is gone with A1: its three settings (`guard.burst_until`, `burst_cap_usd`,
  `after_burst_usd_day`) are read by no code, and the budget rule sets the day's cap.
- The Sail guard brakes research when Sail's balance falls under its line (two days of the House's burn plus $30),
  before the House is at risk; the House and the live path keep running. The gateway's watchdog mails the owner
  a daily digest at 21:00 UTC, a warning when Sail falls under $25 and a critical one under $12.
- Only the strategist (once a day) and the gate's review and audit spend Claude.
- Sail's model API answers some calls with HTTP 502 (about one researcher cycle in seven on Oct 2); a failed cycle is
  retried, nothing else.
- The tuition lot's program exits it before 15:10 New York on Oct 7.
- Calibration round trips (up to six a session, at most $50 of possible loss a day) and the House live test run every
  session. The practice league is empty since the deploy, so the incubator has no first look to make: one comes when a
  new cohort has 3 sessions and 10 program closes.

**How to look without changing anything.** The public site (blakewoods.us/capital), the gateway's 21:00 UTC digest
mail, the receipts file and the House's daily pages touch nothing on the box (**Observing without exec**). The
pre-open checks (**Pre-open**, below) and `floor_box.py status` read the box and change nothing, but each is an exec.

### V3-A part 1: what the release is

**In it** (this tree; [the CHANGELOG](../CHANGELOG.md) lists it by work package):
- the House's own jobs (`league/ops/`) with receipts the owner reads without touching the box;
- the budget rule, which replaces the research burst, and its `funding` notice;
- settings as code (`league/swarm/policy.json`);
- the standing grant;
- self-deploy: `auto_update` is true in this tree's `league/config.json`, so since the deploy main's head reaches the
  House through the updater's walls, and everything the walls protect stays the owner's deploy (**Deploy classes**);
- the live-path fixes (`league/live/step.py`, `shadow.py`): exit-only opens dropped, practice reads clamped to the Gym's
  store, practice accounts capped as a Probe;
- the gateway's routes for the desk's daily page and for an engineer's pull requests, the admin log, and the lower Sail
  mail lines.

**The money digest is `42c4a3af`, unchanged by A1** (the constitution is untouched: `digest()` equals `PINNED_DIGEST`
on this tree), so the grant `options-swarm-20260928` stayed active across the deploy and no digest ratification was
due (the standing grant's one ratification at the deploy answered a deposit: the record, below).
The sealed-holdout gate, the look rules and execution tuition are exactly as before: they retire only with the forward
ladder.

**Evidence reset 3, and practice does not refill by itself.** A1 changes `league/live/`, so the evaluator's execution
fingerprint moved (`47587e22…` → `ba60c473…`; the Gym's image and bundle did not change). At the first start on A1
(08:50Z Oct 3):
- the swarm archived every family's derived selection evidence and adopted the new evaluator (13 `evaluator_adopted`
  events at 08:50:34Z, one per alive family); trials, lineages and consumed looks are kept (**Evaluator adoption**,
  under **Rules that hold every day**);
- the live path completed every active practice cohort (nine) with the reason "evaluator changed; a new version needs
  fresh practice", and every incubation that rested on one ends with it;
- under A1's cohort rule a (family, version) that ever had a cohort never enters practice again
  (`league/live/observe.py` `cohort_candidates`). So practice refills only from versions that have not had a cohort:
  new versions that qualify on the new evaluator. The versions that were practising do not come back. Until new ones
  qualify the practice league is empty and the incubator has nothing to look at. The ladder release (A2) is where that
  rule changes.

Never compare evidence across the reset. A rollback across A1 moves the fingerprint back and is one more reset.

**Not in A1** (built on branches, not deployed): the forward ladder (`v3/wp6`; its confirmation study is not run yet)
and credit types at $2,000 of equity with a paper proof per type (`v3/wp7`), which together are part 2 (A2); research
v3 (`v3/b1`), births v3 and the strategist's whole agenda (`v3/b23`), the weekly post-mortem (`v3/b4`) and the engineer
and reviewer (`v3/b5`). Every one of them changes a protected file as it stands (the constitution and `league/live/`
for A2; `league/swarm/settings.py`, the store, the evidence and tournament modules or `league/ops/` for the rest), so
each ships by the owner's deploy, not through the updater. A2 is one more evidence reset and a money-digest move. The
ladder's design was frozen on Oct 3, before any confirmation run.

### The A1 deploy, in order

The owner's deploy, never between 13:25Z and 20:05Z on a trading day (**Rules that hold every day**). It ran on
Saturday Oct 3, 2026, from 08:23Z to 09:02Z, by the steps below; each step's time and result are in the record under
them.

**Before step 1 the rollback was rehearsed on production:** a deploy of main as it stood (promoted, watched ten
minutes), then `floor_box.py rollback` with no force flag, then the restored release verified. It found a blocker that
stopped every release, which was fixed before the release went out (the record, below).

1. **The tree.** `main` merged into `release/v3a`; CI green on the exact head (the `gateway`, `tests (3.11)` and
   `tests (3.14)` jobs); the pull request merged with a merge commit whose release trees (`league/`, `ltcm/`,
   `playbooks/`, `scripts/`, `deploy/`) and `gateway/` equal the tested head's. On that commit: `digest()` equals
   `PINNED_DIGEST`, `money_digest()` is production's `42c4a3af` (A1 has nothing to re-pin; a moved money digest stops
   the deploy), `python3 -m league.ci --no-tests` is clean, and the tree `floor_box.py` packs has the same
   `watchdog.tree_digest` as the updater's unpacked archive of the commit, so the updater's first look reads "the box
   already runs main". Deploy from a clean detached checkout of that commit (**Every owner release**, under **Deploy**).
2. **The settings.** Take a fresh copy of the box's `swarm.json` and run `scripts/settings_migrate.py --swarm <copy>
   --policy-out <scratch> --swarm-out <scratch>` as a dry run. Never `--apply` into the repository: the box's file
   holds the private agenda, and `--apply` would write it into the public `policy.json`. The committed `policy.json`
   must give the same settings as the box's file apart from the agenda keys and the retired burst keys: the dry run's
   `changed` list (the keys of the box's file whose values the committed `policy.json` does not hold) names those and
   nothing else. Anything else is re-cut by hand and goes through CI again. The tool's `settings_in_effect: unchanged
   (checked)` is not that check: it compares the box's file with the tool's own proposed `policy.json`, which would
   carry the agenda.
3. **The gateway first.** In `gateway/` of a clean checkout of the same commit: `npm run check && npm test`, read the
   result. No lockfile is tracked, so never `npm ci` (it exits 1 without one) and no install is needed (the checks and
   the tests use Node alone). Then `npx wrangler@4.129.1 deploy`: the pinned version, because a bare `npx wrangler`
   may resolve to a newer one. Record the version id. Read `/v1/health` (`gateway_admin.py status`): the kill switch
   unchanged, the caps as before, `autonomy` and `admin_log` present. `/v1/health` carries no structures list: read
   `OPTION_STRUCTURES_REAL` (the four debit types), `LOW_BALANCE_USD` (25) and `CRITICAL_BALANCE_USD` (12) from the
   deployed version (`npx wrangler@4.129.1 versions view <id> --json`). The running House never calls the new routes
   and the new House tolerates their absence, so the gateway goes first and may be rolled back alone
   (`npx wrangler@4.129.1 rollback <old version id>`).
4. **The House.** Stop the nightly daemon while it is idle (`touch /workspace/state/data/nightly.stop`, wait for
   `nightly.lock` to be free), `python3 scripts/floor_box.py deploy` from the deploy checkout (canary, promotion, the
   ten-minute watch; exit 0 only for `promoted`), then remove the stop and confirm it is gone. Not within 15 minutes of
   a `drills` occurrence (the first Saturday of a month, 15:00Z and 17:00Z): a drill that kills the swarm must not fall
   inside the release's watch. Re-point the harness observer (**Every owner release**, step 7).
5. **The box keeps its FULL `swarm.json`.** It is neutral under A1 (its values equal `policy.json`'s, and `swarm.json`
   wins), and it is what the release in `previous` needs: a pre-V3-A release reads the research settings from
   `swarm.json` alone. The reduced file (the owner's switches and the private agenda only) is installed only once
   `previous` is itself a V3-A release, that is after the next House release (`scripts/settings_migrate.py`, ORDER AT
   THE DEPLOY). It is not the tool's `--swarm-out` file as written: that one keeps `enabled` and `live` and drops the
   agenda. How it is made and checked is in **The settings layers** ("The reduced `swarm.json`").
6. **The checks.** `health.json`: the new release id, `real_money` true, `failures` [], an `ops` block, nothing in
   `stopped_because`. The grant: a `grant` receipt at the start reading `none` on `42c4a3af`, or `ratified` with the
   trigger `deposit` (once: **The standing grant**); no ratification without a deposit. The evaluator:
   `research_evaluator.execution` is the head's fingerprint, one adoption event per alive family, the old cohorts
   completed "evaluator changed". The jobs: `ops.sqlite` holds the `grant` row, nothing `failed` or `missed`, and
   `scripts/desk_receipts.py` reads `latest.json` without an exec. The budget: the floor in force until the first
   `budget` run, then `budget.json`. The updater: built, its first look "the box already runs main", no head pending.
   `nightly.stop` absent and the nightly daemon's heartbeat back. The tuition lot still exit-only.
7. **Criterion 1 on A1:** `floor_box.py stop` then `start` (every instance restored, a new `grant` receipt), then a
   killed swarm process recovered. Outside the session, `health.json` `options_live.blocked` then reads "the account
   could not be read this minute" until the live path's next quiet pass, which reads the account every 15 minutes
   (**Recover**).

**The way back from A1.** `python3 scripts/floor_box.py rollback --reason "why"` moves `current` to `previous`, removes
the `previous` link and restarts the House. It restores code only: the state on the box (the stores, `swarm.json`,
`ops.sqlite`, `budget.json`) stays as it is. Read `floor_box.py status` first and run it only when `current` is the A1
release, `previous` is the release you mean to return to, and no deploy is in flight; a second rollback has nothing to
go back to. After a refused deploy (exit 2) nothing needs undoing; after exit 3 the watch has already gone back.
**Roll back**, below, has what else a rollback across A1 needs. The gateway's way back is `npx wrangler@4.129.1
rollback <old version id>`.

**The deploy's record** (Oct 3, 2026; [the CHANGELOG](../CHANGELOG.md) entry has every check). Writing it,
here and in the CHANGELOG, is a docs-only merge by hand: it changes no release, holds nothing and needs no deploy
(**The protected paths**, below).

| Step | UTC | Result |
|---|---|---|
| The rollback, rehearsed first | 08:23-08:41Z | a deploy of main `d0a2d01b` alone was refused by its canary (exit 2, production untouched: the blocker, below). On main plus the one fix, release `20261003T082921Z-f313be66cb82` was promoted at 08:30:04Z, watched ten minutes (clean; PROMOTED, exit 0) and rolled back with no force flag in 4 s. The restored release was verified: health fresh, the evaluator and the nine cohorts unchanged, no new ratification, the operator's pre-open check 9 of 9 |
| The tree: main's commit, CI run | 08:44:41Z; 08:45:39Z | CI green on the exact head `0c8e8107` (run 37109800144: `gateway`, `tests (3.11)`, `tests (3.14)`); PR #489 merged as `266e6861`, its tree equal to the tested head's, CI green on it too (run 37110781254). One tree digest on both paths (`d817cbf1…`, 941 files); `digest()` equals `PINNED_DIGEST`; money digest `42c4a3af`; fingerprint `ba60c473…`; `auto_update` true. The settings dry run changed exactly the four expected keys |
| The gateway: version id, `/v1/health` | 08:46Z; 08:47-08:48Z | 404 of 404 tests on Node 26 and on Node 24; version `e95a2d4a` at 100%; `/v1/health` ok with `autonomy` and `admin_log`, the kill switch false, the caps unchanged; the deployed version reads the four debit types, `LOW_BALANCE_USD` 25 and `CRITICAL_BALANCE_USD` 12. Its own rollback rehearsed: to `4471596a` and back. The old House ran healthy on it |
| The House: release id, the watch's verdict | 08:49-09:00Z | the nightly daemon stopped idle; `20261003T084912Z-be16b05904ff`: the canary passed, promoted at 08:49:56Z, the ten-minute watch clean, PROMOTED, exit 0; `previous` is `20261002T112610Z-e11710692569`; `nightly.stop` removed and the daemon back; the harness observer re-pointed; the full `swarm.json` kept on the box |
| The checks (step 6) | 09:00-09:01Z | Health: the new release, `real_money` true, `failures` [], nothing in `stopped_because`, an `ops` block (one job due, one ok, none failed or missed). The grant: the start receipt ok, ratified once on the trigger `deposit`, then `none`. The evaluator: `ba60c473…`, 13 adoption events (one per alive family), all nine cohorts completed "evaluator changed". The jobs: 11 registered; `desk_receipts.py` reads `latest.json` with no exec. The budget: the floor in force, its knobs applied, the Sail guard not braked. The updater: built; its first look at the first tick, with no alert and no deploy row. One expected non-pass: the operator's pre-open check is 9 of 10, its check 6 (bands) reading "observe rows 0" after the evidence reset |
| Criterion 1 | 09:01-09:02Z | `stop` (the loop quiesced in 5 s) and `start`: health fresh on the new release, a new `grant` receipt, the swarm's heartbeat fresh 16 s after the start. The swarm killed: recovered in 16 s, 13 families alive before and after. The tuition instance still exit-only |

**The canary blocker the rehearsal found.** From 00:00Z Oct 3 every canary was refused, so no release of any kind
could land: not A1, not a re-deploy of a rollback target, not an updater release, not the rollback drill.
- The cause: the old League's fourteen-day expedition (the constitution's `budgets.expedition`, from Sept 19) ended at
  00:00Z Oct 3. A canary is a fresh House with nothing told yet, so it told the run's scheduled end on its first tick.
  It told it as an error ("The expedition's Sail spending has stopped: day 14 is over"), and the watchdog refuses any
  unmarked error in a canary.
- How it was found: the rehearsal's deploy of main alone was refused at 08:23Z, exit 2, with production untouched.
- The fix: commit `0c8e8107` (`league/house.py` `_expedition_notices`). The calendar ending the run is a warning; a
  budget spent before its last day is still an error. Its three tests fail on the old code with the refusal's own
  words.
- The rehearsal then ran on main plus that one fix (a local cherry-pick: the Oct 2 release's money digest and
  fingerprint, `auto_update` false), and the fix reached main in PR #489.
- The rule it leaves is in **Deploy** ("A canary is a fresh House").

### What A1 does by itself now that it is live

No command is needed for any of this; read the receipts (**Observing without exec**).
- **Research dropped to the budget rule at once.** There is no `budget.json` before the first `budget` run, so the floor
  is in force from the first settings load: Sail research at most $3 a day and Claude at most $2, OpenAI closed. On the
  committed `policy.json` that makes the researchers' Sail pace $0.05 an hour, one Gym box, each Claude role's line at
  most $2 a day, the population's ceiling and start 12, and the architect every 4 hours. From the first run (00:30Z
  Oct 4) each meter gets only what its balance sustains for 90 days above its reserve and fixed cost, which can be less
  than its floor share.
- **The Sail guard brakes the swarm when the day's research dollars are spent**, until 00:00 UTC. At the floor that can
  be most of the day. It is the rule working, not a fault: the `preopen` check 5 passes on it.
- **Each budget run with no close economics yet raises one House warning** (the live book's own read of `p30` is used,
  and the job says so every time). The House's first own close economics runs ten minutes after the first session's
  close on A1, Monday Oct 5's.
- **The first budget run mails a `funding` notice for each meter whose runway is under 60 days at the rate it wants.**
  It is the desk's own notice, at most one a meter a week, and it names both rates: the rate the rule holds the meter
  to now (its fixed cost plus the day's research budget) and the rate the rule wants. While research is above zero and
  the balance covers the card line at the current rate, nothing stops if no card is added: the rule goes on throttling
  research to what the balance sustains. The first run is at 00:30Z Oct 4, and it is expected to mail two notices, one
  a meter.
- **Practice is empty** until new versions qualify on the new evaluator (above) or the ladder release lands.
- **The jobs:** `grant` at every start and hourly at :05; `budget` at 00:30Z; `hygiene` at 02:00Z; `clock` at 11:00Z;
  `preopen` an hour before the open and `economics` ten minutes after the close on trading days; `scoreboard` at
  23:30Z, a docs commit to main ([runs/desk/](runs/desk/README.md)). The first page is due at 23:30Z Oct 3. Until the
  House's own close economics has run, a page's money section says there is none yet.
- **The drills** are due on the first Saturday of each month at 15:00Z and 17:00Z: two test `funding` mails (one a
  meter), a failed Sail read and a gateway outage (both must give no research), a killed swarm that must come back, and
  the rollback drill, which restarts the House twice. The runner never reports an occurrence older than its first tick
  on the state. The runner was installed at 08:50:29Z Oct 3, before both of that day's occurrences, so the first drills
  are due that day and the next on Nov 7. To skip a month, set `{"jobs": {"drills": {"enabled": false}}}` in
  `<state>/ops.json` before 15:00Z.
- **The updater is on.** A merge to main that passes CI on its exact commit, changes the release trees (`league/`,
  `ltcm/`, `playbooks/`, `scripts/`, `deploy/`) and changes no protected path in them deploys itself at the next
  release train. A merge that changes a protected path in those trees is refused, and so is every later head, until the
  owner deploys main's head. A merge that changes nothing in those trees (docs, the CHANGELOG, `gateway/`) is no release
  and holds nothing: a gateway change reaches production only by `npx wrangler@4.129.1 deploy` (**The protected
  paths**, below).
- **The no-forward-edge count** of the budget rule starts at Monday Oct 5's session; its 60th session closes on
  Dec 29, 2026.

### Still true

- **The freeze.** `league/live` and `league/gym` change only in a planned, deliberate release: a change to either, or
  to `LEAGUE_FILES`, the fill model or the Gym image, moves the evaluator. In this tree every file of the fingerprint is
  FORBIDDEN to the updater and to the gateway's merge route (`league/live/`, `league/gym/` and
  `league/{__init__,safety,structure_core,stats}.py`), and so is `league/swarm/policy.json`, which names the Gym image:
  since the A1 deploy no merge to main can cause an evidence reset by itself (the releases before it held a shorter
  list, with the updater off). Keep such commits off main except as a planned release.
- **The incubator's off switch**, on the box: keep a before-copy, set `live.incubator` to JSON `false` and replace the
  file atomically, then read the switch back.

  ```sh
  cd /workspace/state && cp -p swarm.json "swarm.json.before-off-$(date -u +%Y%m%dT%H%M%SZ)"
  /workspace/.venv/bin/python - <<'EOF'
  import json, os
  path, tmp = "/workspace/state/swarm.json", "/workspace/state/swarm.json.tmp"
  with open(path) as f:
      data = json.load(f)
  data.setdefault("live", {})["incubator"] = False
  with open(tmp, "w") as f:
      json.dump(data, f, indent=2)
  os.chmod(tmp, 0o600)
  os.replace(tmp, path)
  EOF
  cd /workspace/current && /workspace/.venv/bin/python -B -m league.live --root /workspace/state --incubator
  ```

  The last command must show `switch` `on` false. Within a minute the incubator's instances go to exits only and their
  working opens are cancelled. First looks are still recorded. Switch it off before any rollback across Release B
  (**Roll back**, below).
- **The library stays off** (`research.enabled` false) until the order route's p99 is measured with the library under
  load.
- **The runtime skew.** The House runs Python 3.11 with numpy 2.4, the Gym Python 3.12 with numpy 2.5. A program can
  train in the Gym and still fail to load on the live path; the preflight flags it (`preflight_house_unloadable`).
- **Unchanged:** D2, the sealed holdout, no forced trades.

Re-read main, the open PRs and the running release before acting: a document's timestamp is not a fresh health check.
During the unattended clock that read is the receipts, the daily pages and the gateway's `/v1/health` (**Observing
without exec**, below), never a command on the box.

The existing ThetaData collector owns the only account session; preserve it while it downloads. Do not log in again, or
launch a duplicate collector to widen the universe. New discovery belongs in a data backlog until coverage and capacity
are verified.

## Running unattended (V3-A)

How the desk runs with no command from the owner's machine, since the A1 deploy (Oct 3, 2026): who may deploy what,
the settings layers, the House's jobs, how to observe them without touching the box, the rollback drill, the budget
rule, the standing grant and the gateway's new routes. The code is the authority; these subsections follow it.

### Deploy classes

| Class | What | How | When |
|---|---|---|---|
| Owner deploy | any change to a protected path in the release trees (below), a `config.json` change beyond its operating dials, `real_money`, and every gateway change | `scripts/floor_box.py deploy` from `~/Work/ltcm-deploy`; the gateway by `npx wrangler@4.129.1 deploy` | the money path's window (20:05-13:25Z on a trading day; from 21:05Z in winter), except a rollback |
| The updater | a change merged to `main` that touches the release trees (`league/`, `ltcm/`, `playbooks/`, `scripts/`, `deploy/`) and no protected path: the swarm's loop, researcher, architect, strategist and pool, the publisher, the House's service code. `league/config.json` only when the running release's checks find nothing but its bounded dials moved. A merge that changes nothing in those trees (docs, the CHANGELOG, `gateway/`) changes no release and holds nothing | the House by itself: it reads main's head every half hour, then the attested commit, the walls, the release train, the canary, promotion, the ten-minute watch, rollback | never inside its calendar hold (12:55Z to 20:05Z on a trading day, to 21:05Z in winter), never within 30 minutes of a House start, at most one release every `release_train_hours` (4) |
| Engineer merges (the House's `engineer` job, from the self-running release; **The improvers**, below) | `engineer/<lane>/<slug>-<hash>` pull requests | the gateway's `POST /v1/github/merge`: green `checks.yml` on the exact head (its three jobs), a recorded approve and no reject for that commit, no protected path, only the branch's own lane and only what the harness lanes declare, new `league/tests/test_harness_candidate_*.py` files only ever added; at most 2 a New York day; never while the kill switch is on | a merge is then an updater release |

**The protected paths.** `league/ci.py` `FORBIDDEN` lists 86 files and trees. No role's branch may change one, and the
gateway's merge route refuses the same list plus `league/config.json` (`gateway/lib/protected.mjs`; a test on each
side fails while the two lists differ by anything else). The updater refuses a main head that changes any of them
inside the release trees; five entries lie outside those trees and never reach the box (below). The list covers:
- the money rules, the grant and the order path: `league/constitution.py`, `league/live/`, `league/live_trading.py`,
  the ledger, the book, `league/structure_core.py`;
- the evaluator's identity and the evidence: `league/gym/`, `league/evaluator.py`, `league/stats.py`,
  `league/safety.py`, the swarm's `gate.py`, `bands.py`, `evaluator.py`, `evidence.py`, `tournament.py` and `store.py`,
  `ltcm/data/` and `scripts/data/`;
- the budget and everything that feeds or enforces it: all of `league/ops/` (the job framework, the budget rule, the
  close economics, the standing grant's job, the drills), `league/swarm/settings.py`, `guard.py`, `models.py` and
  `funding.py`, and `league/swarm/policy.json`;
- the harness loop's own objective: `league/swarm/harness_lanes.py`, its judges, canary and benchmarks, and the goal
  and benchmark documents (`docs/goals/`, `docs/benchmarks/`);
- the walls themselves and how the House is deployed: `league/ci.py`, `league/updater.py`, `league/watchdog.py`,
  `league/house.py`, `scripts/floor_box.py`, `deploy/`, `gateway/`, `.github/`, and the release record `CHANGELOG.md`.

Read the list itself before relying on a path being free: it is the authority.

**What the updater does with the list.** The updater unpacks and compares only the release trees: `league/`, `ltcm/`,
`playbooks/`, `scripts/` and `deploy/` (`league/updater.py` `TREES`, the trees `floor_box.py deploy` sends too). Its
wall is the part of the list inside them. Five entries lie outside and never reach the box as files: `gateway/`,
`.github/`, `CHANGELOG.md`, `docs/goals/` and `docs/benchmarks/`. For those the list holds the roles and the gateway's
merge route only: the updater neither refuses a change to them nor ships it.
- **A head whose release trees equal the running release's is no release.** The digests are equal, so the updater's
  look reads "the box already runs main": nothing deploys, nothing is refused and nothing is held. That is what a
  docs-only merge (the CHANGELOG entry of a deploy among them) or a gateway-only merge gives when the box runs the head
  before it.
- **A gateway change reaches production only by `npx wrangler@4.129.1 deploy`**, and its merge holds nothing. A merge
  that changes `gateway/` together with unprotected House code ships the House part by itself at the next train, while
  the gateway part waits for the owner. So a House change that needs a gateway change is merged only after that gateway
  change is merged and deployed.
- **`.github/workflows/` is held by the updater's pin**, not by the list: a head that would be a release is refused
  while its workflows differ from the running release's `TRUSTED_WORKFLOWS_SHA256`, and the re-pin is a change to
  `league/updater.py`, which is protected (**Rules that hold every day**). Nothing on the box holds the other files
  under `.github/`.

**A merged change to a protected file in the release trees waits for the owner, and holds the train.** The updater
compares main's head with the running tree file by file. A head that changes a protected file is refused, with a House
warning that names the file, and so is every later head, because each still differs from the running release in that
file. Nothing self-deploys again until the owner deploys main's head. Research-class work that touches a protected file
(a new job under `league/ops/`, a setting in `league/swarm/settings.py` or `policy.json`, the store, the tournament) is
therefore an owner deploy: merge it when that deploy is at hand.

**An owner deploy ships main's head, nothing else.** An owner release of any other tree is replaced by main's head at
the next train, or, where it differs from main in a protected file, makes every later head read as a protected change.
Merge first, then deploy the merged commit.

**The engineer's lanes.** `league/ci.py` `ENGINEER_LANES` names four: `research`
(`league/swarm/{researcher,preflight,claude_research}.py`), `memory`
(`league/swarm/{architect,strategist,diagnostician,seeds,mechanisms}.py`), `data` (`league/sailbox.py`,
`league/data_job.py`) and `scheduler` (`league/swarm/loop.py`); each may also add new candidate tests. The gateway is
the stricter wall (`gateway/lib/github.mjs` `ENGINEER_SURFACE`): it opens and merges only paths the harness lanes
themselves declare, so it refuses `league/swarm/loop.py` and `league/swarm/mechanisms.py`, to their own lanes too. The
scheduler lane therefore admits new candidate tests only. Opening either path is an owner deploy (the path named in
`league/swarm/harness_lanes.py` and in `ENGINEER_SURFACE`, both protected). The gateway is the only merge route;
`league/ci.py`'s path guard alone would pass such a change only on a branch pushed by hand. The House's engineer also
holds every lane file the live path loads (on this tree `league/swarm/researcher.py` and `claude_research.py`): its
research lane is `preflight.py` and new tests (**The improvers**, below).

### The settings layers

`league/swarm/settings.load` merges, each layer over the one before:

```
DEFAULTS (settings.py) < league/config.json "swarm"/"gym" < league/swarm/policy.json < <state>/swarm.json < <state>/budget.json (tighten-only)
```

- **`league/swarm/policy.json`** is the research settings as reviewed code. It is a protected path: the gateway merges
  no change to it and the updater ships none. A merged change to it reaches the box by the owner's deploy alone, and
  until that deploy the updater refuses every later head too. A setting that must move without a deploy is set in the
  box's `swarm.json`, which wins over it. It never carries the owner's switches (`enabled`, `live`: ignored there and
  named in `_policy`). A missing file is no layer; one that is not an object, or whose shape breaks the defaults', is
  ignored whole and the loop alerts once.
- **`<state>/swarm.json`** keeps the owner's switches and the private agenda text (`architect.agenda`,
  `architect.agenda_locked`), which the public repository must not hold. Any other key left there still wins over
  `policy.json`: at the A1 deploy the full file stayed (its values equal `policy.json`'s), and the reduced one goes in
  only once `previous` is itself a V3-A release (**The A1 deploy**, step 5; "The reduced `swarm.json`", below). A hand
  edit of `swarm.json` is a command on the box, and it outlives every release.
- **`<state>/budget.json`** is applied last and only to tighten (the budget rule, below). The retired burst trio
  (`guard.burst_until`, `burst_cap_usd`, `after_burst_usd_day`) changes nothing if a file still names it, and an
  operator's own `budget` key in `swarm.json` is replaced, never read.
- **`<state>/ops.json`** is not a settings layer: it is the owner's private file for the House's jobs (below).

What the swarm actually runs on is the merged result, budget included: the receipts carry the budget's knobs
(`budget.knobs`), and the heartbeat shows the Sail guard's budget line (`budget_research_usd_day`, `budget_source`) and
the researcher pace (`status.researcher_pace`).

**The reduced `swarm.json`.** `scripts/settings_migrate.py` writes one to `--swarm-out`, and that file is not yet the
one for the box. It keeps only `enabled`, `live` and the top-level notes, and moves every other key into the tool's
proposed `policy.json`, the two agenda keys among them. The proposed file is never committed (the repository is
public), so over the committed `policy.json` the tool's file leaves the box with no agenda: the architect runs without
one and the strategist stops (it runs only while `architect.agenda_locked` is set). The file for the box is the tool's
output plus `architect.agenda` and `architect.agenda_locked`, copied by hand from the full file. Before it is
installed, the settings are loaded over the committed `policy.json` with the full file and with the reduced one, and
the two must be equal, both agenda keys included. On the owner's machine, against copies, from the root of a checkout
of the commit the box runs:

```sh
python3 - swarm.full.json swarm.reduced.json <<'EOF'
import json, sys
from league.swarm import settings

def layers(path):   # DEFAULTS < config.json < the committed policy.json < this swarm.json, before the budget
    out = settings._merge(settings.load(), json.load(open(path)))
    for key in ("burst_until", "burst_cap_usd", "after_burst_usd_day"):   # retired: no code reads them
        out["guard"].pop(key, None)
    return out

full, reduced = layers(sys.argv[1]), layers(sys.argv[2])
assert full == reduced, "the reduced swarm.json changes the settings"
print("same settings; agenda:", bool(full["architect"]["agenda"]), "locked:", bool(full["architect"]["agenda_locked"]))
EOF
```

The last line says whether each agenda key is set (both are, in the box's file today). The comparison is made before
the budget, which caps the spend knobs and would hide a difference under its cap. The tool's own `settings_in_effect:
unchanged (checked)` is not this check: it sets the full file over the current `policy.json` against its reduced file
over its own proposed `policy.json`, which holds the agenda. Keep the full file: a rollback to a pre-V3-A release needs
it (**Roll back**).

**How the tests see the layers.** The league's tests read an empty policy layer
(`league/tests/fixtures/policy_empty.json`, switched on for the whole process by importing `league.tests`), so they
judge the code against the defaults and what each test sets, and a change of the House's settings never changes what
they test. The committed `policy.json` is judged in one place, `league/tests/test_swarm_settings_policy.py`: by value
(the kinds of its values, the population's order, no line of the guard loosened, the budget binding it) and by the
House's own loop stepping on it. The same module holds the House to never importing `league.tests`.

### The House's jobs

`league/ops/`: the House's tick calls `_ops_step` once (never waiting); due jobs start as one child at a time, the
earliest first and, among jobs due at the same instant (a House start's), in the registry's order, so the grant goes
first (fast lane v2's review) (`python -m league.ops run <job>`: nice 19, memory bounded at what it holds plus 500 MB, CPU and wall limits, a
scrubbed environment). Session triggers read the House's NYSE calendar (`ltcm.data.us_equity_session`), so they follow
DST and early closes; the fixed daily, weekly and monthly UTC times sit outside every session in both seasons, and the
hourly `grant` job also runs in session (a niced, bounded child like every other). Every occurrence gets one row in
`<state>/ops.sqlite` (`ok`, `failed`, `missed` or `skipped`; a run a House restart cut short is marked interrupted and
started again while its grace allows); a job not started within its grace is `missed` and a House warning; a failed run
is retried after 15 minutes inside its grace (at most 3 attempts) unless the job may not repeat. Alerts a job raises
reach the House at warning level at most, scrubbed of box ids and dollar figures (the full text stays in the private
receipt). An occurrence older than the runner's first tick on the state, or than 8 days, is never reported; nor is one
older than the first tick whose registry held its job and trigger (`first_seen` in the `ops.sqlite` kv), so a job or a
trigger a release adds (`stall`, the engineer's hourly :40) starts from the deploy, never `missed` for the days before
it. The first runner to keep `first_seen` on a state that already ran jobs reads the receipts: a trigger none of whose
occurrences past its grace has a receipt was not in the old registry.

| Job | When (UTC) | Grace | What | In a maintenance pause |
|---|---|---|---|---|
| `grant` | at each House start, and hourly at :05 | 70 min | the standing grant (below) | skipped |
| `budget` | after `economics` finishes ok, and daily 00:30 | 3 h | the budget rule and funding notices (below); with no fresh Sail guard reading it first waits up to 270 s for the guard's next one (not deployed) | runs |
| `budget_refresh` | at each House start, and hourly at :35 (the no-captain automations, Oct 10) | 70 min | the budget rule read again: written only when it raises a meter (the top-up raise) or sets a day's first figure; the full `budget` job when `budget.json` is unusable; never lowers a figure, never writes a meter it could not read, sends no notice | runs |
| `hygiene` | daily 02:00 (never within 30 minutes of a session) | 3 h | end practice cohorts barred from the incubator (a retired family's cohort only when `ops.json` `hygiene.end_retired_cohorts` is true); mark `failed` pool rows `terminated` when Sail lists the box terminal or gone; the tournament's idle rule, never below `population.floor`; report stale live instances | skipped |
| `clock` | daily 11:00 | 2 h | Alpaca's `/v2/clock` and `/v2/calendar` against the House's calendar for the next 10 sessions; a mismatch is a warning; writes `<state>/calendar.json` | runs |
| `preopen` | trading days, open − 60 min (12:30 summer, 13:30 winter) | 40 min | the nine pre-open checks (release, grant, gateway caps, account and kill switch, swarm, bands, mirror, backup, compute), read-only; each FAIL a warning | runs |
| `economics` | trading days, close + 10 min | 3 h | the one-cutoff close economics (realized options P&L from the Sept 26 basis, every cost from T0, open lots at conservative marks, one Net, deposits never counted) and `p30`; private, `<state>/economics/<YYYYMMDD>-close/` | runs |
| `scoreboard` | daily 23:30 | 2 h | the public-safe daily page with its Funnel table (**The stall alarm and the funnel**), committed to `docs/runs/desk/<date>.md` through the gateway | skipped |
| `stall` | every 30 minutes, at :20 and :50, round the clock | 70 min | the stall alarm (**The stall alarm and the funnel**, below; the equity lanes' own causes since release E2.4): read-only; one `stall` notice listing every cause (an owner step at once and every 12 h, the rest every 24 h); a House warning per cause every 12 h | runs (a pause left on 6 h is one of its causes) |
| `drills` | first Saturday of the month, 15:00 and 17:00 | 6 h | the failure drills (below); never retried | skipped |
| `postmortem` | Saturdays 14:00 | 6 h | the weekly post-mortem, and the cost review on the month's first Saturday (Phase 5; **The improvers**) | skipped |
| `agenda` | daily 03:00 | 6 h | the strategist's agenda (Phase 2); not in this release | skipped |
| `engineer` | daily 04:00 (authors), hourly :40 (moves its candidate on) | 50 min | the engineer's harness change (Phase 4; **The improvers**); never retried | skipped |
| `direction` | at each House start (after the grant: jobs due at the same instant start in the registry's order), and daily 01:00 (fast lane v2) | 3 h | the Gym roots' daily split-adjusted SIP closes from 2024-12-31 (XSP and SPXW read SPY) through the gateway's bars route into `<state>/direction-closes.json`, for the same-risk buy-and-hold beside each screen result and band row (reported, never a bar); a gateway error writes nothing and is a failed receipt (a House warning, retried inside its grace) | runs |
| `fast_lane` | after each `direction` run (fast lane v2) | 3 h | the fast lane's report, read-only (`guard.readonly()`), into `<state>/fast-lane-report.json`: the last 7 days' Validation rows and every look, band row and the Probe budget, each with its drift fit and same-risk buy-and-hold, the contamination measures and D5 (`league/ops/fast_lane.py`; reported, never a bar); a Probe or Sized family whose look has no buy-and-hold is a House warning | runs |
| `game` | daily 00:00 (the learning game, Oct 8) | 3 h | the learning game's report, read-only (`guard.readonly()`) and operator-only, into `<state>/game/report-<day>.json`: R1-R6 of its measurement plan and the pre-registered decisions (`league/ops/game_report.py`; **The learning game v1**, above); a failed R1 is a House warning naming the failed checks, never a figure; with the game off and no look it writes nothing | runs |
| `forward_register` | at each House start, and hourly at :25 (release E3) | 70 min | the forward registry (**The forward record**, at the top): every equity version judged on the Train bar, each seed and live instance and the controls, hash-chained, into `<state>/forward.sqlite`; the tags and the stop rules; skipped while `elane.forward.mode` is off | runs |
| `fill_minutes` | at each House start, and trading days, close + 45 min (release E3) | 3 h | the send-minute 1Min bars of the universe into `<state>/equity-fill-minutes/` (two bar requests a session); its start run fetches a missed day | runs |
| `forward_shadow` | after each `equity_data` run (22:30; release E3); never inside 09:00-17:30 ET on a session | 3 h | every registered program recomputed whole on its forward days in the job's own decider child, the controls, the checkpoints, the live-like re-price and the live twins; at most `elane.forward.cpu_seconds_night` of child time | runs |
| `forward_report` | after each `forward_shadow` run, and trading days, open − 35 min (release E3) | 3 h | the forward record's meters and `<state>/forward-report.json` with alarms FW1-FW9 and, while the panel lane's switch is up, FX1-FX3 (operator-only) | runs |
| `forward_audit` | trading days, open − 25 min (release E3) | 40 min | a forward day whose bars the morning audit found different leaves the counted days; the registry's hash chain is verified | runs |
| `forward_xs` | after each `equity_panel` run (01:55; release E4, package J); never inside 09:00-17:30 ET on a session | 3 h | the panel lane's forward night: every registered panel program recomputed whole on its forward days, each live panel instance's shadow twin, and the twin marker the lane reads before mode "live" (**The forward twin**, at the top); a `skipped` receipt while `elane.forward.mode` or `elane.panel.mode` is "off", while the House's daily store holds no forward day (where `forward_shadow` skips too), and while the panel store holds no session whose rows are final | runs |
| `contam_probe` | Saturdays 00:10 (release E3) | 6 h | the contamination probe: one model route a week, at most `elane.contam.usd_run` dollars; aggregates into `<state>/contamination.json`; never retried | skipped |
| `equity_universe` | daily 01:40 (release E4; never at a House start) | 3 h | the point-in-time S&P 500 membership, the assets and their aids, the audit, into `<state>/equity-daily/universe/` (**The panel lane**, at the top); a `skipped` receipt while `elane.panel.mode` is "off", as each of the five below | runs |
| `equity_panel` | daily 01:55 (release E4) | 3 h | the panel's daily bars through the venue's asof (never 2020), the coverage audit and its verdict, the half-spread table and the spreads' share, the nightly I6, into `<state>/equity-daily/panel/`; 0.4 s before every venue call (as the membership job's asset rows and rename tests), and 30 s then 65 s after a 429 | runs |
| `equity_spreads` | daily 06:30 (release E4) | 3 h | the panel's half-spreads: quote samples at the instants the book trades, on Train-era sessions, at most 6,000 calls and 40 minutes a night until the table is whole (about nine nights), then monthly; into `<state>/equity-daily/spreads.json`. Three hours of grace, not six: with one ops child no daily job may still be working at a pre-open. Its CPU limit is 900 s: the ops client opens a connection a call, about 70 ms of CPU each on the box | runs |
| `equity_neff` | the first Saturday of a month, 10:00 (release E4) | 6 h | the panel's independent names (N_eff on Train segment 2) into `<state>/equity-daily/neff.json` | runs |
| `french` | the first Saturday of a month, 11:00 (release E4) | 6 h | the French library's daily factors where a route to them exists (none today: a `skipped` receipt) | runs |
| `xs_zero_edge` | Sundays 06:00, 08:00, 10:00 and 12:00 (release E4) | 100 min | the panel Train bar's zero-edge column: seeded random-score programs through the whole bar in the job's own decider child, as many as fit its 2,400 s a chunk (it stops itself), into the swarm store's kv `elane_xs_zero_edge` | runs |

Every job is protected: the whole of `league/ops/` is on the list, so a new job or a changed one is the owner's deploy.

`agenda` is registered but its module is not in this release (it is on `v3/b23`): each occurrence writes a `skipped`
receipt that says so. `postmortem` and `engineer` are in the self-running release, ported from `v3/b4` and `v3/b5`
(**The improvers**, below). Being paid, the three are also skipped while the House has stopped buying work. The owner's private `<state>/ops.json` can switch a job off
(`{"jobs": {"<name>": {"enabled": false}}}`) or every job (`{"enabled": false}`), and holds per-job settings: the
economics' declared external costs (`economics.external`) and `hygiene.end_retired_cohorts`. `health.json` carries an
`ops` block (the day's occurrences: due, late, failed, missed, and the job running now). The jobs' logs are
`<state>/ops/logs/<job>.log`; the economics' own output is `<state>/economics/<YYYYMMDD>-close/` (`summary.json`,
`summary.md`, receipts), the clock's `<state>/calendar.json`, the scoreboard's local copy `<state>/scoreboard/<day>.md`.

**The pre-open check 5 (swarm) and the budget's day.** Under the budget rule the Sail guard brakes the swarm for the
rest of each UTC day once the day's research dollars are spent, so a braked guard an hour before the open is the
ordinary case. The guard names its brake's causes (`causes` in its record and in the heartbeat), and the check reads
the names, never the reason's words. Check 5 passes when the guard is not braked, or when it is braked by the budget's
own daily caps alone (`research_budget`, `account_budget`) and its balance was read fresh, by the guard's own
`stale_seconds`, and is above the House's line. Research at its cap is said as the day as designed; a brake by Sail's
own meter at the account's cap passes too and is said as that, since it means the account was billed the day's research
and fixed dollars while the swarm's booked research was under its cap. A brake for any other cause (the balance under
the line, an unreadable balance, a budget rule that could not be read, a full disk), or one that names no cause, is a
FAIL; a FAIL's public warning never carries the guard's reason, which holds the account's numbers (the receipt keeps
it). Check 6 counts the practice rows the swarm offers, not the cohorts the live path has pinned.

### The improvers: the post-mortem and the engineer

The self-running release (Oct 7, 2026) carries the two House jobs that report on the floor and improve it, ported from
`v3/b4` and `v3/b5`. Both are protected (`league/ops/`), so they reach the House only by the owner's deploy. Both spend
Claude through the swarm's router: every call is a `spend` row in `swarm.sqlite`, admitted inside budget rule v2's Claude
meter (the day's Claude research dollars, $5 at the owner's ceiling from the budget split, $10 before, less the gate's
two holds, $1.95).

**The post-mortem** (`league/ops/postmortem.py`, Saturdays 14:00Z). Code reads the week's receipts, read-only: real
orders by outcome and route with the rejection and refusal reasons; the calibration round trips' real fills against
the mid beside the practice book's fills under the Gym's rules; demotions, promotions and retirements; the updater's
self-deploys, the owner's deploys and the engineer's journal; the week's costs by service, its realized options P&L,
the swarm's model spend and the jobs. On the month's first Saturday also the cost review: 30-day costs, the data
vendor's share, research activity and universe, and a proposal for the owner's D6 by a fixed rule (a proposal only).
One Claude Opus 5.5 call (role `postmortem`, its own $1 line, `max_tokens` 16,000, a worst case near $0.52, a
model-safe prompt of aggregates) writes a headline, findings and at most three actions. Private:
`<state>/postmortem/<date>.md` and `.json`. Public: `docs/runs/desk/<date>-postmortem.md` through the docs route, from an
allowlist of counts and dollars and checked by the scoreboard's filter; the model's text joins it only when it passes.
A week the model cannot be asked (no room in the line, the budget at the floor, an error) still gets its facts, with a
warning. Cost: at most $1 a week. It runs once deployed; ops.json turns it off (`{"jobs": {"postmortem": {"enabled":
false}}}`), keeps the facts but asks no model (`{"postmortem": {"model": false}}`), posts nothing
(`{"postmortem": {"public": false}}`) or moves the cost review (`"cost_review": "always"` or `"never"`). Nothing in it
feeds research: no swarm role reads the post-mortem.

**The engineer** (`league/ops/engineer.py` with `author.py` and `reviewer.py`; daily 04:00Z it may author, hourly at
:40 the candidate in flight moves on). One candidate at a time walks `playbooks/harness-improvement.md`: the top
captured bottleneck of an engineer lane (`research`, `memory`, `data`) with its predeclared metric frozen; a change on
the running release's commit, written by Claude Opus 5.5 (role `engineer`, at most $2 an attempt from the budget split,
$3 before) through confined
tools; the static guards; a pull request through the gateway's engineer role; green CI on the exact head; an
adversarial review of the exact diff (role `reviewer`, at most $1), its verdict posted to `/v1/github/review` (a CI
failure or a reject goes back once); the gateway's merge (at most 2 a New York day, never a protected path, never with
the kill switch on); the updater's deploy at its train; the canary (an arm in `<state>/harness/canary.json`, or the data
lane's window); retain or revert once by the predeclared metric, a revert being a pull request through the same route;
then 20 sessions of the global guard on the promoted programs' forward record. The journal is
`<state>/harness/engineer.sqlite`; the daily scoreboard counts authored, merged, retained, reverted, rejected and failed
candidates and lists the engineer pull requests left for the owner: those the gateway would not close, and a revert that did not merge (the
owner's revert by hand may be merging it). The engineer closes its own superseded and unmerged pull requests through
`POST /v1/github/close` at their exact heads. It cannot
change a protected path: the author's tools and static guards, the gateway's lane surface and protected list (on the
pull request and again on the merge), `league/ci.py` `FORBIDDEN` in CI and the updater's own refusal each stop it.

What the self-running release adds to `v3/b5`:
- **One switch, on:** `engineer.enabled` in the swarm settings. The committed `league/swarm/policy.json` sets it true;
  the box's `swarm.json` `{"engineer": {"enabled": false}}` wins over it with no deploy, and ops.json
  `{"jobs": {"engineer": {"enabled": false}}}` stops the job. The job serves its own two roles (`engineer`, `reviewer`,
  on Claude Opus 5.5 unless `claude.role_model` names one) in its copy of the settings, since the box's `swarm.json`
  replaces `claude.roles` whole.
- **$3 a UTC day** (`engineer.usd_day`; $4 before the budget split): the engineer and the reviewer together, holds
  included. An attempt is capped at what is left, and no attempt or review starts with less than its own cap: one
  attempt ($2) and its review ($1) a day, inside the Claude meter at the ceiling ($5) less the gate's two holds. It
  authors at most once a UTC day (its 04:00Z occurrence's own day: 04:00Z is New York's midnight in summer and 23:00
  the day before in winter, so a New York day skipped one authoring a year) and only with nothing in flight, so most
  days cost a review, a revision or nothing.
- **Research-class only:** a lane file the live path loads is held (`RELEASE_CLASSES`; on this tree
  `league/swarm/researcher.py` and `claude_research.py`): the tools refuse it, the brief names it held, and a candidate
  whose tree classifies as money-path or evidence-reset is closed before its pull request. The gateway holds the same
  two files (`gateway/lib/github.mjs` `ENGINEER_HELD`): no engineer pull request opens on them or merges them, so the
  hold is two walls. `league/ci.py`'s lane table still lists them (a branch pushed by hand is the owner's). Opening the
  money path to the engineer is a change to both: an owner deploy of the House and of the gateway.
- **A base after an owner deploy:** an owner deploy carries no updater attestation. When no observer policy names the
  running release either, main's head is the base if its release trees digest to the running tree, remembered for that
  release. An owner deploy of anything but main's head leaves the engineer idle, its daily note saying why, until the
  next updater release.

What it needs, in place since V3-A: the gateway's engineer routes with `autonomy.engineer_pulls` in `/v1/health`, green
`checks.yml` on main, and `auto_update` on (an engineer merge is an updater release: it deploys outside the updater's
calendar hold, at most one a train).

### The stall alarm and the funnel

The owner's goal of Oct 7, 2026 (item 6: "raises an alarm when it stalls ... push me a short note when something only I
can do is blocking"; item 3: "report the funnel daily"). From Oct 3 to Oct 7 research ran 1 to 13 Gym runs a day with
no birth and nobody was told: the House's only alarm (a pre-open FAIL) went to a ledger row no mail carries.

**The `stall` job** (`league/ops/stall.py`, every 30 minutes at :20 and :50, round the clock, a maintenance pause
included: it is read-only like `preopen` and `clock`). It reads the swarm store, `budget.json`, the swarm's heartbeat,
`deploys.jsonl`, the pause files, the `grant` job's receipts in `ops.sqlite` and the gateway's `/v1/health` (since the
weekend fixes also `dlane-report.json`, the `preopen` receipts and the nightly's `gym-forward.json`, `data/nightly.json`
and `data/nightly.stop`), all read-only, and names a stall by its cause:

| Cause | Raised when | The owner step it names |
|---|---|---|
| `births` | no `swarm.born` in the last 12 h while the living population is under `population.ceiling` (as the swarm loads its settings, the budget's tightening included) | none, unless the Sail guard is braked under its line or for disk, or the kill switch is on |
| `gym_runs` | fewer than 10 Gym runs in the last 6 h (a run is a `runs` row the Gym evaluated: a row with a trial, neither `refused` nor `error`; those, and the rows with no trial an F1 verdict copies from an identical program, are counted apart) | as `births` |
| `validations` | no Validation verdict in the last 24 h (no validation the Gym evaluated, no verdict read from an identical program, nothing a tournament round judged) while a living family is owed one: its candidate (the submitted best, else the Train best the researcher picked by score, `state.best_train_version`, as `Tournament.candidate_version` reads it) is not its validated version, and the last round within the 24 h did not leave it waiting on its 1.5x robustness run or the drift screen (those are counted apart) | as `births` |
| `braked` | the Sail guard braked 12 or more of the last 24 h, whatever the cause (the budget's daily stop reached by noon keeps research from running round the clock as surely as a low balance) | "top up Sail" for `under_line`, "free disk" for `disk`; none for the budget's own stop |
| `runway_sail`, `runway_claude` | the meter's days of research left at the ceiling (`budget.json` `card_runway_days`, the figure the funding notice reads) under 3; a `budget.json` older than 36 h is not read | "top up Sail" or "top up Claude (Anthropic)", with the budget's own amount for 7 more days |
| `owner_deploy` | the updater refused main's head as the owner's deploy (a `deploys.jsonl` `vet` refusal naming a protected file, the workflows or `real_money`) and no release was promoted since: main's head and the running release differ in a file only the owner deploys. Since the weekend fixes (the readiness audit's M12) a refusal counts only once it has stood 45 minutes, and never while a deploy is in flight (a `deploys.jsonl` `start` row with no verdict yet, at most 2 h old, or the operator's own `data/nightly.stop`, the deploy's step 2, at most 2 h old) | both ways out, since the record does not say which side is ahead: "if main is ahead, deploy it yourself (`scripts/floor_box.py deploy`); if the running release is ahead, merge it to main instead", naming the files |
| `paused` | a maintenance pause (`<state>/PAUSE`) or a stopped swarm (`<state>/swarm.stop`) has stood 6 h or more (by the file's time). While either stands, `births`, `gym_runs`, `validations` and `braked` are not raised: a pause stops research by design | "lift the maintenance pause once its work is done (`scripts/floor_box.py maintenance off`)", or "remove state/swarm.stop" |
| `grant_refused` | the standing grant refused to re-ratify since the `grant` job's last `ok` run (its receipts: `standing grant refused`; a failure to read the account is no refusal) | "ratify the grant by hand on the box (`python3 scripts/live_trading.py --ratify`)", with the grant's own reason |
| `kill_on` | the gateway's kill switch is on (`/v1/health` `kill_switch`; since its latest `kill` in `admin_log`): no real order, no Claude call, no merge. An unreadable health is no cause | "lift the gateway's kill switch once its cause is fixed (`python3 scripts/gateway_admin.py unkill`, your admin token)" |
| `dlane` (weekend fixes) | `<state>/dlane-report.json` carries a warning-level alarm (A1-A7, DC1, PL1, PT1, K5, and the forward record's warnings it carries: FW, FX, RR1, CP2, MM1), or it is older than 30 h while the lane is on. The mail names the first 4 warnings, K5 and DC1 before the rest (the `dlane` job stopped). With `dlane.mode` "off" the report is not read at all (the job writes none, so the last one would otherwise be mailed for good) | K5 holding: "the direction lane reads shadow while K5 holds ...: read its losses, then clear it"; K5 disarmed: "take dlane.k5_clear out of swarm.json"; none for the rest |
| `done` (weekend fixes) | a FINAL Done checkpoint holds (the report's `done.<meter>.checkpoints`, final and holding: frozen from report to report) that no SENT notice has told yet (`stall.json` `done_told`, added to only when the gateway says it sent the notice). Not read with the lane off. Until the review of the weekend fixes it read the report's A8, which one report says once, so a House start or a failed notice before the next stall run lost the claim | an owner LINE, told at once: "Done holds at a FINAL checkpoint ...: read the claim in dlane-report.json". News, never an owner step waiting: the Done meter's item 7 does not count it |
| `preopen` (weekend fixes) | the latest pre-open receipt (`ops.sqlite`, at most 24 h old) failed a check, or the job failed or was missed | none: each FAIL is a House warning, and the checks run again before the next open |
| `births`, the jam (no-captain, Oct 10) | no birth for 6 h while at least 4 architect passes wanted births (asked a model, found no cell, or failed; a pass at the ceiling wants none), the population under its ceiling | at once when a setting or an agenda clears the main way they bore nothing: "the architect wanted births in N passes over the last 6 h and none was born:" and its lever (incomplete cards and the fields they lack, the rebirth rule's refuted cells, a spent lineage, a cap, no open cell, cut answers); none (INFO) for failed calls, an empty answer or another refusal |
| `birth_yield` (no-captain) | over the last 3 h at least 4 passes asked a model and bore at most 1, or the card checks refused 80% of their proposals; or no birth in 2 h while 3 passes wanted one (from the `swarm.architect` events) | none (INFO); the jam above is the owner's step |
| `swarm_alerts` (no-captain) | an owner kind whose condition stands now (`stall.alert_states`, from the swarm's settings and store, whatever its alert's age), or a `swarm.status` alert (`alert` true) in the last 12 h whose condition is not read or cleared, but the self-healing ones (`sail_window_stall`, `funding_alert`) alone | for `reader_cut`, `agenda_guard`, `policy_layer`, `train_span_pending`, `train_span_mismatch`, `gate_missing_data`, `gate_coverage`, `game_waits` while their condition stands, and `look_failed_three_times` on the UTC day it fired: the setting or fix each names (`stall.ALERT_STEPS`); none for the rest |
| `underspend` (no-captain) | Sail's booked research today under 70% of what its day's figure buys by now at an even pace (from 6 h into the day, the guard braked under 2 h of it; Claude's reading is said, never a cause), or two settings that cannot both hold while they bind (`settings_binds` conflicts: the class cap once a direction card met it in the last 6 h); the settings that bind research are named either way | none (INFO): the settings named are the owner's to change |
| `elane_dq` (release E2.4) | the equity lanes on and judged: more than half of the equity versions scored in the last 6 h (6 at least, since the running release started; fewer in the 6 h: the last 6 scored; before the sixth: 4 that could not be judged) could not be judged for a fault of their own program (disqualified, refused at load, failed by the decider child), in at least two families; once it stood under a release, until versions scored after are judged by the bar in two families or the release changes | "the equity generators misread the program contract, mostly <the class> (<what it most often is>): fix the text they read (league/equity/EQUITY.md "Reading ctx", elane_review.READING_CTX) or the static rule that should refuse it, in a release" |
| `elane_births` (release E2.4) | the last 3 equity passes that asked a model (in the last 12 h, since the running release started) bore no family | none for 6 h (each pass tells the next its refusals); then, when a setting clears the main way they bore nothing: widening `elane.universe` or `elane.structures` (your decision), `elane.e2.births_max_output_tokens` or `elane.e2.max_per_pass` for answers cut short, a release for a pass that raises; at once for a setting every route refuses the request for; none for the rest |
| `elane_idle` (release E2.4) | a BROKEN lane only. Whatever E2's lines hold: more than half of the program questions the Train rounds asked in the last 6 h (8 at least, since the running release started; fewer in the 6 h: the last 8 asked; before the eighth: 5 lost) were lost to a fault (the answer held no program, or no route answered for 3 h while the lanes kept asking), idle or not; or families in Train research or births wanted, no equity version scored for 3 h (the swarm's running time, kept per release), and the lane's own record shows two rounds that raised, two Train steps failed on the House's side or two step errors; and once either stood under a release, until a version is scored after it, the release changes or no work is owed. Else, idle so, only when no hold of E2's was seen in those 3 h. NEVER for a lane held by its own pace, its day's dollars or the House's Sail day: that reads judged clear and says the steps it cost | "the equity lanes pay for answers that hold no program (<the routes>): raise elane.e2.train_max_output_tokens if they are cut short, or take a route out of elane.e2.routes ...", "no model route answers the equity lanes' program questions (<the routes>): check the routes at the model provider, or name routes that answer in elane.e2.routes ...", "the equity lanes' rounds raise ...", "... Train runs fail on the House's side: check the equity_data job's receipt and the swarm's equity-decider.log", "... Train steps fail with errors", "... rounds run and judge nothing" or "... start no round"; none for lost answers too few to be most, programs refused before a run or barren passes |
| `elane_refused` (release E2.4) | more than half of the programs the equity generators wrote in the last 6 h (8 at least, since the running release started; fewer in the 6 h: the last 8 written; before the eighth: 5 refused by one rule) were refused before a run by one static rule | "the equity generators are not being taught <the rule>: teach it where they read it (league/equity/EQUITY.md, the researcher's system prompt, elane_review.READING_CTX), in a release" |
| `forward` (weekend fixes) | the nightly's ready file (`gym-forward.json`) does not carry the last session before today once the UTC day is 10 h in; `data/nightly.json` has carried an error 6 h or more (from the first run that saw it, kept in `stall.json`); or `data/nightly.stop` has stood 2 h or more. Since the source gap (Oct 14): the controller has retried the same day 6 h or more (`nightly.json` `retrying`, or the stall's own first sight of the error for that same day when that is older: `stall.json` `nightly_error` keeps its day, and a record naming another day starts the count again), named with its short roots and their coverage ("SLV: SIP 389/390, minute 826 (13:46 ET) missing"); or the day the nightly owes has been due 36 h or more (from 02:00 ET the morning after it) with no day completed in as long | for a stop: "remove /workspace/state/data/nightly.stop ... the nightly forward replay, and with it the Done meter's replay twins, waits while it stands"; for a day owed 36 h: "the nightly owes DAY and has completed no day in N h: read data/nightly.json (error, retrying) and data/images.json forward_days. The House hands off only a small SIP source gap by itself, so this needs a fix it cannot make (ROOTS)" (a gap wider than 5 minutes or 2 roots, or empty or invalid bars, schedules no hand-off and reaches it), held back while the nightly has a hand-off scheduled (`retrying.handoff_at`) until an hour past it, or while the record has an error and no `retrying` (the release before wrote it: a deploy's window before the first new try), and never once the day has been owed 72 h; never while a nightly stop stands (the stop is the step); none for the rest |

**The equity lanes' own causes** (release E2.4; the four `elane_` rows; `league/ops/elane_health.py`, which the
stall job calls once): judged only while the lanes are on and not paused, on evidence since the running release first
started (`stall.json` `elane`, with the clocks kept under it), else "Not judged" with the reason, and an `errors`
entry and a House warning every 12 h when the lanes could not be read; `elane_idle` stands for a broken lane only
(most of its program questions lost to a fault, or idle with its own record of failures; held once it stood until a
version is scored), and a lane starved by a setting is read in the check's numbers and the research funnel, never in
the mail;
**The equity lanes' own alarms**, at the top, says how to read each and what to do. They are the last four of
`stall.CAUSES`, causes like any other (`stall.json`, the House's warnings, the daily page's standing causes, the
receipt's `checks`, the notice), and Done's item 7, which reads the receipts' checks, counts an owner step of theirs
like any other's. The gateway words each (`STALL_CAUSES`, which its own test holds equal to `stall.CAUSES`; an
unknown cause is a 400 for the whole notice: the gateway deploys first), so in the mail each is an entry of its own,
keyed by its own name: none rides `swarm_alerts`, and neither holds back the other's mail.

**The notice.** One `POST /v1/notify` kind `stall` a run at most, through the budget's own gateway client, listing
EVERY cause standing, owner steps first: the subject `LTCM: needs you: <the causes with an owner step>` or `LTCM: stalled:
<the causes>`; the body opens with the owner steps (or "nothing here needs you"), then each cause with the House's
sentence, its numbers, how long (from the record when it says: the last birth, the last Validation verdict, the start of
the brake, the first refusal, the pause file, the kill; else from when the job first saw it) and what the House is doing
about it (the architect's passes and why each made no birth, the researchers' cycles, the guard's state and the
heartbeat's age, the tournament's last round and what waits on robustness or the drift screen, how the guard releases,
the budget's taper, the updater keeping the running release, the grant job asking hourly). It is mailed:
- while some cause has an owner step: at once when one of them was not in the last owner notice (a new top-up, a new
  refusal), else at most once every 12 hours;
- while none has: at most once every 24 hours after the last notice of either kind.

The gateway holds the same pace by its own record, whatever id the House sends: it keys an owner notice on its owner
causes (`stall:owner:<causes, sorted, joined by +>`, 12 hours) and one with none on `stall:info` (24 hours), inside
`NOTIFY_MAX_PER_DAY`. A notice counts as told only when the gateway says it SENT it: a `duplicate` answer or a failure is
tried at the next run. Each cause standing is also one House warning (`stall: <cause>: ...`, its dollar figures
scrubbed) every 12 hours. `<state>/stall.json` (private) keeps each cause (since when it stands, when it was last warned
of, when it cleared) and the notices (when the last owner notice and the last other notice were sent, which owner causes
it told). A cause that clears is named in the receipt (`cleared`); the receipt carries every check with its numbers and
what the House is doing. The job moves no money, changes no setting, and starts and stops nothing; it writes only
`stall.json`. Switch it off like any job (`ops.json` `jobs.stall.enabled` false).

**The funnel** (`league/ops/funnel.py`, read by the `scoreboard` job): the daily page gains **Funnel (last 24 h /
since the release)**, the last 24 hours beside the time since the running release's latest `promoted` verdict in
`deploys.jsonl` (n/a when the record has none): births (`swarm.born`), program versions written, Gym runs by window
(train, validations, looks, forward, probe, mechanism; refused or failed apart), validations judged and passed (the
tournament rounds' verdicts; rows copied from an identical program's verdict, F1, are their own row and no Gym run;
since the swarm-side readiness fixes, the validations sent to the gate as `entered`, split by screen, with a page row
only when D2's pre-check sent one),
looks taken and passed, moves to Candidate, Probe and Sized and the bands now, real orders
(and of them filled) and real closes by route (the agents' routes against the House's, as the close economics routes
them), research spend by meter (Sail, Claude, OpenAI) and the hours the Sail guard braked, then the stalls standing
(causes and since when). Counts and spend only, never a Validation or holdout figure, and the page passes the public
filter as before. A section that cannot be read is n/a, never a zero. The equity lanes' counts are in the funnel
apart (`equity`), and since release E2.4 their research funnel with them (`equity.research`,
`elane_health.research_counts`): the daily page prints no equity row, as before; the `scoreboard` job's receipt
(private) carries the equity block for both windows (`equity`: `day`, `since_release`).

### Observing without exec

The House rewrites `<state>/receipts/<YYYY-MM-DD>.json` and `latest.json` every ten minutes: every job occurrence of the
day with its receipt, a health summary, the day's `deploys.jsonl` rows, the swarm's spend by kind, the budget's state
and the latest close economics' headline. It is private (mode 0600). Read it from the laptop through the Sail Files API,
a GET of one file, never an exec:

```sh
python3 scripts/desk_receipts.py                 # latest.json
python3 scripts/desk_receipts.py 2026-10-06      # one UTC day
python3 scripts/desk_receipts.py --json          # the whole file
```

`floor_box.py status`, `logs`, `deploy`, every `on the box` command and every hand edit of a file on the box are execs
or writes, and Sail records every exec. During the unattended clock (the plan's measure: 30 days in which no command
from the owner's machine touches production) the operator's whole view is read-only:
- the receipts file (above);
- the House's daily pages in [runs/desk/](runs/desk/README.md), and its commits and CI runs on GitHub;
- the gateway's `/v1/health` (`gateway_admin.py status`): the caps, the kill switch, the meters, `admin_log` (every
  kill, unkill and admin-token call) and `autonomy` (the desk's docs commits and merges today);
- the public page.

A command that touches production is not forbidden: it ends the clock, and the run record says why.

### The drills and the rollback drill

The `drills` job (`league/ops/drills.py`) is due twice on the first Saturday of each month, 15:00Z and 17:00Z. A drill
done in a month is not run again that month (`<state>/ops/drills.json`), so a run the House's own restart cut short and
the second occurrence pick up where the first stopped. In order:
- `funding`: for each meter, a synthetic runway cliff goes out as the real notice would, with `test: true` (two test
  mails), and an unreadable balance must give that meter no research;
- `sail_read` and `gateway_outage`: a failed Sail read and a gateway that does not answer must fail fast and give no
  research on that meter; recovered when the real reading and the real gateway answer again;
- `swarm_kill`: the swarm process gets SIGTERM and the House must have started a new one within 10 minutes;
- `rollback`, last: the job only writes a request (`<state>/ops/drill-request.json`) and returns. The updater, in the
  House's own process, launches the drill detached at its next full look with nothing in flight, never from the job's
  niced, bounded child. The 17:00Z occurrence reads the drill's verdict in `deploys.jsonl`; a request the updater never
  took is withdrawn then.

A Gym box failure is not drilled yet (the pool has no hook to fail one of its own boxes).

The rollback drill itself, on the box:

```sh
cd /workspace/current && /workspace/.venv/bin/python -m league.watchdog drill-rollback --base /workspace
```

It stages a copy of the CURRENT release (`drill-<stamp>`) with `DRILL_BREAK` in its root and deploys it like any
release; the House started from it raises an error alert ("drill: deliberate break") every tick and never looks at
main, so the watch must roll it back. `rolled_back` is a pass; `promoted` means the break was not caught (the drill
then rolls the copy back itself). It puts `previous` back to the release it named before the drill, removes the copy,
lifts its own nightly stop (`drill:<id>`) and writes a `stage: "drill"` row to `deploys.jsonl` for every outcome. So a
drill restarts the House twice and leaves `current` and `previous` as they were. Refused inside the updater's session
hold or when the calendar cannot be read, while a deploy is in flight, on a House stopped on purpose, on a release that
is itself a drill copy, and when the current release's `config.json` does not turn `auto_update` on. A drill whose
process died after the promotion is recovered by the House it left running (`drill-recover`).

### The budget rule (D4)

`league/ops/budget.py`, protected; constants changed only by an owner deploy (rule version 2 since Oct 3; the module
docstring is the rule). For each meter m in {sail, claude}: `balance_m` (Sail: the guard's last good provider reading,
at most 6 hours old; Claude: the gateway's funded total left), `fixed_m` (Sail: the House and data boxes' own billing a
day over the trailing 7 days, never below `guard.house_burn_usd_day`; Claude: 0), `reserve_m` (Sail: the Sail guard's
own release line, $37 at the configured burn, never under $10; Claude $5); and `p30`, the trailing 30-day realized
options P&L, fees in, every real route. Marks never fund research.

```
ceiling_m  = $25/day × split_m              split: sail 0.8, claude 0.2 = $20 and $5 (0.6 and 0.4, $15 and $10, before)
runway_m   = max(0, balance_m − reserve_m − 5·fixed_m) / 5
research_m = min(ceiling_m, runway_m)       set once a UTC day by its first run, from the balance as the day began;
                                            raised (never lowered) by a later run whose reading sets more (a top-up)
earned     = 0.5 × max(0, p30) / 30         written, inside the ceiling: it lifts no meter
```

- **The split** is Sail 0.8 and Claude 0.2 from the budget-split release (**The budget split**, top of this page; not
  deployed: production still runs 0.6 and 0.4). The owner's ceiling stays $25 a day.
- **`p30` is the live book's own read first.** The rule reads the closed real positions and the broker's posted fee
  corrections itself. The close economics can only cut that number: its `p30` is used when its summary is the latest
  close and its number is smaller, never when it is larger. Unknown stays unknown: while a position is closed but not
  priced, an order is pending or unknown, reconciliation is frozen or the account reading names an event the book has
  not settled, `p30` is unknown from either read, `earned` is 0 and the job raises a warning. With no fresh close
  summary (none yet, a stale one, one that cannot be read) the book's read stands alone and each run says so in a
  warning.
- **The no-forward-edge stop:** once 60 sessions have closed since Oct 5, 2026 (or since the day after the last
  promotion to Probe: the forward ladder's, or the Money table's move after a passed holdout look) with no such
  promotion, `earned` is 0 and the state says "no forward edge". `earned` sits inside the ceiling, so today the stop
  cuts no research.
- **Unknown is never money:** an unreadable balance, fixed cost or reserve gives its meter no research; an unreadable
  `p30` earns nothing; a rule that cannot run at all is no research on either meter.
- **The wait for the guard's next reading** (L4, on `fix/budget-guard-wait`, not deployed). A `budget` run that finds
  no fresh Sail guard reading waits for the guard's next one. It looks at the guard's record every 20 s, for at most
  270 s from its start, inside the job's 600 s wall. When a reading comes, the run takes a new time after it and reads
  every input again at that time. With no reading by then, Sail stays `unreadable`, as before. The warning then starts
  by saying how long the run waited after its first read. When the first read alone took the whole 270 s, it says the
  run never looked. The sleeps add up to at most 270 s. A fresh reading at the start means no wait. Only the guard's
  own reading ends the wait: the gateway's Sail reading is still the card line only. `budget_refresh` does not wait,
  also when it runs the full job. Why: on Oct 15 the owed 00:30Z run came 28 s after the box came back and 3 s before
  the guard's first reading, and one `unreadable` receipt fails the day for Research247. In a swarm pause of more than
  6 h the guard has no fresh reading, so each `budget` run waits the full 270 s, and the next job waits behind it. The
  wait covers the guard's first one or two checks after a start (it checks every 180 s). It does not cover a swarm
  that takes more than about 4 minutes to reach its loop: that run still writes `unreadable`. `budget.json` and the
  receipt say `guard_wait` (the first read's seconds, the seconds waited after it, looks, whether it read) when the
  run found no fresh reading.
- **Output:** `<state>/budget.json` (private): the inputs, each meter's research $/day and the day's figure, the knobs,
  the direction against the last file (`cut`, `raise`, `same`), each meter's runway at the rate the rule holds it to,
  its days of research left at the ceiling and its card date (when those days fall to 5: the day the taper starts),
  the amount that buys 7 more days, and why.
- **Enforcement, tighten-only** (the last step of `settings.load`): min() against `researcher.sail_usd_per_hour`
  (Sail research × 0.4 / 24), `gym.max_boxes` (Sail research × 0.6 over $0.20 an hour × 8 busy hours, at least 1),
  every `claude.role_usd_day` line and `population.ceiling` (a family a dollar a day, at least 8 and never below
  `population.floor` + 4), with `population.start` held to the tightened ceiling; max() against
  `architect.every_seconds` and `architect.refill_seconds` (4 hours at the floor, down to 30 minutes, once a day with
  no research dollars). The Sail guard's daily cap is the budget's: the swarm's booked Sail under the Sail research
  $/day, and Sail's own meter under that plus fixed. Claude's room is also capped by the budget's Claude $/day less
  today's paid-model spend, each model's spend counted on its own and never under 0, so a hold one model released
  never pays for another's spend, and less the gate's holds by stage (every role but the gate's two leaves the
  review's $0.65 and the audit's $1.30; the review leaves the audit's). OpenAI is closed (`guard.openai_cap_usd` 0): it is not a meter of the rule. At Sail's $20 the knobs are 7
  Gym boxes and a Sail model pace of $0.33 an hour; the committed `policy.json` caps (7 boxes, $0.34) let it reach
  them, and the box's own `swarm.json` wins over `policy.json`.
- **No file, a bad file, a stale file.** A missing, unreadable or malformed `budget.json` is the floor ($5 a day split
  as the ceiling is: $4 of Sail research and $1 of Claude; $3 and $2 before the split). One older than 36 hours never
  loosens: each meter is the lower of the floor and what the stale file said, with a warning. A research budget of 0
  brakes the Sail guard at once. At the floor Claude's $1 is under the gate's two holds: the review runs on its Sail
  model, and the audit too unless its hold is at most $1, each with the gate's "not the plan's reviewer" alert.
- **The top-up raise** (the no-captain automations, Oct 10, deployed 21:42Z). A later run of the day whose own reading
  would set more than the day's figure raises it to that reading's (raise-only, never above the ceiling, nothing added
  back; `day_figure.raised_from` and `raised_at`, with the day's first figure and every raise, `set_usd_day` and
  `raises`), so a top-up reaches the day's research, the knobs and the guard's caps within the hour: the
  `budget_refresh` job reads the meters hourly and at each House start and writes `budget.json` only to raise a meter
  or set a day's first figure. A raise is computed on the larger of the reading's fixed cost and reserve and those the
  day's figure was set on (`day_figure.fixed_usd_day`, `reserve_usd`): a fallback reading never raises. A day whose
  first run tapered still reads as a taper day for DONE-RULE item 7.
- **The taper is the rule.** A meter runs at its share of the ceiling while it holds 5 days of it above its reserve
  and 5 days of its fixed cost; under that it spends a fifth a day of what it holds above them, so research tapers by
  itself and ends before the balance meets the Sail guard's brake. A cut shows in `budget.json` (`limited_by`:
  `ceiling`, `runway` or `unreadable`) and in the daily page; the way to more research is the owner's top-up, never a
  setting.
- **The funding notice** is computed at the rate the meter WANTS, not at the rate the rule throttled it to: the
  throttled rate keeps the runway near the rule's runway term by construction, so it would never say a prefund is
  short. (Rule version 2, Oct 3, and release D-1b, Oct 9: the module docstring of `league/ops/budget.py` is the rule.)
  When research on a meter runs out within 2 days at its current burn (`out_in_days` in `budget.json`: the lower of
  the runway at its burn and its days of research left at the ceiling, less the 5-day runway term; at the ceiling the
  7-day card line), the House posts one `POST /v1/notify` kind `funding` with the meter, the balance, both rates (the
  wanted one and the current one, each with its runway), the amount that buys 7 more days and the card date. It goes
  at most once a day per meter (a day less an hour since the last; `funding:<meter>:<UTC day>:r2`, which the gateway
  dedupes); before D-1b it was once a week. The mail names both rates: the rate the rule holds the meter to now (its fixed cost
  plus the day's research budget; a ceiling, not a metered spend) and the rate the rule wants for it. A meter spent
  faster than the rule holds it states its burn as the "now" rate, and its card date is the day research runs out at
  that burn (release D-1b, the review's finding 4). Each runway is
  days until the meter's reserve, not until it is empty, and the mail says it as days above the reserve. It says that
  nothing stops without a card only when the figures sent show it (research above zero and the runway at the current
  rate at or over the card line: the rule goes on throttling research). Otherwise it says how long the meter lasts at
  the rate it is held to now, and a runway of zero there reads as none left above the reserve. With no fresh guard
  reading, Sail's card line is read from the gateway's own Sail reading, for the notice only, never for research. The
  gateway's absolute Sail mail lines drop to $25 (low) and $12 (critical), under the rule's own floor.

### The standing grant (D5)

The `grant` job runs `LiveGrant.standing` (`league/live_trading.py`) and replaces the owner's `--ratify` after a
money-rule deploy and after a deposit. It ratifies the grant in force, writing a `ratifications` row with why, in
exactly two cases: the money digest moved and an owner release change (a promotion or rollback with no updater
attestation, not a drill's) is on `deploys.jsonl` since the last pin; or a deposit landed since then (told by its
id). Capital is the lower of equity and the owner's ceiling; it never enables a grant, never touches a revoked one,
never lifts the ceiling above the one last ratified without an owner release change, and refuses (changing nothing,
the occurrence `failed` and a warning) when anything is unreadable or capital would not cover the smallest stake.
`scripts/live_trading.py --disable` stays the owner's stop; the ceiling and the money table stay owner deploys.
`--ratify` on the box still works and is the way when the job refuses: a digest that moved with no owner release on
the record, or a deposit of a type the funding read cannot ask for (a wire). A1 does not move the money digest. Its
record of the deposits it has seen starts empty, so its first run may answer, once more, a deposit an earlier
ratification already held (one dated up to 14 days before that pin): one extra ratification at the same capital rule,
as its code says. After that a receipt reads `none` until a trigger. At the A1 deploy (Oct 3) it did exactly that: one
ratification on the trigger `deposit` at its first look, then `none`.

### The gateway's V3-A routes

`POST /v1/github/docs` (one page under `docs/runs/desk/`, at most 64 KB, at most 6 commits a New York day, message
`desk: ...`); `POST /v1/github/pr` with role `engineer` (a lane, its own files only, at most 2 a New York day),
`POST /v1/github/review` and `POST /v1/github/merge` (engineer pull requests only, above);
`GET /v1/github/pr/<n>/files` and `POST /v1/github/close`; `funding` and `stall` notices on `/v1/notify` (one stall
notice lists every cause: keyed on its owner causes, 12 hours, or `stall:info`, 24 hours); and the admin log (every
kill, unkill and admin-token call, in `/v1/health` as `admin_log`, beside `autonomy`). The kill switch also stops
merges, and `/v1/kill` now takes either token (stopping is never gated); `/v1/unkill` stays the owner's. The Sail
balance mails (`LOW_BALANCE_USD`, `CRITICAL_BALANCE_USD`) are $25 and $12, under the budget rule's own floor, so the
rule's `funding` notice is the one that asks for a card. `OPTION_STRUCTURES_REAL` is unchanged (the four debit types).
Details in [the gateway's README](../gateway/README.md).

## What runs where

| Piece | Where | Driven by | Local record (gitignored) |
|---|---|---|---|
| The House (`python3 -m league run`) | Sailbox `ltcm-house` (`sb_1d99c4a7`; `floor_box.py`'s default name for a new box is `ltcm-floor`), size s, `/workspace` | `scripts/floor_box.py` | `.data/ltcm/box.json` |
| The gateway (venue, OpenAI, Anthropic and GitHub keys, caps, the OpenAI month, Claude's funded total, kill switch, outside watchdog) | Cloudflare Worker `ltcm-gateway` | `gateway/`, `scripts/gateway_admin.py` | `.data/ltcm/keys/gateway-admin.token` (owner only) |
| The data box (ThetaData downloads, the store) | Sailbox `ltcm-data`, size l, `/data` | `scripts/data/box.py`, `nightly.py` | `.data/gym/data_box.json`, `universe.json` |
| The Gym and gate images | Sail checkpoints (two each, one-year TTL) | `scripts/data/images.py` | `.data/gym/images.json` |
| Gym boxes and the gate box | sealed forks of the images | the swarm's pool (`league/swarm/pool.py`) | the House's state |
| The public page | blakewoods.us/capital (`~/Work/personal-site`) | the House's publisher | - |

Owner deploys run from the checkout `~/Work/ltcm-deploy`. Its `.data` is a symlink into the main
checkout's `.data` (the box record and the admin token): never `ln -sfn` over it.

## Rules that hold every day

- **No money-path deploy from 13:25Z to 20:05Z on a trading day** (to five minutes after the close when that is
  later: 21:05Z in winter), except a rollback: the gateway, the
  constitution, `league/live` and every module the live path loads (the money path, below). A research-class House
  release (no module the live path loads) may deploy in session after an adversarial review, green CI and on-box
  verification, never 19:30-20:00Z (15:30-16:00 New York, while the House live test runs) and never while a
  calibration order works (`league/swarm/harness_lanes.py` `DEPLOY_RULES`). An evidence reset is a planned release
  between evidence windows only. The site is the owner's (hands-off for this repository).
- **A merged PR is not a deployed feature.** Verify it, in the change's window: the release id, the rows the change
  should write, the behaviour itself. During the unattended clock verify from the receipts and the daily pages
  (**Observing without exec**, above).
- **A deploy does not start a stopped loop**; `floor_box.py start` does.
- **The in-box updater is on, since the A1 deploy** (Oct 3; `auto_update` true in this tree's `league/config.json`; a
  missing key means off, and the releases before A1 had it off). A merge to main is a deploy: it reaches the House at
  the next release train unless a wall refuses it (**Deploy classes**, above). Merge to main only what may run on the
  House, and in the window its class allows; the updater holds every release through the session itself (12:55Z to
  20:05Z, to 21:05Z in winter), whatever the class. A merge that changes a protected file in the release trees deploys
  nothing and holds every later head until the owner deploys main's head. A merge that changes only `gateway/` or docs
  is no release and holds nothing: the gateway ships by wrangler alone, so a House change that needs a gateway change is
  merged only after that gateway change is deployed (**The protected paths**, above).
- **Since the A1 deploy ratification is the House's job**: a deploy that moves the money digest leaves the grant
  inactive until it is ratified, and the `grant` job (at each start and hourly) does it after an owner release that
  moved the digest and after a deposit (**The standing grant**, above). Read its receipt after any money-rule deploy;
  `live_trading.py --ratify` stays the way when it refuses, and the only way on a release before A1.
- Run `date -u` before writing any time; take event times from the box.
- Never chain a deploy on another command's exit code (a grep, a filter): run the tests, read the
  result, then deploy.
- **The money path (D8, amended Sept 29).** A research-side release may deploy in the session only when it touches
  none of the money path. The money path is:
  - `league/live`;
  - the gateway;
  - `league/constitution.py`;
  - every module the live path loads.

  An import trace of Release A's tree (Sept 30) finds these loaded, and a static trace of Release B's tree finds the
  same plus one:
  - **at module level:** `league/gym/{__init__,ctx,day,engine,events,fills,greeks,legs,runtime,safety,venue}.py` and
    `league/{safety,stats,structure_core}.py`;
  - **lazily:**
    - `league/gym/{driver,experiment,review_contract}.py`;
    - `league/constitution.py`;
    - `league/swarm/{__init__,store,bands,gate,evaluator,settings}.py`;
    - through `gate`, `league/swarm/{evidence,pool,researcher,claude_research,diagnostics,inputs,public}.py`;
    - from Release B, through `researcher`, `league/swarm/library.py` (#447);
    - from release B', through `researcher`, `league/swarm/{cards,mechanism}.py` (an import trace of the H2 tree,
      Oct 2: `architect.py` is not loaded).

  `league/swarm/{funding,models,loop,guard,practice,tournament}.py` are not loaded. Re-derive the list with an import trace of
  `league/live/*.py` on each release's tree. Any change under `league/gym/` or `league/live/`, to `LEAGUE_FILES`, to the
  fill model or to the Gym image also moves the evaluator's fingerprint: it is an evidence reset (below).
- **A workflow change re-pins the updater in the same commit.** A change to `.github/workflows/` needs
  `TRUSTED_WORKFLOWS_SHA256` in `league/updater.py` re-pinned in the same commit (a test checks it). With the in-box
  updater on (from A1), the running release refuses main heads that carry the new workflows until an owner deploy
  carries the new pin: every later head waits behind it. CI's `tests` job has a 75-minute limit (release E4: its
  league step is about 43 minutes on GitHub's runner, and the 35-minute limit of Release A cut off both jobs of #544;
  it was 20 before Release A).
  The hourly run has its own concurrency group, so it never cancels a push run. `league/updater.py` reads a cancelled
  run as no verdict, so a cancelled run is not green.

### Evaluator adoption and `gym-engine-4`

Engine 4 binds parameter overrides to module `PARAMS` at its declaration, before aliases and helper
defaults capture values; `ctx.params` starts with the same values. Each independent run still executes
the module in a fresh namespace. Persistent module state within one run is permitted. This changes
execution semantics for old programs that read global `PARAMS` with nondefault overrides, so prior
results cannot qualify them under the new runtime.

At swarm startup, before any research or tournament worker, `research_evaluator` records the current
data image, full Gym bundle and execution fingerprint. An identity change archives and clears derived
Train bests, candidates, submissions, stress/drift views, validation and review. Runs, versions, lineage
trial counts, refusals, notebooks and consumed holdout looks remain. Late old-evaluator results are
still counted but cannot refill current selection or forward evidence. Full result pruning retains
each worker's actual image and bundle in its run summary. The replay key and standalone engine hash
also change, so the old cache cannot supply a new result.
If two different evaluator identities return the same standalone worker run ID, the store keeps
separate result rows and files; it never relabels old metrics as new evidence.

An old contract's pre-holdout refusal is archived and its active veto cleared, allowing a fresh review
only after new-evaluator qualification. The refusal record stays; an actually consumed look remains
in `looks` and cannot be reopened for that same program hash.

Candidate, Probe and Sized entry authority additionally pins the program hash and the executable
Gym/live/shared-source fingerprint in `banded_evaluator`. An old/missing fingerprint denies new opens
and band confirmation; startup returns that family to Gym so researchers can requalify it. Frozen
live instances and their positions keep their exit/reconciliation path, and historical band/forward
records remain. A docs-only bundle change does not erase a band whose executable fingerprint still
matches. A runtime, fill or context change does, even if an engine-version bump was missed. A new
qualification still needs all existing Train, validation, independent review and holdout requirements;
an identical code+parameter hash cannot acquire another sealed look because the evaluator changed.

New practice cohorts require a current-image/current-bundle eligible Train or completed Validation
replay; an old `best_train_version` or `validation_version` label alone is insufficient. A zero-trade or
failed validation line remains information, not an automatic experiment-contract failure. Existing
immutable cohorts separately pin their bundle, fill-model label and executable fingerprint: a changed evaluator makes them close-only, with
forced wind-down outcomes excluded from strategy feedback. Their `(family, version)` identity cannot
be reused for a new evaluator; re-entry requires a newly eligible source version.

Adoption needs a new code release, not a new data checkpoint solely for this parameter fix: GymDriver
uploads the content-addressed engine bundle to sealed workers, and results identify both bundle and
data image. Verify the deployed `research_evaluator`, adoption events, unchanged total trials/looks,
worker `gym_bundle`, real entry proof and practice evaluator before treating new observations as
current evidence. Evaluator adoption is not a strategy promotion or a claim of profitability.

**Evidence resets are planned releases** (Sept 30, 2026).
- A change to any of the following re-adopts the evaluator:
  - anything under `league/gym/` or `league/live/`;
  - `LEAGUE_FILES` (`league/{__init__,safety,structure_core,stats}.py`);
  - the fill model;
  - the Gym image.
- The release before Release A had no evaluator record, so Release A's first start adopted one for every alive family.
  That was reset 1 (20:06Z Sept 30).
- Release B, the incubator, was reset 2 (03:49Z Oct 1). It changed `league/live` only, not `league/gym` or
  `LEAGUE_FILES`, so the execution fingerprint moved while the Gym bundle and image stayed Release A's:
  - selection is archived and cleared again, as at reset 1;
  - extension holds and the operator's clears stand, since only a new Gym image or bundle clears them (#453,
    `evaluator.gym_changed`);
  - a validation recorded on the same image and bundle may be judged again;
  - every practice cohort from Release A completes ("evaluator changed; a new version needs fresh practice"), because
    the practice evaluator is the bundle, the fill model and the fingerprint together.

  After an adoption, the idle count restarts from `evaluator_trials`, and an idle retirement says "since the evaluator
  changed" (#453).
- V3-A part 1 was reset 3, at its deploy (08:50Z Oct 3: 13 adoption events, one per alive family). Like B it changes
  `league/live` only (`step.py`, `shadow.py`: the exit-only drop, the store clamp, the practice caps, the honest shed),
  so the fingerprint moved (`47587e22…` → `ba60c473…`) while the Gym bundle and image stay, with the same consequences
  as reset 2: every practice cohort completed (nine), and a (family, version) that had a cohort does not practise
  again, so practice refills only from new versions (**Now**, "Evidence reset 3"). The next planned reset comes with
  the forward ladder and the credit types (`v3/wp6`, `v3/wp7`), batched into one owner deploy when they ship.
- Since B, those paths are frozen for at least five sessions, and for as long as any family holds Candidate, Probe or
  Sized or has an incubator-bound cohort. A change to them ends every practice cohort and every incubation. The only
  exceptions are rollbacks and fixes for bugs that block or endanger real orders.
- Other changes to those paths are batched into planned releases between evidence windows: harness-lane changes, the
  fill-model refit and new images.
- The run record logs every reset. Never compare evidence across fingerprints.

## Pause, resume, stop

```sh
python3 scripts/floor_box.py maintenance on --reason "why"   # pause: paid work and new entries stop
python3 scripts/floor_box.py maintenance status
python3 scripts/floor_box.py maintenance off                 # resume on the next tick
```

`maintenance on` writes `/workspace/state/PAUSE` with the reason; the House keeps ticking.

- **What stops:** paid model work, replays, births, promotions and every new entry.
- **What goes on:** reconciliation, marks and publishing; agents holding a position are still
  woken, and their exits and cancels reach the books; work in flight defers at its next paid turn.
- **The swarm and the Gym under a pause:** a paused House starts no swarm process (and no nightly
  job), but a swarm already running goes on, and the Gym trains through a pause. To stop the swarm,
  write `/workspace/state/swarm.stop`; the House starts it again once the file is gone and the House
  is not paused.
- **The House's jobs and the updater under a pause** (from A1): `preopen`, `clock`, `economics` and `budget` run (and,
  from the self-running release, `stall`, which reports a pause left on 6 hours as an owner step);
  `grant`, `hygiene`, `scoreboard`, `drills` and the paid jobs get a `skipped` receipt naming the pause, and the next
  occurrence after it runs. The updater is not paused: it still deploys main's head inside its walls.

`python3 scripts/floor_box.py stop --reason "why"` writes both stop files (`/workspace/STOP`, the
supervisor's, and `/workspace/state/STOP`, the House's), sends TERM, waits up to 120 s for the tick
in hand, then stops the supervisor. It ends every exit with the loop: prefer `maintenance on`.
`start` clears both files and starts the supervisor, which runs the House from
`/workspace/current` and restarts it 30 s after it exits.

Neither command touches real money. To stop real orders at once, whatever the House does:
`python3 scripts/gateway_admin.py kill` (below, **Real money**).

## Deploy

**The House.** In `~/Work/ltcm-deploy`, check out the exact commit to ship (detached, `git status`
clean: `deploy` sends the working tree), then:

```sh
python3 scripts/floor_box.py deploy              # wait for the verdict (up to 1500 s)
python3 scripts/floor_box.py deploy --no-wait    # launch and return; `status` has the verdict
```

The release is the whole tree (`league/`, `ltcm/`, `scripts/`, `deploy/`, `playbooks/`; never
`docs/`, `archive/` or `.data/`), named `YYYYMMDDTHHMMSSZ-<12 hex of its sha256>`. The in-box
watchdog (`league/watchdog.py`) then:

1. **stages** it as `/workspace/releases/<id>/`;
2. runs a **canary**: 3 ticks of a whole House on throwaway state with a simulated paper venue, no
   publishing, no research and no real money. An error, a traceback, a timeout or bad health
   refuses the release and leaves `current` alone;
3. **promotes** it (`previous` := old `current`, `current` := the release) and restarts the House;
4. **watches** `health.json` every 30 s for 10 minutes and, after a grace of two readings, rolls back
   on the first bad one: a stale `health.json`, a tick that raised, a frozen book, a health failure
   or an unmarked error alert.

A condition that began before the promotion is inherited, reported and never a rollback. **A
vendor's outage never rolls a release back**: an error the House raised because Sail, the site, the
gateway or GitHub failed on its side carries `environment: "<service>"` and is only counted
(`detail.environment_alerts` in the watch rows). Nothing on the trading path is ever marked.

**A canary is a fresh House.** Its state is new, so it has told nothing yet: every once-only notice whose condition
holds is told again on the canary's first tick, and one unmarked error there refuses the release, whatever the release
changes. So a notice that depends on the calendar (a date passed, a run's scheduled end) must never be an error. Once
its date passes every canary raises it, and no release can land: not the fix's own, not an updater release, not the
rollback drill. That happened from 00:00Z Oct 3, 2026, when the old League's fourteen-day expedition ended and its
notice was an error, until commit `0c8e8107` made the calendar ending the run a warning (**Now**, "The canary blocker
the rehearsal found"). An error is for a failure of the House or of the release; a scheduled end is a warning.

`deploy` exits 0 for promoted, 2 refused, 3 rolled back, 4 failed with nothing to roll back to, 1 no
verdict seen. Only one deploy runs at a time: `REFUSED: another deploy or rollback is running (pid
N)` means wait for that watchdog (`status`) and deploy again. With the loop stopped there is no House
to watch, so the watchdog canaries and promotes only; then `start`.

**Every owner release: the release checklist** (as run Oct 1-3; A1's own order and record are in **Now**). The steps
every owner release since Release B followed, in order. From A1 an updater release does steps 2, 4, 6 and 7 by itself:
it stops the nightly daemon with its own marker, deploys through the same watchdog, lifts its marker after the
verdict, and the harness observer follows its attested commit. Its record is `deploys.jsonl` (in the receipts file)
and the daily page; its CHANGELOG entry is written when the record is next brought up to date.
1. **The tree.** Merge first: an owner deploy ships main's head and nothing else. A clean detached checkout of that
   commit in `~/Work/ltcm-deploy` (`git status` empty: `deploy` sends the working tree), with CI green on that exact
   commit (the `gateway`, `tests (3.11)` and `tests (3.14)` jobs). Classify it: money path (a module the live path
   loads, the gateway or the constitution), research-class, or an evidence reset (**Rules that hold every day**,
   above); that sets its window. Read `floor_box.py status`: note `current` and `previous`, because `previous` is where
   a rollback would go. Check that the tree adds no notice at error level whose condition is the calendar: a canary is
   a fresh House and would raise it at every release after that date ("A canary is a fresh House", above).
2. **Stop the nightly forward daemon while it is idle**, so a release change never lands mid-job. On the box:
   `touch /workspace/state/data/nightly.stop` (or write `operator:<why>` into it: the stall alarm names it), then wait
   until `/workspace/state/data/nightly.lock` is free. While this stop is under 2 hours old the `stall` job reads it as
   the owner's deploy in flight and mails no "owner deploy waiting"; at 2 hours it is the `forward` cause. The House's
   step stops the daemon while the file is there (`league/data_job.py`), and a wake that falls in the stop is skipped.
3. **A read-only lineage snapshot** of `swarm.sqlite`: trials, inherited trials and looks by lineage, and the run count.
4. **Deploy:** `python3 scripts/floor_box.py deploy` (it refuses while another deploy is in flight, the updater's
   included: wait for its verdict). If the release moves the money digest, ratify at once
   (`live_trading.py --ratify`); from A1 the `grant` job does it when the House starts on the release (the watchdog
   records the promotion before the restart): read its receipt, and ratify by hand if it refused.
5. **Checks after promotion:** `real_money` true; health `failures` []; `research_evaluator.execution` unchanged (unless
   the release is a planned reset); the tuition lot still exit-only; the practice cohorts intact; a second lineage
   snapshot with 0 violations against the first.
6. **Un-stop the daemon:** `rm /workspace/state/data/nightly.stop`.
7. **Re-point the harness observer:** `/workspace/state/harness/runtime.json` `base` (the deployed commit's full sha)
   and `release_digest` (`league.watchdog.tree_digest` of `/workspace/current`). An owner deploy carries no
   attestation, so the observer does not follow it by itself. Measure the lanes only once the swarm's heartbeat names
   the new release: a capture taken while the swarm still runs the old one binds the wrong base.
8. **Criterion 1 on the new release:** with no calibration order working and outside the House test's window,
   `floor_box.py stop`, then `start`; then kill the swarm process. Both must recover (every instance restored, the swarm
   back within a minute). Outside the session the live path reads the account only on its quiet pass, every 15 minutes,
   so after the restart `options_live.blocked` reads "the account could not be read this minute" until the next quiet
   pass. That is expected, and it clears by itself (Oct 3: a 09:01Z restart, clear at 09:14Z).
9. **A CHANGELOG entry** for the release (the docs-only commit does not change the release tree's digest, so from A1
   the updater reads "the box already runs main": it is no release, it holds nothing and it needs no deploy).
   `CHANGELOG.md` is on the protected list for the roles and the gateway's merge route, so the entry is merged by hand.

**The first release on the new state root.** The old House's state was moved aside on Sept 26; the
new House starts on an empty `/workspace/state` with `real_money` false. Its first owner deploy
makes the watchdog's `previous` a release of the new era. **Never roll back past that release**:
the release before it (Deploy G, `20260926T032739Z-aaf5ac74637c`) would run the old Kalshi and Jev
code on the new root. [CHANGELOG.md](../CHANGELOG.md) records the release id.

**A money rule.** The grant pins `constitution.money_digest()`. Changing a money rule takes three
steps: change `league/constitution.py` and re-pin `PINNED_DIGEST` in the same commit (a test checks
it); deploy it with the owner's deploy; at `promoted`, run `python3 scripts/live_trading.py --ratify` at once (from
A1 the standing grant ratifies when the House starts on the new release: read the `grant` job's receipt, and ratify by
hand only if it refused). To see whether a tree moves the money digest:

```sh
python3 -c "from league.constitution import digest, money_digest; print(digest(), money_digest())"
```

and compare the second with the grant's `constitution_digest` (`python3 scripts/live_trading.py`
prints it). Release B moves it (`a3e2aa7c` → `42c4a3af`, the incubator's row); V3-A part 1 does not.

**The gateway.** In `gateway/`: `npm run check && npm test`, read the result, then `npx wrangler@4.129.1 deploy`. No
lockfile is tracked, so never `npm ci` (it exits 1 without one), and no install is needed: the checks and the tests
use Node alone. Wrangler is run at the pinned version (4.129.1, the one `gateway/package.json` names), because a bare
`npx wrangler` may resolve to a newer one. Record the version id the deploy prints: it is what
`npx wrangler@4.129.1 rollback <version id>` returns to. Deploy the gateway before a House release that needs its
change. From A1 that order is set by the merges: a merged gateway change holds nothing on the box, and a merge of
unprotected House code is a release at the next train, so the House change is merged only after the gateway change it
needs is merged and deployed. After a deploy, read `python3 scripts/gateway_admin.py status`. Caps and
`OPTION_STRUCTURES_REAL` change only this way. Deploy from a clean checkout of exactly `origin/main`: a deploy from a
branch drops whatever else main holds. From Release B the gateway binds a KV namespace (`LIBRARY`,
`ltcm-gateway-library`) for the research library; never delete it.

**The site.** The page is the owner's (since Oct 2: hands-off for this repository's work; keep the publisher's data
contracts stable and ask the owner before changing them). The owner deploys it in `~/Work/personal-site`: `npm test`,
then `npm run build && npx wrangler deploy` (its `DEPLOYMENT.md` has the details). When the publisher's schema or a
bound changes, the site deploys first: it refuses a whole checkpoint for one field it does not allow. The one exception
is the positions table (`positions`, Sept 28, 2026): refused, the publisher posts the checkpoint again without it and
offers it again half an hour later (a warning per distinct reply of the site, "positions table: the site refused the
positions table (old site, or a row it rejects) ... (the site said: ...)"), so either may go first. The first release of
the table went site first (#15, 16:59Z Sept 28), then the House (R6, 20:08Z). The practice league's block (`practice`,
Sept 29, 2026) and Claude's own compute part (`compute.claude_usd`, Release A, #441) are the second exception, handled
together.
- **The order it tries:** a site that refuses the checkpoint is sent each older shape alone, then both:
  1. without the positions table;
  2. without the practice block and with the five-part bill (Claude folded into `other_usd`,
     `publish.legacy_compute`);
  3. both at once.
- **What gets marked:** only the part the site then took is marked refused, and it is offered again after 30 minutes.
- **The warning,** one per distinct reply: "the site refused the practice league block or Claude's own compute part
  (old site, or a row it rejects) ... (the site said: ...)".
- **The site that takes both:** personal-site PR #17 (`capital/cost-net-practice`). It also adds the Net line, costs by
  service and the Incubator label. Its Worker serves the new shapes only to the page's own read
  (`?progress=1&positions=1&practice=1`), so either repository may deploy first. Site first is preferred: the page
  then shows Net as a dash until the House sends `claude_usd`. The site must be live before the incubator is switched
  on.

The swarm window (`levels` and `rationale`, Oct 1, 2026: each agent's level and the levels funnel, each agent's thesis,
and why each real position opened and closed) is the third exception.
- **The order it tries:** a site that refuses a checkpoint carrying the window is sent it again without the window first
  (`publish.windowless`). Refused again, the ladder above goes on without the window.
- **What gets marked:** the window, only when the windowless checkpoint was taken; it is offered again after 30 minutes,
  and the House does not read it meanwhile. A site that refuses the table too is told the window's refusal on the next
  publish.
- **The byte limit:** the window leaves first (its theses, then all of it), before any agent or row, and the body is
  fitted 32 KiB under the site's 512 KiB so the names the site's public read adds (a 40-character name on each of
  at most 508 rows) never push it over.
- **The warning,** one per distinct reply: "the site refused the swarm window (levels and rationale: old site, or an
  entry it rejects) ... (the site said: ...)".
- **The site that takes it:** personal-site branch `capital/swarm-window`. Its Worker serves the window only to
  `?progress=1&positions=1&practice=1&window=1`; every older read gets exactly the keys it validated. Site first is
  preferred; either order works.

**Checkpoint the House box before risky work:** `python3 scripts/floor_box.py checkpoint --name why
--ttl-days 30` (`checkpoints` lists them). A checkpoint holds the box's `.env`. Sail's checkpoint
API failed twice on Sept 26 (06:35Z and 07:00Z, HTTP 503); the old state's archive is a tarball
instead.

## Release A: after promotion (Sept 30, 2026; done 20:16-20:50Z)

Done: the results are in [CHANGELOG.md](../CHANGELOG.md), Sept 30. The steps stay here as the reference for the next
adoption.

**The deploy.** Release A deploys like any House release (above): at 20:05Z or later, from a clean detached checkout of
its main commit.
- **Before:** check that no calibration position or working order is open, `deploys.jsonl` is idle and the latest backup
  is under 30 hours old. Note any House live test position.
- **The verdict:** `deploy` exiting 0 means promoted. On any other exit, stop and read `status`.
- **Right after promotion:** `real_money` true, the money digest `a3e2aa7c`, and the House live test's instance real
  with `observe false`.

**Right after promotion, before the next architect pass** (900 s on the box), on the box:

1. **The graveyard verdict migration** (R11-1, once). Run the dry run, read the counts by verdict, then apply:
   ```sh
   /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state
   /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state --apply
   ```
   The backup and `--rollback` are described under **R11b**, below.
2. **The R11b setting.** In `swarm.json` (keep a before-copy), set `claude.role_effort` to `{"architect": "medium"}`.
   It changes nothing while the architect's Claude line is $0 (Sept 30), and holds if that line is restored. The Gym's
   zero-trade probe stays off: leave `researcher.probe_year` unset.
3. **The extension hold seed: skip it after an adoption.** Adoption clears `validation_version` first, so the seed list
   (`scripts/extension_hold.py --state /workspace/state --seed`, a dry run) is empty by design. It was skipped at
   Release A. Families are held when a validation under the new evaluator meets the checks.
4. **The input capability card** (#432).
   - Check that the private Train audit's `image_checkpoint` equals `swarm.json` `gym.image_checkpoint`.
   - Upload it as `/workspace/state/input-capabilities.json.tmp`, set mode 600, then `mv` it over
     `/workspace/state/input-capabilities.json`, so the replacement is atomic.
   - Its schema is under **Input capability card**, below. The card never enters the repository.
5. **The data side.**
   - `pgrep -af window.py`. If the history window controller's loop (#413, `scripts/data/window.py ... loop --every
     60`) is gone, start it again detached. Only one runs at a time.
   - Set up `sip-progress.sqlite` and the legacy readiness rescan, as
     [data-sip-completion.md](data-sip-completion.md) describes (#433).
6. **Operator revivals** (optional). A near-miss family that the dormancy clause retired may be revived as a lineage
   continuation (origin `operator-revive`, **The graveyard**, below).
   - It inherits its lineage's trials and holdout looks.
   - Its re-validation under engine 4 is a new, counted trial, and the holdout still judges it.
   - Run a dry run first. The revived family is held once its re-validation meets the checks.
   - Record in the run record which families were revived, and that the operator chose them from the validation line.
   - **The harness runs the revived program exactly** (Oct 1, `researcher.py` THE OPERATOR'S RUN). Take a living Gym
     family's latest version written by the operator (author `operator-revive`). If it has no Train run at the normal
     spread on the current evaluator (image and bundle) and Train span that is the program's answer, the harness runs it
     at the start of the family's next cycle, before any rewrite, queued run or model turn. An answer is a run of status
     ok, disqualified, no_data or refused. A run of status `error` is not one: the Gym could not finish it (a dead
     worker, or a unit killed, perhaps for another program in its batch), with no trial and no figures.
     - It runs with the version's stored code and params, through `gym_run`'s own path: the same refusals, no-duplicate
       rule, lineage trial, Train score, drift screen, best and robustness runs. It is never probed. It is recorded as
       that version (no version row, no revision).
     - Any new evaluation of it, ok or not, is the cycle's one run. A rewrite and a run queued last cycle wait for the
       next cycle, and the model reads the result. A run call the model makes in that cycle replaces the queued run.
     - A Gym error, a run the Gym could not finish, or a failure of the attempt itself ends the cycle with no model call.
       The harness tries again next cycle, at most 3 times. When a wait gave up while the Gym was still running the job,
       the harness does not submit it again. It waits up to one more run timeout (`late_until`) and reads the result
       back from the store when it lands, with no second job and no second trial. That holds even after it gave up.
     - A refusal, or the third failure, gives up with a notebook note. The note and the status say how the researcher
       can run the version itself. A gate-mode mechanism test that did not pass is the version's answer.
     - The family state's `operator_run` keeps the record per version, evaluator and Train span, so a later adoption
       owes one more run. The harness's own stored result or refusal never counts toward the dormancy clause.
     - The status tells the researcher that its revival runs unchanged first, that its evidence decides, and that an
       evaluator change is never a reason to retire.
   - **Before this fix, revivals did not run the revived program.** Between Sept 30 and the fix, the harness never ran a
     revival's version 1. A `gym_run` with no code reran the latest code with params `{}`, which dropped the revived
     params; unless they equalled the program's `PARAMS` defaults, a different program ran. Researchers also often wrote
     new code at once. A revival's Train, 1.5x and drift evidence on the evaluator in force therefore mostly never
     landed. Check any run-record claim from that window that a revival "re-validated with identical numbers" by
     evaluation, not by version number. Compare the run's code sha and merged params (its `eval_key`) with version 1's:
     the revived program is that code with version 1's params merged over the `PARAMS` defaults, whichever version row
     the run is under. On the first deploy with the fix, each living revived family whose version 1 has no such run gets
     it in its next cycle. The deploy is a new release, so it also wakes a parked family.
   - `gym_run` with neither `code` nor `params` now reruns the latest version exactly: its params carry over. Explicit
     params, `{}` included, still replace them.

**Checks after promotion.** Record each one in the run record.
- **Evaluator adoption.**
  - `research_evaluator` is set, and each alive family has an `evaluator_adopted` event.
  - Lineage trial counts and consumed holdout looks match a snapshot taken before the deploy.
  - Workers report the new `gym_bundle`, and the practice evaluator is bound to the new fingerprint.
  - The paper route proofs still read passed.
- **The live guards** (#437).
  - `options_live.instances["house:rebound-live@0:h"]` is `kind` real with `observe` false.
  - Every `:o` instance has `observe` true.
  - There is no "is not a real instance" alert.
- **The decider** (#443).
  - `live-decider.log` and `live-decider-observe.log` show no traceback.
  - There is no "requires a network namespace" error.
  - The child's `/proc/<pid>/limits` shows a 64 MB file size and 0 processes.
- **Research.**
  - Retirements happen at `population.floor` and `researcher.retire_min_trials`.
  - After one tournament round (3,600 s), no family without a positive validation mean holds exploit weight.
  - Sampled reviews and audits cite the runtime contract, the evidence or a counterexample.
  - Holding families stay on the same cycle count until new evidence wakes them.
- **Funding** (#439).
  - A few `swarm: funding: ...` warnings are expected in the first minutes.
  - The heartbeat has `status.funding`.
  - Architect calls show up as `claude_fallback` events (kind `line`, route Sail) while its Claude line is $0.
- **The practice league:** the checks in [CHANGELOG.md](../CHANGELOG.md). Right after the reset it is expected to be
  nearly empty.
- **A deliberate restart**, at a quiet moment with no calibration order working and outside the House test's window.
  Run `floor_box.py stop`, then `start`. Then verify:
  - the House test instance comes back real with `observe false`;
  - cohorts, waits and any open position survive;
  - health is clean.
- **The harness observer** (optional, #432). Write `/workspace/state/harness/runtime.json`, mode 600, with:
  - `enabled` true;
  - `schema` 1;
  - `mode` "observe";
  - `base`: the deployed commit's full SHA;
  - `release_digest`: `league.watchdog.tree_digest` of `/workspace/current`.

  [playbooks/harness-improvement.md](../playbooks/harness-improvement.md) has the details. Then check that the House's
  swarm step reports it running, under `harness`.
- **Watch for an hour:** cycle latency, House CPU, `observe_reads_skipped`, `shed` and `restarts_24h`.
  - If the House starves, first lower `live.observe_roots_max` or `live.observe_read_calls`, or set
    `live.observe_train` false. These switch things off, which is allowed in session.
  - Roll back only if that fails, and never past the House test's start release while it holds anything.
- **Then:** apply the Gym settings planned for after Release A: `gym.max_boxes` 6 and `architect.max_refill` 12
  (CHANGELOG, Sept 30; applied that night).

## Release B: deploy, ratify, switch on (Oct 1, 2026; done 03:48-04:01Z)

Done: the results are in [CHANGELOG.md](../CHANGELOG.md), Oct 1. Steps 1-7, 9 and 10 ran in order (the ratify after the
watch's PROMOTED verdict). Step 8, the library, waits: `research.enabled` stays false until the order route's p99 is
measured with the library under load. The steps stay here as the reference for the next money-path release.

Release B (PR #454) is the incubator (B1 and B2), L1 and its restart fix, L2', the research library, the adoption fixes,
information-value allocation and the preflight. It moved the money digest (`a3e2aa7c` → `42c4a3af`) and was evidence
reset 2. It deployed outside the session, before 13:25Z Oct 1, and never 19:30-20:00Z.

**The order.** Nothing here may be reordered.
1. **Merge #454 to main** once CI is green. On the merge commit,
   `python3 -c "from league.constitution import digest, money_digest; print(digest(), money_digest())"` prints
   `595228a6…` and `42c4a3af…`.
2. **Before anything:** no calibration position or working order is open; `deploys.jsonl` is idle; the latest backup is
   under 30 hours old. Note the House live test's position, if any, and every open tuition position (one at Sept 30's
   close). Take a read-only lineage snapshot of `swarm.sqlite` (trials, inherited trials and looks by lineage, and the
   run count).
3. **The gateway first.** It carries the library's code and its KV binding. From a clean checkout of exactly the merge
   commit, in `gateway/`: `npm run check && npm test`, read the result, then `npx wrangler deploy` (as run then; today
   the pinned `npx wrangler@4.129.1 deploy`). Then:
   - `python3 scripts/gateway_admin.py status`: the kill switch unchanged, the caps and `OPTION_STRUCTURES_REAL` as
     before;
   - `GET /v1/research/health` answers a `library` block with `cap` 600;
   - a search twice (`X-LTCM-Library: miss`, then `hit`: the KV cache is bound), and one read of a result's id.

   The House keeps `research.enabled` false throughout, so nothing on the House calls the library yet.
4. **The House:** `python3 scripts/floor_box.py deploy` from the same checkout.
5. **Ratify at once**, as soon as `floor_box.py status` shows `current` = the new release (the promote comes about a
   minute into the deploy; the ten-minute watch follows it): `python3 scripts/live_trading.py --ratify`.
   - It runs on the box against `/workspace/current`, so it pins the digest of the release that is running.
   - It prints the grant: `active` true, `policy.constitution_digest` `42c4a3af…`, and one more ratification.
   - Capital is read afresh: the lower of equity and the ceiling. It follows equity down as well as up, so expect it
     below Sept 28's $1,473.11.
   - Until the ratify, every real entry is refused (the House live test, the calibration, tuition). Exits go on.
   - If the watch then rolls the release back, ratify again at once on the restored release (`a3e2aa7c`).
6. **Checks after promotion.** Record each in the run record.
   - **The adoption (reset 2).** `research_evaluator`'s `execution` has changed, while its `bundle` and `image` have
     not. Every alive family has an `evaluator_adopted` event. A second lineage snapshot shows the same trials,
     inherited trials and looks by lineage, and no fewer runs.
   - **The practice league.** Release A's cohorts in `observe.sqlite` are `complete`, with the reason "evaluator
     changed; a new version needs fresh practice". New cohorts can start at the Oct 1 open, from eligible versions not
     practised before.
   - **The instances** (`health.json` `options_live.instances`):
     - `house:rebound-live@0:h` is real, `observe` false, mode live, with no error;
     - the tuition instance is `exit_only`, tuition, with no error, and its position is open in `live.sqlite`;
     - no `:i` instance exists.
   - **The incubator's block** (`options_live.incubator`): the table as committed (50, 1, 4, 150, 3, 10, 0.80); 0
     verdicts; a zero tally; no weekly stop. `python3 -m league.live --root /workspace/state --incubator` (on the box,
     read-only) says the same, and `switch` `on` false.
   - **Guards:** no "not a real tuition incubator instance" alert and no `:i` id in the swarm's `forward`; `real_money`
     true; `failures` empty.
7. **Switch the incubator on**, outside a session, once the checks pass. The site already labels its rows (personal-site
   #17). In `swarm.json`, set `live.incubator` to JSON `true`, keeping a before-copy. Check it with `--incubator`:
   `switch.on` true.
   - Nothing can be pinned before a first look passes (Oct 6 at the earliest). So switching on early costs nothing.
   - `health.json` `options_live.incubator.switch` shows the last minute's read of `swarm.json`. Outside the session
     the switches are read only at a families pass (every 5 minutes), so between passes it can read false.
     `--incubator` reads the file itself.
8. **The library on:** set `research.enabled` to true in `swarm.json` (**The research library**, below).
9. **Criterion 1 again, under B:** a deliberate restart (`floor_box.py stop`, then `start`, with no calibration order
   working and outside the House test's window), then an induced swarm crash. Verify what Release A's tests verified
   (CHANGELOG, Sept 30). Evidence counts only under the running release.
10. **Close-out:** record releases A and B as order-path deviations in the House live test's private addendum; update
    the run record and the CHANGELOG entry with the times and figures.


## Roll back

```sh
python3 scripts/floor_box.py rollback --reason "why"
```

It asks the in-box watchdog after the guards below. The watchdog moves `current` to `previous`, removes the `previous`
link and restarts the House (`league/watchdog.py` `Releases.rollback`); it runs from the previous release's own code.
Only when `floor_box.py` cannot reach the box, on the box and with no guard:

```sh
cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace --reason "why"
```

- **It restores code only.** The state on the box is not rolled back: the stores, `swarm.json`, the grant and every
  file a newer release wrote stay as they are.
- **It goes wherever `previous` points.** Read `floor_box.py status` first, and run it only when `previous` is the
  release you mean to return to and no deploy is in flight. `previous` is the release that was current before the last
  promotion, which is not always the one you have in mind: an earlier rollback clears it, and a deploy in between
  moves it.
- **There is no second step back.** After a rollback `previous` is empty and another `rollback` is refused. The way
  further back is a deploy of that tree. After a deploy that was refused (exit 2) nothing needs undoing; after exit 3
  the watch has already rolled back.
- **Never past the first release of the new era** (above).
- **After a rollback across a money-digest change**, re-ratify at once on the restored release:
  `python3 scripts/live_trading.py --ratify`. Until then real entries are refused.
- **Structures.** `rollback` and `deploy` refuse a target release that cannot hold structures while
  the practice account's ledger shows a structure held or an order open, or cannot be read.
  `--force-structures-risk` overrides it; use it only when the venue itself shows the account flat
  of option legs. Never roll back to a release that cannot close a structure the real account holds
  in one multi-leg order: close it first, or roll forward.
- **The real book** (the sprint, Sept 26, 2026). `rollback` refuses while the box's `live.sqlite` shows a
  real position held or a real order working and the previous release has `real_money` false (it builds no
  real account: the positions would sit unmanaged) or lacks the long-single code (it cannot close a long
  call or put; a same-day long call could be exercised into 100 shares the account cannot carry).
  `--force-real-risk` overrides it. **Close the real positions, or roll forward, before a rollback.**
- **`long_single` (#425).** Once any `long_single` family exists, alive or retired, a release before #425
  fails every architect pass (its coverage has no `long_single` row: a caught KeyError, so no family is
  born) and refuses forks of it. Roll forward, or hotfix, rather than roll back past #425.
- **Across Release B** (the incubator). Switch `live.incubator` off first and wait until no `:i` position is held or
  working: Release A does not know the route, and would restore an `:i` instance, send it to exits only and count its
  rows as tuition. Then roll back and ratify again at once on `a3e2aa7c`. In an emergency with `:i` positions held: the
  kill switch first, close them at the venue, then roll back. Roll the gateway back
  (`npx wrangler@4.129.1 rollback <version>`) only if the gateway itself is at fault: Release A never calls the library.
  A rollback moves the execution fingerprint back, so the swarm adopts Release A's evaluator again at its start: one
  more evidence reset, to be logged in the run record like the planned ones.
- **Across `20261002T112610Z-e11710692569`** (#484, the look holds). A release before it reads `gate_outcome` "held" as
  no verdict (`bands.BAD_OUTCOMES` lacks it), so a held version whose review and audit passed would regain its 1-lot
  execution tuition (its incubator bar stays: bars are kept). Before such a rollback read
  `SELECT family, version, stage FROM look_holds` on the box; with any row, roll forward instead or take it to the
  owner. Setting `gate.look_holds` null stops new holds and never reopens a held version.
- **Across V3-A part 1.** The release before it has no `policy.json`, no budget, no jobs and `auto_update` false, and
  reads the research settings from `swarm.json` alone.
  - As deployed on Oct 3: `current` is `20261003T084912Z-be16b05904ff` and `previous` is
    `20261002T112610Z-e11710692569`. Roll back only while `floor_box.py status` shows both. A rollback to that release
    was rehearsed on Oct 3 from a release of main, not from A1 itself. The gateway's way back is
    `npx wrangler@4.129.1 rollback` to `4471596a`, rehearsed the same morning from `e95a2d4a`.
  - Roll back only with the FULL `swarm.json` on the box. It stays there while `previous` is a pre-V3-A release; if the
    reduced one was installed, restore the kept copy first. Without it the swarm runs on the old defaults (OpenAI
    routes on, the old Claude lines, no budget).
  - Before it, read `health.json` `ops.running` and roll back when no job runs: the older release neither settles nor
    ends a job's child. After it, check that no `league.ops` process is left and that `nightly.stop` is absent (the
    older release does not lift an `updater:` stop), and re-point the harness observer to the restored release
    (the checklist's step 7).
  - The rollback moves the execution fingerprint back (`ba60c473…` → `47587e22…`): one more evidence reset, to be
    logged. The cohorts that A1's start completed stay completed.
  - The money digest is the same on both sides, so the grant needs nothing.
  - A1's files (`ops.sqlite`, `receipts/`, `budget.json`) stay on disk unread. A second A1 deploy on the same state
    takes up the runner's first install: job occurrences still inside their grace run, and older ones are recorded
    `missed` with one warning. If a `drills` occurrence is inside its 6-hour grace, switch `drills` off in `ops.json`
    first.
  - Roll the gateway back only if the gateway itself is at fault: the old House never calls its new routes.
- **The updater's own releases** (from A1). A release the updater deployed and the watch rolled back is tried again
  once, at the next train; rolled back twice, that head is never tried again, and a new commit on main is the way
  forward. The updater runs through a maintenance pause. To hold it: merge nothing to main (it deploys only main's
  head), or stop the loop (`floor_box.py stop`), or turn `auto_update` off by an owner deploy.
- **The gateway:** `npx wrangler@4.129.1 rollback <version id>` in `gateway/` (the id the earlier deploy printed).
  **The site:** the owner's, in `~/Work/personal-site`. Never delete the gateway's KV namespace `ltcm-gateway-library`
  (Release B): a rollback to a version that binds it needs it.

## Inspect

- **`python3 scripts/floor_box.py status [--json]`:** the box, its spend and rate, whether the egress
  allowlist matches the record, the supervisor and the House, both stop files, `current` and
  `previous`, the last line of `deploys.jsonl`, `health.json` and the log tail.
- **`python3 scripts/floor_box.py logs -n 200`** (`/workspace/league.log`); **`logs --deploy`**
  (`/workspace/deploy.log`, the last deploy).
- **On the box:** `tail -n 40 /workspace/deploys.jsonl` (every stage, reading, verdict and reason);
  `/workspace/state/health.json` (written every tick); the ledger read-only,
  `sqlite3 'file:/workspace/state/ledger.sqlite?mode=ro'`; `cd /workspace/current &&
  /workspace/.venv/bin/python -m league.watchdog status --base /workspace`.
- **The grant:** `python3 scripts/live_trading.py` (no flag) reports it and what enabling would
  record now. The standing grant's receipts are the `grant` rows of the House's jobs (below).
- **The House's jobs** (V3-A), without an exec: `python3 scripts/desk_receipts.py [YYYY-MM-DD] [--json]` (the day's
  occurrences with their receipts, a health summary, the day's deploy rows, the swarm's spend, the budget's state and
  the latest close economics' headline).
  On the box, read-only: `sqlite3 'file:/workspace/state/ops.sqlite?mode=ro' "SELECT job, due_at, status, error FROM
  runs ORDER BY due_at DESC LIMIT 30"`, `/workspace/state/budget.json`, `health.json` `ops`, and the jobs' logs in
  `/workspace/state/ops/logs/`.
- **The updater** (V3-A): its launches, refusals and holds (once per head and reason) are `ops.deploy` rows on the
  ledger, a head it could not deploy is a House warning, and its deploys are `deploys.jsonl` rows carrying the attested
  `sha`; a hold names its reason (`train`, `session`, `recent_start`, the nightly daemon) and the next eligible time.
- **The incubator** (Release B), on the box: `python3 -m league.live --root /workspace/state --incubator`, read-only.
- **The research library** (Release B): `GET /v1/research/health` on the gateway (the `library` block of `/v1/health`),
  and the swarm's private `swarm.research` events.
- **The gateway:** `python3 scripts/gateway_admin.py status`: the kill switch, today's order
  counters, the OpenAI month (spent, settled, in flight, the cap), Claude's funded meter (`claude`: the
  cap, spent, in flight, remaining, holds, the priced models, spend by role and agent), the Sail balance
  and the House box's state. Since PR #417 it also has `overruns` and `overrun_usd`: calls whose settled cost ran
  past their hold (never expected; the House pauses its Claude research band on one).
- **Claude's top band** (PR #417): a `swarm.cycle` event of a top family carries `route: "claude"` once a Claude
  turn was answered, `claude_calls`, `claude_usd`, `claude_usage` (input, cache write, cache read and output tokens
  summed over the cycle, refused and cut answers included), and when it applies `claude_fallback` (`<kind>: <why>`,
  the turn that went to Sail), `claude_skipped` (`hold_streak: ...` or `paused: ...`: the cycle stayed on Sail),
  `claude_paused` (this cycle's trouble paused the band) and `claude_overrun`. The swarm's `spend` rows (kind
  `claude`, `detail.role` "researcher") hold the holds and their settlements; `kv claude_unsettled` lists holds whose
  bill is not yet known; `kv claude_band` is the breaker (`trouble`, `paused_until`, `why`).
- **The public page:** `curl -s https://blakewoods.us/api/capital/checkpoint` (its `published_at`);
  `curl -s 'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1'` adds the positions
  table, which the default read omits; `...&practice=1&window=1` adds the practice league and the swarm window
  (`levels`: each agent's level and the funnel since the reset; `rationale`: each agent's thesis and each real
  position's route, reasons, exit and maximum loss).
- **The public cost and Net** (Release A, #441, with personal-site PR #17).
  - **`compute` is the bill since the reset, by service.**
    - `sail_usd` is what Sail billed. It is the Sail guard's balance meter (`swarm.sqlite` kv `metered_spent`, since the
      swarm began at 10:22:26Z Sept 26) plus `sitefeed.PRE_METER_SAIL_USD` ($0.46, the provider's box billing from T0
      to the meter's start). It is never the Gym's booked `gym_box` estimate, which runs about 70% above the bill. It is
      never below the swarm's booked model calls.
    - `claude_usd` is the swarm's Claude spend, settled plus in-flight holds.
    - `openai_usd` includes unresolved OpenAI holds.
    - The two data subscriptions are prorated from the reset.
    - `other_usd` holds what the owner declares; it is $0.00 until a declaration.
  - **Net** = realized options P&L since T0 minus every input cost since T0. Open gains are excluded and open losses
    included. It is a dash while any part is null or older than ten minutes.
  - **Known limits:**
    - the meter trails the provider's receipts by about $0.5, and the gap closes as late debits post;
    - if a new swarm store is ever started, the meter restarts, and `sail_usd` falls back to the booked figures (which
      overstate) until the pre-meter constant is re-derived.
- **The data:** `python3 scripts/data/box.py status` (the box, its egress, the backfill's progress);
  `python3 scripts/data/box.py run -- check.py report` (underlying-days by window and root, the
  queue, the rate); `python3 scripts/data/images.py status`; `python3 scripts/data/nightly.py status`.
  Numbers derived from the data stay on the boxes and in `.data/`.
- **The swarm and the scoreboard** (families, trials, validation passes, holdout looks, Gym
  throughput, compute against the budgets), on the box:
  - `cd /workspace/current && /workspace/.venv/bin/python -m league.swarm status --root /workspace/state`:
    the heartbeat, the totals (trials, holdout looks and passes), families by band, the live rows and the
    families held at the gate;
  - `python3 scripts/verify_swarm.py --root /workspace/state`: process, population, cycles, the Gym,
    the tournament, each PASS, FAIL or WAIT;
  - `/workspace/state/swarm.heartbeat` (JSON): families, cycles and spend in the last hour by kind, the
    guard, the pool, `status.researcher_pace`;
  - `health.json` `options_live`: the observe band, the calibration, the House live test, the stops;
  - Claude and OpenAI spend: `gateway_admin.py status` (above). `scripts/floor_watch.py` is not
    rewritten for the options scoreboard.

## The data box, the images and the Gym boxes

The data box holds the ThetaData key in `/data/secrets/thetadata.env` (0600) and nothing else
secret. Its egress is the two ThetaData hosts (PyPI only during `setup`).

```sh
python3 scripts/data/box.py status              # the box, its egress, the backfill's progress
python3 scripts/data/box.py start [--stages 1,2,3,5,6]   # the backfill in the background; resumable
python3 scripts/data/box.py stop                # stop it (it resumes from its journal)
python3 scripts/data/box.py slots N             # how many of ThetaData's four requests it may use
python3 scripts/data/box.py sleep [--wake-at ISO]
python3 scripts/data/box.py run -- ARGS         # run backfill.py ARGS (or check.py ...) on the box
```

- **ThetaData allows one session per account.** A login anywhere else kicks the box's session:
  nobody else authenticates while the backfill runs. Every file is journaled with its sha256, so a
  kicked or stopped backfill resumes where it stopped.
- **Sleep the data box, never pause it:** a paused box cannot wake on a schedule.
- **Images.** `python3 scripts/data/images.py build gym|gate [--version vN]` stops the backfill,
  checkpoints the data box, restarts the backfill, forks, seals the fork (`no_network`) before
  anything runs on it, prunes it, verifies from inside and checkpoints it twice with a one-year TTL.
  The Gym image has no key, no holdout and no forward days; the gate image has no key but has both,
  and carries the `GATE` mark. `images.py verify gym|gate` re-checks one. Either image can be rebuilt
  from the data box at any time.
- **Train's span in a Gym image.** `images.py build gym --train-from 2020-01-02` (the running image) or
  `--train-from 2017-01-03` (Train from 2017, released in R11a on Sept 29) keeps those years as Train and the underlying of
  the 60 sessions before as history; without it Train starts 2022-01-03. `--root-first ROOT=DATE,...` gives a root
  its own later first Train day (its history is then the 60 sessions before that day): a 2017 image lists every root
  fetched only from 2020 at 2020-01-02 (the 20 names, until their earlier years and split rows are adopted), and XSP
  too if its 2017-19 is thin. Pruning keeps files by date, so a partly fetched early year of a name would enter Train
  without it; a build from 2017 therefore takes `--roots` and refuses unless every name there has a `--root-first` on
  or after 2020-01-02 or is named in `--early-names` (only once its split rows are in `league/gym/events.py` and its
  years are complete). It refuses `--early-roots`. The fork prunes with the build's own data tools (pushed to it
  first; the data box may run a fetch's code). images.json records `train_from`, `root_first` and `early_names`.
  The inside check (`images.py verify`, and every build) holds each listed root to its own day, every other name to
  2020-01-02 in an image from 2017, and the image's first chain to its `train_from` exactly; `verify --root-first`
  reads the recorded `train_from`. The Gym reads a store's first Train day from its first chain (`train_first`), so
  a 2020 image's 2019 history sessions stay out of Train, and the pool refuses a Gym box whose first Train day is not
  the swarm's span, both ways. `batch --check --window train` on the running image reports its first Train day
  (2020-01-02). The swarm moves only when `gym.train_from` and `gym.image_checkpoint` change together.
- **The nightly forward job.** `python3 scripts/data/nightly.py run [--day YYYY-MM-DD] [--dry-run]`
  pulls the last trading day (from 01:45 ET) into the data box's store and the gate image only,
  stopping and restarting the backfill around it, re-checkpoints the gate and puts both boxes to
  sleep; `nightly.py schedule` sleeps the data box until the next 06:00Z wake. It is idempotent:
  rerun it after any failure. It refuses the Gym image's box as a target. On the House the supervised
  `nightly.py daemon --state <root>/data --ready-file <root>/gym-forward.json` runs it each night and publishes the
  ready file the swarm reads.
- **The source gap** (Oct 14, 2026; `scripts/data/nightly.py` and `sip.py`, THE SOURCE GAP). From 06:20Z Oct 13 the
  nightly retried 2026-10-12 every five minutes for two days: SLV's SIP bars were 389/390 (the 13:45 ET bar, completion
  minute 826, never served), the strict relay ingested none of the day's 23 stock roots, and 2026-10-13 and 14 waited
  behind it. The stall alarm told it only in its daily INFO notice, as an error text with no day and no owner step.
  - **Strict while bars may still arrive.** Each failed relay records, with the day in `images.json`
    (`gate.forward_days[day].sip_watch`), every short root's packet (`packet_sha256`), coverage, quarantine path and
    since when the source has served that packet unchanged (`first_seen`, `attempts`). A changed packet restarts the
    root's clock.
  - **Only a small gap.** A source gap is bars served with at most 5 regular-session minutes missing (receipt status
    "partial", `SOURCE_GAP_MAX_MINUTES`) on at most 2 roots of the day (`SOURCE_GAP_MAX_ROOTS`). An empty or invalid
    packet, a wider gap or more short roots is an outage whose bars may come later (a gateway answering 200 with no
    bars, or every root cut off at noon): the whole day stays strict, no hand-off is scheduled (`handoff_at` null), and
    the stall alarm's owed-day step reaches the owner at 36 h owed.
  - **The hand-off.** Within that bound, a root whose packet has stood unchanged for 6 h (`SOURCE_SETTLE`) and past the
    close of the next session, but never more than 24 h (`SOURCE_SETTLE_CAP`: a Friday's gap waits a day, not the
    weekend), goes to the forward gap ledger (`forward_days[day].sip_gaps`, durable with the day). The relay (`relay_day(...,
    source_incomplete={root: packet})`) then allows that root's gap for that exact packet only. It ingests the day's
    complete roots and leaves the short root's packet in its private `sip-partial-*` quarantine, never ingested and
    never filled. Any other gap, or a handed root whose packet changed, still fails the night.
  - **Never complete.** The day's SIP proof (`nightly.sip_proof`) has `status` "source_incomplete" and lists each short
    root with the canonical file it keeps (`file_sha256`, bound by `files_sha256` like every other root) and that
    file's source label: the vendor's option-implied underlying from the day's pull, as on every forward day before
    the SIP relay. The nightly refuses a proof that calls a short root complete or names a root the ledger does not
    hold. The ready file (schema 1) carries the proof as `sip_coverage`, and `source_incomplete` lists every root-day
    the ledger holds on the chain, with its coverage and missing minutes. Every later day's publication keeps it.
  - **Why not the historical gap queue.** `sip-progress.sqlite` is digest-pinned to the Train-Holdout plan
    (`backfill.py sip-plan` refuses other days). A forward day there would change its plan and stop the completion
    worker ("review a new queue"), so the forward ledger keeps the same rules with the day instead: per-root receipts,
    the packet quarantined, nothing filled, never complete.
  - **What to read.** `nightly.py status` lists `source_incomplete` (the ledger, by day) and `sip_watch` (the clocks).
    `nightly.json` `retrying` holds the day the controller retries, since when, the attempts, the short roots and when
    the day goes on if their packets stay unchanged (`handoff_at`; null for a gap too wide to hand off).
    `completed_at` holds the last completion.
- **The chain's rule** (Oct 1, 2026). The nightly extends the gate image that `<root>/data/images.json` names
  (`gate.current`), and the swarm uses the gate that `swarm.json` names (`gym.gate_checkpoint`). On Sept 29-30 the two
  differed: images.json still named the original five-root gate, the 25-root gate had been adopted through
  `swarm.json` alone, and the ready file's checkpoint silently replaced it. Every gate box then forked from a five-root
  holdout. These rules now keep them together:
  - **Each day names its image.** The nightly records the image it extended with each day (`forward_days[day]`
    `base_checkpoint` and `holdout_roots`, and `base` on each `gate.checkpoints` entry), and the ready file carries
    `base_checkpoint` (the image's first checkpoint) and `holdout_roots` (the roots it was built with). A day finished
    without them (by an earlier release) is completed but not published (`nightly.json` `unpublished`).
  - **The swarm takes the chain only while it extends the named gate.** `settings.load` replaces `gym.gate_checkpoint`
    with the ready file's checkpoint only when `base_checkpoint` equals it and `holdout_roots` covers `gym.roots`.
    Otherwise the swarm uses the named gate itself, with no forward days, and the loop raises one `gate_chain_ignored`
    alert per ignored file. An unreadable file never moves the gate.
  - **A legacy ready file** (no `base_checkpoint`, written before this release) stands only when images.json proves
    the same. Its current gate's first checkpoint must be the named gate, and its recorded roots must cover
    `gym.roots`. The file's checkpoint must be its day's recorded checkpoint, adopted after the image was recorded
    (`forward_days[day].adopted` not before `current.built_at`). It must also be on the image's chain
    (`settings.chain_refusal`): it and every later `gate.checkpoints` entry name the image as `base`, or (an entry
    written before this release) were taken after `built_at`. It need not be the chain's tip, because the nightly
    records a new day's checkpoint shortly before it publishes the day. Production's file at this release is such a
    file (written after the Oct 1 re-base), so the gate does not move at the deploy or at the first publish after it.
    `nightly.py --state <root>/data stamp-ready --ready-file <root>/gym-forward.json [--apply]` writes
    `base_checkpoint` and `holdout_roots` into a legacy file that stands. It needs the daemon stopped, because it
    takes `nightly.lock`. It puts the old file back unless the swarm takes the new one with the same gate.
  - **The nightly never extends a gate that lacks the swarm's roots, or a chain that is not on it.** `run` (and the
    daemon) refuses before any box is woken (`preflight`, before the data box is resumed). It refuses when images.json's
    gate does not list its roots or lacks a root of `gym.roots` (read from `<root>/swarm.json`; the daemon's root is the
    ready file's folder, `run --swarm-root` for a hand run). It also refuses when the chain's tip (`current_checkpoint`)
    is not proven on that gate (`settings.chain_refusal`): the chain records were not reset when the image was
    adopted, and a re-fork of the gate box would carry another image's holdout under this one's name. The refusal is
    the controller's `error` in `nightly.json`, retried every 300 s with no box woken. `schedule` and rehearsals are
    not refused.
  - **A day an earlier release checkpointed** (the daemon was stopped between its checkpoint and its publish) is
    published with its image's name when the chain's records prove it (`Nightly.proven_identity`), and is completed
    without a publish otherwise (`nightly.json` `unpublished`); the next day's publish names its chain.
  - **To adopt a new gate image:** build it (`images.py build gate --roots ...`, which records its roots; or a staging
    build), then point images.json's gate at it with the chain reset, as the operator's Oct 1 re-base did. The reset
    sets `current` to the image's record, `current_checkpoint` to its first checkpoint, `checkpoints` to [] and
    `forward_days` to the `pulled` markers only, and sets `nightly.json` `completed` to {}. Then name the same
    checkpoint in `swarm.json`. Until the nightly publishes on the new chain, the swarm uses the new image itself.
    `images.py build` and `finish` do not reset the chain records; until they are reset, the nightly refuses to run.
- **Gym boxes** are forks of the Gym image checkpoint, sealed, driven through Sail's file and exec
  APIs (`league/gym/driver.py`, `python -m league.gym.batch` on the box). The swarm's pool starts
  `gym.start_boxes` when there is work (4 by default; 2 on the box since Sept 30's throttle), grows to
  `gym.max_boxes` (8 by default; 6 on the box since Release A, Sept 30), sleeps a box after
  ten idle minutes, terminates a box whose image is no longer the configured one, and the Sail guard brakes
  it to zero before the House is at risk. They need no operator step: `swarm.json` sizes the pool, and
  adopting an image is one edit of `gym.image_checkpoint` (with `gym.gate_checkpoint` for its gate partner).
- **One program's failure is its own** (Release A, #440).
  - **Admission.** `check_program` compiles as well as parses, so code that the compiler refuses is refused at the
    House's admission (`researcher.check_code`) with its line. That covers an assignment expression in a comprehension's
    iterable, or an expression nested past the compiler's stack.
  - **The parent's load check.** A program it cannot load comes back `refused` ("the program fails to load: ...") and
    never reaches a worker.
  - **In a worker.** Each program loads on its own, and the engine runs the unit with `isolate=True`. A program that
    fails to load there, or whose run raises (its start, a step, its day's open or close, its result), comes back
    `error` with 0 trials. The unit's other programs run on and return exactly what they would alone.
  - **Still whole-unit failures:** a `MemoryError` (the worker's memory cap is shared by the unit), a worker that dies,
    and the unit's deadline.
  - Before, one program that parsed but did not compile failed its whole 8-program batch twice (14:03Z Sept 30), and
    three failed batches in a row retire a box.
- **Result downloads** (#436). A timed-out or dropped download of a finished result file is retried inside the
  driver's existing attempt limit and backoff, instead of requeuing the batch. TLS, permanent DNS, permission and
  unknown failures are not retried.
- **Volume context** (#431, Release A). `ctx.under.minute_volumes` exposes completed regular-session
  share volume only with first-observation receipts. Finalized historical SIP bars lack these receipts and remain
  unknown in both minute and daily inputs: completion time alone does not exclude later vendor revisions.
  `volume_coverage` names minute/history provenance and counts known/expected bars and prior sessions;
  `volume`, `daily_volumes` and `prior_volume` require complete coverage of first observations. The House persists its observed
  bars and first-observation minutes in `live.sqlite` KV `underlying_volume_session`; `underlying_volume_history`
  keeps the last 60 observed sessions per root, including incomplete-coverage counts and provenance
  `first_observed_session_sum`. A saved daily total without that provenance is unknown. Back up `live.sqlite` as usual.
  No SQL migration, site schema change, new data call, or money-rule change is required. Deploy the matching House
  and Gym bundle together; changed evaluator fingerprints require fresh qualifying evidence. Price-only images
  do not gain usable volume merely by adopting the code. Daily API totals and SPY volume for index roots are not substituted.
  `options_live.summary.volume_error` reports checkpoint/history failures; unknown values remain unavailable after restart.
- **Input capability card** (#432, Release A; the install is a step in **Release A: after promotion**). An
  operator's private Train audit can be installed as
  `/workspace/state/input-capabilities.json`, beside `swarm.sqlite` (use the actual swarm root if different).
  The Researcher family brief and Architect proposal request read it before hypothesis selection. Reads are local
  and cached by file revision; there is no model, data-provider, or Gym query to refresh coverage on a turn. Replace
  the file atomically after an audit. Missing, invalid, oversized (over 128 KiB), or different-image cards report
  unknown coverage; changing `gym.image_checkpoint` invalidates the old counts immediately. A new card does not
  by itself wake event-held families; an image change or an explicit `research_wake` does.
  Schema 1 requires `image_checkpoint`, ISO `audited_at`, `train_from`, `train_through`, `raw_file_count`,
  `raw_volume_file_count`, `raw_complete_volume_sessions`, `point_in_time_verified_volume_sessions`, and `roots`.
  Each root has `train_sessions`, `raw_volume_sessions`, `raw_complete_sessions`, `asof_verified_sessions`,
  `raw_first`, and `raw_last` (both null when no raw volume). Counts must reconcile across roots; other audit fields
  stay private and are not rendered as prompt instructions. Raw counts/date coverage and verified as-of counts are
  labeled separately; the current historical reader loads no volume receipts, so all historical strategy volume
  remains unavailable even with a matching card. No image, SQL or public-site schema change is needed for this card.
  Generate audits from nonsealed Train inputs/metadata only; never infer coverage from holdout/forward prices.
  The measured card itself belongs in private state, not in the repository or a public checkpoint.

  **Future replay receipt requirement (not implemented here):** the current-day volume KV is overwritten on the
  next session, and 60 daily aggregates cannot reconstruct first observations. Replay needs an append-only private
  archive per root/session/bar of the first accepted value, its bar interval and first-available decision minute,
  plus the actual receive timestamp, source/feed, and the extraction/evaluator version. Preserve session calendars,
  explicit gaps and polling failures, restart/duplicate identity, and a content hash so later vendor corrections
  cannot silently replace an observation. Persist each receipt before day rollover with restart-safe idempotency;
  retain the minute series as long as the evidence using it. Archive completeness must itself be measured. Current
  KV rows preserve values and decision minutes, but lack wall-clock receive/source receipts and durable multi-day
  minute history. Any future replay ingestion needs a reviewed as-of schema and explicit evidence-window policy;
  live observations must not silently enter the sealed historical Train image.

## Real money

Real money has been on since R2 (00:30Z Sept 27): `real_money` is true in `league/config.json`. The
House opens real only under the active grant, with the kill switch off and the gates below.

**The grant** `options-swarm-20260928`, the Brokerage Account only, lives on the box in
`/workspace/state/live-grant.sqlite`. The House reads it at every check, so nothing restarts.

```sh
python3 scripts/live_trading.py              # report
python3 scripts/live_trading.py --enable     # create it; capital = min(equity, live_trading.ceiling_usd)
python3 scripts/live_trading.py --ratify     # re-pin to the current money digest; capital read afresh
python3 scripts/live_trading.py --disable    # revoke for good: no new real entry; exits go on
```

Ratify within a minute of any promotion that moves the money digest, when a deposit lands (capital
rises up to the ceiling), and after a rollback across a digest change. From the A1 deploy the House's `grant` job does
the first two itself (**The standing grant**, under **Running unattended**); a rollback across a digest change is an
owner's release change too, so the job answers it as well. `--ratify` by hand is for what the job refuses. A revoked
grant is never reactivated; a new one needs a new id. The old grant `earned-live-20260921` was disabled at
06:25:00Z on Sept 26.

**The kill switch** stops every order-creating call on the real account at the gateway, exits
included; reads and cancels pass, and the paper account is unaffected.

```sh
python3 scripts/gateway_admin.py kill      # any holder of the gateway token may stop
python3 scripts/gateway_admin.py unkill    # the owner's admin token only, from the owner's machine
python3 scripts/gateway_admin.py status
```

A kill the run engaged may be released once its cause is fixed and verified; tell the owner at once
either way.

**The live path** (`league/live/`, Sept 26, 2026, Wave 5) is `House.options_live`, on when `config.json`
`live.enabled`. Once a minute in the session (a few seconds past the minute) it reads each needed root's
chain through the gateway, steps every Candidate's shadow book (the Gym's own engine, one minute behind
the wall clock), reads the Brokerage Account (equity, orders, positions, option events, funding) and
sends Probe and Sized families' orders sized by the constitution's `options_money` table. It owns both
Alpaca accounts: no old `Book` is built for them. Its state is `/workspace/state/live.sqlite` (the real
book: every order written before it is sent, positions by family, fills, the stops, the counters) and
`live-shadow.json`; programs run in a child process (`live-decider.log` beside them). The House box needs
numpy in `/workspace/.venv`. `health.json` carries its block (`options_live`: the last minute, what shuts
real entries now, the stops, reconciliation, the paper proof, every instance).

On the root House, the decider runs under host uid/gid 65534 with no supplementary groups, in a
mandatory private network namespace. Its runtime is a root-owned read-only source copy under `/tmp`;
the production env stays root-owned mode 0600 and the state/deploy directories must not be writable
by other users. The real and Candidate programs share one child and one memory allowance (2 GB), so a hung
or exhausted child can cost all of them that minute. The observe band's programs run in a second child (1 GB),
asked after the real decisions. A minute whose budget is spent skips a request without killing a child. Loads,
pipe writes, decisions and recovery share at most 40 seconds, clamped to five seconds before the next minute.
Recovery after a timeout happens within a later request's budget.

Release A (#443) hardens the decider:
- **Off a root House it refuses to start a child.** Only tests and a developer's machine pass
  `allow_unisolated=True`, in code: there is no switch.
- **A failed namespace probe is never cached.** A probe that fails or times out is retried at a spawn at least 30 s
  later. The probe's timeout is 3-10 s whatever is left of the minute, so a nearly spent minute can overrun by at most
  3 s. While a failed probe stands, the root House refuses the spawn: "the production decider requires a network
  namespace under its separate uid; the namespace probe failed and is retried ...". The next minute, or the 60 s retry
  of a failed real instance, probes again. There are about four chances before a real instance's positions become
  orphans for the House to close, which happens after five minutes.
- **The child's limits:**
  - any file it writes is capped at 64 MB;
  - it can start no process or thread;
  - a write past the cap fails, and does not kill the child.
- **Logs:** `live-decider.log` and `live-decider-observe.log` at 32 MB or more are moved to `<log>.1` before a spawn, so
  the two files hold at most twice the cap.

```sh
python3 -m league.live --root /workspace/state                        # the live state: stops, freeze, proof, positions, orders
python3 -m league.live --root /workspace/state --release-drawdown     # owner: lift the drawdown stop's pause
python3 -m league.live --root /workspace/state --clear-assignment     # owner: lift an assignment's freeze by hand
```

Real entries need all of: `real_money` true; the grant active on the running money digest; the kill
switch off; no stop tripped (daily 35% of start-of-day equity, drawdown 60% from the peak since the
reset, deposits netted, a pending deposit or withdrawal settling nothing); reconciliation clean (two
readings in a row that disagree freeze entries, two clean ones lift it; the LTC dust is known); no
unresolved assignment; the paper proof passed (for a long call or put, the single-leg proof too); the
House not paused. Exits need only the kill switch
off, and go first: an exit cancels another family's resting open on its contracts and waits for them.
A forced exit also cancels a blocking program close; ordinary exits do so after waiting two minutes.
Expiring equity structures with a leg in or within 1% of the money are the House's to close from ten
minutes before the close cutoff (15:00 ET for most roots, 15:15 for SPY and QQQ): a program's own
close is cancelled for the forced one; index structures settle in cash. An expiring long call or put is
the House's to sell there whatever its moneyness while it has a bid (never exercised: the account cannot
carry 100 shares). The last forced close before the cutoff is never cancelled for a re-price. A family moved onto real money
trades it from the next live minute since fast lane v2 (the next session before it, and still for a Probe with no
promotion record); a Candidate whose typical maximum loss is unknown stays shadow-only
(`live.band` rows with `held` say why, once a day). A Probe becomes Sized only after five real Probe
trades and a whole session at Probe. Each real instance has 60 orders a day (the Gym's), charged for
orders that reached the venue and checked for opens only: an exit is never refused on it. A program's
closes (and cancels of its closes) keep room for the House's own exits under 250 legs, and the gateway
stops opens at 250 orders while exits go on to 300. An exit waiting for its contracts is kept across a
restart and dropped at the day's end (its program is told).

Money-band decisions commit only while the selected version and its forward evidence still match.
Promotion time commits in that same swarm transaction, so a crash cannot bypass the next-session
wait; a legacy row without a known promotion time starts its wait at the House's first sighting.
When executed funding changes, the House rereads equity between matching funding histories before
latching a stop. An account read taken before that transition is only provisional.

Demotion, retirement and an unavailable program cancel the instance's working opens. Programs kept
for exits still reload after a decider failure; five minutes without recovery makes their positions
orphans for the House to close. Closed real trades are acknowledged individually, so an older
position that closes late cannot be lost behind a newer trade's export. After expiry, external
liquidation fills reconcile the missing legs and fees, including remaining legs of a broken structure.
Consumed quantity and value are persisted together, so a later cumulative fill price cannot reprice
contracts already attributed to another family. Missing fill values leave an explicit
`unpriced_close` row, release stale exposure and block new entries until venue fills or expiry events
resolve the accounting; estimated intrinsic values never become forward evidence.

The checked-in deployment has `real_money: true`, the grant is active on the money digest in force (`0310779c` since
release L-D's deploy of 09:04Z Oct 9, re-ratified by the standing grant at the House's start; `1665c385` before it, from
the incubator cap's deploy of Oct 8; this tree's is `fdf2ac7c`, the Probe total at $800, which the grant re-ratifies at
the House's start on the owner's deploy of it), and the gateway's `OPTION_STRUCTURES_REAL` names the four debit types.
The gateway still admits paper structures and verified closes of held real positions; `off` is still a permitted
stricter setting in `league.ci`. The paper route proof runs from 09:35 ET until it has passed, even with no real-account
client, grant or eligible family, and keeps an unfinished attempt's identity and owned contracts through restarts. Both
proofs (the multi-leg vertical and the single-leg call) passed on Sept 28; a passed proof is not run again. Passing
records paper execution evidence, never a family's evidence.

**The money table (the sprint, owner decision D4, Sept 26, 2026; the Probe rows since fast lane v2, Oct 7, 2026, release
L-D, Oct 9, 2026, and the Probe total at $800, Oct 10, 2026)**: real types under $2,000 of equity are exactly
`debit_vertical`, `long_butterfly`, `long_call`, `long_put` (the credit types come back only with a deposit to $2,000,
in one deploy with the gateway, and a re-ratified grant); a Probe position is one structure within 10% of equity (5%
with a $100 one-contract floor before fast lane v2), 3 open a family, 15% the family, at most 8 Probe positions across
the account (3 before L-D) and a Probe loss budget of $400 in any rolling 20 sessions and $800 in total (the owner's
ceiling in his goal of Oct 9, since Oct 10 and measured at roster 5; $400 in total at L-D, and $400 in total with no
window before it): realized Probe losses NET (`probe.loss_basis` "net"; GROSS before L-D) over the window's closes (its
worst net stretch, so the $400 holds over every 20 sessions) and over every close, each plus every real position's
maximum loss held or working plus the new open, so the dollars bind before the count; a Probe or Sized family is demoted
by DM1 (`probe.demotion` "dm1"; D5 and the negative forward record before L-D, a Candidate's still); the book 90%; daily
stop 35%, drawdown stop 60%; tuition $200 a day; the D3 calibration's day bounded at $50 of possible loss. The other
routes keep the Probe room, min(`max_open` x 10% x E, $400), of the book's and the day's caps. Release L-D's section and
the Probe total at $800's (both earlier on this page) have each rule's cost and its rollback. The gateway's per-order
cap is the lower of $1,000 and 25% of equity (at Sept 28's $1,473.11 of sizing equity: $368.27; 5% is $73.65, so a
Probe's $100 floor applies; equity was $1,312.79 on Oct 2), 100% of equity opened a day, 250 of 300 orders open.

**The single-leg paper proof**: once the vertical's has passed, the practice account opens and closes a
1-lot SPY call about 1-2% out of the money (nearest expiry at least a day out, at the natural, held two
minutes) with single-leg orders. Real long calls and puts open only after it (`paper_proof_single`).

**Two-sided single families (`long_single`, #425; ships in Release A)**: a family may declare `long_single`, one program
whose every open is one `long_call` or one `long_put` (one leg, long), the side chosen by its rule, in place of a
call/put twin pair. It is a declared structure, never an order type: the money table's `real_types`, the money digest
(`a3e2aa7c` then; `42c4a3af` since Release B, for the incubator's row) and the gateway's `OPTION_STRUCTURES_REAL` are
unchanged, and none of them may name it. The live path maps it to real (tuition, Probe, Sized, the site's
`real_structure` check) only while BOTH `long_call` and `long_put` are real types (`money.order_types`,
`Table.family_real`, `Table.family_allowed`); drop either and the family is held at Candidate with the reason recorded.
Every order it sends still carries its own type and is checked (`type_allowed`, the single-leg paper proof, the gateway)
and sized by its own unit, exactly as a one-sided family's. Its declared type is enforced on real opens only: the live
path refuses a real open of any other type from it ("a long_single family opens only long_call or long_put for real,
never ..."; `money.DECLARED_TYPES`, the instance's `structure`, read at each sync). The Gym and the shadow book never
read a family's structure: there, as for every family, each order is judged by its own type, and a one-sided `long_call`
or `long_put` family is unchanged everywhere. Its forward record, D2 and the drift screen are any family's (it is only
as drift-neutral as its side rule: the screen charges whatever net exposure it holds). The site shows the agent's
structure as null (the site's schema has only the eleven order types) and each of its positions as `long_call` or
`long_put`. The Gym is unchanged: it never reads a family's structure, so its bundle version does not move.

**The practice league** (the observe band; live since Release A, Sept 30, 2026, through #431).
- **Who:** every alive Gym-band family with a validated version, or with an eligible Train version (the version the
  tournament validates next, not demoted).
- **How:** it trades the shadow book on live quotes as `<family>@<version>:o`, on a $10,000 practice account. Its program
  is frozen in `observe.sqlite` before the first decision. Session admissions are in `live.sqlite` `observe_pins`.
- **Never** real, tuition, a forward row or a band move. Two code guards hold this (Release A, #437):
  - an observe instance is only ever a shadow, non-tuition `:o` instance (`Instance.__post_init__`);
  - the order path refuses any instance that is not real, with an error alert: "live: `<key>` is not a real instance and
    asked for a real order: refused".
- **When:** its programs load and decide after every real decision of the minute, in their own decider child (1 GB).
  Its chains are read after the real path, under the minute's data budget.

- **Tiers and order.** The validated tier by validation t, then the Train tier by Train score (highest first, unknown
  last), then by id (`bands.priority`). `live.observe_train` false leaves the Train tier out and winds its pins down at
  the next families pass.
- **Two caps.** `live.observe_max` instances (48) and `live.observe_roots_max` distinct roots (24). Roots bind first:
  every root is read every minute at about 1.1-1.5 data calls, and holds a full-day grid in the House (about 3 MB, at
  most 28 MB). A family whose roots would pass the roots cap is skipped, not stopped at: a later family on roots already
  read may still join. A cap lowered at runtime keeps the first families pinned. The held-back families are said once a
  day (`live.observe` {capped, why: "cap" | "roots"}).
- **Measured** (the House, read-only, 13:33-13:50Z Sept 29): 1 vCPU, 4,284 MB, 3,510 MB available; the House 135-141 MB,
  the swarm 470-513 MB, the observe child 36 MB; a minute of 1 real and 7-8 observe instances took 2.4-3.5 s end to end,
  a decision under 50 ms; 11-16 data calls a minute for about 11 roots against the observe phase's 40. 24 roots is about
  30-36 observe calls a minute. Expect 7-20 instances, not 48: eligibility is hard and families live hours.
- **Degradation.** As before: at most 16 loads a minute above a 10 s floor; observe reads stop at
  `live.observe_read_calls` (40; raise it with the roots cap, about 1.5 calls a root) and at 3 pages and 5 s a root;
  a `BudgetSpent` batch waits a minute. New: when 3 of the last 10 session minutes were **pressed** (the observe batch
  skipped or failed, or an observe read skipped), the lowest-priority quarter (at least one) of the Train-tier pins is
  shed for the rest of the session, at most once every 10 minutes, and no new family joins past what is left
  (`observe_shed` in the live state, so a restart keeps it; one `live.observe` {shed, effective_cap, why} and one
  alert). Validated pins are never shed. The next session admits surviving frozen cohorts at the full caps.
- **Frozen cohorts.** Research retirement and newer revisions do not terminate a cohort. It finishes between sessions
  after at least three observed sessions and ten program closes while flat; otherwise its maximum is
  `observe_max_sessions` session days (the step's default is ten; `league/config.json` `live.observe_max_sessions` is 30
  since Oct 8, 2026, mirrored by `league/swarm/practice.py` `COHORT_WINDOW`), extended to cover the program's declared
  DTE horizon plus three sessions, bounded at sixty. The House reads the window at every cohort pass and a snapshot
  keeps only its DTE horizon, so a new window applies to the cohorts already active from the House's next start. An
  expired snapshot never rejoins; a newer eligible version may. Switches, caps and pressure can still wind it down.
  These are practice durations,
  not capital gates (`OptionsLive` config `observe_min_sessions`, `observe_min_trades`, `observe_max_sessions`).
  Snapshots pin the Gym bundle and fill model. If either changes, old cohorts become close-only and their wind-down
  outcomes are excluded from program feedback. The family/version ledger currently requires a newly eligible source
  version for fresh practice after an evaluator change; it never mixes evaluators into one successful cohort.
- **Ending a cohort by hand** (the operator, after a close, never mid-session). Retiring the family does not end its
  cohort: the two GOOGL-lineage cohorts kept practising after their families were retired on Oct 1. On the box:

  ```sh
  cd /workspace/current && /workspace/.venv/bin/python -c "from league.live.observe import ObserveStore; \
  ObserveStore('/workspace/state').fail_cohort('<family>', <version>, day='<YYYY-MM-DD>', reason='operator: <why>')"
  ```

  The cohort then reads `failed`, and its pin is freed at the next session's first pass. The store opens SQLite with a
  0.05 s timeout, so retry on "database is locked". Record it in the run record.
- **The 30-session cohort window** (Oct 8, 2026; `league/config.json` `live.observe_max_sessions`, the owner's deploy,
  and `practice.COHORT_WINDOW`). Under the practice cap of 3 open structures, mostly held to expiry, no cohort could
  reach the incubator's 10 program closes inside 10-18 sessions. The verifier's replay on the House (each cohort's own
  Gym trades under the practice caps) gave a first look inside the window with probability 0.46 / 0.24 / 0.13 at 20
  sessions and 0.92 / 0.98 / 0.78 at 30 for the three best candidates (china-tech-us-lead-lag@16,
  peer-skew-conduction-single@11, opening-range-highbeta-continuation@31), with expected looks around sessions 20-24.
  So 20 is too short and 30 is the window. What it costs, and the levers:
  - **Roots.** Frozen cohorts are pinned before any new family (`observe.cohort_candidates`), and the binding cap is
    `live.observe_roots_max` (24). On Oct 8 the 12 active cohorts held 22 of the 24 roots; after the two barred ones end
    at the 02:00Z hygiene, 10 hold 21. Every new family then has at most 3 new roots until the cohorts complete (Nov 19
    for the Oct 8 batch, against Oct 22 to Nov 3 under the old window). SPY, XSP and SPXW are free, so the game's core
    arms are not starved; families on other roots are.
  - **Newer versions.** A family with an active cohort practises no other version for the whole window
    (`cohort_candidates` drops its current rows). After T0 that includes the family's new best over 2022-24.
  - **Cohorts that cannot be pinned.** Three cohorts fail the incubator's screen over the current span
    (index-corr-dispersion-break-vertical@32 t 0.46, smci-mara-post-earnings-drift-debit@11 t 0.08,
    semis-lead-smallcap@16 t 0.88) and alone hold IWM, MARA and SMCI. T0 judges them again over 2022-24, so they are
    not dead for good. `tournament.keep_order` spares their families from retirement all the same (it does not ask
    whether a cohort can be marked).
  - **Levers.** (a) The operator ends a cohort that can never be pinned (**Ending a cohort by hand**, above), as the
    Oct 2 "operator (v3 phase 0)" failures were recorded: the screen failures only when T0 is not near. (b) swarm.json
    `live.observe_roots_max` (a runtime switch, 1-128), with `live.observe_read_calls` raised by 4 per root (the read
    budget is 1 + 4 x roots + 20). (c) Owner deploys, both in walled files: `tournament.keep_order` skipping a cohort
    whose mark is dropped for good, and `league/ops/hygiene.py` `end_cohorts` ending a demoted or lost-at-1.5x cohort
    (not a screen failure alone).
- **The practice-evaluator freeze** (Oct 8, 2026). A cohort ends at once when the practice evaluator moves ("evaluator
  changed; a new version needs fresh practice"). Of the 33 cohorts ever completed on the House up to Oct 8, 30 ended
  that way (most 0-2 days after admission, at the Oct 3 and Oct 7 releases) and 3 by an operator; none has ever reached
  its window or its observation target. The practice evaluator is
  `<Gym bundle>:<fill model>:<execution fingerprint>` (`league/live/step.py`): `league/gym/**` (.py and .md), the
  LEAGUE_FILES (`league/__init__.py`, `safety.py`, `structure_core.py`, `stats.py`), `league/live/**.py`, and the
  House's fill model (`/data/calibration/fill_model.json`, read at the House's start). The 30-session window only helps
  if none of these moves until the Oct 8 cohorts have had their first looks (expected around sessions 20-24, Nov 4-10),
  better until they complete (Nov 19): no release that touches those paths, no fill-model recalibration
  (swarm.json `live.calibration` stays false and the fill model file stays as it is). Before any release, compute the
  candidate tree's execution fingerprint and Gym bundle (`league.swarm.evaluator.execution_fingerprint`,
  `league.gym.driver.build_bundle`) and compare them with the cohorts' `practice_evaluator`.
- **Private receipts.** `observe.sqlite.events` records decisions, coverage, intents, rejections, orders and fills with
  leg quotes, fees and slippage against decision mid. The shadow account saves unacknowledged receipts and retries
  idempotently after a restart. Events retain 120 days; a prolonged ledger outage has a 10,000-event per-account buffer
  with an explicit dropped count. This private market data is never published. Program errors are `missed_errors`,
  separate from missed quotes and budget; they do not count as successful decisions.
- **The record.** `/workspace/state/observe.sqlite` (0600): `trades` (one row a closed practice trade: its session,
  exit reason and `forced` when the House closed it winding down) and `practice` (one row per family and version from
  its first live minute, kept after the family retires: tier, lineage, structure, roots, sessions, minutes, decisions
  due / made / missed for want of quotes / missed for want of the budget / program errors, the per-minute marked P&L's peak and drawdown,
  open positions at the engine's mark). Realized P&L is the headline; open positions are apart, at the mark.
- **Who reads it.** Nothing that feeds evidence or money (the gate, the verifier, the bands, the money table, tuition,
  Profit). The swarm reads its summary as a research signal (`league/swarm/practice.py`: the strategist's PRACTICE
  table, the architect's PRACTICE BY CLASS lines, the share bonus: at most +25% of a family's share and at most 10% of
  all share moved). `family_feedback` also supplies researcher context after ten program closes over three close-session
  days; its revision token changes on a new close day or another five closes, so idle researchers can wake on meaningful
  observations. `practice.feedback` false turns these off. The site shows its aggregates (`practice`, below).
- **The forward embargo.** Because practice feeds research, a Sized move also needs the forward record of the sessions
  after the later of its version's creation and selection (`banded_at`) to meet Sized on its own (`OptionsLive._move_band`; held moves are `live.band` {held}
  rows). The whole record still decides negative, Candidate and Probe.

**The D3 calibration round trips**: 1-lot SPY, QQQ and IWM call verticals one dollar wide nearest the
money, hourly at 10:00, 11:00, 12:00, 13:00, 14:00 and 15:00 ET (none starts from 15:15); open at the mid
for 5 minutes -- at 12:00 and 14:00 the patient cell `mid25`, the mid for 25 minutes -- then once at the mid
plus a tick (its own cell `mid25+1` after the patient open), only after an open its time in force ended;
close at the mid, a tick under, then the natural (at most six close attempts a position a day, backing off
after a refusal; every ladder, at its slowest, is sent before the 15:45 last resort). One round trip at a
time, within a strict $50 bound on the day's possible loss: a new open goes only while today's realized
calibration loss (net, floored at zero) plus what is still held or working plus its own maximum loss stays
within $50; a closed round trip frees its maximum loss. What it leaves the families: every calibration open
leaves the Probe room (`money.probe_room`: min(`probe.max_open` x 10% x E, $400) since release L-D; 3 x 10% x E
from fast lane v2; two Probe floors, $200, before it) of the account-wide day cap (1.0 x sizing equity, which every
dispatched open fills by its whole maximum loss, cancelled ones too); no round trip starts once its own legs today (orders
and cancels) reach 80 of the day's 250 (a round trip is 4 legs when both mids fill, about 30 at its
slowest, so at most about 110 before the House's backstop); and a working open whose contracts a family's
real open was refused on is cancelled at once, its round trip ended (recorded `interrupted`). An attempt
cancelled before its time in force ran out (a real-entry block, the House's cancel, that yield) is
`interrupted`: never a sample, never in a fill rate. Only with real money on, the grant active, real
entries open and the paper proof passed; family `house:calibration`, never evidence; in Profit since Sept 28, 2026, as the positions table's "House
calibration" rows (`league/trading_profit.py`; the table must add up to Profit). The owner's written D3 terms (`league/constitution.py`'s
comments) say 1-lot SPY and QQQ; IWM and the six slots' volume (about $430-540 of maximum loss dispatched
on a heavy day, against about $270 before) are the operator's decision inside D3's $50 net bound (Sept 28,
2026), the money table unchanged. Samples: `/workspace/state/calibration.sqlite` (0600; each row its
order's time in force and cancel reason), read with `python3 -m league.live --root /workspace/state
--calibration` (the plan, then every cell, `mid25`, `mid25+1` and the unsampled included: working minutes,
attempts, outcomes, fill rate, mean fill against the mid in ticks, median seconds to fill). Off by default:
`swarm.json` `{"live": {"calibration": true}}` turns it on (on since 00:31Z Sept 27).

How samples may change the Gym (Sept 28, 2026): only through the frozen recalibration protocol, PROTOCOL-v2
(private; sha256 `10f78877…`). Real calibration fills move the Gym's patient-fill table only through a
pre-registered, held-out test: even sessions fit, odd sessions test, at most four looks, sessions as the unit.
Adoption needs significance, no root or patient cell getting worse, and the Gym never more optimistic than real
fills on price. The owner committed in advance to adopt on a passing look without first seeing any strategy's
results under the new table (sha256 `befe90dc…`). The first test session is Tuesday Sept 29. The tool is private.
`live.calibration_samples` is 100 (the owner, Sept 28): the same $50 a day bound, months of sampling, a 1.5x
error in a cell's fill rate caught about half the time (at 30 samples only a 2x error is caught), false adoption
0-1%.

**The House live test** (the owner, Sept 28, 2026; `league/live/house_test.py`; a new shadow-to-real route,
pre-registered in a private file whose sha256 is `c73e2d262b8d2e9493b53c427400ba7adc37490db8c981ddd96644fdb6977954`):
one frozen swarm program (1-lot debit verticals; private, only its hashes are public) runs as the House's own
real instance `house:rebound-live@0:h`, through the families' decider child and order path, only to measure its
real fills and P&L. Never a band, a promotion, evidence or a forward record; D2 unchanged.

- Bounds (the money table's `options_money.house_test`): one structure of at most $100 with fees, at most 3 held or
  working, its NET realized loss plus what is held or working plus the new open at most $300 at every open, no new
  open ever again once its net realized loss reaches $150 (from the book's fee estimates; Profit uses the broker's, so
  they can differ by cents), new opens only through its 20th session from the start and while its round trips are
  under 30. It leaves the families $200 (two Probe floors) of both the day cap and the book's cap, and opens nothing
  while its record (`/workspace/state/house-test.sqlite`) cannot be written.
- The families first: its intents go after theirs each minute, and its working open yields to a family order refused
  on its contracts after the open was placed (never to an older refusal). A position it holds refuses a family's open
  of the other side of that contract ("positions net across the account"), as any held position does.
- The same gates as the calibration (real money, the grant, the kill switch, the stops, reconciliation, the paper
  proof). Its losses count toward the account's daily and drawdown stops like any position's: a bad day for it can
  trip them for everyone.
- Its orders say "House live test (pre-registered)", never the program's note. Its positions are Profit, the positions
  table's "House live test" rows (`source` `house`, which `league/trading_profit.py` gives only this family).
- The program and its params: on the box at `/workspace/state/house-test/rebound-live/program.py` and `params.json`
  (directory 700, files 600, root's), placed by the operator's private upload script (`--apply`, through the Sail
  file API, never on a command line), and in `live.sqlite`'s `instances` row as every real instance's. Checked at
  every load: an identity mismatch (the hashes, the run sha) and it never runs, a restored instance fails for good and
  the House closes what it holds; any other load failure is retried as a decider failure.
- `health.json` `options_live.house_test` shows the files, the start (day, release, fill model), the sessions used, the
  round trips, the realized and possible loss, and a stop or end. Each order's quotes at submit and its outcome are in
  `house-test.sqlite` (an unfilled order ended by its time in force, the close cutoff for expiring contracts or the
  session's close is a full-window sample; any other end is "interrupted").
- Off by default: `swarm.json` `{"live": {"house_test": true}}` turns it on (only after the analysis script's sha256
  is pinned in the private addendum); off again sends it to exits only and cancels its working open within a minute.
- **State:** on since 00:17:28Z Sept 29, switched on after its analysis script was pinned (new opens through its 20th
  session). As of Oct 2 it has sent no order.
- **After a restart:**
  - a restored House test instance is always `kind` real and `observe` false: #429 restores by keyword, and from
    Release A, `Instance` coerces the flag (#437);
  - its program's own orders pass the order path's belt;
  - after Release A, check `options_live.instances["house:rebound-live@0:h"]` for both.
- While it runs: no House deploy or restart inside the decision window the private pre-registration names (each load
  of its program is a `live.instance` "house test program loaded (fresh memory)" row; one inside that window, a
  decider-child restart or a skipped minute there is a deviation of the test, logged in the private addendum). Before a rollback
  past the release that carries it: switch it off and wait until it is flat (an older release would run it as an
  ordinary instance, export its trades as forward rows and show its positions as an agent's).

**The incubator** (Release B, #451; `league/live/incubator.py`; the money row `options_money.incubator`). This is a new
shadow-to-real route: one lot of real money for a family whose live practice was positive. Its P&L is real, and it is
never evidence.
- **The owner's terms.** Approved Sept 29, 14:51Z; the reading was settled Sept 30. A family that passes Train and the
  drift screen on its own, shows positive live practice, and passed the gate's review and audit, trades one lot of an
  approved real structure: at most $50 of maximum loss a structure, fees included, and at most 4 held or working. The
  route stops for the ISO week once its net realized loss reaches $150. It never promotes: D2 is the only route to
  Probe and Sized.
- **The incubator cap (Oct 8, 2026).** Claude's decision under the owner's goal of Oct 7 (item 4 allows up to 10% of
  equity at risk per Probe position; item 5 asks every loosened rule reported with its cost): a structure may risk at
  most $75 with its fees, and a family at most $75 held and working (both $50 before it). The week's $150, the 4 held
  or working and the one lot are the owner's terms as they were, so at most two $75 units are open at once. Its reason
  and cost are in **The incubator cap**, at the top of this page.
- **What it trades.** The unit is a practice cohort `(family, version)`. Its frozen snapshot is the program the
  incubator trades, byte for byte, as the real, tuition-flagged instance `<family>@<version>:i`.
- **The first look** (pre-registered; `money.practice_ok`). It is taken once per cohort, at the first session pin at
  which the cohort's record before today holds at least `min_sessions` (3) completed sessions and `min_trades` (10)
  program-closed trades under the running evaluator. It passes only with all of:
  - decision coverage of at least `min_coverage` (0.80);
  - realized practice P&L above $0 over the program's closes;
  - above $0 over all closes;
  - above $0 over all closes plus the open mark.

  The look is saved in the live state (`incubator_verdicts`) first, and only then recorded as a private `live.incubator`
  `first_look` row (with the program and run sha it judged), whether or not the switch is on. A failed look is final. A
  cohort with a `first_look` row under the running evaluator is never looked at again, even if its saved verdict were
  lost: the verdict is restored from the row as recorded, and a recorded `ended` row still ends it. After a pass, each
  later session re-checks coverage and the three P&L tests on the longer record, and a failure ends the incubation for
  good. A program with no edge passes roughly a third to a half of the time: the weekly envelope bounds the cost, not
  the screen.
- **The swarm's facts** (`league.swarm.bands.incubator`). The family must be:
  - alive, in the Gym band, with the version not demoted (at 1.5x or by drift);
  - carrying a Train-and-drift pass for the version under the current evaluator and Train objective, with a positive
    1.5x Train P&L;
  - reviewed and audited by the gate on the version's run sha, under the current review contract;
  - not refused, failed or demoted by the gate on that sha;
  - not on D2's route: a validated version that met the line gives it a tuition row, which comes first.

  **The reader's belt** (`bands.incubator_refusal`, with B2 #444) comes first and reads the verdicts themselves, not
  only the mark, so a program whose review or audit failed never trades the incubator (the owner's term). There is no
  row for a program the swarm barred (`incubator_barred`: bars are kept for good, and no evaluator adoption clears
  them), one the gate's `review` names without a readable pass and a passed audit (a pass whose audit is still owed
  waits), one whose incubator review or audit failed or was revoked, a version the gate refused at any stage, a program
  whose holdout look failed, or a family whose verdict records cannot be read. These are read for the PROGRAM (the
  same code and params, so the same run sha) in every family that holds it, alive or retired, and a program the gate
  owes a bar is refused too (`incubator-bars-owed.json` beside the swarm store, written only when the store errs; if it
  cannot be read, every incubator row is refused until the gate writes it again). The swarm start backfills bars from
  release B's gate events (log line `incubator backfill: N programs barred`), and an evaluator adoption records every
  failure it would clear before it clears it. The swarm reads the belt's own rules in every other family holding the
  program before it marks a version or pays for an incubator review (`incubator.program_bar`, Release B'), so it never
  pays to review a program the belt would refuse. Another family's gate review that passed with its audit still owed
  holds the program off until that audit lands, and for good if that family retired. This is not a verdict: nothing is
  recorded and no passed review is revoked.

  An unreadable store refuses: no pin and no open, while exits go on. B2 (#444, in Release B) writes the
  Train-and-drift pass and the incubator's reviews.

  **The incubator's own drift screen** (Oct 8, 2026; `incubator.screen_verdict`). Fast lane v2 switched
  `tournament.drift_screen` off for selection on Oct 7, and the mark read that as "never passes": no mark was written,
  the sweep removed every mark, and no cohort could be pinned. The mark now evaluates the screen itself: the
  tournament's screen at its own thresholds while it is on, and while it is off the screen at its default thresholds
  (pooled t 1.0, positive in every Train year but one) and also at `tournament.drift_min_t` and
  `drift_years_positive` wherever those are stricter (an off screen never loosens the mark). The sweep no longer removes
  marks for an off screen. A known failure still drops the mark. The tournament's selection, validation, the gate and
  the bands read the screen as before. A "drift" run that fails three times demotes its version only while the
  tournament's screen is on (`researcher.robust_landed`); with it off, such a run is the incubator's alone.

  **The re-runs** (Oct 8, 2026; `incubator.reruns`, asked for by the swarm loop right after each hourly tournament
  round, `Swarm.incubator_reruns`; not in `league/swarm/tournament.py`, which is the owner's deploy). The learning
  game's T0 (a new Train span) and a Gym image change leave every cohort version's mark stale and its runs from another
  span or image. The researcher re-runs only a family's best or submitted version. So an active, current cohort version
  with no current mark that waits only on Gym runs has them queued one at a time, in the order that spends nothing on a
  version an earlier answer rules out: its Train run over the running span (recorded as a scored Train row of the
  version, with its drift figures), then the "drift" run if a Train answer is in without figures, then its 1.5x run.
  Never the mid run. They run at the robustness priority (`GymJob.incubator`: a newer best never supersedes them).
  Nothing is queued for a version that failed for good (demoted, lost at 1.5x, failed the screen, barred), whose Train
  answer over the span is ineligible, that is on D2's route, or whose cohort is failed, complete or under another
  evaluator. A version is asked for again only once its job has landed or failed, so a failure is retried at a later
  round and a restart, which loses queued jobs, re-queues them at its first round. Three EXECUTED failures (a run the
  Gym ran that failed, erred, or landed without an answer under the current evaluator) under one Train objective and
  evaluator spend the version (`incubator_reruns` in the family state), with one `swarm.status` alert
  (`incubator_reruns_spent`); a restart, a supersession or a retirement charges nothing. Each round's result is one log
  line ("incubator re-runs: ...") and, when anything was queued, one `swarm.robustness` event (`incubator_reruns`).
  New re-runs are asked for only while the guard allows new research; jobs already queued are the pool's like every
  robustness job: an asleep box's dispatcher takes a robustness head, and resumes the box, when another box is free or
  once the job has aged (`pool._take_active`), and queued jobs keep running under the research hold (`GymPool` asks the
  guard about `gym`, not `research`). At most one job per cohort version is
  ever in flight, so the cost after T0 is about two Gym jobs per cohort (Train, then 1.5x). The next round's marks read
  what landed.
- **Pins,** at the session's first families pass. A restart reuses them, and nothing joins mid-session. At most 8
  cohorts, one per family, by first-look return on risk. Each needs:
  - the switch on and real money on;
  - a first look that passed, and a record that still passes today;
  - an active cohort with its program unchanged;
  - the facts, with the snapshot's run sha;
  - no D2 route for the family (`:r` > `:t` > `:i`);
  - a real structure;
  - at least one sampled program close that one lot could open under the $75 cap.

  Every families pass checks again, and a failure sends the instance to exits only, its working opens cancelled.
  `health.json` `options_live.incubator.pins.refused` says why each passing cohort was not pinned.
- **Keep (L2').** While the switch is on, a cohort whose first look passed keeps practising past its observation target
  to its bounded window (at most 8), so its re-checks go on. Off, the practice league's own rule is unchanged.
  - **A failed read never ends an incubation.** Sometimes today's check cannot be taken: the cohorts or a cohort's
    record cannot be read, or the first looks raise. Then the last keep's cohorts that no re-check ended stay kept, and
    so does an active cohort whose first look could not read its record (first look or not, and across a restart).
    A cohort kept without a verdict (its first look unread, or waiting for the next session's record) stays kept for
    the rest of the day, a restart after the day's retries included. It is never a pin candidate, and its look is
    taken at the next session's first pass.
  - While the cohorts themselves cannot be read, and on a pass where the keep raises, the practice league completes
    no cohort at its observation target (`observe.HOLD`). That is practising only, for that pass, and only while the
    day's retries remain. After them the carried keep (or, if the keep still raises, the last saved keep) alone is kept
    and the rest of the league completes by its own rule; one error alert a day says so. If the saved keep cannot be
    read either, the House keeps the last keep it took itself, or, if it has taken none since it started, completes no
    cohort at its target. It never falls back to keeping nothing, which would complete pinned cohorts.
  - Such a cohort is never pinned on the untaken check. `pins.refused` says so, and a private `live.incubator` event
    (`unread`, `keep_carried`) and one alert a day record it. A failed ledger write never changes the keep.
  - The keep is marked `unread` (health `keep_carried`), and the next families pass, 5 minutes later, takes the checks
    again, for at most 12 counted passes after the day's first. After that the day's keep stands and the next
    session's first pass reads again. Pins are still taken once a session.
  - The day's passes are counted durably in the live state (`incubator_session`: day, passes, the last counted pass's
    time, the day's waiting first looks), written at the START of each in-session families pass, before the bands or
    anything else is read. A pass whose reads all fail still counts, and a restart keeps the count.
  - A pass counts only 5 minutes (`FAMILIES_EVERY`) or more after the last counted one. A pass forced sooner (a forward
    read that fails, a band not confirmed, the decider losing a program, a restart) reads again but spends no retry, so
    the 12 retries span at least an hour.
  - Within a day the keep only grows. A cohort kept at an earlier pass leaves it only when a check ends it (or its first
    look fails) or its cohort is no longer active, so a pinned cohort is never completed mid-session. A cohort held on
    an untaken check is kept beyond the 8 and never takes the place of one checked that day.
  - **Every first look and re-check reads the record before today, never today's values**, at the session's first
    pass or at a retry alike, whatever failed before it. `observe.practice_record` leaves out today's closes and
    today's session, and it reads the practice row's decision coverage and open mark as its last session before today
    left them. The practice row keeps those (`prior_due`, `prior_made`, `prior_open_mark`), copied at the first minute
    of each new session day and stamped with that day (`prior_day`, the day of the copy, not the day the values came
    from). They are read only when `prior_day` is today. So a retry reads the same before-today record as the first
    pass, plus any before-today closes recorded since (a trade written again after a failed write, a missed expiry
    settled on its day): today's mark can neither end an incubation nor pin one.
  - A record that cannot say what its row held before today (`intraday`) decides nothing on P3 or P6. That is a row
    stepped today before those columns were kept (only around the release), or one stepped today by a release that never
    copies them, as after a rollback to release A: its `prior_day` is then an earlier day, and its values an older
    session's. A re-check then ends only on P4 or P5, evaluated whatever P3 says, and is otherwise `deferred`: kept, not
    pinned, and re-checked at the next session's first pass. A first look then fails only on P4 or P5, and otherwise
    waits, kept, for the next session's record. It is never taken again that day.
  - The first pass of a session day that cannot pin is retried every 5 minutes, not every minute. That covers the bands,
    the observe band or its cohorts being unreadable, and the incubator's pins raising. A restart asks again at once,
    and switching the observe band on mid-session still pins it at the next minute.
- **The caps** (`money.plan_incubator`, with the tally read afresh from `live.sqlite` at every open). They live in the
  House only: the gateway cannot tell routes apart, so its caps are the backstop.
  - One lot; at most $75 a structure; at most $75 held or working per family (both $50 before the incubator cap of
    Oct 8, 2026).
  - At most 4 structures held or working.
  - **The weekly envelope:** this ISO week's net realized loss, plus what is held, plus what is working, plus the new
    unit, at most $150 at every open. Once the week's net realized loss has reached $150 at any close, the route is
    stopped until the next ISO week, a later gain notwithstanding. The stop is alerted once a week: "live: the incubator
    its net realized loss this week reached $X, at or over $150: stopped for the rest of the week (exits go on)".
  - 40 order legs a day, and 25% of the gateway's day cap.
  - Room kept in the book's and the day's caps: the families' Probe room (`money.probe_room`: min(`probe.max_open` x
    10% of E, $400) since release L-D, $400 at 8 slots; 3 x 10% of E from fast lane v2, $386.52 at E = $1,288.40; two
    Probe floors, $200, before it) and, while the House live test can still open, its structure ($100).

  The $150 is a true bound apart from residuals: broker fees above the book's estimate, and a broken structure closed
  leg by leg.
- **The order of a minute.** The D2 families' intents go first (`:r`, `:t`), then the incubator's, then the House live
  test's, then the calibration's. A working incubator open is cancelled, recorded "yielded", when a D2 family's real
  order is refused on one of its contracts after the open was placed. The House live test yields to an incubator
  refusal as to a family's.
- **Never evidence.** Its rows are tuition-flagged, but never in tuition's own day and week sums. It is never:
  - a forward row;
  - a band move or a promotion;
  - read by the swarm.

  Its positions are Profit, on the site with the source "incubator" (the agent's id as an agent's).
- **The belt.** An `:i` instance must be real, tuition-flagged, on a House with an incubator, and its route is its key's
  alone. Anything else that asks for a real order is refused before the venue, with an error alert: "live: `<key>` is
  not a real tuition incubator instance and asked for a real order: refused". A restored `:i` instance is
  tuition-flagged whatever its row says.
- **The cost.** Expected value is negative until a family has a real edge: at most about $650 a month on average ($750
  in a five-week month), plus residuals.
- **The switch:** `live.incubator` in `swarm.json`, off by default. Only JSON `true` turns it on; any other value reads
  off and is alerted once. Switch it on only outside a session, after the ratification. Off takes effect within a
  minute: exits only, and working opens cancelled. First looks are recorded either way.
- **Where it shows:**
  - `health.json` `options_live.incubator`: the switch as last read, the table, today's pins and refusals, the keep,
    the verdict counts, the tally and the weekly stop;
  - `options_live.instances[...].incubator`;
  - `python3 -m league.live --root /workspace/state --incubator`, read-only: the switch as `swarm.json` says, the pins,
    every first look with its P1-P6 values, the tally, the instances and today's refusals;
  - private `live.incubator` ledger rows: first looks, ends, pins, yields and the weekly stop.
- **To stop it,** in order of reach:
  1. `live.incubator` false (within a minute);
  2. `max_open`, `week_loss_usd` or `max_loss_usd` set to 0 in the money table: a tightening, so a new digest, an
     owner deploy after a close and a ratify. The constitution is outside the fingerprint, so it is no evidence reset;
  3. `python3 scripts/gateway_admin.py kill`, which stops every route.
- **Earliest possible open:** Tuesday Oct 6, 13:30Z, for cohorts that begin practice on Oct 1 (sessions Oct 1, 2 and 5).
  B2 is live with Release B.

**L1, the cohort keep** (Release B, #445; `league/swarm/tournament.py`, `league/swarm/practice.py`; research side). So
that a family is still alive when its cohort's sample is complete, the tournament spares a living Gym family with an
active practice cohort. It is spared the revision, evaluation and idle rules, and the idle pass, until the cohort
completes, fails or reaches its session window.
- **The record it reads** is the cohort's realized record before today, under its own evaluator. Until the cohort meets
  the incubator's sample (3 sessions, 10 program closes), it is kept whatever that record says. After that, it is kept
  only while program-closed P&L and all-closes P&L are both at least 0.
- **Not kept:** a cohort the House has not practised on 2 sessions while it practises others, or one whose practice row
  began before it.
- **At most `tournament.incubator_keep_max` (12) families;** 0, null, a boolean or a string turns it off. Those that
  meet the sample come first, by return on risk.
- **The incubator's cohorts come first and are never cut by the cap** (Release B', `tournament.incubator_held`). These
  are cohorts that met the sample with a record that is not negative, and whose program the swarm's own incubator
  facts admit (`bands.incubator`, the reader the House pins by). Every cohort the House can pin (L2', at most 8) is one
  of them. The swarm never reads the House's live state, so it cannot see which ones were pinned and holds them all
  (at most 96). So the keep never holds fewer families than the House can have pinned, and a pinned family is never
  retired because a cohort with a higher return took its place. If the facts cannot be read, every cohort past the
  sample is held for that read. The saved keep (`cohort_keep`) lists them under `held`, and a fresh process whose
  first read fails keeps those families first, beyond the cap.
- **What it never spares:** the deflated-Sharpe rule, the population floor, and the operator's gate hold.
- **The keep waits for retirement** (Oct 9, `Researcher.cohort_kept`): while the saved keep holds a family, its
  researcher's `retire` is not offered and a call is refused (guard `cohort_keep`), the mechanism test's retirement is
  deferred, and the diagnostician's retire defers as for pending evidence. The incubator pins only a living family's
  cohort, so a retired family's cohort practises on but can never trade. Before this, researchers retired three of the
  twelve cohorts' families within four hours of T0 (megacap-post-earnings-drift-single at 02:11Z Oct 9, its kept
  version 8 freshly passing the drift screen). A held family is parked at no cost until news, so the keep costs
  research nothing while the researcher has no idea to test.
- **Its record:** one private `swarm.status` event a round (`incubator_keep`), with each kept family, the rule it was
  spared, and `held`, the incubator's cohorts' families, when there are any.
- **The researcher's status line.** The keep is saved (`cohort_keep` in the swarm's kv), so a kept family's researcher
  is told that idleness is no reason to retire it, and that retire waits for the cohort.
- **An unreadable record.** When `observe.sqlite` or the swarm's families cannot be read, the last good keep stands for
  an hour (`KEEP_STALE_SECONDS`), then none does, with one alert in the round's event. A fresh swarm process (a deploy,
  a restart, the induced-failure kill test) runs its idle pass at once; if its first read fails, it takes the keep the
  last process saved (`cohort_keep`, read `stale` in the event) for the rest of that hour and does not overwrite it
  before then, so a restart never retires a kept family on one failed read.
- **Research attention only:** no trial count, look, validation, gate, band or money rule reads it.

**Turning real money on** (M4b; the sprint's R2; done: the grant was enabled at 00:30:15Z Sept 27, re-ratified at
$1,473.11 after the deposit and on `a3e2aa7c` at R7): the gateway deployed first (`OPTION_STRUCTURES_REAL`
`debit_vertical,long_butterfly,long_call,long_put`, `MAX_ORDER_EQUITY_SHARE` 0.25); then the owner deploy with
`real_money` true (a new money digest); `python3 scripts/live_trading.py --enable` (first time), then `--ratify`
within a minute. Then the House promotes Candidates that qualify to Probe within five minutes (`live.band` rows). Real
entries still require the paper route proofs' witnessed round trips.

### Pre-open (each trading day, 12:00-13:25Z; first run Sept 28)

From the A1 deploy the House runs its own `preopen` job an hour before the open (`league/ops/preopen.py`: release,
grant, gateway caps, account and kill switch, swarm, bands, mirror, backup, compute; read-only, each FAIL a House
warning, every line in the receipt). Its expectations are what the running House says they should be, not one day's
runbook, and a Sail guard braked by the budget's own daily cap alone is a pass (**The House's jobs**). The list
below is the owner's own fuller check, for a day with a deploy or a doubt; outside the unattended clock it may be run as
before.

1. **The box** (`python3 scripts/floor_box.py status`, then on the box): the loop and supervisor up;
   `health.json` `options_live.summary.state` is "before the open", `options_live.instances` lists every
   Candidate's shadow instance and every Probe's real one with no `error`; `/workspace/.venv/bin/python -c
   "import numpy"` works; `live-decider.log` has no traceback; `release` is the release you expect.
2. **The account** (through the gateway, reads only): equity, `last_equity`, `options_buying_power`,
   options level 3, multiplier; no open order; positions only the LTC dust (0.000373062); whether the
   deposit has landed (a `CSD` activity).
3. **The grant**: `python3 scripts/live_trading.py` on the box: `active` true, `constitution_digest` equal
   to the running release's money digest, capital = min(equity, `live_trading.ceiling_usd`). A deposit
   that landed: `--ratify` now (capital follows it up to the ceiling; above the ceiling is the owner's call).
4. **The gateway**: `python3 scripts/gateway_admin.py status`: `kill_switch` false; `max_loss` shows a
   fresh equity reading (it reads the account on the first open if stale), the per-order cap = the lower of
   $1,000 and 25% of equity, today's opening maximum loss 0 of 100% of equity; `caps.max_day_orders` 300; the
   deployed `OPTION_STRUCTURES_REAL` is `debit_vertical,long_butterfly,long_call,long_put`.
5. **The live state**: `python3 -m league.live --root /workspace/state`: `stops` not tripped (no
   `drawdown_tripped`), `reconciliation.frozen` empty, no `assignment_latch`, `paper_proof` absent or
   `passed`, no working orders, no open real positions but the ones expected.
5b. **The sprint's checks**: `health.json` `options_live.fill_model` names the refitted model (its `source`
   and `version`; `GYM_FILL_MODEL` or `/data/calibration/fill_model.json`, loaded once at the House's start);
   `options_live.observe.switches` shows observe on and calibration as intended; `swarm.json` reads as a
   JSON object; after 13:30Z `options_live.observe.pins` lists the session's families with their `tiers` and
   `roots`, and `options_live.observe` shows `roots_used` under `roots_max` and `effective_cap` (no `shed`);
   `observe_reads_skipped` stays 0 and `budget_spent` {}; `observe.sqlite` `practice` has a row per pinned family and
   version; `live.sqlite` has no `:o` order, position or instance and `swarm.sqlite` `forward` no `:o` id; after the proofs,
   `paper_proof_single` passed; after 14:00Z `options_live.calibration.slots` and
   `python3 -m league.live --root /workspace/state --calibration`; `options_live.house_test`: `files`
   verified, `wanted` as intended, and no stop or end you did not expect; from Release B,
   `python3 -m league.live --root /workspace/state --incubator` (the switch as intended, the pins and first looks,
   the tally within its caps, no weekly stop you did not expect) and no `:i` id in the swarm's `forward`.
6. **The Probe list**: `live.band` rows since the last session (who became Probe or Sized and why; who
   stayed a Candidate and why: not through the holdout, a type real money does not open, a credit type
   under $2,000, a typical structure over the Probe's cap or unknown). It must match the run record's list.
   Bands move only while real money is on and the grant active, and a family moved onto real money trades
   from the NEXT session: only families promoted before the open trade that session.
7. **The day**: a full session or a half day; any FOMC, CPI or jobs release; which admitted roots have
   0DTE expiries. No deploy from 13:25Z to 20:05Z except a rollback.
8. **At the open** (13:30-13:45Z): the paper proof (`live.paper_proof` "passed" in the ledger by about
   13:40Z; if "failed", read `paper_proof` in the live state and the proof's events before anything else);
   then the first real orders (`live.order`), the refusals (`live.refusal`: each says which rule), the day's
   order count against 250, `reconciliation.frozen` staying empty. Watch every 30 minutes: fills against the
   Gym's expectation, the stops, the index 0DTE cutoff actually enforced by the venue at 15:00 ET.
9. **To stop real money at once**: `python3 scripts/gateway_admin.py kill` (exits stop too; release with
   `unkill` from the owner's machine). `live_trading.py --disable` revokes the grant for good: not for a pause.

## Recover

- **The House is not ticking.** `floor_box.py status`: if a stop file is set and nobody meant it,
  `start`. The gateway's outside watchdog (every five minutes) runs `/workspace/restart.sh` when the
  production checkpoint is over 30 minutes old (at most once in 30 minutes) and resumes a paused or
  sleeping House box when Sail credit is above $10. It acts only once the site has a checkpoint:
  while the checkpoint route answers 404 it touches nothing.
- **Sail credits ran out.** Every box pauses, the House included. The owner tops up; then
  `floor_box.py resume` and, if the loop is down, `start`. The swarm's Sail guard is meant to stop
  the Gym and the researchers well before this.
- **A release was refused or rolled back.** Read the reasons in `deploys.jsonl` (or `logs
  --deploy`), fix the defect with a test, deploy again. When the canary's error is one any fresh House would tell on
  its first tick, the defect is that notice's level, not the release, and nothing can land until it is fixed
  (**Deploy**, "A canary is a fresh House").
- **`options_live.blocked` reads "the account could not be read this minute" after a restart outside the session.**
  Off-session the live path reads the account only on its quiet pass, every 15 minutes, and a restart forgets the last
  reading. The block clears at the next quiet pass with no command. In the session the account is read every minute,
  so the same words there mean the read itself failed.
- **The grant reads inactive.** The money digest moved: ratify (above).
- **"publishing failed (... HTTP 400 {"error":"Invalid checkpoint."})".** The site refuses the whole
  checkpoint for one field it does not allow, and the page keeps the last one it accepted. Rebuild
  the body the House would post from `/workspace/state` (read-only) and run the site's validators
  (`capital/schema.js`) over it to find the field. Widen a bound on the site first and deploy the
  site before the House.
- **"positions table: ..." warnings.** The positions table and Profit are read from the live book and the
  account's own activity (`league/account_activity.py`). Each reason the table does not reconcile is said
  once: a fill or a fee on an order the live book does not hold (an owner's trade by hand, a lost answer),
  a finished order whose fills at the broker differ from the book's, an option event on a contract the book
  never held, a cash event the book never counts, the broker's cash for an assignment, an exercise or an
  index expiry the book settled against the book's own value, an activity of an unknown type; and "the
  table carries an unreconciled X", the line the page shows beside the rows. Nothing is hidden: fix the book
  or classify the type, and the line goes back to 0.00. Profit shows a dash (said once) while shares an
  assignment left are held, while the book has not taken an assignment, and while a broker fill on a
  contract the book still holds is unmatched. "position real:N cannot be described" or "open position
  real:N is not listed": the row is counted in the page's not-listed line. "could not be read": Profit
  shows a dash ten minutes after the last good reading (a restart keeps the last reading).
- **Sail's checkpoint API is down.** The House's backup fails as a marked vendor error (one error,
  then warnings at 30 min, 1 h, 2 h, 4 h, then every 6 h) and never rolls a release back. The post-close
  checkpoint (release U) fails as a warning each try, on the same backoff, while the evening lasts. The images
  have two checkpoints each and `images.py` rebuilds them.
- **The House box is gone (a spot interruption, a dead disk).** Fork the newest named checkpoint of the House box
  (`floor_box.py fork`, the loop stopped): `league-YYYY-MM-DD-close` (taken after each session's close since release
  U) or `league-YYYY-MM-DD` (the daily one), whichever is later. Oct 14, 2026: an AWS spot interruption at 20:12Z left
  only that morning's 13:28Z checkpoint, before release U.
- **The data box's session was kicked or the backfill stopped.** `box.py status`, then `box.py
  start`: it resumes from its journal. A night's forward pull that failed: `nightly.py run` again.
- **A structure is left on the real account.** The gateway admits a close of any defined-risk type
  once the account holds every leg, whatever `OPTION_STRUCTURES_REAL` says; close it with one
  multi-leg order. Legging out is a last resort. An assigned short leg becomes shares: an OPASN or
  OPEXC activity latches `assignment_latch`, which freezes real entries, and the owner is told. The
  House closes the shares at once (the gateway admits a sale of shares held long and a cover of shares held short, at
  most what is held; since Oct 10 also listed long-only buys, `STOCK_BUYS_REAL`, never a short sale) and
  closes the structure's other legs alone. The latch lifts by itself once no broken structure and no
  shares remain and reconciliation is clean; `python3 -m league.live --root /workspace/state
  --clear-assignment` lifts it by hand.

From Release A:

- **The error alert "live: `<key>` is not a real instance and asked for a real order: refused"** (#437). A bug put a
  non-real instance (a practice `:o` shadow, a Candidate's shadow, or an instance whose observe flag is not False) on the
  real order path. The belt refused it before anything reached the venue, so nothing was sent.
  - Treat it like a reconciliation error: read that instance's `live.refusal` rows and the live state
    (`python3 -m league.live --root /workspace/state`).
  - Do not switch anything on to make it go away.
  - It repeats once per intent a minute while the bug stands, loud on purpose.
- **"the production decider requires a network namespace under its separate uid; the namespace probe failed ..."**
  (#443). The root House could not make a network namespace for the decider child in time, so the spawn was refused.
  - This is not cached: the next spawn at least 30 s later probes again.
  - One such line on a busy minute needs no action.
  - If it repeats for several minutes, real instances will be orphaned and closed after five. Check the box's load, and
    that unprivileged network namespaces work for uid 65534: the probe runs `unshare --net --map-root-user true` as
    that uid. A House restart does not fix a box that refuses namespaces.
- **"generated programs run only as uid 65534 in a private network namespace (a root House)"** (#443). A `Decider` was
  built off a root House. On the House it means the House is not running as root; fix that. It never runs generated
  code unisolated.
- **A Gym result `refused` with "the program does not compile" or "the program fails to load"** (#440). It is the
  program's own code, for example code that parses but that the compiler refuses. Admission now refuses such code with
  its line, so the family's researcher sees the reason and fixes it.
- **A Gym result `error`** (#440), 0 trials, with any of these reasons:
  - "the program failed to load in its worker";
  - "the program failed to start";
  - "the program's run stopped on an error".

  It names an engine-side exception on that one program. The other programs in the batch are unaffected, and their
  results are what they would be alone. Look at it as a possible engine bug, and keep the reason text: it is the only
  signal.
- **`pool.batch_failed`** (Release A). It should now mean box, transport, deadline or memory trouble: a dead worker, the
  unit deadline or a `MemoryError` still fail the whole unit. It should no longer mean one bad program. A timed-out or
  dropped download of a finished result is retried inside the driver's attempt limit before the batch is requeued
  (#436).
- **"swarm: funding: ..." warnings** (#439): a funding cliff ahead. The next section, **Funding cliffs and alerts**,
  explains them. They are warnings, never errors, so the watchdog never rolls a release back over one.
- **"the site refused the practice league block or Claude's own compute part ..."** (#441). The site predates
  personal-site PR #17. The House sent it the older shape: no practice block, and Claude inside `other_usd`. It offers
  the newer shape again in 30 minutes. Deploy the site; nothing is lost.
- **"the site refused the swarm window ..."** (the swarm window, Oct 1, 2026). The site predates the window (personal-site
  `capital/swarm-window`), or it refused an entry. The House sent the checkpoint without `levels` and `rationale` and
  offers them again in 30 minutes. Deploy the site; nothing is lost. If the deployed site should take it, read the reply
  the warning quotes; `curl -s 'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1&practice=1&window=1'`
  shows what the site serves.

From Release B:

- **"live: `<key>` is not a real tuition incubator instance and asked for a real order: refused"** (error). A bug put an
  `:i` instance that is not a real, tuition-flagged one on the real order path, or a non-`:i` instance claimed the
  route. The belt refused it before anything reached the venue. Treat it like the observe belt's alert above: read the
  instance's `live.refusal` rows and `--incubator`, and switch nothing on to make it go away.
- **"live: the incubator's facts could not be read (...)"** (warning, once). The swarm store could not be read, so no
  incubator pin or open happens until it can; exits are unaffected.
- **"live: the incubator could not read the practice cohorts; no first look and no new pin until it can"** and **"live:
  the incubator's first looks failed (...)"** (warnings). That pass takes no first look; the practice league goes on
  under its own rule.
- **"live: the incubator's pins failed (...)"** (warning). That pass wants no incubator instance, so its instances go to
  exits only until a pass succeeds.
- **"live: swarm.json live.incubator is X, not true or false: the incubator reads OFF"** (warning, once). Fix the value.
- **"live: the incubator its net realized loss this week reached $X, at or over $150: stopped for the rest of the week
  (exits go on)"** (warning, once a week). The weekly stop latched, as designed. It lifts at the next ISO week; nothing
  is to be done.
- **A library call refused with `cap` or `busy`** (in `swarm.research` events). `cap` means the gateway's day of arXiv
  requests (`LIBRARY_DAY_UPSTREAM`) or a House line is spent; `busy` means arXiv's one-at-a-time queue was full. Both
  are plain refusals. A long run of `busy` or a `backoff_until` in `/v1/research/health` means arXiv asked us to slow
  down: leave it.

## Funding cliffs and alerts (Release A, #439)

The swarm says each funding cliff ahead of time (`league/swarm/funding.py`, `FundingWatch`, on the swarm's main loop
right after the Sail guard's reading). It changes no route, line, hold or guard decision. These are House alerts on
hours of runway; from A1 the owner's mail about a card is the budget rule's `funding` notice, on 60 days (**The budget
rule**, under **Running unattended**). Claude's cliff reads the funded room only: the budget's daily Claude line runs
out every day by design and is not a cliff. From the self-running release, research that stalls (no births, too few Gym
runs, no Validation, a guard braked most of the day, a meter under three days of research, an owner deploy waiting, a
pause left on, a refused grant, the kill switch on) is mailed too, as a `stall` notice (**The stall alarm and the funnel**, under **Running unattended**).

| Cliff | Measured as | Leads: notice / warning / urgent |
|---|---|---|
| Claude's room (`claude_room`) | runway: the room above `claude.reserve_usd`, less `funding.claude_out_usd` ($2), over the measured burn | 48 / 24 / 6 h |
| The Sail guard (`sail_guard`) | runway to the guard's brake line, from the guard's own reading | 72 / 24 / 6 h |
| The OpenAI month (`openai_month`) | calendar: the next UTC month boundary, while the gateway's frontier month has room | 48 / 24 / 6 h |
| (retired in A1) The burst's end (`burst_end`) | said by the releases before A1; gone in V3-A part 1 with the burst: the Sail guard's daily cap is the budget rule's | - |

**Burn.** The measured burn is the larger of the last 24 hours' and the last `funding.burn_window_hours` (6) hours'
rate. It comes from the swarm's booked spend and from the meter's own fall between samples taken every ten minutes. A
top-up is a rise, never negative spend. Because it takes the larger rate, the runway errs early: right after a pace cut
it looks shorter than the new pace implies.

**Tiers:** notice, warning, urgent, then out once the cliff is here.
- **Rises:** a rise to a tier not yet said is said at once. Warning, urgent and out repeat every `funding.repeat_hours`
  (12) while they stand. A calendar cliff's out is said once.
- **Falls:** a fall is silent. A fall of two tiers or more (a top-up) makes the tiers above it news again.
- **Recovery:** a recovery past `funding.clear_factor` (1.5) times the first lead is one `funding_ok` event, and the
  cliff is forgotten.
- **No burn:** a runway with no burn measured is shown as state `no burn`, with no tier. It neither clears nor repeats
  an alert.
- **Sail braked:** while the Sail guard is braked and its balance is under its release line (the line plus
  `guard.release_margin_usd`), the Sail cliff stays out, with state `braked`.
- **Restarts:** what was said is kept in the swarm store, so a restart repeats nothing.

**Fallbacks.** Every call that asked Claude and ended somewhere else (the next route, Sail, or no route) is counted by
role, Claude failure kind and route.
- Each key is said the first time it appears as a `claude_fallback` event, then at most every 6 h with the count since.
- Only `no_room` (a funding cliff) is an alert.
- A role's own daily line (kind `line`, such as the architect's $0 line since Sept 30) and errors are events without an
  alert.

**Where it shows:**
- **Swarm events:** `swarm.status` events with `action` `funding_alert` or `claude_fallback` (and `alert` true only for
  alerts), or `funding_ok` for a recovery.
- **The House:** the House mirrors them into its private ledger and turns each alert into an `ops.alert` at level
  warning, reading "swarm: funding: ...". `scripts/floor_watch.py` shows it.
- **The heartbeat:** the last assessment of each cliff (tier, hours, room or balance, burn, projected time) is under
  `status.funding` (`python -m league.swarm status --root /workspace/state`).
- **The site:** nothing is published, and no key, account number or secret is read.
- **Swarm store keys:** `funding_alerts`, `funding_fallbacks`, `funding_samples` and `funding_openai_seen`.

**Settings.** Set them in `swarm.json` `"funding"`, read every tick, with no deploy:
- `enabled` (true);
- `every_seconds` (300);
- `fallback_flush_seconds` (30);
- `lead_hours`, keyed `claude_room`, `sail_guard` and `openai_month` (`burst_end` is gone with the burst);
- `repeat_hours` (12);
- `clear_factor` (1.5);
- `claude_out_usd` (2);
- `burn_window_hours` (6);
- `after_end_hours` (48: a calendar cliff older than this is not announced);
- `fallback_every_seconds` (21600).

A value that is not a finite, non-negative number is its default. On a gateway hang, the check's meter refresh can hold
the swarm's loop for up to the meters' 20 s timeouts, at most once every 5 minutes.

## Switches

**Where a setting lives** (**The settings layers**, under **Running unattended**). The releases before A1 read
every research row below from `swarm.json` on the box and nowhere else. This tree also holds them in
`league/swarm/policy.json`, with the box's values as of 21:00Z Oct 2. Since the A1 deploy both are read and the box's
full file still wins, so the "Now" and "How it changes" columns stay true: an edit of `swarm.json` on the box takes
effect with no deploy and outlives every release. A change to `policy.json` is a reviewed pull request and then the
owner's deploy (the file is protected: the updater ships no change to it), and it takes effect only for keys the box's
file does not set, that is once the reduced `swarm.json` is installed (**The A1 deploy**, step 5). The budget rule then
tightens the result. The rows that stay only in `swarm.json` on the box are the owner's switches (`enabled`, every
`live.*` row) and the private agenda (`architect.agenda`, `architect.agenda_locked`). `scripts/settings_migrate.py`'s
`--swarm-out` file keeps the switches only: the two agenda keys are added by hand and the result is checked before it
is installed (**The settings layers**, "The reduced `swarm.json`").

| Switch | Where | Now | What it does | How it changes |
|---|---|---|---|---|
| `real_money` | `league/config.json` | true (since R2, Sept 27) | real orders at all | owner deploy |
| `auto_update` | `league/config.json` | true on the box since the A1 deploy (08:49Z Oct 3; off from Sept 26 until then) | the in-box updater: main's head deployed through its walls (**Deploy classes**); a missing key means off | owner deploy |
| `live_trading.ceiling_usd` | `league/config.json` | 5500 | the grant's capital ceiling | owner deploy; the standing grant ratifies a raise after it (`--ratify` if it refuses) |
| `performance.start_at`, `start_equity` | `league/config.json` | 06:25:30Z Sept 26, $481.65 | the profit baseline; equals the site's `PERFORMANCE_START_AT` | only with a site reset |
| `gym.enabled`, `swarm.enabled` | `league/config.json`, overlaid by `swarm.json` | false in `config.json`; true in `swarm.json` | the Gym and the swarm in the House's tick | edit `swarm.json`; a change of `enabled` takes a House restart (`config.json` `swarm._about`) |
| `swarm.json` | `/workspace/state/` on the box | present, mode 600; the full file until the reduced one is installed (the migration tool's output plus the two agenda keys by hand: **The settings layers**) | the owner's switches (`enabled`, `live`) and the private agenda, over `policy.json`; re-read every loop (the live path each minute), no deploy; never the evidence lines | edit it on the box, keeping a before-copy |
| `league/swarm/policy.json` | the repository (in every release from A1) | the research settings, the box's as of 21:00Z Oct 2 | the swarm's throughput and research settings as code, between `config.json` and `swarm.json`; never `enabled` or `live` (ignored there, with one alert); a malformed file is ignored whole, with one alert | a reviewed pull request, then the owner's deploy (protected: the updater ships no change to it) |
| `budget.json` | `/workspace/state/` on the box | absent until the `budget` job's first run (00:30Z Oct 4), with the floor in force; written by the `budget` job | the budget rule's research dollars a day, applied last and only to tighten; missing: the floor; older than 36 h: never looser | the rule alone (`league/ops/budget.py`, owner deploy); never by hand |
| `ops.json` | `/workspace/state/` on the box | the owner's private file, read from A1; absent, every job runs and no external cost is declared | the House's jobs: `enabled` false stops them all, `jobs.<name>.enabled` false one; `economics.external` (the owner's declared external costs, `complete` true when the list is whole: undeclared, the close economics lists them as unknown, never zero), `hygiene.end_retired_cohorts` | edit it on the box (a command on the box) |
| `sail_fallback`, `sail_fallback_same_model` | the code's defaults (neither `policy.json` nor the box sets them) | `{"k3_balanced": "pro_asap", "pro_balanced": "pro_asap"}`, `["audit"]` (from A1) | the window fallback of a one-shot Sail call: a poll timeout on a balanced profile retries once on the mapped asap profile and flags the window stalled for an hour (kv `sail_window_stall`); the listed roles keep their own model's asap profile; null turns it off | edit `swarm.json`, or `policy.json` by the owner's deploy |
| `options_structures.book`, `practice_account` | `league/config.json` | options-shadow, false | which book structures practise on | owner deploy of a release changing only that key |
| `PAUSE` | `/workspace/state/` | absent | the maintenance pause | `floor_box.py maintenance` |
| `STOP`, `state/STOP` | `/workspace/` | absent | the loop ends | `floor_box.py stop` / `start` |
| `swarm.stop` | `/workspace/state/` | absent | the swarm process leaves and is not restarted | create / delete it |
| Kill switch | the gateway | off | every real order-creating call refused | `gateway_admin.py kill` / `unkill` |
| `MAX_ORDER_MAX_LOSS_USD`, `MAX_ORDER_EQUITY_SHARE`, `MAX_DAY_EQUITY_SHARE`, `MAX_DAY_ORDERS`, `MAX_DAY_OPEN_ORDERS` | `gateway/wrangler.jsonc` | $1,000, 0.25, 1.0, 300, 250 | the real account's caps by maximum loss; equal to the constitution's `options_money.gateway` | gateway deploy with the matching House deploy |
| `OPTION_STRUCTURES_REAL` | `gateway/wrangler.jsonc` | `debit_vertical,long_butterfly,long_call,long_put` | the types real money may open; must equal the constitution's `options_money.real_types` (`league.ci`) | gateway deploy with the matching House deploy and a ratify |
| `STOCK_BUYS_REAL` | `gateway/wrangler.jsonc` | `on` on `feat/gateway-stock-opens` (not deployed; production admits stock closes only) | long-only buys of `STOCK_UNIVERSE` on the real account; anything but `on` admits none (closes go either way) | gateway deploy |
| `STOCK_ETF_EQUITY_SHARE`, `STOCK_SINGLE_EQUITY_SHARE`, `STOCK_MAX_EQUITY_MULTIPLE`, `STOCK_DAY_EQUITY_MULTIPLE` | `gateway/wrangler.jsonc` | 0.5, 0.2, 2, 4 (the code's ceilings) | an ETF position, a single-stock position, the whole long book as a margin line (x min(this, the account's multiplier), long options counted at that multiple), the day's stock buys, as shares or multiples of the gateway's own equity reading; a value can only lower them | gateway deploy |
| `LIBRARY_DAY_UPSTREAM`, the `LIBRARY` KV binding | `gateway/wrangler.jsonc` | 600; namespace `ltcm-gateway-library` (Release B) | the research library's requests to arXiv a UTC day for the whole floor (`"0"` stops them; cache hits still answer), and its cache | gateway deploy; never delete the namespace |
| `live.observe`, `live.observe_max` | `swarm.json` on the box | true, 48 (since 13:36Z Sept 29) | the practice league (the observe band) and its instance cap (default 48); read each minute, no deploy (a swarm.json that is not a JSON object turns it off) | edit `swarm.json` |
| `live.observe_train`, `live.observe_roots_max`, `live.observe_read_calls` | `swarm.json` on the box | defaults: true, 24, 120 (120 from V3-A part 1; 40 before) | the Train tier; the distinct roots the league may read (1-128); the minute's data calls before observe reads stop (10-200; unset: the step's own 120, room for 24 roots at the page cap after the real phase's 20); only a read skipped for this budget sheds practice instances | edit `swarm.json` |
| `practice.feedback`, `sessions`, `bonus`, `bonus_total`, `min_trades` | `swarm.json` on the box | defaults: true, 10, 0.25, 0.10, 3 (from Release A) | the practice league's research feedback: the strategist's table, the architect's lines, the share bonus (code ceilings 0.5 and 0.2); off: none of the three | edit `swarm.json` |
| `live.calibration`, `live.calibration_samples` | `swarm.json` on the box | true, 100 | the D3 round trips (still only with real money on, the grant and the paper proof); samples a symbol's open cell (the mid, or the patient mid at 12:00 and 14:00) stops at (defaults false, 30) | edit `swarm.json` |
| `live.house_test` | `swarm.json` on the box | true (since 00:17:28Z Sept 29) | the House live test (still only with real money on, the grant, the paper proof and its private program verified); off: exits only | edit `swarm.json` |
| `live.incubator` | `swarm.json` on the box | true (since 04:01Z Oct 1); default false (Release B ships it off) | the incubator (still only with real money on, the grant, a passed first look and the swarm's facts, which B2 writes); only JSON `true` is on; off: exits only, working opens cancelled within a minute; first looks are recorded either way | edit `swarm.json`, and switch on only outside a session |
| The House live test's program | `/workspace/state/house-test/rebound-live/` on the box | present, verified | the frozen program and its params, hash-checked against `league/live/house_test.py` `FROZEN` | the operator's private upload script, `--apply` |
| `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD`, `FRONTIER_FUNDED_MONTH` | `gateway/wrangler.jsonc` | $707, September 2026 only; not topped up again (the owner, Sept 29), so $0 from Oct 1 | the OpenAI month; expires before an unfunded month can renew it | gateway deploy |
| `CLAUDE_USD`, `CLAUDE_MODELS` | `gateway/wrangler.jsonc` | $265 (since Oct 1: the owner topped the account up to a $100 balance against $165.26 spent; $200 from 05:29Z Sept 29); Opus 5.5, Sonnet 5, Sonnet 5.5 | the Anthropic account's funded total (never resets) and the priced models (the allowlist) | gateway deploy after the owner adds funds |
| `claude.model`, `claude.usd_cap`, `claude.max_tokens` | `swarm.json` on the box | `claude-sonnet-5-5` (since 04:53Z Sept 29), 263 (since 20:33Z Oct 1; 198 from 05:29Z Sept 29), 32000 | the swarm's Claude model, its own lifetime Claude line inside `CLAUDE_USD`, a call's output ceiling (defaults `claude-opus-5-5`, 100, 16000) | edit `swarm.json` |
| `claude.roles`, `claude.role_usd_day`, `claude.role_model` | `swarm.json` on the box | architect, audit, diagnostician, rewrite, review, researcher, strategist; lines: architect $0 (since 11:54Z Oct 2; $5 at 20:33Z Oct 1 to 00:06Z Oct 2, 06:09-06:51Z and 11:38-11:54Z Oct 2: 0 births in its 4 Oct 2 passes; $0 from 16:41Z Sept 30), rewrite $0, researcher $0, review $5, strategist $6, diagnostician $6; audit on `claude-opus-5-5` (since 04:53Z Sept 29) | who asks Claude first; a role's own Claude line a UTC day; a role's own Claude model (defaults since PR #417: architect, audit, diagnostician, researcher; the researcher $100; the researcher on `claude-sonnet-5-5`; the box's `roles` list replaces the default, so the box's research band is off until "researcher" is added to it) | edit `swarm.json` |
| `researcher.claude_top`, `claude_effort`, `claude_max_tokens`, `claude_hold_every` | `swarm.json` on the box | 0 on the box (the band is off); defaults: 12, `medium`, 12000, 3 | the top band on Claude (PR #417): how many of the top families by allocation share, at what effort, each call's output ceiling (it sizes the hold), and how often Claude looks during a hold streak (1: every cycle) | edit `swarm.json` |
| `researcher.claude_family_usd_day`, `claude_min_room_usd`, `claude_timeout_seconds`, `claude_breaker_failures`, `claude_breaker_window_seconds`, `claude_breaker_pause_seconds` | `swarm.json` on the box | defaults: $15, $25, 180, 3, 3600, 3600 | the band's fuses: one family's Claude a UTC day, the funded room left to the other roles, one call's limit, and the breaker (unknown bills in the window that pause the band, and for how long) | edit `swarm.json` |
| `gate.review_openai_model`, `gate.audit_openai_model` | `swarm.json` on the box | null, null (since 04:53Z Sept 29) | the review's and the audit's OpenAI route; null skips it (defaults `gpt-6-sol`, `gpt-6-astra`) | edit `swarm.json` |
| `gate.look_holds` (`drift_share`, `min_power`) | `league/swarm/policy.json` (null since fast lane v2, Oct 7, 2026: both holds off); `swarm.json` on the box must not set it | default `{"drift_share": 0.25, "min_power": 0.30}` (the owner, Oct 2, 2026) | THE LOOK HOLDS: hold a holdout look at a long-delta version whose Train drift share is at least `drift_share`, or whose expected holdout power at the next look's Holm level is below `min_power` (the look holds, in the gate's section below). A key null turns that hold off, `look_holds` null both; a value that is not a number from 0 to 1 reads as its default | edit `swarm.json` |
| `architect.openai_model`, `every_seconds`, `refill_seconds`, `max_refill`, `max_output_tokens` | `swarm.json` on the box | null, 7200 (since 17:04Z Oct 2; 1800 from 02:47Z Oct 1; 900 before; from A1 the budget rule makes it, and the refill, every 4 hours or slower at the floor), 1200, 6 (since about 14:00Z Oct 1; 12 from Release A, Sept 30), 32000 | the architect: null leaves it Claude first (its Sail profile, `architect.sail_profile`, as the fallback, and its route while `claude.role_usd_day.architect` is 0); its cadence, its refill below `population.start` and each pass's births (defaults `gpt-6-astra`, 14400, 3600, 12, 12000) | edit `swarm.json` |
| `architect.sail_effort` | `swarm.json` on the box | `high` (since 12:54Z Oct 2; `medium` 11:38-12:54Z Oct 2; `high` from about 14:00Z Oct 1); default `medium` (Oct 1; before it, `high` was hard-coded) | the architect's reasoning effort on Sail (its `architect.sail_profile`) and OpenAI; Claude's is `claude.role_effort` / `claude.effort`. One of `minimal`, `low`, `medium`, `high`, `xhigh`; anything else reads as `medium`. At `high`, from 08:15Z Oct 1 every pass spent the whole 32,000-token output on reasoning and came back cut, most with no text; the same request at `medium` completed in 66 s with 12 carded families. A cut Sail answer is salvaged like a Claude one (its complete families born, fewer than 3 buy the one retry on Claude alone), and the pass's `swarm.architect` event says its `effort`, its `usage` (input, cached, output and reasoning tokens) and, when cut, its `incomplete_reason`. At `medium`, k3 sometimes writes stray trailing commas (`,}`, `,]`) into a complete answer; when the strict read finds no `families` array and the families object has such a comma, the architect reads it again without them, from the `{` that opens that object (`read_families`; the event says `lenient`), where before it read as no proposals (11:57Z Oct 1). A complete answer whose families array still does not parse whole (15:59Z Oct 1: a stray `}` after the fourth and the fifth of six families, and the pass read as no proposals) is read object by object, each family decoded from its own `{` and the stray closers and commas between the families skipped, never outside the array and nothing inside a family changed beyond the strip (`recover_families`: an object that does not decode whole is passed over, never entered or kept truncated; the event's `recovered` says how many and why, and `passed` the objects passed over). An answer with no readable family still reads as none (the CHANGELOG, Oct 1, has the history) | edit `swarm.json` |
| `population.start`, `ceiling`, `floor` | `swarm.json` on the box | 16, 96, 8 (since 17:04Z Oct 2; 96, 96, 12 before); from A1 the budget rule caps the ceiling (a family a dollar a day, at least `floor` + 4) and holds the start to it | the refill target, the most alive, the fewest retirement may leave (defaults 48, 96, 16) | edit `swarm.json` |
| `gym.start_boxes`, `max_boxes`, `train_from`, `image_checkpoint`, `gate_checkpoint` | `swarm.json` on the box | 2, 1 (since 17:23Z Oct 2; 6 from Release A, 2 from 17:04Z Oct 2; from A1 the budget rule may cap it, never below 1), "2020-01-02", the sealed 2020-24 image, its gate partner | the Gym pool, Train's first day and the images (defaults 4, 8, unset, none, none: the gate is off without a gate image). `train_from` takes "2022-01-03", "2020-01-02" or (since R11a) "2017-01-03"; the derived split and time limit are 8 and 900 s, 16 and 1500 s, 24 and 2400 s | edit `swarm.json`; `train_from` and a new image together |
| `researcher.sail_usd_per_hour`, `usd_per_hour`, `top_families` | `swarm.json` on the box | 0.25 (since 17:23Z Oct 2; 0.4 from 17:04Z; 1.3 from 02:47Z Oct 1; 1.1 from 16:41Z Sept 30; 12 before), 5 (not read while the Sail pace is set), 0; from A1 the budget rule caps the pace (Sail research × 0.4 / 24) | the researcher pace (below) and the top band by allocation share (defaults null, 4.0, 10) | edit `swarm.json` |
| `researcher.retire_idle_evaluations`, `dormant_cycles`; `tournament.retire_revisions`, `retire_evaluations` | `swarm.json` on the box | 500, 12; 200, 4000 | the idle rule and its dormancy clause; the tournament's retirement (defaults 150, 40; 30, 2000) | edit `swarm.json` |
| `tournament.incubator_keep_max` | `swarm.json` on the box | default 12 (Release B, L1) | the most families the cohort keep spares from the revision, evaluation and idle rules (at most 96), beside the incubator's cohorts, which it never cuts (Release B'); 0, null, a boolean or a string turns it off | edit `swarm.json` |
| (retired in A1) `guard.burst_cap_usd`, `burst_until`, `after_burst_usd_day` | `swarm.json` on the box | $900 to 2026-10-05, still in the box's file; read by the releases before A1 and by no code since | the research burst; from A1 the Sail guard's daily cap is the budget rule's, and a file that still names them changes nothing. The guard's balance line (two days of the House's burn plus $30) is unchanged | - |
| `diagnostician.enabled`, `usd_day`, `per_round`, `family_hours`, `min_validations`, `near_miss_checks` | `swarm.json` on the box | false (since 16:41Z Sept 30), $60, 6, 3, 2, 5 | the diagnostician on or off; its Claude spend a day, families a round, how often a family, who is eligible (defaults true, $15, 2, 6, 2, 6) | edit `swarm.json` |
| `researcher.stall_revisions`, `rewrites_per_day` | `swarm.json` on the box | 10000 (since 16:41Z Sept 30: stall rewrites off; 12 before), 1 | the stall that buys a researcher one rewrite from a stronger model, and at most how many a family a day (defaults 5, 4) | edit `swarm.json` |
| `claude.role_effort` | `swarm.json` on the box | `{"architect": "medium"}` (since Release A, Sept 30; it matters only while the architect has a Claude line) | a role's own Claude effort when the caller names none (R11b; default `{}`: `claude.effort` for every role, so the gate keeps "high") | edit `swarm.json` |
| `architect.max_alive_per_class` | `swarm.json` on the box | default 12 (R11b) | the most living families of one mechanism class (structure x root group); `admit` refuses births past it; 0 or null off | edit `swarm.json` |
| `architect.cell_yield` | `swarm.json` on the box | default null: off (H2); null on the box (the owner, Oct 2: claims first; switching it on is the owner's decision, because open-cell restatements on another slice are born as fresh lineages) | the card check's yield-aware cells (**The cell's yield**, below). Null keeps every mechanism-verdict row needing a rebirth claim. `{"min_births": 30, "floor": 0.10, "lookback_days": 7}` (or `true`, the same) opens every cell except an exhausted one: at least `min_births` settled births in the lookback, with a Wilson 95% upper bound on their drift-pass share below `floor`. In an open cell a card that matches only self-refuted and drift rows needs no claim. A key that is missing or misstated takes its default | edit `swarm.json`; roll back with null |
| `architect.claimable_rows` | `swarm.json` on the box | default 0: off (H2); 4 on the box (since 05:26Z Oct 2) | the most rows a claim may name that the REFUTED CELLS list for each cell where a claim can be needed (at most 12; the newest rows that still have rebirth room, each with the inputs it read). Row ids and input names only, no figure | edit `swarm.json` |
| `architect.structures` | `swarm.json` on the box | default null: every type (Oct 1); `["debit_vertical", "long_single"]` on the box (since 15:22:15Z Oct 1; `"real"` before) | the structure types a birth may be. `"real"` reads the allocator's `allocation.real_structures` (one list for both, so a change of the account's real types is one edit); a list such as the gateway's real types (`["debit_vertical", "long_butterfly", "long_call", "long_put"]`) also admits `long_single` (a list must then change beside `allocation.real_structures`). The architect's and the strategist's GAPS and coverage show only these (a list naming one side alone makes that side a gap), the architect's request names them and its BIRTH QUOTAS show only their structure families, `admit` refuses any other type and the next request names each refusal still outside the list (kv `architect_structure_refusals`); the tournament forks and the loop's founding seeds and reseeds are only of these types, and a living family of another type keeps researching until a rule retires it. The pass's event: `structures`, `structure_not_allowed` by type, `structures_ignored` (a value naming no known type is ignored whole: every type) | edit `swarm.json` |
| `architect.sail_profile` | `swarm.json` on the box | `pro_asap` (DeepSeek-V4-Pro on the asap queue; since 12:49Z Oct 2; `pro_balanced` 12:28-12:49Z) | the architect's Sail route (default `k3_balanced`, Kimi-K3). From about 07:00Z to 12:53Z Oct 2 every architect request on Sail's balanced queue went unanswered past the 15-minute poll (`provider_poll_timeout`), while the researchers on the asap queue ran on; on `pro_asap` the next pass answered in 42 s | edit `swarm.json`; unset returns `k3_balanced` |
| `tournament.fork_top`, `fork_min_t`, `fork_cooldown_hours` | `swarm.json` on the box | 0 (since 05:03Z Oct 2), 1.0, 6 | each round forks the top `fork_top` families whose validation t is at least `fork_min_t` with a positive validation mean, each at most once every `fork_cooldown_hours` (defaults 3, 1.0, 6); 0 turns forks off, because forks re-mined one validated lineage and raised its deflated-Sharpe N | edit `swarm.json`; roll back with `fork_top` 3 |
| `architect.agenda_locked`, `architect.agenda` | `swarm.json` on the box | agenda v16c in both (private; sha256 `c7a46dca0707…`; since 15:22:15Z Oct 1) | the operator's locked preamble, which no model edits, and the fallback agenda (at most 4,000 characters each; never a Validation figure, D2a); **The graveyard**, below | edit `swarm.json`, keeping a backup |
| `architect.max_rebirths_per_cell`, `max_rebirths_per_row`, `rebirth_window_days`, `card_rebirth`, `require_card` | `swarm.json` on the box | 6 (since 15:22Z Oct 1), 2, 7, `"refuse"`, true | the card check's rebirth budgets (a refuted cell's rebirths and a row's in the window) and its switches (defaults 3, 2, 7, `"refuse"`, true; league/swarm/cards.py) | edit `swarm.json` |
| `researcher.retire_hold_cycles`, `retire_hold_trials`, `extension_hold_checks` | `swarm.json` on the box | defaults 3, 10, 6 (R11b) | the hold offer (retire after that many holds in a row with an eligible Train run or that many trials); the extension hold (a validation with that many checks met is exempt from the dormancy clause until cleared); 0 turns each off | edit `swarm.json` |
| `researcher.probe_year`, `probe_timeout_seconds` | `swarm.json` on the box | default null (off), 300 (R11b) | the Gym's zero-trade probe: 2022 switches it on | edit `swarm.json` |
| `tournament.exploit_per_positive` | `swarm.json` on the box | default 0.15 (R11b) | (bandit mode only, `allocation.mode` "bandit") the bandit's exploit share a positive old family earns; null: `explore_share` alone, as before | edit `swarm.json` |
| `researcher.hold_until_news`, `retire_min_trials` | `swarm.json` on the box | defaults true, 10 (Release A, #431) | durable holds that only new evidence wakes (false: the R4 timer); the trials after which a researcher may retire its family | edit `swarm.json` |
| `researcher.retire_guard_days` | `swarm.json` on the box | default 14 (Oct 1) | the validated-family guard: a researcher may not retire a family that holds a version which passed the validation line (in its state, in the tournament's verdict records, or archived by any evaluator adoption) last validated within this many days, unless a later validation of that version failed the line; a number at or below 0 turns it off; null, a boolean or a string reads as 14 | edit `swarm.json` |
| `funding` (`enabled`, `every_seconds`, `lead_hours`, `repeat_hours`, `clear_factor`, `claude_out_usd`, `burn_window_hours`, `after_end_hours`, `fallback_every_seconds`, `fallback_flush_seconds`) | `swarm.json` on the box | defaults (Release A, #439): on, 300, per cliff, 12, 1.5, 2, 6, 48, 21600, 30 | the funding cliff alerts (**Funding cliffs and alerts**) | edit `swarm.json` |
| `research.enabled`, `requests_day`, `family_requests_day`, `cycle_calls` | `swarm.json` on the box | defaults (Release B, #447): false, 300, 12, 2 | the research library on the House, and its lines: calls a UTC day for the floor, a family, a research cycle (**The research library**) | edit `swarm.json`; on only after the gateway and the House that carry it |
| The money rules | `league/constitution.py` | the sprint's D4 table and the House live test's bounds (money `a3e2aa7c`); Release B adds the incubator's row (`42c4a3af`); V3-A part 1 leaves it as it is; fast lane v2 moves the Probe row (`da5c7542`); the incubator cap moves `incubator.max_loss_usd` to $75 (`1665c385`); release L-D moves the Probe row's `max_open` and adds `loss_basis`, `demotion`, `loss_window_sessions` and `loss_total_usd` (`0310779c`); the Probe total at $800 moves `loss_total_usd` to 800 (`fdf2ac7c`, Oct 10); the equity lane's rows from release E1 on; in force since 08:00Z Oct 15, 2026: `cfcc94b1` (#557: one open options structure a Probe family and the Probe sleeve 0.33 x E; the CHANGELOG lists every move); C2 (A45) of the scaling plan, the options sizing-up step parked, moves it to `4cd610a5` (`feat/scale-c2`, not deployed); C3 (A45), the Scaled band's block shipped dark, to `558dc3a2` (`feat/scale-c3`, not deployed) | what real money may do | owner deploy; the standing grant ratifies it when the House starts on it (`--ratify` if it refuses) |
| `options_money.probe` | `league/constitution.py` | from fast lane v2: `max_loss_share` 0.10, `contracts` 1, `open_per_family` 3 (1 since Oct 15, 2026: one open structure a Probe family), `family_share` 0.15, `floor_usd` 0, `loss_budget_usd` 400; from release L-D: `max_open` 8 (3 before), `loss_basis` "net" ("gross" before), `demotion` "dm1" ("dm0" before), `loss_window_sessions` 20 and `loss_total_usd` 400; from the Probe total at $800 (Oct 10): `loss_total_usd` 800, the owner's ceiling (the $400 in total before L-D, with no window) | the Probe: one structure within 10% of E, at most `max_open` Probe positions at once, the Probe loss budget ($400 over the last `loss_window_sessions` NY sessions and `loss_total_usd` in total) read by `loss_basis`, live demotion by `demotion` (0 in `max_open`, `loss_budget_usd` or `loss_total_usd` stops Probe opens; "gross", 3, "dm0", a $400 total and a 2000-session window together are L-D's CON-only rollback) | owner deploy; the standing grant re-ratifies at the House's start; no fingerprint move |
| `tournament.drift_screen` | `league/swarm/policy.json` and `swarm.json` on the box | false (the box since 15:53Z Oct 7; the policy from fast lane v2) | THE DRIFT SCREEN's refusal (direction counts since fast lane v2; its fit is reported by the `direction` and `fast_lane` jobs into `<state>/fast-lane-report.json`, and by `scripts/fast_lane_report.py` on copies) | edit the file; true restores the screen |
| `options_money.sized` | `league/constitution.py` | the sprint's: `min_trades` 20, `confidence` 0.80, `kelly_fraction` 0.25, `max_loss_share` 0.10, `family_share` 0.30, `min_probe_real_trades` 5, `min_probe_sessions` 1; `min_trades` 1000 from C2 (A45) of the scaling plan (the options sizing-up step parked; `feat/scale-c2`, not deployed) | when a Probe options family is Sized and how far Kelly sizes it up; at 1000 no options family reaches Sized | owner deploy; the standing grant re-ratifies at the House's start; no fingerprint move; 20 is the rollback |
| `equity_money.scaled` | `league/constitution.py` | C3 (A45) of the scaling plan (`feat/scale-c3`, not deployed): `pin_sha256` "" (dark), `rungs` 0.50 / 1.25 / 2.25 / 4.00 / 6.75 x E_P, `max_sleeve_share` 0.50, `lines` {`in_force` false, `window_share` 0.18, `window_sessions` 20, `total_share` 0.36, `program_share` 0.10, `family_line_probe_only` false} | THE SCALED BAND: with "" every program is at Probe; with a sha256 the matching private pin's rungs size share programs (each row may only tighten; **C3 (A45) of the scaling plan**, above) | owner deploy; every rung raise is a new pin and its sha256 here; the standing grant re-ratifies |
| `elane.scale` | `swarm.json` on the box | C3: `{"rung": 5, "programs": {}}` (the pin alone) | the Scaled band's tighten-only setting: a program sizes at the lower of the pin's rung and this; `{"rung": 0}` stops the ladder; a program's own cap under `programs` ("eq|<family>|v<N>") | edit `swarm.json` (the captain's same-day step-down); never raises a rung |
| `options_money.incubator` | `league/constitution.py` | from Release B, with `max_loss_usd` 75 from the incubator cap (Oct 8, 2026; 50 before it): `max_loss_usd` 75, `contracts` 1, `max_open` 4, `week_loss_usd` 150, `min_sessions` 3, `min_trades` 10, `min_coverage` 0.80 | the incubator's caps and its pre-registered practice rule; each row may only tighten (`max_loss_usd` within $0-75), and 0 in `max_open`, `week_loss_usd` or `max_loss_usd` stops the route | owner deploy; the standing grant re-ratifies at the House's start (`--ratify` if it refuses; no evidence reset) |

In the settings, `researcher.sail_usd_per_hour`, when set, is the researcher pace: the Sail models' spend over the
trailing hour (0.25 since 17:23Z Oct 2; 1.3 from 02:47Z Oct 1; 12 from Sept 29), capped from A1 by the budget
rule, and `researcher.usd_per_hour` is then NOT read (its 5 is inert). Absent or null, `usd_per_hour` paces Sail models
and OpenAI together (OpenAI has no room from A1: the budget closes it). Claude is outside the research pace: it
has its own lines (`claude.usd_cap`, `claude.role_usd_day`, `diagnostician.usd_day`) inside the gateway's funded total,
and from A1 the budget's Claude dollars a day cap them all. Invalid, nonfinite or negative limits pause
research. The heartbeat's `status.researcher_pace` reports the scope, limit, spend and pause reason, so a quiet research
loop can be distinguished from a publication delay.

### The idle rule and a researcher's retire

A Gym researcher can call `retire(reason)` to abandon its whole family on a REVISE or READ turn once retirement is
earned (two validations, `researcher.retire_min_trials` (10) counted trials, death by the idle rule, or the hold offer)
while more families live than `population.floor`; never while a version is at the gate, a look is out, an extension hold
stands or its best Train version awaits validation, and the validated-family guard refuses it for
`researcher.retire_guard_days` (14) after a passed validation (**Goal continuation**, below; on Sept 26 an unguarded
retire on the REVISE turn took the population from 49 to 16, which is why these guards exist). A family is dead by the
idle rule (R3, Sept 27; `researcher.idle_dead`) after `researcher.retire_idle_evaluations` (default 150, 500 on the box;
0 or null turns the rule off, in `swarm.json` without a deploy; a boolean or a non-number also reads as off) Gym
evaluations since its birth or last validation without an eligible Train version, or three times as many with its best
Train score below zero. It counts evaluations, not versions: the store keeps one version for identical code and
parameters, so a family re-running one placeholder makes trials but no revisions. A family whose validated version
awaits the gate (`gate_ready`) or whose holdout look is out is never dead. With the population held at its start, dead
families never qualified before and looped on placeholder runs (the operator retired 48 by hand on Sept 27). The
tournament retires a dead family that never calls retire by the same rule, down to `population.floor`; the architect
refills below `population.start`. The graveyard lesson and the public cause say the idle rule retired it; since R11b the
lesson carries the verdict of its Train record (DRIFT, STRESS, THIN or EXHAUSTED, tested findings), and only a family
that never traded on Train is "a time limit, not a refutation" (IDLE). The family's own last notebook lines carry its
researcher's verdict.

No duplicate runs (R3; the harness audit of Sept 28 found 44% of cycles wasted and 45% of trials identical
re-runs). A `gym_run` or `gym_sweep` variant a family already ran to completion (the same code, merged params,
stress, window, sorted roots, Gym image and engine, Train split and capital: its `eval_key`, kept in the run row's
summary with the result's fill model) is answered from the store, marked `already_run`: no Gym job, no trial, no
version, no revision, and the cycle's REVISE turn goes on. A failed run runs again, and so does a stored result on
another fill model than the one the Gym last returned (a calibration changed on a box in place) or one that can no
longer be scored. The key is coarser than the Gym's run_id on purpose: the Gym's day list is the union of its batch's
roots, so a stored result is the sample of the batch it ran in and is not run again for another batch. Data and the
fill model are the image's, so a new data set or calibration should come as a new image checkpoint (which is in the
key). A run that lands after the wait gave up is recorded with its Train score, so asked for again it is scored like
any run and can become the best. `researcher.reuse_results` (default true, `swarm.json`) false turns it off. A
REVISE turn may also call `gym_run` with `hold=true`: no run, no trial, a notebook line (its `note` only), and the
cycle ends; a run call after it in the same answer is refused, and code or params passed beside it are ignored. A
row recorded before R3 has no key: the next identical run is one more trial (the same Gym run_id, the same row) and
writes the key, and from then on it answers.

Because stored results and holds add no evaluations, the idle rule has a dormancy clause: a Gym family whose last
`researcher.dormant_cycles` (default 40, 12 on the box; 0 or null turns it off) cycles made no new Gym evaluation,
only stored results, holds and runs refused for its own doing (its program, NEEDS, params or variants), is dead (the
same floor, gate exemption and graveyard wording), unless its best awaits validation (not yet validated and not lost
at 1.5x). A new evaluation of its own restarts the count as soon as it is recorded (in the cycle, or when a run lands
after the wait), and so does a counted validation. A cycle that asked the Gym for a new evaluation the Gym did not
make (a Gym error; a run, or every new variant of a sweep, that did not land) leaves it, and a sweep whose new
variants all failed is a Gym error even when some of its variants were read back from the store. A sweep refused for
room leaves it too, unless the cycle also held, got a stored result or had a run refused. The count is zero outside
the Gym band, and a Candidate sent back to the Gym starts afresh. A holding cycle is one model call, so 40 of them can
pass in well under an hour of a family's cycles; the count is the family's state `dormant_cycles`, and each dormant
cycle's `swarm.cycle` event carries it.

Deploy impact (R3): the rule applies at once to every family that is already past it. On Sept 27 (start 72, floor
44, 74 alive) about 29 families were past it, nearly all long-refuted placeholders, so the first tournament round and
the dead researchers retiring themselves take the population to about 45 within minutes, and the architect's refill
(a handful of births a pass) takes hours to restore the start. To stage it, set `researcher.retire_idle_evaluations`
high in `swarm.json` before the deploy (for example 500, which catches only the longest loops) and lower it toward
150 over the following passes; the setting reloads each step. Retirement stops queued research, keeps the best
programs and every trial/look, and leaves existing positions under their exit owner. Researchers and the
tournament share the same atomic population-floor check. A refused retire (not offered, or the floor) is a plain
tool answer: no cycle error and no cooldown; it does not retire the family. The raw reason stays private in its
notebook and graveyard; the public event carries only filtered prose.

### Search settings

The sprint's search settings (Sept 26), all in `swarm.json` without a deploy: `researcher.top_profile` (default
`pro_asap`, null turns it off), `researcher.top_reasoning_effort` (`low`), `researcher.top_families` (10; 0 on the box
since Sept 30, so the top band is off) and `researcher.top_max_output_tokens` (12000) put the top families by allocation
share on the stronger Sail profile inside the same hourly pace; `architect.agenda` (default empty) closes every
architect request as the operator's research agenda (at most 4,000 characters; the box's agenda: v16c in
`architect.agenda_locked` and `architect.agenda` since 15:22:15Z Oct 1, after v14 from Sept 29 and v15 on Sept 30; it
steers where to look and changes no evidence line or kill test; its text stays private); `population.reseed_max`
(default 0, off) founds the seeds' mechanisms again on roots they never tried while the population is below its start
and the architect is not due; `tournament.require_robustness` (default true) validates a version only after its 1.5x
Train robustness run came back with a profit. The robust Train objective, its robustness runs (1.5x and mid, at the
pool's lowest priority, never starting or keeping a box awake) and the D2 validation line are code, not settings. The
objective's one-time migration beats the heartbeat while it runs, skips a family it already moved and empties (never
keeps) the best of a family it cannot rescore.

## The gate

The operator's gate hold (R3): `python -m league.swarm hold-gate --root /workspace/state --family <id> --reason
"..."` (or `SwarmStore.hold_gate(fid)` from a shell on the box; a second connection is safe beside the running
swarm) sets `gate_hold` in the family's state. The gate then starts nothing for it (no review, audit or holdout
look; a hold set while a review is out stops the stage after it) and leaves `gate_ready` as it is; a look already
in flight is still judged when it lands. `--clear` releases it, and the next gate round looks at it. The gate
round's answer lists it under `held`; `python -m league.swarm status` (`gate_held`), the tournament's board and the
researcher's status say "held by the operator"; the public checklist shows `gate_paused`, since the site's list of
blockers is closed. Each hold and release is a private `swarm.gate` event with its reason. While a family is held
with `gate_ready`, no rule retires it: not the idle rule, not the tournament's revision, evaluation or deflated
Sharpe rules, not its own researcher and not the diagnostician (`SwarmStore.retire_gym` refuses it; `hold-gate`
answers `retire_exempt: true`). Its clocks keep running while it is held, so a family past one of those rules can
retire at a tournament round after the hold is cleared if the gate has not started its look by then (the gate
round comes every few minutes, the tournament hourly). A hold on a family without `gate_ready` protects nothing.
The hold does not touch tuition of a version whose review and audit already passed (`bands.read`).

The gate's data (Oct 1, 2026). A look needs the gate image to hold the holdout of every root the program needs. On
Sept 30, three looks of a GOOGL/MSFT program failed with "no holdout days for GOOGL, MSFT". Each counted as a try, and
the third wrote a stage "gym" refusal that bars the program from the incubator, although no verdict was made.
- **Each gate box lists its holdout when it starts**, by file name only (holdout-dated `nbbo/<ROOT>/*.parquet` and
  `underlying/<ROOT>/*.parquet`; no file is opened and the gate's capability is never minted). Its roots with the
  image's full count of both (the count most roots have, 184 sessions on the current images) are the box's
  `holdout_roots` (the `boxes` row and the `box_ready` event); a root copied only in part is not among them. A holdout
  job needing another root fails at once as missing data. A store with no holdout at all fails the box, records the
  image as holding none, and fails the holdout looks waiting for a gate box as missing data. The pool keeps the
  coverage per gate image in kv `gate_coverage`, with the roots any Gym exit-3 answer named since ("no holdout days
  for GOOGL, MSFT in ..."). An exit-3 answer that names no root (no store, a missing package) is a fault of the box,
  not missing data: it is not recorded, and its look fails and counts a try as before. An image that lacks a root of
  `gym.roots` raises one `gate_coverage` alert.
- **The record is per image**, keyed by `gym.gate_checkpoint`, so each nightly publish starts a fresh one. To clear a
  record that is wrong (say a Gym fault that named roots the image holds), drop that image's entry from kv
  `gate_coverage` on the House:
  `s=SwarmStore('/workspace/state'); c=s.get('gate_coverage') or {}; c.pop('<checkpoint>', None); s.put('gate_coverage', c)`.
  The next gate box lists the image again.
- **The gate refuses a look up front** when that record, or the ready file's `holdout_roots` while its chain is the
  gate, says the image lacks a root the program needs. No look is marked, no try is counted, nothing is refused,
  `gate_ready` stays, the round lists the family under `waiting`, and one `gate_missing_data` alert is raised per
  program, image and gap (kv `gate_missing:<run_sha>`). The look runs once `gym.gate_checkpoint` names an image that
  holds those roots (a new image starts with no record).
- **A look that fails for missing data all the same** (the first look on an image no gate box has listed yet) is owed
  again on the same terms: no try, no refusal, no incubator bar, the same alert.
- **Any other failure counts a try** (kv `look_tries:<run_sha>`, kept by program). The third writes the "gym" refusal
  and its incubator bar, as before. The `look_failed_three_times` alert now fires at every count from three on (its
  `tries` field says which). A fourth failure, as when a revived family runs the same program, therefore parks the
  version loudly instead of silently. After fixing the gate, reset the count: on the House,
  `SwarmStore('/workspace/state').put('look_tries:<run_sha>', 0)`.
- **A look that never reached a gate box** (the queue gave up on it after the run timeout because no gate box became
  ready) still counts a try. The try is the loop's bound: a look holds the gate's round for up to the run timeout, and
  gate boxes have no probe fork to find the image back. A store with no holdout is the one start-up failure that is
  missing data (above).
- **Sept 30's leftovers are not changed by this release.** The GOOGL/MSFT program of
  `googl-lags-msft-ai-cloud-qqq-flat` v27 still has `look_tries` 3, the stage "gym" refusal row and its incubator bar,
  from three failures this release treats as missing data. The revived `-r` family runs the same program. A single
  real failure there makes the count 4 and parks it at once (with the alert). Reset the count once the gate is right
  (above). Whether the refusal row and the bar stand is the owner's call: should an infrastructure refusal bar a
  program from the incubator?

The duplicate look (H3a, Oct 1, 2026; `league/swarm/gate.py` `duplicate_look`). Every holdout look raises the Holm bar
for every later one (the 4th look must reach p <= 0.0125, the 10th 0.005), and the three looks after the Sept 26 reset
covered two programs: the two Sept 27 looks had identical Train and Validation results under different run shas. The
gate now compares each gate-ready version, before anything else (the experiment contract, the drift screen, the
rations, the paid review and audit, the gate image's coverage, the look), with every look in the `looks` table, in any
family and lineage, and with any look in flight in another family.
- **A repeat** is (1) the same program: the same `run_sha` (code and parameters); or (2) the same Validation run, read
  from the stored Validation results of the looked version and of the candidate (`validation_identity`, hashes only):
  the Gym's own `run_sha` (the code with its PARAMS merged over the declared defaults, so an override that restates a
  default is the same program), or the same evaluation (`engine`, the engine's `code`, `tables`, `fill_model`, roots,
  window, stress, capital) with the same outcome (`summary`, `fills`, `breakdown`, `stress_1.5`). The program's own
  identity, the image and bundle labels and the runtime counters are left out. A result that names no engine or
  engine code, or has no trade, is never compared on its outcome.
- **The refusal** is recorded as every gate refusal is (stage "duplicate look": a `refusals` row, the program's
  incubator bar, `gated_sha` with `gate_ready` cleared, `gate_outcome` "refused", the researcher's status line), plus
  one private `swarm.gate` event, action `duplicate_look`, with `of_look` (the earlier look's seq), `of_family`,
  `of_version` and `match` (`run_sha`, `program` or `validation`). No look row, no `look_tries`, no review, no holdout
  read. The researcher reads "a duplicate of holdout look #N" and why, never a figure or that look's verdict. The
  tournament never makes the version gate-ready again (`gate_spent` reads `gated_sha`); an evaluator adoption clears
  `gated_sha`, so after one the gate refuses it once more.
- **A repeat of a look still in flight** in another family is listed under `waiting` (no refusal, `gate_ready` stays)
  and refused once that look lands. A version whose own look already landed is only closed (`gated_sha`), never refused.
- **To see it**: `swarm.gate` events with action `duplicate_look`, and `refusals` rows with stage "duplicate look".
  Expect none for a genuinely new version. A refusal that should not have been made (two different programs with
  byte-identical Validation outcomes) would show as `match` "validation" on programs whose code differs in more than
  comments; report it, and the owner decides whether to clear its `gated_sha`, refusal row and incubator bar.

The look holds (L6(b) and L6(c) of the Oct 1 edge study, approved by the owner on Oct 2, 2026 as a tightening with
fixed-benchmark proof; `league/swarm/gate.py` `look_hold`, `league/swarm/evidence.py` `drift_lean`, `holm_level`,
`holdout_power`). The three looks after the Sept 26 reset were all long-delta programs and all failed, and every look
raises the Holm bar of every later one. After the duplicate look, the experiment contract, the drift screen and the
rations (each of which refuses, and a refusal bars the program from the incubator: a hold never takes a refusal's
place), and before the paid review and audit, the gate image's coverage and the look, the gate HOLDS the look at a
gate-ready version when:
- **(b) the drift hold** (stage "look hold (drift)"): its own Train drift fit (`researcher.version_drift`, the figures
  the drift screen reads; the pooled line over the years the screen counts, re-pooled when it leaves a year out) is
  long-delta (beta above zero) with drift share |drift_usd| / (|alpha_usd| + |drift_usd|) at least
  `gate.look_holds.drift_share` (0.25). A version with no drift fit, or a long-delta one with neither alpha nor drift,
  is held too (fail-closed): with the drift screen on, such a version already waits at the screen, so this bites only
  when `tournament.drift_screen` is off or a fit lacks a beta.
- **(c) the power hold** (stage "look hold (power)"): its expected holdout power is below `gate.look_holds.min_power`
  (0.30). Power = P(Z >= z(level) - S sqrt(N)), the normal approximation of the holdout line's one-sided day-block
  bootstrap test of mean daily P&L above zero: S is the version's Validation all-days daily Sharpe
  (`validation_numbers.sharpe_daily`, the figure the look's own Sharpe check uses), N the holdout window's NYSE
  sessions (`holdout_sessions`, Jan 2 to Sept 25, 2026: 184), and the level is the one the look would have to reach
  under Holm across every look made (`evidence.holm_level`, the gate's own `holm_passes`; with every earlier look
  failed, 0.05 / m: the 4th look 0.0125), a look in flight in another family counted as a failed one. A missing Sharpe
  or session count holds (fail-closed). The approximation leaves out the line's other checks (which can only lower the
  pass chance, and barely bind near the line). For independent daily P&L (the usual one-lot program) the gate's
  bootstrap passes a little more often than the approximation near the line, so the hold errs toward holding (the
  tighter side); for positively autocorrelated daily P&L (positions marked over several days) it errs toward looking.
- **The record**: one `look_holds` row (`SwarmStore.hold_look`: family, version, run sha, stage, the researcher's words;
  never a `refusals` row), the program's incubator bar (`incubator_barred[sha]`, "the gate held its holdout look (<stage>)",
  recorded right after the row and before anything else: THE VERDICT FIRST), `gated_sha` with `gate_ready` cleared (the
  tournament never readies the version again), `gate_outcome` "held" (one of `bands.BAD_OUTCOMES`, below), the
  researcher's status line, and one private `swarm.gate` event,
  action `look_hold`, with `stage`, `holds` (every hold that fired, the drift hold first) and `_figures` (beta, alpha,
  drift, share; power, Sharpe, sessions, level, looks counted: operator-only, never in a model's text). No look row, no
  `look_tries`, no review, no audit, no holdout read. The round's answer lists it under `look_held`. `look()` asks
  again under the store's lock, since a look landing meanwhile lowers the power; one held there is recorded next round.
- **What the researcher reads**: "the holdout look is held: the program's Train profit leans on market drift ..." or
  "... too few independent bets for the holdout to judge it ...", never a figure (D2a). A new version of the family is
  looked at once it clears both holds; the held version stays closed (an evaluator adoption clears `gated_sha`, and
  the gate then holds it again if its figures still say so).
- **On the money path a hold is a failed look** (the owner approved the holds as a tightening; reviews A1 and B1 of
  PR #484). "held" is one of `bands.BAD_OUTCOMES` (`incubator.BAD_OUTCOMES` is the same tuple), so:
  - **its execution tuition ends** (`bands.read` drops the row; open tuition goes exit-only, as after a failed look).
    This matters because a hold can land after the review: a version whose review and audit passed and that waits (for
    the gate image, a holdout gap, a look owed) is held when a look landing elsewhere lowers its power, when `look()`'s
    recheck under the lock fires, or when the holds are switched on. Without this its tuition row would stay for good,
    since no look is coming to fail it;
  - **its program never trades the incubator** (`bands.program_refusal` refuses it, `incubator.gate_bar` bars it, the
    bar is recorded for good, and no incubator review is paid for it), where a held program would otherwise reach one
    real lot through the incubator's own review that the failed look it replaces would have barred.
  `bands.py` is the House's reader, so the House and the swarm deploy together (one release): a gate that writes "held"
  before the House reads it would leave a held version's tuition running until the House restarts on the release.
- **At the deploy** (the holds are on by default): every gate-ready version is read against the holds in the first gate
  round, including one already reviewed and waiting, whose tuition then ends. Before the deploy, list those on the box:
  `SELECT id, json_extract(state, '$.validation_version') FROM families WHERE retired_at IS NULL AND
  json_extract(state, '$.gate_ready') AND json_extract(state, '$.review.verdict') = 'pass'` (each may be held in the
  first round, and its tuition then stops); after it, check that `bands.read` has no row for a family in `look_holds`.
- **Rollback**: `"gate": {"look_holds": {"drift_share": null}}` (or `"min_power": null`) in `swarm.json` turns one hold
  off; `"look_holds": null` turns both off and the gate is exactly as before. A version already held stays closed, and
  its program's incubator bar stays (bars are kept for good, as a failed look's); to look at it, the operator clears
  its `gated_sha` and its `gate_outcome` (or it is looked at as a new version). A value that is not a number
  from 0 to 1 reads as its default.
- **To see it**: `look_holds` rows (`SELECT family, version, stage, at FROM look_holds`) and `swarm.gate` events with
  action `look_hold` (their `_figures` say which figure held it). Expect most long-call and call-vertical programs held
  for drift, and sparse single-pair programs held for power.
- **The fixed-benchmark proof** (the owner's condition): `scripts/look_holds_benchmark.py run` runs the pinned
  `evaluator-suite-1` (#452) and records each case-world's hold figures; `analyze` counts promotions with and without
  the holds (engine tier) and re-simulates the search tier's current rule with the power hold before each look. On the
  branch, at full protocol: the suite equals base case for case; with the holds, false promotions stay 16 of 160 and 0
  of 896 search noise lineages, missed signals stay 23 of 40 and 269 of 384 (no planted signal that reached its look is
  held). The suite's worlds have no long-drift program that reaches a look, so it shows the cost, not the saving.

## R11b: honest verdicts, corrections that land, effort where it pays (Sept 29)

R11b was merged through #431 and ships in Release A. The operator's steps after it are in **Release A: after
promotion**.

### Goal continuation: event-driven research and reachable retirement (Sept 30)

The goal continuation keeps the R11b fixes and adds these defaults without changing models, funded budgets or any
promotion threshold:

- `researcher.hold_until_news: true`: a hold is stored in `family.state.research_wait`. Time and process restarts alone
  never schedule another paid call. New trials, gate state, a rewrite, notebook guidance, the agenda, data image or
  harness release can wake it. To deliver explicit new guidance, append a factual notebook note or change the family's
  `research_wake` state token. `false` restores the optional R4 timer. A worker with nothing ready inspects local state
  every few seconds; this does not contact a model.
- `researcher.retire_min_trials: 10`: a researcher may retire after this many counted trials, or after two validations,
  on either its REVISE or READ turn. It need not spend three holding cycles to receive the tool. All researcher and
  diagnostician retirements use the atomic `population.floor`. `population.start` only governs refilling. Pending gate
  work and extension/operator holds remain protected, and so is a best Train version that awaits validation (Oct 1, H1;
  `awaiting_validation`, the dormancy clause's own exemption: not validated, not lost at 1.5x, not failed by the drift
  screen): the tool is not offered, a call is refused with the reason (the cycle's record carries `retire_awaiting`),
  the status says so in place of any offer, and the diagnostician's retire defers the same way; the tournament's
  verdict, pass or fail, ends it, and so does a demotion. On Oct 1 seven of the ten families that made a drift-passing
  Train version had retired themselves before the tournament validated it. The tournament's own rules, operator
  retirements and `SwarmStore.retire_gym` are unchanged (a 1.5x run that never lands must not make a family no rule
  can retire). The floor prevents concurrent retirements from draining the
  population. The agent must explain abandonment, and all prior evidence remains.
- The validated-family guard (Oct 1, `researcher.retire_guard_days`, default 14): the retire tool refuses while the
  family holds a version whose latest validation passed the line, last validated within that many days (the
  tournament keeps each version's latest verdict and its evaluator in `validation_verdicts`). A pass counts wherever it
  is held: the family's line, a passed record in `validation_verdicts` (no adoption clears it and no other version's
  validation replaces it), `previous_evaluator_selection`, and the selection each adoption within the window archived
  in its own append-only `evaluator_adopted` event. So a second adoption, which overwrites
  `previous_evaluator_selection` with the selection the first one already cleared (the House adopted at Sept 30 20:08Z
  and again at Oct 1 03:51Z), never lifts it. An archived pass counts only while it is still that version's latest
  verdict: a record of the version (always its newest verdict) or a newer adoption's archive that shows it failed
  refutes it. So a version that passed under one evaluator and failed its re-run under the next stays refuted after a
  third adoption. A version whose validation time is unknown guards only from an adoption's archive, counted from that
  adoption. A
  failed holdout look does not end it (the gate retires nobody; the tournament's rules still apply). The refusal says
  why and, for a version passed under an earlier evaluator, returns its program to re-run unchanged; the status says so
  in place of any offer to retire, and the prompt says an evaluator change is never a reason to retire. It exists
  because googl-lags-msft-ai-cloud-qqq-flat, the only D2-tuition family, was retired by its own researcher 17 seconds
  after the Sept 30 20:08Z adoption. Operator retirements, the tournament's rules (the deflated-Sharpe rule and the
  idle rule among them), the diagnostician and the population floor are unaffected.
- `gym_run` and every variant of `gym_sweep` receive the static experiment-contract check before any version or Gym job
  is created. Changed parameters that are provably unread, invalid override types and malformed declarations return
  an actionable refusal without consuming a replay trial. A valid zero-trade control remains admissible.
- Graveyard format 4 limits economic claims to the versions actually tested. Drift-screen failure means the required
  alpha beyond exposure was not demonstrated. `UNRESOLVED` identifies missing/failed robustness evidence, rather than
  falsely labeling an execution failure a measured stress loss. The digest reseals automatically. Run the existing
  graveyard migration dry-run and review its counts before applying it to pre-R11b idle deaths.

At deployment, verify `holding` families remain on the same cycle count without new evidence, then verify a genuine
new result or guidance note wakes its family. Inspect retirement events to confirm tested families can exit below the
refill target while the living count remains at or above the floor. The zero-trade probe remains off by default; no
model migration or additional service funding is part of this change.

The ROI audit and plan of Sept 29 (the operator's `scratch/roi/PLAN.md`, section (b)) found the swarm's inputs untrue in
places: 99% of the dormancy deaths filed as "a time limit, not a finding" had been screened on Train, the strategist read
them as untested, and its 13:10Z correction was voided by a family id. R11b is research-side only: no file under
`league/live`, the gateway or the constitution changed, and the money digest stays `a3e2aa7c`. Train figures only (D2).

- **The idle rule's verdict (R11-1).** An idle-rule death is filed under what its Train record shows
  (`researcher.train_record`, from the family's `best_train`, `drift_failed`, `robust_failed`, `robust_why` and its Train
  rows' `train_eligible` and `trades`): DRIFT (its eligible versions failed the drift screen), STRESS (they lost at 1.5x
  the half-spread), THIN (it traded, never 40 trades on 20 days in every Train year), EXHAUSTED (it reached a Train
  score, then ran dry). Only a family that never traded on Train keeps IDLE and the old words. The public cause of a
  tested death is "Retired by the idle rule after its Train record was screened." The digest (format 3, one reseal)
  tags each row by its verdict and says in its header that they are tested findings; the ladder shortens DRIFT, STRESS
  and THIN rows with no Train score exactly as it shortened those IDLE rows, and its id lists name each verdict. The
  strategist's evidence carries `screen` (scored, drift, stress, thin, untested) per family in place of
  `eligible_train_version`, and its SYSTEM text says DRIFT, STRESS, THIN and EXHAUSTED are tested.
- **The hold offer (R11-1).** A Gym family that held `researcher.retire_hold_cycles` (3) cycles in a row with an eligible
  Train run, or `researcher.retire_hold_trials` (10) trials, behind it is offered `retire` on its REVISE turn too, down to
  `population.floor` (the floor rule is unchanged). Every retirement a researcher calls is SELF-REFUTED in the graveyard
  ("Self-refuted by its researcher: " and its reason; its last notes follow as before).
- **The migration (R11-1, once, the operator's).** `scripts/graveyard_verdicts.py` re-heads the rows already buried from
  the same function. Run it on the box right after the release is promoted and before the next architect pass, so the
  digest reseals once:
  `/workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state` (a dry run:
  counts by verdict and clause, examples, the digest's ladder before and after), then the same with `--apply` (a backup
  of every changed row in `state/backups/graveyard-before-verdicts-<UTC>.json`, mode 600; compare-and-set in one
  transaction; the seal emptied; the tags counted after). `--rollback <backup> --apply` restores. On the Sept 29 03:51Z
  graveyard (809 rows) enriched with the ROI extracts, 473 of 474 IDLE rows re-head (305 DRIFT, 92 THIN, 50 EXHAUSTED,
  26 STRESS) and the ladder stays at level 0.
- **The strategist's corrections land (R11-2).** Every known graveyard or family id in a section is masked before the
  content rules read it (an id is a name). The prompt asks for about 85% of `strategist.max_chars` ("at most 1,600
  characters; about 1,350 is right"); the validator still checks the cap, and a section refused for its length alone and
  at most 15% over is cut at its last sentence end inside the cap and validated again (the event's `trimmed`), instead
  of paying for a repair turn.
- **The class cap (R11-2).** `architect.max_alive_per_class` (12) living families of one mechanism class (structure x
  root group, the strategist's `mechanism_class`); `admit` refuses births past it whatever the agenda says, the request
  names the full classes, and the pass's event counts the refusals (`class_capped`).
- **Per-role effort and truncation salvage (R11-3).** `claude.role_effort` {role: effort} applies when the caller names
  no effort; `claude.effort` stays the default (the gate keeps "high"). After the deploy, set
  `claude.role_effort.architect` to "medium" in `swarm.json`; roll back by removing the entry. An architect answer cut
  at max_tokens keeps its complete families; fewer than 3 buys one retry on Claude alone at medium effort. A cut never
  falls to a Sail refill: a retry Claude has no room or line for leaves the pass, and the next pass routes as usual.
  The event's `truncated` says what was salvaged and retried.
- **The bandit exploits only positive evidence (R11-5; the bandit runs only under `allocation.mode` "bandit" since
  Release B's value allocator became the default).** Only an old family whose latest validation mean is positive is
  in the exploit pool, each earning at most `tournament.exploit_per_positive` (0.15) of the share; the explore pool (new
  families, and old ones at zero or below drawing from their own posterior) takes the rest, never less than
  `explore_share`. It replaces the A4 stopgap (`explore_share` 0.75): with it, return `explore_share` to 0.25.
- **The zero-trade probe (R11-6).** Off by default: `researcher.probe_year` 2022 in `swarm.json` switches it on. A new
  version's first Train run at the normal spread is then preceded by a run over 2022 on the family's first root; a probe
  with no trade is the answer ("disqualified: no trades in the probe year", one trial, a `probe` run row that no Train
  score, best or drift screen reads), and the five-year run is skipped; the same program asked again is answered from
  that row. A probe that trades, fails or does not answer in `researcher.probe_timeout_seconds` (300) says nothing and
  the full run follows unrecorded. `gym_run` full=true skips it; sweeps and 1.5x runs are never probed. The risk is a
  false negative (a program that trades only in other years or roots): watch `probe` in the cycle events.
- **The extension hold (R11-4's swarm rule).** A validation that meets `researcher.extension_hold_checks` (6) of the
  line's checks sets the family's `extension_hold`, and the family is exempt from the dormancy clause while it stands
  (for the version its latest validation judged). The operator clears it once the 2017-19 extension result lands:
  `scripts/extension_hold.py --state /workspace/state` lists the holds and the alive families that met the checks before
  the rule shipped; `--seed --apply` holds those; `--clear FID ... --apply` ends a hold (the version is never held again
  on the same Gym; the state keeps `extension_cleared`). From Release B (#453):
  - a validation of the held version that falls below the checks ends the hold (`extension_lapsed`), and a later one
    that meets them holds it again;
  - an adoption that changes the Gym's image or bundle archives and clears these records, and one that changes only
    `league/live` keeps them.

Checks after R11b ships (with the plan's 4-hour check): the share of new graveyard rows tagged IDLE (expect under 5%),
strategist acceptance (2 of 3 runs or better) and the largest mechanism class's share of births (expect under 25%),
architect truncations and births per Claude pass, and `probe` outcomes once it is on.

**The cell's yield** (H2, `league/swarm/cards.py`; `architect.cell_yield` off: the owner chose claims first on Oct 2;
`architect.claimable_rows` 4 on the box since 05:26Z Oct 2). On Oct 1 from 22:00Z the
architect bore nothing for seven passes in a row and the population fell to 13 (floor 12). Every refusal was the card
check's rebirth rule: the productive cells (for example `relative_value / directional / days_4_10`, 139
mechanism-verdict rows) are full of self-refuted and drift rows, so every proposal there needed a claim naming one of
the cell's rows, and the model named rows outside the six the refusal listed. The edge study's critique (L4, H2)
prescribes this variant, not dropping those tags from the verdict list and not `card_rebirth` "off".
- **Switch on**, in `swarm.json` under `architect`, no deploy and no restart (the next pass reads them):
  - claimable rows (on): `"claimable_rows": 4`. Births per Sail pass went from 0-1 to 4 within an hour of it; roll back
    with `"claimable_rows": 0`;
  - open cells (the owner's decision): `"cell_yield": {"min_births": 30, "floor": 0.10, "lookback_days": 7}`; roll back
    with `"cell_yield": null`.
- **What it does.** A cell is exhausted when it has at least 30 settled births in 7 days whose Wilson 95% upper bound on
  drift-pass share is below 10%. At 0 drift passes that takes 35 settled births; at 1 pass, 53; at 2 passes, 69. In
  every other cell, a card that matches only self-refuted and drift rows needs no claim. Refuted, the operator's,
  diagnosed, trial-adjusted, stress and failed-mechanism-test rows still need one, and so does every row of an exhausted
  cell. A settled birth is a retired family or one that already holds a drift-passing eligible Train run. A family still
  researching without a pass is pending, and one whose eligible runs all predate the drift figures is unknown; neither
  counts. The budgets (`max_rebirths_per_cell` 3 by default, 6 on the box since Oct 1; `max_rebirths_per_row` 2; 7
  days), the matching, `card_rebirth` "refuse" and card completeness are unchanged. **Lineage is not unchanged when
  `cell_yield` is on** (the H2 review, F1-F2): an open-cell birth on a slice its matched self-refuted or drift rows did
  not search is born as a fresh lineage with its own deflated-Sharpe N and look ration, where the card check used to
  refuse it or link a prior (a probe on the Oct 1 extract: 31 of 33 verbatim restatements across root sets and
  structures born as fresh lineages with the setting on, 0 of 34 with it off); a paraphrase on the same slice counts
  only the slice's newest dead lineage of each type; and on the Oct 1 extract every cell is open, while a barren cell
  reopens within the lookback. This widens the cross-slice escape from the deflated Sharpe's N that the edge study's
  critique flagged as an owner D2 item, so switching `cell_yield` on is the owner's decision. `claimable_rows` alone
  changes no lineage: it lists, for each cell where a claim can be needed and the cell has rebirth room, the newest rows
  that still have row room, each with the inputs it read, so a valid claim (which links its lineage) can name one.
- **Expected effect, from the edge study's Oct 1 12:59Z extract (not live).** None of the 127 classified cells would
  be exhausted. The lowest upper bounds were `trend_momentum / directional / days_4_10` (14 passes in 156 settled
  births, 0.145) and two cells at 0 in 19 (0.168). Switching on therefore reopens the productive cells now. The guard
  binds only on a cell re-mined to at least 35 settled births with no pass within a week.
- **Verify after switching on.** Each pass's `swarm.architect` event carries `cell_yield`: the settings, `exhausted`
  (cells), `cells` (each with births, passed, pending, unknown, upper, exhausted), `open_born` (births in an open cell
  that needed no claim) and `claims_dropped`. Each `swarm.born` event's `card` carries `open_cell` (and
  `claim_dropped`, with the reason, when a claim was stripped). Expect births per pass to recover and `card_refused`
  `rebirth` counts to fall. Track drift pass per shape birth (the critique's metric (b), at least 10%) and watch for
  `exhausted` cells. An `error` in `cell_yield` means the yields could not be read, and every cell then needs a claim
  as before.
- **Not touched:** `cards.MECHANISM_VERDICTS` and the rows the index holds, which the memory lane's judge reads (its
  settings never set `cell_yield`, so its answers are unchanged); `league/live`, `league/gym`, `LEAGUE_FILES`, the
  constitution, the gate and the evaluator.

## The research library (Release B, #447)

The agents read the literature through the gateway: arXiv's quantitative finance, econometrics, statistics and machine
learning on markets, posted before 2025 and nothing later. Open web access would let them read about the Validation
year and the sealed holdout and select on them, so they get a library. The date rule is code in the gateway
([gateway/README.md](../gateway/README.md), "The research library"), and the House checks every answer again
(`league/swarm/library.py`). What it does not do: the models' weights already hold 2025 and part of 2026. The library
adds nothing after 2024, but it removes nothing a model already knows ([design.md](design.md)).

- **The gateway.** It serves `GET /v1/research/search?q=&cat=&max=`, `GET /v1/research/read?id=&start=&chars=` and
  `GET /v1/research/health`, with the ordinary gateway token.
  - **Pace:** it keeps to arXiv's terms: one request at a time, 3 s apart on the API, 15 s on arxiv.org.
  - **Budget:** `LIBRARY_DAY_UPSTREAM` (600) requests to arXiv a UTC day for the whole floor; `"0"` stops them.
  - **Cache:** KV, binding `LIBRARY`, namespace `ltcm-gateway-library`. A cache hit is free and answers even at the
    cap; the answer's `X-LTCM-Library` header says `hit` or `miss`.
  - **Health:** `/v1/health` carries the same `library` block as `/v1/research/health`.
  - **The kill switch does not stop it:** it moves no money.
- **The House.**
  - The Claude researchers get a `literature` tool: search, and read. The Claude researcher band is off on the box, so
    it goes unused for now.
  - The architect and the strategist get a retrieved block of abstracts before their calls, and the strategist names
    the next searches. The block is kept 3 hours, so the hourly passes make no new call.
  - Sail's profiles never see it.
  - Every agent cites the ids it relied on. A paper's finding is a hypothesis, judged by Train, the drift screen, the
    verifier and the holdout like any idea.
- **The House's lines** (`swarm.json`, `research`): `requests_day` 300 calls a UTC day for every role together,
  `family_requests_day` 12 and `cycle_calls` 2. A call they refuse is a plain refusal with no request. Each call is a
  private `swarm.research` event (the query or id, the ids served, the status, and whether it counted), never mirrored
  to the ledger.
- **The switch:** `research.enabled`, false by default. The rollout order:
  1. the gateway that carries the library, with its KV binding;
  2. the House that carries the client (Release B);
  3. then `research.enabled` true in `swarm.json`.

  To stop it, set `research.enabled` false: no deploy needed. At the gateway, `LIBRARY_DAY_UPSTREAM` `"0"` stops every
  request to arXiv (a gateway deploy).
- **After switching it on,** check:
  - `swarm.research` events from the architect and the strategist, with status ok and ids served;
  - `/v1/research/health`: `upstream` under `cap`, and `backoff_until` empty;
  - no refusal loop (`cap`, `busy`) in the events.
- **Never delete the KV namespace** once a deployed gateway version binds it: that would block `wrangler rollback` to
  that version.

## Models and Claude

Every paid model call goes through the gateway: Claude against the owner's funded total (`CLAUDE_USD`, $265 since Oct 1;
it never resets), OpenAI against the funded month (September 2026 only; $0 from Oct 1). Sail models (DeepSeek, Kimi) are
the inner loop and every role's last fallback but the diagnostician's (it has none). `league/swarm/models.py` routes a
role's call:

- **Claude first** for the roles in `claude.roles`: by default the architect, the gate's audit, the diagnostician and
  (since PR #417) the researcher's top band. Since R8 the researcher's stall rewrite and the gate's program review ask
  for Claude too, so adding "rewrite" or "review" to `claude.roles` in `swarm.json` routes them to Claude with no
  deploy; the box has all five since 04:53Z Sept 29. Claude answers while the gateway's total has room above
  `claude.reserve_usd` (5) and the swarm's own Claude spend is under `claude.usd_cap` (263 on the box since 20:33Z Oct
  1).
- **The model** is `claude.model` (`claude-sonnet-5-5` on the box since 04:53Z Sept 29, the owner's Sonnet 5.5; the
  default is `claude-opus-5-5`), or a role's own model in `claude.role_model` {role: model id} (the box: the audit on
  `claude-opus-5-5`). A role model must be priced both in `league/claude.py` `MODEL_CEILINGS` and in
  the gateway's `CLAUDE_MODELS`, else the role falls to its next route. Sonnet 5.5's list prices: $2 input, $2.50 a
  five-minute cache write, $0.20 a cache hit, $10 output per million tokens (Opus 5.5: $4, $5, $0.20, $20). Sonnet 5.5's
  default effort is `high` (Opus's is `medium`); the House always sends an effort.
- **A role's daily line**: `claude.role_usd_day` {role: usd}, a UTC day with holds included; a call counts on the day
  its hold was booked, even when it settles after midnight. A call that would pass the line skips Claude for the role's
  next route. No entry is no extra line (the box: the architect $0, the rewrite $0, the researcher $0, the review $5,
  the strategist $6, the diagnostician $6). The diagnostician also keeps its own `diagnostician.usd_day`.
- **The next routes**: the architect falls to its Sail profile, `architect.sail_profile` (Kimi-K3 balanced by default;
  DeepSeek-V4-Pro asap on the box since 12:49Z Oct 2), at `architect.sail_effort` (`medium` by default; `high` on the
  box); with a model named in `architect.openai_model` (null on the box), every other pass would ask GPT-6 Astra first,
  at the same effort. A Sail answer cut short is salvaged as a Claude one, and its retry asks Claude alone. The audit
  falls to GPT-6 Astra while the OpenAI month has room and `gate.audit_openai_model` names it, then to a second,
  different Sail model; the review to GPT-6 Sol on the same terms (`gate.review_openai_model`), else DeepSeek-V4-Pro on
  Sail; the stall rewrite to its Sail profile. Both gate OpenAI models are null on the box, so no role calls OpenAI;
  from Oct 1 the gateway's month would refuse it anyway.
- **Two readers**: the plan wants two different paid models to read a program before its holdout look. A review or
  an audit on Sail, or one Claude model reading both (with "review" and "audit" both in `claude.roles`), raises the
  gate's `not_the_plans_reviewer` alert (`same_reader` true for the second); the cure is a different
  `claude.role_model` for one of them (the box gives the audit Opus 5.5).
- **The top band on Claude** (PR #417, the owner's Sept 29 decision to use Claude Sonnet 5.5 boldly): the top
  `researcher.claude_top` families by allocation share (12) run their research cycles on `claude.role_model.researcher`
  (`claude-sonnet-5-5`) at `researcher.claude_effort` (`medium`), streamed, with `researcher.claude_max_tokens` (12000;
  a call's hold is about $0.31 on a median body) and `claude_timeout_seconds` (180), while "researcher" is in
  `claude.roles`. The loop, the tools, their limits and their semantics are the Sail loop's
  (league/swarm/claude_research.py adapts the tools and the history, checks every input against its schema before it
  runs, and caches the tools, the system prompt and the conversation's tail). A cycle is Claude's when a queued run or a
  rewrite landed in it, when the family's last cycle did not hold, and on every `claude_hold_every`-th cycle (3) of a
  hold streak; the rest of a streak runs on the family's Sail profile. Any Claude failure (a refusal, a cut answer, a
  402, 403, 423, 429 or 5xx, the researcher's line, the family's `claude_family_usd_day` ($15), the
  `claude_min_room_usd` ($25) left to the other roles, a stream timeout, an input that does not parse or validate, a
  REVISE answer without an offered run, an answer that cannot be read) finishes that turn on the family's Sail profile,
  never a cycle error. THE BREAKER: `claude_breaker_failures` (3) calls whose bill stayed unknown (their whole hold
  booked: a cut stream, a 5xx, a 429) inside `claude_breaker_window_seconds` (3600), or one bill above its hold, pause
  the band for `claude_breaker_pause_seconds` (3600); `kv claude_band` says why and until when (the operator can end a
  pause early by setting its `paused_until` to 0).
- **The band's cost** (a dry estimate, Sept 29: the median top-band request of the last 3 h through this adapter, and
  the top band's measured pace of 914 cycles in 12 h, 1.01 calls a cycle): about $0.051 a call at medium (14,500
  tokens of tools and system read from the cache at $0.20, 9,300 of the family's own written at $2.50, 2,500 output
  at $10), and about 1,050 Claude cycles a day with the hold rule (1,830 without it): about $59 a day at medium
  ($48 at low; $103 without the hold rule, where the $100 line binds), 10% more if the Anthropic workspace bills
  US-only inference (`/v1/health` `claude.geos` shows "us"). The top band's Sail spend falls by about $12 a day.
  After about 50 Claude cycles, read `claude_usage` and `claude_usd` from the cycle events: above about $0.08 a
  cycle, drop to `low` or `claude_top` 6; below about $0.04, consider `high` for the top six or `claude_hold_every` 1.
- **Switching the band on** (the owner's or operator's steps, none done by the code; the runbook is in the PR): deploy
  the gateway (PR #417's tool admission, the US multiplier on every row, the checked body forwarded, overruns counted;
  until then a House tool call is a 400 and falls back to Sail), then the House release; then add "researcher" to
  `claude.roles` in `swarm.json` and raise `claude.usd_cap` by the day's expected Claude spend (the researcher's line
  counts against it), and keep `CLAUDE_USD` funded above everything else plus `claude_min_room_usd`,
  `claude.reserve_usd` and one hold. Remove "researcher" from `claude.roles`, or set `researcher.claude_top` to 0, to
  turn the band off.
- **The meters**: `python3 scripts/gateway_admin.py status` (`claude`: the funded total, spent, in flight, remaining,
  holds, the priced models, `by_role`); the swarm's `spend` rows (kind `claude`, by family and role); the
  diagnostician's refusals name the line that stopped it.
- **The spend cut of Sept 30** (16:41Z; the owner's answer was to cut burn to evidence). Claude now answers only the
  gate's review and audit (Opus 5.5 for the audit) and the strategist.
  - `claude.role_usd_day.architect` 0: every architect call takes the role's line and falls to its Sail profile
    (Kimi-K3 then; DeepSeek-V4-Pro asap since 12:49Z Oct 2). From Release A, the funding watch counts these as
    `claude_fallback` events of kind `line`, without an alert. The architect's Claude line was $5 at times on Oct 1-2
    (20:33Z Oct 1 to 00:06Z Oct 2, 06:09-06:51Z and 11:38-11:54Z Oct 2) and is $0 again since 11:54Z Oct 2: its Claude
    passes on Oct 2 bore no family.
  - The researcher's top band (`researcher.claude_top` 0, the researcher's line $0) is off, and so are stall rewrites
    (`researcher.stall_revisions` 10000) and the diagnostician (`diagnostician.enabled` false).
  - The Sail pace is $1.30 an hour (since 02:47Z Oct 1; $1.10 from 16:41Z Sept 30).
  - The evidence behind the cut is in the run record, `docs/runs/2026-09-30-continuous-learning.md`.
  - To undo it, restore the earlier values (CHANGELOG, Sept 30).

## The graveyard

A retired family's lesson (its mechanism, what it tried, its best numbers, its last notebook lines) goes to the
graveyard in `swarm.sqlite`, which researchers search and every architect request and new family reads. Since R8 the
search ranks rows by BM25 (a word's repeats saturate and a long row is discounted, so a long lesson no longer outranks
a short one about the query), and a new family is born with three distinct lessons.

Operator lessons (Sept 29, 2026): the operator's own experiments are in the graveyard as rows with `op-` ids (45 at
04:33Z Sept 29), each dated when its experiment concluded and ending with a "do not re-propose unless ..." line. They
are compiled from private results, reviewed as public-safe, and inserted by the operator's private tool with a backup.
Operator revivals are lineage continuations (origin `operator-revive`): a fork that inherits its lineage's trials and
holdout looks, so the deflated Sharpe and the holdout ration count every version. Since Oct 1 the harness runs the
revived version exactly, with its code and params, before its researcher edits it (**Operator revivals**, above).
Before that fix, the harness never ran a revived program, and a bare `gym_run` dropped its params.

The full graveyard and the strategist (Sept 29, 2026; `league/swarm/architect.py`, `league/swarm/strategist.py`), all in
`swarm.json`. On the Claude route the architect reads every graveyard row as one sealed, cached digest ahead of its own
instructions (`architect.full_graveyard`, default true; `architect.graveyard_digest_tokens`, 100000;
`architect.graveyard_digest_tail_share`, 0.15; `architect.graveyard_digest_ttl`: "5m" marks the digest only when the
strategist's call just wrote it, "1h" marks every call and needs `claude.cache_1h: true`, which is set only after the
gateway admits the 1-hour cache, "off" never marks it). The operator's rows (`op-` ids with no family row; no proposed
family is born with an `op-` id) come first and whole; the other rows shorten on a ladder as the graveyard grows (at the
default budget: every row in full to ~900 rows, idle rows shortened to ~1,600, one line per refuted, diagnosed or scored
row from ~1,800 and fewer such lines from ~3,000, id lists from ~6,500; past ~7,000 the idle ids are cut, with the count
stated). OpenAI and Sail keep the 20 newest rows. Every lesson a model reads loses any sentence about Validation, the
holdout, out-of-sample results or 2025 (`lesson_view`). Each `swarm.architect` event carries `digest` (rows, level, sha,
ttl, `cache_miss`), `usage` and `cited` (proposals naming a real graveyard row). The agenda splits in two:
`architect.agenda_locked` is the operator's preamble, which no model edits; while it is non-empty the strategist runs
before an architect pass that has room (at most every `strategist.every_seconds`, 10800) and writes only the WHERE TO
LOOK section after it (kv `architect_agenda_section`, the previous one kept inside it), every line quoted under a header
that says it changes no rule, the verifier or money. A validator rejects money, real-money or envelope talk, a verifier
word beside a changing verb or a voiding state (paused, advisory, not binding ...), numeric rules, 2025, the holdout or
the Validation period in any words, the operator's voice, overrides and revivals, non-ASCII, and fewer than
`strategist.min_cites` real ids; a rejection goes back once with its reasons (`strategist.repair_turns`, 1), and a final
rejection or any failure keeps the last section. Its Claude line is `claude.role_usd_day["strategist"]` (4.0 a UTC day
by default), and "strategist" must be in `claude.roles` (the default; the box's `swarm.json` overrides the list, so add
it there, or the strategist runs on Sail's small packet and its event says so). The architect has no daily Claude line
of its own unless `claude.role_usd_day["architect"]` is set: with the digest each call carries ~85k more input tokens.
Each run is a private `swarm.strategist` event. Emptying `architect.agenda_locked` returns to `architect.agenda` as before.

Two-sided singles (#425, ships in Release A; `league/swarm/store.py`, `architect.py`). The architect's structure types include
`long_single` (one program that buys calls or puts by its rule; a proposal states the side rule and why its calls
and puts balance, since the drift screen charges whatever net exposure it holds), and its prompt asks for one
`long_single` family where it would have proposed a call/put twin pair. `admit` enforces it: a `long_call` or `long_put`
is refused while a living family on the same roots with the same idea (`same_idea`, one born earlier in the same pass
too) is a `long_single` or the other side. In GAPS a single option's one gap is `long_single`, covered only by a living
`long_single` family on the root; the one-sided `long_call` and `long_put` are never gaps (still admitted when proposed,
on other roots or another idea), and the coverage table has a `long_single` row. A `long_single` and the singles it
sends are one slice for lineage matching (`same_slice`): the same idea as a dead call or put twin on the same roots
continues its lineage and joins BOTH twins' (`SwarmStore.link_lineages`: the other twin of its idea or its parent's,
dead or alive, so their trials, looks and validated versions all count); a `long_single` of a living twin's idea
continues that twin's lineage and joins the other's; another idea on the slice counts the newest dead lineage of each
type there, its own first (`slice_priors`, stored as `prior_lineage` and `prior_lineages`; every other structure keeps
its one `prior_lineage`, as before); and identical code links their lineages. So relabeling a program two-sided buys no
trials or looks. Its graveyard reads include its singles' lessons. The researcher, the reviewer, the auditor and the diagnostician read what its orders are (`structure_text`);
every other family's prompts are byte-identical.
