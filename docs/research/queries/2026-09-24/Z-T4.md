# gap scoreboard: ledger 437,170 rows to 2026-09-24T05:28:53.169Z; window since 2026-09-23T05:28:53Z; baseline -; release main-2afffaa59e86; board 2026-09-24T05:27:21.626Z; feeds store yes

| # | Metric | Reading | Computed by |
|---|---|---|---|
| 1 | families with a positive real lower bound; capacity | 4 (crypto-strikes-lab-955dae real n 5, $22.93/day; prices-favorites real n 2, $6.58/day; sports-central-run-under real n 5, $103.61/day; weather-favorites real n 5, $7.93/day); 0 on >= 10 real events | `real_bounds, family_capacity` |
| 2 | allocator promotions to real money: settled result, share positive | 12 promotions, $7.26 on 46 settlements, 3 positive (25%) | `allocator_promotions` |
| 3 | real dollars in proven / unproven families; Alpaca real agents | $117.10 / $103.98; 1 | `real_dollars` |
| 4 | median life (h), all / day-horizon; deaths before 3 fills | 12.06 / 13.32 h over 97 deaths; 53 (55%) | `deaths_in_window` |
| 5 | lab batches an hour; LLM share of born graduates; waiters, longest wait; supersessions | 16 in the last hour; 6 of 36; 10 at 37.64 h; 0 superseded in the window (0 on real money), 0 of 3 real-money parents with a passing research child | `lab_loop` |
| 6 | self-cross refusals of reducing orders (6 h); promotions on stacked positions | 34; 4 of 12 (below the bunt counts: 3 with every close counted per event, 2 with settlements only) | `self_cross_exits, stacked_promotions` |
| 7 | recorders live on the allowed hosts; desks offered markets with no intent (48 h) | 0 of 12; 1 (alpaca-open) | `recorders_live, idle_desks` |

## 1. families with a positive real lower bound [real_bounds, family_capacity]
- kalshi/crypto-strikes-lab-955dae: real n 5 (eff 5.0) mean +0.0315 sd 0.0179 lcb +0.0240; 11 rows, P&L $4.77
-   capacity $22.93/day = 72.13 markets bid a day (35 over 0.49 days) x fill rate 0.7333 (real, bids <=$12, median $10.34) x $0.43 a settlement (real, n 11); real seats earn $9.83/day now
- kalshi/prices-favorites: real n 2 (eff 2.0) mean +0.0208 sd 0.0126 lcb +0.0086; 3 rows, P&L $2.52
-   capacity $6.58/day = 15.66 markets bid a day (68 over 4.34 days) x fill rate 0.5 (real, bids <=$12, median $9.60) x $0.84 a settlement (real, n 3); real seats earn $0.58/day now
- kalshi/sports-central-run-under: real n 5 (eff 5.0) mean +0.0624 sd 0.0361 lcb +0.0472; 5 rows, P&L $19.47
-   capacity $103.61/day = 26.6 markets bid a day (36 over 1.35 days) x fill rate 1.0 (real, bids <=$12, median $9.50) x $3.89 a settlement (real, n 5); real seats earn $14.39/day now
- kalshi/weather-favorites: real n 5 (eff 5.0) mean +0.0159 sd 0.0057 lcb +0.0135; 12 rows, P&L $5.89
-   capacity $7.93/day = 26.94 markets bid a day (117 over 4.34 days) x fill rate 0.6 (real, bids <=$12, median $9.60) x $0.49 a settlement (real, n 12); real seats earn $1.36/day now
- families with any real closed trade: 12

