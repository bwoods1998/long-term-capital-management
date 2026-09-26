# Owner-account performance

The website masthead and balance chart use the venue accounts, not the sum of
virtual desk ledgers. Desk attribution and learning rewards remain independent.

The audited opening mark is **976.11177639 USD at 2026-09-16T04:58:42.508Z**.
This is the first complete Kalshi-plus-Coinbase mark after the Kalshi cash/equity
fix. It is **not** an original deposit or a claim of lifetime profit. Earlier
performance is excluded and the website says so. Never move this boundary to hide
losses. The config preserves this observed mark even when history is sampled.

Tracked profit = current account equity − opening mark − subsequent net external
deposits. Withdrawals are negative deposits. Open-position P&L and fees already
reflected in venue balances are included. Sail costs are shown separately;
“tracked profit less all Sail spending” deliberately deducts all recorded compute
spend, including spend before the chart boundary.

`AccountPerformance` reads Kalshi deposit/withdrawal records and Coinbase v2
account transactions every five minutes on a background thread. It follows
pagination, ignores internal Advanced Trade fills, and publishes only aggregate
flows and the verification timestamp. It makes no money-moving requests. Unknown
transaction types, pending funding, failed/incomplete reads, stale funding checks,
or incomplete/stale venue balances make profit unavailable rather than guessing
zero flows. Funding APIs and balance APIs are eventually consistent; these are
marked account estimates, not guaranteed liquidation proceeds or audited returns.

The current accounting scope is exactly Kalshi and Coinbase. Adding another venue
requires a funding reader and a reconciled opening basis; it must not silently
join the denominator. Incomplete/stale balance reads are not archived as new
performance marks. The chart endpoint and headline use the same checkpoint;
newer tape marks wait for that checkpoint instead of racing the headline.

Only initial aggregate funding was present during the September 17 verification:
no subsequent external flows after the opening mark. Older personal account
transactions are not project returns and are never published.
