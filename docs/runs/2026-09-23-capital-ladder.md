# Capital is the ladder — September 23, 2026

Execution record for the owner's goal of Sept 23, 2026: execute
[the north-star build plan](../goals/LTCM_NORTH_STAR_BUILD.md) autonomously for eight hours.

## The clock

- **T0:** 2026-09-23T06:30:58Z (the first action of the session, `date -u`).
- **Deadline:** 2026-09-23T14:30:58Z (T0 + 8 h). A context reset does not restart the clock.
- **The watch starts no later than:** 2026-09-23T13:00:58Z (the final 90 minutes).
- **Morning report:** at the deadline, in this file and in the session.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 and deadline recorded and committed | done |
| 0.2 | Baseline snapshot (release, grant, digest, population, live agents, fills, budget lines, foundry) | done (below) |
| 0.3 | Alpaca live crypto check (`crypto_status`) | done: ACTIVE, crypto ACTIVE, $500 cash |
| 0.4 | Compute aligned to funded balances (OpenAI, Sail, Jev) | done: PR #157, gateway `c6c507ad`, House top-up |
| 0.5 | `scripts/floor_watch.py` | done (in PR #163) |
| 0.6 | Builders B, C, D, E spawned in their own worktrees | done 07:05Z |
| A | The allocator: evidence as wealth, bands, stakes, death, performance fee | live: PR #163, release `20260923T082402Z-7c69b3eb57f0` |
| B | The capital board (publisher + site) | live: site #4 (`5772ac0c`, 06:54Z), House #162 in release `20260923T090513Z-7009e67356f0` |
| C | Exit splitting and stake-scaled positions | live: #164 + #168 in release `20260923T090513Z-7009e67356f0` |
| D | The Alpha Lab (box, batch evaluator, evolution, graduation, royalties, tools) | live: #170 (supersedes #167, #160) in release `20260923T104142Z-5d86b468fbde`; lab box `sb_742fe765` |
| E | Profit-indexed compute and envelope; a tick that never blocks | live: E2 in A; E3 + E1 (House) in #170; E1 gateway `3eef1b8a` |
| F | Open desks (stretch) | live: #171 (`kalshi-open`, `alpaca-open`, 8 seats each) in release `20260923T104142Z-5d86b468fbde` |
| Deploy 1 | A (B's publisher follows through the updater; C in Deploy 2), ratified at promotion | done 08:27:54Z, ratified 08:28:13Z |
| Deploy 2 | B + C (+ #168: positions follow stakes) | done 09:09:29Z (no money rule changed; no ratify) |
| Deploys 3-6 | E3 + E1 + D + F; #173/#174; #176; #178 | done 10:43Z, 11:17Z, 12:07Z, 12:34Z (no money rule changed) |
| Watch | ≥ 90 minutes, every 15 minutes through `scripts/floor_watch.py` | done: 12:08Z to the deadline, plus a floor-events monitor. Found and fixed: the auditor's context (#176), lab tape order (#178), the watch's labels (#179), Kalshi shard 3 funding |
| Docs | README, operations, runbook, league README, CONTRACT, gateway README, DESIGN.md, rules, playbook | done: #175 and #179; the rules and playbook in #163 |
| Cleanup | this build's worktrees and branches removed once merged | done at the deadline (see the report) |
| Memory | project memory + MEMORY.md line | done: `ltcm-capital-ladder-2026-09-23.md` |
| Report | morning report at the deadline | done: below |

## Baseline (T0, 06:30Z)

- **Release** `main-f45606af3205` (the updater's), health 44.98 s tick, nothing stopped.
- **Grant** `earned-live-20260921` active on money digest `a6b83f9e` (constitution `64a206c6`): Kalshi $517.75, Alpaca $500, 16 agents.
- **Population** 96 living / 335 dead: Alpaca paper 48, Kalshi paper 45, Kalshi rung 2: 3 (mullins-2 $61.29, mullins-6 $60.50, hawkins-19 $59.47 on $60 stakes each). The Alpaca real account has never traded.
- **Last hour** (05:30-06:30Z): fills alpaca-paper 14 ($538 notional), kalshi-shadow 19 ($253); real: 1 Kalshi order rejected, 3 cancelled, no real fill. Refusals: 24 "market orders outside regular hours", 6 below Alpaca's $10 crypto minimum.
- **Replay** in the hour: Alpaca 23 passed / 6 failed (15 of the passes through the out-of-sample floor), Kalshi 5 / 4. Promotions 0→1: haghani-53, haghani-54, scholes-28. Births 13 (12 foundry cards), deaths 12 (10 displaced, 2 redundant: holdout rationed).
- **Budget**: House OpenAI line $65.88, Sail $100.66; gateway OpenAI month $308.46 of $374; Jev $16.14 of $20; Sail balance $102.26 at $30.8/day (runway 3.0 days). 44 pending calls.
- **Foundry**: 108 cards (33 passed, 73 failed, 2 data-blocked), 8 waiting for seats, $8.48 of its $40 window spent.
- **Defect found at T0**: the site had refused every checkpoint since about 05:30Z (`HTTP 400 Invalid checkpoint`, 63 alerts in the hour): 96 living + 8 dead = 104 desk rows against the site's `MAX_DESKS` 100. Fixed twice over: PR #156 (publisher bounds the roster to 100; merged 06:39Z, updater-deployable) and the site's `MAX_DESKS` 160 (site PR #4, builder B). Publishing resumed by 07:13Z.

## Compute aligned to funded balances (Phase 0.4, 07:14Z)

| Line | Before | After | How |
|---|---|---|---|
| OpenAI gateway month | $374 cap, $308.46 metered | **$408** (metered + owner-funded ~$100, rounded down) | PR #157, gateway version `c6c507ad` |
| Jev (TypeSafe) | $20 cap, $16.14 metered | **$42** (metered + $26 funded) | same deploy |
| OpenAI House line | $58.61 left | **$85.91** left | `campaign_topup.py --id topup-20260923-capital-ladder-funded --openai 28` (matches the gateway's ~$87 remaining) |
| Sail | $101.84 balance, $28.9/day | unchanged (prepaid; auto-recharge is the owner's decision) | — |

## Log

- 06:30:58Z — T0. Plan read from `origin/main` (`daebfbe`, PR #155). Worktree `~/Work/ltcm-ladder`,
  branch `night/capital-ladder`.
- 06:34Z — PR #156 (site roster ≤ 100) opened; merged 06:39Z.
- 06:40Z — PR #157 (funded caps) opened; merged and gateway deployed 07:14Z (`c6c507ad`); House top-up +$28.
- 06:45Z — measured the evidence distribution on the live ledger: only the three live Kalshi agents have E ≥ 1.01; the best paper agent 1.0094.
- 07:05Z — builders launched as background workflows (build → adversarial review → fix): B board (`ltcm-board` + `personal-site-board`), C exits (`ltcm-exits`), D-core (`ltcm-labcore`), D-evo (`ltcm-labevo`), E (`ltcm-noblock`).
- 07:17Z — PR #163 (Workstream A, the allocator) opened; an adversarial three-lens review workflow launched on it.
  - Dry run on a copy of the live ledger: 96 agents' evidence in 1.0 s.
  - Alpaca bunt $25, not $15: the book's 50%-of-equity order rule and Alpaca's $10 crypto minimum make a $15 bunt untradeable (found by `test_allocator`'s end-to-end test).
  - `bunt_at` 1.01, not 1.03: no paper agent was near 1.03, and 1.03 would have seated nobody for days. Both changes are inside the plan's bounds.
- 07:25-07:50Z — **Adversarial review of #163** (three lenses: money path, evidence honesty,
  lifecycle; each finding checked by a skeptic that tried to refute it). Every defect below was
  reproduced by script, and each now has a regression test. Fixes are on #163:
  1. **Evidence depended on the rung.** A demoted bunt's unfinished real loss disappeared on paper,
     so it was re-bunted every other pass (12 flips in 30 minutes). Now both records are read in
     full at every rung.
  2. **Real drawdown was lifetime.** A demoted agent re-bunted and flipped forever. The drawdown is
     now the current real stay's, and any demotion starts a 1-hour re-entry cooldown
     (`allocator.reentry_cooldown_hours`).
  3. **A re-seated account's new stay was invisible** (`_unfinished_growth` returned 0 after a
     zero-equity block) and its losses were refilled. A re-seated account now grows from what was
     lent.
  4. **An account marked before it was funded** took the net of stakes and withdrawals as its
     start, which inflated E or read as ruin. Now it grows from what was lent, and only withdrawals
     are flows (`observe`, `wealth`, `_unfinished_growth`).
  5. **The envelope counted a seated account's net loan.** Returned profit counted twice, and a
     star's stake could drop out of it. It is now grant + realized − what every account can still
     lose.
  6. **Unfunded seats counted $0**, so one pass could promote every eligible agent. Pending seats
     are now reserved, and the allocator checks the venue can fund a stake before promoting. A
     failed stake sends the agent straight back. `seat()` lends a real stake only with envelope
     room, and a known-defect bunt committed after its audit checks the allocator's envelope.
  7. **The swing audit's packet was empty** (no `book` on the verdict). It now reads the real record
     (the paper record for a known-defect bunt).
  8. **A drifting swing was liquidated and re-swung in the same tick.** Drift from swing to bunt now
     only re-seats, and the cooldown blocks the re-swing.
  9. **Any past approval skipped the swing audit**, even after a veto or new code. Now only the
     latest real verdict on the current code counts, and a veto's cooldown holds a bunt for every
     agent.
  10. **Trade counts vanished once the net stake was ≤ 0**, and settlements before an evidence
      cutoff counted. `closed_trades` fixes both.
  11. **The haircut was 0 after a cutoff** and diluted across stays. It is now charged per stay.
  12. **A throttled Alpaca bunt could not trade** (half of $12.50 is under the $10 minimum). The
      throttle now stops at the smallest stake that can trade.
  13. **judge and the allocator alternated `progress` rows** every pass. Only the allocator writes
      statuses now.
  14. **Positions are capped at $60 until exit slicing (C) lands** (`EXITS_SLICED`), so one $75
      order can always close one.


- 08:12Z — #163 merged (`a653291`) after CI passed on the review fixes (including `test_ladder`,
  which times out locally under this machine's load).
- 08:23:50Z — **Deploy 1** (A only; B was still in its review-fix phase and its publisher is not a
  protected file, so the updater can ship it).
  - Release `20260923T082402Z-7c69b3eb57f0` promoted at 08:27:54Z.
  - Grant `earned-live-20260921` ratified at 08:28:13Z (19 s later) on money digest `44e8d48d`
    (constitution `9fa83727`): the same capital, max agents 16 → 101, stake line $10.
  - First full tick 08:29:14Z (76.6 s). The first allocator pass came at 08:30:03Z:
    - The three legacy $60 Kalshi stakes shrank toward $10 by free cash only (−$3.89, −$3.26,
      −$2.60); their positions are held.
    - **haghani-37 is on real money at Alpaca.** The old screen had promoted it at 08:06:22Z,
      before the deploy, and the allocator made it a $25 bunt, returning $31.21 of free cash. Its
      first real Alpaca order, a resting XRP limit buy of $28.79 placed at 08:15:54Z under the old
      micro limits, is accepted and unfilled.
    - Envelope in use: Kalshi $175.54 of $517.75, Alpaca $28.79 of $500. Throttle off; floor real
      P&L −$2.64.
  - The site kept publishing: the 08:31Z checkpoint had 100 desks (the #156 roster bound is in
    this release).
- 08:40-09:03Z — builders finished (each with an adversarial review and a fix pass):
  - D-evo #160: 3 majors fixed (graduates' trial counts, idempotent births, submission starvation).
  - C #164: 1 major fixed (the gateway prices an Alpaca market order at ask × 1.10, so an entry
    of $68.19-$75 at the ask was a 403; the book now counts orders as the gateway does).
  - D-core #167: no major; lab box `sb_742fe765` (8 vCPU, sealed) measured 11.1/s (Kalshi),
    3.2/s (sports), 1.7/s (crypto) against about 0.02/s for the old path; batch equals the House's
    recorded results in 13/13.
  - B #162: 1 major fixed (reasons cut in UTF-16 units, as the site counts them; an emoji had
    been able to get a checkpoint refused), and the allocator's empty pre-pass board falls back to rung bands.
  - E #159/#166: 1 major fixed (a research admission held the lifecycle lock across a Sail fork).
- 09:04Z — #162 (board publisher) merged; #164 (exit slices) merged 08:57Z; #168 (positions follow
  stakes, Alpaca orders ≤ $68.18 = $75 / 1.10) merged 09:05Z.
- 09:05:12Z — **Deploy 2**, release `20260923T090513Z-7009e67356f0`, promoted 09:09:29Z. No money
  rule changed (digest `44e8d48d`), so the grant stayed active. The 09:15Z checkpoint on
  blakewoods.us carries the board (`enabled: true`, bands per venue, 50 moves) and every desk's
  band, stake and evidence.
- 09:10Z — Deploy 3 integration workflow launched (worktree `ltcm-labint`, branch
  `night/lab-integration`): E3 + E1 + D-core + D-evo onto main, the two conflicts (sandbox.py E3 vs
  D-core, house.py E3 vs D-evo), D-core's minors, and the lab's birth taking the probe box before
  the lifecycle lock.
- 09:10-10:23Z — **Deploy 3 integration** (#170): E3 (#159), E1 (#166), D-core (#167) and D-evo (#160)
  merged onto main, with both conflicts resolved (`sandbox.py`: the lab box's batch goes through
  E3's `_turn`, patience and `SandboxBusy`; `house.py`: the lab's tick sits in E3's `_tick`).
  - Integration fixes:
    - a corrupt gzip tape reads as missing;
    - a failed fork is infrastructure;
    - a terminated lab box raises `BoundBoxGone` instead of leaking a replacement;
    - `Lab._birth` makes no Sail call under the lifecycle lock;
    - the service binds `config.json` `lab.box_id`.
  - The integration review found one major: the lab spent a living line's holdout budget. The
    lab now leaves a living line its last evaluation (`holdout_reserve` 1).
  - I added two more:
    - the gateway's `/v1/health` no longer reads both venues inline, because the House reads its
      kill switch there and treats a slow answer as engaged;
    - the lab stops with the Sail meter, and a graduate waiting for a seat is re-ranked at most
      every 10 minutes.
  - 88 modules and 2,257 tests green; CI green on the PR head.
- 10:30Z — #170 merged (`bf202d4`); F #171 (open desks) merged (`3ae144c`; its review found no
  major).
- 10:41:41Z — **Deploy 3** (main `3ae144c`: E3 + E1 + the Alpha Lab + open desks). Release
  `20260923T104142Z-5d86b468fbde` promoted at 10:43:05Z. Money digest unchanged (`44e8d48d`), so
  no ratify was needed.
- 10:42Z — **gateway `3eef1b8a`**: E1's profit-indexed OpenAI cap (`COMPUTE_PROFIT_SHARE` 0.3 over
  the $1,017.75 baseline, ceiling `FRONTIER_MONTH_MAX_USD` = the funded $408, so it measures profit
  and reports it but buys no compute above funded money) and the health fix. `/v1/health` answered
  in 0.23 s.
- 10:46Z — the lab started: 212 seeds queued. The first batch (10:51Z) evaluated 2 candidates at
  0.33 per box-second. Early batches are tape-bound: each seed carries its own NEEDS, so its own
  tape, and the lab builds 4 tapes a step on the House box and keeps 6.
- 10:53:26Z — Deploy 3's watchdog watch passed (exit 0). The in-box updater later picked up
  Merton's #172 (a new strategy file).
- 10:55-11:10Z — **Diagnosing slow ticks and a slow lab on the live floor** (py-spy on the House):
  - Ticks went 70 → 88 → 109 → 191 s. About 80% of the tick thread was in `House.standings()`:
    displacement, the refill and the foundry each re-ranked all 96 agents with several ledger
    scans apiece. That is not the lab. **PR #173:** one standings table per tick.
  - The lab evaluated 21 candidates in 11 minutes, 1-6 a batch. 191 seeds were queued, each on its
    own tape (4 tapes are built a step), and the step bred only when fewer than a batch were queued
    at all, so the elites whose tapes were built got no children. **Same PR:** the lab breeds while
    fewer than a batch wait on built tapes, with 48 parameter children a breed (was 16).
  - **The best paper agent was blocked by an audit veto over a label.** huang-h6d3302 (E 1.037,
    W_paper 1.075, 13 settlements; above the 1.01 bunt line) had a stale "barren" pre-audit flag,
    so it was audited before its bunt. At 09:32Z the auditor vetoed it for "unexplained zero-fee
    taker executions". Five of its 14 fills were resting Kalshi limit orders that filled later and
    paid the maker's fee ($0), but `Book._liquidity` labels every non-post-only limit as a taker.
    The money was right and the label was wrong. **PR #174** fixes the label (with a test that
    fails without the fix). The veto's cooldown (about 22 h) stands: it was a real audit and is
    not overridden.
- 11:16:06Z — **Deploy 4** (#173 standings once a tick + lab breeding; #174 maker label), release
  `20260923T111607Z-5b863ec3725f`, promoted at 11:17:36Z. Ticks went from 109-191 s to 50-90 s
  (sampled 11:22-11:32Z).
- 11:26:20Z — **the first real Alpaca fill of the build**: haghani-37 (a $25 bunt) bought 0.1923 LTC
  at $62.39 ($12.00), inside its $12.50 position cap. Kalshi real fills since Deploy 1: 2 ($17.78).
- 11:35-11:50Z — two more findings:
  - **Lab batches were still one candidate**, because seeds with a tape each sat ahead of the
    children by priority: 60 evaluated in an hour, 543 queued. Fix: batches alternate between
    queue order and the largest ready group.
  - **The audits the allocator asked for were judged against the wrong rules.** Its verdicts
    carried no `allocation_context`, so the auditor read the legacy $50 / 4-agent tuition and a
    $60 stake and vetoed both top paper agents on capacity. (huang-h51fdd3-2 at 10:06Z:
    "promotion_context limits tuition to four agents and $50 aggregate loss ...
    allocation_context is null".) Fix: `Allocator.context` sends the stake, limits, envelope,
    headroom and grant; the auditor's purpose, limits and prompt describe a bunt or first swing;
    and the allocator rules join the audit policy digest, so the stale vetoes get the short
    reconsideration cooldown the digest exists for. Both fixes are in PR #176.
- No band moves happened between Deploy 1 and 11:50Z. The two paper agents over the bunt line
  (huang-h6d3302 E 1.037, huang-h51fdd3-2 E 1.026) were both held by those vetoes; every other paper
  agent was below E 1.01.
- 12:05:52Z — **Deploy 5** (#176: lab batches alternate; audits under the allocator see its envelope),
  release `20260923T120553Z-1fb264401995`, promoted at 12:07:20Z. No money rule changed (`44e8d48d`).
  - The 3.11 CI job hung twice at the same point in the league suite on GitHub's runner, and was
    cancelled at the 10-minute job limit. Neither hang reproduced: this branch's `test_lab`,
    `test_auditor`, `test_episodes`, `test_economy` and `test_evaluator`, and then the first 300
    league tests in one process, all passed under Python 3.11 on the House box. The 3.14 job
    passed, and main and the docs PR passed on 3.11. It went out through the watchdog's canary
    with a CI rerun in the background.
- 12:05Z — docs PR #175 merged (README, operations, runbook, league README, CONTRACT, gateway README;
  a verifier checked every added claim against the code and corrected four).

## The watch (from 12:08Z)

Every 15 minutes `scripts/floor_watch.py` appends to the session log (the loop has run since
09:17Z). The entries below are what changed, what broke and what was fixed.
- 12:04:29Z — huang-h6d3302 (the agent the zero-fee label veto held) died, displaced by the refill.
  Its paper wealth had fallen from 1.075 to 0.941 over its last settlements (E 0.970): the auditor's
  doubt about its short, concentrated record was borne out.
- **12:10:19Z — the first allocator bunt.** Under the corrected audit policy, huang-h51fdd3-2 was
  re-audited after the short cooldown for a revised policy digest, and this time the auditor approved:
  "The supplied accounting and execution evidence supports the allocator's bounded $10 bunt, with no
  identified blocker". The allocator then promoted it paper → bunt (E 1.0257, W_paper 1.052,
  4 settlements; a $10 stake at Kalshi).
- 12:11:51Z — its first real trade: bought 2 KXDOGE15M-26SEP230815 at $0.76.
- 12:21Z — watch:
  - The new bunt's first real trade (2 KXDOGE15M at $0.76) settled at a $1.52 loss, 15% of its $10
    stake. The book's existing per-desk rule ("desk daily loss 13.2% reached limit 10%; only
    risk-reducing orders allowed") now holds it out of new entries for the day. Its E (about
    0.87) is still above the allocator's 0.8585 exit line.
  - This is a real interaction: a 10% daily-loss rule on a $10 stake freezes a bunt after one
    small loss, before the allocator's own demotion lines can act. It is left unchanged. Loosening
    a real-money risk rule is the owner's call (see "Decisions for the owner").
  - Lab: after the 12:08Z restart only seeds and submissions were evaluated (104 in all; 0 of the
    500 children).
- 12:32:29Z — **Deploy 6** (#178): on the largest-group turn the lab builds the biggest waiting
  groups' tapes first. After a restart the step's tape budget had gone, in queue order, to seeds
  that each need their own tape, so the children's tapes were never built. Release
  `20260923T123231Z-4c6c96522a1c`, promoted at 12:34:00Z. CI was green on both 3.11 and 3.14, which
  supports reading the earlier 3.11 hangs on #176 as runner flakiness.
- 12:44-12:53Z — **the lab at scale.** After Deploy 6 the children's tapes were built: 196 parameter
  children in about 10 minutes, in batches of 32 (a 10-minute rate of about 1,200 an hour). In total:
  119 seeds, 8 agent submissions and 196 children evaluated; 21 archive cells.
- 12:46:39Z — **the first lab graduate candidate.** A lab-made program for `kalshi-crypto-15m` passed
  the House's own replay (a counted trial on its own line). It is `waiting_seat`: the league is at 96
  and no resident is displaceable. It is asked again every 10 minutes.
- **12:50:25Z — the second allocator bunt**, and the first through the pure allocator path (no audit):
  meriwether-h2d625d, paper → bunt, a $10 stake at Kalshi, E 1.0100 on 7 closed paper trades.

- 12:54:00Z — the lab's `alpaca-index-etfs` elite was `holdout_rationed`: its lineage
  (agent:scholes-21) had spent its 3 sealed-holdout evaluations. It joins agent:mcentee-31
  (`alpaca-megacaps`, 11:29:48Z). Rationing is the plan's D4 rule, working as written.
- 12:56Z — **why the graduate waits.** `Lab._seat_for` asks `House._weakest` for a resident to
  displace, the same rule the House's own births use. The league is at its 96 cap (6 bunts,
  90 on paper). Of the 90 on paper, 39 are below W_paper 1 and 61 have never traded, yet
  `_weakest` found none it may displace. Each one is still inside a grace the rule guarantees:
  - completed research passes (rung 0);
  - a first offered market opportunity (equity agents seated overnight);
  - a daily agent's pending screen.

  Those graces exist because of the Sept 20-22 deaths recorded in the code. Three residents
  were displaced since T0, all to House births. Shortening a grace to seat the lab's program
  would buy a move with the rule the evidence set, so it is left alone. The graduate is asked
  again every 10 minutes.
- 12:57Z — **`scripts/floor_watch.py` counted practice as real money.** Its "real money" line
  summed every book with venue fills, including the practice books `alpaca-paper` and
  `kalshi-shadow`. Fixed on this branch: only `kalshi` and `alpaca` are real, and practice gets
  its own line. Since T0, real money is:
  - **Kalshi:** 3 fills, $19.30 notional, −$1.52 realized (huang-h51fdd3-2's DOGE 15-minute contract).
  - **Alpaca:** 1 fill (haghani-37 bought $12.00 of LTC/USD at 11:26:20Z), still open.

  Practice since T0: alpaca-paper 100 fills ($3,148, +$0.99 realized); kalshi-shadow 69 fills
  ($759, −$108.66 realized).
- **Lab throughput, measured at 12:57Z.** The first evaluation was at 10:51:07Z.
  - **The first hour evaluated 87 candidates**, against the plan's 1,000. The batch evaluator
    was never the limit: 109 batches took 577 s of lab-box time and $0.03 of Sail. Two things
    held it back:
    - until #176 every batch was a single seed waiting for its own tape;
    - the House box (1 vCPU) builds only 4 tapes a step, and every restart empties the tape cache.
  - **Hour 12 evaluated 324.** Since Deploy 6 it has run at about 200 per 10 minutes.
  - **Totals:** 423 evaluated (123 seeds, 292 parameter children, 8 agent submissions), 0 errors.
    335 were eligible (79%) and 279 cleared the replay gate (66%). The archive holds 22 cells
    across 9 desks.
  - **Graduation, per stage:** 3 elites were put forward. 2 were refused a sealed-holdout run,
    because their lineages had spent their ration. 1 passed the House's replay, and is now
    `waiting_seat`.
- **12:59:39Z — the first Alpha Lab graduate was born.** 13 minutes after `waiting_seat`, a
  resident became displaceable: hufschmid-33 (rung 1, `kalshi-sports-props`, generation 3), which
  had run out its grace. The lab's retry took the seat.
  - huang-l23cdb7 was born with founder `lab:agent:huang-h6d3302`: the lab's search, seeded
    from the program of the agent that died at 12:04Z.
  - Its program is candidate `23cdb791b32a`, a KXETH15M prior-window fade on 5-minute ETH bars.
  - Seat verdict: "an Alpha Lab graduate: candidate 23cdb791b32a29111d5208fe passed the House's
    replay before birth, on its own line". Rung 1, a $200 kalshi-shadow practice stake, $8
    endowment. It woke at 13:00:20Z.

  **This meets D's acceptance line: a graduate born on practice.** Two more events followed:
  - 12:59:40Z — a third lineage was rationed (agent:mcentee-30, `alpaca-megacaps`).
  - 13:00:48Z — a second `kalshi-crypto-15m` candidate passed the House replay. It now waits
    because that desk is full.
- 13:05Z — **the stretch and slicing workstreams, as they stand on the running release.**
  - **F: the open desks have no members yet.** `kalshi-open` is live, with the survey's series
    joined at 10:46Z. A program is seated there only when `niches.match` finds it spans desks or
    names markets no desk lists. Of the 4 births since Deploy 3 (3 House, 1 lab), each fitted one
    desk. The lab's archive cells are per desk, so the lab does not seed open-desk programs itself.
  - **C: sliced exits have not been needed on a venue.** The largest real stake is $56.70
    (mullins-6). A position is capped at half its stake, so no position has come near an order
    cap. The caps are $75 at Kalshi, and $68.18 at Alpaca (the $75 cap over the gateway's 1.10
    ask markup). Slicing starts to matter for stakes above about $136 at Alpaca and $150 at
    Kalshi, which only a swing can reach. No agent has swung: none has 8 real trades yet.
- 13:06:37Z — **E1 read on the live gateway.** `floor_watch` had asked for field names the gateway
  never sends, so it showed `null`; it now reads `base_cap_usd` and `profit_index`. Equity is
  $1,016.00 (Kalshi $516.10, Alpaca $499.90) against the $1,017.75 baseline, with `read_ok` true.
  Profit is $0, so the bonus is $0 ("no profit above the baseline"), and the cap is the funded
  $408 with $351.54 spent this month.
- 13:10:18Z — a third lab candidate passed the House replay, for `kalshi-sports`. It is waiting for
  a seat: that desk is full.
- 13:11Z — **the House's teacher disagreed with the lab.** Merton (teacher) merged #181, a playbook
  lesson: pause parameter-only forks of the ETH prior-window fade until its forward losses are
  explained. The evidence behind it:
  - huang-h6d3302 passed replay, then logged −0.0603 total forward log growth;
  - huang-h6d3302-2 has −0.0498 over 9 blocks;
  - huang-h609d6f has −0.0589 over 11 blocks.

  The lab's first graduate, huang-l23cdb7, is such a fork: a parameter child from that lineage's
  archive cell. The lab's gate (the House replay on its own line, plus the sealed holdout) does
  not consult a lineage's forward record. The plan leaves that to practice, where the
  allocator's evidence takes over and death comes at W_paper < 0.8 after 10 trades. Nothing was
  changed: the graduate trades practice money only, and whether its fork holds up is exactly
  what practice will show. It is recorded as a design question for the lab (see the report).
- 13:15:37Z — PR #179 (this record, the `floor_watch` fixes, README Deploys 4-6, operations)
  merged as `8e5c22a`, after CI passed on 3.11 and 3.14. Main also carries Merton's #180
  (a Haghani-40 child strategy) and #181, which the in-box updater will ship as usual.
- 13:30:05Z — **a real-money blocker at Kalshi: exchange shards.** The new sports bunt
  meriwether-h2d625d placed its first real order: buy 5 NO on KXMLBTOTAL-26SEP231840STLPIT-8
  at $0.54 ($2.70). Kalshi rejected it with HTTP 404 `insufficient_shard_balance` ("Exchange user
  not found ... Exchange Sharding"), as it had its 12:58:27Z order.
  - **Cause.** Kalshi now runs markets on several exchange shards. Crypto and commodities are
    on shard 2, and since August 24, 2026 new baseball and tennis events are on shard 3 (basketball
    since September 10). An order fails unless its shard holds collateral.
  - **Cash per shard,** read through the gateway at 13:39Z (`GET /portfolio/balance`
    `balance_breakdown`, read-only): shard 0 $331.51, shard 1 $0, shard 2 $39.14, shard 3 $0.
  - **Events per shard:** KXMLBTOTAL, KXMLBGAME, KXWNBAGAME and KXATPMATCH open events are
    all on shard 3; KXNFLGAME is on shard 0. Every accepted real Kalshi order in the ledger is on
    a funded shard: weather, WTI, gold and the 15-minute crypto series.
  - **Why the League never funds shard 3.** The first run's service (`ltcm/service.py`
    `_fund_kalshi_shards`) topped up shards 0 and 2 hourly, and the gateway allows exactly
    this one funds move (`POST /portfolio/intra_exchange_instance_transfer`, money between
    shards of the owner's own account). The League has no shard code at all (nothing under
    `league/` mentions a shard). Shard 2's $39.14 is what the first run left there, and shard 3
    was never in the first run's list (`ltcm/config.json` `kalshi_shards.shards`).
- 13:48:57Z — the updater's release `main-1615d78c07bd` (main `23ccab4`: #179, plus Merton's #180,
  #181 and #182, new strategy children and a lesson) passed its canary and its 10-minute watch.
  The in-box updater shipped it, as it ships every unprotected main commit.
- **13:50:00Z — shard 3 funded, one time.** I moved $30 of collateral from shard 0 to shard 3
  inside the Kalshi account, through the gateway's one allowed funds move
  (`KalshiBroker.transfer_between_shards`, transfer `d2d4de3f-502b-42e2-ad11-f2daea67d218`). It
  ran after the release's watch had passed, so a reconcile blip could not roll a release back.
  - Before: shard 0 $331.51, shard 2 $39.14, shard 3 $0.
  - After: shard 0 $301.51, shard 2 $39.14, shard 3 $30.00.
  - The account total is unchanged ($370.6533) and the envelope is unchanged. It is not a
    deposit and not a transfer between venues, the two moves the plan forbids.

  $30 covers the one sports bunt ($10 stake, $5 position cap). **The durable fix is left
  unbuilt:** the House should keep collateral on every shard it trades, as the first run's
  service did (shards 0, 2 and 3, hourly, floor/top-up/keep). That is money-path code, and it
  deserves the adversarial review this build gave the allocator, not a deploy in the last 40
  minutes. Until it lands, shard 3 runs down as sports bunts trade, and shard 2 ($39.14) is
  similarly unreplenished for the crypto and commodities bunts.
  - 13:52:33Z — the House's next reconciliation after the move: all four books `ok` (Kalshi
    expected $370.6533, venue $370.6533; Alpaca $488 = $488).
- 13:51Z — **the owner asked** that stocks and the Alpaca accounts' level-3 options be fully used
  by the agents now that the market is open.
  - **Account reads.** Both accounts are options level 3 (approved and trading). The real account
    is a cash account (multiplier 1, no shorting) with $488 of options buying power.
  - **Activity from 13:30Z to 13:52Z:**
    - Practice: 70 equity orders and 16 equity fills (5 agents); 8 option orders and 4 option
      fills (4 agents).
    - Real Alpaca: only haghani-37's crypto, 3 orders, one refused by the book's 50%-of-equity
      rule.
    - No Alpaca stock or option agent holds real money.
  - **Response.** A read-only investigation workflow was launched (stocks, options and level 3,
    and the Alpaca ladder, each re-checked by a skeptic, then a fix plan). Its findings follow.
- 14:01:41Z — **the shard fix, confirmed by a fill.** meriwether-h2d625d bought 5 KXMLBTOTAL at
  $0.54 on real money: the first real sports fill. The same order had been refused twice before
  shard 3 held collateral.
- 14:03:24Z — huang-h51fdd3 (same family as the first bunt, huang-h51fdd3-2) died on evidence: down 19.1%
  on practice after 6 active blocks.

## Morning report (the deadline, 14:30:58Z)

### 1. What is live
- **Release** `main-1615d78c07bd` (main `23ccab4`: Deploy 6's code plus #179-#182, shipped by the in-box updater at 13:38:57Z, watch passed 13:48:57Z), tick 56-84 s. Nothing stopped, no book frozen.
- **Grant** `earned-live-20260921` is active on money digest `44e8d48d` (constitution `9fa83727`),
  ratified 19 s after Deploy 1. No later deploy changed a money rule.
- **Workstreams**, all on the running release:

| # | Workstream | State on the running release |
|---|---|---|
| A | The allocator (capital is the ladder) | live since 08:27:54Z (#163): 7 bunts (Kalshi 6, $171.81; Alpaca 1, $25), 88 on practice, 0 swings |
| B | The capital board | live: blakewoods.us/capital, the checkpoint of 14:02:24Z carries the board (104 desks) with bands, stakes, evidence and the moves trail |
| C | Exit slicing, positions follow stakes | live (#164, #168). No slice has run on a venue: every position is under the order caps |
| D | The Alpha Lab | live (#170, #173, #176, #178). First graduate born 12:59:39Z (huang-l23cdb7) |
| E | A tick that never blocks, profit-indexed compute | live: E3 defers births when the probe box is busy; E1 gateway `3eef1b8a` reads equity $1,015.12 (read 13:57Z) against the $1,017.75 baseline (bonus $0) |
| F | Open desks (stretch) | live (#171). 0 members: no birth has spanned desks |

### 2. The ladder
- **Band moves since T0.** Each was earned on evidence, and none was forced:

| At (Z) | Agent | Move | Why |
|---|---|---|---|
| 08:06:22 | haghani-37 (Alpaca) | practice → micro rung (old screen) | 3 active hour blocks, 3 closed trades; made a $25 bunt at the first allocator pass (08:30:03Z) |
| 12:10:19 | huang-h51fdd3-2 (Kalshi) | practice → bunt $10 | E 1.0257 on 4 settlements, after the corrected re-audit approved |
| 12:24:20 | haghani-55 (Alpaca) | replay → practice | deep replay and the sealed holdout |
| 12:50:25 | meriwether-h2d625d (Kalshi) | practice → bunt $10 | E 1.0100 on 7 closed trades (no audit needed) |
| 13:35:56 | huang-h427345 (Kalshi) | practice → bunt $10 | E 1.0162 on 7 closed trades |

- **Births and deaths since T0:** 5 births (3 foundry cards, 1 House, 1 lab graduate) and
  6 deaths (5 displaced; huang-h51fdd3 died on evidence at 14:03Z, down 19.1% on practice). There was no demotion and no swing: no
  agent has the 8 real trades a swing needs.
- **Real stakes now:**
  - **Kalshi** (6):
    - mullins-2 $56.11 (E 1.114, 4 real trades, +$1.29 realized)
    - mullins-6 $56.70 (E 1.021)
    - hawkins-19 $27.48 (E 0.990)
    - huang-h51fdd3-2 $11.52 (E 0.870, frozen for the day by the daily-loss rule)
    - meriwether-h2d625d $10 (E 1.011)
    - huang-h427345 $10 (E 0.957)
  - **Alpaca** (1): haghani-37 $25 (E 0.999, crypto)
  - No Alpaca stock or option agent holds real money (see the owner's request below).
- **The first Alpaca real trade:** haghani-37 bought 0.1923 LTC/USD at $62.39 ($12.00) at 11:26:20Z,
  as a $25 bunt. The position is still open.
- **Top practice evidence below the bunt line:** at 14:05Z:
  - **Kalshi:** the lab graduate huang-l23cdb7 is at E 1.011, over the line, but it has 1 closed trade of the 5 it needs. Next are mullins-13 at 1.006 (4 trades), meriwether-36 at 1.006 (6 trades), and the hawkins-22/23/24 family at 1.005 (0 trades).
  - **Alpaca:** the best practice agent is haghani-39 at E 1.0006 on 2 trades. No Alpaca stock or option agent is near the line.

### 3. Real P&L per venue, and the throttle
- **Since T0 (fills made during the build):**
  - Kalshi: 4 fills, $22.00 notional; realized −$1.52 (huang-h51fdd3-2's DOGE 15-minute contract). Includes the first sports fill, 5 KXMLBTOTAL at $0.54 at 14:01:41Z, after the shard fix.
  - Alpaca: 1 fill, $12.00 (haghani-37, LTC/USD), still open; the account holds $488 cash and $500.05 equity.
- **Floor real P&L since the grant:** −$5.84.
- **The throttle** triggers at −30% of the $1,017.75 envelope (−$305). It was never active. Across
  every 15-minute watch the floor's real P&L stayed between −$2.63 and −$5.07.
- **Performance fees:** $0, since no agent has realized a profit on real money yet.

### 4. The lab
- **Throughput:** the first evaluation was at 10:51:07Z.
  - The first hour evaluated 87 candidates, against the plan's 1,000. It was tape-bound, not
    evaluator-bound: 109 batches took 577 s on the lab box and $0.03 of Sail. #173, #176 and
    #178 fixed the batching.
  - From 12:44Z it ran at about 200 candidates per 10 minutes, in batches of 32.
- **Totals:** 905 evaluated by 14:03Z (139 seeds, 753 parameter children, 13 agent submissions), 0 errors; 807 eligible (89%) and 661 through the replay gate (73%). 374 were evaluated in hour 13. 155 batches used 809 s of lab-box time and $0.045 of Sail. The archive holds 26 cells across 9 desks.
- **Graduation:**   - **Born:** 1 graduate, huang-l23cdb7 at 12:59:39Z.
  - **Passed the House replay, waiting for a seat** (their desks or the league are full of agents inside their grace): 2 at kalshi-attention, 2 at kalshi-sports, 1 more at kalshi-crypto-15m.
  - **Failed the House replay:** 2 kalshi-sports and 1 kalshi-weather, on out-of-sample growth.
  - **Refused a holdout run by rationing:** 4 candidates from 3 lineages (alpaca-megacaps and alpaca-index-etfs).
  - **Now trading on practice:** the born graduate is at E 1.011 after 1 trade.
- **What the graduate trades:** a KXETH15M prior-window fade on 5-minute ETH bars, on the
  kalshi-crypto-15m desk, with a $200 practice stake.

### 5. Costs (since T0)
- **OpenAI:**
  - Gateway month: $308.46 → $358.74, so **$50.28** spent. The cap is the funded $408.
  - House line: $65.88 plus the $28 top-up, now $46.44, about **$47** at the House's ceiling prices.
- **Sail:** the balance went $102.26 → $98.35 (**$3.91**). The House line went $100.66 → $96.04. The burn estimate is $31.45 a day, a 2.8-day runway.
- **Jev:** $16.14 → $16.14 (**$0**) of its $42 cap.
- **Cost per dollar of real P&L:** undefined. Real P&L since the grant is negative (−$5.84),
  so there is no profit to divide by.

### 6. Defects
- **Found and fixed (all verified on the running release):**
  - the site refusing checkpoints (#156, site #4);
  - 14 allocator defects from the adversarial review (#163);
  - the gateway's Alpaca ask markup (#164);
  - the lab spending a living line's holdout (#170);
  - `/v1/health` reading both venues inline (#170, gateway `3eef1b8a`);
  - repeated standings making ticks 191 s (#173);
  - the Kalshi maker label (#174);
  - the auditor judging bunts against the legacy tuition (#176);
  - lab batches of one and unbuilt children's tapes (#173, #176, #178);
  - the watch script's real-money and gateway lines (#179).
- **Found and worked around:**
  - **Kalshi exchange shards.** MLB, WNBA and tennis markets sit on shard 3, and shard 3 held $0,
    so the sports bunt's real orders were refused (`insufficient_shard_balance`, 12:58Z and
    13:30Z). At 13:50Z I moved $30 from shard 0 to shard 3 inside the account (transfer
    `d2d4de3f`). The durable fix is still to build: the House should keep collateral on shards 0,
    2 and 3, as the first run's service did for 0 and 2. It needs a reviewed PR.
- **Still open:**
  - **The daily-loss rule freezes small bunts.** The book's 10% per-desk rule holds a $10 bunt
    out of new entries for the day after one small loss (huang-h51fdd3-2: −$1.52). This is left
    for the owner.
  - **Pre-audit red flags are noisy.** "barren" and "refusals" force an audit before a bunt.
  - **The lab's first hour was 87 candidates, not 1,000.** Tapes are built on the 1-vCPU House
    box, 4 a step, and every restart empties the tape cache. Building tapes on the 8-vCPU lab box
    is the likely next step.
  - **Holdout rationing is binding.** 3 lab lineages (agent:mcentee-31, agent:scholes-21,
    agent:mcentee-30) have spent their 3 sealed-holdout evaluations, so their elites cannot
    graduate. This is the plan's D4 rule working as written, not a bug. It does mean the
    Alpaca desks' best lab programs are held back.
  - **The open desks are empty.** The lab seeds per desk, so it does not produce spanning programs.
  - **`kalshi-open` maker fees.** The desk lists no `maker_fee_series`, so its replay and desk
    brief treat maker fills as free. In fact 163 of the 195 series in its universe charge makers,
    so replay understates cost on that desk. It has no members yet.
  - **GitHub's 3.11 runner hung twice on #176.** Neither hang reproduced; watch for it.

### 7. Rollback, and the owner's decisions
- **Rollback:**
  - **The House, to the previous release:** on the box, run
    `cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace --reason "why"`.
  - **The allocator only:** set `allocator.enabled` to `False` in `league/constitution.py`, run
    an owner deploy (`python3 scripts/floor_box.py deploy`), then re-ratify with
    `python3 scripts/live_trading.py --ratify earned-live-20260921`. The old screen, micro bound and Kelly sizing
    then decide again.
  - **The gateway:** `npx wrangler rollback` in `gateway/`. The version before E1 is `c6c507ad`.
  - **Stop all real trading:** `python3 scripts/gateway_admin.py kill`.
- **Decisions pending:**
  1. **Sail auto-recharge.** The balance is $98.35, about 2.8 days at $31.45 a day.
  2. **The daily-loss rule for bunts:** keep 10% of the stake, or judge a bunt on the allocator's
     own 35% stay drawdown.
  3. **Compute indexing:** E1's ceiling is the funded $408 (`FRONTIER_MONTH_MAX_USD`). Raise it
     only when more is funded. Until then profit is measured but buys no compute.
  4. **Alpaca permissions:** none were needed tonight. The account was ACTIVE with crypto ACTIVE
     at T0.
  5. **The envelope:** grant capital is Kalshi $517.75 and Alpaca $500. No deposit was made
     and nothing moved between venues. The only funds move was $30 between Kalshi shards of the
     same account.
  6. **Kalshi shard funding:** approve the durable fix (the House funds shards 0, 2 and 3 hourly),
     or keep topping up shard 3 by hand as sports bunts appear.
- **Worktrees:**
  - Removed: all of this build's worktrees (`ltcm-ladder`, `ltcm-record`, the builders' and the
    integration's).
  - Kept: `ltcm-deploy`, which is the deploy tree.
  - Left untouched, from earlier builds, with unmerged branches: `ltcm-architect-repair`
    (`codex/architect-registry-repair`), `ltcm-night` (`night/record`) and `ltcm-repairs`
    (`night/repairs`).
  - Left untouched, merged or detached: the other 31 older `ltcm-*` worktrees.

### 8. The owner's two requests during the watch (open at the deadline)
- **13:51Z: use stocks and the level-3 options the Alpaca accounts are approved for.**
  - **Measured.** Both accounts are options level 3. Since the open, practice agents trade
    stocks (70 orders, 16 fills) and options (8 orders, 4 fills). No stock or option agent holds
    real money: the best Alpaca practice agent is at E 1.0006.
  - **Why options are shut out.** At a $25 bunt the position cap is $12.50, and one contract
    costs premium × 100, so options are all but shut out of real money at bunt size.
  - **In progress.** A read-only investigation (stocks, options and level 3, the Alpaca ladder,
    each re-checked by a skeptic) is writing a ranked fix plan. The plan separates fixes to what
    agents can already trade from new level-3 multi-leg support. Nothing will force a trade or
    lower a promotion line.
- **14:02Z: the capital page's ladder.** Level 1, 2 and 3 with a word or two each ("Practice",
  "Live Trading", "Increased Capital"), one dot per agent instead of bars, and made as intuitive
  and interesting as it can be.
  - **In progress.** Three concepts judged, then a build in `~/Work/personal-site-levels` with
    tests and headless screenshots at 390 px and 1,280 px, visual and code review, then the
    site deploy.
  - **What does not change.** Only the site changes. The House's data already carries the band,
    stake, evidence and last move.


## After the deadline (14:31Z onward)

**A correction to the report.** The report says haghani-37's LTC position is still open. It was
drafted at 14:05Z, and at 14:19:26Z haghani-37 sold its 0.1919 LTC at $60.07 for −$0.51. That was
the first closed real Alpaca trade. At the deadline the real Alpaca account held cash only.

**The floor.**
- **Kalshi:**
  - **Sports fills.** meriwether-h2d625d, the sports bunt, filled on shard 3 again: 5 KXMLBTOTAL
    AZ–COL at $0.54 (14:32:12Z) and 5 MIL–PHI at $0.54 (15:02:29Z).
  - **huang-h427345.** Its first real trade was 4 KXBTC15M at $0.62 (14:48:47Z), which settled
    at a loss of about $2.55. At 14:57:45Z **the allocator's first demotion** sent it back to
    practice: E 0.7157, under the 0.8585 exit line. The one-hour re-entry cooldown then applied.
- **Alpaca:**
  - **haghani-37.** At 15:02:48Z the evaluator's drift check (a CUSUM of block growth against
    the record that earned the rung) moved it from rung 2 to 1: "its growth has decayed from the
    record that earned this rung". The allocator kept this check deliberately, beside its own
    lines, and for swings #163 made drift re-seat only. With it, Alpaca has no real-money agent
    until one earns a bunt.
  - **Lab stock programs.** For the first time, lab programs for Alpaca stock desks passed both
    the House replay and the sealed holdout: `alpaca-megacaps` (14:33Z), `alpaca-index-etfs`
    (15:00Z), and `alpaca-crypto-majors` (15:04Z and 15:27Z). Each waits for a seat.

**The owner's stocks-and-options request, answered.**
- **The investigation** is saved as
  [a proposal](../proposals/2026-09-23-alpaca-stocks-and-level-3-options.md). In short:
  - Level 3 is not used at all. The House only buys single calls and puts, as design decision 28
    set it (assignment risk on a cash account).
  - No stock or option agent has earned real money: the best are E 0.9987 and 0.9973.
  - Four House defects would have stopped them once they did.
  - The gateway under-priced multi-leg orders.
- **Shipped:**
  - **#187 (gateway).** Multi-leg, symbol-less, stop and adjusted-option Alpaca orders are refused
    before pricing. Six tests fail on main and pass on the branch. Deployed at 15:06Z as gateway
    version `3e79ad85`, tagged `3cca040`. The House's own orders (market or limit; plain, crypto
    and OCC symbols; qty) price exactly as before.
  - **#189.** Real-money limits shown to agents are the ones the book enforces; buys are trimmed
    to fit, never enlarged. The options chain is filtered at what a bunt can hold. Stock and
    options desks wake just after the open. `ctx.now` is stamped after market data.
  - **#190.** Stock and options agents that are trading keep their seats until they close 5
    trades or have had 3 sessions. Grace counts in session hours. No agent is removed while
    holding a position overnight. A rewrite of a never-traded agent no longer restarts its
    clock. mcentee-34 gets DST-correct session hours. Every agent sees its distance to the bunt
    line.
  - None changes a money rule: the grant stays on `44e8d48d`.
  - **Deploy 7 (15:29Z).** #187 changed a protected path (`gateway/`), so the in-box updater
    refused the range, and main `da846db` (#187, #189, #190) went out as an owner deploy. Release
    `20260923T152910Z-9a5970c56aca` passed its canary, was promoted at 15:30:50Z, and passed all
    20 watch checks by 15:40:50Z. The running `house.py` carries `_fit_real_entry`,
    `_trading_pending` and `bunt_line`. The grant stayed active on `44e8d48d`, with no
    re-ratification needed.
- **Next:** B1, level-3 debit verticals on practice. Real multi-leg orders only after a week on
  practice and a re-ratified grant, per the proposal.

**The capital page (the owner's second request).**
- **personal-site #5,** deployed at about 15:25Z as version `0752a7b8`, tagged `c2ee806`. The ladder
  is three floors:
  - Level 3 "Increased capital"
  - Level 2 "Live trading"
  - Level 1 "Practice"
- **Drawing:** one dot per agent (green up, red down, grey flat, hollow untraded). Real-money
  agents are gold coins sized by stake. A gold arc fills toward the next level.
- **Beneath the floors:** a Retired strip, the latest climb (replayed once), and the latest
  moves.
- **Build:** three concepts were judged, then built, reviewed visually and for code (3 majors
  and 8 minors fixed), then checked by screenshot on the live site at 390 px.

**My own slip.** At 15:06Z a local `ln -sfn` meant for a scratch check replaced the `.data`
symlink in `~/Work/ltcm-deploy` with a link to itself. For about a minute the local box tools
could not read `box.json`. Nothing on the box, the gateway or the site was touched. I restored it
to `~/Work/long-term-capital-management/.data`, the target every other worktree uses.
