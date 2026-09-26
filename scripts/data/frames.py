"""Parquet for the Gym store (polars + pyarrow): ThetaData frames in, the fixed v1 schema out.

Runs on the data box (and in tests when polars is installed). Every writer is atomic (a temporary
file renamed into place) and returns (rows, sha256, bytes). The schema is the one in
`storelib`'s docstring and the plan; nothing here adds a date column to a per-day file.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import polars as pl

try:  # the scripts/data directory is on sys.path when these modules run
    from storelib import sha256_file
except ImportError:  # pragma: no cover - imported as a package
    from .storelib import sha256_file

NBBO_SCHEMA = {
    "expiration": pl.Date, "strike": pl.Float64, "right": pl.Utf8, "minute": pl.Int16,
    "bid": pl.Float32, "ask": pl.Float32, "bid_size": pl.Int32, "ask_size": pl.Int32,
}
UNDERLYING_SCHEMA = {"minute": pl.Int16, "price": pl.Float64}
OI_SCHEMA = {"expiration": pl.Date, "strike": pl.Float64, "right": pl.Utf8, "open_interest": pl.Int64}
TQ_SCHEMA = {
    "expiration": pl.Date, "strike": pl.Float64, "right": pl.Utf8, "ms_of_day": pl.Int32,
    "price": pl.Float64, "size": pl.Int32, "condition": pl.Int16, "exchange": pl.Int16,
    "bid": pl.Float32, "ask": pl.Float32, "bid_size": pl.Int32, "ask_size": pl.Int32,
}
CONTRACT_KEY = ["expiration", "strike", "right"]


def _right(col: str = "right") -> pl.Expr:
    text = pl.col(col).cast(pl.Utf8).str.to_uppercase()
    return pl.when(text.str.starts_with("C")).then(pl.lit("C")).when(text.str.starts_with("P")).then(pl.lit("P")).otherwise(None)


def _expiration(col: str = "expiration") -> pl.Expr:
    return pl.col(col).cast(pl.Utf8).str.slice(0, 10).str.to_date("%Y-%m-%d")


def _minute(col: str = "timestamp") -> pl.Expr:
    """Minutes since midnight ET. ThetaData stamps option rows in America/New_York."""
    ts = pl.col(col)
    return (ts.dt.hour().cast(pl.Int32) * 60 + ts.dt.minute().cast(pl.Int32)).cast(pl.Int16)


def _dte_filter(day: dt.date, max_dte: int, min_dte: int = 0) -> pl.Expr:
    lo = day + dt.timedelta(days=min_dte)
    hi = day + dt.timedelta(days=max_dte)
    return (pl.col("expiration") >= lo) & (pl.col("expiration") <= hi)


def nbbo(raw: pl.DataFrame, day: dt.date, *, open_min: int, close_min: int, max_dte: int,
         min_dte: int = 0) -> tuple[pl.DataFrame, dict[str, int]]:
    """ThetaData one-minute quote rows -> the store's NBBO rows, and what was dropped and why.

    A row is the NBBO in force at the minute's start. Dropped: no quote yet (NaN or null), an ask
    of zero or less (no offer), a negative bid, and crossed quotes (bid above ask). A zero bid is
    kept (a real no-bid); a locked quote (bid equal to ask) is kept.
    """
    stats = {"raw": raw.height}
    if raw.height == 0:
        return pl.DataFrame(schema=NBBO_SCHEMA), {**stats, "kept": 0}
    frame = raw.select(
        _expiration().alias("expiration"),
        pl.col("strike").cast(pl.Float64),
        _right().alias("right"),
        _minute().alias("minute"),
        pl.col("bid").cast(pl.Float64).alias("bid"),
        pl.col("ask").cast(pl.Float64).alias("ask"),
        pl.col("bid_size").cast(pl.Int64).alias("bid_size"),
        pl.col("ask_size").cast(pl.Int64).alias("ask_size"),
    ).filter(_dte_filter(day, max_dte, min_dte) & pl.col("right").is_not_null()
             & (pl.col("minute") >= open_min) & (pl.col("minute") <= close_min))
    stats["in_window"] = frame.height
    missing = pl.col("bid").is_null() | pl.col("ask").is_null() | pl.col("bid").is_nan() | pl.col("ask").is_nan()
    stats["no_quote"] = frame.filter(missing).height
    frame = frame.filter(~missing)
    stats["no_offer"] = frame.filter(pl.col("ask") <= 0).height
    stats["negative"] = frame.filter((pl.col("ask") > 0) & (pl.col("bid") < 0)).height
    stats["crossed"] = frame.filter((pl.col("ask") > 0) & (pl.col("bid") >= 0) & (pl.col("bid") > pl.col("ask"))).height
    frame = frame.filter((pl.col("ask") > 0) & (pl.col("bid") >= 0) & (pl.col("bid") <= pl.col("ask")))
    frame = frame.with_columns(
        pl.col("bid").cast(pl.Float32), pl.col("ask").cast(pl.Float32),
        pl.col("bid_size").clip(0, 2**31 - 1).cast(pl.Int32), pl.col("ask_size").clip(0, 2**31 - 1).cast(pl.Int32),
    ).unique(subset=CONTRACT_KEY + ["minute"], keep="last").sort(CONTRACT_KEY + ["minute"])
    stats["kept"] = frame.height
    return frame.select(list(NBBO_SCHEMA)), stats


def underlying(raw: pl.DataFrame, *, open_min: int, close_min: int) -> pl.DataFrame:
    """ThetaData greeks rows (a few near-the-money contracts) -> one price per minute."""
    if raw.height == 0 or "underlying_price" not in raw.columns:
        return pl.DataFrame(schema=UNDERLYING_SCHEMA)
    frame = raw.select(_minute().alias("minute"), pl.col("underlying_price").cast(pl.Float64).alias("price"))
    frame = frame.filter(pl.col("price").is_not_null() & ~pl.col("price").is_nan() & (pl.col("price") > 0)
                         & (pl.col("minute") >= open_min) & (pl.col("minute") <= close_min))
    return frame.group_by("minute").agg(pl.col("price").median()).sort("minute").select(list(UNDERLYING_SCHEMA))


def open_interest(raw: pl.DataFrame, day: dt.date, *, max_dte: int) -> pl.DataFrame:
    if raw.height == 0:
        return pl.DataFrame(schema=OI_SCHEMA)
    frame = raw.select(_expiration().alias("expiration"), pl.col("strike").cast(pl.Float64), _right().alias("right"),
                       pl.col("open_interest").cast(pl.Int64))
    frame = frame.filter(_dte_filter(day, max_dte) & pl.col("right").is_not_null() & pl.col("open_interest").is_not_null())
    return frame.unique(subset=CONTRACT_KEY, keep="last").sort(CONTRACT_KEY).select(list(OI_SCHEMA))


def expirations(raw: pl.DataFrame, day: dt.date, *, max_dte: int) -> list[dt.date]:
    """The distinct expiries in a contract list, from `day` to `day + max_dte`."""
    if raw.height == 0:
        return []
    frame = raw.select(_expiration().alias("expiration")).unique().filter(_dte_filter(day, max_dte))
    return sorted(frame["expiration"].to_list())


def trade_quote(raw: pl.DataFrame, day: dt.date, *, max_dte: int) -> pl.DataFrame:
    """ThetaData trade_quote rows -> calibration rows (the NBBO at each trade)."""
    if raw.height == 0:
        return pl.DataFrame(schema=TQ_SCHEMA)
    ts = pl.col("trade_timestamp") if "trade_timestamp" in raw.columns else pl.col("timestamp")
    ms = (ts.dt.hour().cast(pl.Int64) * 3_600_000 + ts.dt.minute().cast(pl.Int64) * 60_000
          + ts.dt.second().cast(pl.Int64) * 1000 + ts.dt.millisecond().cast(pl.Int64))
    frame = raw.select(
        _expiration().alias("expiration"), pl.col("strike").cast(pl.Float64), _right().alias("right"),
        ms.cast(pl.Int32).alias("ms_of_day"),
        pl.col("price").cast(pl.Float64), pl.col("size").cast(pl.Int32),
        pl.col("condition").cast(pl.Int16), pl.col("exchange").cast(pl.Int16),
        pl.col("bid").cast(pl.Float32), pl.col("ask").cast(pl.Float32),
        pl.col("bid_size").cast(pl.Int32), pl.col("ask_size").cast(pl.Int32),
    ).filter(_dte_filter(day, max_dte) & pl.col("right").is_not_null())
    return frame.sort(CONTRACT_KEY + ["ms_of_day"]).select(list(TQ_SCHEMA))


# ------------------------------------------------------------------------------ writing
def write(frame: pl.DataFrame, path: str | os.PathLike[str]) -> tuple[int, str, int]:
    """Write Parquet (zstd) atomically. Returns (rows, sha256, bytes)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp-{os.getpid()}-{id(frame)}")
    frame.write_parquet(tmp, compression="zstd", compression_level=6, statistics=True)
    with open(tmp, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    digest, size = sha256_file(target)
    return frame.height, digest, size


def merge_nbbo(existing: pl.DataFrame, extra: pl.DataFrame) -> pl.DataFrame:
    """The day's NBBO with more contracts added (back months); a contract-minute appears once."""
    both = pl.concat([existing.select(list(NBBO_SCHEMA)), extra.select(list(NBBO_SCHEMA))], how="vertical")
    return both.unique(subset=CONTRACT_KEY + ["minute"], keep="first").sort(CONTRACT_KEY + ["minute"])


def manifest_frame(records: Iterable[Mapping[str, Any]]) -> pl.DataFrame:
    rows = [r for r in records if r.get("kind")]
    frame = pl.DataFrame(
        {
            "kind": [str(r["kind"]) for r in rows],
            "root": [str(r["root"]) for r in rows],
            "date": [dt.date.fromisoformat(str(r["date"])) for r in rows],
            "rows": [int(r["rows"]) for r in rows],
            "sha256": [str(r["sha256"]) for r in rows],
            "bytes": [int(r["bytes"]) for r in rows],
            "window": [str(r["window"]) for r in rows],
            "fetched_at": [_ts(r["fetched_at"]) for r in rows],
            "source": [str(r.get("source") or "") for r in rows],
        },
        schema={"kind": pl.Utf8, "root": pl.Utf8, "date": pl.Date, "rows": pl.Int64, "sha256": pl.Utf8,
                "bytes": pl.Int64, "window": pl.Utf8, "fetched_at": pl.Datetime("us", "UTC"), "source": pl.Utf8},
    )
    return frame.sort(["kind", "root", "date"])


def _ts(text: Any) -> dt.datetime:
    value = str(text).replace("Z", "+00:00")
    stamp = dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def expiries_frame(rows: Iterable[tuple[str, dt.date, dt.date]]) -> pl.DataFrame:
    data = sorted(set(rows))
    return pl.DataFrame(
        {"root": [r[0] for r in data], "date": [r[1] for r in data], "expiration": [r[2] for r in data]},
        schema={"root": pl.Utf8, "date": pl.Date, "expiration": pl.Date},
    )


def calendar_frame(days: Sequence[tuple[dt.date, int, int]]) -> pl.DataFrame:
    data = sorted(days)
    return pl.DataFrame(
        {"date": [d[0] for d in data], "open_min": [d[1] for d in data], "close_min": [d[2] for d in data]},
        schema={"date": pl.Date, "open_min": pl.Int16, "close_min": pl.Int16},
    )
