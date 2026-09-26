#!/usr/bin/env python3
"""Checks on the Gym store, and the store report for the scoreboard.

    check.py report                  underlying-days by window and root, the queue, rate and ETAs
                                     (standard library; reads the journal and progress file)
    check.py quality [--sample N] [--root R] [--window W]
                                     per-day file checks (polars): contracts and rows per contract
                                     within the session's minutes, no crossed/negative/no-offer quote
                                     kept, minutes inside the calendar's hours, the NBBO's expiries all
                                     listed that day and every listed 0-14 DTE expiry present
    check.py alpaca --quotes F       the laptop's recorded Alpaca OPRA quotes (F: export_alpaca's
                                     csv.gz) against the store's one-minute NBBO on the same contracts
                                     and minutes: the share within a tick, overall and for quotes taken
                                     in a minute's first seconds (where the minute row is the NBBO in
                                     force); holdout days, so this runs on the data box only

On the laptop: `python3 scripts/data/check.py export-alpaca` writes the csv.gz from
~/Work/.options-history/options_history.sqlite (read-only), and `box.py run -- check.py ...` runs
the rest on the data box. Numbers derived from the data stay on the box and in `.data/`.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import storelib as sl  # noqa: E402

PENNY_ALWAYS = {"SPY", "QQQ", "IWM"}


def tick(root: str, price: float) -> float:
    """The venue's minimum increment for a penny-class contract (SPY, QQQ, IWM: a penny always)."""
    if root in PENNY_ALWAYS or price < 3.0:
        return 0.01
    return 0.05


# ------------------------------------------------------------------------------ report
def report(work: Path = Path(sl.WORK_ROOT)) -> dict[str, Any]:
    journal = sl.Journal(work / "journal.jsonl")
    files = journal.files()
    days: dict[str, dict[str, int]] = {}
    size = 0
    kinds: dict[str, int] = {}
    for row in files.values():
        size += int(row.get("bytes") or 0)
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        if row["kind"] == "nbbo":
            cell = days.setdefault(row["window"], {})
            cell[row["root"]] = cell.get(row["root"], 0) + 1
    try:
        progress = json.loads((work / "progress.json").read_text())
    except (OSError, ValueError):
        progress = {}
    return {
        "at": sl.utc_now(),
        "underlying_days": {w: dict(sorted(c.items())) for w, c in sorted(days.items())},
        "underlying_days_total": {w: sum(c.values()) for w, c in sorted(days.items())},
        "files": kinds,
        "store_gib": round(size / 2**30, 2),
        "queue": progress.get("stages"),
        "eta_hours": progress.get("eta"),
        "tasks_per_hour": progress.get("tasks_per_hour"),
        "underlying_days_per_hour": progress.get("underlying_days_per_hour"),
        "progress_at": progress.get("at"),
        "last_error": progress.get("last_error"),
    }


def print_report(data: dict[str, Any]) -> None:
    print(f"store report at {data['at']} (progress {data.get('progress_at')})")
    print(f"  files {data['files']}  size {data['store_gib']} GiB")
    for window, cell in data["underlying_days"].items():
        print(f"  {window:<10} {data['underlying_days_total'][window]:>6} underlying-days  " +
              " ".join(f"{r}:{n}" for r, n in cell.items()))
    print(f"  rate: {data.get('underlying_days_per_hour')} underlying-days/h ({data.get('tasks_per_hour')} tasks/h)")
    for stage, row in (data.get("queue") or {}).items():
        eta = (data.get("eta_hours") or {}).get(stage, {})
        print(f"  stage {stage}: {row['done']}/{row['planned']} done ({row['empty']} empty, {row['failing']} failing); "
              f"all through it in {eta.get('hours_to_finish')} h -- {sl.STAGES.get(int(stage), '')}")
    if data.get("last_error"):
        print(f"  last error: {data['last_error']}")


