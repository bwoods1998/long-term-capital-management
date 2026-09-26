# The feeds added on Sept 26, 2026, in full

Moved out of `league/CONTRACT.md` (which the engineer and every Merton pass read whole as their system prompt, so its size
is paid on every call): the full description of each recorder the Kalshi-scale run added (`league/open_feeds.py`). The same
texts reach every agent through `runtime_status` (`observations.feeds`: each feed's host, what it records, since when, and how
it is stamped). `CONTRACT.md` keeps the declaration and a line per feed.

The key-free hosts the Kalshi-scale run added (`league/open_feeds.py`): each passed the rule that a
host is key-free, public, permits automated access in its terms and answers without a bot wall.
Declared and read exactly like the feeds above (known keys only, at most six a feed; an absent key is
unavailable, never zero); **live** rows carry the House's receive time and are never backfilled,
**history** rows carry the moment the source says the value became known and are backfilled, so a
strategy that declares only history feeds is replayed at once. Weather keys are settlement stations
as above (`KXHIGHNY` means `KNYC`).

```python
NEEDS["feeds"] = {"cli": ["KXHIGHNY"], "metar": ["KNYC"], "ghcnd": ["KNYC"],        # what the stations recorded
                  "kalshi_candles": ["KXMLBGAME"],                                   # what traded on Kalshi, by the hour
                  "bls": ["CPI"], "fiscal": ["auctions"], "fx": ["USD"], "cot": ["BTC"], "fomc": ["fomc"],
                  "pageviews": ["bitcoin"], "gdelt": ["trump"], "fear_greed": ["crypto"], "mempool": ["BTC"],
                  "storms": ["atlantic"], "quakes": ["m4.5_day"],
                  "cli_text": ["KNYC"], "presidential": ["actions"], "federal_register": ["executive_orders"],
                  "fuel": ["GASOLINE"], "bls_releases": ["cpi"], "bea_releases": ["gdp"], "halts": ["AAPL"]}
```

- **cli** (history; the Iowa Environmental Mesonet's parse of the NWS Daily Climate Report -- the
  numbers every Kalshi daily high, low and rain market settles on): each report as issued, `t` the
  NWS product's own issue time: `date` (the climate day, local standard time), `final` (False for the
  afternoon's preliminary report -- the high SO FAR -- True once issued after the day ended), `high`,
  `low` (F), `precip_in`, `snow_in` (0.0001 is a trace), `high_time`, `low_time`, `high_normal`,
  `low_normal`, `precip_month_in`, `product`, `issued`. The backfill holds each day's newest report
  (the final, or a correction); a preliminary report exists only where the House read it live.
- **metar** (history; the Aviation Weather Center): every METAR/SPECI of the station, `t` when the
  AWC received it: `observed`, `temp_f`, `dewpoint_f`, `max_6h_f`, `min_6h_f`, `max_24h_f`,
  `min_24h_f`, wind, `precip_1h_in`, `precip_6h_in`, `precip_24h_in`, `raw`. Backfilled 29 days (the
  service holds 30). The day's high so far is the max of `temp_f` and `max_6h_f` since local standard
  midnight.
