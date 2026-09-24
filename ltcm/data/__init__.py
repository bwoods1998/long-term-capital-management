"""Market and document sources: shared contracts, calendar and HTTP transport.

Standard library only (`urllib`, `json`, `sqlite3`, `decimal`, `hashlib`, `zoneinfo`). Nothing in
this package trades; it only observes. Every source is either public data or an explicitly
delayed feed, and every quote carries `delayed` and `source` so the publisher can label it.

The US equity calendar is ported from `portfolio_runtime/market.py`, which pinned a reviewed
literal set for 2026 only. Here the same closures are computed by rule so 2026-2030 and beyond
need no review of a literal list, and the 2026 output is asserted against the reviewed set in
`ltcm/tests/test_data_calendar.py`.

Rules and hours verified against:
  - https://www.nyse.com/markets/hours-calendars (NYSE holidays and 1:00 p.m. ET early closes)
  - https://www.sec.gov/os/webmaster-faq#developers (SEC requires a contact User-Agent)

`HttpTransport` is the only thing here that touches the network. Tests inject a fake with the
same `get`/`request` signature; nothing under `ltcm/tests/` opens a socket.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta, timezone
from html.parser import HTMLParser
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from ..broker import Instrument, Quote, money, text

NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc

#: The User-Agent the SEC and the National Weather Service ask every client to send, an application
#: name and a contact address (https://www.sec.gov/os/webmaster-faq#developers,
#: https://www.weather.gov/documentation/services-web-api). Sept 24, 2026: one constant, so the owner
#: changes the contact in one place; the NWS, Open-Meteo, derivatives, macro and EDGAR readers and
#: the House's feed recorders (league/feeds.py) all send it.
CONTACT_USER_AGENT = "ltcm (agent@blakewoods.us)"
#: The default every `HttpTransport` sends (the older EDGAR calls among them). Sept 24, 2026: it named
#: the owner's personal address; it is the one contact constant now, so no reader sends another.
USER_AGENT = CONTACT_USER_AGENT
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
#: The on-disk HTTP cache never grows past this; the oldest entries go first.
CACHE_CAP_BYTES = 256 * 1024 * 1024
#: How many stores between trims: a glob of the cache directory is cheap but not free.
TRIM_EVERY_STORES = 50
DEFAULT_TIMEOUT = 20

INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d", "1wk", "1mo")

#: Years the computed calendar is trusted for. Juneteenth became an NYSE holiday in 2022 and the
#: rules below encode the post-2022 regime only.
CALENDAR_MIN_YEAR = 2022
CALENDAR_MAX_YEAR = 2100

#: Full closures that no rule can produce (days of mourning, disasters). Add, never remove.
SPECIAL_CLOSURES: dict[str, str] = {
    "2025-01-09": "National Day of Mourning (Jimmy Carter)",
}


class DataError(ValueError):
    """A source returned something this code will not guess about."""


class TransportError(RuntimeError):
    """The request did not complete. Never raised for an HTTP status code."""


# --------------------------------------------------------------------------- contracts


@dataclass(frozen=True)
class Bar:
    """One OHLCV interval. Timestamps are ISO-8601 UTC; prices and volume are Decimal."""

    instrument: Instrument
    start: str
    end: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self):
        for name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, name, money(getattr(self, name)))
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise DataError("bar prices must be positive")
        if self.volume < 0:
            raise DataError("bar volume must not be negative")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise DataError("bar OHLC values are inconsistent")
        if not isinstance(self.start, str) or not isinstance(self.end, str):
            raise DataError("bar timestamps must be ISO strings")
        if self.end <= self.start:
            raise DataError("bar end must follow its start")

    @property
    def dollar_volume(self) -> Decimal:
        """Close times volume: the standard cheap proxy for one session's traded value."""
        return self.close * self.volume * self.instrument.multiplier

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument.to_dict(),
            "start": self.start,
            "end": self.end,
            "open": text(self.open),
            "high": text(self.high),
            "low": text(self.low),
            "close": text(self.close),
            "volume": text(self.volume),
        }


