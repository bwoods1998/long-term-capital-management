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
beside the deploys of their day, marked "no deploy". The run record (`docs/runs/2026-09-26-options-swarm.md`
on branch `run/options-swarm-2026-09-26`) has the detail.

## Not yet deployed

Main `3eaf4d06` is Release B, deployed Oct 1 (below). Under the freeze (Oct 1, "The freeze"), a change to
`league/live` or `league/gym` waits for a planned release. Merged since and waiting for a release:

- **The swarm window** (branch `b/site-rationale`): the publisher sends `levels` (each agent's level and the levels
  funnel since the reset) and `rationale` (each agent's thesis, and each real position's route, reasons, exit and maximum
  loss), pins every agent a real position names to the roster, and filters every mechanism against its program's
  parameter names. After its three reviews: a thesis, a tag, a note and a mechanism carry no number in any form (number
  words including ordinals, fractions and run-together numbers; "one" only as a pronoun; numerals of any script; no
  hidden format mark or look-alike letter; parameter names with hyphens or run together); the roster's mechanism and the
  birth news drop every sentence with a number (no entry window or threshold on the page); Tuition counts only families
  that held a tuition lot (its own branch of the funnel); a position's route is the band it was opened on; under the byte
  limit the window leaves before any agent or row, with 32 KiB left for the site's names (a 40-character name on each
  of 508 rows); the window is not read while the site refuses it. After the post-fix verification (Oct 1, 09:30Z): an
  apostrophe never hides a number word ("fifty's", "'twenty-day'", typographic quotes), accents fold away before
  reading ("twénty"), a word split by a mark joins ("twen·ty"), cardinal plurals, multiples ("quintuple"), "couple",
  "unity", "a score of", "-ish"/"-odd"/"-something" and "pct"/"bps" run together are numbers (`number_words.json` is the
  case list the site tests too); and a trade's `why` on the public tape (`agent.trade`, live today) is filtered by the
  same rules and the traded program's parameter names, or empty. Publisher and swarm-feed files only (`league/publish.py`, `league/site_window.py`,
  `league/trading_profit.py`, `league/swarm/public.py`, `league/swarm/sitefeed.py`, `league/swarm/hook.py`): nothing in `league/live`,
  `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest. Site first (personal-site
  `capital/swarm-window`); an older site gets the checkpoint without the window. To verify after the deploy: no "the site
  refused the swarm window" warning, and `curl -s
  'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1&practice=1&window=1'` shows `levels` and
  `rationale`.
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

## 2026-10-01

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
