# Changelog

One entry per deploy, newest first, from the options overhaul of Sept 26, 2026 on. Earlier history is
in [archive/](archive/README.md).

Each entry: the UTC time; what was deployed (House release id and main commit, gateway version, or
site version); the pull requests it carries; the money digest and when the grant was ratified, if
it moved; what was verified on the box, and how; and the rollback floor when it changes. A merged
pull request is not an entry until it is deployed.

## Rollback floor

`20260926T084913Z-8158a11cfe3f` (main `b68b3800`, promoted 08:49:50Z Sept 26), the first House release
on the new state root: never roll back past it, because the release before it (Deploy G,
`20260926T032739Z-aaf5ac74637c`) would run the old Kalshi and Jev code on the new root. With real money
on, a rollback also has the real-book and structures guards of [docs/operations.md](docs/operations.md).

Operator changes that are not deploys (`swarm.json`, image adoptions, grant ratifications) are listed
beside the deploys of their day, marked "no deploy". The run records have the detail: to Sept 29,
`docs/runs/2026-09-26-options-swarm.md` on branch `run/options-swarm-2026-09-26`; Sept 30-Oct 2,
[docs/runs/2026-09-30-continuous-learning.md](docs/runs/2026-09-30-continuous-learning.md); from Oct 2,
[docs/runs/2026-10-02-unattended-desk.md](docs/runs/2026-10-02-unattended-desk.md). From the V3-A part 1 deploy
(Oct 3, below) the House also deploys main by itself (the updater): its daily pages in
[docs/runs/desk/](docs/runs/desk/README.md) count its self-deploys and self-rollbacks, and they get entries here like
any other deploy.

## Not yet deployed

The running House release is `20261010T062000Z-1767910d2115` (main `dd196cad`, the spent-lineage refusal, 06:20Z Oct 10),
the gateway is `507b6118`, and the box's updater is on. What is built and not deployed is on branches.

### An always-in card's ablation is dropped, on `fix/always-in-ablation` (unreleased; an owner deploy; no evidence reset)

- `league/swarm/cards.py` `validate`: the architect's card template asks every card for an `ablation` switch, so its
  always-in cards (declared inputs exactly `["clock"]`) arrived with one and were refused ("has no gate to switch off").
  Such a card's ablation is now stored as the default (the same card and sha as one that declared none);
  `dlane.card_errors` itself still refuses one. G1 on Train still holds the program to the clock alone.

### The always-in card, on `fix/always-in-v2` (unreleased; an owner deploy; no evidence reset)

- A direction card whose declared inputs are exactly `["clock"]` is always-in: its card says "always-in" or "no gate"
  and has no ablation; it is bound only by the always-in direction rows on its roots (`cards.RebirthIndex.check`'s
  direction path; alpha cards, legacy rows and gated direction cards as on main); its birth joins every always-in
  lineage on its roots and no gated one (one Validation try a root, claimed by a living member); it trades only the
  roots it was born on and never forks; and it is checked on Train (G1: entries on 90% of its flat sessions, or of all
  of them for a ladder, its risk within 3x and its hold within 2x of their medians, or its version due for Validation
  is never validated and it retires, after the ration). The architect's prompt, BIRTH CELLS and closed-pass check say
  it. A LOOSENED row in the `dlane` report states the cost. Docs: `docs/operations.md`. Proof: `test_dlane_always_in`.

### 06:20Z Oct 10, 2026: the spent-lineage refusal (#526), House `20261010T062000Z-1767910d2115`, main `dd196cad`

Owner deploy (no gateway change) after the 06:00Z nightly: no order in flight at 06:19:51Z; promoted (rollback
`20261010T053556Z-6803e7940d24`), nightly back 06:31:04Z, updater repointed. Verified on the box: health clean, real money
on, execution fingerprint `31a7e921`, money `fdf2ac7c` and constitution `0adb4f0e` unchanged from the release below.

### 05:36Z Oct 10, 2026: the Probe total at $800 and the program line at -$300 (#525), House `20261010T053556Z-6803e7940d24`, main `d93a091e`

Owner deploy (no gateway change): no order in flight at 05:35:44Z; promoted 05:36:40Z (rollback
`20261010T033512Z-df7078e102a6`), nightly back 05:46:55Z, updater repointed. Verified: money digest `0310779c` ->
`fdf2ac7c`, constitution `ca89ff8a` -> `0adb4f0e`, execution fingerprint `31a7e921` unchanged (no evidence reset), and
the standing grant RATIFIED on `fdf2ac7c` at 05:37:13Z. The entries below describe both; they are now live.

### The Probe total at $800 and the program line at -$300, on `feat/probe-total-800` (DEPLOYED 05:36Z Oct 10; money digest `0310779c` -> `fdf2ac7c`; no evidence reset)

- **Why** (PREREG-T, Claude's decision pre-registered privately on Oct 10, 2026 under the Probe roster R5 already live;
  the owner's goal as re-set on Oct 9, item 4: "Probe loss budget: $400 net in any rolling 20 sessions and $800 net in
  total"): the measured gain in Done at the owner's ceiling. The operator's simulation (three paired arms; cross-fit,
  fixed 2-, 3- and 5-session holds standing in for the House's pool, roster 5, arrivals; index beta minus option costs,
  not alpha): P(Done) at 12 weeks 4.6% -> 5.5% (paired +0.92 points, SE 0.15), at 24 weeks 11.6% -> 14.4%; P(Done |
  zero edge) 2.2% -> 2.7% at 12 weeks, 6.9% -> 9.0% at 24.
- **The rule:** `options_money.probe.loss_total_usd` "400" -> "800", the owner's ceiling (`league/constitution.py`);
  `dlane.program_loss_usd` -200 -> -300 and `dlane.done_zero_edge_p` 0.024 -> 0.027 (`league/swarm/policy.json` and
  `league/swarm/dlane.py` `DEFAULTS`; the line's bound in `dlane.cfg` is its default, -300 to -25, tighten only;
  `dlane.ZERO_EDGES` labels 0.024 and 0.027, `dlane.ZERO_EDGE` is 0.027). Unchanged: the rolling $400 in any 20
  sessions, the 10% cap, `open_per_family` 3, `max_open` 8, DM1, the kill switch, the daily stop and the drawdown stop;
  open Probe risk stays at or under $400.
- **Cost** (two loosenings, each a row in the `dlane` report's `LOOSENED` header): P(the agents' running real net, the
  Probe/Sized route and the incubator together, below -$400 within 12 weeks) 17.8% -> 36.8%, below -$600 0.6% -> 4.4%;
  the 12-week net's 5th percentile -$396 -> -$679; P(the 60% drawdown stop trips by 24 weeks) 21% -> 48%; mean 12-week
  net +$22 -> +$25, median -$327 -> -$231. Most of it is the total's; the line's own step over the $800 total alone:
  35.8% -> 36.8%, 4.1% -> 4.4%, 46% -> 48%, zero-edge Done 2.5% -> 2.7%, for P(Done) 5.3% -> 5.5% (+0.24 points, SE
  0.12: 2.06 paired SE, just past PREREG-T's 2). One program may spend $100 more of the shared total before it is
  retired.
- **Roster 5 only:** the pair was measured at `dlane.roster` 5 alone (at no roster the operator's grid found the $800
  total almost all cost). The roster moves by `swarm.json` with no deploy, so a roster rollback or another count needs
  the pair's rollback too, or a new measurement first; the `dlane` report's new PT1 warns while they run apart
  (`dlane_report.pt1_alarms`).
- **The report:** P(Done | zero edge) keeps both figures labelled: 0.027 with PREREG-T's horizon, holds and source,
  0.024 with A1.2's, and any other figure is "not one this code names" (it no longer calls 0.027 A1.2's pin).
- **Identities:** money digest `0310779c` -> `fdf2ac7c`; constitution digest `ca89ff8a` -> `0adb4f0e`; the execution
  fingerprint (`31a7e921`), the Gym bundle and the gate contract (`397b22b772b3`) unchanged (nothing in `league/live/`
  or `league/gym/`). The standing grant re-ratifies on `fdf2ac7c` at the House's start on the owner's deploy (the
  updater alone never does); no real entry until it has. Known stale: `league/live/money.py`'s docstring still says
  "$400 as set on Oct 9" for `probe.loss_total_usd` (the code reads the constitution); its words wait for the next
  `league/live` release, since editing them alone would move the fingerprint.
- **Rollback** (one owner deploy): `loss_total_usd` "400" (`PINNED_DIGEST` back to `ca89ff8a`);
  `dlane.program_loss_usd` -200 and `dlane.done_zero_edge_p` 0.024 in `policy.json` and in `dlane.py` `DEFAULTS` (the
  bound follows); `ZERO_EDGE = ZERO_EDGES[0.024]`; the tests that pin the $800 rules with them. The money digest goes
  back to `0310779c`, re-ratified the same way; no fingerprint move.
