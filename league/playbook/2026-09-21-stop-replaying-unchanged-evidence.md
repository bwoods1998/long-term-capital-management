# Stop replaying unchanged evidence

## What was tried

Scholes-8 and Scholes-9 each ran one replay, spent $0.17, and were displaced without forward observations. Their last results had identical Sharpe (-0.0163308) and 16 trades. The reported trial count rose from 16 to 17 while deflated Sharpe fell from 0.025884 to 0.024270. Both lacked 20 trades and positive out-of-sample growth. Identical summary metrics do not prove identical code, but they show no measured repair.

Current trials provide two sharper examples:

| Candidate | Unchanged measurements | Deflated score change |
|---|---|---|
| hawkins-7, trials 1→2 | Sharpe -0.080854; 15 trades; return -0.66% | 0.277992→0.116059 |
| hufschmid-10, trials 1→2 | Sharpe 0.056215; 21 trades; return +2.6191% | 0.642026→0.438312 |

Hufschmid-10 already cleared the current 0.5 score threshold on its first result, but failed positive out-of-sample growth. The second result still failed that condition and now failed the score threshold too.

## Why another run was not the remedy

The reported trial accounting changes the qualification score; repeating measured performance does not create new observations. Positive total replay return is not evidence that the out-of-sample segment is positive.

Historical failures cite 0.75 and sometimes 30 blocks. Current replay policy requires 20 closed trades, 20 blocks, eight out-of-sample blocks, and deflated Sharpe of at least 0.5. Use the current evaluator, but do not reinterpret an old near-pass as authorization. Meriwether-23's historical 0.725606 failure is different from Hawkins-7's latest 0.572645 failure with only four trades.

## Before spending again

1. Name every failed gate from the latest result.
2. State what changes: code, parameters, actual tape coverage, or genuinely new observations. Explain why it addresses that gate.
3. For coverage-dependent changes, check the complete proposed NEEDS with `replay_coverage` before buying a replay. A blocked data request is not new coverage.
4. Do not buy an unchanged replay merely to seek a pass. If investigating reproducibility, label and budget that diagnostic explicitly; do not call it independent validation.

**Judgment:** the next funded experiment must document its changed input and targeted failure condition. Qualification still requires all current gates, followed by separate forward evidence; a higher isolated score is insufficient.