## 2. allocator promotions to real money [allocator_promotions]
- 2026-09-23T12:10:19Z huang-h51fdd3-2 (crypto-15m-doge-flat-spot-no) to rung 2, stake None: -$2.44 on 4 settlements (4 events), 0 open; stay ended 2026-09-23T22:01:31Z; unlabelled (family record then: unproven)
- 2026-09-23T12:50:25Z meriwether-h2d625d (sports-central-run-under) to rung 2, stake 10: $19.47 on 5 settlements (5 events), 6 open; stay ended no; unlabelled (family record then: unproven)
- 2026-09-23T13:35:56Z huang-h427345 (crypto-15m-prior-window-reset) to rung 2, stake 10: -$2.55 on 1 settlements (1 events), 0 open; stay ended 2026-09-23T14:57:45Z; unlabelled (family record then: unproven)
- 2026-09-23T18:49:05Z huang-l23cdb7 (crypto-15m-lab-335592) to rung 2, stake 30: -$8.51 on 3 settlements (3 events), 0 open; stay ended 2026-09-23T20:25:51Z; unlabelled (family record then: unproven)
- 2026-09-23T20:07:05Z meriwether-h7d7702 (sports-central-over-under) to rung 2, stake 30: $16.30 on 1 settlements (1 events), 0 open; stay ended 2026-09-23T23:33:37Z; unlabelled (family record then: unproven)
- 2026-09-23T21:02:43Z hilibrand-h6ca596-3 (crypto-strikes-vol-shock-upside) to rung 2, stake 30: -$0.62 on 5 settlements (5 events), 0 open; stay ended no; unlabelled (family record then: unproven)
- 2026-09-23T22:36:33Z huang-hd8ff7c-3 (crypto-15m-spot-impulse-lag) to rung 2, stake None: -$7.94 on 6 settlements (6 events), 0 open; stay ended 2026-09-24T01:44:20Z; unlabelled (family record then: unproven)
- 2026-09-23T23:50:01Z huang-hd8ff7c-4 (crypto-15m-spot-impulse-lag) to rung 2, stake 30: -$4.66 on 3 settlements (3 events), 0 open; stay ended 2026-09-24T01:01:35Z; unlabelled (family record then: proven)
- 2026-09-24T00:17:18Z huang-h427345-2 (crypto-15m-prior-window-reset) to rung 2, stake 30: -$6.56 on 7 settlements (7 events), 0 open; stay ended 2026-09-24T03:24:31Z; unlabelled (family record then: unproven)
- 2026-09-24T00:39:48Z meriwether-h7d7702 (sports-central-over-under) to rung 2, stake 30: $0.00 on 0 settlements (0 events), 2 open; stay ended no; unlabelled (family record then: unproven)
- 2026-09-24T00:39:48Z hilibrand-lc04657 (crypto-strikes-lab-955dae) to rung 2, stake 30: $4.77 on 11 settlements (5 events), 0 open; stay ended no; unlabelled (family record then: unproven)
- 2026-09-24T02:17:34Z haghani-56 (crypto-alts-reversion) to rung 2, stake 25: $0.00 on 0 settlements (0 events), 0 open; stay ended no; unlabelled (family record then: unproven)

## 3. real dollars by family state [real_dollars]
- haghani-56 alpaca bunt $25.00 crypto-alts-reversion unproven
- hawkins-19 kalshi bunt $27.48 prices-favorites unproven
- hilibrand-h6ca596-3 kalshi bunt $30.00 crypto-strikes-vol-shock-upside unproven
- hilibrand-lc04657 kalshi bunt $30.00 crypto-strikes-lab-955dae proven
- meriwether-h2d625d kalshi bunt $20.54 sports-central-run-under proven
- meriwether-h7d7702 kalshi bunt $21.50 sports-central-over-under unproven
- mullins-2 kalshi bunt $29.86 weather-favorites proven
- mullins-6 kalshi bunt $36.70 weather-favorites proven
- Alpaca agents ever staked on real money: 2

## 4. deaths in the window [deaths_in_window]
- 97 deaths since 2026-09-23T05:28:53Z; causes {'displaced': 91, 'redundant': 2, 'evidence': 3, 'stuck': 1}
- day-horizon agents: 56 deaths, median 13.32 h, 39 before 3 fills; on day-only desks: 49 deaths, median 14.45 h

## 5. the lab and the loop [lab_loop]
- batches: 16 in the last hour, 35.92 an hour over the window, the last at 2026-09-24T05:11:23Z
- born graduates by origin {'param': 30, 'agent': 3, 'sol': 1, 'luna': 2}; in the window {'param': 30, 'agent': 3, 'sol': 1, 'luna': 2}
- waiting: 8 graduates (longest 14.93 h since passing), 2 cards (longest 37.64 h since passing replay)
- superseded in the window: 0 (0 on real money); real-money parents with a replay-passing research child: 3 (0 superseded, 2 still on real money)
-   mullins-2 -> mullins-14 passed replay 2026-09-23T16:45:23Z; parent superseded False, demoted since False, on real money now True
-   mullins-2 -> mullins-18 passed replay 2026-09-23T05:32:14Z; parent superseded False, demoted since False, on real money now True
-   huang-h51fdd3-2 -> huang-h51fdd3-3 passed replay 2026-09-23T19:31:49Z; parent superseded False, demoted since True, on real money now False
-   meriwether-h2d625d -> meriwether-h2d625d-2 passed replay 2026-09-24T00:18:31Z; parent superseded False, demoted since False, on real money now True
-   mullins-2 -> mullins-20 passed replay 2026-09-23T22:31:15Z; parent superseded False, demoted since False, on real money now True

