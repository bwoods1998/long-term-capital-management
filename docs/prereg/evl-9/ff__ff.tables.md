## SEARCH (ff.search.jsonl, 200 programs a cell, seeds 861e6 +)

| history (t(3)-body clustered crash days, left-skewed events, rho_day 0.15, phi_day 0.20, a 20 bp drift, 1% issuer effects unless named) | EVL-WL-ON pool 300 | 600 | 800 | EVL-WL-O1 pool 300 | 450 | 600 |
|---|---|---|---|---|---|---|
| ADV leak: all prior weight on one event column | 0.115 | 0.120 | 0.070 | 0.110 | 0.045 | 0.055 |
| ADV lowvol: "low-volatility names win" (k 0.30) | 0.090 | 0.095 | 0.180 | 0.115 | 0.155 | 0.155 |
| ADV lowvol: "low-volatility names win" (k 0.30); no issuer effect | 0.095 | 0.100 | 0.100 | 0.090 | 0.085 | 0.070 |
| ADV rand: a strong random prior (k 0.60) | 0.085 | 0.035 | 0.035 | 0.040 | 0.050 | 0.050 |
| CHAR10: HD08 with a drift of 10 bp a unit along its own history direction | 0.070 | 0.095 | 0.115 | 0.085 | 0.075 | 0.110 |
| H0, noise history | 0.080 | 0.110 | 0.120 | 0.100 | 0.130 | 0.115 |
| H0, noise history; counts that follow the day | - | 0.130 | - | - | 0.100 | - |
| H0, noise history; crash days not clustered | - | 0.115 | - | - | 0.105 | - |
| H0, noise history; drift 0 bp | - | 0.110 | - | - | 0.095 | - |
| H0, noise history; drift 10 bp | - | 0.115 | - | - | 0.080 | - |
| H0, noise history; no issuer effect | 0.125 | 0.060 | 0.080 | 0.100 | 0.090 | 0.100 |
| HD05: a decayed history edge of 0.05 | 0.060 | 0.035 | 0.080 | 0.080 | 0.060 | 0.045 |
| HD08: a decayed history edge of 0.08 | 0.065 | 0.060 | 0.055 | 0.050 | 0.070 | 0.035 |
| N2, the knife edge, ic 0.05 | 0.065 | 0.075 | 0.055 | 0.090 | 0.070 | 0.060 |
| N2, the knife edge, ic 0.08 | 0.040 | 0.050 | 0.035 | 0.040 | 0.055 | 0.035 |
| TAUH: EVL-WL-ON's history carried the issuer slope through dmove | 0.095 | 0.105 | 0.100 | - | - | - |
| TAUS 0.5: history carried the issuers' own effects (rho_tau 0.5) through ln sig20, the SIC groups and g | 0.090 | 0.110 | 0.100 | 0.100 | 0.130 | 0.115 |
| COLD (PREREG-EVL-7's learner on this file's columns, no prior, no g) | 0.065 | 0.115 | 0.105 | 0.110 | 0.075 | 0.110 |

ON pool 300: warm cells 13, run 1 max 0.125 median 0.085; picks a session 2.7-8.0; picks' issuer effect +0.3 to +8.8 bp (1% cells); version within 120 sessions max 0.200
ON pool 600: warm cells 17, run 1 max 0.130 median 0.100; picks a session 5.5-8.0; picks' issuer effect -0.1 to +9.1 bp (1% cells); version within 120 sessions max 0.220
ON pool 800: warm cells 13, run 1 max 0.180 median 0.080; picks a session 6.4-8.0; picks' issuer effect +0.6 to +8.9 bp (1% cells); version within 120 sessions max 0.280
O1 pool 300: warm cells 12, run 1 max 0.115 median 0.090; picks a session 2.5-8.0; picks' issuer effect +0.5 to +7.4 bp (1% cells); version within 120 sessions max 0.190
O1 pool 450: warm cells 16, run 1 max 0.155 median 0.085; picks a session 4.2-8.0; picks' issuer effect +0.5 to +8.7 bp (1% cells); version within 120 sessions max 0.300
O1 pool 600: warm cells 12, run 1 max 0.155 median 0.070; picks a session 5.5-8.0; picks' issuer effect +0.5 to +8.7 bp (1% cells); version within 120 sessions max 0.235

## FRESH (ff.fresh1 + ff.fresh2)

