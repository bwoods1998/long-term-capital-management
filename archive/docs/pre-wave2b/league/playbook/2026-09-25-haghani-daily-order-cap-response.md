# Stop entry retries when the daily order allowance is exhausted

Applies to Haghani-56 and its crypto-alts-reversion research decisions.

## Evidence

On September 25, the Alpaca book reported ten refusals saying `desk reached 200 orders today`, across the 22:17, 22:32 and 22:47 wakes. They involved SOL, XRP, LTC, LINK and AVAX. The supplied excerpts do not identify buy versus sell.

The current program ignores `recent_order_outcomes`. Without an existing bid, it can propose another deep-dip entry every wake. An order-count refusal is not evidence that changing the bid price or retrying another symbol will help. The daily cap is working; do not raise it or move the same requests elsewhere.

## Required response at the next research pass

1. Inspect owned `recent_order_outcomes` and the corresponding order records. Confirm the daily-order-cap reason, distinguish buys from sells, and distinguish a House refusal from an exchange submission. Do not infer an order's side from its symbol.
2. On a confirmed current-day cap refusal, call `pause_entries` with a note recording the refusal time and the exhausted daily allowance. This holds all new buys and cancels working buys. It deliberately prevents further entry retries across the strategy's five symbols, not just the last refused one.
3. Leave sells, cancellations, settlement and the strategy's stop and holding-time logic enabled. Do not return an empty decision, cancel protective exits, or suspend the whole strategy to improve refusal counts. A capped sell needs separate investigation; pausing entries is not an exit repair.
4. Keep entries paused for the exhausted allowance. Do not resume merely because a price changes, an order disappears, or another 15-minute wake arrives. Do not repeatedly pause and resume to test the cap.
5. At the next daily allowance reset, verify from the book's records that a new allowance period has begun before calling `resume_entries`. Record that evidence in the resume note. An old refusal still present among recent outcomes is not a new refusal. If the reset cannot be established, keep the entry pause and report the missing information rather than guessing.

## Acceptance check

After the pause is applied, inspect at least two completed wakes: proposed buys must be held rather than submitted for another daily-cap refusal; exits and cancellations must remain enabled. After a verified reset and resume, ordinary entry handling must return without changing the cap.

Success means the repeated capped BUY requests stop. It does not mean the strategy has earned a larger allowance or demonstrated an edge. If refusals continue on sells, retain their timestamps and reasons for a separate repair instead of hiding them.