## 6. exits and stacked records [self_cross_exits, stacked_promotions]
- self-cross refusals in 6 h: 62, of them reducing (sell intents) 34; by agent {'haghani-hb85bb8': 24, 'haghani-60': 10}
- bunt counts: 5 closed trades or 3 settlements
- 2026-09-23T12:50:25Z meriwether-h2d625d: 7 practice closes on 5 events; passes with settlements per event True, with every close per event True
- 2026-09-23T20:07:05Z meriwether-h7d7702: 3 practice closes on 1 events; passes with settlements per event False, with every close per event False
- 2026-09-23T21:02:43Z hilibrand-h6ca596-3: 4 practice closes on 2 events; passes with settlements per event False, with every close per event False
- 2026-09-24T00:39:48Z meriwether-h7d7702: 6 practice closes on 2 events; passes with settlements per event True, with every close per event False

## 7. inputs [recorders_live, idle_desks]
- read from feeds.sqlite; feeds live in the last day: ['funding', 'perps', 'sports', 'vol']
- api.open-meteo.com: not recorded (feeds -)
- ensemble-api.open-meteo.com: not recorded (feeds -)
- historical-forecast-api.open-meteo.com: not recorded (feeds -)
- api.weather.gov: not recorded (feeds -)
- www.sec.gov: not recorded (feeds -)
- efts.sec.gov: not recorded (feeds -)
- api.nasdaq.com: not recorded (feeds -)
- markets.newyorkfed.org: not recorded (feeds -)
- home.treasury.gov: not recorded (feeds -)
- sports.core.api.espn.com: not recorded (feeds -)
- www.tsa.gov: not recorded (feeds -)
- www.realclearpolling.com: not recorded (feeds -)
- alpaca-open: 41 markets offered over 65 wakes, no intent

## evidence clocks: first fill to the third independent settlement, members whose first fill is in the last 7 days [evidence_clocks]
- alpaca-crypto-alts: Kaplan-Meier median 4.1 h; 17 of 28 reached it (median 3.3 h among them); the longest still waiting or dead first 11.7 h
- alpaca-crypto-majors: Kaplan-Meier median not reached h; 2 of 10 reached it (median 8.2 h among them); the longest still waiting or dead first 28.0 h
- alpaca-index-etfs: Kaplan-Meier median 18.1 h; 5 of 15 reached it (median 18.1 h among them); the longest still waiting or dead first 34.1 h
- alpaca-megacaps: Kaplan-Meier median 4.4 h; 5 of 9 reached it (median 2.5 h among them); the longest still waiting or dead first 15.7 h
- alpaca-options: Kaplan-Meier median 23.9 h; 1 of 13 reached it (median 23.9 h among them); the longest still waiting or dead first 20.6 h
- kalshi-attention: Kaplan-Meier median not reached h; 0 of 2 reached it (median None h among them); the longest still waiting or dead first 71.8 h
- kalshi-crypto-15m: Kaplan-Meier median 2.6 h; 20 of 26 reached it (median 1.9 h among them); the longest still waiting or dead first 22.3 h
- kalshi-crypto-strikes: Kaplan-Meier median 3.2 h; 7 of 8 reached it (median 3.2 h among them); the longest still waiting or dead first 11.4 h
- kalshi-prices: Kaplan-Meier median 36.5 h; 4 of 13 reached it (median 38.6 h among them); the longest still waiting or dead first 26.0 h
- kalshi-sports: Kaplan-Meier median 20.5 h; 16 of 28 reached it (median 15.7 h among them); the longest still waiting or dead first 19.6 h
- kalshi-sports-props: Kaplan-Meier median not reached h; 0 of 6 reached it (median None h among them); the longest still waiting or dead first 27.1 h
- kalshi-weather: Kaplan-Meier median 31.8 h; 3 of 25 reached it (median 31.8 h among them); the longest still waiting or dead first 35.6 h

