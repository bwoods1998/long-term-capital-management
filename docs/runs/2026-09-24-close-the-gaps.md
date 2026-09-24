# Close the gaps to the north star — September 24, 2026

Execution record for the owner's goal of Sept 24, 2026: execute
[the close-the-gaps plan](../goals/LTCM_CLOSE_THE_GAPS.md) autonomously, with no deadline, until
every gap in its Done list is closed or recorded as blocked with numbers. The run happens outside
US market hours: anything that needs a stock or options session is built and deployed, then
recorded for the next open; live verification uses the markets that trade around the clock.

## The clock

- **T0:** 2026-09-24T01:34:02Z (the first action of the session, `date -u`).
- **T0':** 2026-09-24T15:04:54Z, the resumed run's first action (`date -u`), executing the plan's
  "Wave 3: the resume's order of work" (R0-R7) under the owner's /goal of the resume.
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

## The owner's message at the resume (Sept 24, 2026, T0')

- Resume the plan from origin/main, executing its "Wave 3" section (R0-R7), with no deadline, in
  the open US session (R4 uses it). Order: R0 re-baseline; R1 Deploy C first and verified in its
  first hour; R2 the seat market's capacity; R3 more real members of the proven family; R4 the stock
  and options session every 30 minutes; R6 the bugs seen at the resume, including the practice book
  freezing on a 3-cent difference; then the watch, docs, cleanup and the report.
