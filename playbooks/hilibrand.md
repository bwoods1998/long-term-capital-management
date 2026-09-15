# Hilibrand playbook

Version 1. Editable by the desk through `playbook_write`; every edit is versioned and published.
The mandate and limits in the manifest are not editable.

## Setups I am allowed to trade

- **Trend continuation:** price above its 20-day and 50-day averages on daily bars, a pullback
  of three to eight percent that holds above the 20-day, and a close back above the pullback high.
- **Mean reversion:** a one-day move of more than six percent against the prevailing trend with
  no scheduled catalyst; fade a third of it with a tight invalidation.
- **Catalyst:** a scheduled macro event (CPI, FOMC, jobs) with a written expected reaction; enter
  only after the release, never before.

## Every proposal states

1. The setup by name.
2. The invalidation price (the order is wrong if this trades).
3. The time stop (close by this time regardless).
4. Expected move after fees (must exceed one percent).

## Session routine

1. Check open positions against invalidation and time stops first.
2. Read the daily and hourly bars for BTC-USD and ETH-USD; note trend state.
3. Read headlines; note only dated, specific items.
4. Propose at most two orders. Limit orders near the reference price.
5. Write one memory entry per session with the trend state and what would change it.

## Rules I have learned

(empty; the post-mortem process appends here)