## family records: practice 0.5 + real 1, one observation an event [family_records]
- 48 of 73 families have a closed trade; proven: sports-central-run-under, weather-favorites, crypto-strikes-lab-955dae
- alpaca/crypto-alts-reversion: n 178 (eff 177.0) mean -0.0010 sd 0.0041 lcb -0.0012; members 62 (10 living), real stake $25.00
-   practice n 177 (eff 177.0) mean -0.0009 sd 0.0040 lcb -0.0011 | real n 1 (eff 1.0) mean -0.0085 sd - lcb - | maker n 0 | taker n 178 (eff 177.0) mean -0.0010 sd 0.0041 lcb -0.0012
- kalshi/crypto-15m-favorites: n 106 (eff 101.2) mean -0.0021 sd 0.0509 lcb -0.0064; members 28 (0 living), real stake $0.00
-   practice n 100 (eff 100.0) mean -0.0060 sd 0.0266 lcb -0.0083 | real n 6 (eff 6.0) mean +0.0307 sd 0.1424 lcb -0.0227 | maker n 78 (eff 78.0) mean -0.0053 sd 0.0205 lcb -0.0073 | taker n 29 (eff 26.1) mean +0.0054 sd 0.0866 lcb -0.0091
- kalshi/crypto-15m-spot-impulse-lag: n 52 (eff 47.4) mean -0.0095 sd 0.0385 lcb -0.0143; members 7 (4 living), real stake $0.00
-   practice n 48 (eff 48.0) mean +0.0007 sd 0.0116 lcb -0.0007 | real n 8 (eff 8.0) mean -0.0407 sd 0.0844 lcb -0.0675 | maker n 11 (eff 11.0) mean -0.0004 sd 0.0150 lcb -0.0044 | taker n 48 (eff 43.6) mean -0.0099 sd 0.0399 lcb -0.0150
- kalshi/kalshi-favorites: n 35 (eff 35.0) mean -0.0060 sd 0.0378 lcb -0.0114; members 37 (0 living), real stake $0.00
-   practice n 35 (eff 35.0) mean -0.0060 sd 0.0378 lcb -0.0114 | real n 0 | maker n 35 (eff 35.0) mean -0.0060 sd 0.0378 lcb -0.0114 | taker n 0
- kalshi/crypto-15m-prior-window-reset: n 34 (eff 30.4) mean -0.0320 sd 0.1070 lcb -0.0486; members 2 (0 living), real stake $0.00
-   practice n 26 (eff 26.0) mean -0.0088 sd 0.0774 lcb -0.0218 | real n 8 (eff 8.0) mean -0.0697 sd 0.1410 lcb -0.1143 | maker n 0 | taker n 34 (eff 30.4) mean -0.0320 sd 0.1070 lcb -0.0486
- kalshi/sports-favorites: n 29 (eff 29.0) mean -0.0011 sd 0.0204 lcb -0.0044; members 50 (6 living), real stake $0.00
-   practice n 29 (eff 29.0) mean -0.0011 sd 0.0204 lcb -0.0044 | real n 0 | maker n 21 (eff 21.0) mean -0.0025 sd 0.0159 lcb -0.0055 | taker n 14 (eff 14.0) mean -0.0019 sd 0.0281 lcb -0.0085
- kalshi/crypto-15m-lab-335592: n 21 (eff 19.2) mean -0.0320 sd 0.1353 lcb -0.0586; members 3 (2 living), real stake $0.00
-   practice n 18 (eff 18.0) mean -0.0002 sd 0.0355 lcb -0.0074 | real n 3 (eff 3.0) mean -0.1275 sd 0.2838 lcb -0.3013 | maker n 12 (eff 11.3) mean -0.0453 sd 0.1197 lcb -0.0766 | taker n 10 (eff 9.0) mean -0.0116 sd 0.1514 lcb -0.0565
- kalshi/crypto-15m-eth-prior-window-fad: n 20 (eff 20.0) mean -0.0049 sd 0.0345 lcb -0.0115; members 2 (0 living), real stake $0.00
-   practice n 20 (eff 20.0) mean -0.0049 sd 0.0345 lcb -0.0115 | real n 0 | maker n 0 | taker n 20 (eff 20.0) mean -0.0049 sd 0.0345 lcb -0.0115
- kalshi/sports-runline-leverage-tax: n 20 (eff 20.0) mean -0.0105 sd 0.0503 lcb -0.0202; members 4 (1 living), real stake $0.00
-   practice n 20 (eff 20.0) mean -0.0105 sd 0.0503 lcb -0.0202 | real n 0 | maker n 0 | taker n 20 (eff 20.0) mean -0.0105 sd 0.0503 lcb -0.0202
- kalshi/crypto-15m-doge-flat-spot-no: n 19 (eff 17.1) mean -0.0313 sd 0.0782 lcb -0.0477; members 5 (3 living), real stake $0.00
-   practice n 15 (eff 15.0) mean -0.0126 sd 0.0257 lcb -0.0183 | real n 4 (eff 4.0) mean -0.0664 sd 0.1342 lcb -0.1321 | maker n 10 (eff 8.9) mean -0.0366 sd 0.1021 lcb -0.0670 | taker n 9 (eff 9.0) mean -0.0231 sd 0.0153 lcb -0.0276
- kalshi/sports-central-run-under: n 19 (eff 16.9) mean +0.0300 sd 0.0625 lcb +0.0169 PROVEN; members 2 (2 living), real stake $20.54
-   practice n 19 (eff 19.0) mean +0.0208 sd 0.0708 lcb +0.0068 PROVEN | real n 5 (eff 5.0) mean +0.0624 sd 0.0361 lcb +0.0472 | maker n 0 | taker n 19 (eff 16.9) mean +0.0300 sd 0.0625 lcb +0.0169 PROVEN
- kalshi/crypto-15m-lab-0492e4: n 18 (eff 18.0) mean -0.0006 sd 0.0120 lcb -0.0030; members 1 (0 living), real stake $0.00
-   practice n 18 (eff 18.0) mean -0.0006 sd 0.0120 lcb -0.0030 | real n 0 | maker n 0 | taker n 18 (eff 18.0) mean -0.0006 sd 0.0120 lcb -0.0030
- alpaca/megacaps-expanding-range-chas: n 17 (eff 17.0) mean -0.0000 sd 0.0003 lcb -0.0001; members 1 (0 living), real stake $0.00
-   practice n 17 (eff 17.0) mean -0.0000 sd 0.0003 lcb -0.0001 | real n 0 | maker n 0 | taker n 17 (eff 17.0) mean -0.0000 sd 0.0003 lcb -0.0001
- alpaca/options-pullback: n 17 (eff 17.0) mean -0.0158 sd 0.0301 lcb -0.0222; members 15 (7 living), real stake $0.00
-   practice n 17 (eff 17.0) mean -0.0158 sd 0.0301 lcb -0.0222 | real n 0 | maker n 0 | taker n 17 (eff 17.0) mean -0.0158 sd 0.0301 lcb -0.0222
- kalshi/weather-favorites: n 16 (eff 14.2) mean +0.0050 sd 0.0073 lcb +0.0033 PROVEN; members 25 (11 living), real stake $66.56
-   practice n 13 (eff 13.0) mean +0.0000 sd 0.0075 lcb -0.0018 | real n 5 (eff 5.0) mean +0.0159 sd 0.0057 lcb +0.0135 | maker n 16 (eff 14.2) mean +0.0050 sd 0.0073 lcb +0.0033 PROVEN | taker n 0
- kalshi/sports-central-under-demand: n 15 (eff 15.0) mean +0.0033 sd 0.0612 lcb -0.0104; members 3 (1 living), real stake $0.00
-   practice n 15 (eff 15.0) mean +0.0033 sd 0.0612 lcb -0.0104 | real n 0 | maker n 4 (eff 4.0) mean -0.0113 sd 0.0328 lcb -0.0273 | taker n 11 (eff 11.0) mean +0.0087 sd 0.0693 lcb -0.0097
- alpaca/equity-trend: n 14 (eff 14.0) mean -0.0005 sd 0.0003 lcb -0.0005; members 23 (7 living), real stake $0.00
-   practice n 14 (eff 14.0) mean -0.0005 sd 0.0003 lcb -0.0005 | real n 0 | maker n 0 | taker n 14 (eff 14.0) mean -0.0005 sd 0.0003 lcb -0.0005
- kalshi/crypto-strikes-vol-shock-upside: n 12 (eff 10.7) mean -0.0197 sd 0.1482 lcb -0.0596; members 3 (2 living), real stake $30.00
-   practice n 8 (eff 8.0) mean -0.0319 sd 0.1627 lcb -0.0835 | real n 5 (eff 5.0) mean -0.0124 sd 0.1392 lcb -0.0710 | maker n 12 (eff 10.7) mean -0.0197 sd 0.1482 lcb -0.0596 | taker n 0
- kalshi/crypto-strikes-lab-955dae: n 11 (eff 9.8) mean +0.0214 sd 0.0192 lcb +0.0160 PROVEN; members 1 (1 living), real stake $30.00
-   practice n 6 (eff 6.0) mean +0.0044 sd 0.0014 lcb +0.0039 | real n 5 (eff 5.0) mean +0.0315 sd 0.0179 lcb +0.0240 | maker n 11 (eff 9.8) mean +0.0214 sd 0.0192 lcb +0.0160 PROVEN | taker n 0
- alpaca/crypto-reversion: n 8 (eff 8.0) mean -0.0004 sd 0.0008 lcb -0.0007; members 42 (1 living), real stake $0.00
-   practice n 8 (eff 8.0) mean -0.0004 sd 0.0008 lcb -0.0007 | real n 0 | maker n 0 | taker n 8 (eff 8.0) mean -0.0004 sd 0.0008 lcb -0.0007
- kalshi/crypto-strikes-downside-insurance-s: n 8 (eff 8.0) mean -0.0680 sd 0.1297 lcb -0.1091; members 1 (0 living), real stake $0.00
-   practice n 8 (eff 8.0) mean -0.0680 sd 0.1297 lcb -0.1091 | real n 0 | maker n 8 (eff 8.0) mean -0.0680 sd 0.1297 lcb -0.1091 | taker n 0
- kalshi/prices-favorites: n 7 (eff 6.2) mean +0.0007 sd 0.0185 lcb -0.0061; members 29 (6 living), real stake $27.48
-   practice n 7 (eff 7.0) mean -0.0034 sd 0.0183 lcb -0.0097 | real n 2 (eff 2.0) mean +0.0208 sd 0.0126 lcb +0.0086 | maker n 7 (eff 6.2) mean +0.0007 sd 0.0185 lcb -0.0061 | taker n 0
- alpaca/crypto-alts-trend: n 6 (eff 6.0) mean +0.0014 sd 0.0114 lcb -0.0029; members 2 (0 living), real stake $0.00
-   practice n 6 (eff 6.0) mean +0.0014 sd 0.0114 lcb -0.0029 | real n 0 | maker n 0 | taker n 6 (eff 6.0) mean +0.0014 sd 0.0114 lcb -0.0029
- alpaca/megacaps-chip-demand-relay: n 6 (eff 6.0) mean +0.0002 sd 0.0005 lcb +0.0001; members 1 (1 living), real stake $0.00
-   practice n 6 (eff 6.0) mean +0.0002 sd 0.0005 lcb +0.0001 | real n 0 | maker n 0 | taker n 6 (eff 6.0) mean +0.0002 sd 0.0005 lcb +0.0001
- alpaca/megacaps-semiconductor-catchu: n 6 (eff 6.0) mean -0.0002 sd 0.0011 lcb -0.0006; members 3 (3 living), real stake $0.00
-   practice n 6 (eff 6.0) mean -0.0002 sd 0.0011 lcb -0.0006 | real n 0 | maker n 0 | taker n 6 (eff 6.0) mean -0.0002 sd 0.0011 lcb -0.0006
- kalshi/sports-central-over-under: n 6 (eff 5.4) mean +0.1313 sd 0.1835 lcb +0.0582; members 1 (1 living), real stake $21.50
-   practice n 6 (eff 6.0) mean +0.0656 sd 0.1251 lcb +0.0186 | real n 1 (eff 1.0) mean +0.4341 sd - lcb - | maker n 0 | taker n 6 (eff 5.4) mean +0.1313 sd 0.1835 lcb +0.0582
- alpaca/equity-overnight: n 5 (eff 5.0) mean -0.0002 sd 0.0004 lcb -0.0004; members 3 (1 living), real stake $0.00
-   practice n 5 (eff 5.0) mean -0.0002 sd 0.0004 lcb -0.0004 | real n 0 | maker n 0 | taker n 5 (eff 5.0) mean -0.0002 sd 0.0004 lcb -0.0004
- kalshi/sports-props-favorites: n 5 (eff 5.0) mean -0.0282 sd 0.0279 lcb -0.0399; members 37 (4 living), real stake $0.00
-   practice n 5 (eff 5.0) mean -0.0282 sd 0.0279 lcb -0.0399 | real n 0 | maker n 5 (eff 5.0) mean -0.0282 sd 0.0279 lcb -0.0399 | taker n 0
- alpaca/crypto-alts-funded-spot-hedge: n 4 (eff 4.0) mean -0.0089 sd 0.0122 lcb -0.0148; members 1 (0 living), real stake $0.00
-   practice n 4 (eff 4.0) mean -0.0089 sd 0.0122 lcb -0.0148 | real n 0 | maker n 0 | taker n 4 (eff 4.0) mean -0.0089 sd 0.0122 lcb -0.0148
- alpaca/crypto-alts-lab-e60292: n 4 (eff 4.0) mean +0.0005 sd 0.0000 lcb +0.0004; members 2 (2 living), real stake $0.00
-   practice n 4 (eff 4.0) mean +0.0005 sd 0.0000 lcb +0.0004 | real n 0 | maker n 0 | taker n 4 (eff 4.0) mean +0.0005 sd 0.0000 lcb +0.0004
- alpaca/crypto-majors-absorbed-buy-program: n 4 (eff 4.0) mean -0.0045 sd 0.0045 lcb -0.0067; members 1 (0 living), real stake $0.00
-   practice n 4 (eff 4.0) mean -0.0045 sd 0.0045 lcb -0.0067 | real n 0 | maker n 0 | taker n 4 (eff 4.0) mean -0.0045 sd 0.0045 lcb -0.0067
- alpaca/index-etfs-real-asset-rotation: n 4 (eff 4.0) mean -0.0001 sd 0.0002 lcb -0.0002; members 1 (1 living), real stake $0.00
-   practice n 4 (eff 4.0) mean -0.0001 sd 0.0002 lcb -0.0002 | real n 0 | maker n 0 | taker n 4 (eff 4.0) mean -0.0001 sd 0.0002 lcb -0.0002
- alpaca/megacaps-lab-d7fe38: n 4 (eff 4.0) mean +0.0007 sd 0.0010 lcb +0.0002; members 2 (2 living), real stake $0.00
-   practice n 4 (eff 4.0) mean +0.0007 sd 0.0010 lcb +0.0002 | real n 0 | maker n 0 | taker n 4 (eff 4.0) mean +0.0007 sd 0.0010 lcb +0.0002
- kalshi/crypto-strikes-lab-1b9d16: n 4 (eff 4.0) mean +0.0027 sd 0.0013 lcb +0.0021; members 1 (1 living), real stake $0.00
-   practice n 4 (eff 4.0) mean +0.0027 sd 0.0013 lcb +0.0021 | real n 0 | maker n 4 (eff 4.0) mean +0.0027 sd 0.0013 lcb +0.0021 | taker n 0
- alpaca/crypto-alts-alt-basket-catchup: n 3 (eff 3.0) mean -0.0015 sd 0.0017 lcb -0.0025; members 1 (0 living), real stake $0.00
-   practice n 3 (eff 3.0) mean -0.0015 sd 0.0017 lcb -0.0025 | real n 0 | maker n 0 | taker n 3 (eff 3.0) mean -0.0015 sd 0.0017 lcb -0.0025
- alpaca/megacaps-quiet-vwap-reclaim: n 3 (eff 3.0) mean +0.0008 sd 0.0009 lcb +0.0003; members 5 (5 living), real stake $0.00
-   practice n 3 (eff 3.0) mean +0.0008 sd 0.0009 lcb +0.0003 | real n 0 | maker n 0 | taker n 3 (eff 3.0) mean +0.0008 sd 0.0009 lcb +0.0003
- alpaca/crypto-majors-funding-short-relief: n 2 (eff 2.0) mean -0.0070 sd 0.0005 lcb -0.0075; members 1 (0 living), real stake $0.00
-   practice n 2 (eff 2.0) mean -0.0070 sd 0.0005 lcb -0.0075 | real n 0 | maker n 0 | taker n 2 (eff 2.0) mean -0.0070 sd 0.0005 lcb -0.0075
- kalshi/crypto-15m-lab-a69fa4: n 2 (eff 2.0) mean -0.0581 sd 0.0046 lcb -0.0626; members 1 (1 living), real stake $0.00
-   practice n 2 (eff 2.0) mean -0.0581 sd 0.0046 lcb -0.0626 | real n 0 | maker n 0 | taker n 2 (eff 2.0) mean -0.0581 sd 0.0046 lcb -0.0626
- kalshi/crypto-15m-prior-window-fade: n 2 (eff 2.0) mean -0.0295 sd 0.0455 lcb -0.0738; members 1 (0 living), real stake $0.00
-   practice n 2 (eff 2.0) mean -0.0295 sd 0.0455 lcb -0.0738 | real n 0 | maker n 2 (eff 2.0) mean -0.0295 sd 0.0455 lcb -0.0738 | taker n 0
- alpaca/crypto-majors-lab-8899c2: n 1 (eff 1.0) mean -0.0012 sd - lcb -; members 2 (2 living), real stake $0.00
-   practice n 1 (eff 1.0) mean -0.0012 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0012 sd - lcb -
- alpaca/crypto-majors-upside-gamma-hedging: n 1 (eff 1.0) mean -0.0021 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice n 1 (eff 1.0) mean -0.0021 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0021 sd - lcb -
- alpaca/crypto-majors-vol-risk-rebuild: n 1 (eff 1.0) mean -0.0004 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice n 1 (eff 1.0) mean -0.0004 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0004 sd - lcb -
- alpaca/index-etfs-duration-to-assets: n 1 (eff 1.0) mean -0.0002 sd - lcb -; members 1 (1 living), real stake $0.00
-   practice n 1 (eff 1.0) mean -0.0002 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0002 sd - lcb -
- alpaca/index-etfs-morning-range-stops: n 1 (eff 1.0) mean -0.0002 sd - lcb -; members 2 (2 living), real stake $0.00
-   practice n 1 (eff 1.0) mean -0.0002 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean -0.0002 sd - lcb -
- alpaca/megacaps-reversion: n 1 (eff 1.0) mean +0.0000 sd - lcb -; members 38 (1 living), real stake $0.00
-   practice n 1 (eff 1.0) mean +0.0000 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean +0.0000 sd - lcb -
- alpaca/options-breakout: n 1 (eff 1.0) mean +0.0050 sd - lcb -; members 4 (0 living), real stake $0.00
-   practice n 1 (eff 1.0) mean +0.0050 sd - lcb - | real n 0 | maker n 0 | taker n 1 (eff 1.0) mean +0.0050 sd - lcb -
- kalshi/attention-favorites: n 1 (eff 1.0) mean +0.0055 sd - lcb -; members 32 (0 living), real stake $0.00
-   practice n 1 (eff 1.0) mean +0.0055 sd - lcb - | real n 0 | maker n 1 (eff 1.0) mean +0.0055 sd - lcb - | taker n 0
- kalshi/crypto-15m-sol-beta-catchup: n 1 (eff 1.0) mean -0.1143 sd - lcb -; members 1 (0 living), real stake $0.00
-   practice n 1 (eff 1.0) mean -0.1143 sd - lcb - | real n 0 | maker n 1 (eff 1.0) mean -0.1143 sd - lcb - | taker n 0

## the weather favourites' capacity [weather_capacity]
- capacity $7.93/day = 26.94 markets bid a day (117 over 4.34 days) x fill rate 0.6 (real, bids <=$12, median $9.60) x $0.49 a settlement (real, n 12); real seats earn $1.36/day now
- settlements a day over 4.34 days: {'real': 2.76, 'all': 16.58, 'real_independent': 1.15}; practice profit a settlement -$0.24
- real bids <=$12: 18 of 30 markets filled (0.6), 22 of 38 bids
- practice bids <=$12: 53 of 109 markets filled (0.4862), 104 of 293 bids