@dataclass(frozen=True)
class MarketSession:
    """One regular trading session. `date` is the local (exchange) calendar day."""

    date: str
    open_at: str
    close_at: str
    early_close: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "open_at": self.open_at,
            "close_at": self.close_at,
            "early_close": self.early_close,
        }


@runtime_checkable
class MarketData(Protocol):
    """What every price source provides. Implementations never raise for a missing session."""

    source: str

    def quote(self, instrument: Instrument) -> Quote: ...

    def bars(self, instrument: Instrument, interval: str = "1d", limit: int = 30) -> list[Bar]: ...

    def session(self, day: "str | date") -> MarketSession | None:
        """The US equity session for a calendar day, or None when the market is closed."""

    def adv_usd(self, instrument: Instrument) -> Decimal | None:
        """Average daily dollar volume, or None when the source cannot say."""


# ---------------------------------------------------------------------------- calendar


def easter(year: int) -> date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher). 2026-04-05, 2027-03-28, 2028-04-16."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth (1-based) `weekday` (Monday=0) of a month; n=-1 means the last one."""
    if n > 0:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + 7 * (n - 1))
    last_day = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def observed(day: date) -> date:
    """NYSE observance: a Saturday holiday moves to Friday, a Sunday holiday to Monday."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _check_year(year: int) -> None:
    if not CALENDAR_MIN_YEAR <= year <= CALENDAR_MAX_YEAR:
        raise DataError(
            f"the computed NYSE calendar covers {CALENDAR_MIN_YEAR}-{CALENDAR_MAX_YEAR}; "
            f"{year} needs a reviewed rule change"
        )


def nyse_holidays(year: int) -> dict[str, str]:
    """Full NYSE closures for a year, computed by rule. Keys are ISO dates."""
    _check_year(year)
    days: dict[str, str] = {}

    def add(day: date, name: str) -> None:
        if day.weekday() < 5 and day.year == year:
            days[day.isoformat()] = name

    add(observed(date(year, 1, 1)), "New Year's Day")
    add(nth_weekday(year, 1, 0, 3), "Martin Luther King, Jr. Day")
    add(nth_weekday(year, 2, 0, 3), "Washington's Birthday")
    add(easter(year) - timedelta(days=2), "Good Friday")
    add(nth_weekday(year, 5, 0, -1), "Memorial Day")
    add(observed(date(year, 6, 19)), "Juneteenth National Independence Day")
    add(observed(date(year, 7, 4)), "Independence Day")
    add(nth_weekday(year, 9, 0, 1), "Labor Day")
    add(nth_weekday(year, 11, 3, 4), "Thanksgiving Day")
    add(observed(date(year, 12, 25)), "Christmas Day")
    # New Year's Day falling on a Saturday is *not* observed on the preceding Friday by the NYSE,
    # so `observed()` would wrongly close 31 December of the previous year. Guard it here.
    if date(year, 1, 1).weekday() == 5:
        days.pop(date(year - 1, 12, 31).isoformat(), None)
    for iso, name in SPECIAL_CLOSURES.items():
        if iso.startswith(f"{year:04d}-") and date.fromisoformat(iso).weekday() < 5:
            days[iso] = name
    return dict(sorted(days.items()))


def nyse_early_closes(year: int) -> dict[str, str]:
    """1:00 p.m. ET closes, computed by rule. Keys are ISO dates."""
    _check_year(year)
    days: dict[str, str] = {}
    holidays = nyse_holidays(year)

    def add(day: date, name: str) -> None:
        if day.weekday() < 5 and day.year == year and day.isoformat() not in holidays:
            days[day.isoformat()] = name

    # The day after Thanksgiving is always a half day.
    add(nth_weekday(year, 11, 3, 4) + timedelta(days=1), "Day after Thanksgiving")
    # 3 July is a half day only when Independence Day itself is the trading holiday; when 4 July
    # falls at a weekend the observed closure lands on 3 or 5 July and there is no half day.
    if date(year, 7, 4).weekday() < 5:
        add(date(year, 7, 3), "Day before Independence Day")
    # 24 December is a half day only when Christmas Day itself is the trading holiday and the 24th
    # is a weekday (Christmas on a Monday puts the 24th at the weekend).
    if date(year, 12, 25).weekday() < 5:
        add(date(year, 12, 24), "Christmas Eve")
    return dict(sorted(days.items()))


def as_day(value: "str | date | datetime") -> date:
    if isinstance(value, datetime):
        return value.astimezone(NEW_YORK).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise DataError(f"not a date: {value!r}")


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def us_equity_session(day: "str | date | datetime") -> MarketSession | None:
    """The regular NYSE/Nasdaq session for a day, or None when the market is closed."""
    day = as_day(day)
    _check_year(day.year)
    iso = day.isoformat()
    if day.weekday() >= 5 or iso in nyse_holidays(day.year):
        return None
    early = iso in nyse_early_closes(day.year)
    opened = datetime.combine(day, clock_time(9, 30), NEW_YORK)
    closed = datetime.combine(day, clock_time(13 if early else 16), NEW_YORK)
    return MarketSession(date=iso, open_at=_stamp(opened), close_at=_stamp(closed), early_close=early)


def next_session(after: "str | date | datetime", *, horizon: int = 15) -> MarketSession | None:
    """The first session opening strictly after `after`."""
    moment = to_datetime(after)
    day = moment.astimezone(NEW_YORK).date()
    for _ in range(horizon):
        session = us_equity_session(day)
        if session is not None and to_datetime(session.open_at) > moment:
            return session
        day += timedelta(days=1)
    return None


def previous_session(before: "str | date | datetime", *, horizon: int = 15) -> MarketSession | None:
    """The last session that had already closed at `before`."""
    moment = to_datetime(before)
    day = moment.astimezone(NEW_YORK).date()
    for _ in range(horizon):
        session = us_equity_session(day)
        if session is not None and to_datetime(session.close_at) <= moment:
            return session
        day -= timedelta(days=1)
    return None


def market_open_at(moment: "str | datetime") -> bool:
    """True when regular US equity hours contain `moment`."""
    instant = to_datetime(moment)
    session = us_equity_session(instant)
    if session is None:
        return False
    return to_datetime(session.open_at) <= instant < to_datetime(session.close_at)


def to_datetime(value: "str | datetime | date | int | float") -> datetime:
    """Normalize a clock reading or ISO timestamp to an aware UTC datetime.

    Accepts what the rest of the runtime already produces: `time.time()` floats, ISO strings with
    or without a trailing Z, datetimes (naive ones are read as UTC) and plain dates.
    """
    if isinstance(value, bool):
        raise DataError("a bool is not a time")
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, clock_time(0, 0), UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith(("Z", "z")):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise DataError(f"not an ISO timestamp: {value!r}") from exc
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise DataError(f"not a time: {value!r}")


def iso(value: "str | datetime | date | int | float") -> str:
    """Seconds-precision UTC stamp, the form every source in this package emits."""
    return _stamp(to_datetime(value))


# --------------------------------------------------------------------------- transport


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are a source change; callers decide, this transport never follows one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def _headers_to_dict(headers: Iterable[tuple[str, str]] | Any) -> dict[str, str]:
    try:
        items = headers.items()
    except AttributeError:
        items = headers or ()
    return {str(k).lower(): str(v) for k, v in items}


_SSL_CONTEXT = None


def _shared_ssl_context():
    """The process-wide TLS context (built once; certificates loaded once)."""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        import ssl

        _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


class HttpTransport:
    """Bounded, redirect-free HTTP with an optional on-disk TTL cache.

    Every network read in `ltcm.data` goes through one of these. Responses are capped at
    4 MB, HTTP status codes are returned rather than raised, and transport failures raise
    `TransportError`. The default User-Agent carries a contact address because the SEC requires
    one (https://www.sec.gov/os/webmaster-faq#developers).

    `min_interval` throttles consecutive requests to the same host; the sleep function is
    injected so tests never wait.
    """

    def __init__(
        self,
        *,
        cache_dir: "str | Path | None" = None,
        ttl: float = 0,
        opener: Any = None,
        clock=time.time,
        sleep=time.sleep,
        user_agent: str = USER_AGENT,
        max_bytes: int = MAX_RESPONSE_BYTES,
        min_interval: float = 0.0,
        cache_cap_bytes: int = CACHE_CAP_BYTES,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = float(ttl)
        self.clock = clock
        self.sleep = sleep
        self.user_agent = user_agent
        self.max_bytes = int(max_bytes)
        self.min_interval = float(min_interval)
        self.cache_cap_bytes = int(cache_cap_bytes)
        self._stores = 0
        # One TLS context for every request: `urlopen` builds a fresh context and reloads the
        # CA bundle per call, which was most of each quote's cost on Sept 18, 2026.
        self._opener = opener or urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_shared_ssl_context())).open
        self._lock = threading.RLock()
        self._next_at: dict[str, float] = {}

    # ------------------------------------------------------------------ cache
    def _cache_path(self, url: str) -> "Path | None":
        if self.cache_dir is None or self.ttl <= 0:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:40] + ".json")

    def cached(self, url: str) -> "tuple[int, dict[str, str], bytes] | None":
        """The cached response for a URL when it is still inside its TTL."""
        path = self._cache_path(url)
        if path is None or not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            age = float(self.clock()) - float(record["fetched_at"])
            if age < 0 or age > self.ttl:
                return None
            return (
                int(record["status"]),
                dict(record["headers"]),
                base64.b64decode(record["body"].encode("ascii")),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _store(self, url: str, status: int, headers: dict[str, str], body: bytes) -> None:
        path = self._cache_path(url)
        if path is None or status != 200:
            return
        record = {
            "url": url,
            "status": status,
            "headers": headers,
            "body": base64.b64encode(body).decode("ascii"),
            "fetched_at": float(self.clock()),
        }
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(record), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            try:
                tmp.unlink()  # a half-written entry on a full disk is never a cache hit
            except OSError:
                pass
            return
        self._stores += 1
        if self._stores % TRIM_EVERY_STORES == 0:
            self.trim()

    def trim(self, *, force: bool = False) -> int:
        """Keep the cache directory bounded: drop expired entries and stray temp files, then
        the oldest entries until the directory fits `cache_cap_bytes`. Returns the number removed.
        The cache had no eviction at all before Sept 16, 2026, when a floor box ran its disk full
        and the loop died with nothing on the tape about it; every store now trims periodically."""
        if self.cache_dir is None:
            return 0
        removed = self.purge()
        now = float(self.clock())
        entries: list[tuple[float, int, Path]] = []
        for path in self.cache_dir.iterdir():
            try:
                stat = path.stat()
            except OSError:
                continue
            if path.suffix == ".tmp" and (force or now - stat.st_mtime > 600):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
                continue
            if path.suffix == ".json":
                entries.append((stat.st_mtime, stat.st_size, path))
        total = sum(size for _, size, _ in entries)
        for _, size, path in sorted(entries):
            if total <= self.cache_cap_bytes:
                break
            try:
                path.unlink()
                removed += 1
                total -= size
            except OSError:
                pass
        return removed

    def purge(self) -> int:
        """Delete expired cache entries. Returns the number removed."""
        if self.cache_dir is None:
            return 0
        removed = 0
        for path in self.cache_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if float(self.clock()) - float(record["fetched_at"]) > self.ttl:
                    path.unlink()
                    removed += 1
            except (OSError, ValueError, KeyError, TypeError):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    # ---------------------------------------------------------------- requests
    def _throttle(self, url: str) -> None:
        if self.min_interval <= 0:
            return
        host = urllib.parse.urlsplit(url).netloc or url
        with self._lock:
            now = time.monotonic()
            wait = self._next_at.get(host, 0.0) - now
            if wait > 0:
                self.sleep(wait)
            self._next_at[host] = time.monotonic() + self.min_interval

    def get(
        self,
        url: str,
        headers: "dict[str, str] | None" = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> tuple[int, dict[str, str], bytes]:
        """GET a URL. Returns (status, lowercased headers, body). Cached when a TTL is set."""
        hit = self.cached(url)
        if hit is not None:
            return hit
        status, response_headers, body = self.request("GET", url, headers=headers, timeout=timeout)
        self._store(url, status, response_headers, body)
        return status, response_headers, body

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: "dict[str, str] | None" = None,
        body: "bytes | None" = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> tuple[int, dict[str, str], bytes]:
        """One uncached HTTP request. Status codes are returned, not raised."""
        if not isinstance(url, str) or not url.startswith("https://"):
            raise DataError(f"refusing a non-HTTPS URL: {url!r}")
        sent = {"User-Agent": self.user_agent, "Accept-Encoding": "identity"}
        sent.update(headers or {})
        self._throttle(url)
        request = urllib.request.Request(url, data=body, headers=sent, method=method.upper())
        try:
            with self._opener(request, timeout=timeout) as response:
                payload = response.read(self.max_bytes + 1)
                status = int(getattr(response, "status", 0) or response.getcode() or 0)
                response_headers = _headers_to_dict(getattr(response, "headers", {}))
        except urllib.error.HTTPError as error:  # 4xx, 5xx and unfollowed redirects
            payload = error.read(self.max_bytes + 1)
            status = int(error.code)
            response_headers = _headers_to_dict(getattr(error, "headers", {}))
        except urllib.error.URLError as error:
            raise TransportError(f"{method} {url} failed: {error.reason}") from error
        except OSError as error:  # socket.timeout and friends
            raise TransportError(f"{method} {url} failed: {error}") from error
        if len(payload) > self.max_bytes:
            raise DataError(f"response from {url} exceeds {self.max_bytes} bytes")
        return status, response_headers, payload


def read_json(
    transport: Any,
    url: str,
    *,
    headers: "dict[str, str] | None" = None,
    timeout: float = DEFAULT_TIMEOUT,
    what: str = "response",
) -> Any:
    """GET and parse JSON with Decimal numbers, failing loudly on anything else."""
    status, _, body = transport.get(url, headers or {}, timeout)
    if status != 200:
        raise DataError(f"{what}: HTTP {status} from {url}")
    try:
        return json.loads(
            body.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=lambda name: (_ for _ in ()).throw(DataError(f"{what}: {name} in JSON")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataError(f"{what}: malformed JSON from {url}") from exc


def require(condition: Any, message: str) -> None:
    if not condition:
        raise DataError(message)


def decimal_or_none(value: Any) -> "Decimal | None":
    """Parse a source number defensively: None for null, missing or unusable values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):  # only ever from a json.loads without parse_float=Decimal
        value = repr(value)
    try:
        result = money(value)
    except (ValueError, ArithmeticError):
        return None
    return result if result.is_finite() else None


