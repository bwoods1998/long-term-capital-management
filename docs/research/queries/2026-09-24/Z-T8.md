# gap scoreboard: ledger 475,400 rows to 2026-09-24T09:34:23.628Z; window since 2026-09-23T09:34:23Z; baseline 2026-09-24T05:37:31Z; release 20260924T082939Z-019dd23442a9; board 2026-09-24T09:34:01.967Z; feeds store yes

| # | Metric | Reading | Computed by |
|---|---|---|---|
| 1 | families with a positive real lower bound; capacity (and proven by the House's pooled record) | 1 (sports-central-run-under real n 5, $94.57/day); 0 on >= 10 real events; proven (house record): 1 (sports-central-run-under n 19, real n 5, $94.57/day) | `real_bounds, family_capacity` |
| 2 | allocator promotions to real money: settled result, share positive (since the baseline) | 0 promotions, $0.00 on 0 settlements, 0 positive (-);  | `allocator_promotions` |
| 3 | real dollars in proven / unproven families; Alpaca real agents | $20.54 / $122.35; 1 | `real_dollars` |
| 4 | median life (h), all / day-horizon; deaths before 3 fills (of them, agents that held a practice seat) | 9.59 / 5.79 h over 124 deaths; 76 (61%); seated: 118 deaths, median 10.91 h, 70 (59%) before 3 fills | `deaths_in_window` |
| 5 | lab batches an hour; LLM share of born graduates; waiters, longest wait; supersessions | 106 in the last hour; 14 of 50; 23 at 41.73 h; 3 superseded in the window (0 on real money), 0 of 3 real-money parents with a passing research child | `lab_loop` |
| 6 | self-cross refusals of reducing orders (6 h); promotions on stacked positions | 8; 0 of 0 (below the bunt counts: 0 with every close counted per event, 0 with settlements only) | `self_cross_exits, stacked_promotions` |
| 7 | recorders live on the allowed hosts; desks offered markets with no intent (48 h) | 9 of 12; 0 (-) | `recorders_live, idle_desks` |

## 1. families with a positive real lower bound [real_bounds, family_capacity]
- the family record read: house (the House own function, league.families / league.allocator family_record)
- kalshi/sports-central-run-under: real n 5 (eff 3.8) mean +0.7599 sd 0.0976 lcb +0.2913
-   capacity $94.57/day = 24.28 markets bid a day (37 over 1.52 days) x fill rate 1.0 (real, bids <=$12, median $9.40) x $3.89 a settlement (real, n 5); real seats earn $12.78/day now
- PROVEN kalshi/sports-central-run-under: pooled n 19 (eff 13.6) mean +0.3934 sd 0.8009 lcb +0.2040 PROVEN; real n 5 (eff 3.8) mean +0.7599 sd 0.0976 lcb +0.2913
-   capacity $94.57/day = 24.28 markets bid a day (37 over 1.52 days) x fill rate 1.0 (real, bids <=$12, median $9.40) x $3.89 a settlement (real, n 5); real seats earn $12.78/day now
- families with any real closed trade: 12

## 2. allocator promotions to real money [allocator_promotions]

## 3. real dollars by family state [real_dollars]
- haghani-56 alpaca probe $25.00 crypto-alts-reversion unproven (board: unproven)
- hawkins-19 kalshi probe $14.13 prices-favorites unproven (board: unproven)
- hilibrand-h6ca596-3 kalshi probe $10.62 crypto-strikes-vol-shock-upside unproven (board: unproven)
- hilibrand-lc04657 kalshi probe $6.82 crypto-strikes-lab-955dae unproven (board: unproven)
- meriwether-h2d625d kalshi bunt $20.54 sports-central-run-under proven (board: proven)
- meriwether-h7d7702 kalshi probe $0.00 sports-central-over-under unproven (board: unproven)
- mullins-2 kalshi probe $29.08 weather-favorites unproven (board: unproven)
- mullins-6 kalshi probe $36.70 weather-favorites unproven (board: unproven)
- Alpaca agents ever staked on real money: 2

## 4. deaths in the window [deaths_in_window]
- 124 deaths since 2026-09-23T09:34:23Z; causes {'displaced': 117, 'evidence': 3, 'stuck': 1, 'superseded': 3}
- day-horizon agents: 63 deaths, median 5.79 h, 46 before 3 fills; on day-only desks: 57 deaths, median 5.48 h
- agents that held a practice seat: 118 deaths, median 10.91 h, 70 (59%) before 3 fills; the rest never left replay (rung 0) and could not fill

## 5. the lab and the loop [lab_loop]
- batches: 106 in the last hour, 47.96 an hour over the window, the last at 2026-09-24T09:33:09Z
- born graduates by origin {'param': 36, 'agent': 5, 'sol': 3, 'luna': 6}; in the window {'param': 36, 'agent': 5, 'sol': 3, 'luna': 6}
- waiting: 14 graduates (longest 19.02 h since passing), 9 cards (longest 41.73 h since passing replay)
- superseded in the window: 3 (0 on real money); real-money parents with a replay-passing research child: 3 (0 superseded, 2 still on real money)
-   mullins-2 -> mullins-14 passed replay 2026-09-23T16:45:23Z; parent superseded False, demoted since False, on real money now True
-   mullins-2 -> mullins-18 passed replay 2026-09-23T05:32:14Z; parent superseded False, demoted since False, on real money now True
-   huang-h51fdd3-2 -> huang-h51fdd3-3 passed replay 2026-09-23T19:31:49Z; parent superseded False, demoted since True, on real money now False
-   meriwether-h2d625d -> meriwether-h2d625d-2 passed replay 2026-09-24T00:18:31Z; parent superseded False, demoted since False, on real money now True
-   mullins-2 -> mullins-20 passed replay 2026-09-23T22:31:15Z; parent superseded False, demoted since False, on real money now True

## 6. exits and stacked records [self_cross_exits, stacked_promotions]
- self-cross refusals in 6 h: 11, of them reducing (sell intents) 8; by agent {'haghani-60': 8}
- bunt counts: 5 closed trades or 3 settlements

## 7. inputs [recorders_live, idle_desks]
- read from feeds.sqlite; feeds live in the last day: ['earnings', 'earnings_date', 'forecast', 'funding', 'nws', 'odds', 'oi', 'perps', 'rates', 'sports', 'treasury', 'tsa', 'vol', 'weather']
- api.open-meteo.com: not recorded (feeds -)
- ensemble-api.open-meteo.com: LIVE (feeds weather)
- historical-forecast-api.open-meteo.com: LIVE (feeds forecast)
- api.weather.gov: LIVE (feeds nws)
- www.sec.gov: LIVE (feeds earnings)
- efts.sec.gov: not recorded (feeds -)
- api.nasdaq.com: LIVE (feeds earnings_date)
- markets.newyorkfed.org: LIVE (feeds rates)
- home.treasury.gov: LIVE (feeds treasury)
- sports.core.api.espn.com: LIVE (feeds odds)
- www.tsa.gov: LIVE (feeds tsa)
- www.realclearpolling.com: not recorded (feeds polls)

## evidence clocks: first fill to the third independent settlement, members whose first fill is in the last 7 days [evidence_clocks]
- alpaca-crypto-alts: Kaplan-Meier median 3.8 h; 22 of 29 reached it (median 3.3 h among them); the longest still waiting or dead first 43.5 h
- alpaca-crypto-majors: Kaplan-Meier median not reached h; 1 of 13 reached it (median 5.2 h among them); the longest still waiting or dead first 28.0 h
- alpaca-index-etfs: Kaplan-Meier median 19.2 h; 3 of 15 reached it (median 18.1 h among them); the longest still waiting or dead first 38.2 h
- alpaca-megacaps: Kaplan-Meier median 4.4 h; 5 of 9 reached it (median 2.5 h among them); the longest still waiting or dead first 19.7 h
- alpaca-open: Kaplan-Meier median not reached h; 0 of 1 reached it (median None h among them); the longest still waiting or dead first 0.5 h
- alpaca-options: Kaplan-Meier median 23.9 h; 1 of 13 reached it (median 23.9 h among them); the longest still waiting or dead first 20.6 h
- kalshi-attention: Kaplan-Meier median not reached h; 0 of 2 reached it (median None h among them); the longest still waiting or dead first 71.8 h
- kalshi-crypto-15m: Kaplan-Meier median 3.7 h; 22 of 30 reached it (median 1.9 h among them); the longest still waiting or dead first 26.4 h
- kalshi-crypto-strikes: Kaplan-Meier median 3.2 h; 7 of 8 reached it (median 3.2 h among them); the longest still waiting or dead first 11.4 h
- kalshi-prices: Kaplan-Meier median 36.5 h; 4 of 13 reached it (median 38.6 h among them); the longest still waiting or dead first 27.7 h
- kalshi-sports: Kaplan-Meier median 20.6 h; 16 of 29 reached it (median 15.7 h among them); the longest still waiting or dead first 23.7 h
- kalshi-sports-props: Kaplan-Meier median not reached h; 0 of 6 reached it (median None h among them); the longest still waiting or dead first 31.2 h
- kalshi-weather: Kaplan-Meier median 31.8 h; 3 of 25 reached it (median 31.8 h among them); the longest still waiting or dead first 39.7 h

## family records: practice 0.5 + real 1, one observation an event [family_records]
- 50 of 82 families have a closed trade; proven: sports-central-run-under
- alpaca/crypto-alts-reversion: n 201 (eff 197.5) mean -0.0047 sd 0.0229 lcb -0.0061; members 64 (10 living), real stake $25.00
-   practice (account unit) n 200 (eff 200.0) mean -0.0006 sd 0.0039 lcb -0.0008 | real n 1 (eff 1.0) mean -0.0421 sd - lcb - | maker n 0 | taker n 201 (eff 197.5) mean -0.0047 sd 0.0229 lcb -0.0061
- kalshi/crypto-15m-favorites: n 106 (eff 98.6) mean -0.1041 sd 0.5515 lcb -0.1510; members 28 (0 living), real stake $0.00
-   practice (account unit) n 100 (eff 100.0) mean -0.0060 sd 0.0266 lcb -0.0083 | real n 6 (eff 5.4) mean +0.0074 sd 0.7986 lcb -0.3138 | maker n 78 (eff 77.9) mean -0.1091 sd 0.4244 lcb -0.1588 | taker n 29 (eff 24.3) mean -0.0837 sd 0.7723 lcb -0.2179
- kalshi/crypto-15m-spot-impulse-lag: n 57 (eff 50.5) mean -0.0720 sd 0.8189 lcb -0.1699; members 9 (2 living), real stake $0.00
-   practice (account unit) n 53 (eff 53.0) mean +0.0005 sd 0.0117 lcb -0.0009 | real n 8 (eff 7.3) mean -0.3760 sd 0.7986 lcb -0.6426 | maker n 16 (eff 15.4) mean -0.1001 sd 1.1097 lcb -0.3457 | taker n 48 (eff 42.1) mean -0.0603 sd 0.7667 lcb -0.1608
- kalshi/kalshi-favorites: n 35 (eff 27.9) mean -0.0570 sd 0.3351 lcb -0.1312; members 37 (0 living), real stake $0.00
-   practice (account unit) n 35 (eff 35.0) mean -0.0060 sd 0.0378 lcb -0.0114 | real n 0 | maker n 35 (eff 27.9) mean -0.0570 sd 0.3351 lcb -0.1312 | taker n 0
- kalshi/crypto-15m-prior-window-reset: n 34 (eff 27.1) mean -0.1042 sd 1.1126 lcb -0.2870; members 2 (0 living), real stake $0.00
-   practice (account unit) n 26 (eff 26.0) mean -0.0088 sd 0.0774 lcb -0.0218 | real n 8 (eff 6.9) mean -0.4097 sd 1.0426 lcb -0.7703 | maker n 0 | taker n 34 (eff 27.1) mean -0.1042 sd 1.1126 lcb -0.2870
- kalshi/sports-favorites: n 29 (eff 27.6) mean -0.0206 sd 0.3702 lcb -0.1361; members 55 (4 living), real stake $0.00
-   practice (account unit) n 29 (eff 29.0) mean -0.0011 sd 0.0204 lcb -0.0044 | real n 0 | maker n 21 (eff 20.4) mean -0.0568 sd 0.3237 lcb -0.1981 | taker n 14 (eff 13.2) mean -0.0128 sd 0.4551 lcb -0.1761
- kalshi/crypto-15m-doge-flat-spot-no: n 23 (eff 19.8) mean -0.4694 sd 1.0159 lcb -0.6660; members 6 (1 living), real stake $0.00
-   practice (account unit) n 19 (eff 19.0) mean -0.0103 sd 0.0234 lcb -0.0150 | real n 4 (eff 3.9) mean -0.3821 sd 0.8138 lcb -0.7885 | maker n 10 (eff 8.2) mean -0.1963 sd 1.2583 lcb -0.5887 | taker n 13 (eff 12.6) mean -0.7489 sd 0.6632 lcb -0.9122
- kalshi/crypto-15m-lab-335592: n 23 (eff 19.6) mean -0.1684 sd 0.9463 lcb -0.3525; members 5 (2 living), real stake $0.00
-   practice (account unit) n 20 (eff 20.0) mean -0.0044 sd 0.0365 lcb -0.0114 | real n 3 (eff 3.0) mean -0.3665 sd 1.0538 lcb -1.0135 | maker n 12 (eff 10.7) mean -0.1095 sd 0.9146 lcb -0.3550 | taker n 12 (eff 9.8) mean -0.1532 sd 1.0457 lcb -0.4485
- kalshi/sports-runline-leverage-tax: n 21 (eff 19.5) mean -0.0982 sd 0.7762 lcb -0.2495; members 5 (1 living), real stake $0.00
-   practice (account unit) n 21 (eff 21.0) mean -0.0076 sd 0.0508 lcb -0.0171 | real n 0 | maker n 0 | taker n 21 (eff 19.5) mean -0.0982 sd 0.7762 lcb -0.2495
- kalshi/crypto-15m-eth-prior-window-fad: n 20 (eff 19.3) mean -0.2174 sd 0.9092 lcb -0.3958; members 4 (1 living), real stake $0.00
-   practice (account unit) n 20 (eff 20.0) mean -0.0049 sd 0.0345 lcb -0.0115 | real n 0 | maker n 0 | taker n 20 (eff 19.3) mean -0.2174 sd 0.9092 lcb -0.3958
- kalshi/crypto-15m-lab-0492e4: n 20 (eff 19.2) mean +0.1262 sd 0.9186 lcb -0.0546; members 3 (1 living), real stake $0.00
-   practice (account unit) n 20 (eff 20.0) mean +0.0118 sd 0.0537 lcb +0.0015 PROVEN | real n 0 | maker n 0 | taker n 20 (eff 19.2) mean +0.1262 sd 0.9186 lcb -0.0546
- kalshi/sports-central-run-under: n 19 (eff 13.6) mean +0.3934 sd 0.8009 lcb +0.2040 PROVEN; members 2 (2 living), real stake $20.54
-   practice (account unit) n 19 (eff 19.0) mean +0.0208 sd 0.0708 lcb +0.0068 PROVEN | real n 5 (eff 3.8) mean +0.7599 sd 0.0976 lcb +0.2913 | maker n 0 | taker n 19 (eff 13.6) mean +0.3934 sd 0.8009 lcb +0.2040 PROVEN
- alpaca/megacaps-expanding-range-chas: n 17 (eff 17.0) mean -0.0005 sd 0.0034 lcb -0.0012; members 1 (0 living), real stake $0.00
-   practice (account unit) n 17 (eff 17.0) mean -0.0000 sd 0.0003 lcb -0.0001 | real n 0 | maker n 0 | taker n 17 (eff 17.0) mean -0.0005 sd 0.0034 lcb -0.0012
- alpaca/options-pullback: n 17 (eff 16.5) mean -0.1416 sd 0.2498 lcb -0.1948; members 15 (7 living), real stake $0.00
-   practice (account unit) n 17 (eff 17.0) mean -0.0158 sd 0.0301 lcb -0.0222 | real n 0 | maker n 0 | taker n 17 (eff 16.5) mean -0.1416 sd 0.2498 lcb -0.1948
- kalshi/weather-favorites: n 16 (eff 11.8) mean +0.0280 sd 0.0501 lcb -0.2112; members 25 (11 living), real stake $65.78
-   practice (account unit) n 13 (eff 13.0) mean +0.0000 sd 0.0075 lcb -0.0018 | real n 5 (eff 4.1) mean +0.0531 sd 0.0248 lcb -0.2335 | maker n 16 (eff 11.8) mean +0.0280 sd 0.0501 lcb -0.2112 | taker n 0
- kalshi/sports-central-under-demand: n 15 (eff 14.3) mean +0.0674 sd 0.9495 lcb -0.1511; members 3 (1 living), real stake $0.00
-   practice (account unit) n 15 (eff 15.0) mean +0.0033 sd 0.0612 lcb -0.0104 | real n 0 | maker n 4 (eff 4.0) mean -0.1934 sd 0.5543 lcb -0.4646 | taker n 11 (eff 10.3) mean +0.1623 sd 1.0660 lcb -0.1308
- alpaca/equity-trend: n 14 (eff 14.0) mean -0.0049 sd 0.0037 lcb -0.0058; members 23 (7 living), real stake $0.00
-   practice (account unit) n 14 (eff 14.0) mean -0.0005 sd 0.0003 lcb -0.0005 | real n 0 | maker n 0 | taker n 14 (eff 14.0) mean -0.0049 sd 0.0037 lcb -0.0058
- kalshi/crypto-strikes-vol-shock-upside: n 12 (eff 9.9) mean -0.0606 sd 1.6941 lcb -0.5357; members 3 (2 living), real stake $10.62
-   practice (account unit) n 8 (eff 8.0) mean -0.0319 sd 0.1627 lcb -0.0835 | real n 5 (eff 5.0) mean -0.0771 sd 2.1554 lcb -0.9878 | maker n 12 (eff 9.9) mean -0.0606 sd 1.6941 lcb -0.5357 | taker n 0
- kalshi/crypto-strikes-lab-955dae: n 11 (eff 8.6) mean +0.0631 sd 0.0232 lcb -0.0790; members 1 (1 living), real stake $6.82
-   practice (account unit) n 6 (eff 6.0) mean +0.0044 sd 0.0014 lcb +0.0039 | real n 5 (eff 4.2) mean +0.0506 sd 0.0068 lcb -0.2426 | maker n 11 (eff 8.6) mean +0.0631 sd 0.0232 lcb -0.0790 | taker n 0
- alpaca/crypto-alts-lab-e60292: n 10 (eff 10.0) mean +0.0029 sd 0.0047 lcb -0.3797; members 3 (2 living), real stake $0.00
-   practice (account unit) n 10 (eff 10.0) mean +0.0003 sd 0.0004 lcb +0.0002 PROVEN | real n 0 | maker n 0 | taker n 10 (eff 10.0) mean +0.0029 sd 0.0047 lcb -0.3797
- alpaca/crypto-reversion: n 8 (eff 8.0) mean -0.0092 sd 0.0108 lcb -0.0126; members 43 (1 living), real stake $0.00
-   practice (account unit) n 8 (eff 8.0) mean -0.0004 sd 0.0008 lcb -0.0007 | real n 0 | maker n 0 | taker n 8 (eff 8.0) mean -0.0092 sd 0.0108 lcb -0.0126
- kalshi/crypto-strikes-downside-insurance-s: n 8 (eff 6.7) mean -0.4615 sd 0.8850 lcb -0.7719; members 1 (0 living), real stake $0.00
-   practice (account unit) n 8 (eff 8.0) mean -0.0680 sd 0.1297 lcb -0.1091 | real n 0 | maker n 8 (eff 6.7) mean -0.4615 sd 0.8850 lcb -0.7719 | taker n 0
- kalshi/prices-favorites: n 7 (eff 5.7) mean -0.0026 sd 0.1187 lcb -0.0484; members 29 (2 living), real stake $14.13
-   practice (account unit) n 7 (eff 7.0) mean -0.0034 sd 0.0183 lcb -0.0097 | real n 2 (eff 1.7) mean +0.0917 sd - lcb - | maker n 7 (eff 5.7) mean -0.0026 sd 0.1187 lcb -0.0484 | taker n 0
- alpaca/crypto-alts-trend: n 6 (eff 6.0) mean +0.0064 sd 0.0589 lcb -0.0157; members 2 (0 living), real stake $0.00
-   practice (account unit) n 6 (eff 6.0) mean +0.0014 sd 0.0114 lcb -0.0029 | real n 0 | maker n 0 | taker n 6 (eff 6.0) mean +0.0064 sd 0.0589 lcb -0.0157
- alpaca/megacaps-chip-demand-relay: n 6 (eff 6.0) mean +0.0015 sd 0.0039 lcb +0.0001; members 1 (1 living), real stake $0.00
-   practice (account unit) n 6 (eff 6.0) mean +0.0002 sd 0.0005 lcb +0.0001 | real n 0 | maker n 0 | taker n 6 (eff 6.0) mean +0.0015 sd 0.0039 lcb +0.0001
- alpaca/megacaps-semiconductor-catchu: n 6 (eff 6.0) mean -0.0008 sd 0.0044 lcb -0.0025; members 3 (3 living), real stake $0.00
-   practice (account unit) n 6 (eff 6.0) mean -0.0002 sd 0.0011 lcb -0.0006 | real n 0 | maker n 0 | taker n 6 (eff 6.0) mean -0.0008 sd 0.0044 lcb -0.0025
- kalshi/sports-central-over-under: n 6 (eff 4.8) mean +0.8087 sd 1.0767 lcb +0.1807; members 1 (1 living), real stake $0.00
-   practice (account unit) n 6 (eff 6.0) mean +0.0656 sd 0.1251 lcb +0.0186 | real n 1 (eff 1.0) mean +1.8579 sd - lcb - | maker n 0 | taker n 6 (eff 4.8) mean +0.8087 sd 1.0767 lcb +0.1807
- kalshi/sports-props-favorites: n 6 (eff 5.8) mean -0.6437 sd 0.5623 lcb -0.8594; members 37 (4 living), real stake $0.00
-   practice (account unit) n 7 (eff 7.0) mean -0.0337 sd 0.0393 lcb -0.0472 | real n 0 | maker n 6 (eff 5.8) mean -0.6437 sd 0.5623 lcb -0.8594 | taker n 0
- alpaca/equity-overnight: n 5 (eff 5.0) mean -0.0028 sd 0.0034 lcb -0.0042; members 3 (1 living), real stake $0.00
-   practice (account unit) n 5 (eff 5.0) mean -0.0002 sd 0.0004 lcb -0.0004 | real n 0 | maker n 0 | taker n 5 (eff 5.0) mean -0.0028 sd 0.0034 lcb -0.0042
- alpaca/crypto-alts-funded-spot-hedge: n 4 (eff 3.7) mean -0.0357 sd 0.0418 lcb -0.0574; members 1 (0 living), real stake $0.00
-   practice (account unit) n 4 (eff 4.0) mean -0.0089 sd 0.0122 lcb -0.0148 | real n 0 | maker n 0 | taker n 4 (eff 3.7) mean -0.0357 sd 0.0418 lcb -0.0574
- alpaca/crypto-majors-absorbed-buy-program: n 4 (eff 3.6) mean -0.0185 sd 0.0127 lcb -0.0253; members 1 (0 living), real stake $0.00
-   practice (account unit) n 4 (eff 4.0) mean -0.0045 sd 0.0045 lcb -0.0067 | real n 0 | maker n 0 | taker n 4 (eff 3.6) mean -0.0185 sd 0.0127 lcb -0.0253
- alpaca/crypto-majors-lab-8899c2: n 4 (eff 3.7) mean -0.0091 sd 0.0055 lcb -0.0120; members 3 (2 living), real stake $0.00
-   practice (account unit) n 4 (eff 4.0) mean -0.0023 sd 0.0008 lcb -0.0027 | real n 0 | maker n 0 | taker n 4 (eff 3.7) mean -0.0091 sd 0.0055 lcb -0.0120
- alpaca/index-etfs-real-asset-rotation: n 4 (eff 4.0) mean -0.0018 sd 0.0021 lcb -0.0028; members 1 (1 living), real stake $0.00
-   practice (account unit) n 4 (eff 4.0) mean -0.0001 sd 0.0002 lcb -0.0002 | real n 0 | maker n 0 | taker n 4 (eff 4.0) mean -0.0018 sd 0.0021 lcb -0.0028
- alpaca/megacaps-lab-d7fe38: n 4 (eff 3.9) mean +0.0017 sd 0.0027 lcb +0.0004; members 2 (2 living), real stake $0.00
-   practice (account unit) n 4 (eff 4.0) mean +0.0007 sd 0.0010 lcb +0.0002 | real n 0 | maker n 0 | taker n 4 (eff 3.9) mean +0.0017 sd 0.0027 lcb +0.0004
- kalshi/crypto-strikes-lab-1b9d16: n 4 (eff 4.0) mean +0.0582 sd 0.0298 lcb +0.0436; members 1 (1 living), real stake $0.00
-   practice (account unit) n 4 (eff 4.0) mean +0.0027 sd 0.0013 lcb +0.0021 | real n 0 | maker n 4 (eff 4.0) mean +0.0582 sd 0.0298 lcb +0.0436 | taker n 0
- alpaca/crypto-alts-alt-basket-catchup: n 3 (eff 3.0) mean -0.0156 sd 0.0166 lcb -0.0257; members 1 (0 living), real stake $0.00
-   practice (account unit) n 3 (eff 3.0) mean -0.0015 sd 0.0017 lcb -0.0025 | real n 0 | maker n 0 | taker n 3 (eff 3.0) mean -0.0156 sd 0.0166 lcb -0.0257
- alpaca/megacaps-quiet-vwap-reclaim: n 3 (eff 3.0) mean +0.0029 sd 0.0036 lcb +0.0007; members 5 (5 living), real stake $0.00
-   practice (account unit) n 3 (eff 3.0) mean +0.0008 sd 0.0009 lcb +0.0003 | real n 0 | maker n 0 | taker n 3 (eff 3.0) mean +0.0029 sd 0.0036 lcb +0.0007
- alpaca/crypto-majors-funding-short-relief: n 2 (eff 2.0) mean -0.0216 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice (account unit) n 2 (eff 2.0) mean -0.0070 sd 0.0005 lcb -0.0075 | real n 0 | maker n 0 | taker n 2 (eff 2.0) mean -0.0216 sd - lcb -
- kalshi/crypto-15m-lab-a69fa4: n 2 (eff 2.0) mean -1.0050 sd - lcb -; members 2 (1 living), real stake $0.00
-   practice (account unit) n 2 (eff 2.0) mean -0.0581 sd 0.0046 lcb -0.0626 | real n 0 | maker n 0 | taker n 2 (eff 2.0) mean -1.0050 sd - lcb -
- kalshi/crypto-15m-prior-window-fade: n 2 (eff 2.0) mean -0.4905 sd - lcb -; members 2 (1 living), real stake $0.00
-   practice (account unit) n 2 (eff 2.0) mean -0.0295 sd 0.0455 lcb -0.0738 | real n 0 | maker n 2 (eff 2.0) mean -0.4905 sd - lcb - | taker n 0
- alpaca/crypto-majors-positive-funding-bas: n 1 (eff 1.0) mean -0.0243 sd - lcb -; members 1 (1 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.0029 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0243 sd - lcb -
- alpaca/crypto-majors-upside-gamma-hedging: n 1 (eff 1.0) mean -0.0180 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.0021 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0180 sd - lcb -
- alpaca/crypto-majors-vol-risk-rebuild: n 1 (eff 1.0) mean -0.0040 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.0004 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0040 sd - lcb -
- alpaca/index-etfs-duration-to-assets: n 1 (eff 1.0) mean -0.0034 sd - lcb -; members 1 (1 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.0002 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0034 sd - lcb -
- alpaca/index-etfs-morning-range-stops: n 1 (eff 1.0) mean -0.0011 sd - lcb -; members 2 (2 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.0002 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0011 sd - lcb -
- alpaca/megacaps-reversion: n 1 (eff 1.0) mean -0.0002 sd - lcb -; members 38 (1 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean +0.0000 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0002 sd - lcb -
- alpaca/open-squeeze-expansion: n 1 (eff 1.0) mean -0.0107 sd - lcb -; members 1 (1 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.0015 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0107 sd - lcb -
- alpaca/options-breakout: n 1 (eff 1.0) mean +0.0451 sd - lcb -; members 5 (1 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean +0.0050 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean +0.0451 sd - lcb -
- kalshi/attention-favorites: n 1 (eff 1.0) mean +0.1110 sd - lcb -; members 32 (0 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean +0.0055 sd - lcb - | real n 0 | maker n 1 (eff 1.0) mean +0.1110 sd - lcb - | taker n 0
- kalshi/crypto-15m-sol-beta-catchup: n 1 (eff 1.0) mean -1.0050 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice (account unit) n 1 (eff 1.0) mean -0.1143 sd - lcb - | real n 0 | maker n 1 (eff 1.0) mean -1.0050 sd - lcb - | taker n 0

## the weather favourites' capacity [weather_capacity]
- capacity $7.83/day = 26.59 markets bid a day (120 over 4.51 days) x fill rate 0.6 (real, bids <=$12, median $9.60) x $0.49 a settlement (real, n 12); real seats earn $1.30/day now
- settlements a day over 4.51 days: {'real': 2.66, 'all': 15.95, 'real_independent': 1.11}; practice profit a settlement -$0.24
- real bids <=$12: 18 of 30 markets filled (0.6), 22 of 38 bids
- practice bids <=$12: 53 of 112 markets filled (0.4732), 106 of 302 bids
