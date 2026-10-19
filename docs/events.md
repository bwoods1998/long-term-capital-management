# The event lane (EVL)

The lane the owner's goal of Oct 19, 2026 funds: long-only, whole-share trades in US-listed common stocks, entered and
exited in the listing exchange's opening and closing auctions, triggered by public events newer than any model's
training (SEC EDGAR 8-K and Form 4 filings, Alpaca news). The rules are pre-registered and frozen; this page says where
they are and how the code runs them. When this page and a pre-registration disagree, the pre-registration wins.

## The rules

- [PREREG-EVL-1](prereg/PREREG-EVL-1.md), registered 2026-10-19T01:08:38Z (tag `prereg-evl-1`): the universe, events
  and knowable times, the Claude Haiku 4.5 verdicts (temperature 0, stored once, replayed), the auction execution model
  and costs, the four first seatable programs, THE SCREEN (the judge for every program), real money, Done and Kill.
- [PREREG-EVL-2](prereg/PREREG-EVL-2.md), registered 2026-10-19T03:04:07Z (tag `prereg-evl-2`): the second wave, five
  seatable programs, three records and one control, judged by PREREG-EVL-1's screen unchanged.
- An event counts for a program only when it is knowable after that program's own registration time. A change to a
  registered program is a new version with a new registration time. Expected false passes over both files: 0.9
  (0.10 x 9 seatable versions).

## The programs

| program | file | seatable | event | entry | exit |
|---|---|---|---|---|---|
| EVL-ERN-READ-O1 | 1 | yes | earnings 8-K (item 2.02), verdict score >= 2 | next open | that close |
| EVL-ERN-REACT-C1 | 1 | yes | earnings 8-K, day-0 move >= +4% at 15:29 ET | day-0 close | next close |
| EVL-8K-READ-O1 | 1 | yes | 8-K items 1.01, 2.01, 7.01, 8.01 (no 2.02), score >= 2 | next open | that close |
| EVL-NEWS-READ-O1 | 1 | yes | pre-market single-stock news, score >= 2 | open | that close |
| EVL-ERN-REACT-ON | 2 | yes | C1's events and rule | day-0 close | next OPEN |
| EVL-ERN-GUIDE-O1 | 2 | yes | earnings 8-K, guidance "raised" and score >= 1 | next open | that close |
| EVL-INS-BUY-O1 | 2 | yes | Form 4: director/officer open-market buys >= $50k | next open | that close |
| EVL-NEWS-READ-ON | 2 | yes | single-stock news 09:00-15:29 ET, score >= 2 | that close | next OPEN |
| EVL-NEWS-REACT-ON | 2 | yes | the same news, move >= +4% at 15:29 ET | that close | next OPEN |

Records (never seated): EVL-ERN-READ-O3, EVL-INS-CLUSTER-O5 (file 1); EVL-INS-BUY-O5, EVL-ERN-REACT-READ-C1,
EVL-ERN-READ3-O1 (file 2). Controls (what the verdicts add): EVL-CTRL-ERN-ALL-O1, EVL-CTRL-8K-ALL-O1,
EVL-CTRL-NEWS-ALL-O1 (file 1), EVL-CTRL-NEWS-DAY-ON (file 2). File 2's programs are not filled when the entry auction is
above 1.25 x the previous close (real money's limit).

## The code

`league/events/` (standard library only): `store.py` (one SQLite file and a document store; the schema is pinned),
`edgar.py` and `news.py` (the recorders), `calendar.py` (sessions and decision moments), `universe.py` (eligibility),
`verdicts.py` (the recorded Haiku verdicts), `programs.py` (the programs as data rows and their selection rules),
`run.py` (the open and close decisions, backfill), `score.py` (settlement at the auction prints and the exit ladder),
`screen.py` (the judge), `report.py` (the daily one-screen report), `__main__.py` (the CLI: `record`, `backfill`,
`decide-open`, `decide-close`, `catchup`, `tickers`, `equity`, `score`, `screen`, `report`). Release R2's real-money
side: `book.py` (the equity book's event kind's rules: the money rows, the bands, the real-money picks, the limit, the
size target, the open-risk weight, the exit plan, the eligible list) and `proof.py` (the auction paper proof).

## Where it runs (shadow)

Until release R1 moves the lane onto the House, it runs on the captain's workstation as systemd user timers
(`ltcm-evl-record` every 2 minutes; `ltcm-evl-tickers` 07:00 ET; `ltcm-evl-decide` at 09:16 and 15:47 ET plus an
hourly catchup; `ltcm-evl-equity`; `ltcm-evl-score` 20:30 and 08:30 ET; `ltcm-evl-screen` 20:50 ET; `ltcm-evl-report`
21:05 ET), reading Alpaca and Claude through the LTCM gateway. Nothing in shadow sends an order. Real money waits for a
program's screen pass and release R2 (the gateway's event-buy branch, the equity book's event kind, the auction order
types, the paper proof).

## Real money (release R2; not yet deployed)

A program whose held look PASSED trades real money from the next session, through the House's EquityBook (its event
kind: league/equity/live.py `_event_step`, the rules in `book.py`), on the money rows `equity_money.event` of
league/constitution.py: Probe 5% of equity a position (Sized 10% after 150 settled real events and the 80% lower bound
above zero), at most 6 open (Sized 8), the book-wide 10% a name, whole shares, entries limit-on-open / limit-on-close at
1.25 x the previous SIP close, exits market-on-close (market-on-open for the three overnight rows) with PREREG-EVL-1
section 5's fallback ladder, open risk value x max(0.10, 1.65 x sigma60 x sqrt(h)) in the one loss budget ($400 net in
any 20 sessions, $800 net in total), demotion at -$150 over 20 sessions, at most 9 programs live. The real-money
decision reads the lane's store read-only, and only events stored and verdicts answered before its decision time
(PREREG-EVL-1 section 3). Every program ships at shadow; the event kind has its own switch (`equity_money.event.enabled`;
the old lanes' `equity_money.enabled` stays False); the auction paper proof on the practice account comes first; the
gateway's `STOCK_EVENT_BUYS` is the owner's step at the first Probe. How it runs, is read, is deployed and is rolled
back: [operations.md](operations.md), **The event lane's real money on the House (release R2)**. Each real fill is set
beside the shadow's own auction price, per side (league/ops/twins.py `event_twin`).