# ------------------------------------------------------------------------ html

class _TextExtractor(HTMLParser):
    """Visible text only: scripts, styles, inline XBRL headers and <head> are dropped.

    Ported from `portfolio_runtime/filings.py`, which has run against real EDGAR documents.
    Block tags become newlines so paragraph structure survives; everything else collapses to
    single spaces. `convert_charrefs` (the default) resolves entities.
    """

    HIDDEN = ("script", "style", "head", "ix:header", "noscript")
    BLOCK = ("p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table", "section")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif not self.hidden and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def strip_html(payload: "str | bytes") -> str:
    """Markup to readable text. Never raises on malformed HTML; always returns a string."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "replace")
    if not isinstance(payload, str):
        raise DataError("strip_html expects text or bytes")
    parser = _TextExtractor()
    try:
        parser.feed(payload)
        parser.close()
    except Exception:  # a truncated document still yields the text parsed so far
        pass
    return parser.text()


# ------------------------------------------------------------------- composite

class CompositeMarketData:
    """One `MarketData` facade that routes each instrument to the source that owns its venue.

    equity and option -> Yahoo (delayed), crypto -> Coinbase Advanced Trade, event -> Kalshi.
    Sources are constructed lazily so importing this package never touches the network and a
    test can inject fakes for only the classes it exercises.
    """

    source = "composite"

    ROUTES: dict[str, str] = {
        "equity": "equity",
        "option": "equity",
        "future": "equity",
        "crypto": "crypto",
        "event": "event",
    }

    def __init__(
        self,
        *,
        equity: Any = None,
        crypto: Any = None,
        event: Any = None,
        transport: Any = None,
    ):
        self.transport = transport
        self._sources: dict[str, Any] = {}
        for name, source in (("equity", equity), ("crypto", crypto), ("event", event)):
            if source is not None:
                self._sources[name] = source

    def _source(self, name: str) -> Any:
        existing = self._sources.get(name)
        if existing is not None:
            return existing
        if name == "equity":
            from .yahoo import YahooMarketData

            built: Any = YahooMarketData(self.transport)
        elif name == "crypto":
            from .coinbase import CoinbaseMarketData

            built = CoinbaseMarketData(self.transport)
        elif name == "event":
            from .kalshi import KalshiMarketData

            built = KalshiMarketData(self.transport)
        else:  # pragma: no cover - ROUTES has no other values
            raise DataError(f"no market data source named {name!r}")
        self._sources[name] = built
        return built

    def route(self, instrument: Instrument) -> Any:
        """The source that answers for this instrument. A future on Coinbase (a CDE contract,
        Sept 17, 2026) is quoted by Coinbase's own market data, not the equity source."""
        name = self.ROUTES.get(instrument.asset_class)
        if instrument.asset_class == "future" and str(instrument.venue).lower() == "coinbase":
            name = "crypto"
        if name is None:
            raise DataError(f"no market data route for asset class {instrument.asset_class!r}")
        return self._source(name)

    def quote(self, instrument: Instrument) -> Quote:
        return self.route(instrument).quote(instrument)

    def bars(self, instrument: Instrument, interval: str = "1d", limit: int = 30) -> list[Bar]:
        return self.route(instrument).bars(instrument, interval, limit)

    def session(self, day: "str | date") -> "MarketSession | None":
        """The US equity session. Crypto and event venues have no daily session; callers that
        need one ask this and get the equity calendar, which is what schedules the floor."""
        return us_equity_session(day)

    def adv_usd(self, instrument: Instrument) -> "Decimal | None":
        source = self.route(instrument)
        getter = getattr(source, "adv_usd", None)
        return getter(instrument) if getter is not None else None


__all__ = [
    "Bar",
    "MarketSession",
    "MarketData",
    "CompositeMarketData",
    "HttpTransport",
    "strip_html",
    "DataError",
    "TransportError",
    "USER_AGENT",
    "CONTACT_USER_AGENT",
    "MAX_RESPONSE_BYTES",
    "INTERVALS",
    "SPECIAL_CLOSURES",
    "easter",
    "nth_weekday",
    "observed",
    "nyse_holidays",
    "nyse_early_closes",
    "us_equity_session",
    "next_session",
    "previous_session",
    "market_open_at",
    "to_datetime",
    "iso",
    "as_day",
    "read_json",
    "require",
    "decimal_or_none",
    "NEW_YORK",
    "UTC",
]
