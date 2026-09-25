"""Bitcoin's network and the crypto crowd's mood: mempool.space's fees, mempool and mining, and
alternative.me's Fear & Greed Index (Sept 25, 2026, the Kalshi-scale run's `mempool` and `fear_greed`
recorders, league/open_feeds_signals.py).

The crypto desks trade Kalshi's BTC strikes and Alpaca's coins around the clock; the House recorded
derivatives positioning (perps, funding, oi, vol) but nothing of the chain itself or of sentiment.

    GET https://mempool.space/api/v1/fees/recommended
      fastestFee, halfHourFee, hourFee, economyFee, minimumFee (sat/vB)
    GET https://mempool.space/api/mempool
      count, vsize (vbytes), total_fee (sats), fee_histogram [[feerate, vsize], ...]
    GET https://mempool.space/api/v1/difficulty-adjustment
      progressPercent, difficultyChange (% estimated), estimatedRetargetDate (ms), remainingBlocks,
      remainingTime (ms), previousRetarget (%), nextRetargetHeight, timeAvg (ms a block)
    GET https://mempool.space/api/v1/mining/hashrate/3d
      currentHashrate (H/s), currentDifficulty, hashrates[] {timestamp, avgHashrate}
    GET https://api.alternative.me/fng/?limit=N&format=json
      data[]: value ("71"), value_classification ("Greed"), timestamp (unix s, 00:00 UTC of the day),
      and on the newest only time_until_update (s). Probed Sept 25, 2026 06:59Z: the newest value's
      timestamp was 2026-09-25 00:00Z and time_until_update 61265 s -- the next value at 00:00Z on the
      26th: one value a UTC day, published at the day's start.

Terms (read Sept 25, 2026): mempool.space's terms (the mempool/mempool repository's terms page, updated
Jul 10, 2024) put no restriction on automated or commercial use of its public API; it rate-limits with
HTTP 429 and may ban an address that ignores it. alternative.me: "You are free to use our API ... this
includes commercial projects of any kind", attribution next to any display of the data required, 60
requests a minute (https://alternative.me/crypto/api/).
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from . import CONTACT_USER_AGENT, DataError, HttpTransport, read_json, require

MEMPOOL_HOST = "https://mempool.space"
FEES_URL = MEMPOOL_HOST + "/api/v1/fees/recommended"
MEMPOOL_URL = MEMPOOL_HOST + "/api/mempool"
DIFFICULTY_URL = MEMPOOL_HOST + "/api/v1/difficulty-adjustment"
HASHRATE_URL = MEMPOOL_HOST + "/api/v1/mining/hashrate/3d"
FNG_URL = "https://api.alternative.me/fng/"
MIN_INTERVAL = 1.0


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso(seconds: float | None) -> str | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_fees(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, Mapping) and _number(payload.get("fastestFee")) is not None, "mempool fees: no fastestFee")
    return {name: _number(payload.get(key)) for name, key in (("fastest", "fastestFee"), ("half_hour", "halfHourFee"),
                                                               ("hour", "hourFee"), ("economy", "economyFee"), ("minimum", "minimumFee"))}


def parse_mempool(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, Mapping) and _number(payload.get("count")) is not None, "mempool: no count")
    return {"count": _number(payload.get("count")), "vsize": _number(payload.get("vsize")), "total_fee_sats": _number(payload.get("total_fee"))}


def parse_difficulty(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, Mapping) and _number(payload.get("progressPercent")) is not None, "mempool difficulty: no progress")
    retarget = _number(payload.get("estimatedRetargetDate"))
    block = _number(payload.get("timeAvg"))
    return {"progress_pct": _number(payload.get("progressPercent")), "change_pct": _number(payload.get("difficultyChange")),
            "previous_change_pct": _number(payload.get("previousRetarget")), "remaining_blocks": _number(payload.get("remainingBlocks")),
            "retarget_height": _number(payload.get("nextRetargetHeight")),
            "estimated_retarget": _iso(retarget / 1000.0) if retarget is not None else None,
            "block_seconds": round(block / 1000.0, 1) if block is not None else None}


def parse_hashrate(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, Mapping) and _number(payload.get("currentHashrate")) is not None, "mempool hashrate: no currentHashrate")
    return {"hashrate_ehs": round(_number(payload.get("currentHashrate")) / 1e18, 3),
            "difficulty": _number(payload.get("currentDifficulty"))}


def parse_fear_greed(payload: Any) -> list[dict[str, Any]]:
    """alternative.me's index as `[{t (the value's own day start, unix s), date, value, classification}]`, oldest first."""
    rows = payload.get("data") if isinstance(payload, Mapping) else None
    require(isinstance(rows, list), "fear and greed: no data")
    error = (payload.get("metadata") or {}).get("error") if isinstance(payload.get("metadata"), Mapping) else None
    if error:
        raise DataError(f"fear and greed: {str(error)[:120]}")
    out = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        at, value = _number(row.get("timestamp")), _number(row.get("value"))
        if at is None or value is None:
            continue
        out.append({"t": at, "date": datetime.fromtimestamp(at, timezone.utc).date().isoformat(), "value": int(value),
                    "classification": row.get("value_classification")})
    out.sort(key=lambda row: row["t"])
    return out


class Chain:
    """mempool.space and alternative.me, asked with the contact User-Agent."""

    def __init__(self, transport: Any = None, *, timeout: float = 20.0, clock: Any = time.time):
        self.transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)
        self.timeout = float(timeout)
        self.clock = clock

    def _json(self, url: str, what: str) -> Any:
        return read_json(self.transport, url, headers={"Accept": "application/json", "User-Agent": CONTACT_USER_AGENT},
                         timeout=self.timeout, what=what)

    def fees(self) -> dict[str, Any]:
        return parse_fees(self._json(FEES_URL, "mempool fees"))

    def mempool(self) -> dict[str, Any]:
        return parse_mempool(self._json(MEMPOOL_URL, "mempool"))

    def difficulty(self) -> dict[str, Any]:
        return parse_difficulty(self._json(DIFFICULTY_URL, "mempool difficulty"))

    def hashrate(self) -> dict[str, Any]:
        return parse_hashrate(self._json(HASHRATE_URL, "mempool hashrate"))

    def fear_greed(self, limit: int) -> list[dict[str, Any]]:
        return parse_fear_greed(self._json(f"{FNG_URL}?limit={max(1, int(limit))}&format=json", "fear and greed"))


__all__ = ["Chain", "DIFFICULTY_URL", "FEES_URL", "FNG_URL", "HASHRATE_URL", "MEMPOOL_URL", "parse_difficulty", "parse_fear_greed",
           "parse_fees", "parse_hashrate", "parse_mempool"]
