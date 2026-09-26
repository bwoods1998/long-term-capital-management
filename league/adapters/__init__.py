"""Live venue adapters: shared credentials, signing and request plumbing.

Every adapter in this package implements `league.broker.Broker` against a real venue and
obeys the same four rules:

1. **Credentials are injected, never read.** A `Credentials` dataclass is constructed by the
   service from whatever secret store it uses. Nothing in this package touches `os.environ`,
   `.env` or a key file, so an adapter can never widen its own access.
2. **Secrets never reach a log or a repr.** Every credentials class masks itself, and no request
   body, header dict or exception message built here contains a key, a secret or a signature.
3. **The intent id is the idempotency key.** `client_order_id` is `OrderIntent.id`, so a retry
   after a lost response finds the original order instead of placing a second one.
4. **An unconfirmed write is `UnknownOutcome`, never a silent retry.** When a POST times out the
   adapter looks the order up by its client order id; if that lookup cannot confirm either way,
   it raises `UnknownOutcome` and the service reconciles before anything else happens.

The live House uses gateway mode and holds no venue credential. Direct Alpaca credentials exist only
for injected offline adapter tests; all production orders cross the gateway money boundary.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol, runtime_checkable

from ..broker import (
    BrokerError,
    Order,
    RejectedOrder,
    UnknownOutcome,
    VenueUnavailable,
    money,
)
from ..data import HttpTransport

JSON = "application/json"


# ------------------------------------------------------------------- signing

@runtime_checkable
class Signer(Protocol):
    """Signs a byte string with a private key the adapter never sees.

    `algorithm` names the scheme so a caller building a JWS header knows what to write.
    Implementations must be safe to call from several threads.
    """

    algorithm: str

    def sign(self, message: bytes) -> bytes:
        """Return the raw signature bytes, already in the form the venue expects."""






class GatewaySigner:
    """Gateway mode: this process holds no venue key at all, only a bearer token.

    The order gateway (a separate Cloudflare Worker) holds the Kalshi and Coinbase private keys,
    signs every request itself, and enforces the hard caps and the kill switch before it forwards
    anything. So an adapter running in gateway mode still builds the same request, but the
    signature it would have produced is empty and `VenueClient` replaces the venue's auth headers
    with `Authorization: Bearer <token>` on the way out.

    The difference this makes is the whole point of the arrangement: a machine running the desks
    can ask for an order, but it cannot sign one, and it cannot raise its own limits.
    """

    algorithm = "none"

    def __init__(self, token: str):
        if not isinstance(token, str) or len(token.strip()) < 32:
            raise ValueError("gateway token must be at least 32 characters")
        self._token = token.strip()

    def headers(self) -> dict[str, str]:
        """The only credential this process has: the gateway's bearer token."""
        return {"Authorization": "Bearer " + self._token}

    def sign(self, message: bytes) -> bytes:
        """No key, no signature. The gateway signs; `VenueClient` drops what this produces."""
        return b""

    def __repr__(self) -> str:  # never print the token
        return "GatewaySigner(<token>)"






# --------------------------------------------------------------- credentials

class _Masked:
    """Mixin: a credentials repr shows the shape of the secret, never the secret."""

    def __repr__(self) -> str:
        name = type(self).__name__
        identity = getattr(self, "key_id", None) or getattr(self, "key_name", "")
        tail = str(identity)[-4:] if identity else "?"
        return f"{name}(key_id=...{tail}, secret=<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class AlpacaCredentials(_Masked):
    """Alpaca header auth. `paper` picks the base URL; nothing else changes."""

    key_id: str
    secret_key: str
    paper: bool = True

    def __post_init__(self):
        if not isinstance(self.key_id, str) or not self.key_id.strip():
            raise ValueError("alpaca key_id is required")
        if not isinstance(self.secret_key, str) or not self.secret_key.strip():
            raise ValueError("alpaca secret_key is required")

    def headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
        }






# ----------------------------------------------------------------- requests

