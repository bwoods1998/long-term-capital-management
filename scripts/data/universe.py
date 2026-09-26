#!/usr/bin/env python3
"""Choose the Gym's universe from ThetaData EOD for 2024 (run ON the data box, one ThetaData slot).

    universe.py [--screen-days 6] [--eod-days 12] [--candidates 80] [--names 20] [--slots 1]

1. Screen: on `--screen-days` trading days spread over 2024, list every contract that TRADED with
   0-7 days to expiry, market-wide (`option_list_contracts('trade', day, max_dte=7)`), and count
   them per root. The roots with the most (index roots, the core five and adjusted roots excluded)
   become the candidates.
2. Measure: on `--eod-days` days of 2024 (one a month), each candidate's EOD report for every
   listed contract gives the day's option volume (all contracts) and, for the contracts within 0-7
   days to expiry and within three strikes of the money (the money found by put-call parity: the
   strike where the call and put mids are closest), the closing quoted spread (ask - bid) relative
   to the mid, and in dollars.
3. Rank: by mean daily option volume (1 = most) and by the median relative spread (1 = tightest)
   among candidates that had 0-7 DTE contracts on at least 10 of the days; score = the sum of the
   two ranks; the best `--names` by score (ties by volume) join the core five.

Writes /data/work/universe.json: {"core", "names", "roots", "numbers", "method", "at"}. Only 2024
days are read; nothing from Validation, the holdout or later.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import storelib as sl  # noqa: E402

INDEX_ROOTS = {"SPX", "SPXW", "SPXPM", "XSP", "NDX", "NDXP", "XND", "RUT", "RUTW", "MRUT", "VIX", "VIXW", "DJX",
               "OEX", "XEO", "NANOS", "MXEA", "MXEF", "XSPAM"}
YEAR = 2024


def spread_days(calendar: sl.Calendar, count: int, *, weekday: int = 2) -> list[dt.date]:
    """`count` trading days spread over the year: the first `weekday` on or after the 10th of evenly
    spaced months (a mid-month mid-week day avoids monthly-expiry Fridays and month ends)."""
    months = [1 + round(i * 12 / count) for i in range(count)] if count < 12 else list(range(1, 13))
    out = []
    for month in sorted(set(min(12, m) for m in months)):
        day = dt.date(YEAR, month, 10)
        while day.weekday() != weekday or not calendar.is_trading(day):
            day += dt.timedelta(days=1)
        out.append(day)
    return out


def eligible(root: str, core: Sequence[str]) -> bool:
    return root.isalpha() and root not in INDEX_ROOTS and root not in core


def atm_strike(rows: Sequence[dict[str, Any]]) -> float | None:
    """The strike where the call and put mids are closest (put-call parity), from one expiry's rows."""
    calls, puts = {}, {}
    for row in rows:
        bid, ask = row.get("bid"), row.get("ask")
        if bid is None or ask is None or bid != bid or ask != ask or ask <= 0 or bid < 0 or bid > ask:
            continue
        mid = (bid + ask) / 2
        (calls if str(row["right"]).upper().startswith("C") else puts)[float(row["strike"])] = mid
    both = [k for k in calls if k in puts]
    if not both:
        return None
    return min(both, key=lambda k: abs(calls[k] - puts[k]))


def measure_day(rows: Sequence[dict[str, Any]], day: dt.date, *, near: int = 3, max_dte: int = 7) -> dict[str, Any]:
    """One root-day's EOD rows -> volume and the near-the-money 0-7 DTE closing spreads."""
    volume = sum(int(r.get("volume") or 0) for r in rows)
    by_expiry: dict[dt.date, list[dict[str, Any]]] = {}
    for row in rows:
        expiry = sl.as_date(row["expiration"])
        if 0 <= (expiry - day).days <= max_dte:
            by_expiry.setdefault(expiry, []).append(row)
    rel, absolute = [], []
    for expiry, group in by_expiry.items():
        atm = atm_strike(group)
        if atm is None:
            continue
        strikes = sorted({float(r["strike"]) for r in group}, key=lambda k: (abs(k - atm), k))[: 2 * near + 1]
        for row in group:
            if float(row["strike"]) not in strikes:
                continue
            bid, ask = row.get("bid"), row.get("ask")
            if bid is None or ask is None or bid != bid or ask != ask or ask <= 0 or bid <= 0 or bid > ask:
                continue
            mid = (bid + ask) / 2
            rel.append((ask - bid) / mid)
            absolute.append(ask - bid)
    return {"volume": volume, "near_expiries": len(by_expiry), "rel": rel, "abs": absolute}