# ------------------------------------------------------------------------------ quality
def quality(store_root: Path, work: Path, *, sample: int | None = None, root: str | None = None,
            window: str | None = None, seed: int = 7) -> dict[str, Any]:
    import polars as pl

    calendar = sl.Calendar.from_json(json.loads((work / "calendar.json").read_text())["exceptions"])
    journal = sl.Journal(work / "journal.jsonl")
    rows = [r for r in journal.files().values() if r["kind"] == "nbbo"
            and (root is None or r["root"] == root) and (window is None or r["window"] == window)]
    rows.sort(key=lambda r: (r["root"], r["date"]))
    if sample and len(rows) > sample:
        rows = random.Random(seed).sample(rows, sample)
    problems: list[dict[str, Any]] = []
    totals = {"days": 0, "rows": 0, "contracts": 0, "bad_quotes": 0, "outside_hours": 0, "over_minutes": 0,
              "unlisted_expiries": 0, "listed_missing": 0, "underlying_missing": 0, "checksum": 0}
    for record in rows:
        day = sl.as_date(record["date"])
        path = store_root / record["path"]
        digest, _ = sl.sha256_file(path)
        if digest != record["sha256"]:
            totals["checksum"] += 1
            problems.append({"path": record["path"], "problem": "sha256"})
        frame = pl.read_parquet(path)
        open_min, close_min = calendar.hours(day) or (0, 0)
        minutes = close_min - open_min + 1
        per = frame.group_by(["expiration", "strike", "right"]).len()
        bad = frame.filter((pl.col("bid") < 0) | (pl.col("ask") <= 0) | (pl.col("bid") > pl.col("ask"))
                           | pl.col("bid").is_nan() | pl.col("ask").is_nan()).height
        outside = frame.filter((pl.col("minute") < open_min) | (pl.col("minute") > close_min)).height
        over = per.filter(pl.col("len") > minutes).height
        expiries = set(frame["expiration"].unique().to_list())
        listed_path = work / "expiries" / record["root"] / f"{day.isoformat()}.json"
        listed = {dt.date.fromisoformat(x) for x in json.loads(listed_path.read_text())} if listed_path.exists() else set()
        unlisted = {e for e in expiries if e not in listed}
        near_listed = {e for e in listed if (e - day).days <= sl.MAX_DTE}
        missing = near_listed - expiries
        under = store_root / sl.rel_path("underlying", record["root"], day)
        totals["days"] += 1
        totals["rows"] += frame.height
        totals["contracts"] += per.height
        totals["bad_quotes"] += bad
        totals["outside_hours"] += outside
        totals["over_minutes"] += over
        totals["unlisted_expiries"] += len(unlisted)
        totals["listed_missing"] += len(missing)
        totals["underlying_missing"] += 0 if under.exists() else 1
        if bad or outside or over or unlisted or missing or not under.exists():
            problems.append({"path": record["path"], "bad_quotes": bad, "outside_hours": outside, "over_minutes": over,
                             "unlisted": sorted(str(e) for e in unlisted), "listed_missing": sorted(str(e) for e in missing),
                             "underlying": under.exists()})
    hard = totals["bad_quotes"] + totals["outside_hours"] + totals["over_minutes"] + totals["unlisted_expiries"] + totals["checksum"]
    return {"at": sl.utc_now(), "checked": totals, "passed": hard == 0, "problems": problems[:40],
            "problem_days": len(problems),
            "rows_per_contract_mean": round(totals["rows"] / totals["contracts"], 1) if totals["contracts"] else None}


# ------------------------------------------------------------------------------ Alpaca agreement
def export_alpaca(sqlite_path: Path, out: Path) -> dict[str, Any]:
    """The recorded OPRA quotes with their contracts, to a csv.gz for the data box. Read-only."""
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    rows = con.execute(
        "select q.occ, q.t, q.bid, q.ask, c.underlying, c.expiry, c.strike, c.right from quotes q "
        "join contracts c using(occ) where q.source = 'opra' order by q.t").fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["occ", "t", "bid", "ask", "root", "expiration", "strike", "right"])
        writer.writerows(rows)
    out.chmod(0o600)
    days = sorted({r[1][:10] for r in rows})
    return {"rows": len(rows), "days": days, "roots": sorted({r[4] for r in rows}), "out": str(out)}


