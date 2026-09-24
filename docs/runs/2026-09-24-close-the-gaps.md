# Close the gaps to the north star — September 24, 2026

Execution record for the owner's goal of Sept 24, 2026: execute
[the close-the-gaps plan](../goals/LTCM_CLOSE_THE_GAPS.md) autonomously, with no deadline, until
every gap in its Done list is closed or recorded as blocked with numbers. The run happens outside
US market hours: anything that needs a stock or options session is built and deployed, then
recorded for the next open; live verification uses the markets that trade around the clock.

## The clock

- **T0:** 2026-09-24T01:34:02Z (the first action of the session, `date -u`).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Progress notes:** a scoreboard reading and a short state note every four hours from T0
  (05:34Z, 09:34Z, 13:34Z, ... Sept 24), in the "Progress notes" section below.
- **Report:** when the Done list holds, in this file and in the session.

## The owner's message (Sept 24, 2026, at T0)

- Funding in place: Sail funded to $170 (the owner added $100) and OpenAI to $213 (added $200).
  At T0 the run records the top-up (`scripts/campaign_topup.py --sail 100 --openai 200`), raises
  the gateway's `FRONTIER_MONTH_USD` and `FRONTIER_MONTH_MAX_USD` to the month's spend plus the
  $213 funded, deploys the gateway and confirms the frontier tier is "all" before Wave 0 launches.
- The key-free data hosts of workstream I are on the live allowlist; their recorders are built in
  Wave 1. The EIA and Odds API keys are not available yet: those two recorders stay behind a host
  check and are the owner's step in the report.
- Authority: everything the plan grants (money rules inside its closed table with a re-ratify of
  `earned-live-20260921` at each promotion that moves the digest; owner, gateway and site deploys
  with tests green; real trading on Kalshi and Alpaca inside the envelope, volatility and losses
  accepted; funded compute up to the funded balances; repo cleanup under its rules). Nothing in
  the plan's "Not authorized" list.
