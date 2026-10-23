# PREREG-EVL-10: READER-2, a stronger reader of the news and 8-Ks the slots can trade, with one consumer seat, real money at learning size from its first live decision

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6e6a85b9) under the owner's goal as he re-set it at about
04:40Z Fri Oct 23, 2026 (goal V3, `goal-2026-10-19/GOAL-MESSAGE-V3-DRAFT.txt`; the captain's A138): "every seatable
program trades real money from its first event at up to 5% of equity a position ... promotion, demotion and retirement
are pre-registered sequential tests in settled events at a false-positive rate <= 25% per test by issuer-block
permutation; the code never edits the judges that judge it; births come from your architect agents and from you on
outcome-free facts, under a false-pass budget you state and may restate each week", and "metered compute <= $10 a day
plus half the trailing week's realized net profit, never above $50". Goal V3 replaced goal V2 (05:15Z Mon Oct 19,
`GOAL-MESSAGE-V2.txt`: real money "at learning size", a false-positive rate <= 15%, the $5 compute line), under which
the draft was written; every figure the draft took from V2 is restated here and says so (section 12, F13). Also under
the owner's asks of Oct 22 for bigger swings at the source of the lane's edge (the captain's A119: "the lane's thesis is
reading, and it reads with the cheapest model"). Written 16:57Z Oct 22-07:10:40Z Oct 23, 2026 (the design
workflow wf_117ca4fe-359: four blind designers from 16:57Z Oct 22 (a READER-2 designer, an intraday-lane designer, a
births-at-scale designer and a red team), the judge from 21:23Z; two adversarial checks after the judge; the fix round
of Oct 23, `evl10/fix1/`, which applied every finding of both checks that concerns this file and goal V3's figures;
two adversarial re-checks of the fixed file, `evl10/recheck1/` and `evl10/recheck2/`; and the second fix round,
`evl10/fix2/`, which applied the two majors they returned).

HOW IT WAS MADE. The captain's A119 (16:45Z Oct 22) opened this design before any design existed. The READER-2
designer started from PREREG-EVL-7's reader lens (its sketch `evl7/EDGE-RESULT.json`, key `design-reader`, and
PREREG-EVL-7 section 0's NOT TAKEN note) and wrote frozen request specs, a consumer seat and its synthetic calibration
under PREREG-EVL-6 as frozen (`goal-2026-10-19/evl10/reader2/`). The red team assumed both of A119's swings had failed
six weeks out, ranked the causes and proposed guards (`goal-2026-10-19/evl10/redteam/`). The judge chose among them,
changed what the code, the frozen files, the budget and the red team's evidence force, re-measured the seat's false
passes on fresh synthetic seeds (`goal-2026-10-19/evl10/calib/`) and wrote the draft. Two adversarial checks read it
(`evl10/CHECKS.json`: check 1 statistics, `evl10/check1/`; check 2 honesty and implementability, `evl10/check2/`); both
said fix. The fix round (`evl10/fix1/`) applied every major and minor of both checks that concerns this file, changed
the prompts' p_up line (new request shas), re-measured on fresh seeds what the fixes touch (the worst thin-supply cells,
the supply the new R2 line starves, its power cost) and restated the money, cost and budget figures under goal V3 and
release 1019l; section 12 lists every change and where it sits. Two re-checks read the fixed file; the second fix
round (`evl10/fix2/`) applied their two majors: this file's real-money pass carries release 1019l's per-program rules
(section 2.5) and COMPLETE can be met (section 1.4), section 12's F17 and F18. Each of them worked under the rule that
no price after any event, and no return, P&L, look, band, mark or bar of any event, symbol or program, is read, queried
or computed, from the House, the gateway, events.sqlite, live.sqlite, `~/Work/ltcm-evl-run`, `~/Work/.ltcm-main/evl`,
`~/Work/.ltcm-main/scratch` (but the amendments record) or any run record; none was (section 10).

PROVENANCE. The design workflow ran from `goal-2026-10-19/workflows/edge_swings.js` (sha256
40edc3fdd27696e58809838a4def2f96340fa40b8f0ef2e9b3ecbbedd7880869); the fix round, the re-checks and the second fix round
from `goal-2026-10-19/workflows/evl10_fix.js` (sha256 4b03d2d7fbf41017472bb9385246b73ecbc82d8c51369d5e4d6561556a75d0ba
at this writing). Their prompts carried only outcome-free counts (`goal-2026-10-19/speed/SPEED-FACTS.md`,
`speed/EXECUTION-FACTS.md`), the done-speed brief (`speed/KEPT-1019h.md`), the frozen texts PREREG-EVL-1 to -9, the code
at releases 1019f-1019l, goal V3's text and a pointer to the captain's amendments record
(`scratch/eqlane-1010/CAPTAIN-AMENDMENTS.md`, A60-A138 named). The draft this file was fixed from is
`evl10/PREREG-EVL-10.draft.md` (sha256 c4adfac25bef4bd10d7586b92d9aaee98302cff6a24d1499f007ed4d2f75cb82); the checks'
findings `evl10/CHECKS.json` (70304a0970bebf29dc1f3804a53377b740efd2056ff7a8dd92b691ead7b1304b). THE FROZEN READER-2
FILES ARE THE FIX ROUND'S: `evl10/fix1/r2_spec.py` (sha256
fd5c040e739f433c013c86f49caf70f2645d87015d6c645ab04b049b42d82a28) and `evl10/fix1/smoke_r2.py`
(2bf2d11cffc7c1657fdc94c0753c6844677097a8fa026090535ae14e7d20bc61), which differ from the designer's
`evl10/reader2/r2_spec.py` (b14402e2...) and `smoke_r2.py` (b44e31ed...) exactly as their docstrings state; the
designer's calibration `calib_r2.py` (130de336...) and its outputs are listed with their sha256 in
`evl10/reader2/SHA256SUMS`; the judge's calibration is `evl10/calib/` with `SHA256SUMS`; check 1's `evl10/check1/` with
`SHA256SUMS`; check 2's `evl10/check2/r2_line.py` (a57e14bc...) and `r2_line.out` (1b6dc6b0...); the fix round's
`evl10/fix1/` with `SHA256SUMS`; re-check 1's `evl10/recheck1/` and re-check 2's `evl10/recheck2/` (`a85_slot.py`
5d9656ba..., `a85_slot.out` 5d965128...), each with `SHA256SUMS`; the second fix round's `evl10/fix2/` (`slot_rules.py`
and `complete.py` with their outputs) with `SHA256SUMS`; the four designs as their designers returned them in
`evl10/designs/`. All of them are copied into `docs/prereg/evl-10/` at the freeze with their sha256.

REGISTRATION TIME: the latest of three times, all recorded in the captain's registering amendment, which pins it as
`REGISTERED_AT_10` (A92's method): this file's commit time; the pushing client's own clock read after the push of the
tag `prereg-evl-10` returns; GitHub's activity time for the push of the branch `prereg/evl-10`. The tag never moves. A
program or record of this file counts only events knowable after REGISTERED_AT_10, and its JUDGED RECORD only
decisions the House makes live with the release carrying this file's code (section 2.6). Nothing here changes for a
registered version: a change is a new version with its own registration time. No READER-2 read of any event exists
before REGISTERED_AT_10: the only calls before it are the two synthetic smoke-test calls of section 1.7.

## 0. What this file adds, and what shaped it

- WHAT IT ADDS. A second, new reader version, READER-2 (R2): claude-sonnet-5-5 with structured outputs, reading at
  most about 40 day-news articles a session chosen by a hash share (more on a heavy day, up to a cap of 64, section 1.4)
  and at most 8 8-Ks, chosen by fixed rules from the eligible, liquid, BUYABLE names that v1 (PREREG-EVL-1 section 4's
  PROMPT-NEWS and PROMPT-DOC on Claude Haiku 4.5) already ranks; ONE seatable consumer, EVL-R2-ON (bought at D's
  close, sold at the next open), registered with it before any R2 read exists; its control EVL-R2-ON-SET and two free
  records; FEATURES-R2 v1, the frozen columns any later learner version may take, all or none. It changes no verdict,
  prompt, program, record, control, judge, band rule or wall of PREREG-EVL-1 to -9, and no earlier program reads
  anything it writes EXCEPT PREREG-EVL-8's EVL-META-ON and its POOL record EVL-META-ON-POOL: by that file's section 7.2
  (frozen) they take this file's four rows as SOURCES, members from the first live decision and program experts once
  those hold MINB 3 settled blocks, read only through section 2.4's one reading of this file's rows (never `reads2`).
- WHY A STRONGER READER (the lane's own facts). v1 gives a seven-level score; the slots bind, not supply (A94; at most
  8 open at learning, and 14 at Probe for versions registered from REGISTERED_AT_6, A99); book.picks ranks a READ row
  by (rank_key, adv20 descending), so a READ row's real money takes the LARGEST names among 54-165 score >= 2 ties a
  session (SPEED-FACTS: EVL-NEWS-READ-ON 54 / 54 / 142, EVL-NEWS-READ-O1 54 / 88 / 165 on Oct 19-21). With slots
  fixed, a seat's profit is the edge of the events it fills, so the key that orders them is the lever (Grinold 1989,
  Journal of Portfolio Management 15(3)). In the designer's synthetic consumer, a continuous reader key beat a coarse
  v1-like key with size ties at the same information (+1.5 against -3.6 bp a pick, `reader2/calib_r2.power.jsonl`),
  and a filter made of the reader's own fields doubled the picks' edge against a random filter (+27.5 against +9.8 bp
  at c 0.5, `calib_r2.power2.jsonl`).
