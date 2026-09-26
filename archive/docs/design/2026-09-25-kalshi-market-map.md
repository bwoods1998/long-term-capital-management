# Kalshi market map (J4, Sept 25, 2026)

What Kalshi trades, how each series settles, and which of the House's recorded feeds could price it:
the Jev run's J4 market discovery (`docs/goals/LTCM_JEV_SENSES.md`), read-only. Jev (`jev-1.13.0`) answered
`choice` questions for the settlement mechanics and the pricing feed of each series; deterministic prefix rules
override it where they apply, and its agreement with them is reported. Jev labels are reading aids: they carry
no order, promotion, spending or merge authority. The script is `scripts/jev_lab_eval/market_map.py` (it lands
with the Jev run's next House deploy); its bulk output (one row per series) is kept out of the repository.

Kalshi pulled 2026-09-25 07:15Z (131,970 open non-combo markets in 4,132 series, 2,382 with any 24 h volume). Counted: the **1,654 series** with at least 100 contracts traded in 24 h, 59.31M contracts. House snapshot 2026-09-25 06:41Z (last survey 2026-09-24 10:46Z). Jev (jev-1.13.0, j4-map-v1): 1,654 series classified, **$0.1410** spent in total ({'http_502': 92, 'ok': 443}).

Volume is contracts traded in the last 24 h across all of a series' open markets; `48h` is the part in markets that stop within 48 h (what `league.niches.survey` counts and the desks can trade). Mechanics and feed are Jev's `choice` answers, overridden by the deterministic prefix rule where one applies and Jev disagrees; the feed is then checked against what the House records now (its league, coin, station or stock; owner-key and bot-walled feeds). A series is covered when a non-open Kalshi desk lists it or the survey's pattern rule claims it.

## Headline: 24 h volume by mechanics x feed availability

| mechanics | recorded | key_missing | owner_key_or_blocked | venue_only | none | total | share |
|---|---:|---:|---:|---:|---:|---:|---:|
| discrete_sports_outcome | 10.89M (170) | 5.87M (58) | - | - | 23.60M (228) | 40.36M | 68.0% |
| political_or_legal_event | 6k (1) | - | 98k (5) | - | 8.93M (375) | 9.04M | 15.2% |
| mention_or_media | 21k (6) | 2k (2) | 7k (1) | - | 2.96M (186) | 2.99M | 5.0% |
| continuous_price_threshold | 1.84M (46) | 1k (1) | 0.39M (26) | - | 0.17M (56) | 2.41M | 4.1% |
| sports_stat_threshold | 1.06M (43) | 16k (7) | - | - | 0.61M (40) | 1.68M | 2.8% |
| weather_observation | 1.02M (49) | 21k (15) | - | - | 90k (18) | 1.13M | 1.9% |
| economic_release | 0.37M (16) | - | 499 (2) | - | 0.50M (114) | 0.86M | 1.5% |
| company_event | 4k (4) | 9k (4) | - | - | 0.44M (147) | 0.45M | 0.8% |
| other | - | - | - | - | 0.20M (19) | 0.20M | 0.3% |
| price_range_bucket | 24k (4) | 0.10M (4) | 28k (1) | - | 37k (6) | 0.19M | 0.3% |
| **all** | 15.23M | 6.02M | 0.53M | 0 | 37.54M | 59.31M | 100% |

Cells: volume (series). `recorded`: a recorded feed covers it now; `key_missing`: the feed exists, its league/coin/station/stock is not recorded; `owner_key_or_blocked`: the feed waits for an owner key or a bot wall; `venue_only`: Kalshi's own quotes only; `none`: no feed.

## Coverage

- Covered by a Kalshi desk: 208 series, 31.37M (53% of volume).
- Covered but with no recorded feed pricing it: 20.38M.
- Not covered but a recorded feed prices it: 241 series, 4.23M.

## Jev against the deterministic rules

- **mechanics**: 616/635 = **97.0%** agree. By rule: crypto_coin_prefix 12/12; mentions 40/40; prices_desk_prefix 35/35; sports_game_pattern 194/194; sports_league_prefix 251/261; sports_props_pattern 25/34; weather_prefix 59/59.
  Disagreements (rule: Jev's answer x n): sports_props_pattern: discrete_sports_outcome x9; sports_league_prefix: mention_or_media x8; sports_league_prefix: other x1; sports_league_prefix: political_or_legal_event x1.
- **feed**: 169/189 = **89.4%** agree. By rule: approval 2/2; crypto_coin_prefix 12/12; energy_prices 18/28; fed_rates 7/10; mapped_league_game 58/59; treasury 15/18; tsa 1/1; weather_prefix 56/59.
  Disagreements (rule: Jev's answer x n): energy_prices: none x10; fed_rates: none x3; treasury: none x3; weather_prefix: none x3; mapped_league_game: none x1.

## Top 30 by volume: no desk covers it, a recorded feed could price it

| # | series | title | 24h | 48h | mechanics | feed (key, status) | desk |
|---:|---|---|---:|---:|---|---|---|
| 1 | KXMLB | World Series | 0.84M | 0 | discrete_sports_outcome | odds (mlb, recording) | none |
| 2 | KXNFLMATCHUP | Pro Football Matchups | 0.38M | 0 | discrete_sports_outcome | odds (nfl, recording) | none |
| 3 | KXWNBA | WNBA Championship | 0.32M | 0 | discrete_sports_outcome | sports (wnba, recording) | none |
| 4 | KXFEDDECISION | Fed meeting | 0.31M | 0 | economic_release | rates (BGCR,EFFR,OBFR,SOFR,TGCR, recording) | none |
| 5 | KXNCAAF | NCAAF Championship | 0.21M | 0 | discrete_sports_outcome | sports (ncaaf, recording) | none |
| 6 | KXNFLNFCCHAMP | National Football Conference Champion | 0.19M | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 7 | KXMLBPLAYOFFS | Pro Baseball Playoff Qualifiers | 0.17M | 0 | discrete_sports_outcome | sports (mlb, recording) | none |
| 8 | KXNBA | Pro Basketball Champion | 0.17M | 0 | discrete_sports_outcome | sports (nba, recording) | none |
| 9 | KXBTCMAXMON | Bitcoin monthly one touch | 0.16M | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 10 | KXNFLAFCCHAMP | American Football Conference Champion | 80k | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 11 | KXBTC2026200 | Will Bitcoin hit 200k in 2026?  | 77k | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 12 | KXMLBNL | MLB National League Championship | 75k | 0 | discrete_sports_outcome | odds (mlb, recording) | none |
| 13 | KXNFLWINS | Pro Football Wins | 71k | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 14 | KXNCAAFB12 | Big 12 Champion | 65k | 0 | discrete_sports_outcome | sports (ncaaf, recording) | none |
| 15 | KXMLBAL | MLB American League Championship | 54k | 0 | discrete_sports_outcome | odds (mlb, recording) | none |
| 16 | KXNFLAFCNORTH | American Football Conference North Winner | 53k | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 17 | KXNFLPLAYOFF | Pro Football Playoff Qualifiers | 44k | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 18 | KXNHL | Stanley Cup | 42k | 0 | discrete_sports_outcome | sports (nhl, recording) | none |
| 19 | KXMLBALWEST | American League West Winner | 39k | 0 | discrete_sports_outcome | sports (mlb, recording) | none |
| 20 | KXBTC50VS100 | Will BTC fall below 50k before hitting 100k? | 37k | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 21 | KXBTCMAX150 | When will bitcoin hit 150k? | 32k | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 22 | KXBTCMINMON | BTC one touch minimum | 30k | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 23 | KXMLBALCENT | American League Central Winner | 30k | 0 | discrete_sports_outcome | sports (mlb, recording) | none |
| 24 | KXNFLLASTTOLOSE | Pro Football Last Undefeated Team | 25k | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 25 | KXNFLAFCSOUTH | American Football Conference South Winner | 25k | 0 | discrete_sports_outcome | odds (nfl, recording) | none |
| 26 | KXBTCMAXY | How high will Bitcoin get this year? | 24k | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 27 | KXBTCMAX100 | When will bitcoin hit 100k? | 23k | 0 | continuous_price_threshold | perps (BTC, recording) | none |
| 28 | KXNCAAFSEC | SEC Champion | 22k | 0 | discrete_sports_outcome | sports (ncaaf, recording) | none |
| 29 | KXNFLNFCNORTH | National Football Conference North Winner | 22k | 0 | discrete_sports_outcome | sports (nfl, recording) | none |
| 30 | KXNCAAFWINS | College Football Win Total | 17k | 0 | discrete_sports_outcome | sports (ncaaf, recording) | none |

## Top 30 by volume with no feed at all (what would unlock it)

| # | series | title | 24h | 48h | mechanics | feed (key, status) | settles on -> unlock |
|---:|---|---|---:|---:|---|---|---|
| 1 | KXWTAMATCH | WTA Tennis Match | 10.03M | 32k | discrete_sports_outcome | none (none) | WTA -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 2 | KXDPWORLDTOUR | DP World Tour Tournament Winner | 3.06M | 3.06M | discrete_sports_outcome | none (none) | DP World Tour -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 3 | KXATPMATCH | ATP Tennis Match | 2.85M | 2.80M | discrete_sports_outcome | none (none) | ATP -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 4 | KXPRESNOMD | Democratic Primary winner | 1.42M | 0 | political_or_legal_event | none (none) | Republican Party; Democratic Party -> polling averages and election-result feeds |
| 5 | KXT20MATCH | Men's T20 Cricket Match | 1.07M | 1.05M | discrete_sports_outcome | none (none) | Cricbuzz; ESPN cricinfo; ICC; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 6 | CONTROLH | House winner | 0.97M | 0 | political_or_legal_event | none (none) | Library of Congress -> congress.gov / Federal Register / court dockets as event features |
| 7 | SENATEME | Maine Senate race | 0.88M | 0 | political_or_legal_event | none (none) | United States Congress -> congress.gov / Federal Register / court dockets as event features |
| 8 | KXRT | Rotten Tomatoes Scores | 0.77M | 0 | mention_or_media | none (none) | Rotten Tomatoes -> the chart or rating source's own history (Billboard/Spotify/YouTube/Rotten Tomatoes/box office) |
| 9 | CONTROLS | Senate winner | 0.65M | 0 | political_or_legal_event | none (none) | Library of Congress -> congress.gov / Federal Register / court dockets as event features |
| 10 | KXINTLFRIENDLYGAME | International Friendly Game | 0.62M | 0.61M | discrete_sports_outcome | none (none) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 11 | KXBALANCEPOWERCOMBO | Congress balance of power combo | 0.62M | 0 | political_or_legal_event | none (none) | Bureau of Labor Statistics; Bureau of Labor Statistics; Fede -> the release calendar plus nowcasts/consensus (Cleveland Fed CPI nowcast, BLS history) |
| 12 | KXPRESCUP | President's Cup | 0.54M | 0 | discrete_sports_outcome | none (none) | The Wall Street Journal; ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 13 | KXITFMATCH | ITF Men's Match | 0.51M | 0.15M | discrete_sports_outcome | none (none) | ITF; Flashscore; Fox Sports; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 14 | KXPRESCUPPTSLEAD | Presidents Cup Points Leader | 0.45M | 0 | sports_stat_threshold | none (none) | ESPN; the Governing League -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 15 | SENATEOHS | Special Senate election in Ohio | 0.34M | 0 | political_or_legal_event | none (none) | United States Congress -> congress.gov / Federal Register / court dockets as event features |
| 16 | SENATENE | Nebraska Senate race | 0.30M | 0 | political_or_legal_event | none (none) | United States Congress -> congress.gov / Federal Register / court dockets as event features |
| 17 | KXNFLMVP | AP Pro Football Regular Season MVP | 0.27M | 0 | discrete_sports_outcome | none (none) | the Governing League; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 18 | KXAFCONGAME | AFCON Game Winner | 0.27M | 0.27M | discrete_sports_outcome | none (none) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 19 | KXUFCFIGHT | UFC Fight | 0.26M | 0.22M | discrete_sports_outcome | none (none) | DAZN; ESPN; Fox Sports; the Governing League -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 20 | KXBIGBROTHER | who will win big brother | 0.25M | 0 | mention_or_media | none (none) | CBS; Paramount+ -> the chart or rating source's own history (Billboard/Spotify/YouTube/Rotten Tomatoes/box office) |
| 21 | KXPRESNOMR | Republican Primary winner | 0.23M | 0 | political_or_legal_event | none (none) | Republican Party; Democratic Party -> polling averages and election-result feeds |
| 22 | SENATENH | New Hampshire Senate race | 0.23M | 0 | political_or_legal_event | none (none) | United States Congress -> congress.gov / Federal Register / court dockets as event features |
| 23 | KXPRESCUPMATCH | Presidents Cup matches | 0.22M | 0.22M | discrete_sports_outcome | none (none) | ESPN; the Governing League -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 24 | KXVMA | who will win VMA award  | 0.22M | 0 | mention_or_media | none (none) | MTV -> the chart or rating source's own history (Billboard/Spotify/YouTube/Rotten Tomatoes/box office) |
| 25 | KXF1RACE | F1 Race | 0.19M | 0.19M | discrete_sports_outcome | none (none) | FIA -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 26 | KXPRESPERSON | Pres person | 0.18M | 0 | political_or_legal_event | none (none) | Office of the Presidency -> congress.gov / Federal Register / court dockets as event features |
| 27 | KXINTLFRIENDLYTOTAL | International Friendly Total | 0.18M | 0.18M | discrete_sports_outcome | none (none) | Fox Sports; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 28 | SENATETX | Texas Senate race | 0.17M | 0 | political_or_legal_event | none (none) | United States Congress -> congress.gov / Federal Register / court dockets as event features |
| 29 | KXGOVCA | California Governor's race | 0.17M | 0 | political_or_legal_event | none (none) | Fox News; MSNBC; The Wall Street Journal; Semafor; ABC; The  -> news-volume and event features (GDELT, J4's first bullet) and, for elections, polling averages |
| 30 | KXODIMATCH | Men's ODI Cricket Match | 0.16M | 0.13M | discrete_sports_outcome | none (none) | ESPNcricinfo; Cricbuzz; ICC; ESPN; BBC Sport -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |

## Top 15 uncovered: the feed exists but its key is not recorded (or waits for an owner key)

| # | series | title | 24h | 48h | mechanics | feed (key, status) | settles on -> unlock |
|---:|---|---|---:|---:|---|---|---|
| 1 | KXSB | Super Bowl | 4.37M | 0 | discrete_sports_outcome | sports (key_unmapped) | ESPN; Fox Sports; AP -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 2 | KXBTCY | BTC price range EOY | 98k | 0 | price_range_bucket | perps (BTCY, key_not_recorded) | CF Benchmarks -> the coin's spot and perps (add the coin to the perps/funding keys) |
| 3 | KXRECORDNFLBEST | best football record | 65k | 0 | discrete_sports_outcome | sports (key_unmapped) | the Governing League; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 4 | KXTEAMSINWS | Teams in MLB Finals | 52k | 0 | discrete_sports_outcome | sports (key_unmapped) | ESPN; the Governing League -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 5 | KXUEFANLSCORE | Correct Score | 50k | 50k | discrete_sports_outcome | sports (key_unmapped) | ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 6 | KXWTIMAX | WTI oil high | 43k | 0 | continuous_price_threshold | eia (owner_key) | ICE -> the settlement source itself |
| 7 | KXPREMIERLEAGUE | PREMIER LEAGUE | 33k | 0 | discrete_sports_outcome | odds (key_unmapped) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 8 | KXAFCONSCORE | Correct Score | 28k | 28k | discrete_sports_outcome | sports (key_unmapped) | ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 9 | KXAPRPOTUS | President RCP approval rating this week | 28k | 28k | political_or_legal_event | polls (blocked) | RealClearPolitics -> a polling average without a bot wall |
| 10 | KXRECORDNFLWORST | worst football record | 25k | 0 | discrete_sports_outcome | sports (key_unmapped) | the Governing League; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 11 | KXUCL | UEFA Champions League | 23k | 0 | discrete_sports_outcome | odds (key_unmapped) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 12 | KXAAAGASM | US gas price | 15k | 0 | continuous_price_threshold | eia (owner_key) | AAA -> AAA's daily national and state gas averages (the settlement source itself; EIA weekly is only a proxy) |
| 13 | KXBRENTMON | Brent Monthly | 14k | 0 | continuous_price_threshold | eia (owner_key) | Pyth - Brent -> the oracle's own price feed |
| 14 | KXLEADERWNBAAST | WNBA APG Leader | 14k | 0 | sports_stat_threshold | sports (key_unmapped) | the Governing League; ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 15 | KXDIESELMON | Diesel Prices month | 12k | 0 | continuous_price_threshold | eia (owner_key) | AAA -> AAA's daily national and state gas averages (the settlement source itself; EIA weekly is only a proxy) |

## Top 15 covered by a desk whose feed does not record them

| # | series | title | 24h | 48h | mechanics | feed (key, status) | settles on -> unlock |
|---:|---|---|---:|---:|---|---|---|
| 1 | KXUEFANLGAME | UEFA Nations League Game | 0.81M | 0.78M | discrete_sports_outcome | odds (key_unmapped) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 2 | KXAAAGASW | US gas price up | 0.12M | 0 | continuous_price_threshold | eia (owner_key) | AAA -> AAA's daily national and state gas averages (the settlement source itself; EIA weekly is only a proxy) |
| 3 | KXUEFANLSPREAD | Spread | 81k | 78k | discrete_sports_outcome | odds (key_unmapped) | Fox Sports; ESPN -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 4 | KXWTI | WTI oil on day | 74k | 69k | continuous_price_threshold | eia (owner_key) | ICE -> the underlying's spot/index price (stock indices, FX, metals, commodities) |
| 5 | KXATPGTOTAL | ATP Total Games | 70k | 70k | discrete_sports_outcome | sports (key_unmapped) | ATP -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 6 | KXTRUMPAPPROVE | Trump approval rating | 67k | 67k | political_or_legal_event | polls (blocked) | RealClearPolitics -> a polling average without a bot wall |
| 7 | KXUEFANLTOTAL | Point Total | 58k | 51k | discrete_sports_outcome | odds (key_unmapped) | FIFA -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 8 | KXBRENTW | Brent Oil | 42k | 42k | continuous_price_threshold | eia (owner_key) | Pyth - Brent -> the oracle's own price feed |
| 9 | KXDIESELW | diesel price week | 38k | 0 | continuous_price_threshold | eia (owner_key) | AAA -> AAA's daily national and state gas averages (the settlement source itself; EIA weekly is only a proxy) |
| 10 | KXATPGSPREAD | ATP Game Spread | 36k | 36k | discrete_sports_outcome | sports (key_unmapped) | ESPN; Fox Sports; ATP -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 11 | KXUEFANLBTTS | BTTS | 31k | 29k | discrete_sports_outcome | sports (key_unmapped) | FIFA -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 12 | KXWTIW | WTI oil weekly range | 28k | 28k | price_range_bucket | eia (owner_key) | ICE -> the underlying's spot/index price (stock indices, FX, metals, commodities) |
| 13 | KXINTLFRIENDLY1H | 1st Half Winner | 22k | 22k | discrete_sports_outcome | sports (key_unmapped) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 14 | KXCOUNTYCHAMPMATCH | County Championship Cricket Match | 12k | 0 | discrete_sports_outcome | sports (key_unmapped) | ESPNcricinfo; BBC; England and Wales Cricket Board -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |
| 15 | KXUEFANL1H | 1st Half Winner | 12k | 12k | discrete_sports_outcome | sports (key_unmapped) | ESPN; Fox Sports -> that sport's scoreboard and sportsbook odds (ESPN covers tennis, golf, cricket, MMA, F1 and more leagues than SPORTS_SERIES maps; futures need outright/futures odds) |

## Settlement source families (24 h volume)

| family | volume |
|---|---:|
| sports_official_or_espn | 42.26M |
| government_official | 5.74M |
| media_charts_ratings | 2.09M |
| crypto_index_cf_benchmarks | 1.94M |
| election_authority | 1.69M |
| weather_company | 1.05M |
| news_reports | 0.99M |
| bls | 0.85M |
| other | 0.84M |
| federal_reserve | 0.49M |
| kalshi_itself | 0.37M |
| company_reports | 0.23M |
| aaa_gas | 0.22M |
| market_price_source | 0.18M |
| price_oracle | 0.11M |
| polls | 0.10M |
| nws_noaa | 70k |
| treasury | 39k |
| bea | 19k |
| eia | 16k |
| dol_census_other_stats | 4k |
| tsa | 394 |