- Never wait on the owner: one notification per owner step, everything else proceeds, the exact
  commands in the report. Fix every bug observed and add an invariant for it.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan read from origin/main (the no-deadline version, PR #219) | done 01:41Z (#219 merged, `35d6c1b`) |
| 0.3 | Top-up recorded; gateway month raised and deployed; tier "all" | done 01:36-01:38Z (below) |
| 0.4 | Baseline and the scoreboard at T0 | baseline done (below); the scoreboard's T0 reading from Z |
| 0.5 | First-hour decision 1: can this session ratify | done 01:35Z |
| 0.6 | First-hour decision 2: compute truth; owner notified | done 01:45Z |
| 0.7 | First-hour decision 3: the lab | done 01:48Z |
| 0.8 | First-hour decision 4: Deploy A's money set | done 01:55Z |
| 0.9 | First-hour decision 5: file owners per wave | done 01:55Z |
| Z | The scoreboard (`scripts/gap_scoreboard.py`) | T0 reading done (PR #223, below) |
| D1 | The lab's step | **verified** 06:40Z: 63 batches (84 candidates) in the first hour after Deploy A (target ≥ 30), no failed step, the ADA/USD row blocked "the House's tape for these NEEDS has no steps" |
| D2 | Phantom OpenAI holds | live 05:37Z; gateway `44edfee6` 05:26Z; the meter anchored 05:38:57Z; the release to verify |
| D3 | Exits walled off by the self-cross rule | live 05:37Z; **0 self-cross refusals** in the first hour (26 in the 6 h before T0); no exit has yet met a House bid (0 crosses, 0 re-prices) |
| D4 | Independent settlements | live 05:37Z (money digest `521c4586`) |
| P | Promotion on proof (probes, the one-loss trial, maker unless proven) | live 05:37Z; 05:44Z board: 1 proven-family bunt, 7 probes; lopsided gate adopted (04:15Z) |
| X0 | Book rules through constitution keys | live 05:37Z |
| Deploy A | Wave 0, ratified at promotion (digest change 1 of 2) | done: promoted 05:37:31Z, ratified 05:37:41Z on `521c4586`, watch passed 05:47:34Z |
| C1/C2 | The mechanism ledger and the family swing | ⟨pending⟩ |
| S | The evidence clock and the seat market | ⟨pending⟩ |
| L | The loop's joints | ⟨pending⟩ |
| I | Feed recorders on the allowed hosts | ⟨pending⟩ |
| X1/X2 | Pause and size-down tools; the horizon rule | ⟨pending⟩ |
| Deploy B | Wave 1, ratified at promotion (digest change 2 of 2) | ⟨pending⟩ |
| E | The lab as a search; the foundry brief; capacity | ⟨pending⟩ |
| C3 | Alpaca real money | ⟨pending⟩ |
| W | The site's mechanism ledger | ⟨pending⟩ |
| Deploy C | Wave 2 | ⟨pending⟩ |
| Watch | At least three hours after the last deploy | ⟨pending⟩ |
| B | Bugs: regression test, fix, invariant | ⟨pending⟩ |
| H | Cleanup: worktrees, branches, PRs, dead docs | ⟨pending⟩ |
| Docs | README, operations, runbook, league README, CONTRACT, gateway README, DESIGN.md | ⟨pending⟩ |
| Memory | project memory + MEMORY.md line | ⟨pending⟩ |
| Report | when the Done list holds | ⟨pending⟩ |

## Baseline (T0)

`scripts/floor_watch.py --since 2026-09-24T00:34:00` at 01:33:55Z (the session scratchpad's
`watch-T0.txt`), and the read-only snapshot taken at 01:38-01:42Z (`ledger.sqlite` 401,286 rows to
01:41:05Z, `lab.sqlite`, `campaigns.sqlite`, `health.json`, `house.json`, `allocator-board.json`):

- **Release** `20260923T233921Z-493b4a2ff9ab` (main `76e446d`); tick 42 s; living 110, dead 387;
  nothing stopped, no book frozen. Grant `earned-live-20260921` active on money digest `c2b0e09c`.
- **Bands:** Kalshi bunt 9, Kalshi practice 50, Kalshi replay 1, Alpaca practice 50; swings 0;
  Alpaca real 0. Moves in the hour: meriwether-h7d7702 and hilibrand-lc04657 paper → bunt (00:39:48Z,
  $30 each; the first on stacked MLB strikes), huang-hd8ff7c-4 bunt → paper (01:01:35Z, E 0.8583 under
  the 0.8585 hysteresis line).
- **Envelope:** Kalshi $517.75 with $288.99 committed; Alpaca $500 with $0.51 committed; throttle off,
  floor real P&L +$1.35.
- **Real money in the hour:** Kalshi 9 fills, $44.95, realized +$16.65 across 5 agents (meriwether-
  h7d7702's MILPHI-6 NO settled +$16.31). Practice: kalshi-shadow 18 fills −$27.29; alpaca-paper 1 fill.
- **Top evidence:** meriwether-h7d7702 E 1.901 (W_paper 1.551, W_real 1.527, 13 paper / 1 real
  trades); meriwether-h2d625d 1.288; mullins-2 1.210 (W_real 1.190, 11/10); hilibrand-h6ca596-3 1.191;
  mullins-6 1.063.
- **The lab:** failing: 56 "the lab's step failed (IndexError: list index out of range)" warnings in
  the hour; last batch 23:37:17Z Sept 23 (822 batches in all); 618 queued, 3,019 evaluated; 25
  graduates and 5 cards waiting for seats (26 displaceable, 22 never-traded past grace).
- **Refusals in the hour:** 16 "a market order here could trade against the House's own resting
  order", 15 "market orders outside regular hours", 3 below the Alpaca minimum, 2 both-legs.
- **Kalshi shards:** 0 $287.54, 2 $17.41, 3 $22.71 ($60 moved in 24 h).
- **Site:** publishing (age 11 s, 118 desks, board present).

## First-hour decisions

1. **This session can ratify: yes.** 01:35Z: the ratify ran on the box through the exec
   `scripts/live_trading.py` uses (`league.live_trading main --ratify earned-live-20260921`), without
   the wrapper's restart step (a restart empties the lab's tape cache). The grant stayed active on
   `c2b0e09c`; nothing was written. Deploys that change the digest use `deploy_ratify.sh`, which
   ratifies the moment the watchdog promotes.
2. **Compute truth and the owner's funding.**
   - At T0 the gateway's month read $394.46 of $408 (tier "audits": the House's OpenAI line read $7.94
     after 49 holds with no response older than 6 h, $98.36; in the 01:42Z snapshot: 19 aged 6-24 h,
     $23.96, and 30 older than 24 h, $74.40, plus 2 new ones, $8.50, made after the top-up). Sail
     $169.87 (the owner's $100 already in), burn $40.45 a day on the 24-hour average, runway 3.95
     days. Jev $16.16 of $42.
   - 01:36:00Z: `scripts/campaign_topup.py --id topup-20260924-owner --sail 100 --openai 200` recorded
     the owner's top-up (House lines after: Sail $168.22, OpenAI $207.94; burst caps OpenAI $778, Sail
     $275).
   - 01:36Z: the gateway's `FRONTIER_MONTH_USD` and `FRONTIER_MONTH_MAX_USD` 408 → 607 ($394.46 metered
     at T0 + the $213 the owner states is funded, rounded down), deployed from PR #220's commit
     (`7f322bf`) with `wrangler deploy --tag 7f322bf`: version `8d4e1a47`. `/v1/health` at 01:37Z:
     spent $402.96 of $607 ($8.50 spent in the minutes after the House line reopened).
   - 01:37:56Z: the House's frontier tier read **"all"** (it was "audits" at T0 and "earned" at
     01:35:55Z). Wave 0 launched after this.
   - The owner steps were given in the session at about 01:45Z (the terminal was active, so the push
     notification was not sent): the SEC/NWS User-Agent contact address came through blank in the
     /goal message ("use ."), so the recorders use `agent@blakewoods.us` unless the owner names
     another; the OpenAI dashboard's September spend, to check D2 against; the EIA and Odds API keys
     when available. Nothing waits on them.