- WHAT THE JUDGE CHANGED FROM THE DESIGNER'S DRAFT, AND WHY (as fixed by the fix round where marked):
  1. BUYABLE (new): every read and every candidate needs 1.25 x the previous close <= 5% of the previous close's
     equity, so one whole share at the limit fits goal V3's learning position (5% of equity, release 1019l's row,
     A138) and Probe's 5% envelope (PREREG-EVL-1 section 8): no read is spent on a name no band can hold. The bound is a
     fixed constant of this file (0.05), never a money row: a later change of a size row moves no candidate.
  2. R2'S LINE IS INSIDE THE LANE'S LINE (the fix round, check 2's major 3; the draft had a $0.75 line of its own
     beside a $5.00 metered-day guard, which sat outside THE COST RULE, so a fully spent day could pass the owner's
     wall and trip the cap-breach hold that zeroes v1's line): R2's dollars count in the lane's line as the births'
     do, and R2 asks only within R2_LINE = max(0, min($0.75, L - 1.5 x V - $0.25)), where v1 keeps 1.5 times its
     heaviest recent day and the births their night before R2 asks (section 1.5). No R2 dollar can make a cap breach.
  3. THE PIN AND THE SCHEMA STOP (from the red team's C8): every answer stores the response's model string; a change
     from the smoke test's pin, or two sessions of broken schemas, stops R2 for good (section 1.5). The red team's
     daily canaries are not taken: Sonnet 5.5 refuses a sampling parameter, so a canary tolerance cannot be set blind,
     and a report-only canary is spend that feeds no seat (A102).
  4. SPEND FOLLOWS THE SEAT (from the red team's C3, simplified): R2 asks nothing once its only consumer can never
     trade again (retired, or out of runs). The red team's IC spend stop is not taken: its own power (`redteam/
     futility10.out`) stops a worse reader at most 0.197 of the time by 60 sessions; the small line is the guard.
  5. TWO FREE RECORDS (new): REC-R2-ON-PASS and REC-R2-ON-AVOID, so PREREG-EVL-8's EVL-META-ON, whose SOURCES are
     every hold-1 close-to-open row of every later file (its section 7.2), can weigh slices of R2's information
     forward at no charge (the red team's records-first route, C5), beside the seat.
  6. FEATURES-R2 v1 COMPACT (changed): 21 columns (section 1.6) instead of the designer's one-hot set of about 60, so
     a later learner version that takes them adds a dimension its about 45 R2 rows a session can fit.
  7. ONE SEAT, AT THE CLOSE (kept, against the red team's open seat): buying at the open after attention news pays an
     opening premium that reverses during the day (Berkman, Koch, Tuttle and Zhang 2012, JFQA 47(4)); overnight
     returns carry the attention premium (Lou, Polk and Skouras 2019, JFE 134(1)); PREREG-EVL-7's E8 bars an
     open-to-close buy of an earnings issuer; and one seat costs one charge of a scarce budget (section 4). Earnings
     8-Ks (item 2.02) are not read (the designer's reasons, kept: at the open E8; at the close the reaction bands of
     PREREG-EVL-2, -4 and -5 take them first and their 15:30 mark is fetched only inside the close run). The prompts'
     p_up asks about exactly this hold, D's closing auction to the next opening auction (the fix round, check 2's minor
     12).
  8. LIVE-ONLY RECORD AND NO CATCH-UP (kept): no R2 read can exist before the code ships, so the record's clock is the
     code's (section 2.6). The decision is its own slot in the decision scheduler (A120), before the lane's close
     decision; its buys come after every earlier file's (the fix round, check 2's major 1: section 2.5's ROOM).
- WHAT THE RED TEAM'S EVIDENCE SAYS, STATED BEFORE THE RULES (section 6 answers every cause): the most likely six-week
  outcome is "nothing promoted", whatever the reader knows (PREREG-EVL-6's first look is at the 22nd block); a seat
  with no reader information loses its metered dollars, about $49 over 120 sessions at the mid cost ($72 at the caps'
  mid cost, at most $90 at the line; `fix1/ev_fix1.out`); the seat is clearly positive only if the reader carries real
  information over v1 (section 7).

## 1. READER-2

### 1.1 Identity and request

- R2 is a reader version with two request specs, each named by the SHA-256 of its canonical spec (model, effort,
  thinking, stream, max_tokens, system, user, format and render constants; `r2_spec.spec(kind)` with `json.dumps(...,
  sort_keys=True)`), the FIX ROUND'S `evl10/fix1/r2_spec.py` copied verbatim into `docs/prereg/evl-10/r2_spec.py` at
  the freeze and recomputed there:
  - R2-NEWS a82396145a28dd4d98d6878e515cc26c26fd70c6c29f2642d4e1c4241642d694;
  - R2-DOC 127c19f36f3811afaf4401c35e7620618a27ca0eb32795d0b19ba45a87522c5b.
  - (The draft's 617f8979... and 65d79226... are the designer's texts, never sent and never R2.)
  - If section 1.7's smoke test pins R2-J, the registering amendment states R2-J's two shas and they are R2 for good.
- MODEL: `claude-sonnet-5-5` through the gateway's `/v1/claude/messages` (its CLAUDE_MODELS row, unchanged from release
  1019h to release 1019l: $2 a million input tokens, $2.50 a five-minute write, $0.20 a hit, $10 output; geo us 1.1).
- BODY (`r2_spec.body`): model; max_tokens 1,200 (news) or 1,600 (doc); system; one user turn; thinking {type
  adaptive, display omitted}; output_config {effort low, format {type json_schema, schema}}; stream true. No
  temperature (Sonnet 5.5 refuses sampling values), no tools, no cache markers. The gateway's `admit` (gateway/lib/
  claude.mjs at release 1019h) admits exactly this shape: adaptive thinking with display omitted or summarized, an
  effort and a json_schema format, streamed.
- STREAMED by the lane's `gw.post_stream` (release 1019h, built for the Opus births call), a byte at least every 30 s,
  the whole answer within 90 s.
- TEXTS AND SCHEMAS: `fix1/r2_spec.py`'s SYSTEM_NEWS, USER_NEWS, SCHEMA_NEWS (10 fields: type of 13 values, new 0-2,
  corroborated 0-2, price_story, consensus of 5 values, vs_own_guidance of 9 values, magnitude 0-3, specific 0-2,
  surprise -3..3, p_up 0-100 in steps of 5) and SYSTEM_DOC, USER_DOC, SCHEMA_DOC (15 fields: the news fields with
  routine in place of price_story, plus material 0-3, guide_chg_pct (a number or null), dilution, one_offs and tone
  -2..2), verbatim. p_up is "the probability, from 0 to 100 in steps of 5, that this stock outperforms the overall
  stock market from the closing auction of the trading day this item is read on to the opening auction of the next
  trading day" (the seat's own hold; the draft's "over the next trading day" was, for an 8-K read before 09:30 ET, D
  itself, which the seat never holds). Integers are enums, the nullable number is anyOf [number, null],
  additionalProperties is false, every field is required. Neither text gives any market data; stored headlines may
  mention prices, as v1's do.
- WHY SONNET 5.5 AND NOT OPUS 5.5: Opus's prices are twice Sonnet's for input, cache writes and output (cache hits are
  $0.20 for both; R2 sends no cache marker), and the slots fix the read count, so Opus doubles R2's cost ($0.82 against
  $0.41 a day at the designer's mid case, `reader2/cost_r2.out`); the task is extraction and judgment over at most
  about 20,000 characters at low effort; no outcome-free measurement here separates the two models. A model change is
  a new reader version, by a later file. WHY NOT HAIKU (the red team's choice for news): the owner's A119 asks for a
  stronger model; the same model with a longer prompt tests a prompt, not a reader.
- R2 is stored only in `reads2` (section 1.3), never in `verdicts`. It never changes, replaces, delays or re-asks a
  PROMPT-DOC or PROMPT-NEWS verdict (PREREG-EVL-1 section 4) except as section 1.5 states for a day v1 spends more than
  1.5 times its heaviest recent day (counted, binding `v1_reserve`); and no program, record, control, judge, look,
  band or Done rule of PREREG-EVL-1 to -9 reads it, except PREREG-EVL-8's EVL-META-ON and EVL-META-ON-POOL, which read
  this file's four rows (never `reads2`, `r2_qual` or `r2_features`) through section 2.4's one reading, by their own
  section 7.2.

### 1.2 What a read sees

Every input is knowable before the read's own decision time (section 2.2's tau) and stored before the ask.
- NEWS (`r2_spec.render_news`): the symbol; D's universe name; the article's created time (ET); its source; "Read on
  D." (D the entry session of the decision the read is for, YYYY-MM-DD); its headline and summary. Then EARLIER NEWS:
  stored articles whose symbols include the ticker (any number of symbols; the item itself excluded), knowable in
  [k - 30 days, k) and received before the ask, newest first, at most 40 lines "YYYY-MM-DD HH:MM ET | source |
  headline[:160]"; and EARLIER FILINGS: the issuer's stored form 8-K filings knowable in [k - 30 days, k), newest first,
  at most 10 lines "YYYY-MM-DD HH:MM ET | SEC 8-K items x, y". k is the item's knowable time (PREREG-EVL-1 section 3).
  An empty block reads "none".
- DOC (`r2_spec.render_doc`): PREREG-EVL-1 section 4's name, ticker, items and acceptance time (ET), "Read on D.", and
  the first 16,000 characters of the same TEXT document v1 read (v1's document sha). Then NEWS: stored articles naming
  the ticker knowable in [k - 30 days, the ask) and received before it, newest first, at most 25 lines.
- Each read keeps its prior article ids, its filing accessions, the number of prior lines given (prior_n) and the
  SHA-256 of its rendered user text. The store's news begins Oct 19, so the 30 days are shorter until about Nov 18;
  prior_n records it.

### 1.3 Storage (additive tables; SCHEMA_VERSION stays 1)

- `reads2`(event, prompt_sha, model, window, day, request_id, asked_at, answered_at, status, answer, fields, usd,
  in_tokens, out_tokens, response_model, user_sha, prior_ids), PRIMARY KEY (event, prompt_sha, model). STATUS is one
  of:
  - `ok`: the answer is one JSON object that validates its schema exactly (`r2_spec.parse`);
  - `unparsed`; `refused` (an API refusal, or a response model that is not the pin, section 1.5); `cut` (stop_reason
    max_tokens); `lost` (the stream went out and no whole answer came back).
- THE FIRST STORED ROW IS FINAL: no event is asked again for the same prompt sha and model; `cut` and `lost` are never
  re-asked. A call the gateway or R2's line refuses BEFORE sending stores nothing and may be asked while sections 1.4
  and 1.5 allow. A lost or unpriced call counts at its worst-case hold (section 1.5).
- `r2_qual`(window, day, cik, event, kind, qualified_at, v1_score, h, q, chosen), write-once: every event that
  qualified (section 1.4), read or not, whatever the lines and the day stop.
- `r2_scan`(day, scanned_at), write-once, one row for each qualification scan R2's task makes (section 1.4's COMPLETE).
- `r2_features`(event, decision, columns, written_at), write-once per (event, decision) (section 1.6).
- A test pins that an R2 write leaves `verdicts` byte-identical (screen.py reads a late share from `verdicts`).

### 1.4 The ON SET of entry session D: what R2 reads

- THE TERMS (PREREG-EVL-4 section 1.1 and PREREG-EVL-5 section 1.1, unchanged): D, P, T29, DAY(D), F8K(D), ERN(D),
  EXCLUDED on D (an issuer in ERN(D) or DAY(D)), D's close window. E_prev: the account equity at P's close as score.py
  reads it (`equity_on`).
- AN EVENT QUALIFIES at an ask when ALL hold, as stored at the ask:
  - its issuer's LIVE-rule eligibility for D is decided and eligible (the lane's `eligibility` row, rule 'live');
  - LIQUID: D's universe row's adv20 >= $10,000,000 (score.py `LIQUID_ADV`, the replay's lower impact tier);
  - BUYABLE: 1.25 x D's universe row's prev_close <= 0.05 x E_prev (this implies PREREG-EVL-1 section 5's TRADABLE);
  - it is knowable after REGISTERED_AT_10;
  - and it is either
    - NEWS-ON: an article of DAY(D) (EVL-NEWS-READ-ON's family: single-symbol, the eligible ticker, knowable after
      09:00 ET of D and at or before T29 of D, PREREG-EVL-1 section 3's non-live exclusion applied) with a stored `ok`
      PROMPT-NEWS verdict of score >= 2; or
    - 8K-ON: an 8-K of F8K(D) (form exactly `8-K`; items 1.01, 2.01, 7.01 or 8.01 and no 2.02; knowable in D's close
      window) of an issuer not EXCLUDED on D, whose TEXT has at least 200 characters and whose stored PROMPT-DOC
      verdict is `ok` with score <= 1 (the filings v1 sets aside, which no earlier close row takes).
- Each qualifying event is written once to `r2_qual` with its time, at the scan that first sees it qualify. R2's task
  scans at each job the House's publishes start while it runs (section 1.5) and stores each scan in `r2_scan`.
- CHOSEN, NEWS-ON:
  - h(D, cik) = int.from_bytes(sha256("R2|ON|" + D + "|" + cik)[:8], "big") / 2^64 (`r2_spec.h`), uniform and
    independent of everything stored.
  - q(D) = min(1, 40 / m), m the mean, over the last 5 sessions whose NEWS-ON window is COMPLETE in `r2_qual`, of the
    number of issuers with a qualifying NEWS-ON article; q = 0.5 when there is none (`r2_spec.share`). COMPLETE (check
    2's minor 13 (d), restated by the second fix round, F17): a session whose stored `r2_scan` times have no gap over 5
    minutes between consecutive times, counting 07:30:00 ET as the first time and tau - 30 s as the last. The task
    starts at 07:30:00 and stops at tau - 30 s, and its scans come only on the jobs the House's publishes start (60-121
    s apart), so no stored scan falls exactly on either end. Qualification is recorded whatever the lines and the day
    stop. (`fix2/complete.out`: under that cadence, with one job at a time and a streamed call of up to 90 s in every
    job, every synthetic session with no House stall is COMPLETE, its largest gap 211 s; a stall of over 5 minutes is
    not; the first fix round's wording, a stored scan at or before 07:30 and one at or after tau - 30 s, made none
    COMPLETE and so held q at 0.5 for good.) q is fixed at the first ask of D.
  - An issuer is read for (i) its first qualifying article when h < q, or else its first qualifying article with v1
    score 3; and (ii) once more, for its first later qualifying article whose v1 score is strictly higher than the
    article read in (i). At most 2 news reads an issuer a session; at most 64 news reads a session, in qualification
    order.
- CHOSEN, 8K-ON: an issuer's first qualifying filing, at most 8 a session in qualification order.
- NEWS-ON issuers are DAY(D) issuers and 8K-ON issuers are not (EXCLUDED), so the two never share an issuer at one
  ask; an 8K-ON issuer that becomes a DAY(D) issuer later in the session is dropped at the decision (section 2.2).
- EXPECTED READS A SESSION (check 2's minor 11, stated as it is): the hash share targets about 40 news issuers, but
  every issuer's first score-3 article is read whatever h, so on a heavy day the news count follows the score-3 volume
  up to its cap of 64. The designer's `reader2/cost_r2.py` assumed about 2 such reads above the share (news 31.8 /
  37.2 / 42.0 and 8-K 7.4 / 8.0 / 8.0 at a liquid share 0.4 / 0.6 / 0.8 of the qualifying issuers, before BUYABLE;
  neither share is in the facts); at the caps (64 news + 8 docs) a day costs $0.220 / $0.602 / $1.344 at the lo / mid
  / hi per-read costs (`fix1/cost_fix1.out`), against $0.140 / $0.411 / $0.968 at the designer's counts. BUYABLE (the
  share of liquid names under about $76 at $1,906 of equity is not in the facts) lowers m and so raises q. Reads past
  a cap or a line are the session's latest, since asks go in qualification order.

### 1.5 Asks, lines and stops

- WHEN: R2's asks for D's ON SET run as per-call jobs on their OWN House lane, a new lane 'reader' (league/house.py
  `_lanes`: Semaphore(1); `_background` key 'reader:r2'), never on 'feeds:' (the lane's one slot, so no record pass,
  verdict pass or decision waits for R2) and never on 'ops:' (whose workers the backup and stall jobs share; check 2's
  minor 13 (a)); each of the House's publishes (at most once a minute, 60-121 s apart in session: house.py's H5 note)
  starts one job when R2's last job has finished (`_background`: one job per key), and that job makes a qualification
  scan and the next due call, if any. They run from 07:30:00 ET of D until 30 seconds before section 2.2's tau,
  one call at a time, in qualification order (8K-ON and NEWS-ON interleaved by qualified_at). An event that qualifies
  later than 30 seconds before tau is never asked.
- R2'S LINE IS INSIDE THE LANE'S LINE (check 2's major 3). R2's dollars count in the lane's line: house.py
  `_spend_today` adds `reads2.usd` (a lost or unpriced call at its hold), as it adds the births' cost. With the fixed
  costs and the other lines they therefore stay inside THE COST RULE's cap (league/ops/budget.py), and no R2 dollar can
  make a cap breach. A call is sent only while both hold, each with the call's worst-case hold (`fix1/cost_fix1.out`:
  $0.0552 a news read, $0.1036 a doc read at the body's max size and max_tokens, at Sonnet 5.5's prices with geo us
  1.1):
  - (a) R2's own dollars of the UTC day plus the hold are at most R2_LINE = max(0, min($0.75, L - 1.5 x V - $0.25)),
    L the lane's line of the day (house.py `verdict_line`: the lower of `events.verdict_usd_day` and budget.py
    `lane_allowance`), V the heaviest UTC day of PROMPT-NEWS and PROMPT-DOC verdict dollars over the trailing 7 days
    (verdicts only), $0.25 the births' night cap (births.NIGHT_USD); R2_LINE is fixed at the day's first ask;
  - (b) no cap hold (budget.py `cap_hold`) names the day.
  So v1 keeps 1.5 times its heaviest recent day, and the births their night, before R2 asks: at L = $3, R2_LINE is
  $0.75 while V <= $1.33, $0.62 at V = $1.42 (Oct 21's v1 volume), $0.35 at $1.60, $0.20 at $1.70 and $0 from about
  $1.83 (`fix1/cost_fix1.out`, check 2's `r2_line.out`). R2 can delay a v1 verdict only on a day v1 spends more than
  1.5 V; that day is counted (alarm `reader_line`, binding `v1_reserve`). Over its line R2 asks nothing (alarm
  `reader_line`) and the events not asked are missing. Every R2 dollar is metered and reported (league/ops/metered.py,
  budget.py, daily_report, evl_health).
- THE OWNER'S LINE UNDER GOAL V3, stated: goal V3 raised the metered-compute wall to $10 a day plus half the trailing
  week's realized net profit, never above $50; release 1019l's code still holds THE COST RULE at goal V2's $5 plus half
  the week's profit, never above $25 (league/ops/budget.py RULE_VERSION 3). R2 sits inside whichever cap the code's
  rule enforces, so it can breach neither. This file freezes R2_LINE's formula, not L: a release that moves the cost
  rule to V3's figures and raises the lane's line moves L, and R2_LINE follows by the same formula, never above $0.75.
  The draft's $5.00 metered-day guard (its (b)), which was V2's line before any profit share and saw only spend so far,
  is withdrawn.
- THE PIN: the smoke test of section 1.7 records the response's `model` string; every R2 answer stores its response
  model; an answer whose model string differs from the pin is stored `refused`, and R2 asks nothing more for good
  (alarm `reader_pin`; a new reader version is a later file's).
- THE SCHEMA STOP: when, on two consecutive sessions each with at least 10 answered reads, `unparsed` + `cut` are at
  least 10% of the session's answered reads, R2 asks nothing more for good (alarm `reader_schema`).
- THE DAY STOP: three gateway 4xx answers to R2 in a UTC day stop R2's asks for that day (alarm `reader_stop`); its
  scans go on.
- SPEND FOLLOWS THE SEAT: R2 asks nothing more for good once EVL-R2-ON is `retired`, or once it is a shadow record
  only because it cannot start a run (section 3), or when the lane's pivot retires it.
- A read not answered before tau is MISSING for the decision, for the shadow and for real money alike (the shadow
  never waits for a read; section 2.4's one reading).

### 1.6 FEATURES-R2 v1 (frozen here; read only by a later file)

- For each (event, decision) of EVL-R2-ON's decision of D whose event has an `ok` R2 read answered before tau (the
  issuer's read of section 2.2), written once at the decision from rows stored before tau, the 21 columns in this
  order: (1) kind_doc; (2) new / 2; (3) corroborated / 2; (4) magnitude / 3; (5) specific / 2; (6) surprise / 3; (7)
  (p_up - 50) / 50; (8) price_story (news; 0 for a doc); (9) routine (doc; 0 for news); (10) material / 3 (doc; 0);
  (11) tone / 2 (doc; 0); (12) dilution (doc; 0); (13) one_offs (doc; 0); (14) consensus = beat; (15) consensus =
  miss; (16) vs_own_guidance in {above, raised}; (17) vs_own_guidance in {below, lowered, withdrawn}; (18) type in
  {analyst_rating, analyst_target} (news; 0); (19) type in {earnings, guidance}; (20) ln(1 + prior_n) / ln(41); (21)
  r2_missing, 0 here. An event a later learner meets with no such row reads r2_missing = 1 and every other column 0.
- A later file may give a NEW VERSION of a PREREG-EVL-7 or -9 learner, or of a PREREG-EVL-8 meta-learner, ALL these
  columns or none, with its own registration time, charge and screen: the subset is never chosen (all or none). This
  file registers no learner version. (PREREG-EVL-7's NOT TAKEN note asked that READER-2 be registered with the learner
  version that reads its fields. This file answers it two ways and states the rest: PREREG-EVL-8's meta-learners,
  registered before any R2 read, weigh EVL-R2-ON, its control and its two records forward as program experts by their
  own rule; and the columns are frozen now, all or none. A later file that takes them is designed by designers who read
  no RS-2 figure (section 2.7); its captain, who will have seen RS-2, states what of it he saw and chooses none of its
  rules; it counts only its own later events and pays its own charge; check 2's minor 13 (e).)

### 1.7 The smoke test, before the freeze (at most $0.01)

- `evl10/fix1/smoke_r2.py --send`, run by the captain (never a designer, never the fix round): two streamed Sonnet 5.5
  calls with section 1.1's body shape and the fix round's texts on pinned synthetic texts naming no real company, ticker
  or event (ticker ZZXQ, read_day 2026-10-22): DOC with max_tokens 400 (worst case $0.0078), then NEWS with max_tokens
  300 (worst case $0.0061 with the longer fix-1 text, `fix1/cost_fix1.out`), sent only if call 1's stated cost +
  $0.0061 <= $0.01, else after 00:00 UTC. The dry run is `fix1/smoke_r2.dry.out` (doc body 4,646 bytes, news 3,572;
  the spec shas of section 1.1). The designer's `reader2/smoke_r2.py` is not run: it sends the superseded texts.
- PASS: the gateway admits both bodies, both answers parse `ok`, and the gateway's `ltcm.cost` event arrives. The
  registering amendment records PASS, the response `model` string (THE PIN; the fix round's copy prints it in its
  report, which the designer's did not), the measured tokens and seconds.
- If `output_config.format` is refused, the amendment pins R2-J before the freeze: the same texts with the line
  "Answer with one JSON object with exactly these keys and no other text." and no format, their shas recomputed; R2-J
  is then R2 for good. A "max_tokens" stop is a finding (the max_tokens are raised in the same amendment, before the
  freeze, with new shas), not a fail.

## 2. The programs

### 2.1 Terms

As section 1.4. A CANDIDATE's READ is the issuer's `ok` R2 read answered before tau with the highest KEY (below), then
the earliest answered; the candidate's EVENT is that read's event. THE E10 BAR (PREREG-EVL-7 section 1.9's reading,
applied here to the RECORD as well as to money): an issuer is BARRED on D when any of its 8-Ks (form exactly `8-K`)
knowable at or after 09:00 ET of D and stored before tau has a stored PROMPT-DOC verdict `ok` with score >= 2, or `ok`
with score >= 1 and guidance "raised", or no answer by tau (such a filing is an earlier row's event at the next open,
which this file's sale there would take).

### 2.2 EVL-R2-ON v1 (seatable)

- ENTRY AND EXIT: buys at the CLOSE auction of D, sells at the OPEN auction of the next session (PREREG-EVL-2 section
  2's exit at the open, PREREG-EVL-1 section 5's fallback ladder); hold 1 in the screen's sense (its block is D;
  blocks never overlap). TAU = D's close - 20 minutes (15:40:00 ET on a full day; on an early close, the close - 20
  minutes).
- CANDIDATES: one per issuer, the issuers of D's ON SET with an `ok` R2 read answered before tau, that at tau, as
  stored before tau, are: BUYABLE (section 1.4); for an 8K-ON issuer, not EXCLUDED on D; not BARRED (section 2.1);
  eligible (section 1.4); and whose event is knowable after REGISTERED_AT_10.
- THE FILTER (`r2_spec.consumer_pass`), all of: for news, price_story false and type not price_move or commentary; for
  a doc, routine false, dilution false and type not investor_materials; vs_own_guidance not below, lowered or
  withdrawn; consensus not miss; new >= 1; surprise >= 1; p_up >= 60.
- THE KEY (`r2_spec.consumer_key`, higher first): p_up, then surprise, magnitude, specific and corroborated; then the
  lower h (section 1.4; for an 8K-ON issuer the same formula over its CIK).
- PICKS: the first 8 passing candidates in key order that the version holds no position in within 5 sessions
  (PREREG-EVL-1 section 5 as A72 reads it: every written, non-skipped intent of this id and version), with
  `intents.rank_key` = 9 - position (8 for the first). A decision may pick fewer than 8, or none.
- PREREG-EVL-2's LIMIT AT ENTRY applies, shadow and real: an entry auction above 1.25 x the raw SIP close of P is not
  filled and the event is skipped. PREREG-EVL-1 section 5's replay gives the costs, r, b, a and TRADABLE.
- FEATURES-R2 v1 (section 1.6) are written for every candidate in the same transaction as the intents.

### 2.3 The control and the records (free; never seated; no expected false pass)

- EVL-R2-ON-SET: EVL-R2-ON's control (PREREG-EVL-1 section 7's comparison, PREREG-EVL-6 section 1.4's READ condition):
  every candidate of section 2.2 (one per issuer, its read's event), whatever the filter, entering and exiting as
  EVL-R2-ON, one position per issuer within 5 sessions of its own intents.
- REC-R2-ON-PASS: every candidate that passes the filter (no cut at 8), the same entry, exit and one-position rule.
- REC-R2-ON-AVOID: every candidate that fails the filter, the same.
- These three and EVL-R2-ON are hold-1 close-to-open rows, so by PREREG-EVL-8 section 7.2 as written they are
  EVL-META-ON SOURCES (members from their first live decision; program experts, asleep until they hold MINB 3 settled
  blocks; four of a family capped at 1,535), and so EVL-META-ON's and EVL-META-ON-POOL's members, walk and intents
  change with them (section 0, the one exception). This file neither asserts more nor relies on it. Their reading at
  META's tau, or at any time, is section 2.4's ONE READING. (If PREREG-EVL-8's code reads its section 7.2 so that a
  source decided in the lane's own runs gives members only when `decide-close:<D>` names it, which never names a later
  file's row, these rows give none; that reading is PREREG-EVL-8's, and this file changes nothing in it.)

### 2.4 The decision run

- `decide-close-r2:<D>` is THIS FILE'S SLOT in the decision scheduler's close table (A120; origin/feat/scheduler,
  PR 603): `scheduler.Slot("evl10", "close", 10.0, "close-r2", start=Wall("close", -1200), never_past=Wall("close",
  -940), send_from=Wall("close", -780), send_until=Wall("close", -660), catchup=None)`, the LAST row of the close
  table: a clock start at tau, a bound of 10 seconds, never started past the close - 15 minutes 40 seconds (15:44:20
  ET), so it ends by 15:44:30 (HOLD_LEAD's lead), DECISION_MARGIN and more before the lane's close decision; the send
  window [15:47:00, 15:49:00) of the main rows; SQL over stored rows only (no network read). Its writes (intents of the
  three rows and EVL-R2-ON, every intent with `decided_at` = tau; `r2_features`) are one transaction committed only
  when the run completes; its receipt is `ok` or it is not made.
- Its picks are fixed by stored times (answered_at, stored_at, received_at, decided_at before tau), so they do not
  depend on when in its window the run starts.
- THE ONE READING OF THIS FILE'S ROWS (check 2's major 0). For each of EVL-R2-ON, EVL-R2-ON-SET, REC-R2-ON-PASS and
  REC-R2-ON-AVOID, `book.picks(lane, s, D, decided_at=t)`, for ANY t, is s's intents written by the live
  `decide-close-r2:<D>` receipt with status `ok`, taken in rank_key order, then adv20 descending, then event id, less
  real money's own held-lot skip (`held`, the book's lots and buys; the version's own five-session rule is already in
  the decision). Every input is cut at this file's tau of D, never at t. With no such receipt the reading is empty
  (PREREG-EVL-7's learners are read the same way: book.py `learner_picks`). So real money, PREREG-EVL-8's members of
  EVL-META-ON and the shadow read the same picks: no read answered after tau (a call sent at tau - 30 s can answer at
  tau + 60 s) and no 8-K or article stored after tau can reach real money or a member. TEST: a read answered at tau +
  30 s and an 8-K stored at tau + 60 s change neither the book's picks at 15:46 nor META's members.
- A session whose slot did not run live, failed, was cut or was missed has NO decision of this file: no intent, no
  block, no record, no real money (alarm `r2_starve`). There is no catch-up (`catchup=None`). THIS DEPARTS FROM
  PREREG-EVL-1 SECTION 3 ("an outage removes nothing") FOR THIS FILE'S ROWS ONLY (check 2's minor 13 (b)): the removal
  is by the clock and the House's own run, never by a price or an outcome, and the shadow of PREREG-EVL-1 to -9 is
  untouched.
- THIS FILE NEEDS THE SCHEDULER: its decision is a scheduler slot, so the release that carries this file's code carries
  the decision scheduler (PR 603, not live at this writing) or comes after one that does; no other path decides this
  file's rows (the reading that trades and asks less: no slot, no decision, no record, and so no R2 ask, section 1.5's
  SPEND FOLLOWS THE SEAT). The code ships in the first release after the freeze that passes its review, never held
  back or brought forward for any figure.

### 2.5 Real money

- REAL-MONEY SIZE IS THE MONEY TABLE'S (goal V3; the captain's A138, release 1019l: "the frozen texts' size words were
  V2's walls; only real-money size moved, every judge is unchanged"). The draft's sizes were V2's (learning 2%, Probe
  3.5%); they are restated here (section 12, F13).
- LEARNING from the first live decision of the House release that carries this file's code: a target of the learning
  share of E_prev (`equity_money.event.position_share.learning`, 0.05 at release 1019l: goal V3's "up to 5% of
  equity a position"), whole shares at the limit (1.25 x the previous SIP close), one share when that rounds to none
  and one share at the limit is at most 5% of E_prev (`one_share_max`) and fits every wall (BUYABLE makes at least one
  whole share fit the 5% target for every pick), at most 8 open. At E = $1,906 a learning lot is at most $95.30 at the
  limit, $66.74 on average at the fill under a stated price law (`fix1/ev_fix1.out`: log-uniform previous closes on
  [$3, $76.24]; $62.85 on [$10, $76.24]).
- PROBE and SIZED are PREREG-EVL-6 section 6's (its clause 2, A99): at Probe at most 14 open, and a Probe or Sized buy
  takes the fewest whole shares whose value at the limit reaches 0.8 of its band's target (the Probe share, 0.05 at
  release 1019l), never above 5% of equity at Probe nor the name's 10% wall at Sized, that ask judged again by every
  cap; a pick no such count reaches is skipped before it takes a slot (the shadow keeps it). Sized: a target of 10%, at
  most 8 open. Eight picks a decision bound every band. STATED UNDER V3'S ROWS: with the Probe target AT the 5%
  envelope, a whole-share count lands in [0.8, 1.0] x 5% of E at the limit only for some prices, so a pick whose
  previous close lies in about ($38.12, $60.99), ($25.41, $30.50) or ($19.06, $20.33) at E = $1,906 is skipped at
  Probe though learning buys it (`under_bar`; 22% of BUYABLE prices under the [$3, $76.24] law, 35% under the [$10,
  $76.24] law); a Probe lot of this seat is about a learning lot ($66.14 on average when bought), so promotion to Probe
  adds slots this seat's 8 picks a decision cannot use. BUYABLE therefore makes every pick buyable at learning, not at
  Probe. A later release that moves a band's size (goal V3's Kelly scale-up on promotion, up to 25% of equity a name;
  A138's NOT YET) sizes this file's version as every promoted row, inside its own walls; no shadow, judge, candidate
  or pick rule of this file moves with it.
- ROOM: AFTER EVERY BUY PLANNED BEFORE IT, AND IT KEEPS NO ROOM (check 2's major 1). This file's buys, in any band, are
  planned in this file's own pass of the scheduler (league/equity/live.py `_event_decide_slot` for file `evl10`), at
  the first book tick inside the close window [15:47:00, 15:49:00) at which all three hold:
  - (i) the main pass of D's close is done (every row of PREREG-EVL-1 to -6 AND R3's births, which the scheduler's main
    slot holds, A101's tiers inside it);
  - (ii) the pass of every file whose close row precedes this file's in the timing table (PREREG-EVL-7's, -8's and
    -9's) is decided: planned, or decided with no buy because its receipt is final without being made or its window
    closed, or it has no live program at D's close;
  - (iii) this file's live receipt `decide-close-r2:<D>` is made (`ok`).
  They come after every buy those passes planned (every name given at the auction counted as given); inside the pass,
  Sized, then Probe, then learning, then rank. While any earlier pass waits, this file's pass waits too and keeps no
  room. A buy not planned by the 15:48 tick (the first book tick at or after 15:48:00, so 15:48:03 or later) is not sent
  (binding 'window', the next bullet's (e)); the shadow keeps it. The scheduler's `_event_decide_slots` gains this wait
  for this file (on origin/feat/scheduler each file's pass waits only for its own receipt, so R2's, made by 15:44:30,
  would plan ahead of PREREG-EVL-7's, -8's and -9's). TEST: with evl7's receipt at 15:48:20, no EVL-R2-ON buy is planned
  at the 15:48 tick, and none at that close. So, AT ITS OWN AUCTION, no earlier row, R3's births included, ever waits
  for, keeps room for or is refused for a buy of this file, at learning, Probe or Sized alike. AT THE OTHER AUCTION
  (D+1's open) a promoted EVL-R2-ON (Probe or Sized) is, as every promoted row, among "the other auction's live Probe
  and Sized programs" whose cash, invested room and loss budget A85's reservation keeps (book.py `reservation`), so an
  earlier file's LEARNING buy there sizes on that room less its reservation: the one way a row of this file reaches an
  earlier row's room, A85's rule for every promoted row, unchanged (PREREG-EVL-8 section 4.2 states the same for its
  rows). (The draft put this file "before R3's births"; under the scheduler the main slot holds the births, so this
  file's pass comes after them: the reading that trades less for this file, F2.)
- THE PASS CARRIES RELEASE 1019l's PER-PROGRAM RULES (the second fix round, F18). origin/feat/scheduler's
  `_event_decide_slot` was built on release 1019h, before releases 1019i-l, so this file's pass adds the rules that
  release 1019l's `_event_decide` and `_event_decide_lrn` apply and the slot pass lacks:
  - (a) ROOM is `max_open(band, program)` less the seat count (`_event_seat_count`): 14 at Probe (PREREG-EVL-6 section
    6, clause 1), 8 at learning and at Sized. The slot pass's `max_open(band)` gives 6 at Probe.
  - (b) THE SEATABLE ROW IS ONE PREREG-EVL-6 JUDGES: EVL-R2-ON's program row reads `Program.evl6` True
    (league/events/programs.py). Release 1019l selects by that flag the versions PREREG-EVL-6's screen and bands judge
    (screen.py `_v6_programs`, bands.py) and the versions its section 6 sizes (book.py `Settings.max_open`, live.py's
    `under_bar` and `reach_bar_off` skips in `_event_gate`, the at-size count in `_size_event`, the unsettled hold). On
    release 1019l the flag is True only for PREREG-EVL-6's own versions (`regfile` 6) and for births born at or after
    REGISTERED_AT_6, so a plain row of this file would read False: 6 Probe slots, no at-size rule, no unsettled hold and
    no PREREG-EVL-6 judge (`fix2/slot_rules.out`). Its control and its two records read False, since they are never
    seated.
  - (c) PREREG-EVL-6 section 3's unsettled-stay hold as release 1019l reads it (`_event_unsettled`, A134) applies to
    its Probe and Sized buys. While a real-money Probe or Sized lot of this version is still held `LADDER_CLOSES` + 1
    (6) or more sessions after its planned exit, past the fallback ladder, the pass plans no Probe or Sized buy of it
    and records picks None, room 0 and held "unsettled". Learning lots never hold.
  - (d) THE SUMMARY IN THE AUCTION'S OWN ROW: each of its programs' entries (picks, room, planned, skipped by reason,
    where `name_given` is binding 'given', held, binding) and its sale_to_later (the sale gate's lost picks,
    `_event_sale_takers`) are written into the auction's own decision row (day, "close") as well as its own (day,
    "close-evl10"), in the same transaction as its intents, as `_event_decide_lrn` does on release 1019l. A receipt
    final without being made writes picks None, which `_event_recent` passes over. So A85's `_event_recent`,
    daily_report (`picks_a_session`), evl_health's auction counts and the alarms read this file's picks and bindings
    where they read every program's. The send's bindings (`cash`, `invested`, `budget`) are read from the intents, whose
    `at` is "close", as before.
  - (e) THE WINDOW ROW: at the 15:48 tick, a pass that still waits reads its programs' picks (section 2.4's one
    reading), plans none, and writes both rows with planned 0 and binding "window". The slot pass's own "window closed"
    row is never reached: `_event_step` stops calling the passes at close_until (15:49:00), which is where the send
    window ends. A close at which the pass still waits and no book tick falls in [15:48:00, 15:49:00) is counted
    "window" by the report, from the receipt that has no pass row.
  TEST: a promoted EVL-R2-ON at Probe holding nothing, whose real-money picks at its last five closes were 5, 6, 6, 7
  and 5, reserves min(14, 6) x 0.05 x E at the next open: $571.80, 30% of E at E = $1,906, never its whole room
  ($1,334.20, 70%; `fix2/slot_rules.out`, as `recheck2/a85_slot.out`). Its program row reads evl6 True and
  max_open("probe", row) = 14. With a Probe lot of its stay unsettled past the ladder, it plans no Probe buy. With
  every earlier pass decided only after 15:48:03, the report counts one "window" binding for that close.
- The event kind's day order line (150 orders, A74 (7), A78) refuses this file's entries after every earlier PREREG
  row's; an exit is never stopped by it. At most 8 entries and 8 exits a day.
- STATED EFFECTS, not prevented, each counted in the report (book `sale_to_later`, binding `given`, `window`, `cash`;
  the decision's counts from the auction's own row, the bullet above's (d)):
  - names an earlier row takes at D's close are lost to this file's real money: NEWS-ON issuers are EVL-NEWS-READ-ON's
    events, and the overlap is unmeasured (check 2's minor 11): R2 reads every score-3 issuer, and those are
    EVL-NEWS-READ-ON's first picks by rank (programs.py `rank = float(score)`), so it can reach most of that row's 8
    (book binding 'given' counts it); the draft's "about 1-2 names a session" came from no script and is withdrawn;
  - CASH (goal V3's 5% lots): about 20 learning lots fill the book at 100% invested, and every row ahead of this file
    at D's close (and the open-entry rows' lots still held) takes cash first, so this file's real money gets what is
    left, on many sessions none (binding `cash` or `invested`, counted);
  - THE WINDOW: on a close whose earlier passes are decided only after the 15:48 tick (the main decision near its bound,
    PREREG-EVL-7's learner part near its 120 s), this file buys nothing at that close (binding `window`, counted);
  - a lot sold at D+1's open takes the name from an earlier open row with fresh overnight news (the sale gate); the
    lots hold cash, invested room and loss-budget room at D+1's open, which earlier open-entry learning rows need (A85
    reserves only for Probe and Sized).
  None of these touches the JUDGED RECORD, which is the shadow of the live decision (section 2.6).
- Every wall, the open-risk weight max(0.10, 1.65 x sigma x sqrt(h)), the loss budget (release 1019l: $1,900 net in any
  20 sessions and $1,900 net total, realized plus open risk at the 95% holding-period loss; V2's $400 / $800 are
  superseded, A138), goal V3's bug stop (new entries paused after a 25% loss in one session, `daily_stop_share` 0.25),
  the kill switch and the stops are unchanged by this file and judge every buy.

### 2.6 The record

- EVL-R2-ON's JUDGED RECORD is the settled TRADABLE intents of its decisions made LIVE by the House under
  `decide-close-r2:<D>` (status `ok`) of the release carrying this file's code, or of a later release carrying it
  unchanged, whose events are knowable after REGISTERED_AT_10. There is no record before that release and no catch-up:
  every session between the freeze and the release is a block that does not exist (section 2.4's departure from
  PREREG-EVL-1 section 3, stated).
- The control's record for PREREG-EVL-6's READ condition is EVL-R2-ON-SET's TRADABLE intents of the same live
  decisions.

### 2.7 RS-2, a report that is never an input to any rule

Forward, on EVL-R2-ON-SET's settled TRADABLE outcomes: the Spearman IC of p_up, of surprise and of the v1 score; the
issuer-block bootstrap 95% interval (10,000 resamples, seed sha256("RS-2|" + as-of)) of IC(p_up) - IC(v1); the
per-session lift of EVL-R2-ON's picks over its SET; missing reads by cause; dollars and tokens by kind; R2_LINE by
day and the days it was 0; dollars per real entry in bp of the mean lot; real-money buys lost by binding (given,
window, cash, invested, under_bar). It is for the captain and the owner only: `reads2`, `r2_qual`, `r2_scan`,
`r2_features` and RS-2 are on births' FACTS_DENY and on the report's designer deny list, and no designer of a later
file reads them.

## 3. The judge

- PREREG-EVL-6 sections 1-3 AS FROZEN, word for word (`docs/prereg/PREREG-EVL-6.md` on the tag `prereg-evl-6`, commit
  4ae9017aaac964503a0dc8ad71965d38a08cc18d, sha256 0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057),
  under its section 1.1 LATER VERSIONS clause, with PREREG-EVL-1 section 5's a and r. EVL-R2-ON is a READ version
  whose control is EVL-R2-ON-SET (screen.CONTROLS); its own ranking for the top-14 guard is rank_key. For the reader:
  the first look at a run's 22nd settled block, looks at 22, 25, 30, 35, 40, 50 and 60 blocks with alpha 0.020, 0.006
  and 0.001, block values min(n_s, 14) x (B_s - 10 bp), RETIRE first, the run ends at its 60th block, seed strings
  f"{id}|v{version}|evl6|{tag}S{S}" with this file's id. Where the two texts differ, PREREG-EVL-6 wins, except the
  run-start rule below.
- GOAL V3'S 25% PER TEST, stated: V3 allows a false-positive rate up to 25% a test; this file's version keeps
  PREREG-EVL-6 as frozen (about 0.12 a run at the worst plausible cell, charged 0.13, section 4), well inside it. A
  faster judge at V3's line is a new pre-registration (A138's NOT YET: "the frozen judges are not edited"); this
  file's version never switches to one.
- RUNS (PREREG-EVL-7 section 1.10's rule, the same here): EVL-R2-ON's runs, Probe stays, demotion and re-promotion are
  PREREG-EVL-6's as frozen. Each run after the first is charged c10 when it starts. FOR THIS FILE'S VERSION THIS
  BULLET REPLACES PREREG-EVL-6 SECTION 3's WAIT FOR ROOM: the budget is read once, at the close at which the run would
  start; if the lane's count cannot hold c10 then, the run never starts, no later amendment that restates the budget
  revives it, and the version continues as a shadow record (R2 then asks nothing more, section 1.5). A restatement
  made BEFORE that close counts. At most THREE runs over the id's life (a run after a demotion counts). A RETIRE retires
  it for good.
- The code never edits the judge that judges it.

## 4. Expected false passes and the lane's budget

- PER RUN (PREREG-EVL-6's D11: each run is one test, which goal V3's "per test" now states in the owner's own words),
  at the consumer's own shape under the frozen screen at the widened grid's worst structures (t(3)-body crash days
  clustered in high volatility, left-skewed events, rho_day 0.15, phi_day 0.20, a 20 bp drift at AR 0.97, counts that
  follow the day), under the designer's five nulls (N1 a noise key; NK the knife, an informative key whose edge mu
  offsets exactly; NV a key that prefers volatile names whose day loadings are larger; NS a key that prefers "big news"
  that is 1.5x noisier, more left-skewed and jumpier; NI a key that prefers some issuers while issuers carry 1%
  persistent effects), each with a money-weighted pick mean of zero by construction:
  - THE WORST CELL IS THIN SUPPLY AT A STRICT FILTER (check 1's minor; the draft named NV at 5 candidates with the
    designer's 60% filter, 0.1149 pooled over 10,000, which is not the worst): NV at 5 candidates with counts that
    follow the day and a 30% filter (1.46 picks a session): 0.1250 +- 0.0052 (check 1, 4,000 programs, fresh seeds
    264,000,001+), 0.1140 (its 2,000 replicate, 266,000,001+) and 0.1123 +- 0.0050 (the fix round, 4,000, fresh seeds
    371,000,001+): POOLED 0.1177 +- 0.0032 over 10,000. W10 = 0.1250, the highest figure any plausible cell has read in
    one round of at least 4,000 programs (the reading that does not understate the rate; the pooled 0.1177 is the
    best estimate of that cell).
  - THE OTHER THIN-SUPPLY CELLS (the fix round's prompt change asks p_up about the overnight hold, which may pass fewer
    reads through p_up >= 60 than the designer's assumed 60%): NV at 8 candidates with a 30% filter 0.1177 +- 0.0051
    and a 15% filter 0.1197 +- 0.0051 (check 1); NV at 5 with a 15% filter 0.1108 +- 0.0050, at 8 with a 10% filter
    0.1003 +- 0.0047, at 3 with a 30% filter 0.1135 +- 0.0071, at 5 with a 30% filter and a 10 bp drift 0.1185 +-
    0.0072, NK at 5 with 30% 0.1040, NS at 5 with 30% 0.0995 (the fix round, `fix1/fp_fix1.worst.jsonl`); NV at 3 with
    the designer's filter 0.1030, NK 0.1060, NV at 14 with 30% 0.0805 (check 1).
  - THE SUPPLY THE NEW LINE STARVES (the fix round, `fix1/fp_fix1.starve.jsonl`, fresh seeds 372,000,001+): with
    R2_LINE driven by a trailing week whose heavy days follow the volatility regime (V_t = V_med x the 7-session
    trailing max of the frozen generator's day-count multiplier over its median; the session keeps the share
    min(1, R2_LINE / need) of its candidates, need $0.50 at a mean-count session; the line is 0 on 30-38% of sessions
    at the corner), each null's mu recomputed under the same law with the day shock's full AR state: NV at 8 with a 30%
    filter 0.0680 +- 0.0040 (L $3, V_med $1.42) and 0.0730 +- 0.0041 (V_med $1.60), NV at 14 0.0785 / 0.0655, NV at 5
    with 30% 0.0750, NK 0.0725, NS 0.0740, NV at 8 with L $3.75 0.0765, against 0.1085 for the same NV cell with no
    line. A starved session is no block, so the looks come later and the rate falls. (The phase's first run, kept in
    `fix1/v0/` as a finding, centred the null on the day's innovation only, as calib_r2.knife_mu does; under a
    trailing-week cut that left the picks' mean at +8 to +15 bp, calm weeks carrying the corner's positive day means;
    it read 0.081-0.102 and is not a result.)
  - The judge's cells (4,000 each; `calib/judge_fp.r2.jsonl`): NV at 5 with the designer's filter 0.1172 +- 0.0042
    (6,000); NV at 8 0.1100; NK at 5 0.0965; NI at 8 0.0803; NS at 8 0.0663; NV at 14 0.0828; NV at the base model
    0.0250 (2,000). The designer's (`reader2/calib_r2.final.jsonl`): NV at 5 0.1115 +- 0.0050; at 42 candidates
    0.0605-0.0890 at the corner and 0.015-0.023 at the base; every cell of its null, power2, stress and final phases at
    most 0.1115.
- THE CHARGE: c10 = max(0.13, W10 rounded up to 0.01) = max(0.13, 0.13) = 0.13, PREREG-EVL-6's frozen per-run charge
  (the same on the pooled 0.1177 or on check 1's 0.1213 over 6,000).
- PER VERSION within 120 sessions (two runs): at most about 0.22 at the worst cells (0.2155 the fix round's
  2,000-program replicate of check 1's NV at 8 with a 30% filter, which read 0.2095; 0.2137 judge; 0.2028 designer),
  also inside goal V3's 25%; with at most three runs over the id's life, about 1 - 0.875^3 = 0.33 at W10 (stated, not
  separately simulated; three runs are three tests).
- STRESSES (named, never binding: PREREG-EVL-6 section 4.3's stress list): the designer's phi_day 0.25 0.071-0.080,
  rho_day 0.30 0.078-0.087, a 30 bp drift 0.064-0.071 (`calib_r2.stress.jsonl`); the judge's harshest combination, day
  momentum phi_day 0.40 at rho_day 0.30 ON TOP OF the worst corner (t(3)-body clustered crash days, skewed events, a
  20 bp drift): 0.1755 +- 0.0085 at 5 candidates with counts that follow the day and 0.1535 +- 0.0081 at 14
  (`calib/judge_stress.jsonl`, fresh seeds 246,000,001+; PREREG-EVL-6's own fixed-program figure for day momentum at
  rho_day 0.30 alone is 0.097-0.161).
- THE LANE'S BUDGET, on PREREG-EVL-6's frozen basis (lifetime 3.9 = 30 x 0.13; goal V3 lets the captain state and
  restate a false-pass budget each week, and none is restated at this writing, A138's NOT YET), as the code on
  origin/rel/1019l counts it (`fix1/budget_fix1.py`, `budget_fix1.out`, superseding the draft's `calib/budget_judge.out`,
  which assumed no birth): the screen's own sum (screen.py `budget6`) holds 1.95 for PREREG-EVL-6's fifteen versions,
  0.26 for PREREG-EVL-7's two learners (pinned live since release 1019j, A137) and 0.52 for the FOUR seatable births
  registered since REGISTERED_AT_6 (EVL-B-NEWSDAY-NEG-C1 and EVL-B-NEWS-AFTERHRS-MILD-O1 of the night of Oct 22, A136;
  EVL-B-DAYNEWS-DROP-ON and EVL-B-DAYNEWS-S1-ON of the night of Oct 23, A137; EVL-B-8K-OFFICERS-REC is a free record):
  2.73; births.RESERVED (A137) holds 0.65 for PREREG-EVL-8's five seats and 0.30 for PREREG-EVL-9's two warm learners
  while their pins are unset. USED BEFORE THIS FILE 3.68, LEFT 0.22. THIS FILE ADDS c10 = 0.13 (RESERVED already holds
  it, A129's budget order): USED AFTER 3.81, LEFT 0.09, no whole charge. This file's lifetime draw is at most 3 x c10 =
  0.39.
- THE SEAT RULE AT THE FREEZE: the registering amendment restates USED and LEFT from R3's validator before the tag is
  pushed; if LEFT cannot hold 0.13, this file is NOT frozen (A102: R2 spends only for a seat), unless the captain
  restates the budget by amendment with its cost stated (each 0.13 is one more expected false pass).
- WHAT IT COSTS LATER RUNS, stated: with LEFT 0.09 after this file, no later run of any file starts until the captain
  restates the budget: PREREG-EVL-6's fifteen second runs (from about the 60th session after REGISTERED_AT_6) alone
  need 1.95; they start first (registration order) and wait; this file's own run 2 never starts unless a restatement
  made before the close at which it would start holds it (section 3); and seatable births pause (records stay free,
  A137).
- EVERY REPORT shows this file's expected false passes three ways (PREREG-EVL-6 section 5): the count (c10 = 0.13 a
  run), the base model (0.03 a run: 0.025 rounded up) and the stresses' worst (0.18 a run: 0.1755 rounded up), and
  beside them the per-version figure (0.22 within 120 sessions).

## 5. The calibration record (synthetic only)

- FILES: `evl10/reader2/` (the designer's: `calib_r2.py` and its phases null, power, power2, stress and final with
  their logs; `cost_r2.py`/`.out`; `ev_r2.py`/`.out`; `budget_r2.py`/`.out`; `r2_spec.py`/`.out`; `smoke_r2.py`,
  `smoke_r2.dry.out`; `evl6_frozen/` byte-identical to `docs/prereg/evl-6/`: calib_final.py e35e649d..., calib_v2.py
  d2991caa..., search_final.py 606c5407...); `evl10/calib/` (the judge's: `judge_fp.py` with `judge_fp.r2.jsonl`
  and `.log`; `judge_stress.py` with `judge_stress.jsonl`; `budget_judge.py`/`.out`; `ev_judge.py`/`.out`;
  `evl6_frozen/`, the same three files, sha256 checked against the tag); `evl10/check1/` (check 1's `fp_check1.py` with
  its r2sparse and r2filter phases, `cost_check1.py`, `SHA256SUMS`); `evl10/check2/r2_line.py` and `.out`; and
  `evl10/fix1/` (the fix round's, with `SHA256SUMS`: `r2_spec.py`/`.out` and `smoke_r2.py`/`smoke_r2.dry.out`, the
  frozen reader; `fp_fix1.py` with its phases worst, starve and power, `.jsonl` and `.log` each, run by `chain.sh` and
  `chain2.sh`, the worst phase re-run with the final script byte-identical; `cost_fix1.py`/`.out`;
  `budget_fix1.py`/`.out`; `ev_fix1.py`/`.out`; `v0/`, the starve and power phases' first run with the innovation-only
  centring, kept as a finding); `evl10/recheck1/` and `evl10/recheck2/` (the re-checks', with `SHA256SUMS`); and
  `evl10/fix2/` (the second fix round's, with `SHA256SUMS`: `slot_rules.py`/`.out`, release 1019l's own Settings,
  Program rows and A85's `reservation` on synthetic rows; `complete.py`/`.out`, COMPLETE's tests and the scans under
  the House's cadence on synthetic sessions). All copied with their sha256 into `docs/prereg/evl-10/` at the freeze.
- THE CONSUMER MODEL (`calib_r2.py`): each session the SET holds N_t ~ Poisson(Nbar x Gamma(3, 1/3)) issuers (count CV
  0.58), drawn by popularity as the frozen generator draws a control's events (Zipf 0.8 with Gumbel noise, a hot
  sector on half the sessions), optionally with counts that follow the day (D14); each candidate passes the filter
  with probability 0.6, or by the reader's own fields (finf) at a stated share; the seat takes the top 8 passing by its
  key outside a 5-session cooldown. Each event's a = mu + drift + h_t (l_i c_t + sector + factors + sigma_i e) + jumps
  + issuer effect + alpha_i, the frozen generator's terms (calib_v2.py), alpha_i the TRUE news value (sd_alpha x N(0,
  1)) and the key c x alpha / sd_alpha + sqrt(1 - c^2) x noise (c the reader's information). The screen: PREREG-EVL-6's
  rule with calib_final.py's sign-flip p, its 19,999 fixed vectors (the House uses 99,999), its z >= 1 prefilter and
  its issuer guard; RETIRE first; PASS with the guards, the control, p_I <= 0.10 and the 30 / 30 / 6 minimums; run 2
  after the 60th block. THE LINE (the fix round, `fp_fix1.py` `make_draw`, `cut`, `pilot_mean`): calib_r2.draw_session
  unchanged, then the line's cut of section 4's third bullet; each null centred by a pilot of the same law with the day
  shock's full AR(1) state; each power cell's mu shifted by the line's own regime effect (common random numbers with and
  without the cut), so it differs from its twin in supply alone.
- POWER (the designer's fresh seeds, base model, 2,000 programs a cell; P(run 1 passes by session 120), the picks'
  mean a after the replay's cost):

  | true news value sd | c 0.3 | c 0.5 | c 0.7 |
  |---|---|---|---|
  | 0.4% | +1.5 bp, 0.024 | +11.0 bp, 0.048 | +21.1 bp, 0.067 |
  | 0.8% | +16.6 bp, 0.052 | +35.7 bp, 0.150 | +55.2 bp, 0.299 |
  | 1.5% | +42.3 bp, 0.182 | +78.7 bp, 0.522 | +116.2 bp, 0.827 |

  At the worst corner the same cells read 0.068-0.69, inflated by drift luck (the null there reads about 0.07). THE
  LINE'S COST IN POWER (the fix round, `fp_fix1.power.jsonl`, fresh seeds 373,000,001+, the base model with counts that
  follow the day, sd 0.8%): at c 0.5, 0.1320 with no line, 0.1435 (L $3, V_med $1.42), 0.1380 (V_med $1.60), 0.1330 (L
  $3.75); at c 0.7, 0.2820 / 0.2845 / 0.2850 / 0.3050, all within two standard errors (about 0.008-0.010); picks a
  session 7.65 / 6.05 / 5.12 / 6.62. The line costs supply (a fifth to a third of the picks, and real-money buys with
  them), not measurable power by session 120. THE HONEST BOTTOM LINE: at 8 picks a session and a first look at block
  22, the seat is promoted within 120 sessions with probability above 0.3 only if the reader is strong (c >= 0.7 on a
  0.8% dispersion of true news value, or c >= 0.5 on 1.5%). Nobody can know c before the forward record exists.
- DESIGN CHOICES THE CALIBRATION MADE (the designer's, kept): K = 8 (K = 4 gave +26.6 bp but only 3.9 picks a
  session); 40 news reads, not 24 (+10 bp, P(pass) 0.106 to 0.158, `calib_r2.power2.jsonl`); one seat.
- LIMITS: the filter's pass share (0.6, and 0.10-0.30 in the thin cells), the dispersion of true news value and c are
  assumptions; the line's model (its V from the day-count multiplier, the $0.50 need, the order of the cut) is a
  stylization of rules whose real inputs (v1's daily dollars, R2's per-read cost) are not in the outcome-free facts; no
  cash or fill model; 19,999 sign vectors instead of the House's 99,999; calib_r2.py was extended after its null,
  power and stress phases ran (per-cell k, finf and the final phase) with defaults that reproduce every earlier phase
  from its seeds.

## 6. The red team's causes and their guards (`evl10/redteam/`, C1-C12; and the lens's named causes)

- C1 THE CLOCK (no look before the 22nd block; a real +60 bp edge at 8 a session is still unpromoted at session 30
  with probability 0.64-0.80, `redteam/screen10.power`). No guard inside the frozen screen; none is taken (A114 gave
  speed up for honesty). This file spends no charge while it waits: c10 is charged once; its R2 dollars stop with the
  seat; the six-week read is RS-2 and the learning P&L, never a promotion.
- C2 HFT PRICED THE ITEM: not this file's cause; it enters at the close auction, hours after its news, and holds the
  night (section 0, item 7).
- C3 READER-2 ADDS COST WITHOUT INFORMATION. Guards: the read count follows the slots (about 40 news a session by the
  hash share, up to 64 on a heavy score-3 day, at most 8 8-Ks, section 1.4), not the feed; R2's dollars inside the
  lane's line, never above R2_LINE ($0.75 at most), so no cap breach and v1's 1.5 V kept; one model, no cascade, no
  Opus; spend follows the seat (section 1.5). Its price: $0.140 / $0.411 a day at the designer's counts, $0.602 at the
  caps' mid, at most $0.75; 3.5 / 10.3 / 15.0 / 18.7 bp of a V3 learning lot a traded event at 6 buys a session
  (`fix1/ev_fix1.out`); the mid day is 8.2% of release 1019l's $5 rule and 4.1% of goal V3's $10. (A102 priced
  metered compute at about 6 sessions of time-to-Done per metered dollar a session in the best scenario; it was
  modelled under goal V2's Done and $5 line, Done is now V3's, and the conversion is not re-derived here.) The red
  team's IC spend stop is not taken (it stops a worse reader at most 0.197 of the time by 60 sessions,
  `redteam/futility10.out`); the measured cost of a worthless reader is its spend: about $49 over 120 sessions at the
  mid cost, $72 at the caps' mid, at most $90 at the line, less on the days the line starves it.
- C4 THE SPREAD THE AUCTIONS NEVER PAID: not this file's (auction entry and exit; real fills printed at the replay's
  prices, EXECUTION-FACTS).
- C5 THE BUDGET CROWDS OUT: one seat only (0.13), registered only if LEFT holds it at the freeze (section 4); the
  records feed EVL-META-ON at no charge (section 2.3); three runs at most, the budget read once at each start. With
  LEFT 0.09 after it, this file is the last seatable charge before a restatement (section 4).
- C6 A MIS-COSTED REPLAY: not this file's (PREREG-EVL-1 section 5's auction replay, whose assumed 14-24 bp sits above
  the measured 0 bp, EXECUTION-FACTS).
- C7 JUDGED IS NOT TRADED VIA LATE READS: a read not answered before tau is missing for the shadow and for money
  alike, and section 2.4's ONE READING makes real money and EVL-META-ON's members read exactly the live decision's
  intents (no read answered, and no 8-K or article stored, after tau reaches either); the shadow never waits; the E10
  bar and BUYABLE are in the candidate definition, so the record holds only names the guards let money buy at learning.
- C8 DRIFT BEHIND 'claude-sonnet-5-5' (Chen, Zaharia and Zou 2023, arXiv:2307.09009) AND UNTESTED json_schema: THE PIN
  (a changed response model string stops R2 for good), THE SCHEMA STOP, the smoke test (whose report prints the pin)
  and the R2-J fallback, pinned before the freeze; the first stored answer is final and replay is from the store
  (sections 1.5, 1.7). Canaries are not taken (item 3 of section 0).
- C9 PLUMBING: R2's asks run as per-call jobs on their own House lane 'reader', never on the lane's slot or on 'ops';
  the decision is SQL only in its own scheduler slot ending before the lane's close decision; its buys are planned in
  its own pass after every earlier pass and keep no room, with release 1019l's per-program rules and its summary in
  the auction's own decision row (section 2.5); its code ships only with the scheduler.
- C10 KNOB MULTIPLICITY: every constant is fixed here, blind; one seat; the records are free and never seated by this
  file; FEATURES-R2 v1 is all or none for any later file.
- C11 SEASON: no earnings 8-K is read; NEWS-ON runs all year; the read count is fixed by the hash share and the
  score-3 rule, not the season.
- C12 GATEWAY CAPS: at most 8 entries and 8 exits a day against the 150 / 250 / 300 lines; not binding on a typical
  day (about 23.5 real buys a session over every program on Oct 20-21, SPEED-FACTS); the 150-order line refuses this
  file's entries after every earlier row's when it does bind.
- THE LENS'S NAMED CAUSES, the rest: STRUCTURED OUTPUTS DRIFT (C8); MULTIPLICITY (C10); the DEPLOY WINDOW (R2 sends no
  order; its reads run from 07:30 ET, partly before the 12:55Z block begins, so a deploy before 12:55Z may cut one
  streamed call, stored `lost` at its hold; the code ships from a deploy window and its record is live-only, so
  nothing is lost but the sessions before the release); the 15 bp FILL CRITERION (auction fills, 0 bp measured).
- CORRELATED PASSES (the red team's risk list): NEWS-ON events are EVL-NEWS-READ-ON's v1 >= 2 events, so a drifting
  family can pass both (PREREG-EVL-6's N2+ case); the beat-the-control condition compares the picks with the same
  v1 >= 2 liquid set, and Done's issuer-block bound and realized P&L are the backstop.
- THE LINE'S STARVATION (the fix round's own): R2's supply falls on sessions after a heavy v1 week, which follow the
  volatility regime; measured, it lowers the false-pass rate (section 4) and costs supply, not measurable power
  (section 5); the days it bites are counted (RS-2: R2_LINE by day).

## 7. Cost and expected value (synthetic power, stated priors, goal V3's sizes)

- PER READ (`fix1/cost_fix1.out`: the designer's token model on the fix round's texts): news $0.0023 / $0.0071 /
  $0.0171, doc $0.0090 / $0.0184 / $0.0311 (lo / mid / hi; mid tokens news 1,356 in / 375 out, doc 5,276 / 615). A
  DAY: $0.140 / $0.411 / $0.968 at the designer's counts (39-50 reads), $0.220 / $0.602 / $1.344 at the caps (64 news
  + 8 docs); never above R2_LINE ($0.75 at most; $0.62 at V = $1.42). PER TRADED EVENT at 6 buys a session and V3's
  mean learning lot ($66.74 at the fill): 3.5 / 10.3 bp at the designer's lo / mid, 15.0 bp at the caps' mid, 18.7 bp
  at $0.75. BREAK-EVEN PICK EDGE at the mid cost: 10.3 bp at 6 buys (12.3 at 5, 8.8 at 7); at the caps' mid 15.0 bp.
  (The draft's 6.1 / 17.9 / 42.4 bp of a "$38" lot and its 15.4-21.5 bp break-even were V2's 2% lots, at the limit.)
- AGAINST THE LINE: at release 1019l's rule with no profit, the fixed costs $1.66 (Sail's boxes at the rule's own
  $1.50 example, Cloudflare $0.16) + the lane's line $3.00 (v1 about $1.30-1.42 a day at Oct 21's volume, HOUSE-FACTS
  $0.000896 a verdict; the births at most $0.25 a night; R2 at most R2_LINE) + the old research roles' $0.34 = the $5.00
  cap: R2 adds no dollar to the cap, it uses the lane's line where v1 and the births leave room. Under goal V3's $10
  (once a release moves the rule) the lane's line stays $3 unless that release raises it; at L = $3.75 R2_LINE would
  be $0.75 up to V = $1.83 and 0 only from V = $2.33, and the line would starve 24% of sessions at the corner instead of
  30-38% (`fp_fix1.starve.jsonl`).
- EXPECTED VALUE over 120 sessions (`fix1/ev_fix1.py`, `ev_fix1.out`; V3's lots at E = $1,906 at the fill: learning
  $66.74 at 6 buys a session, Probe $66.14 at 7 less the 22% under_bar skips, Probe from the first pass; power from
  the designer's fresh seeds; no starvation):

  | the reader's information | picks' a | P(promoted by 120) | P&L | net of R2 at the mid / caps' mid / $0.75 | P&L per metered $ (mid) |
  |---|---|---|---|---|---|
  | none (c 0) | 0 | 0.019 (false) | $0 | -$49 / -$72 / -$90 | 0 |
  | c 0.3, sd 0.8% | +16.6 bp | 0.052 | +$79 | +$30 / +$7 / -$11 | 1.61 |
  | c 0.5, sd 0.8% | +35.7 bp | 0.150 | +$170 | +$120 / +$97 / +$80 | 3.44 |
  | c 0.7, sd 0.8% | +55.2 bp | 0.299 | +$259 | +$210 / +$187 / +$169 | 5.25 |
  | c 0.5, sd 1.5% | +78.7 bp | 0.522 | +$363 | +$314 / +$291 / +$273 | 7.36 |

  UNDER THE JUDGE'S STATED PRIOR (none 0.40, c 0.3 0.25, c 0.5 0.20, c 0.7 0.08 at sd 0.8%, c 0.5 at sd 1.5% 0.07: a
  judgment, not data): E[P&L] +$99.9, net +$50.5 at the mid cost (+$83.1 at the low, +$27.6 at the caps' mid, +$9.9 at
  $0.75), P&L per metered dollar 2.02; true promotions per 0.13 charge 0.103; false promotions per charge 0.008 (base)
  to 0.050 (W10). WITH THE LINE'S STARVATION (picks and R2's dollars scaled by the line cells over their twins):
  E[P&L] +$78.8, net +$39.8 at the mid (L $3, V_med $1.42); +$66.8, net +$33.8 (V_med $1.60); +$86.3, net +$43.7 (L
  $3.75). AT V3's ROWS PROMOTION ADDS LITTLE MONEY TO THIS SEAT: a Probe lot is about a learning lot and Probe skips
  under_bar names (section 2.5), so the P&L is mostly learning P&L, and Sized (10%) is not reached within 120 sessions
  in this model. THE CASH CAVEAT: every figure assumes 6 real buys a session; this file's buys come after every earlier
  row's at D's close, and with 5% lots the book fills at about 20, so cash may leave it fewer (P&L scales with the buys;
  at 3 a session it halves, and R2's dollars do not). The draft's figures (+$70.6, net +$21.5) were V2's lots. The real
  auction fills printed at the replay's prices while the replay charges 14-24 bp, so the money figures are
  conservative on that count.

## 8. Why this, and what argues against it (the judge's prior, stated before any outcome)

- FOR: the fields priced by the literature, read where the texts state them: novelty and staleness (Tetlock 2011, RFS
  24(5); Fedyk and Hodson 2023, JFE 149(1)); news against no-news drift (Chan 2003, JFE 70(2)); analyst actions and
  targets (Womack 1996, JF 51(1); Brav and Lehavy 2003, JF 58(5)); results against expectations (Bernard and Thomas
  1989, Journal of Accounting Research 27); management guidance (Anilowski, Feng and Skinner 2007, Journal of
  Accounting and Economics 44); 8-K item materiality (Lerman and Livnat 2010, Review of Accounting Studies 15(4)); and
  language models reading headlines (Lopez-Lira and Tang 2023, arXiv:2304.07619). Every event postdates the model's
  training (the look-ahead concern of Glasserman and Lin 2023, arXiv:2309.17322). The seat holds the night after
  attention news (Berkman, Koch, Tuttle and Zhang 2012; Lou, Polk and Skouras 2019), its key asks about that night,
  and it is compared with the same v1 >= 2 liquid set, so "beats its control" is exactly the claim that the stronger
  reader adds information over v1.
- AGAINST: language-model predictability concentrates in small stocks and negative news (Lopez-Lira and Tang), which a
  long-only seat at adv20 >= $10M can use only by avoidance; published effects decay (McLean and Pontiff 2016, JF
  71(1)); v1 is already a language model, and PREREG-EVL-7's learners already take the free headline flags; at 8 picks
  a session PREREG-EVL-6 promotes slowly at any edge below about 60 bp; the overnight p_up may cluster near 50 and pass
  few reads (the thin cells of section 4 measure what that does to the rate, not to the edge). Strength: weak to
  moderate.

## 9. What is unchanged

Everything this file does not state is PREREG-EVL-1's to -9's, word for word: the universe, the events, the knowable
times, backfill and the shadow rule (but this file's rows' live-only record, section 2.4, stated); the verdicts, their
model, prompts (PROMPT-DOC and PROMPT-NEWS and their SHA-256), parsing and the rule that the first stored answer is
final; the lane's verdict line (now shared with R2 inside it, section 1.5); the execution model, auction prices, the
fallback ladder, costs, per-event returns and TRADABLE; every earlier program, record and control and their places in
ROOM ahead of this file's rows (EVL-META-ON's sources rule included, section 2.3); the screens; the bands, Sized,
demotion and retirement; the money walls as release 1019l holds them under goal V3 (a cash account: no margin,
borrowing, shorts or option sales; <= 10% of equity a name at the book and at the gateway's STOCK_EVENT_SHARE_MAX;
<= 100% invested), the loss budget ($1,900 net in any 20 sessions, $1,900 net total, realized plus open risk at the 95%
holding-period loss), the open-risk rule, the bug stop (25% in one session), the kill switch and the stops; Done
(read by `league/events/done.py`, whose loss total release 1019l set to $1,900; goal V3's Done text is the owner's and
is read by that reader's releases, not by this file), pivot and reporting.

## 10. Honesty

- BLIND DESIGN. The four designers, the judge, the two checks, the fix round, the two re-checks and the second fix round
  worked under the rule stated in the header; none read, queried or computed any outcome, price after an event, look,
  band, mark, bar or P&L of any event, symbol or program. They read the frozen rules, the drafts, the code (read only,
  git show), the outcome-free facts and the literature, and ran synthetic simulations only. Every constant here (the
  read sets, the hash share and its target 40, the caps, the filter, the key, K = 8, tau, the lines and R2_LINE's
  formula, the stops, the 21 columns, the prompts' p_up line) was fixed on code, counts and synthetic paths.
- WHAT THE JUDGE SAW BESIDE THE RULES, stated: reading the handoff (`goal-2026-10-19/NEXT-AGENT.md`) and the
  amendments record for the release and budget state, the judge saw account-level and lane-aggregate figures written
  there by the captain (the account-shown profit about -$480 and Net about -$1,385 at Oct 22's cut-off; "event lane
  real money ~flat (46 closed); no edge"; earlier aggregate realized figures and loss-budget room; A96's line that
  three sessions showed no program clear of noise). No per-program, per-family or per-event figure was seen, and no
  rule here was chosen from them. The judge did not run `evl10/intraday/count_idn.py` and read no store.
- WHAT THE FIX ROUND SAW, stated: the draft; CHECKS.json (all of it, to separate this file's findings from
  PREREG-EVL-11's); check 1's and check 2's scripts and outputs; the designer's and the judge's scripts and outputs;
  goal V3's text; the amendments A98-A105 and A119-A138 (A138 names the account figure $1,906 of goal V3's Done and
  "$1,900 ... about the balance on Oct 23"; A136 and A137 the births registered and the budget's room; A125 A96's
  basis line); SPEED-FACTS' header (equity about $1,898, the walls) and HOUSE-FACTS' verdict count and dollars; the
  frozen texts on their tags; the code on origin/rel/1019l and origin/feat/scheduler (git show); and the registered
  births' specs in docs/births/*.jsonl (ids, families, auctions, seatable flags). No per-program, per-family or
  per-event figure was seen and no store, House, gateway or run record was read. The fix round ran only the smoke
  test's DRY run; `smoke_r2.py --send` is the captain's.
- WHAT THE SECOND FIX ROUND SAW, stated: this file; the two majors as the workflow passed them; re-check 2's
  `recheck2/a85_slot.py` and `.out`; the code on origin/rel/1019l and origin/feat/scheduler (git show; release 1019l's
  tree at 3df7dd9d imported read only, no bytecode written, for its Settings, Program rows and `book.reservation`);
  PREREG-EVL-6's frozen text on rel/1019l; the amendments record's headings A130-A139 and the text of A134 with its
  addendum (the stay-look reading and the v6 sizing). It wrote only `evl10/fix2/` and this file; it read no store,
  House, gateway or run record, saw no per-program, per-family or per-event figure, and did not run `smoke_r2.py
  --send`.
- THE CAPTAIN: the registering captain session (6e6a85b9) had read, on Oct 21 and 22, per-program shadow means and
  session-clustered t-statistics of the existing programs over Oct 19-21 and the lane's aggregate real-money figures;
  it wrote A119 and the workflows' prompts, and it chose none of these rules; it changes nothing in them but the
  checks' stated fixes, WRITTEN_AT, the smoke test's pin and tokens (or R2-J) and the registration fields. For that
  reason this file counts only events knowable after REGISTERED_AT_10 and only decisions the House makes live after
  its release.
- OUTCOMES AT RUN TIME: none. R2, its decision and its records read no price after any event and no outcome; the only
  prices they read are D's universe row's prev_close and adv20 and E_prev, as every earlier file's rules do; R2_LINE
  reads only metered dollars. RS-2 and the screen read settled outcomes forward, after the decisions they judge.
- IMPLEMENTATION LEAKS, AND THE GUARDS: a read answered after tau, an 8-K stored after tau, an eligibility result or a
  universe row written after the decision, or a row rewritten after it would leak; so would a real-money or META
  reading of this file's rows at a later decided_at. Guards: every cut-off is a stored time (answered_at, stored_at,
  received_at, decided_at before tau); `reads2`, `r2_qual`, `r2_scan` and `r2_features` are write-once; the decision is
  SQL only and fixed by stored times; section 2.4's one reading; the tests of section 11.

## 11. What is not decided here

The code (league/events/reader2.py: the constants copied verbatim from `fix1/r2_spec.py` with a test that compares them,
the renderers with read_day and their 30-day prior builders, qualification and choice, the scans and `r2_scan`,
COMPLETE, the asks with `gw.post_stream`, the statuses, the pin, R2_LINE and the cap hold, the stops, parse, features;
store.py's four additive tables; league/house.py's new lane 'reader' (`_lanes`, `_background`'s key 'reader:r2') and the
per-call job; league/events/house.py's `_spend_today` adding `reads2.usd` (a lost or unpriced call at its hold) and
R2_LINE's inputs (`verdict_line`'s L, the trailing 7 days' heaviest verdict day V); its metered accounting
(league/ops/metered.py, budget.py, daily_report and evl_health add `reads2.usd`); the scheduler row `close-r2` (the last
of the close table) and its part (`scheduler.register(Part("evl10", run=..., catchup=None, ...))`); the scheduler's
per-file pass waiting for every earlier file's pass (`_event_decide_slots`); this file's pass sizes room by
max_open(band, program) and the seat count, applies PREREG-EVL-6 section 3's unsettled hold, writes its summary into the
auction's own decision row, and writes its "window" row at the 15:48 tick (section 2.5, (a)-(e)); programs.py's rows,
EVL-R2-ON's reading `Program.evl6` True (section 2.5 (b)), REGISTERED_AT_10 and SEATING_PREREGS gaining 10 (and
births.RESERVED's 0.13 released by that pin); book.picks for this file's four rows as section 2.4's one reading
(`r2_picks`, as `learner_picks`); screen.CONTROLS mapping EVL-R2-ON to EVL-R2-ON-SET; births.py's FACTS_DENY gaining
reads2, r2_qual, r2_scan and r2_features; report.py's READER block, RS-2 on the deny list; alarms reader_line,
reader_pin, reader_schema, reader_stop, reader_missing (under 85% of chosen reads answered by tau two sessions running),
r2_starve, r2_cap (64 news reads reached)), the site and the docs, built after this file to these rules; the build's
plan is a guide and this file wins. The tests it must carry: an R2 write leaves `verdicts` and every earlier program's
intents byte-identical, except EVL-META-ON's and EVL-META-ON-POOL's, whose members from this file's rows are exactly
section 2.4's one reading; the decision is identical with rows stored, answered or written after tau added; a read
answered at tau + 1 s is missing for shadow and money; a read answered at tau + 30 s and an 8-K stored at tau + 60 s
change neither the book's picks at 15:46 nor META's members; BUYABLE, EXCLUDED and the E10 bar read as stored before
tau; the hash share; COMPLETE (scans from 07:31:10 every 90 s to 15:38:40 make the session COMPLETE; one gap of 5
minutes 1 second does not, `fix2/complete.out`); the caps; the pin and schema stops; R2_LINE (at V = $1.30 / $1.42 /
$1.60 / $1.83: $0.75 / $0.62 / $0.35 / $0) and the cap hold, and that a day of R2 at its line plus v1 at 1.5 V plus the
births' $0.25 stays inside L; the first stored answer final; with evl7's receipt at 15:48:20, no EVL-R2-ON buy that
close; section 2.5's TEST of the pass's per-program rules (A85's reservation of a promoted EVL-R2-ON at 30% of E, never
70%; evl6 True and 14 Probe slots; the unsettled hold; one "window" binding); a run refused when the budget cannot hold
it; no R2 table read by births' facts; R2's asks never on the 'feeds' or 'ops' lane. If an implementation finds a rule
here ambiguous, it takes the reading LESS LIKELY TO PASS (screen rules) or that TRADES OR ASKS LESS (trading and reading
rules), recorded as an amendment before the release that carries the code; a later resolution is a new version.

## 12. The fix rounds' changes (Oct 23, `evl10/fix1/` and `evl10/fix2/`), finding by finding

Every finding of `evl10/CHECKS.json` that concerns this file, and every change the fix round made on its own, with
where it sits (F1-F16); then the two majors of the re-checks and the second fix round's changes (F17, F18).
PREREG-EVL-11's findings are another workflow's and are not touched here.

- F1, CHECK 2 MAJOR 0 (real money and EVL-META-ON read the R2 rows through book.picks at a later decided_at, so they
  could buy or take as members picks built from reads answered, and 8-Ks or articles stored, after tau): APPLIED.
  Section 2.4's ONE READING (book.picks of the four rows is the live receipt's intents for any t, every input cut at
  tau, empty with no receipt) and its test; cited from sections 2.3, 2.5 (C7) and 11; section 2.3's claim "which
  reads the same reads as this file's decision because no R2 call is made after tau - 30 s" replaced by the one
  reading. Verified on origin/feat/scheduler (live.py `_event_decide_slot` asks `adapter.picks(..., decided_at=
  em.close_decide)`, the close - 14 minutes) and origin/rel/1019l (book.py `picks` re-runs `select` before
  decided_at; `learner_picks` is the precedent).
- F2, CHECK 2 MAJOR 1 (ROOM under the scheduler as built: R2's receipt by 15:44:30 would plan its pass at the first
  close tick, ahead of PREREG-EVL-7's, -8's and -9's passes): APPLIED, with one part changed. Section 2.5's ROOM: the
  pass waits for the main pass, every earlier file's pass and its own receipt; the last tick 15:48; the scheduler's
  wait; the test. CHANGED: the check's interim path ("until the scheduler ships, after PREREG-EVL-9's late pass") is
  replaced by THIS FILE NEEDS THE SCHEDULER (section 2.4): this file's decision is itself a scheduler slot, so without
  the scheduler there is no live receipt to plan from, and an interim path would be new timing nobody checked.
  ADDED by the fix round: the scheduler's main slot holds R3's births, so this file's pass comes after them, and the
  draft's "before R3's births (A101)" and "the last program of each pass before the band's births" are withdrawn
  (the reading that trades less for this file); A85's reservation at D+1's open stated, as PREREG-EVL-8 section 4.2
  states it.
- F3, CHECK 2 MAJOR 2 (section 0 and section 1.1 said no earlier program reads R2, yet PREREG-EVL-8 section 7.2 makes
  the four rows EVL-META-ON sources, and the byte-identical test would fail): APPLIED. The exception in section 0's
  first bullet, section 1.1's last bullet and section 2.3, and the test's exception in section 11. ADDED: if
  PREREG-EVL-8's code reads its section 7.2's first bullet so that these rows give no members, that reading is
  PREREG-EVL-8's (section 2.3).
- F4, CHECK 2 MAJOR 3 (R2's $0.75 line sat outside THE COST RULE, whose lines already take the whole $5 cap; guard (b)
  saw only spend so far; a breach zeroes v1's line): APPLIED. Section 1.5: R2's dollars in the lane's line, R2_LINE =
  max(0, min($0.75, L - 1.5 V - $0.25)) fixed at the day's first ask, no cap hold, binding v1_reserve; section 0 item
  2; the draft's $5.00 metered-day guard withdrawn. RE-MEASURED: R2_LINE's table and the reads it buys
  (`fix1/cost_fix1.out`); the supply it starves as a false-pass and power calibration on fresh seeds (sections 4, 5;
  `fp_fix1.starve`, `fp_fix1.power`); the money it costs (section 7).
- F5, CHECK 1 MINOR (the stated worst cell was not the worst; stricter filters read higher): APPLIED, and
  re-measured. Section 4: check 1's cells; a fresh 4,000-program replicate of its worst cell (0.1123) and six more thin
  cells on fresh seeds 371,000,001+ (`fp_fix1.worst`); W10 = 0.1250 (the highest single round; pooled 0.1177 over
  10,000, check 1's 0.1213 over 6,000); c10 = max(0.13, 0.13) = 0.13; check 1's files copied at the freeze.
- F6, CHECK 2 MINOR 11 (the read count and cost were understated: every score-3 issuer is read whatever h; the overlap
  "about 1-2 names a session" came from no script): APPLIED. Section 1.4's last bullet; section 2.5's stated effects;
  section 7 prints the caps' figures ($0.220 / $0.602 / $1.344) beside the designer's.
- F7, CHECK 2 MINOR 12 (p_up asked "over the next trading day", not about the seat's hold): APPLIED. Both prompts'
  p_up line and "Read on {read_day}." (`fix1/r2_spec.py`); new shas R2-NEWS a8239614... and R2-DOC 127c19f3...
  (section 1.1); the smoke copy `fix1/smoke_r2.py` (section 1.7). RE-MEASURED: the thinner filter the new horizon may
  give (section 4's thin cells, F5).
- F8, CHECK 2 MINOR 13 (a) (R2's House lane unnamed; 'feeds:' is the lane's one slot and an unknown key falls to
  'ops'): APPLIED. Section 1.5's WHEN (lane 'reader', key 'reader:r2', per-call jobs on the House's publishes); section
  6's C9; section 11. (Its EVL-11 half is not this file's.)
- F9, CHECK 2 MINOR 13 (b) (the no-catch-up rule departs from PREREG-EVL-1 section 3 without saying so): APPLIED.
  Sections 2.4 and 2.6, with "the code ships in the first release after the freeze that passes its review, never held
  for any figure".
- F10, CHECK 2 MINOR 13 (c) ("Opus's prices are exactly twice Sonnet's", but cache hits are $0.20 for both): APPLIED.
  Section 1.1 (checked on origin/rel/1019l's gateway/wrangler.jsonc CLAUDE_MODELS).
- F11, CHECK 2 MINOR 13 (d) ("complete in r2_qual" undefined): APPLIED. Section 1.4's COMPLETE, read from a new
  write-once `r2_scan` table (section 1.3), so the definition is a stored fact.
- F12, CHECK 2 MINOR 13 (e) ("never chosen after outcomes exist" beside "a captain who will have seen RS-2"):
  APPLIED. Section 1.6's wording.
- F13, GOAL V3 (the fix round's brief: update every figure taken from V2 and say so): the header's goal quote (V3's
  25% per test, 5% positions, the $10 line); section 0 item 1 (BUYABLE's reason: V3's 5% learning position); section
  1.5 (the $5.00 guard withdrawn; V3's $10 against release 1019l's $5 rule, R2 inside either); section 2.5 (learning
  5% and Probe 5% from the money table, the Probe skip bands stated, the loss budget $1,900 / $1,900, the 25% bug stop,
  later size releases sizing this version as every promoted row); section 3 (V3's 25% stated beside the frozen judge);
  section 4 (the per-test reading in the owner's words; per version inside 25%); sections 6 and 7 (costs in bp of V3's
  lots; A102 marked as V2's and not re-derived; the expected value recomputed at V3's lots, `fix1/ev_fix1.out`);
  section 9 (V3's walls as release 1019l holds them). E = $1,906 (goal V3's figure) replaces the draft's $1,898.
- F14, THE BUDGET (the fix round's own): the draft's section 4 counted no birth; four seatable births have registered
  since (A136, A137) and births.RESERVED holds the frozen files' charges (A137). Restated from the code on
  origin/rel/1019l (`fix1/budget_fix1.out`): USED 3.68 before this file, LEFT 0.22; after it 3.81, LEFT 0.09; and what
  that costs every later run (section 4).
- F15, THE SMOKE TEST (the fix round's own): the designer's smoke script did not print the response's `model` string,
  which section 1.7 makes THE PIN; the fix round's copy prints it, and its NEWS worst case is $0.0061 with the longer
  text (the designer's $0.0060 no longer bounded it).
- F16, CASH AND THE WINDOW (the fix round's own): stated effects of V3's 5% lots and of the new ROOM on this file's
  real money (sections 2.5 and 7), never on its record.
- REJECTED: no blocker or major is rejected. One part of F2 (the interim late-pass path) is replaced, for the reason
  stated there.

THE SECOND FIX ROUND (Oct 23, `evl10/fix2/`). Re-check 2 (honesty and implementability) found the first round's changes
applied (check 2's majors 0-3, its minors 11, 12 and 13 (a)-(e), check 1's minor, the V3 figures and the budget) and
returned two new majors; both are applied. No figure of sections 4, 5 or 7 moves: neither change touches the shadow, the
screen, the read count's target, the costs or the budget.

- F17, RE-CHECK 2'S MAJOR ON COMPLETE (COMPLETE needed a stored scan at or before 07:30 ET and one at or after tau - 30
  s, but the scans start at 07:30:00 on the House's publishes and stop at tau - 30 s, so no session is ever COMPLETE and
  q(D) is 0.5 for good; "scans at least once a minute" was not the publish cadence): APPLIED. Section 1.4's COMPLETE
  restated as the check's text gives it (07:30:00 and tau - 30 s counted as the first and last times, no gap over 5
  minutes); "scans at each job the House's publishes start"; section 1.5's WHEN states the cadence (at most once a
  minute, 60-121 s apart in session) and one job at a time; section 11's test. CHANGED from the check's text: its test
  grid "from 07:31:10 every 90 s to 15:39:05" does not land on 15:39:05 (29,275 s is not a multiple of 90), so the test
  reads "to 15:38:40". RE-RUN (`fix2/complete.py`, `complete.out`, seed 202610232, 20,000 synthetic sessions a cell): as
  in the check's 100,000 sessions, the first wording makes no session COMPLETE; under the restated rule every session
  with no House stall is COMPLETE whether a call is due at 0%, 30% or 100% of jobs (the largest gap 211 s), 31% are with
  a 4-minute stall and none with a stall over 5 minutes; the frozen `r2_spec.share` then leaves Q_DEFAULT (q = 0.4211 at
  a mean of 95 qualifying issuers). r2_spec.py and the request shas do not change (COMPLETE is this file's text, not the
  spec's).
- F18, RE-CHECK 2'S MAJOR ON THE SLOT PASS (section 2.5's pass, built on origin/feat/scheduler's `_event_decide_slot`,
  drops release 1019l's per-program rules: its summary sits only under (day, "close-evl10"), which A85's `_event_recent`
  never reads, so a promoted EVL-R2-ON reserves its whole room at every open; its room is `max_open(band)`, 6 at Probe;
  it has no unsettled-stay hold; its "window closed" row is dead code): APPLIED, with one part added. Section 2.5's new
  bullet THE PASS CARRIES RELEASE 1019l's PER-PROGRAM RULES, (a) room, (c) the unsettled hold, (d) the summary in the
  auction's own row, (e) the window row, and its TEST; section 11's code list and tests; section 6's C9. VERIFIED on the
  code: origin/feat/scheduler forks from release 1019h (merge base 59663f06), and its `_event_decide_slot` sizes by
  `s.max_open(inst.band)` and writes only (day, f"{at}-{file}"). On origin/rel/1019l, `_event_recent` reads `WHERE at=?
  AND status='done'` with at "close"; `_event_decide_lrn` merges its programs and sale_to_later into the main row;
  `_event_decide` uses `max_open(band, program)`, `_event_seat_count` and `_event_unsettled`. `_event_step` calls the
  passes only while now < close_until (15:49:00), the end of every close send window (event.order_path
  close_until_before_close_s 660). ADDED (b), found while applying (a): on release 1019l, `max_open(band, program)`
  gives 14 only when `program.evl6` is True, and `Program.evl6` is True only for `regfile` 6 and for births born at or
  after REGISTERED_AT_6. The same flag selects PREREG-EVL-6's screen (screen.py `_v6_programs`), its band moves
  (bands.py), the under_bar and reach_bar_off skips, the at-size count and the unsettled hold, so EVL-R2-ON's row must
  read it True. Without it, (a) alone still gives 6 slots and PREREG-EVL-6's screen would not select the row
  (`fix2/slot_rules.out`: a plain prereg-10 row reads evl6 False and max_open 6; a row reading True gives 14). REFINED:
  the check counted 'cash' among the bindings read from the main row; the send's bindings (cash, invested, budget) are
  read by evl_health from the intents, whose `at` is "close", so they were counted already. The decision's own counts
  were not, and (d) carries them: picks, the room cut, the skips by reason ('given' among them), 'window' and
  sale_to_later. RE-RUN (`fix2/slot_rules.py` on release 1019l's real `book.reservation`, E = $1,906): history found and
  room 14, $571.80 (30% of E); history not found and room 14, $1,334.20 (70%), as `recheck2/a85_slot.out`; with room 6
  (evl6 False), 30% either way, only because the whole room is then 6. (a) and (b) without (d) would reserve 70%; only
  (a), (b) and (d) together give the stated rule (14 slots and 30% of E at a median of 6 picks).
- REJECTED in the second round: none.
