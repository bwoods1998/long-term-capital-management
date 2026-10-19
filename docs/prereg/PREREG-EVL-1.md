# PREREG-EVL-1: the event lane's first programs and judges

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6f078599) under the owner's goal of Oct 19, 2026
(`goal-2026-10-19/GOAL-MESSAGE.txt`). Written 00:05-02:00Z Mon Oct 19, 2026, before any event of Mon Oct 19 was read
and before any outcome (a price after an event) of any event was looked at by the captain or any agent. Draft 1 was
reviewed adversarially (blockers B1-B4, majors M1-M9, minors) and draft 2 re-reviewed; every finding is answered here.

REGISTRATION TIME: the later of this file's commit time and GitHub's receipt of the push of the tag `prereg-evl-1`
(read from the GitHub API and recorded in amendment A61); the tag never moves. An event counts for a program only if
its knowable time (section 3) is after the registration time. Nothing here changes for a registered program: a
change is a NEW program version with its own registration time, and the old version's record is kept. Every count of
expected false passes uses 0.10 x every seatable version ever registered.

## 1. What this lane is

Long-only, whole-share trades in US-listed common stocks, entered and exited in the listing exchange's opening and
closing auctions, triggered by public events newer than any model's training: SEC EDGAR filings (8-K, Form 4) and
Alpaca (Benzinga) news. Every program is shadow-traded on every qualifying event from its registration; real money
follows only a pass of the screen in section 7. No margin, no shorts, no options.

## 2. The universe (as of the entry session D, from data before it)

A stock is eligible for entry session D if all hold, read from data available before D's open:
- its ticker maps to the event's issuer CIK in SEC's `company_tickers.json` (the latest copy fetched before 07:30 ET
  of D); when a CIK maps to several tickers, the one with the highest ADV below; for an 8-K with several filers, the
  first filer that has a ticker;
- Alpaca lists it as `class: us_equity` on exchange NYSE, NASDAQ, AMEX, ARCA or BATS (never OTC): live decisions read
  `status=active` and `tradable: true`; backfilled decisions read Alpaca's asset records with `status=all`, and for a
  backfilled D the listing exchange is the one whose condition-`6` closing print the stock had on the session before
  D (a stock with none is not eligible), so a name delisted or moved since cannot drop out;
- its last completed session's SIP close (Alpaca 1Day bar, raw) is >= $3.00;
- its ADV, the mean of SIP close x volume over the 20 completed sessions before D, is >= $1,000,000, with a SIP daily
  bar on each of them;
- it is an operating company's stock: its CIK filed a Form 10-K, 10-Q, 20-F or 40-F in the 15 months before D, and its
  EDGAR SIC code is neither 6221 (commodity and crypto trusts) nor 6770 (blank-check companies), both read from
  EDGAR's company browse feed (cached per CIK for 30 days).

ADV also chooses each event's BENCHMARK: IWM when ADV < $50,000,000, else SPY.

## 3. Events and their knowable time

- E8K: an EDGAR filing of form type exactly `8-K` (amendments `8-K/A` excluded): accession, CIK, items, EDGAR's
  acceptance time (Eastern), the documents. TEXT = the lowest-numbered `EX-99.*` exhibit (`.htm`, `.html` or `.txt`) if
  any, else the primary 8-K document, converted HTML to plain text with the House's `ltcm.data.strip_html` and
  whitespace collapsed, then the FIRST 16,000 characters. A TEXT shorter than 200 characters gets no verdict.
- EF4: an EDGAR filing of form type exactly `4`, parsed from its XML: issuer CIK, reporting owners and relationships,
  and each non-derivative transaction (date, code, shares, price, acquired/disposed).
- ENEWS: an Alpaca news article: id, created_at, updated_at, headline, summary, symbols, source. LIVE = first stored by
  the lane's recorder within 10 minutes of `created_at` (the news recorder runs around the clock); a non-live
  (backfilled) article is excluded when its `updated_at` is more than 10 minutes after `created_at`.