3. **The lab: still failing** (above). D1 goes first in Wave 0, with a reproduction from the snapshot.
   The lead: `Lab._search_tape` indexes `steps[0]` outside its try block, and `search_tape()` returns
   no steps for a tape that has none, so one queued candidate can stop every step.
4. **Deploy A's money set** (one digest change, one ratify), from the evidence on record: D4
   (`independent_settlements: "event"`, `max_event_share` 0.25), P1 (`probe_bunt_usd` Kalshi $10 /
   Alpaca $25, `bunt_usd` unchanged at $30 / $25 for a proven family, `family_proven` ≥ 10 independent
   settlements with a one-sided 80% bound above zero, practice at 0.5), P2 (`hysteresis_after_settled`
   3, `position_share_event` 0.2), P3 (`longshot_floor_real` 0.30, `real_entry_liquidity`
   `"maker_unless_family_taker_positive"`). `corrected_child_supersedes` rides with L1 in Deploy B's
   digest change, where its reader lands.
5. **Owners this wave** (at most four builders; worktrees from `0d1dd47`):
   - A-money (`ltcm-a-money`): `constitution.py`, `allocator.py`, `evaluator.py`, `live_trading.py`.
   - A-book (`ltcm-a-book`): `book.py`, `ltcm/risk.py`, the `Book(...)` wiring in `house.py`.
   - A-lab (`ltcm-a-lab`): `lab.py`, `labbox.py`, `scripts/floor_watch.py`'s lab line.
   - A-holds (`ltcm-a-holds`): `campaigns.py`, `campaigns.json`, the gateway's frontier accounting.
   - With them: the scoreboard analyst Z (`ltcm-z`, `scripts/gap_scoreboard.py`) and the cleanup
     agent H. Money PRs get the three-lens adversarial review before Deploy A.

## Log

- 01:34:02Z — T0; run worktree `~/Work/ltcm-gaps-run`, branch `run/close-the-gaps-2026-09-24`.
- 01:35Z — the ratify check (decision 1). 01:36:00Z — the top-up recorded. 01:36Z — gateway
  `8d4e1a47` (month $607). 01:37:56Z — tier "all".
- 01:38-01:42Z — the T0 snapshot (read-only sqlite backups on the box, downloaded to the session
  scratchpad).
- 01:41Z — PR #219 merged (the plan without a deadline, the allowed data hosts in `LEAGUE_HOSTS`):
  main `35d6c1b`; the in-box updater ships it as a release (unprotected).
- 01:4xZ — the watch loop (`floor_watch.py` every 15 minutes) and the events loop (real fills, band
  moves, audits, error alerts, deaths every 5 minutes) started, into the session scratchpad.
- 01:50Z — Merton's #221 merged by its workflow (main `0d1dd47`). PR #220 (the gateway month)
  merged: main `563314e`.
- 01:54Z — site PR #6 (personal-site): the House's `probe` band is Level 2, accepted by the schema on
  desks, the board and moves; deployed 01:55Z (`npm run build && wrangler deploy`, 78 tests green),
  version `47d752a3`, before any floor publishes the band. The checkpoint kept publishing (01:54:33Z,
  120 desks).
