"""Public daily-bar adapter for paper trading; Yahoo is a third-party source.

NYSE's reviewed 2026 calendar fixes the next opening before any outcome exists.
Yahoo daily OHLC and reported actions provide an explicitly delayed paper model,
not exchange execution or a real-time quote subscription. The benchmark adapter
uses Yahoo's specifically identified S&P 500 total-return series, never an ETF
or the S&P 500 price index. Its third-party provenance remains in every receipt.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote as urlquote, urlencode
from urllib.request import Request, urlopen

from .contracts import (
    BenchmarkPoint,
    DailyBar,
    MarketSession,
    NEW_YORK,
    UTC,
    YAHOO_SP500TR,
    decimal_text,
    symbol,
    timestamp,
    utc_now,
)


CALENDAR_SOURCE = "https://www.nyse.com/trade/hours-calendars"
CALENDAR_REVIEWED_ON = "2026-09-13"
CALENDAR_YEAR = 2026
HOLIDAYS = frozenset(
    (
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-04-03",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
        "2026-11-26",
        "2026-12-25",
    )
)
EARLY_CLOSES = frozenset(("2026-11-27", "2026-12-24"))
HOST = "query1.finance.yahoo.com"
MAX_RESPONSE_BYTES = 2_000_000


def _stamp(value):
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(value):
    if type(value) is not int or value < 0:
        raise ValueError("Market timestamps require nonnegative integer Unix seconds")
    return _stamp(datetime.fromtimestamp(value, UTC))


def session_for_day(day):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    if type(day) is not date or day.year != CALENDAR_YEAR:
        raise ValueError(
            "The reviewed NYSE calendar covers 2026 only; refresh it before another year"
        )
    if day.weekday() >= 5 or day.isoformat() in HOLIDAYS:
        return None
    opened = datetime.combine(day, time(9, 30), NEW_YORK)
    closed = datetime.combine(
        day, time(13 if day.isoformat() in EARLY_CLOSES else 16), NEW_YORK
    )
    return MarketSession(
        opens_at=_stamp(opened), closes_at=_stamp(closed), source=CALENDAR_SOURCE
    )


def next_session(decided_at):
    """The first reviewed opening strictly after a decision, including holidays."""
    instant = timestamp(decided_at)
    day = instant.astimezone(NEW_YORK).date()
    for _ in range(10):
        session = session_for_day(day)
        if session is not None and timestamp(session.opens_at) > instant:
            return session
        day += timedelta(days=1)
    raise ValueError("No next trading session is available in the reviewed calendar")


def latest_completed_session(observed_at):
    instant = timestamp(observed_at)
    day = instant.astimezone(NEW_YORK).date()
    for _ in range(10):
        session = session_for_day(day)
        if session is not None and timestamp(session.closes_at) <= instant:
            return session
        day -= timedelta(days=1)
    raise ValueError(
        "No completed trading session is available in the reviewed calendar"
    )


def chart_url(ticker):
    symbol(ticker)
    # Yahoo uses hyphens for share classes; the internal constituent symbol stays
    # unchanged and is checked again against the response metadata.
    provider_symbol = ticker.replace(".", "-")
    return (
        "https://"
        + HOST
        + "/v8/finance/chart/"
        + urlquote(provider_symbol, safe="-")
        + "?"
        + urlencode({"interval": "1d", "range": "1mo", "events": "div,splits"})
    )


def _price(value):
    # json.loads(parse_float=Decimal) avoids a second binary-float conversion.
    if type(value) is int:
        value = Decimal(value)
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not 0 < value < Decimal("1000000000000000")
    ):
        raise ValueError("OHLC values must be finite positive source numbers")
    with localcontext() as context:
        context.prec = 80
        result = value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
    if result <= 0:
        raise ValueError("A source price is below the supported decimal precision")
    return decimal_text(result)


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    captured_at: str
    source: str
    source_sha256: str
    bars: tuple[DailyBar, ...]
    actions: tuple[dict, ...]
    coverage_start: str
    last_trade_at: str | None = None
    provider: str = "Yahoo Finance"

    def bar(self, session):
        matches = [bar for bar in self.bars if bar.opens_at == session.opens_at]
        if len(matches) != 1:
            raise ValueError(
                "The provider has no complete bar for the required session"
            )
        return matches[0]


def parse_chart(raw, ticker, *, captured_at, source=None):
    """Validate an exact saved Yahoo response; missing action blocks mean none reported.

    The explicit events=div,splits request is preserved in the source URL. This
    is provider-reported action coverage, not a claim of independently verified
    completeness. Unknown event kinds, malformed actions and partial bars fail.
    """
    symbol(ticker)
    timestamp(captured_at)
    source = source or chart_url(ticker)
    if source != chart_url(ticker):
        raise ValueError("The source must identify the exact allowlisted chart request")
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Require a bounded original chart response")
    try:
        payload = json.loads(
            raw,
            parse_float=Decimal,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError("Non-finite JSON")
            ),
        )
        chart = payload["chart"]
        if chart.get("error") is not None or len(chart["result"]) != 1:
            raise ValueError("The provider did not return one usable equity chart")
        item = chart["result"][0]
        meta = item["meta"]
        if (
            meta["symbol"] != ticker.replace(".", "-")
            or meta["currency"] != "USD"
            or meta["instrumentType"] != "EQUITY"
            or meta["exchangeTimezoneName"] != "America/New_York"
            or meta.get("dataGranularity") != "1d"
        ):
            raise ValueError(
                "The chart does not identify the requested daily US equity"
            )
        last_trade_at = (
            _epoch(meta["regularMarketTime"])
            if meta.get("regularMarketTime") is not None
            else None
        )
        if last_trade_at is not None and timestamp(last_trade_at) > timestamp(
            captured_at
        ):
            raise ValueError("Provider market time cannot be later than this capture")
        times = item["timestamp"]
        series = item["indicators"]["quote"]
        if (
            not isinstance(times, list)
            or not 1 <= len(times) <= 40
            or len(series) != 1
            or any(
                not isinstance(series[0].get(field), list)
                or len(series[0][field]) != len(times)
                for field in ("open", "high", "low", "close", "volume")
            )
        ):
            raise ValueError("Daily chart arrays must be bounded and aligned")
        bars = []
        source_sha256 = sha256(raw).hexdigest()
        last = None
        for index, epoch in enumerate(times):
            opened = _epoch(epoch)
            if last is not None and timestamp(opened) <= timestamp(last):
                raise ValueError("Daily chart timestamps must be unique and increasing")
            last = opened
            if timestamp(opened) > timestamp(captured_at):
                raise ValueError("The chart contains a future opening")
            session = session_for_day(timestamp(opened).astimezone(NEW_YORK).date())
            if session is None or session.opens_at != opened:
                raise ValueError(
                    "The chart opening disagrees with the reviewed market calendar"
                )
            values = [
                series[0][field][index] for field in ("open", "high", "low", "close")
            ]
            volume = series[0]["volume"][index]
            if all(value is None for value in values) and volume in (None, 0):
                continue
            if (
                any(value is None for value in values)
                or type(volume) is not int
                or volume <= 0
            ):
                raise ValueError(
                    "An executable paper bar requires complete OHLC and positive reported volume"
                )
            bars.append(
                DailyBar(
                    symbol=ticker,
                    opens_at=opened,
                    open=_price(values[0]),
                    high=_price(values[1]),
                    low=_price(values[2]),
                    close=_price(values[3]),
                    observed_at=captured_at,
                    source=source,
                    corporate_actions_checked_through=captured_at,
                    source_sha256=source_sha256,
                )
            )
        if not bars:
            raise ValueError("No complete traded daily bars are available")
        events = item.get("events", {})
        if not isinstance(events, dict) or set(events) - {"dividends", "splits"}:
            raise ValueError("Unknown corporate-action data requires explicit review")
        actions = []
        for kind, mapping in events.items():
            if not isinstance(mapping, dict) or len(mapping) > 100:
                raise ValueError("Corporate-action records must be a bounded mapping")
            for key, action in mapping.items():
                effective_at = _epoch(action["date"])
                if key != str(action["date"]) or timestamp(effective_at) > timestamp(
                    captured_at
                ):
                    raise ValueError(
                        "Corporate-action dates must be identified and already observed"
                    )
                if kind == "dividends":
                    details = {"amount": _price(action["amount"])}
                else:
                    numerator, denominator = action["numerator"], action["denominator"]
                    if (
                        type(numerator) is not int
                        or type(denominator) is not int
                        or numerator <= 0
                        or denominator <= 0
                    ):
                        raise ValueError(
                            "Split ratios require explicit positive integer terms"
                        )
                    details = {"numerator": numerator, "denominator": denominator}
                content = {
                    "symbol": ticker,
                    "kind": kind,
                    "effective_at": effective_at,
                    **details,
                }
                action_id = (
                    "yahoo-"
                    + sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[
                        :40
                    ]
                )
                actions.append({"id": action_id, **content})
        return MarketSnapshot(
            symbol=ticker,
            captured_at=captured_at,
            source=source,
            source_sha256=source_sha256,
            bars=tuple(bars),
            actions=tuple(
                sorted(
                    actions, key=lambda action: (action["effective_at"], action["id"])
                )
            ),
            coverage_start=bars[0].opens_at,
            last_trade_at=last_trade_at,
        )
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Yahoo chart response") from exc


def parse_benchmark(raw, *, captured_at):
    """Read only ^SP500TR OHLC boundaries, with exact provider identity checks."""
    timestamp(captured_at)
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Require a bounded original index response")
    try:
        data = json.loads(raw, parse_float=Decimal)
        chart = data["chart"]
        if chart.get("error") is not None or len(chart["result"]) != 1:
            raise ValueError("The provider did not return one total-return index")
        item = chart["result"][0]
        meta = item["meta"]
        if (
            meta["symbol"] != "^SP500TR"
            or meta["instrumentType"] != "INDEX"
            or meta["currency"] != "USD"
            or meta["exchangeTimezoneName"] != "America/New_York"
            or meta["dataGranularity"] != "1d"
            or meta["longName"] != "S&P 500 (TR)"
        ):
            raise ValueError(
                "Expected the specifically identified USD S&P 500 total-return index"
            )
        last_trade = timestamp(_epoch(meta["regularMarketTime"]))
        if last_trade > timestamp(captured_at):
            raise ValueError("A future benchmark update cannot be observed")
        times, series = item["timestamp"], item["indicators"]["quote"]
        if (
            not isinstance(times, list)
            or not 1 <= len(times) <= 40
            or len(series) != 1
            or any(
                not isinstance(series[0].get(field), list)
                or len(series[0][field]) != len(times)
                for field in ("open", "high", "low", "close")
            )
        ):
            raise ValueError("Benchmark OHLC arrays must be bounded and aligned")
        previous, points, digest = None, [], sha256(raw).hexdigest()
        for index, epoch in enumerate(times):
            opened = _epoch(epoch)
            if previous is not None and timestamp(opened) <= timestamp(previous):
                raise ValueError("Benchmark openings must be unique and increasing")
            previous = opened
            session = session_for_day(timestamp(opened).astimezone(NEW_YORK).date())
            if (
                session is None
                or session.opens_at != opened
                or timestamp(opened) > last_trade
            ):
                raise ValueError(
                    "Benchmark opening must match an already observed calendar session"
                )
            values = [
                _price(series[0][field][index])
                for field in ("open", "high", "low", "close")
            ]
            opening, high, low, closing = map(Decimal, values)
            if not low <= opening <= high or not low <= closing <= high:
                raise ValueError("Benchmark OHLC values are inconsistent")
            points.append(
                BenchmarkPoint(
                    as_of=opened,
                    value=values[0],
                    source=YAHOO_SP500TR,
                    captured_at=captured_at,
                    source_sha256=digest,
                )
            )
            if timestamp(session.closes_at) <= last_trade:
                points.append(
                    BenchmarkPoint(
                        as_of=session.closes_at,
                        value=values[3],
                        source=YAHOO_SP500TR,
                        captured_at=captured_at,
                        source_sha256=digest,
                    )
                )
        return points
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Yahoo total-return index response") from exc


class YahooMarketData:
    """Small bounded read-only HTTP client with exact private response captures."""

    def __init__(
        self, directory, *, opener=urlopen, clock=utc_now, benchmark_enabled=True
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.opener, self.clock = opener, clock
        self.benchmark_enabled = benchmark_enabled

    def fetch(self, ticker):
        url = chart_url(ticker)
        request = Request(
            url,
            headers={
                "User-Agent": "PortfolioAgent/1.0 (public paper research)",
                "Accept": "application/json",
            },
        )
        with self.opener(request, timeout=20) as response:
            if response.geturl() != url or response.status != 200:
                raise ValueError(
                    "Market data must come directly from the allowlisted chart endpoint"
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        captured = self.clock()
        snapshot = parse_chart(raw, ticker, captured_at=captured, source=url)
        name = (
            ticker
            + "-"
            + captured.replace(":", "").replace("-", "")
            + "-"
            + snapshot.source_sha256[:16]
        )
        path = self.directory / (name + ".json")
        # Identical bytes are content addressed. No credentials or account values
        # are sent in this request, and no provider response is published here.
        path.write_bytes(raw)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "provider": snapshot.provider,
                    "symbol": ticker,
                    "source": url,
                    "captured_at": captured,
                    "sha256": snapshot.source_sha256,
                    "price_rounding": "8 decimal places, half even",
                    "actions": "Provider-reported dividends and splits from the requested month",
                },
                indent=2,
            )
            + "\n"
        )
        return snapshot

    def snapshot_price(self, ticker):
        snapshot = self.fetch(ticker)
        bar = snapshot.bars[-1]
        session = session_for_day(timestamp(bar.opens_at).astimezone(NEW_YORK).date())
        complete = (
            snapshot.last_trade_at is not None
            and timestamp(snapshot.last_trade_at) >= timestamp(session.closes_at)
            and timestamp(snapshot.captured_at) >= timestamp(session.closes_at)
        )
        return {
            "schema_version": 1,
            "symbol": ticker,
            "currency": "USD",
            "price": bar.close,
            "price_kind": "daily_close" if complete else "session_to_date",
            "as_of": session.closes_at if complete else snapshot.last_trade_at,
            "captured_at": snapshot.captured_at,
            "source": snapshot.source,
            "source_sha256": snapshot.source_sha256,
            "provider": snapshot.provider,
            "adjusted": False,
        }

    def fetch_benchmark(self):
        request = Request(
            YAHOO_SP500TR,
            headers={
                "User-Agent": "PortfolioAgent/1.0 (public paper research)",
                "Accept": "application/json",
            },
        )
        with self.opener(request, timeout=20) as response:
            if response.geturl() != YAHOO_SP500TR or response.status != 200:
                raise ValueError(
                    "The total-return series must come directly from its allowlisted endpoint"
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        captured = self.clock()
        points = parse_benchmark(raw, captured_at=captured)
        digest = sha256(raw).hexdigest()
        name = (
            "SP500TR-" + captured.replace(":", "").replace("-", "") + "-" + digest[:16]
        )
        path = self.directory / (name + ".json")
        path.write_bytes(raw)
        path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "provider": "Yahoo Finance",
                    "symbol": "^SP500TR",
                    "source": YAHOO_SP500TR,
                    "captured_at": captured,
                    "sha256": digest,
                    "kind": "sp500_total_return",
                    "price_rounding": "8 decimal places, half even",
                },
                indent=2,
            )
            + "\n"
        )
        return points

    def sync_benchmark(self, ledger):
        """Attach available matching boundaries; a missing index never blocks trades.

        Later observations may supply a previously missing baseline, but cannot
        change an already recorded index point or an investment decision.
        """
        state = ledger.public_state()
        if not self.benchmark_enabled or not state["history"]:
            return {
                "status": "unavailable",
                "observations_added": 0,
                "portfolio": state,
            }
        expected = {point["at"] for point in state["history"]}
        existing = {
            event["payload"]["as_of"]
            for event in ledger.events()
            if event["kind"] == "benchmark"
        }
        if expected <= existing:
            return {
                "status": state["performance"]["benchmark"]["status"],
                "observations_added": 0,
                "portfolio": state,
            }
        count = 0
        try:
            points = self.fetch_benchmark()
            recorded_at = self.clock()
            for point in points:
                if point.as_of in expected and point.as_of not in existing:
                    ledger.record_benchmark(point, recorded_at=recorded_at)
                    count += 1
        except (ValueError, OSError, TimeoutError):
            return {
                "status": "unavailable",
                "observations_added": count,
                "portfolio": ledger.public_state(),
            }
        state = ledger.public_state()
        return {
            "status": state["performance"]["benchmark"]["status"],
            "observations_added": count,
            "portfolio": state,
        }

    def establish_baseline(self, ledger, *, now=None):
        """Keep a cash-only Monday in the forward benchmark interval."""
        now = now or self.clock()
        state = ledger.public_state()
        if state["history"]:
            return {"status": "established", "portfolio": state}
        pending_ids = {decision["id"] for decision in state["pending_decisions"]}
        if any(not event["payload"].get("expected_open_at")
               or timestamp(event["payload"]["expected_open_at"]) <= timestamp(now)
               for event in ledger.events() if event["kind"] == "decision" and event["id"] in pending_ids):
            return {"status": "waiting_for_pending_fill", "portfolio": state}
        session = next_session(state["created_at"])
        if timestamp(now) < timestamp(session.opens_at):
            return {"status": "waiting_for_first_session", "portfolio": state}
        if not self.benchmark_enabled:
            return {"status": "unavailable", "portfolio": state}
        points = self.fetch_benchmark()
        point = next((p for p in points if p.as_of == session.opens_at), None)
        if point is None:
            return {"status": "unavailable", "portfolio": state}
        return {"status": "established", "portfolio": ledger.establish_cash_baseline(
            market_session=session, benchmark=point, observed_at=self.clock())}

    @staticmethod
    def _guard_actions(ledger, snapshots, *, observed_at):
        state = ledger.public_state()
        held = {holding["symbol"] for holding in state["holdings"]}
        boundary = state["as_of"] or state["created_at"]
        existing = {
            event["payload"]["action_id"]
            for event in ledger.events()
            if event["kind"] == "action_flag"
        }
        blocked = False
        for snapshot in snapshots:
            if snapshot.symbol not in held:
                continue
            if timestamp(snapshot.coverage_start) > timestamp(boundary):
                raise ValueError(
                    "Corporate-action coverage does not reach the last account valuation"
                )
            for action in snapshot.actions:
                if timestamp(action["effective_at"]) > timestamp(boundary):
                    if action["id"] not in existing:
                        ledger.flag_corporate_action(
                            snapshot.symbol,
                            action_id=action["id"],
                            effective_at=action["effective_at"],
                            observed_at=observed_at,
                            source=snapshot.source,
                        )
                    blocked = True
        if blocked:
            raise ValueError(
                "A reported corporate action requires its explicit accounting adapter before trading or marking"
            )

    def fill_pending(self, ledger, *, now=None):
        now = now or self.clock()
        state = ledger.public_state()
        if not state["pending_decisions"]:
            return {
                "status": "no_pending_decision",
                "portfolio": self.sync_benchmark(ledger)["portfolio"],
            }
        decision_id = state["pending_decisions"][0]["id"]
        decision = next(
            event["payload"]
            for event in ledger.events()
            if event["kind"] == "decision" and event["id"] == decision_id
        )
        expected = decision.get("expected_open_at")
        if expected is None:
            raise ValueError(
                "Pending decisions need a precommitted next opening before daily-bar execution"
            )
        session = next_session(decision["decided_at"])
        if (
            expected != session.opens_at
            or decision.get("calendar_source") != CALENDAR_SOURCE
        ):
            raise ValueError(
                "The decision calendar does not match the reviewed next session"
            )
        if timestamp(now) < timestamp(expected):
            return {
                "status": "waiting_for_market",
                "next_open_at": expected,
                "portfolio": state,
            }
        required = sorted(
            set(decision["targets"])
            | {holding["symbol"] for holding in state["holdings"]}
        )
        snapshots = [self.fetch(ticker) for ticker in required]
        observed_at = self.clock()
        self._guard_actions(ledger, snapshots, observed_at=observed_at)
        result = ledger.fill_at_next_open(
            decision_id,
            bars=[snapshot.bar(session) for snapshot in snapshots],
            now=observed_at,
            market_session=session,
        )
        return {
            "status": "filled",
            "receipt": result,
            "portfolio": self.sync_benchmark(ledger)["portfolio"],
        }

    def mark_close(self, ledger, *, now=None):
        now = now or self.clock()
        state = ledger.public_state()
        session = latest_completed_session(now)
        if timestamp(session.closes_at) < timestamp(state["created_at"]):
            return {"status": "waiting_for_first_session", "portfolio": state}
        if state["history"] and timestamp(state["history"][-1]["at"]) >= timestamp(
            session.closes_at
        ):
            return {
                "status": "up_to_date",
                "portfolio": self.sync_benchmark(ledger)["portfolio"],
            }
        snapshots = [self.fetch(holding["symbol"]) for holding in state["holdings"]]
        observed_at = self.clock()
        if any(
            snapshot.last_trade_at is None
            or timestamp(snapshot.last_trade_at) < timestamp(session.closes_at)
            for snapshot in snapshots
        ):
            raise ValueError(
                "The provider has not confirmed the completed session close"
            )
        self._guard_actions(ledger, snapshots, observed_at=observed_at)
        state = ledger.mark_daily_close(
            [snapshot.bar(session) for snapshot in snapshots],
            observed_at=observed_at,
            market_session=session,
        )
        return {
            "status": "marked",
            "portfolio": self.sync_benchmark(ledger)["portfolio"],
        }