| cell | learner, pool | fresh run 1 (SE, programs) | search run 1 (200) | version within 120 sessions | record's true mean a <= 0 / <= 10 bp at the pass | picks a session | picks' issuer effect (bp) |
|---|---|---|---|---|---|---|---|
| ADV lowvol: "low-volatility names win" (k 0.30) | O1, 600 | **0.1475** (0.0079, 2,000) | 0.155 | 0.255 | 0.0250 / 0.0410 | 7.9 | +6.9 |
| ADV lowvol: "low-volatility names win" (k 0.30) | ON, 800 | 0.1370 (0.0077, 2,000) | 0.180 | 0.251 | 0.0175 / 0.0330 | 7.9 | +7.8 |
| ADV lowvol: "low-volatility names win" (k 0.30) | O1, 450 | 0.1300 (0.0075, 2,000) | 0.155 | 0.234 | 0.0155 / 0.0375 | 7.8 | +6.1 |
| H0, noise history; counts that follow the day | ON, 600 | 0.1100 (0.0099, 1,000) | 0.130 | 0.199 | 0.0220 / 0.0330 | 6.5 | +4.4 |
| H0, noise history | O1, 450 | 0.1070 (0.0098, 1,000) | 0.130 | 0.190 | 0.0150 / 0.0360 | 5.0 | +5.0 |
| TAUS 0.5: history carried the issuers' own effects (rho_tau 0.5) through ln sig20, the SIC groups and g | O1, 450 | 0.1070 (0.0069, 2,000) | 0.130 | 0.205 | 0.0160 / 0.0340 | 7.4 | +7.9 |

## POWER (ff.power.jsonl)

| ic | history | EVL-WL-O1 (lag 1, pool 300): by 25 / 40 / 60 / 120 | edge 1-10 -> 51-60 | EVL-WL-ON (lag 2, pool 600): by 25 / 40 / 60 / 120 | edge 1-10 -> 51-60 |
|---|---|---|---|---|---|
| 0.03 | cold | 0.005 / 0.030 / 0.035 / 0.035 | -0.0 -> +2.6 | 0.015 / 0.015 / 0.015 / 0.015 | +1.0 -> +7.6 |
| 0.03 | warm, rho 1 | 0.040 / 0.065 / 0.065 / 0.065 | +17.1 -> +14.1 | 0.030 / 0.050 / 0.050 / 0.050 | +19.8 -> +17.2 |
| 0.03 | warm, rho 0.7 | 0.020 / 0.035 / 0.035 / 0.035 | +9.0 -> +9.6 | 0.015 / 0.040 / 0.040 / 0.040 | +12.1 -> +13.4 |
| 0.03 | warm, rho 0 | 0.015 / 0.025 / 0.025 / 0.025 | -4.9 -> +0.9 | 0.000 / 0.005 / 0.005 / 0.005 | -2.7 -> +4.9 |
| 0.05 | cold | 0.010 / 0.065 / 0.065 / 0.065 | +22.7 -> +28.0 | 0.030 / 0.060 / 0.065 / 0.065 | +27.1 -> +39.4 |
| 0.05 | warm, rho 1 | 0.150 / 0.190 / 0.190 / 0.190 | +49.8 -> +44.4 | 0.175 / 0.215 / 0.230 / 0.230 | +60.3 -> +53.5 |
| 0.05 | warm, rho 0.7 | 0.090 / 0.120 / 0.120 / 0.120 | +36.8 -> +36.6 | 0.150 / 0.190 / 0.190 / 0.190 | +46.0 -> +47.9 |
| 0.05 | warm, rho 0 | 0.020 / 0.030 / 0.030 / 0.030 | +6.8 -> +18.3 | 0.050 / 0.065 / 0.075 / 0.075 | +14.2 -> +33.2 |
| 0.08 | cold | 0.040 / 0.210 / 0.210 / 0.225 | +61.4 -> +73.6 | 0.160 / 0.275 / 0.305 / 0.320 | +72.3 -> +93.0 |
| 0.08 | warm, rho 1 | 0.305 / 0.420 / 0.440 / 0.440 | +95.6 -> +87.5 | 0.420 / 0.500 / 0.520 / 0.520 | +116.2 -> +107.1 |
| 0.08 | warm, rho 0.7 | 0.225 / 0.295 / 0.325 / 0.325 | +77.9 -> +77.0 | 0.340 / 0.445 / 0.485 / 0.485 | +94.3 -> +97.7 |
| 0.08 | warm, rho 0 | 0.065 / 0.105 / 0.105 / 0.105 | +28.9 -> +49.1 | 0.105 / 0.180 / 0.185 / 0.185 | +43.5 -> +74.9 |

O1-rho10-ic05-t3-sym-rho05-phi10-dr00-tau0-n300-lag1-SP05: by25/40/60/120 0.125/0.175/0.175/0.175 edge +49.7 -> +49.3
ON-cold-ic05-crasht3cl-skew-rho15-phi20-dr20-tau0-n600-lag2: by25/40/60/120 0.055/0.090/0.100/0.105 edge +18.2 -> +27.7
ON-rho07-ic05-crasht3cl-skew-rho15-phi20-dr20-tau0-n600-lag2: by25/40/60/120 0.100/0.155/0.160/0.160 edge +44.3 -> +38.0
ON-rho10-ic05-crasht3cl-skew-rho15-phi20-dr20-tau0-n600-lag2: by25/40/60/120 0.200/0.270/0.295/0.295 edge +56.7 -> +47.2
ON-rho10-ic05-t3-sym-rho05-phi10-dr00-tau0-n600-lag2-SP05: by25/40/60/120 0.130/0.165/0.175/0.175 edge +60.5 -> +59.1