- 01:56Z — **Wave 0 launched together:** A-money (D4, P1-P3's keys), A-book (D3, X0), A-lab (D1),
  A-holds (D2), the scoreboard analyst Z and the cleanup agent H, from `0d1dd47`.
- 01:58Z — the events loop: huang-hd8ff7c-3 demoted (E 0.7749) after a −$4.29 settlement,
  huang-h427345-2 −$1.36: the 15-minute crypto taker bunts losing, as the gap review measured.
- 01:57Z — OpenAI since the tier reopened: the gateway month $402.96 → $405.45 in 20 minutes (235
  calls in the hour: the research backlog and the six Merton roles that were overdue; $2.52 settled,
  $8.59 of in-flight holds). Watched hourly; L2 pauses the unproductive roles in Wave 1.

- 02:15Z — PR #222 merged (the House publishes the probe band; the site accepts it since #6).
- 02:17:34Z — **the first Alpaca real agent:** haghani-56 (alpaca-crypto-alts, family
  crypto-alts-reversion) promoted to an Alpaca bunt, "E 1.0104 is at or above 1.01 on 10 closed trades",
  under the T0 rules. Its family's pooled record is negative (n 156, lcb −0.0016): after Deploy A it is
  a $25 probe, the same stake.
- 02:27Z — PR #223 merged (the scoreboard); the T0 reading is below. Z's report: D4 must count closed
  trades per event too (the A-money build does); the event rule groups `KXRAIN-26SEP21-ATL/-CHI/...`
  into one event (Kalshi's own grouping; conservative); practice rows are growth on a $200 purse and
  real rows on a $30 stake, so real rows dominate the pooled mean beyond their weight. Kept for
  Deploy A (account growth is the unit W is measured in; a return-on-risk check agrees that
  weather-favorites is proven and disagrees on sports-central-run-under, negative on practice returns
  at risk); C1 revisits the normalization with more data.
- 02:3xZ — the in-box updater shipped main (release `main-84a377f23768`): a House restart.
- 02:42Z — OpenAI: the gateway month $409.54 (+$4.09 since 01:57Z). The hour's costs on the ledger:
  Luna research 126 sessions $2.69, Sail `pro_asap` research 8 sessions $0.90 ($0.11 a session),
  consultant 3 passes $1.18, and the architect, toolsmith, designer and teacher once each ($2.46: the
  roles that were overdue while the tier was below "all"). L2 (Wave 1) pauses the four roles until the
  floor's real P&L is positive.

- 02:00Z — **H, the cleanup's first pass** (`scratchpad/cleanup-report.md`): 13 of the paused Sept 23
  run's worktrees removed (all merged and clean: `ltcm-pacing`, `ltcm-rules`, `ltcm-w0-*` ×7,
  `ltcm-w1-bugs`, `-lab`, `-loop`, `-seats`) and their 13 merged remote branches deleted; 10 more were
  inside the plan's six-hour window (eligible from 03:35Z to 07:30Z) and wait for a second pass;
  `w2-options/design` (draft #210) kept. Open Merton PRs #217 and #208 (Huang BTC 15-minute repairs)
  fail CI because `league/ci.py` `regression_tape` gives a Kalshi strategy that observes spot bars no
  `observed_bars`: a CI defect, assigned to Wave 1 (B-loop). `scripts/recover_coinbase_exits.py` is
  unreferenced (a deletion candidate).
- 02:33-03:07Z — **Wave 0's PRs:** #224 A-money (D4, P1-P3's keys; money digest c2b0e09c → 223e2f0e,
  the grant 40 → 101 seats at a $10 probe), #226 A-book (D3, X0, and a latent `Book.cancel` race: a
  fill between Kalshi's read and delete was booked as cancelled), #227 A-holds (D2 and the gateway's
  settled/in-flight split), #228 A-lab (D1). The lab's IndexError, reproduced from the snapshot: a Luna
  child on alpaca-crypto-alts asking ADA/USD 15Min, whose deep tape
  (`deep:alpaca:ADA/USD:15Min:100:hour:2025-09-12:2025-11-14:sip`) had 0 steps because the history store
  holds ADA/USD only from 2026-02-01; `_search_tape` read `steps[0]` outside its guard, so one queued
  row failed every step.
- 03:0xZ — adversarial reviews launched for #224, #226 and #227 (A-lab is reviewed by the main session:
  not a money path). The Wave 1 recorders (B-feeds) launched from `90a15f6`.
- 03:09Z — a live defect found by the Deploy A check: the House's wind-down of the dead agent
  haghani-h426990's practice account has sent a 0.000000001 LINK/USD sell every ~5 minutes since 15:44Z
  Sept 23, and Alpaca refused all 107 ("order qty must be >= minimal qty"). Assigned to Wave 1 with an
  invariant (B-seats).