- **ghcnd** (live; NCEI's GHCN-Daily): the last 14 days of quality-checked `high`, `low`,
  `precip_in`, `snow_in` per station, about three days behind and revised by NCEI; `cli` has the same
  day's numbers earlier and stamped.
- **kalshi_candles** (history; Kalshi's own hourly candles): per series the non-crypto desks trade,
  a row an hour, `t` the hour's END: `volume` (contracts traded in the markets read), `markets_traded`,
  `markets_read`, `markets_listed`, and `markets[ticker]` = `{volume, open_interest, open, high, low,
  close}` (traded YES price in dollars, None in an hour without a trade) and `bid`, `ask` (the YES bid
  and ask at the hour's close). `markets_listed` counts the series' markets open during that hour
  (by their listing times) and `markets_read` those of them read: the busiest by volume up to when the
  hour was fetched (at most 300). The running hour is never shown. Backfilled 14 days: what traded at
  which prices, for capacity.
- **bls** (live; BLS's public data API): `CPI` (seasonally adjusted), `CPI_CORE`, `CPI_NSA` (the
  index the year-over-year markets settle on), `UNRATE`, `PAYROLLS`, `AHE`, `PPI` (`KXCPI`, `KXU3`,
  `KXPAYROLLS` name theirs): `latest` `{period, value, preliminary}`, `change_1m_pct`,
  `change_12m_pct`, `diff_1m`, `recent` (13 months). A new release is a new row from when the House
  first read it (every 90 minutes).
- **fiscal** (live; FiscalData): `tga` (the Treasury General Account), `debt` (Debt to the Penny),
  `auctions` (`upcoming` and `recent` with `high_yield`, `bid_to_cover` and the bidder shares).
- **fx** (history; the ECB's euro reference rates): `USD`, `JPY`, `GBP`, `CHF`, `CAD`, `AUD`,
  `CNY`, `MXN` (any of the ECB's 29; `KXEURUSD` names `USD`), a row per business day, `t` 17:00
  Frankfurt time on the date (published about 16:00 CET): `per_eur`, `per_usd` (the cross through the
  day's USD rate), `change_1d_pct`, `change_5d_pct`, `usd_change_1d_pct`. For information: Kalshi's FX
  series settle on their own sources.
- **cot** (history; the CFTC's legacy futures-only Commitments of Traders): `BTC`, `ES`, `TY`,
  `GOLD`, `WTI`, `EUR`, a row per weekly report, `t` its as-of Tuesday + 7 days (it is released the
  Friday after, later in holiday weeks): `open_interest`, `noncommercial` `{long, short, spread, net,
  ...}`, `commercial`, `nonreportable`, `traders`, `net_change_1w`.
- **fomc** (live; the Federal Reserve Board's calendar): `fomc`, `speeches`, `testimony`, `beige`:
  `next`, `next_meeting` (the decision day), `events` (the 12 soonest, times Eastern).
- **pageviews** (history; Wikimedia): daily English Wikipedia views of `bitcoin`, `ethereum`,
  `solana`, `xrp`, `dogecoin`, `stablecoin`, `tether`, `anthropic`, `claude`, `openai`, `chatgpt`,
  `deepseek`, `gemini`, `grok`, `openrouter`, `trump`, `truth_social`, `fed`, `inflation`,
  `recession` (a Kalshi series names its subject: `KXANTHSHARE` is `anthropic`), `t` two days after
  the day began (the day's end plus a day's allowance): `views`, `avg_7d`, `ratio_7d`.
- **gdelt** (live; the GDELT Project, gdeltproject.org): per subject (`bitcoin`, `ethereum`,
  `anthropic`, `openai`, `trump`, `fed`, `inflation`, `recession`) the last day's news coverage:
  `articles_24h`, `all_articles_24h`, `share_24h` and 15-minute `points`; every three hours a subject.
  (Every host here backs off when it cannot be reached, times out or answers 429/5xx: a failed poll,
  no request, for five minutes doubling up to its cadence -- a key can then be absent for hours.)
- **fear_greed** (history; alternative.me): key `crypto`, the daily Crypto Fear & Greed Index, `t`
  its own timestamp plus two hours: `value` (0-100), `classification`, `change_1d`, `avg_7d`.
- **mempool** (live; mempool.space): key `BTC`: `fees` (sat/vB), `mempool`, `difficulty` (the
  coming adjustment), `hashrate`.
- **storms** (live; the National Hurricane Center): `atlantic`, `east_pacific`, `central_pacific`,
  `all`: `count` and the active `storms` (classification, intensity, pressure, position, movement,
  advisory); `count` 0 is a quiet basin, not an unavailable one.
- **quakes** (live; USGS): `m4.5_day`, `significant_week`: `count` and the `events` (magnitude, place,
  origin, status, tsunami flag).
- **cli_text** (history as issued; the NWS's own raw climate report, `tgftp.nws.noaa.gov`): per
  station (19 of the 20; New Orleans' file does not answer), `t` the product's issue time: `date`,
  `final`, `preliminary`, `as_of`, `high`, `high_time`, `low`, `low_time`, `precip_in`, `snow_in`.
  Faster than `cli`, but the NWS keeps only the newest report: nothing before recording began.
- **presidential** (history; the White House's presidential actions -- what KXTRUMPACT settles on):
  `actions` (every kind), `executive_orders`, `proclamations`, `memoranda`, `nominations`, a row per
  posting second, `t` the post's own publication time: `actions` (`title`, `link`, `kind`) and
  `today_et` (how many of the key that New York day, these included). Backfilled.
- **federal_register** (history; the Federal Register's API): `documents`, `executive_orders`,
  `proclamations`, `memoranda`, a row per day's issue, `t` 09:00 New York time on its publication
  date: `documents` (`document_number`, `title`, `signing_date`, `executive_order_number` ...).
- **fuel** (live; EIA's public tables, no key): `GASOLINE`, `DIESEL` (weekly US retail, $/gal),
  `WTI`, `BRENT` (daily spot, $/bbl): `latest`, `recent`, `release_date`, `next_release`. AAA's daily
  average, which KXAAAGAS* settles on, is not EIA's.
- **bls_releases**, **bea_releases** (live; the agencies' release calendars): `cpi`, `jobs`, `ppi`,
  `jolts`, `eci`, `real_earnings`, `import_prices`, `productivity`, `all` / `gdp`, `pce`, `trade`,
  `all`: `next` `{at (UTC), date, time_et}` and the next 60 days' `upcoming`. A moved date is a new row.
- **halts** (live; Nasdaq Trader's trade halts): per stock the equity desks trade, and `all`:
  `count` and `halts` (`reason` code, `halted`, `resumed_trading`); an empty list is a stock not halted.

A request for data no key-free source may give the House -- Polymarket's prices (its terms bar trading
firms), MLB/NHL/NBA line-ups and stats (their terms bar automated and commercial use), sportsbook
player props or line history (paid), FRED, Cboe, OpenRouter's rankings (keys or terms) and the like --
is answered on the ledger with the rule it fails (`tool.blocked`, `league/open_feeds.py` `REFUSALS`),
and stays answered unless a recorder that passes the rule is built.

