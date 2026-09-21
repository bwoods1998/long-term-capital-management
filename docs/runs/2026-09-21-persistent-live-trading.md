# Persistent earned live trading — September 21, 2026

The owner requested that agents be able to climb the entire ladder and trade automatically
without a live-pilot deadline. The current Kalshi and Alpaca balances are available as risk
capital, including the possibility of losing the full allocation. This supersedes the timed
$200 pilot in the [gate audit](2026-09-21-game-gate-audit.md); it does not relax performance tests.

## Account-owner command

After this implementation is merged and accepted by the production watchdog, run:

```sh
cd ~/Work/long-term-capital-management
git pull --ff-only
python scripts/live_trading.py --enable earned-live-20260921
```

This reads the live venue cash, records a persistent authorization, resumes the **unused**
OpenAI/Sail allowance, and restarts the supervised House to load the accelerated game. The
supervisor normally restarts it in about 30 seconds. Deployment and report commands do not
activate trading. The assistant does not execute the account activation.

The command prints `live_trading.active: true`, `ends: null`, and both
`micro_entries_allowed` and `scaled_entries_allowed` as `true`. This is financial eligibility;
an actual order still needs a qualified agent, fresh production audit, reconciled venue, an
entry signal, and cash. No agent is promoted merely because the command ran.

Read status or revoke new entries with:

```sh
python scripts/live_trading.py
python scripts/live_trading.py --disable
```

Revocation preserves position exits and all loss accounting. Repeating `--enable` cannot
undo revocation, enlarge the allocation, reset spending, or refill losses. Restarting the
House also does none of these. A material constitution change invalidates the grant.

## Capital and performance

Read-only account checks during preparation showed **$500 Alpaca** and **$517.7551 Kalshi**
cash/equity, with no live open orders on either book. Activation reads fresh balances and
rounds cash allocation down to cents, so that snapshot would allocate **$1,017.75**. It uses
cash, not margin buying power, and makes no deposit, withdrawal or inter-venue transfer.
Additional deposits do not silently expand the authorized allocation.

The ladder remains replay → paper → audited $25 live stake → performance-earned scaling.
The old pilot's $50 per-agent ceiling and eight-seat ceiling do not apply. The maximum seat
count follows the allocated cash divided by the $25 starting stake (40 at the snapshot above),
within the game's population limit. Scaling follows the existing quarter-Kelly calculation
on a positive lower confidence bound and the 25% venue-share limit. Available capital is
bounded separately at each venue and in aggregate, including historical losses, outstanding
exposure and scaled accounts. Profit at one venue cannot refill the other's allocation.

Completed-exposure qualification has no elapsed-time minimum. All existing fee, evidence,
variance, loss-risk, reconciliation, order and no-leverage checks remain. Strong performance
retains its research-credit and frontier-access rewards through promotion. Negative evidence,
drawdown or drift can demote or kill a former winner. Replacement still requires completed
research/trading opportunity and a valid entrant. This establishes an executable merit-based
game; it cannot guarantee that a real strategy has an edge or that returns will be exponential.

## Compute and clocks

The persistent owner grant removes the original burst/foundation deadlines from **effective**
OpenAI/Sail admission. Original phase and burst records, caps, meter anchors, costs and pending
holds remain unchanged. This is reuse of unspent allowance, not another $325 purchase and not
a daily/monthly reset. At 13:29 UTC, the original burst had committed $115.396206 of $250 OpenAI
and $7.314138 of $75 Sail, leaving about **$134.60 OpenAI / $67.69 Sail** before subsequent
hosting charges and reconciliation. These are budget allowances, not provider billing balances.

The accelerated game keeps 15-minute research eligibility, 12 research workers, four replay
workers, hourly payouts, the cubic performance reward and 15% niche floor. The original
Luna/Sail cohort identity remains fixed. Persistent-mode credit pools use remaining allowance,
so old expenditure does not produce a fresh pool of backed credits.

Finite compute budgets and provider balances still matter: exhausted or unhealthy meters
block new paid work, and execution needs funded Sail hosting. Gateway order and OpenAI caps
remain in force. The existing Jev experiment has its own expired gateway deadline; this
command does not reopen it or erase its holds. Jev classifications are optional features,
not promotion or order authority.

At 13:29 UTC, Haghani still passed the paper screen and was held by campaign authorization.
Hilibrand-2 no longer passed: its forward mean had turned negative. Past qualification does
not entitle a deteriorating agent to live capital. This observation supports retaining the
performance checks while removing the account-activation obstacle.

## Verification

`league/tests/test_live_trading.py` exercises persistent activation beyond both original
deadlines; no implicit activation; concurrent/idempotent activation; retained unknown-cost
holds and spent budgets; no capital refill; revocation; frozen research cohort; cash-only
allocation; venue-specific capital headroom; and report-only wrapper behavior.

The fake-venue integration runs a paper agent through audit, live fills and earned scaling
above $50, then removes its edge and requires demotion/death while checking reconciliation
and the ledger chain. No test submits orders to real accounts. Existing ladder, incentive,
replacement and adversarial evidence tests remain required. Full CI and production acceptance
receipts are recorded on the implementation pull request; live activation remains an owner action.