def rank(numbers: dict[str, dict[str, Any]], *, names: int, min_days: int) -> list[str]:
    pool = {r: n for r, n in numbers.items() if n["days_with_near_expiry"] >= min_days and n["median_rel_spread"] is not None}
    by_volume = sorted(pool, key=lambda r: -pool[r]["mean_daily_volume"])
    by_spread = sorted(pool, key=lambda r: (pool[r]["median_rel_spread"], -pool[r]["mean_daily_volume"]))
    for i, root in enumerate(by_volume):
        pool[root]["volume_rank"] = i + 1
    for i, root in enumerate(by_spread):
        pool[root]["spread_rank"] = i + 1
    for root in pool:
        pool[root]["score"] = pool[root]["volume_rank"] + pool[root]["spread_rank"]
    ordered = sorted(pool, key=lambda r: (pool[r]["score"], pool[r]["volume_rank"]))
    return ordered[:names]


def main(argv: Sequence[str] | None = None) -> int:
    import backfill as bf

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--screen-days", type=int, default=6)
    parser.add_argument("--eod-days", type=int, default=12)
    parser.add_argument("--candidates", type=int, default=80)
    parser.add_argument("--names", type=int, default=20)
    parser.add_argument("--slots", type=int, default=4, help="ThetaData allows one session per account: stop the backfill first")
    parser.add_argument("--min-days", type=int, default=10)
    parser.add_argument("--out", default=f"{sl.WORK_ROOT}/universe.json")
    args = parser.parse_args(argv)
    started = time.time()
    theta = bf.Theta(bf.open_client, bf.Limiter(args.slots))
    store = bf.Store()
    calendar = store.calendar(theta)
    core = list(sl.CORE_FIVE)

    counts: dict[str, list[int]] = {}
    screen = spread_days(calendar, args.screen_days)
    for day in screen:
        frame = theta.call("option_list_contracts", "trade", day, None, max_dte=7)
        per_root: dict[str, int] = {}
        for root in (frame["symbol"].to_list() if frame is not None else []):
            per_root[root] = per_root.get(root, 0) + 1
        for root, n in per_root.items():
            counts.setdefault(root, [0] * len(screen))[screen.index(day)] = n
        print(f"screen {day}: {sum(per_root.values())} traded 0-7 DTE contracts across {len(per_root)} roots", flush=True)
    screened = sorted((r for r in counts if eligible(r, core)), key=lambda r: -sum(counts[r]))[: args.candidates]

    measure = spread_days(calendar, args.eod_days)
    from concurrent.futures import ThreadPoolExecutor

    def eod(pair: tuple[str, dt.date]) -> tuple[str, dt.date, dict[str, Any] | None]:
        root, day = pair
        frame = theta.call("option_history_eod", day, day, root, "*")
        return root, day, (measure_day(frame.to_dicts(), day) if frame is not None else None)

    with ThreadPoolExecutor(max_workers=max(1, args.slots)) as pool:
        results = list(pool.map(eod, [(root, day) for root in screened for day in measure]))
    measured: dict[str, list[dict[str, Any]]] = {}
    for root, day, got in results:
        if got is not None:
            measured.setdefault(root, []).append(got)
    numbers: dict[str, dict[str, Any]] = {}
    for i, root in enumerate(screened):
        volumes, rel, absolute, near_days = [], [], [], 0
        for got in measured.get(root, []):
            volumes.append(got["volume"])
            rel.extend(got["rel"])
            absolute.extend(got["abs"])
            near_days += 1 if got["near_expiries"] else 0
        numbers[root] = {
            "screen_mean_traded_contracts_0_7dte": round(sum(counts[root]) / len(screen), 1),
            "mean_daily_volume": round(sum(volumes) / len(measure), 1) if measure else 0.0,
            "days_with_near_expiry": near_days,
            "median_rel_spread": round(statistics.median(rel), 5) if rel else None,
            "median_abs_spread": round(statistics.median(absolute), 4) if absolute else None,
            "spread_samples": len(rel),
        }
        print(f"[{i + 1}/{len(screened)}] {root}: {numbers[root]}", flush=True)
    names = rank(numbers, names=args.names, min_days=args.min_days)
    out = {
        "at": sl.utc_now(), "core": core, "names": names, "roots": core + names,
        "screen_days": [d.isoformat() for d in screen], "eod_days": [d.isoformat() for d in measure],
        "numbers": numbers, "seconds": round(time.time() - started, 1), "requests": theta.requests,
        "method": ("screen: count of contracts traded with 0-7 DTE per root on the screen days (index roots, the core "
                   "five and roots with digits excluded), top candidates; measure: EOD of every listed contract on the "
                   "eod days -> mean daily option volume and the median closing (ask-bid)/mid of 0-7 DTE contracts "
                   "within 3 strikes of the parity ATM; rank: volume rank + spread rank among candidates with 0-7 DTE "
                   f"contracts on >= {args.min_days} eod days; best {args.names} by score, ties by volume"),
    }
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({"names": names, "roots": core + names, "seconds": out["seconds"], "requests": theta.requests}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
