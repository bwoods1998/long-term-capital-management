| day shape | lag | phi 0.10: drift 0 / 10 / 20 bp | phi 0.15: drift 0 / 10 / 20 bp | phi 0.20: drift 0 / 10 / 20 bp |
|---|---|---|---|---|
| crash days, normal body | 1 | 0.057 / 0.056 / 0.056 | 0.061 / 0.069 / 0.057 | 0.063 / 0.082 / 0.078 |
| crash days, normal body | 2 | 0.056 / 0.061 / 0.060 | 0.052 / 0.060 / 0.072 | 0.062 / 0.071 / 0.076 |
| crash days, t(3) body | 1 | 0.054 / 0.044 / 0.082 | 0.050 / 0.062 / 0.058 | 0.078 / 0.082 / 0.068 |
| crash days, t(3) body | 2 | 0.065 / 0.054 / 0.054 | 0.056 / 0.062 / 0.096 (fresh 0.079) | 0.050 / 0.076 / 0.064 |
| clustered crash days | 1 | 0.078 / 0.046 / 0.058 | 0.080 / 0.056 / 0.086 | 0.080 / 0.062 / 0.080 |
| clustered crash days | 2 | 0.058 / 0.086 / 0.070 | 0.094 (fresh 0.060) / 0.066 / 0.062 | 0.088 / 0.082 / 0.070 |
| t(3)-body clustered crash days | 1 | 0.082 / 0.074 / 0.088 | 0.072 / 0.058 / 0.072 | 0.072 / 0.080 / 0.098 (fresh 0.087) |
| t(3)-body clustered crash days | 2 | 0.084 / 0.076 / 0.080 | 0.070 / 0.056 / 0.068 | 0.070 / 0.070 / 0.096 (fresh 0.086) |

| varied from the corner (phi_day 0.20, 20 bp drift unless stated) | normal-body crash | t(3)-body crash | clustered crash | t(3)-body clustered crash |
|---|---|---|---|---|
| symmetric events, lag 1 | 0.060 | 0.070 | 0.068 | 0.080 |
| symmetric events, lag 2 | 0.060 | 0.076 | 0.066 | 0.084 |
| no issuer effect, lag 1 | 0.076 | 0.084 | 0.096 (fresh 0.084) | 0.072 |
| no issuer effect, lag 2 | 0.084 | 0.076 | 0.096 (fresh 0.073) | 0.076 |
| counts follow the day, lag 1 | 0.068 | 0.092 | 0.076 | 0.078 |
| counts follow the day, lag 2 | 0.062 | 0.060 | 0.066 | 0.094 (fresh 0.083) |
| counts follow the day, phi_day 0.15, lag 1 | 0.064 | 0.066 | 0.064 | 0.080 |
| counts follow the day, phi_day 0.15, lag 2 | 0.078 | 0.088 | 0.076 | 0.078 |
| pool 800, lag 1 | 0.074 | 0.056 | 0.080 | 0.080 |
| pool 800, lag 2 | 0.072 | 0.082 | 0.072 | 0.068 |
| rho_day 0.05, lag 1 | 0.068 | 0.100 (fresh 0.071) | 0.052 | 0.058 |
| rho_day 0.05, lag 2 | 0.060 | 0.048 | 0.066 | 0.052 |
| knife edge, ic 0.03, lag 1 | 0.058 | 0.066 | 0.058 | 0.048 |
| knife edge, ic 0.03, lag 2 | 0.048 | 0.050 | 0.050 | 0.070 |
| knife edge, ic 0.05, lag 1 | 0.024 | 0.048 | 0.054 | 0.058 |
| knife edge, ic 0.05, lag 2 | 0.046 | 0.050 | 0.054 | 0.048 |

- lag 1: symmetric t(3) days at the corner, phi_day 0.10 / 0.15 / 0.20: 0.050 / 0.040 / 0.044; BASE (symmetric days and events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect): 0.020; the base at phi_day 0.20: 0.032
- lag 2: symmetric t(3) days at the corner, phi_day 0.10 / 0.15 / 0.20: 0.040 / 0.062 / 0.044; BASE (symmetric days and events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect): 0.030; the base at phi_day 0.20: 0.026
- 146 cells; search maximum 0.100 (N1-crasht3-skew-rho05-phi20-dr20-tau1-n300-lag1-D57); median 0.066; programs a cell: 1,000 for grid cells 0-19, 500 for the rest