KNOWABLE TIME: EDGAR events, acceptance + 10 minutes; news, `created_at` + 2 minutes. A decision may use only events
knowable before it. The SHADOW record decides every event by its knowable time and its stored verdict, whenever the
recorder stored the event and whenever the verdict arrived (an outage removes nothing; the late share is reported).
A REAL-MONEY decision may in addition use only events stored, and verdicts answered, before its decision time.

BACKFILL: EDGAR filings and acceptance times are immutable public records and Alpaca keeps its news, so events after
the registration time that occur before the recorders run are read afterwards and count, decided as the shadow rule
above decides every event. The captain does not choose which events count: all do.

## 4. Verdicts (recorded feeds)

Model `claude-haiku-4-5-20251001` (Anthropic, through the LTCM gateway), temperature 0, max_tokens 300, no thinking,
no tools. No verdict is asked until the gateway admits temperature 0; READ events wait for it and are decided by the
shadow rule; a verdict asked any other way is never used. Each verdict is stored once with the event id, the prompt's
SHA-256, the model, the request id, the answer and the time; the first stored answer that is `ok`, `unparsed` or
`refused` (the model's own `stop_reason` refusal) is final, and replay reads it and never asks again. A call with no answer (a transport failure, a 5xx or 429,
or an HTTP refusal by the gateway itself, such as today's 400 on temperature) stores nothing and is asked again
later, at most 3 times a pass. PARSING: surrounding whitespace and one Markdown code fence (```` ```json ... ``` ````) are
removed, then the text must be one JSON object whose `score` is an integer in -3..3, else `unparsed` (trades nothing).
FORMATS: `{items}` = the 8-K's item numbers in ascending order joined by ", " (e.g. "2.02, 9.01"); `{acceptance_et}` and
`{created_et}` = Eastern time as "YYYY-MM-DD HH:MM"; `{name}` = the SEC title of the CIK; `{ticker}` and `{symbol}` = the
eligible ticker.

PROMPT-DOC (for E8K), system: "You are an equity analyst reading a company's SEC filing the moment it is published.
You see no market prices. Judge only from the text." User:

    Company: {name} (ticker {ticker}). SEC Form 8-K, items {items}, accepted {acceptance_et} ET.
    Document (its first 16,000 characters):
    <document>
    {text}
    </document>
    Relative to what investors most likely expected before this filing, is this news likely to make the stock
    outperform or underperform the overall stock market over the next trading day? Answer with JSON only:
    {"score": an integer from -3 (strongly underperform) to 3 (strongly outperform), 0 if neutral or unclear,
     "guidance": one of "raised", "maintained", "lowered", "none", "unclear",
     "reasons": up to three short strings}

PROMPT-NEWS (for ENEWS), same system text with "a news headline" in place of "a company's SEC filing". User:

    Stock: {symbol}. Published {created_et} ET by {source}.
    Headline: {headline}
    Summary: {summary}
    Relative to what investors most likely expected before this news, is it likely to make the stock outperform or
    underperform the overall stock market over the next trading day? Answer with JSON only:
    {"score": an integer from -3 (strongly underperform) to 3 (strongly outperform), 0 if neutral or unclear,
     "reasons": up to three short strings}

CONTAMINATION: every screened event post-dates the verdict model's training data, so the forward record cannot be
contaminated by memory of the outcome; no historical test seats a program. Any historical test of a reading program
that is ever run is reported with its contamination measured (masked vs unmasked verdicts) and is never a screen.

## 5. Execution model (shadow and real money identical)

- OPEN entry on session D: decided at 09:15 ET from events knowable by 09:00 ET; the order sent by 09:27 ET.
- CLOSE entry or exit on session D: decided at the session's close - 14 minutes (15:46 ET on a full day); the order
  sent by close - 11 minutes. Early-close sessions move every close time with the session.
- AUCTION PRICES (the shadow's, and the price real fills are compared with): the OPEN price of D is the listing
  exchange's opening cross print on the SIP tape (the first regular-session trade on D from the stock's listing
  exchange carrying trade condition `O`); the CLOSE price is its closing cross print (the trade from the listing
  exchange carrying condition `6`); if the listing exchange printed no `O` (`6`) on D, its `Q` (`M`) official open
  (close) record. Listing exchange codes: NYSE `N`, NASDAQ `Q`, AMEX `A`, ARCA `P`, BATS `Z` (each verified on the Oct 16,
  2026 tape: the listing exchange prints `O` with `Q` at the open and `6` with `M` at the close; other venues print their
  own, so only the listing exchange's print counts). Read
  from SIP historical trades once 15 minutes old. The SIP daily bar's open and close are recorded beside them and the
  gap reported. Splits and dividends inside a hold apply through the ratio of Alpaca's adjusted to raw daily close.
- NO AUCTION PRINT at entry: the event is skipped. NO EVENT IS VOIDED AFTER ENTRY: with no exit auction print on the
  exit day the position exits at the next session's closing cross, and with none within 5 sessions at the first SIP
  trade of the next session on any venue, and at 0 after 20 sessions.
- Session count: the entry session is session 1. "Exit at CLOSE of session h" means h sessions held.
- One position per issuer per program: an event whose issuer the program holds, or held within the last 5 sessions,
  is skipped (shadow and real alike).
- COSTS (screen): per side 0.5 bp plus an impact allowance of 5 bp (ADV >= $10M) or 10 bp (ADV $1M-$10M), plus fees at
  the Probe position notional N (5% of the account equity at the previous close): $0.01 per side (CAT) and $0.01 on
  the sale (TAF), each over N. The NBBO at order time is recorded beside every decision (IEX live; SIP historical once
  15 minutes old) and a stress return net of half the quoted spread is reported beside the screen, never instead of
  it. Once real fills exist the allowance is checked weekly: if the signed mean gap, per side, between real fills and
  the shadow auction prices is worse than the allowance, the allowance is raised to it for every program (never
  lowered); real fees are booked as the broker posts them.
- PER-EVENT RETURNS (per dollar): r = exit_px x (1 - c_exit) / (entry_px x (1 + c_entry)) - 1. ABNORMAL a = r - b,
  b = the benchmark's return between its own auction prints at the same two auctions.
- TRADABLE: an event whose stock's 1.25 x previous SIP close is <= 10% of the account equity at the previous close
  (one share fits under the real-money limit price; section 8). TRADABLE is the population the screen tests.

## 6. The programs

Seatable (may earn real money after a screen pass); every one holds 1 session:

| id | event | rule | entry | exit |
|---|---|---|---|---|
| EVL-ERN-READ-O1 | E8K with item 2.02 | PROMPT-DOC score >= 2 | OPEN of the first session whose 09:00 ET is after the knowable time | CLOSE of session 1 |
| EVL-ERN-REACT-C1 | E8K with item 2.02 | no model: the close of the regular-session SIP 1-minute bar starting 15:29:00 ET on day 0 (on an early close, the bar starting 31 minutes before the close; if that minute has no trade, the last earlier regular-session minute bar of day 0) is >= 1.04 x the raw SIP daily close of the last session that closed before the acceptance time; day 0 = the first session whose close decision time is after the knowable time | CLOSE of day 0 | CLOSE of the next session |
| EVL-8K-READ-O1 | E8K with any of items 1.01, 2.01, 7.01, 8.01 and without 2.02 | PROMPT-DOC score >= 2 | OPEN as for O1 | CLOSE of session 1 |
| EVL-NEWS-READ-O1 | ENEWS with exactly one symbol, knowable after the previous session's close and by 09:00 ET of D, that symbol the eligible one | PROMPT-NEWS score >= 2; one event per issuer per D (the highest score, then the earliest) | OPEN of D | CLOSE of D |

Records (shadow only, never seated; reported beside):
- EVL-ERN-READ-O3: the O1 events and rule, exit at the CLOSE of session 3 (overlapping holds: its screen would not
  hold the false-positive cap, so it is a record).
- EVL-INS-CLUSTER-O5: Form 4 open-market purchases (code P, acquired A) whose transaction dates fall inside the
  window, by at least two distinct reporting owners who are directors or officers of the same issuer, in at least two
  different filings, all filed within the 10 calendar days ending at this filing's acceptance, total value (shares x
  price) >= $50,000; triggered by the filing that first meets it, and not again for that issuer until 10 calendar days
  after the trigger; entry at the OPEN of the first session whose 09:00 ET is after the knowable time; exit at the
  CLOSE of session 5 (too few events for power: a record).
- Controls (they measure what the verdicts add): EVL-CTRL-ERN-ALL-O1 (every O1 event, any score), EVL-CTRL-8K-ALL-O1
  (every 8K-READ event, any score), EVL-CTRL-NEWS-ALL-O1 (every NEWS-READ event before its score rule, one per issuer
  per D by the same order).

EVL-NEWS-READ-O1 needs the gateway to read Alpaca's news path; its events after the registration time are backfilled
once it can.

## 7. The screen (judge; recursion never touches it; implemented in league/events/screen.py)

- SESSIONS AND BLOCKS: a program's sessions are numbered from its first entry session (= 1); each session is one block
  (every seatable program holds one session); a block counts once all its events have settled; an empty session has
  no block. A block's value is the mean abnormal return a of its TRADABLE events.
- LOOKS: look k (k = 1..7) is computed as of the close of the program's session S_k, S = 10, 15, 20, 30, 40, 60, 90,
  counting the session of its first settled exit as session 1. It covers every block whose scheduled exits are at or
  before the look's close, and is computed once all of them have settled (fallback exits included); late data delays
  the computation, never its as-of date. A look is HELD only
  if, then, the program has >= 60 settled TRADABLE events, >= 40 distinct issuers among them, and >= 10 blocks; a look
  that fails a minimum is skipped, never deferred. No other look exists.
- SIGN-FLIP p: one-sided, (1 + #{v : mean(s_v x values) >= mean(values)}) / (1 + 99,999) over 99,999 sign vectors s_v
  drawn by Python's `random.Random(seed).getrandbits(n)` (bit j set = +1 for value j, in order), seed =
  int.from_bytes(sha256(f"{id}|v{version}|look{k}").digest()[:8], "big"); ties count against the program (a vector counts when its mean >= mean(values) - 1e-12).
- SKEW CHECK (tightens only; automatic, at every held look, before p is computed): centre the look's block values to
  mean zero, draw 1,000 bootstrap samples of the same count with replacement (`random.Random` seeded as above with
  "|skew" appended to the seed string, each index drawn by `r.randrange(n)`), and let f = the share of samples with mean > 0 and a sign-flip p <= alpha,
  each p over the same 1,999 sign vectors (seed string with "|skewflip" appended); starting from alpha = 0.024, while
  f > 0.024 lower alpha by 0.002 (floor 0.002). The session-block and issuer-block tests each get their own check. f
  and alpha are recorded before p.
- PASS when, at a held look: p <= alpha (session blocks) AND the same test with ISSUER blocks (each issuer's TRADABLE
  events averaged into one value, values in ascending CIK order, seed string with "|issuer" appended, its own skew
  check) has p <= its alpha AND the mean abnormal return of the TRADABLE events > 0 AND their mean
  raw after-cost return r > 0 AND, for a READ program, its mean block value exceeds its control's over the same
  sessions (the control's TRADABLE events in those blocks).
- MEASURED FALSE-POSITIVE RATE (the reviewer's simulations of this rule, synthetic, per-session common shock 0.4%,
  3% per event, t(4)): the session-block test with the skew check passes a zero-edge program 8.3% of the time
  (symmetric returns, 6 or 40 events a session; 5.6% at 2), 9.4% (+/-0.6) with left-skewed returns, and 10.3% (+/-0.9)
  with a -20% crash tail at 1% a day: at, not under, the 10% cap in that last case, and under the goal's 15% in all.
  The issuer-block and beat-the-control conditions can only lower it. Expected false passes over the four seatable
  programs: about 0.4.
- POWER (same model, 1-session holds): at 40 events a session an edge of 0.2% a event passes about 59% of the time
  (median session 40), 0.4% about 93% (median 20), 0.8% >99% (session 10); at 2 events a session, 0.4% about 24% and
  0.8% about 55%. The skew check costs 1-2 points; the issuer-block test, the beat-the-control rule and the smaller
  TRADABLE count are not measured.
- Beside every look: the all-event figures, the raw-r test, the half-spread stress, the market-direction share (the
  benchmark's mean return over the events), the control's figures, the late-verdict share, and the counts.

## 8. Real money: promotion, size, demotion

- PROBE: the first session after a pass. Target per position = 5% of account equity. Real entries are limit-on-open /
  limit-on-close orders (`opg` / `cls`) at 1.25 x the previous SIP close, whole shares = floor(min(target, 10% of
  equity - the name's book-wide value) / limit); one share when that rounds to zero and one share fits under both
  the book-wide 10% wall and the 100% book; skipped otherwise (the shadow notes it and keeps the event). The 10% per-name wall is book-wide (all programs
  and lanes together). At most 6 open positions per program; the book <= 100% of equity invested. When more events
  qualify than room, the program takes them in order of verdict score (C1: its reaction), higher first, then ADV;
  when two programs want the same name at one auction, the earlier row of the table in section 6 goes first.
- SIZED: after >= 150 settled real-money events with the 80% session-block bootstrap lower bound of the per-event
  after-cost return above zero: target 10% of equity per position (still under the book-wide 10% wall), at most 8 open.
- DEMOTION: a program whose last 100 settled real-money events have a negative mean after-cost return is retired to
  shadow for good (a new version must be registered to return). A program whose realized real-money net over its
  last 20 sessions is below -$150 goes back to shadow for 20 sessions, then returns to Probe only if its last held
  look passed.
- OPEN RISK for the loss budget ($400 net per 20 sessions, $800 net total, the House's ledger as it stands, which
  counts the total from its inception): each open position counts value x max(0.10, 1.65 x sigma x sqrt(h)), sigma =
  the stock's daily return standard deviation over the 60 sessions before entry, h = sessions left in its hold. Until
  the House's 0.40 floor on stock open risk is lowered by the release that carries this rule, the stricter 0.40
  applies. No new entry may take the budget past its line.
- THE OLD LANES: the index ETF and options programs take no new entries from the first House release after the
  registration time (it switches equity opens off; options reads are already off); their open lots exit by their own
  rules.

## 9. Done, Kill and reporting (from the goal, restated so the reader is pinned)

- Count: settled real-money EVL events from the first real fill. Read at every 100th.
- DONE: >= 300 settled real-money events from >= 3 programs with >= 50 each; realized after-fee P&L positive; the
  95% lower bound of the per-event after-cost return above zero under BOTH an issuer-block and a session-block
  bootstrap (10,000 resamples, seed fixed); trailing 4 weeks' realized profit >= metered compute; real fills within
  15 bp of the shadow auction prices (the signed mean, per side); 14 days with no captain.
- KILL: at 400 events, if the 95% upper bound of the per-event after-cost return under the issuer-block bootstrap is
  below zero, the lane is retired and all research spend stops. At 800 events: Done, a written scaling case, or stop.
- SAME-RISK BUY-AND-HOLD (beside every report): the event's benchmark ETF bought and held continuously over the
  reported period at the program's average invested dollars.
- Every report: account-shown profit first, Net after metered costs beside, the market-direction share, the same-risk
  buy-and-hold, and the expected false passes.

## 10. What is NOT decided here

The recorders' code, the House integration, the gateway changes (Haiku price row, the news path, temperature 0,
any-symbol whole-share opg/cls limit buys capped at 10% per name), the site and docs: built after this file, to these
rules. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS (for screen rules)
or that trades less (for trading rules), fixed before the program's first settled event and recorded as an
amendment; a later resolution is a new version.