- 04:0xZ — **the three money reviews.**
  - A-holds (#227 → `a-holds/review`, draft #232): safe with follow-ups; four defects fixed, the
    required one among them: the House's OpenAI line read $70-79 above the gateway month (above funded
    money) and the agents' credit pool paid $32.87 an hour instead of $28.49; now every reader sees at
    most the gateway month's remaining while its reading is fresh. Also: an unreadable gateway month
    now reads the tier as "audits" (research to Sail, no role scheduled into a refusal); a month the
    gateway cannot close is counted once. The rollback claim holds (the previous release opens the
    amended store). Deploy the House at least 10 minutes after the gateway.
  - A-money (#224 → `a-money/review`): seven fixes (a probe's limits ran ahead of an unlent raise; an
    unproven family's probe could displace a proven family's idle bunt; the family record read Alpaca
    practice fills without the haircut E charges; probe naming; three untested rules pinned; the rules
    text on drift; stale digests in the docs). Two evidence findings: (1) on lopsided records
    (favourites: many small wins, rare whole losses) the t bound alone "proves" an edgeless family at
    its 10th observation 49% of the time at 93c and 74% at 97c, against the nominal 20%, and
    crypto-15m-favorites was proven on Sept 20 on ten small wins before its 11th lost; (2) the proof
    is re-read every pass with no charge for repeated looks, so families flip in and out.
  - **Decision (04:15Z):** the family proof adopts the House's own loss-rate gate for lopsided
    records (`stats.lopsided_growth_lcb`, the rule the evaluator's judges already apply beside their t
    bounds), carried by a constitution key so the ratified digest records it: the table's "one-sided
    80% lower bound", computed honestly for favourites. `min_independent_settlements` stays 10 (20
    would not change the per-look rate of a symmetric record). **Consequence at T0:** weather-favorites
    is NOT proven (t bound +0.0033, loss-rate gate −0.0125: 2 losses in 16 against a breakeven loss
    rate near 7% at ~93c), so mullins-2 and mullins-6 become probes and shrink to $10 by free cash;
    sports-central-run-under (meriwether-h2d625d, symmetric taker bets) stays proven. The plan's
    premise that weather favourites was the one proven edge does not survive per-event counting and
    the loss-rate gate; the report says so with these numbers. Also: an unproven family's agent may not
    take the agent-level swing (every real-money agent is a probe or a proven family's member), and a
    family record that fails to compute is treated as unproven and never blocks a wake or an exit.
    Repeated looks go to C1.
- 04:1xZ — a DNS outage (EAI_AGAIN) stopped three agents (the A-book reviewer, B-feeds, B-loop);
  all three resumed from their transcripts.
- 04:12Z — the cleanup's second pass: `ltcm-w1-int`, `-w1-bugs-rev`, `-w1-bugs-fu`, `-w2-money`,
  `-secondlook`, `-w2-money-rev` removed (merged, clean, past six hours) with their local and remote
  branches. Left: `ltcm-sailfloor` (05:08Z), `ltcm-w2-int` (05:19Z), `ltcm-run` (05:52Z; unmerged: push
  only), `ltcm-hosts` (07:30Z), `ltcm-w2-options` (draft #210, kept).

- 04:24-04:41Z — the reviewers' follow-ups landed: A-book rows 8 (a crossed seller is paid what its
  venue would have paid it alone; the House row keeps the gap) and 9 (an exit the House re-priced never
  walls off the agent's next exit; it is re-checked every pass); A-money the lopsided gate
  (`family_proven.lopsided_gate`), a family record that fails never blocks a wake or the pass, and only a
  proven family's agent swings.
- 04:45-05:10Z — **B-feeds (#234) and B-loop (#236) opened.** B-feeds: twelve recorders (Open-Meteo
  ensembles and forecast history, NWS, EDGAR 8-K acceptance times, Nasdaq dates, NY Fed SOFR, Treasury
  par yields, ESPN odds, TSA, OKX open interest; RealClearPolling answers every automated client with a
  captcha and is recorded as refused; EIA and The Odds API wait for the owner's keys). The main session
  added three fixes it reported (the default User-Agent carried the owner's personal address; the
  foundry's coverage read would lose the ingestion's row within a day; the replay view's feed text).
  B-loop: L2-L4, the CI Kalshi tape's observed bars (unblocks #217 and #208), empty history tapes
  refused where built; and it found `load_turbo` silently dropped `turbo.json`'s Merton cadence, so the
  architect ran every 30-60 minutes instead of 24 h.
- 05:08Z — **Deploy A's PR #240** from `a/integration` (A-lab, A-holds' review, A-book's review, A-money's
  review, the rules text for the real book, one event key for the book and the allocator, main's
  Merton merges). Money digest `c2b0e09c` → `521c4586`. First CI: two House-level fixtures entered a real
  Kalshi position at market and were now refused by X0 (the keys and the book's rules first met on the
  integration branch), fixed by patching the keys out around those entries; three more modules failed on
  "Disk quota exceeded": the session's /tmp is a 3.8 GB tmpfs, filled by parallel suites, stale test
  directories and the reviewers' tree copies (cleared to 1.8 GB free).
- 05:10Z — B-families and B-seats launched from `a/integration` (`8b301a0`).

- 05:25:59Z — **the gateway for Deploy A** (`wrangler deploy --tag deb12e9`, 157 tests): version
  `44edfee6`; `/v1/health` `frontier` reads `settled_usd` 421.405264, `inflight_usd` 0, `previous` null.
- 05:26Z — PR #240 merged (main `9191e81`, with Merton's #241).
- 05:30Z — the T+4 scoreboard reading (below, "Progress notes").
- 05:36:14Z — **Deploy A** (`deploy_ratify.sh` from `~/Work/ltcm-deploy` at `9191e81`): release
  `20260924T053614Z-ca151559d272`, **promoted 05:37:31.724Z**, **the grant ratified 05:37:41Z** (10 s)
  on money digest `521c4586` (constitution `8116302e`): 101 agents at a $10 smallest stake, capital
  unchanged; the watch passed, DEPLOY-EXIT 0 at 05:47:34Z.
- 05:44Z — the first board under Deploy A: meriwether-h2d625d the one bunt (sports-central-run-under,
  proven; target $37.50); probes: haghani-56 (Alpaca $25), hawkins-19, hilibrand-h6ca596-3,
  hilibrand-lc04657, meriwether-h7d7702, mullins-2 (target $11.65, $29.08 now) and mullins-6 ($10.29,
  $36.70 now), shrinking by free cash only (six "size" verdicts with band `probe`). The lab ran 4
  batches by 05:46Z with no failed step. The OpenAI meter anchored at 05:38:57Z ($421.85 settled at the
  gateway; the House line $179.11 against the gateway month's $183.59 left).

- 05:50-06:10Z — cleanup: the Wave 0 worktrees and branches removed (merged via #240; #224/#226/#227/#228
  marked merged by GitHub, #232/#235 closed); the paused run's `ltcm-sailfloor`, `ltcm-w2-int` removed,
  `ltcm-run` removed with its unmerged branch kept on origin (`4572849`). C-tools (X1, X2, the wake skip)
  launched from `9191e81`.
- 06:05Z — **a D2 defect found live:** no stale OpenAI hold released in the first half hour. The check
  compared the House's settled sum since the anchor ($4.1177, growing the moment each call answers) with
  the gateway's settled growth as last read ($4.1045, a tick old): while research ran the House was
  always a minute of calls ahead, so every try was refused, and nothing said so. Fixed in PR #246 (compare
  only calls older than a call's life before the reading; a genuinely lagging gateway still refuses) with
  the invariant `House._watch_absorb` (a release refused for half an hour is said once, with the
  check's numbers). Protected: rides Deploy B. Until then the $98.36 of holds stay counted (the tier
  reads the gateway month, which is the nearer line, so nothing is starved).
- 06:10Z — **B-families (#242) done:** `league/families.py` (the mechanism ledger), the family swing
  (15 real settlements, 2 × the bunt, doubling every 10 positive, Kelly on the bound, 60% of the venue
  and measured capacity, shared across a family's members), `swing_requires_proven_family` and
  `corrected_child_supersedes` as keys, and **the family proof's unit changed to return on the capital
  at risk** (`ln(1 + 0.01 r)/0.01` per event; practice rows had been growth on a $200 purse and real
  rows on a $30 stake, so real rows weighed 3-7 times their declared weight). Money digest `521c4586` →
  `1fa87d83`. Under it **no family is proven at T0**: sports-central-run-under's account-growth proof
  came from buying two strikes on the games it won and one on those it lost (6 of 11 practice events at
  about even money after a 7% fee); weather-favorites' loss-rate bound is −0.21. The first family swing
  is about 19 days away at weather's real pace, if it never loses. Reviews launched: #242
  (adversarial), #236 + #234 (watchdog, point-in-time honesty, compute).

- 06:40Z — **Deploy A's first hour:** the lab ran 63 batches (84 candidates), the poison row is blocked,
  no step failed; 0 self-cross refusals and 0 X0 refusals (no real entry tried a market order, a
  longshot or a crowded event); no band move. B-seats (#245) opened: S1-S4, L1 (its first pass
  supersedes meriwether-h2d625d, 34 of 34 entries takers), the dust wind-down, `_trading_pending`; its
  adversarial review launched.
- 07:05Z — **Wave 1 reviews, B-loop (#236) and B-feeds (#234):** three defects fixed on
  `b-loop/review` (#247) and `b-feeds/review` (#250), each with a test that failed before: Deploy A's
  House kept no record of repeating warnings, so a warning firing every tick through Deploy B's restart
  would have escalated inside the 10-minute watch and rolled Deploy B back (the House now seeds the
  runs from the ledger); the $2/h Sail research cap let queued jobs through as if already running (34
  were queued at once at 00Z); a backfill page made the hourly pass skip its key (an open-interest hour
  landed at 05:02 instead of 04:00). No point-in-time leak found; the reviewer broke every stamp on
  purpose and the tests caught each. Left PLAUSIBLE: a warning that starts during a watch now rolls a
  healthy release back after 10 repeats (by design of L3); daily rain totals may be shifted an hour.
- 07:05Z — **C-tools (#249) built** (X1 pause and size-down in place, X2 the horizon by the scheduled
  expiration, the stock/option wake skip; no protected file, no digest change). Its adversarial review
  started. Integration of Deploy B began on `b/integration` (`~/Work/ltcm-b-int`): #246, `b-feeds/review`
  and `b-loop/review` merged (two doc conflicts resolved), 157 tests of the touched modules OK.
- 07:40Z — **B-families (#242) review: four majors and five minors fixed** on `b-families/review`
  (#252): two newcomers seated into a swinging family in one pass were each lent the one-member share
  ($150 against a $50 cap); the family audit's verdict counted as one member's own approval (a free
  agent-level swing); Kelly per event was turned into a stake at the 20% position share while one event
  may hold 25%; the at-risk unit weighted every event alike, so a family that lost $44 over 100 events
  came out proven (now each event weighs what it put at risk); plus the grant's rung-3 check at every
  pass, an audit-request error no longer sweeps a proven family to probes, `family.record` rows only
  on a change (was ~10,000 rows a day), tests that mutations had slipped past, two doc errors.
- 07:40Z — **Decision on the family swing's entry (findings 10-12 of that review).** Measured by
  simulation (`scratchpad/rev-bfam/sim_rules2.py`, 500 runs a case, the PR's own pooling): judged at
  every settlement at 80%, an edgeless family on 50c totals enters the swing by 30 / 50 / 200 real
  settlements 37% / 44% / 61% of the time. The table's "one-sided 80% lower bound" is honest only for
  one look. Chosen, inside the row: the entry is judged at 15 real settlements and every 5 after, at
  90% a look for both the t bound and the loss-rate gate (`family_swing.entry_every` 5,
  `entry_confidence` 0.9): edgeless 19% / 22% / 37%, near the stated 20% over the 30-50 settlements that
  matter; a real +14%/$ edge (sports-central-run-under measured +0.14) enters at a median 30 settlements
  instead of 20, a +8% edge at 40. Holding the swing and the doubling keep the 80% bound. Also: a
  family swings only when its pooled record is proven (P1) as well (the review found a real-only route
  to "proven"), and an audit approval lapses when the family leaves the swing. Rejected: an
  anytime-valid bound (about 3x wider at n = 30: real edges would need months) and leaving it (a
  money rule that swings on noise four times in ten repeats gap 2 at larger stakes).

## The scoreboard at T0

`scripts/gap_scoreboard.py --snapshot` on the T0 snapshot (ledger to 01:41:05Z; window the last 24 h;
PR #223, the full reading in `docs/research/queries/2026-09-24/Z-T0.txt`). The plan's baseline at
00:50Z in brackets.

| # | Metric | T0 | Target |
|---|---|---|---|
| 1 | Families with a positive real lower bound; capacity | 2 on real n of 2 and 5 (sports-central-run-under $56.65/day est., weather-favorites $7.81/day est.); 0 with ≥ 10 real events [1, ~$1/day] | ≥ 2, capacity measured |
| 2 | Allocator promotions to real money: settled result, share positive | 11 promotions, +$0.28 on 25 settlements, 3 positive (27%) [−$18.62 on 9, 0 positive] | every promotion since Deploy A a probe or a proven-family bunt |
| 3 | Real dollars in proven / unproven families; Alpaca real agents | $96.56 / $168.98; 0 now (1 ever) [$66 / $256; 0] | proven ≥ unproven; ≥ 1 Alpaca real agent |
| 4 | Median agent life (h), all / day-horizon; deaths before 3 fills | 14.38 / 19.83 h over 104 deaths; 69 (66%) [14.3 h; 68%] | ≥ 24 h day-horizon; < 30% |
| 5 | Lab batches an hour; LLM share of born graduates; waiters, longest; supersessions | 0 (34.25 an hour over the day, the last at 23:37:17Z); 2 of 18; 30 waiting, the longest 33.84 h (a card); 0 of 3 real-money parents with a passing research child [0; 2 of 18; 30 at 11 h; 0] | ≥ 30; ≥ 50%; 0 over 2 h; every corrected parent |
| 6 | Self-cross refusals of reducing orders (6 h); promotions on stacked positions | 26 (of 54 self-cross refusals); 4 of 11 [~85; 1] | 0; 0 |
| 7 | Recorders live on the allowed hosts; desks offered markets with no intent (48 h) | 0 of 12; 1 (alpaca-open) [0 of 12; 3] | a recorder for every allowed host a desk needs; 0 |

Also measured at T0:
- **The family records** (practice 0.5 + real 1, one observation an event, Student's t one-sided 80%):
  45 of 66 families have a closed trade; two are proven: **weather-favorites** (n 16, n_eff 14.2, mean
  +0.0050, lcb +0.0033; practice n 13 mean +0.0000, real n 5 mean +0.0159; all maker) and
  **sports-central-run-under** (meriwether-h2d625d's; n 11, n_eff 9.9, mean +0.0237, lcb +0.0058; all
  taker, so its taker record is positive). sports-central-over-under (meriwether-h7d7702's) has a high
  mean on 4 events and is not proven. Every crypto-15m family is negative (crypto-15m-favorites n 106,
  lcb −0.0064; crypto-15m-prior-window-reset n 30, lcb −0.0493).
- **The evidence clocks** (first fill to the third independent settlement, Kaplan-Meier median, last 7
  days): kalshi-crypto-15m 1.9 h, alpaca-crypto-alts 3.8 h, kalshi-crypto-strikes 4.4 h,
  alpaca-megacaps 4.4 h, alpaca-index-etfs 18.1 h, kalshi-sports 20.5 h, alpaca-options 23.9 h,
  kalshi-weather 31.8 h, kalshi-prices 36.5 h; not reached on kalshi-attention, kalshi-sports-props and
  alpaca-crypto-majors.
- **Weather favourites' capacity:** 26.5 markets bid a day, a real fill rate of 0.6 at bids up to $12
  (median $9.60), $0.49 a settlement: about $7.81 a day at today's size; its real seats earn about $1.41
  a day now.
- **Real-money parents with a replay-passing research child:** mullins-2 (children mullins-14, -18,
  -20), meriwether-h2d625d (child -2), huang-h51fdd3-2 (child -3; the parent is off real money).

## Progress notes

### T+4 (05:30Z Sept 24)

`scripts/gap_scoreboard.py --take` from `~/Work/ltcm-deploy` (ledger 437,170 rows to 05:28:53Z; window
the last 24 h; `docs/research/queries/2026-09-24/` keeps the T0 reading). Before Deploy A; the
scoreboard's family states use the t bound alone (the allocator adds the loss-rate gate from Deploy A:
the scoreboard follows in Wave 1).

| # | Metric | T0 | T+4 |
|---|---|---|---|
| 1 | Families with a positive real bound; capacity | 2 (n 2 and 5) | 4, none with ≥ 10 real events: sports-central-run-under n 5 (+$19.47 real, est. $103.61/day), crypto-strikes-lab-955dae n 5 ($22.93/day), weather-favorites n 5 ($7.93/day), prices-favorites n 2 |
| 2 | Allocator promotions: settled, share positive | 11, +$0.28 on 25, 27% | 12, +$7.26 on 46, 25% |
| 3 | Real $ proven / unproven; Alpaca real agents | $96.56 / $168.98; 0 | $117.10 / $103.98; **1** (haghani-56, since 02:17Z) |
| 4 | Median life all / day-horizon; deaths before 3 fills | 14.38 / 19.83 h; 66% | 12.06 / 13.32 h over 97; 55% |
| 5 | Lab batches last hour; LLM share; waiters | 0; 2 of 18; 30 at 33.84 h | 16 (the restarts let a few steps run before the poison row); 6 of 36; 10, the longest 37.64 h |
| 6 | Self-cross refusals of sells (6 h); stacked promotions | 26; 4 of 11 | 34; 4 of 12 |
| 7 | Recorders on allowed hosts; idle desks | 0 of 12; 1 | 0 of 12; 1 |

**State.** Wave 0 is built, reviewed and integrated: PR #240 merged at 05:27Z (main `9191e81`), the
gateway deployed at 05:25:59Z (`44edfee6`: the frontier month reports `settled_usd` $421.41,
`inflight_usd` 0); the House deploy with the ratify (money digest `c2b0e09c` → `521c4586`) follows at
05:36Z, ten minutes after the gateway. Wave 1: B-feeds (#234) and B-loop (#236) are ready; B-families
and B-seats are building. The floor ran under the T0 rules meanwhile: the 15-minute crypto bunts kept
losing (huang-h427345-2 demoted at 03:24Z), meriwether-h2d625d (the one family proven under Deploy A's
rules) made +$19.47 real, and the first Alpaca real agent (haghani-56) was seated. Compute at 05:30Z:
the OpenAI month $421.41 of $607; Sail about $168 (burn about $37 a day).
