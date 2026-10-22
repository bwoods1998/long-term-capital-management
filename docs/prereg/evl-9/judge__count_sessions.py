"""count_sessions.py (EVL-9 judge): NYSE session counts for the warm-start windows, from the repo's own calendar
(league.equity.store.nyse_sessions on rel/1019g). Calendar only: no price, bar or outcome."""
import datetime as dt, sys, json
sys.path.insert(0, "/dev/shm/warm-judge/wt")
from league.equity.store import nyse_sessions
def n(a, b):
    s = nyse_sessions(dt.date.fromisoformat(a), dt.date.fromisoformat(b))
    return len(s), sum(1 for _, e in s if e)
out = {}
for k, (a, b) in {"O1_2022-01-03..2026-10-16": ("2022-01-03", "2026-10-16"),
                  "ON_2022-01-03..2026-10-15": ("2022-01-03", "2026-10-15"),
                  "lane_2026-10-19..2026-10-22": ("2026-10-19", "2026-10-22"),
                  "lookback_2021-11-01..2021-12-31": ("2021-11-01", "2021-12-31")}.items():
    out[k] = n(a, b)
for y in range(2022, 2027):
    out[f"year_{y}"] = n(f"{y}-01-01", f"{y}-12-31" if y < 2026 else "2026-10-16")
print(json.dumps(out, indent=1))