## LIFE (ff.life.jsonl)

O1-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag1-T200: R 600 run1 0.1517 (se 0.0146) v120 0.267 cm<=0 0.0250 cm<=10 0.0450 ev/s 7.86 tau +7.3 uhz -0.56 guarded 106.2 | life3 0.3600 by60/120/200 0.152/0.267/0.360 runs 2.46 | run1 by60/120 0.152/0.152
ON-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n800-lag2-T200: R 600 run1 0.1417 (se 0.0142) v120 0.242 cm<=0 0.0217 cm<=10 0.0483 ev/s 7.89 tau +8.3 uhz -0.55 guarded 136.4 | life3 0.3400 by60/120/200 0.142/0.242/0.340 runs 2.48 | run1 by60/120 0.142/0.142

## COLDREF (ff.coldref.jsonl)

ON-cold-crasht3cl-skew-rho15-phi20-dr20-tau1-n800-lag2: R 600 run1 0.1033 (se 0.0124) v120 0.205 cm<=0 0.0183 cm<=10 0.0350 ev/s 7.82 tau +6.1 uhz 0.11 guarded 143.5
O1-cold-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag1: R 600 run1 0.0950 (se 0.0120) v120 0.195 cm<=0 0.0233 cm<=10 0.0367 ev/s 7.71 tau +4.2 uhz 0.09 guarded 108.7

## STRESS (ff.stress.jsonl)