- **Proof.** `test_constitution`, `test_ld_release` (the two-envelope tests on the $800 in force and on L-D's $400,
  `AS_SET`), `test_standing_grant` (`TheProbeTotal800`: the owner's deploy re-ratifies, the updater never does, the
  rollback is L-D's digest), `test_dlane` (the bound follows the default), `test_dlane_report` (the line at -300, the
  header's two rows with their own costs, both zero-edge labels, PT1), `test_dlane_ld_joins`, `test_fast_lane_v2`,
  `test_live_long_single`. Operator's page: **The Probe total at $800 and the program line at -$300** at the top of
  `docs/operations.md`.

### The ration at birth, on `fix/spent-lineage-birth` (DEPLOYED 06:20Z Oct 10; no evidence reset; no setting)

- **Why** (measured on the House, Oct 10, 2026): about half of the direction lane's births died 15-60 minutes after
  birth on the tournament's `dlane.SPENT_TRY` without ever taking a try. The architect resolved a parent on the slice
  (a declared parent, a dead family of the same idea, a living twin) and, for a `long_single`, linked its twins'
  lineages, so the family joined a connected lineage whose one direction Validation try was already spent. Right for the
  false-positive accounting, but each such birth wasted research money, Gym runs and a population slot, and the
  architect never learned why.
- **The rule** (`league/swarm/dlane.py` `birth_spent`, `spent_birth_text`; `league/swarm/architect.py` `admit`): before
  `add_family`, a direction card's birth reads the lineage it would join (the parent's and every twin's it links: the
  set `lineage_tries` and `lineage_looks` read after the birth). When its tries reach `val_tries` or its looks reach
  `looks_per_lineage` (in flight too), the card is refused and recorded with the card refusals: the next request names
  the lineage that holds the try and the version that spent it ("propose a mechanism-level new idea on another slice or
  a new mechanism"), and the pass's event counts it (`card_refused.spent_lineage`). No lineage is linked for a refused
  card. `SwarmStore.looks_over` is `lineage_looks` over a lineage set.
- **The review's answers:** a CLAIMED try refuses too: a living Gym-band member of that lineage born earlier in the same
  pass (`Architect.pass_born`, a truncated answer's retry included), or one whose best awaits Validation
  (`researcher.awaiting_validation`, passed in: `dlane.py` still imports no researcher), counts against `val_tries`
  ("whose one Validation try is claimed (<family>, born in the same pass)" / "(<family> v<n> awaits Validation)"). The
  refusal names the lineage that holds the try (a `long_single`'s twin, not its parent). `looks_over` joins
  `harness_lanes.SEALED_READS` (a protected file). The LANES prompt is unchanged on purpose (its golden digests); the
  card refusal is the channel.
- **Unchanged:** alpha cards, the lane off, births with no parent, the tournament's retirement rule and the one-try,
  one-look accounting. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint,
  money digest and constitution digest are main's. Not handled: a living member of an earlier pass with no best yet,
  and a lineage joined after birth by identical code (`_link_code`); the tournament retires those losers as before.
- **Rollback:** revert the commit.
- **Proof.** `league/tests/test_dlane_spent_birth.py` (a spent lineage refused, named and fed back; a twin's spent try
  refused and the twin's lineage named; a second card of one idea in one pass, and across a retry, refused; a living
  member awaiting Validation claims the try; `birth_spent` agrees with `lineage_spent` after the birth on each lineage
  shape; a fresh idea, a lineage with its try left, an alpha card and the lane off are born);
  `test_swarm_harness_lanes` (`looks_over` is a sealed read).

### 03:36Z Oct 10, 2026: the Probe roster (#523), House `20261010T033512Z-df7078e102a6`, main `9e2cf9fc`; `dlane.roster` 5 at 03:48Z

Owner deploy (no gateway change): no order in flight at 03:35:03Z; nightly stopped, deployed, promoted 03:36:06Z (rollback
`20261009T225656Z-01beacbc792b`), nightly back 03:46:16Z, updater repointed to `9e2cf9fc`. Verified on the box: health
clean, real money on, execution fingerprint `31a7e921`, money `0310779c`, constitution `ca89ff8a` and gate contract
`397b22b772b3` unchanged. `dlane.roster` 5 set in `swarm.json` at 03:48Z (no deploy): the box reads 5 seats, one Probe
family seated, none waiting. Rollback of the rule: `dlane.roster` 0.

- **Why** (REDESIGN-1010, Oct 10, 2026; the operator's private grid and its confirmatory run): Done needs >= 30 real
  closes with >= 5 from each of >= 2 programs, while every program that passes its look trades at once from one shared
  Probe envelope. At the measured rate of direction verdicts, the envelope's 8 slots spread one or two closes over each
  of many programs, so the ">= 5 from each of >= 2" clause fails even for a strong edge. A roster seats a few programs,
  which then earn the closes that can show an edge.
- **The rule** (`league/swarm/bands.py` `seating`, `waiting`, `roster`; `dlane.roster` in `swarm.json`, read there
  alone): every Probe family holds a seat and is never hidden; a Candidate that cannot trade real money (the money
  table's real types) or has no `banded_at` holds none and is shown; the other Candidates queue, fresh ones by
  `banded_at`, then ones back from Probe by when they came back; the first `seats - Probe` hold a seat and the rest
  WAIT (no `bands.read` row, so no shadow or real instance and no money-table band move). Sized is outside. A setting
  that cannot be read, or is not a whole number, keeps the last good value, else gives no new seat (fails closed).
- **Pre-open check 6** lists waiting Candidates as by design, not as families missing a band row.
- **Rollback:** `dlane.roster` 0 or removed (a setting; no deploy; it releases the queue at the next families pass).
  Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint, money digest and
  constitution digest are main's.
- **Review.** An adversarial review (3 lenses, each finding verified) confirmed 13 findings on the first cut; this
  version answers them: fail-closed settings, real-type seats, demoted families queue for a seat, pre-open check 6, an
  exact `seated` list, a cheaper one-family read, the docs' wording, and the tests below.
- **Proof.** `league/tests/test_swarm_roster.py` (15 tests): the pure rule; `bands.read` hiding and re-seating,
  one-family reads; a demotion through the store; a Probe family never hidden; Sized outside; non-real structures
  seatless; malformed and unreadable settings; the cap at 50; the dlane report's `roster`; pre-open check 6.

### Deployed Oct 9, 2026 (the entries below were written before their deploys; each is now live)

- 10:36Z release D-1 + D-1b (the direction lane on D2): `20261009T103632Z-1edfe38272fb`.
- 12:44Z the direction lane's graveyard (#519): `20261009T124422Z-c5baa58fd45e`, main `d70e00c3`.
- 16:17Z the direction lane's Train map (#520): `20261009T161659Z-95b21ceb53ea`, main `a3c54fa5`.
- 17:03Z the budget split (#521): `20261009T170259Z-404fe99d6c9c`, main `cf96b72c`, gateway `f8061e0f`.
- 22:57Z the weekend fixes (#522): `20261009T225656Z-01beacbc792b`, main `e24a5d6a`, gateway `507b6118` (rollback
  `f8061e0f`); fingerprint `31a7e921`, money `0310779c`, constitution `ca89ff8a`, gate contract `397b22b772b3`, all
  unchanged; health clean, real money on.

### The weekend fixes, integrated, on `release/weekend-fixes` (unreleased; a gateway deploy FIRST, then one owner deploy on main `cf96b72c`; no evidence reset)

`wfix/swarm`, `wfix/ops` and `wfix/replay` (the three entries below) merged one at a time on main `cf96b72c`.
Operator's page: **The weekend fixes, integrated** at the top of `docs/operations.md`. Nothing in `league/live/`,
`league/gym/` or `league/constitution.py`: the execution fingerprint (`31a7e921`), the money digest (`0310779c`), the
constitution digest (`ca89ff8a`) and the gate contract (`397b22b772b3`) are main's, checked at the head.
- **The finality join** (`league/ops/dlane_report.py` `finality`, `meter`, `report`): a close whose per-close twin is
  final has its replay landed whatever the nightly has replayed; with `forward.twins` on, a close with no final twin is
  `pending_twin` and the reading is not final (no A8); with it off, the nightly's landing as before. A1.1's "replay
  untested" why now says a close matched "a replay (a twin or the nightly)".
- **The review's five fixes** (Oct 10, 2026; `league/ops/` only):
  - `dlane_report.Research247`: a UTC day with no `stall` receipt is not held ("no stall receipt"), as a day with no
    `budget` receipt is not: item 7's "no owner step waiting" no longer passes on no evidence.
  - `stall.py` `done`: reads the report's FINAL holding checkpoints (frozen) instead of the once-said A8, and stands for
    each until a notice carrying it is SENT (`stall.json` `done_told`): a House start or a refused notice no longer
    loses a Done claim.
  - `dlane_report.lane_off`: with `dlane.mode` "off" the job still holds the program loss line (A1.3 retires a due
    program, whatever its lane; PL1 a House warning, the figures in the receipt) and writes no report.
  - `registry.py`: the `dlane` job also runs 30 minutes before each open, after the overnight expiry reconciliation (pid
    14's landed at 01:11Z; from Nov 1 that hour is past 01:30Z), so a program an expiry carried past the line is retired
    before the next session.
  - `stall.py`: with the lane off neither `dlane` nor `done` reads the report the lane last wrote (its K5 and A8 were
    mailed at every run for good).
- **Proof.** `test_close_twins` (`test_finality_reads_a_final_twin_as_the_landed_replay`,
  `test_with_the_twins_on_a_reading_is_final_only_once_every_close_has_a_final_twin`); `test_dlane_report`'s two
  nightly-finality tests run with the twins off (`NIGHTLY`). The review's: `test_dlane_report`
  (`test_a_day_no_stall_receipt_read_is_not_a_day_with_no_owner_step_waiting`,
  `test_with_the_lane_off_the_line_still_holds_and_no_report_is_written`, the registry's pre-open trigger, the stall
  job reading a real report's final checkpoints) and `test_ops_stall`
  (`test_an_untold_done_claim_stands_until_a_notice_is_sent`, `test_with_the_lane_off_its_last_report_is_not_read`).
  Both full suites (Python 3.11 and 3.14) at the head.
- **Rollback.** The previous House release and gateway version (its stall job ignores `stall.json`'s `done_told`).

### The swarm-side readiness fixes, on `wfix/swarm` (unreleased; an owner deploy on main `cf96b72c`; no evidence reset)

Four fixes from the operator's readiness audit of Oct 9 (M2, M3, M5, m3). Operator's page: **The swarm-side readiness
fixes** at the top of `docs/operations.md`. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the
execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the gate contract (`397b22b772b3`) do not move,
so no Probe program leaves Probe, no family is reviewed again and no ratification is needed. An owner deploy:
`league/swarm/gate.py`, `tournament.py`, `dlane.py`, `settings.py` and `league/ops/` are FORBIDDEN to the updater.
- **A cut answer is no answer (M2,** `league/swarm/gate.py` `AnswerCut`, `Gate._cut_check`, `gate.cut_tries_day` 6**).**
  A review or audit, the gate's or the incubator's, that Sail returns `incomplete` at max_output_tokens is a
  `review_error` / `audit_error` with `cut` true. No attempt is counted and nothing is barred. It is asked again next
  round on a new model-call key (`:cut<k>`; the Provider dedupes on the key). At most 6 cut answers a version, a stage
  and a UTC day; the sixth raises the owner's `reader_cut` alert, and the stage waits for the next UTC day. On Oct 9
  three cut answers in a row refused dir-qqq-ivlow-3d-call v38, a direction lineage's one try, to a token cap.
- **The ration before the cohort keep (M3,** `league/swarm/tournament.py` `_why`**).** A direction family whose
  lineage spent its one try or look retires even while the cohort keep holds it, which frees its population slot. At
  20:12Z Oct 9 the keep held 8 such families. Its cost: the retired program loses the incubator route. It is listed in
  the dlane report's `tightened`. The alpha lane and the lane-off rollback keep the keep's order exactly.
- **A D2 entry counts (M5,** `tournament.py` `_verdict`, `researcher.record_verdict`, `league/ops/funnel.py`,
  `scoreboard.py`, `dlane_report.py`**).** A direction verdict records `entered` and the lane's `screen` in its
  `swarm.tournament` row and its `validation_verdicts`; `passed` stays the line. The daily funnel gains
  `validations.entered` and `by_screen`, and the public page gains one row only when a window has a pre-check entry.
  The dlane report's direction funnel gains `entered`. A3's gate-wait leg counts entered versions (the verdict's
  `entered`, or `dlane_try.entered` for older entries) and never a refused one. Until now eqp-realcalm-drift-call v17
  (at Probe) counted as a failed Validation everywhere. An alpha verdict's row and record are unchanged, key for key.
- **R3 needs a 1.0x profit (m3,** `league/swarm/dlane.py` `robust_verdict`**).** R3 read `pnl_15 >= 0.5 x pnl_10`
  alone, always true for a 1.0x loss once P1 holds: eqp-term-contango-pool-call v6 (1.0x -$1,778.21, 1.5x +$143.23)
  passed and spent its lineage's try. A 1.0x P&L at or below zero now fails R3. It is a tightening, listed in the dlane
  report's `tightened`. The researcher's brief text is unchanged: the Train map's golden pins it.
- **Proof.** `test_swarm_gate_cut` (cut reviews, audits and incubator reviews; the new keys; the day's cap and its
  alert; a complete unclear answer still counts), `test_dlane_gate_entries` (the verdict row and record, alpha key for
  key, the lane off; the funnel and the page row; the dlane funnel; A3 with entries, older tries and a refusal),
  `test_dlane` (`test_r3_needs_a_profit_at_10x`), `test_dlane_d1b` (`test_the_ration_comes_before_the_cohort_keep`,
  replacing the test that the keep spares the ration) and `test_ops_stall` (the funnel's two new keys).
- **Rollback.** The previous House release. Its code ignores the new verdict keys and the `*_cut:*` kv rows. The
  families M3 retired stay retired.

### The weekend fixes, ops side, on `wfix/ops` (unreleased; a gateway deploy FIRST, then an owner deploy on main `cf96b72c`; no evidence reset)

The readiness audit of Oct 9 (`scratch/ready-1009/FIXLIST.md`: M6, M7, M8, M9, M12, m11) and the pinned amendment
DONE-RULE-A1 (sha256 `333bad06...`: A1.1-A1.4). Operator's page: **The weekend fixes, ops side** at the top of
`docs/operations.md`. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint
(`31a7e921`), the money digest (`0310779c`), the constitution digest (`ca89ff8a`) and the gate contract (`397b22b7`)
do not move, so no ratification and no Probe program leaves its band.
- **The stall alarm** (`league/ops/stall.py`, `gateway/lib/email.mjs`): four causes, `dlane` (the lane's warning alarms;
  K5 the owner's step), `done` (A8, told at once), `preopen` (a pre-open FAIL) and `forward` (a late ready file, a
  nightly error 6 h, a nightly stop 2 h); `owner_deploy` waits 45 minutes and is skipped while a deploy is in flight.
- **The Done meter** (`league/ops/dlane_report.py`): consistency must be measured on 2 programs (A1.1); item 7 read per
  UTC day from the swarm store and the `budget` and `stall` receipts, the operator's edits listed (M7); a reading is
  final only once its replays landed and its broker fees posted, then frozen, and A8 fires only on a final one (A1.4,
  M8); Net after costs from the close economics beside each meter (M9); P(Done | zero edge) 0.024 with its horizon and
  source (A1.2; `policy.json` 0.13 -> 0.024).
- **The program loss line** (A1.3; `league/swarm/dlane.py` `program_loss_usd`, `policy.json` -200): each Probe row
  carries its program's realized Probe net and when DM1 can first fire (17 trades at the live sigma); the `dlane` job
  retires swarm-side a program whose realized Probe net is at or below -$200 (exits go on; alarm PL1).
- **The report's m11:** exact closes for the buy-and-hold or a why, finished sessions only in the `direction` job's
  file, real opens in the funnel, E0's basis said as it is.

### The per-close fill replay, on `wfix/replay` (unreleased; an owner deploy on main `cf96b72c`; no evidence reset)

The readiness audit of Oct 9, blocker B1 (c). Operator's page: **The per-close fill replay** at the top of
`docs/operations.md`. Every real close of an agent program gets its own replay twin: the real trade's own orders (its
contracts, the open's decision minute, limit, size and time in force, each close order the venue received), replayed by
a fixed Gym program on the gate image with the Gym's own engine and fill model, one gate job a close over the trade's own
sessions. Done item 4 then compares each close with its own twin instead of a nightly replay that may not trade the day
the real program did (pid 41 has no nightly match: v17's replay holds Oct 8 to Oct 12).
- **New:** `league/ops/twins.py` (the puppet program, the plan from the live book read-only, the verdict, the round);
  `league/swarm/loop.py` runs it as its own round after the nightly forward; `league/swarm/settings.py`
  `forward.twins` {max_jobs 12, attempts 3}, null or false is off. Records in the swarm store's kv `close_twins`.
- **The report:** `league/ops/dlane_report.py` `replay_gap` matches a close with a priced twin to it, never matches a
  close with a final unpriced twin (no_fill, no_contract, unpriceable) to the nightly replay instead, and falls back to
  the nightly (version, day) match only for a close with no record; with no record the figures are D5's key for key.
  `replay_twins` lists every counted close with its verdict, both returns on maximum loss, the gap and both exits.
- **Walls.** Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint
  (`31a7e921`), the money digest (`0310779c`) and the gate contract sha (`397b22b772b3`) do not move (checked at the
  branch head). No band, forward record, trial count or money moves; a twin is not a research run.
- **Proof.** `league/tests/test_close_twins.py`: the plan on the live book's own shapes (pid 14's and pid 41's), the
  puppet through the real batch runner on a synthetic gate store (the exact contract among decoys, the Gym's expiry
  close, a program close on its day and minute, a vertical left to expire, the model's no-fill, a contract missing at the
  minute, an image without the entry day), the round (one gate job a close, no run row, only once the image holds the
  exit day, never a House route, retries per ready day, the switch), the loop's round, and the report's matching.
- **Rollback.** The previous House release: it never reads `close_twins`.

### The budget split and the graveyard's report row, on `fix/budget-split-sail` (unreleased; an owner deploy on main `d70e00c3`; no evidence reset)

Two operator decisions of Oct 9 (about 16:00Z). Operator's page: **The budget split** at the top of
`docs/operations.md`. Base: main `d70e00c3` (release L-D, D-1, D-1b and the graveyard); PR #520 (the direction Train
map) was still open and is not in it. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the
execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the constitution digest (`ca89ff8a`) do not
move, so no ratification. An owner deploy: `league/ops/` and `league/swarm/policy.json` are FORBIDDEN to the updater.
- **The split** (`league/ops/budget.py` `SPLIT`): Sail 0.6 / Claude 0.4 -> Sail 0.8 / Claude 0.2. THE OWNER'S CEILING
  stays $25 a day: Sail $20 and Claude $5 (was $15 and $10). Why, measured read-only on the House's swarm store (Oct 7
  19:30Z to Oct 9 15:37Z): DeepSeek V4 Flash researched as well as Claude Sonnet 5.5 at 38x lower model cost per Train
  run and 3.3x (95% CI 2.2-5.1) more families reaching the Train bar per research dollar; Claude's researchers had no
  Validation pass (0 of 3); the first real Probe trade (eqp-realcalm-drift-call v17, 14:26Z Oct 9) was written entirely
  by Flash. The operator turned the Claude research band off in `swarm.json` (`researcher.claude_top` 0,
  `claude.role_usd_day` researcher 0, architect 0), leaving Claude the gate's review and audit and the strategist
  (about $2 a day or less, estimated), so the unused Claude share moves to Sail (Gym boxes and Flash research).
- **Derived in the same release:** the floor $4 Sail / $1 Claude (was $3 / $2); at the ceiling 7 Gym boxes and $0.33 an
  hour of Sail model pace (was 5 and $0.25), every Claude line at most $5, Sail's gate reserve $2.00 (was $1.50),
  Claude's room $5 for the audit, $3.70 for the review and $3.05 for every other role (was $10, $8.70, $8.05).
  `policy.json`: `gym.max_boxes` 5 -> 7 and `researcher.sail_usd_per_hour` 0.25 -> 0.34 (so the policy lets Sail's $20
  reach its knobs), `claude.role_usd_day.strategist` 6 -> 3 (its line leaves the gate's holds inside $5). The engineer:
  `usd_day` $4 -> $3 and an attempt's cap $3 -> $2 (review $1), so an attempt and its review fit a day.
- **Its cost.** Sail drains faster: about $21 a day with its fixed cost at the ceiling (from about $16), so for the
  same balance the owner's two-day funding notice comes sooner. Claude's line is $5, of which the gate's holds keep
  $1.95: the strategist, the post-mortem and the engineer share at most $3.05. At the floor Claude's $1 is under the
  gate's holds, so the review (and the audit, unless its hold is at most $1) runs on its Sail model with the gate's
  "not the plan's reviewer" alert; at the old $2 one review and one audit fitted. The engineer's attempt is a third
  smaller. The box's `swarm.json` wins over `policy.json`: where it sets `gym.max_boxes` or
  `researcher.sail_usd_per_hour` (last recorded Oct 8: 2 and 0.5) those still cap Sail's spend under the $20.
- **The day's figure.** RULE_VERSION and the schema stay 2: an old `budget.json` is read held to the new shares, so
  Claude is at most $5 at once and Sail keeps the day's figure (at most $15) until the next UTC day's first budget run
  (00:30Z) sets up to $20.
- **The `dlane` report's header** (`league/ops/dlane_report.py` `LOOSENED`, the owner's goal of Oct 9, item 5) adds the
  direction graveyard rule (PR #519, deployed 12:44Z Oct 9) with its cost: more direction births may retry ideas
  similar to dead alpha ones; each lineage still gets one Validation try and one look, at D2's measured
  false-positive rate of 10.4% per program. The Train map (PR #520) is not listed: it is not in this base.
- **Proof.** `test_ops_budget` (the ceiling $20 / $5, the floor $4 / $1 and its Claude dollar under the gate's holds,
  the taper day by day, the day's figure, the two-day lead, Claude's room by stage), `test_swarm_settings_policy` (the
  committed policy reaches the $20's knobs; the paid-model lines), `test_ops_jobs` (pre-open check 5 at the $4 floor),
  `test_ops_engineer` (the $3 line, the $2 attempt) and `test_dlane_report` (the new header row). Examples that tapered
  under the old shares were moved to balances that taper under the new ones. `test_swarm_frontier_routing` and
  `test_swarm_graveyard_digest`, which do not judge the budget, lift Claude's share in their fixtures: $5 less the
  gate's holds is under the post-mortem's 64,000-token OpenAI hold (about $4.90; OpenAI is closed by the budget in
  production anyway).
- **Rollback.** The previous House release: its code reads this release's `budget.json` held to the old shares.

### The direction lane's Train map, on `feat/dlane-trainmap` (unreleased; an owner deploy, gateway first; no evidence reset)

Births aim at the call shapes that pass direction-v2 on the Train years, instead of searching for them. After the first
direction program reached real money (2.4 h after D-1b), 7 of the 8 other direction families had no eligible version,
mostly on E1. Operator's page: **The Train map** in the Release D-1 section of `docs/operations.md`.
- **The map** (`league/swarm/dlane_map.json`, new, protected). It comes from the operator's census of SPY, QQQ, IWM and
  one-on-each-root call cells, scored by the House's own `dlane.train_score` and `robust_verdict` (main `d70e00c3`) on
  2022-24 data only, one lot at natural prices: 30 of 3,136 cells pass. Every passer is a 0.20-delta call held 2-5
  sessions, in the market all three Train years. The file is reduced to what agents may see: each shape in words, its
  S_D to one decimal, the unit's verdict as a word, and three lessons. Its header carries the label, `built_at`,
  `inputs_sha256`, `source_sha256`, and the commit, `dlane.py` sha and bar settings it was scored under. There is no
  dollar figure, price level, price ratio, per-year P&L or year outside 2022-24.
- **Who sees it** (`league/swarm/dlane.py` `train_map`, `train_map_text`, `train_map_brief`, `map_on`,
  `map_text_problems`). The architect's LANES block gets every passing shape (one line each, at most 30), the lessons,
  and "aim at these shapes and vary the gate, the hold or the root". A direction researcher's brief gets the lessons and
  the 5 best passing shapes on its roots. Both carry the label "in-sample: Train years 2022-24, from the operator's
  census at one-lot natural prices; the screen decides". A shortfall request's opening line points at it.
- **The reader** is cached and never raises. A missing, malformed or unsafe file (a refused year, a `$`, a figure, a
  wrong label or objective, one bad row) reads as no map.
- **The switch:** `league/swarm/policy.json` `dlane.train_map` true. swarm.json false hides it at once, and the code's
  default is false. Off, and with `dlane.mode` "off", every text is main `d70e00c3`'s byte for byte, and so is the
  alpha lane (golden digests computed on that commit).
- **Its cost** (a reported loosening: agents now read an operator study's Train-year figures): births aim at
  in-sample winners. The screen's false-positive rate per program is unchanged, but more programs reach the screen, so
  there are more false passes in count. The `dlane` report's header lists it (`league/ops/dlane_report.py`
  `LOOSENED`), together with the graveyard row deferred to this owner deploy.
- **Walls:** `league/ci.py` FORBIDDEN and the gateway's `protected.mjs` gain `league/swarm/dlane_map.json`, as for
  `dlane.py`. The gateway needs `npx wrangler@4.129.1 deploy` first; until then the deployed merge route does not
  refuse an edit to the map, but the updater does. The execution fingerprint (`31a7e921`), the money digest
  (`0310779c`) and the constitution digest (`ca89ff8a`) do not move.
- **Proof.** `test_dlane_trainmap` covers the switch, the reader's refusals, the secrecy of every text (no
  dollar-looking or price-looking digit run, no year but 2022-24, no provenance hash), each lesson's claims about the
  passers against the file's rows, length bounds, the alpha and rollback goldens, the report row and the wall. The
  operator's private figures are never in the repo: the tests read them from the file `LTCM_PRIVATE_FIGURES` names
  (skipped without it). `test_dlane`'s committed-settings test gains `train_map`.
- **Rollback.** swarm.json `dlane.train_map` false (instant), or `floor_box.py rollback`.

### The direction lane's graveyard, on `fix/dlane-graveyard` (unreleased; an updater release on top of D-1, live since 10:37Z Oct 9 as main `2b60d94a`; no evidence reset)

The operator's decision after the House's architect pass of 11:32Z Oct 9, **a reported loosening**. Operator's page:
**The graveyard** in the Release D-1 section of `docs/operations.md`. Swarm-side only (`league/swarm/cards.py`,
`league/swarm/architect.py`, tests, docs): no `league/live/`, `league/gym/`, `league/constitution.py` or other
protected path, so the updater ships it. The execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the
constitution digest (`ca89ff8a`) do not move.
- **What was wrong.** Live D-1 refused direction cards on alpha graveyard rows: low-iv-drift-call and
  calm-trend-drift-call were refused because their mechanism text reads as the trend_momentum cell, which holds dead
  alpha rows (the refusal: 15 rows, 7 that need a claim, the newest persistent-ceiling-rejection-put, REFUTED). Those
  verdicts judged timing edges against drift under the alpha rules. They say nothing about a direction program, which
  direction-v2 judges as labelled beta, under the lane's own multiplicity control (one Validation try and one look per
  lineage, D2's false-positive rate measured per program).
- **The rule.** While `dlane.mode` is not "off", a DIRECTION card is bound only by the graveyard rows of DIRECTION
  families. A row's lane is read the way D-1 stores it: the family's spec `lane`, else its card's `lane`, else its
  `card_sha`'s card for a fork. A family with no lane is alpha. DRIFT rows still never bind a direction card. A
  direction family's REFUTED, MECHANISM or other verdict row still needs the full rebirth claim with its budgets. A
  claim a direction card makes on an alpha row is checked as one on a DRIFT row: a rebirth only when it holds, otherwise
  dropped. Alpha cards are unchanged: every row binds them.
- **The architect's view.** The LANES block and the BIRTH CELLS header say what binds a direction card. Each cell line a
  direction card may land in counts the rows that bind one, so no alpha row reads as closing a direction cell. `closed`
  (no paid pass without a cell) follows the same rule. A direction birth's `swarm.born` card carries `alpha_rows`.
- **Its cost.** More direction births may retry ideas similar to dead alpha ones. Each such lineage still gets one
  Validation try and one holdout look, at D2's measured false-positive rate of 10.4% per program (mixed worlds). The
  `dlane` report's loosened-rules header (`league/ops/`, an owner-deploy path) lists it from the budget split (above).
- **Proof.** `test_dlane_graveyard`: a direction card in a cell of alpha REFUTED and MECHANISM rows only is admitted
  (the live example among them); a direction family's REFUTED row still needs a claim; alpha cards' verdicts and every
  reading with `dlane.mode` "off" equal main `2b60d94a`'s on a fixture store (golden digests computed on that commit).
- **Rollback.** Revert the commit (`dlane.mode` "off" rolls back the whole lane).
- **Known, not changed:** with `architect.max_rebirths_per_cell` 0, a claim that passes every other test raises
  `KeyError` in `RebirthIndex._claim` (it reads `cell_births[cell]` for a cell with no rebirth yet). No deployed
  setting reaches it (policy.json sets 12).

### Release D-1b, the direction lane on D2, on `release/dlane-d1` (unreleased; in D-1's owner deploy; no evidence reset)

On top of D-1, same branch, same deploy. It switches the direction lane to the D2 screen and meets the owner's goal of
Oct 9: item 4, a pre-registered screen whose measured false-positive rate is at most 15% per program, stated beside
every Probe trade; and item 3, "Tell me 2 days before Sail or Claude runs out". It is Claude's decision DSCREEN-ADOPT,
**a reported loosening**. Operator's page: **Release D-1b** at the top of `docs/operations.md`. Swarm-side and ops
only: no `league/live/`, `league/gym/` or `league/constitution.py` change. The execution fingerprint (`31a7e921`), the
money digest (`0310779c`) and the constitution digest (`ca89ff8a`) stay release L-D's (deployed 09:04Z Oct 9, below).
- **D2 on** (`policy.json` `dlane.screen` "D2"; receipt `docs/benchmarks/direction_screen_2.json`, sha `c3605947`,
  pinned in `dlane.screens.D2` with c 1.00 and the lane's figures; CI holds the sha and every figure to the receipt).
  - The rule: on Validation, 50+ trades on 25+ entry days and a mean entry-day return above zero; after the one look,
    the pooled entry-day t over Validation and the holdout at least 1.00 and the holdout's P&L above zero.
  - The statistic is DSCREEN-2's own on exact figures (to 3e-15). On the Gym's rounded summaries the gate judges its
    lower bound over the rounding, so no pass comes from rounding.
  - The rollback is swarm.json `dlane.screen` "S-C", at once. The alpha lane is untouched.
- **Its cost, measured** (the receipt): the lane's false-positive rate per program at zero edge goes from S-C's 1.41% to
  10.37% on mixed worlds (9.57-11.16%) and 12.39% on 2022-24 worlds (upper bound 13.29%). All cells reach 13.37% and
  14.11% (upper bounds 14.08% and 15.01%). Power at +10% goes from 3.22% to 19.95%. D2 was adopted after it failed the
  operator's own 12% adoption rule: a post-hoc loosening, listed in every `dlane` report's header.
- **Calls only:** `dlane.structures` ["long_single"] (no direction debit vertical, no put), and D2 runs only while the
  lane is calls only. New Train bar C1: a direction program whose Train trades hold a put or a short leg fails it.
- **One Validation try and one holdout look per direction lineage** (`dlane.val_tries`, `looks_per_lineage`, fixed at
  1), so a lineage's false-positive rate is the program's.
  - The tournament guards the try (`dlane.try_open`; one lineage member a round; `spent_lane` and `waiting_lane`, which
    the stall alarm reads). As a backstop, a late second try never reaches the gate.
  - The gate's ration is 1 for a direction lineage. A lineage that has used either without a pass still in play
    retires (`dlane.lineage_spent`), and a direction family never forks once its lineage has tried.
  - The alpha lane keeps its counts.
- **The false-positive rate beside every trade** (operator-facing only): each direction look's line and event carry
  `screen`, `fp_lane_mixed`, `fp_lane_2224` and `receipt`. The fast lane's band rows carry `fp`. The `dlane` report's
  new `fp_beside_trades` lists every real Probe trade and every agent real close with its program's screen, its rates
  and the contamination statement.
- **The meter warning:** the `budget` job's `funding` notice now goes when research on a meter runs out within 2 days
  at its current burn (`out_in_days`, `burn_usd_day` in `budget.json`; at the ceiling the same 7-day card line). It
  goes at most once a day per meter (it was once a week), under a per-day notice id. The channel and the facts' names
  are unchanged.
- **The review's fixes** (Oct 9, on the D-1b build):
  - *The try is always judged.* A direction lineage's first Validation try is judged even when the researcher moved the
    candidate on while its job was out (it was dropped as stale, spent the try and retired the family unjudged). A try
    with no verdict, or whose verdict in the gate is on another Gym image, is validated again as that version
    (`dlane.try_owed`). A family whose own try has no verdict is not retired.
  - *The screen at the result.* A direction look that entered by D2's pre-check alone and lands after the rollback to
    S-C fails closed (`gate.PRECHECK_UNDER_LINE`); the look's marker records how the version entered.
  - *The calls-only code check* (`dlane.calls_only_code`): a direction program whose text names a put, a short leg or
    any open but `long_call` is refused by the researcher before any version, never validated by the tournament
    (`calls_refused`), refused by the gate ("calls only") and failed by the incubator's review. Still open: a type built
    at run time from other pieces, and no live-side calls-only guard: release L-D shipped without it, the live path
    still admits a `long_put` for a `long_single` family, and the guard waits for the next `league/live` release (a
    fingerprint move, rule F0).
  - *The burn in the mail.* A notice fired by the burn states the burn as the mail's "now" figures and the day research
    runs out at it as the add-by date, so it never says "Nothing stops" while research runs out within 2 days.
  - *A screen beside Probe trades only.* The `dlane` report states a look's screen only beside a `:r` trade opened at or
    after that look; tuition and incubator closes state none.

### Release D-1, the direction lane, on `release/dlane-d1` (unreleased; an owner deploy after release L-D; no evidence reset)

A DIRECTION research lane beside the unchanged ALPHA lane, in which profit from the index's direction counts, reported
beside the same-risk buy-and-hold and never called alpha: it is leveraged index beta minus option costs, and an
always-in call program can pass its bar. Claude's decisions under the owner's goal of Oct 7 (items 4 and 5), after the
plan of Oct 9 and its critic. Operator's page: **Release D-1, the direction lane** at the top of `docs/operations.md`;
the design is in `docs/design.md`. Swarm-side only: no `league/live/`, `league/gym/` or `league/constitution.py` change,
so the execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the constitution digest (`ca89ff8a`) stay
release L-D's: no evidence reset, no evaluator adoption, no re-ratification.
- **The lane's core** (`league/swarm/dlane.py`, new, protected: `league/ci.py` FORBIDDEN and the gateway's
  `protected.mjs`, so the gateway is deployed first): settings and bounds (`policy.json` "dlane", mode "gate"; the code's
  default "off" is the rollback), the lane, the Train bar direction-v2 (E1, E3, E4, E5 at 1.0x; P1, R2, R3 at 1.5x; E2,
  R1 and the mechanism test reported only), the live unit (today's closes and equity; "unknown" passes), the incubator's
  direction mark, the screen (S-C for direction; S-B for alpha byte for byte; D2 refused until a receipt is pinned), the
  direction leakage alarm (10 looks, over 60%), K5, the birth quota, the agents' text and the pinned Done rule's
  constants.
- **Cards, architect, allocation, strategist:** `card.lane` and the `equity_premium` class; graveyard DRIFT rows do not
  bind a direction card; the architect's LANES block, `DirectionQuota` (direction about half of births while behind, at
  most 60%) and the `lane_only` request after 12 h without a direction birth; the strategist's inputs per lane.
- **Researcher:** a direction family is scored by direction-v2 and demoted on a failed 1.5x rule; its brief, status and
  views carry the lane's text; the ROLE prompt is lane-aware.
- **Game, gate, evidence, incubator, tournament:** no hidden look for a direction lineage (`dlane.arm_fraction` 0) and
  direction kept out of the game's R1(b) and R2; the look's screen per lane, recorded on each look event (lane, screen,
  receipt); the leakage alarm per lane; the incubator's direction mark (refused while the lane is not "gate"); the
  tournament writes `validation_r_sd` beside `typical_max_loss_usd` for L-D's DM1.
- **The `dlane` job and report** (`league/ops/dlane_report.py`, new; at the House's start and daily 01:30Z; in a pause
  too; operator-only; read-only but for K5's kv; no site data contract change): `<state>/dlane-report.json` with the
  funnel per lane (24 h, 7 d), the Probe envelope (release L-D's two envelopes read from the constitution through
  `money.Table`, the window's and the total's figures under GROSS and NET, the binding room), THE DONE METER of the
  pinned rule (DONE-RULE sha256 `0d007696...`: `done_screen` `:r`, `done_all` `:r`+`:t`+`:i`; 30 closes, 5 from each of
  2 programs, net > 0 after fees, consistency over 5+ matched closes, read only at the 30th close and every 10th; beside
  it P(Done | zero edge) 0.13, the same-risk buy-and-hold delta-matched and in dollars at risk, the screen's
  world-conditional false-positive rate, every loosened rule with its cost and the contamination statement), the account
  and the research costs, the contamination meters per lane, and alarms A1-A9 and K5 as House alerts. K5 is automated:
  at a direction realized net at or below -$600 the job sets the kv `dlane_k5` and the lane reads "shadow" until the
  operator clears it; the job's next run records the clear and re-arms K5 at -$600 below the net at clearing (kv
  `dlane_k5_base`). `league/ops/fast_lane.py`'s rows gain `lane` while the lane is on; the learning game's report says
  what the lane changed mid-experiment.
- **The agenda guard** (D9): the swarm warns the House at its start, and whenever it changes, when `swarm.json`'s locked
  preamble or fallback agenda is over 4,000 characters, not ASCII or names a hidden year; the new operator tool
  `scripts/agenda_install.py` (check, apply) refuses such a text and installs a good one with a before-copy, an atomic
  replace and the strategist's section cleared.
- **Every loosened rule, with its cost** (the operator's measurements): beat-your-exposure for alpha only; direction-v2
  in place of the worst year (more null programs reach Validation; the false-positive rate per program screened is
  unchanged); no hidden look (the lane's false-positive rate at zero edge 0.02% -> 0.70%); S-C (the lane 0.70% -> 1.41%,
  2.22% when both windows rose; power at +10% 1.68% -> 3.22%); the direction leakage alarm at 60% (a leak trips later);
  the incubator's direction mark (with no edge about -$36 a week, at most $150 a week, never evidence); DRIFT rows not
  binding direction cards; **the birth quota: alpha births fall from about 73 to about 36 a day mid-way through the
  learning game's T0 experiment, and the ROLE prompt change reaches alpha researchers too (a shared prefix), so "alpha
  golden" holds for code paths only**; the unit at 10% of equity rather than MONEY's $75 (Probe-stage Done 6.3% against
  7.8%, P(net <= -$360 in 8 weeks) 0.35 against 0.27); **K5's clear: `dlane.k5_clear` true disarms K5 while it stays
  set** (the report warns every run until it is taken out).
- **The review's fixes (Oct 9, before any deploy):** with the lane off, the one leakage alarm counts only the looks the
  alpha line judged (direction looks judged on S-C never stop the alpha lane; a code rollback to the release before
  counts every look, so `docs/operations.md` says to check the pooled pass share first); a direction family never takes
  its lineage's game or control arm (born under a control-arm parent, a game lineage's member from before T0, or left in
  a lineage an alpha family was given an arm in); K5's clear is durable and re-arms from the net at clearing; the
  direction quota reserves no more births than the room left under `architect.max_alive_per_class` in the lane's classes
  (`long_single x etf`, `debit_vertical x etf`), and class-capped direction cards are named apart (`lane_class_capped`);
  no agent text carries a figure priced at today's closes or the account's equity (E5 is its verdict and a scale-free
  hint: this overrides HARNESS 6's `scale` in the view on secrecy grounds); the brief's vertical guidance is a lane rule
  with no Train provenance. Joins from the integration: the public checklist's `gate_paused` reads the family's own
  lane's alarm, and a direction parent's fork carries `lane` in its `swarm.born`.
- **Joins with release L-D** (main `40c39435` merged into `release/dlane-d1` after L-D's deploy): the `dlane` report's
  Probe envelope reads L-D's rolling budget from the constitution (`real.probe_figures` told each basis; alarm A4 reads
  the binding envelope's room, A5 names `probe.demotion`); the tournament's `validation_r_sd` keys are the ones
  `league/live/families.py` reads, tested end to end (`test_dlane_ld_joins`).
- **Owner steps, in order** (docs/operations.md): L-D deployed and verified (done 09:04Z Oct 9); CI green on main's
  head; the gateway (`protected.mjs`) deployed; `floor_box.py deploy` in the money path's window with no order in
  flight; verify (no fingerprint or digest move, `lane_births` on the first pass, the `dlane` report written); install
  agenda v21 with `scripts/agenda_install.py`. Rollback: `dlane.mode` "off" in `swarm.json` (read every loop, no
  restart; every path as before D-1), agenda v19.1 back with the same tool, then `floor_box.py rollback` if the code
  must go.

### On branches, not in V3-A part 1

- `v3/wp6`, the forward ladder and its benchmark (evidence v3, the owner's D2). As first specified it does not meet its
  benchmark rule. A tighter design was frozen before any confirmation run; the confirmation, under a rule
  pre-registered before it, has not been run. It changes `league/live/` and the constitution: an owner deploy and one
  more evidence reset.
- `v3/wp7`, credit types at $2,000 of equity or more and a paper proof per type (money rules v3, D3), with the
  gateway's credit list: an owner deploy and a money-digest move. With the ladder it is V3-A part 2.
- `v3/b1` (research v3), `v3/b23` (births from the mechanism library, the Train kill tests as code, the strategist's
  whole agenda), `v3/b4` (the weekly post-mortem and the monthly cost review), `v3/b5` (the engineer and the reviewer).
  Each changes a protected file as it stands (`league/swarm/settings.py`, the store, the evidence and tournament
  modules, `league/ops/`), so each is an owner deploy, not an updater release.

## 2026-10-09

### 09:04Z, release L-D, the Probe budget read NET and rolling: House release `20261009T090334Z-cdbf1864a573` (main `40c39435`; PR #517), money digest `1665c385` -> `0310779c`, evidence reset 5

Owner deploy. PR #517's Checks green on the exact head `5a37227e`, merged as main `40c39435` (tree-identical to it);
main's Checks green 09:03Z. No order in flight at 09:03:25Z (the House live test's QQQ position open, carried); the
nightly stopped, `floor_box.py deploy`, PROMOTED 09:04:19Z (previous `20261009T025942Z-376c84971b5e`), the nightly
back 09:14:32Z. Verified on the box: real money on, no failures; the Probe row as built (`max_open` 8, `loss_basis`
"net", `demotion` "dm1", `loss_budget_usd` 400, `loss_window_sessions` 20, `loss_total_usd` 400); constitution
`ca89ff8a`, money `0310779c`, the standing grant re-ratified `1665c385` -> `0310779c` at the House's start; the
execution fingerprint `31a7e921` and the evaluator adopted (the Gym bundle `gym-engine-4-e1c896f8d304` unchanged);
the practice cohorts completed (0 active: 40 complete, 5 failed), as planned. Local full suites green on 3.11 and
3.14 (7,698 + 2,005). As built:

The one planned evidence reset of Oct 9 (the plan of Oct 9, "L: Release L-D", and its critic). Claude's decisions under
the owner's goal of Oct 7, item 4 (Probe sizing up to 10% of equity a position, a Probe loss budget up to $400 in total)
and item 5 (every loosened rule reported with its cost), and, for the budget's two figures (L9), the owner's goal as he
re-set it on Oct 9 (about 06:20Z), item 4: "Probe loss budget: $400 net in any rolling 20 sessions and $800 net in
total (realized Probe losses net of Probe gains, plus the maximum loss of everything open)". The 10% is unchanged.
Operator's page: **Release L-D** at the top of `docs/operations.md`.
- **L1, the budget read NET** (`options_money.probe.loss_basis` "net"; allowed exactly "gross" and "net"). THE PROBE LOSS
  BUDGET's realized part is max(0, -(the summed cash of every closed position a Probe family opened)) from inception, in
  place of GROSS (`real.probe_tally`, now told the basis by `money.Table`; the envelope: realized + every real
  position's open maximum loss + the new open <= $400, two envelopes since L9). A Probe gain offsets Probe losses; a
  Sized gain never does.
  It reverses the fast lane review's deliberate GROSS choice of Oct 7. The refusal, the House warning and the fast lane
  report's `realized_basis` name the basis in force. Cost (MONEY, U10%-M3, no edge, 8 weeks): P(net <= -$360) 0.19 ->
  0.27, mean net -$8 -> -$14 (as traded -$45 -> -$64); Done 0.3% -> 2.6% (+5% edge, averaged over holds). Its main
  effect (the critic, B2, 12 weeks): gross Probe losses pass $400 on 46-72% of paths by hold (p95 $1,318-2,088), the
  Probe's realized drawdown passes $400 on 32-48% (worst $2,385), net Probe < -$400 on at most 0.5-2.5%; under GROSS all
  stay at or under about $440. NET is the loosest of GROSS / a high-water mark / NET (12-week Done at zero edge, 3
  programs, 3-session holds: 0.5% / 3.3% / 12.9%).
- **L2, 8 Probe slots** (`probe.max_open` 3 -> 8, bound 0-3 -> 0-8). The $400 envelope, not the count, bounds open Probe
  risk (three $129 units fit, eight $50 ones). Cost: P(net <= -$360) 0.30 -> 0.35, P(net < -$400) 2.1% (through Sized,
  outside the budget); Done 3.3% -> 6.3%. **The Probe room** the incubator, the House live test and the calibration keep
  is now min(`max_open` x 10% x E, $400) (`money.probe_room`; the critic, B1: 8 x 10% x E, $1,031.47 at E $1,289.34,
  would refuse every incubator open); at 3 slots it is fast lane v2's at any E up to $1,333.33.
- **L3, DM1 demotion** (`probe.demotion` "dm1"; allowed exactly "dm0" and "dm1"). For Probe and Sized families, D5's loss
  leg and the forward-negative demotion are off; demoted (sticky, exits only) at 10+ real trades whose returns on
  maximum loss sum below -1.645 x sigma x sqrt(n), sigma the banded version's Validation sd (read from the swarm's state
  by `league/live/families.py` `validation_r_sd`; its writer ships with release D-1), else the forward record's sd, else
  2.0. The replay-gap leg and the real_bad hold are kept; a Candidate keeps every "dm0" check; the live state keeps
  the version DM1 demoted (`dm1_demoted`), held at Candidate whatever sigma or the rule reads later. The band, the open's refusal and the admission read one rule. Every Probe or Sized family,
  alpha too. Cost (the critic, 4,000 bootstrap paths): fires within 30 closes 6.5-13% at zero edge, 14-22% at -0.10,
  29-36% at -0.25 (D5: 77/83/90%): the $400 envelope, not demotion, mostly stops a losing program. MONEY: P(net <=
  -$360) 0.27 -> 0.30; Done 2.6% -> 3.3%.
- **L9, THE ROLLING PROBE BUDGET** (the owner's goal of Oct 9, item 4). `probe.loss_budget_usd` ($400) is now over the
  last `probe.loss_window_sessions` (20) New York sessions, today included (the repo's NYSE calendar,
  `ltcm.data.us_equity_session`; `real.probe_window_start`), beside the new `probe.loss_total_usd` from inception, set
  to $400: the owner's $400 a window is a wall, read as its worst net stretch, and his $800 in total a ceiling (the
  operator's decision of Oct 9, after the budget simulation's worst-stretch run); each realized figure read by
  `loss_basis` (`real.probe_realized`, `real.probe_figures`). Under "net" the window's figure is its WORST NET STRETCH
  (the review of L-D: with the window's plain net a gain that aged out left more than $400 net in a later 20-session
  window, every open having passed), so a Probe gain offsets only the losses closed before it there and the $400 holds
  over every 20-session window as an outcome; the total is the net from inception. A Probe open must fit BOTH
  envelopes, each with every real position's open maximum loss and the open (`money.plan_open`); the refusal names the
  one that binds; exits go on. The House warning and the fast lane report (`realized_total_usd`, `total_budget_usd`,
  `window_sessions`, `window_start`, `binding`) show both figures with the basis. Bounds: window 20-2000 sessions (a
  longer window is never looser), total $0-800 (raising it to $800 later is CON-only: a money-digest move, no
  fingerprint move). Cost, as set: the worst net Probe loss from inception stays $400, and the window adds a second
  wall; a bad stretch that ages out of the window frees no room in the total. Measured (budget simulation, Oct 9,
  worst-stretch variants, seed 202610097, post-hoc, as traded, holds 2 / 3 / 5): P(Done) 6.0 / 3.3 / 1.0% at 12 weeks
  and 11.1 / 8.7 / 5.9% at 24, P(net Probe < -$400 within 12 weeks) 0.9-2.1%, P(the 60% drawdown stop by 24 weeks)
  3.0-8.3%; with an $800 total 7.0 / 3.7 / 1.1%, 14.0 / 10.9 / 7.2%, 37.6-39.2% and 41-46%; with the $400 total and no
  window 10.0 / 7.6 / 4.5%, 11.0 / 9.0 / 7.6%, 1.3-2.8% and 8.2-13.0% (the table is in `docs/operations.md`).
- **L5, the marketable natural limit `{"natural": k}`, dropped** (the operator's decision, Oct 9 about 07:40Z). It
  changed `league/gym/legs.py` and `league/gym/PROGRAM.md`, which moved the Gym bundle (`gym-engine-4-e1c896f8d304` ->
  `gym-engine-4-460b332db232`), so at the adoption no stored Train or Validation result would have been reused (every
  one re-run on the 2 Gym boxes the direction lane shipping that day needs) and the 2017-19 extension holds would have
  been cleared; `{"price": v}` already lets a program pay through. It waits for a planned Gym release (rule F0).
- **Not done: the narrower fingerprint** (the critic, N8): `league/live/money.py` stays hashed, because the practice
  book's caps read `money.Table` and the incubator's first-look rule lives there.
- **Identities.** Constitution digest `5698a2f9` -> `ca89ff8a`; money digest `1665c385` -> `0310779c` (the standing
  grant re-ratifies at the House's start on the owner's deploy); the execution fingerprint `b4c34031` -> `31a7e921`
  (league/live changed): the evaluator adoption re-derives every family's bests, and every active practice cohort is
  completed ("evaluator changed"), the 10 still active of the 12 admitted Oct 8 among them (their incubator first looks
  were expected about Nov 4-10). No family is banded. The Gym bundle does not move (`gym-engine-4-e1c896f8d304`,
  production's), so, as at fast lane v2, the re-derivation reuses recorded Train and Validation results and the
  extension holds stand.
- **Rollback.** CON-only: `loss_basis` "gross", `max_open` 3, `demotion` "dm0", `loss_total_usd` "400" (the value in
  force), `loss_window_sessions` 2000 (money digest `320899d6`, constitution `c9d8ef5b`), one owner deploy and no fingerprint
  move; each value runs fast lane v2's rule, decision for decision (`league/tests/test_ld_release.py`, against a frozen
  copy of `ccfa48d5`'s code; the 2000-session window holds every close since the fast lane). `floor_box.py rollback`
  moves the fingerprint again and, after D-1, drops D-1.

### 03:00Z, the cohort keep blocks every retire: House release `20261009T025942Z-376c84971b5e` (main `ccfa48d5`; PR #516)

While the saved incubator keep holds a family, its researcher's retire is not offered (the guard `cohort_keep`), the
mechanism test's retirement is deferred and the diagnostician's retire defers: after T0 researchers had self-refuted
three of the twelve cohorts' families, and the incubator pins only a living family's cohort. Swarm-side only: the
execution fingerprint `b4c34031` and the money digest `1665c385` are unchanged. Local full suites green on 3.11 and 3.14
(7,642 + 2,005), main's Checks green on the exact head; no open order at 02:59Z (the House test's QQQ position only,
market closed); PROMOTED 03:00:25Z; previous `20261008T225723Z-dea5c1d54c52`.

## 2026-10-08

### 22:58Z, the incubator unblock, the incubator cap and the contract's natural limit: House release `20261008T225723Z-dea5c1d54c52` (main `a5ff6f9e`; PRs #513, #514, #515), money digest `da5c7542` -> `1665c385`

Owner deploy. Main's Checks green on the exact head (gateway, 3.11, 3.14); local full suites green on both Pythons (7,639
+ 2,005). No order in flight at 22:57Z (the House test's QQQ position only, market closed); PROMOTED 22:58:10Z; previous
`20261008T190618Z-96ea9c702b14`. The `grant` job ratified on `1665c385` (trigger `digest`); `health.json` reads the
incubator table's `max_loss_usd` "75". The execution fingerprint `b4c34031` is unchanged: the twelve practice cohorts
carried over, under the 30-session window.
- **#513** (`league/CONTRACT.md`): "natural" is priced at the decision minute and rests when the market moves the
  program's way; to pay through, send `{"price": v}`.
- **#514, the incubator unblock**: the incubator's mark evaluates the drift screen itself at its defaults while the
  tournament's screen is off; a practice cohort's window is 30 sessions (`live.observe_max_sessions`, `practice.py`
  `COHORT_WINDOW`); the swarm loop queues Train and 1.5x re-runs for active cohort versions without a current mark.
- **#515, the incubator cap**, as built:

One money row moves: `options_money.incubator.max_loss_usd` "50" -> "75" (its bound in `OPTIONS_MONEY_BOUNDS` $0-50 ->
$0-75), Claude's decision under the owner's goal of Oct 7 (item 4 allows up to 10% of equity at risk per Probe position,
about $129 at E = $1,288; item 5 asks every loosened rule reported with its cost). Everything else is as it was:
`week_loss_usd` $150, `max_open` 4, `contracts` 1, the practice rule (3 sessions, 10 program closes, 0.80 coverage), the
Probe, tuition, calibration, the House test and the gateway's caps. Operator's page: **The incubator cap** in
`docs/operations.md`.
- **Why.** The Oct 8 incubator audit found the $50 unit cap refuses most one-lot units of the single-name cohorts, so a
  cohort that passes its first look often can never open ("could never open") or opens only its cheapest trades. Share
  of one-lot units (maximum loss plus open and close fees) at or under $50 -> $75 in the active cohorts' Gym Train
  trades: semis-lead-smallcap 4% -> 71%, smci-mara 40% -> 71%, opening-range 40% -> 62%, china-tech 55% -> 77%,
  peer-skew 50% -> 71%, index-corr 83% -> 98%, earnings-gap 10% -> 17%, megacap 0% -> 3%, semis-supply 2% -> 2%.
- **Cost (a loosening).** The row is two caps: a structure's maximum loss with fees, and a family's held and working,
  each $50 -> $75. The week's bound is unchanged ($150 net realized loss plus residuals; about $650 a month on average,
  $750 in a five-week month), and at most two $75 units are open at once (three $50 ones before). What rises is how
  much of that envelope a pass uses: replayed on the 10 live cohorts' eligible Train runs with the practice caps and the
  route's caps, with no edge after costs (-8% of maximum loss a trade), the expected real loss per first-look pass goes
  from about $0.40 to $2.45 at today's practice windows, from $2.22 to $25.53 at 30-session windows and from $5.52 to
  $26.59 at 40-session windows (maximum loss sent per pass $53 -> $145 and $71 -> $164); the worst simulated pass grows
  from -$272 to -$419 over 30 sessions and from -$310 to -$424 over 40 (several weeks, each inside $150). With zero edge
  the means are noise around $0. Alone it opens nothing: on this tree no cohort holds a Train-and-drift mark (the
  drift screen is off), and in the audit's replay 11 of 12 cohorts never reach the first look's 10 program closes
  inside today's windows.
- **Identities.** Constitution digest `5edc8956` -> `5698a2f9`; money digest `da5c7542` -> `1665c385`; the execution
  fingerprint `b4c34031` is unchanged (no `league/gym`, `league/live` or base-file change), so practice cohorts and
  bands carry over: no evidence reset. The updater never deploys it (the constitution is protected), and merging it
  holds the updater's later heads until the owner deploys main's head: deploy it right after the merge. The owner's
  deploy (`floor_box.py deploy`) writes the deploy row, and at the House's start the standing grant re-ratifies on
  `1665c385` by itself (`league/ops/grant.py`, `LiveGrant.standing`: a moved digest with an owner's deploy on record;
  `league/tests/test_standing_grant.py` `TheIncubatorCap`); verify the `grant` job's receipt says `ratified` with
  trigger `digest`, else `python3 scripts/live_trading.py --ratify` on the box. `health.json`
  `options_live.incubator.table.max_loss_usd` then reads "75". A rollback across it (`floor_box.py rollback`, an
  owner's release change) re-ratifies on `da5c7542` the same way.

### 22:17Z, the learning game's T0 (no deploy)

After the M0b retro's GO (c +0.44 [0.15, 0.68]), the operator's `t0_apply.py apply gate` at 22:17:02Z: `swarm.json`'s
`gym.train_from` deleted (the policy's 2022-01-03 applies), `game.mode` "gate", agenda v19 locked, the 2022 input card
installed (backups `swarm.json.before-t0-20261008T221702Z`, `input-capabilities.json.before-t0-*`). kv `game_t0`
"2026-10-08T22:17:18Z". The twelve practice cohorts carried over.

### 19:07-19:18Z, the learning game v1 (dormant until T0): House release `20261008T190618Z-96ea9c702b14` (main `7b71cb1a`; PR #512), gateway `8072b5b1`

Owner deploy. Main's Checks green on the exact head (gateway, 3.11, 3.14); local full suites green (2,005 + 7,619). No
order or position open at 19:06Z; PROMOTED 19:07:43Z; previous `20261008T124025Z-a9686c7cfcfd`. Money digest `da5c7542`
and the execution fingerprint unchanged. Gateway `8072b5b1-13af-4cf2-a47e-fd40b5b76b27` at 19:18Z (rollback `f63dd354`;
412/412): `protected.mjs` lists `league/swarm/game.py`. As built:

From T0 no agent sees 2020 or 2021 again; those two years, scored privately at 1.5x the half-spread and net of each
program's own exposure's drift, decide which programs reproduce and which reach Validation. Researchers keep working on
Train 2022-2024. `league/swarm/game.py` (new, protected) holds the rules; the build spec of Oct 8 holds their numbers.
- **Arms.** New core-five families split by their lineage's hash: half the game arm, half a concurrent control on the
  same seen years with the same hidden measurements as records. Families alive at T0, or born with another root, are
  legacy (today's rules). A family's first arm is kept (`game_arms`): a change of roots, a setting or the game switched
  off never moves it. Births are core-five only once the game has started.
- **Gate mode, game arm.** The look ladder (best by Train score, +0.5 over the last looked score, a profitable 1.5x seen
  run, 4 looks); a SELECT PASS (F >= 1.28) reads the CONFIRM year once (2 a family, 3 a lineage); only a CONFIRMED
  version goes to Validation, 2 tries; its Validation t never steers its compute; children of the top SELECT decile
  with a structural directive (a rotation of 12 that favours pricing, the structure's shape and a regime filter, which
  carried a half-found edge to unseen years in the Oct 8 planted-edge arena, over an input swap, an exit rewrite or a
  flip, which broke it) or a donor's execution (the child joins its signal parent's lineage only); three
  retirement reasons first; the dormancy clause spares such a family only while a CONFIRMED version awaits Validation
  or a look is out.
- **Blindness.** The architect and the strategist never read a game-arm family; every graveyard reader drops game-arm
  rows and those of families born before T0 and retired since the 2020-21 switch, and keeps dropping them with the game
  off once a T0 exists; a family's own views count no trial or mechanism verdict of a child the game bore beside it; the
  readers' research shares are renormalized over what they read; the strategist's section may not name 2020 or 2021;
  the input card reads "span_mismatch" under a 2022 Train until it is re-audited; a game retirement's public cause is
  one set of words for all three rules; the public site shows no game child. `league/CONTRACT.md` is unchanged.
- **Settings** (`league/swarm/policy.json`): `gym.train_from` "2022-01-03", `gym.allow_earlier_image` true,
  `practice.feedback` false, and the `game` block (`enabled` true, `mode` "gate", `arm_fraction` 0.5, and the rest as
  the spec's section 5; `game.cfg` bounds each). The House's `swarm.json` pins `gym.train_from` "2020-01-02": the
  operator changes it at T0 (docs/operations.md, **The learning game v1**, has the T0 steps and the rollback).
- **The span switch is the one evidence reset:** at the next start every living family's best is chosen again over
  2022-2024 (`migrate_objective`) and its robustness starts over; a recorded validation of the same version on the same
  Gym is reused.
- **Measurement.** The House's new `game` job (daily 00:00Z, read-only) and `scripts/game_report.py` write the
  operator-only report `<state>/game/report-<day>.json` (R1-R6, family-cluster bootstrap, the pre-registered
  decisions; D1 by lineage; the leak scan reads what researchers were shown).
- **After its review (Oct 8):** the ladder's triggers are a state (`game.recheck`); a program the Gym ends on the hidden
  years is a landed look; a failed look bars its program (no unbounded control looks); a hidden run is split in 8 as
  the retro ran it; a shadow PASS is read at the first gate round; the candidate is the newest CONFIRMED version not yet
  judged and the tries count CONFIRMED versions only; a start after T0 under a 2020 span voids the epoch and the next
  seen start writes a new T0; the ops' stall check owes a game family no Validation before a CONFIRM and counts the
  game's children as births; `harness_lanes` seals `game.py` and freezes the architect's and strategist's filters.
- **Owner steps, in order** (docs/operations.md, **The learning game v1**): merge and deploy; redeploy the gateway
  (`protected.mjs` gains `game.py`; it may wait a few days); let the release clear its watch; stop the swarm
  (`swarm.stop`); delete `gym.train_from` from the House's `swarm.json` (do not pin 2022: a rollback must fall back to
  2020 by itself); clear the 2020-24 words from the agendas and the strategist's section; re-audit the input card over
  2022; start the swarm. Before or with any code rollback, restore the before-copy of `swarm.json`: the previous
  release refuses every Train job under a 2022 span on the 2020 image.
- **What does not move:** nothing in `league/gym/`, `league/live/`, `league/constitution.py`, `league/swarm/settings.py`
  or the store: the execution fingerprint and the money digest are unchanged, no evaluator adoption, and Validation, the
  gate, the holdout look and Probe sizing are as they were. Control and legacy families, and every family with the game
  off, play main's round byte for byte (`league/tests/test_game.py` `Golden`, against `ab64c68b`).

### 12:40Z, even pacing: House release `20261008T124025Z-a9686c7cfcfd` (main `ab64c68b`; PR #510)

The guard holds new research while today's Sail research runs ahead of the day's budget pro rata plus `guard.pace_slack`
(0.05 of a day; `guard.pace_day` true). On Oct 8 the day's $13.91 was at its line by about noon UTC and new research
held to midnight; pacing spreads the dollars over 24 hours. A hold, never a brake: validation, the gate and the
nightly forward go on, and the stall job's braked hours (brake events) are unchanged. CI green on the exact head
`f4c0a2ef`; no order in flight; PROMOTED 12:41:07Z; previous `20261008T105752Z-eb1ce3d588a9`. Digests unchanged.
Operator, no deploy: `gym.max_boxes` 2 and `researcher.sail_usd_per_hour` 0.5 again (the 06:30Z values 1 and 0.2 were
a stopgap before pacing).

### 10:58Z, the gate's contract: House release `20261008T105752Z-eb1ce3d588a9` (main `8a058384`; PR #509)

The gate's paid readers were told ChainView has no `iv`, `delta`, `gamma`, `theta` or `vega` (league/gym/review_contract.py
lists `__slots__` only), so a delta-selecting program that ran and validated in the Gym got unclear verdicts as a
"verified contract defect" and was refused after three (`highbeta-skew-reprice-single` v15, Oct 7). `gate.gate_contract()`
adds every public property of `Ctx`, `UnderlyingView` and `ChainView` with one fact and its own hash; the gate's prompts
and keys, its restamped review and audit receipts, and the bands' and incubator's checks use it. Built in league/swarm,
so the execution fingerprint (`b4c34031`) and the digests do not move: no evidence reset, no ratification. Past
refusals stand. CI green on the exact head `531e27d9`; no order in flight; PROMOTED 10:58:34Z.

## 2026-10-07

### 19:12-19:24Z, fast lane v2 and the self-running release: gateway `f63dd354`, House release `20261007T191231Z-2cfea1c1f73c` (main `cd58fc8f`; PRs #506, #507), money digest `42c4a3af` -> `da5c7542`, evidence reset 4

Owner deploy in the US session under the owner's goal of Oct 7 (item 1: deploy any time when CI is green on the exact head and rollback is ready; a live-execution change first confirms no order is in flight).
- **CI:** green on the exact head `bf355f55` (gateway, tests 3.11 and 3.14); local full suites green on both Pythons (7,521 league tests); gateway 412/412.
- **Gateway first:** `f63dd354-253a-46d5-90a6-35ca07a49adf` at 19:12Z (rollback `e95a2d4a-a79a-4a68-97f6-914e6af2cace`); kill switch false after.
- **House:** no order in flight at 19:11:57Z; nightly stopped (operator:oct7) while idle; `floor_box.py deploy` PROMOTED 19:13:47Z (canary and ten-minute watch); previous `20261007T160204Z-31d63e37434e`. The standing grant RATIFIED itself at 19:14:20Z on money digest `da5c7542` (the `grant` job, release-triggered). `real_money` true, health failures []. The new jobs ran: `direction` (23 symbols), `fast_lane`, `stall`. Nightly unstopped; harness observer re-pointed to `cd58fc8f`.
- **PR #506** (`league/CONTRACT.md`): the researchers' contract now says real money opens four types and is on.

#### Fast lane v2

The owner's goal of Oct 7, item 4: a program trades at Probe size as soon as it passes a pre-registered screen whose
false-positive rate is measured. Based on PR #505 (the House's release `20261007T160204Z`). The screen (t 1.65, 2 of 4
quarters, N = 1, one flat holdout look at p <= 0.10 a program), direction counts (`policy.json`: the drift screen's
refusal and the look holds off; the `direction` job and `scripts/fast_lane_report.py` report the drift fit and the
same-risk buy-and-hold), a one-structure Probe within 10% of E, at most 3 Probe positions, a $400 Probe loss budget,
same-minute entry and D5 demotion by live results. **The money digest moves** `42c4a3af` -> `da5c7542` (constitution
`595228a6` -> `5edc8956`): the standing grant re-ratifies at the House's start on the owner's deploy. **An evidence
reset**: league/live changes, so the execution fingerprint moves `ba60c473` -> `b4c34031`; no family is banded. The
benchmark is [docs/benchmarks/FAST_LANE_SCREEN_1.md](docs/benchmarks/FAST_LANE_SCREEN_1.md); the deploy's steps and the
stated consequences are in [docs/operations.md](docs/operations.md) ("Fast lane v2").

Its review's fixes (Oct 7): the Probe loss budget counts realized Probe losses GROSS, from positions a Probe family
opened (marked at the order), so a Sized gain or a Probe gain never refills it, and a lost open counts until it is
found (it had netted every `:r` close, Sized included); tuition sends one structure only within the Probe's cap, and
its reach (real 1-lots before the look, up to $300 a week) is stated; C3 keeps its trigger (a Sized family at a
Probe-sized stake under the Probe's limits); the practice caps and the grant's $100 smallest stake stay as they were; a
program a paid review or audit failed is closed unpaid after the deploy's adoption (`Gate.paid_verdict`); the
`direction` job's failure is a failed receipt, and at a House start the grant runs first (same-instant jobs in the
registry's order); a new `fast_lane` job writes the report daily, read-only, with contamination measured (head against
tail per look, pooled, and live against holdout); the adaptive-search ceiling (20-38% for a persistent no-edge lineage
with 3 looks) and the benchmark's history are stated.

#### The self-running release: the improvers

The House's weekly post-mortem (`v3/b4`) and the engineer with its reviewer (`v3/b5`), ported onto `research/restart-1007`
(budget rule v2). The post-mortem: Saturdays 14:00Z, at most $1 a week of Claude, a private report and a public page
under `docs/runs/desk/`. The engineer: on by `policy.json` `engineer.enabled`, at most $4 a UTC day of Claude, one
candidate in flight, research-class only (the modules the live path loads are held, by the House and by the gateway's
`ENGINEER_HELD`), merges only through the gateway's walls (green CI, a recorded review, two a day, no protected path),
closes its own superseded and unmerged pull requests through `POST /v1/github/close`, authors at most once a UTC day,
main's head as its base after an owner deploy of it.
Both are under `league/ops/`, so both are an owner deploy. Off without a deploy: the box's `swarm.json`
`{"engineer": {"enabled": false}}`; ops.json `{"jobs": {"postmortem": {"enabled": false}}}`. Detail: operations,
**The improvers**.

#### The self-running release: the stall alarm and the funnel

The owner's goal of Oct 7, items 3 and 6. A new House job `stall` (`league/ops/stall.py`, every 30 minutes at :20 and
:50, read-only, a maintenance pause included) names a stall by its cause: no birth in 12 h under the population
ceiling, fewer than 10 Gym runs in 6 h, no Validation verdict in 24 h while a family is owed one, the Sail guard braked
12 of 24 h, a meter under 3 days of research at the ceiling, main and the running release differing in what only the
owner deploys, a pause left on 6 h, a refused grant, or the kill switch on. One `stall` mail lists every cause (the
numbers, how long, what the House is doing, the owner steps first or that nothing needs the owner): at once and every
12 h while one needs the owner, else at most once a day; each cause is also a House warning every 12 h; it never acts.
The daily page gains the Funnel table (last 24 h and since the release: `league/ops/funnel.py`). The job runner counts
a job or trigger a release adds from the deploy (`first_seen`), so `stall` and the engineer's :40 are never reported
`missed` for the days before. The gateway composes the new `stall` kind on `/v1/notify` and dedupes it by its owner
causes for 12 h (`stall:info` 24 h) inside the day's cap: deploy the gateway first (an older gateway answers 400, which
the job records and warns of).
Owner deploy (`league/ops/`); off without one: ops.json `{"jobs": {"stall": {"enabled": false}}}`. Detail: operations,
**The stall alarm and the funnel**.

### 16:02-16:14Z, the research restart: House release `20261007T160204Z-31d63e37434e` (main `ab6c0c6a`; PR #505)

Budget rule version 2 (the owner's $25 a day ceiling, Sail 0.6 / Claude 0.4, one 5-day runway term) and the F1 research fixes on V3-A. Money digest `42c4a3af`, constitution `595228a6` and the execution fingerprint unchanged: no ratification, no evidence reset. CI green on the exact head `763f9e57`; no order in flight; PROMOTED 16:03:30Z; budget job run by hand at 16:14Z (research $25.00 a day: Sail $15, Claude $10).

### Operator changes, no deploy (`swarm.json`, Oct 7-8)

- 15:44Z `live.calibration` false (the House's calibration round trips: about $12 a session for data no code reads).
- 15:53Z `tournament.drift_screen` false; `architect.cell_yield` true; `architect.max_rebirths_per_cell` 12; agenda v17.
- 16:13Z `gym.max_boxes` 5, `tournament.retire_revisions` 100, `claude.role_usd_day.diagnostician` 0, `researcher.sail_usd_per_hour` 1.0, `architect.every_seconds` 1800.
- 18:44Z agenda v18 (the edge census's STOP and TARGET cells); 19:35Z `researcher.claude_top` 3, `claude.role_usd_day.researcher` 4, `strategist` 2 (a Claude researcher A/B).
- 19:27Z four near-miss validated programs revived (`operator-revive`); two looked and failed, one retired, one validated.
- 22:00Z and Oct 8 06:30Z pacing for 24/7 inside the Sail line: `gym.max_boxes` 2 then 1, `researcher.sail_usd_per_hour` 0.5 then 0.2.

## 2026-10-03

### 08:49Z, V3-A part 1: House release `20261003T084912Z-be16b05904ff` (main `266e6861`; PR #489), gateway `e95a2d4a`, evidence reset 3

LTCM v3's first release, the one that lets the desk run unattended
([the run record](docs/runs/2026-10-02-unattended-desk.md) has the why and the owner's six decisions). It is **live**:
the owner's deploy on Saturday Oct 3, outside a session, promoted 08:49:56Z. This entry says what the release contains
and ends with the deploy's record. It carries
WP1-WP5, WP8, WP8b and WP9 with their review fixes, the four integration lenses (ops, money, deploy, contract), the
settings migration, the fixes for the causes of the integrated head's CI failures, the canary fix the rollback
rehearsal called for (the entry below), main and the docs pass. It moves the evaluator's fingerprint and carries
money-path changes, so it shipped by a planned owner deploy outside a session.

Money digest `42c4a3af`, unchanged (the constitution is untouched, `digest()` equals `PINNED_DIGEST`): no digest
ratification. **Evidence reset 3** at the deploy: `league/live/` changes, so the execution fingerprint moved
`47587e22…` → `ba60c473…`; the Gym's image and bundle are unchanged. Every practice cohort ended (nine), and a
(family, version) that had a cohort does not practise again: practice refills only from new versions. The forward
ladder and the credit types are not in it (**Not yet deployed**, above).

- **WP1, the updater and deploys** (`league/updater.py`, `league/watchdog.py`, `scripts/floor_box.py`,
  `league/config.json`, `league/ci.py`, `league/house.py`, `league/swarm/harness_runtime.py`): `auto_update` true
  (`release_train_hours` 4); before a launch the updater stops the nightly daemon once it is idle, with an `updater:`
  marker that only its writer removes (a House start removes an orphaned one); its watchdog's pid in `deploy.pid`, so
  `floor_box.py deploy` refuses beside it and the updater waits for any watchdog in flight; `push_release` clears only
  its own `incoming/<id>/`, and the updater sweeps its own stale trees; the harness observer follows a release the
  updater attested; a scrubbed watchdog environment; `python -m league.watchdog drill-rollback` and `drill-recover`.
- **WP2, the House's jobs** (`league/ops/`, new; `scripts/desk_receipts.py`): the scheduler on the House's NYSE calendar,
  the registry and the runner (one niced, bounded child at a time; retries inside the grace; missed occurrences a
  warning; public alerts scrubbed of box ids and dollar figures), receipts in `<state>/ops.sqlite` and the private
  receipts file every ten minutes, `health.json` `ops`. Jobs: `grant` (start, hourly), `budget` (after the economics,
  00:30Z), `hygiene` (02:00Z), `clock` (11:00Z), `preopen` (open − 60 min), `economics` (close + 10 min, with `p30`),
  `scoreboard` (23:30Z, public, through the gateway), `drills` (first Saturday, 15:00Z and 17:00Z); `postmortem`,
  `agenda` and `engineer` are registered and skipped while their modules are absent. A maintenance pause holds the jobs
  that write records, post or spend.
- **WP3, the budget rule** (`league/ops/budget.py`; `league/swarm/{settings,guard,models,funding}.py`; all protected):
  research dollars a day per meter from the prefunded balances (R 90 days, W 60 days, a $5 floor split 60/40
  Sail/Claude, half of the trailing 30-day realized options P&L, a no-forward-edge stop after 60 sessions from Oct 5),
  applied tighten-only to the spend knobs, fail-closed; `budget.json` private. The Sail guard's daily cap is the
  budget's: the burst trio (`guard.burst_cap_usd`, `burst_until`, `after_burst_usd_day`) and the `burst_end` funding
  cliff are gone. Claude's room is also capped by the budget's Claude dollars today; OpenAI is closed. `funding`
  notices by mail.
- **WP4, the standing grant** (`league/live_trading.py` `LiveGrant.standing`, `league/ops/grant.py`; protected):
  ratifies on a money digest moved by an owner's release change, or on a landed deposit (by its id); never enables,
  never touches a revoked grant, never above the lower of equity and the ceiling.
- **WP5, live fixes** (`league/live/step.py`, `league/live/shadow.py`): exit-only instances drop opens silently
  (`exit_only_opens_dropped`); practice reads clamped to the Gym store's window and narrowed rather than lost over the
  page cap; practice accounts capped as a Probe (`practice_sized`, practice refusals); only read-budget skips are
  practice pressure, and `live.observe_read_calls` defaults to 120 (was 40).
- **WP8 and WP8b, the gateway** (`gateway/`): `POST /v1/github/docs`; the engineer's `pr` role with lanes, `review`,
  `merge` (stopped by the kill switch), `close` and `pr/<n>/files`; `league/ci.py` `ENGINEER_LANES`; the `funding`
  notice kind; the admin log and `autonomy` in `/v1/health`; `/v1/kill` takes either token; `LOW_BALANCE_USD` 60 → 25
  and `CRITICAL_BALANCE_USD` 20 → 12. `OPTION_STRUCTURES_REAL` unchanged: the credit types were reverted on the release
  until WP7.
- **WP9, fixes and settings as code** (`league/swarm/{pool,models,settings,gate,loop}.py`, `league/swarm/policy.json`,
  `scripts/settings_migrate.py`, `scripts/verify_swarm.py`): pool rows settled against Sail's list; the balanced-to-asap
  window fallback (`sail_fallback`, the audit keeping its own model); the one-reader check by model across Sail
  profiles; the heartbeat names the families in a cycle (hygiene spares them); the `policy.json` layer
  (DEFAULTS < `config.json` < `policy.json` < `<state>/swarm.json` < `<state>/budget.json`, tighten-only), holding the
  box's research settings as of 21:00Z Oct 2 unchanged, without the private agenda and the burst keys.

**The integration changes** (the review lenses, the merge reviews and the CI-cause fixes; Oct 2-3):
- **One protected list, and a wider one.** `league/ci.py` `FORBIDDEN` is the union with the gateway's merge list: 86
  files and trees (35 on main), where the two lists differ only by `league/config.json` (tests on both sides hold them
  to that). New on it: `league/house.py`, all of `league/ops/`, `scripts/floor_box.py`, `deploy/`,
  `league/swarm/policy.json`, `league/swarm/{settings,guard,models,funding}.py`, `league/gym/`,
  `league/swarm/{gate,bands,evaluator,store,evidence,tournament}.py`, the structure core, `ltcm/data/`, `scripts/data/`
  and the harness loop's own objective. A change to any entry inside the release trees (`league/`, `ltcm/`,
  `playbooks/`, `scripts/`, `deploy/`) is the owner's deploy; the updater refuses it, and every later head with it.
  Five entries are outside those trees and never reach the box (`gateway/`, `.github/`, `CHANGELOG.md`, `docs/goals/`,
  `docs/benchmarks/`): the list holds the roles and the gateway's merge route there, the updater neither refuses nor
  ships a change to them, and a merge that changes only those is no release and holds nothing. The gateway ships only
  by wrangler, so a House change that needs a gateway change is merged after that gateway change is deployed; the
  workflows are held by the updater's pin.
- **`policy.json` is no longer delivered by the updater.** A merged change to it reaches the box by the owner's deploy,
  or the box's `swarm.json`, which wins over it, is edited instead. Research-class work that touches any protected file
  is an owner deploy.
- **The engineer's lanes.** The gateway holds the engineer to the paths the harness lanes declare: it refuses
  `league/swarm/loop.py` and `league/swarm/mechanisms.py`, so the scheduler lane admits new candidate tests only until
  an owner deploy opens them. A candidate test's name is bounded on both sides; an engineer proposal names the commit
  it was written against; the kill switch stops merges.
- **The budget rule as merged.** `p30` is the live book's own read first, and the close economics can only cut it;
  unknown stays unknown (nothing earned, and a warning); with no close summary yet each budget run warns; a missing
  `budget.json` is the floor and a stale one never loosens; the overlay also holds `population.start` to the ceiling
  and the architect's refill to its cadence; the ceiling never falls under `population.floor` + 4; OpenAI is closed;
  the paid-model line counts each model's spend on its own, on the day its hold was booked; a budget room that cannot
  be read refuses the call.
- **The funding notice** is computed at the rate the meter wants, so a throttled desk still says when a card is
  needed, and it carries the current rate beside it: the rate the rule holds the meter to now (its fixed cost plus the
  day's research budget), not a metered spend. The gateway's mail names both rates, says each runway as days above the
  meter's reserve, and says that nothing stops without a card only when the figures sent show it; otherwise it says how
  long the meter lasts at the rate it is held to now. Sail's low and critical balance mails sit under the rule's own
  floor.
- **The jobs.** A failed run is retried after 15 minutes inside its grace, at most three attempts; a job that reports
  its own failure gets a `failed` receipt; the rollback drill is requested by the `drills` job and launched by the
  updater in the House's own process; a maintenance pause holds the jobs that write, post or spend; the House box's id
  is read from the release's pin first.
- **The pre-open job's check 5** passes when the Sail guard is braked only by the budget's own daily caps with a fresh
  balance above the line. The guard names its brake's causes and the check reads the names; any other cause (a budget
  rule that could not be read among them), or none named, is a FAIL.
- **Tests.** The league's tests read an empty policy layer; the committed `policy.json` is judged in one place, by
  value and by the House's own loop; fixtures that route to Claude state the budget they need; the House is held to
  never importing `league.tests`.
- **From main** (ahead of the release before by docs and by two changes inside the release bundle, both of Oct 2):
  comment-only edits (the Oct 2 pause refresh: no behaviour change, verified by an AST comparison) and a prune of dead
  files from the Kalshi era and the first run (`scripts/jev_lab_eval/`,
  `scripts/{attribute_fills,repair_leg_fills,repair_no_fills,survey_kalshi}.py`, `deploy/ltcm.service` and
  `league/FEEDS.md`: nothing imports or runs them, and they stay readable at tag `archive/pre-options-2026-09-26`).
  The comment edits touch modules the live path loads, so they shipped in the money path's window.
- **The canary fix** (`league/house.py` `_expedition_notices`, commit `0c8e8107`; three tests in
  `league/tests/test_pacer.py`): the calendar ending the old League's expedition is a warning, not an error; a budget
  spent before its last day is still an error. Without it no release could pass its canary from 00:00Z Oct 3 (the
  entry below has the finding).
- **Docs:** [the run record](docs/runs/2026-10-02-unattended-desk.md), [docs/runs/desk/](docs/runs/desk/README.md),
  operations (**Now**, **Running unattended**, the release checklist, **Roll back**), design and README.

**The deploy's record** (Oct 3, UTC; writing it is a docs-only merge by hand, which changes no release, holds nothing
and needs no deploy). The order followed: the rollback rehearsed on production first (the entry below), CI green on
the exact head, the merge, the gateway with its own rollback rehearsed, the House, the checks, criterion 1.
- **The tree.** CI green on the exact head `0c8e8107` (run 37109800144, 08:44:41Z: the `gateway`, `tests (3.11)` and
  `tests (3.14)` jobs). PR #489 merged at 08:45:39Z as the merge commit `266e6861`, whose whole tree equals the tested
  head's; CI on the merge commit passed too (push run 37110781254).
  - On that commit: the tree `floor_box.py` packs (941 files, bundle `be16b05904ff`) and the updater's unpack of the
    commit have one tree digest (`d817cbf1…`); `digest()` equals `PINNED_DIGEST`; the money digest is `42c4a3af`; the
    execution fingerprint is `ba60c473…`; `auto_update` is true.
  - The settings: the box's `swarm.json` at 08:45Z was JSON-equal to the copy `policy.json` was cut from, and the
    dry-run migration changed exactly the four expected keys.
- **The gateway first: `e95a2d4a`,** deployed at 08:46Z from the merge commit with `npx wrangler@4.129.1 deploy`, after
  404 of 404 tests on Node 26 and on Node 24. The version serves 100%.
  - `/v1/health` answers ok with `autonomy` and `admin_log` present; the kill switch stayed false and the caps are
    unchanged.
  - Read from the deployed version: `OPTION_STRUCTURES_REAL` is the four debit types, `LOW_BALANCE_USD` 25,
    `CRITICAL_BALANCE_USD` 12.
  - Its own rollback was rehearsed at 08:47-08:48Z: back to `4471596a` (16 keys in `/v1/health`), then to `e95a2d4a`
    again (18 keys). The rollback target is `4471596a`.
  - The old House ran healthy on the new gateway before its own deploy (`failures` [], 9 instances).
- **The House.** The nightly daemon was stopped while idle (`nightly.stop`, the lock free). `floor_box.py deploy` from
  the deploy checkout at the merge commit: the canary passed, the release was promoted at 08:49:56Z, the ten-minute
  watch was clean, the verdict was PROMOTED and the deploy exited 0. The rollback target (`previous`) is
  `20261002T112610Z-e11710692569`. `nightly.stop` was removed and the daemon came back; the harness observer was
  re-pointed to the merge commit and its tree digest. The full `swarm.json` stays on the box, untouched.
- **The checks** (09:00-09:01Z, read-only).
  - Health: the new release id, `real_money` true, `failures` [], nothing in `stopped_because`, the session closed (a
    Saturday); an `ops` block with one job due and one ok, none failed or missed (the runner installed at 08:50:29Z).
  - The standing grant: its start receipt is ok. It ratified once, on its first look, with the trigger `deposit`:
    deposits that landed before the last pin, seen for the first time by the job's new record of deposits (the one
    extra ratification [operations](docs/operations.md), "The standing grant", says a first run may make). The digest
    is `42c4a3af` and the capital is the account's equity, under the ceiling. The looks after it answer `none`, and
    `blocked` reads null.
  - Evidence reset 3: `research_evaluator.execution` is `ba60c473…`, the head's; 13 `evaluator_adopted` events at
    08:50:34Z, one per alive family; all nine practice cohorts `complete: evaluator changed`.
  - The jobs: a registry of 11; `scripts/desk_receipts.py` reads `latest.json` through the Files API with no exec.
  - The budget: no `budget.json` until the first run at 00:30Z, so the floor is in force ($3 a day of Sail research,
    $2 of Claude). The knobs are applied: the researchers' Sail pace $0.05 an hour, the population's ceiling and start
    12, the architect every 14,400 s, OpenAI's cap 0. The Sail guard's cap comes from the budget, and it is not braked.
  - The updater: built; its first look came at the first tick, with no alert and no deploy row; the train is 4 hours
    and its hold reads "no release within 30 minutes of a start".
  - The operator's pre-open check, told the new release and gateway: 9 of 10 PASS. The one FAIL was named before the
    run: check 6 (bands), "observe rows 0", because the evidence reset cleared every family's selection.
- **Criterion 1 on the new release** (09:01-09:02Z).
  - `floor_box.py stop` (the loop quiesced in 5 s), then `start`: health fresh on the new release, `real_money` true,
    `failures` [], `ops` present, a new `grant` receipt, and the swarm's heartbeat fresh 16 s after the start.
  - The swarm process killed: a new one, recovered in 16 s, with 13 families alive and the same count of runs before
    and after.
  - After a restart outside the session, `options_live.blocked` reads "the account could not be read this minute"
    until the live path's next quiet pass: off-session it reads the account every 15 minutes. It cleared at 09:14Z. The
    release before behaved the same.
  - The tuition instance is still exit-only.
- **By itself from here.** The `grant` job hourly at :05; `scoreboard` at 23:30Z (the first daily page, a docs commit
  to main through the gateway); `budget` at 00:30Z (the first `budget.json`, then the `funding` notices); `hygiene` at
  02:00Z. The first drills are due the same day, at 15:00Z and 17:00Z: two test `funding` mails, a failed Sail read,
  a gateway outage, a killed swarm, and the rollback drill (a broken copy promoted and rolled back by the watch: two
  House restarts). Until Monday's close each budget run raises one warning, "no close economics summary yet".
- **What it does not do yet.** Practice is empty until new versions qualify on the new evaluator or the ladder release
  lands. The forward ladder (its design frozen, its confirmation not yet run) and research v3 are not in this release.

### 08:23-08:41Z, the rollback rehearsal: House release `20261003T082921Z-f313be66cb82` (main `d0a2d01b` plus one fix), promoted 08:30Z and rolled back

Before V3-A part 1 shipped, the way back was rehearsed on production: deploy main as it stood, watch it, roll it back.
Main then was `d0a2d01b`, ahead of the running release by docs, comment-only edits and the dead-file prune. The
rehearsal found that no release could land at all.

- **08:23Z, the blocker.** `floor_box.py deploy` of main `d0a2d01b` alone was refused by the canary (exit 2, production
  untouched): "2 error alert(s) ... The expedition's Sail spending has stopped: day 14 is over".
  - The old League's fourteen-day expedition (the constitution's `budgets.expedition`, from Sept 19) ended at 00:00Z
    Oct 3.
  - A canary is a fresh House with nothing told yet, so it tells the run's scheduled end on its first tick. It told it
    as an error, and the watchdog refuses any unmarked error in a canary.
  - So from 00:00Z Oct 3 every canary was refused and no release of any kind could land: not V3-A, not a re-deploy of
    a rollback target, not an updater release, not the rollback drill.
- **The fix** (commit `0c8e8107`, `league/house.py` `_expedition_notices`): the calendar ending the run is a warning; a
  budget spent before its last day is still an error. Its three tests (`league/tests/test_pacer.py`: the notice's level
  in both cases, and a fresh House after the expedition reading healthy to the watchdog) fail on the old code with the
  refusal's own words. It reached main in PR #489.
- **08:28-08:41Z, the rehearsal, on main plus that one fix** (a local cherry-pick onto `d0a2d01b`, not pushed: the
  running release's money digest `42c4a3af` and execution fingerprint `47587e22…`, so no evidence reset, and
  `auto_update` false; 209 tests of the pacer, the watchdog and the House pass on Python 3.11 and 3.14).
  - The nightly daemon was stopped while idle; the lock was free 20 s later.
  - `floor_box.py deploy`: release `20261003T082921Z-f313be66cb82`, the canary passed, promoted at 08:30:04Z, the
    ten-minute watch clean, PROMOTED and exit 0 at 08:40Z, with `previous` the Oct 2 release.
  - `floor_box.py rollback --reason "rehearsal before V3-A"`, with no force flag: the real-book guard passed (the
    previous release manages the real book) and the rollback exited 0 in 4 s.
- **The restored release, verified at 08:41Z:** `current` was `20261002T112610Z-e11710692569` and `previous` empty;
  health was fresh on it, `real_money` true, `failures` []; the research evaluator was unchanged (no adoption event)
  and the same nine practice cohorts were active; there was no new grant ratification; `swarm.json` and the harness
  observer's runtime file were unchanged; `nightly.stop` was removed; a `deploy` at `e3d0111f` answered "nothing to
  deploy"; the operator's pre-open check was 9 of 9 PASS.
- **A side effect to know:** each swarm restart lifts the families' holds. In the cycles after the rehearsal's two
  restarts three families retired themselves (self-refuted by their researchers, 08:30Z and 08:41Z), which left 13
  alive.

## 2026-10-02

### 23:30Z, autopilot (no deploy)

The owner put the project on autopilot. Production stays on `20261002T112610Z-e11710692569`; the box's updater stays
off. The live path trades every session (calibration round trips, the House live test, the incubator, the practice
league in shadow); the swarm researches at the funded floor set below.

### 17:04-21:00Z, research to a funded floor; three cohorts ended; the v3 baseline; settings as code (operator, no deploy)

- 17:04Z and 17:23Z (`swarm.json`, before-copies kept): `population.start` 96 → 16, `population.floor` 12 → 8,
  `architect.every_seconds` 1800 → 7200, `researcher.sail_usd_per_hour` 1.3 → 0.4 → 0.25, `gym.max_boxes` 6 → 2 → 1,
  `strategist.every_seconds` unset → 86400. The swarm had spent about $29 in the 24 hours to the close (Sail models
  $13.04, Sail boxes $3.78, Claude $6.67, plus data vendors pro rata); the floor is about $5 a day of Sail.
- 19:03Z (`observe.sqlite`): practice cohorts ended with an operator reason: `googl-lags-msft-ai-cloud-qqq-flat-r` v1
  and `googl-lags-msft-ai-cloud-qqq-flat--2` v83 (holdout-failed lineage, barred from the incubator) and
  `qqq-exsemis-residual-smh-flat-on-s-2` v1 (its SPXW chain read failed every live minute). Nine cohorts remain.
- 19:03Z (`swarm.sqlite`): the six Gym pool rows in state `failed` marked `terminated` (Sail had ended those boxes
  and listed none of them).
- 20:06Z: the one-cutoff economics at the 20:00Z close, the v3 baseline: realized options P&L -$40.63, input costs
  $607.88, Net -$648.51; with the open tuition lot at its conservative mark, -$772.67.
- 21:00Z: a copy of `swarm.json` became `league/swarm/policy.json` on `release/v3a` (the settings identical, without
  the private agenda and the burst keys). The box's file is unchanged.

### 14:15Z, the pause (no deploy)

- The owner paused active development and chose to keep the swarm running: production runs on
  `20261002T112610Z-e11710692569` with its `swarm.json` unchanged (the continuous-learning run record's "Oct 2:
  pause" has the settings then; `docs/operations.md`, **Now**, has the settings in effect today). Not applied: the next
  agenda (v17), a change to the architect's cadence and spend, and ending the two GOOGL-lineage practice cohorts by
  hand. Work resumed about 17:00Z on the v3 plan (above).

### 11:26Z, House release `20261002T112610Z-e11710692569` (main `e3d0111f`; PRs #484, #481)

- **The look holds** (L6(b) and L6(c), branch `gate/l6-look-holds`; `league/swarm/gate.py`, `league/swarm/evidence.py`,
  `league/swarm/store.py`, `league/swarm/settings.py`, `league/swarm/bands.py` (the House's reader),
  `league/swarm/incubator.py`, `league/CONTRACT.md`, `scripts/verify_swarm.py`, `scripts/look_holds_benchmark.py`; the
  money path as the duplicate look's: 20:05-13:25Z only, after two adversarial reviews and green CI; the House and the
  swarm deploy together). The owner approved them on Oct 2 (~02:55Z) as a tightening, on the condition of
  fixed-benchmark proof that false promotions do not rise and a report of the missed-signal cost. Every holdout look
  raises the Holm bar for every later one; the three looks since the Sept 26 reset were all long-delta programs and all
  failed, and a 2025 Validation pass has mostly measured long-market drift (the edge study). After the duplicate look,
  the experiment contract, the drift screen and the rations, and before the paid review and audit and the sealed read,
  the gate now HOLDS the look at (b) a long-delta version (pooled Train beta above zero) whose own Train drift fit has
  drift share |drift| / (|alpha| + |drift|) of at least 0.25, or (c) a version whose expected holdout power is below
  0.30: the normal approximation of the holdout line's one-sided bootstrap test at the level the look would have to
  reach under Holm, with the version's Validation all-days daily Sharpe over the holdout window's 184 sessions. Missing
  figures hold (fail-closed). A held version gets one `look_holds` row (never a `refusals` row), `gated_sha` with
  `gate_ready` cleared, `gate_outcome` "held", words with no figure for the researcher, and a private `swarm.gate` event
  `look_hold` whose `_figures` say why; no look row, no try, no review, no audit, no holdout read. On the money path a
  hold is a failed look: "held" joins `bands.BAD_OUTCOMES` (refused, failed, demoted), so the held version's execution
  tuition ends (`bands.read`) even when the hold lands after a passed review while it waits, and its program is barred
  from the incubator for good (recorded first, as a refusal's bar); without this a held program kept 1-lot real tuition
  for good and could reach an incubator lot that the failed look it replaces would have barred (reviews A1 and B1). A
  new version that clears both is looked at. Settings `gate.look_holds` `{"drift_share": 0.25, "min_power": 0.30}`, on
  by default; each key null turns its hold off, `look_holds` null both (today's gate). Tightening only: no threshold of
  the validation or holdout line, no Holm, deflated-Sharpe or forward rule moves, and on the money path a hold ends what
  a failed look ends; nothing in `league/live`, `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest;
  the store gains one table. The fixed benchmark (`evaluator-suite-1`, #452, development cohort, full protocol, pinned):
  the suite on the branch equals base case for case (`--compare`: comparable, no regression, no improvement; the same
  world rows), and with the holds overlaid on its recorded outcomes (`scripts/look_holds_benchmark.py`, the branch's own
  functions) false promotions stay 16 of 160 (the two memorized-table leaks the review alone stops) and 0 of 896 search
  noise lineages, and missed signals stay 23 of 40 and 269 of 384: no planted signal that reached its look would be held
  (the nearest, one dense world at power 0.297, had already failed Validation), and the drift-only negative, which the
  drift screen stops, would be held in all 8 worlds. The suite's worlds hold no long-drift program that reaches a look,
  so it shows the holds cost nothing there, not what they save. To verify after the deploy: `look_holds` rows and
  `swarm.gate` events with action `look_hold`.
- **The research canary holds half the families for 12 h; the cycle-error floor; outliers sit out** (branch
  `lanes/retention-guard-rule`; `league/swarm/harness_lanes.py`, `playbooks/harness-improvement.md`, new
  `league/tests/test_harness_canary_rules.py`). The lanestats study (Oct 1, operator-only simulation on the 24 h
  capture's per-family tallies, reproducing the base `retention()` on 24 of 24 draws) found the arms canary too thin to
  decide: the research canary (25% of families, 6 h) ended `insufficient_activity` in 93% of windows at the night pace,
  its cycle-error guard's 20% relative tolerance (a tenth of a point at about 0.5% of cycles) could not be resolved, and
  one already-broken family (53 of the capture's 70 cycle errors) decided that guard by the arm its hash fell in. Now
  the research canary holds 50% of families for 12 h; `cycle_error_rate` gets an absolute tolerance of 0.005 like its
  sibling rate guards; a unit that held >= 25% of a lower-is-better check's events in the capture (>= 20 events; an
  event count only, never seconds or dollars, `AMOUNTS`) sits out both arms, chosen before the arms exist;
  `binomial_low` (the memory lane's birth balance) no longer overflows from 1,030 births. Checks are still judged on the
  point estimate. Unchanged: every primary metric, `min_effect`, the primary alpha, every guard (none removed),
  population guards, window lanes. Re-simulated (the #481 review's simulator driving `retention()`; research at 50%/12 h
  with the floor and the exclusion, simulated together; 120 / 240 Train runs an hour; 600-3,000 windows a cell, SE 0.1-2
  points; the old canary is the base code at 25%/6 h on fresh seeds): no effect retained 3.4% / 3.7% (old 0.5% / 3.5%);
  a true 1x benefit 19.2% / 23.6% (old 1.5% / 15.0%); a 2x benefit 40.3% / 45.5% (old 2.2% / 32.8%). A 1x benefit that
  harms one guard by twice its tolerance is retained at most 8.4% / 12.3% (`zero_trade_ok_rate`; old 1.0% / 7.5%): above
  the operator's 10% at 240 an hour, below it at the night pace; the other guards at most 5.6%; with a 2x benefit the
  zero-trade harm 18.5% / 19.3%. A 50% worsening of the zero-tolerance secondary with a 1x benefit: 5.1% / 3.7%. Given
  that the primary passes with no effect, a check still fails in 36% / 33% of windows. The memory lane's 12 h rebirth
  canary: 2.0% with no effect, 6.0% at a true 1x benefit. A bootstrap guard rule (a check fails on a significant
  worsening beyond its tolerance, or when the canary cannot rule out twice it) was tried on the same windows and dropped
  because it did not beat the point estimate: it lowered the worst 2x guard harm at 240 an hour only to 10.1% (not below
  10%), retained a true 1x benefit less often (17.0% / 22.6%; the memory canary 3.3%) and failed a check more often (43%
  / 35% of no-effect windows whose primary passed). Also: the validated-family retire guard and its input closure
  (`Researcher.guarded`, `retire_guard`, `record_verdict` and the helpers they read) join the research lane's frozen
  symbols (the H1 review's finding 5), and a test checks that every frozen symbol resolves. The rule and lane hashes
  move: every registered candidate is re-captured on this release. Research-class (not on the live path). To verify
  after the deploy: `measure` + `rank` on the new release register fresh keys; the research brief's canary reads
  fraction 0.5, 43,200 s.
- **Deploy.** CI green on the combined head; the nightly forward daemon stopped idle first; staged 11:26:23Z, promoted 11:26:54Z
  over `20261002T051530Z-1aebcf26b145`, the watch's verdict PROMOTED. No evidence reset (the evaluator's execution fingerprint
  `47587e22…`, bundle and image unchanged); the money digest unchanged; the open tuition lot exit-only and the 9 practice cohorts
  intact; lineage snapshot diff 0 violations. A deliberate restart at 11:37Z restored every instance, and a killed swarm process
  recovered in 31 seconds.

### Operator changes on Oct 2 (no deploy)

- **03:00-05:26Z:** the owner chose "claims first": `architect.claimable_rows` 4 (05:26Z); `architect.cell_yield` stays null.
- **05:03Z:** `tournament.fork_top` 3 → 0 (no automatic forks of already-validated lineages; the edge study's L7).
- **00:06Z / 06:09Z / 06:51Z / 11:38Z / 11:54Z:** the architect's Claude line 5 → 0 → 5 → 0 → 5 → 0 (Claude's rebirth
  claims failed the card check; then Sail's architect calls timed out from about 07:00Z, 13 passes, no births; the
  Claude architect bore no family in any of its 4 Oct 2 passes, so the line is 0 again from 11:54Z). **11:38Z:**
  `architect.sail_effort` high → medium so the Sail fallback fits its poll window (the cause was not the effort: Sail's
  balanced queue had stopped answering; below).
- **12:28Z / 12:49Z:** `architect.sail_profile` `k3_balanced` (the default) → `pro_balanced` → `pro_asap`. Every
  architect request on Sail's balanced queue since about 07:00Z had sat unanswered until the 15-minute poll gave up
  (`provider_poll_timeout`), while the researchers on the asap queue ran on. The 12:53Z pass on `pro_asap` answered in
  42 s and bore a family; rollback: unset the key, once the balanced queue answers again.
- **12:54Z:** `architect.sail_effort` medium → high. The 13:14Z pass bore 4 of 6; the population was 21 at 13:40Z.
- **07:38-07:51Z, an operator error:** a large read-only extract on the House exhausted its memory and stalled the swarm; the
  House's supervisor restarted the swarm itself. Extracts are now batched and capped.

### 05:16Z, House release `20261002T051530Z-1aebcf26b145` (main `81ad284c`; PRs #480, #483)

- **The duplicate look** (H3a, branch `gate/h3a-no-duplicate-look`; `league/swarm/gate.py`, `league/swarm/store.py`,
  `league/CONTRACT.md`; the money path: `gate.py` and `store.py` are loaded by the live path, so it deploys 20:05-13:25Z
  only, after two adversarial reviews and green CI). Every holdout look raises the Holm bar for every later one, and the
  three looks since the Sept 26 reset covered two programs (the edge study: the two Sept 27 looks had identical Train
  and Validation results). The gate now refuses a look that would repeat an earlier one, in any family and lineage,
  before anything else is asked of the version (the experiment contract, the drift screen, the rations, the paid review
  and audit, the look): the same program (`run_sha`), or a version whose stored Validation run says the same as a looked
  version's (the Gym's own run sha, the code with its parameters merged over the defaults; or the same evaluation with
  the same outcome). Recorded as every gate refusal is (stage "duplicate look": the refusal row, the program's incubator
  bar, `gated_sha` with `gate_ready` cleared, outcome "refused"), plus a private `swarm.gate` event `duplicate_look`
  naming the earlier look; no look row, no try, no review, no holdout read; the researcher hears the earlier look's
  number, never a figure. A repeat of a look in flight in another family waits for it; a version whose own look landed
  is only closed. Before this, a gate-ready version whose `run_sha` had been looked at was skipped silently every round
  and kept `gate_ready`, and a repeat under another `run_sha` was reviewed and looked at. Tightening only: no threshold,
  Holm, deflated-Sharpe or forward rule moves; nothing in `league/live`, `league/gym` or `LEAGUE_FILES`, no evaluator
  adoption, no money digest. To verify after the deploy: `swarm.gate` events with action `duplicate_look` (expect none
  for a genuinely new version) and `refusals` rows with stage "duplicate look".
- **The cell's yield** (H2 of the Oct 1 edge study, branch `cards/h2-yield-aware`; `league/swarm/cards.py`,
  `league/swarm/architect.py`, `league/swarm/settings.py`; off by default, so the deploy changes nothing until the
  operator sets it). From 22:00Z Oct 1 the architect bore nothing for seven passes and the population fell to 13
  (floor 12). Every refusal was the card check's rebirth rule: the productive cells are full of self-refuted and drift
  rows, which `RebirthIndex` counts as mechanism verdicts, and the model's claims named rows outside the six the refusal
  listed. Two settings, in `swarm.json` with no deploy:
  - `architect.cell_yield` (null) opens a cell unless it is exhausted. Exhausted means at least `min_births` settled
    births in `lookback_days` whose Wilson 95% upper bound on drift-pass share is below `floor` (recommended, and `true`:
    30, 0.10, 7). In an open cell a card matching only self-refuted and drift rows needs no rebirth claim. Every other
    mechanism verdict still needs one, and so does every row of an exhausted cell.
  - `architect.claimable_rows` (0) lists, for each cell where a claim can be needed, the newest rows a claim may name,
    with the inputs each read.

  Unchanged: `MECHANISM_VERDICTS` and the rows indexed (the memory lane's judge), the matching, a claim's tests, both
  rebirth budgets, `card_rebirth` "refuse", the same-slice and same-idea refusals, and card completeness (lineage too
  while `cell_yield` is off). A claim made in an open cell that needed none is kept only when it holds; otherwise it is
  stripped before the card is stored (`claim_dropped` on the birth). A yield that cannot be read leaves every cell as
  before. No Validation or holdout figure reaches the request. The pass's event carries `cell_yield` (Train figures
  only). On the edge study's Oct 1 12:59Z extract, none of the 127 classified cells would be exhausted. Nothing in
  `league/live`, `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest. The money path: an import trace
  of the tree (`league/live/*.py`, then the modules `league/live` imports lazily:
  `league/swarm/{store,bands,gate,evaluator,settings}.py`, and the docs' lazy `league/gym` modules and the constitution)
  loads `cards.py` (through `gate`, `researcher`) and `settings.py`, never `architect.py`, and no module it did not load
  before (`cards.py` now imports `evidence.py`, already loaded), so it deploys 20:05-13:25Z only, after two adversarial
  reviews and green CI. The live path never builds a `RebirthIndex`. To switch on and verify: `docs/operations.md`,
  **The cell's yield**.

  With `cell_yield` on, an open-cell restatement on another slice is born as a fresh lineage (its own deflated-Sharpe
  N): switching it on is the owner's decision; `claimable_rows` alone changes no lineage. Fixes from the reviews: the
  yield reading is read before its error flag (E1); a non-finite `claimable_rows` is off, not an error (E2).
- **Deploy.** CI green on the combined head; the daemon stopped idle; staged 05:15:30Z, promoted 05:16:03Z. No evidence reset; the
  money digest unchanged; lineage diff 0 violations. A deliberate restart at 05:27Z restored every instance, and a killed swarm
  process recovered in 31 seconds.

## 2026-10-01

### 20:35Z, the H1 release: House release `20261001T203426Z-6fa69bfcda55` (main `665a9e8d`; PRs #475, #476, #477)

- **Contents.** No retire while the best Train version awaits validation (H1, #475); the research lane's held-out pool
  pin after the operator's rotation r8 (#476, `league/swarm/harness_lanes.py`: the research lane's hash moves, so every
  research candidate captured before it is re-captured); the architect's lenient read 2 (#477). The two items as
  merged:
  - **No retire while the best Train version awaits validation** (H1, PR #475, branch
    `b/h1-no-retire-awaiting-validation`;
    `league/swarm/researcher.py`, `league/swarm/diagnostician.py`, `league/swarm/harness_lanes.py`; the money path:
    `researcher.py` is loaded by the live path through `gate`, so it deploys 20:05-13:25Z only, after two adversarial
    reviews and green CI). On Oct 1 seven of the ten families that made a drift-passing Train version retired themselves
    before the tournament validated it, four of them holding a positive best whose 1.5x run had landed with a profit:
    `Researcher.can_retire` never asked `awaiting_validation`, which the dormancy clause and the status already honoured.
    Now a Gym family whose best Train version awaits validation (not validated, not lost at 1.5x, not failed by the drift
    screen) is not offered `retire`, a call is refused with the reason (on Sail and on Claude; the cycle's record carries
    `retire_awaiting`), the status says so in place of any offer, and the diagnostician's retire defers as it does behind
    the gate; the tournament's verdict, pass or fail, ends it, and so does a demotion. Nothing else moves: no threshold,
    `retire_min_trials`, floor, eligibility or score; the tournament's own rules and `SwarmStore.retire_gym` are
    unchanged (a store-level refusal would let a 1.5x run that never lands make a family no rule could retire). Not
    done, a follow-up: queueing the validation when a new best lands. Nothing in `league/live`, `league/gym` or
    `LEAGUE_FILES`, no evaluator adoption, no money digest. To verify after the deploy: `swarm.cycle` events carrying
    `retire_refused` with `retire_awaiting` (the version the tournament owes a verdict), and no `swarm.retired` event
    whose cause begins "Self-refuted" for a family whose `best_version` differs from its `validated_version` and sits in
    neither `robust_failed` nor `drift_failed`.
  - **Architect lenient read 2** (branch `b/architect-lenient-json-2`): a complete architect answer whose `families`
    array does not parse whole is read object by object (`recover_families`): each family decoded from its own `{`,
    the stray closers and commas between the families skipped, an object that does not decode passed over to its own
    closing brace (never entered), a card a stray `}` inside it closed early passed over too (never born truncated),
    the walk never leaving the array (anything else between two cards ends it), nothing inside a family changed beyond
    #472's trailing-comma strip; the pass's `swarm.architect` event says `recovered` (how many, why, and `passed`),
    beside #472's `lenient`. At 15:59:36Z Oct 1 a Kimi-K3 pass answered six families in 16,008 characters with a stray
    `}` after the fourth and after the fifth; the strict read failed (`Expecting ',' delimiter` at char 10,897), #472's
    trailing-comma read did not apply, the router's reader fell back to the first family card, and the pass read as 0
    proposals (population 42 against a start of 96; about $0.15 and 20 minutes of births lost). On the saved answer the
    new read recovers 6 of 6, each byte for byte (no strip ran). The parse that feeds `admit` (`read_families`,
    `recover_families`, `_from_families`, `without_trailing_commas`, `_past_object`, `_CARD`, `CARD_KEY`) joins
    `salvage_families` in the memory lane's `FROZEN_SYMBOLS` (`league/swarm/harness_lanes.py`). Research-class:
    `league/swarm/architect.py` is not loaded by the live path (verified Oct 1); nothing in `league/live`, `league/gym`
    or `LEAGUE_FILES`, no evaluator adoption, no money digest. To verify after the deploy: a `swarm.architect` event
    whose answer failed the strict read says `recovered` with `proposed` > 0.
- **Deploy.** From a clean detached checkout of `665a9e8d`, with the nightly forward daemon stopped idle (lock free
  20:34:16Z) and a lineage snapshot taken first: staged 20:34:29Z, promoted 20:35:07Z over `20261001T133355Z-67c841b645ca`.
- **No evidence reset, verified** (read-only, 20:37Z): `research_evaluator.execution` still `47587e22…`, bundle
  `gym-engine-4-e1c896f8d304`, image `sbcp_13c5a61d`; the 9 practice cohorts active; the money digest unchanged
  (`42c4a3af`), so no ratify. `real_money` true, `failures` []; the swarm restarted on the new release; the House test
  instance live and `googl-lags-msft-ai-cloud-qqq-flat@27:t` exit-only with position 14 open; no working order;
  `live.incubator` on.

### 20:33Z, operator change (no deploy): the architect back on Claude

- `claude.usd_cap` 198 → 263 and `claude.role_usd_day.architect` 0 → 5 in `swarm.json` (`set_swarm.py`, dry run then
  `--apply`), within the owner's $100 Claude balance; reviews, audits, the strategist and the diagnostician keep their
  lines.

### 20:32Z, gateway `4471596a` (main `07ab60d3`; PR #473)

- **`CLAUDE_USD` 200 → 265:** the owner topped the Anthropic account up to a $100 balance against $165.26 metered
  spent (Oct 1 about 14:35Z), so the funded total is raised by exactly that, rounded down. `npx wrangler deploy` from a
  clean detached checkout; the deployed version's `CLAUDE_USD` reads 265 and every money cap still matches the
  constitution (pre-open check 3). Rollback: `dafcfa05`.

### 16:25Z, the site (personal-site #20; version `3f6147f5`)

- The owner's ideas as small additions to the prior design (trade reasons, the swarm's profit line, the live thought
  queue, performance over time, per-trade results, the game's levels), after a code review and an honesty review.
  `npm run check && npm test` (112 pass, 0 fail, 9 skipped), then `npm run deploy`. Rollback: `6e49f120`, the prior
  page; the Worker and the data layer are unchanged, so it is safe.

### 15:22Z, operator change (no deploy): agenda v16c, two structures, the cell rebirth budget, two retirements

- **15:22:15Z, `swarm.json`** (a before-copy kept), the edge study's levers as settings after its adversarial critique:
  `architect.agenda_locked` and the fallback `architect.agenda` are agenda v16c (steering only; D2 and every kill test
  unchanged; the text stays private, sha256 `c7a46dca0707…`). The fallback it replaces (v15) carried Validation figures,
  and that route is closed. In the same write: `architect.structures` `"real"` → `["debit_vertical", "long_single"]`,
  and `architect.max_rebirths_per_cell` 3 → 6 (`max_rebirths_per_row` 2 and `card_rebirth` unchanged).
- **15:22:40Z,** the strategist's agenda section (kv `architect_agenda_section`) cleared after a backup, so the
  architect reads v16c verbatim until the strategist's next accepted section.
- **15:22:59Z, two operator retirements** (`SwarmStore.retire_gym`, source "operator"):
  `googl-lags-msft-ai-cloud-qqq-flat-r` and `googl-lags-msft-ai-cloud-qqq-flat--2`, the GOOGL lineage's two practice
  families, retired after the lineage's program failed its holdout look (09:39Z, under the 09:16Z release). The failed
  look already bars the program from the incubator. Retiring a family does not end its practice cohort: both cohorts
  kept practising (`docs/operations.md`, **Ending a cohort by hand**). The open tuition lot stays exit-only to its
  programmed exit.
- **What followed, as expected:** clearing the section woke the held families, and at 15:27Z the idle rule retired 26
  architect-born families with no Train best (population 69 → 40; start 96, floor 12). One more, a 14:43Z revival whose
  best Train version awaited validation, retired itself at 15:22:52Z: the defect the H1 release fixed at 20:35Z.
- **A pre-registered 24-hour read** runs from 15:22:15Z, scored at about 15:22Z Oct 2, with its stop rule fixed in
  advance (the run record, "The edge study").

### 14:43Z, operator change (no deploy): seven revivals for practice

- Seven of release A's drift-passing programs on real structures, revived for Train-tier practice and the incubator
  route, not D2. Each is a lineage continuation that inherits its lineage's trials and holdout looks, with its reason
  recorded; their validation verdicts stand. Since #465 (09:16Z) the harness runs each revived program exactly before
  its researcher acts.

  | Revived as | From | Inherited trials |
  |---|---|---|
  | `rate-lag-flat-index-meta-mara-r-2` | `rate-lag-flat-index-meta-mara` v33 | 227 |
  | `hardborrow-forward-squeeze-single-r` | `hardborrow-forward-squeeze-single` v7 | 77 |
  | `slv-iv-discount-momentum-single-r` | `slv-iv-discount-momentum-single` v19 | 48 |
  | `qqq-exsemis-residual-smh-flat-on-s-2` | `qqq-exsemis-residual-smh-flat-on-spx` v116 | 450 |
  | `levered-close-convergence-single-r` | `levered-close-convergence-single` v5 | 370 |
  | `market-distraction-release-call-r--3` | `market-distraction-release-call-r-2` v2 | 133 |
  | `slv-smh-staggered-coupling-single-r` | `slv-smh-staggered-coupling-single` v4 | 66 |

- **Outcome, 14:56Z:** six re-passed Train and the drift screen with their release A numbers exactly (the revival fix at
  work); `hardborrow-forward-squeeze-single-r` failed the drift screen. Those that passed joined practice at the next
  sync, for 9 practice rows.

### About 13:58Z, the site (personal-site #19; version `6e49f120`)

- The prior design restored at the owner's request: the morning's swarm-window page is reverted, and its data layer
  (the schema and the Worker) is kept, because rolling the Worker back after a window checkpoint is stored is unsafe.
  Verified: 0 differing pixels against the prior page (`420a7de`) with the day's data, and `/capital/` answers 200.

### 13:34Z, the lanes release: House release `20261001T133355Z-67c841b645ca` (main `a7542c1c`; PR #466: #449, #452, the memory judge v4, #472)

- **Contents.** Research-class: no module the live path loads changes, so it deployed in session, after the open had
  settled (never 19:30-20:00Z). Nothing under `league/gym`, `league/live`, `LEAGUE_FILES`, the constitution or the
  gateway.
  - **The harness improvement lanes** (#449): research, prompt/memory, data and execution lanes, each with a
    predeclared metric, judges run on the pinned base, private held-out pools pinned by hash only, and an adversarial
    review recorded before a candidate reaches the House
    ([playbooks/harness-improvement.md](playbooks/harness-improvement.md)).
  - **The evaluator benchmarks** (#452): the pinned suite `evaluator-suite-1`
    (`python -m league.swarm.benchmarks --suite evaluator`) scores an evaluator's false promotions and missed signals on
    known-answer cases; no threshold changes. Its results are in
    [docs/benchmarks/EVALUATOR_1.md](docs/benchmarks/EVALUATOR_1.md), including writable numpy state reachable from Gym
    programs, a channel between runs. The fix is in `league/gym`, so it waits for a planned release; until then it is a
    known limit of the evaluator's isolation.
  - **The memory judge v4** (`memory-rebirth-v4`, on the release branch). Since B', a proposal without a complete
    card is not born, so v3's synthetic proposals were all refused and the judge measured nothing. v4 cards its
    fixtures as production admits them and adds same-cell controls; it closed after four review rounds. The memory
    lane's held-out pool pin moves after the operator's private rotation r7.
  - **The architect's lenient read** (#472): a complete answer with stray trailing commas (`,}`), as Kimi-K3 wrote at
    medium effort at 11:57Z, is read again without them (outside strings); the `swarm.architect` event says `lenient`.
    On the real failed answer it recovers all 6 families.
- **Deploy.** With the nightly forward daemon stopped idle across it: staged 13:33:57Z, promoted 13:34:48Z over
  `20261001T114505Z-2d791c2ca9e7`.
- **No evidence reset, verified** (read-only, after promotion): 0 evaluator adoptions; lineage snapshots before and
  after compared 1,774 lineages and found 0 violations; the 3 practice cohorts intact; health `failures` []; the lanes
  command (`scripts/harness_improve.py lanes`) runs on the box. The money digest is unchanged (`42c4a3af`), so no
  ratify.
- **After it (operator settings, no deploy):** 13:45Z `architect.sail_effort` "medium" and `architect.max_refill` 12,
  with #472 live. The 13:59Z pass at medium proposed 12 and bore none (the card checks refused weaker cards: incomplete
  falsifications and refuted-cell rebirths), so at about 14:00Z both went back, to "high" and 6. Harness cycle 2 then
  measured the lanes on the box and ranked them on this base, registering two candidates: the research lane against
  the Train disqualification rate, and the memory lane against validation attempts per research dollar. Each touches a
  module the live path loads, so each deploys after a close and runs a canary window in which no other House release
  ships.

### 11:45Z, the architect on Sail: House release `20261001T114505Z-2d791c2ca9e7` (main `9b6d8857`; PR #470)

- **Why.** From 08:15Z every architect pass on Sail (Kimi-K3 at a hard-coded "high" effort, 32,000 output tokens) came
  back incomplete. Family cards (B') had doubled the visible answer, and the reasoning spent the whole output budget,
  so the answer was empty or cut. `ModelRouter.ask` ignored Sail's `incomplete`, so each pass read as 0 proposals,
  salvage never ran, and each empty pass erased the last card refusals. The empty passes cost $4.43 on Oct 1.
- **Contents** (#470; `league/swarm/architect.py`, `league/swarm/models.py`). `architect.sail_effort` (default
  "medium"; a value it does not know reads as the default). The Sail route also returns `truncated`,
  `incomplete_reason` and `usage`, so a cut Sail answer is salvaged like a Claude one, and the one retry stays on
  Claude only. A pass that proposed nothing no longer overwrites the card and structure refusals, and a retry no longer
  counts refusals twice. Research-class: the live path loads neither module (verified on the box); the execution
  fingerprint (`47587e22`) and the money digest (`42c4a3af`) are unchanged, so no ratify.
- **Operator stopgaps before it (no deploy):** 11:03Z `architect.every_seconds` 900 → 3600, to stop paying for empty
  passes; 11:15Z `architect.max_refill` 12 → 6, to halve the answer. A mistaken `architect.max_output_tokens` 24000 at
  10:59:44Z was restored to 32000 within a minute.
- **Deploy.** Staged 11:45:07Z, promoted 11:45:42Z over `20261001T101853Z-466bca70278a`.
- **Verified** (read-only): lineage snapshots before and after (11:44:50Z, 11:51:11Z) compared 1,772 lineages and found
  0 violations. At the 13:33Z open check, under this release, health listed no failure, the incubator's pins were dated
  Oct 1 (no eligible family), and 3 practice cohorts were active. A health read and an adoption count taken right after
  the promote are not recorded.
- **After it:** the 11:57Z pass at medium completed in 48 s but read as 0, because stray trailing commas broke the
  strict read (fixed by #472 in the 13:34Z release). At about 12:00Z `architect.sail_effort` was set to "high"; with
  `max_refill` 6, a pass completes.

### 10:19Z, the site feed: House release `20261001T101853Z-466bca70278a` (main `554b0aa8`; PR #469, which carries #463)

- **The site first** (the verified safe order is site, then House): personal-site #18 (merge `b8ad841`), Worker version
  `23d732c6`, at about 10:00Z, after `npm test` (108 pass, 9 skipped). Until the House sent the window, the site served
  the checkpoint as before. **Rollback caution:** once a window checkpoint is stored, rolling the site back past #18
  (to `420a7de`) is unsafe, because the older Worker spreads `levels` and `rationale` (PR #18's rollback note).
- **Contents.** #469 is #463 plus the House's copy of the site schema, refreshed to `b8ad841`. Money path by the goal's
  definition (the live path loads `league/swarm/public.py`), so it deployed outside 13:25-20:05Z. #463 as merged:
  - **The swarm window** (branch `b/site-rationale`): the publisher sends `levels` (each agent's level and the levels
    funnel since the reset) and `rationale` (each agent's thesis, and each real position's route, reasons, exit and
    maximum loss), pins every agent a real position names to the roster, and filters every mechanism against its
    program's parameter names. After its three reviews: a thesis, a tag, a note and a mechanism carry no number in any
    form (number words including ordinals, fractions and run-together numbers; "one" only as a pronoun; numerals of any
    script; no hidden format mark or look-alike letter; parameter names with hyphens or run together); the roster's
    mechanism and the birth news drop every sentence with a number (no entry window or threshold on the page); Tuition
    counts only families that held a tuition lot (its own branch of the funnel); a position's route is the band it was
    opened on; under the byte limit the window leaves before any agent or row, with 32 KiB left for the site's names (a
    40-character name on each of 508 rows); the window is not read while the site refuses it. After the post-fix
    verification (Oct 1, 09:30Z): an apostrophe never hides a number word ("fifty's", "'twenty-day'", typographic
    quotes), accents fold away before reading ("twénty"), a word split by a mark joins ("twen·ty"), cardinal plurals,
    multiples ("quintuple"), "couple", "unity", "a score of", "-ish"/"-odd"/"-something" and "pct"/"bps" run together
    are numbers (`number_words.json` is the case list the site tests too); and a trade's `why` on the public tape
    (`agent.trade`, live today) is filtered by the same rules and the traded program's parameter names, or empty.
    Publisher and swarm-feed files only (`league/publish.py`, `league/site_window.py`, `league/trading_profit.py`,
    `league/swarm/public.py`, `league/swarm/sitefeed.py`, `league/swarm/hook.py`): nothing in `league/live`,
    `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest. Site first (personal-site
    `capital/swarm-window`); an older site gets the checkpoint without the window. Two nits from the verification
    shipped as known limits: one accent case (a mark stuck to a number word) can still pass, and a fill on the netting
    book publishes an empty `why`.
- **Deploy.** With the nightly forward daemon stopped idle across it: staged 10:18:54Z, promoted 10:19:28Z over
  `20261001T091620Z-08ad59436dc2`.
- **No evidence reset, verified** (read-only): no evaluator adoption (fingerprint `47587e22`); lineage snapshots before
  and after compared 1,770 lineages and found 0 violations. The money digest is unchanged (`42c4a3af`), so no ratify.
- **The window, end to end:** at 10:29:02Z the public checkpoint (`curl -s
  'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1&practice=1&window=1'`) carried `levels` and
  `rationale`, so the site took the window; read again at 20:48Z, it still does.

### 09:16Z, the money-path release: House release `20261001T091620Z-08ad59436dc2` (main `4bc49530`; PR #468: #465, #467)

- **Contents.** Money path by the goal's definition (the live path's imports reach `researcher.py`, `gate.py`, `pool.py`
  and `settings.py`), so it deployed outside 13:25-20:05Z. Nothing under `league/gym`, `league/live`, `LEAGUE_FILES`,
  the constitution or the gateway. #463, first planned for this release, shipped on its own at 10:19Z.
  - **An operator revival runs its program exactly** (#465, `league/swarm/researcher.py`). Until now a revival never ran
    the revived program: a bare `gym_run` dropped the version's stored params, and cheap researchers rewrote the code at
    once. Now, at the start of a cycle and before any rewrite or model turn, the harness runs a living Gym family's
    latest operator-written version with its stored code and params, once per evaluator and Train span, through
    `gym_run`'s own path (the same refusals, trial count, drift screen and robustness runs). A bare `gym_run` reruns the
    latest version exactly. Audit a claim that a revival "re-validated with identical numbers" by its eval key (code sha
    and merged params), not its version number.
  - **Gate hardening** (#467; `scripts/data/nightly.py`, `league/swarm/settings.py`, `loop.py`, `pool.py`, `gate.py`).
    The nightly forward chain records the gate image each day extends (`base_checkpoint`, `holdout_roots`), and the
    swarm uses the ready file only when it extends `gym.gate_checkpoint` and covers `gym.roots`; otherwise it keeps
    `swarm.json`'s gate and alerts `gate_chain_ignored`. The nightly refuses a chain it cannot prove before it wakes a
    box. A gate box lists its holdout coverage when it starts, and the gate refuses a look up front for a missing root.
    A look that fails for missing data costs no try, writes no "gym" refusal and bars nothing, and
    `look_failed_three_times` fires at every count from three.
- **Deploy.** The nightly forward daemon stopped idle; staged 09:16:23Z, promoted 09:16:58Z over B'
  (`20261001T071033Z-95efdb353597`). Then #467's migration: `nightly.py stamp-ready`, a dry run and then `--apply`,
  stamped the ready file with its base gate and its 25 holdout roots. The effective gate checkpoint did not change, no
  ready file was ignored, and the daemon was un-stopped.
- **No evidence reset, verified** (read-only): no evaluator adoption, the evaluator unchanged; lineage snapshots before
  and after compared 1,770 lineages and found 0 violations; `real_money` true, `failures` []. The money digest is
  unchanged (`42c4a3af`), so no ratify.
- **The revival fix, in production.** Within 3 minutes the harness ran the living revivals' version 1 exactly
  (`googl-lags-msft-ai-cloud-qqq-flat-r`, v27's program, and `silver-industrial-cycle-debit-r-r`, v20's), and Train and
  the robustness runs landed. The GOOGL program then validated again under the current evaluator, passed review and
  audit, and took its sealed 2026 holdout look at 09:39:56Z, the first look since Sept 27 and the first on the 25-root
  gate. **It failed.** The gate barred the program from the incubator, and its open tuition lot stays exit-only to its
  programmed exit.

### 07:11Z, Release B': House release `20261001T071033Z-95efdb353597` (main `03c274c9`; PR #460: #446, #458, #459, #461)

- **Contents.** Swarm-side only: nothing under `league/gym`, `league/live`, `LEAGUE_FILES`, the constitution or the
  gateway, so no evidence reset. `researcher.py` and `bands.py` are in the live path's imports, so it deployed outside a
  session.
  - **Family cards** (#446; `league/swarm/cards.py`, `league/swarm/mechanism.py`). Every architect proposal carries a
    schema-checked card (hypothesis, mechanism class, inputs, holding, cost, comparison, ablation, falsification); one
    without a complete card is not born (`architect.require_card`). Cards are immutable in `family_cards`, and
    researchers see them in every brief. A rebirth in a cell a mechanism verdict refuted is refused unless it names the
    dead row, adds an input that row did not read and cites checkable evidence, within budgets
    (`architect.max_rebirths_per_row` 2, `architect.max_rebirths_per_cell` 3 in 7 days; `architect.card_rebirth` "off"
    turns it off). A blind mechanism test runs in shadow mode on a quarter of carded families and stops nothing.
  - **The final release-B nits** (#458): the incubator's reader and the swarm agree on another family's owed audit
    (fail-closed: no paid review for a program the reader would refuse), and the L1 keep holds every cohort the
    incubator could pin, beyond its cap.
  - **The architect's structure allowlist** (#459, `architect.structures`). Since release B, 47 of 78 births were
    structures real money cannot trade at this equity. With `"real"`, the gaps, birth quotas, admission, forks and seeds
    read only `allocation.real_structures` (debit verticals, long butterflies, long calls and puts, long singles), and a
    refused proposal is named in the next request. Absent or null, every type stays allowed.
  - **The retire guard** (#461; `researcher.retire_guard_days`, 14). Release B's adoption cleared every selection at
    03:51Z, and within seconds the four families holding validated versions retired themselves, citing the evaluator
    change. A researcher's `retire` is now refused while the family holds a version whose latest validation passed
    within the window. The guard also reads the adoption events, so a second adoption cannot lift it; only a failed
    validation of that version ends it.
- **Deploy.** The nightly forward daemon stopped idle; staged 07:10:34Z, promoted 07:11:09Z over Release B
  (`20261001T034829Z-d823e014ce16`); the daemon was un-stopped at 07:21:45Z. CI was green on 3.11 and 3.14.
- **No evidence reset, verified** (read-only, after promotion): `research_evaluator` unchanged (bundle
  `gym-engine-4-e1c896f8d304`, execution `47587e22…`, image `sbcp_13c5a61d`); 0 adoption events since 07:10Z; lineage
  snapshots before and after compared 1,762 lineages and found 0 violations (11 grew by new trials); `real_money` true,
  `failures` []. The money digest is unchanged (`42c4a3af`), so no ratify.
- **Switched on, 07:20Z** (`swarm.json`, no deploy): `architect.structures` `"real"`. The first pass after B' bore a
  silver-coupled vertical and a TSM long butterfly.
- **Deferred:** #462 (keep the research selection when an adoption moves only the live fingerprint), a policy change,
  because the owner's rule treats a live change as an evidence reset.
- **Found after it:** two of the 07:02Z revivals retired themselves within 15 minutes after running new versions, never
  the revived one. No more revivals until the 09:16Z release's fix (#465).

### 05:55-07:30Z, operator changes (no deploy): revivals, a manual checkpoint, the holdout gate chain re-based

- **About 05:55Z, the GOOGL family revived.** `googl-lags-msft-ai-cloud-qqq-flat` v27, whose tuition lot is open, had
  retired itself over Sept 30's evaluator change. It is revived unchanged as `googl-lags-msft-ai-cloud-qqq-flat-r`, a
  lineage continuation (123 inherited trials, no consumed look).
- **06:58Z, a manual House checkpoint** (`house-manual-20261001`, kept to Oct 31): Sail's automatic House backups had
  failed since Sept 30 05:54Z with a platform 503. They read OK again by 14:54Z.
- **07:02Z, three revivals for Train-tier practice, not D2.** Each program passed Train at 1.5x and the drift screen
  under release A; their validation verdicts stand.

  | Revived as | From | Inherited trials |
  |---|---|---|
  | `silver-industrial-cycle-debit-r-r` | `silver-industrial-cycle-debit-r` v20 | 1,117 |
  | `rate-lag-flat-index-meta-mara-r` | `rate-lag-flat-index-meta-mara` v33 | 217 |
  | `market-distraction-release-call-r--2` | `market-distraction-release-call-r-2` v2 | 120 |

  Two of them (`rate-lag-…-r`, `market-distraction-…-r--2`) retired themselves within 15 minutes without running the
  revived program: the revival defect that #465 fixed at 09:16Z.
- **07:05-07:30Z, the holdout gate chain re-based** (no data fetched, no evidence identity moved, no look consumed).
  The nightly forward chain had extended the original five-root gate image, and its ready file overrode the 25-root
  gate named in `swarm.json`. So every gate box since Sept 29 forked from a five-root holdout, and the GOOGL program's
  look had failed three times on Sept 30 with "no holdout days for GOOGL, MSFT" (infrastructure failures, not looks).
  With the daemon idle and stopped (07:05:31Z), the re-base wrote `data/images.json` and `data/nightly.json` (backups
  kept) to name the 25-root gate image. The daemon restarted at 07:06:41Z, copied the forward days onto the new chain
  (retrying through Sail transport timeouts) and published it at 07:26:13Z. Verified on an idle gate box: all 25 roots
  hold the full 2026 holdout in nbbo, underlying and open interest, plus the forward days. The program's three failed
  tries were reset to 0; the looks table still held 2 rows.

### 04:25Z, operator change (no deploy): a pre-open research burst, reverted at 13:15Z

- **`swarm.json` at 04:24:58Z:** `researcher.sail_usd_per_hour` 1.3 → 2.5, `gym.max_boxes` 6 → 8 and
  `architect.every_seconds` 1800 → 900. Release B's reset had cleared every Train best, and practice cohorts form at
  the 13:30Z open only from Train-eligible versions. Estimated cost: about $25. Train runs went from about 40 to about
  195 an hour.
- **Reverted at 13:15:00Z** by a timer, as planned, to 1.3, 6 and 1800 (verified at the 13:33Z open check). The revert
  also ended the 11:03Z stopgap (`architect.every_seconds` 3600).

### 04:01Z, operator change (no deploy): the incubator switched on

- **`live.incubator`** set to JSON `true` in `swarm.json` (a before-copy kept), outside a session, after the
  ratification and the checks below. `python3 -m league.live --root /workspace/state --incubator` read `switch.on`
  true, a zero tally and no instances.
- **Nothing trades on it yet.** A cohort is pinned only after its first look passes, and a first look needs 3 completed
  sessions and 10 program closes in the record before today. For cohorts admitted at the Oct 1 open, that is the Oct 6
  open at the earliest (sessions Oct 1, 2 and 5).
- **To switch it off:** `live.incubator` false in `swarm.json` ([docs/operations.md](docs/operations.md), "Current
  operation"). Within a minute its instances go to exits only and their working opens are cancelled.

### 03:49Z, Release B: House release `20261001T034829Z-d823e014ce16` (main `3eaf4d06`; PR #454), gateway `dafcfa05`, evidence reset 2

- **The gateway first: `dafcfa05`,** deployed at 03:48Z from the merge commit after `npm run check && npm test` (338
  tests pass).
  - It adds the research library's routes (`/v1/research/search`, `/read`, `/health`) and its KV binding `LIBRARY`
    (namespace `ltcm-gateway-library`), with `LIBRARY_DAY_UPSTREAM` "600". Its web reader now sends arXiv to the
    library.
  - The order routes are unchanged.
  - The kill switch stayed false, `/v1/health` answered 200, and the library's health read OK.
  - The rollback target is `ac2779ac`.
- **The House deploy.** Staged 03:48:34Z; promoted 03:49:07Z over Release A. The watch's verdict was PROMOTED, and the
  deploy exited 0. The rollback target (`previous`) is Release A, `20260930T200604Z-3bf48c3f8f9f`.
- **The money digest moved** `a3e2aa7c` → `42c4a3af` (`PINNED_DIGEST` `fcf8d735` → `595228a6`): the incubator's row.
  - **The grant was re-ratified** at about 03:59Z, after the PROMOTED verdict. No real entry was due before the
    13:30Z open, and ratifying after the verdict avoids a rollback-after-ratify mismatch.
  - The grant reads active on policy digest `42c4a3af`, at its third ratification, with micro and scaled entries
    allowed. Capital was read afresh: $1,246.73, the lower of equity and the ceiling.
- **Evidence reset 2, verified** (read-only, after promotion).
  - `research_evaluator`'s execution fingerprint moved (`2d3d0284` → `47587e22`). The Gym bundle
    (`gym-engine-4-e1c896f8d304`) and the image are unchanged.
  - Each of the 51 families alive at the start recorded an `evaluator_adopted` event.
  - A read-only lineage snapshot before and after the deploy compared 1,690 lineages and found 0 violations: trials,
    inherited trials and consumed holdout looks were unchanged, with 2 looks in all.
- **The B2 backfill** ran at the first swarm start, before the adoption: "incubator backfill: 1 programs barred from 14
  gate events". A failure that the gate had recorded only in its event log or its attempt counts is now a durable bar
  on its program, so B's own adoption could not erase it.
- **The live guards, verified.** `real_money` true; `failures` empty; no working order.
  - `house:rebound-live@0:h` is real, `observe` false, mode live, with no error.
  - The tuition instance is real, tuition and exits-only, with no error, and its position is open.
  - No `:i` instance exists.
  - The incubator's health block: the switch off (as deployed), the table as committed (50, 1, 4, 150, 3, 10, 0.80),
    0 verdicts, a zero tally and no weekly stop.
- **The harness observer** was re-pointed at B's base (`3eaf4d06`) and release digest. It has retained no improvement.
- **Criterion 1 under Release B.**
  - **The restart test,** 04:00:11-04:00:24Z (`floor_box.py stop`, then `start`), with the tuition position open. Both
    instances came back as above, the position was restored, real money stayed on and health listed no failure.
  - **The induced failure,** at about 04:00:31Z: the swarm process was killed with SIGKILL. The House's swarm step
    started a new one within 15 s, with a fresh heartbeat. The alive families (36) and the stored runs (77,027) were
    unchanged: nothing was lost or duplicated.
- **The freeze, in force.** `league/live` and `league/gym` now change only in a planned, deliberate release.
  - A change to either (or to `LEAGUE_FILES`, the fill model or the Gym image) moves the evaluator. Every practice
    cohort is bound to its evaluator, so such a change ends every practice cohort, and with them every incubation, for
    good. It also re-adopts selection.
  - Batch such changes into planned releases. Rollbacks and fixes for bugs that block or endanger real orders are the
    only exceptions.
- **A known skew, for a planned release.** The House runs Python 3.11 with numpy 2.4; the Gym runs Python 3.12 with
  numpy 2.5 (`requirements-gym.txt`). So a program can load and train in the Gym and still fail to load on the live
  path. The preflight (#438) flags it (`preflight_house_unloadable`). The root fix aligns the runtimes: a Gym image
  change is an evidence reset, and a House venv upgrade touches the money path, so it is scheduled, not hot-fixed.
- **The House live test.** Release B changed its order path again: the incubator's route takes its turn after the D2
  families and before the test, the test yields to an incubator refusal on its contracts as to a family's, and the
  incubator keeps $100 of room for the test's structure. `house_test.py`, the test's program, bounds and clock are
  unchanged. Releases A and B are recorded as deviations in the test's private addendum.
- **Operator steps:** [docs/operations.md](docs/operations.md), "Release B: deploy, ratify, switch on".

Release B was branch `release/b-20261001` (PR #454), merged to main as `3eaf4d06`: main `777b894f` (Release A) plus
nine reviewed pull requests and the gateway's KV binding:
- #451, the incubator's live route and money row (B1; money path);
- #444, the incubator's facts and the reader's belt, with durable bars (B2);
- #445, L1, the cohort keep, and #455, its restart safety;
- #456, L2', the incubator's keep (every check reads the record before today; the prior values are copied at the
  session day's roll);
- #447, the research library (it supersedes #428), and `aa435f9e`, its KV binding;
- #453, the evaluator-adoption fixes;
- #448, information-value allocation;
- #438, the API-misuse preflight.

- **Evidence reset 2.** B changes `league/live`, so the execution fingerprint moved. `league/gym` and `LEAGUE_FILES` did
  not change, so the Gym bundle and the image stay Release A's. At B's first start:
  - **Selection was re-adopted.** As at reset 1, every alive family's derived selection evidence was archived and
    cleared: Train bests, candidates, robustness, drift, validation and review. Runs, versions, lineage trial counts and
    consumed holdout looks stay. A validation already recorded on the same image and bundle may be judged again
    (`Tournament.recorded_validation`).
  - **Extension holds stay** (#453): only a new Gym image or bundle clears them, and neither changed.
  - **Practice restarts.** A practice cohort is bound to its evaluator, which is the bundle, the fill model and the
    execution fingerprint. So every cohort from Release A completes at B's first families pass, with the reason
    "evaluator changed; a new version needs fresh practice". A (family, version) that practised under A never practises
    again: practice after B starts from versions not yet practised.

  Evidence from before and after the reset is never compared.

#### What Release B carries

- **The incubator** (#451; `league/live/incubator.py`, `league/live/money.py`, `league/constitution.py`; money path).
  It ships switched off.
  - **The owner's terms.** Approved Sept 29, 14:51Z; the reading was settled Sept 30. A family that passes Train and
    the drift screen on its own, shows positive live practice, and passed the gate's review and audit, trades one lot
    of an approved real structure:
    - at most $50 of maximum loss a structure, fees included;
    - at most 4 structures held or working;
    - the route stops for the ISO week once its net realized loss reaches $150.
  - **The unit** is a practice cohort `(family, version)`. The incubator trades the cohort's frozen snapshot byte for
    byte, never the family's current row, as the REAL, tuition-flagged instance `<family>@<version>:i`.
  - **The first look** (pre-registered, `money.practice_ok`) is taken once per cohort. It comes at the first session
    pin at which the cohort's record before today holds at least 3 completed sessions and 10 program-closed trades
    under the running evaluator. It passes only with:
    - decision coverage of at least 0.80;
    - realized practice P&L above $0 over the program's closes;
    - above $0 over all closes;
    - above $0 over all closes plus the open mark.

    The look is recorded whether or not the switch is on, and a failed first look is final. Its verdict is saved before
    its private `first_look` ledger row, and a cohort with a recorded `first_look` row is never looked at again (its
    verdict is restored from the row). After a pass, each later session re-checks coverage and the three P&L tests on
    the longer record, and a failure ends the incubation for good. A program with no edge passes roughly a third to a
    half of the time: the weekly envelope bounds the cost, not the screen.
  - **The facts** (`bands.incubator`). The family must be:
    - alive, in the Gym band, with the version not demoted;
    - carrying a Train-and-drift pass for the version under the current evaluator and Train objective;
    - reviewed and audited by the gate on the version's run sha, under the current review contract;
    - not refused, failed or demoted by the gate on that sha;
    - not on D2's route.

    With B2 (#444), the reader also keeps its own belt (`incubator_refusal`), whatever the mark says: no row for a
    program the swarm barred (`incubator_barred`, which no adoption clears), one the gate's `review` names without a
    readable pass and a passed audit, one whose incubator review or audit failed, a refused version, a failed look, or
    a family whose verdict records cannot be read. A verdict is on the program (its run sha), so the belt reads these
    in every family that holds the same code and params, alive or retired. It also refuses a program while the gate
    owes it a bar (`incubator-bars-owed.json` beside the store; an unreadable file refuses everything).

    B2 also makes sure B's own evaluator adoption cannot erase a failure. At every swarm start, before the adoption, a
    backfill records as bars the failed reviews and audits that release B's gate left only in its event log
    (`swarm.gate` events, and third unclear answers in the attempt counts). The adoption then records, before it
    clears the selection, every failure held only in `review`, `gate_outcome` or the incubator's reviews, and every
    bar the gate owes.

    **B2 (#444) writes the facts, in this release.** The Train-and-drift mark (`train_passed`) is made by the
    tournament's hourly round for a version of an alive Gym family with an active practice cohort under the current
    evaluator: an eligible Train run, a profitable 1.5x robustness run, no demotion, a passing drift screen, and no bar
    on its program. The incubator's own review and audit are due once the cohort's practice shows at least 2 sessions,
    5 program closes and a positive program P&L, so they are ready by the first look. Both are bound to the evaluator
    they were made under, and an adoption clears them (never a bar). Neither is read by validation, the gate's holdout,
    the forward record or the bands' moves.
  - **The pins,** at the session's first families pass. At most 8 cohorts, one per family, by first-look return on risk,
    each needing:
    - the switch on and real money on;
    - a first look that passed, and a record that still passes;
    - the facts above, with the snapshot's run sha;
    - no D2 route for the family (`:r` and `:t` come first);
    - a real structure;
    - a sampled program close that one lot could open under the $50 cap.

    Every families pass checks again, and a failure sends the instance to exits only.
  - **Keep (L2').** While the switch is on, a cohort whose first look passed keeps practising past its observation
    target, to its bounded window. That is at most 8 cohorts. A failed read never ends an incubation: the last keep's
    cohorts stay kept (never pinned on the untaken check), and the next families pass takes the checks again. While
    the cohorts cannot be read, no cohort is completed at its target, for at most the day's 12 retries. The retries are
    counted durably from the start of each pass, and only for passes 5 minutes apart: a forced pass spends none. If the
    keep raises and the saved keep cannot be read, the House keeps the last keep it took, never nothing. Within a day
    the keep only grows, and a cohort kept without a verdict stays kept for the rest of the day, across a restart.
    Every first look and re-check, at the first pass or a retry, reads the record before today: the practice row keeps
    its coverage and open mark as the last session left them (`prior_*`, stamped with the day they were copied and read
    only on that day), so today's values never decide a check. A record without them, or with an older copy (a release
    that never copies them stepped the row today, as after a rollback), decides nothing on P3 or P6 (P4 and P5 still
    end it) and waits for the next session.
  - **The caps**, in the House only (`money.plan_incubator`). The gateway cannot tell routes apart, so its own caps are
    the backstop.
    - One lot of at most $50 a structure, and $50 held or working per family.
    - At most 4 structures held or working.
    - **The weekly envelope:** this week's net realized loss, plus what is held, plus what is working, plus the new
      unit, at most $150 at every open. Once the week's net realized loss reaches $150 at any close, the route is
      stopped for the rest of the ISO week, whatever a later gain does. The stop is a latch, alerted once a week.
    - 40 order legs a day, and 25% of the gateway's day cap.
    - Room is kept in the book's and the day's caps for two Probe floors ($200) and, while it can still open, the
      House live test's structure ($100).
  - **The order of a minute.** The D2 families' intents go first (`:r`, `:t`), then the incubator's, then the House live
    test's, then the calibration's. A working incubator open is cancelled ("yielded") when a D2 family's real order is
    refused on its contracts after that open was placed.
  - **Never evidence, never a promotion.** Its orders and positions are tuition-flagged. It is never:
    - a forward row (`_export_real` skips every `:i`);
    - a band move;
    - in tuition's own day and week sums.

    D2 stays the only route to Probe and Sized.
  - **Its belt.** An `:i` instance must be real, tuition-flagged, and on a House with an incubator. Anything else asking
    for a real order is refused with an error alert: "live: `<key>` is not a real tuition incubator instance and asked
    for a real order: refused". A restored `:i` instance is tuition-flagged whatever its row says.
  - **Where it shows:**
    - `health.json` `options_live.incubator`: the switch, the table, the pins and refusals, the keep, the verdict
      counts, the tally and the weekly stop;
    - each instance's `incubator` flag;
    - `python3 -m league.live --root /workspace/state --incubator`, read-only;
    - private `live.incubator` ledger rows: first looks, ends, pins, yields and the weekly stop;
    - on the site, the positions table's `source` "incubator" and a real structure's `route` "incubator"
      (personal-site #17 is live).
  - **The switch:** `live.incubator` in `swarm.json`, off by default. Only JSON `true` turns it on; any other value
    reads off and is alerted once. Off, its instances go to exits only and their working opens are cancelled within a
    minute. It is switched on outside a session, after the ratification.
  - **The cost.** Expected value is negative until a family has a real edge: at most about $650 a month on average ($750
    in a five-week month), plus residuals (broker fees above the book's estimate, a broken structure closed leg by leg).
  - **The money row** `options_money.incubator`: `max_loss_usd` 50, `contracts` 1, `max_open` 4, `week_loss_usd` 150,
    `min_sessions` 3, `min_trades` 10, `min_coverage` 0.80. The owner's terms are the loose end of each bound, so a row
    may only tighten. Setting `max_open`, `week_loss_usd` or `max_loss_usd` to 0 stops the route. That is a new digest
    and a ratification, but no evidence reset: the constitution is outside the fingerprint.
  - **Earliest possible open:** Tuesday Oct 6, at 13:30Z, for cohorts that begin practice on Oct 1 (sessions Oct 1, 2
    and 5).
- **B2, the incubator's facts** (#444; `league/swarm/incubator.py`, `league/swarm/bands.py`, `league/swarm/gate.py`):
  the Train-and-drift mark, the incubator's review and audit, the reader's belt, durable bars on the program, and the
  backfill (all under "The facts", above). Swarm side; the fingerprint does not hash it.
- **L1, the cohort keep** (#445, with #455's restart fix; `league/swarm/tournament.py`, `league/swarm/practice.py`,
  `league/swarm/researcher.py`; research side).
  - **What it spares.** A living Gym family with an active practice cohort is spared the tournament's revision,
    evaluation and idle rules, and the idle pass. The keep lasts until the cohort completes, fails or reaches its
    session window. So a family is still alive when its sample is complete and the incubator takes its first look.
  - **What it never spares:** the deflated-Sharpe rule, its researcher's or the diagnostician's own retire, the
    population floor, or the operator's gate hold.
  - **The record it reads** is the cohort's realized record before today. Until the cohort meets the sample (3 sessions
    and 10 program closes), it is kept whatever that record says. After that, it is kept only while program-closed P&L
    and all-closes P&L are both at least 0.
  - **Not kept:**
    - a cohort the House has not practised on 2 sessions while it practises others;
    - a cohort whose practice row began before it.
  - **At most `tournament.incubator_keep_max` (12) families;** 0 turns it off. Those that meet the sample come first,
    by return on risk.
  - **Its record:** one private `swarm.status` event a round (`incubator_keep`).
  - **The researcher's status line.** The keep is saved (`cohort_keep`), so a kept family's researcher is told that
    idleness is no reason to retire it. The retire tool stays offered.
  - **An unreadable record** leaves the last good keep standing for an hour, then none. A fresh swarm process whose
    first read fails takes the keep the last process saved for the rest of that hour, and does not overwrite it
    before then (the release review's restart finding; swarm side, no evidence reset).
  - **Research attention only:** no trial count, look, validation, gate, band or money rule reads it.
- **The research library** (#447, supersedes #428; `gateway/lib/library.mjs`, `league/swarm/library.py`). It is off on
  the House until `research.enabled`.
  - **The gateway** serves `GET /v1/research/search`, `/read` and `/health`: arXiv's quantitative finance,
    econometrics, statistics and machine learning on markets, posted before 2025 and nothing later. The date rule is
    code, on every answer, and the House checks every answer again. Details: [gateway/README.md](gateway/README.md),
    "The research library".
  - **Pace:** arXiv's terms (one request every 3 s, one connection; arxiv.org's crawl delay of 15 s).
    `LIBRARY_DAY_UPSTREAM` allows 600 requests to arXiv a UTC day for the whole floor; `"0"` stops them, and cache hits
    still answer.
  - **The House:**
    - the Claude researchers get a `literature` tool;
    - the architect and the strategist get a retrieved block of abstracts;
    - the strategist names the next searches;
    - Sail's profiles never see it.

    Three lines: 300 calls a day for the floor, 12 a family, 2 a research cycle. Each call is a private
    `swarm.research` event, never mirrored.
  - **The Claude researcher band is off on the box**, so only the architect's and the strategist's blocks are used when
    it is switched on.
- **The gateway's KV cache for the library** (`aa435f9e`). The binding `LIBRARY` is namespace `ltcm-gateway-library`,
  created 20:25Z Sept 30. Never delete it once a deployed version binds it: that would block `wrangler rollback` to
  those versions.
- **Evaluator adoption fixes** (#453; `league/swarm/evaluator.py`, `tournament.py`, `researcher.py`,
  `scripts/extension_hold.py`).
  - **Extension holds.** An adoption archives and clears the extension hold's records only when the Gym's image or
    bundle changes. A `league/live`-only adoption, such as B's, keeps holds and the operator's clears.
  - **Lapses.** A validation of a held version that falls below the checks ends the hold (`extension_lapsed`). A later
    validation of it that meets the checks holds it again.
  - **Idle wording.** After an adoption, the idle count restarts from `evaluator_trials`. Retirements then say "since
    the evaluator changed", no longer "since Train's span changed".
- **Information-value allocation** (#448; `league/swarm/allocation.py`, `loop.py`, `architect.py`; research side).
  - **The share.** Every living family's share of researcher turns and Gym priority is a floor (0.10, spread evenly), an
    exploration share (0.35) across mechanism classes (structure x root group), and a decision share (the rest) by its
    value.
  - **The value** is the variance of its next validation's pass or fail under an empirical-Bayes posterior, discounted
    for the depth of its idea's lineage, for exhaustion (spent looks, a drift-failed or gate-spent version, a hold
    streak) and for a structure the account cannot open for real. So a family near the line earns the most, and an old
    family at zero or below never earns a large share.
  - **The caps:** 5% a family and 30% a mechanism class, while the other classes can take the excess. Shares buy turns
    (stride scheduling, `allocation.scheduler` "stride"), and one structure family may hold at most 60% of the last 24
    hours' births (`BirthQuota`).
  - **Research attention only:** nothing on the way to validation, the gate, the bands or money reads the share.
    `allocation.mode` "bandit" in `swarm.json` restores R11-5's bandit with no deploy.
- **The preflight** (#438; `league/swarm/preflight.py`, `researcher.py`; research side). Before a Train run is spent, a
  candidate program meets small synthetic sessions in the live decider's sandbox.
  - **It refuses only market-independent misuse of the ctx API:** the same misuse at the same line on 25 consecutive
    calls across two sessions, and again on each of five other made-up markets. Everything else is advisory, and the
    run goes on to the Gym, which judges it. Of 300 programs that ran OK in the Gym, it refused none.
  - **The House's runtime.** A program that passes the static code check but does not load on the House's runtime
    (Python 3.11, numpy 2.4) is advisory, and counted (`preflight_house_unloadable`). Its Train run goes ahead, since
    the Gym (Python 3.12, numpy 2.5) may load it, but as written it can never practise or trade live.
  - A refusal costs no Gym job, version or trial. A sweep drops only the refused variants. The preflight never blocks
    on its own failure.
- **Not in B.** These ship when their reviews are clean. They change no file the fingerprint hashes, so none is a
  reset:
  - #446, family cards;
  - #449, harness lanes;
  - #452, evaluator benchmarks.

  Any change to a module the live path loads still deploys only outside the session.

## 2026-09-30

### 20:16-21:25Z, after Release A: operator changes (no deploy)

- **20:16Z, the graveyard verdict migration** (R11-1, once; `scripts/graveyard_verdicts.py --apply`). It re-headed
  1,611 lessons: DRIFT 1,046, THIN 393, EXHAUSTED 145 and STRESS 27, leaving 5 IDLE. The backup of every changed row
  is in `state/backups/`.
- **`swarm.json`:** `claude.role_effort.architect` "medium", `gym.max_boxes` 4 → 6 and `architect.max_refill` 4 → 12.
  These are the settings planned for after Release A.
- **The input capability card** is installed on the box. It is private and matches the Train image.
- **The extension hold seed was not run.** Adoption clears `validation_version` first, so its list is empty by design.
  Families are held when their engine-4 validation meets the checks.
- **Near-miss revivals** (the operator's choice from the validation line). Five families, each a lineage continuation
  that inherits its lineage's trials and holdout looks. None had a consumed look to inherit.

  | Revived as | From | Inherited trials |
  |---|---|---|
  | `silver-industrial-cycle-debit-r` | `silver-industrial-cycle-debit` v58 | 993 |
  | `etf-implied-move-ratio-follow-debi-3` | `etf-implied-move-ratio-follow-debit` v17 | 160 |
  | `second-session-assimilation-call-r` | `second-session-assimilation-call` v31 | 204 |
  | `tlt-realrate-metals-catchup-debit-r` | `tlt-realrate-metals-catchup-debit` v30 | 1,126 |
  | `market-distraction-release-call-r-2` | `market-distraction-release-call` v11 | 112 |

  Their notes ask for the validated version to be re-run unchanged under engine 4. The outcome is in the run record: the
  numbers came back identical, and the deflated-Sharpe check now fails.
- **The harness observer** has been on since 20:19Z, in observe mode (`state/harness/runtime.json`). No harness
  improvement has been retained.
- **20:42Z, architect agenda v15.** It steers only; D2 and every kill test are unchanged, and its text stays private.
- **Pull requests:** #427 and #430 closed, shipped through Release A; #428 closed, superseded by #447.

### 20:16Z, Release A: House release `20260930T200604Z-3bf48c3f8f9f` (main `777b894f`; PR #450), evidence reset 1

- **The deploy.** Staged 20:06:06Z; promoted 20:06:42Z. The ten-minute watch passed with 0 error alerts, and the
  verdict was PROMOTED at 20:16:42Z. The rollback target (`previous`) is `20260930T045038Z-cb6035693ef4`.
- **Money digest unchanged** (`a3e2aa7c`); no re-ratify.
- **Evidence reset 1, verified.**
  - The swarm recorded its evaluator (`research_evaluator`: the Gym bundle `gym-engine-4-e1c896f8d304`, the image and
    the execution fingerprint).
  - A read-only lineage snapshot before and after the deploy compared 1,585 lineages and found 0 violations:
    trials, inherited trials and consumed holdout looks were all unchanged, with 2 looks.
- **The live guards, verified.**
  - `house:rebound-live@0:h` is real, `observe` false, mode live.
  - The tuition instance `googl-lags-msft-ai-cloud-qqq-flat@27:t` came back `exit_only` by design. Adoption dropped its
    engine-3 tuition row: an engine-3 validation bundle, and a review with no `contract_sha`. Its open position is
    kept, and the program's own closes manage it. The family must qualify again under engine 4 to trade tuition again.
- **The restart test, passed.** `floor_box.py stop` at 20:19:00Z and `start` at 20:19:17Z, with that real position open.
  - Both instances came back as above.
  - The position was restored.
  - `real_money` was true, and `failures` was empty.
- **The induced-failure test, passed.** At about 20:50Z the swarm process was killed with SIGKILL.
  - The House's swarm step restarted it within 15 s, with a fresh heartbeat.
  - The alive families (15) and the runs (75,473) were unchanged: nothing was lost or duplicated.
- **The first hour (20:17-21:21Z, read-only).**
  - 0 cycle errors; House load 0.72.
  - 136 Train runs ok, 17 disqualified (11%), 8 validations.
  - Births: 7 debit verticals, 3 `long_single`, 2 `long_call`.
  - The tournament spread its shares at about 10-13% a family.
  - The population fell from 41 to the floor of 12 within 10 minutes of the deploy: researchers now retire the
    mechanisms they refuted (R11b). The architect refills up to 12 births every 20 minutes, on Kimi-K3.

Release A was branch `release/a-20260930` (PR #450), merged to main as `777b894f`:
- main `f082cf5e`, which carries #431-#436, merged Sept 30 between 05:59 and 08:27Z;
- plus six reviewed pull requests merged on the branch: #437, #443, #440, #439, #442 and #441.

- **Evidence reset 1.** The evaluator's execution fingerprint and the Gym bundle both moved:
  - the fingerprint (`league/swarm/evaluator.py`) hashes `league/gym`, `league/live` and `LEAGUE_FILES`;
  - engine 4 (#431), #436's driver, the Gym batch isolation (#440), the live guards (#437) and the decider (#443) all
    change those files.

  The release before it had no evaluator record, so Release A's first start adopted one for every alive family:
  - **Cleared, and archived in the family's state:** Train bests, candidates, robustness, drift, validation and review.
    A Candidate, Probe or Sized family whose banded evaluator no longer matches returns to the Gym. Every family was in
    the Gym.
  - **Kept:** runs, versions, lineage trial counts, refusals, notebooks and consumed holdout looks. Consumed holdout
    looks never reopen.
  - **Practice** started under the new evaluator. It needs Train runs under the new bundle, so the practice league
    started nearly empty.

  Evidence from before and after the reset is never compared.
- **The House live test.** Release A changed the test's order path: the belt it passes, and the decider child it runs
  in. The test's own program and bounds are unchanged. The change is still to be recorded as a deviation in the test's
  private addendum, with Release B's.
- **Operator steps after promotion:** [docs/operations.md](docs/operations.md), "Release A: after promotion".

#### On the release branch

- **Live guards from #427, on main** (#437; money path). Two guards:
  - `Instance.observe` is True only for a shadow, non-tuition `:o` instance. A bad value is coerced, never raised. So
    a real instance, the House live test's included, is never an observe one, restored or not.
  - A belt in `_real_intent` refuses any instance that is not real, whose observe flag is not False, or whose key is
    an observe key. It covers opens, closes and cancels alike, and raises an error alert: "live: `<key>` is not a real
    instance and asked for a real order: refused".

  Tuition and the House live test pass the belt. Calibration never takes this path. Tests:
  `league/tests/test_live_restore.py`.

  After the deploy, check:
  - `options_live.instances["house:rebound-live@0:h"].observe` is `false`;
  - every `:o` instance is `true`;
  - no "not a real instance" alert.
- **The live Decider hardened** (#443; money path).
  - **A failed network-namespace probe is retried**, not cached. Before, a probe that timed out on a busy minute was
    kept as a permanent False: every later spawn on the root House failed until a restart. Real instances would then
    be orphaned and closed after five minutes.
  - **The probe's timing:**
    - its timeout is 3-10 s, whatever is left of the minute;
    - after a failure, spawns inside 30 s are refused without probing;
    - a spawn after that probes again.
  - **Fails closed off a root House.** A `Decider` not running as root refuses to start a child. Only tests pass
    `allow_unisolated=True`; there is no switch for it.
  - **Child limits:** the child caps any file it writes at 64 MB (`RLIMIT_FSIZE`) and can start no process or thread
    (`RLIMIT_NPROC` 0).
  - **Logs:** before each spawn, the House moves a decider log of 32 MB or more to `<log>.1`.
- **Gym: one bad program no longer fails its batch** (#440; `league/gym`, money path).
  - **The incident, 14:03Z Sept 30:** one program parsed but did not compile. It raised `SyntaxError` in the batch's
    load check, and all eight families in the batch got "the Gym failed twice".
  - **Admission:** `check_program` now compiles as well as parses, so such code is refused at admission, with its line.
  - **Per-program results:**
    - any load failure in the parent is that program's `refused` result;
    - a load failure in a worker, or an exception from one program's run, is that program's `error` result, with 0
      trials;
    - the rest of the batch runs on, and its results are byte-identical to running those programs alone.
  - **Still whole-unit failures:** a `MemoryError`, a dead worker or the unit deadline.
- **Funding alerts before the Claude, OpenAI, Sail and burst cliffs** (#439; research-side, no fingerprint move).
  - A new `league/swarm/funding.py` runs on the swarm's loop. It covers four cliffs:
    - Claude's room: a runway from measured burn;
    - the Sail guard's line: a runway;
    - the gateway's OpenAI month end: calendar;
    - `guard.burst_until`: calendar, with the research cut.
  - **Tiers** are notice, warning, urgent and out.
  - **Dedupe:**
    - each tier is said once;
    - warning, urgent and out repeat every 12 h while they stand;
    - a recovery is one `funding_ok` event.
  - **Fallbacks:** every call that asked Claude and ended elsewhere is counted as a `claude_fallback` event. Only
    `no_room` is an alert.
  - **Where it shows:** alerts reach the House as `ops.alert` warnings, never errors, so they never roll a release
    back. The last assessment is in the heartbeat under `status.funding`.
  - **The site shows none of it.**
- **CI never cancelled by its own time limit** (#442).
  - The Checks `tests` job limit is 35 minutes (was 20). The Sept 30 push run on `f082cf5e` was cut off at 20 minutes,
    which the updater reads as no verdict.
  - The hourly run has its own concurrency group, so it no longer cancels a push run on the same ref.
  - CI keeps the tests' scratch on tmpfs (`/dev/shm/ltcm-tests`) when it can.
  - Faster league tests, with the same coverage:
    - the fake market prices a chain once per read;
    - the swarm tests share one Gym bundle version;
    - the hung-decider test uses a 0.75 s budget.
  - `TRUSTED_WORKFLOWS_SHA256` in `league/updater.py` moves to `9aa3c732` in the same commit: a workflow change is an
    owner deploy.
  - No fingerprint or money-digest move.
- **Public site cost** (#441; the site side is personal-site PR #17). Not the money path.
  - **Sail on its billed basis:** the Sail guard's balance meter, plus $0.46 of box billing before the meter began.
    Before, it was the Gym's booked box estimate, which runs about 70% above the bill.
  - **Claude as its own part**, `claude_usd`.
  - **Older-site fallback:** the House tries each older shape alone before both.
  - **The site:**
    - shows Net = realized options P&L since T0 minus every input cost since T0, a dash while any part is null or
      stale;
    - shows the costs by service, the practice league's block and the Incubator label.

  Either repository may deploy first.

#### From main `f082cf5e` (#431-#436, merged Sept 30)

- **Engine 4 and evaluator adoption** (#431; `league/gym` and `league/live`).
  - **Engine 4** (`gym-engine-4`) binds parameter overrides to module `PARAMS` at its declaration, before aliases and
    helper defaults capture them. `ctx.params` starts with the same values.
  - **The evaluator record:** at startup, before any worker selects, the swarm records its evaluator
    (`research_evaluator`: the data image, the Gym bundle and the execution fingerprint). A change is adopted as
    Release A's reset describes (above).
  - **Entry authority:** Candidate, Probe and Sized entry also pins the program hash and the fingerprint
    (`banded_evaluator`). An old fingerprint denies new opens, and exits go on.
  - **Worker run ids:** colliding ids across evaluator bundles keep separate results.
  - **Pre-deploy scan** (read-only, Sept 30): engine 4 loads all 106 programs, meaning the alive families, the practice
    tier and the House test's. The House test's program gives identical intents under engines 3 and 4 on synthetic
    data. Two alive programs read module `PARAMS` with overrides and will behave differently; the reset keeps their
    evidence apart.
- **Research that waits for news, and retirement that can land** (#431).
  - **Holds:** `researcher.hold_until_news` (default true) stores a hold in the family's state. Only new evidence, gate
    state, guidance, the agenda, the image or the harness release wakes it; time and restarts never schedule another
    paid call.
  - **Retirement:** a researcher may retire after `researcher.retire_min_trials` (10) counted trials or two
    validations, on either turn, down to `population.floor`.
  - **The experiment-contract check:** `gym_run` and every `gym_sweep` variant pass a static check (`check_experiment`)
    before a version or Gym job exists. Unread parameter changes and malformed overrides are refused without a trial.
  - **Graveyard format 4:** economic claims are limited to the versions tested.
  - **Grounded reviews:** the gate's reviewer and auditor read the runtime's actual contract
    (`league/gym/review_contract.py`).
- **Causal optional volume context** (#431).
  - **What reaches a strategy:** share bars reach strategy contexts only with first-observation receipts and explicit
    provenance and coverage.
  - **Finalized historical bars without those receipts stay unknown**, daily sums included: a completed-minute grid
    does not prove what was published then.
  - **Live:**
    - reuses existing stock snapshots;
    - persists first observations across restarts;
    - excludes incomplete bars and index proxy volume.
  - **Test:** a late-revision regression checks that finalized history cannot replace the first live value.
  - **Not changed:** no data purchase, production mutation, SQL or site migration, or money-rule change.
  - Actual live coverage remains to be measured after adoption.
- **Persistent practice cohorts and receipts** (#431, building on #430's code).
  - Immutable shadow snapshots survive research churn and restarts. Bounded observation windows include longer-DTE
    programs.
  - No snapshot is promoted into real money.
  - Private receipts (decision, order, quote, fill, slippage) retry across restarts.
  - Program errors reduce coverage, and open marked P&L includes fees already paid.
  - Material researcher feedback requires ten program closes over three sessions.
  - Sized's fresh-forward window starts after both the creation and the selection of its version.
  - New cohort, receipt and feedback tests use simulated quotes only. Actual multi-session practice evidence remains to
    be collected after deployment.
- **The live practice league** (#430's code, merged through #431; #430 itself stays open and is closed as superseded
  after Release A).
  - **What it is:** every alive Gym-band family with a validated version, or an eligible Train version (the
    tournament's candidate, not demoted), trades live quotes in the shadow book under the Gym's fill rules, on a
    $10,000 practice account.
  - **What it is never:** real, tuition, a forward row, or a band move. Release A's #437 guards hold this in code.
  - **Admission:** validated by validation t, then Train by Train score, under two caps:
    - `live.observe_max` (48);
    - `live.observe_roots_max` (24 distinct roots, the binding resource measured on the House Sept 29).

    `live.observe_train` and `live.observe_read_calls` are set in `swarm.json`.
  - **Pressure:** sustained pressure (3 pressed minutes of 10) sheds the lowest-priority quarter of the Train pins for
    the session. Validated pins are never shed.
  - **The practice ledger** (`observe.sqlite`): per family and version from its first live minute, kept after
    retirement. It holds:
    - realized P&L after fees (the headline);
    - forced wind-down closes, apart;
    - open positions at the engine's mark;
    - realized and marked drawdown;
    - coverage.

    `practice_summary` is read-only.
  - **Research feedback** (`league/swarm/practice.py`, `practice.feedback`):
    - the strategist's PRACTICE table;
    - the architect's PRACTICE BY CLASS lines;
    - the bandit's bonus: at most +25% of a family's share and at most 10% of all share moved. It changes the weight
      only, which nothing on the way to real money reads.
  - **The forward embargo:** a Sized move also needs the forward record after its version was written and selected. It
    is a tightening; nothing is Sized today.
  - **The site's `practice` block:** personal-site PR #17 takes it. Until that site deploys, the House posts without it
    and warns once.
  - **Unchanged:** the money digest stays `a3e2aa7c`, and D2.
  - **After the deploy, check:**
    - `options_live.observe` shows `tiers`, `roots_used` and `effective_cap`, and no `shed`;
    - `observe_reads_skipped` stays 0;
    - `observe.sqlite` `practice` rows appear from 13:31Z;
    - there is no `:o` in `live.sqlite` or in the swarm's `forward`;
    - the tournament event's `practice_bonus` values are at most 0.25.
- **R11b: honest verdicts, corrections that land, effort where it pays** (#431). These are the ROI plan's R11 code items
  (Sept 29, section (b)). Research-side only: the money digest stays `a3e2aa7c`, and Train figures only (D2).
  - **R11-1, verdicts and retirement:**
    - an idle-rule death is filed under its Train record's verdict: DRIFT, STRESS, THIN or EXHAUSTED, and IDLE only
      for the untested;
    - the digest (format 3: one reseal) and the strategist (`screen` per family) read the verdicts;
    - a family holding three cycles with an eligible run, or ten trials, is offered `retire`;
    - a researcher's retirement is SELF-REFUTED;
    - `scripts/graveyard_verdicts.py` re-heads the rows already buried (the operator's; a dry run by default).
  - **R11-2, the strategist and the class cap:**
    - known ids are masked before the strategist's content rules;
    - the prompt aims at 85% of the cap;
    - a length-only overflow up to 15% is trimmed at a sentence end;
    - `architect.max_alive_per_class` (12) caps births per mechanism class.
  - **R11-3, effort:** `claude.role_effort`. A cut architect answer keeps its complete families with one medium retry
    on Claude, never a Kimi-K3 refill.
  - **R11-5, exploitation:** the bandit exploits only old families with a positive validation mean, 15% each at most.
  - **R11-6, the Gym's zero-trade probe:** off until `researcher.probe_year` is set.
  - **R11-4's rule, the extension hold:** a validation that met six checks holds its family out of the dormancy clause
    until the operator clears it (`scripts/extension_hold.py`).

  Operator steps after the release: [docs/operations.md](docs/operations.md), "Release A: after promotion". A4 was never
  applied, so `tournament.explore_share` needs no change.
- **Two-sided singles: the `long_single` structure** (#425, merged through #431).
  - **What it is:** a family may declare `long_single`, one program that opens one `long_call` or one `long_put` at a
    time (one leg, long), the side chosen by its rule. It takes the place of a call/put twin pair.
  - **The architect:**
    - its prompt describes the side rule, and why its calls and puts balance: the drift screen charges whatever net
      exposure it holds;
    - it asks for no twins;
    - `admit` refuses a one-sided twin beside a living `long_single`, or the other side of the same idea on the same
      roots.
  - **GAPS and coverage:** in GAPS, a single option's one gap is `long_single`. The one-sided singles are no longer
    gaps, though they are still admitted. Coverage has its row.
  - **Prompts:** the researcher, reviewer, auditor and diagnostician read what its orders are.
  - **Lineage:**
    - it shares its singles' slice for lineage matching and identical-code links;
    - a `long_single` that continues one twin joins the other twin's lineage too (`link_lineages`);
    - a new lineage on a singles' slice counts the newest dead lineage of each type there (`slice_priors`,
      `prior_lineages`). Every other structure keeps its one prior.
  - **Real money:**
    - real eligibility (tuition, Probe, Sized, the site's `real_structure`) needs BOTH `long_call` and `long_put` among
      `options_money.real_types`;
    - every order keeps its own type, is checked by it at the real book and the gateway, and is sized by its own unit;
    - the live path refuses a real open of any other type from a `long_single` family.
  - **The site** shows the agent's structure as null (its schema has the eleven order types) and each position as its
    own type.
  - **Unchanged:** no Gym, verifier, D2, drift-screen, gateway or money-table change. The money digest stays
    `a3e2aa7c`.
  - **Rollback:** once a `long_single` family exists, roll forward rather than back past it. A release before it fails
    every architect pass.
- **Benchmarks and the harness controller** (#431).
  - `python -m league.swarm.benchmarks` runs synthetic statistical controls through the actual Train, Validation and
    holdout arithmetic. These are not market evidence.
  - A protected Scheduler-lane harness-improvement journal, with sandboxed comparisons
    (`playbooks/harness-improvement.md`).
    It authors and deploys nothing itself.
- **Research supervision and honest cost evidence** (#432).
  - **The harness observer:** a release-bound, read-only observer with a private policy. It is off until the operator
    writes its `runtime.json`.
  - **The input capability card:** researchers and the architect read a private card of Train-image coverage
    (`input-capabilities.json`; historical volume stays unavailable).
  - **A frozen `long_single` gate benchmark**
    ([docs/benchmarks/LONG_SINGLE_GATES_1.md](docs/benchmarks/LONG_SINGLE_GATES_1.md)).
  - **A private project-economics report**, which keeps holds, estimates and settled bills apart
    (`playbooks/project-economics.md`).
- **Historical SIP completion that keeps its gaps** (#433).
  - A durable per-root, per-day gap queue lets the scan advance past a missing root.
  - Only complete, validated minute grids replace canonical data.
  - Image readiness is bound to verified file hashes and the intended image pair
    ([docs/data-sip-completion.md](docs/data-sip-completion.md)).
  - After the deploy, the data side needs `sip-progress.sqlite` and a rescan of legacy readiness.
- **One agenda read per scheduler scan** (#434, `league/swarm/loop.py` only). Measured on synthetic populations of 7-127
  held families: 40-49% fewer SQL statements a scan, with unchanged semantics. This is not a retained harness
  improvement.
- **A finite local practice runner** (#435; `scripts/practice_run.py`, [docs/local-practice.md](docs/local-practice.md)).
  - It runs explicit replay or synthetic bundles in a mandatory bwrap sandbox, with no brokerage account and no House.
  - It never writes bands, forward evidence or feedback.
- **Gym result downloads retried** (#436, `league/gym/driver.py`).
  - A timed-out or dropped download of a finished Gym result is retried inside the driver's existing attempt limit and
    backoff, instead of requeuing the batch.
  - TLS, permanent DNS, permission and unknown failures are not retried.
  - The driver is part of the Gym bundle, so its version moves.

### Earlier on Sept 30

**16:41Z, operator change** (no deploy): the spend cut. The owner's Sept 30 answer was to cut burn to evidence, roughly
halving the $84-104 a day. `swarm.json`:
- `claude.role_usd_day.architect` 10 → 0: architect births go to Kimi-K3 on Sail;
- `researcher.stall_revisions` 12 → 10000: stall rewrites off;
- `diagnostician.enabled` unset (on) → false;
- `researcher.sail_usd_per_hour` 4 → 1.1.

The gate's review and audit and the strategist stay on Claude. The evidence and the target are in the run record
(`docs/runs/2026-09-30-continuous-learning.md`): about $2.10 an hour, about $50 a day. `live.*`, calibration and the
House live test are unchanged.

**16:07Z, operator change** (no deploy): an interim research throttle, because Train evidence from before Release B is
archived by the night's evidence resets. Backup `swarm.json.before-set-20260930T1607*`. `swarm.json`:
- `gym.max_boxes` 16 → 4;
- `gym.start_boxes` 6 → 2;
- `researcher.sail_usd_per_hour` 12 → 4;
- `architect.max_refill` 12 → 4;
- `claude.role_usd_day.architect` 25 → 10.

`live.*`, calibration and the House live test are unchanged. After Release A: `gym.max_boxes` 6 and
`architect.max_refill` 12 again.

**05:01Z, restoration fix: House release `20260930T045038Z-cb6035693ef4`** (main `87af7a62`; #429).
- Promoted 04:51:15Z; ten-minute health watch passed at 05:01:20Z.
- Real instances restore by keyword, keeping `observe` false and the saved execution mode.
- Verified on the running House: `house:rebound-live@0:h` is real, `observe: false`, mode `live`;
  supervisor and House alive, health fresh. No options or working orders before the restart.
- Money digest remains `a3e2aa7c`; the grant and accounting baseline were not changed.

## 2026-09-29

**13:44Z, R11a: House release `20260929T134303Z-8366493c614c`** (main `2f6d5109`; #424, Train from 2017).
- The first research-side release under the owner's amended D8: research releases may ship during the session when
  nothing in the money path changes.
- No file under `league/live`, the gateway or the constitution changed. The money digest is unchanged (`a3e2aa7c`).
  0 real positions and 0 working orders at deploy.
- On the box: 0 `train_span_mismatch` events, the swarm cycling (171 cycles and 63 runs in the first minutes), the
  backfill controller alive.
- `gym.train_from` stays 2020-01-02 until image T (2017-24) is built, bridged and pool-checked.
- What #424 carries:
  - **The window.** Train's window, `storelib.TRAIN_EARLIEST` and `gym.train_from` reach 2017-01-03. That is a third
    start beside 2020-01-02 and 2022-01-03; over eight years the derived split is 24 and the time limit 2400 s.
    Stage 9's `EARLY` stays the literal 2020-01-02..2021-12-31.
  - **New public tables:**
    - the 2017-2019 scheduled FOMC days (Federal Reserve meeting pages);
    - CPI and Employment Situation release days (BLS release archives);
    - the rate steps back to 2015-12-17 (the Fed's target-range changes, upper bound less 0.10, as before).
  - **First Train day.** A Gym store's first Train day is its first chain, so a 2020 image's 2019 history sessions stay
    out of Train. `images.py build gym --root-first ROOT=DATE,...` gives a root its own later first Train day, recorded
    in images.json and checked from inside. The fork prunes with the build's own data tools.
  - **A build from 2017** lists its roots and refuses unless every name (a root outside the core five) either has a
    first day on or after 2020-01-02 or is named in `--early-names` (for after its split rows are in). It refuses
    `--early-roots`.
  - **The inside check** holds every other name to 2020-01-02, and the image's first chain to its `train_from` exactly.
    `images.py verify --root-first` reads the recorded `train_from`.
  - **Nothing moves** until an image is built with `--train-from 2017-01-03` and `swarm.json` names it with
    `train_from`.
  - **On release** the Gym bundle and tables digests changed, so every program re-runs once as a new trial and each
    family is re-validated once, as with #399.

**13:36Z, operator change:** `live.observe_max` 8 → 48. **13:20Z:** `architect.max_refill` 24 → 12,
`architect.every_seconds` 600 → 900.

**06:58Z, operator change** (no deploy): the strategist switched on.
- `architect.agenda_locked` is the operator's preamble: agenda v14 without its WHERE TO LOOK directions, plus two
  new binding lessons, that widening does not create edge and that the rebound's 2024 survives every regime gate.
- `claude.roles` adds `strategist`; `claude.role_usd_day` sets architect $25 and strategist $4; `strategist.enabled`.
- Backup `swarm.json.before-strategist-20260929T065848Z`.

**06:48Z, R10: House release `20260929T064727Z-c607a8aa390e`** (main `a700c3ba`; #419).
- The architect reads the whole graveyard as a digest in its Claude context.
- The strategist writes the WHERE TO LOOK section under the locked preamble, with a validator that refuses rule,
  money, threshold, 2025 and override talk.
- 2025 Validation figures are filtered out of every graveyard view shown to models (82 of 809 lessons still carried
  them).
- The money digest is unchanged (`a3e2aa7c`). Backup `state/backups/pre-r10`.

**06:02Z, operator change** (no deploy): `claude.roles` adds `researcher`, so the bandit's top 12 families run
their research cycles on `claude-sonnet-5-5` (medium effort; line `claude.role_usd_day.researcher` $100; the
breaker and every failure fall back to the family's Sail profile). First Claude cycles at 06:02:43Z ($0.07) and
06:03:00Z ($0.04).

**05:52Z, R9: House release `20260929T055159Z-40163c0de3e9`** (main `31853932`; #417). The money digest is unchanged
(`a3e2aa7c`). Backup `state/backups/pre-r9`.

**05:51Z, gateway `ac2779ac`** (#417): the Claude route admits the House's custom tools and tool-loop turns (no
server tools, no forced tool choice); the price rows carry `geo {us: 1.1}`; overruns are counted in `/v1/health`.
`CLAUDE_USD` is still $200.

**05:29Z, gateway `8d80d2f7`** (#420): the owner added $100 to the Anthropic account (its balance then read
$140.54), so `CLAUDE_USD`, the funded total, is $200. The meter had $80.33 spent, which leaves $119.67 of room,
below the account's real balance. Operator change at the same time: `claude.usd_cap` 98 → 198 (the swarm's line
inside it, keeping $2 for the House's own calls). The owner also added $200 to Sail.

**04:53Z, operator change** (no deploy): every paid role on Claude, after R8. `claude.model`
`claude-sonnet-5-5`; `claude.roles` architect, audit, diagnostician, rewrite and review;
`claude.role_usd_day` rewrite $15 and review $5; `claude.role_model` the audit on `claude-opus-5-5`, so
the gate's two reads stay two different models; `gate.review_openai_model` and `gate.audit_openai_model`
null. With `architect.openai_model` already null, no role calls OpenAI.

**04:42Z, R8: House release `20260929T044127Z-2c265b03bc04`** (main `8074e262`; #414, #415, #416)

- #414: the graveyard is ranked by BM25 (a word's repeats saturate and long rows are discounted, so long
  lessons no longer crowd out short ones), and a new family is born with three distinct lessons.
- #415: Claude Sonnet 5.5 (`claude-sonnet-5-5`) priced in the House's hold ceilings.
- #416: Claude may also take the researcher's stall rewrite and the gate's program review (operator
  opt-in through `claude.roles`), with per-role daily lines (`claude.role_usd_day`) and per-role models
  (`claude.role_model`); the gate alerts `same_reader` when one model both reviews and audits.
- The money digest is unchanged (`a3e2aa7c`); the grant stays active. Promoted 04:42:07Z; the ten-minute
  watch passed (verdict 04:52:09Z); its files on the box match main `8074e262`.

**03:59Z, the gateway** (#415; version `7eaede72`): `claude-sonnet-5-5` added to `CLAUDE_MODELS` at its
list prices ($2 input, $2.50 five-minute cache write, $0.20 cache hit, $10 output per million tokens).
`CLAUDE_USD` unchanged at $100.

**00:17-04:00Z, operator changes** (no deploy)

- 00:17:28Z `live.house_test` on, after the test's analysis script was pinned. Its files read verified;
  no trade yet.
- 02:30Z agenda v14 (steering only: D2 and every kill test unchanged; the text stays private).
- 03:35Z operator lessons (`op-` ids) inserted into the graveyard, with a backup: 45 by 04:33Z.
- 03:40-04:00Z the owner's decisions (Claude Sonnet 5.5 throughout; only Sail and Claude topped up from
  now on; "remove any limits that would inhibit this goal"): `architect.openai_model` null (the architect
  is Claude-only), `architect.every_seconds` 600 with `max_refill` 24, `population.start` 96,
  `gym.max_boxes` 16, `researcher.sail_usd_per_hour` 12, `researcher.top_families` 12, the
  diagnostician at $60 a day, 6 a round, every 3 hours a family. The Sail guard's $32 line is unchanged.

**00:06Z, the site** (personal-site #16; version `dcd61fbc`): the positions table labels the House live
test's rows "House live test".

## 2026-09-28

**23:55Z, R7: House release `20260928T235447Z-6005f971ffc5`** (main `6c2de074`; #410, #412)

- #410: five 2020-21 stock splits in `events.SPLITS`. #412: the House live test
  (`league/live/house_test.py`, off by default).
- The money digest moved `ad9bd54c` → `a3e2aa7c`: only the test's own bounds
  (`options_money.house_test`), approved by the owner at 22:55Z. The grant was re-ratified at 23:56:41Z:
  active on `a3e2aa7c`, capital $1,473.11. Backup `state/backups/pre-r7`.
- Verified: `health.json` `options_live.house_test.files` verified; the positions table still adds up
  to Profit.

**22:20Z, the grant** (no deploy): re-ratified once the owner's deposit reached options buying power.
Capital $481.63 → $1,473.11, the lower of equity and the $5,500 ceiling; the digest unchanged.

**20:08Z, R6: House release `20260928T200729Z-5bdeb710c88b`** (main `2981566d`; #409)

- #409 carries #404 (payoff-range fills and marks), #406 (stock splits from a public table), #407 (the D3
  calibration's six hourly slots on SPY, QQQ and IWM with a 25-minute patient mid cell, the same $50
  bound) and #408 (the positions ledger; Profit includes calibration and the broker's fees).
- The money digest is unchanged (`ad9bd54c`). Verified: the positions table's rows add up to Profit.

**16:59Z, the site** (personal-site #15; version `d6e485c0`): the positions table under the chart, an
opt-in read (`GET /api/capital/checkpoint?progress=1&positions=1`).

**16:13Z, Train 2020-2024** (an operator image adoption, no deploy): the sealed 2020-24 Gym image and
`gym.train_from` "2020-01-02" in `swarm.json`; 38 families migrated, 0 failed.

**14:04Z, R5b: House release `20260928T140336Z-766c07a9691b`** (main `2e51ea71`; #405)

- The funding read left out WIRE, which Alpaca's activities filter refuses; the failed read had blocked
  every real entry at the open. The owner's exception to the trading-day freeze.
- The money digest is unchanged. Verified: at 14:06:41Z nothing blocked real entries; the first D3
  round trip followed at 14:08Z.

**06:58Z, R5: House release `20260928T065759Z-aae7108eda03`** (main `9fe54351`; #399): the Train 2020-21
code with the switch off. Verified: the pre-open checks 9/9, no span alerts.

**06:16Z, R4: House release `20260928T061526Z-971da2b2e678`** (main `7effc585`; #403, which carries #401
Gym memory, #402 the hold backoff and the idle pass, and #398 the drift screen). The money digest is
unchanged. Verified: 0 cycle errors after the restart; the pre-open checks 9/9.

**02:56Z, R3: House release `20260928T025520Z-8d5e8eec714a`** (main `e4c9fe5a`; #394, #397): mirror and
backup-box fixes, `gym_sweep`, the idle rule, stored results for identical runs, holds and the dormancy
clause, and the operator's gate hold. The money digest is unchanged (`ad9bd54c`). Sail could not
checkpoint (503), so a SQLite backup is at `state/backups/pre-r3/`.

## 2026-09-27

**13:49Z, the site** (personal-site #14; version `84fedf26`): the balance chart starts after the owner's
deposit.

**01:00Z, the refitted Gym and gate images** (no deploy): fitted on Train `trade_quote` samples only with
#387's estimator, adopted in `swarm.json`; the House restarted at 01:01-01:02Z so the Gym, the gate and
the live shadow share one fill model.

**00:30Z, R2: House release `20260927T002925Z-2bfef7a749bf`** (main `440f6de4`; #387, #390, #391, #392)

- #387 the honest fill model; #390 the live path for Monday (the observe band, long calls and puts as
  real types, the D3 calibration, the D4 money table); #391 Claude streaming; #392 `real_money` true.
- The money digest moved to `ad9bd54c`. The grant `options-swarm-20260928` was enabled at 00:30:15Z,
  capital $481.63. 00:31Z `live.observe` on (at most 8) and `live.calibration` on.
- Verified: the ten-minute watch passed (00:40Z).

## 2026-09-26: the options overhaul and the sprint's first release

**23:41Z, the gateway** (#391; version `953a9b46`): Claude streaming. A probe settled at $0.001.

**23:18Z, the gateway** (#390; version `9634002d`): `OPTION_STRUCTURES_REAL` the four debit types
(`debit_vertical,long_butterfly,long_call,long_put`) and `MAX_ORDER_EQUITY_SHARE` 0.25.

**23:00Z, R1: House release `20260926T225946Z-22b18ea9f452`** (main `5ba25909`; #378, #379, #380, #382,
#383, #386, #388, #389): the Claude route's House side (Claude-first architect and audit, the
diagnostician), the robust Train objective and D2. The money digest is unchanged (`8dba0b1f`). Verified:
the migration re-picked 34 families' bests with 0 errors; the diagnostician's first Claude calls.

**22:37Z, the gateway** (#388, main `13963028`; version `42e443bb`): the Claude route and its funded
meter, `CLAUDE_USD` 100. A probe call settled at $0.001.

**22:10Z, the site** (personal-site #13; version `5ce5265c`): progress checklists accept the D2 line.

**21:24Z, the sprint's Wave 0** (no deploy): `swarm.json` settings (population floor 44, the
architect's refill, retirement at 200 revisions or 4,000 evaluations), a calibrated Gym image and the
gate on its paired gate image.

**20:57Z, the gateway** (version `cd0588b5`): a secret change, no code (Cloudflare's source "Secret
Change"): `CLAUDE_API_KEY` was added, the owner's D7. Not in the run record.

**18:18Z, House release `20260926T181814Z-b4bc25619f84`** (main `60b34dd9`; #377, the publisher's agent
progress). The site's #11 (18:05Z, `7959f35b`) and #12 (18:16Z, `e473bcbc`) went first.

**17:56Z, House release `20260926T175520Z-f47c08cd0535`** (main `8c9216b6`; #376, researcher retirement).

**17:26Z, House release `20260926T172613Z-f62e2af878bb`** (main `7645e202`; #372, #373, #374: the Sail
research pace, the paper route's readiness, the researcher protocol).

**16:50Z, House release `20260926T164943Z-04457584301d`** (main `4472c334`; #362 the live path, #371)
and **16:49Z, the gateway** (version `20a6b706`, `OPTION_STRUCTURES_REAL` off). The money digest moved to
`8dba0b1f`; no grant was enabled. The site's #10 went first (16:42Z, `2506e646`).

**16:11Z, House release `20260926T161049Z-6a9300a67fbb`** (main `570f023c`; #365-#370).

**15:52Z, the gateway** (#368, main `647c8384`; version `e602bdb4`): the OpenAI September cap $707.

**10:55Z, House release `20260926T105515Z-b25acc7981e2`** (main `e6a020dd`; #363, the swarm's loop).

**10:22Z, House release `20260926T102142Z-e71ed057c625`** (main `310225ae`; #361, #364). The new House
started at 10:22:29Z; the swarm founded 48 families.

**08:53Z, the gateway** (#361, main `3f660144`; version `8054eecb`): `SAILBOX_ID` the new House box.

**08:49Z, the first House release on the new state root: `20260926T084913Z-8158a11cfe3f`** (main
`b68b3800`; `real_money` false). Promoted with the loop stopped. It is the rollback floor.

### Before the first House release

**Merged, not yet deployed to the House**

- 06:39:40Z #356, the plan (`docs/goals/LTCM_OPTIONS_SWARM.md`); main `46ec3433`.
- 07:21:04Z #357, the publisher's schema 2 for the options site; main `d1855afc`.
- 07:49:22Z #359, the House options-only (Wave 2a): `auto_update` false and a missing key means off;
  `floor_box.py` and `gateway_admin.py` off the legacy package; the grant `options-swarm-20260928`
  in `league/live_trading.py` with every real-money call site asking it; no Kalshi, Jev, lab,
  foundry, semantic lab, feed, campaign or pacer piece in the service or the tick; the config's dead
  keys removed; CI runs the Gym's dependencies; Merton never auto-merges. `real_money` false. Main
  `6c715d83`.
- Open: #358, the Gym (`league/gym/`), under review.

**07:21Z, the site** (`~/Work/personal-site` PR #9, schema 2; Worker version `650a8ac1`)

- Deployed, then reset with `/api/capital/reset?confirm=erase-everything` on the real record and the
  `test` and `canary` tapes. The real record's 20,000 events, 1,604 history points, 1 checkpoint and
  136 desks were cleared.
- The reset pair: `PERFORMANCE_START_AT` 2026-09-26T06:25:30.000Z, start equity $481.65, the same as
  `performance` in `league/config.json`.
- Verified: all three checkpoint routes answer 404 until the new House publishes; the page reads "AI
  agents trading options." and its HTML names no venue (re-checked read-only at 07:54Z).

**06:24-06:58Z, the old House stopped and archived** (Wave 0; no deploy)

- 06:24:56Z the old House stopped (`floor_box.py stop --reason "options overhaul"`) on release
  `20260926T032739Z-aaf5ac74637c` (Deploy G, main `a1f9a8e7`), paused for maintenance since
  03:55:56Z: 128 agents alive in 121 families, 627 dead.
- 06:25:00Z the old grant `earned-live-20260921` disabled.
- 06:25:30Z the Brokerage Account's leftovers closed: two resting crypto sells cancelled, SOL and XRP
  sold; equity $481.65, with $0.03 of LTC dust kept as a legacy holding outside P&L.
- 06:33Z git archive: tag `archive/pre-options-2026-09-26` at `89bc49a1`, 78 branch tags
  `archive/branch/<name>`, laptop-only branches bundled on the owner's machine; 14 open pull requests
  closed with a comment naming their tag.
- 06:36Z the old state moved aside to `/workspace/archive/state-pre-options-20260926` on the House
  box and a fresh, empty `/workspace/state` made; 06:54Z its tarball written (8,256,763,269 bytes,
  sha256 `e9e5c04482a3321707902dd376a9902fe260954cd76cbe204eec89be6a16256f`, `gzip -t` OK). Two
  checkpoints of the House box failed (Sail 503, 06:35Z and 07:00Z).
- 06:37-06:39Z 420 old Sail boxes terminated (agent sandboxes, lab and foundry boxes, canaries).
