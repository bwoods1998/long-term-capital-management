"""Injected doubles for the Long Term Capital Management tests.

Nothing under `ltcm/tests/` opens a socket, reads a credential or looks at a wall clock.
Every source of nondeterminism in the runtime is an injected object, and these are the fakes the
tests inject: a transport that replays scripted HTTP responses and records what was asked for, a
clock the test advances by hand, a signer that records the bytes it was asked to sign and returns
a constant, and a market-data source whose quotes the test writes directly.

This module is deliberately named so `unittest discover` does not collect it.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from ltcm.broker import Instrument, Quote, money
from ltcm.data import DataError, TransportError, iso, us_equity_session


class Clock:
    """A clock the test moves. Calling it yields Unix seconds, like `time.time`."""

    def __init__(self, start: Any = "2026-09-15T13:30:00Z"):
        from ltcm.data import to_datetime

        self.now = to_datetime(start).timestamp()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now

    def set(self, value: Any) -> float:
        from ltcm.data import to_datetime

        self.now = to_datetime(value).timestamp()
        return self.now

    @property
    def iso(self) -> str:
        return iso(self.now)


class FakeTransport:
    """Replays scripted responses and records every request. Never touches the network.

    A route key is a URL, a `(method, url)` pair, or a URL prefix ending in `*`. The value is a
    `(status, headers, body)` triple, a bytes/str body (status 200), a JSON-serializable object,
    an exception instance to raise, or a callable taking `(method, url, body)`.
    """

    def __init__(self, routes: "dict[Any, Any] | None" = None, *, default: Any = None):
        self.routes: dict[Any, Any] = dict(routes or {})
        self.default = default
        self.calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ setup
    def route(self, key: Any, value: Any) -> "FakeTransport":
        self.routes[key] = value
        return self

    # --------------------------------------------------------------- requests
    def get(self, url: str, headers: "dict[str, str] | None" = None, timeout: Any = None):
        return self.request("GET", url, headers=headers, timeout=timeout)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: "dict[str, str] | None" = None,
        body: "bytes | None" = None,
        timeout: Any = None,
    ) -> tuple[int, dict[str, str], bytes]:
        method = method.upper()
        parsed = json.loads(body.decode("utf-8")) if body else None
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": urllib.parse.urlsplit(url).path,
                "query": dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)),
                "headers": dict(headers or {}),
                "body": parsed,
                "raw_body": body,
            }
        )
        handler = self._match(method, url)
        if handler is None:
            raise AssertionError(f"no scripted response for {method} {url}")
        if callable(handler) and not isinstance(handler, BaseException):
            handler = handler(method, url, parsed)
        if isinstance(handler, BaseException):
            raise handler
        return _as_response(handler)

    def _match(self, method: str, url: str) -> Any:
        bare = url.split("?", 1)[0]
        for key in ((method, url), url, (method, bare), bare):
            if key in self.routes:
                return self.routes[key]
        for key, value in self.routes.items():
            candidate = key[1] if isinstance(key, tuple) else key
            if isinstance(key, tuple) and key[0] != method:
                continue
            if isinstance(candidate, str) and candidate.endswith("*") and url.startswith(candidate[:-1]):
                return value
        return self.default

    # ------------------------------------------------------------ assertions
    @property
    def last(self) -> dict[str, Any]:
        if not self.calls:
            raise AssertionError("no requests were made")
        return self.calls[-1]

    def call(self, index: int) -> dict[str, Any]:
        return self.calls[index]

    def paths(self) -> list[str]:
        return [call["path"] for call in self.calls]


def _as_response(value: Any) -> tuple[int, dict[str, str], bytes]:
    if isinstance(value, tuple) and len(value) == 3:
        status, headers, body = value
        return int(status), {k.lower(): v for k, v in dict(headers or {}).items()}, _as_bytes(body)
    return 200, {"content-type": "application/json"}, _as_bytes(value)


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, default=str).encode("utf-8")


class FakeSigner:
    """Records the exact bytes it was asked to sign and returns a fixed signature."""

    def __init__(self, algorithm: str = "RSA-PSS-SHA256", signature: bytes = b"woods-signature"):
        self.algorithm = algorithm
        self.signature = signature
        self.messages: list[bytes] = []

    def sign(self, message: bytes) -> bytes:
        self.messages.append(message)
        return self.signature

    @property
    def last_message(self) -> str:
        if not self.messages:
            raise AssertionError("nothing was signed")
        return self.messages[-1].decode("utf-8")


class ScriptedMarketData:
    """A `MarketData` whose quotes the test writes by hand."""

    source = "test"

    def __init__(self, clock: Any = None):
        self.clock = clock or Clock()
        self.quotes: dict[str, Quote] = {}
        self.bar_rows: dict[str, list] = {}
        self.calls: list[str] = []

    def set(
        self,
        instrument: Instrument,
        *,
        bid: Any = None,
        ask: Any = None,
        last: Any = None,
        delayed: bool = True,
    ) -> Quote:
        quote = Quote(
            instrument=instrument,
            bid=money(bid) if bid is not None else None,
            ask=money(ask) if ask is not None else None,
            last=money(last) if last is not None else None,
            as_of=iso(self.clock()),
            source=self.source,
            delayed=delayed,
        )
        self.quotes[instrument.key] = quote
        return quote

    def clear(self, instrument: Instrument) -> None:
        self.quotes.pop(instrument.key, None)

    def quote(self, instrument: Instrument) -> Quote:
        self.calls.append(instrument.key)
        quote = self.quotes.get(instrument.key)
        if quote is None:
            raise DataError(f"no scripted quote for {instrument.key}")
        return quote

    def bars(self, instrument: Instrument, interval: str = "1d", limit: int = 30) -> list:
        return list(self.bar_rows.get(instrument.key, []))[-limit:]

    def session(self, day: Any):
        return us_equity_session(day)

    def adv_usd(self, instrument: Instrument) -> None:
        return None


__all__ = [
    "Clock",
    "FakeTransport",
    "FakeSigner",
    "ScriptedMarketData",
    "TransportError",
]
