"""Crypto derivatives signals: implied vol, perp funding, open interest and futures basis.

Kalshi's crypto price markets and the floor's Coinbase perps are both priced against the same
spot; the derivatives venues carry the information spot alone does not. Deribit's DVOL index
is the market's own implied vol for a 30-day horizon, which is what a "BTC above X by Friday"
bracket needs; funding rates across venues say which way leverage leans; the futures basis says
what the term structure pays. All four hosts are keyless and public; nothing here trades.

Hosts, endpoints and the fields relied on (probed live Sept 18, 2026):

    https://www.deribit.com  (JSON-RPC over GET; every answer is {"result": ...})
        /api/v2/public/get_index_price?index_name=btc_usd          result.index_price
        /api/v2/public/get_volatility_index_data?currency=BTC&resolution=3600
            &start_timestamp=<ms>&end_timestamp=<ms>               result.data[]: [t_ms, o, h, l, c]
            (DVOL exists for BTC and ETH only; other currencies answer an empty data list.
            result.continuation, when not null, is the end_timestamp of the next, older page:
            documented, not yet seen on a probe; league/feeds.py asks for 720 hours a page)
        /api/v2/public/get_book_summary_by_currency?currency=BTC&kind=future
            result[]: instrument_name, mark_price, mid_price, open_interest,
                      estimated_delivery_price (the index for that expiry), creation_timestamp
    https://www.okx.com  (every answer is {"code": "0", "data": [...]})
        /api/v5/public/funding-rate?instId=BTC-USDT-SWAP
            fundingRate, nextFundingRate (may be ""), fundingTime, nextFundingTime, premium
            (an 8-hour rate as a decimal fraction)
        /api/v5/public/funding-rate-history?instId=..&limit=30    fundingRate, fundingTime
            (&after=<fundingTime ms> pages back to older settlements, at most 100 a page; OKX's
            docs also list realizedRate, the rate actually charged, and about three months of
            history -- both UNVERIFIED on a probe)
        /api/v5/public/open-interest?instType=SWAP&instId=..      oi, oiCcy, oiUsd
        /api/v5/market/ticker?instId=..                           last, bidPx, askPx
    https://api.hyperliquid.xyz
        POST /info {"type": "metaAndAssetCtxs"}
            [ {universe: [{name, ...}]}, [{funding, openInterest, markPx, oraclePx, premium}] ]
            (the second list is aligned with universe; funding is a 1-hour rate)
    https://futures.kraken.com
        /derivatives/api/v3/tickers   tickers[]: symbol (PF_XBTUSD), fundingRate,
            fundingRatePrediction, markPrice, openInterest, indexPrice
            Kraken's fundingRate is the ABSOLUTE 1-hour rate in quote currency per contract
            (https://docs.kraken.com/api/docs/futures-api/trading/get-tickers); the relative
            rate reported here is fundingRate / markPrice. UNVERIFIED beyond that doc page.

Every value in a result is a float, int, str, bool or None so the dict ships as JSON. Rates are
per-interval decimal fractions (0.0001 = one basis point) and `interval_hours` names the
interval, so a caller annualizes as rate * (8760 / interval_hours).
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Mapping

from . import DataError, HttpTransport, TransportError, iso, read_json, require

DERIBIT_HOST = "https://www.deribit.com"
OKX_HOST = "https://www.okx.com"
HYPERLIQUID_HOST = "https://api.hyperliquid.xyz"
KRAKEN_HOST = "https://futures.kraken.com"
USER_AGENT = "ltcm (agent@blakewoods.us)"
SOURCE = "derivs"

#: Deribit allows 20 public requests a second unauthenticated; OKX 20 per 2 seconds. Ten a second
#: per host is well inside both and far more than the floor asks.
MIN_INTERVAL = 0.1
#: Kraken's perpetual symbols use XBT for Bitcoin.
KRAKEN_ALIASES = {"BTC": "XBT"}
_EXPIRY = re.compile(r"^[A-Z]+-(\d{1,2})([A-Z]{3})(\d{2})$")
_MONTHS = {m: i + 1 for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}


def _float(value: Any) -> "float | None":
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _ms_iso(value: Any) -> "str | None":
    stamp = _float(value)
    return iso(stamp / 1000.0) if stamp is not None and stamp > 0 else None


def expiry_of(instrument: Any) -> "str | None":
    """`BTC-9OCT26` -> `2026-10-09`; a perpetual or an unreadable name -> None."""
    found = _EXPIRY.match(str(instrument or "").upper())
    if not found:
        return None
    day, month, year = int(found.group(1)), _MONTHS.get(found.group(2)), 2000 + int(found.group(3))
    if month is None:
        return None
    try:
        return datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
    except ValueError:
        return None


def zscore(current: "float | None", history: list[float]) -> "float | None":
    """How many trailing standard deviations the current rate sits from the trailing mean."""
    values = [v for v in (_float(h) for h in history) if v is not None]
    if current is None or len(values) < 3:
        return None
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
    if sd <= max(abs(mean), 1e-12) * 1e-9:  # a flat history: floating-point noise is not a spread
        return 0.0
    return round((current - mean) / sd, 3)


class Derivatives:
    """DVOL, cross-venue funding, the Deribit futures basis and a per-symbol snapshot."""

    source = SOURCE

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        cache_dir: Any = None,
        cache_ttl: float = 30.0,
        clock: Any = time.time,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, user_agent=USER_AGENT, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self.clock = clock

    # ------------------------------------------------------------------ reads
    def _get(self, url: str, what: str) -> Any:
        return read_json(self.transport, url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}, timeout=self.timeout, what=what)

    def _deribit(self, path: str, params: dict[str, Any], what: str) -> Any:
        url = DERIBIT_HOST + path + "?" + urllib.parse.urlencode(params)
        payload = self._get(url, what)
        require(isinstance(payload, Mapping) and "result" in payload, f"{what}: no result")
        return payload["result"]

    def _okx(self, path: str, params: dict[str, Any], what: str) -> list:
        url = OKX_HOST + path + "?" + urllib.parse.urlencode(params)
        payload = self._get(url, what)
        require(isinstance(payload, Mapping) and str(payload.get("code")) == "0", f"{what}: okx code {payload.get('code') if isinstance(payload, Mapping) else '?'}")
        data = payload.get("data")
        return data if isinstance(data, list) else []

    def _post_json(self, url: str, body: dict[str, Any], what: str) -> Any:
        headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        status, _, raw = self.transport.request(
            "POST", url, headers=headers, body=json.dumps(body).encode("utf-8"), timeout=self.timeout
        )
        require(status == 200, f"{what}: HTTP {status} from {url}")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DataError(f"{what}: malformed JSON from {url}") from exc

    # ------------------------------------------------------------------- dvol
    def dvol(self, currency: str = "BTC", hours: int = 48) -> list[dict[str, Any]]:
        """Hourly DVOL candles for the trailing window: `[{t, open, high, low, close}]`."""
        end_ms = int(float(self.clock()) * 1000)
        start_ms = end_ms - max(1, int(hours)) * 3600 * 1000
        result = self._deribit(
            "/api/v2/public/get_volatility_index_data",
            {"currency": str(currency).upper(), "resolution": 3600, "start_timestamp": start_ms, "end_timestamp": end_ms},
            f"deribit dvol {currency}",
        )
        rows = result.get("data") if isinstance(result, Mapping) else None
        out = []
        for candle in rows if isinstance(rows, list) else []:
            if not isinstance(candle, (list, tuple)) or len(candle) < 5:
                continue
            values = [_float(v) for v in candle[:5]]
            if any(v is None for v in values):
                continue
            out.append({"t": iso(values[0] / 1000.0), "open": values[1], "high": values[2], "low": values[3], "close": values[4]})
        out.sort(key=lambda row: row["t"])
        return out

    def dvol_candles(self, currency: str, start_ms: int, end_ms: int) -> "tuple[list[dict[str, Any]], int | None]":
        """Hourly DVOL candles OPENING in [start_ms, end_ms], oldest first: `[{t_ms, open, high, low,
        close}]`, and Deribit's `continuation` -- None when the answer holds the whole range, else
        the end_timestamp that pages further back (Deribit pages from the newest end). A candle
        opening at `t_ms` is complete only at `t_ms` + 1 hour; which of them are final is the
        caller's to judge. Unlike `dvol_now`, a venue that fails raises (DataError/TransportError):
        the feed recorder must tell a failed poll from an empty one."""
        what = f"deribit dvol history {currency}"
        result = self._deribit(
            "/api/v2/public/get_volatility_index_data",
            {"currency": str(currency).upper(), "resolution": 3600, "start_timestamp": int(start_ms), "end_timestamp": int(end_ms)},
            what,
        )
        require(isinstance(result, Mapping) and isinstance(result.get("data"), list), f"{what}: no data list")
        out = []
        for candle in result["data"]:
            if not isinstance(candle, (list, tuple)) or len(candle) < 5:
                continue
            values = [_float(v) for v in candle[:5]]
            if any(v is None for v in values) or values[0] <= 0:
                continue
            out.append({"t_ms": int(values[0]), "open": values[1], "high": values[2], "low": values[3], "close": values[4]})
        out.sort(key=lambda row: row["t_ms"])
        more = _float(result.get("continuation"))
        return out, (int(more) if more else None)

    def dvol_now(self, currency: str = "BTC") -> "float | None":
        """The latest DVOL close, or None when the index has no data (or the host is down)."""
        try:
            rows = self.dvol(currency, hours=6)
        except (DataError, TransportError):
            return None
        return rows[-1]["close"] if rows else None

    # ---------------------------------------------------------------- funding
    def okx_funding(self, symbol: str = "BTC") -> "dict[str, Any] | None":
        inst = f"{str(symbol).upper()}-USDT-SWAP"
        try:
            rows = self._okx("/api/v5/public/funding-rate", {"instId": inst}, f"okx funding {inst}")
        except (DataError, TransportError):
            return None
        row = rows[0] if rows and isinstance(rows[0], Mapping) else None
        if row is None:
            return None
        found = {
            "instrument": inst,
            "rate": _float(row.get("fundingRate")),
            "next_rate": _float(row.get("nextFundingRate")),
            "time": _ms_iso(row.get("fundingTime")),
            "next_time": _ms_iso(row.get("nextFundingTime")),
            "premium": _float(row.get("premium")),
            "interval_hours": 8,
            "open_interest_usd": None,
            "last": None,
        }
        try:
            oi = self._okx("/api/v5/public/open-interest", {"instType": "SWAP", "instId": inst}, f"okx oi {inst}")
            if oi and isinstance(oi[0], Mapping):
                found["open_interest_usd"] = _float(oi[0].get("oiUsd"))
            ticker = self._okx("/api/v5/market/ticker", {"instId": inst}, f"okx ticker {inst}")
            if ticker and isinstance(ticker[0], Mapping):
                found["last"] = _float(ticker[0].get("last"))
        except (DataError, TransportError):
            pass
        return found

    def okx_funding_history(self, symbol: str = "BTC", limit: int = 30) -> list[float]:
        """Trailing settled OKX funding rates, newest first. Empty when unreachable."""
        inst = f"{str(symbol).upper()}-USDT-SWAP"
        try:
            rows = self._okx("/api/v5/public/funding-rate-history", {"instId": inst, "limit": int(limit)}, f"okx funding history {inst}")
        except (DataError, TransportError):
            return []
        return [r for r in (_float(row.get("fundingRate")) if isinstance(row, Mapping) else None for row in rows) if r is not None]

    def okx_funding_settled(self, symbol: str = "BTC", *, after_ms: "int | None" = None, limit: int = 100) -> list[dict[str, Any]]:
        """One page of OKX's settled funding for `<symbol>-USDT-SWAP`, newest first as OKX sends it:
        `[{time_ms, rate, funding_rate, realized_rate}]`. `time_ms` is the settlement (`fundingTime`),
        and `rate` is OKX's `realizedRate` (what was actually charged) when it sends one, else its
        `fundingRate`. `after_ms` pages back: only settlements before it. At most 100 a page.
        Unlike `okx_funding_history`, a venue that fails raises (DataError/TransportError); an
        instrument OKX does not list answers `okx code 51001`."""
        inst = f"{str(symbol).upper()}-USDT-SWAP"
        params: dict[str, Any] = {"instId": inst, "limit": max(1, min(int(limit), 100))}
        if after_ms is not None:
            params["after"] = int(after_ms)
        rows = self._okx("/api/v5/public/funding-rate-history", params, f"okx funding history {inst}")
        out = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            at, funding, realized = _float(row.get("fundingTime")), _float(row.get("fundingRate")), _float(row.get("realizedRate"))
            rate = realized if realized is not None else funding
            if at is None or at <= 0 or rate is None:
                continue
            out.append({"time_ms": int(at), "rate": rate, "funding_rate": funding, "realized_rate": realized})
        return out

    def hyperliquid_all(self) -> dict[str, dict[str, Any]]:
        """Every Hyperliquid perp's funding, OI and marks keyed by coin. Empty when unreachable."""
        try:
            payload = self._post_json(HYPERLIQUID_HOST + "/info", {"type": "metaAndAssetCtxs"}, "hyperliquid meta")
        except (DataError, TransportError):
            return {}
        if not (isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[0], Mapping)):
            return {}
        universe = payload[0].get("universe")
        contexts = payload[1]
        if not isinstance(universe, list) or not isinstance(contexts, list):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for asset, context in zip(universe, contexts):
            if not isinstance(asset, Mapping) or not isinstance(context, Mapping):
                continue
            name = str(asset.get("name") or "").upper()
            if not name:
                continue
            out[name] = {
                "rate": _float(context.get("funding")),
                "open_interest": _float(context.get("openInterest")),
                "mark": _float(context.get("markPx")),
                "oracle": _float(context.get("oraclePx")),
                "premium": _float(context.get("premium")),
                "interval_hours": 1,
            }
        return out

    def kraken_all(self) -> dict[str, dict[str, Any]]:
        """Every Kraken perpetual (`PF_*USD`) keyed by base symbol. Empty when unreachable."""
        try:
            payload = self._get(KRAKEN_HOST + "/derivatives/api/v3/tickers", "kraken tickers")
        except (DataError, TransportError):
            return {}
        rows = payload.get("tickers") if isinstance(payload, Mapping) else None
        out: dict[str, dict[str, Any]] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not (symbol.startswith("PF_") and symbol.endswith("USD")):
                continue
            base = symbol[3:-3]
            mark = _float(row.get("markPrice"))
            absolute, predicted = _float(row.get("fundingRate")), _float(row.get("fundingRatePrediction"))
            out[base] = {
                "symbol": symbol,
                "rate": round(absolute / mark, 10) if absolute is not None and mark else None,
                "next_rate": round(predicted / mark, 10) if predicted is not None and mark else None,
                "rate_abs": absolute,
                "open_interest": _float(row.get("openInterest")),
                "mark": mark,
                "index": _float(row.get("indexPrice")),
                "interval_hours": 1,
            }
        return out

    def funding(self, symbol: str = "BTC") -> dict[str, Any]:
        """Funding on OKX, Hyperliquid and Kraken for one coin; a venue is None when unreachable."""
        symbol = str(symbol).upper()
        return {
            "symbol": symbol,
            "okx": self.okx_funding(symbol),
            "hyperliquid": self.hyperliquid_all().get(symbol),
            "kraken": self.kraken_all().get(KRAKEN_ALIASES.get(symbol, symbol)),
            "as_of": iso(float(self.clock())),
        }

    # ------------------------------------------------------------------ basis
    def basis(self, currency: str = "BTC") -> list[dict[str, Any]]:
        """Deribit futures marks against the index: `[{instrument, mark, index, basis_pct, expiry}]`."""
        currency = str(currency).upper()
        index_result = self._deribit("/api/v2/public/get_index_price", {"index_name": f"{currency.lower()}_usd"}, f"deribit index {currency}")
        index = _float(index_result.get("index_price")) if isinstance(index_result, Mapping) else None
        rows = self._deribit("/api/v2/public/get_book_summary_by_currency", {"currency": currency, "kind": "future"}, f"deribit futures {currency}")
        require(isinstance(rows, list), f"deribit futures {currency}: not a list")
        out = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            name = str(row.get("instrument_name") or "")
            mark = _float(row.get("mark_price"))
            spot = _float(row.get("estimated_delivery_price")) or index
            if not name or mark is None:
                continue
            out.append(
                {
                    "instrument": name,
                    "mark": mark,
                    "index": spot,
                    "basis_pct": round((mark / spot - 1.0) * 100.0, 4) if spot else None,
                    "expiry": expiry_of(name),
                    "open_interest": _float(row.get("open_interest")),
                    "mid": _float(row.get("mid_price")),
                }
            )
        out.sort(key=lambda row: (row["expiry"] is not None, row["expiry"] or "", row["instrument"]))
        return out

    # --------------------------------------------------------------- snapshot
    def snapshot(self, symbols: Any = ("BTC", "ETH", "SOL")) -> list[dict[str, Any]]:
        """One row per symbol: funding across venues, DVOL and the OKX funding z-score.

        Hyperliquid and Kraken are fetched once for all symbols. Nothing here raises for one
        venue being down; a row with every venue None is still returned."""
        hyperliquid = self.hyperliquid_all()
        kraken = self.kraken_all()
        out = []
        for raw in symbols:
            symbol = str(raw).upper()
            okx = self.okx_funding(symbol)
            history = self.okx_funding_history(symbol)
            out.append(
                {
                    "symbol": symbol,
                    "okx": okx,
                    "hyperliquid": hyperliquid.get(symbol),
                    "kraken": kraken.get(KRAKEN_ALIASES.get(symbol, symbol)),
                    "dvol": self.dvol_now(symbol) if symbol in ("BTC", "ETH") else None,
                    "funding_z": zscore(okx.get("rate") if okx else None, history),
                    "funding_history_n": len(history),
                    "as_of": iso(float(self.clock())),
                }
            )
        return out


__all__ = [
    "DERIBIT_HOST",
    "Derivatives",
    "HYPERLIQUID_HOST",
    "KRAKEN_HOST",
    "OKX_HOST",
    "USER_AGENT",
    "expiry_of",
    "zscore",
]