- Authority: the plan's "Authorized" list and money-rule table, **plus one further money-digest
  change with a ratify of `earned-live-20260921` for R5** (no probe on a family whose pooled forward
  record is negative), if the evidence in this record supports it. "Not authorized" stays off-limits.

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
| D2 | Phantom OpenAI holds | **verified** 07:48:57Z: 48 holds ($86.86) released into the gateway month; the House line equals the month's ($166.93 at 08:32Z); the check race fixed in Deploy B (#246) |
| D3 | Exits walled off by the self-cross rule | live 05:37Z; **0 self-cross refusals** in the first hour (26 in the 6 h before T0); no exit has yet met a House bid (0 crosses, 0 re-prices) |
| D4 | Independent settlements | live 05:37Z (money digest `521c4586`) |
| P | Promotion on proof (probes, the one-loss trial, maker unless proven) | live 05:37Z; 05:44Z board: 1 proven-family bunt, 7 probes; lopsided gate adopted (04:15Z) |
| X0 | Book rules through constitution keys | live 05:37Z |
| Deploy A | Wave 0, ratified at promotion (digest change 1 of 2) | done: promoted 05:37:31Z, ratified 05:37:41Z on `521c4586`, watch passed 05:47:34Z |
| C1/C2 | The mechanism ledger and the family swing | live 08:31Z (Deploy B, #252): `family.record` rows, entry looks at 15 + 5k at 90%; to verify: rows and the board's families |
| S | The evidence clock and the seat market | live 08:31Z (Deploy B, #254); window 2 h: waiters toward 0, no displacement by a worse forward record |
| L | The loop's joints | live 08:31Z (Deploy B, #247 + L1 in #254); hourly: Sail research <= $2/h, Merton pauses, repeated warnings escalated |
| I | Feed recorders on the allowed hosts | live 08:31Z (Deploy B, #250); EIA and Odds wait for the owner's keys; to verify: `data.coverage` rows |
| X1/X2 | Pause and size-down tools; the horizon rule | reviewed and final (#258 `37b2ae8`: 11 of 12 fixed, X2 by the measured settle lag in the protected `resolution.py`); rides Deploy C |
| Deploy B | Wave 1, ratified at promotion (digest change 2 of 2) | done: promoted 08:30:59Z, ratified 08:31:09Z on `c02ed852`, watch passed 08:41:13Z |
| E | The lab as a search; the foundry brief; capacity | built (#262, 08:58Z), in review; rides Deploy C |
| C3 | Alpaca real money | haghani-56 (crypto-alts-reversion) is an Alpaca real agent since 02:17Z, a $25 probe since Deploy A; the rules-text line in C-search |
| W | The site's mechanism ledger | **verified** 10:14Z: site `a4d25790` (08:55Z), publisher shipped by the updater 09:35:40Z; the checkpoint carries families, the lab line and every desk's family state |
| Deploy C | Wave 2 | ⟨pending⟩ |
| R0 | Re-baseline at T0' (scoreboard, watch loop, events feed) | ⟨pending⟩ |
| R1 | Deploy C (`c/integration` + `c-search/review`), verified in its first hour | ⟨pending⟩ |
| R2 | The seat market's capacity | ⟨pending⟩ |
| R3 | More real members of the proven family | ⟨pending⟩ |
| R4 | The stock and options session, every 30 minutes | ⟨pending⟩ |
| R5 | The probe drain (the owner's third digest change, on evidence) | ⟨pending⟩ |
| R6 | Bugs seen at the resume (practice-book 3-cent freeze, earnings polls, kalshi-open, kalshi-sports) | ⟨pending⟩ |
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
- 06:50Z — **Wave 1 reviews, B-loop (#236) and B-feeds (#234):** three defects fixed on
  `b-loop/review` (#247) and `b-feeds/review` (#250), each with a test that failed before: Deploy A's
  House kept no record of repeating warnings, so a warning firing every tick through Deploy B's restart
  would have escalated inside the 10-minute watch and rolled Deploy B back (the House now seeds the
  runs from the ledger); the $2/h Sail research cap let queued jobs through as if already running (34
  were queued at once at 00Z); a backfill page made the hourly pass skip its key (an open-interest hour
  landed at 05:02 instead of 04:00). No point-in-time leak found; the reviewer broke every stamp on
  purpose and the tests caught each. Left PLAUSIBLE: a warning that starts during a watch now rolls a
  healthy release back after 10 repeats (by design of L3); daily rain totals may be shifted an hour.
- 07:00Z — **C-tools (#249) built** (X1 pause and size-down in place, X2 the horizon by the scheduled
  expiration, the stock/option wake skip; no protected file, no digest change). Its adversarial review
  started. Integration of Deploy B began on `b/integration` (`~/Work/ltcm-b-int`): #246, `b-feeds/review`
  and `b-loop/review` merged (two doc conflicts resolved), 157 tests of the touched modules OK.
- 07:10Z — **B-families (#242) review: four majors and five minors fixed** on `b-families/review`
  (#252): two newcomers seated into a swinging family in one pass were each lent the one-member share
  ($150 against a $50 cap); the family audit's verdict counted as one member's own approval (a free
  agent-level swing); Kelly per event was turned into a stake at the 20% position share while one event
  may hold 25%; the at-risk unit weighted every event alike, so a family that lost $44 over 100 events
  came out proven (now each event weighs what it put at risk); plus the grant's rung-3 check at every
  pass, an audit-request error no longer sweeps a proven family to probes, `family.record` rows only
  on a change (was ~10,000 rows a day), tests that mutations had slipped past, two doc errors.
- 07:15Z — **Decision on the family swing's entry (findings 10-12 of that review).** Measured by
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
- 07:25Z — **B-seats (#245) review: not safe as built; four majors and four minors fixed** on
  `b-seats/review` (#254). L1 would have retired meriwether-h2d625d, the floor's best real record
  (sports-central-run-under, the one proven family), on its first pass: the "defect" its child fixed
  was in a moneyline-favourites file the parent never ran (the plan's own L1 example misread the same
  pair). Now L1 counts only an account of the parent's CURRENT program, every route needs a claimed
  defect, and a liquidity or fee fix must be a program whose buys are post-only (read statically: 145
  of 145 post-only programs in the snapshot recognised); a move TO market orders no longer reads as a
  maker fix. Also: dust was valued at a $0.01 stub bid (a $6 LINK holding booked as dust); a trader the
  lab can never score (options) kept its seat forever; a stopped wind-down never retried; an admission
  that failed to seat its child cancelled the displaced author's retained candidate; a test that
  #242's key would break. On the T0 snapshot the fixed L1 supersedes no parent, so row 5's "real-money
  parents with a corrected child" starts at 0. Decided: L1 also skips a parent whose family's taker
  record is proven (X0 allows its taker entries); the reviewer is adding that, `seats_holding_none`
  in `floor_watch.py`, and checks of two more suspects.
- 07:40Z — **The swing-entry decision is built** on `b-families/review` (#252 at `7fe1703`, CI
  green): `proven` follows the pooled record alone and only a proven family swings; the entry is
  judged at 15 real settlements and every 5 after on the first that many real events, the t bound and
  the loss-rate bound both at 90%, the look derived from the real count (a restart cannot look early);
  holding and doubling stay at 80% on the whole record; an approval lapses when the family leaves the
  swing or a member rewrites its program after the audit began (and, being added, when a member is
  born into the family after it). 93c favourites now need 32 clean real events instead of 23. Money
  digest for Deploy B: `c02ed852` (constitution `915c978e`, the pinned one). On the T0 snapshot:
  sports-central-run-under proven (+0.1423), weather-favorites unproven (loss-rate bound -0.2112),
  nothing swings and no family has reached its first look (every real count under 15).
- 07:50Z — **The tick's cause found and fixed (#257).** The box's tick had slowed from 30-40 s at
  plan time to about 60 s. `auditor.order_outcomes`, called for every wake's snapshot, each research
  standing and each audit packet, re-read every `book.order` and `book.refused` row on the ledger:
  18,641 rows at T+4, 9.8 s a call through the `Ledger` on the owner's machine (first noticed by the
  C-tools builder). An index per House ledger folds the rows once and then only the new ones with the
  same rule: about 1 ms a call, 0 of 24 answers different from the full read on the T+4 snapshot;
  tests hold the index equal to the full read on random interleavings, and each of three sabotaged
  rules fails them. Protected (`auditor.py`): rides Deploy B. The scoreboard gained the House's own
  family record (it had called four families proven where the allocator proved one), the deaths of
  agents that held a practice seat (row 4), and the evidence clock without the House's closing sales.
- 08:16Z — **Deploy B integrated** (`b/integration`, PR #260): #246, `b-feeds/review`, `b-loop/review`,
  `b-seats/review` (with the four follow-ups: L1 skips a parent whose family's taker record is proven,
  the evidence clock without the House's closing sales, the dust rows written as one group,
  `floor_watch.py` showing the seat market), `b-families/review` (`761e267`), #257, the scoreboard
  and main. Money digest `c02ed852` (constitution `915c978e`, pinned). The first full local run, before
  the last merges: league 2,884 tests with one module over its 20-minute limit (`test_ladder`, a
  simulated House over hours; it timed out the same way before Deploy A and passes in CI), ltcm 1,852,
  no failure. C-tools (#249) stays out: its review was still running at the cut; it rides Deploy C.
  Wave 2 (C-search, C-site) was started at 07:50Z from the integration branch, so it builds on Deploy B.
- 08:23Z — **C-tools (#249) review: twelve defects, eleven fixed** on `c-tools/review` (#258). Its
  majors: a pause or resume counted as a new strategy (it cancelled the agent's waiting candidate,
  dropped an audit in flight and set an approval aside); an in-place edit bought a fresh 12 h seat grace
  and wiped the agent's trading record for the seat market; "one edit replay a day" read only the
  newest 400 research rows (26 agents write 400 inside a day); resting buys stayed up for up to a day
  after a pause (a bid filled an hour after one); an audited swing raised its notional in place. And
  X2 changes nothing on the venue's real rows: every cached market carries `expected_expiration_time`,
  and for diesel and the token/share weeklies it is the week-out deadline although they paid within
  12 h of close, so the 71 diesel and 62 other refusals would continue. Decided: the horizon judges
  such a series by its close plus its measured settle lag (the p95 over its last 20+ settled markets,
  from the House's own cache, no look-ahead in replay); a paused agent is not promoted, is not active
  for the seat market or the stuck rule, and after 24 h paused its idle real stake shrinks toward the
  probe by free cash. `allocator.py` and `evaluator.py` change (code only, no digest move): #258 rides
  Deploy C. The wake skip was found sound (holidays, half days, a failed calendar).
- 08:26Z — **Deploy B merged** (PR #260, CI green on `3a80182`: gateway, tests 3.11 and 3.14). The
  first owner deploy was REFUSED at 08:26:49Z: the in-box updater was watching a release of its own.
  Since Deploy A the updater had shipped Merton's strategy commits twice (`main-771488ad8fc2` at about
  07:44Z, `main-6bd75939a291` promoted 08:19:15Z, verdict 08:29:15Z), each a House restart. The deploy
  went again at 08:29:39Z.
- 08:30:59Z — **Deploy B promoted** (release `20260924T082939Z-019dd23442a9`, main `3faf146`) and
  **ratified 10 s later** on money digest `c02ed852` (08:31:08-09Z; 101 seats at the $10 probe). The
  first health at 08:32:16Z: grant active on `c02ed852`, 112 living, no book frozen; the OpenAI line
  $166.93 left, equal to the gateway month's (cap $607, spent $440.06), $0.08 pending.
- **D2 verified.** The first OpenAI "holds absorbed" row was at 07:48:57Z, under the updater's release
  of Deploy A's code: 48 holds with no response, $86.86, released when the House's settled calls since
  the anchor and the gateway's growth were equal to the cent ($13.74). The race #246 fixes made that
  moment rare; it now compares only calls the reading must hold.
- 08:41:13Z — **Deploy B's watch passed** (DEPLOY-EXIT 0). At 08:41Z: grant active on `c02ed852`, 112
  living, no book frozen, no repeating warning, no health failure, tick 51 s. `family.record` rows for
  49 families (sports-central-run-under proven, n 19, at-risk bound +0.204, stake $30). Recorders
  reporting coverage: weather, nws, rates, treasury, odds, tsa current; forecast, earnings,
  earnings_date, oi partial (backfilling); polls unavailable (RCP's bot wall, as designed);
  `consensus` (The Odds API) and `eia` waiting for the owner's keys. Merton: no role paused (real
  P&L +$13.88 over 58 settlements in 24 h). L1's first pass superseded two practice parents whose
  children fixed a taker entry: haghani-37 (19 of 19 entry fills takers, crypto-alts-reversion,
  negative pooled record) and huang-l55a341 (1 of 1). L1 as reviewed applies to practice parents too
  (the plan's text names real-money ones); both supersessions are within its rule. The board carries
  `capacity` per agent. The final head's full local suites: league 2,896 tests, ltcm 1,853, 0 failures.
- 08:43Z — **Cleanup after Deploy B:** 11 merged worktrees and 12 merged branches (local and origin)
  removed, the merged `ltcm-hosts` worktree and `ops/feed-hosts` branch too; 50 merged local branches
  of earlier runs deleted; two unmerged branches that existed only locally
  (`astra/teacher/first-night-of-replays-ec3f3563`, `night/tick-never-blocks-e1-local`) pushed to
  origin. The main checkout fast-forwarded to `3faf146`; its untracked
  `docs/goals/LTCM_OVERNIGHT_GOAL.md` (Sept 21) is left for the owner.
- 08:53Z — **C-site built** (W, C4): personal-site #7 (schema: a desk's `family_state` and `family_n`,
  the board's `families` {unproven, rows} and `lab` {tested_last_hour, graduates_waiting}, exact and
  bounded; the page: the readout names the family and its state and settlements, a "Proven edges" list
  with the unproven count, one quiet lab line, and each birth and death with its cause in fixed plain
  phrases) and league #261 (`publish.py`: the proven families with their HONEST bound — the lower of the
  t bound and the loss-rate bound, so weather favourites would show -0.2112, not +0.0033 — and the lab
  line from the newest `lab.stats` row). Tests: site 81 (78 before), publisher 41 (29 before), three of
  them running the site's validators in node on Deploy B's real board. The owner's words to review:
  "compounding" for a swinging family, "lower bound", the seven death causes.
- 08:55Z — **Site deployed first** (personal-site `301e6a1`, Cloudflare version `a4d25790`), the live
  checkpoint of 08:55:30Z still accepted; then #261 merged (main `3ceb5d6`), unprotected, so the in-box
  updater ships it once main's CI passes on a quiet head. To verify when it ships: `board.families`,
  `board.lab` and the desks' family fields in `/api/capital/checkpoint`, the checkpoint staying fresh.
- 08:58Z — **C-search built** (E1-E3, C3's line; PR #262, CI green; `lab.py` protected, no digest
  change). Measured on snapshot copies, first 15 steps after a restart: T4 89 candidates (1.48 a batch)
  before, 444 (6.83 a batch) after; T0 80 (1.33) before, 464 (7.03) after. Graduation now needs a
  mechanism change beyond PARAMS or a forward score above the desk's living median (a winning own
  window where no resident has a ranked score: 2 of 112 residents had one at T4); a desk idle 48 h
  graduates nothing until a feed it asked for arrives; breeding weighs the parent's forward window;
  no search on a family at capacity; cards must state their fee and the edge they need; no card for
  crypto-strikes or crypto-15m until a family there is positive over 3 forward blocks; the weather
  favourites' ensemble transfer. At T4 the waiting list of 8 becomes 5 graduating, 2 held as nudges,
  1 held on a losing window. Options: no replay on that desk, so no card can be admitted there (a
  House admission-rule change, not built). Its adversarial review started 08:59Z.
- 08:57Z — **The board shows the honest bound** (`c-board/honest-bound`, 82855e9; C-site's finding):
  `family_bound` was the t bound alone (weather favourites +0.0033 against its proof's -0.2112); a
  test fails without the fix. `allocator.py`: rides Deploy C.
- 09:08Z — **C-tools follow-ups done** on #258 (`a8e8178`, CI green on the first attempt; merged with
  Deploy B's main). X2 by the measured settle lag: a market whose expected expiration lies 48 h or more
  after its close is judged by its close plus its series' p95 settle lag (last 40 settled markets, 20
  needed, only settlements known before the day: no look-ahead in replay), never before the close nor
  after the deadline; one function for the book, the House, the live view and replay. Measured: diesel
  daily p95 5.86 h over 347 settlements, weekly 7.79 h over 51: all 71 diesel refusals of the T0 window
  and the 8 diesel-weekly ones would have been admitted (7-40 h out instead of 171-202 h); the share and
  token weeklies (7-9 settlements) stay refused; 74 of 1,683 cached series change answer. The box's
  lags start empty, so diesel stays refused until its tapes record 20 settled markets. Pauses: no
  promotion while paused; after 24 h paused a real stake falls toward the probe by free cash; held buys
  are not activity; a resident paused past its grace is displaceable. Asked next: the horizon's answer
  moves into a protected module (the book is protected but read `tapes.py`, which an updater release
  could change), and the seat report counts a long pause as holding no evidence.
- 09:27Z — **C-tools final** (#258 at `37b2ae8`, CI green first time): the horizon's answer lives in
  `league/resolution.py`, added to `ci.FORBIDDEN` (the book is protected; the module it reads now is
  too, so an updater release cannot change what the book admits). `settle_lags.json` stays House-written
  data read as untrusted: entries that are not three finite times, settled before their close or
  without a real deadline are ignored, each lag is clamped to [0, its deadline], a series needs 20 good
  settlements. This closed a hole in the previous head: a file of negative lags read as 0 and admitted
  the diesel print. Tests: a hostile file leaves diesel refused at 172 h in the House and the book; an
  honest one admits it. The seat report counts a long-paused trader as holding no evidence.
- 09:37Z — **A live defect in Deploy B's seat market: displacement chains.** Since 08:31Z, 6 of 12
  deaths were newborns displaced 33 s to 14 minutes after birth by the next evidenced waiter (the
  alpaca-crypto-alts chain haghani-ld3630c → haghani-lbf6075 → haghani-ladcac2 → haghani-64;
  kalshi-crypto-15m huang-l5aa23e-3 and huang-h6d3302-3), each "traded 0 blocks forward". Cause: in
  `House._displaceable`, an evidenced newcomer may take a never-traded rung-1 seat with NO grace (the
  Sept 23 rule), and a graduate seated a minute earlier has never traded; Deploy B's 24 retained
  candidates added evidenced waiters. The fix (`c-seats/fair-chance`, being built): the shortcut only
  after a fair chance, the desk's evidence clock capped at the plain grace, never under an hour.
- 09:56Z — **C-perf built** (#263, CI green; unprotected). `health.json` `tick_steps` books every moment of
  the tick to a named step (last tick, the hour's eight slowest, each background lane's last job), and
  `floor_watch.py` prints them. A fully settled Kalshi day is now read from History once per process
  (a bounded LRU of the fields the tape reads, at most about 140 MB; the box has 4.0 of 5.8 GB free and
  the House holds 1.65 GB): the second build of a 14-day four-series tape went from about 80 to 19.5
  CPU-seconds (98.8M function calls to 29.8M; `parse_market` 294,864 calls to none), and History logs
  only pages it fetched. Merged into `c/integration` with C-tools and the board's honest bound.
- 09:45Z-10:14Z — **Merton's two stuck repairs merged** (#217 the longshot guard, #208 refusal memory for
  Huang's BTC 15-minute child). They had failed CI since Sept 23 on the CI tape's missing
  `observed_bars`, fixed in Deploy B's `league/ci.py`. A close-and-reopen first re-ran CI on a stale
  merge ref; the judge job runs `league.ci` from the PR branch's own checkout, so `gh pr update-branch`
  gave it the fixed CI code; Merton's judge then passed both and merged them itself.
- 09:35:40Z — **W verified.** The updater shipped the publisher (#261) as `main-e4bb1962d296` (promoted
  09:35:40Z, verdict 09:45:43Z). The live checkpoint at 10:14:22Z carries `board.families` (the proven
  family sports-central-run-under: bound +0.204, capacity $56.93 a day, stake $30, one real member;
  47 unproven), `board.lab` (715 tested in the last hour, 15 graduates waiting) and the family state on
  all 112 desks; blakewoods.us/capital shows them.
- 09:56Z — **The seat fix built** (#265, CI green): the evidenced shortcut waits for a fair chance since
  the seat's program's opportunity (its desk's evidence clock capped at the plain grace, never under an
  hour: 3.7 h crypto-alts, 2.8 h crypto-15m, 12 h prices/sports/weather, 1 h without a clock). Measured
  on the T+8 snapshot: 9 of the 12 deaths since Deploy B prevented (every never-traded paper seat taken);
  3 of those newcomers would have taken idle seats past their chance (alpaca-open and crypto-majors
  coin programs never traded in 1.9-7.1 h), 6 would have waited; the two L1 supersessions and a
  replay-only seat whose replay had failed are unchanged. Merged into `c/integration` (composed with
  C-tools' rule that a long pause counts as idle).
- 10:22Z — **A flaky CI test was a real race** (`c-fix/dispatcher-stop`, a0d6c0e): the strategy
  dispatcher's `stop_dispatcher` joined its loop thread but not the runs it had handed to the pool, so a
  run kept writing the store after stop; in CI that raced `DispatcherTests`' temporary directory three
  times today ("Directory not empty"). Stop now waits, bounded at 5 s, for the runs in flight and
  leaves their results for the next tick. A test fails without it; the module passed three runs in a row.

### Wave 3 (the resume, from T0' 15:04:54Z)

- 15:01:06Z — The in-box updater shipped `main-0e1aec8b9e98` (the plan's Wave 3, #269, and Merton's #270 child);
  its watch passed at 15:10:06Z.
- 15:06Z — **R0, the scoreboard at T0'** (`gap_scoreboard.py --take --baseline 2026-09-24T05:37:31Z`; ledger
  526,226 rows to 15:05:38Z): (1) 1 proven family, sports-central-run-under, real n 5, pooled n 19, bound
  +0.204, capacity $82.17/day; (2) 9 promotions since Deploy A, all probes, −$6.07 on 8 settlements, 0
  positive; (3) proven $20.06 / unproven $168.94 on the board's `stake_usd`, 3 Alpaca real agents; (4) median
  life 5.84 h (day-horizon 5.09 h), 92 of 140 deaths (66%) before 3 fills, 132 of them displaced; (5) 71 lab
  batches in the last hour, 14 of 54 graduates LLM-written, 56 waiters (41 graduates, 15 cards), the longest
  47.25 h; (6) 0 self-cross refusals of reducing orders; (7) 9 of 12 recorders, kalshi-open idle (255 markets
  offered over 4 wakes, no intent). Tick 85-200 s. The watch loop (events every 5 min, `floor_watch.py` every
  15 min, the stock desks every 30 min in the session) started 15:08Z.
- 15:20Z — **R6's freeze measured:** `alpaca-paper` read −$0.0322 at 14:39:07Z and stayed frozen until
  14:51:06Z, when more fills raised the tolerance (one cent a fill) and −$0.0352 was booked as dust. The same
  shape adopted the venue after three failed readings on Sept 21 (−$0.1436), Sept 22 (−$0.0200) and Sept 23
  (−$0.0326), each near 19:30-20:10Z. Builders launched at 15:26Z from `c/deploy`: R2 seats (`r2/seats`), R5 and
  R3's board (`r5/family-probe`), R6 bugs (`r6/bugs`).
- 15:22Z — **The proven bunt's stake was never short.** The board's `stake_usd` is the net loan after profit
  sweeps (`account.staked`), not equity: meriwether-h2d625d was lent $10 (Sept 23 12:50Z) and $20 (22:30Z),
  then swept $0.47, $8.99 and $0.48 as its equity ran over the $37.50 target ($43.54 at 04:37Z, $46.49 at
  04:49Z, $41.67 at 12:40Z): net $20.06. The resume's "stake $20.06 against a $37.50 target" read the loan as
  the stake; the lend-up works. The board gains `equity_usd` beside it (R3).
- 15:22Z — **R5's evidence** (on the 15:06Z snapshot; `r5_evidence.py`: each allocator promotion to rung 2
  since Sept 23 00:00Z, its family's pooled forward record at that moment by `House.family_forward`'s
  definition, and the stay's realized real P&L): 11 promotions onto families negative over 6 or more active
  blocks made **−$8.12 on 22 closes, none positive** (haghani-56 on crypto-alts-reversion at 241 blocks
  −0.1779; huang-h427345-2 at 17 blocks −0.4677; hilibrand-h6ca596-3 at 8 blocks −0.4422; ...); the other 10
  made +$28.96 on 34 closes (the two sports agents +$35.77; three 15-minute crypto bunts −$11.66). At 15:06Z
  seven of the twelve seated probes, $115 of real money, sat on such families: huang-l5aa23e and
  huang-l0c6f38 (crypto-15m-lab-335592, 20 blocks −0.4346), huang-h51fdd3-6 (crypto-15m-doge-flat-spot-no, 26
  blocks −0.4835), huang-h427345-4 (crypto-15m-prior-window-reset, 24 blocks −0.7121), and haghani-62,
  haghani-r42c38c and haghani-63 (crypto-alts-reversion, 336-345 blocks −0.06 to −0.11). The evidence
  supports the owner's third digest change: R5 is built (`r5/family-probe`).
- 15:27Z — **R4 at the first reading** (the loop's 14:38-15:08Z window and the 15:06Z board): the four stock and option desks woke 68 times, wrote 11
  intents and got 3 practice fills; 4 equity entries were refused by the practice-book freeze (R6). On the
  15:06Z board, 39 stock and option agents live; 2 have 5 or more closed trades (scholes-21 8 trades, E
  0.9981; mcentee-hddb4ae 7, E 1.0004); options and alpaca-open have none; the best E is 1.0341 on 0 closed
  trades. All 20 equity orders since the open were market orders: no agent has sent an equity limit order,
  so A7's fractional `day` limit path has no live instance to verify.
- 15:28Z — **R1: Deploy C merged and deploying.** `c/deploy` = main + `c/integration` + `c-search/review`, both
  merges clean (9f20640, 15:08:30Z); the money digest is `c02ed852` on both sides (constitution `915c978e`), so no
  ratify. Local parallel run: one timing flake under 7-way load (`test_tick_steps`, a 1 s slow step beaten by
  a loaded first payout; R6 hardens it). PR #272 opened 15:19:14Z; CI green on both Pythons at 15:28:09Z (run 36019308936); merged
  15:28:17Z (main `9807eec`); owner deploy from `~/Work/ltcm-deploy` at 15:28:31Z, release
  `20260924T152831Z-4c7a6f088c6d`.
- 15:39:27Z — **Deploy C rolled back, by the practice-book freeze, not by its code.** The canary passed
  (15:28:37-15:37:57Z, about 9 minutes on the busy box), the release was promoted at 15:37:57Z, and the
  watch's reading 3 at 15:39:27Z failed on "the alpaca-paper book is frozen: cash differs by -0.0269": the
  box went back to `main-0e1aec8b9e98`. The freeze began at 15:37:27Z in the OLD House's last tick, which
  wrote its health (dated 15:35:14Z) after the reading taken before the promotion, so the watchdog's
  inherited-freeze rule (Sept 19) did not see it; the new House had not finished a tick, and all three
  readings (193-253 s old) read the old process's file. The in-box updater then refused `main-c7bee60611db`
  (main after #272) at 15:41:21Z: protected files are the owner's deploy. The practice book froze again at
  15:47:36Z (−$0.0328), about every ten minutes in the session.
- 15:57Z — **Two fixes before the retry.** (1) `r1/watchdog-inherit` (`07d0761` 15:54:28Z, `94a01b8` 15:57:16Z; `watchdog.py`): the
  watch counts a frozen book only in a `health.json` dated at or after the House's first `ops.started` since
  the promotion; before it the freeze is `frozen_by_previous_process`; staleness, `restart_within`, a
  canary's judgement and an undatable restart still count; five tests, three fail without the fix (90 in
  the module pass). The OLD release's watchdog runs each deploy, so this protects the deploys after the one
  that ships it. (2) R6's practice-dust fix first and alone (`r6/practice-dust`): the new House must not
  freeze on a sub-dollar practice difference during its own watch. Deploy C is retried with both.

- 15:58Z — **R6's freeze explained** (#273, `r6/practice-dust`, 514e5cf): the cents are the OCC clearing fee
  Alpaca takes at an option buy's fill (about $0.03 a contract; listed as a FEE activity only the next
  morning, so `_book_venue_fees` cannot see it yet), maker-fee refunds against the book's taker assumption
  (+$0.03 at 15:27:53Z: haghani-56's AVAX sale charged $0.04 against $0.07) and rounding. -$0.0322 at 14:39Z
  and -$0.0328 at 15:47Z were krasker-14's AAL buys, -$0.0269 at 15:37Z krasker-6's. Today's freezes refused
  11 Alpaca practice entries. The fix: a practice book's cash difference under $1.00, with every position
  agreeing and no order in doubt, is booked as House dust at once; real books keep the freeze.
- 16:03Z — **The drain goes on:** huang-h51fdd3-6 (a $10 probe on crypto-15m-doge-flat-spot-no, 26 blocks
  -0.4835 at its seating) lost $1.20 on an XRP 15-minute contract at 16:00:36Z and was demoted at 16:03:31Z.
- 16:09Z — **R4, 15:08-15:38Z:** 73 stock and option wakes, 8 intents, 8 practice fills (7 equity, 1 option),
  no refusal. **A7 has no instance by the agents' own choice:** of the living programs, 0 of 14 index-ETF and
  0 of 12 megacap programs write a limit order (all market), 1 of 5 alpaca-open programs does, all 8 options
  programs do.
- 16:20Z — **CI's 3.14 job at its limit:** Deploy C′ (#274 = main + `r1/watchdog-inherit` + `r6/practice-dust`,
  opened 15:58Z) passed 3.11 in 9m07s but 3.14 was cancelled at the 10-minute limit twice (15:58:41-16:08:56Z
  and the re-run 16:09:28-16:19:43Z). The lasting fix rides C′ (`0245d76`): the tests job gets 20 minutes, and
  `TRUSTED_WORKFLOWS_SHA256` in `league/updater.py` follows the workflow file (the running updater refuses
  main heads with the new workflow until C′ lands, and trusts them after it).
- 16:42:49Z — **R1: Deploy C′ live.** PR #274 CI green at 16:30:45Z (3.14 in 10m03s under the new 20-minute
  limit), merged 16:31Z (main `84e1d0f`); owner deploy at 16:31:19Z, release `20260924T163119Z-cb03f8aa33a8`,
  canary 76 s, promoted 16:32:40Z, watch passed (verdict 16:42:49Z); no ratify (money digest `c02ed852`).
  The watch's readings 1-2 read the old House's file (16:29:41Z, 208-238 s old, nothing frozen); the new
  House wrote its own at 16:33:50Z and every later reading was its own. This watch was still the OLD
  watchdog's; the next deploy is judged by the fixed one.
- 16:43Z — **R1's first readings** (verifyC.py on the box, from 16:32:40Z): `tick_steps` in health (last tick
  90.7 s: research 15.4 s, wakes 12.1, publish 10.2, poll:kalshi-shadow 8.0, mark:alpaca-paper 7.5,
  hypotheses 6.3); tick 87.6 s, not yet under 60. Waiters 82 → 66: lab graduates 41 → 23 as E1 holds 16 of
  them as parameter nudges (crypto-strikes 11, weather 3, sports-props 1) and one on a losing forward window
  (megacaps). X1 verified: agents edited their own parameters in place (`control: edit_params`:
  hilibrand-l98e85b's risk_fraction 0.05 → 0.12 at 16:36:32Z because 5% of a $10 probe is below one contract;
  haghani-l22bffc's spread cap 0.4% → 0.8% at 16:37:56Z after 30 idle wakes). kalshi-open's member
  diagnosed its own idleness ("none of their four NFL series is currently open in the six-hour window") and
  rewrote itself at 16:36:40Z. One death: krasker-6 (options-pullback, 12 fills, forward −0.0726) displaced by
  krasker-3's retained candidate (S3). The three cards at 16:35:19Z are the engineer's repair cards for three
  real-money agents' refusals, not foundry search cards. `settle_lags.json` holds 2 series, no diesel yet.
- 16:47:37Z — **The first Alpaca options agent on real money is a probe on a losing family.** The allocator seated
  krasker-14 (alpaca-options, options-pullback; E 1.0238 on 5 closed trades) as an $80 probe (an options probe is
  held up to `option_bunt_usd`). The family's record at 16:53:40Z: 19 active practice blocks, growth −0.383
  (losing by `families.losing`), bound −0.109, n 28. It is inside the envelope and has sent no real order yet;
  R5 refuses exactly this, and its builder has the case (a demoted options probe must never be sold at market or
  outside the session). Alpaca real agents: 4 (three crypto-alts probes, all on a losing family, and this one).
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

### T+8 (09:34Z Sept 24)

`scripts/gap_scoreboard.py --take snap/T8 --baseline 2026-09-24T05:37:31Z` from `~/Work/ltcm-deploy`
at `3faf146` (ledger 475,400 rows to 09:34:23Z; window the last 24 h). The first reading made through
the House's own family record (`HouseRecords`, Deploy B): the scoreboard and the allocator now agree
that one family is proven.

| # | Metric | T0 | T+4 | T+8 |
|---|---|---|---|---|
| 1 | Families with a positive real bound; capacity (proven by the House's pooled record) | 2 (n 2 and 5) | 4 on t bounds alone, none with ≥ 10 real events | **1**: sports-central-run-under, real n 5, bound +0.291 a dollar at risk, capacity $94.57/day; the House's proof agrees (pooled n 19, +0.204) |
| 2 | Allocator promotions since Deploy A: settled, share positive | 11, +$0.28 on 25 | 12, +$7.26 on 46 | 0 promotions since 05:37:31Z (no unproven mechanism promoted) |
| 3 | Real $ proven / unproven; Alpaca real agents | $96.56 / $168.98; 0 | $117.10 / $103.98; 1 | $20.54 / $122.35 (seven probes still shrinking to $10 by free cash); 1 (haghani-56) |
| 4 | Median life all / day-horizon; deaths before 3 fills (seated) | 14.38 / 19.83 h; 66% | 12.06 / 13.32 h; 55% | 9.59 / 5.79 h over 124; 61% (seated: 118, 59%). Since Deploy B: 12 deaths, median 0.28 h — the churn below |
| 5 | Lab batches last hour; LLM share of born graduates; waiters | 0; 2 of 18; 30 at 33.84 h | 16; 6 of 36; 10 at 37.64 h | **106**; 14 of 50 (28%); 23 (14 graduates, 9 cards) at 41.73 h |
| 6 | Self-cross refusals of sells (6 h); stacked promotions | 26; 4 of 11 | 34; 4 of 12 | 8, **all before Deploy A** (0 since 05:37Z); 0 of 0 |
| 7 | Recorders on allowed hosts; idle desks (48 h) | 0 of 12; 1 | 0 of 12; 1 | **9 of 12** (RCP refuses bots; api.open-meteo.com and efts.sec.gov unused: their sibling hosts serve the feeds); **0** |

**State.** Deploy B went live at 08:30:59Z and was ratified 10 s later on money digest `c02ed852`, the
run's second and last digest change; its watch passed at 08:41:13Z. The first owner deploy had been
refused because the in-box updater was watching a release of its own. D2 is verified: 48 phantom
OpenAI holds ($86.86) were released at 07:48:57Z, and the House line equals the gateway month. The
site's mechanism ledger is deployed (`a4d25790`). Its publisher (#261) is merged and ships with the
updater. Wave 2 is in review or building: C-tools final (#258), C-search (#262) in review, C-perf
building, and the board's honest bound (`c-board/honest-bound`). Two live defects were found since
the last note:
- The House re-parses the same settled Kalshi listings about 24 times in 30 seconds while running at
  74% CPU, with a 51-64 s tick. C-perf is fixing this and adding step timings.
- Deploy B's seat market chains displacements. An evidenced newcomer may take a never-traded seat
  with no grace, so graduates displace the previous newborn within 33 s to 14 minutes (6 of the 12
  deaths since 08:31Z). The fix is in progress (`c-seats/fair-chance`).

Compute at 09:37Z: the OpenAI month is at $442.50 of $607, with $164.50 left and $2.40 settled in the
last hour. Sail has $165.44 on the House line and burned about $2.60 in four hours under the $2/h
research cap (it was about $37 a day before).

### The resume (14:30Z Sept 24, in the US session)

The session that ran this record was cut off in the night after the T+8 note; the owner resumed
at 14:26Z during the stock session. Read on the box at 14:24-14:35Z (the scoreboard's reading and
the numbers are in the plan's new section "Where the run stands at the resume"):
- The floor runs `main-786bc2285e1a` (Deploy B plus Merton's #208, #217, #264, #266-#268 shipped
  by the updater at 11:46Z); the grant is active on `c02ed852`; 112 living; no book frozen; the
  floor's real P&L +$10.66 marked, the first positive reading since the grant (today's realized
  Kalshi +$22.02: meriwether-h2d625d +$19.47 on 5, meriwether-h7d7702 +$16.30 on 1; the five
  15-minute crypto probes −$27.29 on 23). Three Alpaca crypto-alts probes since 13:29Z (haghani-62,
  haghani-r42c38c, haghani-63; resting SOL and XRP limit buys, no fill yet).
- **Deploy C never shipped.** `c/integration` (36 commits) and `c-search/review` (8 review fixes)
  existed only on this machine; both were pushed at 14:33Z. They merge cleanly (`merge-tree` exit
  0); no money rule changes; owner deploy, no ratify.
- The scoreboard at 14:28Z: 1 proven family (real n 5, capacity $83/day); 9 promotions since
  Deploy A, all probes, −$6.07 on 8; proven $20 / unproven $169; median life 5.8 h, 66% of 140
  deaths before 3 fills (26 of the last 32 displaced without a fill: the chain #265 fixes);
  lab 101 batches an hour, 14 of 54 graduates LLM-written, 53 waiters at 46.6 h (28 of them for
  the 4-seat `kalshi-crypto-strikes` desk); 0 self-cross refusals; 9 of 12 recorders, `kalshi-open`
  idle. Tick 95-175 s (C-perf is in Deploy C).
- The plan gained a "Wave 3" section (PR #269) with the resume's order of work.

### T+16 (17:27Z Sept 24; the resumed run's first note, T0' + 2:22)

`scripts/gap_scoreboard.py --take snap-T16 --baseline 2026-09-24T05:37:31Z` from `~/Work/ltcm-deploy` at `84e1d0f`
(ledger 547,400 rows to 17:27:42Z; window the last 24 h; release `20260924T163119Z-cb03f8aa33a8`).

| # | Metric | T0 | T+8 | T0' (15:06Z) | T+16 (17:27Z) |
|---|---|---|---|---|---|
| 1 | Families proven (House record); real-bound families; capacity | 2 (n 2, 5) | 1 | 1; 1, $82.17/day | **2**: sports-central-run-under (pooled n 19, real n 5, bound +0.204, $77.79/day) and megacaps-chip-demand-relay (pooled n 10 practice, bound +0.0016, $0.46/day, no real member); 1 real-bound |
| 2 | Promotions since Deploy A: settled, share positive | — | 0 | 9 probes, −$6.07 on 8, 0 | 10 probes, −$6.65 on 12, 2 positive |
| 3 | Real $ proven / unproven (board `stake_usd`, the net loan); Alpaca real agents | $96.56 / $168.98; 0 | $20.54 / $122.35; 1 | $20.06 / $168.94; 3 | $20.06 / $238.94; **4** (krasker-14's $80 options probe) |
| 4 | Median life all / day-horizon; deaths before 3 fills | 14.38 / 19.83 h; 66% | 9.59 / 5.79 h; 61% | 5.84 / 5.09 h; 66% | 5.21 / 5.09 h over 140; 66% (24-h window; since Deploy C′ at 16:32:40Z: 3 deaths, 0 before 3 fills) |
| 5 | Lab batches last hour; LLM share of graduates; waiters, longest | 0; 2/18; 30 at 33.8 h | 106; 14/50; 23 at 41.7 h | 71; 14/54; 56 at 47.3 h | 70; 14/56; 40 (23 graduates, 17 cards) at 49.6 h |
| 6 | Self-cross refusals of sells (6 h); stacked promotions | 26; 4/11 | 8; 0 | 0; 1/9 | 0; 1/10 |
| 7 | Recorders; idle desks | 0/12; 1 | 9/12; 0 | 9/12; 1 | 9/12; 0 |

**State.** Deploy C shipped at the second attempt: the first (15:37:57Z) was rolled back by a practice-book freeze the
old House recorded (the watchdog judged the old process's file); Deploy C′ (#274, with the practice-dust fix #273, the
watchdog fix and CI's 20-minute tests job) was promoted at 16:32:40Z and passed its watch. **R1 in its first hour
(16:32:40-17:23Z):** `tick_steps` live; the lab holds nudges and losing windows (graduate waiters 41 → 23); agents use
the in-place parameter edit (16 `edit_params` rows); L1 superseded london-l440e61 by its fee-fixed child at 17:11:05Z;
the foundry wrote its first open-desk cards (kalshi-open, 17:15Z); 3 deaths, none before 3 fills, no newborn displaced;
no practice freeze (3 dust rows booked). **Not met:** the tick, 43-67 s after the restart, then 87-173 s (the hour's
slowest steps: publish 87.7 s, population 67.7, schedule 52.3): a perf builder profiles it on the T+16 snapshot
(`r6/perf`). Diesel's horizon judge waits for its lags (2 series recorded). In review or building for Deploy D: R2 and
R3 (#276, the seat market's capacity and the proven family's births; its review `r2/review`), R5 (`r5/family-probe`,
the third digest change), R6 (#278 practice option fees in `book.py`; #279 earnings timeout, idle-desk counts, the
tick-steps flake). Real money: Kalshi +$22 realized today (the sports and crypto-strike families +$49.41, the 15-minute
crypto probes −$28.49); since T0' one more probe was seated on a losing family (krasker-14, $80 on options-pullback,
19 blocks −0.383) and one seated before it lost again and was demoted (huang-h51fdd3-6, −$1.20). Compute at 16:37Z: OpenAI $471.76 of $607; Sail
$160.76 (runway 4.5 days).
