#!/usr/bin/env python3
"""fetch_budget9.py: OUTCOME-FREE request and row budget of PREREG-EVL-9's history window (counts only).

Reads only the scout's count files (evl9/scout/*.out.json: filings counted per year, no price) and the repo's NYSE
calendar (league.equity.store.nyse_sessions, code only). No market data, no return, no price is read.

Window (this lens's data spec): entry sessions 2022-01-03 .. 2026-10-15; metadata lookbacks from 2021-01-01.
Rates: SEC 6.67 requests/s (the House's MIN_INTERVAL 0.15 s); Alpaca 100 requests/min (half the Basic plan's 200,
leaving the House the rest).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path.home() / "Work" / "long-term-capital-management"
sys.path.insert(0, str(REPO))
from league.equity.store import nyse_sessions  # noqa: E402

SCOUT = Path(__file__).resolve().parent.parent / "scout"
FIRST, LAST = dt.date(2022, 1, 3), dt.date(2026, 10, 15)
SEC_RPS = 1 / 0.15
ALP_RPM = 100.0


def main() -> None:
    sess = nyse_sessions(FIRST, LAST)
    days = (LAST - dt.date(2022, 1, 1)).days + 1
    sub = json.loads((SCOUT / "count_submissions.out.json").read_text())["by_year"]
    lst = json.loads((SCOUT / "count_listed_events.out.json").read_text())
    fb = json.loads((SCOUT / "fetch_budget.out.json").read_text())["inputs"]
    years = [str(y) for y in range(2021, 2027)]
    k8 = {y: sub[y]["8-K"] for y in years if y in sub}
    f4 = {y: sub[y]["4"] for y in years if y in sub}
    k8_all = sum(sub[str(y)]["8-K"] for y in range(2016, 2027))
    f4_all = sum(sub[str(y)]["4"] for y in range(2016, 2027))
    share_8k = sum(k8.values()) / k8_all
    share_f4 = sum(f4.values()) / f4_all
    atom_8k = fb["atom_8k_pages"] * share_8k
    atom_f4 = fb["atom_f4_pages"] * share_f4
    out = {
        "window": {"first_session": FIRST.isoformat(), "last_session": LAST.isoformat(), "sessions": len(sess),
                   "calendar_days_from_2022_01_01": days},
        "sec": {"8k_by_year_2021_2026": k8, "form4_by_year_2021_2026": f4,
                "share_of_2016_2026_8k": round(share_8k, 3), "share_of_2016_2026_form4": round(share_f4, 3),
                "atom_pages_8k_scaled": round(atom_8k), "atom_pages_f4_scaled": round(atom_f4),
                "atom_hours_at_6.67rps": round((atom_8k + atom_f4) / SEC_RPS / 3600, 2),
                "form345_quarters_2019q1_2026q3": 31, "submissions_zip_requests": 1,
                "note": "Atom pages scaled by the 2021-2026 share of filings (an approximation: paging stops at 2021-01-01)"},
        "news": {},
        "bars_1day": {},
        "min1_on": {},
        "rows": {},
    }
    for per_day in (130, 500, 1500, 3000):
        req = days * per_day / 50.0
        out["news"][f"{per_day}_per_day"] = {"requests": round(req), "hours_at_100rpm": round(req / ALP_RPM / 60, 2),
                                             "hours_at_200rpm": round(req / 200.0 / 60, 2)}
    # 1Day bars: point-in-time symbols over the window (scout's 12,590 over 2016-2026 is an upper bound)
    syms = fb["pit_symbols"]
    ndays = len(nyse_sessions(dt.date(2021, 11, 1), LAST))     # 2 months of lookback before the first session
    pages_per_req = -(-(200 * ndays) // 10000)
    req = -(-syms // 200) * pages_per_req * 2                    # raw and split
    ended_alone = syms * 2                                       # upper bound: every spell fetched alone, raw + split
    out["bars_1day"] = {"pit_symbols_upper": syms, "sessions_fetched": ndays, "pages_per_200_symbols": pages_per_req,
                        "batched_requests": req, "batched_hours": round(req / ALP_RPM / 60, 2),
                        "ended_spells_alone_upper_requests": ended_alone,
                        "ended_spells_alone_upper_hours": round(ended_alone / ALP_RPM / 60, 2)}
    # 1Min marks for the ON pool's candidates (SPEED-FACTS: about 420-850 a session; 850 used as the upper bound)
    for cands in (420, 850):
        batches = -(-cands // 100)                               # run.py MARK_BATCH 100
        req = len(sess) * batches * 2                            # the 09:30 minute and 15:00-15:30
        out["min1_on"][f"{cands}_candidates"] = {"requests": req, "hours_at_100rpm": round(req / ALP_RPM / 60, 2)}
    for label, lo, hi in (("O1", 340, 620), ("ON", 420, 850)):
        out["rows"][label] = {"per_session_lo_hi": [lo, hi], "rows_lo": lo * len(sess), "rows_hi": hi * len(sess)}
    out["listed_purchase_filings_by_year"] = {k: v for k, v in (lst.get("by_year") or {}).items()} if isinstance(
        lst.get("by_year"), dict) else None
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
