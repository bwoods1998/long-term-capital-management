"""Versioned paper-account inputs. No market data or brokerage credentials live here."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


VERSION = 1
NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,8})?\Z")
SYMBOL = re.compile(r"[A-Z]{1,5}(?:[.-][A-Z])?\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
YAHOO_SP500TR = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5ESP500TR?interval=1d&range=1mo"
)


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ValueError("Use canonical UTC timestamps to whole seconds")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def utc_now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def number(value, *, positive=False):
    if not isinstance(value, str) or not NUMBER.fullmatch(value):
        raise ValueError(
            "Amounts and weights must be bounded nonnegative decimal strings"
        )
    result = Decimal(value)
    if positive and result <= 0:
        raise ValueError("A positive amount is required")
    return result


def decimal_text(value):
    raw = format(value, "f")
    return (
        raw.rstrip("0").rstrip(".") if "." in raw and value else raw if value else "0"
    )


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Use a bounded identifier")
    return value


def symbol(value):
    if not isinstance(value, str) or not SYMBOL.fullmatch(value):
        raise ValueError("Use a canonical US stock symbol")
    return value


def source_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("A source URL is required")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise ValueError("Sources require HTTPS URLs without credentials or fragments")
    return value


@dataclass(frozen=True)
class Mandate:
    initial_cash: str = "100000"
    max_position_weight: str = "0.20"
    max_quote_age_seconds: int = 90
    max_quote_skew_seconds: int = 5
    share_decimals: int = 0
    universe_max_age_days: int = 7
    open_slippage_bps: str = "5"

    def __post_init__(self):
        if number(self.initial_cash, positive=True) < Decimal("0.01"):
            raise ValueError("Initial virtual funding must be at least one cent")
        if not 0 < number(self.max_position_weight, positive=True) <= 1:
            raise ValueError("Maximum position weight must be in (0, 1]")
        if number(self.open_slippage_bps) > 100:
            raise ValueError(
                "The fixed paper opening slippage must be at most 100 basis points"
            )
        for name, maximum in (
            ("max_quote_age_seconds", 3600),
            ("max_quote_skew_seconds", 60),
            ("share_decimals", 6),
            ("universe_max_age_days", 31),
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0 or value > maximum:
                raise ValueError(f"Invalid {name}")
        if self.max_quote_age_seconds == 0 or self.universe_max_age_days == 0:
            raise ValueError("Quote and membership validity windows must be positive")


@dataclass(frozen=True)
class UniverseSnapshot:
    snapshot_id: str
    effective_at: str
    captured_at: str
    symbols: tuple[str, ...]
    source: str
    expires_at: str
    index: str = "S&P 500"

    def __post_init__(self):
        identifier(self.snapshot_id)
        effective, captured, expires = map(
            timestamp, (self.effective_at, self.captured_at, self.expires_at)
        )
        if self.index != "S&P 500" or expires <= effective or captured > expires:
            raise ValueError(
                "An effective, expiring S&P 500 membership snapshot is required"
            )
        if (
            not isinstance(self.symbols, (tuple, list))
            or not 1 <= len(self.symbols) <= 550
        ):
            raise ValueError("Expected a bounded constituent list")
        checked = tuple(sorted(symbol(item) for item in self.symbols))
        if len(set(checked)) != len(checked):
            raise ValueError("Duplicate constituent symbols")
        object.__setattr__(self, "symbols", checked)
        source_url(self.source)


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: str
    ask: str
    last: str
    as_of: str
    source: str
    session: str = "regular"
    currency: str = "USD"
    corporate_actions_checked_through: str | None = None

    def __post_init__(self):
        symbol(self.symbol)
        bid, ask, last = (
            number(item, positive=True) for item in (self.bid, self.ask, self.last)
        )
        if (
            bid > ask
            or self.currency != "USD"
            or self.session not in ("regular", "closed")
        ):
            raise ValueError(
                "Require a noncrossed USD quote with explicit session status"
            )
        timestamp(self.as_of)
        source_url(self.source)
        if self.corporate_actions_checked_through is not None:
            timestamp(self.corporate_actions_checked_through)


@dataclass(frozen=True)
class MarketSession:
    opens_at: str
    closes_at: str
    source: str

    def __post_init__(self):
        opened, closed = timestamp(self.opens_at), timestamp(self.closes_at)
        left, right = opened.astimezone(NEW_YORK), closed.astimezone(NEW_YORK)
        if (
            opened >= closed
            or left.date() != right.date()
            or left.weekday() >= 5
            or (left.hour, left.minute, left.second) != (9, 30, 0)
            or (right.hour, right.minute, right.second) not in ((13, 0, 0), (16, 0, 0))
        ):
            raise ValueError(
                "Require an explicit US regular or early-close trading session"
            )
        source_url(self.source)


@dataclass(frozen=True)
class DailyBar:
    """A sourced unadjusted session bar; only its opening price is used for fills."""

    symbol: str
    opens_at: str
    open: str
    high: str
    low: str
    close: str
    observed_at: str
    source: str
    currency: str = "USD"
    corporate_actions_checked_through: str | None = None
    source_sha256: str | None = None

    def __post_init__(self):
        symbol(self.symbol)
        opening, high, low, closing = (
            number(item, positive=True)
            for item in (self.open, self.high, self.low, self.close)
        )
        if (
            not low <= opening <= high
            or not low <= closing <= high
            or self.currency != "USD"
        ):
            raise ValueError("Require a coherent unadjusted USD daily OHLC bar")
        if timestamp(self.observed_at) < timestamp(self.opens_at):
            raise ValueError("A session opening must exist before its bar is observed")
        source_url(self.source)
        if self.corporate_actions_checked_through is not None:
            timestamp(self.corporate_actions_checked_through)
        if self.source_sha256 is not None and not re.fullmatch(
            r"[a-f0-9]{64}", self.source_sha256
        ):
            raise ValueError("A source digest must be a complete lowercase SHA-256")


@dataclass(frozen=True)
class BenchmarkPoint:
    as_of: str
    value: str
    source: str
    captured_at: str
    kind: str = "sp500_total_return"
    currency: str = "USD"
    source_sha256: str | None = None

    def __post_init__(self):
        if self.kind != "sp500_total_return" or self.currency != "USD":
            raise ValueError("A USD S&P 500 total-return index observation is required")
        number(self.value, positive=True)
        if timestamp(self.captured_at) < timestamp(self.as_of):
            raise ValueError("Index observations cannot be captured before they exist")
        source_url(self.source)
        host = urlsplit(self.source).hostname
        if (
            host != "spglobal.com"
            and not host.endswith(".spglobal.com")
            and self.source != YAHOO_SP500TR
        ):
            raise ValueError(
                "Benchmark observations require S&P or the exact identified Yahoo total-return series"
            )
        if self.source_sha256 is not None and not re.fullmatch(
            r"[a-f0-9]{64}", self.source_sha256
        ):
            raise ValueError("A source digest must be a complete lowercase SHA-256")
        if self.source == YAHOO_SP500TR and self.source_sha256 is None:
            raise ValueError(
                "Third-party benchmark observations require their captured source digest"
            )


def record(value):
    """Make a JSON-safe copy of a validated dataclass."""
    return asdict(value)
