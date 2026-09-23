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
| Watch | ≥ 90 minutes, every 15 minutes through `scripts/floor_watch.py` | ⟨⟩ |
| Docs | README, operations, runbook, league README, CONTRACT, gateway README, DESIGN.md, rules, playbook | ⟨⟩ |
| Cleanup | this build's worktrees and branches removed once merged | ⟨⟩ |
| Memory | project memory + MEMORY.md line | ⟨⟩ |
| Report | morning report at the deadline | ⟨⟩ |

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
  - **Graduation, per stage:** 3 elites went to the sealed holdout. 2 were holdout-rationed and
    1 passed the House replay, then `waiting_seat`.
