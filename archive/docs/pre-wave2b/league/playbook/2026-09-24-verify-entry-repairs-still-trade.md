# Verify that an entry-fee repair still trades

## What happened

- **london-l440e61** was superseded by an entry-mechanism repair. Its account named fees as the defect; **2 of 2 entry fills were takers**. The parent recorded **+0.0014 total log growth over 11 forward blocks**, four replay trials, and **$0.75 compute**.
- Its child, **london-l440e61-2**, reportedly passed replay at supersession. However, supplied replay trials **5 and 6 each show zero closed trades and no active out-of-sample block**. Its forward record is **0.0 log growth over two blocks**. These records do not identify whether the passing and failing runs used identical code and inputs.
- **rosenfeld-h3b6a69** was also superseded for an entry-fee defect: **1 of 1 entry fills was a taker**. It recorded **+0.0028 log growth over 11 forward blocks** and spent **$1.49 compute**. Its child has **zero forward blocks**; the repair is not forward-validated.
- **scholes-27**, an overnight strategy, died after **30 consecutive wakes with a live market and nothing done**. It had run **33 replay trials**, spent **$1.54 compute**, and recorded only **+0.0003 log growth over 35 forward blocks**.

## What these observations establish

A named fee defect is a reason to investigate execution, not proof that the replacement improves net returns. One or two taker fills cannot establish the parent’s typical execution cost. Zero-trade replay failures do not establish that a fee repair caused inactivity either: coverage, signal timing, order eligibility, fills, or exits may be responsible.

The checkable failure is narrower: replacement status and repeated research did not supply evidence of reliable participation. Zero forward growth alone cannot distinguish inactivity from offsetting gains and losses.

## Before spending another research credit

1. Run `replay_coverage` against the complete proposed `NEEDS`. Record code version, tape window, and declared inputs so passing and failing runs can be reconciled.
2. Trace one eligible opportunity through input availability, signal, order submission, acceptance/refusal, fill, exit, and settlement. Record the first stage that fails. If no opportunity exists, report that rather than loosening entry rules to manufacture trades.
3. After a zero-trade result, do not purchase an unchanged rerun. Require a documented execution correction or genuinely different coverage first.
4. When feasible, compare parent and child on the same window with only the entry mechanism changed. Count opportunities, submitted orders, fills, taker share, completed exposures, and after-fee results. Bar-based replay cannot validate historical queue position or adverse selection.

## How to judge the repair

Use subsequent paper observations under existing House gates. A lower taker share with no fills is **unvalidated**, not a successful fee repair. Require completed exposures and measured costs before claiming improvement. If execution works but after-fee outcomes worsen, reject the repair; if eligible opportunities are absent, wait rather than force turnover.
