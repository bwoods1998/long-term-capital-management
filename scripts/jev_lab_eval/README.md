# Jev evaluations

Read-only, offline evaluations of Jev (TypeSafe `jev-1.13.0`) against the House's own production data.
Bulk extracts stay out of the repository; each script says where it reads and writes.

| Files | What | Result |
|---|---|---|
| `extract.py`, `evaluate.py`, `oracle.py`, `result.txt` | The Sept 20-22 semantic lab: do eight Jev features predict Kalshi midpoint moves? (Sept 22) | Moves at all, yes (AUC 0.61 -> 0.76); direction, no |
| `gate_replay.py` | The research gate replayed over Sept 19-22 sessions | `docs/design/2026-09-22-jev-sensor.md` section 2 |
| `j1/` | J1 (Sept 25): ablations on the same lab data; the served move model's fit (`fit_final.py` -> `league/jev_move_model.json`) and its pure-Python reference | `j1/result.txt`: a free category table explains most of Jev's lift; a free 23-feature model beats it (0.83 at 15 min) and Jev adds nothing on top |
| `move_markouts.py` | J1's economic check: Kalshi fills' 15-minute markouts by the move sensor's `move_p15` tercile at the fill (point in time) | read with the ship rule (`docs/runs/2026-09-25-jev-senses.md`) |
| `markouts.py` | Kalshi fills' 15 and 60-minute markouts from recorded snapshots (J1's adverse-selection baseline) | `docs/runs/2026-09-25-jev-senses.md` |
| `j2/` | J2 (Sept 25): can Jev pick the research sessions and Merton passes worth paying for? Thresholds on Sept 22-23, held out on Sept 24-25 | `j2/research_result.md`, `j2/merton_result.md`: no; free rules do better |
| `market_map.py` | J4 (Sept 25): every traded Kalshi series by settlement mechanics and pricing feed | `docs/design/2026-09-25-kalshi-market-map.md` |

Scripts that call Jev read the gateway token from the deploy checkout's `.env` at call time and never print or
store it; every answer is cached, so a re-run costs nothing. Scripts that read the House box run through a small
wrapper around `scripts.floor_box.client().exec` with sqlite opened read-only (`?mode=ro`).