def encode(body: Any) -> bytes:
    """A request body as compact, sorted JSON so the same order always serializes the same."""
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decode(payload: bytes, *, what: str) -> Any:
    """Parse a response body with Decimal numbers. Never returns a float."""
    if not payload:
        return None
    try:
        return json.loads(
            payload.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=lambda name: (_ for _ in ()).throw(BrokerError(f"{what}: {name}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError(f"{what}: malformed JSON response") from exc


def dec(value: Any, default: Any = None) -> "Decimal | None":
    """Parse a venue number defensively; `None` for null, missing or unusable values."""
    if value is None or isinstance(value, bool):
        return None if default is None else money(default)
    if isinstance(value, float):
        value = repr(value)
    try:
        parsed = money(value)
    except (ValueError, ArithmeticError):
        return None if default is None else money(default)
    return parsed if parsed.is_finite() else (None if default is None else money(default))


def message_of(payload: Any, *, limit: int = 300) -> str:
    """A short human-readable error from a venue body, with no echo of what we sent."""
    if isinstance(payload, dict):
        for key in ("message", "error_message", "error", "msg", "detail", "reason"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:limit]
        return json.dumps(payload, sort_keys=True)[:limit]
    if isinstance(payload, str):
        return payload.strip()[:limit]
    return ""


GATEWAY_PREFIXES = {"alpaca": "/", "alpaca-paper": "/"}
VENUE_AUTH_HEADERS = ("authorization", "apca-api-key-id", "apca-api-secret-key")
PURPOSE_HEADER = "X-LTCM-Purpose"


def gateway_path(venue: str, url: str) -> tuple[str, str]:
    """Split a venue URL into `(path, query)` as the gateway wants them: no host, no prefix."""
    if venue not in GATEWAY_PREFIXES:
        raise ValueError(f"unsupported gateway venue {venue!r}")
    parts = urllib.parse.urlsplit(url)
    path = parts.path
    prefix = GATEWAY_PREFIXES.get(venue, "/")
    path = path[len(prefix):] if path.startswith(prefix) else path.lstrip("/")
    return path.lstrip("/"), parts.query


def gateway_url_for(gateway_url: str, venue: str, url: str) -> str:
    """A venue URL rewritten onto the order gateway: `<gateway_url>/v1/<venue>/<path>?<query>`."""
    path, query = gateway_path(venue, url)
    rewritten = f"{gateway_url.rstrip('/')}/v1/{venue}/{path}"
    return rewritten + ("?" + query if query else "")


class VenueClient:
    """A thin signed-or-keyed HTTP client shared by the adapters.

    Wraps a transport exposing `request(method, url, headers=, body=, timeout=)`. HTTP status
    codes come back to the caller; only a transport failure raises, and it raises
    `TransportError` so the caller can decide whether that means `UnknownOutcome`.

    **Gateway mode.** Given `gateway_url`, a `venue` and a `GatewaySigner`, every request is
    rewritten onto the order gateway instead of the venue, the venue's own auth headers are
    dropped, and the gateway's bearer token is the only credential that leaves this process. The
    adapters above are unchanged by this: they build the same request either way, and the one
    thing they cannot do in gateway mode is produce a valid venue signature.
    """

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        user_agent: Any = None,
        gateway_url: "str | None" = None,
        gateway: Any = None,
        venue: "str | None" = None,
    ):
        self.transport = transport or HttpTransport(
            **({"user_agent": user_agent} if user_agent else {})
        )
        self.timeout = float(timeout)
        self.calls: list[dict[str, Any]] = []
        if gateway_url and (gateway is None or venue not in GATEWAY_PREFIXES):
            raise ValueError("gateway mode needs a GatewaySigner and a venue name")
        self.gateway_url = gateway_url.rstrip("/") if gateway_url else None
        self.gateway = gateway
        self.venue = venue

    def _to_gateway(
        self, method: str, url: str, headers: dict[str, str], body: Any
    ) -> tuple[str, dict[str, str]]:
        """Rewrite one request for the gateway: its URL, its auth, and a price when it needs one."""
        path, _ = gateway_path(self.venue or "", url)
        sent = {
            name: value
            for name, value in headers.items()
            if name.lower() not in VENUE_AUTH_HEADERS
        }
        sent.update(self.gateway.headers())
        return gateway_url_for(self.gateway_url or "", self.venue or "", url), sent

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: "dict[str, str] | None" = None,
        body: Any = None,
        what: str = "venue",
    ) -> tuple[int, Any]:
        """One request. Returns `(status, parsed json)`; raises `TransportError` on no reply."""
        sent = {"Accept": JSON}
        if body is not None:
            sent["Content-Type"] = JSON
        sent.update(headers or {})
        if self.gateway_url:
            url, sent = self._to_gateway(method, url, sent, body)
        payload = encode(body) if body is not None else None
        status, _, raw = self.transport.request(
            method, url, headers=sent, body=payload, timeout=self.timeout
        )
        try:
            return status, decode(raw, what=what)
        except BrokerError:
            if 200 <= status < 300:
                raise  # a successful response that is not JSON is a real shape change
            # A failing response often carries an HTML error page from a proxy. The status
            # code is the fact that matters; keep the text as the message and let the caller
            # classify it rather than reporting "malformed JSON" for a plain 503.
            return status, {"message": raw.decode("utf-8", "replace").strip()[:300]}


def require_ok(status: int, payload: Any, *, what: str, ok: tuple[int, ...] = (200, 201, 204)) -> Any:
    """Turn a non-success status into the right `BrokerError` subclass."""
    if status in ok:
        return payload
    detail = message_of(payload)
    text_value = f"{what}: HTTP {status}{(' ' + detail) if detail else ''}"
    if status in (401, 403):
        raise VenueUnavailable(text_value)
    if status == 429 or status >= 500:
        raise VenueUnavailable(text_value)
    raise RejectedOrder(text_value)


def confirm_or_unknown(
    lookup: Callable[[], "Order | None"], *, what: str, detail: str
) -> Order:
    """After a lost write: return the venue's copy of the order, or raise `UnknownOutcome`.

    Never retries the write. A second POST with the same `client_order_id` would be rejected by
    a well-behaved venue, but "well-behaved" is not something to bet the book on.
    """
    try:
        found = lookup()
    except Exception:  # the follow-up failed too; the outcome is still unknown
        found = None
    if found is not None:
        return found
    raise UnknownOutcome(f"{what}: {detail}; order state could not be confirmed - reconcile")




__all__ = ["GatewaySigner", "AlpacaCredentials", "VenueClient", "GATEWAY_PREFIXES", "VENUE_AUTH_HEADERS",
           "PURPOSE_HEADER", "gateway_path", "gateway_url_for", "encode", "decode", "dec", "message_of",
           "require_ok", "confirm_or_unknown"]