def alpaca(quotes_path: Path, store_root: Path, extra_roots: Sequence[Path] = ()) -> dict[str, Any]:
    """Each recorded quote against the store's minute row for the minute it fell in."""
    from zoneinfo import ZoneInfo

    import polars as pl

    eastern = ZoneInfo("America/New_York")
    quotes = pl.read_csv(quotes_path, schema_overrides={"strike": pl.Float64, "bid": pl.Float64, "ask": pl.Float64})
    stamp = pl.col("t").str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC").dt.convert_time_zone("America/New_York")
    quotes = quotes.with_columns(
        stamp.dt.date().alias("day"),
        (stamp.dt.hour().cast(pl.Int32) * 60 + stamp.dt.minute().cast(pl.Int32)).cast(pl.Int16).alias("minute"),
        stamp.dt.second().alias("second"),
        pl.col("expiration").str.slice(0, 10).str.to_date("%Y-%m-%d").alias("expiration"),
        pl.when(pl.col("right").str.to_uppercase().str.starts_with("C")).then(pl.lit("C")).otherwise(pl.lit("P")).alias("right"),
    )
    del eastern
    results, compared = [], []
    for (root, day), group in quotes.group_by(["root", "day"]):
        path = None
        for base in [store_root, *extra_roots]:
            candidate = Path(base) / sl.rel_path("nbbo", root, day)
            if candidate.exists():
                path = candidate
                break
        if path is None:
            results.append({"root": root, "day": str(day), "recorded": group.height, "store": False})
            continue
        store = pl.read_parquet(path).with_columns(pl.col("bid").cast(pl.Float64).alias("t_bid"),
                                                   pl.col("ask").cast(pl.Float64).alias("t_ask"))
        joined = group.join(store.select(["expiration", "strike", "right", "minute", "t_bid", "t_ask"]),
                            on=["expiration", "strike", "right", "minute"], how="inner")
        results.append({"root": root, "day": str(day), "recorded": group.height, "store": True, "matched": joined.height})
        if joined.height:
            compared.append(joined)
    if not compared:
        return {"at": sl.utc_now(), "by_root_day": results, "compared": 0}
    both = pl.concat(compared)
    tick_expr = (pl.when(pl.col("root").is_in(list(PENNY_ALWAYS)) | (pl.col("ask") < 3.0)).then(0.01).otherwise(0.05))
    both = both.with_columns(tick_expr.alias("tick"))
    within = ((pl.col("bid") - pl.col("t_bid")).abs() <= pl.col("tick") + 1e-6) & ((pl.col("ask") - pl.col("t_ask")).abs() <= pl.col("tick") + 1e-6)
    exact = ((pl.col("bid") - pl.col("t_bid")).abs() < 0.005) & ((pl.col("ask") - pl.col("t_ask")).abs() < 0.005)
    both = both.with_columns(within.alias("within"), exact.alias("exact"))
    early = both.filter(pl.col("second") <= 2)

    def rate(frame: Any, col: str) -> float | None:
        return round(float(frame[col].mean()), 4) if frame.height else None

    per_root = (both.group_by("root").agg(pl.len().alias("n"), pl.col("within").mean().alias("within"))
                .sort("root").to_dicts())
    return {
        "at": sl.utc_now(), "compared": both.height, "within_a_tick": rate(both, "within"), "exact": rate(both, "exact"),
        "first_seconds": {"compared": early.height, "within_a_tick": rate(early, "within"), "exact": rate(early, "exact")},
        "per_root": [{"root": r["root"], "n": r["n"], "within": round(r["within"], 4)} for r in per_root],
        "by_root_day": sorted(results, key=lambda r: (r["root"], r["day"])),
        "note": ("a recorded quote at hh:mm:ss is compared with the store's row for hh:mm (the NBBO in force at "
                 "hh:mm:00); quotes that changed inside the minute disagree by construction, so the rate for quotes "
                 "taken in a minute's first two seconds is the sharper test"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default=sl.STORE_ROOT)
    parser.add_argument("--work", default=sl.WORK_ROOT)
    sub = parser.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--json", action="store_true")
    q = sub.add_parser("quality")
    q.add_argument("--sample", type=int, default=None)
    q.add_argument("--root", default=None)
    q.add_argument("--window", default=None)
    a = sub.add_parser("alpaca")
    a.add_argument("--quotes", required=True)
    a.add_argument("--extra", action="append", default=[], help="another store-layout root to look in")
    e = sub.add_parser("export-alpaca")
    e.add_argument("--sqlite", default=str(Path.home() / "Work" / ".options-history" / "options_history.sqlite"))
    e.add_argument("--out", default=str(HERE.parents[1] / ".data" / "gym" / "alpaca_quotes_2026-09-22_24.csv.gz"))
    args = parser.parse_args(argv)
    work, store = Path(args.work), Path(args.store)
    if args.cmd == "report":
        data = report(work)
        if args.json:
            print(json.dumps(data, indent=1))
        else:
            print_report(data)
    elif args.cmd == "quality":
        result = quality(store, work, sample=args.sample, root=args.root, window=args.window)
        (work / "checks-quality.json").write_text(json.dumps(result, indent=1, default=str))
        print(json.dumps(result, indent=1, default=str))
    elif args.cmd == "alpaca":
        result = alpaca(Path(args.quotes), store, [Path(x) for x in args.extra])
        (work / "checks-alpaca.json").write_text(json.dumps(result, indent=1, default=str))
        print(json.dumps(result, indent=1, default=str))
    elif args.cmd == "export-alpaca":
        print(json.dumps(export_alpaca(Path(args.sqlite), Path(args.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