ON-CHAR30-HD08-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2: R 200 run1 0.2000 (se 0.0283) v120 0.290 cm<=0 0.0100 cm<=10 0.0100 ev/s 7.80 tau +3.1 uhz 1.63 guarded 113.7
ON-H0-crash-skew-rho30-phi40-dr20-tau1-n600-lag2: R 200 run1 0.1700 (se 0.0266) v120 0.270 cm<=0 0.0450 cm<=10 0.0600 ev/s 7.01 tau +5.2 uhz -0.07 guarded 83.3
ON-H0-crasht3cl-skew-rho15-phi20-dr30-tau1-n600-lag2: R 200 run1 0.1550 (se 0.0256) v120 0.240 cm<=0 0.0100 cm<=10 0.0250 ev/s 6.16 tau +6.0 uhz -0.07 guarded 118.1
ON-H0-tauh-crasht3cl-skew-rho15-phi20-dr20-tau1all-n600-lag2: R 200 run1 0.1550 (se 0.0256) v120 0.260 cm<=0 0.0050 cm<=10 0.0050 ev/s 7.97 tau +24.1 uhz 0.48 guarded 119.2
O1-ADVlowvol60-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1: R 200 run1 0.1550 (se 0.0256) v120 0.295 cm<=0 0.0050 cm<=10 0.0350 ev/s 7.89 tau +6.3 uhz -0.57 guarded 85.9
ON-H0-crasht3cl-skew-rho15-phi20-dr20-tau1all-n600-lag2: R 200 run1 0.1500 (se 0.0252) v120 0.295 cm<=0 0.0050 cm<=10 0.0050 ev/s 7.40 tau +23.5 uhz 0.21 guarded 122.7
ON-H0-tauh-crasht3cl-skew-rho15-phi20-dr20-tau2-n600-lag2: R 200 run1 0.1400 (se 0.0245) v120 0.265 cm<=0 0.0000 cm<=10 0.0200 ev/s 7.89 tau +20.0 uhz 0.33 guarded 102.9
O1-H0-crasht3cl-skew-rho15-phi20-dr30-tau1-n450-lag1: R 200 run1 0.1400 (se 0.0245) v120 0.265 cm<=0 0.0300 cm<=10 0.0500 ev/s 5.04 tau +4.9 uhz -0.11 guarded 88.6
ON-H0-crasht3cl-skew-rho15-phi20-dr20-tau0-n600-lag2-sec20: R 200 run1 0.1350 (se 0.0242) v120 0.180 cm<=0 0.0200 cm<=10 0.0450 ev/s 6.02 tau +0.0 uhz -0.03 guarded 125.7
ON-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2-SP05: R 200 run1 0.1350 (se 0.0242) v120 0.250 cm<=0 0.0150 cm<=10 0.0350 ev/s 7.95 tau +8.2 uhz -0.59 guarded 118.5
O1-H0-crash-skew-rho30-phi40-dr20-tau1-n450-lag1: R 200 run1 0.1350 (se 0.0242) v120 0.210 cm<=0 0.0350 cm<=10 0.0600 ev/s 5.96 tau +3.6 uhz -0.04 guarded 65.0
ON-H0-crasht3cl-skew-rho15-phi25-dr20-tau1-n600-lag2: R 200 run1 0.1300 (se 0.0238) v120 0.230 cm<=0 0.0100 cm<=10 0.0200 ev/s 6.18 tau +5.3 uhz 0.00 guarded 117.4
ON-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2-LVSTY10: R 200 run1 0.1300 (se 0.0238) v120 0.250 cm<=0 0.0100 cm<=10 0.0200 ev/s 7.94 tau +6.6 uhz 0.85 guarded 108.9
O1-H0-crasht3cl-skew-rho15-phi25-dr20-tau1-n450-lag1: R 200 run1 0.1300 (se 0.0238) v120 0.250 cm<=0 0.0350 cm<=10 0.0450 ev/s 4.81 tau +4.6 uhz -0.08 guarded 88.8
ON-ADVlowvol60-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2: R 200 run1 0.1200 (se 0.0230) v120 0.190 cm<=0 0.0050 cm<=10 0.0150 ev/s 7.95 tau +6.5 uhz -0.59 guarded 107.2
O1-H0-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1-TAUS10a13: R 200 run1 0.1150 (se 0.0226) v120 0.210 cm<=0 0.0200 cm<=10 0.0300 ev/s 7.69 tau +12.7 uhz 0.24 guarded 85.6
ON-H0-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2-noguard: R 200 run1 0.1100 (se 0.0221) v120 0.160 cm<=0 0.0150 cm<=10 0.0400 ev/s 6.66 tau +2.4 uhz -0.14 guarded 0.0
O1-H0-crasht3cl-skew-rho15-phi20-dr20-tau0-n450-lag1-sec20: R 200 run1 0.1050 (se 0.0217) v120 0.185 cm<=0 0.0400 cm<=10 0.0650 ev/s 4.81 tau +0.0 uhz -0.07 guarded 95.1
O1-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1-SP05: R 200 run1 0.1050 (se 0.0217) v120 0.230 cm<=0 0.0250 cm<=10 0.0300 ev/s 7.90 tau +7.2 uhz -0.59 guarded 87.8
O1-CHAR30-HD08-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1: R 200 run1 0.1000 (se 0.0212) v120 0.245 cm<=0 0.0000 cm<=10 0.0150 ev/s 7.64 tau +1.2 uhz 1.64 guarded 90.0
ON-H0-tauh-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2-TAUS10a13: R 200 run1 0.0900 (se 0.0202) v120 0.210 cm<=0 0.0050 cm<=10 0.0300 ev/s 7.88 tau +14.6 uhz 0.24 guarded 120.1
ON-H0-crash-skew-rho30-phi10-dr20-tau1-n600-lag2: R 200 run1 0.0850 (se 0.0197) v120 0.150 cm<=0 0.0150 cm<=10 0.0250 ev/s 6.83 tau +4.6 uhz -0.10 guarded 82.1
ON-CHAR20-HD08-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2: R 200 run1 0.0850 (se 0.0197) v120 0.210 cm<=0 0.0050 cm<=10 0.0150 ev/s 7.80 tau +2.1 uhz 1.69 guarded 121.0
O1-H0-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1-noguard: R 200 run1 0.0850 (se 0.0197) v120 0.160 cm<=0 0.0300 cm<=10 0.0450 ev/s 5.59 tau +1.7 uhz -0.20 guarded 0.0
O1-H0-crash-skew-rho30-phi10-dr20-tau1-n450-lag1: R 200 run1 0.0750 (se 0.0186) v120 0.145 cm<=0 0.0200 cm<=10 0.0300 ev/s 5.57 tau +3.7 uhz -0.17 guarded 70.5
O1-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1-noguard: R 200 run1 0.0750 (se 0.0186) v120 0.145 cm<=0 0.0150 cm<=10 0.0300 ev/s 8.00 tau +1.0 uhz -0.67 guarded 0.0
O1-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1-LVSTY10: R 200 run1 0.0750 (se 0.0186) v120 0.155 cm<=0 0.0150 cm<=10 0.0150 ev/s 7.88 tau +5.7 uhz 0.91 guarded 85.0
ON-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2-noguard: R 200 run1 0.0700 (se 0.0180) v120 0.155 cm<=0 0.0200 cm<=10 0.0250 ev/s 8.00 tau +0.8 uhz -0.65 guarded 0.0
O1-CHAR20-HD08-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1: R 200 run1 0.0650 (se 0.0174) v120 0.115 cm<=0 0.0050 cm<=10 0.0100 ev/s 7.78 tau +0.9 uhz 1.77 guarded 90.4
